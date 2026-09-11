"""Forecast weather capture (docs/diamond-betting.md 5h). DARK, ships OFF.

Every test here is about whether the CAPTURE and the READER do what they claim.
None of them relates a forecast to a game outcome, because 5c rule 1
disqualifies a candidate measured before its clock, and the 5h clock has not
started. Offline: every request is an injected stub, every write is tmp_path.
"""
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import betting_weather as bw

ROOT = Path(__file__).resolve().parent
NOW = datetime(2026, 9, 11, 19, 0, tzinfo=timezone.utc)

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
def test_the_capture_ships_off_and_names_no_source():
    """A new external dependency is an owner decision. Flipping it is one
    commit that changes this pin on purpose."""
    assert bw.FORECAST_CAPTURE_ENABLED is False
    assert bw.FORECAST_SOURCE is None
    assert bw.WIND_PASS_THROUGH is None


def test_inert_by_default_makes_no_request_and_writes_nothing(tmp_path):
    calls = []
    out = bw.capture("2026-09-11", games=[_game(1, 17, "2026-09-11T23:05:00Z")],
                     venues=VENUES, fetch=_stub_fetch(calls), forecast_dir=tmp_path, now=NOW)
    assert out["captured"] is False and out["state"] == "inert"
    assert "FORECAST_CAPTURE_ENABLED" in out["reason"]
    assert calls == []
    assert list(tmp_path.iterdir()) == []


def test_enabled_without_a_chosen_source_is_still_inert(tmp_path):
    """The flag alone must not silently pick a licence."""
    calls = []
    out = bw.capture("2026-09-11", enabled=True, games=[_game(1, 17, "2026-09-11T23:05:00Z")],
                     venues=VENUES, fetch=_stub_fetch(calls), forecast_dir=tmp_path, now=NOW)
    assert out["captured"] is False and "FORECAST_SOURCE" in out["reason"]
    assert calls == []


def test_run_never_raises_and_is_inert_by_default():
    out = bw.run()
    assert out["captured"] is False


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
