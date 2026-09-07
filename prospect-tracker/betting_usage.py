"""Schema-4 dark-capture builders: bullpen availability, schedule rest, weather.

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
    return {c: {"values": values[c], "basis": basis[c]} for c in cols}


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
