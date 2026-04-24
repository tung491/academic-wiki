# Semantic Scholar MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `semantic_scholar_mcp`, a minimal sibling MCP server that exposes only three Semantic Scholar tools (`semantic_scholar_search`, `get_paper_by_doi`, `discover_related`), fully independent of the existing `academic_wiki_mcp`.

**Architecture:** Standalone package at `/home/tung491/Work/academic_wiki/semantic_scholar_mcp/` with a duplicated copy of the S2 client + identifier logic, registered against its own `FastMCP("SemanticScholarServer")` instance. Installed via a new `s2_mcp` extras group in the existing `pyproject.toml`; launched via a new `semantic-scholar-mcp` console script.

**Tech Stack:** Python 3.10+, `fastmcp>=3.1.1`, `requests>=2.31`, pytest + pytest-asyncio for tests, `uv` for install.

**Spec reference:** `docs/superpowers/specs/2026-04-24-semantic-scholar-mcp-design.md`.

---

## File Structure

Files to create under `/home/tung491/Work/academic_wiki/`:

| Path | Responsibility |
|---|---|
| `semantic_scholar_mcp/__init__.py` | `mcp = FastMCP("SemanticScholarServer")` |
| `semantic_scholar_mcp/config.py` | Read `SEMANTIC_SCHOLAR_API_KEY` env var |
| `semantic_scholar_mcp/identifier.py` | `detect()` — DOI / arXiv / unknown classification |
| `semantic_scholar_mcp/s2_client.py` | HTTP client helpers + `get_paper_by_doi` (plain function) |
| `semantic_scholar_mcp/tools/__init__.py` | Empty package marker |
| `semantic_scholar_mcp/tools/discovery.py` | Three `@mcp.tool()` registrations + private `_search`/`_references`/`_citations`/`_recommendations`/`_resolve_s2_id` helpers |
| `semantic_scholar_mcp/server.py` | `main()` entry point; imports `tools.discovery` to trigger registration |
| `semantic_scholar_mcp/README.md` | Install + Claude Code / Claude Desktop config guide |
| `tests/semantic_scholar_mcp/__init__.py` | Empty |
| `tests/semantic_scholar_mcp/test_identifier.py` | Copied from `tests/mcp/test_identifier.py`, imports rewritten |
| `tests/semantic_scholar_mcp/test_discovery.py` | Copied from `tests/mcp/test_discovery.py`, imports rewritten |
| `tests/semantic_scholar_mcp/test_s2_client.py` | **New**: covers `get_paper_by_doi` |
| `tests/semantic_scholar_mcp/test_server.py` | **New**: smoke test that the three expected tools are registered |

Files to modify:

| Path | Change |
|---|---|
| `pyproject.toml` | Add `s2_mcp` optional-dependencies group, `[project.scripts]` entry, include `semantic_scholar_mcp*` in `setuptools.packages.find` |

---

## Task 1: Bootstrap package skeleton

**Files:**
- Create: `semantic_scholar_mcp/__init__.py`
- Create: `semantic_scholar_mcp/config.py`
- Create: `tests/semantic_scholar_mcp/__init__.py`
- Create: `tests/semantic_scholar_mcp/test_package.py`

- [ ] **Step 1: Write the failing test**

Create `tests/semantic_scholar_mcp/__init__.py` as an empty file (`touch` or equivalent — use Write with empty content).

Create `tests/semantic_scholar_mcp/test_package.py`:

```python
def test_package_exports_fastmcp_instance():
    from semantic_scholar_mcp import mcp

    assert mcp is not None
    assert mcp.name == "SemanticScholarServer"


def test_config_exposes_api_key(monkeypatch):
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "test-key-123")
    import importlib
    from semantic_scholar_mcp import config
    importlib.reload(config)
    assert config.SEMANTIC_SCHOLAR_API_KEY == "test-key-123"


def test_config_defaults_to_empty_string(monkeypatch):
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    import importlib
    from semantic_scholar_mcp import config
    importlib.reload(config)
    assert config.SEMANTIC_SCHOLAR_API_KEY == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/semantic_scholar_mcp/test_package.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'semantic_scholar_mcp'`

- [ ] **Step 3: Create `semantic_scholar_mcp/__init__.py`**

```python
from fastmcp import FastMCP

mcp = FastMCP("SemanticScholarServer")
```

