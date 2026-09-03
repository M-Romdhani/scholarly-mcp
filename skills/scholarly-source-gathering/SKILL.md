---
name: scholarly-source-gathering
description: Federated literature discovery and citation verification across OpenAlex, Crossref, Semantic Scholar, arXiv, Europe PMC, Unpaywall and domain indexes — builds a verified, deduplicated, retraction-screened source set instead of an LLM-generated bibliography. Use whenever the user needs to find papers, do a literature search or review, gather sources or references for a topic, check whether a citation is real, resolve a DOI, find an open-access full text, trace who cited what, or look for evidence contradicting a claim — and always before writing anything with citations in it, since a bibliography assembled from model memory will contain papers that do not exist.
---

# Scholarly Source Gathering

Finds real papers and proves they are real. The output is a verified source set, not a list of plausible titles.

Two failure modes drive every rule here. **Fabrication:** citations generated from model memory look correct — right authors, right journal, right year, no such paper. **Monoculture:** a single index's ranking becomes your view of the field, and what it ranks low you never learn exists.

The answer to both is federation. Independent indexes, cross-checked, with Crossref as the arbiter of what the metadata actually is.

---

## Step 0: establish your access route — do this before anything else

Which APIs you can reach depends entirely on the environment, and getting this wrong produces silent garbage rather than an error. Test, don't assume.

**Check for the MCP server first.** Look at your available tools for `search_literature`, `verify_doi`, `expand_citations`, `resolve_fulltext` and `fetch_fulltext` (the `scholarly-mcp` connector). If they are there, you are on **Route MCP** — stop here, skip the curl probe entirely, and use those tools. Everything below about routes A/B/C and the `web_fetch` trap applies only when they are absent.

Only if the MCP tools are missing, probe the network:

```bash
curl -s -m 8 -o /dev/null -w "%{http_code}\n" "https://api.crossref.org/works/10.1038/nature12373"
```

| Result | Route | What works |
|---|---|---|
| MCP tools present | **MCP — best** | Full federation, verified. No egress limits, no URL-provenance gate. |
| `200` | **A — open network** | Everything. Use `scripts/federate.py`. Full federation. |
| `403`/`000`/timeout, but `web_fetch` available | **B — sandboxed** | Search tools only. See the trap below. |
| Neither | **C — search only** | `web_search` for discovery, publisher pages for verification. |

Claude.ai's container is route B *unless the MCP connector is attached*: its egress proxy allows package registries only, so `curl` to any scholarly API returns 403. Claude Code on a normal machine is route A. The MCP server exists precisely to turn route B into something better than route A, because it also removes the substitution failure described below.

### Route MCP — the tools and what they replace

| Round / task | Tool | Notes |
|---|---|---|
| Round 1, discovery | `search_literature` | Queries several indexes at once and returns a `corroboration` count. Route by field: `europepmc` for biomedical, `inspire` for physics, `arxiv` for preprints. |
| Round 2, citation expansion | `expand_citations` | `direction="references"` backward, `"cited_by"` forward. Cheapest and highest-value round. |
| Verification | `verify_doi` | Crossref + OpenAlex + Europe PMC/MEDLINE, three independent retraction signals. This replaces every manual verification step below. |
| OA location | `resolve_fulltext` | Reports what is *available*. Does not mean you read it. |
| Reading full text | `fetch_fulltext` | Returns the actual open-access text, by section. After this you have genuinely read it. |
| Pacing | `budget_status` | OpenAlex spend and remaining. |

Two things to carry over unchanged: results from `search_literature` are **not verified** (`verified: false`) until `verify_doi` confirms them, and every tool reports failed sources in `sources_failed` — when that is non-empty your coverage is partial and you must say so.

### The route B trap — read this before using web_fetch on an API

**This section applies only when the MCP tools are unavailable.** With the MCP connected, the substitution failure below cannot happen: the server makes the calls from its own network and returns structured results.

