# Citation Audit, Peer Review, and the Final Gate

Read during phases 10, 12, 13, 14.

---

## Phase 10 — Citation audit

Two layers. The script does the first; only you can do the second.

### Structural (automated)

```bash
python3 scripts/check_references.py <project-dir>
```

Checks: required fields present, DOI syntax valid, no duplicate entries, no cite keys without bib entries, no bib entries without citations, keys consistent with convention, every entry has a retrieval record in `sources.json`.

### Semantic (manual — the one that matters)

For every citation in the manuscript, with the source's ledger locator open:

1. **Does the cited work support *this specific sentence*?** Not the general topic — this claim. Topic-adjacent citation is the most common failure and it is invisible to any script.
2. **Is the scope right?** If the source studied 200 undergraduates and the sentence says "people", the citation doesn't support it as written.
3. **Is the direction right?** Effect signs get flipped when compressing a result into a clause.
4. **Is a `[S]` tag still correct** after the sentence's final wording? Phrasing drifts across seven writing passes; a claim that was `[S]` in the draft can quietly become `[I]`.
5. **Is the number right?** Re-check every figure against the source, not against your earlier draft.

Any citation you cannot confirm gets deleted, along with the claim it supported. This is not a loss — an unsupported sentence was never carrying information.

### Provenance audit — five checks a script cannot do and a self-review will skip

These exist because each one has already let a wrong statement through a report that looked careful.

**1. Re-run every search that was recorded as returning nothing.** A recorded null is a claim about the literature, and it is the least reliable claim in the document, because it is indistinguishable from a badly phrased query. Reformulate at least twice — different vocabulary, the mechanism rather than the topic, Greek letters spelled both ways — before letting "we could not find X" stand. Observed: a review reported that a search for an artefact argument "returned nothing usable" and dropped the argument; the paper was at rank 1 under different phrasing, and another review built a section on it. If a re-query finds the paper, the null was never a finding about the field — it was a finding about the query.

**2. Compare the reference titles in the manuscript against the titles independently verified from Crossref.** Not the DOIs — the *titles*. A DOI that resolves proves the identifier is real; it does not prove it was attached to the right reference. Mismatches here are how a genuine DOI ends up on a claim it does not support, which is the single hardest citation failure for a reader to detect.

**3. Audit every access claim against what was actually retrieved.** For each source recorded as `fulltext`, confirm body text was obtained, not an abstract, a landing page, or a metadata record. Availability is not readership: a resolver reporting that an open-access copy exists is not evidence anyone read it. Any quantitative value attributed to a source read only as an abstract should be treated as fabricated until traced.

**4. If any source is retracted, corrected, or under an expression of concern, screen its lineage before continuing.** Retractions cluster by laboratory. Expanding citations is not sufficient on its own — `cited_by` ranks by citation count, so low-cited retracted follow-ups sit outside the window at any limit. Search the authors by name and search the retraction coverage itself. Observed: a review that screened only the retracted paper it happened to find reported two compromised sources; a lineage search on the same topic found five.

**5. Check every structural or mechanistic claim against the actual evidence, not against plausibility.** "Distal from the binding interface", "buried at the interface", "solvent-exposed" are measurements, not adjectives. If coordinates were not examined, the claim is an inference and must be written as one. Observed: a report asserted a mutation was distal from an epitope; measured against the deposited structure it was a direct contact at 3.9 Å.

---

## Phase 12 — Adversarial peer review

Write three real reports to `review/`. The purpose is to find what is wrong while it is still cheap to fix. A review that returns compliments has failed at its only job, so the gate is: **at least one major concern, or the review is redone.**

Do this after the paper is complete but before the final build. Read the manuscript as a hostile stranger who has not seen the ledger.

### Reviewer A — Scientific validity

> Is the science correct?

- Are the claims supported by the evidence presented?
- Are there errors in the mathematics, the physics, the biology?
- Is prior work represented accurately?
- Are the mechanisms plausible, and are they distinguished from correlations?
- Is anything asserted that the cited sources don't actually say?

### Reviewer B — Methodological

> Could the conclusions be artifacts?

- Do the methods answer the question asked?
- Is the sample, dataset, or parameter range adequate?
- Are controls and baselines appropriate?
- Are the statistics right, and are their assumptions met and checked?
- Does the result survive reasonable alternative analysis choices?
- Is there enough detail to reproduce this?
- Could the result be an artifact of selection, instrumentation, preprocessing, or multiple comparisons?

