"""Tests for the Springer publisher extractor."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from academic_wiki_mcp.publishers.springer import SpringerPublisher


@pytest.fixture
def publisher():
    return SpringerPublisher()


def _mock_text(txt: str) -> AsyncMock:
    el = AsyncMock()
    el.text.return_value = txt
    return el


def _mock_attr(content: str) -> AsyncMock:
    el = AsyncMock()
    el.attribute.return_value = content
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
            "h1.c-article-title, h1.ArticleTitle": _mock_text(
                "BERT: Pre-training of Deep Bidirectional Transformers"
            ),
            "#Abs1-content p": _mock_text("We introduce BERT."),
            'meta[name="citation_doi"]': _mock_meta("10.1007/springer.2019"),
            'meta[name="citation_publication_date"]': _mock_meta("2019-10-11"),
            'meta[name="citation_journal_title"]': _mock_meta("Nature Machine Intelligence"),
        }.get(sel)

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        '[data-test="author-name"]': [
            _mock_text("Jacob Devlin"), _mock_text("Ming-Wei Chang")
        ],
        ".c-article-subject-list__subject": [_mock_text("NLP"), _mock_text("BERT")],
    }.get(sel, [])

    meta = await publisher.extract_metadata(browser)
    assert meta.title == "BERT: Pre-training of Deep Bidirectional Transformers"
    assert meta.authors == ["Jacob Devlin", "Ming-Wei Chang"]
    assert meta.doi == "10.1007/springer.2019"
    assert meta.year == 2019
    assert meta.venue == "Nature Machine Intelligence"
    assert "NLP" in meta.keywords


@pytest.mark.asyncio
async def test_extract_metadata_fallback_authors(publisher):
    """Falls back to citation_author meta tags when data-test attrs absent."""
    browser = AsyncMock()

    async def qs(sel):
        return {
            "h1.c-article-title, h1.ArticleTitle": None,
            'meta[name="citation_title"]': _mock_meta("Fallback Paper"),
            "#Abs1-content p": None,
            'meta[name="citation_doi"]': _mock_meta("10.1/x"),
            'meta[name="citation_publication_date"]': _mock_meta("2022-01-01"),
            'meta[name="citation_journal_title"]': _mock_meta("Springer J"),
        }.get(sel)

    async def qsa(sel):
        return {
            '[data-test="author-name"]': [],
            'meta[name="citation_author"]': [
                _mock_meta("John Doe"), _mock_meta("Jane Smith")
            ],
            ".c-article-subject-list__subject": [],
        }.get(sel, [])

    browser.query_selector = qs
    browser.query_selector_all = qsa

    meta = await publisher.extract_metadata(browser)
    assert meta.title == "Fallback Paper"
    assert meta.authors == ["John Doe", "Jane Smith"]


@pytest.mark.asyncio
async def test_extract_figures_dedup(publisher):
    """Springer figure extraction deduplicates by URL."""
    browser = AsyncMock()
    browser.evaluate.return_value = [
        {"id": "https://media.springer.com/fig1.png",
         "url": "https://media.springer.com/fig1.png",
         "caption": "Fig. 1"},
        {"id": "https://media.springer.com/fig2.png",
         "url": "https://media.springer.com/fig2.png",
         "caption": "Fig. 2"},
    ]

    figures = await publisher.extract_figures(browser)
    assert len(figures) == 2
    assert figures[0].filename == "fig1.png"
    assert figures[1].filename == "fig2.png"
    assert figures[0].caption == "Fig. 1"


@pytest.mark.asyncio
async def test_extract_sections_skips_abs1(publisher):
    """Sections with id Abs1 or Abs1-section are skipped."""
    abs_el = AsyncMock()
    abs_el.attribute.return_value = None  # will be queried for abstract text

    abs_section_el = AsyncMock()

    abstract_p_el = _mock_text("Abstract text here.")
    browser = AsyncMock()

    async def qs(sel):
        return {"#Abs1-content p": abstract_p_el}.get(sel)

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        ".c-article-section": [abs_section_el],
        "#Bib1 .c-article-references__item": [],
    }.get(sel, [])

    # The section's id attribute returns "Abs1" — should be skipped
    abs_section_el.attribute.return_value = "Abs1"
    browser.evaluate.return_value = []

    sections = await publisher.extract_sections(browser)
    headings = [s.heading for s in sections]
    assert "Abstract" in headings
    # The body section was skipped
    assert len(sections) == 1
