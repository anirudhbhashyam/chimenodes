"""GPU helpers for chimenodes: float render targets, shader programs, fullscreen draw.

Everything here imports OpenGL / chimerax.graphics lazily so the module can be imported
on plain CPython. Targets are built on ChimeraX's own ``Framebuffer`` / ``Texture`` classes so
they integrate with ``Render.push_framebuffer`` (ChimeraX's built-in 16-bit path is UNORM, we
need RGBA16F, so textures are created here with explicit internal formats).

Shader conventions (see also pipeline.PassContext.draw_fullscreen):
  * fragment shaders live in ``shaders/<name>.frag``, ``#version 330 core``;
    ``#include "file.glsl"`` is expanded (once per program) from the shaders directory;
  * the vertex shader is ``shaders/fullscreen.vert``. It may use ``gl_VertexID`` (preferred) or
    a ``vec2`` attribute at location 0 (a clip space fullscreen triangle is bound there);
  * unknown uniforms are ignored (location -1), never an error.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

SHADER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shaders")

# Used only when shaders/fullscreen.vert is missing.
_FALLBACK_VERT = """#version 330 core
out vec2 uv;
out vec2 vUV;
out vec2 v_uv;
out vec2 texcoord;
out vec2 vTexCoord;
void main() {
    vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
    uv = p; vUV = p; v_uv = p; texcoord = p; vTexCoord = p;
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
"""

_POSITION_NAMES = ("position", "aPos", "a_pos", "a_position", "aPosition", "pos",
                   "in_pos", "in_position", "vertex", "inPosition")


class GLUnsupported(RuntimeError):
    pass


def _gl():
    from OpenGL import GL
    return GL


# --------------------------------------------------------------------------------------
# Render targets
# --------------------------------------------------------------------------------------
class RT(object):
    """A color render target (+ optional depth texture). Wraps a ChimeraX Framebuffer."""

    def __init__(self, ctx, size, float_=True, depth=False, name="chimenodes"):
        GL = _gl()
        from chimerax.graphics.opengl import Texture, Framebuffer
        self.size = (int(size[0]), int(size[1]))
        self.float = bool(float_)
        self.texture = Texture(linear_interpolation=True, clamp_to_edge=True)
        if float_:
            self.texture.initialize_texture(self.size, GL.GL_RGBA, GL.GL_RGBA16F,
                                            GL.GL_FLOAT, 4)
        else:
            self.texture.initialize_rgba(self.size)
        self.depth_texture = None
        if depth:
            dt = Texture(linear_interpolation=False, clamp_to_edge=True)
            dt.initialize_depth(self.size, depth_compare_mode=False)
            self.depth_texture = dt
        try:
            self.fb = Framebuffer(name, ctx, color_texture=self.texture,
                                  depth=bool(depth), depth_texture=self.depth_texture)
            self.fb.framebuffer_id  # create now: raises OpenGLError if incomplete
        except Exception:
            self._delete_textures()
            raise
        self.in_use = False

    @property
    def id(self):
        return self.texture.id

    @property
    def framebuffer(self):
        return self.fb

    def _delete_textures(self):
        for t in (self.texture, self.depth_texture):
            try:
                if t is not None:
                    t.delete_texture()
            except Exception:
                pass
        self.texture = self.depth_texture = None

    def delete(self):
        fb, self.fb = getattr(self, "fb", None), None
        try:
            if fb is not None:
                fb.delete()   # also deletes its textures
        except Exception:
            pass
        self._delete_textures()

    def bind(self, r):
        self.fb.activate()
        r.set_viewport(0, 0, self.size[0], self.size[1])


class FinalTarget(object):
    """The framebuffer that was bound before we took over (screen / image capture)."""
    texture = None
    depth_texture = None
    id = None

    def __init__(self, fb):
        self.fb = fb
        x, y, w, h = fb.viewport
        self.size = (w, h)
        self.viewport = fb.viewport

    def bind(self, r):
        self.fb.activate()
        r.set_viewport(*self.viewport)


class TargetPool(object):
    """Pool of temporary float/8-bit RTs keyed by (w, h, float)."""

    MAX_FREE = 8

    def __init__(self, ctx):
        self.ctx = ctx
        self._free: Dict[Tuple[int, int, bool], List[RT]] = {}
        self._all: List[RT] = []

    def alloc(self, w, h, float_=True):
        key = (int(w), int(h), bool(float_))
        lst = self._free.get(key)
        if lst:
            rt = lst.pop()
        else:
            rt = RT(self.ctx, key[:2], float_=float_, name="chimenodes tmp")
            self._all.append(rt)
        rt.in_use = True
        return rt

    def release(self, rt):
        if rt is None or not isinstance(rt, RT) or not rt.in_use:
            return
        rt.in_use = False
        key = (rt.size[0], rt.size[1], rt.float)
        lst = self._free.setdefault(key, [])
        if len(lst) >= self.MAX_FREE:
            self._all.remove(rt)
            rt.delete()
        else:
            lst.append(rt)

    def reset(self):
        """Mark every RT free (after an aborted frame)."""
        self._free = {}
        for rt in self._all:
            rt.in_use = False
            self._free.setdefault((rt.size[0], rt.size[1], rt.float), []).append(rt)

    def purge_except(self, size):
        """Delete free RTs whose size differs from ``size`` (e.g. after a resize)."""
        for key in list(self._free):
            if (key[0], key[1]) != tuple(size):
                for rt in self._free.pop(key):
                    if rt in self._all:
                        self._all.remove(rt)
                    rt.delete()

    def delete(self):
        for rt in self._all:
            rt.delete()
        self._all = []
        self._free = {}


# --------------------------------------------------------------------------------------
# Shader programs
# --------------------------------------------------------------------------------------
class Program(object):
    def __init__(self, name, program_id):
        self.name = name
        self.id = program_id
        self._locs: Dict[str, int] = {}

    def loc(self, uniform):
        v = self._locs.get(uniform)
        if v is None:
            v = _gl().glGetUniformLocation(self.id, uniform.encode("utf-8"))
            self._locs[uniform] = v
        return v

    def set(self, name, value):
        """Set a uniform from a python value (bool/int -> int, float, tuple -> vecN)."""
        GL = _gl()
        loc = self.loc(name)
        if loc < 0:
            return
        if isinstance(value, bool):
            GL.glUniform1i(loc, int(value))
        elif isinstance(value, int):
            GL.glUniform1i(loc, value)
        elif isinstance(value, float):
            GL.glUniform1f(loc, value)
        else:
            vals = [float(x) for x in value]
            n = len(vals)
            if n == 1:
                GL.glUniform1f(loc, vals[0])
            elif n == 2:
                GL.glUniform2f(loc, *vals)
            elif n == 3:
                GL.glUniform3f(loc, *vals)
            elif n == 4:
                GL.glUniform4f(loc, *vals)
            elif n == 9:
                GL.glUniformMatrix3fv(loc, 1, False, vals)
            elif n == 16:
                GL.glUniformMatrix4fv(loc, 1, False, vals)
            else:
                raise ValueError("uniform %s: unsupported length %d" % (name, n))

    def delete(self):
        try:
            _gl().glDeleteProgram(self.id)
        except Exception:
            pass


_INCLUDE_RE = re.compile(r'^[ \t]*#include[ \t]+"([^"]+)"[ \t]*$', re.M)


def read_shader(fname, seen=None, depth=0):
    """Read a shader file from SHADER_DIR expanding #include once per program."""
    if seen is None:
        seen = set()
    path = os.path.join(SHADER_DIR, fname)
    with open(path, "r") as f:
        src = f.read()
    if depth > 6:
        raise GLUnsupported("shader include depth exceeded at %s" % fname)

    def repl(m):
        inc = m.group(1)
        if inc in seen:
            return ""
        seen.add(inc)
        return read_shader(inc, seen, depth + 1)
    return _INCLUDE_RE.sub(repl, src)


def _with_defines(src, defines):
    if not src.lstrip().startswith("#version"):
        src = "#version 330 core\n" + src
    if not defines:
        return src
    lines = src.split("\n")
    for i, ln in enumerate(lines):
        if ln.strip().startswith("#version"):
            extra = ["#define %s %s" % (k, v) if v is not None else "#define %s" % k
                     for k, v in defines]
            lines[i + 1:i + 1] = extra
            break
    return "\n".join(lines)


def compile_program(name, vert_src, frag_src, defines=None):
    GL = _gl()
    from OpenGL.GL import shaders
    vs = fs = None
    try:
        try:
            vs = shaders.compileShader(vert_src, GL.GL_VERTEX_SHADER)
            fs = shaders.compileShader(_with_defines(frag_src, defines), GL.GL_FRAGMENT_SHADER)
        except Exception as e:
            raise GLUnsupported("shader '%s' failed to compile: %s" % (name, e))
        pid = GL.glCreateProgram()
        GL.glAttachShader(pid, vs)
        GL.glAttachShader(pid, fs)
        for nm in _POSITION_NAMES:
            GL.glBindAttribLocation(pid, 0, nm)
        GL.glLinkProgram(pid)
        if not GL.glGetProgramiv(pid, GL.GL_LINK_STATUS):
            log = GL.glGetProgramInfoLog(pid)
            if isinstance(log, bytes):
                log = log.decode("utf-8", "replace")
            GL.glDeleteProgram(pid)
            raise GLUnsupported("shader '%s' failed to link: %s" % (name, log))
        GL.glDetachShader(pid, vs)
        GL.glDetachShader(pid, fs)
        return Program(name, pid)
    finally:
        for s in (vs, fs):
            if s is not None:
                try:
                    GL.glDeleteShader(s)
                except Exception:
                    pass


class ProgramCache(object):
    def __init__(self):
        self._progs: Dict[Any, Program] = {}
        self._vert: Optional[str] = None

    def vertex_source(self):
        if self._vert is None:
            try:
                self._vert = read_shader("fullscreen.vert")
            except IOError:
                self._vert = _FALLBACK_VERT
        return self._vert

    def get(self, name, defines=None):
        key = (name, tuple(sorted(defines.items())) if defines else ())
        p = self._progs.get(key)
        if p is None:
            fname = name if name.endswith((".frag", ".glsl")) else name + ".frag"
            if not os.path.exists(os.path.join(SHADER_DIR, fname)) and fname.endswith(".frag"):
                alt = name + ".glsl"   # complete shaders may carry a .glsl extension
                if os.path.exists(os.path.join(SHADER_DIR, alt)):
                    fname = alt
            frag = read_shader(fname)
            p = compile_program(name, self.vertex_source(), frag,
                                list(key[1]) if key[1] else None)
            self._progs[key] = p
        return p

    def delete(self):
        for p in self._progs.values():
            p.delete()
        self._progs = {}


# --------------------------------------------------------------------------------------
# Fullscreen triangle geometry (own VAO so ChimeraX's bindings are never touched)
# --------------------------------------------------------------------------------------
class FullscreenGeometry(object):
    def __init__(self):
        GL = _gl()
        import numpy
        prev = GL.glGetIntegerv(GL.GL_VERTEX_ARRAY_BINDING)
        prev_buf = GL.glGetIntegerv(GL.GL_ARRAY_BUFFER_BINDING)
        self.vao = GL.glGenVertexArrays(1)
        self.vbo = GL.glGenBuffers(1)
        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        verts = numpy.array([-1, -1, 3, -1, -1, 3], dtype=numpy.float32)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, verts.nbytes, verts, GL.GL_STATIC_DRAW)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, False, 0, None)
        GL.glBindVertexArray(int(prev))
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, int(prev_buf))

    def draw(self):
        GL = _gl()
        GL.glBindVertexArray(self.vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)

    def delete(self):
        GL = _gl()
        try:
            GL.glDeleteVertexArrays(1, [self.vao])
            GL.glDeleteBuffers(1, [self.vbo])
        except Exception:
            pass
        self.vao = self.vbo = None