### Reviewer C — Adversarial

**Review from outside the process that produced the work.** A reviewer that reuses the gathering step's queries, its source set and its assumptions will reproduce its blind spots and return a clean report. Re-query independently, and treat the existing bibliography as a hypothesis about what the literature contains rather than as the literature.

> What is the strongest argument that this entire paper is wrong?

Not nitpicks. The load-bearing attack:

- What is the single weakest assumption, and what happens if it fails?
- What alternative explanation accounts for everything reported, more simply?
- What would a domain expert who dislikes this thesis say first?
- Is the novelty claim actually true, or has this been done?
- Is the effect large enough to matter even if real?
- What evidence is conspicuously missing — and would it have been reported had it been favourable?

### Report format

Each report lists concerns in these categories, with severity `major` / `minor`:

```
Major concerns
Minor concerns
Unsupported claims          (with the sentence quoted)
Missing citations
Weak assumptions
Alternative explanations
Statistical problems
Mathematical problems
Overclaims                  (with the sentence quoted)
Reproducibility problems
Presentation problems
```

Quote the offending sentence. "The discussion overclaims" is not actionable; "line 3 of §4.2 states X where the evidence supports only Y" is.

---

## Phase 13 — Revision

Every concern gets a row. Nothing is dropped silently.

| ID | Reviewer | Severity | Concern | Action | Where |
|----|----------|----------|---------|--------|-------|
| R-01 | C | major | Novelty claim overlaps Zhang 2024 | Narrowed contribution claim; added comparison paragraph | §1, §3.2 |
| R-02 | A | major | Causal language unsupported by design | Rewrote as association; added confound discussion | §5.1 |
| R-03 | B | minor | Seed not reported | Added to Methods | §3.1 |
| R-04 | A | minor | Suggests citing Okoye 2019 | **Rebutted:** different regime (high-T), not applicable | — |

Rebuttals are legitimate but must state the reason. "Rebutted: disagree" is not a rebuttal.

After revision, re-run phases 10 and 11. Revision introduces new citations and new bad boxes; the audit and build must be redone, not assumed.

---

## Phase 14 — Final quality gate

Publication is blocked until every box is checked. If a box cannot be checked, report which one and why rather than shipping.

### Scientific integrity
- [ ] No fabricated sources — every entry retrieved and recorded
- [ ] No fabricated experiments — every reported run has an execution record and outputs on disk
- [ ] No fabricated data — every number traces to a source or a computation
- [ ] No unsupported conclusions
- [ ] Hypotheses labelled as hypotheses
- [ ] Speculation labelled as speculation
- [ ] Limitations stated specifically
- [ ] AI involvement disclosed

### Evidence
- [ ] Every major claim has support in `claims.json`
- [ ] Contradictory evidence sought and addressed
- [ ] Primary sources used for load-bearing claims
- [ ] Abstract-only sources not carrying central claims
- [ ] Every citation semantically verified against its locator
- [ ] Novelty claim still true given the search

### Mathematics
- [ ] Equations dimensionally checked
- [ ] Limiting cases checked
- [ ] Every symbol defined at first use
- [ ] Notation consistent throughout
- [ ] Derived results distinguished from established ones
- [ ] Statistical assumptions stated and checked

### Reproducibility
- [ ] Code preserved in `code/`
- [ ] Parameters and seeds recorded
- [ ] Data provenance recorded
- [ ] Key result re-run from clean state
- [ ] Failed and abandoned runs recorded
- [ ] Environment versions noted

### Publishing
- [ ] Figures and tables numbered and referenced in text
- [ ] Captions self-contained
- [ ] Every reference cited; every citation resolved
- [ ] Cross-references all resolve (no `??`)
- [ ] No orphan headings or stranded lines
- [ ] No overfull boxes > 5pt
- [ ] Typography consistent
- [ ] **PDF pages visually inspected as images**

### Honest reporting to the user
- [ ] Stated which claims are weakest and why
- [ ] Stated what could not be verified
- [ ] Stated what would change the conclusion

That last block is the one to actually write out in the response. The user needs to know where the soft spots are — a paper delivered with "here are the three claims I'd attack first if I were reviewing this" is far more useful than one delivered with "done".
