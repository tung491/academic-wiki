"""Pure plan-building functions for venue migration per spec 2026-05-10.

The CLI (scripts/migrate-venues.py) consumes these to produce the dry-run
report and to drive --apply. Keeping the logic here makes it unit-testable
without subprocess.
"""
from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .frontmatter import read_frontmatter
from .venue_normalize import normalize_venue


def _to_str_list(val) -> list[str]:
    """Coerce a YAML field to list[str].

    Real venue pages may have `papers: pX` (a bare scalar) instead of the
    proper `papers: [pX]`. `list("pX")` would silently produce `['p', 'X']`,
    so we treat scalars as single-element lists.
    """
    if val is None:
        return []
    if isinstance(val, list):
        return [str(v) for v in val]
    return [str(val)]


@dataclass
class VenuePage:
    """An existing venue page on disk."""
    slug: str
    path: Path
    name: str
    venue_type: str
    created: str
    papers: list[str]
    tags: list[str]
    body: str


@dataclass
class Group:
    """A migration group: one or more existing pages that all map to new_slug."""
    new_slug: str
    new_canonical_name: str
    new_venue_type: str
    new_created: str
    members: list[VenuePage]
    new_papers: list[str]
    new_tags: list[str]

    @property
    def is_merge(self) -> bool:
        return len(self.members) > 1


@dataclass
class Plan:
    """Migration plan. groups excludes no-op groups."""
    groups: list[Group] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _scan_venue_pages(wiki_root: Path) -> tuple[list[VenuePage], list[str]]:
    """Return (parsed pages, skipped reasons)."""
    venues_dir = wiki_root / "wiki" / "venues"
    pages: list[VenuePage] = []
    skipped: list[str] = []
    if not venues_dir.is_dir():
        return pages, skipped
    for md in sorted(venues_dir.glob("*.md")):
        try:
            fm, body = read_frontmatter(md)
        except Exception as e:
            skipped.append(f"{md.name}: parse error ({e})")
            continue
        if not isinstance(fm, dict) or fm.get("type") != "venue":
            skipped.append(f"{md.name}: frontmatter type is not 'venue'")
            continue
        name = fm.get("name")
        if not isinstance(name, str) or not name.strip():
            skipped.append(f"{md.name}: missing or empty 'name:' field")
            continue
        pages.append(VenuePage(
            slug=fm.get("slug") or md.stem,
            path=md,
            name=name,
            venue_type=fm.get("venue-type", "journal"),
            created=str(fm.get("created", ""))[:10],
            papers=_to_str_list(fm.get("papers")),
            tags=_to_str_list(fm.get("tags")),
            body=body,
        ))
    return pages, skipped


def _resolve_venue_type(members: list[VenuePage]) -> str:
    """Most common venue-type; ties broken by member with most papers; if still
    tied, the lex-smallest old slug wins."""
    counts = Counter(m.venue_type for m in members)
    top = counts.most_common()
    if not top:
        return "journal"
    if len(top) == 1 or top[0][1] > top[1][1]:
        return top[0][0]
    # Tie at the top.
    tied_types = [t for t, c in top if c == top[0][1]]
    # Pick the type used by the member with the most papers; tie-break by lex-smallest slug.
    candidates = [m for m in members if m.venue_type in tied_types]
    candidates.sort(key=lambda m: (-len(m.papers), m.slug))
    return candidates[0].venue_type


def _resolve_created(members: list[VenuePage]) -> str:
    valid = sorted(m.created for m in members if m.created)
    return valid[0] if valid else ""


def compute_plan(wiki_root: str | os.PathLike) -> Plan:
    """Build the migration plan from the on-disk venue pages.

    Reads `<wiki_root>/wiki/venues/*.md`. Excludes no-op groups
    (a single page whose existing slug already equals its post-
    normalization slug).
    """
    root = Path(os.fspath(wiki_root))
    pages, skipped = _scan_venue_pages(root)

    # Group by (new_canonical_name, new_slug) computed from each page's name.
    grouped: dict[str, list[tuple[VenuePage, str]]] = {}  # new_slug -> [(page, canonical), ...]
    for page in pages:
        try:
            canonical, new_slug = normalize_venue(page.name)
        except ValueError as e:
            skipped.append(f"{page.path.name}: {e}")
            continue
        grouped.setdefault(new_slug, []).append((page, canonical))

    groups: list[Group] = []
    for new_slug, entries in sorted(grouped.items()):
        members = [e[0] for e in entries]
        # Pick the longest canonical_name as the representative human form (in
        # practice they should all be equal, but defensively prefer the most
        # descriptive variant if not).
        new_canonical_name = max((e[1] for e in entries), key=len)
        # No-op detection: single member whose existing slug already equals new_slug.
        if len(members) == 1 and members[0].slug == new_slug:
            continue
        all_papers = sorted({p for m in members for p in m.papers})
        all_tags = sorted({t for m in members for t in m.tags})
        groups.append(Group(
            new_slug=new_slug,
            new_canonical_name=new_canonical_name,
            new_venue_type=_resolve_venue_type(members),
            new_created=_resolve_created(members),
            members=members,
            new_papers=all_papers,
            new_tags=all_tags,
        ))

    return Plan(groups=groups, skipped=skipped)
