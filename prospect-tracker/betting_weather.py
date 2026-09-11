# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""betting_weather.py - pregame FORECAST weather capture for /betting/ (DARK).

Pre-registered in docs/diamond-betting.md section 5h BEFORE this file existed
and before any captured number was related to any game outcome. Nothing served
reads anything here. The capture ships OFF (`FORECAST_CAPTURE_ENABLED = False`)
because it is a new external dependency, and a new dependency is an owner
decision (section 5h lists it).

THE OWNER ASK (2026-09-11): make the module weather and ballpark aware,
especially for overs/unders and player props.

WHY A FORECAST AND NOT THE OTHER TWO WEATHER SOURCES THE MODULE ALREADY HAS.

  * `gameData.weather` in a game feed is the weather AT THE GAME. It is not
    known before first pitch, so a price built on it reads the future (5d).
    It stays a contaminated screen that can only disqualify.
  * `wx_temp_climo` / `wx_wind_out_climo` (schema 4, betting_usage) are a
    trailing 30-day venue CLIMATOLOGY. Servable, but a climatology cannot see
    tonight's cold front, which is the thing the owner is asking about.
  * A FORECAST captured before first pitch is the only pregame signal that can
    see tonight's weather without reading the future. The whole safety property
    is the capture timestamp: a row may inform a game only when it was captured
    at least MIN_LEAD_HOURS before that game's first pitch, and the reader
    enforces it on the row, never on a file name.

WHAT IS CAPTURED, per scheduled game: the forecast at the venue's coordinates
over the first GAME_WINDOW_HOURS hours from first pitch (temperature, wind
speed and direction, humidity, pressure, precipitation probability), the wind
resolved into a signed OUT-TO-CENTRE component using the venue's own
home-plate-to-centre-field bearing, and the roof type. Venue coordinates,
bearing (`azimuthAngle`) and roof type all come from the cached StatsAPI feeds
already on disk (`gameData.venue.location` / `fieldInfo`), so the only new
network call is the forecast itself.

A CLOSED ROOF ZEROES THE TERM. Dome venues are not fetched at all. Retractable
venues ARE fetched (a secondary arm may read them) but carry
`weather_applies = False`, because the roof decision is not published before
first pitch in any source this repo holds, and guessing it from the forecast
would be a model of a groundskeeper, not of weather.

THE STORE mirrors the odds snapshots: `.cache/weather_forecasts/<UTC date>-
<HHMM>.json`, one immutable file per capture, never overwritten (a second
capture in the same minute raises FileExistsError). Under .cache/ for the
reason the vintage store is: the nightly `git checkout -- .` would revert a
tracked file.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("betting_weather")

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
FEED_DIR = ROOT / ".cache" / "game_feeds"
FORECAST_DIR = ROOT / ".cache" / "weather_forecasts"

# ---------------------------------------------------------------------------
# the arming flag (OWNER DECISION, docs/diamond-betting.md 5h)
# ---------------------------------------------------------------------------
#: Whether the nightly step makes the forecast call at all. FALSE, and the
#: reason is that it is a new external dependency with a licence question
#: attached (section 5h, "The owner decisions"), not that anything failed.
#:
#: WHAT FLIPPING IT CHANGES, exactly: run_monthly step 9e-pre-wx starts making
#: ONE batched forecast request a night (Open-Meteo) or two requests per
#: open-air venue (NWS) and writes one immutable snapshot under
#: .cache/weather_forecasts/. The 5h clock starts on the first such night.
#: WHAT IT DOES NOT CHANGE: no served price, no fair total, no edge, no side
#: marked value, neither Model Watch slot (the Pick of the Day and the longshot
#: are byte-identical), no record row, no shadow or calibration ledger row, no
#: vintage record. Nothing served imports this module and
#: test_betting_weather.py pins that.
#:
#: TO FLIP IT, in ONE commit: set this True, set FORECAST_SOURCE to the source
#: the owner chose, and, for Open-Meteo on a subscription site, put the
#: commercial key in the environment variable OPEN_METEO_KEY_ENV names (the
#: free endpoint is non-commercial only). Update the pinned test and the 5h
#: "clock" paragraph with the first capture date.
FORECAST_CAPTURE_ENABLED = False

#: Which source. None until the owner picks one, so that flipping the flag
#: alone cannot silently choose a licence. See SOURCES.
FORECAST_SOURCE: str | None = None

