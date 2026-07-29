"""FA measurement lab (SCRATCH — writes nothing into data/).

Forward-chained Gate-2 replica with the docs/EFV_GATE_STANDARD.md controls:
  1. paired bootstrap resampling TRAIN and TEST with a refit on every draw
  2. a zero-information control beside every claim
  3. a permutation null band
  4. the effect averaged over >= 4 independent time splits (9 winters here)

Usage:
    python tools/_fa_lab.py bake                 # cache the enriched corpus
    python tools/_fa_lab.py point  <arm>         # single-shot chain, no bootstrap
    python tools/_fa_lab.py boot   <arm> [B] [W] # paired bootstrap vs champion
"""
from __future__ import annotations

import json
import math
import os
import pickle
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

SCRATCH = (r"C:\Users\noah\AppData\Local\Temp\claude"
           r"\c--Users-noah-baseball-projects-BaseballR"
           r"\c6ce73e3-6700-473f-beea-01f160967961\scratchpad")
os.makedirs(SCRATCH, exist_ok=True)
PKL = os.path.join(SCRATCH, "enriched.pkl")

WARMUP_THROUGH = 2017
TEST_YEARS = list(range(2018, 2027))


# ---------------------------------------------------------------- corpus ---
def bake() -> list[dict]:
    import fa_market as fm
    e = fm.enriched_signings(2015, 2026)
    with open(PKL, "wb") as f:
        pickle.dump(e, f)
    return e


def load() -> list[dict]:
    if not os.path.exists(PKL):
        return bake()
    with open(PKL, "rb") as f:
        return pickle.load(f)


# ------------------------------------------------------------------ arms ---
# An ARM is a dict of fa_market module knobs. {} == the shipped champion.
ARMS: dict[str, dict] = {
    "champ": {},
    # BUG-3: comps_for must not let a train row see its own winter.
    "strict_comps": {"COMPS_STRICT_PRIOR": True},
    # BUG-2 / O2: FA-owned de-staling series instead of the dead vf knob.
    "destale_series": {"DESTALE_MODE": "series"},
    "destale_fixed": {"DESTALE_MODE": "fixed", "DESTALE_FIXED": 0.0355},
    # sign-flipped control: same magnitude, economically backwards.
    "destale_neg": {"DESTALE_MODE": "fixed", "DESTALE_FIXED": -0.0355},
    # BUG-6 / O6: wire the ridge.
    "ridge0.1": {"RIDGE_GUAR": 0.1, "RIDGE_YEARS": 0.1},
    "ridge0.3": {"RIDGE_GUAR": 0.3, "RIDGE_YEARS": 0.3},
    "ridge1.0": {"RIDGE_GUAR": 1.0, "RIDGE_YEARS": 1.0},
    "ridge3.0": {"RIDGE_GUAR": 3.0, "RIDGE_YEARS": 3.0},
    # BUG-4 / O9: AAV priced at the term it was priced for.
    "aav_consistent": {"AAV_CONSISTENT": True},
    "aav_reprice": {"AAV_CONSISTENT": "reprice"},
    # level recalibration (nested-CV, ex-ante)
    "recal_shift": {"RECAL_MODE": "shift"},
    # RE-GATE the two shipped Gate-2 features under the standard.
    "no_rate_line": {"X_OFF": ["rate_line"]},
    "recal_line": {"RECAL_MODE": "line"},
    "recal_line_destale": {"RECAL_MODE": "line", "DESTALE_MODE": "series"},
    "recal_shift_destale": {"RECAL_MODE": "shift", "DESTALE_MODE": "series"},
    # O5: split the POS bucket.
    "posgroup5": {"POS_GROUP_MODE": "v2"},
    # O7: TJ durability.
    "tj": {"X_TJ": True},
    "tj_ctl": {"X_TJ": True, "TJ_PERMUTE": 1},
    # O2+O6+O3 stack
    "stack": {"COMPS_STRICT_PRIOR": True, "DESTALE_MODE": "series",
              "RIDGE_GUAR": 0.3, "RIDGE_YEARS": 0.3},
}
# Zero-information placebos: k extra pure-noise columns in the guarantee
# stage. These calibrate "how much does adding k parameters move the
# forward-chained MAE on its own".
for _k in (1, 3):
    for _sd in range(1, 9):
        ARMS[f"noise{_k}_{_sd}"] = {"X_NOISE": True, "NOISE_FEATURES": _k,
                                    "NOISE_SEED": _sd}
