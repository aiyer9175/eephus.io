# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The xM$ lab: the one producer of data/xm_eval.json.

Registered in docs/xm/XM_GATE.md (committed alone, 70864a33) before this file
existed. The read runs in the gate's section 13 order and rewrites the
artifact after every step, recording the step in `order`:

  1. dry run on a synthetic fixture with nulls (--dry-run, scratch only)
  2. planted recovery (P1 censoring, P2a signal, P2b permuted null)
  3. development read, every candidate and comparator; selection written
  4. holdout read, ONCE: the selected challenger, the incumbent, NULL 1, the
     constant comparator and MLB Trade Rumors; pass rule and verdict written
  5. counterfactual extension, anchors and Fair $ on the served model

USAGE
    python tools/xm_lab.py --dry-run [--out DIR]     # fixture, never data/
    python tools/xm_lab.py --read                    # the one read
    python tools/xm_lab.py --resume-holdout          # steps 4-5 once (XM1-Q1)

--read refuses when data/xm_eval.json already holds a holdout block. It reads
cached pages only (scrapers.cache_only) and fetches nothing. It never calls
fa_export, never writes data/fa_gate2_eval.json or data/fa_dpw_series.json,
and never runs backtest.run_backtest.
"""

from __future__ import annotations

import argparse
import faulthandler
import hashlib
import json
import math
import random
import statistics
import subprocess
import sys
import traceback
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import xm  # noqa: E402

OUT_PATH = ROOT / "data" / "xm_eval.json"
GATE_DOC = ROOT / "docs" / "xm" / "XM_GATE.md"
GATE_COMMIT = "70864a33"
MLBTR_PATH = ROOT / "data" / "_labs" / "fa_predictions" / "mlbtr_retro_2015_2025.json"
IL_PATH = ROOT / ".cache" / "mlb_transactions" / "il_table.json"
CANDIDATES = ("a_incumbent", "b_hurdle", "c_gbm")
MLBTR_MIN_PAIRED = 60
PLANT_SIGMA = 0.45
PLANT_OK_RMSE = 0.10
PLANT_ORACLE_RATIO = 1.15


# ============================================================================
# Inputs
# ============================================================================

class Inputs:
    """Everything the read needs, all as of each winter."""

    def __init__(self):
        self.mlb: list[dict] = []        # scored MLB-deal rows
        self.floor: list[dict] = []      # censored floor rows
        self.league_min: dict[int, float] = {}
        self.demand: dict[int, int] = {}
        self.flat_dpw: float = 0.0
        self.disc_rate: float = 0.07
        self.mlbtr: dict[tuple, dict] = {}
        self.coverage: dict = {}
        self.posting: dict = {}


def _league_min(lm: dict, season: int) -> float:
    if season in lm:
        return float(lm[season])
    return float(lm[max(y for y in lm if y <= season)] if any(y <= season for y in lm)
                 else min(lm.values()))


def _il_table() -> dict[int, dict[int, tuple]]:
    try:
        raw = json.loads(IL_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {int(p): {int(y): (float(v[0]), int(v[1])) for y, v in yrs.items()}
            for p, yrs in (raw.get("il") or {}).items()}


def _label_fields(r: dict, lm: dict) -> None:
    import fa_market as fm
    W = int(r["class_year"])
    r["_log_floor"] = math.log(_league_min(lm, W))
    r["_cluster"] = r.get("player_key") or r.get("player_name")
    if r["_kind"] == "mlb":
        npv = fm._npv_of(r)
        yrs = float(r["years"])
        r["_log_total"] = math.log(max(npv, 1.0))
        r["_years"] = yrs
        r["_log_aav"] = math.log(max(npv / yrs, 1.0))


def real_inputs() -> Inputs:
    import arb_dataset
    import fa_class
    import fa_fit_backtest as fb
    import fa_market as fm
    import fa_projection as fp
    import storage
    fm.LAB_RESET()
    inp = Inputs()
    inp.disc_rate = fm._discount_rate()
    inp.flat_dpw = float(fa_class._flat_dpw_usd())
    lm = arb_dataset.league_min_by_year()
    for y in range(2015, xm.SERVE_WINTER + 1):
        inp.league_min[y] = _league_min(lm, y)
    for W in range(2015, xm.SERVE_WINTER + 1):
        pay = fb.team_payroll_state(W - 1) or {}
        tax = {k: (v or {}).get("tax_payroll_usd") for k, v in pay.items()}
        inp.demand[W] = xm.demand_count(tax, fm._cbt_threshold_or_earliest(W))
    il = _il_table()
    corpus = fp.build_corpus()
    league = corpus["league"]
    by_player = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r
    inp._corpus, inp._by_player, inp._il = corpus, by_player, il

    def static(r, side, path_years, age, W):
        mid = r.get("mlbam_id") or r.get("mlbam")
        return xm.static_features(
            age=age, war_by_year=path_years, side=side, position=r.get("position"),
            qo=r.get("qo"), seasons=by_player[side].get(mid) or {},
            il_seasons=(il.get(int(mid)) or {}) if mid else {}, winter=W,
            demand=inp.demand[W], disc_rate=inp.disc_rate)

    enriched = fm.enriched_signings(2015, 2026)
    seen = set()
    for s in enriched:
        r = dict(s)
        r["_kind"] = "mlb"
        r["_xm"] = static(r, r["_side"], r["_war_path"]["war_by_year"], r["_age"], r["class_year"])
        _label_fields(r, lm)
        inp.mlb.append(r)
        seen.add((r.get("player_key"), r["class_year"]))

    # Floor rows: the same as-of path machinery, one-year term (gate section 3).
    skipped_floor = {"no_mlbam": 0, "no_history": 0, "no_path": 0}
    post = {"rows": [], "no_mlbam": 0}
    for year in range(2015, 2027):
        curves, war_map = fp.fitted_models(corpus, year - 1, use_def=fm.FA_PRICING_USE_DEF)
        for s in storage.load_fa_signings(year).values():
            mlb = bool(s.get("mlb_deal"))
            if mlb and (s.get("player_key"), year) in seen:
                continue
            if mlb and not (s.get("years") and s.get("guarantee_usd")):
                continue
            mid = s.get("mlbam_id")
            side = "pit" if fm._pos_group(s.get("position")) in ("SP", "RP") else "hit"
            seasons = by_player[side].get(mid) or {} if mid else {}
            hist = [seasons[t] for t in (year - 1, year - 2, year - 3) if t in seasons]
            if mlb:
                # an MLB deal the enrichment skipped: the posting anchor set
                if not mid:
                    post["no_mlbam"] += 1
                    continue
                if not hist:
                    post["rows"].append({"player": s.get("player_name"), "class_year": year,
                                         "years": int(s["years"]),
                                         "guarantee_usd": int(s["guarantee_usd"]),
                                         "position": s.get("position")})
                continue
            if not mid:
                skipped_floor["no_mlbam"] += 1
                continue
            if not hist:
                skipped_floor["no_history"] += 1
                continue
            age_row = next((h for h in hist if h.get("age")), None)
            age = (age_row["age"] + (year - age_row["season"])) if age_row else None
            path = fm.contract_war_path(hist, side, year, 1, age, curves, war_map, league,
                                        use_ml=False) if age is not None else None
            if path is None:
                skipped_floor["no_path"] += 1
                continue
            r = {**s, "_war_path": path, "_age": age, "_side": side, "_kind": "floor",
                 "class_year": year}
            r["_xm"] = static(r, side, path["war_by_year"], age, year)
            _label_fields(r, lm)
            inp.floor.append(r)
    inp.posting = post

    # MLB Trade Rumors retro rows, keyed (class_year, mlbam)
    try:
        doc = json.loads(MLBTR_PATH.read_text(encoding="utf-8"))
        for _off, blk in (doc.get("seasons") or {}).items():
            cy = int(blk.get("class_year"))
            for row in blk.get("rows") or []:
                if row.get("mlbam_id") and row.get("pred_total_mm") and row.get("pred_years"):
                    inp.mlbtr[(cy, int(row["mlbam_id"]))] = row
    except (OSError, ValueError):
        pass
    inp.coverage = {
        "mlb_rows": len(inp.mlb), "floor_rows": len(inp.floor),
        "mlb_rows_by_winter": dict(sorted(_count(inp.mlb).items())),
        "floor_rows_by_winter": dict(sorted(_count(inp.floor).items())),
        "floor_skipped": skipped_floor,
        "posting_set_rows": len(post["rows"]), "mlb_deals_no_mlbam": post["no_mlbam"],
        "il_table_seasons": sorted({y for v in il.values() for y in v}),
        "il_prior_season_covered_winters": [W for W in range(2015, 2027) if W - 1 >= 2015],
        "demand_by_winter": {str(k): v for k, v in sorted(inp.demand.items())},
        "league_min_by_winter": {str(k): v for k, v in sorted(inp.league_min.items())},
        "mlbtr_rows_with_price": len(inp.mlbtr),
        "flat_dpw_usd": inp.flat_dpw, "discount_rate": inp.disc_rate,
    }
    return inp


def _count(rows) -> dict:
    out = defaultdict(int)
    for r in rows:
        out[int(r["class_year"])] += 1
    return {str(k): v for k, v in out.items()}


# ============================================================================
# One fold: fit on the training winters, predict the test rows
# ============================================================================

class Ctx:
    """Fold context: the $/WAR index from the training rows only and the class
    supply z on the training winters' moments (the incumbent's convention:
    the test winter's own class counts are known at the winter start)."""

    def __init__(self, train_mlb, test_mlb, W, inp: Inputs):
        import fa_market as fm
        self.series = fm.dollars_per_war_by_winter(train_mlb)
        self.flat = inp.flat_dpw
        counts = defaultdict(float)
        for r in train_mlb:
            counts[(int(r["class_year"]), fm._pos_group(r.get("position")))] += 1.0
        tr_vals = list(counts.values())
        for r in test_mlb:
            counts[(int(W), fm._pos_group(r.get("position")))] += 1.0 if int(r["class_year"]) == int(W) else 0.0
        self.counts = counts
        self.mean = statistics.mean(tr_vals) if tr_vals else 0.0
        self.sd = (statistics.pstdev(tr_vals) if len(tr_vals) > 1 else 1.0) or 1.0
        self._idx = {}

    def index(self, w: int) -> float:
        if w not in self._idx:
            self._idx[w] = xm.dpw_index(self.series, int(w), self.flat)
        return self._idx[w]

    def supply_z(self, r) -> float:
        import fa_market as fm
        c = self.counts.get((int(r["class_year"]), fm._pos_group(r.get("position"))), 0.0)
        return (c - self.mean) / self.sd

    def F(self, rows) -> np.ndarray:
        if not rows:
            return np.zeros((0, len(xm.FEATURES)))
        return np.array([xm.feature_vector(r["_xm"], self.index(r["class_year"]),
                                           self.supply_z(r)) for r in rows])


