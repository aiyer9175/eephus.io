"""R_BAKEOFF lab: the three R bake-offs of docs/r/R_BAKEOFF.md, each read once.

R is an OFFLINE fitting tool here (registration section 0). This lab builds each item's frame in
Python, hands the fits to R through tools/rbridge.py (JSON in, JSON out), and scores every rater
in Python. Nothing served moves: the only outputs are the development artifacts under
data/_labs/r_bakeoff/ (off the webroot) and what the caller prints.

    python tools/r_bakeoff_lab.py --item aging --dry-run --out <scratch>/aging_dry.json
    python tools/r_bakeoff_lab.py --item aging --read
    (items: aging, xm, efv; efv also needs --x3-cache <a private copy of X3's cache dir>)

Bans (registration section 2): development frames only; no reserved eFV frame; xM$ class years
2025 and 2026 never built; nothing grouped or stratified by consensus-FV level;
backtest.run_backtest never run; the shared .cache never written (fit_cache_read_only).
"""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import pickle
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import rbridge  # noqa: E402

DOC = "docs/r/R_BAKEOFF.md"
OUT_DIR = ROOT / "data" / "_labs" / "r_bakeoff"
ARTIFACT = {"aging": OUT_DIR / "aging_gam.json", "xm": OUT_DIR / "xm_years_surv.json",
            "efv": OUT_DIR / "efv_glmm.json"}
SEED = 20261022

# item (a)
AGING_LABELS = (2008, 2009, 2010, 2011)
AGING_B = 2000
AGING_ALPHA = 0.025            # one-sided 97.5 percent bounds (Bonferroni over two sides)
AGING_CURVE_AGES = tuple(range(21, 44))
AGING_PLANT_AGES = tuple(range(23, 36))
AGING_PLANT_RMSE = 0.10
AGING_PLANT_PLAYER_SD = 0.15
AGE_BANDS = ((0, 24, "24-"), (25, 27, "25-27"), (28, 30, "28-30"), (31, 33, "31-33"),
             (34, 99, "34+"))

# item (b)
XM_WINTERS = tuple(range(2018, 2025))
XM_FIRST, XM_LAST = 2015, 2024          # 2025 and 2026 (the xM$ holdout) are never built
XM_WARMUP = (2015, 2016, 2017)
XM_B = 4000
XM_ALPHA = 0.05
XM_ORACLE_RATIO = 1.10
XM_PERM_SEED = 20261023
XM_FEATURE_NAMES = ("age", "w1", "w1sq", "age_w1", "is_SP", "is_RP", "is_C", "qo", "comps_my",
                    "prime", "comps_my75", "qo_prime_w1", "age_SP", "age_RP")
XM_LABEL_FREE = frozenset({"age", "w1", "w1sq", "age_w1", "is_SP", "is_RP", "is_C", "qo",
                           "prime", "qo_prime_w1", "age_SP", "age_RP"})

# item (c)
EFV_B = 4000
EFV_SEED = 20261020
EFV_PERM_SEEDS = tuple(range(20261024, 20261044))
EFV_PLANT_SEED = 20261044
EFV_PLANT_Q = 0.25
EFV_PLANT_R = 0.30
EFV_PLANT_CORR = 0.70
EFV_PARITY_TOL = 1e-9


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(*args) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _rnd(v, d=5):
    if v is None:
        return None
    v = float(v)
    return None if not math.isfinite(v) else round(v, d)


# ---------------------------------------------------------------------------
# shared: the read-only fit cache, the read-once guard, the bootstrap, the verdict words
# ---------------------------------------------------------------------------

class CacheWriteRefused(RuntimeError):
    pass


@contextlib.contextmanager
def fit_cache_read_only():
    """fa_projection's fit and corpus caches are READ, never written: a cache miss refits in
    memory (use_cache=False) and saves nothing (registration section 2)."""
    import fa_projection as fp

    class _Shim:
        load = staticmethod(pickle.load)
        loads = staticmethod(pickle.loads)
        HIGHEST_PROTOCOL = pickle.HIGHEST_PROTOCOL

        @staticmethod
        def dump(*_a, **_k):
            raise CacheWriteRefused("the shared .cache is read-only in this lab")

        dumps = staticmethod(pickle.dumps)

    orig_pickle = fp.pickle
    orig_fitted = fp.fitted_models

    def fitted_ro(corpus, max_season, use_cache=True, **kw):
        try:
            return orig_fitted(corpus, max_season, use_cache=use_cache, **kw)
        except CacheWriteRefused:
            return orig_fitted(corpus, max_season, use_cache=False, **kw)

    fp.pickle = _Shim
    fp.fitted_models = fitted_ro
    try:
        yield
    finally:
        fp.pickle = orig_pickle
        fp.fitted_models = orig_fitted


def refuse_second_read(item: str) -> None:
    p = ARTIFACT[item]
    if p.exists():
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            doc = {}
        if doc.get("read_done"):
            raise SystemExit(f"refused: {p.name} already records the one read")


def cluster_draws(clusters, B: int, seed: int):
    """Yield B multiplicity vectors (rows weighted by how often their cluster was drawn)."""
    keys = list(dict.fromkeys(clusters))
    idx = {k: i for i, k in enumerate(keys)}
    inv = np.asarray([idx[c] for c in clusters], dtype=np.int64)
    nc = len(keys)
    rng = np.random.default_rng(int(seed))
    for _ in range(int(B)):
        cnt = np.bincount(rng.integers(0, nc, nc), minlength=nc).astype(np.float64)
        yield cnt[inv]


def boot_mae(err: dict, w: np.ndarray, clusters, B: int, seed: int) -> dict:
    """{rater: array of B weighted MAEs}, paired over the same draws."""
    out = {k: np.empty(B) for k in err}
    for b, m in enumerate(cluster_draws(clusters, B, seed)):
        mw = m * w
        den = mw.sum()
        for k, e in err.items():
            out[k][b] = (mw * e).sum() / den
    return out


def wmae(e: np.ndarray, w: np.ndarray) -> float:
    return float((w * e).sum() / w.sum())


def diff_summary(draws: np.ndarray, alpha: float) -> dict:
    q = np.quantile(draws, [alpha, 0.025, 0.975, 1.0 - alpha])
    return {"lb": _rnd(q[0]), "ub": _rnd(q[3]), "ci95": [_rnd(q[1]), _rnd(q[2])],
            "sd": _rnd(draws.std(ddof=1)), "mde": _rnd(1.645 * draws.std(ddof=1)),
            "p_gt_0": _rnd((draws > 0).mean(), 4)}


def tie_word(ci: dict) -> str:
    if ci["lb"] is not None and ci["lb"] > 0:
        return "beats"
    if ci["ub"] is not None and ci["ub"] < 0:
        return "trails"
    return "ties"


# ---------------------------------------------------------------------------
# item (a): aging curves
# ---------------------------------------------------------------------------

