# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Lane C1 (master plan 2026-08-07b): was the reliability diagnostic measuring its
own label?

Pre-registration: docs/efv-2026-08-07b/DISTRIBUTION_CALIBRATION_GATE.md, written in
full (sections 0-4 plus a literal section-5 placeholder) BEFORE this file existed.

WHAT: D3 says the SERVED five-bucket outcome distribution is miscalibrated monotonically
in consensus-FV tier. D4 says the diagnostic's realized bucket is a CENSORED label divided
by a constant 6. B1 measured that label and found its flat-rate tail projection biased
pessimistic. A pessimistic label inflates realized bust and deflates realized good/star,
which is the sign of the observed miscalibration. This lab measures how much of D3 is the
diagnostic grading the model against its own label error.

HOW: hold the shipped forward-chained OOF chain FIXED (predictions identical row for row)
and vary only the realized bucket and the evaluated row set:
  (a) shipped censored label / 6
  (b) resolved-only rows
  (c) every row, censored labels corrected by the empirical season-share ratio estimator
  (d) NON-PRIMARY sensitivity: the whole chain refit on the corrected label

Writes exactly one artifact: data/xfv_dist_calibration_eval.json.
Recalibrates NOTHING. Touches no served number, no config, no valuation set.

Run: python tools/efv_dist_calibration_lab.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import efv_dataset as ds                 # noqa: E402
import efv_odds_calibration as _odds_cal  # noqa: E402
import efv_reliability as rel            # noqa: E402
import storage                           # noqa: E402

DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "xfv_dist_calibration_eval.json"
GATE_DOC = "docs/efv-2026-08-07b/DISTRIBUTION_CALIBRATION_GATE.md"

PERM_B = 200
PERM_SEED = 20260807
SIDES = ("hit", "pit")

# Pre-registered decision bars (gate section 4.1). SELF-ADDED: the master plan says
# "shrinks materially" and does not quantify it.
CONFIRM_R = 0.50
PARTIAL_R = 0.20
CTRL1_SHARE_BAR = 0.80
FPR_BAR = 0.25


# ---------------------------------------------------------------------------
# source data
# ---------------------------------------------------------------------------

def career_war() -> dict[str, dict[int, float]]:
    """{player_key: {year: bWAR}} - the same table efv_dataset._label_6yr reads."""
    cw: dict[str, dict[int, float]] = {}
    with storage.connect() as con:
        for r in con.execute("SELECT player_key, payload_json FROM career_war"):
            try:
                seasons = (json.loads(r["payload_json"]) or {}).get("seasons") or {}
            except ValueError:
                continue
            cw[r["player_key"]] = {int(y): float(w) for y, w in seasons.items()}
    return cw


def matrix_rows() -> dict[str, dict[str, dict]]:
    """{side: {player_key: matrix row}} over the SAME pool efv_reliability._oof_rows uses."""
    out = {}
    for side in SIDES:
        is_pit = side == "pit"
        rows = json.loads(ds.matrix_path(side).read_text(encoding="utf-8"))
        pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
                and not (r["kind"] == "bust" and r.get("bust_recent"))]
        out[side] = {r["player_key"]: r for r in pool}
    return out


# ---------------------------------------------------------------------------
# the corrected label (gate 2.3)
# ---------------------------------------------------------------------------

def share_profile(src: dict[str, dict[str, dict]], cw: dict, debut_lo: int | None = None,
                  debut_hi: int | None = None) -> dict:
    """Empirical per-season-index share of the six-year WAR total, per side, on the
    FULLY RESOLVED debuted pool. Optionally restricted to a debut-year window (SENS-1)."""
    prof = {}
    for side in SIDES:
        tot = np.zeros(ds.TARGET_SEASONS)
        n = 0
        for pk, r in src[side].items():
            if r.get("kind") != "debuted":
                continue
            dy = r.get("debut_year")
            if dy is None or dy + ds.TARGET_SEASONS - 1 > ds.RESOLVED_THROUGH:
                continue
            if debut_lo is not None and dy < debut_lo:
                continue
            if debut_hi is not None and dy > debut_hi:
                continue
            seasons = cw.get(pk) or {}
            tot += np.array([float(seasons.get(dy + i, 0.0)) for i in range(ds.TARGET_SEASONS)])
            n += 1
        mean = tot / max(n, 1)
        s = float(mean.sum())
        share = (mean / s) if s > 0 else np.full(ds.TARGET_SEASONS, 1.0 / ds.TARGET_SEASONS)
        prof[side] = {
            "n": n,
            "mean_war_by_season_index": [round(float(v), 4) for v in mean],
            "share": [round(float(v), 6) for v in share],
            "cum_share": [round(float(share[:k].sum()), 6) for k in range(ds.TARGET_SEASONS + 1)],
            "factor_by_n_obs": {str(k): round(float((k / ds.TARGET_SEASONS) / share[:k].sum()), 6)
                                for k in range(1, ds.TARGET_SEASONS)},
        }
    return prof