SOURCES = {
    "open-meteo": {
        "endpoint": "https://api.open-meteo.com/v1/forecast",
        "commercial_endpoint": "https://customer-api.open-meteo.com/v1/forecast",
        "key": "none on the free endpoint; `apikey` on the commercial one",
        "licence": ("free endpoint is NON-COMMERCIAL ONLY per open-meteo.com/en/terms, "
                    "and a site with subscriptions or ads is named there as commercial; "
                    "data under CC BY 4.0, attribution required"),
        "calls_per_night": "1 (all venues batched as comma-separated coordinates)",
        "archive": ("Previous Runs API (previous-runs-api.open-meteo.com), "
                    "`<var>_previous_day1` = the value forecast 24h before valid "
                    "time, archived from January 2024 for most models"),
    },
    "nws": {
        "endpoint": "https://api.weather.gov",
        "key": "none; a User-Agent with contact details is required",
        "licence": "open data, free to use for any purpose (weather.gov API docs)",
        "calls_per_night": "2 per open-air or retractable US venue (points, hourly)",
        "archive": "none served by the API; no backfill arm is possible",
        "coverage_gap": "US only: Rogers Centre (TOR, retractable) has no forecast",
    },
}

#: Environment variable carrying an Open-Meteo COMMERCIAL key. Read from the
#: environment only, never written to an artifact or a log.
OPEN_METEO_KEY_ENV = "EEPHUS_OPEN_METEO_KEY"
#: Environment variable carrying the NWS User-Agent string (contact details).
NWS_USER_AGENT_ENV = "EEPHUS_NWS_USER_AGENT"

# ---------------------------------------------------------------------------
# policy constants (named as policy, not measurement)
# ---------------------------------------------------------------------------
#: A forecast row may inform a game only if it was captured at least this many
#: hours before first pitch. POLICY: one hour clears the latest a price could be
#: published for the game and keeps a capture taken minutes before first pitch
#: (which is nearly an observation) out of the candidate.
MIN_LEAD_HOURS = 1.0

#: Hours of forecast averaged from the first-pitch hour. POLICY: a 2026 game
#: runs a little under three hours under the pitch clock.
GAME_WINDOW_HOURS = 3

#: Calendar days of schedule captured per night (today and tomorrow). Tomorrow's
#: day games start before the next nightly run, so without the day-ahead
#: capture they would never carry a forecast.
HORIZON_DAYS = 2

SNAPSHOT_SCHEMA = 1

OPEN_METEO_HOURLY = ("temperature_2m", "relative_humidity_2m", "surface_pressure",
                     "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
                     "precipitation_probability")

#: Roof type (StatsAPI `fieldInfo.roofType`, lower-cased) -> does weather reach
#: the ball. Unknown is False: an unstated roof is not an open one.
ROOF_WEATHER_APPLIES = {"open": True, "retractable": False, "dome": False}

# ---------------------------------------------------------------------------
# the physics prior for the dark props model (LITERATURE, never fitted here)
# ---------------------------------------------------------------------------
#: Feet of fly-ball carry per degree F, on a home-run trajectory (103 mph, 28
#: degrees), linear over 50-100 F. Alan Nathan, "Effect of Temperature on Home
#: Run Production", baseball.physics.illinois.edu (slope 0.33143 ft/deg).
HR_FT_PER_DEG_F = 0.33
#: Feet of carry per mph of wind blowing straight out, and straight in, on a
#: 100 mph / 29 degree / 2500 rpm fly ball whose still-air distance is 397 ft:
#: 5 mph out -> 413 ft, 5 mph in -> 380 ft. Nathan, "The Carry of a Fly Ball",
#: baseball.physics.illinois.edu/carry.html.
HR_FT_PER_MPH_OUT = 3.2
HR_FT_PER_MPH_IN = 3.4
#: Home runs per foot of carry: shifting Statcast 2015-2017 fly-ball distances
#: beyond ~400 ft by +8.5 ft raised home runs by about 25% (Nathan, same
#: temperature note). Applied log-linearly so a multiplier can never go
#: negative. Cross-check: 0.33 ft/F times this is 0.87% per F, against
#: Nathan's own "about 1%" and Callahan and Mankin (BAMS 2023), about 2% per
#: degree C of daily high, i.e. about 1.1% per F.
HR_SHIFT_FT = 8.5
HR_SHIFT_GAIN = 0.25
HR_LOG_ELASTICITY_PER_FT = math.log(1.0 + HR_SHIFT_GAIN) / HR_SHIFT_FT
#: The elasticity above is LOCAL to a shift of about HR_SHIFT_FT. A prior whose
#: carry change exceeds it is an extrapolation and says so on the result.
PRIOR_LOCAL_RANGE_FT = HR_SHIFT_FT
#: Fraction of the FORECAST 10 m out-to-centre wind that reaches the field.
#: NONE, deliberately: nothing measures it yet, and a wind term with an
#: invented pass-through would be a fabricated number on a scale that looks
#: measured. Section 5h pre-registers the forecast-fidelity check that
#: measures it (captured forecast against the feed's reported game wind, a
#: weather-against-weather comparison that reads no score). Until then the
#: prior's wind term is OFF and the result says so.
WIND_PASS_THROUGH: float | None = None

