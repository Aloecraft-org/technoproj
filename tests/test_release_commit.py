"""A release commit is not a dev build.

The merge of a release-prep pull request lands on the default branch before
its release tag exists. diluvium's push-triggered dev build tagged that
commit as v0.17.4-dev.18 while the Release run was building v0.17.4 from it
(da9bbdf). `script/release-commit.sh` (placed by `technoproj sync`, reading
changelog.json) and `technoproj release release-commit` (reading
CHANGELOG.yaml) are one rule; every case here runs through both.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

SCRIPT = pathlib.Path(__file__).parent.parent / "technoproj" / "data" / "release-commit.sh"
AMBIENT = ("GITHUB_REPOSITORY", "GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_URL",
           "GITHUB_REF", "GITHUB_SHA", "GITHUB_ACTIONS")


def env_for(root):
    e = {k: v for k, v in os.environ.items() if k not in AMBIENT}
    e["TECHNO_ROOT"] = str(root)
    return e


def git(d, *a):
    r = subprocess.run(("git", "-C", str(d)) + a, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def commit(d, status, tag="v0.3.0", msg="x"):
    """Commit a changelog whose newest entry is `tag` at `status`, in both
    the spellings the two implementations read."""
    rel = {"version": tag[1:], "tag": tag, "status": status}
    older = {"version": "0.2.0", "tag": "v0.2.0", "status": "released"}
    (d / "changelog.json").write_text(json.dumps({"releases": [rel, older]}))
    (d / "CHANGELOG.yaml").write_text(
        "schema: 1\nreleases:\n"
        "  - {version: \"%s\", tag: %s, status: %s}\n"
        "  - {version: \"0.2.0\", tag: v0.2.0, status: released}\n"
        % (tag[1:], tag, status))
    git(d, "add", "-A")
    git(d, "commit", "-q", "--allow-empty", "-m", msg)
    return git(d, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main", ".")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / ".technoproj").write_text(json.dumps({
        "TECHNO_VERSION": {"major": 0, "minor": 3, "patch": 0, "pre": None},
        "TECHNO_RELEASE": {"dev_builds": True}}))
    return tmp_path


def both(d, *commit_):
    """-> the exit code both implementations agree on."""
    sh = subprocess.run(["sh", str(SCRIPT), *commit_], cwd=str(d),
                        capture_output=True, text=True)
    py = subprocess.run([sys.executable, "-m", "technoproj.cli", "release",
                         "release-commit", *commit_],
                        env=env_for(d), capture_output=True, text=True)
    assert sh.returncode == py.returncode, (sh.stderr, py.stderr)
    return sh.returncode


needs_jq = pytest.mark.skipif(shutil.which("jq") is None, reason="needs jq")


@needs_jq
def test_an_unreleased_newest_entry_is_not_a_release_commit(repo):
    commit(repo, "unreleased")
    assert both(repo) == 3


@needs_jq
def test_the_commit_an_entry_became_released_is_one_before_its_tag_exists(repo):
    commit(repo, "unreleased")
    prep = commit(repo, "released", msg="release prep")
    assert both(repo) == 0
    # ...and the next commit on main, with the tag still not cut, is not:
    # the release was already decided before it.
    commit(repo, "released", msg="after")
    assert both(repo) == 3
    assert both(repo, prep) == 0


@needs_jq
def test_once_tagged_only_the_tagged_commit_is_a_release_commit(repo):
    commit(repo, "unreleased")
    prep = commit(repo, "released", msg="release prep")
    later = commit(repo, "released", msg="after")
    git(repo, "tag", "v0.3.0", later)          # tagged somewhere else
    assert both(repo, prep) == 3
    assert both(repo, later) == 0


@needs_jq
def test_a_merge_is_judged_against_its_first_parent(repo):
    commit(repo, "unreleased")
    git(repo, "checkout", "-q", "-b", "prep")
    commit(repo, "released", msg="release prep")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", "merge prep", "prep")
    assert both(repo) == 0


@needs_jq
def test_a_commit_with_no_changelog_is_not_a_release_commit(repo):
    git(repo, "commit", "-q", "--allow-empty", "-m", "empty")
    assert both(repo) == 3


def test_dev_tag_if_changed_declines_a_release_commit(repo):
    commit(repo, "unreleased")
    r = subprocess.run([sys.executable, "-m", "technoproj.cli", "release",
                        "dev-tag", "--if-changed"],
                       env=env_for(repo), capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "v0.3.0-dev.1", r.stderr
    commit(repo, "released", msg="release prep")
    r = subprocess.run([sys.executable, "-m", "technoproj.cli", "release",
                        "dev-tag", "--if-changed"],
                       env=env_for(repo), capture_output=True, text=True)
    assert r.returncode == 3 and r.stdout.strip() == ""
    assert "not cutting a dev build" in r.stderr
    # Without --if-changed it is still the caller's call -- a dispatch cuts.
    r = subprocess.run([sys.executable, "-m", "technoproj.cli", "release",
                        "dev-tag"],
                       env=env_for(repo), capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "v0.3.0-dev.1"
