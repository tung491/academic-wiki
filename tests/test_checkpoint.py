"""Tests for compile checkpoint management."""
import os
import tempfile
from datetime import datetime, timezone

import pytest
import yaml

from academic_wiki_lib.checkpoint import (
    create_checkpoint,
    delete_checkpoint,
    get_pending_papers,
    read_checkpoint,
    write_checkpoint,
    update_paper_statuses,
    is_stale,
    CHECKPOINT_FILENAME,
)


@pytest.fixture
def wiki_dir(tmp_path):
    (tmp_path / "outputs").mkdir()
    return tmp_path


class TestCreateCheckpoint:
    def test_creates_file_with_correct_structure(self, wiki_dir):
        papers = [("paper-a", "/path/a.md"), ("paper-b", "/path/b.md")]
        cp = create_checkpoint(wiki_dir, papers, wave_size=2)

        assert cp["status"] == "in-progress"
        assert cp["total"] == 2
        assert cp["wave-size"] == 2
        assert cp["last-completed-wave"] == -1
        assert cp["papers"] == {"paper-a": "pending", "paper-b": "pending"}
        assert cp["errors"] == {}
        assert cp["wave-commits"] == []
        assert "run-id" in cp
        assert "squash-base" in cp

    def test_writes_to_disk(self, wiki_dir):
        papers = [("p1", "/path/p1.md")]
        create_checkpoint(wiki_dir, papers, wave_size=1)
        path = wiki_dir / "outputs" / CHECKPOINT_FILENAME
        assert path.exists()
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data["total"] == 1


class TestReadCheckpoint:
    def test_returns_none_when_no_file(self, wiki_dir):
        assert read_checkpoint(wiki_dir) is None

    def test_reads_existing_checkpoint(self, wiki_dir):
        papers = [("p1", "/x")]
        create_checkpoint(wiki_dir, papers, wave_size=1)
        cp = read_checkpoint(wiki_dir)
        assert cp is not None
        assert cp["total"] == 1


class TestUpdatePaperStatuses:
    def test_flips_statuses_and_records_errors(self, wiki_dir):
        papers = [("p1", "/x"), ("p2", "/y"), ("p3", "/z")]
        cp = create_checkpoint(wiki_dir, papers, wave_size=3)
        results = {"p1": ("ok", None), "p2": ("failed", "empty extract"), "p3": ("ok", None)}
        update_paper_statuses(wiki_dir, results, wave_commit_sha="abc123")
        cp = read_checkpoint(wiki_dir)
        assert cp["papers"]["p1"] == "ok"
        assert cp["papers"]["p2"] == "failed"
        assert cp["papers"]["p3"] == "ok"
        assert cp["errors"]["p2"] == "empty extract"
        assert cp["last-completed-wave"] == 0
        assert cp["wave-commits"] == ["abc123"]


class TestIsStale:
    def test_not_stale_when_recent(self, wiki_dir):
        papers = [("p1", "/x")]
        create_checkpoint(wiki_dir, papers, wave_size=1)
        assert is_stale(wiki_dir) is False

    def test_stale_when_old(self, wiki_dir):
        papers = [("p1", "/x")]
        cp = create_checkpoint(wiki_dir, papers, wave_size=1)
        # Manually backdate the run-id
        cp["run-id"] = "2020-01-01T00:00:00Z"
        write_checkpoint(wiki_dir, cp)
        assert is_stale(wiki_dir) is True


class TestDeleteCheckpoint:
    def test_delete_removes_file(self, wiki_dir):
        papers = [("p1", "/x")]
        create_checkpoint(wiki_dir, papers, wave_size=1)
        delete_checkpoint(wiki_dir)
        assert read_checkpoint(wiki_dir) is None


class TestGetPendingPapers:
    def test_returns_pending_and_failed(self, wiki_dir):
        papers = [("p1", "/x"), ("p2", "/y"), ("p3", "/z")]
        create_checkpoint(wiki_dir, papers, wave_size=3)
        results = {"p1": ("ok", None), "p2": ("failed", "err")}
        update_paper_statuses(wiki_dir, results, wave_commit_sha="abc")
        pending = get_pending_papers(wiki_dir)
        assert "p2" in pending
        assert "p3" in pending
        assert "p1" not in pending

    def test_returns_empty_when_no_checkpoint(self, wiki_dir):
        assert get_pending_papers(wiki_dir) == []
