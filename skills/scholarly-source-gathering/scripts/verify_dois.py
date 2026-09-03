#!/usr/bin/env python3
"""Verify candidate DOIs against Crossref, screen for retractions, resolve OA.

Corrects metadata to what the publisher actually deposited, checks retraction
status against both Crossref update-nature and (if present) OpenAlex is_retracted,
and finds legal open-access copies via Unpaywall.

Usage:
    python3 verify_dois.py candidates.json --email you@example.org
                           [--out verified.json] [--rejected rejected.json]
                           [--no-unpaywall]
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from federate import get, norm_doi, norm_title  # noqa: E402

RETRACTION_KINDS = {"retraction", "withdrawal", "removal"}
CONCERN_KINDS = {"expression_of_concern", "expression of concern"}


def crossref_lookup(doi, email):
    url = f"https://api.crossref.org/works/{doi}?mailto={email}"
    body, _ = get(url, email)
    return json.loads(body).get("message", {})


def unpaywall(doi, email):
    url = f"https://api.unpaywall.org/v2/{doi}?email={email}"
    body, _ = get(url, email)
    return json.loads(body)


def classify_updates(msg):
    """Return (status, notes) from Crossref update-to records."""
    notes = []
    status = "ok"
    for u in msg.get("update-to", []) or []:
        kind = (u.get("type") or "").lower().replace("-", "_")
        label = u.get("label") or u.get("type") or "update"
        notes.append(f"{label} ({u.get('DOI', 'no DOI')})")
        if kind in RETRACTION_KINDS:
            status = "retracted"
        elif kind in CONCERN_KINDS and status == "ok":
            status = "concern"
        elif status == "ok":
            status = "corrected"
    return status, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates")
    ap.add_argument("--email", default=os.environ.get("CONTACT_EMAIL"))
    ap.add_argument("--out", default="verified.json")
    ap.add_argument("--rejected", default="rejected.json")
    ap.add_argument("--no-unpaywall", action="store_true")
    ap.add_argument("--delay", type=float, default=0.2)
    args = ap.parse_args()

    if not args.email:
        sys.exit("error: --email or CONTACT_EMAIL required")

    data = json.load(open(args.candidates))
    cands = data.get("candidates", data if isinstance(data, list) else [])

    verified, rejected = [], []
    stats = {"retracted": 0, "concern": 0, "corrected": 0,
             "title_fixed": 0, "authors_fixed": 0, "year_fixed": 0, "oa": 0}

    for i, c in enumerate(cands, 1):
        doi = norm_doi(c.get("doi"))
        if not doi:
            rejected.append({**c, "rejection_reason":
                             "no DOI — verify manually via publisher/arXiv page"})
            continue
        try:
            msg = crossref_lookup(doi, args.email)
        except Exception as e:
            rejected.append({**c, "rejection_reason":
                             f"Crossref lookup failed: {type(e).__name__}: {e}. "
                             f"May be a DataCite DOI (dataset/preprint) — check there."})
            continue

        v = dict(c)
        v["doi"] = doi
        v["verified_against"] = "crossref"
        v["retrieved"] = time.strftime("%Y-%m-%d")
        v["retrieval_method"] = "api:crossref"

        cr_title = (msg.get("title") or [None])[0]
        if cr_title and norm_title(cr_title) != norm_title(c.get("title")):
            v["title_from_discovery"] = c.get("title")
            stats["title_fixed"] += 1
        v["title"] = cr_title or c.get("title")

        cr_authors = [f"{a.get('given','')} {a.get('family','')}".strip()
                      for a in msg.get("author", []) or []]
        if cr_authors and cr_authors != c.get("authors"):
            stats["authors_fixed"] += 1
        v["authors"] = cr_authors or c.get("authors", [])

        parts = ((msg.get("issued") or {}).get("date-parts") or [[None]])[0]
        cr_year = parts[0] if parts else None
        if cr_year and cr_year != c.get("year"):
            stats["year_fixed"] += 1
        v["year"] = cr_year or c.get("year")

        v["venue"] = (msg.get("container-title") or [None])[0] or c.get("venue")
        v["volume"] = msg.get("volume")
        v["pages"] = msg.get("page")
        v["publisher"] = msg.get("publisher")
        v["type"] = msg.get("type") or c.get("type")

        status, notes = classify_updates(msg)
        if c.get("is_retracted") and status == "ok":
            status = "flagged_openalex_only"
            notes.append("OpenAlex flags retracted but Crossref shows no retraction "
                         "— OpenAlex's boolean conflates corrections/EoC; verify manually")
        v["publication_status"] = status
        v["status_notes"] = notes
        if status in stats:
            stats[status] += 1

        v["access"] = "metadata-only"
        if not args.no_unpaywall:
            try:
                up = unpaywall(doi, args.email)
                v["is_oa"] = up.get("is_oa")
                v["oa_status"] = up.get("oa_status")
                best = up.get("best_oa_location") or {}
                v["oa_url"] = best.get("url_for_pdf") or best.get("url") or v.get("oa_url")
                if up.get("is_oa"):
                    stats["oa"] += 1
            except Exception as e:
                v["oa_lookup_error"] = str(e)

        verified.append(v)
        if i % 10 == 0:
            print(f"  {i}/{len(cands)}...", file=sys.stderr)
        time.sleep(args.delay)

    json.dump({"verified_count": len(verified), "stats": stats,
               "verified": verified}, open(args.out, "w"), indent=2)
    json.dump({"rejected_count": len(rejected), "rejected": rejected},
              open(args.rejected, "w"), indent=2)

    print(f"\nverified: {len(verified)}   rejected: {len(rejected)}")
    print(f"metadata corrections — title {stats['title_fixed']}, "
          f"authors {stats['authors_fixed']}, year {stats['year_fixed']}")
    if stats["retracted"]:
        print(f"  !! RETRACTED: {stats['retracted']} — do not cite as evidence")
    if stats["concern"]:
        print(f"  !  expression of concern: {stats['concern']} — cite with the concern stated")
    if stats["corrected"]:
        print(f"  ·  corrected: {stats['corrected']} — check the correction affects your claim")
    print(f"open access: {stats['oa']}")
    print("\nNOTE: 'access' is set to metadata-only. Update it to fulltext or "
          "abstract-only per source, by hand, based on what you actually read. "
          "No script can determine this and inflating it corrupts everything downstream.")


if __name__ == "__main__":
    main()
