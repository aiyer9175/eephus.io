# eFV minimum-detectable-effect lab (LANE A, 2026-08-07).
#
# WHY THIS FILE EXISTS. source_backtest.XFV_VS_CONSENSUS_MDE95 gates the published
# "eFV beats consensus" verdict. Its 0.045 was measured on the RETIRED 4-fold pool
# (n 353 hit / 438 pit). The owner promoted efv_model.SCORED_YEARS to 11 folds on
# 2026-08-06, so the pool is now 755 / 890 and the floor that gate uses is a number
# from a different experiment. This lab re-derives it under the protocol that
# actually ships, and it is the ONLY sanctioned producer of that constant.
#
# PROTOCOL (docs/EFV_GATE_STANDARD.md section 2): paired bootstrap resampling the
# WHOLE pool (train AND test) with a refit on every draw. A test-only bootstrap
# understates sd by 1.6-1.8x, which is exactly the error that would re-license the
# sub-floor claims the gate standard retired.
#
# Run: python tools/efv_mde_lab.py parity        (replica vs shipped, no writes)
#      python tools/efv_mde_lab.py cost          (per-replicate cost, no writes)
#      python tools/efv_mde_lab.py mde [B]       (measure + write the ledger artifact)
#      python tools/efv_mde_lab.py sensitivity   (chain-start x 2024-weight table)
#      python tools/efv_mde_lab.py headtohead [B] (source_backtest common-set gap + MDE)
from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_model as E                                        # noqa: E402  read-only
from prospect_path import _ALPHAS, _RIDGE_HOLDOUT_SEED       # noqa: E402

OUT_PATH = ROOT / "data" / "xfv_mde_floor.json"
SEED = 20260807
SIDES = ("hit", "pit")


# --------------------------------------------------------------------- data
def load_side(side: str) -> dict:
    """The debuted-KM eval pool for one side, as numpy arrays.

    Matches efv_model.run(): rows = matrix, deb = kind == 'debuted', then _prep on
    target_censored. _run_eval trains inside that same debuted pool (train_frame is
    NOT the full pool here), so the arrays carry no bust rows at all.
    """
    from efv_dataset import matrix_path
    raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    deb = [r for r in raw if r["kind"] == "debuted"]
    prep = E._prep(deb, "target_censored", side)
    keys, mono = E._feature_spec(side)
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float)
    return {
        "side": side, "keys": list(keys), "mono": mono,
        "X": X,
        "y": np.array([r["target"] for r in prep], dtype=float),
        "w": np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None),
        "fv": np.array([r["fv"] for r in prep], dtype=float),
        "dy": np.array([r["decision_year"] for r in prep], dtype=int),
        "lam": E.blend_lambda(side),
        "n": len(prep),
    }


# --------------------------------------------------------------------- primitives
def ridge_fit(X, y, w):
    """Bit-parity with prospect_path._fit_ridge: weighted normal equations, alpha by
    5-fold CV over a permutation seeded on _RIDGE_HOLDOUT_SEED, weighted MAE."""
    n = len(y)
    if n < 40:
        return None
    k = X.shape[1]
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd = sd.copy()
    sd[sd == 0] = 1.0
    Xs = (X - mu) / sd

    def _wmean(idx):
        ww = w[idx]
        return float(np.average(y[idx], weights=ww)) if ww.sum() > 0 else float(y[idx].mean())

    def _wridge(idx, alpha, b):
        Xi, wi = Xs[idx], w[idx]
        WX = Xi * wi[:, None]
        A = WX.T @ Xi + alpha * np.eye(k)
        return np.linalg.solve(A, WX.T @ (y[idx] - b))

    order = np.random.default_rng(_RIDGE_HOLDOUT_SEED).permutation(n)
    folds = np.array_split(order, 5)
    best = None
    for alpha in _ALPHAS:
        err_sum, w_sum = 0.0, 0.0
        for i in range(len(folds)):
            ho = folds[i]
            tri = np.concatenate([folds[j] for j in range(len(folds)) if j != i])
            if len(ho) == 0 or len(tri) == 0:
                continue
            b_tr = _wmean(tri)
            pred = Xs[ho] @ _wridge(tri, alpha, b_tr) + b_tr
            ww = w[ho]
            if ww.sum() > 0:
                err_sum += float(np.sum(np.abs(pred - y[ho]) * ww))
                w_sum += float(ww.sum())
            else:
                err_sum += float(np.sum(np.abs(pred - y[ho])))
                w_sum += float(len(ho))
        mae = (err_sum / w_sum) if w_sum > 0 else float("inf")
        if best is None or mae < best[0]:
            best = (mae, alpha)
    alpha = best[1]
    b = _wmean(np.arange(n))
    return (mu, sd, _wridge(np.arange(n), alpha, b), b)


