# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""eFV LANE L3 -- PEAK-WAR target + measurement calibration (round-2 2026-07-24).

Two questions, both OOS / forward-chained on the SHIPPED machinery (efv_lab_runner
data_for + efv_model ridge/OLS blend), so a "gain" here is a real leakage-clean gain
on the same protocol data/xfv_eval.json / the scoreboard use.

PART A  MEASUREMENT (calibrate what counts as accurate).
  Build peak1 (best single first-6 season) + peak3 (best consecutive-3-season sum)
  ground-truth labels from the SAME career_war per-season bWAR the cumulative target
  uses (window debut..debut+5, missing-in-window seasons = 0, censored tail filled at
  the observed per-season rate exactly like efv_dataset._label_6yr). Then re-score the
  CURRENT shipped eFV OOS predictions AND the consensus anchor against peak1 / peak3:
    - Spearman + AUC of eFV-vs-peak and consensus-vs-peak.
    - Does eFV rank peak as well as it ranks cumulative? Does the peak target change
      who is "right" on the biggest eFV-vs-consensus disagreements?
    - Clemens-2026 SURPLUS-WEIGHTED accuracy: weight each realized player by the
      dollar value of their realized first-6 WAR under the clemens_2026 valuation
      (value_framework.tiered_war_value_usd, discounted), then report NDCG / top-quintile
      surplus capture / surplus-weighted Spearman for eFV vs consensus. High-value
      players count more.

PART B  MODEL (the substantive measurement-model question).
  Retrain the WHOLE eFV blend (OLS(FV) + ridge) with peak1 / peak3 / a standardized
  cumulative-peak BLEND as the TRAINING target, forward-chained, and measure OOS
  Spearman/AUC against BOTH the cumulative and the peak ground truths, with a paired
  bootstrap CI on the Spearman delta vs the shipped cumulative-target baseline.
  Ship rule (owner): a target change ships ONLY if it raises OOS rank accuracy AND does
  not degrade the cumulative accuracy that prices surplus (lo95>0 on the accuracy
  yardstick, no-harm on cumulative). If peak improves the GRADE ranking but surplus
  needs cumulative, the shippable form is a split: peak-informed grade target +
  cumulative-target surplus (stated in the report).

