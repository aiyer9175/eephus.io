# P4 pWOBA EV-arm lab (pre-registered 2026-07-15)
#
# QUESTION (owner program: "improve pWOBA further using Statcast, EVs"): do
# EV/barrel features (avg_hit_speed, brl_pa, ev95percent) add forward signal
# ON TOP of the validated pWOBA (fa_projection woba_proj) — and on top of the
# P1 xwOBA output-blend if that passed?
#
# LEDGER POSITION: the 2026-06-23 rejection covered EV/barrel as proj_ml TREE
# features (full bundle, no lift). This is the residual-correction form at the
# OUTPUT layer, newly powered by the 2016-2023 statcast_batter cache backfill
# (was 2024+ only — ~2 pairs; now 8+).
#
# CANDIDATE: ev_corrected = base + OLS(residual ~ z(avg_hit_speed) + z(brl_pa)
# + z(ev95percent)) where base = the P1 winner arm if P1 passed its gate,
# else woba_proj. Residual OLS fit on TRAIN predictors <= 2018 ONLY, frozen.
# EV features z-scored within predictor season (park/era neutral).
#
# GATE (v1, seed 20260715, 2000 reps): ev_corrected vs base:
# paired iid-bootstrap lo95 >= 0. pass_under_v2 reported. Pair set = the P1
# lab's construction + EV row present at Savant attempts >= 100.
from __future__ import annotations

import csv
import json
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys  # noqa: E402
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import numpy as np  # noqa: E402

import plus_lab_harness as plh  # noqa: E402
from rem_plus_backtest import _spearman  # noqa: E402
from phem_marcel_lite_lab import FaEngine, dual_gate, load_hit_season, _r4  # noqa: E402
from xwoba_projection_blend_lab import (  # noqa: E402
    MIN_PA_NEXT, MIN_PA_Y, SAVANT_MIN_PA, SEASONS, TAG_MIN_PA,
    TAG_MIN_SEASONS, TRAIN_MAX_PRED_YEAR, _hem3_window, load_xwoba,
)

SEED = 20260715
BOOT = 2000
EV_MIN_ATTEMPTS = 100.0
EV_FEATS = ("avg_hit_speed", "brl_pa", "ev95percent")
SAVANT_DIR = ROOT / ".cache" / "savant_mlb"


def load_ev(year: int) -> dict[int, dict]:
    path = SAVANT_DIR / f"statcast_batter_{year}.csv"
    if not path.exists():
        return {}
    out: dict[int, dict] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            try:
                mid = int(r.get("player_id") or r.get(" player_id"))
                rec = {"attempts": float(r["attempts"])}
                for k in EV_FEATS:
                    rec[k] = float(r[k])
                out[mid] = rec
            except (KeyError, TypeError, ValueError):
                continue
    return out


def _zmap(ev_season: dict[int, dict]) -> dict[int, dict]:
    """Within-season z-scores of the EV features."""
    out = {}
    for k in EV_FEATS:
        vals = [v[k] for v in ev_season.values()]
        mu = float(np.mean(vals)) if vals else 0.0
        sd = float(np.std(vals)) or 1.0
        for mid, v in ev_season.items():
            out.setdefault(mid, {})[k] = (v[k] - mu) / sd
    return out


