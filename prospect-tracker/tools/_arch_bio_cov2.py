import json, sys, collections
sys.path.insert(0, r"C:\Users\noah\baseball-projects\BaseballR\prospect-tracker")
src = json.load(open("tools/_arch_bio_src.json"))
snap = json.load(open("tools/_arch_bio_snap.json"))
old = {int(r["mlbam_id"]): r for r in json.load(open("data/xfv_extra_physical.json")) if r.get("mlbam_id")}

def cov(rows, label):
    n = len(rows)
    c_draft = c_ov = c_snap = c_old = c_any_hw = c_any_bmi = 0
    for r in rows:
        k = r["player_key"]; mid = r.get("mlbam_id")
        d = src["draft"].get(k); o = src["overseas"].get(k); s = snap.get(k)
        ob = old.get(int(mid)) if mid else None
        if d and (d["h"] or d["w"]): c_draft += 1
        if o: c_ov += 1
        if s: c_snap += 1
        if ob and ob.get("bmi") is not None: c_old += 1
        hw = (d and d["h"] and d["w"]) or (o and o["h"] and o["w"]) or (s and s[0][1] and s[0][2])
        if hw: c_any_hw += 1
        if hw or (ob and ob.get("bmi") is not None): c_any_bmi += 1
    print(f"{label:34s} n={n:5d} draft={c_draft:5d}({c_draft/n:5.1%}) overseas={c_ov:3d} snap={c_snap:3d} "
          f"oldbmi={c_old:4d}({c_old/n:5.1%}) ANY_h+w={c_any_hw:5d}({c_any_hw/n:5.1%}) ANY_bmi={c_any_bmi:5d}({c_any_bmi/n:5.1%})")

for side in ("hit","pit"):
    rows = json.load(open(f"data/xfv_{'hitter' if side=='hit' else 'pitcher'}_matrix.json"))
    cov(rows, f"{side} FULL fit pool")
    cov([r for r in rows if r["kind"]=="debuted"], f"{side} debuted (old-eval pool)")
    cov([r for r in rows if r.get("milb")], f"{side} track-record rows")
    cov([r for r in rows if r["kind"]=="debuted" and r.get("target_resolved") is not None], f"{side} debuted+resolved")

# served board
xf = json.load(open("data/xfv.json"))
print("xfv.json type", type(xf), (list(xf.keys())[:8] if isinstance(xf,dict) else len(xf)))
