"""Offscreen invariants. Skipped cleanly without ChimeraX/GL."""
import numpy as np
import pytest

pytestmark = pytest.mark.gl


def _image(session, w=200, h=200, supersample=3):
    from chimerax.core.commands import run
    session.main_view.render.make_current()
    img = session.main_view.image(w, h, supersample=supersample)
    return np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0


def _lum(a):
    return float((a * [0.2126, 0.7152, 0.0722]).sum(axis=2).mean())


@pytest.fixture
def scene(session):
    from chimerax.core.commands import run
    run(session, "close; shape sphere radius 5 color orange; view; lighting soft")
    yield session
    run(session, "chimenodes off; close")


def run(session, cmd):
    from chimerax.core.commands import run as r
    return r(session, cmd)


def test_off_equals_stock(scene):
    stock = _image(scene)
    run(scene, "chimenodes on glow 1")
    run(scene, "chimenodes off")
    after = _image(scene)
    assert np.abs(stock - after).max() <= 1.0 / 255 + 1e-6


def test_glow_zero_equals_bloom_off(scene):
    run(scene, "chimenodes glow 0 tonemap none")
    a = _image(scene)
    run(scene, "chimenodes off")
    b = _image(scene)
    assert np.abs(a - b).mean() < 0.01


def test_luminance_monotonic_in_glow(scene):
    vals = []
    for g in (0.0, 0.5, 1.0, 2.0):
        run(scene, "chimenodes glow %g bloomThreshold 0.2 tonemap none" % g)
        vals.append(_lum(_image(scene)))
    assert all(b >= a - 1e-4 for a, b in zip(vals, vals[1:])), vals


def test_2x_resolution_consistency(scene):
    run(scene, "chimenodes glow 1 bloomThreshold 0.2 bloomRadius 0.2")
    small = _image(scene, 128, 128, 1)
    big = _image(scene, 256, 256, 1)
    # downsample big by 2x2 mean and compare structure
    ds = big.reshape(128, 2, 128, 2, 3).mean(axis=(1, 3))
    assert abs(_lum(small) - _lum(ds)) < 0.03
