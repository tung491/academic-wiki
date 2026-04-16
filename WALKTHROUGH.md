# academic-wiki Walkthrough

A guided tour for new users. Read top to bottom the first time, then use as reference.

---

## Part 1: Introduction

### What is an academic wiki?

Andrej Karpathy described a pattern where an LLM reads raw source material, writes cross-linked wiki articles from it, files Q&A answers back into the knowledge base, and periodically lints for gaps and contradictions. This plugin applies that pattern to academic papers inside Obsidian: the LLM reads papers, synthesizes cross-linked wiki pages, files query answers, and lints for gaps. Papers are identified canonically (`paper-id` + identifiers), deduplicated across arXiv / DOI / URL, and versioned as papers get revised. The result is a knowledge base that compounds over time.

### Why Obsidian?

Obsidian stores everything as plain markdown files on disk:

- **Graph view** renders `[[wikilinks]]` as a visual network for free
- **Dataview** queries frontmatter across all pages — dynamic tables of papers, concepts, methods by tag, year, or venue
- **Web Clipper** saves web pages and preprints directly to `raw/papers/`, ready to ingest
- **Marp** exports any page as slides with `marp: true` in frontmatter

No lock-in. The files are yours.

### What this plugin does

Eight operations, invoked from a Claude Code session:

| Operation | What it does |
|-----------|-------------|
| `init <name>` | Scaffold a new wiki with 16-dir tree, CLAUDE.md schema, git repo |
| `ingest <path\|id\|url>` | Save a source with dedup + version handling. Does not create wiki pages. |
| `compile [<paper-id>] [--paper-only]` | Wave 1 (paper pages only) or Wave 2 (full synthesis + entity extraction) |
| `query <question>` | Answer against the wiki with `[[paper-id]]` citations; file to queries/; offer promotion |
| `lint [--fix-dead-links] [--suggest-backlinks] [--with-suggestions]` | Audit dead links, orphans, missing sections, index drift |
| `export-bibtex <selectors>` | Consolidated `.bib` for paper writing, filtered by project/field/tag/keys |
| `snapshot <label>` | Git-tag the wiki's own repo for reproducibility |
| `remove <name>` | Delete a wiki (typed-name confirmation required) |

---

## Part 2: Key Concepts

### Directory layout

Every wiki lives at `~/ObsidianVault/03-Resources/<name>/`:

```
<name>/
├── raw/              ← immutable source drops
│   ├── papers/       ← original PDFs, markdown, HTML sources
│   ├── extracts/     ← <paper-id>.md — OCR/extract + frontmatter
│   ├── bib/          ← <paper-id>.bib — per-paper BibTeX
│   ├── figures/      ← <paper-id>/ — extracted figures
│   └── notes/        ← <paper-id>.md — user-authored notes
├── wiki/             ← LLM-owned pages
│   ├── index.md      ← catalog; read before any operation
│   ├── papers/       ← <paper-id>.md per paper
│   ├── concepts/     ← concept pages (Wave 2)
│   ├── methods/      ← method pages (Wave 2)
│   ├── open-problems/  claims/  results/  authors/  venues/  (Wave 2)
│   └── queries/      ← filed query answers
├── outputs/
│   ├── reports/      ← lint reports, promotion-candidates
│   └── bib/          ← exported .bib files
├── CLAUDE.md         ← authoritative schema the LLM follows
├── log.md  .lock  .gitignore  qmd.yml
```

The wiki has its own nested git repo. The vault's outer git repo (if any) is configured to ignore the wiki directory.

### paper-id vs citation-key

`paper-id` is the canonical internal identifier: hyphen-separated, stable, used in filenames and `[[wikilinks]]`. Format: `<lastname>-<year>-<firstword>` (e.g., `vaswani-2017-attention`).

`citation-key` is the BibTeX-native form: no hyphens, used inside `.bib` files only (e.g., `vaswani2017attention`). It is derived at export time. If metadata is corrected later, `citation-key` updates without renaming any file.

Both appear in the paper page frontmatter. Everything in the wiki uses `paper-id`; only BibTeX export uses `citation-key`.