`web_fetch` reaches scholarly APIs, but **only for URLs that appeared verbatim in a previous search or fetch result.** A URL you construct yourself does one of two things:

1. Returns `PERMISSIONS_ERROR` — fine, you know it failed.
2. **Silently returns a different URL's data.** The fetcher snaps to the nearest previously-seen URL and gives you *those* results, formatted exactly like success.

Case 2 is the dangerous one. A constructed Crossref query for one paper came back with results for an unrelated ORCID filter that had appeared in an earlier search snippet — correct-looking JSON, wrong query, no error.

**So on route B: check `destination_url` in every fetch result against the URL you requested. If they differ, discard the result entirely — do not use any part of it.** And prefer `web_search` for discovery, using `web_fetch` only on links that came back in results (DOI landing pages, arXiv abstract pages, PMC records). Do not try to run parameterized API queries.

Tell the user which route you are on when it limits what you can deliver. "I verified 22 of 30 DOIs; the other 8 I could only confirm via publisher pages" is useful. Silently downgrading is not.

---

## The federation

Never use one index. Roles, not preferences:

| Source | Role | Auth |
|---|---|---|
| **OpenAlex** | Discovery backbone + citation graph | Free key required |
| **Semantic Scholar** | Independent second opinion on discovery | Optional key |
| **Crossref** | Bibliographic truth — what the metadata *is* | None (send `mailto`) |
| **Unpaywall** | Legal open-access full text | Email param |
| **arXiv / Europe PMC / others** | Domain depth | None |

Corroboration rule: a paper found by two independent indexes is more likely to be real *and* more likely to be central. A paper found by one is not necessarily wrong, but it needs Crossref verification before it enters the ledger.

One caveat that matters: **OpenAlex and Unpaywall are not independent** — OpenAlex incorporates the same underlying open-access data. Agreement between them is not corroboration.

Full endpoint details, query syntax, and cost model: `references/sources.md`.
Field-to-index routing (physics → arXiv+INSPIRE, biomed → Europe PMC, etc.): `references/domain_routing.md`.

---

## OpenAlex changed in 2026 — budget accordingly

An API key is now **required** and **free** (openalex.org/settings/api). Without one you get $0.10/day; with one, $1.00/day. Pricing is per operation:

| Operation | Cost per 1,000 calls |
|---|---|
| Single lookup by DOI or ID | **free, uncapped** |
| List + filter | $0.10 |
| Search / semantic search | $1.00 |
| Full-text content download | $10.00 |

This shape should change how you search. Discovery costs money; hydration is free. So:

**Search a few times, then expand by DOI.** Run a small number of well-constructed searches to get an entry set, then walk the citation graph using single-record lookups, which cost nothing at any volume. Citation expansion — references and cited-by — is the highest-value round *and* the free one.

Use `per_page=100`. Every response carries headers reporting spend and remaining budget; read them rather than guessing. If the budget runs out mid-run, say so and report what was covered — do not quietly stop early.

---

## The five rounds

One search is not a literature review. Each round finds papers the previous one structurally cannot.

**Round 1 — Discovery.** Query expansion first: synonyms, the adjacent field's vocabulary, the method name as well as the phenomenon name. Then the same expanded query set against the indexes independently. Compare: overlap raises confidence, divergence shows one index's blind spot.

**Run many narrow queries, not a few broad ones.** This is the single biggest determinant of what you find, and broad queries fail in a way that is invisible: they return plenty of results, so nothing looks wrong. Relevance ranking rewards distinctive phrasing. In a measured comparison, the query "SDS-PAGE induces dimerization amyloid-beta human brain oligomers artefact" returned the decisive methodological paper at rank 1 with three-index corroboration, while a broad query on the same topic in the same session returned nothing usable and the argument was dropped from the review entirely.

Budget at least 6–10 distinct queries per round, and make them specific:

