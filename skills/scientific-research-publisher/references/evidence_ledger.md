# Evidence Ledger

Read during phases 3–4 (source triage, ledger construction) and again at phase 10 (citation audit).

The ledger exists because provenance decays. A model that reads twenty papers and then writes ten pages cannot reliably recall which paper supported which sentence — and will confabulate the mapping rather than admit the gap. Writing the ledger first makes the mapping a lookup instead of a recollection.

---

## 1. sources.json

One entry per retrieved source. Never add an entry for something you have not actually opened.

```json
{
  "id": "S07",
  "type": "journal-article",
  "authors": ["Kivelson, S. A.", "Fradkin, E."],
  "year": 2003,
  "title": "Electronic liquid-crystal phases of a doped Mott insulator",
  "venue": "Nature",
  "volume": "393",
  "pages": "550-553",
  "doi": "10.1038/31177",
  "url": "https://doi.org/10.1038/31177",
  "retrieved": "2026-09-02",
  "retrieval_method": "web_fetch",
  "access": "fulltext",
  "evidence_class": "primary-theory",
  "quality_notes": "Analytical treatment; assumptions stated in Sec. II. No experimental validation in this paper.",
  "scope_limits": "2D, weak-coupling regime only",
  "bibtex_key": "kivelson2003electronic"
}
```

**Fields that matter most and are most often skipped:**

- `access` — one of `fulltext`, `abstract-only`, `preprint-version`, `secondhand`. This is not bookkeeping. A claim resting on an abstract is materially weaker: abstracts overstate, omit conditions, and drop sample sizes. If everything supporting your central claim is `abstract-only`, the paper has a hollow core and must say so.
- `retrieval_method` — how you actually got it. `web_search snippet` is not the same as `web_fetch` of the paper.
- `scope_limits` — the conditions under which the finding holds. This is what stops "shown in mice" becoming "shown".
- `evidence_class` — `primary-experimental`, `primary-theory`, `primary-computational`, `review`, `meta-analysis`, `preprint`, `dataset`, `grey-literature`. Reviews are for orientation and for finding primaries; they are weak support for specific claims.

**`secondhand` deserves special caution.** If source A describes what source B found and you cannot reach B, the claim is attributed to A's *reading* of B, and the ledger must say so. Citation chains propagate errors; a startling number of confident claims in the literature trace to a misreading three hops back.

---

## 2. claims.json

The central object. Every substantive sentence in the manuscript traces to one of these.

```json
{
  "id": "C12",
  "text": "Stripe order suppresses the superconducting transition temperature in the 1/8-doping regime.",
  "provenance": "S",
  "support": [
    {"source": "S07", "locator": "Sec. III, Fig. 2", "strength": "direct",
     "what_it_says": "Reports Tc suppression at x=0.125 in LBCO."}
  ],
  "contradicts": [
    {"source": "S14", "locator": "Fig. 4b",
     "what_it_says": "No suppression observed in LSCO at comparable doping.",
     "resolution": "Material-dependent; claim narrowed to LBCO-type systems."}
  ],
  "confidence": "moderate",
  "used_in": ["intro", "discussion"],
  "status": "verified"
}
```

### The provenance tag

| Tag | Test | Grammar required in prose |
|-----|------|---------------------------|
| `[S]` | Could you point at a sentence, figure, or table in a source that states this? | Declarative + citation |
| `[I]` | Does this require combining sources, or reasoning beyond what any one states? | Hedged: "this suggests", "taken together", "implies" |
| `[P]` | Is this yours — a hypothesis, a novel mechanism, an interpretation? | Explicit: "we propose", "one possibility is" |

The boundary between `[S]` and `[I]` is where papers go wrong, so bias toward `[I]`. Specifically:

- A source shows X in condition A; you claim X. → `[I]`, not `[S]`. Generalization is inference.
- A source shows correlation; you claim mechanism. → `[I]` at best.
- Two sources each show half of your claim. → `[I]`. Neither states it.
- A source's discussion section speculates about X; you claim X. → `[I]`, and note that the source itself was speculating.
- A review says "it is well established that X" without citing a primary. → `[I]` until you find the primary. This one catches a lot.

**`what_it_says` is mandatory and must be in the source's terms, not yours.** Writing it forces the check. If you cannot state what the source says without importing your conclusion, the claim is `[I]`.

### Locators

`"locator": "the paper"` is not a locator. Use section, figure, table, equation, or page. At phase 10 you will re-open each source and check the locator; vague locators make that impossible and are usually a sign the claim was written from memory.

### Confidence

`high` — multiple independent primaries, direct measurement, no contradicting evidence found.
`moderate` — single good primary, or several consistent but indirect.
`low` — indirect, contested, abstract-only, or small/narrow studies.
`contested` — credible sources disagree. This is *reportable content*, not a problem to hide: say who disagrees and why.

