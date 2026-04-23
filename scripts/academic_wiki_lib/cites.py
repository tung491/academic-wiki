"""Fuzzy-match references_raw entries against pre-batch paper pages."""
from __future__ import annotations

import os
import re
from difflib import SequenceMatcher
from pathlib import Path

from academic_wiki_lib.frontmatter import read_frontmatter

_THRESHOLD = 0.80
_TOP_K_PER_REF = 5

try:
    from rapidfuzz import fuzz
    def _score(a: str, b: str) -> float:
        # rapidfuzz token_set_ratio returns 0-100; normalize
        return fuzz.token_set_ratio(a, b) / 100.0
except ImportError:
    def _score(a: str, b: str) -> float:
        """Token-set-ratio emulation using difflib.SequenceMatcher."""
        tokens_a = set(a.split())
        tokens_b = set(b.split())
        intersection = tokens_a & tokens_b
        diff_a = tokens_a - tokens_b
        diff_b = tokens_b - tokens_a

        s1 = " ".join(sorted(intersection))
        s2 = " ".join(sorted(intersection | diff_a))
        s3 = " ".join(sorted(intersection | diff_b))

        return max(
            SequenceMatcher(None, s1, s2).ratio(),
            SequenceMatcher(None, s1, s3).ratio(),
            SequenceMatcher(None, s2, s3).ratio(),
        )


def _normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _load_candidate(wiki_root, paper_id: str) -> tuple[str, str, str] | None:
    """Return (title, first_author_surname, year_str) or None if file missing."""
    path = Path(os.fspath(wiki_root)) / "wiki" / "papers" / f"{paper_id}.md"
    if not path.exists():
        return None
    fm, _ = read_frontmatter(path)
    title = fm.get("title") or ""
    authors = fm.get("authors") or []
    first_author = ""
    if authors and isinstance(authors[0], dict):
        first_author = authors[0].get("name") or ""
    elif authors and isinstance(authors[0], str):
        first_author = authors[0]
    year = str(fm.get("year") or "")
    return (title, first_author, year)


def resolve_cites(
    wiki_root,
    references_raw: list[str],
    pre_batch_paper_ids: list[str],
) -> dict[str, list[tuple[str, float]]]:
    """Fuzzy-match each references_raw entry against pre-batch papers.

    Returns dict mapping each reference string to a list of up to 5
    (paper_id, normalized_score) pairs with score >= 0.80, sorted desc.
    """
    candidates: list[tuple[str, str]] = []  # (paper_id, normalized_candidate_string)
    for pid in pre_batch_paper_ids:
        loaded = _load_candidate(wiki_root, pid)
        if loaded is None:
            continue
        title, author, year = loaded
        candidates.append((pid, _normalize(f"{title} {author} {year}")))

    result: dict[str, list[tuple[str, float]]] = {}
    for ref in references_raw:
        norm_ref = _normalize(ref)
        scored = [(pid, _score(norm_ref, cand)) for pid, cand in candidates]
        scored = [(pid, s) for pid, s in scored if s >= _THRESHOLD]
        scored.sort(key=lambda x: x[1], reverse=True)
        result[ref] = scored[:_TOP_K_PER_REF]
    return result
