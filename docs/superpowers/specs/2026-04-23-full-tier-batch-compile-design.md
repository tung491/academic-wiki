# Full-Tier Batch Compile Design

**Date:** 2026-04-23
**Status:** Draft (rev 2 — review fixes)
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

Before the first wave spawns, the orchestrator records the state of the wiki at batch start. Two artifacts:

- **Small snapshot → checkpoint.** `pre-batch-paper-ids` (a list of paper-id strings) is stored directly in `outputs/.compile-checkpoint.yml`. On a wiki with thousands of pre-batch papers this stays under ~100KB, fine for a YAML checkpoint.
- **Large snapshot → disk file.** `pre-batch-backlink-targets` (the full list of wiki file paths for backlink scope) is written to `outputs/.pre-batch-snapshot.yml` as a separate file. Subagents receive the **path to this file** as `{{PRE_BATCH_SNAPSHOT_PATH}}` and read it themselves. Avoids embedding ~60KB of text directly in each subagent's prompt.

The orchestrator creates both artifacts at batch start and deletes `outputs/.pre-batch-snapshot.yml` alongside the checkpoint on successful completion. This makes subagent behavior deterministic regardless of how other subagents in the same wave make progress.

**Empty pre-batch corpus (fresh wiki).** If the wiki has no pre-existing paper pages or entity pages, `pre-batch-paper-ids` is `[]` and the snapshot file contains `targets: []`. Steps 6 (cites), 7 (backlinks), and 8 (cross-paper) become no-ops for every paper in the batch. The final pass (intra-batch) then carries the entire cites + backlinks load for the batch — this is expected and correct.

### 2.4 Final orchestrator pass

After all subagent waves (including the one retry wave) complete, the orchestrator runs one serial pass for intra-batch references:

1. **Intra-batch cites** — re-read each batch paper's `references-raw`, fuzzy-match against the set of paper-ids compiled in this batch (the `ok` set in the checkpoint), append matches to `cites:`.
2. **Intra-batch backlinks** — for each entity page created during this batch, scan the batch's paper pages for mentions of slug-words, insert `[[<slug>]]` where the ≥2-word / proper-noun rule fires.
3. Cross-paper intra-batch is skipped — accepts that sibling papers in the same batch may miss semantic-equivalence flags; lint surfaces the gap if needed.

**State machine for `final-pass-status`:**

- `skipped` — terminal state set at checkpoint creation when `tier='paper-only'`. The final pass is a no-op for paper-only batches.
- `pending` — initial state when `tier='full'`. Set when the checkpoint is created.
- `in-progress` — set by orchestrator when starting substeps.
- `ok` — all three substeps (intra-batch cites, intra-batch backlinks, cross-paper skip-note) completed successfully.
- `failed` — any substep raised. On resume the orchestrator treats `failed` the same as `pending` and re-runs the whole pass. Substep ops are idempotent (cites append dedups by paper-id, backlink insert is a no-op if `[[<slug>]]` is already at the target line), so a partial mid-pass failure leaves the wiki in a valid intermediate state that the re-run completes correctly.

A value of `skipped` must NOT be treated as `failed` or `pending` on resume — it indicates the tier does not need a final pass.

Commit: `compile: final pass (intra-batch cites + backlinks)`. Then squash and finalize as today.

Expected wall time on 1000 papers: ~30-60 seconds (mostly file I/O).

## 3. Entity lock module

**New file:** `scripts/academic_wiki_lib/entity_lock.py`

Uses POSIX `fcntl.flock` — advisory file locking with automatic release on process death.

### 3.1 Low-level API

