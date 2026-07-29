"""T1.4 - EXPECTED VALUE vs VALUE OF THE EXPECTATION, validated in DOLLARS.

Forward-chained Gate-2 rows whose contract years have all been realized, so
each signing can be scored against its OWN realized tier-priced WAR.

  naive     rational_value_usd(mean path)                 - what ships today
  corrected fa_mc.expected_tier_value_usd(band)           - the integral
  realized  rational_value_usd(ACTUAL war path)           - the target

PRIMARY METRIC: signed BIAS (predicted - realized, $M). The correction should
remove a systematic NEGATIVE bias. If it does not, the bands are miscalibrated
and THAT is the finding.

MANDATORY CONTROL: permute band WIDTHS across players holding point paths
fixed. A width permutation keeps the marginal distribution of widths and
destroys the player-to-width match, so if it moves the bias as much as the
real widths do, the correction is riding the average width and not the
player's own uncertainty.

Usage: python tools/_fa_jensen.py [B]
"""
from __future__ import annotations

import json
import math
import os
import pickle
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))

SCRATCH = (r"C:\Users\noah\AppData\Local\Temp\claude"
           r"\c--Users-noah-baseball-projects-BaseballR"
           r"\c6ce73e3-6700-473f-beea-01f160967961\scratchpad")
CACHE = os.path.join(SCRATCH, "jensen_rows.pkl")

# Winters whose full contract term has realized seasons available. 2026 is the
# in-progress season, so the last fully-realized signing year at a 3-year
# horizon is 2022.
TEST_YEARS = list(range(2018, 2023))
MAX_TERM = 5


