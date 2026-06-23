#!/usr/bin/env python3
"""
build_hierarchy_002.py
Build ffiec002_hierarchy.json = per-schedule ORDERED line-item map for the FFIEC 002
explorer's tree picker and call-report view.

Source: the blank FFIEC 002 form PDF (ReturnFinancialReportPDF.pdf). Each line looks like
  <caption> .......... <code> <code> <item-number>
with the column prefixes (RCFD / RCFN / RCON) shown in the page header. We take the
Column-A prefix (Total Reporting Branch incl. IBF) + the 4-char code as the mdrm, parse the
trailing item number for depth/order, and pull the clean CAPTION from the MDRM dictionary.

Output JSON: { "RAL":[{"mdrm","caption","item","depth","order"}, ...], "C":[...], ... }

Run:  python build_hierarchy_002.py
"""
from __future__ import annotations
import csv, json, re
import pypdf

PDF="ReturnFinancialReportPDF.pdf"; DICT="ffiec002_mdrm_dictionary.csv"; OUT="ffiec002_hierarchy.json"
SCHED=re.compile(r'Schedule\s+([A-Za-z0-9-]+)', re.I)
CODE=re.compile(r'^(?=.*\d)[0-9A-Z]{4}$')                       # 4-char item code, has a digit
ITEM=re.compile(r'^\d+(?:\.[a-z0-9]+|\([0-9a-z]+\))*\.?$')      # trailing item number token
LEAD=re.compile(r'^(?:\(\w+\)|\d+\.|[a-z]\.)\s*')              # leading marker on a caption
def depth(it):
    # Count segments: paren groups, digits, lowercase letters; add 1 for uppercase-section prefix (M, S, etc.)
    count = len(re.findall(r'\(\w+\)|\d+|[a-z]', it))
    if it and it[0].isupper():
        count += 1
    return max(1, count)

def item_sort_key(item_str):
    """Convert item number to sort tuple. Three segment classes so siblings order per the form:
      0 = bare numeric ('1','2','M.1' top-level digits) — sorts first (keeps items 1..N before 'M')
      1 = alphabetic (bare 'a'/'b' column letters AND parenthesized '(a)'/'(b)')
      2 = parenthesized numeric '(1)','(2)' — sorts AFTER bare-letter columns
    The class-2 rule fixes Schedule Q item 5.b: its own column items 5.b.b/c/d/e (G498-G501,
    on the same form line) must precede the 5.b.(1) "Nontrading securities" sub-row (F240-F242,
    next line down). Verified to change ordering ONLY for Q 5.b across all 002 schedules; bare
    numeric vs '(2)' (e.g. Schedule B 1.c: '1' then '(2)') is unaffected (0 < 2)."""
    s = (item_str or '').strip().rstrip('.')
    key = []
    for seg in re.findall(r'\([^)]*\)|[^.]+', s):
        paren = seg.startswith('(')
        inner = seg.strip('()')
        if inner.isdigit():
            key.append((2 if paren else 0, int(inner), ''))
        else:
            key.append((1, 0, inner.lower()))
    return key or [(1, 0, '')]

def load_caps():
    caps={}
    try:
        for row in csv.DictReader(open(DICT, encoding="latin-1")):
            m=(row.get("mdrm") or "").strip(); d=(row.get("description") or "").strip()
            if m: caps[m]=d
    except Exception as e: print("(no dictionary:", e, ")")
    return caps

OVERRIDES="ffiec002_hierarchy_overrides.json"

