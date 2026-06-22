#!/usr/bin/env python3
"""
check_schedule_n.py
Does the Chicago Fed call extract carry FFIEC 002 Schedule N (Past Due, Nonaccrual,
and Restructured)? Dumps EVERY non-null MDRM item for one filer (default TD 450810)
from one quarter, so we can see exactly which schedules survived.

Setup:  pip install requests pandas
Run:    python check_schedule_n.py            # TD 450810, 2009Q4
        python check_schedule_n.py --rssd 450810 --zip call0912
Output: schedule_n_check.txt
"""
from __future__ import annotations
import argparse, io, os, re, tempfile, zipfile
import requests, pandas as pd

BASE = ("https://www.chicagofed.org/-/media/others/banking/"
        "financial-institution-reports/commercial-bank-data/{}-zip.zip")
UA = {"User-Agent": "Mozilla/5.0 (research)"}
OUT = "schedule_n_check.txt"
MDRM = re.compile(r"^[A-Z]{4}[A-Z0-9]{4}$")

# FFIEC 002 Schedule N is "Past Due, Nonaccrual, and Restructured". Past-due /
# nonaccrual item NUMBERS (last 4 of the MDRM) commonly used across RC-N/Sched N:
PASTDUE_NUMS = {"1606","1607","1403","1407","5398","5399","5400","5459","5460",
                "1226","1227","1228","3493","3494","3495","5524","5525","5526",
                "1257","1258","1259","3505","3506","3507","b834","b835","b836"}

ap = argparse.ArgumentParser()
ap.add_argument("--rssd", default="450810")
ap.add_argument("--zip", default="call0912")
a = ap.parse_args()
rssd = int(a.rssd)

lines = []
def w(s=""):
    print(s); lines.append(s)

url = BASE.format(a.zip)
w(f"downloading {url}")
r = requests.get(url, headers=UA, timeout=300)
zf = zipfile.ZipFile(io.BytesIO(r.content))
xpt = [m for m in zf.namelist() if m.lower().endswith(".xpt")][0]
with tempfile.NamedTemporaryFile(suffix=".xpt", delete=False) as t:
    t.write(zf.read(xpt)); path = t.name
df = pd.read_sas(path, format="xport"); os.unlink(path)

idcol = "RSSD9001" if "RSSD9001" in df.columns else next(c for c in df.columns if "9001" in str(c))
row = df[df[idcol] == rssd]
if row.empty:
    w(f"RSSD {rssd} not in {a.zip}"); open(OUT,"w").write("\n".join(lines)); raise SystemExit
row = row.iloc[0]

mdrm_cols = [c for c in df.columns if MDRM.match(str(c))]
nonnull = [(c, row[c]) for c in mdrm_cols if pd.notna(row[c])]
w(f"\nRSSD {rssd}  quarter file {a.zip}")
w(f"total MDRM columns in file: {len(mdrm_cols)}")
w(f"non-null MDRM items for this filer: {len(nonnull)}")

# flag likely Schedule N / past-due items
sched_n = [(c, v) for c, v in nonnull if str(c)[-4:].lower() in PASTDUE_NUMS]
w(f"\n==== LIKELY SCHEDULE N / PAST-DUE items present ({len(sched_n)}): ====")
for c, v in sorted(sched_n):
    w(f"   {c} = {v}")
if not sched_n:
    w("   none matched the past-due code set (may use other codes - see full dump)")

w(f"\n==== ALL non-null MDRM items (code = value) ====")
for c, v in sorted(nonnull, key=lambda x: str(x[0])):
    w(f"   {c} = {v}")

open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print(f"\n[written to {OUT}]")
