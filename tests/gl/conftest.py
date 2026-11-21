"""Fixtures for the invariants running inside ChimeraX."""
import builtins

import pytest


@pytest.fixture(scope="session")
def session():
    sess = builtins.session
    render = sess.main_view.render
    if render is None or not render.make_current():
        pytest.skip("ChimeraX could not make an OpenGL context current")

    from cnsrc.cmd import register_commands

    register_commands(sess.logger)
    return sess
