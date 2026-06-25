# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Type-conditioned consensus weights A/B (model-audit follow-up to the
Phase-4a accuracy-weighted consensus SHIP).

Hypothesis: a source's eye may differ by player type - one shop grades
pitchers better, another hitters - so SEPARATE hitter/pitcher accuracy
weights could beat the shipped GLOBAL weights. Same vintage discipline
as run_consensus_weight_ab (weights for board-year Y see base years
<= Y - MIN_LAG_YEARS only); the challenger is type-conditioned weights,
the champion is the SHIPPED global weighting (not equal weights - that
bar was already cleared).

Ship rule: type-conditioned >= global on pooled Spearman AND AUC.
RESULT (2026-06-11): LOST on both (Spearman .2705 vs .2717, AUC .7604
vs .7634, n=3,127) - the per-type common sets are too thin to beat the
shrinkage toward equal. The loss is committed as the type_conditioned_ab
block inside data/consensus_weight_eval.json (the parent model's
artifact - failed challengers never get their own *_eval.json file,
they live as blocks, same as proj_horizon_eval's challenger_blocks).

Run: python tools/consensus_type_ab.py
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from source_backtest import (                                  # noqa: E402
    CANDIDATE_YEARS, MIN_LAG_YEARS, SCORED_SOURCES, SPEARMAN_FLOOR,
    WEIGHT_CLAMP, WEIGHT_SHRINK_K, _auc, _load_universe, _outcome,
    _rater_grades_for_year, _resolved_years, _spearman,
    derive_source_weights,
)

PITCH_POS = {"SP", "RP", "P", "LHP", "RHP", "SP2", "SIRP", "MIRP", "TWP"}


def _is_pitcher(p: dict) -> bool:
    head = str(p.get("position") or "").upper().split("/")[0].strip()
    return head in PITCH_POS


def derive_type_weights(universe: list[dict], max_base_year: int,
                        pitcher: bool) -> dict:
    """derive_source_weights restricted to one player type. Mirrors the
    shipped estimator exactly (shrink k, clamp, floor) so the A/B isolates
    ONE change: the conditioning set."""
    years = [y for y in CANDIDATE_YEARS if y <= max_base_year]
    rows = []
    raters = list(SCORED_SOURCES)
    for p in universe:
        if _is_pitcher(p) != pitcher:
            continue
        out = _outcome(p)
        for y in years:
            g = _rater_grades_for_year(p, y)
            if g and all(r in g for r in raters):
                rows.append({"grades": g, "outcome": out})
    if len(rows) < 60:        # same evidence floor as the global estimator
        return {s: 1.0 for s in SCORED_SOURCES}
    wars = [c["outcome"]["war"] for c in rows]
    rho = {}
    for s in raters:
        r = _spearman([c["grades"][s] for c in rows], wars)
        rho[s] = max(SPEARMAN_FLOOR, r if r is not None else SPEARMAN_FLOOR)
    mean_rho = sum(rho.values()) / len(rho)
    n = len(rows)
    out = {}
    for s in raters:
        raw = rho[s] / mean_rho
        shrunk = (n * raw + WEIGHT_SHRINK_K * 1.0) / (n + WEIGHT_SHRINK_K)
        out[s] = round(min(WEIGHT_CLAMP[1], max(WEIGHT_CLAMP[0], shrunk)), 4)
    return out


def run_ab(data_dir: Path | None = None, write: bool = True) -> dict:
    data_dir = data_dir or (ROOT / "data")
    universe = _load_universe(data_dir)
    as_of_year = date.today().year
    resolved = _resolved_years(universe, as_of_year)
    rows_by_year: dict[int, list[dict]] = {}
    for p in universe:
        out = _outcome(p)
        for y in resolved:
            g = _rater_grades_for_year(p, y)
            if g and all(s in g for s in SCORED_SOURCES):
                rows_by_year.setdefault(y, []).append(
                    {"grades": g, "outcome": out, "pitcher": _is_pitcher(p)})
    per_year = []
    pooled = {"global_fv": [], "typed_fv": [], "war": [], "contrib": []}
    for Y in sorted(rows_by_year):
        vmax = Y - MIN_LAG_YEARS
        w_global = derive_source_weights(universe, vmax)
        w_hit = derive_type_weights(universe, vmax, pitcher=False)
        w_pit = derive_type_weights(universe, vmax, pitcher=True)
        if all(abs(w - 1.0) < 1e-9 for w in w_global.values()):
            continue   # year can't differentiate (same skip as the shipped A/B)
        rows = rows_by_year[Y]
        gl, ty, war, contrib = [], [], [], []
        for r in rows:
            g = r["grades"]
            wg = w_global
            wt = w_pit if r["pitcher"] else w_hit
            gl.append(sum(wg[s] * g[s] for s in SCORED_SOURCES)
                      / sum(wg[s] for s in SCORED_SOURCES))
            ty.append(sum(wt[s] * g[s] for s in SCORED_SOURCES)
                      / sum(wt[s] for s in SCORED_SOURCES))
            war.append(r["outcome"]["war"])
            contrib.append(r["outcome"]["contributor"])
        def _r4(v): return None if v is None else round(v, 4)
        per_year.append({
            "year": Y, "n": len(rows), "vintage_max_base": vmax,
            "weights_global": w_global,
            "weights_hitter": w_hit, "weights_pitcher": w_pit,
            "global": {"spearman": _r4(_spearman(gl, war)), "auc": _r4(_auc(gl, contrib))},
            "typed": {"spearman": _r4(_spearman(ty, war)), "auc": _r4(_auc(ty, contrib))},
        })
        pooled["global_fv"].extend(gl)
        pooled["typed_fv"].extend(ty)
        pooled["war"].extend(war)
        pooled["contrib"].extend(contrib)
    def _r4(v): return None if v is None else round(v, 4)
    summary = {
        "pooled_n": len(pooled["war"]),
        "global": {"spearman": _r4(_spearman(pooled["global_fv"], pooled["war"])),
                   "auc": _r4(_auc(pooled["global_fv"], pooled["contrib"]))},
        "typed": {"spearman": _r4(_spearman(pooled["typed_fv"], pooled["war"])),
                  "auc": _r4(_auc(pooled["typed_fv"], pooled["contrib"]))},
    }
    ship = (summary["typed"]["spearman"] is not None
            and summary["typed"]["spearman"] >= (summary["global"]["spearman"] or 0)
            and summary["typed"]["auc"] is not None
            and summary["typed"]["auc"] >= (summary["global"]["auc"] or 0))
    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "experiment": "type-conditioned (hitter/pitcher) source weights vs the "
                      "SHIPPED global accuracy weighting - same estimator, same "
                      "vintage rule, one change (the conditioning set)",
        "vintage_rule": f"weights for board-year Y use base years <= Y - {MIN_LAG_YEARS} only",
        "per_year": per_year,
        "pooled": summary,
        "ship": ship,
    }
    if write:
        # fold into the parent model's artifact (standing-rule pattern:
        # challenger results are blocks, never standalone *_eval.json files)
        p = data_dir / "consensus_weight_eval.json"
        parent = json.loads(p.read_text(encoding="utf-8"))
        parent["type_conditioned_ab"] = out
        p.write_text(json.dumps(parent, indent=1), encoding="utf-8")
        print(f"wrote type_conditioned_ab block into {p}")
    return out


if __name__ == "__main__":
    rep = run_ab()
    print(json.dumps(rep["pooled"], indent=1))
    print("ship:", rep["ship"])
