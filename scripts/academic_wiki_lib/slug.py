"""Slug generation per spec §3.5."""
from __future__ import annotations

import re
import unicodedata

_STOP_WORDS = frozenset({"a", "an", "the", "on", "of", "for", "with"})
_MAX_LEN = 60

# Lowercase Greek -> Latin transliteration (applied after .lower())
_GREEK_TO_LATIN = {
    "α": "a", "β": "b", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "e",
    "θ": "th", "ι": "i", "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x",
    "ο": "o", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t", "υ": "u",
    "φ": "f", "χ": "ch", "ψ": "ps", "ω": "o",
}
_GREEK_RE = re.compile("|".join(map(re.escape, _GREEK_TO_LATIN.keys())))

# Match a leading stop-word followed by whitespace (detects "A " at start of title)
# Case-insensitive so "A Theory" and "a theory" both match.
_LEADING_STOPWORD_RE = re.compile(
    r"^\s*(" + "|".join(_STOP_WORDS) + r")\s+",
    flags=re.IGNORECASE,
)


def _transliterate(s: str) -> str:
    return _GREEK_RE.sub(lambda m: _GREEK_TO_LATIN[m.group(0)], s)


def _strip_leading_stopword_if_remaining_multiword(title: str) -> str:
    """Drop a leading stop word from the title IFF what's left is multi-word
    (contains at least one whitespace character between non-whitespace chars).

    Non-whitespace single tokens stay intact: "A/B test" keeps "A/B" because
    "A/B" is the first whitespace-delimited token, not "A".
    """
    m = _LEADING_STOPWORD_RE.match(title)
    if not m:
        return title
    remainder = title[m.end():].strip()
    # Only drop if the remainder is still multi-word
    if re.search(r"\S\s+\S", remainder):
        return remainder
    return title


def make_slug(title: str) -> str:
    """Generate a lowercase-kebab-case slug from a title string.

    Implements the rules from spec §3.5. See the specification for details.
    """
    if not title or not title.strip():
        raise ValueError("Cannot generate slug from empty or whitespace-only title")

    # Rule 6 (stop-word filter) — operate on input before normalization so we
    # distinguish "A Theory of Mind" (drop "A") from "A/B test" (keep, not article)
    stripped_title = _strip_leading_stopword_if_remaining_multiword(title)

    # 1. Unicode NFKD normalize + strip combining marks (ASCII-fold)
    decomposed = unicodedata.normalize("NFKD", stripped_title)
    folded = "".join(c for c in decomposed if not unicodedata.combining(c))

    # 2. Lowercase
    lowered = folded.lower()

    # 3. Transliterate Greek -> Latin (after lowercasing so we only need lowercase map)
    transliterated = _transliterate(lowered)

    # 4. Replace non-alphanumeric/non-hyphen runs with single hyphen (strict rule 3)
    tokenized = re.sub(r"[^a-z0-9\-]+", "-", transliterated)

    # 5. Collapse consecutive hyphens and strip leading/trailing
    collapsed = re.sub(r"-+", "-", tokenized).strip("-")

    # 6. Truncate at 60 chars preferring a word boundary (any hyphen beats mid-word)
    if len(collapsed) > _MAX_LEN:
        truncated = collapsed[:_MAX_LEN]
        last_hyphen = truncated.rfind("-")
        if last_hyphen > 0:
            # Always back up to the last hyphen — spec says "word boundary if possible"
            truncated = truncated[:last_hyphen]
        collapsed = truncated.strip("-")

    if not collapsed:
        raise ValueError(f"Slug generation produced empty string from title: {title!r}")

    return collapsed
