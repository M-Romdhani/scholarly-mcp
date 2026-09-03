# Typesetting and PDF Production

Read during phase 11.

Typesetting is a separate subsystem, not something to improvise at the end of writing. The manuscript is LaTeX source compiled by a real engine — never a PDF assembled from prose by a script, and never equations rendered as images.

---

## Environment check (run first)

Toolchains vary. Establish what you have before choosing an approach:

```bash
which pdflatex xelatex lualatex latexmk bibtex biber pandoc
kpsewhich revtex4-2.cls elsarticle.cls IEEEtran.cls biblatex.sty natbib.sty
```

A typical sandboxed container has: **pdflatex, xelatex, lualatex, latexmk, bibtex, pandoc**, and the standard packages (`amsmath`, `booktabs`, `siunitx`, `hyperref`, `cleveref`, `microtype`, `geometry`, `caption`, `subcaption`, `graphicx`, `natbib`, `titlesec`, `placeins`, `threeparttable`, `mathptmx`, `charter`, `tikz`, `pgfplots`).

Commonly **absent**: `biblatex`/`biber`, and journal classes (`revtex4-2`, `elsarticle`, `IEEEtran`). Package installation usually fails because the network is restricted.

Consequences, and the reason the bundled template is built the way it is:

- **Use natbib + bibtex**, not biblatex + biber. `plainnat`, `unsrtnat`, `abbrvnat`, `apalike`, `ieeetr` are available.
- **Do not target a journal class you cannot compile.** Produce the manuscript in the generic template and tell the user which class to swap in locally — for most journals it's a one-line `\documentclass` change plus their metadata macros. Silently producing something that only compiles on your machine is worse than saying so.
- If a package is missing and there is no substitute, say what was unavailable rather than working around it invisibly.

---

## Build

Use `scripts/build_paper.sh`, which runs latexmk with bibtex and extracts real errors from the log. Manual equivalent:

```bash
cd manuscript
latexmk -pdf -interaction=nonstopmode -halt-on-error paper.tex
```

latexmk handles the pass count for cross-references and the bibtex interleaving. Running pdflatex once and stopping is why `??` appears in output PDFs.

**Never accept a build with `Undefined reference`, `Citation undefined`, or `Missing character` warnings.** These are silent corruption: the PDF renders and looks fine, with `[?]` where a citation should be.

---

## Template

`assets/paper_template.tex` — copy to `manuscript/paper.tex` and edit. It is self-contained: `article` class, one column, no external class files. Its defaults:

| Element | Setting | Why |
|---|---|---|
| Page | A4 (or Letter), 25mm margins | Journal-neutral; `geometry` makes it a one-line change |
| Body | 11pt, `mathptmx` (Times) | Times is the default in most of physics/chem/bio; `charter` is a warmer alternative |
| Leading | ~1.2 (default) or `\onehalfspacing` for review copies | Reviewers ask for the latter |
| Paragraphs | First-line indent, no extra space | Standard for papers; `parskip` style is for reports, not manuscripts |
| Justification | Full, with `microtype` | `microtype` fixes most spacing complaints without manual intervention |
| Widows/orphans | `\widowpenalty=10000`, `\clubpenalty=10000` | Prevents the single-line-stranded-at-a-page-break look |
| Sections | `titlesec`, 14pt/12pt/11pt bold-to-italic hierarchy | Clear rank without shouting |
| Floats | `[!htbp]`, `placeins` for section barriers | Keeps figures near their discussion |
| Citations | `natbib` numeric + `plainnat` | Switch to author-year with one option change |
| Cross-refs | `cleveref` | `\cref{fig:x}` produces "Fig. 3" automatically and consistently |

Do not add packages that duplicate these. `hyperref` loads late, `cleveref` after it — reordering breaks both.

---

## Equations

Real math, typeset by the engine. No images of equations, ever.

```latex
\begin{equation}
  S = k_B \ln \Omega
  \label{eq:boltzmann}
\end{equation}
```

- Number equations that are referenced; use `equation*` or `\[...\]` for those that aren't. Numbering everything creates clutter and dead numbers.
- Multi-line: `align` for aligned relations, `split` inside a single numbered equation, `cases` for piecewise. Never manual line breaks with `\\` in `equation`.
- Reference with `\cref{eq:boltzmann}` → "Eq. (1)". Consistent by construction.
- Punctuate display equations as part of the sentence — they are grammatical objects.
- Units with `siunitx`: `\SI{3.2}{\micro\meter}`, `\si{\per\second}`. It handles spacing and the minus sign correctly, which manual markup does not.
- Notation must match `equations.json`. Check upright vs italic: variables italic, operators and units upright (`\mathrm{d}x`, `\sin`, `\mathrm{Re}`).

