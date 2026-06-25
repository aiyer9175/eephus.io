import json, re, unicodedata, os
ROOT = r"c:\Users\noah\baseball-projects\BaseballR\prospect-tracker"

def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace(".", " ").replace("'", "").replace("-", " ")
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()

def fvnum(fv):
    if fv is None: return None
    m = re.match(r"(\d+)", str(fv))
    if not m: return None
    return float(m.group(1)) + (2.5 if "+" in str(fv) else 0.0)

# --- build PROSPX player pool (active + debuts + inactive) ---
ts = json.load(open(os.path.join(ROOT, "data/timeseries.json"), encoding="utf-8"))
pool = []
def add(p, status):
    pool.append({
        "player_key": p.get("player_key"), "name": p.get("player_name"),
        "org": p.get("org"), "fv_close": p.get("fv_close"),
        "position": p.get("position"), "mlbam_id": p.get("mlbam_id"), "status": status,
    })
for p in ts["players"]: add(p, "active")
for fn, st in [("data/debuts.json", "debuted"), ("data/inactive.json", "inactive")]:
    fp = os.path.join(ROOT, fn)
    if os.path.exists(fp):
        arr = json.load(open(fp, encoding="utf-8"))
        arr = arr if isinstance(arr, list) else arr.get("players", [])
        for p in arr: add(p, st)

by_full = {}
by_lastinit = {}
for p in pool:
    n = norm(p["name"])
    by_full.setdefault(n, []).append(p)
    parts = n.split()
    if len(parts) >= 2:
        by_lastinit.setdefault((parts[-1], parts[0][0]), []).append(p)

# --- match scraped FG prospects ---
fg = json.load(open(r"c:\tmp\fg_giants_2026_raw.json", encoding="utf-8"))
results = []
for sp in fg["prospects"]:
    n = norm(sp["name"]); cand = by_full.get(n, [])
    method = "exact"
    if not cand:
        parts = n.split()
        if len(parts) >= 2:
            cand = by_lastinit.get((parts[-1], parts[0][0]), [])
            method = "last+initial"
    # prefer SFG candidate
    sfg_cand = [c for c in cand if c["org"] == "SFG"]
    chosen = (sfg_cand or cand)
    m = None
    if len(chosen) == 1:
        m = chosen[0]
    elif len(chosen) > 1:
        m = chosen[0]; method += "(ambiguous:%d)" % len(chosen)
    fgfv = fvnum(sp["fv"])
    pxfv = m["fv_close"] if m else None
    div = (fgfv - pxfv) if (m and pxfv is not None and fgfv is not None) else None
    results.append({
        "rank": sp["rank"], "name": sp["name"], "pos": sp["position"], "level": sp["level"],
        "fg_fv": sp["fv"], "fg_fv_num": fgfv,
        "matched": bool(m), "match_method": method if m else None,
        "px_key": m["player_key"] if m else None, "px_org": m["org"] if m else None,
        "px_status": m["status"] if m else None, "px_fv_close": pxfv,
        "divergence": round(div, 1) if div is not None else None,
        "wrong_org": (m["org"] != "SFG") if m else None,
    })

matched = [r for r in results if r["matched"]]
unmatched = [r for r in results if not r["matched"]]
wrongorg = [r for r in matched if r["wrong_org"]]
print("=== MATCH SUMMARY ===")
print("matched:", len(matched), "/ 50  | unmatched:", len(unmatched))
print("matched but org != SFG:", [(r["rank"], r["name"], r["px_org"]) for r in wrongorg])
print("non-exact matches:", [(r["name"], r["match_method"]) for r in matched if r["match_method"] != "exact"])
print()
print("=== UNMATCHED (need review / new entries) ===")
for r in unmatched: print(f"  #{r['rank']:>2} {r['name']} ({r['pos']}, {r['level']}) FG FV {r['fg_fv']}")
print()
print("=== DIVERGENCES |Δ| >= 5  (FG FV - PROSPX consensus) ===")
divs = [r for r in matched if r["divergence"] is not None and abs(r["divergence"]) >= 5]
for r in sorted(divs, key=lambda x: -abs(x["divergence"])):
    print(f"  #{r['rank']:>2} {r['name']:<22} FG {r['fg_fv']:>4} ({r['fg_fv_num']}) vs PROSPX {r['px_fv_close']}  Δ {r['divergence']:+}  [{r['px_status']}]")
print()
no_fv = [r for r in matched if r['px_fv_close'] is None]
print("matched but PROSPX has no fv_close (can't compare):", [(r['rank'], r['name'], r['px_status']) for r in no_fv])
json.dump(results, open(r"c:\tmp\fg_giants_match.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
