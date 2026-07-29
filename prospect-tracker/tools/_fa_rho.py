"""T1.3 - measure the HORIZON residual correlation the copula needs.

The quantity is NOT the year-over-year correlation of separately-refreshed
one-year projections (that refresh absorbs the persistent part). It is the
correlation, ACROSS HORIZONS, of the residuals of ONE projection made at
signing time and then held: which is exactly what a contract WAR path is.

Anchored forward-chained: for each anchor season Y the aging curves and WAR
map are refit on seasons strictly before Y, one path is built per player, and
residual_h = actual(Y+h-1) - path[h-1] for h = 1..H.

Usage: python tools/_fa_rho.py [H]
"""
from __future__ import annotations

import math
import os
import pickle
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

SCRATCH = (r"C:\Users\noah\AppData\Local\Temp\claude"
           r"\c--Users-noah-baseball-projects-BaseballR"
           r"\c6ce73e3-6700-473f-beea-01f160967961\scratchpad")
CACHE = os.path.join(SCRATCH, "rho_panel.pkl")
H = 5
ANCHORS = list(range(2015, 2022))          # each needs H realized seasons after


def build(h: int = H) -> list[dict]:
    import fa_market as fm
    import fa_projection as fp
    corpus = fp.build_corpus()
    league = corpus["league"]
    by_player: dict[str, dict[int, dict]] = {"hit": defaultdict(dict),
                                             "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r
    out = []
    for Y in ANCHORS:
        curves, war_map = fp.fitted_models(corpus, Y - 1)
        for side in ("hit", "pit"):
            for mlbam, seasons in by_player[side].items():
                hist = [seasons[s] for s in (Y - 1, Y - 2, Y - 3) if s in seasons]
                if not hist:
                    continue
                age_prev = next((x.get("age") for x in hist if x.get("age")), None)
                age = (age_prev + (Y - hist[0]["season"])) if age_prev else None
                path = fm.contract_war_path(hist, side, Y, h, age, curves,
                                            war_map, league, use_ml=False)
                if path is None:
                    continue
                res, acts = [], []
                for t in range(h):
                    season = Y + t
                    if season == 2020:              # 60-game season, excluded
                        res.append(None)
                        acts.append(None)
                        continue
                    row = seasons.get(season)
                    act = float(row.get("war") or 0.0) if row else 0.0
                    acts.append(act)
                    res.append(act - path["war_by_year"][t])
                out.append({"anchor": Y, "mlbam": mlbam, "side": side,
                            "resid": res, "act": acts, "war1": path["war_y1"],
                            "path": path["war_by_year"][:h],
                            "p10": (path.get("war_by_year_p10") or [])[:h],
                            "p90": (path.get("war_by_year_p90") or [])[:h],
                            "expo": path.get("pt_y1"), "age": age,
                            "band_src": path.get("band_source")})
        print(f"  anchor {Y}: {len(out)} rows", flush=True)
    with open(CACHE, "wb") as f:
        pickle.dump(out, f)
    return out


def load():
    if os.path.exists(CACHE):
        with open(CACHE, "rb") as f:
            return pickle.load(f)
    return build()


def _rank(v):
    n = len(v)
    order = sorted(range(n), key=lambda i: v[i])
    rk = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            rk[order[k]] = avg
        i = j + 1
    return rk


def spearman(xs, ys):
    if len(xs) < 3:
        return float("nan")
    rx, ry = _rank(xs), _rank(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def report(rows, h: int = H):
    print(f"n rows {len(rows)}")
    lags = {}
    for lag in range(1, h):
        xs, ys = [], []
        for r in rows:
            for t in range(h - lag):
                a, b = r["resid"][t], r["resid"][t + lag]
                if a is not None and b is not None:
                    xs.append(a)
                    ys.append(b)
        s = spearman(xs, ys)
        lags[lag] = s
        print(f"  lag{lag}: n={len(xs):6d} spearman={s:.4f} "
              f"pearson={statistics.correlation(xs, ys):.4f}")
    r1 = lags.get(1)
    print(f"\n  AR(1) would predict lag2 = lag1^2 = {r1 * r1:.4f}; measured "
          f"{lags.get(2):.4f}")
    print(f"  equicorrelated (one-factor) predicts lag2 = lag1 = {r1:.4f}")
    # the equicorrelated rho that best matches the whole lag profile
    obs = [lags[k] for k in sorted(lags)]
    print(f"  mean of all lags (the one-factor rho estimate) = "
          f"{statistics.mean(obs):.4f}")
    # Spearman -> Gaussian copula correlation: rho = 2 sin(pi rho_S / 6)
    rs = statistics.mean(obs)
    print(f"  Gaussian-copula rho = 2 sin(pi*rho_S/6) = "
          f"{2 * math.sin(math.pi * rs / 6):.4f}")
    return lags


if __name__ == "__main__":
    h = int(sys.argv[1]) if len(sys.argv) > 1 else H
    report(load(), h)
