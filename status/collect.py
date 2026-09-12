#!/usr/bin/env python3
"""collect.py -- gather activity, build and release state into one status.json.

    collect.py --profile internal --out /var/www/html/status/data

The page this feeds is static. Everything it knows comes from this file, so
this is where the decisions live -- including which facts a profile is
allowed to publish at all.

Two rules, both learned the expensive way:

**Filtering happens here, not in the browser.** A profile that hides a field
by not rendering it still ships the field, and anyone can open devtools. The
public profile must therefore *not collect* what it must not publish, which
is why `include` is applied before anything is written.

**Every source records its own age and its own failure.** The release mirror
this reads was frozen for nine days while its index rewrote itself on
schedule with a fresh timestamp, and nothing looked wrong. So each source
carries `fetched_at`, `ok` and a `note`, and a source that could not be
collected says so rather than rendering as an empty section.

Env:
  GITHUB_TOKEN   optional. Without it, builds and activity are skipped --
                 unauthenticated GitHub allows 60 requests an hour, which
                 this would exhaust on its first run across seven repos.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

UA = "aloecraft-status/1"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
MIRRORS = "https://software.aloecraft.org/releases/mirrors.json"
TIMEOUT = 20


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def age_seconds(stamp):
    d = parse_iso(stamp)
    if d is None:
        return None
    return int((datetime.now(timezone.utc) - d).total_seconds())


def get_json(url, token=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    if token and TOKEN:
        req.add_header("Authorization", "Bearer " + TOKEN)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


# ---------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------

def collect_releases(projects):
    """The release mirror's own index, plus each mirror's releases.json.

    `mirror_age_s` is the age of the mirror's data, NOT of the index that
    wraps it -- those are different numbers, and the difference is exactly
    what hid a nine-day outage."""
    out, note = {}, None
    index = get_json(MIRRORS)
    for m in index.get("mirrors", []):
        name = m.get("name")
        if name not in projects:
            continue
        out[name] = {
            "title": m.get("title") or name,
            "repo": m.get("repo"),
            "version": m.get("latest"),
            "releases": m.get("releases"),
            "source": m.get("source"),
            "mirror_generated_at": m.get("generated_at"),
            "mirror_age_s": age_seconds(m.get("generated_at")),
        }
    missing = [p for p in projects if p not in out]
    if missing:
        note = "not carried by the release mirror: " + ", ".join(sorted(missing))
    return out, note, index.get("generated_at")


def collect_builds(repos):
    """The newest workflow run per repository, whatever its conclusion.

    -> (rows, failures). The failure count is not decoration: a source whose
    every fetch 403'd must not report itself healthy just because this
    function returned. That is the shape of the outage this page exists to
    make visible, and it is as easy to write here as anywhere."""
    out, failed = {}, 0
    for key, repo in repos.items():
        url = ("https://api.github.com/repos/%s/actions/runs?per_page=1" % repo)
        try:
            d = get_json(url, token=True)
        except (urllib.error.URLError, ValueError, OSError) as e:
            out[key] = {"status": "unknown", "note": "fetch failed: %s" % e}
            failed += 1
            continue
        runs = d.get("workflow_runs") or []
        if not runs:
            out[key] = {"status": "none", "note": "no workflow runs"}
            continue
        r = runs[0]
        out[key] = {
            "status": r.get("conclusion") or r.get("status") or "unknown",
            "workflow": r.get("name"),
            "at": r.get("updated_at"),
            "age_s": age_seconds(r.get("updated_at")),
            "branch": r.get("head_branch"),
            "url": r.get("html_url"),
        }
    return out, failed


def collect_activity(repos):
    """The newest commit per repository. -> (rows, failures), for the same
    reason collect_builds counts them."""
    out, failed = {}, 0
    for key, repo in repos.items():
        url = "https://api.github.com/repos/%s/commits?per_page=1" % repo
        try:
            d = get_json(url, token=True)
        except (urllib.error.URLError, ValueError, OSError) as e:
            out[key] = {"note": "fetch failed: %s" % e}
            failed += 1
            continue
        if not d:
            out[key] = {"note": "no commits"}
            continue
        c = d[0]
        at = (c.get("commit", {}).get("author") or {}).get("date")
        out[key] = {
            "at": at,
            "age_s": age_seconds(at),
            "subject": (c.get("commit", {}).get("message") or "").split("\n")[0],
            "sha": (c.get("sha") or "")[:12],
            "url": c.get("html_url"),
        }
    return out, failed


# ---------------------------------------------------------------------------
# profile
# ---------------------------------------------------------------------------

def keep(block, allowed):
    """A block reduced to the fields the profile allows. An empty allowlist
    drops the block entirely -- that is how `public` omits activity rather
    than shipping it and hiding it."""
    if not allowed:
        return None
    return {k: v for k, v in (block or {}).items() if k in allowed}


def build(profile):
    projects = profile["projects"]
    repos = {k: v["repo"] for k, v in projects.items() if v.get("repo")}
    include = profile.get("include", {})
    sources = []

    releases, note, index_at = {}, None, None
    try:
        releases, note, index_at = collect_releases(set(projects))
        sources.append({"name": "releases", "ok": True, "fetched_at": now(),
                        "note": note, "upstream_generated_at": index_at})
    except Exception as e:                                  # noqa: BLE001
        sources.append({"name": "releases", "ok": False, "fetched_at": now(),
                        "note": "could not read the release mirror: %s" % e})

    builds, activity = {}, {}
    if not TOKEN:
        skip = ("no GITHUB_TOKEN: unauthenticated GitHub allows 60 requests "
                "an hour, which this would exhaust on one run")
        for key, label in (("build", "builds"), ("activity", "activity")):
            if include.get(key):
                sources.append({"name": label, "ok": False, "fetched_at": None,
                                "note": skip})
    else:
        for key, label, fn, sink in (("build", "builds", collect_builds, "b"),
                                     ("activity", "activity", collect_activity, "a")):
            if not include.get(key):
                continue
            rows, failed = fn(repos)
            if sink == "b":
                builds = rows
            else:
                activity = rows
            total = len(repos)
            sources.append({
                "name": label,
                # Partial is not ok. Every fetch failing while the source
                # reports healthy is precisely the outage shape this page
                # was built to end.
                "ok": failed == 0,
                "fetched_at": now(),
                "note": None if not failed
                        else "%d of %d repositories could not be read" % (failed, total),
            })

    rows = []
    for key, meta in projects.items():
        rel = releases.get(key) or {}
        row = {
            "name": key,
            "title": meta.get("title") or rel.get("title") or key,
            "release": keep(rel, include.get("release")),
            "build": keep(builds.get(key), include.get("build")),
            "activity": keep(activity.get(key), include.get("activity")),
        }
        if not rel:
            row["release_note"] = "not on the release mirror"
        rows.append(row)

    return {
        "schema": 1,
        "profile": profile["name"],
        "title": profile.get("title") or "Status",
        "generated_at": now(),
        "sources": sources,
        "projects": rows,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--profile", required=True,
                    help="path to a profile json, or a name under profiles/")
    ap.add_argument("--out", required=True, help="directory to write status.json into")
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    path = args.profile
    if not os.path.exists(path):
        path = os.path.join(here, "profiles", args.profile + ".json")
    with open(path) as f:
        profile = json.load(f)

    doc = build(profile)
    os.makedirs(args.out, exist_ok=True)
    dest = os.path.join(args.out, "status.json")
    tmp = dest + ".tmp"
    with open(tmp, "w") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    os.replace(tmp, dest)

    bad = [s["name"] for s in doc["sources"] if not s["ok"]]
    print("wrote %s (%d projects, profile=%s)%s"
          % (dest, len(doc["projects"]), doc["profile"],
             "; degraded: " + ", ".join(bad) if bad else ""))
    # A source that could not be collected is not a crash -- the page says so
    # -- but the exit status has to carry it or nothing upstream ever knows.
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
