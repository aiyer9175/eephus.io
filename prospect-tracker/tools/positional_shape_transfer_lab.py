# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""Lane K6 gate harness: does the SHAPE of a glove predict how it transfers?

Pre-registration: docs/gate-2026-08-07-positional-shape-transfer.md, written and
committed to disk BEFORE this file existed. Read it first. Nothing in here is
allowed to change the shipped model; this script imports positional_fit and
writes exactly one artifact, data/positional_shape_transfer_lab.json.

CHAMPION      pred(b) = D_t[b] + s_b * Zhat                (shipped, unchanged)
CHALLENGER S  pred(b) = D_t[b] + s_b * Zhat + g_b * Uhat   (strictly nested)

Uhat is the shrunk, level-residualised lateral-minus-depth contrast built from
the Savant directional splits that positional_fit has never opened. g_b is a
per-destination coefficient fitted on same-position year-over-year pairs in the
training window only. With every g_b at zero the two arms are bit-identical.

Run:  python tools/positional_shape_transfer_lab.py
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import positional_fit as pf  # noqa: E402

OUT = ROOT / "data" / "positional_shape_transfer_lab.json"

# Everything below is pinned by the pre-registration. No value here was chosen
# after seeing an outcome number.
CONV_FIRST = 2017
CONV_MIN_INN = 200.0          # conversion_accuracy's own floor, both sides
PRIOR_INN_CAP = 50.0          # conversion_accuracy's own destination-experience cap
SHAPE_CORPUS_MIN_INN = pf.MIN_PAIR_INN     # 100, the model's general read floor
YOY_MIN_INN = pf.MIN_RELIABILITY_INN       # 300, fit_signal's own floor
MIN_YOY_PAIRS_FOR_K = 30      # fit_signal's own fallback trigger
MIN_YOY_PAIRS_FOR_G = 60      # pre-registered: below this, g_p = 0
K_U_FALLBACK = 1200.0         # fit_signal's own fallback constant
BOOT = 2000
PERM = 300
SEED = 61                     # conversion_accuracy's own seed

CHAMPION_MAE_ON_DISK = 5.682  # reproduction tripwire
CHAMPION_N_ON_DISK = 169
CHAMPION_AUC_ON_DISK = 0.4809


# ---------------------------------------------------------------- components
def load_components(feeds: pf.Feeds) -> dict:
    """(mlbam, season) -> {POS: u_raw}, lateral minus depth per 1000 innings.

    Same join as Feeds.rates: Savant row x StatsAPI innings. A read with no
    innings is dropped by rates() too, so the two dicts have identical keys.
    """
    out: dict = defaultdict(dict)
    seasons = feeds.inn.get("seasons", {})
    for mid, byyr in feeds.oaa.get("by_mlbam", {}).items():
        for y, byp in byyr.items():
            inns = seasons.get(y, {}).get(mid, {})
            for p, rec in byp.items():
                if p.startswith("_"):
                    continue
                inn = float((inns.get(p) or {}).get("inn", 0.0))
                if inn <= 0:
                    continue
                lat = rec.get("l3", 0.0) + rec.get("l1", 0.0)
                dep = rec.get("in", 0.0) + rec.get("bk", 0.0)
                out[(int(mid), int(y))][p] = (lat - dep) * 1000.0 / inn
    return dict(out)


