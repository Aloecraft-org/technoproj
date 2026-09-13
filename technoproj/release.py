#!/usr/bin/env python3
"""The release process, as one contract every repository follows.

Before this existed, "cut a release" meant something different in every
repository. aloelite dispatches `release.yml` with a `ref` that must already
be a tag; dollup and diluvium-drt dispatch the same workflow with a `tag`
input and *refuse* a tag that exists; xtrshow and aloeschema have no release
workflow at all and publish to PyPI from `publish.yml`; aloecrypt_js has no
changelog to gate anything with. The version scheme is standardised and the
changelog engine is shared, and the step that actually ships was still seven
different procedures.

This module is the declaration that ends that, and the four commands that
read it:

    technoproj release plan            what a release of this tree would be
    technoproj release preflight       every gate CI runs, run here first
    technoproj release doctor          what this repo is missing, and why a
                                       release would be refused
    technoproj release cut --tag TAG   start the release, by dispatch

`cut` is the one that matters for the permissions problem. A release is
started by *dispatching the workflow*, never by pushing a tag from a
workstation or an agent session: the workflow creates the tag itself, as
`GITHUB_TOKEN` with `contents: write`, which is a permission the repository
grants to itself and can be checked. Pushing `refs/tags/v*` needs a
permission that varies by who is pushing -- and an automation session that
has it for one repository routinely does not have it for the next, which is
exactly the failure that looks like "odd permissions issues" and is not
fixed by any repository setting. `doctor` says which of the two routes is
open before anything is attempted, rather than after a 403.

See doc/RELEASING.md for the process this implements.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

from . import version as _version

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")

# What a repository declares about its own release. Everything here has a
# default that is right for most repositories; a repository writes down only
# what it does differently, which is the same bargain TECHNO_CHANGELOG makes.
DEFAULTS = {
    "workflow": "release.yml",      # under .github/workflows
    "name": None,                   # release title; default "<project> <tag>"
    "artifacts": "dist-*",          # upload-artifact names the publish leg merges
    "changelog_gate": None,         # default: on when CHANGELOG.yaml exists
    "dev_builds": False,            # `-dev.<n>` tags take the fast path
    "registry": None,               # {"kind": "pypi"|"npm", "workflow": "..."}
}

# The reusable workflows this repository publishes. A consuming repo's
# release.yml calls these rather than carrying its own copy of the tag
# decision, the changelog gate, BUILDINFO.txt and the release upload.
PREFLIGHT = "Aloecraft-org/technoproj/.github/workflows/release-preflight.yml"
PUBLISH = "Aloecraft-org/technoproj/.github/workflows/release-publish.yml"


class ReleaseError(Exception):
    pass


def root():
    return os.environ.get("TECHNO_ROOT") or os.getcwd()


def _read(*parts):
    try:
        with open(os.path.join(root(), *parts)) as f:
            return f.read()
    except OSError:
        return None


def _exists(*parts):
    return os.path.exists(os.path.join(root(), *parts))


def config(proj):
    """The TECHNO_RELEASE block, with defaults filled in."""
    cfg = dict(DEFAULTS)
    cfg.update(proj.get("TECHNO_RELEASE") or {})
    if cfg["changelog_gate"] is None:
        cfg["changelog_gate"] = _exists("CHANGELOG.yaml")
    if not cfg["name"]:
        project = (proj.get("TECHNO_CHANGELOG") or {}).get("project")
        cfg["name"] = "%s {tag}" % project if project else "{tag}"
    reg = cfg.get("registry")
    if isinstance(reg, str):            # "pypi" is shorthand for the usual shape
        cfg["registry"] = {"kind": reg, "workflow": "publish.yml"}
    return cfg


def workflow_path(cfg):
    return os.path.join(".github", "workflows", cfg["workflow"])


def title(cfg, tag, v=None):
    """The release's title. `{tag}` is the one field every repository wants;
    the version spellings are there for the two that name the product and
    the number separately."""
    fields = dict(v or {})
    fields["tag"] = tag
    try:
        return cfg["name"].format(**fields)
    except (KeyError, IndexError, ValueError) as e:
        raise ReleaseError("TECHNO_RELEASE.name %r cannot be filled in (%s); "
                           "the fields are {tag}, {body}, {base}, {semver} "
                           "and {pep440}" % (cfg["name"], e))


# ---------------------------------------------------------------------------
# the repository's identity, for the API calls
# ---------------------------------------------------------------------------

def slug():
    """owner/repo, from the environment CI sets or from origin."""
    env = os.environ.get("GITHUB_REPOSITORY")
    if env and "/" in env:
        return env
    cfg = _read(".git", "config") or ""
    m = re.search(r'\[remote "origin"\][^\[]*?url\s*=\s*(\S+)', cfg, re.S)
    if not m:
        return None
    url = m.group(1)
    m = re.search(r"github\.com[:/]+([^/]+/[^/\s]+?)(?:\.git)?$", url)
    return m.group(1) if m else None


def token():
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        t = os.environ.get(name)
        # The agent proxies inject a placeholder and swap the real credential
        # in on the wire; it is a usable token to `requests through the
        # proxy` and a useless one to read, so treat it as present.
        if t:
            return t
    return None


def api(path, method="GET", body=None):
    """-> (status, parsed body or None). Never raises for HTTP status."""
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    t = token()
    if t:
        req.add_header("Authorization", "Bearer %s" % t)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else None
        except ValueError:
            return e.code, None
    except (urllib.error.URLError, OSError) as e:
        raise ReleaseError("cannot reach %s (%s)" % (url, e))


def default_branch(repo):
    """The repository's default branch, or `main` when it cannot be read."""
    status, info = api("/repos/%s" % repo)
    if status == 200 and (info or {}).get("default_branch"):
        return info["default_branch"]
    print("technoproj: cannot read %s's default branch (HTTP %s); assuming "
          "`main`. Pass --ref to be sure." % (repo, status), file=sys.stderr)
    return "main"


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------

