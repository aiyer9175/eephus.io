"""Forecast weather capture (docs/diamond-betting.md 5h). DARK; ARMED 2026-09-11.

Every test here is about whether the CAPTURE, the 5h-C BACKFILL and the READERS
do what they claim. None of them relates a forecast to a game outcome, because
5c rule 1 disqualifies a candidate measured before its clock, and the 5h clock
has not opened. Offline: every request is an injected stub, every write is
tmp_path. The module is armed by default now, so no test here may call a
network path without injecting its fetch.
"""
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import betting_weather as bw

ROOT = Path(__file__).resolve().parent
NOW = datetime(2026, 9, 11, 19, 0, tzinfo=timezone.utc)
BF_NOW = datetime(2026, 9, 11, 21, 0, tzinfo=timezone.utc)

VENUES = {
    17: {"name": "Wrigley Field", "lat": 41.948171, "lon": -87.655503,
         "azimuth_deg": 37.0, "roof_type": "Open", "home_org": "CHC"},
    32: {"name": "American Family Field", "lat": 43.02838, "lon": -87.97099,
         "azimuth_deg": 129.0, "roof_type": "Retractable", "home_org": "MIL"},
    12: {"name": "Tropicana Field", "lat": 27.767778, "lon": -82.6525,
         "azimuth_deg": 359.0, "roof_type": "Dome", "home_org": "TBR"},
}


def _game(pk, venue, when, home="CHC", away="PIT", day="2026-09-11"):
    return {"game_pk": pk, "date": day, "datetime": when, "venue": {"id": venue, "name": "x"},
            "home": {"org": home}, "away": {"org": away}}


def _series(temp=70.0, mph=10.0, frm=217.0, start="2026-09-11T00:00", hours=72):
    """A flat hourly series keyed the way both parsers key theirs."""
    t0 = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    out = {}
    for k in range(hours):
        h = bw._hour_key(t0 + timedelta(hours=k))
        out[h] = {"temp_f": temp, "rh_pct": 50, "pressure_hpa": 990.0, "wind_mph": mph,
                  "wind_from_deg": frm, "gust_mph": None, "precip_prob_pct": 0}
    return out


def _stub_fetch(calls):
    def fetch(points):
        calls.append(list(points))
        return [_series() for _ in points], {"source": "stub", "n_calls": 1}
    return fetch


# --------------------------------------------------------------- the flag
def test_the_capture_is_armed_on_open_meteo_and_the_backfill_approved():
    """The owner armed the capture (Open-Meteo, keyless) and approved the 5h-C
    backfill on 2026-09-11. Disarming is one commit that changes this pin on
    purpose. The wind pass-through stays unmeasured: arming is not a look."""
    assert bw.FORECAST_CAPTURE_ENABLED is True
    assert bw.FORECAST_SOURCE == "open-meteo"
    assert bw.BACKFILL_ENABLED is True
    assert bw.WIND_PASS_THROUGH is None
    assert bw.arming_state()["armed"] is True
    assert bw.backfill_arming_state()["armed"] is True


def test_disarmed_makes_no_request_and_writes_nothing(tmp_path):
    calls = []
    out = bw.capture("2026-09-11", enabled=False, games=[_game(1, 17, "2026-09-11T23:05:00Z")],
                     venues=VENUES, fetch=_stub_fetch(calls), forecast_dir=tmp_path, now=NOW)
    assert out["captured"] is False and out["state"] == "inert"
    assert "FORECAST_CAPTURE_ENABLED" in out["reason"]
    assert calls == []
    assert list(tmp_path.iterdir()) == []


def test_enabled_without_a_valid_source_is_still_inert(tmp_path):
    """The flag alone must not silently pick a licence."""
    calls = []
    out = bw.capture("2026-09-11", enabled=True, source="",
                     games=[_game(1, 17, "2026-09-11T23:05:00Z")],
                     venues=VENUES, fetch=_stub_fetch(calls), forecast_dir=tmp_path, now=NOW)
    assert out["captured"] is False and "FORECAST_SOURCE" in out["reason"]
    assert calls == []


def test_run_never_raises_and_captures_before_it_backfills(monkeypatch):
    """The live capture's timestamp must be the earliest the night can give
    it, so it runs first; a failure in either arm never raises out of run()."""
    order = []

    def cap(**k):
        order.append("capture")
        raise RuntimeError("capture down")

    def bf(**k):
        order.append("backfill")
        raise RuntimeError("archive down")

    monkeypatch.setattr(bw, "capture", cap)
    monkeypatch.setattr(bw, "backfill", bf)
    out = bw.run()
    assert order == ["capture", "backfill"]
    assert out["captured"] is False and out["state"] == "error"
    assert out["backfill"]["state"] == "error"


# ---------------------------------------------------------- wind geometry
@pytest.mark.parametrize("frm,expect", [
    (217.0, 10.0),    # from behind home plate, blowing toward CF (azimuth 37): straight out
    (37.0, -10.0),    # from centre field toward the plate: straight in
    (127.0, 0.0),     # across the field
    (307.0, 0.0),     # across the other way
])
def test_wind_resolves_into_a_signed_out_to_centre_component(frm, expect):
    """Meteorological direction is where the wind blows FROM; out is positive,
    matching the sign betting_usage gives the feed's own 'Out To CF'."""
    assert bw.wind_out_component(10.0, frm, 37.0) == pytest.approx(expect, abs=1e-9)


