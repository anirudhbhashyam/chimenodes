# chimenodes architecture and contract

Goal: a ChimeraX bundle that emulates the MolecularNodes look (AO-in-albedo, satin
shading, soft lighting, AgX tone mapping) plus optional glow (bloom, emission), DOF,
outline, FXAA, vignette, grain. Cross-platform (macOS/Windows/Linux, GL 3.3 core, GLSL
`#version 330 core`, fragment shaders only, no compute, no macOS-only code).

## Compatibility rules (all code)
- Python: ChimeraX 1.8-1.11 ships Python 3.11. Keep syntax valid for >=3.9: start every
  module with `from __future__ import annotations`; no `match`, no `X | Y` at runtime,
  no `tomllib`, no 3.10+ only stdlib.
- ChimeraX/GL imports (`chimerax.*`, `OpenGL`) only inside functions or guarded
  `try/except ImportError` so `src/params.py`, `presets.py`, tests/unit run on plain CPython.
- No platform checks except to disable unsupported features. Use `r.render_size()` and
  the current framebuffer size, never window size (HiDPI, supersampled `save image`).
- Blur radii and noise scale are relative to image height (resolution independent).
- Whole chain fails safe: any exception -> log once, uninstall hook, stock rendering.
- Off (`enabled False` or no active effects) must be pixel identical to stock.

## Modules (file ownership; do not edit another owner's files)
| Owner | Files |
|---|---|
| A: core hook | `src/__init__.py`, `src/hook.py`, `src/fbo.py`, `src/pipeline.py` |
| B: MN shading | `src/presets.py`, `src/look.py`, `src/shaders/composite.frag`, `src/shaders/tonemap.glsl`, `src/shaders/fullscreen.vert` |
| C: glow/lens | `src/glow.py`, `src/lens.py`, `src/shaders/{bright,down,up,dof,fxaa,outline,ssao,film}.frag` |
| D: UX/tests/infra | `src/cmd.py`, `src/state.py`, `src/tool.py`, `src/blender_export.py`, `tests/**`, `docs/**` (except this file), `.github/**`, `scripts/**`, `README.md`, `pyproject.toml` |
| shared (frozen, lead only) | `src/params.py`, `bundle_info.xml`, `docs/ARCHITECTURE.md` |

## Interfaces
`params.Params` is the single source of truth (see file).

**hook.py (A)**
- `install(session) -> Pipeline`, `uninstall(session)`, `get(session) -> Pipeline | None`.
- Wraps `View._draw_scene` (idempotent, version guarded, restores on uninstall).
  Pattern to follow: `Silhouette`/`Offscreen` in `chimerax/graphics/opengl.py`.

**pipeline.py (A)** - `class Pipeline`
- `params: Params`; `set_params(params)`; `begin(view, r)` (push HDR FBO: RGBA16F color
  + depth texture, size = `r.render_size()`), `end(view, r)` (run passes, write to the
  previously bound framebuffer). Pass list is ordered; each pass is a `Pass`:
```python
class Pass:                       # defined in pipeline.py
    name: str
    def enabled(self, p: Params) -> bool: ...
    def run(self, ctx: "PassContext") -> None: ...   # reads ctx.color/ctx.depth, writes ctx.target
```
- `PassContext` gives: `r` (Render), `params`, `size`, `color`, `depth` (textures),
  `emission` (texture or None), `near`, `far`, `scene_radius`, `alloc(w,h,float=True)`
  / `release(tex_fb)` temp RT pool, `draw_fullscreen(program, textures: dict, uniforms: dict)`,
  `program(name)` compiles `src/shaders/<name>.frag` with `fullscreen.vert` (cached).
- Order: `ao/look composite (B) -> emission add -> bloom (C) -> dof (C) -> outline (C)
  -> exposure+tonemap (B) -> film vignette/grain (C) -> fxaa (C)`.
- Registration: `pipeline.register_pass(order: int, pass_obj)`; B and C expose
  `make_passes() -> list[(order, Pass)]` which A's `Pipeline.__init__` collects
  (import guarded so a missing module just skips those passes).

**look.py (B)**: `apply_look(session, params)` / `restore_look(session)` sets ChimeraX
lighting/material (multishadow AO, satin material, key/fill/rim) and remembers prior
settings; `make_passes()`.
**presets.py (B)**: `BUILTIN: dict[str, dict]`, `get_preset(name) -> Params-kwargs`,
user presets as JSON in `chimerax.app_dirs.user_config_dir` (path injected, testable).
**glow.py (C)**: bloom (dual-Kawase, Karis average, soft knee), `glow` atom/residue/model
attribute + emission pass; API `set_glow(session, objects, strength, color=None)`,
`clear_glow(session, objects)`; `make_passes()`.
**lens.py (C)**: dof, outline, ssao, fxaa, film; `make_passes()`.
**cmd.py (D)**: `register_commands(logger)`; `chimenodes ...` per README spec;
`glow` helper command for per-object emission; explicit keywords override preset.
**state.py (D)**: session snapshot/restore of Params (versioned, degrades gracefully).
**blender_export.py (D)**: `chimenodes export blender PATH` writes mmCIF/PDB + JSON sidecar
(camera, colors, glow) and a `render_blender.py` helper script for MolecularNodes.

## Commands
```
chimenodes on|off|toggle|reset|info
chimenodes [preset NAME] [glow F] [bloomRadius R] [bloomThreshold T] [bloomKnee K]
           [exposure E] [tonemap none|aces|filmic|agx] [ao F] [aoRadius R] [rim F]
           [dof F] [aperture A] [focus ATOMSPEC] [outline F] [vignette F] [grain F]
           [fxaa true|false] [quality draft|normal|high]
chimenodes preset save|delete|list NAME
chimenodes glow ATOMSPEC [strength S] [color C]   # per-object emission
chimenodes export blender PATH
```
Presets: `mn_default`, `neon`, `cinematic`, `clean`, `inspect`.

## Milestones
M0 hook + passthrough tint; M1 MN shading stack + tonemap; M2 bloom + emission;
M3 DOF/SSAO/outline/FXAA/film, accumulation stills, Qt panel, tests; M4 blender export, CI, docs.
