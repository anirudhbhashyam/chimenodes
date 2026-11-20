# chimenodes user guide

## Quick start
    open 1abc
    chimenodes preset mn_default
    chimenodes glow 1 bloomThreshold 0.8
    save image.png width 2000 supersample 3

`chimenodes info` logs all parameters, the GL renderer and the render size.
`chimenodes off` returns to bit-identical stock rendering and restores your previous lighting.

## Commands
| Command | Effect |
|---|---|
| `chimenodes on/off/toggle/reset/info` | Switch pipeline, reset parameters, diagnostics |
| `chimenodes [preset NAME] [options]` | Apply a preset, then explicit options on top |
| `chimenodes preset save/delete/list NAME` | Manage user presets (built-ins cannot be deleted) |
| `chimenodes glow F` | Global bloom strength (same as the `glow` keyword) |
| `chimenodes glow ATOMSPEC strength S color C` | Make atoms emissive; `chimenodes glow clear [ATOMSPEC]` |
| `chimenodes export blender PATH` | Structure + JSON sidecar + `render_blender.py` |

## Options
Ranges are clamped: glow 0-5, bloomRadius 0-1 (fraction of image height), bloomThreshold 0-4,
bloomKnee 0-1, glowLight 0-3 (0 = off), glowLightRadius 0-60 Angstrom (0 = auto, 6), exposure -5..5 EV, ao/rim/dof/aperture/outline/vignette/grain 0-1, aoRadius 0.01-5.
`focus ATOMSPEC` sets the DOF focal distance from the current camera to those atoms.

## Glow light
`glowLight F` (default 0.6 in the mn_default, neon and cinematic presets) makes glowing atoms
(`chimenodes glow ATOMSPEC ...`) act as point lights that illuminate and tint nearby surfaces;
`glowLightRadius R` sets the reach in Angstrom (0 = auto). It is a screen-space pass: it lights
only the nearest visible surface, and there are no shadows. With no glowing atoms it has no effect.

## Panel
Open the Chimenodes tool (GUI only) for sliders, a preset menu and an enable checkbox.

## Sessions
Settings are saved with sessions (versioned); restoring on a machine without suitable GL
leaves rendering stock and logs a warning.

## Troubleshooting
- Nothing changes: run `chimenodes info`; check the GL version is 3.3+.
- Image differs between window and `save image`: all radii are relative to image height, so
  results should match; report if not.

## Failure handling and known limitations

- If one effect pass raises an error, only that pass is disabled (a warning is logged) and the
  rest of the chain keeps running. `chimenodes reset` or re-enabling reloads passes. If the core
  framebuffer machinery itself fails, chimenodes uninstalls and ChimeraX renders normally.
- ChimeraX's own `graphics silhouettes true` captures colour only, so depth-based passes
  (dof, outline) see no depth while it is on. The MN look turns it off; use `chimenodes outline`.
- Stereo, 360 and VR cameras and OpenGL recording bypass chimenodes.
- Per-object glow re-renders the scene once, roughly doubling frame cost while glow is active.
- Transparent surfaces do not write depth, so depth of field and outline ignore them.

## Glow selection

`chimenodes glow ATOMSPEC strength S [color C]` marks only the atoms in the spec (e.g. `:OHT`, `/B`,
`#1:12@C1,C2`). Surfaces (including translucent ones) are drawn black in the emission pass, so they dim
glow behind them instead of adding colour. `chimenodes glow clear` removes all emission.

Limitations of the emission pass: only surface models are blackened. Pseudobonds, markers and volume
image styles keep their colours and will leak into the glow buffer if displayed.
