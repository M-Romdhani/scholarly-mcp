# Research Protocol

Read during phases 2 (search), 5 (hypotheses), 6 (computation), 7 (mathematics).

---

## Phase 2 — Search and discovery

### Order of attack

1. **Primary literature.** The actual studies. This is where evidence lives.
2. **Reviews and meta-analyses.** Use these for orientation and to *find primaries* — then go read the primaries. A review is weak support for a specific claim because you cannot check what it compressed.
3. **Datasets, code, supplementary material.** Often the only place methods are stated fully enough to evaluate.
4. **Preprints.** Legitimate and often the newest work, but unrefereed. Mark them; weight them accordingly.
5. **Grey literature** (technical reports, theses, standards documents). Sometimes the only source for engineering parameters. Flag the lack of peer review.

### Query design

Vary along three axes, because each finds different papers:

- **Vocabulary.** Fields use different words for the same thing. Search the synonyms; the terminology of an adjacent field often turns up the work that resolves your question.
- **Time.** One recent query, one for foundational work. Recency bias buries the paper that actually settled the question in 1987.
- **Stance.** At least one query written to *disconfirm* the expected answer: "failure of X", "no evidence for X", "X reconsidered", "limitations of X". This is the gate condition for the phase.

Log every query in `search/`, including ones that returned nothing useful. An empty result for a well-formed query is evidence about the field — often the strongest available evidence for a novelty claim.

### When to stop

Stop when new queries return sources you have already seen (saturation), not when you have "enough" citations. If saturation hasn't happened, say so in the limitations: the search was not exhaustive.

Rough calibration: a `brief` needs ~15 sources with ~5 read in full; a `preprint` needs 30–60 with 15+ in full; a systematic review needs a documented, reproducible search protocol with inclusion/exclusion criteria and counts at each stage.

### Verification at retrieval time

For each source, before it enters `sources.json`: confirm it exists (resolve the DOI or fetch the URL), record what you could actually read, and capture the bibliographic fields *from the source*, not from a search snippet. Search result metadata is frequently wrong about year, venue, and author order.

If a source cannot be verified, it does not enter the ledger. There is no "probably fine" tier.

---

## Phase 5 — Hypothesis engine

For each hypothesis, work the chain:

```
Statement
  ↓  What physical/biological/computational process would produce this?
Mechanism
  ↓  If the mechanism is real, what else must be true?
Predictions            (at least one that is not already known to be true)
  ↓
Supporting evidence    (from claims.json)
  ↓
Contradicting evidence (from claims.json — if empty, you didn't look)
  ↓
Competing explanations (at least one, with a discriminating observable)
  ↓
Falsifier              (what observation would kill it)
```

Two checks that catch most bad hypotheses:

**The prediction check.** If every prediction is something already observed, the hypothesis is a restatement, not an explanation. At least one prediction should be currently untested.

**The discriminator check.** For each competing explanation, name the measurement that would distinguish them. If no measurement distinguishes them, the hypotheses are empirically equivalent and the paper must say so rather than pick a favorite on aesthetic grounds.

Beware the mechanism that explains any outcome. Flexibility feels like strength and is the opposite.

---

## Phase 6 — Computational research

Applies whenever the paper reports numbers you produced.

### Before running

- State the question the computation answers and what result would count against the hypothesis. Deciding this after seeing output is how post-hoc rationalization enters.
- Fix and record the seed. Unseeded randomness is unreproducible.
- Write the analysis to a file in `code/`, not into a scratch buffer. The script is an artifact of the paper.

### While running

- Save raw outputs to `data/` before any aggregation. Keep the intermediate.
- Record the environment: language version, key library versions, hardware if performance matters.
- **Record failures.** A run that crashed, a fit that didn't converge, an approach abandoned — all get `status: "failed"` entries in `experiments.json` with a note on why. If three approaches were tried and one worked, the paper reports that, not just the winner. Reporting only the successful run is fabrication by omission, and it is the easiest rule to break without noticing.

### After running

- Re-run at least one key result from a clean state. If it doesn't reproduce, the result is not a result yet.
- Sanity-check against a limiting case or an analytically known answer where one exists.
- Check sensitivity to arbitrary choices (binning, cutoffs, initialization). A result that depends on a choice you made for convenience needs that dependence reported.
- Generate figures from the saved data files, not from variables in memory. This guarantees the figure and the archived data agree.

### If computation is impossible in the environment

Say so plainly and label the work as proposed: "the following analysis would test this; it has not been performed here." Then write the design properly — question, method, expected outcome under each hypothesis. A well-specified proposed experiment is a real contribution. A proposed experiment described in the past tense is fraud.

---

## Phase 7 — Mathematics

### Every equation gets a status

`KNOWN` / `DERIVED` / `CONJECTURE` / `ILLUSTRATIVE` (see `evidence_ledger.md` §5). Record it in `equations.json` and make it unambiguous in the text — "Following [12]," versus "We derive," versus "We conjecture."

### Checks to run on every derived result

**Dimensions.** Both sides must carry the same units. Do this before checking anything else; it catches most algebra errors in seconds.

**Limiting cases.** Set a parameter to zero, one, or infinity and check the result reduces to something known. A derivation that fails a limiting case is wrong no matter how clean it looks.

**Symmetry.** If the problem has a symmetry, the answer should respect it or the breaking should be explicable.

**Magnitude.** Plug in real numbers. If the answer is 10^40 when it should be order unity, stop.

**Numerical spot-check.** Where a closed form exists, evaluate it numerically against a direct computation at a few parameter values. This is cheap and catches sign and factor errors that survive every other check.

### Presentation

- Define every symbol at first use, and keep a notation table if there are more than ~15.
- Notation must be consistent across the whole paper — one symbol, one meaning. Reusing a symbol across sections is a reliable way to make a correct paper unreadable.
- Show the derivation steps that carry information; move routine algebra to an appendix.
- State assumptions where they are used, not only in a list at the start. An approximation invoked in step 4 should be visible at step 4.
- Statistical results need the test, the assumptions it requires, whether those were checked, effect size, and uncertainty — not just a p-value. If assumptions were not checked, say so.
