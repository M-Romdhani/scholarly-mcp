"""Adapters for each scholarly index, normalizing to one record shape.

Every URL here is built via http.build_url from validated parameters. No
function in this module accepts a URL.
"""
import re
import unicodedata
import xml.etree.ElementTree as ET
from typing import Any

from . import config
from .http import FetchError, build_url, fetch, fetch_json


def norm_doi(doi: Any) -> str | None:
    if not doi:
        return None
    d = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", str(doi).strip(), flags=re.I)
    d = d.rstrip(".,;)").lower()
    return d or None


def validate_doi(doi: str) -> str:
    """Normalize and validate. Rejects anything that could escape a URL path."""
    d = norm_doi(doi)
    if not d or not config.DOI_RE.match(d):
        raise ValueError(
            f"not a well-formed DOI: {doi!r}. Expected 10.xxxx/suffix."
        )
    # A DOI suffix may contain "/", and build_url keeps "/" unescaped so the DOI
    # stays one path. That means the regex alone still admits
    # `10.1234/../../v2/x`, which resolves to a different endpoint on an
    # allowlisted host. Reject relative and empty segments explicitly.
    if any(seg in config.DOI_BAD_SEGMENTS for seg in d.split("/")[1:]):
        raise ValueError(
            f"DOI contains an empty or relative path segment: {doi!r}"
        )
    return d


