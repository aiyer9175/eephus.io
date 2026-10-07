# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Scores: the pure core (SCORES_1_CORE_RULES, plan SCORES_PLAN.md sections 4, 7, 8).

Standard library only, no network, no clock, no file I/O: every payload and every
path is passed in by the caller (the scores job, SCORES_2). The module holds:

  1. the state rule (`game_state`): final when `codedGameState` is F or O or
     `detailedState` starts with "Completed Early"; postponed (D), cancelled (C)
     and Suspended are never final although MLB marks postponed and cancelled
     games `abstractGameState` Final; Warmup is `abstractGameState` Live before
     any pitch and renders as pregame until the first pitch;
  2. MLB's win probability series (`wp_series`): integers in thousandths of
     `homeTeamWinProbability` after each COMPLETED plate appearance; an
     in-progress element is never a point and never credited; the pregame point
     is the first element's value minus its added value; MLB values only, a
     missing value stays null (no house fallback, conflict 25);
  3. per-play credit and per-player WPA and pLI with mlb_leverage's attribution
     (`a = homeTeamWinProbabilityAdded / 100`; the batter gets `a` when home bats,
     else `-a`; the pitcher of record at the plate appearance's end gets the
     negative; keyed (player, club)) and `unattributed_home`, so the home players'
     WPA plus it equals final minus pregame;
  4. `bp_v1`, the five biggest plays from the batting club's view;
  5. `stars_v1`, Stars of the Game, exactly as the plan's section 7.1 states it
     (the literals below are pinned to that text by a test);
  6. the why sentences built from the boxscore's numeric fields, never MLB's
     summary string;
  7. `play_text`, a constant table over StatsAPI `eventType` plus RBI and the
     runners who scored; never MLB's description, headline, blurb, title,
     kicker or summary;
  8. the card, date-file and game-file builders of plan 8.2 and 8.3 and the
     validator of plan 8.5 (every rule but the on-disk ones, which the job adds);
  9. clubs by MLBAM team id through a 30-entry literal pinned by a test to
     `trades.canonical_org_from_id` and to the 30 codes of the franchise board.

Every win-probability quantity (`wp_home`, `before`, `after`, `swing`, a star's
`score`, `pregame_home`, `unattributed_home`, box WPA) is an integer in
thousandths, so MLB's one-decimal percentages survive exactly. LI keeps two
decimals. The validator and the club literal are written so a second payload
family (Scores / Standings, STANDINGS_1_CORE_RULES) can register its own file
kinds and budgets through `register_file_kind` and reuse the file-independent
rules through `validate_payload`.

The module flag `SCORES_LIVE` defaults to False: while it is False nothing
scores-related is served, the job writes only under `.cache/scores/preview/`,
and no page, publish path, registry row or glossary entry exists. Only the
flip task turns it on.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re

# --------------------------------------------------------------------------- #
# Flags and frozen literals
# --------------------------------------------------------------------------- #

#: Class 2 module flag (Part 8 8.A). False until SCORES_5a_LIVE_FLIP.
SCORES_LIVE = False

#: Video embed default (plan 6.7). The job also reads an override from outside
#: the repo; the effective value is published as `index.json.rules.video.embed`.
SCORES_EMBED_VIDEO = True
#: ISO date of the owner's re-confirmation of embedding once the Diamond gate
#: reads on (SC-PAID tripwire, plan 6.7); empty until then.
SCORES_EMBED_RECONFIRMED = ""

SCHEMA = 1

#: stars_v1 (plan 7.1; owner answer SC-STARS). Frozen: from the first public
#: serve any change is `stars_v2`, dated, with a same-day note.
STARS_RULE = "stars_v1"
MIN_OUTS = 15
MIN_COVERAGE = 0.95
FIRST_STAR_WINNER = True
SCORE_DECIMALS = 3            # rounding to 0.001 (scores ship as thousandths)
STAR_ORDER = ("score", "avg_li", "best_credit", "first_ab", "id")
MAX_STARS = 3

#: bp_v1 (plan 7.2).
PLAYS_RULE = "bp_v1"
MIN_SWING = 30                # |a| >= 0.03, in thousandths
N_BIG_PLAYS = 5

#: Card states (plan 8.2).
STATES = ("scheduled", "pregame", "delayed", "live", "final", "postponed",
          "suspended", "cancelled")

#: Stars reasons and the withheld-plays reason (plan 10, copy as drafted).
REASON_NOT_FINAL = "Stars post when the game is final."
REASON_COVERAGE = "No stars: MLB's win probability feed is incomplete for this game."
REASON_TIE = "No stars for a tie."
REASON_NO_WINNER_CANDIDATE = "No stars: no player on the winning team scored above zero."
PLAYS_REASON_COVERAGE = ("Biggest plays withheld: MLB's win probability feed is "
                         "incomplete for this game.")

#: The sentence the page prints beside the stars when star 1 scores below star 2.
FIRST_STAR_NOTE_TEXT = "First star: top player on the winning team."

#: Text normalisation of MLB-supplied strings (plan 8.2): U+2013 and U+2014
#: become a hyphen-minus before validation, so rule 10 never refuses MLB's own
#: punctuation.
_DASHES = (chr(0x2013), chr(0x2014))

#: The copyright terms URL StatsAPI's line cites (rule 4's one exemption).
MLB_TERMS_URL = "http://gdx.mlb.com/components/copyright.txt"

# --------------------------------------------------------------------------- #
# Clubs (plan 8.2): MLBAM team id -> the site's canonical 3-letter code.
# Pinned by a test to trades.canonical_org_from_id for every key and to the 30
# codes of data/franchise_board.json. Placeholders such as id 5528 ("HOU/CWS")
# are not in the table and give None. Never trades.canonical_org, never MLB's
# abbreviation (CWS, AZ, KC, SD, SF, TB, WSH are StatsAPI codes, not ours).
# --------------------------------------------------------------------------- #
CLUB_BY_ID = {
    108: "LAA", 109: "ARI", 110: "BAL", 111: "BOS", 112: "CHC", 113: "CIN",
    114: "CLE", 115: "COL", 116: "DET", 117: "HOU", 118: "KCR", 119: "LAD",
    120: "WSN", 121: "NYM", 133: "ATH", 134: "PIT", 135: "SDP", 136: "SEA",
    137: "SFG", 138: "STL", 139: "TBR", 140: "TEX", 141: "TOR", 142: "MIN",
    143: "PHI", 144: "ATL", 145: "CHW", 146: "MIA", 147: "NYY", 158: "MIL",
}


def club_code(team_id) -> str | None:
    """The canonical code for an MLBAM team id; None for a placeholder or an
    unknown id (never a name lookup, never MLB's abbreviation)."""
    try:
        return CLUB_BY_ID.get(int(team_id))
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def normalize_text(s):
    """MLB-supplied string with U+2013 and U+2014 replaced by a hyphen-minus.
    None and non-strings pass through unchanged."""
    if not isinstance(s, str):
        return s
    for d in _DASHES:
        if d in s:
            s = s.replace(d, "-")
    return s


def round_half_up(x: float) -> int:
    """Half-up (ties toward +infinity), the build_site._round_half_up rule."""
    return int(math.floor(x + 0.5))


def thousandths(x) -> int | None:
    """An MLB percentage (52.2) or added value (2.200000000000003) as an
    integer in thousandths (522, 22); None stays None."""
    if x is None:
        return None
    try:
        return round_half_up(float(x) * 10.0)
    except (TypeError, ValueError):
        return None


def wins_to_thousandths(x: float) -> int:
    """A win-unit quantity (0.5134) as thousandths (513), half-up."""
    return round_half_up(x * 1000.0)


def pct_of_thousandths(v: int) -> int:
    """A thousandths value as a whole percentage, rounded half up (293 -> 29)."""
    return round_half_up(v / 10.0)


def ordinal(n) -> str:
    n = int(n)
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _ip(outs: int) -> str:
    """Innings pitched from outs: `outs // 3` "." `outs % 3`."""
    outs = int(outs or 0)
    return f"{outs // 3}.{outs % 3}"


def _int(x, default=0) -> int:
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def _person(d) -> dict | None:
    if not isinstance(d, dict) or d.get("id") is None:
        return None
    return {"id": int(d["id"]), "name": normalize_text(d.get("fullName"))}


