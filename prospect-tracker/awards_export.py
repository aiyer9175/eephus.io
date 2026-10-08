# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Awards board exporter (AWARDS_3_EXPORTER; AWARDS_PLAN 4.1 'Files', 4.4
'data/awards.json (and each data/awards_<S>.json)', 4.5
'data/awards_candidates_<S>.json', 4.7 'The freeze', 4.8 'Refresh', 4.9
'Health', 4.10 'Registry and glossary', 4.11 'Past seasons and the writers').

WHAT IT WRITES. export() writes, at data/ depth one (both deploy consumers ship
depth-one data files only, so a season subfolder would 404 on the public site):

  awards.json                  the current season (live, or frozen once
                               --freeze has run) plus the seasons index
                               (2021 to the current season) and the
                               vote_table (2011 on, computed_after_the_fact)
  awards_<S>.json              a closed season, written ONCE and never
                               rewritten (byte-stable, the mgmt shard rule)
  awards_candidates_<S>.json   My Ballot's pools for every season in the
                               selector (Manager ids are club codes)
  awards_eval.json             the registry row's artifact: reconciliation
                               counts per invariant, the rookie-winner check
                               when the winners file exists, the freeze hashes
                               copied from data/_labs/awards/freeze_log.json

THE FLAG. While awards_core.AWARDS_LIVE is False every one of those files goes
under .cache/awards/preview/ instead (same names, depth one there), so no
served file moves. The one exception is the freeze path (--freeze S), which
writes exactly data/_labs/awards/frozen_<S>.json once and appends its sha256 to
data/_labs/awards/freeze_log.json, with the flag either way; data/_labs/ ships
in neither deploy consumer.

THE RACE (AWARDS_5_RACE; AWARDS_PLAN 4.6). Each season's race block is copied
from the tracked data/_labs/awards/race_<S>.json (mode wpa_order, written once
on the dev box by tools/awards_race.py for 2018, 2019 and 2021 to 2026). From
RULE_PLACE_FIRST (2027) on, a season with no tracked file gets a rule_place
block built from the nightly vintages: from Opening Day each successful run
writes .cache/awards_vintages/<date>.json (the Top 10 per award and league on
the rule; the first write of a date wins; under the preview's awards_vintages
folder while the flag is False), never a tracked file.

THE ONE NETWORK READ. war_source.stint_frame(side, provider=<display provider>)
downloads Baseball-Reference's war_daily file through pybaseball (batting goes
through pybaseball's disk cache; pitching is a live download in every process,
war_source.stint_frame's docstring). It is read once per side per process
(_stint_frame below, memoised the way war_board_export._stint_frame is), on the
DISPLAY provider bullpen_export.served_war_basis()['war_provider'] passed
explicitly, never war_source's training default. A failed download serves the
last-good .cache/war_daily/<side>.parquet and war_source.served_stale() names
the side; the exporter then refuses (4.9). Every other input is a served
artifact or a .cache payload read by path: nothing else here fetches.

