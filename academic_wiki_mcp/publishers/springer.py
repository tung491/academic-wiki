from academic_wiki_mcp.publishers.base import BasePublisher
from academic_wiki_mcp.browser import BrowserBackend
from academic_wiki_mcp.models import Metadata, Section, Figure


class SpringerPublisher(BasePublisher):
    async def extract_metadata(self, browser: BrowserBackend) -> Metadata:
        raise NotImplementedError

    async def extract_sections(self, browser: BrowserBackend) -> list[Section]:
        raise NotImplementedError

    async def extract_figures(self, browser: BrowserBackend) -> list[Figure]:
        raise NotImplementedError
