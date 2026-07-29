# SCRATCH: LIVE-SERVED consequence of the level_rank / n_milb_seasons floor-impute.
# Read-only. Fits the production stack (train pool) and scores the LIVE matrix under
# (a) the shipped feature construction and (b) neutral imputes, then reports how far
# the served model leg moves and for whom.
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import efv_model as E
from _frontier_ablate import ridge_fit, ridge_pred, ols_fit, lincal, rho
import _sweep_structure as S

for side in ("hit", "pit"):
    d = S.D[side]
    keys = list(S.KEYS[side])
    tr = np.flatnonzero(d["keep"])
    live = json.loads((ROOT / "data" / ("xfv_live_pitcher_matrix.json" if side == "pit"
                                        else "xfv_live_hitter_matrix.json")).read_text("utf-8"))
    lv = [E._vec(r, side) for r in live]
    has = np.array([bool(r.get("milb")) for r in live])
    Xl = np.array([[v.get(k, 0.0) for k in keys] for v in lv], dtype=float)
    Xt = d["X"][:, [d["idx"][k] for k in keys]]
    rg = ridge_fit(Xt[tr], d["y"][tr], d["w"][tr])
    a, b = lincal(ridge_pred(rg, Xt[tr]), d["y"][tr])
    p0 = np.maximum(-2.0, a + b * ridge_pred(rg, Xl))
    # NEUTRAL variant: swap the two floor-imputed columns on BOTH train and live
    keys2 = [("level_rank_neutral" if k == "level_rank" else
              "n_milb_seasons_neutral" if k == "n_milb_seasons" else k) for k in keys]
    Xt2 = d["X"][:, [d["idx"][k] for k in keys2]]
    Xl2 = Xl.copy()
    for src, mu in (("level_rank", d["mu_lvl"]), ("n_milb_seasons", d["mu_nms"])):
        if src in keys:
            j = keys.index(src)
            Xl2[~has, j] = mu
    rg2 = ridge_fit(Xt2[tr], d["y"][tr], d["w"][tr])
    a2, b2 = lincal(ridge_pred(rg2, Xt2[tr]), d["y"][tr])
    p1 = np.maximum(-2.0, a2 + b2 * ridge_pred(rg2, Xl2))
    dlt = p1 - p0
    print(f"=== {side.upper()} live n={len(live)}  no-milb rows={int((~has).sum())} "
          f"({100*(~has).mean():.1f}%)")
    print(f"  shipped ridge weights: " + ", ".join(
        f"{k}={w:+.4f}" for k, w in zip(keys, rg[2]) if k in ("level_rank", "n_milb_seasons")))
    print(f"  neutral ridge weights: " + ", ".join(
        f"{k}={w:+.4f}" for k, w in zip(keys2, rg2[2])
        if k in ("level_rank_neutral", "n_milb_seasons_neutral")))
    print(f"  model-leg WAR delta (neutral - shipped): no-milb rows mean "
          f"{dlt[~has].mean():+.3f}  median {np.median(dlt[~has]):+.3f}  "
          f"| milb rows mean {dlt[has].mean():+.3f}")
    r0 = np.argsort(np.argsort(-p0)); r1 = np.argsort(np.argsort(-p1))
    mv = r1 - r0
    print(f"  board-rank movement (model leg alone): no-milb rows median "
          f"{np.median(mv[~has]):+.0f} places, p10/p90 "
          f"{np.percentile(mv[~has],10):+.0f}/{np.percentile(mv[~has],90):+.0f}"
          f"  | all rows |median| {np.median(np.abs(mv)):.0f}")
    print(f"  Spearman(shipped, neutral) over the whole live board = {rho(p0, p1):.4f}")
