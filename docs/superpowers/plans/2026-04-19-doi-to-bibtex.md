# DOI → BibTeX MCP Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `doi_to_bibtex(doi, paper_id)` MCP tool to `academic_wiki_mcp` that fetches BibTeX via doi.org content negotiation, falling back to Semantic Scholar metadata when content negotiation fails.

**Architecture:** Pure-logic root module `bibtex.py` for parsing/building/key-rewriting; thin MCP wrapper at `tools/bibtex.py`; refactored `s2_client.py` to share Semantic Scholar helpers between `tools/discovery.py` and the new tool.

**Tech Stack:** Python 3.10+, FastMCP, `requests`, `pytest`, `pytest-asyncio` (asyncio mode: auto). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-19-doi-to-bibtex-design.md` (commit `1024964`).

**Precondition:** Working from `/home/tung491/Work/academic_wiki`. The repo is on `master`. Consider creating a worktree/branch first if you don't want to commit directly to `master`. The plan uses `git add` of specific files only — it will NOT touch the unrelated dirty files in the repo (`.claude-plugin/marketplace.json`, `README.md`, etc.).

---

## File Map

| Path | Status | Responsibility |
|---|---|---|
| `academic_wiki_mcp/s2_client.py` | NEW | Shared S2 helpers: `_headers`, `_s2_get`, `_normalize_s2_paper`, `get_paper_by_doi` |
| `academic_wiki_mcp/bibtex.py` | NEW | Pure logic: `parse_first_entry`, `rewrite_citation_key`, `build_from_metadata` |
| `academic_wiki_mcp/tools/bibtex.py` | NEW | MCP wrapper exposing `doi_to_bibtex(doi, paper_id)` |
| `academic_wiki_mcp/tools/discovery.py` | MOD | Replace inline S2 helpers with imports from `s2_client.py` |
| `academic_wiki_mcp/server.py` | MOD | Add `bibtex` to the tools import line so the tool registers at startup |
| `tests/mcp/test_bibtex.py` | NEW | Unit tests for `bibtex.py` + integration tests for `doi_to_bibtex` (all mocked HTTP) |
| `tests/mcp/test_discovery.py` | MOD | Update import path for `_s2_get` (now lives in `s2_client.py`) |

---

## Task 1: Refactor — extract S2 helpers into `s2_client.py`

Pure refactor. Existing behavior unchanged. Existing `tests/mcp/test_discovery.py` is the safety net.

**Files:**
- Create: `academic_wiki_mcp/s2_client.py`
- Modify: `academic_wiki_mcp/tools/discovery.py:1-32` (imports + remove the inline definitions)
- Modify: `tests/mcp/test_discovery.py:3-9` (import `_s2_get` from new location)

- [ ] **Step 1: Create `academic_wiki_mcp/s2_client.py` with the moved helpers**

Write this exact content:
```python
from __future__ import annotations
import time

import requests

from academic_wiki_mcp.config import SEMANTIC_SCHOLAR_API_KEY

S2_GRAPH = "https://api.semanticscholar.org/graph/v1"
S2_FIELDS = "paperId,title,authors,year,venue,abstract,externalIds,citationCount"


