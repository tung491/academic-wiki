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


def _sanitize_label(label: str) -> str:
    """Keep label mostly verbatim (per spec §5.6), but strip filesystem-unsafe chars."""
    # Replace / \ \0 with hyphens; keep spaces, dots, case, etc.
    return re.sub(r"[\x00/\\]+", "-", label).strip()


def _label_from_selectors(args) -> str:
    """Derive the output-filename label from selectors by priority order."""
    if args.label:
        return _sanitize_label(args.label)  # verbatim per spec §5.6
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


def _normalize_to_date(val):
    """Parse created: into a date regardless of whether it's a string YYYY-MM-DD,
    an ISO datetime string, or a YAML-parsed datetime/date object."""
    if val is None:
        return None
    # YAML might load a date or datetime object directly
    try:
        from datetime import date as _date
        if isinstance(val, _date):
            return val if not isinstance(val, datetime) else val.date()
        if isinstance(val, datetime):
            return val.date()
    except Exception:
        pass
    s = str(val).strip()
    # Try plain YYYY-MM-DD first
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.date()
        except ValueError:
            continue
    # Last resort: try fromisoformat (Python 3.11+ handles most ISO variants)
    try:
        return datetime.fromisoformat(s.rstrip("Z")).date()
    except Exception:
        return None


def _matches(fm: dict, args) -> bool:
    tags = fm.get("tags") or []
    if args.project and f"project/{args.project}" not in tags:
        return False
    if args.field and f"field/{args.field}" not in tags:
        return False
    if args.tag and args.tag not in tags:
        return False
    if args.since:
        created_val = fm.get("created")
        created = _normalize_to_date(created_val)
        if created is None:
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
    any_selector = any(
        getattr(args, a) for a in ("project", "field", "tag", "query", "keys", "since")
    )
    if not any_selector:
        print("Error: at least one of --project, --field, --tag, --query, --keys, --since is required.", file=sys.stderr)
        return 2

    wr = Path(args.wiki_root)
    papers_dir = wr / "wiki" / "papers"
    bib_dir = wr / "raw" / "bib"

    # Build the candidate set:
    # - If --keys: the explicit list
    # - Else: all paper pages in wiki/papers/
    # Then filter by _matches() (which handles project/field/tag/since filters).
    if args.keys:
        candidate_ids = [k.strip() for k in args.keys.split(",") if k.strip()]
        # Deduplicate while preserving order
        seen_order: list[str] = []
        for k in candidate_ids:
            if k not in seen_order:
                seen_order.append(k)
        candidate_ids = seen_order
    else:
        if not papers_dir.is_dir():
            print("No papers directory found.")
            return 1
        candidate_ids = [md.stem for md in sorted(papers_dir.glob("*.md"))]

    selected: list[tuple[str, Path]] = []
    for pid in candidate_ids:
        paper_path = papers_dir / f"{pid}.md"
        if not paper_path.exists():
            continue  # Silent skip for --keys ids that don't exist
        try:
            fm, _ = read_frontmatter(str(paper_path))
        except Exception:
            continue
        if not _matches(fm, args):
            continue
        resolved_pid = fm.get("paper-id") or pid
        selected.append((resolved_pid, bib_dir / f"{resolved_pid}.bib"))

    if not selected:
        print("No papers match the selector(s).")
        return 1

    incomplete: list[tuple[str, str]] = []
    content_parts: list[str] = []
    exported_ids: list[str] = []
    for pid, bib_path in selected:
        if not bib_path.exists():
            incomplete.append((pid, "missing .bib file"))
            continue
        body = bib_path.read_text(errors="replace")  # tolerate non-UTF-8
        if re.search(r"bib-incomplete:\s*true", body, re.IGNORECASE):
            incomplete.append((pid, "bib-incomplete flag"))
        content_parts.append(f"% {pid}\n{body.strip()}\n")
        exported_ids.append(pid)

    if not exported_ids:
        print(f"No usable BibTeX entries found for {len(selected)} selected papers.")
        if incomplete:
            print("Issues:")
            for pid, reason in incomplete:
                print(f"  - {pid}: {reason}")
        return 1

    label = _label_from_selectors(args)
    out_dir = wr / "outputs" / "bib"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date.today().isoformat()}-{label}.bib"
    out_path.write_text("\n".join(content_parts) + "\n")

    print(f"Exported {len(exported_ids)} papers to {out_path}")
    if incomplete:
        print(f"{len(incomplete)} papers have bib-incomplete issues:")
        for pid, reason in incomplete:
            print(f"  - {pid}: {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(export())
