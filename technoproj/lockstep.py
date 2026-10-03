#!/usr/bin/env python3
"""The operating layout: an owner, an agent operator, and the agreed truth
between them, laid out the same way in every repository.

This layout was worked out in a private operating repository. It is
copied here so other repositories adopt it from one place, for the same
reason version.mk is: three repositories each carried
.claude/rules/human-surfaces.md, and the three copies had already drifted
into two generations. doc/LOCKSTEP.md is the standard; this module places
and checks it.

    technoproj lockstep init [--owner LOGIN]   place every missing file,
                                               then sync; never overwrites
    technoproj lockstep sync                   rewrite the shared rules
    technoproj lockstep check                  every gap, in the order to
                                               fix it; exit 1 if any (CI)

The scaffold includes doc/lockstep/dispatch.md, the outbox through which
one repository asks another for work instead of writing to it; `check`
reads its items and the dispatch block in sources.yaml.

Two kinds of file, and they are treated oppositely. SHARED rules are the
same in every repository, so they are written by `sync` and must match
byte for byte; a repository changes them upstream, here. SCAFFOLD files
are the repository's own agreed truth, so `init` writes them once and
nothing here ever overwrites them; `check` only looks at their shape.
"""
import fnmatch
import json
import re
import sys
from pathlib import Path

import yaml

try:                                     # 3.9+ without importlib.resources.files
    from importlib.resources import files as _files
except ImportError:                      # pragma: no cover
    _files = None

# What a repository declares under TECHNO_LOCKSTEP in .technoproj. Every
# field has a default, and a repository with no .technoproj at all gets
# them, so adopting the layout does not require adopting the release tools.
DEFAULTS = {
    # The declared human surfaces, rendered into human-surfaces.md.
    "surfaces": ["README.md", "doc/", "examples/"],
}

# Placed by `sync`, checked byte for byte. Destination -> packaged source.
SHARED = {
    ".claude/rules/operating.md": "shared/operating.md",
    ".claude/rules/lockstep.md": "shared/lockstep.md",
    ".claude/rules/human-surfaces.md": "shared/human-surfaces.md",
}

# Placed by `init` when missing, never overwritten. Destination -> packaged
# source. The packaged names drop the leading dot so packaging keeps them.
SCAFFOLD = {
    ".claude/CLAUDE.md": "scaffold/claude/CLAUDE.md",
    ".claude/log.md": "scaffold/claude/log.md",
    "doc/lockstep/README.md": "scaffold/doc/lockstep/README.md",
    "doc/lockstep/authority.yaml": "scaffold/doc/lockstep/authority.yaml",
    "doc/lockstep/sources.yaml": "scaffold/doc/lockstep/sources.yaml",
    "doc/lockstep/goal.md": "scaffold/doc/lockstep/goal.md",
    "doc/lockstep/roadmap.md": "scaffold/doc/lockstep/roadmap.md",
    "doc/lockstep/queue.md": "scaffold/doc/lockstep/queue.md",
    "doc/lockstep/ledger.md": "scaffold/doc/lockstep/ledger.md",
    "doc/lockstep/dispatch.md": "scaffold/doc/lockstep/dispatch.md",
    ".github/CODEOWNERS": "scaffold/github/CODEOWNERS",
    # GitHub does not read this from the repository; the owner imports it
    # in Settings > Rules. It is placed so the import has a source.
    ".github/rulesets/main.json": "scaffold/github/rulesets/main.json",
}

# Scaffold files `check` does not require: an import source, not a rule.
OPTIONAL = {".github/rulesets/main.json"}

# Text the scaffold leaves for the owner. A required file still carrying one
# is a gap.
FILL_MARKERS = ("technoproj: fill in", "@OWNER")

# authority.yaml: the shape every repository keeps, and the files the
# self_merge lane may never reach, because the operator cannot widen its
# own authority.
TIERS = ("autonomous", "approve_first", "never")
SELF_MERGE_KEYS = ("paths", "except", "conditions")
LIMIT_KEYS = ("subagents_per_run", "spend_usd", "run_minutes")
NEVER_SELF_MERGED = (
    ".claude/CLAUDE.md",
    ".claude/rules/operating.md",
    "doc/lockstep/authority.yaml",
    "doc/lockstep/goal.md",
    "doc/lockstep/roadmap.md",
)

# CODEOWNERS must name the owner on each of these.
OWNED = ("/doc/lockstep/", "/.claude/CLAUDE.md", "/.claude/rules/")

ROADMAP_STATUSES = ("todo", "active", "review", "done")

