"""MolecularNodes look: ChimeraX lighting/material setup plus composite and
tonemap passes. ChimeraX/GL imports happen lazily so this imports on plain CPython."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

try:
    from .pipeline import Pass
except ImportError:  # pipeline not importable (plain python / not yet written)
    class Pass:  # minimal fallback with the documented interface
        name = "pass"

        def enabled(self, p) -> bool:
            return True

        def run(self, ctx) -> None:
            raise NotImplementedError

# Suggested pipeline orders (A/C slot theirs in between): see report.
ORDER_COMPOSITE = 100
ORDER_TONEMAP = 600

TONEMAP_MODE = {"none": 0, "aces": 1, "filmic": 2, "agx": 3}

# Lighting / material snapshot -------------------------------------------------
_LIGHT_ATTRS = (
    "key_light_direction", "key_light_color", "key_light_intensity",
    "fill_light_direction", "fill_light_color", "fill_light_intensity",
    "ambient_light_color", "ambient_light_intensity",
    "depth_cue", "depth_cue_start", "depth_cue_end", "depth_cue_color",
    "shadows", "shadow_map_size", "shadow_depth_bias",
    "multishadow", "multishadow_map_size", "multishadow_depth_bias",
    "move_lights_with_camera",
)
_MATERIAL_ATTRS = ("ambient_reflectivity", "diffuse_reflectivity",
                   "specular_reflectivity", "specular_exponent")

_saved: Dict[int, Dict[str, Any]] = {}   # id(session) -> snapshot


def _copy(v):
    try:
        return v.copy()           # numpy arrays
    except AttributeError:
        return v


def _snapshot(view) -> Dict[str, Any]:
    snap = {"light": {}, "material": {}, "silhouette": None}
    for a in _LIGHT_ATTRS:
        if hasattr(view.lighting, a):
            snap["light"][a] = _copy(getattr(view.lighting, a))
    for a in _MATERIAL_ATTRS:
        if hasattr(view.material, a):
            snap["material"][a] = _copy(getattr(view.material, a))
    try:
        snap["silhouette"] = bool(view.silhouette.enabled)
    except Exception:
        pass
    return snap


def look_settings(params) -> Dict[str, Any]:
    """Pure-python: the ChimeraX command arguments the look uses (testable)."""
    ms = {"draft": 64, "normal": 192, "high": 512}.get(params.quality, 192)
    ambient = 1.1 if params.ao > 0 else 1.5
    return {
        "lighting": ("intensity 0.7 fillIntensity 0.3 ambientIntensity %.2f "
                     "multiShadow %d msMapSize 1024 msDepthBias 0.01 "
                     "shadows false depthCue false" % (ambient, ms)),
        "material": ("reflectivity 0.8 specularReflectivity 0.4 "
                     "exponent 20 ambientReflectivity 0.8"),
        "silhouettes": False,
    }


def apply_look(session, params) -> None:
    """Configure ChimeraX lighting/material for the MN look, remembering prior state."""
    from chimerax.core.commands import run
    view = session.main_view
    key = id(session)
    if key not in _saved:
        _saved[key] = _snapshot(view)
    s = look_settings(params)
    run(session, "lighting " + s["lighting"], log=False)
    run(session, "material " + s["material"], log=False)
    run(session, "graphics silhouettes false", log=False)


def restore_look(session) -> None:
    """Restore lighting/material/silhouettes saved by apply_look (no-op if none)."""
    snap = _saved.pop(id(session), None)
    if not snap:
        return
    view = session.main_view
    lp, mat = view.lighting, view.material
    for a, v in snap["light"].items():
        try:
            setattr(lp, a, _copy(v))
        except Exception:
            pass
    for a, v in snap["material"].items():
        try:
            setattr(mat, a, _copy(v))
        except Exception:
            pass
    try:
        view.lighting = lp
    except Exception:
        pass
    try:
        view.update_lighting = True
        if snap["silhouette"] is not None:
            view.silhouette.enabled = snap["silhouette"]
    except Exception:
        pass
    view.redraw_needed = True


# Passes ----------------------------------------------------------------------
def _program(ctx, name: str):
    """Compile a shader by name; tonemap lives in tonemap.glsl so try variants."""
    last = None
    for n in (name, name + ".glsl"):
        try:
            return ctx.program(n)
        except Exception as e:  # missing file -> try next spelling
            last = e
    raise last


def _projection_info(ctx):
    """Return (ortho: int, invProj: (x, y)) from the current projection matrix."""
    ortho, sx, sy = 0, 1.0, 1.0
    try:
        P = getattr(ctx.r, "current_projection_matrix")
        sx, sy = float(P[0][0]), float(P[1][1])
        ortho = 1 if abs(float(P[3][3])) > 0.5 else 0
    except Exception:
        pass
    if sx == 0 or sy == 0:
        sx = sy = 1.0
    return ortho, (1.0 / sx, 1.0 / sy)


class CompositePass(Pass):
    name = "mn_composite"

    def enabled(self, p) -> bool:
        return bool(p.enabled and (p.ao > 0 or p.rim > 0))

    def run(self, ctx) -> None:
        p = ctx.params
        w, h = ctx.size
        ortho, inv = _projection_info(ctx)
        radius = max(float(getattr(ctx, "scene_radius", 1.0)), 1e-6) * p.ao_radius
        prog = _program(ctx, "composite")
        ctx.draw_fullscreen(
            prog,
            {"uColor": ctx.color, "uDepth": ctx.depth},
            {"uTexel": (1.0 / w, 1.0 / h), "uNear": float(ctx.near),
             "uFar": float(ctx.far), "uOrtho": ortho, "uInvProj": inv,
             "uAO": float(p.ao), "uAORadius": float(radius), "uRim": float(p.rim)})


class TonemapPass(Pass):
    name = "mn_tonemap"

    def enabled(self, p) -> bool:
        return bool(p.enabled and (p.tonemap != "none" or p.exposure != 0))

    def run(self, ctx) -> None:
        p = ctx.params
        prog = _program(ctx, "tonemap")
        ctx.draw_fullscreen(
            prog, {"uColor": ctx.color},
            {"uExposure": float(p.exposure), "uMode": TONEMAP_MODE[p.tonemap]})


def make_passes() -> List[Tuple[int, Any]]:
    return [(ORDER_COMPOSITE, CompositePass()), (ORDER_TONEMAP, TonemapPass())]
