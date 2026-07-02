# REPRODUCE_VERIFIED — clean-room rebuild record

**Verified: 2026-07-02, against commit `256c108`** (M.1 packaging cycle).
Sibling repos at this cycle: Call_Reports `368d5ef` · FRY9C `c92d60d`.

## What was run (automated, `_verify/acceptance_m1.py` in the dev workspace — mirrors RUNBOOK.md § Tier 1 verbatim)

Fresh `git clone` into an empty temp dir (no dev-workspace files reachable) → clean `venv`
(Python 3.12.1) → `pip install -r reproduce/requirements.txt` (pinned: pandas 3.0.3, pyarrow 24.0.0,
duckdb 1.5.4, playwright 1.60.0, requests 2.34.2) → RUNBOOK Tier-1 steps → checks below.

## Results — 11/11 PASS

| Check | Result |
|---|---|
| clone + venv + pinned pip install | PASS |
| `make_site_002.py --html-only` | PASS, exit 0 |
| rebuilt `site_002/index.html` vs committed `app/index.html` | **byte-identical** after `Built <ts>` normalization (834,105 chars) |
| `validate_build_002.py` | **ALL CHECKS PASSED** (panel committed in kit → full check set incl. golden) |
| golden cell off the cloned parquet (pandas one-liner) | 245,557,856 exact (MUFG Bank NY Branch RSSD 444819, RCFD2170 @2026-03-31) |
| serve cloned `app/` + headless Chromium | loads, golden entity (RSSD 112819 spot entity) renders, **zero console errors, zero 4xx** |

## Expected/allowed diffs
- The `Built YYYY-MM-DD HH:MM` stamp (one occurrence). Nothing else — this run was byte-identical
  otherwise. NODATA-set ordering is a theoretically-possible harmless diff; it did not occur here.

## Found-and-fixed during this verification (why the kit looks the way it does)
- The kit had drifted to a STALE `validate_build_002.py` + its own `_completeness_gate.py` variant;
  the stale pair mis-failed DUP_ITEM on 9 legitimate two-column items. The kit now carries the
  blessed pair the workspace actually runs (plus the current mdrm dictionary).
- `requirements.txt` gains `duckdb` (the completeness gate queries the panel with it; the old
  comment claiming duckdb was browser-only was wrong).