REFUSAL (4.9). On any of these the exporter writes nothing, keeps yesterday's
files and returns ok False with the reason: the eWAR board is stale
(ewar_vintage.stale); served_stale() names a side; a Top-25 row breaks I1 (a
side's league shares miss the provider artifact's side total by more than
0.005, or the summed shares print differently from the board's players[].war);
the projection bundle and the realized side are on different WAR providers
(next_rise / next_drop); the standings cache is older than two days in season;
fewer than 30 clubs; no rookie block for the season; a frozen record whose
sha256 differs from freeze_log.json's; a payload over its size line.

THE FRAME GUARDS (AWARDS_PLAN F10 to F12, I7). Prospect rows are handed to
awards_core only for debut cohorts awards_core.prospect_pool_open() admits
(debut seasons before min(RESERVED_LV) today), so no eFV at debut is paired
with a season for a reserved cohort, not even in memory. proj_above and
proj_below get no rows at all while awards_core.proj_blocked_on(S) is set
(2026 is dark, AW-Q3), so no realized-minus-projected number is computed on a
label season whose registered looks are open. Nothing here groups a realized
number by FV, eFV or consensus band or reads the realized FV anchor.

THE WINNERS FILE. data/_labs/awards/award_winners.json (AWARDS_4, written by
tools/award_winners_ingest.py from MLB's StatsAPI) is read when present, in this
shape: {"fetched_at", "source", "copyright", "seasons": {"<S>": {"<StatsAPI award
id>": {"person_id", "name", "team_id", "team_code", "date", "votes"?,
"finalists"?, "finalists_announced"?}}}}, the award ids of STATSAPI_AWARD_IDS.
winner_rows() turns it into one row per award, league and season; a season in the
file is a closed one, so its writers' block is status final. Manager recipients
are people; the comparison joins on the club through the team id. The rule's
place of the writers' 1st is read on the rule's ballot (the BBWAA length,
awards_core.BALLOT_RULES): past it, or off the pool, the place is null, which the
page prints as outside the rule's ballot.

THE PIPELINE. run_monthly's daily step d10h and monthly step 6b7f call
export() through run_monthly._export_awards_board, which files the health row
awards_export (watched only once the flag is True).

Run: python awards_export.py [--season S] [--freeze S]
"""
from __future__ import annotations

import argparse
import bisect
import copy
import datetime as _dt
import hashlib
import json
import math
import os
import sys
from pathlib import Path

import awards_core as A

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CACHE = ROOT / ".cache"
LABS = DATA / "_labs" / "awards"
PREVIEW = CACHE / "awards" / "preview"
#: The race from 2027 (AWARDS_PLAN 4.6, mode rule_place): from Opening Day of this season
#: the nightly writes one vintage a date (the Top VINTAGE_TOP per award and league on the
#: rule, first write of a date wins) under VINTAGES, or under the preview's own
#: awards_vintages folder while the flag is False, and builds the race block from them on
#: the machine that runs it. Nothing tracked is written by the nightly: the box's nightly
#: checkout would revert it; tools/awards_race.py writes the tracked race_<S>.json once on
#: the dev box after the season closes.
RULE_PLACE_FIRST = 2027
VINTAGE_TOP = 10
VINTAGES = CACHE / "awards_vintages"
RACE_RULE_LABEL = ("Place on the selection rule among every eligible player, week by week, "
                   "from the site's nightly records.")
RACE_RULE_PRODUCER = (".cache/awards_vintages/<date>.json top[<award>_<league>], the "
                      "exporter's nightly Top 10 on the rule")

SCHEMA = 1
PRODUCED_BY = "awards_export.py"

#: The season selector's first season (AWARDS_PLAN 4.11) and the vote table's.
SELECTOR_FIRST = 2021
VOTE_FIRST = 2011
#: I1 tolerance on a side's league shares against the artifact's side total,
#: and how deep down each ballot the refusal check reads (AWARDS_PLAN 4.9).
I1_TOL = 0.005
I1_TOP = 25
#: The standings cache's age line in season (AWARDS_PLAN 4.9).
STANDINGS_MAX_AGE_DAYS = 2
MIN_CLUBS = 30
#: Size lines (AWARDS_PLAN 6 I11): bytes, raw.
AWARDS_MAX_BYTES = 400_000
CANDIDATES_MAX_BYTES = 300_000
#: A lamp ladder draws at most this many lamps (AWARDS_PLAN 5.2).
LAMP_MAX = 60
#: A lit superlative lists three to five rows (AWARDS_PLAN 6, I11).
SL_MIN_ROWS = 3
#: The full ranking: every row of a pool, past the BBWAA length.
_ALL = 10 ** 6
#: Two-way flag on a candidate row: both sides at the war board's qualified cut.
TWO_WAY_MIN_PA = A.ROY_MIN_PA
TWO_WAY_MIN_IP = A.ROY_MIN_IP
#: The candidate pools' line (AWARDS_PLAN 4.5 "every in-league player with a
#: line"): the war board's own qualified rule, in-league PA >= 100 or IP >= 30
#: (awards_core pins both to war_board_export.QUAL_MIN_PA and QUAL_MIN_IP).
#: Measured 2026-10-07 on the 2026 files: every stint-frame row makes the MVP
#: pool 786 AL and 794 NL rows and the file 342 KB, over its 300 KB line; at
#: this rule the pools are 461 and 465 and the file is under 200 KB. The rows
#: this drops are cameos under both cuts; the rule is printed on the file.
CANDIDATE_MIN_PA = A.ROY_MIN_PA
CANDIDATE_MIN_IP = A.ROY_MIN_IP

LEAGUE_IDS = {103: "AL", 104: "NL"}
#: Franchise codes the stint frame used before today's codes; canonical_org
#: leaves these as they are, so the Manager join maps them here.
HISTORIC_CLUBS = {"FLA": "MIA", "ANA": "LAA", "CAL": "LAA", "MON": "WSN", "TBD": "TBR"}
#: The display provider's artifact, whose side totals I1 reads.
PROVIDER_ARTIFACT = {"ewar_v2": "ewar.json"}
#: Decision families the Manager compare strip prints, one row each, never summed.
MGMT_FAMILIES = ("pitching_change", "pinch_hit", "pinch_run", "intentional_walk", "bunt", "steal")
#: The 60-game season's note on the vote table and the selector.
SHORT_SEASON_NOTE = "a {g}-game season"

WRITERS_PENDING = "Writers' vote: not announced yet."
#: StatsAPI award id -> (award, league), the ids of tools/award_winners_ingest.py.
STATSAPI_AWARD_IDS = {
    "ALMVP": ("MVP", "AL"), "NLMVP": ("MVP", "NL"),
    "ALCY": ("CY", "AL"), "NLCY": ("CY", "NL"),
    "ALROY": ("ROY", "AL"), "NLROY": ("ROY", "NL"),
    "ALMOY": ("MOY", "AL"), "NLMOY": ("MOY", "NL"),
}


class AwardsRefusal(RuntimeError):
    """The exporter declines to publish; the previous files stand."""


# --- the one network read ------------------------------------------------------

_FRAME_CACHE: dict = {}


def _stint_frame(side: str, provider: str):
    """war_source.stint_frame(side, provider=provider), read ONCE per process
    and side (the exception is memoised too, so a dead frame is not retried).
    Tests fill _FRAME_CACHE through inject_frames() and never touch the network."""
    key = (side, provider)
    if key not in _FRAME_CACHE:
        try:
            import war_source
            _FRAME_CACHE[key] = (war_source.stint_frame(side, provider=provider), None)
        except Exception as e:   # noqa: BLE001 - the caller refuses on it
            _FRAME_CACHE[key] = (None, e)
    df, err = _FRAME_CACHE[key]
    if err is not None:
        raise err
    return df


def inject_frames(frames: dict, provider: str) -> None:
    """The test seam: {"bat": rows, "pit": rows} served as the memoised frames."""
    for side in ("bat", "pit"):
        _FRAME_CACHE[(side, provider)] = (frames.get(side) or [], None)


def reset_frames() -> None:
    _FRAME_CACHE.clear()


def _served_stale() -> dict:
    try:
        import war_source
        return dict(war_source.served_stale() or {})
    except Exception:   # noqa: BLE001 - a missing module serves nothing stale
        return {}


def _display_provider() -> str:
    return A.display_war_provider()


# --- small helpers -----------------------------------------------------------------

_KEEP_COLS = ("name_common", "age", "mlb_ID", "year_ID", "team_ID", "stint_ID", "lg_ID",
              "PA", "IPouts", "WAR")


def _season_records(frame, seasons: set) -> dict:
    """{season: [records]} of a stint frame (a DataFrame or a list of dicts)."""
    out: dict = {}
    if frame is None:
        return out
    if hasattr(frame, "loc"):
        sub = frame[frame["year_ID"].isin(sorted(seasons))]
        cols = [c for c in _KEEP_COLS if c in sub.columns]
        recs = sub[cols].to_dict("records")
    else:
        recs = [dict(r) for r in frame]
    for r in recs:
        y = A._num(r.get("year_ID"))
        if y is None or int(y) not in seasons:
            continue
        out.setdefault(int(y), []).append(r)
    return out


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _dump(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _write_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)


def _pctl(values: list, q: float):
    """The q-th percentile of `values`, linear between order statistics."""
    vals = sorted(values)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * q / 100.0
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def pool_percentile(v, pool: list):
    """Mid-rank percentile of v inside `pool` (ties shared), 1 dp: the
    awards_core.midrank_percentiles rule for one value."""
    if v is None or not pool:
        return None
    srt = sorted(pool)
    lo = bisect.bisect_left(srt, v)
    hi = bisect.bisect_right(srt, v)
    return round(100.0 * (lo + 0.5 * (hi - lo)) / len(srt), 1)


def _club(raw) -> str | None:
    c = A._club_code(raw)
    return HISTORIC_CLUBS.get(c, c) if c else None


def _sha(raw: bytes, n: int | None = None) -> str:
    h = hashlib.sha256(raw).hexdigest()
    return h if n is None else h[:n]


# --- inputs ---------------------------------------------------------------------------

class _Inputs:
    """Every file the exporter reads, by path, memoised, with its stamp."""

    def __init__(self, data_dir: Path, cache_dir: Path, labs_dir: Path, model_dir: Path):
        self.data, self.cache, self.labs, self.model = data_dir, cache_dir, labs_dir, model_dir
        self._memo: dict = {}
        self.stamps: dict = {}

    def _read(self, label: str, path: Path, required: bool):
        if label in self._memo:
            return self._memo[label]
        if not path.exists():
            if required:
                raise AwardsRefusal(f"missing input {label}")
            self._memo[label] = None
            return None
        raw = path.read_bytes()
        doc = json.loads(raw.decode("utf-8"))
        st = {"generated_at": None, "as_of": None, "sha1_12": hashlib.sha1(raw).hexdigest()[:12]}
        if isinstance(doc, dict):
            st["generated_at"] = doc.get("generated_at") or doc.get("built_at")
            st["as_of"] = doc.get("as_of")
        self.stamps[label] = st
        self._memo[label] = doc
        return doc

    def data_json(self, name: str, required: bool = True):
        return self._read(f"data/{name}", self.data / name, required)

    def cache_json(self, name: str, required: bool = True):
        return self._read(f".cache/{name}", self.cache / name, required)

    def labs_json(self, name: str, required: bool = False):
        return self._read(f"data/_labs/awards/{name}", self.labs / name, required)

    def model_meta(self):
        return self._read("model/proj_lgbm/meta.json", self.model / "meta.json", False)


def _index(rows, key="mlbam") -> dict:
    out = {}
    for r in rows or []:
        k = r.get(key)
        if k is None:
            continue
        try:
            out.setdefault(int(k), r)
        except (TypeError, ValueError):
            continue
    return out


# --- the season world ---------------------------------------------------------------

class _Boards:
    """The per-season board rows the compare strips and superlatives copy from,
    with the producer string each copy names."""

    def __init__(self):
        self.hitters, self.starters, self.relievers, self.fielders = {}, {}, {}, {}
        self.lev_bat, self.lev_sp, self.war_players = {}, {}, {}
        self.src = {}
        self.current = False


def _boards(inp: _Inputs, season: int, board_season: int) -> _Boards:
    b = _Boards()
    if season == board_season:
        b.current = True
        b.hitters = _index(inp.data_json("hitter_leaderboards.json")["hitters"])
        b.starters = _index(inp.data_json("starter_leaderboards.json")["starters"])
        b.relievers = _index(inp.data_json("bullpen_leaderboards.json")["relievers"])
        b.fielders = _index(inp.data_json("defense_leaderboards.json")["fielders"])
        lev = inp.data_json("leverage_leaderboards.json")
        b.lev_bat, b.lev_sp = _index(lev.get("batters")), _index(lev.get("starters"))
        b.war_players = _index(inp.data_json("war_leaderboards.json")["players"])
        b.src = {"hitters": "hitter_leaderboards.json hitters[]",
                 "starters": "starter_leaderboards.json starters[]",
                 "relievers": "bullpen_leaderboards.json relievers[]",
                 "fielders": "defense_leaderboards.json fielders[]",
                 "lev_bat": "leverage_leaderboards.json batters[]",
                 "lev_sp": "leverage_leaderboards.json starters[]",
                 "war_players": "war_leaderboards.json players[]"}
        return b
    key = str(int(season))

    def _hist(name, block):
        doc = inp.data_json(name, required=False) or {}
        h = ((doc.get("history") or {}).get(key) or {})
        return _index(h.get(block))

    b.hitters = _hist("hitter_history.json", "hitters")
    b.starters = _hist("starter_history.json", "starters")
    b.relievers = _hist("bullpen_history.json", "relievers")
    b.fielders = _hist("defense_history.json", "fielders")
    b.lev_bat = _hist("leverage_history.json", "batters")
    b.lev_sp = _hist("leverage_history.json", "starters")
    b.src = {"hitters": f"hitter_history.json history[{key}].hitters[]",
             "starters": f"starter_history.json history[{key}].starters[]",
             "relievers": f"bullpen_history.json history[{key}].relievers[]",
             "fielders": f"defense_history.json history[{key}].fielders[]",
             "lev_bat": f"leverage_history.json history[{key}].batters[]",
             "lev_sp": f"leverage_history.json history[{key}].starters[]"}
    return b


class _Ctx:
    """The run: inputs, the display provider, the stint records by season."""

    def __init__(self, inp: _Inputs, provider: str, season: int, records: dict):
        self.inp, self.provider, self.season = inp, provider, season
        self.records = records
        self.ewar = inp.data_json("ewar.json")
        self.board = inp.data_json("war_leaderboards.json")
        self.board_season = int(self.board.get("season") or season)
        self.abbrev = {int(k): v for k, v in (inp.cache_json("team_abbrev_map.json") or {}).items()}
        self.rookies = inp.labs_json("rookies.json", required=False) or {}
        self.mgmt = inp.data_json("management_board.json", required=False) or {}
        self.proj = inp.data_json("mlb_projections.json", required=False) or {}
        self.registry_doc = inp.data_json("model_registry.json", required=False) or {}
        self.winners = inp.labs_json("award_winners.json", required=False)
        self.winner_list = winner_rows(self.winners)
        self._worlds: dict = {}
        #: The rule_place race (2027 on): where the nightly vintages live, and tonight's
        #: record before it is written (so the race block carries tonight's point).
        self.vintage_dir: Path | None = None
        self.pending_vintage: dict | None = None

    def rookie_block(self, season: int):
        for blk in self.rookies.get("seasons") or []:
            if int(blk.get("season") or 0) == int(season):
                return blk
        return None

    def world(self, season: int) -> dict:
        if season not in self._worlds:
            self._worlds[season] = _build_world(self, season)
        return self._worlds[season]


def _standings(ctx: _Ctx, season: int) -> dict:
    """{"clubs": [{club, league, w, l, gp, run_diff, team_id, name}], "copyright",
    "through"} from .cache/statsapi_standings_<S>.json."""
    doc = ctx.inp.cache_json(f"statsapi_standings_{int(season)}.json", required=False)
    if not doc:
        return {"clubs": [], "copyright": None, "through": None}
    clubs, latest = [], None
    for rec in doc.get("records") or []:
        lg = LEAGUE_IDS.get(int(((rec.get("league") or {}).get("id")) or 0))
        for t in rec.get("teamRecords") or []:
            tid = int((t.get("team") or {}).get("id") or 0)
            code = ctx.abbrev.get(tid)
            w = t.get("wins", (t.get("leagueRecord") or {}).get("wins"))
            l = t.get("losses", (t.get("leagueRecord") or {}).get("losses"))
            x = next((e for e in ((t.get("records") or {}).get("expectedRecords") or [])
                      if e.get("type") == "xWinLoss"), None)
            clubs.append({"club": code, "league": lg, "w": w, "l": l,
                          "gp": t.get("gamesPlayed"), "run_diff": t.get("runDifferential"),
                          "team_id": tid, "name": (t.get("team") or {}).get("name"),
                          "x_w": (x or {}).get("wins"), "x_l": (x or {}).get("losses")})
            lu = str(t.get("lastUpdated") or "")[:10]
            if lu and (latest is None or lu > latest):
                latest = lu
    return {"clubs": clubs, "copyright": doc.get("copyright"), "through": latest}


def _build_world(ctx: _Ctx, season: int) -> dict:
    S = int(season)
    recs = {side: ctx.records.get(side, {}).get(S, []) for side in ("bat", "pit")}
    rows = A.league_split(recs, season=S, war_provider=ctx.provider)
    b = _boards(ctx.inp, S, ctx.board_season)
    names = {}
    for src in (b.war_players, b.hitters, b.starters, b.relievers, b.fielders):
        for k, r in src.items():
            if r.get("name") and k not in names:
                names[k] = r["name"]
    for r in rows:
        if r["mlbam"] in names:
            r["name"] = names[r["mlbam"]]
    pos = {}
    for r in rows:
        m = r["mlbam"]
        if m in b.war_players and b.war_players[m].get("pos"):
            pos[m] = b.war_players[m]["pos"]
        elif m in b.fielders and b.fielders[m].get("pos"):
            pos[m] = b.fielders[m]["pos"]
        elif (r.get("ip") or 0) > 0 and (r.get("pa") or 0) < TWO_WAY_MIN_PA:
            pos[m] = "P"
    wpa = {}
    for m in {r["mlbam"] for r in rows}:
        v = 0.0
        for src in (b.lev_bat, b.lev_sp):
            if m in src and A._num(src[m].get("wpa")) is not None:
                v += float(src[m]["wpa"])
        if m not in b.lev_sp and m in b.relievers and A._num(b.relievers[m].get("wpa")) is not None:
            v += float(b.relievers[m]["wpa"])
        wpa[m] = v
    skill_raw = {}
    for m in {r["mlbam"] for r in rows}:
        if m in b.starters:
            skill_raw[m] = b.starters[m].get("sem_plus_raw", b.starters[m].get("sem_plus"))
        elif m in b.relievers:
            skill_raw[m] = b.relievers[m].get("rem_plus_raw", b.relievers[m].get("rem_plus"))
    st = _standings(ctx, S)
    return {"season": S, "rows": rows, "boards": b, "pos": pos, "wpa": wpa,
            "skill_raw": skill_raw, "standings": st,
            "ewar_side": _ewar_sides(ctx, S)}


def _ewar_sides(ctx: _Ctx, S: int) -> dict:
    out = {}
    key = str(S)
    for mid, by in (ctx.ewar.get("players") or {}).items():
        blk = by.get(key)
        if blk:
            out[int(mid)] = blk
    return out


# --- Manager inputs --------------------------------------------------------------------

def _manager_inputs(ctx: _Ctx, w: dict):
    """(standings, team_outlook, war_earned, sources) for season S. The current
    season reads the served team_outlook and the war board's teams[].war_earned;
    a past season reads StatsAPI's xWinLoss from the standings cache and folds
    the stint frame by club (unrounded)."""
    S = w["season"]
    standings = [c for c in w["standings"]["clubs"] if c.get("club") and c.get("league")]
    if S == ctx.board_season:
        outlook = ctx.proj.get("team_outlook") or []
        earned = ctx.board.get("teams") or []
        src = {"pythag": "mlb_projections.json team_outlook[].current.pythagPct x gamesPlayed",
               "earned": "war_leaderboards.json teams[].war_earned"}
    else:
        outlook = []
        for c in standings:
            xw, xl = A._num(c.get("x_w")), A._num(c.get("x_l"))
            if xw is None or xl is None or xw + xl <= 0:
                continue
            outlook.append({"team": c["club"], "current": {
                "pythagPct": round(xw / (xw + xl), 3), "gamesPlayed": c.get("gp")}})
        earned_map: dict = {}
        for side in ("bat", "pit"):
            for rec in ctx.records.get(side, {}).get(S, []):
                club = _club(rec.get("team_ID"))
                war = A._num(rec.get("WAR"))
                if club and war is not None:
                    earned_map[club] = earned_map.get(club, 0.0) + war
        earned = earned_map
        src = {"pythag": f"statsapi_standings_{S}.json expectedRecords xWinLoss",
               "earned": "war_source.stint_frame WAR summed by club"}
    stand = [dict(c, club=_club(c["club"])) for c in standings]
    out_outlook = [dict(t, team=_club(t.get("team"))) for t in outlook]
    if isinstance(earned, dict):
        earned = {_club(k): v for k, v in earned.items()}
    else:
        earned = [dict(t, team=_club(t.get("team"))) for t in earned]
    return stand, out_outlook, earned, src


# --- ballots ----------------------------------------------------------------------------

def _ballots(ctx: _Ctx, w: dict, award: str, lg: str, n=None) -> dict:
    S = w["season"]
    if award == "MVP":
        return A.mvp_ballot(w["rows"], lg, S, wpa=w["wpa"], pos=w["pos"], n=n)
    if award == "CY":
        return A.cy_young_ballot(w["rows"], lg, S, skill_raw=w["skill_raw"], pos=w["pos"], n=n)
    if award == "ROY":
        blk = ctx.rookie_block(S)
        if blk is None:
            return None
        return A.rookie_ballot(w["rows"], lg, S, rookies=blk, wpa=w["wpa"], pos=w["pos"], n=n)
    if award == "MOY":
        stand, outlook, earned, _ = _manager_inputs(ctx, w)
        if not stand:
            return None
        return A.manager_ballot(stand, outlook, earned, lg, S, war_provider=ctx.provider, n=n)
    raise ValueError(award)


def _row_key(r: dict):
    return r.get("mlbam") if r.get("mlbam") is not None else "c" + str(r.get("club") or "").lower()


# --- compare metrics ----------------------------------------------------------------------

def _get(src: dict, m, field):
    r = src.get(m)
    if r is None:
        return None, None
    v = r.get(field)
    return (None, None) if v is None else (v, field)


class _Metric:
    def __init__(self, key, label, family, registry, decimals, getter, producer, current_only=False):
        self.key, self.label, self.family, self.registry = key, label, family, registry
        self.decimals, self.getter, self.producer = decimals, getter, producer
        self.current_only = current_only


def _player_metrics(award: str, unit: str) -> list:
    """The compare columns of a player award (AWARDS_PLAN 5.3). A getter returns
    (value, source name) with the value COPIED from its producer field, or
    (None, None)."""

    def score(w, r):
        return A.score_display(r["score"]), "score"

    def board(attr, field):
        def g(w, r):
            b = w["boards"]
            v, f = _get(getattr(b, attr), r["mlbam"], field)
            return (v, f"{b.src.get(attr)}.{f}") if v is not None else (None, None)
        return g

    def first(*getters):
        def g(w, r):
            for gt in getters:
                v, s = gt(w, r)
                if v is not None:
                    return v, s
            return None, None
        return g

    def exposure(field):
        def g(w, r):
            b = w["boards"]
            if b.current:
                v, f = _get(b.war_players, r["mlbam"], field)
                if v is not None:
                    return v, f"{b.src['war_players']}.{f}"
                return None, None
            v = r.get(field)
            if v in (None, 0, 0.0):
                return None, None
            return v, ("war_source.stint_frame PA (in-league)" if field == "pa"
                       else "war_source.stint_frame IPouts / 3 (in-league)")
        return g

    def bwp(w, r):
        blk = w["ewar_side"].get(r["mlbam"]) or {}
        v = blk.get("bwp")
        return (v, f"ewar.json players[].{w['season']}.bwp") if v is not None else (None, None)

    def age(w, r):
        v = r.get("age")
        return (v, "war_source.stint_frame age") if v is not None else (None, None)

    M = _Metric
    hem = M("hem_plus", "HEM+", "ratio", "hem_plus", 0, board("hitters", "hem_plus"),
            "hitter board hem_plus")
    sem = M("sem_plus", "SEM+", "run", "sem_plus", 0, board("starters", "sem_plus"),
            "starter board sem_plus")
    rem = M("rem_plus", "REM+", "run", "rem_plus", 0, board("relievers", "rem_plus"),
            "bullpen board rem_plus")
    dem = M("dem_plus", "DEM+", "z", "dem_plus", 0, board("fielders", "dem_plus"),
            "defense board dem_plus")
    pa = M("pa", "PA", None, None, 0, exposure("pa"), "plate appearances")
    ip = M("ip", "IP", None, None, 1, exposure("ip"), "innings pitched")
    sc = M("score", unit, "war", A.SELECTION_REGISTRY, 1, score, "the rule's score")
    if award == "MVP":
        return [sc, hem, sem, rem, dem,
                M("wrc_plus", "wRC+", "wrc", None, 0, board("hitters", "wrc_plus"),
                  "hitter board wrc_plus (FanGraphs)"),
                M("xhem_plus", "xHEM+", "ratio", "xhem_plus", 0, board("hitters", "xhem_plus"),
                  "hitter board xhem_plus", current_only=True),
                M("wpa", "WPA", None, "leverage_board", 2,
                  first(board("lev_bat", "wpa"), board("lev_sp", "wpa"), board("relievers", "wpa")),
                  "leverage and bullpen boards wpa"),
                pa, ip]
    if award == "CY":
        return [sc, sem, rem,
                M("xsem_plus", "xSEM+", "run", "xsem_plus", 0, board("starters", "xsem_plus"),
                  "starter board xsem_plus", current_only=True),
                ip,
                M("era", "ERA", "fip", None, 2, first(board("starters", "era"), board("relievers", "era")),
                  "starter or bullpen board era"),
                M("fip", "FIP", "fip", None, 2, first(board("starters", "fip"), board("relievers", "fip")),
                  "starter or bullpen board fip"),
                M("bwp", "Baseball-Reference pitching WAR (runs allowed)", None, None, 1, bwp,
                  "ewar.json bwp"),
                M("wpa", "WPA", None, "leverage_board", 2,
                  first(board("lev_sp", "wpa"), board("relievers", "wpa")),
                  "leverage starters or bullpen relievers wpa"),
                M("gmli", "gmLI", None, "leverage_board", 2, board("relievers", "gmli"),
                  "bullpen board gmli")]
    if award == "ROY":
        return [sc, hem, sem, rem, dem, pa, ip,
                M("age", "Age", None, None, 0, age, "war_daily age")]
    raise ValueError(award)


def _club_metrics(ctx: _Ctx, w: dict) -> list:
    S = w["season"]
    rows = {}
    for r in ((ctx.mgmt.get("clubs") or {}).get("rows") or []):
        if int(r.get("season") or 0) == S:
            rows[_club(r.get("club"))] = r
    floors = ((ctx.mgmt.get("clubs") or {}).get("floors") or {})
    st = {_club(c["club"]): c for c in w["standings"]["clubs"] if c.get("club")}
    std_src = f"statsapi_standings_{S}.json"

    def stand(field, name):
        def g(w_, r):
            c = st.get(r["club"]) or {}
            v = c.get(field)
            return (v, f"{std_src} teamRecords[].{name}") if v is not None else (None, None)
        return g

    def part(key):
        def g(w_, r):
            return A.score_display(r["parts"][key]), "score part"
        return g

    def fam(f):
        def g(w_, r):
            row = rows.get(r["club"])
            if not row:
                return None, None
            n = A._num(row.get(f"n_{f}")) or 0.0
            if n < float(floors.get(f) or 0):
                return None, None
            v = row.get(f"mwpa_{f}")
            return (v, f"management_board.json clubs.rows[].mwpa_{f}") if v is not None else (None, None)
        return g

    M = _Metric
    out = [M("w", "W", None, None, 0, stand("w", "wins"), "standings wins"),
           M("score", "Wins above the club's earned WAR", None, A.SELECTION_REGISTRY, 1,
             lambda w_, r: (A.score_display(r["score"]), "score"), "the rule's score"),
           M("sequencing", "Wins minus Pythagorean wins", None, None, 1, part("sequencing"),
             "the score's first part"),
           M("runs_vs_player_value", "Pythagorean wins minus the earned-WAR baseline", None, None, 1,
             part("runs_vs_player_value"), "the score's second part"),
           M("run_diff", "Run differential", None, None, 0, stand("run_diff", "runDifferential"),
             "standings runDifferential")]
    if rows:
        for f in MGMT_FAMILIES:
            out.append(M(f"mwpa_{f}", f"Realized value: {f.replace('_', ' ')}", None,
                         "mgmt_decision_ledger", 2, fam(f), f"management_board mwpa_{f}"))
    return out


def _compare(ctx: _Ctx, w: dict, award: str, top: list, pool: list) -> dict:
    unit = "wins" if award == "MOY" else A.war_unit_label(ctx.provider)
    metrics = _club_metrics(ctx, w) if award == "MOY" else _player_metrics(award, unit)
    top3 = top[:3]
    out = []
    for m in metrics:
        if m.current_only and not w["boards"].current:
            continue
        got = [m.getter(w, r) for r in top3]
        if all(v is None for v, _ in got):
            continue
        if m.key == "score":
            pool_vals = [float(r["score"]) for r in pool]
            exact = [float(r["score"]) for r in top3]
        elif m.key in ("sequencing", "runs_vs_player_value"):
            pool_vals = [float(r["parts"][m.key]) for r in pool]
            exact = [float(r["parts"][m.key]) for r in top3]
        else:
            pool_vals = []
            for r in pool:
                v, _ = m.getter(w, r)
                if A._num(v) is not None:
                    pool_vals.append(float(v))
            exact = [A._num(v) for v, _ in got]
        p1, p99 = _pctl(pool_vals, 1), _pctl(pool_vals, 99)
        out.append({
            "key": m.key, "label": m.label, "family": m.family, "producer": m.producer,
            "registry": m.registry,
            "p1": None if p1 is None else round(p1, 4),
            "p99": None if p99 is None else round(p99, 4),
            "values": [v for v, _ in got],
            "sources": [s for _, s in got],
            "pct": [pool_percentile(e, pool_vals) for e in exact],
            "decimals": m.decimals, "n_pool": len(pool_vals)})
    return {"metrics": out}


# --- one award-league card ----------------------------------------------------------------

def _player_key_map(ctx: _Ctx) -> dict:
    if not hasattr(ctx, "_pk"):
        deb = ctx.inp.data_json("debuts_lite.json", required=False) or []
        rows = deb if isinstance(deb, list) else (deb.get("rows") or deb.get("debuts") or [])
        ctx._pk = {}
        for r in rows:
            m = A._num(r.get("mlbam_id"))
            if m is not None and r.get("player_key"):
                ctx._pk.setdefault(int(m), r)
    return ctx._pk


def _decorate(ctx: _Ctx, w: dict, award: str, rows: list) -> list:
    pk = _player_key_map(ctx)
    teams = {c.get("club"): c for c in w["standings"]["clubs"]}
    out = []
    for r in rows:
        r = copy.deepcopy(r)
        if award == "MOY":
            nm = next((c.get("name") for c in w["standings"]["clubs"] if _club(c.get("club")) == r["club"]), None)
            r["club_name"] = nm
        else:
            p = pk.get(int(r["mlbam"]))
            if p and p.get("player_key"):
                r["links"]["prospx"] = f"/prospx/#player={p['player_key']}"
            r["split_label"] = A.split_label(r, ctx.provider)
        out.append(r)
    del teams
    return out


def winner_rows(doc) -> list:
    """The winners file as rows: [{"award", "league", "season", "winner": {"person_id",
    "name", "team_id", "team_code"}, "finalists": [...], "finalists_announced",
    "announced"}], one per award id and season, seasons ascending."""
    out = []
    for s_key, by_id in sorted(((doc or {}).get("seasons") or {}).items(), key=lambda kv: int(kv[0])):
        for aid, rec in (by_id or {}).items():
            al = STATSAPI_AWARD_IDS.get(str(aid))
            if al is None or not isinstance(rec, dict):
                continue
            win = None
            if rec.get("person_id") is not None:
                win = {k: rec.get(k) for k in ("person_id", "name", "team_id", "team_code")}
            out.append({"award": al[0], "league": al[1], "season": int(s_key), "winner": win,
                        "finalists": list(rec.get("finalists") or []),
                        "finalists_announced": rec.get("finalists_announced"),
                        "announced": rec.get("date")})
    return out


def ballot_place(award: str, full_top: list, wid):
    """The rule's place of the row keyed wid on the rule's ballot (the BBWAA length
    of awards_core.BALLOT_RULES), or None past the ballot or off the pool."""
    if wid is None:
        return None
    n = A.BALLOT_RULES[award]["n"]
    place = next((r["rank"] for r in full_top or [] if _row_key(r) == wid), None)
    return place if place is not None and place <= n else None


def _writers(ctx: _Ctx, award: str, lg: str, S: int, full_top: list) -> dict:
    rec = _winner_row(ctx, award, lg, S)
    out = {"status": "pending", "announce_label": WRITERS_PENDING, "finalists": [],
           "winner": None, "rule_place_of_winner": None}
    if not rec:
        return out
    fin = rec.get("finalists") or []
    out["finalists"] = [{"id": _winner_id(ctx, award, f), "name": f.get("name")} for f in fin]
    if fin:
        out["status"] = "finalists"
    win = rec.get("winner")
    if win:
        wid = _winner_id(ctx, award, win)
        out["status"] = "final"
        out["announce_label"] = None
        out["winner"] = {"id": wid, "name": win.get("name")}
        out["rule_place_of_winner"] = ballot_place(award, full_top, wid)
    return out


def _winner_row(ctx: _Ctx, award, lg, S):
    for r in ctx.winner_list:
        if (str(r.get("award")) == award and str(r.get("league")) == lg
                and int(r.get("season") or 0) == int(S)):
            return r
    return None


def _winner_id(ctx: _Ctx, award: str, person: dict):
    if award == "MOY":
        code = ctx.abbrev.get(int(person.get("team_id") or 0)) or person.get("team_code")
        return "c" + str(_club(code) or "").lower() if code else None
    pid = person.get("person_id")
    return int(pid) if pid is not None else None


def _card(ctx: _Ctx, w: dict, award: str, lg: str) -> dict | None:
    S = w["season"]
    card = _ballots(ctx, w, award, lg)
    full = _ballots(ctx, w, award, lg, n=_ALL)
    if card is None or full is None:
        return None
    top = _decorate(ctx, w, award, card["top"])
    excluded = [dict(e, label=A.excluded_label(e)) for e in card.get("excluded") or []]
    block = {
        "top": top, "lead": card["lead"], "tiebreak_sentence": card["tiebreak_sentence"],
        "excluded": excluded, "n_pool": card["n_pool"], "floor": card["floor"],
        "war_provider": ctx.provider,
        "compare": _compare(ctx, w, award, card["top"], full["top"]),
        "drift": None,
        "writers": _writers(ctx, award, lg, S, full["top"]),
    }
    if award == "MOY" and card.get("unscored"):
        block["unscored"] = card["unscored"]
    return {"card": block, "full": full}


# --- superlatives ---------------------------------------------------------------------------

def _season_war(w: dict) -> dict:
    """{mlbam: {war, pa, ip, name, club_code}} both leagues summed (unrounded)."""
    out: dict = {}
    for r in w["rows"]:
        t = out.setdefault(r["mlbam"], {"mlbam": r["mlbam"], "war": 0.0, "pa": 0, "ip": 0.0,
                                         "name": r.get("name"), "club_code": None})
        t["war"] += float(r.get("bat") or 0.0) + float(r.get("pit") or 0.0)
        t["pa"] += int(r.get("pa") or 0)
        t["ip"] += float(r.get("ip") or 0.0)
        if r.get("clubs"):
            t["club_code"] = r["clubs"][-1]
    return out


def _prospect_rows(ctx: _Ctx, w: dict) -> list:
    """Per-player rows for the prospect pair, ONLY for debut cohorts the frame
    guard admits (awards_core.prospect_pool_open); a reserved cohort is never
    paired with a season here."""
    xfv = (ctx.inp.data_json("xfv.json", required=False) or {}).get("by_player") or {}
    pk = _player_key_map(ctx)
    war = _season_war(w)
    frames = A.reserved_frames()
    rows = []
    for m, deb in pk.items():
        d = str(deb.get("debut_date") or "")[:4]
        if not d.isdigit():
            continue
        debut = int(d)
        if not A.prospect_pool_open(debut, frames=frames):
            continue
        if m not in war:
            continue
        x = xfv.get(deb["player_key"]) or {}
        if x.get("kind") != "debuted":
            continue
        efv = x.get("xfv_grade_at_debut", x.get("xfv_grade"))
        if efv is None:
            continue
        rows.append(dict(war[m], player_key=deb["player_key"], debut_season=debut,
                         efv_at_debut=efv))
    return rows


def _next_rows(ctx: _Ctx, w: dict):
    """(rows, bundle_provider, realized_provider, displayed) for next_rise / next_drop."""
    S = w["season"]
    meta = ctx.inp.model_meta() or {}
    bundle = meta.get("war_provider")
    if int(ctx.proj.get("first_season") or 0) != S + 1:
        return None, bundle, None, "the projection file's first season is not the next season"
    war = _season_war(w)
    realized_provider = ctx.provider
    realized = {m: t["war"] for m, t in war.items()}
    if bundle and bundle != ctx.provider and bundle == "fwar":
        # The bundle is labelled on fWAR (the epoch's training label) while the
        # displayed WAR stays eWAR v2: the realized side is read from the frozen
        # fWAR vintage through EPOCH_E3's reader (fwar_vintage.side_targets, the
        # door war_source's side map uses), never the live saber cache, and the
        # displayed eWAR v2 total prints beside it.
        realized = _fwar_realized(S)
        realized_provider = "fwar"
    rows = []
    for v in ctx.proj.get("vets") or []:
        m = A._num(v.get("mlbam"))
        path = v.get("war") or []
        if m is None or not path or int(m) not in war or int(m) not in realized:
            continue
        t = war[int(m)]
        rows.append({"mlbam": int(m), "name": t["name"] or v.get("name"),
                     "club_code": t["club_code"], "pa": t["pa"], "ip": t["ip"],
                     "war_realized": realized[int(m)], "war_next": path[0],
                     "displayed": A.score_display(t["war"])})
    return rows, bundle, realized_provider, None


def _fwar_realized(S: int) -> dict:
    """{mlbam: realized fWAR in S, both sides summed} from the frozen vintage."""
    import fwar_vintage
    blob = fwar_vintage.load()
    out: dict = {}
    for side in ("bat", "pit"):
        for (mid, season), val in fwar_vintage.side_targets(blob, side).items():
            if int(season) != int(S) or val is None:
                continue
            out[int(mid)] = out.get(int(mid), 0.0) + float(val)
    return out


def _superlatives(ctx: _Ctx, w: dict, *, live_next: bool = True) -> list:
    S = w["season"]
    b = w["boards"]
    out = []
    out.append(A.prospect_above(_prospect_rows(ctx, w), S, war_provider=ctx.provider))
    out.append(A.prospect_below(_prospect_rows(ctx, w), S, war_provider=ctx.provider))
    # The projection pair gets no rows while it is dark: nothing realized is
    # subtracted from a projection on a label season whose looks are open.
    for fn in (A.proj_above, A.proj_below):
        blocked = A.proj_blocked_on(S)
        out.append(fn([], S, war_provider=ctx.provider) if blocked else
                   _blocked_block(fn.__name__, S, ctx.provider,
                                  "The frozen Opening Day file reader lands with AWARDS_13."))
    if live_next and S == ctx.board_season:
        rows, bundle, realized_prov, why = _next_rows(ctx, w)
        if rows is None:
            out += [_blocked_block(k, S, ctx.provider, why) for k in ("next_rise", "next_drop")]
        else:
            for fn in (A.next_rise, A.next_drop):
                blk = fn(rows, S, bundle_provider=bundle, realized_provider=realized_prov)
                blk["displayed_provider"] = ctx.provider
                blk["stamp"] = _proj_stamp(ctx)
                out.append(blk)
    else:
        why = (f"The projection file holds one forward path, for the season after "
               f"{ctx.board_season}.")
        out += [_blocked_block(k, S, ctx.provider, why) for k in ("next_rise", "next_drop")]
    fielders = list(b.fielders.values())
    if not b.current:
        fielders = [dict(r, dem_plus_raw=r.get("dem_plus_raw", r.get("dem_plus"))) for r in fielders]
    g = A.glove(fielders, S)
    g["producer"] = f"{b.src.get('fielders')}.{'dem_plus_raw' if b.current else 'dem_plus'}"
    out.append(g)
    if b.current:
        out.append(A.contact_ahead(list(b.hitters.values()), S))
        out.append(A.results_ahead(list(b.hitters.values()), S))
    else:
        why = "The Savant xwOBA join starts in 2026."
        out += [_blocked_block(k, S, None, why) for k in ("contact_ahead", "results_ahead")]
    rel = list(b.relievers.values())
    if not b.current:
        rel = [dict(r, rem_plus_raw=r.get("rem_plus_raw", r.get("rem_plus"))) for r in rel]
    rb = A.relief(rel, S)
    rb["producer"] = f"{b.src.get('relievers')}.{'rem_plus_raw' if b.current else 'rem_plus'}"
    out.append(rb)
    club_rows = [r for r in ((ctx.mgmt.get("clubs") or {}).get("rows") or [])]
    seasons = set((ctx.mgmt.get("decisions") or {}).get("seasons") or [])
    if S in seasons:
        out.append(A.pitching_changes(club_rows, S))
    else:
        out.append(_blocked_block("pitching_changes", S, None,
                                  "The decision ledger covers 2018, 2019 and 2021 on."))
    for blk in out:
        if blk.get("blocked_on"):
            continue
        n = len(blk.get("rows") or [])
        if n == 0:
            blk["blocked_on"] = "No player in this view clears the floor."
        elif n < SL_MIN_ROWS:
            # A lit card lists three to five (AWARDS_PLAN 6, I11); fewer is
            # the unmeasured state, naming the count, and the rows stay off.
            blk["blocked_on"] = (f"Only {n} of this season's rows clear the floor; the card "
                                 f"lists {SL_MIN_ROWS} to {A.SL_TOP_N}.")
            blk["rows"] = []
    return out


def _blocked_block(sl_id: str, S: int, provider, why: str) -> dict:
    return {"id": sl_id, "title": A.sl_title(sl_id, S), "definition": None, "floor_label": None,
            "frame_label": None, "kind": None, "family": None, "lamp_unit": None,
            "producer": None, "registry": None, "war_provider": provider, "n_pool": 0,
            "blocked_on": why, "caption": None, "rows": []}


def _proj_stamp(ctx: _Ctx) -> dict:
    meta = ctx.inp.model_meta() or {}
    return {"generated_at": ctx.proj.get("generated_at"), "first_season": ctx.proj.get("first_season"),
            "war_provider": meta.get("war_provider"), "label_shape": meta.get("label_shape"),
            "train_hash": meta.get("train_hash")}


# --- the registry, stamps and credits -------------------------------------------------------

def _registry_block(ctx: _Ctx, ids) -> dict:
    models = {m.get("model_id"): m for m in (ctx.registry_doc.get("models") or [])}
    out = {}
    for mid in sorted(i for i in ids if i):
        m = models.get(mid)
        if m is None:
            out[mid] = {"verdict": None, "eval_artifact": None, "age_days": None, "stale": None,
                        "registered": False}
        else:
            out[mid] = {"verdict": m.get("verdict"), "eval_artifact": m.get("eval_artifact"),
                        "age_days": m.get("artifact_age_days"), "stale": m.get("stale"),
                        "registered": True}
    return out


def _registry_ids(payload: dict) -> set:
    ids = {A.SELECTION_REGISTRY, "ewar"}
    for a in (payload.get("awards") or {}).values():
        for blk in a.values():
            for m in ((blk or {}).get("compare") or {}).get("metrics") or []:
                ids.add(m.get("registry"))
    for s in payload.get("superlatives") or []:
        ids.add(s.get("registry"))
    for r in (payload.get("race") or {}).values():
        if r:
            ids.add(r.get("registry"))
    return {i for i in ids if i}


# --- the season payload --------------------------------------------------------------------

def _lamp_units(seasons_tops: list) -> dict:
    """Per award, the base lamp unit doubled until the largest value in any built
    season's ballot needs at most LAMP_MAX lamps (shared by both leagues)."""
    out = {}
    for award in A.AWARDS:
        unit = A.LAMP_UNITS[award]
        big = 0.0
        for tops in seasons_tops:
            for r in tops.get(award, []):
                big = max(big, abs(float(r["score"])))
        while big / unit > LAMP_MAX:
            unit *= 2
        out[award] = unit
    return out


def _season_payload(ctx: _Ctx, S: int) -> dict:
    w = ctx.world(S)
    awards, full = {}, {}
    for award in A.AWARDS:
        for lg in A.LEAGUES:
            got = _card(ctx, w, award, lg)
            if got is None:
                continue
            awards.setdefault(award, {})[lg] = got["card"]
            full[(award, lg)] = got["full"]
    st = w["standings"]
    rules = {}
    for award in A.AWARDS:
        blocked = None if award in awards else "The inputs for this award are not on file for the season."
        rules[award] = A.rules_block(award, S, ctx.provider, blocked_on=blocked)
    sl = _superlatives(ctx, w)
    return {"season": S, "awards": awards, "rules": rules, "superlatives": sl,
            "full": full, "world": w, "through": _through(ctx, S, st)}


def _through(ctx: _Ctx, S: int, st: dict):
    tb = ((ctx.mgmt.get("decisions") or {}).get("through_by_season") or {})
    return tb.get(str(S)) or st.get("through")


def _race(ctx: _Ctx, S: int) -> dict:
    """The race block: the tracked data/_labs/awards/race_<S>.json when it exists (mode
    wpa_order, tools/awards_race.py), else from RULE_PLACE_FIRST on the rule_place race
    built from the nightly vintages on this machine."""
    doc = ctx.inp.labs_json(f"race_{S}.json", required=False)
    if doc is None and S >= RULE_PLACE_FIRST and ctx.vintage_dir is not None:
        pending = ctx.pending_vintage if (ctx.pending_vintage or {}).get("season") == S else None
        doc = rule_place_race(load_vintages(ctx.vintage_dir, S, pending=pending))
    out = {}
    for award in A.AWARDS:
        for lg in A.LEAGUES:
            k = f"{award}_{lg}"
            blk = (doc or {}).get(k) if isinstance(doc, dict) else None
            out[k] = copy.deepcopy(blk) if blk else None
    return out


def _credits(ctx: _Ctx, current: bool, copyright_: str | None) -> list:
    shows = ["mlb", "bref", "fangraphs", "eephus"]
    if current:
        shows.append("savant")
    return A.credit_lines(shows, mlb_copyright=copyright_)


def _seasons_index(ctx: _Ctx, built: dict, frozen_seasons: set) -> list:
    out = []
    for S in range(ctx.board_season, SELECTOR_FIRST - 1, -1):
        p = built.get(S)
        if p is None:
            continue
        status = ("frozen" if S in frozen_seasons else "live") if S == ctx.board_season else "closed"
        g = A.scheduled_games(S)
        out.append({
            "season": S, "status": status,
            "awards": sorted(p.get("awards") or {}, key=A.AWARDS.index),
            "superlatives": [s["id"] for s in p.get("superlatives") or []
                             if s.get("rows") and not s.get("blocked_on")],
            "race": any(v for v in (p.get("race") or {}).values()),
            "note": SHORT_SEASON_NOTE.format(g=g) if g != A.FULL_SEASON_GAMES else None})
    return out


def _public(p: dict) -> dict:
    """The season payload without the build's internals."""
    return {k: v for k, v in p.items() if k not in ("full", "world")}


def _shard_doc(ctx: _Ctx, p: dict, *, status: str, generated_at: str) -> dict:
    S = p["season"]
    st = p["world"]["standings"]
    current = S == ctx.board_season
    doc = {
        "schema": SCHEMA, "produced_by": PRODUCED_BY, "generated_at": generated_at,
        "season": S, "status": status, "war_provider": ctx.provider,
        "stamp": {"through": p["through"], "frozen_at": None},
        "ballot_rules": A.ballot_rules_payload(),
        "rules": p["rules"], "awards": p["awards"],
        "superlatives": [A.sl_present(s, S) for s in p["superlatives"]],
        "race": _race(ctx, S),
        "credits": _credits(ctx, current, st.get("copyright")),
        "what_this_page_does_not_claim": A.does_not_claim_lines(ctx.provider),
    }
    doc["registry"] = _registry_block(ctx, _registry_ids(doc))
    return doc


# --- the rule_place race (2027 on) ----------------------------------------------------------

def vintage_dir(cache_dir=None, preview_dir=None) -> Path:
    """Where the nightly vintages live: .cache/awards_vintages once the flag is True; while
    it is False, the preview's own awards_vintages folder (the flag's rule: the exporter
    writes only under the preview)."""
    if A.AWARDS_LIVE:
        return (Path(cache_dir) / "awards_vintages") if cache_dir is not None else VINTAGES
    if preview_dir is not None:
        base = Path(preview_dir)
    elif cache_dir is not None:
        base = Path(cache_dir) / "awards" / "preview"
    else:
        base = PREVIEW
    return base / "awards_vintages"


def vintage_record(cur: dict, *, date: str, war_provider: str, generated_at: str) -> dict:
    """One night's record: the Top VINTAGE_TOP per award and league on the rule, from the
    season payload's full ballots (the live files, before any frozen record applies)."""
    top = {}
    for (award, lg), full in sorted((cur.get("full") or {}).items(),
                                    key=lambda kv: (A.AWARDS.index(kv[0][0]), kv[0][1])):
        top[f"{award}_{lg}"] = [
            {"id": str(_row_key(r)), "name": r.get("name") or r.get("club"),
             "rank": int(r["rank"]), "score": r.get("score")}
            for r in (full.get("top") or [])[:VINTAGE_TOP]]
    return {"schema": SCHEMA, "produced_by": PRODUCED_BY, "season": int(cur["season"]),
            "date": date, "through": cur.get("through"), "war_provider": war_provider,
            "generated_at": generated_at, "top": top}


def write_vintage(vdir: Path, record: dict) -> bool:
    """Write <date>.json once: the first write of a date wins, a later one is a no-op."""
    path = Path(vdir) / f"{record['date']}.json"
    if path.exists():
        return False
    _write_bytes(path, _dump(record))
    return True


def load_vintages(vdir: Path, S: int, *, pending: dict | None = None) -> list:
    """The season's vintages on disk, by date, plus tonight's pending record when its date
    is not on disk yet (the disk's record wins a date: first write wins)."""
    out = {}
    d = Path(vdir)
    if d.exists():
        for f in sorted(d.glob("*.json")):
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(rec, dict) and int(rec.get("season") or 0) == int(S) and rec.get("date"):
                out[str(rec["date"])] = rec
    if pending and int(pending.get("season") or 0) == int(S) and str(pending["date"]) not in out:
        out[str(pending["date"])] = pending
    return [out[k] for k in sorted(out)]


def _iso_week(day: str) -> tuple:
    return tuple(_dt.date.fromisoformat(day).isocalendar()[:2])


def rule_place_race(vintages: list) -> dict:
    """{"MVP_AL": block, ...} in mode rule_place from the nightly vintages. One column per
    ISO week from the first record to the last; a week's point is the latest record whose
    data run through that week (its `through`, else its date); a week with no record is
    listed in `missing` (its Sunday) with null places and values. The three rows are the
    latest record's Top 3; a place is 1, 2 or 3 among the whole pool, null outside it."""
    if not vintages:
        return {}
    by_week: dict = {}
    for rec in vintages:
        day = str(rec.get("through") or rec["date"])[:10]
        wk = _iso_week(day)
        cur = by_week.get(wk)
        if cur is None or str(rec["date"]) > str(cur[1]["date"]):
            by_week[wk] = (day, rec)
    first_day = min(day for day, _r in by_week.values())
    record_starts = min(str(rec.get("through") or rec["date"])[:10] for rec in vintages)
    last_day = max(day for day, _r in by_week.values())
    weeks, missing, recs = [], [], []
    d = _dt.date.fromisoformat(first_day)
    end = _dt.date.fromisoformat(last_day)
    while True:
        wk = tuple(d.isocalendar()[:2])
        sunday = d + _dt.timedelta(days=6 - d.weekday())
        if wk in by_week:
            weeks.append(by_week[wk][0])
            recs.append(by_week[wk][1])
        else:
            weeks.append(sunday.isoformat())
            missing.append(sunday.isoformat())
            recs.append(None)
        if sunday >= end:
            break
        d = sunday + _dt.timedelta(days=1)
    latest = vintages[-1]
    out = {}
    for key, rows in (latest.get("top") or {}).items():
        three = rows[:3]
        if len(three) < 3:
            continue
        places = {r["id"]: [] for r in three}
        values = {r["id"]: [] for r in three}
        for rec in recs:
            idx = {x["id"]: x for x in ((rec or {}).get("top") or {}).get(key) or []}
            for r in three:
                x = idx.get(r["id"])
                rank = int(x["rank"]) if x is not None else None
                places[r["id"]].append(rank if rank is not None and rank <= 3 else None)
                values[r["id"]].append(x.get("score") if x is not None else None)
        out[key] = {
            "mode": "rule_place", "metric_label": RACE_RULE_LABEL,
            "producer": RACE_RULE_PRODUCER, "registry": A.SELECTION_REGISTRY,
            "war_provider": latest.get("war_provider"),
            "weeks": weeks, "record_starts": record_starts, "missing": missing,
            "finalists": [{"id": r["id"], "name": r.get("name"), "rule_place": int(r["rank"])}
                          for r in three],
            "places": places, "values": values,
        }
    return out


def _season_started(cur: dict) -> bool:
    return any((A._num(c.get("gp")) or 0) > 0 for c in cur["world"]["standings"]["clubs"])


# --- the vote table --------------------------------------------------------------------------

def _first(full_or_card) -> dict | None:
    top = (full_or_card or {}).get("top") or []
    if not top:
        return None
    r = top[0]
    return {"id": _row_key(r), "name": r.get("name") or r.get("club")}


def _vote_table(ctx: _Ctx, shard_firsts: dict, built_full: dict) -> list:
    rows = []
    S0 = ctx.board_season
    for S in range(S0, VOTE_FIRST - 1, -1):
        for award in A.AWARDS:
            for lg in A.LEAGUES:
                if S == S0 and not ((_winner_row(ctx, award, lg, S) or {}).get("winner")):
                    continue
                first = shard_firsts.get((S, award, lg))
                full = built_full.get((S, award, lg))
                if first is None and full is None:
                    w = ctx.world(S)
                    full = _ballots(ctx, w, award, lg, n=_ALL)
                    built_full[(S, award, lg)] = full
                if first is None:
                    first = _first(full)
                if first is None:
                    continue
                rec = _winner_row(ctx, award, lg, S)
                win = rec.get("winner") if rec else None
                wid = _winner_id(ctx, award, win) if win else None
                place = ballot_place(award, (full or {}).get("top"), wid)
                g = A.scheduled_games(S)
                rows.append({
                    "season": S, "award": award, "league": lg, "rule_first": first,
                    "writers_first": ({"id": wid, "name": win.get("name")} if win else None),
                    "rule_place_of_writers_first": place,
                    "writers_finish_of_rule_first": None,
                    "computed_after_the_fact": True,
                    "note": SHORT_SEASON_NOTE.format(g=g) if g != A.FULL_SEASON_GAMES else None})
    return rows


# --- refusal ------------------------------------------------------------------------------------

def _i1_check(ctx: _Ctx, p: dict) -> dict:
    """I1 over every row of the top I1_TOP of each player ballot: each side's AL
    plus NL share against the provider artifact's side total, and the printed
    sum against the war board's players[].war; I2 alongside."""
    w = p["world"]
    totals = A.side_totals(w["rows"])
    board = ctx.world(ctx.board_season)["boards"].war_players if p["season"] == ctx.board_season else {}
    artifact = PROVIDER_ARTIFACT.get(ctx.provider)
    seen, bad, max_diff = set(), [], 0.0
    n_board = n_board_ok = n_art_ok = 0
    n_cy = n_cy_ok = 0
    for (award, lg), full in p["full"].items():
        if award == "MOY":
            continue
        for r in full["top"][:I1_TOP]:
            m = int(r["mlbam"])
            if m in seen:
                continue
            seen.add(m)
            t = totals.get(m, {"bat": 0.0, "pit": 0.0})
            if artifact:
                blk = w["ewar_side"].get(m) or {}
                ok = True
                for side, key in (("bat", "ewb"), ("pit", "ewp")):
                    want = float(blk.get(key) or 0.0)
                    d = abs(t[side] - want)
                    max_diff = max(max_diff, d)
                    if d > I1_TOL:
                        ok = False
                        bad.append(f"{r.get('name')} {side} {t[side]:.3f} vs {want:.3f}")
                n_art_ok += ok
            if m in board:
                n_board += 1
                if A.score_display(t["bat"] + t["pit"]) == board[m].get("war"):
                    n_board_ok += 1
                else:
                    bad.append(f"{r.get('name')} prints {A.score_display(t['bat'] + t['pit'])} "
                               f"against the board's {board[m].get('war')}")
                if board[m].get("war_pit") is not None and t["pit"] != 0.0:
                    n_cy += 1
                    n_cy_ok += A.score_display(t["pit"]) == board[m].get("war_pit")
    return {"n_checked": len(seen), "artifact": artifact, "n_artifact_ok": n_art_ok if artifact else None,
            "max_abs_diff": round(max_diff, 6), "n_board_rows": n_board, "n_board_ok": n_board_ok,
            "i2_n_pitch_rows": n_cy, "i2_n_pitch_ok": n_cy_ok, "failures": bad[:20]}


def _in_season(ctx: _Ctx) -> bool:
    if ctx.proj.get("mc_schedule_source") == "season_complete":
        return False
    for t in ctx.proj.get("team_outlook") or []:
        if (A._num((t.get("current") or {}).get("remGames")) or 0) > 0:
            return True
    return False


def _standings_age_days(ctx: _Ctx) -> float | None:
    p = ctx.inp.cache / f"statsapi_standings_{ctx.board_season}.json"
    if not p.exists():
        return None
    return (_dt.datetime.now().timestamp() - p.stat().st_mtime) / 86400.0


def _refusals(ctx: _Ctx, cur: dict, i1: dict) -> list:
    out = []
    vint = ctx.board.get("ewar_vintage") or {}
    if vint.get("stale"):
        out.append("the eWAR board is stale (war_leaderboards.json ewar_vintage.stale)")
    for side, v in sorted(_served_stale().items()):
        age = v.get("age_days")
        out.append(f"war_source served the {side} stint frame from its last-good parquet"
                   + (f" ({age:.1f} days old)" if isinstance(age, (int, float)) else ""))
    if i1["failures"]:
        out.append(f"I1: {len(i1['failures'])} Top-{I1_TOP} rows miss: " + "; ".join(i1["failures"][:3]))
    if _in_season(ctx):
        age = _standings_age_days(ctx)
        if age is None or age > STANDINGS_MAX_AGE_DAYS:
            out.append("the standings cache is older than "
                       f"{STANDINGS_MAX_AGE_DAYS} days in season")
    n_clubs = len([c for c in cur["world"]["standings"]["clubs"] if c.get("club")])
    n_teams = len(ctx.board.get("teams") or [])
    if min(n_clubs, n_teams) < MIN_CLUBS:
        out.append(f"fewer than {MIN_CLUBS} clubs (standings {n_clubs}, war board {n_teams})")
    if ctx.rookie_block(cur["season"]) is None:
        out.append(f"rookies.json has no block for {cur['season']}")
    return out


# --- the freeze ---------------------------------------------------------------------------------

def _freeze_log(labs: Path) -> dict:
    p = labs / "freeze_log.json"
    if not p.exists():
        return {"schema": 1, "entries": []}
    return json.loads(p.read_text(encoding="utf-8"))


def _frozen_record(ctx: _Ctx, labs: Path, S: int):
    """(record, sha256, entry) for a frozen season, None when there is none;
    raises AwardsRefusal on a hash that differs from the freeze log."""
    p = labs / f"frozen_{S}.json"
    if not p.exists():
        return None
    raw = p.read_bytes()
    sha = _sha(raw)
    entry = next((e for e in _freeze_log(labs).get("entries") or []
                  if int(e.get("season") or 0) == S), None)
    if entry is None or entry.get("sha256") != sha:
        raise AwardsRefusal(f"frozen_{S}.json has sha256 {sha[:12]}, which freeze_log.json "
                            f"does not carry")
    return json.loads(raw.decode("utf-8")), sha, entry


def _finalists_date(ctx: _Ctx, S: int):
    dates = [str(r.get("finalists_announced")) for r in ctx.winner_list
             if int(r.get("season") or 0) == S and r.get("finalists_announced")]
    return min(dates) if dates else None


def _context(*, season=None, data_dir=None, cache_dir=None, labs_dir=None, model_dir=None,
             provider=None):
    data_dir = Path(data_dir) if data_dir is not None else DATA
    cache_dir = Path(cache_dir) if cache_dir is not None else CACHE
    labs_dir = Path(labs_dir) if labs_dir is not None else LABS
    model_dir = Path(model_dir) if model_dir is not None else ROOT / "model" / "proj_lgbm"
    inp = _Inputs(data_dir, cache_dir, labs_dir, model_dir)
    provider = provider or _display_provider()
    board = inp.data_json("war_leaderboards.json")
    S = int(season or board.get("season"))
    seasons = set(range(VOTE_FIRST, S + 1))
    records = {side: _season_records(_stint_frame(side, provider), seasons) for side in ("bat", "pit")}
    return _Ctx(inp, provider, S, records), labs_dir


def freeze(season: int, *, log=print, data_dir=None, cache_dir=None, labs_dir=None,
           model_dir=None) -> dict:
    """Write data/_labs/awards/frozen_<S>.json ONCE and append its sha256 and
    frozen_at to freeze_log.json (AWARDS_PLAN 4.7). Refuses when the record
    exists, while the season is in progress, or on any refusal reason. Writes no
    depth-one data file and nothing under the preview."""
    S = int(season)
    labs = Path(labs_dir) if labs_dir is not None else LABS
    path = labs / f"frozen_{S}.json"
    if path.exists():
        return {"ok": False, "reason": f"frozen_{S}.json exists; the record is write-once"}
    try:
        ctx, labs = _context(season=S, data_dir=data_dir, cache_dir=cache_dir, labs_dir=labs,
                             model_dir=model_dir)
        if S == ctx.board_season and _in_season(ctx):
            raise AwardsRefusal(f"the {S} regular season is still in progress")
        cur = _season_payload(ctx, S)
        i1 = _i1_check(ctx, cur)
        reasons = _refusals(ctx, cur, i1)
        if reasons:
            raise AwardsRefusal("; ".join(reasons))
    except AwardsRefusal as e:
        log(f"  awards freeze REFUSED: {e}")
        return {"ok": False, "reason": str(e)}
    frozen_at = _now_iso()
    fin = _finalists_date(ctx, S)
    vint = ctx.board.get("ewar_vintage") or {}
    record = {
        "schema": SCHEMA, "produced_by": PRODUCED_BY, "season": S, "frozen_at": frozen_at,
        "war_provider": ctx.provider,
        "freeze": {"frozen_at": frozen_at, "war_provider": ctx.provider,
                   "ewar_artifact_generated_at": vint.get("artifact_generated_at"),
                   "label_build_at": vint.get("label_build_at"),
                   "finalists_announced": fin,
                   "after_finalists": bool(fin and frozen_at[:10] >= fin)},
        "through": cur["through"],
        "stint_frames": {"provider": ctx.provider, "stale": _served_stale()},
        "ballot_rules": A.ballot_rules_payload(),
        "rules": cur["rules"], "awards": cur["awards"],
        "superlatives": [s for s in cur["superlatives"] if s["id"] not in ("next_rise", "next_drop")],
        "stamps": ctx.inp.stamps,
    }
    record["registry"] = _registry_block(ctx, _registry_ids(record))
    raw = json.dumps(record, ensure_ascii=False, indent=1).encode("utf-8")
    sha = _sha(raw)
    _write_bytes(path, raw)
    flog = _freeze_log(labs)
    flog.setdefault("entries", []).append({
        "season": S, "path": f"data/_labs/awards/frozen_{S}.json", "sha256": sha,
        "frozen_at": frozen_at})
    _write_bytes(labs / "freeze_log.json", json.dumps(flog, ensure_ascii=False, indent=1).encode("utf-8"))
    log(f"  awards: froze {S} ({len(raw):,} bytes, sha256 {sha[:12]})")
    return {"ok": True, "path": str(path), "sha256": sha, "frozen_at": frozen_at, "bytes": len(raw)}


def _apply_frozen(ctx: _Ctx, cur: dict, record: dict) -> dict:
    """Cards, rules and superlatives (other than next_*) from the frozen record;
    a drift column with each frozen row's score on today's files."""
    S = cur["season"]
    live_scores = {}
    for (award, lg), full in cur["full"].items():
        for r in full["top"]:
            live_scores[(award, lg, _row_key(r))] = r["score"]
    w = cur["world"]
    totals = {}
    for r in w["rows"]:
        totals[(r["league"], r["mlbam"])] = r
    awards = copy.deepcopy(record.get("awards") or {})
    for award, by in awards.items():
        for lg, blk in by.items():
            drift = []
            for r in blk.get("top") or []:
                k = _row_key(r)
                now = live_scores.get((award, lg, k))
                if now is None and award != "MOY":
                    lr = totals.get((lg, r.get("mlbam")))
                    if lr is not None:
                        now = (float(lr.get("pit") or 0.0) if award == "CY"
                               else float(lr.get("bat") or 0.0) + float(lr.get("pit") or 0.0))
                drift.append({"id": k, "score_now": now,
                              "score_now_display": A.score_display(now),
                              "war_provider": ctx.provider,
                              "unit_label": A.drift_unit_label(ctx.provider),
                              "tooltip": A.drift_tooltip(str(record.get("frozen_at"))[:10])})
            blk["drift"] = drift
    live_next = [s for s in cur["superlatives"] if s["id"] in ("next_rise", "next_drop")]
    sl = list(record.get("superlatives") or [])
    order = list(A.SL_IDS)
    sl = sorted(sl + live_next, key=lambda s: order.index(s["id"]))
    return dict(cur, awards=awards, rules=record.get("rules") or cur["rules"], superlatives=sl)


# --- export --------------------------------------------------------------------------------------

def _eval_doc(ctx: _Ctx, cur: dict, i1: dict, copies: dict, labs: Path, generated_at: str) -> dict:
    moy = []
    for lg in A.LEAGUES:
        full = cur["full"].get(("MOY", lg))
        moy += (full or {}).get("top") or []
    outlook = {_club(t.get("team")): t.get("current") or {} for t in ctx.proj.get("team_outlook") or []}
    n_pyth_ok = sum(1 for r in moy if r.get("pythag_w") is not None and
                    abs(r["pythag_w"] - (outlook.get(r["club"], {}).get("pythagPct") or 0)
                        * (outlook.get(r["club"], {}).get("gamesPlayed") or 0)) < 1e-9)
    n_parts_ok = sum(1 for r in moy if abs(r["parts"]["sequencing"] + r["parts"]["runs_vs_player_value"]
                                           - r["score"]) < 1e-9)
    rook = {"status": "no winners file", "n_winners": None, "n_pass": None, "rows": []}
    if ctx.winners:
        rows = []
        for r in ctx.winner_list:
            if r.get("award") != "ROY" or not r.get("winner"):
                continue
            S = int(r.get("season") or 0)
            if not (VOTE_FIRST <= S < ctx.board_season):
                continue
            pid = (r["winner"] or {}).get("person_id")
            st = A.rookie_status(ctx.rookie_block(S) or {}).get(int(pid)) if pid else None
            rows.append({"season": S, "league": r.get("league"), "person_id": pid,
                         "name": r["winner"].get("name"),
                         "passes": bool(st and st["eligible"]),
                         "proxy_days": (st or {}).get("proxy_days")})
        rook = {"status": "measured", "n_winners": len(rows),
                "n_pass": sum(1 for x in rows if x["passes"]), "rows": rows}
    return {
        "schema": SCHEMA, "produced_by": PRODUCED_BY, "generated_at": generated_at,
        "model_id": A.SELECTION_REGISTRY, "season": cur["season"], "war_provider": ctx.provider,
        "reconciliation": {
            "I1": {k: i1[k] for k in ("n_checked", "artifact", "n_artifact_ok", "max_abs_diff",
                                      "n_board_rows", "n_board_ok")},
            "I2": {"n_pitch_rows": i1["i2_n_pitch_rows"], "n_pitch_ok": i1["i2_n_pitch_ok"]},
            "I3": copies,
            "I4": {"n_clubs": len(moy), "sum_scores": round(sum(r["score"] for r in moy), 6),
                   "n_parts_sum_to_score": n_parts_ok, "n_pythag_matches_team_outlook": n_pyth_ok},
        },
        "rookie_winners": rook,
        "freeze": copy.deepcopy(_freeze_log(labs).get("entries") or []),
    }


def _copy_check(ctx: _Ctx, cur: dict) -> dict:
    """I3 at build time: every compare value with a board source re-read from
    its producer, compared as JSON bytes."""
    n = ok = 0
    w = cur["world"]
    b = w["boards"]
    srcmap = {v: getattr(b, k) for k, v in b.src.items()}
    for by in cur["awards"].values():
        for blk in by.values():
            top = blk["top"]
            for m in blk["compare"]["metrics"]:
                for i, (v, s) in enumerate(zip(m["values"], m["sources"])):
                    if v is None or not s or "[]." not in s:
                        continue
                    base, field = s.rsplit(".", 1)
                    src = srcmap.get(base)
                    if src is None or i >= len(top) or top[i].get("mlbam") is None:
                        continue
                    n += 1
                    want = (src.get(int(top[i]["mlbam"])) or {}).get(field)
                    ok += json.dumps(want) == json.dumps(v)
    return {"n_copied_values": n, "n_equal": ok}


def _candidates(ctx: _Ctx, p: dict, generated_at: str) -> dict:
    S = p["season"]
    w = p["world"]
    unit = A.war_unit_label(ctx.provider)
    rook = A.rookie_status(ctx.rookie_block(S) or {})
    cols_out, pools = {}, {}
    for award in A.AWARDS:
        if award == "MOY":
            metrics = _club_metrics(ctx, w)
        else:
            metrics = [m for m in _player_metrics(award, unit)
                       if m.key not in ("score", "pa", "ip", "age")
                       and not (m.current_only and not w["boards"].current)]
        head = [("id", "Id", ("club code" if award == "MOY" else "war_source.stint_frame mlb_ID"), None),
                ("name", "Name", ("club code" if award == "MOY" else
                                  "the season's board name, else war_source.stint_frame name_common"), None),
                ("club", "Club", ("standings club" if award == "MOY" else
                                  "war_source.stint_frame team_ID, the league's last stint"), None),
                ("pos", "Pos", "war_leaderboards.json players[].pos, else the defense board, else P", None),
                ("age", "Age", "war_source.stint_frame age", None),
                ("score", "wins" if award == "MOY" else unit, "the rule's score", A.SELECTION_REGISTRY)]
        if award == "MOY":
            head = head[:3] + [head[5]]
            metrics = [m for m in metrics if m.key != "score"]
        tail = [("pa", "PA", "war_source.stint_frame PA (in-league)", None),
                ("ip", "IP", "war_source.stint_frame IPouts / 3 (in-league)", None),
                ("place", "Rule place", "the rule's ballot", A.SELECTION_REGISTRY),
                ("below_floor", "Below the floor", "the rule's floor", None),
                ("outside_rookie_proxy", "Outside the rookie test", "data/_labs/awards/rookies.json", None),
                ("two_way", "Two-way", "war_source.stint_frame", None)]
        if award == "MOY":
            tail = [tail[2]]
        cols = ([{"key": k, "label": l, "producer": pr, "registry": rg} for k, l, pr, rg in head]
                + [{"key": m.key, "label": m.label, "producer": m.producer, "registry": m.registry}
                   for m in metrics]
                + [{"key": k, "label": l, "producer": pr, "registry": rg} for k, l, pr, rg in tail])
        cols_out[award] = cols
        for lg in A.LEAGUES:
            key = f"{lg.lower()}-{award.lower()}"
            full = p["full"].get((award, lg))
            if full is None:
                continue
            n = A.BALLOT_RULES[award]["n"]
            place = {_row_key(r): r["rank"] for r in full["top"] if r["rank"] <= n}
            if award == "MOY":
                rows = []
                for r in full["top"]:
                    rows.append([_row_key(r), r.get("name"), r.get("club"), round(r["score"], 3)]
                                + [m.getter(w, r)[0] for m in metrics]
                                + [place.get(_row_key(r))])
                pools[key] = {"award": award, "league": lg, "n": len(rows), "rows": rows}
                continue
            lined = [r for r in w["rows"] if r["league"] == lg and _has_line(r)]
            if award == "CY":
                pool = [r for r in lined if (r.get("ip") or 0) > 0]
            elif award == "MVP":
                pool = lined
            else:
                pool = [r for r in lined if r["mlbam"] in rook]
            rows, proxy_out = [], []
            for r in pool:
                m_id = r["mlbam"]
                score = float(r.get("pit") or 0.0) if award == "CY" else \
                    float(r.get("bat") or 0.0) + float(r.get("pit") or 0.0)
                rr = dict(r, score=score)
                st = rook.get(m_id)
                outside = bool(st and not st["eligible"])
                row = ([m_id, r.get("name"), (r.get("clubs") or [None])[-1], w["pos"].get(m_id),
                        r.get("age"), round(score, 3)]
                       + [m.getter(w, rr)[0] for m in metrics]
                       + [r.get("pa"), r.get("ip"), place.get(m_id),
                          not A.clears_floor(award, r, S),
                          outside if award == "ROY" else None,
                          (r.get("pa") or 0) >= TWO_WAY_MIN_PA and (r.get("ip") or 0) >= TWO_WAY_MIN_IP])
                if award == "ROY" and outside:
                    proxy_out.append({"row": row, "reason": st["reason"], "proxy_days": st["proxy_days"]})
                else:
                    rows.append(row)
            rows.sort(key=lambda x: (-x[5], x[0]))
            pools[key] = {"award": award, "league": lg, "n": len(rows), "rows": rows}
            if award == "ROY":
                pools[key]["proxy_out"] = sorted(proxy_out, key=lambda x: (-x["row"][5], x["row"][0]))
    return {"schema": SCHEMA, "produced_by": PRODUCED_BY, "generated_at": generated_at,
            "season": S, "war_provider": ctx.provider, "ballot_rules": A.ballot_rules_payload(),
            "pool_rule": _pool_rule(), "columns": cols_out, "pools": pools}


def _has_line(r: dict) -> bool:
    """A candidate row: in-league exposure at the war board's qualified rule."""
    return ((A._num(r.get("pa")) or 0.0) >= CANDIDATE_MIN_PA
            or (A._num(r.get("ip")) or 0.0) >= CANDIDATE_MIN_IP)


def _pool_rule() -> str:
    return (f"Every in-league player with a line at the war board's qualified rule: "
            f"in-league PA of at least {CANDIDATE_MIN_PA} or IP of at least {CANDIDATE_MIN_IP}; "
            f"Cy Young pitchers among them; Rookie the players the rookie test admits, with "
            f"the players it removes listed under proxy_out; Manager the league's clubs.")


def _n_rows(cand: dict) -> int:
    return sum(len(p["rows"]) + len(p.get("proxy_out") or []) for p in cand["pools"].values())


def export(out_dir=Path("data"), season=None, *, log=print, data_dir=None, cache_dir=None,
           labs_dir=None, preview_dir=None, model_dir=None) -> dict:
    """Build and write the Awards payloads (module docstring). Returns {"ok",
    "reason"|None, "message", "n_rows", "out_dir", "files": {name: bytes},
    "top3": {"MVP_AL": [names], ...}, "status"}. On a refusal nothing is
    written and the previous files stand."""
    if A.AWARDS_LIVE:
        out = Path(out_dir)
        out = out if out.is_absolute() else ROOT / out
    else:
        out = Path(preview_dir) if preview_dir is not None else PREVIEW
    generated_at = _now_iso()
    try:
        ctx, labs = _context(season=season, data_dir=data_dir, cache_dir=cache_dir,
                             labs_dir=labs_dir, model_dir=model_dir)
        S = ctx.board_season if season is None else int(season)
        ctx.vintage_dir = vintage_dir(cache_dir, preview_dir)
        frozen = _frozen_record(ctx, labs, S)
        try:
            cur = _season_payload(ctx, S)
        except A.ProviderMismatch as e:
            raise AwardsRefusal(f"next_rise / next_drop: {e}")
        i1 = _i1_check(ctx, cur)
        reasons = _refusals(ctx, cur, i1)
        if reasons:
            raise AwardsRefusal("; ".join(reasons))
        if S >= RULE_PLACE_FIRST and frozen is None and _season_started(cur):
            ctx.pending_vintage = vintage_record(
                cur, date=_dt.date.today().isoformat(), war_provider=ctx.provider,
                generated_at=generated_at)
        copies = _copy_check(ctx, cur)
        if frozen is not None:
            record, sha, entry = frozen
            cur = _apply_frozen(ctx, cur, record)
        built = {S: cur}
        shard_firsts: dict = {}
        files: dict = {}
        for Sp in range(SELECTOR_FIRST, S):
            shard = out / f"awards_{Sp}.json"
            if shard.exists():
                doc = json.loads(shard.read_text(encoding="utf-8"))
                built[Sp] = {"season": Sp, "awards": doc.get("awards") or {},
                             "superlatives": doc.get("superlatives") or [],
                             "race": doc.get("race") or {}}
                for award, by in (doc.get("awards") or {}).items():
                    for lg, blk in by.items():
                        shard_firsts[(Sp, award, lg)] = _first(blk)
                continue
            built[Sp] = _season_payload(ctx, Sp)
        lamp = _lamp_units([{a: [r for lg in by.values() for r in lg.get("top") or []]
                             for a, by in (p.get("awards") or {}).items()} for p in built.values()])
        for p in built.values():
            for a, rb in (p.get("rules") or {}).items():
                rb["lamp_unit"] = lamp[a]
        built_full = {}
        for Sp, p in built.items():
            for (a, lg), f in (p.get("full") or {}).items():
                built_full[(Sp, a, lg)] = f
        vote_table = _vote_table(ctx, shard_firsts, built_full)
        frozen_seasons = {S} if frozen is not None else set()
        for p in built.values():
            if "world" in p:
                p["race"] = _race(ctx, p["season"])
        index = _seasons_index(ctx, built, frozen_seasons)

        doc = _shard_doc(ctx, cur, status="frozen" if frozen else "live", generated_at=generated_at)
        st = cur["world"]["standings"]
        vint = ctx.board.get("ewar_vintage") or {}
        freeze_blk = None
        if frozen is not None:
            record, sha, entry = frozen
            fz = record.get("freeze") or {}
            freeze_blk = dict(fz, record_sha256=sha)
            doc["what_this_page_does_not_claim"] = A.does_not_claim_lines(
                record.get("war_provider") or ctx.provider,
                frozen_at=str(record.get("frozen_at"))[:10], now_provider=ctx.provider)
            doc["war_provider"] = record.get("war_provider") or ctx.provider
        payload = {
            "schema": SCHEMA, "produced_by": PRODUCED_BY, "generated_at": generated_at,
            "default_season": S, "seasons": index, "season": S,
            "status": "frozen" if frozen else "live", "war_provider": doc["war_provider"],
            "stamp": {"through": cur["through"], "ewar_vintage": vint,
                      "frozen_at": (freeze_blk or {}).get("frozen_at"),
                      "projections_build": _proj_stamp(ctx), "preseason_file": None,
                      "stint_frames": {"provider": ctx.provider, "stale": _served_stale()}},
            "freeze": freeze_blk,
            "selection_caption": A.selection_caption(S, frozen is not None),
            "stamps": None, "registry": doc["registry"],
            "ballot_rules": doc["ballot_rules"], "rules": cur["rules"], "awards": cur["awards"],
            "superlatives": doc["superlatives"], "race": doc["race"], "vote_table": vote_table,
            "credits": doc["credits"],
            "what_this_page_does_not_claim": doc["what_this_page_does_not_claim"],
        }
        payload["stamps"] = dict(sorted(ctx.inp.stamps.items()))
        raw_awards = _dump(payload)
        files["awards.json"] = raw_awards
        if frozen is not None:
            name = f"awards_{S}.json"
            if not (out / name).exists():
                sd = dict(doc, generated_at=str(record.get("frozen_at")), status="frozen")
                sd["stamp"] = dict(sd["stamp"], frozen_at=record.get("frozen_at"))
                files[name] = _dump(sd)
        for Sp in range(SELECTOR_FIRST, S):
            p = built[Sp]
            if "world" not in p:
                continue
            sd = _shard_doc(ctx, p, status="closed", generated_at=f"{Sp}-closed")
            files[f"awards_{Sp}.json"] = _dump(sd)
        n_rows = 0
        for Sp in range(SELECTOR_FIRST, S + 1):
            p = built[Sp]
            if "world" not in p:
                p = _season_payload(ctx, Sp)
            cand = _candidates(ctx, p, generated_at)
            n_rows += _n_rows(cand) if Sp == S else 0
            files[f"awards_candidates_{Sp}.json"] = _dump(cand)
        files["awards_eval.json"] = _dump(_eval_doc(ctx, cur, i1, copies, labs, generated_at))
        over = [f"{k} {len(v):,} bytes" for k, v in files.items()
                if (k == "awards.json" and len(v) > AWARDS_MAX_BYTES)
                or (k.startswith("awards_candidates_") and len(v) > CANDIDATES_MAX_BYTES)]
        if over:
            raise AwardsRefusal("payload over its size line: " + ", ".join(over))
    except AwardsRefusal as e:
        log(f"  awards board REFUSED: {e}; the previous files stand")
        return {"ok": False, "reason": str(e), "message": f"refused: {e}", "n_rows": 0,
                "out_dir": str(out), "files": {}, "top3": {}, "status": None}
    for name, raw in files.items():
        _write_bytes(out / name, raw)
    vintage = None
    if ctx.pending_vintage is not None:
        wrote = write_vintage(ctx.vintage_dir, ctx.pending_vintage)
        vintage = str(Path(ctx.vintage_dir) / f"{ctx.pending_vintage['date']}.json")
        log(f"  awards: vintage {ctx.pending_vintage['date']} "
            + ("written" if wrote else "already on file (first write wins)"))
    top3 = {f"{a}_{lg}": [r.get("name") for r in blk["top"][:3]]
            for a, by in cur["awards"].items() for lg, blk in by.items()}
    win = ctx.winners or {}
    msg = (f"{n_rows} candidate rows for {S}; award_winners.json "
           + (f"fetched {win.get('fetched_at')}, seasons {_span(win.get('seasons'))}"
              if win else "absent"))
    log(f"  awards: {msg}; wrote {len(files)} files to {out}")
    return {"ok": True, "reason": None, "message": msg, "n_rows": n_rows, "out_dir": str(out),
            "files": {k: len(v) for k, v in files.items()}, "top3": top3,
            "status": payload["status"], "vintage": vintage}


def _span(seasons) -> str:
    s = sorted(int(x) for x in (seasons or []))
    if not s:
        return "none"
    return f"{s[0]} to {s[-1]}" if len(s) > 1 else str(s[0])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the Awards board payloads.")
    ap.add_argument("--season", type=int, default=None)
    ap.add_argument("--freeze", type=int, default=None, metavar="S",
                    help="write data/_labs/awards/frozen_<S>.json once")
    a = ap.parse_args(argv)
    if a.freeze is not None:
        res = freeze(a.freeze)
    else:
        res = export(season=a.season)
    print(json.dumps({k: v for k, v in res.items() if k != "files"}, indent=1, ensure_ascii=False))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