def dumps(obj) -> str:
    """The one serializer: compact, sorted keys, UTF-8 characters kept, NaN
    refused. Budgets, revs and the job's bytes all come from it."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def rev_of(obj) -> str:
    """A short content hash of a payload (the first 12 hex of sha1 over
    `dumps`). The job uses the same function over the bytes it writes."""
    data = obj if isinstance(obj, (bytes, bytearray)) else dumps(obj).encode("utf-8")
    return hashlib.sha1(data).hexdigest()[:12]


# --------------------------------------------------------------------------- #
# 1. The state rule
# --------------------------------------------------------------------------- #
def game_state(status: dict | None) -> tuple[str, str | None]:
    """(state, reason) for a StatsAPI `status` object.

    Final only when `codedGameState` is F or O or `detailedState` starts with
    "Completed Early". Suspended, postponed (D) and cancelled (C) are checked
    first and are never final, although MLB marks postponed and cancelled games
    `abstractGameState` Final. Warmup (abstract Live, coded P) is pregame until
    the first pitch. A delayed start or an in-game delay is `delayed`.
    """
    st = status or {}
    coded = str(st.get("codedGameState") or "")
    detailed = normalize_text(str(st.get("detailedState") or ""))
    abstract = str(st.get("abstractGameState") or "")
    reason = normalize_text(st.get("reason")) or None
    low = detailed.lower()
    if low.startswith("suspended"):
        return "suspended", reason
    if coded == "D" or low.startswith("postponed"):
        return "postponed", reason
    if coded == "C" or low.startswith("cancelled") or low.startswith("canceled"):
        return "cancelled", reason
    if coded in ("F", "O") or low.startswith("completed early"):
        return "final", reason
    if low.startswith("delayed"):
        return "delayed", reason
    if low.startswith("warmup"):
        return "pregame", None
    if abstract == "Live" or coded in ("I", "M", "N"):
        return "live", reason
    if low.startswith("pre-game") or coded == "P":
        return "pregame", None
    return "scheduled", reason


def is_final(status: dict | None) -> bool:
    return game_state(status)[0] == "final"


# --------------------------------------------------------------------------- #
# 2. Win probability from MLB's elements
# --------------------------------------------------------------------------- #
def elements_of(payload) -> list:
    """The play list of a winProbability payload (a bare list, or a dict with
    the `winProbability` key), sorted by atBatIndex so input order never matters."""
    if isinstance(payload, dict):
        payload = payload.get("winProbability") or []
    plays = [p for p in (payload or []) if isinstance(p, dict)]
    return sorted(plays, key=lambda p: _int(p.get("atBatIndex"), 0))


def complete_elements(payload) -> list:
    """Only the completed plate appearances (`about.isComplete` true). The
    in-progress last element of a live read is never a point and never
    credited. An element with no `about.isComplete` key is treated as complete
    (the saved final reads carry the key on every element)."""
    out = []
    for p in elements_of(payload):
        about = p.get("about") or {}
        if about.get("isComplete", True):
            out.append(p)
    return out


def _half(p) -> str:
    about = p.get("about") or {}
    half = about.get("halfInning")
    if half:
        return "bottom" if str(half).lower() == "bottom" else "top"
    return "top" if about.get("isTopInning", True) else "bottom"


def _inning(p) -> int:
    return _int((p.get("about") or {}).get("inning"), 0)


def _ab(p) -> int:
    return _int(p.get("atBatIndex", (p.get("about") or {}).get("atBatIndex")), 0)


def wp_series(payload) -> dict:
    """MLB's win probability series over the completed plate appearances.

    Returns `{pregame_home, series [[ab, inning, half, wp_home, swing]],
    coverage {mlb, of}, last {ab, wp_home} | None}`. `wp_home` and `swing` are
    integers in thousandths (None where MLB has no value; a gap, never a
    model estimate). `pregame_home` is the first element's value minus its
    added value, None when either is missing. `coverage.mlb` counts completed
    plate appearances carrying both values; `coverage.of` counts them all.
    """
    plays = complete_elements(payload)
    series = []
    n_mlb = 0
    pregame = None
    for i, p in enumerate(plays):
        wp = thousandths(p.get("homeTeamWinProbability"))
        added = thousandths(p.get("homeTeamWinProbabilityAdded"))
        if wp is not None and added is not None:
            n_mlb += 1
            if i == 0:
                pregame = wp - added
        series.append([_ab(p), _inning(p), _half(p), wp, added])
    last = None
    for row in reversed(series):
        if row[3] is not None:
            last = {"ab": row[0], "wp_home": row[3]}
            break
    return {"pregame_home": pregame, "series": series,
            "coverage": {"mlb": n_mlb, "of": len(plays)}, "last": last}


def coverage_ok(cov: dict) -> bool:
    of = _int(cov.get("of"), 0)
    return of > 0 and _int(cov.get("mlb"), 0) / of >= MIN_COVERAGE


# --------------------------------------------------------------------------- #
# 3. Credit per play, WPA and pLI per (player, club)
# --------------------------------------------------------------------------- #
def play_credits(payload) -> list[dict]:
    """One row per completed plate appearance: `{ab, inning, half, batter,
    pitcher, bat_side, a, credit, li}`; `a` is MLB's added value in wins
    (home view) and `credit` the batting club's view (`a` when home bats, else
    `-a`); both None when MLB has no value. The pitcher of record at the end of
    the plate appearance (`matchup.pitcher`) is the one credited the negative."""
    rows = []
    for p in complete_elements(payload):
        m = p.get("matchup") or {}
        added = p.get("homeTeamWinProbabilityAdded")
        a = None
        try:
            a = float(added) / 100.0 if added is not None else None
        except (TypeError, ValueError):
            a = None
        half = _half(p)
        bat_side = "home" if half == "bottom" else "away"
        credit = None if a is None else (a if bat_side == "home" else -a)
        li = p.get("leverageIndex")
        try:
            li = float(li) if li is not None else None
        except (TypeError, ValueError):
            li = None
        rows.append({"ab": _ab(p), "inning": _inning(p), "half": half,
                     "batter": _person(m.get("batter")),
                     "pitcher": _person(m.get("pitcher")),
                     "bat_side": bat_side, "a": a, "credit": credit, "li": li})
    return rows


def player_wpa(payload) -> dict:
    """Per (player id, side) accumulation in wins: `{wpa_bat, wpa_pit, li_bat
    [..], li_pit [..], best_credit, best_ab, first_ab, name}`. The attribution
    is mlb_leverage's: `_fold_game_batters` for batters, `_game_pitcher_dict`
    for pitchers, on completed elements. A missing value credits nobody."""
    acc: dict = {}

    def row(person, side):
        k = (person["id"], side)
        if k not in acc:
            acc[k] = {"id": person["id"], "side": side, "name": person["name"],
                      "wpa_bat": 0.0, "wpa_pit": 0.0, "li_bat": [], "li_pit": [],
                      "pa_bat": 0, "pa_pit": 0,
                      "best_credit": None, "best_ab": None, "first_ab": None}
        elif person.get("name"):
            acc[k]["name"] = person["name"]
        return acc[k]

    for r in play_credits(payload):
        b = row(r["batter"], r["bat_side"]) if r["batter"] else None
        q = row(r["pitcher"], "away" if r["bat_side"] == "home" else "home") if r["pitcher"] else None
        for x, li_key, pa_key in ((b, "li_bat", "pa_bat"), (q, "li_pit", "pa_pit")):
            if x is None:
                continue
            x[pa_key] += 1
            if x["first_ab"] is None:
                x["first_ab"] = r["ab"]
            if r["li"] is not None:
                x[li_key].append(r["li"])
        if r["credit"] is None:
            continue
        if b is not None:
            b["wpa_bat"] += r["credit"]
            if b["best_credit"] is None or r["credit"] > b["best_credit"]:
                b["best_credit"], b["best_ab"] = r["credit"], r["ab"]
        if q is not None:
            q["wpa_pit"] -= r["credit"]
            if q["best_credit"] is None or -r["credit"] > q["best_credit"]:
                q["best_credit"], q["best_ab"] = -r["credit"], r["ab"]
    return acc


def unattributed_home(payload) -> int | None:
    """Final home value minus the pregame point minus every home player's WPA,
    in thousandths: the part of the move MLB's elements do not attribute
    (base running inside a plate appearance, fielding, a value trailing the
    score by one play). None when the series has no values."""
    ws = wp_series(payload)
    if ws["pregame_home"] is None or ws["last"] is None:
        return None
    home_sum = 0.0
    for (pid, side), r in player_wpa(payload).items():
        if side == "home":
            home_sum += r["wpa_bat"] + r["wpa_pit"]
    return ws["last"]["wp_home"] - ws["pregame_home"] - wins_to_thousandths(home_sum)


# --------------------------------------------------------------------------- #
# 7. Play text from fields (never MLB's description)
# --------------------------------------------------------------------------- #
#: StatsAPI eventType -> short phrase (the batter's name is prefixed; RBI and
#: the runners who scored are appended). Covers the result and the running
#: event types of /api/v1/eventTypes seen on the 2026 feeds.
EVENT_PHRASES = {
    # plate-appearance results
    "single": "single", "double": "double", "triple": "triple",
    "home_run": "home run", "walk": "walk", "intent_walk": "intentional walk",
    "hit_by_pitch": "hit by pitch", "strikeout": "struck out",
    "strike_out": "struck out", "strikeout_double_play": "struck out, double play",
    "strikeout_triple_play": "struck out, triple play",
    "field_out": "out", "force_out": "forceout", "fielders_choice": "fielder's choice",
    "fielders_choice_out": "fielder's choice, out at the base",
    "grounded_into_double_play": "grounded into a double play",
    "grounded_into_triple_play": "grounded into a triple play",
    "double_play": "double play", "triple_play": "triple play",
    "sac_fly": "sacrifice fly", "sac_fly_double_play": "sacrifice fly, double play",
    "sac_bunt": "sacrifice bunt", "sac_bunt_double_play": "sacrifice bunt, double play",
    "field_error": "reached on an error", "error": "error",
    "catcher_interf": "reached on catcher's interference",
    "batter_interference": "out, batter's interference",
    "fan_interference": "fan interference", "runner_interference": "runner's interference",
    "other_out": "out", "batter_out": "out",
    # running events (an element whose result is a running play, or an event
    # inside a plate appearance)
    "stolen_base": "stolen base", "stolen_base_2b": "stole second",
    "stolen_base_3b": "stole third", "stolen_base_home": "stole home",
    "caught_stealing": "caught stealing", "caught_stealing_2b": "caught stealing second",
    "caught_stealing_3b": "caught stealing third", "caught_stealing_home": "caught stealing home",
    "cs_double_play": "caught stealing, double play",
    "pickoff": "picked off", "pickoff_1b": "picked off first", "pickoff_2b": "picked off second",
    "pickoff_3b": "picked off third",
    "pickoff_caught_stealing_2b": "picked off, caught stealing second",
    "pickoff_caught_stealing_3b": "picked off, caught stealing third",
    "pickoff_caught_stealing_home": "picked off, caught stealing home",
    "pickoff_error_1b": "pickoff error at first", "pickoff_error_2b": "pickoff error at second",
    "pickoff_error_3b": "pickoff error at third", "pickoff_attempt": "pickoff attempt",
    "wild_pitch": "wild pitch", "passed_ball": "passed ball", "balk": "balk",
    "forced_balk": "balk", "other_advance": "runner advanced",
    "runner_double_play": "runner doubled off", "runner_placed": "automatic runner placed",
    "defensive_indiff": "advanced on defensive indifference",
    "runner_out": "runner out", "stolen_base_attempt": "stolen base attempt",
    # game events (an element that is not a plate appearance)
    "game_advisory": "game advisory", "ejection": "ejection", "injury": "injury delay",
    "umpire_substitution": "umpire change", "mound_visit": "mound visit",
    "pitching_substitution": "pitching change", "offensive_substitution": "pinch hitter",
    "defensive_substitution": "defensive substitution", "defensive_switch": "defensive switch",
    "batter_timeout": "batter timeout", "no_pitch": "no pitch",
    "pitcher_step_off": "pitcher stepped off", "pitcher_switch": "pitcher switched hands",
    "at_bat_start": "plate appearance", "umpire_review": "umpire review",
    "manager_challenge": "manager challenge", "abs_challenge": "ABS challenge",
    "os_ruling_pending_prior": "ruling pending", "os_ruling_pending_primary": "ruling pending",
}

#: `result.event` labels that refine a `field_out` (a short category label,
#: not prose); anything else prints "out".
FIELD_OUT_LABELS = {
    "Flyout": "flyout", "Groundout": "groundout", "Lineout": "lineout",
    "Pop Out": "pop out", "Bunt Groundout": "bunt groundout",
    "Bunt Pop Out": "bunt pop out", "Bunt Lineout": "bunt lineout",
    "Forceout": "forceout", "Sac Fly": "sacrifice fly", "Sac Bunt": "sacrifice bunt",
}

#: Events whose phrase already names the batter's act in the past tense.
_PAST_TENSE = {"strikeout", "strike_out", "strikeout_double_play", "strikeout_triple_play",
               "grounded_into_double_play", "grounded_into_triple_play",
               "field_error", "catcher_interf", "batter_interference",
               "stolen_base_2b", "stolen_base_3b", "stolen_base_home",
               "caught_stealing", "caught_stealing_2b", "caught_stealing_3b",
               "caught_stealing_home", "pickoff", "pickoff_1b", "pickoff_2b", "pickoff_3b",
               "pickoff_caught_stealing_2b", "pickoff_caught_stealing_3b",
               "pickoff_caught_stealing_home", "defensive_indiff", "pitcher_step_off",
               "pitcher_switch", "other_advance", "runner_double_play"}


def _strikeout_flavor(play: dict) -> str:
    """"swinging" or "looking" from the final pitch's call code (full form) or
    its call label (the fields= form); empty when neither is present."""
    events = play.get("playEvents") or []
    for e in reversed(events):
        if not e.get("isPitch"):
            continue
        det = e.get("details") or {}
        code = str(det.get("code") or (det.get("call") or {}).get("code") or "")
        label = str(det.get("description") or "").lower()
        if code in ("S", "W", "T", "M") or "swing" in label or "foul tip" in label or "missed bunt" in label:
            return "swinging"
        if code == "C" or "called" in label:
            return "looking"
        break
    return ""


def event_phrase(play: dict) -> str:
    """The phrase for a play's `result.eventType`, refined by its `result.event`
    label for a field out and by the final pitch for a strikeout."""
    result = play.get("result") or {}
    et = str(result.get("eventType") or "")
    if et == "field_out":
        return FIELD_OUT_LABELS.get(str(result.get("event") or ""), "out")
    if et in ("strikeout", "strike_out"):
        flavor = _strikeout_flavor(play)
        return "struck out " + flavor if flavor else "struck out"
    phrase = EVENT_PHRASES.get(et)
    if phrase is None:
        phrase = et.replace("_", " ") if et else "play"
    return phrase


_SUFFIXES = ("Jr.", "Sr.", "II", "III", "IV")


def last_name_map(feed: dict | None = None, boxscore: dict | None = None) -> dict:
    """MLBAM id -> the surname the play text prints: the feed's
    `gameData.players[].useLastName` (then `lastName`) when the feed is in
    hand, else the boxscore's `person.boxscoreName` with its ", X" initial
    removed. Names the map lacks fall back to `short_name` on the element's
    own `fullName`."""
    out: dict = {}
    for side in ("away", "home"):
        players = ((((boxscore or {}).get("teams") or {}).get(side) or {}).get("players")) or {}
        for p in players.values():
            person = p.get("person") or {}
            bn = normalize_text(person.get("boxscoreName"))
            if person.get("id") is not None and bn:
                out[int(person["id"])] = _strip_suffix(bn.split(",")[0].strip())
    for p in (((feed or {}).get("gameData") or {}).get("players") or {}).values():
        ln = normalize_text(p.get("useLastName") or p.get("lastName"))
        if p.get("id") is not None and ln:
            out[int(p["id"])] = _strip_suffix(ln)
    return out


def _strip_suffix(name: str) -> str:
    """"Harris II" -> "Harris", "Witt Jr." -> "Witt"; a multi-word surname
    ("De La Cruz") is kept whole."""
    parts = [t for t in (name or "").split(" ") if t]
    while len(parts) >= 2 and parts[-1] in _SUFFIXES:
        parts.pop()
    return " ".join(parts)


def short_name(full: str | None) -> str:
    """The last token of a full name, skipping a generational suffix
    ("Michael Harris II" -> "Harris"); the fallback when no map names him."""
    parts = _strip_suffix(normalize_text(full) or "").split(" ")
    return parts[-1] if parts and parts[-1] else ""


def _name_of(person, names: dict | None) -> str:
    person = person or {}
    pid = person.get("id")
    if names and pid is not None:
        try:
            got = names.get(int(pid))
        except (TypeError, ValueError):
            got = None
        if got:
            return got
    return short_name(person.get("fullName") or person.get("name"))


def _runner_scorers(play: dict, names: dict | None) -> list[str]:
    """The runners who scored on the play (`runners[].movement.end` "score"),
    the batter himself excluded (a home run names him once, as the batter)."""
    batter_id = ((play.get("matchup") or {}).get("batter") or {}).get("id")
    out = []
    seen = set()
    for r in play.get("runners") or []:
        mv = r.get("movement") or {}
        if mv.get("end") != "score":
            continue
        runner = (r.get("details") or {}).get("runner") or {}
        rid = runner.get("id")
        if rid is None or rid in seen or rid == batter_id:
            continue
        seen.add(rid)
        out.append(_name_of(runner, names) or "Runner")
    return out


def _join_names(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def play_text(play: dict, names: dict | None = None) -> str:
    """"Riley home run, 3 RBI. Harris and Albies scored." built from
    `matchup.batter`, `result.eventType`, `result.event`, `result.rbi` and
    `runners[].movement.end`. Never MLB's `description`. `names` is
    `last_name_map(feed, boxscore)` when the caller has either."""
    result = play.get("result") or {}
    m = play.get("matchup") or {}
    batter = _name_of(m.get("batter"), names)
    et = str(result.get("eventType") or "")
    phrase = event_phrase(play)
    if et in _PAST_TENSE or phrase.startswith("struck out"):
        head = f"{batter} {phrase}" if batter else phrase[:1].upper() + phrase[1:]
    elif et in ("game_advisory", "ejection", "injury", "umpire_substitution",
                "mound_visit", "pitching_substitution", "offensive_substitution",
                "defensive_substitution", "defensive_switch", "batter_timeout",
                "no_pitch", "umpire_review", "manager_challenge", "abs_challenge",
                "os_ruling_pending_prior", "os_ruling_pending_primary", "runner_placed",
                "wild_pitch", "passed_ball", "balk", "forced_balk", "error", "at_bat_start"):
        head = phrase[:1].upper() + phrase[1:]
    else:
        head = f"{batter} {phrase}" if batter else phrase[:1].upper() + phrase[1:]
    rbi = _int(result.get("rbi"), 0)
    if rbi > 0:
        head += f", {rbi} RBI"
    text = head + "."
    scorers = _runner_scorers(play, names)
    if scorers:
        text += f" {_join_names(scorers)} scored."
    return text


# --------------------------------------------------------------------------- #
# The situation before and after each plate appearance (plan 8.3)
# --------------------------------------------------------------------------- #
def auto_runner(season, game_type) -> bool:
    """The automatic runner on second at an extra half-inning's start applies
    to regular-season games from 2020; postseason extra innings start empty."""
    return str(game_type or "R") == "R" and _int(season, 0) >= 2020


def _bases_after(play: dict) -> list[bool]:
    m = play.get("matchup") or {}
    return [bool(m.get("postOnFirst")), bool(m.get("postOnSecond")), bool(m.get("postOnThird"))]


def situations(payload, *, season=None, game_type="R", scheduled_innings=9) -> list[dict]:
    """Per completed element: the situation before (from the previous element's
    post state, reset at each half-inning; the automatic runner on second at a
    regular-season extra half-inning start, empty bases in a postseason one)
    and after. Each row: `{ab, inning, half, outs_before, bases_before,
    away_before, home_before, outs_after, bases_after, away_after, home_after}`."""
    rows = []
    prev = None
    prev_key = None
    sched = _int(scheduled_innings, 9) or 9
    for p in complete_elements(payload):
        inning, half = _inning(p), _half(p)
        key = (inning, half)
        res = p.get("result") or {}
        if prev is not None and key == prev_key:
            outs_b = _int((prev.get("count") or {}).get("outs"), 0)
            bases_b = _bases_after(prev)
            away_b = _int((prev.get("result") or {}).get("awayScore"), 0)
            home_b = _int((prev.get("result") or {}).get("homeScore"), 0)
        else:
            outs_b = 0
            bases_b = [False, False, False]
            if inning > sched and auto_runner(season, game_type):
                bases_b = [False, True, False]
            if prev is not None:
                away_b = _int((prev.get("result") or {}).get("awayScore"), 0)
                home_b = _int((prev.get("result") or {}).get("homeScore"), 0)
            else:
                away_b, home_b = 0, 0
        rows.append({"ab": _ab(p), "inning": inning, "half": half,
                     "outs_before": outs_b, "bases_before": bases_b,
                     "away_before": away_b, "home_before": home_b,
                     "outs_after": _int((p.get("count") or {}).get("outs"), outs_b),
                     "bases_after": _bases_after(p),
                     "away_after": _int(res.get("awayScore"), away_b),
                     "home_after": _int(res.get("homeScore"), home_b)})
        prev, prev_key = p, key
    return rows


# --------------------------------------------------------------------------- #
# Per-play rows (the Plays tab) and 4. bp_v1
# --------------------------------------------------------------------------- #
def play_rows(payload, codes: dict, *, season=None, game_type="R", scheduled_innings=9,
              names: dict | None = None) -> list[dict]:
    """Every completed plate appearance as a plays-tab row (plan 8.3):
    `{ab, inning, half, text, outs, bases, away, home, wp, swing, li, clip,
    event_clips, reviews, bat_team, before, after, situation}`. `wp` is MLB's
    home value after the play; `before`, `after` and `swing` read from the
    batting club's view (conflict 23); all in thousandths, None for a gap."""
    sits = situations(payload, season=season, game_type=game_type,
                      scheduled_innings=scheduled_innings)
    rows = []
    for p, s in zip(complete_elements(payload), sits):
        wp = thousandths(p.get("homeTeamWinProbability"))
        added = thousandths(p.get("homeTeamWinProbabilityAdded"))
        bottom = s["half"] == "bottom"
        bat_side = "home" if bottom else "away"
        before = after = swing = None
        if wp is not None and added is not None:
            before_home = wp - added
            before = before_home if bottom else 1000 - before_home
            after = wp if bottom else 1000 - wp
            swing = after - before
        li = p.get("leverageIndex")
        try:
            li = round(float(li), 2) if li is not None else None
        except (TypeError, ValueError):
            li = None
        reviews = []
        rd = p.get("reviewDetails")
        if isinstance(rd, dict):
            reviews.append({"by": club_code(rd.get("challengeTeamId")),
                            "overturned": bool(rd.get("isOverturned")),
                            "kind": normalize_text(rd.get("reviewType"))})
        lead = (s["home_before"] - s["away_before"]) if bottom else (s["away_before"] - s["home_before"])
        rows.append({
            "ab": s["ab"], "inning": s["inning"], "half": s["half"],
            "text": play_text(p, names),
            "outs": s["outs_after"], "bases": s["bases_after"],
            "away": s["away_after"], "home": s["home_after"],
            "wp": wp, "swing": swing, "li": li,
            "clip": None, "event_clips": [], "reviews": reviews,
            "bat_team": codes.get(bat_side), "before": before, "after": after,
            "situation": {"outs": s["outs_before"], "bases": s["bases_before"], "lead": lead},
            "scored": (s["away_after"] + s["home_after"]) > (s["away_before"] + s["home_before"]),
        })
    return rows