def apply_overrides(hier):
    """Apply drop_codes/captions/force_rows from ffiec002_hierarchy_overrides.json.
    Mirrors the Y-9C mechanism: flat drop_codes list (safe here — 002 codes are unique per
    schedule via PDF parse) + force_rows with optional 'depth' field.
    NOTE: Call uses key-scoped {key,mdrm} drop_codes instead (codes repeat across 45 schedules
    in CDR zips; global drops would remove correct entries — verified 2026-06-19)."""
    import os
    if not os.path.exists(OVERRIDES):
        return
    try: ov=json.load(open(OVERRIDES,encoding="utf-8"))
    except Exception as e:
        print(f"  WARNING: {OVERRIDES} not applied (parse error: {e})"); return
    # drop_codes: flat list of mdrm strings, dropped globally (same format as Y-9C)
    drop=set(ov.get("drop_codes",[]))
    if drop:
        ndropped=0
        for key in list(hier):
            before=len(hier[key])
            hier[key]=[r for r in hier[key] if r["mdrm"] not in drop]
            ndropped+=before-len(hier[key])
        if ndropped: print(f"  [overrides] dropped {ndropped} codes via drop_codes")
    # captions: patch specific codes (same as Y-9C)
    caps_ov=ov.get("captions",{})
    for rows in hier.values():
        for r in rows:
            if r["mdrm"] in caps_ov: r["caption"]=caps_ov[r["mdrm"]]
    # force_rows: add/correct rows; a force_row with non-empty mdrm is AUTHORITATIVE —
    # it removes any existing entry for that mdrm in this schedule and re-adds it at
    # the force_row's item/depth. This ensures wrong-notation entries from the PDF
    # parser (e.g. "1.c.(2)(a)" without dot between paren groups) are replaced by
    # the canonical dot-separated form "1.c.(2).(a)".
    added=0
    for row in ov.get("force_rows",[]):
        key=row.get("key"); mdrm=row.get("mdrm","")
        if not key: continue
        seq=hier.setdefault(key,[])
        if mdrm:
            seq[:] = [x for x in seq if x.get("mdrm") != mdrm]  # remove existing; force_row takes precedence
        else:
            item_=row.get("item","")
            if item_ and any(x.get("item")==item_ and not x.get("mdrm") for x in seq): continue
        item=row.get("item", mdrm[4:] if mdrm else "")
        node={"mdrm":mdrm,"caption":row.get("caption",mdrm),"item":item,
                    "depth":depth(item) if item else 1,
                    "order":row.get("order", len(seq))}
        # col: matrix-column leaf flag (mirrors Y-9C build). When set, the engine renders the
        # node as a column-suffix leaf (suppresses the item-number badge) — e.g. Schedule N's
        # .(A)/.(B)/.(C)/.(D) past-due/nonaccrual/modified columns under each loan-type row.
        if row.get("col"): node["col"]=True
        seq.append(node)
        added+=1
    # Re-sort by item number (hierarchical) so force_rows land after their parents,
    # then rewrite 'order' to match new positions (linter and site both use 'order').
    for key in hier:
        hier[key].sort(key=lambda x: item_sort_key(x.get("item", "")))
        for i, node in enumerate(hier[key]):
            node["order"] = i
    print(f"  [overrides] applied {added} force_rows from {OVERRIDES}")

def main():
    caps=load_caps(); r=pypdf.PdfReader(PDF); hier={}
    for pg in r.pages:
        t=pg.extract_text() or ""
        sm=SCHED.search(t)
        if not sm: continue
        sch=sm.group(1).upper()
        pref=re.findall(r'\b(RCFD|RCON|RCFN)\b', t); pA=pref[0] if pref else "RCFD"
        seq=hier.setdefault(sch, []); seen={x["mdrm"] for x in seq}
        for ln in t.splitlines():
            toks=ln.split()
            if len(toks)<2 or not ITEM.match(toks[-1]): continue
            codes=[]; j=len(toks)-2
            while j>=0 and CODE.match(toks[j]): codes.append(toks[j]); j-=1
            if not codes: continue
            code=codes[-1]                       # leftmost trailing code = Column A
            mdrm=pA+code
            if mdrm in seen: continue
            frag=LEAD.sub("", " ".join(toks[:j+1])); frag=re.sub(r'[.\s]+$', "", frag).strip()
            cap=caps.get(mdrm) or caps.get("RCFD"+code) or caps.get("RCON"+code) or frag or mdrm
            it=toks[-1].rstrip(".")
            seq.append({"mdrm":mdrm,"caption":cap,"item":it,"depth":depth(it),"order":len(seq)})
            seen.add(mdrm)
    apply_overrides(hier)
    json.dump(hier, open(OUT,"w",encoding="utf-8"), ensure_ascii=False, indent=0)
    n=sum(len(v) for v in hier.values())
    print(f"wrote {OUT}: {len(hier)} schedules, {n} items")
    for k,v in hier.items(): print(f"  {k}: {len(v)}")

if __name__=="__main__": main()