Run:  python tools/efv_peak_war_lab.py            # full A+B, writes both artifacts
Artifacts: data/xfv_peak_war_eval.json + data/xfv_measurement_calibration_eval.json
"""
from __future__ import annotations
import sys, json, math, random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import os; os.chdir(ROOT)

import storage
import efv_lab_runner as LAB
from efv_model import _feature_spec, _fit_ols_fv, _pred_ols, blend_lambda
from prospect_path import _fit_ridge, _predict, _spearman
from source_backtest import _auc
import value_framework as VF

DATA = ROOT / "data"
SCORED_YEARS = LAB.SCORED_YEARS
TARGET_SEASONS = 6
RESOLVED_THROUGH = 2025           # mirrors efv_dataset.RESOLVED_THROUGH
MIN_TRAIN, MIN_TEST = 50, 12      # the lab pooled-protocol floors (== efv_lab_runner)

# AUC thresholds. Cumulative keeps the scoreboard convention (contributor>=3, star>=10
# on the 6yr sum). Peak thresholds are the single-/three-season analogs, chosen at
# baseball-legible WAR levels (a ~2-WAR season = above-average regular; a ~5-WAR season
# = All-Star; three ~2-WAR seasons = 6; three ~4-WAR seasons = 12). n_pos reported so
# the reader can judge the base rate.
THRESH = {
    "cumulative": {"contributor": 3.0, "star": 10.0},
    "peak1":      {"contributor": 2.0, "star": 5.0},
    "peak3":      {"contributor": 6.0, "star": 12.0},
}


# ---------------------------------------------------------------------------
# labels: peak1 / peak3 built from the SAME career_war seasons as the cumulative target
# ---------------------------------------------------------------------------
def _load_career_war_seasons():
    cw = {}
    with storage.connect() as con:
        for r in con.execute("SELECT player_key, payload_json FROM career_war"):
            try:
                seasons = (json.loads(r["payload_json"]) or {}).get("seasons") or {}
            except ValueError:
                continue
            cw[r["player_key"]] = {int(y): float(w) for y, w in seasons.items()}
    return cw


def _load_debut_years(side):
    rows = json.loads(LAB.matrix_path(side).read_text(encoding="utf-8")) \
        if hasattr(LAB, "matrix_path") else \
        json.loads((DATA / ("xfv_hitter_matrix.json" if side == "hit" else "xfv_pitcher_matrix.json")).read_text(encoding="utf-8"))
    return {r["player_key"]: r.get("debut_year") for r in rows if r.get("kind") == "debuted"}


def _best3(lst):
    """Best consecutive-3-season sum; if fewer than 3 entries, the sum of what exists
    (the peak-so-far lower bound), 0 for empty."""
    if not lst:
        return 0.0
    if len(lst) < 3:
        return float(sum(lst))
    return float(max(sum(lst[i:i + 3]) for i in range(len(lst) - 2)))


def _peak_labels(seasons: dict, debut_year: int):
    """peak1 / peak3 in resolved-only (_res) and censored-fill (_cens) forms, the exact
    analogs of target_resolved / target_censored in efv_dataset._label_6yr.

    window = [debut..debut+5]; observed = window years <= RESOLVED_THROUGH; a window year
    with no career_war row = 0 WAR (the player was not in MLB that year). The censored
    form fills the UNOBSERVED window tail at the observed per-season rate (identical to
    the cumulative extrapolation), then takes the peak; peak1 is a max so the flat-rate
    fill never raises it above the observed max -- only peak3 sees the fill when n_obs<3.
    """
    window = [debut_year + i for i in range(TARGET_SEASONS)]
    observed = [y for y in window if y <= RESOLVED_THROUGH]
    n_obs = len(observed)
    obs_sum = sum(seasons.get(y, 0.0) for y in observed)
    rate = obs_sum / n_obs if n_obs else 0.0
    obs_list = [seasons.get(y, 0.0) for y in observed]
    full = [seasons.get(y, (rate if y > RESOLVED_THROUGH else 0.0)) for y in window]
    censored = (debut_year + TARGET_SEASONS - 1) > RESOLVED_THROUGH
    return {
        "peak1_res": float(max(obs_list)) if obs_list else 0.0,
        "peak3_res": _best3(obs_list),
        "peak1_cens": float(max(full)) if full else 0.0,
        "peak3_cens": _best3(full),
        "n_obs": n_obs, "censored": bool(censored),
        "obs_seasons": obs_list,
    }


# ---------------------------------------------------------------------------
# realized surplus ($) under clemens_2026 -- the Part-A weighting
# ---------------------------------------------------------------------------
def _realized_value_musd(obs_seasons):
    """Discounted market $ value (in $M) of a player's realized first-6 window WAR under
    the ACTIVE (clemens_2026) valuation: each observed season valued on its OWN WAR
    through the convex tiered $/WAR kernel (WAR<=0 -> $0), discounted to debut at 7%.
    Pure production value (no salary net-out): a clean, monotone 'how valuable was this
    player' weight so high-value players count more in the accuracy metric."""
    tot = 0.0
    for i, w in enumerate(obs_seasons):
        tot += VF.present_value(VF.tiered_war_value_usd(w), i)
    return tot / 1e6


# ---------------------------------------------------------------------------
# forward-chained OOS read (shipped machinery), training on an arbitrary target
# ---------------------------------------------------------------------------
def _standardize(vals):
    n = len(vals)
    if n == 0:
        return 0.0, 1.0
    mu = sum(vals) / n
    var = sum((v - mu) ** 2 for v in vals) / n if n > 1 else 0.0
    sd = math.sqrt(var) or 1.0
    return mu, sd