def _ols(x, y):
    """(slope, intercept) with an intercept, or (0.0, 0.0) if degenerate."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 2 or float(np.var(x)) <= 1e-12:
        return 0.0, 0.0
    b = float(np.cov(x, y, bias=True)[0, 1] / np.var(x))
    return b, float(np.mean(y) - b * np.mean(x))


def fit_shape(obs_all, comps, Dt, sig, upto: int) -> dict:
    """Every shape parameter, fitted on seasons <= `upto` ONLY.

    Order matters and is fixed by the pre-registration:
    mu/sd -> u_std -> (a_p, rho_p) -> u_res -> k_u_p -> Uhat -> g_p.
    """
    # ---- 1. within-position standardisation of the raw contrast
    pool = defaultdict(list)
    for (mid, y), byp in comps.items():
        if y > upto:
            continue
        for p, u in byp.items():
            rec = obs_all.get((mid, y), {}).get(p)
            if rec and rec["inn"] >= SHAPE_CORPUS_MIN_INN:
                pool[p].append(u)
    mu, sd = {}, {}
    for p in pf.OAA_POSITIONS:
        v = pool.get(p, [])
        mu[p] = statistics.mean(v) if v else 0.0
        s = statistics.pstdev(v) if len(v) > 1 else 0.0
        sd[p] = s if s > 1e-9 else 1.0

    def u_std(mid, y, p):
        u = comps.get((mid, y), {}).get(p)
        return None if u is None else (u - mu[p]) / sd[p]

    def z_read(rec, p):
        s = sig[p]["signal_sd"]
        return None if s <= 0 else (rec["rate"] - Dt[p]) / s

    # ---- 2. residualise the shape against the champion's own per-read level
    xs, ys = defaultdict(list), defaultdict(list)
    for (mid, y), byp in obs_all.items():
        if y > upto:
            continue
        for p, rec in byp.items():
            if rec["inn"] < SHAPE_CORPUS_MIN_INN:
                continue
            us, zr = u_std(mid, y, p), z_read(rec, p)
            if us is None or zr is None:
                continue
            xs[p].append(zr)
            ys[p].append(us)
    rho, a = {}, {}
    for p in pf.OAA_POSITIONS:
        rho[p], a[p] = _ols(xs.get(p, []), ys.get(p, []))

    def u_res(mid, y, p, rec):
        us, zr = u_std(mid, y, p), z_read(rec, p)
        if us is None or zr is None:
            return None
        return us - (a[p] + rho[p] * zr)

    # ---- 3. reliability of the shape score, by the fit_signal construction
    k_u, rel_meta = {}, {}
    for p in pf.OAA_POSITIONS:
        px, py, hm = [], [], []
        for (mid, y), byp in obs_all.items():
            if y + 1 > upto or p not in byp or byp[p]["inn"] < YOY_MIN_INN:
                continue
            nxt = obs_all.get((mid, y + 1))
            if not nxt or p not in nxt or nxt[p]["inn"] < YOY_MIN_INN:
                continue
            u1 = u_res(mid, y, p, byp[p])
            u2 = u_res(mid, y + 1, p, nxt[p])
            if u1 is None or u2 is None:
                continue
            px.append(u1)
            py.append(u2)
            hm.append(2.0 / (1.0 / byp[p]["inn"] + 1.0 / nxt[p]["inn"]))
        if len(px) < MIN_YOY_PAIRS_FOR_K:
            k_u[p] = K_U_FALLBACK
            rel_meta[p] = {"n_pairs": len(px), "yoy_r": None, "k_inn": K_U_FALLBACK,
                           "fallback": True}
            continue
        r = float(np.corrcoef(px, py)[0, 1])
        r = min(max(r, 0.05), 0.95)
        hmm = statistics.mean(hm)
        k_u[p] = hmm * (1 - r) / r
        rel_meta[p] = {"n_pairs": len(px), "yoy_r": round(r, 4),
                       "hm_inn": round(hmm, 0), "k_inn": round(k_u[p], 0),
                       "fallback": False}

    def shrunk_u(reads, mid, y):
        """Posterior mean of the latent shape, prior N(0,1). Mirrors _shrunk_z."""
        num = den = 0.0
        for p, rec in reads.items():
            ur = u_res(mid, y, p, rec)
            if ur is None or k_u[p] <= 0:
                continue
            prec = rec["inn"] / k_u[p]
            num += prec * ur
            den += prec
        return num / (1.0 + den)

    # ---- 4. the per-position shape coefficient, on same-position yoy pairs
    g, g_meta = {}, {}
    for p in pf.OAA_POSITIONS:
        gx, gy = [], []
        for (mid, y), byp in obs_all.items():
            if y + 1 > upto or p not in byp or byp[p]["inn"] < YOY_MIN_INN:
                continue
            nxt = obs_all.get((mid, y + 1))
            if not nxt or p not in nxt or nxt[p]["inn"] < YOY_MIN_INN:
                continue
            src = {q: v for q, v in byp.items() if v["inn"] >= CONV_MIN_INN}
            if p not in src:
                continue
            zh, _ = pf._shrunk_z(src, Dt, sig)
            uh = shrunk_u(src, mid, y)
            gx.append(uh)
            gy.append(nxt[p]["rate"] - (Dt[p] + sig[p]["signal_sd"] * zh))
        if len(gx) < MIN_YOY_PAIRS_FOR_G:
            g[p] = 0.0
            g_meta[p] = {"n_pairs": len(gx), "g": 0.0, "fallback": True}
            continue
        slope, _intercept = _ols(gx, gy)   # intercept fitted then DISCARDED
        g[p] = slope
        g_meta[p] = {"n_pairs": len(gx), "g": round(slope, 4), "fallback": False,
                     "u_sd_in_fit": round(float(np.std(gx)), 4)}

    return {"mu": mu, "sd": sd, "rho": rho, "a": a, "k_u": k_u, "g": g,
            "shrunk_u": shrunk_u, "reliability": rel_meta, "g_meta": g_meta}


# ------------------------------------------------------- the conversion gate
def build_rows(feeds, obs_all, comps, sig):
    """conversion_accuracy's row selection, verbatim, plus the challenger arm."""
    last = feeds.inn.get("last_season") - 1
    rows, per_season_shape = [], {}
    for t in range(CONV_FIRST, last + 1):
        train = {k: v for k, v in obs_all.items() if k[1] <= t}
        multi = {k: d for k, d in train.items() if len(d) >= 2}
        if len(multi) < 100:
            continue
        beta = pf._solve_D(pf._pairs_from(multi))
        Dt = {p: float(beta[pf.IDX[p]]) for p in pf.OAA_POSITIONS}
        sh = fit_shape(obs_all, comps, Dt, sig, upto=t)
        per_season_shape[t] = {
            "g": {p: round(sh["g"][p], 4) for p in pf.OAA_POSITIONS},
            "k_u": {p: round(sh["k_u"][p], 0) for p in pf.OAA_POSITIONS},
            "shape_yoy_r": {p: sh["reliability"][p]["yoy_r"]
                            for p in pf.OAA_POSITIONS},
            "g_pairs": {p: sh["g_meta"][p]["n_pairs"] for p in pf.OAA_POSITIONS},
        }
        for (mid, s), row in obs_all.items():
            if s != t:
                continue
            nxt = obs_all.get((mid, t + 1))
            if not nxt:
                continue
            src = {p: v for p, v in row.items() if v["inn"] >= CONV_MIN_INN}
            if not src:
                continue
            for b, nv in nxt.items():
                if nv["inn"] < CONV_MIN_INN or b in src:
                    continue
                prior = sum(obs_all.get((mid, y), {}).get(b, {}).get("inn", 0.0)
                            for y in range(t - 2, t + 1))
                if prior > PRIOR_INN_CAP:
                    continue
                a = max(src, key=lambda p: src[p]["inn"])
                z, _ = pf._shrunk_z(src, Dt, sig)
                u = sh["shrunk_u"](src, mid, t)
                champ = Dt[b] + sig[b]["signal_sd"] * z
                rows.append({
                    "mlbam": mid, "season": t, "from": a, "to": b,
                    "actual": nv["rate"], "z": z, "u": u, "g_to": sh["g"][b],
                    "champion": champ,
                    "challenger": champ + sh["g"][b] * u,
                    "carry_over": src[a]["rate"]})
    return rows, per_season_shape


