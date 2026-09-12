#!/usr/bin/env python3
"""Changelog tool, shared across Aloecraft repositories.

CHANGELOG.yaml is the source of truth for release notes. This renders it
and checks it, so that the release page, the release mirror and the copy of
CHANGELOG.md in the tree are all derived from one file rather than
maintained in parallel.

One engine, one copy. What differs between repositories is declared, not
forked: the `TECHNO_CHANGELOG` block in `.technoproj` says which
compatibility facts this project records, how its tags are spelled, and
where its version is stamped. Anything genuinely bespoke -- diluvium's
LUAC_FORMAT, DRT's Cargo.lock pin -- lives in the repository's own
`script/checks.py`, which this calls if it exists.

Usage:
  technoproj-changelog validate              schema and consistency checks
  technoproj-changelog render md             whole changelog, as Markdown
  technoproj-changelog render md --tag TAG   one release's section only
                                     (what a release body wants)
  technoproj-changelog render json           machine-readable form
  technoproj-changelog mirror-tags           tags the mirror should carry,
                                     newest first
  technoproj-changelog latest                the tag `latest/` resolves to
  technoproj-changelog generate              write CHANGELOG.md and changelog.json
  technoproj-changelog check                 fail unless the generated files match
                                     the YAML; for CI
  technoproj-changelog consistency           fail unless the tree agrees with the
                                     newest entry; for CI
  technoproj-changelog release-check --tag TAG [--publish]
                                     fail unless TAG is releasable; prints
                                     prerelease= and version= for
                                     GITHUB_OUTPUT

Why the generated files are committed: the release mirror runs on a host
with a stdlib-only Python and no build step, so it reads changelog.json
directly. `check` is what stops that copy going stale.

Requires PyYAML (pip install pyyaml).
"""
import argparse
import json
import os
import re
import sys

from . import version as _version

try:
    import yaml
except ImportError:
    sys.exit("changelog.py: PyYAML is required (pip install pyyaml)")

# The repository root is the tree being operated on, not wherever this file
# happens to live -- it is shared, so it may be vendored, submoduled or
# pip-installed, and none of those put it two directories under the root.
ROOT = os.environ.get("TECHNO_ROOT") or os.getcwd()

# keepachangelog's six, in the order it prints them, plus our one.
SECTIONS = [
    ("added", "Added"),
    ("changed", "Changed"),
    ("deprecated", "Deprecated"),
    ("removed", "Removed"),
    ("fixed", "Fixed"),
    ("security", "Security"),
    ("known_issues", "Known issues"),
]
STATUSES = {"released", "unreleased", "tagged"}
# Every repository's entries carry these; `facts` in the config adds the
# ones that are this project's own.
CORE_SCALARS = {"version", "tag", "date", "status", "stable", "latest",
                "mirror", "summary", "upgrading"}

KAC = "The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).\n"


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------

DEFAULTS = {
    "project": None,          # display name in the generated preamble
    "intro_extra": "",        # text appended after the Keep a Changelog line
    "facts": [],              # [{keys:[...], fmt:"..."}] -- first match wins per slot
    "mappings": [],           # [{key, title}] profile -> list blocks
    "tag_rule": "exact",      # exact | prefix | derive
    "required": ["version", "tag", "status", "stable", "mirror", "summary"],
    "latest_requires": ["stable", "mirror"],
    "candidates": False,      # release candidates listed under a release
    "planned": False,         # a top-level `planned` section
    "emit_json": True,
    "stamps": [],             # [{file, find, spelling, all?}]
}


def config():
    path = os.path.join(ROOT, ".technoproj")
    try:
        with open(path) as f:
            proj = json.load(f)
    except OSError as e:
        sys.exit("changelog.py: cannot read .technoproj (%s)" % e)
    except ValueError as e:
        sys.exit("changelog.py: .technoproj is not valid JSON (%s)" % e)
    cfg = dict(DEFAULTS)
    cfg.update(proj.get("TECHNO_CHANGELOG") or {})
    if not cfg["project"]:
        sys.exit("changelog.py: .technoproj TECHNO_CHANGELOG.project is required")
    return cfg


CFG = None          # set in main(); module-level so the renderers can read it


def scalars():
    keys = set(CORE_SCALARS)
    for f in CFG["facts"]:
        keys.update(f["keys"])
    return keys


def mapping_keys():
    return {m["key"] for m in CFG["mappings"]}


