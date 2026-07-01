# FFIEC 002 Reproduce Kit — Verification Record

**Current HEAD:** `bcb6360157674c24f915825c1d8a99186c3d0aae` (2026-07-01 — sigma calc fix)
**Pages build:** ✅ SUCCESS 2026-07-01T19:32:27Z
**Live URL:** https://austinfahrenkopf.github.io/FFIEC_002/app/index.html

> **Reproduce verification was run against `08d7f55`** (§NORMDEN-LEAGUE-002). Commits since then
> (`a68fa1a` extra-chart controls, `bbbaac1` app/ layout, `bcb6360` sigma calc fix) are JS-only
> additions. The rebuild-pass and golden cell below remain valid; the features table has been
> extended to include new features at HEAD. Re-run `_qa_final.py` from workspace root to confirm
> current check count (was ALL PASSED at `08d7f55`; +5 checks added at `bbbaac1`).

**Date verified (clean-room rebuild):** 2026-07-01 (against commit `08d7f55`)
**Previous verifications:** 2026-06-25 (Save→localStorage fix), 2026-06-24 (initial)
**Environment:** Python 3.12.1 · pandas 3.0.3 · pyarrow 24.0.0 · duckdb 1.5.4 · Windows 11

---

## Test method

Reproduce/ kit used as a self-contained build environment. `site_002/` created fresh with the
committed site parquet (`app/ffiec002.parquet`, 13.9 MB) as the starting point for `--html-only`.
All build steps run from `reproduce/` directory; no access to the live workspace during any step.

---

## What was rebuilt from scratch

| Step | Script | Produces | Time |
|---|---|---|---|
| 1 | `build_hierarchy_002.py` | `ffiec002_hierarchy.json` (from PDF + overrides) | 1 s |
| 2 | `make_site_002.py --html-only` | `site_002/index.html` (from site parquet + hierarchy) | 4 s |
| 3 | `validate_build_002.py` | — (exit 0) | 2 s |

`ffiec002_panel_long.parquet` (27.7 MB, shipped in this kit) was used as the data source for step 2.

**Note:** `--html-only` regenerates the HTML from the existing site parquet without re-reading the
source panel. The rebuilt HTML is byte-for-byte identical to the committed `app/index.html` except
for the embedded build timestamp (expected — timestamp is inserted at build time). Golden cell and
all feature strings are identical.

---

## Result: ALL CHECKS PASSED

```
site parts: 1   hierarchy schedules: 16   site codes: 679
NOTE  [COMPLETE2] FFIEC 002: all must-add codes from manifest are now present in the hierarchy
NOTE  [MISSING] OK — every active-era code is in the hierarchy or documented (540 active codes checked)
NOTE  [SPURIOUS] OK — every hierarchy leaf code is reported in the panel or documented in spurious_allowed
NOTE  [NESTING] OK — node depths match item numbers
NOTE  [DUP_ITEM] OK — no duplicate item numbers
NOTE  [SEQUENCE] OK — no undocumented item-number gaps
NOTE  [ERA_SEAM] OK — headline NPL/charge-off/past-due/assets series are continuous

ALL CHECKS PASSED [OK]
```

---

## Golden cell confirmed

**MUFG Bank NY Branch (RSSD 444819) RCFD2170 @ 2026-03-31 = 245,557,856** ($ thousands) ✓

---

## Features confirmed at HEAD (commit `bcb6360`, updated 2026-07-01)

| Feature | Commit | Status |
|---|---|---|
| `NORM_DEN_LABELS` normden dropdown | `08d7f55` | ✓ 4 occurrences; COMB2170/2122/2205; NO COMB3210 |
| `buildLGMEAS` full league (190 options) | `08d7f55` | ✓ Playwright-verified vs Deutsche Bank RSSD 112819 |
| `_ND2205` pre-computed deposits WASM workaround | `08d7f55` | ✓ CRITICAL/PERMANENT — never revert to live DuckDB query |
| `.filter(r=>r[1]!==null)` null-filter in `draw()` | `08d7f55` | ✓ Correctness fix; prevents TypeError on quarter-coverage gaps |
| app/ layout + root redirect | `bbbaac1` | ✓ `app/index.html`; root `index.html` is 100-byte redirect |
| Extra-chart controls (per-chart legend, Labels, snap-beside) | `a68fa1a` | ✓ `ec-legend-<id>` div; `renderEcLegend(chart)`; `#charts-flex`; Playwright 25/25 PASS |
| **Sigma Calc fix** | `bcb6360` | ✓ DOM-safe code-search (`createElement`/`textContent`; `rawCode=r.m` closure); Save→Blob `ffiec002_formulas.json`; Load→file input; localStorage `ffiec002_formulas`. Playwright 25/25 PASS (RSSD 112819). |

