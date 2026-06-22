#!/usr/bin/env python3
"""
chicagofed_check.py
Decisive test: do the Chicago Fed free "Complete Files" (Call Report data,
2001-2010) include the FFIEC 002 FOREIGN BRANCHES (uninsured ones like TD's NY
branch, RSSD 450810)? WRDS sources its foreign-bank data from this Chicago Fed
pipeline, so they may be in here - which would be free pre-2020 data for the
uninsured majority.

Downloads one quarter, reads the SAS XPORT file(s), and checks whether our 002
filer RSSDs (and 450810 specifically) are present. Writes results to a file.

Setup:  pip install requests pandas
Run:    python chicagofed_check.py                 # default 2009Q4
        python chicagofed_check.py --zip call0912  # pick a quarter
"""
from __future__ import annotations
import argparse, csv, io, zipfile, os, tempfile
import requests
import pandas as pd

BASE = ("https://www.chicagofed.org/-/media/others/banking/"
        "financial-institution-reports/commercial-bank-data/{}-zip.zip")
PANEL = "ffiec002_filer_panel.csv"
OUT = "chicagofed_check_results.txt"
UA = {"User-Agent": "Mozilla/5.0 (research; chicagofed check)"}


def panel_rssds():
    s = set()
    with open(PANEL, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        col = next(c for c in rd.fieldnames if c.upper() == "ID_RSSD")
        for row in rd:
            v = (row[col] or "").strip()
            if v:
                s.add(v)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", default="call0912", help="e.g. call0912 = 2009Q4")
    a = ap.parse_args()
    url = BASE.format(a.zip)
    lines = []
    def w(s=""):
        print(s); lines.append(s)

    w(f"Downloading {url}")
    r = requests.get(url, headers=UA, timeout=300)
    w(f"  status={r.status_code} bytes={len(r.content):,}")
    if r.status_code != 200 or not r.content:
        w("  download failed."); open(OUT,"w").write("\n".join(lines)); return

    zf = zipfile.ZipFile(io.BytesIO(r.content))
    members = zf.namelist()
    w(f"  zip members: {members}")

    targets = panel_rssds()
    w(f"\nOur FFIEC 002 filers in panel: {len(targets)}")

    all_ids = set()
    id_cols_seen = {}
    td_rows = []
    for m in members:
        if not m.lower().endswith((".xpt", ".sas7bdat")):
            continue
        w(f"\n-- reading {m} --")
        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(m)[1], delete=False) as tmp:
            tmp.write(zf.read(m)); path = tmp.name
        try:
            df = pd.read_sas(path, format="xport" if m.lower().endswith(".xpt") else None)
        except Exception as e:
            w(f"   read error: {e}"); continue
        w(f"   rows={len(df):,} cols={len(df.columns)}")
        # find the RSSD id column (Chicago Fed uses RSSD9001)
        idcol = None
        for cand in ["RSSD9001", "RSSD9001 ", "IDRSSD", "ID_RSSD", "RSSD"]:
            if cand in df.columns:
                idcol = cand; break
        if not idcol:
            idcol = next((c for c in df.columns if "9001" in str(c) or "RSSD" in str(c).upper()), None)
        w(f"   id column: {idcol}")
        if not idcol:
            w(f"   (no RSSD column; sample cols: {list(df.columns)[:15]})")
            continue
        ids = set(str(int(x)) for x in df[idcol].dropna().tolist() if str(x).strip())
        id_cols_seen[m] = (idcol, len(ids))
        all_ids |= ids
        if "450810" in ids:
            sub = df[df[idcol].astype("Int64").astype(str) == "450810"]
            td_rows.append((m, sub))
        os.unlink(path)

    w(f"\n==== RESULT ====")
    w(f"  total distinct entities in file: {len(all_ids):,}")
    overlap = targets & all_ids
    w(f"  our 002 filers present in this Chicago Fed file: {len(overlap)} / {len(targets)}")
    w(f"  TD NY Branch 450810 present? {'YES' if '450810' in all_ids else 'NO'}")
    if overlap:
        w(f"  sample matched RSSDs: {sorted(list(overlap))[:20]}")
    for m, sub in td_rows:
        w(f"\n  TD 450810 row in {m}:")
        # print a few likely asset/name columns
        showcols = [c for c in sub.columns if any(k in str(c).upper()
                    for k in ("9001","2170","RSSD9017","NAME","ASSET"))][:12]
        for c in showcols:
            try:
                w(f"     {c} = {sub.iloc[0][c]}")
            except Exception:
                pass

    w("\nIf overlap is high / 450810=YES, the Chicago Fed free files carry the")
    w("uninsured branches too - I'll build the 2001-2010 puller across all quarters.")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n[written to {OUT}]")


if __name__ == "__main__":
    main()
