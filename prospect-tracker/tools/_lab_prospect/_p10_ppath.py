"""Lane: prospect. (d) VERIFY the prospect_path alpha-selection change landed and
measure whether it moved the SERVED output.

Served output of prospect_path = data/prospect_path_eval.json
  calibration_intercept_only.full_window_shift   -> proj_export._prospect_calibration_shift()
  challenger/baseline blocks                     -> the /projections/ methodology
                                                    "backtests" disclosure block.
Runs the module with the SHIPPED 5-fold _fit_ridge and then with the OLD single
20% holdout monkeypatched back in, on identical rows, persist=False.
"""
import json, sys, time
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import prospect_path as pp

# ---- rebuild the OLD selector exactly as it was before the 2026-07-24 edit ----
def _fit_ridge_old(train, keys):
    if len(train) < 40:
        return None
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in train])
    y = np.array([r["target"] for r in train])
    wts = np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in train]), 1e-3, None)
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd == 0] = 1.0
    Xs = (X - mu) / sd
    n = len(train)
    def _wmean(idx):
        ww = wts[idx]
        return float(np.average(y[idx], weights=ww)) if ww.sum() > 0 else float(y[idx].mean())
    def _wridge(idx, alpha, b):
        Xi, wi = Xs[idx], wts[idx]
        WX = Xi * wi[:, None]
        A = WX.T @ Xi + alpha * np.eye(len(keys))
        return np.linalg.solve(A, WX.T @ (y[idx] - b))
    order = np.random.default_rng(pp._RIDGE_HOLDOUT_SEED).permutation(n)
    k = max(1, n // 5)
    ho, tri = order[:k], order[k:]
    b_tr = _wmean(tri)
    best = None
    for alpha in pp._ALPHAS:
        w = _wridge(tri, alpha, b_tr)
        pred = Xs[ho] @ w + b_tr
        mae = (float(np.average(np.abs(pred - y[ho]), weights=wts[ho]))
               if wts[ho].sum() > 0 else float(np.abs(pred - y[ho]).mean()))
        if best is None or mae < best[0]:
            best = (mae, alpha)
    alpha = best[1]
    b = _wmean(np.arange(n))
    w = _wridge(np.arange(n), alpha, b)
    return {"keys": keys, "mu": mu.tolist(), "sd": sd.tolist(),
            "w": w.tolist(), "b": float(b), "alpha": alpha}

# instrument alpha selection
picked = {"new": [], "old": []}
_new = pp._fit_ridge
def wrap(fn, tag):
    def inner(train, keys):
        m = fn(train, keys)
        if m:
            picked[tag].append((len(train), m["alpha"]))
        return m
    return inner

t = time.time()
pp._fit_ridge = wrap(_new, "new")
rep_new = pp.run(persist=False)
print("5-fold run: %.1fs" % (time.time() - t))
pp._fit_ridge = wrap(_fit_ridge_old, "old")
rep_old = pp.run(persist=False)

print("\nalphas picked, 5-fold CV     :", picked["new"])
print("alphas picked, old 20% holdout:", picked["old"])
same = [a for _, a in picked["new"]] == [a for _, a in picked["old"]]
print("SAME ALPHA AT PRODUCTION n:", same)

print("\n--- SERVED FIELD: calibration_intercept_only.full_window_shift ---")
a = rep_new["calibration_intercept_only"]; b = rep_old["calibration_intercept_only"]
print("  5-fold:", a["full_window_shift"], "ship=", a["ship"])
print("  old   :", b["full_window_shift"], "ship=", b["ship"])
print("  committed artifact:",
      json.loads((ROOT/'data'/'prospect_path_eval.json').read_text(encoding='utf-8'))
      .get("calibration_intercept_only", {}).get("full_window_shift"))

print("\n--- DISCLOSED backtest block (methodology surface) ---")
for k in ("challenger_pooled_oos", "baseline_pooled_oos",
          "baseline_intercept_only_pooled_oos", "baseline_on_intercept_rows"):
    print(f"  {k:38s} 5fold={rep_new.get(k)}")
    print(f"  {'':38s} old  ={rep_old.get(k)}")
print("\nship_decision:", rep_new["ship_decision"], "|", rep_old["ship_decision"])

# byte-level diff of everything except the timestamp
sa = json.dumps({k: v for k, v in rep_new.items() if k != "generated_at"}, sort_keys=True)
sb = json.dumps({k: v for k, v in rep_old.items() if k != "generated_at"}, sort_keys=True)
print("\nFULL ARTIFACT IDENTICAL (ex-timestamp):", sa == sb)
if sa != sb:
    for k in rep_new:
        if k == "generated_at":
            continue
        if json.dumps(rep_new[k], sort_keys=True) != json.dumps(rep_old[k], sort_keys=True):
            print("   DIFFERS:", k)
