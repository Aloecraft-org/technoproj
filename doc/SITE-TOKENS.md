# The site token vocabulary

**Draft, 18 Sep 2026.** What every Aloecraft landing page names its colours,
faces and geometry, so that one shared header and footer can render into all
of them and a project still looks like itself.

This decides names and the contrast gates. It does not decide the build
mechanism, the deploy split, or the docs URL shape — those are
[`SITE-STANDARD.md`](SITE-STANDARD.md) when it exists.

Every number below was measured against the committed file it came from, by
`script/token_contrast.py`, so a stale claim can be re-run rather than argued
about. Where a value fails, the failing hex is named.

---

## Why this document exists

Five sites carry a design system. None of them agrees with another on what to
call a colour:

| concept | portal | dollup | diluvium | xtrshow | discofetch |
|---|---|---|---|---|---|
| page background | `--bg` | `--bg` | `--bg` | `--bg` | `--df-bg` |
| raised surface | `--panel` | `--surface` | `--bg-panel` | `--panel` | `--df-surface` |
| rule / border | `--line` | `--line` | `--line` | `--line` | `--df-line` |
| body text | `--ink` | `--ink` | `--ink` | `--fg` | `--df-text` |
| secondary text | `--muted` | `--dim` | `--ink-dim` | `--fg-dim` | `--df-dim` |
| tertiary text | — | — | `--ink-faint` | `--fg-faint` | — |
| accent | `--accent` | `--blue` | `--accent` | `--blue` | `--df-accent` |
| text on accent | `--accent-ink` | — | `--accent-ink` | — | `--df-on-accent` |
| max content width | — | `--wide` | `--wide` | `--maxw` | `--df-page-max` |
| success | — | `--green` | — | `--green` | `--df-ok` |
| warning | — | — | `--warn` | `--yellow` | `--df-warning` |

Three spellings of body text. Four of the raised surface. Four of secondary
text. Three of max width. Every one of them means exactly the same thing.

**This has already cost something, inside a single repo.** The header of
`discofetch/deploy/cloud1/www/html/assets/tokens.css` records it: `site.css`
and `landing.css` each declared the same nine colours under different names,
a value was retuned in one for measuring 4.43:1 when AA wanted 4.5, and the
old value went on shipping in the other. That file exists because the fix was
to give the two consumers one definition. The fleet is the same failure at
five-way scale, and nothing connects the five.

Two more live inconsistencies, both verified in the committed files:

**The theme choice does not follow a visitor.** Three storage keys:

| site | storage key | attribute | light theme |
|---|---|---|---|
| portal | `aloecraft-theme` | `data-theme` | yes |
| diluvium | `aloecraft-theme` | `data-theme` | yes |
| dollup | `dollup-theme` | `data-theme` | yes |
| discofetch | `df.theme` | `data-bs-theme` + `data-theme` | yes |
| xtrshow | — none — | — none — | **no** |

Set light mode on dollup, walk to diluvium, and it is dark again. Walk to
xtrshow and there is no choice to make.

**`--blue` is a token name that forbids a different brand colour.** dollup
and xtrshow both name their accent after its hue, so diluvium's green accent
cannot be expressed in that vocabulary at all. The same mistake is in
`--green`, `--yellow` and `--red`, which is why the states below are named
`--ok`, `--warn` and `--bad`.

---

## The three tiers

The point of tiering is that **the shared chrome reads Tier 1 and nothing
else.** A project can then carry as many private tokens as its page needs
without the header or footer ever knowing, which is what makes "distinct but
consistent" cost a hex list instead of a fork.

### Tier 1 — core. Required. The only tokens chrome may read.

Fifteen values. A conforming repo defines all of them in both themes.

| token | means | chosen because |
|---|---|---|
| `--bg` | page background | unanimous already |
| `--surface` | raised panel, card | dollup + discofetch; `--panel` reads as a component, and diluvium's `--bg-panel` family wants the `--bg-` prefix left for Tier 2 |
| `--line` | rule, border, divider | unanimous already |
| `--ink` | body text | 3 of 5; and it ladders |
| `--ink-dim` | secondary text, captions | ladders off `--ink`, which `--muted` and `--dim` do not |
| `--ink-faint` | tertiary. **Never body-size text** — see the gates | diluvium and xtrshow invented the same rung independently |
| `--accent` | links, borders, text that carries the brand | 3 of 5; carries no hue |
| `--accent-fill` | the background of a filled button | discofetch is the only site that separates these, and it is right — see below |
| `--accent-ink` | text drawn on `--accent-fill` | portal + diluvium spelling |
| `--shadow` | the one elevation shadow | unanimous among the three that have one |
| `--radius` | the default corner | diluvium + xtrshow agree |
| `--wide` | max content width | 2 of 4; `--maxw` abbreviates nothing worth abbreviating |
| `--sans` | UI stack | unanimous among the three that have one |
| `--mono` | machine text stack | same |
| `--display` | display face. **Defaults to `var(--sans)`** | only discofetch has one, and it is the strongest single distinctness lever a project has |

