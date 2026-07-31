"""SCRATCH (read-only) - (C) term gradient with a convexity control,
(D) a worked option-pricing pass over the 2027 class's 74 option-laden rows.
Writes nothing.
"""
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from value_framework import tiered_war_value_usd, _config  # noqa: E402
import numpy as np  # noqa: E402

cfg = _config()
R = float(cfg["discount_rate"])
FLAT = float(cfg["dollars_per_war"]["flat"])
cls = json.loads((ROOT / "data" / "fa_class.json").read_text(encoding="utf-8"))
LEVEL = float(cls["dpw_usd"]) / FLAT
arch = json.loads((ROOT / "data" / "fa_archive.json").read_text(encoding="utf-8"))

print("=== (C) $ paid per TIER-PRICED realized value, by term ===")
print("    (controls for the convex per-win rate: long deals go to better")
print("     players whose wins are individually pricier)")
b_ = defaultdict(lambda: {"g": 0.0, "v": 0.0, "n": 0})
for wtr in arch["winters"]:
    for s in wtr["signings"]:
        if s.get("milb") or not s.get("done") or not s.get("years") or not s.get("guar"):
            continue
        war = s.get("warTd")
        if war is None:
            continue
        y = int(s["years"])
        per = war / y                      # level realized WAR/season
        val = sum(tiered_war_value_usd(per) * LEVEL / ((1 + R) ** t) for t in range(y))
        b = "1" if y == 1 else "2" if y == 2 else "3" if y == 3 else "4-5" if y <= 5 else "6+"
        d = b_[b]
        d["g"] += s["guar"] / ((1 + R) ** 0)     # nominal guarantee
        d["v"] += val
        d["n"] += 1
print(f"  {'term':6s} {'n':>5s} {'paid/$ of tier-priced value':>30s}")
base = None
for b in ["1", "2", "3", "4-5", "6+"]:
    d = b_.get(b)
    if not d or d["v"] <= 0:
        continue
    ratio = d["g"] / d["v"]
    if base is None:
        base = ratio
    print(f"  {b:6s} {d['n']:5d} {ratio:26.3f}   (x{ratio/base:.2f} vs 1-yr)")

print()
print("=== (D) option pricing pass over the 2027 class ===")
x, w = np.polynomial.hermite_e.hermegauss(25)
w = w / w.sum()
Z = 1.2815515655446004


def rational(path):
    return sum(tiered_war_value_usd(v) * LEVEL / ((1 + R) ** t) for t, v in enumerate(path))


rows = []
for m in cls["members"]:
    price = m.get("optPrice")
    typ = m.get("type")
    if not price or typ == "ufa":
        continue
    mid, p10, p90 = m.get("warPath"), m.get("warPathP10"), m.get("warPathP90")
    if not (mid and p10 and p90):
        continue
    # ONE-YEAR option: the underlying is the value of the option season.
    s_hi = (p90[0] - mid[0]) / Z
    s_lo = (mid[0] - p10[0]) / Z
    club_call = player_put = 0.0
    p_ex_club = p_ex_player = 0.0
    vals = []
    for zi, wi in zip(x, w):
        s = s_hi if zi >= 0 else s_lo
        wz = max(0.0, mid[0] + s * zi)
        v = tiered_war_value_usd(wz) * LEVEL      # market value of the option season
        vals.append((v, wi))
        club_call += wi * max(0.0, v - price)     # team's call: exercise if worth > price
        player_put += wi * max(0.0, price - v)    # player's put: exercise if worth < price
        p_ex_club += wi * (1.0 if v > price else 0.0)
        p_ex_player += wi * (1.0 if v < price else 0.0)
    ev = sum(v * wi for v, wi in vals)
    rows.append({"name": m["name"], "type": typ, "price": price, "ev": ev,
                 "call": club_call, "put": player_put,
                 "p_ex_club": p_ex_club, "p_ex_player": p_ex_player,
                 "enterProb": m.get("enterProb"), "src": m.get("enterProbSrc"),
                 "projAav": m.get("projAav")})
print(f"n option-laden rows priced: {len(rows)}")
by_t = defaultdict(list)
for r in rows:
    by_t[r["type"]].append(r)
for t, rs in sorted(by_t.items()):
    print(f"\n  --- {t} (n={len(rs)}) ---")
    rs.sort(key=lambda r: -(r["call"] if "club" in t else r["put"]))
    for r in rs[:6]:
        held = "CLUB call" if "club" in t else "PLAYER put"
        v = r["call"] if "club" in t else r["put"]
        print(f"    {r['name']:22s} K=${r['price']/1e6:6.1f}M  E[S]=${r['ev']/1e6:6.1f}M  "
              f"{held} ${v/1e6:6.1f}M  P(exercise)={(r['p_ex_club'] if 'club' in t else r['p_ex_player']):.2f}  "
              f"servedEnterProb={r['enterProb']}")
tot_club = sum(r["call"] for r in rows if "club" in (r["type"] or ""))
tot_pl = sum(r["put"] for r in rows if "player" in (r["type"] or "") or r["type"] == "opt_out")
print(f"\n  TOTAL club-held call value in the class:   ${tot_club/1e6:.1f}M")
print(f"  TOTAL player-held put value in the class: ${tot_pl/1e6:.1f}M")

# consistency: served enterProb (band-priced on AAV) vs value-priced P(exercise)
club = [r for r in rows if r["type"] == "club_option" and r["enterProb"] is not None]
if club:
    d = [(1 - r["p_ex_club"]) - r["enterProb"] for r in club]
    print(f"\n  club_option: P(enter) value-priced vs served band-priced, "
          f"mean diff {statistics.mean(d):+.3f}, n={len(club)}")
    print(f"    served mean {statistics.mean(r['enterProb'] for r in club):.3f} | "
          f"value-priced mean {statistics.mean(1-r['p_ex_club'] for r in club):.3f}")
