# academic-wiki

A Claude Code plugin (with a bundled MCP server) that builds a **persistent, compounding knowledge base of academic papers** inside an Obsidian vault. Ingest by arXiv ID, DOI, PDF, or web clipping; the LLM extracts, deduplicates, versions, and synthesizes — papers, concepts, methods, claims, results — into a graph of cross-linked markdown.

It applies Andrej Karpathy's [LLM-Wiki pattern](refs/llm-wiki.md) (`refs/llm-wiki.md`), but specialized for academic data: identifiers and dedup, BibTeX export, paper versioning, snapshots for reproducibility.

---

## How this differs from Karpathy's `llm-wiki`

Karpathy's `llm-wiki` is a **generic** LLM wiki for articles, web clippings, and free-form notes. `academic-wiki` keeps the same core pattern (raw → wiki → schema, with `ingest` / `compile` / `query` / `lint`) but adds machinery you need when the sources are scholarly papers:

| | `llm-wiki` (Karpathy) | `academic-wiki` (this project) |
|---|---|---|
| **Domain** | Generic articles, web pages, notes | Academic papers |
| **Operations** | 6: init, ingest, compile, query, lint, remove | 8: adds `export-bibtex`, `snapshot` |
| **Source types** | Plain markdown / URL | arXiv ID (with version), DOI, PDF, web clipping, pre-extracted markdown |
| **Identity** | Source filename | `paper-id` (stable, hyphenated) + `citation-key` (BibTeX) + `identifiers` (DOI / arXiv / URL) |
| **Deduplication** | None | Two-pass: byte-SHA, then identifier match across DOI / arXiv / URL — same paper from different sources collapses to one `paper-id` |
| **Versioning** | None | arXiv v1, v2... resolved to one canonical paper with `.versions.yml` history |
| **BibTeX** | n/a | Per-paper `raw/bib/<paper-id>.bib`; consolidated export filtered by project / field / tag / keys / natural-language query |
| **Snapshots** | Vault-shared git | Each wiki is its **own** nested git repo; `snapshot <label>` creates an annotated tag for reproducibility (e.g. conference submission) |
| **Page taxonomy** | Concepts, people, sources | Papers + concepts + methods + claims + results + open-problems + authors + venues + queries |
| **Tag scheme** | Free-form | Reserved prefixes auto-applied: `field/*`, `subfield/*`, `method/*`, `year/*`, `venue/*`; user-controlled: `project/*`, `user/*` |
| **Bibliography model** | n/a | `references-raw` (verbatim) → `cites` (resolved to internal `paper-id`s) → `sources` (papers informing a non-paper page) |
| **Conflict policy** | Implicit | Explicit: prior text preserved, new evidence appended, contradictions flagged with `[!WARNING]` callouts — nothing silently overwritten |
| **Bundled tooling** | qmd auto-install | qmd auto-install **+** `academic_wiki_mcp` server: `download_paper`, `doi_to_bibtex`, `semantic_scholar_search`, `get_paper_by_doi`, `discover_related` |
| **Wave structure** | n/a | Wave 1 = paper pages only; Wave 2 = entity extraction + cross-paper synthesis (candidate-only, never auto-promoted) |

If you're tracking generic web articles and personal notes, use Karpathy's `llm-wiki`. If your sources are papers and you need stable IDs, BibTeX, and reproducible snapshots, use this.

---

## Project layout

```
academic_wiki/
├── .claude-plugin/          # plugin manifest (marketplace.json)
├── commands/wiki.md         # /academic-wiki:wiki slash command
├── skills/wiki/             # the SKILL.md the LLM follows
├── hooks/                   # SessionStart hook (qmd / marp auto-install)
├── scripts/                 # academic_wiki_lib helpers (Python)
├── academic_wiki_mcp/       # bundled MCP server (paper downloads, BibTeX, S2 discovery)
├── tests/                   # pytest suite
├── docs/                    # design specs and plans
└── refs/llm-wiki.md         # Karpathy's original idea
```

---

## Prerequisites

