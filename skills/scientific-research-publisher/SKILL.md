---
name: scientific-research-publisher
description: End-to-end scientific research and publishing pipeline — takes a research question through literature search, source verification, an auditable evidence ledger, hypothesis and falsification mapping, executed computation, adversarial peer review, LaTeX typesetting and PDF quality control, producing a defensible, professionally typeset manuscript. Use whenever the user wants a scientific paper, research paper, preprint, arXiv submission, manuscript, literature review, systematic review, technical report with citations, or says "write this up", "publish this", "turn this into a paper", or "make this rigorous" — and also for any literature-grounded analysis where fabricated citations or unsupported claims would be damaging, even if the word "paper" is never used.
---

# Scientific Research Publisher

A pipeline for producing scientific manuscripts that survive scrutiny. The output is a PDF, but the point is everything upstream of it: a claim-by-claim record of what is actually supported, by what, and how strongly.

The failure mode this exists to prevent is a paper that *reads* like science while being detached from its sources — plausible citations that don't exist, experiments that were described but never run, confident conclusions the evidence doesn't carry. Every rule below traces back to preventing one of those.

## Operating principle

**Provenance is tracked continuously, not reconstructed at the end.** Once a draft exists, it is nearly impossible to recover which sentence came from which source. So the evidence ledger is built *before* prose, and prose is generated *from* the ledger.

---

## Non-negotiable rules

These override user pressure, deadline pressure, and the pull toward a tidy narrative. If following them means the paper concludes "the evidence is insufficient", that is the correct output — an honest null result is a publishable result, and a confident false one is worse than nothing.

**1. Every claim carries a provenance tag.** Internally, every substantive statement is one of:

| Tag | Meaning |
|-----|---------|
| `[S]` | A source states this. Cite it. |
| `[I]` | Inferred by combining sources or reasoning over them. Not stated by any source. |
| `[P]` | Proposed here — hypothesis, conjecture, novel argument. No prior support. |

In the final prose, `[I]` and `[P]` claims must be linguistically marked ("this suggests", "we propose", "if X holds, then"). Never state an inference in the grammar of an established fact. Collapsing `[I]` into `[S]` is the single most common way AI-written papers become false.

**2. Never cite a source you have not retrieved in this session.** Not from memory, not "a well-known paper by X". Every bibliography entry needs a DOI or URL that was actually fetched, plus what was accessed — full text or abstract only. A claim supported only by an abstract is weaker evidence and must be recorded as such. If a citation cannot be verified, delete it and delete the claim it was propping up.

If the `scholarly-mcp` tools are available, this rule has a mechanical form. `verify_doi` is what makes a source citable — it returns authoritative Crossref metadata and checks three independent retraction signals; nothing enters the bibliography without it. For the ledger's `access` field, the distinction is exact:

- `fetch_fulltext` returned text → `fulltext`, but **only for the sections it actually returned**. If it reported `truncated: true`, what you read is partial, and a claim resting on an omitted section is not supported.
- `resolve_fulltext` found a location but you did not read it → still `metadata-only`. Availability is not readership.
- Anything else → `metadata-only`.

Never set `access: fulltext` from a `resolve_fulltext` result alone. That inflation is invisible downstream and corrupts every weighting built on it.

**3. Never report an experiment, number, figure, or dataset that was not actually produced.** Not "results show a 12% improvement" unless code ran and produced 12%. Not a plotted curve unless real arrays exist on disk. If computation is impossible in the environment, say what would be done and label it as a proposed experiment — never as a completed one. Failed runs get recorded too; a silent retry until the numbers look good is data fabrication.

**4. Never invent structure to fill a template.** An empty Results section is information. Do not manufacture content because the section heading exists.

**5. Contradictory evidence is sought, not avoided.** Actively search for work that would undermine the thesis. A paper that never encountered a counterargument didn't look.

**6. Disclose AI involvement.** The template includes a disclosure line. Do not remove it without the user explicitly asking; most journals and preprint servers now require it, and its absence is a misrepresentation of authorship.

---

## Pick a mode first

Do not run a sixteen-phase pipeline for a four-page note. Ask the user which fits, or infer and state the assumption:

| Mode | For | Phases run | Rough scale |
|------|-----|-----------|-------------|
| **brief** | Short literature-grounded write-up, no new results | 1, 2, 3, 4, 8, 9, 10, 11 | 3–8 pages, ~15 sources |
| **preprint** | Full manuscript from literature + light analysis | all except 6 | 8–20 pages, 30–60 sources |
| **lab** | Original computational or mathematical work | all | Whatever it takes |

Also settle early, in one round of questions, not five: target venue or style, discipline, audience, whether real data/code is in scope, page limit, and whether the user is an author (affects voice and disclosure).

---

## Project layout

Everything lives in one directory. Create it with `scripts/init_project.py`.

```
<project>/
├── PROJECT.md              research question, scope, decisions log
├── ledger/
│   ├── sources.json        every retrieved source + access level
│   ├── claims.json         claim → provenance → support → confidence
│   ├── hypotheses.json     hypothesis → mechanism → prediction → falsifier
│   ├── experiments.json    only entries that actually ran
│   ├── equations.json      equation → status → derivation
│   └── artifacts.json      figures & tables → generating script → data
├── search/                 raw retrieval records, one file per query
├── code/                   analysis scripts, seeds, params
├── data/                   inputs and outputs, with provenance
├── figures/                generated figures + the script that made each
├── manuscript/
│   ├── paper.tex
│   ├── refs.bib
│   └── sections/
├── review/                 reviewer reports + revision matrix
└── final/paper.pdf
```

