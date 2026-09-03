#!/usr/bin/env python3
"""Post-build PDF quality control.

Parses the LaTeX log for silent-corruption warnings, cross-checks labels and
citations, reports document statistics, and rasterizes every page to PNG so the
pages can actually be LOOKED AT. Log parsing catches errors; only looking
catches ugliness.

Usage:
    python3 pdf_qa.py <project-dir> [--dpi 110] [--max-pages 20]
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def analyse_log(log_path, results):
    if not log_path.exists():
        results["errors"].append(f"log not found: {log_path}")
        return
    log = log_path.read_text(errors="ignore")

    undef = sorted(set(re.findall(r"(?:Reference|Citation) `([^']+)' (?:on page \d+ )?undefined", log)))
    for u in undef:
        results["errors"].append(f"undefined reference/citation: {u}")

    for m in sorted(set(re.findall(r"Label `([^']+)' multiply defined", log))):
        results["errors"].append(f"multiply-defined label: {m}")

    over = [(float(pt), page) for pt, page in
            re.findall(r"Overfull \\hbox \(([\d.]+)pt too wide\).*?(?:at lines? (\d+))?", log)]
    bad = [o for o in over if o[0] > 5]
    if bad:
        worst = max(b[0] for b in bad)
        results["errors"].append(
            f"{len(bad)} overfull hbox(es) > 5pt (worst {worst:.1f}pt) — text in the margin")
    minor = len(over) - len(bad)
    if minor:
        results["info"].append(f"{minor} overfull hbox(es) under 5pt (acceptable)")

    missing = len(re.findall(r"Missing character", log))
    if missing:
        results["errors"].append(f"{missing} missing character(s) — glyphs silently dropped")

    for w in sorted(set(re.findall(r"LaTeX Warning: ([^\n]+)", log))):
        if not any(s in w for s in ("undefined", "multiply", "rerun", "Rerun", "Font shape")):
            results["warnings"].append(f"latex: {w.strip()}")


def check_crossrefs(manuscript, results):
    """Labels defined but never referenced, and vice versa."""
    tex = "\n".join(p.read_text(errors="ignore") for p in manuscript.rglob("*.tex"))
    labels = set(re.findall(r"\\label\{([^}]+)\}", tex))
    refs = set()
    for pat in (r"\\c?ref\{([^}]+)\}", r"\\Cref\{([^}]+)\}", r"\\eqref\{([^}]+)\}",
                r"\\autoref\{([^}]+)\}", r"\\pageref\{([^}]+)\}"):
        for m in re.findall(pat, tex):
            refs.update(k.strip() for k in m.split(","))

    for lab in sorted(labels - refs):
        if lab.startswith(("fig:", "tab:")):
            results["errors"].append(
                f"float never referenced in text: {lab} — every figure/table must be discussed")
        elif lab.startswith("eq:"):
            results["warnings"].append(f"numbered equation never referenced: {lab}")
        else:
            results["info"].append(f"unreferenced label: {lab}")
    for r in sorted(refs - labels):
        results["errors"].append(f"reference to undefined label: {r}")


def rasterize(pdf, outdir, dpi, max_pages, results):
    if not shutil.which("pdftoppm"):
        results["warnings"].append("pdftoppm not available — cannot rasterize for visual QA")
        return []
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)
    r = run(["pdftoppm", "-png", "-r", str(dpi), "-l", str(max_pages),
             str(pdf), str(outdir / "page")])
    if r is None or r.returncode != 0:
        results["warnings"].append("rasterization failed")
        return []
    return sorted(outdir.glob("page*.png"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_dir")
    ap.add_argument("--dpi", type=int, default=110)
    ap.add_argument("--max-pages", type=int, default=20)
    ap.add_argument("--tex", default="paper")
    args = ap.parse_args()

    root = Path(args.project_dir)
    manuscript = root / "manuscript"
    pdf = manuscript / f"{args.tex}.pdf"
    if not pdf.exists():
        pdf = root / "final" / "paper.pdf"
    if not pdf.exists():
        sys.exit("error: no PDF found — run build_paper.sh first")

    results = {"errors": [], "warnings": [], "info": []}

    analyse_log(manuscript / f"{args.tex}.log", results)
    check_crossrefs(manuscript, results)

    info = run(["pdfinfo", str(pdf)])
    pages = "?"
    if info and info.returncode == 0:
        for line in info.stdout.splitlines():
            if line.startswith("Pages:"):
                pages = line.split()[1]
            if line.startswith("Page size:"):
                results["info"].append(line.strip())

    txt = run(["pdftotext", str(pdf), "-"])
    if txt and txt.returncode == 0:
        words = len(txt.stdout.split())
        results["info"].append(f"word count: ~{words}")
        if "??" in txt.stdout:
            results["errors"].append("literal '??' in rendered text — unresolved cross-reference")
        if "[?]" in txt.stdout:
            results["errors"].append("literal '[?]' in rendered text — unresolved citation")

    imgs = rasterize(pdf, root / "final" / "qa_pages", args.dpi, args.max_pages, results)

    print(f"PDF: {pdf}  ({pages} pages)")
    for key, mark in (("errors", "✗"), ("warnings", "!"), ("info", "·")):
        if results[key]:
            print(f"\n{key.upper()} ({len(results[key])}):")
            for item in results[key]:
                print(f"  {mark} {item}")

    if imgs:
        print(f"\nRendered {len(imgs)} page image(s) → {root / 'final' / 'qa_pages'}")
        print("VIEW THESE. Automated checks cannot see:")
        for c in ("headings stranded at a page bottom",
                  "single lines orphaned at a page top or bottom",
                  "figures floating pages from their discussion",
                  "tables split awkwardly across pages",
                  "rivers of whitespace from bad justification",
                  "inconsistent caption or heading spacing",
                  "a final page holding two lines"):
            print(f"  - {c}")

    print()
    if results["errors"]:
        print(f"QA FAILED — {len(results['errors'])} error(s) block release.")
        sys.exit(1)
    print("Automated QA passed. Visual inspection still required before phase 14.")


if __name__ == "__main__":
    main()
