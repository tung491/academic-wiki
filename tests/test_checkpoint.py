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
    update_final_pass_status,
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


class TestFullTierFields:
    def test_default_tier_is_paper_only(self, wiki_dir):
        papers = [("p1", "/x")]
        cp = create_checkpoint(wiki_dir, papers, wave_size=1)
        assert cp["tier"] == "paper-only"
        assert cp["pre-batch-paper-ids"] == []
        assert cp["final-pass-status"] == "skipped"

    def test_tier_full_sets_final_pass_pending(self, wiki_dir):
        papers = [("p1", "/x")]
        cp = create_checkpoint(
            wiki_dir, papers, wave_size=1,
            tier="full",
            pre_batch_paper_ids=["oldpaper1", "oldpaper2"],
        )
        assert cp["tier"] == "full"
        assert cp["pre-batch-paper-ids"] == ["oldpaper1", "oldpaper2"]
        assert cp["final-pass-status"] == "pending"

    def test_none_pre_batch_coerced_to_empty_list(self, wiki_dir):
        papers = [("p1", "/x")]
        cp = create_checkpoint(wiki_dir, papers, wave_size=1, tier="full",
                               pre_batch_paper_ids=None)
        assert cp["pre-batch-paper-ids"] == []


class TestReadCheckpointBackCompat:
    def test_missing_fields_default_on_read(self, wiki_dir):
        # Write an old-style checkpoint without the new fields
        cp_old = {
            "run-id": "2026-04-01T00:00:00Z",
            "status": "in-progress",
            "total": 1,
            "wave-size": 1,
            "last-completed-wave": -1,
            "papers": {"p1": "pending"},
            "errors": {},
            "squash-base": "",
            "wave-commits": [],
        }
        write_checkpoint(wiki_dir, cp_old)
        cp = read_checkpoint(wiki_dir)
        assert cp["tier"] == "paper-only"
        assert cp["pre-batch-paper-ids"] == []
        assert cp["final-pass-status"] == "skipped"


class TestUpdateFinalPassStatus:
    def test_sets_status(self, wiki_dir):
        papers = [("p1", "/x")]
        create_checkpoint(wiki_dir, papers, wave_size=1, tier="full",
                          pre_batch_paper_ids=[])
        update_final_pass_status(wiki_dir, "in-progress")
        cp = read_checkpoint(wiki_dir)
        assert cp["final-pass-status"] == "in-progress"
        update_final_pass_status(wiki_dir, "ok")
        cp = read_checkpoint(wiki_dir)
        assert cp["final-pass-status"] == "ok"

    def test_rejects_unknown_status(self, wiki_dir):
        papers = [("p1", "/x")]
        create_checkpoint(wiki_dir, papers, wave_size=1, tier="full")
        with pytest.raises(ValueError):
            update_final_pass_status(wiki_dir, "bogus")

    def test_rejects_paper_only_checkpoint(self, wiki_dir):
        papers = [("p1", "/x")]
        create_checkpoint(wiki_dir, papers, wave_size=1)  # paper-only default
        with pytest.raises(ValueError, match="tier='full'"):
            update_final_pass_status(wiki_dir, "in-progress")

    def test_raises_when_no_checkpoint(self, wiki_dir):
        with pytest.raises(FileNotFoundError):
            update_final_pass_status(wiki_dir, "ok")

    def test_rejects_skipped_status(self, wiki_dir):
        # 'skipped' is a create-time terminal state for paper-only; never settable via update
        papers = [("p1", "/x")]
        create_checkpoint(wiki_dir, papers, wave_size=1, tier="full")
        with pytest.raises(ValueError, match="skipped"):
            update_final_pass_status(wiki_dir, "skipped")


class TestCreateCheckpointTierValidation:
    def test_rejects_unknown_tier(self, wiki_dir):
        papers = [("p1", "/x")]
        with pytest.raises(ValueError, match="Unknown tier"):
            create_checkpoint(wiki_dir, papers, wave_size=1, tier="experimental")
