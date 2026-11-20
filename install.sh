#!/bin/sh
# chimenodes installer: MolecularNodes-style rendering + glow for UCSF ChimeraX.
#
#   curl -fsSL <raw-url>/install.sh | sh
#   curl -fsSL <raw-url>/install.sh | sh -s -- --ref v0.1.0
#
# No system Python, uv, pixi, git or compiler is needed: the bundle is built and installed
# by ChimeraX itself using ChimeraX's bundled Python. Requirements: ChimeraX >= 1.8, and
# curl or wget plus tar (only when not using --local).
#
# Options (or environment variables):
#   --chimerax PATH   ChimeraX executable            (CHIMERAX_EXE)
#   --repo URL        GitHub repo URL                (CHIMENODES_REPO)
#   --ref REF         branch, tag or commit          (CHIMENODES_REF, default: main)
#   --local DIR       install from a local checkout instead of downloading
#   --build-only      build the wheel into ./dist, do not install
#   --uninstall       remove chimenodes from ChimeraX
#   --dry-run         find ChimeraX and show what would happen, change nothing
#   -h, --help
#
# ChimeraX itself is NOT downloaded for you: its license must be accepted by you at
# https://www.cgl.ucsf.edu/chimerax/download.html

set -eu

DEFAULT_REPO="https://github.com/anirudhbhashyam/chimenodes"
BUNDLE_NAME="ChimeraX-Chimenodes"
MIN_MAJOR=1
MIN_MINOR=8

REPO="${CHIMENODES_REPO:-$DEFAULT_REPO}"
REF="${CHIMENODES_REF:-main}"
CX="${CHIMERAX_EXE:-}"
LOCAL=""
MODE="install"
DRY=0

say()  { printf '%s\n' "$*"; }
info() { printf '==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

usage() { sed -n '2,24p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//' || true; }

while [ $# -gt 0 ]; do
    case "$1" in
        --chimerax)   [ $# -ge 2 ] || die "--chimerax needs a path"; CX="$2"; shift 2 ;;
        --repo)       [ $# -ge 2 ] || die "--repo needs a URL"; REPO="$2"; shift 2 ;;
        --ref)        [ $# -ge 2 ] || die "--ref needs a value"; REF="$2"; shift 2 ;;
        --local)      [ $# -ge 2 ] || die "--local needs a directory"; LOCAL="$2"; shift 2 ;;
        --build-only) MODE="build"; shift ;;
        --uninstall)  MODE="uninstall"; shift ;;
        --dry-run)    DRY=1; shift ;;
        -h|--help)    usage; exit 0 ;;
        *)            die "unknown option: $1 (try --help)" ;;
    esac
done

# --- locate ChimeraX -------------------------------------------------------------------
newest() {  # print the last path (version-sorted) among the arguments that exist and are executable
    best=""
    for p in "$@"; do
        [ -f "$p" ] && [ -x "$p" ] && best="$p"
    done
    [ -n "$best" ] && printf '%s' "$best"
}

find_chimerax() {
    if [ -n "$CX" ]; then
        # allow a macOS .app bundle path too
        case "$CX" in
            *.app) CX="$CX/Contents/MacOS/ChimeraX" ;;
        esac
        [ -x "$CX" ] || die "ChimeraX not executable at: $CX"
        return 0
    fi
    for name in chimerax ChimeraX ChimeraX-console; do
        if p=$(command -v "$name" 2>/dev/null) && [ -n "$p" ]; then CX="$p"; return 0; fi
    done
    case "$(uname -s)" in
        Darwin)
            # shellcheck disable=SC2046
            CX=$(newest $(ls -d /Applications/ChimeraX*.app "$HOME"/Applications/ChimeraX*.app 2>/dev/null \
                | sort -V | sed 's|$|/Contents/MacOS/ChimeraX|')) || true ;;
        Linux)
            # shellcheck disable=SC2046
            CX=$(newest $(ls -d /opt/UCSF/ChimeraX*/bin/ChimeraX /opt/UCSF/ChimeraX*/bin/chimerax \
                /usr/libexec/UCSF-ChimeraX*/bin/ChimeraX "$HOME"/.local/UCSF/ChimeraX*/bin/ChimeraX 2>/dev/null \
                | sort -V)) || true ;;
        MINGW*|MSYS*|CYGWIN*)
            # shellcheck disable=SC2046
            CX=$(newest $(ls -d "/c/Program Files/ChimeraX"*/bin/ChimeraX-console.exe \
                "/c/Program Files/ChimeraX"*/bin/ChimeraX.exe 2>/dev/null | sort -V)) || true ;;
    esac
    [ -n "${CX:-}" ]
}

no_chimerax() {
    cat >&2 <<'EOF'
error: UCSF ChimeraX was not found on this system.

chimenodes is a ChimeraX plugin, so ChimeraX (>= 1.8) must be installed first:
  1. Download it from https://www.cgl.ucsf.edu/chimerax/download.html
     (free for non-commercial use; you must accept its license yourself)
  2. Install it, then re-run this script. If it is in a non-standard place, point to it:
       curl -fsSL <url>/install.sh | sh -s -- --chimerax /path/to/ChimeraX
     or set CHIMERAX_EXE=/path/to/ChimeraX
No system Python, uv or pixi is required: ChimeraX ships its own Python.
EOF
    exit 1
}

find_chimerax || no_chimerax
info "ChimeraX executable: $CX"