def aging_pairs(corpus: dict) -> list[dict]:
    """Every pair (player, side, t) of the fit's own definition (fit_aging_curves): exposure at
    the floor in t and t + 1, ages inside age_range, the regressed WAR rate at both seasons."""
    import fa_projection as fp
    cfg = fp._pcfg()
    a_lo, a_hi = cfg["age_range"]
    reg_k = cfg.get("war_rate_regression") or {"hit_pa": 600, "pit_bf": 350}
    out = []
    for side, rows, expo_key, min_expo in (
            ("hit", corpus["hit"], "pa", cfg["min_exposure_pair"]["pa"]),
            ("pit", corpus["pit"], "bf", cfg["min_exposure_pair"]["bf"])):
        rows = [r for r in rows if r.get("age") and a_lo <= r["age"] <= a_hi]
        per = 600.0 if side == "hit" else 250.0
        k_reg = float(reg_k["hit_pa"] if side == "hit" else reg_k["pit_bf"])
        acc_w: dict = {}
        acc_e: dict = {}
        for r in rows:
            if r.get("war") is not None and (r.get(expo_key) or 0) > 0:
                acc_w[r["season"]] = acc_w.get(r["season"], 0.0) + r["war"]
                acc_e[r["season"]] = acc_e.get(r["season"], 0.0) + r[expo_key]
        lg = {s: acc_w[s] / e * per for s, e in acc_e.items() if e > 0}
        by_player: dict = {}
        for r in rows:
            if r.get("mlbam") is not None:
                by_player.setdefault(r["mlbam"], {})[r["season"]] = r

        def val(r):
            w, e = r.get("war"), r.get(expo_key) or 0
            if w is None or e < min_expo:
                return None
            return (w / e * per * e + lg.get(r["season"], 0.0) * k_reg) / (e + k_reg)

        for pid, seasons in by_player.items():
            for s, r in seasons.items():
                nxt = seasons.get(s + 1)
                if not nxt or s + 1 == 2020:
                    continue
                v0, v1 = val(r), val(nxt)
                if v0 is None or v1 is None:
                    continue
                base = ("C" if r["role"] == "C" else "H") if side == "hit" else r["role"]
                prof = fp._row_profile(r, side, corpus["league"])
                out.append({"side": side, "pid": int(pid), "t": int(s), "L": int(s) + 1,
                            "age1": int(r["age"]) + 1, "role": base,
                            "role_key": f"{base}|{prof}" if prof else base,
                            "v0": v0, "v1": v1, "dv": v1 - v0,
                            "w": 2.0 / (1.0 / r[expo_key] + 1.0 / nxt[expo_key])})
    return out


def aging_inc(corpus: dict, pairs: list[dict], L: int, *, lam0: bool = False) -> np.ndarray:
    """The served curve's predicted v(t + 1) on `pairs` (label season L), refit with
    max_season = L - 1; lam0 sets the survivorship lambda to 0 (a reported diagnostic)."""
    import fa_projection as fp
    orig = fp._pcfg
    if lam0:
        fp._pcfg = lambda: {**orig(), "survivorship_lambda": 0.0}
    try:
        curves = fp.fit_aging_curves(corpus, max_season=L - 1, write=False)
    finally:
        fp._pcfg = orig
    return np.asarray([p["v0"] + fp.curve_delta(curves, p["side"], p["role_key"], "war_rate",
                                                 p["age1"]) for p in pairs])


def aging_gam_jobs(pairs: list[dict], dv: np.ndarray, labels, ref_role: dict) -> list[dict]:
    jobs = []
    for L in labels:
        for side in ("hit", "pit"):
            tr = [i for i, p in enumerate(pairs) if p["side"] == side and p["L"] <= L - 1]
            te = [i for i, p in enumerate(pairs) if p["side"] == side and p["L"] == L]
            if not te:
                continue
            jobs.append({"id": f"{L}|{side}",
                         "train": {"dv": [float(dv[i]) for i in tr],
                                   "age1": [pairs[i]["age1"] for i in tr],
                                   "role": [pairs[i]["role"] for i in tr],
                                   "pid": [str(pairs[i]["pid"]) for i in tr],
                                   "w": [pairs[i]["w"] for i in tr]},
                         "test": {"age1": [pairs[i]["age1"] for i in te],
                                  "role": [pairs[i]["role"] for i in te],
                                  "pid": [str(pairs[i]["pid"]) for i in te]},
                         "test_idx": te, "ages": list(AGING_CURVE_AGES),
                         "ref_role": ref_role[side]})
    return jobs


def run_gam(pairs, dv, labels, ref_role, work: Path | None = None) -> dict:
    jobs = aging_gam_jobs(pairs, dv, labels, ref_role)
    payload = {"jobs": [{k: v for k, v in j.items() if k != "test_idx"} for j in jobs]}
    res = rbridge.run_r("aging_gam.R", payload, workdir=work)
    pred_dv = np.full(len(pairs), np.nan)
    per = {}
    for j in jobs:
        r = res["jobs"][j["id"]]
        pred_dv[j["test_idx"]] = np.asarray(r["pred"], dtype=float)
        per[j["id"]] = {"curve": dict(zip([int(a) for a in r["ages"]], r["curve"])),
                        "sd_pid": r.get("sd_pid"), "n_train": r["n_train"],
                        "n_players": r["n_players"], "n_test": len(j["test_idx"]),
                        "n_test_seen": r["n_test_seen"], "edf_age": r.get("edf_age"),
                        "ref_role": r["ref_role"]}
    return {"pred_dv": pred_dv, "per_fold": per, "mgcv": res.get("mgcv")}


def aging_score(pairs, scored, preds: dict, v1: np.ndarray, *, B: int, seed: int) -> dict:
    """Per side: weighted MAE of every rater, the paired D's against the GAM, age bands."""
    out = {}
    for side in ("hit", "pit"):
        ix = np.asarray([i for i in scored if pairs[i]["side"] == side])
        w = np.asarray([pairs[i]["w"] for i in ix])
        cl = [pairs[i]["pid"] for i in ix]
        err = {k: np.abs(p[ix] - v1[ix]) for k, p in preds.items()}
        mae = {k: _rnd(wmae(e, w)) for k, e in err.items()}
        draws = boot_mae(err, w, cl, B, seed)
        ds = {}
        for k in preds:
            if k == "GAM":
                continue
            ds[k] = {"delta": _rnd(wmae(err[k], w) - wmae(err["GAM"], w)),
                     **diff_summary(draws[k] - draws["GAM"], AGING_ALPHA)}
        bands = {}
        a1 = np.asarray([pairs[i]["age1"] for i in ix])
        for lo, hi, nm in AGE_BANDS:
            m = (a1 >= lo) & (a1 <= hi)
            if m.any():
                bands[nm] = {"n": int(m.sum()), **{k: _rnd(wmae(e[m], w[m])) for k, e in err.items()}}
        out[side] = {"n": int(ix.size), "n_players": len(set(cl)), "mae": mae, "D": ds,
                     "by_age_band": bands}
    return out


