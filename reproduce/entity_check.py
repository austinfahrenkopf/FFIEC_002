#!/usr/bin/env python3
"""
entity_check.py
Are there 002 filers in the Chicago Fed files that our panel (current NIC snapshot)
MISSES? Counts branch/agency filers BY ENTITY TYPE in the file itself (RSSD9346)
and compares to our 387-filer panel, listing any extras not in the panel.

Setup:  pip install requests pandas
Run:    python entity_check.py --zip call1512
        python entity_check.py --zip call0912
Output: entity_check_results.txt
"""
from __future__ import annotations
import argparse, csv, io, os, tempfile, zipfile
from collections import Counter
import requests, pandas as pd

BASE = ("https://www.chicagofed.org/-/media/others/banking/"
        "financial-institution-reports/commercial-bank-data/{}-zip.zip")
UA = {"User-Agent": "Mozilla/5.0 (research)"}
PANEL = "ffiec002_filer_panel.csv"
OUT = "entity_check_results.txt"
FFIEC002_TYPES = {"IFB", "ISB", "UFB", "USB", "UFA", "USA"}

ap = argparse.ArgumentParser()
ap.add_argument("--zip", default="call1512")
a = ap.parse_args()

lines = []
def w(s=""):
    print(s); lines.append(s)

# panel rssds + names
panel = {}
with open(PANEL, newline="", encoding="utf-8") as f:
    rd = csv.DictReader(f)
    rcol = next(c for c in rd.fieldnames if c.upper() == "ID_RSSD")
    ncol = next((c for c in rd.fieldnames if c.upper() == "NM_LGL"), None)
    for row in rd:
        v = (row[rcol] or "").strip()
        if v:
            panel[int(v)] = (row.get(ncol, "") or "").strip()

url = BASE.format(a.zip)
w(f"downloading {url}")
r = requests.get(url, headers=UA, timeout=300)
zf = zipfile.ZipFile(io.BytesIO(r.content))
xpt = [m for m in zf.namelist() if m.lower().endswith(".xpt")][0]
with tempfile.NamedTemporaryFile(suffix=".xpt", delete=False) as t:
    t.write(zf.read(xpt)); path = t.name
df = pd.read_sas(path, format="xport"); os.unlink(path)
w(f"file {a.zip}: rows={len(df):,} cols={len(df.columns)}")

idcol = "RSSD9001" if "RSSD9001" in df.columns else next(c for c in df.columns if "9001" in str(c))

# find entity-type column
etcol = None
for cand in ["RSSD9346", "RSSD9331", "RSSD9425", "RSSD9048"]:
    if cand in df.columns:
        # decode a sample to check it looks like type codes
        sample = df[cand].dropna().head(50).tolist()
        decoded = [x.decode("latin-1").strip() if isinstance(x, bytes) else str(x) for x in sample]
        if any(d in FFIEC002_TYPES or d in ("NMB","SMB","SNM","NAT") for d in decoded):
            etcol = cand; break
w(f"entity-type column: {etcol}")

if etcol:
    def dec(x):
        return x.decode("latin-1").strip() if isinstance(x, bytes) else str(x).strip()
    df["_ET"] = df[etcol].map(dec)
    w("\nentity-type counts (top 25):")
    for k, n in Counter(df["_ET"]).most_common(25):
        tag = "  <-- 002 filer" if k in FFIEC002_TYPES else ""
        w(f"   {k:8} {n}{tag}")

    in_file_002 = df[df["_ET"].isin(FFIEC002_TYPES)]
    file_rssds = set(int(x) for x in in_file_002[idcol].dropna())
    w(f"\n002-type filers in this file (by entity type): {len(file_rssds)}")
    overlap = file_rssds & set(panel)
    extras = file_rssds - set(panel)
    w(f"  also in our panel: {len(overlap)}")
    w(f"  NOT in our panel (we'd MISS these!): {len(extras)}")
    if extras:
        w("  sample missed filers:")
        nm = {int(row[idcol]): (row.get("RSSD9017") or row.get("RSSD9010"))
              for _, row in in_file_002.iterrows()}
        for rssd in sorted(extras)[:30]:
            n = nm.get(rssd, b"")
            n = n.decode("latin-1").strip() if isinstance(n, bytes) else str(n)
            w(f"     {rssd}  {n}")
else:
    w("no entity-type column found; can't measure completeness this way.")

open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print(f"\n[written to {OUT}]")