# ChimeraX version, e.g. "UCSF ChimeraX version: 1.11.1 (2026-01-23)"
VER_LINE=$("$CX" --version 2>/dev/null | grep -i "version" | head -n 1 || true)
VER=$(printf '%s' "$VER_LINE" | sed -n 's/.*version:* *\([0-9][0-9]*\.[0-9][0-9]*\(\.[0-9][0-9]*\)*\).*/\1/p')
[ -n "$VER" ] || die "could not determine the ChimeraX version (is '$CX' really ChimeraX?)"
MAJ=${VER%%.*}; REST=${VER#*.}; MIN=${REST%%.*}
if [ "$MAJ" -lt "$MIN_MAJOR" ] || { [ "$MAJ" -eq "$MIN_MAJOR" ] && [ "$MIN" -lt "$MIN_MINOR" ]; }; then
    die "ChimeraX $VER is too old; chimenodes needs >= $MIN_MAJOR.$MIN_MINOR. Update ChimeraX and retry."
fi
info "ChimeraX version: $VER (ok, >= $MIN_MAJOR.$MIN_MINOR)"

# Run a ChimeraX command headless (no window, no GL needed for install/uninstall).
cx_run() { "$CX" --nogui --exit --cmd "$1"; }

# --- uninstall -------------------------------------------------------------------------
if [ "$MODE" = "uninstall" ]; then
    info "Uninstalling $BUNDLE_NAME"
    if [ "$DRY" -eq 1 ]; then say "(dry run) would run: toolshed uninstall $BUNDLE_NAME"; exit 0; fi
    cx_run "toolshed uninstall $BUNDLE_NAME"
    info "Done. Restart ChimeraX if it is running."
    exit 0
fi

# --- get the source --------------------------------------------------------------------
TMP=""
cleanup() { if [ -n "$TMP" ]; then rm -rf "$TMP"; fi; }
trap cleanup EXIT INT TERM

if [ -n "$LOCAL" ]; then
    [ -f "$LOCAL/bundle_info.xml" ] || die "no bundle_info.xml in --local directory: $LOCAL"
    SRC=$(cd "$LOCAL" && pwd)
    info "Using local source: $SRC"
else
    [ -n "$REPO" ] || die "no repository URL configured. Pass --repo https://github.com/<owner>/chimenodes (or --local DIR)."
    REPO=${REPO%/}; REPO=${REPO%.git}
    URL="$REPO/archive/$REF.tar.gz"
    info "Downloading $URL"
    if [ "$DRY" -eq 1 ]; then
        say "(dry run) would download, build and install $BUNDLE_NAME from $URL"; exit 0
    fi
    TMP=$(mktemp -d 2>/dev/null || mktemp -d -t chimenodes)
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$URL" -o "$TMP/src.tar.gz" || die "download failed: $URL"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$TMP/src.tar.gz" "$URL" || die "download failed: $URL"
    else
        die "need curl or wget to download the source"
    fi
    command -v tar >/dev/null 2>&1 || die "need tar to unpack the source"
    mkdir "$TMP/src"
    tar -xzf "$TMP/src.tar.gz" -C "$TMP/src" --strip-components=1 || die "could not unpack the download"
    [ -f "$TMP/src/bundle_info.xml" ] || die "downloaded archive has no bundle_info.xml (wrong --repo/--ref?)"
    SRC="$TMP/src"
fi

# Windows (Git Bash/MSYS): ChimeraX needs a native path
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) command -v cygpath >/dev/null 2>&1 && SRC_NATIVE=$(cygpath -m "$SRC") || SRC_NATIVE="$SRC" ;;
    *) SRC_NATIVE="$SRC" ;;
esac

# --- build / install -------------------------------------------------------------------
if [ "$DRY" -eq 1 ]; then
    if [ "$MODE" = build ]; then
        say "(dry run) would run: $CX --nogui --exit --cmd 'devel build \"$SRC_NATIVE\"'"
    else
        say "(dry run) would run: $CX --nogui --exit --cmd 'devel install \"$SRC_NATIVE\" user true'"
    fi
    exit 0
fi

if [ "$MODE" = "build" ]; then
    info "Building wheel"
    cx_run "devel build \"$SRC_NATIVE\" exit true"
    OUTDIR="$(pwd)/dist"; mkdir -p "$OUTDIR"
    WHL=""
    for w in "$SRC"/dist/*.whl; do
        case "$w" in *editable*) continue ;; esac
        [ -f "$w" ] && WHL="$w"
    done
    [ -n "$WHL" ] || die "build finished but no wheel was produced"
    cp "$WHL" "$OUTDIR"/
    info "Wheel written to $OUTDIR"
    exit 0
fi

info "Building and installing $BUNDLE_NAME (for the current user)"
cx_run "devel install \"$SRC_NATIVE\" user true exit true" \
    || die "installation failed. Re-run with --chimerax PATH if multiple ChimeraX versions exist."

# --- verify ----------------------------------------------------------------------------
info "Verifying"
OUT=$("$CX" --nogui --exit --cmd "usage chimenodes" 2>&1 || true)
case "$OUT" in
    *chimenodes*"Configure"*|*"MolecularNodes-style"*)
        info "chimenodes is installed and its command is registered." ;;
    *)
        warn "installed, but the 'chimenodes' command was not found in ChimeraX's output."
        warn "Start ChimeraX and run:  usage chimenodes   (restart ChimeraX if it was already open)." ;;
esac

cat <<'EOF'

Next steps (in ChimeraX):
    open 1ubq                       # any structure
    chimenodes preset mn_default    # MolecularNodes-style look
    chimenodes glow /A strength 3   # per-object glow (bloom)
    chimenodes off                  # back to stock rendering
Uninstall:  sh install.sh --uninstall
EOF
