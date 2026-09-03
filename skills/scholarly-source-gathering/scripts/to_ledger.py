#!/usr/bin/env python3
"""Emit ledger/sources.json and manuscript/refs.bib from verified records.

Output matches the schema the scientific-research-publisher skill consumes, so
the two skills chain: gather here, write there.

Usage:
    python3 to_ledger.py verified.json [--out ledger/sources.json]
                          [--bib manuscript/refs.bib] [--exclude-retracted]
"""
import argparse
import json
import os
import re
import sys
import unicodedata

TYPE_MAP = {
    "journal-article": "article", "proceedings-article": "inproceedings",
    "book-chapter": "incollection", "book": "book", "posted-content": "misc",
    "dissertation": "phdthesis", "report": "techreport", "dataset": "misc",
}
BIB_TYPE = {
    "article": ["author", "title", "journal", "year"],
    "inproceedings": ["author", "title", "booktitle", "year"],
    "incollection": ["author", "title", "booktitle", "year"],
    "book": ["author", "title", "publisher", "year"],
    "phdthesis": ["author", "title", "school", "year"],
    "techreport": ["author", "title", "institution", "year"],
    "misc": ["author", "title", "year"],
}


def ascii_slug(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def make_key(r, used):
    surname = ""
    if r.get("authors"):
        surname = ascii_slug(str(r["authors"][0]).split()[-1])
    first_word = ""
    for w in re.findall(r"[A-Za-z]+", r.get("title") or ""):
        if w.lower() not in {"the", "a", "an", "on", "of", "in", "for", "and"}:
            first_word = ascii_slug(w)
            break
    base = f"{surname or 'anon'}{r.get('year') or 'nd'}{first_word}" or "ref"
    key, n = base, 1
    while key in used:
        key = f"{base}{chr(ord('a') + n - 1)}"
        n += 1
    used.add(key)
    return key


def esc(s):
    if s is None:
        return None
    return str(s).replace("&", r"\&").replace("%", r"\%").replace("_", r"\_") \
                 .replace("#", r"\#").replace("$", r"\$")


def bib_entry(r):
    btype = TYPE_MAP.get(r.get("type"), "article")
    if btype == "article" and not r.get("venue"):
        btype = "misc"
    fields, missing = [], []
    authors = " and ".join(esc(a) for a in r.get("authors", []) if a)
    add = lambda k, v: fields.append(f"  {k:<9}= {{{v}}}") if v else None

    add("author", authors)
    add("title", esc(r.get("title")))
    venue = esc(r.get("venue"))
    if btype == "article":
        add("journal", venue)
    elif btype in ("inproceedings", "incollection"):
        add("booktitle", venue)
    elif btype == "techreport":
        add("institution", esc(r.get("publisher")) or venue)
    elif btype == "phdthesis":
        add("school", esc(r.get("publisher")) or venue)
    elif btype == "book":
        add("publisher", esc(r.get("publisher")))
    else:
        add("howpublished", venue)
    add("year", r.get("year"))
    add("volume", r.get("volume"))
    add("pages", esc(r.get("pages")))
    add("doi", r.get("doi"))
    if not r.get("doi"):
        add("url", r.get("oa_url"))
    if r.get("publication_status") == "retracted":
        add("note", "RETRACTED PUBLICATION")
    elif r.get("publication_status") == "concern":
        add("note", "Subject to an expression of concern")

    present = {f.split("=")[0].strip() for f in fields}
    for req in BIB_TYPE.get(btype, []):
        if req not in present:
            missing.append(req)
    return f"@{btype}{{{r['bibtex_key']},\n" + ",\n".join(fields) + "\n}\n", missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("verified")
    ap.add_argument("--out", default="ledger/sources.json")
    ap.add_argument("--bib", default="manuscript/refs.bib")
    ap.add_argument("--exclude-retracted", action="store_true")
    args = ap.parse_args()

    data = json.load(open(args.verified))
    records = data.get("verified", data if isinstance(data, list) else [])

    used, sources, bib_parts, warnings = set(), [], [], []
    skipped = 0

    for i, r in enumerate(records, 1):
        status = r.get("publication_status", "ok")
        if args.exclude_retracted and status == "retracted":
            skipped += 1
            continue
        r["bibtex_key"] = make_key(r, used)
        entry, missing = bib_entry(r)
        bib_parts.append(entry)
        if missing:
            warnings.append(f"{r['bibtex_key']}: missing {', '.join(missing)}")
        if not r.get("retrieved"):
            warnings.append(f"{r['bibtex_key']}: no retrieval date — this record never "
                            f"went through verification and will fail the citation audit")
        if status == "retracted":
            warnings.append(f"{r['bibtex_key']}: RETRACTED — cite only when "
                            f"discussing the retraction, and say so in the text")

        sources.append({
            "id": f"S{i:02d}",
            "type": r.get("type", "journal-article"),
            "authors": r.get("authors", []),
            "year": r.get("year"),
            "title": r.get("title"),
            "venue": r.get("venue"),
            "volume": r.get("volume"),
            "pages": r.get("pages"),
            "doi": r.get("doi"),
            "url": r.get("oa_url") or (f"https://doi.org/{r['doi']}" if r.get("doi") else None),
            "retrieved": r.get("retrieved"),
            "retrieval_method": r.get("retrieval_method", "api"),
            "access": r.get("access", "metadata-only"),
            "evidence_class": r.get("evidence_class"),
            "quality_notes": None,
            "scope_limits": None,
            "publication_status": status,
            "status_notes": r.get("status_notes", []),
            "found_by": r.get("found_by", []),
            "corroboration": r.get("corroboration"),
            "bibtex_key": r["bibtex_key"],
        })

    for path in (args.out, args.bib):
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)

    json.dump(sources, open(args.out, "w"), indent=2)
    with open(args.bib, "w") as f:
        f.write("% Generated from the verified source set — do not hand-edit.\n"
                "% Regenerate with scripts/to_ledger.py after any change.\n\n")
        f.write("\n".join(bib_parts))

    print(f"{len(sources)} sources → {args.out}")
    print(f"{len(bib_parts)} entries → {args.bib}")
    if skipped:
        print(f"{skipped} retracted record(s) excluded")
    if warnings:
        print(f"\nWARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  ! {w}")

    unset = sum(1 for s in sources if s["access"] == "metadata-only")
    if unset:
        print(f"\n{unset} record(s) still have access='metadata-only'. Set each to "
              f"fulltext / abstract-only / preprint-version / secondhand by hand, "
              f"reflecting what you actually read. The downstream citation audit "
              f"depends on this being honest.")
    print("\nAlso fill in evidence_class, quality_notes and scope_limits during triage "
          "— see the publisher skill's references/evidence_ledger.md.")


if __name__ == "__main__":
    main()