def mae(rs, key):
    return statistics.mean(abs(r[key] - r["actual"]) for r in rs)


# -------------------------------------------------- the demotion-AUC clause
def demotion_auc(feeds, obs_all, comps, sig, ladder, feas):
    """backtest's AUC, scored for both arms on identical rows."""
    last = feeds.inn.get("last_season") - 1
    inn650 = ladder["inn_per_pa"] * 650.0
    lad = ladder["values"]
    recs = []
    for t in range(2017, last + 1):
        train = {k: v for k, v in obs_all.items() if k[1] <= t}
        multi = {k: d for k, d in train.items() if len(d) >= 2}
        if len(multi) < 100:
            continue
        beta = pf._solve_D(pf._pairs_from(multi))
        Dt = {p: float(beta[pf.IDX[p]]) for p in pf.OAA_POSITIONS}
        sh = fit_shape(obs_all, comps, Dt, sig, upto=t)

        def gain(row, cur, mid, use_shape):
            z, _ = pf._shrunk_z(row, Dt, sig)
            u = sh["shrunk_u"](row, mid, t) if use_shape else 0.0
            cand = set(feas["allowed"].get(cur, ["DH"])) | {
                p for p, v in row.items() if v["inn"] >= 100} | {"DH", cur}
            vals = {}
            for p in cand:
                if p == "DH":
                    vals["DH"] = lad["DH"]
                elif p in pf.OAA_POSITIONS:
                    r = Dt[p] + sig[p]["signal_sd"] * z + sh["g"][p] * u
                    vals[p] = r * inn650 / 1000.0 + lad[p]
            here = vals.get(cur, max(vals.values()))
            downs = {p: v for p, v in vals.items() if lad[p] < lad[cur] - 0.5}
            if not downs:
                return -99.0
            return max(downs.values()) - here

        rows_t = []
        for (mid, s), row in obs_all.items():
            if s != t:
                continue
            cur = feeds.primary_position(mid, t)
            if cur not in pf.OAA_POSITIONS:
                continue
            if sum(v["inn"] for v in row.values()) < 400.0:
                continue
            nxt = feeds.primary_position(mid, t + 1)
            if nxt is None:
                continue
            if sum(v["inn"] for p, v in feeds.innings(mid, t + 1).items()
                   if p != "P") < 200.0:
                continue
            rows_t.append((mid, cur, nxt, row))
        if len(rows_t) < 30:
            continue
        for mid, cur, nxt, row in rows_t:
            recs.append({"moved_down": bool(lad[nxt] < lad[cur] - 0.5),
                         "champion": gain(row, cur, mid, False),
                         "challenger": gain(row, cur, mid, True)})
    labels = [r["moved_down"] for r in recs]
    return {"n_scored": len(recs), "n_moved_down": sum(labels),
            "auc_champion": round(pf._auc([r["champion"] for r in recs], labels), 4),
            "auc_challenger": round(pf._auc([r["challenger"] for r in recs], labels), 4)}


