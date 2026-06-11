"""Source-vs-source predictive track record (PROSPX backtesting).

Evaluates how predictive each scouting source's preseason grades have been,
head-to-head, including the PROSPX consensus FV — the core claim a consensus
model has to defend: does blending the inputs beat the best individual input?

Methodology (kept deliberately conservative + disclosed):

  • COHORTS — for each resolved base year (preseason lists only, no in-season
    lookahead), every prospect a rater graded that preseason is a cohort
    member. Players who NEVER debuted stay in the cohort with outcome 0 WAR —
    excluding them would be survivorship bias and would flatter every source.

  • OUTCOME (resolved as of the run date) — cumulative MLB WAR (Baseball-
    Reference) to date, censored at "now". debut = reached MLB; CONTRIBUTOR =
    career WAR >= 3.0; STAR = career WAR >= 10.0. These are low-ish bars
    because the track record is SHORT (see window) — they are stated, not hidden.

  • EVALUATION WINDOW — only base years old enough to have resolved outcomes
    are included (>= MIN_LAG_YEARS of development). With per-source history
    beginning 2021, that is 2021–2023 preseasons → 3–5 years of outcomes. The
    newer sources (ESPN / TJ / Just Baseball / Baseball America) have NO
    resolved cohorts yet and are reported as "insufficient history", not scored.

  • FAIRNESS — the head-to-head accuracy ranking is computed on the COMMON set
    of players every compared rater graded that year (same players, same
    outcome definition, same window), so no source is advantaged by covering an
    easier slice. Per-source calibration tables use each source's full cohort
    (with n disclosed).

  • METRICS — Spearman rank correlation (grade vs realized WAR — ordering
    skill) and ROC AUC (grade discriminating "became a contributor"). Both are
    nonparametric and robust to the FV→WAR scale being nonlinear.

Reads the exported data/timeseries.json (active) + data/debuts.json
(graduated) — the same per-snapshot consensus + per-source FVs + outcome WAR
the site shows — and writes data/source_backtest.json for the Methodology tab.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger("source_backtest")

DATA_DIR = Path(__file__).parent / "data"

# Only score base years with at least this much development lag.
MIN_LAG_YEARS = 3
# Candidate preseason base years (filtered to those resolved + present in data).
# 2017-2020 added via the FanGraphs + MLB Pipeline historical backfill — these
# fully-resolved cohorts extend the evaluation window back four years.
CANDIDATE_YEARS = (2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024)
# Preseason window per base year: Jan 1 – Apr 30. Captures the FanGraphs
# preseason "report" + MLB Pipeline January Top-100/org lists; excludes the
# midseason "updated" list so there is no within-season lookahead.
_WINDOW_START_MMDD = "-01-01"
_WINDOW_END_MMDD = "-05-01"

# Raters with enough multi-year history to score. Keyed by the per_source key
# used in timeseries points[]; "prospx_consensus" is the blended model.
SCORED_SOURCES = ("fangraphs", "mlb_pipeline")
CONSENSUS_KEY = "prospx_consensus"

# Outcome thresholds (cumulative career WAR, censored at run date).
CONTRIBUTOR_WAR = 3.0
STAR_WAR = 10.0
# Rate-based outcomes (WAR per season, among players who debuted) — less
# sensitive to the short censored window than cumulative totals.
REGULAR_WPY = 1.5      # ~ everyday MLB regular pace
ALLSTAR_WPY = 3.0      # ~ All-Star pace

# FV tiers for the cohort/calibration tables (lower-inclusive bins).
FV_TIERS = (
    (60, None, "60+"),
    (55, 60, "55"),
    (50, 55, "50"),
    (45, 50, "45"),
    (0, 45, "<45"),
)


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
def _load_universe(data_dir: Path = DATA_DIR) -> list[dict]:
    """Active prospects + graduated players, each carrying points[] history
    and (for graduates) career_war. Together they are the full graded universe.
    """
    players: list[dict] = []
    ts_path = data_dir / "timeseries.json"
    if ts_path.exists():
        ts = json.loads(ts_path.read_text(encoding="utf-8"))
        players.extend(ts.get("players") or [])
    deb_path = data_dir / "debuts.json"
    if deb_path.exists():
        d = json.loads(deb_path.read_text(encoding="utf-8"))
        players.extend(d if isinstance(d, list) else (d.get("players") or []))
    return players


def _outcome(p: dict) -> dict:
    """Resolved outcome for a player: cumulative WAR (0 if never debuted),
    debut flag, and the contributor/star flags."""
    cw = p.get("career_war") or {}
    war = cw.get("career_war")
    debuted = bool(p.get("debut_date")) or (war is not None) or (p.get("status") == "debuted")
    war = float(war) if war is not None else 0.0
    wpy = cw.get("war_per_yr")
    wpy = float(wpy) if wpy is not None else None
    return {
        "debuted": bool(debuted),
        "war": war,
        "war_per_yr": wpy,
        "contributor": war >= CONTRIBUTOR_WAR,
        "star": war >= STAR_WAR,
        # Rate-based (only meaningful for players who reached MLB).
        "regular_pace": (wpy is not None and wpy >= REGULAR_WPY),
        "allstar_pace": (wpy is not None and wpy >= ALLSTAR_WPY),
    }


def _rater_grades_for_year(p: dict, year: int) -> dict:
    """Extract each rater's preseason FV for `p` in `year` from points[].

    Returns {fangraphs, mlb_pipeline, prospx_consensus} with None where the
    rater didn't grade the player that preseason. consensus = the consensus_fv
    of the latest point inside the preseason window (the board as it stood),
    so it uses only data available by then (no lookahead).
    """
    lo, hi = f"{year}{_WINDOW_START_MMDD}", f"{year}{_WINDOW_END_MMDD}"
    win = [pt for pt in (p.get("points") or [])
           if pt.get("snapshot_date") and lo <= pt["snapshot_date"] < hi]
    if not win:
        return {}
    out: dict = {}
    # Per-source published FV — max across the window's points (a player can
    # appear on both the Top-100 and their org list at the same grade).
    for src in SCORED_SOURCES:
        vals = []
        for pt in win:
            ps = (pt.get("per_source") or {}).get(src) or {}
            v = ps.get("fv_published")
            if v is not None:
                vals.append(float(v))
        if vals:
            out[src] = max(vals)
    # Consensus = latest in-window point's consensus FV.
    win_sorted = sorted(win, key=lambda pt: pt["snapshot_date"])
    cons = win_sorted[-1].get("consensus_fv_raw", win_sorted[-1].get("consensus_fv"))
    if cons is not None:
        out[CONSENSUS_KEY] = float(cons)
    return out


# --------------------------------------------------------------------------
# Stats helpers (no scipy dependency)
# --------------------------------------------------------------------------
def _rankdata(a: list[float]) -> list[float]:
    """Average ranks (ties get the mean of the tied positions)."""
    order = sorted(range(len(a)), key=lambda i: a[i])
    ranks = [0.0] * len(a)
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and a[order[j + 1]] == a[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 4:
        return None
    rx, ry = _rankdata(x), _rankdata(y)
    n = len(x)
    mx, my = sum(rx) / n, sum(ry) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None
    return sxy / (sxx * syy) ** 0.5


def _auc(scores: list[float], labels: list[bool]) -> float | None:
    """ROC AUC via the Mann-Whitney U statistic (ties at 0.5)."""
    pos = [s for s, l in zip(scores, labels) if l]
    neg = [s for s, l in zip(scores, labels) if not l]
    if not pos or not neg:
        return None
    ranks = _rankdata(scores)
    rank_by_idx = {i: ranks[i] for i in range(len(scores))}
    pos_idx = [i for i, l in enumerate(labels) if l]
    sum_ranks_pos = sum(rank_by_idx[i] for i in pos_idx)
    n_pos, n_neg = len(pos), len(neg)
    u = sum_ranks_pos - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


def _tier_of(fv: float) -> str:
    for lo, hi, label in FV_TIERS:
        if fv >= lo and (hi is None or fv < hi):
            return label
    return "<45"


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
def _resolved_years(universe: list[dict], as_of_year: int) -> list[int]:
    present = set()
    for p in universe:
        for pt in (p.get("points") or []):
            sd = pt.get("snapshot_date")
            if sd:
                present.add(int(sd[:4]))
    return [y for y in CANDIDATE_YEARS
            if y in present and (as_of_year - y) >= MIN_LAG_YEARS]


def _tier_table(rows: list[dict]) -> list[dict]:
    """rows: [{fv, outcome}] → per-tier aggregate stats."""
    out = []
    for lo, hi, label in FV_TIERS:
        members = [r for r in rows if r["fv"] >= lo and (hi is None or r["fv"] < hi)]
        n = len(members)
        if not n:
            continue
        wars = [r["outcome"]["war"] for r in members]
        debuts = [r for r in members if r["outcome"]["debuted"]]
        wpys = [r["outcome"]["war_per_yr"] for r in debuts if r["outcome"]["war_per_yr"] is not None]
        out.append({
            "tier": label,
            "n": n,
            "debut_rate": round(sum(1 for r in members if r["outcome"]["debuted"]) / n, 3),
            "mean_war": round(sum(wars) / n, 2),
            "median_war": round(sorted(wars)[n // 2], 2),
            "contributor_rate": round(sum(1 for r in members if r["outcome"]["contributor"]) / n, 3),
            "star_rate": round(sum(1 for r in members if r["outcome"]["star"]) / n, 3),
            # Rate-based outcomes among players who debuted (window-robust).
            "n_debuted": len(debuts),
            "mean_war_per_yr_debut": round(sum(wpys) / len(wpys), 2) if wpys else None,
            "regular_pace_rate": round(sum(1 for r in members if r["outcome"]["regular_pace"]) / n, 3),
            "allstar_pace_rate": round(sum(1 for r in members if r["outcome"]["allstar_pace"]) / n, 3),
        })
    return out


def run_source_backtest(data_dir: Path = DATA_DIR,
                        write: bool = True) -> dict:
    """Compute the full source-vs-source backtest and (optionally) write
    data/source_backtest.json. Returns the result dict."""
    universe = _load_universe(data_dir)
    as_of = date.today()
    years = _resolved_years(universe, as_of.year)
    raters = list(SCORED_SOURCES) + [CONSENSUS_KEY]

    # Gather per (year, player): rater grades + outcome.
    # rows_by_rater[rater] = pooled [{fv, outcome, year, key}] across years.
    rows_by_rater: dict[str, list[dict]] = {r: [] for r in raters}
    # common[year] = [{key, grades:{rater:fv}, outcome}] for players ALL raters graded.
    common_by_year: dict[int, list[dict]] = {y: [] for y in years}

    for p in universe:
        out = _outcome(p)
        for y in years:
            grades = _rater_grades_for_year(p, y)
            if not grades:
                continue
            for rater, fv in grades.items():
                rows_by_rater[rater].append({"fv": fv, "outcome": out, "year": y,
                                             "key": p.get("player_key")})
            if all(r in grades for r in raters):
                common_by_year[y].append({"key": p.get("player_key"),
                                          "grades": {r: grades[r] for r in raters},
                                          "outcome": out})

    # Per-rater cohort/calibration tables (full cohort, pooled across years).
    cohorts = {}
    for rater in raters:
        rows = rows_by_rater[rater]
        cohorts[rater] = {
            "n": len(rows),
            "n_debuted": sum(1 for r in rows if r["outcome"]["debuted"]),
            "tiers": _tier_table(rows),
        }

    # Head-to-head accuracy on the COMMON resolved set (same players).
    def _acc(common_rows: list[dict]) -> dict:
        res = {}
        for rater in raters:
            fvs = [c["grades"][rater] for c in common_rows]
            wars = [c["outcome"]["war"] for c in common_rows]
            contrib = [c["outcome"]["contributor"] for c in common_rows]
            res[rater] = {
                "n": len(common_rows),
                "spearman": (round(_spearman(fvs, wars), 4)
                             if _spearman(fvs, wars) is not None else None),
                "auc": (round(_auc(fvs, contrib), 4)
                        if _auc(fvs, contrib) is not None else None),
            }
        return res

    pooled_common = [c for y in years for c in common_by_year[y]]
    accuracy = {
        "common_n": len(pooled_common),
        "pooled": _acc(pooled_common),
        "per_year": {y: {"common_n": len(common_by_year[y]), **_acc(common_by_year[y])}
                     for y in years if common_by_year[y]},
    }
    # Does the consensus beat its best individual input on each metric?
    def _beats(metric: str) -> dict:
        vals = {r: accuracy["pooled"][r].get(metric) for r in raters}
        cons = vals.get(CONSENSUS_KEY)
        best_input = max((vals[r] for r in SCORED_SOURCES if vals[r] is not None),
                         default=None)
        return {"consensus": cons, "best_input": best_input,
                "consensus_wins": (cons is not None and best_input is not None and cons >= best_input)}
    accuracy["consensus_vs_inputs"] = {
        "spearman": _beats("spearman"),
        "auc": _beats("auc"),
    }

    result = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of_date": as_of.isoformat(),
        "window": {
            "years": years,
            "min_lag_years": MIN_LAG_YEARS,
            "note": (f"Preseason cohorts {min(years)}–{max(years)} (no in-season lookahead), "
                     f"outcomes resolved as of {as_of.isoformat()}."
                     if years else "No base years have resolved outcomes yet."),
        },
        "raters": raters,
        "scored_sources": list(SCORED_SOURCES),
        "insufficient_history": ["espn", "tjstats", "just_baseball", "baseballamerica"],
        "outcome_defs": {
            "contributor_war": CONTRIBUTOR_WAR,
            "star_war": STAR_WAR,
            "regular_war_per_yr": REGULAR_WPY,
            "allstar_war_per_yr": ALLSTAR_WPY,
            "metric": "cumulative MLB bWAR, censored at run date; undebuted = 0. "
                      "Rate outcomes (WAR/yr) computed among players who debuted.",
        },
        "cohorts": cohorts,
        "accuracy": accuracy,
    }

    if write:
        out_path = data_dir / "source_backtest.json"
        out_path.write_text(json.dumps(result, indent=1), encoding="utf-8")
        log.info("wrote %s (%d years, common_n=%d)", out_path, len(years), len(pooled_common))
    return result


# --------------------------------------------------------------------------
# WS-5 — accuracy-weighted consensus (model-audit Phase 4)
# --------------------------------------------------------------------------
# Weight estimator + the vintage-disciplined A/B backtest that decides
# whether weighting ships. VINTAGE RULE: weights usable for board-year Y
# may only see base years RESOLVED by Y (base <= Y - MIN_LAG_YEARS) — a
# 2021 board can't know FanGraphs' 2021-cohort track record.
WEIGHT_SHRINK_K = 150          # pseudo-n toward equal weight
WEIGHT_CLAMP = (0.6, 1.5)      # relative-vote bounds (1.0 = equal)
SPEARMAN_FLOOR = 0.05          # accuracy floor so a near-zero source isn't zeroed


def derive_source_weights(universe: list[dict], max_base_year: int) -> dict:
    """{source: relative vote weight} from pooled common-set Spearman over
    base years <= max_base_year. Sources without resolved history stay at
    1.0 (equal) — new sources are never punished for being new. Weights
    are shrunk toward equal (k pseudo-observations) and clamped."""
    years = [y for y in CANDIDATE_YEARS if y <= max_base_year]
    rows_common: list[dict] = []
    raters = list(SCORED_SOURCES)
    for p in universe:
        out = _outcome(p)
        for y in years:
            grades = _rater_grades_for_year(p, y)
            if grades and all(r in grades for r in raters):
                rows_common.append({"grades": grades, "outcome": out})
    if len(rows_common) < 60:
        return {s: 1.0 for s in SCORED_SOURCES}
    wars = [c["outcome"]["war"] for c in rows_common]
    rho = {}
    for s in raters:
        fvs = [c["grades"][s] for c in rows_common]
        r = _spearman(fvs, wars)
        rho[s] = max(SPEARMAN_FLOOR, r if r is not None else SPEARMAN_FLOOR)
    mean_rho = sum(rho.values()) / len(rho)
    n = len(rows_common)
    out = {}
    for s in raters:
        raw = rho[s] / mean_rho                       # relative accuracy
        shrunk = (n * raw + WEIGHT_SHRINK_K * 1.0) / (n + WEIGHT_SHRINK_K)
        out[s] = round(min(WEIGHT_CLAMP[1], max(WEIGHT_CLAMP[0], shrunk)), 4)
    return out


def run_consensus_weight_ab(data_dir: Path = DATA_DIR, write: bool = True) -> dict:
    """The A/B that decides whether accuracy weighting ships: for each
    evaluable board-year Y, weights are derived ONLY from base years
    resolved by Y, then the weighted two-source blend is scored against
    the equal blend on year-Y's common set (Spearman + AUC). Ship rule:
    weighted >= equal on BOTH pooled metrics."""
    universe = _load_universe(data_dir)
    as_of_year = date.today().year
    resolved = _resolved_years(universe, as_of_year)
    rows_by_year: dict[int, list[dict]] = {}
    for p in universe:
        out = _outcome(p)
        for y in resolved:
            grades = _rater_grades_for_year(p, y)
            if grades and all(s in grades for s in SCORED_SOURCES):
                rows_by_year.setdefault(y, []).append(
                    {"grades": grades, "outcome": out})
    per_year = []
    pooled = {"equal_fv": [], "weighted_fv": [], "war": [], "contrib": []}
    for Y in sorted(rows_by_year):
        vintage_max = Y - MIN_LAG_YEARS
        weights = derive_source_weights(universe, vintage_max)
        if all(abs(w - 1.0) < 1e-9 for w in weights.values()):
            # no resolvable history before Y — weights would be flat; skip
            # the year from the A/B (it can't differentiate A from B).
            continue
        rows = rows_by_year[Y]
        eq, wt, war, contrib = [], [], [], []
        for r in rows:
            g = r["grades"]
            eq.append(sum(g[s] for s in SCORED_SOURCES) / len(SCORED_SOURCES))
            wsum = sum(weights[s] for s in SCORED_SOURCES)
            wt.append(sum(weights[s] * g[s] for s in SCORED_SOURCES) / wsum)
            war.append(r["outcome"]["war"])
            contrib.append(r["outcome"]["contributor"])
        per_year.append({
            "year": Y, "n": len(rows), "weights_vintage_max_base": vintage_max,
            "weights": weights,
            "equal": {"spearman": _r4(_spearman(eq, war)), "auc": _r4(_auc(eq, contrib))},
            "weighted": {"spearman": _r4(_spearman(wt, war)), "auc": _r4(_auc(wt, contrib))},
        })
        pooled["equal_fv"].extend(eq)
        pooled["weighted_fv"].extend(wt)
        pooled["war"].extend(war)
        pooled["contrib"].extend(contrib)
    summary = {
        "pooled_n": len(pooled["war"]),
        "equal": {"spearman": _r4(_spearman(pooled["equal_fv"], pooled["war"])),
                  "auc": _r4(_auc(pooled["equal_fv"], pooled["contrib"]))},
        "weighted": {"spearman": _r4(_spearman(pooled["weighted_fv"], pooled["war"])),
                     "auc": _r4(_auc(pooled["weighted_fv"], pooled["contrib"]))},
    }
    ship = (summary["weighted"]["spearman"] is not None
            and summary["weighted"]["spearman"] >= (summary["equal"]["spearman"] or 0)
            and summary["weighted"]["auc"] is not None
            and summary["weighted"]["auc"] >= (summary["equal"]["auc"] or 0))
    live_weights = derive_source_weights(universe, as_of_year - MIN_LAG_YEARS)
    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "vintage_rule": f"weights for board-year Y use base years <= Y - {MIN_LAG_YEARS} only",
        "per_year": per_year,
        "pooled": summary,
        "ship": ship,
        "live_weights": live_weights,
        "live_weights_vintage_max_base": as_of_year - MIN_LAG_YEARS,
        "notes": [
            "two-source A/B: only FanGraphs + MLB Pipeline have resolvable multi-year history; all other sources stay at weight 1.0 (equal) in the live blend — new sources are never punished for being new",
            f"weights shrunk toward equal with k={WEIGHT_SHRINK_K} pseudo-n, clamped {WEIGHT_CLAMP}",
            "ship rule: weighted >= equal on BOTH pooled Spearman and AUC; loss means equal-weight retains",
        ],
    }
    if write:
        (data_dir / "consensus_weight_eval.json").write_text(
            json.dumps(out, indent=1), encoding="utf-8")
        if ship:
            (data_dir / "source_weights.json").write_text(json.dumps({
                "generated_at": out["generated_at"],
                "vintage_max_base_year": out["live_weights_vintage_max_base"],
                "weights": live_weights,
                "note": "relative vote weights (1.0 = equal); sources absent here vote at 1.0",
            }, indent=1), encoding="utf-8")
        log.info("consensus weight A/B: ship=%s pooled=%s", ship, summary)
    return out


def _r4(v):
    return round(v, 4) if v is not None else None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    r = run_source_backtest()
    import pprint
    print("=== WINDOW ===", r["window"]["note"])
    print("\n=== COHORT TIER TABLES (pooled) ===")
    for rater in r["raters"]:
        print(f"\n{rater}  (n={r['cohorts'][rater]['n']}, debuted={r['cohorts'][rater]['n_debuted']})")
        for t in r["cohorts"][rater]["tiers"]:
            print(f"  {t['tier']:>4}  n={t['n']:<4} debut={t['debut_rate']:.0%}  "
                  f"meanWAR={t['mean_war']:<5} contrib={t['contributor_rate']:.0%}  star={t['star_rate']:.0%}")
    print("\n=== HEAD-TO-HEAD ACCURACY (common set, n=%d) ===" % r["accuracy"]["common_n"])
    for rater in r["raters"]:
        a = r["accuracy"]["pooled"][rater]
        print(f"  {rater:>16}  Spearman ρ={a['spearman']}  AUC={a['auc']}")
    print("\n=== CONSENSUS vs INPUTS ===")
    pprint.pprint(r["accuracy"]["consensus_vs_inputs"])