### Identifiers and dedup

`ingest` runs two dedup passes before creating a new paper:

1. **Byte-level (source-sha):** SHA-256 of the raw source. If an identical file was ingested before, skip entirely.
2. **Identifier-level:** compares `doi`, `arxiv` (ignoring version suffix), and `url` against all existing papers' `identifiers:` frontmatter. A match means the paper exists — ingest merges any new identifiers into the existing record rather than creating a duplicate.

Result: ingest the same paper via arXiv, then later via its DOI — one `paper-id` with merged identifiers, no duplicate.

### sources vs cites vs references-raw

- `references-raw:` — verbatim bibliography strings extracted from the paper itself.
- `cites:` — subset of references resolved to `paper-id` values present in this wiki (populated in Wave 2).
- `sources:` — `paper-id` values that inform a non-paper entity page (concept, method, claim, etc.).

### Tag taxonomy

Reserved prefixes (auto-applied by compile): `field/*`, `subfield/*`, `method/*`, `year/*`, `venue/*`. User-controlled: `project/*`, `user/*`. Free-form tags are allowed alongside reserved ones.

Example tags on a paper page: `[field/nlp, method/attention, year/2017, venue/nips, project/rsma-survey]`.

### Update conflict policy

When a recompiled or updated paper contributes overlapping information to an existing page:
- Prior claims and text are preserved.
- New evidence is appended.
- Contradictions are flagged with `> [!WARNING] Contradiction with [[other-paper-id]]` callouts.
- `updated:` is bumped.
- Nothing is silently replaced.

---

## Part 3: Installation

### Prerequisites

- Python 3.10+, git with `user.name` and `user.email` configured
- Obsidian vault at `~/ObsidianVault/` with a `03-Resources/` directory
- Node.js 18+ (optional, for qmd auto-install)
- `ocr-papers-to-latex` skill (for local PDF ingestion)
- `agentic-rag-v2` MCP (for arXiv/DOI/publisher download)

Verify before installing:

```bash
python3 --version          # 3.10+
git --version              # 2.x
git config user.name       # your name
ls ~/ObsidianVault/03-Resources/
```

### Install

From a Claude Code session:

```
/plugin install /path/to/academic_wiki
```

or via the marketplace.

### Verify

```
/academic-wiki:wiki
```

Expected output:

```
Usage: init <name> | ingest <path|id|url> | compile [<paper-id>] [--paper-only] | query <question> | lint | export-bibtex <selectors> | snapshot <label> | remove <name>
```

---

## Part 4: Your First Academic Wiki (Guided)

Work through these steps in order. Each builds on the previous.

---

### Step 1: init

```
/academic-wiki:wiki init academic
```

**What happens:**

1. Creates `~/ObsidianVault/03-Resources/academic/` with the 16-subdirectory tree.
2. Writes `CLAUDE.md` with the full schema (entity templates, naming conventions, log format).
3. Writes `wiki/index.md`, `log.md`, `.gitignore`, `qmd.yml`.
4. Initializes the wiki's own git repo and makes initial commit: `init: academic wiki`.
5. Adds `03-Resources/academic/` to the vault's `.gitignore` (if the vault is a git repo).
6. If qmd is available, creates a search collection and embeds the (empty) wiki.
7. Prints Web Clipper + Zotero setup hints.

**Verify:**

```bash
ls ~/ObsidianVault/03-Resources/academic/
git -C ~/ObsidianVault/03-Resources/academic log --oneline -1
```

Expected:

```
raw/  wiki/  outputs/  CLAUDE.md  log.md  .gitignore  qmd.yml
init: academic wiki
```

---

### Step 2: ingest a paper via arXiv ID

```
/academic-wiki:wiki ingest 1706.03762
```

Downloads via `agentic-rag-v2`, extracts via `ocr-papers-to-latex`, runs both dedup passes, derives `paper-id: vaswani-2017-attention`, saves `raw/papers/`, `raw/extracts/`, `raw/bib/`, commits.

**Verify:**

