# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""dfs_export.py - data/dfs.json for the /dfs/ Daily Fantasy module.

TODAY'S SLATE, priced. The /fantasy/ corpus (fantasy_export.py) projects the
whole pool REST OF SEASON; a DFS player needs one game. This module does the
re-pricing and nothing else:

  * the slate comes from fantasy_schedule.fetch_probables (the same forward
    StatsAPI poller /redraft/'s streamer board runs on),
  * the per-player counting vectors come from data/fantasy.json (no second
    corpus build, no projection engine import at run time),
  * matchup context comes from the frames fantasy_export already loads:
    team Offense+ / Bullpen+ (_teams_context) and the opposing probable's SEM+
    off the fantasy pool itself,
  * position eligibility comes from data/mlb_fielding_positions.json.

SALARIES ARE NOT HERE, ON PURPOSE. We do not scrape DraftKings or FanDuel
salary feeds. The optimizer on /dfs/ takes salaries the USER pastes or imports
from the CSV their own site hands them, and the payload says so in `salaries`.

WHAT IS A MODEL AND WHAT IS AN ESTIMATE. The skill line (K, BB, HR, hits,
IP, PA) rides the Gate-1-validated FA projection engine through fantasy.json.
Everything this module adds on top is a documented DISPLAY-LAYER heuristic
with league anchors, marked in each row's `est` list and stated on the page:
per-game playing time, the matchup multiplier, and the park leg. No served
number moves, no model gate is triggered, and nothing here writes to the DB.

Best-effort and additive. An empty slate, a missing fantasy.json, or a dead
schedule endpoint all produce a VALID payload carrying `empty_reason`, so the
page renders a loud honest empty state instead of a blank board.

AN EMPTY BOARD IS A CLAIM, AND WE ONLY MAKE THE ONES WE CAN SUPPORT. The two
empties this module can reach are opposites and used to be the same sentence:
"the league scheduled no games" is a fact about baseball, "the schedule feed did
not answer" is a fact about our pipeline. `empty_reason_kind` names which one,
`_schedule_for_day` corroborates an empty fetch against the already-guarded
schedule in fantasy.json before it will say the day is off, and `refresh` keeps
the previous payload rather than publishing an unverified empty or a slate that
came out structurally impossible (games, but no hitters). That carry is BOUNDED
by _MAX_STALE_CARRY_DAYS: keeping a board forever is its own dishonesty, and an
off day has to be publishable as a real empty day. The counts every join
resolved ride in `integrity`, measured over the orgs THIS SLATE needed, so a
thin board can be told from a broken one.

Run: python dfs_export.py            (writes data/dfs.json for today)
     python dfs_export.py --date 2026-08-06
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import fantasy_export as fe
import fantasy_schedule as fsched

_log = logging.getLogger("dfs_export")

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "dfs.json"

# ---------------------------------------------------------------------------
# League anchors. Each one is a published constant with a stated basis, in the
# same spirit as fantasy_export's _LG_OBP / _SP_DECISION_RATE block.
# ---------------------------------------------------------------------------
_SEASON_GAMES = 162             # team games in a regular season
_PA_PER_START = 4.15            # league plate appearances for a player who starts
_SP_IP_SHARE = 5.4 / 9.0        # starter share of a team's innings (5.4 IP per GS,
                                # the same anchor fantasy_export._pitcher_ros uses)
_MIN_ELIG_GAMES = fe._ELIG_MIN_GAMES   # games at a position before it is eligible
# Multiplier clamps. Wider than the observed spread of the inputs so the clamp
# is a guard rail, not the operative term.
_HIT_MULT_CLAMP = (0.80, 1.25)
_PIT_ALLOW_CLAMP = (0.82, 1.22)
# Announced probables that must ALL fail to price before we call the pitcher
# side collapsed rather than thin. One or two unprojected spot starters is a
# normal night (they land in `unprojected`); four in a row that all miss is a
# join, not a coincidence. See _slate_integrity.
_MIN_PROBABLES_FOR_COLLAPSE = 4


# ---------------------------------------------------------------------------
# Scoring. Transcribed from the public classic-format rules of the two big
# sites and PUBLISHED IN THE PAYLOAD so a reader can audit every weight rather
# than trust a number baked into a bundle. The client re-scores from these
# exact tables (the fantasy_scoring.points_weight_tables pattern), so the board
# and the optimizer can never disagree about what a point is.
#
# Deliberately omitted from the pitcher tables: complete game, complete-game
# shutout and no-hitter bonuses. Their per-start expectation rounds to under a
# tenth of a point in the modern usage era, and carrying them would imply a
# projection of an event this pool does not project.
# ---------------------------------------------------------------------------
DK_HITTER = {"single": 3.0, "double": 5.0, "triple": 8.0, "hr": 10.0,
             "rbi": 2.0, "r": 2.0, "bb": 2.0, "hbp": 2.0, "sb": 5.0, "cs": -2.0}
DK_PITCHER = {"ip": 2.25, "k": 2.0, "w": 4.0, "er": -2.0,
              "h": -0.6, "bb": -0.6, "hbp": -0.6}
FD_HITTER = {"single": 3.0, "double": 6.0, "triple": 9.0, "hr": 12.0,
             "rbi": 3.5, "r": 3.2, "bb": 3.0, "hbp": 3.0, "sb": 6.0, "out": -0.25}
FD_PITCHER = {"ip": 3.0, "k": 3.0, "w": 6.0, "er": -3.0}

SCORING_CATALOG = [
    {"id": "dk", "label": "Classic (DK-style)", "default": True},
    {"id": "fd", "label": "Full (FD-style)"},
]
SCORING_NOTE = ("Weights are our transcription of the public classic-format "
                "scoring rules. Sites change rules; every weight we used is in "
                "this payload, so check it against your contest before you trust it.")


def scoring_tables() -> dict:
    """The serializable weight tables the client re-scores from."""
    return {
        "dk": {"hitter": dict(DK_HITTER), "pitcher": dict(DK_PITCHER)},
        "fd": {"hitter": dict(FD_HITTER), "pitcher": dict(FD_PITCHER)},
    }


def score_line(line: dict, system: str, side: str) -> float:
    """Dot product of one per-game line with one scoring table. Missing keys
    score zero, exactly like fantasy_scoring.score_points."""
    tables = scoring_tables().get((system or "dk").lower())
    if not tables:
        raise ValueError(f"unknown DFS scoring system {system!r}")
    w = tables["hitter"] if side in ("hit", "hitter", "h") else tables["pitcher"]
    return round(sum(float((line or {}).get(k, 0) or 0) * v for k, v in w.items()), 2)


# ---------------------------------------------------------------------------
# Roster templates for the client optimizer. Published here (not hardcoded in
# the JS) so the shapes are auditable and a user can see the constraint set the
# solver ran under. The UI lets a user edit the cap and the per-team limit.
# ---------------------------------------------------------------------------
def _slots(*names) -> list:
    return [{"slot": n} for n in names]


ROSTER_TEMPLATES = [
    {"id": "classic", "label": "Classic: 2 P, C, 1B, 2B, 3B, SS, 3 OF",
     "scoring": "dk", "cap": 50000, "max_per_team": 5, "min_games": 2,
     "default": True,
     "slots": _slots("P", "P", "C", "1B", "2B", "3B", "SS", "OF", "OF", "OF")},
    {"id": "full", "label": "Full: P, C/1B, 2B, 3B, SS, 3 OF, UTIL",
     "scoring": "fd", "cap": 35000, "max_per_team": 4, "min_games": 2,
     "slots": [{"slot": "P"}, {"slot": "C/1B", "accepts": ["C", "1B"]},
               {"slot": "2B"}, {"slot": "3B"}, {"slot": "SS"},
               {"slot": "OF"}, {"slot": "OF"}, {"slot": "OF"},
               {"slot": "UTIL", "accepts": ["C", "1B", "2B", "3B", "SS", "OF", "UTIL"]}]},
]

def positions_by_mlbam() -> dict:
    """{mlbam: [slot, ...]} lineup eligibility.

    Delegates to fantasy_export._elig_positions so the eligibility RULE (games
    floor, modal-position fallback, StatsAPI abbreviation to slot map) has
    exactly one definition on the site. This module only needs the answer, and
    a second copy of the rule is how /fantasy/ ended up serving two eFV bases
    off one page."""
    return fe._elig_positions()


def _park_factors(season: int, raw: dict | None = None) -> dict:
    """{venue_id: run_pf} for the slate season, when a park-factor artifact
    covers the venue.

    HONEST GAP, stated on the page: the committed artifact
    (data/milb_park_factors.json, tools/park_line_lab.py) covers sportIds
    11-16, so no MLB venue resolves today and every park leg is neutral. The
    lookup is interface-shaped: the day an MLB park-factor table lands under
    the same venue-keyed shape, the DFS park leg starts working with no change
    here beyond the filename."""
    if raw is None:
        raw = fe._load_json("milb_park_factors.json")
    out: dict = {}
    for v in ((raw or {}).get("venues") or []):
        vid = v.get("venue_id")
        win = v.get("window_run_pf") or {}
        pf = win.get(str(season)) or win.get(str(season - 1))
        if vid is not None and isinstance(pf, (int, float)):
            out[int(vid)] = float(pf)
    return out


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _hitter_line(ros: dict, rem_games: int, mult: float) -> tuple[dict, float]:
    """One hitter's expected line FOR A GAME HE STARTS, plus his start rate.

    ROS playing time already prices rest days and injury risk, so dividing by
    the remaining team games gives an UNCONDITIONAL per-game line: too low for
    a DFS slot, where the question is only ever "what does he do if he is in
    the lineup". Split the two:

        pa_per_team_game = ros.pa / remaining team games
        start_rate       = min(1, pa_per_team_game / 4.15)
        line             = ros line scaled to (pa_per_team_game / start_rate) PA

    so an everyday bat scales to a 4.15-PA game and his start rate reads ~1.0,
    while a strong-side platoon scales to the same 4.15-PA game with a start
    rate near 0.6. The optimizer prices the line; the UI shows the rate, which
    is the number a DFS player actually wants before lineups post."""
    pa = float(ros.get("pa") or 0)
    if pa <= 0 or rem_games <= 0:
        return {}, 0.0
    pa_pg = pa / rem_games
    start_rate = _clamp(pa_pg / _PA_PER_START, 0.0, 1.0)
    if start_rate <= 0:
        return {}, 0.0
    pa_per_start = pa_pg / start_rate
    scale = pa_per_start / pa
    line = {}
    for k in ("pa", "ab", "h", "single", "double", "triple", "hr", "bb",
              "hbp", "so", "sb", "cs", "r", "rbi"):
        v = ros.get(k)
        if v is None:
            continue
        # Rate-driven counting stats carry the matchup multiplier; the plate
        # appearance itself does not (a tough matchup does not shorten your
        # turn in the order), and neither does the strikeout, which moves the
        # OTHER way against a better arm. `so` is display context only (no DFS
        # table scores it; the scored out term is ab - h), so it rides through
        # unadjusted rather than carrying a sign we know is backwards.
        m = 1.0 if k in ("pa", "ab", "so") else mult
        line[k] = round(float(v) * scale * m, 3)
    line["out"] = round(max(0.0, (line.get("ab") or 0.0) - (line.get("h") or 0.0)), 3)
    return line, round(start_rate, 3)


def _pitcher_line(ros: dict, allow_mult: float) -> dict:
    """One starter's expected line for ONE start.

    The ROS vector already carries a projected start count (`gs`), so the per
    start line is a straight division. The matchup enters on the ALLOWED side
    (hits, earned runs, home runs) rather than as a blanket multiplier on the
    total, because a weak opponent does not hand a pitcher strikeouts or
    innings. Wins are left alone: fantasy_export already prices them off the
    pitcher's own FIP, and re-pricing them here on opponent offense would
    double-count the same signal."""
    gs = float(ros.get("gs") or 0)
    if gs <= 0:
        return {}
    line = {}
    for k in ("ip", "k", "bb", "hbp", "w", "qs"):
        v = ros.get(k)
        if v is not None:
            line[k] = round(float(v) / gs, 3)
    for k in ("h", "er", "hr"):
        v = ros.get(k)
        if v is not None:
            line[k] = round(float(v) / gs * allow_mult, 3)
    return line


def _team_ctx_index(teams_ctx: dict) -> dict:
    """Offense+ / Bullpen+ per org, defaulting to league average (100) so a
    missing team is neutral rather than absent - and a flag saying which of the
    two you are looking at.

    100 STAYS THE PRICE. A league-average opponent is the honest guess for a
    club we could not look up, and changing it would move served numbers for no
    modelling reason. What it must stop being is INVISIBLE: five clubs genuinely
    sit at 100, so an unlabelled 100 makes a total join failure look exactly
    like an average lineup. `*_resolved` records whether anyone measured it, and
    build_payload counts and reports the misses."""
    out = {}
    for org, row in (teams_ctx or {}).items():
        if not org:
            # A None key answers ctx.get(None) for every game side whose org
            # did not resolve, handing an unknown opponent a real club's numbers.
            continue
        entry = {}
        for field in ("offense_plus", "bullpen_plus"):
            v = (row or {}).get(field)
            ok = isinstance(v, (int, float)) and bool(v)
            entry[field] = v if ok else 100
            entry[field + "_resolved"] = ok
        out[org] = entry
    return out


def _empty(day: str, season, reason: str, extra: dict | None = None,
           kind: str | None = None) -> dict:
    """A VALID payload that carries its own reason for being empty. The page
    renders this loudly; it never renders a blank board.

    `kind` is the MACHINE-readable half of `empty_reason`, and it exists because
    the two empties this module can hit are opposites: "the league scheduled no
    games" is a fact about baseball, "the schedule feed did not answer" is a
    fact about our pipeline, and only one of them is safe to publish as an
    assertion. Keys: no_corpus, season_over, no_games_scheduled,
    schedule_unavailable, no_projections, collapsed_slate; None when healthy."""
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "slate_date": day,
        "season": season,
        "n_games": 0,
        "n_players": 0,
        "games": [],
        "players": [],
        "scoring": scoring_tables(),
        "scoring_catalog": SCORING_CATALOG,
        "scoring_note": SCORING_NOTE,
        "roster_templates": ROSTER_TEMPLATES,
        "salaries": _SALARY_BLOCK,
        "empty_reason": reason,
        "empty_reason_kind": kind,
        "notes": _NOTES,
    }
    if extra:
        payload.update(extra)
    return payload


