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
import random
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

# --------------------------------------------------------------------------
# Source classification: DERIVED, not asserted (Lane BA3, 2026-08-07b).
# --------------------------------------------------------------------------
# `insufficient_history` used to be a literal list of four source names. It was
# written when Baseball America had one rank-only snapshot in the database, and
# it went on asserting "no resolvable cohorts" after BA acquired four preseason
# org-board vintages (2023-02-15 through 2026-02-15, 383-385 rows each, every row
# carrying an FV). The 2023 vintage joins the outcome universe on 332 rows and IS
# resolvable at MIN_LAG_YEARS=3. The string was simply out of date, and being a
# string it could not notice.
#
# Everything below is now counted from the same universe the backtest scores, so
# the classification self-corrects the day a vintage resolves. See
# docs/efv-2026-08-07b/BA_SOURCE_CLASS_GATE.md for the pre-registration and
# data/ba_source_class_eval.json for the measurement.
#
# TWO conditions, because history alone is not the binding one:
#
#   1. HISTORY. At least SOURCE_CLASS_MIN_ROWS resolvable preseason rows in a
#      single base year. 100 is the smallest count that leaves a pooled Spearman
#      with any precision once the common-set intersection has cut it down
#      (compare ARCH_MIN_N = 40 below).
#
#   2. COMMON-SET RETENTION. `run_source_backtest` admits a player to the common
#      set only when EVERY scored rater graded him, so a new rater does not add a
#      bar to the chart, it redefines the population every other bar is computed
#      on. Re-measured 2026-08-12: admitting BA takes the common set from 4,299
#      rows to 666, a retention of 0.1549. THAT is the reason it stays out, it is
#      arithmetic, and it does not expire.
#
#      TWO CORRECTIONS TO WHAT THIS COMMENT USED TO SAY, both found by the D3
#      basis re-derivation (docs/efv-2026-08-12/SOURCE_SCORING_BASIS_GATE.md).
#
#      (1) THE RATER-ORDER FLIP IS A YEAR EFFECT, NOT A BA EFFECT. This comment
#      attributed the flip (mlb_pipeline > fangraphs becoming fangraphs >
#      mlb_pipeline) to admitting BA. It is not: restricting the INCUMBENT pair
#      to 2023 alone, with Baseball America absent entirely and not scored,
#      already flips it. On the full window fangraphs 0.2473 trails
#      mlb_pipeline 0.2810; on 2023 alone fangraphs 0.2533 leads mlb_pipeline
#      0.2137, n=828. Admitting BA and restricting to the one year BA covers are
#      two different things and the old wording ran them together. The published
#      same-year benchmark in `pairwise_head_to_head` is exactly this number, so
#      the correction is checkable rather than asserted.
#
#      (2) THE RETENTION GATE CANNOT BE PASSED BY A SHORT-HISTORY SOURCE, BY
#      CONSTRUCTION. `retention` divides a source's coverage by the ALL-YEARS
#      pooled common set, so BA's ceiling is 828/4299 = 0.1926 even if it graded
#      every row of the only year it covers, against a 0.75 gate. That is not a
#      defect: the quantity being measured is the COST OF ADMISSION under a
#      global intersection, and that cost really is 85% of the evidence. It does
#      mean the gate can never be the thing that lets BA in, and that scoring BA
#      needed a different BASIS rather than a lower threshold. Year-matched, the
#      same measurement reads 666/828 = 0.8043, which is why the pairwise view
#      can score BA at all.
#
#      A source that costs 85% of the evidence has to be kept out for THAT
#      reason, which is measured and does not expire, rather than for
#      "insufficient history", which was neither.
#
# Promotion into SCORED_SOURCES stays an explicit edit, because it restates every
# published accuracy number. What the code no longer does is assert the answer:
# when a source clears both conditions the classification says `scoreable_now`
# and a warning is logged, so the promotion is a data event someone is told about.
SOURCE_CLASS_MIN_ROWS = 100
SOURCE_CLASS_MIN_COMMON_RETENTION = 0.75

# Synthetic / derived per_source keys that are not outlets with a grading scale.
# performance_ingest hands every auto-tracked player the same provisional FV floor
# and draft_signing is a bonus-derived anchor (both are pass-through in
# grade_normalization for the same reason); *_statcast_by_age is a derived overlay,
# not a published board. None of them is a rater, so none is classifiable as one.
_NON_RATER_SOURCES = frozenset({"performance_ingest", "draft_signing", "auto_detect"})

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

# Prospect archetypes for the per-archetype track record: bat/arm from position,
# HS/college/international from signing path. HS vs college uses age-at-draft
# (draft_year - birth_year), which matches explicit scouting HS/college labels
# ~99% of the time and needs no extra data source (self-contained on the
# exported universe).
# CP and CL added 2026-08-09 (lane C-A2). The set was written against the
# FanGraphs / MLB Pipeline role vocabulary (SIRP / MIRP) and never learned the
# closer token Baseball America uses: prospects.db carries 22 snapshot rows at
# position CP, all on the 2023 BA org boards, and they reach the published table
# through the player-level `position` the export carries. On the current universe
# that mislabelled 6 distinct players as BATS: 23 rows of the 4,284-row pooled
# common set (13 college_bat, 8 hs_bat, 2 intl_bat) and, after the one-row-per-
# player dedup the archetype table runs on, 6 of 1,517 (3 college_bat, 2 hs_bat,
# 1 intl_bat). CL is not in the database today and is added with CP because it is
# the same role in the other common spelling: a closer must not be able to enter
# the bat/arm split as a bat because of which outlet typed the row.
# The intl_arm cell is 196 rows, so 1 misrouted row is 0.5% of it.
_PITCH_POS = {"P", "RHP", "LHP", "SP", "RP", "SIRP", "MIRP", "CP", "CL"}
# TWP (two-way) is EXCLUDED from the split, not guessed into it. The archetype
# axis is bat-vs-arm and a two-way player is a member of both, so any assignment
# is a coin flip that a reader would nonetheless read as a measurement, and the
# cell it lands in is one of the thin ones (intl_arm n=195). 6 players in the
# universe carry TWP and NONE of them is in today's common set, so excluding them
# moves no published number now and prevents a silent miscount when one arrives.
# 4C (four-corners) stays a bat by falling through: it is a corner-infield /
# corner-outfield label, not a pitching role.
_TWO_WAY_POS = frozenset({"TWP"})
_ARCH_ORDER = ("hs_bat", "hs_arm", "college_bat", "college_arm", "intl_bat", "intl_arm")
_ARCH_LABELS = {
    "hs_bat": "HS bats", "hs_arm": "HS arms",
    "college_bat": "College bats", "college_arm": "College arms",
    "intl_bat": "Int'l bats", "intl_arm": "Int'l arms",
}
ARCH_MIN_N = 40   # don't score a thinly-populated archetype

# --------------------------------------------------------------------------
# Which protocol produced a rater's number (F3, 2026-08-09).
# --------------------------------------------------------------------------
# The per-source bars are scored IN SAMPLE on the common set: the boards were not
# fit to these outcomes, but they are not held out from them either, and the same
# rows both define the population and score it. eFV enters with its forward-chained
# out-of-sample grade, which is the HARDER bar. The module has always said so in
# prose (`_xfv_vs_consensus`'s docstring, the surface's "more conservative test than
# the in-sample common-set bars above"), and the served numbers carried no field a
# renderer could key off, so the marker on the surface was a hardcoded rater name.
# That breaks silently the day a second out-of-sample model joins the table. The
# basis now travels WITH the number.
_OOS_RATERS = frozenset({"xfv"})
BASIS_IN_SAMPLE = "in_sample_common_set"
BASIS_OOS = "forward_chained_oos"


def _rater_basis(rater: str) -> str:
    return BASIS_OOS if rater in _OOS_RATERS else BASIS_IN_SAMPLE


