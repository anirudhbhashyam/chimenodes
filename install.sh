#!/bin/sh
# chimenodes installer: MolecularNodes-style rendering + glow for UCSF ChimeraX.
#
#   curl -fsSL https://raw.githubusercontent.com/anirudhbhashyam/chimenodes/main/install.sh -o chimenodes-install.sh
#   sh chimenodes-install.sh
#
# ChimeraX installs the prebuilt release wheel using its bundled Python.
# Requires ChimeraX >= 1.8 and, for downloads, curl or wget and sha256sum or shasum.
#
# ChimeraX itself is NOT downloaded for you: its license must be accepted by you at
# https://www.cgl.ucsf.edu/chimerax/download.html
#
# Keep the entry point after the function definitions.

set -eu

VERSION="1.0.7"
WHEEL_NAME="chimerax_chimenodes-$VERSION-py3-none-any.whl"
WHEEL_URL="https://github.com/anirudhbhashyam/chimenodes/releases/download/v$VERSION/$WHEEL_NAME"
WHEEL_SHA256="a17c5920d563ff074de5c72ef2e3607f881838b7efd050a8fd06b53e05438b1a"
BUNDLE_NAME="ChimeraX-Chimenodes"
MIN_MAJOR=1
MIN_MINOR=8
TMP=""

say()  { printf '%s\n' "$*"; }
info() { printf '==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
chimenodes installer

Usage: install.sh [options]

  --chimerax PATH   ChimeraX executable or .app bundle   (env CHIMERAX_EXE)
  --local DIR       install from a local checkout instead of downloading
  --build-only      save the release wheel to ./dist (build it with --local)
  --uninstall       remove chimenodes from ChimeraX
  --dry-run         find ChimeraX and show what would happen, change nothing
  -h, --help        show this help
EOF
}

cleanup() { if [ -n "$TMP" ]; then rm -rf "$TMP"; fi; }

# --- version helpers (no `sort -V`: not available everywhere) ------------------------------
# prints the dotted version found in a path ("ChimeraX-1.11.1.app" -> 1.11.1), or 0
path_version() {
    v=$(printf '%s' "$1" | sed -n 's/.*ChimeraX[- _]\{0,1\}\([0-9][0-9]*\(\.[0-9][0-9]*\)*\).*/\1/p' | head -n 1)
    printf '%s' "${v:-0}"
}

# returns 0 if version $1 is strictly newer than $2
ver_gt() {
    a=$1; b=$2
    for _ in 1 2 3 4; do
        an=${a%%.*}; bn=${b%%.*}
        [ "$an" -gt "$bn" ] 2>/dev/null && return 0
        [ "$an" -lt "$bn" ] 2>/dev/null && return 1
        case "$a" in *.*) a=${a#*.} ;; *) a=0 ;; esac
        case "$b" in *.*) b=${b#*.} ;; *) b=0 ;; esac
    done
    return 1
}

# --- locate ChimeraX -------------------------------------------------------------------
# Sets CX to the newest executable among the candidate paths given as arguments.
pick_newest() {
    best=""; bestv="-1"
    for p in "$@"; do
        [ -f "$p" ] && [ -x "$p" ] || continue
        v=$(path_version "$p")
        if [ -z "$best" ] || ver_gt "$v" "$bestv"; then best=$p; bestv=$v; fi
    done
    [ -n "$best" ] || return 1
    CX=$best
}

find_chimerax() {
    if [ -n "$CX" ]; then
        case "$CX" in *.app) CX="$CX/Contents/MacOS/ChimeraX" ;; esac   # macOS app bundle
        [ -x "$CX" ] || die "ChimeraX not executable at: $CX"
        return 0
    fi
    for name in chimerax ChimeraX ChimeraX-console; do
        if p=$(command -v "$name" 2>/dev/null) && [ -n "$p" ]; then CX=$p; return 0; fi
    done
    case "$(uname -s)" in
        Darwin)
            pick_newest /Applications/ChimeraX*.app/Contents/MacOS/ChimeraX \
                "$HOME"/Applications/ChimeraX*.app/Contents/MacOS/ChimeraX ;;
        Linux)
            pick_newest /opt/UCSF/ChimeraX*/bin/ChimeraX /opt/UCSF/ChimeraX*/bin/chimerax \
                /usr/libexec/UCSF-ChimeraX*/bin/ChimeraX "$HOME"/.local/UCSF/ChimeraX*/bin/ChimeraX ;;
        MINGW*|MSYS*|CYGWIN*)
            pick_newest "/c/Program Files/ChimeraX"*/bin/ChimeraX-console.exe \
                "/c/Program Files/ChimeraX"*/bin/ChimeraX.exe ;;
        *) return 1 ;;
    esac
}

