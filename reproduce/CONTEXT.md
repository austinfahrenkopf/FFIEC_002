# FFIEC 002 Dashboard — Design Context for Future Editors

This document distills the standing design decisions, methodology constraints, and
non-obvious implementation choices for the FFIEC 002 dashboard. Read this before making
substantive changes to `make_site_002.py`, `build_hierarchy_002.py`, or the curated
input files (`ffiec002_hierarchy_overrides.json`).

---

## What this project is

A browser dashboard over the **FFIEC 002** — the quarterly report filed by U.S. branches
and agencies of foreign banks. Roughly 200 active filers at any given time; data goes
back to the 1990s.

The FFIEC 002 is one of three sibling dashboards (Y-9C, FFIEC 002, Call Reports). The three
`make_site_*.py` scripts are **clones** of one explorer engine — no shared module. Every
engine or UI change must be ported to all three. Never copy a MDRM code from one form to
another without verifying it exists in that form's data panel.

---

## The rendered-vs-PDF standard (the quality bar)

The hierarchy in `ffiec002_hierarchy.json` must match the blank FFIEC 002 form PDF
(`FFIEC002_202606_f.pdf`). The gate passed at final validation (2026-06-22, commit
`c13792a`) across all 18 schedules.

**Known deferred cosmetic (not a blocker):** 98 ALL-CAPS captions (e.g., "ASSETS",
"LIABILITIES AND CAPITAL") appear uppercase as extracted from the raw data. These are
cosmetically different from the PDF's title-case rendering but structurally correct.
Fix them in `ffiec002_hierarchy_overrides.json` under `caption_fixes` when making a
caption-normalization pass.

---

## Hierarchy construction

`build_hierarchy_002.py` builds `ffiec002_hierarchy.json` in two layers:

### Layer 1 — PDF parsing (pypdf)
Reads `FFIEC002_202606_f.pdf` to extract schedule/line-item structure. The FFIEC 002
form is simpler than the Y-9C (no complex matrix schedules), so PDF parsing covers
most of the hierarchy reliably.

### Layer 2 — JSON overrides (ffiec002_hierarchy_overrides.json)
Post-parse corrections:
- `force_rows`: inject line items the parser misses
- `caption_fixes`: correct garbled or uppercase captions
- `drop_codes`: remove obsolete codes
- `renames`: correct item numbering

---

## No DYN subtotals (002 is flat, unlike Y-9C)

The Y-9C dashboard has dynamic subtotals (DYN) for clicking schedule headers. The FFIEC
002 does NOT — its schedule hierarchy is flat enough that subtotals aren't useful. Do
not port DYN to 002 without careful consideration.

---

## No PCTC codes in FFIEC 002

Foreign-branch reporting (FFIEC 002) has no capital ratio disclosures — there are no
non-additive PCTC codes. The `isRawPct()` guard in the JS engine returns false for
all 002 codes; this is correct. Do not copy PCTC logic from Y-9C into 002.

---

## Aggregated ratio rule (same as Y-9C)

For any DERIV-type ratio in the 002, use Σnumerator / Σdenominator — never
average-of-ratios. This is enforced in `seriesFor()` in `make_site_002.py`.

---

## Single parquet (no entity sharding)

Unlike Y-9C (which uses era-sharded active parquets for fast loading), FFIEC 002 uses
a **single `ffiec002.parquet`** (~7.8 MB). The filer universe is small enough that one
file is efficient. DuckDB-WASM loads it in full on startup.

If the file grows large in the future (unlikely unless the history window is extended),
consider the same era-sharding approach used by Y-9C.

---

## Completeness gate

`_completeness_gate.py` runs a bidirectional check:
1. Every code in `expected_items.json` must appear in the hierarchy.
2. Every code in the hierarchy must be in `expected_items.json` or in
   `ffiec002_completeness_exclusions.json`.

`ffiec002_completeness_exclusions.json` lists codes legitimately absent from the
filer data (retired codes, memo items not universally collected). When the gate
fails on a new "missing" code, check the PDF and the panel before adding an exclusion.

---

## Data source: Chicago Fed (not Akamai-guarded)

Unlike the Y-9C (Akamai-guarded NIC Financial Data Download), the FFIEC 002 data
comes from the Chicago Fed's public file server. This is usually a direct download,
but `download_ffiec002_playwright.py` uses Playwright for reliability in case the
page navigation changes.

Do NOT try to reconstruct the panel from archive.org mirrors or third-party caches —
use only the official Chicago Fed source.

---

## Three-dashboard clone constraint

`make_site_002.py` is a clone of the shared explorer engine. When changing engine
logic (JS functions, Python build logic):
1. Make and test the change in one file.
2. Port to all three `make_site_*.py` files.
3. Adjust for form-specific differences (MDRM prefixes, PCTC sets, schedule names).
4. Run `FINALIZE.ps1` to validate all three.

The most common porting mistake is assuming a MDRM code or schedule structure from
Y-9C exists in 002. Always check `ffiec002_mdrm_dictionary.csv` or the panel.

---

## Validation checkpoints

| Check | Tool | Pass condition |
|---|---|---|
| Golden cell | `validate_build_002.py` | Known NY Fed branch value at a fixed quarter |
| DERIV codes resolve | `validate_build_002.py` | All DERIV num/den codes in panel |
| Bidirectional completeness | `_completeness_gate.py` | 0 missing, 0 unexpected |
| Rendered-vs-PDF | Manual + overrides audit | 18/18 schedules match form |
| Engine smoke test | `_qa_final.py` | 23/23 QA checks pass |
| Full suite | `FINALIZE.ps1` | "FINALIZE COMPLETE - ALL PASSED" |

---

## Key files and what to edit

| Want to... | Edit this |
|---|---|
| Fix a caption, force a row, drop an old code | `ffiec002_hierarchy_overrides.json` |
| Add a derived ratio | `DERIVED` dict in `make_site_002.py` |
| Change dashboard UI or query logic | `make_site_002.py` (then port to Y-9C/Call) |
| Exclude a known-absent code from gate | `ffiec002_completeness_exclusions.json` |
| Add a new expected line item | `expected_items.json` |
| Update for a new form revision | New PDF → re-run `build_hierarchy_002.py` → audit diff |