def _big_key(r: dict):
    return (-abs(r["swing"]), -(r["li"] if r["li"] is not None else -1.0), r["ab"])


def biggest_plays(rows: list[dict], *, n: int = N_BIG_PLAYS) -> list[dict]:
    """bp_v1 over plays-tab rows: completed plate appearances with an MLB value
    and |swing| >= 30 thousandths, by |swing| descending, LI descending,
    atBatIndex ascending; the top `n` as `{rank, ab, inning, half, situation,
    text, bat_team, before, after, swing, li, clip, clip_state}`."""
    cands = [r for r in rows if r.get("swing") is not None and abs(r["swing"]) >= MIN_SWING]
    cands.sort(key=_big_key)
    out = []
    for i, r in enumerate(cands[:n], start=1):
        out.append({"rank": i, "ab": r["ab"], "inning": r["inning"], "half": r["half"],
                    "situation": dict(r["situation"]), "text": r["text"],
                    "bat_team": r["bat_team"], "before": r["before"], "after": r["after"],
                    "swing": r["swing"], "li": r["li"], "clip": None, "clip_state": "pending"})
    return out


# --------------------------------------------------------------------------- #
# 5. stars_v1
# --------------------------------------------------------------------------- #
def _box_players(boxscore: dict, side: str) -> dict:
    return (((boxscore or {}).get("teams") or {}).get(side) or {}).get("players") or {}


def _box_entry(boxscore: dict, side: str, pid: int) -> dict:
    return _box_players(boxscore, side).get(f"ID{pid}") or {}


def runs_prevented(outs: int, runs: int, lg: dict) -> float:
    """The workhorse term in wins: `(outs / 3 * lg_ra9 / 9 - runs) / rpw`."""
    return (outs / 3.0 * float(lg["lg_ra9"]) / 9.0 - runs) / float(lg["rpw"])


def star_candidates(payload, boxscore: dict, lg: dict) -> list[dict]:
    """Every (player, club) with a positive stars_v1 score, in the rule's order.

    Score = batting WPA + pitching credit, where a pitcher with `outs >=
    MIN_OUTS` and pitching WPA `>= 0` is credited `max(WPA, runs prevented)`
    with runs as charged in the boxscore (`basis` records which); every other
    pitcher's credit is his WPA. Order: score rounded to 0.001 descending,
    then average LI of his plate appearances descending, then his largest
    single-play credit descending, then his first plate appearance ascending,
    then MLBAM id ascending.
    """
    rows = []
    for (pid, side), r in player_wpa(payload).items():
        pit = ((_box_entry(boxscore, side, pid).get("stats") or {}).get("pitching") or {})
        outs = _int(pit.get("outs"), 0)
        pitched = r["pa_pit"] > 0 or (bool(pit) and outs > 0)
        basis = "wpa"
        pitch_credit = r["wpa_pit"] if pitched else 0.0
        rp = None
        if pitched and outs >= MIN_OUTS and r["wpa_pit"] >= 0:
            rp = runs_prevented(outs, _int(pit.get("runs"), 0), lg)
            if rp > r["wpa_pit"]:
                pitch_credit, basis = rp, "runs"
        score = r["wpa_bat"] + pitch_credit
        li = r["li_bat"] + r["li_pit"]
        rows.append({
            "id": pid, "side": side, "name": r["name"],
            "score_m": wins_to_thousandths(score),
            "score": round(score, SCORE_DECIMALS),
            "wpa_bat": r["wpa_bat"], "wpa_pit": r["wpa_pit"] if pitched else None,
            "runs_prevented": rp, "basis": basis, "pitched": pitched, "outs": outs,
            "avg_li": (sum(li) / len(li)) if li else 0.0,
            "best_credit": r["best_credit"] if r["best_credit"] is not None else 0.0,
            "best_ab": r["best_ab"], "first_ab": r["first_ab"] if r["first_ab"] is not None else 10 ** 9,
        })
    cands = [c for c in rows if c["score_m"] > 0]
    cands.sort(key=lambda c: (-c["score_m"], -c["avg_li"], -c["best_credit"], c["first_ab"], c["id"]))
    return cands


def pick_stars(cands: list[dict], winner_side: str) -> list[dict]:
    """The first star is the top candidate from the winning club; the second
    and third are the next two by the order from either club; fewer when fewer
    qualify. The display order is star 1, 2, 3 and is not a score ranking."""
    first = next((c for c in cands if c["side"] == winner_side), None) if FIRST_STAR_WINNER else (cands[0] if cands else None)
    if first is None:
        return []
    rest = [c for c in cands if c is not first]
    return [first] + rest[:MAX_STARS - 1]


# --------------------------------------------------------------------------- #
# 6. Why sentences (module_design 5.4), from the boxscore's numeric fields
# --------------------------------------------------------------------------- #
def _qualifier(row: dict, ended_game: bool) -> str:
    """"Walk-off", "Go-ahead", "Game-tying" or "" from the score before and
    after the batting club's best plate appearance."""
    s = row["situation"]
    lead_before = s["lead"]
    bottom = row["half"] == "bottom"
    lead_after = (row["home"] - row["away"]) if bottom else (row["away"] - row["home"])
    if lead_before <= 0 < lead_after:
        return "Walk-off" if (ended_game and bottom) else "Go-ahead"
    if lead_before < 0 and lead_after == 0:
        return "Game-tying"
    return ""


def hitter_sentence(bat: dict, best_row: dict | None, club: str, ended_game: bool) -> str:
    h, ab = _int(bat.get("hits"), 0), _int(bat.get("atBats"), 0)
    parts = [f"{h}-for-{ab}"]
    for key, label in (("doubles", "2B"), ("triples", "3B"), ("homeRuns", "HR")):
        n = _int(bat.get(key), 0)
        if n == 1:
            parts.append(label)
        elif n > 1:
            parts.append(f"{n} {label}")
    rbi = _int(bat.get("rbi"), 0)
    if rbi == 1:
        parts.append("RBI")
    elif rbi > 1:
        parts.append(f"{rbi} RBI")
    bb = _int(bat.get("baseOnBalls"), 0)
    if bb == 1:
        parts.append("BB")
    elif bb > 1:
        parts.append(f"{bb} BB")
    first = ", ".join(parts) + "."
    if best_row is None or best_row.get("before") is None:
        return first
    q = _qualifier(best_row, ended_game)
    ev = best_row["event_phrase"]
    ev_text = (q + " " + ev) if q else (ev[:1].upper() + ev[1:])
    return (f"{first} {ev_text} in the {ordinal(best_row['inning'])}, {club} "
            f"{pct_of_thousandths(best_row['before'])}% to {pct_of_thousandths(best_row['after'])}%.")


def _innings_text(innings: list[int]) -> str:
    inns = sorted(set(int(i) for i in innings))
    if not inns:
        return ""
    if len(inns) == 1:
        return ordinal(inns[0])
    if len(inns) == 2:
        return f"{ordinal(inns[0])} and {ordinal(inns[1])}"
    return f"{ordinal(inns[0])} to {ordinal(inns[-1])}"


def runs_saved(outs: int, runs: int, lg: dict) -> float:
    """RS = outs / 3 * lg_ra9 / 9 - runs (the runs term before dividing by rpw)."""
    return outs / 3.0 * float(lg["lg_ra9"]) / 9.0 - runs


def pitcher_sentence(pit: dict, basis: str, lg: dict, innings: list[int]) -> str:
    outs = _int(pit.get("outs"), 0)
    k = _int(pit.get("strikeOuts"), 0)
    r = _int(pit.get("runs"), 0)
    pc = _int(pit.get("numberOfPitches", pit.get("pitchesThrown")), 0)
    started = _int(pit.get("gamesStarted"), 0) >= 1
    if basis == "runs":
        return (f"{_ip(outs)} IP, {r} R, {k} K on {pc} pitches: {_fmt1(runs_saved(outs, r, lg))} "
                f"runs better than the league rate over his innings.")
    if started or outs >= MIN_OUTS:
        relief = "" if started else " in relief"
        return (f"{_ip(outs)} IP{relief}, {_int(pit.get('hits'), 0)} H, {r} R, "
                f"{_int(pit.get('baseOnBalls'), 0)} BB, {k} K on {pc} pitches.")
    deco = ""
    if _int(pit.get("saves"), 0) > 0:
        deco = "; save"
    elif _int(pit.get("holds"), 0) > 0:
        deco = "; hold"
    elif _int(pit.get("wins"), 0) > 0:
        deco = "; win"
    where = _innings_text(innings)
    where = f" in the {where}" if where else ""
    return f"{_ip(outs)} IP{where}, {k} K{deco}."


