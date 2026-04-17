"""Tests for the arXiv publisher extractor."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from academic_wiki_mcp.publishers.arxiv import ArxivPublisher


@pytest.fixture
def publisher():
    return ArxivPublisher()


def _mock_meta(content: str) -> AsyncMock:
    el = AsyncMock()
    el.attribute.return_value = content
    return el


def _mock_text(txt: str) -> AsyncMock:
    el = AsyncMock()
    el.text.return_value = txt
    return el


@pytest.mark.asyncio
async def test_extract_metadata_title_from_evaluate(publisher):
    browser = AsyncMock()
    browser.query_selector.side_effect = lambda sel: {
        "h1.ltx_title": AsyncMock(),
    }.get(sel)
    browser.query_selector_all.side_effect = lambda sel: {
        ".ltx_authors .ltx_personname": [_mock_text("Alice"), _mock_text("Bob")],
        ".ltx_abstract .ltx_p": [_mock_text("We study transformers.")],
        ".ltx_classification .ltx_text": [_mock_text("cs.LG")],
    }.get(sel, [])
    browser.evaluate.side_effect = lambda js, *args: {
        "() => {\n                    const el = document.querySelector": "Neural Scaling Laws",
    }.get(js[:50], "Neural Scaling Laws")
    # Simplify: mock evaluate to return title string
    browser.evaluate = AsyncMock(return_value="Neural Scaling Laws")

    # Re-mock query_selector_all for meta tags (citation_doi etc.)
    async def qs(sel):
        return {
            "h1.ltx_title": AsyncMock(),
            'meta[name="citation_doi"]': _mock_meta("10.48550/arXiv.2001.08361"),
            'meta[name="citation_date"]': _mock_meta("2020-01-01"),
            'meta[name="citation_journal_title"]': _mock_meta("arXiv"),
        }.get(sel)

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        ".ltx_authors .ltx_personname": [_mock_text("Alice"), _mock_text("Bob")],
        ".ltx_abstract .ltx_p": [_mock_text("We study transformers.")],
        ".ltx_classification .ltx_text": [_mock_text("cs.LG")],
    }.get(sel, [])

    meta = await publisher.extract_metadata(browser)
    assert meta.title == "Neural Scaling Laws"
    assert meta.authors == ["Alice", "Bob"]
    assert meta.doi == "10.48550/arXiv.2001.08361"
    assert meta.year == 2020
    assert meta.venue == "arXiv"
    assert "cs.LG" in meta.keywords


@pytest.mark.asyncio
async def test_extract_metadata_fallback_title(publisher):
    """When h1.ltx_title is absent, falls back to citation_title meta tag."""
    browser = AsyncMock()

    async def qs(sel):
        mapping = {
            "h1.ltx_title": None,
            'meta[name="citation_title"]': _mock_meta("Fallback Title"),
            'meta[name="citation_doi"]': _mock_meta("10.1/xyz"),
            'meta[name="citation_date"]': _mock_meta(""),
            'meta[name="citation_journal_title"]': None,
            'meta[name="citation_publication_date"]': _mock_meta(""),
        }
        return mapping.get(sel)

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {}.get(sel, [])

    meta = await publisher.extract_metadata(browser)
    assert meta.title == "Fallback Title"
    assert meta.venue == "arXiv"  # default


@pytest.mark.asyncio
async def test_extract_metadata_year_parsed(publisher):
    browser = AsyncMock()

    async def qs(sel):
        return {
            "h1.ltx_title": None,
            'meta[name="citation_title"]': _mock_meta("Title"),
            'meta[name="citation_doi"]': _mock_meta(""),
            'meta[name="citation_date"]': _mock_meta("2023/07/15"),
            'meta[name="citation_journal_title"]': _mock_meta("NeurIPS"),
            'meta[name="citation_publication_date"]': _mock_meta(""),
        }.get(sel)

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: [].copy()

    meta = await publisher.extract_metadata(browser)
    assert meta.year == 2023
    assert meta.venue == "NeurIPS"


@pytest.mark.asyncio
async def test_extract_figures_returns_figures(publisher):
    browser = AsyncMock()
    browser.evaluate.return_value = [
        {"url": "https://arxiv.org/html/2001/fig1.png", "caption": "Figure 1: Architecture"},
        {"url": "https://arxiv.org/html/2001/fig2.png", "caption": "Figure 2: Results"},
    ]

    figures = await publisher.extract_figures(browser)
    assert len(figures) == 2
    assert figures[0].filename == "fig1.png"
    assert figures[0].url == "https://arxiv.org/html/2001/fig1.png"
    assert figures[0].caption == "Figure 1: Architecture"
    assert figures[1].filename == "fig2.png"


@pytest.mark.asyncio
async def test_extract_figures_empty(publisher):
    browser = AsyncMock()
    browser.evaluate.return_value = []
    figures = await publisher.extract_figures(browser)
    assert figures == []


@pytest.mark.asyncio
async def test_extract_sections_abstract(publisher):
    browser = AsyncMock()
    browser.query_selector_all.side_effect = lambda sel: {
        ".ltx_abstract .ltx_p": [_mock_text("We propose the Transformer.")],
        ".ltx_section": [],
        ".ltx_bibliography .ltx_bibitem": [],
    }.get(sel, [])
    browser.evaluate.return_value = []

    sections = await publisher.extract_sections(browser)
    assert len(sections) == 1
    assert sections[0].heading == "Abstract"
    assert sections[0].content[0].text == "We propose the Transformer."


@pytest.mark.asyncio
async def test_extract_sections_with_body_and_refs(publisher):
    sec_el = AsyncMock()
    browser = AsyncMock()
    browser.query_selector_all.side_effect = lambda sel: {
        ".ltx_abstract .ltx_p": [_mock_text("Abstract text.")],
        ".ltx_section": [sec_el],
        ".ltx_bibliography .ltx_bibitem": [_mock_text("Vaswani et al. 2017")],
    }.get(sel, [])

    evaluate_results = {
        0: "1. Introduction",  # heading
        1: ["Transformers are important."],  # paras
        2: [],  # fig_imgs
    }
    call_count = 0

    async def fake_evaluate(js, *args):
        nonlocal call_count
        result = evaluate_results.get(call_count, None)
        call_count += 1
        return result

    browser.evaluate = fake_evaluate

    sections = await publisher.extract_sections(browser)
    headings = [s.heading for s in sections]
    assert "Abstract" in headings
    assert "1. Introduction" in headings
    assert "References" in headings
