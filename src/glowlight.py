"""Glow light: glowing atoms act as point lights that tint nearby surfaces (screen space).

Pass assumptions: see glow.py header. Uses ctx.camera.position (Place, camera -> scene) to bring
scene-space emitter positions into view space, ctx.tan_half / ctx.near / ctx.far / ctx.perspective
for depth reconstruction. Requires glow.emitter_lights(session, max_lights).
"""
from __future__ import annotations

try:  # Pass base class lives in pipeline.py; minimal fallback keeps this importable.
    from .pipeline import Pass  # type: ignore
except Exception:  # pragma: no cover
    class Pass:  # type: ignore
        name = "pass"

        def enabled(self, p):
            return True

        def run(self, ctx):
            raise NotImplementedError

ORDER_GLOWLIGHT = 160
MAX_LIGHTS = 32
DEFAULT_RADIUS = 6.0


def effective_radius(radius):
    return float(radius) if radius and radius > 0 else DEFAULT_RADIUS


def to_view_space(camera, positions):
    """Scene-space (N,3) float32 -> camera/view space."""
    import numpy as np
    pos = np.ascontiguousarray(positions, dtype=np.float32)
    try:
        return np.asarray(camera.position.inverse().transform_points(pos), np.float32)
    except Exception:
        m = np.asarray(camera.position.inverse().matrix, np.float64)  # 3x4
        return (pos @ m[:, :3].T + m[:, 3]).astype(np.float32)


class GlowLight(Pass):
    name = "glowlight"

    def enabled(self, p):
        return bool(p.glow_light > 0)

    def run(self, ctx):
        import numpy as np
        try:
            from .glow import emitter_lights
        except ImportError:  # pragma: no cover
            from glow import emitter_lights  # type: ignore
        p = ctx.params
        session = getattr(ctx, "session", None)
        positions, colors = emitter_lights(session, MAX_LIGHTS)
        n = min(len(positions), MAX_LIGHTS)
        if n == 0:
            return
        vpos = to_view_space(ctx.camera, np.asarray(positions, np.float32)[:n])
        cols = np.asarray(colors, np.float32)[:n]
        # Many lights describe one extended source, not n separate lamps: keep total energy sane.
        cols = cols / float(max(1.0, (n / 4.0)) ** 0.5)
        emission = getattr(ctx, "emission", None)
        uniforms = {
            "uOrtho": 0 if ctx.perspective else 1,
            "uTanHalf": tuple(getattr(ctx, "tan_half", (1.0, 1.0))),
            "uOutSize": (float(ctx.size[0]), float(ctx.size[1])),
            "uCount": int(n),
            "uStrength": float(p.glow_light),
            "uRadius": effective_radius(p.glow_light_radius),
            "uGain": float(getattr(ctx, "emission_gain", 1.0)),
            "uHasEmission": 1 if emission is not None else 0,
        }
        for i in range(n):
            uniforms["uLightPos[%d]" % i] = tuple(float(x) for x in vpos[i])
            uniforms["uLightCol[%d]" % i] = tuple(float(x) for x in cols[i])
        textures = {"uColor": ctx.color, "uDepth": ctx.depth,
                    "uEmission": emission if emission is not None else ctx.color}
        ctx.draw_fullscreen(ctx.program("glowlight"), textures, uniforms)


def make_passes():
    return [(ORDER_GLOWLIGHT, GlowLight())]
