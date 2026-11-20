# chimenodes

A ChimeraX bundle that emulates the look of [MolecularNodes](https://github.com/BradyAJohnston/MolecularNodes)
(AO-in-albedo, satin shading, soft lighting, AgX tone mapping) plus optional glow
(bloom and per-object emission), depth of field, outline, FXAA, vignette and grain.
Cross-platform: macOS, Windows, Linux (OpenGL 3.3 core, fragment shaders only).

## Install (one line)

Requires [UCSF ChimeraX](https://www.cgl.ucsf.edu/chimerax/download.html) >= 1.8. You do **not** need
system Python, uv, pixi, git or a compiler: ChimeraX builds and installs the bundle with its own Python.

```sh
curl -fsSL https://raw.githubusercontent.com/<owner>/chimenodes/main/install.sh | sh
```

Options go after `sh -s --`, e.g. `... | sh -s -- --ref v0.1.0 --chimerax /path/to/ChimeraX`.
`--uninstall` removes it, `--build-only` writes a wheel to `./dist`, `--local DIR` installs from a
checkout, `--dry-run` shows what would happen. The script finds ChimeraX on macOS, Linux and Windows
(Git Bash/WSL) and stops with download instructions if it is missing (the ChimeraX license must be
accepted by you, so it is never downloaded automatically).

## Install
Development (editable) install, any platform:

    python scripts/dev_install.py            # or scripts/dev_install.sh / .bat

This finds ChimeraX (or use `--exe PATH` / `CHIMERAX_EXE`) and runs
`devel install . editable true`. Or from the ChimeraX command line: `devel install /path/to/chimenodes editable true`.

## Usage
    chimenodes preset neon              # apply a preset (turns rendering on)
    chimenodes glow 1.5 bloomRadius 0.4 # explicit keywords override the preset
    chimenodes glow /A:10-20 strength 3 color gold   # per-object emission
    chimenodes off | on | toggle | reset | info
    chimenodes export blender ~/out/prot.cif

Keywords: `glow bloomRadius bloomThreshold bloomKnee exposure tonemap(none|aces|filmic|agx)
ao aoRadius rim dof aperture focus outline vignette grain fxaa quality(draft|normal|high)`.
Values are clamped to valid ranges. `chimenodes preset save|delete|list NAME` manages presets.

## Presets
`mn_default` (MolecularNodes look), `neon` (strong glow), `cinematic` (DOF, vignette, grain),
`clean` (flat, outlined), `inspect` (neutral, for analysis).

## Blender export
`chimenodes export blender PATH` writes the structure, `PATH.chimenodes.json` (camera, colours,
representation, glow) and `render_blender.py`. Then:
`blender -b -P render_blender.py -- prot.cif out.png`.

## Limitations
- Requires OpenGL 3.3 core; on failure the bundle logs once and falls back to stock rendering.
- Blender export is approximate: MolecularNodes may recentre the structure and its API varies
  by release; colours/glow are advisory.
- Screen-space AO/DOF/outline are approximations of the Blender look, not a path tracer.

## Development
    python -m pytest tests/unit                      # pure Python, no ChimeraX
    ChimeraX --nogui --offscreen --exit --script tests/gl/run_gl.py   # GL invariants
    ChimeraX --nogui --offscreen --exit --script tests/bench/bench.py

See `docs/ARCHITECTURE.md` and `docs/user-guide.md`.