def _archetype(p: dict) -> str | None:
    pos = (p.get("position") or "").upper().split("/")[0]
    if pos in _TWO_WAY_POS:
        return None
    side = "arm" if pos in _PITCH_POS else "bat"
    a = p.get("acquisition") or {}
    method = a.get("method")
    if method == "international_fa":
        org = "intl"
    elif method == "draft":
        by, yr = (p.get("birth_date") or "")[:4], a.get("year")
        if not (by.isdigit() and yr):
            return None
        org = "hs" if (int(yr) - int(by)) <= 19 else "college"
    else:
        return None
    return f"{org}_{side}"


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
    dd = str(p.get("debut_date") or "")
    return {
        "debuted": bool(debuted),
        "debut_year": int(dd[:4]) if dd[:4].isdigit() else None,
        "war": war,
        "war_per_yr": wpy,
        "contributor": war >= CONTRIBUTOR_WAR,
        "star": war >= STAR_WAR,
        # Rate-based (only meaningful for players who reached MLB).
        "regular_pace": (wpy is not None and wpy >= REGULAR_WPY),
        "allstar_pace": (wpy is not None and wpy >= ALLSTAR_WPY),
    }


def _all_source_grades_by_year(p: dict) -> tuple[dict, dict]:
    """(in_window, out_of_window) source coverage for `p`, one pass over points[].

    in_window     = {base_year: {source: max published preseason FV, or None}}
    out_of_window = {year: {source}}: the source published on this player OUTSIDE
                    the preseason window (midseason boards, e.g. Baseball America's
                    June Top 100 and Just Baseball's in-season lists)

    Same window and same max-across-the-window rule as `_rater_grades_for_year`,
    but not restricted to SCORED_SOURCES, and this is what lets the classification
    below count a source the backtest does not (yet) score, including vintages too
    recent to be scoreable and boards that fall outside the window entirely.

    An in-window value of None means the source APPEARED but published a rank with
    no FV. Those rows are counted so the source can be classified as rank-only
    rather than silently disappearing, and they never contribute a number: a null
    grade must not be read as an FV of zero.
    """
    inw: dict = {}
    outw: dict = {}
    for pt in (p.get("points") or []):
        sd = pt.get("snapshot_date")
        if not sd:
            continue
        try:
            year = int(sd[:4])
        except (TypeError, ValueError):
            continue
        # The window is [YYYY-01-01, YYYY-05-01) of the snapshot's OWN year, so the
        # year prefix cancels and membership is decided by the "-MM-DD" suffix alone.
        # Identical test to _rater_grades_for_year's `lo <= sd < hi`.
        in_window = _WINDOW_START_MMDD <= sd[4:] < _WINDOW_END_MMDD
        bucket = inw.setdefault(year, {}) if in_window else None
        for src, ps in (pt.get("per_source") or {}).items():
            if src in _NON_RATER_SOURCES or src.endswith("_statcast_by_age"):
                continue
            if not in_window:
                outw.setdefault(year, set()).add(src)
                continue
            v = (ps or {}).get("fv_published")
            if v is None:
                bucket.setdefault(src, None)
                continue
            v = float(v)
            prev = bucket.get(src)
            bucket[src] = v if prev is None else max(prev, v)
    return inw, outw


def classify_sources(source_year_rows: dict, source_year_rank_only: dict,
                     source_year_out_of_window: dict,
                     common_cover: dict, common_n: int,
                     years: list[int], as_of_year: int) -> list[dict]:
    """Derive each non-scored source's classification from counted rows.

    source_year_rows[source][year]          = preseason rows it published an FV on.
    source_year_rank_only[source][year]     = preseason rows with a rank but no FV.
    source_year_out_of_window[source][year] = rows outside the preseason window.
    common_cover[source]                    = how many of the CURRENT common-set rows
                                              that source also graded, i.e. exactly
                                              the population that would survive
                                              admitting it as a rater.

    Returns one record per candidate source carrying the numbers behind its
    classification, so the served artifact can cite a row count and a year instead
    of a bare string. Sorted scoreable-first, then by resolvable row count.
    """
    out: list[dict] = []
    seen = set(source_year_rows) | set(source_year_rank_only) | set(source_year_out_of_window)
    for src in sorted(seen):
        if src in SCORED_SOURCES or src == CONSENSUS_KEY:
            continue
        by_year = {y: n for y, n in sorted(source_year_rows.get(src, {}).items()) if n}
        rank_only = {y: n for y, n in sorted(source_year_rank_only.get(src, {}).items()) if n}
        off_window = {y: n for y, n in sorted(source_year_out_of_window.get(src, {}).items()) if n}
        resolvable = {y: n for y, n in by_year.items()
                      if y in years}                     # years[] is already lag-filtered
        best_year, best_rows = None, 0
        for y, n in resolvable.items():
            if n > best_rows:
                best_year, best_rows = y, n
        history_ok = best_rows >= SOURCE_CLASS_MIN_ROWS
        retention = (common_cover.get(src, 0) / common_n) if common_n else 0.0
        common_ok = retention >= SOURCE_CLASS_MIN_COMMON_RETENTION

        # When does the next unresolved vintage become scoreable? A vintage needs
        # BOTH the development lag AND membership in CANDIDATE_YEARS, and the
        # second is a hardcoded tuple that can block a cohort physics has already
        # resolved. Report the two separately so the tuple cannot fail silently.
        pending = [(y, n) for y, n in by_year.items()
                   if y not in years and n >= SOURCE_CLASS_MIN_ROWS]
        first_year, needs_tuple = None, []
        for y, _n in sorted(pending):
            if y not in CANDIDATE_YEARS:
                needs_tuple.append(y)
                continue
            cand = y + MIN_LAG_YEARS
            if first_year is None or cand < first_year:
                first_year = cand
        if history_ok and not common_ok:
            # The BA case: the history exists, admitting it is what costs.
            reason = "common_set_collapse"
        elif not by_year and rank_only:
            # Publishes a board but no grades, so there is nothing to score and
            # no amount of waiting changes that.
            reason = "no_published_fv"
        elif not by_year and not rank_only and off_window:
            # Publishes only outside Jan 1 to Apr 30, so the preseason window this
            # backtest is defined on never sees it. Not a history problem.
            reason = "no_preseason_board"
        elif not history_ok and best_rows:
            reason = "thin_resolvable_cohort"
        elif not history_ok:
            reason = "insufficient_history"
        else:
            reason = None
        out.append({
            "source": src,
            "scoreable_now": bool(history_ok and common_ok),
            "blocked_by": reason,
            "history_ok": bool(history_ok),
            "common_set_ok": bool(common_ok),
            "resolvable_rows_best_year": best_rows,
            "resolvable_best_base_year": best_year,
            "resolvable_rows_total": sum(resolvable.values()),
            "rows_by_base_year": by_year,
            "rank_only_rows_by_base_year": rank_only,
            "out_of_window_rows_by_year": off_window,
            "resolvable_base_years": sorted(resolvable),
            "common_set_rows_covered": common_cover.get(src, 0),
            "common_set_n": common_n,
            "common_set_retention": round(retention, 4),
            "min_rows": SOURCE_CLASS_MIN_ROWS,
            "min_common_retention": SOURCE_CLASS_MIN_COMMON_RETENTION,
            "scoreable_from_run_year": first_year,
            "base_years_blocked_by_candidate_years": needs_tuple,
            "as_of_run_year": as_of_year,
        })
    out.sort(key=lambda r: (not r["scoreable_now"], -r["resolvable_rows_best_year"], r["source"]))
    return out


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


