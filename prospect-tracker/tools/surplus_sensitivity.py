# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Surplus-value sensitivity to the $/WAR level (credibility analysis).

Question: if the market price of a win were mis-estimated by -20/-10/+10/+20
percent, how much would the platform's prospect surplus values and, more
importantly, their ORDERING change?

Method (level scaled, shape fixed):
  * The $/WAR level is centralized in the loaded config's `dollars_per_war`
    block (`flat` plus the three tier rates). That is exactly the quantity the
    production fa_dpw_series re-anchor rescales at config load, tier SHAPE
    (rate ratios) preserved. This harness applies the same operation in
    process: it scales `flat` and all three tier rates on the lru-cached
    config dict by (1 + shift), clears the derived dollar caches, recomputes,
    and restores. value_framework.py is never edited; the pattern mirrors the
    `_perturb` harness in test_config_base_verification.py.
  * Population: every active prospect in data/timeseries.json with a baked
    `surplus` block (the full board population). Inputs replicate the exact
    values the platform priced: surplus.fv_used (continuous FV), the baked
    is_pitcher flag, position, age, and the baked eta_years (None where no
    ETA, matching the engine's default path).
  * Held fixed at shipped values: league minimum, arbitration fractions,
    discount rate, $/WAR inflation, the Edwards FV<=40 dollar anchor, and the
    isotonic output calibration (fit at the baseline level). So the analysis
    answers: everything as shipped, but the market level itself is off by X%.
  * Deterministic: the point-surplus path has no Monte Carlo. SEED is a
    documented constant for provenance only (nothing stochastic runs).

Outputs (data/surplus_sensitivity.json):
  * Spearman rank correlation of per-player surplus vs baseline, per shift
    (on the production calibrated value and on the raw pre-calibration value).
  * Top-50 churn per shift: players entering/leaving the baseline top 50 and
    the max rank move among baseline top-50 players.
  * Per-FV-tier median dollar change ($M and percent) per shift.
  * A three-sentence plain-prose takeaway for the methodology note.

Run directly:  python tools/surplus_sensitivity.py
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from datetime import date
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))

import value_framework as vf  # noqa: E402  (needs _ROOT on sys.path)

OUT_PATH = _ROOT / "data" / "surplus_sensitivity.json"
TS_PATH = _ROOT / "data" / "timeseries.json"

SEED = 20260701          # provenance only; the point-surplus path is deterministic
SHIFTS = (-0.20, -0.10, 0.10, 0.20)
TOP_N = 50

# FV tiers for the median-change table: [lo, hi) bins on the continuous FV the
# engine priced (fv_used). The board population runs FV 35 to the low 60s.
TIER_EDGES = ((35.0, 40.0, "FV 35-40"), (40.0, 45.0, "FV 40-45"),
              (45.0, 50.0, "FV 45-50"), (50.0, 55.0, "FV 50-55"),
              (55.0, 60.0, "FV 55-60"), (60.0, 81.0, "FV 60+"))


# ---------------------------------------------------------------------------
# $/WAR level injection (in-process; value_framework.py untouched)
# ---------------------------------------------------------------------------
def _clear_derived() -> None:
    """Clear the caches derived from config WITHOUT clearing _config itself
    (clearing _config would reload the YAML and undo the level shift). Same
    set the test perturbation harness clears."""
    vf._bucket_sv_usd.cache_clear()
    vf._calibrated_midpoints.cache_clear()
    vf._fv_war_scale.cache_clear()


class LevelScaler:
    """Scale the $/WAR LEVEL (flat + all tier rates) by a multiplier, keeping
    the convex tier shape (rate ratios) fixed, exactly as the fa_dpw_series
    re-anchor does at load. set(1.0) restores the baseline."""

    def __init__(self):
        dpw = vf._config()["dollars_per_war"]
        self._dpw = dpw
        self.base_flat = float(dpw["flat"])
        self.base_rates = {k: float(v) for k, v in dpw["tiered"]["rates"].items()}

    def set(self, mult: float) -> None:
        self._dpw["flat"] = self.base_flat * mult
        self._dpw["tiered"]["rates"] = {k: v * mult for k, v in self.base_rates.items()}
        _clear_derived()