def forward_read(side, train_target, cw, dyr):
    """Forward-chained OOS predictions for a blend TRAINED on `train_target`, with EVERY
    candidate ground-truth label attached to each test row so one read scores against
    cumulative + peak1 + peak3 + surplus.

    train_target in {"cumulative","peak1","peak3","blend_std"}. The WHOLE blend is
    retrained on that target (OLS(FV) and ridge both), so the blend predicts that target;
    Spearman/AUC are rank metrics (scale-invariant) so no rescale is needed to compare
    across targets. blend_std standardizes cumulative and peak3 on TRAIN-observed stats
    each fold (anti-leakage) and averages the z-scores.
    """
    rows0 = LAB.data_for(side)
    keys = _feature_spec(side)[0]
    lam = blend_lambda(side)

    # attach labels once
    rows = []
    for r in rows0:
        pk = r["player_key"]
        s = cw.get(pk); dy = dyr.get(pk)
        if not s or dy is None:
            continue
        pl = _peak_labels(s, int(dy))
        rows.append({**r,
                     "y_cumul": r["target_censored"],
                     "y_peak1": pl["peak1_cens"],
                     "y_peak3": pl["peak3_cens"],
                     "y_peak1_res": pl["peak1_res"],
                     "y_peak3_res": pl["peak3_res"],
                     "surplus": _realized_value_musd(pl["obs_seasons"]),
                     "lbl_censored": pl["censored"]})

    def tgt_of(r, mu_c, sd_c, mu_p, sd_p):
        if train_target == "cumulative":
            return r["y_cumul"]
        if train_target == "peak1":
            return r["y_peak1"]
        if train_target == "peak3":
            return r["y_peak3"]
        if train_target.startswith("blend_std"):
            # "blend_std" -> 0.50 cumul weight; "blend_std:0.75" -> 0.75 cumul weight.
            wc = float(train_target.split(":", 1)[1]) if ":" in train_target else 0.5
            return wc * (r["y_cumul"] - mu_c) / sd_c + (1 - wc) * (r["y_peak3"] - mu_p) / sd_p
        raise ValueError(train_target)

    out = []
    for yr in SCORED_YEARS:
        tr = [r for r in rows if r["decision_year"] < yr]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(te) < MIN_TEST or len(tr) < MIN_TRAIN:
            continue
        mu_c, sd_c = _standardize([r["y_cumul"] for r in tr])
        mu_p, sd_p = _standardize([r["y_peak3"] for r in tr])
        ols = _fit_ols_fv([{"fv": r["fv"], "target": tgt_of(r, mu_c, sd_c, mu_p, sd_p)} for r in tr])
        ridge = _fit_ridge([{"feats": r["feats"], "target": tgt_of(r, mu_c, sd_c, mu_p, sd_p),
                             "weight": r["weight"], "fv": r["fv"]} for r in tr], keys)
        if not (ols and ridge):
            continue
        floor0 = not train_target.startswith("blend_std")   # WAR-scale targets floor cons at 0 (shipped convention)
        for r in te:
            cw_pred = _pred_ols(ols, r["fv"])
            if floor0:
                cw_pred = max(0.0, cw_pred)
            blend = (1 - lam) * cw_pred + lam * _predict(ridge, r["feats"])
            out.append({"pk": r["player_key"], "blend": blend, "cons": cw_pred, "fv": r["fv"],
                        "cohort": r["cohort"], "year": yr, "lbl_censored": r["lbl_censored"],
                        "y_cumul": r["y_cumul"], "y_peak1": r["y_peak1"], "y_peak3": r["y_peak3"],
                        "y_peak1_res": r["y_peak1_res"], "y_peak3_res": r["y_peak3_res"],
                        "surplus": r["surplus"]})
    return out


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------
def _sp(rows, pred_key, y_key):
    xs = [r[pred_key] for r in rows]; ys = [r[y_key] for r in rows]
    return _spearman(xs, ys)


def _auc_cell(rows, pred_key, y_key, thr):
    labels = [r[y_key] >= thr for r in rows]
    npos = sum(1 for l in labels if l)
    if npos == 0 or npos == len(labels):
        return None
    return {"auc": _auc([r[pred_key] for r in rows], labels), "n_pos": npos, "thr": thr}


