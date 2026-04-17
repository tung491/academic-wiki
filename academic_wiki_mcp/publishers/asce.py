from __future__ import annotations

from academic_wiki_mcp.publishers.base import BasePublisher, _normalize_date
from academic_wiki_mcp.browser import BrowserBackend
from academic_wiki_mcp.models import Metadata, Section, ContentBlock, Figure


class ASCEPublisher(BasePublisher):
    async def extract_metadata(self, browser: BrowserBackend) -> Metadata:
        # Title
        title_el = await browser.query_selector(
            "h1.citation__title, h1.article__title"
        )
        if title_el:
            title = await title_el.text()
        else:
            title = await self._meta_tag(browser, "citation_title")

        # Authors
        author_els = await browser.query_selector_all(
            ".author-name span, .loa__author-name, .contrib-author a"
        )
        authors = [await el.text() for el in author_els]
        if not authors:
            authors = await self._meta_tags(browser, "citation_author")

        # Abstract — iterate sections for h2 matching /^abstract$/i
        abstract = await browser.evaluate("""
            () => {
                let result = '';
                document.querySelectorAll('section').forEach(sec => {
                    const h = sec.querySelector('h2');
                    if (h && /^abstract$/i.test(h.textContent.trim())) {
                        const div = sec.querySelector('div');
                        if (div) result = div.textContent.trim();
                    }
                });
                return result;
            }
        """) or ""

        doi = await self._meta_tag(browser, "citation_doi")
        date = await self._meta_tag(browser, "citation_publication_date")
        venue = await self._meta_tag(browser, "citation_journal_title")

        # Keywords
        kw_els = await browser.query_selector_all(
            ".article__keyword, .abstractKeywords a, .kwd-group .kwd"
        )
        keywords_seen: set[str] = set()
        keywords: list[str] = []
        for el in kw_els:
            kw = await el.text()
            if kw and kw not in keywords_seen:
                keywords_seen.add(kw)
                keywords.append(kw)

        date, year = _normalize_date(date)

        return Metadata(
            title=title,
            authors=authors,
            abstract=abstract,
            doi=doi,
            arxiv=None,
            url="",
            date=date,
            year=year,
            venue=venue,
            keywords=keywords,
        )

    async def extract_sections(self, browser: BrowserBackend) -> list[Section]:
        sections: list[Section] = []

        # Extract via evaluate — div.core-container section walk
        body_data = await browser.evaluate("""
            () => {
                function extractTableAsText(table) {
                    const rows = [];
                    table.querySelectorAll('tr').forEach(tr => {
                        const cells = [];
                        tr.querySelectorAll('th, td').forEach(cell => {
                            cells.push(cell.textContent.trim());
                        });
                        rows.push(cells.join(' | '));
                    });
                    return rows.join('\\n');
                }

                const sectionList = [];
                const container = document.querySelector('div.core-container');
                if (!container) return sectionList;

                container.querySelectorAll('section').forEach(sec => {
                    const h2 = sec.querySelector('h2');
                    if (!h2) return;
                    const heading = h2.textContent.trim();

                    if (/data availability|acknowledgment|author contribution|supplemental/i
                            .test(heading)) return;

                    const content = [];

                    [...sec.children].forEach(child => {
                        if (child.tagName === 'H2' || child.tagName === 'H3') return;

                        if (child.tagName === 'FIGURE' || child.querySelector?.('figure')) {
                            const isFig = child.tagName === 'FIGURE';
                            const img = isFig
                                ? child.querySelector('img')
                                : child.querySelector('figure img');
                            const src = img?.getAttribute('data-src') || img?.src || '';
                            if (src) content.push({ type: 'figure', figureId: src });

                            const figEl = isFig ? child : child.querySelector('figure');
                            const captionText = figEl?.querySelector('figcaption')
                                ?.textContent?.trim();
                            if (captionText) {
                                content.push({ type: 'paragraph', text: captionText });
                            }
                            return;
                        }

                        if (child.tagName === 'TABLE' || child.querySelector?.('table')) {
                            const table = child.tagName === 'TABLE'
                                ? child
                                : child.querySelector('table');
                            if (table && table.querySelectorAll('tr').length >= 2) {
                                const tableText = extractTableAsText(table);
                                if (tableText) content.push({ type: 'paragraph', text: tableText });
                            }
                            return;
                        }

                        const text = child.textContent.trim();
                        if (text && text.length > 10) {
                            content.push({ type: 'paragraph', text });
                        }
                    });

                    if (content.length > 0) {
                        sectionList.push({ heading, content });
                    }
                });

                return sectionList;
            }
        """)

        for sec_data in (body_data or []):
            content: list[ContentBlock] = []
            for block in sec_data["content"]:
                if block["type"] == "figure":
                    content.append(
                        ContentBlock(type="figure", figure_id=block["figureId"])
                    )
                else:
                    content.append(
                        ContentBlock(type="paragraph", text=block["text"])
                    )
            if content:
                sections.append(Section(heading=sec_data["heading"], content=content))

        # No references section for ASCE
        return sections

    async def extract_figures(self, browser: BrowserBackend) -> list[Figure]:
        figures: list[Figure] = []

        data = await browser.evaluate("""
            async () => {
                const figures = [];
                const seen = new Set();
                const figEls = document.querySelectorAll('figure img');

                for (const img of figEls) {
                    const src = img.getAttribute('data-src') || img.src;
                    if (!src) continue;

                    let url;
                    try { url = src.startsWith('http') ? src : new URL(src, location.href).href; }
                    catch { url = src; }

                    if (seen.has(url)) continue;
                    if (/icon|logo|spinner/i.test(url)) continue;
                    seen.add(url);

                    img.scrollIntoView({ behavior: 'instant', block: 'center' });
                    await new Promise(r => setTimeout(r, 300));

                    const actualSrc = img.src || img.getAttribute('data-src');
                    let actualUrl = url;
                    if (actualSrc) {
                        try {
                            actualUrl = actualSrc.startsWith('http')
                                ? actualSrc
                                : new URL(actualSrc, location.href).href;
                        } catch { actualUrl = url; }
                    }

                    const container = img.closest('figure');
                    const captionEl = container?.querySelector('figcaption');
                    const caption = captionEl?.textContent?.trim() || '';

                    figures.push({ id: url, url: actualUrl, caption: caption });
                }
                return figures;
            }
        """)

        for i, item in enumerate(data or [], 1):
            figures.append(Figure(
                id=item["id"],
                url=item["url"],
                filename=f"fig{i}.png",
                caption=item["caption"],
            ))

        return figures