def ridge_pred(m, X):
    mu, sd, ww, b = m
    return ((X - mu) / sd) @ ww + b


def ols_fit(x, y):
    if len(y) < 8:
        return None
    mx, my = x.mean(), y.mean()
    var = float(((x - mx) ** 2).sum())
    if var <= 0:
        return None
    b = float(((x - mx) * (y - my)).sum()) / var
    return (my - b * mx, b)


def _rankavg(v):
    v = np.asarray(v, dtype=float)
    order = v.argsort(kind="mergesort")
    r = np.empty(len(v), dtype=float)
    r[order] = np.arange(1, len(v) + 1, dtype=float)
    s = v[order]
    i, n = 0, len(s)
    while i < n:
        j = i
        while j + 1 < n and s[j + 1] == s[i]:
            j += 1
        if j > i:
            r[order[i:j + 1]] = (i + j) / 2.0 + 1
        i = j + 1
    return r


def wrho(p, t, w=None):
    """Pair-weighted Spearman, UNROUNDED. prospect_path._weighted_spearman rounds to
    4 decimals; a bootstrap sd built from rounded replicates is quantized at a scale
    comparable to the effect being measured, so this lab keeps full precision and
    checks parity against the rounded published value separately."""
    if len(p) < 8:
        return float("nan")
    rp, rt = _rankavg(p), _rankavg(t)
    if w is None:
        w = np.ones(len(p))
    sw = float(w.sum())
    if sw <= 0:
        return float("nan")
    mx = float((w * rp).sum()) / sw
    my = float((w * rt).sum()) / sw
    a, b = rp - mx, rt - my
    cov = float((w * a * b).sum())
    vx = float((w * a * a).sum())
    vy = float((w * b * b).sum())
    if vx <= 0 or vy <= 0:
        return float("nan")
    return cov / math.sqrt(vx * vy)


# --------------------------------------------------------------------- one pass
def chain(D, sel=None, years=None, lam=None):
    """Forward-chained blend + baseline predictions for one side.

    `sel` = row indices (a bootstrap resample); None = the whole pool. Returns
    (year, cons, blend, target, weight) arrays over the pooled test folds, or None
    when no fold survives the floors.
    """
    years = tuple(E.SCORED_YEARS) if years is None else tuple(years)
    lam = D["lam"] if lam is None else lam
    if sel is None:
        sel = np.arange(D["n"])
    X, y, w, fv, dy = D["X"][sel], D["y"][sel], D["w"][sel], D["fv"][sel], D["dy"][sel]
    YR, C, B, T, W = [], [], [], [], []
    for yr in years:
        tr = np.flatnonzero(dy < yr)
        te = np.flatnonzero(dy == yr)
        if len(te) < 15 or len(tr) < 60:
            continue
        o = ols_fit(fv[tr], y[tr])
        rg = ridge_fit(X[tr], y[tr], w[tr])
        if o is None or rg is None:
            continue
        cons = np.maximum(0.0, o[0] + o[1] * fv[te])
        mod = ridge_pred(rg, X[te])
        YR.append(np.full(len(te), yr))
        C.append(cons)
        B.append((1 - lam) * cons + lam * mod)
        T.append(y[te])
        W.append(w[te])
    if not B:
        return None
    return tuple(np.concatenate(a) for a in (YR, C, B, T, W))


