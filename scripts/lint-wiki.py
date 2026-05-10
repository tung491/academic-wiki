#!/usr/bin/env python3
"""Deterministic wiki lint per spec §5.5.

Reports issues as lines starting with issue tags like DEAD_LINK, ORPHAN,
MISSING_FIELD_TAG, STALE, MISSING_SECTION, INVALID_CITES, MISSING_BIBTEX,
INDEX_DRIFT, VERSION_DRIFT, EXTRACT_MISSING, EXTRACT_FAILED, CONTRADICTION,
ALIAS_LINK, VENUE_NEAR_DUPLICATE.

Exit code 0 always (lint reports, not gates).
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

# Make the lib importable when running as a script
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

from academic_wiki_lib.frontmatter import read_frontmatter
from academic_wiki_lib.venue_normalize import near_duplicate_pairs

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

_REQUIRED_FIELDS = {
    "paper": ["paper-id", "type", "status", "created", "updated", "title",
              "authors", "year", "identifiers", "bib-file", "extract", "tags"],
    "concept": ["type", "status", "created", "updated", "sources", "tags"],
    "method": ["type", "status", "created", "updated", "sources", "tags"],
    "open-problem": ["type", "status", "created", "updated", "sources", "tags"],
    "claim": ["type", "status", "created", "updated", "sources", "tags"],
    "result": ["type", "status", "created", "updated", "sources", "tags"],
    "author": ["type", "name", "slug", "created", "updated", "papers", "tags"],
    "venue": ["type", "name", "slug", "venue-type", "created", "updated", "papers", "tags"],
    "query-output": ["type", "question", "status", "created", "updated", "sources", "tags"],
}


def _scan_wiki_files(wiki_root: Path) -> dict[str, tuple[Path, dict, str]]:
    """Return {slug: (path, frontmatter, body)} for every .md under wiki/."""
    out = {}
    wdir = wiki_root / "wiki"
    if not wdir.is_dir():
        return out
    for md in wdir.rglob("*.md"):
        try:
            fm, body = read_frontmatter(str(md))
        except Exception as e:
            print(f"PARSE_ERROR: {md.relative_to(wiki_root)} — {e}")
            continue
        out[md.stem] = (md, fm, body)
    return out


def _build_alias_map(files: dict) -> dict[str, str]:
    """Return {alias: canonical_slug} for every aliases: entry across pages."""
    out = {}
    for slug, (_, fm, _) in files.items():
        for a in fm.get("aliases") or []:
            out[str(a)] = slug
    return out


def _count_counter_args(body: str) -> int:
    return len(re.findall(r"(?im)^##\s+counter.?arguments", body))


def _parse_date(s) -> date | None:
    try:
        return datetime.strptime(str(s), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _check_venue_near_duplicates(files: dict[str, tuple]) -> list[str]:
    """Flag pairs of venue page slugs that look like spelling variants of each other.

    Returns a list of issue lines; empty if no pairs.
    """
    venue_slugs = []
    for slug, (_, fm, _) in files.items():
        if fm.get("type") == "venue":
            venue_slugs.append(slug)
    pairs = near_duplicate_pairs(venue_slugs)
    issues = []
    for a, b, sim in pairs:
        a_tail = a.rsplit("-", 1)[-1] if "-" in a else a
        b_tail = b.rsplit("-", 1)[-1] if "-" in b else b
        suffix_note = f"; matching acronym suffix {a_tail!r}" if a_tail == b_tail else ""
        issues.append(
            f"VENUE_NEAR_DUPLICATE: {a!r} ↔ {b!r} (similarity {sim:.2f}{suffix_note})"
        )
    return issues


def lint(wiki_root: str) -> int:
    wr = Path(wiki_root)
    files = _scan_wiki_files(wr)
    alias_to_canonical = _build_alias_map(files)
    issues: list[str] = []
    inbound: dict[str, set[str]] = {slug: set() for slug in files}

    # --- Dead-link / alias resolution ---
    for slug, (path, _, body) in files.items():
        rel = str(path.relative_to(wr))
        for lineno, line in enumerate(body.splitlines(), start=1):
            for m in WIKILINK_RE.finditer(line):
                t = m.group(1).strip()
                if t in files:
                    inbound[t].add(slug)
                elif t in alias_to_canonical:
                    canonical = alias_to_canonical[t]
                    issues.append(
                        f"ALIAS_LINK: [[{t}]] in {rel}:{lineno} resolves to "
                        f"[[{canonical}]] — consider rewriting"
                    )
                    inbound[canonical].add(slug)
                else:
                    issues.append(f"DEAD_LINK: [[{t}]] in {rel}:{lineno}")

    skip_names = {"index", "log"}
    today = date.today()

    # --- Per-page checks ---
    for slug, (path, fm, body) in files.items():
        if slug in skip_names:
            continue
        rel = str(path.relative_to(wr))
        t = fm.get("type")
        required = _REQUIRED_FIELDS.get(t) or []
        for field_name in required:
            if field_name not in fm or fm.get(field_name) is None:
                issues.append(f"MISSING_FIELD: {rel} lacks required field '{field_name}' for type '{t}'")
        tags = fm.get("tags") or []

        # Orphan
        if not inbound.get(slug):
            issues.append(f"ORPHAN: {rel} has no inbound links")

        # Missing field/* tag
        if t in {"paper", "concept", "method", "open-problem", "claim", "result"}:
            if not any(isinstance(x, str) and x.startswith("field/") for x in tags):
                issues.append(f"MISSING_FIELD_TAG: {rel}")

        # Stale
        updated = _parse_date(fm.get("updated"))
        if updated:
            age = (today - updated).days
            if fm.get("status") == "stale" and age > 90:
                issues.append(f"STALE: {rel} (status=stale, age={age}d)")
            if t in {"concept", "method"} and age > 180:
                issues.append(f"STALE: {rel} ({t} untouched for {age}d)")

        # Counter-Arguments and Gaps on concept/method
        if t in {"concept", "method"} and _count_counter_args(body) == 0:
            issues.append(f"MISSING_SECTION: {rel} lacks 'Counter-Arguments and Gaps'")

        # Contradictions
        for m in re.finditer(r">\s*\[!WARNING\]\s*Contradiction", body, re.IGNORECASE):
            issues.append(f"CONTRADICTION: {rel} has [!WARNING] callout")

        # Paper-specific
        if t == "paper":
            # Invalid cites
            for c in fm.get("cites") or []:
                if c not in files:
                    issues.append(f"INVALID_CITES: {rel} cites unknown paper-id [{c}]")

            # Missing bibtex
            bib_file = fm.get("bib-file")
            if bib_file:
                bib_path = wr / bib_file
                if not bib_path.exists():
                    issues.append(f"MISSING_BIBTEX: {rel} (expected {bib_file})")
                else:
                    bib_content = bib_path.read_text(errors="ignore")
                    if re.search(r"bib-incomplete:\s*true", bib_content, re.IGNORECASE):
                        issues.append(f"MISSING_BIBTEX: {rel} (bib-incomplete flag)")

            # Paper-id based checks
            pid = fm.get("paper-id") or slug
            extract_path = wr / "raw" / "extracts" / f"{pid}.md"
            if not extract_path.exists():
                issues.append(f"EXTRACT_MISSING: {rel} (expected raw/extracts/{pid}.md)")
            else:
                try:
                    efm, _ = read_frontmatter(str(extract_path))
                    if efm.get("extract-status") == "failed":
                        issues.append(f"EXTRACT_FAILED: {rel} (extract-status: failed in {pid}.md)")
                except Exception as e:
                    issues.append(f"EXTRACT_PARSE_ERROR: {rel} — {e}")

            # Version drift
            versions_yml = wr / "raw" / "extracts" / f"{pid}.versions.yml"
            if versions_yml.exists():
                try:
                    import yaml
                    data = yaml.safe_load(versions_yml.read_text()) or {}
                    vs = data.get("versions") or []
                    if vs:
                        latest = vs[-1].get("version")
                        current = (fm.get("identifiers") or {}).get("arxiv-version")
                        if latest and current and latest != current:
                            issues.append(
                                f"VERSION_DRIFT: {rel} identifiers.arxiv-version={current} "
                                f"but newer {latest} in {pid}.versions.yml"
                            )
                except Exception:
                    pass

    # --- Index drift ---
    index_path = wr / "wiki" / "index.md"
    if index_path.exists():
        idx_body = index_path.read_text()
        # Collect wikilink targets in index.md
        linked = {t.strip() for t in WIKILINK_RE.findall(idx_body)}
        for target in linked:
            if target not in files and target not in alias_to_canonical:
                issues.append(f"INDEX_DRIFT: index.md references [[{target}]] which doesn't exist")
        # Reverse: files that exist but are not linked in index.md
        for slug, (path, _, _) in files.items():
            if slug in skip_names:
                continue
            if slug not in linked:
                issues.append(f"INDEX_DRIFT: {slug} exists at {path.relative_to(wr)} but is not in index.md")

    # --- Venue near-duplicate check ---
    issues.extend(_check_venue_near_duplicates(files))

    # --- Report ---
    if not issues:
        print("OK: No issues found")
        return 0
    for issue in sorted(issues):
        print(issue)
    print(f"\nTotal: {len(issues)} issue(s)")
    return 0  # lint reports but doesn't gate


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <wiki-root>", file=sys.stderr)
        sys.exit(2)
    sys.exit(lint(sys.argv[1]))
