"""Pure-numpy clustering of glowing-atom emitters into a small set of point lights."""
from __future__ import annotations

import numpy as np

WEIGHT_CAP = 4.0


def _voxel_ids(pos, lo, cell):
    ijk = np.floor((pos - lo) / cell).astype(np.int64)
    dims = ijk.max(axis=0) + 1
    key = (ijk[:, 0] * dims[1] + ijk[:, 1]) * dims[2] + ijk[:, 2]
    return np.unique(key, return_inverse=True)[1].ravel()


def cluster_lights(pos, col, max_lights, cap=WEIGHT_CAP):
    """Reduce emitters to <= max_lights point lights.

    pos: (N,3) positions. col: (N,3) emitted radiance per emitter = hue * strength
    (a lone strength-1 atom has colour magnitude (max channel) 1).
    Rule: voxel-grid clustering; cell size is binary-searched over the bounding box so the
    number of occupied cells is the largest that is <= max_lights. Cluster position = centroid
    weighted by strength; hue = strength-weighted mean hue; intensity = max(strongest member,
    sqrt(total strength)) so big clusters grow sub-linearly; singletons keep their own
    strength; every light's intensity is capped at `cap` (colour max channel <= cap).
    Returns float32 (M,3), (M,3), deterministic.
    """
    pos = np.asarray(pos, np.float32).reshape(-1, 3)
    col = np.asarray(col, np.float32).reshape(-1, 3)
    n = len(pos)
    if n == 0 or max_lights <= 0:
        return np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32)
    w = col.max(axis=1)
    ok = w > 1e-6
    pos, col, w = pos[ok], col[ok], w[ok]
    n = len(pos)
    if n == 0:
        return np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32)
    p64 = pos.astype(np.float64)
    if n <= max_lights:
        ids, m = np.arange(n), n
    else:
        lo = p64.min(axis=0)
        ext = np.maximum(p64.max(axis=0) - lo, 1e-6)
        diag = float(np.linalg.norm(ext))
        hi_c = diag * 1.001            # one cell
        lo_c = diag / (4.0 * max_lights ** (1 / 3.0) * max(1.0, n ** (1 / 3.0)))
        best = None
        ids_hi = _voxel_ids(p64, lo, hi_c)
        best = (ids_hi, int(ids_hi.max()) + 1)
        for _ in range(12):            # bisect (geometric) on cell size
            mid = (lo_c * hi_c) ** 0.5
            ids = _voxel_ids(p64, lo, mid)
            m = int(ids.max()) + 1
            if m <= max_lights:
                hi_c = mid
                if m > best[1] or best[1] > max_lights:
                    best = (ids, m)
                elif m >= best[1]:
                    best = (ids, m)
            else:
                lo_c = mid
        ids, m = best
        if m > max_lights:             # safety net: keep strongest
            keep = np.argsort(-w, kind="stable")[:max_lights]
            ids, m = np.arange(len(keep)), len(keep)
            pos, col, w = pos[keep], col[keep], w[keep]
            p64 = pos.astype(np.float64)
    ws = np.bincount(ids, w, m)
    cnt = np.bincount(ids, minlength=m)
    cen = np.stack([np.bincount(ids, w * p64[:, k], m) for k in range(3)], 1) / ws[:, None]
    hue = col / w[:, None]
    hs = np.stack([np.bincount(ids, w * hue[:, k], m) for k in range(3)], 1) / ws[:, None]
    hs /= np.maximum(hs.max(axis=1, keepdims=True), 1e-6)
    wmax = np.zeros(m)
    np.maximum.at(wmax, ids, w)
    inten = np.where(cnt == 1, wmax, np.maximum(wmax, np.sqrt(ws)))
    inten = np.minimum(inten, cap)
    return cen.astype(np.float32), (hs * inten[:, None]).astype(np.float32)
