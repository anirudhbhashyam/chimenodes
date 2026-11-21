"""Export a ChimeraX scene for MolecularNodes in Blender.

build_sidecar() and friends are pure Python; ChimeraX access is isolated in
collect_scene() / export_blender().
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence

SIDECAR_VERSION = 1


def _round(seq, n=6):
    return [round(float(x), n) for x in seq]


def build_sidecar(structure_file: str, camera: Dict[str, Any], models: List[Dict[str, Any]],
                  params: Dict[str, Any], background: Optional[Sequence[float]] = None,
                  glow_atoms: Optional[Dict[str, List[int]]] = None) -> Dict[str, Any]:
    """Assemble the JSON-serialisable description.

    camera: {position:[x,y,z], rotation:[[3x3 rows, camera axes as columns]],
             fov_degrees, near, far, orthographic}
    models: [{name, file, representation:[...], chain_colors:{chain:[r,g,b,a]}}]
    """
    glow = {
        "global_strength": float(params.get("glow", 0.0)),
        "bloom_radius": float(params.get("bloom_radius", 0.3)),
        "bloom_threshold": float(params.get("bloom_threshold", 1.0)),
        "bloom_knee": float(params.get("bloom_knee", 0.5)),
        "atoms": glow_atoms or {},
    }
    return {
        "chimenodes_export_version": SIDECAR_VERSION,
        "structure": os.path.basename(structure_file),
        "units": "angstrom",
        "camera": {
            "position": _round(camera["position"]),
            "rotation": [_round(r) for r in camera["rotation"]],
            "fov_degrees": round(float(camera["fov_degrees"]), 4),
            "near": round(float(camera["near"]), 4),
            "far": round(float(camera["far"]), 4),
            "orthographic": bool(camera.get("orthographic", False)),
        },
        "background": _round(background) if background is not None else [0, 0, 0, 1],
        "models": models,
        "tonemap": params.get("tonemap", "none"),
        "exposure": float(params.get("exposure", 0.0)),
        "glow": glow,
        "params": params,
    }


def write_sidecar(path: str, data: Dict[str, Any]) -> str:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    return path


def sidecar_path(structure_path: str) -> str:
    return os.path.splitext(structure_path)[0] + ".chimenodes.json"


def write_helper_script(directory: str) -> str:
    out = os.path.join(directory, "render_blender.py")
    with open(out, "w") as f:
        f.write(RENDER_BLENDER_PY)
    return out


# ------------------------------------------------------------------ ChimeraX side

def collect_scene(session, models=None) -> Dict[str, Any]:
    import numpy as np
    from chimerax.atomic import AtomicStructure
    view = session.main_view
    cam = view.camera
    pos = cam.position
    axes = pos.axes()  # rows: x, y, z axes
    near, far = 0.0, 0.0
    try:
        near, far = view.near_far_distances(cam, view.drawing_bounds())[:2]
    except Exception:
        pass
    camera = {
        "position": list(pos.origin()),
        "rotation": np.asarray(axes).T.tolist(),
        "fov_degrees": getattr(cam, "field_of_view", 30.0),
        "near": near, "far": far,
        "orthographic": cam.name == "orthographic",
    }
    structs = [m for m in (models or session.models) if isinstance(m, AtomicStructure)]
    infos, glow_atoms = [], {}
    for i, s in enumerate(structs):
        reps = []
        if s.atoms.displays.any():
            styles = set(int(x) for x in s.atoms.draw_modes[s.atoms.displays])
            names = {0: "sphere", 1: "ball", 2: "stick"}
            reps += [names.get(x, "ball") for x in sorted(styles)]
        if s.residues.ribbon_displays.any():
            reps.append("cartoon")
        chain_colors = {}
        for ch in s.chains:
            res = ch.existing_residues
            if len(res):
                c = res[0].ribbon_color if res.ribbon_displays[0] else res[0].atoms[0].color
                chain_colors[ch.chain_id] = [int(x) for x in c]
        infos.append({"name": s.name, "id": s.id_string, "representation": reps,
                      "chain_colors": chain_colors, "num_atoms": s.num_atoms})
        try:
            g = np.array(s.atoms.get_attr("glow", 0.0) if hasattr(s.atoms, "get_attr")
                         else getattr(s.atoms, "glows", []))
            idx = np.nonzero(g > 0)[0]
            if len(idx):
                glow_atoms[s.id_string] = [int(x) for x in idx]
        except Exception:
            pass
    from . import state
    params = state.get_params(session).to_dict()
    bg = list(view.background_color)
    return {"camera": camera, "models": infos, "structures": structs, "params": params,
            "background": bg, "glow_atoms": glow_atoms}


def export_blender(session, path: str, models=None) -> str:
    path = os.path.abspath(os.path.expanduser(path))
    if os.path.splitext(path)[1].lower() not in (".cif", ".pdb", ".bcif"):
        path += ".cif"
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    sc = collect_scene(session, models)
    if not sc["structures"]:
        raise OSError("no atomic structures to export")
    fmt = "pdb" if path.casefold().endswith(".pdb") else "mmcif"
    session.save_command.save_data(path, format=fmt, models=sc["structures"])
    data = build_sidecar(path, sc["camera"], sc["models"], sc["params"],
                         sc["background"], sc["glow_atoms"])
    write_sidecar(sidecar_path(path), data)
    write_helper_script(d)
    return path


RENDER_BLENDER_PY = r'''"""Standalone Blender helper generated by chimenodes.

