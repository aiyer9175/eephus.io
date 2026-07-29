"""Lane: prospect. (b) CONCRETE CONTRADICTION TABLE - named players, served numbers.

Every row is a quantity two shipped surfaces disagree about for the SAME player on
the SAME build date.
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
D = ROOT / "data"
L = lambda n: json.loads((D / n).read_text(encoding="utf-8"))
import value_framework as vf

xfv = L("xfv.json")["by_player"]
tv = {r["player_key"]: r for r in L("trade_values.json")["players"]}
mp = L("mlb_projections.json")
pr = {r["key"]: r for r in mp["prospects"]}

print("=" * 90)
print("X1  STAR ODDS  vs  the eFV outcome distribution on the same card")
print("=" * 90)
print("   PROSPX shows surplus.star_odds = published_star_odds(served eFV grade, role).")
print("   The same card's outcome-mix comes from xfv p_bucket. Both claim P(star).")
rows = []
for k, x in xfv.items():
    if x.get("kind") != "active":
        continue
    g = x.get("xfv_grade_quantile")
    pb = (x.get("p_bucket") or {}).get("star")
    if g is None or pb is None:
        continue
    is_pit = x.get("side") == "P"
    so = vf.published_star_odds(float(g), is_pit)
    if so is None:
        continue
    rows.append((k, g, x.get("side"), float(so), float(pb)))
rows.sort(key=lambda r: -(r[3] - r[4]))
print(f"   n active with both = {len(rows)}")
import statistics
print(f"   median published star odds = {statistics.median(r[3] for r in rows):.4f}")
print(f"   median eFV p_bucket star   = {statistics.median(r[4] for r in rows):.4f}")
print(f"   ratio of medians           = "
      f"{statistics.median(r[3] for r in rows)/max(1e-9,statistics.median(r[4] for r in rows)):.1f}x")
print(f"   {'player':30s} {'eFV':>5s} {'side':>4s} {'STAR ODDS shown':>15s} {'eFV P(star)':>12s}")
for k, g, s, so, pb in rows[:12]:
    print(f"   {k[:30]:30s} {g:5.1f} {s:>4s} {so:15.3f} {pb:12.3f}")

print()
print("=" * 90)
print("X2  P(BUST): /prospx/ (eFV outcome model) vs /projections/ (FV-mixture)")
print("=" * 90)
b = [(k, xfv[k]["p_bust"], pr[k]["pBust"], pr[k].get("name"))
     for k in pr if k in xfv and xfv[k].get("p_bust") is not None
     and pr[k].get("pBust") is not None]
b.sort(key=lambda r: -(abs(r[2] - r[1])))
print(f"   n joined = {len(b)}   disagree by >0.01: {sum(1 for r in b if abs(r[2]-r[1])>0.01)}")
print(f"   {'player':28s} {'prospx p_bust':>14s} {'projections pBust':>18s} {'ratio':>7s}")
for k, a, c, nm in b[:12]:
    print(f"   {str(nm)[:28]:28s} {a:14.3f} {c:18.3f} {(c/a if a else float('inf')):7.2f}")

print()
print("=" * 90)
print("X3  eFV GRADE: /prospx/ (quantile, site-wide rule) vs the Trade Machine sort key (raw)")
print("=" * 90)
g = [(tv[k].get("player_name"), xfv[k]["xfv_grade_quantile"], tv[k]["xfv_grade"])
     for k in xfv if k in tv and tv[k].get("xfv_grade") is not None
     and xfv[k].get("xfv_grade_quantile") is not None]
g.sort(key=lambda r: -abs(r[1] - r[2]))
print(f"   n = {len(g)}   differ by >=5 grade points: {sum(1 for r in g if abs(r[1]-r[2])>=5)}")
for nm, a, c in g[:8]:
    print(f"   {str(nm)[:30]:30s} prospx {a:5.1f}   trade board sort key {c:5.1f}   delta {c-a:+.1f}")

print()
print("=" * 90)
print("X4  SURPLUS: eFV surplus vs the value the Trade Machine shows, same player")
print("=" * 90)
s = [(tv[k].get("player_name"), xfv[k]["surplus_mm"], tv[k]["trade_value_mm"],
      tv[k].get("surplus_source"), tv[k].get("status"))
     for k in xfv if k in tv and xfv[k].get("surplus_mm") is not None
     and tv[k].get("trade_value_mm") is not None]
for src in ("projection", "xfv_backgrade", "xfv"):
    sub = [r for r in s if r[3] == src]
    if not sub:
        continue
    sub.sort(key=lambda r: -abs(r[1] - r[2]))
    print(f"   surplus_source={src}  n={len(sub)}  "
          f"median|diff|=${statistics.median(abs(r[1]-r[2]) for r in sub):.1f}M  "
          f"max|diff|=${max(abs(r[1]-r[2]) for r in sub):.1f}M")
    for nm, a, c, _, st in sub[:5]:
        print(f"      {str(nm)[:28]:28s} eFV surplus ${a:8.1f}M   board value ${c:8.1f}M   ({st})")

print()
print("=" * 90)
print("X5  DOES THE BOARD ORDER CONTRADICT ITS OWN DISPLAYED LETTER?")
print("=" * 90)
rows = [p for p in tv.values() if p.get("xfv_grade") is not None
        and p.get("trade_value_mm") is not None]
rows.sort(key=lambda p: (-p["xfv_grade"], -p["trade_value_mm"]))
inv = [(a, b) for a, b in zip(rows, rows[1:]) if b["trade_value_mm"] > a["trade_value_mm"]]
print(f"   default 'Grade' sort, n={len(rows)}: adjacent inversions of the displayed $ = "
      f"{len(inv)} ({100*len(inv)/(len(rows)-1):.1f}%)")
inv.sort(key=lambda ab: ab[0]["trade_value_mm"] - ab[1]["trade_value_mm"])
for a, b in inv[:6]:
    print(f"      {a['player_name'][:24]:24s} ${a['trade_value_mm']:8.1f}M  listed ABOVE  "
          f"{b['player_name'][:24]:24s} ${b['trade_value_mm']:8.1f}M")
