# scratch verification for roleconditioned.py: paired bootstrap + mid-side rank diagnostics
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import efv_pitcher_label_harness as H  # noqa: E402
from prospect_path import _spearman, _fit_ridge, _predict  # noqa: E402
from efv_model import _vec, _fit_ols_fv, _pred_ols, _feature_spec  # noqa: E402
import roleconditioned as RC  # noqa: E402

SPAN = int(sys.argv[1]) if len(sys.argv) > 1 else 3


def blend_preds(train_pairs, test_recs, side="pit"):
    keys, _m = _feature_spec(side)
    data = [{"feats": _vec(r["row"], side), "target": float(t),
             "fv": float(r["row"]["consensus_fv_raw"]), "player_key": r["pk"]}
            for r, t in train_pairs if t is not None]
    ridge = _fit_ridge(data, keys)
    ols = _fit_ols_fv(data)
    lam = H.LAM_PIT
    out = []
    for r in test_recs:
        f = _vec(r["row"], side)
        p = _predict(ridge, f)
        out.append((1 - lam) * max(0.0, _pred_ols(ols, float(r["row"]["consensus_fv_raw"]))) + lam * p)
    return out


def main():
    pool = H.build_pool("pit")
    early = [r for r in pool if H.EARLY[0] <= r["dy"] <= H.EARLY[1]]
    mid = [r for r in pool if H.MID[0] <= r["dy"] <= H.MID[1]]
    test = [r for r in pool if H.TEST[0] <= r["dy"] <= H.TEST[1]]
    y = [r["true6"] for r in test]
    print(f"span={SPAN} early={len(early)} mid={len(mid)} test={len(test)}")

    state = RC.fit(early)
    labels = {"A_KM": [H.km_label(r, SPAN) for r in mid],
              "C_oracle": [r["true6"] for r in mid]}
    for arm in ("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"):
        labels[arm] = [RC.predict(state, r, SPAN, arm) for r in mid]
    # drop-the-block control (the free-gain fallback)
    base_pairs = [(r, r["true6"]) for r in early]

    preds = {}
    for k, lab in labels.items():
        preds[k] = blend_preds(base_pairs + list(zip(mid, lab)), test)
    preds["Z_drop_mid"] = blend_preds(base_pairs, test)

    print("\nTEST blend rho:")
    for k, p in preds.items():
        print(f"  {k:12} {_spearman(p, y):.4f}")

    rng = random.Random(17)
    n = len(test)
    base = preds["A_KM"]
    print("\nPAIRED bootstrap vs A_KM (B=2000, resample test rows):")
    for k in ("C_oracle", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "Z_drop_mid"):
        d = []
        for _ in range(2000):
            idx = [rng.randrange(n) for _ in range(n)]
            yy = [y[i] for i in idx]
            d.append(_spearman([preds[k][i] for i in idx], yy)
                     - _spearman([base[i] for i in idx], yy))
        d.sort()
        m = sum(d) / len(d)
        sd = (sum((x - m) ** 2 for x in d) / (len(d) - 1)) ** 0.5
        pos = sum(1 for x in d if x > 0) / len(d)
        print(f"  {k:12} delta {m:+.4f} sd {sd:.4f} CI95 [{d[50]:+.4f},{d[1949]:+.4f}] P(>0)={pos:.3f}")

    # ---- mid-side (tuning-legal) rank diagnostics -------------------------
    tm = [r["true6"] for r in mid]
    order = sorted(range(len(mid)), key=lambda i: -tm[i])
    topq = set(order[:max(1, len(mid) // 4)])
    topd = set(order[:max(1, len(mid) // 10)])
    print("\nMID label diagnostics (n=%d):" % len(mid))
    print(f"  {'label':10} {'rho_all':>8} {'rho_topQ':>9} {'topD_recall':>12} {'mae':>7}")
    for k in ("A_KM", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"):
        lab = labels[k]
        ti = [i for i in range(len(mid)) if i in topq]
        rq = _spearman([lab[i] for i in ti], [tm[i] for i in ti])
        pred_top = set(sorted(range(len(mid)), key=lambda i: -lab[i])[:len(topd)])
        rec = len(pred_top & topd) / len(topd)
        mae = sum(abs(lab[i] - tm[i]) for i in range(len(mid))) / len(mid)
        print(f"  {k:10} {_spearman(lab, tm):>8.4f} {rq:>9.4f} {rec:>12.2f} {mae:>7.3f}")


main()
