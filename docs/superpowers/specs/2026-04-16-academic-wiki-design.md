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

- Multi-wiki use of this plugin in practice (intended to be used as a single `academic/` wiki with tag-based projections). The `init` command still accepts a `<name>` argument so the plugin is technically capable of scaffolding other wikis, but the design is not optimized for maintaining more than one simultaneously.
- Custom MCP backend for search — user will build that separately.
- Branch-based hypothesis tracking (contradictions handled inline via `[!WARNING]` callouts).
- Blob-level git plumbing for knowledge units (see §1.2 for evaluation of the git proposal).
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
| Content dedup via SHA | **Partial adopt** — SHA is wrong as a knowledge-unit identifier, but a SHA-256 over source files is useful for duplicate-source detection (e.g., the same PDF ingested twice). Stored as `source-sha:` on raw-side metadata and checked by `ingest`. Identity of papers, not bytes, is handled by a separate `paper-id` + `identifiers:` model (see §3). |
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

The wiki is **its own git repository** (nested inside the Obsidian vault), not part of the vault's git history. This gives clean, atomic snapshots of only wiki state, independent of unrelated vault changes. See §2.3 for rationale and §5.7 for snapshot semantics.

```
academic/                             # self-contained git repo (nested in vault)
├── .git/                             # the wiki's own git history
├── raw/                              # immutable; LLM reads, never edits
│   ├── papers/                       # source files: <paper-id>.pdf / .tex / .html / .md
│   ├── extracts/                     # LLM-readable text/LaTeX extracts: <paper-id>.md
│   ├── bib/                          # per-paper BibTeX: <paper-id>.bib
│   ├── figures/                      # per-paper figures: <paper-id>/fig-N.png
│   └── notes/                        # user's manual reading notes: <paper-id>.md (optional)
├── wiki/                             # LLM-owned synthesis
│   ├── index.md                      # catalog
│   ├── papers/                       # <paper-id>.md (paper-id is the canonical key; see §3.1)
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
├── .lock                             # advisory lockfile; prevents concurrent mutating ops
├── .gitignore
└── qmd.yml                           # optional; used if qmd is installed
```

The vault's own `.git` (if present) should ignore this nested repo. `init` writes a `.gitignore` entry in the vault root if it doesn't already exclude `03-Resources/<name>/`.

### 2.3 Key architectural decisions

1. **Wiki is its own git repo** (nested at `~/ObsidianVault/03-Resources/academic/.git/`). Commits capture only wiki state, independent of unrelated vault changes. Snapshots (tags) are clean. Concurrent mutations are serialized via an advisory `.lock` file (see §8).
2. **`paper-id` is the canonical key**, not `citation-key`. `paper-id` is a stable internal identifier assigned on first ingest. The human-facing BibTeX citation key is derived from metadata and is an output/export field — it can change without breaking the wiki (§3.1). This is the fix for "same paper ingested via arXiv ID and via DOI" deduplication.
3. **`raw/papers/` + `raw/extracts/` split.** PDF/HTML stays in `papers/`; LLM-readable extract goes to `extracts/`. The LLM reads from `extracts/` during compile — not the PDF directly.
4. **User notes (`raw/notes/<paper-id>.md`) live in `raw/`, not `wiki/`.** They are immutable source. Wiki paper pages reference them via a "User Notes" section; they are never overwritten or embedded.
5. **`wiki/` is subdivided by entity type.** Keeps the directory navigable at 1000+ pages. Obsidian wikilinks resolve globally, so `[[slug]]` still works across subfolders.
6. **`authors/` and `venues/` are created on demand only** — not automatically. Most papers just list authors in frontmatter without triggering a page.
7. **`outputs/` is split** — `reports/` for lint, `bib/` for BibTeX exports. Both dated, both kept versioned.
8. **Obsidian ergonomics preserved**: graph view, Dataview queries, Marp slide export all work because everything is standard markdown with standard wikilinks.

## 3. Entity Schemas

All pages use YAML frontmatter. All filenames are lowercase-kebab-case except paper pages, which use the `paper-id` verbatim (see §3.1). Slug rules are in §3.5; update/conflict policy in §3.6.

### 3.1 Primary entities

**paper** — `wiki/papers/<paper-id>.md`

```yaml
---
paper-id: vaswani-2017-attention            # canonical internal ID (stable, never rewrites)
citation-key: vaswani2017attention          # derived, used for BibTeX export; may change
type: paper
status: queued | skimmed | read | deep-read
created: YYYY-MM-DD                         # first ingest date
updated: YYYY-MM-DD                         # last material update
publication-date: YYYY-MM-DD                # optional, if known
title: "Attention Is All You Need"
authors:                                    # full objects — slug + human name + optional ORCID
  - {slug: ashish-vaswani, name: "Ashish Vaswani"}
  - {slug: noam-shazeer, name: "Noam Shazeer"}
year: 2017
venue: nips                                 # slug; human name stored on the venue page if one exists
identifiers:                                # all known identifiers for this paper (used for dedup)
  doi: 10.xxx/xxx
  arxiv: 1706.03762
  arxiv-version: v5                         # specific arXiv version, if applicable
  url: https://...
aliases: []                                 # alternate paper-ids this page was previously known as
source-version: arxiv-v5                    # which source this wiki page summarizes
relationships:                              # optional — relations to other papers
  preprint-of: null                         # paper-id of the journal version
  version-of: null                          # paper-id of the canonical work (if this is a specific version)
  supersedes: []                            # paper-ids this supersedes
bib-file: raw/bib/vaswani-2017-attention.bib
extract: raw/extracts/vaswani-2017-attention.md
notes: raw/notes/vaswani-2017-attention.md  # optional — only if user wrote notes
figures: raw/figures/vaswani-2017-attention/  # optional
references-raw:                             # unresolved bibliography (verbatim from paper)
  - "Bahdanau, D. et al. 'Neural Machine Translation by Jointly Learning to Align and Translate.' 2014."
  - "Cho, K. et al. 'Learning Phrase Representations...' 2014."
cites:                                      # resolved references — paper-ids in this wiki
  - bahdanau-2014-neural
  - cho-2014-learning
tags: [field/nlp, method/attention, year/2017, venue/nips]
---
```

