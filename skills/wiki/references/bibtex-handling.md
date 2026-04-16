# BibTeX Handling

## Per-paper .bib files

Every paper has a `raw/bib/<paper-id>.bib` file. Content is either:
- Real BibTeX from the identifier handler (arXiv/DOI/publisher).
- Stub `@misc{...}` with a `% bib-incomplete: true` marker at the top if no real bib was available at ingest time.

Example real entry:
```bibtex
@inproceedings{vaswani2017attention,
  title={Attention is all you need},
  author={Vaswani, Ashish and Shazeer, Noam and others},
  booktitle={Advances in Neural Information Processing Systems},
  year={2017}
}
```

The `@key` field inside the bib is the **citation-key** (BibTeX-native style, `vaswani2017attention`). This is distinct from the `paper-id` (hyphenated, `vaswani-2017-attention`). The paper page frontmatter has both; `bib-file` uses paper-id as the basename.

## Export flow

`/academic-wiki:wiki export-bibtex <selectors>` invokes `scripts/bibtex-export.py` which:
1. Resolves selectors (AND semantics) to a list of paper-ids.
2. Concatenates `raw/bib/<paper-id>.bib` for each.
3. Writes `outputs/bib/YYYY-MM-DD-<label>.bib`.
4. Reports:
   - Successful entries count.
   - Papers with `bib-incomplete: true` flag (need manual fix).
   - Papers missing `.bib` file entirely.

## Common gotchas

- **Numeric-looking strings in frontmatter:** DOIs like `10.1145/3442188.3445922` parse as strings by yaml.safe_load because of the slash. ArXiv IDs like `1706.03762` parse as *floats* if unquoted. Write arxiv IDs as quoted strings in frontmatter: `arxiv: "1706.03762"`.
- **Non-UTF-8 bib files:** Some publisher BibTeX uses Latin-1 for special characters. The export script reads with `errors="replace"` — replacement characters appear as `?`. Fix by re-saving the bib file in UTF-8.
- **Label verbatim:** `--label "My Export"` produces filename `2026-04-16-My Export.bib` (space preserved, only `/\` stripped). This differs from slug-style normalization.

## Fixing bib-incomplete entries

When lint or export reports a `bib-incomplete` paper:
1. Open `raw/bib/<paper-id>.bib` in Obsidian or an editor.
2. Remove the `% bib-incomplete: true` comment line.
3. Fill in the missing fields (title, author, venue, year, DOI, etc.).
4. Save. Next lint/export will no longer flag it.
