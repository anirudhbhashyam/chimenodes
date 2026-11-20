"""The ``chimenodes`` command family.

merge_params / settings helpers are pure Python (testable without ChimeraX).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .params import Params, TONEMAPS, QUALITIES, RANGES

# command keyword -> Params field
KEYWORDS = {
    "glow": "glow",
    "bloomRadius": "bloom_radius",
    "bloomThreshold": "bloom_threshold",
    "bloomKnee": "bloom_knee",
    "exposure": "exposure",
    "tonemap": "tonemap",
    "ao": "ao",
    "aoRadius": "ao_radius",
    "rim": "rim",
    "dof": "dof",
    "aperture": "aperture",
    "outline": "outline",
    "vignette": "vignette",
    "grain": "grain",
    "fxaa": "fxaa",
    "quality": "quality",
}


def merge_params(base: Params, preset_kwargs: Optional[Dict[str, Any]] = None,
                 overrides: Optional[Dict[str, Any]] = None,
                 preset_name: str = "") -> Params:
    """Return a new clamped Params.

    A preset replaces the whole look (starting from defaults, keeping base.enabled);
    explicit overrides (keys are Params field names, None values ignored) win over it.
    Raises ValueError on invalid enum values, KeyError on unknown field names.
    """
    if preset_kwargs is not None:
        p = Params()
        p.enabled = base.enabled
        p.update(**{k: v for k, v in preset_kwargs.items() if k != "enabled"})
        p.preset = preset_name or p.preset
    else:
        p = Params.from_dict(base.to_dict())
    clean = {k: v for k, v in (overrides or {}).items() if v is not None}
    if clean:
        p.update(**clean)
    return p.clamp()


def keywords_to_overrides(kw: Dict[str, Any]) -> Dict[str, Any]:
    """Map command keyword names to Params field names, dropping None."""
    out = {}
    for k, v in kw.items():
        if v is None:
            continue
        if k in KEYWORDS:
            out[KEYWORDS[k]] = v
    return out


def format_params(p: Params) -> str:
    d = p.to_dict()
    return ", ".join("%s=%s" % (k, ("%.3g" % v) if isinstance(v, float) else v)
                     for k, v in d.items())


# ---------------------------------------------------------------- ChimeraX side

def _get_preset_kwargs(name: str) -> Dict[str, Any]:
    from chimerax.core.errors import UserError
    try:
        from . import presets
    except ImportError:
        raise UserError("chimenodes: presets module is not available")
    try:
        return dict(presets.get_preset(name))
    except Exception:
        names = ", ".join(sorted(getattr(presets, "BUILTIN", {}).keys()))
        raise UserError("chimenodes: unknown preset '%s' (available: %s)" % (name, names))


def _focus_depth(session, focus) -> float:
    """Distance from camera to centre of the atoms along the view direction."""
    from chimerax.core.errors import UserError
    if focus is None or len(focus) == 0:
        return -1.0
    import numpy as np
    xyz = focus.scene_coords
    c = xyz.mean(axis=0)
    cam = session.main_view.camera
    pos = cam.position
    d = np.asarray(c) - pos.origin()
    depth = float(np.dot(d, -pos.axes()[2]))
    if depth <= 0:
        raise UserError("chimenodes: focus atoms are behind the camera")
    return depth


def _commit(session, params: Params, message: bool = True):
    from . import state
    ok = state.apply_params(session, params)
    from chimerax.core.errors import UserError
    if not ok and params.enabled:
        raise UserError("chimenodes: could not enable rendering pipeline "
                        "(see log; OpenGL 3.3 core required)")
    return ok


def chimenodes(session, preset=None, focus=None, **kw):
    from chimerax.core.errors import UserError
    from . import state
    base = state.get_params(session)
    over = keywords_to_overrides(kw)
    if focus is not None:
        over["focus_depth"] = _focus_depth(session, focus)
    pk = _get_preset_kwargs(preset) if preset else None
    try:
        p = merge_params(base, pk, over, preset_name=preset or "")
    except (ValueError, KeyError) as e:
        raise UserError("chimenodes: %s" % e)
    if preset or over:
        p.enabled = True
    _commit(session, p)
    session.logger.status("chimenodes: %s" % ("on" if p.enabled else "off"))


def chimenodes_on(session):
    from . import state
    p = Params.from_dict(state.get_params(session).to_dict())
    p.enabled = True
    if not p.any_post_effect():
        try:
            p = merge_params(p, _get_preset_kwargs("mn_default"), {}, "mn_default")
            p.enabled = True
        except Exception:
            pass
    _commit(session, p)


def chimenodes_off(session):
    from . import state
    p = Params.from_dict(state.get_params(session).to_dict())
    p.enabled = False
    _commit(session, p)


def chimenodes_toggle(session):
    from . import state
    if state.get_params(session).enabled:
        chimenodes_off(session)
    else:
        chimenodes_on(session)


def chimenodes_reset(session):
    _commit(session, Params())


def chimenodes_info(session):
    from . import state
    log = session.logger
    p = state.get_params(session)
    log.info("chimenodes parameters: " + format_params(p))
    try:
        r = session.main_view.render
        r.make_current()
        import OpenGL.GL as gl
        log.info("GL renderer: %s | %s" % (gl.glGetString(gl.GL_RENDERER).decode(),
                                          gl.glGetString(gl.GL_VERSION).decode()))
        log.info("render size: %dx%d" % tuple(r.render_size()))
    except Exception as e:
        log.info("GL info unavailable (%s)" % e)
    try:
        from . import hook
        log.info("pipeline installed: %s" % (hook.get(session) is not None))
    except Exception:
        pass


def _user_presets_path(session):
    import os
    from chimerax import app_dirs
    return os.path.join(app_dirs.user_config_dir, "chimenodes_presets.json")


def chimenodes_preset_save(session, name):
    from chimerax.core.errors import UserError
    from . import state, presets
    if not hasattr(presets, "save_user_preset"):
        raise UserError("chimenodes: preset saving not supported by this build")
    p = state.get_params(session).to_dict()
    for k in ("enabled", "preset"):
        p.pop(k, None)
    presets.save_user_preset(name, p)
    session.logger.info("chimenodes: saved preset '%s'" % name)


def chimenodes_preset_delete(session, name):
    from chimerax.core.errors import UserError
    from . import presets
    if name in getattr(presets, "BUILTIN", {}):
        raise UserError("chimenodes: cannot delete built-in preset '%s'" % name)
    if not hasattr(presets, "delete_user_preset"):
        raise UserError("chimenodes: preset deletion not supported by this build")
    if not presets.delete_user_preset(name):
        raise UserError("chimenodes: no such user preset '%s'" % name)
    session.logger.info("chimenodes: deleted preset '%s'" % name)


def chimenodes_preset_list(session):
    from . import presets
    names = sorted(getattr(presets, "BUILTIN", {}).keys())
    user = []
    if hasattr(presets, "list_presets"):
        try:
            user = [n for n in presets.list_presets() if n not in names]
        except Exception:
            pass
    session.logger.info("chimenodes built-in presets: " + ", ".join(names))
    if user:
        session.logger.info("chimenodes user presets: " + ", ".join(sorted(user)))


def chimenodes_glow(session, objects=None, strength=None, color=None, **kw):
    """`chimenodes glow ATOMSPEC [strength S] [color C]`, or `chimenodes glow F ...`."""
    if isinstance(objects, float):          # global form: chimenodes glow 1.5 ...
        kw["glow"] = objects
        return chimenodes(session, **kw)
    from chimerax.core.errors import UserError
    try:
        from . import glow
    except ImportError:
        raise UserError("chimenodes: glow module is not available")
    if objects is None:
        raise UserError("chimenodes glow: specify atoms or a strength")
    s = 1.0 if strength is None else max(0.0, min(RANGES["glow"][1] * 4, float(strength)))
    rgba = None if color is None else color
    glow.set_glow(session, objects, s, rgba)
    from . import state
    p = state.get_params(session)
    if not p.enabled:
        q = Params.from_dict(p.to_dict())
        q.enabled = True
        if q.glow == 0:
            q.glow = 1.0
        _commit(session, q)


def chimenodes_glow_clear(session, objects=None):
    from chimerax.core.errors import UserError
    try:
        from . import glow
    except ImportError:
        raise UserError("chimenodes: glow module is not available")
    if objects is None:
        from chimerax.atomic import all_atoms
        objects = all_atoms(session)
    glow.clear_glow(session, objects)


def chimenodes_export_blender(session, path, models=None):
    from chimerax.core.errors import UserError
    from . import blender_export
    try:
        out = blender_export.export_blender(session, path, models)
    except OSError as e:
        raise UserError("chimenodes export blender: %s" % e)
    session.logger.info("chimenodes: wrote %s (+ sidecar JSON and render_blender.py)" % out)


def register_commands(logger=None):
    from chimerax.core.commands import (
        CmdDesc, register, BoolArg, FloatArg, EnumOf, StringArg, SaveFileNameArg,
        ColorArg, Annotation, ObjectsArg, ModelsArg)
    from chimerax.atomic import AtomsArg

    class ObjectsOrFloatArg(Annotation):
        name = "atomspec or number"

        @staticmethod
        def parse(text, session):
            try:
                return FloatArg.parse(text, session)
            except Exception:
                return ObjectsArg.parse(text, session)

    kwd = [
        ("preset", StringArg), ("glow", FloatArg), ("bloomRadius", FloatArg),
        ("bloomThreshold", FloatArg), ("bloomKnee", FloatArg),
        ("exposure", FloatArg), ("tonemap", EnumOf(TONEMAPS)),
        ("ao", FloatArg), ("aoRadius", FloatArg), ("rim", FloatArg),
        ("dof", FloatArg), ("aperture", FloatArg), ("focus", AtomsArg),
        ("outline", FloatArg), ("vignette", FloatArg), ("grain", FloatArg),
        ("fxaa", BoolArg), ("quality", EnumOf(QUALITIES)),
    ]
    syn = "Configure MolecularNodes-style rendering"
    register("chimenodes", CmdDesc(keyword=kwd, synopsis=syn), chimenodes,
             logger=logger)
    for name, fn in (("on", chimenodes_on), ("off", chimenodes_off),
                     ("toggle", chimenodes_toggle), ("reset", chimenodes_reset),
                     ("info", chimenodes_info)):
        register("chimenodes " + name, CmdDesc(synopsis="chimenodes " + name), fn,
                 logger=logger)
    register("chimenodes preset save",
             CmdDesc(required=[("name", StringArg)], synopsis="Save current look as preset"),
             chimenodes_preset_save, logger=logger)
    register("chimenodes preset delete",
             CmdDesc(required=[("name", StringArg)], synopsis="Delete a user preset"),
             chimenodes_preset_delete, logger=logger)
    register("chimenodes preset list",
             CmdDesc(synopsis="List presets"), chimenodes_preset_list, logger=logger)
    glow_kw = [k for k in kwd if k[0] not in ("preset", "glow")] + [
        ("strength", FloatArg), ("color", ColorArg)]
    register("chimenodes glow",
             CmdDesc(optional=[("objects", ObjectsOrFloatArg)], keyword=glow_kw,
                     synopsis="Per-object emission, or global glow strength"),
             chimenodes_glow, logger=logger)
    register("chimenodes glow clear",
             CmdDesc(optional=[("objects", ObjectsArg)], synopsis="Clear per-object glow"),
             chimenodes_glow_clear, logger=logger)
    register("chimenodes export blender",
             CmdDesc(required=[("path", SaveFileNameArg)],
                     keyword=[("models", ModelsArg)],
                     synopsis="Export structure + camera/colours for MolecularNodes"),
             chimenodes_export_blender, logger=logger)
