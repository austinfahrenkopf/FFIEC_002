#!/usr/bin/env python3
"""
build_segments.py
Pre-aggregated SEGMENT extract for Excel / Power Query / pivots — the consolidated
buckets only (not the 4.3M-row filer-level panel), so it's small and ingestible.

Segments produced (per quarter, per MDRM, summed across the member filers):
  ALL_BANKS
  charter type:   UFB, USB, UFA, USA, IFB, ISB
  groups:         BRANCHES_ALL, AGENCIES_ALL, INSURED_ALL, UNINSURED_ALL
  filer:          TD_NYB (RSSD 450810)               (handy benchmark)
Plus two derived rows per segment/quarter:
  DERIV_NPL       = RCFD1403 + RCFD1406 + RCFD1407
  DERIV_NPL_PCT   = 100 * DERIV_NPL / RCFD2122

Output columns: segment, segment_type, quarter_end, mdrm, description, value, n_filers
Files: ffiec002_segments_long.csv  (+ .parquet for Python)

Setup:  pip install pandas pyarrow
Run:    python build_segments.py
        python build_segments.py --mdrm RCFD2170,RCFD2122,RCFD1403  (subset = tiny file)
"""
from __future__ import annotations
import argparse
import pandas as pd

SRC = "ffiec002_panel_long.parquet"
OUT_CSV = "ffiec002_segments_long.csv"
OUT_PQ  = "ffiec002_segments_long.parquet"
NPL_CODES = ["RCFD1403","RCFD1406","RCFD1407"]
DEN_CODE  = "RCFD2122"

ap = argparse.ArgumentParser()
ap.add_argument("--mdrm", default="", help="comma-separated MDRM codes to keep (default all)")
a = ap.parse_args()

print(f"reading {SRC} ...")
df = pd.read_parquet(SRC)
df["value"] = pd.to_numeric(df["value"], errors="coerce")
df = df.dropna(subset=["value"])
df["entity_type"] = df["entity_type"].fillna("").astype(str)

# segment definitions: name -> (segment_type, row-mask)
et = df["entity_type"]
SEG = {
 "ALL_BANKS":      ("all",          pd.Series(True, index=df.index)),
 "UFB":            ("charter_type", et.eq("UFB")),
 "USB":            ("charter_type", et.eq("USB")),
 "UFA":            ("charter_type", et.eq("UFA")),
 "USA":            ("charter_type", et.eq("USA")),
 "IFB":            ("charter_type", et.eq("IFB")),
 "ISB":            ("charter_type", et.eq("ISB")),
 "BRANCHES_ALL":   ("group",        et.isin(["IFB","ISB","UFB","USB"])),
 "AGENCIES_ALL":   ("group",        et.isin(["UFA","USA"])),
 "INSURED_ALL":    ("group",        et.isin(["IFB","ISB"])),
 "UNINSURED_ALL":  ("group",        et.isin(["UFB","USB","UFA","USA"])),
 "TD_NYB":         ("filer",        df["id_rssd"].eq(450810)),
}

keep = [c.strip().upper() for c in a.mdrm.split(",") if c.strip()] if a.mdrm else None
out = []
for name,(stype,mask) in SEG.items():
    sub = df[mask]
    if sub.empty:
        print(f"  {name}: 0 rows"); continue
    g = (sub.groupby(["quarter_end","mdrm"], as_index=False)
            .agg(description=("description","first"), value=("value","sum"),
                 n_filers=("id_rssd","nunique")))
    # derived rows
    npl = (sub[sub.mdrm.isin(NPL_CODES)].groupby("quarter_end")
              .agg(value=("value","sum"), n_filers=("id_rssd","nunique")).reset_index())
    npl["mdrm"]="DERIV_NPL"; npl["description"]="Derived: Non-performing loans (RCFD1403+1406+1407)"
    den = (sub[sub.mdrm.eq(DEN_CODE)].groupby("quarter_end")["value"].sum())
    nser = npl.set_index("quarter_end")["value"]
    pct = (100.0*nser/den).dropna().reset_index().rename(columns={0:"value","value":"value"})
    pct.columns=["quarter_end","value"]
    pct["mdrm"]="DERIV_NPL_PCT"; pct["description"]="Derived: NPL % (NPL / RCFD2122)"; pct["n_filers"]=""
    seg = pd.concat([g, npl[["quarter_end","mdrm","description","value","n_filers"]], pct],
                    ignore_index=True)
    seg.insert(0,"segment",name); seg.insert(1,"segment_type",stype)
    out.append(seg)

res = pd.concat(out, ignore_index=True)
if keep:
    res = res[res["mdrm"].isin(keep + ["DERIV_NPL","DERIV_NPL_PCT"])]
res = res[["segment","segment_type","quarter_end","mdrm","description","value","n_filers"]]
res = res.sort_values(["segment","mdrm","quarter_end"]).reset_index(drop=True)

res.to_csv(OUT_CSV, index=False)
try: res.to_parquet(OUT_PQ, index=False)
except Exception as e: print("  (parquet skipped:", e, ")")

print(f"\nwrote {OUT_CSV}: {len(res):,} rows, {res['segment'].nunique()} segments, "
      f"{res['mdrm'].nunique()} line items, {res['quarter_end'].nunique()} quarters")
print("Columns: segment, segment_type, quarter_end, mdrm, description, value, n_filers")
print("In Power Query: load this file, filter 'mdrm' to what you need, pivot on segment x quarter_end.")
