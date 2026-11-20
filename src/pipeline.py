"""Post-processing pipeline: HDR scene capture + ordered fullscreen passes.

Flow per frame (driven by hook.py):
    pipeline.begin(view, r, camera)  -> pushes an RGBA16F color + depth-texture FBO
    <ChimeraX draws the scene into it>
    pipeline.end(view, r)            -> pops it, runs enabled passes in order, last pass
                                        writes into the framebuffer that was bound before.

Pass authors (look.py / glow.py / lens.py) implement ``Pass`` and expose
``make_passes() -> [(order, Pass), ...]``. Suggested order numbers (any ints work):
    100 look composite, 200 emission add, 300 bloom, 400 dof, 500 outline,
    600 exposure+tonemap, 700 film, 800 fxaa.

Inside ``Pass.run(ctx)`` use ``ctx.draw_fullscreen(ctx.program("name"),
{"uColor": ctx.color, "uDepth": ctx.depth}, {"uStrength": 0.5})``; it renders into
``ctx.target`` unless ``target=`` (an ``alloc``-ed RT) is given. Automatic uniforms, set
for every draw if the program declares them: ``uResolution`` (vec2, target size in px),
``uTexel`` (vec2), ``uNear``, ``uFar``, ``uPerspective`` (int, 0 for orthographic),
``uSceneRadius``. Sampler uniforms named in ``textures`` are bound to units 0..n.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

try:  # pure-python importability
    from .params import Params
except ImportError:  # pragma: no cover
    from params import Params  # type: ignore

_REGISTRY: List[Tuple[int, Any]] = []


class Pass(object):
    """Base class of a post-processing pass."""
    name = "pass"

    def enabled(self, p: Params) -> bool:
        return False

    def run(self, ctx: "PassContext") -> None:
        raise NotImplementedError


def register_pass(order: int, pass_obj: Any) -> None:
    """Register an extra pass globally (picked up by Pipelines created afterwards)."""
    _REGISTRY.append((int(order), pass_obj))


def _collect_module_passes(log=None):
    out: List[Tuple[int, Any]] = []
    for modname in ("look", "glow", "lens"):
        try:
            mod = __import__(__package__ + "." + modname if __package__ else modname,
                             fromlist=["make_passes"])
            out.extend(mod.make_passes())
        except ImportError:
            continue  # module (or one of its optional deps) is not there: skip
        except AttributeError:
            continue  # module has no make_passes yet
        except Exception as e:
            if log is not None:
                log("chimenodes: could not load passes from %s (%s)" % (modname, e))
    return out


class PassContext(object):
    """Everything a pass needs; see module docstring."""

    def __init__(self, pipeline, view, r, camera, scene, final):
        self.pipeline = pipeline
        self.view = view
        self.r = r
        self.params = pipeline.params
        self.size = scene.size
        self.scene = scene
        self.final = final
        self.color = scene.texture
        self.depth = scene.depth_texture
        self.emission = None  # per-frame; never reuse a previous frame's emission
        self.target = final
        self.near, self.far, self.perspective = pipeline.near_far(view, camera)
        self.scene_radius = pipeline.scene_radius(view)
        self.camera = camera
        self.session = pipeline.session
        self.tan_half = pipeline.tan_half(camera, scene.size, self.perspective)
        self.emission_gain = 1.0
        self._wrote = False

    # -- temp render targets
    def alloc(self, w=None, h=None, float=True):
        """Get a temporary RT (use ``rt.texture`` to sample). Release when done."""
        if w is None:
            w = self.size[0]
        if h is None:
            h = self.size[1]
        return self.pipeline.pool.alloc(max(1, int(w)), max(1, int(h)), float)

    def release(self, rt):
        self.pipeline.pool.release(rt)

    def program(self, name, defines=None):
        return self.pipeline.programs.get(name, defines)

    def draw_fullscreen(self, program, textures: Optional[Dict[str, Any]] = None,
                        uniforms: Optional[Dict[str, Any]] = None, target=None):
        """Draw a fullscreen triangle with ``program`` into ``target`` (default ctx.target).

        ``textures`` maps sampler name -> Texture/RT/int GL id. Raises if a sampled texture is
        attached to the target (feedback loop).
        """
        from OpenGL import GL
        tgt = target if target is not None else self.target
        tgt_id = getattr(tgt, "id", None)
        if tgt is self.target:
            self._wrote = True
        tgt.bind(self.r)
        GL.glUseProgram(program.id)
        # ChimeraX caches the current program; invalidate so it re-issues glUseProgram.
        self.r.opengl_context.current_shader_program = None
        units = 0
        for name, tex in (textures or {}).items():
            tid = tex if isinstance(tex, int) else tex.id
            if tid is None:
                raise ValueError("texture '%s' has no GL id" % name)
            if tgt_id is not None and tid == tgt_id:
                raise ValueError("pass samples its own render target (%s)" % name)
            depth = getattr(tgt, "depth_texture", None)
            if depth is not None and tid == depth.id:
                raise ValueError("pass samples a texture attached to its target (%s)" % name)
            GL.glActiveTexture(GL.GL_TEXTURE0 + units)
            GL.glBindTexture(GL.GL_TEXTURE_2D, tid)
            program.set(name, units)
            units += 1
        self.pipeline._max_units = max(self.pipeline._max_units, units)
        w, h = tgt.size
        program.set("uResolution", (float(w), float(h)))
        program.set("uTexel", (1.0 / max(w, 1), 1.0 / max(h, 1)))
        program.set("uNear", float(self.near))
        program.set("uFar", float(self.far))
        program.set("uPerspective", 1 if self.perspective else 0)
        program.set("uSceneRadius", float(self.scene_radius))
        for k, v in (uniforms or {}).items():
            program.set(k, v)
        self.pipeline.geometry.draw()
        GL.glActiveTexture(GL.GL_TEXTURE0)

    def render_emission(self, scope):
        """Re-draw the scene into a float RT inside context manager ``scope`` (glow.py's
        emission_scope), black background; sets ``ctx.emission`` (None on failure)."""
        self.emission = None
        self.pipeline.emission = self.pipeline.render_emission(self, scope)
        self.emission = self.pipeline.emission

    def blit(self, src_texture, target=None):
        """Copy a texture to target (uses built-in blit program)."""
        self.draw_fullscreen(self.pipeline.blit_program(), {"uTex": src_texture}, None, target)


_BLIT_FRAG = """#version 330 core
uniform sampler2D uTex;
out vec4 fragColor;
void main() { fragColor = texelFetch(uTex, ivec2(gl_FragCoord.xy), 0); }
"""


class Pipeline(object):
    def __init__(self, session=None):
        self.session = session
        self.params = Params()
        self.emission = None
        self.passes: List[Tuple[int, Any]] = []
        self.disabled_passes = set()  # names of passes that raised; skipped from then on
        self.reload_passes()
        # GL resources (created lazily, inside a current context)
        self._scene = None
        self._ctx = None
        self.pool = None
        self.programs = None
        self.geometry = None
        self._blit = None
        self._max_units = 0
        self._begun = None
        self._saved = None
        self._draw_args = (None, None, None)
        self._emission_rt = None
        self._emission_busy = False
        self.frames = 0
        self.last_ms = 0.0

    # -- configuration -------------------------------------------------------------
    def reload_passes(self):
        self.disabled_passes.clear()
        log = None
        if self.session is not None:
            log = self.session.logger.warning
        ps = list(_REGISTRY) + _collect_module_passes(log)
        ps.sort(key=lambda t: t[0])
        self.passes = ps

    def set_params(self, params: Params) -> None:
        self.params = params
        try:
            self.session.main_view.redraw_needed = True
        except Exception:
            pass

    def active_passes(self) -> list:
        p = self.params
        if not p.enabled:
            return []
        out = []
        for _o, ps in self.passes:
            if getattr(ps, "name", id(ps)) in self.disabled_passes:
                continue
            try:
                if ps.enabled(p):
                    out.append(ps)
            except Exception:
                continue
        return out

    def is_active(self) -> bool:
        return bool(self.active_passes())

    # -- scene info ----------------------------------------------------------------
    def near_far(self, view, camera):
        perspective = getattr(camera, "name", "") != "orthographic"
        try:
            n, f = view.near_far_distances(camera, 0)
            return float(n), float(f), perspective
        except Exception:
            return 0.1, 100.0, perspective

    def tan_half(self, camera, size, perspective):
        """(x, y) half extents of the view plane at unit distance (ortho: half width/height)."""
        import math
        w, h = size
        try:
            if perspective:
                x = math.tan(math.radians(camera.field_of_view) / 2.0)
            else:
                x = camera.field_width / 2.0
        except Exception:
            x = 1.0
        return (x, x * h / max(w, 1))

    def scene_radius(self, view):
        try:
            b = view.drawing_bounds(allow_drawing_changes=False)
            if b is not None:
                return float(b.radius())
        except Exception:
            pass
        return 1.0

    # -- GL resources ----------------------------------------------------------------
    def _init_gl(self, r):
        if self._ctx is not None:
            return
        from . import fbo
        ctx = r.opengl_context
        self._ctx = ctx
        self.pool = fbo.TargetPool(ctx)
        self.programs = fbo.ProgramCache()
        self.geometry = fbo.FullscreenGeometry()

    def blit_program(self):
        if self._blit is None:
            from . import fbo
            self._blit = fbo.compile_program("blit", self.programs.vertex_source(), _BLIT_FRAG)
        return self._blit

    def _scene_target(self, r, size):
        from . import fbo
        sc = self._scene
        if sc is not None and sc.size != tuple(size):
            sc.delete()
            self._scene = sc = None
            self.pool.purge_except(size)
        if sc is None:
            self._scene = sc = fbo.RT(self._ctx, size, float_=True, depth=True,
                                      name="chimenodes scene")
            self.pool.purge_except(size)
        return sc

    def delete(self, r=None):
        """Release all GL resources (a context should be current)."""
        for obj in (self._scene, self._emission_rt, self.pool, self.programs, self.geometry, self._blit):
            try:
                if obj is not None:
                    obj.delete()
            except Exception:
                pass
        self._emission_rt = None
        self._scene = self.pool = self.programs = self.geometry = self._blit = None
        self._ctx = None

    # -- frame -----------------------------------------------------------------------
    def begin(self, view, r, camera=None, drawings=None, draw_fn=None) -> bool:
        """Push the HDR FBO. Returns False (nothing pushed) if nothing to do."""
        if not self.is_active():
            return False
        w, h = r.render_size()
        if w < 1 or h < 1:
            return False
        self._init_gl(r)
        sc = self._scene_target(r, (w, h))
        r.push_framebuffer(sc.fb)
        self._begun = sc
        self._draw_args = (camera, drawings, draw_fn)
        self._t0 = time.time()
        return True

    def _unwind(self, r):
        """Pop framebuffers down to (and including) our scene FBO. Returns scene RT."""
        sc, self._begun = self._begun, None
        if sc is None:
            return None
        stack = r.framebuffer_stack
        while len(stack) > 1 and stack[-1] is not sc.fb:
            stack.pop()
        if len(stack) > 1 and stack[-1] is sc.fb:
            r.pop_framebuffer()
        else:
            r.current_framebuffer().activate()
        return sc

    def abort(self, view, r):
        """Scene drawing raised: restore framebuffer stack."""
        try:
            self._unwind(r)
        except Exception:
            pass

    def recover(self, view, r, sc=None):
        """Best effort: show the unprocessed scene (used when a pass failed)."""
        try:
            sc = sc or self._scene
            prev = r.current_framebuffer()
            prev.activate()
            r.set_viewport(*prev.viewport)
            prev.copy_from_framebuffer(sc.fb, depth=False)
        except Exception:
            pass

    def end(self, view, r, camera=None) -> None:
        sc = self._unwind(r)
        if sc is None:
            return
        self._enter_state()
        pass_ctx = None
        try:
            final = _final_target(r)
            camera = camera if camera is not None else view.camera
            self.emission = None
            actives = self.active_passes()
            pass_ctx = PassContext(self, view, r, camera, sc, final)
            # Overlays etc. drawn afterwards must not see stale depth.
            final.bind(r)
            from OpenGL import GL
            GL.glDepthMask(True)
            GL.glClear(GL.GL_DEPTH_BUFFER_BIT)
            src = sc
            held = None
            n = len(actives)
            if n == 0:
                pass_ctx.target = final
                pass_ctx.blit(sc.texture)
            for i, ps in enumerate(actives):
                last = (i == n - 1)
                tgt = final if last else pass_ctx.alloc(sc.size[0], sc.size[1], True)
                pass_ctx.color = src.texture
                pass_ctx.target = tgt
                pass_ctx._wrote = False
                try:
                    ps.run(pass_ctx)
                    if not pass_ctx._wrote:
                        # Pass produced nothing for its target (e.g. emission setup):
                        # treat as identity.
                        if tgt is final:
                            pass_ctx.target = final
                            pass_ctx.blit(src.texture)
                            pass_ctx._wrote = True
                except Exception as e:
                    # Per-pass fail-safe: skip just this pass from now on and keep going
                    # with the rest of the chain (identity for this frame).
                    if tgt is not final:
                        pass_ctx.release(tgt)
                    self._disable_pass(ps, e)
                    if tgt is final:
                        try:
                            pass_ctx.target = final
                            pass_ctx.blit(src.texture)
                        except Exception:
                            raise e
                    continue
                if not pass_ctx._wrote:
                    pass_ctx.release(tgt)
                    continue
                if held is not None:
                    pass_ctx.release(held)
                    held = None
                if not last:
                    held = tgt
                    src = tgt
            if held is not None:
                pass_ctx.release(held)
        except Exception:
            self._exit_state()
            self._release_all_temps()
            self.recover(view, r, sc)
            raise
        else:
            self._exit_state()
            self.frames += 1
            self.last_ms = (time.time() - self._t0) * 1000.0

    def _disable_pass(self, ps, exc):
        name = getattr(ps, "name", None) or type(ps).__name__
        self.disabled_passes.add(name)
        try:
            self.session.logger.warning(
                "chimenodes: pass '%s' failed and was disabled (%s: %s)"
                % (name, type(exc).__name__, str(exc)[:300]))
        except Exception:
            pass

    def render_emission(self, ctx, scope):
        """Draw the scene again with ``scope`` active into a float RT; returns its texture."""
        camera, drawings, draw_fn = self._draw_args
        view, r = ctx.view, ctx.r
        if draw_fn is None or self._emission_busy:
            return None
        from . import fbo
        size = ctx.size
        rt = self._emission_rt
        if rt is not None and rt.size != tuple(size):
            rt.delete()
            rt = self._emission_rt = None
        if rt is None:
            rt = self._emission_rt = fbo.RT(self._ctx, size, float_=True, depth=True,
                                            name="chimenodes emission")
        self._emission_busy = True
        self._exit_state()
        stack_len = len(r.framebuffer_stack)
        bg = tuple(r._last_background_color)
        was_redraw = view.redraw_needed
        ok = False
        try:
            with scope:
                _refresh_graphics(view, r)
                r.push_framebuffer(rt.fb)
                try:
                    r.set_background_color((0.0, 0.0, 0.0, 1.0))
                    draw_fn(camera, drawings)
                finally:
                    r.set_background_color(bg)
                    while len(r.framebuffer_stack) > stack_len:
                        r.pop_framebuffer()
            ok = True
        except Exception as e:
            self._warn("emission render failed (%s); glow uses scene colors" % e)
        finally:
            while len(r.framebuffer_stack) > stack_len:
                r.framebuffer_stack.pop()
            r.current_framebuffer().activate()
            r.set_viewport(*r.current_framebuffer().viewport)
            _refresh_graphics(view, r, restore_flag=was_redraw)
            self._emission_busy = False
            self._enter_state()
        return rt.texture if ok else None

    def _warn(self, msg):
        try:
            from . import hook
            hook._log_once(self.session, msg, "chimenodes: " + msg)
        except Exception:
            pass

    def _release_all_temps(self):
        try:
            self.pool.reset()
        except Exception:
            pass

    # -- GL state --------------------------------------------------------------------
    def _enter_state(self):
        from OpenGL import GL
        caps = (GL.GL_DEPTH_TEST, GL.GL_BLEND, GL.GL_CULL_FACE, GL.GL_SCISSOR_TEST)
        saved = {c: bool(GL.glIsEnabled(c)) for c in caps}
        self._saved = (saved, int(GL.glGetIntegerv(GL.GL_VERTEX_ARRAY_BINDING)),
                       bool(GL.glGetBooleanv(GL.GL_DEPTH_WRITEMASK)))
        for c in caps:
            GL.glDisable(c)
        GL.glColorMask(True, True, True, True)
        self._max_units = 0

    def _exit_state(self):
        from OpenGL import GL
        if self._saved is None:
            return
        saved, vao, dmask = self._saved
        self._saved = None
        for c, on in saved.items():
            (GL.glEnable if on else GL.glDisable)(c)
        GL.glDepthMask(dmask)
        GL.glBindVertexArray(vao)
        for u in range(self._max_units):
            GL.glActiveTexture(GL.GL_TEXTURE0 + u)
            GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glUseProgram(0)
        if self._ctx is not None:
            self._ctx.current_shader_program = None


def _refresh_graphics(view, r, restore_flag=None):
    """Make ChimeraX pick up drawing/lighting changes made while drawing a frame."""
    try:
        trig = view.triggers
        if trig:
            trig.activate_trigger('graphics update', view)
        try:
            view._drawing_manager.clear_changes()
        except Exception:
            pass
        view.update_lighting = False
        r.set_lighting_shader_capabilities()
        r.update_lighting_parameters()
        r.activate_lighting()
        view.update_lighting = True   # make the next real frame reload stock lighting
        if restore_flag is not None:
            view.redraw_needed = restore_flag
    except Exception:
        pass


def _final_target(r):
    from . import fbo
    return fbo.FinalTarget(r.current_framebuffer())