def _archetype_accuracy(common_rows: list[dict], raters: list[str]) -> list[dict]:
    """Per-archetype head-to-head accuracy on the COMMON set (same players each
    rater graded). AUC = grade discriminates 'became a contributor'; Spearman =
    ordering vs realized WAR. Archetypes below ARCH_MIN_N are dropped (n disclosed).

    Two rater tables, because they answer two questions (2026-08-07):
      raters            = each rater on the rows IT graded. The per-source coverage
                          and calibration story; eFV's n is smaller than everyone's.
      raters_efv_common = every rater on the rows eFV also graded. The ONLY basis on
                          which an eFV-vs-source cell in this table is a contest.
    The Diamond hub's archetype table green-highlights the higher of two numbers, and
    on the `raters` basis those two numbers were not computed on the same players.
    """
    out = []
    for arch in _ARCH_ORDER:
        rows = [c for c in common_rows if c.get("archetype") == arch]
        if len(rows) < ARCH_MIN_N:
            continue

        def _per(pool):
            per = {}
            for r in raters:
                rr = [c for c in pool if c["grades"].get(r) is not None]  # eFV may be missing
                if len(rr) < ARCH_MIN_N:
                    continue
                fvs = [c["grades"][r] for c in rr]
                wars = [c["outcome"]["war"] for c in rr]
                contrib = [c["outcome"]["contributor"] for c in rr]
                sp, au = _spearman(fvs, wars), _auc(fvs, contrib)
                per[r] = {"n": len(rr), "basis": _rater_basis(r),
                          "spearman": round(sp, 4) if sp is not None else None,
                          "auc": round(au, 4) if au is not None else None}
            return per

        efv_rows = [c for c in rows if c["grades"].get("xfv") is not None]
        row = {"archetype": arch, "label": _ARCH_LABELS[arch],
               "n": len(rows), "raters": _per(rows)}
        if len(efv_rows) >= ARCH_MIN_N:
            row["n_efv"] = len(efv_rows)
            row["raters_efv_common"] = _per(efv_rows)
        out.append(row)
    return out


def _xfv_vs_consensus(data_dir: Path = DATA_DIR) -> dict | None:
    """eFV (our outcome-grounded model) vs consensus FV, lifted from the eFV eval
    artifacts. Reported SEPARATELY from the per-source bars because it is the
    model's OWN out-of-sample protocol (forward-chained, leakage-clean), not the
    in-sample common-set backtest the sources share -- OOS is the HARDER bar, so a
    win here is conservative. This is the honest 'eFV beats consensus on rank' record."""
    out = {"protocol": ("forward-chained out-of-sample; debuted cohort; first-6-season "
                        "bWAR (KM-censored). The shipped headline rank is the guarded "
                        "blend (consensus prior + the model edge that survives OOS)."),
           "sides": {}}
    found = False
    block = None
    for side, fn in (("hitters", "xfv_eval.json"), ("pitchers", "xfv_eval_pitcher.json")):
        p = data_dir / fn
        if not p.exists():
            continue
        try:
            ev = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        pooled = ((ev.get("evals") or {}).get("debuted_km") or {}).get("pooled_oos") or {}
        base = (pooled.get("baseline") or {}).get("spearman")
        blend = (pooled.get("blend") or {}).get("spearman")
        if base is None or blend is None:
            continue
        found = True
        # The two-metric gate's second leg, lifted from whichever side artifact
        # carries it. It is JOINT (both sides in one number), so both artifacts hold
        # the identical block and reading either one is correct.
        if block is None and isinstance(ev.get("block_rho"), dict) and "error" not in ev["block_rho"]:
            block = ev["block_rho"]
        # HONEST VERDICT, not a bare inequality (2026-08-06).
        #
        # This published `xfv_beats` to the Methodology tab as `blend > base`,
        # with no minimum detectable effect anywhere near it. That was tolerable
        # while the pitcher delta was +0.0533 against an MDE95 of about 0.045.
        # It stopped being tolerable when SCORED_YEARS was promoted from 4 folds
        # to 11 by owner decision: the deltas fell to +0.0113 hit and +0.0108
        # pit, roughly a quarter of the floor, and a bare `>` would have gone on
        # printing a star next to a difference the eval cannot resolve.
        #
        # A claim the evidence cannot support is worse than no claim, so the
        # boolean is now gated on resolvability and the numbers behind it travel
        # with it.
        delta = blend - base
        resolvable = abs(delta) >= XFV_VS_CONSENSUS_MDE95
        out["sides"][side] = {
            "n": (pooled.get("blend") or {}).get("n"),
            "consensus_spearman": base,
            "xfv_spearman": blend,
            "delta": round(delta, 5),
            "mde95": XFV_VS_CONSENSUS_MDE95,
            "resolvable": resolvable,
            # True ONLY when the gap is both positive and large enough to be a
            # measurement. The UI keys its star off this.
            "xfv_beats": bool(delta > 0 and resolvable),
            "verdict": ("beats consensus" if (delta > 0 and resolvable)
                        else "loses to consensus" if (delta < 0 and resolvable)
                        else "not resolvable at this power"),
            "era_split": ev.get("era_split_debuted") or {},
        }
    if block is None:
        # The eval artifacts are rebuilt on the pipeline's cadence, so on the run
        # right after the leg lands they do not carry it yet. Computing it live
        # keeps the Methodology surface from waiting a rebuild for its own gate.
        try:
            from efv_model import block_rho_eval
            block = block_rho_eval()
        except Exception as exc:                          # noqa: BLE001
            log.warning("block-rho leg unavailable: %s", exc)
    if block:
        out["block_rho"] = block
    return out if found else None


#: Model-versus-consensus pooled-rho MDE95, from docs/EFV_GATE_STANDARD.md section 1.
#: A delta smaller than this is not a result, whichever way it points.
#:
#: RE-DERIVED 2026-08-07 on the 11-fold pair-weighted basis (the one that ships).
#: The previous 0.045 was measured on the RETIRED 4-fold pool, so it was a floor
#: from a different experiment being applied to today's deltas. Fresh measurement:
#: `python tools/efv_mde_lab.py mde 2000`, paired bootstrap resampling train AND
#: test together with a refit per draw, seed 20260807; ledger data/xfv_mde_floor.json.
#: 0.0440 hit / 0.0436 pit, one-sided 95% (1.645 * sd), published as one number
#: because the two sides agree to 0.0004.
#:
#: THE FLOOR DID NOT FALL. The 2026-08-05 plan estimated ~0.012 on the theory that
#: n 353/438 -> 755/890 would buy power. It does not: the added folds are the thin
#: 2014-2019 cohorts plus the censored 2024 cohort, the bootstrap resamples the
#: TRAIN frame too (so the ridge's own refit variance dominates, and it does not
#: shrink with test n), and pair-weighting the 2024 rows at 0.333 gives back the
#: effective n the extra rows bought. Same lab on the legacy 4-fold pool reproduces
#: 0.0376 hit / 0.0487 pit, which brackets the retired 0.045 and confirms both the
#: method and the one-sided convention that number was on.
XFV_VS_CONSENSUS_MDE95 = 0.044

#: MDE95 for the OTHER gap the site asserts: eFV's OOS grade against the PROSPX
#: consensus on the common resolved set (accuracy.pooled_efv_common). Different
#: statistic, different pool, so it needs its own floor and does not inherit the
#: one above. Measured 2026-08-07, `python tools/efv_mde_lab.py headtohead 2000`,
#: cluster paired bootstrap over the eFV matrix pool with a refit per draw;
#: ledger data/xfv_headtohead_gap.json. One-sided 95%, sd 0.02139.
XFV_HEADTOHEAD_MDE95 = 0.0352

