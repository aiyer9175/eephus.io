import json, sys, collections, statistics
sys.path.insert(0, r"C:\Users\noah\baseball-projects\BaseballR\prospect-tracker")
panel = json.load(open("tools/_arch_bio_panel.json"))
src = json.load(open("tools/_arch_bio_src.json"))
old = {int(r["mlbam_id"]): r for r in json.load(open("data/xfv_extra_physical.json")) if r.get("mlbam_id")}

# --- empirical drift: do listed ht/wt CHANGE over a career? ---
dw = []; dh = []; nmulti = 0
for k, obs in panel.items():
    ws = [(o["vintage"], o["w"]) for o in obs if o["w"]]
    hs = [(o["vintage"], o["h"]) for o in obs if o["h"]]
    if len(ws) >= 2:
        nmulti += 1
        dw.append(ws[-1][1] - ws[0][1])
    if len(hs) >= 2:
        dh.append(hs[-1][1] - hs[0][1])
print(f"players with >=2 dated WEIGHT obs: {nmulti}")
print(f"  weight last-minus-first: mean {statistics.mean(dw):+.2f} lb, median {statistics.median(dw):+.1f}, "
      f"changed in {sum(1 for x in dw if x):d}/{len(dw)} ({sum(1 for x in dw if x)/len(dw):.1%}), "
      f"max +{max(dw)} / {min(dw)}")
print(f"  height changed in {sum(1 for x in dh if x)}/{len(dh)} ({sum(1 for x in dh if x)/len(dh):.1%})")

def asof(key, cutoff):
    """Latest board observation with vintage STRICTLY <= cutoff. None if none."""
    obs = panel.get(key)
    if not obs or not cutoff: return None
    ok = [o for o in obs if o["vintage"] <= cutoff]
    return ok[-1] if ok else None

def latest(key):
    obs = panel.get(key)
    return obs[-1] if obs else None

for side, f in (("hit", "hitter"), ("pit", "pitcher")):
    rows = json.load(open(f"data/xfv_{f}_matrix.json"))
    for label, sel in (("FULL fit pool", lambda r: True),
                       ("debuted (old-eval pool)", lambda r: r["kind"] == "debuted"),
                       ("track-record rows", lambda r: bool(r.get("milb")))):
        rr = [r for r in rows if sel(r)]
        n = len(rr)
        c_asof = c_any = c_frame_asof = c_old = 0
        for r in rr:
            k = r["player_key"]; cut = r.get("cutoff") or r.get("asof_date")
            a = asof(k, cut)
            if a and a["h"] and a["w"]: c_asof += 1
            if a and a.get("frame") not in (None, ""): c_frame_asof += 1
            l = latest(k)
            d = src["draft"].get(k)
            if (l and l["h"] and l["w"]) or (d and d["h"] and d["w"]): c_any += 1
            mid = r.get("mlbam_id")
            if mid and old.get(int(mid), {}).get("bmi") is not None: c_old += 1
        print(f"{side} {label:26s} n={n:5d} | AS-OF-SAFE h+w {c_asof:5d} ({c_asof/n:5.1%}) | "
              f"as-of Frame {c_frame_asof:4d} ({c_frame_asof/n:5.1%}) | any-vintage {c_any:5d} ({c_any/n:5.1%}) | "
              f"2026-07-15 bmi {c_old:4d} ({c_old/n:5.1%})")

# served board
xf = json.load(open("data/xfv.json"))["by_player"]
n = len(xf); ca = cf = 0
for k, v in xf.items():
    a = latest(k)
    if a and a["h"] and a["w"]: ca += 1
    if a and a.get("frame") not in (None, ""): cf += 1
print(f"SERVED BOARD n={n} | h+w (latest board) {ca} ({ca/n:.1%}) | Frame {cf} ({cf/n:.1%})")