def aging_verdict(score: dict, planted: dict) -> dict:
    out = {}
    for side in ("hit", "pit"):
        d = score[side]["D"]
        c1 = d["INC"]["lb"] is not None and d["INC"]["lb"] > 0
        c2 = d["N0"]["lb"] is not None and d["N0"]["lb"] > 0
        c3 = d["N1"]["lb"] is not None and d["N1"]["lb"] > 0
        c4 = bool(planted.get(side, {}).get("pass"))
        ok = c1 and c2 and c3 and c4
        word = "PASS" if ok else f"FAIL ({tie_word(d['INC'])} the served curve)"
        if not c4:
            word += ", UNRESOLVED (planted check failed)"
        out[side] = {"verdict": word, "pass": ok, "c1_beats_inc": c1, "c2_beats_n0": c2,
                     "c3_beats_n1": c3, "c4_planted": c4}
    return out


def aging_planted(pairs, labels, ref_role, *, B: int, seed: int, work=None) -> dict:
    """Section 3 check (4): a planted curve plus a player effect plus noise on the real design."""
    rng = np.random.default_rng(int(seed))
    dv_real = np.asarray([p["dv"] for p in pairs])
    w_all = np.asarray([p["w"] for p in pairs])
    dv = np.empty(len(pairs))
    truth = {}
    for side in ("hit", "pit"):
        ix = np.asarray([i for i, p in enumerate(pairs) if p["side"] == side])
        tr0 = np.asarray([i for i in ix if pairs[i]["L"] <= labels[0] - 1])
        ww = w_all[tr0]
        mu = float((ww * dv_real[tr0]).sum() / ww.sum())
        s = math.sqrt(float((ww * (dv_real[tr0] - mu) ** 2).sum() / ww.sum()))
        pids = sorted({pairs[i]["pid"] for i in ix})
        b = dict(zip(pids, rng.normal(0.0, AGING_PLANT_PLAYER_SD, len(pids))))
        w_rel = w_all[ix] / w_all[ix].mean()
        f = np.asarray([0.30 - 0.06 * (pairs[i]["age1"] - 26) for i in ix])
        e = rng.normal(0.0, 1.0, ix.size) * s / np.sqrt(w_rel)
        dv[ix] = f + np.asarray([b[pairs[i]["pid"]] for i in ix]) + e
        truth[side] = {"noise_sd": _rnd(s), "n_players": len(pids)}
    v0 = np.asarray([p["v0"] for p in pairs])
    v1 = v0 + dv
    g = run_gam(pairs, dv, labels, ref_role, work)
    scored = [i for i, p in enumerate(pairs) if p["L"] in labels]
    preds = {"GAM": v0 + g["pred_dv"], "N0": v0.copy()}
    n1 = np.full(len(pairs), np.nan)
    for L in labels:
        for side in ("hit", "pit"):
            tr = [i for i, p in enumerate(pairs) if p["side"] == side and p["L"] <= L - 1]
            te = [i for i, p in enumerate(pairs) if p["side"] == side and p["L"] == L]
            n1[te] = v0[te] + float((w_all[tr] * dv[tr]).sum() / w_all[tr].sum())
    preds["N1"] = n1
    sc = aging_score(pairs, scored, preds, v1, B=B, seed=seed)
    out = {}
    for side in ("hit", "pit"):
        rmse = {}
        for L in labels:
            cv = g["per_fold"][f"{L}|{side}"]["curve"]
            rmse[str(L)] = _rnd(math.sqrt(statistics.mean(
                (cv[a] - (0.30 - 0.06 * (a - 26))) ** 2 for a in AGING_PLANT_AGES)), 4)
        d = sc[side]["D"]
        ok = (all(v is not None and v <= AGING_PLANT_RMSE for v in rmse.values())
              and d["N0"]["lb"] > 0 and d["N1"]["lb"] > 0)
        out[side] = {"pass": bool(ok), "curve_rmse_by_fold": rmse, "D_N0": d["N0"],
                     "D_N1": d["N1"], "mae": sc[side]["mae"], **truth[side]}
    return out


def aging_read(pairs, corpus, labels, *, B: int, seed: int, work=None, log=print) -> dict:
    scored = [i for i, p in enumerate(pairs) if p["L"] in labels]
    ref_role = {}
    for side in ("hit", "pit"):
        roles = [p["role"] for p in pairs if p["side"] == side and p["L"] <= labels[0] - 1]
        ref_role[side] = max(set(roles), key=roles.count)
    t0 = time.time()
    planted = aging_planted(pairs, labels, ref_role, B=B, seed=seed, work=work)
    log(f"  planted: hit {planted['hit']['pass']} pit {planted['pit']['pass']} "
        f"({round(time.time() - t0, 1)} s)")
    v0 = np.asarray([p["v0"] for p in pairs])
    v1 = np.asarray([p["v1"] for p in pairs])
    dv = np.asarray([p["dv"] for p in pairs])
    w_all = np.asarray([p["w"] for p in pairs])
    inc = np.full(len(pairs), np.nan)
    inc0 = np.full(len(pairs), np.nan)
    n1 = np.full(len(pairs), np.nan)
    for L in labels:
        te = [i for i in scored if pairs[i]["L"] == L]
        sub = [pairs[i] for i in te]
        if corpus is not None:
            inc[te] = aging_inc(corpus, sub, L)
            inc0[te] = aging_inc(corpus, sub, L, lam0=True)
        else:   # fixtures: the incumbent is a known curve
            inc[te] = [p["v0"] + p.get("inc_delta", 0.0) for p in sub]
            inc0[te] = inc[te]
        for side in ("hit", "pit"):
            tr = [i for i, p in enumerate(pairs) if p["side"] == side and p["L"] <= L - 1]
            tes = [i for i in te if pairs[i]["side"] == side]
            n1[tes] = v0[tes] + float((w_all[tr] * dv[tr]).sum() / w_all[tr].sum())
    g = run_gam(pairs, dv, labels, ref_role, work)
    preds = {"GAM": v0 + g["pred_dv"], "INC": inc, "N0": v0.copy(), "N1": n1,
             "INC_lambda0": inc0}
    sc = aging_score(pairs, scored, preds, v1, B=B, seed=seed)
    return {"planted": planted, "score": sc, "verdict": aging_verdict(sc, planted),
            "gam_folds": g["per_fold"], "ref_role": ref_role, "mgcv": g["mgcv"],
            "frame": {"label_seasons": list(labels), "n_pairs_total": len(pairs),
                      "n_scored": len(scored)}}


def aging_fixture(seed: int = 7) -> list[dict]:
    """Synthetic pairs: two sides, players over seasons 2000 to 2011, a known curve."""
    rng = np.random.default_rng(seed)
    out = []
    for side, roles in (("hit", ("H", "C")), ("pit", ("SP", "RP"))):
        for pid in range(260):
            age = int(rng.integers(21, 33))
            t0 = int(rng.integers(2000, 2009))
            v = float(rng.normal(1.0, 1.0))
            b = float(rng.normal(0, 0.2))
            for t in range(t0, min(2011, t0 + 6)):
                a1 = age + (t - t0) + 1
                dvv = 0.2 - 0.05 * (a1 - 27) + b + float(rng.normal(0, 0.6))
                out.append({"side": side, "pid": pid + (0 if side == "hit" else 10000), "t": t,
                            "L": t + 1, "age1": a1, "role": roles[pid % 2], "role_key": roles[pid % 2],
                            "v0": v, "v1": v + dvv, "dv": dvv, "w": float(rng.uniform(100, 600)),
                            "inc_delta": 0.1 - 0.04 * (a1 - 27)})
                v += dvv
    return out


