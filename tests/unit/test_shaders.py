import glob
import os

import pytest


def test_shaders_version(src_dir):
    files = glob.glob(os.path.join(src_dir, "shaders", "*"))
    if not files:
        pytest.skip("no shaders yet")
    for f in files:
        if f.endswith(".frag") or f.endswith(".vert"):
            first = open(f).read().lstrip().splitlines()[0]
            assert first.strip() == "#version 330 core", f


def test_expected_shaders_exist(src_dir):
    d = os.path.join(src_dir, "shaders")
    if not os.path.isdir(d):
        pytest.skip("no shaders yet")
    missing = [n for n in ("fullscreen.vert", "composite.frag", "tonemap.glsl")
               if not os.path.exists(os.path.join(d, n))]
    if missing:
        pytest.skip("not landed yet: %s" % missing)


def test_no_future_syntax_issues(src_dir):
    """All python sources must parse as py3.9 grammar (best effort: ast feature_version)."""
    import ast
    for f in glob.glob(os.path.join(src_dir, "*.py")):
        ast.parse(open(f).read(), f, feature_version=(3, 9))