def test_wind_component_is_null_when_any_input_is_missing():
    assert bw.wind_out_component(None, 200, 37) is None
    assert bw.wind_out_component(10, None, 37) is None
    assert bw.wind_out_component(10, 200, None) is None


@pytest.mark.parametrize("roof,applies", [
    ("Open", True), ("Retractable", False), ("Dome", False), (None, False), ("", False)])
def test_a_closed_or_unknown_roof_zeroes_the_weather_term(roof, applies):
    assert bw.weather_applies(roof)[0] is applies


# ---------------------------------------------------------------- parsers
def test_open_meteo_parses_the_probed_multi_location_shape():
    """The shape the 2026-09-11 probe returned: a list of per-location objects
    in request order, hourly arrays keyed by variable, GMT hour strings."""
    loc = {"latitude": 41.962704, "longitude": -87.67416, "elevation": 182.0,
           "hourly_units": {"time": "iso8601"},
           "hourly": {"time": ["2026-09-11T23:00", "2026-09-12T00:00"],
                      "temperature_2m": [74.2, 72.0], "relative_humidity_2m": [60, 62],
                      "surface_pressure": [991.0, 991.4], "wind_speed_10m": [10.5, 9.0],
                      "wind_direction_10m": [106, 110], "wind_gusts_10m": [17.2, 15.0],
                      "precipitation_probability": [0, 5]}}
    out = bw.parse_open_meteo([loc, dict(loc, location_id=1)], 2)
    assert len(out) == 2
    assert out[0]["2026-09-11T23:00"]["temp_f"] == 74.2
    assert out[1]["2026-09-12T00:00"]["wind_from_deg"] == 110
    # a single-point request comes back as one object, not a list
    assert bw.parse_open_meteo(loc, 1)[0]["2026-09-11T23:00"]["wind_mph"] == 10.5


def test_open_meteo_url_batches_every_venue_in_one_request():
    url = bw.open_meteo_url([(41.9, -87.6), (39.7, -104.9)])
    assert url.startswith(bw.SOURCES["open-meteo"]["endpoint"])
    assert "latitude=41.900000%2C39.700000" in url
    assert "wind_speed_unit=mph" in url and "temperature_unit=fahrenheit" in url
    assert "apikey" not in url
    keyed = bw.open_meteo_url([(41.9, -87.6)], api_key="k")
    assert keyed.startswith(bw.SOURCES["open-meteo"]["commercial_endpoint"])


def test_nws_hourly_parses_to_utc_hours_and_degrees_from():
    body = {"properties": {"periods": [
        {"startTime": "2026-09-11T18:00:00-05:00", "temperature": 74, "temperatureUnit": "F",
         "windSpeed": "5 to 10 mph", "windDirection": "SW",
         "relativeHumidity": {"value": 55}, "probabilityOfPrecipitation": {"value": 10}},
        {"startTime": "2026-09-11T19:00:00-05:00", "temperature": 20, "temperatureUnit": "C",
         "windSpeed": "12 mph", "windDirection": "N"}]}}
    s = bw.parse_nws_hourly(body)
    assert s["2026-09-11T23:00"]["wind_mph"] == 7.5
    assert s["2026-09-11T23:00"]["wind_from_deg"] == 225.0
    assert s["2026-09-11T23:00"]["temp_f"] == 74.0
    assert s["2026-09-12T00:00"]["temp_f"] == pytest.approx(68.0)
    assert s["2026-09-12T00:00"]["wind_from_deg"] == 0.0


# ---------------------------------------------------------------- capture
def test_armed_capture_writes_one_immutable_snapshot(tmp_path):
    calls = []
    games = [_game(1, 17, "2026-09-11T23:05:00Z"),
             _game(2, 32, "2026-09-11T23:45:00Z", home="MIL"),
             _game(3, 12, "2026-09-11T23:10:00Z", home="TBR")]
    out = bw.capture("2026-09-11", enabled=True, source="open-meteo", games=games,
                     venues=VENUES, fetch=_stub_fetch(calls), forecast_dir=tmp_path, now=NOW)
    assert out["captured"] is True
    # ONE batched request, and the dome was never asked about
    assert len(calls) == 1 and len(calls[0]) == 2
    rec = json.loads(Path(out["path"]).read_text(encoding="utf-8"))
    rows = {r["game_pk"]: r for r in rec["rows"]}
    wr = rows[1]
    assert wr["weather_applies"] is True
    assert wr["fc_temp_f"] == 70.0
    assert wr["fc_wind_out_mph"] == pytest.approx(10.0)       # 217 from, azimuth 37: out
    assert wr["hours_used"] == ["2026-09-11T23:00", "2026-09-12T00:00", "2026-09-12T01:00"]
    assert wr["lead_hours"] == pytest.approx(4.08, abs=0.01)
    assert rows[2]["weather_applies"] is False and rows[2]["fc_temp_f"] == 70.0
    assert rows[3]["weather_applies"] is False and rows[3]["fc_temp_f"] is None
    assert rec["n_open_air_with_forecast"] == 1
    with pytest.raises(FileExistsError):
        bw.capture("2026-09-11", enabled=True, source="open-meteo", games=games,
                   venues=VENUES, fetch=_stub_fetch([]), forecast_dir=tmp_path, now=NOW)