def _arr(rows, key):
    return np.array([r[key] for r in rows], dtype=float)


def fit_predict(cand: str, train_mlb, train_floor, test_rows, W, inp: Inputs,
                supply_rows=None, seed: int = xm.SEED) -> dict:
    """Fit ``cand`` on the training rows and predict ``test_rows`` (winter W).
    Returns years_f, log_total and the in-sample band offsets (q10, q90).
    ``supply_rows`` are the MLB rows whose counts set winter W's class supply
    (default: the MLB rows among test_rows)."""
    import fa_market as fm
    sup = [r for r in (supply_rows if supply_rows is not None else test_rows)
           if r.get("_kind", "mlb") == "mlb"]
    out: dict = {}
    if cand == "a_incumbent":
        model = fm.MarketModel(train_mlb, fm.dollars_per_war_by_winter(train_mlb))
        model.supply_by_year[W] = fm._supply(sup, W)
        yrs, lt, lo, hi = [], [], [], []
        for r in test_rows:
            p = model.predict(r)
            g = max(float(p["proj_guarantee_usd"]), 1.0)
            yrs.append(float(p["proj_years"]))
            lt.append(math.log(g))
            if p.get("proj_guarantee_p10_usd"):
                lo.append(math.log(max(p["proj_guarantee_p10_usd"], 1.0)) - math.log(g))
                hi.append(math.log(max(p["proj_guarantee_p90_usd"], 1.0)) - math.log(g))
        out["years_f"] = np.array(yrs)
        out["log_total"] = np.array(lt)
        q = xm.band_quantiles(model.resid_log_guar)
        out["q"] = (statistics.median(lo), statistics.median(hi)) if lo else q
        return out
    ctx = Ctx(train_mlb, sup, W, inp)
    Ftr = ctx.F(train_mlb)
    Fte = ctx.F(test_rows)
    lf_te = np.array([r["_log_floor"] for r in test_rows]) if test_rows else np.zeros(0)
    if cand == "b_hurdle":
        Ffl = ctx.F(train_floor)
        m = xm.Hurdle().fit(Ftr, _arr(train_mlb, "_years"), _arr(train_mlb, "_log_aav"),
                            Ffl, np.array([r["_log_floor"] for r in train_floor]),
                            _arr(train_mlb, "_log_floor"))
        ins = m.predict(Ftr, _arr(train_mlb, "_log_floor"))
        pr = m.predict(Fte, lf_te) if len(test_rows) else {"years_f": np.zeros(0), "log_total": np.zeros(0)}
        out["p_mlb"] = m.p_mlb(Fte) if len(test_rows) else np.zeros(0)
        out["_model"] = m
    elif cand == "c_gbm":
        m = xm.GBM().fit(Ftr, _arr(train_mlb, "_years"), _arr(train_mlb, "_log_aav"), seed=seed)
        ins = m.predict(Ftr)
        pr = m.predict(Fte) if len(test_rows) else {"years_f": np.zeros(0), "log_total": np.zeros(0)}
        out["_model"] = m
    elif cand == "null1":
        m = xm.Null1().fit(_arr(train_mlb, "_age"), _arr(train_mlb, "_years"))

        def _p(rows):
            return m.predict([r["_age"] for r in rows], [r["_xm"]["plat_war"] for r in rows],
                             [ctx.index(r["class_year"]) for r in rows],
                             [inp.league_min[int(r["class_year"])] for r in rows])
        ins = _p(train_mlb)
        pr = _p(test_rows) if test_rows else {"years_f": np.zeros(0), "log_total": np.zeros(0)}
    elif cand == "const":
        import fa_market as fm2
        by = defaultdict(list)
        for r in train_mlb:
            by[fm2._pos_group(r.get("position"))].append(r["_log_total"])
        allv = [r["_log_total"] for r in train_mlb]
        med = {g: statistics.median(v) for g, v in by.items()}
        yby = defaultdict(list)
        for r in train_mlb:
            yby[fm2._pos_group(r.get("position"))].append(r["_years"])
        ymed = {g: statistics.median(v) for g, v in yby.items()}

        def _p(rows):
            gs = [fm2._pos_group(r.get("position")) for r in rows]
            return {"log_total": np.array([med.get(g, statistics.median(allv)) for g in gs]),
                    "years_f": np.array([ymed.get(g, 1.0) for g in gs])}
        ins = _p(train_mlb)
        pr = _p(test_rows) if test_rows else {"years_f": np.zeros(0), "log_total": np.zeros(0)}
    else:
        raise ValueError(cand)
    out["years_f"] = np.asarray(pr["years_f"], dtype=float)
    out["log_total"] = np.asarray(pr["log_total"], dtype=float)
    out["q"] = xm.band_quantiles(_arr(train_mlb, "_log_total") - ins["log_total"])
    return out