```python
@contextmanager
def acquire(wiki_root, kind: str, key: str, timeout_seconds: float = 60.0):
    """Acquire exclusive fcntl.flock on <wiki_root>/.locks/<kind>/<key>.lock.

    kind: one of 'paper' | 'concept' | 'method' | 'open-problem' | 'venue' | 'reports'
    Raises TimeoutError past deadline; raises ValueError if kind is unrecognized.

    Timeout is implemented as a non-blocking retry loop:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline: raise TimeoutError
                time.sleep(0.1)
    (fcntl.flock in blocking mode supports no timeout, so we poll.)

    Lock auto-releases when the holding process exits (crash or clean), so
    "stale lock" is only possible if a process is alive but wedged. If that
    happens the user clears `<wiki_root>/.locks/` manually before retrying —
    no mtime-based auto-steal (which would be unsafe against a live holder).
    """
```

Lock files live in `<wiki_root>/.locks/<kind>/<key>.lock`. The `.locks/` directory is added to the wiki's `.gitignore`.

**Relationship to existing `lockfile.py`:** `entity_lock.py` is a separate module with a separate primitive (`fcntl.flock`) and separate file-path namespace (`.locks/<kind>/`). The existing `lockfile.py` — which protects against concurrent `ingest`/`compile`/`lint` at the wiki level using `O_CREAT|O_EXCL` on `<wiki_root>/.lock` — is unchanged and still acquired at batch start for the entire run. The two modules don't interact: the wiki-level lock is held by the orchestrator process for the full batch; the per-entity locks are held briefly by subagents inside that window. Because subagents are spawned as separate processes (not `fork()`s of the orchestrator), `fcntl.flock`'s per-process semantics do not apply adversely.

### 3.2 High-level helpers

**`scripts/academic_wiki_lib/entity_pages.py`:**

```python
def upsert_entity(wiki_root, slug, kind, paper_id, title, tags, body_contribution,
                  status_default="active") -> bool:
    """Create or merge into wiki/<kind>s/<slug>.md atomically.

    On create: render from §3 template with sources=[paper_id], tags, body_contribution.
    On update: append paper_id to sources (dedup), union tags, bump updated,
    append body_contribution as attributed paragraph per update conflict policy.

    Returns True if the page was created (caller should schedule backlink audit
    for this slug), False if the page existed and was merged into.
    """
    with entity_lock.acquire(wiki_root, kind, slug):
        # read-modify-write under lock
```

**`scripts/academic_wiki_lib/cites.py`:**

```python
def resolve_cites(wiki_root, references_raw, pre_batch_paper_ids):
    """Fuzzy-match each references_raw entry against pre-batch paper pages.
    Returns list of candidate (reference_string, paper_id, score) tuples for
    the subagent LLM to review.

    Algorithm:
      1. For each pre_batch_paper_id, read its page frontmatter via
         academic_wiki_lib.frontmatter.read_frontmatter to get
         (title, first_author_surname, year). Cache across a batch for speed.
      2. For each reference_string in references_raw, normalize (lower,
         strip punctuation).
      3. Score each candidate via token-set ratio against the candidate string
         "<title> <first_author_surname> <year>". All scores are normalized
         to the 0.0-1.0 range before comparison (rapidfuzz returns 0-100 by
         default — divide by 100; difflib.SequenceMatcher.ratio() is already
         0.0-1.0). Prefer rapidfuzz if installed; fall back to difflib.
      4. Keep candidates with normalized score >= 0.80. Among them, return
         up to 5 per reference sorted by score desc.

    No lock needed — caller (subagent) owns the paper page being updated.
    """
```

**`scripts/academic_wiki_lib/backlinks.py`:**

