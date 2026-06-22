#!/usr/bin/env python3
"""
aggregate_extract.py
Builds a two-entity extract from the full panel:
  * TD_NYB        - Toronto-Dominion Bank, New York Branch (RSSD 450810)
  * ALL_BANKS_SUM - every FFIEC 002 filer that reported that quarter, summed per MDRM

For each (entity, quarter_end, mdrm): the value (TD's value, or the sum across all
filers), the MDRM description, the # of filers in the sum, and the source feed.

Outputs:
  ffiec002_tdnyb_vs_allbanks_long.csv   tidy (entity,quarter_end,mdrm,description,value,n_filers,source)
  ffiec002_tdnyb_vs_allbanks_wide.csv   one row per entity+quarter, one column per MDRM
  aggregate_report.txt                  total-assets sanity check

Setup:  pip install pandas pyarrow
Run:    python aggregate_extract.py
"""
from __future__ import annotations
import pandas as pd

SRC = "ffiec002_panel_long.parquet"
TD  = 450810
OUT_LONG = "ffiec002_tdnyb_vs_allbanks_long.csv"
OUT_WIDE = "ffiec002_tdnyb_vs_allbanks_wide.csv"
REPORT   = "aggregate_report.txt"

lines=[]
def w(s=""):
    print(s); lines.append(s)

w(f"reading {SRC} ...")
long = pd.read_parquet(SRC)
long["value"] = pd.to_numeric(long["value"], errors="coerce")
long = long.dropna(subset=["value"])
w(f"  rows: {len(long):,}  filers: {long['id_rssd'].nunique()}  quarters: {long['quarter_end'].nunique()}")

# --- TD NY Branch -----------------------------------------------------------
td = long[long["id_rssd"] == TD]
td_g = (td.groupby(["quarter_end","mdrm"], as_index=False)
          .agg(description=("description","first"),
               value=("value","first"),
               source=("source","first")))
td_g["entity"]="TD_NYB"; td_g["n_filers"]=1

# --- ALL banks, summed per MDRM per quarter ---------------------------------
allg = (long.groupby(["quarter_end","mdrm"], as_index=False)
            .agg(description=("description","first"),
                 value=("value","sum"),
                 n_filers=("id_rssd","nunique"),
                 source=("source","first")))
allg["entity"]="ALL_BANKS_SUM"

cols = ["entity","quarter_end","mdrm","description","value","n_filers","source"]
out = (pd.concat([td_g, allg], ignore_index=True)[cols]
         .sort_values(["entity","quarter_end","mdrm"]).reset_index(drop=True))
out.to_csv(OUT_LONG, index=False)
w(f"\nwrote {OUT_LONG}: {len(out):,} rows")

# wide: entity+quarter x MDRM
wide = (out.pivot_table(index=["entity","quarter_end"], columns="mdrm",
                        values="value", aggfunc="first").reset_index())
wide.to_csv(OUT_WIDE, index=False)
w(f"wrote {OUT_WIDE}: {wide.shape[0]:,} rows x {wide.shape[1]:,} cols")

# --- sanity: total assets RCFD2170 ------------------------------------------
ta = (out[out["mdrm"]=="RCFD2170"]
        .pivot_table(index="quarter_end", columns="entity", values="value"))
nf = (allg[allg["mdrm"]=="RCFD2170"].set_index("quarter_end")["n_filers"])
w("\nTotal assets RCFD2170 ($thousands) — sample quarters:")
w(f"  {'quarter':<12}{'TD_NYB':>16}{'ALL_BANKS_SUM':>18}{'banks':>8}{'TD share':>10}")
for q in list(ta.index)[::max(1,len(ta)//10)]:
    t = ta.loc[q].get("TD_NYB"); a = ta.loc[q].get("ALL_BANKS_SUM")
    n = int(nf.get(q,0)) if q in nf.index else 0
    share = f"{100*t/a:.1f}%" if (t and a) else ""
    w(f"  {q:<12}{(t or 0):>16,.0f}{(a or 0):>18,.0f}{n:>8}{share:>10}")

w("\nNOTE: ALL_BANKS_SUM includes TD. Dollar MDRM items (RCFD/RCON/RCFN balances)")
w("aggregate meaningfully; a few non-dollar items (counts, rates, indicators) are")
w("summed mechanically — use the dollar line items for economic totals.")
open(REPORT,"w",encoding="utf-8").write("\n".join(lines))
print(f"\n[written to {REPORT}]")