- The **mechanism or artefact**, not just the topic: "SDS-PAGE dimerization artefact", not "amyloid oligomers".
- **Named entities** — a drug, an assay, a cohort, a mutation, a trial acronym. Named things retrieve far better than concepts.
- The **claim you are trying to falsify**, phrased as its own paper title would be.
- **Both vocabularies** where a field renamed something.
- **Greek letters spelled BOTH ways.** Indexes do not normalise `β` to `beta`. Measured against OpenAlex: searching the exact title of a well-known paper as "amyloid-beta protein assembly" returned it in **none** of the top 100 results, while the identical query written "amyloid-β protein assembly" returned it immediately. The same applies to α/alpha, γ/gamma, Λ/Lambda, σ/sigma, µ/micro and to `Aβ` vs `Abeta` vs `A-beta`. In any field that names things with Greek letters — most of physics, chemistry and molecular biology — run the query both ways or you will silently miss the central paper.

Two mechanical notes. `*` and `?` are wildcard operators that some indexes reject outright; the server strips them before querying OpenAlex, so a molecule genuinely named `Aβ*56` is searchable, but be aware the asterisk is not matched literally. And a paper's indexed title may carry a status prefix — `RETRACTED ARTICLE:` or `WITHDRAWN:` — so an exact-title search can miss it while a distinctive-phrase search finds it.

A search that returns nothing is a finding worth reporting — but before reporting it, reformulate at least twice. "We could not find X" is only honest when it means "X does not appear to exist", not "our query was too broad".

**Round 2 — Citation expansion.** For each central paper, pull references (what it built on) and cited-by (what built on it). This is how you find the foundational 1987 paper that keyword search buried and the 2026 rebuttal that hasn't accumulated citations yet. Free via singleton lookups.

**Round 2b — Retraction lineage. Run this whenever a retracted or concerned paper turns up anywhere.** Retractions in a research programme rarely occur alone: they cluster by laboratory, because the same people, methods and data recur. Screening the single paper you happened to find and stopping there leaves the rest of the cluster in your bibliography, unflagged.

When any source comes back `retracted` or `concern`:

1. **Expand citations both ways from it** and `verify_doi` everything that comes back. Watch `retraction_alerts` in the tool output — an index has often already flagged a paper before you check it.
2. **Search its authors by name**, especially first and last author, together with the specific entity involved (the assay, the molecule, the model). Citation expansion alone is not sufficient and it is important to understand why: `cited_by` is ranked by citation count, so a retracted follow-up with few citations sits outside the window no matter how large you set the limit. This step is what actually finds the cluster.
3. **Search the retraction itself** — the notice, and any journalism or institutional investigation reporting on it. Investigative coverage names the affected papers directly and is frequently the fastest route to the full list.
4. **Report the cluster, not just the count.** Which specific inferential links depended on the retracted work, and what survives when those links are cut? A retraction that removes a result which *constrained* the hypothesis is not the same as one that removes support.

In a measured comparison, a review that screened only the one retracted paper it had found reported two non-clean sources; the same task done with a lineage search found five, including three retracted papers from the same laboratory that no citation walk surfaced.

**Round 3 — Contradiction.** Explicitly search against your thesis: `"X" criticism`, `"X" limitations`, `"X" failure to replicate`, `"X" reconsidered`, `"X" comment on`. Also check for Comment/Reply pairs and Expressions of Concern. **A source set with no disconfirming papers means the search was biased, not that the thesis is safe.** Report the round's yield explicitly, including zero.

**Round 4 — Recency.** Filter to the last 1–3 years. Recent work is systematically under-ranked by citation-weighted relevance, and it is where a novelty claim goes to die.

**Round 5 — Missing literature.** Ask: what work would I expect to exist that I haven't found? A landmark study everyone cites? A registered replication? A dataset paper? A review in the last two years? Then search for those specifically. This round catches the gap you didn't know you had.

Stop at saturation — when new queries return only papers you have. If saturation never arrives, say the search was not exhaustive rather than implying it was.

Full protocol including query construction: `references/discovery_protocol.md`.

---

## Verification — nothing enters the ledger unverified

