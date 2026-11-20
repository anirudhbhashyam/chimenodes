"""Load src/ as a synthetic package so relative imports work without ChimeraX."""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
PKG = "cnsrc"

if PKG not in sys.modules:
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [SRC]
    sys.modules[PKG] = pkg