def score_block(rows, subset="full"):
    """Spearman + AUC for BOTH raters (eFV blend, consensus) against cumulative / peak1 /
    peak3 ground truths. subset 'resolved' restricts to fully-resolved players and scores
    against the resolved (_res) peak labels (clean truth, no censoring extrapolation)."""
    if subset == "resolved":
        rs = [r for r in rows if not r["lbl_censored"]]
        gt = {"cumulative": "y_cumul", "peak1": "y_peak1_res", "peak3": "y_peak3_res"}
    else:
        rs = rows
        gt = {"cumulative": "y_cumul", "peak1": "y_peak1", "peak3": "y_peak3"}
    block = {"n": len(rs)}
    for name, yk in gt.items():
        cell = {
            "spearman": {"efv": _r(_sp(rs, "blend", yk)), "consensus": _r(_sp(rs, "cons", yk))},
        }
        for lvl in ("contributor", "star"):
            thr = THRESH[name][lvl]
            be = _auc_cell(rs, "blend", yk, thr); co = _auc_cell(rs, "cons", yk, thr)
            if be and co:
                cell[f"auc_{lvl}"] = {"efv": _r(be["auc"]), "consensus": _r(co["auc"]),
                                      "n_pos": be["n_pos"], "thr": thr}
        cell["spearman"]["delta"] = _r((_sp(rs, "blend", yk) or 0) - (_sp(rs, "cons", yk) or 0))
        block[name] = cell
    return block


def _r(x, n=4):
    return None if x is None else round(x, n)


# ---------------------------------------------------------------------------
# surplus-weighted accuracy (Clemens-2026 basis)
# ---------------------------------------------------------------------------
def _ndcg(rows, pred_key, gain_key, k=None):
    """NDCG: rank players by `pred_key` desc, gain = realized surplus. Rewards putting
    high-surplus players near the top; DCG discount = 1/log2(rank+1). k limits to the
    top-k ranked. IDCG is the same gains sorted by gain desc."""
    order = sorted(rows, key=lambda r: r[pred_key], reverse=True)
    ideal = sorted(rows, key=lambda r: r[gain_key], reverse=True)
    if k:
        order = order[:k]; ideal = ideal[:k]
    dcg = sum(r[gain_key] / math.log2(i + 2) for i, r in enumerate(order))
    idcg = sum(r[gain_key] / math.log2(i + 2) for i, r in enumerate(ideal))
    return (dcg / idcg) if idcg else None


def _topk_capture(rows, pred_key, gain_key, frac):
    """Fraction of TOTAL realized surplus captured by the top-`frac` of players ranked by
    `pred_key` (the ideal rater captures the most)."""
    k = max(1, int(round(frac * len(rows))))
    order = sorted(rows, key=lambda r: r[pred_key], reverse=True)[:k]
    tot = sum(r[gain_key] for r in rows) or 1.0
    return sum(r[gain_key] for r in order) / tot


def _weighted_spearman(rows, pred_key, gain_key):
    """Rank correlation between prediction and realized surplus, each observation weighted
    by its realized surplus (high-value players dominate). Weighted Pearson on ranks."""
    n = len(rows)
    if n < 3:
        return None
    def ranks(vals):
        order = sorted(range(n), key=lambda i: vals[i])
        rk = [0.0] * n; i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for t in range(i, j + 1):
                rk[order[t]] = avg
            i = j + 1
        return rk
    pr = ranks([r[pred_key] for r in rows])
    gr = ranks([r[gain_key] for r in rows])
    w = [max(r[gain_key], 0.0) for r in rows]
    W = sum(w) or 1.0
    mp = sum(wi * x for wi, x in zip(w, pr)) / W
    mg = sum(wi * x for wi, x in zip(w, gr)) / W
    cov = sum(wi * (x - mp) * (y - mg) for wi, x, y in zip(w, pr, gr)) / W
    vp = sum(wi * (x - mp) ** 2 for wi, x in zip(w, pr)) / W
    vg = sum(wi * (y - mg) ** 2 for wi, y in zip(w, gr)) / W
    return cov / math.sqrt(vp * vg) if vp > 0 and vg > 0 else None