def corrected_targets(src, cw, prof) -> tuple[dict, dict, dict]:
    """Per side: {player_key: corrected_target}, plus the obs_sum reconciliation and
    the per-row multiplicative factor. Identity on every non-censored row (CTRL-0)."""
    corrected, recon, factors = {}, {"checked": 0, "match": 0, "mismatch": 0,
                                     "mismatch_examples": []}, {}
    for side in SIDES:
        cs, fs = {}, {}
        cum = np.array(prof[side]["cum_share"])
        for pk, r in src[side].items():
            shipped = r.get("target_censored")
            if shipped is None:
                continue
            if not r.get("censored"):
                cs[pk] = float(shipped)
                fs[pk] = 1.0
                continue
            dy = int(r["debut_year"])
            n_obs = int(r["observed_seasons"])
            seasons = cw.get(pk) or {}
            window = [dy + i for i in range(ds.TARGET_SEASONS)]
            observed = [y for y in window if y <= ds.RESOLVED_THROUGH]
            obs_sum = round(sum(float(seasons.get(y, 0.0)) for y in observed), 3)
            recon["checked"] += 1
            want = round(obs_sum + (ds.TARGET_SEASONS - n_obs) * (obs_sum / n_obs if n_obs else 0.0), 3)
            if abs(want - float(shipped)) <= 1e-3 and len(observed) == n_obs:
                recon["match"] += 1
            else:
                recon["mismatch"] += 1
                if len(recon["mismatch_examples"]) < 8:
                    recon["mismatch_examples"].append(
                        {"player_key": pk, "side": side, "shipped": float(shipped),
                         "recomputed": want, "n_obs": n_obs, "n_observed_years": len(observed)})
            denom = float(cum[n_obs]) if n_obs < ds.TARGET_SEASONS else 1.0
            cs[pk] = round(obs_sum / denom, 3) if denom > 0 else float(shipped)
            fs[pk] = (cs[pk] / float(shipped)) if shipped else 1.0
        corrected[side] = cs
        factors[side] = fs
    return corrected, recon, factors


# ---------------------------------------------------------------------------
# the chain. Arms (a)/(b)/(c) reuse the SHIPPED rows; arm (d) refits.
# ---------------------------------------------------------------------------

def refit_chain(side: str, target_map: dict[str, float] | None) -> list[dict]:
    """Mirror of efv_reliability._oof_rows with the fit/eval target swappable.
    Verified against the shipped function by running it with target_map=None
    (identity) and requiring byte-identical output (see `mirror_check`)."""
    import value_framework as vf
    from efv_dataset import matrix_path, TARGET_SEASONS
    from efv_model import _prep, _feature_spec
    from efv_score import _age_at, _grade_map_age
    from prospect_path import _fit_ridge, _predict, _fit_linear_calibration

    is_pit = side == "pit"
    keys, _mono = _feature_spec(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
            and not (r["kind"] == "bust" and r.get("bust_recent"))]
    data = _prep(pool, "target_censored", side)
    if target_map is not None:
        data = [dict(r, target=float(target_map.get(r["player_key"], r["target"]))) for r in data]
    by_key = {r["player_key"]: r for r in pool}

    out: list[dict] = []
    for yr in rel.CHAIN_YEARS:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < rel.MIN_TEST or len(tr) < rel.MIN_TRAIN:
            continue
        ridge = _fit_ridge(tr, keys)
        if not ridge:
            continue
        cal = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
        a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        for r in te:
            s = by_key[r["player_key"]]
            xfv_war = max(-2.0, a + b * _predict(ridge, r["feats"]))
            dyear = s.get("debut_year") or 2020
            age = _age_at(s.get("birth_date"), dyear)
            grade = vf.realized_implied_fv(xfv_war, is_pit, age=_grade_map_age(age, 0.0),
                                           position=s.get("position"),
                                           exposure_seasons=TARGET_SEASONS)
            if grade is None:
                continue
            probs = vf.p_bucket_given_fv(grade, is_pit)
            if not probs or len(probs) != len(rel.BUCKETS):
                continue
            probs_after = _odds_cal.recalibrate_bucket(probs, is_pit,
                                                       provisional=not s.get("milb"))
            out.append({"player_key": r["player_key"], "side": side, "decision_year": yr,
                        "fv": r["fv"], "p_before": np.asarray(probs, dtype=float),
                        "p_after": np.asarray(probs_after, dtype=float),
                        "y": rel._realized_bucket(r["target"]), "weight": float(r["weight"])})
    return out


def mirror_check(shipped: list[dict], mirrored: list[dict]) -> dict:
    """Arm (d)'s chain must reproduce the shipped chain exactly when given no override."""
    ok = len(shipped) == len(mirrored)
    maxdp = 0.0
    ydiff = 0
    if ok:
        for u, v in zip(shipped, mirrored, strict=False):
            if u["player_key"] != v["player_key"] or u["decision_year"] != v["decision_year"]:
                ok = False
                break
            maxdp = max(maxdp, float(np.max(np.abs(u["p_after"] - v["p_after"]))))
            ydiff += int(u["y"] != v["y"])
    return {"identical_length": len(shipped) == len(mirrored), "row_order_ok": bool(ok),
            "max_abs_p_after_delta": round(float(maxdp), 12), "n_y_differences": int(ydiff),
            "pass": bool(ok and maxdp < 1e-12 and ydiff == 0)}


# ---------------------------------------------------------------------------
# metrics (gate 2.4) - the SHIPPED functions, not reimplementations
# ---------------------------------------------------------------------------

