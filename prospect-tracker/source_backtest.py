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

CLAIM FRAME (V5 primary, V6 receipts). Every floored verdict this module
publishes rests on a POOLED cell scored against a STORED MDE95 constant. That is
the V5 claim frame and it remains THE PRIMARY: the pooled cell, its stored floor
and its verdict string are what the site renders and what a reader may cite. The
V6 instruments under `accuracy.claim_instruments` (floors derived in run by a
player-clustered E_cond bootstrap on the frame being scored, per side; the
best-rater argmax resampled inside every draw with its winner shares; a
within-base-year block-normalized leg; an AUC coverage certificate) are RECEIPTS,
and they stay receipts: the block leg sits beside the pooled cell and is not a
replacement for it, no V6 number overrides a V5 verdict, and any verdict that
WOULD change is named in `claim_instruments.verdict_changes_under_V6` rather
than applied. CLAIM_V6_SIGNED_ON records the DATE the owner signed the V6
registration and labels the artifact with it. It is not the switch: promoting
the V6 floors to primary is a separate registered change, and the constant's own
comment carries the proof of what it does and does not reach.

What this module refuses to claim: that a floor measured on one frame is the
floor for another. Every stored constant here names the experiment that produced
it, and the V6 blocks report how far the frame has moved since.
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
#      (1) THE DAMAGE IS THE YEAR RESTRICTION, NOT BASEBALL AMERICA. This comment
#      attributed the rater-order flip (mlb_pipeline > fangraphs becoming
#      fangraphs > mlb_pipeline) to admitting BA. Decomposed into its two steps,
#      pooled(4,299) -> 2023-only with BA ABSENT(828) -> 2023 AND BA graded
#      him(666), Spearman against realized WAR:
#
#                        pooled   2023 only   2023+BA   YEAR eff   BA eff
#          fangraphs     0.2473      0.2533    0.2450    +0.0060   -0.0083
#          mlb_pipeline  0.2810      0.2137    0.2266    -0.0673   +0.0129
#          consensus     0.2809      0.2375    0.2328    -0.0434   -0.0047
#
#      The order flips at the FIRST step, with BA absent and unscored. Pipeline's
#      year effect is -0.0673 while its BA effect is +0.0129, OPPOSITE IN SIGN
#      and 19% the magnitude; the consensus year effect is 9.2x its BA effect.
#      Admitting BA and restricting to the one year BA covers are two different
#      things and the old wording ran them together. The 2023-only column is the
#      same-year benchmark now published in `pairwise_head_to_head`, so this is
#      checkable rather than asserted.
#
#      Note also that `consensus_vs_inputs` no longer has a Spearman flip to
#      lose: pooled it already reads -0.0001 in the inputs' favour today, which
#      is why the served `consensus_wins` is False on that leg.
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

# The subset of the above that consensus.py PARKS: they carry an FV, but it is a
# placeholder constant rather than an opinion, and it votes only when nothing
# real graded the player (consensus.CONSTANT_ANCHOR_SOURCES). Mirrored here
# rather than imported so this module keeps its no-heavy-import property; the
# mirror is asserted against the source of truth in test_served_population.py.
_CONSTANT_ANCHOR_SOURCES = frozenset({"performance_ingest", "auto_detect"})

#: A "disagreement" is a gap of at least this many percentile points between the
#: eFV and consensus placements. Module scope since 2026-09-06 so the bootstrap
#: floor and the tests name the same constant the cohort was cut with.
DISAGREE_GAP = 0.15

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


# ---------------------------------------------------------------------------
# A-CLAIM-4: THE FRAME IS 100% SURVIVORS, BY CONSTRUCTION.
#
# `_is_vintage_matched` requires `debut_year is not None`. A prospect who never
# reached the majors therefore CANNOT enter the flagship head-to-head frame, not
# because anybody filtered him out but because the frame is keyed on a debut he
# does not have. Every accuracy cell this artifact publishes is measured on 796
# rows that all made it.
#
# That is survivorship, and it is the single most common way a forecasting claim
# flatters itself: the players a grade got most wrong are exactly the ones who
# vanished. data/inactive.json holds 2,346 of them, none carrying a debut date.
#
# This lane scores the same raters on that pool as an ADDITIONAL frame. It is a
# COVERAGE RECEIPT, not a correction: no published cell moves, and the blast
# radius rule in _claim_instruments is what keeps that true.
def _load_bust_universe(data_dir: Path, universe: list[dict]):
    """(kept, exclusions) from inactive.json, with every drop named.

    TWO SCREENS, both of which fire on real rows:

      REAL MLB VALUE. A player carrying career WAR is not a bust however he got
      into this file. Measured: exactly one, Zack Britton at 11.73 over twelve
      seasons. Scoring him as a never-debuted failure would be a straightforward
      lie about a player a reader may well remember.

      IDENTITY COLLISION. A bust whose player_key or MLBAM id already appears in
      the debuted universe is the SAME HUMAN reached by two routes, and counting
      him on both sides would let one player be his own control.
    """
    p = Path(data_dir) / "inactive.json"
    if not p.exists():
        return [], [{"player_key": None, "reason": f"{p} does not exist"}]
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [], [{"player_key": None, "reason": f"unreadable: {exc}"}]
    rows = doc if isinstance(doc, list) else (doc.get("players") or [])

    uni_keys = {u.get("player_key") for u in universe if u.get("player_key")}
    uni_ids = {str(u.get("mlbam_id")) for u in universe if u.get("mlbam_id")}

    kept, excluded = [], []
    for r in rows:
        key = r.get("player_key")
        war = ((r.get("career_war") or {}).get("career_war")) or 0
        if r.get("debut_date"):
            excluded.append({"player_key": key, "reason": "carries a debut date"})
            continue
        if war and float(war) > 0:
            excluded.append({"player_key": key,
                             "reason": f"carries {war} career WAR, so not a bust"})
            continue
        if key in uni_keys:
            excluded.append({"player_key": key,
                             "reason": "player_key already in the debuted universe"})
            continue
        mid = r.get("mlbam_id")
        if mid and str(mid) in uni_ids:
            excluded.append({"player_key": key,
                             "reason": f"mlbam id {mid} already in the debuted "
                                       "universe: the same human by two routes"})
            continue
        kept.append(r)
    return kept, excluded


