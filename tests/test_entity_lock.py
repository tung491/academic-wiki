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
