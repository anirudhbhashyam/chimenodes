from tests.unit.conftest import load


def test_round_trip():
    state, params = load("state"), load("params")
    p = params.Params(enabled=True, glow=2.5, tonemap="agx", fxaa=True, quality="high")
    snap = state.snapshot_params(p)
    assert snap["version"] == state.STATE_VERSION
    assert state.restore_params(snap) == p


def test_degrades():
    state, params = load("state"), load("params")
    assert state.restore_params(None) == params.Params()
    assert state.restore_params({"params": 3}) == params.Params()
    got = state.restore_params({"version": 99, "params": {"glow": 2.0, "tonemap": "bad", "x": 1}})
    assert got.glow == 2.0 and got.tonemap == "none"
