from __future__ import annotations
import re

DOI_PATTERN = re.compile(r"^10\.\d{4,9}/[^\s]+$")
ARXIV_PATTERN = re.compile(r"^(\d{4}\.\d{4,5}(v\d+)?|[a-z][\w-]*/\d{7})$", re.IGNORECASE)
ARXIV_URL_PATTERN = re.compile(r"arxiv\.org/(?:abs|html|pdf)/(.+?)(?:/|$)")
DOI_URL_PATTERN = re.compile(r"doi\.org/(10\.\d{4,9}/[^\s]+)")


def detect(identifier: str) -> tuple[str, str]:
    s = identifier.strip()
    if not s:
        return ("unknown", s)

    for prefix in ("arXiv:", "arxiv:", "doi:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break

    m = ARXIV_URL_PATTERN.search(s)
    if m:
        return ("arxiv", m.group(1))

    m = DOI_URL_PATTERN.search(s)
    if m:
        return ("doi", m.group(1))

    if DOI_PATTERN.match(s):
        return ("doi", s)

    if ARXIV_PATTERN.match(s):
        return ("arxiv", s)

    return ("unknown", identifier.strip())