Body sections: `Metadata` / `Summary` / `Key Contributions` / `Methods` / `Results` / `Claims` / `User Notes` / `See Also`. User-notes section is auto-filled from `raw/notes/<paper-id>.md` if present.

Notes on the identity model:
- `paper-id` is generated on first ingest (see §5.2). Format mirrors the BibTeX key style for readability but is explicitly hyphen-separated to distinguish it from `citation-key`: `<lastname>-<year>-<firstword>`.
- `citation-key` (BibTeX-native, no hyphens: `vaswani2017attention`) is a derived export field. If metadata is corrected later, `citation-key` updates without renaming files.
- `identifiers:` is the dedup key. Ingest checks all existing papers' `identifiers:` against the incoming source — a match on any non-empty identifier (`doi`, `arxiv`, `url`, or `source-sha`) means the paper already exists; ingest merges new identifiers into the existing record instead of creating a duplicate.
- `aliases:` records historical `paper-id` values if the canonical id is ever renamed (e.g., metadata correction changes the first author). Wikilinks to the old id still resolve via alias lookup during lint.

Non-paper entities use `paper-id` values (not `citation-key`) in all reference fields like `sources:`, `supports:`, `evidence-for:`, etc.

**concept** — `wiki/concepts/<slug>.md`

```yaml
---
type: concept
status: active | stale
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [vaswani-2017-attention, ...]            # paper-ids
tags: [field/..., ...]
---
```

Body: `Definition` / `Details` / `See Also` / `Counter-Arguments and Gaps`.

**method** — `wiki/methods/<slug>.md`

```yaml
---
type: method
status: active | deprecated | contested
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [paper-id-1, paper-id-2]
related-methods: [other-method-slug]
tags: [field/..., method/..., ...]
---
```

Body: `Definition` / `How It Works` / `Results Using This Method` / `Known Limitations` / `See Also` / `Counter-Arguments and Gaps`.

**open-problem** — `wiki/open-problems/<slug>.md`

```yaml
---
type: open-problem
status: open | partially-resolved | resolved | disputed
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [paper-id-1, ...]
resolved-by: paper-id                             # optional
tags: [field/..., ...]
---
```

Body: `Statement` / `Why It Matters` / `Current Approaches` / `What's Missing` / `See Also`.

**result** — `wiki/results/<slug>.md` (cross-paper only)

```yaml
---
type: result
status: replicated | contested | preliminary | unverified
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [paper-id-1, paper-id-2, ...]
refutes: [other-result-slug]
supports: [claim-slug]
tags: [field/..., method/..., ...]
---
```

Body: `Statement` / `Evidence` / `Conditions` / `Caveats` / `See Also`.

**claim** — `wiki/claims/<slug>.md` (cross-paper only)

```yaml
---
type: claim
status: established | contested | fringe | deprecated
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [paper-id-1, ...]
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
type: author
name: "Ashish Vaswani"                            # human-readable
slug: ashish-vaswani
orcid: 0000-...
affiliation: ...
created: YYYY-MM-DD
updated: YYYY-MM-DD
papers: [paper-id-1, paper-id-2, ...]
tags: [field/..., person]
---
```

**venue** — `wiki/venues/<slug>.md`

```yaml
---
type: venue
name: "Conference on Neural Information Processing Systems"   # human-readable
slug: nips
venue-type: conference | journal | workshop | preprint-server
created: YYYY-MM-DD
updated: YYYY-MM-DD
papers: [paper-id-1, ...]
tags: [field/...]
---
```

### 3.3 Operational entity

**query-output** — `wiki/queries/<slug>.md`

```yaml
---
type: query-output
question: "<original question>"
status: filed | promoted
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [paper-id-1, ...]
tags: [field/...]
---
```

### 3.4 Cross-schema conventions

1. **`sources:` vs `cites:` vs `references-raw:`** — three layered concepts:
   - `references-raw:` (paper pages only): the raw bibliography as captured from the source, unresolved.
   - `cites:` (paper pages only): the subset of `references-raw:` that has been resolved to `paper-id`s in the wiki. Every key in `cites:` must match an existing paper page; unmatched raw references stay only in `references-raw:` until their papers are ingested.
   - `sources:` (every non-paper entity): paper-ids that inform this page.
2. **References are by `paper-id`, not `citation-key`.** `citation-key` is presentation-only; internal graph references are all `paper-id`.
3. **Status fields are entity-specific.** Different entity types have different meaningful states.
4. **`cited-by:` is never stored.** Dataview computes it on demand from `cites:` fields.
5. **Result/claim pages exist only when cross-paper.** Single-paper results/claims stay inline in the paper page until promoted.
6. **User notes are referenced, not copied.** The paper page's "User Notes" section links and summarizes `raw/notes/<paper-id>.md`; it never embeds or overwrites.
7. **`created:` vs `updated:`** — `created:` is set on page birth and never changes. `updated:` is bumped on any material content change. Lint uses `updated:` for staleness checks.

### 3.5 Slug generation rules

Applies to all non-paper entity pages (paper pages use `paper-id`). Concept/method/open-problem/claim/result/author/venue slugs are derived deterministically from a title string:

