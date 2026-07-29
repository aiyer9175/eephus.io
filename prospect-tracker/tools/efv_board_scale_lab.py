"""W-SIDESCALE gate lab: reproduces every number quoted in efv_board_scale's GATE
RECORD and writes data/xfv_board_scale_eval.json.

Measurement standard: docs/EFV_GATE_STANDARD.md. Paired bootstrap resampling the
whole pool with a REFIT on every draw, a zero-information control (side label
permuted -- identical marginals, no side information), a permutation null band, and
the effect averaged over 5 independent cohort-year time splits.

Statistic: gap@55 = calibrated hitter grade minus calibrated pitcher grade at raw
grade 55. Negative = pitchers lifted relative to hitters. It is gauge-invariant (the
common affine in step 4 of the fit cancels), so it measures only the cross-side
correction and nothing about the board's overall level.

Run:  python tools/efv_board_scale_lab.py            (prints + writes the artifact)
"""
from __future__ import annotations

import json
import math
import os
import random
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import efv_board_scale as bs                                       # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "xfv_board_scale_eval.json"
B = 2000
SEED = 7

PHI = {"identity_war": lambda w: w,
       "sqrt_war": lambda w: math.sqrt(max(w, 0.0)),
       "p_war_ge_3": lambda w: 1.0 if w >= 3.0 else 0.0}


def load_rows():
    """Labeled pool: raw grade, realized first-6yr WAR, side, cohort year."""
    rows = []
    for side, sf, mf in (("hit", "xfv_scored.json", "xfv_hitter_matrix.json"),
                         ("pit", "xfv_scored_pitcher.json", "xfv_pitcher_matrix.json")):
        meta = {r["player_key"]: r for r in json.loads((DATA / mf).read_text(encoding="utf-8"))}
        for r in json.loads((DATA / sf).read_text(encoding="utf-8")):
            g, w = r.get("xfv_grade"), r.get("realized_war_6yr")
            if g is None or w is None:
                continue
            yr = str((meta.get(r["player_key"]) or {}).get("asof_date") or "")[:4]
            rows.append({"side": side, "g": float(g), "w": float(w),
                         "year": int(yr) if yr.isdigit() else None})
    return rows


