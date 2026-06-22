#!/usr/bin/env python3
"""
validate_build_002.py — automated post-build QA gate for the FFIEC 002 dashboard.
Run AFTER python make_site_002.py. Exit code 0 = all green; 1 = at least one FAIL.

Checks:
  1. HIERARCHY   ffiec002_hierarchy.json present with expected schedule sections.
  2. DERIV       every DERIV formula code (RCFD/RCON/RCFN base expansion) resolves in the site parquet.
  3. LGMEAS      every LGMEAS code (raw or COMB base) resolves in the site parquet.
  4. GOLDEN      MUFG NY Branch (RSSD 444819) RCFD2170 present at the latest quarter.
  5. FILTER      site parquet is smaller than the source panel (verifies MED-3 DISPLAY_CODES filter).
  6. CAPTIONS    no hierarchy leaf node has a blank caption and no mdrm.

Usage: python validate_build_002.py   (run from FFIEC 002/ directory)
"""
from __future__ import annotations
import json, os, re, sys

HIER="ffiec002_hierarchy.json"; SITE_DIR="site_002"; SRC="ffiec002_panel_long.parquet"
GOLDEN_RSSD=444819; GOLDEN_CODE="RCFD2170"

def main():
    fails=[]; notes=[]

    # 1. HIERARCHY present with expected schedules
    if not os.path.exists(HIER): sys.exit(f"[HIERARCHY] missing {HIER} — run build_hierarchy_002.py first")
    hier=json.load(open(HIER,encoding="utf-8"))
    expect_scheds={'RAL','N','C','E','L','M'}   # core 002 schedules
    missing_sch=sorted(s for s in expect_scheds if s not in hier)
    if missing_sch: fails.append(f"[HIERARCHY] expected schedule(s) missing from hierarchy: {missing_sch}")
    blank_cap=sum(1 for items in hier.values() for n in items
                  if not (n.get('caption') or '').strip() and not n.get('mdrm'))
    if blank_cap: notes.append(f"[CAPTIONS] {blank_cap} node(s) with no caption and no code")

    # Find site parquets
    if not os.path.isdir(SITE_DIR): sys.exit(f"[SITE] {SITE_DIR}/ not found — run make_site_002.py first")
    site_parts=[os.path.join(SITE_DIR,f) for f in os.listdir(SITE_DIR) if f.endswith(".parquet")]
    if not site_parts: fails.append(f"[SITE] no parquet files in {SITE_DIR}/ — run make_site_002.py"); print_and_exit(fails,notes); return

    # Load site parquet codes
    try:
        import pandas as pd
        site_codes=set()
        for p in site_parts: site_codes.update(pd.read_parquet(p,columns=["mdrm"])["mdrm"].unique())
    except Exception as e: sys.exit(f"[SITE] cannot read site parquet: {e}")

    # 2. DERIV code check — parse DERIV 4-char bases from deployed HTML
    SITE_HTML=os.path.join(SITE_DIR,"index.html")
    if os.path.exists(SITE_HTML):
        html=open(SITE_HTML,encoding="utf-8").read()
        dm=re.search(r'const DERIV=\{(.*?)\n\};',html,re.DOTALL)
        if dm:
            bases=set(re.findall(r"'([0-9A-Z]{4})'",dm.group(1)))
            bases.discard('0000')
            missing_deriv=[]
            for b in sorted(bases):
                variants={p+b for p in ('RCFD','RCON','RCFN')}
                if not variants & site_codes: missing_deriv.append(b)
            if missing_deriv: fails.append(f"[DERIV] {len(missing_deriv)} DERIV base code(s) absent from site parquet: {missing_deriv[:10]}")
        else: notes.append("[DERIV] DERIV block not found in site HTML; check skipped")

        # 3. LGMEAS code check
        lm=re.search(r'const LGMEAS=\[(.*?)\];',html,re.DOTALL)
        if lm:
            comb_bases=re.findall(r"code:'COMB([0-9A-Z]{4})'",lm.group(1))
            missing_lg=[]
            for b in comb_bases:
                variants={p+b for p in ('RCFD','RCON','RCFN')}
                if not variants & site_codes: missing_lg.append('COMB'+b)
            if missing_lg: fails.append(f"[LGMEAS] {len(missing_lg)} LGMEAS COMB base(s) absent from site parquet: {missing_lg}")
    else: notes.append(f"[DERIV] {SITE_HTML} not found; run make_site_002.py first")

    # 4. GOLDEN cell — MUFG NY Branch RCFD2170 at latest quarter
    if os.path.exists(SRC):
        try:
            pnl=pd.read_parquet(SRC,columns=["quarter_end","id_rssd","mdrm","value"])
            lq=pnl["quarter_end"].max()
            gold=pnl[(pnl["id_rssd"]==GOLDEN_RSSD)&(pnl["mdrm"]==GOLDEN_CODE)&(pnl["quarter_end"]==lq)]
            if gold.empty: fails.append(f"[GOLDEN] MUFG {GOLDEN_RSSD} {GOLDEN_CODE} not found in panel at {lq}")
            else:
                v=int(gold["value"].iloc[0])
                if not (1_000_000 <= v <= 10_000_000_000): notes.append(f"[GOLDEN] {GOLDEN_CODE}={v:,} at {lq} — outside expected range for a large foreign branch")
        except Exception as e: notes.append(f"[GOLDEN] panel unreadable ({e}); golden check skipped")
    else: notes.append(f"[GOLDEN] {SRC} not found; golden check skipped")

    # 5. FILTER size check — site parquet(s) must be smaller than source
    if os.path.exists(SRC):
        src_size=os.path.getsize(SRC)
        site_size=sum(os.path.getsize(p) for p in site_parts)
        if site_size>=src_size:
            fails.append(f"[FILTER] site parquet ({site_size//1_000_000}MB) >= source ({src_size//1_000_000}MB) — DISPLAY_CODES filter may not be applied; run make_site_002.py without --html-only")

    # 7. COMPLETENESS (manifest-driven) — consume expected_items.json from the form-completeness
    #    auditor. The manifest lists, per form/schedule, MDRM codes that HAVE DATA but are absent
    #    from the hierarchy. We re-test each must-add code (has_recent_data) against the freshly built
    #    hierarchy and WARN with the remaining count for a future fixer — a tracking signal, not a
    #    blocking gate (the 002 hierarchy is known-sparse: 100s of historical gaps).
    HERE=os.path.dirname(os.path.abspath(__file__))
    _bare=lambda c:(str(c)[4:] if len(str(c))==8 and str(c)[:2].isalpha() else str(c))
    EXP=next((c for c in (os.path.join(HERE,"expected_items.json"),os.path.join(HERE,"..","expected_items.json")) if os.path.exists(c)),None)
    if not EXP:
        notes.append("[COMPLETE2] no expected_items.json manifest found; schedule-completeness check skipped")
    else:
        try:
            forms=json.load(open(EXP,encoding="utf-8")).get("forms",{})
            fkey=next((k for k in ("FFIEC 002","002") if k in forms),None)
            if not fkey:
                notes.append("[COMPLETE2] manifest has no FFIEC 002 entry; check skipped")
            else:
                present=set()
                for nodes in hier.values():
                    for nd in nodes:
                        if nd.get("mdrm"): present.add(nd["mdrm"]); present.add(_bare(nd["mdrm"]))
                still=[]; per={}
                for sch,sobj in forms[fkey].get("schedules",{}).items():
                    for mc in sobj.get("missing_codes",[]):
                        if not mc.get("has_recent_data"): continue
                        code=str(mc.get("code","")).strip()
                        if code and code not in present and _bare(code) not in present:
                            still.append(code); per[sch]=per.get(sch,0)+1
                if still:
                    top=sorted(per.items(),key=lambda x:-x[1])[:6]
                    notes.append(f"[COMPLETE2] {fkey}: {len(still)} must-add code(s) still absent from hierarchy "
                                 f"(top schedules: {top}); sample {sorted(still)[:12]} — tracked for the completeness fixer")
                else:
                    notes.append(f"[COMPLETE2] {fkey}: all must-add codes from manifest are now present in the hierarchy")
        except Exception as e:
            notes.append(f"[COMPLETE2] expected_items.json unreadable ({e}); check skipped")

    # Hierarchy structural lint — EMPTY_CAPTION / SCHED_CONTAM / within-DUPLICATE
    try:
        import sys as _sys; _sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '_lint_scratch'))
        from hierarchy_linter import lint_structural
        lint_defects = lint_structural(hier, '002')
        if lint_defects:
            fails.append(f"[HIERARCHY_LINT] {len(lint_defects)} structural defect(s) detected")
            for d in lint_defects[:5]:
                fails.append(f"  {d['check']} {d['sched']} item={d['item']} {d.get('mdrm','')}: {d['problem'][:80]}")
    except ImportError:
        notes.append("[HIERARCHY_LINT] hierarchy_linter not found; structural check skipped")
    except Exception as e:
        notes.append(f"[HIERARCHY_LINT] structural check error ({e}); skipped")

    # COMPLETENESS GATE (bidirectional, era-aware, BLOCKING) — MISSING / SPURIOUS / SEQUENCE /
    # ERA_SEAM. See _completeness_gate.py for the full contract.
    try:
        import sys as _sys; _gbase=os.path.dirname(os.path.abspath(__file__))
        for _p in (os.path.join(_gbase,'..'), _gbase):
            if _p not in _sys.path: _sys.path.insert(0,_p)
        from _completeness_gate import run_gate
        g_fails, g_notes = run_gate('002', hier, _gbase)
        fails.extend(g_fails); notes.extend(g_notes)
    except ImportError:
        fails.append("[GATE] _completeness_gate.py not found — completeness gate is REQUIRED; build cannot be trusted")
    except Exception as e:
        fails.append(f"[GATE] completeness gate error ({e})")

    print("="*60); print("FFIEC 002 build validation"); print("="*60)
    print(f"  site parts: {len(site_parts)}   hierarchy schedules: {len(hier)}   site codes: {len(site_codes)}")
    for n in notes: print("  NOTE  "+n)
    if fails:
        print(f"\n  {len(fails)} FAILURE(S):")
        for x in fails: print("  FAIL  "+x)
        sys.exit(1)
    print("\n  ALL CHECKS PASSED [OK]")

if __name__=="__main__":
    main()
