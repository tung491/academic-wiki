# Clipper Directory Ingest & Unified Compile Pipeline

**Date:** 2026-04-18
**Status:** Approved

## Problem Statement

Two usability issues with the academic wiki plugin:

1. **Clipper directory handling:** The Obsidian Web Clipper saves papers as directories containing a `.md` file and an optional `images/` subdirectory. The current ingest flow only handles flat files — it cannot detect clipper directories, find the `.md` inside, or handle companion images. It also creates redundant copies (`raw/extracts/` and `raw/papers/`) when the clipper `.md` is already in the right place.

2. **Two-wave compile:** Compile is split into Wave 1 (paper-only) and Wave 2 (full: entities + cites + backlinks). Users must run compile twice or remember flags. This should be a single invocation.

Additionally, the `paper-id` format changes from `brik-2023-xai` (hyphenated) to `brik2023xai` (no hyphens), unifying it with the BibTeX citation-key format and making `citation-key` redundant.

## Design

### 1. Paper-ID Format Change

**Before:** `<lastname>-<year>-<firstword>` (e.g., `brik-2023-xai`)
**After:** `<lastname><year><firstword>` (e.g., `brik2023xai`)

- Collision suffix appended directly with no separator: `brik2023xai2`, `brik2023xai3`. Both `generate_paper_id()` and `resolve_collision()` in `paper_id.py` must be updated — `resolve_collision` currently appends `-N`; change to append `N` directly.
- `citation-key` field is dropped from all frontmatter schemas — `paper-id` serves both purposes. This includes: paper page frontmatter, `templates.py` (CLAUDE.md schema example), `bibtex-handling.md` (which currently distinguishes citation-key from paper-id), and SKILL.md step 12 (which says BibTeX @key uses citation-key).
- BibTeX export uses `paper-id` as the `@key`
- All filenames follow the new format: `raw/extracts/brik2023xai.md`, `raw/bib/brik2023xai.bib`, `wiki/papers/brik2023xai.md`, `raw/figures/brik2023xai/`
- Wikilinks: `[[brik2023xai]]`
- Fallback paper-id format also changes: `unknown<currentyear><filenameslug>` (no hyphens, consistent with the main format)
- No migration needed — wiki will be re-initialized fresh

### 2. Clipper Directory Detection & In-Place Ingest

#### New routing pattern

Inserted into the ingestion routing table **before** the existing "local `.md`" pattern:

| Pattern | Handler |
|---|---|
| Local directory containing ≥1 `.md` file + optional `images/` subdirectory | Clipper handler |

#### Detection logic

A directory is recognized as a clipper directory when:
1. It contains at least one `.md` file
2. It optionally contains an `images/` subdirectory with image files (`.png`, `.jpg`, `.gif`, `.webp`)
3. The `.md` file does NOT already have a `paper-id` field in its frontmatter (unprocessed)

#### Batch scan mode

`ingest` with no arguments:
- Walks `raw/papers/*/` looking for directories matching the clipper pattern
- Filters to only unprocessed ones (no `paper-id` in `.md` frontmatter, OR `paper-id` present but `extract-status` absent/not `complete` — recovery for partial-ingest crashes)
- One `acquire()` before the loop, one `release()` after the loop (not per-directory). This replaces the per-paper lock pattern from normal ingest — batch mode sets the EXIT trap once before the loop and the trap releases on any exit. The per-paper lock/trap code in SKILL.md steps 1/15 is skipped in batch mode.
- Processes each sequentially within the single lock. Papers processed earlier in the batch are visible to later papers' dedup scans (their `paper-id` is already written to frontmatter).
- Prints summary: `Ingested N papers from raw/papers/`

#### Per-directory ingest flow

1. Find the `.md` file inside the clipper directory
2. Read its frontmatter + body to extract metadata (title, DOI, date, venue, authors from content)
3. Run the standard metadata pipeline: first-author -> year -> first-word -> generate `paper-id` (new no-hyphen format)
4. Run dedup passes:
   - **Dedup pass 1 (byte-level):** scan both `raw/extracts/*.md` AND `raw/papers/*/` clipper `.md` files for matching `source-sha` in frontmatter. Both locations must be checked since clipper sources live in `raw/papers/`, not `raw/extracts/`.
   - **Dedup pass 2 (identifier-level):** same as existing — scan `wiki/papers/*.md` for matching identifiers.
   - **Collision resolution:** `resolve_collision()` must check both `wiki/papers/*.md` filenames AND `paper-id` values in clipper `.md` frontmatter across `raw/papers/*/`. Two uncompiled clipper papers could otherwise receive the same `paper-id`.