#: MDE95 for the THIRD gap the site asserts, and the one it defends blending with:
#: the PROSPX consensus against its best single input on the pooled common set
#: (accuracy.consensus_vs_inputs). Per metric, because the two legs do not have the
#: same precision and one of them is resolvable while the other is not.
#:
#: Measured 2026-08-09 on the shipped pooled common set (4,284 rows, 1,568 distinct
#: players, base years 2017-2023): cluster bootstrap BY PLAYER, B=2000, seed
#: 20260809, with the max-over-inputs recomputed inside every draw so the argmax is
#: resampled honestly rather than pinned to today's winner. One-sided 95%
#: (1.645 * sd), the same convention as the two floors above.
#:
#:   Spearman  consensus 0.2825  best input 0.2810 (mlb_pipeline)  delta +0.00153
#:             sd 0.007342  CI95 [-0.01291, +0.01558]  MDE95 0.0121
#:   AUC       consensus 0.7334  best input 0.7218 (mlb_pipeline)  delta +0.01158
#:             sd 0.004757  CI95 [+0.00224, +0.02109]  MDE95 0.0078
#:
#: WHAT THIS CHANGES. `consensus_wins` was a bare `cons >= best_input`, so the
#: surface rendered "the blend wins" on BOTH legs. The AUC leg earns it: +0.01158
#: is 1.48x its floor and its CI excludes zero. The Spearman leg does NOT: +0.00153
#: is 0.13x its floor and its CI straddles zero, so the ordering claim was a coin
#: flip printed as a result. The defensible statement is narrower and is the one the
#: measurement supports: BLENDING BUYS DISCRIMINATION, NOT ORDERING. The consensus
#: separates future contributors from non-contributors better than any single input,
#: and it does not order realized WAR better than MLB Pipeline alone.
#:
#: The `>=` also handed the blend an exact tie. A tie is not a win, so the test is
#: now a strict `>` gated on resolvability.
CONSENSUS_VS_INPUTS_MDE95 = {"spearman": 0.0121, "auc": 0.0078}


def _beats(pooled: dict, metric: str, sources: tuple | None = None) -> dict:
    """Does the consensus beat its best individual input on `metric`?

    `pooled` is an accuracy.pooled-shaped {rater: {metric: value}} block. Returns the
    two numbers, the delta, the floor this backtest can resolve, and a three-valued
    verdict. `consensus_wins` is True only when the delta is BOTH positive under a
    strict `>` and larger than CONSENSUS_VS_INPUTS_MDE95[metric]; everything else,
    including an exact tie and any lead inside the floor, is False.

    `sources` overrides SCORED_SOURCES for counterfactual labs that ask what an extra
    rater would do to this claim (tools/ba_source_class_lab.py). Those labs run on a
    DIFFERENT common set, so the floor below is a lower bound there, not the floor:
    admitting Baseball America cuts the population hard (4,284 -> 295 when measured
    2026-08-07b at 13-club coverage; 4,299 -> 666 after the 30-club backfill of
    2026-08-10, i.e. 15.5% retention against a 75% gate) and the MDE95 grows with
    1/sqrt(n), so a verdict computed on the shrunken pool is more conservative than
    it looks, never less. The live figures are in `source_classification`.
    """
    sources = tuple(sources) if sources else tuple(SCORED_SOURCES)
    vals = {r: (pooled.get(r) or {}).get(metric) for r in sources + (CONSENSUS_KEY,)}
    cons = vals.get(CONSENSUS_KEY)
    best_input = max((vals[r] for r in sources if vals[r] is not None), default=None)
    mde95 = CONSENSUS_VS_INPUTS_MDE95.get(metric)
    if cons is None or best_input is None or mde95 is None:
        return {"consensus": cons, "best_input": best_input, "delta": None,
                "mde95": mde95, "resolvable": False, "consensus_wins": False,
                "verdict": "not measurable"}
    delta = round(cons - best_input, 5)
    resolvable = abs(delta) >= mde95
    return {
        "consensus": cons,
        "best_input": best_input,
        "delta": delta,
        "mde95": mde95,
        "resolvable": bool(resolvable),
        "consensus_wins": bool(delta > 0 and resolvable),
        "verdict": ("the blend wins" if (delta > 0 and resolvable)
                    else "the best input wins" if (delta < 0 and resolvable)
                    else "not resolvable at this power"),
    }


def _xfv_vs_consensus_detail(common_rows: list[dict]) -> dict | None:
    """The head-to-head, broken down: eFV vs consensus FV by FV tier, plus the resolved
    'receipts' -- the players the two disagreed on most, and who was closer to the outcome.
    Uses the OUT-OF-SAMPLE eFV grade attached to the common set (so it is a fair contest)."""
    rows = [c for c in common_rows
            if c["grades"].get("xfv") is not None and c["grades"].get(CONSENSUS_KEY) is not None]
    # Dedup to ONE row per player: the LATEST pre-debut read. The pooled common set
    # carries a row per base year, so an early read can show a stale consensus that
    # later caught up (e.g. Francisco Alvarez graded 40 as a young prospect, 63 by
    # graduation). The disagreements table should reflect the grades as they LAST
    # stood before debut, so it surfaces real eFV-vs-consensus gaps, not catch-up.
    latest: dict = {}
    for c in rows:
        k = c.get("key")
        if k is None:
            continue
        # PRE-DEBUT only (audit fix 2026-07-15): the eFV side of this contest
        # is anchored strictly pre-debut (oos_grades at the debut-year
        # decision), so the consensus read must be the same vintage. The old
        # dedup took the latest read of ANY base year - consensus entered the
        # contest with up to 2.5 years of the player's actual MLB results in
        # hand (all 8 receipts were post-debut reads; Deivi Garcia's verdict
        # was literally inverted). A base year EQUAL to the debut year is a
        # preseason read and stays eligible.
        dy = (c.get("outcome") or {}).get("debut_year")
        if dy is not None and (c.get("year") or 0) > dy:
            continue
        if k not in latest or (c.get("year") or 0) > (latest[k].get("year") or 0):
            latest[k] = c
    rows = list(latest.values())
    if len(rows) < 40:
        return None

    per_tier = []
    for lo, hi, label in FV_TIERS:
        tr = [c for c in rows if c["grades"][CONSENSUS_KEY] >= lo
              and (hi is None or c["grades"][CONSENSUS_KEY] < hi)]
        if len(tr) < 25:
            continue
        wars = [c["outcome"]["war"] for c in tr]
        cr = _spearman([c["grades"][CONSENSUS_KEY] for c in tr], wars)
        xr = _spearman([c["grades"]["xfv"] for c in tr], wars)
        per_tier.append({"tier": label, "n": len(tr),
                         "consensus_spearman": round(cr, 4) if cr is not None else None,
                         "xfv_spearman": round(xr, 4) if xr is not None else None})

    # Percentile each rater + the outcome over the common set; disagreement = the gap
    # between eFV's and consensus's percentile placement; "right" = whose placement was
    # closer to the realized-WAR placement. Receipts use resolved (debuted) players.
    def _pct(vals):
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        pr = [0.0] * len(vals)
        for p, i in enumerate(order):
            pr[i] = p / (len(vals) - 1) if len(vals) > 1 else 0.5
        return pr
    cons_pct = _pct([c["grades"][CONSENSUS_KEY] for c in rows])
    xfv_pct = _pct([c["grades"]["xfv"] for c in rows])
    war_pct = _pct([c["outcome"]["war"] for c in rows])
    recs = []
    for i, c in enumerate(rows):
        if not c["outcome"]["debuted"]:
            continue
        recs.append({
            "name": c.get("name") or c["key"], "key": c["key"],
            "consensus_fv": round(c["grades"][CONSENSUS_KEY], 1),
            "war": round(c["outcome"]["war"], 1),
            "dir": "higher" if xfv_pct[i] > cons_pct[i] else "lower",
            "disagree": abs(xfv_pct[i] - cons_pct[i]),
            "xfv_right": abs(xfv_pct[i] - war_pct[i]) < abs(cons_pct[i] - war_pct[i]),
        })
    # A "disagreement" is where eFV and consensus place the player at least 15
    # percentile points apart - a clear grade disagreement. Near-ties (most
    # players, where the two grades agree) are coin-flips that only dilute the
    # signal, so the share-who-was-right is taken over real disagreements, not the
    # whole cohort. On these, eFV is closer on the majority, consistent with its
    # stronger overall ordering. n reported alongside so the share is transparent.
    DISAGREE_GAP = 0.15
    disag = sorted((r for r in recs if r["disagree"] >= DISAGREE_GAP),
                   key=lambda r: -r["disagree"])
    right_share = (round(sum(1 for r in disag if r["xfv_right"]) / len(disag), 3)
                   if disag else None)
    receipts = [{k: r[k] for k in ("name", "consensus_fv", "war", "dir", "xfv_right")}
                for r in disag[:8]]
    return {"n": len(rows), "n_disagreements": len(disag), "per_tier": per_tier,
            "receipts": receipts, "xfv_right_share_on_disagreements": right_share}


