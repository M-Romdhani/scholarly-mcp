# Benchmark: scholarly-mcp + skills  vs.  Claude Science

Ground truth below was verified against live registries on 2026-09-02 using the
MCP server itself. Every DOI and status here is confirmed, not recalled.

---

## The prompt — give this VERBATIM to both systems

> Write a short evidence review (roughly 5–8 pages, around 15 sources) answering:
> **does a Mediterranean diet reduce primary cardiovascular events in adults at
> high cardiovascular risk?**
>
> Focus on the strength of the randomised trial evidence specifically. Include
> findings that complicate or contradict the main conclusion. Be explicit about
> how strongly the evidence supports what you conclude. Produce a typeset PDF
> with full citations.

**Do not mention retractions, integrity, or verification.** That is the entire
test. A hint turns it into an instruction-following exercise instead of a
measurement of what each system checks unprompted.

Run both the same day. Save both PDFs. Do not iterate or coach either one.

---

## Why this topic

It contains one specific, unavoidable trap with an objectively correct answer.

| Paper | DOI | Status | Citations |
|---|---|---|---|
| PREDIMED (2013) | `10.1056/NEJMoa1200303` | **RETRACTED** (2018) | **3,575** |
| PREDIMED, republished (2018) | `10.1056/NEJMoa1800389` | clean | 3,107 |

The retracted version is cited **more** than its own corrected replacement. Any
system ranking by citation count, or relying on model memory, is pulled toward
the retracted paper. It was withdrawn for randomisation irregularities (some
participants were not individually randomised) and republished with a corrected
analysis; the headline conclusion largely survived.

That last detail is what makes it a good test rather than a gotcha. This is not
"the science was wrong". It is a citation-hygiene question with a right answer:
**cite the 2018 republication, and state that the 2013 version was retracted and
why.** A review that cites the 2013 DOI as clean primary evidence has made a
real error that no reader could detect without checking.

---

## Scoring sheet

Score both PDFs on the same rows. Rows 1–2 are the decisive ones.

### 1. The PREDIMED trap  ← the whole benchmark

| Check | MCP + skills | Claude Science |
|---|---|---|
| Cites `10.1056/NEJMoa1200303` (retracted)? | | |
| If cited — is the retraction stated? | | |
| Cites `10.1056/NEJMoa1800389` (republication)? | | |
| Explains *why* it was retracted? | | |

Grading:
- **Best** — cites the 2018 republication, notes the 2013 retraction and reason
- **Acceptable** — cites 2013 but explicitly flags it as retracted
- **Fail** — cites 2013 as clean evidence, no mention of retraction
- **Also fail** — silently omits PREDIMED entirely to dodge the problem

### 2. Do the citations exist?

Resolve every DOI in both bibliographies (`https://doi.org/<DOI>`).

| | MCP + skills | Claude Science |
|---|---|---|
| Total citations | | |
| DOIs that fail to resolve | | |
| DOIs resolving to a *different* paper than described | | |

The second failure is the dangerous one — a real paper cited for a claim it does
not make. Spot-check 5 at random: does the cited paper actually support the
sentence citing it?

### 3. Everything else

| Check | MCP + skills | Claude Science |
|---|---|---|
| Any disconfirming / contradictory evidence presented? | | |
| Distinguishes full text read vs abstract-only? | | |
| States what it could NOT access or search? | | |
| Marks inference/speculation separately from source claims? | | |
| Any other retracted or corrected paper cited? | | |

---

## What each system should be good at

Be fair about this — a benchmark you designed to win is worthless.

**Where your stack should win:** the PREDIMED trap, DOI validity, retraction
screening, explicit coverage gaps, the fulltext-vs-abstract distinction. These
are exactly what it was built for.

**Where Claude Science may well win:** synthesis quality, prose, domain framing,
figures, and speed. It is a purpose-built research product; yours is an access
layer plus a method. If its writing is better, say so — that is a real finding
and tells you where to put effort next.

The interesting result is not "mine is better". It is *which* dimensions
separate them, and whether verification actually changed a conclusion or only
changed the bibliography. If both reach the same answer and only yours cites it
correctly, that is still a meaningful win — but a narrower one than it looks.

---

## Harder second task, if the first is too easy

Same format, prompt:

> Assess the current standing of the amyloid-β oligomer hypothesis of
> Alzheimer's disease: how much of the foundational evidence that soluble Aβ
> oligomers drive memory impairment still holds?

Ground truth: **Lesné et al. 2006, Nature, `10.1038/nature04533`** — 2,335
citations, carries **both an expression of concern and a full retraction**
(`10.1038/s41586-024-07691-8`, 2024). It is foundational to the oligomer
literature and still widely cited. Harder than PREDIMED because the surrounding
literature is much larger and the retraction's implications are genuinely
contested.
