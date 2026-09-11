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

THREE CONTEXT JOINS AND NOT ONE NEW MODEL (2026-08-07). Everything below reads
an artifact somebody else already pays for, and every one of them is absent and
labelled when it does not resolve rather than filled in:

  * PARK. The Savant runs index in data/fa_meta.json, the same table /betting/
    prices games with. It is keyed by club and a game is played at a venue, so
    it is resolved through the StatsAPI club-venue map and applied only at a
    club's own park. It is the one join here that MOVES a price, so it went
    through a pre-registered gate: docs/dfs-park-leg-gate-2026-08-07.md.
  * VEGAS. Implied team totals off the odds snapshots the betting close job
    already bought. This module never fetches: the budget is 500 credits a
    month at 3 a snapshot and this costs zero. Display only.
  * LINEUPS. Confirmed batting order from the free StatsAPI lineups hydration,
    which returns nothing until a club posts. Display only, except that a
    posted card replaces our start-rate ESTIMATE with the fact it was
    estimating, and the row stops listing it as an estimate.

Display only means display only. Neither the market's number nor a batting
order is paid into `pts`. Pricing our line off the market would be a new model
with no gate behind it, and buying the half plate appearance a leadoff spot is
worth over a ninth would be a second one.

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
from datetime import date, datetime, timedelta, timezone
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
#
# THEY BOUND THE MATCHUP TERM AND NOT THE PARK (2026-08-07). They were sized
# against the spread of the opponent pitching and offense indexes, which is the
# only input they saw while every MLB park factor was 1.00. The day the park leg
# started resolving, folding it inside these bounds made the guard rail the
# operative term for exactly the parks that carry the most park signal: measured
# on the 2026-08-07 slate, 0 of 30 game sides bound the hit clamp without the
# park leg and 2 of 30 bound it with, both at T-Mobile Park (0.83), where the
# honest multiplier of 0.707 was being clipped to 0.800. So the clamp now wraps
# the matchup index alone and the park factor multiplies the clamped result.
#
# THIS MOVES NO NUMBER THAT WAS EVER SERVED. Clamping before or after a
# multiplication by exactly 1.0 is the same arithmetic, and 1.0 is what every
# MLB park leg was until the join below landed.
_HIT_MULT_CLAMP = (0.80, 1.25)
_PIT_ALLOW_CLAMP = (0.82, 1.22)
# A guard rail on the park TABLE, not on the park effect. The committed Savant
# index spans 0.83 (T-Mobile) to 1.28 (Coors), so nothing honest reaches these
# bounds; they exist so a corrupt or mis-scaled entry (a factor written as 108
# rather than 1.08) cannot multiply a whole club's slate by a hundred.
_PARK_PF_CLAMP = (0.70, 1.45)
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


def _park_factors(season: int, raw: dict | None = None, *, meta: dict | None = None,
                  home_venues: dict | None = None) -> dict:
    """{venue_id: {"pf": run index, "source": str}} for the slate season.

    TWO TABLES, ONE VENUE-KEYED ANSWER. The MLB legs come from the Savant runs
    index in data/fa_meta.json, which the FA engine already builds
    (`fa_fit.park_factors(CLASS_YEAR - 1)`) and which /betting/ already prices
    games with through betting_model.park_index. Nothing is fetched and no
    second copy is kept: one park number, three readers. The minor-league
    artifact (data/milb_park_factors.json, sportIds 11-16) stays wired because
    it costs nothing and it is already venue-keyed, but it never resolves an
    MLB slate.

    THE ORG-TO-VENUE STEP IS NOT BOOKKEEPING. fa_meta keys park factors by
    CLUB and a game is played at a VENUE, and those coincide until the year's
    neutral-site game, where an org-keyed lookup would price a London or a
    Field of Dreams game at the nominal home club's park. Only a venue that IS
    the club's own park gets that club's factor; anything else stays neutral
    and says so. With no venue map at all (the StatsAPI call failed) the MLB
    legs go neutral rather than fall back to the org, because a factor we
    cannot place is exactly the invented leg this module refuses everywhere
    else.

    ATH HAS NO ENTRY, on purpose and not by omission: the Savant table covers
    29 of 30 clubs, and Sutter Health Park's first season is not a park factor
    yet. Its home games take source "no_factor_for_park".

    The park leg was NEUTRAL FOR EVERY MLB VENUE until 2026-08-07 and the
    payload said so. It earns its place through the pre-registered gate in
    docs/dfs-park-leg-gate-2026-08-07.md (tools/dfs_park_gate.py): over 1,720
    completed 2026 games, `mu x pf` beat a neutral park on RMSE, and only 3 of
    10,000 shuffled park assignments matched it (p = 0.0003)."""
    out: dict = {}
    if raw is None:
        raw = fe._load_json("milb_park_factors.json")
    for v in ((raw or {}).get("venues") or []):
        vid = v.get("venue_id")
        win = v.get("window_run_pf") or {}
        pf = win.get(str(season)) or win.get(str(season - 1))
        if vid is not None and isinstance(pf, (int, float)):
            out[int(vid)] = {"pf": float(pf), "source": "milb_park_factors"}
    if meta is None:
        meta = fe._load_json("fa_meta.json")
    savant = (meta or {}).get("park_factors") or {}
    if not savant:
        return out
    if home_venues is None:
        home_venues = fsched.fetch_home_venues(season)
    for vid, org in (home_venues or {}).items():
        row = savant.get(org)
        runs = (row or {}).get("runs") if isinstance(row, dict) else None
        if isinstance(runs, (int, float)) and runs:
            out[int(vid)] = {"pf": float(runs) / 100.0, "source": "savant_mlb", "org": org}
        else:
            out[int(vid)] = {"pf": 1.0, "source": "no_factor_for_park", "org": org}
    return out