---

## Figures

```latex
\begin{figure}[!htbp]
  \centering
  \includegraphics[width=0.8\linewidth]{figures/fig3_exponent.pdf}
  \caption{Fitted exponent versus binning resolution. Error bars are $1\sigma$ from
           bootstrap resampling ($n=1000$). Data from \cref{tab:runs}.}
  \label{fig:exponent}
\end{figure}
```

- **Vector formats** (PDF, EPS) for plots; raster (PNG, ≥300 dpi) only for images and photographs. A PNG line plot in a PDF looks amateur at any zoom level.
- Size in `\linewidth` fractions, never absolute cm. Scaling text inside a figure to fit is what produces the mismatched font sizes that mark a document as machine-made — set the font size when generating the figure instead (matplotlib: `rcParams['font.size']`, target 8–10pt at final width).
- Captions go **below** figures, above tables. Captions are self-contained: a reader who reads only figures should understand each one.
- Every figure referenced in text via `\cref`. Every figure traceable to `artifacts.json`.
- Colour must not be the only channel carrying information — use markers or linestyle too. Roughly 1 in 12 male readers cannot distinguish red from green.

---

## Tables

```latex
\begin{table}[!htbp]
  \centering
  \caption{Fit results across binning choices.}
  \label{tab:runs}
  \begin{tabular}{lS[table-format=1.2]S[table-format=1.2]}
    \toprule
    Bins & {Exponent} & {Uncertainty} \\
    \midrule
    20  & 1.83 & 0.07 \\
    50  & 1.84 & 0.06 \\
    100 & 1.85 & 0.08 \\
    \bottomrule
  \end{tabular}
\end{table}
```

- `booktabs` only: `\toprule`, `\midrule`, `\bottomrule`. **No vertical rules and no `\hline`.** This is the single clearest visual tell separating typeset tables from generated ones.
- Align numbers on the decimal with `siunitx`'s `S` column.
- Consistent significant figures down each column, matching actual precision.
- Units in the column header, not repeated in every cell.
- Footnotes via `threeparttable`, not `\footnote` (which escapes the float).
- A table wider than the text block should be `sidewaystable` or moved to an appendix, not shrunk to 6pt.

---

## References

- One `refs.bib`, generated from `sources.json` so the bibliography and the ledger cannot drift apart.
- Every entry needs author, year, title, venue, and DOI or a stable URL.
- Consistent key convention: `firstauthorYEARfirstword`.
- Cite with `\citep{}` (parenthetical) / `\citet{}` (textual) — mixing raw `\cite` with natbib produces inconsistent brackets.
- Run `scripts/check_references.py` for: missing required fields, malformed DOIs, duplicate entries, uncited entries sitting in the bibliography, and cite keys with no bib entry.
- Structural validity is not existence. Existence was verified at phase 3, by retrieval. If any entry lacks a verified retrieval record, it does not ship.

---

## PDF quality control

Run `scripts/pdf_qa.py`, then **look at the rendered pages**. The script rasterizes them to PNG in `final/qa_pages/` for exactly this purpose. Log parsing catches errors; only looking catches ugliness.

Automated checks:
- Undefined references / citations → build failure, not a warning
- Overfull hboxes > 5pt → text in the margin
- Multiply-defined labels → wrong cross-references throughout
- Missing characters → silently dropped glyphs
- Page count vs target

Visual checks, on the actual images:
- Headings stranded at the bottom of a page
- Single lines orphaned at a page top or bottom
- Figures floating pages away from their discussion
- Tables split awkwardly across pages
- Rivers of whitespace from bad justification
- Inconsistent caption or heading spacing
- A last page with two lines on it

Most of these are fixed by `\FloatBarrier` at section ends, resizing a figure slightly, or rewording a paragraph to change its line count. Resist `\clearpage` as a fix — it usually trades one problem for a half-empty page.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `[?]` or `??` in output | Insufficient passes | Use latexmk; it iterates |
| `Citation undefined` | bibtex didn't run, or key mismatch | Check `.blg` log; verify key exists in `refs.bib` |
| Figure not found | Path relative to `.tex`, extension case | Use `figures/name.pdf` from `manuscript/`; check case |
| Float drifts to the end | Too many floats queued, or oversized | `\FloatBarrier`, or reduce size below ~0.9\textheight |
| `Package inputenc Error` | Non-ASCII in a pdflatex document | Escape it, or compile with xelatex |
| Bad line breaks in URLs | No breakpoints | `\usepackage{url}` and `\url{}`; already in the template |
| Build hangs | Interactive error prompt | Always pass `-interaction=nonstopmode` |
| Missing package | Not installed, network blocked | Substitute, or tell the user what was unavailable |
