"""The guidance document's examples are run, not trusted.

`doc/STANDARD.md` is what a project is pointed at, so an example in it that
does not validate is worse than no example: it is followed. Every fenced
block this file extracts is the real one from the document, assembled into a
repository and put through the same commands CI runs.

This is the same bargain as `technoproj check` -- the copy is checked rather
than trusted, because the failure being prevented is documentation drifting
away from the tool it documents.
"""
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

DOC = pathlib.Path(__file__).parent.parent / "doc" / "STANDARD.md"


def block(lang, contains):
    """The fenced block of `lang` containing `contains`, from the doc."""
    text = DOC.read_text()
    for m in re.finditer(r"```%s\n(.*?)```" % lang, text, re.S):
        if contains in m.group(1):
            return m.group(1)
    raise AssertionError("doc/STANDARD.md has no %s block containing %r"
                         % (lang, contains))


@pytest.fixture(scope="module")
def documented_repo(tmp_path_factory):
    """A repository built from the document's own examples."""
    tmp = tmp_path_factory.mktemp("documented")
    (tmp / "CHANGELOG.yaml").write_text(block("yaml", "schema: 1"))

    # The declaration in the doc is a fragment of .technoproj, shown without
    # the enclosing object so it can be pasted beside the other blocks.
    decl = block("json", '"TECHNO_CHANGELOG"').strip().rstrip(",")
    proj = json.loads("{%s}" % decl)
    proj["TECHNO_VERSION"] = {"major": 0, "minor": 4, "patch": 0, "pre": None}
    proj["TECHNO_RELEASE"] = {"name": "Example {tag}"}
    (tmp / ".technoproj").write_text(json.dumps(proj, indent=2))

    # The `stamps` example names pyproject.toml, so there has to be one for
    # `consistency` to check -- which is the point of testing the example.
    (tmp / "pyproject.toml").write_text('version = "0.4.0"\n')

    wf = tmp / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "release.yml").write_text(block("yaml", "name: Release"))
    return str(tmp)


def run(mod, *args, root):
    return subprocess.run([sys.executable, "-m", mod, *args],
                          env=dict(os.environ, TECHNO_ROOT=root),
                          capture_output=True, text=True)


@pytest.mark.parametrize("command", ["validate", "consistency", "generate"])
def test_the_documented_changelog_passes(documented_repo, command):
    r = run("technoproj.changelog", command, root=documented_repo)
    assert r.returncode == 0, r.stderr + r.stdout


def test_the_documented_stamp_catches_a_disagreeing_version(documented_repo):
    # The doc claims `stamps` checks rather than writes. Prove it fails when
    # the file disagrees, or the claim is decoration.
    p = os.path.join(documented_repo, "pyproject.toml")
    keep = open(p).read()
    try:
        open(p, "w").write('version = "0.3.0"\n')
        r = run("technoproj.changelog", "consistency", root=documented_repo)
        assert r.returncode == 1
        assert "pyproject.toml carries version" in r.stderr
    finally:
        open(p, "w").write(keep)


def test_the_documented_caller_conforms(documented_repo):
    r = run("technoproj.cli", "release", "check-workflow", root=documented_repo)
    assert r.returncode == 0, r.stderr + r.stdout


def test_the_documented_caller_builds_from_preflights_sha(documented_repo):
    # The doc calls this out as load-bearing: a build job checking out
    # anything else can ship assets from a different tree than the notes.
    caller = block("yaml", "name: Release")
    assert "needs.preflight.outputs.sha" in caller


def test_the_pinned_version_matches_this_package(documented_repo):
    # Every `@vX.Y.Z` the doc tells a project to pin must be the version
    # being released here, or the guidance points at the previous one.
    import technoproj.version as _v
    proj = json.loads((DOC.parent.parent / ".technoproj").read_text())
    want = "v" + _v.of(proj)["body"]
    pins = set(re.findall(r"technoproj/\.github/workflows/\S+?@(v[\d.]+)",
                          DOC.read_text()))
    assert pins, "the doc shows no pinned shared workflow"
    assert pins == {want}, "doc pins %s; this package is %s" % (sorted(pins), want)