A `low` or `contested` claim can appear in the paper. It cannot appear in the abstract as a finding.

---

## 3. hypotheses.json

```json
{
  "id": "H2",
  "statement": "Charge-order fluctuations mediate the pairing interaction.",
  "mechanism": "Soft collective mode couples to fermions near the antinode, enhancing the pairing vertex.",
  "predictions": [
    "Tc peaks near the charge-order quantum critical point.",
    "Isotope effect is suppressed relative to phonon-mediated pairing."
  ],
  "supporting": ["C12", "C19"],
  "contradicting": ["C31"],
  "competing_explanations": [
    {"statement": "Spin-fluctuation mediated pairing.",
     "discriminator": "Momentum dependence of the gap anisotropy differs; measurable by ARPES."}
  ],
  "falsifier": "Observation of maximal Tc far from the charge-order QCP in a clean system.",
  "status": "open"
}
```

A hypothesis without a `falsifier` is not a hypothesis and does not go in the paper as one. If you cannot write one, say what would have to be true for the statement to be testable at all.

---

## 4. experiments.json

**An entry is created only after execution.** Planned work goes in `PROJECT.md`, not here.

```json
{
  "id": "E03",
  "question": "Does the fitted exponent depend on binning choice?",
  "script": "code/exponent_fit.py",
  "commit_or_hash": "sha256:9f2c...",
  "params": {"bins": [20, 50, 100], "seed": 20260902},
  "environment": {"python": "3.11.6", "numpy": "1.26.4"},
  "executed_at": "2026-09-02T14:03:11Z",
  "outputs": ["data/exponent_fit_results.json", "figures/fig3_exponent.png"],
  "result_summary": "Exponent stable at 1.84 +/- 0.06 across binning; no dependence detected.",
  "status": "completed"
}
```

Failed and abandoned runs get entries with `status: "failed"` and a note on why. This is not paperwork — selective reporting of only the runs that worked is the mechanism behind a large share of irreproducible literature, and it is trivially easy to do by accident when an agent retries until something looks clean.

---

## 5. equations.json

```json
{
  "id": "eq:entropy",
  "latex": "S = k_B \\ln \\Omega",
  "status": "KNOWN",
  "source": "S02",
  "symbols": {"S": "entropy [J/K]", "k_B": "Boltzmann constant [J/K]", "\\Omega": "number of microstates [dimensionless]"},
  "derivation": null,
  "checks": {"dimensional": "pass", "limiting_case": "Omega=1 gives S=0, correct"}
}
```

Status values: `KNOWN` (established, cite it) / `DERIVED` (worked out here — show the derivation or put it in an appendix) / `CONJECTURE` (proposed, unproven) / `ILLUSTRATIVE` (schematic, not exact — say so in the caption).

An unlabeled equation reads as established. Silently presenting a conjecture in the typography of a known result is a form of the same failure as an untagged `[I]` claim.

---

## 6. artifacts.json — figures and tables

```json
{
  "id": "fig3",
  "kind": "figure",
  "caption": "Fitted exponent versus binning resolution. Error bars are 1 sigma from bootstrap (n=1000).",
  "generated_by": "code/exponent_fit.py",
  "data_source": "data/exponent_fit_results.json",
  "experiment": "E03",
  "variables": {"x": "bin count [dimensionless]", "y": "exponent [dimensionless]"},
  "alt_text": "Scatter plot showing exponent near 1.84 across all three binning choices, with overlapping error bars.",
  "referenced_in": ["results"]
}
```

Rules that follow from rule 3 in SKILL.md:

- Every figure has a `data_source` file that exists. No `data_source`, no figure.
- Never draw a schematic that could be mistaken for data. If it is a cartoon, the caption says so and the styling makes it obvious (no axis ticks implying measurement).
- `alt_text` is not decoration — write it, both for accessibility and because a figure you cannot describe in one sentence is probably doing too much.
- Every artifact is referenced in the text. An unreferenced figure is either unnecessary or the text has a gap.

---

## Auditing the ledger before writing

Before phase 9, walk the ledger and answer:

1. Which claims are load-bearing for the conclusion? Are any of them `low` confidence or `abstract-only`?
2. Is any `[I]` claim doing the work of an `[S]` claim in the argument?
3. Are all contradictions resolved, narrowed, or explicitly reported as unresolved?
4. Is there a claim with no `used_in`? Either it belongs somewhere or it was gathered for a question the paper no longer asks.
5. Is the novelty claim in `PROJECT.md` still true given what the search turned up?

Question 5 is the one that gets skipped and the one most likely to sink the paper at review.
