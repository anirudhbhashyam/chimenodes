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


def test_remote_needs_repo(tmp_path):
    r = _run("--dry-run", "--chimerax", _stub(tmp_path))
    assert r.returncode != 0 and "repository" in r.stderr


def test_remote_dry_run_url(tmp_path):
    r = _run("--dry-run", "--repo", "https://github.com/o/chimenodes.git", "--ref", "v1",
             "--chimerax", _stub(tmp_path))
    assert r.returncode == 0 and "github.com/o/chimenodes/archive/v1.tar.gz" in r.stdout


def test_uninstall_dry_run(tmp_path):
    r = _run("--uninstall", "--dry-run", "--chimerax", _stub(tmp_path))
    assert r.returncode == 0 and "toolshed uninstall ChimeraX-Chimenodes" in r.stdout


def test_bad_local_dir(tmp_path):
    r = _run("--local", str(tmp_path), "--chimerax", _stub(tmp_path))
    assert r.returncode != 0 and "bundle_info.xml" in r.stderr


def test_bundle_declares_shader_data_dir():
    xml = open(os.path.join(ROOT, "bundle_info.xml")).read()
    assert "<DataDir>shaders</DataDir>" in xml
