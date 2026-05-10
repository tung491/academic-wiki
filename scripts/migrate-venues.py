#!/usr/bin/env python3
"""Venue migration CLI per spec 2026-05-10.

Walks wiki/venues/, computes a normalization plan, and either prints a dry-run
report or applies the consolidation (renames + merges + paper-page rewrites).
"""
from __future__ import annotations

import argparse
import subprocess  # used by _run_apply (Tasks 11-14)
import sys
from datetime import date
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

from academic_wiki_lib.frontmatter import read_frontmatter, write_frontmatter
from academic_wiki_lib.lockfile import LockHeld, acquire, release
from academic_wiki_lib.venue_migrate import (
    Group,
    PaperRewrite,
    Plan,
    collect_paper_rewrites,
    compute_plan,
    render_report,
)


def _today() -> str:
    return date.today().isoformat()


def _build_report(wiki_root: Path, today: str) -> tuple[Plan, list[PaperRewrite], str]:
    plan = compute_plan(wiki_root)
    rewrites = collect_paper_rewrites(wiki_root, plan)
    report = render_report(plan, rewrites, today=today)
    return plan, rewrites, report


def _write_report(wiki_root: Path, today: str, report: str) -> Path:
    out_path = wiki_root / "outputs" / "reports" / f"{today}-venue-migration.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    return out_path


def _apply_rename(wiki_root: Path, group: Group, today: str) -> None:
    """Rename a single-page group's file and update its slug/name/aliases.

    Note: if `git mv` succeeds but `write_frontmatter` then fails, the file is
    at the new path with stale frontmatter. Task 14's dirty-tree precondition
    refuses to re-run --apply on the resulting half-migrated tree; the user
    must `git restore` and re-run. Tracking this here rather than adding a
    crash-safe staging dance.
    """
    page = group.members[0]
    new_path = page.path.parent / f"{group.new_slug}.md"
    fm, body = read_frontmatter(page.path)
    fm["slug"] = group.new_slug
    fm["name"] = group.new_canonical_name
    fm["updated"] = today
    aliases = list(fm.get("aliases") or [])
    if page.slug not in aliases:
        aliases.append(page.slug)
    fm["aliases"] = aliases
    # `git mv` preserves history when the file is tracked; fall back to a
    # plain rename for untracked files or non-git directories.
    try:
        subprocess.run(["git", "mv", str(page.path), str(new_path)],
                       cwd=wiki_root, check=True, capture_output=True)
    except subprocess.CalledProcessError:
        page.path.rename(new_path)
    write_frontmatter(new_path, fm, body)


def _run_apply(wiki_root: Path) -> int:
    today = _today()
    plan, rewrites, report = _build_report(wiki_root, today)
    _write_report(wiki_root, today, report)

    for g in plan.groups:
        if g.is_merge:
            # Task 12 implements merges
            continue
        _apply_rename(wiki_root, g, today)
    # Task 13 adds paper-page rewrites; Task 14 adds preconditions/snapshot/commit
    return 0


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
            return _run_apply(wiki_root)
        today = _today()
        plan, rewrites, report = _build_report(wiki_root, today)
        out = _write_report(wiki_root, today, report)
        print(f"Dry-run report written to: {out}")
        return 0
    finally:
        release(lock_path)


if __name__ == "__main__":
    raise SystemExit(main())
