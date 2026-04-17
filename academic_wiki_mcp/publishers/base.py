from __future__ import annotations
from abc import ABC, abstractmethod

from academic_wiki_mcp.browser import BrowserBackend
from academic_wiki_mcp.models import Metadata, Section, Figure


class BasePublisher(ABC):
    backend: str = "playwright"
    fallback_backend: str = "selenium"

    @abstractmethod
    async def extract_metadata(self, browser: BrowserBackend) -> Metadata: ...

    @abstractmethod
    async def extract_sections(self, browser: BrowserBackend) -> list[Section]: ...

    @abstractmethod
    async def extract_figures(self, browser: BrowserBackend) -> list[Figure]: ...

    async def _meta_tag(self, browser: BrowserBackend, name: str) -> str:
        el = await browser.query_selector(f'meta[name="{name}"]')
        if el:
            return (await el.attribute("content")) or ""
        return ""

    async def _meta_tags(self, browser: BrowserBackend, name: str) -> list[str]:
        els = await browser.query_selector_all(f'meta[name="{name}"]')
        results = []
        for el in els:
            val = await el.attribute("content")
            if val:
                results.append(val.strip())
        return results

    async def _fallback_metadata(self, browser: BrowserBackend) -> Metadata:
        return Metadata(
            title=await self._meta_tag(browser, "citation_title"),
            authors=await self._meta_tags(browser, "citation_author"),
            abstract="",
            doi=await self._meta_tag(browser, "citation_doi"),
            arxiv=None,
            url="",
            date=await self._meta_tag(browser, "citation_publication_date"),
            year=None,
            venue=await self._meta_tag(browser, "citation_journal_title"),
            keywords=[],
        )
