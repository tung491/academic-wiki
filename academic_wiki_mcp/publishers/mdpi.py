from __future__ import annotations
import re

from academic_wiki_mcp.publishers.base import BasePublisher
from academic_wiki_mcp.browser import BrowserBackend
from academic_wiki_mcp.models import Metadata, Section, ContentBlock, Figure


class MDPIPublisher(BasePublisher):
    async def extract_metadata(self, browser: BrowserBackend) -> Metadata:
        # Title
        title_el = await browser.query_selector("h1.title")
        if title_el:
            title = await title_el.text()
        else:
            alt_el = await browser.query_selector(".article-title")
            if alt_el:
                title = await alt_el.text()
            else:
                title = await self._meta_tag(browser, "citation_title")

        # Authors
        author_els = await browser.query_selector_all(
            ".art-authors .sciprofiles-link"
        )
        if author_els:
            authors = [await el.text() for el in author_els]
        else:
            authors = await self._meta_tags(browser, "citation_author")

        # Abstract
        abstract_el = await browser.query_selector(".art-abstract p")
        if not abstract_el:
            abstract_el = await browser.query_selector(".art-abstract .html-p")
        abstract = await abstract_el.text() if abstract_el else ""

        doi = await self._meta_tag(browser, "citation_doi")
        date = await self._meta_tag(browser, "citation_publication_date")

        venue = await self._meta_tag(browser, "citation_journal_title")
        if not venue:
            venue_el = await browser.query_selector(".journal-name")
            if venue_el:
                venue = await venue_el.text()

        # Keywords — strip trailing semicolons
        kw_els = await browser.query_selector_all(".art-keyword")
        keywords = []
        for el in kw_els:
            kw = await el.text()
            kw = kw.strip().rstrip(";").strip()
            if kw:
                keywords.append(kw)

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
        abstract_el = await browser.query_selector(".art-abstract p")
        if not abstract_el:
            abstract_el = await browser.query_selector(".art-abstract .html-p")
        if abstract_el:
            text = await abstract_el.text()
            if text:
                sections.append(
                    Section(
                        heading="Abstract",
                        content=[ContentBlock(type="paragraph", text=text)],
                    )
                )

        # Body: filtered TreeWalker on .html-body via evaluate
        body_data = await browser.evaluate("""
            () => {
                const bodyEl = document.querySelector('.html-body');
                if (!bodyEl) return [];

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
                let currentHeading = null;
                let currentContent = [];

                function flush() {
                    if (currentHeading !== null || currentContent.length > 0) {
                        sectionList.push({
                            heading: currentHeading || 'Untitled Section',
                            content: currentContent
                        });
                    }
                    currentHeading = null;
                    currentContent = [];
                }

                const walker = document.createTreeWalker(
                    bodyEl, NodeFilter.SHOW_ELEMENT, {
                        acceptNode(node) {
                            if (node.matches(
                                '.html-h2, .html-h4, .html-p, .html-fig_img, ' +
                                '.html-table_show, .html-fig_description'
                            )) return NodeFilter.FILTER_ACCEPT;
                            return NodeFilter.FILTER_SKIP;
                        }
                    }
                );

                let node;
                while ((node = walker.nextNode())) {
                    if (node.matches('.html-h2, .html-h4')) {
                        flush();
                        currentHeading = node.textContent.trim();
                    } else if (node.matches('.html-p')) {
                        const text = node.textContent.trim();
                        if (text) currentContent.push({ type: 'paragraph', text });
                    } else if (node.matches('.html-fig_img')) {
                        const img = node.querySelector('a.html-img-zoom img')
                            || node.querySelector('.html-figpopup img');
                        if (img && img.src) {
                            currentContent.push({ type: 'figure', figureId: img.src });
                        }
                    } else if (node.matches('.html-table_show')) {
                        const table = node.querySelector('table');
                        if (table) {
                            const tableText = extractTableAsText(table);
                            if (tableText) {
                                currentContent.push({ type: 'paragraph', text: tableText });
                            }
                        }
                    }
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
            ".html-bib-entry, .article-bibliography li"
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

                // Primary: a.html-img-zoom img
                const imgEls = document.querySelectorAll('a.html-img-zoom img');
                for (const img of imgEls) {
                    const src = img.src;
                    if (!src || seen.has(src)) continue;
                    seen.add(src);

                    img.scrollIntoView({ behavior: 'instant', block: 'center' });
                    await new Promise(r => setTimeout(r, 200));

                    const container = img.closest('.html-fig_show')
                        || img.closest('.html-img')?.parentElement;
                    const captionEl = container?.querySelector('.html-fig_description');
                    const caption = captionEl?.textContent?.trim() || '';

                    figures.push({ id: src, url: src, caption: caption });
                }

                // Fallback: .html-figpopup img
                if (figures.length === 0) {
                    const fallbackImgs = document.querySelectorAll('.html-figpopup img');
                    for (const fImg of fallbackImgs) {
                        const fSrc = fImg.src;
                        if (!fSrc || seen.has(fSrc)) continue;
                        seen.add(fSrc);

                        const fContainer = fImg.closest('.html-fig_img')?.parentElement;
                        const fCaptionEl = fContainer?.querySelector('.html-fig_description');
                        const fCaption = fCaptionEl?.textContent?.trim() || '';

                        figures.push({ id: fSrc, url: fSrc, caption: fCaption });
                    }
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