def known():
    extra = {"candidates"} if CFG["candidates"] else set()
    return scalars() | mapping_keys() | extra | {k for k, _ in SECTIONS}


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------

def source():
    return os.path.join(ROOT, "CHANGELOG.yaml")


def load():
    """A missing CHANGELOG.yaml is the first thing an adopting repository
    hits, so it gets a sentence rather than a traceback."""
    try:
        with open(source()) as f:
            return yaml.safe_load(f)
    except OSError as e:
        sys.exit("changelog.py: cannot read %s (%s)\n"
                 "  Every command here reads CHANGELOG.yaml; create one, or "
                 "run from the repository root." % (source(), e))
    except yaml.YAMLError as e:
        sys.exit("changelog.py: %s is not valid YAML\n  %s" % (source(), e))


def read(path):
    with open(os.path.join(ROOT, path)) as f:
        return f.read()


def tag_of(r):
    if CFG["tag_rule"] == "derive":
        return r.get("tag") or "v%s" % r["version"]
    return r.get("tag")


def candidates_of(r):
    return (r.get("candidates") or []) if CFG["candidates"] else []


def find_tag(doc, tag):
    """-> (release, candidate or None) for a release tag or a candidate tag
    listed under a release; (None, None) when nothing claims the tag."""
    for r in doc["releases"]:
        if tag_of(r) == tag:
            return r, None
        for c in candidates_of(r):
            if isinstance(c, dict) and "v%s" % c.get("version") == tag:
                return r, c
    return None, None


def pep440_to_semver(v):
    """The Python version as Cargo spells it: 0.4.0rc1 -> 0.4.0-rc.1,
    0.4.0a2 -> 0.4.0-alpha.2, 0.4.0 -> 0.4.0. None when it is not a shape
    this project uses."""
    m = re.match(r"^(\d+\.\d+\.\d+)(?:(a|b|rc)(\d+))?$", v)
    if not m:
        return None
    base, kind, n = m.groups()
    if not kind:
        return base
    return "%s-%s.%s" % (base, {"a": "alpha", "b": "beta", "rc": "rc"}[kind], n)


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

def validate(doc):
    """-> list of problems, empty when the file is sound."""
    bad = []
    if doc.get("schema") != 1:
        bad.append("schema must be 1")
    releases = doc.get("releases") or []
    if not releases:
        bad.append("no releases")

    KNOWN, SCALARS, MAPPINGS = known(), scalars(), mapping_keys()
    seen_v, seen_t, latest = set(), set(), []
    for r in releases:
        v = r.get("version", "<unnamed>")
        where = "release %s" % v

        for key in r:
            if key not in KNOWN:
                bad.append("%s: unknown key %r" % (where, key))
        for key in CFG["required"]:
            if r.get(key) in (None, ""):
                bad.append("%s: missing %s" % (where, key))

        if v in seen_v:
            bad.append("%s: duplicate version" % where)
        seen_v.add(v)

        tag = r.get("tag")
        if tag:
            if tag in seen_t:
                bad.append("%s: duplicate tag %s" % (where, tag))
            seen_t.add(tag)
            if CFG["tag_rule"] == "exact" and tag != "v" + str(v):
                bad.append("%s: tag %r should be %r" % (where, tag, "v" + str(v)))
            elif CFG["tag_rule"] == "prefix" and not tag.startswith("v"):
                bad.append("%s: tag %r should start with 'v'" % (where, tag))

        status = r.get("status")
        if status not in STATUSES:
            bad.append("%s: status %r not one of %s"
                       % (where, status, ", ".join(sorted(STATUSES))))

        date = r.get("date")
        if status == "unreleased":
            if date:
                bad.append("%s: unreleased but carries a date" % where)
        elif not date:
            bad.append("%s: %s but has no date" % (where, status))
        elif not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date)):
            bad.append("%s: date %r is not ISO yyyy-mm-dd" % (where, date))

        if r.get("mirror") and status != "released":
            bad.append("%s: mirror: true but status is %r -- the mirror can "
                       "only carry a published release" % (where, status))

        if r.get("latest"):
            latest.append(r)

        for key in sorted(MAPPINGS):
            block = r.get(key)
            if block is None:
                continue
            if not isinstance(block, dict):
                bad.append("%s: %s must be a mapping of profile -> list"
                           % (where, key))
                continue
            for prof, names in block.items():
                if not isinstance(names, list) or not all(
                        isinstance(n, str) for n in names):
                    bad.append("%s: %s.%s must be a list of strings"
                               % (where, key, prof))

        for key in sorted(SCALARS):
            val = r.get(key)
            # By what it is not, rather than by an allowlist: YAML resolves a
            # bare 'date: 2026-01-01' to a datetime.date, and an allowlist of
            # scalar types would have to name every tag the resolver knows.
            if not isinstance(val, (list, tuple, dict, set)):
                continue
            bad.append("%s: %s must be a single value, not a %s -- a block "
                       "scalar is '%s: |', not '%s:' followed by '- |'"
                       % (where, key, type(val).__name__, key, key))

        for key, _ in SECTIONS:
            items = r.get(key)
            if items is None:
                continue
            if not isinstance(items, list):
                bad.append("%s: %s must be a list" % (where, key))
                continue
            for i, item in enumerate(items):
                if not isinstance(item, str) or not item.strip():
                    bad.append("%s: %s[%d] must be a non-empty string"
                               % (where, key, i))

    if len(latest) != 1:
        bad.append("exactly one release must carry 'latest: true' (found %d)"
                   % len(latest))
    else:
        r = latest[0]
        for key in CFG["latest_requires"]:
            if not r.get(key):
                bad.append("release %s is latest but %s is not true"
                           % (r.get("version"), key))
        if r.get("status") != "released":
            bad.append("release %s is latest but is not released"
                       % r.get("version"))
    return bad


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

