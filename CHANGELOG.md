# Changelog

All notable changes to technoproj are recorded here.

Generated from `CHANGELOG.yaml`, which is the source of truth --
edit that file, then run `technoproj-changelog generate`.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
