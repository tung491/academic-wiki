from __future__ import annotations
import re
from abc import ABC, abstractmethod

from academic_wiki_mcp.browser import BrowserBackend
from academic_wiki_mcp.models import Metadata, Section, Figure


def _normalize_date(raw: str) -> tuple[str, int | None]:
    """Normalize a raw date string to ISO format YYYY-MM-DD.

    Returns (iso_date_string, year_int).
    Falls back to ("YYYY-01-01", YYYY) if only a year is found,
    or ("", None) if completely unparseable.
    """
    if not raw:
        return "", None

    raw = raw.strip()

    # Already ISO: YYYY-MM-DD
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        return raw, int(m.group(1))

    # YYYY/MM/DD
    m = re.fullmatch(r"(\d{4})/(\d{2})/(\d{2})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}", int(m.group(1))

    _MONTHS = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12",
    }

    # "Month DD, YYYY" or "Month YYYY"
    m = re.match(
        r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})",
        raw,
    )
    if m:
        mon = _MONTHS.get(m.group(1).lower())
        if mon:
            day = m.group(2).zfill(2)
            return f"{m.group(3)}-{mon}-{day}", int(m.group(3))

    # "DD Month YYYY"
    m = re.match(
        r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
        raw,
    )
    if m:
        mon = _MONTHS.get(m.group(2).lower())
        if mon:
            day = m.group(1).zfill(2)
            return f"{m.group(3)}-{mon}-{day}", int(m.group(3))

    # Bare year only
    m = re.fullmatch(r"(\d{4})", raw)
    if m:
        return f"{m.group(1)}-01-01", int(m.group(1))

    # Year anywhere in the string
    m = re.search(r"(\d{4})", raw)
    if m:
        return f"{m.group(1)}-01-01", int(m.group(1))

    return "", None


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