def _park_basis(park: dict | None) -> str:
    """Which world the park index came back from, which is what a MISS means.

    An MLB venue absent from a map that HAS the 30 home parks is a neutral-site
    game. The same absence from a map that never loaded is our outage. Those
    are opposite claims and the row is neutral either way, so the only thing
    that can tell them apart is this label."""
    for cell in (park or {}).values():
        if isinstance(cell, dict) and cell.get("source") in ("savant_mlb",
                                                             "no_factor_for_park"):
            return "savant_mlb"
    return "venue_map_unavailable"


def _park_leg(park: dict | None, venue_id, basis: str) -> tuple[float, str]:
    """(multiplier, source) for one venue. Neutral and LABELLED is the answer
    for every miss, and the label is what tells a measured 1.00 (a genuinely
    average park sits there) from a lookup that found nothing.

    Accepts the {venue_id: float} shape as well as the current
    {venue_id: {pf, source}} one, because `build_payload(park=...)` is an
    injection point that labs and tests hand a bare index to."""
    cell = (park or {}).get(venue_id)
    if cell is None:
        return 1.0, ("neutral_site" if basis == "savant_mlb" else "none")
    if isinstance(cell, dict):
        pf, src = cell.get("pf"), str(cell.get("source") or "none")
    else:
        pf, src = cell, ("milb_park_factors" if cell else "none")
    if not isinstance(pf, (int, float)) or not pf:
        return 1.0, "none"
    guarded = _clamp(float(pf), *_PARK_PF_CLAMP)
    if guarded != float(pf):
        # A factor outside the guard is a corrupt table, not an extreme park.
        # It is said out loud rather than quietly clipped, because a silently
        # clipped 108 looks exactly like a measured 1.45.
        _log.error("dfs: park factor %.3f for venue %s is outside %s - "
                   "clamping and marking the leg as suspect", pf, venue_id,
                   _PARK_PF_CLAMP)
        return guarded, src + "_out_of_range"
    return guarded, src


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# Vegas implied team totals. READ ONLY, ZERO CREDITS.
# ---------------------------------------------------------------------------
# THE BUDGET IS THE DESIGN CONSTRAINT. The odds feed is The Odds API's free
# tier: 500 credits a month at 3 credits a snapshot, which the betting close job
# already spends twice a day. This module fetches NOTHING. It reads the
# snapshots that job already wrote to .cache/odds and joins them to the slate. A
# game with no snapshot gets an absence with a reason, never an invented line.
#
# WHY THE MONEYLINE AND NOT THE SPREAD. In every other sport an implied team
# total is (total / 2) +/- (spread / 2). MLB does not price a variable spread:
# measured on the 2026-08-06 snapshot, 97 of 99 posted runlines were exactly
# -1.5/+1.5 and the two exceptions were 2.5. The spread carries no information
# about WHO scores the runs, so the split has to come off the moneyline.
#
# WHY THE SPLIT REUSES THE BETTING MODEL. Turning a win probability into a run
# margin needs a run distribution. This module does not get to invent one: it
# inverts the one /betting/ already publishes and grades (two independent
# Poissons, `betting_runs_v1`, with the P(margin = 0) mass split by the MEASURED
# extra-innings home win rate). So the DFS board and the betting board cannot
# disagree about what a 62% favourite is worth in runs, and no new distribution
# enters the site.
#
# WHY THE LINE AND NOT THE PRICE-SOLVED TOTAL. We could solve for the total that
# reproduces the de-vigged over price instead of taking the posted line, and the
# first cut did. Measured on all 11 games of the 2026-08-06 snapshot, that
# solve came back HIGHER than the line in 11 of 11 games, by +0.40 runs on
# average. That is not information, it is the Poisson: a right-skewed count
# distribution puts P(X >= mean + 1) below one half, so a fair 50/50 line forces
# lambda up. Taking the posted line has no such artifact and is the number on
# the board a reader can check.
_ODDS_MIN_BOOKS = 2             # one book is a quote, not a market
_ITT_BISECT_STEPS = 40          # 10 runs / 2^40; the metric is rounded to 0.01
# How far a snapshot event's first pitch may sit from the scheduled game's
# before the pair is not the same game.
#
# THE JOIN NEEDS THIS AND THE ORG PAIR IS NOT ENOUGH. Snapshot FILENAMES carry
# the UTC capture date while a slate is US-local, so a close snapshot taken near
# a 10pm ET first pitch lands under TOMORROW's filename; on a snapshot written
# before betting_ingest started stamping `slate_date`, a date-filtered read
# resolves it to the wrong slate. Clubs play three-game series, so yesterday's
# card and today's are usually the SAME two org pairs, and an org-only match
# would silently price today's board on yesterday's closing line. A day apart is
# 24 hours; six is loose enough for any schedule move and nowhere near that.
_ODDS_TIME_TOLERANCE_S = 6 * 3600


