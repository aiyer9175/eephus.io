# SCRATCH (adversarial audit: leakage / circularity / selection). Read-only w.r.t. shipped code.
# Reuses the parity-verified replica in tools/_frontier_ablate.py.
from __future__ import annotations
import json, math, os, sys, time
from pathlib import Path
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import _frontier_ablate as A  # noqa
from _frontier_ablate import (load_side, score_side, block_rho, rho, ridge_fit, ridge_pred,
                              ols_fit, lincal, _rankavg, LAM)

OUT = ROOT / "tools" / "_frontier_out"
OUT.mkdir(exist_ok=True)
SEED = 20260724
ORIGINS = (2020, 2021, 2022, 2023, 2024)


def load_all():
    D = {s: load_side(s) for s in ("hit", "pit")}
    # attach raw per-row weight/censored/observed_seasons for the test-label audit
    for s, fn in (("hit", "xfv_hitter_matrix.json"), ("pit", "xfv_pitcher_matrix.json")):
        raw = json.loads((ROOT / "data" / fn).read_text(encoding="utf-8"))
        import efv_model as E
        prep = E._prep(raw, "target_censored", s)
        # _prep preserves order (asserted in ablate.load_side)
        D[s]["obs"] = np.array([int(r.get("observed_seasons") or 6) for r in raw])
        D[s]["cens"] = np.array([bool(r.get("censored")) for r in raw])
        D[s]["tres"] = np.array([float(r.get("target_resolved") or 0.0) for r in raw])
    return D


# ------------------------------------------------------------------ (1) per-origin signal
def per_origin(D):
    print("=== PER-ORIGIN TEST-SET DIAGNOSTIC (shipped blend, production train frame) ===")
    print(f"{'side':4} {'orig':5} {'n':>4} {'%cens':>6} {'meanW':>6} {'rho_cens':>9} "
          f"{'rho_resolvedsub':>16} {'n_res':>6} {'sd(target)':>10}")
    rowsout = []
    for s in ("hit", "pit"):
        Dd = D[s]
        cols = np.arange(len(Dd["keys"]))
        for yr in ORIGINS:
            r = score_side(Dd, cols, origins=(yr,))
            if r is None:
                continue
            b, p, t = r
            te = np.flatnonzero(Dd["deb"] & (Dd["dy"] == yr))
            assert len(te) == len(t)
            w = Dd["w"][te]
            cens = Dd["cens"][te]
            rr = rho(p, t)
            m = ~cens
            rres = rho(p[m], t[m]) if m.sum() >= 15 else float("nan")
            print(f"{s:4} {yr:5} {len(t):4d} {100*cens.mean():6.0f} {w.mean():6.3f} "
                  f"{rr:9.4f} {rres:16.4f} {int(m.sum()):6d} {t.std():10.3f}")
            rowsout.append(dict(side=s, origin=yr, n=len(t), pct_cens=float(cens.mean()),
                                meanW=float(w.mean()), rho=float(rr),
                                rho_resolved=None if math.isnan(rres) else float(rres),
                                n_res=int(m.sum())))
    return rowsout


# ------------------------------------------------------------------ arms
def arm_cols(D, s, arm):
    keys = D[s]["keys"]; idx = D[s]["idx"]
    base = [idx[k] for k in keys]
    if arm == "base":
        return base
    if arm.startswith("drop:"):
        k = arm.split(":", 1)[1]
        return [idx[x] for x in keys if x != k]
    if arm.startswith("dropG:"):
        ks = set(arm.split(":", 1)[1].split("+"))
        return [idx[x] for x in keys if x not in ks]
    if arm.startswith("noise:"):
        j = int(arm.split(":", 1)[1])
        return base + [idx["~noise~%d" % j]]
    raise ValueError(arm)


ARMS_HIT = ["drop:fv", "drop:tool_speed", "noise:0", "noise:1", "noise:2"]
ARMS_PIT = ["dropG:peak_k_rel+k_rel+bb_rel+x_era_k", "drop:tool_fb", "noise:0", "noise:1", "noise:2"]


