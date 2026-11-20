import importlib
import os

import pytest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src")


def load(name):
    """Import cnsrc.<name> or skip the test if the module is not there (yet) or needs ChimeraX."""
    if not os.path.exists(os.path.join(SRC, name + ".py")):
        pytest.skip("src/%s.py not present" % name)
    try:
        return importlib.import_module("cnsrc." + name)
    except ImportError as e:
        pytest.skip("cannot import %s without ChimeraX: %s" % (name, e))


@pytest.fixture
def src_dir():
    return SRC
