#!/usr/bin/env python3
"""Structural citation audit: bib fields, DOI syntax, duplicates, orphans,
and ledger cross-check.

This checks STRUCTURE, not EXISTENCE. Network access is usually restricted in
sandboxes, so verifying that a paper is real is done at phase 3 with retrieval
tools, and recorded in ledger/sources.json. This script flags any bib entry
without such a record.

Usage:
    python3 check_references.py <project-dir>

Exit code 0 = clean, 1 = errors found.
"""
import json
import re
import sys
from pathlib import Path

REQUIRED = {
    "article": ["author", "title", "journal", "year"],
    "inproceedings": ["author", "title", "booktitle", "year"],
    "book": ["author", "title", "publisher", "year"],
    "incollection": ["author", "title", "booktitle", "year"],
    "phdthesis": ["author", "title", "school", "year"],
    "techreport": ["author", "title", "institution", "year"],
    "misc": ["author", "title", "year"],
}
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([^,]+),", re.M)


def parse_bib(text):
    """Minimal BibTeX parser: entry type, key, and top-level fields."""
    entries = []
    for m in ENTRY_RE.finditer(text):
        etype, key = m.group(1).lower(), m.group(2).strip()
        start, depth, i = m.end(), 1, m.end()
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        body = text[start:i - 1]
        fields, depth, buf = {}, 0, ""
        parts = []
        for ch in body:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            if ch == "," and depth == 0:
                parts.append(buf)
                buf = ""
            else:
                buf += ch
        parts.append(buf)
        for p in parts:
            if "=" in p:
                k, _, v = p.partition("=")
                fields[k.strip().lower()] = v.strip().strip("{}\" \n\t")
        entries.append({"type": etype, "key": key, "fields": fields})
    return entries


def find_citations(tex_files):
    keys = set()
    pat = re.compile(r"\\cite[a-zA-Z]*\s*(?:\[[^\]]*\])*\s*\{([^}]*)\}")
    for f in tex_files:
        for m in pat.finditer(f.read_text(errors="ignore")):
            for k in m.group(1).split(","):
                if k.strip():
                    keys.add(k.strip())
    return keys


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = Path(sys.argv[1])
    bib_path = root / "manuscript" / "refs.bib"
    errors, warnings = [], []

    if not bib_path.exists():
        sys.exit(f"error: {bib_path} not found")

    entries = parse_bib(bib_path.read_text(errors="ignore"))
    tex_files = sorted((root / "manuscript").rglob("*.tex"))
    cited = find_citations(tex_files)

    # --- duplicate keys
    seen = {}
    for e in entries:
        if e["key"] in seen:
            errors.append(f"duplicate bib key: {e['key']}")
        seen[e["key"]] = e

    # --- likely duplicate content (same first author + year + title start)
    sig = {}
    for e in entries:
        f = e["fields"]
        s = (f.get("author", "").split(",")[0].lower().strip(),
             f.get("year", ""),
             f.get("title", "").lower()[:40])
        if all(s) and s in sig:
            warnings.append(f"possible duplicate entry: {e['key']} ~ {sig[s]}")
        sig[s] = e["key"]

    # --- required fields, DOI syntax
    for e in entries:
        req = REQUIRED.get(e["type"], ["author", "title", "year"])
        for field in req:
            if not e["fields"].get(field):
                errors.append(f"{e['key']}: missing required field '{field}'")
        doi = e["fields"].get("doi", "")
        if doi:
            clean = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
            if not DOI_RE.match(clean):
                errors.append(f"{e['key']}: malformed DOI '{doi}'")
        elif not e["fields"].get("url"):
            errors.append(f"{e['key']}: no DOI and no URL — cannot be verified")

    # --- citation / bibliography symmetry
    bib_keys = {e["key"] for e in entries}
    for k in sorted(cited - bib_keys):
        errors.append(f"cited but not in refs.bib: {k}")
    for k in sorted(bib_keys - cited):
        warnings.append(f"in refs.bib but never cited: {k}")

    # --- ledger cross-check
    src_path = root / "ledger" / "sources.json"
    if src_path.exists():
        try:
            sources = json.loads(src_path.read_text() or "[]")
        except json.JSONDecodeError as exc:
            errors.append(f"sources.json is not valid JSON: {exc}")
            sources = []
        by_key = {s.get("bibtex_key"): s for s in sources if s.get("bibtex_key")}
        for e in entries:
            s = by_key.get(e["key"])
            if not s:
                errors.append(
                    f"{e['key']}: no entry in sources.json — retrieval unverified")
                continue
            if not s.get("retrieved"):
                errors.append(f"{e['key']}: sources.json entry has no retrieval date")
            if not s.get("access"):
                warnings.append(f"{e['key']}: access level not recorded")
            elif s["access"] == "abstract-only":
                warnings.append(
                    f"{e['key']}: abstract-only — check it is not carrying a central claim")
    else:
        warnings.append("ledger/sources.json not found — ledger cross-check skipped")

    # --- report
    print(f"refs.bib entries: {len(entries)}   cited keys: {len(cited)}   "
          f"tex files scanned: {len(tex_files)}")
    if errors:
        print(f"\nERRORS ({len(errors)}):")
        for e in errors:
            print(f"  ✗ {e}")
    if warnings:
        print(f"\nWARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  ! {w}")
    if not errors and not warnings:
        print("\nClean.")

    print("\nStructural check only. Semantic verification — does each cited work "
          "actually support the sentence it is attached to — is manual. See "
          "references/review_and_qa.md, phase 10.")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
