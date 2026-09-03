# Discovery Protocol

Read for rounds 1–5.

---

## Round 0 — Query expansion

Before any search, generate the query set. A single phrasing finds a single slice of the literature.

Expand along four axes:

**Synonyms and field vocabulary.** The same concept has different names in different fields. "Working memory capacity" and "attentional control" overlap heavily and cite each other rarely. Search both.

**Specificity.** One broad query to map the field, several narrow ones for the specific claim. Broad first, so you learn the vocabulary the field actually uses, then narrow with those terms.

**Method vs phenomenon.** People search for the thing being studied; the paper that answers your question may be indexed under the technique used to study it.

**Language and era.** Foundational work predates current terminology. If the modern term dates from 2015, searching it cannot find the 1994 paper that established the result.

Write the query set down before searching. It becomes the record of search coverage, and a review's search protocol section is built from it.

---

## Round 1 — Discovery

Run the expanded query set against OpenAlex and Semantic Scholar **independently**. Do not merge queries across indexes; run the same queries on each so the comparison is meaningful.

Then compare:

- **In both** → higher confidence the paper is real and central.
- **In one only** → not wrong, but flagged. Verify via Crossref before it enters the ledger.
- **Ranked very differently** → informative. Usually means one index weights citations and the other weights semantic match; the disagreement often surfaces something recent and important.

Log every query and its result count, including zeros. A well-formed query returning nothing is evidence about the field — often the best evidence available for a novelty claim.

---

## Round 2 — Citation expansion

For each central paper, in both directions:

- **References** (backward) → the foundations. This is how you find the paper that established the result, which keyword search buries because its terminology is thirty years old.
- **Cited-by** (forward) → what came after. Replications, extensions, corrections, and rebuttals. The rebuttal is often what you most need and has the fewest citations.

Two passes is usually the right depth. Three explodes and drifts off-topic.

On OpenAlex this is free — singleton lookups are uncapped. Spend here rather than on more searches.

**Watch for citation cartels and single-source cascades.** If forty papers all trace to one primary, you have one piece of evidence with forty citations, not forty pieces of evidence. Trace load-bearing claims back to the primary; a startling number of confident statements in any literature dissolve two or three hops back.

---

## Round 3 — Contradiction

The round that separates a literature review from an advocacy document. Search *against* the thesis:

```
"<claim>" criticism
"<claim>" limitations
"<claim>" failure to replicate
"<claim>" reconsidered
"<claim>" comment on
"<claim>" methodological concerns
"<claim>" no evidence
comment on "<paper title>"
reply to "<author> et al"
```

Also check structurally:

- **Comment/Reply pairs.** Crossref `relation` and `update-to` link them. A paper with a published Comment has been formally challenged.
- **Expressions of Concern and Corrections.** Not retractions, but signals.
- **Registered replications**, especially in psychology and biomedicine.
- **Meta-analyses and systematic reviews** that included the paper — they report effect sizes in context, which often shrinks a headline finding.
- **PubPeer** discussion for contested work.

**Report this round's yield explicitly, including zero.** "Round 3 found no published criticism" is a real finding. Silently producing a source set with no disconfirming evidence tells the reader the field is settled when what actually happened is that nobody looked.

---

## Round 4 — Recency

Filter to the last 1–3 years and search again.

Citation-weighted relevance ranking systematically buries recent work — a 2026 paper has not had time to accumulate citations, so it ranks below a mediocre 2015 paper on the same topic. Recent work is also where a novelty claim is most likely to already be occupied.

Include preprints here, marked as unrefereed. In fast-moving fields the preprint *is* the current state.

---

## Round 5 — Missing literature

Ask, explicitly: what would I expect to exist that I have not found?

- A landmark paper everyone in this field cites?
- A recent review or meta-analysis?
- A registered replication of the central finding?
- A dataset or benchmark paper?
- A dissenting school of thought?
- Work from a different research tradition or a non-English literature?
- A negative result — and if none exists, is that publication bias rather than absence of the effect?

Then search for each specifically. This round catches the gap that isn't visible from inside the source set you already have, and it is the one most often skipped.

---

## Saturation and stopping

Stop when new queries return only papers you already have.

If saturation hasn't happened, do not imply it has. Write down what was and wasn't covered: which indexes, which date range, which languages, how many queries. That record is what makes the search reproducible, and reproducibility is the difference between a search protocol and a bibliography.

Rough calibration: a focused question saturates around 20–40 papers; a broad topic may not saturate at all, in which case scope the question down rather than pretending to comprehensiveness.
