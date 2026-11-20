"""Optional Qt panel for chimenodes. Safe to import without a GUI."""
from __future__ import annotations

from .params import Params, RANGES, TONEMAPS, QUALITIES

SLIDERS = [("glow", "Glow"), ("bloom_radius", "Bloom radius"), ("bloom_threshold", "Bloom threshold"),
           ("exposure", "Exposure"), ("ao", "AO"), ("rim", "Rim"), ("dof", "DOF"),
           ("outline", "Outline"), ("vignette", "Vignette"), ("grain", "Grain")]
STEPS = 1000


def slider_to_value(name: str, pos: int) -> float:
    lo, hi = RANGES[name]
    return lo + (hi - lo) * max(0, min(STEPS, pos)) / STEPS


def value_to_slider(name: str, value: float) -> int:
    lo, hi = RANGES[name]
    return int(round((float(value) - lo) / (hi - lo) * STEPS))


def show_tool(session):
    """Open (or raise) the panel. No-op with a log message in nogui mode."""
    if not session.ui.is_gui:
        session.logger.info("chimenodes: the panel needs the ChimeraX GUI")
        return None
    try:
        return _make_tool(session)
    except Exception as e:
        session.logger.warning("chimenodes: panel unavailable (%s)" % e)
        return None


def _make_tool(session):
    from chimerax.ui import MainToolWindow
    from chimerax.core.tools import ToolInstance
    from Qt.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QSlider, QComboBox,
                              QCheckBox, QWidget)
    from Qt.QtCore import Qt
    from . import state

    existing = getattr(session, "_chimenodes_tool", None)
    if existing is not None and not existing.tool_window.__dict__.get("_destroyed", False):
        try:
            existing.tool_window.shown = True
            return existing
        except Exception:
            pass

    class ChimenodesTool(ToolInstance):
        SESSION_ENDURING = False
        SESSION_SAVE = False

        def __init__(self, session, name="Chimenodes"):
            super().__init__(session, name)
            self.tool_window = MainToolWindow(self)
            parent = self.tool_window.ui_area
            lay = QVBoxLayout(parent)
            self.enable = QCheckBox("Enable")
            lay.addWidget(self.enable)
            self.preset = QComboBox()
            try:
                from . import presets
                self.preset.addItems(sorted(presets.BUILTIN))
            except Exception:
                pass
            lay.addWidget(self.preset)
            self.tonemap = QComboBox()
            self.tonemap.addItems(TONEMAPS)
            lay.addWidget(self.tonemap)
            self.sliders = {}
            for key, label in SLIDERS:
                row = QHBoxLayout()
                row.addWidget(QLabel(label))
                s = QSlider(Qt.Horizontal)
                s.setRange(0, STEPS)
                row.addWidget(s)
                lay.addLayout(row)
                self.sliders[key] = s
                s.valueChanged.connect(lambda v, k=key: self._changed(k, v))
            self.fxaa = QCheckBox("FXAA")
            lay.addWidget(self.fxaa)
            self._busy = False
            self.enable.toggled.connect(lambda b: self._set(enabled=bool(b)))
            self.tonemap.currentTextChanged.connect(lambda t: self._set(tonemap=t))
            self.fxaa.toggled.connect(lambda b: self._set(fxaa=bool(b)))
            self.preset.activated.connect(lambda i: self._preset(self.preset.itemText(i)))
            self.refresh()
            self.tool_window.manage("side")

        def _set(self, **kw):
            if self._busy:
                return
            p = Params.from_dict(state.get_params(self.session).to_dict()).update(**kw)
            state.apply_params(self.session, p)

        def _changed(self, key, pos):
            self._set(**{key: slider_to_value(key, pos)})

        def _preset(self, name):
            from .cmd import merge_params, _get_preset_kwargs
            p = merge_params(state.get_params(self.session), _get_preset_kwargs(name), {}, name)
            p.enabled = True
            state.apply_params(self.session, p)
            self.refresh()

        def refresh(self):
            p = state.get_params(self.session)
            self._busy = True
            try:
                self.enable.setChecked(p.enabled)
                self.fxaa.setChecked(p.fxaa)
                self.tonemap.setCurrentText(p.tonemap)
                for k, s in self.sliders.items():
                    s.setValue(value_to_slider(k, getattr(p, k)))
            finally:
                self._busy = False

    tool = ChimenodesTool(session)
    session._chimenodes_tool = tool
    return tool