def item_aging(args, log) -> dict:
    if args.dry_run:
        pairs = aging_fixture()
        res = aging_read(pairs, None, AGING_LABELS, B=200, seed=SEED, log=log)
        return {"item": "aging", "dry_run": True, "generated": _now(), **res}
    import fa_projection as fp
    with fit_cache_read_only():
        corpus = fp.build_corpus()
        if corpus.get("war_provider") != "fwar":
            raise SystemExit("BLOCKER: other the corpus is not on the fWAR label")
        pairs = [p for p in aging_pairs(corpus) if p["L"] <= max(AGING_LABELS)]
        res = aging_read(pairs, corpus, AGING_LABELS, B=AGING_B, seed=SEED, log=log)
    return {"item": "aging", "dry_run": False, "generated": _now(),
            "corpus": {"war_provider": corpus.get("war_provider"), "first": corpus["first"],
                       "last": corpus["last"], "sig": fp._corpus_sig(corpus)}, **res}


# ---------------------------------------------------------------------------
# item (b): xM$ contract years as an interval-censored duration
# ---------------------------------------------------------------------------

def xm_features(model, s: dict) -> list[float]:
    import fa_market as fm
    cs = model._comps_stats(s)
    return [float(x) for x in fm._features_years(s, cs[0], cs[3])[1:]]


def xm_pipeline(rows: list[dict], *, work=None, log=print, with_inc: bool = True) -> dict:
    """Every development winter: the incumbent, the two nulls and SURV on the scored rows."""
    import fa_market as fm
    jobs, recs, meta = [], [], {}
    for W in XM_WINTERS:
        train = [s for s in rows if s["class_year"] < W]
        test = [s for s in rows if s["class_year"] == W]
        if len(train) < 100 or not test:
            continue
        model = fm.MarketModel(train, fm.dollars_per_war_by_winter(train))
        model.supply_by_year[W] = fm._supply(test, W)
        Xtr = np.asarray([xm_features(model, s) for s in model.train_pool])
        ytr = np.asarray([float(s["years"]) for s in model.train_pool])
        med_c = float(statistics.median(ytr))
        scored = []
        for s in test:
            comps = fm.comps_for(s, train)
            if not comps:
                continue
            rec = {"W": W, "key": s.get("player_key") or s["player_name"],
                   "y": float(s["years"]), "N_C": med_c,
                   "N_K": float(statistics.median(c["years"] for c in comps)),
                   "x": xm_features(model, s)}
            if with_inc:
                rec["INC"] = float(model.predict(s)["proj_years"])
            scored.append(rec)
        if not scored:
            continue
        mu, sd = Xtr.mean(axis=0), Xtr.std(axis=0)
        keep = sd > 1e-12
        z = lambda X: ((np.asarray(X) - mu) / np.where(keep, sd, 1.0))[:, keep]  # noqa: E731
        jobs.append({"id": str(W), "train_x": z(Xtr).tolist(), "train_y": ytr.tolist(),
                     "test_x": z([r["x"] for r in scored]).tolist()})
        meta[str(W)] = {"n_train": int(len(ytr)), "n_scored": len(scored), "n_test": len(test),
                        "dropped_constant": [XM_FEATURE_NAMES[i] for i in np.flatnonzero(~keep)]}
        recs.extend(scored)
    res = rbridge.run_r("xm_years_surv.R", {"jobs": jobs}, workdir=work)
    by_w = {}
    for r in recs:
        by_w.setdefault(str(r["W"]), []).append(r)
    for wk, rr in by_w.items():
        j = res["jobs"][wk]
        meta[wk]["dist"] = j["dist"]
        for r, m in zip(rr, j["median"]):
            r["SURV"] = float(min(15, max(1, math.ceil(m - 1e-9))))
            r["SURV_median_T"] = float(m)
    return {"rows": recs, "meta": meta, "flexsurv": res.get("flexsurv")}


def xm_score(recs: list[dict], raters, *, B: int, seed: int, ref: str = "SURV") -> dict:
    y = np.asarray([r["y"] for r in recs])
    w = np.ones(len(recs))
    err = {k: np.abs(np.asarray([r[k] for r in recs]) - y) for k in raters}
    draws = boot_mae(err, w, [r["key"] for r in recs], B, seed)
    out = {"n": len(recs), "n_players": len({r["key"] for r in recs}),
           "mae": {k: _rnd(wmae(e, w), 4) for k, e in err.items()},
           "exact": {k: _rnd(float((np.asarray([r[k] for r in recs]) == y).mean()), 4) for k in raters},
           "log_mae": {k: _rnd(float(np.mean(np.abs(np.log(np.maximum(np.asarray([r[k] for r in recs]), 1.0))
                                                    - np.log(y)))), 4) for k in raters},
           "D": {}}
    for k in raters:
        if k == ref:
            continue
        out["D"][k] = {"delta": _rnd(wmae(err[k], w) - wmae(err[ref], w), 4),
                       **diff_summary(draws[k] - draws[ref], XM_ALPHA)}
    per_w = {}
    for W in sorted({r["W"] for r in recs}):
        m = np.asarray([r["W"] == W for r in recs])
        per_w[str(W)] = {"n": int(m.sum()), **{k: _rnd(float(e[m].mean()), 4) for k, e in err.items()}}
    out["by_winter"] = per_w
    return out


