#!/usr/bin/env python3
"""The version scheme, in Python.

`version.mk` derives these for make; this is the same rules for everything
that is not a Makefile. The two must agree, and `tests/test_version.py`
checks them against each other rather than trusting that they do.

    v<major>.<minor>.<patch>[-<kind>.<n>]     kind in dev|alpha|beta|rc

The tag is canonical. The tag body -- the tag without its leading `v` -- is
what `CHANGELOG.yaml`, `Cargo.toml` and a dollup manifest all carry. PEP 440
is a derived spelling that exists only in `pyproject.toml` and on PyPI.

Two rules that look cosmetic and are not, both in doc/ALIGNMENT.md §1:

  * The dot in `-dev.7` is load-bearing. SemVer compares dot-separated
    identifiers, numeric ones numerically -- without it `b104` sorts before
    `b2` and the bug first appears at build 10.
  * `-b<n>` is never a build number. PEP 440 reads `b` as beta, so
    `0.0.1-b104` and `0.0.1-beta104` are the same version.
"""
import re

KINDS = ("dev", "alpha", "beta", "rc")
# PEP 440's spelling of each kind. `dev` is the one that sorts below every
# other prerelease, which is why a throwaway build belongs there.
PEP = {"dev": ".dev", "alpha": "a", "beta": "b", "rc": "rc"}


class VersionError(ValueError):
    pass


# The canonical form, for reading a tag body back into its parts. Anchored
# and exhaustive on purpose: `1.4.0rc1` must NOT parse, or the two spellings
# quietly become interchangeable and the scheme stops meaning anything.
BODY_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-(dev|alpha|beta|rc)\.(\d+))?$")


def parse(text):
    """A tag body -> a TECHNO_VERSION dict. The inverse of body()."""
    m = BODY_RE.match(str(text or ""))
    if not m:
        raise VersionError(
            "%r is not a version: expected X.Y.Z or X.Y.Z-<kind>.<n> with "
            "kind in %s (note the hyphen and the dot -- `1.4.0rc1` is the "
            "PEP 440 spelling, which is derived, not canonical)"
            % (text, "/".join(KINDS)))
    maj, mnr, pat, kind, n = m.groups()
    v = {"major": int(maj), "minor": int(mnr), "patch": int(pat), "pre": None}
    if kind:
        v["pre"] = {"kind": kind, "n": int(n)}
    return v


def respell(text, spelling):
    """A tag body in another spelling. `base` is X.Y.Z with the prerelease
    dropped -- which is what a Cargo workspace keeps during an rc, since the
    tag is the release's identity and the manifest version is the code's."""
    v = parse(text)
    if spelling == "pep440":
        return pep440(v)
    if spelling == "semver":
        return body(v)
    return base(v)


def _pre(v):
    pre = v.get("pre")
    if pre in (None, {}, ""):
        return None, None
    if not isinstance(pre, dict):
        raise VersionError("TECHNO_VERSION.pre must be null or "
                           "{kind, n}, not %r" % (pre,))
    kind, n = pre.get("kind"), pre.get("n")
    if kind not in KINDS:
        raise VersionError("TECHNO_VERSION.pre.kind is %r; expected one of %s"
                           % (kind, ", ".join(KINDS)))
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        raise VersionError("TECHNO_VERSION.pre.n must be a non-negative "
                           "integer, not %r" % (n,))
    return kind, n


def base(v):
    """X.Y.Z, with no prerelease."""
    try:
        parts = [v["major"], v["minor"], v["patch"]]
    except (KeyError, TypeError):
        raise VersionError("TECHNO_VERSION needs major, minor and patch")
    for p in parts:
        if not isinstance(p, int) or isinstance(p, bool) or p < 0:
            raise VersionError("TECHNO_VERSION major/minor/patch must be "
                               "non-negative integers, got %r" % (parts,))
    return "%d.%d.%d" % tuple(parts)


def body(v):
    """The tag without its `v`. What the manifest and Cargo.toml carry."""
    kind, n = _pre(v)
    if kind is None:
        return base(v)
    return "%s-%s.%d" % (base(v), kind, n)


def tag(v):
    return "v" + body(v)


def semver(v):
    """Identical to the tag body. Named so the caller says what it means."""
    return body(v)


def pep440(v):
    kind, n = _pre(v)
    if kind is None:
        return base(v)
    return "%s%s%d" % (base(v), PEP[kind], n)


def of(proj):
    """Everything, from a parsed .technoproj."""
    v = proj.get("TECHNO_VERSION")
    if not isinstance(v, dict):
        raise VersionError(".technoproj has no TECHNO_VERSION object")
    return {"base": base(v), "body": body(v), "tag": tag(v),
            "semver": semver(v), "pep440": pep440(v)}