**On splitting `--accent` from `--accent-fill`.** Only discofetch does this,
and the measurements say the other four are getting away with it rather than
being right. In light mode a link must be dark enough to clear 4.5:1 against
a near-white page, while a filled button wants to stay bright with dark text
on it. One token cannot be both. discofetch light sets `--df-accent: #137D86`
for text and keeps `--df-accent-fill: #4FD8E4` for fills, measuring 4.50:1
and 9.21:1 respectively. portal, diluvium and dollup each use one value for
both and land at 4.78, 4.81 and 5.12 as links — passing only because those
particular hues happen to be mid-dark. A project that picks a light or
saturated accent will fail the moment it tries. Where a project genuinely
wants one value, `--accent-fill: var(--accent)` is a legal one-line answer.

### Tier 2 — extended. Optional, but these names when present.

| token | means | replaces |
|---|---|---|
| `--bg-soft` | second page background, banding | diluvium `--bg-soft`, xtrshow `--bg-2` |
| `--bg-code` | `pre` / code block background | diluvium `--bg-code`, xtrshow `--panel-2`, dollup `--key-bg` |
| `--line-soft` | a rule that should barely read | diluvium `--line-soft`, xtrshow `--line-2` |
| `--ink-bright` | emphasised text above `--ink` | diluvium `--ink-bright` |
| `--accent-dim` | hover and disabled accent | diluvium `--accent-dim`, discofetch `--df-accent-hover` |
| `--ok` | success, live, up | dollup/xtrshow `--green`, discofetch `--df-ok` |
| `--warn` | warning, degraded | diluvium `--warn`, xtrshow `--yellow`, discofetch `--df-warning` |
| `--bad` | error, down | xtrshow `--red`, discofetch `--df-down` |
| `--radius-sm`, `--radius-lg`, `--radius-pill` | the rest of the scale | discofetch's scale |

### Tier 3 — private. Any name, any count. Chrome never reads them.

No constraint, and no migration. These stay exactly as they are:

- diluvium's `--tok-comment`, `--tok-string`, `--tok-keyword`, … — the Prism
  palette, plus the terminal's own dark colours in both themes.
- dollup's `--ripple`, `--ripple-op`, `--chip`, `--key-bg`, `--hero`,
  `--hero-ink`, `--hero-dim`, `--hero-line`, `--keypanel-edge`.
- xtrshow's `--code-size` and `--code-lh`, which the gutter, the highlight
  layer and the textarea must all render identically or the caret drifts.
- discofetch's `--df-tiles`, `--df-glass-*`, `--df-glow-*`, `--df-facet-*`,
  `--df-sheen*`, `--df-drift-*`, and the 74 `--bs-*` Bootstrap variables.

Tier 3 is where a project's character actually lives. Nothing here is being
standardised, and the list above is a promise about that.

---

## The theme contract

One key, one attribute, dark by default.

```
storage key   aloecraft-theme          localStorage, values "dark" | "light"
attribute     data-theme               on <html>
default       dark
```

`prefers-color-scheme` is deliberately not consulted — the ask is a dark
default, not a system-following one, which is what portal, dollup and
diluvium already do and say so in comments.

The pre-paint script moves into shared chrome unchanged, because all three
copies are already the same idea and one of them explains why it must be in
`<head>`: run it later and a light-mode visitor sees a flash of dark on every
load.

Two consumers need an adapter rather than a rewrite:

- **discofetch** keys on `df.theme` and drives Bootstrap's `data-bs-theme`.
  It already sets `data-theme` too (11 occurrences alongside 31 of
  `data-bs-theme`), so the change is the storage key and a second attribute
  write, not a retheme.
- **xtrshow** has no light palette and no toggle. Adopting the contract means
  building a light theme, which is real design work and the one item in this
  document that is not a rename. Until it exists, xtrshow declares
  `data-theme="dark"` and omits the toggle — a site with one theme is
  consistent; a toggle that does nothing is not.

---

## Contrast gates

Required pairs, both themes, checked by `technoproj site check --contrast`:

| pair | minimum | why |
|---|---|---|
| `--ink` on `--bg` | 4.5 | body text |
| `--ink` on `--surface` | 4.5 | body text on a card |
| `--ink-dim` on `--bg` | 4.5 | captions are text |
| `--ink-dim` on `--surface` | 4.5 | same |
| `--accent` on `--bg` | 4.5 | links are text |
| `--accent-ink` on `--accent-fill` | 4.5 | button labels |
| `--ink-faint` on `--bg` | 3.0 | large text and non-text only |

