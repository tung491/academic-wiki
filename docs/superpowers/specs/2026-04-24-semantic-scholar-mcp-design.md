---
title: Semantic Scholar MCP — Design Spec
date: 2026-04-24
status: approved (pending spec review)
---

# Semantic Scholar MCP — Design Spec

## Overview

A new MCP server, `semantic_scholar_mcp`, sibling to the existing `academic_wiki_mcp` in the same repository. It exposes only Semantic Scholar-backed tools — keyword search, DOI lookup, and related-paper discovery — and has no dependency on the existing MCP, no browser automation, and no Obsidian vault integration.

The goal is a minimal, independently installable MCP that can be wired into Claude Code or Claude Desktop without pulling in the full `academic_wiki_mcp` toolchain (Playwright, Selenium, publisher-specific scrapers).

## Goals

- Ship a standalone MCP exposing three S2 tools: `semantic_scholar_search`, `get_paper_by_doi`, `discover_related`.
- Installable via a single pyproject extra (`s2_mcp`) with only `fastmcp` and `requests` as runtime dependencies.
- Launchable as a console script (`semantic-scholar-mcp`) for easy MCP client configuration.
- Fully self-contained: no imports from `academic_wiki_mcp`, trivially extractable to its own repo later.
- Tests mirror the existing S2 coverage, rewritten to import from the new package.
- README guides the user through install and Claude client configuration.

## Non-goals

- No edits to existing `academic_wiki_mcp` code or tests.
- No shared-core package refactor — the two MCPs duplicate S2 client logic deliberately.
- No new env vars, caching, or pagination beyond what the existing tools already support.
- No marketplace entry (`.claude-plugin/marketplace.json`) — this is a plain MCP server, not a plugin.
- No handling for tool-name collisions when both MCPs are registered in the same client; the user resolves via config (register only one, or prefix the server name).

## Architecture

### File layout

```
/home/tung491/Work/academic_wiki/
└── semantic_scholar_mcp/
    ├── __init__.py          # mcp = FastMCP("SemanticScholarServer")
    ├── README.md            # install + Claude client config guide
    ├── config.py            # SEMANTIC_SCHOLAR_API_KEY env var
    ├── identifier.py        # detect(identifier) — DOI/arXiv/S2 ID detection
    ├── s2_client.py         # _headers, _s2_get, _normalize_s2_paper,
    │                        # get_paper_by_doi (plain function, also wrapped as tool)
    ├── server.py            # main() entry point; imports tools to trigger registration
    └── tools/
        ├── __init__.py
        └── discovery.py     # @mcp.tool decorators for the three tools,
                             # plus private helpers _search, _references,
                             # _citations, _recommendations, _resolve_s2_id
```

All files are byte-for-byte copies of the corresponding `academic_wiki_mcp` files with imports rewritten from `academic_wiki_mcp.*` to `semantic_scholar_mcp.*`, except:
- `config.py` drops the unused `WIKI_ROOT` and `BROWSER_TIMEOUT` vars.
- `tools/discovery.py` adds a new `@mcp.tool()`-decorated wrapper around `get_paper_by_doi` (in the existing MCP it is a plain function, not a registered tool).
- `__init__.py` creates a `FastMCP("SemanticScholarServer")` instance (new server name).
- `README.md` is new (no equivalent in `academic_wiki_mcp`).

### Why copy, not import

The user chose full independence (Question 3, option 1). Benefits:
- New MCP can be extracted into its own repo with zero entanglement.
- Breaking changes in `academic_wiki_mcp` cannot cascade into the new MCP.
- Each MCP can evolve its S2 surface independently.

Cost: two copies of `s2_client.py` + `identifier.py` + the discovery helpers to maintain. Accepted.

## Tool surface

Three MCP tools, all `async`, registered on the new `FastMCP("SemanticScholarServer")` instance.

### `semantic_scholar_search(query, venue=None, year=None, limit=10) -> list[dict]`

Keyword search against `GET /graph/v1/paper/search`. Returns a list of normalized paper dicts. Empty list on non-200 or no results.