# --------------------------------------------------------------------------
# D3 - PAIRWISE HEAD-TO-HEAD, an ADDITIONAL basis (2026-08-12)
# --------------------------------------------------------------------------
# Pre-registered at docs/efv-2026-08-12/SOURCE_SCORING_BASIS_GATE.md.
#
# THE PROBLEM THIS SOLVES. The common set admits a player only when EVERY scored
# rater graded him, so adding a rater does not add a bar to the chart, it
# redefines the population every other bar is computed on. Admitting Baseball
# America costs 93% of the evidence and flips the incumbent ordering, so it
# cannot be admitted. But that cost is a property of insisting on ONE GLOBAL
# POPULATION, not a property of the evidence: BA carries 750 resolvable rows and
# overlaps FanGraphs on 700 and Pipeline on 696, none of which need to come out
# of the 4,402 the incumbents share.
#
# So a pair is scored on the rows THAT PAIR shares. Nothing is removed from
# anyone else's comparison, and a rater with a short history is measurable the
# day it has enough overlap rather than the day it covers everything.
#
# THIS IS ADDITIVE AND CHANGES NO PUBLISHED VERDICT. SCORED_SOURCES is
# untouched, consensus_wins is untouched, the pooled bars are untouched. A cell
# here may disagree with a published number; the published number does not move.
#
# TWO CELLS ARE TWO DIFFERENT COMPARISONS. They sit on different rows and often
# on different YEARS, so they must never be combined into one ranking. That is
# not a footnote: it is the cross-basis error this repo fixed on the eFV hero
# banner, where a margin computed on one population was floored against another.
#
# WHICH IS WHY EVERY SHORT-WINDOW PAIR CARRIES A SAME-YEAR BENCHMARK. Restricted
# to 2023 alone FanGraphs leads Pipeline; pooled over 2017-2023 Pipeline leads.
# One year flips it. Without the benchmark a reader cannot tell a rater
# difference from a year difference.
_PAIRWISE_MIN_ROWS = 100
_PAIRWISE_BOOT = 2000
_PAIRWISE_SEED = 20260812


def _pairwise_rows(universe: list[dict], years: list[int]) -> list[dict]:
    """One row per (player, base year): every source's preseason FV plus the
    outcome. Undebuted players carry WAR 0, so busts are IN and the read is not
    survivor-biased."""
    out = []
    for p in universe:
        war = _outcome(p)["war"]
        in_window, _ = _all_source_grades_by_year(p)
        for y, srcs in (in_window or {}).items():
            if y not in years:
                continue
            g = {s: float(fv) for s, fv in (srcs or {}).items() if fv is not None}
            if g:
                out.append({"key": p.get("player_key"), "year": y, "war": war, "g": g})
    return out


def _pairwise_cell(rows: list[dict], a: str, b: str) -> dict | None:
    """a vs b on the rows both graded, with a PLAYER-clustered bootstrap.

    Clustered because a player can appear in several base years, and treating
    those as independent would overstate the evidence."""
    rs = [r for r in rows if a in r["g"] and b in r["g"]]
    if len(rs) < _PAIRWISE_MIN_ROWS:
        return None
    wars = [r["war"] for r in rs]
    ra = _spearman([r["g"][a] for r in rs], wars)
    rb = _spearman([r["g"][b] for r in rs], wars)
    if ra is None or rb is None:
        return None
    by_key: dict[str, list[dict]] = {}
    for r in rs:
        by_key.setdefault(r["key"], []).append(r)
    keys = list(by_key)
    rng = random.Random(_PAIRWISE_SEED)
    diffs = []
    for _ in range(_PAIRWISE_BOOT):
        samp = [x for k in (keys[rng.randrange(len(keys))] for _ in keys)
                for x in by_key[k]]
        w = [x["war"] for x in samp]
        xa = _spearman([x["g"][a] for x in samp], w)
        xb = _spearman([x["g"][b] for x in samp], w)
        if xa is not None and xb is not None:
            diffs.append(xa - xb)
    lo = hi = None
    if diffs:
        diffs.sort()
        lo = round(diffs[int(0.025 * (len(diffs) - 1))], 4)
        hi = round(diffs[int(0.975 * (len(diffs) - 1))], 4)
    resolvable = bool(lo is not None and (lo > 0 or hi < 0))
    ys = sorted({r["year"] for r in rs})
    cell = {
        "a": a, "b": b, "n": len(rs), "n_players": len(by_key), "years": ys,
        "rho_a": round(ra, 4), "rho_b": round(rb, 4),
        "delta_a_minus_b": round(ra - rb, 4),
        "ci95": [lo, hi] if lo is not None else None,
        "resolvable": resolvable,
        "leader": (a if ra > rb else b) if resolvable else None,
        "verdict": ((a if ra > rb else b) + " orders outcomes better on these rows"
                    if resolvable else "not resolvable at this power"),
    }
    # A PAIR SOMEBODY ELSE ALREADY ADJUDICATES DOES NOT GET A SECOND VERDICT
    # HERE, and this is not politeness, it is the whole point of the lane.
    #
    # source_cohort_accuracy owns the source-versus-source question and scores
    # FanGraphs against MLB Pipeline on ITS population, publishing
    # "not resolvable" there. This basis sees 4,299 rows where that one sees
    # 1,520, so the same difference (about -0.03 either way) clears an interval
    # here and does not there. Both readings are correct on their own rows, and
    # a reader handed two verdicts for one pair has been handed a contradiction
    # rather than a measurement.
    #
    # So the incumbent pair keeps its NUMBERS, which is what makes it a
    # regression control (they reproduce accuracy.pooled exactly), and hands its
    # VERDICT back to the artifact that owns it, quoting that artifact so the
    # difference in population is visible instead of implied.
    if {a, b} == set(SCORED_SOURCES):
        cell["role"] = "regression_control"
        cell["defers_verdict_to"] = "data/source_cohort_accuracy.json accuracy.pooled"
        cell["verdict"] = ("no verdict from this basis: the incumbent pair is "
                           "adjudicated by source_cohort_accuracy, which scores it "
                           "on a smaller population. This cell exists to prove the "
                           "machinery reproduces the served pooled numbers.")
        cell["leader"] = None
    return cell


