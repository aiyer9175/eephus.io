"""T1.2 band-width lab (SCRATCH - writes nothing into data/).

Builds the Gate-1 year-1 WAR residual panel WITH covariates, then fits and
grades the location-scale band model against the shipped 4-bucket step
function under docs/EFV_GATE_STANDARD.md:

  1. paired bootstrap resampling TRAIN and TEST with a refit on every draw
  2. a zero-information control (variance function fit on PERMUTED residuals,
     which must return a flat sigma)
  3. a permutation null band
  4. effects averaged over >= 4 independent forward-chained splits

Usage:
    python tools/_fa_bandlab.py panel          # build + cache the panel
    python tools/_fa_bandlab.py fit            # point estimates, all folds
    python tools/_fa_bandlab.py boot [B]       # paired bootstrap
"""
from __future__ import annotations

import json
import math
import os
import pickle
import statistics


def _bmean(vals):
    import math as _m
    v = list(vals)
    return _m.fsum(float(x) for x in v) / len(v)
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

SCRATCH = (r"C:\Users\noah\AppData\Local\Temp\claude"
           r"\c--Users-noah-baseball-projects-BaseballR"
           r"\c6ce73e3-6700-473f-beea-01f160967961\scratchpad")
os.makedirs(SCRATCH, exist_ok=True)
PANEL = os.path.join(SCRATCH, "band_panel.pkl")

TARGETS = list(range(2013, 2026))          # 2013-14 are the shipped warmups
FOLDS = [2021, 2022, 2023, 2024, 2025]     # >= 4 independent forward splits