# dispatch.md: one item per asked-for piece of work in another repository.
# Routers parse these, so the header and the fields are fixed, not
# conventional. `inbox: issues` is how a public repository receives asks
# without naming a private router in its sources.
DISPATCH_HEADER = re.compile(r"^## D-(\d+) To: (\S+?)\. \S.*$")
DISPATCH_FIELDS = ("Why", "Ask", "Approval", "Re")
DISPATCH_INBOX_ISSUES = "issues"


class LockstepError(Exception):
    pass


# depth: reading the declaration and the packaged files

def declaration(root):
    """TECHNO_LOCKSTEP from .technoproj, over the defaults."""
    path = Path(root) / ".technoproj"
    decl = {}
    if path.is_file():
        try:
            decl = json.loads(path.read_text()).get("TECHNO_LOCKSTEP") or {}
        except ValueError as e:
            raise LockstepError(".technoproj is not valid JSON (%s)" % e)
    unknown = sorted(set(decl) - set(DEFAULTS))
    if unknown:
        raise LockstepError("TECHNO_LOCKSTEP has unknown keys: %s"
                            % ", ".join(unknown))
    out = dict(DEFAULTS)
    out.update(decl)
    surfaces = out["surfaces"]
    if (not isinstance(surfaces, list) or not surfaces
            or not all(isinstance(s, str) and s for s in surfaces)):
        raise LockstepError("TECHNO_LOCKSTEP.surfaces must be a non-empty "
                            "list of paths")
    return out


def packaged(rel):
    if _files is not None:
        return Path(str(_files("technoproj") / "data" / "lockstep" / rel))
    return Path(__file__).resolve().parent / "data" / "lockstep" / rel  # pragma: no cover


def rendered(dest, decl):
    """The exact text SHARED[dest] must hold in this repository."""
    text = packaged(SHARED[dest]).read_text()
    if dest.endswith("human-surfaces.md"):
        text = text.replace("@@SURFACES@@", "\n".join(
            "- `%s`" % s for s in decl["surfaces"]))
    return text


# depth: the three commands

def sync(root, out=print):
    decl = declaration(root)
    for dest in SHARED:
        path = Path(root) / dest
        want = rendered(dest, decl)
        if path.is_file() and path.read_text() == want:
            out("unchanged %s" % dest)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(want)
        out("wrote %s" % dest)
    return 0