def heading(r, candidate=None):
    if candidate is not None:
        return "## [%s] - %s (release candidate of %s)" % (
            candidate["version"], candidate["date"], r["version"])
    date = r.get("date") or "unreleased"
    text = "## [%s] - %s" % (r["version"], date)
    marks = []
    if not r.get("stable"):
        marks.append("prerelease")
    if r.get("status") == "tagged":
        marks.append("tagged, not published")
    if marks:
        text += " (%s)" % ", ".join(marks)
    return text


def bullets(items):
    """A bullet may be multiline; its first line is the headline, and the
    rest is indented under it so Markdown keeps it inside the item."""
    out = []
    for item in items:
        lines = item.rstrip("\n").split("\n")
        out.append("- " + lines[0])
        for line in lines[1:]:
            out.append(("  " + line).rstrip())
    return out


def facts_of(r):
    """The compatibility facts this project records, in declared order.
    A fact renders when every key it names is present; the first variant
    that matches wins, which is how `diluvium (buildN)` collapses to
    `diluvium` when there is no build number."""
    out, used = [], set()
    for f in CFG["facts"]:
        slot = f.get("id") or f["keys"][0]
        if slot in used:
            continue
        if any(r.get(k) is None or r.get(k) == "" for k in f["keys"]):
            continue
        out.append(f["fmt"].format(**r))
        used.add(slot)
    return out


def render_release(r, candidate=None):
    out = [heading(r, candidate), ""]
    meta = []
    tag = "v%s" % candidate["version"] if candidate else tag_of(r)
    if tag:
        meta.append("`%s`" % tag)
    meta += facts_of(r)
    if meta:
        out += [" &middot; ".join(meta), ""]
    if candidate is None and candidates_of(r):
        out += ["Release candidates: " + ", ".join(
            "`v%s` (%s)" % (c["version"], c["date"]) for c in candidates_of(r)), ""]
    if r.get("summary"):
        out += [r["summary"].rstrip("\n"), ""]
    for m in CFG["mappings"]:
        key = m["key"]
        if not r.get(key):
            continue
        out += ["### " + m["title"], ""]
        for prof in sorted(r[key]):
            out.append("- `%s`: %s" % (prof, ", ".join(
                "`%s`" % n for n in r[key][prof]) or "_none_"))
        out.append("")
    for key, title in SECTIONS:
        if r.get(key):
            out += ["### " + title, ""] + bullets(r[key]) + [""]
    if r.get("upgrading"):
        out += ["### Upgrading", "", r["upgrading"].rstrip("\n"), ""]
    return "\n".join(out).rstrip("\n") + "\n"