# ------------------------------------------------------------------ panel ---
def build_panel() -> list[dict]:
    """One row per (player, target season) with the champion year-1 WAR
    prediction, the realization, and the RESTRICTED covariate set.

    Point-in-time throughout: curves/war_map are refit on seasons strictly
    before each target, exactly as fa_backtest.run_projection_gate does, and
    the TJ count is read as-of Jan 1 of the target year."""
    import fa_projection as fp
    import tj_surgery

    corpus = fp.build_corpus()
    league = corpus["league"]
    tj_store = tj_surgery._load_store()
    by_player: dict[str, dict[int, dict]] = {"hit": defaultdict(dict),
                                             "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r

    rows: list[dict] = []
    for target in TARGETS:
        curves, war_map = fp.fitted_models(corpus, target - 1)
        for side in ("hit", "pit"):
            for mlbam, seasons in by_player[side].items():
                hist = [seasons[s] for s in (target - 1, target - 2, target - 3)
                        if s in seasons]
                if not hist:
                    continue
                age_prev = next((h.get("age") for h in hist if h.get("age")), None)
                age = (age_prev + (target - hist[0]["season"])) if age_prev else None
                proj = fp.project_player(hist, side, target, curves, league, age)
                if proj is None:
                    continue
                pred = fp.war_from_projection(proj, side, war_map, league, target)
                act_row = seasons.get(target)
                act = float(act_row.get("war") or 0.0) if act_row else 0.0
                platform = seasons.get(target - 1)
                if side == "hit":
                    vol, full = (platform.get("pa") or 0) if platform else 0, 600.0
                else:
                    vol, full = (platform.get("bf") or 0) if platform else 0, 600.0
                thin = 1.0 if (platform is None or vol < 0.3 * full) else 0.0
                try:
                    tjf = tj_surgery.tj_features(mlbam, f"{target}-01-01", tj_store)
                    tj_n = float(tjf.get("tj_count_pre") or 0)
                except Exception:                       # noqa: BLE001
                    tj_n = 0.0
                rows.append({
                    "season": target, "mlbam": mlbam, "side": side,
                    "pred": float(pred), "act": act, "resid": act - float(pred),
                    "age": float(age) if age else None,
                    "expo": float(proj["pt_proj"]),
                    "role": proj.get("role"),
                    "thin": thin, "tj_n": tj_n,
                    "pos": (act_row or platform or {}).get("pos"),
                })
        print(f"  target {target}: {len(rows)} rows cumulative", flush=True)
    with open(PANEL, "wb") as f:
        pickle.dump(rows, f)
    return rows


def load_panel() -> list[dict]:
    if not os.path.exists(PANEL):
        rows = build_panel()
    else:
        with open(PANEL, "rb") as f:
            rows = pickle.load(f)
    # 2020 is a 60-game season: realized WAR is compressed by ~2.7x, so its
    # residuals are a different scale entirely. The shipped Gate-1 target list
    # excludes it and so does this panel, on both sides of every split.
    return [r for r in rows if r["season"] != 2020]


# ------------------------------------------------------------- band models ---
# The SHIPPED model: 4 buckets (side x exposure hi/lo), empirical q10/q90 of
# the pooled residuals in each bucket, added to the point prediction.
def _bucket(r: dict) -> str:
    lo = 350 if r["side"] == "hit" else 250
    return f"{r['side']}:{'hi' if r['expo'] >= lo else 'lo'}"


def fit_shipped(train: list[dict]) -> dict:
    out = {}
    by = defaultdict(list)
    for r in train:
        by[_bucket(r)].append(r["resid"])
    for b, v in by.items():
        if len(v) >= 50:
            qs = statistics.quantiles(v, n=10)
            out[b] = (qs[0], qs[-1])
    return {"kind": "shipped", "q": out}


def _z_features(r: dict, age_mean: float) -> list[float]:
    """The RESTRICTED covariate set. Deliberately small: every term is a
    quantity a reader could name, and the panel is ~2k rows per fold-year."""
    age = (r["age"] if r["age"] is not None else age_mean)
    return [
        1.0,
        (age - age_mean) / 5.0,
        ((age - age_mean) / 5.0) ** 2,
        1.0 if r["side"] == "pit" else 0.0,
        # log projected value: the scale term. log1p keeps a 0-WAR projection
        # finite and makes the coefficient a per-doubling elasticity.
        math.log1p(max(r["pred"], 0.0)),
        # exposure, in units of a full season
        min(r["expo"] / (600.0 if r["side"] == "hit" else 600.0), 2.0),
        r["thin"],
        min(r["tj_n"], 2.0),
    ]


ZNAMES = ("const", "age", "age^2", "is_pit", "log1p_pred", "expo", "thin", "tj_n")
# E[log(chi2_1)] = digamma(1/2) + log 2 = -1.270363
_LOGCHI2_1 = -1.2703628454614782


def fit_scale(train: list[dict], permute_seed: int | None = None) -> dict:
    """Two-step location-scale fit.

    Step 1  OLS of the residual on z (the location term). The champion point
            forecast is not guaranteed unbiased conditionally, and leaving a
            conditional mean in would be absorbed by the scale as spurious
            variance.
    Step 2  OLS of log(e^2) on z, where e is the step-1 residual, de-biased by
            E[log chi2_1] = -1.270363 so exp(0.5 * (z'g - E)) is a consistent
            sigma. Then the SHAPE is the empirical quantile of the
            standardized residual e/sigma, estimated per side.

    ``permute_seed`` is the ZERO-INFORMATION CONTROL: the residual column is
    row-permuted before fitting, so z carries no information about it and a
    correct estimator must return a flat sigma."""
    import numpy as np
    rows = list(train)
    if permute_seed is not None:
        import random
        rng = random.Random(permute_seed)
        res = [r["resid"] for r in rows]
        rng.shuffle(res)
        rows = [{**r, "resid": v} for r, v in zip(rows, res)]
    ages = [r["age"] for r in rows if r["age"] is not None]
    age_mean = _bmean(ages) if ages else 29.0
    Z = np.asarray([_z_features(r, age_mean) for r in rows], dtype=float)
    y = np.asarray([r["resid"] for r in rows], dtype=float)
    beta, *_ = np.linalg.lstsq(Z, y, rcond=None)
    e = y - Z @ beta
    l2 = np.log(np.maximum(e * e, 1e-6))
    gamma, *_ = np.linalg.lstsq(Z, l2, rcond=None)
    sig = np.exp(0.5 * (Z @ gamma - _LOGCHI2_1))
    sig = np.clip(sig, 0.05, 10.0)
    u = e / sig
    shape = {}
    for side in ("hit", "pit"):
        idx = [i for i, r in enumerate(rows) if r["side"] == side]
        if len(idx) >= 200:
            us = sorted(float(u[i]) for i in idx)
            shape[side] = us
    return {"kind": "scale", "beta": beta.tolist(), "gamma": gamma.tolist(),
            "age_mean": age_mean, "shape": shape}


def _emp_q(sorted_vals: list[float], tau: float) -> float:
    if not sorted_vals:
        return 0.0
    n = len(sorted_vals)
    i = tau * (n - 1)
    lo, hi = int(math.floor(i)), int(math.ceil(i))
    return sorted_vals[lo] + (i - lo) * (sorted_vals[hi] - sorted_vals[lo])


def predict_band(model: dict, r: dict, taus) -> dict:
    """{tau: predicted WAR quantile} for one row."""
    if model["kind"] == "shipped":
        q = model["q"].get(_bucket(r))
        if not q:
            return {}
        # The shipped artifact carries ONLY q10/q90. Anything else it cannot
        # answer, which is itself part of the finding.
        out = {}
        for t in taus:
            if abs(t - 0.10) < 1e-9:
                out[t] = r["pred"] + q[0]
            elif abs(t - 0.90) < 1e-9:
                out[t] = r["pred"] + q[1]
            elif abs(t - 0.50) < 1e-9:
                out[t] = r["pred"]
        return out
    import numpy as np
    z = np.asarray(_z_features(r, model["age_mean"]), dtype=float)
    mu = r["pred"] + float(z @ np.asarray(model["beta"]))
    sig = float(np.exp(0.5 * (z @ np.asarray(model["gamma"]) - _LOGCHI2_1)))
    sig = min(max(sig, 0.05), 10.0)
    sh = model["shape"].get(r["side"]) or model["shape"].get("hit") or []
    return {t: mu + sig * _emp_q(sh, t) for t in taus}


def sigma_of(model: dict, r: dict) -> float:
    if model["kind"] == "shipped":
        q = model["q"].get(_bucket(r))
        return ((q[1] - q[0]) / 2.5631) if q else float("nan")
    import numpy as np
    z = np.asarray(_z_features(r, model["age_mean"]), dtype=float)
    return float(min(max(math.exp(0.5 * (z @ np.asarray(model["gamma"]) - _LOGCHI2_1)),
                         0.05), 10.0))


# ------------------------------------------------------------------ score ---
TAUS = (0.10, 0.50, 0.90)


def score_fold(model: dict, test: list[dict], taus=TAUS) -> dict:
    import fa_calibration as fc
    rows = []
    for r in test:
        q = predict_band(model, r, taus)
        if len(q) < len(taus):
            continue
        rows.append({"y": r["act"], "q": q, **r})
    if not rows:
        return {}
    out = {
        "n": len(rows),
        "cov": fc.coverage(rows, 0.10, 0.90)["coverage"],
        "pin10": _bmean(fc.pinball(r["y"], r["q"][0.10], 0.10) for r in rows),
        "pin90": _bmean(fc.pinball(r["y"], r["q"][0.90], 0.90) for r in rows),
        "crps3": _bmean(fc.crps_from_quantiles(r["y"], r["q"]) for r in rows),
        "pit_hump": None,
    }
    out["pin_avg"] = (out["pin10"] + out["pin90"]) / 2.0
    # conditional coverage on the four pre-registered conditioners
    cond = {
        "pred_decile": fc.conditional_coverage(rows, lambda r: r["pred"], n_bins=10),
        "age": fc.conditional_coverage(
            rows, lambda r: ("<25" if (r["age"] or 29) < 25 else
                             "25-29" if (r["age"] or 29) < 30 else
                             "30-34" if (r["age"] or 29) < 35 else "35+")),
        "expo_decile": fc.conditional_coverage(rows, lambda r: r["expo"], n_bins=10),
        "tj": fc.conditional_coverage(rows, lambda r: ("tj" if r["tj_n"] >= 1 else "none")),
    }
    out["cond"] = cond
    # ONE headline number for conditional miscalibration: the rms deviation
    # of binned coverage from nominal, pooled over all four conditioners.
    devs = [c["coverage"] - 0.80 for tab in cond.values() for c in tab
            if c.get("coverage") is not None and c["n"] >= 30]
    out["cond_rmse"] = math.sqrt(_bmean(d * d for d in devs)) if devs else None
    out["cond_maxabs"] = max((abs(d) for d in devs), default=None)
    out["sigma_sd"] = statistics.pstdev([sigma_of(model, r) for r in test])
    out["sigma_mean"] = _bmean([sigma_of(model, r) for r in test])
    return out


def chain(panel: list[dict], permute_seed: int | None = None,
          folds=FOLDS) -> dict:
    """Forward-chained: train strictly before each fold year, test on it."""
    out = {"folds": [], }
    agg = defaultdict(lambda: defaultdict(list))
    for W in folds:
        train = [r for r in panel if r["season"] < W]
        test = [r for r in panel if r["season"] == W]
        if len(train) < 500 or not test:
            continue
        ship = fit_shipped(train)
        scale = fit_scale(train, permute_seed=permute_seed)
        s_ship = score_fold(ship, test)
        s_scale = score_fold(scale, test)
        out["folds"].append({"winter": W, "n": s_ship.get("n"),
                             "shipped": {k: v for k, v in s_ship.items() if k != "cond"},
                             "scale": {k: v for k, v in s_scale.items() if k != "cond"},
                             "cond_scale": s_scale.get("cond"),
                             "cond_ship": s_ship.get("cond")})
        for m, s in (("shipped", s_ship), ("scale", s_scale)):
            for k in ("cov", "pin10", "pin90", "pin_avg", "crps3",
                      "cond_rmse", "cond_maxabs", "sigma_sd", "sigma_mean"):
                if s.get(k) is not None:
                    agg[m][k].append(s[k])
    out["mean"] = {m: {k: _bmean(v) for k, v in d.items()}
                   for m, d in agg.items()}
    return out


# ------------------------------------------------------- paired bootstrap ---
def _resample(panel, rng):
    by = defaultdict(list)
    for r in panel:
        by[r["season"]].append(r)
    out = []
    for _y, rows in by.items():
        n = len(rows)
        out.extend(rows[rng.randrange(n)] for _ in range(n))
    return out


_PANEL_CACHE = None


def _one_draw(args):
    global _PANEL_CACHE
    seed, = args
    import random
    if _PANEL_CACHE is None:
        _PANEL_CACHE = load_panel()
    rng = random.Random(seed)
    draw = _resample(_PANEL_CACHE, rng)
    r = chain(draw)
    # PERMUTATION NULL on the same draw: the identical estimator fit on a
    # row-permuted residual column. Its delta-vs-shipped distribution is the
    # null band the real delta has to clear.
    rp = chain(draw, permute_seed=seed)
    m, mp = r["mean"], rp["mean"]
    keys = ("cov", "pin_avg", "crps3", "cond_rmse", "cond_maxabs", "sigma_sd")
    return {"shipped": {k: m["shipped"][k] for k in keys},
            "scale": {k: m["scale"][k] for k in keys},
            "perm": {k: mp["scale"][k] for k in keys}}


def boot(B: int = 200, workers: int = 6) -> dict:
    from concurrent.futures import ProcessPoolExecutor
    draws = []
    args = [(2000 + i,) for i in range(B)]
    try:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for r in ex.map(_one_draw, args, chunksize=4):
                draws.append(r)
    except Exception as exc:                       # noqa: BLE001
        print("pool failed (%s) -- falling back to serial" % exc, file=sys.stderr)
        draws = [_one_draw(a) for a in args]
    res = {"B": len(draws)}
    for k in ("pin_avg", "crps3", "cond_rmse", "cond_maxabs", "sigma_sd", "cov"):
        d = sorted(x["scale"][k] - x["shipped"][k] for x in draws)
        dp = sorted(x["perm"][k] - x["shipped"][k] for x in draws)
        n = len(d)
        res[k] = {
            "shipped_mean": _bmean(x["shipped"][k] for x in draws),
            "scale_mean": _bmean(x["scale"][k] for x in draws),
            "delta_mean": _bmean(d),
            "delta_sd": statistics.pstdev(d),
            "ci95": [d[int(0.025 * n)], d[min(n - 1, int(0.975 * n))]],
            "p_improves": sum(1 for v in d if v < 0) / n,
            # zero-information control on identical draws
            "perm_delta_mean": _bmean(dp),
            "perm_delta_sd": statistics.pstdev(dp),
            "perm_null_band95": [dp[int(0.025 * n)], dp[min(n - 1, int(0.975 * n))]],
            # MDE95: the half-width of the paired-bootstrap 95% interval, i.e.
            # the smallest delta this instrument can resolve.
            "mde95": 1.96 * statistics.pstdev(d),
        }
    return res


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "fit"
    if cmd == "panel":
        p = build_panel()
        print("panel rows", len(p))
    elif cmd == "fit":
        p = load_panel()
        r = chain(p)
        print(json.dumps({"mean": r["mean"],
                          "folds": [{k: v for k, v in f.items()
                                     if not k.startswith("cond_")}
                                    for f in r["folds"]]},
                         indent=1, default=float))
    elif cmd == "cond":
        p = load_panel()
        r = chain(p)
        f = r["folds"][-1]
        print("FOLD", f["winter"])
        for name in f["cond_scale"]:
            print(f"-- {name}")
            for a, b in zip(f["cond_ship"][name], f["cond_scale"][name]):
                print(f"   {str(a['bin']):8} n={a['n']:5} shipped {a['coverage']} "
                      f"scale {b['coverage']}")
    elif cmd == "ctl":
        p = load_panel()
        for sd in (1, 2, 3):
            r = chain(p, permute_seed=sd)
            print(f"permute seed {sd}: ",
                  json.dumps({k: round(v, 5) for k, v in r["mean"]["scale"].items()},
                             default=float))
    elif cmd == "boot":
        B = int(sys.argv[2]) if len(sys.argv) > 2 else 200
        print(json.dumps(boot(B), indent=1, default=float))