def _changelog(cfg):
    """The changelog module, configured for this tree, or None when this
    repository has no changelog to gate on."""
    if not cfg["changelog_gate"]:
        return None
    from . import changelog as _cl
    _cl.ROOT = root()
    _cl.CFG = _cl.config()
    return _cl


def plan(proj, args):
    cfg = config(proj)
    v = _version.of(proj)
    repo = slug()

    print("release plan  %s" % (repo or "(no origin)"))
    print()
    print("  version")
    for k in ("tag", "body", "base", "semver", "pep440"):
        print("    %-8s %s" % (k + ":", v[k]))
    print()

    tag = args.tag or v["tag"]
    print("  tag to release   %s%s"
          % (tag, "" if args.tag else "   (from .technoproj)"))
    print("  workflow         %s" % workflow_path(cfg))
    print("  release title    %s" % title(cfg, tag, v))
    print("  artifacts        %s" % cfg["artifacts"])
    reg = cfg.get("registry")
    print("  registry leg     %s"
          % ("%s, from .github/workflows/%s (stays in this repo -- see "
             "doc/RELEASING.md)" % (reg["kind"], reg["workflow"])
             if reg else "none"))
    print()

    cl = _changelog(cfg)
    print("  changelog gate   %s" % ("on" if cl else "OFF -- no CHANGELOG.yaml"))
    if cl:
        doc = cl.load()
        problems = cl.validate(doc)
        if problems:
            for p in problems:
                print("    CHANGELOG.yaml: %s" % p)
            return 1
        bad, out = cl.release_check(doc, tag, True)
        if bad:
            print("    NOT releasable as %s:" % tag)
            for p in bad:
                print("      %s" % p)
            print()
            print("  -> fix the above, then `technoproj release preflight`.")
            return 1
        for k in ("version", "prerelease", "dev"):
            print("    %-11s %s" % (k + ":", out.get(k, "?")))
    print()
    print("  -> `technoproj release preflight --tag %s` to run every gate here," % tag)
    print("     then `technoproj release cut --tag %s` to start it." % tag)
    return 0


# ---------------------------------------------------------------------------
# preflight -- every gate CI runs, run locally first
# ---------------------------------------------------------------------------

