# Promotion Rules

Default `compile` detects cross-paper claim/result candidates but **does not auto-promote**. Candidates are written to `outputs/reports/YYYY-MM-DD-promotion-candidates.md` for explicit user action. This step is skipped when `compile --paper-only` is used.

## Detection heuristic

For each claim or result drafted inline in a newly-compiled paper page:

1. Search existing paper pages' `## Claims` and `## Results` sections for text that is **semantically equivalent** (LLM judgment, NOT regex). Two statements are equivalent when:
   - They describe the same underlying assertion despite different wording.
   - Examples of equivalence:
     - "attention is quadratic in sequence length" ≈ "self-attention complexity grows as O(n²)"
     - "RSMA outperforms NOMA under imperfect CSI" ≈ "rate-splitting surpasses non-orthogonal MA when CSI is noisy"
   - Examples of non-equivalence (do NOT promote):
     - "attention helps translation" vs "attention is quadratic" — different claims
     - "X is faster than Y by 10%" vs "X is faster than Y by 30%" — **do NOT merge into a single claim/result page**. These are conflicting quantitative findings that require manual resolution. Instead:
       - Keep them as separate inline claims in each paper page.
       - Add a `> [!WARNING] Contradiction with [[other-paper-id]]` callout in each paper, pointing at the other.
       - Write a candidate entry in `outputs/reports/*-promotion-candidates.md` of type `contested` (not a normal claim/result) so the user can review and decide how to represent the disagreement. Flag it explicitly as `**Contradiction, not equivalence**` in the candidate body.

**Contradiction rule:** When detecting semantic equivalence, always check if the statements disagree on quantity, direction, or substantive detail. If they disagree, treat as a contradiction — route to the "contested candidate" flow described at the end of this section, not the normal equivalence-promotion flow.

2. If ≥1 equivalent match is found, write a candidate entry to `outputs/reports/YYYY-MM-DD-promotion-candidates.md`:

    ```markdown
    ## Candidate: <proposed-slug>

    **Type:** claim | result
    **Sources:** [[<paper-id-1>]], [[<paper-id-2>]]
    **Statement:** <one-paragraph synthesis of the shared claim/result>
    **Evidence (paper 1):** <excerpt from paper 1's Claims/Results section>
    **Evidence (paper 2):** <excerpt from paper 2's Claims/Results section>

    **To promote:** Run `/academic-wiki:wiki query "promote candidate <proposed-slug>"` or accept during the next relevant query.
    ```

    `<proposed-slug>` is derived via `academic_wiki_lib.slug.make_slug` from the statement text.

3. Do NOT modify the paper pages during detection — the inline claims/results stay. Promotion happens later via an explicit user action.

## Promotion flow (user-triggered)

When the user accepts a candidate (via `query` promotion prompt or a future `promote` command):

1. Read the candidate from `outputs/reports/*-promotion-candidates.md`.
2. Create `wiki/claims/<slug>.md` or `wiki/results/<slug>.md` per spec §3.1:
   - Frontmatter per §3.1 entity-type schema with `sources:` listing all paper-ids, `status` inferred (`replicated` if ≥2 sources agree; `contested` if sources disagree; `preliminary` if only 1 source).
   - Body sections per the entity's template (Claim: `Statement` / `Evidence For` / `Evidence Against` / `Open Questions` / `See Also`; Result: `Statement` / `Evidence` / `Conditions` / `Caveats` / `See Also`).
3. In each contributing paper page (the ones listed in `sources:`), replace the inline claim/result prose with a `[[wikilink]]` to the new page. Add the brief context as backlink on the new page.
4. Remove the candidate entry from `outputs/reports/*-promotion-candidates.md` (or mark it `status: promoted`).
5. Append to `log.md`: `## [YYYY-MM-DD] promote | <slug> to claim|result`.
6. Commit in the wiki's own git repo.

## Non-goals

- Automatic promotion — NEVER. Every promotion requires explicit user action.
- Automatic merging of "close-but-not-equivalent" candidates — the threshold is strict semantic equivalence.
- Retroactive promotion of claims/results that exist in the paper bodies from prior compile runs — detection only fires on newly-compiled papers. Users can trigger detection manually by re-compiling.
