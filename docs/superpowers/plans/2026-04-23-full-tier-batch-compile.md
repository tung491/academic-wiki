# Full-Tier Batch Compile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the academic-wiki `compile` command so that batch mode on >5 pending papers produces full-tier output (paper pages + entity extraction + cites + backlinks + cross-paper candidates), using wave-based parallel Sonnet subagents with `fcntl.flock`-based per-entity locks.

**Architecture:** New Python helpers (`entity_lock`, `entity_pages`, `cites`, `backlinks`, `cross_paper`) wrap atomic read-modify-write of shared wiki pages. Subagents receive a new full-tier prompt template that calls these helpers. A pre-batch snapshot (paper-ids in checkpoint, backlink targets in a separate YAML file) keeps subagent behavior deterministic. After all subagent waves complete, the orchestrator runs one serial final pass for intra-batch cites + backlinks.

**Tech Stack:** Python 3.11+ (`fcntl`, `yaml`, `difflib`, optional `rapidfuzz`), pytest, bash (skill files), existing `academic_wiki_lib.frontmatter`, `academic_wiki_lib.slug`, `academic_wiki_lib.checkpoint`, `academic_wiki_lib.lockfile`.

**Spec:** `docs/superpowers/specs/2026-04-23-full-tier-batch-compile-design.md`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `scripts/academic_wiki_lib/entity_lock.py` | `fcntl.flock` context manager for per-entity locks |
| Create | `tests/test_entity_lock.py` | Lock acquire/timeout/release tests |
| Modify | `scripts/academic_wiki_lib/checkpoint.py` | Add `tier`, `pre-batch-paper-ids`, `final-pass-status`; `update_final_pass_status` helper; read-defaults for old checkpoints |
| Modify | `tests/test_checkpoint.py` | Cover new fields + backward-compat |
| Create | `scripts/academic_wiki_lib/entity_pages.py` | `upsert_entity()` atomic create/merge, returns `created: bool` |
| Create | `tests/test_entity_pages.py` | upsert create, merge, dedup, tags-union |
| Create | `scripts/academic_wiki_lib/cites.py` | `resolve_cites()` fuzzy-matcher (normalized 0-1 score, threshold 0.80) |
| Create | `tests/test_cites.py` | Threshold, top-5 cap, ranking |
| Create | `scripts/academic_wiki_lib/backlinks.py` | `_target_lock_kind_and_key()`, `insert_backlink()` |
| Create | `tests/test_backlinks.py` | Target-path mapping, ≥2-word rule, no-op when link present |
| Create | `scripts/academic_wiki_lib/cross_paper.py` | `compute_top_k_neighbors()`, `append_candidates()` |
| Create | `tests/test_cross_paper.py` | Top-K ranking, dedup on append |
| Create | `scripts/academic_wiki_lib/pre_batch_snapshot.py` | Write/read `outputs/.pre-batch-snapshot.yml` |
| Create | `tests/test_pre_batch_snapshot.py` | Write/read round-trip |
| Create | `skills/wiki/references/batch-compile-full-prompt.md` | Full-tier subagent prompt template |
| Modify | `skills/wiki/references/batch-compile-prompt.md` | Replace hard-coded `2026-04-22` with `{{TODAY}}` (pre-existing latent bug fix) |
| Modify | `skills/wiki/references/compilation-guide.md` | Full-tier batch mode section, final pass, extended wave commit paths |
| Modify | `skills/wiki/SKILL.md` | Remove paper-only-only assertion, add full-tier routing |
| Modify | `scripts/academic_wiki_lib/templates.py` | Add `.locks/` and `outputs/.pre-batch-snapshot.yml` to `.gitignore` template |

---

## Task 1: Entity Lock Module

**Files:**
- Create: `scripts/academic_wiki_lib/entity_lock.py`
- Create: `tests/test_entity_lock.py`

Foundation for all per-page atomic writes. Uses `fcntl.flock` with a non-blocking poll loop for timeout support.

- [ ] **Step 1: Write the failing test**

Create `tests/test_entity_lock.py`:

```python
"""Tests for per-entity fcntl.flock helper."""
from __future__ import annotations

import multiprocessing
import time
from pathlib import Path

import pytest

from academic_wiki_lib.entity_lock import acquire, VALID_KINDS


@pytest.fixture
def wiki_dir(tmp_path):
    return tmp_path


class TestAcquire:
    def test_creates_lock_file_on_first_acquire(self, wiki_dir):
        with acquire(wiki_dir, kind="concept", key="attention"):
            lock_path = wiki_dir / ".locks" / "concept" / "attention.lock"
            assert lock_path.exists()

    def test_releases_on_context_exit(self, wiki_dir):
        # Acquire and release; second acquire should succeed immediately
        with acquire(wiki_dir, kind="concept", key="foo"):
            pass
        with acquire(wiki_dir, kind="concept", key="foo", timeout_seconds=1.0):
            pass

    def test_rejects_unknown_kind(self, wiki_dir):
        with pytest.raises(ValueError):
            with acquire(wiki_dir, kind="nonsense", key="x"):
                pass

    def test_accepts_all_documented_kinds(self, wiki_dir):
        for kind in VALID_KINDS:
            with acquire(wiki_dir, kind=kind, key="x"):
                pass


def _hold_lock_in_subprocess(wiki_root, duration_s, ready_event, start_event):
    """Helper for cross-process test: hold the lock for duration_s after signaling ready."""
    from academic_wiki_lib.entity_lock import acquire as _acquire
    with _acquire(wiki_root, kind="concept", key="contested"):
        ready_event.set()
        start_event.wait(timeout=10)
        time.sleep(duration_s)


class TestAcquireCrossProcess:
    def test_blocks_while_other_process_holds_lock(self, wiki_dir):
        ready = multiprocessing.Event()
        start = multiprocessing.Event()
        holder = multiprocessing.Process(
            target=_hold_lock_in_subprocess,
            args=(str(wiki_dir), 0.5, ready, start),
        )
        holder.start()
        try:
            ready.wait(timeout=5)
            # Other process holds the lock — acquiring with a short timeout should fail
            start.set()
            t0 = time.monotonic()
            with pytest.raises(TimeoutError):
                with acquire(wiki_dir, kind="concept", key="contested", timeout_seconds=0.1):
                    pass
            assert time.monotonic() - t0 < 2.0
        finally:
            holder.join(timeout=5)

    def test_acquires_after_other_process_releases(self, wiki_dir):
        ready = multiprocessing.Event()
        start = multiprocessing.Event()
        holder = multiprocessing.Process(
            target=_hold_lock_in_subprocess,
            args=(str(wiki_dir), 0.2, ready, start),
        )
        holder.start()
        try:
            ready.wait(timeout=5)
            start.set()
            # Acquire with a timeout longer than the holder's hold duration
            with acquire(wiki_dir, kind="concept", key="contested", timeout_seconds=5.0):
                pass
        finally:
            holder.join(timeout=5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_entity_lock.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'academic_wiki_lib.entity_lock'`

- [ ] **Step 3: Implement `entity_lock.py`**

Create `scripts/academic_wiki_lib/entity_lock.py`:

```python
"""Per-entity fcntl.flock helper for atomic read-modify-write on shared wiki pages."""
from __future__ import annotations

import fcntl
import os
import time
from contextlib import contextmanager
from pathlib import Path

VALID_KINDS = frozenset({"paper", "concept", "method", "open-problem", "venue", "reports"})
POLL_INTERVAL_S = 0.1


def _lock_path(wiki_root, kind: str, key: str) -> Path:
    return Path(os.fspath(wiki_root)) / ".locks" / kind / f"{key}.lock"


@contextmanager
def acquire(wiki_root, kind: str, key: str, timeout_seconds: float = 60.0):
    """Acquire exclusive fcntl.flock on <wiki_root>/.locks/<kind>/<key>.lock.

    Raises ValueError if kind is not one of VALID_KINDS.
    Raises TimeoutError if the lock cannot be acquired within timeout_seconds.

    The lock auto-releases when this process dies (crash or clean), so stale
    locks are not normally possible. If a process is wedged but alive, the
    user clears <wiki_root>/.locks/ manually before retrying.
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"Unknown entity lock kind: {kind!r} (expected one of {sorted(VALID_KINDS)})")

    path = _lock_path(wiki_root, kind, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Could not acquire entity lock {kind}/{key} within {timeout_seconds}s"
                    )
                time.sleep(POLL_INTERVAL_S)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_entity_lock.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git -C /home/tung491/Work/academic_wiki add scripts/academic_wiki_lib/entity_lock.py tests/test_entity_lock.py
git -C /home/tung491/Work/academic_wiki commit -m "feat(lib): add entity_lock for per-page fcntl.flock"
```

---

## Task 2: Extend `checkpoint.py` for full-tier

**Files:**
- Modify: `scripts/academic_wiki_lib/checkpoint.py`
- Modify: `tests/test_checkpoint.py`

