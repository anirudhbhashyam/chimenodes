#!/bin/sh
# Regenerate every showcase image in docs/assets (stills, stock/chimenodes pairs, hero, gallery).
#
#   tools/showcase/render.sh [--chimerax PATH] [--out DIR] [--scenes er,sav,abl,barn,rbd,gallery]
#
# Opens the ChimeraX GUI once (rendering needs a GL context) and fetches the PDB entries from RCSB
# the first time. Exits non-zero if ChimeraX is missing or any scene failed; see <out>/report.json.
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
CX="${CHIMERAX_EXE:-}"
OUT="$ROOT/docs/assets"
SCENES=""
while [ $# -gt 0 ]; do
    case "$1" in
        --chimerax) CX="$2"; shift 2 ;;
        --out)      OUT="$2"; shift 2 ;;
        --scenes)   SCENES="$2"; shift 2 ;;
        -h|--help)  sed -n '2,8p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

if [ -z "$CX" ]; then
    for c in /Applications/ChimeraX*.app/Contents/MacOS/ChimeraX \
             "$HOME"/Applications/ChimeraX*.app/Contents/MacOS/ChimeraX \
             /usr/bin/chimerax /usr/local/bin/chimerax /opt/UCSF/ChimeraX*/bin/ChimeraX; do
        [ -x "$c" ] && CX="$c"
    done
fi
[ -n "$CX" ] && [ -x "$CX" ] || { echo "ChimeraX not found; pass --chimerax PATH or set CHIMERAX_EXE" >&2; exit 1; }

mkdir -p "$OUT"
rm -f "$OUT/report.json"
CHIMENODES_ASSETS="$OUT" CHIMENODES_SCENES="$SCENES" CHIMENODES_SRC="$ROOT/src" \
    "$CX" --exit --script "$ROOT/tools/showcase/render_showcase.py" </dev/null >/dev/null 2>&1 || true

[ -f "$OUT/report.json" ] || { echo "no report.json written: ChimeraX did not run the script" >&2; exit 1; }
python3 - "$OUT/report.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
print("ChimeraX %s, chimenodes %s" % (r.get("chimerax", "?"), r.get("chimenodes", "?")))
bad = 0
for k, v in r.get("scenes", {}).items():
    print("  %-8s %s %.1fs" % (k, "ok  " if v["ok"] else "FAIL", v.get("secs", 0)))
    bad += 0 if v["ok"] else 1
if r.get("crash"):
    print(r["crash"]); bad += 1
sys.exit(1 if bad else 0)
PY
