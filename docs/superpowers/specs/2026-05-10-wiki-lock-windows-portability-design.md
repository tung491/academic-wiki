# Wiki Lock Cross-Platform Portability — Design

**Date:** 2026-05-10
**Status:** Draft, awaiting implementation
**Touches:** `scripts/academic_wiki_lib/lockfile.py`, `scripts/academic_wiki_lib/entity_lock.py`, new `scripts/academic_wiki_lib/cli.py`, `skills/wiki/SKILL.md`, `pyproject.toml`, `tests/`

## Problem

The wiki's locking layer is currently POSIX-only:

1. **`scripts/academic_wiki_lib/entity_lock.py`** does `import fcntl` at module load. The `fcntl` module does not exist on Windows; importing the module raises `ModuleNotFoundError` immediately, breaking every consumer (`entity_pages.py`, `cross_paper.py`, `backlinks.py`).
2. **`scripts/academic_wiki_lib/lockfile.py`** uses `os.kill(pid, 0)` for stale-PID detection. On Windows, `os.kill(pid, 0)` does not raise `ProcessLookupError` for non-existent PIDs the way it does on POSIX — instead it raises `OSError` with platform-specific errnos (commonly `EINVAL`/`ERROR_INVALID_PARAMETER` 87, or `ERROR_ACCESS_DENIED` 5). The current handler only catches `ProcessLookupError` and `PermissionError`, so on Windows a dead-PID lock would be misclassified and stale recovery would fail.
3. **`skills/wiki/SKILL.md`** uses bash heredocs (`"$PY" -c "..."`) and `trap '...' EXIT` for lock cleanup. Neither is portable to PowerShell or `cmd.exe`.

The wiki must run on Windows with no degradation in correctness or in the cross-process mutex semantics required by parallel batch-compile subagents.

## Non-goals

- Replacing the per-step LLM judgment embedded in SKILL.md with a single Python entry-point per command. Each top-level wiki op stays a sequence of agent-mediated steps.
- Migrating `lockfile.py`'s O_CREAT|O_EXCL marker-file approach to `filelock`. The global wiki lock must persist across separate Python invocations within one SKILL.md flow; `filelock`'s held-FD model can't satisfy that.
- WSL-only deployment. Windows-native shells (PowerShell 7+, `cmd.exe`) must work.
- Refactoring path layout for `pyproject.toml` packaging. Keep the existing `scripts/academic_wiki_lib/` location and rely on `PYTHONPATH` for imports.

## Design

### Three-primitive division

| Lock | Lifecycle | Primitive | Cross-platform path |
|---|---|---|---|
| Global wiki lock — `<wiki>/.lock` | persists across separate Python invocations within one SKILL.md flow | `O_CREAT\|O_EXCL` marker file + PID liveness | unchanged shape; only `_is_alive()` gets a Windows ctypes branch |
| Per-entity lock — `<wiki>/.locks/<kind>/<key>.lock` | held within one Python invocation by a batch-compile subagent | held FD with OS-level mutex | replace `fcntl.flock` with the `filelock` library (handles POSIX + Windows internally) |
| Orchestration — SKILL.md | bash trap as belt-and-suspenders for global lock | bash heredoc `python -c "..."` + `trap EXIT` | new `python -m academic_wiki_lib.cli <subcommand>` calls; drop trap; rely on stale-PID recovery |

The asymmetry between the global and per-entity locks is intentional. `filelock` would be wrong for the global lock because each SKILL.md step is a fresh Python process — a held FD would release immediately when that process exits, freeing the lock between every step. Marker-file + PID-liveness is the only model that survives multiple `python …` invocations bridged by a shell. Conversely, marker-file would be heavier than necessary for per-entity locks, which are short-lived inside one process.

### Component A: `lockfile.py` cross-platform liveness

The only API-level change is the implementation of `_is_alive(pid: int) -> bool`. Public signatures (`acquire`, `release`, `LockHeld`, `StaleLockRecovered`, `_parse_lock_content`) are unchanged.

