# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""Forward-chained gate: does a recency-aware positional ladder predict the
current era better than the shipped 2012-onward fit?

Pre-registration (written and committed BEFORE this ran):
docs/gate-2026-08-07-positional-ladder-recency.md. Read it first; every rule
below is stated there, and nothing here may be re-tuned after seeing a number.

Protocol. For each held-out season T in 2024/2025/2026, fit on rows with
year <= T-1 and predict the held-out rows' runs_position * 650 / PA from their
innings shares. Three specs:

  champion       unweighted LS from LADDER_RETIRED_FIRST_SEASON (2012)
  challenger W   unweighted LS over the last 6 training seasons (2018..T-1)
  challenger R   weighted LS from 2012, weight 0.85 ** (T-1-season)   SECONDARY
  control        challenger W refit on PERMUTED training labels

Scoring runs on the UNCENTRED solution. The ladder's level is unidentified
(share rows sum to 1), so the recentring is a reporting convention; comparing
recentred vectors would score the convention rather than the model.

Run: python tools/positional_ladder_recency_lab.py [--blast]
--blast additionally rebuilds the whole positional-fit payload under both
windows IN MEMORY and records how far the served /pal/ Position Fit board moves.
It costs a couple of minutes and writes nothing outside this eval artifact.

Writes data/positional_ladder_recency_eval.json. Read-only against every other
artifact."""
from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import positional_fit as pf  # noqa: E402

HOLDOUT_SEASONS = (2024, 2025, 2026)
WINDOW_W = 6                 # challenger W keeps the last six training seasons
DECAY_R = 0.85               # challenger R half-life ~4.3 seasons
BOOT = 2000
SEED = 20260807


def _fit(X, y, w=None):
    """Uncentred least squares. `w` is a per-row weight vector or None."""
    if w is None:
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        return beta
    s = np.sqrt(w)[:, None]
    beta, *_ = np.linalg.lstsq(X * s, y * s[:, 0], rcond=None)
    return beta


def blast_radius():
    """How far the served /pal/ Position Fit board moves under the new window.

    Two full in-memory builds; nothing is written to data/positional_fit.json.
    The row SET is asserted identical, because a window change must not add or
    drop a player: qualification is PA and innings, which the ladder never
    touches, so a row-count change would mean something else moved."""
    win_new = pf.LADDER_WINDOW_SEASONS
    # 2012 expressed as a window length, so both branches run the same code path
    win_old = 2026 - pf.LADDER_RETIRED_FIRST_SEASON + 1
    out = {}
    payloads = {}
    for tag, win in (("retired", win_old), ("shipped", win_new)):
        pf.LADDER_WINDOW_SEASONS = win
        payloads[tag] = pf.build(with_backtest=True)
    pf.LADDER_WINDOW_SEASONS = win_new
    A = {r["mlbam"]: r for r in payloads["retired"]["players"]}
    B = {r["mlbam"]: r for r in payloads["shipped"]["players"]}
    if set(A) != set(B):
        raise SystemExit("row set changed under a ladder swap; that is not a "
                         "ladder effect and must be diagnosed before shipping")
    gains = sorted(abs(B[k]["gain_runs_per_650"] - A[k]["gain_runs_per_650"])
                   for k in A if A[k]["gain_runs_per_650"] is not None
                   and B[k]["gain_runs_per_650"] is not None)
    for tag in ("retired", "shipped"):
        p = payloads[tag]
        out[tag] = {"ladder": p["fit"]["ladder"]["values"],
                    "seasons": p["fit"]["ladder"]["seasons"],
                    "n_player_seasons": p["fit"]["ladder"]["n_player_seasons"],
                    "r2": p["fit"]["ladder"]["r2"],
                    "resid_sd": p["fit"]["ladder"]["resid_sd"],
                    "n_flagged_misplaced": p["n_flagged"],
                    "n_flagged_demotion": p["n_flagged_demotion"],
                    "conversion_accuracy_mae": p["conversion_accuracy"]["mae"],
                    "demotion_auc": p["validation"]["auc"]}
    out["delta"] = {
        "n_rows": len(A),
        "best_pos_changed": sum(1 for k in A if A[k]["best_pos"] != B[k]["best_pos"]),
        "misplaced_flag_changed": sum(1 for k in A if bool(A[k]["flagged_misplaced"])
                                      != bool(B[k]["flagged_misplaced"])),
        "gain_abs_delta_median": round(gains[len(gains) // 2], 3),
        "gain_abs_delta_p90": round(gains[int(0.9 * len(gains))], 3),
        "gain_abs_delta_max": round(gains[-1], 3),
    }
    out["note"] = (
        "conversion_accuracy takes no ladder argument (positional_fit.py "
        "conversion_accuracy signature), so the model's VALIDATED claim - the "
        "size of a move, MAE 5.682 on 169 real movers - is measured on the "
        "fielding transfer alone and is byte-identical under the swap. "
        "data/def_home.json cannot move either: def_home_export reads only "
        "p_hold and def_home_entropy off def_value(), and both come from "
        "mlb_position_probs, which never touches POS_ADJ.")
    return out


def main():
    feeds = pf.Feeds()
    first = pf.LADDER_RETIRED_FIRST_SEASON
    X, y, keys, ipp = pf._ladder_design(feeds, first, max(HOLDOUT_SEASONS),
                                        pf.LADDER_MIN_PA)
    yrs = np.array([k[1] for k in keys])
    pids = [k[0] for k in keys]

    # per-row absolute error, one column per spec, filled season by season
    specs = ("champion", "challenger_w", "challenger_r", "control")
    err = {s: np.full(len(y), np.nan) for s in specs}
    per_season = {}
    rng = random.Random(SEED)

    for T in HOLDOUT_SEASONS:
        tr = np.where(yrs <= T - 1)[0]
        te = np.where(yrs == T)[0]
        if not len(te):
            continue
        Xtr, ytr, Xte, yte = X[tr], y[tr], X[te], y[te]
        tr_yrs = yrs[tr]

        b_champ = _fit(Xtr, ytr)

        selw = tr_yrs >= (T - WINDOW_W)
        b_w = _fit(Xtr[selw], ytr[selw])

        wt = DECAY_R ** (T - 1 - tr_yrs).astype(float)
        b_r = _fit(Xtr, ytr, wt)

        # zero-information control: same spec as W, labels permuted in-window
        yperm = ytr[selw].copy()
        idx = list(range(len(yperm)))
        rng.shuffle(idx)
        b_ctl = _fit(Xtr[selw], yperm[idx])

        for name, b in (("champion", b_champ), ("challenger_w", b_w),
                        ("challenger_r", b_r), ("control", b_ctl)):
            err[name][te] = np.abs(Xte @ b - yte)

        per_season[str(T)] = {
            "n_holdout": int(len(te)),
            "n_train": int(len(tr)),
            "train_seasons_champion": [int(tr_yrs.min()), int(T - 1)],
            "train_seasons_challenger_w": [int(T - WINDOW_W), int(T - 1)],
            "mae": {n: round(float(np.nanmean(err[n][te])), 4) for n in specs},
        }
        per_season[str(T)]["dmae_w"] = round(
            per_season[str(T)]["mae"]["champion"]
            - per_season[str(T)]["mae"]["challenger_w"], 4)
        per_season[str(T)]["dmae_r"] = round(
            per_season[str(T)]["mae"]["champion"]
            - per_season[str(T)]["mae"]["challenger_r"], 4)

    scored = np.where(~np.isnan(err["champion"]))[0]
    pooled_mae = {n: float(np.nanmean(err[n][scored])) for n in specs}

    # cluster bootstrap by player: the same man contributes up to three
    # held-out seasons and they are not independent draws.
    by_player = defaultdict(list)
    for i in scored:
        by_player[pids[i]].append(i)
    players = list(by_player)
    nrng = np.random.default_rng(SEED)

    def boot_dmae(name):
        out = []
        for _ in range(BOOT):
            pick = nrng.integers(0, len(players), len(players))
            rows = np.concatenate([by_player[players[p]] for p in pick])
            out.append(float(np.mean(err["champion"][rows] - err[name][rows])))
        out.sort()
        return out

    res = {}
    for name in ("challenger_w", "challenger_r", "control"):
        d = boot_dmae(name)
        res[name] = {
            "dmae_mean": round(pooled_mae["champion"] - pooled_mae[name], 4),
            "ci95": [round(d[int(0.025 * BOOT)], 4), round(d[int(0.975 * BOOT)], 4)],
            "p_better": round(sum(1 for v in d if v > 0) / len(d), 4),
        }

    signs = [per_season[s]["dmae_w"] > 0 for s in per_season]
    passes = {
        "ci_excludes_zero_above": res["challenger_w"]["ci95"][0] > 0,
        "sign_consistency_all_splits": all(signs),
        "control_scores_worse": res["control"]["ci95"][1] < 0,
    }

    # the era rung the fallback would publish, straight off the live artifact
    art = json.loads((ROOT / "data" / "positional_fit.json").read_text(encoding="utf-8"))
    lad = (art.get("fit") or {}).get("ladder") or {}

    doc = {
        "model": "positional_ladder_recency",
        "owner_surface": "positional_fit.fit_ladder -> data/positional_fit.json "
                         "-> prospect_def_value.POS_ADJ",
        "generated_at": "2026-08-07",
        "prereg": "docs/gate-2026-08-07-positional-ladder-recency.md",
        "standard": "docs/EFV_GATE_STANDARD.md",
        "question": "Does a recency-aware ladder predict current-era BRef "
                    "runs_position per 650 PA better than the shipped 2012-onward fit?",
        "protocol": {
            "scoring": "forward-chained: fit on year <= T-1, predict season T",
            "target": "runs_position * 650 / PA (the quantity the ladder inverts)",
            "solution_scored": "UNCENTRED least squares; the level is unidentified "
                               "so recentring is a reporting convention, not a model",
            "holdout_seasons": list(HOLDOUT_SEASONS),
            "n_holdout": int(len(scored)),
            "min_pa": pf.LADDER_MIN_PA,
            "bootstrap": f"{BOOT} draws, CLUSTERED BY PLAYER",
        },
        "specs": {
            "champion": f"unweighted LS from {first} (the shipped window)",
            "challenger_w": f"PRIMARY: unweighted LS, last {WINDOW_W} training seasons",
            "challenger_r": f"SECONDARY (cannot ship alone): weighted LS from {first}, "
                            f"weight {DECAY_R} ** (T-1-season)",
            "control": "challenger_w refit on PERMUTED training labels",
        },
        "pooled_mae_runs_per_650pa": {n: round(v, 4) for n, v in pooled_mae.items()},
        "results": res,
        "per_season": per_season,
        "gate": passes,
        "verdict": None,
        "era_splits_from_artifact": lad.get("era_splits"),
        "shipped_ladder": lad.get("values"),
    }
    if "--blast" in sys.argv:
        doc["served_impact"] = blast_radius()
    ship = all(passes.values())
    doc["verdict"] = {
        "ship": ship,
        "status": "validated" if ship else "deprecated",
        "note": ("All three pre-registered statistical clauses clear. The fourth "
                 "clause is an ATOMICITY requirement, not a measurement: the "
                 "window flip only becomes real when data/positional_fit.json is "
                 "regenerated, and that regen must land with the test_positional_fit "
                 "window and row-count pins rebased plus a build_site pass to "
                 "refresh data/positional_fit_ui.json."
                 if ship else
                 "NO SHIP. Publish the era rung as a labelled secondary column."),
    }
    out = ROOT / "data" / "positional_ladder_recency_eval.json"
    out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(json.dumps({k: doc[k] for k in
                      ("pooled_mae_runs_per_650pa", "results", "per_season", "gate")},
                     indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
