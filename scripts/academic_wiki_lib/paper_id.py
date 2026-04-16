"""Paper-id generation and dedup per spec §5.2."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from academic_wiki_lib.frontmatter import read_frontmatter

_STOP_WORDS = frozenset({"a", "an", "the", "on", "of", "for", "with"})

# Letters that don't decompose under NFKD but have standard transliterations
_MANUAL_FOLD = str.maketrans({
    "ø": "o", "Ø": "o",
    "æ": "ae", "Æ": "ae",
    "œ": "oe", "Œ": "oe",
    "ß": "ss",
    "ð": "d", "Ð": "d",
    "þ": "th", "Þ": "th",
    "ł": "l", "Ł": "l",
})


def _ascii_fold(s: str) -> str:
    # Apply manual fold first (for letters without NFKD decomposition)
    pre = s.translate(_MANUAL_FOLD)
    decomposed = unicodedata.normalize("NFKD", pre)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _first_meaningful_word(title: str) -> str:
    """Return the first word of the title, skipping stop words and pure numbers."""
    # Split on any non-alphanumeric run
    words = re.split(r"[^a-zA-Z0-9]+", title.strip())
    for w in words:
        if not w:
            continue
        wl = w.lower()
        if wl in _STOP_WORDS:
            continue
        if wl.isdigit():
            continue
        # Fold and strip non-alphanumeric residue
        folded = _ascii_fold(w)
        cleaned = re.sub(r"[^a-z0-9]", "", folded)
        if cleaned:
            return cleaned
    return "untitled"


def generate_paper_id(lastname: str, year: int, title: str) -> str:
    """Generate a paper-id per spec §5.2: <lastname>-<year>-<firstword>."""
    ln = re.sub(r"[^a-z0-9]", "", _ascii_fold(lastname))
    if not ln:
        ln = "unknown"
    fw = _first_meaningful_word(title)
    return f"{ln}-{year}-{fw}"


def normalize_identifier(kind: str, value: str) -> tuple[str, str | None]:
    """Normalize an identifier value for comparison.

    Returns (normalized_id, version_suffix). The version suffix is separated out
    so two different versions of the same arXiv paper match on the ID.
    """
    v = value.strip()
    if kind == "arxiv":
        m = re.match(r"^(\d{4}\.\d{4,5})(v\d+)?$", v)
        if m:
            return m.group(1), m.group(2)
        return v, None
    if kind == "doi":
        return v.lower(), None
    if kind == "url":
        return v, None
    return v, None


def find_existing_paper_by_identifiers(wiki_root, identifiers: dict[str, str]) -> str | None:
    """Scan wiki/papers/*.md for any paper whose identifiers match the given dict.

    Match semantics:
      - doi: case-insensitive equal
      - arxiv: equal after stripping version suffix
      - url: exact equal
    Returns the matching paper-id, or None.
    """
    papers_dir = Path(wiki_root) / "wiki" / "papers"
    if not papers_dir.is_dir():
        return None

    # Normalize incoming identifiers
    incoming: dict[str, str] = {}
    for k, v in identifiers.items():
        if v:
            norm, _ = normalize_identifier(k, v)
            incoming[k] = norm

    for p in papers_dir.glob("*.md"):
        try:
            fm, _ = read_frontmatter(str(p))
        except Exception:
            # Malformed frontmatter — skip but don't abort dedup
            continue
        existing = fm.get("identifiers") or {}
        if not isinstance(existing, dict):
            continue
        for k, v in incoming.items():
            ev = existing.get(k)
            if not ev:
                continue
            ev_norm, _ = normalize_identifier(k, str(ev))
            if ev_norm == v:
                return fm.get("paper-id") or p.stem
    return None


def resolve_collision(wiki_root, proposed_id: str) -> str:
    """If <proposed_id>.md already exists in wiki/papers/, append -2, -3, ..."""
    papers_dir = Path(wiki_root) / "wiki" / "papers"
    candidate = proposed_id
    suffix = 2
    while (papers_dir / f"{candidate}.md").exists():
        candidate = f"{proposed_id}-{suffix}"
        suffix += 1
    return candidate
