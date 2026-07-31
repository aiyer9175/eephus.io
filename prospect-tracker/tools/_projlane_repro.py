# Scratch: reproduce the projections-lane bugs. Read-only (writes nothing).
from __future__ import annotations
import json, os, sys, datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import fa_projection as fp

def hdr(s): print("\n=== " + s + " ===")

corpus = fp.build_corpus()
league = corpus["league"]
hdr("BUG 3: corpus staleness")
p = fp.CORPUS_CACHE
print("corpus pkl mtime:", datetime.datetime.fromtimestamp(os.path.getmtime(p)))
print("corpus first/last:", corpus["first"], corpus["last"])
for s in (2024, 2025, 2026):
    print(f"  season {s}: _total_pa={league.get(s,{}).get('_total_pa')}")
print("season_fraction(2026) =", round(fp.season_fraction(league, 2026), 4))
print("today:", datetime.date.today())

hdr("BUG 2: pitcher ip_proj never aged")
curves, war_map = fp.fitted_models(corpus, 2026)
by_p = {}
for r in corpus["pit"]:
    if r.get("mlbam"):
        by_p.setdefault(r["mlbam"], {})[r["season"]] = r
rows = []
for m, seasons in by_p.items():
    hist = [seasons[t] for t in (2026, 2025, 2024) if t in seasons]
    if not hist:
        continue
    ar = next((h for h in hist if h.get("age")), None)
    if ar is None:
        continue
    age = ar["age"] + (2027 - ar["season"])
    pr = fp.project_player(hist, "pit", 2027, curves, league, age,
                           in_progress=(2026, fp.season_fraction(league, 2026)))
    if not pr:
        continue
    pt, ip = pr["pt_proj"], pr.get("ip_proj") or 0.0
    if ip <= 0:
        continue
    war = fp.war_from_projection(pr, "pit", war_map, league, 2027)
    # internally-consistent twin: ip derived from the AGED bf
    ip2 = pt / 4.3
    fipc = fp._league_recent(league, 2027, "fip_constant") or 3.1
    fip2 = round((13*pr["hr_bf"]*pt + 3*(pr["bb_pct"]*pt + 0.008*pt) - 2*pr["k_pct"]*pt)
                 / max(ip2, 1) + fipc, 2)
    pr2 = dict(pr); pr2["ip_proj"] = round(ip2, 1); pr2["fip_proj"] = fip2
    war2 = fp.war_from_projection(pr2, "pit", war_map, league, 2027)
    rows.append((m, pr["role"], age, pt, ip, ip2, pr["fip_proj"], fip2, war, war2))
n = len(rows)
ratios = [r[3] / (4.3 * r[4]) for r in rows]
dfip = [r[6] - r[7] for r in rows]
dwar = [r[8] - r[9] for r in rows]
def q(v, f):
    v = sorted(v); return v[int(f * (len(v) - 1))]
print(f"n pitchers projected 2027: {n}")
print(f"pt_proj/(4.3*ip_proj): mean {sum(ratios)/n:.3f} median {q(ratios,.5):.3f} "
      f"min {min(ratios):.3f} max {max(ratios):.3f} frac>1.05or<0.95 "
      f"{sum(1 for x in ratios if x>1.05 or x<0.95)/n:.3f}")
print(f"fip shipped - consistent: mean {sum(dfip)/n:+.3f} median {q(dfip,.5):+.3f} "
      f"min {min(dfip):+.3f} max {max(dfip):+.3f}")
print(f"WAR shipped - consistent: mean {sum(dwar)/n:+.3f} median {q(dwar,.5):+.3f} "
      f"max {max(dwar):+.3f} SUM {sum(dwar):+.1f}")
rows.sort(key=lambda r: -abs(r[4] - r[5]))
for r in rows[:5]:
    print(f"  mlbam {r[0]} age {r[2]:.0f} {r[1]}: pt(BF,aged)={r[3]:.1f} ip_proj={r[4]:.1f} "
          f"impliedIP={r[5]:.1f} fip {r[6]:.2f}->{r[7]:.2f} WAR {r[8]:.3f}->{r[9]:.3f}")

hdr("BUG 5: pitcher-batting rows in league hitter totals")
import fa_sources
for season in (2015, 2019, 2021, 2023):
    raw = fa_sources.fetch_statsapi_season_range(season, season)
    inc_so = inc_pa = exc_so = exc_pa = 0.0
    npitch = 0
    for s in raw.get((season, "hitting"), []):
        st = s.get("stat") or {}
        pa = fp._f(st.get("plateAppearances"))
        if pa <= 0:
            continue
        so = fp._f(st.get("strikeOuts"))
        inc_so += so; inc_pa += pa
        pos = ((s.get("position") or {}).get("abbreviation") or "").upper()
        if pos == "P":
            npitch += 1
            continue
        exc_so += so; exc_pa += pa
    print(f"  {season}: pitcher-batting rows {npitch}; K% incl {inc_so/inc_pa:.5f} "
          f"excl {exc_so/exc_pa:.5f} delta {inc_so/inc_pa-exc_so/exc_pa:+.5f} "
          f"(pitcher PA share {(inc_pa-exc_pa)/inc_pa:.4f})")
print("committed corpus league k_pct:",
      {s: round(league[s]["k_pct"], 5) for s in (2019, 2020, 2021, 2022, 2023) if s in league})
