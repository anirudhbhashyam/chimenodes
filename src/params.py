"""Shared parameter model for chimenodes. Pure Python (no GL, no ChimeraX imports)."""
from __future__ import annotations

from dataclasses import dataclass, field, fields, asdict
from typing import Any, Dict

TONEMAPS = ("none", "aces", "filmic", "agx")
QUALITIES = ("draft", "normal", "high")

# name -> (min, max)
RANGES = {
    "glow": (0.0, 5.0),
    "bloom_radius": (0.0, 1.0),
    "bloom_threshold": (0.0, 4.0),
    "bloom_knee": (0.0, 1.0),
    "exposure": (-5.0, 5.0),
    "ao": (0.0, 1.0),
    "ao_radius": (0.01, 5.0),
    "dof": (0.0, 1.0),
    "aperture": (0.0, 1.0),
    "outline": (0.0, 1.0),
    "rim": (0.0, 1.0),
    "vignette": (0.0, 1.0),
    "grain": (0.0, 1.0),
}


@dataclass
class Params:
    enabled: bool = False
    # Look / shading (applied through ChimeraX lighting + our composite pass)
    ao: float = 0.0            # strength of AO multiplied into albedo
    ao_radius: float = 0.5     # relative to scene size
    rim: float = 0.0           # fresnel rim strength
    # Glow
    glow: float = 0.0          # intensity of bloom added to the image
    bloom_radius: float = 0.3  # fraction of image height
    bloom_threshold: float = 1.0
    bloom_knee: float = 0.5
    # Tone / film
    tonemap: str = "none"
    exposure: float = 0.0      # EV
    vignette: float = 0.0
    grain: float = 0.0
    # Lens
    dof: float = 0.0
    aperture: float = 0.0
    focus_depth: float = -1.0  # <0 means auto (scene centre)
    outline: float = 0.0
    fxaa: bool = False
    quality: str = "normal"
    preset: str = ""

    def clamp(self) -> "Params":
        for k, (lo, hi) in RANGES.items():
            setattr(self, k, min(hi, max(lo, float(getattr(self, k)))))
        if self.tonemap not in TONEMAPS:
            raise ValueError("tonemap must be one of %s" % (TONEMAPS,))
        if self.quality not in QUALITIES:
            raise ValueError("quality must be one of %s" % (QUALITIES,))
        return self

    def update(self, **kw: Any) -> "Params":
        names = {f.name for f in fields(self)}
        for k, v in kw.items():
            if k not in names:
                raise KeyError(k)
            setattr(self, k, v)
        return self.clamp()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Params":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names}).clamp()

    def any_post_effect(self) -> bool:
        return self.enabled and (
            self.glow > 0 or self.tonemap != "none" or self.exposure != 0
            or self.vignette > 0 or self.grain > 0 or self.dof > 0
            or self.outline > 0 or self.fxaa or self.ao > 0 or self.rim > 0)
