# technoproj

Shared release tooling for Aloecraft projects: **one changelog engine and one
`version.mk`**, with everything repository-specific declared in that
repository's `.technoproj` rather than forked into a copy.

> **Setting up a project?** [`doc/STANDARD.md`](doc/STANDARD.md) is the one
> document to read: how to write a consistent changelog, and the release
> action that goes with it.

Before this existed, `changelog.py` was 423 / 484 / 576 lines in diluvium /
diluvium-drt / aloelite — one tool, copied twice, then drifted. `version.mk`
was byte-identical in aloelite and xtrshow and Cargo-shaped in both,
including the one with no Cargo.

The divergence between those three copies turned out to be **a schema and a
fact table, not logic**. That is what makes one engine possible.

## Install

```sh
pip install git+https://github.com/Aloecraft-org/technoproj@v0.2.0
```

Always pin a tag. A release pipeline that tracks `main` is a release pipeline
that changes when nobody touched it.

## What a consuming repository does

```sh
technoproj sync                      # place script/version.mk
technoproj show                      # this repo's version, every spelling
technoproj release doctor            # what this repo still needs
technoproj-changelog validate        # schema + consistency
technoproj-changelog generate        # write CHANGELOG.md and changelog.json
```

`technoproj-changelog` is argument-for-argument compatible with the
`script/changelog.py` it replaces, so migrating is a change of command name,
not of usage. In CI:

```sh
technoproj check                     # version.mk has not drifted
technoproj release check-workflow    # the release workflow still conforms
technoproj-changelog check           # the generated files match the YAML
technoproj-changelog consistency     # the tree agrees with the newest entry
technoproj-changelog release-check --tag "$TAG" --publish
```

## Releasing

One process, in every repository:

```sh
technoproj release plan            # what a release of this tree would be
technoproj release preflight       # every gate CI runs, run here first
technoproj release doctor          # what is missing, and which route is open
technoproj release cut --tag v0.3.0 --publish --yes
```

The halves of a release that were never meant to differ between projects are
two reusable workflows here — the tag decision and the changelog gate, then
`BUILDINFO.txt`, `SHA256SUMS.txt`, the notes and the release itself. A
consuming repository's `release.yml` calls them and keeps only its build
jobs:

```yaml
  preflight:
    uses: Aloecraft-org/technoproj/.github/workflows/release-preflight.yml@v0.3.0
  publish:
    permissions:
      contents: write        # the caller grants it; a called workflow cannot
    uses: Aloecraft-org/technoproj/.github/workflows/release-publish.yml@v0.3.0
```

There is one pin to keep, not two: the shared workflows install the engine
from the commit they were themselves read from, so the tool and the workflow
cannot end up different versions.

**The workflow creates the tag; nobody pushes one.** That is the whole of the
permissions story. `contents: write` on one job is a permission the
repository grants itself and can be read back from the file; the right to
push `refs/tags/*` varies by person, by machine, by automation session and by
tag ruleset, and no repository setting makes it uniform. `technoproj release
doctor` says which route is open before anything is attempted.

A repository declares what is its own in `TECHNO_RELEASE` -- the workflow's
file name, the release title, the artifact pattern, the registry leg. Every
field has a default; see `examples/release.json` for the three shapes the
fleet has.

**[`doc/STANDARD.md`](doc/STANDARD.md) is the document to point a project
at** — the changelog schema and the release actions, with every example in it
verified against the engine by `tests/test_doc_examples.py` rather than
asserted. [`doc/RELEASING.md`](doc/RELEASING.md) is the runbook for cutting a
release once a project is set up, and
[`doc/RELEASE-ADOPTION.md`](doc/RELEASE-ADOPTION.md) tracks where each
repository stands. All are vendored byte-identical, like `ALIGNMENT.md`.

### Why `version.mk` is copied rather than imported

`make` has to read it with no network and no virtualenv active, so it lives
in the consuming repo at `script/version.mk`. `technoproj sync` places it and
`technoproj check` fails when the copy has drifted — the copy is checked
rather than trusted, which is the failure this package exists to end.

## The declaration

Everything that differs between repositories goes in `.technoproj` under
`TECHNO_CHANGELOG`. See `examples/` for the three real ones.

```json
{
  "TECHNO_VERSION": {
    "major": 0, "minor": 4, "patch": 0,
    "pre": { "kind": "rc", "n": 1 }
  },
  "TECHNO_CHANGELOG": {
    "project": "DRT",
    "facts": [
      {"id": "dv_abi", "keys": ["dv_abi"], "fmt": "dv ABI {dv_abi}"}
    ],
    "mappings": [{"key": "connectors", "title": "Connectors"}],
    "tag_rule": "exact",
    "emit_json": true,
    "stamps": [
      {"file": "Cargo.toml", "find": "version\\s*=\\s*\"([^\"]+)\"",
       "spelling": "semver"}
    ]
  }
}
```

