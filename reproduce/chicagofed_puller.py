#!/usr/bin/env python3
"""
chicagofed_puller.py  (entity-type complete edition)
Pulls FFIEC 002 foreign branch/agency financials from the Chicago Fed free
"Complete Files" (which carry 002 in standard RCFD/RCFN/RCON MDRM codes).

COMPLETENESS: instead of trusting the current NIC panel, it selects EVERY
branch/agency filer present in each quarterly file by its own entity-type code
(RSSD9346 in IFB/ISB/UFB/USB/UFA/USA), unioned with your panel. So it captures
all institutions that actually filed 002 in each historical quarter - including
ones that have since closed and dropped off today's NIC roster.

Coverage: the Chicago Fed hosts callYYMM-zip.zip for 2001-2021Q2 (2011+ are live
but unlinked). Output matches your NIC stack:
    quarter_end, id_rssd, institution_name, mdrm, description, value
Plus a roster of every filer found: chicagofed_filer_roster.csv

Setup:  pip install requests pandas
Run:    python chicagofed_puller.py                 # 2001-2021
        python chicagofed_puller.py --years 2011,2012,2013,2014,2015,2016,2017,2018,2019
Output: ffiec002_chicagofed_long.csv , chicagofed_filer_roster.csv , chicagofed_puller.log
"""
from __future__ import annotations
import argparse, csv, io, os, re, tempfile, zipfile
import requests
import pandas as pd

BASE = ("https://www.chicagofed.org/-/media/others/banking/"
        "financial-institution-reports/commercial-bank-data/{}-zip.zip")
PANEL = "ffiec002_filer_panel.csv"
OUT = "ffiec002_chicagofed_long.csv"
ROSTER = "chicagofed_filer_roster.csv"
LOG = "chicagofed_puller.log"
UA = {"User-Agent": "Mozilla/5.0 (research; chicagofed puller)"}
MDRM = re.compile(r"^[A-Z]{4}[A-Z0-9]{4}$")
FFIEC002_TYPES = {"IFB", "ISB", "UFB", "USB", "UFA", "USA"}


def panel_rssds():
    s = set()
    with open(PANEL, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        col = next(c for c in rd.fieldnames if c.upper() == "ID_RSSD")
        for row in rd:
            v = (row[col] or "").strip()
            if v:
                s.add(int(v))
    return s


def quarters(years):
    out = []
    for y in years:
        yy = f"{y % 100:02d}"
        for mm, qend in (("03", f"{y}-03-31"), ("06", f"{y}-06-30"),
                         ("09", f"{y}-09-30"), ("12", f"{y}-12-31")):
            out.append((f"call{yy}{mm}", qend))
    return out


def dec(x):
    return x.decode("latin-1").strip() if isinstance(x, bytes) else (
        "" if x is None else str(x).strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default=",".join(str(y) for y in range(2001, 2022)))
    a = ap.parse_args()
    years = [int(x) for x in a.years.split(",")]
    panel = panel_rssds()

    logf = open(LOG, "w", encoding="utf-8")
    def log(s):
        print(s); logf.write(s + "\n"); logf.flush()

    log(f"panel filers: {len(panel)}   quarters to try: {len(quarters(years))}")
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(["quarter_end", "id_rssd", "institution_name",
                                "mdrm", "description", "value"])
    roster = {}   # rssd -> (name, entity_type, first_q, last_q, n_quarters)
    grand = 0

    for zipname, qend in quarters(years):
        url = BASE.format(zipname)
        try:
            r = requests.get(url, headers=UA, timeout=600)
        except Exception as e:
            log(f"  {zipname} {qend}: download error {e}"); continue
        if r.status_code != 200 or not r.content or len(r.content) < 1000:
            log(f"  {zipname} {qend}: HTTP {r.status_code} / empty (skip)"); continue
        try:
            zf = zipfile.ZipFile(io.BytesIO(r.content))
            xpt = [m for m in zf.namelist() if m.lower().endswith(".xpt")][0]
            with tempfile.NamedTemporaryFile(suffix=".xpt", delete=False) as tmp:
                tmp.write(zf.read(xpt)); path = tmp.name
            df = pd.read_sas(path, format="xport")
            os.unlink(path)
        except Exception as e:
            log(f"  {zipname} {qend}: read error {e}"); continue

        idcol = "RSSD9001" if "RSSD9001" in df.columns else next(
            (c for c in df.columns if "9001" in str(c)), None)
        if not idcol:
            log(f"  {zipname} {qend}: no id column (skip)"); continue
        namecol = next((c for c in ("RSSD9017", "RSSD9010") if c in df.columns), None)
        etcol = next((c for c in ("RSSD9346", "RSSD9331") if c in df.columns), None)

        df["_RSSD"] = df[idcol].astype("Int64")
        if etcol:
            df["_ET"] = df[etcol].map(dec)
            sel = df["_ET"].isin(FFIEC002_TYPES) | df["_RSSD"].isin(panel)
        else:
            df["_ET"] = ""
            sel = df["_RSSD"].isin(panel)
        sub = df[sel].copy()
        if sub.empty:
            log(f"  {zipname} {qend}: 0 filers"); continue

        n_by_type = int(df["_ET"].isin(FFIEC002_TYPES).sum()) if etcol else 0
        extras = int((df["_ET"].isin(FFIEC002_TYPES) & ~df["_RSSD"].isin(panel)).sum()) if etcol else 0

        mdrm_cols = [c for c in df.columns if MDRM.match(str(c))]
        rows_out = []
        for _, row in sub.iterrows():
            rssd = int(row["_RSSD"]); nm = dec(row[namecol]) if namecol else ""
            et = row["_ET"]
            # roster bookkeeping
            if rssd not in roster:
                roster[rssd] = [nm, et, qend, qend, 0]
            roster[rssd][0] = nm or roster[rssd][0]
            roster[rssd][1] = et or roster[rssd][1]
            roster[rssd][3] = qend
            roster[rssd][4] += 1
            for c in mdrm_cols:
                v = row[c]
                if pd.isna(v):
                    continue
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                if abs(fv) < 1e-70:        # SAS/XPORT missing sentinel (and 0)
                    continue
                rows_out.append((qend, rssd, nm, c, "", fv))
        with open(OUT, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows_out)
        grand += len(rows_out)
        log(f"  {zipname} {qend}: filers={sub['_RSSD'].nunique()} "
            f"(002-type={n_by_type}, extras-not-in-panel={extras}) "
            f"rows+={len(rows_out):,} total={grand:,}")

    # write roster
    with open(ROSTER, "w", newline="", encoding="utf-8") as f:
        wcsv = csv.writer(f)
        wcsv.writerow(["id_rssd", "institution_name", "entity_type",
                       "first_quarter", "last_quarter", "n_quarters", "in_panel"])
        for rssd in sorted(roster):
            nm, et, fq, lq, nq = roster[rssd]
            wcsv.writerow([rssd, nm, et, fq, lq, nq, rssd in panel])

    log(f"\nDONE. {grand:,} value rows -> {OUT}")
    log(f"distinct filers captured: {len(roster)}  (panel had {len(panel)})")
    log(f"roster -> {ROSTER}")
    log("Next: concat with ffiec002_master_long.csv (NIC 2020Q4+) = full panel.")
    logf.close()


if __name__ == "__main__":
    main()
