# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Lane B2 (master plan 2026-08-07b): ONE replacement for the eFV label's censored-tail
projection, scored on held-out truncation error, and gated.

Pre-registration: docs/efv-2026-08-07b/LABEL_REPLACEMENT_GATE.md, written IN FULL before
this file existed. Only part 8 of that doc is filled in afterwards.

CANDIDATE. A per-season-index share profile, FORWARD CHAINED so a cohort is never scored
with a profile that saw it:

    m_k  = mean bWAR in season index k over rows from STRICTLY PRIOR debut cohorts
    S_n  = sum_{k<=n} m_k / sum_j m_j
    candidate_target(n) = obs_sum / S_n

The shipped projection is the special case S_n = n / 6.

CONTROLS (all mandatory, all reported whatever they say):
  4.1 rank-identical LEVEL TWIN     shipped + forward-chained constant
  4.2 NULL-A permuted share profile (720 deterministic permutations, no RNG)
      NULL-B zero-information projection (values permuted across rows)
  4.3 sign-flip permutation p-value on the paired per-row squared-error difference
  4.4 the embarrassing one: a plain one-parameter least-squares scalar fit, no season
      structure at all. If it matches the candidate, the profile contributes nothing.

Writes exactly one artifact: data/xfv_label_replacement_eval.json.
Fits no model, rebuilds nothing, writes nothing to prospects.db, edits no shipped code.