def render_planned(doc):
    """Work that is real and scheduled but NOT in this tree. Kept out of
    `releases` on purpose: an entry there claims the code is here, and
    `consistency` checks the newest one against the tree."""
    items = (doc.get("planned") or []) if CFG["planned"] else []
    if not items:
        return ""
    out = ["## Planned", ""]
    for p in items:
        out.append("### %s" % p["title"])
        out.append("")
        if p.get("branch"):
            out.append("Not on `main`. Lives on `%s`." % p["branch"])
            out.append("")
        out.append(p["summary"].rstrip("\n"))
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n\n"


def render_md(doc, tag=None):
    if tag:
        r, c = find_tag(doc, tag)
        if r is None:
            sys.exit("changelog.py: no release with tag %r" % tag)
        return render_release(r, c)
    head = (
        "# Changelog\n\n"
        "All notable changes to %s are recorded here.\n\n"
        "Generated from `CHANGELOG.yaml`, which is the source of truth --\n"
        "edit that file, then run `technoproj-changelog generate`.\n\n"
        % CFG["project"]
    ) + KAC + CFG["intro_extra"]
    return (head + "\n" + render_planned(doc)
            + "\n\n".join(render_release(r) for r in doc["releases"]))


def render_json(doc):
    """What the mirror consumes. Rendered Markdown travels with each entry
    so the mirror needs no renderer of its own."""
    fact_keys = []
    for f in CFG["facts"]:
        for k in f["keys"]:
            if k not in fact_keys:
                fact_keys.append(k)
    keys = (["version", "tag", "date", "status", "stable", "mirror"]
            + fact_keys + [m["key"] for m in CFG["mappings"]]
            + ["summary", "upgrading"])
    out = {
        "schema": doc["schema"],
        "repo": doc["repo"],
        "latest": next((tag_of(r) for r in doc["releases"] if r.get("latest")),
                       None),
        "mirror_tags": [tag_of(r) for r in doc["releases"] if r.get("mirror")],
        "releases": [],
    }
    for r in doc["releases"]:
        entry = {k: r.get(k) for k in keys}
        # PyYAML gives an unquoted yyyy-mm-dd back as a datetime.date; the
        # mirror wants a plain ISO string.
        entry["date"] = str(r["date"]) if r.get("date") else None
        entry["latest"] = bool(r.get("latest"))
        entry["sections"] = {k: r[k] for k, _ in SECTIONS if r.get(k)}
        entry["notes_md"] = render_release(r)
        out["releases"].append(entry)
    return json.dumps(out, indent=2) + "\n"


# ---------------------------------------------------------------------------
# consistency
# ---------------------------------------------------------------------------

def spell(version, spelling):
    """Delegated to technoproj.version so there is one implementation of
    the spelling rules. This used to respell PEP 440 into SemVer, which was
    the wrong direction once the canonical form became the tag body."""
    return _version.respell(version, spelling)


def consistency(doc):
    """The newest entry describes the tree as it stands, so the tree has to
    agree with it. The generic half is `stamps` in .technoproj: a file, a
    pattern, and which spelling of the version it should hold. The half
    that cannot be generalised is the repository's own script/checks.py."""
    bad = []
    r = doc["releases"][0]
    version = str(r["version"])
    where = "newest entry (%s)" % version

    # The entry's `version` is the TAG BODY -- `1.4.0-rc.1`, not `1.4.0rc1`.
    # That is what validate() enforces under tag_rule: exact, and this used
    # to demand the PEP 440 spelling instead, so no prerelease could satisfy
    # both. Plain releases hid it: X.Y.Z is the same in every spelling.
    parsed = None
    try:
        parsed = _version.parse(version)
    except _version.VersionError as e:
        bad.append("%s: %s" % (where, e))

    # Not a return: a bad version shape used to skip every stamp below and
    # the repository's own checks, so one problem silenced all the others.
    for st in (CFG["stamps"] if parsed else []):
        path, pattern = st["file"], st["find"]
        want = spell(version, st.get("spelling"))
        try:
            text = read(path)
        except OSError as e:
            bad.append("%s: cannot read (%s)" % (path, e))
            continue
        found = set(re.findall(pattern, text, re.M))
        if not found:
            bad.append("%s: no version matching %s" % (path, pattern))
            continue
        wrong = sorted(v for v in found if v != want)
        if wrong:
            bad.append("%s carries version %s but %s implies %r"
                       % (path, ", ".join(repr(w) for w in wrong), where, want))

    bad += repo_checks(doc, _version.base(parsed) if parsed else version)
    return bad