_COMPASS = {name: i * 22.5 for i, name in enumerate(
    ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
     "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"))}
_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)")


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _utc(ts) -> datetime | None:
    """ISO-8601 -> aware UTC datetime, or None. Accepts 'Z' and offsets."""
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def _hour_key(d: datetime) -> str:
    """The UTC hour a series is keyed by: 'YYYY-MM-DDTHH:00'."""
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00")


def _org(name):
    try:
        import betting_usage
        return betting_usage._org(name)
    except Exception:                                            # noqa: BLE001
        return name


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return (sum(xs) / len(xs)) if xs else None


def _r(x, nd=2):
    return None if x is None else round(float(x), nd)


def wind_out_component(speed_mph, wind_from_deg, azimuth_deg) -> float | None:
    """Signed component of the wind blowing from home plate toward centre field.

    Forecast wind direction is METEOROLOGICAL: the bearing the wind blows FROM.
    It blows TOWARD from + 180. `azimuth_deg` is the venue's home-plate-to-
    centre-field bearing (StatsAPI `azimuthAngle`: Wrigley 37, Fenway 45, Coors
    4, Oracle 85). Out is positive, the direction that adds carry, matching
    betting_usage.WIND_OUT_COMPONENT's sign on the feed's own strings.
    """
    if speed_mph is None or wind_from_deg is None or azimuth_deg is None:
        return None
    toward = (float(wind_from_deg) + 180.0) % 360.0
    return float(speed_mph) * math.cos(math.radians(toward - float(azimuth_deg)))


def weather_applies(roof_type) -> tuple[bool, str]:
    """(does weather reach the ball, why). A closed roof zeroes the term."""
    rt = str(roof_type or "").strip().lower()
    if rt not in ROOF_WEATHER_APPLIES:
        return False, f"roof type {roof_type!r} is unknown; an unstated roof is not an open one"
    if rt == "open":
        return True, "open-air venue"
    if rt == "dome":
        return False, "fixed dome: weather does not reach the ball, the term is zero by construction"
    return False, ("retractable roof: the roof decision is not published before first pitch "
                   "in any source this repo holds, so the primary arm zeroes the term")


