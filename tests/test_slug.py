"""Tests for §3.5 slug generation rules."""
from academic_wiki_lib.slug import make_slug


def test_basic_title():
    assert make_slug("Rate-Splitting Multiple Access") == "rate-splitting-multiple-access"


def test_stop_word_dropped_only_if_remaining_is_multi_word():
    assert make_slug("The Attention Mechanism") == "attention-mechanism"
    assert make_slug("The") == "the"  # single word, keep


def test_ascii_folding():
    assert make_slug("α-divergence") == "a-divergence"
    assert make_slug("García-Luna") == "garcia-luna"


def test_punctuation_stripped():
    assert make_slug("O(n²) complexity of self-attention") == "on2-complexity-of-self-attention"


def test_truncation_at_60_chars():
    long = "a-" * 50  # 100 chars
    assert len(make_slug(long)) <= 60


def test_collapses_multiple_hyphens():
    assert make_slug("foo---bar") == "foo-bar"


def test_strips_leading_trailing_hyphens():
    assert make_slug("--foo-bar--") == "foo-bar"


def test_lowercases():
    assert make_slug("K-Means") == "k-means"


def test_empty_input_raises():
    import pytest
    with pytest.raises(ValueError):
        make_slug("")
    with pytest.raises(ValueError):
        make_slug("   ")