def block_norm(yr, v):
    """Percentile position inside each cohort-year block, on [0, 1]."""
    out = np.empty(len(v), dtype=float)
    for u in np.unique(yr):
        m = yr == u
        out[m] = (_rankavg(v[m]) - 0.5) / int(m.sum())
    return out


def stats_from(parts, weighted=True):
    """parts = {side: (yr, cons, blend, target, weight)}. Returns the pooled per-side
    rhos plus the joint block-rho, both legs computed on identical rows."""
    out = {}
    bc, bb, bt, bw = [], [], [], []
    for side, r in parts.items():
        if r is None:
            continue
        yr, cons, blend, tgt, w = r
        ww = w if weighted else None
        out[side] = {
            "n": int(len(tgt)),
            "consensus": wrho(cons, tgt, ww),
            "blend": wrho(blend, tgt, ww),
        }
        out[side]["delta"] = out[side]["blend"] - out[side]["consensus"]
        # (side x cohort-year) blocks: tag the year so hit-2020 and pit-2020 stay
        # separate blocks, which is what "side x cohort-year" means.
        tag = yr * 10 + (1 if side == "pit" else 0)
        bc.append(block_norm(tag, cons))
        bb.append(block_norm(tag, blend))
        bt.append(block_norm(tag, tgt))
        bw.append(w)
    if not bc:
        return out
    bc, bb, bt, bw = (np.concatenate(a) for a in (bc, bb, bt, bw))
    ww = bw if weighted else None
    out["block"] = {
        "n": int(len(bt)),
        "consensus": wrho(bc, bt, ww),
        "blend": wrho(bb, bt, ww),
    }
    out["block"]["delta"] = out["block"]["blend"] - out["block"]["consensus"]
    return out


# --------------------------------------------------------------------- modes
def parity():
    print("=== PARITY: replica vs shipped efv_model._run_eval (debuted_km, 11 fold) ===")
    D = {s: load_side(s) for s in SIDES}
    parts = {s: chain(D[s]) for s in SIDES}
    st = stats_from(parts, weighted=True)
    stu = stats_from(parts, weighted=False)
    for s in SIDES:
        art = ROOT / "data" / ("xfv_eval_pitcher.json" if s == "pit" else "xfv_eval.json")
        ship = {}
        if art.exists():
            ev = json.loads(art.read_text(encoding="utf-8"))
            ship = ((ev.get("evals") or {}).get("debuted_km") or {}).get("pooled_oos") or {}
        print(f"  {s}: lam={D[s]['lam']}  n={st[s]['n']}  "
              f"cons={st[s]['consensus']:.4f} blend={st[s]['blend']:.4f} "
              f"delta={st[s]['delta']:+.4f}")
        print(f"       shipped artifact: n={(ship.get('blend') or {}).get('n')} "
              f"cons={(ship.get('baseline') or {}).get('spearman')} "
              f"blend={(ship.get('blend') or {}).get('spearman')}")
        print(f"       unweighted: cons={stu[s]['consensus']:.4f} "
              f"blend={stu[s]['blend']:.4f} delta={stu[s]['delta']:+.4f}")
    print(f"  block-rho weighted   n={st['block']['n']} cons={st['block']['consensus']:.4f} "
          f"blend={st['block']['blend']:.4f} delta={st['block']['delta']:+.4f}")
    print(f"  block-rho unweighted n={stu['block']['n']} cons={stu['block']['consensus']:.4f} "
          f"blend={stu['block']['blend']:.4f} delta={stu['block']['delta']:+.4f}")
    return D, st, stu


def cost():
    D = {s: load_side(s) for s in SIDES}
    rng = np.random.default_rng(SEED)
    t0 = time.time()
    reps = 5
    for _ in range(reps):
        parts = {s: chain(D[s], rng.integers(0, D[s]["n"], D[s]["n"])) for s in SIDES}
        stats_from(parts, weighted=True)
    per = (time.time() - t0) / reps
    print(f"per replicate: {per:.3f}s -> B=500 {per*500/60:.1f} min, "
          f"B=1000 {per*1000/60:.1f} min, B=2000 {per*2000/60:.1f} min")
    return per