def xm_planted(rows: list[dict], *, work=None, log=print) -> dict:
    """P1 (signal) and P2 (permuted null) on the real design (registration section 4)."""
    import fa_market as fm
    # the planted truth: a lognormal AFT on the warm-up rows' LABEL-FREE features
    warm = [s for s in rows if s["class_year"] in XM_WARMUP]
    model = fm.MarketModel(warm, fm.dollars_per_war_by_winter(warm))
    names = XM_FEATURE_NAMES[:len(xm_features(model, warm[0]))]
    lf_idx = [i for i, n in enumerate(names) if n in XM_LABEL_FREE]
    Xw = np.asarray([xm_features(model, s) for s in warm])[:, lf_idx]
    mu, sd = Xw.mean(axis=0), Xw.std(axis=0)
    keep = sd > 1e-12
    zf = lambda X: ((np.asarray(X) - mu) / np.where(keep, sd, 1.0))[:, keep]  # noqa: E731
    yw = np.asarray([float(s["years"]) for s in warm])
    tr = rbridge.run_r("xm_years_surv.R", {"jobs": [{"id": "truth", "mode": "fit_lnorm",
                                                       "train_x": zf(Xw).tolist(),
                                                       "train_y": yw.tolist(),
                                                       "test_x": zf(Xw[:1]).tolist()}]},
                       workdir=work)["jobs"]["truth"]
    beta = np.asarray(tr["beta"], dtype=float)
    rng = np.random.default_rng(SEED)
    sim = []
    for s in rows:
        x = np.asarray(xm_features(model, s))[lf_idx]
        eta = tr["meanlog"] + float(zf(x[None, :])[0] @ beta)
        t = math.exp(eta + tr["sdlog"] * float(rng.normal()))
        s2 = dict(s)
        s2["years"] = int(min(15, max(1, math.ceil(t))))
        s2["_oracle"] = float(min(15, max(1, math.ceil(math.exp(eta) - 1e-9))))
        sim.append(s2)
    p1 = xm_pipeline(sim, work=work, log=log, with_inc=False)
    orc = {(s["class_year"], s.get("player_key") or s["player_name"]): s["_oracle"] for s in sim}
    for r in p1["rows"]:
        r["ORACLE"] = orc[(r["W"], r["key"])]
    sc1 = xm_score(p1["rows"], ("SURV", "N_C", "ORACLE"), B=XM_B, seed=SEED)
    ratio = sc1["mae"]["SURV"] / max(sc1["mae"]["ORACLE"], 1e-9)
    p1_ok = ratio <= XM_ORACLE_RATIO and sc1["D"]["N_C"]["lb"] > 0
    # P2: actual years permuted within each class year
    rng2 = np.random.default_rng(XM_PERM_SEED)
    perm = []
    by_cy: dict = {}
    for s in rows:
        by_cy.setdefault(s["class_year"], []).append(s)
    for cy, rr in sorted(by_cy.items()):
        ys = [s["years"] for s in rr]
        order = rng2.permutation(len(ys))
        for s, j in zip(rr, order):
            s2 = dict(s)
            s2["years"] = ys[int(j)]
            perm.append(s2)
    p2 = xm_pipeline(perm, work=work, log=log, with_inc=False)
    sc2 = xm_score(p2["rows"], ("SURV", "N_C"), B=XM_B, seed=SEED)
    p2_ok = not (sc2["D"]["N_C"]["lb"] > 0)
    return {"P1": {"pass": bool(p1_ok), "surv_over_oracle": _rnd(ratio, 4), "score": sc1,
                   "truth": {"meanlog": _rnd(tr["meanlog"]), "sdlog": _rnd(tr["sdlog"]),
                             "features": [names[i] for i in lf_idx]},
                   "dists": {k: v.get("dist") for k, v in p1["meta"].items()}},
            "P2": {"pass": bool(p2_ok), "score": sc2,
                   "dists": {k: v.get("dist") for k, v in p2["meta"].items()}}}


def xm_verdict(sc: dict, planted: dict) -> dict:
    d = sc["D"]
    cs = {k: bool(d[k]["lb"] is not None and d[k]["lb"] > 0) for k in ("INC", "N_C", "N_K")}
    pl = bool(planted["P1"]["pass"] and planted["P2"]["pass"])
    ok = all(cs.values()) and pl
    word = "PASS" if ok else f"FAIL ({tie_word(d['INC'])} the served years stage)"
    if not pl:
        word += ", UNRESOLVED (a planted check failed)"
    return {"verdict": word, "pass": ok, "beats": cs, "planted": pl}


def xm_fixture(seed: int = 11) -> list[dict]:
    rng = np.random.default_rng(seed)
    out = []
    for cy in range(XM_FIRST, XM_LAST + 1):
        for j in range(60):
            x = rng.normal(size=4)
            t = math.exp(0.4 + 0.5 * x[0] + 0.5 * rng.normal())
            out.append({"W": cy, "key": f"p{cy}_{j}", "y": float(min(15, max(1, math.ceil(t)))),
                        "x": x.tolist(), "N_C": 1.0, "N_K": float(min(15, max(1, round(math.exp(0.4 + 0.3 * x[0]))))),
                        "INC": float(min(15, max(1, round(math.exp(0.4 + 0.45 * x[0])))))})
    return out


def item_xm(args, log) -> dict:
    if args.dry_run:
        recs = [r for r in xm_fixture() if r["W"] in XM_WINTERS]
        allr = xm_fixture()
        jobs = []
        for W in XM_WINTERS:
            tr = [r for r in allr if r["W"] < W]
            te = [r for r in recs if r["W"] == W]
            jobs.append({"id": str(W), "train_x": [r["x"] for r in tr], "train_y": [r["y"] for r in tr],
                         "test_x": [r["x"] for r in te]})
        res = rbridge.run_r("xm_years_surv.R", {"jobs": jobs})
        for W in XM_WINTERS:
            te = [r for r in recs if r["W"] == W]
            for r, m in zip(te, res["jobs"][str(W)]["median"]):
                r["SURV"] = float(min(15, max(1, math.ceil(m - 1e-9))))
        sc = xm_score(recs, ("SURV", "INC", "N_C", "N_K"), B=200, seed=SEED)
        fake_planted = {"P1": {"pass": True}, "P2": {"pass": False}}
        return {"item": "xm", "dry_run": True, "generated": _now(), "score": sc,
                "verdict": xm_verdict(sc, fake_planted),
                "dists": {k: v["dist"] for k, v in res["jobs"].items()}}
    import fa_market as fm
    with fit_cache_read_only():
        rows = fm.enriched_signings(XM_FIRST, XM_LAST)
    bad = [s for s in rows if s["class_year"] > XM_LAST]
    if bad:
        raise SystemExit("guard: a holdout class year reached the frame")
    t0 = time.time()
    planted = xm_planted(rows, log=log)
    log(f"  planted: P1 {planted['P1']['pass']} P2 {planted['P2']['pass']} "
        f"({round(time.time() - t0, 1)} s)")
    real = xm_pipeline(rows, log=log)
    sc = xm_score(real["rows"], ("SURV", "INC", "N_C", "N_K"), B=XM_B, seed=SEED)
    return {"item": "xm", "dry_run": False, "generated": _now(),
            "frame": {"class_years_built": [XM_FIRST, XM_LAST], "winters": list(XM_WINTERS),
                      "n_enriched": len(rows)},
            "planted": planted, "score": sc, "verdict": xm_verdict(sc, planted),
            "folds": real["meta"], "flexsurv": real["flexsurv"]}


# ---------------------------------------------------------------------------
# item (c): crossed random effects on X3's ridge staged model
# ---------------------------------------------------------------------------