Discovery finds candidates. Verification decides what is real.

1. **Deduplicate** on normalized DOI first, then normalized title + first author + year. The same paper appears as preprint and version-of-record with different DOIs — keep both, link them, and cite the version of record.
2. **Crossref-verify** every DOI. Authoritative title, authors, venue, volume, pages, date. Metadata from a discovery index is a search result, not a fact; discovery indexes get author order and year wrong.
3. **Screen for retraction.** Check OpenAlex `is_retracted`, Crossref `updated-by` (NOT `update-to` — that lives on the retraction notice, not on the retracted paper), and Europe PMC / MEDLINE publication type. Neither alone is sufficient: OpenAlex's boolean has conflated corrections and expressions of concern with retractions, and roughly 7% of known retractions aren't flagged there at all. `verify_doi` checks all three and escalates only. A retracted paper can still be cited — but only knowingly and with the retraction stated.

   **If anything comes back retracted or concerned, run the lineage search in Round 2b before continuing.** One retraction found usually means more exist.

   **Read what the notice actually says.** Publication status is not self-interpreting, and the same label can cut in opposite directions. A paper retracted for image manipulation and a paper retracted-and-republished after a randomisation audit are not the same evidential object. A *correction* issued after a challenge — where the authors revised the analysis and the conclusion survived — leaves the paper stronger evidence than it was before, not weaker. Reporting "this was corrected" without reading the correction can invert its meaning.
4. **Resolve full text** via Unpaywall or the OA location. Record whether you got full text or only an abstract. This is not bookkeeping: a claim resting on an abstract is materially weaker evidence, and abstracts routinely omit the conditions that limit a finding.
5. **Drop what won't verify.** A DOI that doesn't resolve is not a source. No "probably fine" tier.

Details and edge cases: `references/verification.md`.

---

## Output — hand off to the writing pipeline

Emit `ledger/sources.json` in the schema the `scientific-research-publisher` skill consumes, plus a matching `refs.bib`:

```bash
python3 scripts/to_ledger.py candidates.json --out <project>/ledger/sources.json --bib <project>/manuscript/refs.bib
```

Every record carries `retrieved`, `retrieval_method`, and `access` — that is what makes the downstream citation audit possible. Records that failed verification are written to a separate `rejected.json` with the reason, never silently dropped: knowing a plausible-looking paper doesn't exist is a finding worth keeping.

If that skill isn't in play, the same JSON works standalone.

---

## Scripts (route A only)

```bash
# multi-index federated search, dedup, merge
python3 scripts/federate.py "your query" --email you@example.org --openalex-key $OPENALEX_API_KEY --out candidates.json

# Crossref verification + retraction screen
python3 scripts/verify_dois.py candidates.json --email you@example.org --out verified.json

# emit ledger + bibliography
python3 scripts/to_ledger.py verified.json --out ledger/sources.json --bib manuscript/refs.bib
```

Stdlib only, no install. They need network egress — on route B they will fail with 403, which is the expected result, not a bug to work around. Do the equivalent work with search tools and record it the same way.

**On Route MCP you do not need these scripts at all.** `search_literature` replaces `federate.py` and `verify_doi` replaces `verify_dois.py`, both without needing egress from this container. `to_ledger.py` is still useful for emitting the ledger and bibliography from what the tools returned.

Credentials come from env vars (`OPENALEX_API_KEY`, `S2_API_KEY`, `CONTACT_EMAIL`). Never hardcode a key into a file, and never paste one into chat.

## Reference files

| File | Read it when |
|---|---|
| `references/access_routes.md` | Step 0, and any time a fetch behaves oddly |
| `references/sources.md` | Constructing any query — endpoints, syntax, fields, costs |
| `references/domain_routing.md` | After identifying the field, to pick connectors |
| `references/discovery_protocol.md` | Rounds 1–5, query expansion, saturation |
| `references/verification.md` | Dedup, Crossref checks, retraction screening, OA resolution |
