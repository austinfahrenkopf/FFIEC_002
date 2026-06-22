#!/usr/bin/env python3
"""
build_ffiec002_overnight.py
=================================================================================
ONE overnight job -> a complete, analysis-ready FFIEC 002 panel, 1999 -> present.

SOURCES (all free):
  * Chicago Fed "Complete Files"  : 1999Q1 - 2021Q2, every branch/agency filer,
    standard RCFD/RCFN/RCON MDRM codes (requests; fully unattended).
  * NIC per-filer CSV (real Chrome): 2021Q3 - present (Akamai-guarded; opens a
    visible Chrome window - leave it open).

COMPLETENESS: filers are taken from each Chicago Fed file BY ENTITY TYPE
(IFB/ISB/UFB/USB/UFA/USA) unioned with your panel, so every institution that
actually filed 002 each quarter is captured - including ones long since closed.

OUTPUTS (in this folder):
  ffiec002_panel_long.parquet / .csv   tidy: quarter_end,id_rssd,institution_name,
                                       entity_type,mdrm,description,value,source
  ffiec002_panel_wide.parquet          one row per (quarter_end,id_rssd), MDRM cols
  ffiec002_filer_roster.csv            every filer, type, first/last quarter, in_panel
  ffiec002_mdrm_dictionary.csv         MDRM code -> description (from NIC labels)

RESUMABLE: re-run anytime; finished quarters/files are skipped.

SETUP (once):
  pip install requests pandas pyarrow playwright
  playwright install chromium      # only used by the NIC phase fallback
Requires Google Chrome installed for the NIC phase.

RUN:
  python build_ffiec002_overnight.py                 # everything, 1999->present
  python build_ffiec002_overnight.py --phase cf      # Chicago Fed only
  python build_ffiec002_overnight.py --phase nic     # NIC only
  python build_ffiec002_overnight.py --phase merge   # rebuild outputs from parts
  python build_ffiec002_overnight.py --cf-start 2001 # skip the 1999-2000 bonus
=================================================================================
"""
from __future__ import annotations
import argparse, csv, io, json, os, re, sys, tempfile, time, zipfile
import requests
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

PANEL       = "ffiec002_filer_panel.csv"
CF_BASE     = ("https://www.chicagofed.org/-/media/others/banking/"
               "financial-institution-reports/commercial-bank-data/{}-zip.zip")
CF_LONG     = "_cf_long.csv"           # intermediate (Chicago Fed)
CF_DONE     = "_cf_done.json"
NIC_DIR     = "ffiec002_csvs"          # per-filer NIC CSVs (reused/ resumable)
NIC_LONG    = "_nic_long.csv"          # intermediate (NIC)
OUT_LONG_PQ = "ffiec002_panel_long.parquet"
OUT_LONG_CSV= "ffiec002_panel_long.csv"
OUT_WIDE_PQ = "ffiec002_panel_wide.parquet"
ROSTER      = "ffiec002_filer_roster.csv"
DICT        = "ffiec002_mdrm_dictionary.csv"
LOG         = "build_overnight.log"

UA   = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) research"}
MDRM = re.compile(r"^[A-Z]{4}[A-Z0-9]{4}$")
FFIEC002_TYPES = {"IFB", "ISB", "UFB", "USB", "UFA", "USA"}

CF_LAST = "call2106"      # Chicago Fed last available quarter (2021Q2)
NIC_MIN_DT = "20210930"   # NIC handles 2021Q3 onward (after Chicago Fed ends)

_logf = open(LOG, "a", encoding="utf-8")
def log(s):
    line = f"[{time.strftime('%H:%M:%S')}] {s}"
    print(line); _logf.write(line + "\n"); _logf.flush()

def dec(x):
    return x.decode("latin-1").strip() if isinstance(x, bytes) else ("" if x is None else str(x).strip())

