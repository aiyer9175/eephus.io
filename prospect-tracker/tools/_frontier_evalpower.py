# SCRATCH (frontier: higher-power eFV evaluator). Reads only; writes JSON to data/_scratch.
# Does NOT modify any shipped module. Run: python tools/_frontier_evalpower.py

from __future__ import annotations

import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_model as em                      # noqa: E402  (read-only use)
from prospect_path import _fit_ridge, _predict, _fit_linear_calibration  # noqa: E402

DATA = ROOT / "data"
ORIGINS_ALL = tuple(range(2016, 2025))      # 9 rolling origins (debuted rows exist 2016-2024)
ORIGINS_GATE = (2020, 2021, 2022, 2023)     # the CURRENT gate
LAM = {"hit": 0.85, "pit": 0.63}            # pinned served blend weights
CONTRIB, STAR = 3.0, 10.0

BASE_KEYS = {s: em._feature_spec(s)[0] for s in ("hit", "pit")}
ARMS = {
    "base":        {s: list(BASE_KEYS[s]) for s in ("hit", "pit")},
    "noise":       {s: list(BASE_KEYS[s]) + ["_noise"] for s in ("hit", "pit")},
    "prod_trend":  {s: list(BASE_KEYS[s]) + ["prod_trend"] for s in ("hit", "pit")},
    "drop_peakk":  {s: [k for k in BASE_KEYS[s] if k != "peak_k_rel"] for s in ("hit", "pit")},
}


# --------------------------------------------------------------------------- data
def load_pool():
    rng = random.Random(20260724)
    pool = {}
    for side, fn in (("hit", "xfv_hitter_matrix.json"), ("pit", "xfv_pitcher_matrix.json")):
        raw = json.loads((DATA / fn).read_text(encoding="utf-8"))
        out = []
        for r in raw:
            p = em._prep([r], "target_censored", side)
            if not p:
                continue
            d = p[0]
            d["side"] = side
            d["kind"] = r["kind"]
            d["bust_recent"] = bool(r.get("bust_recent"))
            d["feats"]["_noise"] = rng.gauss(0.0, 1.0)     # fixed per player, zero information
            out.append(d)
        pool[side] = out
    return pool


def frame_rows(rows, frame):
    if frame == "debuted":
        return [r for r in rows if r["kind"] == "debuted"]
    return [r for r in rows if not (r["kind"] == "bust" and r["bust_recent"])]


# --------------------------------------------------------------------------- scoring
def score_records(rows, side, keys, origins, train_frame, test_frame="debuted", cal=True):
    """Forward-chained production-analogue scores. Returns list of records."""
    tr_pool = frame_rows(rows, train_frame)
    te_pool = frame_rows(rows, test_frame)
    lam = LAM[side]
    recs = []
    for yr in origins:
        tr = [r for r in tr_pool if r["decision_year"] < yr]
        te = [r for r in te_pool if r["decision_year"] == yr]
        if len(te) < 15 or len(tr) < 60:
            continue
        ols = em._fit_ols_fv(tr)
        ridge = _fit_ridge(tr, keys)
        if not (ols and ridge):
            continue
        a, b = 0.0, 1.0
        if cal:
            c = _fit_linear_calibration([(_predict(ridge, r["feats"]), r["target"]) for r in tr])
            if c:
                a, b = c["a"], c["b"]
        for r in te:
            cons = max(0.0, em._pred_ols(ols, r["fv"]))
            mod = max(-2.0, a + b * _predict(ridge, r["feats"])) if cal else _predict(ridge, r["feats"])
            recs.append((side, yr, (1 - lam) * cons + lam * mod, r["target"], r["fv"]))
    return recs


# --------------------------------------------------------------------------- metrics
def _rank(v):
    v = np.asarray(v, dtype=float)
    order = v.argsort(kind="mergesort")
    r = np.empty(len(v), dtype=float)
    r[order] = np.arange(1, len(v) + 1, dtype=float)
    # average ties
    s = v[order]
    i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[i]:
            j += 1
        if j > i:
            r[order[i:j + 1]] = (i + j) / 2.0 + 1
        i = j + 1
    return r


def _rho(p, t):
    if len(p) < 8:
        return None
    rp, rt = _rank(p), _rank(t)
    rp = rp - rp.mean()
    rt = rt - rt.mean()
    d = math.sqrt(float((rp * rp).sum()) * float((rt * rt).sum()))
    return float((rp * rt).sum() / d) if d > 0 else None


def _blocks(recs):
    b = {}
    for s, y, p, t, fv in recs:
        b.setdefault((s, y), []).append((p, t, fv))
    return b


def _pct(v):
    n = len(v)
    return (_rank(v) - 0.5) / n if n else np.array([])