def mde(B: int = 2000, write: bool = True):
    D = {s: load_side(s) for s in SIDES}
    point_w = stats_from({s: chain(D[s]) for s in SIDES}, weighted=True)
    point_u = stats_from({s: chain(D[s]) for s in SIDES}, weighted=False)
    rng = np.random.default_rng(SEED)
    draws = {k: {"w": [], "u": []} for k in ("hit", "pit", "block")}
    t0 = time.time()
    done = 0
    for i in range(B):
        parts = {s: chain(D[s], rng.integers(0, D[s]["n"], D[s]["n"])) for s in SIDES}
        sw = stats_from(parts, weighted=True)
        su = stats_from(parts, weighted=False)
        if not all(k in sw for k in draws):
            continue
        for k in draws:
            draws[k]["w"].append(sw[k]["delta"])
            draws[k]["u"].append(su[k]["delta"])
        done += 1
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{B}  {time.time()-t0:.0f}s", flush=True)
    elapsed = round(time.time() - t0, 1)

    def _summ(vals, point):
        a = np.array(vals, dtype=float)
        a = a[np.isfinite(a)]
        sd = float(a.std(ddof=1))
        return {
            "B_used": int(len(a)),
            "point_delta": round(float(point), 5),
            "boot_mean_delta": round(float(a.mean()), 5),
            "sd": round(sd, 5),
            # MDE95 = the two-sided 95% half-width of the delta's own sampling
            # distribution. An observed delta smaller than this is a null.
            "mde95": round(1.96 * sd, 4),
            "mde95_onesided": round(1.645 * sd, 4),
            "ci95": [round(float(np.percentile(a, 2.5)), 5),
                     round(float(np.percentile(a, 97.5)), 5)],
            "p_gt_0": round(float((a > 0).mean()), 4),
            "resolvable": bool(abs(point) >= 1.96 * sd),
        }

    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "produced_by": "tools/efv_mde_lab.py mde",
        "purpose": ("Minimum detectable effect for the model-vs-consensus pooled-rho gate, "
                    "re-derived under the 11-fold pair-weighted protocol that ships today. "
                    "Feeds source_backtest.XFV_VS_CONSENSUS_MDE95 and "
                    "docs/EFV_GATE_STANDARD.md section 1."),
        "basis": {
            "scored_years": list(E.SCORED_YEARS),
            "folds": len(E.SCORED_YEARS),
            "headline_weighting": "pair-weighted (row weight = observed_seasons/6)",
            "pool": "debuted rows, KM-censored target; train and test both inside that pool",
            "lambda": {s: D[s]["lam"] for s in SIDES},
            "matrix_rows": {s: D[s]["n"] for s in SIDES},
        },
        "protocol": ("paired bootstrap over the WHOLE pool (train AND test resampled together, "
                     "one draw per side per replicate), refitting consensus OLS and the weighted "
                     "ridge on every draw; blend and baseline scored on identical rows. "
                     "MDE95 = 1.96 * sd(delta)."),
        "B_requested": int(B),
        "seed": SEED,
        "elapsed_s": elapsed,
        "weighted": {k: _summ(draws[k]["w"], point_w[k]["delta"]) for k in draws},
        "unweighted": {k: _summ(draws[k]["u"], point_u[k]["delta"]) for k in draws},
        "point_estimates": {
            "weighted": {k: {kk: (round(vv, 5) if isinstance(vv, float) else vv)
                             for kk, vv in point_w[k].items()} for k in point_w},
            "unweighted": {k: {kk: (round(vv, 5) if isinstance(vv, float) else vv)
                               for kk, vv in point_u[k].items()} for k in point_u},
        },
    }
    if write:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("wrote", OUT_PATH)
    print(json.dumps({k: out["weighted"][k] for k in draws}, indent=1))
    print(json.dumps({k: out["unweighted"][k] for k in draws}, indent=1))
    return out


