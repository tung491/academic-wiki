from unittest.mock import patch, MagicMock

from semantic_scholar_mcp.s2_client import get_paper_by_doi


def test_get_paper_by_doi_returns_normalized_paper():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "paperId": "abc",
        "title": "Attention Is All You Need",
        "authors": [{"name": "Vaswani"}, {"name": "Shazeer"}],
        "year": 2017,
        "venue": "NeurIPS",
        "abstract": "We propose the Transformer.",
        "externalIds": {"DOI": "10.48550/arXiv.1706.03762", "ArXiv": "1706.03762"},
        "citationCount": 99999,
        "publicationTypes": ["JournalArticle"],
    }
    with patch("requests.get", return_value=mock_resp):
        result = get_paper_by_doi("10.48550/arXiv.1706.03762")

    assert result is not None
    assert result["paperId"] == "abc"
    assert result["title"] == "Attention Is All You Need"
    assert result["authors"] == ["Vaswani", "Shazeer"]
    assert result["year"] == 2017
    assert result["doi"] == "10.48550/arXiv.1706.03762"
    assert result["arxiv"] == "1706.03762"
    assert result["citationCount"] == 99999
    assert result["publicationTypes"] == ["JournalArticle"]


def test_get_paper_by_doi_returns_none_on_404():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    with patch("requests.get", return_value=mock_resp):
        result = get_paper_by_doi("10.0/nonexistent")
    assert result is None


def test_get_paper_by_doi_returns_none_after_retries_on_503():
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.raise_for_status.return_value = None
    # Patch time.sleep to avoid waiting for 2+4+8+16+32 seconds in the retry loop.
    with patch("requests.get", return_value=mock_resp), \
         patch("semantic_scholar_mcp.s2_client.time.sleep"):
        result = get_paper_by_doi("10.1/x")
    assert result is None
