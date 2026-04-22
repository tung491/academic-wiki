# Batch Compile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable the academic wiki `compile` command to handle 1000+ papers using wave-based parallel Sonnet subagents with checkpointing and resumability.

**Architecture:** Orchestrator (main context) partitions pending papers into waves, spawns 10-15 parallel Sonnet subagents per wave (each handling 15-20 papers), collects results, commits per wave, and squashes on completion. A checkpoint file in the wiki enables resume after crashes.

**Tech Stack:** Python (checkpoint module), Markdown skill files (SKILL.md, compilation-guide.md, batch-compile-prompt.md), Claude Code Agent tool (Sonnet subagents)

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `scripts/academic_wiki_lib/checkpoint.py` | Checkpoint YAML read/write/update |
| Create | `tests/test_checkpoint.py` | Unit tests for checkpoint module |
| Create | `skills/wiki/references/batch-compile-prompt.md` | Self-contained subagent prompt template |
| Modify | `skills/wiki/references/compilation-guide.md` | Add batch orchestration section |
| Modify | `skills/wiki/SKILL.md` | Add routing, resume, batch steps to compile section |

---

### Task 1: Checkpoint Module

**Files:**
- Create: `scripts/academic_wiki_lib/checkpoint.py`
- Create: `tests/test_checkpoint.py`

- [ ] **Step 1: Write failing tests for checkpoint create/read/write**

```python
# tests/test_checkpoint.py
"""Tests for compile checkpoint management."""
import os
import tempfile
from datetime import datetime, timezone

import pytest
import yaml

from academic_wiki_lib.checkpoint import (
    create_checkpoint,
    read_checkpoint,
    write_checkpoint,
    update_paper_statuses,
    is_stale,
    CHECKPOINT_FILENAME,
)


@pytest.fixture
def wiki_dir(tmp_path):
    (tmp_path / "outputs").mkdir()
    return tmp_path


class TestCreateCheckpoint:
    def test_creates_file_with_correct_structure(self, wiki_dir):
        papers = [("paper-a", "/path/a.md"), ("paper-b", "/path/b.md")]
        cp = create_checkpoint(wiki_dir, papers, wave_size=2)

        assert cp["status"] == "in-progress"
        assert cp["total"] == 2
        assert cp["wave-size"] == 2
        assert cp["last-completed-wave"] == -1
        assert cp["papers"] == {"paper-a": "pending", "paper-b": "pending"}
        assert cp["errors"] == {}
        assert cp["wave-commits"] == []
        assert "run-id" in cp
        assert "squash-base" in cp

    def test_writes_to_disk(self, wiki_dir):
        papers = [("p1", "/path/p1.md")]
        create_checkpoint(wiki_dir, papers, wave_size=1)
        path = wiki_dir / "outputs" / CHECKPOINT_FILENAME
        assert path.exists()
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data["total"] == 1


class TestReadCheckpoint:
    def test_returns_none_when_no_file(self, wiki_dir):
        assert read_checkpoint(wiki_dir) is None

    def test_reads_existing_checkpoint(self, wiki_dir):
        papers = [("p1", "/x")]
        create_checkpoint(wiki_dir, papers, wave_size=1)
        cp = read_checkpoint(wiki_dir)
        assert cp is not None
        assert cp["total"] == 1


class TestUpdatePaperStatuses:
    def test_flips_statuses_and_records_errors(self, wiki_dir):
        papers = [("p1", "/x"), ("p2", "/y"), ("p3", "/z")]
        cp = create_checkpoint(wiki_dir, papers, wave_size=3)
        results = {"p1": ("ok", None), "p2": ("failed", "empty extract"), "p3": ("ok", None)}
        update_paper_statuses(wiki_dir, results, wave_commit_sha="abc123")
        cp = read_checkpoint(wiki_dir)
        assert cp["papers"]["p1"] == "ok"
        assert cp["papers"]["p2"] == "failed"
        assert cp["papers"]["p3"] == "ok"
        assert cp["errors"]["p2"] == "empty extract"
        assert cp["last-completed-wave"] == 0
        assert cp["wave-commits"] == ["abc123"]


class TestIsStale:
    def test_not_stale_when_recent(self, wiki_dir):
        papers = [("p1", "/x")]
        create_checkpoint(wiki_dir, papers, wave_size=1)
        assert is_stale(wiki_dir) is False

    def test_stale_when_old(self, wiki_dir):
        papers = [("p1", "/x")]
        cp = create_checkpoint(wiki_dir, papers, wave_size=1)
        # Manually backdate the run-id
        cp["run-id"] = "2020-01-01T00:00:00Z"
        write_checkpoint(wiki_dir, cp)
        assert is_stale(wiki_dir) is True


class TestDeleteCheckpoint:
    def test_delete_removes_file(self, wiki_dir):
        from academic_wiki_lib.checkpoint import delete_checkpoint
        papers = [("p1", "/x")]
        create_checkpoint(wiki_dir, papers, wave_size=1)
        delete_checkpoint(wiki_dir)
        assert read_checkpoint(wiki_dir) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_checkpoint.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'academic_wiki_lib.checkpoint'`

