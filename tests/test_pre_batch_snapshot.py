"""Tests for pre-batch snapshot helper."""
from __future__ import annotations

import pytest

from academic_wiki_lib.pre_batch_snapshot import (
    write_snapshot, read_snapshot, snapshot_path, delete_snapshot, scan_targets,
)


@pytest.fixture
def wiki_dir(tmp_path):
    (tmp_path / "outputs").mkdir()
    (tmp_path / "wiki" / "papers").mkdir(parents=True)
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    (tmp_path / "wiki" / "methods").mkdir(parents=True)
    (tmp_path / "wiki" / "open-problems").mkdir(parents=True)
    (tmp_path / "wiki" / "venues").mkdir(parents=True)
    return tmp_path


class TestWriteAndRead:
    def test_roundtrip(self, wiki_dir):
        targets = ["wiki/papers/a.md", "wiki/concepts/foo.md"]
        write_snapshot(wiki_dir, targets)
        got = read_snapshot(wiki_dir)
        assert got == targets

    def test_read_returns_empty_when_missing(self, wiki_dir):
        assert read_snapshot(wiki_dir) == []

    def test_delete_removes_file(self, wiki_dir):
        write_snapshot(wiki_dir, ["wiki/papers/a.md"])
        assert snapshot_path(wiki_dir).exists()
        delete_snapshot(wiki_dir)
        assert not snapshot_path(wiki_dir).exists()

    def test_delete_is_noop_when_missing(self, wiki_dir):
        delete_snapshot(wiki_dir)


class TestScanTargets:
    def test_scans_all_known_subdirs(self, wiki_dir):
        (wiki_dir / "wiki" / "papers" / "p1.md").write_text("---\n---\n")
        (wiki_dir / "wiki" / "concepts" / "c1.md").write_text("---\n---\n")
        (wiki_dir / "wiki" / "methods" / "m1.md").write_text("---\n---\n")
        (wiki_dir / "wiki" / "open-problems" / "o1.md").write_text("---\n---\n")
        (wiki_dir / "wiki" / "venues" / "v1.md").write_text("---\n---\n")
        targets = scan_targets(wiki_dir)
        assert "wiki/papers/p1.md" in targets
        assert "wiki/concepts/c1.md" in targets
        assert "wiki/methods/m1.md" in targets
        assert "wiki/open-problems/o1.md" in targets
        assert "wiki/venues/v1.md" in targets

    def test_empty_wiki_returns_empty(self, wiki_dir):
        assert scan_targets(wiki_dir) == []
