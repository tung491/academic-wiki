# Full-Tier Batch Compile Design

**Date:** 2026-04-23
**Status:** Draft
**Problem:** Today's batch compile is paper-only (SKILL.md §compile: "Batch mode is paper-only tier only. `--paper-only` is implicit; Wave 2 full-tier batch is future work."). On a 1000-paper wiki, `/academic-wiki:wiki compile` produces paper pages without the enrichment that sequential compile provides (entity extraction, cites resolution, backlink audit, cross-paper candidate detection). The user must either run a second pass paper-by-paper or never get the full wiki.

**Goal:** Extend batch mode so that `compile` (no flag) on >5 pending papers produces the same output as sequential full-tier compile, using wave-based parallel Sonnet subagents with per-entity-page locks, a pre-batch snapshot for deterministic cites/backlinks, and a single serial final pass for intra-batch references.

## 1. Non-goals

- Single-paper compile path (`compile <paper-id>`) is unchanged.
- Paper-only batch (`compile --paper-only`) is unchanged.
- Cross-paper candidate detection remains a non-destructive report; no auto-promotion.
- Full O(N²) cross-paper comparison is out of scope. We use top-K=20 tag-overlap bounding.
- No new wiki page types or frontmatter schema changes.

## 2. Architecture

### 2.1 Routing change

SKILL.md §compile routing currently activates batch mode on >5 pending papers and silently forces paper-only. After this change:

- `compile` (no flag) + >5 pending → **full-tier batch mode**
- `compile --paper-only` + >5 pending → paper-only batch mode (today's behavior)
- `compile <paper-id>` → sequential single-paper path (unchanged)
- ≤5 pending → sequential path (unchanged)
- Existing in-progress checkpoint → resume flow (new `tier:` field determines which template to use)

### 2.2 One-shot subagents

Each Sonnet subagent handles its assigned batch of 8–10 papers end-to-end through Steps 1–8:

1. Read extract + user notes
2. Derive frontmatter fields (authors, venue, tags, identifiers)
3. Write paper page
4. Venue page upsert
5. Entity extraction — `upsert_entity()` per detected concept/method/open-problem
6. Cites resolution against pre-batch snapshot
7. Backlink audit from newly-created entity pages into pre-batch targets
8. Cross-paper candidate detection — top-K=20 tag-overlap neighbors only

**Batch size:** reduced from 15-20 (paper-only) to **8-10 per subagent** because full-tier work is ~3× heavier. Total concurrency still capped at 15 subagents per wave.

**Wave size:** ~100 papers per wave (10 subagents × 10 papers). For 1000 pending, ~10 waves.

### 2.3 Pre-batch snapshot

Before the first wave spawns, the orchestrator records the state of the wiki at batch start:

- `pre-batch-paper-ids` — every paper-id in `wiki/papers/*.md`
- `pre-batch-backlink-targets` — every wiki file path (papers + entity pages) that existed at batch start

These snapshots are stored in the checkpoint and passed to each subagent. Subagents use them for cites matching (against `pre-batch-paper-ids`) and backlink insertion (into `pre-batch-backlink-targets`). This makes subagent behavior deterministic regardless of how other subagents in the same wave make progress.

### 2.4 Final orchestrator pass

After all subagent waves (including the one retry wave) complete, the orchestrator runs one serial pass for intra-batch references:

1. **Intra-batch cites** — re-read each batch paper's `references-raw`, fuzzy-match against the set of paper-ids compiled in this batch, append matches to `cites:`.
2. **Intra-batch backlinks** — for each entity page created during this batch, scan the batch's paper pages for mentions of slug-words, insert `[[<slug>]]` where the ≥2-word / proper-noun rule fires.
3. Cross-paper intra-batch is skipped — accepts that sibling papers in the same batch may miss semantic-equivalence flags; lint surfaces the gap if needed.

Commit: `compile: final pass (intra-batch cites + backlinks)`. Then squash and finalize as today.

Expected wall time on 1000 papers: ~30-60 seconds (mostly file I/O).

## 3. Entity lock module

**New file:** `scripts/academic_wiki_lib/entity_lock.py`

Uses POSIX `fcntl.flock` — advisory file locking with automatic release on process death (no stale-lock cleanup needed for crashed subagents).

### 3.1 Low-level API

```python
@contextmanager
def acquire(wiki_root, kind: str, key: str, timeout_seconds: float = 60.0):
    """Acquire lock at <wiki_root>/.locks/<kind>/<key>.lock.

    kind: 'concept' | 'method' | 'open-problem' | 'paper' | 'reports'
    Raises TimeoutError past deadline. If lock file mtime > 5 min old, steals
    it (covers wedged, not-dead processes).
    """
```

Lock files live in `<wiki_root>/.locks/<kind>/<key>.lock`. The `.locks/` directory is added to the wiki's `.gitignore`.

### 3.2 High-level helpers

**`scripts/academic_wiki_lib/entity_pages.py`:**

```python
def upsert_entity(wiki_root, slug, kind, paper_id, title, tags, body_contribution,
                  status_default="active"):
    """Create or merge into wiki/<kind>s/<slug>.md atomically.

    On create: render from §3 template with sources=[paper_id], tags, body_contribution.
    On update: append paper_id to sources (dedup), union tags, bump updated,
    append body_contribution as attributed paragraph per update conflict policy.
    """
    with entity_lock.acquire(wiki_root, kind, slug):
        # read-modify-write under lock
```

**`scripts/academic_wiki_lib/cites.py`:**

```python
def resolve_cites(wiki_root, references_raw, pre_batch_paper_ids):
    """Fuzzy-match each references_raw entry (title + first-author + year) against
    pre-batch paper pages. Returns list of matched paper-ids.

    No lock needed — caller (subagent) owns the paper page being updated.
    """
```

**`scripts/academic_wiki_lib/backlinks.py`:**

```python
def insert_backlink(wiki_root, target_path, slug):
    """Atomically insert [[<slug>]] into target_path where slug-words appear in prose,
    following the ≥2-word / proper-noun rule. No-op if [[<slug>]] already present.

    Locks the target file.
    """
    with entity_lock.acquire(wiki_root, _kind_of(target_path), _key_of(target_path)):
        # read-modify-write under lock
```

**`scripts/academic_wiki_lib/cross_paper.py`:**

```python
def compute_top_k_neighbors(wiki_root, paper_id, pre_batch_paper_ids, k=20):
    """Rank pre-batch papers by shared field/* and method/* tag count.

    Returns paper-ids sorted: (shared_count desc, year desc, paper_id asc).
    """

def append_candidates(wiki_root, entries):
    """Atomically append rendered candidate entries to outputs/reports/
    YYYY-MM-DD-promotion-candidates.md, deduping by (paper_a, paper_b, type).

    Locks the report file.
    """
```

### 3.3 Contention estimate

Popular entity (e.g., `attention-mechanism` in an NLP-heavy corpus, ~200 papers mention it):
- 10-15 subagents concurrent, each holds the lock ~50-200ms per merge.
- Worst-case queue on that slug: ~3s total across all subagents.
- Total batch wall time: ~20-40 min for 1000 papers. Lock wait <1% of wall time.

## 4. Subagent prompt template

### 4.1 Two templates side by side

- `skills/wiki/references/batch-compile-prompt.md` — paper-only (today's file, unchanged)
- `skills/wiki/references/batch-compile-full-prompt.md` — **new**, full-tier

Orchestrator chooses based on whether `--paper-only` was set (or the checkpoint's `tier:` field on resume).

### 4.2 Full-tier template inputs

```
{{WIKI_ROOT}}           — absolute path to wiki root
{{PAPER_LIST}}          — this subagent's batch: paper-id + extract-path per line
{{PRE_BATCH_PAPERS}}    — comma-separated paper-ids that existed before batch start
{{PRE_BATCH_TARGETS}}   — newline-separated wiki file paths that existed before batch start
{{PYTHONPATH}}          — path to scripts/ for helper imports
{{TODAY}}               — ISO date for `updated:` frontmatter
```

### 4.3 New steps (5-8) in the template

**Step 5 — Entity extraction.** For each paper:
- LLM scans the extract body for concept / method / open-problem mentions.
- For each entity: classify type, generate slug via `make_slug`, generate 1-3 paragraph `body_contribution` describing what this paper contributes to the entity.
- Call `upsert_entity(wiki_root, slug, kind, paper_id, title, tags, body_contribution)`. Helper locks atomically.

**Step 6 — Cites resolution.** For each paper:
- Helper `resolve_cites(references_raw, pre_batch_paper_ids)` returns candidate matches.
- LLM reviews matches for plausibility (author/year/title consistency); writes approved matches to paper page's `cites:`.

**Step 7 — Backlinks.** For each newly-created (not merged-into) entity page this subagent wrote:
- For each target in `PRE_BATCH_TARGETS` that mentions the entity's slug-words (detected by LLM after `rg` pre-filter):
- Call `insert_backlink(wiki_root, target_path, slug)`. Helper locks target file atomically.

**Step 8 — Cross-paper candidates.** For each paper:
- `top_k = compute_top_k_neighbors(paper_id, pre_batch_paper_ids, k=20)`
- If `top_k` is empty or all have 0 tag overlap: skip (document as `cross-paper: 0 candidates (no tag overlap)`).
- Otherwise: read `## Claims` and `## Results` sections of each neighbor. LLM compares; flags only confident equivalence/contradiction.
- Accumulate candidate entries in memory until end of subagent run, then single `append_candidates()` call (minimizes report-file lock contention).

### 4.4 Return format

```
RESULTS:
ok: <paper-id-1>, <paper-id-2>
failed: <paper-id-3> (reason)
entities: <N> created, <M> merged
cites: <K> resolved
backlinks: <L> inserted
cross-paper: <X> candidates
```

## 5. Checkpoint schema

Existing paper-only schema (kept as-is) plus three new fields:

```yaml
# Existing:
run-id: "2026-04-23T14:30:00Z"
status: in-progress          # in-progress | completed | failed
total: 1024
wave-size: 100               # papers per wave (was 200 for paper-only; smaller for full-tier)
last-completed-wave: 2
papers: {...}
errors: {...}
squash-base: "abc1234"
wave-commits: [...]

# NEW:
tier: full                   # paper-only | full — template selection on resume
pre-batch-paper-ids:         # snapshot at batch start
  - oldpaper1
  - oldpaper2
pre-batch-backlink-targets:  # wiki file paths that existed at batch start
  - wiki/papers/oldpaper1.md
  - wiki/concepts/existing-concept.md
final-pass-status: pending   # pending | ok | failed | skipped
```

**Size estimate:** 500 pre-batch papers + 500 entity pages = 1000 paths ≈ 60KB YAML. Well within reason.

**Resume flow additions:**

- `tier: paper-only` checkpoint → orchestrator uses today's paper-only template on resume.
- `tier: full` checkpoint → orchestrator uses `batch-compile-full-prompt.md`.
- All papers `ok` but `final-pass-status: pending` → resume skips subagent work, runs only the final pass.
- `final-pass-status: failed` → re-run final pass.

**Stale detection:** unchanged — 24h `run-id` threshold.

## 6. Cross-paper top-K details

### 6.1 Ranking

For paper P and pre-batch paper Q:
- `shared = |P.tags(field/*) ∪ P.tags(method/*) ∩ Q.tags(field/*) ∪ Q.tags(method/*)|`
- Exclude `year/*` and `venue/*` (too broad or too narrow).
- Primary sort: `shared` desc. Tie-break: Q.year desc. Final tie-break: Q.paper-id asc.
- Take top 20.

### 6.2 Zero-overlap edge case

If the top neighbor has 0 shared tags, skip cross-paper for that paper entirely. Report `cross-paper: 0 candidates (no tag overlap)`.

### 6.3 LLM comparison prompt guidance

Err conservative: "flag only if you'd expect a human researcher to agree this is the same claim restated or a direct contradiction." Over-flagging creates noise in the promotion-candidates report; under-flagging is recoverable.

### 6.4 Candidate entry format

Matches existing promotion-candidates.md convention:

```markdown
### Candidate: <short description>
- **Type:** claim | result
- **Paper A:** [[paper-id-1]] — "<quote>"
- **Paper B:** [[paper-id-2]] — "<quote>"
- **Relationship:** equivalent | contradiction
- **Action:** review — promote to wiki/<type>s/<slug>.md or leave as-is
```

### 6.5 Cost estimate

1000 papers × 20 neighbors = 20K LLM comparisons total. Distributed across ~100 subagents (10 papers each). Each subagent does ~200 comparisons. Wall time: ~3× paper-only batch for the same paper count.

## 7. Idempotency

All mutating operations in the full-tier path are idempotent, so retry waves and resume are safe:

- Paper page write → update conflict policy handles re-write
- `upsert_entity` → dedups paper-id in `sources:`, unions tags, appends attributed paragraph (already-present contribution re-adds; duplicate paragraph is cosmetic, no correctness loss)
- Cites append → dedup by paper-id
- Backlink insert → no-op if `[[<slug>]]` already present at the target line
- Cross-paper report → `append_candidates` dedups on read before append by `(paper_a, paper_b, type)` key

## 8. File changes

### Create

| Path | Purpose |
|------|---------|
| `scripts/academic_wiki_lib/entity_lock.py` | `fcntl.flock`-based per-entity locks |
| `scripts/academic_wiki_lib/entity_pages.py` | `upsert_entity()` helper |
| `scripts/academic_wiki_lib/cites.py` | `resolve_cites()` fuzzy-matcher |
| `scripts/academic_wiki_lib/backlinks.py` | `insert_backlink()` + helpers |
| `scripts/academic_wiki_lib/cross_paper.py` | `compute_top_k_neighbors()`, `append_candidates()` |
| `skills/wiki/references/batch-compile-full-prompt.md` | Full-tier subagent prompt template |
| `tests/test_entity_lock.py` | Unit tests for lock module |
| `tests/test_entity_pages.py` | Unit tests for `upsert_entity` merge logic |
| `tests/test_cites.py` | Unit tests for fuzzy matcher |
| `tests/test_backlinks.py` | Unit tests for backlink insertion rules |
| `tests/test_cross_paper.py` | Unit tests for top-K ranking + report append dedup |

### Modify

| Path | Change |
|------|--------|
| `scripts/academic_wiki_lib/checkpoint.py` | Add `tier`, `pre-batch-paper-ids`, `pre-batch-backlink-targets`, `final-pass-status` fields |
| `tests/test_checkpoint.py` | Cover new fields |
| `skills/wiki/references/compilation-guide.md` | Update "Batch compile mode" section — remove paper-only-only assertion, describe full-tier flow, final pass |
| `skills/wiki/SKILL.md` | Compile section routing: full-tier batch when no `--paper-only` flag + >5 pending; remove paper-only-only assertion |
| `skills/wiki/references/batch-compile-prompt.md` | Clarify this is paper-only template; full-tier lives in sibling file |
| Wiki template `.gitignore` | Add `.locks/` |

## 9. Constraints and limits

- **Concurrent subagents per wave: 15** — higher risks Claude Code resource exhaustion.
- **Papers per subagent: 8-10** for full-tier (down from 15-20 for paper-only).
- **Retry: one attempt** — papers that fail retry stay `failed`; user investigates manually.
- **Lockfile held for entire batch run** — no other wiki ops run concurrently. Accepted for bulk operation.
- **Top-K=20** — fixed for now; tune after observing real run behavior.
- **Cross-paper: pre-batch only during subagent waves** — intra-batch cross-paper is skipped (not handled in final pass). Future work if needed.
- **Backlink audit scope: pre-batch targets + batch-level final pass** — same semantics as sequential compile output.

## 10. Rejected alternatives

- **Two-phase (parallel papers, serial enrichment).** Cleaner coordination but slower enrichment. Rejected: we want maximum parallelism for the 4 enrichment steps.
- **mkdir atomic locks.** Simpler than `fcntl.flock` but requires spin-wait polling and manual stale-lock cleanup. Rejected: `fcntl.flock` auto-releases on process death and integrates with Python idiomatically.
- **Granular per-step checkpoint (paper-page-done / entities-done / cites-done / ...).** More precise resume but ~5× more state to maintain. Rejected: per-paper ok/failed plus `final-pass-status` is sufficient because per-step ops are idempotent — retry is cheap.
- **Skip intra-batch final pass; let lint surface gaps.** Simplest but sacrifices intra-batch references permanently. Rejected: you picked pre-batch snapshot + final pass in Q5.
- **Full O(N²) cross-paper.** Correct but prohibitive at 1000 papers. Rejected in favor of top-K=20 tag-overlap.

## 11. Open questions / future work

- **Intra-batch cross-paper.** If users find the gap meaningful, a dedicated `/academic-wiki:wiki find-cross-paper-candidates` command could run post-batch.
- **Top-K tuning.** K=20 is a guess. Revisit after observing real run behavior.
- **Embedding-based neighbors.** Replacing tag overlap with embedding similarity (via `qmd`) would catch cross-field equivalents. Out of scope for v1.
- **Parallel final pass.** If final pass becomes slow on very large batches, split it into per-entity-page work with the existing lock mechanism.
