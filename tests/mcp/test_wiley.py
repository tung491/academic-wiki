"""Tests for the Wiley publisher extractor."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from academic_wiki_mcp.publishers.wiley import WileyPublisher


@pytest.fixture
def publisher():
    return WileyPublisher()


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
            ".citation__title": _mock_text("Protein folding with AI"),
            "#abstract .article-section__content p": _mock_text("We study protein structures."),
            "[class*='abstract'] .article-section__content p": None,
            ".article-section__content p": None,
            'meta[name="citation_doi"]': _mock_meta("10.1002/prot.2022"),
            'meta[name="citation_publication_date"]': _mock_meta("2022-09-01"),
            'meta[name="citation_journal_title"]': _mock_meta("Proteins"),
        }.get(sel)

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        ".loa-authors-trunc .author-name span, .loa-authors .author-name span": [
            _mock_text("David Baker"), _mock_text("John Jumper")
        ],
        ".article-keywords__list a, .kwd-group .kwd": [
            _mock_text("protein folding"), _mock_text("AlphaFold")
        ],
    }.get(sel, [])

    meta = await publisher.extract_metadata(browser)
    assert meta.title == "Protein folding with AI"
    assert meta.authors == ["David Baker", "John Jumper"]
    assert meta.doi == "10.1002/prot.2022"
    assert meta.year == 2022
    assert meta.venue == "Proteins"
    assert "protein folding" in meta.keywords


@pytest.mark.asyncio
async def test_extract_metadata_three_tier_abstract(publisher):
    """Falls through 3-tier abstract selector."""
    browser = AsyncMock()

    async def qs(sel):
        return {
            ".citation__title": _mock_text("Paper X"),
            "#abstract .article-section__content p": None,
            "[class*='abstract'] .article-section__content p": _mock_text(
                "Second tier abstract."
            ),
            'meta[name="citation_doi"]': _mock_meta("10.1/x"),
            'meta[name="citation_publication_date"]': _mock_meta("2023-01-01"),
            'meta[name="citation_journal_title"]': _mock_meta("Wiley J"),
        }.get(sel)

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        ".loa-authors-trunc .author-name span, .loa-authors .author-name span": [],
        ".article-keywords__list a, .kwd-group .kwd": [],
        'meta[name="citation_author"]': [],
    }.get(sel, [])

    meta = await publisher.extract_metadata(browser)
    assert meta.abstract == "Second tier abstract."


@pytest.mark.asyncio
async def test_extract_figures_requires_cms_asset(publisher):
    """Only figures with cms/asset in URL are included."""
    browser = AsyncMock()
    browser.evaluate.return_value = [
        {
            "id": "https://onlinelibrary.wiley.com/cms/asset/fig1.png",
            "url": "https://onlinelibrary.wiley.com/cms/asset/fig1.png",
            "caption": "Figure 1",
        },
    ]

    figures = await publisher.extract_figures(browser)
    assert len(figures) == 1
    assert figures[0].filename == "fig1.png"
    assert "cms/asset" in figures[0].url


@pytest.mark.asyncio
async def test_extract_figures_empty(publisher):
    browser = AsyncMock()
    browser.evaluate.return_value = []
    figures = await publisher.extract_figures(browser)
    assert figures == []


@pytest.mark.asyncio
async def test_extract_sections_body_from_evaluate(publisher):
    """Body sections come from evaluate with seenAbstract logic."""
    browser = AsyncMock()

    async def qs(sel):
        return {
            "#abstract .article-section__content p": _mock_text("Abstract."),
            "[class*='abstract'] .article-section__content p": None,
            ".article-section__content p": None,
        }.get(sel)

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        "#references-section li, .citation__body": [],
    }.get(sel, [])

    browser.evaluate.return_value = [
        {
            "heading": "Introduction",
            "content": [
                {"type": "paragraph", "text": "Proteins are important."},
                {"type": "figure", "figureId": "https://wiley.com/cms/asset/fig1.png"},
            ],
        },
    ]

    sections = await publisher.extract_sections(browser)
    headings = [s.heading for s in sections]
    assert "Abstract" in headings
    assert "Introduction" in headings

    intro = next(s for s in sections if s.heading == "Introduction")
    fig_blocks = [b for b in intro.content if b.type == "figure"]
    assert len(fig_blocks) == 1
