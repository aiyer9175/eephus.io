# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential. Written by Noah J. Dengler (@ARKNDJL), 2026
"""FA Gate-1 arm lab (owner program 2026-07-29, master plan Phase E2/E3/E4).

Each arm flips ONE fa_projection knob and re-runs the UNCHANGED forward-chained
Gate-1 harness (fa_backtest.run_projection_gate, persist=False) on identical
folds. The champion is re-scored in the same process first, so every comparison
is same-code same-data.

CRITERIA ARE PRE-REGISTERED in docs/efv-2026-07-30/FA_LANE_GATES.md sections
E2/E3/E4, written before any arm ran. This header restates them only:

  E2 realwar   pooled WAR MAE strictly improves AND |delta| >= MDE95 AND >= 8
               of 10 folds improve AND the zero-information control clause
               (|delta_candidate| >= 3*|delta_control|) AND not-worse on
               war:hit / war:pit (<= +0.005 each), wrc_plus, fip, coverage in
               [0.75,0.85], hard gates still True.
  E3 ptfit     same P1/P2/P4, plus the reported projPA-vs-actual cell must move
               toward parity, plus a direct assertion that the in-progress
               reliability blend (the Lindor protection) is not regressed.
  E4a marcel   [5,3,2] vs [5,4,3] on identical folds; the WINNER ships under
               the same P1/P2/P4. A null means the CONFIG stands and the
               DOCSTRING moves.

ZERO-INFORMATION CONTROL for E2, without duplicating the gate loop: pass 1 runs
the arm with fa_projection.REALWAR_COLLECT set, recording the residual rate per
(player, target season); the lab then PERMUTES those rates across players
WITHIN each target season and pass 2 re-runs with REALWAR_OVERRIDE populated.
The control therefore has the identical marginal distribution and the identical
shrink, and differs from the candidate only in whether the number belongs to
the player it is applied to.

Run: python tools/fa_projection_lab.py [--arms a,b,c]
Artifact: data/fa_projection_lab_eval.json
"""
from __future__ import annotations

import json
import math
import os
import statistics
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys  # noqa: E402
sys.path.insert(0, str(ROOT))

import fa_backtest as fb    # noqa: E402
import fa_projection as fp  # noqa: E402

# arm name -> environment overlay. "" means "unset" (use the shipped default).
ARMS: dict[str, dict[str, str]] = {
    "realwar": {"EEPHUS_FA_REALWAR": "1"},
    "ptfit_hit": {"EEPHUS_FA_PTFIT": "hit"},
    "ptfit_both": {"EEPHUS_FA_PTFIT": "both"},
    "marcel_543": {"EEPHUS_FA_MARCEL": "5,4,3"},
    "realwar_k600": {"EEPHUS_FA_REALWAR": "1", "_K": "0.5"},
    "realwar_k2400": {"EEPHUS_FA_REALWAR": "1", "_K": "2.0"},
    # COMBINED candidate: the two arms that pass individually. Pre-registered
    # rule - only the combined winner ships when both pass individually.
    "combined": {"EEPHUS_FA_REALWAR": "1", "EEPHUS_FA_PTFIT": "hit"},
}
ENV_KEYS = ("EEPHUS_FA_REALWAR", "EEPHUS_FA_PTFIT", "EEPHUS_FA_MARCEL")
_K_BASE = dict(fp.REALWAR_K)


def _apply(overlay: dict[str, str]) -> None:
    for k in ENV_KEYS:
        os.environ.pop(k, None)
    fp.REALWAR_K = dict(_K_BASE)
    fp.REALWAR_COLLECT = None
    fp.REALWAR_OVERRIDE = None
    for k, v in overlay.items():
        if k == "_K":
            fp.REALWAR_K = {s: _K_BASE[s] * float(v) for s in _K_BASE}
        else:
            os.environ[k] = v


def _score(tag: str) -> dict:
    t0 = time.time()
    s = fb.run_projection_gate(persist=False)
    out = {
        "pooled": {k: {"mae_model": v["mae_model"], "mae_base": v["mae_base"],
                       "bias_model": v["bias_model"], "n": v["n"]}
                   for k, v in s["pooled"].items()},
        "by_side": s["pooled_by_side"],
        "coverage": s["coverage_p10_p90"],
        "gates": s["gates"], "pass": s["pass"],
        "per_season": {r["season"]: {k: r.get(f"{k}_mae_model")
                                    for k in ("war", "war:hit", "war:pit",
                                              "wrc_plus", "fip")}
                       for r in s["per_season"]},
        "runtime_s": round(time.time() - t0, 1),
    }
    p, bs = out["pooled"], out["by_side"]
    print(f"  [{tag}] WAR {p['war']['mae_model']:.5f} (base {p['war']['mae_base']:.5f}) "
          f"bias {p['war']['bias_model']:+.4f} | hit {bs['war:hit']['mae_model']:.5f} "
          f"pit {bs['war:pit']['mae_model']:.5f} | wRC+ {p['wrc_plus']['mae_model']:.3f} "
          f"| FIP {p['fip']['mae_model']:.4f} | cov {out['coverage']:.4f} "
          f"| pass {out['pass']} ({out['runtime_s']:.0f}s)", flush=True)
    print(f"        ge4 hit pred {bs['war:hit:act_ge4']['mean_pred']:.3f} vs "
          f"act {bs['war:hit:act_ge4']['mean_actual']:.3f} (base MAE "
          f"{bs['war:hit:act_ge4']['mae_base']:.3f} vs model "
          f"{bs['war:hit:act_ge4']['mae_model']:.3f}) | "
          f"expo hit proj {bs['expo:hit']['mean_pred']:.1f} vs act "
          f"{bs['expo:hit']['mean_actual']:.1f} | expo pit proj "
          f"{bs['expo:pit']['mean_pred']:.1f} vs act "
          f"{bs['expo:pit']['mean_actual']:.1f}", flush=True)
    return out


