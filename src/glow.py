"""Glow for chimenodes: dual-Kawase bloom + per-object emission.

Pass assumptions about A's PassContext (see docs/ARCHITECTURE.md), documented here because the
contract leaves them open:
  * ctx.alloc(w, h, float=True) -> rt with ``.texture`` and ``.framebuffer`` (or a 2-tuple (tex, fb));
    ctx.release(rt) returns it to the pool.
  * ctx.draw_fullscreen(program, textures, uniforms, target=None): draws into ``target`` (an rt from
    alloc) or, when None, into ctx.target. Shaders derive UVs from gl_FragCoord, so no vertex varying
    is required from fullscreen.vert.
  * Emission: ctx.render_emission(scope) re-draws the scene into an RGBA16F target while ``scope``
    (a context manager from glow.emission_scope) is entered, then sets ctx.emission (and optionally
    ctx.emission_gain, default 1.0; the colour sent to the framebuffer is divided by this gain so
    strengths > 1 survive 8-bit vertex colours). ctx.emission is None when no emission was rendered.
"""
from __future__ import annotations

import contextlib
import math

try:  # Pass base class lives in pipeline.py (owner A); minimal fallback keeps this importable.
    from .pipeline import Pass  # type: ignore
except Exception:  # pragma: no cover - plain Python / circular import
    class Pass:  # type: ignore
        name = "pass"

        def enabled(self, p):
            return True

        def run(self, ctx):
            raise NotImplementedError

# Pass orders (low runs first). B's tonemap sits at 500 by convention.
ORDER_EMISSION = 150
ORDER_BLOOM = 200

ATTR = "glow"
_STORE = "_chimenodes_glow"      # structure attribute: dict(strength=float32[N], color=float32[N,3] or None)


# ----------------------------------------------------------------------------- pure helpers
def luminance(r, g, b):
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def soft_knee_weight(l, threshold, knee):
    """Multiplier applied to a colour of luminance l (matches bright.frag)."""
    w = min(max(l - threshold + knee, 0.0), 2.0 * knee)
    w = w * w / (4.0 * knee + 1e-4)
    return max(l - threshold, w) / max(l, 1e-4)


def max_levels(quality):
    return {"draft": 5, "normal": 6, "high": 7}.get(quality, 6)


def bloom_levels(quality, radius, height):
    """Number of downsample levels (>=1) for the given radius fraction (0..1) and image height.

    Returns (levels, offset): offset (0.75..1.5) fine-tunes the tap spread so radius changes
    continuously between integer level counts.
    """
    top = max_levels(quality)
    # never go below ~4 px tall
    cap = max(1, int(math.floor(math.log2(max(height, 8) / 4.0))))
    top = min(top, cap)
    x = math.sqrt(min(max(radius, 0.0), 1.0)) * (top - 1) + 1.0   # 1..top
    n = int(math.floor(x + 1e-6))
    n = max(1, min(top, n))
    frac = min(max(x - n, 0.0), 1.0) if n < top else 0.0
    return n, 0.75 + 0.75 * frac


def bloom_norm(levels):
    """Energy normalisation so intensity feels similar across level counts."""
    return 1.0


def down_weights():
    """5-tap dual-Kawase downsample weights: centre, 4 diagonals."""
    return (4.0 / 8.0, 1.0 / 8.0, 1.0 / 8.0, 1.0 / 8.0, 1.0 / 8.0)


def tent_weights():
    """8-tap dual-Kawase upsample weights (4 axis taps weight 1, 4 diagonal weight 2) / 12."""
    return tuple(w / 12.0 for w in (1, 2, 1, 2, 1, 2, 1, 2))


