#!/usr/bin/env python3
"""
build_ffiec002_panel.py
================================================================================
PART 1 of your FFIEC 002 repository: the FILER PANEL.

This produces the authoritative list of "FBOs that file the FFIEC 002" -- every
U.S. branch and agency of a foreign bank -- per quarter, with their RSSD IDs,
names, locations, insurance status, and active date windows. That panel is the
backbone: every financial pull in Part 2 loops over these RSSD x quarter pairs.

This part is 100% free, public, and genuinely turnkey. It runs against NIC's
Bulk Data Download (structure data), which is a plain CSV with no login and no
bot wall. Confirmed against the NIC "BULK DATA DOWNLOAD DATA DICTIONARY" (v2.0).

------------------------------------------------------------------------------
HOW TO RUN (about 2 minutes):
  1. pip install pandas
  2. Go to NIC's Bulk Data Download page:
        https://www.ffiec.gov/npw/FinancialReport/DataDownload
     Download these three "Attributes" files (CSV option):
        - Active   -> CSV_ATTRIBUTES_ACTIVE.CSV
        - Closed   -> CSV_ATTRIBUTES_CLOSED.CSV
        - Branches -> CSV_ATTRIBUTES_BRANCHES.CSV
     (They arrive zipped; unzip into ./nic_data/. The download links carry an
      as-of date, which is why you grab them fresh rather than me hard-coding a
      URL that rots.)
  3. python build_ffiec002_panel.py
     -> writes ffiec002_filer_panel.csv  (one row per filer per quarter)
     -> prints filer counts per quarter for a sanity check
------------------------------------------------------------------------------

WHY THIS IS THE RIGHT FILTER (not a guess):
The FFIEC 002 reporting panel is "all U.S. branches and agencies of foreign
banks." In NIC's ENTITY_TYPE field those are exactly:
    IFB = Insured Federal Branch of an FBO
    ISB = Insured State   Branch of an FBO
    UFB = Uninsured Federal Branch of an FBO
    USB = Uninsured State  Branch of an FBO
    UFA = Uninsured Federal Agency of an FBO
    USA = Uninsured State   Agency of an FBO
We deliberately EXCLUDE:
    FBK (the parent foreign bank), FBO/FBH (the foreign holding org),
    REP (representative office -- files nothing), and
    TWG/PST (non-U.S. branches managed by a U.S. branch -- those file the
             FFIEC 002S supplement, whose microdata is CONFIDENTIAL).
================================================================================
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
OUT = Path("./ffiec002_filer_panel.csv")
START = dt.date(2001, 6, 30)           # first in-scope FFIEC 002 quarter
END = dt.date.today()

# The six NIC entity types that ARE the FFIEC 002 reporting panel.
FFIEC002_ENTITY_TYPES = {"IFB", "ISB", "UFB", "USB", "UFA", "USA"}

# We auto-find the three NIC "Attributes" CSVs (Active / Closed / Branches)
# wherever they are — current folder or any subfolder — regardless of exact
# filename, as long as the name contains "ATTRIBUTES". So it doesn't matter that
# yours are in "...\Desktop\Claude\FFIEC 002" instead of a ./nic_data/ folder.
SEARCH_DIRS = [Path(".")]              # searched recursively below

# Columns we keep (all exist in the NIC Attributes table per the data dictionary).
KEEP = [
    "ID_RSSD", "NM_LGL", "NM_SHORT", "ENTITY_TYPE", "EST_TYPE_CD",
    "CITY", "STATE_ABBR_NM", "ZIP_CD",
    "CNTRY_INC_NM",          # home country of the parent foreign bank
    "ID_RSSD_HD_OFF",        # RSSD of the (foreign) head office
    "INSUR_PRI_CD",          # insurance status
    "DT_OPEN", "DT_END", "DT_EXIST_CMNC", "DT_EXIST_TERM",
]


def quarter_ends(start: dt.date, end: dt.date) -> list[dt.date]:
    out = []
    for y in range(start.year, end.year + 1):
        for m, d in ((3, 31), (6, 30), (9, 30), (12, 31)):
            qe = dt.date(y, m, d)
            if start <= qe <= end:
                out.append(qe)
    return out


def find_attribute_files() -> list[Path]:
    """Find the NIC Attributes CSVs anywhere under the current folder.
    Matches any CSV whose name contains 'ATTRIBUTES' (Active/Closed/Branches),
    so exact filenames and folder layout don't matter."""
    found = []
    for base in SEARCH_DIRS:
        for fp in base.rglob("*.csv"):
            if "ATTRIBUTES" in fp.name.upper():
                found.append(fp)
    # de-dup while preserving order
    seen, uniq = set(), []
    for fp in found:
        if fp.resolve() not in seen:
            seen.add(fp.resolve())
            uniq.append(fp)
    return uniq


