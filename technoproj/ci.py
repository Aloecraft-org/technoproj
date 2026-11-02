#!/usr/bin/env python3
"""The CI trigger rules: one run per pull request commit, and no dev tag
on a release commit.

    technoproj ci check        every workflow under .github/workflows

A workflow that a pull request triggers must not also be push-triggered on
the pull request's branch. Both fire for one commit, so every push to a PR
branch ran the whole workflow twice, and only the `pull_request` run is the
one a merge rule counts. Across the Aloecraft repositories the triggers had
drifted three ways (push on every branch, push on `claude/**`, push on the
default branch only), and the first two doubled the queue for the jobs the
third did not.

## surface block

- Entry points: `check(root)` -> list of problems; `main(args, root)`.
- Configurable values: DEFAULT_BRANCHES, the branch names a push trigger
  may name beside `pull_request`.
- Fan-out: RULES, the checks run on each workflow, in order.

The rule, per workflow that has a `pull_request` trigger:

1. `on.push`, if present, names only DEFAULT_BRANCHES under `branches`.
   No `branches` (every branch), a glob, or another branch is a duplicate
   run. A push trigger with only `tags` is fine: a tag is not a PR branch.
2. A top-level `concurrency` group whose `cancel-in-progress` can be true,
   so a newer commit on a PR cancels the run it replaces. Leaving a run on
   the default branch uncancelled is the caller's business, and the
   recommended form does (doc/STANDARD.md, "CI triggers").

And per workflow that has a `push` or `schedule` trigger:

3. If a step cuts a dev tag -- runs `script/dev-tag.sh`, `make dev-tag`,
   or `technoproj release dev-tag` without `--if-changed` -- some step
   also runs the release-commit guard (`script/release-commit.sh` or
   `technoproj release release-commit`). The merge of a release-prep pull
   request lands on the default branch before its release tag exists, so
   an unguarded dev build tags the commit the real release is building:
   diluvium's `v0.17.4-dev.18` and `v0.17.4` both name da9bbdf.
   `technoproj release dev-tag --if-changed` applies the guard itself,
   which is how the shared release-preflight.yml is covered.
"""
import os
import re

DEFAULT_BRANCHES = ("main", "master")


def _on(wf):
    # `on` parses as the YAML 1.1 boolean True; see release.check_workflow.
    on = wf.get("on", wf.get(True)) or {}
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {k: None for k in on}
    return on


# depth: the rules

def push_duplicates_pull_request(path, wf):
    on = _on(wf)
    if "pull_request" not in on or "push" not in on:
        return []
    push = on.get("push") or {}
    branches = push.get("branches")
    if branches is None:
        if push.get("tags") and not push.get("branches-ignore"):
            return []
        return ["%s: `on.push` has no `branches`, so every branch push runs "
                "it, and a pull request's commits run it twice (push and "
                "pull_request). Name only %s." % (path, _names())]
    extra = [str(b) for b in branches if str(b) not in DEFAULT_BRANCHES]
    if extra:
        return ["%s: `on.push.branches` names %s beside `pull_request`, so a "
                "pull request from such a branch runs it twice. Name only %s."
                % (path, ", ".join("`%s`" % b for b in extra), _names())]
    return []


def pull_request_runs_cancel(path, wf):
    if "pull_request" not in _on(wf):
        return []
    c = wf.get("concurrency")
    if not c:
        return ["%s: no top-level `concurrency`, so a run for a commit a "
                "newer push replaced still holds its runners to the end."
                % path]
    if isinstance(c, str):
        return ["%s: `concurrency` is a bare group, which queues a newer run "
                "behind the old one instead of cancelling it. Add "
                "`cancel-in-progress`." % path]
    cancel = c.get("cancel-in-progress")
    if cancel is None or cancel is False or str(cancel).lower() == "false":
        return ["%s: `concurrency.cancel-in-progress` is off, so a superseded "
                "pull request run is not cancelled." % path]
    return []


# What cuts a dev tag, and what guards it, matched as text in each step's
# `run:` anywhere in the workflow. Shell is not parsed, so a guard that is
# only named in a comment passes; the rule catches the workflow that has
# no guard at all, which is the shape that tagged da9bbdf.
CUTS_DEV_TAG = re.compile(
    r"dev-tag\.sh"
    r"|\bmake\b[^\n]*\bdev-tag\b"
    r"|\btechnoproj\s+release\s+dev-tag\b(?![^\n]*--if-changed)")
GUARDS_RELEASE_COMMIT = re.compile(
    r"release-commit\.sh|\btechnoproj\s+release\s+release-commit\b")


def _runs(wf):
    jobs = wf.get("jobs") or {}
    for job in (jobs.values() if isinstance(jobs, dict) else ()):
        steps = job.get("steps") if isinstance(job, dict) else None
        for step in steps or ():
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                yield step["run"]


def dev_build_skips_a_release_commit(path, wf):
    on = _on(wf)
    events = [e for e in ("push", "schedule") if e in on]
    if not events:
        return []
    runs = list(_runs(wf))
    if not any(CUTS_DEV_TAG.search(r) for r in runs):
        return []
    if any(GUARDS_RELEASE_COMMIT.search(r) for r in runs):
        return []
    return ["%s: cuts a dev tag on %s with no release-commit guard, so the "
            "merge of a release-prep pull request gets a dev tag on the "
            "commit the real release is building. Skip the cut on push and "
            "schedule when `script/release-commit.sh` exits 0 "
            "(doc/STANDARD.md, \"A release commit is not a dev build\")."
            % (path, " and ".join("`%s`" % e for e in events))]


RULES = (push_duplicates_pull_request, pull_request_runs_cancel,
         dev_build_skips_a_release_commit)


def _names():
    return " or ".join("`%s`" % b for b in DEFAULT_BRANCHES)


def workflows(root):
    d = os.path.join(str(root), ".github", "workflows")
    if not os.path.isdir(d):
        return []
    return sorted(os.path.join(".github", "workflows", n) for n in os.listdir(d)
                  if n.endswith((".yml", ".yaml")))


def check(root):
    """-> list of problems, empty when every workflow follows the rule."""
    import yaml
    bad = []
    for rel in workflows(root):
        with open(os.path.join(str(root), rel), encoding="utf-8") as f:
            try:
                wf = yaml.safe_load(f) or {}
            except yaml.YAMLError as e:
                bad.append("%s is not valid YAML (%s)" % (rel, e))
                continue
        if not isinstance(wf, dict):
            continue
        for rule in RULES:
            bad.extend(rule(rel, wf))
    return bad


def main(args, root):
    bad = check(root)
    for b in bad:
        print(b)
    if not bad:
        print("ok: %d workflow(s) run once per pull request commit, and "
              "none tags a release commit as a dev build"
              % len(workflows(root)))
    return 1 if bad else 0
