"""Run the GL invariants in the current ChimeraX session."""
import builtins
from contextlib import redirect_stderr, redirect_stdout
import os
from pathlib import Path
import sys
import traceback


def run_tests(report_dir):
    import pytest

    test_file = Path(__file__).with_name("invariants.py")
    args = [str(test_file), "-q", "-rs", "-p", "no:cacheprovider"]
    if report_dir:
        args.extend(["--junitxml", str(report_dir / "results.xml")])
    return int(pytest.main(args))


builtins.session = session  # noqa: F821 (injected by ChimeraX)
report_dir = os.environ.get("CHIMENODES_GL_REPORT_DIR")
if not report_dir:
    sys.exit(run_tests(None))

report_dir = Path(report_dir)
with (report_dir / "pytest.log").open("w", encoding="utf-8") as log:
    with redirect_stdout(log), redirect_stderr(log):
        try:
            status = run_tests(report_dir)
        except ImportError:
            traceback.print_exc()
            status = 1
sys.exit(status)
