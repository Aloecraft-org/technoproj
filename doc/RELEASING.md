# Releasing

**The canonical copy of this document lives in
[Aloecraft-org/technoproj](https://github.com/Aloecraft-org/technoproj).**
A consuming repository vendors it byte-identical, like `ALIGNMENT.md`, and
does not edit it — so it can be diffed against upstream, and so the answer to
"how do I release this project" is the same answer in every project.

Anything genuinely specific to one repository — which platforms it builds,
what its assets are called — is declared in that repository's `.technoproj`,
not written here and not written into its workflow.

---

## The whole procedure

```sh
technoproj release plan                       # what a release would be
technoproj release preflight                  # every gate CI runs, run here
technoproj release cut --tag v0.3.0           # rehearse it
technoproj release cut --tag v0.3.0 --publish --yes
```

That is it, in every repository. There is no fifth step and no per-project
variant. If one of those commands does not work in some repository, that
repository has not finished adopting the standard — `technoproj release
doctor` says which part.

### 1. Stamp the version

`.technoproj`'s `TECHNO_VERSION` is the one definition; every other spelling
derives from it.

```sh
make set_pre KIND=rc N=1      # a candidate
make clear_pre                # the final
technoproj show               # every spelling, derived
```

Then put the printed `pep440:` / `semver:` lines wherever this repository
stamps them (`pyproject.toml`, `Cargo.toml`, …). `TECHNO_CHANGELOG.stamps`
declares those places and CI fails when they disagree — it checks, it does
not write, so the number is still typed and never silently drifts.

### 2. Write the changelog entry

`CHANGELOG.yaml` is the source of truth. For a final release the entry needs
`status: released`, a `date`, `stable: true`, `latest: true` moved onto it
(and off the previous one), and `mirror:` answered.

```sh
technoproj-changelog generate      # writes CHANGELOG.md (+ changelog.json)
```

Commit both generated files. They are committed because the release mirror
reads `changelog.json` on a host with a stdlib-only Python and no build step;
`technoproj-changelog check` in CI is what stops that copy going stale.

### 3. Preflight

```sh
technoproj release preflight --tag v0.3.0
```

Runs, locally, the same gates the pipeline runs: `version.mk` has not
drifted, the changelog validates, the generated files match, the tree agrees
with the newest entry, the tag is releasable, and the workflow still conforms
to the contract. A release that fails here fails in CI ten minutes later for
the same reason.

Without `--publish` this is the rehearsal, so an entry still marked
`unreleased` passes — which is what it is on every commit between one release
and the next, and CI runs this on all of them. Add `--publish` for the gate
the release itself faces.

### 4. Cut it

Rehearse first — every gate, every build, artifacts left on the run, nothing
published:

```sh
technoproj release cut --tag v0.3.0 --yes
```

Then publish:

```sh
technoproj release cut --tag v0.3.0 --publish --yes
```

Without `--yes`, `cut` prints exactly what it would dispatch and sends
nothing. The same run can be started from the Actions tab — **Release → Run
workflow** — with the same three inputs, which is the route when you have a
browser and not a shell.

---

## Why you do not push the tag

**The workflow creates the tag. Do not push `v*` by hand.**

A tag push and a workflow dispatch reach the same place, and they need
different permissions from different identities:

| | who creates the tag | permission needed | who has it |
|---|---|---|---|
| `git push origin v0.3.0` | you | push to `refs/tags/*` on that repository | varies per person, per machine, per automation session, and per tag ruleset |
| `technoproj release cut` | the workflow's own `GITHUB_TOKEN` | `contents: write` on one job | the repository, always — it is in the workflow file |

The second row is a permission the repository grants itself, written down in
its own `release.yml`, readable by anyone looking at the file. The first row
is not a repository setting at all, which is why no amount of
**Settings → Actions** or **Settings → Tags** makes it uniform.

This is the whole explanation for "some sessions can cut a release and some
get a permissions error". An automation session is scoped to the
repositories it was attached to; it can push to the one it was started on and
is read-only on the next, and nothing in the target repository's settings
changes that. Dispatching needs only `actions: write` and fails with a clear
403 naming that scope, rather than a tag push that fails with something that
reads like an account problem.

```sh
technoproj release doctor
```

says which of the two routes is open here, before anything is attempted —
including whether a tag ruleset is active, and whether GitHub has the
workflow registered yet. (A workflow is dispatchable by file name only once
it exists on the default branch; before that, dispatch it by numeric id.)

### The other permissions trap

Naming **any** permission in a `permissions:` block sets every unnamed one to
`none`. So this, which is what every trusted-publishing example shows:

```yaml
    permissions:
      id-token: write        # and therefore contents: none
```

gives the job no `contents` at all. It is harmless while the job only
downloads artifacts and uploads to a registry — and the first checkout, tag
or release step added to it fails with a 403 that reads like an
organisation policy problem and is not one. Write `contents: read` next to
it. `technoproj release doctor` lists every job in the repository sitting on
this.

---

## What a repository declares

```json
"TECHNO_RELEASE": {
  "workflow": "release.yml",
  "name": "dollup {tag}",
  "artifacts": "dist-*",
  "registry": {"kind": "pypi", "workflow": "publish.yml"}
}
```

| field | meaning | default |
|---|---|---|
| `workflow` | the release workflow's file name | `release.yml` |
| `name` | release title; `{tag}`, `{body}`, `{base}`, `{semver}`, `{pep440}` | `<project> {tag}` |
| `artifacts` | `download-artifact` pattern the publish leg merges | `dist-*` |
| `changelog_gate` | run the changelog gates | on when `CHANGELOG.yaml` exists |
| `dev_builds` | `-dev.<n>` tags take the fast path | `false` |
| `registry` | the PyPI/npm leg, which stays in this repo — see below | none |

---

## The workflow

Two halves are shared and pinned; the middle is yours.

```yaml
name: Release

on:
  push:
    tags: ["v*"]
  workflow_dispatch:
    inputs:
      ref:     { type: string,  required: false, default: "" }
      tag:     { type: string,  required: false, default: "" }
      publish: { type: boolean, required: false, default: false }

permissions:
  contents: read

concurrency:
  group: release-${{ inputs.tag || github.ref }}
  cancel-in-progress: false

jobs:
  preflight:
    uses: Aloecraft-org/technoproj/.github/workflows/release-preflight.yml@v0.3.0
    with:
      ref: ${{ inputs.ref }}
      tag: ${{ inputs.tag }}
      publish: ${{ inputs.publish || false }}

  build:
    needs: preflight
    # ...whatever this project builds. Upload with a `dist-*` artifact name.

  publish:
    needs: [preflight, build]
    if: needs.preflight.outputs.publish == 'true'
    permissions:
      contents: write          # the caller grants this; the called workflow cannot
    uses: Aloecraft-org/technoproj/.github/workflows/release-publish.yml@v0.3.0
    with:
      tag:        ${{ needs.preflight.outputs.tag }}
      sha:        ${{ needs.preflight.outputs.sha }}
      branch:     ${{ needs.preflight.outputs.branch }}
      version:    ${{ needs.preflight.outputs.version }}
      prerelease: ${{ needs.preflight.outputs.prerelease }}
      artifacts:  dist-*
```

`technoproj release check-workflow` fails when any of that is missing, and
`release-preflight` runs it on every release, so a repository cannot drift
back off the contract quietly.

**Pin the `@v0.3.0`.** A release pipeline that tracks `main` changes when
nobody touched it. There is only one pin to keep: the shared workflows
install the engine from the very commit they were themselves read from
(`github.job_workflow_sha`), so the tool and the workflow are one version by
construction and cannot disagree.

### What preflight decides

| output | from |
|---|---|
| `tag` | the pushed tag, or the `tag` input |
| `publish` | true for a tag push; the `publish` input otherwise |
| `sha` | the commit being released |
| `branch` | derived, for `BUILDINFO.txt` — a tag push carries none |
| `version` | the changelog entry's |
| `prerelease` | the changelog's `stable`, inverted — not a checkbox |
| `dev` | whether this is a `-dev.<n>` build |

**A tag that already exists is a re-run, not an error** — the release is
updated in place and its assets replaced, so a run that died of
infrastructure needs no new version number. The one refusal is a tag that
points at a *different* commit than the one being built, which would publish
a release whose own tag disagrees with its assets.

### What publish writes

`BUILDINFO.txt` (tag, version, commit, branch, built, then this project's
compatibility facts from the changelog entry), `SHA256SUMS.txt` over
everything including it, and the release itself with the entry rendered as
its body — never GitHub's autogenerated commit list, which says what changed
in the repository rather than what changed for the person installing it.

### The registry leg stays in your repository

PyPI's trusted publishing matches the OIDC claim against **a workflow
filename in the publishing repository**. So the upload step cannot move into
a shared workflow, and `publish.yml` cannot be renamed without
re-registering the publisher first. The standard leaves that leg where it is
and checks its shape instead. Declare it in `TECHNO_RELEASE.registry` so
`doctor` knows it is deliberate.

---

## Dev builds

A `-dev.<n>` tag is one commit in someone's hands without a ten-minute gate:
no changelog entry, ever; never mirrored; always a prerelease; pruned once
newer ones exist. The number is allocated from the tags that exist, so it is
global, never reused, and two branches cannot collide.

`release-check` resolves a dev tag against the newest entry instead of
demanding one of its own, and refuses it when that entry is a different
`X.Y.Z` — a dev build of a version the changelog has not reached is a
mis-stamped tree, not a release.

---

## Adopting this

```sh
technoproj release doctor
```

lists what is missing, in order. The usual sequence:

1. `pip install "git+https://github.com/Aloecraft-org/technoproj@v0.3.0"`
2. Add `TECHNO_CHANGELOG` to `.technoproj` and delete `script/changelog.py`.
   The engine reproduces each repository's committed output from its
   declaration alone — if anything but the generated preamble changes, the
   declaration is wrong, not the engine.
3. `technoproj sync` to place `script/version.mk`, and commit it.
4. Add `TECHNO_RELEASE`, and the `release.yml` above.
5. `technoproj release check-workflow` until it passes.
6. Add `technoproj release check-workflow` to CI.
