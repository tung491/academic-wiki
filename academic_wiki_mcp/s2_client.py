from __future__ import annotations
import time

import requests

from academic_wiki_mcp.config import SEMANTIC_SCHOLAR_API_KEY

S2_GRAPH = "https://api.semanticscholar.org/graph/v1"
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
