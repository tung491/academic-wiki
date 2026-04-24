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
