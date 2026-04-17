from __future__ import annotations
import sys
from pathlib import Path

import requests

from academic_wiki_mcp import mcp
from academic_wiki_mcp.browser import (
    get_backend,
    get_backend_for_publisher,
    record_backend_success,
    detect_blocked,
)
from academic_wiki_mcp.config import WIKI_ROOT
from academic_wiki_mcp.identifier import detect
from academic_wiki_mcp.markdown import to_markdown
from academic_wiki_mcp.publishers import find_publisher

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from academic_wiki_lib.paper_id import (
    generate_paper_id,
    find_existing_paper_by_identifiers,
    resolve_collision,
)


def _resolve_url(id_type: str, raw_id: str) -> str:
    if id_type == "arxiv":
        return f"https://arxiv.org/html/{raw_id}"
    if id_type == "doi":
        resp = requests.head(f"https://doi.org/{raw_id}", allow_redirects=True, timeout=15)
        return resp.url
    raise ValueError(f"Cannot resolve identifier: {raw_id}")


async def _download_paper_impl(identifier: str, wiki_path: str) -> dict:
    wp = Path(wiki_path).resolve()
    wiki_root = WIKI_ROOT.resolve()
    if not wp.exists() or not wp.is_relative_to(wiki_root):
        return {"error": f"Invalid wiki_path: {wiki_path}"}

    id_type, raw_id = detect(identifier)
    if id_type == "unknown":
        return {
            "error": (
                f"Cannot detect identifier type for: {identifier}. "
                "Use semantic_scholar_search first."
            )
        }

    url = _resolve_url(id_type, raw_id)
    publisher = find_publisher(url)
    is_arxiv_abs_fallback = False

    if not publisher and id_type == "arxiv":
        url = f"https://arxiv.org/abs/{raw_id}"
        publisher = find_publisher(url)
        is_arxiv_abs_fallback = True

    if not publisher:
        from urllib.parse import urlparse
        domain = urlparse(url).hostname
        return {"error": f"Publisher not supported: {domain}"}

    from urllib.parse import urlparse as _urlparse
    pub_domain = _urlparse(url).hostname or ""
    browser, backend_name = get_backend_for_publisher(
        pub_domain, publisher.backend, publisher.fallback_backend
    )
    try:
        await browser.navigate(url)
        html = await browser.get_page_content()

        if detect_blocked(html):
            await browser.close()
            fallback_name = (
                publisher.fallback_backend
                if backend_name == publisher.backend
                else publisher.backend
            )
            browser = get_backend(fallback_name)
            await browser.navigate(url)
            html = await browser.get_page_content()
            if detect_blocked(html):
                return {"error": f"Both backends blocked for {url}"}
            backend_name = fallback_name

        record_backend_success(pub_domain, backend_name)

        metadata = await publisher.extract_metadata(browser)
        sections = await publisher.extract_sections(browser)
        figures = await publisher.extract_figures(browser)

        # Download figures while browser is still open (for auth cookies)
        for fig in figures:
            if fig.url and not fig.failed:
                try:
                    fig.data = await browser.download_image(fig.url)
                except Exception:
                    fig.failed = True
    finally:
        await browser.close()

    if id_type == "arxiv":
        metadata.arxiv = raw_id
    metadata.url = url

    identifiers: dict[str, str] = {}
    if metadata.doi:
        identifiers["doi"] = metadata.doi
    if metadata.arxiv:
        identifiers["arxiv"] = metadata.arxiv
    if metadata.url:
        identifiers["url"] = metadata.url

    existing = find_existing_paper_by_identifiers(str(wp), identifiers)
    if existing:
        return {
            "paper_id": existing,
            "path": str(wp / "raw" / "papers" / existing),
            "title": metadata.title,
            "authors": metadata.authors,
            "is_new": False,
        }

    last_name = metadata.authors[0].split()[-1] if metadata.authors else "unknown"
    year = metadata.year or 0
    paper_id = generate_paper_id(last_name, year, metadata.title)
    paper_id = resolve_collision(str(wp), paper_id)

    paper_dir = wp / "raw" / "papers" / paper_id
    paper_dir.mkdir(parents=True, exist_ok=True)

    for fig in figures:
        if fig.data and not fig.failed:
            (paper_dir / fig.filename).write_bytes(fig.data)

    md = to_markdown(metadata, sections, figures, paper_id=paper_id)
    (paper_dir / f"{paper_id}.md").write_text(md, encoding="utf-8")

    result: dict = {
        "paper_id": paper_id,
        "path": str(paper_dir),
        "title": metadata.title,
        "authors": metadata.authors,
        "is_new": True,
    }
    if is_arxiv_abs_fallback:
        result["partial"] = True
    return result


@mcp.tool()
async def download_paper(identifier: str, wiki_path: str) -> dict:
    """Download a paper by DOI or arXiv ID, extract content, save to wiki."""
    return await _download_paper_impl(identifier, wiki_path)