def _headers() -> dict[str, str]:
    h: dict[str, str] = {}
    if SEMANTIC_SCHOLAR_API_KEY:
        h["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY
    return h


def _s2_get(url: str, params: dict | None = None, max_retries: int = 5) -> requests.Response | None:
    for attempt in range(max_retries):
        resp = requests.get(url, params=params, headers=_headers(), timeout=30)
        if resp.status_code == 200:
            return resp
        if resp.status_code == 404:
            return resp
        if resp.status_code in (429, 500, 502, 503):
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
    return None


def _normalize_s2_paper(p: dict) -> dict:
    ext = p.get("externalIds") or {}
    return {
        "paperId": p.get("paperId", ""),
        "title": p.get("title", ""),
        "authors": [a["name"] for a in (p.get("authors") or [])],
        "year": p.get("year"),
        "venue": p.get("venue", ""),
        "abstract": p.get("abstract", ""),
        "doi": ext.get("DOI", ""),
        "arxiv": ext.get("ArXiv", ""),
        "citationCount": p.get("citationCount", 0),
    }
```

- [ ] **Step 2: Replace the inline definitions in `tools/discovery.py`**

Open `academic_wiki_mcp/tools/discovery.py`. Replace lines 1-32 (everything from the top through the end of `_normalize_s2_paper`) with:

```python
from __future__ import annotations
import requests  # noqa: F401  # kept for any future direct use; not currently needed

from academic_wiki_mcp import mcp
from academic_wiki_mcp.config import SEMANTIC_SCHOLAR_API_KEY  # noqa: F401  # used elsewhere if added later
from academic_wiki_mcp.identifier import detect
from academic_wiki_mcp.s2_client import (
    S2_FIELDS,
    S2_GRAPH,
    _normalize_s2_paper,
    _s2_get,
)

S2_RECS = "https://api.semanticscholar.org/recommendations/v1"
```

Leave the rest of the file (the `_search`, `_references`, `_citations`, `_recommendations`, `_resolve_s2_id`, and `@mcp.tool()` definitions) untouched.

If `time` is no longer used elsewhere in discovery.py, remove `import time` from the top. (It isn't — it was only used by the moved `_s2_get`.)

- [ ] **Step 3: Update test imports in `tests/mcp/test_discovery.py`**

Change lines 3-9 from:
```python
from academic_wiki_mcp.tools.discovery import (
    _s2_get,
    _search,
    _references,
    _citations,
    _recommendations,
)
```
to:
```python
from academic_wiki_mcp.s2_client import _s2_get
from academic_wiki_mcp.tools.discovery import (
    _search,
    _references,
    _citations,
    _recommendations,
)
```

- [ ] **Step 4: Run existing tests to confirm refactor is behavior-preserving**

Run: `pytest tests/mcp/test_discovery.py -v`
Expected: all existing tests pass (search, recommendations_404, references, citations, s2_get_returns_200_response).

- [ ] **Step 5: Commit the refactor**

```bash
git add academic_wiki_mcp/s2_client.py academic_wiki_mcp/tools/discovery.py tests/mcp/test_discovery.py
git commit -m "$(cat <<'EOF'
refactor: extract Semantic Scholar helpers into s2_client module

Moves _headers, _s2_get, _normalize_s2_paper, S2_GRAPH, S2_FIELDS from
tools/discovery.py into a shared s2_client.py so the upcoming doi_to_bibtex
tool can reuse them without circular imports. No behavior change.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add `get_paper_by_doi` to `s2_client.py`

**Files:**
- Modify: `academic_wiki_mcp/s2_client.py` (append new function)
- Test: `tests/mcp/test_bibtex.py` (new file, just this one test for now)

- [ ] **Step 1: Create `tests/mcp/test_bibtex.py` with a failing test for `get_paper_by_doi`**

```python
from unittest.mock import MagicMock, patch

import pytest

from academic_wiki_mcp.s2_client import get_paper_by_doi


def test_get_paper_by_doi_returns_normalized_paper():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "paperId": "abc",
        "title": "Attention Is All You Need",
        "authors": [{"name": "Ashish Vaswani"}, {"name": "Noam Shazeer"}],
        "year": 2017,
        "venue": "NeurIPS",
        "abstract": "We propose...",
        "externalIds": {"DOI": "10.48550/arXiv.1706.03762"},
        "citationCount": 100000,
    }
    with patch("requests.get", return_value=mock_resp):
        result = get_paper_by_doi("10.48550/arXiv.1706.03762")
    assert result is not None
    assert result["title"] == "Attention Is All You Need"
    assert result["authors"] == ["Ashish Vaswani", "Noam Shazeer"]
    assert result["year"] == 2017
    assert result["venue"] == "NeurIPS"
    assert result["doi"] == "10.48550/arXiv.1706.03762"


def test_get_paper_by_doi_returns_none_on_404():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    with patch("requests.get", return_value=mock_resp):
        result = get_paper_by_doi("10.1/missing")
    assert result is None


def test_get_paper_by_doi_returns_none_when_s2_get_returns_none():
    with patch("academic_wiki_mcp.s2_client._s2_get", return_value=None):
        result = get_paper_by_doi("10.1/ratelimited")
    assert result is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/mcp/test_bibtex.py -v`
Expected: 3 failures with `ImportError: cannot import name 'get_paper_by_doi' from 'academic_wiki_mcp.s2_client'`.

- [ ] **Step 3: Implement `get_paper_by_doi` in `s2_client.py`**

Append to the end of `academic_wiki_mcp/s2_client.py`:

```python


def get_paper_by_doi(doi: str) -> dict | None:
    """Fetch a single paper by DOI from S2 Graph API.

    Returns the normalized paper dict (title, authors, year, venue, doi, ...)
    or None if not found / S2 unreachable.
    """
    resp = _s2_get(f"{S2_GRAPH}/paper/DOI:{doi}", params={"fields": S2_FIELDS})
    if resp is None or resp.status_code != 200:
        return None
    return _normalize_s2_paper(resp.json())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/mcp/test_bibtex.py -v`
Expected: 3 passes.

- [ ] **Step 5: Commit**

```bash
git add academic_wiki_mcp/s2_client.py tests/mcp/test_bibtex.py
git commit -m "$(cat <<'EOF'
feat(s2_client): add get_paper_by_doi for single-paper DOI lookup

Used by the upcoming doi_to_bibtex tool as fallback when doi.org content
negotiation fails. Returns the normalized S2 paper dict or None.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Implement `bibtex.parse_first_entry`

**Files:**
- Create: `academic_wiki_mcp/bibtex.py`
- Test: `tests/mcp/test_bibtex.py` (append)

- [ ] **Step 1: Append failing tests for `parse_first_entry` to `tests/mcp/test_bibtex.py`**

Append to the end of the file:
```python


# ---------------------------------------------------------------------------
# bibtex.parse_first_entry
# ---------------------------------------------------------------------------

from academic_wiki_mcp.bibtex import parse_first_entry


def test_parse_first_entry_basic():
    text = "@article{Smith_2020, title = {Foo}, year = {2020}}"
    parsed = parse_first_entry(text)
    assert parsed["type"] == "article"
    assert parsed["key"] == "Smith_2020"
    assert parsed["fields"]["title"] == "Foo"
    assert parsed["fields"]["year"] == "2020"


def test_parse_first_entry_handles_inproceedings_with_braces():
    text = """@inproceedings{vaswani2017attention,
      title = {Attention Is All You Need},
      author = {Vaswani, Ashish and Shazeer, Noam},
      booktitle = {Advances in {Neural} Information Processing Systems},
      year = {2017},
    }"""
    parsed = parse_first_entry(text)
    assert parsed["type"] == "inproceedings"
    assert parsed["key"] == "vaswani2017attention"
    assert parsed["fields"]["title"] == "Attention Is All You Need"
    assert parsed["fields"]["booktitle"] == "Advances in {Neural} Information Processing Systems"
    assert parsed["fields"]["year"] == "2017"


def test_parse_first_entry_no_entry_raises():
    with pytest.raises(ValueError):
        parse_first_entry("not a bibtex file at all")
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/mcp/test_bibtex.py -k parse_first_entry -v`
Expected: 3 failures with `ModuleNotFoundError: No module named 'academic_wiki_mcp.bibtex'`.

- [ ] **Step 3: Create `academic_wiki_mcp/bibtex.py` with `parse_first_entry`**

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/mcp/test_bibtex.py -k parse_first_entry -v`
Expected: 3 passes.

- [ ] **Step 5: Commit**

```bash
git add academic_wiki_mcp/bibtex.py tests/mcp/test_bibtex.py
git commit -m "$(cat <<'EOF'
feat(bibtex): add parse_first_entry for BibTeX entry parsing

Tolerates loose whitespace and nested braces. Returns {type, key, fields}.
Raises ValueError when no @type{key, pattern is found.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Implement `bibtex.rewrite_citation_key`

**Files:**
- Modify: `academic_wiki_mcp/bibtex.py` (append)
- Test: `tests/mcp/test_bibtex.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `tests/mcp/test_bibtex.py`:
```python


# ---------------------------------------------------------------------------
# bibtex.rewrite_citation_key
# ---------------------------------------------------------------------------

from academic_wiki_mcp.bibtex import rewrite_citation_key


def test_rewrite_citation_key_replaces_first_match():
    text = "@article{Smith_2020, title = {Foo}, year = {2020}}"
    result = rewrite_citation_key(text, "vaswani2017attention")
    assert result == "@article{vaswani2017attention, title = {Foo}, year = {2020}}"


def test_rewrite_citation_key_preserves_other_at_signs():
    text = "@article{x, note = {foo@bar.com}}"
    result = rewrite_citation_key(text, "newkey")
    # First @ rewritten, embedded @bar.com untouched
    assert result == "@article{newkey, note = {foo@bar.com}}"


def test_rewrite_citation_key_no_match_raises():
    with pytest.raises(ValueError):
        rewrite_citation_key("no entry here", "newkey")
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/mcp/test_bibtex.py -k rewrite_citation_key -v`
Expected: 3 failures with `ImportError: cannot import name 'rewrite_citation_key'`.

- [ ] **Step 3: Append `rewrite_citation_key` to `academic_wiki_mcp/bibtex.py`**

Append after `parse_first_entry`:
```python


_KEY_REWRITE = re.compile(r"(@\w+\s*\{\s*)([^,\s]+)(\s*,)")


def rewrite_citation_key(bibtex_text: str, paper_id: str) -> str:
    """Replace the citation key inside the first @type{KEY, ...} with paper_id.

    Preserves whitespace, field order, and escaping of the rest of the entry.
    Raises ValueError if no @type{key, pattern is found.
    """
    new_text, n = _KEY_REWRITE.subn(
        lambda m: f"{m.group(1)}{paper_id}{m.group(3)}",
        bibtex_text,
        count=1,
    )
    if n == 0:
        raise ValueError("No @type{key, ...} pattern found in BibTeX text")
    return new_text
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/mcp/test_bibtex.py -k rewrite_citation_key -v`
Expected: 3 passes.

- [ ] **Step 5: Commit**

```bash
git add academic_wiki_mcp/bibtex.py tests/mcp/test_bibtex.py
git commit -m "$(cat <<'EOF'
feat(bibtex): add rewrite_citation_key for stamping paper-id onto entries

Replaces the citation key in the first @type{KEY, ...} pattern, preserving
the rest of the body byte-identical. Raises ValueError when no match found.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Implement `bibtex.build_from_metadata`

**Files:**
- Modify: `academic_wiki_mcp/bibtex.py` (append)
- Test: `tests/mcp/test_bibtex.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `tests/mcp/test_bibtex.py`:
```python


# ---------------------------------------------------------------------------
# bibtex.build_from_metadata
# ---------------------------------------------------------------------------

from academic_wiki_mcp.bibtex import build_from_metadata


def _meta(**overrides):
    base = {
        "title": "Sample Title",
        "authors": ["Ada Lovelace", "Charles Babbage"],
        "year": 1843,
        "venue": "Sample Journal",
        "doi": "10.1/sample",
    }
    base.update(overrides)
    return base


def test_build_from_metadata_inproceedings():
    meta = _meta(venue="Proceedings of NeurIPS")
    text, entry_type = build_from_metadata(meta, "lovelace1843sample")
    assert entry_type == "inproceedings"
    assert text.startswith("@inproceedings{lovelace1843sample,")
    assert "booktitle = {Proceedings of NeurIPS}" in text
    assert "journal" not in text
    assert "title = {Sample Title}" in text
    assert "author = {Ada Lovelace and Charles Babbage}" in text
    assert "year = {1843}" in text
    assert "doi = {10.1/sample}" in text


def test_build_from_metadata_article():
    meta = _meta(venue="Nature")
    text, entry_type = build_from_metadata(meta, "key1")
    assert entry_type == "article"
    assert text.startswith("@article{key1,")
    assert "journal = {Nature}" in text
    assert "booktitle" not in text


def test_build_from_metadata_misc_no_venue():
    meta = _meta(venue="")
    text, entry_type = build_from_metadata(meta, "key1")
    assert entry_type == "misc"
    assert text.startswith("@misc{key1,")
    assert "journal" not in text
    assert "booktitle" not in text


def test_build_from_metadata_authors_joined_with_and():
    meta = _meta(authors=["A B", "C D", "E F"])
    text, _ = build_from_metadata(meta, "key1")
    assert "author = {A B and C D and E F}" in text


def test_build_from_metadata_omits_empty_doi():
    meta = _meta(doi="")
    text, _ = build_from_metadata(meta, "key1")
    assert "doi" not in text


def test_build_from_metadata_omits_empty_authors():
    meta = _meta(authors=[])
    text, _ = build_from_metadata(meta, "key1")
    assert "author" not in text


def test_build_from_metadata_raises_when_title_missing():
    meta = _meta(title="")
    with pytest.raises(ValueError):
        build_from_metadata(meta, "key1")


def test_build_from_metadata_raises_when_year_missing():
    meta = _meta(year=None)
    with pytest.raises(ValueError):
        build_from_metadata(meta, "key1")


def test_build_from_metadata_inproceedings_pattern_case_insensitive():
    meta = _meta(venue="cvpr 2024 workshop")
    _, entry_type = build_from_metadata(meta, "key1")
    assert entry_type == "inproceedings"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/mcp/test_bibtex.py -k build_from_metadata -v`
Expected: 9 failures with `ImportError: cannot import name 'build_from_metadata'`.

- [ ] **Step 3: Append `build_from_metadata` to `academic_wiki_mcp/bibtex.py`**

Append:
```python


_INPROC_PATTERN = re.compile(
    r"Proceedings|Conference|Symposium|Workshop|ICCV|CVPR|NeurIPS|ICML",
    re.IGNORECASE,
)


def build_from_metadata(meta: dict, paper_id: str) -> tuple[str, str]:
    """Construct a BibTeX entry from a normalized S2-shaped metadata dict.

    Entry-type heuristic (case-insensitive on `meta['venue']`):
      - matches Proceedings|Conference|Symposium|Workshop|ICCV|CVPR|NeurIPS|ICML
        → @inproceedings, field name `booktitle`
      - non-empty venue → @article, field name `journal`
      - empty venue → @misc, no booktitle/journal

    Always emits: title, author (when authors list is non-empty), year, doi
    (when present). Skips empty fields silently.

    Returns (bibtex_text, entry_type) — entry_type is one of
    "article" | "inproceedings" | "misc".

    Raises ValueError if title or year are missing.
    """
    title = meta.get("title")
    year = meta.get("year")
    if not title:
        raise ValueError("title is missing")
    if not year:
        raise ValueError("year is missing")

    venue = meta.get("venue") or ""
    if venue and _INPROC_PATTERN.search(venue):
        entry_type = "inproceedings"
        venue_field = "booktitle"
    elif venue:
        entry_type = "article"
        venue_field = "journal"
    else:
        entry_type = "misc"
        venue_field = None

    authors = meta.get("authors") or []
    doi = meta.get("doi") or ""

    lines = [f"@{entry_type}{{{paper_id},"]
    lines.append(f"  title = {{{title}}},")
    if authors:
        author_str = " and ".join(authors)
        lines.append(f"  author = {{{author_str}}},")
    lines.append(f"  year = {{{year}}},")
    if venue_field:
        lines.append(f"  {venue_field} = {{{venue}}},")
    if doi:
        lines.append(f"  doi = {{{doi}}},")
    lines.append("}")
    return "\n".join(lines), entry_type
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/mcp/test_bibtex.py -k build_from_metadata -v`
Expected: 9 passes.

- [ ] **Step 5: Commit**

```bash
git add academic_wiki_mcp/bibtex.py tests/mcp/test_bibtex.py
git commit -m "$(cat <<'EOF'
feat(bibtex): add build_from_metadata for synthesizing entries from S2 dicts

Picks @inproceedings vs @article vs @misc by a case-insensitive venue regex.
Joins authors with ' and '. Skips empty fields silently. Raises ValueError
when title or year are missing so the caller can return a clean error.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Implement `doi_to_bibtex` MCP tool — input validation + happy path

**Files:**
- Create: `academic_wiki_mcp/tools/bibtex.py`
- Test: `tests/mcp/test_bibtex.py` (append)

- [ ] **Step 1: Append failing tests for input validation + doi.org happy path**

Append to `tests/mcp/test_bibtex.py`:
```python


# ---------------------------------------------------------------------------
# tools/bibtex.doi_to_bibtex — input validation + happy path
# ---------------------------------------------------------------------------

from academic_wiki_mcp.tools.bibtex import doi_to_bibtex


async def test_doi_to_bibtex_invalid_doi_returns_error_without_network():
    with patch("requests.get") as mock_get:
        result = await doi_to_bibtex("not-a-doi", "key1")
    assert "error" in result
    assert "invalid DOI" in result["error"]
    mock_get.assert_not_called()


async def test_doi_to_bibtex_empty_paper_id_returns_error():
    with patch("requests.get") as mock_get:
        result = await doi_to_bibtex("10.1/foo", "")
    assert "error" in result
    assert "paper_id is required" in result["error"]
    mock_get.assert_not_called()


async def test_doi_to_bibtex_doi_org_happy_path():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "@article{Smith_2020, title = {Foo}, year = {2020}}"
    mock_resp.headers = {"Content-Type": "application/x-bibtex"}
    with patch("requests.get", return_value=mock_resp):
        result = await doi_to_bibtex("10.1/foo", "lovelace1843sample")
    assert "error" not in result
    assert result["source"] == "doi.org"
    assert result["entry_type"] == "article"
    assert result["bibtex"].startswith("@article{lovelace1843sample,")
    assert "Smith_2020" not in result["bibtex"]
```

(Note: `pytest-asyncio` is in `auto` mode per `pyproject.toml`, so `async def test_...` is detected automatically — no `@pytest.mark.asyncio` decorator needed.)

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/mcp/test_bibtex.py -k doi_to_bibtex -v`
Expected: 3 failures with `ModuleNotFoundError: No module named 'academic_wiki_mcp.tools.bibtex'`.

- [ ] **Step 3: Create `academic_wiki_mcp/tools/bibtex.py` with the minimal happy-path implementation**

```python
"""MCP tool: doi_to_bibtex — DOI → BibTeX entry keyed by paper_id."""
from __future__ import annotations
import logging
import re

import requests

from academic_wiki_mcp import bibtex, mcp, s2_client

log = logging.getLogger(__name__)

_DOI_PAT = re.compile(r"^10\.\d{4,9}/")
_DOI_ORG_TIMEOUT = 15


def _try_doi_org(doi: str, paper_id: str) -> dict | None:
    """Try doi.org content negotiation. Return result dict on success, None on
    any failure (so the caller falls back)."""
    try:
        resp = requests.get(
            f"https://doi.org/{doi}",
            headers={
                "Accept": "application/x-bibtex; charset=utf-8",
                "User-Agent": "academic-wiki-mcp/1.0",
            },
            allow_redirects=True,
            timeout=_DOI_ORG_TIMEOUT,
        )
    except requests.RequestException as e:
        log.warning("doi.org request failed for %s: %s", doi, e)
        return None

    if resp.status_code != 200:
        log.warning("doi.org returned %s for %s", resp.status_code, doi)
        return None

    body = (resp.text or "").strip()
    if not body.startswith("@"):
        log.warning("doi.org body for %s does not look like BibTeX", doi)
        return None

    try:
        parsed = bibtex.parse_first_entry(body)
        out = bibtex.rewrite_citation_key(body, paper_id)
    except ValueError as e:
        log.warning("doi.org body for %s could not be parsed: %s", doi, e)
        return None

    return {"bibtex": out, "source": "doi.org", "entry_type": parsed["type"]}


@mcp.tool()
async def doi_to_bibtex(doi: str, paper_id: str) -> dict:
    """Fetch BibTeX metadata for a DOI and return an entry keyed by paper_id.

    Tries doi.org content negotiation (Accept: application/x-bibtex). On
    failure, falls back to Semantic Scholar metadata and synthesizes a
    BibTeX entry.

    Returns:
      {"bibtex": "<entry text>",
       "source": "doi.org" | "semantic_scholar",
       "entry_type": "article" | "inproceedings" | "misc"}
      or {"error": "...", "doi": doi} on total failure.
    """
    if not paper_id:
        return {"error": "paper_id is required"}
    if not doi or not _DOI_PAT.match(doi):
        return {"error": "invalid DOI", "doi": doi}

    try:
        result = _try_doi_org(doi, paper_id)
        if result is not None:
            return result
        return {"error": "doi.org returned no BibTeX (fallback not implemented yet)", "doi": doi}
    except Exception as e:
        log.exception("doi_to_bibtex unexpected error")
        return {"error": f"{type(e).__name__}: {e}", "doi": doi}
```

(The fallback returns a placeholder error for now; Task 7 wires in the real S2 fallback.)

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/mcp/test_bibtex.py -k doi_to_bibtex -v`
Expected: 3 passes (invalid DOI, empty paper_id, doi.org happy path).

- [ ] **Step 5: Commit**

```bash
git add academic_wiki_mcp/tools/bibtex.py tests/mcp/test_bibtex.py
git commit -m "$(cat <<'EOF'
feat(tools/bibtex): add doi_to_bibtex MCP tool with doi.org happy path

Validates DOI and paper_id, then fetches BibTeX via doi.org content
negotiation and rewrites the citation key to paper_id. Fallback path is
stubbed and will be wired up in the next commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Wire S2 fallback into `doi_to_bibtex`

**Files:**
- Modify: `academic_wiki_mcp/tools/bibtex.py`
- Test: `tests/mcp/test_bibtex.py` (append)

- [ ] **Step 1: Append failing tests for the four fallback triggers**

Append to `tests/mcp/test_bibtex.py`:
```python


# ---------------------------------------------------------------------------
# tools/bibtex.doi_to_bibtex — fallback paths
# ---------------------------------------------------------------------------


def _make_doi_org_resp(status_code: int, text: str = "", content_type: str = ""):
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    r.headers = {"Content-Type": content_type}
    return r


def _make_s2_resp(paper_dict):
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = paper_dict
    return r


def _route(doi_org_resp, s2_resp):
    """Build a side_effect that returns doi_org_resp for doi.org and s2_resp for S2."""
    def fake_get(url, *args, **kwargs):
        if "doi.org" in url:
            if isinstance(doi_org_resp, BaseException):
                raise doi_org_resp
            return doi_org_resp
        if "semanticscholar" in url:
            if isinstance(s2_resp, BaseException):
                raise s2_resp
            return s2_resp
        raise AssertionError(f"unexpected url: {url}")
    return fake_get


_S2_GOOD = {
    "paperId": "abc",
    "title": "Fallback Title",
    "authors": [{"name": "Ada Lovelace"}],
    "year": 1843,
    "venue": "Sample Journal",
    "abstract": "",
    "externalIds": {"DOI": "10.1/foo"},
    "citationCount": 1,
}


async def test_doi_to_bibtex_falls_back_on_404():
    side = _route(_make_doi_org_resp(404), _make_s2_resp(_S2_GOOD))
    with patch("requests.get", side_effect=side):
        result = await doi_to_bibtex("10.1/foo", "key1")
    assert result["source"] == "semantic_scholar"
    assert result["entry_type"] == "article"
    assert "@article{key1," in result["bibtex"]
    assert "title = {Fallback Title}" in result["bibtex"]


async def test_doi_to_bibtex_falls_back_on_non_bibtex_body():
    side = _route(
        _make_doi_org_resp(200, text="<html>not bibtex</html>", content_type="text/html"),
        _make_s2_resp(_S2_GOOD),
    )
    with patch("requests.get", side_effect=side):
        result = await doi_to_bibtex("10.1/foo", "key1")
    assert result["source"] == "semantic_scholar"


async def test_doi_to_bibtex_falls_back_on_timeout():
    import requests as _r
    side = _route(_r.Timeout("doi.org timed out"), _make_s2_resp(_S2_GOOD))
    with patch("requests.get", side_effect=side):
        result = await doi_to_bibtex("10.1/foo", "key1")
    assert result["source"] == "semantic_scholar"


async def test_doi_to_bibtex_falls_back_when_rewrite_key_fails():
    # Body starts with @ but has no @type{key, pattern (malformed)
    side = _route(
        _make_doi_org_resp(200, text="@malformed_no_braces", content_type="application/x-bibtex"),
        _make_s2_resp(_S2_GOOD),
    )
    with patch("requests.get", side_effect=side):
        result = await doi_to_bibtex("10.1/foo", "key1")
    assert result["source"] == "semantic_scholar"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/mcp/test_bibtex.py -k "doi_to_bibtex_falls_back" -v`
Expected: 4 failures — the placeholder error from Task 6 prevents the S2 fallback from running.

- [ ] **Step 3: Replace the stubbed fallback with the real S2 fallback**

In `academic_wiki_mcp/tools/bibtex.py`, replace the body of `doi_to_bibtex` from the `try:` block onward:

Find:
```python
    try:
        result = _try_doi_org(doi, paper_id)
        if result is not None:
            return result
        return {"error": "doi.org returned no BibTeX (fallback not implemented yet)", "doi": doi}
    except Exception as e:
        log.exception("doi_to_bibtex unexpected error")
        return {"error": f"{type(e).__name__}: {e}", "doi": doi}
```

Replace with:
```python
    try:
        result = _try_doi_org(doi, paper_id)
        if result is not None:
            return result
        return _try_s2_fallback(doi, paper_id)
    except Exception as e:
        log.exception("doi_to_bibtex unexpected error")
        return {"error": f"{type(e).__name__}: {e}", "doi": doi}
```

Add the `_try_s2_fallback` helper above the `@mcp.tool()` decorator (between `_try_doi_org` and `doi_to_bibtex`):

```python
def _try_s2_fallback(doi: str, paper_id: str) -> dict:
    """Fetch metadata via Semantic Scholar and synthesize a BibTeX entry.

    Returns the success dict, or an error dict on S2 miss / incomplete metadata.
    """
    meta = s2_client.get_paper_by_doi(doi)
    if meta is None:
        return {"error": "DOI not found in doi.org or Semantic Scholar", "doi": doi}
    try:
        out, entry_type = bibtex.build_from_metadata(meta, paper_id)
    except ValueError as e:
        return {"error": f"S2 metadata incomplete: {e}", "doi": doi, "partial": meta}
    return {"bibtex": out, "source": "semantic_scholar", "entry_type": entry_type}
```

- [ ] **Step 4: Run to verify all `doi_to_bibtex` tests pass**

Run: `pytest tests/mcp/test_bibtex.py -k doi_to_bibtex -v`
Expected: 7 passes (3 from Task 6 + 4 fallback tests).

- [ ] **Step 5: Commit**

```bash
git add academic_wiki_mcp/tools/bibtex.py tests/mcp/test_bibtex.py
git commit -m "$(cat <<'EOF'
feat(tools/bibtex): wire Semantic Scholar fallback into doi_to_bibtex

Falls back to S2 metadata + build_from_metadata when doi.org returns non-2xx,
non-BibTeX body, network exception, or unparseable BibTeX. Each fallback
trigger has its own test.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Cover total-failure and S2-incomplete cases

**Files:**
- Test: `tests/mcp/test_bibtex.py` (append)

(The implementation in Task 7 already handles these — this task adds the test cases that verify it.)

- [ ] **Step 1: Append the remaining tests**

Append to `tests/mcp/test_bibtex.py`:
```python


async def test_doi_to_bibtex_total_failure():
    # doi.org 404, S2 also returns no paper (None from get_paper_by_doi)
    side = _route(_make_doi_org_resp(404), _make_doi_org_resp(404))
    # The S2 path goes through _s2_get → 404 → returns response with status 404
    # → get_paper_by_doi returns None → _try_s2_fallback returns the error dict.
    with patch("requests.get", side_effect=side):
        result = await doi_to_bibtex("10.1/missing", "key1")
    assert "error" in result
    assert "DOI not found" in result["error"]
    assert result["doi"] == "10.1/missing"


async def test_doi_to_bibtex_s2_incomplete_metadata():
    incomplete = dict(_S2_GOOD)
    incomplete["year"] = None  # missing year → build_from_metadata raises
    side = _route(_make_doi_org_resp(404), _make_s2_resp(incomplete))
    with patch("requests.get", side_effect=side):
        result = await doi_to_bibtex("10.1/foo", "key1")
    assert "error" in result
    assert "S2 metadata incomplete" in result["error"]
    assert "partial" in result
    assert result["partial"]["title"] == "Fallback Title"
```

- [ ] **Step 2: Run to verify pass on first run (no implementation change needed)**

Run: `pytest tests/mcp/test_bibtex.py -k "total_failure or incomplete_metadata" -v`
Expected: 2 passes.

- [ ] **Step 3: Run the full test_bibtex.py file to confirm everything still passes together**

Run: `pytest tests/mcp/test_bibtex.py -v`
Expected: all tests pass (3 s2_client + 3 parse + 3 rewrite + 9 build + 7 doi_to_bibtex + 2 from this task = 27 tests).

- [ ] **Step 4: Commit**

```bash
git add tests/mcp/test_bibtex.py
git commit -m "$(cat <<'EOF'
test(bibtex): cover total-failure and S2 incomplete-metadata cases

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Register the tool in `server.py` and run the whole suite

**Files:**
- Modify: `academic_wiki_mcp/server.py:2`
- Smoke test via `python -c "import academic_wiki_mcp.server"`

- [ ] **Step 1: Add the new tools module to the server import line**

Open `academic_wiki_mcp/server.py`. Change line 2 from:
```python
from academic_wiki_mcp.tools import download, discovery  # noqa: F401
```
to:
```python
from academic_wiki_mcp.tools import bibtex, discovery, download  # noqa: F401
```

(Alphabetical order is the existing convention nowhere written, but follows Python style.)

- [ ] **Step 2: Smoke test — verify the server module imports cleanly**

Run: `python -c "import academic_wiki_mcp.server; print('OK')"`
Expected: prints `OK`. No `ModuleNotFoundError` or `ImportError`.

- [ ] **Step 3: Run the full MCP test suite to confirm no regression**

Run: `pytest tests/mcp/ -v`
Expected: all tests pass (existing + new). The discovery tests should still pass against the refactored `s2_client` from Task 1.

- [ ] **Step 4: Run the entire repo test suite to catch any unrelated breakage**

Run: `pytest -v`
Expected: no failures introduced by this branch. (Pre-existing failures unrelated to this work are acceptable; note them in the commit if any are unexpected.)

- [ ] **Step 5: Commit**

```bash
git add academic_wiki_mcp/server.py
git commit -m "$(cat <<'EOF'
feat(server): register doi_to_bibtex tool at startup

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage check:** Each spec section maps to tasks below.
- §3 Underlying mechanism (doi.org content neg + S2 fallback) → Tasks 6, 7
- §4 Architecture & file layout → Tasks 1 (refactor), 3 (bibtex.py), 6 (tools/bibtex.py), 9 (server.py)
- §5.1 `s2_client.py` (`_headers`, `_s2_get`, `_normalize_s2_paper`, `get_paper_by_doi`) → Tasks 1, 2
- §5.2 `bibtex.py` (`parse_first_entry`, `rewrite_citation_key`, `build_from_metadata`) → Tasks 3, 4, 5
- §5.3 `tools/bibtex.py` (`doi_to_bibtex`) → Tasks 6, 7
- §5.4 `tools/discovery.py` modification → Task 1
- §5.5 `server.py` modification → Task 9
- §6 Data flow (happy + fallback) → Tasks 6, 7
- §6.3 All four fallback triggers (non-2xx, non-bibtex body, network exception, unparseable bibtex) → Task 7
- §7 Error handling matrix (invalid DOI, empty paper_id, total failure, S2 incomplete, unexpected exception) → Tasks 6, 8 (the catch-all `except Exception` is in Task 6's implementation but no explicit test — acceptable; see note below)
- §8.1 12 pure-logic unit tests → Tasks 3, 4, 5 (parse=3, rewrite=3, build=9 — note: 9 here vs 7 in spec because two `omits_empty_*` tests were split out and one case-insensitivity test added; this is more coverage, not less)
- §8.2 8 mocked integration tests → Tasks 6, 7, 8 (validation=2, happy=1, fallback=4, total_failure=1, incomplete=1 = 9; one extra fallback variant)
- §8.3 Regression test → Task 1, Step 4 (and Task 9, Step 3)

**Note on §7 unexpected-exception case:** the catch-all `except Exception` in `doi_to_bibtex` is implemented in Task 6 but not separately tested. Adding a test would require injecting an exception that bypasses both `_try_doi_org`'s own try/except and `_try_s2_fallback`'s ValueError handling — possible but contrived. Acceptable to leave untested; the existing `RequestException` + `Timeout` + `ValueError` paths exercise the realistic exception surface. If you want a test, add it as a follow-up.

**Placeholder scan:** None — every step has runnable code/commands.

**Type/signature consistency:**
- `parse_first_entry` returns `dict` with keys `type` (str), `key` (str), `fields` (dict) — used as `parsed["type"]` in `_try_doi_org`. ✓
- `rewrite_citation_key` returns `str`, raises `ValueError` — caught in `_try_doi_org`. ✓
- `build_from_metadata` returns `tuple[str, str]` (bibtex, entry_type), raises `ValueError` — unpacked in `_try_s2_fallback`, ValueError caught. ✓
- `get_paper_by_doi` returns `dict | None` — checked for `None` in `_try_s2_fallback`. ✓

**Decomposition note:** Tasks 1 and 9 contain the only file modifications outside the new modules. Tasks 2-8 are additive and don't touch existing code paths, minimizing regression risk for the rest of the project.
