# Academic Wiki — Design Spec

**Date:** 2026-04-16
**Status:** Approved for implementation planning
**Plugin name (tentative):** `academic-wiki`
**Plugin location:** `/home/tung491/Work/academic_wiki/`
**Wiki data location:** `~/ObsidianVault/03-Resources/academic/`

---

## 1. Purpose and Scope

A new Claude Code plugin that implements the Karpathy LLM-Wiki pattern specialized for academic data (journal PDFs, arXiv papers, conference proceedings, and the user's own reading notes). Designed as a long-term personal knowledge base across multiple research fields, with cross-paper synthesis, BibTeX export for paper writing, and Obsidian as the front-end viewer.

The `llm-wiki` plugin at `./llm-wiki/` is kept as reference and remains unmodified. This plugin is independent in code and lifecycle.

### 1.1 Non-goals

- Multi-wiki support beyond the default `academic/` wiki (design is monolithic with tag-based projections).
- Custom MCP backend for search — user will build that separately.
- Branch-based hypothesis tracking (contradictions handled inline via `[!WARNING]` callouts).
- Blob-level git plumbing (see §1.2 for evaluation of the git proposal).
- Web UI, API, or non-Claude-Code surface.
- Automated LLM-quality evaluation (subjective; out of test scope).

### 1.2 Evaluation of the git-as-knowledge-backend proposal

From `refs/git_proposal.md` — adopt the selectively useful parts, skip the rest.

| Proposal idea | Verdict |
|---|---|
| Blob = atomic knowledge unit | Skip — markdown files already give sufficient granularity |
| Tree = category/index | Already baked in — directories are git trees |
| Commit = provenance event | Already baked in via auto-commit; codify message format (see §7) |
| Branch = competing hypotheses | Skip as primary feature — `[!WARNING]` callouts handle contradictions inline |
| Merge = synthesis | Skip (follows from skipping branches) |
| Tag = stable snapshot | **Adopt** — new `snapshot <label>` command |
| Content dedup via SHA | Skip — wrong dedup key; use citation keys instead |
| Anti-repetition memory | Soft-adopt via `log.md` |

## 2. Architecture

### 2.1 Plugin repo layout

```
academic_wiki/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── commands/
│   └── wiki.md                               # /academic-wiki:wiki entrypoint
├── skills/
│   └── wiki/
│       ├── SKILL.md
│       └── references/
│           ├── entity-schemas.md
│           ├── tag-taxonomy.md
│           ├── ingestion-routing.md
│           ├── promotion-rules.md
│           ├── bibtex-handling.md
│           └── compilation-guide.md
├── scripts/
│   ├── install-deps.sh
│   ├── deps-version.txt
│   ├── lint-wiki.py
│   └── bibtex-export.py
├── hooks/
│   └── hooks.json                            # SessionStart hook
├── refs/                                     # existing
├── llm-wiki/                                 # existing, untouched
├── docs/
│   └── superpowers/specs/                    # this doc lives here
├── README.md
├── WALKTHROUGH.md
└── LICENSE
```

### 2.2 Wiki data layout (`~/ObsidianVault/03-Resources/academic/`)

```
academic/
├── raw/                              # immutable; LLM reads, never edits
│   ├── papers/                       # source files: <key>.pdf / .tex / .html / .md
│   ├── extracts/                     # LLM-readable text/LaTeX extracts: <key>.md
│   ├── bib/                          # per-paper BibTeX: <key>.bib
│   ├── figures/                      # per-paper figures: <key>/fig-N.png
│   └── notes/                        # user's manual reading notes: <key>.md (optional)
├── wiki/                             # LLM-owned synthesis
│   ├── index.md                      # catalog
│   ├── papers/                       # <citation-key>.md
│   ├── concepts/                     # <slug>.md
│   ├── methods/                      # <slug>.md
│   ├── open-problems/                # <slug>.md
│   ├── claims/                       # cross-paper only
│   ├── results/                      # cross-paper only
│   ├── authors/                      # on demand
│   ├── venues/                       # on demand
│   └── queries/                      # filed query answers
├── outputs/
│   ├── reports/                      # YYYY-MM-DD-lint.md
│   └── bib/                          # YYYY-MM-DD-<label>.bib
├── CLAUDE.md                         # authoritative schema
├── log.md                            # append-only ops log
├── .gitignore
└── qmd.yml                           # optional; used if qmd is installed
```

### 2.3 Key architectural decisions

1. **`raw/papers/` + `raw/extracts/` split.** PDF/HTML stays in `papers/`; LLM-readable extract goes to `extracts/`. The LLM reads from `extracts/` during compile — not the PDF directly.
2. **User notes (`raw/notes/<key>.md`) live in `raw/`, not `wiki/`.** They are immutable source. Wiki paper pages reference them via a "User Notes" section; they are never overwritten or embedded.
3. **`wiki/` is subdivided by entity type.** Keeps the directory navigable at 1000+ pages. Obsidian wikilinks resolve globally, so `[[slug]]` still works across subfolders.
4. **`authors/` and `venues/` are created on demand only** — not automatically. Most papers just list authors in frontmatter without triggering a page.
5. **`outputs/` is split** — `reports/` for lint, `bib/` for BibTeX exports. Both dated, both kept versioned.
6. **Obsidian ergonomics preserved**: graph view, Dataview queries, Marp slide export all work because everything is standard markdown with standard wikilinks.

## 3. Entity Schemas

All pages use YAML frontmatter. All filenames are lowercase-kebab-case except paper pages, which use the citation key verbatim.

### 3.1 Primary entities

**paper** — `wiki/papers/<citation-key>.md`

```yaml
---
date: YYYY-MM-DD
type: paper
status: queued | skimmed | read | deep-read
citation-key: vaswani2017attention
title: "Attention Is All You Need"
authors: [ashish-vaswani, noam-shazeer]
year: 2017
venue: nips
doi: 10.xxx/xxx
arxiv: 1706.03762
url: https://...
bib-file: raw/bib/vaswani2017attention.bib
extract: raw/extracts/vaswani2017attention.md
notes: raw/notes/vaswani2017attention.md         # optional — only if user wrote notes
figures: raw/figures/vaswani2017attention/       # optional
cites: [bahdanau2014neural, cho2014learning]     # citation keys this paper references
tags: [field/nlp, method/attention, year/2017, venue/nips]
---
```

Body sections: `Metadata` / `Summary` / `Key Contributions` / `Methods` / `Results` / `Claims` / `User Notes` / `See Also`. User-notes section is auto-filled from `raw/notes/<key>.md` if present.

**concept** — `wiki/concepts/<slug>.md`

```yaml
---
date: YYYY-MM-DD
type: concept
status: active | stale
sources: [vaswani2017attention, ...]
tags: [field/..., ...]
---
```

Body: `Definition` / `Details` / `See Also` / `Counter-Arguments and Gaps`.

**method** — `wiki/methods/<slug>.md`

```yaml
---
date: YYYY-MM-DD
type: method
status: active | deprecated | contested
sources: [citation-key-1, citation-key-2]
related-methods: [other-method-slug]
tags: [field/..., method/..., ...]
---
```

Body: `Definition` / `How It Works` / `Results Using This Method` / `Known Limitations` / `See Also` / `Counter-Arguments and Gaps`.

**open-problem** — `wiki/open-problems/<slug>.md`

```yaml
---
date: YYYY-MM-DD
type: open-problem
status: open | partially-resolved | resolved | disputed
sources: [citation-key-1, ...]
resolved-by: citation-key                        # optional
tags: [field/..., ...]
---
```

Body: `Statement` / `Why It Matters` / `Current Approaches` / `What's Missing` / `See Also`.

**result** — `wiki/results/<slug>.md` (cross-paper only)

```yaml
---
date: YYYY-MM-DD
type: result
status: replicated | contested | preliminary | unverified
sources: [citation-key-1, citation-key-2, ...]
refutes: [other-result-slug]
supports: [claim-slug]
tags: [field/..., method/..., ...]
---
```

Body: `Statement` / `Evidence` / `Conditions` / `Caveats` / `See Also`.

**claim** — `wiki/claims/<slug>.md` (cross-paper only)

```yaml
---
date: YYYY-MM-DD
type: claim
status: established | contested | fringe | deprecated
sources: [citation-key-1, ...]
evidence-for: [result-slug, ...]
evidence-against: [result-slug, ...]
tags: [field/..., ...]
---
```

Body: `Statement` / `Evidence For` / `Evidence Against` / `Open Questions` / `See Also`.

### 3.2 Secondary entities (on demand)

**author** — `wiki/authors/<slug>.md`

```yaml
---
date: YYYY-MM-DD
type: author
orcid: 0000-...
affiliation: ...
papers: [citation-key-1, citation-key-2, ...]
tags: [field/..., person]
---
```

**venue** — `wiki/venues/<slug>.md`

```yaml
---
date: YYYY-MM-DD
type: venue
venue-type: conference | journal | workshop | preprint-server
papers: [citation-key-1, ...]
tags: [field/...]
---
```

### 3.3 Operational entity

**query-output** — `wiki/queries/<slug>.md`

```yaml
---
date: YYYY-MM-DD
type: query-output
question: "<original question>"
status: filed | promoted
sources: [citation-key-1, ...]
tags: [field/...]
---
```

### 3.4 Cross-schema conventions

1. **`sources:` vs `cites:`**: `cites:` is only on paper pages and lists citation keys that paper references. `sources:` is on every non-paper entity and lists papers that inform that page.
2. **Status fields are entity-specific.** Different entity types have different meaningful states.
3. **`cited-by:` is never stored.** Dataview computes it on demand from `cites:` fields.
4. **Result/claim pages exist only when cross-paper.** Single-paper results/claims stay inline in the paper page until promoted.
5. **User notes are referenced, not copied.** The paper page's "User Notes" section links and summarizes `raw/notes/<key>.md`; it never embeds or overwrites.

## 4. Tag Taxonomy

### 4.1 Reserved prefixes

| Prefix | Purpose | Examples | Auto-applied |
|---|---|---|---|
| `field/*` | Major research field | `field/wireless-comms`, `field/nlp` | Yes (during compile) |
| `subfield/*` | Narrower slice | `subfield/rsma`, `subfield/attention` | Yes (during compile) |
| `method/*` | Technique discussed | `method/rsma`, `method/transformer` | Yes (during compile) |
| `year/*` | Publication year | `year/2017`, `year/2024` | Yes (on paper creation) |
| `venue/*` | Venue slug | `venue/nips`, `venue/globecom` | Yes (on paper creation) |
| `project/*` | User's research project | `project/rsma-survey-2025` | **No — user-only** |
| `user/*` | Personal workflow flag | `user/to-reread`, `user/must-cite` | **No — user-only** |

### 4.2 Free-form tags

Allowed without a prefix. Examples: `foundational`, `survey`, `tutorial`, `position-paper`, `benchmark`, `reproducibility-study`.

### 4.3 Rules

1. Paper pages get `field/*`, `subfield/*`, `method/*`, `year/*`, `venue/*` from the LLM during compile.
2. Concept / method / open-problem / claim / result pages get `field/*` and `subfield/*` aggregated from their `sources:` paper pages.
3. `project/*` and `user/*` are user-driven; the LLM may suggest them but never applies them silently.
4. Lint fails if any paper / concept / method / open-problem / claim / result lacks ≥1 `field/*` tag.
5. Tag renames are a manual concern for now — future tooling may automate.

## 5. Command Surface

Eight commands, invoked via `/academic-wiki:wiki <operation> [<args>]`.

### 5.1 `init [<name>]`

Scaffolds a new wiki at `~/ObsidianVault/03-Resources/<name>/` (default `academic`).

1. Abort if target exists.
2. Create full directory tree (§2.2).
3. Write `CLAUDE.md` with the complete schema (§§2–7 inline, ~800 lines).
4. Write `wiki/index.md`, `log.md`, `.gitignore`, `qmd.yml`.
5. Commit: `init: <name> wiki`.
6. If qmd available: `qmd collection add` + `qmd embed`.
7. Print Web Clipper + Zotero export setup hints.

### 5.2 `ingest <path|id|url>`

Saves a source to `raw/`, generates extract, stubs BibTeX. Does **not** create wiki pages.

**Input routing** (autodetect):

- `^\d{4}\.\d{4,5}(v\d+)?$` → arXiv ID → `mcp__agentic-rag-v2__download_arxiv`
- `^10\.\d+/.+` → DOI → `mcp__agentic-rag-v2__doi2content`
- `arxiv.org/abs/...` or `arxiv.org/pdf/...` → extract ID → arXiv handler
- Publisher URL → `mcp__agentic-rag-v2__fetch_publisher_html`
- Local `.pdf` → `ocr-papers-to-latex` skill
- Local `.md` → treat as pre-extracted
- Anything else → ask user

**Pipeline**:

1. Route input, acquire raw content.
2. Metadata extraction:
    - First-author last name (lowercased, ASCII-folded: `García` → `garcia`).
    - 4-digit publication year.
    - Title's first meaningful word (lowercased; skip `a`/`an`/`the` and numerals).
3. Citation key: `<lastname><year><firstword>`. Example: `vaswani2017attention`.
4. Collision check: if key exists, append suffix letter (`vaswani2017attentiona`).
5. If extraction fails (scan without OCR-able text, garbage metadata): use fallback key `unknown-<current-year>-<filename-slug>` (the same fallback key is used for ALL file basenames in step 6, not only the extract); set `metadata-incomplete: true` in frontmatter; log for lint.
6. Save all files with `<key>` as the common basename — consistent across `raw/papers/<key>.*`, `raw/extracts/<key>.md`, `raw/bib/<key>.bib`, `raw/figures/<key>/`. The wiki always identifies a paper by this one key.
7. If BibTeX unavailable, stub `@misc` entry with `bib-incomplete: true`.
8. Append to `log.md`: `## [YYYY-MM-DD] ingest | <key>`.
9. Commit: `ingest: <key>`.
10. Print: `Source saved as <key>. Run wiki compile <key> to integrate.`

### 5.3 `compile [<key>]`

Reads raw sources, creates/updates wiki pages, extracts entities, auto-promotes cross-paper claims/results.

1. Identify sources: given `<key>` or all keys in `raw/extracts/` without a matching `wiki/papers/<key>.md`.
2. For each source:
    - Read `raw/extracts/<key>.md` + `raw/notes/<key>.md` if present.
    - Write/update `wiki/papers/<key>.md` per §3.1.
    - Entity extraction: identify concepts, methods, open-problems. Create/update `wiki/concepts/<slug>.md`, `wiki/methods/<slug>.md`, `wiki/open-problems/<slug>.md`. Append citation key to each page's `sources:`.
    - Claims/results: draft as inline sections in the paper page. Compare against other papers' claim/result sections using LLM judgment (semantic equivalence, not regex; the LLM decides if "attention is quadratic in sequence length" and "self-attention complexity grows as O(n²)" describe the same claim). **Auto-promote** to standalone `wiki/claims/<slug>.md` or `wiki/results/<slug>.md` when equivalence found in ≥1 other paper; lint report documents new pages.
    - `cites:` extraction: LLM reads bibliography section of the extract, fuzzy-matches each reference against existing `wiki/papers/`. Unmatched entries logged in lint as candidate new ingests.
    - Backlink audit: `grep -rln "<new page title>" wiki/` and add wikilinks where missing.
3. Update `wiki/index.md` (sectioned by `field/*` tag).
4. Append to `log.md`: `## [YYYY-MM-DD] compile | N papers → M pages`.
5. Commit: `compile: <summary>`.
6. If qmd available: `qmd embed --collection academic`.

### 5.4 `query <question>`

Answers using the wiki; files the answer.

1. Find relevant pages: qmd if installed, else `index.md` + ripgrep.
2. Read relevant pages; follow one level of wikilinks if targets look relevant.
3. Synthesize answer with `[[wikilinks]]` as citations.
    - Default: prose.
    - If question contains "compare" / "table": markdown table.
    - If question contains "slides": Marp markdown.
4. File answer to `wiki/queries/<slug>.md` (mandatory, no prompt).
5. Prompt: `"Promote to a first-class page? If yes, which type: concept / method / open-problem / claim / result?"` If promoted, move to appropriate subdirectory with appropriate frontmatter schema.
6. Append to `log.md`; commit: `query: <slug>` (and `promote: <slug> to <type>` if promoted).

### 5.5 `lint`

Audits wiki health via `scripts/lint-wiki.py` + LLM suggestions.

**Deterministic checks** (Python):

- Dead links (`[[foo]]` with no `foo.md`) — create stubs using appropriate template.
- Orphan pages (no inbound links) — list, suggest where to add inbound links.
- Missing `field/*` tag on any paper / concept / method / open-problem / claim / result.
- Missing frontmatter fields per entity-type schema.
- Stale pages: (a) any page with `status: stale` whose frontmatter `date:` is >90 days old; (b) any `concept` or `method` page whose `date:` is >180 days old regardless of status (suggesting review even if not explicitly stale).
- Missing "Counter-Arguments and Gaps" on concept / method pages.
- Contradictions (`[!WARNING]` markers) — list.
- Invalid `cites:` keys (no matching file in `wiki/papers/`) — flag as candidate new ingests.
- Missing BibTeX (paper page has no corresponding `raw/bib/<key>.bib` or `bib-incomplete: true`).
- Index drift (`wiki/index.md` vs actual files).

**LLM suggestions**: 3–5 questions the wiki can't yet answer well, 2–3 sources that would strengthen gaps.

Save report to `outputs/reports/YYYY-MM-DD-lint.md`; append to `log.md`; commit.

### 5.6 `export-bibtex <selectors>`

Generates a consolidated `.bib` from a subset of paper pages.

**Selectors** (≥1 of the first six required; combinable with AND semantics):

- `--project <slug>` — papers tagged `project/<slug>`.
- `--field <slug>` — papers tagged `field/<slug>`.
- `--tag <tag>` — full tag including prefix.
- `--query <text>` — hybrid search over paper pages.
- `--keys <key1,key2,...>` — explicit list.
- `--since YYYY-MM-DD` — filter by ingest date.
- `--label <string>` — optional override for the output filename label.

**Label resolution** (for the output filename):

1. If user passed `--label <string>`, use it verbatim. (Add `--label` to the selector list.)
2. Else: use the first non-empty selector value in this fixed priority order — `project`, `field`, `tag`, `query`, `keys[0]`, `since` — slugified.
3. Example: `export-bibtex --field wireless-comms --since 2024-01-01` → `outputs/bib/2026-04-16-wireless-comms.bib`.

**Pipeline**:

1. Resolve selectors → list of paper pages (AND semantics across multiple selectors).
2. Concatenate `raw/bib/<key>.bib` contents into `outputs/bib/YYYY-MM-DD-<label>.bib`.
3. Report: `N papers exported. M have bib-incomplete flag (listed below).`
4. Append to `log.md`; commit: `export: <label> (<N> papers)`.

### 5.7 `snapshot <label>`

Tags the wiki state for reproducibility.

1. `git -C ~/ObsidianVault tag academic-wiki/<label>` at current HEAD.
2. Append to `log.md`: `## [YYYY-MM-DD] snapshot | <label>` with SHA.
3. Print: `Tagged as academic-wiki/<label> at <SHA>. Revisit with: git -C ~/ObsidianVault checkout academic-wiki/<label>`.

### 5.8 `remove <name>`

Deletes a wiki after confirmation.

1. Verify target exists.
2. Confirm: `"This will permanently delete '<name>'. Proceed? (y/n)"`.
3. Remove qmd collection if present.
4. `git rm -rf` + commit: `remove: <name> wiki`.

## 6. Search Strategy

Single `find_pages(query) → list[path]` abstraction with two backends:

### 6.1 Phase 1 — index.md + ripgrep (default, no dependencies)

LLM reads `wiki/index.md` first to identify candidate matches by title/description, then uses ripgrep for content matching. Works for ≤100 papers without external tools.

### 6.2 Phase 2 — qmd (optional, auto-installed)

If `${CLAUDE_PLUGIN_DATA}/node_modules/.bin/qmd` exists and is executable, use qmd's hybrid BM25 + vector search via `qmd query "<question>" --collection academic`. Falls back to Phase 1 if qmd crashes or collection is corrupt.

### 6.3 Future: custom MCP

User plans to build a custom MCP modeled on `agentic-rag-v2`. Not built by this plugin. The `find_pages` abstraction is designed so adding an MCP backend later is a two-line change in `SKILL.md` (check MCP tool registry first, fall through to qmd, then Phase 1).

## 7. CLAUDE.md Contract

The wiki-root `CLAUDE.md` is the authoritative contract the LLM reads on every operation. Self-contained — readable without reference to the plugin source. Sections:

1. Directory layout (§2.2 inline).
2. Citation key convention (§5.2 inline).
3. Entity types (§3 inline).
4. Tag taxonomy (§4 inline).
5. Naming conventions.
6. Log format: `## [YYYY-MM-DD] <op> | <subject>` where `<op> ∈ {init, ingest, compile, query, promote, lint, export, snapshot, remove}`.
7. Commit message format: `<op>: <subject>`, optionally followed by a one-line "why" body.
8. Cross-reference rules (wikilink density, backlink audit, contradiction callouts).
9. Ingest rules (§5.2 step-by-step).
10. Compile rules (§5.3 step-by-step, including auto-promotion).
11. Query rules (§5.4).
12. Lint rules (§5.5 complete check list).
13. Export-bibtex rules (§5.6).
14. Snapshot rules (§5.7 tag format).
15. Search strategy (§6 with fallback chain).

Expected length: ~800 lines. Reference doc, not linear reading material.

## 8. Error Handling

| Situation | Action |
|---|---|
| No active wiki found | List candidates in `~/ObsidianVault/03-Resources/*/wiki`. Default to `academic/` if present; else prompt. |
| PDF has no extractable text | Route to `ocr-papers-to-latex` with OCR mode; if still fails, save PDF as-is, set `extract-failed: true`, warn, don't block. |
| Metadata extraction fails | Fallback filename `unknown-YYYY-<filename-slug>.md`; set `metadata-incomplete: true`; lint surfaces. |
| arXiv/DOI API failure | Retry once with backoff. If still failing, log error; suggest manual ingest. |
| Citation-key collision | Append suffix letter `a`, `b`, ...; never overwrite. |
| BibTeX missing | Stub minimal `@misc`; set `bib-incomplete: true`. |
| Git commit fails | Warn with git output; do not retry; do not use `--no-verify`. User resolves manually. |
| qmd crashes / corrupt index | Fall back to Phase 1 search for that operation; warn once per session. |
| Extract exists, paper page missing | Treat as uncompiled; next `compile` picks up. |
| Paper page exists, extract missing | Lint warning: re-run ingest on the source. |
| Invalid `cites:` key | Lint: "candidate new ingests"; do not auto-ingest. |
| `compile` targets non-existent key | Abort: `No extract found at raw/extracts/<key>.md. Did you run wiki ingest first?` |
| Inconsistent tag use | Lint: list pages, suggest rename. (No automatic rename yet.) |
| Large source (>1MB extract) | Warn; entity extraction may be incomplete; proceed. |

## 9. Dependencies

### 9.1 Required

- Python 3.10+ (for `lint-wiki.py`, `bibtex-export.py`)
- git with `user.name` and `user.email` configured
- Obsidian vault at `~/ObsidianVault/03-Resources/`

### 9.2 Auto-installed via SessionStart hook

- Node.js 18+ (checked, not installed — prompted if missing)
- qmd → `${CLAUDE_PLUGIN_DATA}/node_modules/.bin/qmd`
- marp-cli (optional, for Marp slide export)

Sentinel file `~/.claude/plugins/data/academic-wiki/.deps-ok` gates install; missing triggers retry on next SessionStart.

### 9.3 Assumed present (not installed by plugin)

- `ocr-papers-to-latex` skill — user's existing skill
- `mcp__agentic-rag-v2__*` tools — user's existing MCP server
- Obsidian app with Dataview plugin (recommended) and Git plugin (recommended)

## 10. Testing Strategy

### 10.1 Python unit tests

- `scripts/lint-wiki.py`: dead link, orphan, missing field tag, missing counter-arguments, stale, invalid cites key, missing bibtex, index drift.
- `scripts/bibtex-export.py`: each selector, combination semantics, since filter, explicit key list, collision of `--project` + `--field`.

### 10.2 Integration fixture

`test-fixtures/mini-wiki/` with 3–5 hand-crafted papers:
- 1 arXiv paper (identifier-based)
- 1 DOI paper
- 1 local PDF
- 1 with user notes present
- 1 with `bib-incomplete: true`

End-to-end runs of each command against the fixture, compared against expected state.

### 10.3 Manual smoke tests

Documented in `WALKTHROUGH.md` — full end-to-end run on a real paper: ingest → compile → query → lint → export-bibtex → snapshot.

### 10.4 Explicit non-tests

LLM synthesis quality is not tested automatically (subjective; better evaluated by reading). Tests cover plumbing: routing, filenames, frontmatter correctness, commit messages, file structure.

## 11. Rollout Plan

Three waves. Wave 1 must work end-to-end before starting Wave 2.

### 11.1 Wave 1 — Core loop

- `init`
- `ingest` (full routing, metadata extraction, citation-key generation)
- `compile` (paper pages, entity extraction, auto-promotion, backlink audit, `cites:` population)
- `query` (Phase 1 search, synthesis, file-to-queries)

**Exit criterion**: full ingest → compile → query → promote flow works on ≥5 real papers.

### 11.2 Wave 2 — Maintenance and output

- `lint`
- `export-bibtex`
- `snapshot`

### 11.3 Wave 3 — Polish

- `remove`
- `WALKTHROUGH.md` analogous to llm-wiki's
- Marp slide export convenience
- Tooling gaps surfaced during Wave 1/2 (e.g., `rename-key`, `merge-duplicate-papers` — not yet in scope)

## 12. Open Questions and Future Work

Flagged explicitly, not blockers for implementation:

1. **Tag rename tool** — no automatic rename today; lint surfaces inconsistencies, user fixes manually.
2. **Custom MCP backend** — user will build separately; plugin's `find_pages` abstraction is MCP-ready.
3. **Cross-wiki references** — if user later creates a sibling wiki (e.g., `methods-notebook/`), referencing between them is out of scope here.
4. **Branch-based hypothesis tracking** — rejected for primary design; may be adopted later as user-discretion pattern.
5. **Figure-level search** — `get_image_path` exists in `agentic-rag-v2`; not wired into this plugin's query flow yet.

---

## Appendix A — Summary of user decisions

| Question | Answer |
|---|---|
| Scope | B — new plugin, `llm-wiki/` untouched as reference |
| Use case | B — long-term personal KB across a field, but with richer entity types |
| Entity types (top tier) | concept, method, open-problem, paper, result, claim |
| Source shape | C — mix of local PDFs + identifiers |
| Notes workflow | (iii) — sometimes manual notes, sometimes LLM-only |
| Wiki structure | C — monolithic with tag-based projections |
| Wiki data location | α — inside Obsidian vault |
| MCP integration | B — wiki self-contained; custom MCP later |
| Scale plan | D — small now, designed to grow fast |
| Math | `$...$` and `$$...$$`, Obsidian-native |
| BibTeX | Per-paper `.bib` files in `raw/bib/` |
| Citation key | `<lastname><year><firstword>`, BibTeX-native style |
| Git proposal adoption | Tags only (`snapshot` command); commit-message format codified |
| Tag taxonomy | `field/`, `subfield/`, `method/`, `year/`, `venue/` auto-applied; `project/`, `user/` user-only |
| Metadata-extraction fallback | Filename-derived + lint flag, no interactive prompt |
| Compile auto-promotion | Yes (silent, lint-reported) |
| Search phases | index.md + qmd only for now; no custom MCP yet |
| Testing | Unit + fixture + manual smoke; no LLM-quality tests |
| Rollout | Core loop → maintenance → polish |
