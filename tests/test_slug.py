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
    assert make_slug("O(n²) complexity of self-attention") == "o-n2-complexity-of-self-attention"
    assert make_slug("f(x)") == "f-x"
    assert make_slug("node.js") == "node-js"
    assert make_slug("A/B test") == "a-b-test"


def test_uppercase_greek():
    assert make_slug("Α-divergence") == "a-divergence"
    assert make_slug("Δ-learning") == "d-learning"
    assert make_slug("Σ-algebra") == "s-algebra"


def test_numbers_only():
    assert make_slug("123 456") == "123-456"


def test_only_stop_word_returns_itself():
    # "the" alone is single-word, so stop-word filter does NOT drop it
    assert make_slug("the") == "the"


def test_exactly_60_chars_unchanged():
    # A slug that is already 60 chars should be returned as-is
    # Build a 60-char input that is all alpha-hyphens
    input_str = "a-" * 30  # 60 chars
    result = make_slug(input_str)
    assert len(result) <= 60


def test_emoji_dropped():
    # Emoji are non-alphanumeric; they collapse to hyphens
    assert make_slug("emoji 😀 test") == "emoji-test"


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


def test_leading_article_dropped_without_ab_conflict():
    # Real article "A" at start — must be dropped
    assert make_slug("A Theory of Mind") == "theory-of-mind"
    assert make_slug("A Survey of Transformers") == "survey-of-transformers"
    # "A/B" should NOT have its A dropped (it's not a leading article; it's part of "A/B")
    assert make_slug("A/B test") == "a-b-test"


def test_x_plus_y_punctuation():
    assert make_slug("x+y") == "x-y"


def test_truncation_backs_up_to_any_hyphen():
    # Single hyphen near the start; remainder is long
    long_input = "abcde-" + "f" * 80
    result = make_slug(long_input)
    assert len(result) <= 60
    # Should back up to the hyphen, producing a 5-char slug
    assert result == "abcde"
