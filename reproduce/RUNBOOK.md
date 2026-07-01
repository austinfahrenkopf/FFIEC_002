# RUNBOOK — FFIEC 002 Panel (build, refresh, deploy)

Quarterly panel of every U.S. branch & agency of a foreign bank (FFIEC 002 filers),
**1999 Q1 → present**, all reported MDRM items, free public data.

**Current state (2026-07-01, commit `bcb6360`):** Full feature parity with FRY9C and FFIEC Call —
sigma calc fix (DOM-safe code-search, file Save/Load), per-extra-chart legend + Labels checkbox +
snap-beside layout, denominator dropdown (COMB2170/2122/2205 — no COMB3210), league table
(190 options), `_ND2205` pre-computed deposits denominator (WASM workaround — PERMANENT, never
revert), Export Builder fidelity fix. Pages ✅ 2026-07-01T19:32:27Z.
Golden: RCFD2170=245,557,856 @ 2026-03-31 (MUFG Bank NY Branch RSSD 444819).

## Prerequisites (once)
```
pip install requests pandas pyarrow playwright
playwright install chromium
```
Google Chrome installed (the NIC step drives real Chrome).

## Repo layout

The dashboard is served from `app/index.html`. The root `index.html` redirects to `app/`.
Data files (`ffiec002.parquet`, `ffiec002_hierarchy.json`) and `serve.ps1` are in `app/`.

For local serving, run:
```powershell
.\app\serve.ps1
```
or:
```powershell
cd app; python -m http.server 8002
```

**Note on FINALIZE.ps1:** The `FINALIZE.ps1` in this reproduce/ kit is designed to run from
the `External Bank Data\` development workspace, not from a fresh clone. Running it from a
fresh clone will produce path errors. From a fresh clone, use the per-step commands below.

## What's pre-built in this kit

- `ffiec002_hierarchy.json` — final curated form tree (use as-is; re-run step 5 only when editing overrides).
- `ffiec002_panel_long.parquet` — full long panel (27.7 MB). Provided so `validate_build_002.py` can run immediately.
- `ReturnFinancialReportPDF.pdf` — blank FFIEC 002 form PDF (required by `build_hierarchy_002.py`).

## Build from scratch — run in order

Run all steps from the `reproduce/` directory.

| # | Command | Produces |
|---|---|---|
| 1 | `python build_ffiec002_panel.py` | `ffiec002_filer_panel.csv` (filer list) |
| 2 | `python build_ffiec002_overnight.py` | Chicago Fed 1999–2021Q2 + NIC 2021Q3→now, merged long CSV (~1.5 h; leave Chrome window open) |
| 3 | `python finalize_outputs.py` | `ffiec002_panel_long.parquet`/`.csv`, `_wide.parquet`, roster |
| 4 | `python enrich_mdrm.py` | fills MDRM titles into the parquet + dictionary |
| 5 | `python build_hierarchy_002.py` | `ffiec002_hierarchy.json` (reads `ReturnFinancialReportPDF.pdf` + overrides; re-run after PDF or overrides change) |
| 6 | `python validate_build_002.py` | (exit 0 = pass) **QA gate — must pass before site build** |
| 7 | `python make_site_002.py` | `site_002/` (web explorer + parquet) |

## HTML-only rebuild (fast iteration)

To regenerate only `index.html` without re-reading the source panel:
```
python make_site_002.py --html-only
```
Reads the existing `site_002/ffiec002.parquet` and re-emits `site_002/index.html` (~4 s).
Use this when editing dashboard UI or JS logic without changing the data pipeline.

## Golden cell (proof the rebuild is correct)

MUFG Bank NY Branch (RSSD 444819) RCFD2170 at 2026-03-31 = **245,557,856** ($ thousands).
`validate_build_002.py` checks this automatically.

## Normden / league checks

After building, confirm:
- `#normden` select has 3 options: `COMB2170` (assets), `COMB2122` (loans), `COMB2205` (deposits)
- `buildLGMEAS` present in HTML (governs the 190-option league table)
- `_ND2205` and `_ND2205_Q` constants embedded in HTML (WASM deposits-denominator workaround)
- No `COMB3210` option (branches/agencies don't file equity — intentionally absent)

## Deploy (GitHub Pages)

After building:
```powershell
Copy-Item site_002\index.html ..\app\index.html
Copy-Item site_002\ffiec002.parquet ..\app\ffiec002.parquet
```
Commit and push. GitHub Pages serves from the `main` branch root; the root `index.html`
redirects to `app/index.html`.

## Outputs
- `ffiec002_panel_long.parquet` / `.csv` — full tidy panel: quarter_end, id_rssd, institution_name, entity_type, mdrm, description, value, source
- `ffiec002_panel_wide.parquet` — one row per filer-quarter, one col per MDRM
- `ffiec002_filer_roster.csv`, `ffiec002_mdrm_dictionary.csv`
- `site_002/` — DuckDB-WASM explorer

## Quarterly refresh
1. `python build_ffiec002_overnight.py --phase nic` (only pulls the new NIC quarter; Chicago Fed history is frozen at 2021 Q2).
2. `python finalize_outputs.py` → `enrich_mdrm.py` → `make_site_002.py`.
3. Copy `site_002/index.html` + `site_002/ffiec002.parquet` → `app/`.
4. Commit + push.

## Sources & key facts
- 1999 Q1–2021 Q2: FRB Chicago "Complete Files" `callYYMM-zip.zip` (carry FFIEC 002 in RCFD/RCFN/RCON MDRM; live but unlinked after 2010).
- 2021 Q3–present: NIC per-filer CSV via real Chrome (Akamai-guarded).
- Filers selected by entity type (IFB/ISB/UFB/USB/UFA/USA) so closed/historical branches are captured (~405 distinct vs 387 in the current roster).

## Caveats
- Values in **$ thousands**. `RCFD…` = total branch incl. IBF; `RCFN…` = IBF only.
- Two schemas (Chicago Fed = Call layout; NIC = FFIEC 002 layout) overlap on RCFD/RCFN/RCON codes; the `source` column marks each value's origin.
- Schedule M (due from/to related institutions) is confidential — absent everywhere.
- **`COMB2205` WASM hang is permanent** — do not revert to live DuckDB queries on RCFD/RCON/RCFN2205. See CONTEXT.md `_ND2205` section.