```bash
ls ~/ObsidianVault/03-Resources/academic/raw/extracts/
git -C ~/ObsidianVault/03-Resources/academic log --oneline -1
# ingest: vaswani-2017-attention
```

---

### Step 3: ingest via DOI (dedup in action)

Suppose the same paper also has a published DOI version:

```
/academic-wiki:wiki ingest 10.48550/arXiv.1706.03762
```

**What happens:** ingest checks identifiers — the `arxiv: "1706.03762"` field matches `vaswani-2017-attention`. Instead of creating a duplicate, it merges the new DOI into the existing paper's `identifiers:` frontmatter and exits:

```
Identifier match: doi 10.48550/arXiv.1706.03762 → vaswani-2017-attention (existing paper).
Merged identifiers. No new paper created.
```

If the source bytes also matched (source-sha), it would say:

```
This exact source was already ingested as vaswani-2017-attention. Skipping.
```

---

### Step 4: ingest a local PDF

```
/academic-wiki:wiki ingest ~/Downloads/someone-2025-paper.pdf
```

Routes to `ocr-papers-to-latex`. Metadata extracted from LaTeX/markdown output. All dedup passes run as normal.

---

### Step 5: ingest a new version

```
/academic-wiki:wiki ingest 1706.03762v5
```

Identifier match (`arxiv: "1706.03762"`, version-stripped) → version handler: saves `raw/papers/vaswani-2017-attention-v5.pdf`, updates `raw/extracts/vaswani-2017-attention.md`, appends to `.versions.yml`, updates `source-version: arxiv-v5`. No new `paper-id`.

---

### Step 6: add user notes for a paper

Drop a notes file before compiling — it gets folded into `## User Notes` on the paper page:

```bash
cat > ~/ObsidianVault/03-Resources/academic/raw/notes/vaswani-2017-attention.md << 'EOF'
# My notes on Attention Is All You Need

Key insight: multi-head attention attends to different subspaces simultaneously.
Scaled dot-product: softmax(QK^T / sqrt(d_k)) * V
Questions: does positional encoding generalize beyond fixed-length sequences?
EOF
```

The notes file is immutable — the LLM reads it but never overwrites it.

---

### Step 7: compile --paper-only (Wave 1)

```
/academic-wiki:wiki compile --paper-only
```

All uncompiled extracts → paper pages in `wiki/papers/`. Each page has full frontmatter (`paper-id`, `citation-key`, `type: paper`, `status`, `identifiers`, `references-raw`, `cites: []`, `tags`) and body sections `## Metadata` / `## Summary` / `## Key Contributions` / `## Methods` / `## Results` / `## Claims` / `## User Notes` / `## See Also`. No entity pages yet; `cites:` empty.

**Verify:**

```bash
ls ~/ObsidianVault/03-Resources/academic/wiki/papers/
git -C ~/ObsidianVault/03-Resources/academic log --oneline -1
# compile: 1 paper pages
```

---

### Step 8: compile (Wave 2, full)

After ingesting several papers:

```
/academic-wiki:wiki compile
```

Additional steps beyond Wave 1: extracts entity pages (`wiki/concepts/`, `wiki/methods/`, `wiki/open-problems/`), resolves `references-raw` → `cites:`, runs backlink audit (adds `[[wikilinks]]` where missing), writes cross-paper candidates to `outputs/reports/YYYY-MM-DD-promotion-candidates.md`. Nothing is auto-promoted.

**Verify:**

```bash
ls ~/ObsidianVault/03-Resources/academic/wiki/concepts/
ls ~/ObsidianVault/03-Resources/academic/outputs/reports/
```

---

### Step 9: query

```
/academic-wiki:wiki query "What is self-attention and how does it scale with sequence length?"
```

Phase 1 search reads `wiki/index.md` for candidate pages (Phase 2 uses qmd for large wikis). Synthesizes a prose answer with `[[paper-id]]` citations, files it to `wiki/queries/what-is-self-attention.md`, then prompts for promotion.

**Example answer format:**

