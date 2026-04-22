# Batch Compile Design

**Date:** 2026-04-22
**Status:** Draft
**Problem:** Compiling 1000+ papers fills Claude Code's context window and has no resume mechanism.

## 1. Architecture

Batch compile adds a two-layer architecture to the existing `compile` command.

### Orchestrator (main context)

Lightweight coordinator that never touches paper content directly:

1. Acquires wiki lockfile (`op=compile`)
2. Reads or creates checkpoint at `outputs/.compile-checkpoint.yml`
3. Scans `raw/extracts/*.md` vs `wiki/papers/*.md` to build the pending list
4. Partitions pending papers into waves of ~200 (10-15 subagents x 15-20 papers each)
5. Spawns Sonnet subagents in parallel per wave (`run_in_background: true`)
6. Collects results as agents complete, updates checkpoint, commits wave
7. After all waves: retries failed papers once, squashes wave commits, updates `wiki/index.md` + `log.md`
8. Releases lockfile

### Compiler subagent (Sonnet)

Self-contained agent that reads extracts and writes paper pages:

- Receives: wiki path, list of paper-ids, compilation rules + frontmatter schema
- For each paper-id: reads extract, optionally reads notes, generates paper page, writes to disk
- Returns: short status summary (`ok: id1, id2, ...` / `failed: id3 (reason)`)
- Does NOT touch: checkpoint, index.md, log.md, git

### Routing

```
compile [<paper-id>] [--paper-only]
  |
  +-- Single paper-id given? --> existing sequential path (unchanged)
  |
  +-- No paper-id (batch mode)?
       |
       +-- Checkpoint exists (status: in-progress)? --> resume flow
       |
       +-- No checkpoint? --> scan extracts vs papers
            |
            +-- <=5 papers to compile --> existing sequential path
            |
            +-- >5 papers to compile --> batch mode
```

Batch mode threshold: **>5 pending papers**. Below that, the subagent/checkpoint overhead is not justified.

Single-paper compile (`compile <paper-id>`) is completely unchanged.

## 2. Checkpoint Format

**File:** `outputs/.compile-checkpoint.yml`

```yaml
run-id: "2026-04-22T14:30:00Z"
status: in-progress          # in-progress | completed | failed
total: 1024
wave-size: 200
current-wave: 3
papers:
  abdullatifIcc20242024: ok
  abhijan202517thInternational2025: ok
  acamporaSemanticViewFlexible2006: failed
  ahmadSemanticCommunicationCooperative2024: pending
errors:
  acamporaSemanticViewFlexible2006: "subagent timeout after 120s"
squash-base: "abc1234"       # commit SHA before first wave
wave-commits:
  - "def5678"
  - "ghi9012"
```

### Lifecycle

1. **Create** -- orchestrator creates checkpoint at start. All pending papers set to `pending`. Records `squash-base` as current HEAD.
2. **Update after each wave** -- flip completed papers to `ok` or `failed`, append wave commit SHA, bump `current-wave`.
3. **Resume** -- if `compile` is invoked and a checkpoint with `status: in-progress` exists, skip `ok` papers, retry `failed` papers, continue from `current-wave`.
4. **Complete** -- after all waves finish, set `status: completed`, squash wave commits, delete checkpoint file.
5. **Stale detection** -- if checkpoint `run-id` is >24h old and status is `in-progress`, warn user and ask whether to resume or start fresh.

## 3. Subagent Design

### Prompt contents (self-contained)

Each subagent prompt includes:

