# FFIEC 002 Dashboard

Free, reproducible browser dashboard over public FFIEC 002 filings — every U.S. branch and agency of a foreign bank, plus ALL / branch-type aggregates and custom peer groups, 1976–present (semiannual 1976–79, quarterly from 1980), $ thousands. No server: static HTML + DuckDB-WASM; the parquet loads in your browser.

**Live:** https://austinfahrenkopf.github.io/FFIEC_002/app/index.html
**Siblings:** [Call_Reports](https://github.com/austinfahrenkopf/Call_Reports) · [FFIEC_002](https://github.com/austinfahrenkopf/FFIEC_002) · [FRY9C](https://github.com/austinfahrenkopf/FRY9C) (three hand-synced dashboards — see GLOSSARY.md "three-clone rule")

## Use it
Open the live URL. Pick a branch (name or RSSD) → click measures in the left rail, or hit ⚡ Views for one-click preset analyses. All aggregates are Σnumerator/Σdenominator. Data as of: 2026-Q1.

## Run locally
Clone → serve the app folder (`cd app; python -m http.server 8002`) → open http://localhost:8002. No build needed; the committed HTML + parquet are the deployable artifact. (DuckDB-WASM needs `http://`, not `file://`.)

## Rebuild from source (Tier 1 — no browser automation needed)
Requirements: Python 3.12, `pip install -r reproduce/requirements.txt` (pandas, pyarrow).
See `reproduce/RUNBOOK.md` § Tier 1: rebuild `index.html` from the committed parquet + hierarchy, then follow DID_I_BREAK_IT.md.

## Rebuild the DATA from scratch (Tier 2 — full pipeline)
Needs real Chrome + Playwright (some FFIEC endpoints are bot-guarded; plain HTTP clients are blocked and must not be used). See `reproduce/RUNBOOK.md` § Tier 2. Everything comes from free public sources: Chicago Fed FFIEC 002 Complete files, the FFIEC CDR, and the Fed MDRM dictionary.

## Trust & verification
Every number is traceable to public filings. Regression tripwires: a hand-verified golden cell (RCFD2170 = 245,557,856 @ 2026-03-31, MUFG Bank NY Branch — see GLOSSARY.md), `reproduce/validate_build_002.py`, and REPRODUCE_VERIFIED.md documenting a clean-room rebuild. Before changing anything, read GLOSSARY.md and DID_I_BREAK_IT.md.

## License
MIT (see LICENSE). The underlying data is U.S. government public-domain regulatory filings.