def metrics(rows: list[dict]) -> dict:
    curves_after = rel._reliability_bins(rows, key="p_after")
    curves_before = rel._reliability_bins(rows, key="p_before")
    tiers = rel._tier_reliability(rows, key="p_after")
    if tiers:
        ns = np.array([tiers[t]["n"] for t in tiers], dtype=float)
        gaps = np.array([tiers[t]["gap"] for t in tiers], dtype=float)
        wgap = float((ns * gaps).sum() / ns.sum())
        ugap = float(gaps.mean())
    else:
        wgap = ugap = float("nan")
    signed = {}
    for t, v in tiers.items():
        signed[t] = {bk: round(v["realized_freq"][bk] - v["mean_p"][bk], 4)
                     for bk in ("bust", "good", "star")}
    return {
        "n": len(rows),
        "ece_after": {k: curves_after[k]["ece"] for k in rel.BUCKETS},
        "ece_before": {k: curves_before[k]["ece"] for k in rel.BUCKETS},
        "bust_ece": curves_after["bust"]["ece"],
        "tier_gap_weighted": round(wgap, 5),
        "tier_gap_unweighted": round(ugap, 5),
        "per_tier": tiers,
        "signed_tier_residual": signed,
        "bucket_counts": {rel.BUCKETS[i]: int(sum(1 for r in rows if r["y"] == i))
                          for i in range(len(rel.BUCKETS))},
    }


def oracle_bust_ece(rows: list[dict], cens_flag: dict, n_bins: int = 10) -> dict:
    """Smallest pooled bust ECE reachable by relabelling ONLY the censored rows.
    Mirrors rel._reliability_bins' binning exactly (equal-width, bins under 5 dropped,
    denominator = the full row count)."""
    p = np.array([r["p_after"][0] for r in rows])
    is_bust = np.array([1.0 if r["y"] == 0 else 0.0 for r in rows])
    cens = np.array([bool(cens_flag[r["side"]].get(r["player_key"])) for r in rows])
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece, detail = 0.0, []
    for i in range(n_bins):
        m = (p >= edges[i]) & (p < edges[i + 1] if i < n_bins - 1 else p <= 1.0)
        nb = int(m.sum())
        if nb < 5:
            continue
        mp = float(p[m].mean())
        fixed = float(is_bust[m][~cens[m]].sum())
        n_cens = int(cens[m].sum())
        want = mp * nb - fixed
        chosen = float(np.clip(round(want), 0, n_cens))
        fr = (fixed + chosen) / nb
        ece += (nb / len(p)) * abs(mp - fr)
        detail.append({"bin": [round(float(edges[i]), 2), round(float(edges[i + 1]), 2)],
                       "n": nb, "n_censored": n_cens, "mean_p": round(mp, 4),
                       "freq_shipped": round(float(is_bust[m].mean()), 4),
                       "freq_oracle": round(fr, 4)})
    return {"oracle_bust_ece": round(float(ece), 5), "bins": detail}


