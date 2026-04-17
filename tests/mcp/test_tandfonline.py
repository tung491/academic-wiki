"""Tests for the Taylor & Francis publisher extractor."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from academic_wiki_mcp.publishers.tandfonline import TandFPublisher


@pytest.fixture
def publisher():
    return TandFPublisher()


def _mock_text(txt: str) -> AsyncMock:
    el = AsyncMock()
    el.text.return_value = txt
    return el


def _mock_meta(content: str) -> AsyncMock:
    el = AsyncMock()
    el.attribute.return_value = content
    return el


@pytest.mark.asyncio
async def test_extract_metadata_title_nlm(publisher):
    """Title extracted from .NLM_article-title."""
    browser = AsyncMock()

    async def qs(sel):
        return {
            ".NLM_article-title": _mock_text(
                "Machine Learning for Climate Science"
            ),
            ".abstractSection p, .abstract p, #abstract p": _mock_text(
                "We apply ML to climate modeling."
            ),
            ".hlFld-Abstract p": None,
            'meta[name="citation_doi"]': _mock_meta("10.1080/123456"),
            'meta[name="citation_publication_date"]': _mock_meta("2022-04-15"),
            "meta[name=\"dc.Date\"]": None,
            'meta[name="citation_journal_title"]': _mock_meta("Climate Dynamics"),
        }.get(sel)

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        ".entryAuthor a, .author, .contrib-author, .NLM_contrib-group a": [
            _mock_text("Alice Chen"), _mock_text("Bob Yang")
        ],
        ".abstractKeywords a, .keyword, .hlFld-KeywordText a": [
            _mock_text("machine learning,"),
            _mock_text("climate"),
        ],
    }.get(sel, [])

    meta = await publisher.extract_metadata(browser)
    assert meta.title == "Machine Learning for Climate Science"
    assert meta.authors == ["Alice Chen", "Bob Yang"]
    assert meta.doi == "10.1080/123456"
    assert meta.year == 2022
    assert meta.venue == "Climate Dynamics"
    # trailing comma stripped from keyword
    assert "machine learning" in meta.keywords


@pytest.mark.asyncio
async def test_extract_metadata_title_fallback_chain(publisher):
    """Falls through NLM → article-title → h1 → citation_title."""
    browser = AsyncMock()

    async def qs(sel):
        return {
            ".NLM_article-title": None,
            ".article-title": None,
            "h1": _mock_text("H1 Title"),
            ".abstractSection p, .abstract p, #abstract p": None,
            ".hlFld-Abstract p": None,
            'meta[name="citation_doi"]': _mock_meta(""),
            'meta[name="citation_publication_date"]': _mock_meta(""),
            "meta[name=\"dc.Date\"]": None,
            'meta[name="citation_journal_title"]': _mock_meta(""),
        }.get(sel)

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        ".entryAuthor a, .author, .contrib-author, .NLM_contrib-group a": [],
        ".abstractKeywords a, .keyword, .hlFld-KeywordText a": [],
        'meta[name="citation_author"]': [],
    }.get(sel, [])

    meta = await publisher.extract_metadata(browser)
    assert meta.title == "H1 Title"


@pytest.mark.asyncio
async def test_extract_figures_requires_cms_asset(publisher):
    """Figures must have cms/asset in URL."""
    browser = AsyncMock()
    browser.evaluate.return_value = [
        {
            "id": "https://tandfonline.com/cms/asset/fig_climate.png",
            "url": "https://tandfonline.com/cms/asset/fig_climate.png",
            "caption": "Figure 1: Temperature trends",
        },
        {
            "id": "https://tandfonline.com/cms/asset/fig2.png",
            "url": "https://tandfonline.com/cms/asset/fig2.png",
            "caption": "",
        },
    ]

    figures = await publisher.extract_figures(browser)
    assert len(figures) == 2
    assert figures[0].filename == "fig1.png"
    assert figures[0].caption == "Figure 1: Temperature trends"
    assert figures[1].filename == "fig2.png"


@pytest.mark.asyncio
async def test_extract_figures_empty(publisher):
    browser = AsyncMock()
    browser.evaluate.return_value = []
    figures = await publisher.extract_figures(browser)
    assert figures == []


@pytest.mark.asyncio
async def test_extract_sections_with_popup_tables(publisher):
    """Sections built from evaluate including table map logic."""
    browser = AsyncMock()

    async def qs(sel):
        return {
            ".abstractSection p, .abstract p, #abstract p": _mock_text("Abstract text."),
            ".hlFld-Abstract p": None,
        }.get(sel)

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        ".references li, .citedByEntry, #references-section li": [],
    }.get(sel, [])

    browser.evaluate.return_value = [
        {
            "heading": "Introduction",
            "content": [
                {"type": "paragraph", "text": "ML is important for climate."},
            ],
        },
        {
            "heading": "Results",
            "content": [
                {"type": "figure", "figureId": "https://tandfonline.com/cms/asset/fig1.png"},
                {"type": "paragraph", "text": "Table 1\nA | B\n1 | 2"},
            ],
        },
    ]

    sections = await publisher.extract_sections(browser)
    headings = [s.heading for s in sections]
    assert "Abstract" in headings
    assert "Introduction" in headings
    assert "Results" in headings

    results_sec = next(s for s in sections if s.heading == "Results")
    fig_blocks = [b for b in results_sec.content if b.type == "figure"]
    assert len(fig_blocks) == 1
    assert fig_blocks[0].figure_id == "https://tandfonline.com/cms/asset/fig1.png"


@pytest.mark.asyncio
async def test_extract_sections_references(publisher):
    browser = AsyncMock()

    async def qs(sel):
        return None

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        ".references li, .citedByEntry, #references-section li": [
            _mock_text("Smith 2020"),
            _mock_text("Jones 2021"),
        ],
    }.get(sel, [])
    browser.evaluate.return_value = []

    sections = await publisher.extract_sections(browser)
    ref_sec = next((s for s in sections if s.heading == "References"), None)
    assert ref_sec is not None
    assert len(ref_sec.content) == 2
    assert ref_sec.content[0].text.startswith("1.")