def _ols(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx if sxx else 0.0
    return my - b * mx, b


def equate(rows, phi):
    """Steps 1-3 of the fit (per-side outcome line -> pooled anchor -> equated map).
    Returns None when a side is too thin to carry a line."""
    fits = {}
    for s in ("hit", "pit", "pool"):
        sub = rows if s == "pool" else [r for r in rows if r["side"] == s]
        if len(sub) < 30:
            return None
        fits[s] = _ols([r["g"] for r in sub], [phi(r["w"]) for r in sub])
    A, Bp = fits["pool"]
    if Bp <= 0:
        return None
    return {s: ((fits[s][0] - A) / Bp, fits[s][1] / Bp) for s in ("hit", "pit")}


def gap(eq, g=55.0):
    return (eq["hit"][0] + eq["hit"][1] * g) - (eq["pit"][0] + eq["pit"][1] * g)


def band_rows(rows):
    lo, hi = bs.FIT_BAND
    return [r for r in rows if lo <= r["g"] <= hi]


def q(v, p):
    v = sorted(v)
    return v[max(0, min(len(v) - 1, int(round(p * (len(v) - 1)))))]


def run(persist=True):
    rows = load_rows()
    band = band_rows(rows)
    art = {"line": "W-SIDESCALE per-side affine outcome calibration of the eFV board grade",
           "module": "efv_board_scale.py",
           "standard": "docs/EFV_GATE_STANDARD.md",
           "statistic": "gap@55 = calibrated hit grade - calibrated pit grade at raw 55 "
                        "(gauge-invariant; negative = pitchers lifted)",
           "fit_band": list(bs.FIT_BAND),
           "band_n": {s: sum(1 for r in band if r["side"] == s) for s in ("hit", "pit")},
           "outcome": bs.OUTCOME, "fit_pool": bs.FIT_POOL,
           "shipped_enabled": bs.enabled(), "shipped_coeffs": {s: list(c) for s, c in bs.COEFFS.items()},
           "outcome_functionals": {}}

    blocks = [(2013, 2015), (2016, 2017), (2018, 2019), (2020, 2021), (2022, 2024)]
    for name, phi in PHI.items():
        pt = equate(band, phi)
        rnd = random.Random(SEED)
        boot, ctl = [], []
        n = len(band)
        for _ in range(B):
            draw = [band[rnd.randrange(n)] for _ in range(n)]
            e = equate(draw, phi)
            if e:
                boot.append(gap(e))
            sides = [r["side"] for r in draw]
            rnd.shuffle(sides)
            e = equate([dict(r, side=s) for r, s in zip(draw, sides)], phi)
            if e:
                ctl.append(gap(e))
        rnd2 = random.Random(11)
        null = []
        for _ in range(B):
            sides = [r["side"] for r in band]
            rnd2.shuffle(sides)
            e = equate([dict(r, side=s) for r, s in zip(band, sides)], phi)
            if e:
                null.append(gap(e))
        obs = gap(pt)
        splits = []
        for lo, hi in blocks:
            sub = [r for r in band if r["year"] and lo <= r["year"] <= hi]
            e = equate(sub, phi)
            splits.append({"block": f"{lo}-{hi}", "n": len(sub),
                           "gap55": round(gap(e), 2) if e else None})
        good = [s["gap55"] for s in splits if s["gap55"] is not None]
        ci = [round(q(boot, .05), 2), round(q(boot, .95), 2)]
        cci = [round(q(ctl, .05), 2), round(q(ctl, .95), 2)]
        art["outcome_functionals"][name] = {
            "point_gap55": round(obs, 2),
            "paired_bootstrap": {"b": len(boot), "refit_per_draw": True,
                                 "mean": round(st.mean(boot), 2), "ci90": ci,
                                 "sd": round(st.pstdev(boot), 2),
                                 "resolves_ci_excludes_zero": ci[1] < 0 or ci[0] > 0},
            "zero_information_control": {"description": "side label permuted within the draw",
                                         "mean": round(st.mean(ctl), 2), "ci90": cci,
                                         "candidate_inside_control_band": cci[0] <= obs <= cci[1]},
            "permutation_null": {"ci90": [round(q(null, .05), 2), round(q(null, .95), 2)],
                                 "p_two_sided": round(sum(1 for v in null if abs(v) >= abs(obs)) / len(null), 4)},
            "time_splits": {"blocks": splits, "cross_split_mean": round(st.mean(good), 2),
                            "sign_agreement_negative": f"{sum(1 for v in good if v < 0)}/{len(good)}"},
        }
        v = art["outcome_functionals"][name]
        v["verdict"] = ("RESOLVES" if (v["paired_bootstrap"]["resolves_ci_excludes_zero"]
                                       and not v["zero_information_control"]["candidate_inside_control_band"])
                        else "NULL")

    # ---- board effect (acceptance checks 1 + 5) ----
    doc = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))
    bp = doc.get("by_player") or {}
    act = {k: v for k, v in bp.items() if (v or {}).get("kind") == "active"}
    named = ["seth_hernandez", "ryan_sloan", "franklin_arias", "leo_de_vries", "jesus_made"]
    board = {}
    for state in ("off", "on"):
        # Both states must be set EXPLICITLY. Popping the flag falls through to
        # bs.ENABLED_DEFAULT, which the owner flipped to True on 2026-07-25 -- so the
        # "off" arm was silently reading the ON board and the A/B collapsed to a
        # no-op (both arms identical). Set "0"/"1" so the contrast is real either way.
        os.environ[bs.ENV_FLAG] = "1" if state == "on" else "0"
        rowsb = sorted(((bs.board_value(v), k, v.get("side")) for k, v in act.items()
                        if bs.board_value(v) is not None), key=lambda r: (-r[0], r[1]))
        pos = {k: i + 1 for i, (_v, k, _s) in enumerate(rowsb)}
        val = {k: v for v, k, _s in rowsb}
        shown = [int(v + 0.5) for v, _k, _s in rowsb]
        board[state] = {
            "top_n_side_mix_active_board": bs.top_n_side_mix(act),
            "top_n_side_mix_all_rows": bs.top_n_side_mix(bp),
            "display_inversions_in_board_order": sum(1 for a, b in zip(shown, shown[1:]) if b > a),
            "max_served_move_fv": round(max(abs(bs.board_value(v) - bs.raw_grade(v))
                                            for v in act.values() if bs.board_value(v) is not None), 2),
            "named": {p: {"grade": round(val[p], 1), "rank": pos[p]} for p in named if p in pos},
        }
    os.environ.pop(bs.ENV_FLAG, None)
    art["board_effect"] = board
    art["fside_reference"] = {
        "source": "data/xfv_side_fairness_eval.json (efv_model F-SIDE, measurement-only)",
        "note": ("F-SIDE ranks the joint board by the RETIRED per-side quantile display "
                 "grade, a basis the board stopped serving 2026-07-25, so it no longer "
                 "measures the served board. Its rank_war frame is the calibration-honest "
                 "reference for the top-25 pitcher share."),
    }
    try:
        sf = json.loads((DATA / "xfv_side_fairness_eval.json").read_text(encoding="utf-8"))
        t = sf["frames"]["full_pool_km"]["joint_bands_display_grade"]["001-025"]
        art["fside_reference"].update({
            "top25_pit_share_display_frame": t["pit_share"],
            "top25_pit_share_rank_war_frame": t["pit_share_rank_war_frame"],
            "top25_hit_minus_pit": t["boot"]["mean_diff"], "ci90": t["boot"]["mean_ci90"]})
    except (OSError, ValueError, KeyError):
        art["fside_reference"]["error"] = "artifact unavailable"

    if persist:
        OUT.write_text(json.dumps(art, indent=1), encoding="utf-8")
        print("wrote", OUT)
    return art


if __name__ == "__main__":
    a = run()
    for k, v in a["outcome_functionals"].items():
        print(f"{k:14s} gap@55 {v['point_gap55']:+6.2f}  boot CI90 {v['paired_bootstrap']['ci90']}"
              f"  ctl CI90 {v['zero_information_control']['ci90']}"
              f"  perm p {v['permutation_null']['p_two_sided']}"
              f"  folds {v['time_splits']['sign_agreement_negative']}  -> {v['verdict']}")
    for s in ("off", "on"):
        print(f"board[{s}] top25 {a['board_effect'][s]['top_n_side_mix_active_board']['top25']}"
              f"  inversions {a['board_effect'][s]['display_inversions_in_board_order']}"
              f"  max move {a['board_effect'][s]['max_served_move_fv']}")