_SALARY_BLOCK = {
    "source": "user",
    "note": ("Salaries come from you. We do not scrape or republish any site's "
             "salary feed. Paste the CSV your contest site exports, or type a "
             "handful of prices in by hand; both stay in your browser."),
    "csv_columns": ["Name", "Position", "Salary", "TeamAbbrev"],
}

_NOTES = [
    "Skill projections (K, BB, HR, hits, innings, plate appearances) come from "
    "the rest-of-season engine behind the Redraft board. Nothing new is fit here.",
    "Per-game playing time, the matchup multiplier and the park leg are display "
    "layer estimates with published league anchors. Each row lists them in `est`.",
    "Relievers are not on the slate. Save and hold chances are not knowable "
    "before first pitch, and pretending otherwise would be the least honest "
    "number on the page.",
    "Park factors: the committed artifact covers the minor league ladder only, "
    "so every MLB park leg is neutral today and labelled as such.",
    "The matchup multiplier is the inverse of an innings-weighted opponent "
    "pitching index (5.4 of 9 innings to the announced starter's SEM+, the rest "
    "to the bullpen's Bullpen+), clamped. It mirrors the opponent term the "
    "streamer board has always used. It is a display heuristic, not a fitted "
    "run-environment model, and no backtest stands behind it yet.",
]


