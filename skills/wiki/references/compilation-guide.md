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
    - Tags MUST include `year/<YYYY>` (derived from the extract frontmatter's `year:` or `date:` field) and `venue/<slug>` (when the extract has a `venue:` field — if missing, only the `year/*` tag is added). These are deterministic — they do not depend on LLM inference. LLM-inferred tags (`field/*`, `subfield/*`, `method/*`) are added on top.
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

## Batch compile mode

Batch mode orchestrates parallel Haiku subagents for bulk compilation. The subagents handle per-paper work (steps 1–5 + 4b from *Per-source steps*). The orchestrator handles checkpoint management, wave coordination, git commits, and index/log updates.

### Activation

- Batch mode activates when **no `<paper-id>` argument is given** AND the count of pending papers is **>5**.
- If a checkpoint file exists with `status: in-progress`, enter the **resume flow** instead (see *Resume flow* below).
- Papers ≤5: use the existing sequential path — no subagents.
- Activation selects **full-tier** when invoked without `--paper-only` and **paper-only** when `--paper-only` is set; resume reads the checkpoint's `tier:` field to pick the right template.

### Checkpoint management

Use `academic_wiki_lib.checkpoint` for all checkpoint operations. Follow the same Python invocation style used elsewhere in the skill:

```bash
"$PY" -c "
import sys; sys.path.insert(0, '${PYTHONPATH}')
from academic_wiki_lib.checkpoint import create_checkpoint, read_checkpoint
..."
```

- **Create** a checkpoint at the start of a fresh batch run, recording `squash-base` as the current `HEAD` SHA.
- **Update** the checkpoint after each wave completes, saving per-paper `ok`/`failed` statuses and `last-completed-wave`.
- **Delete** the checkpoint file on successful completion (all papers `ok`).

**New checkpoint fields for full-tier:**

| Field | Values | Purpose |
|---|---|---|
| `tier` | `full` / `paper-only` | Determines which subagent prompt template to use; written at creation time |
| `pre-batch-paper-ids` | list of paper-id strings | Paper IDs present in `wiki/papers/` before the batch started; used by the final pass to distinguish intra-batch from pre-existing papers |
| `final-pass-status` | `pending` / `in-progress` / `ok` / `failed` | Tracks state of the final orchestrator pass (intra-batch cites + backlinks); only present for full-tier checkpoints |

Use `update_final_pass_status(wiki_root, status)` from `academic_wiki_lib.checkpoint` to transition `final-pass-status` — never edit the checkpoint YAML directly.

Note: `pre-batch-backlink-targets` is **not** stored in the checkpoint. It lives in a separate file `outputs/.pre-batch-snapshot.yml`, written by the snapshot helper before Wave 1 (see *Pre-batch snapshot* below).

### Wave partitioning

1. Call `find_all_extracts(wiki_root)` to obtain all `(paper_id, md_path)` tuples.
2. Filter out any `paper_id` already marked `ok` in the checkpoint (resume case).
3. From the remaining papers, keep only those where the extract is **newer** than the paper page (compare `extracted-at` frontmatter vs `updated:` on `wiki/papers/<paper-id>.md`) **or** the paper page does not yet exist.
4. Partition into waves using the `wave-size` field in the checkpoint, which stores **papers per wave** (not agent count):
   - Target up to 60 papers per wave: `papers_per_wave = min(len(pending), 60)`. (Capacity is 3 subagents × 20 papers = 60.)
   - Split each wave into subagent batches of `ceil(papers_per_wave / 3)` papers each, capped at **20 papers per subagent**.
   - Each wave is a list of subagent batches, where each batch is a list of `{paper-id, extract-path}` tuples.

**Full-tier vs. paper-only sizing:**

- **Full-tier:** wave-size is ~30 papers (3 subagents × 10 papers each). Each subagent's batch is capped at **10 papers** to keep entity extraction + backlink context manageable.
- **Paper-only:** wave-size is ~60 papers (3 subagents × 20 papers each; matches the values above).

### Pre-batch snapshot (full-tier only)

Before dispatching Wave 1 on a **fresh full-tier** batch run, capture the vault state so the final pass can distinguish intra-batch work from pre-existing pages:

1. Compute the list of paper IDs already on disk:
   ```python
   from pathlib import Path
   pre_batch_paper_ids = [Path(p).stem for p in sorted(Path(wiki_root, "wiki/papers").glob("*.md"))]
   ```
2. Compute the current backlink target set:
   ```python
   from academic_wiki_lib.pre_batch_snapshot import scan_targets
   backlink_targets = scan_targets(wiki_root)
   ```
3. Write the snapshot file (`outputs/.pre-batch-snapshot.yml`):
   ```python
   from academic_wiki_lib.pre_batch_snapshot import write_snapshot
   write_snapshot(wiki_root, backlink_targets)
   ```
4. Store `pre_batch_paper_ids` in the checkpoint at creation time:
   ```python
   create_checkpoint(..., tier='full', pre_batch_paper_ids=pre_batch_paper_ids)
   ```

This step is skipped for paper-only batches and skipped on resume (snapshot already exists from the original run; see *Resume flow* for missing-snapshot handling).

### Subagent dispatch

For each wave, spawn all subagents **in a single message** (parallel tool calls) using the Agent tool:

- `model: "haiku"`
- `mode: "auto"`
- `run_in_background: true`
- **Template selection:** use `references/batch-compile-full-prompt.md` for full-tier batches; use `references/batch-compile-prompt.md` for paper-only batches.
- For **full-tier**, the orchestrator interpolates these placeholders before dispatch:
  - `{{WIKI_ROOT}}` — absolute path to the wiki root
  - `{{PAPER_LIST}}` — one `<paper-id> <extract-path>` line per entry for this subagent's batch
  - `{{PRE_BATCH_PAPERS}}` — comma-separated `pre_batch_paper_ids` list from the checkpoint (the prompt's Step 6/8 snippets parse with `.split(',')`)
  - `{{PRE_BATCH_SNAPSHOT_PATH}}` — absolute path to `outputs/.pre-batch-snapshot.yml`
  - `{{PYTHONPATH}}` — path to insert at `sys.path[0]` so subagents can import `academic_wiki_lib`
  - `{{TODAY}}` — ISO date string (e.g. `2026-04-23`)
- For **paper-only**, interpolate only `{{WIKI_ROOT}}` and `{{PAPER_LIST}}` (as before).

Wait for all subagents in the wave to complete before proceeding (Claude Code notifies on completion).

### Result collection

After all subagents in a wave finish:

1. Parse each subagent's return text for `ok:` and `failed:` lines.
2. For full-tier waves, also parse the four auxiliary counter lines (`entities: N created, M merged`, `cites: K resolved`, `backlinks: L inserted`, `cross-paper: X candidates`) from each subagent's RESULTS block. Accumulate sums in memory — these drive the per-wave console line (e.g. `Wave 3/10 complete: 98 ok, 2 failed. +218 entities, +512 cites, +104 backlinks, +41 cross-paper candidates.`) and feed the roll-up described in "Finalize (full-tier)".
3. Call `update_paper_statuses()` with the aggregated ok/failed results.
4. Stage and commit the wave:
   ```bash
   git -C "$WIKI_ROOT" add wiki/papers/ wiki/venues/ wiki/concepts/ wiki/methods/ wiki/open-problems/ outputs/.compile-checkpoint.yml outputs/reports/
   git -C "$WIKI_ROOT" commit -m "compile: wave N/M (X papers, Y ok, Z failed)"
   ```
   Note: paper-only tier never writes to `wiki/concepts/`, `wiki/methods/`, `wiki/open-problems/`, or `outputs/reports/`, so the extra paths are harmless no-ops for that tier.

### Retry wave

After all main waves complete:

1. Collect papers with `failed` status via `get_pending_papers()`.
2. If any exist, spawn one more wave of subagents for retry (same dispatch logic).
3. Papers that fail the retry wave stay `failed` — print the list for the user. Do not raise an error.

### Final orchestrator pass (full-tier only)

After all subagent waves (including any retry wave) complete for a **full-tier** batch, the orchestrator runs one additional sequential pass before squashing:

1. **Transition state:** call `update_final_pass_status(wiki_root, 'in-progress')` to record that the pass has started (allows clean resume if interrupted).

2. **Intra-batch cites:** for each paper in the batch that has status `ok` in the checkpoint:
   - Re-read that paper's `references-raw` frontmatter field.
   - Call `resolve_cites(wiki_root, refs, batch_paper_ids)` where `batch_paper_ids` is the set of all `ok` paper IDs in the current checkpoint. The helper fuzzy-matches each raw reference against both pre-existing and newly-created paper pages.
   - Append approved matches to the paper's `cites:` list (dedup, preserve order). Write the updated frontmatter back to disk.

3. **Intra-batch backlinks:** discover entity pages created during this batch by diffing against the squash base:
   ```bash
   git -C "$WIKI_ROOT" log --diff-filter=A --name-only <squash-base>..HEAD -- wiki/concepts/ wiki/methods/ wiki/open-problems/
   ```
   For each newly-created entity page, derive its slug from the filename stem, then call `insert_backlink(wiki_root, target_path, entity_slug)` against each in-batch paper page to add `[[entity-slug]]` wikilinks where appropriate.

4. **On success:**
   - Call `update_final_pass_status(wiki_root, 'ok')`.
   - Commit: `compile: final pass (intra-batch cites + backlinks)`.

5. **On any exception:**
   - Call `update_final_pass_status(wiki_root, 'failed')`.
   - Do **not** squash; surface the exception to the user with full traceback.
   - Resume will re-run the entire final pass (all steps are idempotent — dedup guards prevent duplicate `cites:` entries or double-inserted wikilinks).

### Squash and finalize

When all papers are `ok`:

1. `git reset --soft <squash-base>` then commit with a single compile message.
2. If the squash fails: print a warning, keep the per-wave commits, and proceed with bookkeeping.
3. Update `wiki/index.md` — append new papers under `## Uncategorized` (same as `--paper-only` mode step 10).
4. Append to `log.md`: `## [YYYY-MM-DD] compile | N paper pages created/updated`.
5. Delete the checkpoint file.
6. Final commit: `compile: update index + log (N papers)`.

### Resume flow

Triggered when `read_checkpoint()` finds an existing checkpoint with `status: in-progress`.

1. Call `is_stale()` on the checkpoint — if stale, prompt the user before continuing.
2. Re-scan for new papers via `find_all_extracts(wiki_root)` (covers both `raw/extracts/` and `raw/papers/*/` clipper directories); append any new paper-ids not in the checkpoint to the pending list.
3. Continue from `last-completed-wave + 1`, skipping any `paper_id` already marked `ok` in the checkpoint.
4. If `tier: full`, use `references/batch-compile-full-prompt.md` for all subagent dispatch on resume (same as the original run).
5. **Validate previously-ok papers:** for each paper marked `ok` in the checkpoint, verify that `wiki/papers/<paper-id>.md` still exists on disk. If any are missing (e.g. user deleted files between runs), demote their status back to `pending` and include them in the next dispatch wave. Emit a `stderr` warning line for each demoted paper.
6. **Fast-path to final pass:** if `final-pass-status` is `pending` or `failed` AND all papers in the checkpoint are `ok` (none are `pending` or `failed`), skip subagent dispatch entirely and jump straight to the *Final orchestrator pass* step.
7. **Missing snapshot handling:** if `outputs/.pre-batch-snapshot.yml` does not exist on resume (e.g. deleted by the user), re-derive the backlink targets via `pre_batch_snapshot.scan_targets(wiki_root)` and write a fresh snapshot with a warning: `"Warning: .pre-batch-snapshot.yml missing; re-derived from current vault state — backlink target set may drift from batch-start state, but resume will proceed."` The `pre_batch_paper_ids` in the checkpoint are authoritative and are **not** re-derived.

### Finalize (full-tier)

After the final orchestrator pass reaches `final-pass-status: ok`:

1. **Delete the snapshot file:**
   ```python
   from academic_wiki_lib.pre_batch_snapshot import delete_snapshot
   delete_snapshot(wiki_root)   # removes outputs/.pre-batch-snapshot.yml
   ```

2. **Proceed with squash + bookkeeping** using the existing *Squash and finalize* flow (same steps, applies to both tiers). For full-tier, step 3 (index rebuild) uses the full-mode path from step 10 of *Shared final steps*: rebuild `wiki/index.md` by `field/*` tag rather than appending under `## Uncategorized`.

3. **Roll up aggregate counters** from all subagent RESULTS blocks across all waves and include them in the `log.md` entry and the final console output line:

   | Counter | Source |
   |---|---|
   | `entities` | total entity pages created (concepts + methods + open-problems) |
   | `cites` | total `cites:` entries resolved across all papers |
   | `backlinks` | total wikilinks inserted by `insert_backlink` in the final pass |
   | `cross-paper` | total cross-paper promotion candidates written to `outputs/reports/` |

   Example log line:
   ```
   ## [2026-04-23] compile | 42 papers | 18 entities | 134 cites | 67 backlinks | 3 cross-paper candidates
   ```