def test_a_game_inside_the_lead_window_is_skipped_not_captured(tmp_path):
    """A capture minutes before first pitch is nearly an observation."""
    games = [_game(1, 17, "2026-09-11T18:20:00Z"),     # already under way at 19:00Z
             _game(2, 17, "2026-09-11T19:40:00Z")]     # inside MIN_LEAD_HOURS
    out = bw.capture("2026-09-11", enabled=True, source="open-meteo", games=games,
                     venues=VENUES, fetch=_stub_fetch([]), forecast_dir=tmp_path, now=NOW)
    rec = json.loads(Path(out["path"]).read_text(encoding="utf-8"))
    assert rec["rows"] == []
    assert sorted(s["game_pk"] for s in rec["skipped"]) == [1, 2]


def test_an_unknown_venue_is_a_stated_null_row(tmp_path):
    out = bw.capture("2026-09-11", enabled=True, source="open-meteo",
                     games=[_game(9, 5445, "2026-09-11T23:05:00Z")], venues=VENUES,
                     fetch=_stub_fetch([]), forecast_dir=tmp_path, now=NOW)
    row = json.loads(Path(out["path"]).read_text(encoding="utf-8"))["rows"][0]
    assert row["fc_temp_f"] is None and "not in the cached-feed venue table" in row["basis"]


# ----------------------------------------------------------------- reader
def _write(tmp, name, captured_at, pk=1, temp=70.0):
    (tmp / name).write_text(json.dumps({"captured_at": captured_at, "rows": [
        {"game_pk": pk, "captured_at": captured_at, "fc_temp_f": temp,
         "weather_applies": True}]}), encoding="utf-8")


def test_reader_returns_the_newest_row_captured_in_time_and_nothing_later(tmp_path):
    fp = "2026-09-11T23:05:00Z"
    _write(tmp_path, "2026-09-10-1900.json", "2026-09-10T19:00:00+00:00", temp=60.0)
    _write(tmp_path, "2026-09-11-1900.json", "2026-09-11T19:00:00+00:00", temp=65.0)
    # captured 30 minutes before first pitch: inside MIN_LEAD_HOURS, never used
    _write(tmp_path, "2026-09-11-2235.json", "2026-09-11T22:35:00+00:00", temp=99.0)
    r = bw.forecast_for_game(1, fp, forecast_dir=tmp_path)
    assert r["fc_temp_f"] == 65.0 and r["snapshot"] == "2026-09-11-1900.json"


def test_reader_is_none_when_only_late_captures_exist(tmp_path):
    _write(tmp_path, "2026-09-11-2300.json", "2026-09-11T23:00:00+00:00")
    assert bw.forecast_for_game(1, "2026-09-11T23:05:00Z", forecast_dir=tmp_path) is None
    assert bw.forecast_for_game(2, "2026-09-11T23:05:00Z", forecast_dir=tmp_path) is None


def test_reader_trusts_the_row_timestamp_not_the_file_name(tmp_path):
    """A file named early but holding a late capture must not leak."""
    _write(tmp_path, "2026-09-10-0100.json", "2026-09-11T23:00:00+00:00")
    assert bw.forecast_for_game(1, "2026-09-11T23:05:00Z", forecast_dir=tmp_path) is None


def test_coverage_counts_and_never_reports_a_value(tmp_path):
    assert bw.coverage(tmp_path)["clock_started"] is None
    _write(tmp_path, "2026-09-12-1900.json", "2026-09-12T19:00:00+00:00", temp=71.5)
    c = bw.coverage(tmp_path)
    assert c["clock_started"] == "2026-09-12"
    assert c["earliest_first_look"] == "2026-10-10"
    assert "71.5" not in json.dumps(c)


# ------------------------------------------------------ the 5h-C backfill
def _feed(fdir, pk, vid, name, lat, lon, az, roof, when, day):
    fdir.mkdir(parents=True, exist_ok=True)
    loc = {"azimuthAngle": az}
    if lat is not None:
        loc["defaultCoordinates"] = {"latitude": lat, "longitude": lon}
    (fdir / f"{pk}.json").write_text(json.dumps({"gameData": {
        "datetime": {"dateTime": when, "officialDate": day},
        "venue": {"id": vid, "name": name, "location": loc,
                  "fieldInfo": {"roofType": roof}}}}), encoding="utf-8")


def _result(pk, day="2026-09-09", home="CHC", away="PIT"):
    return {"game_pk": pk, "season": "2026", "date": day, "home_org": home, "away_org": away}


