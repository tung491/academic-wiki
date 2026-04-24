import pytest
from unittest.mock import patch, MagicMock
from semantic_scholar_mcp.s2_client import _s2_get
from semantic_scholar_mcp.tools.discovery import (
    _search,
    _references,
    _citations,
    _recommendations,
)


@pytest.mark.asyncio
async def test_search_returns_results():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [
        {
            "paperId": "abc",
            "title": "Test",
            "authors": [{"name": "A"}],
            "year": 2024,
            "venue": "V",
            "abstract": "Ab",
            "externalIds": {"DOI": "10.1/x"},
        },
    ]}
    with patch("requests.get", return_value=mock_resp):
        results = await _search("transformer", limit=1)
        assert len(results) == 1
        assert results[0]["title"] == "Test"


@pytest.mark.asyncio
async def test_recommendations_404_returns_empty():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    with patch("requests.get", return_value=mock_resp):
        results = await _recommendations("abc123")
        assert results == []


@pytest.mark.asyncio
async def test_search_empty_on_non_200():
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.raise_for_status.return_value = None
    with patch("requests.get", return_value=mock_resp):
        results = await _search("transformer", limit=1)
        assert results == []


@pytest.mark.asyncio
async def test_references_returns_results():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [
        {
            "citedPaper": {
                "paperId": "ref1",
                "title": "Referenced Paper",
                "authors": [{"name": "B"}],
                "year": 2020,
                "venue": "ICML",
                "abstract": "",
                "externalIds": {},
                "citationCount": 50,
            }
        },
    ]}
    with patch("requests.get", return_value=mock_resp):
        results = await _references("someid", limit=10)
        assert len(results) == 1
        assert results[0]["title"] == "Referenced Paper"


@pytest.mark.asyncio
async def test_citations_returns_results():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [
        {
            "citingPaper": {
                "paperId": "cit1",
                "title": "Citing Paper",
                "authors": [{"name": "C"}],
                "year": 2023,
                "venue": "NeurIPS",
                "abstract": "",
                "externalIds": {},
                "citationCount": 10,
            }
        },
    ]}
    with patch("requests.get", return_value=mock_resp):
        results = await _citations("someid", limit=10)
        assert len(results) == 1
        assert results[0]["title"] == "Citing Paper"


def test_s2_get_returns_200_response():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("requests.get", return_value=mock_resp) as mock_get:
        result = _s2_get("https://api.semanticscholar.org/graph/v1/paper/search")
        assert result is mock_resp
        mock_get.assert_called_once()