def _schedule_for_day(day: str, fantasy: dict | None) -> tuple[list, dict]:
    """(games on `day`, provenance) - the slate, plus how we know it.

    THE DEFECT THIS EXISTS FOR (2026-08-05). build_payload used to fetch and
    then publish, on the empty list a FAILED fetch returns, the sentence "No MLB
    games scheduled for {day}." That is a positive claim about the league's
    schedule, and a network error is not evidence for it. It also reads exactly
    like a genuine off day, so the one thing a reader could have used to tell an
    outage from a Monday in November was gone.

    fsched.fetch_probables returns [] for both cases and is not this module's to
    change, so corroborate the empty here instead:

      * data/fantasy.json's schedule block is the ALREADY-GUARDED copy of this
        same feed (fantasy_export.refresh_live keeps the previous games rather
        than publishing an empty fetch), so it is a second witness available for
        free, with no second network call;
      * games for `day` in that block prove the day is NOT empty whatever the
        fetch just said, so we price the older copy instead of blanking a board;
      * a schedule block that BRACKETS `day` with real games and still holds none
        ON it is evidence of a real off day. Anything else is "we do not know",
        and we say that instead.

    STALE ALONE MUST NOT VOID THE CORROBORATION (fixed 2026-08-05, second pass).
    The first cut required `not stale_schedule`, and that turns a multi-day off
    period into an indefinite silent freeze: with the fetch down, refresh() keeps
    the previous payload on `schedule_unavailable` forever, and a real empty day
    can never be published because the only witness is disqualified for being a
    copy. It is also the wrong test. refresh_live rebuilds the block wholesale
    and only restores the GAMES, so `streamer_window` is always recomputed for
    today while a kept games list may be older - the declared window says nothing
    about what a stale copy actually covers.

    So corroborate against the copy's OWN observed span instead. By the time
    this test is reached the copy holds NO game on `day` (the branch above
    already returned if it did), so a span that contains `day` means the copy
    holds games strictly before AND strictly after it: the day is bracketed, and
    its silence is real evidence whether the copy is stale or not. A stale copy
    cannot invent a whole slate that appeared later; the only schedule
    edits that reach a bracketed day are doubleheaders (which add to a day that
    already has games) and postponements (which move TOWARD empty). The declared
    window is still honoured for a FRESH block, which is the case where a real
    off day sits at the leading edge of the window with no earlier game to
    bracket it.
    """
    sched = (fantasy or {}).get("schedule") or {}
    prev_all = sched.get("games") or []
    prev_day = [g for g in prev_all if g.get("date") == day]
    window = sched.get("streamer_window") or []
    covers = bool(len(window) == 2 and window[0] <= day <= window[1])
    prev_stale = bool(sched.get("stale_schedule"))
    prev_dates = sorted({g.get("date") for g in prev_all if g.get("date")})
    spans_day = bool(prev_dates) and prev_dates[0] <= day <= prev_dates[-1]
    try:
        s, e = fsched.date_window(1, date.fromisoformat(day))
        games = fsched.fetch_probables(s, e)
    except Exception:
        _log.exception("dfs: schedule fetch raised for %s - treating as no answer", day)
        games = []
    meta = {"n_fetched": len(games), "n_previous_for_day": len(prev_day),
            "previous_window": list(window) or None,
            "previous_covers_day": covers, "previous_stale": prev_stale,
            "previous_date_span": ([prev_dates[0], prev_dates[-1]]
                                   if prev_dates else None),
            "previous_spans_day": spans_day}
    if games:
        meta.update(source="statsapi", verified_empty=False, stale=False)
        return games, meta
    if prev_day:
        meta.update(source="fantasy.json (kept)", verified_empty=False, stale=True)
        _log.warning("dfs: schedule fetch returned nothing for %s but the guarded "
                     "fantasy.json schedule holds %d game(s) that day - pricing the "
                     "older copy rather than publishing an empty slate",
                     day, len(prev_day))
        fe._record_ingest_safe(
            "dfs_schedule", ok=False, n_rows=len(prev_day),
            message=(f"probables fetch returned 0 games for {day}; priced the "
                     f"{len(prev_day)} game(s) already in fantasy.json instead. "
                     "The slate on /dfs/ is as fresh as that copy, not as of now."))
        return prev_day, meta
    # A bracketing span is evidence on its own; the declared window only counts
    # when the block is fresh (see the docstring).
    verified = bool(prev_all) and (spans_day or (covers and not prev_stale))
    meta.update(source="statsapi (empty)", verified_empty=verified, stale=False,
                verified_by=("previous_date_span" if verified and spans_day
                             else "streamer_window" if verified else None))
    if not verified:
        _log.error("dfs: no games for %s from the feed AND no corroborating copy "
                   "(fantasy.json schedule: %d games, span %s, window %s, "
                   "stale=%s) - refusing to claim the league scheduled nothing",
                   day, len(prev_all),
                   f"{prev_dates[0]}..{prev_dates[-1]}" if prev_dates else "none",
                   window or "none", prev_stale)
        fe._record_ingest_safe(
            "dfs_schedule", ok=False,
            message=(f"no games for {day} and nothing to corroborate it with: the "
                     "probables fetch returned 0 and fantasy.json's schedule does "
                     "not cover the day. /dfs/ says the slate is unknown rather "
                     "than asserting an empty schedule."))
    return [], meta