def _fmt1(x: float) -> str:
    return f"{round_half_up(x * 10.0) / 10.0:.1f}"


def why_sentence(cand: dict, boxscore: dict, rows_by_ab: dict, codes: dict, lg: dict,
                 last_ab: int | None, pitched_innings: list[int]) -> str:
    """Hitter, pitcher or two-way sentence for a star candidate."""
    entry = _box_entry(boxscore, cand["side"], cand["id"])
    stats = entry.get("stats") or {}
    bat = stats.get("batting") or {}
    pit = stats.get("pitching") or {}
    pa = _int(bat.get("plateAppearances"), 0) or (_int(bat.get("atBats"), 0) + _int(bat.get("baseOnBalls"), 0)
                                                   + _int(bat.get("hitByPitch"), 0) + _int(bat.get("sacFlies"), 0)
                                                   + _int(bat.get("sacBunts"), 0))
    club = codes.get(cand["side"]) or ""
    parts = []
    if pa > 0 or not cand["pitched"]:
        best = rows_by_ab.get(cand["best_ab"]) if cand["best_ab"] is not None else None
        best_row = None
        if best is not None and best.get("bat_team") == club:
            best_row = dict(best)
            best_row["event_phrase"] = best["event_phrase"]
        ended = bool(best is not None and last_ab is not None and best["ab"] == last_ab)
        parts.append(hitter_sentence(bat, best_row, club, ended))
    if cand["pitched"]:
        parts.append(pitcher_sentence(pit, cand["basis"], lg, pitched_innings))
    if len(parts) == 2:
        return parts[0] + " On the mound: " + parts[1]
    return parts[0] if parts else ""


def stars_of_game(payload, boxscore: dict, lg: dict, codes: dict, *, state: str,
                  away_runs: int | None, home_runs: int | None, rows: list[dict] | None = None) -> dict:
    """`{stars, first_star_note, stars_reason}` for a game (plan 7.1).

    Eligible: the game is final, the scores differ, and MLB's added value is
    present on at least 95 percent of completed plate appearances; otherwise
    `stars: []` with a reason.
    """
    if state != "final":
        return {"stars": [], "first_star_note": False, "stars_reason": REASON_NOT_FINAL}
    if away_runs is None or home_runs is None or away_runs == home_runs:
        return {"stars": [], "first_star_note": False, "stars_reason": REASON_TIE}
    ws = wp_series(payload)
    if not coverage_ok(ws["coverage"]):
        return {"stars": [], "first_star_note": False, "stars_reason": REASON_COVERAGE}
    winner = "home" if home_runs > away_runs else "away"
    cands = star_candidates(payload, boxscore, lg)
    picked = pick_stars(cands, winner)
    if not picked:
        return {"stars": [], "first_star_note": False, "stars_reason": REASON_NO_WINNER_CANDIDATE}
    if rows is None:
        rows = play_rows(payload, codes)
    rows_by_ab = {}
    for r, p in zip(rows, complete_elements(payload)):
        rr = dict(r)
        rr["event_phrase"] = event_phrase(p)
        rows_by_ab[r["ab"]] = rr
    last_ab = rows[-1]["ab"] if rows else None
    innings_by_pitcher: dict = {}
    for pr in play_credits(payload):
        if pr["pitcher"]:
            innings_by_pitcher.setdefault((pr["pitcher"]["id"], "away" if pr["bat_side"] == "home" else "home"), []).append(pr["inning"])
    stars = []
    for i, c in enumerate(picked, start=1):
        stars.append({
            "rank": i, "id": c["id"], "name": c["name"], "team": codes.get(c["side"]),
            "score": c["score_m"], "basis": c["basis"],
            "why": why_sentence(c, boxscore, rows_by_ab, codes, lg, last_ab,
                                innings_by_pitcher.get((c["id"], c["side"]), [])),
            "clip": None,
        })
    note = len(stars) >= 2 and stars[0]["score"] < stars[1]["score"]
    return {"stars": stars, "first_star_note": bool(note), "stars_reason": None}


# --------------------------------------------------------------------------- #
# Box score rows with WPA and pLI
# --------------------------------------------------------------------------- #
_BAT_KEYS = (("ab", "atBats"), ("r", "runs"), ("h", "hits"), ("2b", "doubles"), ("3b", "triples"),
             ("hr", "homeRuns"), ("rbi", "rbi"), ("bb", "baseOnBalls"), ("k", "strikeOuts"),
             ("hbp", "hitByPitch"), ("sb", "stolenBases"), ("lob", "leftOnBase"))
_PIT_KEYS = (("outs", "outs"), ("h", "hits"), ("r", "runs"), ("er", "earnedRuns"), ("bb", "baseOnBalls"),
             ("k", "strikeOuts"), ("hr", "homeRuns"), ("pc", "numberOfPitches"), ("strikes", "strikes"),
             ("bf", "battersFaced"))


def _dec(pit: dict) -> dict:
    return {"w": _int(pit.get("wins"), 0) > 0, "l": _int(pit.get("losses"), 0) > 0,
            "sv": _int(pit.get("saves"), 0) > 0, "hld": _int(pit.get("holds"), 0) > 0,
            "bs": _int(pit.get("blownSaves"), 0) > 0}


def pitches_seen(payload) -> dict | None:
    """Pitches each batter saw, `{(batter id, batting side): n}`, counted from
    the `isPitch` events of the completed plate appearances and credited to
    the batter of record at the end of each one. None when any completed
    element carries no `playEvents` list (a read without the events cannot be
    counted, so it prints nothing rather than a short count)."""
    out: dict = {}
    for p in complete_elements(payload):
        ev = p.get("playEvents")
        if not isinstance(ev, list):
            return None
        bat = _person((p.get("matchup") or {}).get("batter"))
        if not bat:
            continue
        k = (bat["id"], "home" if _half(p) == "bottom" else "away")
        out[k] = out.get(k, 0) + sum(1 for e in ev if isinstance(e, dict) and e.get("isPitch") is True)
    return out


def _per(num: int, den: float) -> float | None:
    """A one-decimal rate, half up; None when the denominator is zero."""
    return round_half_up(num * 10.0 / den) / 10.0 if den > 0 else None


def box_rows(boxscore: dict, payload, debuts: set | None = None) -> dict:
    """`{away, home: {batting [...], pitching [...], notes []}}` from the
    boxscore's numeric fields with WPA (thousandths) and pLI (two decimals)
    from MLB's elements. `notes` stays empty here: MLB's note strings are
    prose and are not copied. A position player who pitched is marked.

    Pitch rates (owner ask 2026-10-07, one decimal, half up): a batter's
    `pit` (pitches seen, from MLB's pitch events) and `p_pa` (pitches per
    plate appearance, over the boxscore's plate appearances); a pitcher's
    `p_ip` (pitches per inning, the boxscore's pitch count over outs / 3).
    Each is None when its count or denominator is missing or zero."""
    acc = player_wpa(payload)
    seen = pitches_seen(payload)
    debuts = debuts or set()
    out = {}
    for side in ("away", "home"):
        team = (((boxscore or {}).get("teams") or {}).get(side) or {})
        players = team.get("players") or {}
        order = [_int(str(k)[2:], 0) for k in (team.get("batters") or [])]
        pitch_order = [_int(str(k)[2:], 0) for k in (team.get("pitchers") or [])]
        batting, pitching = [], []
        for key, entry in players.items():
            pid = _int(str(key)[2:], _int((entry.get("person") or {}).get("id"), 0))
            stats = entry.get("stats") or {}
            bat, pit = stats.get("batting") or {}, stats.get("pitching") or {}
            pos = normalize_text(((entry.get("position") or {}).get("abbreviation")) or "")
            name = normalize_text((entry.get("person") or {}).get("fullName"))
            r = acc.get((pid, side))
            if bat and (_int(bat.get("plateAppearances"), 0) > 0 or _int(bat.get("atBats"), 0) > 0
                        or _int(bat.get("baseOnBalls"), 0) > 0 or entry.get("battingOrder") or pid in order):
                row = {"id": pid, "name": name, "pos": pos, "order": _int(entry.get("battingOrder"), 0) or None}
                for short, full in _BAT_KEYS:
                    row[short] = _int(bat.get(full), 0)
                row["wpa"] = wins_to_thousandths(r["wpa_bat"]) if r else None
                row["pli"] = round(sum(r["li_bat"]) / len(r["li_bat"]), 2) if (r and r["li_bat"]) else None
                row["pit"] = seen.get((pid, side), 0) if seen is not None else None
                row["p_pa"] = (_per(row["pit"], _int(bat.get("plateAppearances"), 0))
                               if row["pit"] is not None else None)
                row["debut"] = pid in debuts
                batting.append(row)
            if pit and (_int(pit.get("outs"), 0) > 0 or _int(pit.get("battersFaced"), 0) > 0 or pid in pitch_order):
                row = {"id": pid, "name": name, "pos": pos}
                for short, full in _PIT_KEYS:
                    row[short] = _int(pit.get(full), 0)
                row["started"] = _int(pit.get("gamesStarted"), 0) > 0
                row["dec"] = _dec(pit)
                row["wpa"] = wins_to_thousandths(r["wpa_pit"]) if r else None
                row["pli"] = round(sum(r["li_pit"]) / len(r["li_pit"]), 2) if (r and r["li_pit"]) else None
                row["p_ip"] = _per(row["pc"] * 3, row["outs"]) if row["pc"] > 0 else None
                row["position_player"] = pos not in ("P", "TWP", "SP", "RP", "")
                row["debut"] = pid in debuts
                pitching.append(row)
        batting.sort(key=lambda x: (x["order"] is None, x["order"] or 0, x["id"]))
        rank = {pid: i for i, pid in enumerate(pitch_order)}
        pitching.sort(key=lambda x: (rank.get(x["id"], 10 ** 6), x["id"]))
        out[side] = {"batting": batting, "pitching": pitching, "notes": []}
    return out


# --------------------------------------------------------------------------- #
# 8. The card (plan 8.2)
# --------------------------------------------------------------------------- #
def _series_block(game: dict, codes_by_id: dict) -> dict | None:
    ss = game.get("seriesStatus")
    if not isinstance(ss, dict) or not ss:
        return None
    n, of = _int(ss.get("gameNumber"), 0) or None, _int(ss.get("totalGames"), 0) or None
    desc = normalize_text(ss.get("description")) or ""
    parts = []
    if desc and desc.lower() != "regular season":
        parts.append(desc)
    if n and of:
        parts.append(f"Game {n} of {of}")
    w, l = _int(ss.get("wins"), 0), _int(ss.get("losses"), 0)
    if w + l > 0:
        wid = (ss.get("winningTeam") or {}).get("id")
        code = codes_by_id.get(wid) or club_code(wid)
        if ss.get("isTied") or w == l:
            parts.append(f"Series tied {w}-{l}")
        elif code:
            parts.append(f"{code} wins {w}-{l}" if ss.get("isOver") else f"{code} leads {w}-{l}")
    key = _series_key(game)
    return {"text": ", ".join(parts) if parts else None, "n": n, "of": of,
            "if_necessary": str(game.get("ifNecessary") or "N") == "Y",
            "desc": key[0] if key else None}


def _side_block(game: dict, side: str, people: dict | None) -> dict:
    t = ((game.get("teams") or {}).get(side) or {})
    team = t.get("team") or {}
    tid = team.get("id")
    rec = t.get("leagueRecord") or {}
    prob = t.get("probablePitcher")
    probable = None
    if isinstance(prob, dict) and prob.get("id") is not None:
        extra = (people or {}).get(int(prob["id"])) or (people or {}).get(str(prob["id"])) or {}
        probable = {"id": int(prob["id"]), "name": normalize_text(prob.get("fullName")),
                    "hand": extra.get("hand"), "w": extra.get("w"), "l": extra.get("l"),
                    "era": extra.get("era")}
    lineups = game.get("lineups") or {}
    posted = bool(lineups.get("homePlayers" if side == "home" else "awayPlayers"))
    ls_team = (((game.get("linescore") or {}).get("teams") or {}).get(side) or {})
    return {
        "team_id": int(tid) if tid is not None else None,
        "code": club_code(tid),
        "name": normalize_text(team.get("name")),
        "short": normalize_text(team.get("teamName") or team.get("shortName") or team.get("name")),
        "wl": {"w": _int(rec.get("wins"), 0), "l": _int(rec.get("losses"), 0)},
        "r": ls_team.get("runs") if ls_team.get("runs") is not None else (t.get("score") if t.get("score") is not None else None),
        "h": ls_team.get("hits"), "e": ls_team.get("errors"),
        "probable": probable, "lineup_posted": posted,
    }


def _line(game: dict) -> list:
    innings = ((game.get("linescore") or {}).get("innings")) or []
    return [[(inn.get("away") or {}).get("runs"), (inn.get("home") or {}).get("runs")] for inn in innings]


def _sit(game: dict, last_text: str | None, pitcher_pitches: int | None) -> dict:
    ls = game.get("linescore") or {}
    off, dfn = ls.get("offense") or {}, ls.get("defense") or {}
    pitcher = _person(dfn.get("pitcher"))
    if pitcher is not None:
        pitcher["pitches"] = pitcher_pitches
    return {"inning": _int(ls.get("currentInning"), 0) or None,
            "half": "bottom" if str(ls.get("inningHalf") or ls.get("inningState") or "").lower() == "bottom" else "top",
            "outs": _int(ls.get("outs"), 0), "balls": _int(ls.get("balls"), 0), "strikes": _int(ls.get("strikes"), 0),
            "bases": [bool(off.get("first")), bool(off.get("second")), bool(off.get("third"))],
            "batter": _person(off.get("batter")), "pitcher": pitcher, "last_text": last_text}


