"""The release contract.

Two things are worth testing here and they are not the same thing. One is
that the engine now answers the questions the shared workflow asks it --
`dev=`, and `buildinfo`. The other is that `check-workflow` actually refuses
the shapes that made a release procedure unportable, because a conformance
check nobody can fail is worse than none: it certifies drift.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

FIXTURE = pathlib.Path(__file__).parent / "fixture"

# The smallest conforming caller there can be. Every test that expects a
# pass starts from this and every test that expects a failure breaks exactly
# one thing in it, so a failing test names the rule it broke.
GOOD = """
name: Release
on:
  push:
    tags: ["v*"]
  workflow_dispatch:
    inputs:
      ref: {type: string, required: false, default: ""}
      tag: {type: string, required: false, default: ""}
      publish: {type: boolean, required: false, default: false}
permissions:
  contents: read
concurrency:
  group: release-${{ inputs.tag || github.ref }}
jobs:
  preflight:
    uses: Aloecraft-org/technoproj/.github/workflows/release-preflight.yml@v0.3.0
  build:
    needs: preflight
    runs-on: ubuntu-latest
    steps: [{run: "true"}]
  publish:
    needs: [preflight, build]
    permissions:
      contents: write
    uses: Aloecraft-org/technoproj/.github/workflows/release-publish.yml@v0.3.0