def surplus_weighted_block(rows):
    """eFV-vs-consensus under Clemens-2026 surplus weighting: NDCG (all / top-20% / top-10%),
    top-quintile & top-decile surplus capture, surplus-weighted Spearman."""
    out = {"n": len(rows), "total_surplus_musd": _r(sum(r["surplus"] for r in rows), 1),
           "surplus_gini_note": "gain = discounted realized first-6 WAR $ under clemens_2026"}
    k20 = max(1, int(round(0.20 * len(rows)))); k10 = max(1, int(round(0.10 * len(rows))))
    out["ndcg_all"] = {"efv": _r(_ndcg(rows, "blend", "surplus")),
                       "consensus": _r(_ndcg(rows, "cons", "surplus"))}
    out["ndcg_top20"] = {"efv": _r(_ndcg(rows, "blend", "surplus", k20)),
                         "consensus": _r(_ndcg(rows, "cons", "surplus", k20))}
    out["ndcg_top10"] = {"efv": _r(_ndcg(rows, "blend", "surplus", k10)),
                         "consensus": _r(_ndcg(rows, "cons", "surplus", k10))}
    out["capture_top20pct"] = {"efv": _r(_topk_capture(rows, "blend", "surplus", 0.20)),
                               "consensus": _r(_topk_capture(rows, "cons", "surplus", 0.20)),
                               "ideal": _r(_topk_capture(rows, "surplus", "surplus", 0.20))}
    out["capture_top10pct"] = {"efv": _r(_topk_capture(rows, "blend", "surplus", 0.10)),
                               "consensus": _r(_topk_capture(rows, "cons", "surplus", 0.10)),
                               "ideal": _r(_topk_capture(rows, "surplus", "surplus", 0.10))}
    out["weighted_spearman"] = {"efv": _r(_weighted_spearman(rows, "blend", "surplus")),
                                "consensus": _r(_weighted_spearman(rows, "cons", "surplus"))}
    for key in ("ndcg_all", "ndcg_top20", "ndcg_top10", "capture_top20pct",
                "capture_top10pct", "weighted_spearman"):
        e, c = out[key]["efv"], out[key]["consensus"]
        out[key]["win"] = (e is not None and c is not None and e > c)
        out[key]["margin"] = _r((e - c) if (e is not None and c is not None) else None)
    return out


# ---------------------------------------------------------------------------
# biggest-disagreements under peak vs cumulative
# ---------------------------------------------------------------------------
def disagreement_block(rows, topn=40):
    """The largest |eFV blend - consensus| disagreements (shipped predictions). For a
    FIXED disagreement set, who is 'right' (prediction closer to the realized label)
    changes with the ground truth -- report eFV-correct rate judged by cumulative vs peak1
    vs peak3. Answers: does the peak target change who's right on the biggest misses?"""
    ds = sorted(rows, key=lambda r: abs(r["blend"] - r["cons"]), reverse=True)[:topn]
    out = {"n": len(ds)}
    for name, yk in (("cumulative", "y_cumul"), ("peak1", "y_peak1"), ("peak3", "y_peak3")):
        # both raters are on their own scale; compare via rank error against the label rank
        # within the disagreement set: eFV 'wins' a row when its prediction rank is closer
        # to the realized-label rank than consensus is.
        n = len(ds)
        def rk(key):
            order = sorted(range(n), key=lambda i: ds[i][key])
            rr = [0] * n
            for pos, i in enumerate(order):
                rr[i] = pos
            return rr
        lr = rk(yk); br = rk("blend"); cr = rk("cons")
        ewins = sum(1 for i in range(n) if abs(br[i] - lr[i]) < abs(cr[i] - lr[i]))
        cwins = sum(1 for i in range(n) if abs(cr[i] - lr[i]) < abs(br[i] - lr[i]))
        out[name] = {"efv_closer": ewins, "cons_closer": cwins,
                     "efv_win_rate": _r(ewins / (ewins + cwins), 3) if (ewins + cwins) else None}
    # top receipts (player, blend, cons, all labels)
    out["receipts"] = [{"pk": r["pk"], "fv": r["fv"], "year": r["year"],
                        "blend": _r(r["blend"], 2), "cons": _r(r["cons"], 2),
                        "disagreement": _r(r["blend"] - r["cons"], 2),
                        "cumul": _r(r["y_cumul"], 2), "peak1": _r(r["y_peak1"], 2),
                        "peak3": _r(r["y_peak3"], 2), "surplus_musd": _r(r["surplus"], 1)}
                       for r in ds[:20]]
    return out


