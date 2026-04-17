from __future__ import annotations
import re

from academic_wiki_mcp.publishers.base import BasePublisher
from academic_wiki_mcp.browser import BrowserBackend
from academic_wiki_mcp.models import Metadata, Section, ContentBlock, Figure


class WileyPublisher(BasePublisher):
    async def extract_metadata(self, browser: BrowserBackend) -> Metadata:
        # Title
        title_el = await browser.query_selector(".citation__title")
        if title_el:
            title = await title_el.text()
        else:
            title = await self._meta_tag(browser, "citation_title")

        # Authors
        author_els = await browser.query_selector_all(
            ".loa-authors-trunc .author-name span, .loa-authors .author-name span"
        )
        authors = [await el.text() for el in author_els]
        if not authors:
            authors = await self._meta_tags(browser, "citation_author")

        # Abstract — 3-tier selector
        abstract_el = await browser.query_selector(
            "#abstract .article-section__content p"
        )
        if not abstract_el:
            abstract_el = await browser.query_selector(
                "[class*='abstract'] .article-section__content p"
            )
        if not abstract_el:
            abstract_el = await browser.query_selector(
                ".article-section__content p"
            )
        abstract = await abstract_el.text() if abstract_el else ""

        doi = await self._meta_tag(browser, "citation_doi")
        date = await self._meta_tag(browser, "citation_publication_date")
        venue = await self._meta_tag(browser, "citation_journal_title")

        # Keywords
        kw_els = await browser.query_selector_all(
            ".article-keywords__list a, .kwd-group .kwd"
        )
        keywords_seen: set[str] = set()
        keywords: list[str] = []
        for el in kw_els:
            kw = await el.text()
            if kw and kw not in keywords_seen:
                keywords_seen.add(kw)
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

        # Abstract (3-tier, same as metadata)
        abstract_el = await browser.query_selector(
            "#abstract .article-section__content p"
        )
        if not abstract_el:
            abstract_el = await browser.query_selector(
                "[class*='abstract'] .article-section__content p"
            )
        if not abstract_el:
            abstract_el = await browser.query_selector(
                ".article-section__content p"
            )
        if abstract_el:
            text = await abstract_el.text()
            if text:
                sections.append(
                    Section(
                        heading="Abstract",
                        content=[ContentBlock(type="paragraph", text=text)],
                    )
                )

        # Body sections via evaluate — seenAbstract skip logic + table extraction
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
                let seenAbstract = false;

                const abstractEl =
                    document.querySelector('#abstract .article-section__content p') ||
                    document.querySelector('[class*="abstract"] .article-section__content p') ||
                    document.querySelector('.article-section__content p');

                document.querySelectorAll('.article-section__content').forEach(sectionEl => {
                    if (!seenAbstract) {
                        seenAbstract = true;
                        const isAbstract = sectionEl.closest('#abstract')
                            || sectionEl.closest('[class*="abstract"]');
                        if (isAbstract
                            || sectionEl === abstractEl?.closest('.article-section__content')
                        ) return;
                    }

                    const parent = sectionEl.closest('section') || sectionEl.parentElement;
                    const headingEl = parent?.querySelector(
                        'h2, h3, .article-section__title'
                    );
                    const heading = headingEl?.textContent?.trim() || 'Untitled Section';

                    if (/references|bibliography|supporting info|acknowledgment/i.test(heading))
                        return;

                    const content = [];

                    sectionEl.querySelectorAll('p').forEach(p => {
                        const text = p.textContent.trim();
                        if (text && text.length > 10) {
                            content.push({ type: 'paragraph', text });
                        }
                    });

                    sectionEl.querySelectorAll('figure').forEach(fig => {
                        const img = fig.querySelector('img.figure__image, picture img, img');
                        if (img && img.src && img.src.includes('cms/asset')) {
                            content.push({ type: 'figure', figureId: img.src });
                        }
                    });

                    sectionEl.querySelectorAll('.article-table-content-wrapper').forEach(wrapper => {
                        const captionEl = wrapper.closest('.article-table-content')
                            ?.querySelector(
                                '.article-table-caption, .table-caption__label'
                            );
                        const caption = captionEl?.textContent?.trim() || '';
                        const table = wrapper.querySelector('table');
                        if (table) {
                            let tableText = extractTableAsText(table);
                            if (caption) tableText = caption + '\\n' + tableText;
                            if (tableText) content.push({ type: 'paragraph', text: tableText });
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

        # References
        ref_els = await browser.query_selector_all(
            "#references-section li, .citation__body"
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
                const figureEls = document.querySelectorAll('figure.figure');

                for (const fig of figureEls) {
                    const img = fig.querySelector('img.figure__image')
                        || fig.querySelector('picture img')
                        || fig.querySelector('img');
                    if (!img) continue;

                    const src = img.src;
                    if (!src || !src.includes('cms/asset')) continue;
                    if (seen.has(src)) continue;
                    seen.add(src);

                    img.scrollIntoView({ behavior: 'instant', block: 'center' });
                    await new Promise(r => setTimeout(r, 300));

                    const captionEl = fig.querySelector('figcaption, .figure__caption');
                    const caption = captionEl?.textContent?.trim() || '';

                    figures.push({ id: src, url: src, caption: caption });
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