def conformal_q(cand, train_mlb, train_floor, inp: Inputs, seed: int = xm.SEED):
    """Winter-blocked conformal offsets (gate section 5): P10/P90 of the
    out-of-sample residuals of an inner forward chain over the training
    winters, from the fifth winter on."""
    winters = sorted({int(r["class_year"]) for r in train_mlb})
    res = []
    for w in winters[4:]:
        tr = [r for r in train_mlb if r["class_year"] < w]
        fl = [r for r in train_floor if r["class_year"] < w]
        te = [r for r in train_mlb if r["class_year"] == w]
        if len(tr) < 100 or not te:
            continue
        p = fit_predict(cand, tr, fl, te, w, inp, seed=seed)
        res.extend((_arr(te, "_log_total") - p["log_total"]).tolist())
    return xm.band_quantiles(res), len(res)


def run_chain(cands, winters, inp: Inputs, mlb=None, floor=None, band=None,
              seed: int = xm.SEED) -> dict:
    """Forward-chained read over ``winters``. Returns per-candidate rows:
    {cand: {"rows": [...], "pred": {...arrays...}}} with the test rows in a
    fixed order shared by every candidate (paired scoring)."""
    mlb = inp.mlb if mlb is None else mlb
    floor = inp.floor if floor is None else floor
    band = band or {}
    out = {c: {"y": [], "p50": [], "p10": [], "p90": [], "yp": [], "ya": [], "w": [],
               "cl": [], "key": [], "p_mlb_rows": [], "rows": []} for c in cands}
    for W in winters:
        tr = [r for r in mlb if r["class_year"] < W]
        fl = [r for r in floor if r["class_year"] < W]
        te = [r for r in mlb if r["class_year"] == W]
        te_fl = [r for r in floor if r["class_year"] == W]
        if len(tr) < 100 or not te:
            continue
        for c in cands:
            p = fit_predict(c, tr, fl, te + te_fl if c == "b_hurdle" else te, W, inp,
                            supply_rows=te, seed=seed)
            n = len(te)
            q = p["q"]
            if band.get(c) == "conformal":
                q, _ = conformal_q(c, tr, fl, inp, seed=seed)
            lo, hi = xm.apply_band(p["log_total"][:n], q)
            o = out[c]
            o["y"].extend(_arr(te, "_log_total").tolist())
            o["p50"].extend(p["log_total"][:n].tolist())
            o["p10"].extend(lo.tolist())
            o["p90"].extend(hi.tolist())
            o["yp"].extend(p["years_f"][:n].tolist())
            o["ya"].extend(_arr(te, "_years").tolist())
            o["w"].extend([W] * n)
            o["cl"].extend([r["_cluster"] for r in te])
            o["key"].extend([(W, r.get("player_key")) for r in te])
            o["rows"].extend(te)
            if c == "b_hurdle":
                pm = p["p_mlb"]
                o["p_mlb_rows"].extend(list(zip(pm.tolist(), [1] * n + [0] * len(te_fl))))
    return out


def score(o: dict) -> dict:
    m = xm.metrics(o["y"], o["p50"], o["p10"], o["p90"], o["yp"], o["ya"])
    if not o["y"]:
        return m
    y = np.array(o["y"])
    p = np.array(o["p50"])
    ya = np.array(o["ya"])
    yp = np.maximum(np.array(o["yp"]), 1.0)
    m["log_aav_mae"] = float(np.abs((y - np.log(ya)) - (p - np.log(yp))).mean())
    m["guarantee_mae_mm"] = float(np.abs(np.exp(y) - np.exp(p)).mean() / 1e6)
    mega = np.exp(y) >= 100e6
    m["mega_n"] = int(mega.sum())
    m["mega_guarantee_mae_mm"] = (float(np.abs(np.exp(y[mega]) - np.exp(p[mega])).mean() / 1e6)
                                  if mega.any() else None)
    per = {}
    for w in sorted(set(o["w"])):
        idx = [i for i, v in enumerate(o["w"]) if v == w]
        per[str(w)] = xm.metrics([o["y"][i] for i in idx], [o["p50"][i] for i in idx],
                                 [o["p10"][i] for i in idx], [o["p90"][i] for i in idx],
                                 [o["yp"][i] for i in idx], [o["ya"][i] for i in idx])
    m["per_winter"] = per
    if o.get("p_mlb_rows"):
        pr = np.array([a for a, _ in o["p_mlb_rows"]])
        lab = np.array([b for _, b in o["p_mlb_rows"]])
        m["p_mlb_brier"] = float(((pr - lab) ** 2).mean())
        m["p_mlb_rows"] = int(len(lab))
        m["p_mlb_floor_rows"] = int((lab == 0).sum())
    return m


def paired(o_cmp: dict, o_cand: dict, B: int = 4000, seed: int = xm.SEED) -> dict:
    assert o_cmp["key"] == o_cand["key"], "paired rows differ"
    e_cmp = np.abs(np.array(o_cmp["y"]) - np.array(o_cmp["p50"]))
    e_c = np.abs(np.array(o_cand["y"]) - np.array(o_cand["p50"]))
    return xm.cluster_lo95(e_cmp, e_c, o_cand["cl"], B=B, seed=seed)


# ============================================================================
# Planted recovery (gate section 10)
# ============================================================================

_TRUE_FEATS = ("age", "war_y1", "war_3", "war_tot", "plat_war", "war_3y", "pos_sp",
               "pos_rp", "pos_c", "pos_prem", "gs_share", "il_prior1", "il_3y", "qo", "demand")


def _true_X(rows, log_years=None) -> np.ndarray:
    X = np.array([[r["_xm"][k] for k in _TRUE_FEATS] for r in rows], dtype=float)
    X = np.column_stack([X, (X[:, 0] - 30.0) ** 2])
    if log_years is not None:
        X = np.column_stack([X, log_years])
    return X