1. Unicode NFKD normalize, strip combining marks (ASCII-fold): `"SIC'19 Paper" → "SIC'19 Paper"` (unchanged); `"α-divergence" → "a-divergence"`.
2. Lowercase.
3. Replace any run of non-alphanumeric characters (except existing hyphens) with a single hyphen.
4. Collapse consecutive hyphens to one; strip leading/trailing hyphens.
5. Truncate at 60 chars at a word boundary if possible.
6. **Stop-word filter** — drop leading `a`/`an`/`the`/`on`/`of`/`for`/`with` if and only if the result is ≥2 words.
7. Collision resolution: if `<slug>.md` already exists in the same subfolder, check whether the existing page's subject is the same (LLM judgment: same concept/method/etc. with a different phrasing — merge instead of creating). If genuinely distinct, append suffix `-2`, `-3`, ....
8. Aliases: when a slug is merged or renamed, add the former slug to the target page's frontmatter `aliases: []`. Lint resolves `[[old-slug]]` via alias lookup.

Examples:
- `"Rate-Splitting Multiple Access"` → `rate-splitting-multiple-access`
- `"The Attention Mechanism"` → `attention-mechanism` (stop-word dropped)
- `"O(n²) complexity of self-attention"` → `o-n2-complexity-of-self-attention` (non-alphanumeric runs collapse to hyphens; `²` is NFKD-folded to `2`)
- `"K-means"` → `k-means`

### 3.6 Update conflict policy

When a new source contributes information that overlaps with an existing entity page, the compile flow merges rather than overwrites:

1. **Preserve prior claims** — existing assertions are not deleted by a new source alone.
2. **Append new evidence** — add the new source to `sources:` and add content in a new paragraph or section, clearly attributed.
3. **Flag contradictions inline** — if the new source asserts something in tension with existing content, add an Obsidian callout:
   ```
   > [!WARNING] Contradiction with [[other-paper-id]]
   > <Paper A> says X, but <Paper B> says Y. Needs resolution.
   ```
   Do not silently overwrite either side.
4. **Never replace without provenance** — every material claim on a wiki page must be traceable to at least one paper-id in `sources:`. If an LLM cannot attribute a claim to a source, the claim is dropped or marked `status: stale`.
5. **Bump `updated:` frontmatter** after any merge.
6. **Log the merge** — compile's commit message summarizes: `compile: merged <new-paper-id> into <N> existing pages`.

### 3.7 Raw-side metadata (extract and source provenance)

Raw-side metadata lives in `raw/extracts/<paper-id>.md` frontmatter. These fields are written by `ingest` and are read-only for `compile`/`query`/`lint`.

```yaml
---
paper-id: vaswani-2017-attention
source-path: raw/papers/vaswani-2017-attention.pdf
source-sha: 3f8c1e...                       # SHA-256 of the source file; used for dedup
source-version: arxiv-v5                    # arXiv version, DOI version, publisher revision, etc.
source-type: pdf | html | latex | markdown
source-url: https://arxiv.org/pdf/1706.03762v5.pdf
extractor: ocr-papers-to-latex              # name of extractor used
extractor-version: 1.2.0                    # if the extractor reports a version
extracted-at: YYYY-MM-DDTHH:MM:SSZ          # ISO-8601 UTC timestamp
ocr-used: true | false
extract-status: complete | partial | failed
extract-warnings: []                        # list of LLM or extractor warnings
---
```

Purpose:
- `source-sha` is compared on every ingest; an exact match means this source has already been ingested (skip with a warning, or merge identifiers into the existing paper).
- `extractor-version` + `extract-status` tell the LLM whether the extract is trustworthy and whether to suggest re-extracting.
- `extract-warnings` captures things like "Figures 3-5 failed to render" or "Pages 8-10 have low OCR confidence" — consumed by lint.

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

Scaffolds a new wiki at `~/ObsidianVault/03-Resources/<name>/` (default `academic`). The wiki is created as its own nested git repository.

1. Abort if target exists (suggest `remove <name>` first).
2. Create full directory tree (§2.2).
3. `git -C <wiki-path> init` to start the nested repo.
4. Write `CLAUDE.md` with the complete schema (§§2–7 inline, ~1000–1200 lines).
5. Write `wiki/index.md`, `log.md`, `.gitignore`, `qmd.yml`.
6. Update the Obsidian vault's `.gitignore` (if one exists) to exclude `03-Resources/<name>/` so the vault's git doesn't try to track the nested repo. Log a note if the vault isn't itself a git repo.
7. Initial commit **inside the wiki's own repo**: `git -C <wiki-path> add . && git -C <wiki-path> commit -m "init: <name> wiki"`.
8. If qmd available: `qmd collection add <wiki-path>/wiki --name <name> && qmd embed --collection <name>`.
9. Print Web Clipper + Zotero export setup hints.

### 5.2 `ingest <path|id|url>`

Saves a source to `raw/`, generates an extract, stubs BibTeX, and assigns a canonical `paper-id`. Does **not** create wiki pages — `compile` does.

**Input routing** (autodetect):

- `^\d{4}\.\d{4,5}(v\d+)?$` → arXiv ID → `mcp__agentic-rag-v2__download_arxiv`
- `^10\.\d+/.+` → DOI → `mcp__agentic-rag-v2__doi2content`
- `arxiv.org/abs/...` or `arxiv.org/pdf/...` → extract ID (including version) → arXiv handler
- Publisher URL → `mcp__agentic-rag-v2__fetch_publisher_html`
- Local `.pdf` → `ocr-papers-to-latex` skill
- Local `.md` → treat as pre-extracted
- Anything else → ask user

**Pipeline**:

1. **Acquire lockfile**: take `academic/.lock` (see §8). If already held, fail with `another operation is in progress`.
2. **Route input, acquire raw bytes/text.**
3. **Compute `source-sha`** — SHA-256 over the raw file. This is the cheapest dedup key.
4. **Dedup check — pass 1 (byte-level)**: scan existing `raw/extracts/*.md` for matching `source-sha`. If found, print: `"This exact source was already ingested as <paper-id>. Skipping."` Release lock; exit.
5. **Extract metadata** from the content:
    - First-author last name (lowercased, ASCII-folded: `García` → `garcia`).
    - 4-digit publication year.
    - Title's first meaningful word (lowercased; skip `a`/`an`/`the` and numerals).
    - Any known identifiers: `doi`, `arxiv` (with version if present), canonical `url`.
6. **Dedup check — pass 2 (identifier-level)**: compare extracted identifiers against every existing paper page's `identifiers:`. If any identifier matches (same DOI, same arXiv ID ignoring version, same canonical URL):
    - This paper already exists. Load its `paper-id`.
    - Merge: add any new identifiers the incoming source provides; if the incoming `source-version` differs, treat as a new version of the same paper (see step 8).
    - Do NOT create a new paper entity; re-use the existing `paper-id`.
7. **If no match (truly new paper)**: generate `paper-id` as `<lastname>-<year>-<firstword>`. Collision: if the id is already taken by a different paper (different identifiers), append `-2`, `-3`, ...
8. **Handle versions**: if the new source is a different version of an already-known paper (e.g., existing paper at arXiv v3, incoming is v5):
    - Save the new source file and extract with the same `paper-id` basename but store `source-version: arxiv-v5` in the extract frontmatter.
    - Append the new source to a per-paper-id manifest: `raw/extracts/<paper-id>.versions.yml` listing every version ingested with its `source-sha`, `extracted-at`, and `source-path`.
    - `wiki/papers/<paper-id>.md` updates `identifiers.arxiv-version:` to the most recent; older versions remain referenced in the manifest.
9. **Metadata-extraction failure fallback** (scan without OCR-able text, garbage metadata): use fallback `paper-id` of `unknown-<current-year>-<filename-slug>` for ALL file basenames consistently; set `metadata-incomplete: true` in the extract frontmatter; log for lint.
10. **Save files** with `<paper-id>` as the common basename across `raw/papers/`, `raw/extracts/`, `raw/bib/`, `raw/figures/`.
11. **Write extract frontmatter** per §3.7 with `source-sha`, `extractor`, `extracted-at`, `source-version`, etc.
12. **BibTeX**: if the source came with BibTeX (identifier-based ingest), save to `raw/bib/<paper-id>.bib`; otherwise stub a minimal `@misc` entry with `bib-incomplete: true`. BibTeX `@key` field uses `citation-key` (BibTeX-native style), not `paper-id`.
13. **Append to `log.md`**: `## [YYYY-MM-DD] ingest | <paper-id>` with one-line summary (new paper, new version, or deduped).
14. **Commit**: `ingest: <paper-id>` (or `ingest: <paper-id> (new version v5)` / `ingest: deduped <paper-id>`).
15. **Release lockfile.**
16. **Print**: `Source saved with paper-id <paper-id>. Run wiki compile <paper-id> to integrate into the wiki.`

### 5.3 `compile [<paper-id>]`

Compile comes in two tiers. Wave 1 ships the **paper-only** tier, which is low-risk and gets the wiki usable fast. Wave 2 adds entity extraction, cross-paper synthesis, and backlink audit. The command name stays the same; a flag controls the tier until Wave 2 is the default.

**Wave 1 tier — `compile [<paper-id>] [--paper-only]`** (default in Wave 1):

1. Acquire `academic/.lock`.
2. Identify sources: given `<paper-id>` or all paper-ids in `raw/extracts/` without a matching `wiki/papers/<paper-id>.md`.
3. For each source:
    - Read `raw/extracts/<paper-id>.md` + `raw/notes/<paper-id>.md` if present.
    - Write/update `wiki/papers/<paper-id>.md` per §3.1. Populate `Summary`, `Key Contributions`, `Methods`, `Results`, `Claims`, `User Notes` sections inline. Do NOT create entity pages for concepts/methods/open-problems.
    - `references-raw:` is populated from the bibliography section of the extract. `cites:` stays empty in Wave 1.
4. Update `wiki/index.md` (a simple chronological listing of paper pages in Wave 1; sectioned by `field/*` in Wave 2).
5. Append to `log.md`: `## [YYYY-MM-DD] compile | N paper pages created/updated`.
6. Commit: `compile: paper-only <summary>`.
7. Release lock.

Rationale: Wave 1 deliberately avoids entity extraction, cross-paper synthesis, backlink audit, and `cites:` resolution. Those are the highest-risk LLM-judgment operations in the whole design; shipping paper-only first lets you validate the rest of the system on real papers before turning on the risky parts.

**Wave 2 tier — `compile [<paper-id>]`** (default in Wave 2; Wave 1 tier remains available via `--paper-only`):

After Wave 1 is in use and stable, compile adds:

1. **Entity extraction**: identify concepts, methods, open-problems from the extract. Create/update `wiki/concepts/<slug>.md`, `wiki/methods/<slug>.md`, `wiki/open-problems/<slug>.md` per §3 schemas and §3.5 slug rules. Append `paper-id` to each page's `sources:`. Apply the update conflict policy (§3.6).
2. **Claim/result drafting**: draft claims and results as inline sections in the paper page (as in Wave 1).
3. **Cross-paper candidate detection** — NO silent auto-promotion. Use LLM judgment on semantic equivalence to identify candidates where a claim/result in this paper overlaps with one in another paper's Claims/Results section. Write candidates to a scratch file `outputs/reports/YYYY-MM-DD-promotion-candidates.md` with proposed slug, source paper-ids, and proposed content. Promotion itself requires an explicit user action via `query` + promote or a future `/academic-wiki:wiki promote <candidate-id>` command.
4. **`cites:` resolution**: LLM fuzzy-matches entries in `references-raw:` against existing `wiki/papers/` by title + first author + year. Matches populate `cites:`. Unmatched entries remain only in `references-raw:` and surface in lint as candidate new ingests.
5. **Backlink audit with allowlist**: `grep -rln` to find page titles in other wiki files, but ONLY insert `[[wikilink]]` when:
    - the matched slug is ≥2 words (avoids common single-word pollution like `[[attention]]` or `[[method]]`), OR
    - the page title appears within a noun phrase recognized by the LLM as a proper named entity.
    Common-word slugs can still be manually linked; they just aren't auto-linked by the audit.
6. **Index update**: sectioned by `field/*` tag.
7. Log + commit + qmd re-embed as in Wave 1.

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

**Deterministic checks** (Python, no LLM):

- **Dead links** (`[[foo]]` with no `foo.md`): flagged with context (the file and line where the link appears); not auto-stubbed. Deterministic code cannot infer the target's entity type from the wikilink alone. Stubbing is deferred to an optional LLM pass (`lint --fix-dead-links`) that reads the usage context and creates an appropriate-type stub.
- **Alias resolution**: before flagging a dead link as dead, check every existing page's `aliases:` frontmatter; if the dead link matches an alias, suggest rewriting to the canonical slug.
- **Orphan pages** (no inbound links): list, suggest where to add inbound links.
- **Missing `field/*` tag** on any paper / concept / method / open-problem / claim / result.
- **Missing frontmatter fields** per entity-type schema (uses §3 definitions).
- **Stale pages**: (a) any page with `status: stale` whose `updated:` is >90 days old; (b) any `concept` or `method` page whose `updated:` is >180 days old regardless of status.
- **Missing "Counter-Arguments and Gaps"** on concept / method pages.
- **Contradictions** (`[!WARNING]` markers): list.
- **Invalid `cites:` keys** (no matching paper page `paper-id`): flag as candidate new ingests.
- **Missing BibTeX** (paper page has no corresponding `raw/bib/<paper-id>.bib` or the bib has `bib-incomplete: true`).
- **Index drift** (`wiki/index.md` vs actual files).
- **Extract integrity**: paper page exists but `raw/extracts/<paper-id>.md` is missing, or the extract's `extract-status: failed`.
- **Version drift**: paper page's `identifiers.arxiv-version` differs from the latest entry in the versions manifest (a newer version has been ingested but the paper page hasn't been updated).

**LLM suggestions** (optional pass, `lint --with-suggestions`): 3–5 questions the wiki can't yet answer well, 2–3 sources that would strengthen gaps.

**Optional fix passes** (each opt-in, each separate):
- `lint --fix-dead-links`: LLM creates stubs for flagged dead links using usage context to choose entity type.
- `lint --suggest-backlinks`: LLM identifies pages that *should* link to new pages but don't, and proposes edits (does not apply silently; produces a diff for user review).

Save report to `outputs/reports/YYYY-MM-DD-lint.md`; append to `log.md`; commit.

### 5.6 `export-bibtex <selectors>`

Generates a consolidated `.bib` from a subset of paper pages.

**Selectors** (≥1 of the first six required; combinable with AND semantics):

- `--project <slug>` — papers tagged `project/<slug>`.
- `--field <slug>` — papers tagged `field/<slug>`.
- `--tag <tag>` — full tag including prefix.
- `--query <text>` — hybrid search over paper pages.
- `--keys <key1,key2,...>` — explicit list.
- `--since YYYY-MM-DD` — include only papers whose `created:` frontmatter (first-ingest date) is ≥ this date.
- `--label <string>` — optional override for the output filename label.

**Label resolution** (for the output filename):

1. If user passed `--label <string>`, use it verbatim. (Add `--label` to the selector list.)
2. Else: use the first non-empty selector value in this fixed priority order — `project`, `field`, `tag`, `query`, `keys[0]`, `since` — slugified.
3. Example: `export-bibtex --field wireless-comms --since 2024-01-01` → `outputs/bib/2026-04-16-wireless-comms.bib`.

**Pipeline**:

1. Resolve selectors → list of paper pages (AND semantics across multiple selectors).
2. Concatenate `raw/bib/<paper-id>.bib` contents into `outputs/bib/YYYY-MM-DD-<label>.bib`.
3. Report: `N papers exported. M have bib-incomplete flag (listed below).`
4. Append to `log.md`; commit: `export: <label> (<N> papers)`.

### 5.7 `snapshot <label>`

Tags the wiki state for reproducibility. Operates on the wiki's own nested git repo (§2), so the snapshot captures only wiki state — not unrelated Obsidian vault changes.

1. Acquire `academic/.lock`.
2. Precondition: `git -C <wiki-path> status --porcelain` must be empty (no unstaged changes). If not, warn with the list of uncommitted files and abort; the user commits pending changes first (they were most likely just made during a prior operation and should already be committed, so this is defensive).
3. `git -C <wiki-path> tag snapshot/<label>` at current HEAD. Tag name is namespaced under `snapshot/` to keep the tag space tidy.
4. Append to `log.md`: `## [YYYY-MM-DD] snapshot | <label>` with SHA.
5. Release lock.
6. Print: `Tagged as snapshot/<label> at <SHA>. Revisit with: git -C <wiki-path> checkout snapshot/<label>`.

