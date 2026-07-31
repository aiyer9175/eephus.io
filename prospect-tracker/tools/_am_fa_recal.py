# AUDIT LANE `fa`. (b) ATTACK THE LARGEST BLOCK: predicted-guarantee compression.
"""Is the Gate-2 under-prediction a fixable calibration defect, or is it the
MAE-optimal shrinkage it is supposed to be?

THE OBSERVATION (tools/_am_fa_decomp.py, pinned corpus B, n=1,199):
  bias by actual deal size   <$5M +1.05 | $5-20M -2.62 | $20-50M -13.37
                             $50-100M -24.76 | $100-200M -42.82 | >=$200M -122.01
  at >=$200M the bias EQUALS the MAE, i.e. all 15 of the largest contracts in
  twelve winters are under-predicted. Same one-sided pattern in both stages:
  term is short on every actual term >= 2, rate is short on every AAV >= $5M.

THE PROTOCOL, fixed before any result was looked at:
  * recalibration map fitted ONLY on out-of-fold predictions from winters
    strictly before the test winter (a nested forward chain; the OOF set for
    winter W is every earlier winter's held-out prediction, never an in-sample
    fit, because an in-sample fit would hide the very compression at issue).
  * paired bootstrap resampling the whole signing corpus with a FULL refit of
    the chain on every draw.
  * zero-information control = the SAME estimator on a row-permuted twin of
    the pred column used to fit the map.
  * effect reported per winter across 9 independent forward splits.
  * NOTE THE PRIOR: MAE is minimised by the conditional MEDIAN, so shrinkage
    toward the middle is MAE-OPTIMAL under uncertainty. De-shrinking is
    expected to cut BIAS and RAISE MAE. Both are reported; the gate metric is
    MAE and it decides.
"""
from __future__ import annotations

import math
import pickle
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import _am_fa            # noqa: E402
import _am_fa_gate2 as g2  # noqa: E402


def corpusB():
    with open(_am_fa.SCRATCH / "fa_enriched_signings_B.pkl", "rb") as fh:
        return pickle.load(fh)


def oof_chain(enriched, min_train=100):
    """Out-of-fold predictions for EVERY winter that has a trainable history,
    not just the scored ones. The extra early winters are what the
    recalibration map for the first scored winter is fitted on."""
    import fa_market as fm
    winters = sorted({s["class_year"] for s in enriched})
    infl = fm._dpw_inflation()
    rows = []
    for W in winters:
        train = [s for s in enriched if s["class_year"] < W]
        test = [s for s in enriched if s["class_year"] == W]
        if len(train) < min_train or not test:
            continue
        dpw = fm.dollars_per_war_by_winter(train)
        model = fm.MarketModel(train, dpw)
        model.supply_by_year[W] = fm._supply(test, W)
        for s in test:
            pred = model.predict(s)
            comps = fm.comps_for(s, train)
            if not comps:
                continue
            b_guar = statistics.median(
                (c.get("npv_guarantee_usd") or c["guarantee_usd"])
                * ((1 + infl) ** (W - c["class_year"])) for c in comps)
            act_g = fm._npv_of(s)
            rows.append({
                "winter": W, "player": s["player_name"],
                "act_guar": act_g / 1e6,
                "pred_guar": pred["proj_guarantee_usd"] / 1e6,
                "base_guar": b_guar / 1e6,
                "act_years": float(s["years"]),
                "pred_years": float(pred["proj_years"]),
                "pos_group": fm._pos_group(s.get("position")),
            })
    return rows


def fit_loglin(pairs, ridge=1e-6):
    """log(act) = a + b*log(pred). Returns (a, b)."""
    xs = [math.log(max(p, 0.05)) for p, _ in pairs]
    ys = [math.log(max(a, 0.05)) for _, a in pairs]
    n = float(len(xs))
    if n < 20:
        return (0.0, 1.0)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs) + ridge
    b = num / den if den > 0 else 1.0
    return (my - b * mx, b)


def apply_map(kind, params, pred):
    if kind == "off":
        return pred
    a, b = params
    if kind == "shift":
        return math.exp(a) * pred          # b forced to 1 at fit time
    return math.exp(a) * (max(pred, 0.05) ** b)


def score(rows, kind, permute_seed=0, scored_from=2018):
    """Apply a forward-chained recalibration and score the SCORED winters."""
    rng = random.Random(permute_seed) if permute_seed else None
    by_w = defaultdict(list)
    for r in rows:
        by_w[r["winter"]].append(r)
    out = []
    for W in sorted(by_w):
        if W < scored_from:
            continue
        prior = [r for r in rows if r["winter"] < W]
        if len(prior) < 50:
            continue
        preds = [r["pred_guar"] for r in prior]
        if rng is not None:                      # zero-information control
            preds = preds[:]
            rng.shuffle(preds)
        pairs = list(zip(preds, [r["act_guar"] for r in prior]))
        if kind == "shift":
            # intercept only: mean log ratio, slope pinned to 1
            a = sum(math.log(max(act, .05) / max(p, .05)) for p, act in pairs) / len(pairs)
            params = (a, 1.0)
        else:
            params = fit_loglin(pairs)
        for r in by_w[W]:
            out.append({**r, "recal_guar": apply_map(kind, params, r["pred_guar"]),
                        "_a": params[0], "_b": params[1]})
    return out