def _auc(scores, labels):
    labels = np.asarray(labels, dtype=bool)
    npos, nneg = int(labels.sum()), int((~labels).sum())
    if npos == 0 or nneg == 0:
        return None
    r = _rank(scores)
    return float((r[labels].sum() - npos * (npos + 1) / 2.0) / (npos * nneg))


def metric(recs, kind):
    if not recs:
        return None
    if kind == "pooled_rho":
        return _rho([r[2] for r in recs], [r[3] for r in recs])
    bl = _blocks(recs)
    if kind == "fold_mean_rho":
        vals = [_rho([x[0] for x in g], [x[1] for x in g]) for g in bl.values() if len(g) >= 15]
        vals = [v for v in vals if v is not None]
        return float(np.mean(vals)) if vals else None
    # block-normalized pooling (side/year indicator absorbed)
    P, T, Y = [], [], []
    for g in bl.values():
        if len(g) < 8:
            continue
        P.append(_pct([x[0] for x in g]))
        T.append(_pct([x[1] for x in g]))
        Y.append(np.array([x[1] for x in g], dtype=float))
    if not P:
        return None
    P = np.concatenate(P); T = np.concatenate(T); Y = np.concatenate(Y)
    if kind == "block_rho":
        return _rho(P, T)
    if kind == "cauc":
        return _auc(P, Y >= CONTRIB)
    if kind == "sauc":
        return _auc(P, Y >= STAR)
    if kind == "prec20":
        sel = P >= 0.80
        return float((Y[sel] >= CONTRIB).mean()) if sel.sum() else None
    raise ValueError(kind)


# --------------------------------------------------------------------------- evaluators
# (name, sides, origins, train_frame, test_frame, metric)
EVALS = [
    ("EV0_current_gate",        ("hit",),        ORIGINS_GATE, "debuted", "debuted", "pooled_rho"),
    ("EV1_hit_9origin",         ("hit",),        ORIGINS_ALL,  "debuted", "debuted", "pooled_rho"),
    ("EV2_hit_9origin_foldmean",("hit",),        ORIGINS_ALL,  "debuted", "debuted", "fold_mean_rho"),
    ("EV3_hit_9origin_blockrho",("hit",),        ORIGINS_ALL,  "debuted", "debuted", "block_rho"),
    ("EV4_both_4origin_blockrho",("hit","pit"),  ORIGINS_GATE, "debuted", "debuted", "block_rho"),
    ("EV5_both_9origin_blockrho",("hit","pit"),  ORIGINS_ALL,  "debuted", "debuted", "block_rho"),
    ("EV6_both_9origin_pooledraw",("hit","pit"), ORIGINS_ALL,  "debuted", "debuted", "pooled_rho"),
    ("EV7_both_9origin_cauc",   ("hit","pit"),   ORIGINS_ALL,  "debuted", "debuted", "cauc"),
    ("EV8_both_9origin_sauc",   ("hit","pit"),   ORIGINS_ALL,  "debuted", "debuted", "sauc"),
    ("EV9_both_9origin_prec20", ("hit","pit"),   ORIGINS_ALL,  "debuted", "debuted", "prec20"),
    ("EV10_prodfit_testdeb",    ("hit","pit"),   ORIGINS_ALL,  "fullpool","debuted", "block_rho"),
    ("EV11_prodfit_testfull",   ("hit","pit"),   ORIGINS_ALL,  "fullpool","fullpool","block_rho"),
    ("EV12_prodfit_testfull_cauc",("hit","pit"), ORIGINS_ALL,  "fullpool","fullpool","cauc"),
]
FRAMES = sorted({(e[3], e[4]) for e in EVALS})


def all_records(pool, arm_keys):
    """{(train_frame,test_frame,side): recs} for one arm."""
    out = {}
    for tf, sf in FRAMES:
        for side in ("hit", "pit"):
            out[(tf, sf, side)] = score_records(pool[side], side, arm_keys[side],
                                                ORIGINS_ALL, tf, sf)
    return out


def eval_all(recmap):
    res = {}
    for name, sides, origins, tf, sf, mk in EVALS:
        recs = [r for side in sides for r in recmap[(tf, sf, side)] if r[1] in origins]
        res[name] = metric(recs, mk)
    return res


def eval_ns(recmap):
    ns = {}
    for name, sides, origins, tf, sf, mk in EVALS:
        ns[name] = len([r for side in sides for r in recmap[(tf, sf, side)] if r[1] in origins])
    return ns


# --------------------------------------------------------------------------- bootstrap
def resample(pool, rng, mode):
    out = {}
    for side, rows in pool.items():
        if mode == "strat":       # cluster/blocked on decision-year cohort (sizes preserved)
            by = {}
            for r in rows:
                by.setdefault(r["decision_year"], []).append(r)
            new = []
            for _y, g in by.items():
                new.extend(g[rng.randrange(len(g))] for _ in g)
            out[side] = new
        else:                     # plain player bootstrap within side
            out[side] = [rows[rng.randrange(len(rows))] for _ in rows]
    return out