Add `tier`, `pre-batch-paper-ids`, `final-pass-status` fields + `update_final_pass_status` helper. Keep backward-compat: old checkpoints missing these fields default sensibly on read.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_checkpoint.py` (below the existing `TestGetPendingPapers` class):

```python
class TestFullTierFields:
    def test_default_tier_is_paper_only(self, wiki_dir):
        papers = [("p1", "/x")]
        cp = create_checkpoint(wiki_dir, papers, wave_size=1)
        assert cp["tier"] == "paper-only"
        assert cp["pre-batch-paper-ids"] == []
        assert cp["final-pass-status"] == "skipped"

    def test_tier_full_sets_final_pass_pending(self, wiki_dir):
        papers = [("p1", "/x")]
        cp = create_checkpoint(
            wiki_dir, papers, wave_size=1,
            tier="full",
            pre_batch_paper_ids=["oldpaper1", "oldpaper2"],
        )
        assert cp["tier"] == "full"
        assert cp["pre-batch-paper-ids"] == ["oldpaper1", "oldpaper2"]
        assert cp["final-pass-status"] == "pending"

    def test_none_pre_batch_coerced_to_empty_list(self, wiki_dir):
        papers = [("p1", "/x")]
        cp = create_checkpoint(wiki_dir, papers, wave_size=1, tier="full",
                               pre_batch_paper_ids=None)
        assert cp["pre-batch-paper-ids"] == []


class TestReadCheckpointBackCompat:
    def test_missing_fields_default_on_read(self, wiki_dir):
        # Write an old-style checkpoint without the new fields
        cp_old = {
            "run-id": "2026-04-01T00:00:00Z",
            "status": "in-progress",
            "total": 1,
            "wave-size": 1,
            "last-completed-wave": -1,
            "papers": {"p1": "pending"},
            "errors": {},
            "squash-base": "",
            "wave-commits": [],
        }
        write_checkpoint(wiki_dir, cp_old)
        cp = read_checkpoint(wiki_dir)
        assert cp["tier"] == "paper-only"
        assert cp["pre-batch-paper-ids"] == []
        assert cp["final-pass-status"] == "skipped"


class TestUpdateFinalPassStatus:
    def test_sets_status(self, wiki_dir):
        from academic_wiki_lib.checkpoint import update_final_pass_status
        papers = [("p1", "/x")]
        create_checkpoint(wiki_dir, papers, wave_size=1, tier="full",
                          pre_batch_paper_ids=[])
        update_final_pass_status(wiki_dir, "in-progress")
        cp = read_checkpoint(wiki_dir)
        assert cp["final-pass-status"] == "in-progress"
        update_final_pass_status(wiki_dir, "ok")
        cp = read_checkpoint(wiki_dir)
        assert cp["final-pass-status"] == "ok"

    def test_rejects_unknown_status(self, wiki_dir):
        from academic_wiki_lib.checkpoint import update_final_pass_status
        papers = [("p1", "/x")]
        create_checkpoint(wiki_dir, papers, wave_size=1)
        with pytest.raises(ValueError):
            update_final_pass_status(wiki_dir, "bogus")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_checkpoint.py -v`
Expected: new tests FAIL (missing `tier` field, missing `update_final_pass_status`).

- [ ] **Step 3: Modify `checkpoint.py`**

Edit `scripts/academic_wiki_lib/checkpoint.py`:

Replace the existing `create_checkpoint` with:

```python
VALID_FINAL_PASS_STATUSES = frozenset({"pending", "in-progress", "ok", "failed", "skipped"})