> Self-attention, introduced in [[vaswani-2017-attention]], computes pairwise interactions between all positions in a sequence. The scaled dot-product mechanism has O(n²) complexity — a limitation explored in [[child-2019-sparse-transformer]]...

**Verify:**

```bash
cat ~/ObsidianVault/03-Resources/academic/wiki/queries/what-is-self-attention.md
git -C ~/ObsidianVault/03-Resources/academic log --oneline -1
# query: what-is-self-attention
```

---

### Step 10: promote a query answer

At the promotion prompt, answer `y` and choose a type (`concept`, `method`, `claim`, `result`, or `open-problem`). The file moves from `wiki/queries/` to `wiki/concepts/self-attention.md` with `type: concept`, `status: active`, `sources: [vaswani-2017-attention, ...]`.

---

### Step 11: review and promote a candidate

Open `outputs/reports/YYYY-MM-DD-promotion-candidates.md`. Each entry lists type, sources, and a synthesized statement. To promote, manually create the corresponding page in `wiki/claims/` or `wiki/results/`, or run a query asking to promote it.

---

### Step 12: lint

```
/academic-wiki:wiki lint
```

Saves a report to `outputs/reports/YYYY-MM-DD-lint.md` and prints a summary:

```
Lint report: outputs/reports/2026-04-16-lint.md
  Dead links:      3  (wikilinks pointing to nonexistent pages)
  Orphan pages:    2  (pages with no inbound links)
  Missing sections: 1  (pages missing required body sections)
  Index drift:     0
Recommended: run lint --fix-dead-links to auto-create 3 stub pages.
```

Fix dead links automatically:

```
/academic-wiki:wiki lint --fix-dead-links
```

Suggest where backlinks are missing (review required — not auto-applied):

```
/academic-wiki:wiki lint --suggest-backlinks
```

---

### Step 13: export-bibtex

First, tag papers for your project by editing the paper's frontmatter `tags:` in Obsidian or by running:

```bash
# In wiki/papers/vaswani-2017-attention.md, add project/rsma-survey-2025 to tags
```

Then export:

```
/academic-wiki:wiki export-bibtex --project rsma-survey-2025 --label rsma-survey
```

Output written to `outputs/bib/2026-04-16-rsma-survey.bib`. The command also reports:

```
Exported 12 entries to outputs/bib/2026-04-16-rsma-survey.bib
  bib-incomplete: 2 papers (manual fix required — see raw/bib/)
  missing .bib:   0
```

Other selector forms:

```
# All papers in a field since a date
/academic-wiki:wiki export-bibtex --field nlp --since 2024-01-01

# Ad-hoc set of paper-ids
/academic-wiki:wiki export-bibtex --keys vaswani-2017-attention,bahdanau-2014-neural --label icml-rebuttal

# Natural-language query — wiki finds the papers
/academic-wiki:wiki export-bibtex --query "sparse attention methods" --label sparse-attn
```

Fix a `bib-incomplete` entry by editing `raw/bib/<paper-id>.bib`, removing the `% bib-incomplete: true` comment, and filling in the missing fields.

---

### Step 14: snapshot

```
/academic-wiki:wiki snapshot icc-2026-submission
```

Requires a clean working tree. Appends a log entry, commits, then creates annotated tag `snapshot/icc-2026-submission`:

```
Tagged snapshot/icc-2026-submission at a1b2c3d.
Revisit with: git -C ~/ObsidianVault/03-Resources/academic checkout snapshot/icc-2026-submission
List all snapshots: git -C ~/ObsidianVault/03-Resources/academic tag --list 'snapshot/*'
```

To return from detached HEAD: `git -C ~/ObsidianVault/03-Resources/academic checkout main`.

---

### Step 15: remove (careful)

```
/academic-wiki:wiki remove academic
```

The plugin shows what will be deleted (commit count, tag count) and prompts:

```
This will PERMANENTLY delete wiki 'academic' and its git history at ~/ObsidianVault/03-Resources/academic.
Type the wiki name exactly to confirm (or anything else to cancel):
```

