"""Tests for the ScienceDirect publisher extractor."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from academic_wiki_mcp.publishers.sciencedirect import ScienceDirectPublisher


@pytest.fixture
def publisher():
    return ScienceDirectPublisher()


def _mock_text(txt: str) -> AsyncMock:
    el = AsyncMock()
    el.text.return_value = txt
    return el


def _mock_meta(content: str) -> AsyncMock:
    el = AsyncMock()
    el.attribute.return_value = content
    return el


@pytest.mark.asyncio
async def test_extract_metadata_title_from_span(publisher):
    """Title extracted from h1.title-text span.title-text."""
    browser = AsyncMock()

    async def qs(sel):
        return {
            "h1.title-text span.title-text": _mock_text(
                "Attention mechanisms in neural networks"
            ),
            "[id*='abspara']": _mock_text("We present a study."),
            'meta[name="citation_doi"]': _mock_meta("10.1016/j.neunet.2021"),
            'meta[name="citation_publication_date"]': _mock_meta("2021-05-01"),
            'meta[name="citation_journal_title"]': _mock_meta("Neural Networks"),
        }.get(sel)

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        ".author span.text": [_mock_text("Jane Doe"), _mock_text("John Smith")],
        ".keyword span": [_mock_text("attention"), _mock_text("deep learning")],
    }.get(sel, [])

    meta = await publisher.extract_metadata(browser)
    assert meta.title == "Attention mechanisms in neural networks"
    assert meta.authors == ["Jane Doe", "John Smith"]
    assert meta.doi == "10.1016/j.neunet.2021"
    assert meta.year == 2021
    assert meta.venue == "Neural Networks"
    assert "attention" in meta.keywords


@pytest.mark.asyncio
async def test_extract_metadata_fallback_title_chain(publisher):
    """Falls through h1 → h1.title-text → citation_title."""
    browser = AsyncMock()

    async def qs(sel):
        return {
            "h1.title-text span.title-text": None,
            "h1.title-text": None,
            'meta[name="citation_title"]': _mock_meta("Triple Fallback Paper"),
            "[id*='abspara']": None,
            ".abstract div": None,
            "#abstracts p": None,
            'meta[name="citation_doi"]': _mock_meta("10.1/x"),
            'meta[name="citation_publication_date"]': _mock_meta("2020-01-01"),
            'meta[name="citation_journal_title"]': _mock_meta("Elsevier J"),
        }.get(sel)

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        ".author span.text": [],
        ".keyword span": [],
        'meta[name="citation_author"]': [_mock_meta("Author A")],
    }.get(sel, [])

    meta = await publisher.extract_metadata(browser)
    assert meta.title == "Triple Fallback Paper"


@pytest.mark.asyncio
async def test_extract_figures_skips_clear_gif(publisher):
    """Figures matching clear.gif/1x1/blank are excluded."""
    browser = AsyncMock()
    browser.evaluate.return_value = [
        {
            "id": "https://sciencedirect.com/fig1.png",
            "url": "https://sciencedirect.com/fig1.png",
            "caption": "Figure 1",
        },
    ]

    figures = await publisher.extract_figures(browser)
    assert len(figures) == 1
    assert figures[0].filename == "fig1.png"
    assert figures[0].caption == "Figure 1"


@pytest.mark.asyncio
async def test_extract_figures_empty(publisher):
    browser = AsyncMock()
    browser.evaluate.return_value = []
    figures = await publisher.extract_figures(browser)
    assert figures == []


@pytest.mark.asyncio
async def test_extract_sections_from_evaluate(publisher):
    """Sections are built from TreeWalker evaluate result."""
    browser = AsyncMock()

    # No direct abstract element
    async def qs(sel):
        return None

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        ".reference .contribution, .bib-reference, [name='bibliography'] li": [],
    }.get(sel, [])

    browser.evaluate.return_value = [
        {
            "heading": "Introduction",
            "content": [
                {"type": "paragraph", "text": "This paper presents a method."},
                {"type": "figure", "figureId": "https://sd.com/fig1.png"},
            ],
        },
        {
            "heading": "Methods",
            "content": [
                {"type": "paragraph", "text": "We use a new dataset."},
            ],
        },
    ]

    sections = await publisher.extract_sections(browser)
    assert len(sections) == 2
    assert sections[0].heading == "Introduction"
    assert sections[0].content[0].type == "paragraph"
    assert sections[0].content[1].type == "figure"
    assert sections[0].content[1].figure_id == "https://sd.com/fig1.png"
    assert sections[1].heading == "Methods"