def _staged_rec_class():
    import efv_x3_pooled as X

    class StagedRec(X.Staged):
        """X3's Staged.fit, unchanged, keeping the stage training arrays for the GLMM."""

        def fit(self, ctx, tr):
            T = ctx.T
            v = ctx.variant
            R = tr["R"]
            wR = X.player_weights(T, R) * ctx.w_shift[R]
            self.R = self._fit(ctx, R, T.r3[R], wR, "binary")
            C = tr["C"]
            p = self.R.predict(C)
            lvC = T.kind[C] == "LV"
            if lvC.any():
                cf = X._crossfit_folds(T.pk[R])
                cfC = X._crossfit_folds(T.pk[C])
                for j in range(X.CROSSFIT_K):
                    m = cf != j
                    if m.sum() < 50:
                        continue
                    Rj = R[m]
                    fj = self._fit(ctx, Rj, T.r3[Rj], wR[m], "binary")
                    sel = lvC & (cfC == j)
                    if sel.any():
                        p[sel] = fj.predict(C[sel])
            mills = X.imr(p)
            if v.get("imr") == "perm":
                raise RuntimeError("not used here")
            inst_m = dict(zip(C.tolist(), mills.tolist()))
            wC = dict(zip(C.tolist(), (X.player_weights(T, C) * ctx.w_shift[C]).tolist()))
            ii, kk, pt, wr = X.panel_design(T, C, zero_fill=v.get("censor") == "zero")
            wi = np.asarray([wC[i] for i in ii])
            mi = np.asarray([inst_m[i] for i in ii])
            self.T_ = self._fit(ctx, ii, pt, wi, "reg", k=kk, extra={"imr": mi})
            q = pt > 0
            self.Q = self._fit(ctx, ii[q], wr[q] / pt[q], wi[q] * pt[q], "reg", k=kk[q],
                               extra={"imr": mi[q]})
            self.cap = {"R": R, "wR": wR, "ii": ii, "kk": kk, "pt": pt, "wr": wr, "wi": wi,
                        "mi": mi, "q": q}
            return self

    return StagedRec


def efv_input_ids(cache: Path) -> dict:
    """{(kind, side, year, pk): MLBAM id} from the INPUT side of X3's cached build: the list
    frame rows' outcome-blind id (LV) and the matrix rows' id (MTX, PIN), the ids X3's own
    inputs read through (efv_x3_pooled.Builder.build). Labels' ids are never used."""
    import efv5_combined as V5C
    import efv_etools_reweight as ER
    main_mod = sys.modules["__main__"]
    for cls in ("Bank", "RowMeta"):
        if not hasattr(main_mod, cls):
            setattr(main_mod, cls, getattr(ER, cls))
    with (cache / "er" / "build.pkl").open("rb") as fh:
        frames_lv = pickle.load(fh)["frames_lv"]
    raw_m = V5C._raw_by_side()
    out = {}
    for side in ("hit", "pit"):
        for V, (rows, _labs) in frames_lv[side].items():
            for r in rows:
                if r.get("mlbam_id"):
                    out[("LV", side, int(V), r["player_key"])] = int(r["mlbam_id"])
        for pk, rw in raw_m[side].items():
            if rw.get("mlbam_id"):
                out[("RAW", side, pk)] = int(rw["mlbam_id"])
    return out


def efv_groups(T, cache: Path, log=print) -> dict:
    """Side-specific org, level-season and entry class (registration section 5 as amended by
    A-1): org from the league transaction feed (the parent org of the latest transaction's
    destination club dated before the read), entry class from the draft history (the latest
    draft before the read) else the first MiLB season before the read, both keyed by the
    instance's INPUT-side MLBAM id; level-season from the instance's level_rank and year."""
    import efv_vintage_frame as F
    import efv_x2_revealed as X2
    ids = efv_input_ids(cache)
    books = X2.Books.load(last_year=F.R_VM_FIRST_DEBUT_YEAR - 1,
                          date_cap=f"{F.R_VM_FIRST_DEBUT_YEAR}-01-01", log=log)
    org, ls, ec = [], [], []
    cnt: dict = {}

    def bump(k):
        cnt[k] = cnt.get(k, 0) + 1
    lvl = T.base.get("level_rank")
    latest_input = None
    for i, r in enumerate(T.recs):
        side, kind = r["side"], r["kind"]
        read = str(r.get("read") or f"{int(r['year'])}-01-01")[:10]
        if kind == "LV":
            pid = ids.get(("LV", side, int(r["year"]), r["pk"]))
        elif kind in ("MTX", "PIN"):
            pid = ids.get(("RAW", side, r["pk"]))
        else:
            pid = None
        o = None
        if pid is not None:
            for ev in reversed(books.tx.events.get(pid) or []):
                if ev[0] < read and ev[4] is not None:
                    ti = X2.team_info(ev[4], int(ev[0][:4]))
                    if ti is not None:
                        o = ti[1]
                        latest_input = max(latest_input or "", ev[0])
                        break
        if o is None:
            bump(f"{kind}:org_unk")
        org.append(f"{side}|{o if o is not None else 'UNK'}")
        lv = None if lvl is None or not np.isfinite(lvl[i]) else float(lvl[i])
        ls.append(f"{side}|{'NA' if lv is None else round(lv, 3)}|{int(r['year'])}")
        e = None
        if pid is not None:
            ry, rm = int(read[:4]), int(read[5:7])
            dys = [y for y in books.drafts.get(pid) or [] if y < ry or (y == ry and rm >= 8)]
            if dys:
                e = f"draft|{max(dys)}"
            else:
                fs = books.milb.first_season.get(pid)
                if fs is not None and fs < ry:
                    e = f"milb|{fs}"
        if e is None:
            bump(f"{kind}:ec_unk")
        ec.append(f"{side}|{e or 'UNK'}")
        bump(f"{kind}:n")
    return {"org": np.asarray(org, dtype=object), "ls": np.asarray(ls, dtype=object),
            "ec": np.asarray(ec, dtype=object), "counts": cnt, "latest_tx_input": latest_input,
            "levels": {"org": len(set(org)), "ls": len(set(ls)), "ec": len(set(ec))}}


def _re_lookup(res: dict, g: dict, rows: np.ndarray) -> np.ndarray:
    out = np.full(rows.size, float(res.get("intercept") or 0.0))
    re = res.get("re") or {}
    if not isinstance(re, dict):
        return out
    for term in ("org", "ls", "ec"):
        tab = re.get(term) or {}
        if not isinstance(tab, dict):
            continue
        out += np.asarray([float(tab.get(str(x), 0.0)) for x in g[term][rows]])
    return out