Run: python tools/efv_label_replacement_lab.py
"""

from __future__ import annotations

import itertools
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import efv_dataset as ds            # noqa: E402  READ ONLY
import efv_model as em              # noqa: E402  READ ONLY
import efv_reliability as rel       # noqa: E402
import storage                      # noqa: E402

DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "xfv_label_replacement_eval.json"

SPANS = (2, 3, 4, 5)
SIDES = ("hit", "pit")

# Pre-registered in the gate doc, part 3.2. Chosen from ROW COUNTS ONLY, before any
# error or bias number existed.
MIN_PRIOR_POOLED = 100
MIN_PRIOR_PER_SIDE = 60

# Pre-registered, part 2 and part 4. Seed inherited from B1, fixed before the run.
SEED = 20260807
B_COND = 5000
B_REFIT = 2000
N_NULL_B = 1000
N_SIGNFLIP = 10000

PRIMARY_CELL = ("n2_hit", 2, "hit")

# B1's recorded pool, asserted here rather than trusted.
B1_POOL = {"n": 988, "hit": 460, "pit": 528}


# ---------------------------------------------------------------------------
# part 5: pins asserted, not assumed
# ---------------------------------------------------------------------------

def pin_check() -> dict:
    got = dict(em._BLEND_LAMBDA_RESELECT)
    want = {"hit": 0.70, "pit": 0.57}
    ok = (got.get("hit") == want["hit"] and got.get("pit") == want["pit"])
    # find the line the pin actually lives on now (B1 cited :581; edits move it)
    line = None
    src = (ROOT / "efv_model.py").read_text(encoding="utf-8").splitlines()
    for i, ln in enumerate(src, 1):
        if ln.startswith("_BLEND_LAMBDA_RESELECT"):
            line = i
            break
    return {
        "source": "efv_model._BLEND_LAMBDA_RESELECT",
        "line_found": line,
        "line_cited_by_b1": 581,
        "line_matches_b1_citation": bool(line == 581),
        "read": got,
        "expected": want,
        "pin_ok": bool(ok),
        "note": ("lambda pinned; a synthetic label beside an unpinned lambda would silently "
                 "move the served blend. This lab changes no lambda and fits nothing."
                 if ok else "PIN VIOLATED: served lambda is not what the plan asserts"),
    }


# ---------------------------------------------------------------------------
# part 3.1: the rows. Same construction as B1, re-derived and reconciled.
# ---------------------------------------------------------------------------

def _career_war() -> dict[str, dict[int, float]]:
    cw = {}
    with storage.connect() as con:
        for r in con.execute("SELECT player_key, payload_json FROM career_war"):
            try:
                seasons = (json.loads(r["payload_json"]) or {}).get("seasons") or {}
            except ValueError:
                continue
            cw[r["player_key"]] = {int(y): float(w) for y, w in seasons.items()}
    return cw


def load_pool():
    """Resolved debuted rows (the scoring pool) and censored debuted rows (the shipped
    rows that ride the projection, used for the label-space diagnostic only)."""
    cw = _career_war()
    resolved, censored, terminal, meta = [], [], [], {}
    for side, fname in (("hit", "xfv_hitter_matrix.json"), ("pit", "xfv_pitcher_matrix.json")):
        p = DATA_DIR / fname
        mrows = json.loads(p.read_text(encoding="utf-8"))
        meta[fname] = {
            "mtime_utc": datetime.fromtimestamp(p.stat().st_mtime, UTC).isoformat(timespec="seconds"),
            "n_rows": len(mrows),
            "n_debuted": sum(1 for r in mrows if r.get("kind") == "debuted"),
            "n_censored_shipped": sum(1 for r in mrows if r.get("censored")),
        }
        for r in mrows:
            if r.get("kind") != "debuted":
                continue
            dy = r.get("debut_year")
            if dy is None:
                continue
            seasons = cw.get(r["player_key"])
            if not seasons:
                continue
            rec = {"player_key": r["player_key"], "side": side, "debut_year": int(dy),
                   "seasons": seasons, "shipped_target_resolved": r.get("target_resolved"),
                   "shipped_censored": bool(r.get("censored"))}
            if int(dy) + ds.TARGET_SEASONS - 1 <= ds.RESOLVED_THROUGH:
                resolved.append(rec)
            elif rec["shipped_censored"]:
                censored.append(rec)
            else:
                # window arithmetic says censored but the shipped matrix says resolved:
                # efv_dataset's career-TERMINAL transaction rule closed the window early
                # (retirement / lifetime ban). These rows do NOT ride the projection.
                terminal.append(rec)
    return resolved, censored, terminal, meta


def replay(rows: list[dict]) -> tuple[dict, dict]:
    """Truncation replay through the SHIPPED _label_6yr. No reimplementation."""
    real_through = ds.RESOLVED_THROUGH
    recon = {"checked": 0, "match": 0, "mismatch": 0, "mismatch_examples": []}
    true, obs, ship, dy, side, keys, wmat = [], {n: [] for n in SPANS}, {n: [] for n in SPANS}, [], [], [], []
    try:
        for r in rows:
            y0 = r["debut_year"]
            ds.RESOLVED_THROUGH = real_through
            _tr, tc, cf, _w, nb = ds._label_6yr(r["seasons"], y0)
            assert not cf and nb == ds.TARGET_SEASONS, (r["player_key"], nb, cf)
            recon["checked"] += 1
            shp = r["shipped_target_resolved"]
            if shp is not None and abs(float(shp) - tc) < 1e-6:
                recon["match"] += 1
            else:
                recon["mismatch"] += 1
                if len(recon["mismatch_examples"]) < 10:
                    recon["mismatch_examples"].append(
                        {"player_key": r["player_key"], "shipped": shp, "recomputed": tc})
            true.append(tc)
            dy.append(y0)
            side.append(r["side"])
            keys.append(r["player_key"])
            wmat.append([float(r["seasons"].get(y0 + k, 0.0)) for k in range(ds.TARGET_SEASONS)])
            for n in SPANS:
                ds.RESOLVED_THROUGH = y0 + n - 1
                osum, ctgt, cflag, _wt, nobs = ds._label_6yr(r["seasons"], y0)
                assert cflag and nobs == n, (r["player_key"], n, nobs, cflag)
                obs[n].append(osum)
                ship[n].append(ctgt)
    finally:
        ds.RESOLVED_THROUGH = real_through
    assert ds.RESOLVED_THROUGH == real_through, "RESOLVED_THROUGH not restored"

    P = {
        "true": np.array(true, dtype=float),
        "dy": np.array(dy, dtype=int),
        "side": np.array(side),
        "keys": np.array(keys),
        "w": np.array(wmat, dtype=float),               # n x 6 season-index WAR
        "obs": {n: np.array(obs[n], dtype=float) for n in SPANS},
        "ship": {n: np.array(ship[n], dtype=float) for n in SPANS},
    }
    return P, recon


# ---------------------------------------------------------------------------
# part 1 and 4: the arms. Every multiplier / constant is FORWARD CHAINED.
# ---------------------------------------------------------------------------

def _fit_arm_params(w_prior, true_prior, obs_prior, ship_prior, perm=None):
    """From prior-cohort rows only: the candidate multiplier, the twin constant, the
    scalar-fit multiplier. perm reorders the season-index means (NULL-A)."""
    m = w_prior.mean(axis=0)
    if perm is not None:
        m = m[list(perm)]
    tot = float(m.sum())
    out = {"m": m.tolist(), "R": {}, "c": {}, "rstar": {}, "S": {}}
    for n in SPANS:
        cum = float(m[:n].sum())
        S = cum / tot if tot else float(n) / ds.TARGET_SEASONS
        out["S"][n] = S
        out["R"][n] = (1.0 / S) if S > 0 else float(ds.TARGET_SEASONS) / n
        out["c"][n] = float((true_prior - ship_prior[n]).mean())
        den = float((obs_prior[n] ** 2).sum())
        out["rstar"][n] = float((obs_prior[n] * true_prior).sum() / den) if den > 0 else \
            float(ds.TARGET_SEASONS) / n
    return out


def build_chain(P, cohorts, per_side: bool, perm=None):
    """Per eligible cohort, the parameters estimated on strictly prior cohorts."""
    chain = {}
    for Y in cohorts:
        prior = P["dy"] < Y
        if per_side:
            chain[Y] = {}
            for sd in SIDES:
                sel = prior & (P["side"] == sd)
                chain[Y][sd] = _fit_arm_params(
                    P["w"][sel], P["true"][sel],
                    {n: P["obs"][n][sel] for n in SPANS},
                    {n: P["ship"][n][sel] for n in SPANS}, perm)
        else:
            chain[Y] = _fit_arm_params(
                P["w"][prior], P["true"][prior],
                {n: P["obs"][n][prior] for n in SPANS},
                {n: P["ship"][n][prior] for n in SPANS}, perm)
    return chain


def score_chain(P, chain, cohorts, per_side: bool):
    """Project every eligible row with its own cohort's forward-chained parameters."""
    N = len(P["true"])
    out = {a: {n: np.full(N, np.nan) for n in SPANS} for a in ("cand", "twin", "scalar")}
    elig = np.zeros(N, dtype=bool)
    for Y in cohorts:
        sel = P["dy"] == Y
        if not sel.any():
            continue
        elig |= sel
        for n in SPANS:
            if per_side:
                for sd in SIDES:
                    s2 = sel & (P["side"] == sd)
                    pr = chain[Y][sd]
                    out["cand"][n][s2] = P["obs"][n][s2] * pr["R"][n]
                    out["twin"][n][s2] = P["ship"][n][s2] + pr["c"][n]
                    out["scalar"][n][s2] = P["obs"][n][s2] * pr["rstar"][n]
            else:
                pr = chain[Y]
                out["cand"][n][sel] = P["obs"][n][sel] * pr["R"][n]
                out["twin"][n][sel] = P["ship"][n][sel] + pr["c"][n]
                out["scalar"][n][sel] = P["obs"][n][sel] * pr["rstar"][n]
    return out, elig


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

