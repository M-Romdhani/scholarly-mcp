# Source APIs

Read before constructing any query.

Verified September 2026. APIs change — if a response shape contradicts this file, trust the response and tell the user the reference is stale.

---

## OpenAlex — discovery backbone

`https://api.openalex.org` · key **required** (free) · `openalex.org/settings/api`

```
GET /works?search=<terms>&per_page=100&api_key=$KEY
GET /works/doi:10.1038/nature12373?api_key=$KEY          # singleton — free
GET /works?filter=cited_by:W2741809807&api_key=$KEY      # what this paper cites
GET /works?filter=cites:W2741809807&api_key=$KEY         # what cites this paper
GET /works?filter=publication_year:>2024,concepts.id:C41008148&api_key=$KEY
```

**Cost model (this should drive your strategy):**

| Operation | per 1,000 calls |
|---|---|
| Singleton by DOI/ID | free, uncapped |
| List + filter | $0.10 |
| Search / semantic search | $1.00 |
| Content download (PDF/TEI) | $10.00 |

Free budget: $1.00/day with a key, $0.10/day without. Every response returns headers reporting spend and remaining — read them.

**Strategic consequence:** searching is the expensive operation and singleton lookup is free at any volume. So spend a few searches to get an entry set, then expand the citation graph by DOI for nothing. Always `per_page=100`.

Useful fields: `doi`, `title`, `publication_year`, `authorships[].author.display_name`, `primary_location.source.display_name`, `type`, `cited_by_count`, `referenced_works`, `open_access.oa_status`, `open_access.oa_url`, `is_retracted`, `best_oa_location.pdf_url`. Use `select=` to keep responses small.

The full 480M-work snapshot is free to bulk download — for anything at corpus scale, that beats hammering the API.

---

## Crossref — bibliographic truth

`https://api.crossref.org` · no key · send `mailto` for the polite pool

```
GET /works/10.1038/nature12373?mailto=you@example.org
GET /works?query.bibliographic=<title words>&rows=5&select=DOI,title,author,container-title,issued&mailto=...
GET /works?query.author=<name>&filter=from-pub-date:2024-01-01&mailto=...
```

This is the arbiter. Discovery indexes normalize, guess, and get author order and publication year wrong; Crossref holds what the publisher actually deposited. Verify every DOI here before it enters the ledger.

Fields that matter: `title[0]`, `author[]` (`given`, `family`, `sequence`), `container-title[0]`, `volume`, `page`, `issued.date-parts`, `type`, `publisher`, `is-referenced-by-count`, `update-to[]` (retraction/correction records), `relation`.

Always use `select=` — a single record with its full reference list can be tens of thousands of tokens. The Crossref record for one 1977 review returned 295 references in one response.

Rate limits were revised December 2025; read `X-Rate-Limit-*` response headers rather than assuming a figure, and honor `Retry-After` on `429`.

---

## Semantic Scholar — independent second opinion

`https://api.semanticscholar.org/graph/v1` · unauthenticated works at a shared low rate limit; key available for volume

```
GET /paper/search?query=<terms>&limit=20&fields=title,authors,year,venue,externalIds,citationCount,abstract
GET /paper/DOI:10.1038/nature12373?fields=title,authors,year,references,citations
GET /paper/DOI:.../references?fields=title,year,externalIds
```

Value is independence: it indexes and ranks differently from OpenAlex, so agreement is genuine corroboration and divergence exposes a blind spot. Also strong on CS/AI, and `tldr` summaries are useful for triage — but a `tldr` is a machine summary, so a claim sourced from one is `abstract-only` at best, not full text.

Expect `429` under load. Back off.

---

## Unpaywall — legal open access

`https://api.unpaywall.org/v2/<DOI>?email=you@example.org` · no key, email required

Returns `is_oa`, `oa_status` (gold/green/hybrid/bronze/closed), `best_oa_location.url_for_pdf`, and all `oa_locations`.

**Not independent of OpenAlex** — OpenAlex incorporates the same OA dataset. Agreement between them corroborates nothing.

Bronze OA is free-to-read but without an open license, and can disappear. Prefer gold or green when recording a durable link.

---

## arXiv — preprints in physics, math, CS

`http://export.arxiv.org/api/query` · no key · Atom XML, not JSON

```
GET /api/query?search_query=all:<terms>&max_results=50&sortBy=submittedDate&sortOrder=descending
GET /api/query?id_list=2403.13339
```

Rate limit: roughly one request every 3 seconds. Where the newest work lives, months ahead of journal publication.

**Always record the version** (`v1`, `v2`, …) — arXiv papers change, sometimes substantially, and a claim cited to "the arXiv version" without a version number is unverifiable. If a version of record exists, cite that and note the preprint.

---

## Europe PMC — biomedical, with full text

`https://www.ebi.ac.uk/europepmc/webservices/rest` · no key

```
GET /search?query=<terms>&format=json&pageSize=100&resultType=core
GET /search?query=DOI:"10.1038/nature12373"&format=json&resultType=core
```

Broader than PubMed (includes preprints and patents) and gives open-access full text directly via `/{source}/{id}/fullTextXML` — which means real full-text access rather than abstract-only, and that distinction matters downstream. Query syntax supports `AUTH:`, `JOURNAL:`, `PUB_YEAR:`, `SRC:`.

PubMed E-utilities (`eutils.ncbi.nlm.nih.gov/entrez/eutils/`) remain useful for MeSH-term precision.

---

## Others, when the field calls for them

- **OpenCitations** (`opencitations.net/index/api/v1`) — open citation graph, independent of the commercial indexes. Useful as a third opinion on citation relationships.
- **DataCite** (`api.datacite.org`) — datasets, software, and other non-article research outputs with DOIs. The place to find the data behind a paper.
- **NASA ADS** (`api.adsabs.harvard.edu/v1`) — astronomy; token required, free with registration.
- **INSPIRE-HEP** (`inspirehep.net/api`) — high-energy physics; no key, excellent citation graph.
- **DBLP** (`dblp.org/search/publ/api`) — CS bibliography, authoritative on venue names and author disambiguation.
- **zbMATH Open** (`api.zbmath.org`) — mathematics reviews.

**Google Scholar has no official API.** Scraping it violates its terms and gets blocked. Do not build on it, and do not present scraped Scholar results as retrieved sources.