- **Python 3.10+** — `academic_wiki_lib` helpers and the MCP server
- **git** with `user.name` and `user.email` configured
- **Obsidian vault** at `~/Documents/Obsidian Vault/03-Resources/` (note the space in the directory name)
- **Node.js 18+** (optional) — auto-installs `qmd` and `marp-cli` via the SessionStart hook
- **Existing skill** `ocr-papers-to-latex` — used by `ingest` for local-PDF extraction
- **Existing MCP** `agentic-rag-v2` — used by `ingest` for arXiv / DOI / publisher fetching (`download_arxiv`, `doi2content`, `fetch_publisher_html`)

---

## Install — Claude Code plugin

The plugin gives you the `/academic-wiki:wiki` slash command in Claude Code.

From this repo:

```bash
# inside academic_wiki/
claude plugin marketplace add .
claude plugin install academic-wiki
```

Or directly:

```bash
claude plugin install /path/to/academic_wiki
```

Verify in a Claude Code session:

```
/academic-wiki:wiki
```

You should see the usage line listing all 8 operations.

---

## Install — `academic_wiki_mcp` server

The bundled MCP exposes paper-fetching and discovery tools that any MCP-aware client can call:

| Tool | Purpose |
|---|---|
| `download_paper(identifier, wiki_path)` | Resolve arXiv ID / DOI / URL → save the source under `wiki_path/raw/papers/` |
| `doi_to_bibtex(doi, paper_id)` | Fetch a BibTeX entry for a DOI (doi.org content negotiation; S2 fallback) |
| `semantic_scholar_search(query, venue?, year?, limit?)` | Keyword search Semantic Scholar |
| `get_paper_by_doi(doi)` | Single-paper lookup on S2 |
| `discover_related(identifier, limit?)` | Union of references + citations + recommendations for a DOI / arXiv ID / S2 ID |

### One-time setup

```bash
cd /path/to/academic_wiki
pip install -e ".[mcp]"
# or, with uv:
uv pip install -e ".[mcp]"
```

The `[mcp]` extra pulls in `fastmcp`, `requests`, and the browser-automation deps (`playwright`, `selenium`, `undetected-chromedriver`, `selenium-stealth`) used by `download_paper` for publisher pages.

The server is invoked as `python -m academic_wiki_mcp.server`. Use the **absolute** path to your venv's Python in client configs so they don't depend on shell `PATH`.

### Optional: API key

Set `SEMANTIC_SCHOLAR_API_KEY` in the server's environment to lift Semantic Scholar's anonymous rate limits. The server still works without it.

### Claude Code

```bash
claude mcp add academic-wiki -- /path/to/academic_wiki/.venv/bin/python -m academic_wiki_mcp.server
```

Or edit `~/.claude.json` (or per-project `.claude/settings.json`) under `mcpServers`:

```json
{
  "mcpServers": {
    "academic-wiki": {
      "type": "stdio",
      "command": "/path/to/academic_wiki/.venv/bin/python",
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
      "command": "/path/to/academic_wiki/.venv/bin/python",
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

Edit `~/.gemini/settings.json` (or a project-level `.gemini/settings.json`):

```json
{
  "mcpServers": {
    "academic-wiki": {
      "command": "/path/to/academic_wiki/.venv/bin/python",
      "args": ["-m", "academic_wiki_mcp.server"],
      "env": {
        "SEMANTIC_SCHOLAR_API_KEY": "optional-key-here"
      }
    }
  }
}
```

Restart the Gemini CLI session. The MCP schema is the same as Claude's; check `gemini mcp list` to confirm the server is registered.

### Antigravity (Google IDE)

Antigravity reads MCP servers from its settings UI (Settings → MCP Servers → Add) or its config file. Use the same JSON shape as above:

```json
{
  "mcpServers": {
    "academic-wiki": {
      "command": "/path/to/academic_wiki/.venv/bin/python",
      "args": ["-m", "academic_wiki_mcp.server"],
      "env": {
        "SEMANTIC_SCHOLAR_API_KEY": "optional-key-here"
      }
    }
  }
}
```

Reload the Antigravity window after saving. If your installation supports project-scoped servers, dropping the same JSON in the project's MCP config file works the same way.

### Other MCP-aware clients (Cursor, Cody, Continue, …)

Most clients accept the same `mcpServers` JSON. The recipe is always:

- `command`: absolute path to the Python interpreter
- `args`: `["-m", "academic_wiki_mcp.server"]`
- `env` (optional): `SEMANTIC_SCHOLAR_API_KEY`
- `transport`: stdio (default)

---

## Usage

```
/academic-wiki:wiki init <name>                      # scaffold a new wiki
/academic-wiki:wiki ingest <path|arxiv-id|doi|url>   # save + dedup a source
/academic-wiki:wiki compile [<paper-id>] [--paper-only]
/academic-wiki:wiki query "<question>"               # answer with [[paper-id]] cites; file to queries/
/academic-wiki:wiki lint [--fix-dead-links] [--suggest-backlinks]
/academic-wiki:wiki export-bibtex --project <name>   # filter by project / field / tag / keys / query
/academic-wiki:wiki snapshot <label>                 # annotated git tag on the wiki's repo
/academic-wiki:wiki remove <name>                    # typed-name confirmation required
```

Examples:

```
/academic-wiki:wiki init academic
/academic-wiki:wiki ingest 1706.03762
/academic-wiki:wiki ingest 10.1145/3442188.3445922
/academic-wiki:wiki ingest ~/Downloads/paper.pdf
/academic-wiki:wiki compile --paper-only
/academic-wiki:wiki query "What is self-attention and how does it scale?"
/academic-wiki:wiki export-bibtex --project rsma-survey-2025 --label rsma-survey
/academic-wiki:wiki snapshot icc-2026-submission
```

See [`WALKTHROUGH.md`](WALKTHROUGH.md) for a full guided tour.

---

## Wiki layout

Each wiki lives at `~/Documents/Obsidian Vault/03-Resources/<name>/` as its own nested git repo:

```
<name>/
├── raw/                    # immutable sources
│   ├── papers/             # PDFs / HTML / TeX / markdown
│   ├── extracts/           # LLM-readable extracts (frontmatter: source-sha, extractor, ...)
│   ├── bib/                # per-paper BibTeX
│   ├── figures/            # per-paper figure dumps
│   └── notes/              # user's manual notes (immutable to LLM)
├── wiki/                   # LLM-owned synthesis
│   ├── index.md
│   ├── papers/             # one page per paper
│   ├── concepts/  methods/  open-problems/
│   ├── claims/  results/   # cross-paper only (Wave 2+)
│   ├── authors/  venues/   # on-demand
│   └── queries/            # filed query answers
├── outputs/
│   ├── reports/            # lint reports, promotion candidates
│   └── bib/                # consolidated BibTeX exports
├── CLAUDE.md               # authoritative schema the LLM follows
├── log.md                  # append-only operation log
├── .lock  .gitignore  qmd.yml
```

---

## Key concepts

- **`paper-id` vs `citation-key`** — `paper-id` is the canonical internal identifier (`vaswani-2017-attention`, hyphen-separated, never changes); `citation-key` is the BibTeX-native form (`vaswani2017attention`, no hyphens), derived at export time and editable without renaming files.
- **Identifiers + dedup** — every paper carries `identifiers: {doi, arxiv, arxiv-version, url}`. Ingest checks each new source against existing papers; a match merges identifiers (or registers a new version), never duplicates.
- **`references-raw` / `cites` / `sources`** — `references-raw` is the verbatim bibliography; `cites` is the subset resolved to in-wiki `paper-id`s; `sources` is the list of papers informing a non-paper entity page.
- **Conflict policy** — recompiles preserve prior text, append new evidence, and flag contradictions with `[!WARNING]` callouts. Nothing is silently replaced.

---

## Development

```bash
pip install -e ".[dev,mcp]"
python -m pytest -v
```

---

## Spec & roadmap

- Design: `docs/superpowers/specs/2026-04-16-academic-wiki-design.md`
- Plan: `docs/superpowers/plans/2026-04-16-academic-wiki-plan.md`
- Wave 1 (shipped): init, ingest, compile --paper-only, query (Phase 1)
- Wave 2: entity extraction, cites resolution, cross-paper candidate detection (no auto-promote)
- Wave 3: lint, export-bibtex, snapshot
- Wave 4: remove, polish

---

## License

MIT. See [`LICENSE`](LICENSE).