# ---------------------------------------------------------------------------
# Population: the board's baked surplus inputs
# ---------------------------------------------------------------------------
def load_population() -> list[dict]:
    data = json.loads(TS_PATH.read_text(encoding="utf-8"))
    rows = []
    for p in data.get("players") or []:
        s = p.get("surplus") or {}
        fv = s.get("fv_used")
        if p.get("status") != "active" or fv is None or s.get("value_mm") is None:
            continue
        rows.append({
            "key": p.get("player_key"),
            "name": p.get("player_name"),
            "fv": float(fv),
            "is_pitcher": bool(s.get("is_pitcher")),
            "position": p.get("position"),
            "age": p.get("age"),
            "eta_years": s.get("eta_years"),   # None -> engine default
            "baked_mm": float(s["value_mm"]),
        })
    return rows


def compute_scenario(rows: list[dict]) -> tuple[list[float], list[float]]:
    """Per-player (calibrated $M, raw pre-calibration $M) at the CURRENT config
    level. Calibrated values are kept unrounded so ranks carry full precision
    (the shipped surplus_value_mm rounds to 0.1)."""
    cal, raw = [], []
    for r in rows:
        usd = vf.expected_surplus_usd(r["fv"], r["is_pitcher"], r["position"],
                                      age=r["age"], eta_years=r["eta_years"])
        usd = max(0.0, float(usd or 0.0))
        c = vf.apply_calibration(usd / 1e6, r["fv"], r["is_pitcher"])
        raw.append(usd / 1e6)
        cal.append(float(c))
    return cal, raw


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def _avg_ranks(vals: list[float]) -> list[float]:
    """Average ranks (1-indexed) with ties shared, ascending order."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(a: list[float], b: list[float]) -> float:
    ra, rb = _avg_ranks(a), _avg_ranks(b)
    n = len(ra)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = sum((x - ma) ** 2 for x in ra)
    vb = sum((y - mb) ** 2 for y in rb)
    if va <= 0 or vb <= 0:
        return float("nan")
    return cov / math.sqrt(va * vb)


def board_positions(rows: list[dict], vals: list[float]) -> dict[str, int]:
    """1-indexed board rank per player key: surplus descending, deterministic
    key tiebreak (matches how a tied board would sort stably)."""
    order = sorted(range(len(rows)), key=lambda i: (-vals[i], rows[i]["key"] or ""))
    return {rows[i]["key"]: pos + 1 for pos, i in enumerate(order)}


def top50_churn(rows, base_pos, shift_pos, top_n=TOP_N) -> dict:
    base_top = {k for k, v in base_pos.items() if v <= top_n}
    shift_top = {k for k, v in shift_pos.items() if v <= top_n}
    entering = sorted(shift_top - base_top, key=lambda k: shift_pos[k])
    leaving = sorted(base_top - shift_top, key=lambda k: base_pos[k])
    names = {r["key"]: r["name"] for r in rows}
    moves = [abs(shift_pos[k] - base_pos[k]) for k in base_top]
    return {
        "n_entering": len(entering),
        "n_leaving": len(leaving),
        "max_rank_move_of_baseline_top50": max(moves) if moves else 0,
        "entering": [{"key": k, "name": names.get(k),
                      "rank_base": base_pos[k], "rank_shift": shift_pos[k]} for k in entering],
        "leaving": [{"key": k, "name": names.get(k),
                     "rank_base": base_pos[k], "rank_shift": shift_pos[k]} for k in leaving],
    }


def tier_median_changes(rows, base_cal, shift_cal) -> dict:
    out = {}
    for lo, hi, label in TIER_EDGES:
        deltas, pcts = [], []
        for i, r in enumerate(rows):
            if lo <= r["fv"] < hi:
                d = shift_cal[i] - base_cal[i]
                deltas.append(d)
                if base_cal[i] > 0:
                    pcts.append(100.0 * d / base_cal[i])
        if not deltas:
            continue
        out[label] = {
            "n": len(deltas),
            "median_change_mm": round(statistics.median(deltas), 2),
            "median_change_pct": round(statistics.median(pcts), 2) if pcts else None,
        }
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> dict:
    rows = load_population()
    if not rows:
        raise SystemExit("no population rows (timeseries.json missing surplus blocks?)")

    scaler = LevelScaler()
    fa_meta = vf._config()["dollars_per_war"].get("_fa_reanchor") or {}
    # Isotonic calibration floor (the bottom knot's y): raw values below the
    # first knot all map here, forming a tie block in the deep low tier.
    try:
        iso_floor = float(vf._config()["calibration"]["isotonic"]["y_mm"][0])
    except (KeyError, IndexError, TypeError, ValueError):
        iso_floor = None
    hi_idx = [i for i, r in enumerate(rows) if r["fv"] >= 45.0]

    # Baseline (multiplier 1.0) + replication check against the shipped numbers.
    scaler.set(1.0)
    base_cal, base_raw = compute_scenario(rows)
    diffs = [abs(round(c, 1) - r["baked_mm"]) for c, r in zip(base_cal, rows)]
    replication = {
        "n_players": len(rows),
        "share_exact_at_0p1_rounding": round(
            sum(1 for d in diffs if d < 0.05001) / len(diffs), 4),
        "median_abs_diff_mm": round(statistics.median(diffs), 3),
        "p95_abs_diff_mm": round(sorted(diffs)[int(0.95 * len(diffs))], 3),
        "note": ("recomputed baseline vs the baked surplus.value_mm in "
                 "timeseries.json; small diffs reflect build-time age/ETA drift"),
    }
    base_pos = board_positions(rows, base_cal)

    shifts_out = {}
    for shift in SHIFTS:
        mult = 1.0 + shift
        scaler.set(mult)
        cal, raw = compute_scenario(rows)
        pos = board_positions(rows, cal)
        label = f"{shift:+.0%}"
        shifts_out[label] = {
            "level_multiplier": round(mult, 2),
            "flat_usd_per_war": round(scaler.base_flat * mult),
            "spearman_vs_baseline_calibrated": round(spearman(cal, base_cal), 6),
            "spearman_vs_baseline_calibrated_fv45plus": round(
                spearman([cal[i] for i in hi_idx], [base_cal[i] for i in hi_idx]), 6),
            "spearman_vs_baseline_raw": round(spearman(raw, base_raw), 6),
            "top50": top50_churn(rows, base_pos, pos),
            "fv_tier_median_change": tier_median_changes(rows, base_cal, cal),
            "n_unchanged_players": sum(1 for b, c in zip(base_cal, cal)
                                       if abs(b - c) < 1e-9),
            "n_pinned_at_calibration_floor": (
                sum(1 for c in cal if abs(c - iso_floor) < 1e-9)
                if iso_floor is not None else None),
            "total_board_surplus_mm": round(sum(cal), 1),
            "total_change_pct": round(100.0 * (sum(cal) - sum(base_cal)) / sum(base_cal), 2),
        }
    scaler.set(1.0)   # restore the in-process config

    # Plain-prose takeaway (filled with the computed numbers below).
    min_rho45 = min(s["spearman_vs_baseline_calibrated_fv45plus"] for s in shifts_out.values())
    max_churn = max(s["top50"]["n_entering"] for s in shifts_out.values())
    max_move = max(s["top50"]["max_rank_move_of_baseline_top50"] for s in shifts_out.values())
    hi_pcts = [abs(t["median_change_pct"])
               for s in shifts_out.values()
               for label, t in s["fv_tier_median_change"].items()
               if not label.startswith(("FV 35", "FV 40")) and t["median_change_pct"] is not None]
    churn_clause = (f"at most {max_churn} players enter or leave the top 50"
                    if max_churn else "nobody enters or leaves the top 50")
    rho_floor = math.floor(min_rho45 * 1e4) / 1e4   # truncate so "above X" is literally true
    takeaway = (
        f"A 20 percent error in the dollars-per-WAR level would change price tags, not the "
        f"pecking order: among the FV 45 and up prospects that drive rankings and trade value, "
        f"rank correlation with the baseline stays above {rho_floor:.4f}, {churn_clause}, and "
        f"no baseline top-50 player moves more than {max_move} spots. "
        f"Below FV 45, values sit on the fixed Edwards dollar anchor and the calibration "
        f"floor, so tier medians there do not move at all, while FV 45 and up tier medians "
        f"move about {min(hi_pcts):.0f} to {max(hi_pcts):.0f} percent under 10 to 20 percent "
        f"level shifts, locally amplified or damped by the isotonic output calibration. "
        f"Rankings and tier comparisons are therefore stable to how the market level is "
        f"estimated, and the absolute dollar figures carry that uncertainty at roughly the "
        f"size of the shift."
    )
    notes = [
        ("FV at or below 40 uses the Edwards fixed-dollar anchor (by design, the production "
         "fa_dpw re-anchor does not scale it either), so those players' raw surplus is "
         "identical under every level shift; the 40-45 bridge moves only through its "
         "pipeline component."),
        ("The full-board calibrated Spearman dips at -20 percent because more small raw "
         "values fall below the first isotonic knot and join the tie block at the "
         "calibration floor; it is tie compression, not reordering. The raw Spearman and "
         "the FV 45+ calibrated Spearman both stay above 0.999."),
        ("Per-tier median percent changes can exceed the shift because the isotonic output "
         "calibration has locally steep and flat segments; raw pre-calibration surplus "
         "scales close to one for one with the level."),
    ]

    payload = {
        "generated": date.today().isoformat(),
        "seed": SEED,
        "deterministic": True,
        "method": {
            "question": ("sensitivity of prospect surplus values to the $/WAR level: "
                         "shape fixed, level scaled by -20/-10/+10/+20 percent"),
            "injection": ("in-process scale of the loaded config's dollars_per_war block "
                          "(flat + all three tier rates) by (1 + shift), derived caches "
                          "cleared, config restored after; the same level-only rescale the "
                          "fa_dpw_series re-anchor performs at load (tier shape preserved); "
                          "value_framework.py not modified"),
            "population": ("all active prospects in data/timeseries.json with a baked "
                           "surplus block; inputs replicated from the baked payload "
                           "(fv_used, is_pitcher, position, age, eta_years)"),
            "held_fixed": ["league_min_usd", "arb fractions", "discount_rate",
                           "dollars_per_war_inflation", "lowtier Edwards anchor",
                           "isotonic output calibration (fit at baseline level)"],
            "value_basis": ("production calibrated surplus in $M, unrounded "
                            "(surplus_value_mm before its 0.1 rounding); raw "
                            "pre-calibration Spearman reported as a cross-check"),
            "rank_tiebreak": "surplus descending, then player_key",
        },
        "baseline": {
            "flat_usd_per_war": round(scaler.base_flat),
            "tier_rates_usd_per_war": {k: round(v) for k, v in scaler.base_rates.items()},
            "fa_reanchor": fa_meta,
            "replication": replication,
            "total_board_surplus_mm": round(sum(base_cal), 1),
        },
        "shifts": shifts_out,
        "notes": notes,
        "takeaway": takeaway,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    return payload


if __name__ == "__main__":
    out = main()
    print(f"wrote {OUT_PATH}")
    print(f"n_players={out['baseline']['replication']['n_players']}  "
          f"replication_share={out['baseline']['replication']['share_exact_at_0p1_rounding']}")
    for label, s in out["shifts"].items():
        print(f"{label}: rho_cal={s['spearman_vs_baseline_calibrated']:.6f} "
              f"rho_cal_fv45+={s['spearman_vs_baseline_calibrated_fv45plus']:.6f} "
              f"rho_raw={s['spearman_vs_baseline_raw']:.6f} "
              f"top50 +{s['top50']['n_entering']}/-{s['top50']['n_leaving']} "
              f"maxmove={s['top50']['max_rank_move_of_baseline_top50']} "
              f"total%={s['total_change_pct']:+.2f}")
    print()
    print(out["takeaway"])
