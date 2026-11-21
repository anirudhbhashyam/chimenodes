"""Launch the GL invariants once when a ChimeraX executable is available."""
import os
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree

import pytest

from scripts.dev_install import find_chimerax


@pytest.mark.gl
def test_chimerax_gl_invariants(tmp_path):
    executable = find_chimerax()
    if not executable:
        pytest.skip("ChimeraX executable not found (set CHIMERAX_EXE to override discovery)")

    options = []
    has_display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    if sys.platform.startswith("linux") and not has_display:
        options = ["--nogui", "--offscreen"]

    env = {**os.environ, "CHIMENODES_GL_REPORT_DIR": str(tmp_path)}
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTEST_PLUGINS", None)
    try:
        result = subprocess.run(
            [str(Path(executable).resolve()), *options, "--exit", "--script", "run_gl.py"],
            cwd=Path(__file__).resolve().parent,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("ChimeraX GL tests timed out after 120 seconds", pytrace=False)

    log = tmp_path / "pytest.log"
    report = tmp_path / "results.xml"
    output = log.read_text(encoding="utf-8") if log.is_file() else ""
    if result.returncode or not report.is_file():
        pytest.fail(f"ChimeraX GL run exited with status {result.returncode}\n"
                    f"{result.stdout}{result.stderr}{output}", pytrace=False)

    cases = ElementTree.parse(report).findall(".//testcase")
    if not cases or any(case.find("failure") is not None or case.find("error") is not None
                        for case in cases):
        pytest.fail(output, pytrace=False)
    skipped = [case.find("skipped") for case in cases]
    if all(skip is not None for skip in skipped):
        pytest.skip(skipped[0].get("message"))
    print(output, end="")