### `get_paper_by_doi(doi) -> dict | None`

Single-paper lookup against `GET /graph/v1/paper/DOI:{doi}`. Returns a normalized paper dict on 200, `None` on 404 or any error.

### `discover_related(identifier, limit=10) -> dict`

Fan-out over three S2 endpoints and merge results:
- `GET /graph/v1/paper/{id}/references?limit=50`
- `GET /graph/v1/paper/{id}/citations?limit=50`
- `GET /recommendations/v1/papers/forpaper/{id}?limit=20`

`identifier` is resolved to an S2 path via `detect()`: DOI → `DOI:{raw}`, arXiv → `ARXIV:{raw}`, else passthrough as S2 paper ID.

Returns `{"related": [...], "total_found": int}`. The `related` list is de-duplicated by `paperId`, sorted by `citationCount` descending, and truncated to `limit`. `total_found` is the pre-truncation union size.

### Normalized paper dict shape

From `_normalize_s2_paper`:
```
{
  "paperId": str,
  "title": str,
  "authors": [str, ...],     # name strings, not objects
  "year": int | None,
  "venue": str,
  "abstract": str,
  "doi": str,                 # "" if missing
  "arxiv": str,               # "" if missing
  "citationCount": int,
  "publicationTypes": [str, ...]
}
```

S2 fields requested: `paperId,title,authors,year,venue,abstract,externalIds,citationCount,publicationTypes`.

## HTTP behavior

All HTTP goes through `_s2_get(url, params, max_retries=5)`:
- 200 → return response.
- 404 → return response (caller handles as "not found").
- 429 / 500 / 502 / 503 → exponential backoff `sleep(2**attempt)`, retry up to `max_retries` times, then return `None`.
- Other non-200 → `raise_for_status()`.
- Timeout: 30 seconds per request.

Headers include `x-api-key` when `SEMANTIC_SCHOLAR_API_KEY` is set; otherwise no auth header is sent (S2 allows unauthenticated requests at lower rate limits).

## Configuration

### Env vars

| Name | Required | Default | Purpose |
|---|---|---|---|
| `SEMANTIC_SCHOLAR_API_KEY` | No | `""` | S2 API key; unset → unauthenticated (rate-limited). |

No other env vars. `WIKI_ROOT` and `BROWSER_TIMEOUT` from `academic_wiki_mcp/config.py` are omitted.

### `pyproject.toml` edits

Two changes to `/home/tung491/Work/academic_wiki/pyproject.toml`:

**1. New optional-dependencies group:**
```toml
[project.optional-dependencies]
s2_mcp = [
    "fastmcp>=3.1.1",
    "requests>=2.31",
]
```

**2. Console script and package discovery:**
```toml
[project.scripts]
semantic-scholar-mcp = "semantic_scholar_mcp.server:main"

[tool.setuptools.packages.find]
include = ["academic_wiki_mcp*", "semantic_scholar_mcp*"]
```

Install: `uv pip install -e ".[s2_mcp]"` (or `pip install -e ".[s2_mcp]"`). To get both MCPs: `.[mcp,s2_mcp]`.

### Server entry point (`server.py`)

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

Launchable as:
- `semantic-scholar-mcp` (stdio, default)
- `semantic-scholar-mcp stdio` / `sse` / `http`
- `python -m semantic_scholar_mcp.server [transport]`

## README contents

New file at `semantic_scholar_mcp/README.md`. Sections:

1. **What it is** — one paragraph describing the server and its three tools.
2. **Install**
   - `uv pip install -e ".[s2_mcp]"` from repo root (or `pip install -e ".[s2_mcp]"`).
   - Sanity check: `semantic-scholar-mcp --help` / `which semantic-scholar-mcp`.
3. **Configure for Claude Code**
   - `claude mcp add semantic-scholar -- semantic-scholar-mcp` (one-liner).
   - Alternative: manual `~/.claude.json` snippet:
     ```json
     {
       "mcpServers": {
         "semantic-scholar": {
           "command": "semantic-scholar-mcp",
           "env": { "SEMANTIC_SCHOLAR_API_KEY": "<optional>" }
         }
       }
     }
     ```
