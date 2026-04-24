"""Integration tests for the semantic_scholar_mcp standalone auto-stub hook."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from semantic_scholar_mcp.tools.discovery import (
    semantic_scholar_search,
    discover_related,
    get_paper_by_doi,
)


def _mk_wiki(tmp_path):
    wiki = tmp_path / "academic"
    (wiki / "wiki").mkdir(parents=True)
    (wiki / "CLAUDE.md").write_text("test\n")
    (wiki / "raw" / "papers").mkdir(parents=True)
    return wiki


def _s2_search_response():
    return MagicMock(
        status_code=200,
        json=MagicMock(return_value={"data": [
            {
                "paperId": "abc",
                "title": "Hooked Paper",
                "authors": [{"name": "A. Author"}],
                "year": 2024,
                "venue": "ICML",
                "abstract": "An abstract.",
                "externalIds": {"DOI": "10.1/standalone"},
                "citationCount": 5,
            },
        ]}),
    )


@pytest.mark.asyncio
async def test_search_writes_stub_when_wiki_resolved(tmp_path, monkeypatch):
    wiki = _mk_wiki(tmp_path)
    monkeypatch.setenv("ACADEMIC_WIKI_DEFAULT", str(wiki))

    with patch("requests.get", return_value=_s2_search_response()):
        results = await semantic_scholar_search("test query", limit=1)

    assert len(results) == 1
    stub = wiki / "raw" / "papers" / "s2-doi-10.1_standalone" / "s2-doi-10.1_standalone.md"
    assert stub.is_file()


@pytest.mark.asyncio
async def test_search_returns_results_when_no_wiki(tmp_path, monkeypatch):
    monkeypatch.delenv("ACADEMIC_WIKI_DEFAULT", raising=False)
    monkeypatch.chdir(tmp_path)

    with patch("requests.get", return_value=_s2_search_response()):
        results = await semantic_scholar_search("test query", limit=1)

    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_returns_results_when_hook_raises(tmp_path, monkeypatch):
    """If write_s2_stubs raises, the tool still returns its S2 results.

    Also asserts the patched writer was actually invoked.
    """
    wiki = _mk_wiki(tmp_path)
    monkeypatch.setenv("ACADEMIC_WIKI_DEFAULT", str(wiki))

    with patch("requests.get", return_value=_s2_search_response()), \
         patch("academic_wiki_lib.s2_stub.write_s2_stubs",
               side_effect=RuntimeError("bug in stub writer")) as mock_writer:
        results = await semantic_scholar_search("test query", limit=1)

    assert len(results) == 1
    assert mock_writer.called


@pytest.mark.asyncio
async def test_discover_related_writes_stubs(tmp_path, monkeypatch):
    wiki = _mk_wiki(tmp_path)
    monkeypatch.setenv("ACADEMIC_WIKI_DEFAULT", str(wiki))

    paper_block = {
        "paperId": "rel1",
        "title": "Related",
        "authors": [{"name": "B"}],
        "year": 2023,
        "venue": "NeurIPS",
        "abstract": "",
        "externalIds": {"DOI": "10.1/standalone-rel"},
        "citationCount": 0,
    }
    refs_resp = MagicMock(status_code=200, json=MagicMock(
        return_value={"data": [{"citedPaper": paper_block}]}))

    with patch("requests.get", return_value=refs_resp):
        result = await discover_related("10.1/source", limit=5)

    assert result["total_found"] >= 1
    stub = wiki / "raw" / "papers" / "s2-doi-10.1_standalone-rel" / "s2-doi-10.1_standalone-rel.md"
    assert stub.is_file()


@pytest.mark.asyncio
async def test_get_paper_by_doi_writes_stub(tmp_path, monkeypatch):
    wiki = _mk_wiki(tmp_path)
    monkeypatch.setenv("ACADEMIC_WIKI_DEFAULT", str(wiki))

    single_resp = MagicMock(status_code=200, json=MagicMock(return_value={
        "paperId": "single",
        "title": "Single Lookup",
        "authors": [{"name": "C"}],
        "year": 2022,
        "venue": "AAAI",
        "abstract": "Brief.",
        "externalIds": {"DOI": "10.1/standalone-single"},
        "citationCount": 1,
    }))

    with patch("requests.get", return_value=single_resp):
        result = await get_paper_by_doi("10.1/standalone-single")

    assert result is not None
    stub = wiki / "raw" / "papers" / "s2-doi-10.1_standalone-single" / "s2-doi-10.1_standalone-single.md"
    assert stub.is_file()


@pytest.mark.asyncio
async def test_get_paper_by_doi_none_result_no_write(tmp_path, monkeypatch):
    wiki = _mk_wiki(tmp_path)
    monkeypatch.setenv("ACADEMIC_WIKI_DEFAULT", str(wiki))

    miss = MagicMock(status_code=404)
    with patch("requests.get", return_value=miss):
        result = await get_paper_by_doi("10.1/missing")

    assert result is None
    assert list((wiki / "raw" / "papers").iterdir()) == []
