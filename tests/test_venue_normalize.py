"""Tests for venue normalization per spec §2026-05-10."""
import pytest

from academic_wiki_lib.venue_normalize import normalize_venue


# (raw_input, expected_canonical_name, expected_slug)
WORKED_EXAMPLES = [
    (
        "2022 56th Asilomar Conference on Signals, Systems, and Computers",
        "Asilomar Conference on Signals, Systems, and Computers",
        "asilomar-conference-on-signals-systems-and-computers",
    ),
    (
        "19th International Conference on Advanced Information Networking and Applications (AINA 2005)",
        "International Conference on Advanced Information Networking and Applications AINA",
        "international-conference-on-advanced-information-networking-and-applications-aina",
    ),
    (
        "2022 IEEE 96th Vehicular Technology Conference (VTC2022-Fall)",
        "IEEE Vehicular Technology Conference VTC-Fall",
        "ieee-vehicular-technology-conference-vtc-fall",
    ),
    (
        "2024 IEEE Globecom Workshops (GC Wkshps)",
        "IEEE Globecom Workshops GC Wkshps",
        "ieee-globecom-workshops-gc-wkshps",
    ),
    (
        "IEEE Transactions on Communications",
        "IEEE Transactions on Communications",
        "ieee-transactions-on-communications",
    ),
    (
        "arXiv preprint",
        "arXiv preprint",
        "arxiv-preprint",
    ),
]


@pytest.mark.parametrize("raw,canonical,slug", WORKED_EXAMPLES)
def test_normalize_venue_worked_examples(raw, canonical, slug):
    got_canonical, got_slug = normalize_venue(raw)
    assert got_canonical == canonical, f"canonical mismatch for {raw!r}"
    assert got_slug == slug, f"slug mismatch for {raw!r}"