Usage:
  blender --background --python render_blender.py -- STRUCTURE.cif [out.png] [--engine eevee|cycles]

Requires the MolecularNodes add-on. Reads STRUCTURE.chimenodes.json next to the structure.
MolecularNodes' API changes between releases; failures are reported, not fatal.
"""
import json
import math
import os
import sys

WORLD_SCALE = 0.01  # MolecularNodes imports angstrom * 0.01 as Blender units


def _args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    pos = [x for x in a if not x.startswith("--")]
    engine = "eevee"
    if "--engine" in a:
        engine = a[a.index("--engine") + 1]
        pos = [x for x in pos if x != engine]
    if not pos:
        raise SystemExit("usage: blender -b -P render_blender.py -- STRUCTURE [out.png] [--engine eevee|cycles]")
    return pos[0], (pos[1] if len(pos) > 1 else None), engine


def main():
    import bpy
    from mathutils import Matrix, Vector
    structure, out, engine = _args()
    side = os.path.splitext(structure)[0] + ".chimenodes.json"
    with open(side) as f:
        info = json.load(f)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    import molecularnodes as mn
    try:
        mol = mn.Molecule.load(structure)          # MolecularNodes 4.x
    except AttributeError:
        raise SystemExit("Unsupported MolecularNodes version; load the structure manually.")
    reps = []
    for m in info.get("models", []):
        reps += m.get("representation", [])
    style = "cartoon" if "cartoon" in reps else ("spheres" if "sphere" in reps else "ball_and_stick")
    try:
        mol.add_style(style)
    except Exception as e:
        print("could not add style %s: %s" % (style, e))

    # Camera: ChimeraX (x right, y up, -z view) -> Blender (z up); camera looks down -Z too.
    cam_info = info["camera"]
    C = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))
    R = Matrix(cam_info["rotation"])
    Rb = C @ R
    loc = C @ Vector(cam_info["position"]) * WORLD_SCALE
    cam_data = bpy.data.cameras.new("chimenodes")
    cam_data.sensor_fit = "HORIZONTAL"
    cam_data.angle = math.radians(cam_info["fov_degrees"])
    cam_data.clip_start = max(cam_info["near"] * WORLD_SCALE, 1e-4)
    cam_data.clip_end = max(cam_info["far"] * WORLD_SCALE, cam_data.clip_start * 10)
    cam = bpy.data.objects.new("chimenodes", cam_data)
    cam.matrix_world = Matrix.Translation(loc) @ Rb.to_4x4()
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    # NOTE: MolecularNodes may recentre the molecule; disable centring in the add-on
    # if the camera does not frame the structure.

    scn = bpy.context.scene
    world = bpy.data.worlds.new("chimenodes")
    world.use_nodes = True
    bg = info.get("background", [0, 0, 0, 1])
    world.node_tree.nodes["Background"].inputs[0].default_value = bg
    scn.world = world
    scn.render.engine = "CYCLES" if engine == "cycles" else "BLENDER_EEVEE_NEXT" \
        if "BLENDER_EEVEE_NEXT" in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items else "BLENDER_EEVEE"
    tm = {"agx": "AgX", "filmic": "Filmic", "aces": "Filmic", "none": "Standard"}
    try:
        scn.view_settings.view_transform = tm.get(info.get("tonemap", "none"), "Standard")
    except TypeError:
        pass
    scn.view_settings.exposure = info.get("exposure", 0.0)

    glow = info.get("glow", {})
    if glow.get("global_strength", 0) > 0:
        scn.use_nodes = True
        nt = scn.node_tree
        rl = nt.nodes.get("Render Layers") or nt.nodes.new("CompositorNodeRLayers")
        gl = nt.nodes.new("CompositorNodeGlare")
        gl.glare_type = "FOG_GLOW"
        gl.threshold = glow.get("bloom_threshold", 1.0)
        gl.mix = min(1.0, glow["global_strength"] - 1.0)
        comp = nt.nodes.get("Composite") or nt.nodes.new("CompositorNodeComposite")
        nt.links.new(rl.outputs[0], gl.inputs[0])
        nt.links.new(gl.outputs[0], comp.inputs[0])

    if out:
        scn.render.filepath = out
        bpy.ops.render.render(write_still=True)
    else:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.splitext(structure)[0] + ".blend")


main()
'''
