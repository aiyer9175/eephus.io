# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""betting_weather.py - pregame FORECAST weather capture for /betting/ (DARK).

Pre-registered in docs/diamond-betting.md section 5h BEFORE this file existed
and before any captured number was related to any game outcome. Nothing served
reads anything here. The capture shipped OFF because it is a new external
dependency, and a new dependency is an owner decision. The owner ARMED it on
2026-09-11 (Open-Meteo, keyless) and approved the section 5h-C backfill arm
from Open-Meteo's Previous Runs API in the same answer. Arming changes no
served number: it starts the capture, the backfill and the 5h clock.

THE SOURCE CHANGED ON 2026-10-08 (owner answer FP5-2, 2026-09-25, final-pass
batch 5): the live capture now reads the US National Weather Service
(api.weather.gov, public domain, no key, a User-Agent naming the site and a
contact), because Open-Meteo's free endpoint is non-commercial only. The owner
accepted the cost: NWS keeps no archive, so the 5h-C backfill arm is gone
(BACKFILL_ENABLED is False; the rows it already wrote stay on disk, read by no
candidate). Same store, same row schema, same dark contract; section 5h's
amendment of 2026-10-08 names the change before any look.

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

THE BACKFILL ARM (section 5h-C) writes into the same directory under its own
name, `previous-runs-<UTC date>-<HHMM>.json`, so the live reader and the live
clock can never pool the two arms (the 5a arm split). Each backfilled row is
the forecast Open-Meteo archived about 24 hours before each game hour
(`<var>_previous_day1`) and carries `issued_at`, the LATEST moment that
forecast could have been issued; a row whose `issued_at` is not at least
MIN_LEAD_HOURS before first pitch is never written. Its `captured_at` is the
honest fetch time, which is after the game, and that is exactly why the live
reader, which tests `captured_at`, can never return a backfilled row.
The Historical Forecast API stays banned (5h): it is stitched from each run's
first hours and tracks observed weather.
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
#: Whether the nightly step makes the forecast call at all. TRUE since
#: 2026-09-11: the owner armed it (docs/diamond-betting.md 5h, "Armed").
#:
#: WHAT ARMING CHANGES, exactly: run_monthly step 9e-pre-wx makes ONE batched
#: Open-Meteo forecast request a night and writes one immutable snapshot under
#: .cache/weather_forecasts/, then the 5h-C backfill (BACKFILL_ENABLED) makes
#: its Previous Runs requests for completed games not yet in the store. The 5h
#: clock starts on the first night a live open-air row lands.
#: WHAT IT DOES NOT CHANGE: no served price, no fair total, no edge, no side
#: marked value, neither Model Watch slot (the Pick of the Day and the longshot
#: are byte-identical), no record row, no shadow or calibration ledger row, no
#: vintage record. Nothing served imports this module and
#: test_betting_weather.py pins that.
#:
#: SINCE 2026-10-08 the one request a night is NWS's two requests per fetched
#: venue (points, then the hourly gridpoint forecast), and there is no backfill
#: (see FORECAST_SOURCE). To disarm: set this False and update the pinned test.
FORECAST_CAPTURE_ENABLED = True

#: Which source. The owner chose Open-Meteo (keyless) on 2026-09-11, and
#: switched to NWS on 2026-09-25 (FP5-2, "Switch weather to NWS (lose the
#: Open-Meteo archive backfill)"), landed 2026-10-08: Open-Meteo's free terms
#: name subscription sites as commercial, NWS data is public domain. None would
#: make the armed flag inert, so that the flag alone can never pick a licence.
FORECAST_SOURCE: str | None = "nws"
#: The date the live capture changed source (docs/diamond-betting.md 5h,
#: amendment 2026-10-08). Rows carry their own `source` at the snapshot level.
FORECAST_SOURCE_SINCE = "2026-10-08"

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
                    "time, archived from January 2024 for most models; the 5h-C "
                    "backfill arm, see PREVIOUS_RUNS"),
    },
    "nws": {
        "endpoint": "https://api.weather.gov",
        "key": "none; a User-Agent naming the site and a contact is required",
        "licence": ("US National Weather Service data, a US Government work in the public "
                    "domain (17 U.S.C. 105); open data, free to use for any purpose "
                    "(weather.gov API docs); no attribution required"),
        "calls_per_night": "2 per open-air or retractable US venue (points, hourly)",
        "archive": "none served by the API; no backfill arm is possible",
        "coverage_gap": "US only: Rogers Centre (TOR, retractable) has no forecast",
        # The hourly gridpoint forecast carries temperature, relative humidity,
        # wind speed, wind direction (a 16-point compass string, so 22.5 degree
        # steps) and precipitation probability. It carries NO surface pressure
        # and NO wind gust, so those two columns are null on every NWS row.
        "variables_missing": ("pressure_hpa", "gust_mph"),
    },
}

#: Environment variable carrying an Open-Meteo COMMERCIAL key. Read from the
#: environment only, never written to an artifact or a log.
OPEN_METEO_KEY_ENV = "EEPHUS_OPEN_METEO_KEY"
#: Environment variable that overrides the NWS User-Agent string.
NWS_USER_AGENT_ENV = "EEPHUS_NWS_USER_AGENT"
#: The NWS User-Agent: the site and a contact, in the form the API docs give,
#: "(myweatherapp.com, contact@myweatherapp.com)". The contact is the site's
#: /sources/ page, which carries the address sources write to.
NWS_USER_AGENT = "(eephus.io, https://eephus.io/sources/)"
#: Attempts per NWS request. The hourly endpoint returns an occasional 5xx
#: that clears on a second try; a venue that fails twice is a stated null row.
NWS_ATTEMPTS = 2

