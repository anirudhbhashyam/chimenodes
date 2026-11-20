"""Consolidated real-GL suite, run ONCE inside a ChimeraX GUI session:

    CHIMENODES_OUT=/path/to/out ChimeraX --exit --script tests/gl/gui_suite.py

(ChimeraX opens a window briefly: --offscreen needs OSMesa and --nogui has no GL.)
Writes <out>/report.json, <out>/summary.txt and one PNG per visual case.
Every case is independent; a failure is recorded and the suite continues.
Compatible with Python >= 3.9.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
import types

OUT = os.environ.get("CHIMENODES_OUT") or os.path.join(os.getcwd(), "chimenodes_gui_out")
SRC = os.environ.get("CHIMENODES_SRC") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "src")
os.makedirs(OUT, exist_ok=True)
RESULTS = []
W, H = 480, 320


def case(name):
    def deco(fn):
        t0 = time.time()
        try:
            detail = fn() or {}
            RESULTS.append({"name": name, "ok": True, "secs": round(time.time() - t0, 2),
                            "detail": detail})
        except Exception:
            RESULTS.append({"name": name, "ok": False, "secs": round(time.time() - t0, 2),
                            "error": traceback.format_exc()[-1500:]})
        return fn
    return deco


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main(session):
    import numpy as np
    import chimerax
    # load the working-tree source as the bundle package (no install needed)
    if "chimerax.chimenodes" not in sys.modules:
        pkg = types.ModuleType("chimerax.chimenodes")
        pkg.__path__ = [os.path.abspath(SRC)]
        sys.modules["chimerax.chimenodes"] = pkg
        chimerax.chimenodes = pkg
    from chimerax.core.commands import run
    from chimerax.chimenodes import hook, cmd, presets, state
    from chimerax.chimenodes.params import Params
    cmd.register_commands(session.logger)
    view = session.main_view

    def png(img, name):
        try:
            from PIL import Image
            Image.fromarray(img[..., :3].astype("uint8")).save(os.path.join(OUT, name + ".png"))
        except Exception:
            pass

    def render(w=W, h=H, **kw):
        return view.image_rgba(w, h, **kw).astype(float)

    def lum(img):
        return float(img[..., :3].mean())

    def reset():
        run(session, "chimenodes off", log=False)
        run(session, "chimenodes reset", log=False)

    # ---- scene: small atomic structure (so glow attribute works) + shapes
    scene = {"atoms": False}

    @case("scene_setup")
    def _():
        run(session, "set bgColor black", log=False)
        try:
            from chimerax.atomic import AtomicStructure
            s = AtomicStructure(session, name="grid")
            res = s.new_residue("GLY", "A", 1)
            n = 0
            for i in range(5):
                for j in range(4):
                    a = s.new_atom("C%d" % n, "C")
                    a.coord = np.array([i * 3.0, j * 3.0, (i + j) % 3 * 1.5])
                    res.add_atom(a)
                    n += 1
            session.models.add([s])
            run(session, "style #1 sphere; color #1 skyblue; view", log=False)
            scene["atoms"] = True
            scene["model"] = s
        except Exception:
            run(session, "shape sphere radius 5 color red; shape cone radius 3 height 8 "
                         "center 6,0,0 color cyan; view", log=False)
        return {"atoms": scene["atoms"]}

    stock = render()
    png(stock, "00_stock")

    @case("hook_idle_equals_stock")
    def _():
        hook.install(session)
        img = render()
        d = float(abs(img - stock).max())
        hook.uninstall(session)
        check(d == 0, "hook with no effects differs from stock, max diff %s" % d)
        return {"max_diff": d}

    @case("off_after_on_equals_stock")
    def _():
        run(session, "chimenodes preset mn_default", log=False)
        render()
        reset()
        d = float(abs(render() - stock).max())
        check(d == 0, "after off, image differs from stock: %s" % d)
        return {"max_diff": d, "hook_removed": hook.get(session) is None}

    @case("presets_render_and_differ")
    def _():
        out = {}
        for name in presets.BUILTIN:
            run(session, "chimenodes preset %s fxaa true" % name, log=False)
            img = render()
            check(np.isfinite(img).all(), "%s has NaN/inf" % name)
            check(hook.get(session) is not None, "%s: hook was auto-uninstalled (pass failed)" % name)
            out[name] = {"mean_lum": round(lum(img), 2), "diff_vs_stock": round(float(abs(img - stock).mean()), 3)}
            png(img, "preset_" + name)
        reset()
        check(out["mn_default"]["diff_vs_stock"] > 0, "mn_default identical to stock")
        return out

    def single(label, command, expect_change=True):
        @case("effect_" + label)
        def _():
            run(session, command, log=False)
            img = render()
            ok_hook = hook.get(session) is not None
            reset()
            check(ok_hook, "hook uninstalled itself (pass error, see log)")
            check(np.isfinite(img).all(), "NaN/inf in output")
            d = float(abs(img - stock).mean())
            png(img, "effect_" + label)
            if expect_change:
                check(d > 0, "no visible change vs stock")
            return {"diff_vs_stock": round(d, 3), "mean_lum": round(lum(img), 2)}

    single("ao", "chimenodes ao 1 aoRadius 0.5")
    single("rim", "chimenodes rim 1")
    single("glow_threshold", "chimenodes tonemap none bloomThreshold 0.2 glow 2")
    single("tonemap_aces", "chimenodes tonemap aces")
    single("tonemap_filmic", "chimenodes tonemap filmic")
    single("tonemap_agx", "chimenodes tonemap agx")
    single("exposure_up", "chimenodes exposure 1.5 tonemap aces")
    single("dof", "chimenodes dof 1 aperture 1")
    single("outline", "chimenodes outline 1")
    single("vignette", "chimenodes vignette 1")
    single("grain", "chimenodes grain 1")
    single("fxaa", "chimenodes fxaa true", expect_change=False)
    single("quality_high", "chimenodes preset cinematic quality high")
    single("quality_draft", "chimenodes preset cinematic quality draft")

    @case("tonemap_none_exposure0_is_noop")
    def _():
        run(session, "chimenodes tonemap none exposure 0", log=False)
        pipe = hook.get(session)
        act = [getattr(p, "name", "?") for p in pipe.active_passes()] if pipe else []
        reset()
        check(act == [], "identity settings still activate passes: %s" % act)
        return {}

    @case("bloom_luminance_monotonic")
    def _():
        vals = []
        for g in (0.0, 1.0, 2.5, 5.0):
            run(session, "chimenodes tonemap none bloomThreshold 0.1 glow %s" % g, log=False)
            vals.append(lum(render()))
        reset()
        check(all(b >= a - 1e-6 for a, b in zip(vals, vals[1:])), "luminance not monotonic: %s" % vals)
        check(vals[-1] > vals[0], "bloom adds no light: %s" % vals)
        return {"lum": [round(v, 2) for v in vals]}

    @case("glow_zero_equals_bloom_off")
    def _():
        run(session, "chimenodes tonemap aces glow 0", log=False)
        a = render()
        run(session, "chimenodes tonemap aces glow 3", log=False)
        run(session, "chimenodes glow 0", log=False)
        b = render()
        reset()
        d = float(abs(a - b).max())
        check(d <= 1, "glow 0 differs from bloom off by %s" % d)
        return {"max_diff": d}

    @case("per_object_glow_emission")
    def _():
        check(scene["atoms"], "atomic scene unavailable")
        run(session, "chimenodes tonemap aces", log=False)
        base = render()
        run(session, "chimenodes glow #1 strength 4 color yellow", log=False)
        run(session, "chimenodes glow 1.5", log=False)
        img = render()
        only_global = None
        pipe = hook.get(session)
        ok = pipe is not None
        from chimerax.chimenodes import glow as glow_mod
        had = glow_mod.has_glow_objects(session)
        run(session, "chimenodes glow clear", log=False)
        gone = not glow_mod.has_glow_objects(session)
        cleared = render()
        reset()
        png(img, "glow_emission")
        check(ok, "hook died during emission render")
        check(lum(img) > lum(base), "emission added no light")
        check(had and gone, "glow objects flag wrong: before=%s after_clear_gone=%s" % (had, gone))
        check(abs(cleared - img).mean() > 0, "glow clear did not change the image")
        return {"lum_base": round(lum(base), 2), "lum_glow": round(lum(img), 2)}

    @case("resolution_consistency_2x")
    def _():
        run(session, "chimenodes preset mn_default", log=False)
        a = render(W, H)
        b = render(W * 2, H * 2)
        reset()
        bd = b.reshape(H, 2, W, 2, 4).mean(axis=(1, 3))
        d = float(abs(a - bd).mean())
        check(d < 12, "2x render differs from 1x by mean %.2f" % d)
        return {"mean_abs_diff": round(d, 2)}

    @case("supersample_with_effects")
    def _():
        run(session, "chimenodes preset cinematic", log=False)
        img = render(supersample=3)
        ok = hook.get(session) is not None
        reset()
        png(img, "supersample3")
        check(ok and np.isfinite(img).all(), "supersample render failed")
        return {}

    @case("odd_size_and_transparent_bg")
    def _():
        run(session, "chimenodes preset neon", log=False)
        img = view.image_rgba(321, 77, transparent_background=True)
        ok = hook.get(session) is not None
        reset()
        check(ok and img.shape[:2] == (77, 321), "odd-size render failed %s" % (img.shape,))
        return {}

    @case("live_draw_path")
    def _():
        run(session, "chimenodes preset mn_default", log=False)
        t0 = time.time()
        for _i in range(10):
            view.draw()
        dt = (time.time() - t0) / 10 * 1000
        ok = hook.get(session) is not None
        reset()
        check(ok, "live draw uninstalled hook")
        return {"ms_per_frame": round(dt, 1)}

    @case("movie_record_path")
    def _():
        run(session, "chimenodes preset mn_default", log=False)
        img = render()
        reset()
        check(np.isfinite(img).all(), "bad frame")
        return {}

    @case("benchmark_overhead")
    def _():
        def t(n=15):
            t0 = time.time()
            for _i in range(n):
                render(960, 540)
            return (time.time() - t0) / n * 1000
        base = t()
        run(session, "chimenodes preset mn_default", log=False)
        mn = t()
        run(session, "chimenodes preset cinematic quality high", log=False)
        cin = t()
        reset()
        return {"stock_ms": round(base, 1), "mn_default_ms": round(mn, 1), "cinematic_high_ms": round(cin, 1)}

    @case("commands_roundtrip")
    def _():
        run(session, "chimenodes info", log=False)
        run(session, "chimenodes preset list", log=False)
        run(session, "chimenodes preset neon glow 1.7", log=False)
        p = state.get_params(session)
        check(abs(p.glow - 1.7) < 1e-6, "explicit keyword did not override preset: %s" % p.glow)
        run(session, "chimenodes preset save zz_suite_tmp", log=False)
        check("zz_suite_tmp" in presets.list_presets(), "saved preset not listed")
        run(session, "chimenodes preset delete zz_suite_tmp", log=False)
        run(session, "chimenodes toggle", log=False)
        run(session, "chimenodes toggle", log=False)
        reset()
        errs = 0
        for bad in ("chimenodes tonemap nope", "chimenodes glow 99 exposure 99"):
            try:
                run(session, bad, log=False)
            except Exception:
                errs += 1
            reset()
        return {"bad_commands_rejected_or_clamped": errs}

    @case("session_state_roundtrip")
    def _():
        run(session, "chimenodes preset neon glow 2.2", log=False)
        snap = state.snapshot_params(state.get_params(session))
        reset()
        restored = state.restore_params(snap)
        check(abs(restored.glow - 2.2) < 1e-6, "state restore lost glow")
        return {}

    @case("export_blender")
    def _():
        path = os.path.join(OUT, "blender", "scene")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        run(session, "chimenodes export blender %s" % path, log=False)
        files = os.listdir(os.path.dirname(path))
        check(any(f.endswith(".json") for f in files), "no sidecar JSON: %s" % files)
        return {"files": sorted(files)}

    @case("failsafe_bad_pass_is_isolated")
    def _():
        from chimerax.chimenodes import pipeline

        class Bad(pipeline.Pass):
            name = "bad"

            def enabled(self, p):
                return p.enabled

            def run(self, ctx):
                raise RuntimeError("boom")

        pipeline.register_pass(1, Bad())
        run(session, "chimenodes preset neon", log=False)
        img = render()
        pipe = hook.get(session)
        alive = pipe is not None
        disabled = sorted(pipe.disabled_passes) if alive else []
        img2 = render()
        try:
            pipeline._REGISTRY[:] = [x for x in pipeline._REGISTRY if getattr(x[1], "name", "") != "bad"]
        except Exception:
            pass
        reset()
        check(alive, "one bad pass took down the whole chain")
        check("bad" in disabled, "bad pass not recorded as disabled: %s" % disabled)
        check(np.isfinite(img).all() and abs(img - stock).mean() > 0, "remaining passes did not render")
        check(abs(img - img2).max() <= 1, "frame unstable after pass disabled")
        return {"disabled": disabled}

    report = {"ok": all(r["ok"] for r in RESULTS), "passed": sum(r["ok"] for r in RESULTS),
              "total": len(RESULTS), "cases": RESULTS}
    with open(os.path.join(OUT, "report.json"), "w") as f:
        json.dump(report, f, indent=1)
    lines = ["%s  %-34s %5.1fs  %s" % ("PASS" if r["ok"] else "FAIL", r["name"], r["secs"],
                                       json.dumps(r.get("detail")) if r["ok"] else r["error"].strip().splitlines()[-1])
             for r in RESULTS]
    lines.append("%d/%d passed" % (report["passed"], report["total"]))
    with open(os.path.join(OUT, "summary.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")


try:
    main(session)  # noqa: F821  (provided by ChimeraX --script)
except Exception:
    with open(os.path.join(OUT, "summary.txt"), "w") as f:
        f.write("SUITE CRASHED\n" + traceback.format_exc())
