"""Tests for the IEEE publisher extractor."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from academic_wiki_mcp.publishers.ieee import IEEEPublisher


@pytest.fixture
def publisher():
    return IEEEPublisher()


def _mock_text(txt: str) -> AsyncMock:
    el = AsyncMock()
    el.text.return_value = txt
    return el


def _mock_meta(content: str) -> AsyncMock:
    el = AsyncMock()
    el.attribute.return_value = content
    return el


@pytest.mark.asyncio
async def test_extract_metadata_title_from_document_title(publisher):
    browser = AsyncMock()

    async def qs(sel):
        return {
            ".document-title": _mock_text("Deep Residual Learning for Image Recognition"),
            '.authors-info .author-name': None,
            ".abstract-text .u-mb-1, .abstract-desktop-div div[xplmathjax]": _mock_text(
                "Deep residual networks."
            ),
            ".stats-document-abstract-doi a, a[href*=\"doi.org\"]": _mock_text(
                "10.1109/CVPR.2016.90"
            ),
            ".doc-abstract-pubdate, "
            ".stats-document-abstract-publishedIn .document-banner-date": _mock_text(
                "Date of Publication: Jan 2016"
            ),
            ".stats-document-abstract-publishedIn a, .document-banner-conference-title": _mock_text(
                "CVPR 2016"
            ),
        }.get(sel)

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        '.authors-info .author-name, .authors-info span[id^="author"]': [
            _mock_text("Kaiming He"), _mock_text("Xiangyu Zhang")
        ],
        ".stats-keywords-section .stats-keywords a": [_mock_text("deep learning")],
    }.get(sel, [])

    meta = await publisher.extract_metadata(browser)
    assert meta.title == "Deep Residual Learning for Image Recognition"
    assert meta.authors == ["Kaiming He", "Xiangyu Zhang"]
    assert meta.doi == "10.1109/CVPR.2016.90"
    assert meta.year == 2016
    assert meta.venue == "CVPR 2016"
    # "Date of Publication:" should be stripped
    assert "Date of Publication:" not in meta.date


@pytest.mark.asyncio
async def test_extract_metadata_date_prefix_stripped(publisher):
    browser = AsyncMock()

    async def qs(sel):
        return {
            ".document-title": _mock_text("Some Paper"),
            ".abstract-text .u-mb-1, .abstract-desktop-div div[xplmathjax]": None,
            ".stats-document-abstract-doi a, a[href*=\"doi.org\"]": None,
            ".doc-abstract-pubdate, "
            ".stats-document-abstract-publishedIn .document-banner-date": _mock_text(
                "Date of Publication: 15 March 2021"
            ),
            ".stats-document-abstract-publishedIn a, .document-banner-conference-title": None,
            'meta[name="citation_doi"]': _mock_meta("10.1/x"),
            'meta[name="citation_publication_date"]': _mock_meta("2021-03-15"),
            'meta[name="citation_journal_title"]': _mock_meta("IEEE Trans."),
        }.get(sel)

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        '.authors-info .author-name, .authors-info span[id^="author"]': [],
        ".stats-keywords-section .stats-keywords a": [],
        'meta[name="citation_author"]': [],
    }.get(sel, [])

    meta = await publisher.extract_metadata(browser)
    assert "Date of Publication:" not in meta.date
    # Date should be normalized to ISO format YYYY-MM-DD
    assert meta.date == "2021-03-15"
    assert meta.year == 2021


@pytest.mark.asyncio
async def test_extract_figures_url_transform(publisher):
    """Figures replace -small with -large in URL."""
    browser = AsyncMock()
    browser.evaluate.return_value = [
        {
            "id": "media123",
            "url": "https://ieeexplore.ieee.org/mediastore/img-small.png",
            "caption": "Fig. 1",
        },
        {
            "id": "media456",
            "url": "https://ieeexplore.ieee.org/mediastore/img-large.png",
            "caption": "",
        },
    ]

    figures = await publisher.extract_figures(browser)
    assert len(figures) == 2
    assert figures[0].filename == "fig1.png"
    assert figures[0].caption == "Fig. 1"
    assert figures[1].filename == "fig2.png"


@pytest.mark.asyncio
async def test_extract_figures_empty(publisher):
    browser = AsyncMock()
    browser.evaluate.return_value = []
    figures = await publisher.extract_figures(browser)
    assert figures == []


@pytest.mark.asyncio
async def test_extract_sections_abstract_first(publisher):
    browser = AsyncMock()
    abstract_el = _mock_text("We present deep residual learning.")

    async def qs(sel):
        if sel == ".abstract-text .u-mb-1, .abstract-desktop-div div[xplmathjax]":
            return abstract_el
        return None

    browser.query_selector = qs
    browser.query_selector_all.side_effect = lambda sel: {
        "div.section, div.section_2, .section--body, "
        ".document-ft-section-container .section": [],
        ".reference-container .reference-item, ol.references li, .refs .reference": [],
    }.get(sel, [])
    browser.evaluate.return_value = []

    sections = await publisher.extract_sections(browser)
    assert sections[0].heading == "Abstract"
    assert sections[0].content[0].text == "We present deep residual learning."
