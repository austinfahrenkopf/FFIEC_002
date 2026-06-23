#!/usr/bin/env python3
"""
make_site_002.py  (v3 engine for FFIEC 002 — branches & agencies of foreign banks)
Mirrors the Call Report explorer: dark mode, Items+Entities tabbed rail, collapsible
hierarchy tree, draggable pop-out, multi-measure aligned $/% panes, range slider,
peer groups, and a drill-down/time-frame call-report view.

Data: queries ffiec002_panel_long.parquet directly (small enough for the browser).
Entity types come from the roster (embedded), not the panel's noisy entity_type column.
COMB = coalesce(RCFD, RCON) per filer (RCFD = Total Reporting Branch incl. IBF).

Run:  python build_hierarchy_002.py  ->  python make_site_002.py
Then upload site_002/ (index.html + ffiec002.parquet + ffiec002_hierarchy.json).
"""
import os, sys, shutil, csv, json
from datetime import datetime
import pandas as pd
BUILD_TS = datetime.now().strftime('%Y-%m-%d %H:%M')
SRC="ffiec002_panel_long.parquet"; SITE="site_002"; MAXBYTES=95*1024*1024
CREDIT_URL="https://github.com/austinfahrenkopf"   # <-- your GitHub profile (or set a specific repo URL)
# --html-only: regenerate just index.html from the EXISTING site parquet(s) — fast iteration on
# the dashboard UI without re-copying/re-splitting the panel. Use after editing the template.
HTML_ONLY="--html-only" in sys.argv
os.makedirs(SITE, exist_ok=True)
if HTML_ONLY:
    PARTS=sorted(f for f in os.listdir(SITE) if f.endswith(".parquet"))
    if not PARTS: raise SystemExit("--html-only: no site parquet in "+SITE+" yet; run a full build first.")
    print("[--html-only] reusing", PARTS)
    # no-data codes: in hierarchy but absent from all site parquets
    _hj2=json.load(open("ffiec002_hierarchy.json",encoding="utf-8")) if os.path.exists("ffiec002_hierarchy.json") else {}
    _dc2=set();[_dc2.add(_it.get("mdrm")) for _its in _hj2.values() for _it in _its];_dc2.discard(None)
    _spq=pd.concat([pd.read_parquet(os.path.join(SITE,p),columns=["mdrm"]) for p in PARTS],ignore_index=True) if PARTS else pd.DataFrame(columns=["mdrm"])
    NODATA_CODES=sorted(c for c in _dc2 if c and c not in set(_spq["mdrm"].unique()))
else:
    for f in os.listdir(SITE):
        if f.endswith(".parquet"): os.remove(os.path.join(SITE,f))
    df=pd.read_parquet(SRC)
    # MED-3: filter to DISPLAY_CODES only — ship codes the dashboard actually surfaces.
    # Source parquet is the full panel; browser only needs hierarchy tree + DERIV + LGMEAS codes.
    DISPLAY_CODES=set()
    if os.path.exists("ffiec002_hierarchy.json"):
        import json as _json
        _H=_json.load(open("ffiec002_hierarchy.json",encoding="utf-8"))
        for _items in _H.values():
            for _it in _items:
                if _it.get("mdrm"): DISPLAY_CODES.add(_it["mdrm"])
    # 4-char bases used in DERIV plus/minus/den + LGMEAS COMB raw codes; expand to all prefixes
    _BASES=['0010','2154','2927','2948','2200','2205','2365','2122','2170','2944',
            '1403','1406','1407','1607','1608','1763','1764',
            '1415','1420','1460','1480','1797','1422','1423','3184','3185','1885','3123',
            '1606','1421','3183']
    for _b in _BASES:
        for _p in ('RCFD','RCON','RCFN'):
            DISPLAY_CODES.add(_p+_b)
    DISPLAY_CODES.discard(None)
    if DISPLAY_CODES:
        _before=len(df); df=df[df["mdrm"].isin(DISPLAY_CODES)].reset_index(drop=True)
        print(f"site parquet limited to {len(DISPLAY_CODES)} display codes: {_before:,} -> {len(df):,} rows")
    NODATA_CODES=sorted(c for c in DISPLAY_CODES if c and c not in set(df["mdrm"].unique()))
    print(f"NODATA_CODES: {len(NODATA_CODES)} codes in hierarchy but absent from panel")
    # Sort id_rssd (entity) first: single-entity queries prune to that entity's row groups + better zstd.
    df=df.sort_values(["id_rssd","mdrm","quarter_end"]).reset_index(drop=True)
    # Perf mirror from Y-9C (Levers 3+6): ZSTD compression (~-21% size) + finer row groups (4x DuckDB pruning)
    _PQARGS=dict(index=False, compression='zstd', row_group_size=50000)
    PARTS=[]
    df.to_parquet(os.path.join(SITE,"ffiec002.parquet"),**_PQARGS); PARTS=["ffiec002.parquet"]
    if os.path.getsize(os.path.join(SITE,"ffiec002.parquet"))>MAXBYTES:
        os.remove(os.path.join(SITE,"ffiec002.parquet")); PARTS=[]; yr=df["quarter_end"].str[:4].astype(int)
        for lo,hi in [(1999,2009),(2010,2019),(2020,2030)]:
            sub=df[(yr>=lo)&(yr<=hi)]
            if sub.empty: continue
            fn=f"ffiec002_{lo}_{hi}.parquet"; sub.to_parquet(os.path.join(SITE,fn),**_PQARGS); PARTS.append(fn)
open(os.path.join(SITE,".nojekyll"),"w").close()
if os.path.exists("ffiec002_hierarchy.json"):
    shutil.copy("ffiec002_hierarchy.json", os.path.join(SITE,"ffiec002_hierarchy.json")); print("copied hierarchy")
else: print("NOTE: run build_hierarchy_002.py for the tree / call-report view")
# embed roster (id_rssd, name, entity_type)
banks=[]
try:
    for r in csv.DictReader(open("ffiec002_filer_roster.csv", encoding="latin-1")):
        try: rssd=int(str(r["id_rssd"]).strip())
        except: continue
        banks.append([rssd, (r.get("institution_name") or "").strip(), (r.get("entity_type") or "").strip()])
except Exception as e: print("(roster read failed:", e, ")")
BANKS_JSON=json.dumps(banks, ensure_ascii=False)
nodata_codes_js=json.dumps(NODATA_CODES)
parts_js="["+",".join(f"'{p}'" for p in PARTS)+"]"
print("parts:", [(p, round(os.path.getsize(os.path.join(SITE,p))/1e6,1)) for p in PARTS], "| filers:", len(banks))

HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FFIEC 002 Dashboard</title>
<style>
 *{box-sizing:border-box}
 body{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;color:#14213d;background:#fafbfc}
 header{background:#14213d;color:#fff;padding:12px 20px}header h1{margin:0;font-size:17px}header p{margin:3px 0 0;font-size:12px;color:#aeb7c9}
 .app{display:grid;grid-template-columns:var(--railw,460px) 7px 1fr;min-height:calc(100vh - 52px)}
 #railsplit{cursor:col-resize;background:#e3e8ef}#railsplit:hover{background:#b9c2cf}body.dark #railsplit{background:#2a3547}
 .app.popped #railsplit{display:none}
 .rail{border-right:1px solid #e3e8ef;background:#fff;display:flex;flex-direction:column;max-height:calc(100vh - 52px);position:sticky;top:0}
 .railtabs{display:flex;gap:4px;align-items:center;padding:8px 10px;border-bottom:1px solid #e3e8ef;background:#f7f9fb}
 .tab{background:#fff;color:#14213d;border:1px solid #cdd5e0;padding:4px 12px;border-radius:7px;font-size:12px;cursor:pointer}
 .tab.on{background:#14213d;color:#fff;border-color:#14213d}
 #panelItems,#panelEnts{flex:1;overflow:hidden;display:flex;flex-direction:column;min-height:0}
 .railhead{padding:8px 12px;border-bottom:1px solid #e3e8ef}
 .railhead input{width:100%;margin-top:6px;font-size:13px;padding:7px;border:1px solid #cdd5e0;border-radius:7px}
 #tree{flex:1;overflow:auto;padding:6px 10px}#entlistpanel{flex:1;overflow:auto;padding:4px 8px}
 .main{padding:14px 18px;overflow:auto}
 label{font-size:12px;color:#5a6478;display:block;margin-bottom:3px}
 select,input{font-size:14px;padding:7px;border:1px solid #cdd5e0;border-radius:7px;background:#fff}
 input{min-width:300px}#ent{min-width:380px}#pname{min-width:160px}
 button{font-size:13px;padding:7px 12px;border:1px solid #1b7f3b;background:#1b7f3b;color:#fff;border-radius:7px;cursor:pointer}
 button.sec{background:#fff;color:#14213d;border-color:#cdd5e0}
 .row{display:flex;gap:10px;flex-wrap:wrap;align-items:end;margin-bottom:10px}
 #status{font-size:12px;color:#5a6478;margin:6px 0}.muted{color:#5a6478;font-size:12px}
 .chips{display:flex;gap:8px;flex-wrap:wrap;margin:2px 0 10px}
 .chip{display:inline-flex;align-items:center;gap:7px;font-size:12px;background:#eef3f8;border:1px solid #d8e0ea;border-radius:14px;padding:4px 10px}
 .chip b{font-weight:600}.chip .x{cursor:pointer;color:#8a93a3;font-weight:700}
 .sw{width:10px;height:10px;border-radius:50%;display:inline-block}
 .cards{display:flex;gap:12px;flex-wrap:wrap;margin:6px 0 12px}
 .card{flex:1;min-width:140px;background:#fff;border:1px solid #e3e8ef;border-radius:10px;padding:10px 13px}
 .card .k{font-size:11px;color:#5a6478}.card .v{font-size:28px;font-weight:700;margin-top:3px}
 .up{color:#fff;background:#1b7f3b;border-radius:4px;padding:1px 5px;font-size:11px;font-weight:600}.dn{color:#fff;background:#c0392b;border-radius:4px;padding:1px 5px;font-size:11px;font-weight:600}
 table{border-collapse:collapse;width:100%;font-size:13px;margin-top:10px}th,td{border:1px solid #e3e8ef;padding:6px 9px;text-align:right}
 th{background:#f2f5f9;position:sticky;top:0;z-index:1}td:first-child,th:first-child{text-align:left}tr:nth-child(even) td{background:#f7f9fc}
 svg{background:#fff;border:1px solid #e3e8ef;border-radius:8px;display:block;overflow:visible}
 svg circle.pt{cursor:pointer;r:1.5px;fill-opacity:0;stroke-opacity:0;pointer-events:none;transition:r .1s,fill-opacity .1s,stroke-opacity .1s}
 svg .qband .reveal{opacity:0;transition:opacity .05s;pointer-events:none}svg .qband:hover .reveal{opacity:1}svg .qband-pinned .reveal{opacity:1!important;pointer-events:none}svg .qband .hit{fill:#000;fill-opacity:0;pointer-events:all;cursor:crosshair}
 details{margin-top:14px;background:#fff;border:1px solid #e3e8ef;border-radius:8px;padding:12px}
 textarea{width:100%;height:70px;font-family:Consolas,monospace;font-size:13px}
 .box{background:#fff;border:1px solid #e3e8ef;border-radius:8px;padding:12px;margin-bottom:12px}
 .legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;margin:6px 0 2px}
 .schhead{font-weight:700;color:#14213d;margin:8px 0 3px;cursor:pointer;font-size:12px}.schhead .cnt{color:#9aa3b2;font-weight:400}
 .trow{padding:3px 6px;border-radius:5px;cursor:pointer;font-size:12px;line-height:1.3;display:flex;align-items:baseline;gap:4px;white-space:nowrap}
 .trow:hover{background:#eef3f8}.trow .code{color:#9aa3b2;font-size:10px;flex:none}
 .trow.comb{color:#1b7f3b}.trow .num{color:#5a6478;flex:none}.trow.on{background:#dcefe2}.trow.nodata{opacity:0.38;pointer-events:none;cursor:default}.trow.hdr{font-weight:600;border-left:2px solid var(--accent,#1b7f3b);margin-top:2px}.trow.hdr .cap{color:#14213d}body.dark .trow.hdr .cap{color:#e6e9ef}
 .trow .cap{overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0}
 .caret{cursor:pointer;color:#5a6478;display:inline-block;width:13px;text-align:center;font-size:10px}
 .railctl{margin-top:6px;display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-size:11px}.railctl button{padding:3px 8px}
 .erow{display:flex;justify-content:space-between;gap:8px;padding:4px 6px;border-radius:5px;cursor:pointer;font-size:12px;border-bottom:1px solid #f3f5f8}
 .erow:hover{background:#eef3f8}.erow .en{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .erow .ev{color:#5a6478;font-variant-numeric:tabular-nums}.erow .pp{color:#1b7f3b;font-weight:700;cursor:pointer}.erow.agg{font-weight:600}
 .erow .ewl{cursor:pointer;color:#c8992e;font-size:12px;flex:none;padding:0 2px;opacity:.2;transition:opacity .1s;user-select:none}.erow .ewl.on{opacity:1;color:#e8a800}.erow:hover .ewl{opacity:.6}.erow:hover .ewl.on{opacity:1}
 .slider{display:flex;align-items:center;gap:10px;margin:8px 0}.slider input{min-width:120px;flex:1}
 .frow{display:flex;gap:10px;padding:2px 6px;font-size:13px;border-bottom:1px solid #f3f5f8}
 .frow .lab{flex:1;min-width:280px}.vcell{width:92px;flex:none;text-align:right;font-variant-numeric:tabular-nums;color:#14213d}
 :root{--border:#ccc;--head:#f7f8fc;--fg2:#64748b}
 .modal{position:fixed;inset:0;background:rgba(10,20,40,.4);z-index:60;display:flex;align-items:flex-start;justify-content:center}
 .modalbox{background:#fff;margin-top:32px;width:min(960px,95vw);height:88vh;min-width:480px;min-height:320px;max-width:98vw;display:flex;flex-direction:column;border-radius:10px;overflow:hidden;resize:both}
 .modalbody{flex:1;overflow:auto}
 .modalhead{padding:12px 14px;border-bottom:1px solid #e3e8ef;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
 /* popped rail leaves the grid (fixed) + splitter hidden; a single 1fr keeps #main full-width
    ("0 0 1fr" reflowed #main into a 0px column, collapsing it). */
 .app.popped{grid-template-columns:1fr}
 .modal.float{background:transparent;pointer-events:none}
 .modal.float .modalbox{pointer-events:auto;position:fixed;top:60px;left:60px;width:min(900px,92vw);box-shadow:0 14px 44px rgba(10,20,40,.35);resize:both}
 .modal.float .modalhead{cursor:move}
 /* fixed height (not max-height) + overflow:hidden so resize:both actually works */
 .rail.floating{position:fixed;top:70px;left:24px;width:380px;height:82vh;min-width:300px;min-height:240px;z-index:80;border:1px solid #cdd5e0;border-radius:10px;box-shadow:0 14px 44px rgba(10,20,40,.32);resize:both;overflow:hidden}
 .rail.floating .railtabs{cursor:move}
 #panelEnts.entfloat{position:fixed;top:90px;right:26px;width:380px;height:70vh;min-width:300px;min-height:240px;z-index:84;background:#fff;border:1px solid #cdd5e0;border-radius:10px;box-shadow:0 14px 44px rgba(10,20,40,.32);resize:both;overflow:hidden}
 body.dark #panelEnts.entfloat{background:#161e2b;border-color:#2a3547}
 #panelEnts.entfloat .railhead{cursor:move}
 #entdetach{float:right;padding:2px 8px;margin-left:6px}
 body.dark{background:#0e1420;color:#e6e9ef;--border:#2a3547;--head:#1a2638;--fg2:#9aa3b2}
 body.dark .rail,body.dark .card,body.dark .box,body.dark details,body.dark .modalbox{background:#161e2b;border-color:#2a3547}
 body.dark .railtabs{background:#121a26;border-color:#2a3547}body.dark .railhead,body.dark .modalhead{border-color:#2a3547}body.dark .rail{border-right-color:#2a3547}
 body.dark select,body.dark input,body.dark textarea,body.dark button.sec,body.dark .tab{background:#1b2433;color:#e6e9ef;border-color:#2a3547}
 body.dark .tab.on{background:#1b7f3b;color:#fff;border-color:#1b7f3b}
 body.dark .muted,body.dark label,body.dark .card .k,body.dark .schhead .cnt,body.dark .trow .code,body.dark .trow .num,body.dark .caret{color:#9aa3b2}
 body.dark .schhead,body.dark .card .v,body.dark .vcell,body.dark td:first-child{color:#e6e9ef}
 body.dark th{background:#1b2433;border-color:#2a3547}body.dark td{border-color:#2a3547}body.dark tr:nth-child(even) td{background:#19253a}body.dark .up{background:#1b5e2e}body.dark .dn{background:#8b1a1a}
 .erow.on{background:#dcefe2}
body.dark .erow.on{background:#16361f}
 body.dark .chip{background:#1b2433;border-color:#2a3547}body.dark .trow:hover,body.dark .erow:hover{background:#1f2a3a}body.dark .trow.on{background:#16361f}
 body.dark .erow,body.dark .frow{border-color:#222c3b}body.dark svg{background:#0f1825;border-color:#2a3547}
 body.dark .up{color:#3fb950}body.dark .dn{color:#f85149}body.dark a{color:#6cb6ff}
 #theme{float:right;background:rgba(255,255,255,.12);color:#fff;border:1px solid rgba(255,255,255,.25);padding:4px 10px;font-size:12px}
 .credit{margin:20px 2px 10px;font-size:11px;color:#9aa3b2}.credit a{color:inherit;text-decoration:underline}
.fav{cursor:pointer;color:#d69e2e;font-size:11px;flex:none;padding:0 3px;opacity:.4;transition:opacity .1s}.fav.on{opacity:1}.fav:hover{opacity:1}
.pane-toggle{font-size:11px;padding:3px 8px;margin-bottom:4px}
.trow.placeholder{opacity:.55;cursor:default;pointer-events:none}
#charttip{position:fixed;pointer-events:none;z-index:50;background:var(--tip-bg,#1a2535);color:var(--tip-fg,#e6e9ef);border:1px solid #3a4a5e;border-radius:8px;padding:8px 12px;font-size:12px;line-height:1.55;white-space:normal;max-width:min(460px,82vw);display:none;box-shadow:0 4px 16px rgba(0,0,0,.4)}
body:not(.dark) #charttip{--tip-bg:#fff;--tip-fg:#14213d;border-color:#cdd5e0;box-shadow:0 4px 16px rgba(0,0,0,.12)}
#charttip .tip-q{font-weight:700;margin-bottom:4px;color:#9aa3b2;font-size:11px}
#charttip .tip-row{display:flex;align-items:center;gap:6px}
#charttip .tip-sw{width:8px;height:8px;border-radius:50%;flex:none}
#toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%) translateY(8px);background:#1a2638;color:#e6e9ef;padding:9px 18px;border-radius:8px;font-size:13px;z-index:9999;pointer-events:none;opacity:0;transition:opacity .2s,transform .2s;max-width:min(360px,90vw);text-align:center;box-shadow:0 4px 16px rgba(0,0,0,.3)}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
#formulatip{position:fixed;pointer-events:none;z-index:55;background:var(--tip-bg,#1a2535);color:var(--tip-fg,#e6e9ef);border:1px solid #3a4a5e;border-radius:6px;padding:7px 11px;font-size:11px;line-height:1.5;display:none;box-shadow:0 3px 12px rgba(0,0,0,.35);max-width:320px;white-space:normal}
#formulatip .ftip-lbl{font-weight:600;color:#9aa3b2;font-size:10px;letter-spacing:.3px;text-transform:uppercase;margin-bottom:3px}
body:not(.dark) #formulatip{--tip-bg:#fff;--tip-fg:#14213d;border-color:#cdd5e0;box-shadow:0 3px 12px rgba(0,0,0,.12)}
body:not(.dark) .lgon-row td{background:#e8f5e9!important}body.dark .lgon-row td{background:#0f2f1c!important}.lgon-row .lglink{font-weight:600}
#pbar{position:fixed;top:0;left:0;height:3px;width:0%;background:var(--accent,#1b7f3b);transition:width .3s ease,opacity .4s ease;z-index:10000;pointer-events:none}
@media print{body{background:#fff!important;color:#000!important}.rail,.railsplit,#pbar,button,.modal,#charttip,header .buttons{display:none!important}.main{margin:0!important;padding:0!important}svg{break-inside:avoid;max-width:100%!important}body.dark{background:#fff!important;color:#000!important}.cards{flex-wrap:wrap!important}h1,h2{color:#000!important}}
</style></head><body class="dark">
<div id="pbar"></div><div id="formulatip" style="display:none"></div>
<header><button id="theme">☀ Light</button><h1>FFIEC 002 Dashboard</h1>
<p>U.S. Branches &amp; Agencies of Foreign Banks · filers + ALL / type / peer groups · 1999&ndash;present · $ thousands<span id="datacur"></span></p></header>
<div class="app">
 <div class="rail">
  <div class="railtabs"><button id="tabItems" class="tab on">Line items</button><button id="tabEnts" class="tab">Entities</button>
   <button id="popout" class="sec" style="margin-left:auto;padding:2px 8px">⧉ Pop out</button></div>
  <div id="panelItems">
   <div class="railhead"><span class="muted">click to add to chart</span>
    <input id="treesearch" placeholder="search code or caption…">
    <div class="railctl"><button id="drilldn" class="sec" title="expand one level in open branches [ ] keys">▼ Drill</button><button id="drillup" class="sec" title="collapse deepest open level [ ] keys">▲ Drill</button>
     <button id="expall" class="sec">⊕ all</button><button id="colall" class="sec">⊖ all</button>
     <button id="jumpto" class="sec" title="scroll to active measure in tree">⊙ active</button>
     <label><input type="checkbox" id="showraw"> RCFD/RCON variants</label></div></div>
   <div id="tree"><p class="muted" style="padding:10px">Loading…</p></div></div>
  <div id="panelEnts" style="display:none">
   <div class="railhead"><button id="entdetach" class="sec" title="use Items + Entities at once">⧉ Detach</button><span class="muted">click to chart · ＋peer to bucket</span>
    <input id="entsearch" placeholder="search branch / RSSD…">
    <div class="railctl">Show
     <select id="entfilter"><option value="all">All</option><option value="bank">Filers</option><option value="agg">Aggregates</option><option value="peer">Peer groups</option><option value="charted">Charted only</option><option value="watchlist">★ Watchlist</option></select>
     Sort <select id="entsort"><option value="assets">Total assets</option><option value="deposits">Total deposits</option><option value="loans">Total loans</option><option value="duet">Net due to related</option><option value="current">Current measure</option><option value="name">Name A–Z</option><option value="rssd">RSSD</option></select>
     <label><input type="checkbox" id="entdesc" checked> high→low</label>
     <!-- showmerged: lineage not available for this form --><label title="show predecessor / merged-bank RSSDs in entity list"><input type="checkbox" id="showmerged"> Show merged</label></div></div>
   <div id="entlistpanel"><p class="muted" style="padding:10px">…</p></div></div>
 </div>
 <div id="railsplit" title="drag to resize the panel"></div>
 <div class="main">
  <div id="status">Loading data engine…</div><div id="downloads" class="muted" style="margin-bottom:8px"></div>
  <div class="row">
   <div><label>Entity (branch name, RSSD, ALL, type USB/UFB/UFA/USA/IFB/ISB, or ★ peer group)</label>
    <input id="ent" list="entlist" autocomplete="off"><datalist id="entlist"></datalist></div>
   <div><button id="add" class="sec">+ Add to chart</button> <button id="addpeer" class="sec">+ Add to peer</button>
    <button id="formbtn" class="sec">📄 Call-report view</button> <button id="leaguebtn" class="sec">🏆 League table</button> <button id="reportbtn" class="sec" disabled title="Select a single filer to generate a tear-sheet report">📋 Report</button> <button id="exportbtn" class="sec">⬇ Export</button> <button id="copylink" class="sec" title="Copy link to current chart state">🔗 Link</button> <button id="kbdbtn" class="sec" title="Keyboard shortcuts (?)">⌨</button></div>
  </div>
  <div><label>Entities (overlay to compare)</label> <button id="clrents" class="sec" style="padding:1px 6px;font-size:10px;opacity:0.6" title="Remove all entities from chart">✕ Clear</button><div id="chips" class="chips"><span class="muted">none</span></div><div id="crosslinks" style="font-size:10px;color:var(--muted,#9aa3b2);margin-bottom:4px"></div></div>
  <div><label>Measures (click items in the left rail; ✕ to remove)</label> <button id="clrmeas" class="sec" style="padding:1px 6px;font-size:10px;opacity:0.6" title="Remove all measures">✕ Clear</button>
   <span style="font-size:11px;white-space:nowrap">Quick add: <select id="deriv-grpadd" style="font-size:11px;padding:1px 3px"><option value="">— category —</option><option value="Credit">Credit quality</option><option value="Loan quality">Loan-level NPL</option><option value="Funding">Funding</option><option value="Liquidity">Liquidity</option><option value="Subtotal">Subtotals $</option></select><button id="deriv-grpadd-btn" class="sec" style="padding:1px 6px;font-size:11px">Add</button></span>
   <div id="mchips" class="chips"><span class="muted">none</span></div></div>
  <details class="box" id="peerbox"><summary><b>Peer-group builder</b> — custom bucket of filers; aggregates correctly for levels &amp; ratios</summary>
   <div class="row" style="margin-top:10px"><div><label>Peer group name</label><input id="pname" placeholder="e.g. Japanese branches"></div>
    <div><button id="savepeer">Save peer group</button> <button id="clearpeer" class="sec">Clear members</button></div></div>
   <div><label>Members (use “+ Add to peer”; filers only)</label><div id="pmembers" class="chips"><span class="muted">none</span></div></div>
   <div><label>Saved peer groups</label><div id="psaved" class="chips"></div></div></details>
  <div id="kpiselrow" style="display:none;margin-bottom:4px"><span class="muted" style="font-size:11px">KPI series: </span><select id="kpisel" style="font-size:11px;padding:2px 4px;border:1px solid var(--border,#ccc);background:inherit;color:inherit;border-radius:4px"></select></div>
  <div class="cards" id="cards"></div><div class="legend" id="legend"></div>
  <div id="snapshot"></div>
  <div id="panes"><p class="muted">Pick an entity, then click a line item on the left.</p></div>
  <div class="slider" id="sliderwrap" style="display:none"><span class="muted">From</span><input type="range" id="r0"><input type="range" id="r1">
   <input type="text" id="rfrom" list="qlist" size="10" style="font:inherit;font-size:12px;border:1px solid var(--border,#ccc);border-radius:3px;padding:1px 4px;background:inherit;color:inherit"><span class="muted">to</span><input type="text" id="rto" list="qlist" size="10" style="font:inherit;font-size:12px;border:1px solid var(--border,#ccc);border-radius:3px;padding:1px 4px;background:inherit;color:inherit"><datalist id="qlist"></datalist> <button id="preset1y" class="sec" style="padding:3px 8px;font-size:11px">1Y</button><button id="preset5y" class="sec" style="padding:3px 8px;font-size:11px">5Y</button><button id="preset10y" class="sec" style="padding:3px 8px;font-size:11px">10Y</button><button id="rreset" class="sec" style="padding:3px 8px;font-size:11px">All</button>
   <label class="muted" title="rebase each $ series to 100 at the start of the range"><input type="checkbox" id="idx"> index to 100</label>
   <label class="muted" title="show quarter-over-quarter absolute change instead of level"><input type="checkbox" id="qoqdelta"> QoQ Δ</label>
   <label class="muted" title="divide each $ series by total assets (RCFD2170), producing a % ratio"><input type="checkbox" id="normbyassets"> ÷ assets</label>
   <span class="muted" style="font-size:11px;white-space:nowrap">⟵<input id="reflineval" type="text" placeholder="ref line e.g. 8 or 5e6" style="width:100px;font-size:11px;padding:1px 4px;border:1px solid var(--border,#ccc);background:inherit;color:inherit;border-radius:3px"><input id="reflinelbl" type="text" placeholder="label" style="width:60px;font-size:11px;padding:1px 4px;border:1px solid var(--border,#ccc);background:inherit;color:inherit;border-radius:3px"><button id="reflineset" class="sec" style="padding:1px 6px;font-size:11px">Set</button><button id="reflineclr" class="sec" style="padding:1px 6px;font-size:11px">✕</button></span>
   <button id="csv" class="sec">Export</button><button id="svgexport" class="sec" style="padding:3px 8px;font-size:11px" title="Download chart as SVG file">📷 SVG</button><button id="cplink" class="sec" style="padding:3px 8px;font-size:11px" title="Copy shareable link to this view">🔗 Link</button></div>
  <div id="tbl"></div>
  <details class="box"><summary><b>SQL</b> — table <code>t</code> (quarter_end,id_rssd,institution_name,entity_type,mdrm,description,value,source)</summary>
   <textarea id="sql">SELECT quarter_end, value FROM t WHERE id_rssd=450810 AND mdrm='RCFD2170' ORDER BY quarter_end;</textarea>
   <div style="margin-top:8px"><button id="runsql" class="sec">Run</button> <button id="sqlcsv" class="sec">Export result</button></div>
   <div id="sqlout"></div></details>
  <div class="credit">Built by Austin Fahrenkopf &middot; data: public FFIEC filings &middot; Built __BUILD_TS__</div>
 </div>
</div>
<div id="formmodal" class="modal" style="display:none"><div class="modalbox">
 <div class="modalhead" style="flex-wrap:wrap;row-gap:4px"><b>Call-report view</b>
  <div id="fent-chips" style="display:inline-flex;flex-wrap:wrap;gap:3px;margin:0 4px"></div>
  <input id="fent-inp" list="entlist" autocomplete="off" placeholder="name or RSSD…" style="font:inherit;font-size:11px;border:1px solid var(--border,#ccc);border-radius:3px;padding:2px 5px;background:inherit;color:inherit;width:140px">
  <button id="fent-add" class="sec" style="font-size:11px;padding:2px 6px">Add</button>
  <button id="fent-cur" class="sec" style="font-size:11px;padding:2px 6px" title="Add chart entities">+Chart</button>
  <label style="font-size:12px">From <select id="ffrom"></select></label><label style="font-size:12px">To <select id="fto"></select></label>
  <button id="ffull" class="sec" style="font-size:11px;padding:2px 6px" title="Full available range">Full</button>
  <input id="frow-filter" autocomplete="off" placeholder="filter items…" style="font:inherit;font-size:11px;border:1px solid var(--border,#ccc);border-radius:3px;padding:2px 5px;background:inherit;color:inherit;width:110px">
  <button id="fdn" class="sec" title="expand one level">▾</button><button id="fup" class="sec" title="collapse one level">▴</button>
  <button id="fexp" class="sec">⊕</button><button id="fcol" class="sec">⊖</button><button id="fpop" class="sec" title="float / dock">⧉</button>
  <button id="formexport" class="sec">Export</button> <button id="formclose" class="sec">Close</button></div>
 <div id="formbody" style="overflow:auto;padding:10px 14px"></div></div></div>
<div id="leaguemodal" class="modal" style="display:none"><div class="modalbox">
 <div class="modalhead"><b>🏆 League table</b>
  <label style="font-size:12px">Measure <select id="lgmeasure"></select></label>
  <label style="font-size:12px">Quarter <select id="lgquarter"></select></label>
  <label style="font-size:12px">Top <select id="lgtopn"><option>25</option><option>50</option><option>100</option><option value="0">All</option></select></label>
  <label style="font-size:12px" title="Filter by total-asset bucket">Size <select id="lgbucket"><option value="">All</option><option value="1">≥$1T</option><option value="0.1">$100B–$1T</option><option value="0.01">$10B–$100B</option><option value="0.001">$1B–$10B</option><option value="0.0001">$100M–$1B</option><option value="-">&lt;$100M</option></select></label>
  <button id="lgexport" class="sec">Export</button> <button id="lgclose" class="sec">Close</button></div>
 <div id="leaguebody" style="flex:1;overflow:auto;padding:10px 14px"><p class="muted">Loading…</p></div></div></div>
<div id="reportmodal" class="modal" style="display:none"><div class="modalbox" style="width:min(1040px,96vw);height:92vh">
 <div class="modalhead"><b>📋 Entity Report</b> &nbsp;<span id="rpt-title"></span><span id="rpt-asof" class="muted" style="font-size:11px"></span>
  <button id="rpt-addchart" class="sec">📈 Add to chart</button> <button id="rpt-print" class="sec">🖨 Print / PDF</button> <button id="rpt-html" class="sec" title="Download report as HTML file">⬇ HTML</button> <button id="rpt-link" class="sec" style="padding:3px 8px;font-size:11px" title="Copy link to this entity view">📎 Link</button> <button id="rptclose" class="sec">Close</button></div>
 <div id="rptbody" class="modalbody" style="flex:1;overflow:auto;padding:14px 18px"></div></div></div>
<div id="exportmodal" class="modal" style="display:none"><div class="modalbox" style="width:min(840px,96vw);max-height:92vh">
 <div class="modalhead"><b>⬇ Export Builder</b>
  <button id="expbld-setcur" class="sec" title="Copy current chart entity and date range">↺ From chart</button>
  <button id="expbld-preview" class="sec">👁 Preview</button>
  <button id="expbld-run" class="sec">⬇ Download CSV</button>
  <button id="expbld-close" class="sec">Close</button></div>
 <div id="expbldbody" class="modalbody" style="flex:1;overflow:auto;padding:14px 18px"><p class="muted">Loading…</p></div>
 <div id="eb-preview-area" style="overflow:auto;max-height:260px;padding:0 18px 10px;font-size:11px"></div></div></div>
<div id="toast"></div>
<div id="kbdmodal" class="modal" style="display:none"><div class="modalbox" style="width:min(420px,92vw)">
 <div class="modalhead"><b>⌨ Keyboard shortcuts</b> <button id="kbdclose" class="sec">Close</button></div>
 <div style="padding:16px;font-size:13px"><table style="width:100%;border-collapse:collapse">
  <tr><td style="padding:3px 10px;font-family:monospace;width:120px">[  ,</td><td>Previous quarter</td></tr>
  <tr><td style="padding:3px 10px;font-family:monospace">]  .</td><td>Next quarter</td></tr>
  <tr><td style="padding:3px 10px;font-family:monospace">/</td><td>Focus tree search</td></tr>
  <tr><td style="padding:3px 10px;font-family:monospace">Enter</td><td>Add first search result to chart</td></tr>
  <tr><td style="padding:3px 10px;font-family:monospace">Esc</td><td>Clear search / close modal</td></tr>
  <tr><td style="padding:3px 10px;font-family:monospace">I / E</td><td>Switch to Items / Entities tab</td></tr>
  <tr><td style="padding:3px 10px;font-family:monospace">L</td><td>Open League table</td></tr>
  <tr><td style="padding:3px 10px;font-family:monospace">R</td><td>Open entity report (single filer active)</td></tr>
  <tr><td style="padding:3px 10px;font-family:monospace">?</td><td>This help</td></tr>
 </table></div></div></div>
<script type="module">
import * as duckdb from 'https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/+esm';
const PARTS=__PARTS__, BANKS=__BANKS__;
const EMPTY_CODES=new Set(__NODATA__);
const st=m=>document.getElementById('status').textContent=m;
const _pb=document.getElementById('pbar');const pbar=pct=>{if(!_pb)return;_pb.style.width=pct+'%';if(pct>=100){setTimeout(()=>{_pb.style.opacity='0';setTimeout(()=>{_pb.style.display='none';},400);},300);}};
let _reflineVal=null,_reflineLbl='';
let _idxBase=null;
const COLORS=['#1b7f3b','#e07a1f','#2b6cb0','#b83280','#6b46c1','#d69e2e','#0f766e','#be123c'];
const RECESSIONS=[['1990-09-30','1991-03-31','1990-91'],['2001-03-31','2001-09-30','2001'],['2007-12-31','2009-06-30','GFC'],['2020-03-31','2020-12-31','COVID'],['2023-03-31','2023-06-30','Reg. Banking']];
const DK=()=>document.body.classList.contains('dark');
let _toastTmr;function showToast(msg,type='warn'){const t=document.getElementById('toast');t.textContent=msg;t.style.background=type==='err'?'#7f1d1d':type==='ok'?'#14532d':'#1a2638';t.classList.add('show');clearTimeout(_toastTmr);_toastTmr=setTimeout(()=>t.classList.remove('show'),2800);}
const ROSTER=new Map(),TYPES={};
for(const [rssd,nm,ty] of BANKS){ROSTER.set(rssd,{nm,ty});if(ty){(TYPES[ty]=TYPES[ty]||[]).push(rssd);}}
const TYPE_DESC={USB:'uninsured state branches',UFB:'uninsured federal branches',UFA:'uninsured federal agencies',USA:'uninsured state agencies',IFB:'insured federal branches',ISB:'insured state branches'};
const SCHED_NAMES={'RAL':'RAL — Assets & Liabilities','A':'A — Cash & Balances Due','C':'C — Loans & Leases','C -- Part II':'C — Part II (Small Business & Small Farm Loans)','E':'E — Deposits & Credit Balances','K':'K — Quarterly Averages','L':'L — Off-Balance-Sheet Items','M':'M — Memoranda','N':'N — Past Due & Nonaccrual','O':'O — Other Data','RAL -- Schedule P':'P — Other Borrowed Money','Q':'Q — Fair Value (Assets)','Q -- Liabilities':'Q — Fair Value (Liabilities)','Q -- Memoranda':'Q — Fair Value (Memoranda)','S':'S — Servicing/Securitization','T':'T — Other'};
const FORM_ORDER=['RAL','A','C','C -- Part II','E','K','L','M','N','O','RAL -- Schedule P','Q','Q -- Liabilities','Q -- Memoranda','S','T'];
const DERIV={
 'D_LOANSDEP':{type:'ratio',lbl:'Liquidity ▸ Loans / Deposits (%)',plus:['2122'],den:['2205']},
 'D_DEPASSETS':{type:'ratio',lbl:'Funding ▸ Deposits / Assets (%)',plus:['2205'],den:['2170']},
 'D_DUETO':{type:'ratio',lbl:'Funding ▸ Net due TO related / Assets (%)',plus:['2944'],den:['2170']},
 'D_DUEFROM':{type:'ratio',lbl:'Funding ▸ Net due FROM related / Assets (%)',plus:['2154'],den:['2170']},
 'D_NONREL':{type:'ratio',lbl:'Funding ▸ Nonrelated liabilities / Assets (%)',plus:['2927'],den:['2170']},
 'D_CASH':{type:'ratio',lbl:'Liquidity ▸ Cash & balances due / Assets (%)',plus:['0010'],den:['2170']},
 'D_NPL':{type:'ratio',lbl:'Credit ▸ NPL % (Past Due + Non Accrual / loans)',plus:['1403','1406','1407'],den:['2122']},
 'D_NONCUR':{type:'ratio',lbl:'Credit ▸ Noncurrent ratio % (1403+1407 / loans)',plus:['1403','1407'],den:['2122']},
 'S_NPL':{type:'sum',lbl:'Subtotal ▸ Past-due + nonaccrual loans $ (30-89+90++nonaccrual)',plus:['1403','1406','1407']},
 'S_NONCUR':{type:'sum',lbl:'Subtotal ▸ Noncurrent loans $ (1403+1407)',plus:['1403','1407']},
 'D_NPL_CI':{type:'ratio',lbl:'Loan quality ▸ C&I NPL % (Past Due + Non Accrual / C&I loans)',plus:['1606','1607','1608'],den:['1763','1764']},
 'D_NPL_RE':{type:'ratio',lbl:'Loan quality ▸ RE loans NPL % (Past Due + Non Accrual / RE loans)',plus:['1421','1422','1423'],den:['1415','1420','1460','1480','1797']},
 'D_NPL_OTHR':{type:'ratio',lbl:'Loan quality ▸ Other loans NPL % (Past Due + Non Accrual / other loans)',plus:['3183','3184','3185'],den:['1885']},
};
const DYN={};   // dynamic subtotal measures created by clicking a grouping row in the tree
const DKIND=m=>DERIV[m]?DERIV[m].type:null;const isPct=m=>DKIND(m)==='ratio';
const short=lbl=>{const i=lbl.indexOf('▸');return (i>=0?lbl.slice(i+1):lbl).replace(/\s*\(.*\)\s*$/,'').trim();};
const sqlList=a=>a.map(x=>`'${String(x).replace(/'/g,"''")}'`).join(',');
// MEDIUM-2: date-based quarter helpers — quarter strings are "YYYY-MM-DD" (end-of-quarter).
function prevQtr(q){if(!q)return null;const m=q.slice(5,7);return m==='03'?`${+q.slice(0,4)-1}-12-31`:m==='06'?`${q.slice(0,4)}-03-31`:m==='09'?`${q.slice(0,4)}-06-30`:`${q.slice(0,4)}-09-30`;}
function yoyQtr(q){return q?`${+q.slice(0,4)-1}${q.slice(4)}`:null;}
const fmtUnit=(v,pct)=>v==null?'—':pct?(+v).toFixed(2)+'%':(Math.abs(v)>=1e9?(v/1e6).toLocaleString(undefined,{maximumFractionDigits:0})+' B':Math.abs(v)>=1e6?(v/1e3).toLocaleString(undefined,{maximumFractionDigits:0})+' M':Number(v).toLocaleString()+' k');

let conn,HIER=null,treeBuilt=false,sqlC=[],sqlR=[],ALLQ=[];
const SUB_AGG_DESCS={
  // ONLY additive column-sum matrices: columns mutually-exclusive, same unit, NO redundant Total/Memo col,
  // AND the schedule body is UNIFORMLY that matrix (every clickable header sums the same exclusive columns).
  // Verified against panel + hierarchy (see ORCHESTRATION_STATE §68 v2).
  'N':'Total Past Due & Nonaccrual',     // 100% col rows: 30-89d / 90+d / nonaccrual / modified — exclusive states
  // NOT clean uniform column-sum matrices (header-sum would double-count, mix units, or the schedule is mixed):
  //   Q / Q -- Liabilities / Q -- Memoranda : each row has a "Total fair value" column PLUS Level 1/2/3
  //        → sum ≈ 2× total (codes RCFDJA36 / RCFDG478 populated)
  //   E : col "Memo: Total demand deposits (included in Column A)" (RCON2210, ~23k filings) is a SUBSET of
  //        column A → including it double-counts demand deposits
  //   L : MIXED — only items 10/11/12 are the 4-col derivative matrix (24 of 79 data rows are col); items 1-9
  //        (commitments, standby/commercial LCs, credit-derivative detail) are non-matrix OBS → descriptor mislabels them
  //   C -- Part II : columns are Number + Amount PAIRS per size bucket → sum mixes loan counts with dollars
  //   RAL, A, C, K, M, O, RAL -- Schedule P, S, T — roll-up
};
const _fullCap=new Map();
function _walkFC(nodes,parts,sch){for(const nd of nodes){if(!nd.placeholder&&!nd.derived&&!nd.header&&nd.code&&!/^(H:|SEC:|SUB:|EMPTY:)/.test(nd.code)){const cap=nd.caption||'';const anc=parts.filter(Boolean);_fullCap.set(nd.code,anc.length?anc.join(' — ')+' — '+cap:cap);}if(nd.header&&nd.code){const _sn=sch&&SCHED_NAMES[sch]?SCHED_NAMES[sch]:(parts.length?parts[0]:'');const _si=_sn.indexOf(' — ');const _sk=_si>=0?_sn.slice(0,_si):_sn;const _agg=sch?SUB_AGG_DESCS[sch]||'':'';const _cnt=(function c(n){let k=0;for(const x of(n.children||[])){if(x.header)k+=c(x);else if(x.code&&!x.placeholder&&!/^(H:|SEC:|SUB:|EMPTY:)/.test(x.code))k++;}return k;})(nd);if(_cnt>0){const _rl=_agg?_sk+' '+_agg+': '+(nd.caption||''):_sk?_sk+' '+(nd.caption||''):(nd.caption||'');_fullCap.set('SUB:'+nd.code,_rl);if(!/^(H:|SEC:|EMPTY:)/.test(nd.code)&&!_fullCap.has(nd.code))_fullCap.set(nd.code,_rl);}}if(nd.children&&nd.children.length)_walkFC(nd.children,nd.header?[...parts,nd.caption||'']:parts,sch);}}
function fullCap(code){return _fullCap.get(code)||'';}
const _seriesCache=new Map(),_inflight=new Map();
let active=[],measures=[],peerMembers=[],peers={},lastSeries=[],Qall=[],rangeSel={a:0,b:0};
function loadPeers(){try{peers=JSON.parse(localStorage.getItem('ffiec002_peers')||'{}');}catch{peers={};}}
function savePeers(){localStorage.setItem('ffiec002_peers',JSON.stringify(peers));}
function stateToHash(){
  const params=new URLSearchParams();
  if(active.length)params.set('e',active.map(a=>a.id).join(','));
  if(measures.length)params.set('m',measures.map(m=>m.code).join(','));
  if(Qall.length){params.set('q0',Qall[rangeSel.a]||'');params.set('q1',Qall[rangeSel.b]||'');}
  history.replaceState(null,'','#'+params.toString());}
function hashToState(){
  if(!location.hash||location.hash==='#')return false;
  try{const p=new URLSearchParams(location.hash.slice(1));
    const eStr=p.get('e');if(eStr){active=eStr.split(',').filter(Boolean).map(id=>({id,label:elabel(id)}));}
    const mStr=p.get('m');if(mStr){measures=[];for(const code of mStr.split(',').filter(Boolean)){
      const d=DERIV[code];const lbl=d?d.lbl:code;const pct=isPct(code);
      if(measures.length<6)measures.push({code,label:lbl,pct:!!pct});}}
    const q0=p.get('q0'),q1=p.get('q1');
    if(q0&&q1&&Qall.length){const a=Qall.indexOf(q0),b=Qall.indexOf(q1);
      if(a>=0&&b>=0)rangeSel={a:Math.min(a,b),b:Math.max(a,b)};}
    return !!(eStr||mStr);}catch{return false;}}
function elabel(id){if(id==='ALL')return 'ALL';if(id.startsWith('ET:'))return 'ALL '+id.slice(3);
 if(id.startsWith('PEER:'))return '★ '+id.slice(5);if(id.startsWith('BANK:')){const r=ROSTER.get(+id.slice(5));return r?`${r.nm} (${id.slice(5)})`:id;}return id;}
function resolveEnt(){const v=document.getElementById('ent').value.trim();
 if(v.replace(/^★\s*/,'') in peers){const n=v.replace(/^★\s*/,'');return {id:'PEER:'+n,label:'★ '+n};}
 const et=v.match(/\b(UFB|USB|UFA|USA|IFB|ISB)\b/i);if(et)return {id:'ET:'+et[1].toUpperCase(),label:'ALL '+et[1].toUpperCase()};
 if(/^all\b/i.test(v)||v.toUpperCase()==='ALL')return {id:'ALL',label:'ALL'};
 const m=v.match(/(\d{3,})/);if(m)return {id:'BANK:'+m[1],label:elabel('BANK:'+m[1])};return null;}
function scopeCond(id){if(id==='ALL')return '1=1';
 if(id.startsWith('ET:'))return `id_rssd IN (${(TYPES[id.slice(3)]||[-1]).join(',')})`;
 if(id.startsWith('BANK:'))return `id_rssd=${+id.slice(5)}`;
 if(id.startsWith('PEER:'))return `id_rssd IN (${(peers[id.slice(5)]||[-1]).join(',')})`;return null;}
function members(id){if(id.startsWith('BANK:'))return [+id.slice(5)];if(id.startsWith('ET:'))return TYPES[id.slice(3)]||[];
 if(id.startsWith('PEER:'))return peers[id.slice(5)]||[];if(id==='ALL')return [...ROSTER.keys()];return [];}
function coalesce(map,base){return map['RCFD'+base]??map['RCON'+base]??map['RCFN'+base];}

async function seriesFor(id,m){const cond=scopeCond(id);if(cond==null)return [];
 const _sk=`${id}::${m}`;if(_seriesCache.has(_sk))return _seriesCache.get(_sk);
 if(_inflight.has(_sk))return _inflight.get(_sk);
 const _p=(async()=>{
 let d=DERIV[m]||DYN[m];if(!d&&m&&m.startsWith('COMB'))d={type:'sum',plus:[m.slice(4)],minus:[],den:[]};
 if(d){const bases=[...d.plus,...(d.minus||[]),...(d.den||[])];
   const codes=[];for(const b of bases)for(const p of['RCFD','RCON','RCFN'])codes.push(`${p}${b}`);
   const r=(await conn.query(`SELECT id_rssd,quarter_end,mdrm,value FROM t WHERE ${cond} AND mdrm IN (${sqlList(codes)})`)).toArray();
   const byqe={};for(const x of r){((byqe[x.quarter_end]=byqe[x.quarter_end]||{})[x.id_rssd]=byqe[x.quarter_end][x.id_rssd]||{})[x.mdrm]=Number(x.value);}
   const acc=(mp,arr)=>{let s=0,seen=false;for(const b of arr){const v=coalesce(mp,b);if(v!=null){s+=v;seen=true;}}return [s,seen];};
   const out=[];for(const q of Object.keys(byqe).sort()){let num=0,den=0,anyN=false,anyD=false;
     for(const id2 of Object.keys(byqe[q])){const mp=byqe[q][id2];
       const [np,ns]=acc(mp,d.plus);const [nm,ms]=acc(mp,d.minus||[]);num+=np-nm;if(ns||ms)anyN=true;
       const [dp,ds]=acc(mp,d.den||[]);den+=dp;if(ds)anyD=true;}
     if(d.type==='sum'){if(anyN)out.push([q,num]);}else{if(anyN&&anyD&&den>0)out.push([q,100*num/den]);}}
   _seriesCache.set(_sk,out);return out;}
 const r=(await conn.query(`SELECT quarter_end, SUM(value) v FROM t WHERE ${cond} AND mdrm='${m}' GROUP BY quarter_end ORDER BY quarter_end`)).toArray();
 const res=r.map(x=>[String(x.quarter_end),Number(x.v)]);_seriesCache.set(_sk,res);return res;})();
 _inflight.set(_sk,_p);_p.then(()=>_inflight.delete(_sk),()=>_inflight.delete(_sk));return _p;}

async function init(){try{
 pbar(5);
 const B=duckdb.getJsDelivrBundles(),b=await duckdb.selectBundle(B);
 const w=await duckdb.createWorker(b.mainWorker);const db=new duckdb.AsyncDuckDB(new duckdb.ConsoleLogger(),w);
 await db.instantiate(b.mainModule,b.pthreadWorker);conn=await db.connect();pbar(20);
 let _doneP=0;
 for(const p of PARTS){const r=await fetch(new URL(p,location.href).href);if(!r.ok)throw new Error(p+' HTTP '+r.status);
   await db.registerFileBuffer(p,new Uint8Array(await r.arrayBuffer()));_doneP++;pbar(20+60*_doneP/Math.max(1,PARTS.length));}
 await conn.query(`CREATE VIEW t AS SELECT * FROM read_parquet([${PARTS.map(p=>`'${p}'`).join(',')}])`);
 ALLQ=(await conn.query('SELECT DISTINCT quarter_end FROM t ORDER BY quarter_end')).toArray().map(r=>String(r.quarter_end));
 {const maxQ=ALLQ[ALLQ.length-1];if(maxQ){const dc=document.getElementById('datacur');if(dc)dc.textContent=` · data through ${maxQ}`;}}
 pbar(85);loadPeers();rebuildEntList();
 try{const hr=await fetch(new URL('ffiec002_hierarchy.json',location.href).href);if(hr.ok)HIER=await hr.json();}catch(e){}
 document.getElementById('ent').value='ALL';
 document.getElementById('add').onclick=()=>{const e=resolveEnt();if(!e)return;if(!active.find(a=>a.id===e.id))active.push(e);renderChips();scheduleRecompute();};
 document.getElementById('addpeer').onclick=()=>{const e=resolveEnt();if(!e)return;if(!e.id.startsWith('BANK:')){showToast('Peer members must be individual filers.');return;}const rssd=+e.id.slice(5);if(!peerMembers.find(a=>a.rssd===rssd))peerMembers.push({rssd,label:e.label});renderPeerBuilder();document.getElementById('peerbox').open=true;};
 document.getElementById('savepeer').onclick=savePeer;document.getElementById('clearpeer').onclick=()=>{peerMembers=[];renderPeerBuilder();};
 document.getElementById('treesearch').addEventListener('input',e=>filterTree(e.target.value));
 document.getElementById('treesearch').addEventListener('keydown',e=>{if(e.key==='Escape'){e.target.value='';filterTree('');e.target.blur();}else if(e.key==='Enter'){const vis=[...document.querySelectorAll('#tree .trow')].filter(r=>r.style.display!=='none');if(vis.length)vis[0].click();}});
 document.getElementById('expall').onclick=()=>expandAll(true);document.getElementById('colall').onclick=()=>expandAll(false);
 document.getElementById('jumpto').onclick=()=>{
   const on=document.querySelector('#tree .trow.on');if(!on)return;
   on.scrollIntoView({block:'nearest',behavior:'smooth'});
   on.style.outline='2px solid #1b7f3b';setTimeout(()=>on.style.outline='',800);};
 document.getElementById('drilldn').onclick=()=>drillSmart(1);document.getElementById('drillup').onclick=()=>drillSmart(-1);
 document.addEventListener('keydown',e=>{if(e.target.closest('input,textarea,select'))return;if(e.key===']'||e.key==='.')  {e.preventDefault();drillSmart(1);}if(e.key==='['||e.key===','){e.preventDefault();drillSmart(-1);}if(e.key==='/'){e.preventDefault();const ts=document.getElementById('treesearch');ts.focus();ts.select();}if(e.key==='l'||e.key==='L'){e.preventDefault();openLeague();}if((e.key==='r'||e.key==='R')&&active.length===1&&active[0].id.startsWith('BANK:')){e.preventDefault();openReport(active[0].id);}if(e.key==='?'){e.preventDefault();document.getElementById('kbdmodal').style.display='flex';}if(e.key==='i'||e.key==='I'){e.preventDefault();switchTab(true);}if(e.key==='e'||e.key==='E'){e.preventDefault();switchTab(false);}if(e.key==='Escape'){document.querySelectorAll('.modal').forEach(m=>{if(m.style.display&&m.style.display!=='none')m.style.display='none';});}});
 document.getElementById('showraw').onchange=()=>buildTree();
 document.getElementById('showmerged').onchange=renderEntList;
 document.getElementById('tabItems').onclick=()=>switchTab(true);document.getElementById('tabEnts').onclick=()=>switchTab(false);
 document.getElementById('entsearch').addEventListener('input',renderEntList);
 document.getElementById('entsearch').addEventListener('keydown',e=>{if(e.key==='Escape'){e.target.value='';renderEntList();e.target.blur();}else if(e.key==='Enter'){const r=document.querySelector('#entlistpanel .erow');if(r)r.querySelector('.en').click();}});
 document.getElementById('entfilter').onchange=renderEntList;document.getElementById('entsort').onchange=renderEntList;document.getElementById('entdesc').onchange=renderEntList;
 if(localStorage.getItem('ffiec002_theme')==='light')document.body.classList.remove('dark');
 const setLbl=()=>document.getElementById('theme').textContent=DK()?'☀ Light':'🌙 Dark';setLbl();
 document.getElementById('theme').onclick=()=>{const d=document.body.classList.toggle('dark');localStorage.setItem('ffiec002_theme',d?'dark':'light');setLbl();draw();};
 (function(){const app=document.querySelector('.app'),rail=document.querySelector('.rail'),head=rail.querySelector('.railtabs');
  document.getElementById('popout').onclick=ev=>{ev.stopPropagation();const f=rail.classList.toggle('floating');app.classList.toggle('popped',f);document.getElementById('popout').textContent=f?'⧈ Dock':'⧉ Pop out';};
  let dx=0,dy=0,drag=false;head.addEventListener('mousedown',e=>{if(!rail.classList.contains('floating'))return;if(e.target.closest('input,button,label'))return;drag=true;dx=e.clientX-rail.offsetLeft;dy=e.clientY-rail.offsetTop;e.preventDefault();});
  window.addEventListener('mousemove',e=>{if(!drag)return;rail.style.left=(e.clientX-dx)+'px';rail.style.top=(e.clientY-dy)+'px';});window.addEventListener('mouseup',()=>{drag=false;});})();
 document.getElementById('entdetach').onclick=()=>{entFloating?dockEnts():detachEnts();};
 (function(){const p=document.getElementById('panelEnts'),h=p.querySelector('.railhead');let dx=0,dy=0,drag=false;
  h.addEventListener('mousedown',e=>{if(!entFloating)return;if(e.target.closest('input,button,select,label'))return;drag=true;dx=e.clientX-p.offsetLeft;dy=e.clientY-p.offsetTop;p.style.right='auto';e.preventDefault();});
  window.addEventListener('mousemove',e=>{if(!drag)return;p.style.left=(e.clientX-dx)+'px';p.style.top=(e.clientY-dy)+'px';});window.addEventListener('mouseup',()=>{drag=false;});})();
 document.getElementById('leaguebtn').onclick=openLeague;document.getElementById('lgclose').onclick=()=>document.getElementById('leaguemodal').style.display='none';
 document.getElementById('lgmeasure').onchange=renderLeague;document.getElementById('lgquarter').onchange=renderLeague;document.getElementById('lgtopn').onchange=renderLeague;document.getElementById('lgbucket').onchange=renderLeague;
 document.getElementById('lgexport').onclick=()=>{if(!window._lg)return;const pm=window._lg.pctileMap||new Map();dl2(['rank','rssd','filer',window._lg.meas.label,'QoQ','YoY','percentile'],window._lg.rows.map((r,i)=>[i+1,r.rssd,r.name,r.v,r.qoq,r.yoy,pm.get(r.rssd)??'']),'league');};
 document.getElementById('reportbtn').onclick=()=>{if(active.length===1&&active[0].id.startsWith('BANK:'))openReport(active[0].id);};
 document.getElementById('rptclose').onclick=()=>{document.getElementById('reportmodal').style.display='none';const p=new URLSearchParams(location.hash.slice(1));p.delete('report');history.replaceState(null,'','#'+p.toString());};
 document.getElementById('rpt-print').onclick=rptPrint;
 document.getElementById('rpt-html').onclick=()=>{const b=document.getElementById('rptbody');if(!b)return;const title=document.getElementById('rpt-title')?.textContent||'entity_report';const css=`<style>body{font-family:system-ui,sans-serif;margin:20px;background:#fff;color:#111}h3{margin:14px 0 6px}table{border-collapse:collapse}td,th{padding:3px 6px;border-bottom:1px solid #ddd}.muted{color:#666}</style>`;const html=`<!DOCTYPE html><html><head><meta charset="utf-8"><title>${title}</title>${css}</head><body>${b.innerHTML}</body></html>`;const bl=new Blob([html],{type:'text/html'});const a=document.createElement('a');a.href=URL.createObjectURL(bl);a.download=(title.replace(/\s+/g,'_').replace(/[^\w_-]/g,'')||'report')+'.html';a.click();};
 document.getElementById('rpt-link').onclick=()=>{if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(location.href).then(()=>showToast('Link copied!','ok')).catch(()=>prompt('Copy this link:',location.href));}else{prompt('Copy this link:',location.href);}};
 document.getElementById('exportbtn').onclick=openExportBuilder;
 document.getElementById('copylink').onclick=()=>{const b=document.getElementById('copylink');navigator.clipboard.writeText(location.href).then(()=>{const t=b.textContent;b.textContent='✓ Copied!';setTimeout(()=>b.textContent=t,2000);}).catch(()=>showToast('Copy the URL from the address bar.'));};
 document.getElementById('kbdbtn').onclick=()=>document.getElementById('kbdmodal').style.display='flex';
 document.getElementById('clrents').onclick=()=>{active=[];renderChips();scheduleRecompute();};
 document.getElementById('clrmeas').onclick=()=>{measures=[];entSortField='__none__';markTree();renderMeasures();scheduleRecompute();saveMeasures();};
 document.getElementById('deriv-grpadd-btn').onclick=()=>{const cat=document.getElementById('deriv-grpadd').value;if(!cat)return;let added=0;for(const [code,d] of Object.entries(DERIV)){const lbl=d.lbl||'';const parts=lbl.split(' ▸ ');if(parts[0]!==cat)continue;if(measures.length>=6){showToast('Measure limit is 6 — remove some first.','warn');break;}if(!measures.find(m=>m.code===code)){const shortLbl=parts.slice(1).join(' ▸ ')||lbl;measures.push({code,label:shortLbl,pct:true});added++;}}if(!added){showToast('No new measures found for that category.','warn');return;}entSortField='__none__';markTree();renderMeasures();scheduleRecompute();saveMeasures();};
 document.getElementById('kbdclose').onclick=()=>document.getElementById('kbdmodal').style.display='none';
 (function(){const ft=document.getElementById('formulatip');document.querySelector('.rail').addEventListener('mouseover',e=>{const row=e.target.closest('.trow[data-formula]');if(!row||!ft)return;ft.innerHTML=`<div class="ftip-lbl">Formula</div>${row.dataset.formula}`;ft.style.display='block';});document.querySelector('.rail').addEventListener('mouseout',e=>{if(e.target.closest('.trow[data-formula]')&&!e.relatedTarget?.closest('.trow[data-formula]'))ft.style.display='none';});document.addEventListener('mousemove',e=>{if(ft&&ft.style.display!=='none'){const x=e.clientX+14,y=e.clientY+14,w=ft.offsetWidth,h=ft.offsetHeight;ft.style.left=Math.min(x,window.innerWidth-w-10)+'px';ft.style.top=Math.min(y,window.innerHeight-h-10)+'px';}});})();
 document.getElementById('expbld-close').onclick=()=>document.getElementById('exportmodal').style.display='none';
 document.getElementById('expbld-run').onclick=async()=>{const btn=document.getElementById('expbld-run');btn.textContent='⏳…';btn.disabled=true;try{const res=await runExport(false);if(!res||!res.body?.length){showToast('No data for the selected scope.');return;}dl2(res.headers,res.body,'ffiec002_export');}catch(e){showToast('Export error: '+e,'err');}finally{btn.textContent='⬇ Download CSV';btn.disabled=false;}};
 document.getElementById('expbld-preview').onclick=async()=>{const btn=document.getElementById('expbld-preview');btn.textContent='⏳…';btn.disabled=true;try{const res=await runExport(true);if(!res)return;const sqlBlock=res.sql?`<details style="margin-bottom:8px"><summary style="cursor:pointer;font-size:11px;color:var(--muted,#9aa3b2)">Generated SQL (click to expand)</summary><pre style="font-size:10px;white-space:pre-wrap;word-break:break-all;background:var(--head,#eef2f7);padding:6px 8px;border-radius:4px;margin:4px 0">${res.sql.replace(/</g,'&lt;')}</pre></details>`:'';let h=`<table><tr>${res.headers.map(c=>`<th>${c}</th>`).join('')}</tr>`;for(const r of res.body)h+=`<tr>${r.map(v=>`<td>${v??''}</td>`).join('')}</tr>`;document.getElementById('eb-preview-area').innerHTML=sqlBlock+h+`</table><p class="muted">${res.body.length} rows shown (first 50).</p>`;}catch(e){showToast('Preview error: '+e,'err');}finally{btn.textContent='👁 Preview';btn.disabled=false;}};
 document.getElementById('expbld-setcur').onclick=()=>{for(const e of active){if(!_eb.entities.find(x=>x.id===e.id))_eb.entities.push({id:e.id,label:e.label});}if(Qall.length){_eb.fromQ=Qall[rangeSel.a];_eb.toQ=Qall[rangeSel.b];}renderExportUI();};
 document.getElementById('ffrom').onchange=renderForm;document.getElementById('fto').onchange=renderForm;
 document.getElementById('fexp').onclick=()=>expandAll(true,'#formbody');document.getElementById('fcol').onclick=()=>expandAll(false,'#formbody');
 document.getElementById('fdn').onclick=()=>drillSmart(1,'#formbody');document.getElementById('fup').onclick=()=>drillSmart(-1,'#formbody');
 document.getElementById('frow-filter').oninput=function(){const q=this.value.toLowerCase();document.querySelectorAll('#formbody .frow').forEach(r=>{const lab=r.querySelector('.lab');if(!lab)return;const txt=lab.textContent.toLowerCase();const show=!q||txt.includes(q);r.style.display=show?'':'none';});};
 document.getElementById('ffull').onclick=()=>{const qs=window._fq||[];if(qs.length){document.getElementById('ffrom').value=qs[0];document.getElementById('fto').value=qs[qs.length-1];}renderForm();};
 document.getElementById('fent-add').onclick=()=>{const v=document.getElementById('fent-inp').value.trim();if(!v)return;let ent=null;const cv=v.replace(/^★\s*/,'');if(cv in peers)ent={id:'PEER:'+cv,label:'★ '+cv};else if(/^all$/i.test(v))ent={id:'ALL',label:'ALL'};else{const m=v.match(/(\d{3,})/);if(m)ent={id:'BANK:'+m[1],label:elabel('BANK:'+m[1])};}if(ent){window._feEnts=window._feEnts||[];if(!window._feEnts.find(e=>e.id===ent.id)){window._feEnts.push(ent);renderFentChips();renderForm();}}document.getElementById('fent-inp').value='';};
 document.getElementById('fent-cur').onclick=()=>{window._feEnts=window._feEnts||[];for(const e of active){if(e.id.startsWith('BANK:')&&!window._feEnts.find(x=>x.id===e.id))window._feEnts.push({id:e.id,label:e.label});}renderFentChips();renderForm();};
 (function(){const md=document.getElementById('formmodal'),box=md.querySelector('.modalbox'),head=md.querySelector('.modalhead');
  document.getElementById('fpop').onclick=()=>md.classList.toggle('float');
  let dx=0,dy=0,drag=false;head.addEventListener('mousedown',e=>{if(!md.classList.contains('float'))return;if(e.target.closest('input,button,select,label'))return;drag=true;dx=e.clientX-box.offsetLeft;dy=e.clientY-box.offsetTop;e.preventDefault();});
  window.addEventListener('mousemove',e=>{if(!drag)return;box.style.left=(e.clientX-dx)+'px';box.style.top=(e.clientY-dy)+'px';});window.addEventListener('mouseup',()=>{drag=false;});})();
 document.getElementById('formbtn').onclick=openForm;document.getElementById('formclose').onclick=()=>{document.getElementById('formmodal').style.display='none';window._feEnts=[];};
 document.getElementById('formexport').onclick=exportForm;document.getElementById('csv').onclick=exportSeries;document.getElementById('svgexport').onclick=exportChartSVG;document.getElementById('kpisel').onchange=draw;document.getElementById('cplink').onclick=()=>{const url=location.href;if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(url).then(()=>showToast('Link copied!','ok')).catch(()=>prompt('Copy this link:',url));}else{prompt('Copy this link:',url);}};
 document.getElementById('runsql').onclick=runsql;document.getElementById('sqlcsv').onclick=()=>dl2(sqlC,sqlR,'query');
 document.getElementById('r0').oninput=onSlide;document.getElementById('r1').oninput=onSlide;
 document.getElementById('rreset').onclick=()=>{rangeSel={a:0,b:Qall.length-1};syncSlider();draw();};
 ['1y','5y','10y'].forEach((id,k)=>{const btn=document.getElementById(`preset${id}`);if(btn)btn.onclick=()=>{if(!Qall.length)return;const n=[4,20,40][k];rangeSel={a:Math.max(0,Qall.length-n),b:Qall.length-1};syncSlider();draw();};});
 document.getElementById('rfrom').onchange=()=>{const q=document.getElementById('rfrom').value.trim();const i=Qall.indexOf(q);if(i>=0){rangeSel.a=Math.min(i,rangeSel.b);syncSlider();draw();}};
 document.getElementById('rto').onchange=()=>{const q=document.getElementById('rto').value.trim();const i=Qall.indexOf(q);if(i>=0){rangeSel.b=Math.max(i,rangeSel.a);syncSlider();draw();}};
 document.getElementById('idx').onchange=draw;document.getElementById('qoqdelta').onchange=draw;document.getElementById('normbyassets').onchange=draw;document.getElementById('reflineset').onclick=()=>{const v=parseFloat(document.getElementById('reflineval').value);if(!isNaN(v)){_reflineVal=v;_reflineLbl=document.getElementById('reflinelbl').value.trim()||String(v);}draw();};document.getElementById('reflineclr').onclick=()=>{_reflineVal=null;document.getElementById('reflineval').value='';document.getElementById('reflinelbl').value='';draw();};
 (function(){const sp=document.getElementById('railsplit');let drag=false;
  sp.addEventListener('mousedown',e=>{drag=true;e.preventDefault();document.body.style.userSelect='none';});
  window.addEventListener('mousemove',e=>{if(!drag)return;const w=Math.min(820,Math.max(300,e.clientX));document.documentElement.style.setProperty('--railw',w+'px');});
  window.addEventListener('mouseup',()=>{drag=false;document.body.style.userSelect='';});})();
 document.getElementById('downloads').innerHTML='&#11015; Data: '+PARTS.map(p=>`<a href="${p}" download>${p}</a>`).join(' &middot; ')+' (Python / Power BI / DuckDB)';
 if(HIER)buildTree();else document.getElementById('tree').innerHTML='<p class="muted" style="padding:10px">hierarchy not found</p>';
 const restored=hashToState();
 if(!restored){active=[{id:'ALL',label:'ALL'}];}
 if(!measures.length){try{const s=localStorage.getItem('ffiec002_measures');if(s){const ms=JSON.parse(s);if(Array.isArray(ms)&&ms.length)measures=ms.slice(0,6);}}catch{}if(!measures.length)measures=[{code:'COMB2170',label:'Total assets',pct:false}];}
 renderChips();renderMeasures();renderPeerSaved();
 st(`Ready — ${ROSTER.size} filers. Click items on the left; add entities to compare.`);pbar(100);recompute();
 {const _rp=new URLSearchParams(location.hash.slice(1));if(_rp.get('report')==='1'&&active.length===1&&active[0].id.startsWith('BANK:'))openReport(active[0].id);}
}catch(e){st('Load failed: '+e);console.error(e);}}

function rebuildEntList(){const dl=document.getElementById('entlist');dl.innerHTML='';
 const add=v=>{const o=document.createElement('option');o.value=v;dl.appendChild(o);};
 add('ALL');for(const t in TYPES)add(t+' — '+(TYPE_DESC[t]||''));for(const n in peers)add('★ '+n);
 for(const [rssd,r] of ROSTER)add(`${r.nm} (${rssd}${r.ty?', '+r.ty:''})`);}
function renderChips(){const c=document.getElementById('chips');if(!active.length){c.innerHTML='<span class="muted">none</span>';const cl=document.getElementById('crosslinks');if(cl)cl.innerHTML='';return;}
 c.innerHTML=active.map((a,i)=>`<span class="chip"><span class="sw" style="background:${COLORS[i%COLORS.length]}"></span><b>${a.label}</b><span class="x" data-i="${i}">✕</span></span>`).join('');
 c.querySelectorAll('.x').forEach(x=>x.onclick=()=>{active.splice(+x.dataset.i,1);renderChips();scheduleRecompute();});
 // cross-dashboard links for BANK: entities
 const cl=document.getElementById('crosslinks');if(cl){const banks=active.filter(a=>a.id.startsWith('BANK:'));if(banks.length){const base=location.href.replace(/\/[^/]*$/,'/');const eHash=banks.map(a=>a.id).join(',');const mk=(dir,lbl)=>`<a href="${base.replace(/site_002\//,''+dir+'/')}index.html#e=${encodeURIComponent(eHash)}" target="_blank" style="color:var(--muted,#9aa3b2);text-decoration:underline dotted">${lbl}</a>`;cl.innerHTML='Also view in: '+mk('site_fry9c','Y-9C')+' · '+mk('site_call','Call');}else cl.innerHTML='';}
 // keep entity-list highlights in sync
 const ep=document.getElementById('panelEnts');
 if(ep&&ep.style.display!=='none')renderEntList();
 const rb=document.getElementById('reportbtn');if(rb)rb.disabled=!(active.length===1&&active[0].id.startsWith('BANK:'));}
const saveMeasures=()=>{try{localStorage.setItem('ffiec002_measures',JSON.stringify(measures.map(m=>({code:m.code,label:m.label,pct:m.pct}))));}catch{}};
function renderMeasures(){const c=document.getElementById('mchips');if(!measures.length){c.innerHTML='<span class="muted">none</span>';return;}
 c.innerHTML=measures.map((m,i)=>`<span class="chip"><b>${m.label}</b> <span class="muted">${m.pct?'%':'$'}</span><span class="x" data-i="${i}">✕</span></span>`).join('');
 c.querySelectorAll('.x').forEach(x=>x.onclick=()=>{measures.splice(+x.dataset.i,1);entSortField='__none__';markTree();renderMeasures();scheduleRecompute();saveMeasures();});}
function renderPeerBuilder(){const c=document.getElementById('pmembers');if(!peerMembers.length){c.innerHTML='<span class="muted">none</span>';return;}
 c.innerHTML=peerMembers.map((a,i)=>`<span class="chip"><b>${a.label}</b><span class="x" data-i="${i}">✕</span></span>`).join('');
 c.querySelectorAll('.x').forEach(x=>x.onclick=()=>{peerMembers.splice(+x.dataset.i,1);renderPeerBuilder();});}
function renderPeerSaved(){const c=document.getElementById('psaved');const names=Object.keys(peers);
 if(!names.length){c.innerHTML='<span class="muted">none saved</span>';return;}
 c.innerHTML=names.map(n=>`<span class="chip"><b>★ ${n}</b> <span class="muted">(${peers[n].length})</span> <span class="use" data-n="${n}" style="cursor:pointer;color:#1b7f3b;font-weight:700">＋chart</span> <span class="x" data-n="${n}">✕</span></span>`).join('');
 c.querySelectorAll('.use').forEach(u=>u.onclick=()=>{const id='PEER:'+u.dataset.n;if(!active.find(a=>a.id===id))active.push({id,label:'★ '+u.dataset.n});renderChips();scheduleRecompute();});
 c.querySelectorAll('.x').forEach(x=>x.onclick=()=>{delete peers[x.dataset.n];savePeers();rebuildEntList();renderPeerSaved();});}
function savePeer(){const n=document.getElementById('pname').value.trim();if(!n){showToast('Name the peer group.');return;}
 if(!peerMembers.length){showToast('Add at least one member.');return;}
 const prefix=`PEER:${n}::`;for(const k of _seriesCache.keys())if(k.startsWith(prefix))_seriesCache.delete(k);
 peers[n]=peerMembers.map(m=>m.rssd);savePeers();rebuildEntList();renderPeerSaved();
 document.getElementById('pname').value='';peerMembers=[];renderPeerBuilder();st(`Saved peer group "${n}".`);}

function loadFavs(){try{return new Set(JSON.parse(localStorage.getItem('ffiec002_favs')||'[]'));}catch{return new Set();}}
function saveFavs(s){localStorage.setItem('ffiec002_favs',JSON.stringify([...s]));}
function loadWL(){try{return new Set(JSON.parse(localStorage.getItem('ffiec002_wl')||'[]'));}catch{return new Set();}}
function saveWL(s){localStorage.setItem('ffiec002_wl',JSON.stringify([...s]));}
function buildFavShelf(){
  const favs=loadFavs();if(!favs.size)return null;
  const nodes=[...favs].map(code=>{
    const row=document.querySelector(`#tree .trow[data-code="${CSS.escape(code)}"]`);
    const cap=row?row.querySelector('.cap')?.textContent||code:code;
    return {code,caption:cap,num:'',depth:1,comb:false,derived:false,pct:false,children:[]};});
  return nodes;}
function renderFavShelf(){
  const old=document.getElementById('favshelf');if(old)old.remove();
  const nodes=buildFavShelf();if(!nodes||!nodes.length)return;
  const t=document.getElementById('tree');
  const {sec,rows}=mkSec('★ Favorites',nodes.length);sec.id='favshelf';
  renderNodes(rows,nodes);rows.style.display='block';
  sec.querySelector('.schhead').innerHTML=sec.querySelector('.schhead').innerHTML.replace('▸','▾');
  t.insertBefore(sec,t.firstChild);}
// ---- tree ----
const REPORT=/^(RCON|RCFD|RCFN)[A-Z0-9]{4}$/;
function mkSec(title,cnt){const sec=document.createElement('div');sec.className='schsec';
 const h=document.createElement('div');h.className='schhead';h.innerHTML=`▸ ${title} ${cnt?`<span class=cnt>(${cnt})</span>`:''}`;
 const rows=document.createElement('div');rows.className='schrows';rows.style.display='none';
 h.onclick=()=>{const open=rows.style.display!=='none';rows.style.display=open?'none':'block';h.innerHTML=h.innerHTML.replace(open?'▾':'▸',open?'▸':'▾');};
 sec.appendChild(h);sec.appendChild(rows);return {sec,rows};}
function rowEl(nd,has,dispCap){
 if(nd.placeholder){
   const p=document.createElement('div');p.className='trow placeholder';
   p.style.cssText=`padding-left:${6+(nd.depth-1)*14}px`;
   p.innerHTML=`<span class="caret" style="visibility:hidden">▸</span>`+
     (nd.num?`<span class="num">${nd.num}</span>`:'') +
     `<span class="cap" style="color:#9aa3b2;font-style:italic">(empty)</span>`;
   return p;}
 if(nd.header){
   const d=document.createElement('div');d.className='trow hdr';
   d.dataset.code=nd.code;d.dataset.depth=nd.depth;d.style.paddingLeft=(6+(nd.depth-1)*14)+'px';
   const car=`<span class="caret"${has?'':' style="visibility:hidden"'}>▸</span>`;
   const cap=`<span class="cap" title="${String(nd.caption||'').replace(/"/g,'&quot;')}">${dispCap||nd.caption||''}</span>`;
   d.innerHTML=`${car}${nd.num?`<span class=num>${nd.num}</span>`:''}${cap}`;
   d.querySelector('.caret').onclick=ev=>{ev.stopPropagation();if(has)toggleNode(d);};
   const codes=descCodes(nd);const pctSkip=hasPctDesc(nd);
   if(codes.length){d.title='Click to chart sum of '+codes.length+' leaf $ code(s)'+(pctSkip?' · non-additive % cells excluded':'');
     d.onclick=()=>{const code='SUB:'+nd.code;const rl=fullCap(code)||nd.caption;DYN[code]={type:'sum',lbl:rl,plus:codes};toggleMeasure(code,rl,false);};}
   else if(pctSkip){d.title='Contains only non-additive % cells — cannot sum';d.onclick=()=>{if(has)toggleNode(d);};}
   else d.onclick=()=>{if(has)toggleNode(d);};
   return d;}
 const d=document.createElement('div');d.className='trow'+(nd.comb?' comb':'');
 d.dataset.code=nd.code;d.dataset.txt=(nd.code+' '+nd.caption).toLowerCase();d.dataset.depth=nd.depth;d.style.paddingLeft=(6+(nd.depth-1)*14)+'px';
 const car=`<span class="caret"${has?'':' style="visibility:hidden"'}>▸</span>`;
 const cap=`<span class="cap" title="${String(nd.caption||'').replace(/"/g,'&quot;')}">${dispCap||nd.caption||''}</span>`;
 d.innerHTML=nd.derived?`${car}${cap}`:`${car}${(nd.num&&!nd.col)?`<span class=num>${nd.num}</span>`:''}${cap}<span class=code>${nd.code}</span>`;
 const lab=nd.derived?short(nd.caption):(nd.caption||nd.code);
 d.querySelector('.caret').onclick=ev=>{ev.stopPropagation();if(has)toggleNode(d);};
 d.onclick=()=>toggleMeasure(nd.code,lab,nd.pct);
 if(nd.derived&&DERIV[nd.code]){const dr=DERIV[nd.code];const ab=a=>{if(!a||!a.length)return '?';return a.length<=3?a.join(' + '):a.slice(0,2).join(' + ')+` + …(${a.length})`;};let fml;if(dr.type==='ratio'){const nStr=dr.minus&&dr.minus.length?`(${ab(dr.plus)} − ${ab(dr.minus)})`:ab(dr.plus);fml=`${nStr} ÷ ${ab(dr.den)} × 100${dr.annualize?' × (4/N)':''}`;}else{fml=`${ab(dr.plus)}`;}d.dataset.formula=fml;d.title='Click to chart · hover for formula';}
 if(!nd.derived){const fstar=document.createElement('span');fstar.className='fav'+(loadFavs().has(nd.code)?' on':'');fstar.textContent='★';fstar.title='Add to favorites';
   fstar.onclick=ev=>{ev.stopPropagation();const f=loadFavs();if(f.has(nd.code)){f.delete(nd.code);fstar.classList.remove('on');}else{f.add(nd.code);fstar.classList.add('on');}saveFavs(f);renderFavShelf();};
   const caret=d.querySelector('.caret');if(caret)caret.after(fstar);else d.prepend(fstar);}
 if(!nd.header&&!nd.derived&&EMPTY_CODES.has(nd.code)){d.classList.add('nodata');d.title='No panel data for this item';}
 return d;}
// nest by the item NUMBER (parent of "1.a.1" is "1.a") — robust for matrix schedules
function nest(flat){const ns=flat.map(it=>({...it,children:[]}));
 const byItem=new Map();for(const n of ns){if(n.num){if(!byItem.has(n.num))byItem.set(n.num,[]);byItem.get(n.num).push(n);}}
 const first=it=>{const a=byItem.get(it);return a&&a[0];};
 const ancestor=it=>{const p=String(it).split('.');p.pop();while(p.length){const k=p.join('.');if(byItem.has(k))return k;p.pop();}return null;};
 const roots=[];
 for(const n of ns){if(!n.num){roots.push(n);continue;}const a=ancestor(n.num);const par=a&&first(a);(par?par.children:roots).push(n);}
 return roots;}
function emitSchedule(sch,showRaw){const allRows=HIER[sch];
 // Emit rows in ORIGINAL hierarchy order, interleaving header/placeholder rows and code rows.
 // (Previously code rows and header rows were collected separately and concatenated, which made
 //  code-bearing top-level items — e.g. RAL item 3 Total assets, 6 Total liabilities, 9395 —
 //  sort ABOVE header-only top-level items 1/2/4/5. nest() orders siblings by list position, so
 //  preserving the JSON order here is what keeps the form's numeric item order in the tree.)
 const raw=allRows.filter(r=>REPORT.test(r.mdrm));
 const combBases=new Set();for(const r of raw){const p=r.mdrm.slice(0,4);if(p==='RCFD'||p==='RCON')combBases.add(r.mdrm.slice(4));}
 const out=[],done=new Set();
 for(const r of allRows){
   if(!REPORT.test(r.mdrm)){ // header / placeholder row (no valid MDRM)
     if(!r.item)continue;
     if(r.caption)out.push({code:'HDR:'+sch+':'+r.item,caption:r.caption,num:r.item||'',depth:r.depth||1,comb:false,derived:false,pct:false,header:true});
     else out.push({code:'EMPTY:'+r.item,caption:'(empty)',num:r.item||'',depth:r.depth||1,comb:false,derived:false,pct:false,placeholder:true});
     continue;}
   const p=r.mdrm.slice(0,4),base=r.mdrm.slice(4),cap=r.caption||r.mdrm;const depth=r.depth||1;
   if(p==='RCFD'||p==='RCON'){if(!done.has('C'+base)){done.add('C'+base);out.push({code:'COMB'+base,caption:cap,num:r.item||'',depth,comb:true,derived:false,pct:false,col:!!r.col});}
     if(showRaw&&!done.has(r.mdrm)){done.add(r.mdrm);out.push({code:r.mdrm,caption:cap+' ['+p.slice(2)+']',num:'',depth:depth+1,comb:false,derived:false,pct:false});}}
   else{if(combBases.has(base))continue;if(!done.has(r.mdrm)){done.add(r.mdrm);out.push({code:r.mdrm,caption:cap,num:r.item||'',depth,comb:false,derived:false,pct:false,col:!!r.col});}}}
 return out;}
function secPrefix(nodes){
 const caps=[];function walk(ns){for(const n of ns){if(!n.header&&!n.derived&&!n.placeholder){if(!n.children.length)caps.push(n.caption||'');else walk(n.children);}}}
 walk(nodes);if(caps.length<3)return '';
 let pre=caps[0];for(const s of caps.slice(1)){while(pre&&!s.startsWith(pre))pre=pre.slice(0,-1);}
 const mm=pre.match(/^(.*\w)\s*/);pre=mm?mm[1]+' ':pre;if(pre.length<12)return '';
 return caps.filter(c=>c.startsWith(pre)).length/caps.length>=0.7?pre:'';}
function nodeChildPfx(children){
 const caps=children.filter(c=>!c.placeholder&&!c.col&&!c.header).map(c=>c.caption||'');
 if(caps.length<2)return '';
 let pre=caps[0];for(const s of caps.slice(1)){while(pre&&!s.startsWith(pre))pre=pre.slice(0,-1);}
 const mm=pre.match(/^(.*\w)\s*/);pre=mm?mm[1]+' ':pre;
 if(pre.length<12)return '';
 const tails=caps.filter(c=>c.startsWith(pre)).map(c=>c.slice(pre.length).replace(/^[\s:\-–]+/,''));
 if(tails.some(t=>t.length<10))return '';
 return pre;}
function renderNodes(container,nodes,pfx,pfx2){if(!pfx)pfx='';if(!pfx2)pfx2='';
 // Matrix rows: items sharing item# with long common prefix get "… stripped" display
 const disp=new Map(),grp={};
 for(const n of nodes) if(!n.header&&n.num){(grp[n.num]=grp[n.num]||[]).push(n);}
 for(const num in grp){const g=grp[num];if(g.length<2)continue;
   let pre=g[0].caption||'';
   for(const n of g){const c=n.caption||'';while(pre&&!c.startsWith(pre))pre=pre.slice(0,-1);}
   const mm=pre.match(/^.*[ :\-–]/);const bp=mm?mm[0]:'';
   if(bp.length>=18)for(const n of g){const c=n.caption||'';if(c.startsWith(bp))disp.set(n,'… '+c.slice(bp.length).replace(/^[\s:\-–]+/,''));}}
 for(const nd of nodes){const has=nd.children.length>0;
   let dc=disp.get(nd);
   if(!dc){const cap=nd.caption||'';
     if(pfx2&&!nd.header&&cap.toUpperCase().startsWith(pfx2.toUpperCase())){const tail=cap.slice(pfx2.length).replace(/^[\s:\-–]+/,'');dc='… '+(tail||'(total)');}
     else if(pfx&&cap.toUpperCase().startsWith(pfx.toUpperCase()))dc=cap.slice(pfx.length).replace(/^[\s:\-–]+/,'');}
   const row=rowEl(nd,has,dc);container.appendChild(row);
 if(has){const kids=document.createElement('div');kids.className='kids';kids.style.display='none';
   const kp=nodeChildPfx(nd.children);renderNodes(kids,nd.children,pfx,kp);container.appendChild(kids);row._kids=kids;}}}
function addSchedule(t,title,nodes){const pfx=secPrefix(nodes);const {sec,rows}=mkSec(title,nodes.length);renderNodes(rows,nodes,pfx);t.appendChild(sec);}
function toggleNode(row){if(!row._kids)return;const open=row._kids.style.display!=='none';row._kids.style.display=open?'none':'block';const c=row.querySelector('.caret');if(c)c.textContent=open?'▸':'▾';}
function buildTree(){const t=document.getElementById('tree');t.innerHTML='';const showRaw=document.getElementById('showraw').checked;
 addSchedule(t,'★ Ratios & Subtotals',Object.keys(DERIV).map(k=>({code:k,caption:DERIV[k].lbl,num:'',depth:1,comb:false,derived:true,pct:isPct(k),children:[]})));
 const keys=[...FORM_ORDER.filter(k=>HIER[k]),...Object.keys(HIER).filter(k=>SCHED_NAMES[k]&&!FORM_ORDER.includes(k))];
 for(const sch of keys){const flat=emitSchedule(sch,showRaw);if(!flat.length)continue;const nroots=nest(flat);addSchedule(t,SCHED_NAMES[sch]||sch,nroots);_walkFC(nroots,[SCHED_NAMES[sch]||sch],sch);}
 treeBuilt=true;markTree();renderFavShelf();}
let lvl={'#tree':0,'#formbody':0};
function applyLevel(L,root='#tree'){L=Math.max(0,L);lvl[root]=L;
 document.querySelectorAll(`${root} .schrows`).forEach(r=>r.style.display=L>=1?'block':'none');
 document.querySelectorAll(`${root} .schhead`).forEach(h=>{const w=L>=1;h.innerHTML=h.innerHTML.replace(w?'▸':'▾',w?'▾':'▸');});
 document.querySelectorAll(`${root} .trow, ${root} .frow`).forEach(row=>{if(!row._kids)return;const d=+(row.dataset.depth||1),open=d<L;
   row._kids.style.display=open?'block':'none';const c=row.querySelector('.caret');if(c&&c.style.visibility!=='hidden')c.textContent=open?'▾':'▸';});}
function maxDepth(root){let m=1;document.querySelectorAll(`${root} .trow, ${root} .frow`).forEach(r=>{const d=+(r.dataset.depth||1);if(d>m)m=d;});return m;}
function expandAll(open,root='#tree'){applyLevel(open?maxDepth(root)+1:0,root);}
function drill(step,root='#tree'){applyLevel((lvl[root]||0)+step,root);}
function drillSmart(step,root='#tree'){
  if(step>0){
    const openRows=[];
    document.querySelectorAll(`${root} .trow,${root} .frow`).forEach(r=>{
      if(r._kids&&r._kids.style.display==='block')openRows.push(r);});
    if(!openRows.length){
      document.querySelectorAll(`${root} .schrows`).forEach(r=>r.style.display='block');
      document.querySelectorAll(`${root} .schhead`).forEach(h=>{h.innerHTML=h.innerHTML.replace('▸','▾');});
      return;}
    openRows.forEach(row=>{
      Array.from(row._kids.children).forEach(el=>{
        if((el.classList.contains('trow')||el.classList.contains('frow'))&&el._kids){
          el._kids.style.display='block';
          const c=el.querySelector('.caret');
          if(c&&c.style.visibility!=='hidden')c.textContent='▾';}});});
  } else {
    let maxD=0;
    document.querySelectorAll(`${root} .trow,${root} .frow`).forEach(r=>{
      if(r._kids&&r._kids.style.display==='block'){const d=+(r.dataset.depth||1);if(d>maxD)maxD=d;}});
    if(!maxD){
      document.querySelectorAll(`${root} .schrows`).forEach(r=>r.style.display='none');
      document.querySelectorAll(`${root} .schhead`).forEach(h=>{h.innerHTML=h.innerHTML.replace('▾','▸');});
      return;}
    document.querySelectorAll(`${root} .trow,${root} .frow`).forEach(r=>{
      if(!r._kids||r._kids.style.display==='none')return;
      if(+(r.dataset.depth||1)===maxD){r._kids.style.display='none';
        const c=r.querySelector('.caret');if(c&&c.style.visibility!=='hidden')c.textContent='▸';}});}}
function filterTree(q){q=q.trim().toLowerCase();
 if(!q){document.querySelectorAll('#tree .trow').forEach(r=>r.style.display='');document.querySelectorAll('#tree .schsec').forEach(s=>s.style.display='');expandAll(false);return;}
 document.querySelectorAll('#tree .kids').forEach(k=>k.style.display='block');
 document.querySelectorAll('#tree .schsec').forEach(sec=>{const rows=sec.querySelector('.schrows');let any=false;
   sec.querySelectorAll('.trow').forEach(r=>{const m=r.dataset.txt.includes(q);r.style.display=m?'':'none';if(m)any=true;});
   rows.style.display=any?'block':'none';sec.style.display=any?'':'none';});}
function descCodes(nd){const out=[];(function rec(n){for(const c of (n.children||[])){if(c.header)rec(c);else if(c.code&&!c.placeholder&&!c.derived)out.push(c.code.slice(4));}})(nd);return out;}
function hasPctDesc(nd){return false;}
function markTree(){const on=new Set(measures.map(m=>m.code));document.querySelectorAll('#tree .trow').forEach(r=>r.classList.toggle('on',on.has(r.dataset.code)||on.has('SUB:'+r.dataset.code)));}
function toggleMeasure(code,label,pct){const i=measures.findIndex(m=>m.code===code);
 if(i>=0)measures.splice(i,1);else{if(measures.length>=6){showToast('Up to 6 measures.');return;}measures.push({code,label,pct:!!pct});}
 entSortField='__none__';markTree();renderMeasures();scheduleRecompute();saveMeasures();}

// ---- entity panel ----
let entSortVals=new Map(),entSortField='__none__';
async function computeSortVals(field){if(field===entSortField)return;entSortVals=new Map();
 if(field==='name'||field==='rssd'){entSortField=field;return;}
 const baseMap={assets:'2170',deposits:'2205',loans:'2122',duet:'2944'};
 let base;if(field==='current'){if(!measures.length){entSortField=field;return;}const c=measures[0].code;base=(c.startsWith('COMB')||/^(RCFD|RCON|RCFN)/.test(c))?c.slice(4):null;
   if(!base){
     // LOW-1: derived code — use perFilerValues so sort works for D_* ratios
     try{const latR=(await conn.query('SELECT max(quarter_end) q FROM t')).toArray();const latQ=latR.length?String(latR[0].q):null;
       if(latQ){const vals=await perFilerValues(c,[latQ]);const cur=vals[latQ]||new Map();
         let all=0;for(const[rssd,v]of cur){entSortVals.set('BANK:'+rssd,v);all+=v;}
         entSortVals.set('ALL',all);
         for(const n in peers){let s=0,any=false;for(const r2 of peers[n])if(cur.has(r2)){s+=cur.get(r2);any=true;}if(any)entSortVals.set('PEER:'+n,s);}}}catch(e){}
     entSortField=field;return;}}else base=baseMap[field];
 const codes=['RCFD'+base,'RCON'+base,'RCFN'+base];
 try{const r=(await conn.query(`SELECT id_rssd,mdrm,value FROM t WHERE mdrm IN (${sqlList(codes)}) AND quarter_end=(SELECT max(quarter_end) FROM t)`)).toArray();
   const per={};for(const x of r){(per[x.id_rssd]=per[x.id_rssd]||{})[x.mdrm]=Number(x.value);}
   const filer=new Map();for(const id in per){const mp=per[id];const v=mp['RCFD'+base]??mp['RCON'+base]??mp['RCFN'+base];if(v!=null)filer.set(+id,v);}
   let all=0;for(const v of filer.values())all+=v;entSortVals.set('ALL',all);
   for(const t in TYPES){let s=0,any=false;for(const r2 of TYPES[t])if(filer.has(r2)){s+=filer.get(r2);any=true;}if(any)entSortVals.set('ET:'+t,s);}
   for(const [r2,v] of filer)entSortVals.set('BANK:'+r2,v);
   for(const n in peers){let s=0,any=false;for(const r2 of peers[n])if(filer.has(r2)){s+=filer.get(r2);any=true;}if(any)entSortVals.set('PEER:'+n,s);}
 }catch(e){}entSortField=field;}
async function renderEntList(){const field=document.getElementById('entsort').value;await computeSortVals(field);
 const desc=document.getElementById('entdesc').checked,filt=document.getElementById('entfilter').value,q=document.getElementById('entsearch').value.trim().toLowerCase();
 // showmerged: lineage not available for FFIEC 002 — toggle has no visible effect
 const wlSet=loadWL();
 const pool=[{id:'ALL',label:'ALL',cat:'agg'}];
 for(const t in TYPES)pool.push({id:'ET:'+t,label:'ALL '+t,cat:'agg'});
 for(const [rssd,r] of ROSTER)pool.push({id:'BANK:'+rssd,label:`${r.nm} (${rssd}${r.ty?', '+r.ty:''})`,cat:'bank'});
 for(const n in peers)pool.push({id:'PEER:'+n,label:'★ '+n,cat:'peer'});
 const rows=[];for(const p of pool){if(filt==='charted'){if(!active.some(a=>a.id===p.id))continue;}else if(filt==='watchlist'){if(!wlSet.has(p.id))continue;}else if(filt!=='all'&&p.cat!==filt)continue;
   if(q&&!(p.label.toLowerCase().includes(q)||p.id.toLowerCase().includes(q)))continue;
   let sv;if(field==='name')sv=p.label.toLowerCase();else if(field==='rssd'){const m=p.id.match(/(\d+)/);sv=m?+m[1]:(desc?-Infinity:Infinity);}
   else sv=entSortVals.has(p.id)?entSortVals.get(p.id):(desc?-Infinity:Infinity);rows.push({...p,sv});}
 rows.sort((a,b)=>typeof a.sv==='string'?(desc?b.sv.localeCompare(a.sv):a.sv.localeCompare(b.sv)):(desc?b.sv-a.sv:a.sv-b.sv));
 {const et=document.getElementById('tabEnts');if(et)et.textContent=`Entities (${rows.length.toLocaleString()})`;}
 const cont=document.getElementById('entlistpanel');
 cont.innerHTML=rows.slice(0,800).map(r=>{const val=(field==='name')?'':(field==='rssd'?(r.id.match(/(\d+)/)?r.id.match(/(\d+)/)[1]:''):(entSortVals.has(r.id)?fmtUnit(entSortVals.get(r.id),false):''));
   const isOn=active.some(a=>a.id===r.id);const isWL=wlSet.has(r.id);
   return `<div class="erow${r.cat==='agg'?' agg':''}${isOn?' on':''}" data-id="${r.id}" data-label="${r.label.replace(/"/g,'&quot;')}"><span class="en">${r.label}</span><span class="ev">${val}</span> <span class="pp">＋peer</span><span class="rpt" title="Open entity report">📋</span><span class="ewl${isWL?' on':''}" title="Toggle watchlist">★</span></div>`;}).join('')||'<p class="muted" style="padding:8px">none match</p>';
 cont.querySelectorAll('.erow').forEach(el=>{const id=el.dataset.id,label=el.dataset.label;
   const addChart=()=>{if(!active.find(a=>a.id===id))active.push({id,label});renderChips();scheduleRecompute();};
   el.querySelector('.en').onclick=addChart;el.querySelector('.ev').onclick=addChart;
   el.querySelector('.pp').onclick=ev=>{ev.stopPropagation();if(!id.startsWith('BANK:')){showToast('Peer members must be filers.');return;}const rssd=+id.slice(5);if(!peerMembers.find(a=>a.rssd===rssd))peerMembers.push({rssd,label});renderPeerBuilder();document.getElementById('peerbox').open=true;};
   el.querySelector('.rpt').onclick=ev=>{ev.stopPropagation();if(id.startsWith('BANK:'))openReport(id);};
   el.querySelector('.ewl').onclick=ev=>{ev.stopPropagation();const wl2=loadWL();if(wl2.has(id)){wl2.delete(id);ev.currentTarget.classList.remove('on');}else{wl2.add(id);ev.currentTarget.classList.add('on');}saveWL(wl2);if(document.getElementById('entfilter').value==='watchlist')renderEntList();};});}
let entFloating=false;
function switchTab(items){
 if(entFloating&&!items){dockEnts();return;}          // clicking Entities while floating re-docks it
 document.getElementById('panelItems').style.display=items?'flex':'none';
 if(!entFloating)document.getElementById('panelEnts').style.display=items?'none':'flex';
 document.getElementById('tabItems').classList.toggle('on',items);document.getElementById('tabEnts').classList.toggle('on',!items);
 if(!items)renderEntList();}
function detachEnts(){const p=document.getElementById('panelEnts');entFloating=true;p.classList.add('entfloat');p.style.display='flex';
 document.getElementById('panelItems').style.display='flex';
 document.getElementById('tabItems').classList.add('on');document.getElementById('tabEnts').classList.remove('on');
 document.getElementById('entdetach').textContent='⧈ Dock';renderEntList();}
function dockEnts(){const p=document.getElementById('panelEnts');entFloating=false;p.classList.remove('entfloat');p.style.cssText='';
 document.getElementById('entdetach').textContent='⧉ Detach';
 document.getElementById('panelItems').style.display='none';document.getElementById('panelEnts').style.display='flex';
 document.getElementById('tabItems').classList.remove('on');document.getElementById('tabEnts').classList.add('on');renderEntList();}

// ---- compute + draw ----
const _assetRows=new Map();
let _rcSeq=0,_rcTimer=null;
function scheduleRecompute(){clearTimeout(_rcTimer);_rcTimer=setTimeout(recompute,60);}
async function recompute(){if(!measures.length||!active.length){lastSeries=[];Qall=[];draw();return;}
 const mySeq=++_rcSeq;
 const skW=n=>`<div style="height:14px;border-radius:3px;background:linear-gradient(90deg,var(--head,#eef2f7) 25%,var(--bg2,#f7f9fb) 50%,var(--head,#eef2f7) 75%);background-size:200% 100%;animation:skshimmer 1.2s infinite;width:${n}%;margin-bottom:6px"></div>`;
 if(!document.getElementById('skstyle')){const ss=document.createElement('style');ss.id='skstyle';ss.textContent='@keyframes skshimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}';document.head.appendChild(ss);}
 const pEl=document.getElementById('panes'),cEl=document.getElementById('cards');
 if(pEl)pEl.innerHTML=`<div style="padding:24px 16px">${skW(90)}${skW(75)}${skW(85)}${skW(60)}</div>`;
 if(cEl)cEl.innerHTML=`<div style="padding:10px 0">${skW(55)}${skW(40)}${skW(48)}</div>`;
 const out=[];let ci=0;
 for(const m of measures)for(const e of active){if(mySeq!==_rcSeq)return;const rows=await seriesFor(e.id,m.code);if(mySeq!==_rcSeq)return;out.push({label:`${e.label} · ${fullCap(m.code)||m.label}`,pct:m.pct,rows,color:COLORS[ci++%COLORS.length],eid:e.id});}
 lastSeries=out;const qs=new Set();for(const s of out)for(const r of s.rows)qs.add(r[0]);
 _assetRows.clear();for(const e of active){if(mySeq!==_rcSeq)return;const ar=await seriesFor(e.id,'RCFD2170');_assetRows.set(e.id,Object.fromEntries(ar.map(r=>[r[0],r[1]])));}
 Qall=[...qs].sort();rangeSel={a:0,b:Math.max(0,Qall.length-1)};syncSlider();draw();stateToHash();}
function syncSlider(){const n=Qall.length,w=document.getElementById('sliderwrap');if(n<2){w.style.display='none';return;}w.style.display='flex';
 for(const id of['r0','r1']){const el=document.getElementById(id);el.min=0;el.max=n-1;}
 document.getElementById('r0').value=rangeSel.a;document.getElementById('r1').value=rangeSel.b;
 document.getElementById('rfrom').value=Qall[rangeSel.a];document.getElementById('rto').value=Qall[rangeSel.b];
 const dl=document.getElementById('qlist');dl.innerHTML=Qall.map(q=>`<option value="${q}">`).join('');}
function onSlide(){let a=+document.getElementById('r0').value,b=+document.getElementById('r1').value;rangeSel={a:Math.min(a,b),b:Math.max(a,b)};
 document.getElementById('rfrom').value=Qall[rangeSel.a];document.getElementById('rto').value=Qall[rangeSel.b];draw();}
function draw(){const host=document.getElementById('panes');
 if(!lastSeries.length){host.innerHTML='<p class="muted">Pick an entity, then click a line item on the left.</p>';document.getElementById('cards').innerHTML='';document.getElementById('tbl').innerHTML='';return;}
 const win=Qall.slice(rangeSel.a,rangeSel.b+1),ws=new Set(win);
 const normOn=document.getElementById('normbyassets')&&document.getElementById('normbyassets').checked;
 const workSeries=normOn?lastSeries.map(s=>{if(s.pct)return s;const am=_assetRows.get(s.eid)||{};const norm=s.rows.map(([q,v])=>{const a=am[q];return [q,v!=null&&a&&a!==0?100*v/a:null];});return {...s,rows:norm,pct:true,label:s.label+' / assets %'};}).map(s=>({...s})):lastSeries;
 const groups=[['$ thousands',workSeries.filter(s=>!s.pct)],['percent',workSeries.filter(s=>s.pct)]];let html='';
 let dualAxis=window._dualAxis||false;
 if(!window._axisRight)window._axisRight=new Set();
 const hasDol=workSeries.some(s=>!s.pct),hasPct=workSeries.some(s=>s.pct);
 if(hasDol&&hasPct){
   const axisUI=dualAxis?workSeries.map((s,i)=>`<label style="font-size:10px;white-space:nowrap;margin-right:6px"><input type="checkbox" class="ax-right" data-i="${i}" ${window._axisRight.has(s.label)?'checked':''}> <span style="color:${s.color}">${(s.label||'').slice(0,30)}</span> → right</label>`).join(''):'';
   html+=`<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><button class="sec pane-toggle" id="axistoggle">${dualAxis?'⊞ Split panes':'⊟ Dual axis'}</button>${axisUI}</div>`;
   if(dualAxis){const leftS=workSeries.filter(s=>!window._axisRight.has(s.label));const rightS=workSeries.filter(s=>window._axisRight.has(s.label));const lFilt=leftS.length?leftS:workSeries.filter(s=>!s.pct);const rFilt=rightS.length?rightS:workSeries.filter(s=>s.pct);html+=paneDual(lFilt.map(s=>({...s,rows:s.rows.filter(r=>ws.has(r[0]))})),rFilt.map(s=>({...s,rows:s.rows.filter(r=>ws.has(r[0]))})),win);}
   else{for(const [unit,arr] of groups){if(!arr.length)continue;const w=arr.map(s=>({...s,rows:s.rows.filter(r=>ws.has(r[0]))}));html+=pane(w,unit==='percent',unit,win);}}}
 else{for(const [unit,arr] of groups){if(!arr.length)continue;const w=arr.map(s=>({...s,rows:s.rows.filter(r=>ws.has(r[0]))}));html+=pane(w,unit==='percent',unit,win);}}
 if(document.getElementById('idx')&&document.getElementById('idx').checked){const dol=lastSeries.filter(s=>!s.pct);
   if(dol.length){const w=dol.map(s=>{const rw=s.rows.filter(r=>ws.has(r[0]));let bb;if(_idxBase){bb=rw.find(r=>r[0]===_idxBase&&r[1]!=null&&r[1]!==0)||rw.find(r=>r[1]!=null&&r[1]!==0);}else{bb=rw.find(r=>r[1]!=null&&r[1]!==0);}const b=bb&&bb[1];return {...s,rows:b?rw.map(([q,v])=>[q,v==null?null:100*v/b]):[]};});const baseLbl=_idxBase?` (base: ${_idxBase})`:'';html+=`<div class="idx-pane"><div style="font-size:10px;color:var(--muted,#9aa3b2);padding:2px 14px">Index to 100${baseLbl} — click chart to rebase${_idxBase?` · <a href="#" id="idxbasereset" style="color:var(--muted,#9aa3b2)">reset</a>`:''}`;html+=pane(w,false,'index',win);html+=`</div>`;}}
 if(document.getElementById('qoqdelta')&&document.getElementById('qoqdelta').checked){const dol=lastSeries.filter(s=>!s.pct);
   if(dol.length){const w=dol.map(s=>{const rw=s.rows.filter(r=>ws.has(r[0]));const qm=Object.fromEntries(s.rows.map(r=>[r[0],r[1]]));const dd=rw.map((r,i)=>{const pQ=prevQtr(r[0]);const pv=pQ in qm?qm[pQ]:null;return [r[0],r[1]!=null&&pv!=null?r[1]-pv:null];}).filter(r=>r[1]!=null);return {...s,rows:dd,pct:false};});html+=pane(w,false,'$ thousands',win);}}
 host.innerHTML=html;
 if(window._pinnedQ){document.querySelectorAll(`#panes .qband[data-q="${window._pinnedQ}"]`).forEach(g=>g.classList.add('qband-pinned'));}
 if(lastSeries.length>0&&!lastSeries.some(s=>s.rows.some(r=>ws.has(r[0])))){host.innerHTML+=`<div style="text-align:center;padding:16px 8px 4px;font-size:13px;color:var(--muted,#9aa3b2)">No data available in the selected date range — try expanding the range or selecting <b>All</b>.</div>`;}
 const atb=document.getElementById('axistoggle');if(atb)atb.onclick=()=>{window._dualAxis=!window._dualAxis;draw();};
 document.querySelectorAll('.ax-right').forEach(cb=>cb.onchange=()=>{const s=workSeries[+cb.dataset.i];if(!s)return;if(cb.checked)window._axisRight.add(s.label);else window._axisRight.delete(s.label);draw();});
 const kpiSelEl=document.getElementById('kpisel'),kpiSelRow=document.getElementById('kpiselrow');
 if(lastSeries.length>1){kpiSelRow.style.display='';const pv=kpiSelEl.value;kpiSelEl.innerHTML=lastSeries.map((s,i)=>`<option value="${i}">${s.label||s.id||('Series '+(i+1))}</option>`).join('');if(pv&&+pv<lastSeries.length)kpiSelEl.value=pv;}else{kpiSelRow.style.display='none';kpiSelEl.innerHTML='';}
 const kpiIdx=lastSeries.length>1?(+kpiSelEl.value||0):0;
 const prim={...lastSeries[kpiIdx],rows:lastSeries[kpiIdx].rows.filter(r=>ws.has(r[0]))};
 // MEDIUM-2: date-based QoQ/YoY (not positional — gaps/lineage hand-offs cause mislabeled quarters).
 const primR=prim.rows,last=primR.length?primR[primR.length-1][1]:null,lastQ=primR.length?primR[primR.length-1][0]:null;
 const qmapObj=Object.fromEntries(primR.map(r=>[r[0],r[1]]));
 const pQ=lastQ?prevQtr(lastQ):null,yQ=lastQ?yoyQtr(lastQ):null;
 const prev=(pQ&&pQ in qmapObj)?qmapObj[pQ]:null,yr=(yQ&&yQ in qmapObj)?qmapObj[yQ]:null;
 const f0=primR.length?primR[0][1]:null,f0q=primR.length?primR[0][0]:null;
 // LOW-2: suppress sign-flip % deltas (e.g. loss→profit looks like a decline at -150%).
 const sameSign=(a,b)=>(a>=0)===(b>=0);
 const pctChg=(a,b)=>(a!=null&&b!=null&&b!==0&&sameSign(a,b))?100*(a/b-1):null;
 const qoq=pctChg(last,prev),yoy=pctChg(last,yr),tot=pctChg(last,f0);
 const cls=x=>x==null?'':(x>=0?'up':'dn'),ar=x=>x==null?'—':((x>=0?'▲ ':'▼ ')+Math.abs(x).toFixed(1)+'%');
 const qoqRaw=last!=null&&prev!=null?last-prev:null,yoyRaw=last!=null&&yr!=null?last-yr:null,totRaw=last!=null&&f0!=null?last-f0:null;
 const absChg=(d)=>{if(d==null)return '';const s=d>=0?'+':'−';const a=Math.abs(d);if(prim.pct)return `${s}${a.toFixed(2)} pp`;if(a>=1e9)return `${s}${(a/1e6).toLocaleString(undefined,{maximumFractionDigits:0})} B`;if(a>=1e6)return `${s}${(a/1e3).toLocaleString(undefined,{maximumFractionDigits:0})} M`;return `${s}${a.toLocaleString()} k`;};
 const hasAgg=active.some(a=>a.id==='ALL'||a.id.startsWith('PEER:')||a.id.startsWith('ET:'));
 const aggNote=hasAgg?`<div style="font-size:11px;color:#d97706;padding:4px 0 2px" title="Dollar figures for ALL/peer/type-group entities are Σ of individual filer values — ratios (%) are Σnumerator/Σdenominator, not averages">⚠ Aggregate view — $ values are sums across filers; ratios are population-weighted</div>`:'';
 document.getElementById('cards').innerHTML=
  aggNote+
  `<div class=card><div class=k>${prim.label} — latest${lastQ?` (${lastQ})`:''}</div><div class=v>${fmtUnit(last,prim.pct)}</div></div>`+
  `<div class=card><div class=k>QoQ${pQ&&prev!=null?' vs '+pQ:''}</div><div class="v ${cls(qoq)}">${ar(qoq)}</div>${qoq!=null?`<div class="muted" style="font-size:11px;margin-top:2px">${absChg(qoqRaw)}</div>`:''}</div>`+
  `<div class=card><div class=k>YoY${yQ&&yr!=null?' vs '+yQ:''}</div><div class="v ${cls(yoy)}">${ar(yoy)}</div>${yoy!=null?`<div class="muted" style="font-size:11px;margin-top:2px">${absChg(yoyRaw)}</div>`:''}</div>`+
  `<div class=card><div class=k>Total Δ (range${f0q?' from '+f0q:''})</div><div class="v ${cls(tot)}">${ar(tot)}</div>${tot!=null?`<div class="muted" style="font-size:11px;margin-top:2px">${absChg(totRaw)}</div>`:''}</div>`+
  `<div class=card><div class=k>Series</div><div class=v>${lastSeries.length}</div></div>`;
 const maps=lastSeries.map(s=>Object.fromEntries(s.rows));
 const head=['quarter_end',...lastSeries.map(s=>s.label)];
 const body=win.map(q=>[q,...maps.map((mp,i)=>mp[q]==null?'':(lastSeries[i].pct?+mp[q].toFixed(3):mp[q]))]);
 let h='<table><tr>'+head.map(x=>`<th>${x}</th>`).join('')+'</tr>';
 for(const r of body)h+='<tr>'+r.map((x,i)=>`<td>${i>=1&&typeof x==='number'?Number(x).toLocaleString():x}</td>`).join('')+'</tr>';
 document.getElementById('tbl').innerHTML=h+'</table>';window._exp={head,body};
 const snapEl=document.getElementById('snapshot');
 if(lastSeries.length>1&&snapEl){
  const fmtDelta=(d,isPct)=>{if(d==null)return '';const sg=d>=0?'+':'−';const a=Math.abs(d);if(isPct)return `${sg}${a.toFixed(2)} pp`;if(a>=1e9)return `${sg}${(a/1e6).toLocaleString(undefined,{maximumFractionDigits:0})} B`;if(a>=1e6)return `${sg}${(a/1e3).toLocaleString(undefined,{maximumFractionDigits:0})} M`;return `${sg}${a.toLocaleString()} k`;};
  const snapRows=lastSeries.map(s=>{const sR=s.rows.filter(r=>ws.has(r[0]));const sLast=sR.length?sR[sR.length-1][1]:null,sLastQ=sR.length?sR[sR.length-1][0]:null;const sMap=Object.fromEntries(sR.map(r=>[r[0],r[1]]));const sPQ=sLastQ?prevQtr(sLastQ):null,sYQ=sLastQ?yoyQtr(sLastQ):null;const sPrev=(sPQ&&sPQ in sMap)?sMap[sPQ]:null,sYr=(sYQ&&sYQ in sMap)?sMap[sYQ]:null;const sF0=sR.length?sR[0][1]:null;const sQoq=pctChg(sLast,sPrev),sYoy=pctChg(sLast,sYr),sTot=pctChg(sLast,sF0);const sQR=sLast!=null&&sPrev!=null?sLast-sPrev:null,sYR=sLast!=null&&sYr!=null?sLast-sYr:null,sTR=sLast!=null&&sF0!=null?sLast-sF0:null;return {s,sLast,sQoq,sYoy,sTot,sQR,sYR,sTR};});
  let sh=`<table style="width:100%;margin-top:8px;border-collapse:collapse;font-size:12px"><thead><tr><th style="text-align:left;padding:3px 6px">Entity</th><th style="padding:3px 6px">Latest</th><th style="padding:3px 6px">QoQ</th><th style="padding:3px 6px">YoY</th><th style="padding:3px 6px">Total Δ</th></tr></thead><tbody>`;
  for(const {s,sLast,sQoq,sYoy,sTot,sQR,sYR,sTR} of snapRows){const dot=`<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${s.color};margin-right:5px"></span>`;sh+=`<tr><td style="text-align:left;padding:3px 6px">${dot}${s.label}</td><td style="padding:3px 6px;text-align:right">${fmtUnit(sLast,s.pct)}</td><td class="${cls(sQoq)}" style="padding:3px 6px;text-align:right">${ar(sQoq)}${sQR!=null?` <span class="muted" style="font-size:10px">${fmtDelta(sQR,s.pct)}</span>`:''}</td><td class="${cls(sYoy)}" style="padding:3px 6px;text-align:right">${ar(sYoy)}${sYR!=null?` <span class="muted" style="font-size:10px">${fmtDelta(sYR,s.pct)}</span>`:''}</td><td class="${cls(sTot)}" style="padding:3px 6px;text-align:right">${ar(sTot)}${sTR!=null?` <span class="muted" style="font-size:10px">${fmtDelta(sTR,s.pct)}</span>`:''}</td></tr>`;}
  snapEl.innerHTML=sh+'</tbody></table>';
 }else if(snapEl){snapEl.innerHTML='';} }
function pane(series,pct,unit,win){const W=1080,H=300,pad=64,n=win.length;const xi=Object.fromEntries(win.map((q,i)=>[q,i]));
 let mn=Infinity,mx=-Infinity;for(const s of series)for(const r of s.rows){mn=Math.min(mn,r[1]);mx=Math.max(mx,r[1]);}
 if(!isFinite(mn)){const aC=DK()?'#9aa3b2':'#5a6478';return `<svg viewBox="0 0 1080 300" width="100%" xmlns="http://www.w3.org/2000/svg"><text x="540" y="150" font-size="16" fill="${aC}" text-anchor="middle" dominant-baseline="middle">No data available for this entity / date range</text></svg>`;}
 // Anchor $ and % charts to a zero baseline; index charts keep their own scale.
 if(unit==='$ thousands'&&mn>0)mn=0;
 if(unit==='percent'){if(mn>0)mn=0;if(mx<0)mx=0;}
 if(mn===mx){mx=mn+1;}
 const rg=(mx-mn)||1;
 const X=i=>pad+i*(W-2*pad)/Math.max(1,n-1),Y=v=>H-pad-(v-mn)/rg*(H-2*pad);
 const f=v=>unit==='percent'?v.toFixed(2)+'%':unit==='index'?v.toFixed(0):fmtUnit(v,false);
 const gC=DK()?'#243044':'#eef2f7',aC=DK()?'#9aa3b2':'#5a6478',tC=DK()?'#e6e9ef':'#14213d';
 // gridlines at min / mid / max, with a distinct zero line whenever 0 falls inside the range
 const ticks=[...new Set([mn,(mn+mx)/2,mx])];
 let tk=ticks.map(v=>`<line x1="${pad}" y1="${Y(v)}" x2="${W-pad}" y2="${Y(v)}" stroke="${gC}"></line><text x="8" y="${Y(v)+4}" font-size="11" fill="${aC}">${f(v)}</text>`).join('');
 if(mn<0&&mx>0){const zC=DK()?'#6b7689':'#9aa3b2';tk+=`<line x1="${pad}" y1="${Y(0)}" x2="${W-pad}" y2="${Y(0)}" stroke="${zC}" stroke-width="1.5"></line><text x="8" y="${Y(0)+4}" font-size="11" fill="${zC}">${unit==='percent'?'0%':'0'}</text>`;}
 const recC=DK()?'rgba(217,119,6,0.09)':'rgba(217,119,6,0.07)';
 for(const [rs,re,rl] of RECESSIONS){const i0=win.findIndex(q=>q>=rs);const i1=win.reduceRight((a,q,i)=>a<0&&q<=re?i:a,-1);if(i0<0||i1<0||i0>i1)continue;const rx=X(i0),rx2=X(i1);tk+=`<rect x="${rx.toFixed(1)}" y="${pad}" width="${Math.max(2,rx2-rx).toFixed(1)}" height="${H-2*pad}" fill="${recC}"></rect><text x="${((rx+rx2)/2).toFixed(1)}" y="${pad-3}" font-size="8" fill="#d97706" text-anchor="middle" opacity=".7">${rl}</text>`;}
 if(_reflineVal!=null&&_reflineVal>=mn&&_reflineVal<=mx){const ry=Y(_reflineVal).toFixed(1);tk+=`<line x1="${pad}" y1="${ry}" x2="${W-pad}" y2="${ry}" stroke="#e07a1f" stroke-width="1.5" stroke-dasharray="5 3"></line><text x="${pad+4}" y="${+ry-4}" font-size="9" fill="#e07a1f">${_reflineLbl||_reflineVal}</text>`;}
 const dotC=DK()?'#0f1825':'#fff';
 const byQ={};   // win-index -> {x, q, items:[{cy,color,label,val}]} for nearest-X hover snapping
 let areas='',paths='',pts='',slbls='',_el=[];for(const s of series){let p='',firstCx,lastCx,lastCy;s.rows.forEach((r,k)=>{const cx=X(xi[r[0]]).toFixed(1),cy=Y(r[1]).toFixed(1);if(k===0)firstCx=cx;lastCx=cx;lastCy=cy;p+=(k?'L':'M')+cx+' '+cy+' ';
   const qi=xi[r[0]];(byQ[qi]=byQ[qi]||{x:+cx,q:r[0],items:[]}).items.push({cy:+cy,color:s.color,label:s.label,val:f(r[1])});
   pts+=`<circle class="pt" cx="${cx}" cy="${cy}" r="1.5" fill="${s.color}" stroke="${dotC}" stroke-width="1"></circle>`;});
   if(s.rows.length>1){const by=Y(Math.max(mn,0)).toFixed(1);areas+=`<path d="${p}L${lastCx} ${by} L${firstCx} ${by} Z" fill="${s.color}" fill-opacity="0.12" stroke="none"></path>`;}
   paths+=`<path d="${p}" fill="none" stroke="${s.color}" stroke-width="2"></path>`;
   if(lastCx!=null){const pts2=s.label.split(' \xb7 ');const nE=active.length,nM=measures.length;const sl=(nE>1&&nM===1?pts2[0]:(nE===1&&nM>1?short(pts2.slice(1).join(' \xb7 ')):short(s.label))).slice(0,22);_el.push({x:+lastCx+5,y:+lastCy+4,sl:sl,color:s.color});}}
 // Nearest-X hover bands: each quarter owns a full-height transparent rect spanning the midpoints
 // to its neighbors, so hovering ANYWHERE in that vertical band (any distance, any height) snaps
 // the marker(s) + tooltip to that quarter. Pure SVG+CSS so it is instant. Multi-series: every
 // series with a point at the quarter gets its own marker and a line in the shared tooltip.
 const _bi=Object.keys(byQ).map(Number).sort((a,b)=>a-b); let bands='';
 _bi.forEach((qi,k)=>{const Q=byQ[qi],xc=Q.x;
   const left=k===0?0:(byQ[_bi[k-1]].x+xc)/2, right=k===_bi.length-1?W:(xc+byQ[_bi[k+1]].x)/2;
   let mk=`<line class="reveal" x1="${xc.toFixed(1)}" y1="${pad}" x2="${xc.toFixed(1)}" y2="${H-pad}" stroke="${aC}" stroke-width="1" stroke-dasharray="2 2"></line>`;
   for(const it of Q.items)mk+=`<circle class="reveal" cx="${xc.toFixed(1)}" cy="${it.cy.toFixed(1)}" r="4" fill="${it.color}" stroke="${dotC}" stroke-width="1.5"></circle>`;
   bands+=`<g class="qband" data-q="${Q.q}"><rect class="hit" x="${left.toFixed(1)}" y="0" width="${(right-left).toFixed(1)}" height="${H}"></rect>${mk}</g>`;});
 const want=Math.min(8,n),ix=[...new Set(Array.from({length:want},(_,k)=>Math.round(k*(n-1)/Math.max(1,want-1))))];
 const lb=ix.map(i=>{const a=i===0?'start':(i===n-1?'end':'middle');return `<text x="${X(i)}" y="${H-pad+18}" font-size="10" fill="${aC}" text-anchor="${a}">${win[i]}</text>`;}).join('');
 _el.sort((a,b)=>a.y-b.y);for(let _i=1;_i<_el.length;_i++){if(_el[_i].y<_el[_i-1].y+11)_el[_i].y=_el[_i-1].y+11;}const _ov=_el.length?Math.max(0,_el[_el.length-1].y-(H-4)):0;slbls=_el.map(e=>`<text x="${e.x.toFixed(1)}" y="${(e.y-_ov).toFixed(1)}" font-size="9" fill="${e.color}" font-weight="600">${e.sl}</text>`).join('');
 return `<svg viewBox="0 0 ${W+96} ${H}" width="100%" xmlns="http://www.w3.org/2000/svg">${tk}${areas}${paths}${pts}${slbls}${lb}<text x="14" y="16" font-size="11" fill="${tC}">${unit==='$ thousands'?'$':unit}</text>${bands}</svg>`;}
function exportSeries(){if(!window._exp){showToast('Nothing to export.');return;}dl2(window._exp.head,window._exp.body,'series');}
function exportChartSVG(){const svgs=[...document.querySelectorAll('#panes svg')];if(!svgs.length){showToast('No chart to export.');return;}let y=0;const bg=DK()?'#0f1825':'#fff';const gs=svgs.map(s=>{const vb=(s.getAttribute('viewBox')||'0 0 1080 300').split(' ').map(Number);const H=vb[3]||300;const g=`<g transform="translate(0,${y})">${s.innerHTML}</g>`;y+=H+8;return g;});const total=Math.max(y-8,1);const svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 ${total}" width="1080" height="${total}"><rect width="1080" height="${total}" fill="${bg}"/>${gs.join('')}</svg>`;const a=document.createElement('a');a.href='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);a.download='chart.svg';a.click();}
function paneDual(dol,pct,win){const W=1080,H=300,pad=64,padR=80,n=win.length;const xi=Object.fromEntries(win.map((q,i)=>[q,i]));
 let mn0=Infinity,mx0=-Infinity;for(const s of dol)for(const r of s.rows){mn0=Math.min(mn0,r[1]);mx0=Math.max(mx0,r[1]);}
 let mn1=Infinity,mx1=-Infinity;for(const s of pct)for(const r of s.rows){mn1=Math.min(mn1,r[1]);mx1=Math.max(mx1,r[1]);}
 if(!isFinite(mn0)&&!isFinite(mn1))return '';
 if(mn0>0)mn0=0;if(mn1>0)mn1=0;if(mn0===mx0)mx0=mn0+1;if(mn1===mx1)mx1=mn1+1;
 const rg0=(mx0-mn0)||1,rg1=(mx1-mn1)||1;
 const X=i=>pad+i*(W-pad-padR)/Math.max(1,n-1);
 const Y0=v=>H-pad-(v-mn0)/rg0*(H-2*pad);const Y1=v=>H-pad-(v-mn1)/rg1*(H-2*pad);
 const f0=v=>fmtUnit(v,false),f1=v=>(+v).toFixed(2)+'%';
 const gC=DK()?'#243044':'#eef2f7',aC=DK()?'#9aa3b2':'#5a6478',tC=DK()?'#e6e9ef':'#14213d';
 const ticks0=[mn0,(mn0+mx0)/2,mx0],ticks1=[mn1,(mn1+mx1)/2,mx1];
 let tk=ticks0.map(v=>`<line x1="${pad}" y1="${Y0(v)}" x2="${W-padR}" y2="${Y0(v)}" stroke="${gC}"></line><text x="8" y="${Y0(v)+4}" font-size="11" fill="${aC}">${f0(v)}</text>`).join('');
 tk+=ticks1.map(v=>`<text x="${W-padR+4}" y="${Y1(v)+4}" font-size="11" fill="${aC}">${f1(v)}</text>`).join('');
 const dotC=DK()?'#0f1825':'#fff';
 let areas='',paths='',pts='',slbls='',_el=[];
 const render=(arr,Yf,fmt)=>{for(const s of arr){let p='',firstCx,lastCx,lastCy;s.rows.forEach((r,k)=>{const cx=X(xi[r[0]]).toFixed(1),cy=Yf(r[1]).toFixed(1);if(k===0)firstCx=cx;lastCx=cx;lastCy=cy;p+=(k?'L':'M')+cx+' '+cy+' ';
   pts+=`<circle class="pt" cx="${cx}" cy="${cy}" r="1.5" fill="${s.color}" stroke="${dotC}" stroke-width="1"></circle>`;});
   if(s.rows.length>1){const by=Yf(Math.max(mn0,mn1,0)).toFixed(1);areas+=`<path d="${p}L${lastCx} ${by} L${firstCx} ${by} Z" fill="${s.color}" fill-opacity="0.12" stroke="none"></path>`;}
   paths+=`<path d="${p}" fill="none" stroke="${s.color}" stroke-width="2"></path>`;
   if(lastCx!=null){const pts2=s.label.split(' \xb7 ');const nE=active.length,nM=measures.length;const sl=(nE>1&&nM===1?pts2[0]:(nE===1&&nM>1?short(pts2.slice(1).join(' \xb7 ')):short(s.label))).slice(0,22);_el.push({x:+lastCx+5,y:+lastCy+4,sl:sl,color:s.color});}}};
 render(dol,Y0,f0);render(pct,Y1,f1);
 const want=Math.min(8,n),ix=[...new Set(Array.from({length:want},(_,k)=>Math.round(k*(n-1)/Math.max(1,want-1))))];
 const lb=ix.map(i=>`<text x="${X(i)}" y="${H-pad+18}" font-size="10" fill="${aC}" text-anchor="${i===0?'start':(i===n-1?'end':'middle')}">${win[i]}</text>`).join('');
 _el.sort((a,b)=>a.y-b.y);for(let _i=1;_i<_el.length;_i++){if(_el[_i].y<_el[_i-1].y+11)_el[_i].y=_el[_i-1].y+11;}const _ov=_el.length?Math.max(0,_el[_el.length-1].y-(H-4)):0;slbls=_el.map(e=>`<text x="${e.x.toFixed(1)}" y="${(e.y-_ov).toFixed(1)}" font-size="9" fill="${e.color}" font-weight="600">${e.sl}</text>`).join('');
 return `<svg viewBox="0 0 ${W+96} ${H}" width="100%" xmlns="http://www.w3.org/2000/svg"><text x="14" y="16" font-size="11" fill="${tC}">$ (left) \xb7 % (right)</text>${tk}${areas}${paths}${pts}${slbls}${lb}</svg>`;}

// ---- league / rank table ----
// NOTE (aggregation under review): per-filer values reuse the same coalesce(RCFD/RCON/RCFN)
// + sum-then-divide ratio logic as seriesFor(). Each league row is ONE filer (no cross-entity
// sum), but the ratio/coalesce pattern mirrors the engine logic currently being corrected in
// Y-9C — keep this structurally identical so that fix can be reconciled here too.
const LGMEAS=[
 {code:'COMB2170',label:'Total assets',pct:false},
 {code:'COMB2205',label:'Total deposits',pct:false},
 {code:'COMB2122',label:'Total loans',pct:false},
 {code:'COMB2944',label:'Net due TO related',pct:false},
 {code:'D_LOANSDEP',label:'Loans / Deposits %',pct:true},
 {code:'D_DEPASSETS',label:'Deposits / Assets %',pct:true},
 {code:'D_DUETO',label:'Net due TO related / Assets %',pct:true},
 {code:'D_NONCUR',label:'Noncurrent ratio %',pct:true},
];
let lgSortField='v',lgSortDir=-1;   // league sort: field v/qoq/yoy, dir 1=asc -1=desc
async function perFilerValues(measCode, quarters){
 // map: quarter -> Map(id_rssd -> per-filer value) for a COMB/raw code OR a DERIV ratio/sum
 const out={}; for(const q of quarters) out[q]=new Map();
 let d=DERIV[measCode]; if(!d&&measCode.startsWith('COMB'))d={type:'sum',plus:[measCode.slice(4)],minus:[],den:[]};
 if(d){const bases=[...d.plus,...(d.minus||[]),...(d.den||[])];
   const codes=[];for(const b of bases)for(const p of['RCFD','RCON','RCFN'])codes.push(p+b);
   const r=(await conn.query(`SELECT id_rssd,quarter_end,mdrm,value FROM t WHERE mdrm IN (${sqlList(codes)}) AND quarter_end IN (${sqlList(quarters)})`)).toArray();
   const byqf={}; for(const x of r){const q=String(x.quarter_end);(byqf[q]=byqf[q]||{});(byqf[q][x.id_rssd]=byqf[q][x.id_rssd]||{})[x.mdrm]=Number(x.value);}
   const acc=(mp,arr)=>{let s=0,seen=false;for(const b of arr){const v=coalesce(mp,b);if(v!=null){s+=v;seen=true;}}return [s,seen];};
   for(const q of quarters){const per=byqf[q]||{};
     for(const id in per){const mp=per[id];const [np,ns]=acc(mp,d.plus);const [nm,ms]=acc(mp,d.minus||[]);const num=np-nm;const [dp,ds]=acc(mp,d.den||[]);
       if(d.type==='sum'){if(ns||ms)out[q].set(+id,num);}else{if((ns||ms)&&ds&&dp>0)out[q].set(+id,100*num/dp);}}}
 } else {
   const r=(await conn.query(`SELECT id_rssd,quarter_end,SUM(value) v FROM t WHERE mdrm='${measCode}' AND quarter_end IN (${sqlList(quarters)}) GROUP BY id_rssd,quarter_end`)).toArray();
   for(const x of r) out[String(x.quarter_end)].set(Number(x.id_rssd), Number(x.v));
 }
 return out;}
async function renderLeague(){
 const meas=LGMEAS[+document.getElementById('lgmeasure').value];
 const q=document.getElementById('lgquarter').value, topn=+document.getElementById('lgtopn').value;
 const prevQ=prevQtr(q), yoyQ=yoyQtr(q);
 const quarters=[q,prevQ,yoyQ].filter(Boolean);
 document.getElementById('leaguebody').innerHTML='<p class="muted">Computing…</p>';
 const bkt=document.getElementById('lgbucket').value;
 const qi=ALLQ.indexOf(q);const spkQs=qi>=0?ALLQ.slice(Math.max(0,qi-7),qi+1):[];
 const allFetchQs=[...new Set([...quarters,...spkQs])];
 const [vals,avals]=await Promise.all([perFilerValues(meas.code,allFetchQs),bkt?perFilerValues('RCFD2170',[q]):Promise.resolve(null)]);
 const assetMap=avals?avals[q]||new Map():null;
 const cur=vals[q]||new Map();
 const spkFn=rssd=>{const pts=spkQs.map(sq=>vals[sq]?vals[sq].get(rssd):undefined).filter(v=>v!=null&&!isNaN(v));if(pts.length<2)return '';const mn2=Math.min(...pts),mx2=Math.max(...pts),rng=mx2-mn2||1;const W2=56,H2=20,pad2=2;const xs=pts.map((_,i)=>(pad2+i*(W2-2*pad2)/(pts.length-1)).toFixed(1));const ys=pts.map(v=>(H2-pad2-(v-mn2)/rng*(H2-2*pad2)).toFixed(1));const poly=xs.map((x,i)=>`${x},${ys[i]}`).join(' ');const lc=DK()?'#4ade80':'#1b7f3b';return `<svg width="${W2}" height="${H2}" style="vertical-align:middle"><polyline points="${poly}" fill="none" stroke="${lc}" stroke-width="1.5"></polyline></svg>`;};
 let rows=[...cur.entries()].map(([rssd,v])=>{const pv=prevQ?vals[prevQ].get(rssd):null, yv=yoyQ?vals[yoyQ].get(rssd):null;
   const qoq=meas.pct?(pv!=null?v-pv:null):(pv?100*(v/pv-1):null);
   const yoy=meas.pct?(yv!=null?v-yv:null):(yv?100*(v/yv-1):null);
   return {rssd,name:(ROSTER.get(rssd)&&ROSTER.get(rssd).nm)||String(rssd),v,qoq,yoy};});
 if(assetMap&&bkt){const lo=bkt==='-'?0:(+bkt)*1e9,hi=bkt==='-'?1e8:(+bkt)*1e10;rows=rows.filter(r=>{const a=assetMap.get(r.rssd);return a!=null&&a>=lo&&(bkt==='-'?a<1e8:a<hi);});}
 rows.sort((a,b)=>{const av=a[lgSortField],bv=b[lgSortField];   // nulls always last
   if(av==null&&bv==null)return 0;if(av==null)return 1;if(bv==null)return -1;return lgSortDir*(av-bv);});
 const valSorted=rows.filter(r=>r.v!=null).sort((a,b)=>b.v-a.v);const nm=valSorted.length;
 const pctileMap=new Map(valSorted.map((r,i)=>[r.rssd,nm>1?Math.round(100*(nm-1-i)/(nm-1)):50]));
 const show=topn?rows.slice(0,topn):rows;
 const fmtV=v=>v==null?'—':(meas.pct?(+v).toFixed(2)+'%':fmtUnit(v,false));
 const fmtD=x=>x==null?'—':(meas.pct?((x>=0?'+':'')+x.toFixed(2)+' pp'):((x>=0?'▲ ':'▼ ')+Math.abs(x).toFixed(1)+'%'));
 const cls=x=>x==null?'':(x>=0?'up':'dn');
 const arr=f=>lgSortField===f?(lgSortDir<0?' ▼':' ▲'):'';
 const pcClr=pc=>pc>=75?'color:#1b7f3b':pc<25?'color:#c0392b':'';
 const ETCLR={IBF:'#6b46c1',BRANCH:'#2b6cb0',AGENCY:'#0f766e',BANK:'#1b7f3b'};
 const etBadge=ty=>{if(!ty)return '';const c=ETCLR[ty]||'#6b7280';return `<span style="font-size:9px;padding:1px 4px;border-radius:3px;background:${c};color:#fff;margin-left:4px;vertical-align:middle">${ty}</span>`;};
 let h=`<table><tr><th>#</th><th style="text-align:left">Filer</th>`+
   `<th class="lgs" data-f="v" style="cursor:pointer" title="click to sort">${meas.label}${arr('v')}</th>`+
   `<th class="lgs" data-f="qoq" style="cursor:pointer" title="click to sort">QoQ${arr('qoq')}</th>`+
   `<th class="lgs" data-f="yoy" style="cursor:pointer" title="click to sort">YoY${arr('yoy')}</th>`+
   `<th title="Percentile rank by value this quarter — 99th = top 1%">Pctile</th>`+
   `<th title="8-quarter trend">Trend</th></tr>`;
 show.forEach((r,i)=>{const pc=pctileMap.get(r.rssd);const on=active.some(a=>a.id===`BANK:${r.rssd}`);const ty=(ROSTER.get(r.rssd)||{}).ty||'';h+=`<tr${on?' class="lgon-row"':''}><td>${i+1}</td><td class="lglink${on?' lgon':''}" data-id="BANK:${r.rssd}" data-nm="${r.name.replace(/"/g,'&quot;')}" style="text-align:left;cursor:pointer;text-decoration:underline dotted" title="${on?'In chart':'Click to add to chart'}">${r.name} <span style="color:#9aa3b2">(${r.rssd})</span>${etBadge(ty)}${on?' <span style="font-size:10px;color:#1b7f3b">✓</span>':''}</td><td>${fmtV(r.v)}</td><td class="${cls(r.qoq)}">${fmtD(r.qoq)}</td><td class="${cls(r.yoy)}">${fmtD(r.yoy)}</td><td style="${pcClr(pc)}">${pc!=null?pc+'th':'—'}</td><td>${spkFn(r.rssd)}</td></tr>`;});
 h+=`</table><p class="muted">${show.length} of ${rows.length} filers · ${q}${meas.pct?' · QoQ/YoY in percentage points':''} · click a name to add to chart · click a header to sort</p>`;
 const body=document.getElementById('leaguebody'); body.innerHTML=h; window._lg={meas,q,rows:show,pctileMap};
 body.querySelectorAll('.lgs').forEach(th=>th.onclick=()=>{const f=th.dataset.f;if(lgSortField===f)lgSortDir*=-1;else{lgSortField=f;lgSortDir=-1;}renderLeague();});
 body.querySelectorAll('.lglink').forEach(td=>{td.onclick=()=>{const id=td.dataset.id,nm=td.dataset.nm;if(!active.find(a=>a.id===id))active.push({id,label:nm});renderChips();scheduleRecompute();};});}
async function openLeague(){
 const msel=document.getElementById('lgmeasure');
 if(!msel.options.length) msel.innerHTML=LGMEAS.map((m,i)=>`<option value="${i}">${m.label}</option>`).join('');
 const qsel=document.getElementById('lgquarter');
 if(!qsel.options.length){qsel.innerHTML=ALLQ.map(q=>`<option>${q}</option>`).join(''); if(ALLQ.length)qsel.value=ALLQ[ALLQ.length-1];}
 document.getElementById('leaguemodal').style.display='flex'; await renderLeague();}

// ---- call-report view ----
function renderFentChips(){const c=document.getElementById('fent-chips');if(!c)return;const ents=window._feEnts||[];c.innerHTML=ents.map((ent,i)=>`<span style="display:inline-flex;align-items:center;gap:2px;padding:2px 5px;background:var(--head,#eef2f7);border-radius:3px;font-size:11px">${ent.label}<span class="fent-del" data-i="${i}" style="cursor:pointer;color:#c0392b;margin-left:3px">×</span></span>`).join('');for(const d of document.querySelectorAll('.fent-del'))d.onclick=()=>{(window._feEnts||[]).splice(+d.dataset.i,1);renderFentChips();renderForm();};}
function fentCond(){const ents=window._feEnts||[];if(!ents.length)return null;const rs=new Set();for(const ent of ents){if(ent.id==='ALL')return '1=1';if(ent.id.startsWith('ET:'))for(const r of(TYPES[ent.id.slice(3)]||[]))rs.add(r);else if(ent.id.startsWith('BANK:'))rs.add(+ent.id.slice(5));else if(ent.id.startsWith('PEER:'))for(const r of(peers[ent.id.slice(5)]||[]))rs.add(r);}return rs.size?`id_rssd IN (${[...rs].join(',')})`:null;}
async function openForm(){if(!HIER){showToast('Hierarchy not loaded.');return;}
 const initE=active[0]||resolveEnt();if(!initE){showToast('Add an entity first.');return;}
 if(!window._feEnts||!window._feEnts.length){window._feEnts=active.length?active.filter(e=>e.id.startsWith('BANK:')||e.id.startsWith('PEER:')||e.id.startsWith('ET:')):[initE];}
 renderFentChips();
 const cond=fentCond()||scopeCond(initE.id);
 const qs=(await conn.query(`SELECT DISTINCT quarter_end FROM t WHERE ${cond} ORDER BY quarter_end`)).toArray().map(r=>String(r.quarter_end));
 window._fq=qs;const opt=qs.map(q=>`<option>${q}</option>`).join('');
 document.getElementById('ffrom').innerHTML=opt;document.getElementById('fto').innerHTML=opt;
 if(qs.length){document.getElementById('fto').value=qs[qs.length-1];document.getElementById('ffrom').value=qs[Math.max(0,qs.length-4)];}
 document.getElementById('formmodal').style.display='flex';renderForm();}
async function renderForm(){const fq=window._fq||[];const cond=fentCond();if(!cond)return;
 let lo=fq.indexOf(document.getElementById('ffrom').value),hi=fq.indexOf(document.getElementById('fto').value);
 if(lo<0)lo=0;if(hi<0)hi=fq.length-1;if(lo>hi){const t=lo;lo=hi;hi=t;}
 let cols=fq.slice(lo,hi+1);if(cols.length>16)cols=cols.slice(cols.length-16);const colsDesc=[...cols].reverse();
 const r=(await conn.query(`SELECT quarter_end,mdrm,SUM(value) v FROM t WHERE ${cond} AND quarter_end IN (${sqlList(cols)}) GROUP BY quarter_end,mdrm`)).toArray();
 const val={};for(const x of r){(val[x.mdrm]=val[x.mdrm]||{})[String(x.quarter_end)]=Number(x.v);}
 const body=document.getElementById('formbody');body.innerHTML='';window._fr=[];window._fcols=colsDesc;
 const hd=document.createElement('div');hd.className='frow';hd.style.cssText=`font-weight:700;position:sticky;top:0;z-index:2;background:${DK()?'#161e2b':'#fff'}`;
 hd.innerHTML=`<span class="lab">Item</span>`+colsDesc.map(q=>`<span class="vcell">${q.slice(0,7)}</span>`).join('');body.appendChild(hd);
 const keys=[...FORM_ORDER.filter(k=>HIER[k]),...Object.keys(HIER).filter(k=>SCHED_NAMES[k]&&!FORM_ORDER.includes(k))];
 for(const sch of keys){const items=HIER[sch].filter(rr=>REPORT.test(rr.mdrm)&&val[rr.mdrm]);if(!items.length)continue;
   const flat=items.map(rr=>({code:rr.mdrm,caption:rr.caption||rr.mdrm,num:rr.item||'',depth:rr.depth||1}));
   const {sec,rows}=mkSec(SCHED_NAMES[sch]||sch,items.length);body.appendChild(sec);renderFormNodes(rows,nest(flat),colsDesc,val);
   for(const rr of items)window._fr.push([sch,rr.item||'',rr.mdrm,rr.caption||rr.mdrm,...colsDesc.map(q=>(val[rr.mdrm]&&val[rr.mdrm][q])??'')]);}
 if(!window._fr.length)body.innerHTML='<p class=muted>No data for this entity/range.</p>';}
function renderFormNodes(container,nodes,colsDesc,val){for(const nd of nodes){const has=nd.children.length>0;
 const d=document.createElement('div');d.className='frow';d.dataset.depth=nd.depth;d.style.paddingLeft=(6+(nd.depth-1)*14)+'px';
 const car=has?`<span class="caret">▸</span>`:`<span class="caret" style="visibility:hidden">▸</span>`;
 const cells=colsDesc.map(q=>{const v=val[nd.code]&&val[nd.code][q];return `<span class="vcell">${v==null?'':Number(v).toLocaleString()}</span>`;}).join('');
 d.innerHTML=`<span class="lab">${car}${nd.num?`<b>${nd.num}</b> `:''}${nd.caption} <span style="color:#9aa3b2;font-size:11px">${nd.code}</span></span>${cells}`;
 d.querySelector('.caret').onclick=ev=>{ev.stopPropagation();if(has)toggleNode(d);};container.appendChild(d);
 if(has){const kids=document.createElement('div');kids.className='kids';kids.style.display='none';renderFormNodes(kids,nd.children,colsDesc,val);container.appendChild(kids);d._kids=kids;}}}
function exportForm(){if(!window._fr||!window._fr.length){showToast('Nothing to export.');return;}dl2(['schedule','item','mdrm','caption',...(window._fcols||[])],window._fr,'callreport');}

function dl2(c,rows,nm){if(!rows.length){showToast('Nothing to export.');return;}const e=v=>{v=v==null?'':String(v);return /[",\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v;};
 const lines=[c.join(',')].concat(rows.map(r=>r.map(e).join(',')));const bl=new Blob([lines.join('\n')],{type:'text/csv'});
 const a=document.createElement('a');a.href=URL.createObjectURL(bl);a.download='ffiec002_'+nm+'.csv';a.click();}
// ---- entity report (V2) ----
async function openReport(entityId){
 if(!entityId||!entityId.startsWith('BANK:'))return;
 const rssd=+entityId.slice(5);
 {const p=new URLSearchParams(location.hash.slice(1));p.set('report','1');history.replaceState(null,'','#'+p.toString());}
 document.getElementById('reportmodal').style.display='';
 document.getElementById('rpt-title').innerHTML=`${ROSTER.get(rssd)?.nm||String(rssd)} · RSSD ${rssd} <a href="https://www.ffiec.gov/nicpubweb/nicweb/InstitutionProfile.aspx?parID_RSSD=${rssd}&parDT_END=99991231" target="_blank" rel="noopener" style="font-size:11px;font-weight:400;color:inherit;opacity:0.55;text-decoration:none;margin-left:4px" title="FFIEC NIC institution profile">NIC ↗</a>`;
 {const ac=document.getElementById('rpt-addchart');const ae=bankEnt(rssd);const on=active.some(a=>a.id===ae.id);ac.textContent=on?'✓ In chart':'📈 Add to chart';ac.style.opacity=on?'0.5':'';ac.onclick=()=>{const e=bankEnt(rssd);if(!active.find(a=>a.id===e.id)){active.push({id:e.id,label:e.label});renderChips();scheduleRecompute();}ac.textContent='✓ In chart';ac.style.opacity='0.5';};}
 document.getElementById('rpt-asof').textContent='';
 document.getElementById('rptbody').innerHTML='<p class="muted" style="padding:20px">Loading…</p>';
 try{
  const qtrsRes=(await conn.query(`SELECT DISTINCT quarter_end FROM t WHERE id_rssd=${rssd} ORDER BY quarter_end DESC LIMIT 16`)).toArray();
  if(!qtrsRes.length){document.getElementById('rptbody').innerHTML='<p class="muted" style="padding:20px">No data for this entity.</p>';return;}
  const latestQ=qtrsRes[0].quarter_end;
  document.getElementById('rpt-asof').textContent=' · as of '+latestQ;
  document.getElementById('rptbody').innerHTML=await buildReport(rssd,latestQ,qtrsRes.map(r=>r.quarter_end).reverse());
 }catch(e){document.getElementById('rptbody').innerHTML='<p style="color:#c0392b;padding:20px">Report error: '+e+'</p>';}}
async function buildReport(rssd,latestQ,qtrs){
 const bases=['2170','2122','2205','2944','1403','1406','1407','3123'];
 const prfx=['RCFD','RCON','RCFN'];
 const kpiCodes=bases.flatMap(b=>prfx.map(p=>p+b));
 const qList=qtrs.map(q=>`'${q}'`).join(',');
 const cList=kpiCodes.map(c=>`'${c}'`).join(',');
 const data=(await conn.query(`SELECT mdrm,quarter_end,value FROM t WHERE id_rssd=${rssd} AND quarter_end IN (${qList}) AND mdrm IN (${cList})`)).toArray();
 const V={};for(const r of data)(V[r.mdrm]=V[r.mdrm]||{})[r.quarter_end]=Number(r.value);
 const getR=(base,q)=>{
  const rcfd=V['RCFD'+base]?.[q??latestQ],rcon=V['RCON'+base]?.[q??latestQ],rcfn=V['RCFN'+base]?.[q??latestQ];
  if(rcfd!=null)return rcfd;if(rcon!=null&&rcfn!=null)return rcon+rcfn;return rcon??rcfn??null;};
 const assets=getR('2170'),loans=getR('2122'),dep=getR('2205'),dueto=getR('2944');
 const npl30=getR('1403'),npl90=getR('1406'),nona=getR('1407');
 const npl=(npl30!=null||npl90!=null||nona!=null)?((npl30||0)+(npl90||0)+(nona||0)):null;
 const noncur=(npl90!=null||nona!=null)?((npl90||0)+(nona||0)):null;
 const alll=getR('3123');
 const nplRat=loans&&npl!=null&&loans>0?100*npl/loans:null;
 const noncurRat=loans&&noncur!=null&&loans>0?100*noncur/loans:null;
 const loanDep=loans&&dep&&dep>0?100*loans/dep:null;
 const duetoAssets=dueto&&assets&&assets>0?100*dueto/assets:null;
 const rescov=noncur&&alll!=null&&noncur>0?100*alll/noncur:null;
 const alllPct=loans&&alll!=null&&loans>0?100*alll/loans:null;
 let assetRank=null,assetCount=null;
 try{
  const rk=(await conn.query(`SELECT COUNT(*) n FROM t WHERE mdrm='RCFD2170' AND quarter_end='${latestQ}' AND value>=${assets??0}`)).toArray();
  const ct=(await conn.query(`SELECT COUNT(*) n FROM t WHERE mdrm='RCFD2170' AND quarter_end='${latestQ}'`)).toArray();
  assetRank=Number(rk[0]?.n??0);assetCount=Number(ct[0]?.n??0);
 }catch{}
 // Peer percentile bars (002 uses RCFD primary)
 const peerPctile={};
 try{
  const peerBases=['2170','2122','2205','2944','1403','3123'];
  for(const base of peerBases){const code='RCFD'+base;const ev=V[code]?.[latestQ];if(ev==null)continue;
   const res=(await conn.query(`SELECT COUNT(*) n FROM t WHERE mdrm='${code}' AND quarter_end='${latestQ}'`)).toArray();
   const tot=Number(res[0]?.n||0);if(!tot)continue;
   const lwr=(await conn.query(`SELECT COUNT(*) n FROM t WHERE mdrm='${code}' AND quarter_end='${latestQ}' AND value<=${ev}`)).toArray();
   peerPctile[base]=Math.round(100*Number(lwr[0]?.n||0)/tot);}
 }catch{}
 const prevQ=qtrs.length>=2?qtrs[qtrs.length-2]:null,yoyQ=qtrs.length>=5?qtrs[qtrs.length-5]:null;
 const pctD=(a,b)=>(a!=null&&b!=null&&b!==0)?100*(a-b)/b:null;
 const aQoQ=pctD(assets,prevQ?getR('2170',prevQ):null),aYoY=pctD(assets,yoyQ?getR('2170',yoyQ):null);
 const fA=v=>v==null?'—':v>=1e9?'$'+(v/1e9).toFixed(1)+'T':v>=1e6?'$'+(v/1e6).toFixed(1)+'B':'$'+Math.round(v/1e3)+'M';
 const fP=v=>v==null?'—':v.toFixed(2)+'%';
 const fD=v=>v==null?'':v>=0?`<span style="color:#1b7f3b;font-size:10px"> ▲${v.toFixed(1)}%</span>`:`<span style="color:#c0392b;font-size:10px"> ▼${Math.abs(v).toFixed(1)}%</span>`;
 const pct=assetRank&&assetCount?Math.round((1-assetRank/assetCount)*100):null;
 const rnk=assetRank?`Rank #${assetRank} of ${assetCount}${pct!=null?' ('+pct+'th %ile)':''}`:null;
 const nm=ROSTER.get(rssd)?.nm||String(rssd);
 const hdr=`<div style="border:1px solid var(--border,#ccc);border-radius:6px;padding:14px 18px;margin-bottom:14px;background:var(--head,#f7f8fc);color:var(--fg,#111)"><div style="font-size:20px;font-weight:700;color:var(--fg,#111)">${nm}</div><div class="muted" style="font-size:12px;margin-top:3px">RSSD ${rssd} · U.S. Branch/Agency of Foreign Bank · FFIEC 002</div><div style="font-size:13px;margin-top:7px;color:var(--fg,#111)">As of ${latestQ}${assets!=null?' &nbsp;·&nbsp; Total assets: '+fA(assets):''}${rnk?' &nbsp;·&nbsp; '+rnk:''}</div></div>`;
 // per-quarter helpers for sparklines and trend charts
 const nplQ=q=>{const l=getR('2122',q);const np=(getR('1403',q)||0)+(getR('1406',q)||0)+(getR('1407',q)||0);return l&&l>0?100*np/l:null;};
 const ncurQ=q=>{const l=getR('2122',q);const nc=(getR('1406',q)||0)+(getR('1407',q)||0);return l&&l>0?100*nc/l:null;};
 const dtaQ=q=>{const a=getR('2170',q),d=getR('2944',q);return a&&a>0&&d!=null?100*d/a:null;};
 const ldQ=q=>{const l=getR('2122',q),d=getR('2205',q);return l&&d&&d>0?100*l/d:null;};
 const pctileBar=(p)=>{if(p==null)return '';const c=p>=75?'#1b7f3b':p>=50?'#2980b9':p>=25?'#e67e22':'#c0392b';return `<div style="margin-top:4px"><div style="height:5px;background:var(--border,#e0e4ea);border-radius:3px;overflow:hidden"><div style="height:100%;width:${p}%;background:${c};border-radius:3px"></div></div><div style="font-size:9px;color:var(--fg2,#888);margin-top:1px">${p}th %ile among reporters</div></div>`;};
 const kpis=[
  {lbl:'Total Assets',val:fA(assets),spk:sparkline(qtrs.map(q=>[q,getR('2170',q)]),false,COLORS[0]),qoq:aQoQ,yoy:aYoY,pc:peerPctile['2170']},
  {lbl:'Total Loans',val:fA(loans),spk:sparkline(qtrs.map(q=>[q,getR('2122',q)]),false,COLORS[1]),qoq:null,yoy:null,pc:peerPctile['2122']},
  {lbl:'Total Deposits',val:fA(dep),spk:sparkline(qtrs.map(q=>[q,getR('2205',q)]),false,COLORS[2]),qoq:null,yoy:null,pc:peerPctile['2205']},
  {lbl:'Net Due TO Related',val:fA(dueto),spk:sparkline(qtrs.map(q=>[q,getR('2944',q)]),false,COLORS[3]),qoq:null,yoy:null,pc:peerPctile['2944']},
  {lbl:'Loans / Deposits',val:fP(loanDep),spk:sparkline(qtrs.map(q=>[q,ldQ(q)]),true,COLORS[4]),qoq:null,yoy:null,pc:null},
  {lbl:'Due-to / Assets',val:fP(duetoAssets),spk:sparkline(qtrs.map(q=>[q,dtaQ(q)]),true,COLORS[5]),qoq:null,yoy:null,pc:null},
  {lbl:'NPL Ratio',val:fP(nplRat),spk:sparkline(qtrs.map(q=>[q,nplQ(q)]),true,COLORS[6]),qoq:null,yoy:null,pc:peerPctile['1403']},
  {lbl:'Noncurrent Ratio',val:fP(noncurRat),spk:sparkline(qtrs.map(q=>[q,ncurQ(q)]),true,COLORS[7]),qoq:null,yoy:null,pc:null},
 ];
 const cards=kpis.map(k=>`<div style="border:1px solid var(--border,#ccc);border-radius:6px;padding:10px 14px;min-width:148px;display:inline-block;vertical-align:top;margin:4px"><div style="font-size:10px;color:var(--fg2,#666);font-weight:600;letter-spacing:.3px;text-transform:uppercase">${k.lbl}</div><div style="font-size:26px;font-weight:700;line-height:1.1;margin-top:4px">${k.val}</div><div style="min-height:14px;margin-top:2px">${fD(k.qoq)}${k.yoy!=null?' &nbsp;YoY:'+fD(k.yoy):''}</div>${k.spk||''}${pctileBar(k.pc)}</div>`).join('');
 const kpiSec=`<h3 style="font-size:13px;font-weight:600;margin:0 0 6px">Key Metrics — as of ${latestQ}</h3><div style="margin-bottom:14px">${cards}</div>`;
 // reserve coverage panel
 const resSec=alll!=null?`<div style="display:inline-block;vertical-align:top;border:1px solid var(--border,#ccc);border-radius:6px;padding:10px 14px;min-width:240px;margin-bottom:14px"><div style="font-size:12px;font-weight:600;margin-bottom:6px">Allowance / Reserve Coverage</div><table style="font-size:12px;border-collapse:collapse;width:100%"><tr><td style="padding:3px 0">ALLL / Total Loans</td><td style="text-align:right;font-weight:700">${fP(alllPct)}</td></tr><tr><td style="padding:3px 0">ALLL / Noncurrent Loans</td><td style="text-align:right;font-weight:700">${fP(rescov)}</td></tr><tr><td style="padding:3px 0">Noncurrent Loans</td><td style="text-align:right;font-weight:700">${noncur!=null?fA(noncur):'—'}</td></tr></table></div>`:'';
 // trend small-multiples — 2×2 grid (002 has no income statement)
 const mkS=(rows,color,lbl)=>({rows:rows.filter(r=>r[1]!=null),color,label:lbl,pct:false});
 const trends=[
  {t:'Total Assets',s:[mkS(qtrs.map(q=>[q,getR('2170',q)]),COLORS[0],'Assets')],u:'$ thousands'},
  {t:'Loans & Deposits',s:[mkS(qtrs.map(q=>[q,getR('2122',q)]),COLORS[1],'Loans'),mkS(qtrs.map(q=>[q,getR('2205',q)]),COLORS[2],'Deposits')],u:'$ thousands'},
  {t:'Balance Sheet Structure (%)',s:[mkS(qtrs.map(q=>[q,ldQ(q)]),COLORS[4],'Loans/Dep'),mkS(qtrs.map(q=>[q,dtaQ(q)]),COLORS[5],'Due-to/Assets')],u:'percent'},
  {t:'Credit Quality (%)',s:[mkS(qtrs.map(q=>[q,nplQ(q)]),COLORS[6],'NPL %'),mkS(qtrs.map(q=>[q,ncurQ(q)]),COLORS[7],'Noncurrent %')],u:'percent'},
 ];
 const trendCells=trends.map(t=>{if(!t.s.some(s=>s.rows.length>0))return '';const svg=pane(t.s,false,t.u,qtrs);return svg?`<div style="min-width:0"><div style="font-size:11px;font-weight:600;color:var(--fg2,#666);margin-bottom:3px">${t.t}</div>${svg}</div>`:''}).filter(Boolean);
 const trendSec=trendCells.length?`<h3 style="font-size:13px;font-weight:600;margin:14px 0 6px">Trends — last ${qtrs.length} quarters</h3><div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px">${trendCells.join('')}</div>`:'';
 const nar=buildNarrative({nm,latestQ,assets,assetRank,assetCount,aQoQ,aYoY,nplRat,noncurRat,rescov,loanDep,duetoAssets});
 return hdr+kpiSec+resSec+trendSec+`<h3 style="font-size:13px;font-weight:600;margin:14px 0 6px">Summary</h3>`+nar;}
function sparkline(rows,pct,color){
 const W=120,H=40;if(!rows||rows.every(r=>r[1]==null))return '';
 const vals=rows.map(r=>r[1]).filter(v=>v!=null);if(!vals.length)return '';
 let mn=Math.min(...vals),mx=Math.max(...vals);if(mn===mx){mn-=1;mx+=1;}
 if(!pct&&mn>0)mn=0;const rg=mx-mn,n=rows.length;
 const X=i=>4+i*(W-8)/Math.max(1,n-1),Y=v=>H-4-(v-mn)/rg*(H-8);
 const filtered=rows.filter(r=>r[1]!=null);
 const pts=filtered.map((r,i)=>`${X(rows.indexOf(r)).toFixed(1)},${Y(r[1]).toFixed(1)}`).join(' ');
 if(!pts)return '';
 const lp=filtered[filtered.length-1],li=rows.indexOf(lp);
 const fill=`4,${H-4} ${pts} ${X(li).toFixed(1)},${H-4}`;
 return `<svg width="120" height="40" style="display:block;margin-top:4px"><polygon points="${fill}" fill="${color||COLORS[0]}" fill-opacity=".12"/><polyline points="${pts}" fill="none" stroke="${color||COLORS[0]}" stroke-width="1.5"/></svg>`;}
function buildNarrative(d){
 const {nm,latestQ,assets,assetRank,assetCount,aQoQ,aYoY,nplRat,noncurRat,rescov,loanDep,duetoAssets}=d;
 const fA=v=>v==null?null:v>=1e9?'$'+(v/1e9).toFixed(1)+'T':v>=1e6?'$'+(v/1e6).toFixed(1)+'B':'$'+Math.round(v/1e3)+'M';
 const fP=v=>v==null?null:v.toFixed(2)+'%';
 const pct=assetRank&&assetCount?Math.round((1-assetRank/assetCount)*100):null;
 const grTxt=aYoY!=null?(aYoY>5?` Assets grew ${aYoY.toFixed(1)}% year-over-year.`:aYoY<-5?` Assets contracted ${Math.abs(aYoY).toFixed(1)}% year-over-year.`:' Asset levels were stable year-over-year.'):'';
 const p1=`${nm} is a U.S. branch/agency of a foreign bank with ${fA(assets)||'undisclosed assets'} as of ${latestQ}${assetRank?`, ranking #${assetRank} of ${assetCount} FFIEC 002 filers${pct!=null?' ('+pct+'th percentile)':''}`:''}.${grTxt}`;
 const ldTxt=loanDep!=null?` Loans-to-deposits stood at ${fP(loanDep)}.`:'';
 const dtTxt=duetoAssets!=null?` Net due-to related offices represented ${fP(duetoAssets)} of total assets.`:'';
 const p2=(ldTxt||dtTxt)?ldTxt+dtTxt:null;
 const nplD=nplRat==null?null:nplRat<1?'clean credit quality':nplRat<2?'manageable credit stress':nplRat<3?'elevated NPL levels':'significant credit deterioration';
 const resD=rescov==null?null:rescov<50?'thin reserve coverage':rescov<100?'adequate reserve coverage':'strong reserve coverage';
 const p3p=[];
 if(nplD&&nplRat!=null)p3p.push(`${nm} reported a total NPL ratio of ${fP(nplRat)}, indicating ${nplD}.`);
 if(resD&&rescov!=null)p3p.push(`The allowance for loan losses covered ${fP(rescov)} of noncurrent loans, reflecting ${resD}.`);
 const p3=p3p.join(' ')||null;
 return [p1,p2,p3].filter(Boolean).map(p=>`<p style="line-height:1.6;margin:6px 0">${p}</p>`).join('');}
function rptPrint(){
 const content=document.getElementById('rptbody').innerHTML;
 const title=document.getElementById('rpt-title').textContent;
 const w=window.open('','_blank','width=900,height=700');if(!w)return;
 w.document.write('<!doctype html><html><head><meta charset="utf-8"><title>'+title+' Tear Sheet<\/title><style>*{box-sizing:border-box}:root{--border:#ccc;--head:#f7f8fc;--fg2:#555}.muted{color:#555}body{font-family:-apple-system,Segoe UI,sans-serif;font-size:12px;color:#1a202c;margin:24px 32px}svg{display:block}h3{font-size:13px;margin:12px 0 4px}p{margin:6px 0}@media print{body{margin:0}}<\/style><\/head><body>'+content+'<p style="margin-top:32px;font-size:10px;color:#888">Data: public FFIEC\/FRB filings · Generated '+new Date().toISOString().slice(0,10)+'<\/p><script>window.onload=()=>window.print();<\/script><\/body><\/html>');
 w.document.close();}
// ---- export builder (V1) ----
const _eb={entities:[],scope:'all',scheds:new Set(),codes:new Set(),fromQ:null,toQ:null,fmt:'long'};
function ebScheduleCodes(){
 if(!HIER)return [];
 const out=new Set();
 for(const sch of _eb.scheds)for(const r of (HIER[sch]||[]))if(REPORT.test(r.mdrm))out.add(r.mdrm);
 return [...out];}
function ebRawCodes(){
 const out=new Set();
 for(const c of _eb.codes){const d=DERIV[c];
   if(d){for(const base of [...(d.plus||[]),...(d.minus||[]),...(d.den||[])])for(const p of['RCFD','RCON','RCFN'])out.add(p+base);}
   else out.add(c);}
 return [...out];}
function ebEntityCond(){
 if(!_eb.entities.length)return null;
 if(_eb.entities.some(e=>e.id==='ALL'))return '1=1';
 const rssds=new Set();
 for(const ent of _eb.entities){
   if(ent.id.startsWith('BANK:'))rssds.add(+ent.id.slice(5));
   else if(ent.id.startsWith('PEER:')){for(const r of peers[ent.id.slice(5)]||[])rssds.add(r);}
   else if(ent.id.startsWith('ET:')){for(const r of TYPES[ent.id.slice(3)]||[])rssds.add(r);}
 }
 return rssds.size?`id_rssd IN (${[...rssds].join(',')})`:null;}
function pivotWide(rows){
 const captionMap={};
 if(HIER)for(const sch of Object.keys(HIER))for(const r of HIER[sch])if(r.mdrm&&r.caption)captionMap[r.mdrm]=r.caption;
 const qtrs=[...new Set(rows.map(r=>String(r.quarter_end)))].sort().reverse();
 const ents=[...new Set(rows.map(r=>r.id_rssd))];
 const byE={};for(const r of rows){const k=r.id_rssd;if(!byE[k])byE[k]={nm:r.institution_name,m:{}};(byE[k].m[r.mdrm]=byE[k].m[r.mdrm]||{})[String(r.quarter_end)]=r.value;}
 const body=[];for(const eid of ents){if(!byE[eid])continue;for(const m of Object.keys(byE[eid].m).sort())body.push([eid,byE[eid].nm||'',m,fullCap(m)||captionMap[m]||'',...qtrs.map(q=>byE[eid].m[m][q]??'')]);}
 return {headers:['id_rssd','institution_name','mdrm','caption',...qtrs],body};}
async function ebEstimate(){
 let nC=0;
 if(_eb.scope==='schedules')nC=ebScheduleCodes().length;
 else if(_eb.scope==='codes')nC=ebRawCodes().length;
 else try{const r=(await conn.query('SELECT COUNT(DISTINCT mdrm) n FROM t')).toArray();nC=Number(r[0]?.n||0);}catch{nC=0;}
 let nQ=0;
 if(_eb.fromQ&&_eb.toQ)try{const r=(await conn.query(`SELECT COUNT(DISTINCT quarter_end) n FROM t WHERE quarter_end>='${_eb.fromQ}' AND quarter_end<='${_eb.toQ}'`)).toArray();nQ=Number(r[0]?.n||0);}catch{}
 let nE=_eb.entities.length||0;
 if(_eb.entities.some(e=>e.id==='ALL'))try{const r=(await conn.query('SELECT COUNT(DISTINCT id_rssd) n FROM t')).toArray();nE=Number(r[0]?.n||0);}catch{}
 else if(nE>0){const rs=new Set();for(const ent of _eb.entities){if(ent.id.startsWith('BANK:'))rs.add(+ent.id.slice(5));else if(ent.id.startsWith('PEER:')){for(const r of peers[ent.id.slice(5)]||[])rs.add(r);}else if(ent.id.startsWith('ET:')){for(const r of TYPES[ent.id.slice(3)]||[])rs.add(r);}}if(rs.size)nE=rs.size;}
 const nR=nC*nQ*nE;const warn=nR>500000,block=nR>10000000;
 const el=document.getElementById('eb-estimate');
 if(el){el.innerHTML=`Estimated rows: <b>~${nR.toLocaleString()}</b> (${nC.toLocaleString()} codes × ${nQ} qtrs × ${nE} entities)`+(warn&&!block?' <span style="color:#e07a1f">⚠ large export</span>':'')+(block?' <span style="color:#c0392b">⛔ too large — narrow scope or date range first</span>':'');
   const btn=document.getElementById('expbld-run');if(btn)btn.disabled=block;}
 return nR;}
function openExportBuilder(){document.getElementById('exportmodal').style.display='flex';renderExportUI();}
async function renderExportUI(){
 const body=document.getElementById('expbldbody');body.innerHTML='<p class="muted">Loading…</p>';
 let allQtrs=[];
 try{
  const ec0=_eb.entities.length?ebEntityCond():null;
  const cond=ec0?`WHERE ${ec0}`:'';
  const res=(await conn.query(`SELECT DISTINCT quarter_end FROM t ${cond} ORDER BY quarter_end`)).toArray();
  allQtrs=res.map(r=>String(r.quarter_end));
 }catch{}
 if(allQtrs.length&&!_eb.fromQ)_eb.fromQ=allQtrs[0];
 if(allQtrs.length&&!_eb.toQ)_eb.toQ=allQtrs[allQtrs.length-1];
 const inRange=allQtrs.filter(q=>(!_eb.fromQ||q>=_eb.fromQ)&&(!_eb.toQ||q<=_eb.toQ));
 const selF=allQtrs.map(q=>`<option value="${q}"${q===_eb.fromQ?' selected':''}>${q}</option>`).join('');
 const selT=allQtrs.map(q=>`<option value="${q}"${q===_eb.toQ?' selected':''}>${q}</option>`).join('');
 const hierKeys=HIER?[...FORM_ORDER.filter(k=>HIER[k]),...Object.keys(HIER).filter(k=>SCHED_NAMES[k]&&!FORM_ORDER.includes(k))]:[];
 const schedHtml=hierKeys.map(sch=>{const cnt=(HIER[sch]||[]).filter(r=>REPORT.test(r.mdrm)).length;const chk=_eb.scheds.has(sch)?'checked':'';return `<label style="display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border:1px solid var(--border,#ccc);border-radius:4px;font-size:12px;cursor:pointer"><input type="checkbox" class="eb-sch" value="${sch}" ${chk}>${SCHED_NAMES[sch]||sch} <span class="muted" style="font-size:10px">(${cnt})</span></label>`;}).join(' ');
 const selCodes=[..._eb.codes].map(c=>`<span style="display:inline-flex;align-items:center;gap:2px;padding:1px 5px;background:var(--head,#eef2f7);border-radius:3px;font-size:11px;margin:2px">${c}<span class="eb-del" data-c="${c}" style="cursor:pointer;color:#c0392b;margin-left:2px">×</span></span>`).join('');
 body.innerHTML=`<div style="border:1px solid var(--border,#ccc);border-radius:6px;padding:10px 14px;margin-bottom:8px"><b>Entities</b> <span class="muted" style="font-size:11px">Add one or more banks, ALL filers, types, or peer groups</span>
  <div id="eb-ent-chips" style="display:flex;flex-wrap:wrap;gap:3px;min-height:26px;padding:4px;border:1px solid var(--border,#ccc);border-radius:3px;margin:6px 0 6px"></div>
  <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
   <input id="eb-ent" list="entlist" autocomplete="off" placeholder="bank name, RSSD, type (UFB…), or ★ peer-group…" style="flex:1;min-width:200px;font:inherit;font-size:12px;border:1px solid var(--border,#ccc);border-radius:3px;padding:3px 6px;background:inherit;color:inherit">
   <button id="eb-ent-add" class="sec">Add</button>
   <button id="eb-ent-cur" class="sec" title="Add entities currently in the chart">+ From chart</button>
   <button id="eb-ent-all" class="sec" title="Export all filing institutions">All filers</button>
   <span id="eb-ent-status" style="font-size:12px"></span>
  </div></div>
 <div style="border:1px solid var(--border,#ccc);border-radius:6px;padding:10px 14px;margin-bottom:8px"><b>Scope</b>
  <div style="margin-top:6px;display:flex;gap:16px;flex-wrap:wrap">
   <label style="display:inline-flex;align-items:flex-start;gap:5px;cursor:pointer"><input type="radio" name="eb-scope" value="all" ${_eb.scope==='all'?'checked':''}><span><b>All codes</b><br><span class="muted" style="font-size:11px">Every MDRM in site parquet</span></span></label>
   <label style="display:inline-flex;align-items:flex-start;gap:5px;cursor:pointer"><input type="radio" name="eb-scope" value="schedules" ${_eb.scope==='schedules'?'checked':''}><span><b>Selected schedules</b><br><span class="muted" style="font-size:11px">Choose by form schedule</span></span></label>
   <label style="display:inline-flex;align-items:flex-start;gap:5px;cursor:pointer"><input type="radio" name="eb-scope" value="codes" ${_eb.scope==='codes'?'checked':''}><span><b>Selected codes</b><br><span class="muted" style="font-size:11px">Custom MDRM / DERIV list</span></span></label>
  </div>
  <div id="eb-sched-panel" style="display:${_eb.scope==='schedules'?'block':'none'};margin-top:8px">
   <div style="display:flex;flex-wrap:wrap;gap:4px">${schedHtml}</div>
   <div style="margin-top:6px;display:flex;align-items:center;gap:8px"><button id="eb-sall" class="sec" style="font-size:11px;padding:2px 7px">All</button><button id="eb-snone" class="sec" style="font-size:11px;padding:2px 7px">None</button><span class="muted" style="font-size:11px" id="eb-sched-cnt">${_eb.scheds.size} schedule${_eb.scheds.size!==1?'s':''} / ${ebScheduleCodes().length} codes</span></div>
  </div>
  <div id="eb-code-panel" style="display:${_eb.scope==='codes'?'block':'none'};margin-top:8px">
   <div style="display:flex;gap:6px;align-items:center"><input id="eb-csearch" autocomplete="off" placeholder="Search MDRM or description…" style="flex:1;min-width:200px;font:inherit;font-size:12px;border:1px solid var(--border,#ccc);border-radius:3px;padding:3px 6px;background:inherit;color:inherit"><button id="eb-cadd" class="sec" style="font-size:11px;padding:2px 7px">Add</button><button id="eb-caddfil" class="sec" style="font-size:11px;padding:2px 7px">Add all matching</button></div>
   <div id="eb-cres" style="max-height:90px;overflow-y:auto;border:1px solid var(--border,#ccc);border-radius:3px;margin-top:4px;font-size:11px"></div>
   <div id="eb-selcodes" style="margin-top:6px;display:flex;flex-wrap:wrap">${selCodes}</div>
   <div style="margin-top:4px;display:flex;align-items:center;gap:8px"><span class="muted" style="font-size:11px" id="eb-code-cnt">${_eb.codes.size} code${_eb.codes.size!==1?'s':''} selected</span><button id="eb-clrall" class="sec" style="font-size:11px;padding:1px 7px">Clear all</button></div>
  </div>
 </div>
 <div style="border:1px solid var(--border,#ccc);border-radius:6px;padding:10px 14px;margin-bottom:8px"><b>Date range</b>
  <div style="display:flex;align-items:center;gap:8px;margin-top:6px;flex-wrap:wrap">
   <span class="muted">From</span><select id="eb-from" style="font:inherit;font-size:12px">${selF}</select>
   <span class="muted">to</span><select id="eb-to" style="font:inherit;font-size:12px">${selT}</select>
   <button id="eb-full" class="sec">Full range</button>
   <span class="muted" style="font-size:11px" id="eb-qcount">${inRange.length} quarter${inRange.length!==1?'s':''}</span>
  </div>
 </div>
 <div style="border:1px solid var(--border,#ccc);border-radius:6px;padding:10px 14px;margin-bottom:8px"><b>Format</b>
  <div style="margin-top:6px;display:flex;gap:16px;flex-wrap:wrap">
   <label style="display:inline-flex;align-items:flex-start;gap:5px;cursor:pointer"><input type="radio" name="eb-fmt" value="long" ${_eb.fmt==='long'?'checked':''}><span><b>Long</b><br><span class="muted" style="font-size:11px">One row per entity-quarter-code</span></span></label>
   <label style="display:inline-flex;align-items:flex-start;gap:5px;cursor:pointer"><input type="radio" name="eb-fmt" value="wide" ${_eb.fmt==='wide'?'checked':''}><span><b>Wide</b><br><span class="muted" style="font-size:11px">Codes as rows, quarters as columns (one column per quarter)</span></span></label>
  </div>
 </div>
 <div style="border:1px solid var(--border,#ccc);border-radius:6px;padding:8px 14px;font-size:12px" id="eb-estimate"><span class="muted">Set entity and scope to estimate row count.</span></div>`;
 function updSchedCnt(){const n=_eb.scheds.size,c=ebScheduleCodes().length;const el=document.getElementById('eb-sched-cnt');if(el)el.textContent=n+' schedule'+(n!==1?'s':'')+' / '+c+' codes';ebEstimate();}
 function updCodeCnt(){const n=_eb.codes.size;const el=document.getElementById('eb-code-cnt');if(el)el.textContent=n+' code'+(n!==1?'s':'')+' selected';ebEstimate();}
 function renderCodeTags(){document.getElementById('eb-selcodes').innerHTML=[..._eb.codes].map(c=>`<span style="display:inline-flex;align-items:center;gap:2px;padding:1px 5px;background:var(--head,#eef2f7);border-radius:3px;font-size:11px;margin:2px">${c}<span class="eb-del" data-c="${c}" style="cursor:pointer;color:#c0392b;margin-left:2px">×</span></span>`).join('');for(const d of document.querySelectorAll('.eb-del'))d.onclick=()=>{_eb.codes.delete(d.dataset.c);renderCodeTags();updCodeCnt();};}
 function buildCandidates(q){const q2=q.toLowerCase();const seen=new Set();const res=[];
  if(HIER)for(const sch of Object.keys(HIER))for(const r of (HIER[sch]||[])){if(!r.mdrm||seen.has(r.mdrm))continue;seen.add(r.mdrm);if((r.mdrm||'').toLowerCase().includes(q2)||(r.caption||'').toLowerCase().includes(q2))res.push({m:r.mdrm,c:r.caption||''});}
  for(const k of Object.keys(DERIV)){if(seen.has(k))continue;seen.add(k);const d=DERIV[k];if((k||'').toLowerCase().includes(q2)||(d.lbl||'').toLowerCase().includes(q2))res.push({m:k,c:d.lbl||''});}
  return res.slice(0,40);}
 function renderEbChips(){const c=document.getElementById('eb-ent-chips');if(!c)return;c.innerHTML=_eb.entities.map((ent,i)=>`<span style="display:inline-flex;align-items:center;gap:2px;padding:2px 6px;background:var(--head,#eef2f7);border-radius:3px;font-size:11px">${ent.id==='ALL'?'All filers':ent.label}<span class="eb-edel" data-i="${i}" style="cursor:pointer;color:#c0392b;margin-left:3px">×</span></span>`).join('');for(const d of document.querySelectorAll('.eb-edel'))d.onclick=()=>{_eb.entities.splice(+d.dataset.i,1);renderEbChips();ebEstimate();};}
 function addEbEnt(v){v=v.trim();if(!v)return;const cv=v.replace(/^★\s*/,'');
  if(/^all$/i.test(v)){_eb.entities=[{id:'ALL',label:'All filers'}];renderEbChips();ebEstimate();return;}
  if(cv in peers){const id='PEER:'+cv;if(!_eb.entities.find(e=>e.id===id))_eb.entities.push({id,label:'★ '+cv});renderEbChips();ebEstimate();return;}
  const et=v.match(/\b(UFB|USB|UFA|USA|IFB|ISB)\b/i);if(et){const id='ET:'+et[1].toUpperCase();if(!_eb.entities.find(e=>e.id===id))_eb.entities.push({id,label:'ALL '+et[1].toUpperCase()});renderEbChips();ebEstimate();return;}
  const m=v.match(/(\d{3,})/);if(m){const rid='BANK:'+m[1];if(!_eb.entities.find(e=>e.id===rid))_eb.entities.push({id:rid,label:elabel(rid)});renderEbChips();ebEstimate();return;}
  document.getElementById('eb-ent-status').innerHTML='<span style="color:#c0392b">Not recognised</span>';}
 document.getElementById('eb-ent-add').onclick=()=>{addEbEnt(document.getElementById('eb-ent').value);document.getElementById('eb-ent').value='';};
 document.getElementById('eb-ent').onkeydown=e=>{if(e.key==='Enter'){addEbEnt(e.target.value);e.target.value='';}};
 document.getElementById('eb-ent-cur').onclick=()=>{for(const e of active){if(!_eb.entities.find(x=>x.id===e.id))_eb.entities.push({id:e.id,label:e.label});}renderEbChips();ebEstimate();};
 document.getElementById('eb-ent-all').onclick=()=>{_eb.entities=[{id:'ALL',label:'All filers'}];renderEbChips();ebEstimate();};
 for(const el of document.querySelectorAll('[name=eb-scope]'))el.addEventListener('change',e=>{_eb.scope=e.target.value;document.getElementById('eb-sched-panel').style.display=_eb.scope==='schedules'?'block':'none';document.getElementById('eb-code-panel').style.display=_eb.scope==='codes'?'block':'none';ebEstimate();});
 for(const el of document.querySelectorAll('.eb-sch'))el.addEventListener('change',e=>{if(e.target.checked)_eb.scheds.add(e.target.value);else _eb.scheds.delete(e.target.value);updSchedCnt();});
 document.getElementById('eb-sall').onclick=()=>{for(const el of document.querySelectorAll('.eb-sch')){el.checked=true;_eb.scheds.add(el.value);}updSchedCnt();};
 document.getElementById('eb-snone').onclick=()=>{for(const el of document.querySelectorAll('.eb-sch')){el.checked=false;_eb.scheds.delete(el.value);}updSchedCnt();};
 document.getElementById('eb-csearch').oninput=function(){const q=this.value.trim();const el=document.getElementById('eb-cres');if(!q){el.innerHTML='';return;}const res=buildCandidates(q);el.innerHTML=res.length?res.map(r=>`<div class="eb-cand" data-m="${r.m}" style="padding:2px 6px;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${r.m}: ${r.c}"><b>${r.m}</b> ${r.c}</div>`).join(''):'<div class="muted" style="padding:4px 6px">No matches</div>';for(const d of el.querySelectorAll('.eb-cand'))d.onclick=()=>{_eb.codes.add(d.dataset.m);renderCodeTags();updCodeCnt();};};
 document.getElementById('eb-cadd').onclick=()=>{const v=document.getElementById('eb-csearch').value.trim().toUpperCase();if(!v)return;_eb.codes.add(v);renderCodeTags();updCodeCnt();};
 document.getElementById('eb-caddfil').onclick=()=>{const q=document.getElementById('eb-csearch').value.trim();if(!q)return;buildCandidates(q).forEach(r=>_eb.codes.add(r.m));renderCodeTags();updCodeCnt();};
 document.getElementById('eb-clrall').onclick=()=>{_eb.codes.clear();renderCodeTags();updCodeCnt();};
 for(const d of document.querySelectorAll('.eb-del'))d.onclick=()=>{_eb.codes.delete(d.dataset.c);renderCodeTags();updCodeCnt();};
 for(const el of document.querySelectorAll('[name=eb-fmt]'))el.addEventListener('change',e=>{_eb.fmt=e.target.value;});
 document.getElementById('eb-from').onchange=()=>{_eb.fromQ=document.getElementById('eb-from').value;const n=allQtrs.filter(q=>q>=_eb.fromQ&&q<=_eb.toQ).length;document.getElementById('eb-qcount').textContent=n+' quarter'+(n!==1?'s':'');ebEstimate();};
 document.getElementById('eb-to').onchange=()=>{_eb.toQ=document.getElementById('eb-to').value;const n=allQtrs.filter(q=>q>=_eb.fromQ&&q<=_eb.toQ).length;document.getElementById('eb-qcount').textContent=n+' quarter'+(n!==1?'s':'');ebEstimate();};
 document.getElementById('eb-full').onclick=()=>{if(allQtrs.length){_eb.fromQ=allQtrs[0];_eb.toQ=allQtrs[allQtrs.length-1];}renderExportUI();};
 renderEbChips();ebEstimate();}
async function runExport(preview=false){
 if(!_eb.entities.length){showToast('Add at least one entity first.');return null;}
 const ec=ebEntityCond();if(!ec){showToast('Could not resolve entities.');return null;}
 const df=_eb.fromQ?`AND quarter_end>='${_eb.fromQ}'`:'',dt=_eb.toQ?`AND quarter_end<='${_eb.toQ}'`:'';
 let mdrmF='';
 if(_eb.scope==='schedules'){const cs=ebScheduleCodes();if(!cs.length){showToast('No codes selected for the chosen schedules.');return null;}mdrmF=`AND mdrm IN (${cs.map(m=>`'${m}'`).join(',')}) `;}
 else if(_eb.scope==='codes'){const cs=ebRawCodes();if(!cs.length){showToast('No codes in selection.');return null;}mdrmF=`AND mdrm IN (${cs.map(m=>`'${m}'`).join(',')}) `;}
 const sql=`SELECT quarter_end,id_rssd,institution_name,mdrm,value FROM t WHERE ${ec} ${df} ${dt} ${mdrmF}ORDER BY mdrm,id_rssd,quarter_end${preview?' LIMIT 50':''}`;
 const rows=(await conn.query(sql)).toArray();
 if(_eb.fmt==='wide'&&!preview)return pivotWide(rows);
 return {headers:['quarter_end','id_rssd','institution_name','mdrm','caption','value'],body:rows.map(r=>[r.quarter_end,r.id_rssd,r.institution_name,r.mdrm,fullCap(r.mdrm)||'',r.value]),sql};}
async function runsql(){try{const r=(await conn.query(document.getElementById('sql').value)).toArray();
 sqlC=r.length?Object.keys(r[0]):[];sqlR=r.map(x=>sqlC.map(c=>x[c]));
 let h='<table><tr>'+sqlC.map(c=>`<th>${c}</th>`).join('')+'</tr>';for(const x of r.slice(0,500))h+='<tr>'+sqlC.map(c=>`<td>${x[c]}</td>`).join('')+'</tr>';
 document.getElementById('sqlout').innerHTML=h+`</table><p class=muted>${r.length} rows (first 500)</p>`;}catch(e){document.getElementById('sqlout').textContent='SQL error: '+e;}}
(function(){
  const tip=document.createElement('div');tip.id='charttip';document.body.appendChild(tip);
  let _hovQ=null,_hovTx=null,_hovTy=null;window._pinnedQ=null;
  function showTip(e,svg){
    if(!lastSeries.length){if(!window._pinnedQ)tip.style.display='none';return;}
    const win=Qall.slice(rangeSel.a,rangeSel.b+1);
    if(!win.length){if(!window._pinnedQ)tip.style.display='none';return;}
    if(window._pinnedQ)return;
    const br=svg.getBoundingClientRect();
    const vb=svg.viewBox.baseVal;const pad=64;const svgW=br.width;const W=vb.width;
    const mx=e.clientX-br.left;
    const frac=(mx-pad*svgW/W)/((svgW*(W-2*pad))/W);
    const qi=Math.max(0,Math.min(win.length-1,Math.round(frac*(win.length-1))));
    const q=win[qi];_hovQ=q;
    const qSvgX=pad+qi*(W-2*pad)/Math.max(1,win.length-1);
    const qScreenX=br.left+qSvgX*(svgW/W);
    const maps=lastSeries.map(s=>Object.fromEntries(s.rows));
    let html=`<div class="tip-q">${q}</div>`;
    for(let i=0;i<lastSeries.length;i++){const s=lastSeries[i];const v=maps[i][q];if(v==null)continue;
      const fv=s.pct?(+v).toFixed(2)+'%':fmtUnit(v,false);
      const tpts=s.label.split(' \xb7 ');const nE=active.length,nM=measures.length;const tl=(nE>1&&nM===1?tpts[0]:(nE===1&&nM>1?tpts.slice(1).join(' · '):s.label));
      html+=`<div class="tip-row"><span class="tip-sw" style="background:${s.color}"></span>${tl}: <b>${fv}</b></div>`;}
    html+=`<div style="font-size:10px;color:#9aa3b2;margin-top:3px;opacity:.6">click to pin</div>`;
    tip.innerHTML=html;tip.style.display='block';
    let tx=qScreenX+14;if(tx+tip.offsetWidth>window.innerWidth-8)tx=qScreenX-14-tip.offsetWidth;if(tx<8)tx=8;
    const ty=Math.max(8,Math.min(br.top+14,window.innerHeight-tip.offsetHeight-8));
    tip.style.left=tx+'px';tip.style.top=ty+'px';_hovTx=tx+'px';_hovTy=ty+'px';}
  document.getElementById('panes').addEventListener('pointermove',e=>{const svg=e.target.closest('svg');if(!svg){if(!window._pinnedQ)tip.style.display='none';return;}showTip(e,svg);});
  document.getElementById('panes').addEventListener('pointerleave',()=>{if(!window._pinnedQ)tip.style.display='none';});
  document.getElementById('panes').addEventListener('click',e=>{
    if(e.target.closest('#idxbasereset')){e.preventDefault();window._idxBase=null;draw();return;}
    const svg=e.target.closest('svg');if(!svg)return;
    const idxEl=document.getElementById('idx');
    if(idxEl&&idxEl.checked&&_hovQ&&svg.closest('.idx-pane')){window._idxBase=_hovQ;draw();return;}
    if(window._pinnedQ){
      window._pinnedQ=null;
      document.querySelectorAll('#panes .qband').forEach(g=>g.classList.remove('qband-pinned'));
      tip.style.display='none';
    }else if(_hovQ){
      window._pinnedQ=_hovQ;
      if(_hovTx){tip.style.left=_hovTx;tip.style.top=_hovTy;}
      const cur=tip.innerHTML;tip.innerHTML=cur.replace(/<div style="font-size:10px[^"]*"[^>]*>click to pin<\/div>/,'');
      tip.innerHTML+=`<div style="font-size:10px;color:#9aa3b2;margin-top:3px">📌 click to unpin</div>`;
      tip.style.display='block';
      document.querySelectorAll(`#panes .qband[data-q="${window._pinnedQ}"]`).forEach(g=>g.classList.add('qband-pinned'));
    }});
})();
init();
</script></body></html>"""
HTML=HTML.replace("__PARTS__", parts_js).replace("__BANKS__", BANKS_JSON).replace("__CREDIT_URL__", CREDIT_URL).replace("__BUILD_TS__", BUILD_TS).replace("__NODATA__", nodata_codes_js)
open(os.path.join(SITE,"index.html"),"w",encoding="utf-8").write(HTML)
print(f"wrote {SITE}/index.html and {len(PARTS)} parquet part(s)")
print("Upload site_002/'s index.html + ffiec002*.parquet + ffiec002_hierarchy.json")