### 5.8 `remove <name>`

Deletes a wiki and its nested git repo after confirmation.

1. Acquire `academic/.lock` inside `<wiki-path>`.
2. Verify target exists.
3. Confirm: `"This will permanently delete '<name>' AND its git history at <wiki-path>. Proceed? (y/n)"`.
4. Remove qmd collection if present: `qmd collection remove <name>`.
5. Remove the directory entirely: `rm -rf <wiki-path>` (the nested `.git/` goes with it).
6. If the Obsidian vault is itself a git repo, commit the removal so the vault's git knows the directory is gone: `git -C ~/ObsidianVault commit -am "remove: <name> wiki"` (no-op if vault isn't a git repo).

Note: the lock is released by the directory being gone.

## 6. Search Strategy

Single `find_pages(query) → list[SearchHit]` abstraction with multiple backends. The return type is richer than a path to let backends contribute ranking and snippet information.

```python
# Conceptual shape (the Python lint/export helpers may use this; the SKILL.md itself describes the contract informally)
class SearchHit:
    path: str           # relative to wiki root (e.g., "wiki/papers/vaswani-2017-attention.md")
    score: float        # backend-specific; higher is better; normalized to [0, 1] where possible
    snippet: str        # short matching context, if backend supports it; else empty
    backend: str        # "index+ripgrep" | "qmd" | "mcp:<name>"
```

Callers (query, lint, export-bibtex `--query`) use `path` to read the page, `score` to rank, `snippet` to show context. Backends that don't support `score` or `snippet` return sentinel values (`score=1.0`, `snippet=""`) rather than failing.

### 6.1 Phase 1 — index.md + ripgrep (default, no dependencies)

LLM reads `wiki/index.md` first to identify candidate matches by title/description, then uses ripgrep for content matching. Returns hits with `score=1.0` and a ripgrep-line `snippet`. Realistic for up to ~100 paper pages plus associated concept/method/etc. pages — beyond that, title-based matching in `index.md` starts missing candidates and ripgrep-across-everything gets noisy.

### 6.2 Phase 2 — qmd (optional, auto-installed)

If `${CLAUDE_PLUGIN_DATA}/node_modules/.bin/qmd` exists and is executable, use qmd's hybrid BM25 + vector search via `qmd query "<question>" --collection <wiki-name>`. Returns hits with qmd's own `score` and surrounding snippet. Falls back to Phase 1 if qmd crashes, the collection is corrupt, or qmd returns zero hits.

### 6.3 Future: custom MCP

User plans to build a custom MCP modeled on `agentic-rag-v2`. Not built by this plugin. The `find_pages` abstraction is designed so adding an MCP backend later is a modest change in `SKILL.md` (check MCP tool registry first, fall through to qmd, then Phase 1). Because the return type already carries `score`, `snippet`, and `backend`, no schema migration is needed.

## 7. CLAUDE.md Contract

The wiki-root `CLAUDE.md` is the authoritative contract the LLM reads on every operation. Self-contained — readable without reference to the plugin source. Sections:

1. Directory layout (§2.2 inline, including the nested-git-repo note).
2. Identity model (§2.3 #2 + §3.1 — paper-id vs citation-key, identifiers, aliases, dedup rules).
3. Entity types (§3.1–§3.3 inline).
4. Cross-schema conventions (§3.4).
5. Slug generation rules (§3.5).
6. Update conflict policy (§3.6).
7. Raw-side metadata schema (§3.7).
8. Tag taxonomy (§4 inline).
9. Naming conventions.
10. Log format: `## [YYYY-MM-DD] <op> | <subject>` where `<op> ∈ {init, ingest, compile, query, promote, lint, export, snapshot, remove}`.
11. Commit message format: `<op>: <subject>`, optionally followed by a one-line "why" body.
12. Cross-reference rules (wikilink density, backlink audit allowlist, contradiction callouts).
13. Ingest rules (§5.2 step-by-step with dedup and versioning).
14. Compile rules (§5.3 — paper-only tier for Wave 1; full tier for Wave 2).
15. Query rules (§5.4).
16. Lint rules (§5.5 complete check list, including opt-in fix passes).
17. Export-bibtex rules (§5.6).
18. Snapshot rules (§5.7 — wiki's own git repo, tag namespace).
19. Search strategy (§6 — SearchHit contract and fallback chain).
20. Lockfile semantics (§8 concurrent-operation protection).

Expected length: ~1000–1200 lines with the new sections. Reference doc, not linear reading material.

## 8. Error Handling

### 8.1 Concurrent-operation protection (lockfile)

Mutating commands (`ingest`, `compile`, `query` with promotion, `lint --fix-*`, `export-bibtex`, `snapshot`, `remove`) take an advisory `academic/.lock` at the start and release at the end. The lockfile contains `<pid>:<iso-timestamp>:<op>`.

- Acquiring a held lock: fail fast with `Another operation is in progress: <op> started at <timestamp> by pid <pid>`. User retries after the other op completes.
- Stale lock (holding pid is gone): treat as released. Log a warning and take the lock.
- Any command that panics between acquire and release leaves the lock; stale-pid detection recovers on the next attempt.

**Cross-platform behavior.** Stale-lock detection works on Windows as well as POSIX via `_is_alive()`'s platform branch — POSIX uses `os.kill(pid, 0)`; Windows uses `OpenProcess` + `GetExitCodeProcess` via `ctypes`. The bash `trap EXIT` cleanup mechanism documented in earlier drafts of SKILL.md has been removed in favor of explicit `release` calls on every error-exit path; agent-crash recovery now relies entirely on stale-PID detection, which is platform-agnostic. Per-entity locks (`<wiki>/.locks/<kind>/<key>.lock`) use the `filelock` library, which selects the appropriate OS primitive (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows) and auto-releases on process death across both platforms.

Read-only commands (`query` without promotion, `lint` without fix passes) do not take the lock.

### 8.2 Error catalog

| Situation | Action |
|---|---|
| **Lockfile held** | Fail fast (see §8.1). |
| **Lockfile stale** (holding pid gone) | Warn, take the lock, continue. |
| **No active wiki found** | List candidates in `~/ObsidianVault/03-Resources/*/wiki`. Default to `academic/` if present; else prompt. |
| **Duplicate source (`source-sha` match)** | Skip ingest; print the existing `paper-id`. |
| **Duplicate paper (identifier match, different source-sha)** | Treat as new version of an existing paper; reuse `paper-id`, update `identifiers:`, store new source under the same id with `source-version:` distinguishing. |
| **PDF has no extractable text** | Route to `ocr-papers-to-latex` with OCR mode; if still fails, save PDF as-is, set `extract-status: failed`, warn, don't block. |
| **Metadata extraction fails** | Fallback `paper-id` = `unknown-<YYYY>-<filename-slug>`; set `metadata-incomplete: true`; lint surfaces. |
| **arXiv/DOI API failure** | Retry once with backoff. If still failing, log error; suggest manual ingest. |
| **Paper-id collision** (different paper wants the same id) | Append numeric suffix `-2`, `-3`, ...; never overwrite. |
| **BibTeX missing** | Stub minimal `@misc`; set `bib-incomplete: true`. |
| **Git commit fails** | Warn with git output; do not retry; do not use `--no-verify`. User resolves manually. Release lock before surfacing the error. |
| **qmd crashes / corrupt index** | Fall back to Phase 1 search for that operation; warn once per session. |
| **Extract exists, paper page missing** | Treat as uncompiled; next `compile` picks up. |
| **Paper page exists, extract missing** | Lint warning: re-run ingest on the source. |
| **Invalid `cites:` key** | Lint: "candidate new ingests"; do not auto-ingest. |
| **`compile` targets non-existent paper-id** | Abort: `No extract found at raw/extracts/<paper-id>.md. Did you run wiki ingest first?` |
| **Snapshot precondition fails** (uncommitted changes) | Abort with a list of uncommitted files. User commits and retries. |
| **Dead wikilink** | Flag with context in lint; do not auto-stub. Use `lint --fix-dead-links` for an LLM-assisted stub pass. |
| **Inconsistent tag use** | Lint: list pages, suggest rename. (No automatic rename yet.) |
| **Large source (>1MB extract)** | Warn; entity extraction may be incomplete; proceed. |
| **Version drift** (newer version ingested but paper page not updated) | Lint warning: paper page `identifiers.arxiv-version` behind latest version in `raw/extracts/<paper-id>.versions.yml`. |

## 9. Dependencies

### 9.1 Required

- Python 3.10+ (for `lint-wiki.py`, `bibtex-export.py`)
- git with `user.name` and `user.email` configured — `init` runs `git init` inside the wiki directory to create its nested repo
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

- `scripts/lint-wiki.py`: dead link (flagged, not stubbed), alias resolution, orphan, missing field tag, missing counter-arguments, stale (using `updated:`), invalid `cites:` key, missing bibtex, index drift, version drift.
- `scripts/bibtex-export.py`: each selector, combination semantics, `--since` against `created:` field, explicit key list, label resolution priority order, `--label` override.
- Slug generator (§3.5): unicode folding, stop-word filter, collision handling, edge cases (equations, acronyms, numbers).
- Paper-id generator + dedup logic: identifier normalization (arXiv ID with/without version, DOI case-folding), identifier-match dedup, source-sha dedup, collision resolution.
- Lockfile: acquire / fail / stale-recovery / release.

### 10.2 Integration fixture

`test-fixtures/mini-wiki/` with ≥7 hand-crafted papers covering:
- 1 arXiv paper (identifier-based)
- 1 DOI paper
- 1 local PDF
- 1 with user notes (`raw/notes/<paper-id>.md`)
- 1 with `bib-incomplete: true`
- 1 ingested twice to verify identifier-level dedup (e.g., first via arXiv, then via DOI with same underlying paper)
- 1 ingested as v1 then v2 to verify version handling

End-to-end runs of each command against the fixture, compared against expected state. Wave 1 tests cover ingest + `compile --paper-only` + query; Wave 2 tests add entity extraction, backlink audit, promotion-candidate generation.

### 10.3 Manual smoke tests

Documented in `WALKTHROUGH.md` — full end-to-end run on a real paper: ingest → compile → query → lint → export-bibtex → snapshot.

### 10.4 Explicit non-tests

LLM synthesis quality is not tested automatically (subjective; better evaluated by reading). Tests cover plumbing: routing, filenames, frontmatter correctness, commit messages, file structure.

## 11. Rollout Plan

Four waves (was three; Wave 1 has been split on Codex's feedback to separate low-risk paper-page creation from high-risk cross-paper synthesis). Each wave's exit criterion must be met before starting the next.

### 11.1 Wave 1 — Paper-only core loop (the real MVP)

Goal: end-to-end flow works on real papers without any cross-paper synthesis or entity extraction. This validates the hard plumbing (routing, metadata extraction, paper-id + identifiers, source-sha dedup, version handling, lockfile, own-repo git semantics) before introducing LLM-judgment risks.

- `init` (scaffolds wiki, initializes its own git repo, writes `CLAUDE.md`).
- `ingest` — full routing, metadata extraction, `paper-id` + `identifiers:` assignment, dedup (byte-level + identifier-level), version handling, extract frontmatter per §3.7.
- `compile --paper-only` — creates/updates paper pages only. Populates `Summary`, `Key Contributions`, `Methods`, `Results`, `Claims`, `User Notes` inline. Writes `references-raw:` from the bibliography. Does NOT create entity pages, does NOT resolve `cites:`, does NOT run backlink audit, does NOT auto-promote.
- `query` — Phase 1 search over paper pages only. Synthesizes answers with wikilink citations to paper pages. Files answers to `wiki/queries/`. No promotion prompt yet (promotion targets concept/method/etc. pages that don't exist in Wave 1).

**Exit criterion**: ingest → compile-paper → query → file loop works on ≥5 real papers of varied types (≥1 arXiv-identifier, ≥1 DOI, ≥1 local PDF, ≥1 with `raw/notes/<id>.md` present, ≥1 re-ingested as a new version). Dedup and version handling verified end-to-end. No entity pages exist yet.

### 11.2 Wave 2 — Synthesis

Turn on the features that rely on LLM judgment, with explicit user review built in.

- `compile` (full tier) — entity extraction for concepts, methods, open-problems. `cites:` resolution from `references-raw:`. Backlink audit with the ≥2-word slug allowlist. Cross-paper claim/result equivalence detection, writing candidates to `outputs/reports/*-promotion-candidates.md`. No silent auto-promotion.
- `query` extended with the promotion prompt (concept / method / open-problem / claim / result).

**Exit criterion**: on a wiki of ≥15 compiled papers, concept/method/open-problem pages exist for a majority of papers, backlink density is ≥3 wikilinks per page on average, promotion candidates have been reviewed by hand at least once.

### 11.3 Wave 3 — Maintenance and output

- `lint` (deterministic checks + opt-in `--fix-dead-links`, `--suggest-backlinks`, `--with-suggestions`).
- `export-bibtex` (all selectors).
- `snapshot` (tags the wiki's own repo).

### 11.4 Wave 4 — Polish

- `remove` (cleanup command).
- `WALKTHROUGH.md` analogous to `llm-wiki`'s.
- Marp slide export convenience.
- Tooling gaps surfaced during Wave 1–3 (candidates: `promote <candidate-id>` command, `rename-key`, `merge-duplicate-papers`, `re-extract <paper-id>` — all out of scope for initial design).

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
| Wiki data location | α — inside Obsidian vault (as its own nested git repo, after Codex review) |
| MCP integration | B — wiki self-contained; custom MCP later |
| Scale plan | D — small now, designed to grow fast |
| Math | `$...$` and `$$...$$`, Obsidian-native |
| BibTeX | Per-paper `.bib` files in `raw/bib/` |
| Citation key | `<lastname><year><firstword>` (hyphen-separated `paper-id`, BibTeX `citation-key` without hyphens) |
| Canonical paper identity | `paper-id` + `identifiers:` + `aliases:` (after Codex review; `citation-key` is now a derived export field) |
| Git proposal adoption | Tags adopted (`snapshot` command); commit-message format codified; source-file SHA-256 adopted for dedup |
| Tag taxonomy | `field/`, `subfield/`, `method/`, `year/`, `venue/` auto-applied; `project/`, `user/` user-only |
| Metadata-extraction fallback | Filename-derived + lint flag, no interactive prompt |
| Compile auto-promotion | **No** — Wave 2 writes promotion candidates only (revised after Codex review; was originally silent auto-promote) |
| Search phases | index.md + qmd only for now; no custom MCP yet |
| Testing | Unit + fixture + manual smoke; no LLM-quality tests |
| Rollout | Four waves: paper-only core → synthesis → maintenance → polish (revised after Codex review; was originally three) |

## Appendix B — Revisions from Codex review (2026-04-16)

Codex's review identified five major concerns. All were adopted:

1. **Identity model overhaul** — introduced `paper-id`, `identifiers:`, `aliases:`. `citation-key` demoted to derived export field. Dedup on ingest uses identifier-level match + byte-level `source-sha`.
2. **Versioning added** — `source-version`, `relationships:`, per-paper-id versions manifest. arXiv v1/v2 handled as distinct versions of one canonical paper.
3. **Silent auto-promotion removed** — compile now writes promotion candidates to a report; promotion requires explicit user action. Backlink audit tightened with a ≥2-word allowlist.
4. **Git atomicity fixed** — wiki is its own nested git repo. Snapshot acts on this repo, not the vault's. Advisory `.lock` serializes mutating operations.
5. **Wave 1 split** — `compile` now has `--paper-only` tier that is the Wave 1 default. Entity extraction, `cites:` resolution, cross-paper candidate detection, and backlink audit all move to Wave 2.

Medium concerns adopted:
- `references-raw:` vs `cites:` split (raw vs resolved bibliography).
- `find_pages` returns `SearchHit {path, score, snippet, backend}`, not bare paths.
- `init [<name>]` consistency clarified; qmd collection uses `<name>`, not hardcoded.
- `--since` explicitly uses `created:` frontmatter.
- Lint does not auto-stub dead links; `--fix-dead-links` is opt-in.
- Slug generation rules (§3.5) added.
- Update conflict policy (§3.6) added.
- Extract frontmatter provenance (§3.7) added.
- Git-proposal dedup rejection revised to partial-adopt (source-file SHA).

Minor concerns adopted:
- `date:` split into `created:` and `updated:` (plus optional `publication-date:` on papers).
- Fallback naming made consistent (fallback `paper-id` used for all file basenames).
- Authors store human-readable `name:` alongside slug.
- Figure extraction trigger + failure-surfacing defined in §3.7 + §8.2.