def _bf_stub(calls, empty=False):
    """Previous-Runs-shaped stub: a flat series over the requested UTC dates."""
    def fetch(points, d0, d1):
        calls.append((list(points), d0, d1))
        if empty:
            return [{} for _ in points], {"n_calls": 1}
        n = ((date.fromisoformat(d1) - date.fromisoformat(d0)).days + 1) * 24
        return ([_series(start=f"{d0}T00:00", hours=n) for _ in points],
                {"n_calls": 1, "endpoint": "stub"})
    return fetch


def _slate(tmp_path):
    fdir = tmp_path / "feeds"
    _feed(fdir, 11, 17, "Wrigley Field", 41.948171, -87.655503, 37.0, "Open",
          "2026-09-09T23:05:00Z", "2026-09-09")
    _feed(fdir, 12, 32, "American Family Field", 43.02838, -87.97099, 129.0, "Retractable",
          "2026-09-09T23:40:00Z", "2026-09-09")
    _feed(fdir, 13, 12, "Tropicana Field", 27.767778, -82.6525, 359.0, "Dome",
          "2026-09-09T23:10:00Z", "2026-09-09")
    _feed(fdir, 14, 5340, "Estadio Alfredo Harp Helu", None, None, None, "Open",
          "2026-09-09T22:05:00Z", "2026-09-09")
    games = [_result(11), _result(12, home="MIL"), _result(13, home="TBR"),
             _result(14, home="ARI"), _result(15, home="NYY")]   # 15: feed not cached
    return fdir, games


def test_backfill_writes_one_row_per_game_with_its_issue_time(tmp_path):
    fdir, games = _slate(tmp_path)
    store, calls = tmp_path / "store", []
    out = bw.backfill(games=games, feed_dir=fdir, fetch=_bf_stub(calls),
                      forecast_dir=store, now=BF_NOW)
    assert out["captured"] is True
    assert Path(out["path"]).name == "previous-runs-2026-09-11-2100.json"
    # ONE batched request; the dome and the venue without coordinates never asked
    assert len(calls) == 1 and len(calls[0][0]) == 2
    assert (calls[0][1], calls[0][2]) == ("2026-09-09", "2026-09-10")
    rec = json.loads(Path(out["path"]).read_text(encoding="utf-8"))
    assert rec["arm"] == "backfill" and rec["variable_suffix"] == "_previous_day1"
    rows = {r["game_pk"]: r for r in rec["rows"]}
    assert sorted(rows) == [11, 12, 13, 14]
    w = rows[11]
    assert w["arm"] == "backfill" and w["weather_applies"] is True
    assert w["fc_temp_f"] == 70.0 and w["fc_wind_out_mph"] == pytest.approx(10.0)
    assert w["hours_used"] == ["2026-09-09T23:00", "2026-09-10T00:00", "2026-09-10T01:00"]
    # the newest run behind the last hour: initialised by 01:00 - 24h, issued
    # no later than that plus the 12h allowance, i.e. 10.08h before first pitch
    assert w["run_initialised_by"] == "2026-09-09T01:00:00+00:00"
    assert w["issued_at"] == "2026-09-09T13:00:00+00:00"
    assert w["lead_hours"] == pytest.approx(10.08, abs=0.01)
    assert w["captured_at"] == BF_NOW.isoformat()          # the honest fetch time
    assert rows[12]["weather_applies"] is False and rows[12]["fc_temp_f"] == 70.0
    assert rows[13]["fc_temp_f"] is None and "dome" in rows[13]["basis"]
    assert rows[14]["fc_temp_f"] is None and "coordinates" in rows[14]["basis"]
    assert [s["game_pk"] for s in rec["skipped"]] == [15]
    for r in rec["rows"]:
        if r["issued_at"]:
            fp = bw._utc(r["first_pitch_utc"])
            assert bw._utc(r["issued_at"]) <= fp - timedelta(hours=bw.MIN_LEAD_HOURS)


def test_backfill_first_write_wins_and_only_the_unwritten_game_is_retried(tmp_path):
    fdir, games = _slate(tmp_path)
    store = tmp_path / "store"
    bw.backfill(games=games, feed_dir=fdir, fetch=_bf_stub([]), forecast_dir=store, now=BF_NOW)
    _feed(fdir, 15, 3313, "Yankee Stadium", 40.829, -73.926, 75.0, "Open",
          "2026-09-09T23:05:00Z", "2026-09-09")
    calls = []
    out = bw.backfill(games=games, feed_dir=fdir, fetch=_bf_stub(calls), forecast_dir=store,
                      now=BF_NOW + timedelta(minutes=5))
    assert out["n_already_in_store"] == 4 and out["n_games"] == 1
    assert len(calls) == 1 and len(calls[0][0]) == 1
    assert bw.backfill_game_pks(store) == {11, 12, 13, 14, 15}
    again = bw.backfill(games=games, feed_dir=fdir, fetch=_bf_stub(calls), forecast_dir=store,
                        now=BF_NOW + timedelta(minutes=10))
    assert again["captured"] is False and len(calls) == 1        # nothing new, no request