def pairwise_head_to_head(universe: list[dict], years: list[int]) -> dict:
    """Every rater pair scored on the rows that pair shares. Additive."""
    rows = _pairwise_rows(universe, years)
    sources = sorted({s for r in rows for s in r["g"]} - _NON_RATER_SOURCES
                     - {CONSENSUS_KEY})
    cells, benchmarks = [], {}
    for i, a in enumerate(sources):
        for b in sources[i + 1:]:
            c = _pairwise_cell(rows, a, b)
            if not c:
                continue
            # SAME-YEAR BENCHMARK for any pair that does not span the window.
            if len(c["years"]) < len(years):
                sub = [r for r in rows if r["year"] in set(c["years"])]
                bm = _pairwise_cell(sub, SCORED_SOURCES[0], SCORED_SOURCES[1])
                if bm:
                    key = ",".join(str(y) for y in c["years"])
                    benchmarks[key] = bm
                    c["same_year_benchmark"] = key
            cells.append(c)
    return {
        "basis": "pairwise: each pair scored on the rows BOTH raters graded",
        "is_additional_view": True,
        "changes_no_published_verdict": True,
        "min_rows": _PAIRWISE_MIN_ROWS,
        "bootstrap_B": _PAIRWISE_BOOT, "seed": _PAIRWISE_SEED,
        "clustered_by": "player",
        "window_years": years,
        "cells": cells,
        "same_year_benchmarks": benchmarks,
        "read_this": (
            "Two cells are two different comparisons. They sit on different "
            "players and often on different years, so they must never be read "
            "as one ranking. A pair that does not span the whole window carries "
            "a same-year benchmark: the incumbent pair restricted to those same "
            "years, so a rater difference can be told apart from a year "
            "difference. Restricted to 2023 alone FanGraphs leads MLB Pipeline "
            "while pooled over the full window Pipeline leads, which is exactly "
            "how much one year can move."),
        "verdict_ownership": (
            "The incumbent pair (FanGraphs vs MLB Pipeline) carries NO verdict "
            "from this basis. source_cohort_accuracy owns that question and "
            "scores it on a smaller population, so the same difference resolves "
            "here and does not there. Its numbers are kept as a regression "
            "control: they reproduce accuracy.pooled exactly, which is how you "
            "know this basis is computing the same thing on more rows."),
        "why_this_exists": (
            "The common set admits a player only when every scored rater graded "
            "him, so a rater with a short history cannot be added without "
            "redefining the population every other number is computed on. "
            "Scoring a pair on its own overlap measures the newcomer without "
            "removing a row from anyone else."),
    }


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
    # Tallies for the DERIVED source classification (see SOURCE_CLASS_MIN_ROWS).
    # source_year_rows[source][base_year] = graded preseason rows; common_cover
    # [source] = how many of the CURRENT common-set rows that source also graded,
    # i.e. exactly the population that would survive admitting it as a rater.
    source_year_rows: dict[str, dict[int, int]] = {}
    source_year_rank_only: dict[str, dict[int, int]] = {}
    source_year_out_of_window: dict[str, dict[int, int]] = {}
    common_cover: dict[str, int] = {}

    for p in universe:
        out = _outcome(p)
        all_grades, off_window = _all_source_grades_by_year(p)
        for y, srcs in all_grades.items():
            for src, fv in srcs.items():
                tgt = source_year_rows if fv is not None else source_year_rank_only
                tgt.setdefault(src, {})
                tgt[src][y] = tgt[src].get(y, 0) + 1
        for y, srcs in off_window.items():
            for src in srcs:
                source_year_out_of_window.setdefault(src, {})
                source_year_out_of_window[src][y] = \
                    source_year_out_of_window[src].get(y, 0) + 1
        for y in years:
            grades = _rater_grades_for_year(p, y)
            if not grades:
                continue
            for rater, fv in grades.items():
                rows_by_rater[rater].append({"fv": fv, "outcome": out, "year": y,
                                             "key": p.get("player_key")})
            if all(r in grades for r in raters):
                common_by_year[y].append({"key": p.get("player_key"),
                                          "name": p.get("player_name"), "year": y,
                                          "grades": {r: grades[r] for r in raters},
                                          "outcome": out, "archetype": _archetype(p)})
                for src, fv in all_grades.get(y, {}).items():
                    if fv is not None:      # a rank-only row could not act as a rater
                        common_cover[src] = common_cover.get(src, 0) + 1

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
    # eFV (our outcome-grounded model) as a head-to-head rater. Its grade is the
    # OUT-OF-SAMPLE forward-chained score (efv_model.oos_grades) so the comparison is
    # fair: a fitted model would otherwise enjoy an in-sample advantage the raw source
    # grades don't. Attached to every common row that has an eFV grade; sources still
    # define common-set membership, so eFV is reported on the subset it covers.
    try:
        from efv_model import oos_grades
        xfv_oos = {**oos_grades("hit"), **oos_grades("pit")}
    except Exception:
        log.exception("eFV OOS grades unavailable for source comparison — continuing")
        xfv_oos = {}
    n_xfv = 0
    if xfv_oos:
        for y in years:
            for c in common_by_year[y]:
                g = xfv_oos.get(c["key"])
                if g is not None:
                    c["grades"]["xfv"] = g          # raw rank-war score (for now)
                    n_xfv += 1
        # Remap the raw eFV score onto a 20-80 grade via the common-set consensus-FV
        # distribution, so eFV can be tier-binned + read on the familiar scale. Spearman/AUC
        # are rank-based, so this monotone remap leaves the head-to-head numbers unchanged,
        # but it lets eFV join the FV-tier graphs + cohort tables + archetype breakdown.
        rows_x = [c for y in years for c in common_by_year[y] if "xfv" in c["grades"]]
        if rows_x:
            order = sorted(range(len(rows_x)), key=lambda i: rows_x[i]["grades"]["xfv"])
            cons_sorted = sorted(c["grades"][CONSENSUS_KEY] for c in rows_x)
            m = len(rows_x)
            for rank_pos, i in enumerate(order):
                pp = rank_pos / (m - 1) if m > 1 else 0.0
                rows_x[i]["grades"]["xfv"] = round(cons_sorted[min(m - 1, int(round(pp * (m - 1))))], 1)
    disp_raters = raters + (["xfv"] if n_xfv >= 30 else [])

    def _acc(common_rows: list[dict]) -> dict:
        res = {}
        for rater in disp_raters:
            rr = [c for c in common_rows if c["grades"].get(rater) is not None]
            if not rr:
                continue
            fvs = [c["grades"][rater] for c in rr]
            wars = [c["outcome"]["war"] for c in rr]
            contrib = [c["outcome"]["contributor"] for c in rr]
            sp, au = _spearman(fvs, wars), _auc(fvs, contrib)
            res[rater] = {
                "n": len(rr),
                # The protocol behind the number, so the surface marks the
                # in-sample bars off a FIELD and not off a rater name (F3).
                "basis": _rater_basis(rater),
                "spearman": round(sp, 4) if sp is not None else None,
                "auc": round(au, 4) if au is not None else None,
            }
        return res

    pooled_common = [c for y in years for c in common_by_year[y]]
    # eFV cohort-outcomes table: built over the FULL oos-graded pool (debuted + busts),
    # NOT the common resolved set, so its debut rate + tier outcomes sit on the same
    # population basis as the per-source tables above. The common set is ~fully debuted
    # (never-debuted busts are rarely graded by EVERY source), which made the eFV cohort
    # read 100% debut and not comparable to the sources. (The head-to-head Spearman/AUC
    # stay on the common set - those need identical players to be a fair contest.)
    import efv_dataset
    uni_out = {p.get("player_key"): _outcome(p) for p in universe}
    m_cons: dict[str, float] = {}
    m_info: dict[str, tuple] = {}      # key -> (realized war, debuted?) from the eFV matrix
    for _side in ("hit", "pit"):
        try:
            for r in json.loads(efv_dataset.matrix_path(_side).read_text(encoding="utf-8")):
                if r.get("consensus_fv_raw") is None:
                    continue
                k = r["player_key"]
                m_cons[k] = float(r["consensus_fv_raw"])
                war = r.get("target_resolved")
                war = float(war) if war is not None else float(r.get("target_censored") or 0.0)
                m_info[k] = (war, r.get("kind") == "debuted")
        except (OSError, ValueError):
            pass
    # Debuted players take the universe's full outcome (war/yr, pace flags); the
    # never-debuted busts (in the eFV matrix, not the source-comparison universe) take
    # a non-debuted outcome from the matrix war target - so the pool is debuted + busts.
    fullp = []
    for k in xfv_oos:
        if k not in m_cons:
            continue
        if k in uni_out:
            fullp.append((k, xfv_oos[k], m_cons[k], uni_out[k]))
        else:
            war, deb = m_info.get(k, (0.0, False))
            fullp.append((k, xfv_oos[k], m_cons[k],
                          {"debuted": deb, "war": war, "war_per_yr": None,
                           "contributor": war >= CONTRIBUTOR_WAR, "star": war >= STAR_WAR,
                           "regular_pace": False, "allstar_pace": False}))
    capture_curve = None
    if len(fullp) >= 30:
        order = sorted(range(len(fullp)), key=lambda i: fullp[i][1])
        cons_sorted = sorted(x[2] for x in fullp)
        mlen = len(fullp)
        xfv_rows = []
        for rp, i in enumerate(order):
            pp = rp / (mlen - 1) if mlen > 1 else 0.0
            fv = cons_sorted[min(mlen - 1, int(round(pp * (mlen - 1))))]
            xfv_rows.append({"fv": round(fv, 1), "outcome": fullp[i][3]})
        cohorts["xfv"] = {"n": len(xfv_rows),
                          "n_debuted": sum(1 for r in xfv_rows if r["outcome"]["debuted"]),
                          "tiers": _tier_table(xfv_rows)}
        # WAR-capture (lift) curve: the share of the pool's total realized WAR that sits in the
        # top N% of each board. Better ordering concentrates WAR earlier -> a higher curve. eFV
        # vs the consensus it upgrades, over the FULL graded population (incl. the busts eFV
        # correctly buries). A clean discrimination metric; replaces the confounded
        # mean-WAR-by-tier chart (where better ordering paradoxically LOWERS the middle mean).
        _tot = sum(max(0.0, x[3]["war"]) for x in fullp) or 1.0
        _PCTS = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        def _capture(idx):
            ordr = sorted(fullp, key=lambda x: -x[idx]); n = len(ordr)
            cum = [0.0] * (n + 1)
            for i, x in enumerate(ordr, 1):
                cum[i] = cum[i - 1] + max(0.0, x[3]["war"])
            return {"points": [{"pct": p, "captured": round(cum[max(1, int(round(p * n)))] / _tot, 4)} for p in _PCTS],
                    "area": round(sum(cum[1:]) / n / _tot, 4),
                    "top20": round(cum[max(1, int(round(0.2 * n)))] / _tot, 4)}
        capture_curve = {"pool_n": len(fullp), "xfv": _capture(1), "consensus": _capture(2)}
    # HEAD-TO-HEAD BASIS (2026-08-07). `pooled` scores each rater on the rows THAT
    # rater graded, and eFV covers only the subset of the common set its matrix
    # reaches (3,210 of 4,259 on this vintage). Reading eFV's number against a
    # consensus number computed on 1,049 extra rows is not a head-to-head: on this
    # vintage it inflates the gap from +0.033 to +0.067, because the rows eFV cannot
    # reach are rows consensus orders BADLY. `pooled_efv_common` re-scores every
    # rater on the eFV-covered rows only, which is the sole basis a head-to-head
    # claim can rest on. `pooled` is kept because the per-source calibration and
    # coverage story legitimately wants each source's full common cohort.
    efv_common = [c for c in pooled_common if c["grades"].get("xfv") is not None]
    accuracy = {
        "capture_curve": capture_curve,
        "common_n": len(pooled_common),
        "head_to_head_raters": disp_raters,   # includes "xfv" (OOS) for the bars/archetype
        "pooled": _acc(pooled_common),
        "common_n_efv": len(efv_common),
        "pooled_efv_common": _acc(efv_common) if len(efv_common) >= 40 else None,
        "pooled_basis_note": ("pooled = each rater on its own rows (eFV n < the others); "
                              "pooled_efv_common = every rater on the eFV-covered rows, "
                              "which is the identical-rows basis for any head-to-head claim"),
        "per_year": {y: {"common_n": len(common_by_year[y]), **_acc(common_by_year[y])}
                     for y in years if common_by_year[y]},
    }
    # The head-to-head verdict, carrying its own floor. Without this the surface
    # renders a bare inequality, which is the pattern the 2026-08-06 resolvability
    # gate was added to stop one level up.
    _pec = accuracy.get("pooled_efv_common") or {}
    _x, _c = (_pec.get("xfv") or {}), (_pec.get(CONSENSUS_KEY) or {})
    if _x.get("spearman") is not None and _c.get("spearman") is not None:
        _d = round(_x["spearman"] - _c["spearman"], 5)
        _res = abs(_d) >= XFV_HEADTOHEAD_MDE95
        accuracy["head_to_head_verdict"] = {
            "basis": "pooled_efv_common (identical rows)",
            "n": _pec.get("xfv", {}).get("n"),
            "xfv_spearman": _x["spearman"], "consensus_spearman": _c["spearman"],
            "delta": _d, "mde95": XFV_HEADTOHEAD_MDE95, "resolvable": _res,
            "xfv_beats": bool(_d > 0 and _res),
            "verdict": ("beats consensus" if (_d > 0 and _res)
                        else "loses to consensus" if (_d < 0 and _res)
                        else "not resolvable at this power"),
        }
    # Does the consensus beat its best individual input on each metric? Each leg
    # carries its own measured floor (CONSENSUS_VS_INPUTS_MDE95) because the two do
    # not have the same precision: on this vintage the AUC leg clears its floor by
    # 1.48x and the Spearman leg reaches 0.13x of its own, so a bare inequality
    # published a coin flip as a result on the ordering leg.
    accuracy["consensus_vs_inputs"] = {
        "spearman": _beats(accuracy["pooled"], "spearman"),
        "auc": _beats(accuracy["pooled"], "auc"),
        "basis": ("pooled common set, every scored rater on identical rows; cluster "
                  "bootstrap by player B=2000 seed 20260809, MDE95 = 1.645 * sd of the "
                  "consensus-minus-best-input delta with the argmax over inputs "
                  "recomputed inside each draw"),
        "reading": ("Blending buys DISCRIMINATION, not ORDERING. The consensus separates "
                    "future contributors from non-contributors better than any single "
                    "input, and it does not order realized WAR better than MLB Pipeline "
                    "alone: that gap is inside the floor this backtest can resolve."),
    }
    # OBS-1 (L4 bughunt-2, 2026-07-24e measurement fix): score archetypes on ONE row
    # per player (latest pre-debut read), matching _xfv_vs_consensus_detail's dedup.
    # pooled_common counts a stable player once per base YEAR (intl_bat ~2.4x), which
    # flips a close head-to-head AUC cell vs the leakage-clean per-player read - the
    # source of the misleading "intl_bat weak cell" on the scoreboard.
    _arch_latest: dict = {}
    for _c in pooled_common:
        _dy = (_c.get("outcome") or {}).get("debut_year")
        if _dy is not None and (_c.get("year") or 0) > _dy:
            continue
        _k = _c.get("key")
        if _k is None:
            continue
        if _k not in _arch_latest or (_c.get("year") or 0) > (_arch_latest[_k].get("year") or 0):
            _arch_latest[_k] = _c
    accuracy["by_archetype"] = _archetype_accuracy(list(_arch_latest.values()), disp_raters)
    # The eFV-vs-CONSENSUS detail (per-FV-tier + biggest disagreements) runs on the
    # BROADER consensus + eFV pool - every player BOTH graded, not the all-source common
    # set. Only two graders are compared, so also requiring FanGraphs + Pipeline needlessly
    # shrinks (and skews) the sample; the wider pool is more precise. (The 4-source
    # head-to-head bars above keep the common set - all four on identical players.)
    _names = {p.get("player_key"): p.get("player_name") for p in universe}
    cons_xfv_rows = []
    for r in rows_by_rater[CONSENSUS_KEY]:
        g = xfv_oos.get(r["key"])
        if g is not None:
            cons_xfv_rows.append({"key": r["key"], "name": _names.get(r["key"]),
                                  "year": r["year"],
                                  "grades": {CONSENSUS_KEY: r["fv"], "xfv": g},
                                  "outcome": r["outcome"]})
    accuracy["xfv_vs_consensus_detail"] = _xfv_vs_consensus_detail(
        cons_xfv_rows if len(cons_xfv_rows) >= 50 else pooled_common)

    # DERIVED source classification. Replaces a literal list that had gone stale.
    source_classification = classify_sources(
        source_year_rows, source_year_rank_only, source_year_out_of_window,
        common_cover, len(pooled_common), years, as_of.year)
    # Self-correcting tripwire: promotion into SCORED_SOURCES restates every
    # published accuracy number, so it stays a deliberate edit, but the code is
    # now the thing that notices, instead of a string that could not.
    for _sc in source_classification:
        if _sc["scoreable_now"]:
            log.warning(
                "source %s now clears both classification conditions "
                "(%d resolvable rows in %s, common-set retention %.3f) but is not in "
                "SCORED_SOURCES; promoting it restates every published accuracy number, "
                "so review docs/efv-2026-08-07b/BA_SOURCE_CLASS_GATE.md before adding it",
                _sc["source"], _sc["resolvable_rows_best_year"],
                _sc["resolvable_best_base_year"], _sc["common_set_retention"])

    result = {
        "xfv_vs_consensus": _xfv_vs_consensus(data_dir),
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
        # Kept as a list of NAMES because assets/glossary.js renders it with
        # `.join(", ")`, but it is now DERIVED from source_classification below
        # rather than typed in. Every entry's row count, base years and
        # first-scoreable year live in `source_classification`; the flat list is a
        # projection of it, so the two cannot disagree.
        "insufficient_history": [s["source"] for s in source_classification
                                 if not s["scoreable_now"]],
        "source_classification": source_classification,
        "scoreable_now": [s["source"] for s in source_classification if s["scoreable_now"]],
        "source_class_rules": {
            "min_resolvable_rows_in_a_base_year": SOURCE_CLASS_MIN_ROWS,
            "min_common_set_retention": SOURCE_CLASS_MIN_COMMON_RETENTION,
            # THIS NOTE IS PROSE ABOUT A MEASUREMENT, SO IT GOES STALE THE WAY
            # THE THING IT REPLACED DID. The classification above is computed
            # every run; this sentence is not. It was written when Baseball
            # America held about 385 rows a vintage over 13 clubs and quoted
            # "332 resolvable rows, common set 4,284 -> 295, 6.9% retention".
            # A full 30-club backfill on 2026-08-10 moved every one of those
            # numbers (749 resolvable, 4,299 -> 666, 15.5%) and the sentence went
            # on asserting the old ones - the exact failure the block comment at
            # the top of this file describes, reproduced by the fix for it.
            # So the numbers now come from the computed rows, and only the RULE
            # is prose.
            "note": ("A source is scoreable only if it has enough resolvable preseason "
                     "rows AND admitting it would not collapse the common set every "
                     "other source is reported on. Per-source counts, retention and "
                     "the blocking condition are in `source_classification` above and "
                     "are recomputed every run; do not restate them here. "
                     "Pre-registered in docs/efv-2026-08-07b/BA_SOURCE_CLASS_GATE.md."),
        },
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
        # ADDITIVE (D3). Nothing above this line is computed from it.
        "pairwise_head_to_head": pairwise_head_to_head(universe, years),
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


def _cohort_ab_sidecar(data_dir: Path = DATA_DIR) -> dict | None:
    """The cohort-weight A/B block, lifted from data/source_cohort_accuracy.json.

    APPENDED, NOT REFIT. source_cohort_accuracy.py owns the estimator, the arms, the
    permutation control and the shrink sensitivity; this reads the block it wrote and
    stamps where it came from. If the sidecar is missing (a fresh checkout, or a run
    ordered before it) the key is simply absent, which is honest: the global A/B does
    not depend on it and must not fabricate it.
    """
    p = data_dir / "source_cohort_accuracy.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:                      # noqa: BLE001
        log.warning("cohort_ab sidecar unreadable (%s); omitting from the weight eval", exc)
        return None
    ab = d.get("cohort_ab")
    if not isinstance(ab, dict):
        return None
    # Provenance keys go LAST so a future block key cannot shadow them.
    return {**ab,
            "appended_from": "data/source_cohort_accuracy.json",
            "produced_by": d.get("produced_by"),
            "produced_at": d.get("generated_at"),
            "ships_a_weight": d.get("ships_a_weight")}


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
    # SHIP GATE HARDENED 2026-07-25 (docs/EFV_GATE_STANDARD.md). The old rule was a bare
    # "weighted >= equal on both metrics", with no floor - so ANY positive fluctuation shipped.
    # It did: the live weights {fangraphs 0.9363, mlb_pipeline 1.0637} shipped on a pooled
    # Spearman gain of +0.0011, and a forward-chained A/B with a refit-per-draw cluster
    # bootstrap later measured that design at d_rho -0.0012 against an MDE95 of 0.0068 (i.e.
    # unresolvable, inside the permutation null |d| p95 0.0033) with the SECOND metric,
    # debut AUC, NEGATIVE and its CI excluding zero. The structural reason no recombination
    # can help: of the 8 contributing outlets only FanGraphs (2017+) and MLB Pipeline (2011+)
    # have any resolvable outcome history, and their precisions are indistinguishable
    # (residual variance 14.362 vs 14.462, difference CI95 [-0.649, +0.454]).
    # A weight now has to beat equal by more than the gate can resolve, on BOTH metrics.
    _SHIP_MIN_RHO_GAIN = 0.0068   # measured MDE95 of this A/B's pooled-Spearman delta
    _SHIP_MIN_AUC_GAIN = 0.0052   # measured magnitude of the debut-AUC loss it must clear
    _d_rho = ((summary["weighted"]["spearman"] or 0) - (summary["equal"]["spearman"] or 0))
    _d_auc = ((summary["weighted"]["auc"] or 0) - (summary["equal"]["auc"] or 0))
    ship = (summary["weighted"]["spearman"] is not None
            and summary["weighted"]["auc"] is not None
            and _d_rho >= _SHIP_MIN_RHO_GAIN
            and _d_auc >= _SHIP_MIN_AUC_GAIN)
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
            "ship rule (hardened 2026-07-25): weighted must beat equal by more than the gate can RESOLVE on BOTH metrics (d_rho >= 0.0068 = the measured MDE95, d_auc >= 0.0052); anything smaller is inside the noise floor and equal-weight retains",
            "cohort_ab is APPENDED from data/source_cohort_accuracy.json, not refit here: it asks whether a PER-COHORT weight can do what one global weight cannot, and all of its arms are scored against these same two gate constants",
        ],
    }
    # The cohort-weight A/B travels WITH the global A/B it extends (2026-08-09). Both
    # ask the same ship question against the same two constants, and reading the
    # global "ship: false" without the per-cohort arms invites the obvious follow-up
    # ("would a weight per archetype work?") that has already been measured and
    # answered no. Appended verbatim, never recomputed: source_cohort_accuracy.py owns
    # that estimator and refitting it here would create a second number under one name.
    cohort_ab = _cohort_ab_sidecar(data_dir)
    if cohort_ab:
        out["cohort_ab"] = cohort_ab
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
