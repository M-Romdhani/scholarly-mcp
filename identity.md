# identity.md

**Read this before reviewing the code.** It explains what this server is for and, more importantly, what it must refuse to become. Several design choices below look like unnecessary restrictions until you know the failure they prevent.

---

## The gap

Claude in a browser chat session cannot reach scholarly APIs. Two independent blocks, both verified by testing on 2026-09-02:

**1. The container has no egress to them.** The sandbox proxy allowlists package registries (PyPI, npm, GitHub) and nothing else. `curl https://api.crossref.org/works/10.1038/nature12373` returns `403` from the proxy, not from Crossref.

**2. `web_fetch` reaches them, but unreliably — and fails silently.** It only accepts URLs that appeared verbatim in a prior search or fetch result. A constructed URL does one of two things:

- Returns `PERMISSIONS_ERROR`. Harmless — you know it failed.
- **Silently returns a different URL's data.** The fetcher snaps to the nearest previously-seen URL and returns *that* response, correctly formatted, with no error.

Observed: a request for `api.crossref.org/works?query.bibliographic=attention+is+all+you+need` returned results for `api.crossref.org/works?filter=orcid:0000-0002-9117-4510` — an ORCID filter that had appeared in an earlier search snippet. Twenty real papers, valid JSON, none related to the query. Nothing in the body indicated a substitution.

That second one is why this server exists. A research assistant that trusts a silently-substituted response will produce a bibliography of papers that are real but have nothing to do with the topic — which is harder to catch than an outright hallucination, because every DOI resolves.

**What the MCP fixes:** the server makes the calls from its own network, so there is no egress block and no URL-provenance gate. Results come back as structured tool results. The substitution failure mode disappears entirely.

**Secondary win:** API keys live in the server's environment. They never appear in a skill file, a repo, or a chat transcript.

---

## Who this is for

Med — physicist, builds early-stage products, uses Claude for science and code work. Direct user, not a customer-facing deployment.

It backs two skills:

- `scholarly-source-gathering` — federated literature discovery and citation verification
- `scientific-research-publisher` — takes a verified source set through to a typeset PDF

The skills contain the *method* (five search rounds, verification discipline, evidence ledger schema). This server provides the *access*. Neither replaces the other. If the server is unreachable, the skills fall back to search tools at reduced coverage — degraded, not broken.

Traffic is one person's research sessions. Tens to low hundreds of calls per session. Design for correctness and clear failure, not for scale.

---

## How the engine works

```
Claude (chat)
    │  MCP over streamable HTTP
    ▼
 THIS SERVER  ── allowlist ── SSRF guard ── SQLite cache
    │
    ├─→ OpenAlex        discovery + citation graph   (key required, budgeted)
    ├─→ Crossref        bibliographic truth          (no key, mailto)
    ├─→ Semantic Scholar independent second opinion  (optional key)
    ├─→ arXiv           preprints                    (no key, 3s spacing)
    └─→ Unpaywall       legal open-access full text  (email param)
```

Five tools, deliberately:

| Tool | Does | Notes |
|---|---|---|
| `search_literature` | Same query across independent indexes, merged, deduped, corroboration-counted | The expensive one |
| `verify_doi` | Crossref metadata + retraction status | The truth layer |
| `expand_citations` | References (backward) or cited-by (forward) | Free on OpenAlex |
| `resolve_fulltext` | OA location + access level | Feeds the ledger's `access` field |
| `budget_status` | OpenAlex spend and remaining | So Claude can pace itself |

### Why these five and not one

Two shapes were rejected.

**A generic `call_api(url, headers)` passthrough.** Tempting — "then Claude can use any API." It is a confused-deputy machine. Claude reads web content during research; injected text in a fetched page can induce it to point that tool at cloud metadata endpoints, Railway internals, or an attacker's collector with API keys in a header. It also gives the model no affordances: it would have to recall each API's query syntax from memory, which reintroduces exactly the fabrication risk the skills exist to prevent — moved from citations to query construction.

**A single `do_literature_review()` mega-tool.** Would hit tool timeouts, return an unreviewable blob, and duplicate orchestration the skill already specifies better. Fast primitives, Claude drives the loop.

So: **task-shaped tools, no arbitrary URLs, all endpoints constructed server-side from validated parameters.**

### The cost model shapes the design

OpenAlex changed in February 2026. A key is now required (free, `openalex.org/settings/api`). Budget is $1.00/day with a key, $0.10/day without.

| Operation | per 1,000 calls |
|---|---|
| Single lookup by DOI/ID | **free, uncapped** |
| List + filter | $0.10 |
| Search / semantic search | $1.00 |
| Content download | $10.00 |

This inverts the naive strategy. Searching costs money; hydrating by DOI is free at any volume. So `expand_citations` — walking the citation graph — is both the highest-value research operation and the free one, while `search_literature` is the one to spend carefully. `budget_status` exists so Claude can see where it stands rather than guessing, and the cache exists because citation expansion revisits the same DOIs across rounds.

### What the server must never do

These are correctness properties, not preferences:

1. **Never fetch a URL not built by this server from validated parameters.** No user-supplied or model-supplied URLs, ever.
2. **Never widen the allowlist by suffix matching.** `evil-api.crossref.org.attacker.com` must fail. Exact hostname match only.
3. **Never follow a redirect off the allowlist.** Re-validate the host on every hop.
4. **Never return metadata as verified when it came from a discovery index.** Discovery indexes get author order and publication year wrong routinely. Only Crossref (or DataCite) output is marked `verified_against`.
5. **Never guess an access level.** `resolve_fulltext` reports what OA data says; whether a human or model actually *read* the paper is set downstream, by hand. Inflating this field corrupts every judgment built on it.
6. **Never silently degrade.** If a source fails, say which one failed and why, in the tool result. Partial coverage reported as complete is the failure this whole system exists to prevent.

Rule 6 is the through-line. The purpose of the server is not convenience — it is that a claim about the literature can be traced to something that actually happened. Every place the code chooses a loud failure over a quiet fallback, that is why.

---

## Deployment shape

Railway, streamable HTTP on `/mcp`, `PORT` from the environment. Single process, SQLite cache on the local filesystem (ephemeral by design — it's a cache, and losing it costs a few free DOI lookups). Optional bearer token so the endpoint isn't open to the internet.

Review notes, known gaps, and the Railway steps are in `README.md`.
