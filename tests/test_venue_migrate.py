"""Tests for venue_migrate.compute_plan — pure plan-building logic."""
from pathlib import Path

import pytest

from academic_wiki_lib.frontmatter import write_frontmatter
from academic_wiki_lib.venue_migrate import compute_plan


def _venue(tmp_wiki, slug, name, papers=None, tags=None, venue_type="conference",
           created="2026-04-01"):
    fm = {
        "type": "venue",
        "name": name,
        "slug": slug,
        "venue-type": venue_type,
        "created": created,
        "updated": created,
        "papers": list(papers or []),
        "tags": list(tags or []),
    }
    write_frontmatter(str(tmp_wiki / "wiki/venues" / f"{slug}.md"), fm, "Body of " + slug + "\n")


def test_no_op_group_skipped(tmp_wiki):
    """A single canonical-slug venue is a no-op (skipped from the plan)."""
    _venue(tmp_wiki, "ieee-transactions-on-communications",
           "IEEE Transactions on Communications", papers=["p1"])
    plan = compute_plan(tmp_wiki)
    assert plan.groups == []  # no rename needed, no merge needed


def test_single_page_rename(tmp_wiki):
    """An existing non-canonical-slug venue produces a rename group."""
    _venue(tmp_wiki, "2022-56th-asilomar-conference-on-signals-systems-and-computers",
           "2022 56th Asilomar Conference on Signals, Systems, and Computers",
           papers=["paperA"])
    plan = compute_plan(tmp_wiki)
    assert len(plan.groups) == 1
    g = plan.groups[0]
    assert g.new_slug == "asilomar-conference-on-signals-systems-and-computers"
    assert g.new_canonical_name == "Asilomar Conference on Signals, Systems, and Computers"
    assert len(g.members) == 1
    assert g.members[0].slug == "2022-56th-asilomar-conference-on-signals-systems-and-computers"
    assert g.new_papers == ["paperA"]
    assert g.is_merge is False


def test_multi_page_merge(tmp_wiki):
    """Multiple venues normalizing to the same slug form a merge group."""
    _venue(tmp_wiki, "2022-56th-asilomar-conference-on-signals-systems-and-computers",
           "2022 56th Asilomar Conference on Signals, Systems, and Computers",
           papers=["pA", "pB"], tags=["field/wireless-comms"], created="2024-01-01")
    _venue(tmp_wiki, "2023-57th-asilomar-conference-on-signals-systems-and-computers",
           "2023 57th Asilomar Conference on Signals, Systems, and Computers",
           papers=["pC"], tags=["field/wireless-comms", "field/signal-processing"],
           created="2024-06-15")
    plan = compute_plan(tmp_wiki)
    assert len(plan.groups) == 1
    g = plan.groups[0]
    assert g.new_slug == "asilomar-conference-on-signals-systems-and-computers"
    assert g.is_merge is True
    assert len(g.members) == 2
    # Papers union, deduped, lex-sorted
    assert g.new_papers == ["pA", "pB", "pC"]
    # Tags union, deduped, lex-sorted
    assert g.new_tags == ["field/signal-processing", "field/wireless-comms"]


def test_merge_with_existing_canonical(tmp_wiki):
    """A canonical-slug page coexisting with non-canonical members is included
    as a merge member (not skipped)."""
    _venue(tmp_wiki, "asilomar-conference-on-signals-systems-and-computers",
           "Asilomar Conference on Signals, Systems, and Computers",
           papers=["pA"])
    _venue(tmp_wiki, "2022-56th-asilomar-conference-on-signals-systems-and-computers",
           "2022 56th Asilomar Conference on Signals, Systems, and Computers",
           papers=["pB"])
    plan = compute_plan(tmp_wiki)
    assert len(plan.groups) == 1
    g = plan.groups[0]
    assert g.is_merge is True
    assert len(g.members) == 2
    assert g.new_papers == ["pA", "pB"]


def test_venue_type_majority_with_paper_count_tiebreak(tmp_wiki):
    """venue-type unanimous → use it; otherwise majority; ties broken by papers count."""
    _venue(tmp_wiki, "2022-fooconf", "2022 FooConf", papers=["p1"], venue_type="conference")
    _venue(tmp_wiki, "2023-fooconf", "2023 FooConf", papers=["p2"], venue_type="conference")
    _venue(tmp_wiki, "2024-fooconf", "2024 FooConf", papers=["p3"], venue_type="journal")
    plan = compute_plan(tmp_wiki)
    g = plan.groups[0]
    assert g.new_venue_type == "conference"  # 2-vs-1 majority


def test_venue_type_tied_count_broken_by_paper_count(tmp_wiki):
    """1 conference vs 1 journal → the one with more papers wins."""
    _venue(tmp_wiki, "2022-fooconf", "2022 FooConf",
           papers=["p1", "p2"], venue_type="conference")
    _venue(tmp_wiki, "2023-fooconf", "2023 FooConf",
           papers=["p3"], venue_type="journal")
    plan = compute_plan(tmp_wiki)
    assert plan.groups[0].new_venue_type == "conference"


def test_venue_type_tied_count_and_papers_broken_by_lex_slug(tmp_wiki):
    """Both ties broken by lex-smallest old slug."""
    _venue(tmp_wiki, "2022-fooconf", "2022 FooConf",
           papers=["p1"], venue_type="journal")
    _venue(tmp_wiki, "2023-fooconf", "2023 FooConf",
           papers=["p2"], venue_type="conference")
    plan = compute_plan(tmp_wiki)
    # 2022-fooconf is lex-smaller; its venue_type is journal → wins.
    assert plan.groups[0].new_venue_type == "journal"


def test_papers_field_tolerates_scalar_yaml(tmp_wiki):
    """A venue page with 'papers: pX' (bare scalar) is read as ['pX'], not ['p', 'X']."""
    fm = {
        "type": "venue",
        "name": "2022 FooConf",
        "slug": "2022-fooconf",
        "venue-type": "conference",
        "created": "2024-01-01",
        "updated": "2024-01-01",
        "papers": "p1",  # scalar, not list
        "tags": "field/x",  # scalar, not list
    }
    write_frontmatter(str(tmp_wiki / "wiki/venues/2022-fooconf.md"), fm, "Body\n")
    plan = compute_plan(tmp_wiki)
    g = plan.groups[0]
    assert g.new_papers == ["p1"]
    assert g.new_tags == ["field/x"]


def test_created_earliest_wins(tmp_wiki):
    """The merged page's created: is the earliest across members."""
    _venue(tmp_wiki, "2022-fooconf", "2022 FooConf", papers=["p1"], created="2025-01-01")
    _venue(tmp_wiki, "2023-fooconf", "2023 FooConf", papers=["p2"], created="2024-06-15")
    _venue(tmp_wiki, "2024-fooconf", "2024 FooConf", papers=["p3"], created="2024-01-10")
    plan = compute_plan(tmp_wiki)
    g = plan.groups[0]
    assert g.new_created == "2024-01-10"


def test_unparseable_frontmatter_listed_separately(tmp_wiki):
    """Pages with unparseable frontmatter are reported in plan.skipped."""
    bad = tmp_wiki / "wiki/venues/broken.md"
    bad.write_text("---\nthis: is: not: valid yaml: [\n---\nbody\n")
    plan = compute_plan(tmp_wiki)
    assert any("broken.md" in s for s in plan.skipped)