def planted(inp: Inputs, dev, cands, seed: int = xm.SEED) -> dict:
    dev_through = max(dev)
    rng = np.random.default_rng(seed)
    mlb = [r for r in inp.mlb if r["class_year"] <= dev_through]
    flo = [r for r in inp.floor if r["class_year"] <= dev_through]
    out: dict = {}
    # ---- P1 censoring -----------------------------------------------------
    rows = mlb + flo
    ly = np.array([math.log(r["_years"]) if r["_kind"] == "mlb" else 0.0 for r in rows])
    X = _true_X(rows, ly)
    std = xm._Std(X)
    Z = std(X)
    A = np.column_stack([np.ones(len(Z)), Z])
    ym = np.array([r["_log_aav"] for r in mlb])
    b_true, *_ = np.linalg.lstsq(A[:len(mlb)], ym, rcond=None)
    mu = A @ b_true
    lat = mu + rng.normal(0.0, PLANT_SIGMA, len(mu))
    floor = np.array([r["_log_floor"] for r in rows])
    cens = lat < floor
    bt, sig = xm.tobit_fit(Z, lat, cens, floor)
    mu_t = A @ bt
    bo, *_ = np.linalg.lstsq(A[~cens], lat[~cens], rcond=None)
    mu_o = A @ bo
    rm_t = float(np.sqrt(np.mean((mu_t - mu) ** 2)))
    rm_o = float(np.sqrt(np.mean((mu_o - mu) ** 2)))
    out["P1_censoring"] = {"rows": int(len(rows)), "censored_share": float(cens.mean()),
                           "sigma_true": PLANT_SIGMA, "sigma_fit": float(sig),
                           "rmse_tobit": rm_t, "rmse_ols_uncensored": rm_o,
                           "pass": bool(rm_t <= PLANT_OK_RMSE and rm_t < rm_o)}
    # ---- P2a signal ---------------------------------------------------------
    # One data-generating process for every row of the development frame
    # (MLB and floor rows alike): ordered-logit years and a normal latent log
    # AAV given log years, coefficients fixed at fits to the real development
    # rows. A row whose latent AAV falls below its floor becomes a floor row,
    # so the censoring is consistent with the simulated prices.
    Xy_m = _true_X(mlb)
    sy = xm._Std(Xy_m)
    ycat = np.array([xm.year_cat(r["_years"]) for r in mlb])
    by, th = xm.ordered_logit_fit(sy(Xy_m), ycat)
    top = [r["_years"] for r in mlb if xm.year_cat(r["_years"]) == xm.YEAR_CATS - 1]
    top_y = float(round(statistics.mean(top))) if top else 7.0
    cat_years = np.array([1, 2, 3, 4, 5, 6, top_y], dtype=float)
    Xa_m = _true_X(mlb, np.log(np.array([r["_years"] for r in mlb])))
    sa = xm._Std(Xa_m)
    ba, *_ = np.linalg.lstsq(np.column_stack([np.ones(len(mlb)), sa(Xa_m)]), ym, rcond=None)
    allr = mlb + flo
    Xb = _true_X(allr)
    P = xm.ordered_probs(sy(Xb), by, th)
    cdf = np.cumsum(P, axis=1)
    fl_all = np.array([r["_log_floor"] for r in allr])

    def _lat(Xbase, yrs):
        X_ = np.column_stack([Xbase, np.log(yrs)])
        return np.column_stack([np.ones(len(X_)), sa(X_)]) @ ba

    u = rng.random(len(allr))
    cat = (cdf < u[:, None]).sum(axis=1).clip(0, xm.YEAR_CATS - 1)
    yrs_sim = cat_years[cat]
    la_sim = _lat(Xb, yrs_sim) + rng.normal(0.0, PLANT_SIGMA, len(allr))
    D = 400
    sim_mlb, sim_floor = [], []
    for i, r in enumerate(allr):
        s = dict(r)
        if la_sim[i] < fl_all[i]:
            s["_kind"] = "floor"
            s["mlb_deal"] = False
            sim_floor.append(s)
            continue
        y_ = float(yrs_sim[i])
        t_ = math.exp(la_sim[i]) * y_
        s.update({"_kind": "mlb", "mlb_deal": True, "years": int(y_),
                  "guarantee_usd": int(t_), "npv_guarantee_usd": int(t_),
                  "aav_usd": int(t_ / y_), "npv_aav_usd": int(t_ / y_), "_years": y_,
                  "_log_total": math.log(t_), "_log_aav": math.log(t_ / y_),
                  "deferral_adjusted": False})
        # oracle: the median log total given an MLB deal under the true model
        uu = rng.random(D)
        yy = cat_years[(cdf[i][None, :] < uu[:, None]).sum(axis=1).clip(0, xm.YEAR_CATS - 1)]
        lat = _lat(np.repeat(Xb[i:i + 1], D, axis=0), yy) + rng.normal(0.0, PLANT_SIGMA, D)
        keep = lat >= fl_all[i]
        s["_oracle"] = float(np.median((lat + np.log(yy))[keep])) if keep.any() else s["_log_total"]
        sim_mlb.append(s)
    ch = run_chain(list(cands), dev, inp, mlb=sim_mlb, floor=sim_floor, seed=seed)
    p2a = {"simulated_floor_share": len(sim_floor) / max(len(allr), 1)}
    for c in cands:
        o = ch[c]
        y = np.array(o["y"])
        orc = np.array([r["_oracle"] for r in o["rows"]])
        mae = float(np.abs(y - np.array(o["p50"])).mean())
        omae = float(np.abs(y - orc).mean())
        p2a[c] = {"n": len(y), "log_total_mae": mae, "oracle_mae": omae,
                  "ratio": mae / omae if omae else None,
                  "pass": bool(omae and mae <= PLANT_ORACLE_RATIO * omae)}
    out["P2a_signal"] = p2a
    # ---- P2b permuted null -----------------------------------------------------
    rnd = random.Random(seed)
    perm = []
    by_w = defaultdict(list)
    for r in mlb:
        by_w[r["class_year"]].append(r)
    for w, rs in by_w.items():
        labs = [(r["years"], r["guarantee_usd"], r.get("npv_guarantee_usd"), r.get("aav_usd"),
                 r.get("npv_aav_usd"), r["_years"], r["_log_total"], r["_log_aav"]) for r in rs]
        rnd.shuffle(labs)
        for r, lab in zip(rs, labs):
            s = dict(r)
            (s["years"], s["guarantee_usd"], s["npv_guarantee_usd"], s["aav_usd"],
             s["npv_aav_usd"], s["_years"], s["_log_total"], s["_log_aav"]) = lab
            perm.append(s)
    ch2 = run_chain(list(cands) + ["const"], dev, inp, mlb=perm, floor=flo, seed=seed)
    p2b = {}
    for c in cands:
        pr = paired(ch2["const"], ch2[c])
        p2b[c] = {"vs_const": pr, "pass": bool(not (pr["lo95_one_sided"] is not None
                                                    and pr["lo95_one_sided"] > 0))}
    out["P2b_null"] = p2b
    return out


# ============================================================================
# Counterfactual extension, anchors, Fair $ (gate section 11)
# ============================================================================

def _season_age(age_now: float) -> int:
    """Season age in 2027 (age on 2027-06-30) from an age read on 2026-10-22."""
    return int(math.floor(float(age_now) + 0.69))