"""


# Actions sets these on every job, and they are exactly the inputs the
# release tooling reads about "which repository is this". A test that
# inherits them passes on a workstation and fails in CI -- which is how this
# file learned to strip them.
AMBIENT = ("GITHUB_REPOSITORY", "GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_URL",
           "GITHUB_REF", "GITHUB_SHA", "GITHUB_ACTIONS")


def env_for(root):
    e = {k: v for k, v in os.environ.items() if k not in AMBIENT}
    e["TECHNO_ROOT"] = str(root)
    return e


def changelog(*args, root=FIXTURE):
    return subprocess.run([sys.executable, "-m", "technoproj.changelog", *args],
                          env=env_for(root), capture_output=True, text=True)


def cli(*args, root):
    return subprocess.run([sys.executable, "-m", "technoproj.cli", *args],
                          env=env_for(root), capture_output=True, text=True)


@pytest.fixture
def repo():
    """A copy of the fixture with a conforming release workflow."""
    tmp = tempfile.mkdtemp()
    try:
        for f in (".technoproj", "CHANGELOG.yaml"):
            shutil.copy(FIXTURE / f, os.path.join(tmp, f))
        wf = os.path.join(tmp, ".github", "workflows")
        os.makedirs(wf)
        with open(os.path.join(wf, "release.yml"), "w") as f:
            f.write(GOOD)
        # An origin, because `cut` names the repository it would dispatch
        # against even when it is only printing what it would send.
        os.makedirs(os.path.join(tmp, ".git"))
        with open(os.path.join(tmp, ".git", "config"), "w") as f:
            f.write('[remote "origin"]\n'
                    "\turl = https://github.com/Aloecraft-org/fixture.git\n")
        yield tmp
    finally:
        shutil.rmtree(tmp)


def edit(repo, old, new):
    p = os.path.join(repo, ".github", "workflows", "release.yml")
    text = open(p).read()
    assert old in text, "the fixture changed; %r is no longer in it" % old
    open(p, "w").write(text.replace(old, new))


def drop_input(repo, name):
    """Remove one `workflow_dispatch` input, whatever its type."""
    p = os.path.join(repo, ".github", "workflows", "release.yml")
    lines = open(p).read().splitlines(True)
    kept = [l for l in lines if not l.strip().startswith("%s: {" % name)]
    assert len(kept) == len(lines) - 1, "no `%s:` input to drop" % name
    open(p, "w").writelines(kept)


# ---------------------------------------------------------------------------
# the engine answers what the workflow asks
# ---------------------------------------------------------------------------

def test_release_check_always_says_whether_this_is_a_dev_build():
    # Every caller branches on it, so it is present for a plain release too
    # -- three repositories each worked this out in their own shell.
    out = changelog("release-check", "--tag", "v0.2.0").stdout
    assert "dev=false" in out
    assert "prerelease=false" in out


def test_a_dev_tag_needs_no_entry_of_its_own():
    r = changelog("release-check", "--tag", "v0.2.0-dev.7")
    assert r.returncode == 0, r.stderr
    assert "dev=true" in r.stdout
    assert "version=0.2.0-dev.7" in r.stdout
    assert "prerelease=true" in r.stdout


def test_a_dev_tag_of_a_version_the_changelog_has_not_reached_is_refused():
    r = changelog("release-check", "--tag", "v9.9.9-dev.1")
    assert r.returncode == 1
    assert "newest entry" in r.stderr


def test_buildinfo_prints_the_declared_facts():
    r = changelog("buildinfo", "--tag", "v0.2.0")
    assert r.returncode == 0, r.stderr
    assert r.stdout == "widget_abi: 3\n"


def test_buildinfo_of_a_dev_tag_uses_the_entry_it_was_cut_from():
    assert changelog("buildinfo", "--tag", "v0.2.0-dev.7").stdout == "widget_abi: 3\n"


def test_buildinfo_refuses_a_tag_nothing_claims():
    r = changelog("buildinfo", "--tag", "v0.9.9")
    assert r.returncode != 0
    assert "no release with tag" in (r.stderr + r.stdout)


# ---------------------------------------------------------------------------
# the conformance check refuses what it is for
# ---------------------------------------------------------------------------

def test_the_reference_caller_conforms(repo):
    r = cli("release", "check-workflow", root=repo)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("missing", ["ref", "tag", "publish"])
def test_a_missing_dispatch_input_fails(repo, missing):
    # This is the difference that made one repo's release procedure
    # unusable in the next: aloelite had no `tag` input at all.
    drop_input(repo, missing)
    r = cli("release", "check-workflow", root=repo)
    assert r.returncode == 1
    assert "inputs.%s` is missing" % missing in r.stderr


def test_a_publish_job_without_contents_write_fails(repo):
    # The single most expensive failure: a 403 at the last step of a
    # twenty-minute build.
    edit(repo, "    permissions:\n      contents: write\n", "")
    r = cli("release", "check-workflow", root=repo)
    assert r.returncode == 1
    assert "contents: write" in r.stderr


def test_an_unpinned_shared_workflow_fails(repo):
    edit(repo, "release-preflight.yml@v0.3.0", "release-preflight.yml@main")
    r = cli("release", "check-workflow", root=repo)
    assert r.returncode == 1
    assert "pin a technoproj release tag" in r.stderr


def test_reimplementing_preflight_instead_of_calling_it_fails(repo):
    edit(repo,
         "  preflight:\n    uses: Aloecraft-org/technoproj"
         "/.github/workflows/release-preflight.yml@v0.3.0\n",
         "  preflight:\n    runs-on: ubuntu-latest\n    steps: [{run: \"true\"}]\n")
    r = cli("release", "check-workflow", root=repo)
    assert r.returncode == 1
    assert "release-preflight.yml" in r.stderr


def test_a_top_level_write_permission_fails(repo):
    edit(repo, "permissions:\n  contents: read\n",
         "permissions:\n  contents: write\n")
    r = cli("release", "check-workflow", root=repo)
    assert r.returncode == 1
    assert "contents: read" in r.stderr


def test_no_tag_trigger_fails(repo):
    edit(repo, '    tags: ["v*"]\n', '    branches: ["main"]\n')
    r = cli("release", "check-workflow", root=repo)
    assert r.returncode == 1
    assert "on.push.tags" in r.stderr


def test_a_missing_workflow_says_so_rather_than_crashing(repo):
    os.remove(os.path.join(repo, ".github", "workflows", "release.yml"))
    r = cli("release", "check-workflow", root=repo)
    assert r.returncode == 1
    assert "does not exist" in r.stderr


def test_on_is_read_despite_yaml_reading_it_as_true(repo):
    # `on:` parses to the boolean True under YAML 1.1. A checker that misses
    # that passes everything, which is worse than not checking.
    import yaml
    doc = yaml.safe_load(open(os.path.join(repo, ".github", "workflows",
                                           "release.yml")))
    assert True in doc or "on" in doc
    assert cli("release", "check-workflow", root=repo).returncode == 0


# ---------------------------------------------------------------------------
# the registry hand-off (issue #6)
# ---------------------------------------------------------------------------

# A registry workflow shaped the way all three of ours are: it triggers on a
# tag push, which the release's own GITHUB_TOKEN-created tag never fires.
TAG_TRIGGERED = ('name: Publish\non:\n  push:\n    tags: ["v*"]\n'
                 "jobs:\n  publish:\n    runs-on: ubuntu-latest\n"
                 "    permissions:\n      id-token: write\n"
                 "      contents: read\n    steps: [{run: \"true\"}]\n")

DISPATCHABLE = ('name: Publish\non:\n  push:\n    tags: ["v*"]\n'
                "  workflow_dispatch:\n    inputs:\n"
                "      tag: {type: string, required: true}\n"
                "jobs:\n  publish:\n    runs-on: ubuntu-latest\n"
                "    permissions:\n      id-token: write\n"
                "      contents: read\n    steps: [{run: \"true\"}]\n")


def with_registry(repo, publish_yml, handoff=True):
    """Declare a pypi leg, and optionally wire the hand-off correctly."""
    p = os.path.join(repo, ".technoproj")
    proj = json.loads(open(p).read())
    proj["TECHNO_RELEASE"] = {"registry": {"kind": "pypi",
                                           "workflow": "publish.yml"}}
    open(p, "w").write(json.dumps(proj, indent=2))
    open(os.path.join(repo, ".github", "workflows", "publish.yml"),
         "w").write(publish_yml)
    if handoff:
        edit(repo,
             "    permissions:\n      contents: write\n",
             "    permissions:\n      contents: write\n      actions: write\n")
        edit(repo,
             "    uses: Aloecraft-org/technoproj"
             "/.github/workflows/release-publish.yml@v0.3.0",
             "    uses: Aloecraft-org/technoproj"
             "/.github/workflows/release-publish.yml@v0.3.0\n"
             "    with:\n      registry-workflow: publish.yml")


def test_a_registry_leg_left_waiting_for_a_tag_push_is_refused(repo):
    # The whole of issue #6: adopting the standard would switch publishing
    # off, and nothing would say so. It has to be a hard error.
    with_registry(repo, TAG_TRIGGERED, handoff=False)
    r = cli("release", "check-workflow", root=repo)
    assert r.returncode == 1
    assert "registry-workflow: publish.yml" in r.stderr
    assert "actions: write" in r.stderr
    assert "workflow_dispatch" in r.stderr


def test_a_registry_workflow_without_a_tag_input_is_refused(repo):
    # Everything wired except the input the tag travels in. aloeschema's
    # workflow_dispatch takes no inputs today, so this is its exact shape.
    no_input = DISPATCHABLE.replace(
        "    inputs:\n      tag: {type: string, required: true}\n", "")
    with_registry(repo, no_input)
    r = cli("release", "check-workflow", root=repo)
    assert r.returncode == 1
    assert "`tag` input" in r.stderr


def test_a_correctly_handed_off_registry_leg_conforms(repo):
    with_registry(repo, DISPATCHABLE)
    r = cli("release", "check-workflow", root=repo)
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_repo_with_no_registry_leg_needs_no_handoff(repo):
    # The permission is only demanded of repositories that actually publish
    # to a registry; everyone else keeps contents: write alone.
    r = cli("release", "check-workflow", root=repo)
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# dev builds: merging is the trigger
# ---------------------------------------------------------------------------

def enable_dev(repo):
    p = os.path.join(repo, ".technoproj")
    proj = json.loads(open(p).read())
    proj.setdefault("TECHNO_RELEASE", {})["dev_builds"] = True
    open(p, "w").write(json.dumps(proj, indent=2))


def git(repo, *args):
    return subprocess.run(("git", "-C", repo) + args,
                          capture_output=True, text=True)


@pytest.fixture
def git_repo(repo):
    """The fixture, as a real repository with tags to allocate against."""
    git(repo, "init", "-q", ".")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    git(repo, "commit", "-q", "--allow-empty", "-m", "x")
    return repo


def test_dev_tag_is_refused_where_it_is_not_declared(git_repo):
    r = cli("release", "dev-tag", root=git_repo)
    assert r.returncode == 1
    assert "not opted into dev builds" in r.stderr


def test_dev_tag_starts_at_one(git_repo):
    enable_dev(git_repo)
    r = cli("release", "dev-tag", root=git_repo)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "v0.2.0-dev.1"


def test_the_dev_number_is_global_and_sorts_numerically(git_repo):
    # The bug ALIGNMENT §1 exists to prevent: `dev.104` must not sort below
    # `dev.2`. And the number carries across versions -- it is allocated
    # from the tags that exist, not from this version's own.
    enable_dev(git_repo)
    for t in ("v0.1.0-dev.2", "v0.1.0-dev.9", "v0.1.0-dev.104"):
        git(git_repo, "tag", t)
    assert cli("release", "dev-tag", root=git_repo).stdout.strip() \
        == "v0.2.0-dev.105"


def test_if_changed_declines_to_cut_the_same_commit_twice(git_repo):
    enable_dev(git_repo)
    git(git_repo, "tag", "v0.2.0-dev.7")          # points at HEAD
    r = cli("release", "dev-tag", "--if-changed", root=git_repo)
    assert r.returncode == 3
    assert r.stdout.strip() == ""
    assert "already names HEAD" in r.stderr
    # ...but moving HEAD frees it again.
    git(git_repo, "commit", "-q", "--allow-empty", "-m", "y")
    r = cli("release", "dev-tag", "--if-changed", root=git_repo)
    assert r.returncode == 0
    assert r.stdout.strip() == "v0.2.0-dev.8"


def test_declared_dev_builds_with_nothing_to_trigger_them_is_refused(repo):
    # The issue #6 shape again: declared, never fires, nothing says so.
    enable_dev(repo)
    r = cli("release", "check-workflow", root=repo)
    assert r.returncode == 1
    assert "on.push.branches" in r.stderr


def test_declared_dev_builds_with_a_branch_trigger_conforms(repo):
    enable_dev(repo)
    edit(repo, '  push:\n    tags: ["v*"]\n',
         '  push:\n    branches: ["main"]\n    tags: ["v*"]\n')
    r = cli("release", "check-workflow", root=repo)
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# the permission trap
# ---------------------------------------------------------------------------

def test_id_token_without_contents_is_reported(repo):
    wf = os.path.join(repo, ".github", "workflows", "publish.yml")
    with open(wf, "w") as f:
        f.write("name: Publish\non: {push: {tags: ['v*']}}\n"
                "jobs:\n  publish:\n    runs-on: ubuntu-latest\n"
                "    permissions:\n      id-token: write\n"
                "    steps: [{run: \"true\"}]\n")
    r = cli("release", "doctor", "--offline", root=repo)
    assert "contents: none" in r.stdout
    assert "publish.yml" in r.stdout


def test_id_token_with_contents_is_not_reported(repo):
    wf = os.path.join(repo, ".github", "workflows", "publish.yml")
    with open(wf, "w") as f:
        f.write("name: Publish\non: {push: {tags: ['v*']}}\n"
                "jobs:\n  publish:\n    runs-on: ubuntu-latest\n"
                "    permissions:\n      id-token: write\n      contents: read\n"
                "    steps: [{run: \"true\"}]\n")
    r = cli("release", "doctor", "--offline", root=repo)
    assert "contents: none" not in r.stdout


# ---------------------------------------------------------------------------
# plan and cut
# ---------------------------------------------------------------------------

def test_plan_reports_the_contract(repo):
    r = cli("release", "plan", root=repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "v0.2.0" in r.stdout
    assert "prerelease: false" in r.stdout


def test_preflight_rehearses_by_default_and_is_strict_with_publish(repo):
    # CI runs this on every commit between one release and the next, when
    # the newest entry is legitimately still `unreleased`.
    import shutil
    src = open(os.path.join(repo, "CHANGELOG.yaml")).read()
    open(os.path.join(repo, "CHANGELOG.yaml"), "w").write(
        src.replace("status: released", "status: unreleased", 1)
           .replace('date: "2026-09-12"\n    status', "status", 1))
    rehearsal = cli("release", "preflight", "--tag", "v0.2.0", root=repo)
    strict = cli("release", "preflight", "--tag", "v0.2.0", "--publish",
                 root=repo)
    assert "rehearsal" in rehearsal.stdout
    assert strict.returncode == 1
    assert "still status: unreleased" in strict.stdout


def test_cut_sends_nothing_without_yes(repo):
    # A release is outward-facing; printing what it would do is the default.
    # `--ref` so the dry run needs no network at all.
    r = cli("release", "cut", "--tag", "v0.2.0", "--publish", "--ref", "main",
            root=repo)
    assert r.returncode == 0
    assert "Nothing sent" in r.stdout
    assert "Aloecraft-org/fixture" in r.stdout


def test_the_tree_names_the_repository_not_the_ambient_job(repo):
    # Under Actions, GITHUB_REPOSITORY names the job's own repository. It
    # must not win over the tree TECHNO_ROOT points at, or `doctor` and `cut`
    # silently report on -- and dispatch to -- a different repository than
    # the one they were given.
    e = env_for(repo)
    e["GITHUB_REPOSITORY"] = "Aloecraft-org/some-other-repo"
    r = subprocess.run([sys.executable, "-m", "technoproj.cli", "release",
                        "cut", "--tag", "v0.2.0", "--ref", "main"],
                       env=e, capture_output=True, text=True)
    assert "Aloecraft-org/fixture" in r.stdout, r.stdout + r.stderr
    assert "some-other-repo" not in r.stdout


def test_cut_refuses_a_tag_the_changelog_does_not_claim(repo):
    r = cli("release", "cut", "--tag", "v0.9.9", "--publish", "--yes",
            root=repo)
    assert r.returncode == 1
    assert "no entry in CHANGELOG.yaml" in r.stderr
