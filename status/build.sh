#!/bin/sh
# Build the status board into --out. On the Aloecraft site contract:
# offline, hermetic, idempotent, clears its output first, and never deploys.
#
#   ./status/build.sh [--out DIR] [--profile NAME]
#
# --profile only stamps the page for a human reading the source; it selects
# nothing. What a profile publishes is decided by collect.py at collection
# time, not here and not in the browser.
#
# The built tree is static and carries no data. `data/status.json` is written
# on the box by collect.py under autoserv, which is why `data/` is declared
# server-generated in sites.json and stays off deploy.py's --delete.
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUT="$HERE/_out"
PROFILE="internal"

while [ $# -gt 0 ]; do
    case "$1" in
        --out)     OUT="$2"; shift 2 ;;
        --out=*)   OUT="${1#--out=}"; shift ;;
        --profile) PROFILE="$2"; shift 2 ;;
        --profile=*) PROFILE="${1#--profile=}"; shift ;;
        -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "build.sh: unknown argument $1" >&2; exit 2 ;;
    esac
done

# One copy of the profiles, in the package, because the collector reads them
# there when installed. Two copies would be the drift this repository exists
# to end.
PROFILES="$HERE/../technoproj/profiles"
if [ ! -f "$PROFILES/$PROFILE.json" ]; then
    echo "build.sh: no profile '$PROFILE' in $PROFILES/" >&2
    exit 2
fi

# Clear first. A file left over from a previous build is a file lk_web will
# faithfully deploy.
rm -rf "$OUT"
mkdir -p "$OUT"

cp "$HERE/template/index.html" "$OUT/index.html"
cp "$HERE/template/style.css"  "$OUT/style.css"
cp "$HERE/template/app.js"     "$OUT/app.js"

# The directory the collector writes into has to exist in the deployed tree,
# or the first page load 404s until the first collection. A placeholder that
# says so beats an empty directory that looks like a bug.
mkdir -p "$OUT/data"
cat > "$OUT/data/status.json" <<EOF
{
  "schema": 1,
  "profile": "$PROFILE",
  "title": "Status",
  "generated_at": null,
  "sources": [
    {"name": "collector", "ok": false, "fetched_at": null,
     "note": "placeholder shipped by build.sh -- collect.py has not run on this host yet"}
  ],
  "projects": []
}
EOF

# Guard the page's own load-bearing details, the way dollup's site/check.py
# does: these are invisible when lost and the page still renders.
for needle in 'id="rows"' 'id="freshness"' 'id="sources"' 'data/status.json'; do
    if ! grep -qF "$needle" "$OUT/index.html" "$OUT/app.js"; then
        echo "build.sh: built page is missing $needle -- refusing to ship it" >&2
        exit 1
    fi
done
if grep -qiE 'https?://(cdn|fonts|unpkg|ajax)' "$OUT/index.html" "$OUT/app.js" "$OUT/style.css"; then
    echo "build.sh: the page gained an external request -- a status board must" >&2
    echo "          render when the internet does not. Inline it instead." >&2
    exit 1
fi

echo "built $PROFILE -> $OUT"
