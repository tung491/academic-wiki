from __future__ import annotations

from academic_wiki_mcp.publishers.base import BasePublisher, _normalize_date
from academic_wiki_mcp.browser import BrowserBackend
from academic_wiki_mcp.models import Metadata, Section, ContentBlock, Figure


class IEEEPublisher(BasePublisher):
    async def extract_metadata(self, browser: BrowserBackend) -> Metadata:
        # Title
        title_el = await browser.query_selector(".document-title")
        if title_el:
            title = await title_el.text()
        else:
            og_el = await browser.query_selector('meta[property="og:title"]')
            if og_el:
                title = (await og_el.attribute("content")) or ""
            else:
                title = await self._meta_tag(browser, "citation_title")

        # Authors
        author_els = await browser.query_selector_all(
            '.authors-info .author-name, .authors-info span[id^="author"]'
        )
        authors = [await el.text() for el in author_els]
        if not authors:
            authors = await self._meta_tags(browser, "citation_author")

        # Abstract
        abstract_el = await browser.query_selector(
            ".abstract-text .u-mb-1, .abstract-desktop-div div[xplmathjax]"
        )
        abstract = await abstract_el.text() if abstract_el else ""

        # DOI
        doi_el = await browser.query_selector(
            '.stats-document-abstract-doi a, a[href*="doi.org"]'
        )
        doi = (await doi_el.text()).strip() if doi_el else ""
        if not doi:
            doi = await self._meta_tag(browser, "citation_doi")

        # Date — strip "Date of Publication:" prefix
        date_el = await browser.query_selector(
            ".doc-abstract-pubdate, "
            ".stats-document-abstract-publishedIn .document-banner-date"
        )
        if date_el:
            raw_date = await date_el.text()
            date = raw_date.replace("Date of Publication:", "").strip()
        else:
            date = await self._meta_tag(browser, "citation_publication_date")

        # Venue
        venue_el = await browser.query_selector(
            ".stats-document-abstract-publishedIn a, .document-banner-conference-title"
        )
        venue = await venue_el.text() if venue_el else ""
        if not venue:
            venue = await self._meta_tag(browser, "citation_journal_title")

        # Keywords
        keyword_els = await browser.query_selector_all(
            ".stats-keywords-section .stats-keywords a"
        )
        keywords_seen: set[str] = set()
        keywords: list[str] = []
        for el in keyword_els:
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

        # Abstract
        abstract_el = await browser.query_selector(
            ".abstract-text .u-mb-1, .abstract-desktop-div div[xplmathjax]"
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

        # Body sections
        section_els = await browser.query_selector_all(
            "div.section, div.section_2, .section--body, "
            ".document-ft-section-container .section"
        )
        for sec_el in section_els:
            heading = await browser.evaluate("""
                (secEl) => {
                    const h = secEl.querySelector('h2, h3, .section-title, .header-title');
                    return h ? h.textContent.trim() : 'Untitled Section';
                }
            """, sec_el) or "Untitled Section"

            paras = await browser.evaluate("""
                (secEl) => {
                    return Array.from(
                        secEl.querySelectorAll('p, .paragraph, div[xplmathjax]')
                    ).map(p => p.textContent.trim()).filter(Boolean);
                }
            """, sec_el)

            content: list[ContentBlock] = []
            for p_text in (paras or []):
                content.append(ContentBlock(type="paragraph", text=p_text))

            fig_ids = await browser.evaluate("""
                (secEl) => {
                    return Array.from(secEl.querySelectorAll('img[src*="mediastore"]'))
                        .map(img => img.getAttribute('data-media-id') || img.src)
                        .filter(Boolean);
                }
            """, sec_el)
            for fig_id in (fig_ids or []):
                content.append(ContentBlock(type="figure", figure_id=fig_id))

            if content:
                sections.append(Section(heading=heading, content=content))

        # References
        ref_els = await browser.query_selector_all(
            ".reference-container .reference-item, ol.references li, .refs .reference"
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
                const results = [];
                const allImgs = document.querySelectorAll('img[src*="mediastore"]');
                for (const img of allImgs) {
                    const src = img.src;
                    if (!src || src.includes('icon') || src.includes('logo')) continue;

                    img.scrollIntoView({ behavior: 'instant', block: 'center' });
                    await new Promise(r => setTimeout(r, 300));

                    const fullSizeUrl = src
                        .replace('-small.', '-large.')
                        .replace('-small-', '-large-');
                    const figId = img.getAttribute('data-media-id') || src;

                    const parent = img.closest('div') || img.parentElement;
                    const captionEl = parent?.querySelector(
                        '.figcaption, figcaption, .caption, .fig-caption'
                    ) || parent?.nextElementSibling;
                    let caption = '';
                    if (captionEl) {
                        const text = captionEl.textContent?.trim() || '';
                        if (text.match(/^fig/i) || text.length < 200) {
                            caption = text;
                        }
                    }
                    results.push({ id: figId, url: fullSizeUrl, caption: caption });
                }
                return results;
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