**`--ink-faint` is gated at 3:1 and is not valid for body-size text.** That
rule is doing work rather than describing practice: measured today, a light
theme with three ink rungs that all clear 4.5:1 has almost no room —
diluvium's `--ink-dim` sits at 5.20:1, so a compliant `--ink-faint` would
have to live between 4.5 and 5.2, which is not a visible difference. The rung
is worth having for large type and disabled states. It is not worth having
for a sentence.

### Measured today

`python3 script/token_contrast.py --root /home/user --table`, verbatim.
Everything passes except one row. "Worst" is the smallest margin against a
pair's own gate, not the smallest ratio — a 3.35 at a 3.0 gate is tighter
than a 5.49 at 4.5. Names are canonical, resolved through the alias map in
the script, since no repo has adopted the vocabulary yet.

| site | theme | worst required pair | ratio |
|---|---|---|---|
| portal | dark | `--ink-dim` on `--surface` | 6.89 |
| portal | light | `--accent` on `--bg` | 4.78 |
| dollup | dark | `--ink-dim` on `--surface` | 6.68 |
| dollup | light | `--ink-dim` on `--bg` | 5.09 |
| diluvium | dark | `--ink-faint` on `--bg` | 3.35 |
| diluvium | light | **`--ink-faint` on `--bg`** | **2.93 — fails** |
| xtrshow | dark | `--ink-faint` on `--bg` | 3.74 |
| discofetch | dark | `--ink-dim` on `--bg` | 8.24 |
| discofetch | light | `--accent` on `--bg` | 4.50 |

`--ink-faint` is the worst rung on three of the five sites, which is the
measurement behind the rule above rather than a coincidence. portal has no
`--ink-faint` to measure; discofetch's `--surface` is an `rgba()` over the
page rather than a flat colour, so its two "on surface" rows are skipped
instead of being measured against a value that is not what renders.

**The one failure is in the footer.** `diluvium/site/static/assets/styles.css:359`
is `footer.site .muted { color: var(--ink-faint); }`, which in light mode
draws `#8a939b` on `#f7f8f6` — 2.93:1 for body-size text that needs 4.5.

The fix is the rule above, not a new colour: the footer uses `--ink-dim`
(5.20:1). Darkening `--ink-faint` to `#6a737c` would also clear the gate at
4.53:1, but it spends the whole ladder to keep one footer line on the wrong
rung. **The shared footer will use `--ink-dim`**, so adopting the chrome fixes
this rather than porting it.

Worth noting without treating it as a defect: discofetch light's
`--df-accent` is at 4.50:1 against its background — exactly the line, zero
margin. Its comment on line 342 says `4.50:1`, which is correct. Any future
retune of that hue breaks it, and the gate is what will say so.

---

## Migrating a repo

Use the alias block. discofetch already proved this technique — `landing.css`
aliases nine short names onto the `--df-*` definitions, so its components
never learned the long names:

```css
/* Transitional. Delete when the component rules are renamed.
   technoproj site check warns while this block exists. */
:root {
  --panel:  var(--surface);
  --muted:  var(--ink-dim);
  --blue:   var(--accent);
  --maxw:   var(--wide);
}
```

Adopting the vocabulary is then: define the fifteen Tier 1 tokens with the
values the site already uses, add the alias block, ship. **No component rule
changes and no pixel moves.** The renames happen later, per repo, at whatever
pace suits — and `check` can tell the difference between a repo that has
adopted the vocabulary and one that has finished migrating.

A repo carrying heavy vendor CSS keeps its private prefixed layer. discofetch
should stay `--df-*` internally and alias Tier 1 onto it, exactly as it
aliases today: `--bs-*` is 74 variables of Bootstrap and a generic `--line`
in the same scope is a collision waiting to happen.

### Order

1. **portal** — 16 declarations, no light-theme surprises, and it is the
   declared reference implementation. It also gains the five Tier 1 tokens it
   lacks entirely (`--ink-faint`, `--radius`, `--wide`, `--sans`, `--mono`).
2. **dollup** — 11 declarations, and the newest of the five: `site/` landed on
   `main` in 0.1.1 on 13 Sep. Fewest component rules to rename, so it is the
   cheapest real migration and the one that proves the alias block.
3. **diluvium** — 46 declarations, the largest Tier 3 set, and the footer fix
   lands here.
4. **xtrshow** — rename, then the light palette as separate work.
5. **discofetch** — alias only. Its palette is the most mature of the five
   and the one that already measures itself; it should not be rewritten to
   match sites that are behind it.

---

## What this does not decide

- **The chrome markup.** Which slots exist, what the header and footer
  contain, where the docs and releases links sit.
- **Type scale and spacing.** Only the faces are named here. Sizes are still
  per project, and should stay that way until there is a reason.
- **The logo and mark.** Each project has its own; nothing here touches them.
- **Whether `--display` is worth buying a webfont for.** discofetch ships
  Fraunces, Inter and JetBrains Mono; everyone else is on system stacks. The
  token exists so a project *can* differ, defaulted so that not differing
  costs nothing.