def load_attributes() -> pd.DataFrame:
    files = find_attribute_files()
    if not files:
        all_csvs = [str(p) for b in SEARCH_DIRS for p in b.rglob("*.csv")]
        raise FileNotFoundError(
            "Could not find the NIC Attributes CSVs (filenames containing "
            "'ATTRIBUTES'). Put the three files (Active / Closed / Branches) "
            "from https://www.ffiec.gov/npw/FinancialReport/DataDownload in this "
            "folder or a subfolder.\nCSVs I did see here: "
            + (", ".join(all_csvs) if all_csvs else "(none)")
        )
    print(f"Using {len(files)} NIC attribute file(s):")
    for fp in files:
        print(f"  - {fp}")
    frames = []
    for fp in files:
        df = pd.read_csv(fp, dtype=str, low_memory=False)
        df.columns = [c.strip().upper() for c in df.columns]
        frames.append(df)
    attrs = pd.concat(frames, ignore_index=True)
    cols = [c for c in KEEP if c in attrs.columns]
    return attrs[cols].copy()


def to_int_date(s: pd.Series) -> pd.Series:
    """NIC dates are YYYYMMDD ints; 99991231 means 'still open'."""
    d = pd.to_datetime(s, format="%Y%m%d", errors="coerce")
    return d


def build_panel() -> pd.DataFrame:
    attrs = load_attributes()

    # 1) Restrict to the FFIEC 002 reporting population.
    panel = attrs[attrs["ENTITY_TYPE"].isin(FFIEC002_ENTITY_TYPES)].copy()
    if panel.empty:
        raise RuntimeError(
            "No FFIEC 002 entities matched. Check that ENTITY_TYPE values in your "
            "files look like 'IFB','USB',... (run panel['ENTITY_TYPE'].value_counts())."
        )

    # 2) Existence window for each entity (prefer open/close; fall back to exist).
    open_dt = to_int_date(panel.get("DT_OPEN")).fillna(
              to_int_date(panel.get("DT_EXIST_CMNC")))
    end_raw = panel.get("DT_END")
    end_dt = to_int_date(end_raw)
    # 99991231 / NaT -> treat as open through END
    still_open = end_raw.isna() | (end_raw.astype(str).str.startswith("9999"))
    end_dt = end_dt.where(~still_open, pd.Timestamp(END))

    panel = panel.assign(_open=open_dt, _end=end_dt)

    # 3) Cross with quarters: a filer is "in panel" for quarter Q if it existed
    #    on the quarter-end date.
    rows = []
    qends = [pd.Timestamp(q) for q in quarter_ends(START, END)]
    for q in qends:
        live = panel[(panel["_open"].isna() | (panel["_open"] <= q)) &
                     (panel["_end"].isna() | (panel["_end"] >= q))].copy()
        live.insert(0, "quarter_end", q.date().isoformat())
        rows.append(live)

    out = pd.concat(rows, ignore_index=True).drop(columns=["_open", "_end"])
    out = out.sort_values(["quarter_end", "ID_RSSD"]).reset_index(drop=True)
    return out


def main() -> None:
    panel = build_panel()
    panel.to_csv(OUT, index=False)

    print(f"\nWrote {len(panel):,} filer-quarter rows -> {OUT}")
    print(f"Unique filers overall: {panel['ID_RSSD'].nunique():,}")
    print("\nFilers per quarter (recent) -- sanity-check these against the Fed's "
          "quarterly 'Structure and Share Data for U.S. Offices of Foreign "
          "Banking Organizations' release:")
    counts = panel.groupby("quarter_end")["ID_RSSD"].nunique()
    print(counts.tail(12).to_string())
    print("\nEntity-type mix:")
    print(panel["ENTITY_TYPE"].value_counts().to_string())


if __name__ == "__main__":
    main()
