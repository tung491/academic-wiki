"""Write S2 search results as clipper-compatible stubs into a wiki's raw/papers/."""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from academic_wiki_lib.wiki_paths import find_active_wiki, _has_wiki_markers

_SLUG_PREFIX_DOI = "s2-doi-"
_SLUG_PREFIX_ARXIV = "s2-arxiv-"
_SLUG_PREFIX_PID = "s2-pid-"
_DOI_BODY_MAX = 100
_NON_SAFE_CHAR_RE = re.compile(r"[^a-z0-9._-]")
_ARXIV_VERSION_RE = re.compile(r"v\d+$")


def _sanitize_doi(doi: str) -> str:
    s = doi.lower().replace("/", "_")
    s = _NON_SAFE_CHAR_RE.sub("-", s)
    return s[:_DOI_BODY_MAX]


# arXiv IDs are short by nature: new-style "2312.12345" ≈ 10 chars, old-style "cs/0301013" similarly short.
def _normalize_arxiv(arxiv: str) -> str:
    s = arxiv.lower()
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


def resolve_default_wiki(start_cwd: str | None = None) -> str | None:
    """Resolve the active wiki root.

    1. If start_cwd is provided, walk up via find_active_wiki(start_cwd). If found, return it.
    2. Read env var ACADEMIC_WIKI_DEFAULT. If set and the path has wiki markers, return it.
    3. Return None.
    """
    if start_cwd is not None:
        found = find_active_wiki(start_cwd)
        if found is not None:
            return found

    env_path = os.environ.get("ACADEMIC_WIKI_DEFAULT", "").strip()
    if env_path:
        p = Path(env_path).expanduser()
        if p.is_dir() and _has_wiki_markers(p):
            return str(p.resolve())

    return None