for _sd in range(1, 9):
    ARMS[f"tjctl{_sd}"] = {"X_TJ": True, "TJ_PERMUTE": _sd}
# de-staling rate sweep (is the effect a rate-level effect or an artifact?)
for _r in (-0.06, -0.04, -0.02, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10):
    ARMS[f"destale{_r:+.2f}"] = {"DESTALE_MODE": "fixed", "DESTALE_FIXED": _r}


def apply_arm(arm: dict) -> None:
    import fa_market as fm
    fm.LAB_RESET()
    for k, v in arm.items():
        if k == "X_TJ":
            fm.X_FEATURES["tj"] = bool(v)
        elif k == "X_OFF":
            for f in v:
                fm.X_FEATURES[f] = False
        elif k == "X_NOISE":
            fm.X_FEATURES["noise"] = bool(v)
        else:
            setattr(fm, k, v)
    if arm.get("TJ_PERMUTE"):
        fm.LAB_TJ_PERMUTE_SEED = int(arm["TJ_PERMUTE"])


# ------------------------------------------------------------------ eval ---
def _mae(pairs):
    return statistics.mean(abs(p - a) for p, a in pairs) if pairs else None


def chain(pool: list[dict], arm: dict, want_rows: bool = False) -> dict:
    """Forward-chained Gate-2 replica. Returns pooled + per-winter metrics."""
    import fa_market as fm
    apply_arm(arm)
    rows = []
    per_winter = []
    for W in TEST_YEARS:
        train = [s for s in pool if s["class_year"] < W]
        test = [s for s in pool if s["class_year"] == W]
        if len(train) < 100 or not test:
            continue
        dpw_series = fm.dollars_per_war_by_winter(train)
        model = fm.MarketModel(train, dpw_series)
        model.supply_by_year[W] = fm._supply(test, W)
        infl = fm._destale_rate(dpw_series, W)
        wrows = []
        for s in test:
            comps = fm.comps_for(s, train)
            if not comps:
                continue
            pred = model.predict(s)
            b_guar = statistics.median(
                (c.get("npv_guarantee_usd") or c["guarantee_usd"])
                * ((1 + infl) ** (W - c["class_year"])) for c in comps)
            b_years = statistics.median(c["years"] for c in comps)
            act_g, act_y = fm._npv_of(s), float(s["years"])
            wrows.append({
                "winter": W, "name": s.get("player_name"),
                "pos": fm._pos_group(s.get("position")),
                "age": s["_age"], "qo": bool(s.get("qo")),
                "pg": pred["proj_guarantee_usd"] / 1e6, "ag": act_g / 1e6,
                "bg": b_guar / 1e6,
                "py": float(pred["proj_years"]), "ay": act_y,
                "by": float(b_years),
                "pa": pred["proj_aav_usd"] / 1e6,
                "aa": act_g / max(act_y, 1) / 1e6,
                "ba": b_guar / max(b_years, 1) / 1e6,
                "side": "pit" if fm._pos_group(s.get("position")) in ("SP", "RP") else "hit",
            })
        if not wrows:
            continue
        per_winter.append({
            "winter": W, "n": len(wrows),
            "guar_m": _mae([(r["pg"], r["ag"]) for r in wrows]),
            "guar_b": _mae([(r["bg"], r["ag"]) for r in wrows]),
            "aav_m": _mae([(r["pa"], r["aa"]) for r in wrows]),
            "aav_b": _mae([(r["ba"], r["aa"]) for r in wrows]),
            "yrs_m": _mae([(r["py"], r["ay"]) for r in wrows]),
            "yrs_b": _mae([(r["by"], r["ay"]) for r in wrows]),
        })
        rows.extend(wrows)
    mega = [r for r in rows if r["ag"] >= 100.0]
    out = {
        "n": len(rows),
        "guar_mae": _mae([(r["pg"], r["ag"]) for r in rows]),
        "guar_base": _mae([(r["bg"], r["ag"]) for r in rows]),
        "guar_bias": statistics.mean(r["pg"] - r["ag"] for r in rows) if rows else None,
        "aav_mae": _mae([(r["pa"], r["aa"]) for r in rows]),
        "yrs_mae": _mae([(r["py"], r["ay"]) for r in rows]),
        "mega_mae": _mae([(r["pg"], r["ag"]) for r in mega]),
        "mega_n": len(mega),
        "per_winter": per_winter,
    }
    if want_rows:
        out["rows"] = rows
    return out