- [ ] **Step 4: Create `semantic_scholar_mcp/config.py`**

```python
import os

SEMANTIC_SCHOLAR_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/semantic_scholar_mcp/test_package.py -v`
Expected: 3 passed.

If the `mcp.name` assertion fails because FastMCP stores the name under a different attribute in the installed version, open a Python REPL, do `from fastmcp import FastMCP; m = FastMCP("X"); print(dir(m))` to find the right attribute, and update the test accordingly.

- [ ] **Step 6: Commit**

```bash
git add semantic_scholar_mcp/__init__.py semantic_scholar_mcp/config.py \
  tests/semantic_scholar_mcp/__init__.py tests/semantic_scholar_mcp/test_package.py
git commit -m "feat(s2-mcp): bootstrap semantic_scholar_mcp package"
```

---

## Task 2: Copy `identifier.py` + its tests

**Files:**
- Create: `semantic_scholar_mcp/identifier.py`
- Create: `tests/semantic_scholar_mcp/test_identifier.py`

- [ ] **Step 1: Write the failing test** — copy the existing test with one import rewrite.

Create `tests/semantic_scholar_mcp/test_identifier.py` as an **exact copy** of `tests/mcp/test_identifier.py` with only this change on line 2:

```python
from semantic_scholar_mcp.identifier import detect
```

