# SCRATCH (adversarial audit part 2): quantify the as-of violation and its effect on
# (a) apparent model skill and (b) the evaluator's resolving power.
from __future__ import annotations
import json, os, sys, time
from pathlib import Path
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import efv_model as E
from _frontier_ablate import (score_side, rho, ridge_fit, ridge_pred, ols_fit, lincal,
                              _rankavg, LAM, N_NOISE)
from prospect_path import _RIDGE_HOLDOUT_SEED  # noqa

OUT = ROOT / "tools" / "_frontier_out"
SEED = 20260724
ORIGINS = (2020, 2021, 2022, 2023, 2024)
FN = {"hit": "xfv_hitter_matrix.json", "pit": "xfv_pitcher_matrix.json"}


def leaked(r):
    m = r.get("milb") or {}
    s = m.get("milb_season")
    return bool(s) and int(s) >= int(r["asof_date"][:4])


def build(side, scrub):
    raw = json.loads((ROOT / "data" / FN[side]).read_text(encoding="utf-8"))
    lk = np.array([leaked(r) for r in raw])
    if scrub:
        raw = [dict(r, milb=None) if leaked(r) else r for r in raw]
    prep = E._prep(raw, "target_censored", side)
    assert len(prep) == len(raw)
    keys = list(E._feature_spec(side)[0])
    rng = np.random.default_rng(SEED + (7 if side == "pit" else 3))
    n = len(prep)
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float)
    extra = [rng.standard_normal(n) for _ in range(N_NOISE)]
    Xa = np.column_stack([X] + extra)
    names = keys + ["~noise~%d" % j for j in range(N_NOISE)]
    return dict(side=side, X=Xa, y=np.array([r["target"] for r in prep]),
                w=np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None),
                fv=np.array([r["fv"] for r in prep]),
                dy=np.array([r["decision_year"] for r in prep]),
                deb=np.array([r["kind"] == "debuted" for r in prep]),
                keep=np.array([not (r["kind"] == "bust" and o.get("bust_recent"))
                               for r, o in zip(prep, json.loads((ROOT / "data" / FN[side]).read_text("utf-8")))]),
                leak=lk, names=names, idx={k: i for i, k in enumerate(names)}, keys=keys)


def cols_for(D, arm):
    keys, idx = D["keys"], D["idx"]
    base = [idx[k] for k in keys]
    if arm == "base":
        return base
    if arm.startswith("drop:"):
        return [idx[x] for x in keys if x != arm.split(":", 1)[1]]
    if arm.startswith("dropG:"):
        ks = set(arm.split(":", 1)[1].split("+"))
        return [idx[x] for x in keys if x not in ks]
    if arm.startswith("noise:"):
        return base + [idx["~noise~%d" % int(arm.split(":", 1)[1])]]
    raise ValueError(arm)


def _auc(score, lab):
    lab = np.asarray(lab, bool)
    if lab.sum() == 0 or (~lab).sum() == 0:
        return float("nan")
    r = _rankavg(score); n1 = lab.sum(); n0 = (~lab).sum()
    return float((r[lab].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def run(D, cols, sel=None, drop_leak_test=False):
    X, y, w, fv, dy, deb, keep, lk = (D["X"], D["y"], D["w"], D["fv"], D["dy"],
                                      D["deb"], D["keep"], D["leak"])
    if sel is None:
        sel = np.arange(len(y))
    Xs, ys, ws, fvs, dys = X[sel][:, cols], y[sel], w[sel], fv[sel], dy[sel]
    debs, keeps, lks = deb[sel], keep[sel], lk[sel]
    lam = LAM[D["side"]]
    res = {"deb": [], "full": []}
    for yr in ORIGINS:
        tr = np.flatnonzero(keeps & (dys < yr))
        if len(tr) < 60:
            continue
        o = ols_fit(fvs[tr], ys[tr]); rg = ridge_fit(Xs[tr], ys[tr], ws[tr])
        if o is None or rg is None:
            continue
        a, bb = lincal(ridge_pred(rg, Xs[tr]), ys[tr])
        for frame in ("deb", "full"):
            base = (debs if frame == "deb" else keeps) & (dys == yr)
            if drop_leak_test:
                base = base & (~lks)
            te = np.flatnonzero(base)
            if len(te) < 15:
                continue
            mod = np.maximum(-2.0, a + bb * ridge_pred(rg, Xs[te]))
            cons = np.maximum(0.0, o[0] + o[1] * fvs[te])
            p = (1 - lam) * cons + lam * mod
            n = len(te)
            res[frame].append(((_rankavg(p) - 0.5) / n, ys[te], debs[te]))
    out = {}
    if res["deb"]:
        P = np.concatenate([x[0] for x in res["deb"]]); T = np.concatenate([x[1] for x in res["deb"]])
        out["block_rho"] = rho(P, T)
    if res["full"]:
        P = np.concatenate([x[0] for x in res["full"]]); Dd = np.concatenate([x[2] for x in res["full"]])
        T = np.concatenate([x[1] for x in res["full"]])
        out["fp_auc_debut"] = _auc(P, Dd)
        out["fp_auc_war1"] = _auc(P, T >= 1.0)
    return out


ARMS = {"hit": ["drop:fv", "drop:tool_speed", "noise:0", "noise:1", "noise:2"],
        "pit": ["dropG:peak_k_rel+k_rel+bb_rel+x_era_k", "drop:tool_fb",
                "noise:0", "noise:1", "noise:2"]}
MET = ("block_rho", "fp_auc_debut", "fp_auc_war1")


def main(B=300):
    t0 = time.time()
    report = {}
    for side in ("hit", "pit"):
        for scrub in (False, True):
            for dlt in (False, True):
                if scrub and dlt:
                    continue
                tag = f"{side}/{'SCRUB' if scrub else 'asis'}/{'noleaktest' if dlt else 'alltest'}"
                D = build(side, scrub)
                print(f"\n===== {tag}   leaked rows = {int(D['leak'].sum())}/{len(D['leak'])} =====")
                base = run(D, cols_for(D, "base"), drop_leak_test=dlt)
                print("  BASE " + "  ".join(f"{k}={v:.4f}" for k, v in base.items()))
                # bootstrap
                rng = np.random.default_rng(SEED)
                strata = [np.flatnonzero(D["dy"] == yr) for yr in np.unique(D["dy"])]
                acc = {a: {m: [] for m in MET} for a in ARMS[side]}
                for it in range(B):
                    sel = np.concatenate([rng.choice(ix, len(ix), True) for ix in strata])
                    b = run(D, cols_for(D, "base"), sel, dlt)
                    for arm in ARMS[side]:
                        a_ = run(D, cols_for(D, arm), sel, dlt)
                        for m in MET:
                            if m in b and m in a_:
                                acc[arm][m].append(b[m] - a_[m])
                print(f"  {'arm':40}" + "".join(f"{m:>22}" for m in MET))
                rr = {}
                for arm in ARMS[side]:
                    line = f"  {arm:40}"
                    rr[arm] = {}
                    for m in MET:
                        v = np.array(acc[arm][m])
                        mu, sd = float(v.mean()), float(v.std(ddof=1))
                        rr[arm][m] = dict(mean=mu, sd=sd, snr=abs(mu) / sd if sd else None,
                                          p_gt0=float((v > 0).mean()))
                        line += f"{mu:+.4f}/{sd:.4f} r={abs(mu)/sd:4.1f}".rjust(22)
                    print(line)
                report[tag] = dict(base=base, arms=rr, n_leak=int(D["leak"].sum()))
    (OUT / "_auditleak2.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("\nelapsed", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 300)