def relabel(rows: list[dict], tmap: dict[str, dict[str, float]]) -> list[dict]:
    """New row list with `y` recomputed from a {side: {player_key: target}} map."""
    out = []
    for r in rows:
        t = tmap.get(r["side"], {}).get(r["player_key"])
        out.append(r if t is None else dict(r, y=rel._realized_bucket(t)))
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    cw = career_war()
    src = matrix_rows()

    shipped_rows = {s: rel._oof_rows(s) for s in SIDES}
    pooled_a = [r for s in SIDES for r in shipped_rows[s]]

    shipped_t = {s: {pk: float(r["target_censored"]) for pk, r in src[s].items()
                     if r.get("target_censored") is not None} for s in SIDES}

    prof = share_profile(src, cw)
    corrected, recon, factors = corrected_targets(src, cw, prof)

    # CTRL-0: identity on every non-censored row.
    ctrl0 = {"checked": 0, "violations": 0, "examples": []}
    for s in SIDES:
        for pk, r in src[s].items():
            if r.get("censored") or r.get("target_censored") is None:
                continue
            ctrl0["checked"] += 1
            if abs(corrected[s][pk] - float(r["target_censored"])) > 1e-9:
                ctrl0["violations"] += 1
                if len(ctrl0["examples"]) < 5:
                    ctrl0["examples"].append({"player_key": pk, "side": s})
    ctrl0["pass"] = ctrl0["violations"] == 0

    # which OOF eval rows are censored, and per-tier censored share (M5)
    cens_flag = {s: {pk: bool(r.get("censored")) for pk, r in src[s].items()} for s in SIDES}
    n_cens_eval = sum(1 for r in pooled_a if cens_flag[r["side"]].get(r["player_key"]))
    nobs_eval = Counter(int(src[r["side"]][r["player_key"]].get("observed_seasons") or 0)
                        for r in pooled_a if cens_flag[r["side"]].get(r["player_key"]))
    tier_cens = defaultdict(lambda: [0, 0])
    for r in pooled_a:
        tk = rel._tier(r["fv"])
        tier_cens[tk][0] += 1
        if cens_flag[r["side"]].get(r["player_key"]):
            tier_cens[tk][1] += 1
    m5 = {str(k): {"n": v[0], "n_censored": v[1], "censored_share": round(v[1] / v[0], 4)}
          for k, v in sorted(tier_cens.items())}
    # Reason 3 of the write-up: how much of each tier's realized-BUST mass is
    # never-debuted `kind == "bust"` rows, whose label is exactly 0.0 and uncensored and
    # which therefore no tail-projection correction can reach.
    for tk, v in sorted(tier_cens.items()):
        rows_t = [r for r in pooled_a if rel._tier(r["fv"]) == tk]
        nbust_kind = sum(1 for r in rows_t if src[r["side"]][r["player_key"]]["kind"] == "bust")
        real_bust = [r for r in rows_t if r["y"] == 0]
        nb_kind = sum(1 for r in real_bust
                      if src[r["side"]][r["player_key"]]["kind"] == "bust")
        m5[str(tk)].update({
            "n_never_debuted_bust_kind": nbust_kind,
            "n_realized_bust": len(real_bust),
            "share_of_realized_bust_that_is_never_debuted": (
                round(nb_kind / len(real_bust), 4) if real_bust else None)})

    # ---- arms -------------------------------------------------------------
    arm_a = metrics(pooled_a)
    pooled_c_rows = relabel(pooled_a, corrected)
    arm_c = metrics(pooled_c_rows)
    resolved_rows = [r for r in pooled_a if not cens_flag[r["side"]].get(r["player_key"])]
    arm_b = metrics(resolved_rows)

    # CTRL-5: mechanical ceiling.
    n_bucket_changed = sum(1 for u, v in zip(pooled_a, pooled_c_rows, strict=False) if u["y"] != v["y"])
    dirn = Counter("up" if v["y"] > u["y"] else "down"
                   for u, v in zip(pooled_a, pooled_c_rows, strict=False) if u["y"] != v["y"])
    ctrl5 = {"n_pool": len(pooled_a), "n_censored_in_pool": n_cens_eval,
             "n_bucket_changed": n_bucket_changed,
             "pct_of_pool": round(100.0 * n_bucket_changed / max(len(pooled_a), 1), 3),
             "pct_of_censored": round(100.0 * n_bucket_changed / max(n_cens_eval, 1), 3),
             "direction": dict(dirn),
             "observed_seasons_in_eval_pool": {str(k): v for k, v in sorted(nobs_eval.items())}}

    def red(m_new, m_ref, key):
        ref = m_ref[key]
        return round(1.0 - (m_new[key] / ref), 5) if ref else None

    R1 = red(arm_c, arm_a, "bust_ece")
    R2 = red(arm_c, arm_a, "tier_gap_weighted")

    # ---- CTRL-1: zero-information constant --------------------------------
    cens_keys = [(s, pk) for s in SIDES for pk in src[s] if cens_flag[s][pk]
                 and src[s][pk].get("target_censored") is not None]
    tot_ship = sum(shipped_t[s][pk] for s, pk in cens_keys)
    tot_corr = sum(corrected[s][pk] for s, pk in cens_keys)
    kconst = (tot_corr / tot_ship) if tot_ship else 1.0
    const_map = {s: {pk: shipped_t[s][pk] * kconst for pk in src[s] if cens_flag[s][pk]
                     and src[s][pk].get("target_censored") is not None} for s in SIDES}
    arm_const = metrics(relabel(pooled_a, const_map))
    R1c = red(arm_const, arm_a, "bust_ece")
    R2c = red(arm_const, arm_a, "tier_gap_weighted")
    ctrl1 = {"constant": round(float(kconst), 6),
             "bust_ece": arm_const["bust_ece"], "tier_gap_weighted": arm_const["tier_gap_weighted"],
             "R1": R1c, "R2": R2c,
             "share_of_R1": (round(R1c / R1, 4) if R1 not in (None, 0) else None),
             "share_of_R2": (round(R2c / R2, 4) if R2 not in (None, 0) else None),
             "bar": CTRL1_SHARE_BAR}
    ctrl1["level_effect_only"] = bool(
        ctrl1["share_of_R1"] is not None and ctrl1["share_of_R1"] >= CTRL1_SHARE_BAR)

    # ---- CTRL-2: permuted correction factors ------------------------------
    rng = np.random.default_rng(PERM_SEED)
    perm_R1, perm_R2 = [], []
    for _ in range(PERM_B):
        pmap = {}
        for s in SIDES:
            ks = [pk for pk in src[s] if cens_flag[s][pk] and src[s][pk].get("target_censored") is not None]
            fac = np.array([factors[s][pk] for pk in ks])
            rng.shuffle(fac)
            pmap[s] = {pk: shipped_t[s][pk] * float(f) for pk, f in zip(ks, fac, strict=False)}
        m = metrics(relabel(pooled_a, pmap))
        perm_R1.append(red(m, arm_a, "bust_ece"))
        perm_R2.append(red(m, arm_a, "tier_gap_weighted"))
    ctrl2 = {"B": PERM_B, "seed": PERM_SEED,
             "R1_mean": round(float(np.mean(perm_R1)), 5),
             "R1_p05": round(float(np.percentile(perm_R1, 5)), 5),
             "R1_p95": round(float(np.percentile(perm_R1, 95)), 5),
             "R2_mean": round(float(np.mean(perm_R2)), 5),
             "R2_p05": round(float(np.percentile(perm_R2, 5)), 5),
             "R2_p95": round(float(np.percentile(perm_R2, 95)), 5),
             "actual_R1": R1, "actual_R2": R2}
    ctrl2["R1_outside_band"] = bool(R1 is not None and (R1 > ctrl2["R1_p95"] or R1 < ctrl2["R1_p05"]))
    ctrl2["R2_outside_band"] = bool(R2 is not None and (R2 > ctrl2["R2_p95"] or R2 < ctrl2["R2_p05"]))
    ctrl2["perm_p_R1"] = round(float((np.sum(np.array(perm_R1) >= R1) + 1) / (PERM_B + 1)), 5)
    ctrl2["perm_p_R2"] = round(float((np.sum(np.array(perm_R2) >= R2) + 1) / (PERM_B + 1)), 5)

    # ---- CTRL-3: wrong direction ------------------------------------------
    defl = {s: {pk: (shipped_t[s][pk] / factors[s][pk]) if factors[s][pk] else shipped_t[s][pk]
                for pk in src[s] if cens_flag[s][pk] and src[s][pk].get("target_censored") is not None}
            for s in SIDES}
    arm_defl = metrics(relabel(pooled_a, defl))
    ctrl3 = {"bust_ece": arm_defl["bust_ece"], "tier_gap_weighted": arm_defl["tier_gap_weighted"],
             "R1": red(arm_defl, arm_a, "bust_ece"), "R2": red(arm_defl, arm_a, "tier_gap_weighted")}
    ctrl3["pass"] = bool(arm_defl["bust_ece"] >= arm_a["bust_ece"]
                         and arm_defl["tier_gap_weighted"] >= arm_a["tier_gap_weighted"])

    # ---- CTRL-4: composition decomposition --------------------------------
    ctrl4 = {}
    for key in ("bust_ece", "tier_gap_weighted"):
        d_label = round(arm_c[key] - arm_a[key], 6)
        d_comp = round(arm_b[key] - arm_c[key], 6)
        total = round(arm_b[key] - arm_a[key], 6)
        ctrl4[key] = {"a": arm_a[key], "b_resolved_only": arm_b[key], "c_corrected": arm_c[key],
                      "delta_label_only_a_to_c": d_label,
                      "delta_composition_only_c_to_b": d_comp,
                      "delta_total_a_to_b": total,
                      "identity_ok": bool(abs((d_label + d_comp) - total) < 1e-6)}
    ctrl4["note"] = ("a->b is CONFOUNDED (pool composition plus label); a->c is the "
                     "label-only measurement on an identical pool")

    # ---- CTRL-6: ORACLE upper bound ---------------------------------------
    # ADDED AFTER the primary run, and it is the control that could embarrass this
    # lane: it asks what the BEST POSSIBLE censored-label correction could do, not
    # what this particular one does. The bust ECE depends on the censored rows only
    # through whether each is labelled bust, so within each fixed probability bin the
    # optimum is closed-form. This is an exact upper bound on any relabelling of the
    # censored rows whatsoever, including a correct one.
    ctrl6 = oracle_bust_ece(pooled_a, cens_flag)
    ctrl6["arm_a_bust_ece"] = arm_a["bust_ece"]
    ctrl6["arm_c_bust_ece"] = arm_c["bust_ece"]
    ctrl6["max_possible_R1"] = (round(1.0 - ctrl6["oracle_bust_ece"] / arm_a["bust_ece"], 5)
                                if arm_a["bust_ece"] else None)
    ctrl6["note"] = ("upper bound on R1 over EVERY relabelling of the censored rows. If "
                     "this is below the CONFIRMED bar, no censored-label correction of any "
                     "kind can make D3 a censoring artifact.")

    # ---- CTRL-7: how big would the label error have to be? ----------------
    # CTRL-6 says an ORACLE relabelling could erase the bust ECE, so the SURVIVES
    # verdict must be shown to be about a PLAUSIBLE correction, not about a weak one.
    # Scan uniform multiplicative factors on the censored labels and report (i) the
    # factor that minimises the bust ECE and (ii) the structural ceiling of the whole
    # multiplicative family: a censored row with zero observed WAR stays at zero under
    # ANY factor, so it can never leave the bust bucket.
    scan = []
    for k in [1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0, 6.0, 10.0, 25.0]:
        km = {s: {pk: shipped_t[s][pk] * k for pk in src[s] if cens_flag[s][pk]
                  and src[s][pk].get("target_censored") is not None} for s in SIDES}
        m = metrics(relabel(pooled_a, km))
        scan.append({"factor": k, "bust_ece": m["bust_ece"],
                     "tier_gap_weighted": m["tier_gap_weighted"],
                     "R1": red(m, arm_a, "bust_ece")})
    best = min(scan, key=lambda z: z["bust_ece"])
    n_cens_zero = sum(1 for r in pooled_a if cens_flag[r["side"]].get(r["player_key"])
                      and abs(shipped_t[r["side"]][r["player_key"]]) < 1e-9)
    ctrl7 = {
        "uniform_factor_scan": scan,
        "best_factor": best,
        "b1_measured_factors_by_n_obs": {s: prof[s]["factor_by_n_obs"] for s in SIDES},
        "n_obs_present_in_eval_pool": ctrl5["observed_seasons_in_eval_pool"],
        "n_censored_eval_rows_with_zero_observed_war": n_cens_zero,
        "pct_of_censored_eval_rows_immovable": round(100.0 * n_cens_zero / max(n_cens_eval, 1), 3),
        "note": ("the immovable share is the structural ceiling of every multiplicative "
                 "tail-projection correction, the family _label_6yr belongs to"),
    }

    # ---- SENS-1: cohort drift in the share profile ------------------------
    sens1 = {}
    for name, lo, hi in (("debut_2011_2015", 2011, 2015), ("debut_2016_2020", 2016, 2020)):
        p = share_profile(src, cw, lo, hi)
        c, _r, _f = corrected_targets(src, cw, p)
        m = metrics(relabel(pooled_a, c))
        sens1[name] = {"profile_n": {s: p[s]["n"] for s in SIDES},
                       "factor_by_n_obs": {s: p[s]["factor_by_n_obs"] for s in SIDES},
                       "bust_ece": m["bust_ece"], "tier_gap_weighted": m["tier_gap_weighted"],
                       "R1": red(m, arm_a, "bust_ece"), "R2": red(m, arm_a, "tier_gap_weighted")}
    spread_R1 = abs(sens1["debut_2011_2015"]["R1"] - sens1["debut_2016_2020"]["R1"])
    sens1["R1_spread_between_cohort_profiles"] = round(float(spread_R1), 5)
    sens1["stable"] = bool(R1 is None or spread_R1 <= abs(R1) or abs(R1) < 1e-9)

    # ---- SENS-2 / arm (d): refit the chain on the corrected label ----------
    mirror = {s: mirror_check(shipped_rows[s], refit_chain(s, None)) for s in SIDES}
    arm_d_rows = [r for s in SIDES for r in refit_chain(s, corrected[s])]
    arm_d = metrics(arm_d_rows)
    sens2 = {"mirror_check": mirror,
             "mirror_pass": bool(all(m["pass"] for m in mirror.values())),
             "n": arm_d["n"], "bust_ece": arm_d["bust_ece"],
             "tier_gap_weighted": arm_d["tier_gap_weighted"],
             "R1": red(arm_d, arm_a, "bust_ece"), "R2": red(arm_d, arm_a, "tier_gap_weighted"),
             "per_tier": arm_d["per_tier"], "signed_tier_residual": arm_d["signed_tier_residual"],
             "note": "NON-PRIMARY. Refits the model on the corrected label, so predictions move too."}

    # ---- 4.0 stop conditions ----------------------------------------------
    ship = json.loads((DATA_DIR / "xfv_reliability.json").read_text(encoding="utf-8"))
    ship_bust = float(ship["tripwire"]["bust_ece"])
    stop = {
        "arm_a_reproduces_shipped": {
            "shipped_bust_ece": ship_bust, "shipped_pooled_n": ship.get("pooled_n"),
            "arm_a_bust_ece": arm_a["bust_ece"], "arm_a_n": arm_a["n"],
            "abs_delta": round(abs(arm_a["bust_ece"] - ship_bust), 6),
            "pass": bool(abs(arm_a["bust_ece"] - ship_bust) <= 0.005)},
        "obs_sum_reconciliation": dict(
            recon, mismatch_rate=round(recon["mismatch"] / max(recon["checked"], 1), 5),
            **{"pass": bool(recon["mismatch"] / max(recon["checked"], 1) <= 0.01)}),
        "ctrl0_noop_on_resolved": ctrl0,
        "ctrl3_wrong_direction": ctrl3,
    }
    stop["any_tripped"] = bool(not all(
        stop[k]["pass"] for k in ("arm_a_reproduces_shipped", "obs_sum_reconciliation",
                                  "ctrl0_noop_on_resolved", "ctrl3_wrong_direction")))

    # ---- 4.1 verdict -------------------------------------------------------
    if stop["any_tripped"]:
        verdict, why = "NULL", "a pre-registered stop condition tripped (gate 4.0)"
    elif R1 is not None and R2 is not None and R1 >= CONFIRM_R and R2 >= CONFIRM_R \
            and not ctrl1["level_effect_only"] and ctrl2["R1_outside_band"]:
        verdict, why = "CONFIRMED", "the diagnostic was measuring its own label"
    elif max(R1 or 0.0, R2 or 0.0) >= PARTIAL_R:
        verdict, why = "PARTIAL", "some of D3 is label error; a material remainder survives"
    else:
        verdict, why = "SURVIVES", "D3 is not a censoring artifact of the realized bucket"

    # ---- 4.2 the tripwire --------------------------------------------------
    trip = tripwire_study(pooled_a, pooled_c_rows, arm_a, arm_c, ship)

    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "lane": "C1 (master plan 2026-08-07b)",
        "gate_doc": GATE_DOC,
        "what": ("how much of the D3 served-distribution miscalibration is the reliability "
                 "diagnostic grading the model against its own censored label (D4)"),
        "recalibrated_anything": False,
        "chain": {"years": list(rel.CHAIN_YEARS), "min_train": rel.MIN_TRAIN,
                  "min_test": rel.MIN_TEST, "min_tier_n": rel.MIN_TIER_N,
                  "bucket_edges_annual": list(rel.BUCKET_EDGES),
                  "target_seasons_divisor": rel.TARGET_SEASONS,
                  "resolved_through": ds.RESOLVED_THROUGH,
                  "predictions_held_fixed_in_arms_abc": True},
        "self_added_thresholds": {
            "confirm_R": CONFIRM_R, "partial_R": PARTIAL_R,
            "ctrl1_share_bar": CTRL1_SHARE_BAR, "tripwire_fpr_bar": FPR_BAR,
            "note": ("the master plan says 'shrinks materially' without a number; these "
                     "bars are added by this gate and were fixed before the run")},
        "season_share_profile": prof,
        "correction_factors_by_n_obs": {s: prof[s]["factor_by_n_obs"] for s in SIDES},
        "pool_composition": {"per_tier_censored_share": m5,
                             "n_censored_in_eval_pool": n_cens_eval},
        "arms": {"a_shipped": arm_a, "b_resolved_only": arm_b, "c_corrected": arm_c},
        "primary": {"R1_bust_ece_reduction": R1, "R2_tier_gap_reduction": R2,
                    "bust_ece": {"a": arm_a["bust_ece"], "c": arm_c["bust_ece"]},
                    "tier_gap_weighted": {"a": arm_a["tier_gap_weighted"],
                                          "c": arm_c["tier_gap_weighted"]}},
        "controls": {"ctrl0_noop_on_resolved": ctrl0, "ctrl1_zero_information_constant": ctrl1,
                     "ctrl2_permuted_factors": ctrl2, "ctrl3_wrong_direction": ctrl3,
                     "ctrl4_composition_decomposition": ctrl4, "ctrl5_ceiling": ctrl5,
                     "ctrl6_oracle_upper_bound": ctrl6,
                     "ctrl7_required_label_error": ctrl7},
        "sensitivities": {"sens1_cohort_profile_drift": sens1, "sens2_refit_arm_d": sens2},
        "stop_conditions": stop,
        "tripwire_study": trip,
        "verdict": verdict,
        "verdict_reason": why,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print(f"lane C1 -> {OUT_PATH.name}")
    print(f"  pool n={arm_a['n']}  censored in pool={n_cens_eval}  "
          f"bucket flips under correction={n_bucket_changed} ({ctrl5['pct_of_pool']}%)")
    print(f"  (a) bust ECE {arm_a['bust_ece']:.5f}  tier gap(w) {arm_a['tier_gap_weighted']:.5f}")
    print(f"  (b) bust ECE {arm_b['bust_ece']:.5f}  tier gap(w) {arm_b['tier_gap_weighted']:.5f}"
          f"   [CONFOUNDED: different pool]")
    print(f"  (c) bust ECE {arm_c['bust_ece']:.5f}  tier gap(w) {arm_c['tier_gap_weighted']:.5f}")
    print(f"  R1={R1}  R2={R2}   CTRL1 share_of_R1={ctrl1['share_of_R1']}  "
          f"CTRL2 perm p(R1)={ctrl2['perm_p_R1']}")
    print(f"  CTRL3 deflate pass={ctrl3['pass']}   stop tripped={stop['any_tripped']}")
    print(f"  VERDICT: {verdict} - {why}")


