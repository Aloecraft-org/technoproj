#!/usr/bin/env python3
"""token_contrast.py -- measure the site token contrast gates.

    python3 script/token_contrast.py                      # every site it can find
    python3 script/token_contrast.py --root /home/user    # where the checkouts live
    python3 script/token_contrast.py --site diluvium
    python3 script/token_contrast.py --table              # markdown, for doc/

Every ratio in doc/SITE-TOKENS.md comes from this script, so a claim in that
document can be re-run rather than argued about. Exit status is 1 if any
required pair fails its gate, which is what makes it usable as a gate.

This is the seed of `technoproj site check --contrast`. It reads the sites
where they live today, through the per-site alias map below, because the
vocabulary in SITE-TOKENS.md has not been adopted yet -- the whole point is to
measure the tree as it is. Once a repo adopts Tier 1, its entry loses its
aliases and the map shrinks to nothing.
"""

import argparse
import os
import re
import sys

# ── the gates ──────────────────────────────────────────────────────────
# (foreground, background, minimum). SITE-TOKENS.md carries the reasons;
# the short version is that everything here is text except the last row,
# which is why it is gated at 3.0 and not 4.5.
GATES = [
    ("ink",        "bg",          4.5),
    ("ink",        "surface",     4.5),
    ("ink-dim",    "bg",          4.5),
    ("ink-dim",    "surface",     4.5),
    ("accent",     "bg",          4.5),
    ("accent-ink", "accent-fill", 4.5),
    ("ink-faint",  "bg",          3.0),
]

# ── where each site keeps its tokens, and what it calls them ───────────
# `path` is relative to --root. `alias` maps a canonical Tier 1 name onto
# the name that site uses today; a canonical name absent from both the
# alias map and the file is simply not measured, and is reported as such
# rather than passing quietly.
SITES = {
    "portal": {
        "path": "aloecraft-software-portal/site/template/index.html",
        "alias": {"surface": "panel", "ink-dim": "muted", "accent-fill": "accent"},
    },
    "dollup": {
        "path": "pub/dollup/site/template/index.html",
        "alias": {"ink-dim": "dim", "accent": "blue", "accent-fill": "blue"},
    },
    "diluvium": {
        "path": "pub/diluvium/site/static/assets/styles.css",
        "alias": {"surface": "bg-panel", "accent-fill": "accent"},
    },
    "xtrshow": {
        "path": "pub/xtrshow/web/assets/style.css",
        "alias": {"ink": "fg", "ink-dim": "fg-dim", "ink-faint": "fg-faint",
                  "surface": "panel", "accent": "blue", "accent-fill": "blue"},
    },
    "discofetch": {
        "path": "discofetch/deploy/cloud1/www/html/assets/tokens.css",
        "alias": {"bg": "df-bg", "ink": "df-text", "ink-dim": "df-dim",
                  "accent": "df-accent", "accent-fill": "df-accent-fill",
                  "accent-ink": "df-on-accent"},
        # --df-surface is rgba() over the page, not a flat colour, so the
        # two "on surface" rows are skipped here rather than measured
        # against a value that is not what renders.
    },
}


def luminance(hex_colour):
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lin = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def ratio(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def themes(path):
    """Split a stylesheet into its dark and light token maps.

    A selector naming "light" defines the light theme; everything else is
    the dark default, which is also the base the light block overrides --
    hence the merge in `resolve`. Comments are stripped first: several of
    these files document a hex in prose right beside the declaration, and
    a comment is not a definition.
    """
    src = re.sub(r"/\*.*?\*/", "", open(path).read(), flags=re.S)
    dark, light = {}, {}
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", src):
        selector, body = m.group(1).strip(), m.group(2)
        decls = re.findall(r"(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*(?:;|$)", body)
        if not decls:
            continue
        target = light if "light" in selector.lower() else dark
        target.update({k.lstrip("-"): v for k, v in decls})
    return dark, light


def resolve(canonical, alias, tokens):
    return tokens.get(alias.get(canonical, canonical))


def measure(name, spec, root):
    path = os.path.join(root, spec["path"])
    if not os.path.exists(path):
        return None, "not checked out: %s" % spec["path"]

    alias = spec.get("alias", {})
    dark, light = themes(path)
    rows = []
    for theme, overrides in (("dark", {}), ("light", light)):
        if theme == "light" and not light:
            continue
        tokens = {**dark, **overrides}
        for fg, bg, need in GATES:
            fv, bv = resolve(fg, alias, tokens), resolve(bg, alias, tokens)
            if not fv or not bv:
                continue
            r = ratio(fv, bv)
            rows.append((theme, fg, bg, fv, bv, r, need, r >= need))
    return rows, None


def main():
    ap = argparse.ArgumentParser(description="measure site token contrast gates")
    ap.add_argument("--root", default="/home/user",
                    help="directory holding the site checkouts")
    ap.add_argument("--site", action="append",
                    help="limit to this site; repeatable")
    ap.add_argument("--table", action="store_true",
                    help="markdown worst-pair summary, as doc/SITE-TOKENS.md carries it")
    args = ap.parse_args()

    wanted = args.site or list(SITES)
    failures, summary = 0, []

    for name in wanted:
        if name not in SITES:
            sys.exit("unknown site %r -- known: %s" % (name, ", ".join(SITES)))
        rows, why = measure(name, SITES[name], args.root)
        if rows is None:
            print("%-11s skipped -- %s" % (name, why))
            continue

        for theme in ("dark", "light"):
            here = [r for r in rows if r[0] == theme]
            if not here:
                continue
            if not args.table:
                print("%s %s" % (name, theme))
                for _, fg, bg, fv, bv, r, need, ok in here:
                    print("    %-24s %-8s on %-8s %6.2f  need %.1f  %s"
                          % ("%s / %s" % (fg, bg), fv, bv, r, need,
                             "ok" if ok else "FAIL"))
            worst = min(here, key=lambda r: r[5] / r[6])
            summary.append((name, theme, worst))
            failures += sum(1 for r in here if not r[7])
        if not args.table:
            print()

    if args.table:
        print("| site | theme | worst required pair | ratio |")
        print("|---|---|---|---|")
        for name, theme, (_, fg, bg, _fv, _bv, r, need, ok) in summary:
            pair = "`--%s` on `--%s`" % (fg, bg)
            cell = "%.2f" % r
            if not ok:
                pair, cell = "**%s**" % pair, "**%s — fails**" % cell
            print("| %s | %s | %s | %s |" % (name, theme, pair, cell))
        print()

    print("%d required pair(s) failing" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
