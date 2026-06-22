#!/usr/bin/env python3
"""
download_ffiec002_playwright.py  (real-Chrome edition)
================================================================================
Downloads every filer-quarter FFIEC 002 CSV from NIC, defeating its Akamai bot
wall by driving your REAL installed Google Chrome, headed, with a persistent
profile and automation flags hidden — the setup proved out by probe_ffiec002_v2.

  reads  : ffiec002_filer_panel.csv          (from build_ffiec002_panel.py)
  writes : ./ffiec002_csvs/FFIEC002_<rssd>_<yyyymmdd>.csv   (same naming as before)
  logs   : ffiec002_misses.csv               (id_rssd, dt) for quarters not filed

stack_ffiec002_csvs.py works unchanged afterward.

SETUP (already done if probe v2 ran):
  pip install playwright pandas
  playwright install chromium      # only needed for the --chromium fallback

RUN:
  python download_ffiec002_playwright.py --limit 20    # quick sanity test
  python download_ffiec002_playwright.py               # full pull (resumable)
  python stack_ffiec002_csvs.py

NOTES:
  * A visible Chrome window opens and stays open for the whole run — that's what
    keeps Akamai happy. Don't close it; you can keep working in other windows.
  * Resumable: stop anytime (Ctrl-C) and re-run; it skips files already saved.
  * Newest quarter first, so useful data lands immediately. Pre-coverage early
    quarters (NIC may not go back to 2001) simply log as "no filing".
  * If you don't have Google Chrome, add --chromium to use bundled Chromium
    (less reliable against Akamai, but try it).
================================================================================
"""
from __future__ import annotations
import argparse, random, sys, time
from pathlib import Path
import pandas as pd
from playwright.sync_api import sync_playwright

PANEL    = Path("./ffiec002_filer_panel.csv")
OUT_DIR  = Path("./ffiec002_csvs")
MISS_LOG = Path("./ffiec002_misses.csv")
PROFILE  = "./.pw_profile"
HOME     = "https://www.ffiec.gov/npw/"
SLEEP    = 0.4

FETCH_JS = """
async ([id, dt]) => {
  const url = `/npw/FinancialReport/ReturnFinancialReportCSV?rpt=FFIEC002&id=${id}&dt=${dt}`;
  try { const r = await fetch(url, {headers:{'Accept':'text/csv,application/csv,*/*'}});
        const t = await r.text(); return {status:r.status, body:t}; }
  catch (e) { return {status:-1, body:String(e)}; }
}
"""

def looks_like_report(text: str) -> bool:
    return text[:300].lstrip("﻿").lstrip().startswith("ItemName")

def warmup(pg):
    pg.goto(HOME, wait_until="networkidle", timeout=90000)
    pg.wait_for_timeout(6000)
    pg.mouse.move(300, 300); pg.mouse.move(700, 500)
    pg.wait_for_timeout(1500)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="stop after N attempts")
    ap.add_argument("--chromium", action="store_true", help="use bundled Chromium")
    args = ap.parse_args()

    if not PANEL.exists():
        sys.exit(f"Missing {PANEL}. Run build_ffiec002_panel.py first.")
    OUT_DIR.mkdir(exist_ok=True)

    panel = pd.read_csv(PANEL, dtype=str)
    pairs = (panel[["quarter_end", "ID_RSSD"]].dropna().drop_duplicates()
             .sort_values(["quarter_end", "ID_RSSD"], ascending=[False, True]))  # newest first
    total = len(pairs) if not args.limit else min(args.limit, len(pairs))
    print(f"{total:,} filer-quarter CSVs to fetch into {OUT_DIR}/"
          + (f"  (TEST: limited to {args.limit})" if args.limit else ""))

    got = skipped = missed = 0
    misses = []

    with sync_playwright() as p:
        kw = dict(user_data_dir=PROFILE, headless=False,
                  args=["--disable-blink-features=AutomationControlled",
                        "--disable-features=IsolateOrigins,site-per-process"],
                  viewport={"width": 1320, "height": 900})
        if not args.chromium:
            kw["channel"] = "chrome"
        try:
            ctx = p.chromium.launch_persistent_context(**kw)
        except Exception as e:
            sys.exit(f"Could not launch Chrome ({e}).\nTry: python download_ffiec002_playwright.py --chromium")
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        print("Warming up NIC session (clearing the bot check)...")
        warmup(pg)

        for i, (_, row) in enumerate(pairs.iterrows(), 1):
            if args.limit and i > args.limit:
                break
            rssd = str(row["ID_RSSD"]).strip()
            dt = str(row["quarter_end"]).replace("-", "")
            out = OUT_DIR / f"FFIEC002_{rssd}_{dt}.csv"
            if out.exists():
                skipped += 1
                continue

            text = None
            for attempt in range(1, 4):
                res = pg.evaluate(FETCH_JS, [rssd, dt])
                status, body = res.get("status"), res.get("body") or ""
                if status == 200 and looks_like_report(body):
                    text = body; break
                if status == 200:
                    break                              # filed nothing that quarter
                if status in (403, 429):
                    print(f"  HTTP {status} on {rssd} {dt} -- re-warming (attempt {attempt})")
                    pg.wait_for_timeout(int(1500 * attempt + random.random() * 800))
                    warmup(pg); continue
                break                                  # 404 etc.

            if text:
                out.write_text(text, encoding="utf-8"); got += 1
            else:
                missed += 1; misses.append({"id_rssd": rssd, "dt": dt})

            if i % 100 == 0:
                print(f"  {i:,}/{total:,}  got={got} skip={skipped} miss={missed}")
                if misses:                              # checkpoint the miss log
                    pd.DataFrame(misses).to_csv(MISS_LOG, index=False)
            time.sleep(SLEEP)

        ctx.close()

    if misses:
        pd.DataFrame(misses).to_csv(MISS_LOG, index=False)
    print(f"\nDone. downloaded={got}  already_had={skipped}  no_filing={missed}")
    if got:
        print("Next: python stack_ffiec002_csvs.py")

if __name__ == "__main__":
    main()
