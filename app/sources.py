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


# OpenAlex treats * and ? as wildcard operators and answers HTTP 400 when they
# appear in a search string. Tested against the live API: every other punctuation
# character passes, these two do not. It matters because entities are sometimes
# named with them — "Aβ*56" is the actual name of a molecule — so searching for
# the thing by its real name crashed the call rather than returning nothing.
_OA_SEARCH_BREAKS = str.maketrans({"*": " ", "?": " "})


def _oa_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.translate(_OA_SEARCH_BREAKS)).strip()


def openalex_search(query: str, limit: int) -> list[dict]:
    url = build_url("api.openalex.org", "works", _oa_params({
        "search": _oa_query(query), "per_page": min(limit, 100),
        "select": OA_SELECT,
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


# ------------------------------------------------------------ Europe PMC

EPMC_BASE = "europepmc/webservices/rest"

# MEDLINE publication types, mirrored by Europe PMC. This is a retraction signal
# independent of both Crossref and OpenAlex — indexed by NLM curators rather than
# derived from publisher deposits, so it catches cases the other two miss.
EPMC_RETRACTED_TYPES = {"retracted publication", "retraction of publication"}
EPMC_CONCERN_TYPES = {"expression of concern"}
# commentCorrectionList entries point from this paper to the notice about it.
EPMC_RETRACTION_LINKS = {"retraction in"}
EPMC_CONCERN_LINKS = {"expression of concern in"}


def _epmc_authors(r: dict) -> list[str]:
    authors = [a.get("fullName") for a in
               ((r.get("authorList") or {}).get("author") or [])
               if a.get("fullName")]
    if authors:
        return authors
    # authorString is "Kucsko G, Maurer PC, ..." — usable when authorList is absent.
    return [a.strip() for a in (r.get("authorString") or "").rstrip(".").split(",")
            if a.strip()]


def _epmc_type(pub_types: list) -> str | None:
    """MEDLINE lists funding categories alongside document types, and the
    funding ones often sort first — "Research Support, Non-U.S. Gov't" is not a
    document type. Prefer anything else."""
    usable = [t for t in pub_types
              if t and not t.lower().startswith("research support")]
    return (usable or pub_types or [None])[0]


def _epmc_record(r: dict) -> dict:
    ji = r.get("journalInfo") or {}
    year = r.get("pubYear")
    return _record(
        "europepmc",
        doi=r.get("doi"),
        title=(r.get("title") or "").rstrip("."),
        year=int(year) if str(year).isdigit() else None,
        authors=_epmc_authors(r),
        venue=(ji.get("journal") or {}).get("title"),
        type=_epmc_type((r.get("pubTypeList") or {}).get("pubType") or []),
        cited_by_count=r.get("citedByCount"),
        abstract=r.get("abstractText"),
        pmid=r.get("pmid"),
        pmcid=r.get("pmcid"),
        # isOpenAccess, NOT inEPMC, is what gates fullTextXML: a record can be
        # inEPMC=Y and still 404 on full text when it is not open access.
        is_open_access=(r.get("isOpenAccess") == "Y"),
        pub_types=(r.get("pubTypeList") or {}).get("pubType") or [],
        comment_corrections=[
            {"type": c.get("type"), "reference": c.get("reference"),
             "pmid": c.get("id")}
            for c in ((r.get("commentCorrectionList") or {}).get("commentCorrection")
                      or [])
        ],
    )


def europepmc_search(query: str, limit: int) -> list[dict]:
    url = build_url("www.ebi.ac.uk", f"{EPMC_BASE}/search", {
        "query": query, "format": "json", "resultType": "core",
        "pageSize": min(limit, 100),
    })
    data = fetch_json(url)
    return [_epmc_record(r) for r in
            ((data.get("resultList") or {}).get("result") or [])]


def europepmc_by_doi(doi: str) -> dict | None:
    """Exact DOI lookup. The quotes matter — an unquoted DOI is tokenized by the
    query parser and returns loosely-related hits rather than nothing."""
    clean = validate_doi(doi)
    url = build_url("www.ebi.ac.uk", f"{EPMC_BASE}/search", {
        "query": f'DOI:"{clean}"', "format": "json", "resultType": "core",
        "pageSize": 1,
    })
    results = ((fetch_json(url).get("resultList") or {}).get("result") or [])
    return _epmc_record(results[0]) if results else None


def epmc_publication_status(rec: dict) -> tuple[str, list[str]]:
    """Retraction status from MEDLINE publication types and correction links.

    Independent of Crossref `updated-by` and of OpenAlex `is_retracted`: this is
    NLM's own curation. Returns the same vocabulary as classify_updates so the
    two can be compared directly.
    """
    status, notes = "ok", []
    for t in rec.get("pub_types") or []:
        low = (t or "").strip().lower()
        if low in EPMC_RETRACTED_TYPES:
            status = "retracted"
            notes.append(f"MEDLINE publication type: {t}")
        elif low in EPMC_CONCERN_TYPES and status == "ok":
            status = "concern"
            notes.append(f"MEDLINE publication type: {t}")
    for c in rec.get("comment_corrections") or []:
        low = (c.get("type") or "").strip().lower()
        if low in EPMC_RETRACTION_LINKS:
            status = "retracted"
            notes.append(f"{c.get('type')}: {c.get('reference')}")
        elif low in EPMC_CONCERN_LINKS and status != "retracted":
            status = "concern"
            notes.append(f"{c.get('type')}: {c.get('reference')}")
    return status, notes


def _jats_text(el) -> str:
    return " ".join("".join(el.itertext()).split())


def europepmc_fulltext(pmcid: str) -> dict:
    """Open-access full text as JATS XML, parsed into sections.

    Only open-access records have it; `inEPMC` is not sufficient and a
    subscription record 404s here.
    """
    if not re.match(r"^PMC\d+$", pmcid or ""):
        raise ValueError(f"not a PMC id: {pmcid!r}. Expected PMC followed by digits.")
    url = build_url("www.ebi.ac.uk", f"{EPMC_BASE}/{pmcid}/fullTextXML")
    body, _ = fetch(url, accept="application/xml")
    root = ET.fromstring(body)

    sections: list[dict] = []
    front = root.find("front")
    if front is not None:
        abstract = front.find(".//abstract")
        if abstract is not None:
            sections.append({"heading": "Abstract", "text": _jats_text(abstract)})
    # Walk the body in document order. A body commonly mixes bare <p> children
    # with <sec> blocks; taking only <sec> when any exists silently drops most of
    # the article (observed: 21 of 22 paragraphs lost).
    body_el = root.find("body")
    if body_el is not None:
        loose: list[str] = []

        def flush_loose() -> None:
            if loose:
                joined = " ".join(loose).strip()
                if joined:
                    sections.append({"heading": "Body", "text": joined})
                loose.clear()

        for child in body_el:
            if child.tag == "sec":
                flush_loose()
                heading = (child.findtext("title") or "Untitled section").strip()
                text = " ".join(_jats_text(p) for p in child.findall(".//p"))
                if text:
                    sections.append({"heading": heading, "text": text})
            elif child.tag == "p":
                text = _jats_text(child)
                if text:
                    loose.append(text)
        flush_loose()

    lic = root.find(".//license")
    return {
        "pmcid": pmcid,
        "license": _jats_text(lic) if lic is not None else None,
        "sections": sections,
    }


# ---------------------------------------------------------- INSPIRE-HEP

INSPIRE_FIELDS = ("titles,dois,authors,publication_info,citation_count,"
                  "arxiv_eprints,document_type,earliest_date,preprint_date")
# INSPIRE's default ordering put 5-citation papers above the LIGO detection for
# "gravitational waves binary black hole". mostcited is the usable ranking.
INSPIRE_SORT = "mostcited"
# Collaboration papers routinely list >1000 authors; keep the record readable.
INSPIRE_MAX_AUTHORS = 25


def _inspire_record(hit: dict) -> dict:
    m = hit.get("metadata") or hit
    pub = (m.get("publication_info") or [{}])[0]
    # A record can carry several DOIs (publication, dataset, erratum). Prefer the
    # publication one rather than whichever happens to be first.
    dois = m.get("dois") or []
    doi = next((d.get("value") for d in dois if d.get("material") in (None, "publication")),
               (dois[0].get("value") if dois else None))
    year = pub.get("year")
    if not year:
        for key in ("earliest_date", "preprint_date"):
            raw = str(m.get(key) or "")[:4]
            if raw.isdigit():
                year = int(raw)
                break
    authors = [a.get("full_name") for a in (m.get("authors") or [])
               if a.get("full_name")]
    eprints = m.get("arxiv_eprints") or []
    return _record(
        "inspire",
        doi=doi,
        title=((m.get("titles") or [{}])[0]).get("title"),
        year=int(year) if str(year).isdigit() else None,
        authors=authors[:INSPIRE_MAX_AUTHORS],
        author_count=len(authors),
        venue=pub.get("journal_title"),
        type=(m.get("document_type") or [None])[0],
        cited_by_count=m.get("citation_count"),
        arxiv_id=eprints[0].get("value") if eprints else None,
    )


def inspire_search(query: str, limit: int) -> list[dict]:
    url = build_url("inspirehep.net", "api/literature", {
        "q": query, "size": min(limit, 100), "sort": INSPIRE_SORT,
        "fields": INSPIRE_FIELDS,
    })
    data = fetch_json(url)
    return [_inspire_record(h) for h in ((data.get("hits") or {}).get("hits") or [])]


# -------------------------------------------------------- OpenCitations

def _oc_ids(blob: str) -> dict:
    """OpenCitations packs identifiers into one space-separated string, e.g.
    "omid:br/06120344846 doi:10.1038/nature12373 openalex:W2159974629 pmid:23903748"."""
    out: dict[str, str] = {}
    for token in (blob or "").split():
        prefix, _, value = token.partition(":")
        if value and prefix not in out:
            out[prefix] = value
    return out


def opencitations_expand(doi: str, direction: str, limit: int) -> list[dict]:
    """Citation edges from OpenCitations — a citation index independent of both
    OpenAlex and Semantic Scholar.

    Returns identifiers only; OpenCitations carries no titles. Bare records merge
    by DOI with the other sources, which is where their value is: an edge
    confirmed by a third independent index. Records it alone contributes are
    hydrated by the caller via free OpenAlex lookups.
    """
    clean = validate_doi(doi)
    endpoint = "references" if direction == "references" else "citations"
    url = build_url("api.opencitations.net", f"index/v2/{endpoint}/doi:{clean}")
    edges = fetch_json(url)
    if not isinstance(edges, list):
        return []
    field = "cited" if direction == "references" else "citing"
    out = []
    for edge in edges[:limit]:
        ids = _oc_ids(edge.get(field))
        if not ids.get("doi"):
            continue
        out.append(_record("opencitations", doi=ids["doi"],
                           openalex_id=ids.get("openalex")))
    return out


SEARCH_SOURCES = {
    "openalex": openalex_search,
    "crossref": crossref_search,
    "semanticscholar": s2_search,
    "arxiv": arxiv_search,
    "europepmc": europepmc_search,
    "inspire": inspire_search,
}