no_chimerax() {
    cat >&2 <<'EOF'
error: UCSF ChimeraX was not found on this system.

chimenodes is a ChimeraX plugin, so ChimeraX (>= 1.8) must be installed first:
  1. Download it from https://www.cgl.ucsf.edu/chimerax/download.html
     (free for non-commercial use; you must accept its license yourself)
  2. Install it, then re-run this script. If it is in a non-standard place, point to it:
       sh /path/to/install.sh --chimerax /path/to/ChimeraX
     or set CHIMERAX_EXE=/path/to/ChimeraX
No system Python, uv or pixi is required: ChimeraX ships its own Python.
EOF
    exit 1
}

# Run a ChimeraX command headless. stdin is detached: under `curl | sh` it is the script itself.
cx_run() { "$CX" --nogui --exit --cmd "$1" </dev/null; }

# Windows (Git Bash/MSYS) needs a native path in ChimeraX commands.
native_path() {
    path=$1
    case "$(uname -s)" in
        MINGW*|MSYS*|CYGWIN*) if command -v cygpath >/dev/null 2>&1; then path=$(cygpath -m "$path") || return 1; fi ;;
    esac
    case "$path" in *\"*) die "refusing a path containing a double quote: $path" ;; esac
    printf '%s\n' "$path"
}

wheel_sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum < "$1"
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 < "$1"
    else
        die "need sha256sum or shasum to verify the release wheel"
    fi
}

save_wheel() {
    outdir="$(pwd)/dist"
    mkdir -p "$outdir"
    if ! [ "$1" -ef "$outdir/${1##*/}" ]; then
        cp "$1" "$outdir"/
    fi
    info "Wheel written to $outdir"
}

install_release() {
    if [ "$DRY" -eq 1 ]; then
        if [ "$MODE" = build ]; then
            say "(dry run) would download and verify $WHEEL_URL and save it to ./dist"
        else
            say "(dry run) would download and verify $WHEEL_URL and install it with toolshed install"
        fi
        exit 0
    fi

    info "Downloading $WHEEL_URL"
    TMP=$(mktemp -d 2>/dev/null || mktemp -d -t chimenodes)
    wheel="$TMP/$WHEEL_NAME"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL -o "$wheel" -- "$WHEEL_URL" </dev/null || die "download failed: $WHEEL_URL"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$wheel" -- "$WHEEL_URL" </dev/null || die "download failed: $WHEEL_URL"
    else
        die "need curl or wget to download the release wheel"
    fi
    digest=$(wheel_sha256 "$wheel") || die "could not verify the release wheel"
    [ "${digest%% *}" = "$WHEEL_SHA256" ] || die "SHA-256 mismatch for $WHEEL_NAME"

    if [ "$MODE" = build ]; then
        save_wheel "$wheel"
        exit 0
    fi

    wheel_native=$(native_path "$wheel")
    info "Installing $BUNDLE_NAME $VERSION (for the current user)"
    cx_run "toolshed install \"$wheel_native\"" || die "installation failed"
}

