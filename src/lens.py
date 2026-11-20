"""Lens effects for chimenodes: DOF, outline, SSAO helper, FXAA, film (vignette/grain/CA).

PassContext assumptions are listed at the top of glow.py (alloc/release rt objects with
``.texture``; ctx.draw_fullscreen(program, textures, uniforms, target=None)). All shaders derive UVs
from gl_FragCoord, so only the fragment shaders are needed. Every pass is skipped (zero cost) when its
parameters are zero. Passes read ctx.color / ctx.depth and write ctx.target.
"""
from __future__ import annotations

import math

try:  # Pass base class lives in pipeline.py (owner A); minimal fallback keeps this importable.
    from .pipeline import Pass  # type: ignore
except Exception:  # pragma: no cover
    class Pass:  # type: ignore
        name = "pass"

        def enabled(self, p):
            return True

        def run(self, ctx):
            raise NotImplementedError

# Pass orders (low runs first). B's tonemap sits at 500 by convention; bloom is 200 (glow.py).
ORDER_DOF = 300
ORDER_OUTLINE = 400
ORDER_FILM = 650
ORDER_FXAA = 700


# ----------------------------------------------------------------------------- pure helpers
def linearize_depth(d, near, far, ortho=False):
    """Window depth (0..1) -> eye distance. Matches dof.frag."""
    if ortho:
        return near + d * (far - near)
    return near * far / max(far - d * (far - near), 1e-6)


def auto_focus(near, far):
    """Auto focus distance: ChimeraX fits near/far to the scene bounds, so the midpoint ~ centre."""
    return 0.5 * (near + far)


def focus_distance(params, near, far, override=None):
    if override is not None and override > 0:
        return float(override)
    if params.focus_depth is not None and params.focus_depth >= 0:
        return float(params.focus_depth)
    return auto_focus(near, far)


def aperture_scale(dof, aperture):
    """Effective aperture (CoC growth); aperture 0 with dof>0 falls back to a mild default."""
    return aperture if aperture > 0 else 0.25


def max_coc_px(dof, height):
    """Maximum circle-of-confusion radius in pixels (resolution relative)."""
    return max(0.0, dof) * 0.03 * height


def coc_px(z, focus, aperture, dof, height):
    """Circle of confusion radius in pixels for eye distance z. Matches dof.frag."""
    c = abs(z - focus) / max(focus, 1e-4) * aperture_scale(dof, aperture)
    return min(c, 1.0) * max_coc_px(dof, height)


def dof_taps(quality):
    return {"draft": 16, "normal": 24, "high": 32}.get(quality, 24)


def vignette_factor(x, y, aspect=1.0, strength=1.0):
    """Multiplier at normalised coordinates x,y in 0..1 (matches film.frag)."""
    qx, qy = (x - 0.5) * aspect, (y - 0.5)
    r = math.hypot(qx, qy) / 0.7071
    t = min(max((r - 0.35) / (1.2 - 0.35), 0.0), 1.0)
    v = t * t * (3 - 2 * t)
    return 1.0 - strength * v * v


def outline_thickness(height, strength):
    return max(1.0, height / 1080.0) * (1.0 + strength)


# ----------------------------------------------------------------------------- passes
def _o(ctx):
    return 1 if getattr(ctx, "orthographic", False) else 0


class DofPass(Pass):
    name = "dof"

    def enabled(self, p):
        return bool(p.enabled and p.dof > 0)

    def run(self, ctx):
        p = ctx.params
        w, h = ctx.size
        ctx.draw_fullscreen(ctx.program("dof"), {"uColor": ctx.color, "uDepth": ctx.depth}, {
            "uNear": float(ctx.near), "uFar": float(ctx.far),
            "uFocus": focus_distance(p, ctx.near, ctx.far, getattr(ctx, "focus_distance", None)),
            "uAperture": float(aperture_scale(p.dof, p.aperture)),
            "uMaxCoc": float(max_coc_px(p.dof, h)),
            "uTaps": int(dof_taps(p.quality)), "uOrtho": _o(ctx)})


class OutlinePass(Pass):
    name = "outline"

    def enabled(self, p):
        return bool(p.enabled and p.outline > 0)

    def run(self, ctx):
        p = ctx.params
        w, h = ctx.size
        ctx.draw_fullscreen(ctx.program("outline"), {"uColor": ctx.color, "uDepth": ctx.depth}, {
            "uNear": float(ctx.near), "uFar": float(ctx.far), "uOrtho": _o(ctx),
            "uStrength": float(p.outline), "uThickness": float(outline_thickness(h, p.outline)),
            "uColorOut": (0.0, 0.0, 0.0)})


class FilmPass(Pass):
    name = "film"

    def enabled(self, p):
        return bool(p.enabled and (p.vignette > 0 or p.grain > 0))

    def run(self, ctx):
        p = ctx.params
        w, h = ctx.size
        ctx.draw_fullscreen(ctx.program("film"), {"uColor": ctx.color}, {
            "uVignette": float(p.vignette), "uGrain": float(p.grain),
            "uChroma": float(getattr(ctx, "chroma", 0.0)),
            "uSeed": float(getattr(ctx, "frame_seed", 0.0)),
            "uGrainCell": float(max(1.0, h / 1080.0))})


class FxaaPass(Pass):
    name = "fxaa"

    def enabled(self, p):
        return bool(p.enabled and p.fxaa)

    def run(self, ctx):
        ctx.draw_fullscreen(ctx.program("fxaa"), {"uColor": ctx.color}, {
            "uSubpix": 0.75, "uEdgeThreshold": 0.166, "uEdgeThresholdMin": 0.0833})


def make_passes():
    return [(ORDER_DOF, DofPass()), (ORDER_OUTLINE, OutlinePass()),
            (ORDER_FILM, FilmPass()), (ORDER_FXAA, FxaaPass())]


def ssao_uniforms(ctx, radius, strength=1.0, samples=16):
    """Uniform dict for ssao.frag mode 0 (B calls this if it wants SSAO; see ssao.frag header).

    Run at half res: uOutSize = half size; then mode 1 twice with uDir=(1,0) and (0,1).
    ``ctx.tan_half`` (tan(fov/2)*aspect, tan(fov/2)) or ortho half extents should come from the camera.
    """
    return {"uNear": float(ctx.near), "uFar": float(ctx.far), "uOrtho": _o(ctx),
            "uTanHalf": tuple(getattr(ctx, "tan_half", (1.0, 1.0))),
            "uRadius": float(radius), "uStrength": float(strength), "uSamples": int(samples)}
