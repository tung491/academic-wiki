import pytest
from academic_wiki_mcp.publishers import find_publisher
from academic_wiki_mcp.publishers.base import BasePublisher


def test_find_publisher_exact():
    pub = find_publisher("https://arxiv.org/html/1706.03762")
    assert pub is not None
    assert type(pub).__name__ == "ArxivPublisher"


def test_find_publisher_www_prefix():
    pub = find_publisher("https://www.sciencedirect.com/science/article/pii/S0001")
    assert pub is not None
    assert type(pub).__name__ == "ScienceDirectPublisher"


def test_find_publisher_unknown():
    assert find_publisher("https://example.com/paper") is None


def test_find_publisher_ieee():
    pub = find_publisher("https://ieeexplore.ieee.org/document/123456")
    assert type(pub).__name__ == "IEEEPublisher"


def test_find_publisher_mdpi_www():
    pub = find_publisher("https://www.mdpi.com/1234-5678/1/1/1")
    assert type(pub).__name__ == "MDPIPublisher"


def test_base_publisher_is_abstract():
    with pytest.raises(TypeError):
        BasePublisher()
