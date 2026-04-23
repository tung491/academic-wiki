"""Tests for cross-paper helpers."""
from __future__ import annotations

import pytest

from academic_wiki_lib.cross_paper import compute_top_k_neighbors, append_candidates
from academic_wiki_lib.frontmatter import write_frontmatter


@pytest.fixture
def wiki_dir(tmp_path):
    (tmp_path / "wiki" / "papers").mkdir(parents=True)
    (tmp_path / "outputs" / "reports").mkdir(parents=True)
    return tmp_path


def _make_paper(wiki_dir, paper_id, tags, year=2020):
    path = wiki_dir / "wiki" / "papers" / f"{paper_id}.md"
    write_frontmatter(path, {
        "paper-id": paper_id,
        "type": "paper",
        "title": paper_id,
        "year": year,
        "tags": tags,
    }, "# " + paper_id + "\n")


class TestComputeTopKNeighbors:
    def test_ranks_by_shared_field_and_method_tags(self, wiki_dir):
        _make_paper(wiki_dir, "target", ["paper", "field/nlp", "method/attention"])
        _make_paper(wiki_dir, "best", ["paper", "field/nlp", "method/attention"], year=2023)
        _make_paper(wiki_dir, "medium", ["paper", "field/nlp"], year=2022)
        _make_paper(wiki_dir, "none", ["paper", "field/vision"], year=2021)

        result = compute_top_k_neighbors(wiki_dir, "target", ["best", "medium", "none"], k=3)
        assert result == ["best", "medium"]  # 'none' has 0 overlap, excluded

    def test_excludes_year_and_venue_tags(self, wiki_dir):
        _make_paper(wiki_dir, "target", ["paper", "year/2020", "venue/neurips"])
        _make_paper(wiki_dir, "match", ["paper", "year/2020", "venue/neurips"])
        result = compute_top_k_neighbors(wiki_dir, "target", ["match"], k=3)
        assert result == []  # no field/ or method/ overlap

    def test_respects_k_limit(self, wiki_dir):
        _make_paper(wiki_dir, "target", ["paper", "field/nlp"])
        for i in range(5):
            _make_paper(wiki_dir, f"p{i}", ["paper", "field/nlp"])
        result = compute_top_k_neighbors(wiki_dir, "target",
                                         [f"p{i}" for i in range(5)], k=2)
        assert len(result) == 2

    def test_year_tiebreak_prefers_recent(self, wiki_dir):
        _make_paper(wiki_dir, "target", ["paper", "field/nlp"])
        _make_paper(wiki_dir, "old", ["paper", "field/nlp"], year=2010)
        _make_paper(wiki_dir, "new", ["paper", "field/nlp"], year=2023)
        result = compute_top_k_neighbors(wiki_dir, "target", ["old", "new"], k=2)
        assert result == ["new", "old"]

    def test_missing_neighbor_skipped(self, wiki_dir):
        _make_paper(wiki_dir, "target", ["paper", "field/nlp"])
        _make_paper(wiki_dir, "p1", ["paper", "field/nlp"])
        result = compute_top_k_neighbors(wiki_dir, "target",
                                         ["p1", "nonexistent"], k=3)
        assert result == ["p1"]


class TestAppendCandidates:
    def test_creates_file_on_first_append(self, wiki_dir):
        entries = [{
            "description": "A claim restated",
            "type": "claim",
            "paper_a": "p1",
            "paper_b": "p2",
            "quote_a": "foo",
            "quote_b": "foo variant",
            "relationship": "equivalent",
        }]
        append_candidates(wiki_dir, entries)
        reports = list((wiki_dir / "outputs" / "reports").glob("*-promotion-candidates.md"))
        assert len(reports) == 1
        content = reports[0].read_text()
        assert "A claim restated" in content
        assert "[[p1]]" in content
        assert "[[p2]]" in content

    def test_dedups_on_repeat_append(self, wiki_dir):
        entries = [{
            "description": "dup",
            "type": "claim",
            "paper_a": "p1",
            "paper_b": "p2",
            "quote_a": "x",
            "quote_b": "y",
            "relationship": "equivalent",
        }]
        append_candidates(wiki_dir, entries)
        append_candidates(wiki_dir, entries)
        reports = list((wiki_dir / "outputs" / "reports").glob("*-promotion-candidates.md"))
        assert len(reports) == 1
        content = reports[0].read_text()
        assert content.count("dup") == 1
