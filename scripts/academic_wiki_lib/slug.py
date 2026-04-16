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
      2. Transliterate Greek letters to Latin equivalents.
      3. Lowercase.
      4. Drop non-alphanumeric (except hyphens) chars that sit between two
         alphanumeric characters (no separator inserted); replace all remaining
         non-alphanumeric (except hyphens) runs with a single hyphen.
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

    # 2. Transliterate Greek
    transliterated = _transliterate(folded)

    # 3. Lowercase
    lowered = transliterated.lower()

    # 4a. Drop non-alnum/non-hyphen chars sandwiched between alnum chars (no hyphen inserted)
    no_inner_punct = re.sub(r"(?<=[a-z0-9])[^a-z0-9 \-]+(?=[a-z0-9])", "", lowered)

    # 4b. Replace remaining non-alnum/non-hyphen runs with a single hyphen
    tokenized = re.sub(r"[^a-z0-9\-]+", "-", no_inner_punct)

    # 5. Collapse multiple hyphens
    collapsed = re.sub(r"-+", "-", tokenized)

    # 6. Strip leading/trailing hyphens
    stripped = collapsed.strip("-")

    # 7. Stop-word filter
    parts = stripped.split("-")
    if len(parts) >= 2 and parts[0] in _STOP_WORDS:
        candidate = "-".join(parts[1:])
        if "-" in candidate:  # still multi-word after dropping stop word
            stripped = candidate

    # 8. Truncate at 60 chars, preferring a word boundary
    if len(stripped) > _MAX_LEN:
        truncated = stripped[:_MAX_LEN]
        last_hyphen = truncated.rfind("-")
        if last_hyphen > _MAX_LEN // 2:
            truncated = truncated[:last_hyphen]
        stripped = truncated.strip("-")

    if not stripped:
        raise ValueError(f"Slug generation produced empty string from title: {title!r}")

    return stripped
