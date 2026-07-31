"""As-of-safe biometric features per matrix row. Vintage is STRICTLY <= the row's
decision cutoff, so nothing is measured after the label window opens."""
import json, sys, collections
sys.path.insert(0, r"C:\Users\noah\baseball-projects\BaseballR\prospect-tracker")
panel = json.load(open("tools/_arch_bio_panel.json"))
src = json.load(open("tools/_arch_bio_src.json"))

def _f(x):
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None

out = {}
audit = collections.Counter()
for side, f in (("hit", "hitter"), ("pit", "pitcher")):
    rows = json.load(open(f"data/xfv_{f}_matrix.json"))
    for r in rows:
        k = r["player_key"]
        cut = r.get("cutoff") or r.get("asof_date")
        rec = {"h": None, "w": None, "frame": None, "athl": None, "levers": None,
               "vintage": None, "src": None}
        obs = [o for o in (panel.get(k) or []) if cut and o["vintage"] <= cut]
        if obs:
            # latest as-of board; backfill each field from the most recent board that has it
            for o in reversed(obs):
                for fld, key in (("h", "h"), ("w", "w"), ("frame", "frame"),
                                 ("athl", "athl"), ("levers", "levers")):
                    if rec[fld] in (None, "") and o.get(key) not in (None, ""):
                        rec[fld] = o[key]
                        if fld in ("h", "w") and rec["vintage"] is None:
                            rec["vintage"] = o["vintage"]
            rec["src"] = "fg_board_asof"
        else:
            d = src["draft"].get(k)
            if d and (d["h"] or d["w"]) and cut and d["vintage"] <= cut:
                rec.update(h=d["h"], w=d["w"], vintage=d["vintage"], src="draft_board_asof")
        if rec["vintage"] and cut and rec["vintage"] > cut:
            audit["VIOLATION"] += 1
        h, w = rec["h"], rec["w"]
        rec["bmi"] = round(703.0 * w / (h * h), 3) if (h and w) else None
        # Levers is a categorical Short/Med/Long
        lv = (rec["levers"] or "").strip().lower()
        rec["levers_num"] = {"short": -1.0, "med": 0.0, "medium": 0.0, "long": 1.0}.get(lv)
        rec["frame"] = _f(rec["frame"]); rec["athl"] = _f(rec["athl"])
        out[f"{side}|{k}"] = rec
        audit[f"{side}_total"] += 1
        if rec["bmi"] is not None: audit[f"{side}_bmi"] += 1
        if rec["frame"] is not None: audit[f"{side}_frame"] += 1
        if rec["levers_num"] is not None: audit[f"{side}_levers"] += 1

print("AS-OF VIOLATIONS (vintage after cutoff):", audit["VIOLATION"])
for s in ("hit", "pit"):
    t = audit[f"{s}_total"]
    print(f"{s}: n={t} bmi={audit[f'{s}_bmi']} ({audit[f'{s}_bmi']/t:.1%}) "
          f"frame={audit[f'{s}_frame']} ({audit[f'{s}_frame']/t:.1%}) "
          f"levers={audit[f'{s}_levers']} ({audit[f'{s}_levers']/t:.1%})")
json.dump(out, open("tools/_arch_bio_feat.json", "w"))

# lag audit: how stale is the as-of observation?
lags = []
for side, f in (("hit", "hitter"),):
    rows = json.load(open(f"data/xfv_{f}_matrix.json"))
    for r in rows:
        rec = out[f"hit|{r['player_key']}"]
        cut = r.get("cutoff")
        if rec["vintage"] and cut:
            from datetime import date
            a = date.fromisoformat(rec["vintage"]); b = date.fromisoformat(cut[:10])
            lags.append((b - a).days)
lags.sort()
import statistics
print(f"as-of lag (days before cutoff) n={len(lags)} median {statistics.median(lags):.0f} "
      f"p10 {lags[len(lags)//10]} p90 {lags[9*len(lags)//10]} min {lags[0]} max {lags[-1]}")