def counterfactual(inp: Inputs, served: str, seed: int = xm.SEED) -> dict:
    import fa_export
    import fa_market as fm
    import fa_projection as fp
    import scrapers
    import spotrac
    import storage
    W = xm.SERVE_WINTER
    corpus, by_player, il = inp._corpus, inp._by_player, inp._il
    league = corpus["league"]
    curves, war_map = fp.fitted_models(corpus, W - 1, use_def=fm.FA_PRICING_USE_DEF)
    frac = fp.season_fraction(league, W - 1)
    tv = json.loads((ROOT / "data" / "trade_values.json").read_text(encoding="utf-8"))["players"]
    ts = json.loads((ROOT / "data" / "timeseries.json").read_text(encoding="utf-8"))["players"]
    eta = {p.get("player_key"): (p.get("eta") or {}).get("year") for p in ts
           if isinstance(p.get("eta"), dict)}
    pops = {"pre_arb": [], "arb": [], "prospect": []}
    counts = defaultdict(lambda: defaultdict(int))
    for p in tv:
        phase = (p.get("crunch") or {}).get("service_phase")
        if p.get("status") == "debuted" and phase in ("pre_arb", "arb_eligible"):
            pop = "pre_arb" if phase == "pre_arb" else "arb"
            counts[pop]["listed"] += 1
            mid = p.get("mlbam_id")
            side = "pit" if fm._pos_group(p.get("position")) in ("SP", "RP") else "hit"
            seasons = by_player[side].get(mid) or {} if mid else {}
            hist = [seasons[t] for t in (W - 1, W - 2, W - 3) if t in seasons]
            if not hist:
                counts[pop]["no_history"] += 1
                continue
            age_row = next((h for h in hist if h.get("age")), None)
            if not age_row:
                counts[pop]["no_age"] += 1
                continue
            age = age_row["age"] + (W - age_row["season"])
            path = fm.contract_war_path(hist, side, W, 10, age, curves, war_map, league,
                                        in_progress=(W - 1, frac), use_ml=False)
            if not path:
                counts[pop]["no_path"] += 1
                continue
            pops[pop].append({"player_key": p.get("player_key"), "player_name": p.get("player_name"),
                              "mlbam_id": mid, "position": p.get("position"), "qo": False,
                              "class_year": W, "_side": side, "_age": age, "_war_path": path,
                              "_contract": p.get("contract") or {},
                              "_service_years": (p.get("crunch") or {}).get("service_years")})
        elif p.get("status") == "active" and p.get("xfv_war_6yr") is not None:
            counts["prospect"]["listed"] += 1
            if p.get("age") is None:
                counts["prospect"]["no_age"] += 1
                continue
            age = _season_age(p["age"])
            side = "pit" if fm._pos_group(p.get("position")) in ("SP", "RP") else "hit"
            wy = xm.prospect_path(p["xfv_war_6yr"], eta.get(p.get("player_key")), age, W)
            if eta.get(p.get("player_key")) is None:
                counts["prospect"]["no_eta_debut_now"] += 1
            path = {"war_by_year": wy, "war_y1": wy[0], "war_total": sum(wy),
                    "rates_by_year": [], "role": "SP" if side == "pit" else None}
            pops["prospect"].append({"player_key": p.get("player_key"),
                                     "player_name": p.get("player_name"), "mlbam_id": None,
                                     "position": p.get("position"), "qo": False,
                                     "class_year": W, "_side": side, "_age": age,
                                     "_war_path": path, "_contract": {}})
    # the final model, fitted on every winter 2015-2026
    train = list(inp.mlb)
    train_fl = list(inp.floor)
    box = xm.support_box([r["_xm"] for r in train])
    cls = list(storage.load_fa_class_players(W).values())
    sup_rows = fa_export._class_supply_rows(cls, W, by_player)
    for r in sup_rows:
        r["_kind"] = "mlb"
    rows_all = []
    for pop, rows in pops.items():
        for r in rows:
            a2, wy2, outside = xm.clip_to_support(r["_age"], r["_war_path"]["war_by_year"], box)
            r["_outside"] = outside
            r["_pop"] = pop
            r["_age_raw"] = r["_age"]
            r["_age"] = int(round(a2))
            pth = dict(r["_war_path"])
            pth["war_by_year"] = wy2
            pth["war_y1"] = wy2[0] if wy2 else 0.0
            if outside and pth.get("war_by_year_p10"):
                f = (sum(wy2) / max(sum(r["_war_path"]["war_by_year"]), 1e-9))
                pth["war_by_year_p10"] = [w * f for w in pth["war_by_year_p10"]]
                pth["war_by_year_p90"] = [w * f for w in pth["war_by_year_p90"]]
            r["_war_path"] = pth
            mid = r.get("mlbam_id")
            r["_xm"] = xm.static_features(
                age=r["_age"], war_by_year=wy2, side=r["_side"], position=r.get("position"),
                qo=False, seasons=(by_player[r["_side"]].get(mid) or {}) if mid else {},
                il_seasons=(il.get(int(mid)) or {}) if mid else {}, winter=W,
                demand=inp.demand[W], disc_rate=inp.disc_rate)
            r["_kind"] = "cf"
            r["_log_floor"] = math.log(inp.league_min[W])
            rows_all.append(r)
    p = fit_predict(served, train, train_fl, rows_all, W, inp, supply_rows=sup_rows, seed=seed)
    ctx = Ctx(train, sup_rows, W, inp)
    idx27 = ctx.index(W)
    for r, yf, lt in zip(rows_all, p["years_f"], p["log_total"]):
        yrs = max(1, int(round(float(yf))))
        tot = math.exp(float(lt))
        r["_xm_years"] = yrs
        r["_xm_total"] = tot
        r["_xm_aav"] = tot / (yrs if served == "a_incumbent" else max(float(yf), 1.0))
        r["_fair"] = xm.fair_value_usd(r["_war_path"], yrs, W, idx27)
    summ = {}
    for pop, rows in pops.items():
        if not rows:
            summ[pop] = {"priced": 0, **counts[pop]}
            continue
        aav = sorted(r["_xm_aav"] for r in rows)
        fair = sorted(r["_fair"] for r in rows)
        yrs = [r["_xm_years"] for r in rows]
        summ[pop] = {**counts[pop], "priced": len(rows),
                     "outside_support": sum(1 for r in rows if r["_outside"]),
                     "share_outside_support": sum(1 for r in rows if r["_outside"]) / len(rows),
                     "age_outside": sum(1 for r in rows if not (box["age"][0] <= r["_age_raw"] <= box["age"][1])),
                     "xm_aav_mm_p10_p50_p90": [round(float(np.quantile(aav, q)) / 1e6, 3)
                                               for q in (0.1, 0.5, 0.9)],
                     "xm_years_median": float(statistics.median(yrs)),
                     "fair_usd_mm_p10_p50_p90": [round(float(np.quantile(fair, q)) / 1e6, 3)
                                                 for q in (0.1, 0.5, 0.9)]}
    # ---- extension anchor -------------------------------------------------------
    with scrapers.cache_only():
        sp_rows = []
        for _code, slug in spotrac._SPOTRAC_TEAM_SLUGS.items():
            try:
                sp_rows.extend(spotrac.scrape_spotrac_team_contracts(slug))
            except Exception:                           # noqa: BLE001 - counted
                continue
    sp = {}
    for row in sp_rows:
        if row.get("player_key"):
            sp.setdefault(row["player_key"], row)
    ext = {"candidates": 0, "no_spotrac_row": 0, "no_bought_fa_season": 0, "no_service_years": 0}
    ratios, cl = [], []
    lst = []
    for pop in ("pre_arb", "arb"):
        for r in pops[pop]:
            ph = str((r.get("_contract") or {}).get("phase") or "")
            if not ph.startswith("Ext"):
                continue
            ext["candidates"] += 1
            sy = r.get("_service_years")
            if sy is None:
                ext["no_service_years"] += 1
                continue
            row = sp.get(r["player_key"])
            if not row:
                ext["no_spotrac_row"] += 1
                continue
            fa_season = W + max(0, 6 - int(sy))
            sal = [float(v) for s, v in (row.get("salary_by_year") or {}).items()
                   if int(s) >= fa_season and v]
            if not sal:
                ext["no_bought_fa_season"] += 1
                continue
            bought = statistics.mean(sal)
            ratios.append(bought / max(r["_xm_aav"], 1.0))
            cl.append(r["player_key"])
            lst.append({"player": r["player_name"], "phase": pop, "fa_season": fa_season,
                        "bought_fa_aav_mm": round(bought / 1e6, 3),
                        "xm_aav_mm": round(r["_xm_aav"] / 1e6, 3),
                        "outside_support": bool(r["_outside"])})
    ext["n"] = len(ratios)
    if ratios:
        rng = np.random.default_rng(seed)
        arr = np.array(ratios)
        meds = np.array([np.median(arr[rng.integers(0, len(arr), len(arr))]) for _ in range(4000)])
        lo, hi = float(np.quantile(meds, 0.025)), float(np.quantile(meds, 0.975))
        ext.update({"median_ratio": float(np.median(arr)), "ci95": [lo, hi], "B": 4000,
                    "seed": seed,
                    "reading": ("consistent" if hi < 1 else "not consistent" if lo > 1
                                else "inconclusive"),
                    "rows": sorted(lst, key=lambda d: -d["bought_fa_aav_mm"])})
    # ---- posting anchor ----------------------------------------------------------
    post_rows = inp.posting.get("rows") or []
    posting = {"rows": len(post_rows), "with_as_of_path": 0, "status": "NOT MEASURABLE",
               "why": ("no as-of translated MLB WAR path exists in the store for a player "
                       "with no MLB season in the three before the winter; the overseas "
                       "translation serves ERA and strikeout factors, not WAR"),
               "median_aav_mm": (round(statistics.median(r["guarantee_usd"] / r["years"]
                                                         for r in post_rows) / 1e6, 3)
                                 if post_rows else None),
               "largest": sorted(({"player": r["player"], "class_year": r["class_year"],
                                   "years": r["years"],
                                   "guarantee_mm": round(r["guarantee_usd"] / 1e6, 1)}
                                  for r in post_rows), key=lambda d: -d["guarantee_mm"])[:10]}
    return {"served_model": served, "winter": W, "index_usd": idx27,
            "support_box": box, "class_supply_rows": len(sup_rows),
            "populations": summ, "extension_anchor": ext, "posting_anchor": posting,
            "fair_value_note": ("fa_market.expected_rational_value_usd on the same (clipped) "
                                "path at the xM$ point term and the one-step index")}