def build_payload(*, day: str | None = None, fantasy: dict | None = None,
                  games: list | None = None, positions: dict | None = None,
                  park: dict | None = None, teams_ctx: dict | None = None) -> dict:
    """Assemble data/dfs.json. Every input is injectable so the whole thing
    runs offline in a test with a stubbed schedule.

    `games` is the fantasy_schedule.fetch_probables shape. Passing [] is the
    empty-slate case and is a supported, tested path, not an error - and it is
    the CALLER asserting the slate is empty, which is why an injected [] still
    publishes "No MLB games scheduled" while an empty fetch has to earn that
    sentence (see _schedule_for_day).

    Pure: this only builds and diagnoses. Whether the result is fit to publish
    is refresh()'s call, and it reads `empty_reason_kind` and `integrity`."""
    day = day or date.today().isoformat()
    if fantasy is None:
        fantasy = fe._load_json("fantasy.json")
    if not isinstance(fantasy, dict) or not fantasy.get("players"):
        return _empty(day, None,
                      "The rest-of-season projection corpus has not been built yet. "
                      "The nightly build seeds it.", kind="no_corpus")
    season = fantasy.get("season")
    frac = float(fantasy.get("season_fraction") or 0.0)
    rem_games = int(round(_SEASON_GAMES * max(0.0, 1.0 - frac)))
    if rem_games <= 0:
        return _empty(day, season,
                      "The regular season is over. Daily slates come back on "
                      "opening day.", kind="season_over")
    # An INJECTED `games` list is the caller's own verified slate (the offline
    # CLI, a test, a lab): [] from a caller means "there are no games", which is
    # a supported, tested path. Only a slate we went and got ourselves can be
    # empty for a reason we have to be careful about.
    if games is None:
        games, sched_meta = _schedule_for_day(day, fantasy)
    else:
        sched_meta = {"source": "caller", "n_fetched": len(games),
                      "verified_empty": True, "stale": False}
    if not games:
        if sched_meta.get("verified_empty"):
            return _empty(day, season, f"No MLB games scheduled for {day}.",
                          extra={"schedule_source": sched_meta},
                          kind="no_games_scheduled")
        return _empty(
            day, season,
            (f"We could not confirm the slate for {day}. The MLB schedule feed "
             "did not answer, so we do not know whether games are scheduled, and "
             "we will not guess. This page rebuilds on the next run."),
            extra={"schedule_source": sched_meta}, kind="schedule_unavailable")

    if positions is None:
        positions = positions_by_mlbam()
    if park is None:
        park = _park_factors(int(season) if season else date.today().year)
    if teams_ctx is None:
        teams_ctx = fe._teams_context()
    ctx = _team_ctx_index(teams_ctx)

    # Pool index. Keyed by (mlbam, side) - the two-way lesson from
    # fantasy.js/S.byId: a bare mlbam is last-write-wins and hands a hitter
    # board a pitcher record.
    pool = {}
    hitters_by_team: dict = {}
    n_hit_pool = n_hit_teamless = 0
    for p in fantasy["players"]:
        pool[(p.get("mlbam"), p.get("side"))] = p
        if p.get("side") != "hit":
            continue
        n_hit_pool += 1
        # CANONICAL ON BOTH SIDES OF THIS JOIN. fantasy.json carries the hitter
        # leaderboard's raw team code (AZ, CWS, KC, SD, SF, TB, WSH) while the
        # slate carries the schedule feed's canonical code (ARI, CHW, KCR, SDP,
        # SFG, TBR, WSN), so `hitters_by_team.get(org)` missed for 7 of 30 clubs
        # and every one of their bats was absent from /dfs/ with nothing said.
        # Measured on the 2026-08-05 payload: 30 orgs on the slate, hitters for
        # 23. Both sides go through the ONE canonicaliser (fantasy_export.
        # _canon_org -> trades.canonical_org); neither artifact is re-keyed on
        # disk, so no other reader of fantasy.json moves.
        org = fe._canon_org(p.get("team"))
        if not org:
            n_hit_teamless += 1
            continue
        hitters_by_team.setdefault(org, []).append(p)

    slate_games: list = []
    # Keyed by (mlbam, side) so a doubleheader cannot put the same bat in a
    # lineup twice. The better matchup of the two wins the row and the row
    # records that there are two games.
    by_id: dict = {}
    unprojected: list = []

    def _add(row: dict) -> None:
        k = (row["mlbam"], row["side"])
        prev = by_id.get(k)
        if prev is None:
            row["games_today"] = 1
            by_id[k] = row
            return
        prev["games_today"] = prev.get("games_today", 1) + 1
        if row["pts"]["dk"] > prev["pts"]["dk"]:
            row["games_today"] = prev["games_today"]
            by_id[k] = row
    for g in games:
        venue = g.get("venue") or {}
        pf = park.get(venue.get("id"))
        park_source = "milb_park_factors" if pf else "none"
        pf = float(pf) if pf else 1.0
        sides = {}
        for me, opp in (("home", "away"), ("away", "home")):
            side_obj = g.get(me) or {}
            opp_obj = g.get(opp) or {}
            pp = side_obj.get("probable") or {}
            opp_pp = opp_obj.get("probable") or {}
            opp_sp = pool.get((opp_pp.get("mlbam"), "pit")) if opp_pp.get("mlbam") else None
            opp_sem = ((opp_sp or {}).get("skill") or {}).get("sem_plus")
            # ONE lookup, and it reports whether it hit. Both numbers below fall
            # back to the neutral 100 exactly as before (the price does not
            # move); `matchup_resolved` is what lets a reader, and a future
            # audit, tell a measured 100 from a lookup that found nothing.
            octx = ctx.get(opp_obj.get("org")) or {}
            opp_bp = octx.get("bullpen_plus") or 100
            matchup_resolved = bool(octx.get("offense_plus_resolved")
                                    and octx.get("bullpen_plus_resolved"))
            # Opponent run prevention, innings weighted: the announced starter
            # covers 5.4 of 9 innings, the bullpen the rest. No starter posted
            # yet means the bullpen number carries the whole game rather than a
            # guess at who takes the ball.
            if opp_sem:
                opp_pitch = _SP_IP_SHARE * float(opp_sem) + (1 - _SP_IP_SHARE) * float(opp_bp)
            else:
                opp_pitch = float(opp_bp)
            hit_mult = _clamp((100.0 / opp_pitch) * pf, *_HIT_MULT_CLAMP)
            opp_off = octx.get("offense_plus") or 100
            allow_mult = _clamp((float(opp_off) / 100.0) * pf, *_PIT_ALLOW_CLAMP)
            sides[me] = {
                "org": side_obj.get("org"), "team": side_obj.get("team"),
                "probable": ({"mlbam": pp.get("mlbam"), "name": pp.get("name")}
                             if pp.get("mlbam") else None),
                # The arm THIS side's hitters have to face. Distinct from
                # `probable`, which is this side's own starter: reading one for
                # the other puts a club's ace in its own lineup's matchup cell.
                "opp_probable": ({"mlbam": opp_pp.get("mlbam"), "name": opp_pp.get("name")}
                                 if opp_pp.get("mlbam") else None),
                "opp_org": opp_obj.get("org"),
                "opp_off": opp_off, "opp_bullpen": opp_bp,
                "matchup_resolved": matchup_resolved,
                "opp_sp_sem": opp_sem,
                "opp_pitch": round(opp_pitch, 1),
                "hit_mult": round(hit_mult, 3),
                "allow_mult": round(allow_mult, 3),
                "is_home": me == "home",
            }
        slate_games.append({
            "game_pk": g.get("game_pk"), "date": g.get("date"),
            "datetime": g.get("datetime"), "status": g.get("status"),
            "venue": venue.get("name"), "venue_id": venue.get("id"),
            "park_run_pf": round(pf, 3), "park_source": park_source,
            "home": sides["home"], "away": sides["away"],
        })

        # --- pitchers: announced probables only -----------------------------
        for me in ("home", "away"):
            s = sides[me]
            pp = s.get("probable")
            if not pp:
                continue
            rec = pool.get((pp["mlbam"], "pit"))
            ros = (rec or {}).get("ros") or {}
            line = _pitcher_line(ros, s["allow_mult"]) if rec else {}
            if not line:
                unprojected.append({"mlbam": pp["mlbam"], "name": pp.get("name"),
                                    "team": s.get("org"), "why": "no rest-of-season projection"})
                continue
            fgp = fe._start_score(rec, s.get("opp_org"), teams_ctx) or {}
            _add({
                "mlbam": pp["mlbam"], "name": rec.get("name") or pp.get("name"),
                "team": s.get("org"), "opp": s.get("opp_org"),
                "is_home": s["is_home"], "game_pk": g.get("game_pk"),
                "side": "pit", "elig": ["P"],
                "line": line,
                "pts": {"dk": score_line(line, "dk", "pit"),
                        "fd": score_line(line, "fd", "pit")},
                "sem_plus": ((rec.get("skill") or {}).get("sem_plus")),
                "per_start_fgp": fgp.get("per_start_fgp"),
                "ctx": {"opp_off": s["opp_off"],
                        "matchup_resolved": s["matchup_resolved"],
                        "park_run_pf": round(pf, 3),
                        "park_source": park_source, "mult": s["allow_mult"]},
                "est": ["h", "er", "w", "qs", "matchup", "park"],
            })

        # --- hitters: everyone in the pool whose club is on the slate -------
        for me in ("home", "away"):
            s = sides[me]
            org = s.get("org")
            if not org:
                continue
            for rec in hitters_by_team.get(fe._canon_org(org) or org, []):
                mid = rec.get("mlbam")
                line, start_rate = _hitter_line(rec.get("ros") or {}, rem_games,
                                                s["hit_mult"])
                if not line or start_rate <= 0:
                    continue
                elig = rec.get("elig") or positions.get(mid) or ["UTIL"]
                _add({
                    "mlbam": mid, "name": rec.get("name"),
                    "team": org, "opp": s.get("opp_org"),
                    "is_home": s["is_home"], "game_pk": g.get("game_pk"),
                    "side": "hit", "elig": elig,
                    "line": line,
                    "pts": {"dk": score_line(line, "dk", "hit"),
                            "fd": score_line(line, "fd", "hit")},
                    "start_rate": start_rate,
                    "hem_plus": ((rec.get("skill") or {}).get("hem_plus")),
                    "ctx": {"opp_sp": (s.get("opp_probable") or {}).get("name"),
                            "opp_sp_sem": s.get("opp_sp_sem"),
                            "opp_bullpen": s.get("opp_bullpen"),
                            "opp_pitch": s.get("opp_pitch"),
                            "matchup_resolved": s["matchup_resolved"],
                            "park_run_pf": round(pf, 3), "park_source": park_source,
                            "mult": s["hit_mult"]},
                    "est": ["r", "rbi", "sb", "start_rate", "matchup", "park"],
                })

    rows = sorted(by_id.values(),
                  key=lambda r: -(r["pts"]["dk"] if r.get("pts") else -1e9))
    payload = _empty(day, season, None)
    integrity = _slate_integrity(day, slate_games, rows, ctx,
                                 n_hit_pool=n_hit_pool, n_hit_teamless=n_hit_teamless)
    payload.update({
        "n_games": len(slate_games),
        "n_players": len(rows),
        "games": slate_games,
        "players": rows,
        "remaining_team_games": rem_games,
        "season_fraction": round(frac, 3),
        "fantasy_generated_at": fantasy.get("generated_at"),
        "unprojected": unprojected[:40],
        "schedule_source": sched_meta,
        "integrity": integrity,
        "anchors": {"pa_per_start": _PA_PER_START, "sp_ip_share": round(_SP_IP_SHARE, 3),
                    "season_games": _SEASON_GAMES, "elig_min_games": _MIN_ELIG_GAMES},
    })
    if not rows:
        payload["empty_reason"] = (
            f"{len(slate_games)} games are on the slate for {day}, but no probable "
            "starter or hitter on it has a rest-of-season projection yet.")
        payload["empty_reason_kind"] = "no_projections"
    elif not integrity["ok"]:
        # A HALF BOARD IS WORSE THAN NO BOARD. The client renders `empty_reason`
        # INSTEAD of the tables, so setting it here means a reader is told the
        # slate did not assemble rather than being shown 29 pitchers and no
        # hitters and left to conclude that is the day. The rows stay in the
        # payload for an auditor; `integrity` says what is wrong with them.
        # refresh() prefers keeping YESTERDAY's good payload over publishing
        # this at all - this branch is the floor, for a box with no previous.
        payload["empty_reason"] = integrity["message"]
        payload["empty_reason_kind"] = integrity["kind"]
    return payload


