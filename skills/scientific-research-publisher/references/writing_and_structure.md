# Paper Architecture and Scientific Writing

Read during phases 8 (architecture) and 9 (writing).

---

## Phase 8 — Architecture

Build the skeleton before any prose: section list, one-line purpose per section, and the claim IDs each section will use. If a planned section has no claims behind it, either the search was incomplete or the section shouldn't exist.

### Structure by discipline

The IMRaD shape (Introduction, Methods, Results, Discussion) is a biomedical convention, not a law. Forcing it on a theory paper produces a Methods section describing algebra and a Results section restating equations.

**Experimental (bio, chem, med, psych, materials):**
Introduction → Methods → Results → Discussion → Limitations → Conclusion

**Theoretical / physics:**
Introduction → Background & formalism → Model → Analysis/Derivation → Consequences → Comparison with experiment → Discussion → Conclusion
Methods and Results are interleaved because the derivation *is* the result.

**Computational / CS / ML:**
Introduction → Related work → Method → Experimental setup → Results → Ablations → Limitations → Conclusion
Related work is its own section here, not folded into the introduction.

**Review / systematic review:**
Introduction → Search protocol (with counts, inclusion/exclusion, PRISMA-style flow) → Thematic synthesis → Contradictions and gaps → Discussion → Conclusion
The search protocol section is what separates a review from an essay.

**Methods / tool paper:**
Introduction → Design goals → Implementation → Validation → Comparison → Availability → Limitations

**Position / perspective:**
Introduction → State of the field → The problem → Argument → Objections and responses → Implications
The objections section is mandatory; without it, it's advocacy.

### Introduction shape

Four moves, in this order: what the problem is → what is known → what is missing (the gap) → what this paper contributes. The gap statement must follow from your search, and the contribution must be the size your evidence actually supports. "We show X" when you have suggestive correlational evidence is the most common overclaim in existence.

### Abstract

Write it last, from `claims.json`. Only `[S]`-backed or clearly-hedged results appear. Structure: context (1–2 sentences), question, what was done, what was found *with the key number*, what it means, and the principal limitation. An abstract with no limitation is either a very unusual paper or a dishonest one.

---

## Phase 9 — Writing passes

One pass, one job. Combining them produces prose that is fluent and wrong, because fluency optimization pulls against precision.

### Pass 1 — Draft
Write section by section directly from the ledger, carrying the provenance tags inline as comments (`% [I] C12`). Do not stop to polish. Do not write a sentence you cannot attach to a claim ID.

### Pass 2 — Scientific accuracy
For each sentence: is this what the source says, or what I want it to say? Check every number, unit, and direction of effect against `claims.json`. Verify each generalization is licensed by the source's scope.

### Pass 3 — Logical coherence
Does each conclusion follow from what precedes it? Look specifically for: correlation described as cause, a sample-specific finding stated universally, a mechanism asserted from an association, and the load-bearing "clearly" or "obviously" that is doing the work an argument should do.

### Pass 4 — Citation audit
Every citation re-checked against its ledger locator. Every claim needing support has it. No citation is decorative — attached to a sentence it doesn't actually support. See `review_and_qa.md`.

### Pass 5 — Terminology
One term per concept. Field-standard usage. Define non-obvious terms at first use. Notation matches `equations.json` exactly.

### Pass 6 — Concision
Cut what doesn't carry information. Prime targets: throat-clearing openers ("It is important to note that"), restatements of the previous sentence, and adjective stacks that add emphasis rather than content. Nothing that changes the meaning gets cut — this is a length pass, not an editing-for-taste pass.

### Pass 7 — Grammar and mechanics
Tense consistency (past for what was done and found; present for established facts and what figures show), subject–verb agreement, parallel structure in lists, hyphenation of compound modifiers, consistent number and unit formatting.

**There is no "make it compelling" pass.** Every strengthening move available at that stage — dropping the hedge, promoting the inference, deleting the caveat — makes the paper less true.

---

## Style rules

**Hedge precisely, not reflexively.** "May potentially possibly contribute" is not careful, it's noise. Match the hedge to the evidence: `[S]` with high confidence → state it. `[I]` → "suggests", "is consistent with", "taken together imply". `[P]` → "we propose", "one interpretation is". Contested → name the disagreement.

**Prefer the specific.** "Increased by 34% (95% CI 28–41)" beats "significantly increased". "In three of five cell lines" beats "generally".

**Voice.** Active where the actor matters ("We measured..."), passive where the process does ("Samples were incubated..."). Both are correct scientific English; alternating for variety within a paragraph is not.

**Numbers.** Significant figures reflect actual precision — do not report 3.14159 from a measurement good to two digits. Uncertainty accompanies every measured value. Units on every quantity, SI unless the field's convention differs. Consistent decimal and thousands separators throughout.

**Attribute contested claims.** "Smith et al. argue X, while Jones et al. report the opposite under Y conditions" — not a smoothed synthesis that hides the disagreement.

**Limitations are load-bearing.** Written specifically, not as ritual. "Small sample" is filler; "n=12 from a single site limits generalization to other populations, and the effect was not observed in the one replication attempt we found" is a limitation.

**Say what would change your mind.** A sentence naming what evidence would overturn the conclusion is worth a page of hedging.

---

## Sentence-level examples

**Overclaim → calibrated**
- ✗ "These results demonstrate that X causes Y."
- ✓ "These results are consistent with X contributing to Y; the design does not exclude Z as a common cause."

**Inference stated as fact → marked inference**
- ✗ "The mechanism operates through pathway P."
- ✓ "Taken together, these observations suggest pathway P, though no study has measured the intermediate directly."

**Decorative citation → real support**
- ✗ "Deep learning has transformed the field [1–8]."
- ✓ "Error rates on ImageNet fell from 26% to 3.6% between 2011 and 2015 [3, 5]."

**Vague scope → specified scope**
- ✗ "The effect is well documented."
- ✓ "The effect has been reported in four studies of adult rodents; we found no human data."

**Hidden disagreement → reported disagreement**
- ✗ "Estimates of the rate cluster around 0.4."
- ✓ "Reported rates range from 0.1 [7] to 0.8 [12]; the discrepancy tracks the measurement technique rather than the sample."