def test_backfill_retries_rather_than_retires_an_empty_series(tmp_path):
    fdir, games = _slate(tmp_path)
    store = tmp_path / "store"
    out = bw.backfill(games=games[:2], feed_dir=fdir, fetch=_bf_stub([], empty=True),
                      forecast_dir=store, now=BF_NOW)
    assert out["captured"] is False
    assert bw.backfill_game_pks(store) == set()


def test_backfill_never_writes_a_row_issued_inside_the_lead(tmp_path, monkeypatch):
    """The whole safety property of the arm, enforced on the row: widen the
    publication allowance until the bound crosses first pitch minus the lead,
    and the row is refused, not written."""
    fdir, games = _slate(tmp_path)
    monkeypatch.setattr(bw, "BACKFILL_ISSUE_ALLOWANCE_HOURS", 23.5)
    out = bw.backfill(games=games[:1], feed_dir=fdir, fetch=_bf_stub([]),
                      forecast_dir=tmp_path / "store", now=BF_NOW)
    assert out["captured"] is False and out["n_skipped"] == 1
    assert bw.backfill_game_pks(tmp_path / "store") == set()


def test_backfill_skips_a_game_whose_hours_are_not_past(tmp_path):
    fdir, games = _slate(tmp_path)
    out = bw.backfill(games=games[:1], feed_dir=fdir, fetch=_bf_stub([]),
                      forecast_dir=tmp_path / "store",
                      now=datetime(2026, 9, 10, 1, 30, tzinfo=timezone.utc))
    assert out["captured"] is False and out["n_skipped"] == 1


def test_backfill_batches_a_short_span_and_splits_a_long_one(tmp_path):
    fdir = tmp_path / "feeds"
    _feed(fdir, 21, 17, "Wrigley Field", 41.9, -87.6, 37.0, "Open", "2026-04-01T18:20:00Z",
          "2026-04-01")
    _feed(fdir, 22, 19, "Coors Field", 39.7, -104.9, 4.0, "Open", "2026-05-20T01:10:00Z",
          "2026-05-19")
    calls = []
    bw.backfill(games=[_result(21, day="2026-04-01"), _result(22, day="2026-05-19", home="COL")],
                feed_dir=fdir, fetch=_bf_stub(calls), forecast_dir=tmp_path / "store",
                now=BF_NOW)
    assert sorted((len(c[0]), c[1], c[2]) for c in calls) == [
        (1, "2026-04-01", "2026-04-01"), (1, "2026-05-20", "2026-05-20")]


@pytest.mark.parametrize("kw,why", [
    ({"capture_enabled": False}, "capture is not armed"),
    ({"enabled": False}, "BACKFILL_ENABLED"),
    ({"source": "nws"}, "no backfill arm"),
])
def test_backfill_is_inert_unless_everything_is_armed(tmp_path, kw, why):
    fdir, games = _slate(tmp_path)
    calls = []
    out = bw.backfill(games=games, feed_dir=fdir, fetch=_bf_stub(calls),
                      forecast_dir=tmp_path / "store", now=BF_NOW, **kw)
    assert out["captured"] is False and why in out["reason"]
    assert calls == [] and not (tmp_path / "store").exists()


def test_backfill_is_pinned_to_the_approved_season(tmp_path):
    """5h-C approved the 2026 season; 2027 is a new owner decision."""
    assert bw.BACKFILL_SEASONS == ("2026",)
    fdir, games = _slate(tmp_path)
    calls = []
    out = bw.backfill(games=games, feed_dir=fdir, fetch=_bf_stub(calls),
                      forecast_dir=tmp_path / "store",
                      now=datetime(2027, 4, 20, 21, 0, tzinfo=timezone.utc))
    assert out["captured"] is False and out["state"] == "inert" and "2027" in out["reason"]
    assert calls == [] and not (tmp_path / "store").exists()


def _long_slate(tmp_path, n_venues=3):
    """One game per venue on dates far enough apart that each venue is its own
    request (the first-night shape)."""
    fdir = tmp_path / "feeds"
    games = []
    for k in range(n_venues):
        day = f"2026-0{4 + k}-10"
        _feed(fdir, 100 + k, 500 + k, f"Park {k}", 40.0 + k, -80.0, 45.0, "Open",
              f"{day}T23:05:00Z", day)
        games.append(_result(100 + k, day=day))
    return fdir, games


def test_backfill_stops_its_requests_at_the_first_failure(tmp_path):
    fdir, games = _long_slate(tmp_path)
    calls = []

    def down(points, d0, d1):
        calls.append(d0)
        raise TimeoutError("archive host hung")

    out = bw.backfill(games=games, feed_dir=fdir, fetch=down, forecast_dir=tmp_path / "store",
                      now=BF_NOW)
    assert len(calls) == 1 and out["n_requests"] == 1            # not one timeout per venue
    assert out["captured"] is False
    assert out["skipped_by_code"] == {"request_deferred": 2, "request_failed": 1}
    assert bw.backfill_game_pks(tmp_path / "store") == set()     # all retried later


