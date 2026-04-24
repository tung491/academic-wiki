"""Write S2 search results as clipper-compatible stubs into a wiki's raw/papers/."""
from __future__ import annotations

import hashlib
import re

_SLUG_PREFIX_DOI = "s2-doi-"
_SLUG_PREFIX_ARXIV = "s2-arxiv-"
_SLUG_PREFIX_PID = "s2-pid-"
_DOI_BODY_MAX = 100
_NON_SAFE_CHAR_RE = re.compile(r"[^a-z0-9._-]")
_ARXIV_VERSION_RE = re.compile(r"v\d+$")


def _sanitize_doi(doi: str) -> str:
    s = doi.strip().lower().replace("/", "_")
    s = _NON_SAFE_CHAR_RE.sub("-", s)
    return s[:_DOI_BODY_MAX]


def _normalize_arxiv(arxiv: str) -> str:
    s = arxiv.strip().lower()
    if s.startswith("arxiv:"):
        s = s[len("arxiv:"):]
    s = _ARXIV_VERSION_RE.sub("", s)
    return s


def _compute_slug(paper: dict) -> str | None:
    """Deterministic per-paper slug. Returns None if paper has no usable identifier.

    Priority: doi > arxiv > paperId. See spec §5.5.
    """
    doi = (paper.get("doi") or "").strip()
    if doi:
        return _SLUG_PREFIX_DOI + _sanitize_doi(doi)

    arxiv = (paper.get("arxiv") or "").strip()
    if arxiv:
        return _SLUG_PREFIX_ARXIV + _normalize_arxiv(arxiv)

    pid = (paper.get("paperId") or "").strip()
    if pid:
        sha8 = hashlib.sha256(pid.encode("utf-8")).hexdigest()[:8]
        return _SLUG_PREFIX_PID + sha8

    return None
