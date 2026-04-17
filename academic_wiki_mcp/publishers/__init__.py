from __future__ import annotations
from urllib.parse import urlparse

from academic_wiki_mcp.publishers.base import BasePublisher
from academic_wiki_mcp.publishers.arxiv import ArxivPublisher
from academic_wiki_mcp.publishers.ieee import IEEEPublisher
from academic_wiki_mcp.publishers.springer import SpringerPublisher
from academic_wiki_mcp.publishers.sciencedirect import ScienceDirectPublisher
from academic_wiki_mcp.publishers.mdpi import MDPIPublisher
from academic_wiki_mcp.publishers.wiley import WileyPublisher
from academic_wiki_mcp.publishers.tandfonline import TandFPublisher
from academic_wiki_mcp.publishers.asce import ASCEPublisher

PUBLISHERS: list[tuple[str, type[BasePublisher]]] = [
    ("arxiv.org", ArxivPublisher),
    ("ieeexplore.ieee.org", IEEEPublisher),
    ("link.springer.com", SpringerPublisher),
    ("sciencedirect.com", ScienceDirectPublisher),
    ("mdpi.com", MDPIPublisher),
    ("onlinelibrary.wiley.com", WileyPublisher),
    ("tandfonline.com", TandFPublisher),
    ("ascelibrary.org", ASCEPublisher),
]


def find_publisher(url: str) -> BasePublisher | None:
    hostname = urlparse(url).hostname or ""
    for suffix, cls in PUBLISHERS:
        if hostname == suffix or hostname.endswith("." + suffix):
            return cls()
    return None