def test_backfill_caps_its_requests_per_night(tmp_path, monkeypatch):
    fdir, games = _long_slate(tmp_path)
    monkeypatch.setattr(bw, "BACKFILL_MAX_REQUESTS_PER_NIGHT", 2)
    calls = []
    store = tmp_path / "store"
    out = bw.backfill(games=games, feed_dir=fdir, fetch=_bf_stub(calls), forecast_dir=store,
                      now=BF_NOW)
    assert len(calls) == 2 and out["n_games"] == 2
    assert out["skipped_by_code"] == {"request_deferred": 1}
    nxt = bw.backfill(games=games, feed_dir=fdir, fetch=_bf_stub(calls), forecast_dir=store,
                      now=BF_NOW + timedelta(days=1))
    assert nxt["n_games"] == 1 and len(calls) == 3               # the deferred one, next night


def test_backfill_fetches_a_missing_feed_through_the_loader(tmp_path):
    """A pruned feed cache is refilled through the injected loader, the game's
    own feed; no fallback to the home club's park."""
    fdir, games = _slate(tmp_path)
    asked = []

    def loader(pk, day):
        asked.append((pk, day))
        return {"gameData": {
            "datetime": {"dateTime": "2026-09-09T23:05:00Z", "officialDate": "2026-09-09"},
            "venue": {"id": 3313, "name": "Yankee Stadium",
                      "location": {"azimuthAngle": 75.0,
                                   "defaultCoordinates": {"latitude": 40.829,
                                                          "longitude": -73.926}},
                      "fieldInfo": {"roofType": "Open"}}}}

    out = bw.backfill(games=games, feed_dir=fdir, fetch=_bf_stub([]), feed_loader=loader,
                      forecast_dir=tmp_path / "store", now=BF_NOW)
    assert asked == [(15, "2026-09-09")]                         # only the uncached game
    assert out["n_feed_fetches"] == 1 and out["n_skipped"] == 0
    assert 15 in bw.backfill_game_pks(tmp_path / "store")


def test_backfill_feed_fetches_stop_at_the_first_failure_and_at_the_cap(tmp_path, monkeypatch):
    fdir = tmp_path / "feeds"
    fdir.mkdir()
    games = [_result(pk) for pk in (31, 32, 33)]                 # none cached
    asked = []

    def down(pk, day):
        asked.append(pk)
        raise ConnectionError("statsapi down")

    out = bw.backfill(games=games, feed_dir=fdir, fetch=_bf_stub([]), feed_loader=down,
                      forecast_dir=tmp_path / "s1", now=BF_NOW)
    assert asked == [31]
    assert out["skipped_by_code"] == {"feed_fetch_deferred": 2, "feed_fetch_failed": 1}
    monkeypatch.setattr(bw, "BACKFILL_MAX_FEED_FETCHES_PER_NIGHT", 1)
    out = bw.backfill(games=games, feed_dir=fdir, fetch=_bf_stub([]),
                      feed_loader=lambda pk, day: {}, forecast_dir=tmp_path / "s2", now=BF_NOW)
    assert out["n_feed_fetches"] == 1
    assert out["skipped_by_code"] == {"feed_fetch_deferred": 2, "feed_not_cached": 1}


def test_a_test_feed_dir_never_reaches_the_network_loader(tmp_path, monkeypatch):
    """The default feed_cache loader is for the production cache only."""
    def boom(*a, **k):
        raise AssertionError("network loader called")

    monkeypatch.setattr(bw, "_default_feed_loader", boom)
    fdir, games = _slate(tmp_path)
    out = bw.backfill(games=games, feed_dir=fdir, fetch=_bf_stub([]),
                      forecast_dir=tmp_path / "store", now=BF_NOW)
    assert out["skipped_by_code"] == {"feed_not_cached": 1}


def test_coverage_reports_the_last_run_skips_even_when_nothing_was_written(tmp_path):
    fdir = tmp_path / "feeds"
    fdir.mkdir()
    store = tmp_path / "store"
    out = bw.backfill(games=[_result(41), _result(42)], feed_dir=fdir, fetch=_bf_stub([]),
                      forecast_dir=store, now=BF_NOW)
    assert out["captured"] is False
    lr = bw.coverage(store)["backfill"]["last_run"]
    assert lr["n_written"] == 0 and lr["skipped_by_code"] == {"feed_not_cached": 2}
    assert lr["run_at"] == BF_NOW.isoformat()
    # the state file sits outside both snapshot globs
    assert bw.snapshot_paths(store) == [] and bw.backfill_paths(store) == []
    assert all(c in bw.SKIP_CODES for c in lr["skipped_by_code"])


def test_previous_runs_url_asks_for_the_day1_archive_and_nothing_else():
    url = bw.previous_runs_url([(41.9, -87.6), (39.7, -104.9)], "2026-04-01", "2026-04-02")
    assert url.startswith("https://previous-runs-api.open-meteo.com/v1/forecast?")
    q = dict(p.split("=", 1) for p in url.split("?", 1)[1].split("&"))
    hourly = q["hourly"].split("%2C")
    assert len(hourly) == len(bw.OPEN_METEO_HOURLY)
    assert all(h.endswith("_previous_day1") for h in hourly)
    assert q["start_date"] == "2026-04-01" and q["end_date"] == "2026-04-02"
    assert "apikey" not in url
    assert bw.previous_runs_url([(1.0, 2.0)], "2026-04-01", "2026-04-01",
                                api_key="k").startswith(bw.PREVIOUS_RUNS["commercial_endpoint"])


