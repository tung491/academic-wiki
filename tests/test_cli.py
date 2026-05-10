"""Tests for the academic_wiki_lib.cli module — invoked via `python -m academic_wiki_lib.cli`."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Invoke `python -m academic_wiki_lib.cli` with the given args. Returns the CompletedProcess."""
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{SCRIPTS_DIR}{os.pathsep}{existing}" if existing else str(SCRIPTS_DIR)
    return subprocess.run(
        [sys.executable, "-m", "academic_wiki_lib.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
    )


class TestAcquireRelease:
    def test_acquire_creates_lock_file(self, tmp_path):
        result = _run_cli("acquire", str(tmp_path), "--op", "ingest")
        assert result.returncode == 0, result.stderr
        assert (tmp_path / ".lock").exists()
        content = (tmp_path / ".lock").read_text()
        assert "ingest" in content

    def test_release_removes_lock_file(self, tmp_path):
        # Acquire first
        acq = _run_cli("acquire", str(tmp_path), "--op", "compile")
        assert acq.returncode == 0
        # Then release
        rel = _run_cli("release", str(tmp_path))
        assert rel.returncode == 0, rel.stderr
        assert not (tmp_path / ".lock").exists()

    def test_release_silent_if_lock_absent(self, tmp_path):
        result = _run_cli("release", str(tmp_path))
        assert result.returncode == 0
        assert result.stderr == ""

    def test_acquire_fails_with_exit_1_when_held_by_live_process(self, tmp_path):
        # Plant a lock claiming this very process holds it
        (tmp_path / ".lock").write_text(f"{os.getpid()}:2026-04-16T10:00:00Z:compile")
        result = _run_cli("acquire", str(tmp_path), "--op", "ingest")
        assert result.returncode == 1
        assert "in progress" in result.stderr.lower() or "held" in result.stderr.lower() or "compile" in result.stderr
