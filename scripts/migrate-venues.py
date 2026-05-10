#!/usr/bin/env python3
"""Venue migration CLI per spec 2026-05-10.

Walks wiki/venues/, computes a normalization plan, and either prints a dry-run
report or applies the consolidation (renames + merges + paper-page rewrites).
"""
from __future__ import annotations

import argparse
import datetime
import subprocess  # used by _run_apply (Tasks 11-14)
import sys
from datetime import date
from pathlib import Path

import yaml

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

from academic_wiki_lib.frontmatter import read_frontmatter, write_frontmatter
from academic_wiki_lib.lockfile import LockHeld, acquire, release
from academic_wiki_lib.templates import venue_md_stub
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
    fm["updated"] = datetime.date.fromisoformat(today)
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


def _split_stub(stub: str) -> tuple[dict, str]:
    """Parse a venue_md_stub() string into (fm dict, body).

    Only intended for use with venue_md_stub() output — not a general
    YAML+markdown parser.
    """
    if not stub.startswith("---\n"):
        return {}, stub
    rest = stub[4:]
    end = rest.find("\n---\n")
    if end < 0:
        return {}, stub
    fm_text = rest[:end]
    body = rest[end + 5:]
    fm = yaml.safe_load(fm_text) or {}
    return fm, body


def _apply_merge(wiki_root: Path, group: Group, today: str) -> None:
    """Merge a multi-page group into the canonical slug page.

    Writes the canonical page (overwrites if it exists), archives every
    member's body under a 'Merged from' section, deletes the source pages
    (except the canonical one if it pre-existed). All old slugs become aliases.
    """
    venues_dir = wiki_root / "wiki" / "venues"
    canon_path = venues_dir / f"{group.new_slug}.md"

    # Stub frontmatter + standard preamble body
    stub = venue_md_stub(
        slug=group.new_slug,
        name=group.new_canonical_name,
        venue_type=group.new_venue_type,
        paper_ids=group.new_papers,
        field_tags=group.new_tags,
        today=today,
    )
    stub_fm, stub_body = _split_stub(stub)
    # Keep `created` as datetime.date so YAML serializes it the same way as
    # `updated` (both unquoted ISO dates) — venue_md_stub stores the today
    # value as datetime.date, so coerce the override to match.
    if group.new_created:
        stub_fm["created"] = datetime.date.fromisoformat(group.new_created)

    # Aliases = union of all members' existing aliases + every member's old slug
    aliases: list[str] = []
    for m in group.members:
        existing_fm, _ = read_frontmatter(m.path)
        for a in existing_fm.get("aliases") or []:
            if a not in aliases:
                aliases.append(a)
        if m.slug not in aliases:
            aliases.append(m.slug)
    # Don't list the canonical slug in its own aliases.
    aliases = [a for a in aliases if a != group.new_slug]
    stub_fm["aliases"] = aliases

    # Build the body: stub preamble + Merged from section
    merged_section_lines = ["", "## Merged from", ""]
    for m in group.members:
        merged_section_lines.append(f"### `{m.slug}` — {m.name}")
        merged_section_lines.append("")
        merged_section_lines.append(m.body.rstrip())
        merged_section_lines.append("")
    final_body = stub_body + "\n".join(merged_section_lines) + "\n"

    # Delete every source page (except the canonical-slug one — we're rewriting it)
    for m in group.members:
        if m.path == canon_path:
            continue  # will be overwritten by write_frontmatter below
        try:
            subprocess.run(["git", "rm", "-q", str(m.path)],
                           cwd=wiki_root, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            m.path.unlink(missing_ok=True)

    canon_path.parent.mkdir(parents=True, exist_ok=True)
    write_frontmatter(canon_path, stub_fm, final_body)


def _apply_paper_rewrites(rewrites: list[PaperRewrite], today: str) -> None:
    today_date = datetime.date.fromisoformat(today)
    for r in rewrites:
        fm, body = read_frontmatter(r.path)
        fm["venue"] = r.new_slug
        new_tags: list[str] = []
        old_tag = f"venue/{r.old_slug}"
        new_tag = f"venue/{r.new_slug}"
        # Both old_tag and new_tag collapse to a single new_tag (dedup against
        # partially-migrated papers that already have both); other tags pass
        # through preserving order.
        for t in fm.get("tags") or []:
            if t in (old_tag, new_tag):
                if new_tag not in new_tags:
                    new_tags.append(new_tag)
            else:
                new_tags.append(t)
        if new_tag not in new_tags:
            new_tags.append(new_tag)
        fm["tags"] = new_tags
        fm["updated"] = today_date
        write_frontmatter(r.path, fm, body)


def _run_apply(wiki_root: Path) -> int:
    today = _today()
    plan, rewrites, report = _build_report(wiki_root, today)
    _write_report(wiki_root, today, report)

    for g in plan.groups:
        if g.is_merge:
            _apply_merge(wiki_root, g, today)
        else:
            _apply_rename(wiki_root, g, today)

    _apply_paper_rewrites(rewrites, today)
    # Task 14 adds preconditions/snapshot/commit
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