def build_card(game: dict, *, generated_at: str, wp=None, derived: dict | None = None,
               people: dict | None = None, names: dict | None = None) -> dict:
    """The date-file card for one schedule game (plan 8.2). `wp` is the game's
    winProbability payload when the job has one (live or final); `derived` is
    the game file's star, top play and flags block when it exists (final)."""
    state, reason = game_state(game.get("status"))
    st = game.get("status") or {}
    away, home = _side_block(game, "away", people), _side_block(game, "home", people)
    codes_by_id = {away["team_id"]: away["code"], home["team_id"]: home["code"]}
    derived = derived or {}
    card = {
        "pk": int(game.get("gamePk")), "rev": derived.get("rev"),
        "type": game.get("gameType"), "state": state, "reason": reason,
        "start": game.get("gameDate"), "tbd": bool(st.get("startTimeTBD")),
        "dh": {"kind": {"S": "split", "Y": "traditional"}.get(str(game.get("doubleHeader") or "N")),
               "n": _int(game.get("gameNumber"), 1)},
        "venue": {"id": (game.get("venue") or {}).get("id"), "name": normalize_text((game.get("venue") or {}).get("name"))},
        "series": _series_block(game, codes_by_id),
        "tv": sorted({normalize_text(b.get("callSign") or b.get("name")) for b in (game.get("broadcasts") or [])
                      if str(b.get("type") or "").upper() == "TV" and (b.get("callSign") or b.get("name"))}),
        "away": away, "home": home,
        "line": _line(game),
        "sit": None, "wp": None, "of_record": None, "star": None, "top_play": None, "videos": None,
        "flags": {"no_hitter": False, "perfect_game": False, "debut": False,
                  "extra_innings": False, "shortened": False},
        "weather": None, "makeup": game.get("rescheduleDate"), "resume": game.get("resumeDate"),
        "updated_at": generated_at, "stale_since": None,
    }
    fl = game.get("flags") or {}
    innings = len(card["line"])
    sched = _int(game.get("scheduledInnings"), 9) or 9
    card["flags"].update({
        "no_hitter": bool(fl.get("noHitter")), "perfect_game": bool(fl.get("perfectGame")),
        "extra_innings": innings > sched,
        "shortened": state == "final" and (innings < sched or str(st.get("detailedState") or "").startswith("Completed Early")),
    })
    weather = game.get("weather") or {}
    if weather.get("condition") or weather.get("temp"):
        card["weather"] = {"condition": normalize_text(weather.get("condition")),
                           "temp": normalize_text(weather.get("temp")), "wind": normalize_text(weather.get("wind"))}
    last_text = None
    if wp is not None:
        ws = wp_series(wp)
        if ws["last"] is not None:
            card["wp"] = {"home": ws["last"]["wp_home"], "ab": ws["last"]["ab"]}
        plays = complete_elements(wp)
        if plays:
            last_text = play_text(plays[-1], names)
    if state in ("live", "delayed"):
        card["sit"] = _sit(game, last_text, derived.get("pitcher_pitches"))
    if state == "final":
        d = game.get("decisions") or {}
        card["of_record"] = {"w": _person(d.get("winner")), "l": _person(d.get("loser")), "sv": _person(d.get("save"))}
        card["star"] = derived.get("star")
        card["top_play"] = derived.get("top_play")
        card["videos"] = derived.get("videos") or {"recap_s": None, "condensed_s": None}
        card["flags"]["debut"] = bool(derived.get("debut"))
    return card


# --------------------------------------------------------------------------- #
# 8b. Clips (SCORES_4a_VIDEO; plan 6.0 to 6.7 and 8.4)
# --------------------------------------------------------------------------- #
#: The owner's answer SC-VIDEO (a): MLB's own embed player in a frame from
#: streamable.com/m/<slug>; the clip object stores `embed` and no media file.
VIDEO_BRANCH = "a"
#: Distribution tags in a clip's taxonomy that name a licensed sportsbook feed
#: (plan 6.0); a later book tag is added here by commit.
SPORTSBOOK_TAGS = ("fan-duel", "bet-mgm")
#: Taxonomy values that mark an ABS challenge reel. A play clip matched by its
#: `guid` is an exact join and keeps a replay `challenge` tag (849845's hit by
#: pitch carries one); an `abs` reel never matches a play, and no reel tagged
#: `abs` or `challenge` becomes a game video or a pitcher star's reel.
ABS_PLAY_TAGS = ("abs",)
ABS_REEL_TAGS = ("abs", "challenge")
#: The poster cuts the clip object keeps (plan 6.2), and the template fallback.
POSTER_WIDTHS = {"w480": (480, 270), "w960": (960, 540)}
#: Never stored (plan 8.4): renditions the page must not reach.
FORBIDDEN_MEDIA = ("highbit", "trickplay", "portrait", "http_cloud_wired")
#: A plate appearance's earlier events (plan 6.1) by `eventType` prefix or
#: `type`, with the label the Plays tab prints ("Pickoff attempt, top 3").
EVENT_LABELS = (
    ("pickoff_attempt", "Pickoff attempt"), ("pickoff_error", "Pickoff error"),
    ("pickoff_caught_stealing", "Caught stealing"), ("pickoff", "Pickoff"),
    ("stepoff", "Step-off"), ("pitcher_step_off", "Step-off"),
    ("stolen_base", "Stolen base"), ("caught_stealing", "Caught stealing"),
    ("wild_pitch", "Wild pitch"), ("passed_ball", "Passed ball"), ("balk", "Balk"),
    ("defensive_indiff", "Defensive indifference"), ("pitch", "Pitch"),
)
#: A clip is pending ("No MLB clip for this play yet") this long after a final.
CLIP_PENDING_S = 24 * 3600
_SLUG_RE = re.compile(r"^[a-z0-9-]+$")


def _taxonomy(item: dict) -> set:
    return {str(k.get("value") or "").lower() for k in item.get("keywordsAll") or []
            if isinstance(k, dict) and k.get("type") == "taxonomy"}


def _keyword_values(item: dict, kind: str) -> list[str]:
    return [str(k.get("value")) for k in item.get("keywordsAll") or []
            if isinstance(k, dict) and k.get("type") == kind and k.get("value") is not None]


def parse_duration(s) -> int | None:
    """"00:00:29" (HH:MM:SS on every sampled item) as whole seconds, 1 to 3,600;
    None otherwise."""
    m = re.match(r"^(\d{1,2}):(\d{2}):(\d{2})$", str(s or ""))
    if not m:
        return None
    sec = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    return sec if 1 <= sec <= 3600 else None


def _host(url) -> str | None:
    m = re.match(r"^https://([^/\s]+)/", str(url or ""))
    return m.group(1).lower() if m else None


def pick_file(item: dict, name: str) -> str | None:
    """The `playbacks` entry named `name` (`mp4Avc`, `hlsCloud`) whose URL
    contains the item's `mediaPlaybackId`, else the first one (plan 6.2: on
    849845 an item's own asset is listed third on one multi-asset item)."""
    cands = [str(p.get("url") or "") for p in item.get("playbacks") or []
             if isinstance(p, dict) and p.get("name") == name and p.get("url")]
    mid = str(item.get("mediaPlaybackId") or "")
    for u in cands:
        if mid and mid in u:
            return u
    return cands[0] if cands else None


def _posters(item: dict, notes: dict) -> dict | None:
    img = item.get("image") or {}
    out = {}
    for key, (w, h) in POSTER_WIDTHS.items():
        url = None
        for c in img.get("cuts") or []:
            if isinstance(c, dict) and _int(c.get("width"), 0) == w and _int(c.get("height"), 0) == h:
                url = c.get("src")
                break
        if not url and img.get("templateUrl"):
            url = str(img["templateUrl"]).replace("{formatInstructions}", f"w_{w},h_{h},f_jpg,c_fill,g_auto")
        if url and url_ok(url, "poster"):
            out[key] = url
        elif url:
            notes.setdefault("new_media_host", []).append(_host(url) or "?")
    return out or None


def trim_content(content) -> dict:
    """What the job keeps in its work file from a `/game/{pk}/content` read:
    the video items with only the keys the join and the clip object use (no
    headline, blurb, description, title or kicker; no rendition but `mp4Avc`
    and `hlsCloud`). Each fetch replaces the game's set."""
    items = (((content or {}).get("highlights") or {}).get("highlights") or {}).get("items") or []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        img = it.get("image") or {}
        cuts = [{"width": c.get("width"), "height": c.get("height"), "src": c.get("src")}
                for c in img.get("cuts") or [] if isinstance(c, dict)
                and (_int(c.get("width"), 0), _int(c.get("height"), 0)) in POSTER_WIDTHS.values()]
        out.append({
            "type": it.get("type"), "state": it.get("state"), "date": it.get("date"), "slug": it.get("slug"),
            "guid": it.get("guid"), "mediaPlaybackId": it.get("mediaPlaybackId"), "duration": it.get("duration"),
            "cclocationVtt": it.get("cclocationVtt") or None,
            "keywordsAll": [{"type": k.get("type"), "value": k.get("value")} for k in it.get("keywordsAll") or []
                            if isinstance(k, dict) and k.get("type") in ("taxonomy", "player_id", "game_pk")],
            "image": {"templateUrl": img.get("templateUrl"), "cuts": cuts},
            "playbacks": [{"name": p.get("name"), "url": p.get("url")} for p in it.get("playbacks") or []
                          if isinstance(p, dict) and p.get("name") in ("mp4Avc", "hlsCloud")],
        })
    return {"items": out}


def _items_of(content) -> list[dict]:
    if isinstance(content, dict) and isinstance(content.get("items"), list):
        items = content["items"]
    else:
        items = trim_content(content)["items"]
    return [it for it in items if isinstance(it, dict) and it.get("type") == "video" and it.get("state") == "A"]


def clip_object(item: dict, *, kind: str, match: str, branch: str = VIDEO_BRANCH, seen_at=None,
                play_id=None, event=None, notes: dict | None = None) -> dict | None:
    """The clip object of plan 8.4, or None when the item has no id or no
    usable slug (no page to fall back to). Branch (a): `embed` is MLB's player
    at streamable.com/m/<slug>, set only when the item's own video file (the
    6.2 pick of `mp4Avc`, else `hlsCloud`) sits on an allowlisted video host,
    which is what that player plays; an unknown host leaves the clip at its
    MLB.com `page` (F1) and records `new_media_host`. No `hls`, `mp4` or `vtt`
    under (a). Nothing of MLB's prose is copied."""
    notes = notes if notes is not None else {}
    cid, slug = item.get("mediaPlaybackId"), str(item.get("slug") or "")
    if not cid or not _SLUG_RE.match(slug):
        notes["dropped"] = notes.get("dropped", 0) + 1
        return None
    page = f"https://www.mlb.com/video/{slug}"
    if not url_ok(page, "page"):
        notes["dropped"] = notes.get("dropped", 0) + 1
        return None
    tax = _taxonomy(item)
    clip = {"id": str(cid), "kind": kind, "match": match, "play_id": play_id, "event": event,
            "feeds_sportsbook": bool(tax & set(SPORTSBOOK_TAGS)),
            "poster": _posters(item, notes), "dur_s": parse_duration(item.get("duration")),
            "posted_at": item.get("date"), "seen_at": seen_at, "page": page}
    files = [u for u in (pick_file(item, "mp4Avc"), pick_file(item, "hlsCloud")) if u]
    if branch == "a":
        clip["embed"] = None
        if files:
            bad = [_host(u) or "?" for u in files if not url_ok(u, "mp4" if u.endswith(".mp4") else "hls")]
            if bad:
                notes.setdefault("new_media_host", []).extend(bad)
            else:
                emb = f"https://{FRAME_HOST}/m/{slug}"
                clip["embed"] = emb if url_ok(emb, "embed") else None
        if clip["embed"] is None:
            notes["f1"] = notes.get("f1", 0) + 1
    if not clip["poster"]:
        clip["poster"] = None
    return clip


def _event_kind(ev: dict) -> str:
    """The type of a plate appearance's event, from `details.eventType`, else
    `type`, else the short call label MLB gives a pickoff attempt or a
    step-off (mapped to a constant, never copied)."""
    det = ev.get("details") or {}
    et = str(det.get("eventType") or "").lower()
    if et:
        return et
    t = str(ev.get("type") or "").lower()
    if t == "pickoff":
        return "pickoff_attempt"
    if t:
        return t
    label = str(det.get("description") or "").lower()
    if label.startswith("pickoff attempt"):
        return "pickoff_attempt"
    if "step off" in label:
        return "stepoff"
    return "pitch" if ev.get("isPitch") else "play"


def event_label(kind: str, half: str, inning: int) -> str:
    """"Pickoff attempt, top 3" for an earlier event's clip (plan 6.1)."""
    word = "Play"
    for pre, lab in EVENT_LABELS:
        if kind.startswith(pre):
            word = lab
            break
    return f"{word}, {half} {int(inning)}"


def _tie_key(item: dict):
    """Several candidates for one event: captions first, then taxonomy
    in-game-highlight, then the earliest date, then slug (plan 6.1)."""
    return (0 if item.get("cclocationVtt") else 1, 0 if "in-game-highlight" in _taxonomy(item) else 1,
            str(item.get("date") or ""), str(item.get("slug") or ""))


