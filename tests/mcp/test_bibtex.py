from unittest.mock import MagicMock, patch

import pytest

from academic_wiki_mcp.s2_client import get_paper_by_doi


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
