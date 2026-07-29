# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""LANE recalibrate -- fv_to_6yr_avg_war anchors on BOTH FV scales (READ-ONLY).

empirical_anchors._cohort pools the RAW snapshot FV (plain mean over the window)
and bins to 5-point tiers; the tiers are the x-axis of fv_to_6yr_avg_war, which
sits UNDERNEATH the surplus calibration. Refitting the calibration on the
normalized scale while the anchors stay raw-fit makes the calibration absorb an
anchor-axis error. This lab derives the anchors under both scales with the
SHIPPED policy so the calibration refit can be run on a matched stack.

Three arms:
  shipped   data/value_framework_fitted.json empirical_anchors (2026-06-21)
  raw       re-derived TODAY on the raw scale   (isolates data drift since then)
  norm      re-derived TODAY on the normalized scale (isolates the scale)

Writes JSON to the scratchpad. Touches no production file.
"""
from __future__ import annotations

import json
import statistics as _st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import storage                                          # noqa: E402
import consensus as _cons                               # noqa: E402
import value_framework as vf                            # noqa: E402
from grade_normalization import build_remapper          # noqa: E402
from empirical_anchors import _is_pitcher_positions     # noqa: E402

OUT = Path(r"C:\Users\noah\AppData\Local\Temp\claude"
           r"\c--Users-noah-baseball-projects-BaseballR"
           r"\c6ce73e3-6700-473f-beea-01f160967961\scratchpad\recal_anchors.json")


def cohorts(y0: int, y1: int) -> dict:
    """{key: {fv_raw, fv_norm, is_pit, realized_war}} -- mirrors
    empirical_anchors._cohort exactly, plus the normalized pooled FV."""
    remap = build_remapper(aliases=_cons.SOURCE_ALIASES)
    fvs: dict[str, list[float]] = defaultdict(list)
    fvn: dict[str, list[float]] = defaultdict(list)
    pos: dict[str, list[str]] = defaultdict(list)
    with storage.connect() as con:
        for r in con.execute(
                "SELECT player_key, fv, position, source, snapshot_date FROM snapshots "
                "WHERE snapshot_date BETWEEN ? AND ? AND fv IS NOT NULL",
                (f"{y0}-01-01", f"{y1}-12-31")):
            k = r["player_key"]
            fv = float(r["fv"])
            fvs[k].append(fv)
            yr = int(str(r["snapshot_date"])[:4])
            n = remap(fv, r["source"], r["position"], yr)
            fvn[k].append(float(n if n is not None else fv))
            pos[k].append((r["position"] or "").upper())
        war: dict[str, float] = {}
        for r in con.execute("SELECT player_key, payload_json FROM career_war"):
            seasons = sorted((int(y), float(w)) for y, w in
                             (json.loads(r["payload_json"]).get("seasons") or {}).items())
            war[r["player_key"]] = sum(w for _, w in seasons[:6])
    return {k: {"fv_raw": _st.mean(v), "fv_norm": _st.mean(fvn[k]),
                "is_pit": _is_pitcher_positions(pos[k]),
                "realized_war": war.get(k, 0.0)}
            for k, v in fvs.items()}


def derive(cohort: dict, field: str, policy: dict) -> dict:
    tiers = [int(t) for t in policy.get("tiers", [40, 45, 50, 55, 60, 65, 70, 80])]
    ref = {int(k): float(v) for k, v in policy.get("public_reference", {}).items()}
    min_n = int(policy.get("min_n_robust", 40))
    w_base = float(policy.get("blend_weight_public", 0.5))
    w_thin = float(policy.get("blend_thin_extra", 0.4))
    by_tier: dict[int, list[float]] = defaultdict(list)
    for r in cohort.values():
        by_tier[int(round(r[field] / 5) * 5)].append(r["realized_war"] / 6.0)
    diag, raw = {}, {}
    for t in tiers:
        ws = by_tier.get(t, [])
        n = len(ws)
        emp = _st.mean(ws) if n else None
        rt = ref.get(t)
        if rt is None:
            rt = max((ref[k] for k in ref if k <= t), default=ref[min(ref)] if ref else 0.0)
        if n == 0:
            w, val = 1.0, rt
        else:
            w = min(0.95, w_base + (w_thin * max(0.0, 1.0 - n / min_n)))
            val = (1.0 - w) * emp + w * rt
        raw[t] = val
        diag[t] = {"n": n, "empirical_war_yr": round(emp, 3) if emp is not None else None,
                   "blend_w_public": round(w, 3)}
    anchors, prev = {}, None
    for t in tiers:
        v = raw[t] if prev is None else max(raw[t], prev)
        anchors[str(t)] = round(v, 2)
        prev = v
    return {"anchors": anchors, "diagnostics": diag}


if __name__ == "__main__":
    cfg = vf._config()
    policy = cfg["anchor_calibration"]
    ry = 2026
    y0, y1 = ry - int(policy["resolved_lag_max"]), ry - int(policy["resolved_lag_min"])
    coh = cohorts(y0, y1)
    out = {"cohort_window": [y0, y1], "n_cohort": len(coh),
           "shipped": (vf._fitted().get("empirical_anchors") or {}).get("anchors"),
           "raw": derive(coh, "fv_raw", policy),
           "norm": derive(coh, "fv_norm", policy)}
    ds = [c["fv_norm"] - c["fv_raw"] for c in coh.values()]
    out["pooled_fv_shift"] = {"mean": sum(ds) / len(ds), "median": _st.median(ds),
                              "n": len(ds)}
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("window", out["cohort_window"], "n_cohort", out["n_cohort"])
    print("pooled FV shift", {k: round(v, 4) if isinstance(v, float) else v
                              for k, v in out["pooled_fv_shift"].items()})
    print("shipped", out["shipped"])
    print("raw    ", out["raw"]["anchors"])
    print("norm   ", out["norm"]["anchors"])
    print("\ntier n (raw -> norm):")
    for t in policy["tiers"]:
        print(f"  {t}: {out['raw']['diagnostics'][t]['n']:5d} -> "
              f"{out['norm']['diagnostics'][t]['n']:5d}   emp "
              f"{out['raw']['diagnostics'][t]['empirical_war_yr']} -> "
              f"{out['norm']['diagnostics'][t]['empirical_war_yr']}")
    print("wrote", OUT)
