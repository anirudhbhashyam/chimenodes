#!/usr/bin/env python3
"""Install this bundle into ChimeraX in editable mode (mac/win/linux).

Usage: python scripts/dev_install.py [--exe /path/to/ChimeraX] [--no-editable]
Env:   CHIMERAX_EXE overrides discovery.
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _newest(patterns):
    hits = []
    for p in patterns:
        hits += glob.glob(p)
    return sorted(hits)[-1] if hits else None


def find_chimerax(explicit=None):
    cands = [explicit, os.environ.get("CHIMERAX_EXE")]
    for c in cands:
        if c and os.path.exists(c):
            return c
    which = shutil.which("ChimeraX") or shutil.which("chimerax")
    if which:
        return which
    if sys.platform == "darwin":
        return _newest(["/Applications/ChimeraX*.app/Contents/bin/ChimeraX",
                        os.path.expanduser("~/Applications/ChimeraX*.app/Contents/bin/ChimeraX")])
    if sys.platform.startswith("win"):
        roots = [os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("LOCALAPPDATA", "")]
        return _newest([os.path.join(r, "ChimeraX*", "bin", "ChimeraX-console.exe") for r in roots if r]
                       + [os.path.join(r, "ChimeraX*", "bin", "ChimeraX.exe") for r in roots if r])
    return _newest(["/usr/libexec/UCSF-ChimeraX*/bin/ChimeraX", "/opt/UCSF/ChimeraX*/bin/ChimeraX",
                    "/usr/bin/chimerax", os.path.expanduser("~/ChimeraX*/bin/ChimeraX")])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe")
    ap.add_argument("--no-editable", action="store_true")
    a = ap.parse_args()
    exe = find_chimerax(a.exe)
    if not exe:
        sys.exit("ChimeraX not found. Pass --exe or set CHIMERAX_EXE.")
    cmd = "devel install %s%s exit true" % (
        '"%s"' % ROOT.replace("\\", "/"), "" if a.no_editable else " editable true")
    full = [exe, "--nogui", "--exit", "--cmd", cmd]
    print("+", " ".join(full))
    sys.exit(subprocess.call(full))


if __name__ == "__main__":
    main()
