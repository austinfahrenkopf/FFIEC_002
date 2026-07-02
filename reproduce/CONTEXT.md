# FFIEC 002 Dashboard — Design Context for Future Editors

This document distills the standing design decisions, methodology constraints, and
non-obvious implementation choices for the FFIEC 002 dashboard. Read this before making
substantive changes to `make_site_002.py`, `build_hierarchy_002.py`, or the curated
input files (`ffiec002_hierarchy_overrides.json`).

> **Start here (added 2026-07-02, M.1 packaging):**
> - Every term of art (MDRM, COMB, DERIV, golden cell, NODATA, …) is defined in `../GLOSSARY.md`.
> - **Three-clone rule:** this engine is one of three hand-synced clones —
>   [Call_Reports](https://github.com/austinfahrenkopf/Call_Reports) ·
>   [FFIEC_002](https://github.com/austinfahrenkopf/FFIEC_002) ·
>   [FRY9C](https://github.com/austinfahrenkopf/FRY9C). An engine/UI fix here almost certainly
>   belongs in the other two; a data CODE must never be copied across forms without proving it
>   exists in that form's parquet.
> - **Golden cell:** MUFG Bank NY Branch (RSSD 444819) `RCFD2170` @ 2026-03-31 = **245,557,856**.
> - Before pushing any change: `../DID_I_BREAK_IT.md`. Current verified commit: see
>   `REPRODUCE_VERIFIED.md` (which also records the sibling repos' SHAs for this cycle).

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

## Mis-nest de-nestings (9 hierarchy bugs, 2026-07)

Triage identified **9 real hierarchy mis-nests in bucket A** (credit-derivative and C-II pairs):

- **3 credit-derivative beneficiary legs** — in Schedule L, the beneficiary-side fair-value
  and notional rows (RCFDC221, RCFDC222, and their Schedule E counterparts) were nested under
  the guarantor parent instead of the beneficiary parent. Fixed via `ffiec002_hierarchy_overrides.json`
  caption_fixes + force_rows to re-parent them.

- **6 C-II count/amount pairs** — pairs of count and notional-amount codes in Schedule C-II
  were nested as siblings of a header instead of children. De-nested by adjusting depth in
  the overrides file.

All 9 fixes are encoded in `ffiec002_hierarchy_overrides.json`. The gate (`validate_build_002.py`)
and completeness check (`_completeness_gate.py`) verify the correct structure after each rebuild.

---

## Export Builder fidelity fix (§EXPORT-FIX, ebRawCodes)

`ebRawCodes()` is the function that assembles the code list for the Export Builder modal.
Prior to the fix, it returned only DERIV/LGMEAS base codes, not the full set of raw MDRM
codes that the site parquet actually contains. The fix changed `ebRawCodes()` to walk
the site parquet's unique MDRM codes directly, ensuring every code that can be exported
is listed — including codes not referenced by the HIER tree.

---

## Denominator dropdown (÷ assets; §NORMDEN)

The dashboard has a compound control: **`#normbyassets` checkbox** + **`#normden` select** dropdown.

**002-specific presets** (`NORM_DEN_LABELS` dict):
| Key | Description |
|---|---|
| `COMB2170` | Total assets |
| `COMB2122` | Total loans and leases |
| `COMB2205` | Total deposits (see `_ND2205` workaround below) |

**`COMB3210` equity is intentionally absent.** FFIEC 002 branches and agencies of foreign banks
do not file RAL (Report of Assets and Liabilities) equity capital items, so there is no
`COMB3210` value to use as a denominator. Do not add it.

**Implementation:**
- `window._normDenCd` — current denominator code, readable from outside (Playwright tests).
- `localStorage` key `ffiec002_normden` / `ffiec002_normbyassets` — persists selection.
- `_getLinkTfm()` / `_applyLinkedTfm()` — propagates the denominator to linked charts.
- `recompute()` reads `#normden.value` to decide whether to normalize.

---

## CRITICAL: `_ND2205` pre-computed WASM workaround (PERMANENT — do not revert)

**Problem:** Any live DuckDB-WASM query on `RCFD2205`, `RCON2205`, or `RCFN2205` (total deposits)
hangs indefinitely in the browser (>40 s; confirmed across browsers). Root cause is unknown but
consistent — these three codes trigger a pathological query plan in the WASM build of DuckDB.

**Fix (permanent):** At HTML build time (`make_site_002.py`), the total-deposits denominator is
pre-computed from the site parquet and embedded into the HTML as two JavaScript constants:

```python
_nd_raw = pd.read_parquet(_nd_site_pq, columns=["id_rssd","quarter_end","mdrm","value"])
# coalesce RCFD2205 > RCON2205 > RCFN2205 per entity per quarter
```

The embedded constants are:
- `_ND2205_Q` — ordered array of `[quarter_end, quarter_index]` pairs (184 quarters)
- `_ND2205` — map of `{rssd: [value_at_Q0, value_at_Q1, ...]}` (658 entities, ~0.6 MB inline)

At runtime, `perFilerValues('COMB2205')` coalesces from `_ND2205` instead of querying DuckDB.

**Never revert to live queries on RCFD/RCON/RCFN2205.** The hang is not intermittent — it
is 100% reproducible. The pre-computation adds ~0.3 s to the build and ~0.6 MB to the HTML.

**Module-scope false negative (Playwright caveat):** `page.evaluate("typeof _ND2205_Q !== 'undefined'")`
returns `false` even when the constant is present, because it is declared as a module-scoped
`const`. Use the `window._ndQLen` proxy variable (an integer also embedded in the HTML) for
Playwright assertions instead.

---

## League table full measure set (§NORMDEN-LEAGUE, buildLGMEAS)

`buildLGMEAS()` walks the full HIER and creates a league-table option for every leaf and
header node (190 options as of 2026-07-01). Implementation details:

- `emitSchedule(sch)` → `nest()` → `descCodes()` — same HIER walk as FFIEC Call (no `hybrid_sum`
  special case; 002 hierarchy is flat).
- For every HIER header node, creates `DYN['SUB:'+nd.code]` with `{type:'sum', plus:[base_codes]}`
  so schedule subtotals are computable in the league context.
- `pct` flag: `d.type==='ratio'` (not `d.type!=='sum'`) — ensures raw-% codes are treated as
  ratios in ranking.
- `perFilerValues()` uses `||DYN[measCode]` coalesce so SUB: entries resolve correctly.

**DYN subtotals clarification (update to prior doc):** The statement "No DYN subtotals (002 is flat)"
referred to tree-click DYN behavior — clicking a schedule header in the tree still does not
produce a DYN chart in 002. However, `buildLGMEAS()` now creates `DYN['SUB:...']` entries for
the league table. These are league-only; tree-click DYN remains absent from 002.

---

## Null-filter in `draw()` (correctness fix)

`draw()` applies `.filter(r=>r[1]!==null)` on the normalized series before charting.

**Why:** When the normden denominator (e.g., `COMB2205` via `_ND2205`) only covers quarters
where the filer filed FFIEC 002, while the main measure covers additional quarters from the
Chicago Fed era, the normalized series may contain `null` for quarters with no denominator
value. Without the filter, the chart passes `null` to scale functions (`f(null)` → `TypeError`).

This fix is 002-specific because the pre-computed `_ND2205` array has a fixed set of
quarters. The other denominators (`COMB2170`, `COMB2122`) are live queries that naturally
return no row for quarters with no data, so they don't produce `null` either — but the
filter is harmless for those cases too.

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
a **single `ffiec002.parquet`** (~14 MB as of 2026-07-01, compressed). The filer universe
is small enough that one file is efficient. DuckDB-WASM loads it in full on startup.

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

## Layout: `app/` (standardized 2026-07-01)

The repo serves the dashboard from `app/index.html`. The root `index.html` is a
`<meta http-equiv="refresh">` redirect to `app/index.html`. Data files
(`ffiec002.parquet`, `ffiec002_hierarchy.json`) and `serve.ps1` live in `app/`.

This matches the FRY9C and FFIEC Call layout. The live Pages URL
(`https://austinfahrenkopf.github.io/FFIEC_002/`) works via the root redirect.

---

## Validation checkpoints

| Check | Tool | Pass condition |
|---|---|---|
| Golden cell | `validate_build_002.py` | Known NY Fed branch value at a fixed quarter |
| DERIV codes resolve | `validate_build_002.py` | All DERIV num/den codes in panel |
| Bidirectional completeness | `_completeness_gate.py` | 0 missing, 0 unexpected |
| Rendered-vs-PDF | Manual + overrides audit | 18/18 schedules match form |
| Engine smoke test | `_qa_final.py` | All QA checks pass |
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
