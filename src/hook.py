"""Install/uninstall the chimenodes render hook on the main View.

The hook shadows ``View._draw_scene`` with an instance attribute (the class is never
modified), so uninstalling just deletes that attribute. It is idempotent, version guarded
and fail-safe: any unexpected error logs once, restores stock rendering and uninstalls.
"""
from __future__ import annotations

from typing import Optional

_ATTR_PIPE = "_chimenodes_pipeline"
_ATTR_WRAP = "_chimenodes_wrapper"
_warned = set()


def _log_once(session, key, msg):
    if key in _warned:
        return
    _warned.add(key)
    try:
        session.logger.warning(msg)
    except Exception:
        pass


def _compatible(view) -> bool:
    """Version guard: the View/Render API we rely on."""
    try:
        import inspect
        from chimerax.graphics.view import View
        params = list(inspect.signature(View._draw_scene).parameters)
        if params != ["self", "camera", "drawings"]:
            return False
        r = view._render
        needed = ("push_framebuffer", "pop_framebuffer", "current_framebuffer",
                  "render_size", "set_viewport", "framebuffer_stack", "opengl_context")
        return r is not None and all(hasattr(r, n) for n in needed)
    except Exception:
        return False


def get(session):
    """Return the installed Pipeline or None."""
    try:
        return getattr(session.main_view, _ATTR_PIPE, None)
    except Exception:
        return None


def install(session):
    """Install the hook (idempotent). Returns the Pipeline, or None if unsupported."""
    try:
        view = session.main_view
    except Exception:
        return None
    pipe = getattr(view, _ATTR_PIPE, None)
    if pipe is not None:
        return pipe
    if getattr(view, "_render", None) is None:
        return None  # --nogui: no graphics
    if not _compatible(view):
        _log_once(session, "version",
                  "chimenodes: this ChimeraX version's graphics API is not supported; "
                  "rendering effects disabled")
        return None
    try:
        from .pipeline import Pipeline
        pipe = Pipeline(session)
    except Exception as e:
        _log_once(session, "init", "chimenodes: pipeline init failed (%s)" % e)
        return None
    orig = view._draw_scene  # bound method (class one; no wrapper present at this point)
    wrapper = _make_wrapper(session, view, orig)
    setattr(wrapper, _ATTR_WRAP, True)
    setattr(view, _ATTR_PIPE, pipe)
    view._draw_scene = wrapper
    view.redraw_needed = True
    return pipe


def uninstall(session) -> None:
    """Remove the hook and free GPU resources (idempotent)."""
    try:
        view = session.main_view
    except Exception:
        return
    pipe = getattr(view, _ATTR_PIPE, None)
    if view.__dict__.get("_draw_scene") is not None and \
            getattr(view.__dict__["_draw_scene"], _ATTR_WRAP, False):
        del view.__dict__["_draw_scene"]
    if pipe is not None:
        try:
            del view.__dict__[_ATTR_PIPE]
        except KeyError:
            pass
        try:
            r = view._render
            if r is not None and r.make_current():
                pipe.delete(r)
        except Exception:
            pass
    try:
        view.redraw_needed = True
    except Exception:
        pass


def _make_wrapper(session, view, orig):
    def _draw_scene(camera, drawings):
        pipe = getattr(view, _ATTR_PIPE, None)
        if pipe is None:
            return orig(camera, drawings)
        r = view._render
        started = False
        try:
            if (camera.number_of_views() == 1 and not r.recording_opengl
                    and pipe.is_active()):
                started = pipe.begin(view, r, camera, drawings, orig)
        except Exception as e:
            pipe.abort(view, r)
            _fail(session, "begin", e)
            return orig(camera, drawings)
        if not started:
            return orig(camera, drawings)
        try:
            orig(camera, drawings)
        except BaseException:
            pipe.abort(view, r)
            raise
        try:
            pipe.end(view, r, camera)
        except Exception as e:
            _fail(session, "end", e)
    return _draw_scene


def _fail(session, where, exc):
    """Log once, then fall back to stock rendering permanently (until re-enabled)."""
    msg = str(exc)
    if len(msg) > 400:
        msg = msg[:400] + " ..."
    _log_once(session, "fail-" + where,
              "chimenodes: rendering pipeline error in %s (%s: %s); falling back to stock "
              "rendering" % (where, type(exc).__name__, msg))
    try:
        uninstall(session)
    except Exception:
        pass
