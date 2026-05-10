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


class TestSourceSha:
    def test_source_sha_prints_hex_digest(self, tmp_path):
        target = tmp_path / "input.bin"
        target.write_bytes(b"hello world")
        result = _run_cli("source-sha", str(target))
        assert result.returncode == 0
        # SHA-256 of "hello world" is b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9
        assert result.stdout.strip() == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

    def test_source_sha_missing_file_exits_nonzero(self, tmp_path):
        result = _run_cli("source-sha", str(tmp_path / "does-not-exist"))
        assert result.returncode != 0


import json


class TestFindPaper:
    def _setup_wiki_with_paper(self, tmp_path: Path, paper_id: str, identifiers: dict) -> None:
        papers_dir = tmp_path / "wiki" / "papers"
        papers_dir.mkdir(parents=True)
        # Minimal frontmatter + body
        ident_yaml = "\n".join(f"  {k}: {v}" for k, v in identifiers.items())
        (papers_dir / f"{paper_id}.md").write_text(
            f"---\npaper-id: {paper_id}\nidentifiers:\n{ident_yaml}\n---\n\n# {paper_id}\n"
        )

    def test_find_paper_returns_match_by_doi(self, tmp_path):
        self._setup_wiki_with_paper(tmp_path, "smith2020quantum", {"doi": "10.1234/abc"})
        result = _run_cli(
            "find-paper", str(tmp_path), "--doi", "10.1234/abc",
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload == {"paper_id": "smith2020quantum"}

    def test_find_paper_returns_null_paper_id_when_no_match(self, tmp_path):
        # Empty wiki — no papers/ dir
        (tmp_path / "wiki").mkdir()
        result = _run_cli(
            "find-paper", str(tmp_path), "--doi", "10.9999/none",
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload == {"paper_id": None}

    def test_find_paper_with_no_identifiers_exits_zero_and_returns_null(self, tmp_path):
        (tmp_path / "wiki").mkdir()
        result = _run_cli("find-paper", str(tmp_path))
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload == {"paper_id": None}


class TestPaperId:
    def test_paper_id_generates_no_collision(self, tmp_path):
        result = _run_cli(
            "paper-id", str(tmp_path),
            "--lastname", "Smith",
            "--year", "2020",
            "--title", "Quantum Foo Bar",
        )
        assert result.returncode == 0, result.stderr
        # First meaningful word of "Quantum Foo Bar" is "quantum"
        assert result.stdout.strip() == "smith2020quantum"

    def test_paper_id_resolves_collision_with_numeric_suffix(self, tmp_path):
        # Plant an existing paper at the would-be id
        papers = tmp_path / "wiki" / "papers"
        papers.mkdir(parents=True)
        (papers / "smith2020quantum.md").write_text("---\npaper-id: smith2020quantum\n---\n")
        result = _run_cli(
            "paper-id", str(tmp_path),
            "--lastname", "Smith",
            "--year", "2020",
            "--title", "Quantum Other Title",
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "smith2020quantum2"
