"""dollup package generation, including the provenance the format lacked."""
import hashlib, json, os, subprocess, sys, pytest
from technoproj import dollup

DECL = {
    "TECHNO_VERSION": {"major": 0, "minor": 1, "patch": 0, "pre": None},
    "TECHNO_DOLLUP": {
        "package": "token-bucket",
        "guest": {"modules": {"token_bucket": "token_bucket.dlua"},
                  "source_only": True},
        "requires": {"dv_abi": 1},
    },
}

def git(d, *a):
    subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True)

@pytest.fixture
def lib(tmp_path):
    (tmp_path / "token_bucket.dlua").write_text("-- token bucket\nreturn {}\n")
    (tmp_path / ".technoproj").write_text(json.dumps(DECL))
    git(tmp_path, "init", "-q"); git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    git(tmp_path, "remote", "add", "origin",
        "git@github.com:Aloecraft-org/token-bucket-lib.git")
    git(tmp_path, "add", "-A"); git(tmp_path, "commit", "-q", "-m", "x")
    return tmp_path

def test_refuses_a_dirty_tree(lib):
    (lib / "token_bucket.dlua").write_text("-- changed\n")
    with pytest.raises(dollup.DollupError) as e:
        dollup.build(str(lib), DECL)
    assert "uncommitted" in str(e.value)

def test_allow_dirty_records_it_rather_than_hiding_it(lib):
    (lib / "token_bucket.dlua").write_text("-- changed\n")
    m, _ = dollup.build(str(lib), DECL, allow_dirty=True)
    assert m["source"]["dirty"] is True

def test_source_block_carries_provenance(lib):
    m, _ = dollup.build(str(lib), DECL)
    src = m["source"]
    assert len(src["commit"]) == 40
    # ssh remotes become a URL a person can open
    assert src["repo"] == "https://github.com/Aloecraft-org/token-bucket-lib"
    assert src["ref"] in ("main", "master")

def test_tag_is_preferred_over_branch_as_ref(lib):
    git(lib, "tag", "v0.1.0")
    m, _ = dollup.build(str(lib), DECL)
    assert m["source"]["ref"] == "v0.1.0"

def test_hashes_are_of_the_real_bytes(lib):
    m, _ = dollup.build(str(lib), DECL)
    want = hashlib.sha256((lib / "token_bucket.dlua").read_bytes()).hexdigest()
    assert m["files"]["guest/token_bucket.dlua"] == "sha256:" + want

def test_library_has_no_main(lib):
    """guest.main's ABSENCE is what says 'library' (RepoFormat 5)."""
    m, _ = dollup.build(str(lib), DECL)
    assert "main" not in m["guest"]

def test_deterministic_bytes(lib):
    """The index hashes the manifest, so the same inputs must give the same
    bytes or the index churns on every rebuild."""
    a, _ = dollup.build(str(lib), DECL)
    b, _ = dollup.build(str(lib), DECL)
    assert dollup.render(a) == dollup.render(b)
    assert dollup.render(a).endswith("}\n")

def test_key_order_follows_the_format(lib):
    m, _ = dollup.build(str(lib), DECL)
    order = [k for k in dollup.KEY_ORDER if k in m]
    assert list(m) == order

def test_declared_but_missing_file_is_refused(lib):
    (lib / "token_bucket.dlua").unlink()
    git(lib, "add", "-A"); git(lib, "commit", "-q", "-m", "drop")
    with pytest.raises(dollup.DollupError) as e:
        dollup.build(str(lib), DECL)
    assert "not in the tree" in str(e.value)

def test_writes_the_package_tree(lib, tmp_path):
    out = tmp_path / "repo"
    path, m, files = dollup.write(str(lib), DECL, str(out))
    assert os.path.isfile(path)
    assert os.path.isfile(out / "packages/token-bucket/0.1.0/guest/token_bucket.dlua")
    assert json.load(open(path))["version"] == "0.1.0"