def preflight(proj, args):
    """Run the gates in the same order the workflow does, and report all of
    them rather than stopping at the first. A release that fails here fails
    in CI ten minutes later for the same reason.

    Strictness matches the rest of the vocabulary: without `--publish` this
    is the rehearsal, so an entry still marked `unreleased` passes -- which
    is what it is on every commit between one release and the next, and CI
    runs this on all of them. With `--publish` it is the gate the release
    itself faces.
    """
    cfg = config(proj)
    v = _version.of(proj)
    tag = args.tag or v["tag"]
    publishing = bool(getattr(args, "publish", False))
    checks, failed = [], 0

    def gate(name, fn):
        nonlocal failed
        try:
            bad = fn()
        except SystemExit as e:                 # the changelog engine's exits
            bad = [str(e)]
        except Exception as e:                  # noqa: BLE001 -- reported, not raised
            bad = ["%s: %s" % (type(e).__name__, e)]
        checks.append((name, bad))
        if bad:
            failed += 1

    gate("version.mk matches the installed technoproj", _version_mk_ok)

    cl = _changelog(cfg)
    if cl is None:
        checks.append(("changelog", ["skipped -- this repository declares no "
                                     "changelog gate"]))
    else:
        doc = cl.load()
        gate("CHANGELOG.yaml validates", lambda: cl.validate(doc))
        gate("the generated files match the YAML",
             lambda: [] if not _stale(cl, doc) else
                     ["stale: %s -- run `technoproj-changelog generate`"
                      % ", ".join(_stale(cl, doc))])
        gate("the tree agrees with the newest entry",
             lambda: cl.consistency(doc))
        gate("%s is releasable%s" % (tag, "" if publishing else " (rehearsal)"),
             lambda: cl.release_check(doc, tag, publishing)[0])

    gate("the release workflow conforms",
         lambda: check_workflow(proj, quiet=True))

    width = max(len(n) for n, _ in checks)
    for name, bad in checks:
        mark = "ok  " if not bad else ("--  " if "skipped" in " ".join(bad)
                                       else "FAIL")
        print("%s  %-*s" % (mark, width, name))
        for b in bad:
            print("      %s" % b)
    print()
    if failed:
        print("%d gate%s would fail in CI. Fix them before cutting %s."
              % (failed, "" if failed == 1 else "s", tag))
        return 1
    if publishing:
        print("every gate passes. `technoproj release cut --tag %s --publish "
              "--yes` is ready." % tag)
    else:
        print("every rehearsal gate passes. `--publish` additionally requires "
              "the entry to be marked released.")
    return 0


def _version_mk_ok():
    """`technoproj check`, without its own success line on our output."""
    import contextlib
    import io
    from . import cli as _cli
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = _cli.main(["check"])
    if rc == 0:
        return []
    return ["run `technoproj sync` and commit the result"]


def _stale(cl, doc):
    want = {"CHANGELOG.md": cl.render_md(doc)}
    if cl.CFG["emit_json"]:
        want["changelog.json"] = cl.render_json(doc)
    out = []
    for name, text in want.items():
        cur = _read(name)
        if cur != text:
            out.append(name)
    return sorted(out)


# ---------------------------------------------------------------------------
# check-workflow -- the conformance check, for CI
# ---------------------------------------------------------------------------