def _bust_frame(busts: list[dict], years: list[int], raters: list[str],
                xfv_by_key: dict):
    """Rows for the bust-inclusive frame, at each bust's LAST LIST YEAR.

    THE VINTAGE RULE. A bust's grade is scored at the last year anybody still
    ranked him, which is the latest point at which the raters were all still
    making a claim about him. Scoring an earlier year would ask what they thought
    before the evidence arrived; scoring every year would weight a
    long-lingering prospect more heavily than a quick failure.

    The outcome is ZERO WAR, and that is a fact rather than an imputation: the
    screen above removed everybody who accumulated any.
    """
    rows, receipt = [], {"considered": len(busts), "no_points": 0,
                         "not_graded_by_all_raters": 0, "no_efv": 0,
                         "out_of_window_years": 0}
    for b in busts:
        pts = [pt for pt in (b.get("points") or []) if pt.get("snapshot_date")]
        if not pts:
            receipt["no_points"] += 1
            continue
        last_year = int(max(pt["snapshot_date"] for pt in pts)[:4])
        if last_year not in years:
            receipt["out_of_window_years"] += 1
            continue
        grades = _rater_grades_for_year(b, last_year)
        if not all(r in grades for r in raters):
            receipt["not_graded_by_all_raters"] += 1
            continue
        key = b.get("player_key")
        x = xfv_by_key.get(key)
        if x is None:
            receipt["no_efv"] += 1
            continue
        g = {r: grades[r] for r in raters}
        g["xfv"] = x
        rows.append({
            "key": key, "name": b.get("player_name"), "year": last_year,
            "grades": g,
            # NEVER DEBUTED, so the realized outcome is zero and `debuted` is
            # False. This is measured, not imputed: the screen dropped anybody
            # who accumulated WAR.
            "outcome": {"war": 0.0, "debuted": False, "debut_year": None,
                        "contributor": False, "star": False,
                        "war_per_yr": None, "regular_pace": False,
                        "allstar_pace": False},
            "archetype": _archetype(b),
        })
    receipt["kept"] = len(rows)
    return rows, receipt


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
        # PER-SIDE FLOORS, LIFTED (lane A-CLAIM-1, 2026-09-06). XFV_VS_CONSENSUS_MDE95
        # is ONE number applied to BOTH sides. The eval artifacts already carry the
        # per-side floored call for this exact delta under BOTH estimators
        # (`verdict_vs_consensus.blend.spearman_call_E_refit` / `_E_cond`, sourced from
        # data/xfv_power_eval.json partb_floors.cells.pooled_rho.<side>.debuted_km), and
        # this cell was ignoring them in favour of the pooled constant. They are lifted
        # here, not recomputed: efv_model owns that estimator and refitting it in this
        # module would put a second number under one name. The V5 keys above keep the
        # stored constant and their verdict strings; the per-side calls are published
        # beside them until the V6 registration is signed.
        _blend_v = ((ev.get("evals") or {}).get("debuted_km") or {}).get(
            "verdict_vs_consensus", {}).get("blend") or {}
        _side_floors = {
            "call_E_refit": _blend_v.get("spearman_call_E_refit"),
            "call_E_cond": _blend_v.get("spearman_call_E_cond"),
            "both_estimators_agree": _blend_v.get("both_estimators_agree"),
        }
        out["sides"][side] = {
            "n": (pooled.get("blend") or {}).get("n"),
            "consensus_spearman": base,
            "xfv_spearman": blend,
            "delta": round(delta, 5),
            "mde95": XFV_VS_CONSENSUS_MDE95,
            "mde95_estimator": "E_refit",
            "mde95_basis": ("frozen V5 constant, POOLED ACROSS SIDES; the per-side "
                            "floors for this same delta are in floors_per_side"),
            "floors_per_side": {k: v for k, v in _side_floors.items() if v is not None},
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
    # IS THE POOLED CONSTANT STILL THE FLOOR FOR EITHER SIDE? A receipt, not a
    # repair: XFV_VS_CONSENSUS_MDE95 stays the V5 primary until the V6
    # registration is signed, and this block just makes the drift visible instead
    # of leaving it to be rediscovered. A gap larger than the delta being floored
    # means the pooled constant is deciding the verdict on its own.
    _ps = {s: (((c.get("floors_per_side") or {}).get("call_E_refit") or {}).get("mde95"))
           for s, c in out["sides"].items()}
    _gaps = [abs(v - XFV_VS_CONSENSUS_MDE95) for v in _ps.values() if v is not None]
    if _ps:
        out["stored_pooled_floor_audit"] = {
            "stored_pooled_mde95": XFV_VS_CONSENSUS_MDE95,
            "stored_estimator": "E_refit",
            "per_side_mde95_E_refit": _ps,
            "max_abs_gap": (round(max(_gaps), 4) if _gaps else None),
            "any_side_verdict_would_change": any(
                v is not None and c.get("delta") is not None
                and (abs(c["delta"]) >= v) != bool(c.get("resolvable"))
                for s, c in out["sides"].items() for v in [_ps.get(s)]),
            "note": ("one floor is applied to two sides. The per-side floors for this "
                     "same delta are measured on each side's own frame and travel with "
                     "the cell under floors_per_side; this line reports how far the "
                     "pooled constant sits from them and whether that distance decides "
                     "anything."),
        }
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

#: The same gap on the two OTHER frames, measured 2026-08-13 by
#: `python tools/efv_headtohead_frame_lab.py 2000` (artifact
#: data/xfv_headtohead_frame_eval.json, pre-registration
#: docs/efv-2026-08-13/HEADTOHEAD_FRAME_GATE.md). All three frames are scored
#: INSIDE THE SAME DRAWS at the same seed, so these are not a stored constant read
#: against a fresh delta, and the incumbent frame is re-derived there too: it comes
#: back at MDE95 0.0355 against the 0.0352 above, i.e. the constant is not stale.
#:
#: WHY THREE FLOORS EXIST. The frame decides the answer, and each frame hands one
#: of the two graders an information edge:
#:
#:   all base years      delta +0.0313  floor 0.0355  0.881x  not resolvable
#:   pre-debut only      delta +0.0625  floor 0.0372  1.679x  "beats consensus"
#:   base year == debut  delta +0.0040  floor 0.0303  0.131x  not resolvable
#:
#: The first hands the CONSENSUS up to 2.5 years of major league outcome on 550 of
#: 3,234 rows. The second removes exactly those rows, but keeps rows whose base
#: year PRECEDES eFV's decision year, where eFV is the side with extra
#: information, so its margin is earned partly by that asymmetry rather than by
#: better ordering. The third holds vintage fixed on both sides and is the honest
#: contest; it reads a dead tie, at the SMALLEST floor of the three because one row
#: per player removes the duplication that inflates variance under player
#: resampling. The tie is therefore better measured than either alternative, not
#: worse, and "not resolvable" here is not a power excuse.
XFV_HEADTOHEAD_PREDEBUT_MDE95 = 0.0372
XFV_HEADTOHEAD_VINTAGE_MDE95 = 0.0303

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
        # AVERAGE RANKS FOR TIES (A-CLAIM-10, 2026-09-06). This used to assign
        # each element its position in the sorted list, which gives tied values
        # DIFFERENT percentiles decided by nothing but their index. That is not
        # a rounding detail here: consensus FV lives on the 20-80 scale in
        # 5-point steps and a large block of rows sits on the FV 35 constant
        # anchor, so the old code spread one grade across a wide percentile band
        # and manufactured "disagreement" between two players the consensus had
        # graded identically. Ties now share the mean of the positions they
        # occupy, which is the standard convention and the one _rankdata above
        # already uses.
        n = len(vals)
        if n == 1:
            return [0.5]
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 / (n - 1)
            for k in range(i, j + 1):
                pr[order[k]] = avg
            i = j + 1
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
    disag = sorted((r for r in recs if r["disagree"] >= DISAGREE_GAP),
                   key=lambda r: -r["disagree"])
    right_share = (round(sum(1 for r in disag if r["xfv_right"]) / len(disag), 3)
                   if disag else None)
    receipts = [{k: r[k] for k in ("name", "consensus_fv", "war", "dir", "xfv_right")}
                for r in disag[:8]]
    out = {"n": len(rows), "n_disagreements": len(disag), "per_tier": per_tier,
           "receipts": receipts, "xfv_right_share_on_disagreements": right_share}
    out.update(_disagreement_floor(disag))
    return out


#: B and seed for the disagreement-share bootstrap. Fixed so the published
#: interval is reproducible; the seed is this lane's date.
_DISAGREE_BOOT = 2000
_DISAGREE_SEED = 20260906


def _disagreement_floor(disag: list[dict]) -> dict:
    """A confidence interval on "eFV was closer on X% of the disagreements",
    and the verdict that follows from it.

    WHY THIS IS NOT OPTIONAL. That share is rendered in three places, twice in
    bold and once as a headline tile, and it has always been published as a bare
    percentage. On the current cohort it is about 54% on fewer than 300 rows,
    which is close enough to a coin flip that the reader cannot tell whether
    they are being shown a skill or a sample. A percentage without an interval
    invites exactly one reading, and it is the flattering one.

    ONE ROW PER PLAYER, so a plain resample IS the clustered resample: the
    caller deduplicates to the latest pre-debut read before this is reached, and
    a player therefore appears at most once. If that dedup is ever removed, this
    function needs a cluster argument and the interval it returns until then is
    too narrow.

    The null is 0.5 exactly. "Closer" is a two-way comparison decided per row,
    so a model with no skill at picking its spots lands at half by construction.
    """
    n = len(disag)
    base = {
        "disagreement_gap": DISAGREE_GAP,
        "disagreement_null": 0.5,
        "disagreement_bootstrap": {"B": _DISAGREE_BOOT, "seed": _DISAGREE_SEED,
                                   "unit": "player (one row per player)"},
    }
    if n < 30:
        base["xfv_right_share_ci95"] = None
        base["xfv_right_share_resolvable"] = False
        base["xfv_right_share_verdict"] = (
            f"only {n} resolved disagreements; too few to say anything")
        return base
    try:
        import numpy as np
    except Exception:                                          # noqa: BLE001
        base["xfv_right_share_ci95"] = None
        base["xfv_right_share_resolvable"] = None
        base["xfv_right_share_verdict"] = (
            "numpy is unavailable, so no interval was derived; the share must "
            "not be published as a finding without one")
        return base
    wins = np.array([1.0 if r["xfv_right"] else 0.0 for r in disag])
    rng = np.random.default_rng(_DISAGREE_SEED)
    idx = rng.integers(0, n, size=(_DISAGREE_BOOT, n))
    draws = wins[idx].mean(axis=1)
    lo, hi = (float(np.percentile(draws, 2.5)),
              float(np.percentile(draws, 97.5)))
    point = float(wins.mean())
    # A one-sided p against the coin: how often a draw fails to beat the null.
    p_le_half = float((draws <= 0.5).mean())
    resolvable = lo > 0.5
    base.update({
        "xfv_right_share_ci95": [round(lo, 4), round(hi, 4)],
        "xfv_right_share_point": round(point, 4),
        "xfv_right_share_p_le_null": round(p_le_half, 4),
        "xfv_right_share_resolvable": bool(resolvable),
        "xfv_right_share_verdict": (
            f"eFV is closer on {100 * point:.0f}% of the {n} resolved "
            f"disagreements, 95% CI {100 * lo:.0f}% to {100 * hi:.0f}%. "
            + ("The interval clears the 50% coin, so the edge is resolvable at "
               "this sample size."
               if resolvable else
               "The interval CONTAINS 50%, so on this sample the share is not "
               "distinguishable from a coin flip and must not be presented as "
               "an edge.")),
    })
    return base


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


# ---------------------------------------------------------------------------
# A-CLAIM-14: WHEN, IF EVER, DOES EACH PAIR BECOME DECIDABLE?
#
# `classify_sources` above answers this for a source against the COMMON SET. It
# does not answer it for a PAIR, and the pair is what `pairwise_head_to_head`
# actually scores. Those two questions have different answers, and the gap
# between them is where a source sits in limbo: it has enough history to be
# classified as scoreable-someday while sharing too few rows with any particular
# rival for that rival comparison to ever resolve.
#
# THE CONCRETE CASE THIS EXISTS FOR, AND A CORRECTION. The 2026-09-05 plan
# asserted that the ESPN x MLB Pipeline 2026 overlap stood at 11 rows and "can
# never clear the 100-row pairwise minimum". Measured here on 2026-09-06 the
# overlap is 102 rows, so it DOES clear the minimum, and the pair is blocked by
# something else entirely: 2026 is not in CANDIDATE_YEARS, and would not resolve
# until the 2029 run in any case. The plan's number is retracted. Anyone citing
# "11 rows" is citing a figure this ledger contradicts.
#
# The distinction the plan was reaching for is real, though, and five other pairs
# are in exactly that state: MLB Pipeline x TJStats (94), ESPN x TJStats (90) and
# every Just Baseball pair (21 to 26) share too few rows on any vintage, and no
# amount of waiting adds rows to a vintage that is already published.
#
# TWO BLOCKERS, REPORTED SEPARATELY, because they have opposite remedies:
#
#   lag         The vintage exists and is big enough, it just has not resolved
#               yet. Time fixes this, and the ledger says exactly which run year.
#   overlap     The vintage will never carry enough shared rows. Time fixes
#               nothing. The only remedy is a different pair or a pooled window.
#
# And a third, which is neither and is the one that fails silently:
#
#   candidate_years  The vintage has resolved and is big enough, and the
#               hardcoded CANDIDATE_YEARS tuple does not list it. This is a
#               maintenance state, not a fact about the data, so it is named
#               separately rather than folded into "not yet decidable". 2024 is
#               in the tuple and enters at the 2027 run; a vintage that resolves
#               while missing from the tuple would otherwise disappear.
def _candidate_year_ledger(universe: list[dict], years: list[int],
                           as_of_year: int) -> dict:
    """Per-source and per-pair in-window footprints, and the first run year each
    pair could be decided.

    IN-WINDOW AND FV-BEARING, the same two conditions `_pairwise_rows` applies,
    so a pair's overlap here is the same population its cell would be scored on.
    A rank-only appearance is counted separately and never toward overlap: a
    rater that published a board without grades cannot be compared on grades.
    """
    per_source: dict = {}
    rank_only: dict = {}
    keys_by_source_year: dict = {}
    for pl in universe:
        key = pl.get("player_key")
        if key is None:
            continue
        inw, _out = _all_source_grades_by_year(pl)
        for y, by_src in inw.items():
            for src, fv in by_src.items():
                if src in _NON_RATER_SOURCES or src == CONSENSUS_KEY:
                    continue
                if fv is None:
                    rank_only.setdefault(src, {})
                    rank_only[src][y] = rank_only[src].get(y, 0) + 1
                    continue
                per_source.setdefault(src, {})
                per_source[src][y] = per_source[src].get(y, 0) + 1
                keys_by_source_year.setdefault((src, y), set()).add(key)

    sources = sorted(per_source)
    pairs = []
    for i, a in enumerate(sources):
        for b in sources[i + 1:]:
            by_year = {}
            for y in sorted(set(per_source[a]) | set(per_source[b])):
                ka = keys_by_source_year.get((a, y)) or set()
                kb = keys_by_source_year.get((b, y)) or set()
                n = len(ka & kb)
                if n:
                    by_year[y] = n
            if not by_year:
                continue
            resolved_now = {y: n for y, n in by_year.items() if y in years}
            decidable_now = sum(1 for n in resolved_now.values()
                                if n >= _PAIRWISE_MIN_ROWS)
            # THE FIRST RUN YEAR. A vintage is decidable at y + MIN_LAG_YEARS,
            # and only if it is BOTH big enough and listed in CANDIDATE_YEARS.
            first_run, blocked_by_tuple, too_thin = None, [], []
            # The SAME question asked without the tuple constraint. Reported
            # beside the real answer because the two differ for every 2025 and
            # 2026 vintage, and a bare None would read as "never" when the true
            # state is "one line of maintenance away". A reader must be able to
            # tell a data limit from a config limit without opening the code.
            first_run_if_extended = None
            for y, n in sorted(by_year.items()):
                if n < _PAIRWISE_MIN_ROWS:
                    too_thin.append(y)
                    continue
                cand = y + MIN_LAG_YEARS
                if cand > as_of_year and (first_run_if_extended is None
                                          or cand < first_run_if_extended):
                    first_run_if_extended = cand
                if y not in CANDIDATE_YEARS:
                    blocked_by_tuple.append(y)
                    continue
                if cand <= as_of_year:
                    continue                      # already in `years`
                if first_run is None or cand < first_run:
                    first_run = cand
            if decidable_now:
                blocker = None
            elif first_run is not None:
                blocker = "lag"
            elif blocked_by_tuple:
                blocker = "candidate_years"
            else:
                blocker = "overlap"
            pairs.append({
                "a": a, "b": b,
                "overlap_by_base_year": by_year,
                "overlap_best": max(by_year.values()),
                "overlap_best_base_year": max(by_year, key=lambda y: by_year[y]),
                "overlap_total": sum(by_year.values()),
                "resolved_overlap_by_base_year": resolved_now,
                "decidable_vintages_now": decidable_now,
                "decidable_now": bool(decidable_now),
                "first_decidable_run_year": first_run,
                "first_decidable_run_year_if_candidate_years_extended":
                    first_run_if_extended,
                "blocked_by": blocker,
                "base_years_too_thin": too_thin,
                "base_years_blocked_by_candidate_years": blocked_by_tuple,
                "min_rows": _PAIRWISE_MIN_ROWS,
                "never_decidable_on_current_vintages": (
                    blocker == "overlap"),
            })
    pairs.sort(key=lambda c: (not c["decidable_now"], -c["overlap_best"],
                              c["a"], c["b"]))

    newcomers = [
        {"pair": f"{c['a']} x {c['b']}",
         "best_overlap": c["overlap_best"],
         "best_base_year": c["overlap_best_base_year"],
         "blocked_by": c["blocked_by"],
         "first_decidable_run_year": c["first_decidable_run_year"],
         "first_decidable_run_year_if_candidate_years_extended":
             c["first_decidable_run_year_if_candidate_years_extended"]}
        for c in pairs if not c["decidable_now"]]

    return {
        "as_of_run_year": as_of_year,
        "resolvable_base_years": list(years),
        "candidate_years": list(CANDIDATE_YEARS),
        "min_lag_years": MIN_LAG_YEARS,
        "pairwise_min_rows": _PAIRWISE_MIN_ROWS,
        "is_additional_view": True,
        "changes_no_published_verdict": True,
        "per_source_resolved_keys_by_base_year": {
            src: dict(sorted(v.items())) for src, v in sorted(per_source.items())},
        "per_source_rank_only_rows_by_base_year": {
            src: dict(sorted(v.items())) for src, v in sorted(rank_only.items())},
        "pairs": pairs,
        "newcomers_not_yet_decidable": newcomers,
        "next_run_year_that_adds_a_vintage": min(
            [c["first_decidable_run_year"] for c in pairs
             if c["first_decidable_run_year"] is not None] or [None]
        ) if any(c["first_decidable_run_year"] is not None for c in pairs) else None,
        "blocked_by_meaning": {
            "lag": ("the vintage is large enough and has not resolved yet; "
                    "`first_decidable_run_year` says when it does"),
            "overlap": ("no vintage this pair shares reaches the minimum, so "
                        "waiting changes nothing: the overlap is fixed the day "
                        "the boards are published"),
            "candidate_years": ("resolved and large enough, but the base year is "
                                "not in the CANDIDATE_YEARS tuple. A maintenance "
                                "state, not a fact about the data"),
        },
        "resolution_denominator_is_not_visible_here": (
            "these are RESOLVED keys: a published row that never matched a "
            "player identity is absent from the universe this reads and cannot "
            "be counted from it. The unresolved side lives in the ingest layer "
            "and data/identity_collisions.json, not in this artifact, so no "
            "coverage RATE may be derived from the counts above."),
        "why_this_exists": (
            "a source can have enough history to be classified scoreable-someday "
            "while sharing too few rows with a given rival for that comparison "
            "to ever resolve. The source classification cannot see that, because "
            "it asks about the common set rather than about a pair."),
    }


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


# --------------------------------------------------------------------------
# CLAIM INSTRUMENTS (lane A-CLAIM-1, registered by the owner 2026-09-06)
# --------------------------------------------------------------------------
# WHAT THIS IS. Four instruments that decide what the accuracy cells above are
# ALLOWED TO CLAIM, computed on the rows those cells are actually scored on:
#
#   1. FLOORS DERIVED IN RUN. A player-clustered E_cond bootstrap of every
#      published delta, on the frame being scored, per side. It exists because a
#      stored constant is a floor from the experiment that measured it: the
#      head-to-head vintage floor 0.0303 was measured on a frame of 802 rows with
#      delta +0.00396, and the frame it is applied to today is a different size
#      carrying a different delta in a different label epoch. E_refit is reported
#      BESIDE the derived E_cond, never instead of it: the two estimators answer
#      different questions and disagree on live cells (efv_model.E_REFIT /
#      efv_model.E_COND carry that contract in full).
#   2. BEST-RATER RESAMPLING. The comparator in `consensus_vs_inputs` is "the
#      best public rater on this cell", which is an ARGMAX, so the argmax is
#      recomputed inside every draw and the per-draw winner shares are published.
#      The argmax-resampled floor minus the fixed-argmax floor is the winner's
#      curse, stated as a number rather than assumed away. A stable argmax is
#      shown, not assumed.
#   3. A WITHIN-BASE-YEAR BLOCK LEG. Percentile-normalize prediction and outcome
#      INSIDE each base year, then pool, so a year with more rows or a fatter
#      outcome tail cannot buy a rater ordering skill it does not have. That
#      pooling across base years with different exposure is defect F06, and it
#      currently credits the raters. Published BESIDE the pooled cell, never in
#      place of it, and built the same way as efv_model._block_norm so the two
#      legs are comparable.
#   4. AN AUC COVERAGE CERTIFICATE. Which rows each rater actually graded on the
#      AUC frame, with every rater re-scored on the intersection, so a cell
#      cannot be read across a universe one of its raters never saw.
#
# WHAT THIS IS NOT. It is not a re-estimate of any grade, any model, or any
# published rho, and it does not refit anything. Nothing here moves a served
# number: every accuracy value, every `mde95`, every `verdict` string above keeps
# the value and the meaning it had, so no downstream consumer changes behaviour.
#
# WHAT IT REFUSES TO CLAIM. E_cond holds the fit and resamples the scored rows,
# so it CANNOT say whether a rebuild of the model on a resample of this pool
# would land the same way. On every cell measured so far it is the SMALLER of the
# two floors, so a verdict that resolves under E_cond and not under E_refit is a
# narrower claim, not a stronger one, which is why the estimator is stamped into
# the verdict string itself. The block leg refuses to claim it is the better
# basis: it is a second reading of the same rows under a different pooling rule,
# and where the two disagree the disagreement IS the finding.
#
# THE POOLED CELLS REMAIN THE FROZEN V5 PRIMARY, and no constant in this file
# changes that. Every block here is a RECEIPT: computed every run, published
# beside the V5 cell it would replace, and compared against it so a verdict that
# WOULD change is named rather than discovered later. CLAIM_V6_SIGNED_ON below
# dates the owner's registration and labels the artifact; it does not perform the
# substitution, which is a separate registered change.
CLAIM_INSTRUMENTS_VERSION = "V6"
CLAIM_PRIMARY_VERSION = "V5"
CLAIM_REGISTERED_ON = "2026-09-06"
#: The DATE the owner signed the V6 registration, or None while it is unsigned.
#:
#: WHAT IT ACTUALLY DOES, which is less than an earlier comment here claimed. It
#: is copied verbatim into `claim_instruments.signed_on` and it flips the wording
#: of `claim_instruments.status`. That is the whole of its effect. It is a LABEL
#: on the artifact, NOT a switch: no floor, no verdict string and no served cell
#: reads it, so setting it does not substitute the V6 per-side floors for the
#: frozen V5 pooled primary, and nothing the site renders moves.
#:
#: Verified 2026-09-06 by walking this module's own AST: the name has one Store
#: (the line below) and exactly three Loads, all three inside the
#: `_claim_instruments` return dict under the keys "signed_on" and "status"; and
#: a repo-wide grep finds the name in no other file. Making the substitution real
#: is a separate registered change that has to restamp every floored verdict, not
#: a one-line edit here.
CLAIM_V6_SIGNED_ON = None     # unsigned; the pooled V5 cell stays the primary
_CLAIM_BOOT_B = 2000
_CLAIM_SEED = 20260906
_CLAIM_MIN_ROWS = 60          # below this a clustered floor is noise about noise
_CLAIM_MIN_CLUSTERS = 30
_CLAIM_BLOCK_MIN = 8          # a base year smaller than this cannot be percentiled
_Z95 = 1.645                  # one-sided 95%, the convention in docs/EFV_GATE_STANDARD.md

_NP_CACHE: dict = {}
_FLOOR_CACHE: dict = {}


# ---------------------------------------------------------------------------
# A-CLAIM-12: WHAT THE SERVED CONSENSUS IS ACTUALLY MADE OF.
#
# Every head-to-head cell in this artifact compares eFV against "the consensus",
# and a reader reasonably hears that as a blend of published scouting opinion.
# For a large share of the board it is not one. When no rater published an FV,
# the consensus falls back to a constant anchor, and that row then enters every
# pooled comparison as though it carried an opinion.
#
# This is not a hypothetical. The C-6 lane (2026-08-14) found a board-wide eFV
# deflation of -5.13 FV that turned out to be an artifact of exactly this: 59%
# of rows were being differenced against a fabricated constant. On the rows with
# a real published opinion the sign reversed, and eFV read +2.03 ABOVE consensus.
# The number moved by five FV points on nothing but the composition of the
# denominator, so the composition belongs in the artifact next to the cells it
# governs rather than in a lane document nobody opens.
#
# FOUR CATEGORIES, and the split that matters is the first one:
#
#   constant_anchor_only   No rater published an FV. The served consensus rests
#                          on CONSTANT_ANCHOR_SOURCES (performance_ingest,
#                          auto_detect), which consensus.py parks precisely
#                          because they are placeholders rather than opinions:
#                          they vote only when nothing real graded the player.
#   single_source_shrunk   Exactly one rater, and it graded the player once, so
#                          the shrinkage pulled the value toward the FV 35 prior
#                          (shrinkage_weight < 1). Part opinion, part prior.
#   single_source_unshrunk One rater, but repeated across snapshots, so the
#                          source confirmed its own grade and the pull is off.
#   multi_source           Two or more raters published an FV. This is the only
#                          category that is a consensus in the ordinary sense.
#
# Two further categories exist and are reported rather than folded away, because
# folding them into "constant anchor" would overstate a number that is already
# the uncomfortable one:
#
#   rank_implied_only      Ranked but never FV-graded; the value comes from the
#                          rank-to-FV curve. A real opinion, expressed as a rank.
#   no_basis               Neither. Carried for completeness; should be rare.
#
# A COUNT, NOT A CORRECTION. Nothing here reweights, drops or adjusts any cell.
# The pooled numbers above are unchanged. What this adds is the ability to read
# them: a tie on a population that is 38% placeholder is a different claim from
# a tie on published opinion, and until now the artifact did not say which one
# the reader was looking at.
def _population_category(point: dict) -> str:
    """The four-plus-two category for ONE served consensus point.

    Reads the same fields consensus.py wrote, and applies the same source
    partition: CONSTANT_ANCHOR_SOURCES are placeholders, _NON_RATER_SOURCES are
    not raters at all, and a per-source entry with `fv_published` None APPEARED
    without grading (a rank-only row) and must never be counted as an FV.
    """
    real, const = set(), set()
    for src, ps in (point.get("per_source") or {}).items():
        if src.endswith("_statcast_by_age"):
            continue
        if (ps or {}).get("fv_published") is None:
            continue
        if src in _CONSTANT_ANCHOR_SOURCES:
            const.add(src)
        elif src not in _NON_RATER_SOURCES:
            real.add(src)
    if len(real) >= 2:
        return "multi_source"
    if len(real) == 1:
        w = point.get("shrinkage_weight")
        return ("single_source_shrunk" if (w is not None and float(w) < 1.0)
                else "single_source_unshrunk")
    if const:
        return "constant_anchor_only"
    if point.get("rank_implied_fv") is not None:
        return "rank_implied_only"
    return "no_basis"


_POPULATION_ORDER = ("multi_source", "single_source_unshrunk",
                     "single_source_shrunk", "constant_anchor_only",
                     "rank_implied_only", "no_basis")


def _population_tally(cats) -> dict:
    """Counts, shares and the two roll-ups a reader actually reasons with."""
    counts = {k: 0 for k in _POPULATION_ORDER}
    for c in cats:
        counts[c] = counts.get(c, 0) + 1
    n = sum(counts.values())
    share = {k: (round(v / n, 4) if n else None) for k, v in counts.items()}
    opinion = (counts["multi_source"] + counts["single_source_unshrunk"]
               + counts["single_source_shrunk"] + counts["rank_implied_only"])
    return {
        "n": n,
        "counts": counts,
        "share": share,
        # THE ROLL-UPS. `any_published_opinion` is every category where a human
        # rater said something about this player, including a rank. Its
        # complement is every row whose served consensus nobody actually voted
        # on. These two are the numbers the copy sentence is derived from.
        "n_any_published_opinion": opinion,
        "n_no_published_opinion": n - opinion,
        "share_no_published_opinion": (round((n - opinion) / n, 4) if n else None),
        "n_partly_prior": counts["single_source_shrunk"],
    }


def _population_sentence(latest: dict, common: dict) -> str:
    """ONE sentence of accuracy-page copy, DERIVED from the counts above.

    Derived rather than written, on the standing rule that a page must not
    carry a number a human typed: the C-6 lane's -5.13 headline survived for
    weeks because the figure and the population it described were maintained in
    different places. If the composition shifts, this sentence shifts with it.
    """
    def pct(x):
        return "n/a" if x is None else f"{100.0 * x:.0f}%"
    return (
        f"Of the {latest['n']:,} players on the board, "
        f"{pct(latest['share']['multi_source'])} carry an FV from two or more "
        f"raters and {pct(latest['share_no_published_opinion'])} carry none at "
        f"all, so their consensus is a constant anchor rather than an opinion; "
        f"on the {common['n']:,} rows the head-to-head is scored on, the same "
        f"figures are {pct(common['share']['multi_source'])} and "
        f"{pct(common['share_no_published_opinion'])}.")


def _population_reading(latest: dict, common: dict) -> str:
    """What the two views mean together, derived from their own numbers.

    Written as a derivation because the conclusion depends on which way the gap
    falls and the gap is not fixed. If the common set ever stops being the
    better-graded population, this sentence says so instead.
    """
    lat_bad = latest["share_no_published_opinion"] or 0.0
    com_bad = common["share_no_published_opinion"] or 0.0
    if com_bad <= lat_bad:
        return (
            "The accuracy claim is computed on a better-graded population than "
            "the board it describes: "
            f"{100.0 * com_bad:.0f}% of scored rows rest on no published opinion "
            f"against {100.0 * lat_bad:.0f}% of the live board. That is good for "
            "the claim's internal validity and it is a limit on its reach. The "
            "head-to-head says how eFV and the consensus compare on players the "
            "industry actually grades; it does not say how they compare on the "
            "part of the board nobody graded, and that part is not small.")
    return (
        "The scored rows rest on published opinion LESS often than the live "
        f"board does ({100.0 * com_bad:.0f}% against {100.0 * lat_bad:.0f}%), "
        "which inverts the usual direction and means the head-to-head is "
        "running on a worse-graded population than the product. Treat every "
        "cell above as a lower bound until this is explained.")


def _served_population(universe: list[dict], common_rows: list[dict]) -> dict:
    """The four-category population block, at the latest point and on the
    common set, with the derived copy sentence.

    THE TWO VIEWS ANSWER DIFFERENT QUESTIONS and must not be conflated. The
    latest-point view describes THE BOARD A READER IS LOOKING AT NOW. The
    common-set view describes THE ROWS THE ACCURACY CLAIM IS COMPUTED ON, which
    is a much narrower and much better-graded population: a row only reaches the
    common set if every scored rater graded it, which by construction excludes
    most constant-anchor rows. The gap between the two views is the point.
    """
    latest_cats = []
    by_key: dict = {}
    for p in universe:
        pts = [x for x in (p.get("points") or []) if x.get("snapshot_date")]
        if not pts:
            continue
        by_key[p.get("player_key")] = pts
        latest_cats.append(_population_category(
            max(pts, key=lambda x: x["snapshot_date"])))

    # THE COMMON SET, classified at the point the claim is scored on, not today.
    # Same preseason window as _rater_grades_for_year, and the LAST in-window
    # point of that base year, because that is the read the year's grade came
    # from once the window's max was taken.
    common_cats, unresolved = [], 0
    for c in common_rows:
        pts = by_key.get(c.get("key"))
        y = c.get("year")
        if not pts or y is None:
            unresolved += 1
            continue
        lo, hi = f"{y}{_WINDOW_START_MMDD}", f"{y}{_WINDOW_END_MMDD}"
        inw = [x for x in pts if lo <= str(x["snapshot_date"]) < hi]
        if not inw:
            unresolved += 1
            continue
        common_cats.append(_population_category(
            max(inw, key=lambda x: x["snapshot_date"])))

    latest = _population_tally(latest_cats)
    common = _population_tally(common_cats)
    common["rows_not_resolvable_to_a_point"] = unresolved
    return {
        "latest_point": latest,
        "common_set": common,
        "sentence": _population_sentence(latest, common),
        # THE READING, derived, because the two views came out far apart and a
        # bare pair of tables invites the wrong conclusion in either direction.
        "reading": _population_reading(latest, common),
        "categories": {
            "multi_source": "two or more raters published an FV",
            "single_source_unshrunk": ("one rater, but it graded the player more "
                                       "than once, so the single-source pull is off"),
            "single_source_shrunk": ("one rater, graded once, so the value is pulled "
                                     "toward the FV 35 prior: part opinion, part prior"),
            "constant_anchor_only": ("no rater published an FV; the served consensus "
                                     "rests on a placeholder constant"),
            "rank_implied_only": ("ranked but never FV-graded; the value comes from "
                                  "the rank-to-FV curve"),
            "no_basis": "neither an FV nor a rank",
        },
        "changes_no_published_number": True,
        "what_this_is_not": (
            "not a correction and not a reweighting. Every pooled cell in this "
            "artifact is computed exactly as before. This block says what those "
            "cells are computed OVER, which is the thing a reader cannot "
            "otherwise recover and which moved a published headline by 5.13 FV "
            "the one time it was measured (C-6, 2026-08-14)."),
        "why_the_two_views_differ": (
            "a row reaches the common set only if every scored rater graded it, "
            "so the common set is filtered toward well-covered players by "
            "construction. The board-wide view is the honest description of the "
            "product; the common-set view is the honest description of the claim."),
    }


def _numpy():
    """numpy or None. Imported lazily and ONLY for the bootstrap: the stats
    helpers above stay dependency-free on purpose, and a machine without numpy
    must still produce the served artifact. Without it the instruments publish
    `status: not derived` rather than a quietly smaller B."""
    if "np" not in _NP_CACHE:
        try:
            import numpy as np
            _NP_CACHE["np"] = np
        except ImportError:
            _NP_CACHE["np"] = None
    return _NP_CACHE["np"]


def _ranks_np(np, a):
    """Average ranks, ties sharing the mean rank: the same convention as
    `_rankdata` above, so a bootstrap draw and the point estimate cannot be
    computed under two different tie rules."""
    n = a.size
    if n == 0:
        return a
    order = np.argsort(a, kind="mergesort")
    sa = a[order]
    obs = np.empty(n, dtype=bool)
    obs[0] = True
    if n > 1:
        np.not_equal(sa[1:], sa[:-1], out=obs[1:])
    dense = obs.cumsum()
    starts = np.concatenate([np.nonzero(obs)[0], np.array([n])])
    avg = 0.5 * (starts[dense - 1] + starts[dense] + 1.0)
    r = np.empty(n, dtype=np.float64)
    r[order] = avg
    return r


def _corr_np(np, a, b):
    a = a - a.mean()
    b = b - b.mean()
    da = float(a.dot(a))
    db = float(b.dot(b))
    if da <= 0 or db <= 0:
        return None
    return float(a.dot(b) / (da * db) ** 0.5)


def _spearman_np(np, x, y_rank):
    """Spearman with the OUTCOME already ranked. The outcome column is shared by
    every leg of a draw, so ranking it once per draw instead of once per rater is
    the difference between a 2000-draw bootstrap that runs and one that does not."""
    return _corr_np(np, _ranks_np(np, x), y_rank)


def _auc_np(np, scores, labels):
    npos = int(labels.sum())
    nneg = int(labels.size - npos)
    if npos == 0 or nneg == 0:
        return None
    r = _ranks_np(np, scores)
    return float((r[labels].sum() - npos * (npos + 1) / 2.0) / (npos * nneg))


def _cluster_layout(np, cluster_ids):
    """(order, starts, lens) for a player-clustered resampler: `order` lists row
    indices grouped by cluster, `starts`/`lens` index into it."""
    ids = np.asarray(cluster_ids)
    order = np.argsort(ids, kind="mergesort")
    s = ids[order]
    mask = np.empty(s.size, dtype=bool)
    mask[0] = True
    if s.size > 1:
        np.not_equal(s[1:], s[:-1], out=mask[1:])
    starts = np.nonzero(mask)[0]
    lens = np.diff(np.concatenate([starts, np.array([s.size])]))
    return order, starts, lens


def _cluster_draw(np, rng, order, starts, lens):
    """One player-clustered resample: draw K clusters with replacement and take
    every row each drawn cluster owns. A player who appears in four base years
    enters or leaves as ONE unit, which is the whole point of clustering: those
    four rows are one man's career, not four independent observations."""
    K = starts.size
    pick = rng.integers(0, K, K)
    cnt = lens[pick]
    total = int(cnt.sum())
    if total == 0:
        return order[:0]
    ends = np.cumsum(cnt)
    offs = ends - cnt
    pos = (np.arange(total) - np.repeat(offs, cnt) + np.repeat(starts[pick], cnt))
    return order[pos]


def _floor_shell(label, n, n_clusters, why):
    return {"label": label, "n": n, "n_clusters": n_clusters,
            "estimator": "E_cond", "derived_in_run": False,
            "status": why, "mde95": None}


def _econd_floor(label, cluster_ids, a, b, target, *, is_auc=False,
                 B=_CLAIM_BOOT_B, seed=_CLAIM_SEED):
    """Player-clustered E_cond bootstrap of stat(a) - stat(b) on the rows given.

    E_cond BY CONSTRUCTION: both grade columns are fixed (produced upstream,
    forward-chained for eFV and published for the sources), so the only thing
    resampled is which players the frame drew. It therefore does NOT carry the
    refit variance an E_refit floor carries, and it is not a substitute for one.
    """
    np = _numpy()
    n = len(cluster_ids)
    n_clusters = len(set(cluster_ids))
    if np is None:
        return _floor_shell(label, n, n_clusters, "not derived: numpy unavailable")
    if n < _CLAIM_MIN_ROWS or n_clusters < _CLAIM_MIN_CLUSTERS:
        return _floor_shell(label, n, n_clusters,
                            f"not derived: frame below the floor gate "
                            f"({_CLAIM_MIN_ROWS} rows / {_CLAIM_MIN_CLUSTERS} clusters)")
    av = np.asarray(a, dtype=np.float64)
    bv = np.asarray(b, dtype=np.float64)
    tv = np.asarray(target, dtype=(bool if is_auc else np.float64))
    ids = {k: i for i, k in enumerate(dict.fromkeys(cluster_ids))}
    order, starts, lens = _cluster_layout(np, [ids[k] for k in cluster_ids])
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(B):
        idx = _cluster_draw(np, rng, order, starts, lens)
        if idx.size < 8:
            continue
        t = tv[idx]
        if is_auc:
            xa, xb = _auc_np(np, av[idx], t), _auc_np(np, bv[idx], t)
        else:
            tr = _ranks_np(np, t)
            xa, xb = _spearman_np(np, av[idx], tr), _spearman_np(np, bv[idx], tr)
        if xa is not None and xb is not None:
            diffs.append(xa - xb)
    if len(diffs) < 50:
        return _floor_shell(label, n, n_clusters, "not derived: too few usable draws")
    if is_auc:
        pa, pb = _auc_np(np, av, tv), _auc_np(np, bv, tv)
    else:
        tr_full = _ranks_np(np, tv)
        pa = _spearman_np(np, av, tr_full)
        pb = _spearman_np(np, bv, tr_full)
    d = np.asarray(diffs, dtype=np.float64)
    sd = float(d.std(ddof=1))
    q = np.quantile(d, [0.025, 0.975])
    return {
        "label": label, "n": n, "n_clusters": n_clusters,
        "estimator": "E_cond", "derived_in_run": True,
        "resampling_unit": "player cluster",
        "statistic": "auc" if is_auc else "spearman",
        "B": B, "B_used": len(diffs), "seed": seed,
        "point_delta": (None if (pa is None or pb is None) else round(pa - pb, 5)),
        "boot_mean_delta": round(float(d.mean()), 5),
        "sd": round(sd, 5),
        "mde95": round(_Z95 * sd, 4),
        "mde95_twosided": round(1.96 * sd, 4),
        "ci95": [round(float(q[0]), 4), round(float(q[1]), 4)],
        "p_gt_0": round(float((d > 0).mean()), 4),
        "convention": "MDE95 = 1.645 * sd(delta), one-sided",
    }


def _econd_best_rater_floor(label, cluster_ids, cons, candidates, target, *,
                            is_auc=False, B=_CLAIM_BOOT_B, seed=_CLAIM_SEED):
    """The `consensus_vs_inputs` floor with the ARGMAX RESAMPLED.

    The published comparator is not a fixed column, it is "whichever public rater
    is best on this cell". That is a maximum over raters, and a maximum is biased
    upward under resampling, so pinning it to today's winner measures an easier
    statistic than the sentence claims. Both floors are computed on the SAME
    draws, which makes their difference the winner's curse itself rather than a
    comparison of two independent bootstraps.

    Also published: how often each rater is the argmax across draws. "The best
    public rater" is a meaningful comparator only if the same rater keeps winning,
    and that is a fact to be shown, not assumed.
    """
    np = _numpy()
    n = len(cluster_ids)
    n_clusters = len(set(cluster_ids))
    names = list(candidates)
    if np is None:
        return _floor_shell(label, n, n_clusters, "not derived: numpy unavailable")
    if n < _CLAIM_MIN_ROWS or n_clusters < _CLAIM_MIN_CLUSTERS or not names:
        return _floor_shell(label, n, n_clusters, "not derived: frame below the floor gate")
    cv = np.asarray(cons, dtype=np.float64)
    mats = {k: np.asarray(v, dtype=np.float64) for k, v in candidates.items()}
    tv = np.asarray(target, dtype=(bool if is_auc else np.float64))
    ids = {k: i for i, k in enumerate(dict.fromkeys(cluster_ids))}
    order, starts, lens = _cluster_layout(np, [ids[k] for k in cluster_ids])

    def _stat(vals, t, tr):
        return _auc_np(np, vals, t) if is_auc else _spearman_np(np, vals, tr)

    tr_full = None if is_auc else _ranks_np(np, tv)
    full = {k: _stat(mats[k], tv, tr_full) for k in names}
    full_cons = _stat(cv, tv, tr_full)
    pinned = max((k for k in names if full[k] is not None),
                 key=lambda k: full[k], default=None)
    if pinned is None or full_cons is None:
        return _floor_shell(label, n, n_clusters,
                            "not derived: statistic undefined on this frame")
    rng = np.random.default_rng(seed)
    d_res, d_pin, wins = [], [], {k: 0 for k in names}
    for _ in range(B):
        idx = _cluster_draw(np, rng, order, starts, lens)
        if idx.size < 8:
            continue
        t = tv[idx]
        tr = None if is_auc else _ranks_np(np, t)
        c = _stat(cv[idx], t, tr)
        vals = {k: _stat(mats[k][idx], t, tr) for k in names}
        ok = [k for k in names if vals[k] is not None]
        if c is None or not ok:
            continue
        w = max(ok, key=lambda k: vals[k])
        wins[w] += 1
        d_res.append(c - vals[w])
        if vals.get(pinned) is not None:
            d_pin.append(c - vals[pinned])
    if len(d_res) < 50 or len(d_pin) < 50:
        return _floor_shell(label, n, n_clusters, "not derived: too few usable draws")
    ar = np.asarray(d_res, dtype=np.float64)
    pn = np.asarray(d_pin, dtype=np.float64)
    sd_a, sd_p = float(ar.std(ddof=1)), float(pn.std(ddof=1))
    tot = sum(wins.values()) or 1
    qa = np.quantile(ar, [0.025, 0.975])
    return {
        "label": label, "n": n, "n_clusters": n_clusters,
        "estimator": "E_cond", "derived_in_run": True,
        "resampling_unit": "player cluster",
        "statistic": "auc" if is_auc else "spearman",
        "B": B, "B_used": len(d_res), "seed": seed,
        "consensus": round(full_cons, 5),
        "per_rater_full_sample": {k: (round(v, 5) if v is not None else None)
                                  for k, v in full.items()},
        "argmax_full_sample": pinned,
        "point_delta_vs_argmax": round(full_cons - full[pinned], 5),
        "argmax_resampled": {
            "sd": round(sd_a, 5), "mde95": round(_Z95 * sd_a, 4),
            "ci95": [round(float(qa[0]), 4), round(float(qa[1]), 4)],
            "p_gt_0": round(float((ar > 0).mean()), 4),
        },
        "argmax_fixed": {"sd": round(sd_p, 5), "mde95": round(_Z95 * sd_p, 4)},
        "winners_curse_mde95": round(_Z95 * (sd_a - sd_p), 5),
        "winners_curse_note": ("argmax-resampled floor minus fixed-argmax floor, on the "
                               "SAME draws. THE CURSE HAS TWO CHANNELS and this is only "
                               "the first: a positive number means pinning the comparator "
                               "to today's winner understates the floor. It can come back "
                               "NEGATIVE, because taking a maximum truncates the "
                               "comparator's downside and so REDUCES the spread of the "
                               "delta; when it does, the curse has moved into the point "
                               "estimate instead, and `mean_argmax_gap` is where to read "
                               "it: a resampled argmax is a stronger comparator than a "
                               "pinned one by that many points on average."),
        "mean_argmax_gap": round(float((ar - pn).mean()), 5),
        "winner_shares": {k: round(wins[k] / tot, 4) for k in names},
        "argmax_stability": round(max(wins.values()) / tot, 4),
    }


def _block_percentile(vals):
    """Percentile position inside one block, average ranks for ties. Same
    construction as efv_model._block_norm, so the two block legs are comparable."""
    r = _rankdata(vals)
    n = len(vals)
    return [(x - 0.5) / n for x in r]


def _within_year_block_leg(rows, raters, *, label=""):
    """Percentile-normalize each rater's grade AND the outcome inside each base
    year, then pool. Published BESIDE the pooled cell, never instead of it.

    THE DEFECT THIS MEASURES (F06). The pooled cell stacks base years with very
    different exposure: a year with more rows contributes more pairs, and a year
    whose cohort realized more WAR contributes a longer outcome scale. Both are
    properties of the YEAR, not of the rater, and the pooled number counts both as
    ordering skill. Block-normalizing removes them and keeps only within-cohort
    ordering.

    Rows are restricted to those EVERY listed rater graded, so the legs sit on
    identical rows; what that restriction costs is reported per year rather than
    absorbed. `columns` travels with the block so a floor can be bootstrapped on
    the same normalized numbers instead of a second normalization of them.
    """
    usable = [c for c in rows if all(c["grades"].get(r) is not None for r in raters)]
    by_year: dict = {}
    for c in usable:
        by_year.setdefault(c.get("year"), []).append(c)
    cols = {r: [] for r in raters}
    tgt, keys, years_used, dropped = [], [], [], {}
    for y in sorted(by_year, key=lambda v: (v is None, v)):
        blk = by_year[y]
        if len(blk) < _CLAIM_BLOCK_MIN:
            dropped[str(y)] = len(blk)
            continue
        years_used.append(y)
        for r in raters:
            cols[r].extend(_block_percentile([c["grades"][r] for c in blk]))
        tgt.extend(_block_percentile([(c["outcome"] or {}).get("war") or 0.0 for c in blk]))
        keys.extend(c.get("key") for c in blk)
    if len(tgt) < _CLAIM_MIN_ROWS:
        return {"label": label, "n": len(tgt), "status": "not computed: frame too small"}
    per_year = {}
    for y in years_used:
        blk = by_year[y]
        wars = [(c["outcome"] or {}).get("war") or 0.0 for c in blk]
        cov = sum(1 for c in blk if c["grades"].get("xfv") is not None)
        per_year[str(y)] = {
            "n": len(blk),
            "n_efv_covered": cov,
            "efv_coverage": round(cov / len(blk), 4),
            "mean_war": round(sum(wars) / len(blk), 3),
            "contributor_rate": round(sum(1 for c in blk
                                          if (c["outcome"] or {}).get("contributor"))
                                      / len(blk), 4),
            "rho": {r: _r4(_spearman([c["grades"][r] for c in blk], wars)) for r in raters},
        }
    return {
        "label": label,
        "basis": "percentile-normalized inside each base year, then pooled",
        "raters": list(raters),
        "n": len(tgt), "n_players": len(set(keys)), "years": years_used,
        "blocks_dropped_below_min": dropped, "block_min_rows": _CLAIM_BLOCK_MIN,
        "block_rho": {r: _r4(_spearman(cols[r], tgt)) for r in raters},
        "per_year": per_year,
        "columns": {"keys": keys, "target": tgt, **cols},
    }


def _auc_coverage_certificate(rows, raters):
    """WHICH ROWS EACH RATER ACTUALLY GRADED on the AUC frame, and what its
    discrimination reads once every rater is put on the same rows.

    The pooled AUC block scores each rater on the rows THAT rater graded. For the
    sources that is the whole common set by construction, but eFV covers only the
    subset its matrix reaches, so an AUC read straight off the pooled block can
    compare two raters across two universes. This certificate makes the universes
    explicit and re-scores every rater on the intersection, so the size of that
    effect is a number instead of a caveat.
    """
    frame_n = len(rows)
    if not frame_n:
        return {"status": "empty frame"}
    graded = {r: [c for c in rows if c["grades"].get(r) is not None] for r in raters}
    inter = [c for c in rows if all(c["grades"].get(r) is not None for r in raters)]
    lab_i = [bool((c["outcome"] or {}).get("contributor")) for c in inter]
    per = {}
    for r in raters:
        g = graded[r]
        lab = [bool((c["outcome"] or {}).get("contributor")) for c in g]
        own = _auc([c["grades"][r] for c in g], lab) if g else None
        on_i = _auc([c["grades"][r] for c in inter], lab_i) if inter else None
        by_year: dict = {}
        for c in g:
            k = str(c.get("year"))
            by_year[k] = by_year.get(k, 0) + 1
        seen = {id(c) for c in g}
        miss = [bool((c["outcome"] or {}).get("contributor")) for c in rows
                if id(c) not in seen]
        per[r] = {
            "n_graded": len(g),
            "coverage_of_frame": round(len(g) / frame_n, 4),
            "n_missing": frame_n - len(g),
            "contributor_rate_own_rows": (round(sum(lab) / len(lab), 4) if lab else None),
            # The rows this rater never saw, scored on their own. When this differs
            # from the rate on its own rows, the rater's universe is not a random
            # sample of the frame and its AUC is not comparable to a rater with a
            # different universe. That is the whole certificate in one number.
            "contributor_rate_missing_rows": (round(sum(miss) / len(miss), 4) if miss else None),
            "auc_own_rows": _r4(own),
            "auc_on_intersection": _r4(on_i),
            "auc_shift_from_universe": (None if (own is None or on_i is None)
                                        else round(on_i - own, 4)),
            "graded_by_base_year": {k: by_year[k] for k in sorted(by_year)},
        }
    overlap = {}
    for i, a in enumerate(raters):
        sa = {(c.get("key"), c.get("year")) for c in graded[a]}
        for b in raters[i + 1:]:
            sb = {(c.get("key"), c.get("year")) for c in graded[b]}
            overlap[f"{a}|{b}"] = len(sa & sb)
    shifts = [abs(per[r]["auc_shift_from_universe"]) for r in raters
              if per[r]["auc_shift_from_universe"] is not None]
    return {
        "frame_n": frame_n,
        "frame_n_players": len({c.get("key") for c in rows}),
        "intersection_n": len(inter),
        "intersection_contributor_rate": (round(sum(lab_i) / len(lab_i), 4) if lab_i else None),
        "every_rater_on_identical_rows": all(per[r]["n_graded"] == frame_n for r in raters),
        "per_rater": per,
        "pairwise_overlap_rows": overlap,
        "max_abs_auc_shift_from_universe": (round(max(shifts), 4) if shifts else None),
        "reading": ("`auc_own_rows` is what the pooled block publishes; "
                    "`auc_on_intersection` is the same rater on the rows every rater "
                    "graded. Where the two differ, an AUC comparison read off the "
                    "pooled block is a comparison across universes, and the size of "
                    "that difference is `auc_shift_from_universe`."),
        "refuses": ("this certificate adjudicates no AUC cell. It states which "
                    "universe each number was computed on, so a reader can refuse a "
                    "cross-universe comparison rather than make one by accident."),
    }


def _power_floor_cell(data_dir, cell):
    """One `partb_floors.cells` entry from data/xfv_power_eval.json, or {}.

    Read rather than imported so this module keeps working when efv_model cannot
    load, and read WITH `n_rows` and `point_delta` (which efv_model.power_floors
    drops) because those are exactly what lets a caller notice that a stored floor
    was measured on a different frame than the one being scored.
    """
    if "cells" not in _FLOOR_CACHE:
        cells, meta = {}, {}
        try:
            doc = json.loads((data_dir / "xfv_power_eval.json").read_text(encoding="utf-8"))
            pb = doc.get("partb_floors") or {}
            cells = pb.get("cells") or {}
            meta = {"generated_at": pb.get("generated_at"), "produced_by": pb.get("produced_by")}
        except (OSError, ValueError) as exc:                       # noqa: BLE001
            log.warning("power floors unreadable (%s); stored E_refit legs omitted", exc)
        _FLOOR_CACHE["cells"] = cells
        _FLOOR_CACHE["meta"] = meta
    c = (_FLOOR_CACHE.get("cells") or {}).get(cell) or {}
    if not c:
        return {}
    return {"cell": cell, "E_refit": c.get("MDE95"), "E_cond": c.get("MDE95_COND"),
            "frame_n": c.get("n_rows"), "frame_n_clusters": c.get("n_clusters"),
            "frame_point_delta": c.get("point_delta"),
            "source": f"data/xfv_power_eval.json partb_floors.cells.{cell}",
            "measured_at": (_FLOOR_CACHE.get("meta") or {}).get("generated_at")}


def _floored_call(delta, mde95, estimator, source, *,
                  win="beats consensus", loss="loses to consensus"):
    """One floored call, with the estimator stamped into the verdict STRING as
    well as into its own field. Same contract as efv_model.floored_verdict,
    reimplemented here so the backtest can floor a cell whether or not efv_model
    imports, and so a missing floor publishes as unfloored instead of borrowing a
    neighbouring cell's number. `win`/`loss` because two cells here difference
    different things and "beats consensus" is wrong wording on the leg where the
    consensus is the one being defended."""
    if delta is None or not mde95:
        return {"delta": delta, "mde95": mde95, "mde95_estimator": estimator,
                "mde95_source": source, "resolvable": False,
                "verdict": "unfloored: no floor derived for this cell"}
    d, f = float(delta), float(mde95)
    res = abs(d) >= f
    call = (win if (d > 0 and res)
            else loss if (d < 0 and res)
            else "not resolvable at this power")
    return {"delta": round(d, 5), "mde95": mde95, "mde95_estimator": estimator,
            "mde95_source": source, "margin_over_floor": round(abs(d) / f, 3),
            "resolvable": bool(res), "verdict": f"{call} ({estimator}, MDE95 {mde95})"}


def _h2h_claim_cell(name, rows, side_of, stored_floor, stored_source, power_cell,
                    data_dir, *, comparator: str = CONSENSUS_KEY):
    """One head-to-head frame under the V6 instruments: an in-run E_cond floor for
    the pooled frame and for EACH SIDE, the stored V5 floor beside it, and an
    explicit statement of whether the verdict would change.

    PER SIDE because hitters and pitchers are two different estimation problems on
    two different label distributions, and the module has been applying one pooled
    constant to both. The per-side E_refit floors that already exist
    (partb_floors.pooled_rho.hit/pit.debuted_km) differ by 5% between the sides, so
    a pooled floor is wrong for at least one of them by construction.
    """
    keys = [c.get("key") for c in rows]
    x = [c["grades"]["xfv"] for c in rows]
    # The COMPARATOR is a parameter so the new frame can be scored against
    # FanGraphs and MLB Pipeline as the plan requires. The default preserves
    # byte-identical behaviour for the three existing frames.
    cn = [c["grades"][comparator] for c in rows]
    war = [(c["outcome"] or {}).get("war") or 0.0 for c in rows]
    pooled = _econd_floor(f"{name}.pooled", keys, x, cn, war)
    by_side = {}
    for side in ("hit", "pit"):
        sub = [i for i, c in enumerate(rows) if side_of.get(c.get("key")) == side]
        if not sub:
            continue
        by_side[side] = _econd_floor(
            f"{name}.{side}", [keys[i] for i in sub], [x[i] for i in sub],
            [cn[i] for i in sub], [war[i] for i in sub])
    delta = pooled.get("point_delta")
    stored = _floored_call(delta, stored_floor, "E_refit", stored_source)
    derived = _floored_call(delta, pooled.get("mde95"), "E_cond",
                            "derived in run: player-clustered bootstrap on this frame")
    pw = _power_floor_cell(data_dir, power_cell) if power_cell else {}
    out = {
        "frame": name,
        "comparator": comparator,
        "n": pooled.get("n"), "n_clusters": pooled.get("n_clusters"),
        "point_delta": delta,
        "floor_E_cond_in_run": pooled,
        "floor_E_cond_by_side": by_side,
        "floor_E_refit_stored": {"mde95": stored_floor, "source": stored_source},
        "call_E_cond_in_run": derived,
        "call_E_refit_stored": stored,
        # The CALL, not the string: every verdict string carries its estimator, so
        # comparing strings would report a change on every cell forever. The two
        # calls differ only if one resolves and the other does not (the delta is
        # the same number in both, so the direction cannot move).
        "verdict_changes_under_E_cond": bool(stored.get("resolvable")
                                             != derived.get("resolvable")),
        "estimators_agree": bool(stored.get("resolvable") == derived.get("resolvable")),
    }
    if pw:
        out["floor_pair_published"] = pw
        out["frame_drift_vs_published_floor"] = {
            "published_frame_n": pw.get("frame_n"),
            "frame_n_now": pooled.get("n"),
            "rows_moved": (None if pw.get("frame_n") is None
                           else (pooled.get("n") or 0) - pw["frame_n"]),
            "published_point_delta": pw.get("frame_point_delta"),
            "point_delta_now": delta,
            "note": ("a floor is a property of the frame it was measured on; these "
                     "two lines are how far the frame has moved since"),
        }
        out["call_E_cond_published"] = _floored_call(
            delta, pw.get("E_cond"), "E_cond", pw.get("source"))
    return out


def _claim_instruments(*, data_dir, pooled_common, frames, side_of, disp_raters,
                       served, bust_rows=None, bust_receipt=None,
                       raw_xfv=None) -> dict:
    """Assemble the four V6 receipts and compare each against the frozen V5 call.

    Every block here is computed on the rows the V5 cell above was computed on, so
    a difference between the two is a difference in the INSTRUMENT and never in
    the population. The one thing this function is allowed to conclude is which
    V5 verdicts would change, and it says so in a list rather than by editing one.
    """
    t0 = _now()
    stored = {
        "vintage_matched": (XFV_HEADTOHEAD_VINTAGE_MDE95,
                            "source_backtest.XFV_HEADTOHEAD_VINTAGE_MDE95 "
                            "(tools/efv_headtohead_frame_lab.py, 2026-08-13)", None),
        "predebut": (XFV_HEADTOHEAD_PREDEBUT_MDE95,
                     "source_backtest.XFV_HEADTOHEAD_PREDEBUT_MDE95 "
                     "(tools/efv_headtohead_frame_lab.py, 2026-08-13)", None),
        "all_vintages": (XFV_HEADTOHEAD_MDE95,
                         "source_backtest.XFV_HEADTOHEAD_MDE95 "
                         "(tools/efv_mde_lab.py headtohead, 2026-08-07)",
                         "headtohead_common"),
    }
    h2h = {}
    for name, rows in frames.items():
        if len(rows) < _CLAIM_MIN_ROWS:
            continue
        # .get, not [], so a frame registered after this dict was written
        # degrades to "no stored V5 floor" instead of raising.
        floor, src, pcell = stored.get(
            name, (None, "no stored V5 floor: this frame was registered after "
                         "the V5 constants were frozen, so only the in-run "
                         "E_cond floor adjudicates it", None))
        h2h[name] = _h2h_claim_cell(name, rows, side_of, floor, src, pcell, data_dir)

    # (a2) A-CLAIM-4, THE BUST-INCLUSIVE FRAME. Scored against EACH scored rater
    # rather than against the consensus, because the plan registers the
    # FanGraphs and Pipeline legs only: the consensus bust cell is the already
    # measured full_pool_km and re-deriving it here would be a second read of a
    # cell that has one.
    bust = {}
    if bust_rows and len(bust_rows) >= _CLAIM_MIN_ROWS:
        # THE FRAME IS THE COMBINED POOL, NOT THE BUSTS ALONE, and the first
        # build got this wrong in a way worth recording. Scored on their own,
        # every bust has the SAME outcome (zero WAR), so a rank correlation
        # against it is undefined and every bootstrap draw comes back NaN. The
        # floor reported "not derived: too few usable draws", which is correct
        # and useless. The question was never "how well does a grade order the
        # failures among themselves"; it is "does the grade still order outcomes
        # once the failures are in the pool", and that needs both halves.
        vintage = frames.get("vintage_matched") or []
        combined = []
        for c in vintage:
            # RAW out-of-sample eFV, not the remapped grade. The common set's
            # xfv values were rewritten IN PLACE onto the consensus-FV
            # distribution, so reading them here would put a remapped number on
            # the debuted half and a raw one on the bust half.
            k = c.get("key")
            raw = raw_xfv.get(k) if raw_xfv else None
            if raw is None:
                continue
            merged = dict(c)
            merged["grades"] = {**c["grades"], "xfv": raw}
            combined.append(merged)
        combined.extend(bust_rows)
        cells = {}
        for comp in SCORED_SOURCES:
            usable = [r for r in combined
                      if r["grades"].get(comp) is not None
                      and r["grades"].get("xfv") is not None]
            if len(usable) < _CLAIM_MIN_ROWS:
                continue
            cells[comp] = _h2h_claim_cell(
                f"bust_inclusive.{comp}", usable, side_of, None,
                "no stored V5 floor: this frame did not exist under V5",
                None, data_dir, comparator=comp)
        bust = {
            "registered_on": CLAIM_REGISTERED_ON,
            "receipt": bust_receipt or {},
            "n_debuted_half": sum(1 for r in combined if (r.get("outcome") or {}).get("debuted")),
            "n_bust_half": len(bust_rows),
            "n_combined": len(combined),
            "cells": cells,
            "why_the_pool_is_combined": (
                "scored on their own every bust has the same outcome, zero WAR, "
                "so a rank correlation against it is undefined and the "
                "bootstrap returns nothing. The question is not how a grade "
                "orders the failures among themselves; it is whether it still "
                "orders outcomes once the failures are in the pool."),
            "both_halves_use_the_same_grade": (
                "raw out-of-sample eFV on BOTH halves. The common set's stored "
                "xfv values were remapped in place onto the consensus-FV "
                "distribution, so using them for the debuted half would compare "
                "a remapped number against a raw one."),
            "why_this_frame_exists": (
                "the flagship head-to-head frame requires a debut year, so a "
                "prospect who never reached the majors CANNOT enter it. Not "
                "because anybody filtered him out, but because the frame is "
                "keyed on a debut he does not have. Every accuracy cell this "
                "artifact publishes is therefore measured on players who all "
                "made it, and the ones a grade got most wrong are exactly the "
                "ones who vanished."),
            "outcome_is_measured_not_imputed": (
                "every row here scores zero WAR because the screen dropped "
                "anybody who accumulated any. Exactly one row was dropped on "
                "that ground and it is a real major-league reliever."),
            "changes_no_published_number": True,
            "blast_radius": (
                "these rows are scored in their own frame and are never added "
                "to the common set. The eFV remap re-derives its grid from "
                "whatever population it is handed, so admitting them would "
                "re-bin the ties for every existing row."),
        }

    # (b) BEST-RATER RESAMPLING on the cell whose comparator is an argmax.
    inputs = [s for s in SCORED_SOURCES
              if all(c["grades"].get(s) is not None for c in pooled_common)]
    keys = [c.get("key") for c in pooled_common]
    cons = [c["grades"][CONSENSUS_KEY] for c in pooled_common]
    war = [(c["outcome"] or {}).get("war") or 0.0 for c in pooled_common]
    contrib = [bool((c["outcome"] or {}).get("contributor")) for c in pooled_common]
    cand = {s: [c["grades"][s] for c in pooled_common] for s in inputs}
    best = {
        "spearman": _econd_best_rater_floor("consensus_vs_inputs.spearman", keys,
                                            cons, cand, war),
        "auc": _econd_best_rater_floor("consensus_vs_inputs.auc", keys, cons, cand,
                                       contrib, is_auc=True),
    }

    # (c) WITHIN-BASE-YEAR BLOCK LEG, beside the pooled cell it does not replace.
    block: dict = {}
    src_leg = _within_year_block_leg(pooled_common, list(inputs) + [CONSENSUS_KEY],
                                     label="consensus_vs_inputs, block-normalized")
    if src_leg.get("columns"):
        col = src_leg.pop("columns")
        src_leg["floor_E_cond_in_run"] = _econd_best_rater_floor(
            "block.consensus_vs_inputs.spearman", col["keys"], col[CONSENSUS_KEY],
            {s: col[s] for s in inputs}, col["target"])
        src_leg["call_E_cond_in_run"] = _floored_call(
            (src_leg["floor_E_cond_in_run"] or {}).get("point_delta_vs_argmax"),
            ((src_leg["floor_E_cond_in_run"] or {}).get("argmax_resampled") or {}).get("mde95"),
            "E_cond", "derived in run on the block-normalized columns, argmax resampled",
            win="the blend wins", loss="the best input wins")
        src_leg["pooled_cell_for_comparison"] = {
            "consensus": (served.get("consensus_vs_inputs") or {}).get("spearman", {}).get("consensus"),
            "best_input": (served.get("consensus_vs_inputs") or {}).get("spearman", {}).get("best_input"),
            "delta": (served.get("consensus_vs_inputs") or {}).get("spearman", {}).get("delta"),
        }
    block["consensus_vs_inputs"] = src_leg
    for name in ("vintage_matched", "all_vintages"):
        rows = frames.get(name) or []
        if len(rows) < _CLAIM_MIN_ROWS:
            continue
        leg = _within_year_block_leg(rows, ["xfv", CONSENSUS_KEY],
                                     label=f"head_to_head {name}, block-normalized")
        if leg.get("columns"):
            col = leg.pop("columns")
            leg["floor_E_cond_in_run"] = _econd_floor(
                f"block.head_to_head.{name}", col["keys"], col["xfv"],
                col[CONSENSUS_KEY], col["target"])
            leg["call_E_cond_in_run"] = _floored_call(
                leg["floor_E_cond_in_run"].get("point_delta"),
                leg["floor_E_cond_in_run"].get("mde95"), "E_cond",
                "derived in run on the block-normalized columns")
            leg["pooled_cell_for_comparison"] = (
                (served.get("head_to_head_by_frame") or {}).get(name))
        block[f"head_to_head.{name}"] = leg

    # (d) AUC COVERAGE CERTIFICATE for the frame the AUC bars are read off, plus a
    # floored same-universe contest for the one pair whose universes differ. The
    # certificate on its own says the comparison is cross-universe; this says by how
    # much and whether the same-universe version is a measurement.
    cert = _auc_coverage_certificate(pooled_common, list(disp_raters))
    if "xfv" in disp_raters:
        inter = [c for c in pooled_common
                 if all(c["grades"].get(r) is not None for r in disp_raters)]
        naive_x = (cert.get("per_rater", {}).get("xfv") or {}).get("auc_own_rows")
        naive_c = (cert.get("per_rater", {}).get(CONSENSUS_KEY) or {}).get("auc_own_rows")
        same_x = (cert.get("per_rater", {}).get("xfv") or {}).get("auc_on_intersection")
        same_c = (cert.get("per_rater", {}).get(CONSENSUS_KEY) or {}).get("auc_on_intersection")
        fl = _econd_floor("auc.intersection.xfv_vs_consensus",
                          [c.get("key") for c in inter],
                          [c["grades"]["xfv"] for c in inter],
                          [c["grades"][CONSENSUS_KEY] for c in inter],
                          [bool((c["outcome"] or {}).get("contributor")) for c in inter],
                          is_auc=True)
        cert["same_universe_contest"] = {
            "pair": ["xfv", CONSENSUS_KEY],
            "delta_cross_universe": (None if (naive_x is None or naive_c is None)
                                     else round(naive_x - naive_c, 4)),
            "delta_same_universe": (None if (same_x is None or same_c is None)
                                    else round(same_x - same_c, 4)),
            "floor_E_cond_in_run": fl,
            "call_E_cond_in_run": _floored_call(
                fl.get("point_delta"), fl.get("mde95"), "E_cond",
                "derived in run on the intersection rows"),
            "note": ("delta_cross_universe is what the pooled AUC bars invite a reader "
                     "to compute: two raters differenced across two different row sets. "
                     "delta_same_universe is the same difference on the rows both "
                     "graded. Only the second one is floored, because only the second "
                     "one is a contest."),
        }

    changes = []
    for name, cell in h2h.items():
        if cell.get("verdict_changes_under_E_cond"):
            changes.append({
                "cell": f"accuracy.head_to_head_by_frame.{name}",
                "V5": (cell.get("call_E_refit_stored") or {}).get("verdict"),
                "V6_E_cond_in_run": (cell.get("call_E_cond_in_run") or {}).get("verdict"),
                "why": ("the stored floor was measured on a different frame; the "
                        "in-run floor is measured on this one"),
            })
    for metric, cell in best.items():
        if not cell.get("derived_in_run"):
            continue
        v5 = (served.get("consensus_vs_inputs") or {}).get(metric) or {}
        v6 = _floored_call(cell.get("point_delta_vs_argmax"),
                           (cell.get("argmax_resampled") or {}).get("mde95"), "E_cond",
                           "derived in run with the argmax resampled",
                           win="the blend wins", loss="the best input wins")
        if bool(v5.get("resolvable")) != bool(v6.get("resolvable")):
            changes.append({
                "cell": f"accuracy.consensus_vs_inputs.{metric}",
                "V5": v5.get("verdict"), "V6_E_cond_in_run": v6.get("verdict"),
                "why": "argmax resampled inside every draw, floor derived on this frame",
            })
        cell["call_E_cond_in_run"] = v6
        cell["call_V5_stored"] = {"mde95": v5.get("mde95"), "verdict": v5.get("verdict"),
                                  "source": "source_backtest.CONSENSUS_VS_INPUTS_MDE95"}
    # DERIVED, NOT ASSERTED: where two instruments computed on the SAME rows point
    # opposite ways. Neither reading is promoted over the other. A pooled cell that
    # is a tie because its two sides cancel, or whose sign flips once the base years
    # are block-normalized, is a cell nobody may quote a direction off, and that is
    # true whether or not either leg clears a floor.
    sign_disagreements = []
    for name, cell in h2h.items():
        pd = cell.get("point_delta")
        sides = {s: f.get("point_delta") for s, f in
                 (cell.get("floor_E_cond_by_side") or {}).items()
                 if f.get("point_delta") is not None}
        if len(sides) == 2 and min(sides.values()) < 0 < max(sides.values()):
            sign_disagreements.append({
                "cell": f"head_to_head.{name}", "kind": "the two sides disagree in sign",
                "pooled_delta": pd, "by_side": sides,
                "note": "the pooled number is an average of two opposite readings"})
        elif len(sides) == 2:
            res = {s: bool((cell.get("floor_E_cond_by_side") or {})[s].get("mde95")
                           and abs(sides[s]) >= (cell["floor_E_cond_by_side"][s]["mde95"]))
                   for s in sides}
            if len(set(res.values())) == 2:
                sign_disagreements.append({
                    "cell": f"head_to_head.{name}",
                    "kind": "one side resolves and the other does not",
                    "pooled_delta": pd, "by_side": sides, "resolvable_by_side": res,
                    "note": "the pooled verdict is carried by one side"})
        bd = ((block.get(f"head_to_head.{name}") or {}).get("floor_E_cond_in_run")
              or {}).get("point_delta")
        if bd is not None and pd is not None and (bd > 0) != (pd > 0):
            sign_disagreements.append({
                "cell": f"head_to_head.{name}",
                "kind": "the pooled cell and the within-year block leg disagree in sign",
                "pooled_delta": pd, "block_delta": bd,
                "note": ("F06: pooling across base years with different exposure is "
                         "what the two legs differ by, and it owns the sign here")})
    return {
        "version": CLAIM_INSTRUMENTS_VERSION,
        "primary_version": CLAIM_PRIMARY_VERSION,
        "registered_on": CLAIM_REGISTERED_ON,
        "signed_on": CLAIM_V6_SIGNED_ON,
        # The status label tracks the SIGNATURE, not a promotion: signing records
        # a date and substitutes nothing (see CLAIM_V6_SIGNED_ON). Saying
        # "PRIMARY" on the signed branch would assert a substitution this module
        # does not perform.
        "status": ("RECEIPT (registration unsigned): the pooled cells above are "
                   "the frozen V5 primary and the per-side floors here are "
                   "published beside them"
                   if not CLAIM_V6_SIGNED_ON else
                   f"RECEIPT (registration signed {CLAIM_V6_SIGNED_ON}): the "
                   "pooled cells above are STILL the frozen V5 primary; the "
                   "signature dates the registration and does not substitute "
                   "these floors for it"),
        "changes_no_published_number": True,
        "bootstrap": {"B": _CLAIM_BOOT_B, "seed": _CLAIM_SEED,
                      "unit": "player cluster", "estimator": "E_cond",
                      "convention": "MDE95 = 1.645 * sd(delta), one-sided",
                      "engine": ("numpy" if _numpy() is not None else "unavailable")},
        "head_to_head_floors": h2h,
        "bust_inclusive": bust,
        "best_rater_resampling": best,
        "within_base_year_block": block,
        "auc_coverage_certificate": cert,
        "verdict_changes_under_V6": changes,
        "sign_disagreements": sign_disagreements,
        "reading": ("E_cond holds the fit and resamples the scored rows; E_refit "
                    "also resamples the training frame and refits, so it is the "
                    "larger floor and the harder bar. Neither is quoted here "
                    "without its estimator, and a cell that resolves under E_cond "
                    "alone has earned the narrower claim, not the stronger one."),
        "elapsed_s": round(_now() - t0, 1),
    }


def _now() -> float:
    import time
    return time.time()


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
    # key -> "hit"/"pit", taken from WHICH MATRIX the row lives in, i.e. the model's
    # own side assignment rather than a second guess off the position string. The
    # per-side claim floors are computed on this map. A player in both matrices
    # (two-way) keeps the first assignment, which is "hit"; there is no such row in
    # today's head-to-head frames and one would be a single row in a 700-row side.
    m_side: dict[str, str] = {}
    for _side in ("hit", "pit"):
        try:
            for r in json.loads(efv_dataset.matrix_path(_side).read_text(encoding="utf-8")):
                m_side.setdefault(r["player_key"], _side)
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
    # M-1 (2026-08-13, docs/efv-2026-08-13/HEADTOHEAD_FRAME_GATE.md). The eFV side
    # of this contest is ONE grade per player, anchored strictly pre-debut
    # (xfv_oos is keyed by player). pooled_common carries a row per base year, so
    # for anyone who debuted inside the window the later rows pair that frozen
    # pre-debut eFV grade against a consensus read taken AFTER the player reached
    # the majors. That hands the BASELINE up to 2.5 years of the outcome.
    #
    # _xfv_vs_consensus_detail has stripped those rows since the 2026-07-15 audit
    # fix (see its comment) and _archetype_accuracy strips them too. The pooled
    # head-to-head basis, which is the one the published claim rests on, never
    # received the same filter. Same convention as both of them: a base year EQUAL
    # to the debut year is a preseason read and stays eligible.
    def _is_predebut(c: dict) -> bool:
        dy = (c.get("outcome") or {}).get("debut_year")
        return dy is None or (c.get("year") or 0) <= dy

    efv_common_predebut = [c for c in efv_common if _is_predebut(c)]
    efv_common_postdebut = [c for c in efv_common if not _is_predebut(c)]

    # THE STRIP ALONE IS NOT A SYMMETRIC FRAME, and the third basis below is why
    # this module publishes three rather than one (measured 2026-08-13,
    # tools/efv_headtohead_frame_lab.py, artifact data/xfv_headtohead_frame_eval.json).
    #
    # eFV holds ONE grade per player, fitted at that player's decision year, which
    # `efv_model._decision_year` sets to the DEBUT year for a debuted player. A
    # common-set row from an EARLIER base year therefore scores eFV's later-vintage
    # grade against a consensus read taken before it, and there eFV is the side
    # holding extra information. Removing post-debut rows removes the reads where
    # the CONSENSUS was advantaged while keeping the ones where eFV is, so the
    # pre-debut basis is tilted toward eFV rather than neutral.
    #
    # Measured, same draws, cluster bootstrap by player, B=2000:
    #   all base years       delta +0.0313  0.881x floor  not resolvable
    #   pre-debut only       delta +0.0625  1.679x floor  "beats consensus"
    #   base year == debut   delta +0.0040  0.131x floor  not resolvable
    # The vintage-matched cell carries the SMALLEST floor of the three (0.0303),
    # because one row per player removes the duplication that inflates the variance
    # under player resampling. So the tie is measured MORE precisely than either
    # other frame and is not a power excuse.
    def _is_vintage_matched(c: dict) -> bool:
        dy = (c.get("outcome") or {}).get("debut_year")
        return dy is not None and (c.get("year") or 0) == dy

    efv_common_vintage = [c for c in efv_common if _is_vintage_matched(c)]
    accuracy = {
        "capture_curve": capture_curve,
        "common_n": len(pooled_common),
        "head_to_head_raters": disp_raters,   # includes "xfv" (OOS) for the bars/archetype
        "pooled": _acc(pooled_common),
        "common_n_efv": len(efv_common),
        "common_n_efv_predebut": len(efv_common_predebut),
        "common_n_efv_vintage_matched": len(efv_common_vintage),
        "pooled_efv_common": _acc(efv_common) if len(efv_common) >= 40 else None,
        "pooled_efv_common_predebut": (_acc(efv_common_predebut)
                                       if len(efv_common_predebut) >= 40 else None),
        # The only frame in which neither side holds a timing edge, and therefore
        # the one the head-to-head verdict is read off.
        "pooled_efv_common_vintage_matched": (_acc(efv_common_vintage)
                                              if len(efv_common_vintage) >= 40 else None),
        # The removed rows, scored on their own. The mechanism above predicts the
        # consensus orders these BETTER than the retained rows, because on them it
        # is reading players it has already seen in the majors. This is the gate's
        # direction control: if it does not hold, the stated mechanism is wrong.
        "pooled_efv_common_postdebut_removed": (_acc(efv_common_postdebut)
                                                if len(efv_common_postdebut) >= 40 else None),
        "pooled_basis_note": ("pooled = each rater on its own rows (eFV n < the others); "
                              "pooled_efv_common_predebut = every rater on the eFV-covered "
                              "rows with post-debut consensus reads removed, which is the "
                              "identical-rows AND identical-vintage basis any head-to-head "
                              "claim has to rest on; pooled_efv_common is the same set "
                              "BEFORE that strip and is kept as the regression control"),
        "per_year": {y: {"common_n": len(common_by_year[y]), **_acc(common_by_year[y])}
                     for y in years if common_by_year[y]},
    }
    # M-1 row accounting. Published rather than left in a doc, because the strip
    # changes the population every head-to-head number is computed on and a reader
    # has to be able to see exactly what left.
    _rm_by_year: dict[int, int] = {}
    for _c in efv_common_postdebut:
        _y = _c.get("year")
        if _y is not None:
            _rm_by_year[_y] = _rm_by_year.get(_y, 0) + 1
    accuracy["head_to_head_frame"] = {
        "basis": "pooled_efv_common_predebut",
        "rule": ("drop rows whose base year is strictly later than the player's "
                 "debut year; a base year equal to the debut year is a preseason "
                 "read and is kept"),
        "rows_before": len(efv_common),
        "rows_after": len(efv_common_predebut),
        "rows_removed": len(efv_common_postdebut),
        "players_before": len({c.get("key") for c in efv_common}),
        "players_after": len({c.get("key") for c in efv_common_predebut}),
        "removed_by_base_year": {str(k): _rm_by_year[k] for k in sorted(_rm_by_year)},
        "multi_vintage_retained": True,
        "note": ("the strip and the one-row-per-player dedup are SEPARATE "
                 "operations with different measured effects; this frame applies "
                 "only the strip, per docs/efv-2026-08-13/HEADTOHEAD_FRAME_GATE.md"),
    }
    # The head-to-head verdict, carrying its own floor. Without this the surface
    # renders a bare inequality, which is the pattern the 2026-08-06 resolvability
    # gate was added to stop one level up.
    #
    # The verdict is read off the VINTAGE-MATCHED basis, which is the only one of
    # the three where neither grader holds a timing edge (see the block above).
    # Every basis is still published, each against its OWN measured floor, so a
    # reader can see that the answer moves with the frame and by how much.
    def _h2h_cell(basis_key: str, rows_block: dict | None, floor: float,
                  basis_note: str) -> dict | None:
        blk = rows_block or {}
        x, c = (blk.get("xfv") or {}), (blk.get(CONSENSUS_KEY) or {})
        if x.get("spearman") is None or c.get("spearman") is None:
            return None
        d = round(x["spearman"] - c["spearman"], 5)
        res = abs(d) >= floor
        return {
            "basis": basis_key,
            "basis_note": basis_note,
            "n": x.get("n"),
            "xfv_spearman": x["spearman"], "consensus_spearman": c["spearman"],
            "delta": d, "mde95": floor, "resolvable": bool(res),
            "margin_x_floor": round(abs(d) / floor, 3) if floor else None,
            "xfv_beats": bool(d > 0 and res),
            "verdict": ("beats consensus" if (d > 0 and res)
                        else "loses to consensus" if (d < 0 and res)
                        else "not resolvable at this power"),
        }

    _frames = {
        "vintage_matched": _h2h_cell(
            "pooled_efv_common_vintage_matched",
            accuracy.get("pooled_efv_common_vintage_matched"),
            XFV_HEADTOHEAD_VINTAGE_MDE95,
            "base year equals the eFV decision year; neither side holds a timing edge"),
        "predebut": _h2h_cell(
            "pooled_efv_common_predebut",
            accuracy.get("pooled_efv_common_predebut"),
            XFV_HEADTOHEAD_PREDEBUT_MDE95,
            "post-debut consensus reads removed, all remaining base years kept; "
            "tilted TOWARD eFV, which is graded at the decision year while the "
            "retained earlier reads are not"),
        "all_vintages": _h2h_cell(
            "pooled_efv_common",
            accuracy.get("pooled_efv_common"),
            XFV_HEADTOHEAD_MDE95,
            "every base year including post-debut consensus reads; tilted TOWARD "
            "the consensus, which sees major league performance on those rows"),
    }
    accuracy["head_to_head_by_frame"] = {k: v for k, v in _frames.items() if v}
    if _frames.get("vintage_matched"):
        accuracy["head_to_head_verdict"] = dict(_frames["vintage_matched"])
        accuracy["head_to_head_verdict"]["frame_note"] = (
            "read off the vintage-matched basis. The other two frames are published "
            "in head_to_head_by_frame and each is tilted toward one of the two "
            "graders; see docs/efv-2026-08-13/HEADTOHEAD_FRAME_GATE.md.")
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
    # ------------------------------------------------------------------
    # CLAIM INSTRUMENTS (V6 receipts). Contract in the block above
    # run_source_backtest. ADDITIVE: nothing here changes a value published
    # anywhere else in this artifact, and the frozen V5 cells above keep their
    # stored floors and their verdict strings no matter what CLAIM_V6_SIGNED_ON
    # holds: that constant labels the artifact and substitutes nothing.
    # ------------------------------------------------------------------
    # A-CLAIM-12. ADDITIVE, same contract as the claim instruments below: a
    # description of the population every cell above is computed over, changing
    # none of them.
    accuracy["served_population"] = _served_population(universe, pooled_common)
    # A-CLAIM-14. Also additive: a forward-looking ledger of which pairs can be
    # decided and when, which no other block in this artifact answers.
    accuracy["candidate_year_ledger"] = _candidate_year_ledger(
        universe, years, as_of.year)
    # A-CLAIM-4. THE BLAST-RADIUS RULE, and it is the one thing here that could
    # silently move a published number. The bust rows are assembled and scored
    # in their OWN frame and are NEVER added to common_by_year, pooled_common,
    # efv_common or efv_common_vintage. The in-place eFV remap above re-derives
    # its grid from whatever population it is handed, so enlarging that
    # population would re-bin the ties for every existing row and move cells
    # this lane is not entitled to touch.
    _busts, _bust_excl = _load_bust_universe(data_dir, universe)
    # THE SAME OUT-OF-SAMPLE OBJECT THE FLAGSHIP FRAME SCORES, not the
    # backgraded value on the served board. `xfv_oos` is the leakage-clean grade
    # `efv_common` is built from, so a bust and a debuted player are compared on
    # the same footing. Reading the served `xfv_grade` instead would put a
    # post-hoc number on one side of the comparison and an out-of-sample one on
    # the other, which is the exact asymmetry this lane exists to remove.
    # Measured 2026-09-06: 1,994 of 2,337 screened busts carry one.
    _xfv_by_key = dict(xfv_oos)
    _bust_rows, _bust_receipt = _bust_frame(
        _busts, years, list(SCORED_SOURCES) + [CONSENSUS_KEY], _xfv_by_key)
    _bust_receipt["read_from_inactive_json"] = len(_busts) + len(_bust_excl)
    _bust_receipt["excluded_by_screen"] = len(_bust_excl)
    _bust_receipt["exclusions"] = _bust_excl[:40]
    accuracy["claim_instruments"] = _claim_instruments(
        data_dir=data_dir,
        pooled_common=pooled_common,
        frames={"vintage_matched": efv_common_vintage,
                "predebut": efv_common_predebut,
                "all_vintages": efv_common},
        side_of=m_side,
        disp_raters=disp_raters,
        served=accuracy,
        bust_rows=_bust_rows,
        bust_receipt=_bust_receipt,
        raw_xfv=_xfv_by_key)
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
    # The summary below prints Greek rho and an en dash. On Windows the console encoding
    # is cp1252, which cannot encode either, so the print raised UnicodeEncodeError and
    # the process exited 1 AFTER data/source_backtest.json had already been written
    # correctly. A non-zero exit on a successful run is worse than a mangled glyph: it
    # fails any caller that checks the return code, and the WAR_BASIS_RUNBOOK step Q does.
    # Reconfigure rather than de-Unicode the strings, so the display stays right wherever
    # the console can take it and degrades to a replacement character where it cannot.
    import sys as _sys
    try:
        _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
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
    ci = r["accuracy"].get("claim_instruments") or {}
    if ci:
        print(f"\n=== CLAIM INSTRUMENTS ({ci['version']}, {ci['status'].split(':')[0]}) ===")
        for name, cell in (ci.get("head_to_head_floors") or {}).items():
            f = cell.get("floor_E_cond_in_run") or {}
            print(f"  {name:>16}  n={cell.get('n')} delta={cell.get('point_delta')}  "
                  f"E_cond(in run)={f.get('mde95')}  E_refit(stored)="
                  f"{(cell.get('floor_E_refit_stored') or {}).get('mde95')}  "
                  f"verdict_changes={cell.get('verdict_changes_under_E_cond')}")
            for side, sf in (cell.get("floor_E_cond_by_side") or {}).items():
                print(f"      {side}: n={sf.get('n')} delta={sf.get('point_delta')} "
                      f"mde95={sf.get('mde95')}")
        for metric, cell in (ci.get("best_rater_resampling") or {}).items():
            if not cell.get("derived_in_run"):
                continue
            print(f"  best-rater {metric}: argmax={cell.get('argmax_full_sample')} "
                  f"stability={cell.get('argmax_stability')} shares={cell.get('winner_shares')} "
                  f"floor_resampled={(cell.get('argmax_resampled') or {}).get('mde95')} "
                  f"floor_fixed={(cell.get('argmax_fixed') or {}).get('mde95')} "
                  f"curse={cell.get('winners_curse_mde95')}")
        for d in (ci.get("sign_disagreements") or []):
            print(f"  SIGN: {d['cell']} - {d['kind']}")
        print(f"  verdict changes under {ci['version']}: "
              f"{len(ci.get('verdict_changes_under_V6') or [])}")