def _load_h2h():
    """The source_backtest common set, joined to the eFV matrix pool by player_key.

    Returns (per-side pool arrays for the oos_grades train frame, and for each pool
    row the list of common-set (consensus_fv, war) rows that player owns). Resampling
    a pool row therefore resamples BOTH the fit and the scored rows, which is what
    makes the head-to-head bootstrap paired rather than test-only.
    """
    import source_backtest as SB
    from efv_dataset import matrix_path
    uni = SB._load_universe(SB.DATA_DIR)
    years = SB._resolved_years(uni, SB.date.today().year)
    raters = list(SB.SCORED_SOURCES) + [SB.CONSENSUS_KEY]
    by_key: dict[str, list] = {}
    for p in uni:
        out = SB._outcome(p)
        for y in years:
            g = SB._rater_grades_for_year(p, y)
            if g and all(r in g for r in raters):
                by_key.setdefault(p.get("player_key"), []).append(
                    (float(g[SB.CONSENSUS_KEY]), float(out["war"])))
    pools = {}
    for side in SIDES:
        raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        full = [r for r in raw if not (r["kind"] == "bust" and r.get("bust_recent"))]
        prep = E._prep(full, "target_censored", side)
        keys, _m = E._feature_spec(side)
        pools[side] = {
            "side": side, "keys": list(keys),
            "X": np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float),
            "y": np.array([r["target"] for r in prep], dtype=float),
            "w": np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None),
            "fv": np.array([r["fv"] for r in prep], dtype=float),
            "dy": np.array([r["decision_year"] for r in prep], dtype=int),
            "lam": E.blend_lambda(side),
            "n": len(prep),
            "rows": [by_key.get(r["player_key"]) or [] for r in prep],
        }
    return pools, len(by_key)


def _h2h_pass(P, sel=None):
    """One forward-chained oos_grades pass, scored against the common set.

    Returns (efv_grade, consensus_fv, war) arrays. Mirrors efv_model.oos_grades:
    full-pool train frame, linear output calibration, model leg floored at -2.
    """
    G, C, T = [], [], []
    for side, D in P.items():
        s = np.arange(D["n"]) if sel is None else sel[side]
        X, y, w, fv, dy = D["X"][s], D["y"][s], D["w"][s], D["fv"][s], D["dy"][s]
        rows = [D["rows"][i] for i in s]
        lam = D["lam"]
        for yr in E.SCORED_YEARS:
            tr = np.flatnonzero(dy < yr)
            te = np.flatnonzero(dy == yr)
            if len(te) < 15 or len(tr) < 60:
                continue
            o = ols_fit(fv[tr], y[tr])
            rg = ridge_fit(X[tr], y[tr], w[tr])
            if o is None or rg is None:
                continue
            cal = E._fit_linear_calibration(list(zip(ridge_pred(rg, X[tr]).tolist(), y[tr].tolist())))
            a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
            cons = np.maximum(0.0, o[0] + o[1] * fv[te])
            mod = np.maximum(-2.0, a + b * ridge_pred(rg, X[te]))
            grade = (1 - lam) * cons + lam * mod
            for j, i in enumerate(te):
                for cfv, war in rows[i]:
                    G.append(grade[j])
                    C.append(cfv)
                    T.append(war)
    if not G:
        return None
    return np.array(G), np.array(C), np.array(T)


