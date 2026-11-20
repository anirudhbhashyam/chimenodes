"""Render the docs showcase assets (stills, comparisons, effects gallery, binding animation).

Run ONCE inside a ChimeraX GUI session (needs network the first time to fetch PDB entries):

    CHIMENODES_ASSETS=docs/assets ChimeraX --exit --script tools/showcase/render_showcase.py

Optional: CHIMENODES_SCENES=er,sav,abl,barn,rbd,gallery  (subset), CHIMENODES_SRC=<path to src>.
Writes JPEG/WebP files plus assets/report.json. Each scene is independent; failures are
recorded in the report and the run continues. Python >= 3.9.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.environ.get("CHIMENODES_ASSETS") or os.path.join(ROOT, "docs", "assets")
SRC = os.environ.get("CHIMENODES_SRC") or os.path.join(ROOT, "src")
WANT = [s for s in (os.environ.get("CHIMENODES_SCENES") or "er,sav,abl,barn,rbd,gallery").split(",") if s]
os.makedirs(OUT, exist_ok=True)
REPORT = {"scenes": {}}
BG = "#120C08"   # matches the docs theme


def main(session):
    import numpy as np
    import chimerax
    if "chimerax.chimenodes" not in sys.modules:
        pkg = types.ModuleType("chimerax.chimenodes")
        pkg.__path__ = [SRC]
        sys.modules["chimerax.chimenodes"] = pkg
        chimerax.chimenodes = pkg
    from chimerax.core.commands import run
    from chimerax.chimenodes import hook, cmd, glow
    from PIL import Image
    cmd.register_commands(session.logger)
    view = session.main_view

    def R(c):
        return run(session, c, log=False)

    def save_jpg(img, name, q=92):
        Image.fromarray(img[..., :3].astype("uint8")).save(os.path.join(OUT, name), quality=q, optimize=True)

    def shot(w, h, ss=3):
        R("wait 2")
        return view.image_rgba(w, h, supersample=ss)

    def clean():
        for c in ("chimenodes off", "chimenodes reset", "close", "lighting default",
                  "graphics silhouettes false", "set bgColor %s" % BG):
            try:
                R(c)
            except Exception:
                pass
        try:
            glow.clear_glow(session)
        except Exception:
            pass

    def scene(name):
        def deco(fn):
            if name not in WANT:
                return fn
            t0 = time.time()
            clean()
            try:
                REPORT["scenes"][name] = {"ok": True, "detail": fn() or {}}
            except Exception:
                REPORT["scenes"][name] = {"ok": False, "error": traceback.format_exc()[-1800:]}
            REPORT["scenes"][name]["secs"] = round(time.time() - t0, 1)
            return fn
        return deco

    # Hero look shared by all stills
    LOOK = "chimenodes preset mn_default ao 1 glow 1.0 bloomRadius 0.28 tonemap agx exposure 0.25 vignette 0.3"

    def pocket_scene(pdb, chain, ligand, protein_hex, ligand_hex, strength, slab, extra=""):
        R("open %s" % pdb)
        if extra:
            R(extra)
        R("hide solvent; hide ions; hide H")
        R("cartoon /%s; hide /%s atoms" % (chain, chain))
        R("color /%s %s target cr" % (chain, protein_hex))
        R("surface /%s enclose /%s" % (chain, chain))
        R("color /%s %s target s" % (chain, protein_hex))
        R("transparency /%s 72 target s" % chain)   # after color: color resets opacity
        R("surface cap false")
        R("show :%s atoms; style :%s ball; color :%s %s" % (ligand, ligand, ligand, ligand_hex))
        R("view (:%s :<9) pad 0.06" % ligand)
        R("clip near -%s far %s position :%s" % (slab, slab, ligand))
        return ligand_hex

    def render_pair(key, glow_spec, glow_hex, strength, w=2560, h=1600):
        # stock
        R("chimenodes off")
        save_jpg(shot(w, h, 2), "%s_stock.jpg" % key)
        # chimenodes
        R(LOOK)
        R("chimenodes glow %s strength %s color %s" % (glow_spec, strength, glow_hex))
        save_jpg(shot(w, h, 3), "%s_mn.jpg" % key)

    @scene("er")
    def _():
        pocket_scene("3ert", "A", "OHT", "#7d8db0", "#ffb86b", 3, 9)
        render_pair("er", ":OHT", "#ffb86b", 2)
        # hero banner
        save_jpg(shot(3200, 1600, 3), "hero.jpg", 90)
        return {}

    @scene("sav")
    def _():
        pocket_scene("1stp", "A", "BTN", "#8a96b8", "#2fe3ff", 3, 8)
        render_pair("sav", ":BTN", "#2fe3ff", 2)
        return {}

    @scene("abl")
    def _():
        pocket_scene("1iep", "A", "STI", "#8c8fb8", "#ff4fd0", 3, 9, extra="delete /B")
        render_pair("abl", ":STI", "#ff4fd0", 2)
        return {}

    @scene("gallery")
    def _():
        pocket_scene("3ert", "A", "OHT", "#7d8db0", "#ffb86b", 3, 9)
        variants = [
            ("stock", "ChimeraX default", "chimenodes off"),
            ("look", "MN look (AO + satin)", "chimenodes preset mn_default glow 0 ao 1"),
            ("agx", "+ AgX tone mapping", "chimenodes preset mn_default glow 0 ao 1 tonemap agx exposure 0.25"),
            ("glow", "+ glow", LOOK),
            ("neon", "neon preset", "chimenodes preset neon"),
            ("cinematic", "cinematic preset", "chimenodes preset cinematic"),
            ("dof", "glow + depth of field", LOOK + " dof 1 aperture 0.7"),
            ("outline", "outline", "chimenodes preset mn_default glow 0 ao 1 outline 0.8"),
        ]
        meta = []
        for key, label, command in variants:
            R("chimenodes off")
            R(command)
            if key != "stock":
                R("chimenodes glow :OHT strength 2 color #ffb86b")
                if key in ("look", "agx", "outline"):
                    R("chimenodes glow 0")
            save_jpg(shot(1280, 800, 2), "gallery_%s.jpg" % key, 90)
            meta.append({"key": key, "label": label, "command": command})
        return {"variants": meta}

    def binder_scene(pdb, target, binder, t_hex, b_hex, zoom=0.8):
        """Target as a translucent surface, binder glowing on top of it, seen side-on."""
        from chimerax.atomic import AtomicStructure
        from chimerax.geometry import Place
        R("open %s" % pdb)
        R("delete ~protein; delete ~/%s,%s" % (target, binder))
        R("hide solvent; hide ions; hide H")
        R("cartoon; hide atoms")
        R("color /%s %s target c" % (target, t_hex))
        R("surface /%s enclose /%s" % (target, target))
        R("color /%s %s target s" % (target, t_hex))
        R("transparency /%s 72 target s" % target)
        R("surface cap false")
        R("color /%s %s target abc" % (binder, b_hex))
        R("show ((/%s :<4.5) & /%s) atoms; style stick; size stickRadius 0.2" % (target, binder))
        # camera: look perpendicular to the target->binder axis, binder up, contact in the middle
        st = [m for m in session.models.list() if isinstance(m, AtomicStructure)][0]
        bc = st.atoms[st.atoms.chain_ids == binder].scene_coords.mean(axis=0)
        tc = st.atoms[st.atoms.chain_ids == target].scene_coords.mean(axis=0)
        d = bc - tc
        d /= np.linalg.norm(d)
        ref = np.array([0.0, 0.0, 1.0]) if abs(d[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        v = np.cross(d, ref)
        v /= np.linalg.norm(v)            # view direction
        z = -v
        y = -d                            # binder ends up on top, landing on its target
        x = np.cross(y, z)
        o = bc + z * 200.0
        view.camera.position = Place(matrix=((x[0], y[0], z[0], o[0]),
                                             (x[1], y[1], z[1], o[1]),
                                             (x[2], y[2], z[2], o[2])))
        R("view /%s :<12 pad 0.05; zoom %s" % (binder, zoom))

    @scene("barn")
    def _():
        binder_scene("1brs", "A", "D", "#7d8db0", "#7dffb0", zoom=1.2)      # barnase (target) / barstar (binder)
        render_pair("barn", "/D", "#7dffb0", 0.7)
        return {}

    @scene("rbd")
    def _():
        binder_scene("6m0j", "A", "E", "#7d8db0", "#b78cff", zoom=0.95)      # ACE2 (target) / SARS-CoV-2 RBD (binder)
        render_pair("rbd", "/E", "#b78cff", 0.7)
        return {}

    clean()
    with open(os.path.join(OUT, "report.json"), "w") as f:
        json.dump(REPORT, f, indent=1)


try:
    main(session)  # noqa: F821  (provided by ChimeraX --script)
except Exception:
    REPORT["crash"] = traceback.format_exc()
    with open(os.path.join(OUT, "report.json"), "w") as f:
        json.dump(REPORT, f, indent=1)