5. **Edit the `.md` in place** — read existing frontmatter with `read_frontmatter()`, merge by adding missing fields (do NOT overwrite existing ones like `title`, `doi`, `date`, `venue`, or any user-added fields), write back with `write_frontmatter()`. Fields to inject:
   - `paper-id`
   - `source-sha`
   - `source-type: clipper-md`
   - `source-url` (derived from DOI as `https://doi.org/<doi>` if present; else use URL from clipper frontmatter if present; else `null`)
   - `extracted-at` (ISO-8601 UTC)
   - `extract-status: complete`
   - `extractor: obsidian-clipper`
   - `ocr-used: false`
   - `extract-warnings: []`
6. If `images/` exists: create a **relative** symlink `raw/figures/<paperid>` -> `../papers/<clipper-dir-name>/images/` (relative to `raw/figures/` so the symlink survives vault relocation)
7. Leave image references (`![[fig1.png]]`) untouched — Obsidian resolves them vault-wide
8. Stub BibTeX to `raw/bib/<paperid>.bib` as usual
9. Log + commit

#### Key differences from normal ingest

- No `raw/extracts/<paperid>.md` is created — the clipper `.md` IS the extract
- No `raw/papers/<paperid>.*` copy — the clipper directory is the canonical source
- Figures are symlinked, not copied

#### Compile lookup change

Compile currently scans only `raw/extracts/*.md`. A new unified lookup function `find_all_extracts(wiki_root)` scans both:
- `raw/extracts/*.md` (existing flow for DOI/arXiv/PDF-ingested papers)
- `raw/papers/*/` clipper directories (`.md` files with `paper-id` in frontmatter)

Returns a uniform list of `(paper_id, md_path)` tuples regardless of source type, sorted alphabetically by `paper_id` for deterministic compile ordering. Compile must use the `md_path` from the tuple to read the extract — NOT construct a path from `paper-id`, since the path formula differs per source type.

### 3. Unified Compile Pipeline

**Command:** `/academic-wiki:wiki compile [<paper-id>] [--paper-only]`

Default compile runs the full pipeline. `--paper-only` is the escape hatch for quick passes.

#### Full pipeline (default)

1. Acquire lock (op=`compile`)
2. Find sources via `find_all_extracts()` — filter to new/updated
3. **Per paper:** read extract -> LLM-generate paper page -> write `wiki/papers/<paperid>.md`
4. **Entity extraction:** scan extract body for concepts, methods, open-problems -> create/update `wiki/<type>s/<slug>.md`
5. **Cites resolution:** fuzzy-match `references-raw` entries against existing paper pages -> populate `cites: [...]`
6. **Backlink audit:** grep for entity slugs, insert `[[wikilinks]]` using >=2-word slug rule
7. **Cross-paper candidate detection:** compare claims/results, write to `outputs/reports/YYYY-MM-DD-promotion-candidates.md` (never auto-promote)
8. **Index rebuild:** organize by `field/*` tags
9. Log + commit + release lock

#### `--paper-only` flag

Runs only steps 1-3 + 8 (index) + 9 (log/commit). Skips entity extraction, cites resolution, backlink audit, and cross-paper detection.

#### Terminology cleanup

All "Wave 1" / "Wave 2" language removed from:
- `skills/wiki/SKILL.md`
- `skills/wiki/references/compilation-guide.md`
- `skills/wiki/references/entity-schemas.md`

Replaced with "compile" (full) and "compile --paper-only".

## Files to Modify

| File | Change |
|---|---|
| `skills/wiki/SKILL.md` | New clipper routing, batch scan for `ingest`, unified compile, drop `citation-key`, new `paper-id` format, remove Wave terminology, update step 12 (BibTeX @key now uses paper-id), update compile prose (line 259+) to remove Wave 1/2 language |
| `skills/wiki/references/ingestion-routing.md` | Add clipper directory pattern, document batch scan, update step 5 paper-id format from `<lastname>-<year>-<firstword>` to `<lastname><year><firstword>` |
| `skills/wiki/references/compilation-guide.md` | Merge into single pipeline, document `--paper-only`, remove Wave 1/2 headers |
| `skills/wiki/references/entity-schemas.md` | Drop `citation-key` from paper entity schema, remove any Wave references |
| `skills/wiki/references/bibtex-handling.md` | Remove distinction between `citation-key` and `paper-id` — paper-id is now the BibTeX `@key` |
| `scripts/academic_wiki_lib/paper_id.py` | `generate_paper_id()` drops hyphens; `resolve_collision()` changes suffix from `-N` to `N`; collision check expanded to scan clipper `.md` frontmatter in `raw/papers/*/` |
| `scripts/academic_wiki_lib/wiki_paths.py` | Add `find_all_extracts(wiki_root)` scanning both `raw/extracts/` and `raw/papers/*/` |
| `scripts/academic_wiki_lib/templates.py` | Update CLAUDE.md template: remove `citation-key` from paper schema example, update paper-id format examples |

## Fields Dropped

- `citation-key` — redundant with new `paper-id` format

## New Frontmatter Values

- `source-type: clipper-md` — identifies clipper-ingested sources
- `extractor: obsidian-clipper` — identifies the source handler