- [ ] **Step 3: Implement checkpoint module**

```python
# scripts/academic_wiki_lib/checkpoint.py
"""Compile checkpoint management for batch mode."""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import yaml

CHECKPOINT_FILENAME = ".compile-checkpoint.yml"
STALE_THRESHOLD = timedelta(hours=24)


def _checkpoint_path(wiki_root) -> Path:
    return Path(os.fspath(wiki_root)) / "outputs" / CHECKPOINT_FILENAME


def create_checkpoint(
    wiki_root,
    papers: list[tuple[str, str]],
    wave_size: int,
    squash_base: str = "",
) -> dict[str, Any]:
    """Create a new checkpoint file. Returns the checkpoint dict."""
    cp: dict[str, Any] = {
        "run-id": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "in-progress",
        "total": len(papers),
        "wave-size": wave_size,
        "last-completed-wave": -1,
        "papers": {pid: "pending" for pid, _ in papers},
        "errors": {},
        "squash-base": squash_base,
        "wave-commits": [],
    }
    write_checkpoint(wiki_root, cp)
    return cp


def read_checkpoint(wiki_root) -> dict[str, Any] | None:
    """Read checkpoint from disk. Returns None if no checkpoint exists."""
    path = _checkpoint_path(wiki_root)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def write_checkpoint(wiki_root, cp: dict[str, Any]) -> None:
    """Write checkpoint dict to disk."""
    path = _checkpoint_path(wiki_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(cp, f, sort_keys=False, allow_unicode=True, default_flow_style=False)


def update_paper_statuses(
    wiki_root,
    results: dict[str, tuple[str, str | None]],
    wave_commit_sha: str,
) -> None:
    """Update paper statuses from subagent results and bump wave counter.

    results: {paper_id: ("ok"|"failed", error_message_or_None)}
    """
    cp = read_checkpoint(wiki_root)
    if cp is None:
        raise FileNotFoundError("No checkpoint found")
    for pid, (status, error) in results.items():
        cp["papers"][pid] = status
        if error:
            cp["errors"][pid] = error
    cp["last-completed-wave"] += 1
    cp["wave-commits"].append(wave_commit_sha)
    write_checkpoint(wiki_root, cp)


def is_stale(wiki_root) -> bool:
    """True if checkpoint exists and is older than STALE_THRESHOLD."""
    cp = read_checkpoint(wiki_root)
    if cp is None:
        return False
    try:
        run_time = datetime.fromisoformat(cp["run-id"].replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - run_time > STALE_THRESHOLD
    except (KeyError, ValueError):
        return True


def delete_checkpoint(wiki_root) -> None:
    """Delete the checkpoint file if it exists."""
    path = _checkpoint_path(wiki_root)
    if path.exists():
        path.unlink()


def get_pending_papers(wiki_root) -> list[str]:
    """Return paper-ids that are still pending or failed (for retry)."""
    cp = read_checkpoint(wiki_root)
    if cp is None:
        return []
    return [pid for pid, status in cp["papers"].items() if status in ("pending", "failed")]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_checkpoint.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/academic_wiki_lib/checkpoint.py tests/test_checkpoint.py
git commit -m "feat(checkpoint): add compile checkpoint module for batch mode"
```