def build() -> list[dict]:
    import _fa_lab as lab
    import fa_market as fm
    import fa_projection as fp
    pool = lab.load()
    corpus = fp.build_corpus()
    by_player: dict[str, dict[int, dict]] = {"hit": defaultdict(dict),
                                             "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r
    rows = []
    for W in TEST_YEARS:
        train = [s for s in pool if s["class_year"] < W]
        test = [s for s in pool if s["class_year"] == W]
        if len(train) < 100 or not test:
            continue
        dpw_series = fm.dollars_per_war_by_winter(train)
        model = fm.MarketModel(train, dpw_series)
        model.supply_by_year[W] = fm._supply(test, W)
        dpw = fm.winter_dpw(dpw_series, W)
        infl = fm._destale_rate(dpw_series, W)
        for s in test:
            path = s.get("_war_path") or {}
            p10 = path.get("war_by_year_p10")
            p90 = path.get("war_by_year_p90")
            if not p10 or not p90:
                continue
            pred = model.predict(s)
            yrs = min(int(pred["proj_years"]), MAX_TERM)
            side = s["_side"]
            seasons = by_player[side].get(s.get("mlbam_id")) or {}
            act = []
            ok = True
            for t in range(yrs):
                season = W + t
                if season == 2020 or season > 2025:
                    ok = False
                    break
                row = seasons.get(season)
                act.append(float(row.get("war") or 0.0) if row else 0.0)
            if not ok or len(act) < yrs:
                continue
            rows.append({
                "winter": W, "name": s.get("player_name"),
                "pos": fm._pos_group(s.get("position")), "age": s["_age"],
                "years": yrs, "dpw": dpw, "infl": infl,
                "path": list(path["war_by_year"][:yrs]),
                "p10": list(p10[:yrs]), "p90": list(p90[:yrs]),
                "act": act, "guar": fm._npv_of(s),
                "pred_guar": pred["proj_guarantee_usd"],
            })
        print(f"  winter {W}: {len(rows)} rows cumulative", flush=True)
    with open(CACHE, "wb") as f:
        pickle.dump(rows, f)
    return rows


def load():
    if os.path.exists(CACHE):
        with open(CACHE, "rb") as f:
            return pickle.load(f)
    return build()


def _mean(v):
    v = list(v)
    return math.fsum(float(x) for x in v) / len(v) if v else None


def score(rows, width_permute_seed: int | None = None) -> dict:
    import fa_market as fm
    import fa_mc
    r_disc = fm._discount_rate()
    work = rows
    if width_permute_seed is not None:
        import random
        rng = random.Random(width_permute_seed)
        # PERMUTE THE WIDTHS, hold the point paths fixed. Widths are carried as
        # per-year offsets from the point so they can be transplanted onto a
        # different player without moving his central projection.
        offs = [([p - c for p, c in zip(r["p10"], r["path"])],
                 [p - c for p, c in zip(r["p90"], r["path"])]) for r in rows]
        rng.shuffle(offs)
        work = []
        for r, (lo_off, hi_off) in zip(rows, offs):
            n = len(r["path"])
            lo = [max(0.0, r["path"][t] + (lo_off[t % len(lo_off)]))
                  for t in range(n)]
            hi = [max(0.0, r["path"][t] + (hi_off[t % len(hi_off)]))
                  for t in range(n)]
            work.append({**r, "p10": lo, "p90": hi})
    naive, corrected, realized = [], [], []
    for r in work:
        naive.append(fm.rational_value_usd(r["path"], r["winter"], r["dpw"],
                                           infl=r["infl"]) / 1e6)
        corrected.append(fa_mc.expected_tier_value_usd(
            r["path"], r["p10"], r["p90"], r["years"], r["winter"],
            r["dpw"], r["infl"], r_disc) / 1e6)
        realized.append(fm.rational_value_usd(r["act"], r["winter"], r["dpw"],
                                              infl=r["infl"]) / 1e6)
    return {
        "n": len(work),
        "bias_naive": _mean(p - a for p, a in zip(naive, realized)),
        "bias_corrected": _mean(p - a for p, a in zip(corrected, realized)),
        "mae_naive": _mean(abs(p - a) for p, a in zip(naive, realized)),
        "mae_corrected": _mean(abs(p - a) for p, a in zip(corrected, realized)),
        "mean_naive": _mean(naive), "mean_corrected": _mean(corrected),
        "mean_realized": _mean(realized),
        "lift_pct": 100.0 * (_mean(corrected) - _mean(naive)) / _mean(naive),
    }


def _one_draw(args):
    seed, = args
    import random
    rng = random.Random(seed)
    rows = load()
    by = defaultdict(list)
    for r in rows:
        by[r["winter"]].append(r)
    draw = []
    for _w, rs in by.items():
        n = len(rs)
        draw.extend(rs[rng.randrange(n)] for _ in range(n))
    real = score(draw)
    ctl = score(draw, width_permute_seed=seed)
    return {"real": real, "ctl": ctl}


def boot(B: int = 200, workers: int = 6) -> dict:
    from concurrent.futures import ProcessPoolExecutor
    args = [(7000 + i,) for i in range(B)]
    out = []
    try:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for r in ex.map(_one_draw, args, chunksize=4):
                out.append(r)
    except Exception as exc:                                # noqa: BLE001
        print("pool failed (%s) -- serial" % exc, file=sys.stderr)
        out = [_one_draw(a) for a in args]
    res = {"B": len(out)}
    for k in ("bias", "mae"):
        d = sorted(x["real"][f"{k}_corrected"] - x["real"][f"{k}_naive"]
                   for x in out)
        dc = sorted(x["ctl"][f"{k}_corrected"] - x["ctl"][f"{k}_naive"]
                    for x in out)
        n = len(d)
        res[k] = {
            "naive": _mean(x["real"][f"{k}_naive"] for x in out),
            "corrected": _mean(x["real"][f"{k}_corrected"] for x in out),
            "delta_mean": _mean(d), "delta_sd": statistics.pstdev(d),
            "ci95": [d[int(0.025 * n)], d[min(n - 1, int(0.975 * n))]],
            "mde95": 1.96 * statistics.pstdev(d),
            "ctl_delta_mean": _mean(dc),
            "ctl_band95": [dc[int(0.025 * n)], dc[min(n - 1, int(0.975 * n))]],
        }
    # absolute bias is the thing that should SHRINK
    d = sorted(abs(x["real"]["bias_corrected"]) - abs(x["real"]["bias_naive"])
               for x in out)
    dc = sorted(abs(x["ctl"]["bias_corrected"]) - abs(x["ctl"]["bias_naive"])
                for x in out)
    n = len(d)
    res["abs_bias"] = {"delta_mean": _mean(d), "delta_sd": statistics.pstdev(d),
                       "ci95": [d[int(0.025 * n)], d[min(n - 1, int(0.975 * n))]],
                       "mde95": 1.96 * statistics.pstdev(d),
                       "p_improves": sum(1 for v in d if v < 0) / n,
                       "ctl_delta_mean": _mean(dc),
                       "ctl_band95": [dc[int(0.025 * n)],
                                      dc[min(n - 1, int(0.975 * n))]]}
    return res


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "point"
    if cmd == "build":
        print("rows", len(build()))
    elif cmd == "point":
        rows = load()
        print("real  ", json.dumps(score(rows), indent=1, default=float))
        for sd in (1, 2, 3):
            print(f"ctl{sd}  ", json.dumps(score(rows, width_permute_seed=sd),
                                           default=float))
    elif cmd == "boot":
        B = int(sys.argv[2]) if len(sys.argv) > 2 else 200
        print(json.dumps(boot(B), indent=1, default=float))