# What every conforming release workflow carries. These are not style: each
# one is a thing that differed between repositories and made a release
# procedure unportable.
def check_workflow(proj, quiet=False):
    """-> list of problems. Empty when this repo's release workflow follows
    the standard contract."""
    cfg = config(proj)
    path = workflow_path(cfg)
    text = _read(path)
    if text is None:
        return ["%s does not exist. See doc/RELEASING.md for the caller to "
                "copy; `technoproj release doctor` lists what else is "
                "missing." % path]
    try:
        import yaml
    except ImportError:                                  # pragma: no cover
        return ["PyYAML is required to check the workflow"]
    try:
        wf = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        return ["%s is not valid YAML (%s)" % (path, e)]

    bad = []
    # `on` is the YAML 1.1 boolean True once parsed, which is a trap worth
    # handling rather than rediscovering in each repository.
    on = wf.get("on", wf.get(True)) or {}

    tags = ((on.get("push") or {}).get("tags")) or []
    if not any(str(t).startswith("v") for t in tags):
        bad.append("%s: `on.push.tags` must include a `v*` pattern, so a tag "
                   "push releases" % path)

    inputs = ((on.get("workflow_dispatch") or {}).get("inputs")) or {}
    for want in ("ref", "tag", "publish"):
        if want not in inputs:
            bad.append("%s: `on.workflow_dispatch.inputs.%s` is missing. All "
                       "three are the contract `technoproj release cut` "
                       "dispatches against -- a repository that names them "
                       "differently cannot be released the same way as the "
                       "rest." % (path, want))

    if wf.get("permissions") != {"contents": "read"}:
        bad.append("%s: top-level `permissions:` must be exactly "
                   "`contents: read`, so the write is granted on the one job "
                   "that publishes and nowhere else" % path)

    if not wf.get("concurrency"):
        bad.append("%s: no `concurrency:` group -- two runs for one tag can "
                   "race to upload the same assets" % path)

    jobs = wf.get("jobs") or {}
    # technoproj is the repository that DEFINES the shared workflows, so its
    # own caller refers to them by local path -- pinning itself to a released
    # tag would test the last release instead of the change in hand. Every
    # other repository must name them by owner and pin them.
    owns = _exists(".github", "workflows", "release-preflight.yml")

    def calls(job, shared, local):
        u = str(job.get("uses", ""))
        return shared in u or (owns and u.startswith("./" + local.replace(os.sep, "/")))

    local_pre = os.path.join(".github", "workflows", "release-preflight.yml")
    local_pub = os.path.join(".github", "workflows", "release-publish.yml")
    pre = [j for j in jobs.values()
           if isinstance(j, dict) and calls(j, PREFLIGHT, local_pre)]
    pub = [j for j in jobs.values()
           if isinstance(j, dict) and calls(j, PUBLISH, local_pub)]
    if not pre:
        bad.append("%s: no job calls %s. The tag decision and the changelog "
                   "gate are shared; a repository that reimplements them in "
                   "shell is the drift this replaces." % (path, PREFLIGHT))
    if not pub:
        bad.append("%s: no job calls %s" % (path, PUBLISH))
    for j in pre + pub:
        u = str(j.get("uses", ""))
        if u.startswith("./"):
            continue                    # the defining repository; see above
        ref = u.split("@")[-1] if "@" in u else ""
        if not re.match(r"^v\d+\.\d+\.\d+", ref):
            bad.append("%s: `uses: %s` must pin a technoproj release tag "
                       "(`@vX.Y.Z`). A release pipeline that tracks a branch "
                       "changes when nobody touched it." % (path, u))
    for j in pub:
        if (j.get("permissions") or {}).get("contents") != "write":
            bad.append("%s: the job calling the publish workflow must set "
                       "`permissions: contents: write`. A called workflow "
                       "cannot raise its own permissions -- the caller grants "
                       "them, and this is the single most common reason a "
                       "release run dies at the upload." % path)

    reg = cfg.get("registry")
    if reg:
        rpath = os.path.join(".github", "workflows", reg["workflow"])
        if not _exists(rpath):
            bad.append("%s: declared as the %s leg, but the file does not "
                       "exist" % (rpath, reg["kind"]))
    bad.extend(t for t in permission_traps()
               if t.startswith(".github/workflows/%s:" % cfg["workflow"]))
    return bad


