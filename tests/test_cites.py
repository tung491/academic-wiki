"""Tests for cites fuzzy-matcher."""
from __future__ import annotations

from pathlib import Path

import pytest

from academic_wiki_lib.cites import resolve_cites
from academic_wiki_lib.frontmatter import write_frontmatter


@pytest.fixture
def wiki_dir(tmp_path):
    (tmp_path / "wiki" / "papers").mkdir(parents=True)
    return tmp_path


def _make_paper(wiki_dir, paper_id, title, author_surname, year):
    path = wiki_dir / "wiki" / "papers" / f"{paper_id}.md"
    fm = {
        "paper-id": paper_id,
        "type": "paper",
        "title": title,
        "authors": [{"slug": author_surname.lower(), "name": author_surname}],
        "year": year,
    }
    write_frontmatter(path, fm, f"# {title}\n")


class TestResolveCites:
    def test_exact_title_match_resolves(self, wiki_dir):
        _make_paper(wiki_dir, "vaswani2017attention", "Attention Is All You Need",
                    "Vaswani", 2017)
        refs = ["Vaswani, A. Attention Is All You Need. NeurIPS, 2017."]
        result = resolve_cites(wiki_dir, refs, ["vaswani2017attention"])
        matches = result[refs[0]]
        assert matches
        assert matches[0][0] == "vaswani2017attention"
        assert matches[0][1] >= 0.80

    def test_below_threshold_returns_empty(self, wiki_dir):
        _make_paper(wiki_dir, "p1", "Completely Unrelated Title", "Brown", 2020)
        refs = ["Smith, J. A Different Paper. 2019."]
        result = resolve_cites(wiki_dir, refs, ["p1"])
        assert result[refs[0]] == []

    def test_caps_at_five_per_reference(self, wiki_dir):
        for i in range(10):
            _make_paper(wiki_dir, f"p{i}", "Attention Mechanism Survey",
                        "Author" + str(i), 2020 + i)
        refs = ["Author. Attention Mechanism Survey. 2020."]
        pre_batch = [f"p{i}" for i in range(10)]
        result = resolve_cites(wiki_dir, refs, pre_batch)
        assert len(result[refs[0]]) <= 5

    def test_results_sorted_by_score_desc(self, wiki_dir):
        _make_paper(wiki_dir, "close", "Attention Is All You Need", "Vaswani", 2017)
        _make_paper(wiki_dir, "far", "Attention Is Partially Useful", "Vaswani", 2017)
        refs = ["Vaswani. Attention Is All You Need. 2017."]
        result = resolve_cites(wiki_dir, refs, ["close", "far"])
        matches = result[refs[0]]
        assert len(matches) >= 1
        scores = [s for _, s in matches]
        assert scores == sorted(scores, reverse=True)

    def test_missing_paper_skipped(self, wiki_dir):
        _make_paper(wiki_dir, "p1", "Known Paper", "Author", 2020)
        refs = ["Author. Known Paper. 2020."]
        result = resolve_cites(wiki_dir, refs, ["p1", "nonexistent"])
        assert refs[0] in result