# ---------------------------------------------------------------------------
# PART B: retrain on peak targets, paired bootstrap CI on the Spearman delta
# ---------------------------------------------------------------------------
def _paired_boot(base_rows, var_rows, y_key, nboot=2000, seed=17):
    """Paired bootstrap of the OOS Spearman delta (variant blend - baseline blend) against
    ground truth y_key. base_rows/var_rows are aligned by player index (same test pool,
    same order). Returns mean delta + lo95/hi95. Resamples player indices with replacement."""
    rng = random.Random(seed)
    n = len(base_rows)
    idx = list(range(n))
    by = [base_rows[i]["blend"] for i in idx]; vy = [var_rows[i]["blend"] for i in idx]
    yy = [base_rows[i][y_key] for i in idx]
    base = _spearman(by, yy); var = _spearman(vy, yy)
    point = (var - base) if (base is not None and var is not None) else None
    deltas = []
    for _ in range(nboot):
        samp = [rng.randrange(n) for _ in range(n)]
        b = _spearman([by[i] for i in samp], [yy[i] for i in samp])
        v = _spearman([vy[i] for i in samp], [yy[i] for i in samp])
        if b is not None and v is not None:
            deltas.append(v - b)
    deltas.sort()
    lo = deltas[int(0.025 * len(deltas))] if deltas else None
    hi = deltas[int(0.975 * len(deltas))] if deltas else None
    return {"point": _r(point), "lo95": _r(lo), "hi95": _r(hi),
            "base": _r(base), "variant": _r(var)}


def part_b(side, cw, dyr):
    """Retrain on peak1 / peak3 / blend_std; measure OOS Spearman/AUC vs cumulative AND
    peak, paired-bootstrap the Spearman delta vs the shipped cumulative-target baseline
    on BOTH the cumulative (surplus-pricing) and the peak (grade) ground truths."""
    base = forward_read(side, "cumulative", cw, dyr)   # shipped target
    base_ix = {r["pk"] + "|" + str(r["year"]): r for r in base}
    variants = {}
    for tgt in ("peak1", "peak3", "blend_std:0.75", "blend_std", "blend_std:0.25"):
        v = forward_read(side, tgt, cw, dyr)
        # align to baseline pool (same rows/order guaranteed by identical folds, but join to be safe)
        vb, bb = [], []
        for r in v:
            k = r["pk"] + "|" + str(r["year"])
            if k in base_ix:
                vb.append(r); bb.append(base_ix[k])
        block = {"n": len(vb), "train_target": tgt}
        # measured OOS accuracy of the retrained blend against each ground truth
        block["oos"] = {
            "vs_cumulative": {"spearman": _r(_sp(vb, "blend", "y_cumul"))},
            "vs_peak1": {"spearman": _r(_sp(vb, "blend", "y_peak1"))},
            "vs_peak3": {"spearman": _r(_sp(vb, "blend", "y_peak3"))},
        }
        for gtname, yk in (("cumulative", "y_cumul"), ("peak1", "y_peak1"), ("peak3", "y_peak3")):
            for lvl in ("contributor", "star"):
                c = _auc_cell(vb, "blend", yk, THRESH[gtname][lvl])
                if c:
                    block["oos"][f"vs_{gtname}"][f"auc_{lvl}"] = _r(c["auc"])
        # paired bootstrap delta vs the shipped baseline blend, per ground truth
        block["delta_vs_shipped"] = {
            "on_cumulative": _paired_boot(bb, vb, "y_cumul"),
            "on_peak1": _paired_boot(bb, vb, "y_peak1"),
            "on_peak3": _paired_boot(bb, vb, "y_peak3"),
        }
        variants[tgt] = block
    # shipped baseline's own OOS numbers for reference
    base_oos = {
        "vs_cumulative": _r(_sp(base, "blend", "y_cumul")),
        "vs_peak1": _r(_sp(base, "blend", "y_peak1")),
        "vs_peak3": _r(_sp(base, "blend", "y_peak3")),
    }
    return {"n": len(base), "shipped_baseline_oos": base_oos, "variants": variants}


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------
def run_side(side, cw, dyr):
    shipped = forward_read(side, "cumulative", cw, dyr)
    measA = {
        "n": len(shipped),
        "full_pool": score_block(shipped, "full"),
        "resolved_only": score_block(shipped, "resolved"),
        "surplus_weighted": surplus_weighted_block(shipped),
        "disagreements": disagreement_block(shipped),
    }
    modelB = part_b(side, cw, dyr)
    return measA, modelB