# ---------------------------------------------------------------------------
# the backfill arm (OWNER DECISION 2026-09-11, docs/diamond-betting.md 5h-C)
# ---------------------------------------------------------------------------
#: Whether the backfill runs. FALSE since 2026-10-08: approved by the owner on
#: 2026-09-11, then given up with the switch to NWS (FP5-2, 2026-09-25), which
#: keeps no archive. It also needs the capture armed with FORECAST_SOURCE
#: "open-meteo", so it is inert twice over. The writer and its readers stay,
#: because the `previous-runs-*.json` snapshots it wrote (2026 regular season)
#: stay on disk and coverage() still counts them; no candidate reads them.
BACKFILL_ENABLED = False

#: The seasons the owner approved. 5h-C registered a backfill "over the 2026
#: season to date", so the arm is pinned to 2026: on a date in another season
#: it is inert and says so. Continuing the archive arm into 2027 (which the
#: agreement check's four weeks of overlap would need, see
#: AGREEMENT_MIN_OVERLAP_DAYS) is a separate owner decision (5h, "Armed").
BACKFILL_SEASONS = ("2026",)

#: POLICY caps on ONE night's backfill, so an outage costs one timeout and not
#: the nightly critical path. The first night needs one archive request per
#: venue (32 on the 2026 cache), so 40 covers it; the first failed request ends
#: that night's requests, and every game it would have filled is retried later.
BACKFILL_MAX_REQUESTS_PER_NIGHT = 40
#: Game feeds fetched through feed_cache per night for games whose feed is not
#: cached (a pruned box). The dev box held 2,197 of 2,200 on 2026-09-11; the
#: first failed fetch ends that night's fetches.
BACKFILL_MAX_FEED_FETCHES_PER_NIGHT = 200

#: The archive product. Probed 2026-09-11 (three requests, lane folder only):
#: HTTP 200, the same shape as the forecast API (a LIST of per-location objects
#: for comma-separated coordinates, `hourly` arrays keyed `<var>_previous_day1`
#: in GMT), and every one of the seven variables filled on every hour from
#: 2026-03-25T00:00 to 2026-09-11T23:00 at Wrigley Field and Rogers Centre.
#: The commercial host follows Open-Meteo's `customer-` prefix convention and
#: was NOT probed (no key exists).
PREVIOUS_RUNS = {
    "endpoint": "https://previous-runs-api.open-meteo.com/v1/forecast",
    "commercial_endpoint": "https://customer-previous-runs-api.open-meteo.com/v1/forecast",
    "suffix": "_previous_day1",
    "banned": ("historical-forecast-api.open-meteo.com: stitched from each run's "
               "first hours, it tracks observed weather (5h); never a feature, "
               "never a backfill"),
}

#: The provider's stated lead: `_previous_day1` is "the value that was
#: predicted 24 hours before valid time". The 2026-09-11 probe is consistent
#: with the value at hour T coming from the newest archived run initialised at
#: or before T - 24h: beyond the newest run it repeats that run (it equals the
#: current forecast for hours more than about a day ahead), and for every past
#: hour probed it differs from the current run's value.
BACKFILL_NOMINAL_LEAD_HOURS = 24.0

#: POLICY: hours allowed between a run's initialisation and its publication.
#: Open-Meteo says its global models update every 6 hours; this allowance is
#: twice that, so `issued_at` is an UPPER BOUND on when the forecast behind a
#: row existed, never an optimistic guess. It still sits about ten hours before
#: first pitch for a three-hour window, so no honest row is lost to it.
BACKFILL_ISSUE_ALLOWANCE_HOURS = 12.0

#: A backfill whose games span at most this many UTC days is ONE batched
#: request for every venue (the nightly case); a longer span is one request per
#: venue over that venue's own date range (the first night: about 30 requests,
#: the arithmetic 5h-C registered).
BACKFILL_BATCH_MAX_DAYS = 7

#: File-name prefix of a backfill snapshot. The live glob cannot match it.
BACKFILL_PREFIX = "previous-runs-"

#: The one mutable file of the backfill, under a subdirectory of the store so
#: neither snapshot glob can match it: the last armed run's counts, skips by
#: reason included, so coverage() can report a night that wrote nothing.
BACKFILL_STATE_PATH = Path("state") / "backfill_last_run.json"

#: POLICY thresholds of the 5h-C live-against-archive agreement check, copied
#: from the section as registered; a weather-against-weather comparison. The
#: sign share is over EVERY open-air pair, as registered ("on at least 80% of
#: open-air rows"): a pair where either out-component is zero or null counts as
#: not agreeing.
AGREEMENT_MAX_TEMP_MAE_F = 3.0
AGREEMENT_MIN_SIGN_SHARE = 0.80
#: 5h-C: "so the agreement check has four weeks of overlap to run on". The
#: check returns no verdict (`holds` None) until the paired games span this
#: many calendar days.
AGREEMENT_MIN_OVERLAP_DAYS = 28

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
    if speed_mph is not None and float(speed_mph) == 0.0:
        # Calm: no component in any direction. NWS gives a calm hour an empty
        # direction, which must read as zero, not as a missing value.
        return 0.0
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
    """requests first, urllib only when requests is missing.

    Measured 2026-09-11 on the Windows dev box: urllib's default context failed
    certificate verification against both Open-Meteo hosts ("certificate has
    expired") while requests, on certifi's bundle, returned HTTP 200 from the
    same hosts. The capture shipped with urllib and had never made a request
    through it, so arming it on urllib would have armed a silent failure.
    """
    try:
        import requests
    except ImportError:
        requests = None
    if requests is not None:
        resp = requests.get(url, headers=headers or {}, timeout=30)
        resp.raise_for_status()
        return resp.content
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


