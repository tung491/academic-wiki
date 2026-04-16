# academic-wiki

A Claude Code plugin that implements an LLM-driven knowledge base specialized for academic papers — PDF/arXiv/DOI ingestion, BibTeX export, cross-paper synthesis, Obsidian as the front-end viewer.

Based on the Karpathy LLM-Wiki pattern (`refs/llm-wiki.md`), specialized for academic data.

## Status

This plugin ships in four waves. The current state:

- **Wave 1 (shipped)**: `init`, `ingest`, `compile --paper-only`, `query` (Phase 1 search).
- Wave 2: entity extraction, cites resolution, cross-paper synthesis (candidate-only, no silent auto-promote).
- Wave 3: `lint`, `export-bibtex`, `snapshot`.
- Wave 4: `remove`, WALKTHROUGH, polish.

See `docs/superpowers/specs/2026-04-16-academic-wiki-design.md` for the full design spec.

## Installation

Install as a local Claude Code plugin:

```bash
# From the academic_wiki/ directory
claude plugin install .
```

Or from the marketplace manifest:

```bash
claude plugin marketplace add /path/to/academic_wiki
claude plugin install academic-wiki
```

### Prerequisites

- **Python 3.10+** — for `academic_wiki_lib` helpers
- **git** with `user.name` and `user.email` configured
- **Obsidian vault** at `~/ObsidianVault/03-Resources/`
- **Node.js 18+** (optional) — for auto-installing qmd and marp-cli via the SessionStart hook
- **Existing skill**: `ocr-papers-to-latex` — used by `ingest` for PDF extraction
- **Existing MCP**: `agentic-rag-v2` — used by `ingest` for arXiv/DOI/publisher fetching (tools: `download_arxiv`, `doi2content`, `fetch_publisher_html`)

Install Python deps with:

```bash
pip install pyyaml pytest
```

## Usage

### Initialize a new wiki

```
/academic-wiki:wiki init academic
```

Creates `~/ObsidianVault/03-Resources/academic/` as a self-contained wiki with its own git repo. Scaffolds the 16-subdirectory layout, writes `CLAUDE.md` (the authoritative schema), and makes the first commit.

### Ingest a paper

The plugin auto-detects the input type:

```
/academic-wiki:wiki ingest 1706.03762                   # arXiv ID
/academic-wiki:wiki ingest 1706.03762v5                 # specific arXiv version
/academic-wiki:wiki ingest 10.1145/3442188.3445922      # DOI
/academic-wiki:wiki ingest https://arxiv.org/abs/1706.03762
/academic-wiki:wiki ingest ~/Downloads/paper.pdf        # local PDF
/academic-wiki:wiki ingest ~/notes/paper.md             # pre-extracted markdown
```

Ingest assigns a canonical `paper-id`, deduplicates against existing papers (by source-sha AND by identifier match), handles versions as updates to one canonical paper, and saves raw source + extract + BibTeX under a consistent `<paper-id>` basename.

### Compile (Wave 1 — paper-only)

```
/academic-wiki:wiki compile                          # compile all uncompiled sources
/academic-wiki:wiki compile vaswani-2017-attention   # compile one paper
```

Creates `wiki/papers/<paper-id>.md` with full metadata frontmatter + body sections (Summary, Key Contributions, Methods, Results, Claims, User Notes, See Also). In Wave 1 this is the paper-only tier — no concept/method/open-problem pages are created, `cites:` stays empty, no cross-paper synthesis.

### Query the wiki

```
/academic-wiki:wiki query "What is self-attention and how does it scale?"
```

Searches paper pages (Phase 1: `index.md` + ripgrep; Phase 2: qmd if installed). Synthesizes an answer with `[[paper-id]]` wikilink citations, files it to `wiki/queries/<slug>.md`, and offers to promote it to a first-class entity page.

## Wiki structure

```
~/ObsidianVault/03-Resources/academic/    # its own nested git repo
├── raw/                                   # immutable sources
│   ├── papers/      — PDFs / HTML / TeX / markdown
│   ├── extracts/    — LLM-readable extracts with source-sha, extractor metadata
│   ├── bib/         — per-paper BibTeX files
│   ├── figures/     — per-paper figure dumps
│   └── notes/       — user's manual reading notes (optional, per paper)
├── wiki/                                  # LLM-owned synthesis
│   ├── index.md
│   ├── papers/      — one page per paper (paper-id as filename)
│   ├── concepts/    — Wave 2
│   ├── methods/     — Wave 2
│   ├── open-problems/
│   ├── claims/      — only cross-paper claims (Wave 2+)
│   ├── results/     — only cross-paper results (Wave 2+)
│   ├── authors/     — on-demand
│   ├── venues/      — on-demand
│   └── queries/     — filed query answers
├── outputs/
│   ├── reports/     — lint reports (Wave 3)
│   └── bib/         — consolidated BibTeX exports (Wave 3)
├── CLAUDE.md        — the authoritative schema (inlined from spec)
├── log.md           — append-only operation log
├── .lock            — advisory lockfile (created on-demand)
├── .gitignore
└── qmd.yml          — qmd search collection config (optional)
```

The wiki is its own git repo (nested inside the Obsidian vault). Snapshots (Wave 3) tag this repo, not the vault's.

## Key concepts

- **paper-id vs citation-key**: `paper-id` is the canonical internal identifier (`vaswani-2017-attention`, hyphen-separated). `citation-key` is the BibTeX-native form (`vaswani2017attention`, no hyphens), derived from metadata and used only for `.bib` export. `paper-id` never changes; `citation-key` can be corrected later without renaming files.
- **Identifiers + dedup**: papers carry `identifiers: {doi, arxiv, arxiv-version, url}`. Ingest checks every incoming source's identifiers against existing papers. A match = reuse `paper-id` (merge identifiers; handle as new version if `source-version` differs). A fresh paper = generate a new `paper-id`.
- **sources vs cites vs references-raw**: `cites:` (paper pages only) lists the subset of bibliography that's been resolved to `paper-id`s in the wiki. `references-raw:` is the verbatim bibliography. `sources:` (on concept/method/etc. pages, Wave 2+) lists papers that inform that page.

## Development

Run the test suite:

```bash
python -m pytest -v
```

(Expects pyyaml and pytest installed; see Prerequisites.)

## Spec

Full design: `docs/superpowers/specs/2026-04-16-academic-wiki-design.md`.
Implementation plan: `docs/superpowers/plans/2026-04-16-academic-wiki-plan.md`.

## License

MIT. See `LICENSE`.