def _slate_integrity(day: str, slate_games: list, rows: list, ctx: dict, *,
                     n_hit_pool: int, n_hit_teamless: int) -> dict:
    """Is this board STRUCTURALLY POSSIBLE, and what did the joins resolve?

    2026-08-05: /dfs/ served 15 games, 29 players and ZERO hitters. Every layer
    behaved: the team abbreviation map came back empty, so every hitter row in
    fantasy.json got a blank team, so the by-team hitter index was empty, so no
    club matched, so no bat was priced. Nothing raised and nothing logged, and
    the page rendered a tidy pitchers-only board. An MLB game cannot happen
    without two lineups, so "games on the slate and no hitters" is not a thin
    day, it is a broken join, and the counts have to be published for anyone to
    tell the difference.

    ZERO PITCHERS IS JUDGED DIFFERENTLY, on purpose. Two states are legitimate
    there and neither is a defect: nobody has announced a probable yet (a real
    early-morning slate), and a spot starter with no rest-of-season projection
    (he is already listed in `unprojected`). So the pitcher side only counts as
    collapsed when several arms were announced and NOT ONE of them priced, which
    no amount of ordinary roster churn produces."""
    n_hit = sum(1 for r in rows if r.get("side") == "hit")
    n_pit = sum(1 for r in rows if r.get("side") == "pit")
    n_prob = sum(1 for g in slate_games for k in ("home", "away")
                 if (g.get(k) or {}).get("probable"))
    slate_orgs = {(g.get(k) or {}).get("org") for g in slate_games
                  for k in ("home", "away")}
    slate_orgs.discard(None)
    orgs_with_hitters = {r.get("team") for r in rows if r.get("side") == "hit"}
    missing = sorted(slate_orgs - orgs_with_hitters)
    # COUNT THE CONSUMER'S KEY SPACE, NOT THE PRODUCER'S ROWS (fixed 2026-08-05,
    # second pass). This block used to count rows in `ctx` that carried a number,
    # which is a fact about fe._teams_context() and NOT about this slate. It is
    # the same defect class the rest of this module exists to kill, one level up:
    # a ctx full of resolved clubs reports "30 of 30, healthy" while every org
    # actually on tonight's card missed the lookup and priced at a neutral 100.
    # It cannot even see the failure mode, because the misses are keys ABSENT
    # from ctx and an absent key contributes nothing to a count over ctx.values().
    #
    # The one lookup that decides a price is `ctx.get(opp_obj["org"])` in
    # build_payload, and both sides of every game are somebody's opponent, so the
    # needed key set is exactly `slate_orgs`. Counting with the same .get() the
    # pricer uses means a key-space mismatch (the AZ/ARI, CWS/CHW class of bug
    # that already cost this module 7 of 30 clubs on the hitter join) shows up as
    # a number instead of hiding behind a healthy-looking 30.
    ctx_needed = sorted(slate_orgs)

    def _n_resolved(field: str) -> int:
        return sum(1 for o in ctx_needed if (ctx.get(o) or {}).get(field + "_resolved"))

    n_ctx_off, n_ctx_bp = _n_resolved("offense_plus"), _n_resolved("bullpen_plus")
    ctx_unresolved = [o for o in ctx_needed
                      if not (ctx.get(o) or {}).get("offense_plus_resolved")
                      or not (ctx.get(o) or {}).get("bullpen_plus_resolved")]
    out = {
        "ok": True, "kind": None, "message": None,
        "n_hitters": n_hit, "n_pitchers": n_pit,
        "n_probables_announced": n_prob,
        "n_slate_orgs": len(slate_orgs),
        "orgs_without_hitters": missing,
        "hitter_pool": n_hit_pool, "hitter_pool_without_team": n_hit_teamless,
        # `needed` is the denominator that matters: the clubs ON THIS SLATE.
        # `expected` is the SAME number under the name assets/dfs.js already
        # reads for its "X of Y clubs" chip and its thin-board flag; it used to
        # carry the league's 30, which made a four-game night render "8 of 30"
        # and light the warning every off-peak day. The league size and the size
        # of the context table stay published as context for a reader, and are
        # never the thing resolved is judged against.
        "matchup_orgs_resolved": {"offense_plus": n_ctx_off, "bullpen_plus": n_ctx_bp,
                                  "needed": len(ctx_needed),
                                  "expected": len(ctx_needed),
                                  "unresolved": ctx_unresolved[:12],
                                  "n_context_rows": len(ctx),
                                  "league_clubs": fe._MLB_CLUBS},
    }
    if slate_games and n_hit == 0:
        out.update(ok=False, kind="collapsed_slate", message=(
            f"{len(slate_games)} games are on the slate for {day}, but not one "
            "hitter could be matched to a club. Two lineups play every game, so "
            "this is a broken join in our build, not a thin day. We would rather "
            "show you nothing than a board missing every bat."))
    elif slate_games and n_prob >= _MIN_PROBABLES_FOR_COLLAPSE and n_pit == 0:
        out.update(ok=False, kind="collapsed_slate", message=(
            f"{n_prob} starters are announced for {day} but none of them could be "
            "priced, so the pitcher side of this board is empty. That is a broken "
            "join in our build, not a thin day."))
    return out