def parse_open_meteo(body, n_points: int, *, suffix: str = "") -> list[dict]:
    """Response -> one {hour_key: {...}} series per requested point, in order.

    Shape verified by one probe on 2026-09-11 (Wrigley and Coors in one call):
    a LIST of per-location objects in request order, each with `hourly` arrays
    keyed by variable and `time` as 'YYYY-MM-DDTHH:00' in GMT; a single-point
    request returns one object rather than a list. Coordinates snap to the
    model grid (Wrigley 41.948,-87.656 came back 41.963,-87.674).

    `suffix` reads the Previous Runs archive, whose arrays are keyed
    `<var>_previous_day1`; the same probe discipline confirmed that shape.
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
                arr = h.get(name + suffix) or []
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


def previous_runs_url(points: list[tuple[float, float]], start_date: str, end_date: str,
                      *, api_key: str | None = None) -> str:
    """The Previous Runs archive: `<var>_previous_day1` over a UTC date range,
    every point in one request. Only this suffix is ever requested; the
    current-run value for a past hour is close to observed weather and has no
    use here."""
    sfx = PREVIOUS_RUNS["suffix"]
    q = {
        "latitude": ",".join(f"{p[0]:.6f}" for p in points),
        "longitude": ",".join(f"{p[1]:.6f}" for p in points),
        "hourly": ",".join(v + sfx for v in OPEN_METEO_HOURLY),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "GMT",
        "start_date": str(start_date),
        "end_date": str(end_date),
    }
    base = PREVIOUS_RUNS["endpoint"]
    if api_key:
        q["apikey"] = api_key
        base = PREVIOUS_RUNS["commercial_endpoint"]
    return base + "?" + urllib.parse.urlencode(q)


def fetch_previous_runs(points: list[tuple[float, float]], start_date: str, end_date: str,
                        *, opener=None) -> tuple[list[dict], dict]:
    key = os.environ.get(OPEN_METEO_KEY_ENV) or None
    url = previous_runs_url(points, start_date, end_date, api_key=key)
    raw = (opener or _default_opener)(url, {"User-Agent": "eephus-betting-weather"})
    body = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
    meta = {"source": "open-meteo-previous-runs", "n_calls": 1,
            "endpoint": "commercial" if key else "free (non-commercial)",
            "start_date": str(start_date), "end_date": str(end_date)}
    return parse_open_meteo(body, len(points), suffix=PREVIOUS_RUNS["suffix"]), meta


def _nws_mph(s) -> float | None:
    """'10 mph' -> 10.0, '5 to 10 mph' -> 7.5, anything else -> None. A
    QuantitativeValue object ({'unitCode': 'wmoUnit:km_h-1', 'value': 16}) is
    read by its unit code."""
    if isinstance(s, dict):
        try:
            v = float(s.get("value"))
        except (TypeError, ValueError):
            return None
        unit = str(s.get("unitCode") or "")
        if "km_h" in unit:
            return v / 1.609344
        if "m_s" in unit:
            return v * 2.2369363
        return v
    nums = [float(x) for x in _NUM_RE.findall(str(s or ""))]
    return (sum(nums) / len(nums)) if nums else None


def _nws_temp_f(p: dict) -> float | None:
    """The period's temperature in F, from a number plus temperatureUnit or a
    QuantitativeValue object ({'unitCode': 'wmoUnit:degC', 'value': 20})."""
    temp = p.get("temperature")
    unit = str(p.get("temperatureUnit") or "F").upper()
    if isinstance(temp, dict):
        unit = "C" if "degC" in str(temp.get("unitCode") or "") else "F"
        temp = temp.get("value")
    try:
        temp = float(temp)
    except (TypeError, ValueError):
        return None
    return temp * 9.0 / 5.0 + 32.0 if unit == "C" else temp


def parse_nws_hourly(body) -> dict:
    """NWS /gridpoints/.../forecast/hourly -> {hour_key: {...}}.

    Shape confirmed by one probe on 2026-10-08 (Wrigley Field, gridpoint
    LOT/75,76, HTTP 200, 156 hourly periods): properties.periods[] with
    startTime (local offset), temperature and temperatureUnit ('F'), windSpeed
    ('5 mph', or '5 to 10 mph'), windDirection as a 16-point compass string
    (the direction it blows FROM), and {unitCode, value} objects for
    relativeHumidity and probabilityOfPrecipitation. No pressure and no gust:
    those two columns are null on every NWS row (SOURCES['nws']).
    """
    out = {}
    for p in ((body or {}).get("properties") or {}).get("periods") or []:
        t = _utc(p.get("startTime"))
        if t is None:
            continue
        temp = _nws_temp_f(p)
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


def _nws_get(op, url: str, hdr: dict, counter: list) -> dict:
    """Parsed JSON, in up to NWS_ATTEMPTS tries; the last error is raised.
    Every request made, failed or not, is counted in counter[0]."""
    err = None
    for _ in range(NWS_ATTEMPTS):
        counter[0] += 1
        try:
            raw = op(url, hdr)
            return json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray))
                              else raw)
        except Exception as exc:                                 # noqa: BLE001
            err = exc
    raise err


def fetch_nws(points: list[tuple[float, float]], *, opener=None) -> tuple[list[dict], dict]:
    """Two requests per point: /points/{lat},{lon} names the gridpoint, then its
    `forecastHourly` URL returns the hourly forecast. A point that fails (outside
    NWS coverage, as Toronto is, or down twice) gets an empty series, so its
    rows are stated nulls and the night does not abort."""
    ua = os.environ.get(NWS_USER_AGENT_ENV) or NWS_USER_AGENT
    op = opener or _default_opener
    hdr = {"User-Agent": ua, "Accept": "application/geo+json"}
    out, n, updated, failed = [], [0], [], 0
    for lat, lon in points:
        upd = None
        try:
            pt = _nws_get(op, f"{SOURCES['nws']['endpoint']}/points/{lat:.4f},{lon:.4f}", hdr, n)
            url = (pt.get("properties") or {}).get("forecastHourly")
            if not url:
                failed += 1
                out.append({})
                updated.append(None)
                continue
            body = _nws_get(op, url, hdr, n)
            upd = (body.get("properties") or {}).get("updateTime")
            out.append(parse_nws_hourly(body))
        except Exception as exc:                                 # noqa: BLE001
            log.warning("betting_weather: NWS request for %.4f,%.4f failed: %s", lat, lon, exc)
            failed += 1
            out.append({})
        updated.append(upd)
    return out, {"source": "nws", "n_calls": n[0], "endpoint": "api.weather.gov",
                 "n_points": len(points), "n_points_failed": failed,
                 "forecast_update_times": updated,
                 "variables_missing": list(SOURCES["nws"]["variables_missing"])}


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
        "fc_precip_prob_pct": None, "hours_used": [], "arm": "live",
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
                "reason": ("FORECAST_CAPTURE_ENABLED is False: the forecast capture is "
                           "disarmed, and arming it is an owner decision "
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

    INERT unless armed (it is, since 2026-09-11): disarmed, it returns the
    arming state and makes no request and no write. Every input is
    injectable so the whole path runs offline in a test.
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
# the backfill arm (section 5h-C): Previous Runs, never the Historical Forecast
# ---------------------------------------------------------------------------
def backfill_arming_state(*, enabled: bool | None = None, capture_enabled: bool | None = None,
                          source: str | None = None) -> dict:
    """The backfill needs the capture armed, its own flag, and Open-Meteo."""
    st = arming_state(enabled=capture_enabled, source=source)
    if not st["armed"]:
        return {"armed": False, "state": "inert",
                "reason": "the capture is not armed, so neither is its backfill: " + st["reason"]}
    if not (BACKFILL_ENABLED if enabled is None else bool(enabled)):
        return {"armed": False, "state": "inert",
                "reason": ("BACKFILL_ENABLED is False: the 5h-C backfill is off "
                           "(docs/diamond-betting.md 5h-C). No request is made.")}
    if st["source"] != "open-meteo":
        return {"armed": False, "state": "inert",
                "reason": (f"FORECAST_SOURCE is {st['source']!r}; only Open-Meteo archives "
                           "its forecasts (NWS has no archive), so there is no backfill arm")}
    return {"armed": True, "state": "armed", "source": "open-meteo-previous-runs"}


#: Skip codes a backfill run can record, each a reason the game is retried on a
#: later night (never retired) except `issued_inside_lead`, which is never
#: written at all. coverage()["backfill"]["last_run"] counts them.
SKIP_CODES = ("feed_not_cached", "feed_fetch_failed", "feed_fetch_deferred",
              "no_first_pitch", "hours_not_past", "request_failed", "request_deferred",
              "series_empty", "series_misses_hours", "issued_inside_lead")


def _default_feed_loader(game_pk, game_date):                    # pragma: no cover
    """The game's feed through feed_cache, which caches it for the next reader.
    The same `/feed/live` document the cached files are, so no new shape."""
    import feed_cache
    return feed_cache.get_game_feed(int(game_pk), game_date=game_date)


def feed_game(result_row: dict, *, feed_dir: Path | None = None, feed: dict | None = None):
    """(schedule-shaped game, venue, None) off the game's OWN feed, or
    (None, None, reason). `feed` is a feed already in hand (fetched through
    feed_cache); without it the cached file is read.

    The venue comes from the game, never from the home club's usual park: the
    2026 schedule carries neutral-site games (Mexico City, Las Vegas, the Field
    of Dreams, Williamsport), and a club's park would put their weather in the
    wrong city. That is also why there is no fallback to the club's venue when
    the feed is missing: the game is retried instead. The clubs come from the
    completed-games row, already canonical.
    """
    fdir = Path(feed_dir) if feed_dir else FEED_DIR
    pk = result_row.get("game_pk")
    d = feed
    if d is None:
        try:
            d = json.loads((fdir / f"{int(pk)}.json").read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            d = None
    if not isinstance(d, dict) or not isinstance(d.get("gameData"), dict):
        return None, None, "the game's feed is not cached; retried on a later night"
    gd = d.get("gameData") or {}
    v = gd.get("venue") or {}
    loc = v.get("location") or {}
    co = loc.get("defaultCoordinates") or {}
    dt = gd.get("datetime") or {}
    game = {"game_pk": pk, "date": dt.get("officialDate") or result_row.get("date"),
            "datetime": dt.get("dateTime"),
            "venue": {"id": v.get("id"), "name": v.get("name")},
            "home": {"org": result_row.get("home_org")},
            "away": {"org": result_row.get("away_org")}}
    venue = {"name": v.get("name"), "lat": co.get("latitude"), "lon": co.get("longitude"),
             "azimuth_deg": loc.get("azimuthAngle"), "elevation_ft": loc.get("elevation"),
             "roof_type": (v.get("fieldInfo") or {}).get("roofType"),
             "tz": (v.get("timeZone") or {}).get("id"),
             "home_org": result_row.get("home_org")}
    return game, venue, None


def _window_hours(fp: datetime) -> list[datetime]:
    start = fp.replace(minute=0, second=0, microsecond=0)
    return [start + timedelta(hours=k) for k in range(GAME_WINDOW_HOURS)]


def backfill_row(game: dict, venue: dict, series: dict | None, fetched_at: datetime) -> dict:
    """One backfilled row: the live row's columns, plus the issue time.

    `issued_at` is an UPPER BOUND on when the forecast behind the row existed:
    the newest run behind hour T was initialised no later than T minus
    BACKFILL_NOMINAL_LEAD_HOURS, published within BACKFILL_ISSUE_ALLOWANCE_HOURS
    of that, and the row's latest hour decides. `captured_at` stays the honest
    fetch time. `lead_hours` is measured from `issued_at`, not from the fetch.
    """
    row = game_row(game, venue, series, fetched_at)
    row["arm"] = "backfill"
    row["issued_at"] = None
    row["run_initialised_by"] = None
    row["lead_hours"] = None
    fp = _utc(row.get("first_pitch_utc"))
    if fp is None or not row.get("hours_used") or row.get("fc_temp_f") is None:
        if row.get("hours_used"):
            row["basis"] = ("the archive returned this game's hours with no "
                            "_previous_day1 temperature; a stated null")
        return row
    last = _utc(row["hours_used"][-1])
    run_by = last - timedelta(hours=BACKFILL_NOMINAL_LEAD_HOURS)
    issued = run_by + timedelta(hours=BACKFILL_ISSUE_ALLOWANCE_HOURS)
    row["run_initialised_by"] = run_by.isoformat()
    row["issued_at"] = issued.isoformat()
    row["lead_hours"] = _r((fp - issued).total_seconds() / 3600.0)
    row["basis"] = (f"Previous Runs _previous_day1 mean over {len(row['hours_used'])} hour(s) "
                    f"from the first-pitch hour; the newest run behind it was initialised no "
                    f"later than {run_by.isoformat()} and issued no later than "
                    f"{issued.isoformat()}, {row['lead_hours']}h before first pitch; fetched "
                    f"after the game ({row['captured_at']})")
    return row


def backfill_paths(forecast_dir: Path | None = None) -> list[Path]:
    fdir = Path(forecast_dir) if forecast_dir else FORECAST_DIR
    if not fdir.exists():
        return []
    return sorted(fdir.glob(f"{BACKFILL_PREFIX}????-??-??-????.json"))


def _backfill_rows(forecast_dir: Path | None = None):
    """(snapshot name, row) for every backfilled row, oldest snapshot first."""
    for p in backfill_paths(forecast_dir):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        for r in rec.get("rows") or []:
            yield p.name, r


def backfill_game_pks(forecast_dir: Path | None = None) -> set:
    """Games already in the backfill store. First write wins, as in the vintage
    store: a game is never fetched or written twice."""
    return {r.get("game_pk") for _, r in _backfill_rows(forecast_dir)}


def _backfill_batches(groups: dict) -> list[tuple[list, str, str]]:
    """[(venue ids, start UTC date, end UTC date)]: one batch for a short span,
    else one per venue over that venue's own range."""
    def _span(fps):
        hrs = [h for fp in fps for h in _window_hours(fp)]
        return min(hrs).date(), max(hrs).date()
    spans = {vid: _span([fp for _, fp in g["games"]]) for vid, g in groups.items()}
    if not spans:
        return []
    lo = min(s[0] for s in spans.values())
    hi = max(s[1] for s in spans.values())
    if (hi - lo).days + 1 <= BACKFILL_BATCH_MAX_DAYS:
        return [(list(groups), lo.isoformat(), hi.isoformat())]
    return [([vid], s[0].isoformat(), s[1].isoformat()) for vid, s in spans.items()]


