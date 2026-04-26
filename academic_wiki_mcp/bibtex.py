"""Pure-logic BibTeX parsing, key rewriting, and metadata-to-entry building.

No I/O. No network. Used by tools/bibtex.py.
"""
from __future__ import annotations
import re

_ENTRY_HEAD = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,")
_FIELD_NAME = re.compile(r"(\w+)\s*=\s*", re.IGNORECASE)


def parse_first_entry(bibtex_text: str) -> dict:
    """Parse the first @type{key, ...} entry in `bibtex_text`.

    Returns {'type': str, 'key': str, 'fields': dict[str, str]}.
    Tolerates loose whitespace and nested braces in field values.

    Raises ValueError if no @type{key, pattern is found.
    """
    head = _ENTRY_HEAD.search(bibtex_text)
    if not head:
        raise ValueError("No BibTeX entry found")

    entry_type = head.group(1).lower()
    key = head.group(2)

    pos = head.end()
    fields: dict[str, str] = {}
    n = len(bibtex_text)

    while pos < n:
        # Skip whitespace and field separators
        while pos < n and bibtex_text[pos] in " \t\n\r,":
            pos += 1
        if pos >= n or bibtex_text[pos] == "}":
            break

        m = _FIELD_NAME.match(bibtex_text, pos)
        if not m:
            break
        field_name = m.group(1).lower()
        pos = m.end()
        if pos >= n:
            break

        if bibtex_text[pos] == "{":
            depth = 1
            pos += 1
            value_start = pos
            while pos < n and depth > 0:
                if bibtex_text[pos] == "{":
                    depth += 1
                elif bibtex_text[pos] == "}":
                    depth -= 1
                if depth > 0:
                    pos += 1
            value = bibtex_text[value_start:pos]
            pos += 1  # skip closing brace
        elif bibtex_text[pos] == '"':
            pos += 1
            value_start = pos
            while pos < n and bibtex_text[pos] != '"':
                # Skip past backslash-escaped characters (e.g., \" inside the value)
                if bibtex_text[pos] == "\\" and pos + 1 < n:
                    pos += 1
                pos += 1
            value = bibtex_text[value_start:pos]
            pos += 1  # skip closing quote
        else:
            value_start = pos
            while pos < n and bibtex_text[pos] not in ",}\n":
                pos += 1
            value = bibtex_text[value_start:pos].strip()

        fields[field_name] = value

    return {"type": entry_type, "key": key, "fields": fields}


_KEY_REWRITE = re.compile(r"(@\w+\s*\{\s*)([^,\s]+)(\s*,)")
# A safe BibTeX citation key contains no whitespace, no commas, and no braces.
# (Valid wiki paper-ids are always safe; this guards public callers.)
_VALID_PAPER_ID = re.compile(r"^[^\s,{}]+$")


def rewrite_citation_key(bibtex_text: str, paper_id: str) -> str:
    """Replace the citation key inside the first @type{KEY, ...} with paper_id.

    Preserves whitespace, field order, and escaping of the rest of the entry.
    `paper_id` must contain no whitespace, commas, or braces (would produce
    malformed BibTeX).

    Raises ValueError if `paper_id` is unsafe or no @type{key, pattern is found.
    """
    if not _VALID_PAPER_ID.match(paper_id):
        raise ValueError(
            f"paper_id contains characters that would corrupt BibTeX: {paper_id!r}"
        )
    new_text, n = _KEY_REWRITE.subn(
        lambda m: f"{m.group(1)}{paper_id}{m.group(3)}",
        bibtex_text,
        count=1,
    )
    if n == 0:
        raise ValueError("No @type{key, ...} pattern found in BibTeX text")
    return new_text


_INPROC_PATTERN = re.compile(
    r"Proceedings|Conference|Symposium|Workshop|ICCV|CVPR|NeurIPS|ICML",
    re.IGNORECASE,
)

# S2 publicationTypes → (bibtex_entry_type, venue_field_name_or_None)
_S2_TYPE_MAP: dict[str, tuple[str, str | None]] = {
    "JournalArticle": ("article", "journal"),
    "Conference": ("inproceedings", "booktitle"),
    "Review": ("article", "journal"),
    "Book": ("book", None),
    "BookSection": ("incollection", "booktitle"),
}


def _infer_entry_type(meta: dict) -> tuple[str, str | None]:
    """Infer BibTeX entry type from S2 publicationTypes, falling back to venue regex."""
    for pt in meta.get("publicationTypes") or []:
        if pt in _S2_TYPE_MAP:
            return _S2_TYPE_MAP[pt]

    venue = meta.get("venue") or ""
    if venue and _INPROC_PATTERN.search(venue):
        return "inproceedings", "booktitle"
    if venue:
        return "article", "journal"
    return "misc", None


def build_from_metadata(meta: dict, paper_id: str) -> tuple[str, str]:
    """Construct a BibTeX entry from a normalized S2-shaped metadata dict.

    Entry-type detection (in priority order):
      1. S2 ``publicationTypes`` list — mapped via _S2_TYPE_MAP
         (JournalArticle→article, Conference→inproceedings, Book→book, etc.)
      2. Venue-string heuristic — regex for conference keywords → inproceedings,
         non-empty venue → article, empty → misc

    Always emits: title, author (when authors list is non-empty), year, doi
    (when present). Skips empty fields silently.

    Returns (bibtex_text, entry_type).

    Raises ValueError if title or year are missing.
    """
    title = meta.get("title")
    year = meta.get("year")
    if not title:
        raise ValueError("title is missing")
    if not year:
        raise ValueError("year is missing")

    entry_type, venue_field = _infer_entry_type(meta)
    venue = meta.get("venue") or ""

    authors = meta.get("authors") or []
    doi = meta.get("doi") or ""

    lines = [f"@{entry_type}{{{paper_id},"]
    lines.append(f"  title = {{{title}}},")
    if authors:
        author_str = " and ".join(authors)
        lines.append(f"  author = {{{author_str}}},")
    lines.append(f"  year = {{{year}}},")
    if venue_field and venue:
        lines.append(f"  {venue_field} = {{{venue}}},")
    if doi:
        lines.append(f"  doi = {{{doi}}},")
    lines.append("}")
    return "\n".join(lines), entry_type