# ============================================================================
# The read
# ============================================================================

def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return [_jsonable(v) for v in o.tolist()]
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def persist(doc: dict, out: Path, step: str) -> None:
    doc.setdefault("order", []).append(step)
    out.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(_jsonable(doc), indent=1, sort_keys=False)
    out.write_bytes((txt + chr(10)).encode("utf-8"))


def run(inp: Inputs, out: Path, generated_at: str, dev=xm.DEV_WINTERS,
        hold=xm.HOLDOUT_WINTERS, do_counterfactual: bool = True, B: int = 4000,
        code_head: str | None = None) -> dict:
    doc = {"model_id": "xm", "model_version": xm.MODEL_VERSION, "generated_at": generated_at,
           "what": ("xM$ (Expected Market $): the registered read of docs/xm/XM_GATE.md. "
                    "Candidates (a) incumbent fa_market.MarketModel, (b) hurdle, (c) "
                    "monotone GBM; NULL 1 platform WAR x one-step $/WAR index; MLB Trade "
                    "Rumors retro predictions; planted recovery; holdout read once."),
           "gate": {"doc": "docs/xm/XM_GATE.md", "registered_commit": GATE_COMMIT,
                    "doc_sha256": _sha(GATE_DOC) if GATE_DOC.exists() else None},
           "seed": xm.SEED, "frames": {"warmup_through": xm.WARMUP_THROUGH,
                                       "development": list(dev), "holdout": list(hold)},
           "code_head": code_head, "inputs": inp.coverage, "order": []}
    persist(doc, out, "inputs")
    # ---- 2 planted ---------------------------------------------------------------
    pl = planted(inp, list(dev), CANDIDATES)
    doc["planted"] = pl
    void = {c for c in CANDIDATES
            if not (pl["P2a_signal"][c]["pass"] and pl["P2b_null"][c]["pass"])}
    if not pl["P1_censoring"]["pass"]:
        void.add("b_hurdle")
    doc["planted"]["void_candidates"] = sorted(void)
    persist(doc, out, "planted")
    if "a_incumbent" in void:
        # Gate section 9: the served model failed planted recovery. No verdict
        # and the holdout stays unread.
        doc["holdout"] = None
        doc["verdict"] = "VOID"
        persist(doc, out, "void")
        return doc
    # ---- 3 development -----------------------------------------------------------
    allc = list(CANDIDATES) + ["null1", "const"]
    ch = run_chain(allc, dev, inp)
    devm = {c: score(ch[c]) for c in allc}
    band = {}
    for c in CANDIDATES:
        cov = devm[c].get("coverage_p10_p90")
        band[c] = ("conformal" if cov is not None and not
                   (xm.BAND_TARGET[0] <= cov <= xm.BAND_TARGET[1]) else "in_sample")
    if any(v == "conformal" for v in band.values()):
        need = [c for c in CANDIDATES if band[c] == "conformal"]
        ch_c = run_chain(need, dev, inp, band=band)
        for c in need:
            devm[c + "__in_sample_band"] = {k: devm[c][k] for k in
                                            ("coverage_p10_p90", "pinball_p10", "pinball_p90",
                                             "crps_proxy")}
            ch[c] = ch_c[c]
            devm[c] = score(ch[c])
    for c in ("null1", "const"):
        band[c] = "in_sample"
    eligible = [c for c in CANDIDATES if c not in void or c == "a_incumbent"]
    sel = min(eligible, key=lambda c: devm[c]["log_total_mae"])
    dev_pairs = {f"{c}_vs_{k}": paired(ch[k], ch[c], B=B) for c in CANDIDATES
                 for k in ("null1", "a_incumbent", "const") if c != k}
    doc["development"] = {"band_method": band, "metrics": devm, "paired": dev_pairs,
                          "selection": {"rule": "lowest pooled development log-total MAE",
                                        "eligible": eligible, "selected": sel,
                                        "challenger": None if sel == "a_incumbent" else sel}}
    doc["industry_mlbtr"] = {"development": mlbtr_block(ch, sel, inp, B=B, claim=False)}
    persist(doc, out, "development")
    return holdout_and_after(doc, inp, out, hold, do_counterfactual, B)