install_local() {
    [ -f "$LOCAL/bundle_info.xml" ] || die "no bundle_info.xml in --local directory: $LOCAL"
    SRC=$(cd "$LOCAL" && pwd)
    info "Using local source: $SRC"
    SRC_NATIVE=$(native_path "$SRC")

    if [ "$DRY" -eq 1 ]; then
        if [ "$MODE" = build ]; then
            say "(dry run) would run: $CX --nogui --exit --cmd 'devel build \"$SRC_NATIVE\"'"
        else
            say "(dry run) would run: $CX --nogui --exit --cmd 'devel install \"$SRC_NATIVE\" user true'"
        fi
        exit 0
    fi

    if [ "$MODE" = build ]; then
        info "Building wheel"
        cx_run "devel build \"$SRC_NATIVE\" exit true"
        WHL=""
        for w in "$SRC"/dist/*.whl; do
            case "$w" in *editable*) continue ;; esac
            [ -f "$w" ] && WHL="$w"
        done
        [ -n "$WHL" ] || die "build finished but no wheel was produced"
        save_wheel "$WHL"
        exit 0
    fi

    info "Building and installing $BUNDLE_NAME (for the current user)"
    cx_run "devel install \"$SRC_NATIVE\" user true exit true" \
        || die "installation failed. Re-run with --chimerax PATH if multiple ChimeraX versions exist."
}

main() {
    CX="${CHIMERAX_EXE:-}"
    LOCAL=""
    MODE="install"
    DRY=0

    while [ $# -gt 0 ]; do
        case "$1" in
            --chimerax)   [ $# -ge 2 ] || die "--chimerax needs a path"; CX="$2"; shift 2 ;;
            --local)      [ $# -ge 2 ] || die "--local needs a directory"; LOCAL="$2"; shift 2 ;;
            --build-only) MODE="build"; shift ;;
            --uninstall)  MODE="uninstall"; shift ;;
            --dry-run)    DRY=1; shift ;;
            -h|--help)    usage; exit 0 ;;
            *)            die "unknown option: $1 (try --help)" ;;
        esac
    done

    trap cleanup EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM

    find_chimerax || no_chimerax
    info "ChimeraX executable: $CX"

    # e.g. "UCSF ChimeraX version: 1.11.1 (2026-01-23)"
    VER_LINE=$("$CX" --version </dev/null 2>/dev/null | grep -i "version" | head -n 1 || true)
    VER=$(printf '%s' "$VER_LINE" | sed -n 's/.*version:* *\([0-9][0-9]*\.[0-9][0-9]*\(\.[0-9][0-9]*\)*\).*/\1/p')
    [ -n "$VER" ] || die "could not determine the ChimeraX version (is '$CX' really ChimeraX?)"
    MAJ=${VER%%.*}; REST=${VER#*.}; MIN=${REST%%.*}
    if [ "$MAJ" -lt "$MIN_MAJOR" ] || { [ "$MAJ" -eq "$MIN_MAJOR" ] && [ "$MIN" -lt "$MIN_MINOR" ]; }; then
        die "ChimeraX $VER is too old; chimenodes needs >= $MIN_MAJOR.$MIN_MINOR. Update ChimeraX and retry."
    fi
    info "ChimeraX version: $VER (ok, >= $MIN_MAJOR.$MIN_MINOR)"

    # --- uninstall ---------------------------------------------------------------------
    if [ "$MODE" = "uninstall" ]; then
        info "Uninstalling $BUNDLE_NAME"
        if [ "$DRY" -eq 1 ]; then say "(dry run) would run: toolshed uninstall $BUNDLE_NAME"; exit 0; fi
        cx_run "toolshed uninstall $BUNDLE_NAME"
        info "Done. Restart ChimeraX if it is running."
        exit 0
    fi

    if [ -n "$LOCAL" ]; then
        install_local
    else
        install_release
    fi

    # --- verify ------------------------------------------------------------------------
    info "Verifying"
    OUT=$("$CX" --nogui --exit --cmd "usage chimenodes" </dev/null 2>&1 || true)
    case "$OUT" in
        *chimenodes*"Configure"*|*"MolecularNodes-style"*)
            info "chimenodes is installed and its command is registered." ;;
        *)
            warn "installed, but the 'chimenodes' command was not found in ChimeraX's output."
            warn "Start ChimeraX and run:  usage chimenodes   (restart ChimeraX if it was already open)." ;;
    esac

    cat <<'EOF'

Next steps (in ChimeraX):
    open 1brs                       # any structure
    chimenodes preset mn_default    # MolecularNodes-style look
    chimenodes glow /D strength 1.1 # per-object glow (bloom)
    chimenodes off                  # back to stock rendering
Uninstall:  sh /path/to/install.sh --uninstall
EOF
}

main "$@"
