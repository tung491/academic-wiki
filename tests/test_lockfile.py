"""Tests for advisory lockfile per spec §8.1."""
import os

import pytest

from academic_wiki_lib.lockfile import (
    LockHeld,
    StaleLockRecovered,
    acquire,
    release,
)


def test_acquire_empty(tmp_path):
    lock = tmp_path / ".lock"
    acquire(str(lock), op="ingest")
    assert lock.exists()
    content = lock.read_text()
    assert f"{os.getpid()}:" in content
    assert "ingest" in content


def test_acquire_fails_when_held_by_live_pid(tmp_path):
    lock = tmp_path / ".lock"
    # Simulate a live holder: use current pid (always alive)
    lock.write_text(f"{os.getpid()}:2026-04-16T10:00:00Z:compile")
    with pytest.raises(LockHeld):
        acquire(str(lock), op="ingest")


def test_acquire_recovers_stale_lock(tmp_path):
    lock = tmp_path / ".lock"
    # Use a pid that is very unlikely to exist. On Linux, /proc is authoritative.
    # 99999999 is out of range on a standard system.
    dead_pid = 99999999
    lock.write_text(f"{dead_pid}:2026-04-16T10:00:00Z:ingest")
    with pytest.warns(StaleLockRecovered):
        acquire(str(lock), op="compile")
    # New lock belongs to us
    assert f"{os.getpid()}" in lock.read_text()


def test_release(tmp_path):
    lock = tmp_path / ".lock"
    acquire(str(lock), op="ingest")
    assert lock.exists()
    release(str(lock))
    assert not lock.exists()


def test_release_silent_if_absent(tmp_path):
    lock = tmp_path / ".lock"
    release(str(lock))  # no-op, no error


def test_acquire_recovers_malformed_lock(tmp_path):
    """A lock file with garbage contents should be treated as stale and recovered."""
    lock = tmp_path / ".lock"
    lock.write_text("total garbage not a pid")
    with pytest.warns(StaleLockRecovered):
        acquire(str(lock), op="ingest")
    assert f"{os.getpid()}" in lock.read_text()


def test_acquire_accepts_pathlib_path(tmp_path):
    lock = tmp_path / ".lock"
    acquire(lock, op="ingest")  # pass Path, not str
    assert lock.exists()
    release(lock)


def test_lock_content_format(tmp_path):
    """Spec §8.1: lockfile content is <pid>:<iso-timestamp>:<op>."""
    lock = tmp_path / ".lock"
    acquire(str(lock), op="compile")
    content = lock.read_text()
    parts = content.split(":", 2)
    assert len(parts) == 3
    assert parts[0] == str(os.getpid())
    # ISO-8601 UTC: YYYY-MM-DDTHH:MM:SS+00:00 or similar. Check YYYY-MM-DDTHH at minimum.
    import re
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}", parts[1])
    assert parts[2] == "compile"


def test_acquire_then_release_then_acquire(tmp_path):
    """Normal sequence: take, release, re-take — no issues."""
    lock = tmp_path / ".lock"
    acquire(str(lock), op="ingest")
    release(str(lock))
    acquire(str(lock), op="compile")  # should succeed
    release(str(lock))
    assert not lock.exists()


def test_parser_handles_extended_iso_timestamp(tmp_path):
    """If a lock file has extended-ISO colons (YYYY-MM-DDTHH:MM:SS), parser must still work."""
    lock = tmp_path / ".lock"
    # Dead pid + extended ISO with colons
    lock.write_text("99999999:2026-04-16T10:30:45Z:ingest")
    with pytest.warns(StaleLockRecovered):
        acquire(str(lock), op="compile")
    # Lock should be cleanly ours now
    assert f"{os.getpid()}" in lock.read_text()


def test_acquire_is_atomic_on_exclusive_create(tmp_path):
    """acquire uses O_EXCL so the file it creates didn't exist before. Verify by
    seeing FileExistsError propagate as LockHeld when a live-pid lock exists."""
    lock = tmp_path / ".lock"
    lock.write_text(f"{os.getpid()}:20260416T000000Z:compile")
    with pytest.raises(LockHeld) as exc_info:
        acquire(str(lock), op="ingest")
    # Error message should contain the op and pid of the holder
    assert "compile" in str(exc_info.value)
    assert str(os.getpid()) in str(exc_info.value)
