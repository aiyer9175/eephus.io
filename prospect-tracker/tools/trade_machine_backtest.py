# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Trade Machine validation backtest (the first OUTCOME validation of the
Trade Machine, which previously had only policy/invariant tests and was absent
from model_registry).

The board/evaluator surplus is the platform value_framework number applied by
``bayes_trade_value.apply_platform_surplus``:

    active prospects -> xfv.json by_player[k].surplus_mm
    MLB modeled      -> mlb_projections.json surNpv / 1e6
    MLB unmodeled    -> xfv.json backgrade surplus_mm

So validating the Trade Machine = validating that the surplus the board SHOWS
orders tradeable assets correctly against what those players actually became.

SLICE A (headline, fully feasible now): for every xfv.json player that has
already resolved an outcome (kind in {debuted, resolved, graduated}) and carries
a realized_war, rank-correlate the surplus the board shows (surplus_mm) against
realized career bWAR, pooled + within surplus tier + by side, with consensus FV
as the baseline ordering to beat. An AUC on "became a useful MLB asset" rounds it
out. RANK ONLY: realized_war is full CAREER bWAR, not unit-comparable to the
remaining-control surplus $ the board shows, so we never report bias/slope here.

SLICE A' (join validation, when data/trade_values.json is present): the SAME
rank check on the ACTUAL displayed trade_value_mm, split by surplus_source, so a
strong MLB (surNpv) signal cannot flatter a weak prospect (xfv) signal and the
apply_platform_surplus join/fallback is exercised end to end.

HONEST CAVEATS (also embedded in the artifact): this is NOT a forward backtest -
trade_values.json was never snapshotted, so we cannot measure "what the board
said then vs what happened." Slice A uses CURRENT grades on ALREADY-graduated
players (survivorship + hindsight) and a career-vs-control-window unit mismatch;
it proves ORDERING, never live trade-price accuracy. A genuine forward cohort
requires snapshotting trade_values.json from now on (a documented next step).