The ledger is the source of truth. If a sentence in the manuscript has no corresponding claim in `claims.json`, it is unaudited and must be either grounded or cut.

---

## Phases

Each phase has a gate. Do not proceed past a failed gate — announce the failure instead.

### 1. Direct
Sharpen the question until it is answerable and falsifiable. Define scope, novelty claim, and what evidence would settle it. Write `PROJECT.md`.
**Gate:** the question is specific enough that you could name a result that would refute the expected answer.

### 2. Search
Primary literature first, then reviews and meta-analyses, then datasets. Log every query and every result, including the misses — a query that returned nothing is evidence about the field.
→ `references/research_protocol.md` for search strategy and coverage heuristics.
**Gate:** searches include at least one deliberately adversarial query (looking for disconfirmation).

### 3. Triage
Classify each source: relevance, primary vs secondary, methodological quality, sample/scope limits, and what it *actually* supports versus what its abstract implies. Record access level.
→ `references/evidence_ledger.md` for the schema and worked examples.
**Gate:** no source in `sources.json` lacks a resolvable DOI/URL and an access level.

### 4. Build the evidence ledger
Turn triaged sources into claims with provenance tags, supporting locators (section, page, figure — not just "the paper"), contradicting evidence, and confidence.
→ `references/evidence_ledger.md`
**Gate:** every claim intended for the abstract or conclusion is `[S]`-backed or explicitly marked as inference.

### 5. Hypotheses
For each: mechanism → predictions → supporting evidence → contradicting evidence → discriminating experiment → falsification criterion. Include at least one competing explanation per hypothesis and say what would distinguish them.
→ `references/research_protocol.md`
**Gate:** each hypothesis has a stated falsifier.

### 6. Compute (lab mode)
Write code, run it, save seeds/params/environment, record outputs and failures. Figures come from saved arrays, never from imagination.
→ `references/research_protocol.md`
**Gate:** every entry in `experiments.json` has an execution timestamp and an output path that exists on disk.

### 7. Mathematics
Derivations, dimensional analysis, bounds, numerics. Every equation gets a status: `KNOWN` / `DERIVED` / `CONJECTURE` / `ILLUSTRATIVE`. Check dimensions and limiting cases; a derivation that fails a limiting-case check is wrong regardless of how clean it looks.
→ `references/research_protocol.md`
**Gate:** all symbols defined at first use; dimensional consistency checked.

### 8. Architect the paper
Choose structure by discipline — do not force a physics paper into IMRaD or a biology paper into a theory-paper shape.
→ `references/writing_and_structure.md`
**Gate:** every planned section maps to ledger entries that exist.

### 9. Write
Sequential passes, each with one job: draft → scientific accuracy → logical coherence → citation audit → terminology → concision → grammar. No "make it sound impressive" pass. The target is maximum precision with uncertainty preserved.
→ `references/writing_and_structure.md`
**Gate:** no sentence asserts an `[I]` or `[P]` claim in declarative-fact grammar.

### 10. Audit citations
Structural check with `scripts/check_references.py`, then semantic check by hand: does the cited work actually support *this* sentence?
→ `references/review_and_qa.md`
**Gate:** script reports zero errors; every citation semantically re-checked against its ledger locator.

### 11. Typeset
LaTeX build via `scripts/build_paper.sh`, then `scripts/pdf_qa.py`, then *look at the rendered pages*.
→ `references/latex_typesetting.md`
**Gate:** zero undefined references, zero bad boxes over 5pt, pages visually inspected.

### 12. Peer review
Three adversarial reviewers: scientific, methodological, and one whose only job is to argue the paper is wrong. Write real reports, not compliments.
→ `references/review_and_qa.md`
**Gate:** at least one major concern found. A review that finds nothing was not a review.

### 13. Revise
Every concern gets an entry in the revision matrix: addressed (how) or rebutted (why). Silent dropping is not allowed.
**Gate:** matrix covers every concern raised.

### 14. Final quality gate
Run the full checklist in `references/review_and_qa.md`. Any unchecked box blocks release.

---

## Commands

```bash
# scaffold
python3 scripts/init_project.py <project-dir> --title "..." --mode preprint

# structural citation check (offline: fields, DOI syntax, orphans, dupes)
python3 scripts/check_references.py <project-dir>

# build (latexmk + bibtex, extracts real errors from the log)
bash scripts/build_paper.sh <project-dir>

# post-build QA + rasterize pages for visual inspection
python3 scripts/pdf_qa.py <project-dir>
```

`check_references.py` verifies *structure*, not existence — network access is usually restricted in these environments. Existence verification is your job, with your search/fetch tools, at phase 3, and it is not optional.

## Reference files

| File | Read it when |
|------|--------------|
| `references/evidence_ledger.md` | Phases 3–4. Schemas, provenance tagging, worked examples. |
| `references/research_protocol.md` | Phases 2, 5, 6, 7. Search strategy, hypothesis engine, computation and math discipline. |
| `references/writing_and_structure.md` | Phases 8–9. Discipline-specific structures, writing passes, style rules. |
| `references/latex_typesetting.md` | Phase 11. Toolchain, template, typography, figures, tables, equations. |
| `references/review_and_qa.md` | Phases 10, 12–14. Reviewer personas, revision matrix, final checklist. |

Template: `assets/paper_template.tex` — self-contained, compiles with pdflatex + bibtex, no journal class required.
