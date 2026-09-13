# Changelog

All notable changes to technoproj are recorded here.

Generated from `CHANGELOG.yaml`, which is the source of truth --
edit that file, then run `technoproj-changelog generate`.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.3.0] - unreleased (prerelease)

`v0.3.0`

One release process, shared rather than described. The version scheme
was standardised and the changelog engine was shared, and the step
that actually ships was still seven different procedures -- so cutting
a release meant relearning the repository first.

Two reusable workflows now carry the halves that were never meant to
differ: which tag is being released and whether this run publishes,
and BUILDINFO.txt, SHA256SUMS.txt, the notes and the release itself.
A consuming repository keeps only its build jobs.

The four `release.yml` files this replaces disagreed on the release's
own identity, not on how to build. aloelite had no `tag` input and
required the tag to exist; dollup and diluvium-drt had one and refused
a tag that existed; diluvium spelled tags a third way. The same tag was
releasable in one repository and rejected in the next, and a run that
died of infrastructure could be re-run in one and needed a fresh
version number in another. It is settled one way here: an existing tag
is a re-run and the release is updated in place, unless it points at a
different commit than the one being built.

### Added

- `.github/workflows/release-preflight.yml` and
  `release-publish.yml`, called by a consuming repository's own
  `release.yml`. They install the engine from the commit they were
  themselves read from (`github.job_workflow_sha`), so the tool and
  the workflow are one version by construction and a repository has
  one pin to keep, not two.
- `technoproj release` -- `plan`, `preflight`, `doctor`,
  `check-workflow` and `cut`. `preflight` runs every gate CI runs, on
  a workstation, so a release that would fail does so in seconds
  rather than ten minutes into a build.
- `TECHNO_RELEASE` in `.technoproj`: the workflow's file name, the
  release title, the artifact pattern, and the registry leg. Every
  field has a default, so most repositories declare three lines.
- `technoproj-changelog buildinfo --tag`, the entry's compatibility
  facts as `key: value` lines. dollup grew this in its fork, aloelite
  wrote it again in shell and diluvium-drt a third time; the release
  page and BUILDINFO.txt now come from one renderer and cannot
  disagree.
- `doc/STANDARD.md`, the document a project is pointed at: the
  changelog schema and the release action in one place. Every example
  in it is extracted and run against the engine by
  `tests/test_doc_examples.py` -- the entry validates, its `stamps`
  example is shown failing when the file disagrees, the caller passes
  `check-workflow`, and the version it tells a project to pin is
  checked against this package's own. Documentation is checked rather
  than trusted, for the same reason `version.mk` is.
  It carries the whole of it -- the changelog schema, the release
  action, how to cut one, and the adoption checklist -- and is
  vendored byte-identical, like `ALIGNMENT.md`, so "how do I release
  this project" has one answer everywhere.

### Changed

- `release-check` now prints `dev=` for every tag, not only where a
  caller worked it out for itself, and resolves a `-dev.<n>` tag
  against the newest entry rather than demanding one of its own. It
  refuses a dev tag whose `X.Y.Z` the changelog has not reached: that
  is a mis-stamped tree, not a release.

### Fixed

- `technoproj release doctor` reports the `contents: none` trap:
  naming any permission drops every unnamed one, so a job asking only
  for `id-token: write` has no `contents` at all. Four repositories
  are sitting on it. It is harmless while such a job only uploads to a
  registry, and the first checkout or release step added to it fails
  with a 403 that reads like an organisation policy problem.

### Known issues

- Adoption is per repository and none has landed yet; `technoproj
  release doctor` lists what each one is missing. diluvium needs its
  `TECHNO_CHANGELOG` block before any of this applies to it, and its
  `v5.5.1_buildN` tags are not the standard scheme.


## [0.2.0] - 2026-09-12

`v0.2.0`

The status board's collector ships inside the package, so a host gets
it by installing technoproj rather than by a second copy rsynced into
the fleet.

0.1.0 could not do this: it has no `technoproj/status.py`, so an
install pinned at that tag resolves `-m technoproj.status` to nothing.
Any host deploying the board needs this version or later.

### Added

- `technoproj-status-collect`, and `technoproj.status` as a module, so
  the collector can be run either way.
- `technoproj/profiles/` as package data -- one copy, read by the
  installed collector and by `status/build.sh` alike.

### Changed

- `status/collect.py` is now a three-line shim onto the package, kept
  so `status/` still runs straight from a checkout.


## [0.1.0] - 2026-09-12

`v0.1.0`

One changelog engine and one `version.mk`, with everything
repository-specific declared in that repository's `.technoproj`
rather than forked into a copy.

Verified against the three repositories it replaces: from its
declaration alone the engine reproduces diluvium's and DRT's
committed `changelog.json` byte for byte, and all three
`CHANGELOG.md` files identically but for one intended line.

### Added

- `technoproj-changelog`, argument-for-argument compatible with the
  `script/changelog.py` it replaces.
- `technoproj sync` / `check`, which place `script/version.mk` and
  fail when the copy has drifted. The fragment cannot travel as an
  installed command because `make` must read it with no network and
  no virtualenv active, so the copy is checked rather than trusted.
- `technoproj dollup-manifest`, which builds a dollup package from a
  `TECHNO_DOLLUP` declaration: hashes computed rather than typed, and
  a `source` block recording repo, commit and ref. A dirty tree is
  refused rather than recorded quietly.
- `technoproj show`, the version in every spelling it has.
- `status/`, an activity, build and release board on the site
  contract, with collection-time profile filtering and a public
  profile that omits rather than hides.