def repo_checks(doc, base):
    """The repository's own invariants, if it has any. A repo declares them
    in script/checks.py as `def consistency(doc, ctx) -> list[str]`; ctx
    carries `read`, `root` and the base version so the check needs no
    imports of its own."""
    path = os.path.join(ROOT, "script", "checks.py")
    if not os.path.exists(path):
        return []
    ns = {}
    try:
        with open(path) as f:
            exec(compile(f.read(), path, "exec"), ns)   # noqa: S102
    except Exception as e:                              # noqa: BLE001
        return ["script/checks.py: failed to load (%s)" % e]
    fn = ns.get("consistency")
    if not callable(fn):
        return ["script/checks.py: no consistency(doc, ctx) function"]
    return list(fn(doc, {"read": read, "root": ROOT, "base": base}))


def release_check(doc, tag, publishing):
    """Gate a release on its changelog entry. -> (problems, outputs)."""
    entry, cand = find_tag(doc, tag)
    if entry is None:
        return (["no entry in CHANGELOG.yaml for tag %r -- add one before "
                 "releasing it" % tag], {})
    bad = []
    if publishing and cand is None:
        if entry["status"] != "released":
            bad.append(
                "%s is still status: %s. Before publishing, edit "
                "CHANGELOG.yaml: set status: released and a date, move "
                "latest: true onto it, set mirror: true, then re-run "
                "changelog.py generate and commit." % (tag, entry["status"]))
        if not entry.get("date"):
            bad.append("%s has no date" % tag)
    stable = entry.get("stable") and cand is None
    return bad, {"prerelease": "false" if stable else "true",
                 "version": cand["version"] if cand else entry["version"]}


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------

def main():
    global CFG
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("command", choices=["validate", "render", "mirror-tags",
                                        "latest", "generate", "check",
                                        "consistency", "release-check"])
    ap.add_argument("format", nargs="?", choices=["md", "json"])
    ap.add_argument("--tag")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    args = ap.parse_args()
    if args.help:
        print(__doc__)
        return 0

    CFG = config()
    doc = load()
    problems = validate(doc)
    if problems:
        for p in problems:
            print("CHANGELOG.yaml: " + p, file=sys.stderr)
        return 1

    md_path = os.path.join(ROOT, "CHANGELOG.md")
    json_path = os.path.join(ROOT, "changelog.json")

    if args.command == "validate":
        print("OK: %d releases, latest=%s, %d mirrored"
              % (len(doc["releases"]),
                 next(tag_of(r) for r in doc["releases"] if r.get("latest")),
                 sum(1 for r in doc["releases"] if r.get("mirror"))))
    elif args.command == "render":
        if args.format == "json":
            if not CFG["emit_json"]:
                sys.exit("changelog.py: this project does not emit changelog.json")
            sys.stdout.write(render_json(doc))
        else:
            sys.stdout.write(render_md(doc, args.tag))
    elif args.command == "mirror-tags":
        for r in doc["releases"]:
            if r.get("mirror"):
                print(tag_of(r))
    elif args.command == "latest":
        print(next(tag_of(r) for r in doc["releases"] if r.get("latest")))
    elif args.command == "consistency":
        problems = consistency(doc)
        if problems:
            for p in problems:
                print("inconsistent: " + p, file=sys.stderr)
            return 1
        print("OK: the tree agrees with %s" % doc["releases"][0]["version"])
    elif args.command == "release-check":
        if not args.tag:
            sys.exit("changelog.py: release-check needs --tag")
        problems, out = release_check(doc, args.tag, args.publish)
        if problems:
            for p in problems:
                print("release-check: " + p, file=sys.stderr)
            return 1
        for k, v in out.items():
            print("%s=%s" % (k, v))
    elif args.command in ("generate", "check"):
        want = {md_path: render_md(doc)}
        if CFG["emit_json"]:
            want[json_path] = render_json(doc)
        stale = []
        for path, text in want.items():
            name = os.path.relpath(path, ROOT)
            if args.command == "generate":
                with open(path, "w") as f:
                    f.write(text)
                print("wrote %s" % name)
            else:
                try:
                    with open(path) as f:
                        current = f.read()
                except OSError:
                    current = None
                if current != text:
                    stale.append(name)
        if stale:
            print("stale, re-run 'technoproj-changelog generate': %s"
                  % ", ".join(sorted(stale)), file=sys.stderr)
            return 1
        if args.command == "check":
            print("OK: the generated files match CHANGELOG.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
