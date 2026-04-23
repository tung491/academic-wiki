"""Tests for backlinks helpers."""
from __future__ import annotations

from pathlib import Path

import pytest

from academic_wiki_lib.backlinks import _target_lock_kind_and_key, insert_backlink


class TestTargetLockKindAndKey:
    def test_paper_path(self):
        kind, key = _target_lock_kind_and_key("wiki/papers/vaswani2017attention.md")
        assert (kind, key) == ("paper", "vaswani2017attention")

    def test_concept_path(self):
        kind, key = _target_lock_kind_and_key("wiki/concepts/attention-mechanism.md")
        assert (kind, key) == ("concept", "attention-mechanism")

    def test_method_path(self):
        kind, key = _target_lock_kind_and_key("wiki/methods/transformer.md")
        assert (kind, key) == ("method", "transformer")

    def test_open_problem_path(self):
        kind, key = _target_lock_kind_and_key("wiki/open-problems/ai-safety.md")
        assert (kind, key) == ("open-problem", "ai-safety")

    def test_venue_path(self):
        kind, key = _target_lock_kind_and_key("wiki/venues/neurips.md")
        assert (kind, key) == ("venue", "neurips")

    def test_rejects_unknown(self):
        with pytest.raises(ValueError):
            _target_lock_kind_and_key("wiki/unknown/foo.md")

    def test_rejects_non_wiki_path(self):
        with pytest.raises(ValueError):
            _target_lock_kind_and_key("outputs/x/y.md")


@pytest.fixture
def wiki_dir(tmp_path):
    (tmp_path / "wiki" / "papers").mkdir(parents=True)
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    return tmp_path


class TestInsertBacklink:
    def test_inserts_when_multiword_slug_matches(self, wiki_dir):
        target = wiki_dir / "wiki" / "papers" / "paper-a.md"
        target.write_text(
            "---\npaper-id: paper-a\n---\n\nWe use the attention mechanism here.\n"
        )
        ok = insert_backlink(wiki_dir, "wiki/papers/paper-a.md", "attention-mechanism")
        assert ok is True
        content = target.read_text()
        assert "[[attention-mechanism]]" in content

    def test_noop_when_already_present(self, wiki_dir):
        target = wiki_dir / "wiki" / "papers" / "paper-a.md"
        target.write_text(
            "---\npaper-id: paper-a\n---\n\nWe use [[attention-mechanism]] here.\n"
        )
        ok = insert_backlink(wiki_dir, "wiki/papers/paper-a.md", "attention-mechanism")
        assert ok is False

    def test_noop_when_no_match(self, wiki_dir):
        target = wiki_dir / "wiki" / "papers" / "paper-a.md"
        target.write_text("---\npaper-id: paper-a\n---\n\nUnrelated content.\n")
        ok = insert_backlink(wiki_dir, "wiki/papers/paper-a.md", "attention-mechanism")
        assert ok is False

    def test_single_word_slug_not_inserted(self, wiki_dir):
        target = wiki_dir / "wiki" / "papers" / "paper-a.md"
        target.write_text("---\npaper-id: paper-a\n---\n\nWe discuss attention widely.\n")
        ok = insert_backlink(wiki_dir, "wiki/papers/paper-a.md", "attention")
        assert ok is False
