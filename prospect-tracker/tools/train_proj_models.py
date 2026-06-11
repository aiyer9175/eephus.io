# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Training + evaluation driver for the WAR-projection ML challenger
(model-audit Phase 1, WS-1). Forward-chained everywhere: a model scored
at base B trains only on labels <= B-1.

  --dev       champion-vs-challenger on the dev bases (2017-2021) across
              h1-5 — the ONLY place hyperparameters may be tuned
  --gate1     h1-only check on the Gate-1 target seasons (champion's own
              gate criteria: MAE vs champion + band coverage)
  --holdout   bases 2022-2024 (h1-h3) — TOUCHED ONCE per ship decision
  --final     train the shipping bundle on all complete labels + save to
              model/proj_lgbm/ (records the training-data hash)

Each mode appends its block to data/proj_horizon_eval.json (champion
blocks ride alongside) — losses committed, never hidden."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import fa_projection as fp                                   # noqa: E402
import proj_eval                                             # noqa: E402
import proj_ml                                               # noqa: E402

log = logging.getLogger(__name__)
ARTIFACT = ROOT / "data" / "proj_horizon_eval.json"

DEV_BASES = [2017, 2018, 2019, 2021]
HOLDOUT_BASES = [2022, 2023, 2024]


def challenger_fn(models: dict):
    """proj_eval predict_fn closure over a trained bundle."""
    def _fn(hist, side, base, age, curves, war_map, league):
        feats = proj_ml.build_features(hist, side, base, age, curves,
                                       war_map, league)
        if feats is None:
            return None
        return proj_ml.predict_path(models, feats, side)
    return _fn


def eval_bases(bases: list[int], label: str) -> dict:
    """Forward-chained challenger eval: per base, train on labels <= B-1,
    score through proj_eval, merge horizon stats across bases (weighted
    by n). Champion runs the same bases through the same harness."""
    corpus = fp.build_corpus()
    merged: dict[int, dict] = {}
    for B in bases:
        models = proj_ml.train(corpus, max_label_season=B - 1)
        res = proj_eval.run([B], persist=False, predict_fn=challenger_fn(models),
                            model_label=f"{label}@{B}")
        for h, s in res["horizons"].items():
            m = merged.setdefault(h, {"n": 0, "abs": 0.0, "err": 0.0,
                                      "star_n": 0, "star_abs": 0.0, "star_err": 0.0,
                                      "tp": 0, "ta": 0, "cov_h": 0, "cov_n": 0,
                                      "cov_h_sv": 0, "cov_n_sv": 0,
                                      "pin10": 0.0, "pin90": 0.0, "pin_n": 0})
            m["n"] += s["n"]
            m["abs"] += s["mae"] * s["n"]
            m["err"] += s["bias"] * s["n"]
            if s["n_star"]:
                m["star_n"] += s["n_star"]
                m["star_abs"] += (s["mae_star"] or 0) * s["n_star"]
                m["star_err"] += (s["bias_star"] or 0) * s["n_star"]
            m["tp"] += s["tail_pred_ge3"]
            m["ta"] += s["tail_act_ge3"]
            if s["coverage"] is not None:
                # coverage counted over the banded population (== n here)
                m["cov_h"] += round(s["coverage"] * s["n"])
                m["cov_n"] += s["n"]
            if s["coverage_survived"] is not None:
                m["cov_h_sv"] += round(s["coverage_survived"] * s["n_survived"])
                m["cov_n_sv"] += s["n_survived"]
            if s["pinball_q10"] is not None:
                m["pin10"] += s["pinball_q10"] * s["n"]
                m["pin90"] += s["pinball_q90"] * s["n"]
                m["pin_n"] += s["n"]
    out = {"model": label, "bases": bases, "horizons": {}}
    for h, m in sorted(merged.items()):
        out["horizons"][h] = {
            "n": m["n"],
            "mae": round(m["abs"] / m["n"], 4),
            "bias": round(m["err"] / m["n"], 4),
            "n_star": m["star_n"],
            "mae_star": round(m["star_abs"] / m["star_n"], 4) if m["star_n"] else None,
            "bias_star": round(m["star_err"] / m["star_n"], 4) if m["star_n"] else None,
            "tail_pred_ge3": m["tp"], "tail_act_ge3": m["ta"],
            "tail_ratio": round(m["tp"] / m["ta"], 3) if m["ta"] else None,
            "coverage": round(m["cov_h"] / m["cov_n"], 4) if m["cov_n"] else None,
            "coverage_survived": (round(m["cov_h_sv"] / m["cov_n_sv"], 4)
                                  if m["cov_n_sv"] else None),
            "n_survived": m["cov_n_sv"],
            "pinball_q10": round(m["pin10"] / m["pin_n"], 4) if m["pin_n"] else None,
            "pinball_q90": round(m["pin90"] / m["pin_n"], 4) if m["pin_n"] else None,
        }
    return out


