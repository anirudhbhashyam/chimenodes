"""Tests for install.sh using a stub ChimeraX executable (no real ChimeraX needed)."""
from __future__ import annotations

import os
import stat
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT = os.path.join(ROOT, "install.sh")

pytestmark = pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX shell script")


def _stub(tmp_path, version="1.11.1"):
    p = tmp_path / "ChimeraX"
    p.write_text('#!/bin/sh\nif [ "$1" = "--version" ]; then\n'
                 '  echo "UCSF ChimeraX version: %s (2026-01-23)"; exit 0; fi\n'
                 'echo "stub $@"; exit 0\n' % version)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


def _run(*args, env=None):
    e = dict(os.environ)
    e.pop("CHIMERAX_EXE", None)
    e.update(env or {})
    return subprocess.run(["sh", SCRIPT] + list(args), capture_output=True, text=True, env=e)


def test_syntax():
    assert subprocess.run(["sh", "-n", SCRIPT]).returncode == 0


def test_dry_run_local(tmp_path):
    r = _run("--dry-run", "--local", ROOT, "--chimerax", _stub(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "devel install" in r.stdout and "user true" in r.stdout


def test_too_old_chimerax_rejected(tmp_path):
    r = _run("--dry-run", "--local", ROOT, "--chimerax", _stub(tmp_path, "1.7.1"))
    assert r.returncode != 0 and "too old" in r.stderr


def test_missing_executable():
    r = _run("--chimerax", "/definitely/not/here")
    assert r.returncode != 0 and "not executable" in r.stderr


def test_default_repo_is_used(tmp_path):
    r = _run("--dry-run", "--chimerax", _stub(tmp_path))
    assert r.returncode == 0 and "github.com/anirudhbhashyam/chimenodes/archive/main.tar.gz" in r.stdout


@pytest.mark.parametrize("option", ["--repo", "--ref"])
def test_source_option_is_rejected(option):
    r = _run(option, "custom")
    assert r.returncode != 0 and f"unknown option: {option}" in r.stderr


def test_source_environment_overrides_are_ignored(tmp_path):
    r = _run("--dry-run", "--chimerax", _stub(tmp_path), env={
        "CHIMENODES_REPO": "https://github.com/example/fork",
        "CHIMENODES_REF": "v1",
    })
    assert r.returncode == 0, r.stderr
    assert "https://github.com/anirudhbhashyam/chimenodes/archive/main.tar.gz" in r.stdout
    assert "github.com/example/fork" not in r.stdout


def test_uninstall_dry_run(tmp_path):
    r = _run("--uninstall", "--dry-run", "--chimerax", _stub(tmp_path))
    assert r.returncode == 0 and "toolshed uninstall ChimeraX-Chimenodes" in r.stdout


def test_bad_local_dir(tmp_path):
    r = _run("--local", str(tmp_path), "--chimerax", _stub(tmp_path))
    assert r.returncode != 0 and "bundle_info.xml" in r.stderr


def test_bundle_declares_shader_data_dir():
    xml = open(os.path.join(ROOT, "bundle_info.xml")).read()
    assert "<DataDir>shaders</DataDir>" in xml


def test_truncated_download_runs_nothing(tmp_path):
    """`curl | sh` of a cut-off script must not execute any install step."""
    text = open(SCRIPT).read()
    cut = tmp_path / "partial.sh"
    cut.write_text(text[: len(text) // 2])          # cut mid-way through the function definitions
    r = subprocess.run(["sh", str(cut)], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert "==>" not in r.stdout and "==>" not in r.stderr


def test_help_works_when_piped():
    r = subprocess.run("cat '%s' | sh -s -- --help" % SCRIPT, shell=True, capture_output=True, text=True)
    assert r.returncode == 0 and "--build-only" in r.stdout
    assert "--chimerax" in r.stdout and "--help" in r.stdout
    assert "--repo" not in r.stdout and "--ref" not in r.stdout


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS app-bundle discovery")
def test_newest_chimerax_app_wins_numerically(tmp_path):
    """ChimeraX-1.100 is newer than ChimeraX-1.99 even though it sorts earlier as text."""
    for ver in ("1.99", "1.100"):
        exe = tmp_path / "Applications" / ("ChimeraX-%s.app" % ver) / "Contents" / "MacOS" / "ChimeraX"
        exe.parent.mkdir(parents=True)
        exe.write_text('#!/bin/sh\nif [ "$1" = "--version" ]; then echo "UCSF ChimeraX version: %s (2030-01-01)"; fi\n' % ver)
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    r = _run("--dry-run", "--local", ROOT, env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stderr
    assert "ChimeraX-1.100.app" in r.stdout
