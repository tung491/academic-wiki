from unittest.mock import MagicMock, patch

import pytest

from academic_wiki_mcp.bibtex import build_from_metadata, parse_first_entry, rewrite_citation_key
from academic_wiki_mcp.s2_client import get_paper_by_doi
from academic_wiki_mcp.tools.bibtex import doi_to_bibtex


def test_get_paper_by_doi_returns_normalized_paper():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "paperId": "abc",
        "title": "Attention Is All You Need",
        "authors": [{"name": "Ashish Vaswani"}, {"name": "Noam Shazeer"}],
        "year": 2017,
        "venue": "NeurIPS",
        "abstract": "We propose...",
        "externalIds": {"DOI": "10.48550/arXiv.1706.03762"},
        "citationCount": 100000,
    }
    with patch("requests.get", return_value=mock_resp):
        result = get_paper_by_doi("10.48550/arXiv.1706.03762")
    assert result is not None
    assert result["title"] == "Attention Is All You Need"
    assert result["authors"] == ["Ashish Vaswani", "Noam Shazeer"]
    assert result["year"] == 2017
    assert result["venue"] == "NeurIPS"
    assert result["doi"] == "10.48550/arXiv.1706.03762"


def test_get_paper_by_doi_returns_none_on_404():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    with patch("requests.get", return_value=mock_resp):
        result = get_paper_by_doi("10.1/missing")
    assert result is None


def test_get_paper_by_doi_returns_none_when_s2_get_returns_none():
    with patch("academic_wiki_mcp.s2_client._s2_get", return_value=None):
        result = get_paper_by_doi("10.1/ratelimited")
    assert result is None


# ---------------------------------------------------------------------------
# bibtex.parse_first_entry
# ---------------------------------------------------------------------------


def test_parse_first_entry_basic():
    text = "@article{Smith_2020, title = {Foo}, year = {2020}}"
    parsed = parse_first_entry(text)
    assert parsed["type"] == "article"
    assert parsed["key"] == "Smith_2020"
    assert parsed["fields"]["title"] == "Foo"
    assert parsed["fields"]["year"] == "2020"


def test_parse_first_entry_handles_inproceedings_with_braces():
    text = """@inproceedings{vaswani2017attention,
      title = {Attention Is All You Need},
      author = {Vaswani, Ashish and Shazeer, Noam},
      booktitle = {Advances in {Neural} Information Processing Systems},
      year = {2017},
    }"""
    parsed = parse_first_entry(text)
    assert parsed["type"] == "inproceedings"
    assert parsed["key"] == "vaswani2017attention"
    assert parsed["fields"]["title"] == "Attention Is All You Need"
    assert parsed["fields"]["booktitle"] == "Advances in {Neural} Information Processing Systems"
    assert parsed["fields"]["year"] == "2017"


def test_parse_first_entry_no_entry_raises():
    with pytest.raises(ValueError):
        parse_first_entry("not a bibtex file at all")


def test_parse_first_entry_double_quoted_with_escaped_quotes():
    text = '@article{x, title = "A \\"Quoted\\" Title", year = "2020"}'
    parsed = parse_first_entry(text)
    assert parsed["fields"]["title"] == 'A \\"Quoted\\" Title'
    assert parsed["fields"]["year"] == "2020"


# ---------------------------------------------------------------------------
# bibtex.rewrite_citation_key
# ---------------------------------------------------------------------------


def test_rewrite_citation_key_replaces_first_match():
    text = "@article{Smith_2020, title = {Foo}, year = {2020}}"
    result = rewrite_citation_key(text, "vaswani2017attention")
    assert result == "@article{vaswani2017attention, title = {Foo}, year = {2020}}"


def test_rewrite_citation_key_preserves_other_at_signs():
    text = "@article{x, note = {foo@bar.com}}"
    result = rewrite_citation_key(text, "newkey")
    # First @ rewritten, embedded @bar.com untouched
    assert result == "@article{newkey, note = {foo@bar.com}}"


def test_rewrite_citation_key_no_match_raises():
    with pytest.raises(ValueError):
        rewrite_citation_key("no entry here", "newkey")


def test_rewrite_citation_key_only_rewrites_first_entry():
    text = "@article{Smith_2020, year={2020}}\n@article{Jones_2021, year={2021}}"
    result = rewrite_citation_key(text, "newkey")
    assert "newkey" in result
    assert "Jones_2021" in result  # second entry untouched
    assert "Smith_2020" not in result
    assert result.count("newkey") == 1


