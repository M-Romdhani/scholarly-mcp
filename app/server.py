"""Scholarly source MCP server.

Five task-shaped tools. No generic URL passthrough — see identity.md for why
that shape was rejected.

Every tool reports partial failure explicitly. A source that could not be
reached appears in `sources_failed` with the reason; it never silently vanishes
into a smaller result set that looks complete.
"""
import logging
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from . import config, merge, sources
from .http import FetchError, SecurityError, openalex_budget

log = logging.getLogger("scholarly-mcp")

mcp = MCPServer(
    name="scholarly-sources",
    version="1.0.0",
    instructions=(
        "Federated scholarly literature access: OpenAlex, Crossref, Semantic "
        "Scholar, arXiv, Unpaywall. Use search_literature to discover, "
        "verify_doi to confirm a paper is real and get authoritative metadata, "
        "expand_citations to walk the citation graph, and resolve_fulltext to "
        "find legal open-access copies.\n\n"
        "Cost model matters: on OpenAlex, searching costs money but single "
        "lookups by DOI are free and uncapped. Prefer a few good searches "
        "followed by citation expansion over many searches. Call budget_status "
        "if you are running long.\n\n"
        "Metadata from discovery indexes is unverified — author order and year "
        "are often wrong. Nothing should be cited until verify_doi has "
        "confirmed it."
    ),
)


def _fail(exc: Exception) -> str:
    if isinstance(exc, SecurityError):
        return f"refused: {exc}"
    if isinstance(exc, FetchError):
        return f"unreachable: {exc}"
    if isinstance(exc, ValueError):
        return f"invalid input: {exc}"
    return f"{type(exc).__name__}: {exc}"


@mcp.tool(
    description=(
        "Search several independent scholarly indexes for the same query, then "
        "merge and deduplicate. Returns candidates ranked by corroboration (how "
        "many independent indexes found each paper) then citation count. "
        "Corroboration is a real signal: a paper found by two independent "
        "indexes is more likely to be both real and central. Results are NOT "
        "verified — run verify_doi before citing anything."
    ),
)
def search_literature(
    query: Annotated[str, Field(description="Search terms. Natural language or keywords.")],
    sources_to_query: Annotated[
        list[Literal["openalex", "crossref", "semanticscholar", "arxiv"]],
        Field(description="Which indexes to query. Use at least two independent "
                          "ones; a single index's ranking becomes your view of "
                          "the field. 'semanticscholar' rate-limits hard without "
                          "a key — add it when S2_API_KEY is configured.")
    ] = ["openalex", "crossref"],
    limit: Annotated[int, Field(ge=1, le=100,
                                description="Max results per index.")] = 25,
) -> dict[str, Any]:
    all_recs: list[dict] = []
    failed: dict[str, str] = {}

    for name in sources_to_query:
        fn = sources.SEARCH_SOURCES.get(name)
        if fn is None:
            failed[name] = "unknown source"
            continue
        try:
            found = merge.cached(
                f"search:{name}:{limit}:{query}",
                lambda fn=fn: fn(query, limit),
                ttl=3600,
            )
            all_recs.extend(found)
        except Exception as e:
            failed[name] = _fail(e)
            log.warning("search %s failed: %s", name, e)

    merged = merge.merge(all_recs)
    merged.sort(key=lambda r: (-r.get("corroboration", 0),
                               -(r.get("cited_by_count") or 0)))

    result = {
        "query": query,
        "sources_queried": sources_to_query,
        "sources_failed": failed,
        "raw_count": len(all_recs),
        "unique_count": len(merged),
        "multi_index_count": sum(1 for r in merged if r.get("corroboration", 0) > 1),
        "verified": False,
        "candidates": merged,
    }
    if failed:
        result["coverage_warning"] = (
            f"{len(failed)} of {len(sources_to_query)} sources failed. Coverage "
            f"is incomplete — say so when reporting these results."
        )
    if "semanticscholar" in sources_to_query and not config.S2_API_KEY:
        result["semanticscholar_warning"] = (
            "Semantic Scholar was queried without S2_API_KEY. Unauthenticated "
            "requests are rate-limited aggressively and commonly return 429; if "
            "it appears in sources_failed, that is why.")
    if not config.OPENALEX_API_KEY and "openalex" in sources_to_query:
        result["budget_warning"] = (
            "No OpenAlex API key configured: budget is $0.10/day instead of "
            "$1.00/day. A free key takes 30 seconds at openalex.org/settings/api."
        )
    return result


