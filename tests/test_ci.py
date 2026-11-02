"""The CI trigger rule: one run per pull request commit."""
from technoproj import ci as C

GOOD = """name: ci
on:
  push:
    branches: [main]
  pull_request:
concurrency:
  group: ci-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
jobs: {}
"""


def tree(tmp_path, **files):
    d = tmp_path / ".github" / "workflows"
    d.mkdir(parents=True)
    for name, text in files.items():
        (d / name).write_text(text)
    return tmp_path


def test_the_recommended_shape_passes(tmp_path):
    assert C.check(tree(tmp_path, **{"ci.yml": GOOD})) == []


def test_a_repository_with_no_workflows_passes(tmp_path):
    assert C.check(tmp_path) == []


def test_push_on_every_branch_beside_pull_request_is_a_duplicate_run(tmp_path):
    bad = C.check(tree(tmp_path, **{"ci.yml": GOOD.replace("[main]", '["**"]')}))
    assert len(bad) == 1 and "`**`" in bad[0] and "twice" in bad[0]


def test_push_on_a_work_branch_glob_is_a_duplicate_run(tmp_path):
    bad = C.check(tree(tmp_path, **{"ci.yml": GOOD.replace("[main]", '[main, "claude/**"]')}))
    assert len(bad) == 1 and "`claude/**`" in bad[0]


def test_push_with_no_branch_filter_is_a_duplicate_run(tmp_path):
    text = GOOD.replace("  push:\n    branches: [main]\n", "  push:\n")
    bad = C.check(tree(tmp_path, **{"ci.yml": text}))
    assert len(bad) == 1 and "no `branches`" in bad[0]


def test_a_tag_only_push_is_not_a_pull_request_branch(tmp_path):
    text = GOOD.replace("    branches: [main]\n", '    tags: ["v*"]\n')
    assert C.check(tree(tmp_path, **{"ci.yml": text})) == []


def test_a_pull_request_workflow_needs_a_cancelling_concurrency_group(tmp_path):
    no_group = GOOD.split("concurrency:")[0] + "jobs: {}\n"
    bare = GOOD.replace("concurrency:\n  group: ci-${{ github.event.pull_request.number || github.ref }}\n"
                        "  cancel-in-progress: ${{ github.event_name == 'pull_request' }}\n",
                        "concurrency: ci\n")
    off = GOOD.replace("${{ github.event_name == 'pull_request' }}", "false")
    for text, words in ((no_group, "no top-level"), (bare, "bare group"),
                        (off, "is off")):
        bad = C.check(tree(tmp_path / words.replace(" ", "-"), **{"ci.yml": text}))
        assert len(bad) == 1 and words in bad[0], bad


def test_a_workflow_no_pull_request_triggers_is_left_alone(tmp_path):
    text = 'on:\n  push:\n    branches: ["**"]\n    paths: [x]\njobs: {}\n'
    assert C.check(tree(tmp_path, **{"release.yml": text})) == []


def test_main_exits_nonzero_and_names_each_problem(tmp_path, capsys):
    root = tree(tmp_path, **{"ci.yml": GOOD.replace("[main]", '["**"]')})
    assert C.main(None, root) == 1
    assert "ci.yml" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# a dev build does not tag a release commit
# ---------------------------------------------------------------------------

DEV = """name: dev
on:
  push:
    branches: [main]
  schedule:
    - cron: "0 4 * * *"
  workflow_dispatch:
jobs:
  dev:
    runs-on: ubuntu-latest
    steps:
      - id: guard
        if: github.event_name != 'workflow_dispatch'
        run: |
          if script/release-commit.sh; then echo skip=true >> "$GITHUB_OUTPUT"; fi
      - if: steps.guard.outputs.skip != 'true'
        run: TAG=$(script/dev-tag.sh)
"""
UNGUARDED = DEV.replace(
    "          if script/release-commit.sh; then echo skip=true >> \"$GITHUB_OUTPUT\"; fi\n",
    "          true\n")


def test_a_guarded_dev_build_passes(tmp_path):
    assert C.check(tree(tmp_path, **{"dev.yml": DEV})) == []


def test_a_dev_build_with_no_release_commit_guard_is_flagged(tmp_path):
    bad = C.check(tree(tmp_path, **{"dev.yml": UNGUARDED}))
    assert len(bad) == 1, bad
    assert "release-commit" in bad[0] and "`push` and `schedule`" in bad[0]


def test_each_way_of_cutting_a_dev_tag_needs_the_guard(tmp_path):
    for i, cut in enumerate(("make dev-tag", "make -f script/version.mk dev-tag",
                             "technoproj release dev-tag")):
        text = UNGUARDED.replace("TAG=$(script/dev-tag.sh)", "TAG=$(%s)" % cut)
        bad = C.check(tree(tmp_path / str(i), **{"dev.yml": text}))
        assert len(bad) == 1, (cut, bad)


def test_the_engine_guard_counts(tmp_path):
    # `technoproj release dev-tag --if-changed` applies the rule itself, and
    # `technoproj release release-commit` is the guard spelled in Python.
    a = UNGUARDED.replace("TAG=$(script/dev-tag.sh)",
                          "TAG=$(technoproj release dev-tag --if-changed)")
    b = DEV.replace("script/release-commit.sh", "technoproj release release-commit")
    for i, text in enumerate((a, b)):
        assert C.check(tree(tmp_path / str(i), **{"dev.yml": text})) == []


def test_a_schedule_alone_still_needs_the_guard(tmp_path):
    text = UNGUARDED.replace("  push:\n    branches: [main]\n", "")
    bad = C.check(tree(tmp_path, **{"dev.yml": text}))
    assert len(bad) == 1 and "`schedule`" in bad[0] and "`push`" not in bad[0]


def test_a_dispatch_only_dev_build_needs_no_guard(tmp_path):
    # Someone asked for that build; cutting it is the point.
    text = 'on:\n  workflow_dispatch:\njobs:\n  d:\n    runs-on: x\n' \
           '    steps: [{run: "script/dev-tag.sh"}]\n'
    assert C.check(tree(tmp_path, **{"dev.yml": text})) == []
