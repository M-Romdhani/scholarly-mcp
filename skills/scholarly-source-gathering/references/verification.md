# Verification

Read before writing anything to the ledger.

Discovery produces candidates. Verification decides which are real, which are what they claim to be, and which are safe to rely on. Nothing skips this.

---

## 1. Deduplicate

Two passes.

**By DOI.** Normalize first: lowercase, strip `https://doi.org/` and `doi:` prefixes, strip trailing punctuation. DOIs are case-insensitive but arrive in every casing.

**By content**, for records lacking DOIs: normalized title (lowercase, strip punctuation and articles) + first author surname + year. Allow ±1 year — indexes disagree about online-first versus issue dates constantly.

**Preprint and version of record are not duplicates.** They are the same work with different DOIs, and often different content — the peer-reviewed version may have changed the result. Keep both, link them (`version_of`), and cite the version of record while noting the preprint. If only the preprint exists, say so; it is unrefereed.

---

## 2. Crossref verification

Every DOI goes through Crossref before it enters the ledger. Discovery indexes normalize, guess, and get things wrong; Crossref holds what the publisher deposited.

Check and correct:

| Field | Common failure |
|---|---|
| Title | Truncation, HTML entities, subtitle dropped |
| Authors | **Order scrambled** — check `sequence: first` |
| Venue | Abbreviation vs full name inconsistency |
| Year | Online-first vs issue date disagreement |
| Volume/pages | Missing in discovery metadata |
| Type | Preprint vs article vs chapter mislabeled |

If Crossref doesn't have the DOI, that is a serious signal. Some legitimate DOIs are registered with DataCite (datasets, some preprints) rather than Crossref — check there before rejecting. But a DOI that resolves nowhere is not a source.

**A source that will not verify does not enter the ledger.** Record it in `rejected.json` with the reason. Knowing that a plausible-looking citation doesn't exist is worth keeping — it is often the trace of a fabrication that would otherwise have made it into the paper.

---

## 3. Retraction screening

Check **both** OpenAlex and Crossref. Neither is sufficient alone:

- **OpenAlex `is_retracted`** — a boolean, which is the problem. It has conflated corrections and Expressions of Concern with actual retractions, and roughly 7% of retractions recorded in Retraction Watch are not flagged in OpenAlex at all. Treat it as a screen, never a verdict.
- **Crossref `update-to[]` / `update-nature`** — since Crossref acquired the Retraction Watch database, this carries the nuanced status: Retraction, Correction, Expression of Concern, Withdrawal. This is the one to trust for *what kind* of update it is.

Then act on the distinction:

- **Retracted** → do not cite as evidence. It may be cited *as a retracted paper* when discussing the retraction itself, which must be stated explicitly in the text, not just in the ledger.
- **Expression of Concern** → citable with the concern stated.
- **Correction** → cite the corrected version; check whether the correction affects the specific claim you are drawing on.

Also worth a check for load-bearing sources: papers *citing* the source that describe it as retracted, failed to replicate, or disputed. Retraction notices propagate slowly, and a paper can be thoroughly discredited long before any database says so.

---

## 4. Access resolution

Determine what you can actually read, and record it truthfully:

| Value | Means |
|---|---|
| `fulltext` | Read the whole paper |
| `abstract-only` | Only the abstract |
| `preprint-version` | Read the preprint, not the published version |
| `secondhand` | Only know it through another source's description |
| `metadata-only` | Confirmed it exists; read nothing |

Resolve full text via Unpaywall (`oa_status`, `best_oa_location`), Europe PMC full-text XML for biomedical, or the arXiv PDF. Prefer gold or green OA for durable links — bronze is free-to-read without an open license and can vanish.

This field is not bookkeeping. Downstream, it determines how much weight a claim can carry: abstracts overstate, omit conditions, and drop sample sizes, so a central claim resting entirely on abstracts means the source set has a hollow core. `secondhand` is worse — source A's description of source B is A's *reading* of B, and citation chains propagate misreadings for decades.

Never record `fulltext` for something you skimmed an abstract of. This is the single field most likely to be quietly inflated, and inflating it corrupts every judgment built on top of it.

---

## 5. Quality signals to record

Not scores — context for later judgment:

- `evidence_class`: primary-experimental / primary-theory / primary-computational / review / meta-analysis / preprint / dataset / grey-literature
- `scope_limits`: the conditions under which the finding holds — species, population, parameter range, N. This is what stops "shown in mice" becoming "shown".
- `venue_type`: peer-reviewed journal, conference, preprint server, institutional report
- `cited_by_count`: with the year, since raw counts favor old papers
- `data_available` / `code_available`: reproducibility signal
- `preregistered`: for empirical work, a strong quality signal

Do not compute a composite quality score. It compresses away exactly the information a reader needs, and creates false precision about judgments that are genuinely contestable.

---

## Verification report

When handing off, report the numbers:

```
Candidates found:        84
After deduplication:     61
Crossref verified:       58
Failed verification:      3   → rejected.json
Retracted:                1   → excluded, noted
Expression of concern:    1   → retained, flagged
Full text obtained:      34
Abstract only:           23
Contradiction round:      7 sources found
```

The gap between "found" and "verified", and the ratio of full text to abstract-only, are what tell the user how much the source set can actually bear.