def norm_title(t: Any) -> str:
    if not t:
        return ""
    t = re.sub(r"<[^>]+>", " ", str(t))
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-z0-9 ]", " ", t.lower())
    t = re.sub(r"\b(the|a|an|of|on|in|for|and|to)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _record(found_by: str, **kw) -> dict:
    base = {
        "doi": None, "title": None, "year": None, "authors": [], "venue": None,
        "type": None, "cited_by_count": None, "oa_url": None,
        "abstract": None, "is_retracted": None, "arxiv_id": None,
        "openalex_id": None, "found_by": [found_by],
    }
    base.update({k: v for k, v in kw.items() if k in base or k not in base})
    base["doi"] = norm_doi(base.get("doi"))
    base["found_by"] = [found_by]
    return base


# --------------------------------------------------------------- OpenAlex

OA_SELECT = ("id,doi,title,publication_year,authorships,primary_location,type,"
             "cited_by_count,open_access,is_retracted,referenced_works")


def _oa_params(extra: dict) -> dict:
    p = dict(extra)
    if config.OPENALEX_API_KEY:
        p["api_key"] = config.OPENALEX_API_KEY
    elif config.CONTACT_EMAIL:
        p["mailto"] = config.CONTACT_EMAIL
    return p


def _oa_record(w: dict) -> dict:
    loc = (w.get("primary_location") or {}).get("source") or {}
    return _record(
        "openalex",
        doi=w.get("doi"),
        title=w.get("title"),
        year=w.get("publication_year"),
        authors=[a["author"]["display_name"] for a in w.get("authorships") or []
                 if a.get("author")],
        venue=loc.get("display_name"),
        type=w.get("type"),
        cited_by_count=w.get("cited_by_count"),
        oa_url=(w.get("open_access") or {}).get("oa_url"),
        is_retracted=w.get("is_retracted"),
        openalex_id=(w.get("id") or "").rsplit("/", 1)[-1] or None,
        referenced_works=[r.rsplit("/", 1)[-1] for r in w.get("referenced_works") or []],
    )


def openalex_search(query: str, limit: int) -> list[dict]:
    url = build_url("api.openalex.org", "works", _oa_params({
        "search": query, "per_page": min(limit, 100), "select": OA_SELECT,
    }))
    return [_oa_record(w) for w in (fetch_json(url).get("results") or [])]


def openalex_by_doi(doi: str) -> dict | None:
    """Singleton lookup — free and uncapped under the 2026 pricing model."""
    url = build_url("api.openalex.org", f"works/doi:{validate_doi(doi)}",
                    _oa_params({"select": OA_SELECT}))
    try:
        return _oa_record(fetch_json(url))
    except FetchError as e:
        if e.status == 404:
            return None
        raise


def openalex_cited_by(openalex_id: str, limit: int) -> list[dict]:
    """Forward citations: what cites this work."""
    if not re.match(r"^W\d+$", openalex_id):
        raise ValueError(f"not an OpenAlex work id: {openalex_id!r}")
    url = build_url("api.openalex.org", "works", _oa_params({
        "filter": f"cites:{openalex_id}", "per_page": min(limit, 100),
        "select": OA_SELECT, "sort": "cited_by_count:desc",
    }))
    return [_oa_record(w) for w in (fetch_json(url).get("results") or [])]


def openalex_batch(ids: list[str], limit: int) -> list[dict]:
    """Hydrate up to 100 works by OpenAlex id in one filtered call."""
    ids = [i for i in ids if re.match(r"^W\d+$", i)][:min(limit, 100)]
    if not ids:
        return []
    url = build_url("api.openalex.org", "works", _oa_params({
        "filter": f"openalex_id:{'|'.join(ids)}", "per_page": len(ids),
        "select": OA_SELECT,
    }))
    return [_oa_record(w) for w in (fetch_json(url).get("results") or [])]


# --------------------------------------------------------------- Crossref

CR_SELECT = ("DOI,title,author,container-title,issued,type,volume,page,publisher,"
             "is-referenced-by-count,update-to,updated-by,relation,abstract")


def _cr_record(w: dict) -> dict:
    parts = ((w.get("issued") or {}).get("date-parts") or [[None]])[0]
    return _record(
        "crossref",
        doi=w.get("DOI"),
        title=(w.get("title") or [None])[0],
        year=parts[0] if parts else None,
        authors=[f"{a.get('given', '')} {a.get('family', '')}".strip()
                 for a in w.get("author") or []],
        venue=(w.get("container-title") or [None])[0],
        type=w.get("type"),
        cited_by_count=w.get("is-referenced-by-count"),
        volume=w.get("volume"),
        pages=w.get("page"),
        publisher=w.get("publisher"),
    )


def crossref_search(query: str, limit: int) -> list[dict]:
    url = build_url("api.crossref.org", "works", {
        "query.bibliographic": query, "rows": min(limit, 100),
        "select": CR_SELECT, "mailto": config.CONTACT_EMAIL,
    })
    items = (fetch_json(url).get("message") or {}).get("items") or []
    return [_cr_record(w) for w in items]


def crossref_work(doi: str) -> dict:
    """Full Crossref record. The bibliographic truth layer."""
    url = build_url("api.crossref.org", f"works/{validate_doi(doi)}",
                    {"mailto": config.CONTACT_EMAIL})
    return (fetch_json(url).get("message") or {})


RETRACTION_KINDS = {"retraction", "withdrawal", "removal"}
CONCERN_KINDS = {"expression_of_concern", "expression of concern", "concern"}

# Severity precedence. Crossref lists updates in deposit order, not severity
# order, so a record whose corrections happen to be listed before its expression
# of concern must not be downgraded to "corrected".
STATUS_RANK = {"ok": 0, "corrected": 1, "concern": 2, "retracted": 3}

# Crossref models the relationship in both directions:
#   `update-to`  — "this record updates that one"  → lives on the NOTICE
#   `updated-by` — "this record is updated by that one" → lives on the PAPER
# Verifying a paper means reading `updated-by`. Reading only `update-to`
# classifies every retracted paper as clean, because the retracted paper does not
# carry `update-to` at all — the retraction notice does.
UPDATE_FIELDS = ("updated-by", "update-to")


def classify_updates(msg: dict) -> tuple[str, list[str]]:
    """Classify a work's publication status from its Crossref update records —
    populated from Retraction Watch since Crossref acquired that database.
    Distinguishes retraction from correction from expression of concern, which
    OpenAlex's boolean cannot."""
    status, notes = "ok", []
    for field in UPDATE_FIELDS:
        for u in msg.get(field) or []:
            kind = (u.get("type") or "").lower().replace("-", "_").replace(" ", "_")
            direction = ("this work was updated by" if field == "updated-by"
                         else "this work is itself an update to")
            notes.append(f"{u.get('label') or u.get('type') or 'update'} "
                         f"({u.get('DOI') or 'no DOI'}) — {direction} it")
            if kind in RETRACTION_KINDS:
                candidate = "retracted"
            elif kind in CONCERN_KINDS:
                candidate = "concern"
            else:
                candidate = "corrected"
            if STATUS_RANK[candidate] > STATUS_RANK[status]:
                status = candidate
    return status, notes


# -------------------------------------------------------- Semantic Scholar

S2_FIELDS = "title,authors,year,venue,externalIds,citationCount,publicationTypes,abstract"


def _s2_record(p: dict) -> dict:
    ids = p.get("externalIds") or {}
    return _record(
        "semanticscholar",
        doi=ids.get("DOI"),
        title=p.get("title"),
        year=p.get("year"),
        authors=[a.get("name") for a in p.get("authors") or []],
        venue=p.get("venue"),
        type=(p.get("publicationTypes") or [None])[0],
        cited_by_count=p.get("citationCount"),
        abstract=p.get("abstract"),
        arxiv_id=ids.get("ArXiv"),
    )


def _s2_headers() -> dict:
    return {"x-api-key": config.S2_API_KEY} if config.S2_API_KEY else {}


def s2_search(query: str, limit: int) -> list[dict]:
    url = build_url("api.semanticscholar.org", "graph/v1/paper/search", {
        "query": query, "limit": min(limit, 100), "fields": S2_FIELDS,
    })
    data = fetch_json(url, extra_headers=_s2_headers())
    return [_s2_record(p) for p in (data.get("data") or [])]


def s2_references(doi: str, limit: int) -> list[dict]:
    """Backward citations: what this paper cites."""
    url = build_url("api.semanticscholar.org",
                    f"graph/v1/paper/DOI:{validate_doi(doi)}/references",
                    {"limit": min(limit, 100), "fields": S2_FIELDS})
    data = fetch_json(url, extra_headers=_s2_headers())
    return [_s2_record(item["citedPaper"]) for item in (data.get("data") or [])
            if item.get("citedPaper")]


def s2_citations(doi: str, limit: int) -> list[dict]:
    url = build_url("api.semanticscholar.org",
                    f"graph/v1/paper/DOI:{validate_doi(doi)}/citations",
                    {"limit": min(limit, 100), "fields": S2_FIELDS})
    data = fetch_json(url, extra_headers=_s2_headers())
    return [_s2_record(item["citingPaper"]) for item in (data.get("data") or [])
            if item.get("citingPaper")]


# ------------------------------------------------------------------ arXiv

def arxiv_search(query: str, limit: int) -> list[dict]:
    url = build_url("export.arxiv.org", "api/query", {
        "search_query": f"all:{query}", "max_results": min(limit, 100),
        "sortBy": "relevance",
    })
    body, _ = fetch(url, accept="application/atom+xml")
    ns = {"a": "http://www.w3.org/2005/Atom", "ar": "http://arxiv.org/schemas/atom"}
    out = []
    for e in ET.fromstring(body).findall("a:entry", ns):
        aid = (e.findtext("a:id", "", ns) or "").rsplit("/", 1)[-1]
        doi_el = e.find("ar:doi", ns)
        out.append(_record(
            "arxiv",
            doi=doi_el.text if doi_el is not None else None,
            title=" ".join((e.findtext("a:title", "", ns) or "").split()),
            year=int((e.findtext("a:published", "", ns) or "0000")[:4]) or None,
            authors=[n.text for n in e.findall("a:author/a:name", ns)],
            venue="arXiv", type="preprint",
            oa_url=f"https://arxiv.org/abs/{aid}" if aid else None,
            arxiv_id=aid,
            abstract=" ".join((e.findtext("a:summary", "", ns) or "").split()) or None,
        ))
    return out


# -------------------------------------------------------------- Unpaywall

def unpaywall(doi: str) -> dict:
    url = build_url("api.unpaywall.org", f"v2/{validate_doi(doi)}",
                    {"email": config.CONTACT_EMAIL})
    return fetch_json(url)


# --------------------------------------------------------------- DataCite

def datacite_work(doi: str) -> dict | None:
    """Some legitimate DOIs (datasets, some preprints) are registered with
    DataCite rather than Crossref. Check here before declaring a DOI dead."""
    url = build_url("api.datacite.org", f"dois/{validate_doi(doi)}")
    try:
        return (fetch_json(url).get("data") or {}).get("attributes")
    except FetchError as e:
        if e.status == 404:
            return None
        raise


SEARCH_SOURCES = {
    "openalex": openalex_search,
    "crossref": crossref_search,
    "semanticscholar": s2_search,
    "arxiv": arxiv_search,
}