(Replaces `from academic_wiki_mcp.identifier import detect`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/semantic_scholar_mcp/test_identifier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'semantic_scholar_mcp.identifier'`

- [ ] **Step 3: Create `semantic_scholar_mcp/identifier.py`**

Copy the full contents of `academic_wiki_mcp/identifier.py` verbatim — no imports from that package, so no rewrite needed. The file is 35 lines:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/semantic_scholar_mcp/test_identifier.py -v`
Expected: 14 parametrized cases, all passed.

- [ ] **Step 5: Commit**

```bash
git add semantic_scholar_mcp/identifier.py tests/semantic_scholar_mcp/test_identifier.py
git commit -m "feat(s2-mcp): add identifier detection (DOI/arXiv/unknown)"
```

---

## Task 3: Copy `s2_client.py` + new tests for `get_paper_by_doi`

**Files:**
- Create: `semantic_scholar_mcp/s2_client.py`
- Create: `tests/semantic_scholar_mcp/test_s2_client.py`

- [ ] **Step 1: Write the failing test**

Create `tests/semantic_scholar_mcp/test_s2_client.py`:

```python
from unittest.mock import patch, MagicMock

from semantic_scholar_mcp.s2_client import get_paper_by_doi


def test_get_paper_by_doi_returns_normalized_paper():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "paperId": "abc",
        "title": "Attention Is All You Need",
        "authors": [{"name": "Vaswani"}, {"name": "Shazeer"}],
        "year": 2017,
        "venue": "NeurIPS",
        "abstract": "We propose the Transformer.",
        "externalIds": {"DOI": "10.48550/arXiv.1706.03762", "ArXiv": "1706.03762"},
        "citationCount": 99999,
        "publicationTypes": ["JournalArticle"],
    }
    with patch("requests.get", return_value=mock_resp):
        result = get_paper_by_doi("10.48550/arXiv.1706.03762")

    assert result is not None
    assert result["paperId"] == "abc"
    assert result["title"] == "Attention Is All You Need"
    assert result["authors"] == ["Vaswani", "Shazeer"]
    assert result["year"] == 2017
    assert result["doi"] == "10.48550/arXiv.1706.03762"
    assert result["arxiv"] == "1706.03762"
    assert result["citationCount"] == 99999
    assert result["publicationTypes"] == ["JournalArticle"]


def test_get_paper_by_doi_returns_none_on_404():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    with patch("requests.get", return_value=mock_resp):
        result = get_paper_by_doi("10.0/nonexistent")
    assert result is None


def test_get_paper_by_doi_returns_none_after_retries_on_503():
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.raise_for_status.return_value = None
    # Patch time.sleep to avoid waiting for 2+4+8+16+32 seconds in the retry loop.
    with patch("requests.get", return_value=mock_resp), \
         patch("semantic_scholar_mcp.s2_client.time.sleep"):
        result = get_paper_by_doi("10.1/x")
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/semantic_scholar_mcp/test_s2_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'semantic_scholar_mcp.s2_client'`

- [ ] **Step 3: Create `semantic_scholar_mcp/s2_client.py`**

Copy `academic_wiki_mcp/s2_client.py` with the import path rewritten:

```python
from __future__ import annotations
import time

import requests

from semantic_scholar_mcp.config import SEMANTIC_SCHOLAR_API_KEY

S2_GRAPH = "https://api.semanticscholar.org/graph/v1"
S2_FIELDS = "paperId,title,authors,year,venue,abstract,externalIds,citationCount,publicationTypes"


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
        "publicationTypes": p.get("publicationTypes") or [],
    }


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

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/semantic_scholar_mcp/test_s2_client.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add semantic_scholar_mcp/s2_client.py tests/semantic_scholar_mcp/test_s2_client.py
git commit -m "feat(s2-mcp): add S2 HTTP client + get_paper_by_doi"
```

---

## Task 4: Create `tools/discovery.py` + copy discovery tests

**Files:**
- Create: `semantic_scholar_mcp/tools/__init__.py`
- Create: `semantic_scholar_mcp/tools/discovery.py`
- Create: `tests/semantic_scholar_mcp/test_discovery.py`

- [ ] **Step 1: Write the failing test** — copy the existing discovery test file and rewrite import paths.

Create `tests/semantic_scholar_mcp/test_discovery.py` as an exact copy of `tests/mcp/test_discovery.py` with the top imports changed:

```python
import pytest
from unittest.mock import patch, MagicMock
from semantic_scholar_mcp.s2_client import _s2_get
from semantic_scholar_mcp.tools.discovery import (
    _search,
    _references,
    _citations,
    _recommendations,
)
```

Everything else in the file (all 6 test functions) is a byte-for-byte copy.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/semantic_scholar_mcp/test_discovery.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'semantic_scholar_mcp.tools'`

- [ ] **Step 3: Create `semantic_scholar_mcp/tools/__init__.py`** (empty)

Write an empty file.

- [ ] **Step 4: Create `semantic_scholar_mcp/tools/discovery.py`**

This is the existing `academic_wiki_mcp/tools/discovery.py` with imports rewritten AND an added `@mcp.tool()`-wrapped `get_paper_by_doi`:

```python
from __future__ import annotations

from semantic_scholar_mcp import mcp
from semantic_scholar_mcp.identifier import detect
from semantic_scholar_mcp.s2_client import (
    S2_FIELDS,
    S2_GRAPH,
    _normalize_s2_paper,
    _s2_get,
    get_paper_by_doi as _get_paper_by_doi,
)

S2_RECS = "https://api.semanticscholar.org/recommendations/v1"


async def _search(query: str, venue: str | None = None, year: str | None = None, limit: int = 10) -> list[dict]:
    params: dict[str, str] = {"query": query, "limit": str(limit), "fields": S2_FIELDS}
    if venue:
        params["venue"] = venue
    if year:
        params["year"] = year
    resp = _s2_get(f"{S2_GRAPH}/paper/search", params=params)
    if not resp or resp.status_code != 200:
        return []
    return [_normalize_s2_paper(p) for p in (resp.json().get("data") or [])]


async def _references(paper_id: str, limit: int = 50) -> list[dict]:
    resp = _s2_get(
        f"{S2_GRAPH}/paper/{paper_id}/references",
        params={"fields": S2_FIELDS, "limit": str(limit)},
    )
    if not resp or resp.status_code != 200:
        return []
    return [
        _normalize_s2_paper(r["citedPaper"])
        for r in (resp.json().get("data") or [])
        if r.get("citedPaper")
    ]


async def _citations(paper_id: str, limit: int = 50) -> list[dict]:
    resp = _s2_get(
        f"{S2_GRAPH}/paper/{paper_id}/citations",
        params={"fields": S2_FIELDS, "limit": str(limit)},
    )
    if not resp or resp.status_code != 200:
        return []
    return [
        _normalize_s2_paper(r["citingPaper"])
        for r in (resp.json().get("data") or [])
        if r.get("citingPaper")
    ]


async def _recommendations(paper_id: str, limit: int = 20) -> list[dict]:
    resp = _s2_get(
        f"{S2_RECS}/papers/forpaper/{paper_id}",
        params={"fields": S2_FIELDS, "limit": str(limit)},
    )
    if not resp or resp.status_code == 404:
        return []
    if resp.status_code != 200:
        return []
    return [_normalize_s2_paper(p) for p in (resp.json().get("recommendedPapers") or [])]


def _resolve_s2_id(identifier: str) -> str:
    id_type, raw = detect(identifier)
    if id_type == "doi":
        return f"DOI:{raw}"
    if id_type == "arxiv":
        return f"ARXIV:{raw}"
    return identifier


@mcp.tool()
async def semantic_scholar_search(
    query: str,
    venue: str | None = None,
    year: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search Semantic Scholar for papers by keyword query.

    year accepts single years ("2020") or ranges ("2020-2023", "2020-").
    """
    return await _search(query, venue=venue, year=year, limit=limit)


@mcp.tool()
async def get_paper_by_doi(doi: str) -> dict | None:
    """Fetch a single paper from Semantic Scholar by DOI. Returns None if not found."""
    return _get_paper_by_doi(doi)


@mcp.tool()
async def discover_related(identifier: str, limit: int = 10) -> dict:
    """Discover related papers via Semantic Scholar citation graph and recommendations.

    identifier: DOI, arXiv ID (with or without prefix), or S2 paper ID.
    """
    s2_id = _resolve_s2_id(identifier)

    refs = await _references(s2_id, limit=50)
    cites = await _citations(s2_id, limit=50)
    recs = await _recommendations(s2_id, limit=20)

    seen: set[str] = set()
    combined: list[dict] = []
    for paper in refs + cites + recs:
        pid = paper["paperId"]
        if pid and pid not in seen:
            seen.add(pid)
            combined.append(paper)

    combined.sort(key=lambda p: p.get("citationCount", 0), reverse=True)
    return {"related": combined[:limit], "total_found": len(combined)}
```

Note on the `get_paper_by_doi` import alias: the plain-function version in `s2_client.py` is imported as `_get_paper_by_doi` so the `@mcp.tool()` decorator can register a new async wrapper under the unadorned name `get_paper_by_doi` without shadowing.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/semantic_scholar_mcp/test_discovery.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add semantic_scholar_mcp/tools/__init__.py semantic_scholar_mcp/tools/discovery.py \
  tests/semantic_scholar_mcp/test_discovery.py
git commit -m "feat(s2-mcp): register search/doi/discover_related tools"
```

---

## Task 5: Create `server.py` + smoke test for tool registration

**Files:**
- Create: `semantic_scholar_mcp/server.py`
- Create: `tests/semantic_scholar_mcp/test_server.py`

- [ ] **Step 1: Write the failing test**

Create `tests/semantic_scholar_mcp/test_server.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_server_imports_register_three_tools():
    # Import the server module for its side effect: registering tools on the
    # FastMCP instance via the @mcp.tool() decorators in tools.discovery.
    import semantic_scholar_mcp.server  # noqa: F401
    from semantic_scholar_mcp import mcp

    tools = await mcp.list_tools()
    names = {t.name for t in tools}

    assert names == {
        "semantic_scholar_search",
        "get_paper_by_doi",
        "discover_related",
    }


def test_server_has_main_entry_point():
    from semantic_scholar_mcp.server import main
    assert callable(main)
```

If the FastMCP version installed here uses a different introspection API (e.g. `mcp.get_tools()` returning a dict, or a `.tools` attribute), check `dir(mcp)` in a REPL and adapt. The underlying claim — "these three tool names are registered" — stays the same.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/semantic_scholar_mcp/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'semantic_scholar_mcp.server'`

- [ ] **Step 3: Create `semantic_scholar_mcp/server.py`**

```python
from semantic_scholar_mcp import mcp
from semantic_scholar_mcp.tools import discovery  # noqa: F401 - registers tools


def main():
    import sys
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/semantic_scholar_mcp/test_server.py -v`
Expected: 2 passed.

- [ ] **Step 5: Run the full new test suite**

Run: `pytest tests/semantic_scholar_mcp/ -v`
Expected: 3 (package) + 14 (identifier) + 3 (s2_client) + 6 (discovery) + 2 (server) = 28 passed.

- [ ] **Step 6: Commit**

```bash
git add semantic_scholar_mcp/server.py tests/semantic_scholar_mcp/test_server.py
git commit -m "feat(s2-mcp): add server entry point + tool-registration smoke test"
```

---

## Task 6: Wire up `pyproject.toml` — extras group, console script, package discovery

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Read current `pyproject.toml`**

Run: `cat pyproject.toml`
Confirm the file has `[project.optional-dependencies]` (with `dev` and `mcp` groups) and `[tool.setuptools.packages.find]` with `include = ["academic_wiki_mcp*"]`. Confirm there is NO existing `[project.scripts]` section.

- [ ] **Step 2: Add the `s2_mcp` extras group**

Under `[project.optional-dependencies]`, add after the existing `mcp = [...]` block:

```toml
s2_mcp = [
    "fastmcp>=3.1.1",
    "requests>=2.31",
]
```

- [ ] **Step 3: Add the console script**

Between `[project.optional-dependencies]` and `[tool.setuptools.packages.find]`, add a new section:

```toml
[project.scripts]
semantic-scholar-mcp = "semantic_scholar_mcp.server:main"
```

- [ ] **Step 4: Include the new package in setuptools discovery**

Change the `[tool.setuptools.packages.find]` block from:

```toml
[tool.setuptools.packages.find]
include = ["academic_wiki_mcp*"]
```

to:

```toml
[tool.setuptools.packages.find]
include = ["academic_wiki_mcp*", "semantic_scholar_mcp*"]
```

- [ ] **Step 5: Reinstall the editable package with the new extra**

Run: `uv pip install -e ".[s2_mcp]"`
Expected: success with `semantic_scholar_mcp` listed in the installed files.

If you already had `.[mcp]` installed, you can do `uv pip install -e ".[mcp,s2_mcp]"` in one shot.

- [ ] **Step 6: Verify console script is on PATH and launches**

Run: `which semantic-scholar-mcp`
Expected: path ending in `.venv/bin/semantic-scholar-mcp` (or equivalent).

Run: `semantic-scholar-mcp --help 2>&1 | head -20`
Expected: FastMCP's stdio transport help text, or if `--help` isn't supported directly, at least no ImportError / ModuleNotFoundError traceback.

(FastMCP may not expose `--help` on the stdio CLI; if it hangs waiting for MCP input, that's actually a pass — `Ctrl-C` out.)

- [ ] **Step 7: Run the full test suite to catch any packaging regressions**

Run: `pytest tests/semantic_scholar_mcp/ tests/mcp/ -v 2>&1 | tail -30`
Expected: existing `tests/mcp/` suite still green; new `tests/semantic_scholar_mcp/` suite green.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml
git commit -m "build(s2-mcp): add s2_mcp extras group and console script entry"
```

---

## Task 7: Write the README

**Files:**
- Create: `semantic_scholar_mcp/README.md`

- [ ] **Step 1: Write `semantic_scholar_mcp/README.md`**

Create the file with this content:

````markdown
# Semantic Scholar MCP

A minimal MCP server that exposes three Semantic Scholar tools:

- `semantic_scholar_search(query, venue?, year?, limit?)` — keyword paper search.
- `get_paper_by_doi(doi)` — single-paper lookup.
- `discover_related(identifier, limit?)` — union of references, citations, and recommendations for a given DOI / arXiv ID / S2 paper ID.

No browser automation, no vault integration — just Semantic Scholar over HTTP.

## Install

From the repository root:

```bash
uv pip install -e ".[s2_mcp]"
# or, with plain pip:
pip install -e ".[s2_mcp]"
```

Verify:

```bash
which semantic-scholar-mcp
```

## Configure for Claude Code

One-liner:

```bash
claude mcp add semantic-scholar -- semantic-scholar-mcp
```

Or add manually to `~/.claude.json` under `mcpServers`:

```json
{
  "mcpServers": {
    "semantic-scholar": {
      "command": "semantic-scholar-mcp",
      "env": {
        "SEMANTIC_SCHOLAR_API_KEY": "your-key-here-optional"
      }
    }
  }
}
```

Restart Claude Code; the three tools appear prefixed as
`mcp__semantic-scholar__semantic_scholar_search` etc.

## Configure for Claude Desktop

Edit `claude_desktop_config.json`:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json`

Same JSON snippet as above under `mcpServers`. Fully-qualify the `command` to the `.venv/bin/semantic-scholar-mcp` absolute path if Claude Desktop cannot find it on `PATH`.

Restart Claude Desktop.

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `SEMANTIC_SCHOLAR_API_KEY` | No | Sent as `x-api-key` header. Without it the server uses S2's anonymous tier (lower rate limits but works). |

## Tools

### `semantic_scholar_search`

```python
semantic_scholar_search(query: str, venue: str | None = None,
                        year: str | None = None, limit: int = 10) -> list[dict]
```

`year` accepts single years (`"2023"`) or ranges (`"2020-2023"`, `"2020-"`).
Returns up to `limit` normalized paper dicts.

### `get_paper_by_doi`

```python
get_paper_by_doi(doi: str) -> dict | None
```

Returns a normalized paper dict, or `None` if S2 has no record of the DOI.

### `discover_related`

```python
discover_related(identifier: str, limit: int = 10) -> dict
```

`identifier` can be a DOI, arXiv ID (with or without `arXiv:` prefix or full URL), or an S2 paper ID. Returns `{"related": [...], "total_found": int}` — the union of references + citations + recommendations, de-duplicated by paper ID, sorted by citation count, truncated to `limit`.

### Normalized paper dict shape

```
{
  "paperId": str,
  "title": str,
  "authors": [str, ...],
  "year": int | None,
  "venue": str,
  "abstract": str,
  "doi": str,
  "arxiv": str,
  "citationCount": int,
  "publicationTypes": [str, ...]
}
```

## Troubleshooting

- **Tool-name collision.** If you also register the sibling `academic_wiki_mcp` with the same Claude client, `semantic_scholar_search` and `discover_related` will appear twice. Keep only one registered, or namespace them by giving the two `mcpServers` entries distinct server keys (Claude will prefix with the server key).
- **No results / 429 errors.** You are hitting S2's anonymous rate limit. Set `SEMANTIC_SCHOLAR_API_KEY` to an API key from https://www.semanticscholar.org/product/api.
````

- [ ] **Step 2: Verify the README renders**

Run: `cat semantic_scholar_mcp/README.md | head -40`
Expected: clean Markdown, no broken fences.

(Optional) Open in an editor that previews Markdown, or `markdownlint` if installed, to double-check.

- [ ] **Step 3: Commit**

```bash
git add semantic_scholar_mcp/README.md
git commit -m "docs(s2-mcp): add install + Claude client config README"
```

---

## Task 8: End-to-end live verification

This task verifies the MCP works when a real Claude client calls it. It's not a unit test — it's the final sanity check. Requires a live network and the `claude` CLI (you are running inside it).

**Files:** None.

- [ ] **Step 1: Confirm the console script launches**

Run: `semantic-scholar-mcp stdio < /dev/null` (then `Ctrl-C` after a second)
Expected: starts without Python tracebacks; exits cleanly on Ctrl-C.

If you see `ModuleNotFoundError` or `ImportError`, the `pip install -e ".[s2_mcp]"` didn't pick up the new package — re-run it and verify `pip show academic-wiki-scripts | grep -i location`.

- [ ] **Step 2: Register with Claude Code**

Run: `claude mcp add semantic-scholar -- semantic-scholar-mcp`
Expected: `Added MCP server 'semantic-scholar' (local scope)` or similar confirmation.

- [ ] **Step 3: Verify the tools are reachable**

In a new Claude Code session, type: `/mcp` and confirm `semantic-scholar` is listed with 3 tools.

Alternatively, ask Claude: "Use the semantic-scholar MCP to search for papers about 'transformer attention', limit 3." A successful response with 3 paper titles from S2 is the end-to-end success criterion.

- [ ] **Step 4: Final commit (if anything was edited during verification)**

If Task 8 surfaced any changes, commit them:

```bash
git add <any-changed-files>
git commit -m "fix(s2-mcp): <what you fixed>"
```

If no changes were needed, skip this step.

---

## Done

The MCP is implemented, tested, installed, documented, and verified end-to-end against a real Claude client.

Summary of what exists at completion:

- A `semantic_scholar_mcp/` package with 7 Python files + a README.
- A `tests/semantic_scholar_mcp/` suite with ~28 passing tests covering identifier detection, S2 client, tool registration, and helper functions.
- Two edits to `pyproject.toml` (extras group, console script, package discovery).
- A working `semantic-scholar-mcp` console command.
- Unchanged: `academic_wiki_mcp/`, its tests, and all other existing code.