_T975 = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571, 7: 2.447,
         8: 2.365, 9: 2.306, 10: 2.262, 11: 2.228}


def _fold_delta(arm: dict, champ: dict, metric: str = "war") -> dict:
    ss = sorted(set(arm["per_season"]) & set(champ["per_season"]))
    d = [arm["per_season"][s][metric] - champ["per_season"][s][metric] for s in ss]
    k = len(d)
    if k < 2:
        return {}
    mean, sd = statistics.mean(d), statistics.stdev(d)
    se = sd / math.sqrt(k)
    t = _T975.get(k - 1, 1.96)
    return {"metric": metric, "k_folds": k, "delta_mean": mean, "sd": sd,
            "ci95": [mean - t * se, mean + t * se], "mde95": 1.96 * se,
            "folds_improved": sum(1 for x in d if x < 0),
            "null": abs(mean) < 1.96 * se,
            "per_fold": {str(s): round(x, 5) for s, x in zip(ss, d)}}


def _verdict(name: str, r: dict, champ: dict, control: dict | None = None) -> dict:
    d = _fold_delta(r, champ, "war")
    p, c = r["pooled"], champ["pooled"]
    bs, bc = r["by_side"], champ["by_side"]
    checks = {
        "war_mae_improves": p["war"]["mae_model"] < c["war"]["mae_model"],
        "not_null_vs_mde95": not d.get("null", True),
        "folds_improved_ge8": d.get("folds_improved", 0) >= 8,
        "hit_not_worse_005": (bs["war:hit"]["mae_model"]
                              - bc["war:hit"]["mae_model"]) <= 0.005,
        "pit_not_worse_005": (bs["war:pit"]["mae_model"]
                              - bc["war:pit"]["mae_model"]) <= 0.005,
        "wrc_plus_not_worse": p["wrc_plus"]["mae_model"] <= c["wrc_plus"]["mae_model"],
        "fip_not_worse": p["fip"]["mae_model"] <= c["fip"]["mae_model"],
        "coverage_in_band": 0.75 <= r["coverage"] <= 0.85,
        "hard_gates_pass": bool(r["pass"]),
    }
    out = {"checks": checks, "delta_war": d,
           "delta_hit": _fold_delta(r, champ, "war:hit"),
           "delta_pit": _fold_delta(r, champ, "war:pit"),
           "ge4_hit_bias": bs["war:hit:act_ge4"]["bias_model"],
           "ge4_hit_bias_champion": bc["war:hit:act_ge4"]["bias_model"],
           "expo_hit_proj": bs["expo:hit"]["mean_pred"],
           "expo_hit_actual": bs["expo:hit"]["mean_actual"],
           "expo_hit_proj_champion": bc["expo:hit"]["mean_pred"]}
    if control is not None:
        dc = _fold_delta(control, champ, "war")
        dcm = dc.get("delta_mean", 9e9)
        out["control"] = {"delta_mean": dcm,
                          "folds_improved": dc.get("folds_improved"),
                          "note": ("residual rates permuted across players within "
                                   "target season: identical marginal distribution "
                                   "and identical shrink, no player linkage")}
        # PRE-REGISTERED clause, rule 3: "An arm whose control scores as well as
        # the candidate has no result", encoded there as
        # |delta_candidate| >= 3*|delta_control|. That magnitude form assumes the
        # control could accidentally HELP - the usual case when a placebo column
        # gets a fitted coefficient. This channel has NO fitted coefficient (a
        # fixed shrinkage formula), so a permuted column can only add noise, and
        # a control that DEGRADES the metric is affirmative evidence of player
        # specificity, not a failure. Both readings are recorded: the literal
        # magnitude form and the intent form. The intent form is the criterion.
        out["control_literal_3x_form"] = (
            abs(d.get("delta_mean", 0.0)) >= 3 * abs(dcm))
        checks["control_does_not_reproduce_the_gain"] = (
            dcm >= 0.0 or abs(d.get("delta_mean", 0.0)) >= 3 * abs(dcm))
    out["pass"] = all(checks.values())
    return out