---

### Task 2: Subagent Prompt Template

**Files:**
- Create: `skills/wiki/references/batch-compile-prompt.md`

The subagent prompt template is the most critical piece — it's the self-contained instructions each Sonnet subagent receives. It must include everything needed to compile papers without access to SKILL.md or the compilation guide.

- [ ] **Step 1: Write the prompt template**

Create `skills/wiki/references/batch-compile-prompt.md` with the following structure. This is a reference document read by the orchestrator (SKILL.md) and interpolated with runtime values before dispatch.

The template must contain:

1. **Role and constraints** — you are a paper compiler subagent, you only read extracts and write paper pages, you do NOT touch git/checkpoint/index/log
2. **Input format** — `WIKI_ROOT` path and list of `{paper-id, extract-path}` tuples
3. **Paper page frontmatter schema** — verbatim from entity-schemas.md §3.1 paper type, including all fields and allowed values
4. **Body section template** — the 8 sections (Metadata through See Also) with guidance on what each contains
5. **Derivation rules:**
   - `citation-key`: strip hyphens from paper-id (e.g., `vaswani-2017-attention` → `vaswani2017attention`)
   - `authors`: parse from extract, generate slugs via ASCII-fold + lowercase + hyphenate
   - `tags`: always include `year/<YYYY>` and `venue/<slug>` if available; LLM infers `field/*`, `method/*`
   - `status`: `read` if `raw/notes/<paper-id>.md` exists and >200 chars, else `skimmed`
   - `venue`: slug form (lowercase, hyphenated)
6. **Venue page upsert** — after writing each paper page, ensure `wiki/venues/<venue-slug>.md` exists and includes this paper. New venue pages get minimal frontmatter (`type: venue`, `name`, `slug`, `venue-type`, `papers: [<paper-id>]`, `tags`, `created`, `updated`). Existing venue pages get the paper-id appended to `papers:` and field tags unioned into `tags:`. **Important:** subagents are LLM agents, not Python scripts. Venue upsert rules must be expressed as prose instructions (read file, check if exists, write/update frontmatter fields), NOT as Python `academic_wiki_lib` function calls. The subagent reads and writes files via the Read/Write tools.
7. **Update conflict policy** — preserve prior claims, append new evidence, flag contradictions with `[!WARNING]`, never replace without provenance, bump `updated:`
8. **Return format** — `RESULTS:\nok: id1, id2\nfailed: id3 (reason)`

The template uses placeholder tokens like `{{WIKI_ROOT}}` and `{{PAPER_LIST}}` that the orchestrator replaces at dispatch time.

- [ ] **Step 2: Review the template for completeness**

Verify the template contains all information a Sonnet subagent needs to produce paper pages identical to those produced by the existing sequential compile path. Cross-check against:
- `skills/wiki/references/entity-schemas.md` §3.1 (paper frontmatter)
- `skills/wiki/references/compilation-guide.md` (per-source steps 1-5 + venue upsert 4b)
- A sample existing compiled page (e.g., `wiki/papers/abdullatifIcc20242024.md` in the live wiki)

- [ ] **Step 3: Commit**

```bash
git add skills/wiki/references/batch-compile-prompt.md
git commit -m "feat(skill): add batch compile subagent prompt template"
```

---

### Task 3: Update Compilation Guide

**Files:**
- Modify: `skills/wiki/references/compilation-guide.md`

Add the batch compile orchestration logic as a new section after the existing content.

- [ ] **Step 1: Add batch compile section to compilation-guide.md**

Append a `## Batch compile mode` section after the existing `## Update conflict policy` section. Content:

**Subsection: Activation**
- Batch mode activates when no `<paper-id>` argument is given AND pending paper count >5
- If a checkpoint exists with `status: in-progress`, enter resume flow instead
- Papers <=5: use existing sequential path (no subagents)

