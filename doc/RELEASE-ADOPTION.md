# Release adoption

Where each repository stands against [`STANDARD.md`](STANDARD.md). Produced
by `technoproj release doctor` in each tree, not from memory; re-run it rather
than trusting this table's age.

| repository | `TECHNO_CHANGELOG` | `CHANGELOG.yaml` | forked `changelog.py` | `version.mk` | release workflow | contract problems | permission traps |
|---|---|---|---|---|---|---|---|
| `aloelite` | yes | yes | no | yes | yes | **4** | 1 |
| `diluvium-drt` | yes | yes | **yes** | **no** | yes | **2** | 0 |
| `dollup` | yes | yes | **yes** | yes | yes | **2** | 0 |
| `diluvium` | **no** | yes | **yes** | **no** | yes | **2** | 0 |
| `xtrshow` | yes | yes | no | yes | **no** | — | 1 |
| `aloeschema` | yes | yes | no | yes | **no** | — | 1 |
| `aloecrypt_js` | **no** | **no** | no | yes | **no** | — | 1 |

Read the columns as work, in this order. Nothing below depends on a
repository being released first; each line is independently useful.

## 1. Three repositories still carry a forked `script/changelog.py`

`diluvium-drt`, `dollup` and `diluvium` each have one, and they are 549, 689
and 442 lines against the engine's 643. This is the failure technoproj was
built to end, recurring one layer up: the forks are not stale copies, they
have *grown different features*. `dollup`'s learned `buildinfo` and a `dev=`
output; `aloelite` wrote the same two things again in workflow shell;
`diluvium-drt` a third way. All three are now in the engine, verified
byte-identical against `dollup`'s output, so the forks can go.

`diluvium` needs its `TECHNO_CHANGELOG` block before any of this reaches it.
Its tags are also `v5.5.1_buildN`, which is not the scheme in `ALIGNMENT.md`
§1 — worth settling deliberately rather than as a side effect of this work.

## 2. Three repositories have no release workflow at all

`xtrshow`, `aloeschema` and `aloecrypt_js` publish to PyPI or npm from
`publish.yml` and produce no GitHub release. The registry leg is fine where
it is and **must stay there** — trusted publishing matches the OIDC claim
against a workflow filename in the publishing repository, so moving the
upload into a shared workflow breaks it, and renaming the file means
re-registering the publisher first.

**Adding a `release.yml` beside it is not the whole change**, which is what
this said before [#6](https://github.com/Aloecraft-org/technoproj/issues/6).
All three trigger that leg on a tag push, and the tag a release creates is
made by `GITHUB_TOKEN`, which starts no workflow run. Adopting without the
hand-off switches publishing off silently. Each needs `workflow_dispatch`
with a `tag` input added to `publish.yml`, `registry-workflow` passed from
the publish job, and `actions: write` on it — `check-workflow` fails until
all three are there. None of the three has a usable manual fallback today
either: `xtrshow` and `aloecrypt_js` have no `workflow_dispatch` at all, and
`aloeschema`'s takes no inputs, so it can only build whatever the default
branch is at.

`aloecrypt_js` has no `CHANGELOG.yaml`, so its release notes would be a tag
name. The release gate is off without one and `doctor` says so, rather than
the tooling pretending otherwise.

## 3. The four existing release workflows disagree on the release's identity

Not on how to build — on what a release *is*:

| | `tag` input | a tag that already exists |
|---|---|---|
| `aloelite` | none; `ref` must already be a tag | required |
| `dollup` | yes | **refused** |
| `diluvium-drt` | yes | **refused** |
| `diluvium` | yes, spelled `v5.5.1_buildN` | **refused** |

So the same tag was releasable in one repository and rejected in the next,
and a run that died of infrastructure could be re-run in one and needed a
fresh version number in another. The shared preflight settles it: an existing
tag is a re-run and the release is updated in place, unless it points at a
different commit than the one being built.

## 4. The `contents: none` trap

Four repositories have a job that names `id-token` and no `contents`, which
silently means `contents: none`. None of them is broken by it today — those
jobs only download artifacts and upload to a registry. Each is one added
checkout or release step away from a 403 that reads like an organisation
policy problem. One line each.