# ---------------------------------------------------------------------------
# venues, off the feed cache already on disk
# ---------------------------------------------------------------------------
def venue_table(*, games: list[dict] | None = None, feed_dir: Path | None = None,
                per_org: int = 3) -> dict:
    """{venue_id: {name, lat, lon, azimuth_deg, roof_type, elevation_ft, tz}}.

    Read off the newest `per_org` completed games per home club, so a club's
    one neutral-site game cannot hide its home park. A schedule game at a venue
    this table does not hold gets a stated null row at capture, never a guess.
    Offline: opens at most 30 * per_org cached feeds.
    """
    fdir = Path(feed_dir) if feed_dir else FEED_DIR
    if games is None:
        try:
            import betting_model as bm
            games = bm.completed_games(refresh=False)
        except Exception:                                        # noqa: BLE001
            games = []
    seen_per_org: dict = {}
    out: dict = {}
    for g in sorted(games or [], key=lambda x: str(x.get("date") or ""), reverse=True):
        ho = g.get("home_org")
        if not ho or seen_per_org.get(ho, 0) >= per_org:
            continue
        try:
            d = json.loads((fdir / f"{int(g['game_pk'])}.json").read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        v = (d.get("gameData") or {}).get("venue") or {}
        vid = v.get("id")
        if vid is None:
            continue
        seen_per_org[ho] = seen_per_org.get(ho, 0) + 1
        if vid in out:
            continue
        loc = v.get("location") or {}
        co = loc.get("defaultCoordinates") or {}
        out[vid] = {
            "name": v.get("name"),
            "lat": co.get("latitude"), "lon": co.get("longitude"),
            "azimuth_deg": loc.get("azimuthAngle"),
            "elevation_ft": loc.get("elevation"),
            "roof_type": (v.get("fieldInfo") or {}).get("roofType"),
            "tz": (v.get("timeZone") or {}).get("id"),
            "home_org": _org(ho),
        }
    return out


def load_schedule(on_date: str, *, data_dir: Path | None = None,
                  horizon_days: int = HORIZON_DAYS) -> list[dict]:
    """fantasy.json schedule games dated on_date .. on_date + horizon - 1."""
    dd = Path(data_dir) if data_dir else DATA_DIR
    try:
        blob = json.loads((dd / "fantasy.json").read_text(encoding="utf-8"))
    except Exception:                                            # noqa: BLE001
        return []
    d0 = date.fromisoformat(on_date)
    want = {(d0 + timedelta(days=k)).isoformat() for k in range(horizon_days)}
    return [g for g in ((blob.get("schedule") or {}).get("games") or [])
            if g.get("date") in want]


# ---------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------
def _default_opener(url: str, headers: dict | None = None) -> bytes:  # pragma: no cover
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def open_meteo_url(points: list[tuple[float, float]], *, forecast_days: int = 3,
                   api_key: str | None = None) -> str:
    """ONE request for every venue: coordinates are comma-separated lists.

    forecast_days is 3 because the series is keyed in UTC from today's 00:00Z,
    and a West Coast night game tomorrow starts after 00:00Z the day after.
    """
    q = {
        "latitude": ",".join(f"{p[0]:.6f}" for p in points),
        "longitude": ",".join(f"{p[1]:.6f}" for p in points),
        "hourly": ",".join(OPEN_METEO_HOURLY),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "GMT",
        "forecast_days": str(int(forecast_days)),
    }
    base = SOURCES["open-meteo"]["endpoint"]
    if api_key:
        q["apikey"] = api_key
        base = SOURCES["open-meteo"]["commercial_endpoint"]
    return base + "?" + urllib.parse.urlencode(q)


def parse_open_meteo(body, n_points: int) -> list[dict]:
    """Response -> one {hour_key: {...}} series per requested point, in order.

    Shape verified by one probe on 2026-09-11 (Wrigley and Coors in one call):
    a LIST of per-location objects in request order, each with `hourly` arrays
    keyed by variable and `time` as 'YYYY-MM-DDTHH:00' in GMT; a single-point
    request returns one object rather than a list. Coordinates snap to the
    model grid (Wrigley 41.948,-87.656 came back 41.963,-87.674).
    """
    locs = body if isinstance(body, list) else [body]
    out = []
    for i in range(n_points):
        loc = locs[i] if i < len(locs) and isinstance(locs[i], dict) else {}
        h = loc.get("hourly") or {}
        times = h.get("time") or []
        series = {}
        for k, t in enumerate(times):
            def _v(name):
                arr = h.get(name) or []
                return arr[k] if k < len(arr) else None
            series[str(t)[:13] + ":00"] = {
                "temp_f": _v("temperature_2m"),
                "rh_pct": _v("relative_humidity_2m"),
                "pressure_hpa": _v("surface_pressure"),
                "wind_mph": _v("wind_speed_10m"),
                "wind_from_deg": _v("wind_direction_10m"),
                "gust_mph": _v("wind_gusts_10m"),
                "precip_prob_pct": _v("precipitation_probability"),
            }
        out.append(series)
    return out


def fetch_open_meteo(points: list[tuple[float, float]], *, opener=None) -> tuple[list[dict], dict]:
    key = os.environ.get(OPEN_METEO_KEY_ENV) or None
    url = open_meteo_url(points, api_key=key)
    raw = (opener or _default_opener)(url, {"User-Agent": "eephus-betting-weather"})
    body = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
    meta = {"source": "open-meteo", "n_calls": 1,
            "endpoint": "commercial" if key else "free (non-commercial)"}
    return parse_open_meteo(body, len(points)), meta


def _nws_mph(s) -> float | None:
    """'10 mph' -> 10.0, '5 to 10 mph' -> 7.5, anything else -> None."""
    nums = [float(x) for x in _NUM_RE.findall(str(s or ""))]
    return (sum(nums) / len(nums)) if nums else None


def parse_nws_hourly(body) -> dict:
    """NWS /gridpoints/.../forecast/hourly -> {hour_key: {...}}.

    Documented shape (weather.gov API docs), NOT probed in the lane that wrote
    this: properties.periods[] with startTime (local offset), temperature and
    temperatureUnit, windSpeed ('10 mph' or '5 to 10 mph'), windDirection as a
    16-point compass string (the direction it blows FROM), and value objects
    for relativeHumidity and probabilityOfPrecipitation. No pressure.
    """
    out = {}
    for p in ((body or {}).get("properties") or {}).get("periods") or []:
        t = _utc(p.get("startTime"))
        if t is None:
            continue
        temp = p.get("temperature")
        try:
            temp = float(temp)
            if str(p.get("temperatureUnit") or "F").upper() == "C":
                temp = temp * 9.0 / 5.0 + 32.0
        except (TypeError, ValueError):
            temp = None
        out[_hour_key(t)] = {
            "temp_f": temp,
            "rh_pct": ((p.get("relativeHumidity") or {}).get("value")),
            "pressure_hpa": None,
            "wind_mph": _nws_mph(p.get("windSpeed")),
            "wind_from_deg": _COMPASS.get(str(p.get("windDirection") or "").strip().upper()),
            "gust_mph": None,
            "precip_prob_pct": ((p.get("probabilityOfPrecipitation") or {}).get("value")),
        }
    return out


def fetch_nws(points: list[tuple[float, float]], *, opener=None) -> tuple[list[dict], dict]:
    ua = os.environ.get(NWS_USER_AGENT_ENV) or "eephus-betting-weather"
    op = opener or _default_opener
    hdr = {"User-Agent": ua, "Accept": "application/geo+json"}
    out, n = [], 0
    for lat, lon in points:
        try:
            pt = json.loads(op(f"{SOURCES['nws']['endpoint']}/points/{lat:.4f},{lon:.4f}", hdr))
            n += 1
            url = (pt.get("properties") or {}).get("forecastHourly")
            if not url:
                out.append({})
                continue
            out.append(parse_nws_hourly(json.loads(op(url, hdr))))
            n += 1
        except Exception:                                        # noqa: BLE001
            # Outside NWS coverage (Toronto) or a transient failure: that venue
            # gets a stated null row, the night does not abort.
            out.append({})
    return out, {"source": "nws", "n_calls": n, "endpoint": "api.weather.gov"}


FETCHERS = {"open-meteo": fetch_open_meteo, "nws": fetch_nws}


# ---------------------------------------------------------------------------
# rows
# ---------------------------------------------------------------------------
def game_row(game: dict, venue: dict | None, series: dict | None,
             captured_at: datetime) -> dict:
    """One captured row for one scheduled game. Never raises."""
    fp = _utc(game.get("datetime"))
    vid = (game.get("venue") or {}).get("id")
    row = {
        "game_pk": game.get("game_pk"), "game_date": game.get("date"),
        "first_pitch_utc": fp.isoformat() if fp else None,
        "home_org": _org((game.get("home") or {}).get("org")),
        "away_org": _org((game.get("away") or {}).get("org")),
        "venue_id": vid, "venue_name": (game.get("venue") or {}).get("name"),
        "roof_type": (venue or {}).get("roof_type"),
        "azimuth_deg": (venue or {}).get("azimuth_deg"),
        "lat": (venue or {}).get("lat"), "lon": (venue or {}).get("lon"),
        "captured_at": captured_at.isoformat(),
        "lead_hours": _r((fp - captured_at).total_seconds() / 3600.0) if fp else None,
        "fc_temp_f": None, "fc_wind_mph": None, "fc_wind_from_deg": None,
        "fc_wind_out_mph": None, "fc_rh_pct": None, "fc_pressure_hpa": None,
        "fc_precip_prob_pct": None, "hours_used": [],
    }
    applies, why = weather_applies(row["roof_type"])
    row["weather_applies"] = applies
    row["roof_basis"] = why
    if venue is None:
        row["basis"] = (f"venue {vid} is not in the cached-feed venue table; no "
                        "coordinates, no forecast, a stated null")
        return row
    if not series:
        row["basis"] = ("no forecast series for this venue tonight (dome not fetched, "
                        "outside the source's coverage, or the request failed)")
        return row
    if fp is None:
        row["basis"] = "no first-pitch time on the schedule row"
        return row
    start = fp.replace(minute=0, second=0, microsecond=0)
    hours = [_hour_key(start + timedelta(hours=k)) for k in range(GAME_WINDOW_HOURS)]
    got = [series[h] for h in hours if h in series]
    if not got:
        row["basis"] = "the forecast series does not reach this game's hours"
        return row
    outs = [wind_out_component(h.get("wind_mph"), h.get("wind_from_deg"),
                               row["azimuth_deg"]) for h in got]
    row.update({
        "fc_temp_f": _r(_mean([h.get("temp_f") for h in got])),
        "fc_wind_mph": _r(_mean([h.get("wind_mph") for h in got])),
        "fc_wind_from_deg": got[0].get("wind_from_deg"),
        # Averaged per hour as a COMPONENT, not from an averaged direction: two
        # hours of 10 mph out and 10 mph in are a zero, not a crosswind.
        "fc_wind_out_mph": _r(_mean(outs)),
        "fc_rh_pct": _r(_mean([h.get("rh_pct") for h in got]), 1),
        "fc_pressure_hpa": _r(_mean([h.get("pressure_hpa") for h in got]), 1),
        "fc_precip_prob_pct": _r(_mean([h.get("precip_prob_pct") for h in got]), 1),
        "hours_used": [h for h in hours if h in series],
    })
    row["basis"] = (f"forecast mean over {len(row['hours_used'])} hour(s) from the "
                    f"first-pitch hour, captured {row['lead_hours']}h before first pitch")
    return row


# ---------------------------------------------------------------------------
# capture (inert unless armed)
# ---------------------------------------------------------------------------
def arming_state(*, enabled: bool | None = None, source: str | None = None) -> dict:
    en = FORECAST_CAPTURE_ENABLED if enabled is None else bool(enabled)
    src = FORECAST_SOURCE if source is None else source
    if not en:
        return {"armed": False, "state": "inert",
                "reason": ("FORECAST_CAPTURE_ENABLED is False: the forecast capture is a "
                           "new external dependency and an owner decision "
                           "(docs/diamond-betting.md 5h). No request is made.")}
    if src not in SOURCES:
        return {"armed": False, "state": "inert",
                "reason": (f"FORECAST_SOURCE is {src!r}; it must name one of "
                           f"{sorted(SOURCES)}, chosen by the owner. No request is made.")}
    return {"armed": True, "state": "armed", "source": src}


def capture(on_date: str | None = None, *, enabled: bool | None = None,
            source: str | None = None, games: list[dict] | None = None,
            venues: dict | None = None, fetch=None, forecast_dir: Path | None = None,
            now: datetime | None = None, log_fn=None) -> dict:
    """Capture tonight's forecast for today's remaining games and tomorrow's.

    INERT unless armed: returns the arming state and makes no request and no
    write. Every input is injectable so the whole path runs offline in a test.
    A game whose first pitch is within MIN_LEAD_HOURS of `now` is skipped and
    listed, because a row captured that late could not inform it anyway.
    """
    st = arming_state(enabled=enabled, source=source)
    if not st["armed"]:
        if log_fn:
            log_fn(f"betting_weather: {st['reason']}")
        return {"captured": False, **st}
    src = st["source"]
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    on_date = on_date or now.date().isoformat()
    games = load_schedule(on_date) if games is None else games
    venues = venue_table() if venues is None else venues

    cutoff = now + timedelta(hours=MIN_LEAD_HOURS)
    eligible, skipped = [], []
    for g in games:
        fp = _utc(g.get("datetime"))
        if fp is None or fp <= cutoff:
            skipped.append({"game_pk": g.get("game_pk"),
                            "reason": ("first pitch within MIN_LEAD_HOURS of the capture, "
                                       "or already played" if fp else "no first-pitch time")})
            continue
        eligible.append(g)

    # One point per venue that weather can reach or that a secondary arm may
    # read (retractable). Domes are never fetched.
    pts, order = [], []
    for g in eligible:
        vid = (g.get("venue") or {}).get("id")
        v = venues.get(vid)
        if (v is None or vid in order or v.get("lat") is None or v.get("lon") is None
                or str(v.get("roof_type") or "").lower() == "dome"):
            continue
        order.append(vid)
        pts.append((float(v["lat"]), float(v["lon"])))

    series_by_venue, meta = {}, {"source": src, "n_calls": 0}
    if pts:
        fn = fetch or FETCHERS[src]
        series_list, meta = fn(pts)
        series_by_venue = {vid: s for vid, s in zip(order, series_list)}

    rows = [game_row(g, venues.get((g.get("venue") or {}).get("id")),
                     series_by_venue.get((g.get("venue") or {}).get("id")), now)
            for g in eligible]
    rec = {
        "schema": SNAPSHOT_SCHEMA, "kind": "forecast", "source": src,
        "source_licence": SOURCES[src]["licence"],
        "captured_at": now.isoformat(), "capture_date": on_date,
        "request": meta, "n_games": len(rows),
        "n_with_forecast": sum(1 for r in rows if r["fc_temp_f"] is not None),
        "n_open_air_with_forecast": sum(1 for r in rows if r["fc_temp_f"] is not None
                                        and r["weather_applies"]),
        "skipped": skipped, "rows": rows,
        "policy": {"min_lead_hours": MIN_LEAD_HOURS, "game_window_hours": GAME_WINDOW_HOURS,
                   "horizon_days": HORIZON_DAYS},
        "note": ("DARK (docs/diamond-betting.md 5h): nothing served reads this file. A row "
                 "may inform a game only when captured_at is at least min_lead_hours before "
                 "first pitch; the observed game weather is never a substitute"),
    }
    fdir = Path(forecast_dir) if forecast_dir else FORECAST_DIR
    fdir.mkdir(parents=True, exist_ok=True)
    path = fdir / f"{now.strftime('%Y-%m-%d-%H%M')}.json"
    if path.exists():
        # Immutable, exactly like the odds snapshots: a capture is the evidence
        # behind a claim about what was knowable, and a later copy must never
        # replace an earlier one.
        raise FileExistsError(f"forecast snapshot {path.name} already exists")
    path.write_text(json.dumps(rec, separators=(",", ":")), encoding="utf-8")
    if log_fn:
        log_fn(f"betting_weather: wrote {path.name} ({rec['n_games']} games, "
               f"{rec['n_with_forecast']} with a forecast, "
               f"{rec['n_open_air_with_forecast']} open-air, {len(skipped)} skipped, "
               f"source {src}, {meta.get('n_calls')} call(s))")
    return {"captured": True, "state": "armed", "path": str(path),
            "n_games": rec["n_games"], "n_with_forecast": rec["n_with_forecast"]}


# ---------------------------------------------------------------------------
# the reader (the only way a later candidate may see a row)
# ---------------------------------------------------------------------------
def snapshot_paths(forecast_dir: Path | None = None) -> list[Path]:
    fdir = Path(forecast_dir) if forecast_dir else FORECAST_DIR
    if not fdir.exists():
        return []
    return sorted(p for p in fdir.glob("????-??-??-????.json"))


def forecast_for_game(game_pk, first_pitch_utc, *, forecast_dir: Path | None = None,
                      min_lead_hours: float = MIN_LEAD_HOURS) -> dict | None:
    """The NEWEST captured row for this game whose own captured_at is at least
    `min_lead_hours` before first pitch, or None.

    The test is on the row's timestamp, never on a file name, and None is the
    only fallback: no observed weather, no climatology, no zero.
    """
    fp = _utc(first_pitch_utc)
    if fp is None:
        return None
    limit = fp - timedelta(hours=float(min_lead_hours))
    best = None
    for p in snapshot_paths(forecast_dir):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        for r in rec.get("rows") or []:
            if r.get("game_pk") != game_pk or r.get("fc_temp_f") is None:
                continue
            ca = _utc(r.get("captured_at"))
            if ca is None or ca > limit:
                continue
            if best is None or ca > _utc(best["captured_at"]):
                best = dict(r, snapshot=p.name)
    return best


def coverage(forecast_dir: Path | None = None) -> dict:
    """COUNTS ONLY: how many captures, rows and open-air rows exist, and when
    the 5h clock started. Never a value, never an outcome."""
    paths = snapshot_paths(forecast_dir)
    n_rows = n_fc = n_open = 0
    first = None
    for p in paths:
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        rows = rec.get("rows") or []
        n_rows += len(rows)
        n_fc += sum(1 for r in rows if r.get("fc_temp_f") is not None)
        k_open = sum(1 for r in rows if r.get("fc_temp_f") is not None and r.get("weather_applies"))
        n_open += k_open
        if first is None and k_open:
            first = (rec.get("captured_at") or "")[:10] or None
    out = {"n_snapshots": len(paths), "n_rows": n_rows, "n_rows_with_forecast": n_fc,
           "n_open_air_rows_with_forecast": n_open, "clock_started": first}
    if first:
        out["earliest_first_look"] = (date.fromisoformat(first) + timedelta(days=28)).isoformat()
        out["clock_note"] = ("5h: four weeks minimum AND the sample floor in 5h; this date is "
                             "the calendar half only")
    else:
        out["clock_note"] = "5h: no open-air forecast row has accrued; the clock has not started"
    return out


# ---------------------------------------------------------------------------
# the physics prior the DARK props model may read (nothing served reads it)
# ---------------------------------------------------------------------------
def hr_weather_prior(temp_f, wind_out_mph=None, *, ref_temp_f, ref_wind_out_field_mph=0.0,
                     roof_type="Open", pass_through: float | None = None) -> dict:
    """Literature multiplier on a batter's home-run rate for this game's weather.

    RELATIVE TO A REFERENCE, because the rate it multiplies was built under some
    conditions already: the batter's season rate times the park HR index
    already carries the venue's usual weather, so the prior prices the ANOMALY.
    Section 5h pre-registers the reference as the venue's own trailing-30-day
    climatology (betting_usage.venue_climatology, the schema-4 builder).

    The wind term needs `pass_through` (forecast 10 m wind -> field wind) and
    is OFF while it is None, which it is until the 5h fidelity check measures it.
    """
    applies, why = weather_applies(roof_type)
    base = {"multiplier": 1.0, "carry_ft": 0.0, "temp_ft": 0.0, "wind_ft": 0.0,
            "extrapolated": False, "roof_basis": why}
    if not applies:
        return dict(base, basis="weather does not reach the ball; multiplier 1.0 by construction",
                    wind_term="off: roof")
    if temp_f is None or ref_temp_f is None:
        return dict(base, basis="no forecast temperature or no reference; multiplier 1.0, stated",
                    wind_term="off: no temperature")
    temp_ft = HR_FT_PER_DEG_F * (float(temp_f) - float(ref_temp_f))
    wind_ft, wind_term = 0.0, "off: pass-through unmeasured (5h fidelity check)"
    pt = WIND_PASS_THROUGH if pass_through is None else pass_through
    if pt is not None and wind_out_mph is not None:
        w = float(pt) * float(wind_out_mph) - float(ref_wind_out_field_mph or 0.0)
        wind_ft = (HR_FT_PER_MPH_OUT if w > 0 else HR_FT_PER_MPH_IN) * w
        wind_term = f"on: pass-through {pt}"
    carry = temp_ft + wind_ft
    return {"multiplier": round(math.exp(HR_LOG_ELASTICITY_PER_FT * carry), 5),
            "carry_ft": round(carry, 3), "temp_ft": round(temp_ft, 3),
            "wind_ft": round(wind_ft, 3),
            "extrapolated": abs(carry) > PRIOR_LOCAL_RANGE_FT,
            "wind_term": wind_term, "roof_basis": why,
            "basis": ("LITERATURE PRIOR (Nathan; Callahan and Mankin 2023), never fitted "
                      "here: carry ft from temperature and wind, times ln(1.25)/8.5 per ft")}


def tb_weather_multiplier(hr_multiplier: float, hr_share_of_tb: float) -> float:
    """Total-bases multiplier implied by the HR multiplier alone.

    `hr_share_of_tb` is the hitter's own 4*HR / TB off the same rest-of-season
    line `props_fair_lines` prices from. This is a LOWER BOUND on the weather
    effect: it ignores extra carry on doubles and triples and the (literature:
    about +0.0001 BABIP per F, Rob Arthur via Nathan) contact effect.
    """
    s = min(max(float(hr_share_of_tb), 0.0), 1.0)
    return 1.0 + s * (float(hr_multiplier) - 1.0)


# ---------------------------------------------------------------------------
# pipeline entry
# ---------------------------------------------------------------------------
def run(*, log_fn=None) -> dict:
    """Nightly entry (run_monthly step 9e-pre-wx). Never raises; inert unless armed."""
    try:
        return capture(log_fn=log_fn)
    except Exception as exc:                                     # noqa: BLE001
        log.exception("betting_weather: capture failed")
        return {"captured": False, "state": "error", "reason": f"{type(exc).__name__}: {exc}"}


if __name__ == "__main__":                                       # pragma: no cover
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Pregame forecast weather capture (dark).")
    ap.add_argument("--capture", action="store_true",
                    help="capture tonight's forecasts (inert unless armed in this file)")
    ap.add_argument("--coverage", action="store_true", help="counts only")
    ap.add_argument("--venues", action="store_true", help="print the offline venue table")
    args = ap.parse_args()
    if args.capture:
        print(json.dumps(run(log_fn=print), indent=1))
    if args.coverage:
        print(json.dumps(coverage(), indent=1))
    if args.venues:
        print(json.dumps(venue_table(), indent=1, default=str))
