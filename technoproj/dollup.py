#!/usr/bin/env python3
"""Generate a dollup package from a library repository.

    technoproj dollup-manifest --out DIR [--allow-dirty] [--manifest-only]

Builds `DIR/packages/<name>/<version>/` -- the manifest, and the files it
names, hashed. The layout is dollup's (doc/RepoFormat.md §3), so the output
drops straight into a repo tree for `std-repo/publish.sh` to sign.

Why this exists: nine `*-lib` repositories each hold a `.dlua` and a README
and nothing else -- no version, no tags, no manifest. The version is invented
at publish time, and `files` is a set of sha256 hashes somebody types. Both
are the kind of thing that is right the first time and wrong by the third.

**The `source` block.** dollup manifests carry `name`, `version`, `requires`,
`files`, `guest`, `template` -- and nothing saying which commit produced the
package. A published package cannot be traced back to the tree it came from,
which is the provenance BUILDINFO.txt gives a binary release. This adds it:

    "source": {
      "repo":   "https://github.com/Aloecraft-org/token-bucket-lib",
      "commit": "3f9a1c7e2b884d05a1e6f0c9b7d4e2a8f1c33b90",
      "ref":    "v0.1.0"
    }

A dirty tree is refused rather than recorded quietly. A manifest naming a
commit whose files differ from what was hashed is worse than one with no
`source` at all, because it reads as provenance and is not. `--allow-dirty`
stamps `"dirty": true` and is for local experiments, not for publishing.

**Determinism.** The index hashes the manifest (`"manifest": "sha256:…"`), so
the same inputs must give the same bytes: fixed key order, sorted maps, one
trailing newline. Run it twice and diff -- the test does.

## Declaring a package

In the library's `.technoproj`:

    {
      "TECHNO_VERSION": {"major": 0, "minor": 1, "patch": 0, "pre": null},
      "TECHNO_DOLLUP": {
        "package": "token-bucket",
        "guest": {
          "modules": {"token_bucket": "token_bucket.dlua"},
          "source_only": true
        },
        "requires": {"dv_abi": 1}
      }
    }

`guest.main` is deliberately absent: its absence is what says this is a
library rather than something to run (RepoFormat §5). Give it a value only
for a package with an entry point.
"""
import hashlib
import json
import os
import shutil
import subprocess

from . import version as _version

# The order RepoFormat §5 presents them in. Not alphabetical on purpose: the
# format's own reading order is easier to check a manifest against by eye.
KEY_ORDER = ["name", "version", "source", "capability", "guest", "host",
             "assets", "template", "requires", "files"]


