from __future__ import annotations
import re

from academic_wiki_mcp.publishers.base import BasePublisher
from academic_wiki_mcp.browser import BrowserBackend
from academic_wiki_mcp.models import Metadata, Section, ContentBlock, Figure


class ScienceDirectPublisher(BasePublisher):
    async def extract_metadata(self, browser: BrowserBackend) -> Metadata:
        # Title
        title_el = await browser.query_selector("h1.title-text span.title-text")
        if title_el:
            title = await title_el.text()
        else:
            title_el2 = await browser.query_selector("h1.title-text")
            if title_el2:
                title = await title_el2.text()
            else:
                title = await self._meta_tag(browser, "citation_title")

        # Authors
        author_els = await browser.query_selector_all(".author span.text")
        authors = [await el.text() for el in author_els]
        if not authors:
            authors = await self._meta_tags(browser, "citation_author")

        # Abstract
        abstract_el = await browser.query_selector("[id*='abspara']")
        if not abstract_el:
            abstract_el = await browser.query_selector(".abstract div")
        if not abstract_el:
            abstract_el = await browser.query_selector("#abstracts p")
        abstract = await abstract_el.text() if abstract_el else ""

        doi = await self._meta_tag(browser, "citation_doi")
        date = await self._meta_tag(browser, "citation_publication_date")

        venue = await self._meta_tag(browser, "citation_journal_title")
        if not venue:
            venue_el = await browser.query_selector(".publication-title-link")
            if venue_el:
                venue = await venue_el.text()

        # Keywords
        kw_els = await browser.query_selector_all(".keyword span")
        keywords = [await el.text() for el in kw_els]

        year: int | None = None
        if date:
            m = re.search(r"(\d{4})", date)
            if m:
                year = int(m.group(1))

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

        # Abstract
        abstract_el = await browser.query_selector("[id*='abspara']")
        if not abstract_el:
            abstract_el = await browser.query_selector(".abstract div")
        if not abstract_el:
            abstract_el = await browser.query_selector("#abstracts p")
        if abstract_el:
            text = await abstract_el.text()
            if text:
                sections.append(
                    Section(
                        heading="Abstract",
                        content=[ContentBlock(type="paragraph", text=text)],
                    )
                )

        # Body — TreeWalker via evaluate (complex DOM traversal)
        body_data = await browser.evaluate("""
            () => {
                const bodyEl = document.querySelector('#body, .Body');
                if (!bodyEl) return [];

                const sectionList = [];
                let currentHeading = 'Introduction';
                let currentContent = [];

                function flush() {
                    if (currentContent.length > 0) {
                        sectionList.push({ heading: currentHeading, content: currentContent });
                    }
                    currentContent = [];
                }

                const walker = document.createTreeWalker(
                    bodyEl, NodeFilter.SHOW_ELEMENT, null
                );
                let node = walker.nextNode();

                while (node) {
                    const tag = node.tagName;

                    if (tag === 'H2' || tag === 'H3') {
                        flush();
                        currentHeading = node.textContent.trim() || 'Untitled Section';
                        node = walker.nextNode();
                        continue;
                    }

                    if (tag === 'DIV' && node.classList.contains('u-margin-s-bottom')) {
                        const text = node.textContent.trim();
                        if (text && text.length > 10) {
                            currentContent.push({ type: 'paragraph', text: text });
                        }
                        node = walker.nextNode();
                        continue;
                    }

                    if (tag === 'P') {
                        const text = node.textContent.trim();
                        if (text && text.length > 10) {
                            currentContent.push({ type: 'paragraph', text: text });
                        }
                        node = walker.nextNode();
                        continue;
                    }

                    if (tag === 'FIGURE') {
                        const img = node.querySelector('img');
                        const src = img?.getAttribute('data-src') || img?.src || '';
                        if (src && !/clear\\.gif|1x1|blank/i.test(src)) {
                            currentContent.push({ type: 'figure', figureId: src });
                        }
                        node = walker.nextSibling() || walker.nextNode();
                        continue;
                    }

                    node = walker.nextNode();
                }

                flush();
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

        # References
        ref_els = await browser.query_selector_all(
            ".reference .contribution, .bib-reference, [name='bibliography'] li"
        )
        if ref_els:
            content = []
            for i, el in enumerate(ref_els, 1):
                txt = await el.text()
                content.append(ContentBlock(type="paragraph", text=f"{i}. {txt}"))
            sections.append(Section(heading="References", content=content))

        return sections

    async def extract_figures(self, browser: BrowserBackend) -> list[Figure]:
        figures: list[Figure] = []

        data = await browser.evaluate("""
            async () => {
                const figures = [];
                const seen = new Set();
                const figEls = document.querySelectorAll(
                    'figure img, .figure img, img.imgLazyJSB'
                );

                for (const img of figEls) {
                    const rawSrc = img.getAttribute('data-src') || img.src || '';
                    if (!rawSrc) continue;

                    let url;
                    try { url = new URL(rawSrc, location.href).href; }
                    catch { url = rawSrc; }

                    if (/clear\\.gif|1x1|blank\\.gif/i.test(url)) continue;
                    if (seen.has(url)) continue;
                    seen.add(url);

                    img.scrollIntoView({ behavior: 'instant', block: 'center' });
                    await new Promise(r => setTimeout(r, 500));

                    const container = img.closest('.figure') || img.closest('figure')
                        || img.parentElement;
                    const captionEl = container?.querySelector('.captions')
                        || container?.querySelector('figcaption');
                    const caption = captionEl?.textContent?.trim() || '';

                    figures.push({ id: url, url: url, caption: caption });
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
