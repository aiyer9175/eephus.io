# scratch lab (lane: nested) -- driver.
#   python tools/_comb_nested_run.py prereg          # pre-registration, X only
#   python tools/_comb_nested_run.py insample [arm]  # (a) + family-wise max-stat null + BH
#   python tools/_comb_nested_run.py nested [arm]    # (b)(c)(d)(e)
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import _arch_discover as A          # noqa: E402
import _comb_nested as C            # noqa: E402

OUT = C.OUT


def get_rows(arm="pooled"):
    rows = A.oof("hit")
    if arm == "tr":
        rows = [r for r in rows if r["has_milb"]]
    for r in rows:
        r["_is_train"] = True
    return rows


def nfloor(arm):
    return C.NFLOOR_TR if arm == "tr" else C.NFLOOR_POOLED


# ------------------------------------------------------------------ (1) prereg
def cmd_prereg():
    """Write the FULL candidate list before any outcome statistic exists."""
    rec = {}
    for arm in ("pooled", "tr"):
        rows = get_rows(arm)
        M, desc = C.enumerate_candidates(rows, rows, nfloor(arm))
        by_order = {}
        for d in desc:
            by_order[len(d)] = by_order.get(len(d), 0) + 1
        rec[arm] = {
            "n_rows": len(rows),
            "n_axes": len(C.AXES),
            "axes": C.AXIS_NAMES,
            "nfloor": nfloor(arm),
            "max_order": C.MAX_ORDER,
            "n_candidates_total": len(desc),
            "n_candidates_by_order": {str(k): v for k, v in sorted(by_order.items())},
            "candidates": [C.desc_str(d) for d in desc],
        }
        print(f"[prereg] arm={arm:6s} rows={len(rows):5d} nfloor={nfloor(arm)} "
              f"CANDIDATES={len(desc):6d}  by order={sorted(by_order.items())}")
    (OUT / "prereg.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print("[prereg] wrote", OUT / "prereg.json")


# ------------------------------------------------------------------ helpers
def fold_masks(rows, train_mask, arm):
    for r, t in zip(rows, train_mask):
        r["_is_train"] = bool(t)
    train_rows = [r for r, t in zip(rows, train_mask) if t]
    return C.enumerate_candidates(rows, train_rows, nfloor(arm))


def perm_within_year(y, years, rng):
    out = y.copy()
    for b in np.unique(years):
        i = np.where(years == b)[0]
        out[i] = y[rng.permutation(i)]
    return out


# ------------------------------------------------------------------ (a) in-sample
def cmd_insample(arm="pooled", B=1000, target="resid"):
    t0 = time.time()
    rows = get_rows(arm)
    n = len(rows)
    years = np.array([r["year"] for r in rows])
    w = np.array([r["weight"] for r in rows], float)
    resid = np.array([r["resid"] for r in rows], float)
    tgt = np.array([r["target"] for r in rows], float)
    y_raw = resid if target == "resid" else tgt
    y = C.block_center(y_raw, w, years)

    M, desc = fold_masks(rows, np.ones(n, bool), arm)
    print(f"[insample] arm={arm} target={target} n={n} candidates={len(desc)}")
    Mf = M.astype(np.float32)
    t, m_in, m_out, n_in = C.score_all(Mf, y, w)

    # family-wise max-statistic null: permute the outcome, re-run the ENTIRE sweep
    rng = np.random.default_rng(20260725)
    maxt = np.empty(B)
    for b in range(B):
        yp = perm_within_year(y, years, rng)
        tb, *_ = C.score_all(Mf, yp, w)
        maxt[b] = np.abs(tb).max()
    # per-candidate two-sided p from the normal reference, then BH across the family
    from math import erfc, sqrt
    p = np.array([erfc(abs(v) / sqrt(2)) for v in t])
    q = C.bh_q(p)

    obs_max = float(np.abs(t).max())
    best = int(np.argmax(np.abs(t)))
    fw_p = float((maxt >= obs_max).mean())
    ordr = np.argsort(-np.abs(t))
    top = []
    for c in ordr[:15]:
        top.append({
            "arch": C.desc_str(desc[c]), "n": int(M[:, c].sum()),
            "t": float(t[c]), "mean_in": float(m_in[c]), "mean_out": float(m_out[c]),
            "delta_war": float(m_in[c] - m_out[c]), "p": float(p[c]), "bh_q": float(q[c]),
        })
    rec = {
        "arm": arm, "target": target, "n_rows": n, "n_candidates": len(desc),
        "best_abs_t": obs_max, "best_arch": C.desc_str(desc[best]),
        "best_n": int(M[:, best].sum()),
        "best_delta_war": float(m_in[best] - m_out[best]),
        "maxstat_null_mean": float(maxt.mean()),
        "maxstat_null_p95": float(np.percentile(maxt, 95)),
        "maxstat_null_p99": float(np.percentile(maxt, 99)),
        "maxstat_null_max": float(maxt.max()),
        "familywise_p": fw_p,
        "n_bh_q_lt_10pct": int((q < 0.10).sum()),
        "n_bh_q_lt_5pct": int((q < 0.05).sum()),
        "n_nominal_p_lt_05": int((p < 0.05).sum()),
        "expected_false_at_p05": float(0.05 * len(desc)),
        "top15": top,
        "secs": round(time.time() - t0, 1),
    }
    (OUT / f"insample_{arm}_{target}.json").write_text(json.dumps(rec, indent=1),
                                                       encoding="utf-8")
    print(json.dumps({k: v for k, v in rec.items() if k != "top15"}, indent=1))
    print("--- top 8 ---")
    for r in top[:8]:
        print(f"  t={r['t']:7.3f} q={r['bh_q']:9.3g} n={r['n']:5d} "
              f"dWAR={r['delta_war']:+6.3f}  {r['arch']}")
    return rec


# ------------------------------------------------------------------ (b)-(e) nested
def run_nested(rows, arm, ys, ks, verbose=False):
    """ys: dict rep_name -> full-pool outcome vector (already block-centred per year).

    Returns per-rep, per-k pooled test-fold results. The search (cut-points,
    enumeration, scoring, selection) sees ONLY decision_year < Y."""
    n = len(rows)
    years = np.array([r["year"] for r in rows])
    w = np.array([r["weight"] for r in rows], float)
    pred = np.array([r["pred"] for r in rows], float)
    tgt = np.array([r["target"] for r in rows], float)

    acc = {rep: {k: {"idx": [], "adj": [], "insample_t": []} for k in ks} for rep in ys}
    for Y in C.OUTER_YEARS:
        tr = years < Y
        te = years == Y
        if tr.sum() < 80 or te.sum() == 0:
            continue
        M, desc = fold_masks(rows, tr, arm)
        Mf = M.astype(np.float32)
        tr_i = np.where(tr)[0]
        te_i = np.where(te)[0]
        Mtr = Mf[tr_i]
        if verbose:
            print(f"  fold Y={Y} train={tr.sum()} test={te.sum()} cands={len(desc)}")
        for rep, yfull in ys.items():
            ytr = C.block_center(yfull[tr_i], w[tr_i], years[tr_i])
            t, m_in, m_out, n_in = C.score_all(Mtr, ytr, w[tr_i])
            for k in ks:
                chosen = C.select_topk(t, M, k, tr_i)
                offs = [float(m_in[c] - m_out[c]) for c in chosen]
                adj = C.apply_offsets(M[te_i], list(range(len(chosen))),
                                      offs) if False else None
                # apply on the test rows using the ORIGINAL column ids
                tot = np.zeros(len(te_i))
                cnt = np.zeros(len(te_i))
                for c, d in zip(chosen, offs):
                    mm = M[te_i, c]
                    tot[mm] += d
                    cnt[mm] += 1
                adj = np.zeros(len(te_i))
                nz = cnt > 0
                adj[nz] = tot[nz] / cnt[nz]
                acc[rep][k]["idx"].append(te_i)
                acc[rep][k]["adj"].append(adj)
                acc[rep][k]["insample_t"].append(float(np.abs(t).max()))
        del Mf, Mtr, M

    res = {}
    for rep in ys:
        res[rep] = {}
        for k in ks:
            idx = np.concatenate(acc[rep][k]["idx"])
            adj = np.concatenate(acc[rep][k]["adj"])
            p0 = pred[idx]
            p1 = p0 + adj
            t_ = tgt[idx]
            r0 = C.spearman(p0, t_)
            r1 = C.spearman(p1, t_)
            # block (per-year) rho
            b0, b1 = [], []
            yy = years[idx]
            for b in np.unique(yy):
                i = yy == b
                if i.sum() >= 20:
                    b0.append(C.spearman(p0[i], t_[i]))
                    b1.append(C.spearman(p1[i], t_[i]))
            ww = w[idx]
            mse0 = float(np.average((t_ - p0) ** 2, weights=ww))
            mse1 = float(np.average((t_ - p1) ** 2, weights=ww))
            res[rep][k] = {
                "n_test": int(len(idx)),
                "rho_base": r0, "rho_adj": r1, "d_rho": r1 - r0,
                "block_rho_base": float(np.mean(b0)), "block_rho_adj": float(np.mean(b1)),
                "d_block_rho": float(np.mean(b1) - np.mean(b0)),
                "mse_base": mse0, "mse_adj": mse1, "d_mse": mse1 - mse0,
                "frac_rows_adjusted": float((adj != 0).mean()),
                "mean_abs_adj": float(np.abs(adj).mean()),
                "insample_best_t_per_fold": acc[rep][k]["insample_t"],
                "insample_best_t_mean": float(np.mean(acc[rep][k]["insample_t"])),
            }
    return res


def cmd_nested(arm="pooled", R=40, target="resid"):
    t0 = time.time()
    rows = get_rows(arm)
    n = len(rows)
    years = np.array([r["year"] for r in rows])
    resid = np.array([r["resid"] for r in rows], float)
    tgt = np.array([r["target"] for r in rows], float)
    y_real = resid if target == "resid" else tgt

    rng = np.random.default_rng(777)
    ys = {"real": y_real}
    for i in range(R):
        ys[f"perm{i}"] = perm_within_year(y_real, years, rng)

    print(f"[nested] arm={arm} target={target} n={n} outer_folds={C.OUTER_YEARS} "
          f"ks={C.KS} control_reps={R}")
    res = run_nested(rows, arm, ys, C.KS, verbose=True)

    rec = {"arm": arm, "target": target, "n_rows": n, "ks": list(C.KS),
           "outer_years": list(C.OUTER_YEARS), "control_reps": R, "real": res["real"]}
    ctrl = {}
    for k in C.KS:
        d = np.array([res[f"perm{i}"][k]["d_rho"] for i in range(R)])
        db = np.array([res[f"perm{i}"][k]["d_block_rho"] for i in range(R)])
        it = np.array([res[f"perm{i}"][k]["insample_best_t_mean"] for i in range(R)])
        ctrl[k] = {
            "d_rho_mean": float(d.mean()), "d_rho_sd": float(d.std()),
            "d_rho_p95": float(np.percentile(d, 95)), "d_rho_max": float(d.max()),
            "d_block_rho_mean": float(db.mean()),
            "d_block_rho_p95": float(np.percentile(db, 95)),
            "insample_best_t_mean": float(it.mean()),
            "insample_best_t_p95": float(np.percentile(it, 95)),
            "insample_best_t_max": float(it.max()),
            "p_real_ge_ctrl": float((d >= res["real"][k]["d_rho"]).mean()),
        }
    rec["control"] = {str(k): v for k, v in ctrl.items()}
    rec["secs"] = round(time.time() - t0, 1)
    (OUT / f"nested_{arm}_{target}.json").write_text(json.dumps(rec, indent=1),
                                                     encoding="utf-8")

    print("\n=== NESTED-CV RESULT  arm=%s target=%s ===" % (arm, target))
    for k in C.KS:
        r = res["real"][k]
        c = ctrl[k]
        print(f"k={k:2d}  n_test={r['n_test']:4d}  rho {r['rho_base']:.4f} -> "
              f"{r['rho_adj']:.4f}  d_rho={r['d_rho']:+.4f}  "
              f"d_block_rho={r['d_block_rho']:+.4f}  d_mse={r['d_mse']:+.4f}")
        print(f"      in-sample best |t| (train folds, mean) real={r['insample_best_t_mean']:.3f}"
              f"  CONTROL={c['insample_best_t_mean']:.3f} "
              f"(p95 {c['insample_best_t_p95']:.3f}, max {c['insample_best_t_max']:.3f})")
        print(f"      control d_rho mean={c['d_rho_mean']:+.4f} sd={c['d_rho_sd']:.4f} "
              f"p95={c['d_rho_p95']:+.4f}  P(ctrl >= real)={c['p_real_ge_ctrl']:.3f}")
        print(f"      rows adjusted={r['frac_rows_adjusted']:.3f} "
              f"mean|adj|={r['mean_abs_adj']:.3f} WAR")
    return rec


def cmd_gap(arm="pooled", target="resid", R=20):
    """(c) selection bias = in-sample APPLIED lift minus nested-CV lift.

    In-sample arm: select the top-k on ALL rows and score them on those very
    same rows (the circular number). Nested arm is read from cmd_nested."""
    rows = get_rows(arm)
    n = len(rows)
    years = np.array([r["year"] for r in rows])
    w = np.array([r["weight"] for r in rows], float)
    pred = np.array([r["pred"] for r in rows], float)
    tgt = np.array([r["target"] for r in rows], float)
    y_raw = np.array([r["resid"] for r in rows], float) if target == "resid" else tgt

    M, desc = fold_masks(rows, np.ones(n, bool), arm)
    Mf = M.astype(np.float32)
    allidx = np.arange(n)
    rng = np.random.default_rng(4242)

    def _insample_lift(yv):
        yc = C.block_center(yv, w, years)
        t, m_in, m_out, _ = C.score_all(Mf, yc, w)
        out = {}
        for k in C.KS:
            ch = C.select_topk(t, M, k, allidx)
            offs = [float(m_in[c] - m_out[c]) for c in ch]
            tot = np.zeros(n); cnt = np.zeros(n)
            for c, d in zip(ch, offs):
                mm = M[:, c]
                tot[mm] += d
                cnt[mm] += 1
            adj = np.zeros(n)
            nz = cnt > 0
            adj[nz] = tot[nz] / cnt[nz]
            r0 = C.spearman(pred, tgt)
            r1 = C.spearman(pred + adj, tgt)
            out[k] = {"rho_base": r0, "rho_adj": r1, "d_rho": r1 - r0,
                      "best_abs_t": float(np.abs(t).max()),
                      "archs": [C.desc_str(desc[c]) for c in ch],
                      "offsets": offs,
                      "ns": [int(M[:, c].sum()) for c in ch]}
        return out

    real = _insample_lift(y_raw)
    ctrl = {k: [] for k in C.KS}
    for i in range(R):
        o = _insample_lift(perm_within_year(y_raw, years, rng))
        for k in C.KS:
            ctrl[k].append(o[k]["d_rho"])

    rec = {"arm": arm, "target": target, "n_rows": n, "n_candidates": len(desc),
           "insample": {str(k): real[k] for k in C.KS},
           "insample_control_d_rho": {str(k): {"mean": float(np.mean(ctrl[k])),
                                               "p95": float(np.percentile(ctrl[k], 95)),
                                               "max": float(np.max(ctrl[k]))}
                                      for k in C.KS}}
    (OUT / f"gap_{arm}_{target}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print(f"=== IN-SAMPLE APPLIED LIFT (circular)  arm={arm} target={target} "
          f"cands={len(desc)} ===")
    for k in C.KS:
        r = real[k]
        c = rec["insample_control_d_rho"][str(k)]
        print(f"k={k:2d}  rho {r['rho_base']:.4f} -> {r['rho_adj']:.4f}  "
              f"d_rho={r['d_rho']:+.4f}   CONTROL(permuted y) mean={c['mean']:+.4f} "
              f"p95={c['p95']:+.4f} max={c['max']:+.4f}")
        for a, o, nn in zip(r["archs"], r["offsets"], r["ns"]):
            print(f"        n={nn:5d} off={o:+.3f} WAR   {a}")
    return rec


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "prereg"
    a = sys.argv[2] if len(sys.argv) > 2 else "pooled"
    if cmd == "prereg":
        cmd_prereg()
    elif cmd == "insample":
        cmd_insample(a, B=int(sys.argv[3]) if len(sys.argv) > 3 else 1000,
                     target=sys.argv[4] if len(sys.argv) > 4 else "resid")
    elif cmd == "nested":
        cmd_nested(a, R=int(sys.argv[3]) if len(sys.argv) > 3 else 40,
                   target=sys.argv[4] if len(sys.argv) > 4 else "resid")
    elif cmd == "gap":
        cmd_gap(a, target=sys.argv[3] if len(sys.argv) > 3 else "resid",
                R=int(sys.argv[4]) if len(sys.argv) > 4 else 20)
