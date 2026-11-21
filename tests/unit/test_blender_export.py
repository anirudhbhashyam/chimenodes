import json
import os
import py_compile
from types import SimpleNamespace
from unittest.mock import Mock

from tests.unit.conftest import load


def _sidecar(be):
    cam = {"position": [1, 2, 3], "rotation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
           "fov_degrees": 30, "near": 1.0, "far": 100.0}
    models = [{"name": "m", "representation": ["cartoon"], "chain_colors": {"A": [255, 0, 0, 255]}}]
    return be.build_sidecar("/x/y/prot.cif", cam, models,
                            {"glow": 2.0, "tonemap": "agx", "exposure": 0.5}, [0, 0, 0, 1],
                            {"1": [0, 5]})


def test_sidecar_json(tmp_path):
    be = load("blender_export")
    d = _sidecar(be)
    path = be.write_sidecar(str(tmp_path / "a.json"), d)
    back = json.load(open(path))
    assert back["structure"] == "prot.cif"
    assert back["camera"]["fov_degrees"] == 30
    assert back["glow"]["global_strength"] == 2.0 and back["glow"]["atoms"] == {"1": [0, 5]}
    assert back["tonemap"] == "agx"


def test_sidecar_path():
    be = load("blender_export")
    assert be.sidecar_path("/a/b/prot.cif").endswith("prot.chimenodes.json")


def test_helper_script_compiles(tmp_path):
    be = load("blender_export")
    out = be.write_helper_script(str(tmp_path))
    assert os.path.basename(out) == "render_blender.py"
    py_compile.compile(out, doraise=True)


def test_export_passes_path_and_models_directly_to_saver(tmp_path, monkeypatch):
    be = load("blender_export")
    structures = [object()]
    scene = {
        "structures": structures,
        "camera": _sidecar(be)["camera"],
        "models": [],
        "params": {},
        "background": [0, 0, 0, 1],
        "glow_atoms": {},
    }
    save_data = Mock()
    session = SimpleNamespace(save_command=SimpleNamespace(save_data=save_data))
    monkeypatch.setattr(be, "collect_scene", lambda session, models: scene)
    path = str(tmp_path / "protein's draft; final.PDB")

    assert be.export_blender(session, path, structures) == path

    save_data.assert_called_once_with(path, format="pdb", models=structures)
