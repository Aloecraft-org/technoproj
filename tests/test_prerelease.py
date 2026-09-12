"""Issue #1: a prerelease could not satisfy validate() and consistency() at
once. validate() wanted the tag body, consistency() wanted PEP 440. Plain
releases hid it, because X.Y.Z is the same in every spelling.

The fixture is the real shape of a repository mid-rc: `latest` stays on the
previous stable release, because `latest` is what the mirror's `latest/`
symlink resolves to and a candidate is not it."""
import json, os, subprocess, sys, pytest

FIX = {
    ".technoproj": json.dumps({
        "TECHNO_VERSION": {"major": 1, "minor": 4, "patch": 0,
                           "pre": {"kind": "rc", "n": 1}},
        "TECHNO_CHANGELOG": {
            "project": "Fixture", "tag_rule": "exact", "emit_json": False,
            "stamps": [{"file": "pyproject.toml",
                        "find": r'^version\s*=\s*"([^"]+)"',
                        "spelling": "pep440"}],
        }}),
    "CHANGELOG.yaml": (
        "schema: 1\nrepo: Aloecraft-org/fixture\nreleases:\n"
        '  - version: "1.4.0-rc.1"\n    tag: v1.4.0-rc.1\n'
        '    date: "2026-09-12"\n    status: released\n'
        "    stable: false\n    mirror: false\n"
        "    summary: |\n      A release candidate.\n"
        '  - version: "1.3.0"\n    tag: v1.3.0\n    date: "2026-09-01"\n'
        "    status: released\n    stable: true\n    latest: true\n"
        "    mirror: true\n"
        "    summary: |\n      The release before it.\n"),
    # The PEP 440 spelling, which is what pyproject holds.
    "pyproject.toml": '[project]\nversion = "1.4.0rc1"\n',
}

@pytest.fixture
def repo(tmp_path):
    for name, text in FIX.items():
        (tmp_path / name).write_text(text)
    return tmp_path

def run(root, *args):
    return subprocess.run([sys.executable, "-m", "technoproj.changelog", *args],
                          env=dict(os.environ, TECHNO_ROOT=str(root)),
                          capture_output=True, text=True)

def test_validate_accepts_the_tag_body(repo):
    r = run(repo, "validate")
    assert r.returncode == 0, r.stderr

def test_consistency_accepts_the_same_entry(repo):
    """This is the bug: it demanded 1.4.0rc1 while validate demanded
    1.4.0-rc.1, so no prerelease could pass both."""
    r = run(repo, "consistency")
    assert r.returncode == 0, r.stderr

def test_a_pep440_stamp_wants_the_pep440_spelling(repo):
    """pyproject holds 1.4.0rc1 while the entry holds 1.4.0-rc.1 -- the
    stamp has to convert, which it previously could not do in this
    direction."""
    (repo / "pyproject.toml").write_text('[project]\nversion = "1.4.0-rc.1"\n')
    r = run(repo, "consistency")
    assert r.returncode == 1
    assert "1.4.0rc1" in r.stderr

def test_a_bad_version_no_longer_silences_the_stamps(repo):
    """It used to return early, so one problem hid every other check."""
    p = repo / "CHANGELOG.yaml"
    p.write_text(p.read_text().replace('"1.4.0-rc.1"', '"1.4.0rc1"', 1)
                              .replace("v1.4.0-rc.1", "v1.4.0rc1", 1))
    r = run(repo, "consistency")
    assert r.returncode == 1
    assert "is not a version" in r.stderr
