# The Aloecraft project standard

**Point a project at this document.** It is the whole of what a repository
has to do to have a changelog and a release that work the same way as every
other Aloecraft repository's.

Three things are standardised, and this covers all of them:

1. **The changelog** — `CHANGELOG.yaml` is written; `CHANGELOG.md` and
   `changelog.json` are generated from it and committed. → [Part 1](#part-1--the-changelog)
2. **The actions** — a `release.yml` that calls two shared workflows and
   keeps only its own build jobs. → [Part 2](#part-2--the-actions)
3. **Cutting a release** — the same four commands in every repository.
   → [Part 3](#part-3--cutting-a-release)

[Part 4](#part-4--adopting) is the checklist for a repository that has none
of it yet.

[`ALIGNMENT.md`](ALIGNMENT.md) is the one other document: the version scheme,
artifact naming and `BUILDINFO.txt`. Its canonical copy and this one both
live in
[Aloecraft-org/technoproj](https://github.com/Aloecraft-org/technoproj); a
repository vendors them byte-identical and does not edit them, so they can be
diffed against upstream.

**The one command to start from:**

```sh
pip install "git+https://github.com/Aloecraft-org/technoproj@v0.3.0"
technoproj release doctor
```

`doctor` lists exactly what this repository is missing, in the order to fix
it. Everything below is the explanation behind those lines.

---

# Part 1 — The changelog

## The shape

```
CHANGELOG.yaml      written by hand — the source of truth
CHANGELOG.md        generated; committed
changelog.json      generated; committed, when `emit_json` is on
```

Both generated files are committed because the release mirror reads
`changelog.json` on a host with a stdlib-only Python and no build step.
`technoproj-changelog check` in CI is what stops those copies going stale.
Neither is ever edited by hand.

```sh
technoproj-changelog generate      # write them
technoproj-changelog check         # fail if they drifted (CI)
technoproj-changelog validate      # schema
technoproj-changelog consistency   # the tree agrees with the newest entry
```

## A complete entry

```yaml
schema: 1
repo: Aloecraft-org/example

releases:
  - version: "0.4.0"
    tag: v0.4.0
    date: "2026-09-13"
    status: released
    stable: true
    latest: true
    mirror: true
    summary: |
      One paragraph on what changed for someone installing this, then as
      many more as it earns. This is the release page's body and the first
      thing anyone reads.
    added:
      - |
        A bullet. Multi-line bullets are fine and stay inside their bullet.
      - A short one needs no block scalar.
    changed:
      - |
        What moved, and what a reader has to do about it.
    fixed:
      - |
        The failure, not the patch: "a prerelease could not satisfy
        validate() and consistency() at once", not "fixed a bug".
    known_issues:
      - |
        Things that are still wrong, said here rather than discovered.
    upgrading: |
      Only when upgrading takes a step. Omit it otherwise.
```

### Every key

**Required of every entry** (the default; `TECHNO_CHANGELOG.required`
changes it): `version`, `tag`, `status`, `stable`, `mirror`, `summary`.

| key | type | notes |
|---|---|---|
| `version` | string | **the tag body** — `0.4.0`, `0.4.0-rc.1`. Not PEP 440. Quote it, or YAML makes `1.10` a float. |
| `tag` | string | under `tag_rule: exact` it must be `"v" + version` |
| `date` | `yyyy-mm-dd` | required unless `status: unreleased`; **forbidden** when unreleased |
| `status` | `released` \| `unreleased` \| `tagged` | |
| `stable` | bool | **this, not GitHub's checkbox, decides `prerelease`** |
| `latest` | bool | exactly one entry in the file carries it, and it must be `released` |
| `mirror` | bool | only ever true on a `released` entry |
| `summary` | block scalar | the release body |
| `upgrading` | block scalar | rendered as its own section |
| `added` `changed` `deprecated` `removed` `fixed` `security` `known_issues` | list of strings | Keep a Changelog's six, plus ours, rendered in that order |
| `candidates` | list | only when `candidates: true` is declared |

Any key not in that list, or declared as a fact or a mapping, is **rejected**
— a typo is an error rather than a silently dropped section.

### The four rules that actually bite

**`version` is the tag body, never PEP 440.** `0.4.0-rc.1`, not `0.4.0rc1`.
PEP 440 is a *derived* spelling that exists in `pyproject.toml` and on PyPI
and nowhere else. Plain releases hide the difference — `X.Y.Z` is the same in
every spelling — so this only ever bites on a candidate. Entries written
before the scheme keep the spelling their tag has; existing tags are never
respelled.

**A block scalar is `summary: |`, not a list.** This is the most common
mistake and the error message says so:

```yaml
summary: |            # right
  Text.

summary:              # wrong — that is a list of one string
  - |
    Text.
```

**Exactly one entry carries `latest: true`, and it must be released.** Moving
it is part of cutting a release, not an afterthought.

**An unreleased entry has no date.** It gets one when it ships. `validate`
refuses a date on an unreleased entry and refuses a missing one anywhere
else.

### Writing entries people can use

Schema aside, these are conventions and the tooling does not enforce them:

- **Say what changed for the reader, not what changed in the repository.**
  That is why the release body is the entry rather than GitHub's
  autogenerated commit list.
- **A fix names the failure.** "A prerelease could not satisfy `validate()`
  and `consistency()` at once" beats "fixed a bug in version handling" —
  someone hitting it can recognise it.
- **`summary` carries the argument; the section bullets carry the
  inventory.** If the summary is one line and there are thirty bullets, the
  release has not been explained.
- **`known_issues` is not an admission of failure.** It is the difference
  between a known limit and a surprise.
- **Write the entry before the tag, not after.** It is a release gate:
  `release-check` refuses a tag the changelog does not claim.

## The `TECHNO_CHANGELOG` declaration

Everything that genuinely differs goes in `.technoproj` under
`TECHNO_CHANGELOG`, rather than forking the engine. That is the whole bargain
— one tool, and a fact table per repository.

```json
"TECHNO_CHANGELOG": {
  "project": "Example",
  "tag_rule": "exact",
  "emit_json": true,
  "facts": [
    {"id": "abi", "keys": ["dv_abi"], "fmt": "dv ABI {dv_abi}"}
  ],
  "mappings": [{"key": "connectors", "title": "Connectors"}],
  "stamps": [
    {"file": "pyproject.toml",
     "find": "^version\\s*=\\s*\"([^\"]+)\"",
     "spelling": "pep440"}
  ],
  "required": ["version", "tag", "status", "stable", "mirror", "summary"],
  "latest_requires": ["stable", "mirror"],
  "candidates": false,
  "planned": false
}
```

| field | meaning |
|---|---|
| `project` | display name in the generated preamble. **Required.** |
| `intro_extra` | text after the Keep a Changelog line |
| `facts` | compatibility facts, in render order. A fact renders when every key it names is present; the first variant matching an `id` wins, which is how `diluvium (buildN)` collapses to `diluvium` with no build number. Fact keys become legal entry keys. |
| `mappings` | profile → list blocks, e.g. a connector or feature matrix |
| `tag_rule` | `exact` (tag is `v{version}`), `prefix` (starts with `v`), `derive` (fall back to `v{version}`) |
| `required` | keys every entry must carry |
| `latest_requires` | keys the `latest` entry must carry |
| `candidates` | release candidates listed under their release |
| `planned` | a top-level `planned` section — work that is real and scheduled and **not in this tree**, deliberately kept out of `releases` because an entry there claims the code is here |
| `emit_json` | generate `changelog.json` — required for a `source: changelog` release mirror |
| `stamps` | where this repository's version is written, and in which spelling |

### `stamps` — what it promises, exactly

Each stamp is a file, a regex with one capture group, and a spelling
(`pep440`, `semver` or `base`). It **checks**; it does not write. The number
is still typed in each place, and CI fails when the places disagree.

That is a smaller claim than "stop hand-typing the version", and it is the
real one. xtrshow keeps the same version in four files today with nothing
checking them.

### `script/checks.py` — the invariant that does not generalise

Bespoke rules are not forced into config. A repository declares them in
`script/checks.py` and the engine calls it if the file exists:

```python
def consistency(doc, ctx):
    """ctx carries read(path), root, and base (the X.Y.Z version)."""
    bad = []
    text = ctx["read"]("src/db.py")
    ...
    return bad          # list of problem strings; empty is a pass
```

Real ones: diluvium's `LUAC_FORMAT` and `LUA_VERSION_*`, DRT's `Cargo.lock`
diluvium pin, aloelite's `SCHEMA_ERA`, aloeschema's vendored schema.org
release.

## Migrating off a forked `script/changelog.py`

The engine reproduces each repository's committed output from its declaration
alone — `CHANGELOG.md` and `changelog.json`, byte for byte. The single
intended difference is that the generated preamble names
`technoproj-changelog generate` rather than `script/changelog.py generate`,
so the first `generate` after migrating produces a one-line diff.

**If anything else in your output changes, the declaration is wrong — not the
engine.** Diff before deleting the fork.

---

# Part 2 — The actions

## What a conforming repository has

```
.github/workflows/release.yml     yours: the trigger surface and your build jobs
.github/workflows/publish.yml     yours, if you publish to PyPI or npm — see below
```

and nothing else about releasing, because the two halves that were never
meant to differ between projects are shared:

| shared workflow | what it settles |
|---|---|
| `release-preflight.yml` | which tag, which commit, whether this run publishes, and the changelog gate |
| `release-publish.yml` | `BUILDINFO.txt`, `SHA256SUMS.txt`, the notes, the release itself |

## The caller, complete

Copy this. Change the build job; change nothing else.

```yaml
name: Release

on:
  push:
    branches: ["main"]     # a merge cuts a dev build — see Part 3
    tags: ["v*"]
  workflow_dispatch:
    inputs:
      ref:
        description: "Commit, branch or tag to release (blank = this branch)"
        type: string
        required: false
        default: ""
      tag:
        description: "Tag name, e.g. v0.4.0. Required when publishing."
        type: string
        required: false
        default: ""
      publish:
        description: "Publish. Leave off for a rehearsal."
        type: boolean
        required: false
        default: false

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
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ needs.preflight.outputs.sha }}   # the commit preflight resolved
      # ...whatever this project builds...
      - uses: actions/upload-artifact@v4
        with:
          name: dist-linux_x86_64_gnu               # any `dist-*` name
          path: out/*
          if-no-files-found: error

  publish:
    needs: [preflight, build]
    if: needs.preflight.outputs.publish == 'true'
    permissions:
      contents: write        # the caller grants this; a called workflow cannot
      # + `actions: write` if this repository has a registry leg -- see below
    uses: Aloecraft-org/technoproj/.github/workflows/release-publish.yml@v0.3.0
    with:
      tag:        ${{ needs.preflight.outputs.tag }}
      sha:        ${{ needs.preflight.outputs.sha }}
      branch:     ${{ needs.preflight.outputs.branch }}
      version:    ${{ needs.preflight.outputs.version }}
      prerelease: ${{ needs.preflight.outputs.prerelease }}
      name:       Example ${{ needs.preflight.outputs.tag }}
      artifacts:  dist-*
      keep-dev:   5          # how many dev RELEASES survive; tags are kept
```

Three things in there are load-bearing and easy to get wrong:

**Build from `needs.preflight.outputs.sha`**, not from `github.sha`. Preflight
resolved which commit is being released; a build job that checks out
something else can ship assets from a different tree than the notes.

**`permissions: contents: write` on the publish job.** A called workflow
cannot raise its own permissions — the caller grants them. Without this line
the run dies at the upload, twenty minutes in, with a 403.

**Pin `@v0.3.0`.** A release pipeline that tracks `main` changes when nobody
touched it. There is only one pin to keep: the shared workflows install the
engine from the very commit they were themselves read from, so the tool and
the workflow cannot end up different versions.

## The `TECHNO_RELEASE` declaration

What the workflow above does not say for itself:

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
| `dev_builds` | a merge to the default branch cuts a `-dev.<n>` build | `false` |
| `keep-dev` (workflow input) | how many dev *releases* survive; tags are kept | `5` |
| `registry` | the PyPI/npm leg: stays in this repo, and is handed the tag rather than left waiting for a push — see below | none |

Every field has a default, so most repositories declare two or three lines.
`examples/release.json` has the three shapes the fleet actually has.

## The contract

`preflight` outputs:

| output | from |
|---|---|
| `tag` | the pushed tag, or the `tag` input |
| `publish` | true for a tag push; the `publish` input otherwise |
| `sha` | the commit being released |
| `branch` | derived — a tag push carries none |
| `version` | the changelog entry's |
| `prerelease` | the changelog's `stable`, inverted |
| `dev` | whether this is a `-dev.<n>` build |

**A tag that already exists is a re-run**, and the release is updated in
place with its assets replaced — so a run that died of infrastructure needs
no new version number. The one refusal is a tag pointing at a *different*
commit than the one being built.

A run with `publish` off is a full rehearsal: every gate, every build,
artifacts left on the run, nothing published. Do that first.

## What publish writes

`BUILDINFO.txt` — tag, version, commit, branch, built, then this project's
compatibility facts taken from the changelog entry, so the release page and
`BUILDINFO.txt` are rendered by one tool and cannot disagree. Then
`SHA256SUMS.txt` over everything including it, written last so the glob does
not cover itself.

The release body is **the changelog entry rendered**, never GitHub's
autogenerated commit list — which says what changed in the repository rather
than what changed for the person installing it.

## Permissions

**The workflow creates the tag. Nobody pushes one.**

| | who creates the tag | permission | who has it |
|---|---|---|---|
| `git push origin v0.4.0` | you | push to `refs/tags/*` | varies by person, machine, automation session, and tag ruleset |
| `technoproj release cut` | the workflow's `GITHUB_TOKEN` | `contents: write` on one job | the repository, always — it is in the file |

The second is a permission the repository grants itself and anyone can read
back. The first is not a repository setting at all, which is why no amount of
**Settings → Actions** or **Settings → Tags** makes it uniform, and why the
same automation can cut a release in one repository and fail in the next.

### The `contents: none` trap

Naming **any** permission drops every unnamed one to `none`. So the shape
every trusted-publishing example shows:

```yaml
    permissions:
      id-token: write        # and therefore contents: none
```

leaves the job with no `contents` at all. Harmless while it only downloads
artifacts and uploads to a registry — and the first checkout, tag or release
step added to it fails with a 403 that reads like an organisation policy
problem and is not one. Write `contents: read` beside it. `doctor` lists
every job in the repository sitting on this.

### The registry leg stays in your repository, and must be handed the tag

PyPI's trusted publishing matches the OIDC claim against **a workflow
filename in the publishing repository**. So the upload step cannot move into
a shared workflow owned by technoproj. The name is yours — technoproj reads
it from your declaration and no file has to be called anything in
particular — but **whatever you have already registered with PyPI is the
name PyPI will accept**, so renaming it means re-registering the publisher
first, and it fails confusingly if you do not.

**This is the part that bites.** The publish job creates the tag with
`GITHUB_TOKEN`, and GitHub starts no workflow run from an event that token
created — the recursion guard, which cannot be turned off. So a registry
workflow triggered `on: push: tags:` **never fires** once you adopt this.
Nothing announces it: the release is published, the notes render, the assets
upload, and the only symptom is the registry still serving the previous
version.

`workflow_dispatch` is the documented exception to that guard, so the
release hands the tag over explicitly. Three things together, and
`check-workflow` fails if any is missing:

```json
"TECHNO_RELEASE": {"registry": {"kind": "pypi", "workflow": "publish.yml"}}
```

```yaml
  publish:
    permissions:
      contents: write
      actions: write                      # to dispatch the registry workflow
    uses: Aloecraft-org/technoproj/.github/workflows/release-publish.yml@v0.3.0
    with:
      # ...as above...
      registry-workflow: publish.yml
```

```yaml
# .github/workflows/publish.yml — your existing file, one addition
on:
  push:
    tags: ["v*"]                          # still right for a hand-pushed tag
  workflow_dispatch:
    inputs:
      tag:                                # what the release hands it
        type: string
        required: true
```

Then build from that input rather than from `github.ref` when it is set,
since a dispatched run is not on the tag.

## What to run in CI

```sh
technoproj check                     # version.mk has not drifted
technoproj release check-workflow    # the release workflow still conforms
technoproj release preflight         # every release gate, in rehearsal mode
technoproj-changelog check           # the generated files match the YAML
technoproj-changelog consistency     # the tree agrees with the newest entry
```

`preflight` without `--publish` is the rehearsal, which is what every commit
between one release and the next should pass.

---

# Part 3 — Cutting a release

```sh
technoproj release plan                       # what a release would be
technoproj release preflight                  # every gate CI runs, run here
technoproj release cut --tag v0.4.0 --yes     # rehearse it
technoproj release cut --tag v0.4.0 --publish --yes
```

That is it, in every repository. There is no fifth step and no per-project
variant. If one of those does not work somewhere, that repository has not
finished [Part 4](#part-4--adopting) — `technoproj release doctor` says which
part.

Those four are for a **release**. For a build in someone's hands there is a
shorter answer that needs no commands and no permissions at all: merge, and
a dev build is cut. See [Dev builds](#dev-builds--where-merging-is-the-whole-procedure).

## 1. Stamp the version

`.technoproj`'s `TECHNO_VERSION` is the one definition; every other spelling
derives from it.

```sh
make set_pre KIND=rc N=1      # a candidate
make clear_pre                # the final
technoproj show               # every spelling, derived
```

Then put the printed `pep440:` / `semver:` lines wherever this repository
stamps them. `TECHNO_CHANGELOG.stamps` declares those places and CI fails
when they disagree — it checks, it does not write, so the number is still
typed and never silently drifts.

## 2. Write the changelog entry

The schema is [Part 1](#a-complete-entry). For a final release the entry
needs `status: released`, a `date`, `stable: true`, `latest: true` moved onto
it and off the previous one, and `mirror:` answered.

```sh
technoproj-changelog generate      # writes CHANGELOG.md (+ changelog.json)
```

Commit both generated files with it.

For a **release candidate**, the `X.Y.Z` entry stays `status: unreleased`
and `stable: false`, and the candidate is listed under it — as the tag body,
not PEP 440:

```yaml
    candidates:
      - version: "0.4.0-rc.1"
        date: "2026-09-13"
```

A candidate is not mirrored, so it takes no `mirror` flag.

## 3. Preflight

```sh
technoproj release preflight --tag v0.4.0
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

## 4. Cut it

Rehearse first — every gate, every build, artifacts left on the run, nothing
published:

```sh
technoproj release cut --tag v0.4.0 --yes
```

Then publish:

```sh
technoproj release cut --tag v0.4.0 --publish --yes
```

Without `--yes`, `cut` prints exactly what it would dispatch and sends
nothing. The same run can be started from the Actions tab — **Release → Run
workflow** — with the same three inputs, which is the route when you have a
browser and not a shell.

**The workflow creates the tag; you do not push one.** See
[Permissions](#permissions) for why that is the whole of the difference
between a release that works everywhere and one that works on some machines.

## Dev builds — where merging is the whole procedure

```json
"TECHNO_RELEASE": {"dev_builds": true}
```

```yaml
on:
  push:
    branches: ["main"]
```

That is it. **Every merge to the default branch cuts a `-dev.<n>` build** and
puts it on the releases page. Nobody runs a command, nobody pushes a tag,
nobody dispatches anything.

This is the part that matters if releasing has been painful. The four
commands in Part 3 all need something from whoever runs them — a session
scoped to the repository, `actions: write`, the right to push
`refs/tags/*` — and which of those you have is invisible until it fails.
**A merge needs none of them.** The workflow run is already going, so there
is no ref for anyone to push and no dispatch to be refused; the tag is
created at the end by the publish leg, with `contents: write` the repository
grants itself. A session that can open a pull request can ship a build, and
opening a pull request is the one thing every session can reliably do.

It is safe to do on every merge because of what a dev build *is*
(`ALIGNMENT.md` §7): no changelog entry, ever — so `mirror-tags` cannot list
it and no mirror will carry it; always a prerelease, so `pip install` and
`latest/` ignore it; and pruned once newer ones exist, so the releases page
does not fill up. `keep-dev` says how many survive. Their **tags** are never
deleted, which is what lets a number name exactly one build forever.

The number is allocated from the tags that exist rather than a counter in the
tree, so a build needs no commit, two branches cannot collide, and it is
global across versions — `0.4.0-dev.104` then `0.5.0-dev.105`.

```sh
technoproj release dev-tag              # the tag one would take right now
technoproj release dev-tag --if-changed # nothing, exit 3, if HEAD is already one
```

Only the default branch cuts one. A caller that watches `**` to self-test its
own pipeline still rehearses on a feature branch and publishes nothing.

`release-check` resolves a dev tag against the newest changelog entry instead
of demanding one of its own, and refuses it when that entry is a different
`X.Y.Z` — a dev build of a version the changelog has not reached is a
mis-stamped tree, not a release.

**The real release is unchanged and still deliberate**: a `v*` tag, or
`technoproj release cut`, with the changelog entry marked `released`. Merging
never ships that.

---

# Part 4 — Adopting

`technoproj release doctor` produces this list for your repository, with the
gaps marked. In order:

1. **Install and pin.**
   `pip install "git+https://github.com/Aloecraft-org/technoproj@v0.3.0"`
2. **Declare `TECHNO_CHANGELOG`** in `.technoproj`, run `generate`, diff
   against the committed files, then delete `script/changelog.py`.
3. **`technoproj sync`** to place `script/version.mk`; commit it.
4. **Declare `TECHNO_RELEASE`** — usually three lines; every field has a
   default.
5. **Add `release.yml`** from Part 2.
6. **`technoproj release check-workflow`** until it passes.
7. **Add the CI checks** above, so it cannot drift back off.

Steps are independent — a repository with no changelog can still adopt the
workflow, and `doctor` will say the gate is off rather than pretend
otherwise.

## Commands

```sh
technoproj show                      # this repo's version, every spelling
technoproj sync | check              # place / verify script/version.mk
technoproj release plan              # what a release of this tree would be
technoproj release preflight         # every gate CI runs, run here first
technoproj release doctor            # what is missing, and which route is open
technoproj release check-workflow    # the workflow conforms (CI)
technoproj release cut --tag v0.4.0 --publish --yes

technoproj-changelog validate | check | consistency | generate
technoproj-changelog render md --tag v0.4.0     # one release's section
technoproj-changelog release-check --tag v0.4.0 --publish
technoproj-changelog buildinfo --tag v0.4.0     # the entry's facts
technoproj-changelog latest | mirror-tags
```
