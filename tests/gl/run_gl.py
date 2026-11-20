"""Entry for: ChimeraX --nogui --offscreen --exit --script tests/gl/run_gl.py"""
import os
import sys
import builtins

builtins.session = session  # noqa: F821  (injected by ChimeraX --script)
import pytest  # noqa: E402  (needs pytest installed in ChimeraX's python)

here = os.path.dirname(os.path.abspath(__file__))
rc = pytest.main([here, "-q", "-p", "no:cacheprovider"])
sys.exit(int(rc))