def _read_previous(path: Path) -> dict | None:
    """The payload currently on disk, or None. Used to decide whether a bad
    build is worth publishing over a good one."""
    try:
        prev = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return prev if isinstance(prev, dict) and prev.get("players") else None


# The two build outcomes we would rather NOT publish, and why. Both are cases
# where an older payload on disk is strictly more informative than the new one:
# yesterday's real board (stamped stale) beats a claim we cannot support and
# beats a board that is missing a whole side of the slate.
_KEEP_PREVIOUS_KINDS = {
    "schedule_unavailable": ("the schedule feed did not answer, so the new "
                             "payload asserts nothing about today"),
    "collapsed_slate": ("the new payload is structurally impossible (a slate "
                        "with games but no hitters or no priced starters)"),
}

# HOW OLD A CARRIED SLATE IS ALLOWED TO GET (2026-08-05, second pass). The keep
# rule above had no upper bound, so an outage that lasts a week serves a
# week-old board for a week - and the page's own copy still calls it a slate.
# Yesterday's games, stamped stale, are a defensible substitute for a board we
# could not verify. Games from three days ago are a different week's probables
# priced against a different set of arms, and the honest empty state (which says,
# in words, that we could not confirm the slate) beats them. Two days is set
# just under the longest league-wide scheduled gap, the ~3-day All-Star break, so
# a genuine off period can never hide entirely inside the carry window.
_MAX_STALE_CARRY_DAYS = 2


