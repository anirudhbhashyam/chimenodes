import importlib
import os
import re

import numpy as np
import pytest
from tests.unit.conftest import load, SRC


# ---- params / presets -------------------------------------------------------
def test_params_defaults_and_clamps():
    P = load("params").Params
    p = P()
    assert p.glow_light == 0.0 and p.glow_light_radius == 0.0
    q = P().update(glow_light=99, glow_light_radius=999)
    assert q.glow_light == 3.0 and q.glow_light_radius == 60.0
    q = P().update(glow_light=-5, glow_light_radius=-5)
    assert q.glow_light == 0.0 and q.glow_light_radius == 0.0


def test_params_roundtrip():
    P = load("params").Params
    p = P(enabled=True, glow_light=1.2, glow_light_radius=7.5)
    assert P.from_dict(p.to_dict()) == p


def test_presets_values():
    pr = load("presets").BUILTIN
    for n in ("mn_default", "neon", "cinematic"):
        assert pr[n].get("glow_light") == pytest.approx(0.6), n
    for n in ("clean", "inspect"):
        assert pr.get(n, {}).get("glow_light", 0) == 0, n


# ---- shader source ----------------------------------------------------------
def _frag():
    path = os.path.join(SRC, "shaders", "glowlight.frag")
    if not os.path.exists(path):
        pytest.skip("glowlight.frag not present")
    return open(path).read()


def test_shader_version_first_line():
    assert _frag().lstrip().splitlines()[0].strip() == "#version 330 core"


def test_shader_light_arrays_match_constants():
    src = _frag()
    for name in ("uLightPos", "uLightCol"):
        m = re.search(r"uniform\s+vec3\s+%s\s*\[\s*(\w+)\s*\]" % name, src)
        assert m, name
        size = m.group(1)
        if not size.isdigit():
            c = re.search(r"const\s+int\s+%s\s*=\s*(\d+)" % size, src) or \
                re.search(r"#define\s+%s\s+(\d+)" % size, src)
            assert c, "unresolved array size " + size
            size = c.group(1)
        assert int(size) == 32, name
    assert re.search(r"uniform\s+int\s+uCount\b", src)


def test_shader_no_dynamic_textureoffset():
    for m in re.finditer(r"textureOffset\s*\(([^;]*)\)\s*;", _frag()):
        off = m.group(1).rsplit("ivec2", 1)
        assert len(off) == 2, "non-constant offset: " + m.group(0)
        assert re.fullmatch(r"\(\s*-?\d+\s*,\s*-?\d+\s*\)\s*", off[1]), m.group(0)


# ---- cluster_lights ---------------------------------------------------------
def _cluster():
    for mod in ("emitters", "glow"):
        if not os.path.exists(os.path.join(SRC, mod + ".py")):
            continue
        try:
            m = importlib.import_module("cnsrc." + mod)
        except ImportError:
            continue
        if hasattr(m, "cluster_lights"):
            return m.cluster_lights
    pytest.skip("cluster_lights not available")


def _data(n, seed=0):
    r = np.random.RandomState(seed)
    return (r.uniform(-10, 20, (n, 3)).astype(np.float32),
            r.uniform(0.1, 1.0, (n, 3)).astype(np.float32))


def test_cluster_reduces_to_max():
    f = _cluster()
    pos, col = _data(500)
    p, c = f(pos, col, 32)
    assert p.shape == c.shape and p.shape[1] == 3 and 0 < len(p) <= 32
    assert p.dtype == np.float32 and c.dtype == np.float32


def test_cluster_small_input_kept():
    f = _cluster()
    pos, col = _data(5)
    p, c = f(pos, col, 32)
    assert len(p) == 5 and len(c) == 5


def test_cluster_empty():
    f = _cluster()
    p, c = f(np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32), 32)
    assert p.shape == (0, 3) and c.shape == (0, 3)


def test_cluster_deterministic():
    f = _cluster()
    pos, col = _data(300, seed=3)
    a = f(pos.copy(), col.copy(), 16)
    b = f(pos.copy(), col.copy(), 16)
    assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])


def test_cluster_inside_bbox_and_finite():
    f = _cluster()
    pos, col = _data(400, seed=5)
    p, c = f(pos, col, 8)
    assert np.isfinite(p).all() and np.isfinite(c).all()
    assert (p >= pos.min(0) - 1e-3).all() and (p <= pos.max(0) + 1e-3).all()
    assert (c >= 0).all()


def test_cluster_weight_not_amplified():
    f = _cluster()
    pos, col = _data(200, seed=7)
    _, c = f(pos, col, 8)
    # total emitted colour is either preserved (sum) or capped (mean); never exceeds the input sum
    assert c.sum() <= col.sum() * 1.01 + 1e-3
    assert c.sum() > 0


# ---- back-compat state ------------------------------------------------------
def test_state_restore_v100_dict():
    state, params = load("state"), load("params")
    old = {"version": 1, "params": {"enabled": True, "glow": 2.0, "tonemap": "agx"}}
    p = state.restore_params(old)
    assert p.glow == 2.0 and p.tonemap == "agx"
    assert p.glow_light == 0.0 and p.glow_light_radius == 0.0


def test_state_roundtrip_new_fields():
    state, params = load("state"), load("params")
    p = params.Params(enabled=True, glow_light=1.4, glow_light_radius=12.0)
    q = state.restore_params(state.snapshot_params(p))
    assert q.glow_light == pytest.approx(1.4) and q.glow_light_radius == pytest.approx(12.0)


# ---- pass module ------------------------------------------------------------
def test_make_passes_importable():
    gl = load("glowlight")
    passes = gl.make_passes()
    assert passes
    entries = [(o, p) for o, p in passes]
    assert any(getattr(p, "name", "") == "glowlight" and o == 160 for o, p in entries)


def test_pass_disabled_when_off():
    gl, P = load("glowlight"), load("params").Params
    obj = [p for _, p in gl.make_passes() if p.name == "glowlight"][0]
    assert not obj.enabled(P(enabled=True, glow_light=0.0))
    assert obj.enabled(P(enabled=True, glow_light=1.0))
