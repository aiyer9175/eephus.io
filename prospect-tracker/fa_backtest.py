# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""HARD GATES for the MLB Free Agency module's models.

Gate 1 (projection): train through season N-1, project season N, for every
target season in fa_config projection.eval.target_seasons. NO LOOKAHEAD:
aging curves, the WAR map, and band sigmas are all refitted per target on
data strictly before it (band sigmas roll forward from PREVIOUS targets'
residuals, seeded by two warmup targets excluded from the gate metrics).

Baseline to beat: the 5/4/3 weighted average of each player's ACTUAL
final-metric seasons — no regression, no aging, classic naive carry-forward.

Pass criteria (ship/no-ship):
  - pooled model MAE < baseline MAE on ALL of WAR, wRC+ (PA>=150), FIP (BF>=150)
  - P10-P90 band coverage on WAR within [0.75, 0.85]

Population honesty: every player with >=1 input season is predicted; a
player ABSENT from the target season scores actual WAR = 0 (they delivered
nothing) for BOTH model and baseline; rate metrics evaluate only where the
target season has real exposure (disclosed thresholds). The age-30+ slice
(the FA-relevant population) is reported alongside the full pool.

Results persist to fa_model_eval (the Model Accountability surface renders
them verbatim) — misses and all.
"""

from __future__ import annotations

import argparse
import logging
import math
import statistics
from collections import defaultdict

import fa_class
import fa_projection as fp
import storage

log = logging.getLogger(__name__)

MODEL_VERSION = "fa_proj_v1"
WARMUP_TARGETS = [2013, 2014]          # seed band sigmas; excluded from gate metrics


def _actual_metrics(row: dict, side: str, league: dict) -> dict:
    """Actual final metrics for one corpus row, computed with the SAME
    assembly the projections use (consistent comparison)."""
    out = {"war": row.get("war"), "expo": row.get("pa" if side == "hit" else "bf") or 0}
    if side == "hit":
        a = fp._assemble_hitter({**row, "babip": row.get("babip") or 0.29},
                                league, row["season"] + 1)
        out["wrc_plus"] = a["wrc_plus_proj"]
    else:
        out["fip"] = row.get("fip")
    return out


def _baseline(history: list[dict], side: str, target: int, league: dict) -> dict:
    """5/4/3 weighted average of the player's ACTUAL final metrics — the
    naive carry-forward the model must beat. Rate metrics exposure-weighted;
    WAR plain 5/4/3 over present seasons."""
    weights = {1: 5.0, 2: 4.0, 3: 3.0}
    wn = wd = 0.0
    rn = rd = 0.0
    for h in history:
        lag = target - h["season"]
        if lag not in weights:
            continue
        w = weights[lag]
        if h.get("war") is not None:
            wn += w * h["war"]; wd += w
        act = _actual_metrics(h, side, league)
        rate = act.get("wrc_plus") if side == "hit" else act.get("fip")
        expo = act["expo"]
        if rate is not None and expo > 0:
            rn += w * expo * rate; rd += w * expo
    return {"war": (wn / wd) if wd else None,
            ("wrc_plus" if side == "hit" else "fip"): (rn / rd) if rd else None}


def _mae(pairs: list[tuple[float, float]]) -> float | None:
    if not pairs:
        return None
    return sum(abs(p - a) for p, a in pairs) / len(pairs)


def _rmse(pairs: list[tuple[float, float]]) -> float | None:
    if not pairs:
        return None
    return math.sqrt(sum((p - a) ** 2 for p, a in pairs) / len(pairs))


def run_projection_gate(persist: bool = True) -> dict:
    cfg = fp._pcfg()
    corpus = fp.build_corpus()
    league = corpus["league"]
    targets = list(cfg["eval"]["target_seasons"])
    min_pa = cfg["eval"]["rate_eval_min_pa"]
    min_bf = cfg["eval"]["rate_eval_min_bf"]

    by_player: dict[str, dict[int, dict]] = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r

    # rolling residual store for band sigmas: bucket -> [residuals]
    resid: dict[str, list[float]] = defaultdict(list)

    def _bucket(side: str, expo_proj: float) -> str:
        lo = 350 if side == "hit" else 250
        return f"{side}:{'hi' if expo_proj >= lo else 'lo'}"

    per_season: list[dict] = []
    pooled = {"war": {"m": [], "b": []}, "wrc_plus": {"m": [], "b": []},
              "fip": {"m": [], "b": []}, "war30": {"m": [], "b": []}}
    coverage_hits = coverage_n = 0

    for target in WARMUP_TARGETS + targets:
        is_warmup = target in WARMUP_TARGETS
        curves = fp.fit_aging_curves(corpus, max_season=target - 1, write=False)
        war_map = fp.fit_war_map(corpus, max_season=target - 1)
        season_stats = {"war": {"m": [], "b": []}, "wrc_plus": {"m": [], "b": []},
                        "fip": {"m": [], "b": []}, "war30": {"m": [], "b": []},
                        "cov_hits": 0, "cov_n": 0}
        new_resid: dict[str, list[float]] = defaultdict(list)
        for side in ("hit", "pit"):
            rate_key = "wrc_plus" if side == "hit" else "fip"
            for mlbam, seasons in by_player[side].items():
                hist = [seasons[s] for s in (target - 1, target - 2, target - 3) if s in seasons]
                if not hist:
                    continue
                age_prev = next((h.get("age") for h in hist if h.get("age")), None)
                age = (age_prev + (target - hist[0]["season"])) if age_prev else None
                proj = fp.project_player(hist, side, target, curves, league, age)
                if proj is None:
                    continue
                war_pred = fp.war_from_projection(proj, side, war_map, league, target)
                base = _baseline(hist, side, target, league)
                actual_row = seasons.get(target)
                act = _actual_metrics(actual_row, side, league) if actual_row else {"war": 0.0, "expo": 0}
                act_war = act.get("war") if act.get("war") is not None else 0.0
                # WAR pool (everyone)
                if base["war"] is not None:
                    season_stats["war"]["m"].append((war_pred, act_war))
                    season_stats["war"]["b"].append((base["war"], act_war))
                    if age and age >= 30:
                        season_stats["war30"]["m"].append((war_pred, act_war))
                        season_stats["war30"]["b"].append((base["war"], act_war))
                    # bands: EMPIRICAL residual quantiles from PRIOR targets
                    # only (the spec's preferred mode — self-calibrating;
                    # the parametric normal alternative over-covered at
                    # 0.858 because WAR residuals are fat-middled).
                    bk = _bucket(side, proj["pt_proj"])
                    pool = resid.get(bk) or []
                    if len(pool) >= 50 and not is_warmup:
                        qs = statistics.quantiles(pool, n=10)
                        q10, q90 = qs[0], qs[-1]
                        if q10 <= (act_war - war_pred) <= q90:
                            season_stats["cov_hits"] += 1
                        season_stats["cov_n"] += 1
                    new_resid[bk].append(act_war - war_pred)
                # rate pool (target exposure gate)
                min_expo = min_pa if side == "hit" else min_bf
                if actual_row and act["expo"] >= min_expo and base.get(rate_key) is not None:
                    rate_pred = proj["wrc_plus_proj"] if side == "hit" else proj["fip_proj"]
                    rate_act = act.get(rate_key)
                    if rate_pred is not None and rate_act is not None:
                        season_stats[rate_key]["m"].append((rate_pred, rate_act))
                        season_stats[rate_key]["b"].append((base[rate_key], rate_act))
        for bk, vals in new_resid.items():
            resid[bk].extend(vals)
        if is_warmup:
            continue
        row = {"season": target}
        for k in ("war", "wrc_plus", "fip", "war30"):
            row[f"{k}_mae_model"] = _mae(season_stats[k]["m"])
            row[f"{k}_mae_base"] = _mae(season_stats[k]["b"])
            row[f"{k}_n"] = len(season_stats[k]["m"])
            pooled[k]["m"].extend(season_stats[k]["m"])
            pooled[k]["b"].extend(season_stats[k]["b"])
        row["coverage"] = (season_stats["cov_hits"] / season_stats["cov_n"]
                          if season_stats["cov_n"] else None)
        coverage_hits += season_stats["cov_hits"]
        coverage_n += season_stats["cov_n"]
        per_season.append(row)
        log.info("gate1 %d: WAR mae %.3f vs base %.3f (n=%d) | wRC+ %.1f vs %.1f | "
                 "FIP %.3f vs %.3f | cov %s",
                 target, row["war_mae_model"], row["war_mae_base"], row["war_n"],
                 row["wrc_plus_mae_model"] or -1, row["wrc_plus_mae_base"] or -1,
                 row["fip_mae_model"] or -1, row["fip_mae_base"] or -1,
                 f"{row['coverage']:.3f}" if row["coverage"] else "n/a")

    coverage = coverage_hits / coverage_n if coverage_n else None
    summary = {
        "model_version": MODEL_VERSION,
        "targets": targets,
        "pooled": {k: {"mae_model": _mae(v["m"]), "mae_base": _mae(v["b"]),
                       "rmse_model": _rmse(v["m"]), "rmse_base": _rmse(v["b"]),
                       "n": len(v["m"])} for k, v in pooled.items()},
        "coverage_p10_p90": coverage,
        "per_season": per_season,
        "notes": [
            "WAR = bWAR (war_daily); absent target seasons score actual WAR 0 for model AND baseline",
            f"wRC+ park-neutral, assembled from components (eval PA >= {min_pa})",
            f"FIP per-season constant (eval BF >= {min_bf})",
            "baseline = 5/4/3 weighted average of actual final metrics, no regression, no aging",
            "bands = EMPIRICAL residual q10/q90 per reliability bucket, rolled forward from prior targets only",
            "defense/BsR not separately projected in v1 — absorbed by WAR map + bands",
        ],
        # Per-bucket band quantiles from the FULL rolling residual pools —
        # the live projection's band source (documented in the artifact).
        "band_quantiles": {bk: {"q10": statistics.quantiles(v, n=10)[0],
                                "q90": statistics.quantiles(v, n=10)[-1],
                                "n": len(v)}
                           for bk, v in resid.items() if len(v) >= 50},
    }
    gates = {
        "war": summary["pooled"]["war"]["mae_model"] < summary["pooled"]["war"]["mae_base"],
        "wrc_plus": summary["pooled"]["wrc_plus"]["mae_model"] < summary["pooled"]["wrc_plus"]["mae_base"],
        "fip": summary["pooled"]["fip"]["mae_model"] < summary["pooled"]["fip"]["mae_base"],
        "coverage": coverage is not None and 0.75 <= coverage <= 0.85,
    }
    summary["gates"] = gates
    summary["pass"] = all(gates.values())
    if persist:
        storage.upsert_fa_model_eval(MODEL_VERSION, "projection", summary)
        # Repo-visible copy (prospects.db is gitignored): the committed
        # gate verdict the Accountability surface + tests key off.
        import json
        from pathlib import Path
        (Path(__file__).parent / "data" / "fa_gate1_eval.json").write_text(
            json.dumps(summary, indent=1), encoding="utf-8")
    return summary


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate1", action="store_true")
    args = ap.parse_args()
    if args.gate1:
        s = run_projection_gate()
        print("\n==== HARD GATE 1 — projection engine ====")
        for k, v in s["pooled"].items():
            print(f"  {k:9s} model MAE {v['mae_model']:.4f}  vs base {v['mae_base']:.4f}  (n={v['n']})")
        print(f"  coverage P10-P90: {s['coverage_p10_p90']:.3f}" if s["coverage_p10_p90"] else "  coverage: n/a")
        print(f"  gates: {s['gates']}")
        print(f"  PASS: {s['pass']}")


if __name__ == "__main__":
    main()