def tripwire_study(rows_a, rows_c, arm_a, arm_c, ship) -> dict:
    """4.2. Can pooled bust ECE express the D3 tier-monotone defect, and what bar
    fires on it with a held-out false-positive rate under FPR_BAR?"""
    # candidate statistics on the shipped arm
    def stats(rows):
        m = metrics(rows)
        tiers = m["per_tier"]
        max_gap = max((tiers[t]["gap"] for t in tiers), default=0.0)
        low = [t for t in tiers if int(t) <= 45]
        signed_low = [tiers[t]["realized_freq"]["bust"] - tiers[t]["mean_p"]["bust"] for t in low]
        return {"bust_ece": m["bust_ece"], "max_tier_gap": round(float(max_gap), 5),
                "tier_gap_weighted": m["tier_gap_weighted"],
                "mean_signed_bust_residual_tier_le_45": round(float(np.mean(signed_low)), 5)
                if signed_low else None,
                "n_tiers": len(tiers)}

    s_a, s_c = stats(rows_a), stats(rows_c)

    # leave-one-chain-year-out folds on the SHIPPED arm: the system's current state
    folds = {}
    for yr in rel.CHAIN_YEARS:
        sub = [r for r in rows_a if r["decision_year"] == yr]
        if len(sub) < 100:
            continue
        cur = rel._reliability_bins(sub, key="p_after")
        bef = rel._reliability_bins(sub, key="p_before")
        tiers = rel._tier_reliability(sub, key="p_after")
        folds[str(yr)] = {"n": len(sub), "bust_ece_after": cur["bust"]["ece"],
                          "bust_ece_before": bef["bust"]["ece"],
                          "max_tier_gap": round(float(max((tiers[t]["gap"] for t in tiers),
                                                          default=0.0)), 5)}
    fv = [v["bust_ece_after"] for v in folds.values()]
    fb = [v["bust_ece_before"] for v in folds.values()]
    fm = [v["max_tier_gap"] for v in folds.values()]

    def fpr(vals, bar):
        return round(float(np.mean([1.0 if v > bar else 0.0 for v in vals])), 4)

    cands = {}
    for bar in (0.06, 0.07, 0.075, 0.08, 0.09, 0.10, 0.11, 0.12):
        cands[f"{bar:.3f}"] = {
            "fires_on_pooled_shipped": bool(arm_a["bust_ece"] > bar),
            "held_out_fold_fpr": fpr(fv, bar),
            "fires_if_platt_dropped_pooled": bool(
                float(ship["tripwire"]["bust_ece_before_recalibration"]) > bar),
            "held_out_fold_detection_if_platt_dropped": fpr(fb, bar),
        }
    # Block bootstrap over chain-year folds: the sampling distribution of the POOLED
    # statistic in the system's current state. The tripwire judges the POOLED value, so
    # this, not the per-fold value, is its nuisance-alarm rate. ADDED AFTER the primary
    # run as a strictly better estimator than the pre-registered per-fold count; it does
    # not touch the primary verdict, which is decided in section 4.1.
    yrs = [y for y in rel.CHAIN_YEARS if str(y) in folds]
    by_yr = defaultdict(list)
    for r in rows_a:
        by_yr[r["decision_year"]].append(r)
    rng = np.random.default_rng(PERM_SEED)
    boot_after, boot_before = [], []
    for _ in range(1000):
        pick = rng.choice(len(yrs), size=len(yrs), replace=True)
        samp = [r for i in pick for r in by_yr[yrs[i]]]
        boot_after.append(rel._reliability_bins(samp, key="p_after")["bust"]["ece"])
        boot_before.append(rel._reliability_bins(samp, key="p_before")["bust"]["ece"])
    boot_after, boot_before = np.array(boot_after), np.array(boot_before)

    # Defect injection: can a POOLED bar express a defect LOCATED at the top of the board?
    # Flip a fraction of non-bust realized outcomes to bust among tier >= 50 rows (the
    # realistic worsening: over-priced good/star mass at the top), and among tier <= 45
    # rows for contrast. Report the pooled bust ECE each produces.
    def inject(rows, tier_lo, tier_hi, frac):
        idx = [i for i, r in enumerate(rows)
               if tier_lo <= rel._tier(r["fv"]) <= tier_hi and r["y"] != 0]
        k = int(round(frac * len(idx)))
        flip = set(idx[:k])
        new = [dict(r, y=0) if i in flip else r for i, r in enumerate(rows)]
        tiers = rel._tier_reliability(new, key="p_after")
        sel = [t for t in tiers if tier_lo <= int(t) <= tier_hi]
        resid = float(np.mean([tiers[t]["realized_freq"]["bust"] - tiers[t]["mean_p"]["bust"]
                               for t in sel])) if sel else None
        return {"frac_flipped": frac, "n_eligible": len(idx), "n_flipped": k,
                "pooled_bust_ece": rel._reliability_bins(new, key="p_after")["bust"]["ece"],
                "mean_signed_bust_residual_in_band": round(resid, 5) if resid is not None else None}

    inj_top = [inject(rows_a, 50, 100, f) for f in (0.0, 0.25, 0.5, 0.75, 1.0)]
    inj_low = [inject(rows_a, 0, 45, f) for f in (0.0, 0.05, 0.10, 0.25)]

    return {
        "question": ("BUST_ECE_TRIPWIRE watches POOLED bust ECE. D3 is a defect that is "
                     "monotone IN TIER. These are not the same statistic."),
        "shipped_threshold": rel.BUST_ECE_TRIPWIRE,
        "pooled_stats": {"arm_a": s_a, "arm_c": s_c},
        "block_bootstrap_pooled": {
            "B": 1000, "seed": PERM_SEED, "resampled": "chain-year folds, with replacement",
            "after": {"mean": round(float(boot_after.mean()), 5),
                      "p05": round(float(np.percentile(boot_after, 5)), 5),
                      "p95": round(float(np.percentile(boot_after, 95)), 5)},
            "before": {"mean": round(float(boot_before.mean()), 5),
                       "p05": round(float(np.percentile(boot_before, 5)), 5),
                       "p95": round(float(np.percentile(boot_before, 95)), 5)},
            "fpr_by_bar": {f"{b:.3f}": round(float((boot_after > b).mean()), 4)
                           for b in (0.06, 0.07, 0.075, 0.08, 0.09, 0.10, 0.11, 0.12)},
            "detection_if_platt_dropped_by_bar": {
                f"{b:.3f}": round(float((boot_before > b).mean()), 4)
                for b in (0.06, 0.07, 0.075, 0.08, 0.09, 0.10, 0.11, 0.12)},
            "note": ("ADDED after the primary run. Estimates the nuisance-alarm rate of a "
                     "POOLED bar, which is what the shipped tripwire actually judges. Does "
                     "not enter the section 4.1 verdict."),
        },
        "defect_injection": {
            "what": ("flip realized non-bust outcomes to bust inside a tier band, which is "
                     "the realistic worsening (over-priced good/star mass), and watch the "
                     "POOLED bust ECE the tripwire reads"),
            "top_of_board_tier_ge_50": inj_top,
            "low_tiers_le_45": inj_low,
            "note": ("ADDED after the primary run, for gate 4.2 question 1 only. Does not "
                     "enter the section 4.1 verdict."),
        },
        "held_out_folds": folds,
        "fold_summary": {
            "bust_ece_after": {"min": round(float(min(fv)), 5), "median": round(float(np.median(fv)), 5),
                               "max": round(float(max(fv)), 5),
                               "sd": round(float(np.std(fv, ddof=1)), 5) if len(fv) > 1 else None},
            "bust_ece_before": {"min": round(float(min(fb)), 5), "max": round(float(max(fb)), 5)},
            "max_tier_gap": {"min": round(float(min(fm)), 5), "max": round(float(max(fm)), 5)},
        },
        "candidate_bars": cands,
        "fpr_bar": FPR_BAR,
    }


if __name__ == "__main__":
    main()
