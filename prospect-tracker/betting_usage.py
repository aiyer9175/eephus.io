"""Schema-4 dark-capture builders: bullpen availability, schedule rest, weather.
Also the schema-5 pinch-hit and relief-hand tally (section 5f, at the bottom).
Also the schema-7 starter-workload capture (the section "Starter workload: expected
outs and pitches per start"), after the schema-4 pitcher builder.

Pre-registered in docs/diamond-betting.md section 5d BEFORE this file existed
and before any number here was related to any outcome. Nothing served reads any
of it; the columns accrue so that one day they can be measured on DATED history
instead of being reconstructed from live season-to-date files, which is the leak
the vintage store exists to close.

THE OWNER ASK, in his words: "if a reliever is used 2 days in a row, they
usually never pitch the next day", and price that. Also schedule rest, and
weather.

EVERY INPUT IS ALREADY ON DISK. This adds no API, no credential and no nightly
network call. `.cache/game_feeds` holds complete StatsAPI live feeds, and
betting_model's completed-games cache indexes them by date and org, so a vintage
for date D opens roughly a hundred feeds rather than scanning twenty thousand.

WHY WEATHER IS ONLY CLIMATOLOGY HERE. `gameData.weather` is the weather AT THE
GAME. It is not known before first pitch, so pricing on it reads the future, and
temperature is exactly the variable whose observed value is most correlated with
what it would be predicting. The servable form is a trailing venue window ending
the day BEFORE the game. The observed value is a contaminated screen that lives
in the diagnostics and never in a vintage column; section 5d says so and says
why.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FEED_DIR = ROOT / ".cache" / "game_feeds"

# ---------------------------------------------------------------------------
# policy constants
# ---------------------------------------------------------------------------
#: A reliever who worked BOTH of the two prior calendar days is treated as
#: unavailable. This is the owner's own statement of the convention and it
#: matches ordinary bullpen practice.
#:
#: POLICY, NOT MEASUREMENT, and named as such the way PROVISIONAL_MIN_EDGE and
#: SLATE_OPEN_MIN_PREGAME_SHARE are. Nothing in this repo can derive it.
#: TUNING IT AGAINST OUTCOMES BEFORE THE 5d-A GATE RUNS WOULD BE FITTING THE
#: FEATURE TO THE EVAL WINDOW, which is the whole failure the vintage store
#: exists to prevent. A sensitivity check across neighbouring values is a
#: separate, later question that belongs after the gate, not before it.
B2B_DAYS = 2

#: A reliever who worked YESTERDAY on this many pitches or more is treated as
#: unavailable today. Same policy status as B2B_DAYS; 30 is the common
#: threshold for a heavy relief outing.
HEAVY_PITCHES = 30

#: Trailing window, in days, for the venue weather climatology. Trailing rather
#: than season-to-date because an April game is not evidence about a September
#: one, and pooling the season biases every late estimate cold.
WX_WINDOW_DAYS = 30

#: Minimum games in that window before a climatology value is published. Set
#: against what a venue actually hosts in thirty days (roughly nine to twelve),
#: not against a statistical ideal. The realized count rides in the basis.
WX_MIN_GAMES = 4

#: Signed out-to-centre component of the wind, by StatsAPI's closed direction
#: vocabulary. Out is positive because that is the direction that adds runs.
#: Lateral and calm are 0.0 rather than null: they are a measured absence of
#: an out-or-in component, which is a value on this scale.
#: "Varies" is None, because it is the absence of a reading, not a zero.
WIND_OUT_COMPONENT = {
    "out to cf": 1.0, "out to lf": 0.7, "out to rf": 0.7,
    "in from cf": -1.0, "in from lf": -0.7, "in from rf": -0.7,
    "l to r": 0.0, "r to l": 0.0, "calm": 0.0, "none": 0.0,
    "varies": None,
}

_WIND_RE = re.compile(r"^\s*(\d+)\s*mph\s*,\s*(.+?)\s*$", re.I)


def _org(name):
    """The site's canonical three-letter org code, or the input unchanged.

    THE JOIN THIS CLOSES. `bullpen_leaderboards.json` spells seven clubs
    differently from the completed-games cache: AZ/ARI, CWS/CHW, KC/KCR, SD/SDP,
    SF/SFG, TB/TBR, WSH/WSN. Joining the raw strings silently produced an empty
    depth list for 7 of 30 clubs, which reads downstream as "this club has no
    bullpen" rather than as a failed join. Both sides go through the resolver
    the rest of the module already uses.
    """
    if name is None:
        return None
    try:
        from trades import canonical_org
        return canonical_org(name) or name
    except Exception:                                            # noqa: BLE001
        return name


# ---------------------------------------------------------------------------
# feed reading
# ---------------------------------------------------------------------------
def _feed(game_pk, feed_dir: Path | None = None) -> dict | None:
    p = (feed_dir or FEED_DIR) / f"{int(game_pk)}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:                                            # noqa: BLE001
        return None


def parse_wind(raw) -> tuple[float | None, float | None]:
    """('9 mph, Out To CF') -> (9.0, +1.0). (speed, signed out component).

    Returns (None, None) on anything unparseable, and (speed, None) when the
    speed reads but the direction is "Varies", which is a stated absence of a
    direction rather than a calm one.
    """
    m = _WIND_RE.match(str(raw or ""))
    if not m:
        return None, None
    try:
        mph = float(m.group(1))
    except ValueError:
        return None, None
    comp = WIND_OUT_COMPONENT.get(m.group(2).strip().lower(), None)
    return mph, (None if comp is None else mph * comp)


def game_weather(game_pk, feed_dir: Path | None = None) -> dict | None:
    """{temp_f, condition, wind_mph, wind_out, venue_id} off one cached feed."""
    d = _feed(game_pk, feed_dir)
    if not d:
        return None
    gd = d.get("gameData") or {}
    w = gd.get("weather") or {}
    try:
        temp = float(w.get("temp"))
    except (TypeError, ValueError):
        temp = None
    mph, out = parse_wind(w.get("wind"))
    return {"temp_f": temp, "condition": w.get("condition"),
            "wind_mph": mph, "wind_out": out,
            "venue_id": (gd.get("venue") or {}).get("id")}


def game_pitchers(game_pk, feed_dir: Path | None = None) -> dict | None:
    """{side: [{mlbam, outs, pitches, is_start}]} off one cached feed.

    `is_start` is positional: StatsAPI lists `pitchers` in the order they
    appeared, so the first is the starter. That is the definition the whole
    availability rule needs, and it does not depend on a gameStatus field that
    a suspended game can leave inconsistent.
    """
    d = _feed(game_pk, feed_dir)
    if not d:
        return None
    teams = ((d.get("liveData") or {}).get("boxscore") or {}).get("teams") or {}
    out: dict = {}
    for side in ("home", "away"):
        t = teams.get(side) or {}
        players = t.get("players") or {}
        rows = []
        for i, pid in enumerate(t.get("pitchers") or []):
            st = ((players.get(f"ID{pid}") or {}).get("stats") or {}).get("pitching") or {}
            try:
                outs = int(st.get("outs") or 0)
            except (TypeError, ValueError):
                outs = 0
            pitches = st.get("pitchesThrown")
            if pitches is None:
                pitches = st.get("numberOfPitches")
            try:
                pitches = int(pitches)
            except (TypeError, ValueError):
                pitches = None
            rows.append({"mlbam": int(pid), "outs": outs, "pitches": pitches,
                         "is_start": i == 0})
        out[side] = rows
    return out


# ---------------------------------------------------------------------------
# the usage ledger
# ---------------------------------------------------------------------------
def usage_ledger(games: list[dict], *, feed_dir: Path | None = None,
                 since: str | None = None, until: str | None = None) -> list[dict]:
    """One row per (pitcher, game) over the games in [since, until].

        {date, org, mlbam, outs, pitches, is_start}

    `games` is betting_model's completed-games cache, which carries date,
    game_pk, home_org and away_org. Only the game_pks inside the window are
    opened, which is what keeps this off the twenty-thousand-file scan.
    """
    rows: list[dict] = []
    for g in games or []:
        d = g.get("date")
        if not d:
            continue
        if since and d < since:
            continue
        if until and d > until:
            continue
        pit = game_pitchers(g.get("game_pk"), feed_dir)
        if not pit:
            continue
        for side, org_key in (("home", "home_org"), ("away", "away_org")):
            org = g.get(org_key)
            if not org:
                continue
            for r in pit.get(side) or []:
                rows.append({"date": d, "org": _org(org), **r})
    return rows


def _days_before(on_date: str, n: int) -> list[str]:
    d0 = date.fromisoformat(on_date)
    return [(d0 - timedelta(days=k)).isoformat() for k in range(1, n + 1)]


def unavailable_arms(org: str, on_date: str, ledger: list[dict]) -> dict:
    """{mlbam: reason} for this club's relievers who cannot pitch on `on_date`.

    Two rules, both from section 5d and both POLICY:
      * worked on BOTH of the two prior calendar days, or
      * worked YESTERDAY on HEAVY_PITCHES or more.

    STARTERS ARE EXCLUDED, because a starter's rest is a different question with
    a different answer (`sp_rest_days`), and counting him against the bullpen
    would make every club look a man short the day after every game.
    """
    prior = _days_before(on_date, B2B_DAYS)
    yday = prior[0]
    org = _org(org)
    by_arm: dict[int, dict] = {}
    for r in ledger:
        if r.get("org") != org or r.get("is_start"):
            continue
        if r.get("date") not in prior:
            continue
        by_arm.setdefault(r["mlbam"], {})[r["date"]] = r
    out: dict[int, str] = {}
    for mlbam, days in by_arm.items():
        if len(days) >= B2B_DAYS and all(d in days for d in prior):
            out[mlbam] = f"pitched on each of the {B2B_DAYS} prior days"
            continue
        y = days.get(yday)
        if y and (y.get("pitches") or 0) >= HEAVY_PITCHES:
            out[mlbam] = f"threw {y['pitches']} pitches yesterday"
    return out


def team_availability(org: str, on_date: str, depth: list[dict],
                      ledger: list[dict]) -> dict:
    """The four schema-4 bullpen columns for one club.

    `depth` is a bullpen_leaderboards team's `depth` list, whose `key` IS the
    mlbam id as a string, which is what makes the join to the feed ledger
    direct rather than a name match.

    `pen_plus_avail` is the servable form of the owner's ask: the club's
    bullpen quality recomputed over the arms that can actually pitch tonight,
    innings-weighted the same way the published bullpen_plus is. It drops
    straight into betting_model.game_prevention_z, where bullpen_plus already
    sits, which is why it is built in this shape rather than as a raw count.
    """
    org = _org(org)
    unavail = unavailable_arms(org, on_date, ledger)
    arms = []
    for r in depth or []:
        try:
            mlbam = int(r.get("key"))
        except (TypeError, ValueError):
            continue                       # unreadable id: cannot be judged, so skip
        rp, ip = r.get("rem_plus"), r.get("ip")
        if rp is None or ip is None:
            continue
        arms.append({"mlbam": mlbam, "rem_plus": float(rp), "ip": float(ip),
                     "available": mlbam not in unavail})
    prior = _days_before(on_date, 3)
    outs_l3 = sum(r.get("outs") or 0 for r in ledger
                  if r.get("org") == org and not r.get("is_start")
                  and r.get("date") in prior)
    avail = [a for a in arms if a["available"]]
    w = sum(a["ip"] for a in avail)
    pen_plus_avail = (sum(a["rem_plus"] * a["ip"] for a in avail) / w) if w else None
    return {
        "pen_b2b_arms": sum(1 for m, why in unavail.items() if "each of" in why),
        "pen_arms_avail": len(avail) if arms else None,
        "pen_ip_l3": round(outs_l3 / 3.0 / 3.0, 3),      # outs -> innings -> per day
        "pen_plus_avail": round(pen_plus_avail, 2) if pen_plus_avail is not None else None,
        "n_depth": len(arms),
        "n_unavailable": len(unavail),
        "unavailable": {str(m): why for m, why in sorted(unavail.items())},
    }


# ---------------------------------------------------------------------------
# schedule rest
# ---------------------------------------------------------------------------
def schedule_rest(org: str, on_date: str, games: list[dict]) -> dict:
    """{rest_days, games_in_l7} for one club, off the completed-games cache.

    `rest_days` is days since this club's previous game, so 1 is the ordinary
    day-after and 0 is the second leg of a doubleheader. None when the club has
    no prior game on file, which is a stated absence rather than a large number.
    """
    org = _org(org)
    days = sorted({g["date"] for g in games or []
                   if g.get("date") and g["date"] < on_date
                   and org in (_org(g.get("home_org")), _org(g.get("away_org")))})
    if not days:
        return {"rest_days": None, "games_in_l7": 0}
    d0 = date.fromisoformat(on_date)
    same_day = sum(1 for g in games or []
                   if g.get("date") == on_date
                   and org in (_org(g.get("home_org")), _org(g.get("away_org"))))
    last = date.fromisoformat(days[-1])
    window = {(d0 - timedelta(days=k)).isoformat() for k in range(1, 8)}
    n7 = sum(1 for g in games or []
             if g.get("date") in window
             and org in (_org(g.get("home_org")), _org(g.get("away_org"))))
    return {"rest_days": 0 if same_day else (d0 - last).days, "games_in_l7": n7}


def starter_rest(mlbam, on_date: str, ledger: list[dict]) -> int | None:
    """Days since this pitcher's previous appearance. None on a first
    appearance, which is a season debut and not a large rest number."""
    if mlbam is None:
        return None
    try:
        mid = int(mlbam)
    except (TypeError, ValueError):
        return None
    days = sorted({r["date"] for r in ledger
                   if r.get("mlbam") == mid and r.get("date") < on_date})
    if not days:
        return None
    return (date.fromisoformat(on_date) - date.fromisoformat(days[-1])).days


# ---------------------------------------------------------------------------
# weather climatology
# ---------------------------------------------------------------------------
def venue_climatology(venue_id, on_date: str, games: list[dict], *,
                      feed_dir: Path | None = None,
                      window_days: int = WX_WINDOW_DAYS) -> dict:
    """Trailing-window mean temperature and out-to-centre wind at one venue.

    STRICTLY BEFORE `on_date`, which is what makes this servable at all: the
    observed weather of the game being priced is not knowable pregame, and
    section 5d keeps that value out of the vintage store entirely.

    Trailing rather than season-to-date because an April game is not evidence
    about a September one. The realized count rides on the result so a reader
    can see how thin the estimate is rather than taking the mean on trust.
    """
    if venue_id is None:
        return {"wx_temp_climo": None, "wx_wind_out_climo": None,
                "n_games": 0, "basis": "no venue id on the game"}
    d0 = date.fromisoformat(on_date)
    lo = (d0 - timedelta(days=window_days)).isoformat()
    temps, winds = [], []
    for g in games or []:
        d = g.get("date")
        if not d or d >= on_date or d < lo:
            continue
        w = game_weather(g.get("game_pk"), feed_dir)
        if not w or w.get("venue_id") != venue_id:
            continue
        if w.get("temp_f") is not None:
            temps.append(w["temp_f"])
        if w.get("wind_out") is not None:
            winds.append(w["wind_out"])
    n = len(temps)
    if n < WX_MIN_GAMES:
        return {"wx_temp_climo": None, "wx_wind_out_climo": None, "n_games": n,
                "basis": (f"only {n} game(s) at this venue in the {window_days}d "
                          f"window before {on_date}; the floor is {WX_MIN_GAMES}")}
    return {
        "wx_temp_climo": round(sum(temps) / n, 2),
        "wx_wind_out_climo": round(sum(winds) / len(winds), 3) if winds else None,
        "n_games": n,
        "basis": (f"mean of {n} game(s) at this venue in the {window_days}d window "
                  f"ending the day before {on_date}; observed game-time weather is "
                  f"NEVER used for the game being priced (section 5d)"),
    }


# ---------------------------------------------------------------------------
# the schema-4 builder, one pass
# ---------------------------------------------------------------------------
def build_schema4_team_columns(*, on_date: str, data_dir: Path | None = None,
                               feed_dir: Path | None = None,
                               games: list[dict] | None = None,
                               depth_by_org: dict | None = None) -> dict:
    """{column: {"values": {org: v}, "basis": str}} for every schema-4 team
    column, in ONE pass over the feeds.

    ONE PASS MATTERS HERE. Availability needs the three days before `on_date`
    and the climatology needs thirty, so a naive per-club implementation would
    open the same feeds thirty times over. The weather index is built once,
    keyed by venue, and every club reads its own home park out of it.

    Every input is injectable so the whole thing runs offline in a test with a
    stubbed schedule, which is the contract dfs_export.build_payload states and
    which this file follows for the same reason.
    """
    from datetime import date as _date
    d0 = _date.fromisoformat(on_date)
    lo_wx = (d0 - timedelta(days=WX_WINDOW_DAYS)).isoformat()
    lo_pen = (d0 - timedelta(days=3)).isoformat()
    yday = (d0 - timedelta(days=1)).isoformat()

    if games is None:
        try:
            import betting_model as bm
            games = bm.completed_games(season=on_date[:4], refresh=False)
        except Exception:                                        # noqa: BLE001
            games = []
    games = [g for g in (games or []) if g.get("date")]

    if depth_by_org is None:
        depth_by_org = {}
        try:
            blob = json.loads(((data_dir or (ROOT / "data")) /
                               "bullpen_leaderboards.json").read_text(encoding="utf-8"))
            for t in blob.get("teams") or []:
                depth_by_org[_org(t.get("team"))] = t.get("depth") or []
        except Exception:                                        # noqa: BLE001
            depth_by_org = {}

    ledger = usage_ledger(games, feed_dir=feed_dir, since=lo_pen, until=yday)

    # ONE weather scan, keyed by venue, plus each club's most recent home venue.
    wx: dict = {}
    home_venue: dict = {}
    for g in games:
        d = g.get("date")
        if not d or d >= on_date or d < lo_wx:
            continue
        w = game_weather(g.get("game_pk"), feed_dir)
        if not w or w.get("venue_id") is None:
            continue
        wx.setdefault(w["venue_id"], {"temps": [], "winds": []})
        if w.get("temp_f") is not None:
            wx[w["venue_id"]]["temps"].append(w["temp_f"])
        if w.get("wind_out") is not None:
            wx[w["venue_id"]]["winds"].append(w["wind_out"])
        ho = _org(g.get("home_org"))
        if ho:
            home_venue[ho] = w["venue_id"]      # last one wins, so it is the most recent

    orgs = sorted(set(depth_by_org) |
                  {_org(g.get("home_org")) for g in games if g.get("home_org")})
    orgs = [o for o in orgs if o]

    cols = ("pen_b2b_arms", "pen_arms_avail", "pen_ip_l3", "pen_plus_avail",
            "rest_days", "games_in_l7", "wx_temp_climo", "wx_wind_out_climo")
    # Framing rides the same pass because it reads the same feeds; it is scored
    # on a 30-day window rather than the 3-day availability one, so it takes its
    # own scan and is isolated the way every other builder here is.
    try:
        frame = framing_rates(games, on_date, feed_dir=feed_dir)
    except Exception as exc:                                     # noqa: BLE001
        frame = {"values": {},
                 "basis": f"ABSENT: the framing builder raised {type(exc).__name__}: {exc}"}
    values: dict = {c: {} for c in cols}
    n_thin_wx = 0
    for org in orgs:
        a = team_availability(org, on_date, depth_by_org.get(org) or [], ledger)
        for c in ("pen_b2b_arms", "pen_arms_avail", "pen_ip_l3", "pen_plus_avail"):
            values[c][org] = a[c]
        r = schedule_rest(org, on_date, games)
        values["rest_days"][org] = r["rest_days"]
        values["games_in_l7"][org] = r["games_in_l7"]
        v = home_venue.get(org)
        blk = wx.get(v) or {"temps": [], "winds": []}
        if len(blk["temps"]) >= WX_MIN_GAMES:
            values["wx_temp_climo"][org] = round(sum(blk["temps"]) / len(blk["temps"]), 2)
            values["wx_wind_out_climo"][org] = (
                round(sum(blk["winds"]) / len(blk["winds"]), 3) if blk["winds"] else None)
        else:
            n_thin_wx += 1

    n_led = len({(r["org"], r["date"]) for r in ledger})
    pen_basis = (f"betting_usage over {len(ledger)} appearance(s) in {n_led} club-day(s) "
                 f"from {lo_pen} to {yday}; unavailable = worked both of the "
                 f"{B2B_DAYS} prior days, or {HEAVY_PITCHES}+ pitches yesterday "
                 f"(POLICY constants, docs/diamond-betting.md 5d)")
    wx_basis = (f"venue climatology over the {WX_WINDOW_DAYS}d window {lo_wx} to "
                f"{yday}, {len(wx)} venue(s) resolved, {n_thin_wx} club(s) below the "
                f"{WX_MIN_GAMES}-game floor. Observed game-time weather is NEVER "
                f"used for the game being priced (5d)")
    rest_basis = (f"days since the club's previous game and games in the 7 days "
                  f"before {on_date}, off the completed-games cache "
                  f"({len(games)} game(s))")
    basis = {"pen_b2b_arms": pen_basis, "pen_arms_avail": pen_basis,
             "pen_ip_l3": pen_basis, "pen_plus_avail": pen_basis,
             "rest_days": rest_basis, "games_in_l7": rest_basis,
             "wx_temp_climo": wx_basis, "wx_wind_out_climo": wx_basis}
    out = {c: {"values": values[c], "basis": basis[c]} for c in cols}
    out["catch_frame_rate"] = frame
    return out


def build_starter_rest(pitchers: dict, *, on_date: str,
                       games: list[dict] | None = None,
                       feed_dir: Path | None = None) -> dict:
    """{mlbam_str: days_since_last_appearance} for the pitchers in a vintage.

    None on a season debut, which is a stated absence rather than a large rest
    number, and a large rest number is exactly what a silent zero-or-999 would
    become downstream.
    """
    from datetime import date as _date
    if games is None:
        try:
            import betting_model as bm
            games = bm.completed_games(season=on_date[:4], refresh=False)
        except Exception:                                        # noqa: BLE001
            games = []
    lo = (_date.fromisoformat(on_date) - timedelta(days=21)).isoformat()
    yday = (_date.fromisoformat(on_date) - timedelta(days=1)).isoformat()
    ledger = usage_ledger(games, feed_dir=feed_dir, since=lo, until=yday)
    out = {}
    for mid in pitchers or {}:
        out[str(mid)] = starter_rest(mid, on_date, ledger)
    return out


def build_pitcher_schema4(pitchers: dict, *, on_date: str,
                          games: list[dict] | None = None,
                          feed_dir: Path | None = None) -> dict:
    """Both schema-4 pitcher columns in one call:
    {"sp_rest_days": {...}, "sp_tto3_bf": {...}}, each {mlbam_str: value}.

    Isolated per column: one builder failing costs its own column a stated null
    and never the snapshot, which is the rule every builder in this file
    follows.
    """
    if games is None:
        try:
            import betting_model as bm
            games = bm.completed_games(season=on_date[:4], refresh=False)
        except Exception:                                        # noqa: BLE001
            games = []
    out: dict = {}
    try:
        out["sp_rest_days"] = {"values": build_starter_rest(
            pitchers, on_date=on_date, games=games, feed_dir=feed_dir)}
    except Exception as exc:                                     # noqa: BLE001
        out["sp_rest_days"] = {"values": {},
                               "basis": f"ABSENT: sp_rest_days raised {type(exc).__name__}: {exc}"}
    try:
        tto = tto_exposure(games, on_date, feed_dir=feed_dir)
        out["sp_tto3_bf"] = {"values": {k: v for k, v in tto["values"].items()
                                        if k in (pitchers or {})},
                             "basis": tto["basis"]}
    except Exception as exc:                                     # noqa: BLE001
        out["sp_tto3_bf"] = {"values": {},
                             "basis": f"ABSENT: sp_tto3_bf raised {type(exc).__name__}: {exc}"}
    return out


# ---------------------------------------------------------------------------
# schema 7: the starter-workload dark capture (docs/diamond-betting.md, the
# section "Starter workload: expected outs and pitches per start")
# ---------------------------------------------------------------------------
# Four pitcher columns (`sp_n365`, `sp_budget`, `sp_ppo`, `sp_xouts`) and one team
# column (`bat_ppa_l30`), built off `.cache/game_feeds` for games dated STRICTLY
# BEFORE the vintage date, on the priors stage 1 froze. DARK: nothing served reads
# any of them, and nothing here relates one to a game result or a price. The game's
# xOuts lives in `starter_workload_xouts_candidate`, which nothing served calls.
#
# WHAT A TALLY READS, AND WHAT IT NEVER READS. Per play: the half inning, the
# matchup pitcher, the out count after the play (`count.outs`), the isPitch flag of
# each play event, and `result.eventType` ONLY to tell a plate appearance from a
# non-PA terminal event. The score fields beside them are never read, and the
# completed-games rows are read for game_pk, date and the two orgs only.
#
# THE DEFINITIONS ARE THE STAGE-1 LAB'S, so the capture and the corpus count one
# thing (test_schema7_builders.py holds the parity): a start is the first pitcher
# of each fielding half; a pitch belongs to the pitcher of its play (matchup); the
# outs on a play are the out count after it minus the count before it, reset each
# half inning; a club's pitches seen and PA are its batting half's sums.

#: The starter's own trailing window, in days: dates D - 365 to D - 1.
SW_WINDOW_DAYS = 365
#: The batting club's trailing window, in days: dates D - 30 to D - 1.
SW_LINEUP_DAYS = 30
#: xOuts is capped at a complete game.
SW_OUTS_CAP = 27
#: The priors stage 1 froze on the 2019 starts (data/starter_workload_eval.json,
#: stage1.burn_in.priors). Not a choice here: the builder refuses to build unless
#: the artifact records a stage-1 PASS with exactly these priors.
SW_PRIORS = {"k_b": 2, "k_o": 120, "k_l": 300}
#: The stage-1 artifact the builder reads its gate and priors from.
SW_ARTIFACT = ROOT / "data" / "starter_workload_eval.json"
#: The anchor floor: the prior complete season anchors the shrink only when this
#: many of its regular-season games have a complete cached feed (a full season is
#: about 2,430). Below it the anchors are None and so are the four anchored
#: columns, a stated absence, never a partial-season league rate. POLICY, a
#: data-completeness guard, not a measurement.
SW_MIN_ANCHOR_GAMES = 2000
#: One small memo keyed by game_pk, the ph_tally idiom: a night opens only the
#: feeds it has not tallied, plus any whose file changed since.
SW_TALLY_PATH = ROOT / ".cache" / "betting" / "workload_tally.json"
#: Bumped whenever the per-game rule changes, which discards every memoized tally.
SW_TALLY_VERSION = 1
SW_PITCHER_COLUMNS = ("sp_n365", "sp_budget", "sp_ppo", "sp_xouts")
SW_TEAM_COLUMNS = ("bat_ppa_l30",)

_SW_MEMO: dict = {}


def workload_from_plays(plays) -> dict:
    """One game's workload tally off its play list. Pure.

        {"sp":  {"home": [mlbam, pitches, outs] | None, "away": ...},
         "bat": {"home": [pitches seen, PA], "away": [pitches seen, PA]}}

    "home" under "sp" is the home club's starter, the first pitcher of the TOP
    half; "home" under "bat" is the home club batting, the BOTTOM half. A half
    whose first play names no pitcher has no start (None)."""
    rows = [p for p in (plays or ()) if isinstance(p, dict)]
    rows.sort(key=lambda p: (p.get("atBatIndex") is None, p.get("atBatIndex") or 0))
    first: dict = {}
    lines: dict = {"top": {}, "bottom": {}}
    bat = {"top": [0, 0], "bottom": [0, 0]}
    cur, prev_outs = None, 0
    for play in rows:
        about = play.get("about") or {}
        key = (about.get("inning"), about.get("halfInning"))
        if key != cur:
            cur, prev_outs = key, 0
        before = prev_outs
        after = (play.get("count") or {}).get("outs")
        if after is None:
            # the corpus rule: the walk's own count when the play carries none
            out_ids = {((r.get("details") or {}).get("runner") or {}).get("id")
                       for r in play.get("runners") or ()
                       if (r.get("movement") or {}).get("isOut")}
            after = before + len(out_ids)
        try:
            after = int(after)
        except (TypeError, ValueError):
            after = before
        prev_outs = after
        half = str(about.get("halfInning") or "").lower()
        if half not in ("top", "bottom"):
            continue
        n_pitch = sum(1 for e in play.get("playEvents") or () if e.get("isPitch"))
        outs = max(0, after - before)
        pid = ((play.get("matchup") or {}).get("pitcher") or {}).get("id")
        pid = int(pid) if pid is not None else None
        if half not in first:
            first[half] = pid
        if pid is not None:
            ln = lines[half].setdefault(pid, [0, 0])
            ln[0] += n_pitch
            ln[1] += outs
        bat[half][0] += n_pitch
        bat[half][1] += 1 if is_pa_event((play.get("result") or {}).get("eventType")) else 0

    def _start(half):
        pid = first.get(half)
        if pid is None or pid not in lines[half]:
            return None
        return [pid, lines[half][pid][0], lines[half][pid][1]]

    return {"sp": {"home": _start("top"), "away": _start("bottom")},
            "bat": {"home": list(bat["bottom"]), "away": list(bat["top"])}}


def game_workload_tally(game_pk, feed_dir: Path | None = None) -> dict | None:
    """One cached feed's tally, or None when the feed is missing or unreadable.

    {"complete": False} when the feed is not complete (5d and 5l vintage safety:
    gameData.status.abstractGameState "Final" and a non-empty
    liveData.plays.allPlays), which the builder excludes and counts. A complete
    feed's tally carries the feed's own last-update stamp (metaData.timeStamp)."""
    d = _feed(game_pk, feed_dir)
    if not isinstance(d, dict):
        return None
    state = ((d.get("gameData") or {}).get("status") or {}).get("abstractGameState")
    plays = ((d.get("liveData") or {}).get("plays") or {}).get("allPlays")
    if state != "Final" or not isinstance(plays, list) or not plays:
        return {"complete": False}
    t = workload_from_plays(plays)
    t["complete"] = True
    t["stamp"] = (d.get("metaData") or {}).get("timeStamp")
    return t


def _load_sw_memo(path: Path) -> dict:
    key = str(path)
    if key in _SW_MEMO:
        return _SW_MEMO[key]
    games: dict = {}
    try:
        blob = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(blob, dict) and blob.get("version") == SW_TALLY_VERSION:
            g = blob.get("games")
            games = g if isinstance(g, dict) else {}
    except Exception:                                            # noqa: BLE001
        games = {}
    _SW_MEMO[key] = games
    return games


def _save_sw_memo(path: Path, games: dict) -> str | None:
    try:
        import os
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps({
            "version": SW_TALLY_VERSION,
            "rule": ("per complete feed: each side's starter (first pitcher of the "
                     "fielding half) with his pitches and outs, each batting side's "
                     "pitches seen and PA; a pitch belongs to its play's matchup "
                     "pitcher; no score field is read"),
            "games": games}, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, p)
        return None
    except Exception as exc:                                     # noqa: BLE001
        return f"{type(exc).__name__}: {exc}"


def sw_tallies(games: list[dict], *, since: str, on_date: str,
               feed_dir: Path | None = None,
               tally_path: Path | None = None) -> tuple[list[dict], dict]:
    """(entries, counts) for every completed game dated in [since, on_date), the
    end STRICTLY BEFORE the vintage date. Memoized by game_pk and keyed on the
    feed file's size and mtime, so a re-fetched feed is tallied again. Only a
    complete feed is memoized: a missing or incomplete one is excluded, counted,
    and retried the next night."""
    import os
    path = Path(tally_path) if tally_path else SW_TALLY_PATH
    memo = _load_sw_memo(path)
    fdir = feed_dir or FEED_DIR
    entries: list[dict] = []
    c = {"n_games": 0, "n_complete": 0, "n_missing_feed": 0, "n_incomplete": 0,
         "n_new": 0}
    for g in games or []:
        d, pk = g.get("date"), g.get("game_pk")
        if not d or pk is None or d < since or d >= on_date:
            continue
        c["n_games"] += 1
        key = str(int(pk))
        try:
            st = os.stat(Path(fdir) / f"{int(pk)}.json")
            sig = [st.st_size, int(st.st_mtime_ns)]
        except OSError:
            c["n_missing_feed"] += 1
            memo.pop(key, None)
            continue
        ent = memo.get(key)
        if not (isinstance(ent, dict) and ent.get("sig") == sig):
            t = game_workload_tally(pk, feed_dir)
            if t is None:
                c["n_missing_feed"] += 1
                continue
            if not t.get("complete"):
                c["n_incomplete"] += 1
                continue
            ent = {"date": d, "home_org": _org(g.get("home_org")),
                   "away_org": _org(g.get("away_org")), "sig": sig,
                   "stamp": t.get("stamp"), "sp": t["sp"], "bat": t["bat"]}
            memo[key] = ent
            c["n_new"] += 1
        # the date and clubs come off the completed-games row of THIS call, so a
        # memo entry can never move a game across the strictly-before line
        entries.append({**ent, "date": d, "home_org": _org(g.get("home_org")),
                        "away_org": _org(g.get("away_org"))})
        c["n_complete"] += 1
    c["memo_error"] = _save_sw_memo(path, memo) if c["n_new"] else None
    return entries, c


def sw_anchor_season(on_date: str) -> int:
    """The prior complete season of a date: the season before its own, skipping
    2020, which the corpus and the stage-1 lab do not carry (a 2021 date anchors
    on 2019)."""
    s = int(on_date[:4]) - 1
    return 2019 if s == 2020 else s


def sw_anchors(entries: list[dict]) -> dict:
    """The league anchors over one season's tallies, pooled sum over sum:
    L_pgs pitches per start, L_ppo pitches per out in starts, L_opg outs per
    start, L_ppa pitches per PA. Raw counts ride along."""
    starts = sp = so = bp = bpa = 0
    for e in entries:
        for side in ("home", "away"):
            s = (e.get("sp") or {}).get(side)
            if s:
                starts += 1
                sp += int(s[1])
                so += int(s[2])
            b = (e.get("bat") or {}).get(side)
            if b:
                bp += int(b[0])
                bpa += int(b[1])
    out = {"games": len(entries), "starts": starts, "pitches": sp, "outs": so,
           "bat_pitches": bp, "bat_pa": bpa, "L_pgs": None, "L_ppo": None,
           "L_opg": None, "L_ppa": None}
    if starts and so and bpa:
        out.update(L_pgs=sp / starts, L_ppo=sp / so, L_opg=so / starts, L_ppa=bp / bpa)
    return out


def sw_stage1_gate(artifact_path: Path | None = None) -> tuple[dict | None, str]:
    """(priors, why). The priors only when the stage-1 artifact records a complete
    run with verdict PASS and burn-in priors equal to SW_PRIORS; otherwise None
    and the reason, because the section builds no column without a stage-1 PASS."""
    p = Path(artifact_path) if artifact_path else SW_ARTIFACT
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"ABSENT: no stage-1 record on disk ({p.name}); no column is built"
    except Exception as exc:                                     # noqa: BLE001
        return None, f"ABSENT: the stage-1 record is unreadable ({type(exc).__name__})"
    s1 = (doc or {}).get("stage1") if isinstance(doc, dict) else None
    if not isinstance(s1, dict) or s1.get("status") != "complete":
        return None, "ABSENT: the stage-1 record is not complete; no column is built"
    if s1.get("verdict") != "PASS":
        return None, (f"ABSENT: stage 1 recorded {s1.get('verdict')!r}, not PASS; the "
                      "section builds no column")
    pri = ((s1.get("burn_in") or {}).get("priors") or {})
    got = {k: pri.get(k) for k in SW_PRIORS}
    if got != SW_PRIORS:
        return None, (f"ABSENT: the stage-1 priors {got} differ from the frozen "
                      f"{SW_PRIORS}; no column is built")
    return dict(SW_PRIORS), "stage-1 PASS on disk"


def starter_workload_xouts_candidate(sp_budget, sp_ppo, opp_bat_ppa_l30, l_ppa):
    """The game's xOuts for a probable: min(27, budget / (ppo x r_L)), with
    r_L = the opposing club's bat_ppa_l30 / L_ppa. NOTHING SERVED CALLS THIS
    (test_schema7_builders.py, by AST and by string); it exists for the section's
    stage-2 look. None when any input is None, never a fill."""
    if None in (sp_budget, sp_ppo, opp_bat_ppa_l30, l_ppa):
        return None
    r_l = float(opp_bat_ppa_l30) / float(l_ppa)
    den = float(sp_ppo) * r_l
    if den <= 0:
        return None
    return min(float(SW_OUTS_CAP), float(sp_budget) / den)


def build_schema7_workload_columns(pitchers: dict, *, on_date: str,
                                   orgs=None, games: list[dict] | None = None,
                                   feed_dir: Path | None = None,
                                   tally_path: Path | None = None,
                                   artifact_path: Path | None = None) -> dict:
    """{column: {"values": {...}, "basis": str}} for the four pitcher columns
    (keyed by mlbam str) and `bat_ppa_l30` (keyed by org), plus "basis": the
    record block with the priors, the anchors, the windows, the feed counts and
    every raw count behind a value.

        sp_n365     n, P's starts dated D - 365 to D - 1 (0 is a real count)
        sp_budget   (pitches over those n starts + k_b L_pgs) / (n + k_b)
        sp_ppo      (pitches over those n starts + k_o L_ppo) / (outs + k_o)
        sp_xouts    min(27, sp_budget / sp_ppo), the lineup-neutral value
        bat_ppa_l30 (pitches the club's hitters saw over its games dated D - 30
                    to D - 1 + k_l L_ppa) / (their PA + k_l)

    The anchors come from the prior complete season, pooled. Without a stage-1
    PASS on disk no feed is opened and every column is a stated null; without
    the anchors (under the floor) the four anchored columns are stated nulls and
    `sp_n365` still counts."""
    priors, why = sw_stage1_gate(artifact_path)
    cols = SW_PITCHER_COLUMNS + SW_TEAM_COLUMNS
    if priors is None:
        out = {c: {"values": {}, "basis": why} for c in cols}
        out["basis"] = {"status": "not built", "reason": why}
        return out
    d0 = date.fromisoformat(on_date)
    lo_p = (d0 - timedelta(days=SW_WINDOW_DAYS)).isoformat()
    lo_c = (d0 - timedelta(days=SW_LINEUP_DAYS)).isoformat()
    a_season = sw_anchor_season(on_date)
    a_lo, a_hi = f"{a_season}-01-01", f"{a_season + 1}-01-01"
    if games is None:
        try:
            import betting_model as bm
            games = bm.completed_games(refresh=False)
        except Exception:                                        # noqa: BLE001
            games = []
    games = [g for g in (games or []) if g.get("date")]

    win, cw = sw_tallies(games, since=lo_p, on_date=on_date, feed_dir=feed_dir,
                         tally_path=tally_path)
    a_games = [g for g in games if a_lo <= g["date"] < a_hi]
    a_ent, aw = sw_tallies(a_games, since=a_lo, on_date=min(a_hi, on_date),
                           feed_dir=feed_dir, tally_path=tally_path)
    anc = sw_anchors(a_ent)
    anc["season"] = a_season
    anchored = anc["L_pgs"] is not None and anc["games"] >= SW_MIN_ANCHOR_GAMES
    if anchored:
        anc_why = None
    else:
        anc_why = (f"ABSENT: the prior complete season {a_season} has {anc['games']} "
                   f"complete cached feed(s), under the {SW_MIN_ANCHOR_GAMES}-game "
                   f"anchor floor; the anchored columns are null, never a partial "
                   f"league rate")

    # the starter's window: his starts dated D - 365 to D - 1
    p_raw: dict = {}
    for e in win:
        for side in ("home", "away"):
            s = (e.get("sp") or {}).get(side)
            if s:
                r = p_raw.setdefault(str(int(s[0])), [0, 0, 0])
                r[0] += 1
                r[1] += int(s[1])
                r[2] += int(s[2])
    # the batting club's window: dates D - 30 to D - 1
    c_raw: dict = {}
    c_stamp: dict = {}
    for e in win:
        if e["date"] < lo_c:
            continue
        for side in ("home", "away"):
            org = e.get(f"{side}_org")
            b = (e.get("bat") or {}).get(side)
            if not org or not b:
                continue
            r = c_raw.setdefault(org, [0, 0, 0])
            r[0] += int(b[0])
            r[1] += int(b[1])
            r[2] += 1
            st = e.get("stamp")
            if st and (c_stamp.get(org) is None or str(st) > str(c_stamp[org])):
                c_stamp[org] = st

    k_b, k_o, k_l = priors["k_b"], priors["k_o"], priors["k_l"]
    vals = {c: {} for c in cols}
    raw_p: dict = {}
    for mid in pitchers or {}:
        key = str(mid)
        n, pit, outs = p_raw.get(key, [0, 0, 0])
        raw_p[key] = [n, pit, outs]
        vals["sp_n365"][key] = n
        if anchored:
            b = (pit + k_b * anc["L_pgs"]) / (n + k_b)
            q = (pit + k_o * anc["L_ppo"]) / (outs + k_o)
            vals["sp_budget"][key] = round(b, 4)
            vals["sp_ppo"][key] = round(q, 5)
            vals["sp_xouts"][key] = round(min(float(SW_OUTS_CAP), b / q), 4)
    raw_c: dict = {}
    for org in sorted({o for o in (orgs or ()) if o} | set(c_raw)):
        pit, pa, ng = c_raw.get(org, [0, 0, 0])
        raw_c[org] = [pit, pa, ng]
        if anchored:
            vals["bat_ppa_l30"][org] = round((pit + k_l * anc["L_ppa"]) / (pa + k_l), 5)

    span_p = (f"{cw['n_complete']} complete feed(s) of {cw['n_games']} completed "
              f"game(s) dated {lo_p} to the day before {on_date} "
              f"({cw['n_missing_feed']} without a cached feed and "
              f"{cw['n_incomplete']} incomplete, excluded)")
    fmt = lambda x: "n/a" if x is None else f"{x:.4f}"       # noqa: E731
    a_txt = (f"anchors {a_season} pooled: L_pgs {fmt(anc['L_pgs'])}, L_ppo "
             f"{fmt(anc['L_ppo'])}, L_ppa {fmt(anc['L_ppa'])} over {anc['games']} "
             f"game(s), {anc['starts']} start(s)")
    pri_txt = f"priors frozen by stage 1: k_b {k_b}, k_o {k_o}, k_l {k_l}"
    basis = {
        "sp_n365": (f"betting_usage: the pitcher's starts (first pitcher of a fielding "
                    f"half) over {span_p}; 0 is a real count"),
        "sp_budget": (anc_why or f"(window pitches + k_b L_pgs) / (n + k_b); {span_p}; "
                                 f"{a_txt}; {pri_txt}"),
        "sp_ppo": (anc_why or f"(window pitches + k_o L_ppo) / (window outs + k_o); "
                              f"{span_p}; {a_txt}; {pri_txt}"),
        "sp_xouts": (anc_why or f"min({SW_OUTS_CAP}, sp_budget / sp_ppo), lineup "
                                f"neutral; {span_p}; {a_txt}; {pri_txt}"),
        "bat_ppa_l30": (anc_why or f"(pitches seen + k_l L_ppa) / (PA + k_l) over the "
                                   f"club's games dated {lo_c} to the day before "
                                   f"{on_date}; {a_txt}; {pri_txt}"),
    }
    out = {c: {"values": vals[c], "basis": basis[c]} for c in cols}
    stamps = [str(e["stamp"]) for e in win if e.get("stamp")]
    out["basis"] = {
        "status": "built",
        "rule": "the section 'Starter workload: expected outs and pitches per start'",
        "priors": dict(priors),
        "anchors": anc,
        "anchor_floor_games": SW_MIN_ANCHOR_GAMES,
        "anchored": anchored,
        "window_pitcher": [lo_p, on_date],
        "window_club": [lo_c, on_date],
        "feeds_window": cw,
        "feeds_anchor": aw,
        "latest_feed_stamp": max(stamps) if stamps else None,
        "club_latest_feed_stamp": c_stamp,
        "pitchers_raw": {"fields": ["starts", "pitches", "outs"], "values": raw_p},
        "clubs_raw": {"fields": ["pitches_seen", "pa", "games"], "values": raw_c},
    }
    return out


# ---------------------------------------------------------------------------
# catcher framing and times through the order
# ---------------------------------------------------------------------------
#: Horizontal bin width for the called-strike expectation, in feet. The plate
#: half-width is 0.7083 ft and a ball's radius is about 0.12 ft, so the decision
#: boundary sits near 0.83 ft and a 0.1 ft bin resolves it without splitting the
#: sample too thin.
FRAME_X_BIN = 0.1

#: Vertical bin width, in FRACTIONS OF THE BATTER'S OWN ZONE. The feed carries
#: strikeZoneTop and strikeZoneBottom per plate appearance, so height is
#: normalized to (pZ - bottom) / (top - bottom) and a tall batter and a short one
#: land in the same bin. Binning raw feet would make the expectation a model of
#: batter height.
FRAME_Z_BIN = 0.1

#: A bin needs this many league pitches before it can express an expectation.
#: Below it the pitch is dropped from BOTH the actual and the expected side, so
#: a thin bin cannot manufacture a difference.
FRAME_MIN_BIN = 40

#: A club needs this many scored pitches in the window before a rate is
#: published. Below it the column is null, never a noisy number.
FRAME_MIN_TEAM_PITCHES = 200

#: Trailing window, in days, for the team framing rate and the TTO exposure.
FRAME_WINDOW_DAYS = 30


def _taken_pitches(game_pk, feed_dir=None):
    """Every TAKEN pitch in one game: {bin, is_strike, catching}.

    Taken means called strike or ball. A swing is not an umpire decision and
    carries no framing information, so it is excluded rather than counted.

    THE CATCHING SIDE IS READ OFF THE HALF INNING, not off a pitcher-to-team
    map. In the top half the away team bats, so the home team is catching. That
    is exact, needs no roster join, and is immune to the mid-inning
    substitutions that make per-catcher attribution hard.
    """
    d = _feed(game_pk, feed_dir)
    if not d:
        return []
    out = []
    for p in ((d.get("liveData") or {}).get("plays") or {}).get("allPlays") or []:
        half = str(((p.get("about") or {}).get("halfInning") or "")).lower()
        if half not in ("top", "bottom"):
            continue
        catching = "home" if half == "top" else "away"
        side = ((p.get("matchup") or {}).get("batSide") or {}).get("code") or "?"
        for e in p.get("playEvents") or []:
            if not e.get("isPitch"):
                continue
            code = ((e.get("details") or {}).get("call") or {}).get("code")
            if code not in ("C", "B"):
                continue
            pd = e.get("pitchData") or {}
            co = pd.get("coordinates") or {}
            px, pz = co.get("pX"), co.get("pZ")
            top, bot = pd.get("strikeZoneTop"), pd.get("strikeZoneBottom")
            if px is None or pz is None or top is None or bot is None:
                continue
            try:
                top, bot = float(top), float(bot)
                if top <= bot:
                    continue
                zn = (float(pz) - bot) / (top - bot)
                key = (side, round(abs(float(px)) / FRAME_X_BIN), round(zn / FRAME_Z_BIN))
            except (TypeError, ValueError, ZeroDivisionError):
                continue
            out.append({"bin": key, "is_strike": code == "C", "catching": catching})
    return out


#: One framing scan per (date, window) per process. reduce_current is called
#: several times in a suite run and by more than one pipeline step, and the scan
#: is 408 games of play events; without this each caller pays it again. Keyed on
#: the arguments that change the answer, so a different date still rescans.
_FRAME_CACHE: dict = {}


def framing_rates(games, on_date, *, feed_dir=None,
                  window_days=FRAME_WINDOW_DAYS):
    """{"values": {org: called strikes above expected per 100 taken pitches},
    "basis": str}.

    TWO PASSES OVER THE SAME WINDOW. The first builds the league expectation per
    location bin; the second scores each club against it. The expectation is the
    league's OWN rate in that bin over the SAME window, so it is a within-window
    contrast that carries no constant from anywhere else, and a club cannot beat
    it by playing in a period when everybody did.

    THE UNITS ARE A RATE, ON PURPOSE. Converting to runs needs a
    runs-per-called-strike constant that nothing in this repo measures, and
    inventing one would put a fabricated number on a scale that looks measured.
    `_assemble_team_inputs` standardizes every column anyway, so a rate reaches
    the model in the same shape a run figure would.
    """
    from datetime import date as _date
    ck = (on_date, window_days, str(feed_dir), len(games or []))
    if ck in _FRAME_CACHE:
        return _FRAME_CACHE[ck]
    lo = (_date.fromisoformat(on_date) - timedelta(days=window_days)).isoformat()
    win = [g for g in (games or []) if g.get("date") and lo <= g["date"] < on_date]
    per_game = []
    league = {}
    for g in win:
        rows = _taken_pitches(g.get("game_pk"), feed_dir)
        if not rows:
            continue
        per_game.append((g, rows))
        for r in rows:
            b = league.setdefault(r["bin"], [0, 0])
            b[0] += 1
            b[1] += 1 if r["is_strike"] else 0
    exp = {k: v[1] / v[0] for k, v in league.items() if v[0] >= FRAME_MIN_BIN}

    tot = {}
    n_used = n_dropped = 0
    for g, rows in per_game:
        sides = {"home": _org(g.get("home_org")), "away": _org(g.get("away_org"))}
        for r in rows:
            e = exp.get(r["bin"])
            if e is None:
                n_dropped += 1
                continue                    # thin bin: dropped from BOTH sides
            org = sides.get(r["catching"])
            if not org:
                continue
            t = tot.setdefault(org, [0, 0.0])
            t[0] += 1
            t[1] += (1.0 if r["is_strike"] else 0.0) - e
            n_used += 1
    values = {o: round(100.0 * v[1] / v[0], 3)
              for o, v in tot.items() if v[0] >= FRAME_MIN_TEAM_PITCHES}
    basis = (f"called strikes above the league's own rate in the same location bin, "
             f"per 100 taken pitches, over {len(per_game)} game(s) from {lo} to the "
             f"day before {on_date}. {n_used} pitch(es) scored, {n_dropped} dropped "
             f"for sitting in a bin under {FRAME_MIN_BIN} league pitches. Height is "
             f"normalized to each batter's own zone and bins are split by batter "
             f"side. Swings are excluded: a swing is not an umpire decision")
    out = {"values": values, "basis": basis}
    _FRAME_CACHE[ck] = out
    return out


_TTO_CACHE: dict = {}


def tto_exposure(games, on_date, *, feed_dir=None,
                 window_days=FRAME_WINDOW_DAYS):
    """{"values": {mlbam_str: mean batters faced for the 3rd+ time per START},
    "basis": str}.

    EXPOSURE, NOT PENALTY. How far a starter gets into the order a third time is
    well measured from his own recent starts. How much WORSE he is on that third
    pass is a per-pitcher split with a season of noise in it, and pricing one
    would need shrinkage this has not earned. The candidate is whether exposure
    carries information the innings share does not; the per-pitcher decline is a
    separate, harder question that is not asked here.

    Only each side's FIRST pitcher counts. A reliever's third time through is a
    different event with a different cause.
    """
    from datetime import date as _date
    ck = (on_date, window_days, str(feed_dir), len(games or []))
    if ck in _TTO_CACHE:
        return _TTO_CACHE[ck]
    lo = (_date.fromisoformat(on_date) - timedelta(days=window_days)).isoformat()
    starts = {}
    n_games = 0
    for g in (games or []):
        d = g.get("date")
        if not d or not (lo <= d < on_date):
            continue
        fd = _feed(g.get("game_pk"), feed_dir)
        if not fd:
            continue
        n_games += 1
        order, faced, first = {}, {}, {}
        for p in ((fd.get("liveData") or {}).get("plays") or {}).get("allPlays") or []:
            m = p.get("matchup") or {}
            pid = (m.get("pitcher") or {}).get("id")
            bid = (m.get("batter") or {}).get("id")
            half = str(((p.get("about") or {}).get("halfInning") or "")).lower()
            if not pid or not bid or half not in ("top", "bottom"):
                continue
            first.setdefault(half, pid)
            if pid != first[half]:
                continue                          # not the starter for this side
            faced.setdefault(pid, 0)
            k = (pid, bid)
            order[k] = order.get(k, 0) + 1
            if order[k] >= 3:
                faced[pid] += 1
        for pid, n in faced.items():
            starts.setdefault(pid, []).append(n)
    values = {str(pid): round(sum(v) / len(v), 3)
              for pid, v in starts.items() if len(v) >= 2}
    basis = (f"mean batters faced for the 3rd+ time per start, over {n_games} game(s) "
             f"from {lo} to the day before {on_date}, starters only, minimum 2 starts "
             f"in the window. EXPOSURE only: the per-pitcher decline on that third "
             f"pass is a separate candidate this does not price")
    out = {"values": values, "basis": basis}
    _TTO_CACHE[ck] = out
    return out


# ---------------------------------------------------------------------------
# schema 5: the pinch-hit and relief-hand tally (docs/diamond-betting.md 5f)
# ---------------------------------------------------------------------------
# Two team columns off the same cached feeds the schema-4 builders read, and
# nothing else: `ph_share` (the club's pinch-hit PA against relievers over its
# PA against relievers) and `pen_lhp_share` (relief PA its left-handers threw
# over all relief PA it threw), season to date through the day BEFORE the
# vintage date, each shrunk toward the league rate.
#
# WHAT A TALLY READS, AND WHAT IT NEVER READS. Per plate appearance: the half
# inning, the batter and pitcher ids, the pitcher's hand, the play's
# `result.eventType` (ONLY to tell a completed plate appearance from a non-PA
# terminal event such as a caught stealing), and the substitution actions in
# `playEvents`. The score fields that sit beside `eventType` in the same block
# are never read, and the completed-games rows are read for game_pk, date and
# the two orgs only. Section 5c rule 1: nothing here may be related to a result.

#: Pseudo-counts, in relief PA, for the two shrinks. The MEDIAN split-half
#: pseudo-count k = n_half * (1 - r) / r over 2022-2025, derived with NO 2026
#: data (the pinch-hit design lane, 2026-09-11; per-season k 186.9, 286.6,
#: 585.9, 309.4 for the pinch-hit share and 84.7, 160.2, 232.9, 123.6 for the
#: bullpen hand share). Frozen by section 5f: tuning either against outcomes
#: before the look is fitting the feature to the eval window.
K_PHI = 298
K_PEN = 142

#: Terminal events that end a play without a plate appearance, by eventType
#: prefix, plus the exact type "error". The same list the corpus measurement
#: behind section 5f used, so the feed tally and the corpus count one thing.
NON_PA_PREFIX = ("caught_stealing", "pickoff", "stolen_base", "wild_pitch",
                 "passed_ball", "balk", "other_advance", "game_advisory",
                 "runner_double_play", "other_out", "defensive_indiff",
                 "forced_balk")

#: StatsAPI's substitution code for a pinch HITTER. Code "12" is the pinch
#: RUNNER, who takes no plate appearance and is not counted.
PH_POSITION_CODE = "11"

#: One small memo keyed by game_pk, so a nightly run opens only the feeds it has
#: not tallied (about fifteen), never the whole season. Gitignored .cache, the
#: same box-persistent state the vintage store lives in.
PH_TALLY_PATH = ROOT / ".cache" / "betting" / "ph_tally.json"
#: Bumped whenever the per-game rule changes, which discards every memoized
#: tally rather than mixing two rules in one season's sums.
PH_TALLY_VERSION = 1

_PH_MEMO: dict = {}


def is_pa_event(event_type) -> bool:
    """True when a play's eventType closes a plate appearance. A missing type
    cannot be classified and is not counted."""
    et = str(event_type or "")
    if not et or et == "error":
        return False
    return not et.startswith(NON_PA_PREFIX)


def _zero_side() -> dict:
    return {"rel_pa": 0, "ph_pa": 0, "ph_rel_pa": 0,
            "pen_pa": 0, "pen_hand_pa": 0, "pen_lhp_pa": 0, "n_ph_actions": 0}


def tally_game_feed(feed: dict | None) -> dict | None:
    """{"home": {...}, "away": {...}} counts for one completed feed, or None.

    Per side, as the BATTING club: `rel_pa` plate appearances against the other
    side's relievers, `ph_pa` pinch-hit plate appearances, `ph_rel_pa` those
    against a reliever, `n_ph_actions` code-11 announcements. As the FIELDING
    club: `pen_pa` relief plate appearances its relievers threw, `pen_hand_pa`
    those with a readable pitch hand, `pen_lhp_pa` those thrown left-handed.

    A reliever is any pitcher other than the first one that side used, read off
    the half inning (top: the home club is pitching). A pinch-hit PA is the FIRST
    plate appearance, at or after his announcement, of a player introduced by a
    code-11 action; so a pinch hitter who is himself hit for before a pitch has
    none, and the PA his replacement takes counts once."""
    if not isinstance(feed, dict):
        return None
    plays = ((feed.get("liveData") or {}).get("plays") or {}).get("allPlays")
    if not isinstance(plays, list):
        return None
    out = {"home": _zero_side(), "away": _zero_side()}
    first: dict = {}
    # Player ids are unique across both clubs, so one pending set is exact and
    # survives an announcement logged on the previous play.
    pending: set = set()
    for p in plays:
        if not isinstance(p, dict):
            continue
        half = str(((p.get("about") or {}).get("halfInning") or "")).lower()
        if half not in ("top", "bottom"):
            continue
        bat = "away" if half == "top" else "home"
        fld = "home" if half == "top" else "away"
        m = p.get("matchup") or {}
        pid = (m.get("pitcher") or {}).get("id")
        bid = (m.get("batter") or {}).get("id")
        if pid is not None:
            first.setdefault(half, pid)
        for e in p.get("playEvents") or []:
            if not isinstance(e, dict) or e.get("type") != "action":
                continue
            if not e.get("isSubstitution"):
                continue
            if (e.get("details") or {}).get("eventType") != "offensive_substitution":
                continue
            if str((e.get("position") or {}).get("code") or "") != PH_POSITION_CODE:
                continue
            ph = (e.get("player") or {}).get("id")
            if ph is not None:
                pending.add(ph)
                out[bat]["n_ph_actions"] += 1
        if pid is None or bid is None:
            continue
        if not is_pa_event((p.get("result") or {}).get("eventType")):
            continue
        is_rel = pid != first.get(half)
        if is_rel:
            out[bat]["rel_pa"] += 1
            out[fld]["pen_pa"] += 1
            hand = ((m.get("pitchHand") or {}).get("code") or "")
            if hand in ("L", "R"):
                out[fld]["pen_hand_pa"] += 1
                if hand == "L":
                    out[fld]["pen_lhp_pa"] += 1
        if bid in pending:
            pending.discard(bid)
            out[bat]["ph_pa"] += 1
            if is_rel:
                out[bat]["ph_rel_pa"] += 1
    return out


def game_ph_tally(game_pk, feed_dir: Path | None = None) -> dict | None:
    """tally_game_feed over one cached feed; None when the feed is absent."""
    return tally_game_feed(_feed(game_pk, feed_dir))


def _load_ph_memo(path: Path) -> dict:
    """{game_pk as str: entry} off the memo file, in-process cached per path. A
    missing, unreadable or other-version file is an empty memo, never an error."""
    key = str(path)
    if key in _PH_MEMO:
        return _PH_MEMO[key]
    games: dict = {}
    try:
        blob = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(blob, dict) and blob.get("version") == PH_TALLY_VERSION:
            g = blob.get("games")
            games = g if isinstance(g, dict) else {}
    except Exception:                                            # noqa: BLE001
        games = {}
    _PH_MEMO[key] = games
    return games


def _save_ph_memo(path: Path, games: dict) -> str | None:
    """Write the memo atomically; the error text on failure, which the basis
    carries, and never a raise: the tallies are already in hand."""
    try:
        import os
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps({
            "version": PH_TALLY_VERSION,
            "rule": ("per completed game: relief PA, pinch-hit PA (first PA of a "
                     "code-11 player), relief PA by pitch hand; non-PA terminal "
                     "events excluded; no score field is read"),
            "games": games}, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, p)
        return None
    except Exception as exc:                                     # noqa: BLE001
        return f"{type(exc).__name__}: {exc}"


def ph_tallies(games: list[dict], on_date: str, *, feed_dir: Path | None = None,
               tally_path: Path | None = None) -> tuple[list[dict], dict]:
    """(entries, diagnostics) for every completed game of on_date's season dated
    STRICTLY BEFORE on_date. Memoized by game_pk: only an untallied game opens
    its feed, and a game whose feed is absent is retried next night rather than
    memoized as empty."""
    path = Path(tally_path) if tally_path else PH_TALLY_PATH
    memo = _load_ph_memo(path)
    season = on_date[:4]
    entries, n_new, n_missing = [], 0, 0
    for g in games or []:
        d = g.get("date")
        pk = g.get("game_pk")
        if not d or pk is None or d >= on_date or d[:4] != season:
            continue
        key = str(int(pk))
        ent = memo.get(key)
        if not isinstance(ent, dict):
            t = game_ph_tally(pk, feed_dir)
            if t is None:
                n_missing += 1
                continue
            ent = {"date": d, "home_org": g.get("home_org"),
                   "away_org": g.get("away_org"), "t": t}
            memo[key] = ent
            n_new += 1
        entries.append(ent)
    save_err = _save_ph_memo(path, memo) if n_new else None
    return entries, {"n_games": len(entries), "n_new": n_new,
                     "n_missing_feed": n_missing, "memo_error": save_err}


def ph_columns_from_tallies(entries: list[dict]) -> tuple[dict, dict]:
    """({"ph_share": {org: v}, "pen_lhp_share": {org: v}}, league rates and
    counts). Pure. Shrunk toward the league rate over the same entries:

        ph_share      = (ph_rel_pa + K_PHI * league)  / (rel_pa + K_PHI)
        pen_lhp_share = (pen_lhp_pa + K_PEN * league) / (pen_hand_pa + K_PEN)

    A club is populated when it has any relief PA on file on that side."""
    bat: dict = {}
    pen: dict = {}
    for ent in entries or []:
        t = ent.get("t") or {}
        for side in ("home", "away"):
            org = _org(ent.get(f"{side}_org"))
            s = t.get(side) or {}
            if not org:
                continue
            b = bat.setdefault(org, [0, 0])
            b[0] += int(s.get("ph_rel_pa") or 0)
            b[1] += int(s.get("rel_pa") or 0)
            q = pen.setdefault(org, [0, 0])
            q[0] += int(s.get("pen_lhp_pa") or 0)
            q[1] += int(s.get("pen_hand_pa") or 0)
    n_ph, n_rel = sum(v[0] for v in bat.values()), sum(v[1] for v in bat.values())
    n_lhp, n_hand = sum(v[0] for v in pen.values()), sum(v[1] for v in pen.values())
    lg_phi = (n_ph / n_rel) if n_rel else None
    lg_lhp = (n_lhp / n_hand) if n_hand else None
    ph_share = {o: round((v[0] + K_PHI * lg_phi) / (v[1] + K_PHI), 5)
                for o, v in bat.items() if v[1] > 0 and lg_phi is not None}
    lhp_share = {o: round((v[0] + K_PEN * lg_lhp) / (v[1] + K_PEN), 5)
                 for o, v in pen.items() if v[1] > 0 and lg_lhp is not None}
    return ({"ph_share": ph_share, "pen_lhp_share": lhp_share},
            {"league_phi": lg_phi, "league_lhp": lg_lhp, "n_ph_rel_pa": n_ph,
             "n_rel_pa": n_rel, "n_lhp_pa": n_lhp, "n_hand_pa": n_hand})


def build_schema5_team_columns(*, on_date: str, games: list[dict] | None = None,
                               feed_dir: Path | None = None,
                               tally_path: Path | None = None) -> dict:
    """{column: {"values": {org: v}, "basis": str}} for `ph_share` and
    `pen_lhp_share`. The game list is betting_model.completed_games(season),
    the same index schema 4 reads; every input is injectable for a test."""
    if games is None:
        try:
            import betting_model as bm
            games = bm.completed_games(season=on_date[:4], refresh=False)
        except Exception:                                        # noqa: BLE001
            games = []
    entries, diag = ph_tallies(games, on_date, feed_dir=feed_dir, tally_path=tally_path)
    vals, lg = ph_columns_from_tallies(entries)
    span = (f"{diag['n_games']} game(s) tallied from the season's completed games "
            f"dated before {on_date} ({diag['n_new']} newly opened, "
            f"{diag['n_missing_feed']} without a cached feed")
    if diag.get("memo_error"):
        span += f"; memo not persisted: {diag['memo_error']}"
    span += ")"
    if not entries:
        why = f"ABSENT: no completed game of the season before {on_date} has a tally; {span}"
        return {c: {"values": {}, "basis": why} for c in ("ph_share", "pen_lhp_share")}
    fmt = lambda x: "n/a" if x is None else f"{x:.5f}"     # noqa: E731
    return {
        "ph_share": {"values": vals["ph_share"], "basis": (
            f"pinch-hit PA against relievers over PA against relievers, {span}; "
            f"league rate {fmt(lg['league_phi'])} ({lg['n_ph_rel_pa']} of "
            f"{lg['n_rel_pa']}); shrunk by K_PHI {K_PHI}; a pinch-hit PA is the "
            f"first PA of a code-{PH_POSITION_CODE} player; {len(vals['ph_share'])} clubs")},
        "pen_lhp_share": {"values": vals["pen_lhp_share"], "basis": (
            f"relief PA thrown left-handed over relief PA with a readable hand, "
            f"{span}; league rate {fmt(lg['league_lhp'])} ({lg['n_lhp_pa']} of "
            f"{lg['n_hand_pa']}); shrunk by K_PEN {K_PEN}; "
            f"{len(vals['pen_lhp_share'])} clubs")},
    }


_PH_LIVE_CACHE: dict = {}


def live_ph_columns(*, on_date: str | None = None,
                    tally_path: Path | None = None) -> dict:
    """{org: {"ph_share", "pen_lhp_share"}} for the LIVE read, off the memo ALONE:
    games of on_date's season dated before it that the nightly capture already
    tallied. It never opens a feed, so a board build costs one small file read;
    a club the memo cannot place reads None, which is a stated absence."""
    d = on_date or date.today().isoformat()
    path = Path(tally_path) if tally_path else PH_TALLY_PATH
    try:
        mt = path.stat().st_mtime
    except OSError:
        return {}
    ck = (str(path), mt, d)
    if ck in _PH_LIVE_CACHE:
        return _PH_LIVE_CACHE[ck]
    _PH_MEMO.pop(str(path), None)          # the file moved; re-read it
    memo = _load_ph_memo(path)
    entries = [e for e in memo.values() if isinstance(e, dict)
               and str(e.get("date") or "")[:4] == d[:4] and str(e.get("date") or "") < d]
    vals, _ = ph_columns_from_tallies(entries)
    out: dict = {}
    for col, per in vals.items():
        for org, v in per.items():
            out.setdefault(org, {"ph_share": None, "pen_lhp_share": None})[col] = v
    _PH_LIVE_CACHE.clear()
    _PH_LIVE_CACHE[ck] = out
    return out
