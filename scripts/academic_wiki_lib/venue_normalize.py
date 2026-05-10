"""Venue normalization per spec 2026-05-10.

Strips year (1900-2099) and ordinal prefixes (Nth) from raw venue strings so
different editions of the same conference series collapse to one slug.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from .slug import _transliterate, _strip_leading_stopword_if_remaining_multiword

# 4-digit year, gated by non-digit boundaries so digit-runs like "802.11" are
# left intact. Year window: 1900-2099. Update before 2100.
_YEAR_RE = re.compile(r"(?<![0-9])(?:19|20)\d{2}(?![0-9])")

# Ordinal: any positive integer followed by st/nd/rd/th (case-insensitive).
_ORDINAL_RE = re.compile(r"\b\d+(?:st|nd|rd|th)\b", re.IGNORECASE)

# Paren/bracket characters that get unwrapped to whitespace (their content is
# preserved inline so embedded acronyms like "(AINA 2005)" become "AINA 2005").
_PAREN_RE = re.compile(r"[()\[\]{}]")

# Whitespace runs collapse to a single space. Commas are preserved in the
# canonical name (e.g. "Signals, Systems, and Computers").
_WHITESPACE_RE = re.compile(r"\s+")


def _venue_slug(canonical: str) -> str:
    """Generate a slug for a venue canonical name.

    Like make_slug() from slug.py but WITHOUT the 60-character truncation.
    Venue slugs must remain complete so that same-series editions can be
    reliably grouped (Task 4 near-duplicate detection depends on full slugs).
    """
    if not canonical or not canonical.strip():
        raise ValueError("Cannot generate venue slug from empty string")

    # Apply leading-stop-word filter (same logic as make_slug)
    stripped = _strip_leading_stopword_if_remaining_multiword(canonical)

    # 1. Unicode NFKD normalize + strip combining marks (ASCII-fold)
    decomposed = unicodedata.normalize("NFKD", stripped)
    folded = "".join(c for c in decomposed if not unicodedata.combining(c))

    # 2. Lowercase
    lowered = folded.lower()

    # 3. Transliterate Greek -> Latin
    transliterated = _transliterate(lowered)

    # 4. Replace non-alphanumeric/non-hyphen runs with single hyphen
    tokenized = re.sub(r"[^a-z0-9\-]+", "-", transliterated)

    # 5. Collapse consecutive hyphens and strip leading/trailing
    collapsed = re.sub(r"-+", "-", tokenized).strip("-")

    # NOTE: No truncation — venue slugs are intentionally unbounded so that
    # long-name conferences remain uniquely identifiable.

    if not collapsed:
        raise ValueError(f"Venue slug generation produced empty string from: {canonical!r}")

    return collapsed


def normalize_venue(raw: str) -> tuple[str, str]:
    """Return (canonical_name, slug) for a raw venue string.

    Pipeline:
      1. Unwrap parens/brackets, keeping inner text inline.
      2. Strip ordinals (1st, 2nd, 56th, ...).
      3. Strip 4-digit years (1900-2099), including glued-to-token like VTC2022.
      4. Collapse whitespace runs to a single space (commas are preserved).
      5. Compute canonical_name (trimmed, original casing).
      6. Compute slug via _venue_slug() (no 60-char truncation).

    Raises ValueError when the input is empty/whitespace-only or when nothing
    remains after stripping.
    """
    if raw is None or not raw.strip():
        raise ValueError("Cannot normalize empty venue string")

    # 1. Unwrap parens/brackets
    s = _PAREN_RE.sub(" ", raw)

    # 2. Strip ordinals
    s = _ORDINAL_RE.sub(" ", s)

    # 3. Strip years (anywhere, including glued)
    s = _YEAR_RE.sub("", s)

    # 4. Collapse whitespace runs only (commas preserved in canonical name)
    s = _WHITESPACE_RE.sub(" ", s)

    # Strip stray hyphens that lost a neighbor (e.g. " - " after year removal).
    s = re.sub(r"\s+-\s+", " ", s)
    s = re.sub(r"^\s*-+\s*|\s*-+\s*$", "", s)

    # Strip leading/trailing commas or semicolons left after year/ordinal removal
    s = s.strip(", ;")

    canonical_name = s.strip()
    if not canonical_name:
        raise ValueError(f"Venue normalization produced empty string from: {raw!r}")

    slug = _venue_slug(canonical_name)
    return canonical_name, slug


def near_duplicate_pairs(
    slugs: Iterable[str],
    threshold: float = 0.92,
) -> list[tuple[str, str, float]]:
    """Return pairs (slug_a, slug_b, similarity) with similarity >= threshold.

    Uses difflib.SequenceMatcher on the space-joined token list (split on '-').
    Symmetric: (a, b) appears once with a < b lexicographically.
    Acronym-suffix reinforcement: slugs sharing the same trailing token AND
    similarity >= 0.85 are also flagged.

    Not yet implemented — see Task 4.
    """
    raise NotImplementedError