def join_clips(content, wp, *, pk=None, branch: str = VIDEO_BRANCH, seen_at=None) -> dict:
    """The join of plan 6.1 over a content read and the game's winProbability
    elements. Returns `{clips {id: clip}, result {ab: id}, events {ab: [{event,
    label, clip}]}, recap, condensed, reels {player id: id}, log}`.

    A play clip is an item whose `guid` equals a `playId` of a completed plate
    appearance. When it is the plate appearance's final event (its last
    `playEvents[]` entry carrying a `playId`) it is the RESULT clip; a clip of
    an earlier event (a pickoff attempt, a step-off, a stolen base) is stored
    with that event's type and label and never captions the result. Game
    videos: taxonomy game-recap and condensed-game. Pitcher reels: taxonomy
    highlight-reel-pitching, no guid, exactly one player_id, this game_pk.
    Never an ABS reel, an interview or a data-visualisation item, never a
    headline, player or inning guess."""
    items = _items_of(content)
    notes: dict = {}
    by_play: dict = {}
    for p in complete_elements(wp):
        ids = [e.get("playId") for e in p.get("playEvents") or [] if isinstance(e, dict) and e.get("playId")]
        final = ids[-1] if ids else None
        for e in p.get("playEvents") or []:
            if isinstance(e, dict) and e.get("playId"):
                by_play[str(e["playId"])] = {"ab": _ab(p), "final": e["playId"] == final, "kind": _event_kind(e),
                                             "half": _half(p), "inning": _inning(p)}
    cands: dict = {}
    for it in items:
        g = it.get("guid")
        if g and str(g) in by_play and not (_taxonomy(it) & set(ABS_PLAY_TAGS)):
            cands.setdefault(str(g), []).append(it)
    out = {"clips": {}, "result": {}, "events": {}, "recap": None, "condensed": None, "reels": {}}

    def add(it, **kw):
        c = clip_object(it, branch=branch, seen_at=seen_at, notes=notes, **kw)
        if c is not None:
            out["clips"][c["id"]] = c
            return c["id"]
        return None

    for pid in sorted(cands, key=lambda x: (by_play[x]["ab"], x)):
        it = sorted(cands[pid], key=_tie_key)[0]
        info = by_play[pid]
        ev = "result" if info["final"] else info["kind"]
        cid = add(it, kind="play", match="play", play_id=pid, event=ev)
        if cid is None:
            continue
        if info["final"]:
            out["result"][info["ab"]] = cid
        else:
            out["events"].setdefault(info["ab"], []).append(
                {"event": ev, "label": event_label(ev, info["half"], info["inning"]), "clip": cid})
    for kind, tag in (("recap", "game-recap"), ("condensed", "condensed-game")):
        pool = [it for it in items if tag in _taxonomy(it) and not (_taxonomy(it) & set(ABS_REEL_TAGS))]
        if pool:
            out[kind] = add(sorted(pool, key=_tie_key)[0], kind=kind, match="game")
    for it in sorted(items, key=_tie_key):
        tax = _taxonomy(it)
        pids = _keyword_values(it, "player_id")
        gpk = _keyword_values(it, "game_pk")
        if ("highlight-reel-pitching" in tax and not it.get("guid") and len(pids) == 1
                and not (tax & set(ABS_REEL_TAGS)) and pk is not None and str(pk) in gpk):
            out["reels"].setdefault(int(pids[0]), it)
    hosts = sorted(set(notes.get("new_media_host") or []))
    out["log"] = {"items": len(items), "matched": len(out["result"]), "event_clips": sum(len(v) for v in out["events"].values()),
                  "with_captions": sum(1 for pid in cands if sorted(cands[pid], key=_tie_key)[0].get("cclocationVtt")),
                  "dropped": int(notes.get("dropped") or 0), "f1": int(notes.get("f1") or 0),
                  "new_media_host": hosts}
    return out


def attach_clips(gf: dict, joined: dict, wp, boxscore: dict | None, *, pending: bool,
                 branch: str = VIDEO_BRANCH, seen_at=None) -> dict:
    """Write a join into a built game file (in place, and returned): every
    plays row's result `clip` and `event_clips`; Biggest plays' result clips
    and `clip_state` (`pending` while a clip may still post, else `none`; null
    with a clip); a star's clip (a hitter's highest-credit plate appearance's
    result clip; a pitcher's one-player pitching reel of this game, else his
    highest-credit plate appearance's result clip); the card's `top_play.clip_s`
    and `videos`; and `clips`, holding only the clip objects referenced."""
    res = joined.get("result") or {}
    used: set = set()
    for row in gf.get("plays") or []:
        row["clip"] = res.get(row["ab"])
        row["event_clips"] = [dict(e) for e in (joined.get("events") or {}).get(row["ab"], [])]
        if row["clip"]:
            used.add(row["clip"])
        used.update(e["clip"] for e in row["event_clips"])
    for b in gf.get("plays_big") or []:
        b["clip"] = res.get(b["ab"])
        b["clip_state"] = None if b["clip"] else ("pending" if pending else "none")
    codes = {}
    card = gf.get("card") or {}
    for side in ("away", "home"):
        codes[(card.get(side) or {}).get("code")] = side
    acc = player_wpa(wp) if gf.get("stars") else {}
    pitchers = set()
    for side in ("away", "home"):
        for r in (((gf.get("box") or {}).get(side) or {}).get("pitching") or []):
            pitchers.add((r.get("id"), side))
    for s in gf.get("stars") or []:
        side = codes.get(s.get("team"))
        a = acc.get((s["id"], side)) or {}
        best = res.get(a.get("best_ab")) if a.get("best_ab") is not None else None
        clip = None
        if (s["id"], side) in pitchers:
            reel = (joined.get("reels") or {}).get(int(s["id"]))
            if reel is not None:
                c = clip_object(reel, kind="reel", match="player", branch=branch, seen_at=seen_at)
                if c is not None:
                    joined["clips"][c["id"]] = c
                    clip = c["id"]
        s["clip"] = clip or best
        if s["clip"]:
            used.add(s["clip"])
    for b in gf.get("plays_big") or []:
        if b["clip"]:
            used.add(b["clip"])
    clips = joined.get("clips") or {}
    vids = {"recap_s": None, "condensed_s": None}
    for kind in ("recap", "condensed"):
        cid = joined.get(kind)
        if cid and cid in clips:
            used.add(cid)
            vids[f"{kind}_s"] = clips[cid].get("dur_s")
    gf["clips"] = {cid: clips[cid] for cid in sorted(used) if cid in clips}
    if card.get("state") == "final":
        card["videos"] = vids
        tp = card.get("top_play")
        if tp is not None:
            cid = res.get(tp.get("ab"))
            tp["clip_s"] = clips[cid].get("dur_s") if cid in clips else None
    return gf


def diamond_gating_on(config_text: str | None) -> bool:
    """True when assets/diamond-config.js's window.EEPHUS_DIAMOND object reads
    `gating: true` (comments ignored)."""
    text = re.sub(r"//[^\n]*", "", str(config_text or ""))
    m = re.search(r"\bgating\s*:\s*(true|false)\b", text)
    return bool(m and m.group(1) == "true")


def embed_reconfirmed() -> bool:
    """SCORES_EMBED_RECONFIRMED holds an ISO date (the owner's re-confirmation
    of embedding before the Diamond gate opens, SC-PAID (a))."""
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(SCORES_EMBED_RECONFIRMED or "")))


# --------------------------------------------------------------------------- #
# 8. The game file (plan 8.3)
# --------------------------------------------------------------------------- #
def _info_block(feed: dict | None) -> dict | None:
    if not feed:
        return None
    gd = feed.get("gameData") or {}
    officials = (((feed.get("liveData") or {}).get("boxscore") or {}).get("officials")) or []
    venue = gd.get("venue") or {}
    fi = venue.get("fieldInfo") or {}
    gi = gd.get("gameInfo") or {}
    w = gd.get("weather") or {}
    absc = gd.get("absChallenges") or {}
    rev = gd.get("review") or {}
    mv = gd.get("moundVisits") or {}
    teams = gd.get("teams") or {}
    codes = {side: club_code((teams.get(side) or {}).get("id")) for side in ("away", "home")}

    def by_side(block, keys):
        out = {}
        for side in ("away", "home"):
            b = block.get(side) or {}
            if b:
                out[codes.get(side) or side] = {k: _int(b.get(src), 0) for k, src in keys}
        return out

    return {
        "umpires": [{"pos": normalize_text(o.get("officialType")), "id": (o.get("official") or {}).get("id"),
                     "name": normalize_text((o.get("official") or {}).get("fullName"))} for o in officials],
        "weather": {"condition": normalize_text(w.get("condition")), "temp": normalize_text(w.get("temp"))} if w else None,
        "wind": normalize_text(w.get("wind")) if w else None,
        "first_pitch": gi.get("firstPitch"), "duration_min": gi.get("gameDurationMinutes"),
        "delay_min": gi.get("delayDurationMinutes"), "attendance": gi.get("attendance"),
        "venue": {"name": normalize_text(venue.get("name")), "roof": normalize_text(fi.get("roofType")),
                  "surface": normalize_text(fi.get("turfType")),
                  "dims": {k: fi.get(src) for k, src in (("lf", "leftLine"), ("lcf", "leftCenter"), ("cf", "center"),
                                                          ("rcf", "rightCenter"), ("rf", "rightLine"))},
                  "elevation_ft": (venue.get("location") or {}).get("elevation")},
        "abs": by_side(absc, (("won", "usedSuccessful"), ("lost", "usedFailed"), ("remaining", "remaining"))),
        "reviews": by_side(rev, (("used", "used"), ("remaining", "remaining"))),
        "mound_visits": by_side(mv, (("used", "used"), ("remaining", "remaining"))),
    }


def debut_ids(feed: dict | None, official_date: str | None) -> set:
    """MLBAM ids of players whose `mlbDebutDate` is the game's official date."""
    out = set()
    if not feed or not official_date:
        return out
    for key, p in ((feed.get("gameData") or {}).get("players") or {}).items():
        if p.get("mlbDebutDate") == official_date and p.get("id") is not None:
            out.add(int(p["id"]))
    return out


def _lineups(game: dict, boxscore: dict | None) -> dict:
    out = {"away": [], "home": []}
    lu = game.get("lineups") or {}
    for side, key in (("away", "awayPlayers"), ("home", "homePlayers")):
        rows = []
        for p in lu.get(key) or []:
            if p.get("id") is None:
                continue
            rows.append({"id": int(p["id"]), "name": normalize_text(p.get("fullName")),
                         "pos": normalize_text((p.get("primaryPosition") or {}).get("abbreviation"))})
        if not rows and boxscore:
            team = (((boxscore.get("teams") or {}).get(side)) or {})
            for key2 in team.get("battingOrder") or []:
                entry = (team.get("players") or {}).get(f"ID{key2}") or {}
                rows.append({"id": int(key2), "name": normalize_text((entry.get("person") or {}).get("fullName")),
                             "pos": normalize_text((entry.get("position") or {}).get("abbreviation"))})
        out[side] = rows
    return out


def build_game_file(game: dict, wp, boxscore: dict | None, lg: dict, *, generated_at: str,
                    feed: dict | None = None, people: dict | None = None, content=None,
                    clips_pending: bool | None = None, seen_at=None, clip_log: dict | None = None) -> dict:
    """The game file (plan 8.3) from a schedule game, its winProbability
    payload, its boxscore (needed for stars and the box), the league
    constants `{lg_ra9, rpw}` and, at Final, the feed trimmed to `gameData`
    and `liveData.boxscore.officials`. The card inside it carries the game
    file's `rev`; the caller writes the date-file card from `card`.

    `content` (SCORES_4a) is the game's content read, raw or as
    `trim_content` keeps it; with it the clips of plan 6.1 are joined and
    attached (`attach_clips`). `clips_pending` says whether a missing clip may
    still post (default: no content read yet, or the game is not final); `seen_at` is the content
    fetch time; `clip_log`, when given, receives the join's counts."""
    state, _reason = game_state(game.get("status"))
    teams = game.get("teams") or {}
    codes = {side: club_code(((teams.get(side) or {}).get("team") or {}).get("id")) for side in ("away", "home")}
    season = _int(game.get("season"), 0) or _int(str(game.get("officialDate") or "")[:4], 0)
    gtype = game.get("gameType") or "R"
    sched = _int(game.get("scheduledInnings"), 9) or 9
    ws = wp_series(wp)
    names = last_name_map(feed, boxscore)
    rows = play_rows(wp, codes, season=season, game_type=gtype, scheduled_innings=sched, names=names)
    big = biggest_plays(rows) if coverage_ok(ws["coverage"]) else []
    plays_reason = None if coverage_ok(ws["coverage"]) else PLAYS_REASON_COVERAGE
    ls_teams = ((game.get("linescore") or {}).get("teams")) or {}
    away_runs = (ls_teams.get("away") or {}).get("runs", (teams.get("away") or {}).get("score"))
    home_runs = (ls_teams.get("home") or {}).get("runs", (teams.get("home") or {}).get("score"))
    stars = stars_of_game(wp, boxscore or {}, lg, codes, state=state,
                          away_runs=away_runs, home_runs=home_runs, rows=rows)
    official_date = game.get("officialDate")
    debuts = debut_ids(feed, official_date)
    box = box_rows(boxscore, wp, debuts) if boxscore else None
    top_play = None
    if big and state == "final":
        b = big[0]
        top_play = {"ab": b["ab"], "text": b["text"], "bat_team": b["bat_team"], "before": b["before"],
                    "after": b["after"], "swing": b["swing"], "clip_s": None}
    star_card = None
    if stars["stars"]:
        s0 = stars["stars"][0]
        star_card = {"id": s0["id"], "name": s0["name"], "team": s0["team"], "why": s0["why"]}
    pitcher_pitches = None
    if box and state in ("live", "delayed"):
        pid = ((((game.get("linescore") or {}).get("defense")) or {}).get("pitcher") or {}).get("id")
        for side in ("away", "home"):
            for r in box[side]["pitching"]:
                if pid is not None and r["id"] == int(pid):
                    pitcher_pitches = r["pc"]
    derived = {"star": star_card, "top_play": top_play, "debut": bool(debuts),
               "videos": {"recap_s": None, "condensed_s": None}, "pitcher_pitches": pitcher_pitches}
    card = build_card(game, generated_at=generated_at, wp=wp, derived=derived, people=people, names=names)
    plays_out = []
    for r in rows:
        plays_out.append({k: r[k] for k in ("ab", "inning", "half", "text", "outs", "bases", "away", "home",
                                            "wp", "swing", "li", "clip", "event_clips", "reviews")})
    gf = {
        "schema": SCHEMA, "pk": card["pk"], "rev": None, "generated_at": generated_at,
        "card": card,
        "wp": {"pregame_home": ws["pregame_home"], "series": ws["series"], "coverage": ws["coverage"],
               "unattributed_home": unattributed_home(wp)},
        "plays": plays_out,
        "plays_big": big, "plays_big_reason": plays_reason,
        "stars": stars["stars"], "first_star_note": stars["first_star_note"],
        "stars_reason": stars["stars_reason"],
        "scoring": [r["ab"] for r in rows if r["scored"]],
        "box": box,
        "lineups": _lineups(game, boxscore),
        "info": _info_block(feed) if state == "final" else None,
        "debuts": sorted(debuts),
        "links": {"gameday": f"https://www.mlb.com/gameday/{card['pk']}"},
        "clips": {},
    }
    # with no read yet a clip may still post; after a final read the default
    # is "none" unless the caller (the job's 24 hour rule) says otherwise
    if clips_pending is None:
        pending = content is None or state != "final"
    else:
        pending = bool(clips_pending)
    for b in gf["plays_big"]:
        b["clip_state"] = "pending" if pending else "none"
    if content is not None:
        joined = join_clips(content, wp, pk=card["pk"], seen_at=seen_at)
        attach_clips(gf, joined, wp, boxscore, seen_at=seen_at, pending=pending)
        if clip_log is not None:
            clip_log.update(joined["log"])
            big = gf.get("plays_big") or []
            clip_log["f3_big"] = sum(1 for b in big if not b.get("clip"))
            clip_log["big_matched"] = sum(1 for b in big if b.get("clip"))
            clip_log["big_of"] = len(big)
    rev = rev_of(gf)
    gf["rev"] = rev
    gf["card"]["rev"] = rev
    return gf


