"""The version scheme, and the two implementations of it agreeing."""
import json, os, shutil, subprocess, sys, pytest
from technoproj import version as V

CASES = [
    ({"major":1,"minor":4,"patch":0,"pre":None},
     {"tag":"v1.4.0","body":"1.4.0","base":"1.4.0","semver":"1.4.0","pep440":"1.4.0"}),
    ({"major":1,"minor":4,"patch":0,"pre":{"kind":"rc","n":1}},
     {"tag":"v1.4.0-rc.1","body":"1.4.0-rc.1","base":"1.4.0",
      "semver":"1.4.0-rc.1","pep440":"1.4.0rc1"}),
    ({"major":0,"minor":15,"patch":0,"pre":{"kind":"dev","n":105}},
     {"tag":"v0.15.0-dev.105","body":"0.15.0-dev.105","base":"0.15.0",
      "semver":"0.15.0-dev.105","pep440":"0.15.0.dev105"}),
    ({"major":0,"minor":4,"patch":0,"pre":{"kind":"beta","n":2}},
     {"tag":"v0.4.0-beta.2","body":"0.4.0-beta.2","base":"0.4.0",
      "semver":"0.4.0-beta.2","pep440":"0.4.0b2"}),
]

@pytest.mark.parametrize("v,want", CASES)
def test_spellings(v, want):
    assert V.of({"TECHNO_VERSION": v}) == want

@pytest.mark.parametrize("v,want", CASES)
def test_body_round_trips(v, want):
    assert V.body(V.parse(want["body"])) == want["body"]

def test_pep440_spelling_is_not_canonical():
    """`1.4.0rc1` must not parse as a tag body, or the two spellings become
    interchangeable and the scheme stops meaning anything."""
    with pytest.raises(V.VersionError):
        V.parse("1.4.0rc1")
    with pytest.raises(V.VersionError):
        V.parse("1.4.0-rc1")      # missing the dot: sorts wrong in SemVer

def test_b_is_never_a_build_number():
    """PEP 440 reads b as beta, so a -b<n> build suffix is a collision."""
    assert V.pep440(V.parse("0.0.1-beta.104")) == "0.0.1b104"

@pytest.mark.parametrize("spelling,want", [
    ("base", "1.4.0"), ("semver", "1.4.0-rc.1"), ("pep440", "1.4.0rc1")])
def test_respell(spelling, want):
    assert V.respell("1.4.0-rc.1", spelling) == want

@pytest.mark.skipif(not shutil.which("make") or not shutil.which("jq"),
                    reason="needs make and jq")
@pytest.mark.parametrize("v,want", CASES)
def test_version_mk_agrees_with_version_py(tmp_path, v, want):
    """version.py's docstring claims the two must agree. Check it."""
    (tmp_path / ".technoproj").write_text(json.dumps({"TECHNO_VERSION": v}))
    subprocess.run([sys.executable, "-m", "technoproj.cli", "sync"],
                   env=dict(os.environ, TECHNO_ROOT=str(tmp_path)), check=True,
                   capture_output=True)
    (tmp_path / "Makefile").write_text(
        "ROOT_DIR:=%s\n__TECHNO_PROJECT_FILE:=${ROOT_DIR}/.technoproj\n"
        "-include ${ROOT_DIR}/script/version.mk\n" % tmp_path)
    out = subprocess.run(["make", "-s", "-C", str(tmp_path), "version"],
                         capture_output=True, text=True, check=True).stdout
    got = dict(l.split(":", 1) for l in out.strip().splitlines())
    got = {k.strip(): val.strip() for k, val in got.items()}
    assert got["tag"] == want["tag"]
    assert got["pep440"] == want["pep440"]
    assert got["semver"] == want["semver"]
