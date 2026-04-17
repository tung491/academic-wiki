import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from academic_wiki_mcp.tools.download import _download_paper_impl
from academic_wiki_mcp.models import Metadata, Section, ContentBlock, Figure


@pytest.mark.asyncio
async def test_download_creates_output_dir(tmp_wiki, sample_metadata):
    publisher = AsyncMock()
    publisher.backend = "playwright"
    publisher.fallback_backend = "selenium"
    publisher.extract_metadata.return_value = sample_metadata
    publisher.extract_sections.return_value = [
        Section(heading="Abstract", content=[
            ContentBlock(type="paragraph", text="Test"),
        ]),
    ]
    publisher.extract_figures.return_value = []

    browser = AsyncMock()
    browser.get_page_content.return_value = "<html>" + "x" * 2000 + "</html>"

    with patch("academic_wiki_mcp.tools.download.WIKI_ROOT", tmp_wiki.parent), \
         patch("academic_wiki_mcp.tools.download.find_publisher", return_value=publisher), \
         patch("academic_wiki_mcp.tools.download.get_backend_for_publisher", return_value=(browser, "playwright")), \
         patch("academic_wiki_mcp.tools.download._resolve_url", return_value="https://arxiv.org/html/1706.03762"):
        result = await _download_paper_impl("1706.03762", str(tmp_wiki))

    assert result["is_new"] is True
    paper_dir = tmp_wiki / "raw" / "papers" / result["paper_id"]
    assert paper_dir.exists()
    assert (paper_dir / f"{result['paper_id']}.md").exists()


@pytest.mark.asyncio
async def test_download_dedup_returns_existing(tmp_wiki, sample_metadata):
    (tmp_wiki / "wiki/papers/vaswani-2017-attention.md").write_text(
        '---\npaper-id: vaswani-2017-attention\nidentifiers:\n  doi: "10.48550/arXiv.1706.03762"\n---\n'
    )

    publisher = AsyncMock()
    publisher.backend = "playwright"
    publisher.fallback_backend = "selenium"
    publisher.extract_metadata.return_value = sample_metadata
    publisher.extract_sections.return_value = []
    publisher.extract_figures.return_value = []

    browser = AsyncMock()
    browser.get_page_content.return_value = "<html>" + "x" * 2000 + "</html>"

    with patch("academic_wiki_mcp.tools.download.WIKI_ROOT", tmp_wiki.parent), \
         patch("academic_wiki_mcp.tools.download.find_publisher", return_value=publisher), \
         patch("academic_wiki_mcp.tools.download.get_backend_for_publisher", return_value=(browser, "playwright")), \
         patch("academic_wiki_mcp.tools.download._resolve_url", return_value="https://arxiv.org/html/1706.03762"):
        result = await _download_paper_impl("10.48550/arXiv.1706.03762", str(tmp_wiki))

    assert result["is_new"] is False
    assert result["paper_id"] == "vaswani-2017-attention"


@pytest.mark.asyncio
async def test_download_invalid_wiki_path(tmp_wiki):
    with patch("academic_wiki_mcp.tools.download.WIKI_ROOT", tmp_wiki.parent):
        result = await _download_paper_impl("1706.03762", "/nonexistent/path")
    assert "error" in result
    assert "Invalid wiki_path" in result["error"]


@pytest.mark.asyncio
async def test_download_unknown_identifier(tmp_wiki):
    with patch("academic_wiki_mcp.tools.download.WIKI_ROOT", tmp_wiki.parent):
        result = await _download_paper_impl("not an identifier at all", str(tmp_wiki))
    assert "error" in result
    assert "Cannot detect" in result["error"]


@pytest.mark.asyncio
async def test_download_unsupported_publisher(tmp_wiki, sample_metadata):
    browser = AsyncMock()
    browser.get_page_content.return_value = "<html>" + "x" * 2000 + "</html>"

    with patch("academic_wiki_mcp.tools.download.WIKI_ROOT", tmp_wiki.parent), \
         patch("academic_wiki_mcp.tools.download.find_publisher", return_value=None), \
         patch("academic_wiki_mcp.tools.download._resolve_url", return_value="https://unknown-publisher.com/paper/123"):
        result = await _download_paper_impl("10.9999/unknown.123", str(tmp_wiki))

    assert "error" in result
    assert "not supported" in result["error"]


@pytest.mark.asyncio
async def test_download_creates_markdown_content(tmp_wiki, sample_metadata):
    publisher = AsyncMock()
    publisher.backend = "playwright"
    publisher.fallback_backend = "selenium"
    publisher.extract_metadata.return_value = sample_metadata
    publisher.extract_sections.return_value = [
        Section(heading="Abstract", content=[
            ContentBlock(type="paragraph", text="We propose the Transformer."),
        ]),
    ]
    publisher.extract_figures.return_value = []

    browser = AsyncMock()
    browser.get_page_content.return_value = "<html>" + "x" * 2000 + "</html>"

    with patch("academic_wiki_mcp.tools.download.WIKI_ROOT", tmp_wiki.parent), \
         patch("academic_wiki_mcp.tools.download.find_publisher", return_value=publisher), \
         patch("academic_wiki_mcp.tools.download.get_backend_for_publisher", return_value=(browser, "playwright")), \
         patch("academic_wiki_mcp.tools.download._resolve_url", return_value="https://arxiv.org/html/1706.03762"):
        result = await _download_paper_impl("1706.03762", str(tmp_wiki))

    paper_dir = tmp_wiki / "raw" / "papers" / result["paper_id"]
    md_content = (paper_dir / f"{result['paper_id']}.md").read_text()
    assert "Attention Is All You Need" in md_content
    assert "## Abstract" in md_content
    assert "We propose the Transformer." in md_content