def efv_fold_jobs(T, m, g: dict, perms: dict, plant_rng) -> tuple[list[dict], dict]:
    """The GLMM jobs of one fold: real (R, T, Q), every permuted-group run (R, T, Q) and the
    planted Q and R checks."""
    import efv_x3_pooled as X
    c = m.cap
    R, ii, kk, q = c["R"], c["ii"], c["kk"], c["q"]
    offR = m.R.raw(R)
    offT = m.T_.raw(ii, k=kk, extra={"imr": c["mi"]})
    offQ = m.Q.raw(ii[q], k=kk[q], extra={"imr": c["mi"][q]})
    stages = {"R": ("binomial", R, T.r3[R], c["wR"], offR),
              "T": ("gaussian", ii, c["pt"], c["wi"], offT),
              "Q": ("gaussian", ii[q], c["wr"][q] / c["pt"][q], c["wi"][q] * c["pt"][q], offQ)}

    def job(jid, fam, inst, y, w, off, gmap):
        return {"id": jid, "family": fam, "y": np.asarray(y, float).tolist(),
                "w": np.asarray(w, float).tolist(), "offset": np.asarray(off, float).tolist(),
                "org": gmap["org"][inst].tolist(), "ls": gmap["ls"][inst].tolist(),
                "ec": gmap["ec"][inst].tolist()}
    jobs = []
    for run, gmap in [("real", g)] + list(perms.items()):
        for st, (fam, inst, y, w, off) in stages.items():
            jobs.append(job(f"{run}|{st}", fam, inst, y, w, off, gmap))
    planted = {}
    for st in ("Q", "R"):
        fam, inst, y, w, off = stages[st]
        levels = sorted(set(g["org"][inst].tolist()))
        if st == "Q":
            s = float(np.std(np.asarray(y) - off))
            b = dict(zip(levels, plant_rng.normal(0.0, EFV_PLANT_Q * s, len(levels))))
            ysim = off + np.asarray([b[o] for o in g["org"][inst]]) + plant_rng.normal(0.0, s, inst.size)
        else:
            b = dict(zip(levels, plant_rng.normal(0.0, EFV_PLANT_R, len(levels))))
            pr = X.sigmoid(off + np.asarray([b[o] for o in g["org"][inst]]))
            ysim = (plant_rng.random(inst.size) < pr).astype(float)
        jobs.append(job(f"plant|{st}", fam, inst, ysim, w, off, g))
        planted[st] = b
    return jobs, planted


def efv_score(m, res: dict, run: str, gmap: dict, test: np.ndarray) -> np.ndarray:
    """X3's recombination with each stage's random effects added (section 5)."""
    import efv_x3_pooled as X
    rawR = m.R.raw(test)
    mills = X.imr(X.sigmoid(rawR))
    p = X.sigmoid(rawR + _re_lookup(res[f"{run}|R"], gmap, test))
    reT = _re_lookup(res[f"{run}|T"], gmap, test)
    reQ = _re_lookup(res[f"{run}|Q"], gmap, test)
    cond = np.zeros(test.size)
    for k in range(X.SEASONS_K):
        kk = np.full(test.size, k, dtype=np.int64)
        t = m.T_.predict(test, k=kk, extra={"imr": mills}) + reT
        qv = m.Q.predict(test, k=kk, extra={"imr": mills}) + reQ
        cond += np.maximum(0.0, t) * qv
    return p * cond