def test_the_historical_forecast_api_is_never_an_endpoint():
    """5h bans it as a feature and as a backfill: it tracks observed weather."""
    hosts = [bw.SOURCES["open-meteo"]["endpoint"], bw.SOURCES["open-meteo"]["commercial_endpoint"],
             bw.PREVIOUS_RUNS["endpoint"], bw.PREVIOUS_RUNS["commercial_endpoint"],
             bw.open_meteo_url([(1.0, 2.0)]),
             bw.previous_runs_url([(1.0, 2.0)], "2026-04-01", "2026-04-01")]
    assert not any("historical" in h for h in hosts)


def test_previous_runs_parses_the_probed_suffixed_shape():
    """The 2026-09-11 probe: same list-of-locations shape, arrays keyed
    `<var>_previous_day1`."""
    loc = {"hourly": {"time": ["2026-07-01T00:00"],
                      "temperature_2m_previous_day1": [91.9],
                      "wind_speed_10m_previous_day1": [13.8],
                      "wind_direction_10m_previous_day1": [220]}}
    s = bw.parse_open_meteo([loc], 1, suffix="_previous_day1")[0]["2026-07-01T00:00"]
    assert (s["temp_f"], s["wind_mph"], s["wind_from_deg"]) == (91.9, 13.8, 220)
    assert bw.parse_open_meteo([loc], 1)[0]["2026-07-01T00:00"]["temp_f"] is None


def test_the_live_reader_never_returns_a_backfilled_row(tmp_path):
    """The arms never pool: a backfill file does not match the live glob, and
    its captured_at is after the game anyway."""
    fdir, games = _slate(tmp_path)
    store = tmp_path / "store"
    bw.backfill(games=games, feed_dir=fdir, fetch=_bf_stub([]), forecast_dir=store, now=BF_NOW)
    assert bw.snapshot_paths(store) == []
    assert bw.forecast_for_game(11, "2026-09-09T23:05:00Z", forecast_dir=store) is None
    r = bw.backfill_forecast_for_game(11, "2026-09-09T23:05:00Z", forecast_dir=store)
    assert r["arm"] == "backfill" and r["fc_temp_f"] == 70.0
    # the clock test is on issued_at: 10.08h of lead fails an 11h requirement
    assert bw.backfill_forecast_for_game(11, "2026-09-09T23:05:00Z", forecast_dir=store,
                                         min_lead_hours=11.0) is None
    assert bw.backfill_forecast_for_game(13, "2026-09-09T23:10:00Z", forecast_dir=store) is None


def test_backfilled_rows_never_start_the_live_clock(tmp_path):
    fdir, games = _slate(tmp_path)
    store = tmp_path / "store"
    bw.backfill(games=games, feed_dir=fdir, fetch=_bf_stub([]), forecast_dir=store, now=BF_NOW)
    c = bw.coverage(store)
    assert c["clock_started"] is None and c["n_snapshots"] == 0
    b = c["backfill"]
    assert (b["n_rows"], b["n_rows_with_forecast"], b["n_open_air_rows_with_forecast"]) == (4, 2, 1)
    assert b["n_rows_issued_inside_lead"] == 0
    assert "70.0" not in json.dumps(c)


def _agreement_store(tmp_path, second_game_day="2026-09-12"):
    store = tmp_path / "store"
    store.mkdir()
    days = {1: "2026-09-12", 2: second_game_day, 3: "2026-09-12", 4: "2026-09-12"}
    live = [{"game_pk": pk, "first_pitch_utc": f"{days[pk]}T23:05:00+00:00",
             "captured_at": f"{days[pk]}T02:00:00+00:00", "weather_applies": wa,
             "fc_temp_f": t, "fc_wind_out_mph": w}
            for pk, wa, t, w in ((1, True, 70.0, 5.0), (2, True, 60.0, -4.0),
                                 (3, True, 80.0, 0.0), (4, False, 50.0, 3.0))]
    (store / "2026-09-11-1900.json").write_text(json.dumps({"rows": live}), encoding="utf-8")
    arch = [dict(r, captured_at="2026-10-20T21:00:00+00:00", arm="backfill",
                 issued_at=r["first_pitch_utc"][:10] + "T13:00:00+00:00") for r in live]
    arch[0]["fc_temp_f"], arch[1]["fc_temp_f"] = 72.0, 61.0
    arch[1]["fc_wind_out_mph"] = 2.0                       # sign disagrees
    (store / "previous-runs-2026-10-20-2100.json").write_text(json.dumps({"rows": arch}),
                                                             encoding="utf-8")
    return store


