"""AM-PROJ (c): CONDITIONAL band calibration of the SHIPPED engine.

proj_horizon_eval reports MARGINAL coverage only. This harness records every
(pred p10/p50/p90, actual, survived) pair together with the covariates the
bands are supposed to be conditionally calibrated on -- age, playing-time
(exposure) band, side, role (SP/RP), and predicted level -- for BOTH engines:

  champion  = marcel_decay_v2 (use_ml=False), the registered baseline
  shipped   = proj_lgbm_v1 quantile heads, POINT-IN-TIME (bundle trained on
              labels <= B-1), which is what /projections/ and /fa/ serve

Forward-chained: bases with a point-in-time bundle already cached under the
CURRENT schema tag. Nothing is fitted here, so the uncertainty is binomial:
se = sqrt(p(1-p)/n), z = (cov - 0.80)/se. Writes a scratch JSON only.
"""
import json
import sys
import time
from collections import defaultdict
from math import sqrt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fa_market as fm  # noqa: E402
import fa_projection as fp  # noqa: E402
import proj_ml  # noqa: E402

H = 5
NOMINAL = 0.80
BASES = [int(x) for x in (sys.argv[1].split(",") if len(sys.argv) > 1
                          else "2017,2018,2022,2023,2024".split(","))]

corpus = fp.build_corpus()
league = corpus["league"]
by_player = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
war_actual = {}
for side in ("hit", "pit"):
    for r in corpus[side]:
        if r.get("mlbam"):
            by_player[side][r["mlbam"]][r["season"]] = r
            if r.get("war") is not None:
                war_actual[(r["mlbam"], r["season"])] = (
                    war_actual.get((r["mlbam"], r["season"]), 0.0) + r["war"])

rows = []          # one dict per (player, base, horizon, engine)
t0 = time.time()
for B in BASES:
    curves, war_map = fp.fitted_models(corpus, B - 1)
    try:
        bundle = proj_ml.train_cached(corpus, B - 1)
    except Exception as e:                                  # noqa: BLE001
        print("base", B, "NO BUNDLE:", e)
        continue
    n_b = 0
    for side in ("hit", "pit"):
        for mlbam, seasons in by_player[side].items():
            hist = [seasons[t] for t in (B - 1, B - 2, B - 3) if t in seasons]
            if not hist:
                continue
            age_row = next((h for h in hist if h.get("age")), None)
            if age_row is None:
                continue
            age = age_row["age"] + (B - age_row["season"])
            paths = {}
            paths["champ"] = fm.contract_war_path(hist, side, B, H, age, curves,
                                                  war_map, league, use_ml=False)
            paths["ml"] = fm.contract_war_path(hist, side, B, H, age, curves,
                                               war_map, league, use_ml=True,
                                               ml_models=bundle)
            if paths["champ"] is None or paths["ml"] is None:
                continue
            n_b += 1
            expo = paths["champ"].get("pt_y1") or 0.0
            role = paths["champ"].get("role") or "?"
            for eng, path in paths.items():
                p10 = path.get("war_by_year_p10")
                p90 = path.get("war_by_year_p90")
                p50 = path.get("war_by_year")
                if not (p10 and p90 and p50):
                    continue
                for h in range(1, H + 1):
                    target = B + h - 1
                    if target > corpus["last"] - 1:
                        continue
                    act = war_actual.get((mlbam, target), 0.0)
                    rows.append({
                        "eng": eng, "base": B, "h": h, "side": side,
                        "role": role, "age": age, "expo": expo,
                        "pred": p50[h - 1], "lo": p10[h - 1], "hi": p90[h - 1],
                        "act": act,
                        "sv": 1 if (mlbam, target) in war_actual else 0,
                    })
    print(f"base {B}: {n_b} players, {time.time()-t0:.0f}s")

print("rows", len(rows))


def _age_bin(a):
    a = int(a)
    return "<25" if a < 25 else "25-29" if a < 30 else "30-34" if a < 35 else "35+"


def _expo_bin(e, side):
    # exposure = PA (hit) / BF (pit); thirds chosen on the shipped scale
    if side == "hit":
        return "pt:lo" if e < 200 else "pt:mid" if e < 450 else "pt:hi"
    return "pt:lo" if e < 200 else "pt:mid" if e < 500 else "pt:hi"


def cov(sub):
    if not sub:
        return None
    n = len(sub)
    k = sum(1 for r in sub if r["lo"] <= r["act"] <= r["hi"])
    p = k / n
    se = sqrt(max(p * (1 - p), 1e-9) / n)
    return {"n": n, "cov": round(p, 4), "se": round(se, 4),
            "z": round((p - NOMINAL) / se, 2)}


out = {"bases": BASES, "n_rows": len(rows), "nominal": NOMINAL, "cells": {}}
for eng in ("champ", "ml"):
    E = [r for r in rows if r["eng"] == eng]
    for scope, sel in (("all", lambda r: True), ("survived", lambda r: r["sv"] == 1)):
        S = [r for r in E if sel(r)]
        base_key = f"{eng}|{scope}"
        out["cells"][f"{base_key}|MARGINAL"] = cov(S)
        for h in range(1, H + 1):
            out["cells"][f"{base_key}|h{h}"] = cov([r for r in S if r["h"] == h])
        for b in ("<25", "25-29", "30-34", "35+"):
            out["cells"][f"{base_key}|age:{b}"] = cov([r for r in S if _age_bin(r["age"]) == b])
        for b in ("pt:lo", "pt:mid", "pt:hi"):
            out["cells"][f"{base_key}|{b}"] = cov(
                [r for r in S if _expo_bin(r["expo"], r["side"]) == b])
        for b in ("hit", "pit"):
            out["cells"][f"{base_key}|side:{b}"] = cov([r for r in S if r["side"] == b])
        for b in ("SP", "RP", "C", "H"):
            out["cells"][f"{base_key}|role:{b}"] = cov([r for r in S if r["role"] == b])

for k, v in out["cells"].items():
    if v:
        flag = "  <<< OFF" if abs(v["z"]) > 3 else ""
        print(f"{k:<34} n={v['n']:>6} cov={v['cov']:.4f} se={v['se']:.4f} z={v['z']:>8.2f}{flag}")

json.dump({"summary": out}, open(ROOT / "tools" / "_am_proj_out_cover.json", "w"), indent=1)
import pickle
pickle.dump(rows, open(ROOT / "tools" / "_am_proj_out_cover_rows.pkl", "wb"))
print("saved rows pickle")
