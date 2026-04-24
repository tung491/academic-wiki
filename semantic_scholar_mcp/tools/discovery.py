from __future__ import annotations

import os
import sys
from pathlib import Path

# Make academic_wiki_lib importable when this MCP runs from the parent repo.
# When the standalone is later extracted, this path won't resolve and the
# import inside _stub_papers will fail silently (caught by the try/except).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from semantic_scholar_mcp import mcp
from semantic_scholar_mcp.identifier import detect
from semantic_scholar_mcp.s2_client import (
    S2_FIELDS,
    S2_GRAPH,
    _normalize_s2_paper,
    _s2_get,
    get_paper_by_doi as _get_paper_by_doi,
)

S2_RECS = "https://api.semanticscholar.org/recommendations/v1"


def _stub_papers(papers: list[dict]) -> None:
    """Best-effort: write S2 results to the active wiki's raw/papers/.
    Never raises — hook failures must not break the tool call."""
    try:
        from academic_wiki_lib.s2_stub import write_s2_stubs, resolve_default_wiki
        write_s2_stubs(papers, wiki_root=resolve_default_wiki(os.getcwd()))
    except Exception:
        pass


async def _search(query: str, venue: str | None = None, year: str | None = None, limit: int = 10) -> list[dict]:
    params: dict[str, str] = {"query": query, "limit": str(limit), "fields": S2_FIELDS}
    if venue:
        params["venue"] = venue
    if year:
        params["year"] = year
    resp = _s2_get(f"{S2_GRAPH}/paper/search", params=params)
    if not resp or resp.status_code != 200:
        return []
    return [_normalize_s2_paper(p) for p in (resp.json().get("data") or [])]


async def _references(paper_id: str, limit: int = 50) -> list[dict]:
    resp = _s2_get(
        f"{S2_GRAPH}/paper/{paper_id}/references",
        params={"fields": S2_FIELDS, "limit": str(limit)},
    )
    if not resp or resp.status_code != 200:
        return []
    return [
        _normalize_s2_paper(r["citedPaper"])
        for r in (resp.json().get("data") or [])
        if r.get("citedPaper")
    ]


async def _citations(paper_id: str, limit: int = 50) -> list[dict]:
    resp = _s2_get(
        f"{S2_GRAPH}/paper/{paper_id}/citations",
        params={"fields": S2_FIELDS, "limit": str(limit)},
    )
    if not resp or resp.status_code != 200:
        return []
    return [
        _normalize_s2_paper(r["citingPaper"])
        for r in (resp.json().get("data") or [])
        if r.get("citingPaper")
    ]


async def _recommendations(paper_id: str, limit: int = 20) -> list[dict]:
    resp = _s2_get(
        f"{S2_RECS}/papers/forpaper/{paper_id}",
        params={"fields": S2_FIELDS, "limit": str(limit)},
    )
    if not resp or resp.status_code == 404:
        return []
    if resp.status_code != 200:
        return []
    return [_normalize_s2_paper(p) for p in (resp.json().get("recommendedPapers") or [])]


def _resolve_s2_id(identifier: str) -> str:
    id_type, raw = detect(identifier)
    if id_type == "doi":
        return f"DOI:{raw}"
    if id_type == "arxiv":
        return f"ARXIV:{raw}"
    return identifier


@mcp.tool()
async def semantic_scholar_search(
    query: str,
    venue: str | None = None,
    year: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search Semantic Scholar for papers by keyword query.

    year accepts single years ("2020") or ranges ("2020-2023", "2020-").
    """
    results = await _search(query, venue=venue, year=year, limit=limit)
    _stub_papers(results)
    return results


@mcp.tool()
async def get_paper_by_doi(doi: str) -> dict | None:
    """Fetch a single paper from Semantic Scholar by DOI. Returns None if not found."""
    result = _get_paper_by_doi(doi)
    if result is not None:
        _stub_papers([result])
    return result


@mcp.tool()
async def discover_related(identifier: str, limit: int = 10) -> dict:
    """Discover related papers via Semantic Scholar citation graph and recommendations.

    identifier: DOI, arXiv ID (with or without prefix), or S2 paper ID.
    """
    s2_id = _resolve_s2_id(identifier)

    refs = await _references(s2_id, limit=50)
    cites = await _citations(s2_id, limit=50)
    recs = await _recommendations(s2_id, limit=20)

    seen: set[str] = set()
    combined: list[dict] = []
    for paper in refs + cites + recs:
        pid = paper["paperId"]
        if pid and pid not in seen:
            seen.add(pid)
            combined.append(paper)

    combined.sort(key=lambda p: p.get("citationCount", 0), reverse=True)
    related = combined[:limit]
    _stub_papers(related)
    return {"related": related, "total_found": len(combined)}
