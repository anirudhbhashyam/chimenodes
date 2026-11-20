"""Frame-time benchmark. Run:
    ChimeraX --nogui --offscreen --exit --script tests/bench/bench.py
Prints ms/frame for stock vs presets at a few sizes. Exits quietly without GL.
"""
import time


def main(session):
    from chimerax.core.commands import run
    run(session, "close; shape sphere radius 5; view")
    r = session.main_view.render
    try:
        r.make_current()
    except Exception as e:
        print("no GL: %s" % e)
        return
    for label, cmd in (("stock", "chimenodes off"), ("mn_default", "chimenodes preset mn_default"),
                       ("neon", "chimenodes preset neon"), ("cinematic", "chimenodes preset cinematic")):
        try:
            run(session, cmd, log=False)
        except Exception as e:
            print("%-12s skipped (%s)" % (label, e))
            continue
        for size in (512, 1024, 2048):
            session.main_view.image(size, size)  # warm up
            n = 10
            t = time.perf_counter()
            for _ in range(n):
                session.main_view.image(size, size)
            print("%-12s %4dpx %.1f ms" % (label, size, (time.perf_counter() - t) / n * 1000))
    run(session, "chimenodes off", log=False)


if "session" in globals():
    main(session)  # noqa: F821
