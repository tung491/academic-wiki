"""Tests for upsert_entity atomic create/merge."""
from __future__ import annotations

import pytest

from academic_wiki_lib.entity_pages import upsert_entity
from academic_wiki_lib.frontmatter import read_frontmatter


@pytest.fixture
def wiki_dir(tmp_path):
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    (tmp_path / "wiki" / "methods").mkdir(parents=True)
    (tmp_path / "wiki" / "open-problems").mkdir(parents=True)
    return tmp_path


class TestUpsertEntityCreate:
    def test_creates_new_concept_page(self, wiki_dir):
        created = upsert_entity(
            wiki_dir, slug="attention-mechanism", kind="concept",
            paper_id="vaswani2017attention",
            title="Attention Mechanism",
            tags=["field/nlp"],
            body_contribution="Vaswani et al. propose attention as the core primitive.",
        )
        assert created is True
        path = wiki_dir / "wiki" / "concepts" / "attention-mechanism.md"
        assert path.exists()
        fm, body = read_frontmatter(path)
        assert fm["type"] == "concept"
        assert fm["slug"] == "attention-mechanism"
        assert fm["sources"] == ["vaswani2017attention"]
        assert fm["status"] == "active"
        assert "field/nlp" in fm["tags"]

    def test_status_default_open_for_open_problem(self, wiki_dir):
        # No status_default argument — exercises the _DEFAULT_STATUS mapping
        created = upsert_entity(
            wiki_dir, slug="ai-safety", kind="open-problem",
            paper_id="smith2024safety",
            title="AI Safety",
            tags=["field/ai-safety"],
            body_contribution="An unresolved alignment question.",
        )
        assert created is True
        fm, _ = read_frontmatter(wiki_dir / "wiki" / "open-problems" / "ai-safety.md")
        assert fm["status"] == "open"


class TestUpsertEntityMerge:
    def test_merge_appends_new_source(self, wiki_dir):
        upsert_entity(
            wiki_dir, slug="attention", kind="concept",
            paper_id="paper-a", title="Attention",
            tags=["field/nlp"],
            body_contribution="First contribution.",
        )
        created = upsert_entity(
            wiki_dir, slug="attention", kind="concept",
            paper_id="paper-b", title="Attention",
            tags=["field/vision"],
            body_contribution="Second contribution from paper-b.",
        )
        assert created is False
        fm, body = read_frontmatter(wiki_dir / "wiki" / "concepts" / "attention.md")
        assert fm["sources"] == ["paper-a", "paper-b"]
        assert "field/nlp" in fm["tags"]
        assert "field/vision" in fm["tags"]
        assert "Second contribution from paper-b." in body

    def test_merge_dedups_source(self, wiki_dir):
        upsert_entity(
            wiki_dir, slug="attention", kind="concept",
            paper_id="paper-a", title="Attention",
            tags=["field/nlp"], body_contribution="First.",
        )
        upsert_entity(
            wiki_dir, slug="attention", kind="concept",
            paper_id="paper-a", title="Attention",
            tags=["field/nlp"], body_contribution="First (again).",
        )
        fm, _ = read_frontmatter(wiki_dir / "wiki" / "concepts" / "attention.md")
        # Only one paper-a entry
        assert fm["sources"] == ["paper-a"]

    def test_merge_bumps_updated_preserves_created(self, wiki_dir):
        upsert_entity(
            wiki_dir, slug="attention", kind="concept",
            paper_id="paper-a", title="Attention",
            tags=[], body_contribution="First.",
        )
        fm_first, _ = read_frontmatter(wiki_dir / "wiki" / "concepts" / "attention.md")
        created_first = fm_first["created"]
        upsert_entity(
            wiki_dir, slug="attention", kind="concept",
            paper_id="paper-b", title="Attention",
            tags=[], body_contribution="Second.",
        )
        fm_second, _ = read_frontmatter(wiki_dir / "wiki" / "concepts" / "attention.md")
        assert fm_second["created"] == created_first  # preserved


class TestUpsertEntityValidation:
    def test_rejects_unknown_kind(self, wiki_dir):
        with pytest.raises(ValueError):
            upsert_entity(
                wiki_dir, slug="x", kind="banana",
                paper_id="p", title="X", tags=[], body_contribution="",
            )
