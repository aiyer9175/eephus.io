"""Read-only: how much of the FA WAR-map residual is DEFENSE? Writes nothing."""
import json, math, statistics as st, sys
from collections import defaultdict
sys.path.insert(0, ".")
import fa_projection as fp

corpus = fp.build_corpus()
league = corpus["league"]
war_map = fp.fit_war_map(corpus, max_season=2026)
print("hit war_map:", war_map["hit"])
print("pit war_map:", war_map["pit"])

defh = json.load(open("data/mlb_def_history.json"))["rows"]
a = fp._pcfg()["assembly"]
rows = []
for r in corpus["hit"]:
    if r.get("war") is None or (r.get("pa") or 0) < 200:
        continue
    lg = league.get(r["season"]) or {}
    if not lg.get("woba"):
        continue
    woba = fp._assemble_hitter({**r, "babip": r.get("babip") or lg.get("babip")},
                               league, r["season"] + 1)["woba_proj"]
    wraa_pa = (woba - lg["woba"]) / a["woba_scale"]
    pa6 = r["pa"] / 600.0
    c = war_map["hit"]["coef"]
    pred = c[0] + c[1]*pa6 + c[2]*(wraa_pa*r["pa"]/10.0) + c[3]*(1.0 if r["role"] == "C" else 0.0)*pa6
    dv = defh.get(f'{r["mlbam"]}:{r["season"]}')
    if dv is None:
        continue
    rows.append({"resid": r["war"] - pred, "war_def": dv["war_def"],
                 "runs_pos": dv["runs_position"], "pa": r["pa"],
                 "role": r["role"], "war": r["war"], "pred": pred})

print(f"\nn hitter-seasons (PA>=200, def joined) = {len(rows)}")


def corr(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x-mx)**2 for x in xs) * sum((y-my)**2 for y in ys))
    return num/den if den else 0.0


resid = [r["resid"] for r in rows]
dtot = [r["war_def"] + r["runs_pos"] for r in rows]
print(f"residual sd = {st.pstdev(resid):.3f} WAR   MAE = {st.mean(abs(x) for x in resid):.3f}")
print(f"corr(residual, war_def)                = {corr(resid, [r['war_def'] for r in rows]):+.3f}")
print(f"corr(residual, runs_position)          = {corr(resid, [r['runs_pos'] for r in rows]):+.3f}")
print(f"corr(residual, war_def + runs_position)= {corr(resid, dtot):+.3f}  "
      f"-> R^2 {corr(resid, dtot)**2:.3f} of the residual variance")

print("\nresidual by defensive quintile (war_def + runs_position):")
srt = sorted(rows, key=lambda r: r["war_def"] + r["runs_pos"])
n = len(srt)
for i in range(5):
    sl = srt[i*n//5:(i+1)*n//5]
    print(f"   Q{i+1}  def={st.mean(x['war_def']+x['runs_pos'] for x in sl):+6.2f}  "
          f"n={len(sl):5d}  mean residual = {st.mean(x['resid'] for x in sl):+.3f} WAR  "
          f"(model {'under' if st.mean(x['resid'] for x in sl) > 0 else 'over'}-rates them)")

# by listed primary position from positions_played (prospect-side file) is prospect-only;
# use the ROLE flag the corpus actually carries plus the def spread instead.
print("\nspread between the best and worst defensive quintile:",
      f"{st.mean(x['resid'] for x in srt[4*n//5:]) - st.mean(x['resid'] for x in srt[:n//5]):+.3f} WAR/season")