def headtohead(B: int = 2000, write: bool = True):
    """The gap the Methodology copy asserts: eFV's OOS grade against the PROSPX
    consensus on the source_backtest common set, with its own MDE.

    The published pair (0.3511 vs 0.2846) is NOT computed on identical rows: eFV
    covers 3,210 of the 4,259 common rows, and consensus is scored on all 4,259.
    This mode reports both legs on the eFV-covered rows, which is the only version
    of the number that a head-to-head claim can rest on.
    """
    P, n_common_players = _load_h2h()
    pt = _h2h_pass(P)
    g, c, t = pt
    point = {"n_rows": int(len(t)),
             "efv": wrho(g, t), "consensus": wrho(c, t)}
    point["delta"] = point["efv"] - point["consensus"]
    rng = np.random.default_rng(SEED + 1)
    draws = []
    t0 = time.time()
    for i in range(B):
        sel = {s: rng.integers(0, P[s]["n"], P[s]["n"]) for s in P}
        r = _h2h_pass(P, sel)
        if r is None:
            continue
        gg, cc, tt = r
        d = wrho(gg, tt) - wrho(cc, tt)
        if np.isfinite(d):
            draws.append(d)
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{B}  {time.time()-t0:.0f}s", flush=True)
    a = np.array(draws, dtype=float)
    sd = float(a.std(ddof=1))
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "produced_by": "tools/efv_mde_lab.py headtohead",
        "basis": {"scored_years": list(E.SCORED_YEARS),
                  "common_set_players": n_common_players,
                  "scored_rows": point["n_rows"]},
        "protocol": ("cluster paired bootstrap: resample the eFV matrix pool by player, "
                     "refit the forward chain, score both legs on the common-set rows the "
                     "resampled players own. MDE95 = 1.645 * sd(delta), one-sided, the same "
                     "convention as the model-vs-consensus floor."),
        "B_requested": int(B), "B_used": int(len(a)), "seed": SEED + 1,
        "elapsed_s": round(time.time() - t0, 1),
        "point": {k: (round(v, 5) if isinstance(v, float) else v) for k, v in point.items()},
        "sd": round(sd, 5),
        "mde95": round(1.645 * sd, 4),
        "mde95_twosided": round(1.96 * sd, 4),
        "ci95": [round(float(np.percentile(a, 2.5)), 5),
                 round(float(np.percentile(a, 97.5)), 5)],
        "p_gt_0": round(float((a > 0).mean()), 4),
        "resolvable": bool(abs(point["delta"]) >= 1.645 * sd),
    }
    if write:
        p = ROOT / "data" / "xfv_headtohead_gap.json"
        p.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("wrote", p)
    print(json.dumps(out, indent=1))
    return out


def sensitivity():
    """Protocol sensitivity table (REPORT ONLY, no served basis change): chain start
    2014 vs 2017, crossed with the censored 2024 fold carrying its live weight 0.333
    or being left out of the chain entirely.

    "Weight 0" is implemented as EXCLUSION rather than a zero in the weight vector.
    A zero-weight row still enters _rankdata, so it would keep shifting every other
    row's rank while contributing nothing, which measures neither dial cleanly.
    """
    D = {s: load_side(s) for s in SIDES}
    rows = []
    for start in (2014, 2017):
        for drop24 in (True, False):
            years = tuple(y for y in E.SCORED_YEARS
                          if y >= start and not (drop24 and y >= 2024))
            parts = {s: chain(D[s], years=years) for s in SIDES}
            st = stats_from(parts, weighted=True)
            rows.append({
                "chain_start": start,
                "fold_2024": "excluded" if drop24 else "in, weight 0.333",
                "hit_n": st["hit"]["n"], "hit_cons": round(st["hit"]["consensus"], 4),
                "hit_blend": round(st["hit"]["blend"], 4),
                "hit_delta": round(st["hit"]["delta"], 4),
                "pit_n": st["pit"]["n"], "pit_cons": round(st["pit"]["consensus"], 4),
                "pit_blend": round(st["pit"]["blend"], 4),
                "pit_delta": round(st["pit"]["delta"], 4),
                "block_blend": round(st["block"]["blend"], 4),
                "block_delta": round(st["block"]["delta"], 4),
            })
    for r in rows:
        print(json.dumps(r))
    return rows


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "parity"
    t0 = time.time()
    if mode == "parity":
        parity()
    elif mode == "cost":
        cost()
    elif mode == "mde":
        mde(int(sys.argv[2]) if len(sys.argv) > 2 else 2000)
    elif mode == "sensitivity":
        sensitivity()
    elif mode == "headtohead":
        headtohead(int(sys.argv[2]) if len(sys.argv) > 2 else 2000)
    else:
        print("modes: parity | cost | mde [B] | sensitivity | headtohead [B]")
    print("elapsed", round(time.time() - t0, 1), "s")
