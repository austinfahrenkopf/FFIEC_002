#!/usr/bin/env python3
"""
finalize_outputs.py
Repairs/【finishes the overnight build WITHOUT re-downloading:
  * reads ffiec002_panel_long.csv (already produced),
  * cleans the entity_type column (re-derived from your panel; blanks numeric junk),
  * writes ffiec002_panel_long.parquet and ffiec002_panel_wide.parquet,
  * reports true filer/quarter counts and any filers beyond the original 387 panel,
  * quick TD 450810 total-assets sanity check across a few quarters.

Setup:  pip install pandas pyarrow
Run:    python finalize_outputs.py
Output: parquet files + finalize_report.txt
"""
from __future__ import annotations
import csv
import pandas as pd

LONG_CSV = "ffiec002_panel_long.csv"
PANEL    = "ffiec002_filer_panel.csv"
OUT_LONG_PQ = "ffiec002_panel_long.parquet"
OUT_WIDE_PQ = "ffiec002_panel_wide.parquet"
ROSTER   = "ffiec002_filer_roster.csv"
REPORT   = "finalize_report.txt"
FFIEC002_TYPES = {"IFB","ISB","UFB","USB","UFA","USA"}

lines = []
def w(s=""):
    print(s); lines.append(s)

# panel rssd -> entity_type / name
panel_et, panel_nm = {}, {}
with open(PANEL, newline="", encoding="utf-8") as f:
    rd = csv.DictReader(f)
    rcol = next(c for c in rd.fieldnames if c.upper()=="ID_RSSD")
    ecol = next((c for c in rd.fieldnames if c.upper()=="ENTITY_TYPE"), None)
    ncol = next((c for c in rd.fieldnames if c.upper()=="NM_LGL"), None)
    for row in rd:
        v=(row[rcol] or "").strip()
        if v:
            panel_et[int(v)] = (row.get(ecol,"") or "").strip()
            panel_nm[int(v)] = (row.get(ncol,"") or "").strip()
panel_set = set(panel_et)

w(f"reading {LONG_CSV} ...")
long = pd.read_csv(LONG_CSV, dtype=str, low_memory=False)
w(f"  raw rows: {len(long):,}")

long["id_rssd"] = pd.to_numeric(long["id_rssd"], errors="coerce").astype("Int64")
long = long.dropna(subset=["id_rssd"])
long["id_rssd"] = long["id_rssd"].astype("int64")
long["value"] = pd.to_numeric(long["value"], errors="coerce")
long = long.dropna(subset=["value"])

# clean entity_type: panel value first; else keep in-file only if a valid 002 type
infile = long["entity_type"].where(long["entity_type"].isin(FFIEC002_TYPES), "")
long["entity_type"] = long["id_rssd"].map(panel_et).fillna(infile).fillna("")
for c in ("quarter_end","institution_name","entity_type","mdrm","description","source"):
    if c in long.columns:
        long[c] = long[c].fillna("").astype(str)

cols = ["quarter_end","id_rssd","institution_name","entity_type","mdrm","description","value","source"]
long = long[[c for c in cols if c in long.columns]]

# write parquet long
try:
    long.to_parquet(OUT_LONG_PQ, index=False)
    w(f"  wrote {OUT_LONG_PQ}")
except Exception as e:
    w(f"  parquet long FAILED: {e}")

# wide
try:
    wide = (long.pivot_table(index=["quarter_end","id_rssd","institution_name","entity_type"],
                             columns="mdrm", values="value", aggfunc="first").reset_index())
    wide.to_parquet(OUT_WIDE_PQ, index=False)
    w(f"  wrote {OUT_WIDE_PQ}: {wide.shape[0]:,} filer-quarters x {wide.shape[1]:,} cols")
except Exception as e:
    w(f"  wide FAILED: {e}")

# integrity report
filers = set(long["id_rssd"].unique())
extra = sorted(filers - panel_set)
qs = sorted(long["quarter_end"].unique())
w("\n==== INTEGRITY ====")
w(f"  rows: {len(long):,}")
w(f"  distinct filers: {len(filers)}   (panel had {len(panel_set)})")
w(f"  filers BEYOND the original panel (historical/closed captured): {len(extra)}")
for r in extra[:40]:
    nm = long[long['id_rssd']==r]['institution_name'].iloc[0]
    w(f"     {r}  {nm}")
w(f"  quarters: {len(qs)}  range {qs[0]} .. {qs[-1]}")
w(f"  source mix: {long['source'].value_counts().to_dict()}")

# TD sanity
td = long[(long['id_rssd']==450810) & (long['mdrm']=='RCFD2170')].sort_values('quarter_end')
w("\n  TD NY Branch (450810) total assets RCFD2170, sample quarters:")
for _,r in td.iloc[::max(1,len(td)//8)].iterrows():
    w(f"     {r['quarter_end']}  {r['value']:,.0f}  [{r['source']}]")

# refresh roster from full data
g = long.groupby("id_rssd")
roster = pd.DataFrame({
    "institution_name": g["institution_name"].last(),
    "entity_type": g["entity_type"].agg(lambda s: next((x for x in s[::-1] if x), "")),
    "first_quarter": g["quarter_end"].min(),
    "last_quarter": g["quarter_end"].max(),
    "n_quarters": g["quarter_end"].nunique(),
}).reset_index()
roster["in_panel"] = roster["id_rssd"].isin(panel_set)
roster.to_csv(ROSTER, index=False)
w(f"\n  roster refreshed -> {ROSTER} ({len(roster)} filers)")

open(REPORT,"w",encoding="utf-8").write("\n".join(lines))
print(f"\n[written to {REPORT}]")
