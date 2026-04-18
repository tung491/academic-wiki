# Compilation Guide

Compile reads ingested extracts and produces wiki pages. Default runs the full pipeline;
`--paper-only` skips entity extraction through cross-paper detection.

## Source discovery

Uses `academic_wiki_lib.wiki_paths.find_all_extracts(wiki_root)` which scans both:
- `raw/extracts/*.md` (standard ingest — DOI/arXiv/PDF sources)
- `raw/papers/*/` clipper directories (`.md` files with `paper-id` in frontmatter)

Returns `(paper_id, md_path)` tuples sorted alphabetically by `paper_id` for deterministic ordering. Compile must use the `md_path` from the tuple to read the extract — do NOT construct a path from `paper-id`, since clipper extracts live under `raw/papers/<dir>/` not `raw/extracts/`.

## Per-source steps (all modes)

For each paper-id to compile:

1. Read the extract `.md` via `read_frontmatter` using the `md_path` from `find_all_extracts()`. The frontmatter gives you `paper-id`, `source-sha`, `source-version`, `source-url`, and extractor metadata.

2. Read `raw/notes/<paper-id>.md` if it exists. User-authored; treat as immutable.

3. Determine paper `status:` — `read` if user notes present and non-trivial (>200 chars), else `skimmed`. LLM may override based on content depth.

4. Write (or update) `wiki/papers/<paper-id>.md` with:
    - Full frontmatter per §3.1: `paper-id`, `type: paper`, `status`, `created` (today if new), `updated` (today), `publication-date` (if known), `title`, `authors` (list of `{slug, name}` objects), `year`, `venue` (**slug** form via `academic_wiki_lib.slug.make_slug(<raw-venue>)`), `identifiers`, `aliases: []`, `source-version`, `bib-file`, `extract`, `notes` (only if `raw/notes/<paper-id>.md` exists), `figures` (only if `raw/figures/<paper-id>/` is non-empty), `references-raw` (list of raw bibliography strings), `cites: []` (empty in `--paper-only` mode; resolved in full mode), `tags`.
    - Tags MUST include the deterministic pair `year/<YYYY>` + `venue/<slug>` derived from the extract frontmatter, in addition to any LLM-inferred `field/*`, `subfield/*`, `method/*` tags.
    - Body sections: `## Metadata` (inline one-liner), `## Summary`, `## Key Contributions`, `## Methods`, `## Results`, `## Claims`, `## User Notes`, `## See Also`.

4b. **Venue page upsert** (runs after step 4, before step 5) — after writing the paper page, ensure `wiki/venues/<venue-slug>.md` exists and includes this paper:
    - If the extract has no `venue:` field (missing or empty/whitespace), skip this step.
    - Compute `venue-type` via `academic_wiki_lib.templates.guess_venue_type(<raw-venue>)`.
    - New: render with `academic_wiki_lib.templates.venue_md_stub(slug=<venue-slug>, name=<raw-venue>, venue_type=<venue-type>, paper_ids=[<paper-id>], field_tags=<paper's field/* tags>, today=<today>)` and write the result to disk.
    - Existing: read with `academic_wiki_lib.frontmatter.read_frontmatter`, append `<paper-id>` to `papers:` (dedup, preserve order), union `field/*` into `tags:` (dedup, preserve order), bump `updated:`. Preserve `created:`, `name:`, `venue-type:`, `slug:` (the user may have corrected them). Write back with `academic_wiki_lib.frontmatter.write_frontmatter`.
    - Runs in ALL modes (default AND `--paper-only`) — venue pages are cheap and belong with the paper write.

5. Extract bibliography from the extract body and populate `references-raw: [...]` — verbatim strings.

## Additional steps (full mode only — skipped by `--paper-only`)

6. **Entity extraction:** scan the extract body for concepts, methods, and open-problems. For each:
    - Generate slug via `make_slug(<entity-name>)`.
    - Check if `wiki/<entity-type>s/<slug>.md` exists; if yes apply the update conflict policy; if no, create using the appropriate §3 template.
    - Default `status:` values: concept→`active`, method→`active`, open-problem→`open`, result→`preliminary`, claim→`established`.
    - Add `[[wikilinks]]` in the paper's Methods/Claims/Summary sections.

7. **`cites:` resolution:** for each `references-raw:` entry, LLM fuzzy-matches by title + first-author + year against existing paper pages. Matches populate `cites: [...]`. Unmatched entries remain in `references-raw:` only and surface in lint as candidate new ingests.

8. **Backlink audit with ≥2-word slug allowlist:** use `rg` to find mentions of entity slugs across wiki files; insert `[[wikilink]]` only when: (a) slug is ≥2 hyphen-separated words (e.g., `attention-mechanism`), OR (b) match appears in a proper-named-entity noun phrase. Single-word slugs like `attention` are never auto-linked.

9. **Cross-paper candidate detection** (non-destructive): LLM compares new paper's claims/results against existing paper pages by semantic equivalence. Candidates written to `outputs/reports/YYYY-MM-DD-promotion-candidates.md`. Contradicting quantitative findings get a `**Contradiction, not equivalence**` flag. NO silent auto-promotion.

## Shared final steps (all modes)

10. **Update `wiki/index.md`:** full mode rebuilds by `field/*` tag; `--paper-only` appends under a `## Uncategorized` heading. Avoid duplicates.

11. **Log + commit + release lock.**

## Update conflict policy

Applies whenever compile touches an existing page (re-compiled paper or updated entity page).

Key principles:
1. **Preserve prior claims** — existing assertions are not deleted by a new source alone.
2. **Append new evidence** — add the new paper-id to `sources:` (or `cites:` for paper pages). Incorporate new content in a clearly attributed paragraph or section.
3. **Flag contradictions inline** — insert `> [!WARNING] Contradiction with [[other-paper-id]]` Obsidian callouts at the point of disagreement. Never silently overwrite either side.
4. **Never replace without provenance** — every material claim must trace to ≥1 `paper-id` in `sources:`. Unattributable claims are dropped OR marked `status: stale`.
5. **Bump `updated:`** frontmatter to today.
6. **Do not change `created:`** — it reflects first creation, never re-bumps.
7. **Aliases:** if a rename/merge happens during update, add the former slug to the target page's `aliases: []`. Lint resolves `[[old-slug]]` via alias lookup.
8. **Log the merge** — commit message summarizes: `compile: merged <new-paper-id> into <N> existing pages`.
