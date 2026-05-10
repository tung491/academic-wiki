"""Tests for near_duplicate_pairs per spec 2026-05-10."""
from academic_wiki_lib.venue_normalize import near_duplicate_pairs


def test_variant_spelling_pair_flagged():
    slugs = [
        "ieee-cic-international-conference-on-communications-in-china-iccc",
        "ieeecic-international-conference-on-communications-in-china-iccc",
        "ieee-international-conference-on-communications",
    ]
    pairs = near_duplicate_pairs(slugs)
    flagged_pairs = {(a, b) for a, b, _ in pairs}
    assert (
        "ieee-cic-international-conference-on-communications-in-china-iccc",
        "ieeecic-international-conference-on-communications-in-china-iccc",
    ) in flagged_pairs


def test_distinct_conferences_not_flagged():
    slugs = [
        "ieee-international-conference-on-communications",
        "ieee-international-conference-on-image-processing",
    ]
    assert near_duplicate_pairs(slugs) == []


def test_acronym_suffix_reinforcement():
    # Two slugs that share trailing acronym `iccc` and have similarity
    # below 0.92 but ≥ 0.85 should be flagged.
    slugs = [
        "international-conference-on-communications-in-china-iccc",
        "ieee-international-conf-communications-china-iccc",
    ]
    pairs = near_duplicate_pairs(slugs)
    assert len(pairs) == 1
    a, b, _ = pairs[0]
    assert a < b
    assert a.endswith("iccc") and b.endswith("iccc")


def test_symmetry_appears_once_lex_sorted():
    slugs = ["zzz-conf", "aaa-conf"]  # both end in -conf, similarity high enough
    pairs = near_duplicate_pairs(slugs, threshold=0.5)
    # Each pair should appear once with a < b
    seen = set()
    for a, b, _ in pairs:
        assert a < b
        assert (a, b) not in seen
        seen.add((a, b))


def test_empty_and_single_input():
    assert near_duplicate_pairs([]) == []
    assert near_duplicate_pairs(["only-one"]) == []