4. **Configure for Claude Desktop** — OS-specific `claude_desktop_config.json` paths, same JSON snippet.
5. **Environment variables** — `SEMANTIC_SCHOLAR_API_KEY` is optional; without it, the server works but is rate-limited per S2's unauthenticated tier.
6. **Tools reference** — signature + one-line description for each of the three tools; one example response shape.
7. **Troubleshooting** — note on tool-name collision if both `academic_wiki_mcp` and `semantic_scholar_mcp` are registered in the same client.

## Tests

New directory `tests/semantic_scholar_mcp/`:

```
tests/semantic_scholar_mcp/
├── __init__.py
├── conftest.py        # empty placeholder unless fixtures are needed
├── test_discovery.py  # copied from tests/mcp/test_discovery.py,
│                      # imports rewritten to semantic_scholar_mcp.*
├── test_identifier.py # copied from tests/mcp/test_identifier.py,
│                      # imports rewritten
├── test_s2_client.py  # new: get_paper_by_doi on 200 → dict,
│                      # on 404 → None, on 5xx → None after retries
└── test_server.py     # new: import server, assert three tools registered
                       # on the FastMCP instance
```

- `test_discovery.py` and `test_identifier.py` are direct copies with the only delta being `academic_wiki_mcp` → `semantic_scholar_mcp` in import paths.
- `test_s2_client.py` covers `get_paper_by_doi` — not tested in the existing suite because it wasn't a registered tool there.
- `test_server.py` is the new MCP's integration-level smoke test: imports `semantic_scholar_mcp.server`, then verifies the FastMCP instance has exactly `{"semantic_scholar_search", "get_paper_by_doi", "discover_related"}` registered. Catches packaging / import / decorator errors that unit tests miss.
- `tool.pytest.ini_options.testpaths` stays `["tests"]`, so the new directory is auto-discovered.

## Error handling

Same behavior as existing `academic_wiki_mcp`:
- `_s2_get` exponential-backoff retries on 429/5xx (up to 5 attempts).
- 404 returned to caller for explicit handling.
- Tools never raise on missing data; they return empty-ish values (`[]`, `None`, `{"related": [], "total_found": 0}`).
- No request returns a truncated or malformed payload without S2 having returned 200 — so the JSON decode path in `_normalize_s2_paper` is safe.

## Runtime dependencies

- `fastmcp>=3.1.1` — MCP server framework.
- `requests>=2.31` — HTTP client.

No `playwright`, `selenium`, `undetected-chromedriver`, `selenium-stealth`, or `pyyaml`.

## Risks / open items

1. **Tool-name collision** — if both MCPs register with the same client, both `semantic_scholar_search` and `discover_related` will appear twice. User-resolvable at client config time. Documented in README troubleshooting.
2. **Silent drift** — S2 client code duplication means bugfixes in one MCP won't propagate. Accepted cost of the independence choice; re-visit if both MCPs evolve in lockstep for long.
3. **`get_paper_by_doi` as a new tool** — the existing MCP has it as a plain function only. Promoting it to a tool here is a small surface-area decision that was chosen in Question 2, option 3.

## Implementation order (preview)

The implementation plan (produced by `writing-plans` in the next step) will sequence:

1. Create `semantic_scholar_mcp/` skeleton + `config.py` + `identifier.py` + `s2_client.py` (copied & import-rewritten).
2. Create `semantic_scholar_mcp/tools/discovery.py` with the three `@mcp.tool` registrations.
3. Create `semantic_scholar_mcp/server.py` with `main()`.
4. Edit `pyproject.toml` (extras group, console script, package discovery).
5. Reinstall the editable package; verify `semantic-scholar-mcp --help` works.
6. Create `tests/semantic_scholar_mcp/` with the four test files; run `pytest tests/semantic_scholar_mcp/`.
7. Write `semantic_scholar_mcp/README.md`.
8. End-to-end: register the MCP with Claude Code, verify all three tools appear and return results for a live S2 query.