Run:  python tools/trade_machine_backtest.py
Writes data/trade_machine_eval.json. Verdict is hand-committed in model_registry.
"""

from __future__ import annotations

import json
import logging
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from source_backtest import _spearman, _auc                  # noqa: E402  (canonical helpers)
from bayes_trade_value import _platform_tier                 # noqa: E402

log = logging.getLogger(__name__)

XFV_PATH = ROOT / "data" / "xfv.json"
TRADE_VALUES_PATH = ROOT / "data" / "trade_values.json"
ARTIFACT = ROOT / "data" / "trade_machine_eval.json"

# A player who has already resolved an outcome we can score against.
RESOLVED_KINDS = {"debuted", "resolved", "graduated"}
# "Became a useful MLB asset" ~ >=1 WAR/yr over a 6-yr control window of career bWAR.
USEFUL_WAR = 6.0
# The four board tiers we report within-tier ordering for (minimal=negative folds
# into low for the rank check - too few players to rank on its own).
TIER_ORDER = ["elite", "high", "mid", "low"]


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _rnd(x, n=4):
    return round(float(x), n) if x is not None and not (isinstance(x, float) and math.isnan(x)) else None


def _spear(pred: list[float], real: list[float]) -> dict:
    """Spearman + n in a small dict (None spearman when too few / degenerate)."""
    return {"n": len(pred), "spearman": _rnd(_spearman(pred, real))}


def _slice_a(by_player: dict) -> dict:
    """Rank validation of board surplus vs realized career bWAR, from xfv.json."""
    rows = []
    for v in by_player.values():
        if v.get("kind") not in RESOLVED_KINDS:
            continue
        sur, rw = v.get("surplus_mm"), v.get("realized_war")
        if sur is None or rw is None:
            continue
        rows.append({
            "surplus": float(sur),
            "realized": float(rw),
            "consensus_fv": v.get("consensus_fv"),
            "xfv_grade": v.get("xfv_grade"),
            "side": v.get("side"),
            "tier": _platform_tier(float(sur)),
        })

    surp = [r["surplus"] for r in rows]
    real = [r["realized"] for r in rows]

    # Diagnostic: the raw xfv_grade the surplus $ is derived FROM. The convex-$/WAR
    # + $0-floor transform compresses ordering, so xfv_grade orders realized WAR
    # better than surplus_mm (it is the board's within-tier tie-break). Reported,
    # not shipped-on: the board's headline value is intentionally the $ surplus.
    xg_rows = [r for r in rows if r.get("xfv_grade") is not None]
    xfv_pooled = _rnd(_spearman([float(r["xfv_grade"]) for r in xg_rows],
                                [r["realized"] for r in xg_rows])) if len(xg_rows) >= 4 else None

    # Baseline: does raw consensus FV order realized WAR as well as the board surplus?
    cfv_rows = [r for r in rows if r.get("consensus_fv") is not None]
    base_pred = [float(r["consensus_fv"]) for r in cfv_rows]
    base_real = [r["realized"] for r in cfv_rows]

    pooled = _rnd(_spearman(surp, real))
    baseline = _rnd(_spearman(base_pred, base_real))

    by_tier = {}
    tiers_won = 0
    tiers_compared = 0
    for t in TIER_ORDER:
        tr = [r for r in rows if r["tier"] == t]
        if len(tr) < 4:
            by_tier[t] = {"n": len(tr), "spearman": None, "baseline_spearman": None}
            continue
        m = _rnd(_spearman([r["surplus"] for r in tr], [r["realized"] for r in tr]))
        btr = [r for r in tr if r.get("consensus_fv") is not None]
        b = _rnd(_spearman([float(r["consensus_fv"]) for r in btr],
                           [r["realized"] for r in btr])) if len(btr) >= 4 else None
        xtr = [r for r in tr if r.get("xfv_grade") is not None]
        xg = _rnd(_spearman([float(r["xfv_grade"]) for r in xtr],
                            [r["realized"] for r in xtr])) if len(xtr) >= 4 else None
        by_tier[t] = {"n": len(tr), "spearman": m, "baseline_spearman": b, "xfv_grade_spearman": xg}
        if m is not None and b is not None:
            tiers_compared += 1
            if m >= b:
                tiers_won += 1

    by_side = {}
    for s in ("H", "P"):
        sr = [r for r in rows if r["side"] == s]
        by_side[s] = _spear([r["surplus"] for r in sr], [r["realized"] for r in sr])

    # AUC: surplus as a score for "useful MLB asset" (realized career WAR >= 6).
    labels = [r["realized"] >= USEFUL_WAR for r in rows]
    auc = _rnd(_auc(surp, labels))

    # Ship rule (mirrors source_backtest / consensus_weight_ab): the board surplus
    # must order outcomes at least as well as raw consensus FV pooled AND win the
    # within-tier ordering in a majority of the tiers we could compare.
    ship = bool(pooled is not None and baseline is not None
                and pooled >= baseline
                and tiers_compared > 0 and tiers_won >= math.ceil(tiers_compared / 2))

    return {
        "n": len(rows),
        "predictor": "xfv.json surplus_mm (the value the board shows for prospects + the MLB backgrade fallback)",
        "target": "realized_war (full career bWAR) - RANK only",
        "pooled": {"spearman": pooled, "auc_useful_asset": auc, "useful_war_threshold": USEFUL_WAR},
        "baseline_consensus_fv": {"spearman": baseline, "n": len(cfv_rows)},
        "xfv_grade_orderer": {"spearman": xfv_pooled, "n": len(xg_rows),
                              "note": "the raw grade the surplus is derived from; orders realized "
                                      "WAR better than the $-transform (board within-tier tie-break)"},
        "by_tier": by_tier,
        "by_side": by_side,
        "tiers_won_vs_baseline": f"{tiers_won}/{tiers_compared}",
        "ship": ship,
    }


def _slice_a_prime(by_player: dict, trade_values: dict) -> dict | None:
    """Per-surplus-source rank check on the ACTUAL displayed trade_value_mm,
    joined to realized_war via player_key. Exercises apply_platform_surplus's
    xfv / projection / backgrade join + fallback. Skipped if trade_values.json
    is absent."""
    players = (trade_values or {}).get("players") or []
    if not players:
        return None
    realized = {k: v.get("realized_war") for k, v in by_player.items()
                if v.get("realized_war") is not None}
    by_source: dict[str, dict] = {}
    matched = 0
    for p in players:
        if p.get("status") not in RESOLVED_KINDS:
            continue
        pk = p.get("player_key")
        tv = p.get("trade_value_mm")
        rw = realized.get(pk)
        if pk is None or tv is None or rw is None:
            continue
        matched += 1
        src = p.get("surplus_source") or "unknown"
        b = by_source.setdefault(src, {"pred": [], "real": []})
        b["pred"].append(float(tv))
        b["real"].append(float(rw))
    if not matched:
        return None
    out = {"n_matched": matched, "generated_at": trade_values.get("generated_at"),
           "predictor": "trade_values.json trade_value_mm (post apply_platform_surplus)",
           "by_source": {}}
    allp, allr = [], []
    for src, b in by_source.items():
        out["by_source"][src] = _spear(b["pred"], b["real"])
        allp += b["pred"]
        allr += b["real"]
    out["pooled"] = _spear(allp, allr)
    return out


def run(write: bool = True) -> dict:
    xfv = _load(XFV_PATH)
    by_player = (xfv or {}).get("by_player") or {}
    if not by_player:
        raise RuntimeError(f"xfv.json missing or has no by_player ({XFV_PATH})")

    slice_a = _slice_a(by_player)
    slice_a_prime = _slice_a_prime(by_player, _load(TRADE_VALUES_PATH))

    artifact = {
        "generated_at": (xfv.get("generated_at") or ""),
        "model": "trade_machine_surplus",
        "conventions": {
            "predictor": "trade_values.json trade_value_mm = apply_platform_surplus "
                         "(xfv.surplus_mm for prospects, mlb_projections surNpv/1e6 for MLB, "
                         "xfv backgrade fallback)",
            "target": "xfv.realized_war = full career bWAR (efv_score.py) - RANK only, "
                      "NOT unit-comparable to remaining-control surplus $",
            "metric": "rank-Spearman + AUC(useful-asset); higher is better",
            "ship_rule": "board surplus Spearman >= consensus_fv pooled AND wins within-tier "
                         "ordering in a majority of comparable tiers",
        },
        "slice_a": slice_a,
        "slice_a_prime_by_source": slice_a_prime,
        "ship": slice_a["ship"],
        "honest_note": (
            "NOT a forward backtest: trade_values.json was never snapshotted, so we cannot "
            "measure what the board said then vs what happened. Slice A uses CURRENT grades on "
            "ALREADY-graduated players (survivorship + hindsight) and a career-vs-control-window "
            "unit mismatch, so it proves ORDERING only, never live trade-price accuracy. The "
            "displayed surplus is a passthrough of xfv (xfv_eval, provisional) and projections "
            "(proj_horizon_eval), so this validates the ORDERING + the apply_platform_surplus "
            "join/fallback, not new model machinery. Verdict stays provisional until a genuine "
            "forward cohort accrues - start snapshotting trade_values.json now. Slice B "
            "(bounded-window calibration via surplus_backtest_real on 2017-2019 resolved cohorts) "
            "is the documented next extension."
        ),
    }

    if write:
        ARTIFACT.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        log.info("trade_machine_backtest: n=%d pooled_spearman=%s ship=%s -> %s",
                 slice_a["n"], slice_a["pooled"]["spearman"], artifact["ship"], ARTIFACT.name)
    return artifact


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    a = run(write=True)
    sa = a["slice_a"]
    print(f"\nTrade Machine validation backtest  (n={sa['n']})")
    print(f"  pooled Spearman   : {sa['pooled']['spearman']}  "
          f"(consensus_fv baseline {a['slice_a']['baseline_consensus_fv']['spearman']})")
    print(f"  AUC useful-asset  : {sa['pooled']['auc_useful_asset']}")
    print(f"  within-tier won   : {sa['tiers_won_vs_baseline']}")
    for t, d in sa["by_tier"].items():
        print(f"    {t:>6}: n={d['n']:>4}  spearman={d['spearman']}  base={d['baseline_spearman']}")
    print(f"  by side           : {sa['by_side']}")
    if a["slice_a_prime_by_source"]:
        print(f"  by surplus_source : {a['slice_a_prime_by_source']['by_source']}")
    print(f"  SHIP              : {a['ship']}")