def level_sizes(width, height, levels):
    out = []
    w, h = width, height
    for _ in range(levels):
        w, h = max(1, w // 2), max(1, h // 2)
        out.append((w, h))
    return out


# ----------------------------------------------------------------------------- GL helpers
def _rt_parts(rt):
    tex = getattr(rt, "texture", None)
    if tex is None:
        tex = rt[0]
    return tex


def _draw(ctx, prog, textures, uniforms, target=None):
    if target is None:
        ctx.draw_fullscreen(prog, textures, uniforms)
    else:
        ctx.draw_fullscreen(prog, textures, uniforms, target=target)


class BloomPass(Pass):
    name = "bloom"

    def enabled(self, p):
        return bool(p.enabled and p.glow > 0)

    def run(self, ctx):
        p = ctx.params
        w, h = ctx.size
        emission = getattr(ctx, "emission", None)
        src = emission if emission is not None else ctx.color
        src_tex = src
        n, offset = bloom_levels(p.quality, p.bloom_radius, h)
        sizes = level_sizes(w, h, n)
        bright, down, up = ctx.program("bright"), ctx.program("down"), ctx.program("up")

        rts = []
        try:
            rt = ctx.alloc(sizes[0][0], sizes[0][1], float=True)
            rts.append(rt)
            if emission is not None:
                thr, knee = 0.0, 0.0
            else:
                thr, knee = p.bloom_threshold, max(p.bloom_knee, 1e-3)
            _draw(ctx, bright, {"uSrc": src_tex},
                  {"uOutSize": (float(sizes[0][0]), float(sizes[0][1])), "uThreshold": float(thr),
                   "uKnee": float(knee), "uKaris": 1.0}, target=rt)
            for i in range(1, n):
                rt = ctx.alloc(sizes[i][0], sizes[i][1], float=True)
                rts.append(rt)
                _draw(ctx, down, {"uSrc": _rt_parts(rts[i - 1])},
                      {"uOutSize": (float(sizes[i][0]), float(sizes[i][1])), "uOffset": float(offset)},
                      target=rt)
            # upsample chain, pure tent (each level replaces the next-higher one)
            cur = rts[-1]
            dummy = ctx.color
            for i in range(n - 2, -1, -1):
                dst = ctx.alloc(sizes[i][0], sizes[i][1], float=True)
                rts.append(dst)       # tracked for release; down levels stay readable
                _draw(ctx, up, {"uSrc": _rt_parts(cur), "uBase": dummy, "uAdd": dummy},
                      {"uOutSize": (float(sizes[i][0]), float(sizes[i][1])), "uOffset": float(offset),
                       "uSrcWeight": 1.0, "uBaseWeight": 0.0, "uAddWeight": 0.0}, target=dst)
                cur = dst
            gain = float(getattr(ctx, "emission_gain", 1.0)) if emission is not None else 0.0
            _draw(ctx, up, {"uSrc": _rt_parts(cur), "uBase": ctx.color,
                            "uAdd": emission if emission is not None else ctx.color},
                  {"uOutSize": (float(w), float(h)), "uOffset": float(offset),
                   "uSrcWeight": float(p.glow) * bloom_norm(n), "uBaseWeight": 1.0,
                   "uAddWeight": gain})
        finally:
            for rt in rts:
                try:
                    ctx.release(rt)
                except Exception:
                    pass


class EmissionPass(Pass):
    """Asks the pipeline to render the scene with glow-only colours into ctx.emission."""
    name = "emission"

    def enabled(self, p):
        return bool(p.enabled and p.glow > 0 and has_glow_objects(_STATE.session))

    def run(self, ctx):
        render = getattr(ctx, "render_emission", None)
        if render is None:
            ctx.emission = None
            return
        session = getattr(ctx, "session", None) or _STATE.session
        ctx.emission_gain = emission_gain(session)
        render(emission_scope(session))


def make_passes():
    return [(ORDER_EMISSION, EmissionPass()), (ORDER_BLOOM, BloomPass())]


# ----------------------------------------------------------------------------- per-object glow
class _State:
    session = None


_STATE = _State()


def _register_attrs(session):
    try:
        from chimerax.atomic import Atom, Residue, Structure
    except Exception:
        return
    for cls in (Atom, Residue, Structure):
        try:
            cls.register_attr(session, ATTR, "chimenodes", attr_type=float)
        except Exception:
            pass


def _structures(session):
    try:
        from chimerax.atomic import Structure
        return [m for m in session.models.list() if isinstance(m, Structure)]
    except Exception:
        return []


def has_glow_objects(session):
    if session is None:
        return False
    for s in _structures(session):
        d = getattr(s, _STORE, None)
        if d is not None and len(d["strength"]) == s.num_atoms and (d["strength"] > 0).any():
            return True
    return False


def _hue_only(rgb):
    """Scale colours so the brightest channel is 1: dark chains glow as strongly as light ones
    (Blender-style emission colour with a separate strength)."""
    import numpy as np
    rgb = np.asarray(rgb, np.float32)
    m = rgb.max(axis=1, keepdims=True)
    return np.where(m > 1e-4, rgb / np.maximum(m, 1e-4), 1.0).astype(np.float32)


def emission_gain(session):
    """Max glow strength over all structures (>=1); emission textures are divided by this."""
    g = 1.0
    for s in _structures(session):
        d = getattr(s, _STORE, None)
        if d is not None and len(d["strength"]) == s.num_atoms and len(d["strength"]):
            g = max(g, float(d["strength"].max()))
    return g


def _entry(s):
    import numpy as np
    d = getattr(s, _STORE, None)
    n = s.num_atoms
    if d is None or len(d["strength"]) != n:
        d = {"strength": np.zeros(n, np.float32), "color": np.zeros((n, 3), np.float32),
             "has_color": np.zeros(n, bool)}
        setattr(s, _STORE, d)
    return d


def set_glow(session, objects, strength, color=None):
    """Give atoms (or whole structures) in `objects` an emission `strength` (>=0), optional colour.

    `objects` is a chimerax Objects instance, an Atoms collection or a Structure. color is an RGB(A)
    tuple of 0..255 or 0..1 floats / uint8 array; None keeps the atom's own colour.
    """
    import numpy as np
    _STATE.session = session
    _register_attrs(session)
    strength = max(0.0, float(strength))
    groups = []
    atoms = getattr(objects, "atoms", None)
    if atoms is None and hasattr(objects, "by_structure"):
        atoms = objects
    if atoms is not None:
        groups.extend(atoms.by_structure)
    models = getattr(objects, "models", None)
    if models is None and hasattr(objects, "num_atoms") and not hasattr(objects, "by_structure"):
        models = [objects]
    for m in models or []:
        if hasattr(m, "atoms") and hasattr(m, "num_atoms"):
            groups.append((m, m.atoms))
    rgb = None
    if color is not None:
        if hasattr(color, "rgba"):  # chimerax.core.colors.Color
            color = color.rgba
        c = np.array(color[:3], np.float32)
        rgb = c / 255.0 if c.max() > 1.0 else c
    count = 0
    for s, a in groups:
        d = _entry(s)
        idx = s.atoms.indices(a)
        idx = idx[idx >= 0]
        d["strength"][idx] = strength
        if rgb is not None:
            d["color"][idx] = rgb
            d["has_color"][idx] = True
        elif strength == 0:
            d["has_color"][idx] = False
        for at in (a if len(a) <= 5000 else []):
            try:
                setattr(at, ATTR, strength)
            except Exception:
                break
        count += len(idx)
    return count


def clear_glow(session, objects=None):
    """Remove emission from `objects` (all structures when None)."""
    if objects is None:
        for s in _structures(session):
            if getattr(s, _STORE, None) is not None:
                delattr(s, _STORE)
        return
    set_glow(session, objects, 0.0)


@contextlib.contextmanager
def emission_scope(session):
    """Temporarily recolour scene so only glowing atoms are lit (black elsewhere), flat lit.

    Yields the gain (max strength) the caller must apply when adding the emission texture:
    drawn colour = base * strength / gain, so final = drawn * gain.
    """
    import numpy as np
    saved = []
    gain = 1.0
    view = session.main_view
    lighting = view.lighting
    lkeys = ("key_light_intensity", "fill_light_intensity", "ambient_light_intensity",
             "shadows", "multishadow", "depth_cue")
    lsaved = {k: getattr(lighting, k) for k in lkeys}
    try:
        structs = []
        for s in _structures(session):
            d = getattr(s, _STORE, None)
            if d is None or len(d["strength"]) != s.num_atoms:
                continue
            structs.append((s, d))
            gain = max(gain, float(d["strength"].max()))
        for s, d in structs:
            atoms = s.atoms
            res = s.residues
            saved.append((s, atoms.colors.copy(), res.ribbon_colors.copy()))
            base = atoms.colors.astype(np.float32) / 255.0
            col = np.where(d["has_color"][:, None], d["color"], base[:, :3])
            col = _hue_only(col)  # glow brightness comes from strength, not from albedo
            out = np.zeros((len(atoms), 4), np.float32)
            out[:, :3] = col * (d["strength"][:, None] / gain)
            out[:, 3] = 1.0
            atoms.colors = np.clip(out * 255.0 + 0.5, 0, 255).astype(np.uint8)
            # ribbons: black unless any atom of the residue glows
            rs = np.zeros(len(res), np.float32)
            ridx = res.indices(atoms.residues)
            ok = ridx >= 0
            np.maximum.at(rs, ridx[ok], d["strength"][ok] / gain)
            rc = res.ribbon_colors.astype(np.float32)
            rc[:, :3] = _hue_only(rc[:, :3] / 255.0) * 255.0 * rs[:, None]
            res.ribbon_colors = np.clip(rc + 0.5, 0, 255).astype(np.uint8)
        lighting.key_light_intensity = 0.0
        lighting.fill_light_intensity = 0.0
        lighting.ambient_light_intensity = 1.45
        lighting.shadows = False
        lighting.multishadow = 0
        lighting.depth_cue = False
        yield gain
    finally:
        for s, ac, rc in saved:
            try:
                s.atoms.colors = ac
                s.residues.ribbon_colors = rc
            except Exception:
                pass
        for k, v in lsaved.items():
            try:
                setattr(lighting, k, v)
            except Exception:
                pass
