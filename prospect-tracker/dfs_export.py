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
    missing team is neutral rather than absent."""
    out = {}
    for org, row in (teams_ctx or {}).items():
        out[org] = {
            "offense_plus": (row or {}).get("offense_plus") or 100,
            "bullpen_plus": (row or {}).get("bullpen_plus") or 100,
        }
    return out


def _empty(day: str, season, reason: str, extra: dict | None = None) -> dict:
    """A VALID payload that carries its own reason for being empty. The page
    renders this loudly; it never renders a blank board."""
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


def build_payload(*, day: str | None = None, fantasy: dict | None = None,
                  games: list | None = None, positions: dict | None = None,
                  park: dict | None = None, teams_ctx: dict | None = None) -> dict:
    """Assemble data/dfs.json. Every input is injectable so the whole thing
    runs offline in a test with a stubbed schedule.

    `games` is the fantasy_schedule.fetch_probables shape. Passing [] is the
    empty-slate case and is a supported, tested path, not an error."""
    day = day or date.today().isoformat()
    if fantasy is None:
        fantasy = fe._load_json("fantasy.json")
    if not isinstance(fantasy, dict) or not fantasy.get("players"):
        return _empty(day, None,
                      "The rest-of-season projection corpus has not been built yet. "
                      "The nightly build seeds it.")
    season = fantasy.get("season")
    frac = float(fantasy.get("season_fraction") or 0.0)
    rem_games = int(round(_SEASON_GAMES * max(0.0, 1.0 - frac)))
    if rem_games <= 0:
        return _empty(day, season,
                      "The regular season is over. Daily slates come back on "
                      "opening day.")
    if games is None:
        s, e = fsched.date_window(1, date.fromisoformat(day))
        games = fsched.fetch_probables(s, e)
    if not games:
        return _empty(day, season, f"No MLB games scheduled for {day}.")

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
    for p in fantasy["players"]:
        pool[(p.get("mlbam"), p.get("side"))] = p
        if p.get("side") == "hit" and p.get("team"):
            hitters_by_team.setdefault(p["team"], []).append(p)

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
            opp_bp = (ctx.get(opp_obj.get("org")) or {}).get("bullpen_plus") or 100
            # Opponent run prevention, innings weighted: the announced starter
            # covers 5.4 of 9 innings, the bullpen the rest. No starter posted
            # yet means the bullpen number carries the whole game rather than a
            # guess at who takes the ball.
            if opp_sem:
                opp_pitch = _SP_IP_SHARE * float(opp_sem) + (1 - _SP_IP_SHARE) * float(opp_bp)
            else:
                opp_pitch = float(opp_bp)
            hit_mult = _clamp((100.0 / opp_pitch) * pf, *_HIT_MULT_CLAMP)
            opp_off = (ctx.get(opp_obj.get("org")) or {}).get("offense_plus") or 100
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
                "ctx": {"opp_off": s["opp_off"], "park_run_pf": round(pf, 3),
                        "park_source": park_source, "mult": s["allow_mult"]},
                "est": ["h", "er", "w", "qs", "matchup", "park"],
            })

        # --- hitters: everyone in the pool whose club is on the slate -------
        for me in ("home", "away"):
            s = sides[me]
            org = s.get("org")
            if not org:
                continue
            for rec in hitters_by_team.get(org, []):
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
                            "park_run_pf": round(pf, 3), "park_source": park_source,
                            "mult": s["hit_mult"]},
                    "est": ["r", "rbi", "sb", "start_rate", "matchup", "park"],
                })

    rows = sorted(by_id.values(),
                  key=lambda r: -(r["pts"]["dk"] if r.get("pts") else -1e9))
    payload = _empty(day, season, None)
    payload.update({
        "n_games": len(slate_games),
        "n_players": len(rows),
        "games": slate_games,
        "players": rows,
        "remaining_team_games": rem_games,
        "season_fraction": round(frac, 3),
        "fantasy_generated_at": fantasy.get("generated_at"),
        "unprojected": unprojected[:40],
        "anchors": {"pa_per_start": _PA_PER_START, "sp_ip_share": round(_SP_IP_SHARE, 3),
                    "season_games": _SEASON_GAMES, "elig_min_games": _MIN_ELIG_GAMES},
    })
    if not rows:
        payload["empty_reason"] = (
            f"{len(slate_games)} games are on the slate for {day}, but no probable "
            "starter or hitter on it has a rest-of-season projection yet.")
    return payload


def refresh(log=print, *, day: str | None = None, games: list | None = None,
            out_path: Path | None = None) -> int:
    """DAILY best-effort build of data/dfs.json. Returns the priced player
    count. Never raises: a failure writes nothing and returns 0, and the page
    keeps serving yesterday's payload with its own date stamp on it."""
    try:
        payload = build_payload(day=day, games=games)
    except Exception:
        _log.exception("dfs: payload build failed - continuing")
        return 0
    path = Path(out_path) if out_path else OUT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    if callable(log):
        if payload.get("empty_reason"):
            log(f"dfs: empty slate for {payload['slate_date']} - {payload['empty_reason']}")
        else:
            log(f"dfs: {payload['n_players']} players priced across "
                f"{payload['n_games']} games ({payload['slate_date']})")
    return int(payload.get("n_players") or 0)


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