def test_rewrite_citation_key_rejects_unsafe_paper_id():
    text = "@article{Smith_2020, year={2020}}"
    for bad in ["with space", "with,comma", "with{brace", "with}brace", ""]:
        with pytest.raises(ValueError):
            rewrite_citation_key(text, bad)


# ---------------------------------------------------------------------------
# bibtex.build_from_metadata
# ---------------------------------------------------------------------------


def _meta(**overrides):
    base = {
        "title": "Sample Title",
        "authors": ["Ada Lovelace", "Charles Babbage"],
        "year": 1843,
        "venue": "Sample Journal",
        "doi": "10.1/sample",
    }
    base.update(overrides)
    return base


def test_build_from_metadata_inproceedings():
    meta = _meta(venue="Proceedings of NeurIPS")
    text, entry_type = build_from_metadata(meta, "lovelace1843sample")
    assert entry_type == "inproceedings"
    assert text.startswith("@inproceedings{lovelace1843sample,")
    assert "booktitle = {Proceedings of NeurIPS}" in text
    assert "journal" not in text
    assert "title = {Sample Title}" in text
    assert "author = {Ada Lovelace and Charles Babbage}" in text
    assert "year = {1843}" in text
    assert "doi = {10.1/sample}" in text


def test_build_from_metadata_article():
    meta = _meta(venue="Nature")
    text, entry_type = build_from_metadata(meta, "key1")
    assert entry_type == "article"
    assert text.startswith("@article{key1,")
    assert "journal = {Nature}" in text
    assert "booktitle" not in text


def test_build_from_metadata_misc_no_venue():
    meta = _meta(venue="")
    text, entry_type = build_from_metadata(meta, "key1")
    assert entry_type == "misc"
    assert text.startswith("@misc{key1,")
    assert "journal" not in text
    assert "booktitle" not in text


def test_build_from_metadata_authors_joined_with_and():
    meta = _meta(authors=["A B", "C D", "E F"])
    text, _ = build_from_metadata(meta, "key1")
    assert "author = {A B and C D and E F}" in text


def test_build_from_metadata_omits_empty_doi():
    meta = _meta(doi="")
    text, _ = build_from_metadata(meta, "key1")
    assert "doi" not in text


def test_build_from_metadata_omits_empty_authors():
    meta = _meta(authors=[])
    text, _ = build_from_metadata(meta, "key1")
    assert "author" not in text


def test_build_from_metadata_raises_when_title_missing():
    meta = _meta(title="")
    with pytest.raises(ValueError):
        build_from_metadata(meta, "key1")


def test_build_from_metadata_raises_when_year_missing():
    meta = _meta(year=None)
    with pytest.raises(ValueError):
        build_from_metadata(meta, "key1")


def test_build_from_metadata_inproceedings_pattern_case_insensitive():
    meta = _meta(venue="cvpr 2024 workshop")
    _, entry_type = build_from_metadata(meta, "key1")
    assert entry_type == "inproceedings"


# ---------------------------------------------------------------------------
# tools/bibtex.doi_to_bibtex — input validation + happy path
# ---------------------------------------------------------------------------


async def test_doi_to_bibtex_invalid_doi_returns_error_without_network():
    with patch("requests.get") as mock_get:
        result = await doi_to_bibtex("not-a-doi", "key1")
    assert "error" in result
    assert "invalid DOI" in result["error"]
    mock_get.assert_not_called()


async def test_doi_to_bibtex_empty_paper_id_returns_error():
    with patch("requests.get") as mock_get:
        result = await doi_to_bibtex("10.1/foo", "")
    assert "error" in result
    assert "paper_id is required" in result["error"]
    assert result["doi"] == "10.1/foo"
    mock_get.assert_not_called()


async def test_doi_to_bibtex_doi_org_happy_path():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "@article{Smith_2020, title = {Foo}, year = {2020}}"
    mock_resp.headers = {"Content-Type": "application/x-bibtex"}
    with patch("requests.get", return_value=mock_resp):
        result = await doi_to_bibtex("10.1/foo", "lovelace1843sample")
    assert "error" not in result
    assert result["source"] == "doi.org"
    assert result["entry_type"] == "article"
    assert result["bibtex"].startswith("@article{lovelace1843sample,")
    assert "Smith_2020" not in result["bibtex"]