def _write_last_run(fdir: Path, state: dict) -> None:
    """The one mutable file: the last armed run's counts. Best effort."""
    try:
        p = fdir / BACKFILL_STATE_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
    except Exception:                                            # noqa: BLE001
        log.warning("betting_weather backfill: could not write %s", BACKFILL_STATE_PATH)


def backfill(season: str | int | None = None, *, enabled: bool | None = None,
             capture_enabled: bool | None = None, source: str | None = None,
             games: list[dict] | None = None, feed_dir: Path | None = None, fetch=None,
             feed_loader=None, forecast_dir: Path | None = None, now: datetime | None = None,
             date_from: str | None = None, date_to: str | None = None, log_fn=None) -> dict:
    """Backfill every completed regular-season game of an approved season
    (BACKFILL_SEASONS) not yet in the store from the Previous Runs archive
    (section 5h-C).

    Open-air and retractable venues are fetched (retractable rows carry
    `weather_applies = False`, for the secondary arm, as in the live capture);
    domes never, and a dome game or a venue without coordinates is written as a
    stated null. A forecast row is written only if its `issued_at` is at least
    MIN_LEAD_HOURS before first pitch. A game whose feed cannot be read, or
    whose request failed or was deferred, is listed with a code from SKIP_CODES
    and NOT written, so a later night fills it; first write wins after that.

    A feed missing from the cache is fetched through feed_cache (at most
    BACKFILL_MAX_FEED_FETCHES_PER_NIGHT, and none after the first failure).
    That default loader is used only on the production feed cache: a caller
    that points `feed_dir` elsewhere fetches nothing unless it injects
    `feed_loader(game_pk, game_date)`. Archive requests stop at the first
    failure and at BACKFILL_MAX_REQUESTS_PER_NIGHT. Every armed run records its
    counts, skips by code included, in BACKFILL_STATE_PATH. Inert unless armed;
    every input injectable.
    """
    st = backfill_arming_state(enabled=enabled, capture_enabled=capture_enabled, source=source)
    if not st["armed"]:
        if log_fn:
            log_fn(f"betting_weather backfill: {st['reason']}")
        return {"captured": False, **st}
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    season = str(season or now.year)
    if season not in BACKFILL_SEASONS:
        reason = (f"season {season} is not an approved backfill season {BACKFILL_SEASONS}: "
                  "the owner approved the 2026 season (5h-C); another season is a new "
                  "owner decision. No request is made.")
        if log_fn:
            log_fn(f"betting_weather backfill: {reason}")
        return {"captured": False, "armed": False, "state": "inert", "reason": reason}
    if games is None:
        import betting_model as bm
        games = bm.completed_games(season, refresh=False)
    have = backfill_game_pks(forecast_dir)
    loader = feed_loader
    if loader is None and feed_dir is None:
        loader = _default_feed_loader

    groups: dict = {}
    skipped: list = []
    null_rows: list = []
    n_have = 0
    n_feed_fetches, feed_fetch_down = 0, False

    def _skip(pk, day, code, reason):
        skipped.append({"game_pk": pk, "date": day, "code": code, "reason": reason})

    for g in sorted(games or [], key=lambda x: (str(x.get("date") or ""), x.get("game_pk") or 0)):
        pk = g.get("game_pk")
        if g.get("season") is not None and str(g.get("season")) != season:
            continue
        d = str(g.get("date") or "")
        if (date_from and d < date_from) or (date_to and d > date_to):
            continue
        if pk in have:
            n_have += 1
            continue
        sg, venue, why = feed_game(g, feed_dir=feed_dir)
        code = "feed_not_cached" if why else None
        if why and loader is not None:
            if feed_fetch_down or n_feed_fetches >= BACKFILL_MAX_FEED_FETCHES_PER_NIGHT:
                code = "feed_fetch_deferred"
                why = ("the game's feed is not cached and tonight's feed fetches are spent "
                       "or stopped; retried on a later night")
            else:
                n_feed_fetches += 1
                try:
                    sg, venue, why = feed_game(g, feed=loader(pk, d or None))
                    code = "feed_not_cached" if why else None
                except Exception as exc:                         # noqa: BLE001
                    feed_fetch_down = True
                    log.warning("betting_weather backfill: feed fetch for %s failed, no more "
                                "feed fetches tonight: %s", pk, exc)
                    code = "feed_fetch_failed"
                    why = "fetching the game's feed failed; retried on a later night"
        fp = _utc(sg.get("datetime")) if sg else None
        roof = str((venue or {}).get("roof_type") or "").strip().lower()
        if why is None and fp is None:
            code = "no_first_pitch"
            why = "no first-pitch time in the game's feed; retried on a later night"
        if why is None and _window_hours(fp)[-1] + timedelta(hours=1) > now:
            code = "hours_not_past"
            why = "the game's hours are not all past yet; retried on a later night"
        if why:
            _skip(pk, d, code, why)
            continue
        # Durable facts are written as stated nulls, as the live capture writes
        # its dome rows, so first-write-wins retires them and no later night
        # re-reads their feeds.
        null_why = None
        if roof == "dome":
            null_why = "fixed dome: weather does not reach the ball, never fetched"
        elif venue.get("lat") is None or venue.get("lon") is None:
            null_why = "the game's own feed carries no venue coordinates; a stated null"
        if null_why:
            nr = backfill_row(sg, venue, None, now)
            nr["basis"] = null_why
            null_rows.append(nr)
            continue
        vid = sg["venue"]["id"]
        grp = groups.setdefault(vid, {"venue": venue, "games": []})
        grp["games"].append((sg, fp))

    fn = fetch or fetch_previous_runs
    series_by_venue: dict = {}
    failed_vids: set = set()
    n_calls, n_requests, endpoint, batches = 0, 0, None, _backfill_batches(groups)
    for vids, d0, d1 in batches:
        if n_requests >= BACKFILL_MAX_REQUESTS_PER_NIGHT:
            break                    # the rest are deferred to a later night
        pts = [(float(groups[v]["venue"]["lat"]), float(groups[v]["venue"]["lon"])) for v in vids]
        n_requests += 1
        try:
            sl, meta = fn(pts, d0, d1)
        except Exception as exc:                                 # noqa: BLE001
            # One failure ends the night's requests: a hung or refusing host
            # costs one timeout, never one per venue on the critical path.
            log.warning("betting_weather backfill: request for %d venue(s) %s..%s failed, no "
                        "more requests tonight: %s", len(vids), d0, d1, exc)
            failed_vids.update(vids)
            break
        n_calls += int((meta or {}).get("n_calls", 1))
        endpoint = (meta or {}).get("endpoint", endpoint)
        for v, s in zip(vids, sl):
            series_by_venue[v] = s

    rows = []
    for vid, grp in groups.items():
        for sg, fp in grp["games"]:
            if not series_by_venue.get(vid):
                if vid in failed_vids:
                    code, why = "request_failed", "the archive request failed"
                elif vid not in series_by_venue:
                    code, why = ("request_deferred", "no archive request was made tonight "
                                 "(the request cap, or an earlier failure)")
                else:
                    code, why = "series_empty", "the archive returned no series for this venue"
                _skip(sg["game_pk"], sg["date"], code, why + "; retried on a later night")
                continue
            row = backfill_row(sg, grp["venue"], series_by_venue[vid], now)
            if not row.get("hours_used"):
                # A series that misses the game's hours is a request problem,
                # not a fact about the archive: never retire the game on it.
                _skip(sg["game_pk"], sg["date"], "series_misses_hours",
                      "the archive series does not reach this game's hours; retried on a "
                      "later night")
                continue
            issued = _utc(row.get("issued_at"))
            if issued is not None and issued > fp - timedelta(hours=MIN_LEAD_HOURS):
                # Cannot happen at the registered constants; enforced on the row
                # anyway, because it is the whole safety property of this arm.
                _skip(sg["game_pk"], sg["date"], "issued_inside_lead",
                      "issued_at is not MIN_LEAD_HOURS before first pitch; never written")
                continue
            rows.append(row)
    rows.extend(null_rows)
    rows.sort(key=lambda r: (str(r.get("first_pitch_utc") or ""), r.get("game_pk") or 0))

    by_code: dict = {}
    for s in skipped:
        by_code[s["code"]] = by_code.get(s["code"], 0) + 1
    base = {"n_calls": n_calls, "n_requests": n_requests, "n_feed_fetches": n_feed_fetches,
            "n_already_in_store": n_have, "n_skipped": len(skipped),
            "skipped_by_code": dict(sorted(by_code.items()))}
    fdir = Path(forecast_dir) if forecast_dir else FORECAST_DIR
    last_run = {"run_at": now.isoformat(), "season": season, "n_written": len(rows),
                "snapshot": None, **base}
    if not rows:
        _write_last_run(fdir, last_run)
        if log_fn:
            log_fn(f"betting_weather backfill: nothing new to write ({n_have} game(s) already "
                   f"in the store, {len(skipped)} skipped {base['skipped_by_code']}, "
                   f"{n_requests} request(s), {n_feed_fetches} feed fetch(es))")
        return {"captured": False, "state": "armed", "reason": "no new row", **base}
    rec = {
        "schema": SNAPSHOT_SCHEMA, "kind": "previous_runs_backfill", "arm": "backfill",
        "source": "open-meteo-previous-runs", "source_licence": SOURCES["open-meteo"]["licence"],
        "variable_suffix": PREVIOUS_RUNS["suffix"],
        "captured_at": now.isoformat(), "season": season,
        "request": {"n_calls": n_calls, "n_requests": n_requests, "n_batches": len(batches),
                    "n_venues": len(groups), "endpoint": endpoint,
                    "n_feed_fetches": n_feed_fetches},
        "n_games": len(rows),
        "n_with_forecast": sum(1 for r in rows if r["fc_temp_f"] is not None),
        "n_open_air_with_forecast": sum(1 for r in rows if r["fc_temp_f"] is not None
                                        and r["weather_applies"]),
        "n_already_in_store": n_have, "skipped_by_code": base["skipped_by_code"],
        "skipped": skipped, "rows": rows,
        "policy": {"min_lead_hours": MIN_LEAD_HOURS, "game_window_hours": GAME_WINDOW_HOURS,
                   "nominal_lead_hours": BACKFILL_NOMINAL_LEAD_HOURS,
                   "issue_allowance_hours": BACKFILL_ISSUE_ALLOWANCE_HOURS},
        "note": ("DARK (docs/diamond-betting.md 5h-C): the BACKFILL arm, counted separately "
                 "from the live capture. A row may inform a game only when issued_at is at "
                 "least min_lead_hours before first pitch; captured_at is the fetch time and "
                 "is after the game. Never the Historical Forecast API"),
    }
    fdir.mkdir(parents=True, exist_ok=True)
    path = fdir / f"{BACKFILL_PREFIX}{now.strftime('%Y-%m-%d-%H%M')}.json"
    if path.exists():
        raise FileExistsError(f"backfill snapshot {path.name} already exists")
    path.write_text(json.dumps(rec, separators=(",", ":")), encoding="utf-8")
    _write_last_run(fdir, dict(last_run, snapshot=path.name))
    if log_fn:
        log_fn(f"betting_weather backfill: wrote {path.name} ({rec['n_games']} games, "
               f"{rec['n_with_forecast']} with a forecast, {rec['n_open_air_with_forecast']} "
               f"open-air, {len(skipped)} skipped {base['skipped_by_code']}, {n_have} already "
               f"in the store, {n_requests} request(s), {n_feed_fetches} feed fetch(es))")
    return {"captured": True, "state": "armed", "path": str(path), "n_games": rec["n_games"],
            "n_with_forecast": rec["n_with_forecast"], **base}


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