def holdout_and_after(doc: dict, inp: Inputs, out: Path, hold, do_counterfactual: bool,
                      B: int) -> dict:
    """Gate section 13 steps 4 and 5, from the development block as persisted:
    the selection and the band methods are read from ``doc``, never recomputed."""
    sel = doc["development"]["selection"]["selected"]
    band = dict(doc["development"]["band_method"])
    # ---- 4 holdout (once) -------------------------------------------------------
    hc = ["a_incumbent", "null1", "const"] + ([sel] if sel != "a_incumbent" else [])
    hch = run_chain(hc, hold, inp, band=band)
    hm = {c: score(hch[c]) for c in hc}
    pr = {"incumbent_vs_null1": paired(hch["null1"], hch["a_incumbent"], B=B),
          "incumbent_vs_const": paired(hch["const"], hch["a_incumbent"], B=B)}
    verdict = None
    if sel != "a_incumbent":
        pr["challenger_vs_null1"] = paired(hch["null1"], hch[sel], B=B)
        pr["challenger_vs_incumbent"] = paired(hch["a_incumbent"], hch[sel], B=B)
        pr["challenger_vs_const"] = paired(hch["const"], hch[sel], B=B)
        ok = all(pr[k]["lo95_one_sided"] is not None and pr[k]["lo95_one_sided"] > 0
                 and pr[k]["delta"] > 0
                 for k in ("challenger_vs_null1", "challenger_vs_incumbent"))
        if ok:
            verdict = "REPLACE"
    inc_ok = (pr["incumbent_vs_null1"]["lo95_one_sided"] is not None
              and pr["incumbent_vs_null1"]["lo95_one_sided"] > 0
              and pr["incumbent_vs_null1"]["delta"] > 0)
    if verdict is None:
        verdict = "INCUMBENT" if inc_ok else "TIE"
    served = sel if verdict == "REPLACE" else "a_incumbent"
    doc["holdout"] = {"read_once": True, "scored": hc, "metrics": hm, "paired": pr,
                      "pass_rule": ("challenger replaces the incumbent iff its holdout "
                                    "log-total MAE beats NULL 1 and the incumbent with the "
                                    "one-sided 95 percent lower bound of the paired "
                                    "improvement above 0 (player-clustered, B 4000, seed "
                                    "20261019)"),
                      "verdict": verdict, "served_model": served,
                      "registry_verdict": {"REPLACE": "validated", "INCUMBENT": "provisional",
                                           "TIE": "provisional"}[verdict],
                      "provisional_kind": {"REPLACE": None, "INCUMBENT": "inherits_parent_gate",
                                           "TIE": "measurement_only"}[verdict]}
    doc["industry_mlbtr"]["holdout"] = mlbtr_block(hch, served, inp, B=B, claim=True)
    if served != "a_incumbent":
        doc["industry_mlbtr"]["holdout_incumbent"] = mlbtr_block(hch, "a_incumbent", inp,
                                                                 B=B, claim=False)
    persist(doc, out, "holdout")
    # ---- 5 counterfactual --------------------------------------------------------
    if do_counterfactual:
        doc["counterfactual"] = counterfactual(inp, served)
        persist(doc, out, "counterfactual")
    return doc


def mlbtr_block(ch: dict, model: str, inp: Inputs, B: int, claim: bool) -> dict:
    """Both MLBTR and ``model`` against the STICKER guarantee on rows with no
    deferral adjustment (gate section 8)."""
    o = ch[model]
    rows = {(r["class_year"], r.get("player_key")): r for r in inp.mlb}
    em, et, cl, ny_m, ny_t = [], [], [], [], []
    for i, k in enumerate(o["key"]):
        r = rows.get(k)
        if not r or r.get("deferral_adjusted"):
            continue
        t = inp.mlbtr.get((int(k[0]), int(r.get("mlbam_id") or 0)))
        if not t:
            continue
        y = math.log(float(r["guarantee_usd"]))
        em.append(abs(y - o["p50"][i]))
        et.append(abs(y - math.log(float(t["pred_total_mm"]) * 1e6)))
        cl.append(o["cl"][i])
        ny_m.append(int(max(round(o["yp"][i]), 1) == int(r["years"])))
        ny_t.append(int(int(t["pred_years"]) == int(r["years"])))
    blk = {"model": model, "paired_rows": len(em),
           "model_log_total_mae": float(np.mean(em)) if em else None,
           "mlbtr_log_total_mae": float(np.mean(et)) if et else None,
           "model_years_exact": float(np.mean(ny_m)) if ny_m else None,
           "mlbtr_years_exact": float(np.mean(ny_t)) if ny_t else None}
    if claim:
        if len(em) >= MLBTR_MIN_PAIRED:
            b = xm.cluster_lo95(et, em, cl, B=B)
            blk["model_vs_mlbtr"] = b
            blk["claim"] = ("model beats MLBTR" if b["lo95_one_sided"] > 0 and b["delta"] > 0
                            else "MLBTR beats model" if xm.cluster_lo95(em, et, cl, B=B)["lo95_one_sided"] > 0
                            else "tie")
        else:
            blk["claim"] = f"none: {len(em)} paired rows, fewer than {MLBTR_MIN_PAIRED}"
    return blk


# ============================================================================
# Dry run fixture (gate section 13 step 1)
# ============================================================================