def _consensus_market(event: dict) -> dict | None:
    """One event -> {p_home, total, n_books, ...} by CONSENSUS across books.

    EACH BOOK IS DE-VIGGED AGAINST ITSELF and only then compared. Taking the
    best home price from one book and the best away price from another and
    de-vigging the pair produces a market that does not exist; that exact fusion
    manufactured a 0.388 edge on /betting/ in August 2026 and it is not being
    repeated one module over. `betting_ingest.best_price` is the shop-for-a-
    price helper and is deliberately NOT what this calls.

    The median, not the mean: one book posting a stale number on a late scratch
    should not move a consensus, and with nine books a median is the robust
    read of where the market is."""
    import statistics as _stats

    import betting_ingest as bi
    import betting_model as bm

    probs, lines = [], []
    for b in (event.get("books") or {}).values():
        h2h = b.get("h2h") or {}
        dec = {k: bi.american_to_decimal(h2h.get(k)) for k in ("home", "away")}
        if all(dec.values()):
            fair = bm.devig({k: v for k, v in dec.items() if v})
            if fair.get("home") is not None:
                probs.append(float(fair["home"]))
        pt = ((b.get("totals") or {}).get("over") or {}).get("point")
        if isinstance(pt, (int, float)):
            lines.append(float(pt))
    if len(probs) < _ODDS_MIN_BOOKS or len(lines) < _ODDS_MIN_BOOKS:
        return None
    return {"p_home": _stats.median(probs), "total": _stats.median(lines),
            "n_books_ml": len(probs), "n_books_total": len(lines),
            "total_range": [min(lines), max(lines)],
            "p_home_range": [round(min(probs), 4), round(max(probs), 4)]}


def _split_total(total: float, p_home: float, tie_home: float) -> tuple[float, float, bool]:
    """(home runs, away runs, hit_the_bracket) implied by a total and a home win
    probability, under the betting module's own run distribution.

    P(home wins) is strictly increasing in the home share of a fixed total, so
    one bisection lands it. The bracket is 15%-85% of the total: outside that a
    two-way MLB moneyline has never traded, and a solution sitting ON the
    bracket is reported rather than quietly clipped."""
    import betting_model as bm

    lo, hi = 0.15 * total, 0.85 * total

    def _p(lam_home: float) -> float:
        # The moneyline's reading of the tie atom, through the betting module's
        # one reader of it (L14-01), so this bisection can never split a game
        # level after nine differently from the board it inverts.
        dist = bm.margin_distribution(lam_home, total - lam_home)
        return bm.split_tie_atom(dist, tie_home)["p_home"]

    if _p(hi) <= p_home:
        return hi, total - hi, True
    if _p(lo) >= p_home:
        return lo, total - lo, True
    for _ in range(_ITT_BISECT_STEPS):
        mid = (lo + hi) / 2.0
        if _p(mid) < p_home:
            lo = mid
        else:
            hi = mid
    home = (lo + hi) / 2.0
    return home, total - home, False


