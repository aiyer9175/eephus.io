"""H-PRED-3: the merit model, scored on the bake-off's own frame and folds.

WHAT THIS IS FOR. /hof/ ships its predictor section DARK, blocked on H-PRED-3: "no
induction probability is published until a merit model has passed its own gate against
the best public baseline". This is that model, and the gate is deliberately not a
discrimination contest, because that contest is already lost and the bake-off says so:
`hof_monitor` reaches AUC 0.9697 on label_bbwaa and it is built from batting titles, MVP
shares, All-Star selections and postseason play, none of which is in our feature set.

THE GATE IS CALIBRATION-FIRST, and that is the honest shape of the question. A public
score is a RANKING, not a probability: HoF Monitor's "100 means a likely Hall of Famer" is
a rule of thumb, not a calibrated number. So the model has to be
  1. NON-INFERIOR on discrimination against the best public arm, and only then
  2. BETTER on calibration, measured as Brier and expected calibration error.
A model that ranks slightly worse but tells you 12% means 12% is a real product; a model
that ranks worse AND is no better calibrated is not, and prints its loss.

EVERY COMPARISON RIDES THE EXISTING HARNESS. Same frame, same common support, same
forward-chained folds, same paired bootstrap and the same E_cond floor and verdict
machinery the public bake-off used, so the numbers are comparable by construction rather
than by assertion. The only new thing is one more arm.

LEAKAGE. The model is fit per fold on players whose ballot resolved STRICTLY EARLIER and
predicts a held-out block, so no row contributes to its own score. Its features are the
in-house shelf only, never a public arm: putting hof_monitor in the feature set would be
scoring a model against its own input.

Career totals are the point-in-time frame here, and that is worth stating rather than
assuming: every row is a RETIRED player whose ballot window has closed, so there are no
seasons after the cutoff to leak. The as_of() machinery matters for active players and for
the ballot-trajectory work, not for this frame.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import hof_bakeoff as hb                                    # noqa: E402

OUT = ROOT / "data" / "hof_merit_eval.json"

#: In-house only. A public arm as a feature would make the comparison circular.
FEATURES = ("career_war", "war7", "jaws", "career_waa", "waa_pos", "ink", "n_seasons")
#: Position enters as indicators; the reference level is everything not named.
POS_LEVELS = ("C", "SP", "RP")
RIDGE = 1.0
MAX_ITER = 200


def _design(rows):
    """(X, names) with an intercept, standardised later. Pure python lists."""
    X, names = [], ["intercept"] + list(FEATURES) + [f"pos_{p}" for p in POS_LEVELS]
    for r in rows:
        v = [1.0]
        for f in FEATURES:
            x = r.get(f)
            v.append(float(x) if x is not None and x == x else 0.0)
        pc = str(r.get("pos_class") or "")
        v.extend(1.0 if pc == p else 0.0 for p in POS_LEVELS)
        X.append(v)
    return X, names


def _standardise(Xtr, Xte):
    """Fit centre/scale on TRAIN only and apply to both. The intercept is left alone."""
    k = len(Xtr[0])
    mu = [0.0] * k
    sd = [1.0] * k
    for j in range(1, k):
        col = [row[j] for row in Xtr]
        m = sum(col) / len(col)
        var = sum((c - m) ** 2 for c in col) / max(1, len(col) - 1)
        s = math.sqrt(var) or 1.0
        mu[j], sd[j] = m, s
    z = lambda X: [[row[0]] + [(row[j] - mu[j]) / sd[j] for j in range(1, k)] for row in X]
    return z(Xtr), z(Xte)


def fit_logistic(X, y, *, ridge=RIDGE, max_iter=MAX_ITER):
    """L2 logistic by Newton-IRLS with step halving.

    Ridge on every coefficient EXCEPT the intercept: penalising the intercept
    would pull the fitted base rate toward 0.5, and this problem runs at an 11%
    base rate, so that is the one coefficient the penalty must not touch.
    """
    n, k = len(X), len(X[0])
    beta = [0.0] * k
    for _ in range(max_iter):
        eta = [sum(b * x for b, x in zip(beta, row)) for row in X]
        p = [1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, e)))) for e in eta]
        w = [max(pi * (1 - pi), 1e-8) for pi in p]
        g = [0.0] * k
        for i in range(n):
            r = (1.0 if y[i] else 0.0) - p[i]
            for j in range(k):
                g[j] += X[i][j] * r
        for j in range(1, k):
            g[j] -= ridge * beta[j]
        H = [[0.0] * k for _ in range(k)]
        for i in range(n):
            wi, row = w[i], X[i]
            for a in range(k):
                xa = row[a] * wi
                for b in range(a, k):
                    H[a][b] += xa * row[b]
        for a in range(k):
            for b in range(a):
                H[a][b] = H[b][a]
        for j in range(1, k):
            H[j][j] += ridge
        step = _solve(H, g)
        if step is None:
            break
        t, ok = 1.0, False
        base = _pen_ll(X, y, beta, ridge)
        for _ in range(12):
            cand = [b + t * s for b, s in zip(beta, step)]
            if _pen_ll(X, y, cand, ridge) >= base - 1e-12:
                beta, ok = cand, True
                break
            t *= 0.5
        if not ok or max(abs(t * s) for s in step) < 1e-8:
            break
    return beta


def _pen_ll(X, y, beta, ridge):
    ll = 0.0
    for row, yi in zip(X, y):
        e = max(-30.0, min(30.0, sum(b * x for b, x in zip(beta, row))))
        ll += (e if yi else 0.0) - math.log1p(math.exp(e))
    return ll - 0.5 * ridge * sum(b * b for b in beta[1:])


def _solve(A, b):
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[piv][c]) < 1e-12:
            return None
        M[c], M[piv] = M[piv], M[c]
        d = M[c][c]
        for j in range(c, n + 1):
            M[c][j] /= d
        for r in range(n):
            if r == c:
                continue
            f = M[r][c]
            if f:
                for j in range(c, n + 1):
                    M[r][j] -= f * M[c][j]
    return [M[i][n] for i in range(n)]


def predict(beta, X):
    out = []
    for row in X:
        e = max(-30.0, min(30.0, sum(b * x for b, x in zip(beta, row))))
        out.append(1.0 / (1.0 + math.exp(-e)))
    return out


def out_of_fold(frame, label: str, burn: int):
    """Out-of-fold merit probabilities, forward-chained by resolution year.

    Returns {player_ID: p} plus the per-fold record. A block with too few
    training positives is SKIPPED and reported rather than fitted on nothing: an
    intercept-only prediction dressed as a model is worse than an honest gap.
    """
    preds, blocks = {}, []
    for f in hb.folds(frame, label, burn):
        tr, te = f["_train"], f["_test"]
        rec = {"k": f["k"], "lo": f["lo"], "hi": f["hi"],
               "n_train": f["n_train"], "n_test": f["n_test"],
               "train_pos": f["train_pos"], "test_pos": f["test_pos"]}
        if f["n_test"] == 0 or f["train_pos"] < 10 or f["n_train"] < 60:
            rec["fitted"] = False
            rec["why"] = ("no test rows" if f["n_test"] == 0 else
                          f"only {f['train_pos']} training positives")
            blocks.append(rec)
            continue
        trr = tr.to_dict("records")
        ter = te.to_dict("records")
        Xtr, names = _design(trr)
        Xte, _ = _design(ter)
        Xtr, Xte = _standardise(Xtr, Xte)
        beta = fit_logistic(Xtr, [bool(v) for v in tr["y"].tolist()])
        for r, p in zip(ter, predict(beta, Xte)):
            preds[r["player_ID"]] = p
        rec["fitted"] = True
        rec["coefficients"] = {n: round(b, 4) for n, b in zip(names, beta)}
        blocks.append(rec)
    return preds, blocks


def run(*, offline=True, as_of_year=2026, label="bbwaa", B=None, seed=None,
        persist=True):
    B = B or hb.B_BOOT
    seed = hb.SEED if seed is None else seed
    frame = hb.bakeoff_frame(label, offline=offline, as_of_year=as_of_year)
    frame, drop = hb.common_support(frame, label)
    burn = hb.burn_in_year(frame, label)
    preds, blocks = out_of_fold(frame, label, burn)

    scored = frame[frame["player_ID"].isin(preds.keys())].copy()
    scored["merit"] = [preds[p] for p in scored["player_ID"]]
    y = [bool(v) for v in scored["y"].tolist()]
    n_pos = sum(y)

    import numpy as np
    def auc(col):
        return round(hb._auc_np(np, np.asarray(scored[col].tolist(), dtype=float),
                                np.asarray(y, dtype=bool)), 6)

    arms = {a: auc(a) for a in hb.ALL_ARMS}
    arms["merit"] = auc("merit")
    best_public = max(hb.PUBLIC_ARMS, key=lambda a: arms[a])

    # Calibration. The public arms are RANKINGS, so they get a per-fold Platt map
    # before any Brier or ECE is read; comparing a raw HoF Monitor score to a
    # probability would be a category error, not a result.
    cal = {}
    p_merit = scored["merit"].tolist()
    cal["merit"] = {"brier": round(hb.brier(p_merit, y), 6),
                    "ece": round(hb.ece(p_merit, y), 6),
                    "log_loss": round(hb.log_loss(p_merit, y), 6),
                    "platt_applied": False}
    for a in hb.PUBLIC_ARMS:
        s = scored[a].tolist()
        fit = hb.platt_fit(s, y)
        p = hb.platt_apply(fit, s)
        cal[a] = {"brier": round(hb.brier(p, y), 6), "ece": round(hb.ece(p, y), 6),
                  "log_loss": round(hb.log_loss(p, y), 6), "platt_applied": True}

    keys = list(scored["player_ID"])
    disc_gate = hb._econd_floor_stat(
        f"auc.merit_vs_{best_public}", keys, scored["merit"].tolist(),
        scored[best_public].tolist(), scored["y"].tolist(), hb._auc_stat, B=B, seed=seed)
    d_auc = arms["merit"] - arms[best_public]
    mde = disc_gate.get("mde95")
    non_inferior = (mde is not None and d_auc > -abs(mde))

    def _brier_stat(a, b, yy):
        return hb.brier(list(a), [bool(v) for v in yy]) - hb.brier(list(b), [bool(v) for v in yy])
    cal_gate = hb._econd_floor_stat(
        f"brier.merit_vs_{best_public}", keys, p_merit,
        hb.platt_apply(hb.platt_fit(scored[best_public].tolist(), y),
                       scored[best_public].tolist()),
        scored["y"].tolist(),
        lambda a, yy: hb.brier(list(a), [bool(v) for v in yy]),
        B=B, seed=seed, higher_is_better=False)

    d_brier = cal[ "merit"]["brier"] - cal[best_public]["brier"]
    cal_mde = cal_gate.get("mde95")
    cal_wins = (cal_mde is not None and d_brier < -abs(cal_mde))

    if not non_inferior:
        verdict = "NO_SHIP_DISCRIMINATION"
        why = (f"merit AUC {arms['merit']:.4f} against {best_public} "
               f"{arms[best_public]:.4f}, a deficit of {abs(d_auc):.4f} that exceeds "
               f"the {abs(mde) if mde else float('nan'):.4f} detection floor. The "
               f"calibration leg is not read, because a model that ranks materially "
               f"worse does not get to win on a second metric.")
    elif cal_wins:
        verdict = "SHIP"
        why = (f"non-inferior on discrimination and better calibrated: Brier "
               f"{cal['merit']['brier']:.4f} against {cal[best_public]['brier']:.4f}.")
    else:
        verdict = "NO_SHIP_CALIBRATION"
        why = (f"non-inferior on discrimination ({arms['merit']:.4f} against "
               f"{arms[best_public]:.4f}) but the calibration gain does not clear its "
               f"own floor: Brier delta {d_brier:+.4f} against a {abs(cal_mde) if cal_mde else float('nan'):.4f} floor.")

    out = {
        "generated_at": __import__("datetime").date.today().isoformat(),
        "produced_by": "tools/hof_merit.py",
        "label": label,
        "gate": ("calibration-first: NON-INFERIOR on discrimination against the best "
                 "public arm, then better on Brier. Discrimination alone is already "
                 "lost and the bake-off says so; a ranking that is no better "
                 "calibrated is not a product."),
        "n_scored": len(scored), "n_positive": int(n_pos),
        "base_rate": round(n_pos / len(scored), 4) if len(scored) else None,
        "features": list(FEATURES) + [f"pos_{p}" for p in POS_LEVELS],
        "features_are_in_house_only": ("a public arm as a feature would score the model "
                                       "against its own input"),
        "burn_in_year": burn,
        "best_public_arm": best_public,
        "auc": arms,
        "calibration": cal,
        "discrimination_gate": disc_gate,
        "calibration_gate": cal_gate,
        "delta_auc_vs_best_public": round(d_auc, 6),
        "delta_brier_vs_best_public": round(d_brier, 6),
        "non_inferior_on_discrimination": bool(non_inferior),
        "verdict": verdict,
        "why": why,
        "folds": blocks,
        "common_support_drop": drop,
    }
    if persist:
        OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    r = run(persist="--dry" not in sys.argv)
    print(f"n={r['n_scored']} pos={r['n_positive']} base={r['base_rate']}")
    print(f"best public arm: {r['best_public_arm']} AUC {r['auc'][r['best_public_arm']]:.4f}")
    print(f"merit AUC {r['auc']['merit']:.4f}  delta {r['delta_auc_vs_best_public']:+.4f}")
    print(f"merit Brier {r['calibration']['merit']['brier']:.4f}  "
          f"{r['best_public_arm']} Brier {r['calibration'][r['best_public_arm']]['brier']:.4f}")
    print(f"VERDICT: {r['verdict']}")
    print(f"   {r['why']}")