@mcp.tool(
    description=(
        "Verify a DOI against Crossref and return authoritative bibliographic "
        "metadata, plus retraction status. This is the truth layer: discovery "
        "indexes routinely get author order and publication year wrong. Checks "
        "retraction against BOTH Crossref update-to records (which distinguish "
        "retraction from correction from expression of concern) and OpenAlex "
        "is_retracted, because neither is sufficient alone. Falls back to "
        "DataCite for dataset and preprint DOIs. If this fails, the DOI does "
        "not resolve and the source must not be cited."
    ),
)
def verify_doi(
    doi: Annotated[str, Field(description="DOI, with or without the https://doi.org/ prefix.")],
) -> dict[str, Any]:
    try:
        clean = sources.validate_doi(doi)
    except ValueError as e:
        return {"doi": doi, "verified": False, "error": _fail(e)}

    out: dict[str, Any] = {"doi": clean, "verified": False}

    try:
        msg = merge.cached(f"crossref:work:{clean}",
                           lambda: sources.crossref_work(clean))
    except Exception as e:
        # A 404 means the DOI does not exist. Anything else — proxy denial,
        # timeout, DNS — means we could not check. These warrant opposite
        # guidance, and conflating them is exactly the silent degradation this
        # server exists to prevent (identity.md rule 6).
        reachable = not (isinstance(e, FetchError) and e.status is None)
        not_found = isinstance(e, FetchError) and e.status == 404

        dc = None
        if not_found or reachable:
            # Datasets and some preprints are registered with DataCite.
            try:
                dc = merge.cached(f"datacite:{clean}",
                                  lambda: sources.datacite_work(clean))
            except Exception:
                dc = None
        if dc:
            return {
                "doi": clean, "verified": True, "registry": "datacite",
                "title": (dc.get("titles") or [{}])[0].get("title"),
                "year": dc.get("publicationYear"),
                "authors": [c.get("name") for c in dc.get("creators") or []],
                "venue": dc.get("publisher"),
                "type": (dc.get("types") or {}).get("resourceTypeGeneral"),
                "publication_status": "ok",
                "note": "Registered with DataCite, not Crossref — typically a "
                        "dataset, software, or preprint.",
            }

        out["error"] = _fail(e)
        if not_found:
            out["status"] = "not_found"
            out["interpretation"] = (
                "This DOI is not registered with Crossref or DataCite. Treat as "
                "unverifiable: do not cite it, and record it as rejected with "
                "this reason."
            )
        else:
            out["status"] = "unreachable"
            out["interpretation"] = (
                "Verification could not be performed — the registry was not "
                "reachable. This says NOTHING about whether the paper exists. "
                "Do not record it as rejected, and do not cite it as verified. "
                "Retry, or report to the user that verification was unavailable."
            )
        return out

    rec = sources._cr_record(msg)
    status, notes = sources.classify_updates(msg)

    out.update({
        "verified": True,
        "registry": "crossref",
        "title": rec["title"],
        "authors": rec["authors"],
        "year": rec["year"],
        "venue": rec["venue"],
        "volume": rec.get("volume"),
        "pages": rec.get("pages"),
        "publisher": rec.get("publisher"),
        "type": rec["type"],
        "cited_by_count": rec["cited_by_count"],
        "publication_status": status,
        "status_notes": notes,
    })

    # Cross-check OpenAlex. Its is_retracted boolean has conflated corrections
    # and expressions of concern with retractions, and misses ~7% of known
    # retractions — so it is a screen, never a verdict.
    try:
        oa = merge.cached(f"openalex:doi:{clean}",
                          lambda: sources.openalex_by_doi(clean))
        if oa:
            out["openalex_id"] = oa.get("openalex_id")
            out["openalex_is_retracted"] = oa.get("is_retracted")
            if oa.get("is_retracted") and status == "ok":
                out["publication_status"] = "disputed_flag"
                out["status_notes"] = notes + [
                    "OpenAlex flags this as retracted but Crossref shows no "
                    "retraction record. OpenAlex's boolean conflates "
                    "corrections and expressions of concern with retractions. "
                    "Check the publisher page before relying on this source."
                ]
            elif status == "retracted" and oa.get("is_retracted") is False:
                out["status_notes"] = notes + [
                    "Crossref records a retraction that OpenAlex has not "
                    "flagged. Trust Crossref."
                ]
    except Exception as e:
        out["openalex_crosscheck_error"] = _fail(e)

    if out["publication_status"] == "disputed_flag":
        out["guidance"] = ("DISPUTED. OpenAlex flags a retraction that Crossref "
                           "does not record. Do not cite this as clean evidence "
                           "until you have checked the publisher's page for the "
                           "article directly, and state what you found.")
    elif out["publication_status"] == "retracted":
        out["guidance"] = ("RETRACTED. Do not cite as evidence. It may be cited "
                           "when discussing the retraction itself, which must be "
                           "stated in the text.")
    elif out["publication_status"] == "concern":
        out["guidance"] = ("Subject to an expression of concern. Citable, but "
                           "the concern must be stated.")
    elif out["publication_status"] == "corrected":
        out["guidance"] = ("A correction exists. Check whether it affects the "
                           "specific claim you are drawing on.")
    return out


