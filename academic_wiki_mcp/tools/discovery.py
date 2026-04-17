from __future__ import annotations
import time
import requests
from academic_wiki_mcp import mcp
from academic_wiki_mcp.config import SEMANTIC_SCHOLAR_API_KEY
from academic_wiki_mcp.identifier import detect

S2_GRAPH = "https://api.semanticscholar.org/graph/v1"
S2_RECS = "https://api.semanticscholar.org/recommendations/v1"
S2_FIELDS = "paperId,title,authors,year,venue,abstract,externalIds,citationCount"


def _headers() -> dict[str, str]:
    h: dict[str, str] = {}
    if SEMANTIC_SCHOLAR_API_KEY:
        h["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY
    return h


def _s2_get(url: str, params: dict | None = None, max_retries: int = 5) -> requests.Response | None:
    for attempt in range(max_retries):
        resp = requests.get(url, params=params, headers=_headers(), timeout=30)
        if resp.status_code == 200:
            return resp
        if resp.status_code == 404:
            return resp
        if resp.status_code in (429, 500, 502, 503):
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
    return None


def _normalize_s2_paper(p: dict) -> dict:
    ext = p.get("externalIds") or {}
    return {
        "paperId": p.get("paperId", ""),
        "title": p.get("title", ""),
        "authors": [a["name"] for a in (p.get("authors") or [])],
        "year": p.get("year"),
        "venue": p.get("venue", ""),
        "abstract": p.get("abstract", ""),
        "doi": ext.get("DOI", ""),
        "arxiv": ext.get("ArXiv", ""),
        "citationCount": p.get("citationCount", 0),
    }


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
    """Search Semantic Scholar for papers by keyword query."""
    return await _search(query, venue=venue, year=year, limit=limit)


@mcp.tool()
async def discover_related(identifier: str, limit: int = 10) -> dict:
    """Discover related papers via Semantic Scholar citation graph and recommendations."""
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
    return {"related": combined[:limit], "total_found": len(combined)}
