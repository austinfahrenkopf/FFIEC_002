# RUNBOOK — FFIEC 002 Panel (rebuild, verify, deploy)

Quarterly panel of every U.S. branch & agency of a foreign bank (FFIEC 002 filers),
1976 → present (semiannual 1976–79), all reported MDRM items, free public data.
New here? Read `../GLOSSARY.md` first, and `../DID_I_BREAK_IT.md` before pushing any change.

**State as of 2026-07-02:** see `REPRODUCE_VERIFIED.md` for the commit SHA this kit was last
clean-room-verified against. Golden: RCFD2170=245,557,856 @ 2026-03-31 (MUFG Bank NY Branch
RSSD 444819).

**Environment: Python 3.12.** `pip install -r requirements.txt` (versions pinned — the exact set
the clean-room verification used).

---

## TIER 1 — rebuild the dashboard HTML (minutes, no browser automation)

Works from a fresh clone with nothing but Python 3.12 + the pinned requirements. Run from
`reproduce/`:

```powershell
# 1. stage the committed site data next to the engine (the engine reads/writes site_002/)
New-Item -ItemType Directory -Force site_002 | Out-Null
Copy-Item ..\app\*.parquet site_002\
Copy-Item ..\app\ffiec002_hierarchy.json site_002\

# 2. rebuild the HTML from the committed parquet + hierarchy (~seconds)
python make_site_002.py --html-only

# 3. validator (reads ffiec002_panel_long.parquet — committed in this kit — plus site_002/)
python validate_build_002.py
```

### Acceptance test (if ANY line fails, the build is NOT good — stop, do not push)
- `make_site_002.py --html-only` exits 0 and prints the site size.
- `site_002/index.html` matches the committed `..\app\index.html` **byte-for-byte except the
  `Built YYYY-MM-DD HH:MM` timestamp** (and, in principle, NODATA-set ordering — a documented,
  harmless non-determinism; the CODES themselves must be the same set).
- `validate_build_002.py` prints `ALL CHECKS PASSED` and exits 0 (includes the golden-cell check).
- Golden cell: MUFG Bank NY Branch (RSSD 444819) `RCFD2170` @ 2026-03-31 = **245,557,856**.
  Manual re-check straight off the committed data:
  `python -c "import pandas as pd; d=pd.read_parquet('../app/ffiec002.parquet'); print(d[(d.id_rssd==444819)&(d.mdrm=='RCFD2170')&(d.quarter_end=='2026-03-31')].value.iloc[0])"`
- Serve and open it: `cd site_002; python -m http.server 8002` → http://localhost:8002 loads with
  ZERO console errors (F12) and renders the golden entity.

A golden-cell mismatch or a changed check count = real break. A timestamp diff = expected.

## Serve the committed dashboard (no rebuild at all)

```powershell
cd ..\app; python -m http.server 8002    # DuckDB-WASM needs http://, not file://
```

---

## TIER 2 — rebuild the DATA from scratch (hours; needs real Chrome + Playwright)

Some FFIEC/NIC endpoints are Akamai-guarded: **real Chrome via Playwright only — plain
curl/wget/requests are blocked and must not be used against them.** One-time setup on top of
Tier 1: `playwright install chrome` (Google Chrome must be installed).

Run all steps from `reproduce/`:

| # | Command | Produces |
|---|---|---|
| 1 | `python build_ffiec002_panel.py` | `ffiec002_filer_panel.csv` (filer list) |
| 2 | `python build_ffiec002_overnight.py` | Chicago Fed 1999–2021Q2 + NIC 2021Q3→now, merged long CSV (~1.5 h; leave Chrome window open) |
| 3 | `python finalize_outputs.py` | `ffiec002_panel_long.parquet`/`.csv`, `_wide.parquet`, roster |
| 4 | `python enrich_mdrm.py` | fills MDRM titles into the parquet + dictionary |
| 5 | `python build_hierarchy_002.py` | `ffiec002_hierarchy.json` (reads `ReturnFinancialReportPDF.pdf` + overrides) |
| 6 | `python validate_build_002.py` | (exit 0 = pass) **QA gate — must pass before site build** |
| 7 | `python make_site_002.py` | `site_002/` (web explorer + parquet) |

### What's pre-built in this kit (so Tier 2 is optional)
- `ffiec002_hierarchy.json` — final curated form tree (use as-is; re-run step 5 only when editing overrides).
- `ffiec002_panel_long.parquet` — full long panel (27.7 MB), lets `validate_build_002.py` run immediately.
- `ReturnFinancialReportPDF.pdf` — blank FFIEC 002 form PDF (required by `build_hierarchy_002.py`).

## Deploy (GitHub Pages)

```powershell
Copy-Item site_002\index.html ..\app\index.html
Copy-Item site_002\ffiec002.parquet ..\app\ffiec002.parquet
```
Commit and push. Pages serves the `main` branch; the root `index.html` redirects to `app/`.
Then run the full `../DID_I_BREAK_IT.md` checklist against the live URL.

## Quarterly refresh
1. `python build_ffiec002_overnight.py --phase nic` (only pulls the new NIC quarter; Chicago Fed history is frozen at 2021 Q2).
2. `python finalize_outputs.py` → `enrich_mdrm.py` → `validate_build_002.py` → `make_site_002.py`.
3. Copy `site_002/index.html` + `site_002/ffiec002.parquet` → `app/`; commit + push.

## Normden / league checks (after any engine change)
- `#normden` select has 3 options: `COMB2170` (assets), `COMB2122` (loans), `COMB2205` (deposits)
- `buildLGMEAS` present in HTML (governs the league table)
- `_ND2205` and `_ND2205_Q` constants embedded in HTML (WASM deposits-denominator workaround)
- No `COMB3210` option (branches/agencies don't file equity — intentionally absent)

## Sources & key facts
- 1999 Q1–2021 Q2: FRB Chicago "Complete Files" `callYYMM-zip.zip`; pre-1999 history from the same Chicago Fed series.
- 2021 Q3–present: NIC per-filer CSV via real Chrome (Akamai-guarded).
- Filers selected by entity type (IFB/ISB/UFB/USB/UFA/USA) so closed/historical branches are captured.

## Caveats
- Values in **$ thousands**. `RCFD…` = total branch incl. IBF; `RCFN…` = IBF only.
- Two schemas (Chicago Fed = Call layout; NIC = FFIEC 002 layout) overlap on RCFD/RCFN/RCON codes; the `source` column marks each value's origin.
- Schedule M (due from/to related institutions) is confidential — absent everywhere.
- **`COMB2205` WASM hang is permanent** — do not revert to live DuckDB queries on RCFD/RCON/RCFN2205. See CONTEXT.md `_ND2205` section.