def _print_table(res: dict) -> None:
    print(f"\n==== {res['model']} (bases {res['bases']}) ====")
    print(f"{'h':>2} {'n':>6} {'MAE':>7} {'bias':>7} {'starMAE':>8} {'starBias':>9} "
          f"{'ratio':>6} {'cov':>6} {'covSv':>6} {'pin10':>6} {'pin90':>6}")
    for h, s in res["horizons"].items():
        print(f"{h:>2} {s['n']:>6} {s['mae']:>7.3f} {s['bias']:>7.3f} "
              f"{(s['mae_star'] if s['mae_star'] is not None else float('nan')):>8.3f} "
              f"{(s['bias_star'] if s['bias_star'] is not None else float('nan')):>9.3f} "
              f"{(s['tail_ratio'] or 0):>6.3f} "
              f"{(s['coverage'] if s['coverage'] is not None else float('nan')):>6.3f} "
              f"{(s['coverage_survived'] if s['coverage_survived'] is not None else float('nan')):>6.3f} "
              f"{(s['pinball_q10'] if s['pinball_q10'] is not None else float('nan')):>6.3f} "
              f"{(s['pinball_q90'] if s['pinball_q90'] is not None else float('nan')):>6.3f}")


def _append_artifact(key: str, block: dict) -> None:
    d = json.loads(ARTIFACT.read_text(encoding="utf-8")) if ARTIFACT.exists() else {}
    d.setdefault("challenger_blocks", {})[key] = block
    ARTIFACT.write_text(json.dumps(d, indent=1), encoding="utf-8")
    print(f"appended block '{key}' to {ARTIFACT.name}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", action="store_true")
    ap.add_argument("--gate1", action="store_true")
    ap.add_argument("--holdout", action="store_true",
                    help="TOUCHED ONCE per ship decision (2022-2024, h1-h3)")
    ap.add_argument("--champion", action="store_true",
                    help="also run the champion on the same bases for the table")
    ap.add_argument("--final", action="store_true")
    args = ap.parse_args()

    if args.dev:
        res = eval_bases(DEV_BASES, f"{proj_ml.MODEL_VERSION}_dev")
        _print_table(res)
        _append_artifact("dev", res)
        if args.champion:
            champ = proj_eval.run(DEV_BASES, persist=False)
            _print_table({"model": "champion_marcel_decay_v2", "bases": DEV_BASES,
                          "horizons": champ["horizons"]})
    if args.gate1:
        targets = [2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025]
        res = eval_bases(targets, f"{proj_ml.MODEL_VERSION}_gate1targets")
        _print_table(res)
        _append_artifact("gate1_targets", res)
    if args.holdout:
        res = eval_bases(HOLDOUT_BASES, f"{proj_ml.MODEL_VERSION}_HOLDOUT")
        _print_table(res)
        _append_artifact("holdout_2022_2024", res)
        champ = proj_eval.run(HOLDOUT_BASES, persist=False)
        champ_block = {"model": "champion_marcel_decay_v2", "bases": HOLDOUT_BASES,
                       "horizons": champ["horizons"]}
        _print_table(champ_block)
        _append_artifact("holdout_2022_2024_champion", champ_block)
    if args.final:
        corpus = fp.build_corpus()
        last_label = corpus["last"] - 1            # last COMPLETE season
        models = proj_ml.train(corpus, max_label_season=last_label)
        path = proj_ml.save(models)
        print(f"saved {proj_ml.MODEL_VERSION} (labels <= {last_label}, "
              f"hash {models['meta']['train_hash']}) -> {path}")


if __name__ == "__main__":
    main()
