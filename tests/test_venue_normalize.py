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


def test_year_boundaries():
    # 1899 and 2100 are outside the 1900-2099 window — kept verbatim.
    assert normalize_venue("GLOBECOM 1899")[1] == "globecom-1899"
    assert normalize_venue("ICASSP 2100")[1] == "icassp-2100"
    # 1900 and 2099 are inclusive lower/upper bounds — stripped.
    assert normalize_venue("CONF 1900")[1] == "conf"
    assert normalize_venue("CONF 2099")[1] == "conf"


def test_non_year_digits_preserved():
    # 4-digit runs that aren't (19|20)NN don't match the year regex.
    # 2-3 digit runs and embedded digits like "5G", "802.11" are left alone.
    assert normalize_venue("5G NR Workshop")[1] == "5g-nr-workshop"
    assert normalize_venue("802.11 Standards Forum")[1] == "802-11-standards-forum"
    assert normalize_venue("4G LTE Forum")[1] == "4g-lte-forum"


def test_year_glued_to_token():
    assert normalize_venue("VTC2022-Fall")[1] == "vtc-fall"
    assert normalize_venue("WCNC2023")[1] == "wcnc"


def test_ordinal_anywhere():
    # Ordinals strip even when not at the start; remaining text drives the slug.
    assert normalize_venue("21st Century Networking")[1] == "century-networking"
    assert normalize_venue("Section 1st on Optics")[1] == "section-on-optics"
    # Ordinal embedded in a hyphenated token: "3rd-party" → "-party".
    assert normalize_venue("3rd-party tool")[1] == "party-tool"
    # Sole non-ordinal word survives.
    assert normalize_venue("Section 1st")[1] == "section"


def test_paren_and_bracket_unwrap():
    # All three syntaxes produce the same canonical and slug after year strip.
    a = normalize_venue("Conference on X (AINA 2005)")
    b = normalize_venue("Conference on X [AINA 2005]")
    c = normalize_venue("Conference on X AINA (2005)")
    assert a == b == c
    assert a[1] == "conference-on-x-aina"


def test_empty_input_raises():
    with pytest.raises(ValueError):
        normalize_venue("")
    with pytest.raises(ValueError):
        normalize_venue("   ")
    with pytest.raises(ValueError):
        normalize_venue(None)


def test_only_year_and_ordinal_raises():
    # Nothing left after stripping → ValueError.
    with pytest.raises(ValueError):
        normalize_venue("2024 21st")
    with pytest.raises(ValueError):
        normalize_venue("2022")


def test_trailing_leading_commas_stripped():
    canonical, slug = normalize_venue(",IEEE Transactions,")
    assert canonical == "IEEE Transactions"
    assert slug == "ieee-transactions"
