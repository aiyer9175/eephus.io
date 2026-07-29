"""Biometric coverage census for the eFV pool. READ-ONLY. Scratch lab."""
import json, re, sqlite3, sys, collections
sys.path.insert(0, r"C:\Users\noah\baseball-projects\BaseballR\prospect-tracker")
import storage

HT_RE = re.compile(r"(\d)\s*['\u2019]\s*(\d{1,2})?\s*[\"\u201d]?")
def parse_ht(s):
    if not s: return None
    m = HT_RE.search(str(s))
    if not m: return None
    ft = int(m.group(1)); inch = int(m.group(2) or 0)
    if not (4 <= ft <= 7) or inch > 11: return None
    return ft*12 + inch

con = sqlite3.connect(storage.DB_PATH); con.row_factory = sqlite3.Row

# ---- source 1: draft_players (vintage = draft_year, PRE-decision) ----
src = collections.defaultdict(dict)   # key -> dict
d1 = 0
for r in con.execute("SELECT player_key, promoted_key, player_name, draft_year, height, weight, mlbam_id FROM draft_players"):
    h = parse_ht(r["height"]); w = r["weight"]
    if h is None and not w: continue
    d1 += 1
    for k in (r["promoted_key"], r["player_key"]):
        if k:
            src["draft"][k] = {"h": h, "w": w, "vintage": f"{r['draft_year']}-06-01", "src": "draft_board"}
print("draft_players rows with h/w:", d1, "keys:", len(src["draft"]))

# ---- source 2: overseas_players ----
for r in con.execute("SELECT player_key, promoted_key, height, weight FROM overseas_players"):
    h = parse_ht(r["height"]); w = r["weight"]
    if h is None and not w: continue
    for k in (r["promoted_key"], r["player_key"]):
        if k: src["overseas"][k] = {"h": h, "w": w, "vintage": None, "src": "overseas"}
print("overseas keys:", len(src["overseas"]))

# ---- source 3: snapshots report text "Height/Weight: 6'4", 215" ----
RPT = re.compile(r"Height\s*/\s*Weight\s*:\s*([^|\n]+)", re.I)
WT = re.compile(r"(\d{3})\b")
snap = collections.defaultdict(list)
n_scan = n_hit = 0
for r in con.execute("SELECT player_key, snapshot_date, source, tools_json FROM snapshots WHERE tools_json LIKE '%Height/Weight%'"):
    n_scan += 1
    try: tj = json.loads(r["tools_json"] or "{}")
    except Exception: continue
    rep = (tj.get("_extras") or {}).get("report") or ""
    m = RPT.search(rep)
    if not m: continue
    seg = m.group(1)
    h = parse_ht(seg); wm = WT.search(seg)
    w = int(wm.group(1)) if wm else None
    if h is None and w is None: continue
    n_hit += 1
    snap[r["player_key"]].append((r["snapshot_date"], h, w, r["source"]))
print("snapshot rows scanned:", n_scan, "parsed:", n_hit, "keys:", len(snap))
json.dump({k: v for k, v in snap.items()}, open("tools/_arch_bio_snap.json","w"))
json.dump({k: dict(v) for k, v in src.items()}, open("tools/_arch_bio_src.json","w"))