def _vegas_index(day: str, games: list) -> tuple[dict, dict]:
    """({game_pk: {home_itt, away_itt, ...}}, provenance) from the cached odds.

    Matching is (away org, home org) on the slate date, and the doubleheader
    tiebreak is the nearer first pitch: the two games of a split share a club
    pair, and the snapshot's commence_time runs about a minute later than
    StatsAPI's (measured across all 11 games of 2026-08-06), so an exact time
    match would find nothing at all."""
    meta = {"source": None, "captured_at": None, "kind": None,
            "n_events": 0, "n_matched": 0, "reason": None}
    try:
        import betting_ingest as bi
        import betting_model as bm
        wrap = bi.latest_snapshot(on_date=day)
        if not wrap:
            # Name the nearest miss. This leg read "no odds snapshot" on every
            # slate the module ever priced while the betting page consumed one
            # happily: the pipeline captured the snapshot at 9e, minutes AFTER
            # this export ran at 9d-bis (found 2026-08-16, since reordered to
            # 9d-pre-odds). Publishing the newest cached capture makes that
            # class of ordering failure visible in the payload instead of
            # indistinguishable from a night with no odds feed at all.
            snaps = bi.list_snapshots()
            if snaps:
                _newest = snaps[-1]
                meta["reason"] = (
                    "no odds snapshot is cached for this slate date "
                    f"(newest cached capture is {_newest.get('date')}-"
                    f"{_newest.get('hhmm')})")
                if _newest.get("date") == day:
                    # Drift armor: latest_snapshot filters the same listing, so
                    # a same-date capture it failed to return means the two
                    # functions no longer agree about dates. Loud, not fatal.
                    meta["ordering_regression"] = True
                    _log.error("dfs: RED, a %s snapshot exists in the cache "
                               "but the vegas join did not receive it", day)
            else:
                meta["reason"] = "no odds snapshot is cached for this slate date"
            return {}, meta
        events = bi.parse_events(wrap)
        tie_home = (bm.league_context().get("extra_inning_home_rate")
                    or bm.LITERATURE_TIE_HOME)
    except Exception:
        _log.exception("dfs: vegas join raised - continuing without it")
        meta["reason"] = "the odds snapshot could not be read"
        return {}, meta
    meta.update(source=Path(wrap.get("_path") or "").name or "odds snapshot",
                captured_at=wrap.get("captured_at"), kind=wrap.get("kind"),
                n_events=len(events),
                tie_home=round(float(tie_home), 4),
                model_version=getattr(bm, "MODEL_VERSION", None))
    by_pair: dict = {}
    for e in events:
        by_pair.setdefault((e.get("away_org"), e.get("home_org")), []).append(e)
    out: dict = {}
    n_off_slate = 0
    for g in games:
        pk = g.get("game_pk")
        cands = by_pair.get(((g.get("away") or {}).get("org"),
                             (g.get("home") or {}).get("org")))
        if not pk or not cands:
            continue
        want = _epoch(g.get("datetime"))
        ev = min(cands, key=lambda e: abs(_epoch(e.get("commence_time")) - want))
        gap = abs(_epoch(ev.get("commence_time")) - want)
        if want and gap > _ODDS_TIME_TOLERANCE_S:
            n_off_slate += 1
            _log.warning("dfs: nearest cached odds for %s vs %s is %.1f hours from "
                         "first pitch - treating it as a different game rather than "
                         "pricing this one on it", (g.get("away") or {}).get("org"),
                         (g.get("home") or {}).get("org"), gap / 3600.0)
            continue
        mk = _consensus_market(ev)
        if not mk:
            continue
        try:
            home, away, edge = _split_total(mk["total"], mk["p_home"], tie_home)
        except Exception:
            _log.exception("dfs: implied team total solve failed for %s", pk)
            continue
        out[int(pk)] = {
            "total": round(mk["total"], 2),
            "home_itt": round(home, 2), "away_itt": round(away, 2),
            "p_home": round(mk["p_home"], 4), "p_away": round(1.0 - mk["p_home"], 4),
            "n_books": min(mk["n_books_ml"], mk["n_books_total"]),
            "total_range": mk["total_range"], "p_home_range": mk["p_home_range"],
            "at_bracket": edge,
        }
    meta["n_matched"] = len(out)
    meta["n_rejected_on_time"] = n_off_slate
    if not out and events:
        meta["reason"] = (
            "the cached snapshot holds no game matching this slate" if not n_off_slate
            else (f"the cached snapshot matched {n_off_slate} club pairing(s) on this "
                  "slate but every one of them was hours from the scheduled first "
                  "pitch, so it is a different day's board"))
    return out, meta


def _epoch(ts) -> float:
    """An ISO timestamp as seconds, or 0. Only ever used to rank two candidates
    against each other, so 0 for an unparseable stamp is a stable answer."""
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


_OTHER = {"home": "away", "away": "home"}


def _vg(ctx: dict, key: str, value) -> None:
    """Write a market leg into a row's ctx, or leave the key out entirely.

    An explicit null on every row of a 524-row slate cost 84KB of a payload the
    /fantasy/ shell lazy-boots. Nothing is concealed by the omission: whether
    the market resolved at all is stated once in `vegas_source` and counted in
    `integrity.vegas_games`, and per game in `games[].vegas`. Repeating it on
    every player is not disclosure, it is weight."""
    if value is not None:
        ctx[key] = value