def backfill_forecast_for_game(game_pk, first_pitch_utc, *, forecast_dir: Path | None = None,
                               min_lead_hours: float = MIN_LEAD_HOURS) -> dict | None:
    """The BACKFILLED row for this game, or None; the only reader of that arm.

    The clock test is on the row's own `issued_at`, never on `captured_at`
    (the fetch time, always after the game) and never on a file name. First
    write wins, so the earliest snapshot holding the game is the one read.
    None is the only fallback, exactly as in the live reader.
    """
    fp = _utc(first_pitch_utc)
    if fp is None:
        return None
    limit = fp - timedelta(hours=float(min_lead_hours))
    for name, r in _backfill_rows(forecast_dir):
        if r.get("game_pk") != game_pk:
            continue
        issued = _utc(r.get("issued_at"))
        if r.get("fc_temp_f") is None or issued is None or issued > limit:
            return None
        return dict(r, snapshot=name)
    return None


def live_archive_agreement(forecast_dir: Path | None = None, *,
                           min_lead_hours: float = MIN_LEAD_HOURS) -> dict:
    """The 5h-C precondition: the live capture against the archive on the games
    both arms hold, open-air only. WEATHER AGAINST WEATHER: it reads no score,
    no run, no line and no betting row, and it is not the 5h fidelity check
    (which compares a forecast with the feed's at-game weather).

    The registered rule decides: mean absolute temperature difference at most
    AGREEMENT_MAX_TEMP_MAE_F, and out-component sign agreement on at least
    AGREEMENT_MIN_SIGN_SHARE of ALL open-air pairs, so a pair where either
    component is zero or null counts as NOT agreeing. The share over signed
    pairs only is reported beside it and never decides. `holds` is None, no
    verdict, until the paired games span AGREEMENT_MIN_OVERLAP_DAYS (5h-C's four
    weeks of overlap).
    """
    live: dict = {}
    for p in snapshot_paths(forecast_dir):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:                                        # noqa: BLE001
            continue
        for r in rec.get("rows") or []:
            fp, ca = _utc(r.get("first_pitch_utc")), _utc(r.get("captured_at"))
            if r.get("fc_temp_f") is None or fp is None or ca is None:
                continue
            if ca > fp - timedelta(hours=float(min_lead_hours)):
                continue
            prev = live.get(r.get("game_pk"))
            if prev is None or ca > _utc(prev["captured_at"]):
                live[r.get("game_pk")] = r
    seen: set = set()
    diffs, days, n_signed, n_agree, n_zero_or_null = [], [], 0, 0, 0
    for _, r in _backfill_rows(forecast_dir):
        pk = r.get("game_pk")
        if pk in seen:
            continue
        seen.add(pk)
        lv = live.get(pk)
        if (lv is None or r.get("fc_temp_f") is None or not r.get("weather_applies")
                or not lv.get("weather_applies")):
            continue
        diffs.append(abs(float(lv["fc_temp_f"]) - float(r["fc_temp_f"])))
        fp = _utc(r.get("first_pitch_utc"))
        gd = r.get("game_date") or (fp.date().isoformat() if fp else None)
        if gd:
            days.append(str(gd)[:10])
        a, b = lv.get("fc_wind_out_mph"), r.get("fc_wind_out_mph")
        if a is None or b is None or a == 0 or b == 0:
            n_zero_or_null += 1          # in the denominator, never agreeing
            continue
        n_signed += 1
        n_agree += int((a > 0) == (b > 0))
    n_pairs = len(diffs)
    mae = _r(_mean(diffs), 3)
    share = _r(n_agree / n_pairs, 4) if n_pairs else None
    share_signed = _r(n_agree / n_signed, 4) if n_signed else None
    span = ((date.fromisoformat(max(days)) - date.fromisoformat(min(days))).days + 1
            if days else 0)
    holds = None
    if n_pairs and span >= AGREEMENT_MIN_OVERLAP_DAYS:
        holds = bool(mae <= AGREEMENT_MAX_TEMP_MAE_F and share >= AGREEMENT_MIN_SIGN_SHARE)
    return {"n_pairs": n_pairs, "temp_mae_f": mae,
            "sign_agreement": share, "n_sign_agreeing": n_agree,
            "n_pairs_zero_or_null_component": n_zero_or_null,
            "sign_agreement_signed_pairs_only": share_signed,
            "overlap_first_date": min(days) if days else None,
            "overlap_last_date": max(days) if days else None,
            "overlap_span_days": span, "holds": holds,
            "thresholds": {"max_temp_mae_f": AGREEMENT_MAX_TEMP_MAE_F,
                           "min_sign_share": AGREEMENT_MIN_SIGN_SHARE,
                           "min_overlap_days": AGREEMENT_MIN_OVERLAP_DAYS},
            "note": ("5h-C precondition, weather against weather; the sign share is over every "
                     "open-air pair as registered, the signed-only share is reported and never "
                     "decides; no verdict before min_overlap_days; no backfilled row is used "
                     "by any candidate until this holds")}