def main(B=200):
    t0 = time.time()
    pool = load_pool()
    print("pool sizes", {s: len(v) for s, v in pool.items()}, flush=True)

    # --- point estimates on the real data
    point = {}
    recmaps = {}
    for arm, keys in ARMS.items():
        recmaps[arm] = all_records(pool, keys)
        point[arm] = eval_all(recmaps[arm])
    ns = eval_ns(recmaps["base"])
    print("\n== n per evaluator ==")
    for k, v in ns.items():
        print(f"  {k:32s} n={v}")
    print("\n== point metric (base arm) ==")
    for k in ns:
        print(f"  {k:32s} {point['base'][k]}")
    print(f"[{time.time()-t0:.0f}s] point done", flush=True)

    # --- current-gate reproduction check (uncalibrated blend, exactly _run_eval's row)
    rec0 = score_records(pool["hit"], "hit", BASE_KEYS["hit"], ORIGINS_GATE,
                         "debuted", "debuted", cal=False)
    print("REPRO current gate blend rho (uncal) =", round(_rho([r[2] for r in rec0],
                                                               [r[3] for r in rec0]), 4),
          "n =", len(rec0), flush=True)

    # --- oracle-injection slope: common effect axis across metrics
    def inject(recmap, eps, rng):
        out = {}
        for k, recs in recmap.items():
            bl = _blocks(recs)
            new = []
            for (s, y), g in bl.items():
                p = np.array([x[0] for x in g]); t = np.array([x[1] for x in g])
                fv = [x[2] for x in g]
                if len(g) < 3:
                    new.extend((s, y, x[0], x[1], x[2]) for x in g)
                    continue
                rp, rt = _pct(p), _pct(t)
                mix = (1 - eps) * rp + eps * rt
                srt = np.sort(p)
                pos = np.clip(mix * (len(p) - 1), 0, len(p) - 1)
                lo = np.floor(pos).astype(int); hi = np.minimum(len(p) - 1, lo + 1)
                newp = srt[lo] * (1 - (pos - lo)) + srt[hi] * (pos - lo)
                new.extend((s, y, float(newp[i]), float(t[i]), fv[i]) for i in range(len(g)))
            out[k] = new
        return out

    slopes = {}
    for eps in (0.05, 0.10):
        inj = eval_all(inject(recmaps["base"], eps, None))
        for k in ns:
            if point["base"][k] is None or inj[k] is None:
                continue
            slopes.setdefault(k, {})[eps] = (inj[k] - point["base"][k]) / eps
    print("\n== injection slope d(metric)/d(eps) ==")
    for k in ns:
        print(f"  {k:32s} {slopes.get(k)}")

    # --- INDEPENDENT null band: 24 zero-information features, real refits, real data.
    # sd of these point deltas is a bootstrap-free estimate of the evaluator's noise floor.
    NSEED = 24
    nullband = {k: [] for k in ns}
    for si in range(NSEED):
        r2 = random.Random(90000 + si)
        for side in ("hit", "pit"):
            for row in pool[side]:
                row["feats"]["_noise"] = r2.gauss(0.0, 1.0)
        rr = eval_all(all_records(pool, ARMS["noise"]))
        for k in ns:
            if rr[k] is not None and point["base"][k] is not None:
                nullband[k].append(rr[k] - point["base"][k])
    print(f"\n== NULL BAND ({NSEED} zero-information features, refit, real data) ==")
    print(f"{'evaluator':32s} {'mean_d':>9s} {'sd_null':>9s} {'max|d|':>9s}")
    for k in ns:
        v = np.array(nullband[k])
        print(f"{k:32s} {v.mean():>9.5f} {v.std(ddof=1):>9.5f} {np.abs(v).max():>9.5f}")
    out_null = {k: {"mean": round(float(np.mean(nullband[k])), 5),
                    "sd": round(float(np.std(nullband[k], ddof=1)), 5),
                    "max_abs": round(float(np.abs(nullband[k]).max()), 5)} for k in ns}
    # restore the primary noise feature
    rng0 = random.Random(20260724)
    for side in ("hit", "pit"):
        for row in pool[side]:
            row["feats"]["_noise"] = rng0.gauss(0.0, 1.0)
    print(f"[{time.time()-t0:.0f}s] null band done", flush=True)

    # --- paired refit bootstrap
    boots = {mode: {arm: {k: [] for k in ns} for arm in ARMS} for mode in ("strat", "plain")}
    for mode in ("strat", "plain"):
        rng = random.Random(4242)
        for b in range(B):
            rp = resample(pool, rng, mode)
            for arm, keys in ARMS.items():
                r = eval_all(all_records(rp, keys))
                for k in ns:
                    boots[mode][arm][k].append(r[k])
            if (b + 1) % 20 == 0:
                print(f"[{time.time()-t0:.0f}s] {mode} boot {b+1}/{B}", flush=True)

    # --- test-only bootstrap (naive: fit fixed, resample scored records)
    testonly = {arm: {k: [] for k in ns} for arm in ARMS}
    rng = random.Random(99)
    for b in range(B):
        idx = {}
        for key, recs in recmaps["base"].items():
            idx[key] = [rng.randrange(len(recs)) for _ in recs] if recs else []
        for arm in ARMS:
            rm = {key: [recmaps[arm][key][i] for i in ii] for key, ii in idx.items()}
            r = eval_all(rm)
            for k in ns:
                testonly[arm][k].append(r[k])

    # --- summarize
    def summ(vals_c, vals_b, pt_c, pt_b):
        pair = [(c, bb) for c, bb in zip(vals_c, vals_b) if c is not None and bb is not None]
        if len(pair) < 10:
            return None
        c = np.array([x[0] for x in pair]); bb = np.array([x[1] for x in pair])
        d = c - bb
        sd_a = float(bb.std(ddof=1)); sd_c = float(c.std(ddof=1))
        corr = float(np.corrcoef(c, bb)[0, 1]) if sd_a > 0 and sd_c > 0 else None
        unpaired = math.sqrt(sd_a ** 2 + sd_c ** 2)
        return {"delta": round(pt_c - pt_b, 5) if (pt_c is not None and pt_b is not None) else None,
                "sd": round(float(d.std(ddof=1)), 5),
                "sd_arm_base": round(sd_a, 5), "sd_arm_cand": round(sd_c, 5),
                "arm_corr": round(corr, 4) if corr is not None else None,
                "sd_unpaired": round(unpaired, 5),
                "pairing_gain_x": round(unpaired / float(d.std(ddof=1)), 2) if d.std(ddof=1) > 0 else None,
                "ci95": [round(float(np.percentile(d, 2.5)), 5),
                         round(float(np.percentile(d, 97.5)), 5)],
                "p_gt0": round(float((d > 0).mean()), 3)}

    out = {"n": ns, "point": point, "slopes": slopes, "B": B,
           "null_band": out_null, "summary": {}}
    print("\n" + "=" * 130)
    for arm in ("noise", "prod_trend", "drop_peakk"):
        print(f"\n### candidate = {arm}  (vs base)")
        print(f"{'evaluator':32s} {'delta':>9s} {'sd_strat':>9s} {'sd_plain':>9s} "
              f"{'sd_tonly':>9s} {'x_under':>7s} {'sd_arm':>8s} {'pairx':>6s} "
              f"{'|d|/sd':>7s} {'MDE':>8s} {'MDE_eps':>8s}")
        for k in ns:
            s_st = summ(boots["strat"][arm][k], boots["strat"]["base"][k], point[arm][k], point["base"][k])
            s_pl = summ(boots["plain"][arm][k], boots["plain"]["base"][k], point[arm][k], point["base"][k])
            s_to = summ(testonly[arm][k], testonly["base"][k], point[arm][k], point["base"][k])
            if not s_st:
                continue
            sd = s_st["sd"]
            mde = 2.49 * sd
            sl = (slopes.get(k) or {}).get(0.10)
            mde_eps = (mde / sl) if sl else None
            ratio = round(sd / s_to["sd"], 2) if s_to and s_to["sd"] else None
            snr = abs(s_st["delta"]) / sd if sd else None
            print(f"{k:32s} {s_st['delta']:>9.5f} {sd:>9.5f} {s_pl['sd']:>9.5f} "
                  f"{s_to['sd']:>9.5f} {str(ratio):>7s} {s_st['sd_arm_base']:>8.5f} "
                  f"{str(s_st['pairing_gain_x']):>6s} "
                  f"{(round(snr,2) if snr else 0):>7} {mde:>8.4f} "
                  f"{(round(mde_eps,4) if mde_eps else float('nan')):>8}")
            out["summary"].setdefault(arm, {})[k] = {
                "strat": s_st, "plain": s_pl, "test_only": s_to,
                "mde_95_80": round(mde, 5), "mde_eps": round(mde_eps, 5) if mde_eps else None,
                "sd_understatement_x": ratio}
    outp = ROOT / "tools" / "_frontier_out" / "_scratch_evalpower.json"
    outp.parent.mkdir(exist_ok=True)
    outp.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\nwrote", outp, f"[{time.time()-t0:.0f}s]")


if __name__ == "__main__":
    main(B=int(sys.argv[1]) if len(sys.argv) > 1 else 200)