def permission_traps():
    """The `contents: none` trap, in every workflow this repository has.

    Naming ANY permission in a `permissions:` block sets every unnamed one
    to `none`. A job that asks only for `id-token: write` -- the shape every
    trusted-publishing example shows -- therefore has no `contents` at all:
    checkout of a private repository fails, and anything touching a release
    or a tag fails with a 403 that reads like an account or organisation
    problem and is not one. No repository setting fixes it, which is why it
    survives every round of "check Settings -> Actions".

    Checked across all workflows rather than only the declared release one,
    because the leg it usually bites is the registry upload -- and that leg
    cannot be moved into a shared workflow: PyPI's trusted publishing
    matches the OIDC claim against a workflow filename in the publishing
    repository, so the step must stay put and be checked in place.
    """
    import yaml
    wdir = os.path.join(root(), ".github", "workflows")
    if not os.path.isdir(wdir):
        return []
    bad = []
    for fn in sorted(os.listdir(wdir)):
        if not fn.endswith((".yml", ".yaml")):
            continue
        try:
            with open(os.path.join(wdir, fn)) as f:
                wf = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(wf, dict):
            continue
        top = wf.get("permissions")
        for name, job in (wf.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            perms = job.get("permissions", top)
            if not isinstance(perms, dict):
                continue
            if "id-token" in perms and "contents" not in perms:
                bad.append(
                    ".github/workflows/%s: job `%s` names `id-token` but not "
                    "`contents`, so it runs with `contents: none` -- naming "
                    "any permission drops every unnamed one. Harmless while "
                    "the job only downloads artifacts and uploads to a "
                    "registry, which is what it does today; the first "
                    "checkout, tag or release step added to it fails with a "
                    "403 that reads like an account problem. Add "
                    "`contents: read`." % (fn, name))
    return bad


# ---------------------------------------------------------------------------
# doctor -- what is missing here, and which release route is open
# ---------------------------------------------------------------------------

def doctor(proj, args):
    cfg = config(proj)
    repo = slug()
    rows, gaps = [], []

    def row(ok, what, detail=""):
        rows.append((ok, what, detail))
        if ok is False:
            gaps.append(what)

    print("release doctor  %s" % (repo or "(no origin remote)"))
    print()

    # --- the declaration and the tree ------------------------------------
    row(bool(proj.get("TECHNO_VERSION")), "TECHNO_VERSION declared")
    row(bool(proj.get("TECHNO_CHANGELOG")), "TECHNO_CHANGELOG declared",
        "" if proj.get("TECHNO_CHANGELOG") else
        "the changelog engine is not driven from this repo's declaration; it "
        "is still a forked script/changelog.py or nothing")
    row(bool(proj.get("TECHNO_RELEASE")), "TECHNO_RELEASE declared",
        "" if proj.get("TECHNO_RELEASE") else
        "defaults assumed: workflow=%s, artifacts=%s" % (cfg["workflow"],
                                                         cfg["artifacts"]))
    row(_exists("CHANGELOG.yaml"), "CHANGELOG.yaml",
        "" if _exists("CHANGELOG.yaml") else
        "no changelog: release notes would be GitHub's commit list, and the "
        "changelog gate is off")
    row(_exists("script", "version.mk"), "script/version.mk")
    row(not _exists("script", "changelog.py"), "no forked script/changelog.py",
        "script/changelog.py is still here -- it has drifted from the engine "
        "in every repo that kept one" if _exists("script", "changelog.py")
        else "")
    row(_exists(workflow_path(cfg)), workflow_path(cfg))

    wf_bad = check_workflow(proj, quiet=True) if _exists(workflow_path(cfg)) \
        else ["(absent)"]
    if _exists(workflow_path(cfg)):
        row(not wf_bad, "the release workflow conforms",
            "%d problem%s" % (len(wf_bad), "" if len(wf_bad) == 1 else "s")
            if wf_bad else "")

    width = max(len(w) for _, w, _ in rows)
    for ok, what, detail in rows:
        print("  %s  %-*s  %s" % ("ok " if ok else "GAP", width, what, detail))
    if _exists(workflow_path(cfg)) and wf_bad:
        print()
        print("  workflow conformance:")
        for b in wf_bad:
            print("    - %s" % b)

    traps = permission_traps()
    if traps:
        print()
        print("  permission traps (advisory -- these do not fail a release "
              "today)")
        for t in traps:
            print("    - %s" % t)

    # --- the two routes, and which one is open ----------------------------
    print()
    print("  how a release can be started from here")
    print()
    if not repo:
        print("    no GitHub remote -- neither route can be checked.")
        return 1 if gaps else 0
    if args.offline:
        print("    (--offline: not asking GitHub)")
        return 1 if gaps or wf_bad else 0

    owner_repo = repo
    status, info = api("/repos/%s" % owner_repo)
    if status == 404:
        print("    GitHub says 404 for %s. Either it does not exist or this "
              "token cannot see it -- for an agent session that usually means "
              "the repository was never attached to the session, which is not "
              "a repository setting and cannot be fixed in one." % owner_repo)
        return 1
    if status == 401:
        print("    GitHub says 401: no usable credential in GITHUB_TOKEN or "
              "GH_TOKEN.")
        return 1
    perms = (info or {}).get("permissions") or {}
    print("    identity      %s" % ("token present" if token() else "no token"))
    print("    repo access   push=%s admin=%s"
          % (perms.get("push", "?"), perms.get("admin", "?")))

    # Route 1: dispatch. Needs `actions: write` and nothing else.
    wf_file = cfg["workflow"]
    st, _ = api("/repos/%s/actions/workflows/%s" % (owner_repo, wf_file))
    if st == 200:
        print("    dispatch      OPEN -- %s is registered; "
              "`technoproj release cut` will work" % wf_file)
    elif st == 404:
        print("    dispatch      BLOCKED -- GitHub does not have %s "
              "registered. A workflow is registered once it exists on the "
              "default branch; until then dispatch it by numeric id, or "
              "merge it." % wf_file)
    else:
        print("    dispatch      unknown (HTTP %s)" % st)

    # Route 2: pushing the tag. The one that varies by session.
    st, wperm = api("/repos/%s/actions/permissions/workflow" % owner_repo)
    if st == 200 and wperm:
        d = wperm.get("default_workflow_permissions")
        print("    GITHUB_TOKEN  default=%s%s"
              % (d, "  (the publish job asks for contents: write explicitly, "
                    "so this default does not block it)" if d == "read" else ""))
    elif st in (403, 404):
        print("    GITHUB_TOKEN  cannot read the setting (HTTP %s) -- needs "
              "admin; not required for a release" % st)

    st, rules = api("/repos/%s/rulesets" % owner_repo)
    if st == 200 and isinstance(rules, list):
        tagrules = [r for r in rules if r.get("target") == "tag"
                    and r.get("enforcement") == "active"]
        if tagrules:
            print("    tag rulesets  %d active on tags: %s"
                  % (len(tagrules), ", ".join(r.get("name", "?")
                                              for r in tagrules)))
            print("                  a ruleset on tags can refuse a tag push "
                  "from an identity it does not list, while the workflow's "
                  "own GITHUB_TOKEN creates the same tag without trouble. "
                  "This is the difference that reads as a random permissions "
                  "failure.")
        else:
            print("    tag rulesets  none active")

    print()
    print("    -> start releases with `technoproj release cut --tag vX.Y.Z`.")
    print("       It dispatches the workflow, which creates the tag itself.")
    print("       Do not push `v*` tags by hand: whether that works depends "
          "on who")
    print("       you are, and it is the one step no repository setting makes "
          "uniform.")
    return 1 if gaps or wf_bad else 0


# ---------------------------------------------------------------------------
# cut -- start the release
# ---------------------------------------------------------------------------

def cut(proj, args):
    cfg = config(proj)
    v = _version.of(proj)
    tag = args.tag or v["tag"]

    # What the release IS, before where to send it: a changelog that does not
    # claim this tag is the thing to fix either way, and saying so beats
    # reporting a missing remote when both are true.
    cl = _changelog(cfg)
    if cl is not None:
        doc = cl.load()
        bad = cl.validate(doc) or cl.release_check(doc, tag, args.publish)[0]
        if bad:
            for b in bad:
                print("release cut: %s" % b, file=sys.stderr)
            return 1

    repo = slug()
    if not repo:
        raise ReleaseError("no GitHub origin remote to dispatch against")

    # The workflow file is read from this ref, so it must be a branch that
    # has it -- and the default branch is not `main` everywhere (diluvium's
    # history carries `master` too). Ask, rather than assume.
    ref = args.ref or default_branch(repo)

    body = {"ref": ref,
            "inputs": {"ref": args.ref or "", "tag": tag,
                       "publish": "true" if args.publish else "false"}}
    target = "/repos/%s/actions/workflows/%s/dispatches" % (repo, cfg["workflow"])

    print("dispatch  %s" % repo)
    print("  workflow  %s" % cfg["workflow"])
    print("  on ref    %s" % ref)
    print("  tag       %s" % tag)
    print("  publish   %s" % ("true -- this creates the tag and the GitHub "
                              "release" if args.publish else
                              "false (rehearsal: builds everything, "
                              "publishes nothing)"))
    if not args.yes:
        print()
        print("Nothing sent. Re-run with --yes to dispatch it.")
        return 0

    status, resp = api(target, method="POST", body=body)
    if status == 204:
        print()
        print("dispatched. Watch it at https://github.com/%s/actions/workflows/%s"
              % (repo, cfg["workflow"]))
        return 0
    msg = (resp or {}).get("message", "")
    print("", file=sys.stderr)
    print("dispatch refused: HTTP %s %s" % (status, msg), file=sys.stderr)
    if status == 403:
        print("  This token lacks `actions: write` on %s. That is the only "
              "permission a release needs from you -- run `technoproj release "
              "doctor` for what is open." % repo, file=sys.stderr)
    if status == 404:
        print("  Either %s is not on the default branch yet (GitHub registers "
              "a workflow only once it is), or this token cannot see %s at "
              "all." % (cfg["workflow"], repo), file=sys.stderr)
    if status == 422:
        print("  The workflow exists but rejected the inputs. Its "
              "`workflow_dispatch.inputs` must be `ref`, `tag` and `publish` "
              "-- run `technoproj release doctor`.", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------

def main(proj, args):
    if args.release_command == "plan":
        return plan(proj, args)
    if args.release_command == "preflight":
        return preflight(proj, args)
    if args.release_command == "doctor":
        return doctor(proj, args)
    if args.release_command == "check-workflow":
        bad = check_workflow(proj)
        for b in bad:
            print("release: " + b, file=sys.stderr)
        if bad:
            return 1
        print("OK: the release workflow follows the standard contract")
        return 0
    return cut(proj, args)