def main():
    cw = _load_career_war_seasons()
    peak_eval = {"generated_by": "tools/efv_peak_war_lab.py",
                 "registration": "docs/efv-2026-07-24/GATES-ROUND2.md L3 PEAK-WAR-TARGET",
                 "protocol": {"folds": "forward-chained SCORED_YEARS 2020-2023",
                              "floors": f"train>={MIN_TRAIN}, test>={MIN_TEST}",
                              "target": "PART B retrains OLS(FV)+ridge on the named target; "
                                        "Spearman/AUC are rank metrics (scale-free)",
                              "labels": "peak1/peak3 from career_war seasons, window debut..debut+5, "
                                        "missing-in-window=0, censored tail filled at observed rate "
                                        "(analog of efv_dataset._label_6yr)"},
                 "auc_thresholds": THRESH, "sides": {}}
    meas_cal = {"generated_by": "tools/efv_peak_war_lab.py",
                "registration": "docs/efv-2026-07-24/GATES-ROUND2.md L3 (Part A measurement calibration)",
                "clemens_2026_basis": {
                    "valuation_set": VF.active_valuation_set(),
                    "weight": "discounted realized first-6 WAR $ (value_framework.tiered_war_value_usd, "
                              "per-season floored at $0, 7% discount to debut)",
                    "metrics": "NDCG (gain=surplus), top-quintile/decile surplus capture, surplus-weighted Spearman"},
                "sides": {}}
    for side in ("hit", "pit"):
        dyr = _load_debut_years(side)
        measA, modelB = run_side(side, cw, dyr)
        peak_eval["sides"][side] = {"model_partB": modelB,
                                    "measurement_full_pool": measA["full_pool"],
                                    "measurement_resolved_only": measA["resolved_only"]}
        meas_cal["sides"][side] = {"accuracy_vs_ground_truths": {
                                       "full_pool": measA["full_pool"],
                                       "resolved_only": measA["resolved_only"]},
                                   "surplus_weighted": measA["surplus_weighted"],
                                   "disagreements": measA["disagreements"]}
    (DATA / "xfv_peak_war_eval.json").write_text(json.dumps(peak_eval, indent=1), encoding="utf-8")
    (DATA / "xfv_measurement_calibration_eval.json").write_text(json.dumps(meas_cal, indent=1), encoding="utf-8")
    # console summary
    for side in ("hit", "pit"):
        pb = peak_eval["sides"][side]["model_partB"]
        b = pb["shipped_baseline_oos"]
        print(f"\n=== {side} ===  shipped blend OOS Spearman:  vs_cumul={b['vs_cumulative']} "
              f"vs_peak1={b['vs_peak1']} vs_peak3={b['vs_peak3']}")
        mf = peak_eval["sides"][side]["measurement_full_pool"]
        for gt in ("cumulative", "peak1", "peak3"):
            sp = mf[gt]["spearman"]
            print(f"   MEAS full  eFV-vs-{gt:10s} rho={sp['efv']}  cons={sp['consensus']}  d={sp['delta']}")
        for tgt, blk in pb["variants"].items():
            dc = blk["delta_vs_shipped"]["on_cumulative"]; d3 = blk["delta_vs_shipped"]["on_peak3"]
            print(f"   MODEL train={tgt:9s} OOS vs_cumul={blk['oos']['vs_cumulative']['spearman']} "
                  f"vs_peak3={blk['oos']['vs_peak3']['spearman']} | "
                  f"delta-on-cumul {dc['point']} [{dc['lo95']},{dc['hi95']}] | "
                  f"delta-on-peak3 {d3['point']} [{d3['lo95']},{d3['hi95']}]")
        sw = meas_cal["sides"][side]["surplus_weighted"]
        print(f"   SURPLUS-WTD ndcg_all eFV={sw['ndcg_all']['efv']} cons={sw['ndcg_all']['consensus']} "
              f"win={sw['ndcg_all']['win']} | cap20 eFV={sw['capture_top20pct']['efv']} "
              f"cons={sw['capture_top20pct']['consensus']} ideal={sw['capture_top20pct']['ideal']}")
    print("\nwrote data/xfv_peak_war_eval.json + data/xfv_measurement_calibration_eval.json")


if __name__ == "__main__":
    main()
