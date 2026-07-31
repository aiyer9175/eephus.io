# SCRATCH: paired bootstrap (resamples TRAIN AND TEST, REFITS every draw) +
# permutation null band for every archetype mechanism arm.
# Implements docs/EFV_GATE_STANDARD.md section 2 items 1, 3 (item 2 = the *_CTRL
# arms, item 4 = the 6 forward-chained folds).
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_model as E                     # noqa: E402
import _arch_MECH as M                    # noqa: E402

SIDE = sys.argv[1] if len(sys.argv) > 1 else "hit"
B = int(sys.argv[2]) if len(sys.argv) > 2 else 400
MODE = sys.argv[3] if len(sys.argv) > 3 else "boot"      # boot | perm

keys, _ = E._feature_spec(SIDE)
axes = M.ARCH_AXES[SIDE]
data = M.load(SIDE, "production")
D0 = M.arrays(data, keys, axes)
lam = E.blend_lambda(SIDE)
MILB_KEYS = {"level_rank", "n_milb_seasons", "ops_rel", "obp_rel", "k_rel",
             "peak_k_rel", "age_rel_level", "age", "bb_rel", "era_rel", "x_era_k"}
CTX = {"milb_cols": [i for i, k in enumerate(keys) if k in MILB_KEYS],
       "comp_axes": D0["A"], "knn_k": 20, "k": 6, "seed": 11,
       "thin_cut": None, "omega": None}

ARMS = ["E1_STD_TR", "E1_CTRL", "E2_NOTRACK", "E2_CTRL", "E3_TR_ONLY", "E3_CTRL",
        "M1_ARCH", "M1_CTRL", "M2_COMP", "M2_CTRL",
        "M3_CONDCAL", "M3_CTRL", "M4_SHRINK", "M4_CTRL"]
MET = ("rho", "block_rho", "t45", "auc", "mae", "brier")
INV = ("mae", "brier")          # lower is better


def resample(D, rng, perm=False):
    n = len(D["y"])
    idx = np.arange(n) if perm else rng.integers(0, n, n)
    d = {k: (v[idx] if isinstance(v, np.ndarray) else v) for k, v in D.items()
         if k != "arch_cols"}
    d["arch_cols"] = D["arch_cols"]
    if perm:
        d["y"] = D["y"][rng.permutation(n)]
    return d


def one_draw(D, seed):
    rng = np.random.default_rng(seed)
    ctx = dict(CTX); ctx["comp_axes"] = D["A"]
    out = {}
    b = M.run_arm("BASE", D, M.FOLDS, lam, rng=rng, ctx=ctx)
    if b is None:
        return None
    base, base_t = M.score_arm(b), M.score_arm(b, True)
    if base is None or base_t is None:
        return None
    for arm in ARMS:
        r = M.run_arm(arm, D, M.FOLDS, lam, rng=np.random.default_rng(seed + 7), ctx=dict(ctx))
        s, st = M.score_arm(r), M.score_arm(r, True)
        for m in MET:
            sgn = -1.0 if m in INV else 1.0
            out[f"{arm}|{m}"] = (sgn * (s[m] - base[m])) if s else np.nan
            out[f"{arm}|tr_{m}"] = (sgn * (st[m] - base_t[m])) if (s and st) else np.nan
    for m in MET:
        out[f"BASE|abs_{m}"] = base[m]
    return out


t0 = time.time()
draws = []
for i in range(B):
    D = resample(D0, np.random.default_rng(9000 + i), perm=(MODE == "perm"))
    r = one_draw(D, 9000 + i)
    if r:
        draws.append(r)
    if (i + 1) % 25 == 0:
        print(f"  ... {i+1}/{B}  {time.time()-t0:.0f}s", file=sys.stderr, flush=True)

pt = one_draw(D0, 12345)          # point estimate on the real data
keys_all = sorted(draws[0])
res = {}
for k in keys_all:
    v = np.array([d.get(k, np.nan) for d in draws], float)
    v = v[~np.isnan(v)]
    if len(v) < 20:
        continue
    res[k] = {"point": pt.get(k), "mean": float(v.mean()), "sd": float(v.std(ddof=1)),
              "lo": float(np.percentile(v, 2.5)), "hi": float(np.percentile(v, 97.5)),
              "p_gt0": float((v > 0).mean()), "mde95": float(1.96 * v.std(ddof=1)),
              "n": len(v)}

SCRATCH = Path(r"C:\Users\noah\AppData\Local\Temp\claude"
               r"\c--Users-noah-baseball-projects-BaseballR"
               r"\c6ce73e3-6700-473f-beea-01f160967961\scratchpad")
SCRATCH.mkdir(parents=True, exist_ok=True)
out = SCRATCH / f"_arch_mech_{MODE}_{SIDE}.json"
out.write_text(json.dumps(res, indent=1), encoding="utf-8")
print(f"\nwrote {out}  B={len(draws)}  {time.time()-t0:.0f}s")

print(f"\n{'stat':<26}{'point':>9}{'boot mean':>11}{'sd':>9}{'CI95':>21}{'P>0':>7}{'MDE95':>9}")
for arm in ARMS:
    for m in MET:
        for pre in ("", "tr_"):
            k = f"{arm}|{pre}{m}"
            if k not in res:
                continue
            r = res[k]
            flag = ""
            if r["point"] is not None and abs(r["point"]) > r["mde95"]:
                flag = "  <-- exceeds its own MDE95"
            print(f"{k:<26}{r['point']:+9.4f}{r['mean']:+11.4f}{r['sd']:9.4f}"
                  f"  [{r['lo']:+.4f},{r['hi']:+.4f}]{r['p_gt0']:7.3f}{r['mde95']:9.4f}{flag}")
