# Access Routes

Read at step 0, and again whenever a fetch returns something that doesn't look like what you asked for.

**If the `scholarly-mcp` tools are available, you are on Route MCP and most of this file is historical.** It documents how to work without server-side API access and how to detect a specific silent-failure mode in `web_fetch`. Both stop applying once the MCP connector is attached, because the server makes every call from its own network and returns structured results.

The same query works, fails loudly, or fails silently depending on where the skill is running. Establishing the route first is cheap; discovering it halfway through a literature review is not.

---

## Determining the route

**Check for the MCP connector before anything else.** If `search_literature`, `verify_doi`, `expand_citations`, `resolve_fulltext` and `fetch_fulltext` are in your tool list, you are on **Route MCP** and the rest of this file is background only — no egress probe, no `web_fetch`, and the substitution failure documented below cannot occur.

Only when those tools are absent:

```bash
curl -s -m 8 -o /dev/null -w "%{http_code}\n" "https://api.crossref.org/works/10.1038/nature12373"
```

- MCP tools present → **Route MCP** (best; skip the probe)
- `200` → **Route A**
- `403`, `000`, or timeout → check whether `web_fetch` exists → **Route B** if yes, **Route C** if no

A `403` here is usually an egress proxy denial, not Crossref rejecting you. Sandboxes commonly allow package registries (PyPI, npm, GitHub) and nothing else. If the proxy returns an `x-deny-reason` header, that confirms it — and if the user controls the sandbox settings, they can add the scholarly domains to the allowlist and you become route A.

---

## Route A — open network

Everything works. Use the scripts. Observe rate limits:

- Send a `mailto` on every Crossref request — it routes you to the polite pool. Crossref revised its rate limits in December 2025, so do not hardcode a requests-per-second figure; instead read `X-Rate-Limit-Limit` and `X-Rate-Limit-Interval` from the response headers and back off on `429` honoring `Retry-After`.
- OpenAlex requires an API key on every request. Read the budget headers each response returns rather than estimating spend.
- Semantic Scholar's unauthenticated tier is a shared low rate limit; expect `429` under any real load and back off. Request a key if you need volume.
- Never parallelize aggressively against a free public API. These are nonprofits serving everyone.

---

## Route B — sandboxed, with web_fetch

`web_fetch` routes through a different network path than the container, so it *can* reach scholarly APIs. But it has a gate that changes how you must use it.

### The gate

`web_fetch` only accepts URLs that appeared verbatim in a prior `web_search` or `web_fetch` result. A URL you construct yourself hits one of two outcomes:

**Outcome 1 — rejected.**
```
PERMISSIONS_ERROR: This URL was not in any prior search or fetch result.
```
Harmless. You know it failed.

**Outcome 2 — silently substituted.** The fetcher resolves to the nearest previously-seen URL and returns *that* URL's data. You get well-formed JSON, no error, and the wrong answer.

Observed instance: a request for
```
https://api.crossref.org/works?query.bibliographic=attention+is+all+you+need&rows=2&select=...
```
returned results for
```
https://api.crossref.org/works?filter=orcid:0000-0002-9117-4510&select=...
```
— an ORCID filter that had appeared in an earlier search snippet. Valid JSON, twenty real papers, none of them related to the query. Nothing in the body indicated a problem.

### The defense

**Every fetch result carries `destination_url` (and `final_url`) in its metadata. Compare it to what you requested. If they differ in any way beyond URL encoding, discard the entire result.** Do not salvage part of it. Do not reason about which fields might still be valid.

This is the single most important rule in this file. A silently substituted result is exactly how a fabricated bibliography gets built by a system that was trying to be careful.

### What to do instead on route B

- **Discover with `web_search`**, not with API queries. Search naturally ("papers on X mechanism 2024"), then fetch the specific links that come back.
- **Verify against landing pages**: `doi.org/10.xxxx/...` resolves to the publisher page; `arxiv.org/abs/NNNN.NNNNN`; PubMed and PMC records. These carry authoritative title, authors, venue, and date.
- **Bootstrap API access when you need it**: search for documentation or a blog post that contains a literal example API URL, then fetch that exact URL. This works but gives you *that* example's data, not your query — useful for confirming an API is reachable, not for running a search.
- **Record honestly**: `retrieval_method` becomes `web_search`, `web_fetch:landing-page`, or `web_fetch:api`, and `access` reflects what you could actually read.

Route B is slower and covers less ground. That is a real limitation to state, not to paper over.

---

## Route C — search only

Discovery via `web_search`; verification via whatever the search surfaces. You can still produce a legitimate source set — publisher pages carry authoritative metadata — but citation-graph expansion (round 2) and systematic contradiction search (round 3) are much weaker.

Say so. A source set gathered this way should carry an explicit note that coverage was not systematic.

---

## Credentials

Environment variables only: `OPENALEX_API_KEY`, `S2_API_KEY`, `CONTACT_EMAIL`.

- Never write a key into a file that gets saved or shared.
- Never echo a key into output, logs, or chat.
- If the user offers to paste a key into the conversation, tell them to set it as an environment variable instead — a key in chat history is a key that has leaked.
- OpenAlex keys are free and take about 30 seconds: create an account at openalex.org, then openalex.org/settings/api. If the user hasn't got one, the no-key tier ($0.10/day) is enough to demonstrate the pipeline but not to run a real review.
