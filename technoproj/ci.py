#!/usr/bin/env python3
"""The CI trigger rule: one run per pull request commit.

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
"""
import os

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


RULES = (push_duplicates_pull_request, pull_request_runs_cancel)


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
        print("ok: %d workflow(s) run once per pull request commit"
              % len(workflows(root)))
    return 1 if bad else 0
