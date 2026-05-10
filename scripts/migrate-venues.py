#!/usr/bin/env python3
"""Venue migration CLI per spec 2026-05-10.

Walks wiki/venues/, computes a normalization plan, and either prints a dry-run
report or applies the consolidation (renames + merges + paper-page rewrites).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

from academic_wiki_lib.lockfile import LockHeld, acquire, release
from academic_wiki_lib.venue_migrate import collect_paper_rewrites, compute_plan, render_report


def _today() -> str:
    return date.today().isoformat()


def _run_dry_run(wiki_root: Path) -> tuple[int, str]:
    """Compute plan, write report. Return (exit_code, report_path)."""
    plan = compute_plan(wiki_root)
    rewrites = collect_paper_rewrites(wiki_root, plan)
    report = render_report(plan, rewrites, today=_today())
    out_path = wiki_root / "outputs" / "reports" / f"{_today()}-venue-migration.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    return 0, str(out_path)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Venue migration tool")
    p.add_argument("--wiki-path", required=True, type=Path)
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--dry-run", action="store_true", default=False)
    grp.add_argument("--apply", action="store_true", default=False)
    args = p.parse_args(argv)

    wiki_root = args.wiki_path.resolve()
    if not wiki_root.is_dir():
        print(f"ERROR: wiki path not found: {wiki_root}", file=sys.stderr)
        return 2

    lock_path = wiki_root / ".lock"
    op = "migrate-venues:apply" if args.apply else "migrate-venues:dry-run"
    try:
        acquire(lock_path, op)
    except LockHeld as e:
        print(f"ERROR: lock held — {e}", file=sys.stderr)
        return 3

    try:
        if args.apply:
            print("ERROR: --apply not yet implemented (Tasks 11-15)", file=sys.stderr)
            return 4
        rc, report_path = _run_dry_run(wiki_root)
        print(f"Dry-run report written to: {report_path}")
        return rc
    finally:
        release(lock_path)


if __name__ == "__main__":
    raise SystemExit(main())
