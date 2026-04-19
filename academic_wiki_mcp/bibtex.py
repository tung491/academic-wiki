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