def build_date_file(date: str, cards: list[dict], game_files: dict | None, *, generated_at: str) -> dict:
    """The date file (plan 8.1): `{schema, date, generated_at, day_top_plays,
    games}`. `day_top_plays` holds the date's five largest swings across its
    game files (`{pk, ab, text, bat_team, before, after, swing, live}`)."""
    cards = sorted((copy.deepcopy(c) for c in cards), key=lambda c: (c.get("start") or "", c.get("pk")))
    pool = []
    for c in cards:
        gf = (game_files or {}).get(c["pk"])
        if not gf:
            continue
        for b in gf.get("plays_big") or []:
            pool.append({"pk": c["pk"], "ab": b["ab"], "text": b["text"], "bat_team": b["bat_team"],
                         "before": b["before"], "after": b["after"], "swing": b["swing"],
                         "li": b["li"], "live": c.get("state") != "final"})
    pool.sort(key=_big_key)
    top = [{k: v for k, v in r.items() if k != "li"} for r in pool[:N_BIG_PLAYS]]
    return {"schema": SCHEMA, "date": date, "generated_at": generated_at,
            "day_top_plays": top, "games": cards}


# --------------------------------------------------------------------------- #
# 8. The validator (plan 8.5), with a registry so a second payload family can
# add its own file kinds (STANDINGS_1_CORE_RULES).
# --------------------------------------------------------------------------- #
_KB = 1024

#: kind -> {budget, ceiling, name_re, copyright_exempt, url_paths}
FILE_KINDS: dict = {}


def register_file_kind(kind: str, *, budget: int, ceiling: int | None = None,
                       name_re: str | None = None, copyright_exempt: bool = False,
                       url_paths: tuple = ()) -> None:
    """Register (or amend) a file kind: its test-time budget and runtime
    ceiling in bytes (default four times the budget), the file-name pattern
    `kind_of_name` matches, whether a top-level `copyright` key may carry
    StatsAPI's line with its terms URL (rule 4's exemption), and the dotted key
    paths under which media URLs are allowed."""
    FILE_KINDS[kind] = {"budget": int(budget), "ceiling": int(ceiling if ceiling is not None else budget * 4),
                        "name_re": re.compile(name_re) if name_re else None,
                        "copyright_exempt": bool(copyright_exempt), "url_paths": tuple(url_paths)}


register_file_kind("latest", budget=16 * _KB, name_re=r"^latest\.json$")
register_file_kind("index", budget=16 * _KB, name_re=r"^index\.json$", copyright_exempt=True,
                   url_paths=("rules.video.video_hosts.*", "rules.video.caption_hosts.*",
                              "rules.video.poster_host", "rules.video.frame_host"))
register_file_kind("season_index", budget=40 * _KB, name_re=r"^index-\d{4}\.json$")
register_file_kind("date", budget=150 * _KB, name_re=r"^\d{4}-\d{2}-\d{2}\.json$")
register_file_kind("game", budget=80 * _KB, name_re=r"^games/\d+\.json$",
                   url_paths=("links.gameday", "clips.*.embed", "clips.*.hls", "clips.*.mp4",
                              "clips.*.vtt", "clips.*.page", "clips.*.poster.w480", "clips.*.poster.w960"))
register_file_kind("clip", budget=int(1.2 * _KB), ceiling=int(4.8 * _KB))


def kind_of_name(name: str) -> str | None:
    name = str(name).replace("\\", "/")
    for kind, spec in FILE_KINDS.items():
        if spec["name_re"] is not None and spec["name_re"].search(name):
            return kind
    return None


#: Forbidden keys (plan 8.6), at any depth, every scores payload.
_FORBIDDEN_EXACT = {"edge", "ev", "ev_per_unit", "odds", "decimal", "implied_prob", "fair_odds", "clv", "units"}
_FORBIDDEN_PREFIX = ("kelly", "pick", "slot", "record", "price", "book", "stake")
_FORBIDDEN_CONTAINS = ("dv", "decision")
_FORBIDDEN_PROSE = {"headline", "blurb", "description", "title", "kicker", "summary"}
_MARKET_ALLOWED = {"market_fair_prob", "market_captured_at"}


def forbidden_key(key, *, allow_market: bool = False) -> str | None:
    """Why a key is forbidden (plan 8.6), or None."""
    k = str(key).lower()
    if k in _FORBIDDEN_EXACT:
        return f"forbidden key {key!r}"
    if k in _FORBIDDEN_PROSE:
        return f"MLB prose key {key!r}"
    for pre in _FORBIDDEN_PREFIX:
        if k.startswith(pre):
            return f"forbidden key {key!r} ({pre}*)"
    for sub in _FORBIDDEN_CONTAINS:
        if sub in k:
            return f"forbidden key {key!r} (contains {sub!r})"
    if k.startswith("market") and not (allow_market and k in _MARKET_ALLOWED):
        return f"forbidden key {key!r} (market*)"
    return None


def _walk(obj, path=""):
    """Yield (path, key, value) for every dict entry and (path, None, value)
    for every list element, depth first."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            yield p, k, v
            yield from _walk(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = f"{path}[{i}]"
            yield p, None, v
            yield from _walk(v, p)


def find_forbidden_keys(obj, *, allow_market: bool = False) -> list[tuple[str, str]]:
    out = []
    for path, key, _v in _walk(obj):
        if key is None:
            continue
        why = forbidden_key(key, allow_market=allow_market)
        if why:
            out.append((path, why))
    return out


def find_dashes(obj) -> list[str]:
    """Paths of every string (key or value) carrying U+2013 or U+2014."""
    out = []
    for path, key, v in _walk(obj):
        if key is not None and isinstance(key, str) and any(d in key for d in _DASHES):
            out.append(path)
        if isinstance(v, str) and any(d in v for d in _DASHES):
            out.append(path)
    return out


_URL_RE = re.compile(r"(?:https?:)?//[^\s\"'<>]+", re.IGNORECASE)
_HOST_RE = re.compile(r"(?<![\w.-])(?:[a-z0-9-]+\.)+(?:com|net|org|io|tv|app)(?![\w-])", re.IGNORECASE)


def find_urls(obj) -> list[tuple[str, str]]:
    """(path, string) for every string value that carries a URL or a bare host."""
    out = []
    for path, _key, v in _walk(obj):
        if isinstance(v, str) and (_URL_RE.search(v) or _HOST_RE.search(v)):
            out.append((path, v))
    return out


#: Media and embed hosts by role (plan 6.2); the allowlist grows only by commit.
VIDEO_HOSTS = ("mlb-cuts-diamond.mlb.com", "bdata-producedclips.mlb.com")
CAPTION_HOSTS = ("mlb-cuts-diamond.mlb.com", "diamond.mlb.com")
POSTER_HOST = "img.mlbstatic.com"
FRAME_HOST = "streamable.com"
_SLUG = r"[a-z0-9-]+"
_KNOWN_HOSTS = frozenset(VIDEO_HOSTS) | frozenset(CAPTION_HOSTS) | {POSTER_HOST, FRAME_HOST}
URL_ROLES = {
    "embed": re.compile(rf"^https://{re.escape(FRAME_HOST)}/m/{_SLUG}$"),
    "hls": re.compile(r"^https://(" + "|".join(re.escape(h) for h in VIDEO_HOSTS) + r")/[^?#\s]+$"),
    "mp4": re.compile(r"^https://(" + "|".join(re.escape(h) for h in VIDEO_HOSTS) + r")/[^?#\s]+$"),
    "vtt": re.compile(r"^https://(" + "|".join(re.escape(h) for h in CAPTION_HOSTS) + r")/[^?#\s]+$"),
    "poster": re.compile(rf"^https://{re.escape(POSTER_HOST)}/mlb-images/image/upload/[^?#\s]+$"),
    "page": re.compile(rf"^https://www\.mlb\.com/video/{_SLUG}$"),
    "gameday": re.compile(r"^https://www\.mlb\.com/gameday/\d+$"),
}


def url_ok(url: str, role: str) -> bool:
    """Every URL: https, no query, no whitespace, quotes or angle brackets, at
    most 300 characters, and its role's host pattern."""
    if not isinstance(url, str) or len(url) > 300 or any(c in url for c in " \t\n\"'<>"):
        return False
    pat = URL_ROLES.get(role)
    return bool(pat and pat.match(url))


def _path_matches(path: str, pattern: str) -> bool:
    """Dotted path match with `*` for one segment (list indices are segments)."""
    norm = re.sub(r"\[(\d+)\]", r".\1", path)
    parts, pats = norm.split("."), pattern.split(".")
    if len(parts) != len(pats):
        return False
    return all(q == "*" or q == p for p, q in zip(parts, pats))


def _role_of_path(path: str) -> str | None:
    norm = re.sub(r"\[(\d+)\]", r".\1", path)
    last = norm.split(".")[-1]
    if last in ("w480", "w960"):
        return "poster"
    if last in URL_ROLES:
        return last
    return None


def _wp_values(obj):
    """Every win-probability quantity (path, value) in a payload."""
    keys = {"wp", "wp_home", "before", "after", "home", "pregame_home", "score"}
    for path, key, v in _walk(obj):
        if key in keys and not isinstance(v, (dict, list)) and not path.endswith("wl.home"):
            yield path, key, v
    for path, key, v in _walk(obj):
        if key == "series" and isinstance(v, list):
            for i, row in enumerate(v):
                if isinstance(row, list) and len(row) == 5:
                    yield f"{path}[{i}][3]", "wp_home", row[3]


def _check_wp_block(gf: dict, out: list) -> None:
    wp = gf.get("wp") or {}
    series = wp.get("series") or []
    prev_ab = None
    for i, row in enumerate(series):
        if not (isinstance(row, list) and len(row) == 5):
            out.append(("2", f"wp.series[{i}] is not [ab, inning, half, wp_home, swing]"))
            continue
        if prev_ab is not None and row[0] <= prev_ab:
            out.append(("2", f"wp.series ab not strictly increasing at [{i}]"))
        prev_ab = row[0]
        if row[4] is not None and not (isinstance(row[4], int) and -1000 <= row[4] <= 1000):
            out.append(("2", f"wp.series[{i}] swing {row[4]!r} is not an integer in -1000..1000"))
    card = gf.get("card") or {}
    if card.get("state") == "final":
        last = next((row[3] for row in reversed(series) if isinstance(row, list) and row[3] is not None), None)
        ar, hr = (card.get("away") or {}).get("r"), (card.get("home") or {}).get("r")
        if last is not None and ar is not None and hr is not None and ar != hr:
            want = 1000 if hr > ar else 0
            if last != want:
                out.append(("2", f"final's last value {last} does not match the winner ({want})"))
    if wp.get("pregame_home") is not None and wp["pregame_home"] != 500:
        out.append(("2-note", f"pregame point {wp['pregame_home']} is not 500"))


