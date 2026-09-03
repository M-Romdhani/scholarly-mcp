# scholarly-mcp

MCP server giving Claude verified access to scholarly literature APIs: OpenAlex, Crossref, Semantic Scholar, arXiv, Unpaywall, DataCite, Europe PMC, INSPIRE-HEP and OpenCitations.

**Read `identity.md` first.** It explains the problem this solves and the rules the code must keep. Several design choices look like unnecessary restrictions without that context.

---

## Status

Written and tested on 2026-09-02 against `mcp` SDK **2.1.1**. Note the SDK is at 2.x, where `FastMCP` was renamed to `MCPServer` — v1 examples found online will not work.

**Verified against live APIs on 2026-09-02.** All five adapters were run against real responses from OpenAlex, Crossref, Semantic Scholar, arXiv, Unpaywall and DataCite, and all five tools were exercised over the HTTP transport. 41/41 offline tests pass.

The parsers were correct as written — including `primary_location.source.display_name`, the `select` field lists, and the S2 `citedPaper`/`citingPaper` nesting. Four real defects were found and fixed; each has a regression test:

| Was | Now |
|---|---|
| `/mcp` answered **421** behind any real domain while `/health` returned 200 — a green deploy in front of a dead server | Host validation configured from `PUBLIC_HOSTNAME`; `/health` reports whether *this* request's Host would be accepted |
| Retracted papers classified as **clean** — the code read `update-to`, which lives on the retraction *notice*, not `updated-by`, which lives on the paper | Both fields read, severity ranked by precedence; verified against Wakefield 1998 and Mehra NEJM 2020 |
| `10.1234/../../v2/x` passed DOI validation and built a traversing URL | Relative and empty path segments rejected |
| One SQLite connection shared across the SDK's worker threads | Guarded by a lock |
| `budget_status` reported an amount remaining with no denominator | Full `x-ratelimit-*` family captured and parsed |

**Still not verified:** behaviour under sustained real load, and OpenAlex spend against a paid key (all live testing was on the keyless $0.10/day tier).

---

## Local run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in CONTACT_EMAIL at minimum
set -a && source .env && set +a
python -m app.main            # → http://127.0.0.1:8000/mcp
python -m tests.test_offline  # 57 tests, no network needed
```

Smoke test:

```bash
curl -s localhost:8000/health | python -m json.tool

curl -s -X POST localhost:8000/mcp \
  -H "Authorization: Bearer $MCP_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

---

## Railway deploy

1. Push this directory to a GitHub repo (`.gitignore` already excludes `.env`).
2. Railway → **New Project → Deploy from GitHub repo**. Nixpacks detects Python from `requirements.txt`; `railway.json` supplies the start command and healthcheck.
3. **Variables** — set these in the Railway dashboard, not in the repo:

   | Variable | Required | Notes |
   |---|---|---|
   | `CONTACT_EMAIL` | **yes** | Server refuses to start without it. Crossref's polite pool depends on it. |
   | `OPENALEX_API_KEY` | strongly recommended | Free, 30s at `openalex.org/settings/api`. Without it: $0.10/day instead of $1.00/day. |
   | `MCP_AUTH_TOKEN` | strongly recommended | Otherwise the public URL is open and anyone can spend your budget. Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
   | `PUBLIC_HOSTNAME` | only for custom domains | Railway sets `RAILWAY_PUBLIC_DOMAIN` automatically and the server falls back to it. Set this to the hostname **the client connects to** when you put a custom domain or CDN in front — otherwise `/mcp` answers 421. |
   | `S2_API_KEY` | **yes, if you want corroboration to mean anything** | Semantic Scholar 429s quickly without one. It is a default source for `search_literature`, and it is the only index in the set that is independent of Crossref deposit data — so without the key, corroboration counts are weaker than they look. Requested at `semanticscholar.org/product/api`; approval is manual and not instant. |

   Do **not** set `PORT` — Railway injects it.
4. **Settings → Networking → Generate Domain.**
5. Confirm: `curl https://<domain>/health` should return `{"status":"ok", ...}` with `auth_required: true`, `mcp_would_accept_this_host: true`, and an **empty `warnings` array**. A non-empty `warnings` array is the server telling you something is misconfigured while still returning 200 — read it. In particular, `mcp_would_accept_this_host: false` means `/mcp` will answer 421 even though this check passed.
6. Add to Claude as a custom connector: URL `https://<domain>/mcp`, with the bearer token.