# ------------------------------------------------------- paired bootstrap ---
def _resample(pool, rng):
    """Stratified-by-winter resample with replacement (preserves the
    forward-chain structure; a winter never changes size)."""
    by = defaultdict(list)
    for s in pool:
        by[s["class_year"]].append(s)
    out = []
    for y, rowsy in by.items():
        n = len(rowsy)
        out.extend(rowsy[rng.randrange(n)] for _ in range(n))
    return out


def _one_draw(args):
    """One paired bootstrap draw: resample the WHOLE pool (train AND test),
    then REFIT the champion and every candidate on that same draw."""
    seed, arm_names, metrics = args
    import random
    rng = random.Random(seed)
    draw = _resample(load(), rng)
    out = {}
    for a in ("champ",) + tuple(arm_names):
        r = chain(draw, ARMS[a])
        out[a] = {m: r.get(m) for m in metrics}
    return out


def boot(arm_names, B: int = 200, metrics=("guar_mae",), workers: int = 24):
    from concurrent.futures import ProcessPoolExecutor
    arm_names = tuple(arm_names)
    metrics = tuple(metrics)
    args = [(1000 + i, arm_names, metrics) for i in range(B)]
    draws = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(_one_draw, args, chunksize=1):
            draws.append(r)
    res = {"B": len(draws), "arms": {}}
    for m in metrics:
        vals = [d["champ"][m] for d in draws if d["champ"][m] is not None]
        res.setdefault("champ", {})[m] = statistics.mean(vals) if vals else None
    for a in arm_names:
        res["arms"][a] = {}
        for m in metrics:
            deltas = sorted(d[a][m] - d["champ"][m] for d in draws
                            if d[a][m] is not None and d["champ"][m] is not None)
            n = len(deltas)
            res["arms"][a][m] = {
                "cand_mean": statistics.mean(x for x in (d[a][m] for d in draws)
                                             if x is not None),
                "delta_mean": statistics.mean(deltas),
                "delta_sd": statistics.pstdev(deltas),
                "ci95": [deltas[int(0.025 * n)], deltas[min(n - 1, int(0.975 * n))]],
                "p_improves": sum(1 for d in deltas if d < 0) / n,
            }
    return res


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "point"
    if cmd == "bake":
        print("enriched", len(bake()))
    elif cmd == "point":
        arm = sys.argv[2] if len(sys.argv) > 2 else "champ"
        r = chain(load(), ARMS[arm])
        r.pop("rows", None)
        print(json.dumps(r, indent=1, default=float))
    elif cmd == "boot":
        arm = sys.argv[2]
        B = int(sys.argv[3]) if len(sys.argv) > 3 else 200
        metric = sys.argv[4] if len(sys.argv) > 4 else "guar_mae"
        print(json.dumps(boot(arm, B, metric), indent=1, default=float))
