# Domain Routing

Read after identifying the field, before round 1.

Identify the discipline first, then activate connectors. Querying PubMed about quantum gravity wastes budget and returns noise; skipping Europe PMC on a neuroscience question means missing the full text you needed.

## Always on

`OpenAlex` (discovery) + `Crossref` (verification) + `Semantic Scholar` (second opinion) + `Unpaywall` (full text).

These four cover every field. Everything below is added depth, not replacement.

## By field

| Field | Add | Why |
|---|---|---|
| Physics, astronomy, math, CS | **arXiv** | Where the work appears first, often years before journal publication |
| High-energy physics | **INSPIRE-HEP** | Complete HEP citation graph; better than general indexes for this literature |
| Astronomy | **NASA ADS** | Canonical index; includes observations and data products |
| Mathematics | **zbMATH Open** | Expert reviews, not just metadata |
| Computer science, AI/ML | **DBLP** + Semantic Scholar | DBLP is authoritative on venue names and author disambiguation; conference papers dominate and general indexes handle them badly |
| Biology, medicine, neuroscience | **Europe PMC** + PubMed | MeSH precision, and open-access full text via API |
| Clinical | **ClinicalTrials.gov** | Registered protocols reveal outcome switching and unpublished trials |
| Chemistry, materials | **PubChem**, **Crystallography Open Database** | Compound and structure identifiers |
| Earth, climate | **DataCite**, agency repositories | The datasets are the evidence |
| Social science, economics | **SSRN**, **RePEc**, **OSF** | Working-paper culture; the journal version can lag by years |
| Psychology | **PsyArXiv**, **OSF Registries** | Preregistrations are how you detect analytic flexibility |
| Engineering | **IEEE Xplore** (metadata via Crossref), DBLP | Standards and conference proceedings |
| Any empirical field | **DataCite**, **OSF** | Data and code availability is itself evidence about a paper's quality |

## Cross-disciplinary questions

Query the vocabulary of each field separately rather than blending terms. The same phenomenon has different names across fields, and a blended query often matches neither literature well. Terminology mismatch is the most common reason a relevant literature stays invisible — the answer may already exist under a name you didn't search.

## Registries worth checking regardless of field

For anything empirical, look for the preregistration or trial registration. A registered protocol that differs from the published analysis is a serious methodological finding, and it is invisible to citation-based discovery.

For anything contested, check **PubPeer** for post-publication discussion. It is not peer-reviewed and is not citable as evidence, but a paper with substantial PubPeer criticism is one to read more carefully before relying on.
