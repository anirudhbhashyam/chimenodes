"""Built-in and user presets for chimenodes. Pure Python (no ChimeraX imports)."""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

try:
    from .params import Params
except ImportError:  # plain-python usage / tests importing the module directly
    from params import Params  # type: ignore

# Preset values are Params kwargs. 'enabled' is deliberately omitted: applying a
# preset never turns the effect on or off by itself (cmd.py decides that).
BUILTIN: Dict[str, Dict[str, Any]] = {
    # MolecularNodes look: AO in albedo, satin shading, AgX, no bloom/DOF.
    "mn_default": dict(ao=0.8, ao_radius=0.5, rim=0.25, tonemap="agx", exposure=0.0,
                       glow=0.0, dof=0.0, outline=0.0, vignette=0.0, grain=0.0,
                       fxaa=True),
    "neon": dict(ao=0.5, ao_radius=0.5, rim=0.6, tonemap="filmic", exposure=0.3,
                 glow=1.5, bloom_radius=0.35, bloom_threshold=0.7, bloom_knee=0.5,
                 vignette=0.25, fxaa=True),
    "cinematic": dict(ao=0.8, ao_radius=0.6, rim=0.35, tonemap="agx", exposure=0.0,
                      glow=0.6, bloom_radius=0.3, bloom_threshold=1.0, dof=0.45,
                      aperture=0.4, vignette=0.4, grain=0.12, fxaa=True),
    "clean": dict(ao=0.6, ao_radius=0.4, rim=0.1, tonemap="none", exposure=0.0,
                  glow=0.0, dof=0.0, outline=0.0, vignette=0.0, grain=0.0,
                  fxaa=True),
    "inspect": dict(ao=0.3, ao_radius=0.3, rim=0.0, tonemap="none", exposure=0.0,
                    glow=0.0, dof=0.0, outline=0.6, vignette=0.0, grain=0.0,
                    fxaa=True),
}

# Fields that are not stored in user presets.
_EXCLUDE = ("enabled", "preset", "focus_depth")
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,63}$")


def default_user_dir() -> str:
    """User preset directory: ChimeraX user config dir if available, else ~/.chimenodes."""
    base = None
    try:  # pragma: no cover - only inside ChimeraX
        from chimerax import app_dirs
        base = app_dirs.user_config_dir
    except Exception:
        pass
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".chimenodes")
    return os.path.join(base, "chimenodes_presets")


def _dir(directory: Optional[str]) -> str:
    return directory if directory else default_user_dir()


RESERVED = ("save", "delete", "list")   # subcommands of `chimenodes preset`


def _check_name(name: str) -> str:
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ValueError("invalid preset name %r (use letters, digits, _ and -)" % (name,))
    if name.lower() in RESERVED:
        raise ValueError("preset name %r is reserved" % (name,))
    return name


def _path(name: str, directory: Optional[str]) -> str:
    return os.path.join(_dir(directory), _check_name(name) + ".json")


def list_presets(directory: Optional[str] = None) -> List[str]:
    """Names of all presets: builtin first, then user (sorted)."""
    names = list(BUILTIN)
    d = _dir(directory)
    try:
        user = sorted(f[:-5] for f in os.listdir(d)
                      if f.endswith(".json") and _NAME_RE.match(f[:-5]))
    except OSError:
        user = []
    return names + [n for n in user if n not in BUILTIN]


def is_builtin(name: str) -> bool:
    return name in BUILTIN


def get_preset(name: str, directory: Optional[str] = None) -> Dict[str, Any]:
    """Return Params kwargs for a preset (user presets override nothing builtin).

    Raises KeyError for unknown names."""
    if name in BUILTIN:
        return dict(BUILTIN[name])
    try:
        p = _path(name, directory)
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        raise KeyError("unknown preset %r" % (name,)) from e
    # sanitise through Params so unknown keys / bad values cannot leak out
    valid = Params.from_dict(data).to_dict()
    return {k: valid[k] for k in data if k in valid and k not in _EXCLUDE}


def save_preset(name: str, params: Any, directory: Optional[str] = None) -> str:
    """Save Params (or dict) as a user preset; returns the file path."""
    _check_name(name)
    if name in BUILTIN:
        raise ValueError("cannot overwrite builtin preset %r" % (name,))
    d = params.to_dict() if hasattr(params, "to_dict") else dict(params)
    d = Params.from_dict(d).to_dict()
    d = {k: v for k, v in d.items() if k not in _EXCLUDE}
    p = _path(name, directory)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=2, sort_keys=True)
    os.replace(tmp, p)
    return p


def delete_preset(name: str, directory: Optional[str] = None) -> None:
    """Delete a user preset. Raises ValueError for builtin, KeyError if missing."""
    if name in BUILTIN:
        raise ValueError("cannot delete builtin preset %r" % (name,))
    p = _path(name, directory)
    try:
        os.remove(p)
    except FileNotFoundError as e:
        raise KeyError("unknown preset %r" % (name,)) from e
