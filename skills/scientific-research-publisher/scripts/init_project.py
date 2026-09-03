#!/usr/bin/env python3
"""Scaffold a research project: directory tree, empty ledger, PROJECT.md, template.

Usage:
    python3 init_project.py <project-dir> --title "..." [--mode preprint] [--question "..."]
"""
import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

DIRS = [
    "ledger", "search", "code", "data", "figures",
    "manuscript", "manuscript/sections", "review", "final",
]

LEDGER = {
    "sources.json": [],
    "claims.json": [],
    "hypotheses.json": [],
    "experiments.json": [],
    "equations.json": [],
    "artifacts.json": [],
}

PROJECT_MD = """# {title}

- **Created:** {today}
- **Mode:** {mode}
- **Status:** phase 1 (direct)

## Research question

{question}

## Scope

- In scope:
- Out of scope:

## Novelty claim

<!-- What this adds that does not already exist. Re-check after phase 2 search;
     this is the claim most likely to be falsified by the literature search. -->

## What evidence would settle this

<!-- Name a result that would refute the expected answer. If you cannot, the
     question is not yet answerable and phase 1 is not complete. -->

## Target

- Venue / style:
- Discipline:
- Audience:
- Page limit:

## Decisions log

| Date | Decision | Reason |
|------|----------|--------|
| {today} | Project initialised | |

## Planned but not performed

<!-- Experiments and analyses that were designed but NOT run. These never go in
     experiments.json, and never appear in the manuscript in the past tense. -->
"""

REFS_BIB = """% Generated from ledger/sources.json — do not hand-edit.
% Every entry must have a verified retrieval record in sources.json.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project_dir")
    ap.add_argument("--title", default="Untitled Research Project")
    ap.add_argument("--question", default="<state the research question>")
    ap.add_argument("--mode", default="preprint",
                    choices=["brief", "preprint", "lab"])
    args = ap.parse_args()

    root = Path(args.project_dir)
    if root.exists() and any(root.iterdir()):
        sys.exit(f"error: {root} exists and is not empty — refusing to overwrite")

    for d in DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)

    for name, empty in LEDGER.items():
        (root / "ledger" / name).write_text(json.dumps(empty, indent=2) + "\n")

    (root / "PROJECT.md").write_text(PROJECT_MD.format(
        title=args.title, today=date.today().isoformat(),
        mode=args.mode, question=args.question))

    (root / "manuscript" / "refs.bib").write_text(REFS_BIB)

    template = Path(__file__).resolve().parent.parent / "assets" / "paper_template.tex"
    if template.exists():
        shutil.copy(template, root / "manuscript" / "paper.tex")
        tpl_note = "manuscript/paper.tex (from template)"
    else:
        tpl_note = "manuscript/paper.tex NOT created — template missing"

    print(f"Initialised {root}")
    print(f"  mode: {args.mode}")
    print(f"  {tpl_note}")
    print(f"  ledger: {', '.join(sorted(LEDGER))}")
    print("\nNext: complete phase 1 in PROJECT.md before searching.")


if __name__ == "__main__":
    main()
