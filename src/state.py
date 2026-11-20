"""Session state for chimenodes: versioned snapshot/restore of Params.

Pure helpers (snapshot_params / restore_params) have no ChimeraX dependency.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .params import Params

STATE_VERSION = 1
STATE_NAME = "chimenodes"


def snapshot_params(params: Params) -> Dict[str, Any]:
    """Versioned plain-dict snapshot."""
    return {"version": STATE_VERSION, "params": params.to_dict()}


def restore_params(data: Optional[Dict[str, Any]]) -> Params:
    """Tolerant restore: unknown keys dropped, bad values fall back to defaults."""
    if not isinstance(data, dict):
        return Params()
    raw = data.get("params", {})
    if not isinstance(raw, dict):
        return Params()
    try:
        return Params.from_dict(raw)
    except Exception:
        # Retry field by field so one bad value does not lose everything.
        p = Params()
        for k, v in raw.items():
            try:
                trial = Params.from_dict(dict(p.to_dict(), **{k: v}))
                p = trial
            except Exception:
                pass
        return p


def apply_params(session, params: Params) -> bool:
    """Push params to the hook/look. Fail-safe: returns False on any problem."""
    try:
        from . import hook
        if params.enabled:
            pipe = hook.install(session)
            if pipe is None:
                return False
            pipe.set_params(params)
            try:
                from . import look
                look.apply_look(session, params)
            except ImportError:
                pass
        else:
            pipe = hook.get(session)
            if pipe is not None:
                pipe.set_params(params)
            try:
                from . import look
                look.restore_look(session)
            except ImportError:
                pass
            hook.uninstall(session)
        _store(session).params = params
        return True
    except Exception as e:  # never break rendering/session restore
        try:
            session.logger.warning("chimenodes: could not apply settings (%s)" % e)
        except Exception:
            pass
        return False


class _Store(object):
    def __init__(self, params: Optional[Params] = None):
        self.params = params or Params()


def _store(session) -> _Store:
    st = getattr(session, "_chimenodes_store", None)
    if st is None:
        st = _Store()
        try:
            session._chimenodes_store = st
        except Exception:
            pass
    return st


def get_params(session) -> Params:
    """Current params: live pipeline's if installed, else last stored."""
    try:
        from . import hook
        pipe = hook.get(session)
        if pipe is not None:
            return pipe.params
    except Exception:
        pass
    return _store(session).params


def make_state_manager_class():
    """Build the StateManager subclass lazily (needs chimerax.core)."""
    from chimerax.core.state import StateManager

    class ChimenodesState(StateManager):
        version = STATE_VERSION

        def __init__(self, session):
            self.session = session

        def reset_state(self, session):
            apply_params(session, Params())

        def take_snapshot(self, session, flags):
            return snapshot_params(get_params(session))

        @staticmethod
        def restore_snapshot(session, data):
            mgr = ChimenodesState(session)
            params = restore_params(data)
            _store(session).params = params
            if params.enabled:
                # Defer until the session finished restoring (GL ready).
                def _later(*a):
                    apply_params(session, params)
                    from chimerax.core.triggerset import DEREGISTER
                    return DEREGISTER
                try:
                    session.triggers.add_handler("new frame", _later)
                except Exception:
                    pass
            return mgr

    return ChimenodesState


def register_state(session) -> bool:
    """Register the state manager with the session (call from bundle initialize)."""
    try:
        cls = make_state_manager_class()
        session.add_state_manager(STATE_NAME, cls(session))
        return True
    except Exception:
        return False
