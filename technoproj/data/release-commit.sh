#!/bin/sh
# release-commit.sh [COMMIT] -- is COMMIT the commit a production release
# is being cut from?
#
#   exit 0   yes: a dev build must not tag it
#   exit 3   no:  a dev build may
#   exit 1   it could not tell (not a commit, no jq)
#
# Every merge to the default branch cuts a dev build. The merge of a
# release-prep pull request lands there BEFORE the release tag exists, so a
# push-triggered dev build tagged the very commit the real Release run was
# building: diluvium's v0.17.4-dev.18 and v0.17.4 both name da9bbdf. A
# dev-build workflow's `push` and `schedule` runs skip when this exits 0; a
# `workflow_dispatch` still cuts, because someone asked for it.
#
# COMMIT is a release commit when the newest entry of its committed
# changelog.json is `released`, and either
#   - that entry's tag exists and points at COMMIT, or
#   - the tag does not exist yet and COMMIT is where the entry became
#     released: its first parent did not already have that entry released.
#
# Placed by `technoproj sync`, and `technoproj check` fails when this copy
# drifts. Change it in Aloecraft-org/technoproj, not here.
# `technoproj release release-commit` is the same rule, read from
# CHANGELOG.yaml, for a repository that does not emit changelog.json.
# Needs only git and jq.
set -eu

REF="${1:-HEAD}"
if ! COMMIT=$(git rev-parse -q --verify "$REF^{commit}"); then
  echo "release-commit: $REF is not a commit" >&2
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "release-commit: needs jq" >&2
  exit 1
fi

# "<status> <tag>" of the newest entry in COMMIT's committed changelog.json;
# empty when there is none.
newest() {
  git cat-file -e "$1:changelog.json" 2>/dev/null || return 0
  git show "$1:changelog.json" \
    | jq -r '(.releases[0] // {}) | "\(.status // "") \(.tag // "")"'
}

read -r STATUS TAG <<EOF
$(newest "$COMMIT")
EOF
if [ "${STATUS:-}" != released ] || [ -z "${TAG:-}" ]; then
  echo "release-commit: ${COMMIT}'s newest changelog entry is not released -- not a release commit" >&2
  exit 3
fi

if AT=$(git rev-parse -q --verify "refs/tags/$TAG^{commit}"); then
  if [ "$AT" = "$COMMIT" ]; then
    echo "release-commit: $TAG points at $COMMIT -- a release commit" >&2
    exit 0
  fi
  echo "release-commit: $TAG points at $AT, not $COMMIT -- not a release commit" >&2
  exit 3
fi

if PARENT=$(git rev-parse -q --verify "$COMMIT^1^{commit}"); then
  read -r PSTATUS PTAG <<EOF
$(newest "$PARENT")
EOF
  if [ "${PSTATUS:-}" = released ] && [ "${PTAG:-}" = "$TAG" ]; then
    echo "release-commit: $TAG was already released before $COMMIT, and is not tagged -- not a release commit" >&2
    exit 3
  fi
fi
echo "release-commit: $COMMIT is where $TAG became released, and it is not tagged yet -- a release commit" >&2
exit 0