def _check_card(card: dict, out: list, notes: list) -> None:
    if not isinstance(card.get("pk"), int):
        out.append(("1", f"pk {card.get('pk')!r} is not an int"))
    if card.get("state") not in STATES:
        out.append(("1", f"state {card.get('state')!r} not in the enum"))
    for side in ("away", "home"):
        t = card.get(side) or {}
        if t.get("team_id") is not None and not isinstance(t.get("team_id"), int):
            out.append(("1", f"{side}.team_id {t.get('team_id')!r} is not an int"))
        r = t.get("r")
        line = card.get("line") or []
        idx = 0 if side == "away" else 1
        vals = [row[idx] for row in line if isinstance(row, list) and len(row) == 2 and row[idx] is not None]
        if r is not None and line and sum(vals) != r:
            out.append(("2", f"{side} innings sum {sum(vals)} differs from runs {r}"))
    if card.get("state") != "final" and card.get("star") is not None:
        out.append(("3", "star on a game that is not final"))


def _check_stars(gf: dict, out: list) -> None:
    card = gf.get("card") or {}
    stars = gf.get("stars") or []
    if stars and card.get("state") != "final":
        out.append(("3", "stars on a game that is not final"))
    if len(stars) > MAX_STARS:
        out.append(("3", f"{len(stars)} stars, at most {MAX_STARS}"))
    ids = [s.get("id") for s in stars]
    if len(set(ids)) != len(ids):
        out.append(("3", "stars are not distinct"))
    for s in stars:
        if not (isinstance(s.get("score"), int) and s["score"] > 0):
            out.append(("3", f"star {s.get('id')} score {s.get('score')!r} is not a positive integer"))
    if stars:
        ar, hr = (card.get("away") or {}).get("r"), (card.get("home") or {}).get("r")
        if ar is not None and hr is not None and ar != hr:
            win_code = (card.get("home") if hr > ar else card.get("away")).get("code")
            if stars[0].get("team") != win_code:
                out.append(("3", f"star 1 is from {stars[0].get('team')}, the winner is {win_code}"))
            win_scores = [s["score"] for s in stars if s.get("team") == win_code and isinstance(s.get("score"), int)]
            if win_scores and stars[0].get("score") < max(win_scores):
                out.append(("3", "star 1 is not the winning club's top candidate"))
    if len(stars) == 3 and isinstance(stars[1].get("score"), int) and isinstance(stars[2].get("score"), int):
        if stars[1]["score"] < stars[2]["score"]:
            out.append(("3", "stars 2 and 3 increase"))
    want_note = bool(len(stars) >= 2 and stars[0].get("score", 0) < stars[1].get("score", 0))
    if bool(gf.get("first_star_note")) != want_note:
        out.append(("3", f"first_star_note {gf.get('first_star_note')!r}, expected {want_note}"))
    big = gf.get("plays_big") or []
    if len(big) > N_BIG_PLAYS:
        out.append(("3", f"{len(big)} biggest plays, at most {N_BIG_PLAYS}"))
    keyed = [(-abs(b.get("swing") or 0), -(b.get("li") if b.get("li") is not None else -1.0), b.get("ab", 0)) for b in big]
    if keyed != sorted(keyed):
        out.append(("3", "plays_big is not sorted by the rule"))


def _check_urls(kind: str, obj: dict, out: list) -> None:
    spec = FILE_KINDS.get(kind) or {}
    exempt = spec.get("copyright_exempt", False)
    allowed = spec.get("url_paths", ())
    clips = obj.get("clips") if isinstance(obj.get("clips"), dict) else {}
    for path, s in find_urls(obj):
        if exempt and path == "copyright":
            if MLB_TERMS_URL not in s or _URL_RE.sub("", s).strip() == "":
                out.append(("4", "copyright key does not carry StatsAPI's line with MLB's terms URL"))
            continue
        if not any(_path_matches(path, pat) for pat in allowed):
            out.append(("4", f"URL outside a clip object at {path}"))
            continue
        role = _role_of_path(path)
        if role is None:
            # index.json's rules.video block names the allowlisted hosts
            # themselves (plan 8.1): a bare host from the allowlist, never a URL
            if s in _KNOWN_HOSTS:
                continue
            out.append(("4", f"string at {path} is not an allowlisted host name"))
            continue
        if not url_ok(s, role):
            out.append(("4", f"URL at {path} fails its role allowlist ({role})"))
    if kind == "game":
        refs = []
        for path, key, v in _walk(obj):
            if key == "clip" and v is not None and not path.startswith("clips."):
                refs.append((path, v))
        for path, v in refs:
            if v not in clips:
                out.append(("4", f"clip reference {v!r} at {path} does not resolve in clips"))


def validate_payload(kind: str, obj, *, name: str | None = None, allow_market: bool = False,
                     disk_generated_at: str | None = None) -> dict:
    """The file-independent rules of plan 8.5 for one payload. Returns
    `{ok, refused [(rule, message)], logged [(rule, message)], bytes}`.
    Rules 7 (on-disk age) and 11 (revs on disk) belong to the job; rule 7 runs
    here only when the caller passes `disk_generated_at`."""
    refused: list = []
    logged: list = []
    spec = FILE_KINDS.get(kind)
    if spec is None:
        return {"ok": False, "refused": [("0", f"unknown file kind {kind!r}")], "logged": [], "bytes": 0}
    # 5. serializable without NaN
    try:
        data = dumps(obj).encode("utf-8")
    except (TypeError, ValueError) as e:
        return {"ok": False, "refused": [("5", f"not serializable: {e}")], "logged": [], "bytes": 0}
    n = len(data)
    # 6. budgets and ceilings
    if n > spec["ceiling"]:
        refused.append(("6", f"{n} bytes above the ceiling {spec['ceiling']}"))
    elif n > spec["budget"]:
        logged.append(("6", f"over_budget {n} > {spec['budget']}"))
    if isinstance(obj, dict):
        # 1. schema, name, ids, enum
        if obj.get("schema") != SCHEMA and kind in ("latest", "index", "season_index", "date", "game"):
            refused.append(("1", f"schema {obj.get('schema')!r} is not {SCHEMA}"))
        if kind == "date":
            if name is not None and str(name).replace("\\", "/").split("/")[-1] != f"{obj.get('date')}.json":
                refused.append(("1", f"file name {name!r} does not equal date {obj.get('date')!r}"))
            for i, card in enumerate(obj.get("games") or []):
                _check_card(card or {}, refused, logged)
        if kind == "game":
            card = obj.get("card") or {}
            _check_card(card, refused, logged)
            if not isinstance(obj.get("pk"), int) or obj.get("pk") != card.get("pk"):
                refused.append(("1", "game pk missing or different from its card"))
            if name is not None and str(name).replace("\\", "/").split("/")[-1] != f"{obj.get('pk')}.json":
                refused.append(("1", f"file name {name!r} does not equal pk {obj.get('pk')!r}"))
            _check_wp_block(obj, refused)
            _check_stars(obj, refused)
        if kind == "latest":
            for g in obj.get("live") or []:
                if not isinstance((g or {}).get("pk"), int):
                    refused.append(("1", "latest.live pk is not an int"))
        # 2. every win-probability value an integer 0..1000 or null
        for path, key, v in _wp_values(obj):
            if v is None:
                continue
            if key == "score" and not path.startswith("stars"):
                continue
            if not (isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 1000):
                refused.append(("2", f"{path} = {v!r} is not an integer in 0..1000 or null"))
        for rule, msg in [x for x in refused if x[0] == "2-note"]:
            refused.remove((rule, msg))
            logged.append(("2", msg))
        # 4. URLs
        _check_urls(kind, obj, refused)
        # 7. not older than the file on disk
        if disk_generated_at is not None and str(obj.get("generated_at") or "") < str(disk_generated_at):
            refused.append(("7", f"generated_at {obj.get('generated_at')!r} older than on disk {disk_generated_at!r}"))
    # 9. forbidden keys at every depth
    for path, why in find_forbidden_keys(obj, allow_market=allow_market):
        refused.append(("9", f"{why} at {path}"))
    # 10. no em or en dash in any string (MLB strings were normalised by the builders)
    for path in find_dashes(obj):
        refused.append(("10", f"dash in string at {path}"))
    return {"ok": not refused, "refused": refused, "logged": logged, "bytes": n}


def validate_files(files: dict, *, allow_market: bool = False) -> dict:
    """Per-file results for `{name: obj}` (the kind from the name) or
    `{name: (kind, obj)}`."""
    out = {}
    for name, item in files.items():
        if isinstance(item, tuple) and len(item) == 2:
            kind, obj = item
        else:
            kind, obj = kind_of_name(name), item
        if kind is None:
            out[name] = {"ok": False, "refused": [("0", f"no file kind matches {name!r}")], "logged": [], "bytes": 0}
            continue
        out[name] = validate_payload(kind, obj, name=name, allow_market=allow_market)
    return out


# ---- rule 8: the shrink guard -------------------------------------------- #
def _series_key(game: dict) -> tuple | None:
    """The series a schedule game belongs to: its description with the game
    number stripped, plus the two club ids in a fixed order."""
    desc = normalize_text(game.get("description") or (game.get("seriesStatus") or {}).get("description") or "")
    desc = re.sub(r"\s*Game\s+\d+\s*$", "", desc).strip()
    teams = game.get("teams") or {}
    ids = tuple(sorted(str(((teams.get(s) or {}).get("team") or {}).get("id")) for s in ("away", "home")))
    if not desc:
        return None
    return (desc, ids)


def series_over(pk, schedule_games: list[dict]) -> bool:
    """Is the series of game `pk` over: `seriesStatus.isOver` on any game of
    the series, or the wins of one club (from `isWinner` on final games, or
    `seriesStatus.wins` on the latest game) reaching the round's requirement
    (`gamesInSeries // 2 + 1`)."""
    games = [g for g in schedule_games if isinstance(g, dict)]
    me = next((g for g in games if _int(g.get("gamePk"), -1) == _int(pk, -2)), None)
    key = _series_key(me) if me else None
    members = [g for g in games if key is not None and _series_key(g) == key]
    if not members and me is None:
        return False
    need = 0
    wins: dict = {}
    for g in members:
        ss = g.get("seriesStatus") or {}
        if ss.get("isOver"):
            return True
        total = _int(g.get("gamesInSeries"), 0) or _int(ss.get("totalGames"), 0)
        need = max(need, total // 2 + 1 if total else 0)
        if need and max(_int(ss.get("wins"), 0), _int(ss.get("losses"), 0)) >= need:
            return True
        if is_final(g.get("status")):
            for side in ("away", "home"):
                t = (g.get("teams") or {}).get(side) or {}
                if t.get("isWinner"):
                    tid = (t.get("team") or {}).get("id")
                    wins[tid] = wins.get(tid, 0) + 1
    return bool(need) and any(v >= need for v in wins.values())


def check_shrink(prev_cards: list[dict], new_cards: list[dict], schedule_games: list[dict]) -> list[tuple[str, str]]:
    """Rule 8: a date's game count drops only when the schedule marks each
    missing game as moved (postponed, suspended, cancelled, rescheduled), or
    when the missing game was last seen with `ifNecessary` "Y" and its series
    is over. Returns the refusals (empty when the drop is allowed)."""
    new_pks = {c.get("pk") for c in new_cards}
    sched = {_int(g.get("gamePk"), -1): g for g in schedule_games if isinstance(g, dict)}
    out = []
    for c in prev_cards:
        pk = c.get("pk")
        if pk in new_pks:
            continue
        g = sched.get(pk)
        if g is not None:
            st, _r = game_state(g.get("status"))
            if st in ("postponed", "suspended", "cancelled") or g.get("rescheduleDate") or g.get("resumeDate"):
                continue
        if c.get("state") in ("postponed", "suspended", "cancelled"):
            continue
        series = c.get("series") or {}
        if series.get("if_necessary"):
            # MLB deletes an unneeded if-necessary game from /schedule rather
            # than marking it, so the series is identified from the card itself
            probe = g or {"gamePk": pk, "description": series.get("desc"), "ifNecessary": "Y",
                          "teams": {s: {"team": {"id": (c.get(s) or {}).get("team_id")}} for s in ("away", "home")}}
            if series_over(pk, list(schedule_games) + [probe]):
                continue
        out.append(("8", f"game {pk} left the date without a moved status or a finished if-necessary series"))
    return out


__all__ = [
    "SCORES_LIVE", "SCORES_EMBED_VIDEO", "SCORES_EMBED_RECONFIRMED", "SCHEMA",
    "STARS_RULE", "MIN_OUTS", "MIN_COVERAGE", "FIRST_STAR_WINNER", "SCORE_DECIMALS", "STAR_ORDER",
    "PLAYS_RULE", "MIN_SWING", "N_BIG_PLAYS", "STATES", "FIRST_STAR_NOTE_TEXT", "MLB_TERMS_URL",
    "CLUB_BY_ID", "club_code", "normalize_text", "round_half_up", "thousandths", "ordinal",
    "dumps", "rev_of", "game_state", "is_final", "elements_of", "complete_elements", "wp_series",
    "coverage_ok", "play_credits", "player_wpa", "unattributed_home", "EVENT_PHRASES",
    "FIELD_OUT_LABELS", "event_phrase", "play_text", "last_name_map", "short_name", "auto_runner",
    "situations", "play_rows",
    "biggest_plays", "runs_prevented", "runs_saved", "star_candidates", "pick_stars", "stars_of_game",
    "hitter_sentence", "pitcher_sentence", "box_rows", "build_card", "build_game_file",
    "build_date_file", "FILE_KINDS", "register_file_kind", "kind_of_name", "forbidden_key",
    "find_forbidden_keys", "find_dashes", "find_urls", "url_ok", "URL_ROLES", "validate_payload",
    "validate_files", "series_over", "check_shrink", "debut_ids",
    "VIDEO_BRANCH", "SPORTSBOOK_TAGS", "parse_duration", "pick_file", "trim_content", "clip_object",
    "event_label", "join_clips", "attach_clips", "diamond_gating_on", "embed_reconfirmed",
]