# ------------------------------------------------------------------- driver
def main():
    rng = random.Random(SEED)
    feeds = pf.Feeds()
    obs_all = feeds.rates()
    obs = {k: {p: v for p, v in d.items() if v["inn"] >= pf.MIN_PAIR_INN}
           for k, d in obs_all.items()}
    obs = {k: d for k, d in obs.items() if d}
    sig = pf.fit_signal(obs)
    comps = load_components(feeds)

    rows, per_season_shape = build_rows(feeds, obs_all, comps, sig)

    # ---- reproduction tripwire. If the champion does not land on the artifact,
    # this harness is not scoring the shipped model and nothing below is valid.
    n = len(rows)
    champ_mae = mae(rows, "champion")
    if n != CHAMPION_N_ON_DISK or abs(round(champ_mae, 3) - CHAMPION_MAE_ON_DISK) > 1e-9:
        raise SystemExit(f"REPRODUCTION FAILED: n={n} (want {CHAMPION_N_ON_DISK}), "
                         f"champion MAE={champ_mae:.4f} (want {CHAMPION_MAE_ON_DISK}). "
                         f"STOP and report; do not interpret the gate.")

    chal_mae = mae(rows, "challenger")
    dmae = champ_mae - chal_mae

    # ---- clause 1: cluster bootstrap over PLAYERS
    by_player = defaultdict(list)
    for r in rows:
        by_player[r["mlbam"]].append(r)
    players = list(by_player)
    draws = []
    for _ in range(BOOT):
        pick = []
        for _ in range(len(players)):
            pick.extend(by_player[players[rng.randrange(len(players))]])
        draws.append(mae(pick, "champion") - mae(pick, "challenger"))
    ci = [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))]
    clause1 = bool(ci[0] > 0.0)

    # ---- clause 2: sign consistency across the scored seasons
    by_season = {}
    for t in sorted({r["season"] for r in rows}):
        sub = [r for r in rows if r["season"] == t]
        if len(sub) < 10:
            continue
        by_season[t] = {"n": len(sub),
                        "mae_champion": round(mae(sub, "champion"), 3),
                        "mae_challenger": round(mae(sub, "challenger"), 3),
                        "dmae": round(mae(sub, "champion") - mae(sub, "challenger"), 4)}
    wins = sum(1 for v in by_season.values() if v["dmae"] > 0)
    clause2 = bool(wins >= 6 and len(by_season) == 8)

    # ---- clause 3: shape-permuted zero-information control
    nulls = []
    for _ in range(PERM):
        pool = []
        for t in sorted({r["season"] for r in rows}):
            sub = [r for r in rows if r["season"] == t]
            us = [r["u"] for r in sub]
            rng.shuffle(us)
            for r, uu in zip(sub, us):
                pool.append({"actual": r["actual"], "champion": r["champion"],
                             "challenger": r["champion"] + r["g_to"] * uu})
        nulls.append(mae(pool, "champion") - mae(pool, "challenger"))
    null95 = float(np.percentile(nulls, 95))
    clause3 = bool(dmae > null95)

    # ---- clause 4: no collateral damage on the demotion side
    ladder = pf.fit_ladder(feeds, boot=30)
    feas = pf.fit_feasibility(feeds, ladder)
    auc = demotion_auc(feeds, obs_all, comps, sig, ladder, feas)
    clause4 = bool(auc["auc_challenger"] >= auc["auc_champion"] - 0.01)

    ship = bool(clause1 and clause2 and clause3 and clause4)

    payload = {
        "model": "positional_fit conversion transfer, shape-augmented",
        "lane": "K6",
        "generated_at": "2026-08-07",
        "preregistration": "docs/gate-2026-08-07-positional-shape-transfer.md",
        "verdict": "ship" if ship else "deprecated",
        "one_line": ("Savant directional splits do not improve the transfer "
                     "prediction." if not ship else
                     "Shape improves the transfer prediction."),
        "population": {
            "n_conversions": n,
            "n_distinct_players": len(players),
            "seasons_scored": sorted(by_season),
            "component_coverage": "100 percent; every source read has in/bk/l3/l1",
            "destinations": {b: sum(1 for r in rows if r["to"] == b)
                             for b in sorted({r["to"] for r in rows})},
        },
        "primary": {
            "statistic": "dMAE = MAE(champion) - MAE(challenger), runs per 1000 inn",
            "mae_champion": round(champ_mae, 4),
            "mae_challenger": round(chal_mae, 4),
            "mae_carry_over_reference": round(mae(rows, "carry_over"), 4),
            "dmae": round(dmae, 4),
            "cluster_bootstrap_ci95": [round(ci[0], 4), round(ci[1], 4)],
            "bootstrap_draws": BOOT,
            "clustered_by": "player",
        },
        "clauses": {
            "1_ci_excludes_zero_above": clause1,
            "2_sign_consistency_6_of_8": {"passed": clause2, "wins": wins,
                                          "of": len(by_season)},
            "3_beats_shape_permuted_control": {
                "passed": clause3, "dmae": round(dmae, 4),
                "control_null95": round(null95, 4),
                "control_mean": round(float(np.mean(nulls)), 4),
                "permutations": PERM},
            "4_no_demotion_auc_damage": {"passed": clause4, **auc,
                                         "auc_on_disk": CHAMPION_AUC_ON_DISK},
        },
        "by_season": by_season,
        "by_destination": {
            b: {"n": sum(1 for r in rows if r["to"] == b),
                "mae_champion": round(mae([r for r in rows if r["to"] == b],
                                          "champion"), 3),
                "mae_challenger": round(mae([r for r in rows if r["to"] == b],
                                            "challenger"), 3)}
            for b in sorted({r["to"] for r in rows})
            if sum(1 for r in rows if r["to"] == b) >= 8},
        "fitted_shape_by_training_cutoff": per_season_shape,
        "shape_score_spread": {
            "sd_of_shrunk_u_on_scored_rows": round(
                float(np.std([r["u"] for r in rows])), 4),
            "p05_p95": [round(float(np.percentile([r["u"] for r in rows], 5)), 4),
                        round(float(np.percentile([r["u"] for r in rows], 95)), 4)],
            "max_abs_prediction_shift_runs_per_1000_inn": round(
                max(abs(r["challenger"] - r["champion"]) for r in rows), 4),
            "median_abs_prediction_shift": round(statistics.median(
                abs(r["challenger"] - r["champion"]) for r in rows), 4),
        },
        "standing_finding_not_addressed": {
            "note": ("Raw OAA out-discriminates the shipped demotion score. "
                     "This gate does not target that and does not fix it."),
            "auc_raw_oaa": 0.6184,
            "auc_model": CHAMPION_AUC_ON_DISK,
            "auc_zero_information_control": 0.48,
        },
        "not_tested": ["platoon split rhh/lhh",
                       "4-way canonicalised directional decomposition",
                       "sr_act vs sr_exp as an opportunity control"],
    }
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in
                      ("verdict", "population", "primary", "clauses")}, indent=1))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
