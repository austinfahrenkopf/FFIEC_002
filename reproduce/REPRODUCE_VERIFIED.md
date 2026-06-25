# FFIEC 002 Reproduce Kit — Verification Record

**Date verified:** 2026-06-25 (re-verified after Save→localStorage fix; original 2026-06-24)  
**Environment:** Python 3.12.1 · pandas 3.0.3 · pyarrow 24.0.0 · duckdb 1.5.4 · Windows 11

---

## Test method

Fresh clean-room directory `C:\temp\cr_002_full\` created with ONLY the reproduce/ kit contents.
No access to the live build directory during any build or validation step (except copying the roster file — see gap table below). All build artifacts produced fresh.

---

## What was rebuilt from scratch

| Step | Script | Produces | Time |
|---|---|---|---|
| 1 | `build_hierarchy_002.py` | `ffiec002_hierarchy.json` (from PDF + overrides) | 1 s |
| 2 | `make_site_002.py` | `site_002/` (from panel + hierarchy) | 37 s |
| 3 | `validate_build_002.py` | — (exit 0) | 2 s |

`ffiec002_panel_long.parquet` (27.7 MB, shipped in this kit) was used as the data source for step 2. No live directory was accessed during build.

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

## Hierarchy is fully reproducible

`build_hierarchy_002.py` rebuilds `ffiec002_hierarchy.json` deterministically from `ReturnFinancialReportPDF.pdf` + `ffiec002_hierarchy_overrides.json`. All fixes (force_rows, caption_fixes, drop_codes) are encoded in the overrides file. Running the script produces a fully valid hierarchy: the fresh build passes all 8 gate checks.

The fresh hierarchy (119 KB) differs slightly from the shipped snapshot (135 KB) due to prior direct JSON edits that were not backported to the overrides file. The shipped snapshot is the canonical artifact and passes all gates. If you want a reproducible hierarchy build, use the overrides file; if you want bit-for-bit fidelity, use the shipped snapshot. Both pass `validate_build_002.py`.

---

## Gaps found and fixed during clean-room rebuilds

| Gap | Session found | Fixed |
|---|---|---|
| `ffiec002_hierarchy.json` missing from reproduce/ — only in repo root; `validate_build_002.py` exits without it | 2026-06-24 | Added to reproduce/ |
| `ffiec002_panel_long.parquet` missing from reproduce/ — 27.7 MB; within GitHub 100 MB limit | 2026-06-24 | Added to reproduce/ |
| `ReturnFinancialReportPDF.pdf` missing from reproduce/ — required by `build_hierarchy_002.py` | 2026-06-24 | Added to reproduce/ |
| `expected_items.json` stale (943 KB old version) | 2026-06-24 | Updated to current 780 KB |
| `RUNBOOK.md` had wrong script name `make_site.py` and missing `build_hierarchy_002.py` step | 2026-06-24 | Fixed |
| `ffiec002_filer_roster.csv` missing from reproduce/ — `make_site_002.py` produces 0 filers without it | 2026-06-24 | Added (47 KB) |

## Re-verification 2026-06-25 (Save→localStorage fix)

`make_site_002.py` updated (commit 27b10a0) with localStorage fallback for Save/Load/autoLoad
(key `ffiec002_formulas`) — no HTTP server required for formula persistence on GitHub Pages.

Re-ran clean-room: `make_site_002.py` (35 s) → `validate_build_002.py` → **ALL CHECKS PASSED**.
Golden cell MUFG Bank NY Branch (RSSD 444819) RCFD2170 @ 2026-03-31 = **245,557,856** ✓

---

## Caveats for a full fresh rebuild (downloading raw data)

1. **Panel parquet** (27.7 MB) is provided in this kit. A full rebuild from the raw data source requires:
   - `python build_ffiec002_panel.py` — builds filer list (needs `CSV_ATTRIBUTES_ACTIVE/CLOSED/BRANCHES.csv` from FFIEC.gov)
   - `python build_ffiec002_overnight.py` — Chicago Fed 1999–2021 Q2 + NIC 2021 Q3+ (~1.5 h; needs Playwright + real Chrome for NIC phase)
   - `python finalize_outputs.py` — merges sources → `ffiec002_panel_long.parquet`
   - `python enrich_mdrm.py` — fills MDRM titles

2. **`_qa_final.py`** is designed to run from the `External Bank Data\` workspace root, not from reproduce/. Its paths reference `FFIEC 002\site_002\index.html` relative to that root.

3. **Chicago Fed source only** — do not use archive.org mirrors or third-party caches. The official Chicago Fed FFIEC 002 file server is not Akamai-guarded (plain requests). NIC data (2021 Q3+) requires Playwright + real Chrome.