def _carry_age_days(prev: dict, day: str | None) -> int | None:
    """Days between the payload on disk and the day we just tried to build.

    None when either date is unreadable, and the caller treats that as EXPIRED:
    a carry whose age cannot be established is exactly the unbounded case this
    guard exists to end, and refusing it only ever falls back to publishing a
    loud, self-describing empty payload.

    NEGATIVE is a real answer, not an error: a `--date` backfill for an earlier
    day finds a NEWER board on disk. The bound is one-sided on purpose so that
    run keeps the newer board rather than overwriting it with a backfill's
    unverifiable empty."""
    try:
        return (date.fromisoformat(str(day))
                - date.fromisoformat(str((prev or {}).get("slate_date")))).days
    except (TypeError, ValueError):
        return None


def refresh(log=print, *, day: str | None = None, games: list | None = None,
            out_path: Path | None = None) -> int:
    """DAILY best-effort build of data/dfs.json. Returns the player count of
    what is now SERVED (which is the previous payload's count on the keep paths
    below). Never raises: a failure writes nothing and returns 0, and the page
    keeps serving yesterday's payload with its own date stamp on it.

    THE PUBLISH DECISION LIVES HERE, not in build_payload, so the builder stays
    a pure function a test can drive and the writer owns the refuse-to-publish
    rule (fantasy_export.refresh_live's EMPTY-FETCH GUARD, same shape):

      * a slate we could not verify, or a board that came out structurally
        impossible, does NOT overwrite a good payload. We restamp the previous
        one with `stale_slate` + the reason and file a RED ledger row;
      * but the carry is BOUNDED (_MAX_STALE_CARRY_DAYS). Past the bound the
        stale board is worse than the honest empty payload, so we publish the
        empty one and say so, instead of freezing /dfs/ on an old slate for as
        long as the outage lasts;
      * with nothing to keep, we publish the honest empty/broken payload, which
        carries its own `empty_reason` and renders as a loud state;
      * a payload carrying a non-finite number is never written at all (see
        fantasy_export._json_blob)."""
    try:
        payload = build_payload(day=day, games=games)
    except Exception:
        _log.exception("dfs: payload build failed - continuing")
        return 0
    path = Path(out_path) if out_path else OUT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    kind = payload.get("empty_reason_kind")
    if kind in _KEEP_PREVIOUS_KINDS:
        prev = _read_previous(path)
        age = _carry_age_days(prev, payload.get("slate_date")) if prev else None
        expired = prev is not None and (age is None or age > _MAX_STALE_CARRY_DAYS)
        if prev is not None and not expired:
            why = _KEEP_PREVIOUS_KINDS[kind]
            prev["stale_slate"] = True
            prev["stale_reason"] = payload.get("empty_reason")
            prev["stale_kind"] = kind
            # How old the carried board is, and the bound it is being measured
            # against, so the page can say "2 days old" instead of only "stale".
            prev["stale_age_days"] = age
            prev["stale_max_carry_days"] = _MAX_STALE_CARRY_DAYS
            prev["stale_checked_at"] = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
            blob = fe._json_blob(prev, "dfs_slate")
            if blob is not None:
                path.write_text(blob, encoding="utf-8")
            msg = (f"dfs: refused to publish today's build for {payload['slate_date']} "
                   f"because {why}; kept the {prev.get('n_players')}-player slate "
                   f"for {prev.get('slate_date')} ({age} day(s) old, bound "
                   f"{_MAX_STALE_CARRY_DAYS}) and stamped it stale")
            _log.error(msg)
            if callable(log):
                log(msg)
            fe._record_ingest_safe("dfs_slate", ok=False,
                                   n_rows=int(prev.get("n_players") or 0),
                                   message=msg)
            return int(prev.get("n_players") or 0)
        if expired:
            # The carry has run out. Fall through and publish the new payload:
            # it is empty, but it SAYS it is empty and why, which an old slate
            # dressed as today's board never did.
            msg = (f"dfs: {kind} for {payload.get('slate_date')}, and the payload "
                   f"on disk is for {prev.get('slate_date')} "
                   f"({'unknown' if age is None else age} day(s) old, bound "
                   f"{_MAX_STALE_CARRY_DAYS}) - the carry has expired, so we are "
                   f"publishing the honest empty state instead of freezing /dfs/ "
                   f"on a stale slate")
            payload["previous_slate_dropped"] = {
                "slate_date": prev.get("slate_date"),
                "n_players": prev.get("n_players"),
                "age_days": age, "max_carry_days": _MAX_STALE_CARRY_DAYS,
            }
        else:
            msg = (f"dfs: {kind} for {payload.get('slate_date')} with no previous "
                   "dfs.json to fall back on; published the empty state.")
        _log.error(msg)
        if callable(log):
            log(msg)
        fe._record_ingest_safe("dfs_slate", ok=False, message=msg)

    blob = fe._json_blob(payload, "dfs_slate")
    if blob is None:
        return 0                    # already logged + RED; the old file stands
    path.write_text(blob, encoding="utf-8")
    integ = payload.get("integrity") or {}
    if callable(log):
        if payload.get("empty_reason"):
            log(f"dfs: empty slate for {payload['slate_date']} - {payload['empty_reason']}")
        else:
            _mo = integ.get("matchup_orgs_resolved") or {}
            log(f"dfs: {payload['n_players']} players priced across "
                f"{payload['n_games']} games ({payload['slate_date']}) - "
                f"{integ.get('n_hitters', 0)} hitters, {integ.get('n_pitchers', 0)} "
                f"starters, matchup context on {_mo.get('offense_plus', 0)}"
                f"/{_mo.get('needed', 0)} clubs on the slate")
    # Partial misses do not block the publish - a board short a few clubs still
    # beats no board - but they do go in the ledger, because "23 of 30 orgs" is
    # the number nobody would ever have seen otherwise.
    _report_partial(payload, integ)
    return int(payload.get("n_players") or 0)


