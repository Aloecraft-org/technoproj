# The operating layout

**Point a repository at this document when an agent will operate it.** It
is the layout an owner and an agent operator share: where the agent
thinks, what the owner reads, what both treat as agreed, and what the agent
may do without asking. It was worked out in
the private repository where an agent operates Aloecraft's commercial
work, and is published here so every repository adopts it from one place.

```sh
pip install "git+https://github.com/Aloecraft-org/technoproj@v0.4.1"
technoproj lockstep init --owner aloecraft   # place what is missing
technoproj lockstep check                    # every gap, in fix order
```

`init` never overwrites a file. `check` exits 1 while any gap remains, so
it goes in CI once the owner has filled in the scaffold. A repository that
already has some of this follows
[`LOCKSTEP-MIGRATION.md`](LOCKSTEP-MIGRATION.md).

## The four places

| path | job | who writes it |
|---|---|---|
| `.claude/` | the agent's brain: rules, log, drafts, notes | the agent, freely |
| everything else | functional: code, scripts, config, tests | through pull requests |
| documentation outside `.claude/` | a human surface | through pull requests |
| `doc/lockstep/` | the agreed truth between owner and agent | true once the owner merges it |

No product code reads from `.claude/`. The rule text is
`.claude/rules/lockstep.md`.

## The files

```
.claude/CLAUDE.md                  what this repo is, who the owner is
.claude/log.md                     one entry per run; append only
.claude/rules/operating.md         shared: the run protocol
.claude/rules/lockstep.md          shared: the four places
.claude/rules/human-surfaces.md    shared: writing for the maintainer and the human
.claude/rules/*.md                 this repo's own rules, such as ui-copy.md
doc/lockstep/README.md             index of the files below
doc/lockstep/authority.yaml        what the agent may do
doc/lockstep/sources.yaml          where product truth lives
doc/lockstep/goal.md               the one number
doc/lockstep/roadmap.md            iterations and their gates
doc/lockstep/queue.md              work assigned to the owner
doc/lockstep/ledger.md             experiments
doc/lockstep/dispatch.md           asks this repo sends to other repos
.github/CODEOWNERS                 the owner reviews lockstep and rules
.github/rulesets/main.json         import source for the main-branch ruleset
```

**Shared** files are the same in every repository. `sync` writes them and
`check` compares them byte for byte, the bargain `version.mk` makes. A
change to one is proposed here, released, and synced into each repository
as a `PROPOSAL:` pull request. A repository adds rules of its own as other
files in `.claude/rules/`; `check` ignores them.

**Scaffold** files are the repository's own. `init` writes each once, with
`technoproj: fill in` where the owner has to decide something, and `check`
reports any file still carrying that marker or `@OWNER`.

## Authority

`authority.yaml` sorts every action into `autonomous`, `approve_first` or
`never`. An action not listed is `approve_first`.

The **self_merge lane** is the one place the agent commits to `main`
without a pull request: its own notes and log under `.claude/`, and a new
item appended to `queue.md` or `dispatch.md`. `.claude/CLAUDE.md` and `.claude/rules/` are
excepted, every commit starts with `self-merge:`, and the run's log entry
names it. `check` fails if the lane reaches `CLAUDE.md`, a shared rule,
`authority.yaml`, `goal.md` or `roadmap.md`, because the agent cannot
widen its own authority.

`limits` sets `subagents_per_run`, `spend_usd` and `run_minutes` (the
length of a batch).

## Pull requests

| change | pull request |
|---|---|
| inside self_merge | none; commit to `main` |
| `.claude/CLAUDE.md`, `.claude/rules/`, `authority.yaml`, `goal.md` | its own, titled `PROPOSAL: ...`, on the run branch plus `-proposal` |
| anything else | one per run, on `run/YYYY-MM-DD-slug` or the branch the session assigns |

A pull request that changes a file in `doc/lockstep/` links each changed
file at its head commit (`blob/<full sha>/<path>`), so the owner reads the
revision they would merge rather than whatever `main` holds. The rule text
is in `.claude/rules/lockstep.md`.

CODEOWNERS names the owner on `doc/lockstep/`, `.claude/CLAUDE.md`,
`.claude/rules/` and itself.

## The run

The owner says **Run.** for one run or **Batch.** for several steps up to
`limits.run_minutes`. Either way the agent reads lockstep, works only on
the first roadmap iteration not marked `done`, queues anything that needs
the owner with the artifact already prepared, and opens pull requests.
Only the owner marks an iteration `done`. The steps are in
`.claude/rules/operating.md`.

## Dispatch

No operator writes another repository to get work done there. It
appends an item to its own `dispatch.md`, addressed by the target's
dispatch name. A router, itself a repository running this layout, reads
every outbox and copies each item to the target's inbox. The target's
next run does the item or queues it for its owner, then appends a reply
to its own `dispatch.md`. Nothing in the chain writes outside its own
repository, and an item carries the owner's word only through its
`Approval:` link.

```yaml
dispatch:                            # in sources.yaml
  name: example                      # what other repositories write after To:
  outbox: doc/lockstep/dispatch.md
  inbox: {repo: owner/router, path: dispatch/example.md}   # or: issues
```

`check` requires the block and reads every item's header and fields; the
item format is in the scaffold's `dispatch.md`.

## Public repositories

In a public repository all of this is public, `.claude/log.md` and
`.claude/` drafts included. The goal, the ledger and the queue say what
the owner is trying to do and what they have not done yet. A repository
whose goal or notes should not be read by everyone runs the layout in a
private repository and points `sources.yaml` at the public one.
A public repository sets `inbox: issues`, so its sources name no
private router; asks reach it as issues labelled `dispatch`, opened
from the owner's account.

## The declaration

A repository with no `.technoproj` gets the defaults. To change them:

```json
{
  "TECHNO_LOCKSTEP": {
    "surfaces": ["README.md", "doc/", "examples/"]
  }
}
```

| field | meaning | default |
|---|---|---|
| `surfaces` | the declared human surfaces, rendered into `human-surfaces.md` | `README.md`, `doc/`, `examples/` |

## In CI

```sh
technoproj lockstep check
```
