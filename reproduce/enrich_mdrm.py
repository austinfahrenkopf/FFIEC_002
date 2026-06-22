#!/usr/bin/env python3
"""
enrich_mdrm.py
Fills in MDRM line-item TITLES for every code, using the Federal Reserve's
official MDRM dictionary (the NIC feed only labeled ~675 of ~1,159 codes).

 - downloads the Fed MDRM dictionary (MDRM.zip),
 - builds  Mnemonic+ItemCode -> Item Name  (e.g., RCFD+2170 -> TOTAL ASSETS),
 - rewrites the description column in ffiec002_panel_long.parquet,
 - rewrites ffiec002_mdrm_dictionary.csv with a label for every code in the panel,
 - reports how many codes are now labeled.

Setup:  pip install requests pandas pyarrow
Run:    python enrich_mdrm.py
After:  python make_site.py   (then re-upload BOTH site/index.html and site/ffiec002.parquet)
"""
from __future__ import annotations
import csv, io, zipfile
import requests, pandas as pd

URL = "https://www.federalreserve.gov/apps/mdrm/pdf/MDRM.zip"
SRC = "ffiec002_panel_long.parquet"
DICT = "ffiec002_mdrm_dictionary.csv"
UA = {"User-Agent": "Mozilla/5.0 (research; mdrm dictionary)"}

print("downloading Fed MDRM dictionary ...")
r = requests.get(URL, headers=UA, timeout=120); r.raise_for_status()
zf = zipfile.ZipFile(io.BytesIO(r.content))
member = max((m for m in zf.namelist() if m.lower().endswith(".csv")),
             key=lambda m: zf.getinfo(m).file_size)
print(f"  reading {member}")
text = zf.read(member).decode("latin-1", errors="replace")

rows = list(csv.reader(io.StringIO(text)))
# find the header row (contains 'Mnemonic')
hdr_i = next(i for i,row in enumerate(rows) if any(c.strip().lower()=="mnemonic" for c in row))
hdr = [c.strip() for c in rows[hdr_i]]
def col(*names):
    for n in names:
        for i,h in enumerate(hdr):
            if h.lower()==n.lower(): return i
    for n in names:
        for i,h in enumerate(hdr):
            if n.lower() in h.lower(): return i
    raise KeyError(names)
ci_mn = col("Mnemonic")
ci_ic = col("Item Code","ItemCode","Item")
ci_nm = col("Item Name","ItemName","Name")

mp = {}
for row in rows[hdr_i+1:]:
    if len(row) <= max(ci_mn,ci_ic,ci_nm): continue
    code = (row[ci_mn].strip()+row[ci_ic].strip()).upper()
    name = row[ci_nm].strip()
    if len(code)==8 and name:
        mp.setdefault(code, name)
print(f"  MDRM names loaded: {len(mp):,}")

print(f"reading {SRC} ...")
df = pd.read_parquet(SRC)
df["mdrm"] = df["mdrm"].astype(str).str.upper()
have_before = (df["description"].fillna("")!="").mean()
df["description"] = df["mdrm"].map(mp).fillna(df["description"]).fillna("")
have_after = (df["description"]!="").mean()
df.to_parquet(SRC, index=False)
print(f"  rows labeled: {have_before:.0%} -> {have_after:.0%}")

codes = sorted(df["mdrm"].unique())
labeled = sum(1 for c in codes if mp.get(c) or (df.loc[df.mdrm==c,"description"].iloc[0]))
pd.DataFrame([(c, mp.get(c, "")) for c in codes],
             columns=["mdrm","description"]).to_csv(DICT, index=False)
print(f"  panel codes: {len(codes)}, with a title: {labeled}")
print(f"  wrote {DICT}")
print("\nNext: python make_site.py  -> re-upload site/index.html AND site/ffiec002.parquet")