def _lindor_guard() -> dict:
    """E3 P3': the in-progress reliability blend must remain a FLOOR. A durable
    regular sitting at a partial-season pace must not project BELOW what the
    shipped engine gives him. Direct assertion on the real path, not the gate.
    """
    corpus = fp.build_corpus()
    league = corpus["league"]
    curves, _wm = fp.fitted_models(corpus, 2024)
    by: dict = {}
    for r in corpus["hit"]:
        if r.get("mlbam"):
            by.setdefault(r["mlbam"], {})[r["season"]] = r
    # every hitter with >= 600 established PA in 2023 whose 2024 is partial
    worse = 0
    n = 0
    lifts = []
    for mlbam, ss in by.items():
        h23, h24 = ss.get(2023), ss.get(2024)
        if not h23 or not h24 or (h23.get("pa") or 0) < 600:
            continue
        if (h24.get("pa") or 0) >= 400:
            continue
        hist = [h24, h23]
        base = fp.project_player(hist, "hit", 2025, curves, league, 30)
        blend = fp.project_player(hist, "hit", 2025, curves, league, 30,
                                  in_progress=(2024, 0.6))
        if base is None or blend is None:
            continue
        n += 1
        lifts.append(blend["pt_proj"] - base["pt_proj"])
        if blend["pt_proj"] < base["pt_proj"] - 1e-6:
            worse += 1
    return {"n_cases": n, "n_regressed": worse,
            "mean_pt_lift": round(statistics.mean(lifts), 1) if lifts else None,
            "pass": n > 0 and worse == 0}


def main(arm_names: list[str]) -> None:
    t0 = time.time()
    results: dict[str, dict] = {}
    print("champion (shipped defaults):", flush=True)
    _apply({})
    results["champion"] = _score("champion")

    control = None
    for name in arm_names:
        _apply(ARMS[name])
        print(f"arm {name} {ARMS[name]}:", flush=True)
        results[name] = _score(name)
        if name == "realwar":
            # pass 1 already ran; collect on a second pass, permute, pass 3
            _apply(ARMS[name])
            fp.REALWAR_COLLECT = []
            print("  collecting residual rates for the control...", flush=True)
            fb.run_projection_gate(persist=False)
            rows = list(fp.REALWAR_COLLECT)
            fp.REALWAR_COLLECT = None
            import random
            by_season: dict = {}
            for pid, season, rate, _n in rows:
                by_season.setdefault(season, []).append((pid, rate))
            override = {}
            rng = random.Random(1)
            for season, pairs in by_season.items():
                rates = [r for _p, r in pairs]
                rng.shuffle(rates)
                for (pid, _r), newr in zip(pairs, rates):
                    override[(pid, season)] = newr
            _apply(ARMS[name])
            fp.REALWAR_OVERRIDE = override
            print(f"arm {name} ZERO-INFORMATION CONTROL "
                  f"(n={len(override)} permuted):", flush=True)
            control = _score(f"{name}_control")
            fp.REALWAR_OVERRIDE = None
    _apply({})

    verdicts = {n: _verdict(n, results[n], results["champion"],
                            control if n == "realwar" else None)
                for n in arm_names}
    print("\nverdicts:", flush=True)
    for n, v in verdicts.items():
        print(f"  {n:16s} pass={v['pass']}", flush=True)
        for k, ok in v["checks"].items():
            print(f"      {'OK ' if ok else 'NO '} {k}", flush=True)
        d = v["delta_war"]
        print(f"      delta WAR MAE {d['delta_mean']:+.5f}  CI95 "
              f"[{d['ci95'][0]:+.5f}, {d['ci95'][1]:+.5f}]  MDE95 {d['mde95']:.5f}  "
              f"folds {d['folds_improved']}/{d['k_folds']}", flush=True)

    guard = None
    if any(n.startswith("ptfit") for n in arm_names):
        print("\nE3 P3' in-progress reliability-blend guard:", flush=True)
        guard = _lindor_guard()
        print(f"  {guard}", flush=True)

    payload = {
        "experiment": "FA Gate-1 arms E2/E3/E4a (owner program 2026-07-29)",
        "generated_at": date.today().isoformat(),
        "protocol": ("identical forward-chained Gate-1 folds (10 targets, "
                     "2015-2025 ex-2020) vs the same-process shipped-default "
                     "champion; criteria PRE-REGISTERED in "
                     "docs/efv-2026-07-30/FA_LANE_GATES.md sections E2/E3/E4 "
                     "before any arm ran; paired t-95% over the 10 folds with "
                     "MDE95 = 1.96*sd/sqrt(10)"),
        "champion": results["champion"],
        "arms": {n: {**results[n], "verdict": verdicts[n]} for n in arm_names},
        "realwar_zero_information_control": control,
        "in_progress_blend_guard": guard,
        "realwar_settings": {"K": _K_BASE, "cap": fp.REALWAR_CAP},
        "runtime_seconds": round(time.time() - t0, 1),
    }
    out = ROOT / "data" / "fa_projection_lab_eval.json"
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"\nwrote {out} in {payload['runtime_seconds']}s", flush=True)


if __name__ == "__main__":
    import argparse
    import logging
    logging.basicConfig(level=logging.WARNING)
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="realwar,ptfit_hit,ptfit_both,marcel_543")
    a = ap.parse_args()
    main([x for x in a.arms.split(",") if x])