_RNG = np.random.default_rng(SEED)


def _pct_ci(x, lo=2.5, hi=97.5):
    a, b = np.percentile(x, [lo, hi])
    return [round(float(a), 5), round(float(b), 5)]


def _avg_rank(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x), dtype=float)
    sx = x[order]
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and sx[j + 1] == sx[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def _spearman(a, b):
    if len(a) < 3:
        return float("nan")
    ra, rb = _avg_rank(a), _avg_rank(b)
    ra, rb = ra - ra.mean(), rb - rb.mean()
    den = math.sqrt(float((ra * ra).sum()) * float((rb * rb).sum()))
    return float((ra * rb).sum() / den) if den else float("nan")


def err_stats(pred, true):
    e = pred - true
    return {"n": int(len(e)),
            "mean_bias": round(float(e.mean()), 4),
            "mse": round(float((e ** 2).mean()), 4),
            "rmse": round(float(np.sqrt((e ** 2).mean())), 4),
            "mae": round(float(np.abs(e).mean()), 4),
            "sd_err": round(float(e.std(ddof=1)), 4) if len(e) > 1 else None}


def cell_mask(P, elig, n, side):
    m = elig.copy()
    if side != "all":
        m &= (P["side"] == side)
    return m


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    pins = pin_check()
    assert pins["pin_ok"], f"LAMBDA PIN VIOLATED: {pins['read']}"

    resolved, censored_rows, terminal_rows, meta = load_pool()
    P, recon = replay(resolved)
    N = len(P["true"])
    pool = {"n": N,
            "hit": int((P["side"] == "hit").sum()),
            "pit": int((P["side"] == "pit").sum()),
            "debut_years": sorted(set(int(y) for y in P["dy"]))}
    pool_matches_b1 = (pool["n"] == B1_POOL["n"] and pool["hit"] == B1_POOL["hit"]
                       and pool["pit"] == B1_POOL["pit"])

    # ---- part 3.2: eligible cohorts, from the pre-registered thresholds
    cohort_table, cohorts = [], []
    for Y in sorted(set(int(y) for y in P["dy"])):
        prior = P["dy"] < Y
        npool = int(prior.sum())
        nh = int((prior & (P["side"] == "hit")).sum())
        np_ = int((prior & (P["side"] == "pit")).sum())
        ok = (npool >= MIN_PRIOR_POOLED and nh >= MIN_PRIOR_PER_SIDE and np_ >= MIN_PRIOR_PER_SIDE)
        cohort_table.append({"debut_year": Y, "rows": int((P["dy"] == Y).sum()),
                             "prior_pooled": npool, "prior_hit": nh, "prior_pit": np_,
                             "eligible": bool(ok)})
        if ok:
            cohorts.append(Y)
    elig_mask_expected = np.isin(P["dy"], cohorts)

    # ---- the arms, real forward chain
    chain_pooled = build_chain(P, cohorts, per_side=False)
    chain_side = build_chain(P, cohorts, per_side=True)
    sc_pooled, elig = score_chain(P, chain_pooled, cohorts, per_side=False)
    sc_side, elig2 = score_chain(P, chain_side, cohorts, per_side=True)
    assert (elig == elig_mask_expected).all() and (elig2 == elig).all()
    n_elig = int(elig.sum())

    # ---- part 6.5: pooled vs per-side, tested
    est_pool_mask = P["dy"] < cohorts[0]
    mh = P["w"][est_pool_mask & (P["side"] == "hit")].mean(axis=0)
    mp = P["w"][est_pool_mask & (P["side"] == "pit")].mean(axis=0)
    ma = P["w"][est_pool_mask].mean(axis=0)

    def _S(m):
        t = float(m.sum())
        return {n: round(float(m[:n].sum()) / t, 4) for n in SPANS}

    hh = P["w"][est_pool_mask & (P["side"] == "hit")]
    pp = P["w"][est_pool_mask & (P["side"] == "pit")]
    d2 = []
    for _ in range(B_COND):
        a = hh[_RNG.integers(0, len(hh), len(hh))].mean(axis=0)
        b = pp[_RNG.integers(0, len(pp), len(pp))].mean(axis=0)
        d2.append(float(a[:2].sum() / a.sum()) - float(b[:2].sum() / b.sum()))
    d2 = np.array(d2)
    side_profile_test = {
        "estimation_pool": f"debut_year < {cohorts[0]}",
        "n_hit": int(len(hh)), "n_pit": int(len(pp)),
        "S_hit": _S(mh), "S_pit": _S(mp), "S_pooled": _S(ma),
        "S2_hit_minus_pit": round(float(mh[:2].sum() / mh.sum() - mp[:2].sum() / mp.sum()), 5),
        "S2_diff_ci95": _pct_ci(d2),
        "S2_diff_ci_excludes_zero": bool(np.percentile(d2, 2.5) > 0 or np.percentile(d2, 97.5) < 0),
        "note": ("if the CI covers zero the pooled profile is estimable without per-side "
                 "thinning; the pooled arm stays primary either way per gate doc part 1"),
    }

    multipliers = {str(Y): {"pooled_R": {str(n): round(chain_pooled[Y]["R"][n], 4) for n in SPANS},
                            "pooled_S": {str(n): round(chain_pooled[Y]["S"][n], 4) for n in SPANS},
                            "twin_c": {str(n): round(chain_pooled[Y]["c"][n], 4) for n in SPANS},
                            "scalar_rstar": {str(n): round(chain_pooled[Y]["rstar"][n], 4) for n in SPANS},
                            "shipped_R": {str(n): round(6.0 / n, 4) for n in SPANS},
                            "n_prior": int((P["dy"] < Y).sum())}
                   for Y in cohorts}

    # ---- per-cell descriptive error, all arms
    cells = {}
    for n in SPANS:
        for side in ("hit", "pit", "all"):
            m = cell_mask(P, elig, n, side)
            t = P["true"][m]
            cells[f"n{n}_{side}"] = {
                "shipped": err_stats(P["ship"][n][m], t),
                "candidate_pooled": err_stats(sc_pooled["cand"][n][m], t),
                "candidate_perside": err_stats(sc_side["cand"][n][m], t),
                "level_twin": err_stats(sc_pooled["twin"][n][m], t),
                "scalar_fit": err_stats(sc_pooled["scalar"][n][m], t),
            }

    # ---- part 2: DELTA_MSE with E_cond and E_refit floors
    def d_rows(arm_pred, base_pred, true):
        return (arm_pred - true) ** 2 - (base_pred - true) ** 2

    def e_cond(d):
        idx = _RNG.integers(0, len(d), size=(B_COND, len(d)))
        return d[idx].mean(axis=1)

    # E_refit: resample the FULL pool, REBUILD the forward chain, rescore
    print(f"E_refit: {B_REFIT} draws, rebuilding the forward chain each draw ...")
    refit_draws = {f"n{n}_{s}": {"vs_ship": [], "vs_twin": [], "perside_vs_ship": [],
                                 "twin_vs_ship": []}
                   for n in SPANS for s in ("hit", "pit", "all")}
    for b in range(B_REFIT):
        idx = _RNG.integers(0, N, N)
        Pb = {"true": P["true"][idx], "dy": P["dy"][idx], "side": P["side"][idx],
              "w": P["w"][idx],
              "obs": {n: P["obs"][n][idx] for n in SPANS},
              "ship": {n: P["ship"][n][idx] for n in SPANS}}
        ch_b = {}
        for Y in cohorts:
            pr = Pb["dy"] < Y
            if pr.sum() < 2:
                continue
            ch_b[Y] = _fit_arm_params(Pb["w"][pr], Pb["true"][pr],
                                      {n: Pb["obs"][n][pr] for n in SPANS},
                                      {n: Pb["ship"][n][pr] for n in SPANS})
        ch_bs = {}
        for Y in cohorts:
            pr = Pb["dy"] < Y
            ch_bs[Y] = {}
            for sd in SIDES:
                s2 = pr & (Pb["side"] == sd)
                if s2.sum() < 2:
                    ch_bs[Y] = None
                    break
                ch_bs[Y][sd] = _fit_arm_params(Pb["w"][s2], Pb["true"][s2],
                                               {n: Pb["obs"][n][s2] for n in SPANS},
                                               {n: Pb["ship"][n][s2] for n in SPANS})
        eb = np.isin(Pb["dy"], list(ch_b.keys()))
        cand_b = {n: np.full(N, np.nan) for n in SPANS}
        twin_b = {n: np.full(N, np.nan) for n in SPANS}
        cands_b = {n: np.full(N, np.nan) for n in SPANS}
        for Y, pr in ch_b.items():
            sel = Pb["dy"] == Y
            for n in SPANS:
                cand_b[n][sel] = Pb["obs"][n][sel] * pr["R"][n]
                twin_b[n][sel] = Pb["ship"][n][sel] + pr["c"][n]
            if ch_bs.get(Y):
                for sd in SIDES:
                    s2 = sel & (Pb["side"] == sd)
                    for n in SPANS:
                        cands_b[n][s2] = Pb["obs"][n][s2] * ch_bs[Y][sd]["R"][n]
        for n in SPANS:
            for s in ("hit", "pit", "all"):
                m = eb & ((Pb["side"] == s) if s != "all" else True)
                if m.sum() < 2:
                    continue
                t = Pb["true"][m]
                refit_draws[f"n{n}_{s}"]["vs_ship"].append(
                    float(d_rows(cand_b[n][m], Pb["ship"][n][m], t).mean()))
                refit_draws[f"n{n}_{s}"]["vs_twin"].append(
                    float(d_rows(cand_b[n][m], twin_b[n][m], t).mean()))
                refit_draws[f"n{n}_{s}"]["twin_vs_ship"].append(
                    float(d_rows(twin_b[n][m], Pb["ship"][n][m], t).mean()))
                v = cands_b[n][m]
                ok = ~np.isnan(v)
                if ok.sum() > 1:
                    refit_draws[f"n{n}_{s}"]["perside_vs_ship"].append(
                        float(d_rows(v[ok], Pb["ship"][n][m][ok], t[ok]).mean()))
        if (b + 1) % 500 == 0:
            print(f"  {b + 1}/{B_REFIT}")

    def pack(point, draws_cond, draws_refit):
        out = {"delta_mse": round(float(point), 5)}
        for tag, dr in (("E_cond", draws_cond), ("E_refit", np.array(draws_refit))):
            sd = float(dr.std(ddof=1))
            mde = 1.645 * sd
            ci = _pct_ci(dr)
            out[tag] = {"sd_boot": round(sd, 5), "ci95": ci,
                        "ci_upper_below_zero": bool(ci[1] < 0),
                        "mde95_one_sided": round(mde, 5),
                        "margin_over_floor": round(abs(float(point)) / mde, 4) if mde > 0 else None}
        out["instruments_agree"] = bool(out["E_cond"]["ci_upper_below_zero"]
                                        == out["E_refit"]["ci_upper_below_zero"])
        return out

    gate = {}
    signflip_p = {}
    for n in SPANS:
        for side in ("hit", "pit", "all"):
            key = f"n{n}_{side}"
            m = cell_mask(P, elig, n, side)
            t = P["true"][m]
            d_ship = d_rows(sc_pooled["cand"][n][m], P["ship"][n][m], t)
            d_twin = d_rows(sc_pooled["cand"][n][m], sc_pooled["twin"][n][m], t)
            d_scal = d_rows(sc_pooled["cand"][n][m], sc_pooled["scalar"][n][m], t)
            d_side = d_rows(sc_side["cand"][n][m], P["ship"][n][m], t)
            g = {
                "n": int(m.sum()),
                "candidate_vs_shipped": pack(d_ship.mean(), e_cond(d_ship),
                                             refit_draws[key]["vs_ship"]),
                "candidate_vs_level_twin": pack(d_twin.mean(), e_cond(d_twin),
                                                refit_draws[key]["vs_twin"]),
                "perside_candidate_vs_shipped": pack(d_side.mean(), e_cond(d_side),
                                                     refit_draws[key]["perside_vs_ship"]),
                "candidate_vs_scalar_fit_control": {
                    "delta_mse": round(float(d_scal.mean()), 5),
                    "E_cond_ci95": _pct_ci(e_cond(d_scal)),
                },
                "delta_mae_vs_shipped": round(
                    float(np.abs(sc_pooled["cand"][n][m] - t).mean()
                          - np.abs(P["ship"][n][m] - t).mean()), 5),
                "delta_rmse_vs_shipped": round(
                    float(np.sqrt((sc_pooled["cand"][n][m] - t) ** 2 @ np.ones(len(t)) / len(t))
                          - np.sqrt((P["ship"][n][m] - t) ** 2 @ np.ones(len(t)) / len(t))), 5),
            }
            # 4.3 sign-flip permutation, one sided toward improvement
            sgn = _RNG.integers(0, 2, size=(N_SIGNFLIP, len(d_ship))) * 2 - 1
            perm_means = (sgn * d_ship).mean(axis=1)
            obs_mean = float(d_ship.mean())
            p = (1 + int((perm_means <= obs_mean).sum())) / (1 + N_SIGNFLIP)
            g["signflip_permutation_p_one_sided"] = round(p, 5)
            signflip_p[key] = p
            gate[key] = g

    # ---- 4.2 NULL-A: 720 deterministic permutations of the season-index means
    null_a = {}
    perms = list(itertools.permutations(range(ds.TARGET_SEASONS)))
    identity = tuple(range(ds.TARGET_SEASONS))
    for n in SPANS:
        for side in ("hit", "pit", "all"):
            null_a[f"n{n}_{side}"] = []
    for perm in perms:
        if perm == identity:
            continue
        ch = build_chain(P, cohorts, per_side=False, perm=perm)
        sc, _e = score_chain(P, ch, cohorts, per_side=False)
        for n in SPANS:
            for side in ("hit", "pit", "all"):
                m = cell_mask(P, elig, n, side)
                t = P["true"][m]
                null_a[f"n{n}_{side}"].append(
                    float(d_rows(sc["cand"][n][m], P["ship"][n][m], t).mean()))
    null_a_out = {}
    for k, v in null_a.items():
        v = np.array(v)
        # compare against the UNROUNDED observed delta. Comparing against the rounded
        # value miscounts exact ties: every permutation that preserves the leading-n
        # season set gives a numerically identical delta (2! * 4! = 48 of them at n = 2).
        n_k, side_k = int(k[1]), k.split("_")[1]
        mk = cell_mask(P, elig, n_k, side_k)
        tk = P["true"][mk]
        obs_exact = float((((sc_pooled["cand"][n_k][mk] - tk) ** 2)
                           - ((P["ship"][n_k][mk] - tk) ** 2)).mean())
        tol = 1e-9 * max(1.0, abs(obs_exact))
        null_a_out[k] = {"n_permutations": int(len(v)),
                         "band95": _pct_ci(v),
                         "median": round(float(np.median(v)), 5),
                         "observed": round(obs_exact, 5),
                         "observed_below_p2_5": bool(obs_exact < np.percentile(v, 2.5)),
                         "n_permutations_strictly_better": int((v < obs_exact - tol).sum()),
                         "n_permutations_tied": int((np.abs(v - obs_exact) <= tol).sum()),
                         "n_permutations_strictly_worse": int((v > obs_exact + tol).sum()),
                         "frac_permutations_strictly_better":
                             round(float((v < obs_exact - tol).mean()), 5)}

    # ---- 4.2 NULL-B: zero-information projection, values permuted across rows
    null_b_out = {}
    for n in SPANS:
        for side in ("hit", "pit", "all"):
            m = cell_mask(P, elig, n, side)
            t = P["true"][m]
            c = sc_pooled["cand"][n][m]
            s = P["ship"][n][m]
            base = ((s - t) ** 2).mean()
            draws = []
            for _ in range(N_NULL_B):
                cp = _RNG.permutation(c)
                draws.append(float(((cp - t) ** 2).mean() - base))
            draws = np.array(draws)
            obsv = gate[f"n{n}_{side}"]["candidate_vs_shipped"]["delta_mse"]
            null_b_out[f"n{n}_{side}"] = {"n_draws": N_NULL_B, "band95": _pct_ci(draws),
                                          "median": round(float(np.median(draws)), 5),
                                          "observed": obsv,
                                          "observed_below_p2_5": bool(obsv < np.percentile(draws, 2.5))}

    # ---- part 3.3 multiplicity over the 8 span-by-side family cells
    fam = [f"n{n}_{s}" for n in SPANS for s in SIDES]
    fam_sig_cond = [k for k in fam if gate[k]["candidate_vs_shipped"]["E_cond"]["ci_upper_below_zero"]]
    fam_sig_refit = [k for k in fam if gate[k]["candidate_vs_shipped"]["E_refit"]["ci_upper_below_zero"]]
    ordered = sorted(fam, key=lambda k: signflip_p[k])
    holm, thresh_ok = [], True
    for i, k in enumerate(ordered):
        crit = 0.05 / (len(fam) - i)
        if thresh_ok and signflip_p[k] <= crit:
            holm.append(k)
        else:
            thresh_ok = False
    multiplicity = {
        "family": fam, "family_size": len(fam),
        "k_of_n_ci_upper_below_zero_E_cond": f"{len(fam_sig_cond)} of {len(fam)}",
        "cells_E_cond": sorted(fam_sig_cond),
        "k_of_n_ci_upper_below_zero_E_refit": f"{len(fam_sig_refit)} of {len(fam)}",
        "cells_E_refit": sorted(fam_sig_refit),
        "holm_significant_signflip_alpha_05": sorted(holm),
        "holm_significant_count": len(holm),
        "note": "the 4 pooled-side cells are reported but are not counted into the family",
    }

    # ---- part 7: label-space rank diagnostic. NOT a served-board rank delta.
    m_all = P["w"].mean(axis=0)
    S_prod = {n: float(m_all[:n].sum()) / float(m_all.sum()) for n in SPANS}
    ship_t, cand_t, nobs_l, side_l = [], [], [], []
    real_through = ds.RESOLVED_THROUGH
    for r in censored_rows:
        _tr, tc, cf, _w, nb = ds._label_6yr(r["seasons"], r["debut_year"])
        if not cf or nb not in S_prod:
            continue
        ship_t.append(tc)
        cand_t.append(_tr / S_prod[nb])
        nobs_l.append(nb)
        side_l.append(r["side"])
    assert ds.RESOLVED_THROUGH == real_through
    ship_t, cand_t = np.array(ship_t), np.array(cand_t)
    bt = np.array([rel._realized_bucket(v) for v in ship_t])
    bc = np.array([rel._realized_bucket(v) for v in cand_t])
    from collections import Counter
    label_space = {
        "what": ("Spearman between the SHIPPED and CANDIDATE censored targets over the shipped "
                 "rows that ride the projection. LABEL SPACE ONLY. This is NOT a served-board "
                 "rank delta: no refit was run, per gate doc part 7."),
        "profile_used": {"source": "all 988 resolved rows (what production would estimate on)",
                         "S_n": {str(n): round(S_prod[n], 4) for n in SPANS}},
        "n_rows": int(len(ship_t)),
        "n_shipped_censored_flagged": len(censored_rows),
        "n_terminal_resolved_excluded": len(terminal_rows),
        "terminal_resolved_excluded": [
            {"player_key": r["player_key"], "side": r["side"], "debut_year": r["debut_year"]}
            for r in terminal_rows],
        "terminal_note": ("window arithmetic marks these debuted rows censored, but the shipped "
                          "matrices resolve them via efv_dataset's career-terminal transaction "
                          "rule (retirement or lifetime ban), weight 1.0, observed_seasons 6. "
                          "They do NOT ride the projection and are excluded here. Excluding them "
                          "reproduces B1's 833."),
        "n_by_span": dict(sorted(Counter(nobs_l).items())),
        "n_by_side": dict(sorted(Counter(side_l).items())),
        "spearman_shipped_vs_candidate": round(_spearman(ship_t, cand_t), 5),
        "spearman_within_span_note": ("1.0 by construction within any fixed span: both are "
                                      "positive scalar multiples of obs_sum. All movement is "
                                      "cross-span."),
        "mean_shipped_target": round(float(ship_t.mean()), 4),
        "mean_candidate_target": round(float(cand_t.mean()), 4),
        "realized_bucket_changed": int((bt != bc).sum()),
        "realized_bucket_changed_pct": round(100.0 * float((bt != bc).mean()), 2),
        "bucket_up": int((bc > bt).sum()), "bucket_down": int((bc < bt).sum()),
        "economic_bound": ("deleting the ENTIRE censored pitcher block, the maximum perturbation "
                           "any label instrument in this program can cause, moves the served "
                           "board by rho 0.9441; nothing here can exceed that"),
    }

    # ---- POST HOC, NOT PRE-REGISTERED, NOT GATED, computed only after the run and
    # after every pre-registered RNG draw above, so no number above moves.
    # It is reported because the level twin turned out to beat the SHIPPED projection and
    # an owner deciding what to do about B1's bias needs that number in front of them.
    # It is NOT a recommendation and it did not determine this lane's verdict.
    post_hoc = {"_status": ("POST HOC. Not in the pre-registration. Computed after the run, "
                            "appended after all pre-registered draws. Gates nothing. This lane's "
                            "verdict is about the CANDIDATE and does not depend on this block."),
                "what": "level twin (shipped + forward-chained constant) versus SHIPPED",
                "cells": {}}
    for n in SPANS:
        for side in ("hit", "pit", "all"):
            key = f"n{n}_{side}"
            m = cell_mask(P, elig, n, side)
            t = P["true"][m]
            dtw = d_rows(sc_pooled["twin"][n][m], P["ship"][n][m], t)
            post_hoc["cells"][key] = pack(dtw.mean(), e_cond(dtw),
                                          refit_draws[key]["twin_vs_ship"])
            post_hoc["cells"][key]["delta_mae"] = round(
                float(np.abs(sc_pooled["twin"][n][m] - t).mean()
                      - np.abs(P["ship"][n][m] - t).mean()), 5)

    # ---- verdict, strictly by gate doc part 6
    pc = gate[PRIMARY_CELL[0]]
    g1 = (pc["candidate_vs_shipped"]["E_cond"]["ci_upper_below_zero"]
          and pc["candidate_vs_shipped"]["E_refit"]["ci_upper_below_zero"])
    g2 = (pc["candidate_vs_level_twin"]["E_cond"]["ci_upper_below_zero"]
          and pc["candidate_vs_level_twin"]["E_refit"]["ci_upper_below_zero"])
    g3 = (null_a_out[PRIMARY_CELL[0]]["observed_below_p2_5"]
          and null_b_out[PRIMARY_CELL[0]]["observed_below_p2_5"])
    g4 = bool(signflip_p[PRIMARY_CELL[0]] < 0.05)
    g5 = bool(len(fam_sig_cond) >= 4 and len(holm) >= 2)
    if not g1:
        verdict = "NULL"
    elif not g2:
        verdict = "LEVEL_SHIFT_ONLY"
    elif g3 and g4 and g5:
        verdict = "REPLACEMENT_BEATS_SHIPPED_AND_TWIN"
    else:
        verdict = "UNDERPOWERED_OR_UNSTABLE"

    result = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "lane": "B2 (master plan 2026-08-07b)",
        "gate_doc": "docs/efv-2026-08-07b/LABEL_REPLACEMENT_GATE.md",
        "depends_on": "data/xfv_label_censoring_eval.json (Lane B1)",
        "what": ("one candidate replacement for efv_dataset._label_6yr's flat-rate tail "
                 "projection: a FORWARD-CHAINED per-season-index share profile, scored on "
                 "held-out truncation error against the shipped projection, a rank-identical "
                 "level twin, two nulls, a sign-flip permutation test and a one-parameter "
                 "scalar-fit control"),
        "candidate": ("candidate_target(n) = obs_sum / S_n, S_n = cumulative share of six-year "
                      "WAR mass through season index n, estimated on STRICTLY PRIOR debut "
                      "cohorts. Shipped is the special case S_n = n/6."),
        "shipped_function": "efv_dataset._label_6yr",
        "resolved_through": ds.RESOLVED_THROUGH,
        "target_seasons": ds.TARGET_SEASONS,
        "primary_statistic": "DELTA_MSE = MSE(candidate) - MSE(shipped), negative = better",
        "primary_cell": PRIMARY_CELL[0],
        "thresholds_added_by_this_lane": {
            "min_prior_pooled": MIN_PRIOR_POOLED,
            "min_prior_per_side": MIN_PRIOR_PER_SIDE,
            "chosen_from": "row counts only, before any error number existed",
            "gate_1": "DELTA_MSE CI95 upper < 0 in n2_hit under BOTH E_cond and E_refit",
            "gate_2": "DELTA_MSE vs level twin CI95 upper < 0 in n2_hit under BOTH",
            "gate_5": ">=4 of 8 family cells CI95 upper < 0 under E_cond AND >=2 Holm significant",
        },
        "bootstrap": {"seed": SEED, "seed_provenance": "inherited from B1, fixed before the run",
                      "B_cond": B_COND, "B_refit": B_REFIT,
                      "n_null_b": N_NULL_B, "n_signflip": N_SIGNFLIP,
                      "null_a": "720 deterministic permutations, no RNG"},
        "pin_check": pins,
        "matrix_meta": meta,
        "ground_truth_reconciliation": recon,
        "pool": pool,
        "pool_matches_b1": bool(pool_matches_b1),
        "cohort_eligibility": cohort_table,
        "eligible_cohorts": cohorts,
        "n_scored": n_elig,
        "n_scored_hit": int((elig & (P["side"] == "hit")).sum()),
        "n_scored_pit": int((elig & (P["side"] == "pit")).sum()),
        "forward_chain_multipliers": multipliers,
        "pooled_vs_perside_profile": side_profile_test,
        "error_by_cell": cells,
        "gate": gate,
        "null_a_permuted_share_profile": null_a_out,
        "null_b_zero_information_projection": null_b_out,
        "multiplicity": multiplicity,
        "label_space_rank_diagnostic": label_space,
        "post_hoc_not_preregistered": post_hoc,
        "gates": {"gate1_vs_shipped": bool(g1), "gate2_vs_level_twin": bool(g2),
                  "gate3_null_separation": bool(g3), "gate4_permutation": bool(g4),
                  "gate5_breadth": bool(g5)},
        "verdict": verdict,
        "ship_recommendation": "NO LABEL CHANGE SHIPPED. This lane writes no shipped code by design.",
    }
    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"\npool {pool['n']} (b1 match={pool_matches_b1})  eligible cohorts {cohorts}  scored {n_elig}")
    print(f"S_n forward-chained (first eligible cohort {cohorts[0]}): "
          f"{ {n: round(chain_pooled[cohorts[0]]['S'][n], 4) for n in SPANS} }")
    for n in SPANS:
        for side in ("hit", "pit"):
            k = f"n{n}_{side}"
            g = gate[k]
            print(f"  {k}: n={g['n']:4d} dMSE_vs_ship={g['candidate_vs_shipped']['delta_mse']:+9.4f} "
                  f"cond_ci=[{g['candidate_vs_shipped']['E_cond']['ci95'][0]:+8.3f},"
                  f"{g['candidate_vs_shipped']['E_cond']['ci95'][1]:+8.3f}] "
                  f"refit_ci=[{g['candidate_vs_shipped']['E_refit']['ci95'][0]:+8.3f},"
                  f"{g['candidate_vs_shipped']['E_refit']['ci95'][1]:+8.3f}] "
                  f"| vs_twin={g['candidate_vs_level_twin']['delta_mse']:+9.4f} "
                  f"twin_cond_ci=[{g['candidate_vs_level_twin']['E_cond']['ci95'][0]:+8.3f},"
                  f"{g['candidate_vs_level_twin']['E_cond']['ci95'][1]:+8.3f}] "
                  f"p={g['signflip_permutation_p_one_sided']:.4f}")
    print(f"\ngates: {result['gates']}")
    print(f"VERDICT: {verdict}")
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
