#!/usr/bin/env python3
"""
stack_ffiec002_csvs.py
================================================================================
PIECE 3 of 3: merge NIC per-filer FFIEC 002 CSVs into one master panel.

Each file you download from an institution's NIC page looks like this (confirmed
from TORONTO-DOMINION BK NY BR, RSSD 450810, 2026Q1):

    ItemName,Description,Value
    Institution Name,,TORONTO-DOMINION BK NY BR
    City,,NEW YORK
    ...
    ID_RSSD,Reporting entity identifier,450810
    RCFD2170,TOTAL ASSETS (BANK U.S.+FOREIGN OFC),86488534
    RCFDK479,TRADING ASSETS - U.S. TREASURY AND AGENCY SECURITIES,785384
    ...

Files are named FFIEC002_<rssd>_<yyyymmdd>.csv (e.g. FFIEC002_450810_20260331.csv),
so the RSSD and quarter come straight from the filename.

This produces:
  - ffiec002_master_long.csv : tidy long form, one row per (quarter, filer, MDRM).
        quarter_end, id_rssd, institution_name, mdrm, description, value
    Best for analysis/DB load; no column-count headaches.
  - ffiec002_master_wide.csv : one row per (quarter, filer), one column per MDRM.
    Handy in Excel. FFIEC 002 has well under Excel's 16,384-column limit.

Values are in THOUSANDS of U.S. dollars (per the report instructions).

RUN:
  1. pip install pandas
  2. Put your downloaded NIC CSVs in ./ffiec002_csvs/
     (drop in the one you already have to test the parser end-to-end now)
  3. python stack_ffiec002_csvs.py
================================================================================
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

IN_DIR = Path("./ffiec002_csvs")            # folder of downloaded NIC CSVs
OUT_LONG = Path("./ffiec002_master_long.csv")
OUT_WIDE = Path("./ffiec002_master_wide.csv")

# MDRM data codes: 4 letters + 4 alphanumerics, e.g. RCFD2170, RCFNK479, RCONF236.
MDRM_RE = re.compile(r"^[A-Z]{4}[A-Z0-9]{4}$")
# Pull rssd + period out of the filename.
FNAME_RE = re.compile(r"FFIEC002[_-](\d+)[_-](\d{8})", re.IGNORECASE)


def parse_one(fp: Path) -> pd.DataFrame:
    df = pd.read_csv(fp, dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    if not {"ItemName", "Value"} <= set(df.columns):
        print(f"  ! skipping {fp.name}: unexpected columns {list(df.columns)}")
        return pd.DataFrame()

    meta = dict(zip(df["ItemName"], df["Value"]))
    m = FNAME_RE.search(fp.name)
    rssd = m.group(1) if m else meta.get("ID_RSSD")
    period = m.group(2) if m else None
    quarter_end = (pd.to_datetime(period, format="%Y%m%d").date().isoformat()
                   if period else None)
    inst = meta.get("Institution Name", "")

    data = df[df["ItemName"].str.match(MDRM_RE)].copy()
    data = data.rename(columns={"ItemName": "mdrm",
                                "Description": "description",
                                "Value": "value"})
    data.insert(0, "quarter_end", quarter_end)
    data.insert(1, "id_rssd", rssd)
    data.insert(2, "institution_name", inst)
    return data[["quarter_end", "id_rssd", "institution_name",
                 "mdrm", "description", "value"]]


def main() -> None:
    files = sorted(IN_DIR.glob("*.csv"))
    if not files:
        sys.exit(f"No CSVs found in {IN_DIR}/ . Drop your NIC downloads there.")

    frames = []
    for fp in files:
        out = parse_one(fp)
        if not out.empty:
            frames.append(out)
    if not frames:
        sys.exit("No parseable files.")

    long = pd.concat(frames, ignore_index=True)
    long["value"] = pd.to_numeric(long["value"], errors="coerce")  # $ thousands
    long.to_csv(OUT_LONG, index=False)
    print(f"\nLONG : {len(long):,} rows from {len(files)} file(s) -> {OUT_LONG}")
    print(f"       {long['id_rssd'].nunique()} filer(s), "
          f"{long['quarter_end'].nunique()} quarter(s), "
          f"{long['mdrm'].nunique()} distinct MDRM codes")

    wide = (long.pivot_table(index=["quarter_end", "id_rssd", "institution_name"],
                             columns="mdrm", values="value", aggfunc="first")
                .reset_index())
    wide.to_csv(OUT_WIDE, index=False)
    print(f"WIDE : {wide.shape[0]:,} filer-quarter rows x {wide.shape[1]:,} cols "
          f"-> {OUT_WIDE}")

    # quick proof it worked: show total assets (RCFD2170) per filer-quarter
    if "RCFD2170" in wide.columns:
        print("\nTotal assets (RCFD2170, $ thousands):")
        print(wide[["quarter_end", "id_rssd", "RCFD2170"]].to_string(index=False))


if __name__ == "__main__":
    main()