def item_efv(args, log) -> dict:
    if args.dry_run:
        rng = np.random.default_rng(5)
        n = 3000
        org = rng.integers(0, 30, n)
        eo = rng.normal(0, 0.3, 30)
        off = rng.normal(-1, 1, n)
        y = (rng.random(n) < 1 / (1 + np.exp(-(off + eo[org])))).astype(float)
        jobs = [{"id": "fx|R", "family": "binomial", "y": y.tolist(), "w": np.ones(n).tolist(),
                 "offset": off.tolist(), "org": [f"o{x}" for x in org],
                 "ls": [f"l{x % 7}" for x in range(n)], "ec": ["UNK"] * n}]
        res = rbridge.run_r("efv_glmm.R", {"jobs": jobs})["jobs"]["fx|R"]
        est = np.asarray([float((res.get("re") or {}).get("org", {}).get(f"o{i}", 0.0)) for i in range(30)])
        corr = float(np.corrcoef(est, eo)[0, 1])
        null = [float(x) for x in np.random.default_rng(1).normal(0, 0.01, 20)]
        return {"item": "efv", "dry_run": True, "generated": _now(), "engine": res["engine"],
                "fixture_org_corr": _rnd(corr, 4), "fixture_single_level_term": "ec",
                "null_p95": _rnd(float(np.quantile(null, 0.95)))}
    import efv_beat_pooled_power as PP
    import efv_x3_pooled as X
    cache = Path(args.x3_cache)
    if not (cache / "x3_run_main.pkl").exists():
        raise SystemExit("refused: --x3-cache must hold X3's cached build (x3_run_main.pkl)")
    Run = X.Run(cache, log=log)
    comp, built, T, inp, folds, ets, guards = Run.prep()
    main = Run._load("x3_run_main")
    g = efv_groups(T, cache, log=log)
    log(f"  groups: {g['levels']} {g['counts']}")
    # the permuted-group maps: the triple moved jointly within (side, instance kind, year)
    perms = {}
    for s in EFV_PERM_SEEDS:
        rng = np.random.default_rng(s)
        idx = np.arange(T.n)
        for zg in np.unique(T.zgroup):
            ix = np.flatnonzero(T.zgroup == zg)
            idx[ix] = ix[rng.permutation(ix.size)]
        perms[f"gperm_{s}"] = {k: g[k][idx] for k in ("org", "ls", "ec")}
    StagedRec = _staged_rec_class()
    plant_rng = np.random.default_rng(EFV_PLANT_SEED)
    scores = {"glmm": {}, "ridge_refit": {}, **{k: {} for k in perms}}
    folds_out = {}
    parity_max = 0.0
    for fold in folds:
        t1 = time.time()
        test = fold["test"]
        excl = set(T.pk[test].tolist())
        tr = X.training_sets(T, fold["Y"], excl)
        fx, w_shift, _rec = X.build_fold_features(T, ets["values"][fold["id"]], fold, tr, {},
                                                  perm=None, plant=None, sensitivity=False)
        ctx = X.Ctx(T, fx, w_shift, {})
        inner = {}
        for c in X.CONFIGS:
            sc = main["receipts"][fold["id"]]["inner"].get(X.config_name(c))
            inner[c] = sc
        cfg = X.pick_class(inner, "ridge")
        ref = np.asarray([main["scores"]["X3_ridge"][i]["e"] for i in test.tolist()])
        # the receipts store inner scores rounded to 5 decimals, so a rounded tie can name a
        # different lambda than the read picked; the other grid points are tried against the
        # stored X3-ridge SCORES (never an outcome), and the one that reproduces them is used
        tried = [cfg] + [("ridge", lam) for lam in sorted(X.LAM_GRID, reverse=True)
                         if ("ridge", lam) != cfg]
        m = e_ridge = None
        par = float("inf")
        for c_try in tried:
            m_try = StagedRec(*c_try).fit(ctx, tr)
            e_try = m_try.score(test)["e"]
            par_try = float(np.max(np.abs(e_try - ref))) if test.size else 0.0
            if par_try <= EFV_PARITY_TOL:
                m, e_ridge, par, cfg = m_try, e_try, par_try, c_try
                break
            par = min(par, par_try)
        parity_max = max(parity_max, par)
        if m is None:
            raise SystemExit(f"STOP: X3-ridge parity fails on {fold['id']} (max diff {par})")
        jobs, planted = efv_fold_jobs(T, m, g, perms, plant_rng)
        res = rbridge.run_r("efv_glmm.R", {"jobs": jobs})["jobs"]
        # planted recovery (D)
        pl = {}
        for st, b in planted.items():
            r = res[f"plant|{st}"]
            tab = ((r.get("re") or {}) if isinstance(r.get("re"), dict) else {}).get("org") or {}
            lv = sorted(b)
            est = np.asarray([float(tab.get(o, 0.0)) if isinstance(tab, dict) else 0.0 for o in lv])
            tru = np.asarray([b[o] for o in lv])
            cor = float(np.corrcoef(est, tru)[0, 1]) if est.std() > 0 else 0.0
            pl[st] = {"corr": _rnd(cor, 4), "engine": r["engine"], "n_levels": len(lv)}
        e_glmm = efv_score(m, res, "real", g, test)
        for j, i in enumerate(test.tolist()):
            scores["glmm"][i] = {"e": float(e_glmm[j])}
            scores["ridge_refit"][i] = {"e": float(e_ridge[j])}
        for k, gm in perms.items():
            e_p = efv_score(m, res, k, gm, test)
            for j, i in enumerate(test.tolist()):
                scores[k][i] = {"e": float(e_p[j])}
        folds_out[fold["id"]] = {
            "ridge_lambda": cfg[1], "lambda_by_rounded_receipt": X.pick_class(inner, "ridge")[1],
            "parity_max_abs": par, "planted": pl,
            "engines": {st: res[f"real|{st}"]["engine"] for st in ("R", "T", "Q")},
            "re_sd": {st: res[f"real|{st}"].get("sd") for st in ("R", "T", "Q")},
            "intercepts": {st: _rnd(res[f"real|{st}"].get("intercept")) for st in ("R", "T", "Q")},
            "fallbacks_perm": sum(1 for k in perms for st in ("R", "T", "Q")
                                  if res[f"{k}|{st}"]["engine"] not in ("glmer", "lmer")),
            "n": {st: res[f"real|{st}"]["n"] for st in ("R", "T", "Q")},
            "seconds": round(time.time() - t1, 1)}
        log(f"    fold {fold['id']}: ridge lam {cfg[1]:g}, parity {par:.2e}, planted "
            f"Q {pl['Q']['corr']} R {pl['R']['corr']} ({folds_out[fold['id']]['seconds']} s)")
    runs = {"x3": main, "glmm": {"scores": {"X3": scores["glmm"]}},
            "ridge_refit": {"scores": {"X3": scores["ridge_refit"]}},
            **{k: {"scores": {"X3": scores[k]}} for k in perms}}
    rows_all = X.pool_rows(T, comp, inp, runs)
    rows = PP.dedupe(rows_all, PP.DEDUP_PRIMARY)
    log(f"  pool: {len(rows)} rows after keep_lv ({len(rows_all)} before)")
    planted_ok = all(v["corr"] is not None and v["corr"] >= EFV_PLANT_CORR
                     for f in folds_out.values() for v in f["planted"].values())
    comps_ = [("glmm_vs_served", "glmm", X.SERVED), ("glmm_vs_consensus", "glmm", X.CONS),
              ("glmm_vs_x3ridge", "glmm", "x3:X3_ridge"), ("glmm_vs_x3", "glmm", "x3"),
              ("x3ridge_vs_consensus", "x3:X3_ridge", X.CONS),
              ("served_vs_consensus", X.SERVED, X.CONS)]
    pooled = X.read_legs(rows, comps_, B_=EFV_B, seed=EFV_SEED, log=log)
    per_frame = {fid: X.read_legs([r for r in rows if r["frame"] == fid], comps_[:3], B_=EFV_B,
                                  seed=EFV_SEED, clusterings=("player",), log=lambda *_a: None)
                 for fid in X.FRAMES}
    d_obs = X.point_delta(rows, "glmm", "x3:X3_ridge")
    null_d = [X.point_delta(rows, k, "x3:X3_ridge") for k in perms]
    null_d = [d for d in null_d if d is not None]
    p95 = float(np.quantile(null_d, 0.95)) if null_d else None
    legs = pooled["legs"]

    def lb(name, cl):
        return ((legs[f"{name}|both"].get(cl) or {}).get("lb95"))
    A = all((lb("glmm_vs_served", cl) or -1) > 0 for cl in ("player", "club"))
    Bc = all((lb("glmm_vs_consensus", cl) or -1) > 0 for cl in ("player", "club"))
    C = bool(d_obs is not None and p95 is not None and d_obs > p95)
    ok = A and Bc and C and planted_ok
    ci = (legs["glmm_vs_consensus|both"].get("player") or {}).get("ci95") or [None, None]
    word = ("trails" if ci[1] is not None and ci[1] < 0 else "ties") if not Bc else "beats"
    verdict = "PASS" if ok else f"FAIL ({word} PROSPX consensus)"
    if not planted_ok:
        verdict += ", UNRESOLVED (planted check failed)"
    return {"item": "efv", "dry_run": False, "generated": _now(),
            "x3_cache_files": sorted(p.name for p in cache.glob("x3_run_main.pkl")),
            "guards": guards, "groups": {"levels": g["levels"], "counts": g["counts"]},
            "parity_max_abs": parity_max, "folds": folds_out, "pooled": pooled,
            "per_frame": per_frame,
            "clause_c": {"observed": _rnd(d_obs), "draws": [_rnd(d) for d in null_d],
                         "p95": _rnd(p95), "above": C},
            "clause_d_planted": planted_ok,
            "verdict": {"verdict": verdict, "pass": ok, "A_beats_served": A,
                        "B_beats_consensus": Bc, "C_above_group_null": C, "D_planted": planted_ok}}


# ---------------------------------------------------------------------------

ITEMS = {"aging": item_aging, "xm": item_xm, "efv": item_efv}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--item", required=True, choices=sorted(ITEMS))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--read", action="store_true")
    ap.add_argument("--out", default=None, help="dry-run output path (never under data/)")
    ap.add_argument("--x3-cache", default=None, help="a PRIVATE copy of X3's cache directory")
    a = ap.parse_args(argv)
    if a.dry_run == a.read:
        ap.error("pass exactly one of --dry-run and --read")
    if not rbridge.available():
        print("STOP: R is not installed (Rscript not found)")
        return 2

    def log(*x):
        print(*x, flush=True)
    if a.dry_run:
        if not a.out:
            ap.error("--dry-run needs --out")
        out = Path(a.out).resolve()
        if str(out).startswith(str((ROOT / "data").resolve())):
            ap.error("a dry run never writes under data/")
        doc = ITEMS[a.item](a, log)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
        log(f"dry run written: {out}")
        return 0
    refuse_second_read(a.item)
    t0 = time.time()
    doc = ITEMS[a.item](a, log)
    doc.update({"registration": DOC, "registration_commit": _git("log", "-1", "--format=%h", "--", DOC),
                "code_commit": _git("rev-parse", "--short", "HEAD"), "read_done": True,
                "seconds": round(time.time() - t0, 1), "r_versions": rbridge.versions(),
                "role": "development (adjudicates nothing served; nothing served moves)"})
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT[a.item].write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    log(f"read written: {ARTIFACT[a.item].relative_to(ROOT)}")
    log(json.dumps(doc.get("verdict"), default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
