# FFIEC 002 Dashboard

Interactive browser dashboard over the **FFIEC 002** report — U.S. branches and agencies of
foreign banks. Covers ~200+ active foreign-bank branches filing quarterly with the Federal
Reserve since the 1990s.

**Live site:** https://austinfahrenkopf.github.io/FFIEC_002/

Data source: Chicago Fed "Complete" FFIEC 002 files — free public data, no subscription required.

---

## What it is

A single-page application that runs entirely in the browser. Data is stored as a single Parquet
file served from this repo; all SQL queries execute client-side via **DuckDB-WASM** (no server).
The dashboard lets you:

- Browse all FFIEC 002 line items organized by schedule (A through S, RAL, M, …)
- Chart any measure for any branch/agency or aggregate (ALL, size buckets)
- Compare entities side-by-side, build custom peer groups, export to CSV/Excel
- View KPI tiles (QoQ %, YoY %, total-period Δ) and a quarterly data table

---

## Repo layout

```
/                              GitHub Pages root (served as the live dashboard)
├── index.html                 Dashboard application (self-contained HTML + embedded JS + CSS)
├── ffiec002_hierarchy.json    FFIEC 002 schedule/line-item tree (built from form PDF + overrides)
├── ffiec002.parquet           Full panel — all branches, all quarters (~7.8 MB)
├── .nojekyll                  Tells GitHub Pages not to run Jekyll processing
├── README.md                  This file
├── FFIEC_002_complete.zip     Convenience zip of the full reproduce/ kit
└── reproduce/                 Full reproduction kit — everything needed to rebuild from scratch
    ├── FFIEC002_202606_f.pdf              Blank FFIEC 002 form (structural reference for the parser)
    ├── requirements.txt                   Python dependencies
    ├── download_ffiec002_playwright.py    Step 1: download data from Chicago Fed (Playwright)
    ├── stack_ffiec002_csvs.py             Step 2: stack raw CSVs into a single panel
    ├── build_ffiec002_panel.py            Step 3: build the panel parquet
    ├── build_ffiec002_overnight.py        Step 3b: extended overnight build (full history)
    ├── enrich_mdrm.py                     Step 4: enrich with MDRM descriptions
    ├── aggregate_extract.py               Step 5: build aggregate (ALL) scope data
    ├── build_segments.py                  Step 6: build segment/peer-group data
    ├── finalize_outputs.py                Step 7: finalize and package outputs
    ├── build_hierarchy_002.py             Step 8: parse PDF + overrides → ffiec002_hierarchy.json
    ├── make_site_002.py                   Step 9: build dashboard site_002/ from panel + hierarchy
    ├── validate_build_002.py              Step 10: gate check (golden cell + DERIV validation)
    ├── _completeness_gate.py              Step 10b: bidirectional completeness gate
    ├── _qa_final.py                       Step 11: 23-point QA smoke test (all 3 dashboards)
    ├── FINALIZE.ps1                       One-shot rebuild + QA (all 3 dashboards)
    ├── chicagofed_check.py                Utility: verify Chicago Fed data freshness
    ├── entity_check.py                    Utility: audit filer roster
    ├── check_schedule_n.py                Utility: validate Schedule N structure
    ├── ffiec002_hierarchy_overrides.json  Force-rows, caption fixes, drop-codes post-parse
    ├── ffiec002_completeness_exclusions.json  Known-absent codes excluded from gate
    ├── ffiec002_mdrm_dictionary.csv       MDRM data dictionary
    ├── expected_items.json                Expected line-item set for gate reference
    └── CONTEXT.md                         Design decisions and methodology for future editors
```

---

## Dependencies (one-time setup)

```powershell
pip install -r reproduce/requirements.txt
playwright install chrome
```

Requires **Python 3.10+**. DuckDB runs as DuckDB-WASM in the browser — no Python `duckdb`
needed. Playwright is needed only for the Chicago Fed download step.

---

## Full pipeline: rebuild from scratch

Raw data is NOT committed to this repo (the full panel CSV is ~487 MB). To rebuild completely:

### Step 1 — Download raw data  *(skip if you already have the panel)*

```powershell
cd "FFIEC 002"
python download_ffiec002_playwright.py   # downloads Chicago Fed Complete files
python stack_ffiec002_csvs.py            # stacks raw CSVs into combined form
```

The Chicago Fed hosts the FFIEC 002 "Complete" file series. Unlike some other Fed endpoints,
this is usually a direct download — but `download_ffiec002_playwright.py` uses Playwright
to handle any auth/navigation reliably.

### Step 2 — Build the panel

```powershell
python build_ffiec002_panel.py           # parses CSVs → ffiec002_panel_long.parquet
python enrich_mdrm.py                    # enriches with MDRM descriptions
python aggregate_extract.py             # builds ALL/aggregate scope rows
python build_segments.py                # builds peer-group segment data
python finalize_outputs.py              # packages outputs
```

`ffiec002_panel_long.parquet` (~17 MB) is the source of truth for entity data.
It is not committed here; regenerate from the downloaded CSVs.

### Step 3 — Build the hierarchy  *(run whenever overrides change)*

```powershell
python build_hierarchy_002.py
```

Reads `FFIEC002_202606_f.pdf` via `pypdf`, extracts schedule structure, applies
`ffiec002_hierarchy_overrides.json` (caption fixes, force-rows, drop-codes).
Outputs `ffiec002_hierarchy.json`.

### Step 4 — Build and validate the dashboard site

```powershell
python make_site_002.py                  # full build → site_002/ (parquet + index.html)
python validate_build_002.py             # must exit 0 and print "ALL CHECKS PASSED"
```

For a quick HTML-only rebuild (parquet unchanged):
```powershell
python make_site_002.py --html-only
```

### Step 5 — One-shot rebuild (after initial setup)

```powershell
# From the "External Bank Data\" project root:
.\FINALIZE.ps1
```

Prints `FINALIZE COMPLETE - ALL PASSED` on success.

### Step 6 — Serve locally

```powershell
cd site_002
python -m http.server 8002
# open http://localhost:8002
```

---

## Typical edit-rebuild loop

```
edit ffiec002_hierarchy_overrides.json
  → python build_hierarchy_002.py
  → python validate_build_002.py
  → python make_site_002.py --html-only
  → reload http://localhost:8002
```

---

## Parquet layout

Unlike the Y-9C (which uses entity-clustered era shards), the FFIEC 002 uses a **single
`ffiec002.parquet`** (~7.8 MB). The filer universe is small enough (~200 active branches)
that a single file is efficient — DuckDB-WASM loads it in full on startup.

---

## GitHub Pages deployment

Settings → Pages → Source = Deploy from branch → `main` / `(root)`.

Site live at `https://austinfahrenkopf.github.io/FFIEC_002/` after each push.

**Size notes:** All files well under 50 MB — no GitHub size warnings expected.

---

## Known deferred cosmetic

98 ALL-CAPS schedule captions (e.g., "ASSETS", "LIABILITIES") are displayed in uppercase
as they appear in the raw data. This is a cosmetic difference from the title-case PDF
rendering; it does not affect data or structure. Deferred for a future caption-normalization
pass in `ffiec002_hierarchy_overrides.json`.

---

## Data source

Free public data — no subscription required:

- **FFIEC 002 filings:** [Chicago Fed Complete Files](https://www.chicagofed.org/banking/financial-institution-reports/bhc-data)
  (quarterly; usually direct download)
- **MDRM dictionary:** Fed's MDRM bulk download (fetched by `enrich_mdrm.py`)

No data is bought or licensed.