def coverage(forecast_dir: Path | None = None) -> dict:
    """COUNTS ONLY: how many captures, rows and open-air rows exist, and when
    the 5h clock started. Never a value, never an outcome. The backfill arm is
    counted in its own block and never starts or advances the live clock."""
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
    bf = {"n_snapshots": len(backfill_paths(forecast_dir)), "n_rows": 0,
          "n_rows_with_forecast": 0, "n_open_air_rows_with_forecast": 0,
          "first_game_date": None, "last_game_date": None, "n_rows_issued_inside_lead": 0}
    for _, r in _backfill_rows(forecast_dir):
        bf["n_rows"] += 1
        if r.get("fc_temp_f") is None:
            continue
        bf["n_rows_with_forecast"] += 1
        bf["n_open_air_rows_with_forecast"] += int(bool(r.get("weather_applies")))
        gd = r.get("game_date")
        if gd and (bf["first_game_date"] is None or gd < bf["first_game_date"]):
            bf["first_game_date"] = gd
        if gd and (bf["last_game_date"] is None or gd > bf["last_game_date"]):
            bf["last_game_date"] = gd
        fp, issued = _utc(r.get("first_pitch_utc")), _utc(r.get("issued_at"))
        if fp is None or issued is None or issued > fp - timedelta(hours=MIN_LEAD_HOURS):
            bf["n_rows_issued_inside_lead"] += 1
    # The last armed run, skips by code included, so a night that wrote nothing
    # (every game skipped, say, on a pruned feed cache) is visible here too.
    fdir = Path(forecast_dir) if forecast_dir else FORECAST_DIR
    try:
        lr = json.loads((fdir / BACKFILL_STATE_PATH).read_text(encoding="utf-8"))
    except Exception:                                            # noqa: BLE001
        lr = None
    bf["last_run"] = ({k: lr.get(k) for k in ("run_at", "season", "n_written", "snapshot",
                                              "n_requests", "n_feed_fetches",
                                              "n_already_in_store", "n_skipped",
                                              "skipped_by_code")}
                      if isinstance(lr, dict) else None)
    bf["note"] = ("5h-C backfill arm, counted SEPARATELY from the live capture (the 5a arm "
                  "split); its rows never start or advance the live clock, and no candidate "
                  "reads them until live_archive_agreement() holds")
    out["backfill"] = bf
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
    """Nightly entry (run_monthly step 9e-pre-wx). Never raises; inert unless armed.

    The live capture runs FIRST, so its timestamp is the earliest the night
    can give it; the 5h-C backfill runs after it, in its own guard, and can
    neither delay nor block it. The backfill's result rides under "backfill".
    """
    try:
        out = capture(log_fn=log_fn)
    except Exception as exc:                                     # noqa: BLE001
        log.exception("betting_weather: capture failed")
        out = {"captured": False, "state": "error", "reason": f"{type(exc).__name__}: {exc}"}
    try:
        out["backfill"] = backfill(log_fn=log_fn)
    except Exception as exc:                                     # noqa: BLE001
        log.exception("betting_weather: backfill failed")
        out["backfill"] = {"captured": False, "state": "error",
                           "reason": f"{type(exc).__name__}: {exc}"}
    return out