```python
import os
import sys

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    ERROR_ACCESS_DENIED = 5

    def _is_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            err = ctypes.get_last_error()
            if err == ERROR_ACCESS_DENIED:
                return True   # exists but we can't query — treat as alive
            return False       # invalid PID / not found
        try:
            exit_code = wintypes.DWORD()
            if not _kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            _kernel32.CloseHandle(handle)
else:
    def _is_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
```

The Windows branch uses `PROCESS_QUERY_LIMITED_INFORMATION` (granted to all callers regardless of token privilege on Vista+, unlike `PROCESS_QUERY_INFORMATION`) so `OpenProcess` doesn't fail for permission reasons except in deliberately-restricted scenarios.

PID reuse risk on Windows is the same as POSIX and not introduced by this change; spec §8.1 already acknowledges the lock-content `<pid>:<ts>:<op>` format aids human disambiguation.

### Component B: `entity_lock.py` via `filelock`

Replace the `fcntl` import + manual non-blocking-retry loop with `filelock.FileLock`. The public API (`@contextmanager acquire(wiki_root, kind, key, timeout_seconds)`) is preserved; existing callers in `entity_pages.py`, `cross_paper.py`, `backlinks.py` and existing tests need no edits.

```python
"""Per-entity OS file lock for atomic read-modify-write on shared wiki pages."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, Timeout

VALID_KINDS = frozenset({"paper", "concept", "method", "open-problem", "venue", "reports"})


def _lock_path(wiki_root, kind: str, key: str) -> Path:
    return Path(os.fspath(wiki_root)) / ".locks" / kind / f"{key}.lock"


@contextmanager
def acquire(wiki_root, kind: str, key: str, timeout_seconds: float = 60.0):
    """Acquire exclusive OS file lock on <wiki_root>/.locks/<kind>/<key>.lock.

    Raises ValueError if kind is not one of VALID_KINDS.
    Raises TimeoutError if the lock cannot be acquired within timeout_seconds.

    The lock auto-releases when this process dies (crash or clean), so stale
    locks are not normally possible. If a process is wedged but alive, the
    user clears <wiki_root>/.locks/ manually before retrying.
    """
    if kind not in VALID_KINDS:
        raise ValueError(
            f"Unknown entity lock kind: {kind!r} (expected one of {sorted(VALID_KINDS)})"
        )
    path = _lock_path(wiki_root, kind, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(path), timeout=timeout_seconds)
    try:
        lock.acquire()
    except Timeout:
        raise TimeoutError(
            f"Could not acquire entity lock {kind}/{key} within {timeout_seconds}s"
        ) from None
    try:
        yield
    finally:
        lock.release()
```

`filelock` (≥3.12) is pure Python with zero transitive dependencies. Internally it uses `fcntl.flock` on POSIX and `msvcrt.locking` on Windows, both of which auto-release when the holding process exits — preserving the current crash-safety semantic.

### Component C: New `cli.py` module

`scripts/academic_wiki_lib/cli.py` exposes `python -m academic_wiki_lib.cli <subcommand> [args]`. One module, one dispatcher, runs identically in bash/zsh/PowerShell/cmd. Each subcommand is a thin wrapper around an existing helper.