The SQLite cache lives on ephemeral disk and is wiped on redeploy. That is fine — it is a cache, and losing it costs a few free DOI lookups. Attach a volume at `CACHE_PATH` only if you want it to survive.

---

## Review status

Everything in the original review checklist has now been run against live APIs. Results:

**1. Response parsing — done, parsers were correct.** All six adapters checked against real responses. `_oa_record` (including `primary_location.source.display_name` and the `select` list), `_cr_record`, S2's `citedPaper`/`citingPaper` nesting, arXiv Atom, Unpaywall and DataCite all parse live data correctly.

**2. OpenAlex budget headers — done, names confirmed.** The live set is `X-RateLimit-Limit`, `X-RateLimit-Limit-USD`, `X-RateLimit-Remaining`, `X-RateLimit-Remaining-USD`, `X-RateLimit-Cost-USD`, `X-RateLimit-Credits-Used`, `X-RateLimit-Reset`, `X-RateLimit-Onetime-Remaining`, `X-RateLimit-Prepaid-Remaining-USD`. The capture now takes the whole `x-ratelimit-*` family rather than a substring list, which had been dropping the limit and the reset time. (`X-RateLimit-Limit-USD: 0.1` on a keyless request independently confirms the documented cost model.)

**3. Auth middleware ordering — confirmed correct**, and Host validation was found broken alongside it. `/mcp` returns 401 without a token and 421 for an unrecognised Host; `/health` stays open for platform probes.

**4. `stateless_http=True` — kept.** Works over the real transport.

**5. Rate-limit behaviour — partly addressed.** Semantic Scholar 429s on the first unauthenticated call, so it is no longer a `search_literature` default. Backoff is now bounded by `FETCH_DEADLINE` (45s) so a rate-limited source fails reportably instead of outlasting the client's tool timeout. Sustained-load behaviour is still untested.

**Retraction classification — was wrong, now fixed and the most important change here.** Crossref puts `update-to` on the retraction *notice* and `updated-by` on the retracted *paper*. Reading only `update-to` meant every retracted paper classified as clean; `verify_doi` then emitted `disputed_flag` with the note "Crossref shows no retraction record" — false — and no guidance line at all. Confirmed against Wakefield 1998 and Mehra NEJM 2020, both of which now return `retracted` with the correct guidance.

## Security invariants — do not relax these

Encoded in `tests/test_offline.py`. If a test there starts failing, the server has become the passthrough that `identity.md` rejects.

- **Exact-hostname allowlist**, `in frozenset` — never `endswith()`. `api.crossref.org.attacker.com` must fail.
- **No tool accepts a URL, host, endpoint, or headers.** There is a test asserting this against the generated tool schemas.
- **Redirects re-validated per hop** — `_NoRedirect` forces manual handling so urllib cannot follow one off the allowlist.
- **DNS resolution checked against private/reserved ranges** before connecting.
- **DOIs validated against an anchored regex** that excludes `?`, `#`, `&`, backslash and whitespace, so a DOI cannot inject query parameters into a constructed URL — **and** relative/empty path segments are rejected separately. The regex alone is not sufficient: a DOI suffix may legally contain `/`, and `build_url` leaves `/` unescaped, so `10.1234/../../v2/x` used to validate and build a URL that walked to a different endpoint on an allowlisted host.
- **Host header validated** against `PUBLIC_HOSTNAME` by the MCP transport, and `/health` reports whether the incoming Host would be accepted rather than reporting `ok` for a server whose `/mcp` is answering 421.
- **Response size capped** at 8 MB. One Crossref record with a full reference list ran to hundreds of entries.

If you add a source, add its host to `ALLOWED_HOSTS`, add an adapter that builds URLs via `build_url`, and add a test. Never add a way to pass a URL in.

---

## Sources

| Source | Role | Key |
|---|---|---|
| OpenAlex | Discovery backbone + citation graph | free, required |
| Crossref | Bibliographic truth, retraction records | none |
| Semantic Scholar | Independent second opinion | optional, 429s without |
| arXiv | Preprints | none |
| Unpaywall | Legal OA locations | none |
| DataCite | Dataset/software DOIs | none |
| **Europe PMC** | Biomedical depth, MEDLINE retraction curation, **OA full text** | none |
| **INSPIRE-HEP** | High-energy physics and astrophysics | none |
| **OpenCitations** | Independent citation edges | none |

