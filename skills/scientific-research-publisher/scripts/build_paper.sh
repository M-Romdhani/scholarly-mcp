#!/usr/bin/env bash
# Build the manuscript and surface the errors that matter.
#
# Usage: bash build_paper.sh <project-dir> [texfile]
# Default texfile: paper.tex
#
# Exits non-zero if the PDF was not produced, or if there are undefined
# references or citations — those render as [?] in an otherwise fine-looking
# PDF, which is worse than a hard failure.

set -uo pipefail

PROJECT="${1:?usage: build_paper.sh <project-dir> [texfile]}"
TEX="${2:-paper.tex}"
MANUSCRIPT="$PROJECT/manuscript"
BASE="${TEX%.tex}"

[ -d "$MANUSCRIPT" ] || { echo "error: $MANUSCRIPT not found"; exit 2; }
[ -f "$MANUSCRIPT/$TEX" ] || { echo "error: $MANUSCRIPT/$TEX not found"; exit 2; }

command -v latexmk >/dev/null || { echo "error: latexmk not installed"; exit 2; }

cd "$MANUSCRIPT" || exit 2

echo "== building $TEX =="
latexmk -pdf -bibtex -interaction=nonstopmode -file-line-error "$TEX" \
    > /tmp/latexmk_out.txt 2>&1
BUILD_RC=$?

LOG="$BASE.log"
FAIL=0

if [ ! -f "$BASE.pdf" ]; then
    echo "BUILD FAILED — no PDF produced (latexmk rc=$BUILD_RC)"
    FAIL=1
fi

if [ -f "$LOG" ]; then
    echo
    echo "-- fatal errors --"
    grep -E "^(.*:[0-9]+:|! )" "$LOG" | head -30 || true
    grep -qE "^(.*:[0-9]+:|! )" "$LOG" && FAIL=1

    echo
    echo "-- undefined references / citations --"
    UNDEF=$(grep -cE "(Reference|Citation) .* undefined" "$LOG" || true)
    if [ "${UNDEF:-0}" -gt 0 ]; then
        grep -E "(Reference|Citation) .* undefined" "$LOG" | sort -u | head -20
        echo "  ($UNDEF total) -- these render as [?] in the PDF"
        FAIL=1
    else
        echo "  none"
    fi

    echo
    echo "-- multiply-defined labels --"
    grep -E "multiply.defined" "$LOG" | sort -u | head -10 || echo "  none"
    grep -qE "multiply.defined" "$LOG" && FAIL=1

    echo
    echo "-- overfull boxes > 5pt --"
    # portable: no gawk-only match(s, re, arr). substr after "(" coerces to number.
    OVERFULL_AWK='/Overfull \\hbox \(/ {
        n = substr($0, index($0, "(") + 1) + 0
        if (n > 5) { c++; if (c <= 20) print "  " $0 }
    } END { printf "  (%d over threshold)\n", c + 0 }'
    awk "$OVERFULL_AWK" "$LOG"

    echo
    echo "-- missing characters --"
    grep -c "Missing character" "$LOG" | sed 's/^/  count: /'
fi

if [ -f "$BASE.blg" ]; then
    echo
    echo "-- bibtex problems --"
    # only real diagnostics — the .blg also lists bst function-call counts
    # ("empty$ -- 37"), which must not be mistaken for warnings.
    if grep -qE "^(Warning--|I was expecting|I couldn't|I found|Repeated entry)" "$BASE.blg"; then
        grep -E "^(Warning--|I was expecting|I couldn't|I found|Repeated entry)" "$BASE.blg" | head -15
    else
        echo "  none"
    fi
fi

echo
if [ -f "$BASE.pdf" ]; then
    PAGES=$(pdfinfo "$BASE.pdf" 2>/dev/null | awk '/^Pages:/{print $2}')
    SIZE=$(du -h "$BASE.pdf" | cut -f1)
    echo "PDF: $MANUSCRIPT/$BASE.pdf  (${PAGES:-?} pages, $SIZE)"
    mkdir -p "../final"
    cp "$BASE.pdf" "../final/paper.pdf"
    echo "copied to $PROJECT/final/paper.pdf"
fi

if [ "$FAIL" -ne 0 ]; then
    echo
    echo "BUILD NOT CLEAN — fix the above before phase 14. Full log: $MANUSCRIPT/$LOG"
    exit 1
fi

echo
echo "Build clean. Next: python3 scripts/pdf_qa.py $PROJECT — then LOOK at the pages."