```python
def _target_lock_kind_and_key(target_path: str) -> tuple[str, str]:
    """Map a wiki file path to an (entity_lock kind, key) pair for locking.

    wiki/papers/<pid>.md        -> ("paper", <pid>)
    wiki/concepts/<slug>.md     -> ("concept", <slug>)
    wiki/methods/<slug>.md      -> ("method", <slug>)
    wiki/open-problems/<slug>.md -> ("open-problem", <slug>)
    wiki/venues/<slug>.md       -> ("venue", <slug>)

    Other paths raise ValueError.
    """


def insert_backlink(wiki_root, target_path: str, slug: str) -> bool:
    """Atomically insert [[<slug>]] into target_path where slug-words appear in prose,
    following the ≥2-word / proper-noun rule. No-op if [[<slug>]] already present.

    Implementation:
      1. Lock target_path via _target_lock_kind_and_key.
      2. Run `rg --fixed-strings -n "<slug with hyphens as spaces>" <target_path>`
         (subprocess). Bail out if zero matches.
      3. If slug is a single word AND none of the matches are a proper-noun
         noun-phrase, bail out (preserves existing no-single-word-common-nouns
         rule from sequential compile).
      4. Read target_path, modify first eligible match to include [[...]]
         around the original term, write back.

    Returns True if a backlink was inserted, False if skipped (already present
    or no eligible match).
    """
```

**`scripts/academic_wiki_lib/cross_paper.py`:**

```python
def compute_top_k_neighbors(wiki_root, paper_id, pre_batch_paper_ids, k=20):
    """Rank pre-batch papers by shared field/* and method/* tag count.

    Implementation:
      1. Read <wiki_root>/wiki/papers/<paper_id>.md frontmatter via
         academic_wiki_lib.frontmatter.read_frontmatter.
      2. For each pid in pre_batch_paper_ids, read its frontmatter from
         <wiki_root>/wiki/papers/<pid>.md. Missing files are skipped (the
         user may have deleted pages; that's handled in resume-validation
         elsewhere).
      3. Extract field/* and method/* tags from each; compute overlap.
      4. Sort (shared_count desc, year desc, paper_id asc). Return top k.

    Returns: list of paper-ids (strings), at most k entries.
    """

def append_candidates(wiki_root, entries):
    """Atomically append rendered candidate entries to outputs/reports/
    YYYY-MM-DD-promotion-candidates.md, deduping by (paper_a, paper_b, type)
    against the existing contents of the file before appending.

    Locks the report file via entity_lock.acquire(kind='reports',
    key='promotion-candidates').
    """
```

### 3.3 Contention estimate

Two contention hotspots:

**Popular entity page** (e.g., `attention-mechanism` in an NLP-heavy corpus, ~200 papers mention it):
- 10-15 subagents concurrent, each holds the lock ~50-200ms per merge.
- Worst-case queue on that slug: ~3s total across all subagents.

**Popular pre-batch backlink target** (e.g., a survey paper in `wiki/papers/` that mentions many concepts; many entity pages created across subagents want to backlink into it):
- 10-15 subagents concurrent, each holds ~50-200ms per insert.
- If a single page is the target for 30+ backlinks across a wave, worst-case queue ~6s.
- Mitigation: backlink target choice is sparse (≥2-word slug filter), so this is bounded.

Total batch wall time: ~20-40 min for 1000 papers. Aggregate lock wait <1% of wall time.

## 4. Subagent prompt template

### 4.1 Two templates side by side