| field | meaning |
|---|---|
| `project` | display name in the generated `CHANGELOG.md` preamble |
| `intro_extra` | repo-specific text after the Keep a Changelog line |
| `facts` | compatibility facts, in render order. A fact renders when every key it names is present; the first variant matching a given `id` wins |
| `mappings` | profile → list blocks, e.g. DRT's connectors and features |
| `tag_rule` | `exact` (tag is `v{version}`), `prefix` (starts with `v`), `derive` (fall back to `v{version}`) |
| `required` | keys every entry must carry |
| `latest_requires` | keys the `latest: true` entry must carry |
| `candidates` | release candidates listed under a release |
| `planned` | a top-level `planned` section |
| `emit_json` | generate `changelog.json` — required for a `source: changelog` release mirror |
| `stamps` | generic version-location checks: a file, a pattern, and which spelling it should hold |

`stamps` is how a repository stops its version drifting across several
files. To be exact about the promise: it **checks**, it does not write — the
only files this package writes are `CHANGELOG.md`, `changelog.json` and
`script/version.mk`. So the number is still typed in each place, and CI
fails when the places disagree. That is a real improvement over silent
drift, and it is a smaller claim than "stop hand-typing it". xtrshow keeps
the same version in four files today with nothing checking them.

### `TECHNO_VERSION.pre`

`null` for a release, or `{"kind": "dev|alpha|beta|rc", "n": <int>}`. This
replaces the old `build` field, which meant a PEP 440 suffix in aloelite, an
off switch in xtrshow and a build counter in diluvium — one field, three
meanings, two types.

## What stays in the repository

Bespoke invariants do not generalise and are not forced into config. A
repository declares them in `script/checks.py`:

```python
def consistency(doc, ctx):
    """ctx carries read(path), root and base (the X.Y.Z version)."""
    bad = []
    fmt = ctx["read"]("src/lundump.h")
    ...
    return bad
```

The engine calls it if the file exists. Current examples: diluvium's
`LUAC_FORMAT` and `LUA_VERSION_*`, DRT's `Cargo.lock` diluvium pin,
aloelite's `SCHEMA_ERA`, aloeschema's vendored schema.org release.

## Verification

The engine reproduces each repository's committed output from its
declaration alone — `CHANGELOG.md` and `changelog.json`, byte for byte,
across diluvium (112,770 + 234,253 bytes), diluvium-drt (173,306 + 362,887)
and aloelite (33,001).

The single intended difference: the generated preamble now names
`technoproj-changelog generate` rather than `script/changelog.py generate`,
so the first `generate` after migrating produces a one-line diff.

**If anything else in your output changes, the declaration is wrong — not the
engine.**

## dollup packages

A library distributed through a dollup repo declares `TECHNO_DOLLUP` beside
its version, and the package is generated rather than hand-written:

```sh
technoproj dollup-manifest --out ../std-repo
# -> ../std-repo/packages/token-bucket/0.1.0/{manifest.json,guest/…}
```

It computes the `files` hashes instead of having someone type them, takes the
version from `TECHNO_VERSION` so it agrees with the tag, and adds a **`source`
block** the format did not previously carry:

```json
"source": {
  "repo":   "https://github.com/Aloecraft-org/token-bucket-lib",
  "commit": "0603050ce2fbe89fb04b6e67c9004ffa6810cfb8",
  "ref":    "v0.1.0"
}
```

Without it a published package cannot be traced back to the tree it came
from — the provenance `BUILDINFO.txt` gives a binary release. A dirty tree is
refused rather than recorded quietly, because a manifest naming a commit
whose files differ from what was hashed reads as provenance and is not.

`guest.main` is omitted for a library; its absence is what says so
(RepoFormat §5). See `technoproj/dollup.py` for the declaration shape.

## The version scheme

`v<major>.<minor>.<patch>[-<kind>.<n>]`, `kind ∈ dev | alpha | beta | rc`.
The git tag is canonical; PEP 440 and SemVer spellings derive from it. Two
rules that look like style and are not:

- **`-dev.7`, never `-dev7`.** SemVer compares dot-separated identifiers, so
  `b104 < b2` without the dot — the bug appears at build 10.
- **Never `-b<n>` for a build number.** PEP 440 normalises `0.0.1-b104` to
  `0.0.1b104`, which *is* beta 104. `Version('0.0.1-b104') ==
  Version('0.0.1-beta104')` is `True`.

The full scheme, artifact naming and per-repository migration live in
[`doc/ALIGNMENT.md`](doc/ALIGNMENT.md) — this repository holds the canonical
copy, so a project vendoring it can diff against upstream.