if __name__ == "__main__":                                       # pragma: no cover
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Pregame forecast weather capture (dark).")
    ap.add_argument("--capture", action="store_true",
                    help="capture tonight's forecasts, then run the 5h-C backfill")
    ap.add_argument("--backfill", action="store_true",
                    help="run the 5h-C Previous Runs backfill alone (first write wins)")
    ap.add_argument("--from", dest="date_from", default=None, help="backfill: first game date")
    ap.add_argument("--to", dest="date_to", default=None, help="backfill: last game date")
    ap.add_argument("--coverage", action="store_true", help="counts only")
    ap.add_argument("--agreement", action="store_true",
                    help="the 5h-C live-against-archive agreement check (weather only)")
    ap.add_argument("--venues", action="store_true", help="print the offline venue table")
    args = ap.parse_args()
    if args.capture:
        print(json.dumps(run(log_fn=print), indent=1))
    if args.backfill:
        print(json.dumps(backfill(date_from=args.date_from, date_to=args.date_to,
                                  log_fn=print), indent=1))
    if args.coverage:
        print(json.dumps(coverage(), indent=1))
    if args.agreement:
        print(json.dumps(live_archive_agreement(), indent=1))
    if args.venues:
        print(json.dumps(venue_table(), indent=1, default=str))
