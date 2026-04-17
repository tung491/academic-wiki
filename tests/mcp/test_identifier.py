import pytest
from academic_wiki_mcp.identifier import detect


@pytest.mark.parametrize("input_str,expected_type,expected_id", [
    ("10.1109/TPAMI.2021.1234567", "doi", "10.1109/TPAMI.2021.1234567"),
    ("10.48550/arXiv.1706.03762", "doi", "10.48550/arXiv.1706.03762"),
    ("1706.03762", "arxiv", "1706.03762"),
    ("2301.12345v2", "arxiv", "2301.12345v2"),
    ("cs-AI/0301001", "arxiv", "cs-AI/0301001"),
    ("arXiv:1706.03762", "arxiv", "1706.03762"),
    ("arxiv:2301.12345", "arxiv", "2301.12345"),
    ("doi:10.1109/TPAMI.2021.1234567", "doi", "10.1109/TPAMI.2021.1234567"),
    ("https://arxiv.org/abs/1706.03762", "arxiv", "1706.03762"),
    ("https://arxiv.org/html/2301.12345v1", "arxiv", "2301.12345v1"),
    ("https://arxiv.org/pdf/1706.03762", "arxiv", "1706.03762"),
    ("https://doi.org/10.1109/TPAMI.2021.1234567", "doi", "10.1109/TPAMI.2021.1234567"),
    ("transformer attention", "unknown", "transformer attention"),
    ("", "unknown", ""),
])
def test_detect(input_str, expected_type, expected_id):
    id_type, raw_id = detect(input_str)
    assert id_type == expected_type
    assert raw_id == expected_id
