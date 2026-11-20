"""GL tests run inside ChimeraX nogui/offscreen:
    ChimeraX --nogui --offscreen --exit --script tests/gl/run_gl.py
or plain `pytest tests/gl` where they skip unless chimerax is importable with GL.
"""
import pytest


@pytest.fixture(scope="session")
def session():
    try:
        import chimerax.core  # noqa: F401
    except ImportError:
        pytest.skip("ChimeraX not available")
    try:
        from chimerax.core import session as _s  # noqa: F401
        import chimerax
        sess = getattr(chimerax, "_gl_test_session", None)
    except Exception:
        sess = None
    if sess is None:
        # When run through `ChimeraX --script`, the injected `session` global is used instead.
        import builtins
        sess = getattr(builtins, "session", None)
    if sess is None:
        pytest.skip("no ChimeraX session")
    try:
        sess.main_view.render.make_current()
    except Exception as e:
        pytest.skip("no OpenGL context: %s" % e)
    return sess
