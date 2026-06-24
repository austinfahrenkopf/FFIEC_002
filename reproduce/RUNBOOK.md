# RUNBOOK — FFIEC 002 Panel (build, refresh, deploy)

Quarterly panel of every U.S. branch & agency of a foreign bank (FFIEC 002 filers),
**1999 Q1 → present**, all reported MDRM items, free public data.

## Prerequisites (once)
```
pip install requests pandas pyarrow playwright
playwright install chromium
```
Google Chrome installed (the NIC step drives real Chrome).

## What's pre-built in this kit

- `ffiec002_hierarchy.json` — final curated form tree (use as-is; re-run step 5 only when editing overrides).
- `ffiec002_panel_long.parquet` — full long panel (27 MB). Provided so `validate_build_002.py` can run immediately.
- `ReturnFinancialReportPDF.pdf` — blank FFIEC 002 form PDF (required by `build_hierarchy_002.py`).

## Build from scratch — run in order
| # | Command | Produces |
|---|---|---|
| 1 | `python build_ffiec002_panel.py` | `ffiec002_filer_panel.csv` (filer list) |
| 2 | `python build_ffiec002_overnight.py` | Chicago Fed 1999–2021Q2 + NIC 2021Q3→now, merged long CSV (~1.5 h; leave Chrome window open) |
| 3 | `python finalize_outputs.py` | `ffiec002_panel_long.parquet`/`.csv`, `_wide.parquet`, roster |
| 4 | `python enrich_mdrm.py` | fills MDRM titles into the parquet + dictionary |
| 5 | **`python build_hierarchy_002.py`** | `ffiec002_hierarchy.json` | reads `ReturnFinancialReportPDF.pdf` + overrides. Re-run after PDF or overrides change. |
| 6 | **`python validate_build_002.py`** | (exit 0 = pass) | **QA gate — run after step 5. Must pass before site build.** |
| 7 | `python make_site_002.py` | `site_002/` (web explorer + parquet) |

## Golden cell (proof the rebuild is correct)

MUFG Bank NY Branch (RSSD 444819) RCFD2170 at 2026-03-31 = **245,557,856** ($ thousands).
`validate_build_002.py` checks this automatically.

## Outputs
- `ffiec002_panel_long.parquet` / `.csv` — full tidy panel: quarter_end, id_rssd, institution_name, entity_type, mdrm, description, value, source
- `ffiec002_panel_wide.parquet` — one row per filer-quarter, one col per MDRM
- `ffiec002_filer_roster.csv`, `ffiec002_mdrm_dictionary.csv`
- `site_002/` — DuckDB-WASM explorer

## Quarterly refresh
1. `python build_ffiec002_overnight.py --phase nic` (only pulls the new NIC quarter; Chicago Fed history is frozen at 2021 Q2).
2. `python finalize_outputs.py` → `enrich_mdrm.py` → `make_site_002.py`.
3. Upload `site_002/index.html` + `site_002/ffiec002.parquet`.

## Sources & key facts
- 1999 Q1–2021 Q2: FRB Chicago "Complete Files" `callYYMM-zip.zip` (carry FFIEC 002 in RCFD/RCFN/RCON MDRM; live but unlinked after 2010).
- 2021 Q3–present: NIC per-filer CSV via real Chrome (Akamai-guarded).
- Filers selected by entity type (IFB/ISB/UFB/USB/UFA/USA) so closed/historical branches are captured (~405 distinct vs 387 in the current roster).

## Caveats
- Values in **$ thousands**. `RCFD…` = total branch incl. IBF; `RCFN…` = IBF only.
- Two schemas (Chicago Fed = Call layout; NIC = FFIEC 002 layout) overlap on RCFD/RCFN/RCON codes; the `source` column marks each value's origin.
- Schedule M (due from/to related institutions) is confidential — absent everywhere.
