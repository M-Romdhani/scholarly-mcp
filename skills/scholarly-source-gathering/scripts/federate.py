#!/usr/bin/env python3
"""Federated scholarly search across OpenAlex, Semantic Scholar, Crossref and arXiv.

Runs the same query against independent indexes, deduplicates, and records which
indexes found each paper (corroboration signal). Stdlib only.

Requires network egress. In sandboxes that block it you will get 403s — that is
route B, not a bug. See references/access_routes.md.

Usage:
    python3 federate.py "query terms" --email you@example.org [--out candidates.json]
                        [--openalex-key KEY] [--s2-key KEY] [--limit 25]
                        [--sources openalex,s2,crossref,arxiv]

Credentials also read from env: OPENALEX_API_KEY, S2_API_KEY, CONTACT_EMAIL.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = "scholarly-source-gathering/1.0 (mailto:{email})"


def get(url, email, headers=None, retries=3, timeout=30):
    """GET with polite UA, backoff on 429/5xx. Returns bytes or raises."""
    hdrs = {"User-Agent": UA.format(email=email), "Accept": "application/json"}
    hdrs.update(headers or {})
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                wait = int(e.headers.get("Retry-After", 2 ** (attempt + 1)))
                time.sleep(min(wait, 30))
                continue
            if 500 <= e.code < 600:
                time.sleep(2 ** attempt)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(2 ** attempt)
    raise last


def norm_doi(doi):
    if not doi:
        return None
    d = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", str(doi).strip(), flags=re.I)
    return d.rstrip(".,;").lower() or None


def norm_title(t):
    if not t:
        return ""
    t = re.sub(r"<[^>]+>", " ", str(t))
    t = re.sub(r"[^a-z0-9 ]", " ", t.lower())
    t = re.sub(r"\b(the|a|an|of|on|in|for|and)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def rec(source, doi=None, title=None, year=None, authors=None, venue=None,
        type_=None, cited_by=None, oa_url=None, extra=None):
    return {
        "doi": norm_doi(doi), "title": title, "year": year,
        "authors": authors or [], "venue": venue, "type": type_,
        "cited_by_count": cited_by, "oa_url": oa_url,
        "found_by": [source], **(extra or {}),
    }


# ---------------------------------------------------------------- sources

def search_openalex(q, email, limit, key):
    params = {"search": q, "per_page": min(limit, 100),
              "select": "doi,title,publication_year,authorships,primary_location,"
                        "type,cited_by_count,open_access,is_retracted"}
    if key:
        params["api_key"] = key
    else:
        params["mailto"] = email
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    body, headers = get(url, email)
    for h, v in headers.items():
        if "budget" in h.lower() or "spend" in h.lower() or "credit" in h.lower():
            print(f"  [openalex] {h}: {v}", file=sys.stderr)
    out = []
    for w in json.loads(body).get("results", []):
        loc = (w.get("primary_location") or {}).get("source") or {}
        out.append(rec("openalex", w.get("doi"), w.get("title"),
                       w.get("publication_year"),
                       [a["author"]["display_name"] for a in w.get("authorships", [])
                        if a.get("author")],
                       loc.get("display_name"), w.get("type"), w.get("cited_by_count"),
                       (w.get("open_access") or {}).get("oa_url"),
                       {"is_retracted": w.get("is_retracted")}))
    return out


def search_s2(q, email, limit, key):
    params = {"query": q, "limit": min(limit, 100),
              "fields": "title,authors,year,venue,externalIds,citationCount,publicationTypes"}
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(params)
    body, _ = get(url, email, headers={"x-api-key": key} if key else None)
    out = []
    for p in json.loads(body).get("data", []):
        ids = p.get("externalIds") or {}
        out.append(rec("semanticscholar", ids.get("DOI"), p.get("title"), p.get("year"),
                       [a.get("name") for a in p.get("authors", [])],
                       p.get("venue"), (p.get("publicationTypes") or [None])[0],
                       p.get("citationCount"), None,
                       {"arxiv_id": ids.get("ArXiv")}))
    return out


def search_crossref(q, email, limit, _key=None):
    params = {"query.bibliographic": q, "rows": min(limit, 100), "mailto": email,
              "select": "DOI,title,author,container-title,issued,type,is-referenced-by-count"}
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    body, _ = get(url, email)
    out = []
    for w in json.loads(body).get("message", {}).get("items", []):
        issued = (w.get("issued") or {}).get("date-parts") or [[None]]
        out.append(rec("crossref", w.get("DOI"),
                       (w.get("title") or [None])[0], issued[0][0],
                       [f"{a.get('given','')} {a.get('family','')}".strip()
                        for a in w.get("author", [])],
                       (w.get("container-title") or [None])[0], w.get("type"),
                       w.get("is-referenced-by-count"), None))
    return out


def search_arxiv(q, email, limit, _key=None):
    params = {"search_query": f"all:{q}", "max_results": min(limit, 100),
              "sortBy": "relevance"}
    url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)
    body, _ = get(url, email, headers={"Accept": "application/atom+xml"})
    ns = {"a": "http://www.w3.org/2005/Atom", "ar": "http://arxiv.org/schemas/atom"}
    out = []
    for e in ET.fromstring(body).findall("a:entry", ns):
        aid = (e.findtext("a:id", "", ns) or "").rsplit("/", 1)[-1]
        doi_el = e.find("ar:doi", ns)
        out.append(rec("arxiv", doi_el.text if doi_el is not None else None,
                       (e.findtext("a:title", "", ns) or "").strip(),
                       (e.findtext("a:published", "", ns) or "")[:4] or None,
                       [n.text for n in e.findall("a:author/a:name", ns)],
                       "arXiv", "preprint", None,
                       f"https://arxiv.org/abs/{aid}",
                       {"arxiv_id": aid, "arxiv_version": aid.split("v")[-1] if "v" in aid else None}))
    time.sleep(3)  # arXiv asks for ~1 req / 3s
    return out


SOURCES = {"openalex": search_openalex, "s2": search_s2,
           "crossref": search_crossref, "arxiv": search_arxiv}
KEY_ENV = {"openalex": "OPENALEX_API_KEY", "s2": "S2_API_KEY"}


# ---------------------------------------------------------------- merge

def merge(records):
    """Dedup by DOI, then by normalized title+year(+/-1). Union of found_by."""
    by_doi, by_title, out = {}, {}, []

    def absorb(dst, src):
        for s in src["found_by"]:
            if s not in dst["found_by"]:
                dst["found_by"].append(s)
        for k, v in src.items():
            if k != "found_by" and dst.get(k) in (None, "", []) and v not in (None, "", []):
                dst[k] = v

    for r in records:
        if r["doi"] and r["doi"] in by_doi:
            absorb(by_doi[r["doi"]], r)
            continue
        key = (norm_title(r["title"]), r["year"])
        hit = None
        if key[0]:
            for yr in (r["year"], (r["year"] or 0) + 1, (r["year"] or 0) - 1):
                if (key[0], yr) in by_title:
                    hit = by_title[(key[0], yr)]
                    break
        if hit:
            absorb(hit, r)
            if r["doi"]:
                by_doi[r["doi"]] = hit
            continue
        out.append(r)
        if r["doi"]:
            by_doi[r["doi"]] = r
        if key[0]:
            by_title[key] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--email", default=os.environ.get("CONTACT_EMAIL"))
    ap.add_argument("--out", default="candidates.json")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--openalex-key", default=os.environ.get("OPENALEX_API_KEY"))
    ap.add_argument("--s2-key", default=os.environ.get("S2_API_KEY"))
    ap.add_argument("--sources", default="openalex,s2,crossref,arxiv")
    args = ap.parse_args()

    if not args.email:
        sys.exit("error: --email or CONTACT_EMAIL required — these APIs expect "
                 "contact info, and Crossref's polite pool depends on it")

    wanted = [s.strip() for s in args.sources.split(",") if s.strip()]
    if not args.openalex_key and "openalex" in wanted:
        print("warning: no OpenAlex key — you get $0.10/day instead of $1.00/day. "
              "Free key: openalex.org/settings/api", file=sys.stderr)

    keys = {"openalex": args.openalex_key, "s2": args.s2_key}
    all_recs, failures = [], {}

    for name in wanted:
        fn = SOURCES.get(name)
        if not fn:
            print(f"warning: unknown source '{name}'", file=sys.stderr)
            continue
        try:
            found = fn(args.query, args.email, args.limit, keys.get(name))
            all_recs.extend(found)
            print(f"  {name}: {len(found)}", file=sys.stderr)
        except Exception as e:
            failures[name] = f"{type(e).__name__}: {e}"
            print(f"  {name}: FAILED — {e}", file=sys.stderr)

    merged = merge(all_recs)
    for r in merged:
        r["corroboration"] = len(r["found_by"])

    result = {
        "query": args.query,
        "sources_queried": wanted,
        "sources_failed": failures,
        "raw_count": len(all_recs),
        "merged_count": len(merged),
        "multi_index_count": sum(1 for r in merged if r["corroboration"] > 1),
        "candidates": sorted(merged, key=lambda r: (-r["corroboration"],
                                                    -(r.get("cited_by_count") or 0))),
    }
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n{len(all_recs)} raw → {len(merged)} unique; "
          f"{result['multi_index_count']} found by >1 index → {args.out}")
    if failures:
        print(f"NOTE: {len(failures)} source(s) failed — coverage is incomplete, "
              f"say so when reporting results.")
    print("Next: verify_dois.py — nothing here is verified yet.")


if __name__ == "__main__":
    main()
