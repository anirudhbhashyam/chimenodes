import sys
import types

import pytest
from tests.unit.conftest import load


class _Logger:
    def __init__(self):
        self.warnings = []

    def warning(self, msg):
        self.warnings.append(msg)

    def status(self, msg, **kw):
        pass


class _Session:
    def __init__(self):
        self.logger = _Logger()


def _patch_state(ok):
    m = types.ModuleType("cnsrc.state")
    m.apply_params = lambda session, params: ok
    sys.modules["cnsrc.state"] = m


def test_merge_no_preset_keeps_base():
    cmd, params = load("cmd"), load("params")
    base = params.Params(enabled=True, glow=1.5)
    out = cmd.merge_params(base, None, {"exposure": 1.0})
    assert out.glow == 1.5 and out.exposure == 1.0 and out is not base
    assert base.exposure == 0.0


def test_override_beats_preset():
    cmd, params = load("cmd"), load("params")
    base = params.Params(enabled=True, vignette=0.9)
    out = cmd.merge_params(base, {"glow": 2.0, "tonemap": "agx"}, {"glow": 0.5},
                           preset_name="neon")
    assert out.glow == 0.5 and out.tonemap == "agx"
    assert out.vignette == 0.0          # preset replaces the old look
    assert out.enabled and out.preset == "neon"


def test_clamping_and_none_ignored():
    cmd, params = load("cmd"), load("params")
    out = cmd.merge_params(params.Params(), None, {"glow": 100, "dof": None})
    assert out.glow == 5.0 and out.dof == 0.0


def test_bad_values():
    cmd, params = load("cmd"), load("params")
    with pytest.raises(ValueError):
        cmd.merge_params(params.Params(), None, {"tonemap": "x"})
    with pytest.raises(KeyError):
        cmd.merge_params(params.Params(), {"bogus": 1}, {})


def test_keyword_mapping():
    cmd = load("cmd")
    o = cmd.keywords_to_overrides({"bloomRadius": 0.2, "aoRadius": 1.0, "fxaa": True,
                                   "dof": None, "unknown": 3})
    assert o == {"bloom_radius": 0.2, "ao_radius": 1.0, "fxaa": True}


def test_keywords_cover_params():
    cmd, params = load("cmd"), load("params")
    assert set(params.RANGES) - {"bloom_knee"} <= set(cmd.KEYWORDS.values()) | {"bloom_knee"}
    assert set(cmd.KEYWORDS.values()) <= set(params.Params().to_dict())


def test_builtin_presets_merge():
    cmd = load("cmd")
    presets = load("presets")
    for name in presets.BUILTIN:
        kw = presets.get_preset(name)
        out = cmd.merge_params(load("params").Params(), kw, {}, name)
        assert out.preset == name


def test_commit_fails_safe_when_pipeline_cannot_enable():
    # When the pipeline cannot be enabled (e.g. no OpenGL 3.3 core in an offscreen or
    # software-GL context), _commit must fail safe to stock rendering with a warning,
    # not raise -- otherwise a batch/offscreen render script aborts mid-run.
    cmd, params = load("cmd"), load("params")
    _patch_state(False)
    try:
        s = _Session()
        ok = cmd._commit(s, params.Params(enabled=True))
        assert ok is False
        assert any("could not enable" in w for w in s.logger.warnings)
    finally:
        sys.modules.pop("cnsrc.state", None)


def test_commit_quiet_on_success():
    cmd, params = load("cmd"), load("params")
    _patch_state(True)
    try:
        s = _Session()
        ok = cmd._commit(s, params.Params(enabled=True))
        assert ok is True
        assert s.logger.warnings == []
    finally:
        sys.modules.pop("cnsrc.state", None)