- `skills/wiki/references/batch-compile-prompt.md` — paper-only (today's file; updated alongside this change to use `{{TODAY}}` instead of the hard-coded `2026-04-22` date that was baked into the existing prompt — a pre-existing latent bug)
- `skills/wiki/references/batch-compile-full-prompt.md` — **new**, full-tier

Orchestrator chooses based on whether `--paper-only` was set (or the checkpoint's `tier:` field on resume).

### 4.2 Full-tier template inputs

```
{{WIKI_ROOT}}                — absolute path to wiki root
{{PAPER_LIST}}               — this subagent's batch: paper-id + extract-path per line
{{PRE_BATCH_PAPERS}}         — comma-separated paper-ids that existed before batch start
{{PRE_BATCH_SNAPSHOT_PATH}}  — abs path to outputs/.pre-batch-snapshot.yml (subagent reads
                               the `targets:` list for backlink scope)
{{PYTHONPATH}}               — path to scripts/ for helper imports
{{TODAY}}                    — ISO date for `updated:` frontmatter
```

`{{PRE_BATCH_PAPERS}}` stays inline (short enough: 500 paper-ids ≈ 15KB). `{{PRE_BATCH_SNAPSHOT_PATH}}` replaces the earlier `{{PRE_BATCH_TARGETS}}` inline embed, so subagents read a local file instead of unpacking a 60KB prompt variable.

### 4.3 New steps (5-8) in the template

**Step 5 — Entity extraction.** For each paper:
- LLM scans the extract body for concept / method / open-problem mentions.
- For each entity: classify type, generate slug via `make_slug`, generate 1-3 paragraph `body_contribution` describing what this paper contributes to the entity.
- Call `upsert_entity(wiki_root, slug, kind, paper_id, title, tags, body_contribution)`. Helper locks atomically and returns `created: bool`.
- Track `created_entities: list[(slug, kind)]` in memory — these drive Step 7.

**Note on classification ambiguity.** If the same name is classified as both `concept` and `method` across different papers (or across different subagents), it becomes two separate pages with no cross-reference. The sequential path has the same issue. Lint's orphan + dead-link pass surfaces this for manual cleanup; the spec does not try to solve it here.

**Step 6 — Cites resolution.** For each paper:
- Helper `resolve_cites(wiki_root, references_raw, pre_batch_paper_ids)` returns up to 5 scored candidates per reference (token-set-ratio ≥ 0.80).
- LLM reviews candidates; writes approved matches to paper page's `cites:` (dedup by paper-id).

**Step 7 — Backlinks.** For each entry in `created_entities` (where `upsert_entity` returned `True`):
- Read `{{PRE_BATCH_SNAPSHOT_PATH}}` to get the `targets:` list. Optionally cache in memory after first read.
- For each target that mentions the entity's slug-words (LLM judgment after `rg --fixed-strings` pre-filter executed via Bash):
- Call `insert_backlink(wiki_root, target_path, slug)`. Helper locks target file atomically, skips if link already present.

**Step 8 — Cross-paper candidates.** For each paper:
- `top_k = compute_top_k_neighbors(wiki_root, paper_id, pre_batch_paper_ids, k=20)`.
- If `top_k` is empty or all have 0 tag overlap: skip (document as `cross-paper: 0 candidates (no tag overlap)`).
- Otherwise: read `## Claims` and `## Results` sections of each neighbor. LLM compares; flags only confident equivalence/contradiction.
- Accumulate candidate entries in memory until end of subagent run, then single `append_candidates(wiki_root, entries)` call (minimizes report-file lock contention).

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

### 4.5 Aggregation and user-facing summary

The orchestrator parses each subagent's `RESULTS:` block after a wave completes and sums the four auxiliary counters (`entities`, `cites`, `backlinks`, `cross-paper`) across all subagents in the batch. These aggregated totals appear:

1. **In the per-wave console line** — e.g., `Wave 3/10 complete: 98 ok, 2 failed. +218 entities, +512 cites, +104 backlinks, +41 cross-paper candidates.`
2. **In the final run summary** — rolled-up totals across all waves.
3. **In `log.md`** — appended alongside the existing `compile | N papers` line as a bullet summary.

The counters are not stored in the checkpoint — they're recomputed on resume from whichever waves have run so far.

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
pre-batch-paper-ids:         # snapshot at batch start (small: paper-ids only)
  - oldpaper1
  - oldpaper2
final-pass-status: pending   # pending | in-progress | ok | failed | skipped
```

`pre-batch-backlink-targets` is NOT in the checkpoint — it lives in `outputs/.pre-batch-snapshot.yml` to keep the checkpoint small.

**Size estimate:** 2000 pre-batch paper-ids ≈ 40-50KB YAML. Checkpoint stays under 100KB even on a heavily-populated wiki.

**`checkpoint.py` API change:**

Existing signature (keep the positional-or-keyword `squash_base=""` default to avoid breaking existing callers):

```python
def create_checkpoint(
    wiki_root,
    papers: list[tuple[str, str]],
    wave_size: int,
    squash_base: str = "",
    tier: str = "paper-only",               # NEW
    pre_batch_paper_ids: list[str] | None = None,  # NEW
) -> dict[str, Any]:
    """Write a new checkpoint to disk and return the dict.

    Concretely writes these new keys into the dict body:
      tier:                tier value (literal 'paper-only' or 'full')
      pre-batch-paper-ids: pre_batch_paper_ids if not None else []
                           (None is coerced to [] before writing; the YAML
                           always contains an explicit list, never null)
      final-pass-status:   'pending' if tier == 'full' else 'skipped'
    """
```

`read_checkpoint` is updated to default missing fields for back-compat with rev-1 checkpoints: `tier` → `"paper-only"`, `final-pass-status` → `"skipped"`, `pre-batch-paper-ids` → `[]`. No migration script — rev-1 checkpoints resume correctly as paper-only. A new `update_final_pass_status(wiki_root, status)` helper sets the `final-pass-status` key and writes; this is the single writer for that state transition.

**Resume flow additions:**

- `tier: paper-only` checkpoint → orchestrator uses today's paper-only template on resume.
- `tier: full` checkpoint → orchestrator uses `batch-compile-full-prompt.md` and reads `outputs/.pre-batch-snapshot.yml` (if missing, re-derives from current `wiki/` state with a warning).
- All papers `ok` but `final-pass-status: pending` → resume skips subagent work, runs only the final pass.
- `final-pass-status: failed` → re-run final pass.
- **Validation of previously-ok papers on resume:** orchestrator verifies each `ok` paper's `wiki/papers/<paper-id>.md` still exists. If missing (user deleted the file between runs), the paper is demoted to `pending` and re-compiled. One-line note logged to stderr so the user notices.

**Stale detection:** unchanged — 24h `run-id` threshold.

## 6. Cross-paper top-K details

### 6.1 Ranking

For paper P and pre-batch paper Q, compute:

- `P_tags = P.tags(field/*) ∪ P.tags(method/*)`
- `Q_tags = Q.tags(field/*) ∪ Q.tags(method/*)`
- `shared = |P_tags ∩ Q_tags|`

Exclude `year/*` and `venue/*` tags (too broad or too narrow). Primary sort: `shared` desc. Tie-break: `Q.year` desc. Final tie-break: `Q.paper-id` asc. Take top 20.

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

All mutating operations in the full-tier path are idempotent, so retry waves, resume, and the final-pass re-run path are safe:

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
| `scripts/academic_wiki_lib/entity_pages.py` | `upsert_entity()` helper (returns `created: bool`) |
| `scripts/academic_wiki_lib/cites.py` | `resolve_cites()` fuzzy-matcher (token-set-ratio ≥ 0.80) |
| `scripts/academic_wiki_lib/backlinks.py` | `_target_lock_kind_and_key()`, `insert_backlink()` |
| `scripts/academic_wiki_lib/cross_paper.py` | `compute_top_k_neighbors()`, `append_candidates()` |
| `skills/wiki/references/batch-compile-full-prompt.md` | Full-tier subagent prompt template |
| `tests/test_entity_lock.py` | Unit tests for lock module (concurrency, timeout) |
| `tests/test_entity_pages.py` | Unit tests for `upsert_entity` create + merge |
| `tests/test_cites.py` | Unit tests for fuzzy matcher (threshold, top-5 cap) |
| `tests/test_backlinks.py` | Unit tests for target-path → lock-key mapping + insertion rules |
| `tests/test_cross_paper.py` | Unit tests for top-K ranking + report append dedup |

### Modify

| Path | Change |
|------|--------|
| `scripts/academic_wiki_lib/checkpoint.py` | Extend `create_checkpoint` signature (add `tier`, `pre_batch_paper_ids`); add `final-pass-status` field; `read_checkpoint` defaults missing fields for back-compat |
| `tests/test_checkpoint.py` | Cover new fields + missing-field defaults |
| `skills/wiki/references/compilation-guide.md` | Update "Batch compile mode" — remove paper-only-only assertion, describe full-tier flow, final pass, extended wave commit paths |
| `skills/wiki/SKILL.md` | Compile routing: full-tier batch when no `--paper-only` + >5 pending; remove paper-only-only assertion |
| `skills/wiki/references/batch-compile-prompt.md` | Clarify this is paper-only template; replace hard-coded `2026-04-22` dates with `{{TODAY}}` |
| Wave commit in compilation-guide.md | Extend from `git add wiki/papers/ wiki/venues/ outputs/.compile-checkpoint.yml` to also include `wiki/concepts/ wiki/methods/ wiki/open-problems/ outputs/reports/` |
| Wiki template `.gitignore` | Add `.locks/` and `outputs/.pre-batch-snapshot.yml` |

## 9. Constraints and limits

- **Concurrent subagents per wave: 15** — higher risks Claude Code resource exhaustion.
- **Papers per subagent: 8-10** for full-tier (down from 15-20 for paper-only).
- **Retry: one attempt** — papers that fail retry stay `failed`; user investigates manually.
- **Lockfile held for entire batch run** — no other wiki ops run concurrently. Accepted for bulk operation.
- **Top-K=20** — fixed for now; tune after observing real run behavior.
- **Cross-paper: pre-batch only during subagent waves** — intra-batch cross-paper is skipped (not handled in final pass). Future work if needed.
- **Backlink audit scope: pre-batch targets + batch-level final pass** — same semantics as sequential compile output.
- **Entity kind disambiguation:** if the same name is classified as both `concept` and `method` (by different subagents or different papers), the result is two separate entity pages. Sequential compile has the same issue; lint surfaces it.

## 10. Rejected alternatives

- **Two-phase (parallel papers, serial enrichment).** Cleaner coordination but slower enrichment. Rejected: we want maximum parallelism for the 4 enrichment steps.
- **mkdir atomic locks.** Simpler than `fcntl.flock` but requires spin-wait polling and manual stale-lock cleanup. Rejected: `fcntl.flock` auto-releases on process death and integrates with Python idiomatically.
- **Granular per-step checkpoint (paper-page-done / entities-done / cites-done / ...).** More precise resume but ~5× more state to maintain. Rejected: per-paper ok/failed plus `final-pass-status` is sufficient because per-step ops are idempotent — retry is cheap.
- **Skip intra-batch final pass; let lint surface gaps.** Simplest but sacrifices intra-batch references permanently. Rejected — pre-batch snapshot + final pass was chosen.
- **Full O(N²) cross-paper.** Correct but prohibitive at 1000 papers. Rejected in favor of top-K=20 tag-overlap.
- **Embed `pre-batch-backlink-targets` inline in each subagent prompt.** Rejected after review — 60KB per subagent is unreliable as a prompt variable. Replaced with a snapshot file + path-reference.
- **mtime-based stale-lock auto-steal.** Rejected after review — incompatible with `fcntl.flock` semantics and unsafe against live holders.

## 11. Open questions / future work

- **Intra-batch cross-paper.** If users find the gap meaningful, a dedicated `/academic-wiki:wiki find-cross-paper-candidates` command could run post-batch.
- **Top-K tuning.** K=20 is a guess. Revisit after observing real run behavior.
- **Embedding-based neighbors.** Replacing tag overlap with embedding similarity (via `qmd`) would catch cross-field equivalents. Out of scope for v1.
- **Parallel final pass.** If final pass becomes slow on very large batches, split it into per-entity-page work with the existing lock mechanism.
- **Same-name concept/method disambiguation.** A dedicated lint pass (or interactive merge) could resolve entity splits when they arise.