# ------------------------------------------------------------------ metric variants
def _auc(score, lab):
    lab = np.asarray(lab, dtype=bool)
    if lab.all() or (~lab).any() is False or lab.sum() == 0 or (~lab).sum() == 0:
        return float("nan")
    r = _rankavg(score)
    n1 = lab.sum(); n0 = (~lab).sum()
    return float((r[lab].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def score_full(D, s, cols, origins, sel=None, test_frame="debuted"):
    """Return list of (blockid, pred, target, weight, obs, resolved_target) for one side."""
    Dd = D[s]
    X, y, w, fv, dy, deb, keep = Dd["X"], Dd["y"], Dd["w"], Dd["fv"], Dd["dy"], Dd["deb"], Dd["keep"]
    obs, tres = Dd["obs"], Dd["tres"]
    if sel is None:
        sel = np.arange(len(y))
    Xs, ys, ws, fvs, dys = X[sel][:, cols], y[sel], w[sel], fv[sel], dy[sel]
    debs, keeps, obss, tress = deb[sel], keep[sel], obs[sel], tres[sel]
    lam = LAM[s]
    B, P, T, W, O, R = [], [], [], [], [], []
    for yr in origins:
        tr = np.flatnonzero(keeps & (dys < yr))
        if test_frame == "debuted":
            te = np.flatnonzero(debs & (dys == yr))
        else:  # full pool (debuted + non-recent busts)
            te = np.flatnonzero(keeps & (dys == yr))
        if len(te) < 15 or len(tr) < 60:
            continue
        o = ols_fit(fvs[tr], ys[tr])
        rg = ridge_fit(Xs[tr], ys[tr], ws[tr])
        if o is None or rg is None:
            continue
        a, bb = lincal(ridge_pred(rg, Xs[tr]), ys[tr])
        mod = np.maximum(-2.0, a + bb * ridge_pred(rg, Xs[te]))
        cons = np.maximum(0.0, o[0] + o[1] * fvs[te])
        B.append(np.full(len(te), yr)); P.append((1 - lam) * cons + lam * mod)
        T.append(ys[te]); W.append(ws[te]); O.append(obss[te]); R.append(tress[te])
        if test_frame == "full":
            R[-1] = debs[te].astype(float)   # reuse slot: debut indicator
    if not P:
        return None
    return tuple(np.concatenate(x) for x in (B, P, T, W, O, R))


def metrics(parts):
    """parts = {side: (b,p,t,w,o,r)} -> dict of metric name -> value."""
    out = {}
    def brho(filt=None, origins=None):
        PP, TT = [], []
        for s, (b, p, t, w, o, r) in parts.items():
            for yr in np.unique(b):
                if origins is not None and yr not in origins:
                    continue
                m = b == yr
                if filt is not None:
                    m = m & filt[s]
                if m.sum() < 15:
                    continue
                n = int(m.sum())
                PP.append((_rankavg(p[m]) - 0.5) / n)
                TT.append((_rankavg(t[m]) - 0.5) / n)
        if not PP:
            return float("nan")
        return rho(np.concatenate(PP), np.concatenate(TT))

    out["block_rho"] = brho()
    out["block_rho_2023"] = brho(origins={2020, 2021, 2022, 2023})
    out["block_rho_2022"] = brho(origins={2020, 2021, 2022})
    # resolved-label-only test rows (weight == 1 / not censored)
    filt_res = {s: parts[s][4] >= 6 for s in parts}
    out["block_rho_resolved"] = brho(filt=filt_res)
    # >=4 observed seasons
    filt4 = {s: parts[s][4] >= 4 for s in parts}
    out["block_rho_obs4"] = brho(filt=filt4)
    # pooled AUC(contributor, WAR>=3) on block percentiles
    PP, LL = [], []
    for s, (b, p, t, w, o, r) in parts.items():
        for yr in np.unique(b):
            m = b == yr
            if m.sum() < 15:
                continue
            n = int(m.sum())
            PP.append((_rankavg(p[m]) - 0.5) / n)
            LL.append(t[m] >= 3.0)
    out["cauc"] = _auc(np.concatenate(PP), np.concatenate(LL))
    return out


def metrics_full(parts):
    """full-pool test frame: AUC of debut / AUC of WAR>0, plus block rho."""
    out = {}
    PP, DD, GG = [], [], []
    for s, (b, p, t, w, o, r) in parts.items():
        for yr in np.unique(b):
            m = b == yr
            if m.sum() < 15:
                continue
            n = int(m.sum())
            pp = (_rankavg(p[m]) - 0.5) / n
            PP.append(pp); DD.append(r[m] > 0.5); GG.append(t[m] >= 1.0)
    P = np.concatenate(PP)
    out["fp_auc_debut"] = _auc(P, np.concatenate(DD))
    out["fp_auc_war1"] = _auc(P, np.concatenate(GG))
    return out


def run_point(D):
    print("\n=== POINT ESTIMATES: candidate deltas under 6 metric variants ===")
    res = {}
    for s, arms in (("hit", ARMS_HIT), ("pit", ARMS_PIT)):
        base_parts = {s: score_full(D, s, arm_cols(D, s, "base"), ORIGINS)}
        mb = metrics(base_parts)
        fb = metrics_full({s: score_full(D, s, arm_cols(D, s, "base"), ORIGINS, test_frame="full")})
        res.setdefault("base", {})[s] = dict(mb, **fb)
        print(f"-- {s} base: " + "  ".join(f"{k}={v:.4f}" for k, v in res["base"][s].items()))
        for arm in arms:
            c = arm_cols(D, s, arm)
            ma = metrics({s: score_full(D, s, c, ORIGINS)})
            fa = metrics_full({s: score_full(D, s, c, ORIGINS, test_frame="full")})
            ma = dict(ma, **fa)
            d = {k: res["base"][s][k] - ma[k] for k in ma}   # +ve = the dropped thing helped
            res.setdefault(arm, {})[s] = d
            print(f"   {arm:38} " + "  ".join(f"{k}={d[k]:+.4f}" for k in
                                              ("block_rho", "block_rho_2023", "block_rho_resolved",
                                               "block_rho_obs4", "cauc", "fp_auc_debut", "fp_auc_war1")))
    (OUT / "_auditleak_point.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res


def run_boot(D, B=200):
    print(f"\n=== PAIRED REFIT BOOTSTRAP (B={B}, strata = side x decision_year, TRAIN+TEST) ===")
    rng = np.random.default_rng(SEED)
    keep = {}
    for s, arms in (("hit", ARMS_HIT), ("pit", ARMS_PIT)):
        Dd = D[s]
        n = len(Dd["y"])
        strata = {}
        for yr in np.unique(Dd["dy"]):
            strata[yr] = np.flatnonzero(Dd["dy"] == yr)
        acc = {a: {} for a in arms}
        for it in range(B):
            sel = np.concatenate([rng.choice(ix, size=len(ix), replace=True) for ix in strata.values()])
            bp = score_full(D, s, arm_cols(D, s, "base"), ORIGINS, sel=sel)
            bf = score_full(D, s, arm_cols(D, s, "base"), ORIGINS, sel=sel, test_frame="full")
            if bp is None:
                continue
            mb = dict(metrics({s: bp}), **metrics_full({s: bf}))
            for arm in arms:
                c = arm_cols(D, s, arm)
                ap = score_full(D, s, c, ORIGINS, sel=sel)
                af = score_full(D, s, c, ORIGINS, sel=sel, test_frame="full")
                ma = dict(metrics({s: ap}), **metrics_full({s: af}))
                for k in ma:
                    acc[arm].setdefault(k, []).append(mb[k] - ma[k])
            if (it + 1) % 25 == 0:
                print(f"   {s} {it+1}/{B}  {time.time()-T0:.0f}s")
        keep[s] = {a: {k: (float(np.mean(v)), float(np.std(v, ddof=1))) for k, v in d.items()}
                   for a, d in acc.items()}
    (OUT / "_auditleak_boot.json").write_text(json.dumps(keep, indent=1), encoding="utf-8")
    print("\n=== EFFECT / SD BY METRIC (|mean| / sd = signal-to-noise; higher = better instrument) ===")
    METS = ("block_rho", "block_rho_2023", "block_rho_resolved", "block_rho_obs4",
            "cauc", "fp_auc_debut", "fp_auc_war1")
    for s in keep:
        print(f"-- {s}")
        hdr = f"{'arm':40}" + "".join(f"{m[:14]:>16}" for m in METS)
        print(hdr)
        for a, d in keep[s].items():
            line = f"{a:40}"
            for m in METS:
                mu, sd = d[m]
                line += f"{mu:+.4f}/{sd:.4f}".rjust(16)
            print(line)
        print("   ratio |mean|/sd:")
        for a, d in keep[s].items():
            line = f"{a:40}"
            for m in METS:
                mu, sd = d[m]
                line += f"{abs(mu)/sd if sd > 0 else float('nan'):16.2f}"
            print(line)
    return keep


if __name__ == "__main__":
    T0 = time.time()
    D = load_all()
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("all", "diag"):
        po = per_origin(D)
        (OUT / "_auditleak_origin.json").write_text(json.dumps(po, indent=1), encoding="utf-8")
    if mode in ("all", "point"):
        run_point(D)
    if mode in ("all", "boot"):
        run_boot(D, B=int(sys.argv[2]) if len(sys.argv) > 2 else 200)
    print("elapsed", round(time.time() - T0, 1), "s")