**Subsection: Checkpoint management**
- Use `academic_wiki_lib.checkpoint` module for all checkpoint operations
- Python invocation pattern (matching the existing helper invocation style from SKILL.md):
  ```bash
  "$PY" -c "
  import sys; sys.path.insert(0, '${PYTHONPATH}')
  from academic_wiki_lib.checkpoint import create_checkpoint, read_checkpoint
  ..."
  ```
- Create checkpoint at start, recording `squash-base` as current HEAD SHA
- Update after each wave with subagent results
- Delete on successful completion

**Subsection: Wave partitioning**
- Use `find_all_extracts(wiki_root)` to get all `(paper_id, md_path)` tuples
- Filter out paper-ids already marked `ok` in checkpoint (resume case)
- Compare remaining against `wiki/papers/*.md` — only compile if extract is newer than paper page (by `extracted-at` vs `updated:`) or paper page doesn't exist
- Partition into waves. The checkpoint `wave-size` field stores **papers per wave** (not agent count). Target ~200 papers per wave: `papers_per_wave = min(len(pending), 15 * 20)` (15 subagents × 20 papers each = 300 max, but prefer ~200 for balance). For each wave, split into subagent batches of ~`ceil(papers_per_wave / 15)` papers each, capped at 20 per subagent.
- Each wave gets a list of subagent batches (lists of `{paper-id, extract-path}` tuples)

**Subsection: Subagent dispatch**
- For each wave, spawn subagents using the Agent tool with:
  - `model: "sonnet"`
  - `mode: "auto"`
  - `run_in_background: true`
  - Prompt: read `references/batch-compile-prompt.md`, replace `{{WIKI_ROOT}}` and `{{PAPER_LIST}}` with actual values
- All subagents in a wave are spawned in a single message (parallel tool calls)
- Wait for all subagents to complete (Claude Code notifies on completion)

**Subsection: Result collection**
- Parse each subagent's return text for `ok:` and `failed:` lines
- Call `update_paper_statuses()` with aggregated results
- Git add + commit wave: `git -C "$WIKI_ROOT" add wiki/papers/ wiki/venues/ outputs/.compile-checkpoint.yml`

**Subsection: Retry wave**
- After all main waves, collect papers with `failed` status via `get_pending_papers()`
- If any exist, spawn one more wave of subagents for retry
- Papers that fail retry stay `failed` — print list for user

**Subsection: Squash and finalize**
- On all papers `ok`: `git reset --soft <squash-base>` + commit
- If squash fails: print warning, keep wave commits, proceed with bookkeeping
- Update `wiki/index.md` (append new papers under `## Uncategorized`)
- Append to `log.md`: `## [YYYY-MM-DD] compile | N paper pages created/updated`
- Delete checkpoint file
- Final commit: `compile: update index + log (N papers)`

**Subsection: Resume flow**
- Detect existing checkpoint via `read_checkpoint()`
- Check staleness via `is_stale()` — if stale, prompt user
- Re-scan `raw/extracts/` for new papers added since checkpoint creation, append to pending list
- Continue from `last-completed-wave + 1`

- [ ] **Step 2: Verify no contradictions with existing content**

Re-read the full file to ensure the new batch section doesn't contradict the existing per-source steps, update conflict policy, or source discovery sections.

- [ ] **Step 3: Commit**

```bash
git add skills/wiki/references/compilation-guide.md
git commit -m "feat(skill): add batch compile orchestration to compilation guide"
```

---

### Task 4: Update SKILL.md Compile Section

**Files:**
- Modify: `skills/wiki/SKILL.md` (the `## compile [<paper-id>] [--paper-only]` section)

- [ ] **Step 1: Read the current compile section**

Read `skills/wiki/SKILL.md` to identify the exact location and content of the compile section (lines ~257-380 in the cached version).

- [ ] **Step 2: Add routing logic to the top of the compile section**

Insert a new subsection `### Routing` immediately after the compile heading and before `### Setup variables`. Content:

```markdown
### Routing

1. If `<paper-id>` is given: use the sequential path below (unchanged).
2. If no `<paper-id>`:
   a. Check for existing checkpoint via `read_checkpoint()`.
      - If found with `status: in-progress`: enter resume flow (see `references/compilation-guide.md` "Resume flow").
      - If found and stale (>24h): prompt user — resume or start fresh.
   b. If no checkpoint: scan pending papers via `find_all_extracts()` + compare against `wiki/papers/`.
      - If ≤5 pending: use sequential path below.
      - If >5 pending: enter batch mode (see `references/compilation-guide.md` "Batch compile mode").
```

- [ ] **Step 3: Add batch mode steps to the compile section**

After the existing "Steps (paper-only tier)" subsection, add a new subsection:

```markdown
### Steps (batch mode)

Batch mode replaces the per-paper loop with wave-based parallel subagents. Full orchestration logic is in `references/compilation-guide.md` "Batch compile mode". Summary:

1. **Acquire lockfile** (same as sequential path).
2. **Create or resume checkpoint** at `outputs/.compile-checkpoint.yml`.
3. **Partition pending papers into waves** (~200 papers per wave, 10-15 subagents per wave).
4. **For each wave:** spawn Sonnet subagents in parallel (`run_in_background: true`, `model: "sonnet"`, `mode: "auto"`). Each subagent receives a batch of `{paper-id, extract-path}` tuples and the self-contained prompt from `references/batch-compile-prompt.md`. Subagents write `wiki/papers/<paper-id>.md` and `wiki/venues/<venue-slug>.md` files directly.
5. **Collect results:** parse subagent output, update checkpoint, commit wave.
6. **Retry failed papers** in a single retry wave.
7. **Squash wave commits** into one commit (fall back to keeping wave commits if squash fails).
8. **Update index.md + log.md**, delete checkpoint, final commit.
9. **Release lockfile.**

Batch mode is paper-only tier only. `--paper-only` is implicit; Wave 2 full-tier batch is future work.
```

- [ ] **Step 4: Verify the SKILL.md is internally consistent**

Re-read the full compile section to ensure:
- Sequential path is untouched
- Routing correctly forks between sequential and batch
- Setup variables section still applies to both paths
- Lockfile/trap pattern still applies to both paths

- [ ] **Step 5: Commit**

```bash
git add skills/wiki/SKILL.md
git commit -m "feat(skill): add batch compile routing and steps to SKILL.md"
```

---

### Task 5: Integration Smoke Test

**Files:** None created — this is a manual verification task.

- [ ] **Step 1: Run the full test suite**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest -v`
Expected: All existing tests pass, new checkpoint tests pass.

- [ ] **Step 2: Verify checkpoint module works against real wiki**

```bash
cd /home/tung491/Work/academic_wiki
python -c "
import sys; sys.path.insert(0, 'scripts')
from academic_wiki_lib.checkpoint import create_checkpoint, read_checkpoint, delete_checkpoint
from academic_wiki_lib.wiki_paths import find_all_extracts

wiki = '$HOME/Documents/Obsidian Vault/03-Resources/academic'
extracts = find_all_extracts(wiki)
print(f'Found {len(extracts)} extracts')

# Dry run — create and immediately delete a checkpoint (try/finally for safety)
try:
    cp = create_checkpoint(wiki, extracts[:5], wave_size=5, squash_base='test')
    print(f'Checkpoint created: {cp[\"total\"]} papers, status={cp[\"status\"]}')
    cp2 = read_checkpoint(wiki)
    print(f'Read back: {cp2[\"total\"]} papers')
finally:
    delete_checkpoint(wiki)
    print('Checkpoint deleted')
"
```

Expected: Prints extract count (~1517), creates/reads/deletes checkpoint successfully.

- [ ] **Step 3: Verify subagent prompt template is complete**

Read `skills/wiki/references/batch-compile-prompt.md` and check that it contains all sections listed in Task 2 Step 1. Cross-reference one field from each category against the entity schema to confirm accuracy.

- [ ] **Step 4: Commit any fixes from smoke testing**

If any issues found during steps 1-3, fix and commit:
```bash
git add -u
git commit -m "fix: address issues found during batch compile smoke test"
```