@mcp.tool(
    description=(
        "Walk the citation graph from a paper. direction='references' returns "
        "what the paper cites (finds foundational work that keyword search "
        "buries because its terminology is decades old); direction='cited_by' "
        "returns what cites it (finds replications, corrections and rebuttals, "
        "which often have few citations and rank low in search). This is the "
        "highest-value discovery operation and, via OpenAlex singleton lookups, "
        "the cheapest — prefer it over running more searches."
    ),
)
def expand_citations(
    doi: Annotated[str, Field(description="DOI of the paper to expand from.")],
    direction: Annotated[Literal["references", "cited_by"],
                         Field(description="'references' = backward (what it "
                                           "cites), 'cited_by' = forward (what "
                                           "cites it).")] = "cited_by",
    limit: Annotated[int, Field(ge=1, le=100)] = 25,
) -> dict[str, Any]:
    try:
        clean = sources.validate_doi(doi)
    except ValueError as e:
        return {"doi": doi, "error": _fail(e), "results": []}

    results: list[dict] = []
    failed: dict[str, str] = {}

    # Semantic Scholar handles both directions directly from a DOI.
    try:
        fn = sources.s2_references if direction == "references" else sources.s2_citations
        results.extend(merge.cached(f"s2:{direction}:{clean}:{limit}",
                                    lambda: fn(clean, limit)))
    except Exception as e:
        failed["semanticscholar"] = _fail(e)

    # OpenAlex as the independent second channel.
    try:
        oa = merge.cached(f"openalex:doi:{clean}",
                          lambda: sources.openalex_by_doi(clean))
        if oa:
            if direction == "references":
                refs = oa.get("referenced_works") or []
                if refs:
                    results.extend(merge.cached(
                        f"openalex:batch:{direction}:{clean}:{limit}",
                        lambda: sources.openalex_batch(refs, limit)))
            elif oa.get("openalex_id"):
                results.extend(merge.cached(
                    f"openalex:citedby:{oa['openalex_id']}:{limit}",
                    lambda: sources.openalex_cited_by(oa["openalex_id"], limit)))
        else:
            failed["openalex"] = "DOI not found in OpenAlex"
    except Exception as e:
        failed["openalex"] = _fail(e)

    merged = merge.merge(results)
    merged.sort(key=lambda r: -(r.get("cited_by_count") or 0))

    out = {
        "doi": clean,
        "direction": direction,
        "sources_failed": failed,
        "count": len(merged),
        "verified": False,
        "results": merged[:limit],
    }
    if failed:
        out["coverage_warning"] = (
            f"{len(failed)} source(s) failed; this expansion is partial.")
    if not merged and not failed:
        out["interpretation"] = (
            "No results. For 'cited_by' on a recent paper this is normal. For "
            "'references' it usually means the publisher deposited no reference "
            "list, not that the paper cites nothing."
        )
    return out