def test_live_archive_agreement_is_weather_against_weather(tmp_path):
    """5h-C's precondition on the games both arms hold: temperature MAE and
    out-component sign agreement, open-air only. Counts and weather, no score.
    The registered share is over EVERY open-air pair, so the zero-wind pair
    counts as not agreeing; the signed-only share is reported beside it."""
    a = bw.live_archive_agreement(_agreement_store(tmp_path))
    assert a["n_pairs"] == 3 and a["temp_mae_f"] == pytest.approx(1.0)
    assert a["n_sign_agreeing"] == 1 and a["n_pairs_zero_or_null_component"] == 1
    assert a["sign_agreement"] == pytest.approx(0.3333)
    assert a["sign_agreement_signed_pairs_only"] == 0.5
    # one day of overlap is not the four weeks 5h-C names: no verdict yet
    assert a["overlap_span_days"] == 1 and a["holds"] is None
    assert bw.live_archive_agreement(tmp_path / "none")["holds"] is None


def test_live_archive_agreement_gives_a_verdict_only_after_four_weeks(tmp_path):
    assert bw.AGREEMENT_MIN_OVERLAP_DAYS == 28
    a = bw.live_archive_agreement(_agreement_store(tmp_path, second_game_day="2026-10-09"))
    assert a["overlap_span_days"] == 28
    # MAE 1.0 passes, a one-in-three sign share fails the registered 80%
    assert a["holds"] is False


# ----------------------------------------------------------- physics prior
def test_prior_is_one_at_the_reference_and_about_one_percent_per_degree():
    at_ref = bw.hr_weather_prior(72.0, ref_temp_f=72.0)
    assert at_ref["multiplier"] == 1.0
    warm = bw.hr_weather_prior(73.0, ref_temp_f=72.0)["multiplier"]
    assert warm == pytest.approx(math.exp(0.33 * math.log(1.25) / 8.5), abs=1e-5)
    assert 0.007 < warm - 1.0 < 0.012      # Nathan ~1%/F, Callahan and Mankin ~1.1%/F


def test_prior_wind_term_is_off_until_the_pass_through_is_measured():
    off = bw.hr_weather_prior(72.0, 15.0, ref_temp_f=72.0)
    assert off["multiplier"] == 1.0 and off["wind_term"].startswith("off")
    on = bw.hr_weather_prior(72.0, 10.0, ref_temp_f=72.0, pass_through=0.5)
    assert on["wind_ft"] == pytest.approx(16.0)                # 5 mph at the field, 3.2 ft/mph
    assert on["extrapolated"] is True
    inn = bw.hr_weather_prior(72.0, -10.0, ref_temp_f=72.0, pass_through=0.5)
    assert inn["wind_ft"] == pytest.approx(-17.0) and inn["multiplier"] < 1.0


def test_prior_is_one_under_a_roof():
    assert bw.hr_weather_prior(95.0, 20.0, ref_temp_f=60.0, roof_type="Dome",
                               pass_through=1.0)["multiplier"] == 1.0
    assert bw.hr_weather_prior(95.0, ref_temp_f=60.0,
                               roof_type="Retractable")["multiplier"] == 1.0


def test_total_bases_multiplier_scales_with_the_home_run_share():
    assert bw.tb_weather_multiplier(1.2, 0.0) == 1.0
    assert bw.tb_weather_multiplier(1.2, 1.0) == pytest.approx(1.2)
    assert bw.tb_weather_multiplier(1.2, 0.34) == pytest.approx(1.068)


def test_the_literature_and_policy_constants_are_the_registered_ones():
    assert bw.HR_FT_PER_DEG_F == 0.33
    assert (bw.HR_FT_PER_MPH_OUT, bw.HR_FT_PER_MPH_IN) == (3.2, 3.4)
    assert (bw.HR_SHIFT_FT, bw.HR_SHIFT_GAIN) == (8.5, 0.25)
    assert bw.MIN_LEAD_HOURS == 1.0 and bw.GAME_WINDOW_HOURS == 3 and bw.HORIZON_DAYS == 2


# ------------------------------------------------------------ dark is dark
@pytest.mark.parametrize("served", ["betting_model.py", "betting_export.py",
                                    "leaderboard_vintages.py", "betting_props_dark.py",
                                    "dfs_export.py"])
def test_nothing_served_reads_the_forecast(served):
    """5c: no served price, slot, record row or exported edge reads a dark
    column. The nightly capture step in run_monthly is the one importer."""
    p = ROOT / served
    if p.exists():
        assert "betting_weather" not in p.read_text(encoding="utf-8")


def test_the_nightly_capture_step_sits_after_the_vintage_and_before_the_prices():
    """Pinned on source order, the way test_betting_results_refresh pins 9e-pre.
    The capture must be stamped before the night's prices exist, so that a
    future candidate could have read it when the price was made."""
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    _, _, tail = src.partition("def run_daily")
    daily, _, _ = tail.partition("\ndef main")
    snap = daily.find("9e-pre. Leaderboard vintage snapshot")
    wx = daily.find("9e-pre-wx. Forecast weather capture")
    export = daily.find("from betting_export import refresh_live")
    assert -1 not in (snap, wx, export)
    assert snap < wx < export
    assert "betting_weather.run(" in daily[wx:export]