def panel_map():
    """rssd -> name from the current panel."""
    m = {}
    with open(PANEL, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        rcol = next(c for c in rd.fieldnames if c.upper() == "ID_RSSD")
        ncol = next((c for c in rd.fieldnames if c.upper() == "NM_LGL"), None)
        for row in rd:
            v = (row[rcol] or "").strip()
            if v:
                m[int(v)] = (row.get(ncol, "") or "").strip()
    return m

# --------------------------------------------------------------------------- #
# PHASE A : Chicago Fed 1999Q1 - 2021Q2
# --------------------------------------------------------------------------- #
def cf_quarters(start_year):
    out = []
    for y in range(start_year, 2022):
        yy = f"{y % 100:02d}"
        for mm, qend in (("03", f"{y}-03-31"), ("06", f"{y}-06-30"),
                         ("09", f"{y}-09-30"), ("12", f"{y}-12-31")):
            name = f"call{yy}{mm}"
            out.append((name, qend))
            if name == CF_LAST:
                return out
    return out

def phase_cf(start_year, panel):
    done = set(json.load(open(CF_DONE))) if os.path.exists(CF_DONE) else set()
    if not os.path.exists(CF_LONG):
        with open(CF_LONG, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["quarter_end","id_rssd","institution_name",
                                    "entity_type","mdrm","value"])
    qs = cf_quarters(start_year)
    log(f"PHASE CF: {len(qs)} quarters ({qs[0][0]}..{qs[-1][0]}), {len(done)} already done")
    for zipname, qend in qs:
        if zipname in done:
            continue
        url = CF_BASE.format(zipname)
        try:
            r = requests.get(url, headers=UA, timeout=900)
        except Exception as e:
            log(f"  {zipname} {qend}: download error {e}"); continue
        if r.status_code != 200 or len(r.content) < 1000:
            log(f"  {zipname} {qend}: HTTP {r.status_code} (skip)")
            done.add(zipname); json.dump(sorted(done), open(CF_DONE,"w")); continue
        try:
            zf = zipfile.ZipFile(io.BytesIO(r.content))
            xpt = [m for m in zf.namelist() if m.lower().endswith(".xpt")][0]
            with tempfile.NamedTemporaryFile(suffix=".xpt", delete=False) as t:
                t.write(zf.read(xpt)); path = t.name
            df = pd.read_sas(path, format="xport"); os.unlink(path)
        except Exception as e:
            log(f"  {zipname} {qend}: read error {e}"); continue

        idcol = "RSSD9001" if "RSSD9001" in df.columns else next((c for c in df.columns if "9001" in str(c)), None)
        if not idcol:
            log(f"  {zipname} {qend}: no id col (skip)")
            done.add(zipname); json.dump(sorted(done), open(CF_DONE,"w")); continue
        namecol = next((c for c in ("RSSD9017","RSSD9010") if c in df.columns), None)
        etcol   = next((c for c in ("RSSD9346","RSSD9331") if c in df.columns), None)
        df["_RSSD"] = df[idcol].astype("Int64")
        df["_ET"] = df[etcol].map(dec) if etcol else ""
        sel = (df["_ET"].isin(FFIEC002_TYPES) | df["_RSSD"].isin(panel)) if etcol else df["_RSSD"].isin(panel)
        sub = df[sel]
        if sub.empty:
            log(f"  {zipname} {qend}: 0 filers")
            done.add(zipname); json.dump(sorted(done), open(CF_DONE,"w")); continue
        mdrm_cols = [c for c in df.columns if MDRM.match(str(c))]
        rows = []
        for _, row in sub.iterrows():
            rssd = int(row["_RSSD"]); nm = dec(row[namecol]) if namecol else panel.get(rssd,"")
            et = row["_ET"]
            for c in mdrm_cols:
                v = row[c]
                if pd.isna(v): continue
                try: fv = float(v)
                except (TypeError, ValueError): continue
                if abs(fv) < 1e-70: continue          # SAS missing sentinel / zero
                rows.append((qend, rssd, nm, et, c, fv))
        with open(CF_LONG, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
        done.add(zipname); json.dump(sorted(done), open(CF_DONE,"w"))
        log(f"  {zipname} {qend}: filers={sub['_RSSD'].nunique()} rows+={len(rows):,}")
    log("PHASE CF complete.")

# --------------------------------------------------------------------------- #
# PHASE B : NIC per-filer CSV, 2021Q3 -> present (real Chrome)
# --------------------------------------------------------------------------- #
def phase_nic(panel):
    from playwright.sync_api import sync_playwright
    os.makedirs(NIC_DIR, exist_ok=True)
    p = pd.read_csv(PANEL, dtype=str)
    pairs = (p[["quarter_end","ID_RSSD"]].dropna().drop_duplicates())
    pairs = pairs[pairs["quarter_end"].str.replace("-","") >= NIC_MIN_DT]
    pairs = pairs.sort_values(["quarter_end","ID_RSSD"], ascending=[False, True])
    log(f"PHASE NIC: {len(pairs)} filer-quarters >= {NIC_MIN_DT}")

    FETCH = """
    async ([id,dt]) => { const u=`/npw/FinancialReport/ReturnFinancialReportCSV?rpt=FFIEC002&id=${id}&dt=${dt}`;
      try{const r=await fetch(u,{headers:{'Accept':'text/csv,*/*'}});const t=await r.text();
          return {s:r.status,b:t};}catch(e){return {s:-1,b:String(e)};} }"""
    def is_report(t): return t[:300].lstrip("﻿").lstrip().startswith("ItemName")

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir="./.pw_profile", channel="chrome", headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width":1320,"height":900})
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        def warm():
            pg.goto("https://www.ffiec.gov/npw/", wait_until="networkidle", timeout=90000)
            pg.wait_for_timeout(5000); pg.mouse.move(300,300); pg.mouse.move(700,500)
        warm()
        got = skip = miss = 0
        for i,(_,row) in enumerate(pairs.iterrows(),1):
            rssd = str(row["ID_RSSD"]).strip(); dt = str(row["quarter_end"]).replace("-","")
            out = os.path.join(NIC_DIR, f"FFIEC002_{rssd}_{dt}.csv")
            if os.path.exists(out): skip += 1; continue
            text = None
            for attempt in range(1,4):
                res = pg.evaluate(FETCH, [rssd, dt]); st = res.get("s"); b = res.get("b") or ""
                if st == 200 and is_report(b): text = b; break
                if st == 200: break
                if st in (403,429):
                    pg.wait_for_timeout(1500*attempt); warm(); continue
                break
            if text:
                open(out,"w",encoding="utf-8").write(text); got += 1
            else:
                miss += 1
            if i % 200 == 0: log(f"  NIC {i}/{len(pairs)} got={got} skip={skip} miss={miss}")
            time.sleep(0.35)
        ctx.close()
    log(f"PHASE NIC complete. got={got} skip={skip} miss={miss}")

def parse_nic_dir():
    """Parse all NIC CSVs in NIC_DIR -> NIC_LONG ; also return mdrm->desc map."""
    fn = re.compile(r"FFIEC002[_-](\d+)[_-](\d{8})", re.I)
    desc = {}
    with open(NIC_LONG, "w", newline="", encoding="utf-8") as out:
        w = csv.writer(out)
        w.writerow(["quarter_end","id_rssd","institution_name","entity_type","mdrm","value","description"])
        if not os.path.isdir(NIC_DIR):
            return desc
        for name in os.listdir(NIC_DIR):
            if not name.lower().endswith(".csv"): continue
            m = fn.search(name)
            if not m: continue
            rssd = m.group(1); qend = f"{m.group(2)[:4]}-{m.group(2)[4:6]}-{m.group(2)[6:]}"
            try:
                df = pd.read_csv(os.path.join(NIC_DIR,name), dtype=str, keep_default_na=False)
            except Exception:
                continue
            if not {"ItemName","Value"} <= set(df.columns): continue
            meta = dict(zip(df["ItemName"], df["Value"]))
            inst = meta.get("Institution Name","")
            for _, r in df.iterrows():
                code = str(r["ItemName"]).strip()
                if not MDRM.match(code): continue
                val = str(r.get("Value","")).strip().replace(",","")
                d = str(r.get("Description","")).strip()
                if d and code not in desc: desc[code] = d
                try: fv = float(val)
                except ValueError: continue
                w.writerow([qend, rssd, inst, "", code, fv, d])
    return desc

# --------------------------------------------------------------------------- #
# PHASE C : merge -> analysis-ready outputs
# --------------------------------------------------------------------------- #
def phase_merge(panel):
    log("PHASE MERGE: loading parts...")
    frames = []
    if os.path.exists(CF_LONG):
        cf = pd.read_csv(CF_LONG, dtype={"id_rssd":"int64"})
        cf["description"] = ""; cf["source"] = "ChicagoFed"
        frames.append(cf)
        log(f"  Chicago Fed rows: {len(cf):,}")
    desc = parse_nic_dir()
    if os.path.exists(NIC_LONG):
        nic = pd.read_csv(NIC_LONG, dtype={"id_rssd":"int64"})
        nic["source"] = "NIC"
        frames.append(nic)
        log(f"  NIC rows: {len(nic):,}")
    if not frames:
        log("  nothing to merge."); return
    long = pd.concat(frames, ignore_index=True)
    # fill descriptions from NIC labels
    if desc:
        long["description"] = long.apply(
            lambda r: r["description"] if r["description"] else desc.get(r["mdrm"],""), axis=1)
    # dedupe: prefer NIC on any (quarter,filer,mdrm) overlap
    long["_pri"] = (long["source"] == "NIC").astype(int)
    long = (long.sort_values("_pri")
                .drop_duplicates(["quarter_end","id_rssd","mdrm"], keep="last")
                .drop(columns="_pri"))
    long = long.sort_values(["quarter_end","id_rssd","mdrm"]).reset_index(drop=True)
    cols = ["quarter_end","id_rssd","institution_name","entity_type","mdrm","description","value","source"]
    long = long[cols]

    long.to_csv(OUT_LONG_CSV, index=False)
    try: long.to_parquet(OUT_LONG_PQ, index=False)
    except Exception as e: log(f"  (parquet long skipped: {e})")
    log(f"  LONG: {len(long):,} rows, {long['id_rssd'].nunique()} filers, "
        f"{long['quarter_end'].nunique()} quarters -> {OUT_LONG_CSV}")

    # wide
    try:
        wide = (long.pivot_table(index=["quarter_end","id_rssd","institution_name","entity_type"],
                                 columns="mdrm", values="value", aggfunc="first").reset_index())
        wide.to_parquet(OUT_WIDE_PQ, index=False)
        log(f"  WIDE: {wide.shape[0]:,} filer-quarters x {wide.shape[1]:,} cols -> {OUT_WIDE_PQ}")
    except Exception as e:
        log(f"  (wide skipped: {e})")

    # roster
    g = long.groupby("id_rssd")
    roster = pd.DataFrame({
        "institution_name": g["institution_name"].last(),
        "entity_type": g["entity_type"].agg(lambda s: next((x for x in s[::-1] if x), "")),
        "first_quarter": g["quarter_end"].min(),
        "last_quarter": g["quarter_end"].max(),
        "n_quarters": g["quarter_end"].nunique(),
    }).reset_index()
    roster["in_panel"] = roster["id_rssd"].isin(panel)
    roster.to_csv(ROSTER, index=False)
    log(f"  ROSTER: {len(roster)} filers -> {ROSTER}")

    if desc:
        pd.DataFrame(sorted(desc.items()), columns=["mdrm","description"]).to_csv(DICT, index=False)
        log(f"  DICT: {len(desc)} codes -> {DICT}")
    log("PHASE MERGE complete.")

# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["all","cf","nic","merge"], default="all")
    ap.add_argument("--cf-start", type=int, default=1999, help="Chicago Fed start year (1999 = bonus; 2001 = required)")
    a = ap.parse_args()
    panel = panel_map()
    log(f"=== build start: phase={a.phase} cf_start={a.cf_start} panel={len(panel)} ===")
    if a.phase in ("all","cf"):
        phase_cf(a.cf_start, set(panel))
    if a.phase in ("all","nic"):
        try: phase_nic(set(panel))
        except Exception as e: log(f"PHASE NIC error: {e} (continuing to merge)")
    if a.phase in ("all","nic","merge"):
        phase_merge(set(panel))
    log("=== build done ===")

if __name__ == "__main__":
    main()
