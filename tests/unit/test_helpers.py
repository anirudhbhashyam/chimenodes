"""Pure helpers of glow.py / lens.py, if present. Skips until they exist."""
import os

import pytest
from tests.unit.conftest import load


def test_glow_importable_pure():
    g = load("glow")
    assert hasattr(g, "make_passes") or hasattr(g, "set_glow")


def test_lens_importable_pure():
    l = load("lens")
    assert hasattr(l, "make_passes")


def test_presets_valid():
    presets, params = load("presets"), load("params")
    assert {"mn_default", "neon", "cinematic", "clean", "inspect"} <= set(presets.BUILTIN)
    for name, kw in presets.BUILTIN.items():
        params.Params().update(**{k: v for k, v in kw.items()})  # must not raise


def test_blur_radius_resolution_independent():
    g = load("glow")
    f = getattr(g, "bloom_pixel_radius", None)
    if f is None:
        pytest.skip("no bloom_pixel_radius helper")
    assert abs(f(0.3, 2000) / f(0.3, 1000) - 2.0) < 1e-6
