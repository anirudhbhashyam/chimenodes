"""Render the docs showcase assets (stills, comparisons, effects gallery, binding animation).

Run ONCE inside a ChimeraX GUI session (needs network the first time to fetch PDB entries):

    CHIMENODES_ASSETS=docs/assets ChimeraX --exit --script tools/showcase/render_showcase.py

Optional: CHIMENODES_SCENES=er,sav,abl,mdm2,gallery  (subset), CHIMENODES_SRC=<path to src>.
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
WANT = [s for s in (os.environ.get("CHIMENODES_SCENES") or "er,sav,abl,mdm2,gallery").split(",") if s]
os.makedirs(OUT, exist_ok=True)
REPORT = {"scenes": {}}
BG = "#04050a"


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

    def save_jpg(img, name, q=90):
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
    LOOK = "chimenodes preset mn_default ao 1 glow 1.5 bloomRadius 0.32 tonemap agx exposure 0.25 vignette 0.3"

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

    def render_pair(key, ligand, ligand_hex, strength, w=1600, h=1000):
        # stock
        R("chimenodes off")
        save_jpg(shot(w, h, 2), "%s_stock.jpg" % key)
        # chimenodes
        R(LOOK)
        R("chimenodes glow :%s strength %s color %s" % (ligand, strength, ligand_hex))
        save_jpg(shot(w, h, 3), "%s_mn.jpg" % key)

    @scene("er")
    def _():
        pocket_scene("3ert", "A", "OHT", "#7d8db0", "#ffa02e", 3, 9)
        render_pair("er", "OHT", "#ffa02e", 3)
        # hero banner
        save_jpg(shot(2400, 1200, 3), "hero.jpg", 88)
        return {}

    @scene("sav")
    def _():
        pocket_scene("1stp", "A", "BTN", "#8a96b8", "#2fe3ff", 3, 8)
        render_pair("sav", "BTN", "#2fe3ff", 3)
        return {}

    @scene("abl")
    def _():
        pocket_scene("1iep", "A", "STI", "#8c8fb8", "#ff4fd0", 3, 9, extra="delete /B")
        render_pair("abl", "STI", "#ff4fd0", 3)
        return {}

    @scene("gallery")
    def _():
        pocket_scene("3ert", "A", "OHT", "#7d8db0", "#ffa02e", 3, 9)
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
                R("chimenodes glow :OHT strength 3 color #ffa02e")
                if key in ("look", "agx", "outline"):
                    R("chimenodes glow 0")
            save_jpg(shot(900, 560, 2), "gallery_%s.jpg" % key, 88)
            meta.append({"key": key, "label": label, "command": command})
        return {"variants": meta}

    @scene("mdm2")
    def _():
        from chimerax.geometry import translation  # noqa: F401  (import check only)
        R("open 1ycr")
        R("hide solvent; hide ions; hide H")
        R("cartoon; hide atoms")
        R("color /A #7d8db0 target cr; color /B #7dffb0 target acr")
        R("surface /A enclose /A; color /A #7d8db0 target s; transparency /A 72 target s")
        R("show /B atoms; style /B stick; size /B stickRadius 0.22")
        R("view /A,B pad 0.35")
        from chimerax.atomic import AtomicStructure
        s = [m for m in session.models.list() if isinstance(m, AtomicStructure)][0]
        pep = s.atoms[s.atoms.chain_ids == "B"]
        prot = s.atoms[s.atoms.chain_ids == "A"]
        base = pep.coords.copy()
        direction = base.mean(axis=0) - prot.coords.mean(axis=0)
        direction /= np.linalg.norm(direction)
        # also try to keep the peptide's glow colour
        R("chimenodes preset mn_default ao 1 glow 1.4 bloomRadius 0.32 tonemap agx exposure 0.25 vignette 0.3")
        glow.set_glow(session, pep, 1.6, (0.49, 1.0, 0.69))
        R("view /A,B pad 0.3; zoom 1.2")
        R("chimenodes preset mn_default ao 1 glow 1.4 bloomRadius 0.32 tonemap agx exposure 0.25 vignette 0.3")
        # animation: the p53 peptide approaches the MDM2 pocket, glow intensifies as it docks
        n_in, n_hold = 54, 12
        frames = []
        w, h = 800, 500

        def ease(t):  # ease-out cubic
            return 1.0 - (1.0 - t) ** 3
        for i in range(n_in + n_hold):
            t = min(1.0, i / float(n_in - 1))
            dist = 13.0 * (1.0 - ease(t))
            pep.coords = base + direction * dist
            glow.set_glow(session, pep, 0.4 + 1.3 * ease(t), (0.49, 1.0, 0.69))
            R("turn y 0.7 center /A")
            R("wait 1")
            img = view.image_rgba(w, h, supersample=2)
            frames.append(Image.fromarray(img[..., :3].astype("uint8")))
        frames = frames + frames[::-1][1:-1]  # ping-pong (bind / unbind) for a seamless loop
        path = os.path.join(OUT, "binding.webp")
        try:
            frames[0].save(path, save_all=True, append_images=frames[1:], duration=45, loop=0,
                           quality=82, method=4)
            fmt = "webp"
        except Exception:
            path = os.path.join(OUT, "binding.gif")
            pal = [f.convert("P", palette=Image.ADAPTIVE, colors=256) for f in frames]
            pal[0].save(path, save_all=True, append_images=pal[1:], duration=45, loop=0, optimize=True)
            fmt = "gif"
        frames[len(frames) // 4].save(os.path.join(OUT, "binding_poster.jpg"), quality=88)
        pep.coords = base
        return {"frames": len(frames), "format": fmt, "bytes": os.path.getsize(path)}

    clean()
    with open(os.path.join(OUT, "report.json"), "w") as f:
        json.dump(REPORT, f, indent=1)


try:
    main(session)  # noqa: F821  (provided by ChimeraX --script)
except Exception:
    REPORT["crash"] = traceback.format_exc()
    with open(os.path.join(OUT, "report.json"), "w") as f:
        json.dump(REPORT, f, indent=1)
