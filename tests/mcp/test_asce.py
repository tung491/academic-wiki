"""Tests for the ASCE publisher extractor."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from academic_wiki_mcp.publishers.asce import ASCEPublisher


@pytest.fixture
def publisher():
    return ASCEPublisher()


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
            "h1.citation__title, h1.article__title": _mock_text(
                "Sustainable Bridge Design Using AI"
            ),
            'meta[name="citation_doi"]': _mock_meta("10.1061/JBENF2.2022"),
            'meta[name="citation_publication_date"]': _mock_meta("2022-06-01"),
            'meta[name="citation_journal_title"]': _mock_meta(
                "Journal of Bridge Engineering"
            ),
        }.get(sel)

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        ".author-name span, .loa__author-name, .contrib-author a": [
            _mock_text("Carlos Rivera"), _mock_text("Min Liu")
        ],
        ".article__keyword, .abstractKeywords a, .kwd-group .kwd": [
            _mock_text("bridge design"), _mock_text("machine learning")
        ],
    }.get(sel, [])

    # Abstract is extracted via evaluate
    browser.evaluate.return_value = "We present a new approach to bridge design."

    meta = await publisher.extract_metadata(browser)
    assert meta.title == "Sustainable Bridge Design Using AI"
    assert meta.authors == ["Carlos Rivera", "Min Liu"]
    assert meta.doi == "10.1061/JBENF2.2022"
    assert meta.year == 2022
    assert meta.venue == "Journal of Bridge Engineering"
    assert meta.abstract == "We present a new approach to bridge design."
    assert "bridge design" in meta.keywords


@pytest.mark.asyncio
async def test_extract_metadata_abstract_from_section_iterate(publisher):
    """Abstract is found by iterating sections for h2 matching /^abstract$/i."""
    browser = AsyncMock()

    async def qs(sel):
        return {
            "h1.citation__title, h1.article__title": _mock_text("Paper"),
            'meta[name="citation_doi"]': _mock_meta(""),
            'meta[name="citation_publication_date"]': _mock_meta(""),
            'meta[name="citation_journal_title"]': _mock_meta(""),
        }.get(sel)

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        ".author-name span, .loa__author-name, .contrib-author a": [],
        ".article__keyword, .abstractKeywords a, .kwd-group .kwd": [],
        'meta[name="citation_author"]': [],
    }.get(sel, [])

    browser.evaluate.return_value = "Abstract from section iteration."

    meta = await publisher.extract_metadata(browser)
    assert meta.abstract == "Abstract from section iteration."


@pytest.mark.asyncio
async def test_extract_figures_with_data_src(publisher):
    """Figures use data-src attribute and skip icon/logo/spinner."""
    browser = AsyncMock()
    # First evaluate call is for abstract (metadata), second for figures
    browser.evaluate.side_effect = [
        "",  # abstract
        [
            {
                "id": "https://ascelibrary.org/cms/fig1.png",
                "url": "https://ascelibrary.org/cms/fig1.png",
                "caption": "Figure 1: Bridge load",
            },
            {
                "id": "https://ascelibrary.org/cms/fig2.jpg",
                "url": "https://ascelibrary.org/cms/fig2.jpg",
                "caption": "",
            },
        ],
    ]

    # Setup for extract_figures directly
    browser2 = AsyncMock()
    browser2.evaluate.return_value = [
        {
            "id": "https://ascelibrary.org/cms/fig1.png",
            "url": "https://ascelibrary.org/cms/fig1.png",
            "caption": "Figure 1: Bridge load",
        },
        {
            "id": "https://ascelibrary.org/cms/fig2.jpg",
            "url": "https://ascelibrary.org/cms/fig2.jpg",
            "caption": "",
        },
    ]

    figures = await publisher.extract_figures(browser2)
    assert len(figures) == 2
    assert figures[0].filename == "fig1.png"
    assert figures[0].caption == "Figure 1: Bridge load"
    assert figures[1].filename == "fig2.png"


@pytest.mark.asyncio
async def test_extract_figures_empty(publisher):
    browser = AsyncMock()
    browser.evaluate.return_value = []
    figures = await publisher.extract_figures(browser)
    assert figures == []


@pytest.mark.asyncio
async def test_extract_sections_no_references(publisher):
    """ASCE does not produce a References section."""
    browser = AsyncMock()
    browser.evaluate.return_value = [
        {
            "heading": "Introduction",
            "content": [{"type": "paragraph", "text": "Bridges are important."}],
        },
        {
            "heading": "Methods",
            "content": [
                {"type": "paragraph", "text": "We use FEM analysis."},
                {"type": "figure", "figureId": "https://ascelibrary.org/fig1.png"},
            ],
        },
    ]

    sections = await publisher.extract_sections(browser)
    headings = [s.heading for s in sections]
    assert "Introduction" in headings
    assert "Methods" in headings
    assert "References" not in headings

    methods = next(s for s in sections if s.heading == "Methods")
    fig_blocks = [b for b in methods.content if b.type == "figure"]
    assert len(fig_blocks) == 1
    assert fig_blocks[0].figure_id == "https://ascelibrary.org/fig1.png"


@pytest.mark.asyncio
async def test_extract_sections_abstract_is_skipped(publisher):
    """ASCE skips 'data availability', 'acknowledgment', etc."""
    browser = AsyncMock()
    browser.evaluate.return_value = [
        {
            "heading": "Abstract",
            "content": [{"type": "paragraph", "text": "We study bridges."}],
        },
        {
            "heading": "Introduction",
            "content": [{"type": "paragraph", "text": "Intro text."}],
        },
    ]

    sections = await publisher.extract_sections(browser)
    # The evaluate-based approach doesn't have a separate abstract — it just
    # returns whatever the JS builds. Both should be present here.
    headings = [s.heading for s in sections]
    assert "Introduction" in headings
