# academic_wiki_mcp

The MCP server bundled with [`academic-wiki`](../README.md). Exposes paper-fetching, BibTeX, and Semantic Scholar discovery tools to any MCP-aware LLM client (Claude Code, Claude Desktop, Gemini CLI, Antigravity, Cursor, …).

It can be used standalone — you don't need the Claude Code plugin to call these tools — but `download_paper` writes into a wiki tree that follows the academic-wiki layout (`<wiki_path>/raw/papers/<paper-id>/`).

---

## Tools

| Tool | Purpose |
|---|---|
| `download_paper(identifier, wiki_path)` | Resolve an arXiv ID, DOI, or URL → fetch the publisher page → extract metadata, sections, and figures → save under `<wiki_path>/raw/papers/<paper-id>/`. Runs identifier-level dedup against existing papers; returns `is_new: false` on a hit. |
| `doi_to_bibtex(doi, paper_id)` | Fetch a BibTeX entry for a DOI via doi.org content negotiation, with a Semantic Scholar fallback. Returns `{bibtex, source, entry_type}`. |
| `semantic_scholar_search(query, venue?, year?, limit?)` | Keyword search Semantic Scholar. Side-effect: writes each result as a clipper-compatible stub into the active wiki's `raw/papers/` (see [Auto-stub](#auto-stub)). |
| `get_paper_by_doi(doi)` | Single-paper lookup on Semantic Scholar. |
| `discover_related(identifier, limit?)` | Union of references + citations + recommendations for a DOI / arXiv ID / S2 paper ID, deduplicated by paper ID and sorted by citation count. |

### Normalized paper dict

Both `semantic_scholar_search` and `get_paper_by_doi` return the same shape:

```
{
  "paperId":          str,
  "title":            str,
  "authors":          [str, ...],
  "year":             int | None,
  "venue":            str,
  "abstract":         str,
  "doi":              str,
  "arxiv":            str,
  "citationCount":    int,
  "publicationTypes": [str, ...]   # e.g. ["JournalArticle"], ["Conference"], ["Book"]
}
```

`publicationTypes` drives BibTeX entry-type selection in `doi_to_bibtex`:
`JournalArticle`/`Review` → `@article`, `Conference` → `@inproceedings`,
`Book` → `@book`, `BookSection` → `@incollection`, with a venue-regex fallback.

### `download_paper` return shape

```
{
  "paper_id": "vaswani-2017-attention",
  "path":     "/path/to/wiki/raw/papers/vaswani-2017-attention",
  "title":    "Attention Is All You Need",
  "authors":  ["Ashish Vaswani", ...],
  "is_new":   true,                        # false if dedup matched an existing paper
  "partial":  true                         # only present on best-effort arXiv /abs fallback
}
```

Errors return `{"error": "...", "identifier": "...", "partial_metadata": {...}}` rather than raising.

---

## Install

```bash
git clone git@github.com:tung491/academic-wiki.git
cd academic-wiki
uv pip install -e ".[mcp]"
# or, with plain pip:
pip install -e ".[mcp]"
```

The `[mcp]` extra pulls in `fastmcp`, `requests`, and the browser-automation stack (`playwright`, `selenium`, `undetected-chromedriver`, `selenium-stealth`) used by `download_paper` for publisher pages that need JavaScript.

The server runs as a stdio process:

```bash
python -m academic_wiki_mcp.server
```

Use the **absolute path** to your venv's Python in client configs so they work regardless of shell `PATH`.

---

## Configure

The same JSON shape works for every MCP-aware client; only the file location and registration command differ.

### Claude Code

```bash
claude mcp add academic-wiki -- /path/to/academic-wiki/.venv/bin/python -m academic_wiki_mcp.server
```

Or edit `~/.claude.json` (or per-project `.claude/settings.json`) under `mcpServers`:

```json
{
  "mcpServers": {
    "academic-wiki": {
      "type": "stdio",
      "command": "/path/to/academic-wiki/.venv/bin/python",
      "args": ["-m", "academic_wiki_mcp.server"],
      "env": {
        "SEMANTIC_SCHOLAR_API_KEY": "optional-key-here"
      }
    }
  }
}
```

Restart Claude Code. Tools appear as `mcp__academic-wiki__download_paper`, etc.

### Claude Desktop