def fixture_inputs(seed: int = 7) -> Inputs:
    """A synthetic corpus that carries the nulls the read must survive: a row
    with no path (dropped before the corpus, as in the real enrichment), a
    winter with no floor rows, an MLBTR row with no join."""
    rng = np.random.default_rng(seed)
    inp = Inputs()
    inp.flat_dpw = 8e6
    inp.disc_rate = 0.07
    for y in range(2012, xm.SERVE_WINTER + 1):
        inp.league_min[y] = 5e5 + 1e4 * (y - 2012)
        inp.demand[y] = int(10 + y % 5)
    pos = ["SP", "RP", "C", "SS", "1B", "LF", "CF", "RP/CL"]
    k = 0
    for W in range(2012, 2022):
        for i in range(60):
            k += 1
            age = int(rng.integers(26, 37))
            w1 = float(max(rng.normal(1.5, 1.2), 0.0))
            path = [max(w1 - 0.4 * t, 0.0) for t in range(15)]
            p = pos[i % len(pos)]
            yrs = int(min(max(round(1 + w1 * 1.2 + (32 - age) * 0.2 + rng.normal(0, 0.7)), 1), 10))
            aav = math.exp(math.log(4e6) + 0.45 * w1 + rng.normal(0, 0.4))
            r = {"player_key": f"p{k % 400}", "player_name": f"P {k}", "mlbam_id": 1000 + k,
                 "class_year": W, "position": p, "qo": bool(i % 17 == 0), "years": yrs,
                 "guarantee_usd": int(aav * yrs), "npv_guarantee_usd": int(aav * yrs),
                 "aav_usd": int(aav), "npv_aav_usd": int(aav),
                 "deferral_adjusted": False, "mlb_deal": True,
                 "_war_path": {"war_by_year": path, "war_y1": path[0], "rates_by_year": [],
                               "war_total": sum(path)},
                 "_age": age, "_side": "pit" if p in ("SP", "RP", "RP/CL") else "hit",
                 "_kind": "mlb"}
            seasons = {W - 1: {"war": w1 + rng.normal(0, 0.5), "bf": 300, "role": "SP"}}
            r["_xm"] = xm.static_features(age=age, war_by_year=path, side=r["_side"],
                                          position=p, qo=r["qo"], seasons=seasons,
                                          il_seasons={}, winter=W, demand=inp.demand[W],
                                          disc_rate=0.07)
            _label_fields(r, inp.league_min)
            inp.mlb.append(r)
        if W != 2016:                                  # a winter with no floor rows
            for i in range(6):
                k += 1
                path = [0.1] * 15
                r = {"player_key": f"f{k}", "player_name": f"F {k}", "mlbam_id": 9000 + k,
                     "class_year": W, "position": "RP", "qo": False, "mlb_deal": False,
                     "_war_path": {"war_by_year": path, "war_y1": 0.1, "rates_by_year": []},
                     "_age": 33, "_side": "pit", "_kind": "floor"}
                r["_xm"] = xm.static_features(age=33, war_by_year=path, side="pit",
                                              position="RP", qo=False, seasons={},
                                              il_seasons={}, winter=W, demand=inp.demand[W],
                                              disc_rate=0.07)
                _label_fields(r, inp.league_min)
                inp.floor.append(r)
    for r in inp.mlb[::7]:
        inp.mlbtr[(r["class_year"], r["mlbam_id"])] = {"pred_total_mm": r["guarantee_usd"] / 1e6 * 1.1,
                                                     "pred_years": r["years"]}
    inp.mlbtr[(2020, 1)] = {"pred_total_mm": 10.0, "pred_years": 2}   # no join
    inp.coverage = {"fixture": True, "mlb_rows": len(inp.mlb), "floor_rows": len(inp.floor)}
    inp.posting = {"rows": [], "no_mlbam": 0}
    return inp


def _git_head() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:                                   # noqa: BLE001
        return None


def _registered_body(text: str) -> str:
    """The gate text above section 14 (Amendments), line endings normalized:
    the part an amendment or the results never change."""
    t = text.replace(chr(13) + chr(10), chr(10))
    cut = t.find(chr(10) + "## 14. Amendments")
    return t if cut < 0 else t[:cut]


def _gate_unchanged_since(persisted_sha: str | None) -> bool:
    """True when the persisted sha is the registered gate document's (as
    checked out, CRLF) and the current document keeps its registered body,
    so only sections 14 and 15 may have been appended to since the read."""
    try:
        reg = subprocess.run(["git", "show", f"{GATE_COMMIT}:./docs/xm/XM_GATE.md"], cwd=ROOT,
                             capture_output=True, check=True).stdout.decode("utf-8")
    except Exception:                                   # noqa: BLE001
        return False
    reg_crlf = reg.replace(chr(13) + chr(10), chr(10)).replace(chr(10), chr(13) + chr(10))
    if hashlib.sha256(reg_crlf.encode("utf-8")).hexdigest() != persisted_sha:
        return False
    return _registered_body(GATE_DOC.read_text(encoding="utf-8")) == _registered_body(reg)


def resume_holdout(out: Path) -> int:
    """Run gate steps 4 and 5 ONCE from the development block persisted in
    ``out``. Only for the case the 2026-10-22 read hit: the process died after
    the development block was written and before any holdout metric was
    written (owner question XM1-Q1). Refuses when the holdout is already
    there, when the gate document changed above its section 14 (the dated
    XM1-Q1 amendment is committed first, so the whole-file sha moves by
    design), or when the rebuilt inputs differ from the persisted ones in any
    count."""
    import scrapers
    doc = json.loads(out.read_text(encoding="utf-8"))
    if doc.get("order") != ["inputs", "planted", "development"] or doc.get("holdout"):
        print("refused: the artifact is not a development-only read", file=sys.stderr)
        return 2
    if not _gate_unchanged_since(doc["gate"].get("doc_sha256")):
        print("refused: docs/xm/XM_GATE.md changed above section 14 since the development "
              "read", file=sys.stderr)
        return 2
    with scrapers.cache_only():
        inp = real_inputs()
    if json.loads(json.dumps(_jsonable(inp.coverage))) != doc["inputs"]:
        print("refused: the rebuilt inputs differ from the persisted inputs", file=sys.stderr)
        return 2
    doc["resumed"] = {"on": date.today().isoformat(), "code_head": _git_head(),
                      "gate_doc_sha256_at_resume": _sha(GATE_DOC),
                      "why": ("the first read died (exit 139, no Python traceback) after "
                              "the development block was written and before any holdout "
                              "metric was written; owner answer XM1-Q1"),
                      "crash_fix": ("steps 4-5 run in a fresh process; the bootstrap weight "
                                    "matrix is built by one bincount instead of an np.add.at "
                                    "fancy-index accumulation (exactly equal counts); "
                                    "faulthandler on")}
    try:
        doc = holdout_and_after(doc, inp, out, tuple(doc["frames"]["holdout"]), True, 4000)
    except BaseException:
        traceback.print_exc()
        return 3
    print(json.dumps({"verdict": doc["holdout"]["verdict"],
                      "selected": doc["development"]["selection"]["selected"]}))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--read", action="store_true")
    g.add_argument("--resume-holdout", action="store_true",
                   help="steps 4-5 only, from a persisted development block (owner answer XM1-Q1)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    if not faulthandler.is_enabled():
        faulthandler.enable(all_threads=True)          # a native fault leaves a traceback
    if a.dry_run:
        out = Path(a.out) if a.out else ROOT / ".cache" / "xm" / "dry_run" / "xm_eval.json"
        doc = run(fixture_inputs(), out, date.today().isoformat(),
                  dev=(2015, 2016, 2017, 2018, 2019), hold=(2020, 2021),
                  do_counterfactual=False, B=200)
        print("dry run ok:", out, "verdict", doc["holdout"]["verdict"],
              "selected", doc["development"]["selection"]["selected"])
        return 0
    if a.resume_holdout:
        return resume_holdout(Path(a.out) if a.out else OUT_PATH)
    if OUT_PATH.exists():
        try:
            prev = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        except ValueError:
            prev = {}
        if prev.get("holdout"):
            print("refused: data/xm_eval.json already holds the holdout read", file=sys.stderr)
            return 2
    import scrapers
    with scrapers.cache_only():
        inp = real_inputs()
    out = Path(a.out) if a.out else OUT_PATH
    try:
        doc = run(inp, out, date.today().isoformat(), code_head=_git_head())
    except BaseException:
        traceback.print_exc()
        return 3
    print(json.dumps({"verdict": (doc.get("holdout") or {}).get("verdict") or doc.get("verdict"),
                      "selected": (doc.get("development") or {}).get("selection")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
