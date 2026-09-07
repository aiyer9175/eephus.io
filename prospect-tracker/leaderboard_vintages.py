# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""leaderboard_vintages.py - dated snapshots of the team inputs the betting
model consumes, so a game can be priced on numbers that were true BEFORE it.

THE PROBLEM THIS EXISTS TO SOLVE. `betting_model` reads the team leaderboards
(offense_plus, rotation_plus, bullpen_plus, per-pitcher SEM+/REM+) and the park
index. Those are SEASON-TO-DATE aggregates. Grading a June game against them means the features
already contain that June game's result. The forward split in `backtest()`
refits the coefficients on an earlier window, which removes COEFFICIENT
leakage, but the features stay contaminated. That is the single reason
/betting/ ships with `min_edge: null` and no pick of the day.

There is no way to RECOMPUTE what the leaderboards said on 2026-05-14: they are
a full recompute over the season to date and nothing keeps the intermediate
states. So the fix is a CLOCK: start writing down what the inputs say each
night, and wait. A game on date D is then priced on the newest snapshot whose
knowledge cutoff is strictly before D, and nothing that happened on or after D
can reach it.

THE ARCHIVE THAT WAS ALREADY THERE (2026-08-09). The paragraph above was true
about recomputation and wrong about reconstruction. data/*_leaderboards.json is
TRACKED, so every rebuild since 2026-07-05 is a blob in git history, and a blob
committed at time T provably cannot contain information created after T. A
vintage reduced from those blobs and stamped with the GIT COMMIT DATE is
therefore leak-free by construction, on the same argument the nightly clock
runs on. `tools/backfill_vintages.py` does exactly that and wrote 10 vintages
back to 2026-07-05, which moved the honest sample from 41 gradable games to
414 and the first possible grade from 2027 to about 2026-09-16.

The commit date is the cutoff, never the blob's own `as_of`, and that is a rule
of CONSTRUCTION rather than a repair for an observed divergence. `as_of`
describes the data a board was built from and a rebuild may stamp it with
anything; the commit date is a fact about this tree that no rebuild can move
backwards. Measured 2026-08-09 over all 55 board commits in the 2026 history:
0 carry an `as_of` past their own commit date and 2 sit one day behind it
(f3b6338a, 017d3bc2), so the rule costs at most one day of coverage here. The
guarantee does not rest on that measurement, which is the point of taking it
from the commit.

SEASONS DO NOT POOL. `as_of` will not hand a 2027 game a 2026 vintage even
though a September 2026 cutoff is strictly before an April 2027 date. The
leaderboards are a within-season aggregate, so a September vintage and an April
vintage are not measuring the same quantity (docs/diamond-betting.md caveat 1),
and the strictly-before test alone cannot see that. A cross-season request
returns None, the same answer as an empty archive, and the caller treats it as
"no honest features".

Backfilled records carry `provenance.source = "git-backfill"` and are counted
SEPARATELY by `coverage()`, because a reader grading the two arms against each
other is the leakage check that keeps the backfill honest
(docs/diamond-betting.md section 5a).

THE STORE: ONE FILE PER DATE, under .cache/, never in git.

  .cache/leaderboard_vintages/2026-08-05.json      ~24 KB
  .cache/leaderboard_vintages/2026-08-06.json      ~24 KB

Three decisions, each for a reason:

  ONE FILE PER DATE, not a single file keyed by date. A single keyed file is
  rewritten in full every night, so one bad write costs the entire archive.
  Per-date files cost one night. The archive is evidence that cannot be
  regenerated, so the failure mode that loses all of it is the one to design
  out. Measured at 24.4 KB per night compact (30 teams, ~690 pitchers), a
  180-night season is ~4.4 MB. That is small enough that nothing clever is
  needed on top.

  UNDER .cache/, NOT data/. `deploy/nightly-build.sh` runs `git checkout -- .`
  before every pull, which reverts every TRACKED file the pipeline wrote. A
  tracked vintage store would therefore be destroyed each night and would only
  ever hold the most recent run. .cache/ is the box-persistent, gitignored
  state the deploy README already names (alongside prospects.db). The archive
  accumulates there and survives. The cost is that it lives on one box: see
  the runbook in docs/diamond-betting.md for the backup note.

  FIRST WRITE WINS. Re-running on a date that already has a file is a no-op
  that returns the existing record. A snapshot is evidence behind a claim
  about what was knowable; letting a later run overwrite it would let a
  better-informed copy replace a less-informed one, which is exactly the
  leakage this module removes. `force=True` exists for a repair and says so in
  the log.

THE KNOWLEDGE CUTOFF, which is the whole safety property. Each record carries
`covers_through` = max(the source leaderboards' own `as_of` dates, the date
the snapshot was written). A record is eligible to price a game on date D only
when `covers_through < D`. Using the WRITE date in that max is deliberately
conservative: a file written on 2026-08-05 cannot prove it excludes games
played on 2026-08-05, so the earliest game it may price is 2026-08-06. With a
nightly snapshot that costs nothing in steady state (a game on D uses the
snapshot from D-1); without one it is the difference between an honest
backtest and a dishonest one.

WHAT A RECORD HOLDS: the three team columns, the per-pitcher columns, and (from
schema 2) the PARK INDEX. The park was the one model input that was never dated,
and betting_model read the live one for vintage games; see PARK_SOURCE below for
the leak and why no backfill is needed. `parks` is null on schema 1 records and
the reader must price those games on a neutral park, not on today's index.

ORG CODES ARE CANONICALIZED AT WRITE TIME. The leaderboards carry StatsAPI
abbreviations (SD, SF, TB, KC, AZ, CWS, WSH); park factors and the game feeds
carry the Baseball-Reference set (SDP, SFG, TBR, KCR, ARI, CHW, WSN). Every
key in a stored record has already been through `trades.canonical_org`, so a
reader joins directly and cannot silently drop eight clubs.

CLI:
    python leaderboard_vintages.py --snapshot     # write tonight's vintage
    python leaderboard_vintages.py --coverage     # how far from an honest grade
    python leaderboard_vintages.py --as-of 2026-08-07
    python tools/backfill_vintages.py --dry-run   # what git history can rebuild
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("leaderboard_vintages")

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
VINTAGE_DIR = ROOT / ".cache" / "leaderboard_vintages"

# SCHEMA 2 (2026-08-05) added the `parks` block. See PARK_SOURCE below for why:
# schema 1 records carry no park column at all, and a reader must fall back to a
# NEUTRAL park for them rather than to the live index.
#
# SCHEMA 3 (2026-08-16) added the DARK CAPTURE columns, pre-registered in
# docs/diamond-betting.md section 5c BEFORE this bump existed: six team columns
# (xwoba_14, xwoba_30, off_vs_lhp, off_vs_rhp, lineup_strength, star_out) and
# one pitcher column (throws). Nothing served reads any of them; they accrue so
# that a candidate feature can one day be measured on DATED history instead of
# being reconstructed from live season-to-date files, which is the leak this
# store exists to close. The park precedent governs every one of them: an old
# record returns None for a column it predates, a populated record says where
# the value came from, and an unpopulated one says why it is null, in the
# `feature_basis` block. Absent is a stated fact, never a silent zero.
# SCHEMA 4 (2026-09-07) added the availability, rest and weather dark capture,
# pre-registered in docs/diamond-betting.md section 5d BEFORE this bump existed:
# eight team columns (four bullpen availability, two schedule rest, two venue
# weather climatology) and one pitcher column (sp_rest_days). Same governing
# rules as schema 3, which are the park precedent verbatim: an old record
# returns None for a column it predates, a populated record says where the value
# came from, an unpopulated one says why it is null, and absent is never zero.
#
# THE WEATHER COLUMNS ARE CLIMATOLOGY AND NOT OBSERVATIONS, deliberately.
# `gameData.weather` is the weather AT THE GAME, which is not knowable before
# first pitch, so a model priced on it reads the future. What is stored is a
# trailing venue window ending the day BEFORE the vintage date. Section 5d
# states this and states that the observed value stays a contaminated screen
# that can only ever disqualify a candidate.
SCHEMA = 4

# The reduced record keeps only what betting_model actually consumes (plus the
# schema-3 dark capture). Column order is part of the on-disk contract; a
# reader must go through team_row()/pitcher_row() rather than index into the
# arrays by hand.
TEAM_COLUMNS = ("offense_plus", "rotation_plus", "bullpen_plus",
                "starter_ip", "relief_ip",
                "xwoba_14", "xwoba_30", "off_vs_lhp", "off_vs_rhp",
                "lineup_strength", "star_out",
                "pen_b2b_arms", "pen_arms_avail", "pen_ip_l3", "pen_plus_avail",
                "rest_days", "games_in_l7",
                "wx_temp_climo", "wx_wind_out_climo", "catch_frame_rate")
PITCHER_COLUMNS = ("plus", "ip_per_gs", "org", "role", "throws",
                   "sp_rest_days", "sp_tto3_bf")

# The schema-3 additions by name, so a reader can ask "which columns might an
# older record lack" without diffing tuples by hand.
SCHEMA3_TEAM_COLUMNS = ("xwoba_14", "xwoba_30", "off_vs_lhp", "off_vs_rhp",
                        "lineup_strength", "star_out")
SCHEMA3_PITCHER_COLUMNS = ("throws",)

# The schema-4 additions by name, same purpose: a reader asks "which columns
# might an older record lack" without diffing tuples by hand.
SCHEMA4_TEAM_COLUMNS = ("pen_b2b_arms", "pen_arms_avail", "pen_ip_l3",
                        "pen_plus_avail", "rest_days", "games_in_l7",
                        "wx_temp_climo", "wx_wind_out_climo", "catch_frame_rate")
SCHEMA4_PITCHER_COLUMNS = ("sp_rest_days", "sp_tto3_bf")

# The stated basis for each schema-3 column, written into every record's
# `feature_basis` block. These strings are the honesty mechanism: a column that
# is null carries the reason, and a reader never has to guess whether null
# means "the builder failed tonight" or "the builder does not exist".
#
# The four builder-backed columns (2026-08-19) override these strings at
# capture with a DYNAMIC basis carrying that night's facts (anchor commit,
# join counts, cache age). The static strings below are the registry
# description of the populated case; the record's own feature_basis is always
# the authority for what a given night actually stored.
FEATURE_SOURCES = {
    # Schema 4 (2026-09-07). The team columns' bases are DYNAMIC and come from
    # the builder with that night's counts and window, the way the schema-3
    # builder-backed columns do; only sp_rest_days keeps a static string.
    "sp_rest_days": ("days since this pitcher's previous appearance in "
                     ".cache/game_feeds, over a 21-day lookback; null on a "
                     "season debut, which is a stated absence and not a large "
                     "rest number"),
    "off_vs_lhp": ("hitter_leaderboards.json teams[].orders.vl, PA-weighted "
                   "mean of per-slot hem_plus"),
    "off_vs_rhp": ("hitter_leaderboards.json teams[].orders.vr, PA-weighted "
                   "mean of per-slot hem_plus"),
    "xwoba_14": ("rolling-xwOBA builder (build_xwoba_windows, 2026-08-19): "
                 "trailing-14d team xwOBA by cumulative difference, tonight's "
                 "hitter_leaderboards.json hitters[].xwoba*pa minus the newest "
                 "git-committed board on or before D-14; null with the reason "
                 "stated whenever the anchor is absent or too old"),
    "xwoba_30": ("rolling-xwOBA builder (build_xwoba_windows, 2026-08-19): "
                 "same construction over a trailing 30d window"),
    "lineup_strength": ("lineup builder (build_lineup_strength, 2026-08-19): "
                        "mean projected year-1 wOBA (mlb_projections.json "
                        "vets[].woba[0]) over the day's captured order slots, "
                        "vl and vr sides averaged"),
    "star_out": ("availability builder (build_star_out, 2026-08-19): of each "
                 "club's top-5 projected players (mlb_projections.json "
                 "vets[].warY1Champ), how many sit on the IL per the cached "
                 "StatsAPI 40-man roster status codes"),
    "throws": ("pal_export.load_pitch_hand(season), one bulk StatsAPI call at "
               "assembly, never a per-game lookup"),
}

SOURCES = ("hitter_leaderboards.json", "starter_leaderboards.json",
           "bullpen_leaderboards.json")

# THE FOURTH INPUT, and the one that was leaking (2026-08-05).
#
# betting_model prices a game on four things: team offense, team run prevention,
# the listed probable, and THE PARK. The first three were vintage-dated by this
# module from day one; the park was not, so `backtest()` in vintage mode read
# `park_index()` -> data/fa_meta.json -> `fa_fit.park_factors(CLASS_YEAR - 1)`,
# which is the IN-PROGRESS season. Every eval-window game therefore contributed
# to the park index used to fit and to price it, while the mode label claimed
# "features dated strictly before each game; no leakage". One input made that
# false, and the contamination grows with the 600-game validation clock rather
# than shrinking, because a longer eval window is a larger share of the park
# sample it is graded against.
#
# NO BACKFILL IS NEEDED and none is possible. Park factors are near-static
# inside a season (they are a multi-year regressed index the FA engine rebuilds
# monthly, not a daily aggregate), so tonight's value is a fair reading of what
# was knowable last night. Records written before this schema bump simply have
# no park column, and betting_model prices them on a NEUTRAL park and marks the
# games, which is the conservative direction: it drops the park term rather than
# inventing a dated one.
PARK_SOURCE = "fa_meta.json park_factors"
PARK_UNITS = "runs index / 100 (1.00 = neutral), the same units betting_model.park_index returns"

# WHICH CLOCK WROTE A RECORD. "live" is the nightly snapshot off the working
# tree; "git-backfill" is tools/backfill_vintages.py reducing a historical blob.
#
# THE SCHEMA IS DELIBERATELY NOT BUMPED FOR THIS. SCHEMA exists to tell a reader
# it must BRANCH: schema 1 has no `parks`, so a reader that ignores the version
# prices a game on a park term that is not there. `provenance` carries no model
# input at all. A reader that has never heard of it reads the same teams, the
# same pitchers, the same parks and the same covers_through, and prices the game
# identically. Bumping to 3 would also relabel the five records already on disk
# as a version they were not written under, or force a migration to avoid it,
# and would buy nothing either way.
#
# AN ABSENT BLOCK READS AS UNKNOWN, NOT AS LIVE. The five records written before
# provenance shipped really are live, but "no block" and "live" are different
# facts and defaulting one to the other points the ambiguity the wrong way: it
# would file any future recordless writer inside the LIVE arm, which is the one
# arm the leakage check compares against and the one that must stay clean. So
# the five are grandfathered BY DATE below, which is evidence, and everything
# else that arrives without a block is named `unknown` and counted on its own
# line. Measured 2026-08-09: 10 backfilled, 5 live (all five grandfathered),
# 0 unknown, so naming it moves no published number today.
PROVENANCE_LIVE = "live"
PROVENANCE_BACKFILL = "git-backfill"
PROVENANCE_UNKNOWN = "unknown"

# The exact records on disk when the provenance block shipped (2026-08-09).
# Each was written by the nightly `run()` path off the working tree; the list is
# closed and must never grow, because anything written after 2026-08-09 goes
# through a `snapshot()` that always stamps a block.
PROVENANCE_GRANDFATHERED_LIVE = frozenset({
    "2026-08-05", "2026-08-06", "2026-08-07", "2026-08-08", "2026-08-09",
})


# ---------------------------------------------------------------------------
# io helpers
# ---------------------------------------------------------------------------
def _load_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _org(name: str | None) -> str | None:
    """StatsAPI or BBRef team code -> the canonical 3-letter org. See the
    module docstring: mixing the two code sets silently drops eight clubs."""
    if not name:
        return None
    try:
        from trades import canonical_org
        return canonical_org(name)
    except Exception:                                            # pragma: no cover
        return None


def _today() -> str:
    return date.today().isoformat()


def _iso_date(s) -> str | None:
    """Anything date-shaped -> 'YYYY-MM-DD', or None. Tolerates a full ISO
    timestamp, which is what some leaderboard `generated_at` fields carry."""
    if not s:
        return None
    t = str(s).strip()
    if len(t) >= 10 and t[4] == "-" and t[7] == "-":
        head = t[:10]
        try:
            datetime.strptime(head, "%Y-%m-%d")
        except ValueError:
            return None
        return head
    return None


def provenance_source(rec: dict | None) -> str:
    """Which clock wrote this record: LIVE, BACKFILL, or UNKNOWN.

    An absent block is UNKNOWN, never live. The five pre-provenance records are
    live and are named by date in PROVENANCE_GRANDFATHERED_LIVE, which is
    evidence about those five files; silently directing every other absent block
    into the live arm would hide a backfill inside the arm the leakage check
    grades against, which is the one thing the split cannot tolerate."""
    p = (rec or {}).get("provenance")
    if isinstance(p, dict) and p.get("source"):
        return str(p["source"])
    d = _iso_date((rec or {}).get("vintage_date"))
    if d and d in PROVENANCE_GRANDFATHERED_LIVE:
        return PROVENANCE_LIVE
    return PROVENANCE_UNKNOWN


def record_season(rec: dict | None) -> str | None:
    """The season a stored record describes, as a 4-digit string.

    The `season` field comes off the hitter leaderboard. It falls back to the
    year of `vintage_date` because a board that omitted the field was still
    written inside the season it was aggregating; the fallback never crosses a
    boundary, since a record stamped 2027-04-11 is a 2027 record whatever its
    sources forgot to say."""
    s = str((rec or {}).get("season") or "").strip()
    if len(s) == 4 and s.isdigit():
        return s
    d = _iso_date((rec or {}).get("vintage_date"))
    return d[:4] if d else None


def game_season(on_date: str) -> str | None:
    """The season a game on this date belongs to: its calendar year.

    An MLB season is contained in one calendar year, spring training through the
    World Series, and that is the label the leaderboards themselves carry
    ("2026"). No offseason date is ever inside a season, which is exactly why a
    request from one has to come back empty rather than reach backwards."""
    d = _iso_date(on_date)
    return d[:4] if d else None


def archive_feature_date(rec: dict | None) -> str | None:
    """The newest feature date the ARCHIVE demonstrably holds for this record,
    or None when the record cannot say.

    `tools/backfill_vintages.py` compares this against a candidate's git
    feature_cutoff to decide whether a date adds any leaderboard information.
    Two units meet here and the difference is deliberate:

      * a backfilled record carries `provenance.feature_cutoff`, which IS a git
        commit date, so the comparison is exact;
      * a live record has no commit at all, so the honest answer is the newest
        `as_of` among its three sources. That is at or behind the commit date of
        the equivalent blob (measured over all 55 board commits in the 2026
        history: 0 as_of ahead of its commit, 2 one day behind), so a live
        record can only UNDERSTATE what the archive holds. Understating makes
        the backfill write a day it might have skipped, which costs a fresher
        stamp over near-identical features. Overstating would skip a day whose
        features the archive never held, which loses evidence."""
    p = (rec or {}).get("provenance")
    if isinstance(p, dict):
        fc = _iso_date(p.get("feature_cutoff"))
        if fc:
            return fc
    src = (rec or {}).get("sources")
    if isinstance(src, dict):
        seen = [_iso_date(m.get("as_of")) for m in src.values() if isinstance(m, dict)]
        seen = [d for d in seen if d]
        if seen:
            return max(seen)
    return None


def _pa_weighted_hem(order: list | None) -> float | None:
    """One batting order (teams[].orders.vl or .vr) -> the PA-weighted mean of
    its slots' hem_plus, or None when the order carries nothing usable.

    PA weighting rather than a flat mean because the artifact carries each
    slot's season PA and a nine-hole bat is not a leadoff bat. A slot missing
    either number is skipped, never counted as zero: zero is a value on the
    HEM+ scale (it is a hundred points below average) and treating absence as
    zero would silently crater a team's split the night one slot lost its PA
    column. Verified on the 2026-08-16 artifact: 540 slots, 0 missing."""
    tot_pa, acc = 0.0, 0.0
    for s in (order or []):
        if not isinstance(s, dict):
            continue
        hem, pa = s.get("hem_plus"), s.get("pa")
        if hem is None or pa is None:
            continue
        try:
            hem, pa = float(hem), float(pa)
        except (TypeError, ValueError):
            continue
        if pa <= 0:
            continue
        tot_pa += pa
        acc += hem * pa
    return round(acc / tot_pa, 3) if tot_pa > 0 else None


def off_splits_from_hitter_team(team_blob: dict | None) -> tuple[float | None, float | None]:
    """(off_vs_lhp, off_vs_rhp) for one hitter-leaderboard team row.

    vl is the order the team runs AGAINST A LEFT-HANDED starter and vr against
    a right-handed one (hitter_export's _ORDER_KEY_CONTRACT). On a night the
    batSide lens was down the two orders are byte-identical and the two values
    come out equal; that is a fact about the source, recorded in the artifact's
    own platoon block, and the capture stores what the artifact said.

    Shared by the WRITE side (reduce_current) and the LIVE side
    (betting_model.team_inputs_detail) so the reduction exists exactly once and
    the live/vintage key sets cannot drift."""
    orders = (team_blob or {}).get("orders")
    if not isinstance(orders, dict):
        return None, None
    return _pa_weighted_hem(orders.get("vl")), _pa_weighted_hem(orders.get("vr"))


# ---------------------------------------------------------------------------
# schema-3 dark-capture builders (docs/diamond-betting.md section 5c, B3/B4)
# ---------------------------------------------------------------------------
# Four columns shipped 2026-08-16 as stated nulls because no builder existed.
# The builders below exist as of 2026-08-19. Every one of them reads ONLY what
# is knowable at capture time, and every null they emit carries its reason.
# Nothing served reads any of these columns; they accrue dark, per section 5c.
#
# THE xwOBA PAIR is a cumulative-difference construction. There is no dated
# team-xwOBA source anywhere on disk (checked 2026-08-19: .cache/game_feeds
# box lines carry no Statcast expected stats; .cache/savant_mlb CSVs are
# season-aggregate files overwritten in place; data/leaderboard_gamelogs.json
# is 182 prospects, not MLB teams). What DOES exist is the tracked board:
# data/hitter_leaderboards.json carries per-hitter season-to-date Savant
# xwOBA and PA, and its git history is a dated archive on the same
# leak-free-by-construction argument the backfill runs on (a blob committed at
# time T contains nothing after T). So the trailing-W-day team xwOBA is
#
#   sum over hitters (xwoba_now*pa_now - xwoba_anchor*pa_anchor)
#   / sum over hitters (pa_now - pa_anchor)
#
# with the anchor read from the newest board commit dated on or before D-W.
# Stated approximations, carried in the basis: the board rounds xwoba to 3
# decimals (order .005 team noise over a 14d window); hitters below the Savant
# PA floor at the anchor are excluded entirely (they carry no anchor xwoba);
# a hitter traded inside the window credits his whole window to his current
# club; the anchor commit can trail D-W by up to XWOBA_ANCHOR_TOLERANCE_DAYS,
# so the true window is W to W+tolerance days and the basis records which.
XWOBA_WINDOWS = {"xwoba_14": 14, "xwoba_30": 30}
XWOBA_ANCHOR_TOLERANCE_DAYS = 7
# Window-PA floors, per column. Observed on 2026-08-19: min team window PA was
# 189 (14d) and 625 (30d), so these floors only fire on a degenerate window
# (season opening weeks, or a board whose xwoba coverage collapsed).
XWOBA_MIN_WINDOW_PA = {"xwoba_14": 100.0, "xwoba_30": 200.0}
BOARD_FILE = "hitter_leaderboards.json"

# lineup_strength: the day's captured orders, joined to the projections
# already on disk. Season-to-date offense is already captured (off_vs_lhp/rhp
# on HEM+); this column is the FORWARD-LOOKING read of the same nine names:
# mean projected year-1 wOBA (mlb_projections.json vets[].woba[0]) over the
# order slots, each side needing LINEUP_MIN_JOINED_SLOTS of its nine bats to
# join, the vl and vr side means averaged. Projected wOBA rather than rosWar
# because it is a rate on the wOBA scale (comparable across dates), while
# rest-of-season WAR shrinks mechanically as the season runs out.
LINEUP_MIN_JOINED_SLOTS = 7

# star_out: availability of each club's stars. Top STAR_OUT_TOP_N projected
# players per org by mlb_projections.json vets[].warY1Champ (the year-1
# champion WAR: a scalar on every vet row, and less depressed by a current IL
# stint than rest-of-season WAR, which would hide the exact player this column
# wants to flag), counted against the cached StatsAPI 40-man roster status
# codes (.cache/statsapi_roster_40man_{teamId}_{season}.json, refreshed by the
# nightly projections step via proj_export._il_out60). Codes D7/D10/D15/D60
# and compounds are the IL set. 0 is a real value (all stars healthy); null
# means the org's roster cache was absent or older than the freshness window.
STAR_OUT_TOP_N = 5
IL_CACHE_MAX_AGE_HOURS = 48.0


def _hitter_xwoba_map(hit_blob: dict | None) -> dict[int, tuple[float, float, str | None]]:
    """mlbam -> (season xwOBA, season PA, canonical org) for every hitter row
    carrying both numbers. Hitters below the Savant PA floor carry xwoba None
    on the board and are absent here, which is what makes the anchor-side
    exclusion below explicit rather than accidental."""
    out: dict[int, tuple[float, float, str | None]] = {}
    for h in (hit_blob or {}).get("hitters") or []:
        if not isinstance(h, dict):
            continue
        mid, xw, pa = h.get("mlbam"), h.get("xwoba"), h.get("pa")
        if not mid or xw is None or not pa:
            continue
        try:
            out[int(mid)] = (float(xw), float(pa), _org(h.get("team")))
        except (TypeError, ValueError):
            continue
    return out


def xwoba_window_from_boards(cur_blob: dict | None, anchor_blob: dict | None,
                             *, min_window_pa: float = 0.0) -> tuple[dict[str, float], dict]:
    """({org: window xwOBA}, diagnostics) by cumulative difference between two
    board states. Pure function of its two inputs so the arithmetic is testable
    without git.

    Per hitter on TONIGHT'S board with xwoba and pa:
      * absent from the anchor board -> his whole season is inside the window
        (a call-up or a new acquisition), full cum counts;
      * present with xwoba and pa at the anchor -> the difference counts;
      * present at the anchor WITHOUT an xwoba (below the Savant floor then)
        -> excluded entirely, because his anchor cum is unknowable and
        treating it as zero would invent window production;
      * a non-positive window PA (data revision) -> excluded.
    A team lands in the output only when its summed window PA clears
    `min_window_pa`; zero teams is a valid, stated outcome."""
    cur = _hitter_xwoba_map(cur_blob)
    anchor = _hitter_xwoba_map(anchor_blob)
    # The anchor map above only holds rows WITH xwoba; rows present without it
    # need to be told apart from rows absent entirely.
    anchor_pa_only = set()
    for h in (anchor_blob or {}).get("hitters") or []:
        if isinstance(h, dict) and h.get("mlbam") and h.get("xwoba") is None:
            try:
                anchor_pa_only.add(int(h["mlbam"]))
            except (TypeError, ValueError):
                pass
    acc: dict[str, list[float]] = {}
    n_used = n_skipped = 0
    for mid, (xw, pa, org) in cur.items():
        if not org:
            continue
        old = anchor.get(mid)
        if old is not None:
            dnum, dpa = xw * pa - old[0] * old[1], pa - old[1]
        elif mid in anchor_pa_only:
            n_skipped += 1
            continue
        else:
            dnum, dpa = xw * pa, pa
        if dpa <= 0:
            continue
        a = acc.setdefault(org, [0.0, 0.0])
        a[0] += dnum
        a[1] += dpa
        n_used += 1
    vals = {org: round(num / dpa, 4) for org, (num, dpa) in acc.items()
            if dpa >= max(min_window_pa, 1.0)}
    return vals, {"n_hitters": n_used, "n_skipped_no_anchor_xwoba": n_skipped,
                  "n_below_pa_floor": len(acc) - len(vals)}


def _git_board_anchor(target_date: str, season: str | None,
                      *, repo_dir: Path | None = None):
    """(board blob, anchor commit date, note) for the newest committed
    data/hitter_leaderboards.json whose COMMIT DATE is on or before
    `target_date`, or (None, None, why) when git cannot produce one.

    The commit date is the cutoff, never the blob's own as_of, the same rule
    of construction the backfill runs on (module docstring): a blob committed
    at T provably contains nothing after T. The caller enforces the gap
    tolerance and the season fence; this function only finds and reads."""
    import subprocess
    rd = Path(repo_dir) if repo_dir else ROOT
    rel = "data/" + BOARD_FILE
    try:
        lg = subprocess.run(["git", "log", "--format=%H %cI", "--", rel],
                            cwd=rd, capture_output=True, text=True, timeout=60)
        if lg.returncode != 0:
            return None, None, f"git log failed ({(lg.stderr or '').strip()[:120]})"
        pick = None
        for line in lg.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) != 2:
                continue
            h, ciso = parts
            cdate = _iso_date(ciso)
            if cdate and cdate <= target_date:
                pick = (h, cdate)
                break
        if not pick:
            return None, None, f"no board commit on or before {target_date}"
        pfx = subprocess.run(["git", "rev-parse", "--show-prefix"],
                             cwd=rd, capture_output=True, text=True, timeout=30)
        if pfx.returncode != 0:
            return None, None, "git rev-parse --show-prefix failed"
        full = (pfx.stdout.strip().replace("\\", "/") + rel)
        show = subprocess.run(["git", "show", f"{pick[0]}:{full}"],
                              cwd=rd, capture_output=True, timeout=120)
        if show.returncode != 0:
            return None, None, f"git show failed for {pick[0][:10]}"
        blob = json.loads(show.stdout.decode("utf-8"))
    except Exception as e:                                       # noqa: BLE001
        return None, None, f"anchor read raised {type(e).__name__}"
    if not isinstance(blob, dict):
        return None, None, "anchor blob is not a JSON object"
    if season and str(blob.get("season") or "") not in ("", str(season)):
        return None, None, (f"anchor commit {pick[1]} is a {blob.get('season')} "
                            f"board, season fence forbids crossing into {season}")
    return blob, pick[1], None


def build_xwoba_windows(cur_blob: dict | None, on_date: str, season: str | None,
                        *, anchor_loader=None) -> dict:
    """{column: {"values": {org: v}, "basis": str}} for the xwOBA pair.
    `anchor_loader(target_date, season)` is injectable for tests and defaults
    to the git reader. Empty board short-circuits WITHOUT touching git."""
    loader = anchor_loader or _git_board_anchor
    out: dict[str, dict] = {}
    if not _hitter_xwoba_map(cur_blob):
        basis = ("ABSENT: the rolling-xwOBA builder found no hitter with a "
                 "Savant xwoba and pa on tonight's board; nothing to difference")
        return {c: {"values": {}, "basis": basis} for c in XWOBA_WINDOWS}
    for col, days in XWOBA_WINDOWS.items():
        try:
            target = (date.fromisoformat(on_date) - timedelta(days=days)).isoformat()
            blob, anchor_date, note = loader(target, season)
            if blob is None or not anchor_date:
                out[col] = {"values": {}, "basis": (
                    "ABSENT: the rolling-xwOBA builder has no committed board "
                    f"anchor for {target} ({note or 'no anchor'}); captured "
                    "null, never filled from a live file")}
                continue
            gap = (date.fromisoformat(target) - date.fromisoformat(anchor_date)).days
            if gap > XWOBA_ANCHOR_TOLERANCE_DAYS:
                out[col] = {"values": {}, "basis": (
                    f"ABSENT: the rolling-xwOBA builder's nearest board anchor "
                    f"({anchor_date}) trails the {days}d target {target} by "
                    f"{gap}d, past the {XWOBA_ANCHOR_TOLERANCE_DAYS}d tolerance; "
                    "a window that stale is a different feature")}
                continue
            vals, diag = xwoba_window_from_boards(
                cur_blob, blob, min_window_pa=XWOBA_MIN_WINDOW_PA.get(col, 0.0))
            out[col] = {"values": vals, "basis": (
                f"team rolling xwOBA, trailing {days}d by cumulative "
                f"difference: tonight's {BOARD_FILE} hitters[].xwoba*pa minus "
                f"the git anchor committed {anchor_date} (true window "
                f"{days + gap}d; {diag['n_hitters']} hitters differenced, "
                f"{diag['n_skipped_no_anchor_xwoba']} excluded lacking an "
                "anchor xwoba; Savant per-hitter season xwOBA, PA-weighted; "
                "a traded hitter's window rides his current club)")}
        except Exception as e:                                   # noqa: BLE001
            out[col] = {"values": {}, "basis": (
                f"ABSENT: the rolling-xwOBA builder raised "
                f"{type(e).__name__} tonight; captured null")}
    return out


def _proj_year1_woba_map(data_dir: Path | None = None) -> tuple[dict[str, float], str | None]:
    """{mlbam as str: projected year-1 wOBA} off mlb_projections.json
    vets[].woba[0], plus the artifact's generated_at for the basis."""
    dd = Path(data_dir) if data_dir else DATA_DIR
    proj = _load_json(dd / "mlb_projections.json")
    if not isinstance(proj, dict):
        return {}, None
    out: dict[str, float] = {}
    for v in proj.get("vets") or []:
        if not isinstance(v, dict) or not v.get("mlbam"):
            continue
        w = v.get("woba")
        if isinstance(w, list) and w and isinstance(w[0], (int, float)):
            out[str(int(v["mlbam"]))] = float(w[0])
    return out, _iso_date(proj.get("generated_at"))


def lineup_strength_from_orders(team_blob: dict | None,
                                woba_map: dict[str, float]) -> float | None:
    """One hitter-leaderboard team row -> mean projected year-1 wOBA of the
    day's captured orders, or None. Each side (vl, vr) must join at least
    LINEUP_MIN_JOINED_SLOTS of its nine bats or that side is dropped; the
    value is the mean of the side means that survive. A missing slot is
    SKIPPED, never counted as zero: zero is not a wOBA a lineup runs."""
    orders = (team_blob or {}).get("orders")
    if not isinstance(orders, dict):
        return None
    side_means = []
    for side in ("vl", "vr"):
        joined = []
        for s in orders.get(side) or []:
            if isinstance(s, dict) and str(s.get("key")) in woba_map:
                joined.append(woba_map[str(s.get("key"))])
        if len(joined) >= LINEUP_MIN_JOINED_SLOTS:
            side_means.append(sum(joined) / len(joined))
    if not side_means:
        return None
    return round(sum(side_means) / len(side_means), 4)


def build_lineup_strength(hit_blob: dict | None,
                          data_dir: Path | None = None) -> dict:
    """{"values": {org: v}, "basis": str} for lineup_strength."""
    try:
        woba_map, gen = _proj_year1_woba_map(data_dir)
        if not woba_map:
            return {"values": {}, "basis": (
                "ABSENT: the lineup builder found mlb_projections.json absent "
                "or carrying no vets[].woba year-1 path; captured null")}
        vals: dict[str, float] = {}
        for t in (hit_blob or {}).get("teams") or []:
            o = _org(t.get("team")) if isinstance(t, dict) else None
            if not o:
                continue
            v = lineup_strength_from_orders(t, woba_map)
            if v is not None:
                vals[o] = v
        return {"values": vals, "basis": (
            "mean projected year-1 wOBA (mlb_projections.json vets[].woba[0], "
            f"generated {gen or 'undated'}) over the day's captured order "
            f"slots, vl and vr side means averaged; a side joins only at "
            f">= {LINEUP_MIN_JOINED_SLOTS} of 9 bats")}
    except Exception as e:                                       # noqa: BLE001
        return {"values": {}, "basis": (
            f"ABSENT: the lineup builder raised {type(e).__name__} tonight; "
            "captured null")}


def _il_by_org(season: str | int, cache_dir: Path | None = None,
               *, max_age_hours: float = IL_CACHE_MAX_AGE_HOURS
               ) -> tuple[dict[str, set[int]], str]:
    """{org: set of mlbam on the IL} for every org whose cached StatsAPI
    40-man roster file is present AND fresher than `max_age_hours`, plus a
    note describing coverage. An org missing from the dict had no fresh cache;
    an org present with an empty set has a fresh cache and nobody on the IL.
    Reads the caches the nightly projections step already writes; no fetch."""
    import time
    cd = Path(cache_dir) if cache_dir else ROOT / ".cache"
    teams_path = cd / f"statsapi_teams_{season}.json"
    teams_blob = _load_json(teams_path)
    if not isinstance(teams_blob, dict):
        return {}, f"no readable statsapi_teams_{season} cache"
    now = time.time()
    out: dict[str, set[int]] = {}
    n_stale = n_missing = 0
    for t in teams_blob.get("teams") or []:
        tid, name = t.get("id"), t.get("name")
        org = _org(name or "")
        if not tid or not org or len(org) > 3:
            continue
        rp = cd / f"statsapi_roster_40man_{tid}_{season}.json"
        try:
            age_h = (now - rp.stat().st_mtime) / 3600.0
        except OSError:
            n_missing += 1
            continue
        if age_h > max_age_hours:
            n_stale += 1
            continue
        roster = _load_json(rp)
        if not isinstance(roster, dict):
            n_missing += 1
            continue
        ils = set()
        for p in roster.get("roster") or []:
            code = str(((p or {}).get("status") or {}).get("code") or "")
            mid = ((p or {}).get("person") or {}).get("id")
            if mid and code.startswith("D"):
                ils.add(int(mid))
        out[org] = ils
    note = (f"{len(out)} orgs with a fresh roster cache, {n_stale} stale "
            f"(> {max_age_hours:.0f}h), {n_missing} missing/unreadable")
    return out, note


def star_out_from_projections(vets: list, il_by_org: dict[str, set[int]],
                              *, top_n: int = STAR_OUT_TOP_N) -> dict[str, int]:
    """{org: count of its top-N projected players on the IL}, only for orgs
    with a fresh IL read AND at least N rankable vets. Ranking is
    warY1Champ descending among vets with a numeric value and an mlbam."""
    ranked: dict[str, list[tuple[float, int]]] = {}
    for v in vets or []:
        if not isinstance(v, dict) or not v.get("mlbam"):
            continue
        org = _org(v.get("team"))
        w = v.get("warY1Champ")
        if not org or not isinstance(w, (int, float)):
            continue
        ranked.setdefault(org, []).append((float(w), int(v["mlbam"])))
    out: dict[str, int] = {}
    for org, rows in ranked.items():
        if org not in il_by_org or len(rows) < top_n:
            continue
        rows.sort(key=lambda r: (-r[0], r[1]))
        ils = il_by_org[org]
        out[org] = sum(1 for _, mid in rows[:top_n] if mid in ils)
    return out


def build_star_out(season: str | int, data_dir: Path | None = None,
                   cache_dir: Path | None = None) -> dict:
    """{"values": {org: n}, "basis": str} for star_out. 0 is a value (all
    stars healthy); an org is null when its roster cache was absent or stale."""
    try:
        dd = Path(data_dir) if data_dir else DATA_DIR
        proj = _load_json(dd / "mlb_projections.json")
        vets = (proj or {}).get("vets") if isinstance(proj, dict) else None
        if not vets:
            return {"values": {}, "basis": (
                "ABSENT: the availability builder found mlb_projections.json "
                "absent or carrying no vets; captured null")}
        il_map, il_note = _il_by_org(season, cache_dir)
        if not il_map:
            return {"values": {}, "basis": (
                f"ABSENT: the availability builder had no fresh 40-man roster "
                f"cache ({il_note}); captured null, never fetched live")}
        vals = star_out_from_projections(vets, il_map)
        return {"values": vals, "basis": (
            f"of each club's top-{STAR_OUT_TOP_N} projected players "
            "(mlb_projections.json vets[].warY1Champ), how many carry a "
            "StatsAPI 40-man IL status code (D*) in the cached roster files "
            f"({il_note}); 0 means all stars available")}
    except Exception as e:                                       # noqa: BLE001
        return {"values": {}, "basis": (
            f"ABSENT: the availability builder raised {type(e).__name__} "
            "tonight; captured null")}


def build_dark_team_columns(hit_blob: dict | None, *, on_date: str,
                            season: str | None, data_dir: Path | None = None,
                            cache_dir: Path | None = None,
                            anchor_loader=None) -> dict:
    """All four builder-backed schema-3 team columns in one pass:
    {column: {"values": {org: v}, "basis": str}}. Each builder is isolated;
    one failing costs its own column a stated null, never the snapshot."""
    out = build_xwoba_windows(hit_blob, on_date, season,
                              anchor_loader=anchor_loader)
    out["lineup_strength"] = build_lineup_strength(hit_blob, data_dir)
    out["star_out"] = build_star_out(season or on_date[:4], data_dir, cache_dir)
    return out


def team_row(rec: dict | None, org: str) -> dict | None:
    """One stored team as {column: value}, over the CURRENT TEAM_COLUMNS.

    THE EXPLICIT STATED FALLBACK for the schema seam: a column the record was
    written without (a schema-2 record read under the schema-3 reader) comes
    back None, never a silent zero. Zero is a value on every one of these
    scales; None is the absence of one, and `feature_basis` says why. The
    record's OWN column list decides where each stored value sits, so a reader
    never indexes the array by today's positions."""
    row = ((rec or {}).get("teams") or {}).get(org)
    if not isinstance(row, list):
        return None
    cols = list((rec or {}).get("team_columns") or ())
    pos = {c: i for i, c in enumerate(cols)}
    return {c: (row[pos[c]] if c in pos and pos[c] < len(row) else None)
            for c in TEAM_COLUMNS}


def pitcher_row(rec: dict | None, mlbam) -> dict | None:
    """One stored pitcher as {column: value}, over the CURRENT PITCHER_COLUMNS.
    Same contract as team_row: a column the record predates reads None."""
    row = ((rec or {}).get("pitchers") or {}).get(str(mlbam))
    if not isinstance(row, list):
        return None
    cols = list((rec or {}).get("pitcher_columns") or ())
    pos = {c: i for i, c in enumerate(cols)}
    return {c: (row[pos[c]] if c in pos and pos[c] < len(row) else None)
            for c in PITCHER_COLUMNS}


def feature_basis(rec: dict | None) -> dict:
    """Where each dark-capture column's values came from, or why there are
    none. {column: {"basis": str, "n": int}}.

    A schema-3 record carries the block it was written with. An OLDER record
    gets a synthesized one naming the schema seam, so the marking exists for
    every record a reader can hold and 'predates the column' is a stated basis
    rather than a missing key. The park rides along under the same shape
    because it is the precedent the block generalizes; park_source/park_note
    on the record are unchanged for back-compat."""
    r = rec or {}
    fb = r.get("feature_basis")
    if isinstance(fb, dict) and fb:
        return dict(fb)
    schema = r.get("schema")
    reason = (f"ABSENT: schema {schema} record predates the column "
              "(added in schema 3, 2026-08-16)")
    out = {c: {"basis": reason, "n": 0}
           for c in SCHEMA3_TEAM_COLUMNS + SCHEMA3_PITCHER_COLUMNS}
    parks = r.get("parks")
    n_parks = len(parks) if isinstance(parks, dict) else 0
    out["park"] = {"basis": (r.get("park_source") or
                             "ABSENT: record carries no park column; price on a "
                             "NEUTRAL park, never the live index"),
                   "n": n_parks}
    return out


def park_snapshot(data_dir: Path | None = None) -> dict | None:
    """{canonical org: runs index / 100} for the record, or None.

    NONE IS A SENTINEL AND AN EMPTY DICT IS FORBIDDEN. `{}` would be written to
    disk, read back as "these are the parks", and price every game at a flat
    1.00 while being indistinguishable from a genuinely neutral league. None
    says "this record has no park column", which is exactly what the reader
    needs in order to fall back explicitly and mark the games it affected.
    Missing a park does NOT make the whole block None: `betting_model` already
    resolves an absent org to neutral at lookup (ATH has no Savant entry), and
    dropping 29 measured parks over the 30th would be the same mistake in
    reverse."""
    dd = Path(data_dir) if data_dir else DATA_DIR
    meta = _load_json(dd / "fa_meta.json")
    pf = (meta or {}).get("park_factors") if isinstance(meta, dict) else None
    if not isinstance(pf, dict) or not pf:
        return None
    out: dict[str, float] = {}
    for org, v in pf.items():
        o = _org(org)
        if not o or not isinstance(v, dict):
            continue
        try:
            out[o] = round(float(v.get("runs") or 100) / 100.0, 4)
        except (TypeError, ValueError):
            continue
    return out or None


# ---------------------------------------------------------------------------
# reduce the live leaderboards to a record
# ---------------------------------------------------------------------------
def reduce_current(*, on_date: str | None = None, data_dir: Path | None = None) -> dict | None:
    """The live leaderboards, reduced to the fields the betting model reads.

    None when the leaderboards are absent or do not cover all three sides,
    because a half-populated vintage is worse than no vintage: it would be
    silently eligible to price games and would price them on a broken
    prevention blend."""
    dd = Path(data_dir) if data_dir else DATA_DIR
    vintage_date = on_date or _today()

    src_meta, blobs = {}, {}
    for name in SOURCES:
        d = _load_json(dd / name)
        if not isinstance(d, dict):
            return None
        blobs[name] = d
        # `as_of` is stamped with TODAY on every write, including a write that
        # kept the previous run's block because this run produced nothing. So
        # as_of alone cannot tell a fresh board from a carried-over one, and a
        # staleness check built on it would never fire. The boards record the
        # honest signal separately, in team_rollup, and that is what gets
        # carried into the vintage.
        _roll = d.get("team_rollup") if isinstance(d.get("team_rollup"), dict) else {}
        src_meta[name] = {
            "as_of": _iso_date(d.get("as_of")) or _iso_date(d.get("generated_at")),
            "season": str(d.get("season") or "") or None,
            "stale": bool(_roll.get("stale")),
            "kept_from": _roll.get("kept_from"),
        }

    hit = blobs["hitter_leaderboards.json"]
    rot = blobs["starter_leaderboards.json"]
    pen = blobs["bullpen_leaderboards.json"]

    teams: dict[str, list] = {}

    def _slot(org: str) -> list:
        return teams.setdefault(org, [None] * len(TEAM_COLUMNS))

    i_vl, i_vr = TEAM_COLUMNS.index("off_vs_lhp"), TEAM_COLUMNS.index("off_vs_rhp")
    for t in hit.get("teams") or []:
        o = _org(t.get("team"))
        if o and t.get("offense_plus") is not None:
            row = _slot(o)
            row[0] = round(float(t["offense_plus"]), 3)
            # Schema 3 dark capture: the two order splits, reduced by the same
            # helper the live path uses. None when the artifact carries no
            # usable order, which is a stated fact, never a zero.
            row[i_vl], row[i_vr] = off_splits_from_hitter_team(t)
    for t in rot.get("teams") or []:
        o = _org(t.get("team"))
        if o and t.get("rotation_plus") is not None:
            row = _slot(o)
            row[1] = round(float(t["rotation_plus"]), 3)
            row[3] = round(float(t.get("starter_ip") or 0.0), 1)
    for t in pen.get("teams") or []:
        o = _org(t.get("team"))
        if o and t.get("bullpen_plus") is not None:
            row = _slot(o)
            row[2] = round(float(t["bullpen_plus"]), 3)
            row[4] = round(float(t.get("relief_ip") or 0.0), 1)

    # A club missing any of the three sides is dropped rather than defaulted.
    # betting_model.team_inputs already intersects the three leaderboards; the
    # vintage must not be more permissive than the live path or a backtest
    # would grade games the live model would refuse to price.
    teams = {o: r for o, r in teams.items()
             if r[0] is not None and r[1] is not None and r[2] is not None}
    if not teams:
        return None

    # Schema 3 dark capture, builder-backed columns (2026-08-19): the xwOBA
    # pair, lineup_strength and star_out. Values land only on clubs the
    # three-side intersection kept; every basis is dynamic, carrying that
    # night's anchor commit, join counts, or cache-age facts.
    season_str = src_meta["hitter_leaderboards.json"]["season"] or vintage_date[:4]
    dark = build_dark_team_columns(hit, on_date=vintage_date, season=season_str,
                                   data_dir=dd)
    # Schema 4 dark capture (2026-09-07): bullpen availability, schedule rest
    # and venue weather climatology, all off `.cache/game_feeds`, which is
    # already on disk. One pass, isolated the same way the schema-3 builders
    # are: a failure here costs its own columns a stated null, never the
    # snapshot.
    try:
        import betting_usage
        dark.update(betting_usage.build_schema4_team_columns(
            on_date=vintage_date, data_dir=dd))
    except Exception as exc:                                     # noqa: BLE001
        why = f"ABSENT: the schema-4 builder raised {type(exc).__name__}: {exc}"
        for c in SCHEMA4_TEAM_COLUMNS:
            dark[c] = {"values": {}, "basis": why}
    for col, blk in dark.items():
        i_col = TEAM_COLUMNS.index(col)
        for org, row in teams.items():
            v = (blk.get("values") or {}).get(org)
            if v is not None:
                row[i_col] = v

    pitchers: dict[str, list] = {}
    for r in rot.get("starters") or []:
        mid, plus = r.get("mlbam"), r.get("sem_plus")
        if not mid or plus is None:
            continue
        ipgs = r.get("ip_per_gs")
        pitchers[str(int(mid))] = [
            round(float(plus), 3),
            round(float(ipgs), 3) if ipgs else None,
            _org(r.get("team")),
            r.get("role") or "SP",
            None,                     # throws, filled by the bulk join below
            None,                     # sp_rest_days, filled below
            None,                     # sp_tto3_bf, filled below
        ]
    for r in pen.get("relievers") or []:
        mid, plus = r.get("mlbam"), r.get("rem_plus")
        if not mid or plus is None or str(int(mid)) in pitchers:
            continue
        # REM+ is on the same 100/10z scale as SEM+, which is what lets the
        # prevention blend treat an opener the same way it treats a starter.
        # One None per schema-3+ column, in TEAM/PITCHER_COLUMNS order: throws,
        # then sp_rest_days. Building this row a slot short is what made the
        # rest builder raise IndexError on the 171st pitcher, having silently
        # filled the first 170.
        pitchers[str(int(mid))] = [round(float(plus), 3), None,
                                   _org(r.get("team")), "RP", None, None, None]

    # Schema 3 dark capture: throwing hand, ONE bulk call at assembly, never a
    # per-game lookup. `load_pitch_hand` is lru-cached per season and returns
    # {} on any fetch failure, so a bad network night costs a null column with
    # its basis stated below, never an aborted snapshot.
    i_throws = PITCHER_COLUMNS.index("throws")
    throws_map: dict = {}
    try:
        import pal_export
        season_s = src_meta["hitter_leaderboards.json"]["season"] or vintage_date[:4]
        throws_map = pal_export.load_pitch_hand(int(season_s)) or {}
    except Exception:                                            # noqa: BLE001
        log.warning("leaderboard_vintages: pitch-hand bulk join unavailable; "
                    "the %s vintage stores throws as null", vintage_date)
        throws_map = {}
    n_throws = 0
    if throws_map:
        for mid, row in pitchers.items():
            hand = throws_map.get(int(mid))
            if hand in ("L", "R"):
                row[i_throws] = hand
                n_throws += 1

    as_ofs = [m["as_of"] for m in src_meta.values() if m["as_of"]]
    covers_through = max(as_ofs + [vintage_date])

    # An absent park index does NOT abort the snapshot. The team and pitcher
    # columns are the irreplaceable evidence (they cannot be reconstructed for a
    # past date at all); parks are near-static, so a night without them costs a
    # neutral park term on the games that read this record and nothing else. The
    # reader is told which it got by the presence of the block, never by a zero.
    parks = park_snapshot(data_dir=dd)
    if parks is None:
        log.warning("leaderboard_vintages: no park factors in %s/fa_meta.json; the %s "
                    "vintage is stored WITHOUT a park column and games priced on it "
                    "will use a neutral park", dd, vintage_date)

    # The dark-capture marking (docs/diamond-betting.md section 5c). Every
    # schema-3 column carries its basis and its populated count, so a null is
    # always a stated fact: "the builder does not exist" and "the bulk join
    # returned nothing tonight" are different sentences and both are written.
    def _n_teams_with(col: str) -> int:
        i = TEAM_COLUMNS.index(col)
        return sum(1 for r in teams.values() if r[i] is not None)

    # Builder-backed columns carry the builder's own basis for THIS night
    # (anchor commit, join counts, cache freshness); the two order splits keep
    # the static registry string. n is always counted off the stored rows, so
    # the marking cannot claim more fills than the record holds.
    fb = {c: {"basis": (dark[c]["basis"] if c in dark else FEATURE_SOURCES[c]),
              "n": _n_teams_with(c)}
          for c in SCHEMA3_TEAM_COLUMNS + SCHEMA4_TEAM_COLUMNS}
    # sp_rest_days: days since this arm's previous appearance in any cached
    # feed. None on a season debut, which is a stated absence and not a large
    # rest number, because a silent zero-or-999 is exactly what a downstream
    # reader would mistake for one.
    try:
        import betting_usage
        pit4 = betting_usage.build_pitcher_schema4(pitchers, on_date=vintage_date)
    except Exception as exc:                                     # noqa: BLE001
        why = f"ABSENT: the schema-4 pitcher builder raised {type(exc).__name__}: {exc}"
        pit4 = {c: {"values": {}, "basis": why} for c in SCHEMA4_PITCHER_COLUMNS}
    for col in SCHEMA4_PITCHER_COLUMNS:
        i_col = PITCHER_COLUMNS.index(col)
        blk = pit4.get(col) or {"values": {}, "basis": "ABSENT: builder returned nothing"}
        n_col = 0
        for mid, v in (blk.get("values") or {}).items():
            if v is not None and mid in pitchers:
                pitchers[mid][i_col] = v
                n_col += 1
        fb[col] = {"basis": blk.get("basis") or FEATURE_SOURCES.get(col, ""),
                   "n": n_col}
    fb["throws"] = {
        "basis": (FEATURE_SOURCES["throws"] if n_throws else
                  "ABSENT: the bulk pitchHand call returned nothing tonight; "
                  "the column is null, never guessed"),
        "n": n_throws,
    }
    fb["park"] = {
        "basis": (PARK_SOURCE if parks else
                  "ABSENT: fa_meta.json was unreadable tonight; games priced on "
                  "this record use a NEUTRAL park, never the live index"),
        "n": len(parks) if parks else 0,
    }

    return {
        "schema": SCHEMA,
        "vintage_date": vintage_date,
        "covers_through": covers_through,
        "captured_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "season": src_meta["hitter_leaderboards.json"]["season"],
        "org_codes": "canonical (trades.canonical_org)",
        "team_columns": list(TEAM_COLUMNS),
        "pitcher_columns": list(PITCHER_COLUMNS),
        "sources": src_meta,
        "n_teams": len(teams),
        "n_pitchers": len(pitchers),
        "n_parks": len(parks) if parks else 0,
        "feature_basis": fb,
        "teams": teams,
        "pitchers": pitchers,
        "parks": parks,
        "park_source": PARK_SOURCE if parks else None,
        "park_units": PARK_UNITS,
        "cutoff_note": ("covers_through is the max of the source leaderboards' as_of "
                        "dates and the date this file was written; a record may price "
                        "only games dated strictly after it"),
        "park_note": ("parks is null on schema 1 records and on any night fa_meta.json "
                      "was unreadable; a reader must price those games on a NEUTRAL "
                      "park and mark them, never on the live index"),
    }


# ---------------------------------------------------------------------------
# the store
# ---------------------------------------------------------------------------
def vintage_path(on_date: str, *, vintage_dir: Path | None = None) -> Path:
    return (Path(vintage_dir) if vintage_dir else VINTAGE_DIR) / f"{on_date}.json"


def snapshot(*, on_date: str | None = None, force: bool = False,
             vintage_dir: Path | None = None, data_dir: Path | None = None,
             provenance: dict | None = None, log_fn=None) -> dict:
    """Write one dated vintage. IDEMPOTENT: a date that already has a file is
    a no-op returning the record on disk.

    `provenance` is merged into the record as its own block and defaults to
    the live nightly stamp. It is descriptive only: nothing in the pricing path
    reads it, and the SCHEMA is not bumped for it (see PROVENANCE_LIVE). The
    one thing it is load-bearing for is the arm split - `coverage()` counts
    backfilled and live records separately so the two can be graded against
    each other, and a blended count would make that check unaskable.

    Returns {"written": bool, "path": str, "date": ..., "record": {...}} or a
    {"written": False, "reason": ...} when the leaderboards cannot be reduced.
    Never raises into the pipeline."""
    vdir = Path(vintage_dir) if vintage_dir else VINTAGE_DIR
    d = on_date or _today()
    path = vintage_path(d, vintage_dir=vdir)

    if path.exists() and not force:
        rec = _load_json(path)
        if isinstance(rec, dict):
            if log_fn:
                log_fn(f"leaderboard_vintages: {d} already captured "
                       f"(covers_through {rec.get('covers_through')}), no-op")
            return {"written": False, "path": str(path), "date": d,
                    "reason": "already captured", "record": rec}
        # Unreadable file: treat as absent and rewrite, since an unparseable
        # vintage is not evidence of anything.
        if log_fn:
            log_fn(f"leaderboard_vintages: {path.name} is unreadable, rewriting")

    rec = reduce_current(on_date=d, data_dir=data_dir)
    if not rec:
        if log_fn:
            log_fn("leaderboard_vintages: leaderboards absent or incomplete, "
                   "nothing captured")
        return {"written": False, "path": str(path), "date": d,
                "reason": "leaderboards absent or incomplete", "record": None}

    rec["provenance"] = (dict(provenance) if isinstance(provenance, dict) and provenance
                         else {"source": PROVENANCE_LIVE, "cutoff_basis": "write date"})
    _backfilled = rec["provenance"].get("source") == PROVENANCE_BACKFILL

    # STALE SOURCE WARNING. covers_through is a MAX over the three source as_of
    # dates and today's write date, so a board that failed to rebuild is frozen
    # at an old as_of while the record still gets stamped with tonight's date.
    # That is safe in the leakage direction, since the snapshot then knows LESS
    # than its stamp claims and can never see the future. It is not safe for
    # quality: the model would price tonight's games on a month-old view of the
    # league, on the input it weights most, and the coverage report would call
    # the archive perfectly healthy because it counts files and dates.
    #
    # So name it. A vintage whose sources lag its own date is a degraded
    # vintage, and the only way anyone finds out is if it says so.
    # Two ways a source can be behind, and as_of only catches the first:
    #   1. the file was not rewritten at all, so its as_of really is older
    #   2. the export ran, produced nothing, and KEPT the previous block while
    #      stamping as_of with today. team_rollup.stale is the only witness.
    _lagging = {
        name: (m.get("kept_from") or m.get("as_of"))
        for name, m in (rec.get("sources") or {}).items()
        # `d` is snapshot()'s vintage date. `vintage_date` is reduce_current's
        # local and does not exist here; using it raised NameError inside a
        # best-effort pipeline step, which would have swallowed it silently.
        if m.get("stale") or (m.get("as_of") and m["as_of"] < d)
    }
    if _lagging:
        rec["stale_sources"] = _lagging
        if _backfilled:
            # A backfill LAGS BY DESIGN and the operator instruction above would
            # be nonsense for it: the 2026-07-29 blob carries as_of 2026-07-28
            # because that is the board that was committed on the 29th. The lag
            # is still recorded on the record, because it is the honest measure
            # of how old the features are behind the stamp, but it is not a
            # pipeline fault and must not read like one at WARNING.
            log.info("leaderboard_vintages: %s is a git-backfill whose sources lag its "
                     "stamp %s; covers_through %s is the conservative direction",
                     path.name, _lagging, rec.get("covers_through"))
        else:
            log.warning(
                "leaderboard_vintages: %s is being written with STALE sources %s. "
                "Its covers_through will still read %s, so games priced on it get a "
                "current-looking stamp over an older view of the league. Check that "
                "run_daily step 9e-pre0 rebuilt the boards.",
                path.name, _lagging, rec.get("covers_through"))

    vdir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, separators=(",", ":")), encoding="utf-8")
    reset_cache()
    if log_fn and _lagging and not _backfilled:
        log_fn(f"leaderboard_vintages: WARNING {path.name} has stale sources "
               f"{_lagging}; the vintage is degraded, not fresh")
    if log_fn:
        # The park count is printed even when it is zero. "0 parks" in a nightly
        # log is the whole point of counting: a silent absence is what let the
        # vintage backtest read the live index for months. The provenance rides
        # the same line so a backfill can never be mistaken for a night's work.
        log_fn(f"leaderboard_vintages: wrote {path.name} "
               f"({rec['n_teams']} teams, {rec['n_pitchers']} pitchers, "
               f"{rec['n_parks']} parks, covers_through {rec['covers_through']}, "
               f"provenance {rec['provenance'].get('source')})")
    return {"written": True, "path": str(path), "date": d, "record": rec}


# Read caches. A backtest resolves a vintage for every completed game, inside
# a solver that sweeps a grid: without these, the 96-file directory scan and
# the 25 KB JSON parse run tens of thousands of times and the backtest never
# finishes. Keyed by directory so a test pointing at a tmp dir is not served
# the production store. `reset_cache()` clears them; every write goes through
# `snapshot`, which clears them itself.
_INDEX_CACHE: dict[str, list[tuple[str, str, str | None]]] = {}
_REC_CACHE: dict[tuple[str, str], dict | None] = {}


def reset_cache() -> None:
    """Drop the memoized index and records. Call after writing a vintage
    outside `snapshot`, or when a test repoints the store."""
    _INDEX_CACHE.clear()
    _REC_CACHE.clear()


def vintage_dates(*, vintage_dir: Path | None = None) -> list[str]:
    """Every captured date, ascending. Filenames only; nothing is parsed."""
    vdir = Path(vintage_dir) if vintage_dir else VINTAGE_DIR
    if not vdir.exists():
        return []
    out = []
    for p in vdir.glob("*.json"):
        d = _iso_date(p.stem)
        if d:
            out.append(d)
    return sorted(out)


def load_vintage(on_date: str, *, vintage_dir: Path | None = None) -> dict | None:
    key = (str(vintage_dir or VINTAGE_DIR), on_date)
    if key not in _REC_CACHE:
        rec = _load_json(vintage_path(on_date, vintage_dir=vintage_dir))
        _REC_CACHE[key] = rec if isinstance(rec, dict) else None
    return _REC_CACHE[key]


def _index(vintage_dir: Path | None = None) -> list[tuple[str, str, str | None]]:
    """[(covers_through, vintage_date, season)] for every readable record,
    ascending by cutoff. Built by reading the files: an index sidecar would be
    one more thing that can disagree with the archive it describes, and 180 x
    24 KB is not worth defending against. Memoized, because the backtest asks
    for a vintage once per game per solver step.

    The season rides along because `as_of` has to fence on it and must not
    reopen every record to find out."""
    key = str(vintage_dir or VINTAGE_DIR)
    if key in _INDEX_CACHE:
        return _INDEX_CACHE[key]
    out = []
    for d in vintage_dates(vintage_dir=vintage_dir):
        rec = load_vintage(d, vintage_dir=vintage_dir)
        if not rec:
            continue
        ct = _iso_date(rec.get("covers_through")) or d
        out.append((ct, d, record_season(rec)))
    out.sort()
    _INDEX_CACHE[key] = out
    return out


def as_of(on_date: str, *, vintage_dir: Path | None = None) -> dict | None:
    """The newest vintage of the SAME SEASON whose knowledge cutoff is STRICTLY
    BEFORE `on_date`.

    None when no such vintage exists, which is every date until the nightly
    snapshot has been running for a while. Callers must treat None as "I have
    no honest features for this game" and say so; silently falling back to the
    live leaderboards is the leak this module was written to close, so the
    fallback lives in `betting_model.inputs_as_of` where it is flagged.

    THE SEASON FENCE. Strictly-before is necessary and not sufficient. A
    2026-10-01 vintage is strictly before every 2027 game, so without this fence
    the first backfill run after an offseason would price April 2027 on the
    final week of 2026 and the leakage check would pass, because there is no
    leak: the failure is pooling, not leakage, and the two look identical to a
    date comparison. A vintage is a within-season aggregate (offense_plus is
    season to date), so a September vintage and an April vintage are not
    measuring the same quantity - docs/diamond-betting.md caveat 1 forbids
    exactly this. A cross-season request therefore returns None rather than
    raising: None is already this function's defined answer for "no honest
    features", every caller handles it, and raising would turn a January date
    inside a backtest loop into a pipeline crash instead of an unpriced game."""
    q = _iso_date(on_date)
    if not q:
        return None
    want = game_season(q)
    eligible = [(ct, d) for ct, d, s in _index(vintage_dir) if ct < q and s == want]
    if not eligible:
        return None
    return load_vintage(eligible[-1][1], vintage_dir=vintage_dir)


# ---------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------
def _percentile(sorted_vals: list[int], q: float) -> float | int:
    """Linear-interpolation percentile on an ASCENDING list, the numpy "linear"
    convention: position (n-1)*q, interpolated between its neighbours.

    The nearest-rank shortcut this replaced was `vals[int(n*q)]`, which at q=0.9
    and n=10 lands on index 9, the MAXIMUM. Harmless at n=414 (index 372, the
    90.1th percentile, 11 days against a true 10.7) and badly wrong on a small
    store, which is where a p90 that silently reports the max is most likely to
    be believed. An integral result is returned as an int so a distribution that
    really is flat still prints "3 days" rather than "3.0 days"; JSON has one
    number type and every consumer compares numerically."""
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    pos = (n - 1) * q
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    v = round(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo), 1)
    return int(v) if v == int(v) else v


def _age_distribution(cutoffs: list[tuple[str, str | None]], targets: list[str],
                      basis: str) -> dict:
    """How stale the vintage that prices a date is, in days.

    For each target date, the age is target minus the newest cutoff strictly
    before it. This is the number a reader is owed alongside "n games graded":
    a backfilled archive is not nightly, so the features a game is priced on can
    be a fortnight old, and a graded count alone hides that completely.

    `cutoffs` is [(cutoff date, season)] and the search is fenced on season, so
    this reports exactly the vintage `as_of` would return and never the other
    side of an offseason. Without the fence an April 2027 date would report an
    age of ~190 days off a September 2026 cutoff, which is not a stale vintage
    but no usable vintage at all; a target with no same-season prior is dropped
    from the distribution, the same way it is dropped from the gradable set."""
    ages = []
    cs = sorted(cutoffs)
    for t in sorted(targets):
        prior = [c for c, s in cs if c < t and s == t[:4]]
        if not prior:
            continue
        ages.append((datetime.strptime(t, "%Y-%m-%d").date()
                     - datetime.strptime(max(prior), "%Y-%m-%d").date()).days)
    if not ages:
        return {"basis": basis, "n": 0, "note": "no date in the window has a vintage before it"}
    ages.sort()
    return {
        "basis": basis,
        "n": len(ages),
        "median_days": _percentile(ages, 0.5),
        "p90_days": _percentile(ages, 0.9),
        "max_days": ages[-1],
        "mean_days": round(sum(ages) / len(ages), 2),
    }


def _relative_or_verbatim(p: Path) -> str:
    """POSIX path relative to the checkout root, or the verbatim string for a
    path outside it (test fixtures only). Published fields must not name the
    build machine."""
    try:
        return Path(p).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(p)


def coverage(*, vintage_dir: Path | None = None,
             game_dates: list[str] | None = None) -> dict:
    """How much history the store holds, where the holes are, and how stale the
    vintage that prices a date is.

    `missing_dates` counts calendar days inside the captured span with no
    file. A hole is not fatal (a game just falls back to an older vintage,
    which is still strictly-before and therefore still honest) but a run of
    them means the nightly step is not firing.

    `n_vintages_backfilled`, `n_vintages_live` and
    `n_vintages_unknown_provenance` are reported SEPARATELY and deliberately
    never merged into one another. They are different clocks with different
    failure modes: a live record is evidence that the nightly step fired, a
    backfilled one is evidence about a git blob, and the leakage check in
    docs/diamond-betting.md section 5a grades the two against each other. The
    third is neither and must not be silently added to either; a reader running
    the arm split either excludes it or reports it as its own arm. A caller that
    could only see the total could not run that check and could not tell a
    nightly outage from a healthy archive.

    `game_dates` makes the age distribution GAME weighted rather than calendar
    weighted. Without it the window is every day the archive can price, which
    weights an off day the same as a 15-game Saturday."""
    vdir = Path(vintage_dir) if vintage_dir else VINTAGE_DIR
    dates = vintage_dates(vintage_dir=vdir)
    total_bytes = 0
    for d in dates:
        try:
            total_bytes += vintage_path(d, vintage_dir=vdir).stat().st_size
        except OSError:
            pass
    # How many stored records actually carry a park column. A schema 1 record is
    # priced on a NEUTRAL park, so this is the number that says how much of the
    # archive can be graded with the park term switched on at all.
    n_with_parks = 0
    n_backfilled = n_live = n_unknown = 0
    for d in dates:
        rec = load_vintage(d, vintage_dir=vdir)
        if rec and isinstance(rec.get("parks"), dict) and rec["parks"]:
            n_with_parks += 1
        # Three arms, counted explicitly. `n_vintages_live` used to be
        # len(dates) - n_backfilled, which is the same unsafe default in
        # arithmetic form: anything unclassifiable landed in the live arm.
        src = provenance_source(rec)
        if src == PROVENANCE_BACKFILL:
            n_backfilled += 1
        elif src == PROVENANCE_LIVE:
            n_live += 1
        else:
            n_unknown += 1
    out = {
        # Checkout-relative when the store lives under the checkout (it does in
        # every deployment); the absolute form published the build machine's
        # filesystem layout and OS username into the eval artifact
        # (payload-hygiene sweep, 2026-08-16). A store outside the checkout is
        # echoed as-is, which only ever happens in test fixtures.
        "dir": _relative_or_verbatim(vdir),
        "schema": SCHEMA,
        "n_vintages": len(dates),
        # Three clocks, never blended. See the docstring.
        "n_vintages_backfilled": n_backfilled,
        "n_vintages_live": n_live,
        # Named, not folded into live. Zero on the archive as it stands
        # (2026-08-09: 10 backfilled, 5 live, 0 unknown); a nonzero value means
        # a record arrived with no provenance block after 2026-08-09, which
        # should be impossible and must not be graded as either arm.
        "n_vintages_unknown_provenance": n_unknown,
        "n_vintages_with_parks": n_with_parks,
        "n_vintages_neutral_park": len(dates) - n_with_parks,
        "first": dates[0] if dates else None,
        "last": dates[-1] if dates else None,
        "bytes": total_bytes,
        "missing_dates": [],
        "earliest_gradable_game_date": None,
        "vintage_age_days": None,
    }
    if not dates:
        out["note"] = ("no vintages captured yet; every backtest is contaminated "
                       "until the nightly snapshot has been running")
        return out
    d0 = datetime.strptime(dates[0], "%Y-%m-%d").date()
    d1 = datetime.strptime(dates[-1], "%Y-%m-%d").date()
    have = set(dates)
    missing = []
    cur = d0
    while cur <= d1:
        s = cur.isoformat()
        if s not in have:
            missing.append(s)
        cur += timedelta(days=1)
    out["missing_dates"] = missing
    out["span_days"] = (d1 - d0).days + 1
    idx = _index(vdir)
    if idx:
        # The first game date any vintage can price: one day past the earliest
        # knowledge cutoff in the store.
        first_cut = datetime.strptime(idx[0][0], "%Y-%m-%d").date()
        out["earliest_gradable_game_date"] = (first_cut + timedelta(days=1)).isoformat()
        out["latest_cutoff"] = idx[-1][0]
        cutoffs = [(ct, s) for ct, _, s in idx]
        if game_dates:
            targets, basis = [g for g in game_dates if g], "graded game dates"
        else:
            # Every calendar day the archive can price, from the first gradable
            # day through the day after the newest cutoff. It deliberately stops
            # there rather than at today: a window that runs to the wall clock
            # would make this number change without the store changing.
            targets, basis = [], "calendar days inside the archive"
            cur = first_cut + timedelta(days=1)
            end = datetime.strptime(idx[-1][0], "%Y-%m-%d").date() + timedelta(days=1)
            while cur <= end:
                targets.append(cur.isoformat())
                cur += timedelta(days=1)
        out["vintage_age_days"] = _age_distribution(cutoffs, targets, basis)
    # The unknown arm is named only when it is nonzero, so the sentence a reader
    # has been seeing does not change on an archive where nothing is unknown.
    _unk = f", {n_unknown} UNKNOWN provenance" if n_unknown else ""
    out["note"] = (f"{len(dates)} vintages ({n_backfilled} backfilled, "
                   f"{n_live} live{_unk}), {len(missing)} missing days inside "
                   "the span; a game is gradable when a vintage cutoff of the SAME SEASON "
                   "is strictly before it")
    return out


def dark_capture_dry_run(*, on_date: str | None = None,
                         data_dir: Path | None = None) -> dict:
    """Capture-shaped rehearsal of the schema-3 dark columns: runs the exact
    reduction the nightly snapshot runs, reports per-column fill counts and
    bases, and WRITES NOTHING. First-write-wins makes a rehearsal against a
    date that already has a file otherwise unobservable; this is how a builder
    change is checked before its first real vintage lands."""
    d = on_date or _today()
    rec = reduce_current(on_date=d, data_dir=data_dir)
    if not rec:
        return {"ok": False, "date": d,
                "reason": "leaderboards absent or incomplete"}
    cols = rec["team_columns"]
    n_teams = rec["n_teams"]
    fills = {}
    for c in SCHEMA3_TEAM_COLUMNS:
        i = cols.index(c)
        fills[c] = {
            "filled": sum(1 for r in rec["teams"].values() if r[i] is not None),
            "of": n_teams,
            "basis": (rec.get("feature_basis") or {}).get(c, {}).get("basis"),
        }
    fills["throws"] = {
        "filled": (rec.get("feature_basis") or {}).get("throws", {}).get("n", 0),
        "of": rec["n_pitchers"],
        "basis": (rec.get("feature_basis") or {}).get("throws", {}).get("basis"),
    }
    return {"ok": True, "date": d, "written": False,
            "covers_through": rec["covers_through"], "n_teams": n_teams,
            "n_pitchers": rec["n_pitchers"], "columns": fills}


def run(*, log_fn=None) -> dict:
    """Pipeline entry point. Never raises; the daily step wraps it anyway."""
    try:
        return snapshot(log_fn=log_fn)
    except Exception:                                            # pragma: no cover
        log.exception("leaderboard_vintages: snapshot failed")
        return {"written": False, "reason": "exception", "record": None}


if __name__ == "__main__":                                       # pragma: no cover
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(
        description="Dated snapshots of the betting model's team inputs.")
    ap.add_argument("--snapshot", action="store_true", help="capture tonight's vintage")
    ap.add_argument("--force", action="store_true", help="overwrite an existing date")
    ap.add_argument("--date", default=None, help="stamp date (default: today)")
    ap.add_argument("--coverage", action="store_true", help="how much history exists")
    ap.add_argument("--as-of", dest="as_of", default=None,
                    help="show the vintage a game on this date would be priced on")
    ap.add_argument("--dry-run-dark", action="store_true",
                    help="rehearse the schema-3 dark capture against today's "
                         "data and print per-column fill counts; writes nothing")
    args = ap.parse_args()

    if args.dry_run_dark:
        print(json.dumps(dark_capture_dry_run(on_date=args.date), indent=1))

    if args.snapshot:
        r = snapshot(on_date=args.date, force=args.force, log_fn=print)
        rec = r.get("record") or {}
        print(json.dumps({k: v for k, v in r.items() if k != "record"}, indent=1))
        if rec:
            print(f"  covers_through={rec.get('covers_through')} "
                  f"teams={rec.get('n_teams')} pitchers={rec.get('n_pitchers')}")
    if args.coverage:
        print(json.dumps(coverage(), indent=1))
    if args.as_of:
        rec = as_of(args.as_of)
        if not rec:
            print(f"no vintage strictly before {args.as_of}; a game that day cannot "
                  "be graded honestly")
        else:
            print(json.dumps({k: v for k, v in rec.items()
                              if k not in ("teams", "pitchers")}, indent=1))