def init(root, owner=None, out=print):
    declaration(root)                    # refuse a bad declaration first
    for dest, src in SCAFFOLD.items():
        path = Path(root) / dest
        if path.exists():
            out("kept %s" % dest)
            continue
        text = packaged(src).read_text()
        if owner:
            text = text.replace("@OWNER", "@" + owner.lstrip("@"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        out("wrote %s" % dest)
    return sync(root, out)


def gaps(root):
    """Every way this repository departs from the layout, in fix order."""
    root = Path(root)
    found = []
    decl = declaration(root)

    for dest in SCAFFOLD:
        if dest not in OPTIONAL and not (root / dest).is_file():
            found.append("%s is missing -- run 'technoproj lockstep init'"
                         % dest)
    for dest in SHARED:
        path = root / dest
        if not path.is_file():
            found.append("%s is missing -- run 'technoproj lockstep sync'"
                         % dest)
        elif path.read_text() != rendered(dest, decl):
            found.append("%s has drifted from the installed technoproj -- "
                         "change it upstream, then run 'technoproj lockstep "
                         "sync'" % dest)

    for dest in SCAFFOLD:
        path = root / dest
        if dest in OPTIONAL or not path.is_file():
            continue
        text = path.read_text()
        if any(m in text for m in FILL_MARKERS):
            found.append("%s is not filled in yet" % dest)

    found += _authority_gaps(root / "doc/lockstep/authority.yaml")
    found += _roadmap_gaps(root / "doc/lockstep/roadmap.md")
    found += _sources_gaps(root, root / "doc/lockstep/sources.yaml")
    found += _dispatch_gaps(root / "doc/lockstep/dispatch.md")
    found += _codeowners_gaps(root / ".github/CODEOWNERS")
    return found


def check(root, out=print, err=None):
    err = err or (lambda m: print(m, file=sys.stderr))
    found = gaps(root)
    if not found:
        out("OK: the lockstep layout holds")
        return 0
    err("technoproj: %d lockstep gap%s, in the order to fix them:"
        % (len(found), "" if len(found) == 1 else "s"))
    for g in found:
        err("  - %s" % g)
    return 1


# depth: shape checks for the repository's own files

def _authority_gaps(path):
    if not path.is_file():
        return []
    name = "doc/lockstep/authority.yaml"
    try:
        doc = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        return ["%s does not parse (%s)" % (name, e)]
    if not isinstance(doc, dict):
        return ["%s is not a mapping" % name]
    found = []
    tiers = doc.get("tiers")
    if not isinstance(tiers, dict):
        found.append("%s has no tiers" % name)
    else:
        for t in TIERS:
            if not isinstance(tiers.get(t), list):
                found.append("%s tiers.%s is not a list" % (name, t))
    lane = doc.get("self_merge")
    if not isinstance(lane, dict):
        found.append("%s has no self_merge lane" % name)
    else:
        for k in SELF_MERGE_KEYS:
            if not isinstance(lane.get(k), list):
                found.append("%s self_merge.%s is not a list" % (name, k))
        paths = lane.get("paths") or []
        excepts = lane.get("except") or []
        for target in NEVER_SELF_MERGED:
            reached = any(fnmatch.fnmatch(target, p) for p in paths)
            excluded = any(fnmatch.fnmatch(target, p) for p in excepts)
            if reached and not excluded:
                found.append("%s self_merge reaches %s -- the operator "
                             "cannot widen its own authority" % (name, target))
    limits = doc.get("limits")
    if not isinstance(limits, dict):
        found.append("%s has no limits" % name)
    else:
        for k in LIMIT_KEYS:
            if k not in limits:
                found.append("%s limits.%s is not set" % (name, k))
    return found


def _roadmap_gaps(path):
    if not path.is_file():
        return []
    statuses = []
    for line in path.read_text().splitlines():
        if line.startswith("## ") and line.rstrip().endswith("]"):
            statuses.append(line.rstrip().rsplit("[", 1)[-1][:-1])
    if not statuses:
        return ["doc/lockstep/roadmap.md has no iterations "
                "('## I0 Name [status]')"]
    bad = [s for s in statuses if s not in ROADMAP_STATUSES]
    if bad:
        return ["doc/lockstep/roadmap.md has unknown status%s: %s"
                % ("" if len(bad) == 1 else "es", ", ".join(bad))]
    return []


def _sources_gaps(root, path):
    if not path.is_file():
        return []
    name = "doc/lockstep/sources.yaml"
    try:
        doc = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        return ["%s does not parse (%s)" % (name, e)]
    if not isinstance(doc, dict):
        return ["%s is not a mapping" % name]
    d = doc.get("dispatch")
    if not isinstance(d, dict):
        return ["%s has no dispatch block (name, outbox, inbox)" % name]
    found = []
    if not (isinstance(d.get("name"), str) and d["name"].strip()):
        found.append("%s dispatch.name is not set" % name)
    outbox = d.get("outbox")
    if not (isinstance(outbox, str) and outbox):
        found.append("%s dispatch.outbox is not set" % name)
    elif not (Path(root) / outbox).is_file():
        found.append("%s dispatch.outbox names %s, which does not exist"
                     % (name, outbox))
    inbox = d.get("inbox")
    routed = (isinstance(inbox, dict)
              and all(isinstance(inbox.get(k), str) and inbox[k]
                      for k in ("repo", "path")))
    if inbox != DISPATCH_INBOX_ISSUES and not routed:
        found.append("%s dispatch.inbox must be '%s' or {repo, path}"
                     % (name, DISPATCH_INBOX_ISSUES))
    return found


def _dispatch_gaps(path):
    if not path.is_file():
        return []
    name = "doc/lockstep/dispatch.md"
    items = []                           # [header line, set of fields seen]
    for line in path.read_text().splitlines():
        if line.startswith("## "):
            items.append([line.rstrip(), set()])
        elif items and ":" in line:
            items[-1][1].add(line.split(":", 1)[0].strip())
    found, last = [], 0
    for header, fields in items:
        m = DISPATCH_HEADER.match(header)
        if not m:
            found.append("%s has a malformed item header: '%s' (want "
                         "'## D-001 To: name. Title')" % (name, header))
            continue
        n = int(m.group(1))
        if n <= last:
            found.append("%s D-%s is out of order or repeated -- items "
                         "are appended with the next number"
                         % (name, m.group(1)))
        last = max(last, n)
        missing = [f for f in DISPATCH_FIELDS if f not in fields]
        if missing:
            found.append("%s D-%s is missing %s"
                         % (name, m.group(1), ", ".join(missing)))
    return found


def _codeowners_gaps(path):
    if not path.is_file():
        return []
    owned = set()
    for line in path.read_text().splitlines():
        parts = line.split("#", 1)[0].split()
        if len(parts) >= 2:
            owned.add(parts[0])
    return [".github/CODEOWNERS does not name an owner for %s" % p
            for p in OWNED if p not in owned]


def main(args, root):
    try:
        if args.lockstep_command == "init":
            return init(root, owner=args.owner)
        if args.lockstep_command == "sync":
            return sync(root)
        return check(root)
    except LockstepError as e:
        print("technoproj: %s" % e, file=sys.stderr)
        return 1
