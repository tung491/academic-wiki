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


@dataclass
class PaperRewrite:
    """A paper page that needs its venue: field and venue/* tag rewritten.

    When `venue:` and a `venue/*` tag disagree on the old slug, the `venue:`
    field wins as the authoritative source and is what `old_slug` records.
    """
    paper_id: str
    path: Path
    old_slug: str
    new_slug: str


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


def render_report(plan: Plan, rewrites: list[PaperRewrite], today: str) -> str:
    """Render the dry-run / apply report as markdown."""
    renames = [g for g in plan.groups if not g.is_merge]
    merges = [g for g in plan.groups if g.is_merge]
    n_rewrites = len(rewrites)

    lines: list[str] = []
    lines.append(f"# Venue Migration Plan — {today}\n")
    lines.append("## Summary")
    lines.append(f"- {len(plan.groups) + len(plan.skipped)} venue pages considered "
                 f"({len(plan.skipped)} skipped, {len(plan.groups)} in plan)")
    lines.append(f"- {len(renames)} renamed (single-page groups)")
    if merges:
        merged_in = sum(len(g.members) for g in merges)
        lines.append(f"- {merged_in} pages merge into {len(merges)} canonical pages")
    lines.append(f"- {n_rewrites} paper pages need `venue:` and `venue/*` tag rewrites")
    lines.append("")

    if renames:
        lines.append("## Renames (single-page groups)")
        for g in renames:
            old = g.members[0].slug
            lines.append(f"- `{old}` → `{g.new_slug}`")
        lines.append("")

    if merges:
        lines.append("## Merges (multi-page groups)")
        for g in merges:
            lines.append(f"### `{g.new_slug}` ← merges {len(g.members)} pages")
            lines.append("Sources:")
            for m in g.members:
                lines.append(f"- `{m.slug}` ({len(m.papers)} papers)")
            lines.append(f"New `papers:` list (union, deduped, {len(g.new_papers)} entries): {g.new_papers}")
            lines.append(f"New `tags:` list (union, {len(g.new_tags)} entries): {g.new_tags}")
            lines.append(f"New `name:` \"{g.new_canonical_name}\"")
            lines.append(f"New `venue-type:` {g.new_venue_type}")
            lines.append(f"New `created:` {g.new_created}")
            lines.append("")

    if rewrites:
        lines.append("## Paper-page rewrites")
        for r in rewrites:
            lines.append(f"- `{r.paper_id}.md`: `venue: {r.old_slug}` → `{r.new_slug}`; "
                         f"tag `venue/{r.old_slug}` → `venue/{r.new_slug}`")
        lines.append("")

    if plan.skipped:
        lines.append("## Skipped (could not parse frontmatter)")
        for s in plan.skipped:
            lines.append(f"- {s}")
        lines.append("")

    return "\n".join(lines)


def collect_paper_rewrites(wiki_root: str | os.PathLike, plan: Plan) -> list[PaperRewrite]:
    """Find every paper page whose venue: or venue/* tag references an old
    slug that the plan will replace."""
    root = Path(os.fspath(wiki_root))

    # Build map: old_slug -> new_slug (only for slugs that actually change)
    old_to_new: dict[str, str] = {}
    for g in plan.groups:
        for m in g.members:
            if m.slug != g.new_slug:
                old_to_new[m.slug] = g.new_slug

    if not old_to_new:
        return []

    papers_dir = root / "wiki" / "papers"
    rewrites: list[PaperRewrite] = []
    if not papers_dir.is_dir():
        return rewrites
    for md in sorted(papers_dir.glob("*.md")):
        try:
            fm, _ = read_frontmatter(md)
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        venue = fm.get("venue")
        tags = fm.get("tags") or []
        old_slug = None
        if isinstance(venue, str) and venue in old_to_new:
            old_slug = venue
        else:
            for t in tags:
                if isinstance(t, str) and t.startswith("venue/"):
                    candidate = t[len("venue/"):]
                    if candidate in old_to_new:
                        old_slug = candidate
                        break
        if old_slug is None:
            continue
        rewrites.append(PaperRewrite(
            paper_id=fm.get("paper-id") or md.stem,
            path=md,
            old_slug=old_slug,
            new_slug=old_to_new[old_slug],
        ))
    return rewrites
