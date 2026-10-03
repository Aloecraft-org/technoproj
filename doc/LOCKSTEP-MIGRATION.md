# Migrating a repository to the lockstep layout

How an existing repository adopts [`LOCKSTEP.md`](LOCKSTEP.md). Its
`.claude/` and `doc/` are kept; nothing here deletes a file.

The migration changes `.claude/CLAUDE.md` and `.claude/rules/`, so it is one
pull request titled `PROPOSAL: adopt the lockstep layout`, with nothing
else in it. Moving plans out of `doc/` (step 4) is a second pull request.

## 1. Install and declare

```sh
pip install "git+https://github.com/Aloecraft-org/technoproj@v0.3.0"
```

If the repository already has `.claude/rules/human-surfaces.md`, copy its
declared paths into `.technoproj`. A repository with no `.technoproj`
gets `README.md`, `doc/` and `examples/`.

```json
{
  "TECHNO_LOCKSTEP": {
    "surfaces": ["README.md", "examples/", "doc/guides/"]
  }
}
```

## 2. Place the files

```sh
technoproj lockstep init --owner aloecraft
git diff .claude/rules/
```

`init` writes only files that are missing, then rewrites the three shared
rules. Read the diff of `human-surfaces.md`: anything the old copy said
that the shared one does not is either proposed upstream in technoproj or
moved to a rule file of this repository's own. Other files in
`.claude/rules/`, such as a `ui-copy.md`, are not touched.

## 3. Slim CLAUDE.md

`.claude/CLAUDE.md` says what this repository is, who the owner is, and
what every run needs that is specific to it: build and test commands, the
facts source. The run protocol lives in `.claude/rules/operating.md`, so a
CLAUDE.md that already has one ("Every run", "Batches", "Rules") deletes
those sections. If a section differs from `operating.md`, the
difference is either proposed upstream or kept here as a repo rule.

## 4. Move working notes out of doc/

Under the shared `human-surfaces.md`, every prose file outside `.claude/`
is documentation: what is true now or what has been agreed. Plans,
handoffs, session notes, asks and replies move to `.claude/notes/` with
`git mv`, so their history follows them. Anything a reader needs from one
is promoted into the document it belongs in. This is its own pull request,
because it is large and reviewable without the rest.

## 5. Fill in the scaffold

```sh
technoproj lockstep check
```

`check` lists every gap in fix order. The owner fills in `goal.md`,
`sources.yaml` and `owner` in `authority.yaml`, wherever the scaffold says
`technoproj: fill in`, and writes the iteration after I0 in `roadmap.md`.

## 6. The owner's part

- Import `.github/rulesets/main.json` in Settings > Rules > Rulesets.
- Merge the PROPOSAL pull request.
- Mark I0 `done` in `roadmap.md` once `check` passes.

## 7. Keep it from drifting

Add `technoproj lockstep check` to CI. To take a new version of the shared
rules, bump the pin, run `technoproj lockstep sync`, and open the result as
a PROPOSAL pull request.

A repository placed before dispatch existed runs `init` again to get
`doc/lockstep/dispatch.md`, then adds the `dispatch` block to
`sources.yaml` and the `dispatch.md` entry to the self_merge lane, as
the scaffold has them. `check` names the file and the block until both
are there.