# The park sources that mean a factor other than 1.00 actually multiplied the
# line. Anything else left the row untouched, and listing "park" as an estimate
# on a row where the park leg did nothing is the honesty list telling a small
# lie about itself.
_PARK_APPLIED = ("savant_mlb", "milb_park_factors")


def _est(base: list, park_source: str) -> list:
    """The row's `est` list: every display-layer leg that MOVED this line.

    The park factor is MEASURED now (Savant, gate in
    docs/dfs-park-leg-gate-2026-08-07.md) and it still belongs here, because
    what is heuristic about it is the APPLICATION: a flat run index multiplying
    every counting stat alike, with no per-event elasticity, is not what a park
    does to a home run and a single. The measurement earned its place in the
    price; the shape of the application has not been graded and says so."""
    return base + (["park"] if park_source in _PARK_APPLIED else [])


def _lineup_leg(mlbam, card: list, projected: float) -> tuple:
    """(lineup_spot, status, start_rate, projected_rate) for one bat.

    THREE STATES AND THEY ARE NOT INTERCHANGEABLE:

      * the club has posted and he is on the card -> spot 1-9, status
        "confirmed", start rate 1.0. He is starting. That is not a projection
        any more and the row stops calling it one;
      * the club has posted and he is NOT on the card -> status
        "not_in_lineup", start rate 0.0. He can still pinch hit, which is worth
        approximately nothing in a DFS lineup, and the client's own minimum
        start filter takes him out of the optimizer pool where he belongs;
      * the club has not posted -> everything stays exactly as it was, status
        None. An empty card is the overwhelmingly common state at build time
        (measured 2026-08-07: 1 of 15 games), so this is the DEFAULT path and
        it must leave the projection alone.

    `pts` never moves here. The line is already conditional on starting (see
    _hitter_line), so confirming a start changes what we say about the odds of
    the start and not one number inside it. Batting order is published and is
    NOT paid into the plate appearances: a leadoff spot is worth about half a
    plate appearance over a ninth, and buying that would be a new model."""
    if not card:
        return None, None, projected, projected
    try:
        spot = list(card).index(mlbam) + 1
    except ValueError:
        return None, "not_in_lineup", 0.0, projected
    return spot, "confirmed", 1.0, projected


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
    "Park factors are the Savant runs index the free-agent engine already "
    "builds, the same table the betting model prices games with. It covers 29 "
    "of 30 parks and only applies when the game is at the home club's own park; "
    "every other venue stays neutral and each row says which it got.",
    "The matchup multiplier is the inverse of an innings-weighted opponent "
    "pitching index (5.4 of 9 innings to the announced starter's SEM+, the rest "
    "to the bullpen's Bullpen+), clamped. It mirrors the opponent term the "
    "streamer board has always used. It is a display heuristic, not a fitted "
    "run-environment model, and no backtest stands behind it yet.",
    "Vegas implied team totals are read from odds snapshots the betting module "
    "already pays for, never fetched here. They are context to read beside a "
    "projection: no line on this page is priced off the market, and a game with "
    "no cached snapshot shows no total rather than an estimated one.",
    "A lineup spot appears only once the club posts its card, which is usually "
    "after this board is built. Until then a hitter carries our projected start "
    "rate. Batting order is shown and is never paid into the projection.",
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
                  active_ids=None,
                  games: list | None = None, positions: dict | None = None,
                  park: dict | None = None, teams_ctx: dict | None = None,
                  vegas: dict | None = None, lineups: dict | None = None) -> dict:
    """Assemble data/dfs.json. Every input is injectable so the whole thing
    runs offline in a test with a stubbed schedule.

    `games` is the fantasy_schedule.fetch_probables shape. Passing [] is the
    empty-slate case and is a supported, tested path, not an error - and it is
    the CALLER asserting the slate is empty, which is why an injected [] still
    publishes "No MLB games scheduled" while an empty fetch has to earn that
    sentence (see _schedule_for_day).

    AN INJECTED SLATE ALSO OWNS ITS CONTEXT. `vegas` and `lineups` resolve
    themselves ONLY when we fetched the slate ourselves, which is the same
    doctrine `games` already carries one paragraph up: a caller who handed us a
    slate is a test, a lab or the offline CLI, and going to the network behind
    its back for a lineup it did not ask for is how an offline path stops being
    offline. Pass them explicitly to exercise the joins.

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
    own_slate = games is None
    if own_slate:
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
    park_basis = _park_basis(park)
    if vegas is not None:
        vegas_meta = {"source": "caller", "n_events": len(vegas),
                      "n_matched": len(vegas), "reason": None}
    elif own_slate:
        vegas, vegas_meta = _vegas_index(day, games)
    else:
        vegas, vegas_meta = {}, {
            "source": None, "n_matched": 0,
            "reason": "the caller supplied the slate, so no odds were read"}
    if lineups is None:
        lineups = fsched.fetch_lineups(day) if own_slate else {}
    n_lineup_sides = sum(1 for v in lineups.values() for k in ("home", "away")
                         if (v or {}).get(k))

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
        pf, park_source = _park_leg(park, venue.get("id"), park_basis)
        vg = vegas.get(g.get("game_pk"))
        lu = lineups.get(g.get("game_pk")) or {}
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
            hit_matchup = _clamp(100.0 / opp_pitch, *_HIT_MULT_CLAMP)
            hit_mult = hit_matchup * pf
            opp_off = octx.get("offense_plus") or 100
            allow_matchup = _clamp(float(opp_off) / 100.0, *_PIT_ALLOW_CLAMP)
            allow_mult = allow_matchup * pf
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
                # The two legs are published SEPARATELY as well as combined,
                # because "why is this bat priced up" has two possible answers
                # and one product cannot tell them apart.
                "hit_matchup_mult": round(hit_matchup, 3),
                "allow_matchup_mult": round(allow_matchup, 3),
                "hit_mult": round(hit_mult, 3),
                "allow_mult": round(allow_mult, 3),
                "is_home": me == "home",
                # DISPLAY ONLY, both of them. The market's read on this club and
                # the club's posted card are the two things a DFS player most
                # wants next to a projection, and neither is allowed anywhere
                # near `pts`: pricing our own line off the moneyline would be a
                # new model with no gate behind it, and paying a batting order
                # into the plate appearances would be a second one.
                "vegas_itt": (vg or {}).get(me + "_itt"),
                "vegas_p_win": (vg or {}).get("p_home" if me == "home" else "p_away"),
                "lineup_posted": bool(lu.get(me)),
            }
        slate_games.append({
            "game_pk": g.get("game_pk"), "date": g.get("date"),
            "datetime": g.get("datetime"), "status": g.get("status"),
            "venue": venue.get("name"), "venue_id": venue.get("id"),
            "park_run_pf": round(pf, 3), "park_source": park_source,
            "vegas": vg,
            "lineups_posted": {"home": bool(lu.get("home")), "away": bool(lu.get("away"))},
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
            prow = {
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
                "est": _est(["h", "er", "w", "qs", "matchup"], park_source),
            }
            # The runs the market expects the OPPOSING club to score, which is
            # the number a starter is graded on. Absent when no odds resolved.
            _vg(prow["ctx"], "vegas_opp_itt", (sides[_OTHER[me]] or {}).get("vegas_itt"))
            _add(prow)

        # --- hitters: everyone in the pool whose club is on the slate -------
        for me in ("home", "away"):
            s = sides[me]
            org = s.get("org")
            if not org:
                continue
            card = lu.get(me) or []
            for rec in hitters_by_team.get(fe._canon_org(org) or org, []):
                mid = rec.get("mlbam")
                line, start_rate = _hitter_line(rec.get("ros") or {}, rem_games,
                                                s["hit_mult"])
                if not line or start_rate <= 0:
                    continue
                elig = rec.get("elig") or positions.get(mid) or ["UTIL"]
                spot, lstatus, start_rate, projected = _lineup_leg(mid, card, start_rate)
                row_est = ["r", "rbi", "sb", "matchup"]
                if lstatus is None:
                    # A confirmed card is an OBSERVATION, so it leaves this
                    # list rather than sitting on it dressed as an estimate.
                    row_est.append("start_rate")
                row = {
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
                    "est": _est(row_est, park_source),
                }
                if lstatus:
                    # ONLY WHEN A CARD IS POSTED, which is the minority of rows
                    # and 84KB of nulls if written on all of them (measured on
                    # the 2026-08-07 slate, 524 rows). Nothing is hidden by the
                    # omission: `games[].lineups_posted` already says whether
                    # the club filed, so "no card yet" and "posted, not on it"
                    # stay distinguishable, which is the distinction that
                    # matters. A row that says nothing about a lineup is a row
                    # whose club has posted nothing.
                    row.update(lineup_spot=spot, lineup_status=lstatus,
                               # What the heuristic said, beside the fact that
                               # replaced it. A reader comparing a 1.00 against
                               # the 0.62 it overrode is watching our
                               # playing-time model get graded.
                               start_rate_projected=projected,
                               start_rate_source="confirmed_lineup")
                _vg(row["ctx"], "vegas_itt", s.get("vegas_itt"))
                _vg(row["ctx"], "vegas_p_win", s.get("vegas_p_win"))
                _add(row)

    rows = sorted(by_id.values(),
                  key=lambda r: -(r["pts"]["dk"] if r.get("pts") else -1e9))
    payload = _empty(day, season, None)
    integrity = _slate_integrity(day, slate_games, rows, ctx,
                                 n_hit_pool=n_hit_pool, n_hit_teamless=n_hit_teamless)
    integrity["park_basis"] = park_basis
    integrity["park_sources"] = _count_by(slate_games, "park_source")
    integrity["vegas_games"] = sum(1 for g in slate_games if g.get("vegas"))
    integrity["lineup_sides_posted"] = n_lineup_sides
    integrity["lineup_sides_possible"] = 2 * len(slate_games)
    # TONIGHT'S SLATE, so an off-roster player is undraftable and does not belong
    # in the pool: he cannot accrue a point. This is the opposite call from
    # fantasy, which FLAGS the same players because a rest-of-season board is
    # exactly where a manager needs to see that his man is out. Measured before
    # this shipped: 119 of 497 served DFS players (23.9%) were not on an active
    # roster. Removed rows are ledgered, not silently dropped, beside the
    # `unprojected` list that already exists for this kind of accounting.
    _active = active_ids
    off_roster = []
    if _active is not None:
        kept = []
        for r in rows:
            mid = r.get("mlbam")
            if mid is None or int(mid) in _active:
                kept.append(r)          # unreadable id -> KEEP, never over-filter
            else:
                off_roster.append({"mlbam": mid, "name": r.get("name"),
                                   "team": r.get("team"),
                                   "why": "not on a current active roster"})
        rows = kept
    payload.update({
        "vegas_source": vegas_meta,
        "n_games": len(slate_games),
        "n_players": len(rows),
        "off_roster": off_roster[:60],
        "roster_filter": {
            "applied": _active is not None,
            "n_removed": len(off_roster),
            "basis": "StatsAPI rosterType=active (26-man)",
            "policy": ("FILTERED. A DFS pool is a set of players you can draft for "
                       "tonight, and one who is not on an active roster cannot score. "
                       "fantasy.json flags the same players instead, because a "
                       "rest-of-season board is where you need to see them."),
            "on_failure": "a roster walk covering fewer than 28 of 30 clubs removes "
                          "nothing; a player whose mlbam cannot be read is kept",
        },
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


def _active_roster_ids():
    """The shared active-roster set, or None when the walk was not trustworthy."""
    try:
        from bullpen_export import _active_mlbam_ids
        from datetime import date
        return _active_mlbam_ids(date.today().year)
    except Exception:                                      # noqa: BLE001
        return None


def _count_by(rows: list, field: str) -> dict:
    """{value: n} over a list of dicts. Used for the join-source tallies in
    `integrity`, where the point is that a reader can see a source they did not
    expect (a neutral site, a park with no factor) as a NUMBER."""
    out: dict = {}
    for r in rows:
        k = str((r or {}).get(field))
        out[k] = out.get(k, 0) + 1
    return out


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


# ---------------------------------------------------------------------------
# Slate archive (2026-08-16). data/dfs.json is overwritten by every daily
# export, so until today NO slate this module ever priced could be graded
# afterwards: the registry row says so in its metric field ("none yet; no
# scored slate history exists AND NONE IS BEING ARCHIVED"). This archive is
# what makes the planned-archive language truthful from the day it runs: one
# compact file per slate date, holding exactly what a later backtest needs to
# grade the pricing (the per-player projected points with their join keys, the
# per-game context legs) and nothing a backtest cannot use. Salaries are NOT
# here because they are not in the payload: they live in the reader's browser
# by design (see _SALARY_BLOCK), and archiving would not change that.
#
# Durable per-box state, so it lives under .cache/ (the deploy box runs
# `git checkout -- .` nightly and would revert anything under data/).
# Bounded by _ARCHIVE_KEEP_DAYS: at ~60-90KB a slate, ~120 days is ~10MB, a
# full season of gradeable history, and the prune runs in the same write pass
# so the bound cannot rot.
# ---------------------------------------------------------------------------
ARCHIVE_DIR = Path(__file__).parent / ".cache" / "dfs_history"
_ARCHIVE_KEEP_DAYS = 120

# The player fields a later grading pass needs: identity + join keys (mlbam,
# side, game_pk), the served price (pts in both systems), and the playing-time
# leg that conditions it (start_rate). `line` itself is recoverable from pts
# only lossily, so the compact row keeps the price, not the whole vector.
_ARCHIVE_PLAYER_FIELDS = ("mlbam", "side", "name", "team", "opp", "game_pk",
                          "is_home", "start_rate", "games_today", "pts")
_ARCHIVE_GAME_FIELDS = ("game_pk", "date", "datetime", "venue_id",
                        "park_run_pf", "park_source", "vegas")


def _archive_slate(payload: dict, archive_dir: Path | None = None) -> Path | None:
    """Write the compact slate archive for a SUCCESSFUL build, prune, return
    the path (None when the payload does not qualify or the write refused).

    Only a healthy published board is archived: an empty or refused payload has
    no priced rows to grade, and the keep-previous path re-serves a slate that
    was archived on its own day. Idempotent per slate date: a same-day rebuild
    overwrites its own file, which keeps the LAST board served for that date,
    the one a reader actually saw at lock."""
    if not isinstance(payload, dict) or payload.get("empty_reason"):
        return None
    if not payload.get("n_players"):
        return None
    day = payload.get("slate_date")
    try:
        date.fromisoformat(str(day))
    except (TypeError, ValueError):
        return None
    compact = {
        "slate_date": day,
        "generated_at": payload.get("generated_at"),
        "archived_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "season": payload.get("season"),
        "season_fraction": payload.get("season_fraction"),
        "fantasy_generated_at": payload.get("fantasy_generated_at"),
        "n_games": payload.get("n_games"),
        "n_players": payload.get("n_players"),
        "games": [{k: (g or {}).get(k) for k in _ARCHIVE_GAME_FIELDS}
                  for g in (payload.get("games") or [])],
        "players": [{k: (p or {}).get(k) for k in _ARCHIVE_PLAYER_FIELDS}
                    for p in (payload.get("players") or [])],
    }
    d = Path(archive_dir) if archive_dir is not None else ARCHIVE_DIR
    d.mkdir(parents=True, exist_ok=True)
    blob = fe._json_blob(compact, "dfs_history")
    if blob is None:
        return None
    p = d / f"{day}.json"
    p.write_text(blob, encoding="utf-8")
    _prune_archive(d, today=str(day))
    return p


def _prune_archive(archive_dir: Path, *, today: str,
                   keep_days: int = _ARCHIVE_KEEP_DAYS) -> int:
    """Delete archive files older than `keep_days` before `today`; returns the
    count removed. Non-date filenames are left alone rather than guessed at."""
    try:
        cutoff = (date.fromisoformat(today)
                  - timedelta(days=keep_days)).isoformat()
    except (TypeError, ValueError):
        return 0
    n = 0
    for f in sorted(Path(archive_dir).glob("*.json")):
        try:
            date.fromisoformat(f.stem)
        except ValueError:
            continue
        if f.stem < cutoff:
            try:
                f.unlink()
                n += 1
            except OSError:
                _log.warning("dfs: could not prune archive file %s", f)
    return n


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
    # A build that RAISED is the same publish decision as a build we refused:
    # there is no new board, and whatever is on disk is about to be served. It
    # earns a row here so the crash path cannot silently skip the stamping the
    # other two get (2026-08-07: the except below returned 0 without touching
    # the file, and /dfs/ served a two-day-old slate carrying no stale flag).
    "build_failed": ("today's build raised before it produced a payload"),
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
            out_path: Path | None = None,
            archive_dir: Path | None = None) -> int:
    """DAILY best-effort build of data/dfs.json. Returns the player count of
    what is now SERVED (which is the previous payload's count on the keep paths
    below). Never raises: a build that raises is converted into a `build_failed`
    payload and routed through the same publish decision as a build we refused,
    so the board that stays on disk is STAMPED rather than served as today's.

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
    path = Path(out_path) if out_path else OUT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # the roster walk belongs to the EXPORT path, not to the pure
        # builder: build_payload takes its data from its caller.
        payload = build_payload(day=day, games=games,
                                active_ids=_active_roster_ids())
    except Exception:
        _log.exception("dfs: payload build failed - continuing")
        # NOT a bare `return 0`. Returning here left the previous payload on
        # disk untouched, which means unstamped, which means the page renders an
        # older slate at full confidence: the exact failure the keep-previous
        # rule below was written to prevent, reached by the one route that
        # skipped it. Falling through routes the crash through that rule, so the
        # carried board gets the stale stamp and the bound, and a carry past the
        # bound publishes the honest empty state instead.
        payload = _empty(
            day or date.today().isoformat(), None,
            "Today's slate build did not finish, so no new board was published. "
            "The next daily run rebuilds it.",
            kind="build_failed")

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
    # Archive the slate as served (best-effort, never the reason a publish
    # fails). _archive_slate itself refuses empty and refused payloads, so
    # this line is safe on every path that reaches the write above; the
    # keep-previous branch returned earlier and re-archives nothing, because
    # its board was archived on its own day.
    try:
        _archive_slate(payload, archive_dir)
    except Exception:
        _log.exception("dfs: slate archive failed - continuing")
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