Playwright runtime verification (12/12 PASS, Deutsche Bank AG NY Branch, RSSD 112819):
- F1: `['COMB2170','COMB2122','COMB2205']` present, `COMB3210` absent; loans % and deposits % via `_ND2205` correct
- F2: 190 options; tree subtotals present; SUB code rankings non-empty (425.45 B top)

---

## Hierarchy is fully reproducible

`build_hierarchy_002.py` rebuilds `ffiec002_hierarchy.json` deterministically from `ReturnFinancialReportPDF.pdf` + `ffiec002_hierarchy_overrides.json`. All fixes (force_rows, caption_fixes, drop_codes) are encoded in the overrides file. Running the script produces a fully valid hierarchy: the fresh build passes all 8 gate checks.

The fresh hierarchy (119 KB) differs slightly from the shipped snapshot (135 KB) due to prior direct
JSON edits that were not backported to the overrides file. The shipped snapshot is the canonical
artifact and passes all gates. If you want a reproducible hierarchy build, use the overrides file;
if you want bit-for-bit fidelity, use the shipped snapshot. Both pass `validate_build_002.py`.

---

## Full-data-rebuild path

To rebuild from raw data (no committed parquet), run in order from `reproduce/`:

| # | Step | Script | Time est. |
|---|---|---|---|
| 1 | Build filer list | `python build_ffiec002_panel.py` | 2 min |
| 2 | Pull data (Chicago Fed + NIC) | `python build_ffiec002_overnight.py` | ~1.5 h (leave Chrome open for NIC phase) |
| 3 | Merge sources | `python finalize_outputs.py` | 5 min |
| 4 | Enrich MDRM titles | `python enrich_mdrm.py` | 1 min |
| 5 | Rebuild hierarchy | `python build_hierarchy_002.py` | 1 s |
| 6 | Gate check | `python validate_build_002.py` | 2 s |
| 7 | Build site | `python make_site_002.py` | ~40 s |

Chicago Fed history (1999–2021 Q2) is downloaded from the Chicago Fed's public file server (not
Akamai-guarded). NIC data (2021 Q3+) requires Playwright + real Chrome (Akamai-guarded). Do NOT
use archive.org mirrors or third-party caches.

---

## Gaps found and fixed during prior clean-room rebuilds

| Gap | Session found | Fixed |
|---|---|---|
| `ffiec002_hierarchy.json` missing from reproduce/ — only in repo root; `validate_build_002.py` exits without it | 2026-06-24 | Added to reproduce/ |
| `ffiec002_panel_long.parquet` missing from reproduce/ — 27.7 MB; within GitHub 100 MB limit | 2026-06-24 | Added to reproduce/ |
| `ReturnFinancialReportPDF.pdf` missing from reproduce/ — required by `build_hierarchy_002.py` | 2026-06-24 | Added to reproduce/ |
| `expected_items.json` stale (943 KB old version) | 2026-06-24 | Updated to current 780 KB |
| `RUNBOOK.md` had wrong script name `make_site.py` and missing `build_hierarchy_002.py` step | 2026-06-24 | Fixed |
| `ffiec002_filer_roster.csv` missing from reproduce/ — `make_site_002.py` produces 0 filers without it | 2026-06-24 | Added (47 KB) |
| `CONTEXT.md` / `REPRODUCE_VERIFIED.md` did not cover §NORMDEN-LEAGUE-002 features | 2026-07-01 | Updated both |
| Repo served from root (non-standard vs FRY9C / Call `app/` layout) | 2026-07-01 | Moved to `app/`; root `index.html` is now a redirect |

## Caveats

1. **`_qa_final.py`** runs from the `External Bank Data\` workspace root (not from reproduce/).
   Its paths reference `FFIEC 002\site_002\index.html` relative to that root.

2. **Chicago Fed source only** — do not use archive.org mirrors or third-party caches.
   NIC data (2021 Q3+) requires Playwright + real Chrome.

3. **COMB2205 (`_ND2205`) workaround is permanent** — see CONTEXT.md for details. Do not revert
   to live DuckDB-WASM queries on RCFD/RCON/RCFN2205; they hang indefinitely in the browser.
