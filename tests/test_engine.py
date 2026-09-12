"""The engine's own tests. The real proof is reproducing three repositories'
committed changelogs byte-for-byte; this is what CI can run alone."""
import json, os, pathlib, subprocess, sys, tempfile, shutil

FIXTURE = pathlib.Path(__file__).parent / "fixture"


def run(*args, root=FIXTURE):
    return subprocess.run([sys.executable, "-m", "technoproj.changelog", *args],
                          env=dict(os.environ, TECHNO_ROOT=str(root)),
                          capture_output=True, text=True)


def test_validate():
    r = run("validate")
    assert r.returncode == 0, r.stderr
    assert "2 releases" in r.stdout and "latest=v0.2.0" in r.stdout


def test_declared_fact_renders():
    md = run("render", "md").stdout
    assert "widget ABI 3" in md
    assert "widget ABI 2" in md


def test_multiline_bullet_stays_in_its_item():
    md = run("render", "md").stdout
    assert "- A thing with a second line,\n  which must stay inside its bullet." in md


def test_json_carries_rendered_notes_and_mirror_tags():
    d = json.loads(run("render", "json").stdout)
    assert d["latest"] == "v0.2.0"
    assert d["mirror_tags"] == ["v0.2.0", "v0.1.0"]
    assert d["releases"][0]["notes_md"].startswith("## [0.2.0]")
    assert d["releases"][0]["widget_abi"] == 3


def test_unknown_key_is_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copytree(FIXTURE, tmp, dirs_exist_ok=True)
        p = pathlib.Path(tmp) / "CHANGELOG.yaml"
        p.write_text(p.read_text().replace("widget_abi: 3", "widget_abi: 3\n    nonsense: 1"))
        r = run("validate", root=tmp)
        assert r.returncode == 1
        assert "unknown key 'nonsense'" in r.stderr


def test_release_check_reports_prerelease_flag():
    r = run("release-check", "--tag", "v0.2.0")
    assert r.returncode == 0, r.stderr
    assert "prerelease=false" in r.stdout
    assert "version=0.2.0" in r.stdout


def test_version_mk_sync_and_check(tmp_path):
    env = dict(os.environ, TECHNO_ROOT=str(tmp_path))
    def cli(*a):
        return subprocess.run([sys.executable, "-m", "technoproj.cli", *a],
                              env=env, capture_output=True, text=True)
    assert cli("check").returncode == 1              # missing
    assert cli("sync").returncode == 0
    assert (tmp_path / "script" / "version.mk").is_file()
    assert cli("check").returncode == 0              # placed
    (tmp_path / "script" / "version.mk").write_text("drifted\n")
    assert cli("check").returncode == 1              # drifted