Type `academic` to confirm. Type anything else to cancel. All git history and snapshots are lost.

---

## Part 5: Obsidian Integration Tips

- **Graph view** (Ctrl/Cmd+G) visualizes the link topology. Orphan nodes and dense clusters are immediately visible. After a Wave 2 compile, the graph shows papers connected through shared concepts and methods.
- **Dataview:** `TABLE title, year, venue FROM "03-Resources/academic/wiki/papers" SORT year DESC` — dynamic paper tables from frontmatter.
- **Web Clipper:** destination `03-Resources/academic/raw/papers/`, filename `{{date:YYYY-MM-DD}}-{{title}}`. Run `ingest` after clipping.
- **Marp slides:** add `marp: true` to frontmatter and export via the Obsidian Marp plugin.

---

## Part 6: Advanced Usage

**Multiple wikis:** each is independent with its own git repo and qmd collection. Run commands from inside the target wiki root so active wiki detection resolves unambiguously.

**Large wikis (1000+ papers):** qmd is essential for Phase 2 search. Verify: `ls ~/.claude/plugins/data/academic_wiki/node_modules/.bin/qmd`.

**Contradiction handling:** `[!WARNING]` callouts flag conflicting findings. They are NOT auto-resolved — review in Obsidian and manually edit or create a `wiki/open-problems/` page.

**Compounding queries:** filed answers enrich `wiki/queries/`; promoted answers become concept/method pages reachable by future queries. The graph densifies over time.

---

## Part 7: Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `/academic-wiki:wiki` not found | Plugin not installed | `/plugin install /path/to/academic_wiki` |
| `ingest` fails on arXiv ID | `agentic-rag-v2` MCP unavailable | Install the MCP or place the PDF in `raw/papers/` and ingest the local path |
| `ingest` fails on local PDF | `ocr-papers-to-latex` skill missing | Install the skill |
| Same paper ingested twice | Second ingest was a new version or a genuinely new source | Check: did dedup run? See `source-sha` and `identifiers:` in `raw/extracts/<paper-id>.md` |
| `paper-id` looks wrong (e.g., `unknown-2026-paper`) | Metadata could not be extracted | Edit `raw/extracts/<paper-id>.md` frontmatter manually; re-run compile |
| `compile` creates wrong entity pages | LLM misread the paper | Edit the page manually in Obsidian; the next compile preserves edits (conflict policy) |
| BibTeX missing or incomplete | Paper ingested without available BibTeX | Fix `raw/bib/<paper-id>.bib` manually; remove `% bib-incomplete: true` line |
| Lock held (`LockHeld` error) | Another operation running, or a previous one crashed | The lock auto-recovers after the process exits. If stale, delete `<wiki-root>/.lock` manually |
| `snapshot` fails: uncommitted changes | Dirty working tree | Run compile or ingest to completion, or `git -C <wiki-root> status` to see what's uncommitted |
| `snapshot` fails: tag already exists | Label reused | Use a different label or delete old tag: `git -C <wiki-root> tag -d snapshot/<label>` |
| `export-bibtex` reports `bib-incomplete` | Stub BibTeX at ingest time | Edit `raw/bib/<paper-id>.bib` — fill in fields, remove the `% bib-incomplete: true` line |

---

## Part 8: Where to Learn More

- **Spec:** `docs/superpowers/specs/2026-04-16-academic-wiki-design.md` — full design, all schemas, dedup algorithm, update conflict policy
- **Plan:** `docs/superpowers/plans/2026-04-16-academic-wiki-plan.md` — implementation phases and task breakdown
- **CLAUDE.md** at your wiki root — the authoritative schema the LLM follows on every operation
- **Skill references** at `skills/wiki/references/`:
  - `ingestion-routing.md` — input-type autodetection and dedup pipeline
  - `compilation-guide.md` — Wave 1 and Wave 2 compile steps
  - `promotion-rules.md` — cross-paper candidate detection and promotion
  - `bibtex-handling.md` — BibTeX conventions and export flow
  - `entity-schemas.md` — verbatim frontmatter schemas for all page types