- `WIKI_ROOT` path
- List of paper-ids to compile (15-20 per agent)
- Paper page frontmatter schema (type, fields, allowed values)
- Body section template: Metadata / Summary / Key Contributions / Methods / Results / Claims / User Notes / See Also
- Rules for deriving: `citation-key` (BibTeX-native, no hyphens), `authors` slugs (ASCII-folded, hyphenated), `tags` (field/*, method/*, year/YYYY, venue/slug), `status` (read if notes present and >200 chars, else skimmed)
- Update conflict policy: preserve prior claims, append new evidence, flag contradictions with `[!WARNING]` callouts, never replace without provenance

### Subagent parameters

- `model: "sonnet"` -- cheaper and fast enough for structured generation from small extracts
- `mode: "auto"` -- needs Read + Write file permissions
- `run_in_background: true` -- orchestrator gets notified on completion
- No git, no checkpoint writes, no index.md edits

### Subagent return format

```
RESULTS:
ok: paper-id-1, paper-id-2, paper-id-3
failed: paper-id-7 (extract file missing), paper-id-12 (empty extract)
```

### Concurrency

- 10-15 subagents spawned in a single message (parallel tool calls)
- Each subagent handles 15-20 papers
- One wave = 10-15 subagents x 15-20 papers = ~200 papers
- For 1000 papers: ~5 waves

## 4. Git Commit Strategy

### During the run: one commit per wave

After all subagents in a wave complete and checkpoint is updated:

```bash
git -C "$WIKI_ROOT" add wiki/papers/ outputs/.compile-checkpoint.yml
git -C "$WIKI_ROOT" commit -m "compile: wave 3/5 (200 papers, 198 ok, 2 failed)"
```

### On success: squash + finalize

Step 1 -- squash wave commits:

```bash
git -C "$WIKI_ROOT" reset --soft <squash-base>
git -C "$WIKI_ROOT" commit -m "compile: paper-only 1024 papers"
```

Step 2 -- bookkeeping commit:

```bash
# Update wiki/index.md, append to log.md, delete checkpoint
git -C "$WIKI_ROOT" add wiki/index.md log.md outputs/
git -C "$WIKI_ROOT" commit -m "compile: update index + log (1024 papers)"
```

### On partial failure

No squash. Wave commits stay as-is. Checkpoint remains with `status: in-progress`. Next `compile` picks up where it left off. Squash only happens when all papers reach `ok` or user explicitly accepts.

## 5. Error Handling and Resume

### Subagent failures

- **Partial failure**: subagent returns with some papers `failed`. Those papers get marked `failed` in checkpoint with error. Wave still counts as complete.
- **Subagent timeout/crash**: all its assigned papers marked `failed` with `"subagent timeout"`. Orchestrator continues to next wave.
- **Retry wave**: after main waves finish, failed papers are collected and retried in a single retry wave. If they fail again, they stay `failed` and user is told which papers need manual attention.

### Orchestrator failures (conversation dies mid-run)

Wave commits in git protect completed work. On next `compile`:

1. Orchestrator finds `outputs/.compile-checkpoint.yml` with `status: in-progress`
2. Prints: `Resuming compile from wave 3/5 (600/1024 done, 2 failed, 422 pending). Continue? [y/n]`
3. On `y`: picks up from pending papers, reuses `squash-base` and `wave-commits` list
4. On `n`: asks whether to abort (delete checkpoint, reset to squash-base) or keep for later

### Stale checkpoint (>24h old)

Prints: `Stale compile checkpoint found (started <timestamp>). Resume or start fresh?`

- Resume: continues as above
- Start fresh: deletes checkpoint, resets to `squash-base` if wave commits exist, begins from scratch

### New papers ingested during paused compile

On resume, orchestrator re-scans `raw/extracts/` to detect new extracts added since checkpoint creation. New papers are appended to pending list, `total` is updated.

## 6. Skill Integration

### Changes to SKILL.md compile section

The existing steps 1-7 are wrapped in the routing layer described in Section 1. Batch mode adds:

- Checkpoint read/write logic (inline Python using `yaml` module)
- Wave partitioning logic
- Subagent spawning loop
- Result collection and checkpoint update
- Squash and finalize logic

### New reference file

`references/batch-compile-prompt.md` -- contains the subagent prompt template with:

- Frontmatter schema for paper pages
- Body section template
- Compilation rules (citation-key derivation, slug generation, tag inference, status rules)
- Update conflict policy
- Expected return format

### What stays the same

- Single-paper compile path -- untouched
- Paper page output format -- identical from subagent or main context
- Lockfile semantics -- acquired at start, released at end
- Update conflict policy -- subagents follow same rules
- `--paper-only` flag -- batch mode is paper-only tier only

### User-facing output

```
Found 1024 papers to compile (0 from checkpoint).
Starting batch compile: 5 waves x ~200 papers, 12 parallel Sonnet subagents per wave.

Wave 1/5: spawning 12 subagents (204 papers)...
  Wave 1 complete: 202 ok, 2 failed. Committed.
Wave 2/5: spawning 12 subagents (204 papers)...
  Wave 2 complete: 204 ok, 0 failed. Committed.
...
Wave 5/5: spawning 10 subagents (208 papers)...
  Wave 5 complete: 208 ok, 0 failed. Committed.

Retrying 2 failed papers...
  Retry complete: 2 ok.

Squashing 5 wave commits...
Updating index.md and log.md...

compile: 1024 papers compiled (1024 ok, 0 failed).
```

## 7. Constraints and Limits

- **Batch mode is paper-only tier only.** Wave 2 full-tier batch (entity extraction, cites resolution, backlinks) is future work.
- **Concurrent subagents capped at 15.** Higher risks resource exhaustion in Claude Code.
- **Papers per subagent capped at 20.** Keeps each subagent's context small (~34KB input).
- **Retry is one attempt only.** Papers that fail twice require manual investigation.
- **Lockfile held for entire batch run.** No other wiki operations (ingest, lint, etc.) can run concurrently. This is acceptable since batch compile is a bulk operation.
