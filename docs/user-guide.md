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
| `chimenodes glow F` | Same as `chimenodes glow F` keyword: global bloom strength |
| `chimenodes glow ATOMSPEC strength S color C` | Make atoms emissive; `chimenodes glow clear [ATOMSPEC]` |
| `chimenodes export blender PATH` | Structure + JSON sidecar + `render_blender.py` |

## Options
Ranges are clamped: glow 0-5, bloomRadius 0-1 (fraction of image height), bloomThreshold 0-4,
bloomKnee 0-1, exposure -5..5 EV, ao/rim/dof/aperture/outline/vignette/grain 0-1, aoRadius 0.01-5.
`focus ATOMSPEC` sets the DOF focal distance from the current camera to those atoms.

## Panel
Open the Chimenodes tool (GUI only) for sliders, a preset menu and an enable checkbox.

## Sessions
Settings are saved with sessions (versioned); restoring on a machine without suitable GL
leaves rendering stock and logs a warning.

## Troubleshooting
- Nothing changes: run `chimenodes info`; check the GL version is 3.3+.
- Image differs between window and `save image`: all radii are relative to image height, so
  results should match; report if not.
