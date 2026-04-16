#!/usr/bin/env python3
"""Consolidated BibTeX export per spec §5.6.

Selectors (≥1 of the first six required; combinable with AND semantics):
    --project, --field, --tag, --query, --keys, --since
Label:
    --label (override); else priority: project → field → tag → query → keys[0] → since
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

# Make the lib importable when running as a script
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

from academic_wiki_lib.frontmatter import read_frontmatter
from academic_wiki_lib.slug import make_slug


def _parse_args(argv):
    p = argparse.ArgumentParser(
        description="Export consolidated BibTeX from an academic-wiki.",
    )
    p.add_argument("wiki_root")
    p.add_argument("--project", help="papers tagged project/<slug>")
    p.add_argument("--field", help="papers tagged field/<slug>")
    p.add_argument("--tag", help="full tag including prefix")
    p.add_argument("--query", help="hybrid search text (resolved by SKILL layer; CLI expects --keys)")
    p.add_argument("--keys", help="comma-separated explicit list of paper-ids")
    p.add_argument("--since", help="YYYY-MM-DD — only papers with created:>=this date")
    p.add_argument("--label", help="override for output filename label")
    return p.parse_args(argv)


def _label_from_selectors(args) -> str:
    """Derive the output-filename label from selectors by priority order."""
    if args.label:
        return make_slug(args.label)
    for attr in ("project", "field", "tag", "query"):
        val = getattr(args, attr)
        if val:
            return make_slug(val)
    if args.keys:
        first = args.keys.split(",")[0].strip()
        if first:
            return make_slug(first)
    if args.since:
        return args.since
    return "export"


def _matches(fm: dict, args) -> bool:
    tags = fm.get("tags") or []
    if args.project and f"project/{args.project}" not in tags:
        return False
    if args.field and f"field/{args.field}" not in tags:
        return False
    if args.tag and args.tag not in tags:
        return False
    if args.since:
        try:
            created = datetime.strptime(str(fm.get("created", "")), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return False
        try:
            since = datetime.strptime(args.since, "%Y-%m-%d").date()
        except ValueError:
            return False
        if created < since:
            return False
    return True


def export(argv=None) -> int:
    args = _parse_args(argv)

    # Enforce: ≥1 of the first six selectors required
    any_selector = any(
        getattr(args, a) for a in ("project", "field", "tag", "query", "keys", "since")
    )
    if not any_selector:
        print("Error: at least one of --project, --field, --tag, --query, --keys, --since is required.", file=sys.stderr)
        return 2

    wr = Path(args.wiki_root)
    papers_dir = wr / "wiki" / "papers"
    bib_dir = wr / "raw" / "bib"

    selected: list[tuple[str, Path]] = []
    seen: set[str] = set()

    # --keys path: explicit ids
    if args.keys:
        for key in [k.strip() for k in args.keys.split(",") if k.strip()]:
            paper_path = papers_dir / f"{key}.md"
            if paper_path.exists():
                if key not in seen:
                    selected.append((key, bib_dir / f"{key}.bib"))
                    seen.add(key)

    # Tag/project/field/since path: scan papers
    if any((args.project, args.field, args.tag, args.since)):
        if not papers_dir.is_dir():
            print("No papers directory found.")
            return 1
        for md in sorted(papers_dir.glob("*.md")):
            try:
                fm, _ = read_frontmatter(str(md))
            except Exception:
                continue
            if _matches(fm, args):
                pid = fm.get("paper-id") or md.stem
                if pid not in seen:
                    selected.append((pid, bib_dir / f"{pid}.bib"))
                    seen.add(pid)

    if not selected:
        print("No papers match the selector(s).")
        return 1

    incomplete: list[tuple[str, str]] = []
    content_parts: list[str] = []
    for pid, bib_path in selected:
        if not bib_path.exists():
            incomplete.append((pid, "missing .bib file"))
            continue
        body = bib_path.read_text()
        if re.search(r"bib-incomplete:\s*true", body, re.IGNORECASE):
            incomplete.append((pid, "bib-incomplete flag"))
        content_parts.append(f"% {pid}\n{body.strip()}\n")

    label = _label_from_selectors(args)
    out_dir = wr / "outputs" / "bib"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date.today().isoformat()}-{label}.bib"
    out_path.write_text("\n".join(content_parts) + "\n" if content_parts else "")

    print(f"Exported {len(selected)} papers to {out_path}")
    if incomplete:
        print(f"{len(incomplete)} papers have bib-incomplete issues:")
        for pid, reason in incomplete:
            print(f"  - {pid}: {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(export())