def create_checkpoint(
    wiki_root,
    papers: list[tuple[str, str]],
    wave_size: int,
    squash_base: str = "",
    tier: str = "paper-only",
    pre_batch_paper_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Create a new checkpoint file. Returns the checkpoint dict.

    tier: 'paper-only' (default) preserves existing behavior.
          'full' enables the full-tier batch flow.
    pre_batch_paper_ids: snapshot of paper-ids that existed before this batch.
                         None is coerced to []. Used by subagents for cites matching.
    final-pass-status:   'pending' when tier='full', else 'skipped'.
    """
    final_pass_status = "pending" if tier == "full" else "skipped"
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
        "tier": tier,
        "pre-batch-paper-ids": list(pre_batch_paper_ids) if pre_batch_paper_ids is not None else [],
        "final-pass-status": final_pass_status,
    }
    write_checkpoint(wiki_root, cp)
    return cp
```

Replace the existing `read_checkpoint` with a version that defaults missing fields:

```python
def read_checkpoint(wiki_root) -> dict[str, Any] | None:
    """Read checkpoint from disk. Returns None if no checkpoint exists.

    For back-compat with older checkpoints, missing full-tier fields default:
      tier → 'paper-only'
      pre-batch-paper-ids → []
      final-pass-status → 'skipped'
    """
    path = _checkpoint_path(wiki_root)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        cp = yaml.safe_load(f)
    if cp is None:
        return None
    cp.setdefault("tier", "paper-only")
    cp.setdefault("pre-batch-paper-ids", [])
    cp.setdefault("final-pass-status", "skipped")
    return cp
```

Add `update_final_pass_status` at the end of the file:

```python
def update_final_pass_status(wiki_root, status: str) -> None:
    """Set the final-pass-status field on the checkpoint.

    Raises ValueError for unknown statuses. Raises FileNotFoundError if no
    checkpoint exists.
    """
    if status not in VALID_FINAL_PASS_STATUSES:
        raise ValueError(
            f"Unknown final-pass-status: {status!r} "
            f"(expected one of {sorted(VALID_FINAL_PASS_STATUSES)})"
        )
    cp = read_checkpoint(wiki_root)
    if cp is None:
        raise FileNotFoundError("No checkpoint found")
    cp["final-pass-status"] = status
    write_checkpoint(wiki_root, cp)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_checkpoint.py -v`
Expected: all tests PASS (existing + new).

- [ ] **Step 5: Commit**

```bash
git -C /home/tung491/Work/academic_wiki add scripts/academic_wiki_lib/checkpoint.py tests/test_checkpoint.py
git -C /home/tung491/Work/academic_wiki commit -m "feat(checkpoint): add tier, pre-batch-paper-ids, final-pass-status"
```

---

## Task 3: Entity Pages Module (`upsert_entity`)

**Files:**
- Create: `scripts/academic_wiki_lib/entity_pages.py`
- Create: `tests/test_entity_pages.py`

Atomic create-or-merge for `wiki/<kind>s/<slug>.md`. Returns `created: bool` so subagents know whether to schedule backlink audit.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_entity_pages.py`:

```python
"""Tests for upsert_entity atomic create/merge."""
from __future__ import annotations

import pytest

from academic_wiki_lib.entity_pages import upsert_entity
from academic_wiki_lib.frontmatter import read_frontmatter


@pytest.fixture
def wiki_dir(tmp_path):
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    (tmp_path / "wiki" / "methods").mkdir(parents=True)
    (tmp_path / "wiki" / "open-problems").mkdir(parents=True)
    return tmp_path


class TestUpsertEntityCreate:
    def test_creates_new_concept_page(self, wiki_dir):
        created = upsert_entity(
            wiki_dir, slug="attention-mechanism", kind="concept",
            paper_id="vaswani2017attention",
            title="Attention Mechanism",
            tags=["field/nlp"],
            body_contribution="Vaswani et al. propose attention as the core primitive.",
        )
        assert created is True
        path = wiki_dir / "wiki" / "concepts" / "attention-mechanism.md"
        assert path.exists()
        fm, body = read_frontmatter(path)
        assert fm["type"] == "concept"
        assert fm["slug"] == "attention-mechanism"
        assert fm["sources"] == ["vaswani2017attention"]
        assert fm["status"] == "active"
        assert "field/nlp" in fm["tags"]

    def test_status_default_open_for_open_problem(self, wiki_dir):
        created = upsert_entity(
            wiki_dir, slug="ai-safety", kind="open-problem",
            paper_id="smith2024safety",
            title="AI Safety",
            tags=["field/ai-safety"],
            body_contribution="An unresolved alignment question.",
            status_default="open",
        )
        assert created is True
        fm, _ = read_frontmatter(wiki_dir / "wiki" / "open-problems" / "ai-safety.md")
        assert fm["status"] == "open"


class TestUpsertEntityMerge:
    def test_merge_appends_new_source(self, wiki_dir):
        upsert_entity(
            wiki_dir, slug="attention", kind="concept",
            paper_id="paper-a", title="Attention",
            tags=["field/nlp"],
            body_contribution="First contribution.",
        )
        created = upsert_entity(
            wiki_dir, slug="attention", kind="concept",
            paper_id="paper-b", title="Attention",
            tags=["field/vision"],
            body_contribution="Second contribution from paper-b.",
        )
        assert created is False
        fm, body = read_frontmatter(wiki_dir / "wiki" / "concepts" / "attention.md")
        assert fm["sources"] == ["paper-a", "paper-b"]
        assert "field/nlp" in fm["tags"]
        assert "field/vision" in fm["tags"]
        assert "Second contribution from paper-b." in body

    def test_merge_dedups_source(self, wiki_dir):
        upsert_entity(
            wiki_dir, slug="attention", kind="concept",
            paper_id="paper-a", title="Attention",
            tags=["field/nlp"], body_contribution="First.",
        )
        upsert_entity(
            wiki_dir, slug="attention", kind="concept",
            paper_id="paper-a", title="Attention",
            tags=["field/nlp"], body_contribution="First (again).",
        )
        fm, _ = read_frontmatter(wiki_dir / "wiki" / "concepts" / "attention.md")
        # Only one paper-a entry
        assert fm["sources"] == ["paper-a"]

    def test_merge_bumps_updated_preserves_created(self, wiki_dir):
        upsert_entity(
            wiki_dir, slug="attention", kind="concept",
            paper_id="paper-a", title="Attention",
            tags=[], body_contribution="First.",
        )
        fm_first, _ = read_frontmatter(wiki_dir / "wiki" / "concepts" / "attention.md")
        created_first = fm_first["created"]
        upsert_entity(
            wiki_dir, slug="attention", kind="concept",
            paper_id="paper-b", title="Attention",
            tags=[], body_contribution="Second.",
        )
        fm_second, _ = read_frontmatter(wiki_dir / "wiki" / "concepts" / "attention.md")
        assert fm_second["created"] == created_first  # preserved


class TestUpsertEntityValidation:
    def test_rejects_unknown_kind(self, wiki_dir):
        with pytest.raises(ValueError):
            upsert_entity(
                wiki_dir, slug="x", kind="banana",
                paper_id="p", title="X", tags=[], body_contribution="",
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_entity_pages.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `entity_pages.py`**

Create `scripts/academic_wiki_lib/entity_pages.py`:

```python
"""Atomic upsert for wiki entity pages (concept/method/open-problem)."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

from academic_wiki_lib import entity_lock
from academic_wiki_lib.frontmatter import read_frontmatter, write_frontmatter

_VALID_KINDS = frozenset({"concept", "method", "open-problem"})
_DEFAULT_STATUS = {
    "concept": "active",
    "method": "active",
    "open-problem": "open",
}


def _page_path(wiki_root, kind: str, slug: str) -> Path:
    return Path(os.fspath(wiki_root)) / "wiki" / f"{kind}s" / f"{slug}.md"


def _render_new(slug: str, kind: str, title: str, paper_id: str,
                tags: list[str], body_contribution: str, status: str,
                today: str) -> tuple[dict[str, Any], str]:
    fm: dict[str, Any] = {
        "type": kind,
        "slug": slug,
        "status": status,
        "created": today,
        "updated": today,
        "aliases": [],
        "sources": [paper_id],
        "tags": list(tags),
    }
    body = f"# {title}\n\n## Definition\n\n{body_contribution}\n\n## Details\n\n## See Also\n\n## Counter-Arguments and Gaps\n"
    return fm, body


def _merge_existing(existing_fm: dict[str, Any], existing_body: str,
                    paper_id: str, tags: list[str],
                    body_contribution: str, today: str) -> tuple[dict[str, Any], str]:
    sources = list(existing_fm.get("sources") or [])
    if paper_id not in sources:
        sources.append(paper_id)
    existing_tags = list(existing_fm.get("tags") or [])
    for t in tags:
        if t not in existing_tags:
            existing_tags.append(t)
    existing_fm["sources"] = sources
    existing_fm["tags"] = existing_tags
    existing_fm["updated"] = today
    # Append attributed paragraph to body
    attribution = f"\n\nFrom [[{paper_id}]]: {body_contribution}\n"
    return existing_fm, existing_body.rstrip() + attribution


def upsert_entity(
    wiki_root,
    slug: str,
    kind: str,
    paper_id: str,
    title: str,
    tags: list[str],
    body_contribution: str,
    status_default: str | None = None,
) -> bool:
    """Atomically create or merge wiki/<kind>s/<slug>.md.

    On create: renders a minimal page from template with sources=[paper_id].
    On update: appends paper_id to sources (dedup), unions tags, bumps updated,
    appends body_contribution as an attributed paragraph.

    Returns True if the page was created, False if it existed and was merged.
    """
    if kind not in _VALID_KINDS:
        raise ValueError(f"Unknown entity kind: {kind!r} (expected one of {sorted(_VALID_KINDS)})")

    status = status_default if status_default is not None else _DEFAULT_STATUS[kind]
    today = date.today().isoformat()
    path = _page_path(wiki_root, kind, slug)

    with entity_lock.acquire(wiki_root, kind=kind, key=slug):
        if path.exists():
            existing_fm, existing_body = read_frontmatter(path)
            fm, body = _merge_existing(existing_fm, existing_body, paper_id,
                                       tags, body_contribution, today)
            write_frontmatter(path, fm, body)
            return False
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            fm, body = _render_new(slug, kind, title, paper_id, tags,
                                   body_contribution, status, today)
            write_frontmatter(path, fm, body)
            return True
```

Note: this assumes `academic_wiki_lib.frontmatter.write_frontmatter(path, fm, body)` writes both halves. Verify the existing API signature matches; if it's different (e.g., takes a combined string), adapt the call.

- [ ] **Step 4: Verify frontmatter API matches**

Run: `cd /home/tung491/Work/academic_wiki && python -c "from academic_wiki_lib.frontmatter import read_frontmatter, write_frontmatter; import inspect; print(inspect.signature(write_frontmatter))"`
If the signature differs (e.g., `write_frontmatter(path, fm, body)` vs `write_frontmatter(path, {'fm': fm, 'body': body})`), adjust the implementation. If the tests fail with signature errors, adapt the helper to match the real API.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_entity_pages.py -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git -C /home/tung491/Work/academic_wiki add scripts/academic_wiki_lib/entity_pages.py tests/test_entity_pages.py
git -C /home/tung491/Work/academic_wiki commit -m "feat(lib): add entity_pages.upsert_entity with per-slug locking"
```

---

## Task 4: Cites Fuzzy-Matcher Module

**Files:**
- Create: `scripts/academic_wiki_lib/cites.py`
- Create: `tests/test_cites.py`

Normalized 0-1 token-set-ratio matcher with threshold 0.80 and top-5 candidates per reference. Prefers `rapidfuzz` if installed; falls back to `difflib.SequenceMatcher`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cites.py`:

```python
"""Tests for cites fuzzy-matcher."""
from __future__ import annotations

from pathlib import Path

import pytest

from academic_wiki_lib.cites import resolve_cites
from academic_wiki_lib.frontmatter import write_frontmatter


@pytest.fixture
def wiki_dir(tmp_path):
    (tmp_path / "wiki" / "papers").mkdir(parents=True)
    return tmp_path


def _make_paper(wiki_dir, paper_id, title, author_surname, year):
    path = wiki_dir / "wiki" / "papers" / f"{paper_id}.md"
    fm = {
        "paper-id": paper_id,
        "type": "paper",
        "title": title,
        "authors": [{"slug": author_surname.lower(), "name": author_surname}],
        "year": year,
    }
    write_frontmatter(path, fm, f"# {title}\n")


class TestResolveCites:
    def test_exact_title_match_resolves(self, wiki_dir):
        _make_paper(wiki_dir, "vaswani2017attention", "Attention Is All You Need",
                    "Vaswani", 2017)
        refs = ["Vaswani, A. Attention Is All You Need. NeurIPS, 2017."]
        result = resolve_cites(wiki_dir, refs, ["vaswani2017attention"])
        matches = result[refs[0]]
        assert matches
        assert matches[0][0] == "vaswani2017attention"
        assert matches[0][1] >= 0.80  # normalized score

    def test_below_threshold_returns_empty(self, wiki_dir):
        _make_paper(wiki_dir, "p1", "Completely Unrelated Title", "Brown", 2020)
        refs = ["Smith, J. A Different Paper. 2019."]
        result = resolve_cites(wiki_dir, refs, ["p1"])
        assert result[refs[0]] == []

    def test_caps_at_five_per_reference(self, wiki_dir):
        # Create 10 papers all with title similar to the reference
        for i in range(10):
            _make_paper(wiki_dir, f"p{i}", "Attention Mechanism Survey",
                        "Author" + str(i), 2020 + i)
        refs = ["Author. Attention Mechanism Survey. 2020."]
        pre_batch = [f"p{i}" for i in range(10)]
        result = resolve_cites(wiki_dir, refs, pre_batch)
        assert len(result[refs[0]]) <= 5

    def test_results_sorted_by_score_desc(self, wiki_dir):
        _make_paper(wiki_dir, "close", "Attention Is All You Need", "Vaswani", 2017)
        _make_paper(wiki_dir, "far", "Attention Is Partially Useful", "Vaswani", 2017)
        refs = ["Vaswani. Attention Is All You Need. 2017."]
        result = resolve_cites(wiki_dir, refs, ["close", "far"])
        matches = result[refs[0]]
        assert len(matches) >= 1
        scores = [s for _, s in matches]
        assert scores == sorted(scores, reverse=True)

    def test_missing_paper_skipped(self, wiki_dir):
        _make_paper(wiki_dir, "p1", "Known Paper", "Author", 2020)
        refs = ["Author. Known Paper. 2020."]
        result = resolve_cites(wiki_dir, refs, ["p1", "nonexistent"])
        # Should not raise even though nonexistent has no file
        assert refs[0] in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_cites.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `cites.py`**

Create `scripts/academic_wiki_lib/cites.py`:

```python
"""Fuzzy-match references_raw entries against pre-batch paper pages."""
from __future__ import annotations

import os
import re
from difflib import SequenceMatcher
from pathlib import Path

from academic_wiki_lib.frontmatter import read_frontmatter

_THRESHOLD = 0.80
_TOP_K_PER_REF = 5

try:
    from rapidfuzz import fuzz
    def _score(a: str, b: str) -> float:
        # rapidfuzz token_set_ratio returns 0-100; normalize
        return fuzz.token_set_ratio(a, b) / 100.0
except ImportError:
    def _score(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()


def _normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _load_candidate(wiki_root, paper_id: str) -> tuple[str, str, str] | None:
    """Return (title, first_author_surname, year_str) or None if file missing."""
    path = Path(os.fspath(wiki_root)) / "wiki" / "papers" / f"{paper_id}.md"
    if not path.exists():
        return None
    fm, _ = read_frontmatter(path)
    title = fm.get("title") or ""
    authors = fm.get("authors") or []
    first_author = ""
    if authors and isinstance(authors[0], dict):
        first_author = authors[0].get("name") or ""
    elif authors and isinstance(authors[0], str):
        first_author = authors[0]
    year = str(fm.get("year") or "")
    return (title, first_author, year)


def resolve_cites(
    wiki_root,
    references_raw: list[str],
    pre_batch_paper_ids: list[str],
) -> dict[str, list[tuple[str, float]]]:
    """Fuzzy-match each references_raw entry against pre-batch papers.

    Returns dict mapping each reference string to a list of up to 5
    (paper_id, normalized_score) pairs with score >= 0.80, sorted desc.
    """
    # Load and cache all candidates up-front
    candidates: list[tuple[str, str]] = []  # (paper_id, normalized_candidate_string)
    for pid in pre_batch_paper_ids:
        loaded = _load_candidate(wiki_root, pid)
        if loaded is None:
            continue
        title, author, year = loaded
        candidates.append((pid, _normalize(f"{title} {author} {year}")))

    result: dict[str, list[tuple[str, float]]] = {}
    for ref in references_raw:
        norm_ref = _normalize(ref)
        scored = [(pid, _score(norm_ref, cand)) for pid, cand in candidates]
        scored = [(pid, s) for pid, s in scored if s >= _THRESHOLD]
        scored.sort(key=lambda x: x[1], reverse=True)
        result[ref] = scored[:_TOP_K_PER_REF]
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_cites.py -v`
Expected: all tests PASS. (If `rapidfuzz` is not installed, the fallback `difflib` path is exercised — both should meet the threshold for the test's short title.)

- [ ] **Step 5: Commit**

```bash
git -C /home/tung491/Work/academic_wiki add scripts/academic_wiki_lib/cites.py tests/test_cites.py
git -C /home/tung491/Work/academic_wiki commit -m "feat(lib): add cites.resolve_cites with normalized score + 0.80 threshold"
```

---

## Task 5: Backlinks Module

**Files:**
- Create: `scripts/academic_wiki_lib/backlinks.py`
- Create: `tests/test_backlinks.py`

`_target_lock_kind_and_key()` maps any wiki file path to (kind, key) for locking. `insert_backlink()` atomically inserts `[[<slug>]]` where appropriate.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_backlinks.py`:

```python
"""Tests for backlinks helpers."""
from __future__ import annotations

from pathlib import Path

import pytest

from academic_wiki_lib.backlinks import _target_lock_kind_and_key, insert_backlink


class TestTargetLockKindAndKey:
    def test_paper_path(self):
        kind, key = _target_lock_kind_and_key("wiki/papers/vaswani2017attention.md")
        assert (kind, key) == ("paper", "vaswani2017attention")

    def test_concept_path(self):
        kind, key = _target_lock_kind_and_key("wiki/concepts/attention-mechanism.md")
        assert (kind, key) == ("concept", "attention-mechanism")

    def test_method_path(self):
        kind, key = _target_lock_kind_and_key("wiki/methods/transformer.md")
        assert (kind, key) == ("method", "transformer")

    def test_open_problem_path(self):
        kind, key = _target_lock_kind_and_key("wiki/open-problems/ai-safety.md")
        assert (kind, key) == ("open-problem", "ai-safety")

    def test_venue_path(self):
        kind, key = _target_lock_kind_and_key("wiki/venues/neurips.md")
        assert (kind, key) == ("venue", "neurips")

    def test_rejects_unknown(self):
        with pytest.raises(ValueError):
            _target_lock_kind_and_key("wiki/unknown/foo.md")

    def test_rejects_non_wiki_path(self):
        with pytest.raises(ValueError):
            _target_lock_kind_and_key("outputs/x/y.md")


@pytest.fixture
def wiki_dir(tmp_path):
    (tmp_path / "wiki" / "papers").mkdir(parents=True)
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    return tmp_path


class TestInsertBacklink:
    def test_inserts_when_multiword_slug_matches(self, wiki_dir):
        target = wiki_dir / "wiki" / "papers" / "paper-a.md"
        target.write_text(
            "---\npaper-id: paper-a\n---\n\nWe use the attention mechanism here.\n"
        )
        ok = insert_backlink(wiki_dir, "wiki/papers/paper-a.md", "attention-mechanism")
        assert ok is True
        content = target.read_text()
        assert "[[attention-mechanism]]" in content

    def test_noop_when_already_present(self, wiki_dir):
        target = wiki_dir / "wiki" / "papers" / "paper-a.md"
        target.write_text(
            "---\npaper-id: paper-a\n---\n\nWe use [[attention-mechanism]] here.\n"
        )
        ok = insert_backlink(wiki_dir, "wiki/papers/paper-a.md", "attention-mechanism")
        assert ok is False

    def test_noop_when_no_match(self, wiki_dir):
        target = wiki_dir / "wiki" / "papers" / "paper-a.md"
        target.write_text("---\npaper-id: paper-a\n---\n\nUnrelated content.\n")
        ok = insert_backlink(wiki_dir, "wiki/papers/paper-a.md", "attention-mechanism")
        assert ok is False

    def test_single_word_slug_not_inserted(self, wiki_dir):
        # Single-word slugs are rejected unless proper-noun (we skip proper-noun
        # heuristic in v1 and always reject single-word)
        target = wiki_dir / "wiki" / "papers" / "paper-a.md"
        target.write_text("---\npaper-id: paper-a\n---\n\nWe discuss attention widely.\n")
        ok = insert_backlink(wiki_dir, "wiki/papers/paper-a.md", "attention")
        assert ok is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_backlinks.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `backlinks.py`**

Create `scripts/academic_wiki_lib/backlinks.py`:

```python
"""Atomic backlink insertion into wiki pages."""
from __future__ import annotations

import os
import re
from pathlib import Path

from academic_wiki_lib import entity_lock


_PATH_KIND_MAP = {
    "papers": "paper",
    "concepts": "concept",
    "methods": "method",
    "open-problems": "open-problem",
    "venues": "venue",
}


def _target_lock_kind_and_key(target_path: str) -> tuple[str, str]:
    """Map a wiki file path to (entity_lock kind, key).

    Examples:
        wiki/papers/<pid>.md        → ("paper", <pid>)
        wiki/concepts/<slug>.md     → ("concept", <slug>)
        wiki/methods/<slug>.md      → ("method", <slug>)
        wiki/open-problems/<slug>.md → ("open-problem", <slug>)
        wiki/venues/<slug>.md       → ("venue", <slug>)
    """
    p = Path(target_path)
    parts = p.parts
    if len(parts) < 3 or parts[0] != "wiki":
        raise ValueError(f"Not a wiki/ path: {target_path!r}")
    dir_name = parts[1]
    if dir_name not in _PATH_KIND_MAP:
        raise ValueError(f"Unknown wiki subdir: {dir_name!r} (in {target_path!r})")
    return _PATH_KIND_MAP[dir_name], p.stem


def insert_backlink(wiki_root, target_path: str, slug: str) -> bool:
    """Atomically insert [[<slug>]] into target_path where slug-words appear.

    Rule: only insert if slug has >=2 hyphen-separated tokens. No-op if
    [[<slug>]] already present or no eligible match.

    Returns True if a backlink was inserted, False otherwise.
    """
    if slug.count("-") == 0:
        return False  # single-word slugs are never auto-linked in v1

    kind, key = _target_lock_kind_and_key(target_path)
    abs_target = Path(os.fspath(wiki_root)) / target_path
    if not abs_target.exists():
        return False

    with entity_lock.acquire(wiki_root, kind=kind, key=key):
        content = abs_target.read_text()
        wikilink = f"[[{slug}]]"
        if wikilink in content:
            return False
        # Match hyphenated-slug as space-separated words, case-insensitive
        words_pattern = re.escape(slug.replace("-", " "))
        pattern = re.compile(r"\b" + words_pattern + r"\b", flags=re.IGNORECASE)
        m = pattern.search(content)
        if not m:
            return False
        # Replace the first match with the [[wikilink]]
        matched_text = m.group(0)
        new_content = content[:m.start()] + wikilink + content[m.end():]
        abs_target.write_text(new_content)
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_backlinks.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git -C /home/tung491/Work/academic_wiki add scripts/academic_wiki_lib/backlinks.py tests/test_backlinks.py
git -C /home/tung491/Work/academic_wiki commit -m "feat(lib): add backlinks.insert_backlink with per-file locking"
```

---

## Task 6: Cross-Paper Module (top-K + report append)

**Files:**
- Create: `scripts/academic_wiki_lib/cross_paper.py`
- Create: `tests/test_cross_paper.py`

`compute_top_k_neighbors()` ranks pre-batch papers by shared `field/*` and `method/*` tag overlap. `append_candidates()` atomically appends to the promotion-candidates report with dedup.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cross_paper.py`:

```python
"""Tests for cross-paper helpers."""
from __future__ import annotations

import pytest

from academic_wiki_lib.cross_paper import compute_top_k_neighbors, append_candidates
from academic_wiki_lib.frontmatter import write_frontmatter


@pytest.fixture
def wiki_dir(tmp_path):
    (tmp_path / "wiki" / "papers").mkdir(parents=True)
    (tmp_path / "outputs" / "reports").mkdir(parents=True)
    return tmp_path


def _make_paper(wiki_dir, paper_id, tags, year=2020):
    path = wiki_dir / "wiki" / "papers" / f"{paper_id}.md"
    write_frontmatter(path, {
        "paper-id": paper_id,
        "type": "paper",
        "title": paper_id,
        "year": year,
        "tags": tags,
    }, "# " + paper_id + "\n")


class TestComputeTopKNeighbors:
    def test_ranks_by_shared_field_and_method_tags(self, wiki_dir):
        _make_paper(wiki_dir, "target", ["paper", "field/nlp", "method/attention"])
        _make_paper(wiki_dir, "best", ["paper", "field/nlp", "method/attention"], year=2023)
        _make_paper(wiki_dir, "medium", ["paper", "field/nlp"], year=2022)
        _make_paper(wiki_dir, "none", ["paper", "field/vision"], year=2021)

        result = compute_top_k_neighbors(wiki_dir, "target", ["best", "medium", "none"], k=3)
        assert result == ["best", "medium"]  # 'none' has 0 overlap, excluded

    def test_excludes_year_and_venue_tags(self, wiki_dir):
        _make_paper(wiki_dir, "target", ["paper", "year/2020", "venue/neurips"])
        _make_paper(wiki_dir, "match", ["paper", "year/2020", "venue/neurips"])
        result = compute_top_k_neighbors(wiki_dir, "target", ["match"], k=3)
        assert result == []  # no field/ or method/ overlap

    def test_respects_k_limit(self, wiki_dir):
        _make_paper(wiki_dir, "target", ["paper", "field/nlp"])
        for i in range(5):
            _make_paper(wiki_dir, f"p{i}", ["paper", "field/nlp"])
        result = compute_top_k_neighbors(wiki_dir, "target",
                                         [f"p{i}" for i in range(5)], k=2)
        assert len(result) == 2

    def test_year_tiebreak_prefers_recent(self, wiki_dir):
        _make_paper(wiki_dir, "target", ["paper", "field/nlp"])
        _make_paper(wiki_dir, "old", ["paper", "field/nlp"], year=2010)
        _make_paper(wiki_dir, "new", ["paper", "field/nlp"], year=2023)
        result = compute_top_k_neighbors(wiki_dir, "target", ["old", "new"], k=2)
        assert result == ["new", "old"]

    def test_missing_neighbor_skipped(self, wiki_dir):
        _make_paper(wiki_dir, "target", ["paper", "field/nlp"])
        _make_paper(wiki_dir, "p1", ["paper", "field/nlp"])
        result = compute_top_k_neighbors(wiki_dir, "target",
                                         ["p1", "nonexistent"], k=3)
        assert result == ["p1"]


class TestAppendCandidates:
    def test_creates_file_on_first_append(self, wiki_dir):
        entries = [{
            "description": "A claim restated",
            "type": "claim",
            "paper_a": "p1",
            "paper_b": "p2",
            "quote_a": "foo",
            "quote_b": "foo variant",
            "relationship": "equivalent",
        }]
        append_candidates(wiki_dir, entries)
        # File exists under outputs/reports/ with today's date
        reports = list((wiki_dir / "outputs" / "reports").glob("*-promotion-candidates.md"))
        assert len(reports) == 1
        content = reports[0].read_text()
        assert "A claim restated" in content
        assert "[[p1]]" in content
        assert "[[p2]]" in content

    def test_dedups_on_repeat_append(self, wiki_dir):
        entries = [{
            "description": "dup",
            "type": "claim",
            "paper_a": "p1",
            "paper_b": "p2",
            "quote_a": "x",
            "quote_b": "y",
            "relationship": "equivalent",
        }]
        append_candidates(wiki_dir, entries)
        append_candidates(wiki_dir, entries)
        reports = list((wiki_dir / "outputs" / "reports").glob("*-promotion-candidates.md"))
        assert len(reports) == 1
        # Count occurrences of the description
        content = reports[0].read_text()
        assert content.count("dup") == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_cross_paper.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `cross_paper.py`**

Create `scripts/academic_wiki_lib/cross_paper.py`:

```python
"""Cross-paper candidate detection helpers: top-K neighbors + report append."""
from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from academic_wiki_lib import entity_lock
from academic_wiki_lib.frontmatter import read_frontmatter


def _field_and_method_tags(tags: list[str]) -> set[str]:
    return {t for t in (tags or []) if t.startswith("field/") or t.startswith("method/")}


def _load_paper_meta(wiki_root, paper_id: str) -> tuple[set[str], int, str] | None:
    """Return (field_method_tags, year_int, paper_id) or None if missing."""
    path = Path(os.fspath(wiki_root)) / "wiki" / "papers" / f"{paper_id}.md"
    if not path.exists():
        return None
    fm, _ = read_frontmatter(path)
    tags = _field_and_method_tags(fm.get("tags") or [])
    year_raw = fm.get("year")
    try:
        year = int(year_raw)
    except (TypeError, ValueError):
        year = 0
    return (tags, year, paper_id)


def compute_top_k_neighbors(
    wiki_root,
    paper_id: str,
    pre_batch_paper_ids: list[str],
    k: int = 20,
) -> list[str]:
    """Rank pre-batch papers by shared field/* and method/* tags.

    Returns paper-ids sorted (shared desc, year desc, paper_id asc), filtered
    to positive overlap only, truncated to top k.
    """
    me = _load_paper_meta(wiki_root, paper_id)
    if me is None:
        return []
    my_tags = me[0]
    if not my_tags:
        return []

    scored: list[tuple[int, int, str]] = []  # (shared, year, pid)
    for pid in pre_batch_paper_ids:
        other = _load_paper_meta(wiki_root, pid)
        if other is None:
            continue
        other_tags, other_year, other_pid = other
        shared = len(my_tags & other_tags)
        if shared == 0:
            continue
        scored.append((shared, other_year, other_pid))

    # Sort: shared desc, year desc, pid asc
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
    return [pid for _, _, pid in scored[:k]]


def _report_path(wiki_root) -> Path:
    today = date.today().isoformat()
    return Path(os.fspath(wiki_root)) / "outputs" / "reports" / f"{today}-promotion-candidates.md"


def _render_entry(entry: dict[str, str]) -> str:
    return (
        f"### Candidate: {entry['description']}\n"
        f"- **Type:** {entry['type']}\n"
        f"- **Paper A:** [[{entry['paper_a']}]] — \"{entry['quote_a']}\"\n"
        f"- **Paper B:** [[{entry['paper_b']}]] — \"{entry['quote_b']}\"\n"
        f"- **Relationship:** {entry['relationship']}\n"
        f"- **Action:** review — promote or leave as-is\n\n"
    )


_ENTRY_KEY_PATTERN = re.compile(
    r"- \*\*Paper A:\*\* \[\[(?P<a>[^\]]+)\]\].*?- \*\*Paper B:\*\* \[\[(?P<b>[^\]]+)\]\].*?- \*\*Type:\*\* (?P<type>\w+)",
    flags=re.DOTALL,
)


def _existing_keys(content: str) -> set[tuple[str, str, str]]:
    """Extract (paper_a, paper_b, type) keys from existing report content."""
    keys: set[tuple[str, str, str]] = set()
    # The entry order in the rendered file is: Type, Paper A, Paper B; so adapt pattern
    alt_pattern = re.compile(
        r"- \*\*Type:\*\* (?P<type>\w+)\s*\n"
        r"- \*\*Paper A:\*\* \[\[(?P<a>[^\]]+)\]\].*?\n"
        r"- \*\*Paper B:\*\* \[\[(?P<b>[^\]]+)\]\]",
        flags=re.DOTALL,
    )
    for m in alt_pattern.finditer(content):
        keys.add((m.group("a"), m.group("b"), m.group("type")))
    return keys


def append_candidates(wiki_root, entries: list[dict[str, str]]) -> None:
    """Atomically append candidate entries to today's promotion-candidates report.

    Dedupes by (paper_a, paper_b, type) against existing file contents before
    appending. Creates the file with a heading if it does not exist.
    """
    if not entries:
        return
    path = _report_path(wiki_root)
    with entity_lock.acquire(wiki_root, kind="reports", key="promotion-candidates"):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = path.read_text()
        else:
            existing = f"# Promotion Candidates — {date.today().isoformat()}\n\n"
        existing_keys = _existing_keys(existing)
        new_rendered = []
        for e in entries:
            key = (e["paper_a"], e["paper_b"], e["type"])
            if key in existing_keys:
                continue
            new_rendered.append(_render_entry(e))
            existing_keys.add(key)
        if new_rendered:
            path.write_text(existing + "".join(new_rendered))
        elif not path.exists():
            # Ensure file exists with header even if everything was deduped
            path.write_text(existing)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_cross_paper.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git -C /home/tung491/Work/academic_wiki add scripts/academic_wiki_lib/cross_paper.py tests/test_cross_paper.py
git -C /home/tung491/Work/academic_wiki commit -m "feat(lib): add cross_paper top-K + promotion-candidates append"
```

---

## Task 7: Pre-Batch Snapshot Helper

**Files:**
- Create: `scripts/academic_wiki_lib/pre_batch_snapshot.py`
- Create: `tests/test_pre_batch_snapshot.py`

Orchestrator-side helper that writes `outputs/.pre-batch-snapshot.yml` with the list of wiki file paths that existed at batch start, and reads them back.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pre_batch_snapshot.py`:

```python
"""Tests for pre-batch snapshot helper."""
from __future__ import annotations

import pytest

from academic_wiki_lib.pre_batch_snapshot import (
    write_snapshot, read_snapshot, snapshot_path, delete_snapshot, scan_targets,
)


@pytest.fixture
def wiki_dir(tmp_path):
    (tmp_path / "outputs").mkdir()
    (tmp_path / "wiki" / "papers").mkdir(parents=True)
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    (tmp_path / "wiki" / "methods").mkdir(parents=True)
    (tmp_path / "wiki" / "open-problems").mkdir(parents=True)
    (tmp_path / "wiki" / "venues").mkdir(parents=True)
    return tmp_path


class TestWriteAndRead:
    def test_roundtrip(self, wiki_dir):
        targets = ["wiki/papers/a.md", "wiki/concepts/foo.md"]
        write_snapshot(wiki_dir, targets)
        got = read_snapshot(wiki_dir)
        assert got == targets

    def test_read_returns_empty_when_missing(self, wiki_dir):
        assert read_snapshot(wiki_dir) == []

    def test_delete_removes_file(self, wiki_dir):
        write_snapshot(wiki_dir, ["wiki/papers/a.md"])
        assert snapshot_path(wiki_dir).exists()
        delete_snapshot(wiki_dir)
        assert not snapshot_path(wiki_dir).exists()

    def test_delete_is_noop_when_missing(self, wiki_dir):
        # Should not raise
        delete_snapshot(wiki_dir)


class TestScanTargets:
    def test_scans_all_known_subdirs(self, wiki_dir):
        (wiki_dir / "wiki" / "papers" / "p1.md").write_text("---\n---\n")
        (wiki_dir / "wiki" / "concepts" / "c1.md").write_text("---\n---\n")
        (wiki_dir / "wiki" / "methods" / "m1.md").write_text("---\n---\n")
        (wiki_dir / "wiki" / "open-problems" / "o1.md").write_text("---\n---\n")
        (wiki_dir / "wiki" / "venues" / "v1.md").write_text("---\n---\n")
        targets = scan_targets(wiki_dir)
        assert "wiki/papers/p1.md" in targets
        assert "wiki/concepts/c1.md" in targets
        assert "wiki/methods/m1.md" in targets
        assert "wiki/open-problems/o1.md" in targets
        assert "wiki/venues/v1.md" in targets

    def test_empty_wiki_returns_empty(self, wiki_dir):
        assert scan_targets(wiki_dir) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_pre_batch_snapshot.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `pre_batch_snapshot.py`**

Create `scripts/academic_wiki_lib/pre_batch_snapshot.py`:

```python
"""Pre-batch snapshot: the list of wiki files that existed at batch start.

Stored separately from the checkpoint (checkpoint stays small; snapshot can be
60KB+). Subagents read this file to scope their backlink audit step.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

SNAPSHOT_FILENAME = ".pre-batch-snapshot.yml"
_SCAN_SUBDIRS = ("papers", "concepts", "methods", "open-problems", "venues")


def snapshot_path(wiki_root) -> Path:
    return Path(os.fspath(wiki_root)) / "outputs" / SNAPSHOT_FILENAME


def scan_targets(wiki_root) -> list[str]:
    """Walk wiki/{papers,concepts,methods,open-problems,venues}/ and return
    a sorted list of relative paths (e.g., 'wiki/papers/foo.md').
    """
    root = Path(os.fspath(wiki_root))
    results: list[str] = []
    for sub in _SCAN_SUBDIRS:
        sub_dir = root / "wiki" / sub
        if not sub_dir.is_dir():
            continue
        for p in sorted(sub_dir.glob("*.md")):
            results.append(f"wiki/{sub}/{p.name}")
    return results


def write_snapshot(wiki_root, targets: list[str]) -> None:
    """Write the snapshot file with targets list."""
    path = snapshot_path(wiki_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump({"targets": list(targets)}, f, sort_keys=False,
                  allow_unicode=True, default_flow_style=False)


def read_snapshot(wiki_root) -> list[str]:
    """Read the snapshot's targets list. Returns [] if file missing."""
    path = snapshot_path(wiki_root)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return []
    return list(data.get("targets") or [])


def delete_snapshot(wiki_root) -> None:
    """Delete the snapshot file if present."""
    path = snapshot_path(wiki_root)
    if path.exists():
        path.unlink()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_pre_batch_snapshot.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git -C /home/tung491/Work/academic_wiki add scripts/academic_wiki_lib/pre_batch_snapshot.py tests/test_pre_batch_snapshot.py
git -C /home/tung491/Work/academic_wiki commit -m "feat(lib): add pre_batch_snapshot writer/reader/scanner"
```

---

## Task 8: Full-Tier Subagent Prompt Template

**Files:**
- Create: `skills/wiki/references/batch-compile-full-prompt.md`

Self-contained instructions for a Sonnet subagent doing end-to-end full-tier compile for its batch of 8-10 papers.

- [ ] **Step 1: Read the existing paper-only template for structural reference**

Read `/home/tung491/Work/academic_wiki/skills/wiki/references/batch-compile-prompt.md` in full. The new full-tier template should be structured the same way but extended with Steps 5-8.

- [ ] **Step 2: Create the full-tier template**

Create `skills/wiki/references/batch-compile-full-prompt.md` with the following sections (fill in per the spec §4.2 and §4.3):

1. **Header + usage note.** "This is a template. The orchestrator replaces `{{WIKI_ROOT}}`, `{{PAPER_LIST}}`, `{{PRE_BATCH_PAPERS}}`, `{{PRE_BATCH_SNAPSHOT_PATH}}`, `{{PYTHONPATH}}`, `{{TODAY}}` with runtime values before dispatching each subagent."
2. **Role and constraints.** "You are a full-tier paper compiler subagent. You do NOT touch git, checkpoint, or log files. You DO write paper pages, venue pages, entity pages (concept/method/open-problem), and cites/backlinks/cross-paper candidates via the provided Python helpers."
3. **Input section.** List all six template variables with their semantics, note that `PRE_BATCH_PAPERS` is consumed by Steps 6 and 8, `PRE_BATCH_SNAPSHOT_PATH` is consumed by Step 7.
4. **Steps 1-4b.** Copy verbatim from the paper-only template (paper extraction, notes, derivation, paper page write, venue upsert). Replace hard-coded date literals with `{{TODAY}}`.
5. **Step 5 — Entity extraction.** Per spec §4.3 Step 5. Show the Python helper invocation pattern:

   ```bash
   "$PY" -c "
   import sys; sys.path.insert(0, '{{PYTHONPATH}}')
   from academic_wiki_lib.entity_pages import upsert_entity
   created = upsert_entity(
       '{{WIKI_ROOT}}', slug='<slug>', kind='<kind>',
       paper_id='<paper-id>', title='<title>',
       tags=['field/nlp'], body_contribution='<contribution>',
   )
   print('created' if created else 'merged')
   "
   ```

   Instruct the subagent to track `created_entities` in memory as it goes (list of `(slug, kind)` tuples where `upsert_entity` returned True) — these drive Step 7.

6. **Step 6 — Cites resolution.** Per spec §4.3 Step 6. Helper invocation:

   ```bash
   "$PY" -c "
   import sys; sys.path.insert(0, '{{PYTHONPATH}}')
   import json
   from academic_wiki_lib.cites import resolve_cites
   refs = [...]  # populate from the paper's references-raw
   pre = '{{PRE_BATCH_PAPERS}}'.split(',') if '{{PRE_BATCH_PAPERS}}' else []
   result = resolve_cites('{{WIKI_ROOT}}', refs, pre)
   print(json.dumps({ref: [[pid, score] for pid, score in matches] for ref, matches in result.items()}))
   "
   ```

   Instruct the LLM to review each reference's candidates, choose at most one best match per reference (or none if confidence is low), collect approved paper-ids, update the paper's `cites:` frontmatter field (dedup).

7. **Step 7 — Backlinks.** Per spec §4.3 Step 7. Instruct the subagent to:
   - Read the pre-batch targets list from `{{PRE_BATCH_SNAPSHOT_PATH}}` (one Python call, cache in memory).
   - For each `(slug, kind)` in `created_entities`, for each target that mentions the slug's hyphen-to-space words (use `rg --fixed-strings -l "<slug with spaces>" <target>` via Bash to pre-filter):
   - Call `insert_backlink('{{WIKI_ROOT}}', target, slug)`.

8. **Step 8 — Cross-paper candidates.** Per spec §4.3 Step 8 and §6. Helper invocation:

   ```bash
   "$PY" -c "
   import sys; sys.path.insert(0, '{{PYTHONPATH}}')
   from academic_wiki_lib.cross_paper import compute_top_k_neighbors
   pre = '{{PRE_BATCH_PAPERS}}'.split(',') if '{{PRE_BATCH_PAPERS}}' else []
   neighbors = compute_top_k_neighbors('{{WIKI_ROOT}}', '<paper-id>', pre, k=20)
   print('\n'.join(neighbors))
   "
   ```

   If the neighbor list is empty, report `cross-paper: 0 candidates (no tag overlap)` for that paper. Otherwise, read each neighbor's `## Claims` and `## Results` sections, LLM-compare to the paper's own; accumulate candidate entries in memory. At the end of the subagent run, issue ONE call to `append_candidates(wiki_root, entries)` for all accumulated entries.

9. **Return format.** Per spec §4.4.

- [ ] **Step 3: Verify template has every section**

Run a quick self-check: grep for each section header you wrote, confirm every variable reference resolves against the Inputs list.

```bash
grep -E '^## (Step|Input|Role|Return|Header)' /home/tung491/Work/academic_wiki/skills/wiki/references/batch-compile-full-prompt.md
```
Expected: at least sections for Inputs, Role/constraints, Steps 1–8, Return format.

- [ ] **Step 4: Commit**

```bash
git -C /home/tung491/Work/academic_wiki add skills/wiki/references/batch-compile-full-prompt.md
git -C /home/tung491/Work/academic_wiki commit -m "feat(skill): add full-tier batch compile subagent prompt template"
```

---

## Task 9: Fix Hard-Coded Dates in Paper-Only Template

**Files:**
- Modify: `skills/wiki/references/batch-compile-prompt.md`

Pre-existing latent bug called out by spec §4.1: the paper-only template has `2026-04-22` hard-coded for `created:` and `updated:`. Replace with `{{TODAY}}` so it stays current across runs.

- [ ] **Step 1: Find all hard-coded date occurrences**

Run:
```bash
grep -n '2026-04-22' /home/tung491/Work/academic_wiki/skills/wiki/references/batch-compile-prompt.md
```
Record each line number; expect ~5 occurrences (lines 131, 134, 289, 297, 303 or near).

- [ ] **Step 2: Replace with `{{TODAY}}`**

For each occurrence, replace `2026-04-22` with `{{TODAY}}`. Use `Edit` tool with `replace_all: true` since the literal appears multiple times.

Also: update the template's preamble to list `{{TODAY}}` as one of the variables the orchestrator interpolates (add to the Input section if not present).

- [ ] **Step 3: Verify no stale dates remain**

```bash
grep -n '2026-04' /home/tung491/Work/academic_wiki/skills/wiki/references/batch-compile-prompt.md
```
Expected: no matches (or only doc-comment references unrelated to output dates).

- [ ] **Step 4: Commit**

```bash
git -C /home/tung491/Work/academic_wiki add skills/wiki/references/batch-compile-prompt.md
git -C /home/tung491/Work/academic_wiki commit -m "fix(skill): replace hard-coded date with {{TODAY}} in paper-only prompt"
```

---

## Task 10: Update Compilation Guide for Full-Tier Batch

**Files:**
- Modify: `skills/wiki/references/compilation-guide.md`

Add full-tier batch mode section alongside the existing paper-only batch mode; extend wave commit paths; document final orchestrator pass and resume semantics.

- [ ] **Step 1: Read the existing compilation guide**

Read `/home/tung491/Work/academic_wiki/skills/wiki/references/compilation-guide.md` in full. The "Batch compile mode" section exists (starts around line 72) and is currently paper-only.

- [ ] **Step 2: Edit "Batch compile mode" section**

Make these changes within that section:

1. **Activation subsection:** remove the "Batch mode is paper-only tier only" sentence (if present there; it may be in SKILL.md — check both). Add: "Activation selects full-tier when invoked without `--paper-only` and paper-only when `--paper-only` is set; resume reads the checkpoint's `tier:` field to pick the right template."
2. **Checkpoint management subsection:** document the `tier`, `pre-batch-paper-ids`, `final-pass-status` fields; reference `update_final_pass_status(wiki_root, status)` for transitions. Note that `pre-batch-backlink-targets` lives in `outputs/.pre-batch-snapshot.yml`, not the checkpoint.
3. **Wave partitioning subsection:** add "For full-tier batches, wave-size is ~100 (10 subagents × 10 papers each) vs. ~200 for paper-only. Each subagent's batch is capped at 10 papers for full-tier."
4. **Subagent dispatch subsection:** add a bullet: "For full-tier batches, use `batch-compile-full-prompt.md`; for paper-only, use `batch-compile-prompt.md`. Orchestrator interpolates `{{WIKI_ROOT}}`, `{{PAPER_LIST}}`, `{{PRE_BATCH_PAPERS}}`, `{{PRE_BATCH_SNAPSHOT_PATH}}`, `{{PYTHONPATH}}`, `{{TODAY}}`."
5. **Result collection subsection:** extend the `git add` in wave commits:

    ```bash
    git -C "$WIKI_ROOT" add wiki/papers/ wiki/venues/ wiki/concepts/ wiki/methods/ wiki/open-problems/ outputs/.compile-checkpoint.yml outputs/reports/
    ```

    Note: paper-only tier never writes to `concepts/`, `methods/`, `open-problems/`, or `outputs/reports/` so the extra paths are harmless no-ops for that tier.
6. **NEW subsection: "Pre-batch snapshot (full-tier only)".** Before Wave 1, orchestrator:
   - Computes `pre_batch_paper_ids = [Path(p).stem for p in sorted(wiki/papers/*.md)]`
   - Computes `backlink_targets = scan_targets(wiki_root)` via `pre_batch_snapshot.scan_targets`
   - Writes the targets to `outputs/.pre-batch-snapshot.yml` via `pre_batch_snapshot.write_snapshot`
   - Stores `pre_batch_paper_ids` in the checkpoint via `create_checkpoint(..., tier='full', pre_batch_paper_ids=...)`
7. **NEW subsection: "Final orchestrator pass (full-tier only)"**. After all waves (incl. retry):
   - Transition `final-pass-status` to `in-progress` via `update_final_pass_status`
   - Intra-batch cites: for each batch paper, re-read its `references-raw`, call `resolve_cites(wiki_root, refs, batch_paper_ids)` where `batch_paper_ids` = papers with status `ok` in this checkpoint, append approved matches to that paper's `cites:`
   - Intra-batch backlinks: for each entity page created during this batch (discoverable via `git log --diff-filter=A --name-only <squash-base>..HEAD -- wiki/concepts/ wiki/methods/ wiki/open-problems/`), call `insert_backlink` against each in-batch paper page
   - On success: transition `final-pass-status` to `ok`; commit `compile: final pass (intra-batch cites + backlinks)`
   - On any exception: transition to `failed`; surface a line to the user; do not squash
8. **Resume flow subsection:** add:
   - "If `final-pass-status: pending` or `failed` and all papers are `ok`: skip subagent dispatch entirely; jump straight to the final orchestrator pass."
   - "On resume, validate previously-ok papers still have `wiki/papers/<paper-id>.md` on disk. If any are missing (user deletion between runs), demote to `pending` and include them in the next wave. Log a stderr warning line."
   - "If the snapshot file `outputs/.pre-batch-snapshot.yml` is missing on resume (user or mistake deleted it), re-derive via `pre_batch_snapshot.scan_targets` with a warning — this may drift from the true batch-start state but resume still proceeds."
9. **NEW subsection: "Finalize (full-tier)."**
   - After final pass `ok`, delete `outputs/.pre-batch-snapshot.yml` via `pre_batch_snapshot.delete_snapshot`
   - Proceed with existing squash + index.md + log.md + delete-checkpoint flow
   - Roll up aggregate `entities / cites / backlinks / cross-paper` counters from subagent RESULTS into the log.md line and the final console output

- [ ] **Step 3: Cross-check for contradictions**

Re-read the full file. Verify:
- Activation/routing doesn't contradict SKILL.md (SKILL.md will be updated in Task 11 for consistency).
- Update conflict policy wording is unchanged.
- The existing per-source steps (sequential path) still match the "Steps 1-4b" listed for subagents.

- [ ] **Step 4: Commit**

```bash
git -C /home/tung491/Work/academic_wiki add skills/wiki/references/compilation-guide.md
git -C /home/tung491/Work/academic_wiki commit -m "feat(skill): add full-tier batch mode to compilation guide"
```

---

## Task 11: Update SKILL.md Routing

**Files:**
- Modify: `skills/wiki/SKILL.md`

Remove the paper-only-only assertion from the compile section and document full-tier routing.

- [ ] **Step 1: Find the paper-only-only language**

Run:
```bash
grep -n 'paper-only tier only\|paper-only is implicit\|Wave 2 full-tier batch' /home/tung491/Work/academic_wiki/skills/wiki/SKILL.md
```
Record the line numbers.

- [ ] **Step 2: Edit the assertion out**

Replace the current "Batch mode is paper-only tier only. `--paper-only` is implicit; Wave 2 full-tier batch is future work." block with:

```markdown
Batch mode honors the `--paper-only` flag the same way the sequential path does:

- Without `--paper-only`: **full-tier batch** (paper pages + entity extraction + cites + backlinks + cross-paper candidates). See `references/compilation-guide.md` "Batch compile mode" for full orchestration.
- With `--paper-only`: paper-only batch (today's behavior — paper + venue pages only).

The `tier:` field on the checkpoint drives template selection on resume.
```

- [ ] **Step 3: Edit the "Steps (batch mode)" routing subsection**

In the existing batch mode steps list (SKILL.md around step 4), update the bullet for subagent dispatch:

```markdown
4. **For each wave:** spawn Sonnet subagents in parallel (`run_in_background: true`, `model: "sonnet"`, `mode: "auto"`). Each subagent receives a batch of `{paper-id, extract-path}` tuples. For full-tier batches, use `references/batch-compile-full-prompt.md` (also interpolating `{{PRE_BATCH_PAPERS}}`, `{{PRE_BATCH_SNAPSHOT_PATH}}`, `{{TODAY}}`); for paper-only, use `references/batch-compile-prompt.md`. Subagents write `wiki/papers/`, `wiki/venues/`, and — for full-tier — `wiki/concepts/`, `wiki/methods/`, `wiki/open-problems/`, and candidate entries under `outputs/reports/`.
```

Also add a numbered step between 6 (Retry) and 7 (Squash):

```markdown
6b. **Final orchestrator pass** (full-tier only): resolve intra-batch cites + backlinks. See compilation-guide.md "Final orchestrator pass (full-tier only)". Transitions `final-pass-status` from `pending` to `in-progress` to `ok`.
```

- [ ] **Step 4: Verify no leftover contradictions**

Run:
```bash
grep -n 'paper-only tier only\|future work' /home/tung491/Work/academic_wiki/skills/wiki/SKILL.md
```
Expected: no matches, or only unrelated comments.

- [ ] **Step 5: Commit**

```bash
git -C /home/tung491/Work/academic_wiki add skills/wiki/SKILL.md
git -C /home/tung491/Work/academic_wiki commit -m "feat(skill): route full-tier batch compile from SKILL.md"
```

---

## Task 12: Update Wiki `.gitignore` Template

**Files:**
- Modify: `scripts/academic_wiki_lib/templates.py`

New wikis should ignore `.locks/` and the pre-batch snapshot file.

- [ ] **Step 1: Find the `.gitignore` template content**

Run:
```bash
grep -n 'GITIGNORE\|gitignore\|\.locks' /home/tung491/Work/academic_wiki/scripts/academic_wiki_lib/templates.py
```
Note where the `.gitignore` content is defined (likely a `GITIGNORE` constant or a function).

- [ ] **Step 2: Write a failing test for the new entries**

Add to `tests/test_templates.py` (create if not present — but it exists; append a test):

```python
def test_gitignore_template_includes_locks_and_snapshot():
    from academic_wiki_lib.templates import GITIGNORE  # or the equivalent
    assert ".locks/" in GITIGNORE
    assert "outputs/.pre-batch-snapshot.yml" in GITIGNORE
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_templates.py::test_gitignore_template_includes_locks_and_snapshot -v`
Expected: FAIL — strings not found.

- [ ] **Step 4: Add the two entries**

Edit `templates.py` to append `.locks/` and `outputs/.pre-batch-snapshot.yml` to the `.gitignore` template string.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/tung491/Work/academic_wiki && python -m pytest tests/test_templates.py::test_gitignore_template_includes_locks_and_snapshot -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git -C /home/tung491/Work/academic_wiki add scripts/academic_wiki_lib/templates.py tests/test_templates.py
git -C /home/tung491/Work/academic_wiki commit -m "feat(templates): ignore .locks/ and pre-batch-snapshot.yml in new wikis"
```

---

## Task 13: Integration Smoke Test

**Files:** None created. Manual verification.

- [ ] **Step 1: Run the full test suite**

```bash
cd /home/tung491/Work/academic_wiki && python -m pytest -v
```
Expected: all tests PASS (existing + new from tasks 1-12).

- [ ] **Step 2: Dry-run the Python helpers against a real wiki**

Use a scratch wiki or the user's active wiki cautiously:

```bash
cd /home/tung491/Work/academic_wiki
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from academic_wiki_lib.pre_batch_snapshot import scan_targets, write_snapshot, read_snapshot, delete_snapshot
from academic_wiki_lib.entity_lock import acquire
from academic_wiki_lib.checkpoint import create_checkpoint, read_checkpoint, delete_checkpoint

wiki = '/tmp/smoketest-wiki'
import os; os.makedirs(wiki + '/outputs', exist_ok=True)
os.makedirs(wiki + '/wiki/papers', exist_ok=True)

# Snapshot scan on empty wiki
print('scan_targets:', scan_targets(wiki))

# Write + read roundtrip
write_snapshot(wiki, ['wiki/papers/a.md'])
print('read_snapshot:', read_snapshot(wiki))
delete_snapshot(wiki)

# Create full-tier checkpoint
cp = create_checkpoint(wiki, [('p1', '/x')], wave_size=1, tier='full', pre_batch_paper_ids=['old1'])
print('cp.tier:', cp['tier'])
print('cp.final-pass-status:', cp['final-pass-status'])
print('cp.pre-batch-paper-ids:', cp['pre-batch-paper-ids'])

# Lock acquire/release
with acquire(wiki, kind='concept', key='smoke'):
    print('Lock acquired')
print('Lock released')

delete_checkpoint(wiki)
import shutil; shutil.rmtree(wiki)
print('OK')
"
```

Expected: prints `OK` at the end with no errors.

- [ ] **Step 3: Verify template renders correctly on a fresh init**

Run:
```bash
cd /home/tung491/Work/academic_wiki
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from academic_wiki_lib.templates import GITIGNORE
print(GITIGNORE)
"
```
Expected: output includes `.locks/` and `outputs/.pre-batch-snapshot.yml`.

- [ ] **Step 4: Commit any smoke-test fixes**

If the smoke test revealed any issues, fix and commit:

```bash
git -C /home/tung491/Work/academic_wiki add -u
git -C /home/tung491/Work/academic_wiki commit -m "fix: address issues found during full-tier batch compile smoke test"
```

If no fixes were needed, skip this step.

---

## Done

All tasks complete. Next actions (out of scope for this plan but worth noting):
- Wave 3: observe real-run behavior on a 100-500 paper batch, tune `wave-size` and `k` for cross-paper.
- Wave 3: explore embedding-based cross-paper neighbors via `qmd`.
- Wave 3: handle intra-batch cross-paper detection if users find the gap meaningful.
