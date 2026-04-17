from __future__ import annotations

from academic_wiki_mcp.publishers.base import BasePublisher, _normalize_date
from academic_wiki_mcp.browser import BrowserBackend
from academic_wiki_mcp.models import Metadata, Section, ContentBlock, Figure


class SpringerPublisher(BasePublisher):
    async def extract_metadata(self, browser: BrowserBackend) -> Metadata:
        # Title
        title_el = await browser.query_selector(
            "h1.c-article-title, h1.ArticleTitle"
        )
        if title_el:
            title = await title_el.text()
        else:
            title = await self._meta_tag(browser, "citation_title")

        # Authors
        author_els = await browser.query_selector_all('[data-test="author-name"]')
        if author_els:
            authors = [await el.text() for el in author_els]
        else:
            authors = await self._meta_tags(browser, "citation_author")

        # Abstract
        abstract_el = await browser.query_selector("#Abs1-content p")
        abstract = await abstract_el.text() if abstract_el else ""

        doi = await self._meta_tag(browser, "citation_doi")

        # Date: citation_publication_date, then time[datetime]
        date = await self._meta_tag(browser, "citation_publication_date")
        if not date:
            time_el = await browser.query_selector("time[datetime]")
            if time_el:
                date = (await time_el.attribute("datetime")) or ""

        venue = await self._meta_tag(browser, "citation_journal_title")

        # Keywords
        kw_els = await browser.query_selector_all(".c-article-subject-list__subject")
        keywords = [await el.text() for el in kw_els]

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

        # Abstract
        abstract_el = await browser.query_selector("#Abs1-content p")
        if abstract_el:
            text = await abstract_el.text()
            if text:
                sections.append(
                    Section(
                        heading="Abstract",
                        content=[ContentBlock(type="paragraph", text=text)],
                    )
                )

        # Body sections — skip Abs1/Abs1-section
        section_els = await browser.query_selector_all(".c-article-section")
        for sec_el in section_els:
            sec_id = (await sec_el.attribute("id")) or ""
            if sec_id in ("Abs1", "Abs1-section"):
                continue

            heading = await browser.evaluate("""
                (secEl) => {
                    const h = secEl.querySelector('h2, h3');
                    return h ? h.textContent.trim() : 'Untitled Section';
                }
            """, sec_el) or "Untitled Section"

            paras = await browser.evaluate("""
                (secEl) => {
                    return Array.from(
                        secEl.querySelectorAll(
                            ':scope > .c-article-section__content p, :scope > p'
                        )
                    ).map(p => p.textContent.trim()).filter(Boolean);
                }
            """, sec_el)

            content: list[ContentBlock] = []
            for p_text in (paras or []):
                content.append(ContentBlock(type="paragraph", text=p_text))

            # Figures: only .c-article-section__figure (avoids sidebar dupes)
            fig_data = await browser.evaluate("""
                (secEl) => {
                    function normalizeUrl(src) {
                        if (!src) return '';
                        if (src.startsWith('//')) return 'https:' + src;
                        if (src.startsWith('http')) return src;
                        return new URL(src, location.href).href;
                    }
                    const results = [];
                    secEl.querySelectorAll('.c-article-section__figure').forEach(figDiv => {
                        const img = figDiv.querySelector('picture img, img');
                        if (!img) return;
                        const rawSrc = img.getAttribute('data-src') || img.src || '';
                        if (!rawSrc) return;
                        results.push(normalizeUrl(rawSrc));
                    });
                    return results;
                }
            """, sec_el)
            for src in (fig_data or []):
                content.append(ContentBlock(type="figure", figure_id=src))

            if content:
                sections.append(Section(heading=heading, content=content))

        # References
        ref_els = await browser.query_selector_all(
            "#Bib1 .c-article-references__item"
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

                function normalizeUrl(src) {
                    if (!src) return '';
                    if (src.startsWith('//')) return 'https:' + src;
                    if (src.startsWith('http')) return src;
                    return new URL(src, location.href).href;
                }

                const figDivs = document.querySelectorAll('.c-article-section__figure');
                for (const figDiv of figDivs) {
                    const img = figDiv.querySelector('picture img, img');
                    if (!img) continue;

                    const src = img.getAttribute('data-src') || img.src;
                    if (!src) continue;
                    const url = normalizeUrl(src);
                    if (seen.has(url)) continue;
                    seen.add(url);

                    img.scrollIntoView({ behavior: 'instant', block: 'center' });
                    await new Promise(r => setTimeout(r, 300));

                    const actualSrc = img.src || img.getAttribute('data-src');
                    const actualUrl = normalizeUrl(actualSrc || src);

                    const captionEl = figDiv.querySelector(
                        '.c-article-section__figure-description, figcaption, ' +
                        'b.c-article-section__figure-caption'
                    );
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