def summarize(scored, tag):
    n = len(scored)
    mae = sum(abs(r["recal_guar"] - r["act_guar"]) for r in scored) / n
    bias = sum(r["recal_guar"] - r["act_guar"] for r in scored) / n
    mega = [r for r in scored if r["act_guar"] >= 100]
    mmae = sum(abs(r["recal_guar"] - r["act_guar"]) for r in mega) / len(mega) if mega else float("nan")
    mbias = sum(r["recal_guar"] - r["act_guar"] for r in mega) / len(mega) if mega else float("nan")
    return {"tag": tag, "n": n, "mae": mae, "bias": bias,
            "mega_mae": mmae, "mega_bias": mbias, "mega_n": len(mega),
            "b": scored[-1]["_b"], "a": scored[-1]["_a"]}


if __name__ == "__main__":
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    c = corpusB()
    rows = oof_chain(c)
    print("OOF chain: n=%d rows over winters %s"
          % (len(rows), sorted({r["winter"] for r in rows})))
    arms = {"off": 0, "shift": 0, "loglin": 0}
    res = {}
    for k in arms:
        s = score(rows, k)
        res[k] = summarize(s, k)
        r = res[k]
        print("  %-8s n=%d  MAE %8.4f  bias %+8.4f | mega n=%d MAE %8.3f bias %+8.3f | a=%+.4f b=%.4f"
              % (k, r["n"], r["mae"], r["bias"], r["mega_n"], r["mega_mae"],
                 r["mega_bias"], r["a"], r["b"]))
    for seed in (3, 7):
        s = score(rows, "loglin", permute_seed=seed)
        r = summarize(s, "loglin_perm%d" % seed)
        print("  %-8s n=%d  MAE %8.4f  bias %+8.4f | mega MAE %8.3f | a=%+.4f b=%.4f  <-- ZERO-INFO CONTROL"
              % (r["tag"], r["n"], r["mae"], r["bias"], r["mega_mae"], r["a"], r["b"]))

    print("\n  per-winter MAE (independent forward splits)")
    bw = {k: defaultdict(list) for k in arms}
    for k in arms:
        for r in score(rows, k):
            bw[k][r["winter"]].append(abs(r["recal_guar"] - r["act_guar"]))
    print("  %-6s %5s %9s %9s %9s" % ("winter", "n", "off", "shift", "loglin"))
    for w in sorted(bw["off"]):
        print("  %-6d %5d %9.3f %9.3f %9.3f"
              % (w, len(bw["off"][w]),
                 sum(bw["off"][w]) / len(bw["off"][w]),
                 sum(bw["shift"][w]) / len(bw["shift"][w]),
                 sum(bw["loglin"][w]) / len(bw["loglin"][w])))

    if B:
        print("\n  paired bootstrap, FULL chain refit per draw, B=%d" % B)
        rng = random.Random(20260725)
        acc = {k: [] for k in ("shift", "loglin")}
        accb = {k: [] for k in ("shift", "loglin")}
        for i in range(B):
            draw = [c[rng.randrange(len(c))] for _ in range(len(c))]
            try:
                rr = oof_chain(draw)
                base = summarize(score(rr, "off"), "off")
                for k in acc:
                    s = summarize(score(rr, k), k)
                    acc[k].append(s["mae"] - base["mae"])
                    accb[k].append(abs(s["bias"]) - abs(base["bias"]))
            except Exception as e:                      # noqa: BLE001
                print("    draw %d failed: %s" % (i, e))
        for k in acc:
            v = sorted(acc[k])
            vb = sorted(accb[k])
            if not v:
                continue
            print("    %-7s dMAE  %+0.4f  CI95 [%+0.4f, %+0.4f]  P(improves)=%.3f"
                  % (k, sum(v) / len(v), v[int(.025 * len(v))], v[int(.975 * len(v))],
                     sum(1 for x in v if x < 0) / len(v)))
            print("    %-7s d|bias| %+0.4f  CI95 [%+0.4f, %+0.4f]  P(improves)=%.3f"
                  % (k, sum(vb) / len(vb), vb[int(.025 * len(vb))],
                     vb[int(.975 * len(vb))], sum(1 for x in vb if x < 0) / len(vb)))