```python
"""Cross-shell CLI shim for SKILL.md. All subcommands are thin wrappers
around academic_wiki_lib helpers; they exist so that wiki orchestration
can run identically on bash, zsh, PowerShell, and cmd."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _cmd_acquire(args) -> int:
    from academic_wiki_lib.lockfile import LockHeld, acquire
    lock_path = Path(args.wiki_root) / ".lock"
    try:
        acquire(lock_path, op=args.op)
    except LockHeld as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


def _cmd_release(args) -> int:
    from academic_wiki_lib.lockfile import release
    release(Path(args.wiki_root) / ".lock")
    return 0


def _cmd_source_sha(args) -> int:
    from academic_wiki_lib.source_sha import file_sha256
    print(file_sha256(args.path))
    return 0


def _cmd_find_paper(args) -> int:
    from academic_wiki_lib.paper_id import find_existing_paper_by_identifiers
    identifiers = {}
    if args.doi: identifiers["doi"] = args.doi
    if args.arxiv: identifiers["arxiv"] = args.arxiv
    if args.url: identifiers["url"] = args.url
    pid = find_existing_paper_by_identifiers(args.wiki_root, identifiers)
    print(json.dumps({"paper_id": pid}))
    return 0


def _cmd_read_frontmatter(args) -> int:
    from academic_wiki_lib.frontmatter import read_frontmatter
    print(json.dumps(read_frontmatter(args.path)))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="academic_wiki_lib.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("acquire")
    p.add_argument("wiki_root")
    p.add_argument("--op", required=True)
    p.set_defaults(func=_cmd_acquire)

    p = sub.add_parser("release")
    p.add_argument("wiki_root")
    p.set_defaults(func=_cmd_release)

    p = sub.add_parser("source-sha")
    p.add_argument("path")
    p.set_defaults(func=_cmd_source_sha)

    p = sub.add_parser("find-paper")
    p.add_argument("wiki_root")
    p.add_argument("--doi", default=None)
    p.add_argument("--arxiv", default=None)
    p.add_argument("--url", default=None)
    p.set_defaults(func=_cmd_find_paper)

    p = sub.add_parser("read-frontmatter")
    p.add_argument("path")
    p.set_defaults(func=_cmd_read_frontmatter)

    # Additional subcommands added on demand as SKILL.md is migrated.

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

The implementer must grep `skills/wiki/SKILL.md` exhaustively for `python -c` blocks and add a subcommand for every distinct invocation pattern; the list above seeds the most common ones but is not exhaustive. Each new subcommand is a thin wrapper — no new business logic lives in `cli.py`.

Exit-code convention:
- `0` — success
- `1` — operation-specific failure (e.g. `LockHeld`, file not found, identifier mismatch)
- `2` — unexpected error (uncaught exception; falls through to argparse default)

### Component D: SKILL.md changes

Three structural edits:

1. **Setup block at the top of every command's "Steps" section** (~6 lines). POSIX vs PowerShell `PY` + `PYTHONPATH` setup is the only platform-specific code path. Below this point all commands are byte-for-byte identical.

   ```bash
   # POSIX (bash/zsh)
   export PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts"
   PY="${CLAUDE_PLUGIN_ROOT}/.venv/bin/python"
   ```

   ```powershell
   # PowerShell
   $env:PYTHONPATH = "$env:CLAUDE_PLUGIN_ROOT\scripts"
   $PY = "$env:CLAUDE_PLUGIN_ROOT\.venv\Scripts\python.exe"
   ```

2. **Replace every `"$PY" -c "<heredoc>"` with `"$PY" -m academic_wiki_lib.cli <subcommand>`.** Approximately 12 sites in the current SKILL.md. The implementer must add a subcommand for every distinct heredoc pattern in `cli.py`.

3. **Drop every `trap '... release ...' EXIT`.** Approximately 6 sites. Replace with one explicit `release` call on every error-exit path inside the SKILL.md step lists. Failure-recovery story for agent crashes is captured in §8.1 of the wiki spec (see Component E).

### Component E: Spec updates

`docs/superpowers/specs/2026-04-16-academic-wiki-design.md` §8.1 (Concurrent-operation protection) gets one paragraph appended:

> **Cross-platform behavior.** Stale-lock detection works on Windows as well as POSIX via `_is_alive()`'s platform branch (POSIX uses `os.kill(pid, 0)`; Windows uses `OpenProcess` + `GetExitCodeProcess` via `ctypes`). The bash `trap EXIT` cleanup mechanism documented in earlier drafts of SKILL.md has been removed in favor of explicit `release` calls on every error path; agent-crash recovery now relies entirely on stale-PID detection. Per-entity locks (`<wiki>/.locks/<kind>/<key>.lock`) use the `filelock` library, which selects the appropriate OS primitive (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows) and auto-releases on process death across both platforms.

`docs/superpowers/specs/2026-04-23-full-tier-batch-compile-design.md` §3.1 already says "Uses POSIX `fcntl.flock`". Update to: "Uses `filelock.FileLock` (which dispatches to `fcntl.flock` on POSIX and `msvcrt.locking` on Windows). Auto-releases on process death on both platforms."

### Component F: Tests + packaging

- **`tests/test_lockfile.py`** — add:
  - `test_is_alive_returns_true_for_self_pid()` — calls `_is_alive(os.getpid())`; asserts True.
  - `test_is_alive_returns_false_for_dead_pid()` — uses 99999999 (POSIX-friendly) and a Windows-friendly equivalent (e.g. picks an unused PID via spawning + waiting for a child, then querying after exit). Asserts False on whichever platform the test runs on.
  - The existing `test_acquire_recovers_stale_lock` already exercises the dead-PID path via 99999999. Add a `pytest.mark.skipif(sys.platform == "win32")` only if 99999999 turns out to be a possible live-PID range on Windows; otherwise leave it cross-platform.
- **`tests/test_entity_lock.py`** — no source changes. The `multiprocessing.Process` cross-process test runs under the default `spawn` start method on Windows; the helper imports `acquire` inside the child function so spawn-pickling works. Verify by running on Windows.
- **New `tests/test_cli.py`** — for each subcommand, run `subprocess.run([sys.executable, "-m", "academic_wiki_lib.cli", <subcmd>, ...], capture_output=True)` and assert exit code + stdout shape. Cover both success and the `LockHeld` failure case for `acquire`.
- **CI matrix** — if `.github/workflows/` has a CI config today, extend it with a `windows-latest` job running the same `pytest` command. If no CI exists, this is out of scope and tracked as a follow-up; the implementation must pass tests locally on Windows before being merged.
- **`pyproject.toml`** — add `filelock>=3.12` to base `dependencies`. No other changes; `[tool.setuptools.packages.find]` and `[tool.pytest.ini_options]` stay as-is.

## Failure modes & recovery

| Failure | Behavior |
|---|---|
| Agent crashes between `acquire` and `release` (any platform) | Lock file persists. On next operation, `_is_alive(pid)` returns False (POSIX or Windows), `StaleLockRecovered` is warned, lock is taken. |
| Long-running operation (legit holder still alive) | `LockHeld` raised on any concurrent attempt. User waits or kills the holder. |
| PID reuse — a different live process has the holder's PID | `_is_alive` returns True; new attempt fails with `LockHeld` and a misleading op label. User kills the lock manually (`rm <wiki>/.lock` on POSIX; `del <wiki>\.lock` on Windows). Same risk on POSIX as today; not regressed. |
| `filelock` itself can't acquire (e.g. lock-file directory is read-only) | Raises `OSError`. Propagates to caller. Spec §8.1 already lists "Lock file unwriteable" as an explicit failure mode. |
| `_is_alive` on Windows hits a process owned by a different user | `OpenProcess` returns NULL with `ERROR_ACCESS_DENIED`. `_is_alive` returns True (consistent with POSIX `PermissionError` branch). Lock is treated as held. |

## Implementation order

1. Add `filelock>=3.12` to `pyproject.toml` deps; run `uv lock` / equivalent.
2. Rewrite `entity_lock.py` per Component B. Existing tests should keep passing.
3. Add Windows branch in `lockfile.py` `_is_alive` per Component A. Add the two new liveness tests.
4. Write `cli.py` per Component C with the seed subcommands.
5. Migrate SKILL.md per Component D — replace one section at a time, run the wiki end-to-end on POSIX after each, smoke-test on Windows once at the end.
6. Update spec docs per Component E.
7. Add Windows CI job if CI exists; otherwise log a follow-up issue.

## Open questions for review

- **CI presence**: this design assumes CI exists or a Windows machine is available for one-shot manual verification. If neither, the implementer must call this out before merging.
- **Subcommand inventory**: `cli.py` seeds five subcommands. The full list is determined by an exhaustive grep of SKILL.md `python -c` blocks during implementation, not at design time — so the implementer must commit to that grep-and-add step.
- **Setup-block placement in SKILL.md**: putting POSIX+PowerShell snippets at the top of every command vs. once at file-top with a back-reference. The current proposal is "once per command" because each top-level command's `Steps` section is the natural copy-paste boundary; revisit if duplication becomes painful.