@mcp.tool(
    description=(
        "Find a legal open-access copy of a paper via Unpaywall, and report its "
        "OA status. Returns a suggested access level for the evidence ledger. "
        "Note: this reports what is AVAILABLE, not what was read. Whether you "
        "actually read the full text or only the abstract must be recorded "
        "honestly downstream — inflating that field corrupts every judgment "
        "built on the source."
    ),
)
def resolve_fulltext(
    doi: Annotated[str, Field(description="DOI to resolve.")],
) -> dict[str, Any]:
    try:
        clean = sources.validate_doi(doi)
    except ValueError as e:
        return {"doi": doi, "error": _fail(e)}

    try:
        up = merge.cached(f"unpaywall:{clean}", lambda: sources.unpaywall(clean))
    except Exception as e:
        return {"doi": clean, "error": _fail(e),
                "suggested_access": "metadata-only"}

    best = up.get("best_oa_location") or {}
    oa_status = up.get("oa_status")
    out = {
        "doi": clean,
        "is_oa": up.get("is_oa"),
        "oa_status": oa_status,
        "best_url": best.get("url_for_pdf") or best.get("url"),
        "host_type": best.get("host_type"),
        "version": best.get("version"),
        "all_locations": [
            {"url": loc.get("url_for_pdf") or loc.get("url"),
             "host_type": loc.get("host_type"), "version": loc.get("version")}
            for loc in (up.get("oa_locations") or [])[:5]
        ],
        "suggested_access": "fulltext" if up.get("is_oa") else "metadata-only",
        "reminder": ("suggested_access reflects availability only. Set the "
                     "ledger's access field to what you actually read."),
    }
    if oa_status == "bronze":
        out["caution"] = ("Bronze OA: free to read but with no open licence. "
                          "It can disappear. Prefer a gold or green location "
                          "for a durable link.")
    if best.get("version") == "submittedVersion":
        out["caution"] = ("This is the submitted (pre-peer-review) version. It "
                          "may differ from the version of record.")
    return out


@mcp.tool(
    description=(
        "Report the OpenAlex API budget as reported by its response headers, "
        "plus cache and configuration status. Call this if a session is running "
        "long or searches start failing, so you can pace spending rather than "
        "guessing. Budget only reflects calls made since this server started."
    ),
)
def budget_status() -> dict[str, Any]:
    headers, seen_at = openalex_budget()
    lower = {k.lower(): v for k, v in headers.items()}

    def _num(name):
        try:
            return float(lower[name])
        except (KeyError, TypeError, ValueError):
            return None

    remaining_usd = _num("x-ratelimit-remaining-usd")
    limit_usd = _num("x-ratelimit-limit-usd")
    summary = {
        "remaining_usd": remaining_usd,
        "limit_usd": limit_usd,
        "spent_usd": (round(limit_usd - remaining_usd, 6)
                      if None not in (limit_usd, remaining_usd) else None),
        "calls_remaining": _num("x-ratelimit-remaining"),
        "calls_limit": _num("x-ratelimit-limit"),
        "resets_in_seconds": _num("x-ratelimit-reset"),
    }
    return {
        "openalex_budget": summary if headers else None,
        "openalex_budget_headers": headers or None,
        "budget_last_seen_at": seen_at,
        "note": ("Empty means no OpenAlex call has been made yet this process. "
                 "The whole x-ratelimit-* header family is captured, so a rename "
                 "within that family still shows up in "
                 "openalex_budget_headers even if openalex_budget cannot parse it."),
        "daily_free_budget": "$1.00/day" if config.OPENALEX_API_KEY else "$0.10/day (no key)",
        "cost_model": {
            "single lookup by DOI/ID": "free, uncapped",
            "list+filter": "$0.10 per 1,000",
            "search": "$1.00 per 1,000",
            "content download": "$10.00 per 1,000",
        },
        "strategy": ("Searching costs money; DOI lookups are free. Prefer a few "
                     "good searches then citation expansion."),
        "cache": merge.cache_stats(),
        "config": config.startup_report(),
    }