def main():
    t0 = time.time()
    eng = FaEngine()

    by_season = {}
    for y in sorted(set(SEASONS + [max(SEASONS) + 1])):
        s, _ = load_hit_season(y)
        if s:
            by_season[y] = s
    xw = {y: load_xwoba(y) for y in SEASONS}
    ev_raw = {y: load_ev(y) for y in SEASONS}
    ev = {y: _zmap({m: v for m, v in ev_raw[y].items()
                    if v["attempts"] >= EV_MIN_ATTEMPTS}) for y in SEASONS}
    print("EV coverage:", {y: len(v) for y, v in ev.items()})

    # Base arm: P1 winner if it passed, else raw woba_proj.
    p1_path = ROOT / "data" / "xwoba_projection_blend_eval.json"
    base_name, beta, gamma = "fa_projection", 0.0, 0.0
    if p1_path.exists():
        p1 = json.loads(p1_path.read_text(encoding="utf-8"))
        if p1.get("gate", {}).get("pass"):
            base_name = p1["winner_candidate"]
            beta = float(p1["frozen_hyperparams"]["beta"])
            gamma = float(p1["frozen_hyperparams"]["gamma"])
    print(f"base arm: {base_name} (beta={beta} gamma={gamma})")

    def _base_val(p):
        if base_name == "output_blend":
            return (1 - beta) * p["fa"] + beta * p["xw"]
        if base_name == "gap_corrected":
            return p["fa"] + gamma * p["gap"]
        return p["fa"]

    pairs = []
    drops = {"partial_outcome": 0, "window": 0, "age_missing": 0,
             "fa_proj_missing": 0, "savant_missing": 0, "ev_missing": 0}
    for y in SEASONS:
        cur, nxt = by_season.get(y), by_season.get(y + 1)
        if not cur or not nxt:
            continue
        for mid, a in cur.items():
            b = nxt.get(mid)
            if not b or (a["pa"] or 0) < MIN_PA_Y or (b["pa"] or 0) < MIN_PA_NEXT:
                continue
            if b["woba_raw"] is None or not plh.season_complete(y + 1):
                drops["partial_outcome"] += 1
                continue
            su, wpa = _hem3_window(by_season, mid, y)
            if su < TAG_MIN_SEASONS or wpa < TAG_MIN_PA:
                drops["window"] += 1
                continue
            if a.get("age") is None:
                drops["age_missing"] += 1
                continue
            pr = eng.proj("hit", int(mid), y, a["age"] + 1)
            fa_val = pr.get("woba_proj") if pr else None
            if fa_val is None:
                drops["fa_proj_missing"] += 1
                continue
            sv = xw.get(y, {}).get(int(mid))
            if not sv or sv["pa"] < SAVANT_MIN_PA:
                drops["savant_missing"] += 1
                continue
            e = ev.get(y, {}).get(int(mid))
            if not e:
                drops["ev_missing"] += 1
                continue
            pairs.append({"mid": mid, "y": y, "oy": y + 1, "tgt": b["woba_raw"],
                          "fa": fa_val, "xw": sv["est_woba"],
                          "gap": sv["est_woba"] - sv["woba"], "ev": e})
    train = [p for p in pairs if p["y"] <= TRAIN_MAX_PRED_YEAR]
    gate = [p for p in pairs if p["y"] > TRAIN_MAX_PRED_YEAR]
    print(f"pairs={len(pairs)} train={len(train)} gate={len(gate)} drops={drops}")

    # -- residual OLS on TRAIN only -------------------------------------------
    Xtr = np.array([[p["ev"][k] for k in EV_FEATS] for p in train])
    resid = np.array([p["tgt"] - _base_val(p) for p in train])
    X1 = np.column_stack([np.ones(len(train)), Xtr])
    coef, *_ = np.linalg.lstsq(X1, resid, rcond=None)
    frozen = {"base_arm": base_name,
              "residual_ols_coef": {"intercept": round(float(coef[0]), 5),
                                    **{k: round(float(c), 5)
                                       for k, c in zip(EV_FEATS, coef[1:])}},
              "train_pred_years": f"<= {TRAIN_MAX_PRED_YEAR}", "train_n": len(train)}
    print("frozen residual coefs:", frozen["residual_ols_coef"])

    def _ev_val(p):
        d = float(coef[0]) + sum(float(c) * p["ev"][k] for k, c in zip(EV_FEATS, coef[1:]))
        return _base_val(p) + d

    arms = {
        "base": [_base_val(p) for p in gate],
        "ev_corrected": [_ev_val(p) for p in gate],
    }
    tgt = [p["tgt"] for p in gate]
    rhos = {k: _spearman(v, tgt) for k, v in arms.items()}
    res = dual_gate("ev_corrected", arms, tgt,
                    [p["mid"] for p in gate], [p["y"] for p in gate],
                    [p["oy"] for p in gate])
    gap_v1 = res["v1"]["gap_ci_primary_minus"].get("base")
    gap_v2 = res["v2"]["gap_ci_primary_minus"].get("base")
    pass_v1 = bool(gap_v1 and gap_v1["lo95"] >= 0)
    pass_v2 = bool(gap_v2 and gap_v2["lo95"] >= 0)

    payload = {
        "experiment": "P4 pWOBA EV/barrel residual-correction arm (hitters)",
        "generated_at": date.today().isoformat(), "seed": SEED, "boot": BOOT,
        "harness": plh.convention_meta("wOBA(Y+1) raw pooled", "wOBA(Y+1)"),
        "protocol": {
            "base_arm": base_name,
            "candidate": ("base + OLS(residual ~ z(avg_hit_speed) + z(brl_pa) + "
                          "z(ev95percent)), coefs frozen on train"),
            "ev_cache": "statcast_batter 2016-2023 backfilled 2026-07-15 (was 2024+)",
            "gate_rule": "ev_corrected vs base: iid paired bootstrap lo95 >= 0 (v1)",
            "ledger_position": ("EV as proj_ml TREE features was rejected 2026-06-23; "
                                "this is the output-layer residual form, newly powered "
                                "by the cache backfill"),
        },
        "n_pairs": len(pairs), "n_train": len(train), "n_gate": len(gate),
        "drops": drops, "frozen_hyperparams": frozen,
        "gate_rhos_v1": {k: _r4(v) for k, v in rhos.items()},
        "results": res,
        "gate": {"gap_ci_candidate_minus_base_v1": gap_v1,
                 "gap_ci_candidate_minus_base_v2": gap_v2,
                 "pass": pass_v1, "pass_under_v2": pass_v2},
        "runtime_seconds": round(time.time() - t0, 1),
    }
    out = ROOT / "data" / "pwoba_ev_arm_eval.json"
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"wrote {out}")
    print(json.dumps({"rhos": payload["gate_rhos_v1"], "gap_v1": gap_v1,
                      "pass": pass_v1, "pass_v2": pass_v2}, indent=1))


if __name__ == "__main__":
    main()
