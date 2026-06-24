# RUNBOOK — FFIEC 002 Panel (build, refresh, deploy)

Quarterly panel of every U.S. branch & agency of a foreign bank (FFIEC 002 filers),
**1999 Q1 → present**, all reported MDRM items, free public data.

## Prerequisites (once)
```
pip install requests pandas pyarrow playwright
playwright install chromium
```
Google Chrome installed (the NIC step drives real Chrome). Put the three NIC
Attributes files in this folder as `CSV_ATTRIBUTES_ACTIVE/CLOSED/BRANCHES.csv`
(download from https://www.ffiec.gov/npw/FinancialReport/DataDownload — convert the
XML to CSV if needed).

## Build from scratch — run in order
| # | Command | Produces |
|---|---|---|
| 1 | `python build_ffiec002_panel.py` | `ffiec002_filer_panel.csv` (filer list) |
| 2 | `python build_ffiec002_overnight.py` | Chicago Fed 1999–2021Q2 + NIC 2021Q3→now, merged long CSV (~1.5 h; leave Chrome window open) |
| 3 | `python finalize_outputs.py` | `ffiec002_panel_long.parquet`/`.csv`, `_wide.parquet`, roster |
| 4 | `python enrich_mdrm.py` | fills MDRM titles into the parquet + dictionary |
| 5 | `python aggregate_extract.py` | `ffiec002_tdnyb_vs_allbanks_*.csv` |
| 6 | `python build_segments.py` | `ffiec002_segments_long.csv` (Excel/Power Query buckets) |
| 7 | `python make_site.py` | `site/` (web explorer + parquet) |

## Outputs
- `ffiec002_panel_long.parquet` / `.csv` — full tidy panel: quarter_end, id_rssd,
  institution_name, entity_type, mdrm, description, value, source
- `ffiec002_panel_wide.parquet` — one row per filer-quarter, one col per MDRM
- `ffiec002_segments_long.csv` — pre-aggregated buckets (ALL_BANKS; UFB/USB/UFA/USA/
  IFB/ISB; BRANCHES_ALL/AGENCIES_ALL/INSURED_ALL/UNINSURED_ALL; TD_NYB) + derived NPL
- `ffiec002_tdnyb_vs_allbanks_long.csv` / `_wide.csv` — TD vs all-banks
- `ffiec002_filer_roster.csv`, `ffiec002_mdrm_dictionary.csv`
- `site/` — DuckDB-WASM explorer

## Deploy the explorer (GitHub Pages)
Upload the contents of `site/` to the repo (Add file → Upload files):
- always `site/index.html`
- `site/ffiec002.parquet` whenever the data changed (steps 3–4)
Live at `https://<user>.github.io/<repo>/` (reachable from work).

## Reproducibility bundle
```
Compress-Archive -Force -DestinationPath ffiec002_project_bundle.zip -Path `
 RUNBOOK.md, README_FFIEC002.md, build_ffiec002_panel.py, build_ffiec002_overnight.py, `
 finalize_outputs.py, enrich_mdrm.py, aggregate_extract.py, build_segments.py, make_site.py, `
 download_ffiec002_playwright.py, stack_ffiec002_csvs.py, `
 chicagofed_check.py, entity_check.py, check_schedule_n.py, `
 ffiec002_filer_panel.csv, ffiec002_filer_roster.csv, ffiec002_mdrm_dictionary.csv, `
 ffiec002_panel_long.parquet
```
Upload `ffiec002_project_bundle.zip` to the repo.

## Quarterly refresh
1. Re-download the three NIC Attributes files → `python build_ffiec002_panel.py`.
2. `python build_ffiec002_overnight.py --phase nic` (only pulls the new NIC quarter;
   Chicago Fed history is frozen at 2021 Q2 and never changes).
3. `python finalize_outputs.py` → `enrich_mdrm.py` → `aggregate_extract.py` →
   `build_segments.py` → `make_site.py`.
4. Re-upload `site/index.html` + `site/ffiec002.parquet`.

## Sources & key facts
- 1999 Q1–2021 Q2: FRB Chicago "Complete Files" `callYYMM-zip.zip` (carry FFIEC 002
  in RCFD/RCFN/RCON MDRM; live but unlinked after 2010).
- 2021 Q3–present: NIC per-filer CSV via real Chrome (Akamai-guarded).
- Filers selected by entity type (IFB/ISB/UFB/USB/UFA/USA) so closed/historical
  branches are captured (~405 distinct vs 387 in the current roster).

## Caveats
- Values in **$ thousands**. `RCFD…` = total branch incl. IBF; `RCFN…` = IBF only.
- Two schemas (Chicago Fed = Call layout; NIC = FFIEC 002 layout) overlap on the
  RCFD/RCFN/RCON codes; the `source` column marks each value's origin.
- Schedule M (due from/to related institutions) is confidential — absent everywhere.
- Validate `ALL_BANKS` `RCFD2170` vs the Fed H.8 / "Assets and Liabilities of U.S.
  Branches and Agencies of Foreign Banks" (≈ $1T at 2001, ≈ $3T now).
