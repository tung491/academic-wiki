"""Slug generation per spec §3.5."""
from __future__ import annotations

import re
import unicodedata

_STOP_WORDS = frozenset({"a", "an", "the", "on", "of", "for", "with"})
_MAX_LEN = 60

# Minimal Greek-to-Latin transliteration table for academic notation.
# NFKD covers accented Latin (e.g. García→Garcia) but not Greek script.
_GREEK_TO_LATIN: dict[str, str] = {
    "α": "a", "β": "b", "γ": "g", "δ": "d", "ε": "e", "ζ": "z",
    "η": "e", "θ": "th", "ι": "i", "κ": "k", "λ": "l", "μ": "m",
    "ν": "n", "ξ": "x", "ο": "o", "π": "p", "ρ": "r", "σ": "s",
    "ς": "s", "τ": "t", "υ": "u", "φ": "f", "χ": "ch", "ψ": "ps",
    "ω": "o",
}
_GREEK_RE = re.compile("[" + "".join(_GREEK_TO_LATIN) + "]")


def _transliterate(text: str) -> str:
    """Replace Greek letters with their Latin equivalents."""
    return _GREEK_RE.sub(lambda m: _GREEK_TO_LATIN[m.group()], text)


def make_slug(title: str) -> str:
    """Generate a lowercase-kebab-case slug from a title string.

    Implements the rules from spec §3.5:
      1. Unicode NFKD normalize + strip combining marks (ASCII-fold).
      2. Lowercase.
      3. Transliterate Greek letters to Latin equivalents (after lowercasing).
      4. Replace any run of non-alphanumeric (except hyphens) chars with a
         single hyphen.
      5. Collapse consecutive hyphens.
      6. Strip leading/trailing hyphens.
      7. Stop-word filter: drop leading a/an/the/on/of/for/with iff result
         remains multi-word.
      8. Truncate at 60 chars at a word boundary if possible.
      9. Caller handles collision resolution separately.
    """
    if not title or not title.strip():
        raise ValueError("Cannot generate slug from empty or whitespace-only title")

    # 1. ASCII-fold via NFKD + strip combining marks (handles accented Latin)
    decomposed = unicodedata.normalize("NFKD", title)
    folded = "".join(c for c in decomposed if not unicodedata.combining(c))

    # 2. Lowercase (before Greek transliteration so only lowercase table is needed)
    lowered = folded.lower()

    # 3. Transliterate Greek (after lowercasing; uppercase Greek folds to lowercase first)
    transliterated = _transliterate(lowered)

    # 4. Replace any run of non-alphanumeric/non-hyphen chars with a single hyphen (strict rule 3)
    tokenized = re.sub(r"[^a-z0-9\-]+", "-", transliterated)

    # 5. Collapse multiple hyphens
    collapsed = re.sub(r"-+", "-", tokenized)

    # 6. Strip leading/trailing hyphens
    stripped = collapsed.strip("-")

    # 7. Stop-word filter (only drop leading word if it is a multi-char stop word
    #    to avoid misidentifying single-char tokens from punctuation splitting as "a")
    parts = stripped.split("-")
    if len(parts) >= 2 and len(parts[0]) > 1 and parts[0] in _STOP_WORDS:
        candidate = "-".join(parts[1:])
        if "-" in candidate:  # still multi-word after dropping stop word
            stripped = candidate

    # 7. Truncate at 60 chars, preferring a word boundary
    if len(stripped) > _MAX_LEN:
        truncated = stripped[:_MAX_LEN]
        last_hyphen = truncated.rfind("-")
        # Prefer a word boundary if one exists and doesn't leave us with too little
        if last_hyphen >= 10:  # arbitrary minimum — keep at least 10 chars
            truncated = truncated[:last_hyphen]
        stripped = truncated.strip("-")

    if not stripped:
        raise ValueError(f"Slug generation produced empty string from title: {title!r}")

    return stripped