Three of these carry retraction signals, and `verify_doi` checks all three: Crossref `updated-by`, OpenAlex `is_retracted`, and Europe PMC's MEDLINE curation (`Retracted Publication` publication type plus `Retraction in` links). They escalate only — a registry that has not recorded a retraction is not evidence there is none, so a quieter source never downgrades a retraction another one found.

Two independence caveats are encoded in `merge.INDEPENDENCE_GROUPS` and matter for corroboration counts:

- **OpenCitations is grouped with Crossref.** Its index is built largely from the reference lists publishers deposit at Crossref, so agreement between them is one deposit counted twice.
- **OpenAlex is grouped with Unpaywall**, as before — same underlying OA dataset.

## Known gaps

- **No `search_by_field` tool** (author, year range, venue). OpenAlex list+filter is cheap ($0.10/1000) and this is now the most valuable missing piece, not a nice-to-have: author search is what finds a retraction cluster, and citation expansion demonstrably cannot substitute for it.
- **Cache is not shared across instances.** Fine at one user; would need Redis if that changes. The in-process connection is lock-guarded, which is correct for one process but does not coordinate between replicas — keep this service at one instance.
- **No structured logging or metrics.** Add if it moves beyond personal use.
- **`resolve_fulltext` reports availability, not readership.** By design — see `identity.md` rule 5. Do not "improve" it into auto-setting the ledger's `access` field. `fetch_fulltext` is the tool that actually returns text, and it reports exactly which sections it returned and whether the result was truncated, so `access` can be set from what was really read.
- **`search_literature` ranking is relevance-first, not citation-first.** Sorting merged results by citation count alone surfaced clinical guidelines and burden-of-disease reviews (8,000+ citations) above the pivotal randomised trial a query was actually about. Sorting by corroboration first failed differently: independent indexes agree readily on broad topical matches, so on a cardiovascular query the corroborated papers were about breast cancer and type 2 diabetes and pushed the pivotal trial to rank 5. Results now sort by relevance rank, then corroboration, then citations — corroboration is evidence a paper is real, not that it answers the question, so it is a tiebreak. It is still reported per record and in `multi_index_count`. Recall of mid-list papers is still bounded by what each index ranks highly — expand the query rather than raising `limit` alone.
- **Indexes do not normalise Greek letters.** Measured on OpenAlex: the exact title of a well-known paper searched as "amyloid-beta protein assembly" appears in **none** of the top 100 results; written "amyloid-β protein assembly" it returns immediately. This affects α/alpha, γ/gamma, Λ/Lambda and every field that names things with Greek letters. Query both ways. The gathering skill now says so.
- **`*` and `?` are wildcard operators OpenAlex rejects with HTTP 400.** Every other punctuation character passes. `openalex_search` strips them, because entities are sometimes named with them — `Aβ*56` is a real molecule — and searching for the thing by its actual name used to crash the call rather than return nothing.
- **Retraction flags are surfaced, not just available.** `search_literature` and `expand_citations` now return `retraction_alerts` for any result an index already flags. This costs no extra call — OpenAlex returns `is_retracted` on every record and Europe PMC returns MEDLINE publication types, and that data was being fetched and then ignored. They are screening flags, not verdicts; each still needs `verify_doi`.
- **Citation expansion does not find a retraction cluster.** `cited_by` is ranked by citation count, so retracted follow-ups with few citations sit outside the window at any limit. Measured: walking 100 citing works from a retracted paper surfaced none of the three retracted papers from the same laboratory, all of which OpenAlex already flags when looked up directly. Finding the cluster needs an author search, which this server does not have — see Known gaps.
- **Corroboration means little inside `expand_citations`.** A well-cited paper has thousands of citing works; each index returns its own slice and only OpenAlex sorts by citation count, so the slices rarely overlap. Measured: 29 unique from 29 raw across three indexes. The tool now says so in `corroboration_note` rather than letting a count of 1 read as disagreement. Corroboration remains meaningful in `search_literature`.
- **Full text is Europe PMC only**, so effectively biomedical and life sciences. A physics paper will usually return `not_in_europepmc`; use `resolve_fulltext` and read the arXiv copy.

---

## Related

- `scholarly-source-gathering` skill — the discovery and verification method
- `scientific-research-publisher` skill — verified sources → typeset PDF

Once this server is live, `references/access_routes.md` in the gathering skill can be trimmed: route B and the `web_fetch` substitution trap stop applying when the MCP is connected.
