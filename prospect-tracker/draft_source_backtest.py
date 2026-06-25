"""Draft-source accuracy weighting (the draft analog of source_backtest.py).

The consensus draft FV is an average of the per-source pre-draft grades
(FanGraphs + MLB Pipeline, plus ESPN on the live board). This asks the same
question the MiLB consensus weighting asks: does one source's pre-draft grade
predict realized MLB value better than the other, and does a relative-accuracy-
weighted blend beat the equal blend? If so, ship vote weights to
data/draft_source_weights.json (consumed by draft_export._consensus); otherwise
equal weighting stands.

METHODOLOGY (mirrors source_backtest.py where the data allows, and is explicit
where it does not):

  • RATERS — fangraphs + mlb_pipeline_draft. These are the only two sources with
    multi-year *resolved* draft history (MLB Pipeline boards backfilled 2018-2025
    via scrapers.MLB_PIPELINE_DRAFT_HISTORY_INTERVALS; FanGraphs draft boards go
    back to 2017). ESPN draft only exists on the live board, so it has no
    resolved cohort and votes at 1.0 (equal) — new sources are never punished
    for being new, same rule as the MiLB blend.

  • COHORT / OUTCOME — every prospect a source graded in a resolved class is a
    cohort member; realized outcome is cumulative MLB bWAR (from debuts.json),
    0 for anyone who never debuted (keeping busts in the cohort — excluding them
    would be survivorship bias that flatters both sources). CONTRIBUTOR = career
    WAR >= 3.0 (the AUC label).

  • RESOLVED WINDOW — draft classes only count once outcomes have had time to
    mature: class Y is scored only when (today - Y) >= MIN_LAG_YEARS = 5. Drafted
    players (especially prep bats/arms) take ~5 yrs to reach and bank MLB value;
    a 3-yr lag would grade on un-played careers. With MLB Pipeline history from
    2018 that resolves classes 2018-2021.

  • VALIDATION — a strict *temporal* vintage A/B (MiLB's: weights for board-year
    Y use only base years resolved by Y) is impossible here: it needs resolved
    base years BEFORE the earliest resolved eval year, i.e. ~2x the lag of
    history, and draft data only starts 2018. The honest out-of-sample substitute
    is LEAVE-ONE-CLASS-OUT cross-validation across the resolved classes — derive
    weights on the other classes, score the held-out one — which never lets a
    class help fit its own weights. The shipped pooled comparison is reported
    alongside the LOO read.

  • WEIGHTS — relative Spearman accuracy (grade vs realized WAR on the COMMON set
    both sources graded), normalized to mean 1.0, shrunk toward equal with k
    pseudo-observations, clamped — identical to derive_source_weights in
    source_backtest.py.

  • SHIP RULE — the weighted blend must be >= the equal blend on BOTH pooled
    Spearman and AUC; a loss means equal weighting retains. LOO is advisory
    (reported, not gating) because per-class n is small.

Writes data/draft_consensus_weight_eval.json (full record) and, when it ships,
data/draft_source_weights.json (the live vote weights).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

# Reuse the MiLB eval's nonparametric stat helpers verbatim (no scipy).
from source_backtest import _spearman, _auc

log = logging.getLogger("draft_source_backtest")

DATA_DIR = Path(__file__).parent / "data"

# Sources with resolvable multi-year draft history to score head-to-head.
DRAFT_SOURCES = ("fangraphs", "mlb_pipeline_draft")
# A draft class is "resolved" (outcomes mature enough to score) at this lag.
MIN_LAG_YEARS = 5
CONTRIBUTOR_WAR = 3.0
# Weight regularization — same knobs as source_backtest.derive_source_weights.
WEIGHT_SHRINK_K = 150
WEIGHT_CLAMP = (0.6, 1.5)
SPEARMAN_FLOOR = 0.05
MIN_COMMON_N = 60   # below this the fit falls back to equal weights


def _r4(v):
    return round(v, 4) if v is not None else None


def _load_outcomes(data_dir: Path) -> dict[str, float]:
    """player_key -> cumulative career bWAR for everyone who reached MLB.
    Drafted prospects join via their promoted_key/milb_key; anyone not here
    never debuted and scores 0 WAR."""
    idx: dict[str, float] = {}
    deb_path = data_dir / "debuts.json"
    if not deb_path.exists():
        return idx
    deb = json.loads(deb_path.read_text(encoding="utf-8"))
    players = deb if isinstance(deb, list) else (deb.get("players") or [])
    for p in players:
        k = p.get("player_key")
        if not k:
            continue
        cw = (p.get("career_war") or {}).get("career_war")
        idx[k] = float(cw) if cw is not None else 0.0
    return idx


def _draft_rows(data_dir: Path) -> list[dict]:
    """One row per graded draft prospect: {year, grades:{src:fv}, war,
    contributor, debuted}. Grade per source is the max published draft FV
    (a player can sit on the Top-250 + their team list at one grade)."""
    outcomes = _load_outcomes(data_dir)
    dr = json.loads((data_dir / "draft_timeseries.json").read_text(encoding="utf-8"))
    rows: list[dict] = []
    for c in dr.get("classes") or []:
        Y = c.get("year")
        for p in c.get("prospects") or []:
            grades: dict[str, float] = {}
            for pt in p.get("points") or []:
                s, fv = pt.get("source"), pt.get("fv")
                if s in DRAFT_SOURCES and fv is not None:
                    grades[s] = max(grades.get(s, float("-inf")), float(fv))
            if not grades:
                continue
            key = p.get("promoted_key") or p.get("milb_key")
            war = outcomes.get(key, 0.0)
            rows.append({
                "year": Y, "grades": grades, "war": war,
                "contributor": war >= CONTRIBUTOR_WAR,
                "debuted": key in outcomes,
            })
    return rows


def _common(rows: list[dict]) -> list[dict]:
    return [r for r in rows if all(s in r["grades"] for s in DRAFT_SOURCES)]


def derive_weights(rows: list[dict]) -> tuple[dict, int, dict]:
    """Relative-Spearman vote weights on the common set, shrunk + clamped.
    Returns (weights, common_n, per_source_rho)."""
    common = _common(rows)
    n = len(common)
    if n < MIN_COMMON_N:
        return {s: 1.0 for s in DRAFT_SOURCES}, n, {}
    wars = [r["war"] for r in common]
    rho: dict[str, float] = {}
    for s in DRAFT_SOURCES:
        r = _spearman([c["grades"][s] for c in common], wars)
        rho[s] = max(SPEARMAN_FLOOR, r if r is not None else SPEARMAN_FLOOR)
    mean_rho = sum(rho.values()) / len(rho)
    out: dict[str, float] = {}
    for s in DRAFT_SOURCES:
        raw = rho[s] / mean_rho
        shrunk = (n * raw + WEIGHT_SHRINK_K * 1.0) / (n + WEIGHT_SHRINK_K)
        out[s] = round(min(WEIGHT_CLAMP[1], max(WEIGHT_CLAMP[0], shrunk)), 4)
    return out, n, {s: round(rho[s], 4) for s in DRAFT_SOURCES}


def _score(rows: list[dict], weights: dict) -> dict:
    """Equal-blend vs weighted-blend accuracy on the common set."""
    common = _common(rows)
    eq, wt, war, contrib = [], [], [], []
    wsum = sum(weights[s] for s in DRAFT_SOURCES)
    for r in common:
        g = r["grades"]
        eq.append(sum(g[s] for s in DRAFT_SOURCES) / len(DRAFT_SOURCES))
        wt.append(sum(weights[s] * g[s] for s in DRAFT_SOURCES) / wsum)
        war.append(r["war"])
        contrib.append(r["contributor"])
    return {
        "n": len(common),
        "equal": {"spearman": _r4(_spearman(eq, war)), "auc": _r4(_auc(eq, contrib))},
        "weighted": {"spearman": _r4(_spearman(wt, war)), "auc": _r4(_auc(wt, contrib))},
    }


def run_draft_weight_ab(data_dir: Path = DATA_DIR, write: bool = True) -> dict:
    today = date.today().year
    rows = _draft_rows(data_dir)
    resolved_years = sorted({
        r["year"] for r in rows
        if r["year"] and (today - r["year"]) >= MIN_LAG_YEARS
        and any(s in r["grades"] for s in DRAFT_SOURCES)
    })
    # restrict to classes that actually carry both raters (a common set)
    resolved_years = [Y for Y in resolved_years
                      if len(_common([r for r in rows if r["year"] == Y])) >= 20]
    res_rows = [r for r in rows if r["year"] in resolved_years]

    live_weights, n_common, rho = derive_weights(res_rows)
    pooled = _score(res_rows, live_weights)

    # Leave-one-class-out: weights fit on the other resolved classes, scored on
    # the held-out class — honest out-of-sample without temporal ordering.
    loo_eq, loo_wt, loo_war, loo_contrib = [], [], [], []
    per_year = []
    for Y in resolved_years:
        train = [r for r in res_rows if r["year"] != Y]
        w_y, n_y, rho_y = derive_weights(train)
        held = _common([r for r in res_rows if r["year"] == Y])
        wsum = sum(w_y[s] for s in DRAFT_SOURCES)
        y_eq, y_wt, y_war, y_con = [], [], [], []
        for r in held:
            g = r["grades"]
            y_eq.append(sum(g[s] for s in DRAFT_SOURCES) / len(DRAFT_SOURCES))
            y_wt.append(sum(w_y[s] * g[s] for s in DRAFT_SOURCES) / wsum)
            y_war.append(r["war"])
            y_con.append(r["contributor"])
        loo_eq += y_eq; loo_wt += y_wt; loo_war += y_war; loo_contrib += y_con
        per_year.append({
            "year": Y, "n": len(held), "train_weights": w_y,
            "debut_rate": _r4(sum(1 for r in held if r["debuted"]) / len(held)) if held else None,
        })
    loo = {
        "n": len(loo_war),
        "equal": {"spearman": _r4(_spearman(loo_eq, loo_war)), "auc": _r4(_auc(loo_eq, loo_contrib))},
        "weighted": {"spearman": _r4(_spearman(loo_wt, loo_war)), "auc": _r4(_auc(loo_wt, loo_contrib))},
    }

    ship = bool(
        pooled["weighted"]["spearman"] is not None and pooled["equal"]["spearman"] is not None
        and pooled["weighted"]["spearman"] >= pooled["equal"]["spearman"]
        and pooled["weighted"]["auc"] is not None and pooled["equal"]["auc"] is not None
        and pooled["weighted"]["auc"] >= pooled["equal"]["auc"]
    )
    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "raters": list(DRAFT_SOURCES),
        "min_lag_years": MIN_LAG_YEARS,
        "resolved_years": resolved_years,
        "common_n": n_common,
        "per_source_spearman": rho,
        "live_weights": live_weights,
        "pooled": pooled,
        "loo_cv": {"per_year": per_year, "pooled": loo},
        "ship": ship,
        "notes": [
            "two-source A/B (FanGraphs vs MLB Pipeline); ESPN + any other source vote at 1.0 (no resolved draft history)",
            f"resolved class = (today - draft_year) >= {MIN_LAG_YEARS}; outcome = cumulative MLB bWAR (0 if never debuted)",
            f"weights = relative Spearman accuracy, shrunk k={WEIGHT_SHRINK_K} toward equal, clamped {WEIGHT_CLAMP}",
            "temporal vintage A/B not yet possible (MLB Pipeline draft history starts 2018, 5y outcome lag); LOO-CV is the out-of-sample read and is advisory, not gating",
            "ship rule: weighted >= equal on BOTH pooled Spearman and AUC",
        ],
    }
    if write:
        (data_dir / "draft_consensus_weight_eval.json").write_text(
            json.dumps(out, indent=1), encoding="utf-8")
        if ship:
            (data_dir / "draft_source_weights.json").write_text(json.dumps({
                "generated_at": out["generated_at"],
                "min_lag_years": MIN_LAG_YEARS,
                "resolved_years": resolved_years,
                "weights": live_weights,
                "note": "relative draft-FV vote weights (1.0 = equal); sources absent here vote at 1.0",
            }, indent=1), encoding="utf-8")
        log.info("draft weight A/B: ship=%s pooled=%s loo=%s", ship, pooled, loo)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import pprint
    pprint.pprint(run_draft_weight_ab())
