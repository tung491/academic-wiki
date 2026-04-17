"""Tests for the MDPI publisher extractor."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from academic_wiki_mcp.publishers.mdpi import MDPIPublisher


@pytest.fixture
def publisher():
    return MDPIPublisher()


def _mock_text(txt: str) -> AsyncMock:
    el = AsyncMock()
    el.text.return_value = txt
    return el


def _mock_meta(content: str) -> AsyncMock:
    el = AsyncMock()
    el.attribute.return_value = content
    return el


@pytest.mark.asyncio
async def test_extract_metadata_title_and_authors(publisher):
    browser = AsyncMock()

    async def qs(sel):
        return {
            "h1.title": _mock_text("Graph Neural Networks for Materials"),
            ".art-abstract p": _mock_text("We apply GNN to material science."),
            ".art-abstract .html-p": None,
            'meta[name="citation_doi"]': _mock_meta("10.3390/ijms1234"),
            'meta[name="citation_publication_date"]': _mock_meta("2023-03-15"),
            'meta[name="citation_journal_title"]': _mock_meta("International Journal of Molecular Sciences"),
        }.get(sel)

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        ".art-authors .sciprofiles-link": [
            _mock_text("Alicia Garcia"), _mock_text("Bob Lee")
        ],
        ".art-keyword": [
            _mock_text("graph neural networks;"),
            _mock_text("materials science"),
        ],
    }.get(sel, [])

    meta = await publisher.extract_metadata(browser)
    assert meta.title == "Graph Neural Networks for Materials"
    assert meta.authors == ["Alicia Garcia", "Bob Lee"]
    assert meta.doi == "10.3390/ijms1234"
    assert meta.year == 2023
    # semicolons stripped from keywords
    assert "graph neural networks" in meta.keywords
    assert "materials science" in meta.keywords


@pytest.mark.asyncio
async def test_extract_metadata_keyword_semicolon_stripped(publisher):
    """Keywords with trailing semicolons are stripped."""
    browser = AsyncMock()

    async def qs(sel):
        return {
            "h1.title": _mock_text("Test"),
            ".art-abstract p": None,
            ".art-abstract .html-p": None,
            'meta[name="citation_doi"]': _mock_meta(""),
            'meta[name="citation_publication_date"]': _mock_meta(""),
            'meta[name="citation_journal_title"]': _mock_meta(""),
        }.get(sel)

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        ".art-authors .sciprofiles-link": [],
        ".art-keyword": [
            _mock_text("keyword1;"),
            _mock_text("keyword2;;"),
            _mock_text("keyword3"),
        ],
    }.get(sel, [])

    meta = await publisher.extract_metadata(browser)
    assert meta.keywords == ["keyword1", "keyword2", "keyword3"]


@pytest.mark.asyncio
async def test_extract_figures_primary_path(publisher):
    """Primary path uses a.html-img-zoom img."""
    browser = AsyncMock()
    browser.evaluate.return_value = [
        {"id": "https://mdpi.com/fig1.png", "url": "https://mdpi.com/fig1.png", "caption": "Figure 1: GNN overview"},
        {"id": "https://mdpi.com/fig2.png", "url": "https://mdpi.com/fig2.png", "caption": ""},
    ]

    figures = await publisher.extract_figures(browser)
    assert len(figures) == 2
    assert figures[0].filename == "fig1.png"
    assert figures[0].caption == "Figure 1: GNN overview"
    assert figures[1].filename == "fig2.png"


@pytest.mark.asyncio
async def test_extract_figures_empty(publisher):
    browser = AsyncMock()
    browser.evaluate.return_value = []
    figures = await publisher.extract_figures(browser)
    assert figures == []


@pytest.mark.asyncio
async def test_extract_sections_body_with_headings(publisher):
    """Sections include body content from TreeWalker evaluate."""
    browser = AsyncMock()

    async def qs(sel):
        return {".art-abstract p": _mock_text("Abstract content."), ".art-abstract .html-p": None}.get(sel)

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        ".html-bib-entry, .article-bibliography li": [],
    }.get(sel, [])

    browser.evaluate.return_value = [
        {
            "heading": "Introduction",
            "content": [{"type": "paragraph", "text": "GNNs are powerful."}],
        },
        {
            "heading": "Methods",
            "content": [
                {"type": "paragraph", "text": "We use a GCN."},
                {"type": "figure", "figureId": "https://mdpi.com/fig1.png"},
            ],
        },
    ]

    sections = await publisher.extract_sections(browser)
    headings = [s.heading for s in sections]
    assert "Abstract" in headings
    assert "Introduction" in headings
    assert "Methods" in headings

    methods_sec = next(s for s in sections if s.heading == "Methods")
    fig_blocks = [b for b in methods_sec.content if b.type == "figure"]
    assert len(fig_blocks) == 1
    assert fig_blocks[0].figure_id == "https://mdpi.com/fig1.png"
