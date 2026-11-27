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


def test_bundle_resolves_registered_manager_and_restores_settings(monkeypatch):
    import sys
    from types import ModuleType, SimpleNamespace

    from src import bundle_api, state

    core_state = ModuleType("chimerax.core.state")
    core_state.StateManager = object
    monkeypatch.setitem(sys.modules, "chimerax.core.state", core_state)
    managers = {}
    session = SimpleNamespace(add_state_manager=managers.__setitem__)
    try:
        bundle_api.initialize(session, None)
        manager = managers[state.STATE_NAME]
        cls = bundle_api.get_class(type(manager).__name__)
        assert cls is type(manager)
        assert bundle_api.get_class("UnknownState") is None

        state.get_params(session).glow = 2.5
        snapshot = manager.take_snapshot(session, flags=0)
        restored_session = SimpleNamespace()
        restored = cls.restore_snapshot(restored_session, snapshot)
        assert type(restored) is cls
        assert state.get_params(restored_session).glow == 2.5
    finally:
        state.make_state_manager_class.cache_clear()