class DollupError(Exception):
    pass


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _git(root, *args):
    try:
        r = subprocess.run(["git", "-C", root, *args],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        raise DollupError("git failed: %s" % e)
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def source_block(root, allow_dirty):
    """Where this package came from. Refuses a dirty tree unless told."""
    commit = _git(root, "rev-parse", "HEAD")
    if not commit:
        raise DollupError(
            "%s is not a git checkout, so the package has no provenance to "
            "record. Publish from a clone, or pass --allow-dirty to build "
            "one marked as having none." % root)

    status = _git(root, "status", "--porcelain")
    dirty = bool(status)
    if dirty and not allow_dirty:
        raise DollupError(
            "the working tree has uncommitted changes, so `commit` would "
            "name a tree these files did not come from. Commit them, or pass "
            "--allow-dirty to record the package as dirty.\n" +
            "\n".join("  " + l for l in status.splitlines()[:10]))

    block = {"commit": commit}

    url = _git(root, "remote", "get-url", "origin")
    if url:
        # A published manifest should carry a URL a person can open, not a
        # credential. ssh remotes and embedded tokens both get normalised.
        if url.startswith("git@") and ":" in url:
            host, path = url[4:].split(":", 1)
            url = "https://%s/%s" % (host, path)
        if url.endswith(".git"):
            url = url[:-4]
        if "@" in url.split("//", 1)[-1].split("/", 1)[0]:
            url = url.split("//", 1)[0] + "//" + \
                  url.split("//", 1)[1].split("@", 1)[1]
        block["repo"] = url

    # The tag if HEAD carries one, otherwise the branch. A tag is the useful
    # answer; a branch at least says where to look.
    ref = _git(root, "describe", "--tags", "--exact-match") \
        or _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if ref and ref != "HEAD":
        block["ref"] = ref
    if dirty:
        block["dirty"] = True
    return block


def _declared_files(decl):
    """Every repo-relative path the declaration names, with the path it takes
    inside the package. Guest modules land under guest/ the way std-repo's
    own packages do."""
    out = {}
    guest = decl.get("guest") or {}
    for name, src in sorted((guest.get("modules") or {}).items()):
        out[src] = "guest/" + os.path.basename(src)
    for name, src in sorted((decl.get("assets") or {}).items()):
        out[src] = "assets/" + os.path.basename(src)
    for src in sorted(decl.get("include") or []):
        out[src] = src
    if not out:
        raise DollupError(
            "TECHNO_DOLLUP names no files. A package with no files is not a "
            "package -- declare guest.modules, assets, or include.")
    return out


def build(root, proj, allow_dirty=False):
    """-> (manifest dict, {src path: path inside the package})."""
    decl = proj.get("TECHNO_DOLLUP")
    if not isinstance(decl, dict):
        raise DollupError(
            ".technoproj has no TECHNO_DOLLUP object. See `technoproj "
            "dollup-manifest --help` for the shape.")
    name = decl.get("package")
    if not name:
        raise DollupError("TECHNO_DOLLUP.package is required")

    ver = _version.of(proj)["body"]
    files = _declared_files(decl)

    missing = [s for s in files if not os.path.isfile(os.path.join(root, s))]
    if missing:
        raise DollupError("declared but not in the tree: " + ", ".join(sorted(missing)))

    m = {"name": name, "version": ver, "source": source_block(root, allow_dirty)}

    guest = decl.get("guest")
    if guest:
        g = {}
        if guest.get("main"):
            g["main"] = guest["main"]
        g["modules"] = {n: "guest/" + os.path.basename(p)
                        for n, p in sorted((guest.get("modules") or {}).items())}
        if guest.get("source_only") is not None:
            g["source_only"] = bool(guest["source_only"])
        m["guest"] = g

    for key in ("capability", "host", "assets", "template"):
        if decl.get(key) is not None:
            m[key] = decl[key]
    if decl.get("assets"):
        m["assets"] = {n: "assets/" + os.path.basename(p)
                       for n, p in sorted(decl["assets"].items())}

    if decl.get("requires"):
        m["requires"] = decl["requires"]

    m["files"] = {dest: sha256_file(os.path.join(root, src))
                  for src, dest in sorted(files.items(), key=lambda kv: kv[1])}

    return {k: m[k] for k in KEY_ORDER if k in m}, files


def render(manifest):
    """Deterministic bytes. The index hashes this."""
    return json.dumps(manifest, indent=2, sort_keys=False) + "\n"


def write(root, proj, out, allow_dirty=False, manifest_only=False):
    manifest, files = build(root, proj, allow_dirty)
    pkg = os.path.join(out, "packages", manifest["name"], manifest["version"])
    if not manifest_only:
        # Clear first: a file left from a previous build is a file the
        # publisher would sign.
        if os.path.isdir(pkg):
            shutil.rmtree(pkg)
        for src, dest in sorted(files.items(), key=lambda kv: kv[1]):
            d = os.path.join(pkg, dest)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copyfile(os.path.join(root, src), d)
    os.makedirs(pkg, exist_ok=True)
    path = os.path.join(pkg, "manifest.json")
    with open(path, "w") as f:
        f.write(render(manifest))
    return path, manifest, files
