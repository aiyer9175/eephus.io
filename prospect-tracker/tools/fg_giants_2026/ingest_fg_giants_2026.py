# Ingest the scraped FanGraphs Giants 2026 Top 50 as a dated `fangraphs`
# snapshot (interval_label 'SFG Top 50', 2026-06-05). Reuses the system's own
# Snapshot / _parse_fv_full / insert_snapshots so it integrates exactly like a
# normal FG ingest. Honors the confirmed plan: ingest the 44 matched + create
# the 5 new SFG players; HOLD the Carlos Gutierrez (#33) collision; does NOT
# recompute consensus (no rebuild).
import sys, json
REPO = r"c:\Users\noah\baseball-projects\BaseballR\prospect-tracker"
sys.path.insert(0, REPO)
from scrapers import Snapshot, normalize_key, _parse_fv_full
import storage

HIT_MAP = {"Hit": "hit", "Raw Power": "raw_pwr", "Game Power": "game_pwr",
           "Run": "speed", "Fielding": "field", "Throw": "throw"}
PIT_MAP = {"Fastball": "fb", "Slider": "sl", "Curveball": "cb",
           "Changeup": "ch", "Cutter": "ct", "Command": "cmd"}
SOURCE, INTERVAL, DATE, ORG = "fangraphs", "SFG Top 50", "2026-06-05", "SFG"
HOLD_RANK = 33  # Carlos Gutierrez — CLE namesake collision, held for review

scrape = json.load(open(r"c:\tmp\fg_giants_2026_raw.json", encoding="utf-8"))
match = {m["rank"]: m for m in json.load(open(r"c:\tmp\fg_giants_match.json", encoding="utf-8"))}

def grade(tv):
    val = tv.get("future") or tv.get("raw")
    try: return float(int(str(val).strip()))
    except Exception: return None

snaps, new_players, skipped = [], [], []
for sp in scrape["prospects"]:
    rk = sp["rank"]; m = match.get(rk, {})
    if rk == HOLD_RANK:
        skipped.append((rk, sp["name"], "collision-hold")); continue
    is_new = not m.get("matched")
    key = normalize_key(sp["name"]) if is_new else m["px_key"]
    if is_new:
        new_players.append((rk, sp["name"], key))
    fv, plus = _parse_fv_full(sp["fv"])
    pos = sp["position"]
    is_pit = pos in ("SP", "SIRP", "MIRP", "RP", "P")
    tmap = PIT_MAP if is_pit else HIT_MAP
    tools, extras, present = {}, {}, {}
    for label, tv in sp["tools"].items():
        if label == "Sits/Tops":
            extras["sits_tops"] = tv.get("raw"); continue
        if label == "Splitter":
            extras["splitter"] = tv.get("raw"); continue
        k = tmap.get(label)
        if not k:
            extras[label.lower()] = tv.get("raw"); continue
        g = grade(tv)
        if g is not None: tools[k] = g
        if tv.get("present"):
            try: present[k] = float(int(tv["present"]))
            except Exception: pass
    if present: extras["present"] = present
    payload = dict(tools)
    if extras: payload["_extras"] = extras
    status = "debuted" if (sp["level"] == "MLB") else "active"
    snaps.append(Snapshot(
        source=SOURCE, snapshot_date=DATE, interval_label=INTERVAL,
        player_key=key, player_name=sp["name"], position=pos, org=ORG,
        rank=rk, fv=fv, status=status, tools=(payload or None), fv_plus=bool(plus)))

print("=== BUILD SUMMARY ===")
print("snapshots to insert:", len(snaps))
print("new players to create:", [(r, n, k) for r, n, k in new_players])
print("held (skipped):", skipped)
print("--- sample records ---")
for s in snaps[:2] + [x for x in snaps if x.position in ("SP","SIRP")][:1]:
    print(f"  #{s.rank} {s.player_key} fv={s.fv} plus={s.fv_plus} status={s.status} tools={s.tools}")

storage.init_db()
n = storage.insert_snapshots(snaps)
print("=== insert_snapshots affected rows:", n, "===")