def _report_partial(payload: dict, integ: dict) -> None:
    """RED-file a board that published but did not fully resolve its joins."""
    if not payload.get("n_players"):
        return
    problems = []
    missing = integ.get("orgs_without_hitters") or []
    if missing:
        problems.append(f"{len(missing)} of {integ.get('n_slate_orgs')} slate orgs "
                        f"have no hitter priced ({', '.join(missing[:8])})")
    # Judged against the clubs THIS SLATE needed, not against 30. A four-game
    # night needs eight clubs: "8 of 30" was a false alarm every off-peak day,
    # and "30 of 30" was a false all-clear whenever the misses were keys missing
    # from the context table entirely (see _slate_integrity).
    mo = integ.get("matchup_orgs_resolved") or {}
    resolved, needed = mo.get("offense_plus"), mo.get("needed")
    if isinstance(resolved, int) and isinstance(needed, int) and resolved < needed:
        unres = ", ".join((mo.get("unresolved") or [])[:8]) or "unnamed"
        problems.append(f"opponent Offense+ resolved for {resolved} of {needed} "
                        f"clubs on this slate ({unres}); the rest price at a "
                        f"neutral 100")
    if (payload.get("schedule_source") or {}).get("stale"):
        problems.append("the slate came from the kept fantasy.json schedule, not "
                        "a fresh fetch")
    if not problems:
        return
    msg = "dfs slate published with unresolved joins: " + "; ".join(problems)
    _log.warning(msg)
    fe._record_ingest_safe("dfs_slate", ok=False,
                           n_rows=int(payload.get("n_players") or 0), message=msg)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Build data/dfs.json (daily slate projections).")
    ap.add_argument("--date", default=None, help="slate date (YYYY-MM-DD, default today)")
    ap.add_argument("--offline", action="store_true",
                    help="skip the schedule pull (empty-slate payload)")
    args = ap.parse_args()
    n = refresh(log=print, day=args.date, games=[] if args.offline else None)
    print(f"wrote {OUT_PATH} ({n} players)")