Edit `claude_desktop_config.json`:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "academic-wiki": {
      "command": "/path/to/academic-wiki/.venv/bin/python",
      "args": ["-m", "academic_wiki_mcp.server"],
      "env": {
        "SEMANTIC_SCHOLAR_API_KEY": "optional-key-here"
      }
    }
  }
}
```

Restart Claude Desktop.

### Gemini CLI

Edit `~/.gemini/settings.json` (or project-level `.gemini/settings.json`):

```json
{
  "mcpServers": {
    "academic-wiki": {
      "command": "/path/to/academic-wiki/.venv/bin/python",
      "args": ["-m", "academic_wiki_mcp.server"],
      "env": {
        "SEMANTIC_SCHOLAR_API_KEY": "optional-key-here"
      }
    }
  }
}
```

Restart the Gemini session. Verify with `gemini mcp list`.

### Antigravity (Google IDE)

Settings → MCP Servers → Add, or edit the config file directly with the same JSON shape:

```json
{
  "mcpServers": {
    "academic-wiki": {
      "command": "/path/to/academic-wiki/.venv/bin/python",
      "args": ["-m", "academic_wiki_mcp.server"],
      "env": {
        "SEMANTIC_SCHOLAR_API_KEY": "optional-key-here"
      }
    }
  }
}
```

Reload the Antigravity window.

### Other MCP-aware clients (Cursor, Continue, Cody, …)

The recipe is always the same:

- **command** — absolute path to the Python interpreter
- **args** — `["-m", "academic_wiki_mcp.server"]`
- **env** (optional) — see [Environment variables](#environment-variables)
- **transport** — stdio (the default)

---

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `WIKI_ROOT` | `~/Documents/Obsidian Vault/03-Resources` | Root that all `wiki_path` arguments must be inside. `download_paper` rejects requests outside this tree. |
| `SEMANTIC_SCHOLAR_API_KEY` | unset | Sent as `x-api-key` to S2. Without it the server uses the anonymous tier (lower rate limits but works). Get one at https://www.semanticscholar.org/product/api. |
| `BROWSER_TIMEOUT` | `15000` | Browser-automation timeout in milliseconds for `download_paper`. |
| `S2_STUB_DEBUG` | unset | When set (any non-empty value), the auto-stub helper logs diagnostic info to stderr on each `semantic_scholar_search` call. Useful when stubs aren't being written and you want to know why. |

---

## Auto-stub

`semantic_scholar_search` has a side effect: every result is written as a "stub" markdown file into the **active wiki's** `raw/papers/` directory. The active wiki is resolved by walking up from the server's `cwd` looking for a directory with both `CLAUDE.md` and `wiki/`; if none is found, it falls back to `WIKI_ROOT/academic/`.

Stub filenames are deterministic per paper:

- `s2-doi-<sanitized-doi>.md` — when the result has a DOI
- `s2-arxiv-<arxiv-id>.md` — when there's an arXiv ID but no DOI (version stripped)
- `s2-pid-<sha256-prefix>.md` — fallback to the S2 paper ID

Stubs are clipper-compatible: if the same paper is later web-clipped or fully ingested, the dedup pipeline merges identifiers rather than creating a duplicate.

Failures are silent — if the wiki can't be located or the write fails, the search call still returns its results normally. Set `S2_STUB_DEBUG=1` to see what's happening.

---

## Supported publishers (for `download_paper`)

| Domain | Backend |
|---|---|
| `arxiv.org` | playwright (HTML page) with `/abs` fallback |
| `ieeexplore.ieee.org` | undetected-chromedriver |
| `dl.acm.org`, `link.springer.com` | selenium-stealth |
| `mdpi.com` | playwright |
| `sciencedirect.com` | undetected-chromedriver |
| `tandfonline.com`, `ascelibrary.org` | undetected-chromedriver |

Other publishers return `{"error": "Publisher not supported: <domain>"}`. Add a new publisher in `academic_wiki_mcp/publishers/`.

---

## Troubleshooting

- **`Invalid wiki_path`** — The path you passed to `download_paper` is not inside `WIKI_ROOT`. Either point `wiki_path` at a directory under `~/Documents/Obsidian Vault/03-Resources/` or override `WIKI_ROOT` in the server's env.
- **`Cannot detect identifier type`** — Pass a recognizable form: arXiv ID (`1706.03762`, optionally `vN`), DOI (`10.xxxx/...`), or full URL. Use `semantic_scholar_search` first to discover identifiers from a free-text query.
- **`Both backends blocked`** — Publisher detected the automation. Try again later; consider using the [`agentic-rag-v2`](../README.md) MCP's downloader instead for that domain, or fetch manually and ingest the local PDF.
- **No stubs after `semantic_scholar_search`** — Set `S2_STUB_DEBUG=1` and re-run; stderr will say whether the active wiki was found, whether the result had a usable identifier, or whether the write failed.
- **HTTP 429 from Semantic Scholar** — Anonymous tier rate limit. Set `SEMANTIC_SCHOLAR_API_KEY`.

---

## Development

```bash
pip install -e ".[dev,mcp]"
python -m pytest tests/mcp -v
```

Tests live in `tests/mcp/`. The bibtex entry-type tests in `tests/mcp/test_bibtex.py` cover both the S2 `publicationTypes`-driven path and the venue-regex fallback.

---

## See also

- Parent project & Claude Code plugin: [`../README.md`](../README.md)
- Walkthrough: [`../WALKTHROUGH.md`](../WALKTHROUGH.md)
- Karpathy's LLM-Wiki pattern: [`../refs/llm-wiki.md`](../refs/llm-wiki.md)
