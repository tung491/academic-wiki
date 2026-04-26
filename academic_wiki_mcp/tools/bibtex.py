"""MCP tool: doi_to_bibtex — DOI → BibTeX entry keyed by paper_id."""
from __future__ import annotations
import logging
import re

import requests

from academic_wiki_mcp import bibtex, mcp, s2_client

log = logging.getLogger(__name__)

# \d+ is intentionally looser than Crossref's \d{4,9} so that test-stub DOIs
# (e.g. "10.1/foo") are accepted. Real DOIs always have at least 4 digits.
_DOI_PAT = re.compile(r"^10\.\d+/")
_DOI_ORG_TIMEOUT = 15


def _try_doi_org(doi: str, paper_id: str) -> dict | None:
    """Try doi.org content negotiation. Return result dict on success, None on
    any failure (so the caller falls back)."""
    try:
        resp = requests.get(
            f"https://doi.org/{doi}",
            headers={
                "Accept": "application/x-bibtex; charset=utf-8",
                "User-Agent": "academic-wiki-mcp/1.0",
            },
            allow_redirects=True,
            timeout=_DOI_ORG_TIMEOUT,
        )
    except requests.RequestException as e:
        log.warning("doi.org request failed for %s: %s", doi, e)
        return None

    if resp.status_code != 200:
        log.warning("doi.org returned %s for %s", resp.status_code, doi)
        return None

    body = (resp.text or "").strip()
    if not body.startswith("@"):
        log.warning("doi.org body for %s does not look like BibTeX", doi)
        return None

    try:
        parsed = bibtex.parse_first_entry(body)
        out = bibtex.rewrite_citation_key(body, paper_id)
    except ValueError as e:
        log.warning("doi.org body for %s could not be parsed: %s", doi, e)
        return None

    return {"bibtex": out, "source": "doi.org", "entry_type": parsed["type"]}


def _try_s2_fallback(doi: str, paper_id: str) -> dict:
    """Fetch metadata via Semantic Scholar and synthesize a BibTeX entry.

    Returns the success dict, or an error dict on S2 miss / incomplete metadata.
    """
    meta = s2_client.get_paper_by_doi(doi)
    if meta is None:
        return {"error": "DOI not found in doi.org or Semantic Scholar", "doi": doi}
    try:
        out, entry_type = bibtex.build_from_metadata(meta, paper_id)
    except ValueError as e:
        return {"error": f"S2 metadata incomplete: {e}", "doi": doi, "partial": meta}
    return {"bibtex": out, "source": "semantic_scholar", "entry_type": entry_type}


@mcp.tool()
async def doi_to_bibtex(doi: str, paper_id: str) -> dict:
    """Fetch BibTeX metadata for a DOI and return an entry keyed by paper_id.

    Tries doi.org content negotiation (Accept: application/x-bibtex). On
    failure, falls back to Semantic Scholar metadata and synthesizes a
    BibTeX entry.

    Returns:
      {"bibtex": "<entry text>",
       "source": "doi.org" | "semantic_scholar",
       "entry_type": "article" | "inproceedings" | "book" | "incollection" | "misc"}
      or {"error": "...", "doi": doi} on total failure.
    """
    if not paper_id:
        return {"error": "paper_id is required", "doi": doi}
    if not doi or not _DOI_PAT.match(doi):
        return {"error": "invalid DOI", "doi": doi}

    try:
        result = _try_doi_org(doi, paper_id)
        if result is not None:
            return result
        return _try_s2_fallback(doi, paper_id)
    except Exception as e:
        log.exception("doi_to_bibtex unexpected error")
        return {"error": f"{type(e).__name__}: {e}", "doi": doi}
