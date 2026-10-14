# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EFV5_TRACKING_FETCH contracts: the fetch stays polite, resumable and inside its
own cache folder; the per-pitch definitions match the module docstring; the aStuff+
features are the served model's own; the coverage artifact carries no FV cell and
no outcome. No test touches the network."""

from __future__ import annotations

import gzip
import json
import urllib.error
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest

import efv5_tracking as T
import stuff_plus_aaa as spa


def _pitch(**kw):
    base = {"pitch_type": "FF", "game_date": "2024-06-04", "release_speed": 95.0,
            "release_pos_x": -2.0, "release_pos_z": 5.8, "batter": 1, "pitcher": 9,
            "events": "", "description": "ball", "zone": 12, "stand": "R",
            "p_throws": "R", "home_team": "TAC", "away_team": "RNO", "type": "B",
            "bb_type": None, "pfx_x": -0.5, "pfx_z": 1.4, "plate_x": 0.0,
            "plate_z": 2.5, "launch_speed": None, "launch_angle": None,
            "release_spin_rate": 2400, "release_extension": 6.5, "game_pk": 7,
            "estimated_woba_using_speedangle": None, "woba_value": None,
            "woba_denom": None, "launch_speed_angle": None, "delta_run_exp": 0.0,
            "bat_speed": None, "age_pit": 22, "age_bat": 21, "arm_angle": 35.0,
            "game_year": 2024, "level": "AAA"}
    base.update(kw)
    return base


@pytest.fixture
def frame():
    rows = [
        _pitch(description="called_strike", zone=5),
        _pitch(description="swinging_strike", zone=13),
        _pitch(description="foul", zone=5),
        _pitch(description="foul_tip", zone=4, events="strikeout",
               woba_value=0.0, woba_denom=1),
        _pitch(description="ball", zone=14, pitch_type="SL", release_speed=85.0),
        _pitch(description="swinging_strike", zone=14, pitch_type="SL",
               release_speed=86.0),
        _pitch(description="hit_into_play", zone=5, type="X", events="single",
               bb_type="ground_ball", launch_speed=100.0, launch_angle=10.0,
               launch_speed_angle=4, estimated_woba_using_speedangle=0.5,
               woba_value=0.9, woba_denom=1),
        _pitch(description="hit_into_play", zone=6, type="X", events="home_run",
               bb_type="fly_ball", launch_speed=105.0, launch_angle=28.0,
               launch_speed_angle=6, estimated_woba_using_speedangle=1.5,
               woba_value=2.0, woba_denom=1),
        # an untracked pitch: call counts, kinematics and zone do not
        _pitch(description="ball", zone=None, release_speed=None, plate_x=None,
               pfx_x=None, pfx_z=None, events="walk", woba_value=0.7,
               woba_denom=1),
    ]
    return T.annotate(pd.DataFrame(rows))


def test_pitcher_definitions(frame):
    (r,) = T.pitcher_rows(frame)
    assert (r["mlbam"], r["season"], r["level"]) == (9, 2024, "AAA")
    assert r["pitches"] == 9 and r["tracked_pitches"] == 8
    # CSW = (1 called + 3 whiffs incl. foul tip) / 9
    assert r["csw"] == round(4 / 9, 4)
    # swings: swinging x2, foul, foul tip, two in play = 6; whiffs 3
    assert r["whiff"] == round(3 / 6, 4)
    # zone over tracked pitches: zones 5,5,4,5,6 in = 5 of 8
    assert r["zone"] == round(5 / 8, 4)
    # chase: out-of-zone 13,14,14 = 3; swung at 2
    assert r["chase"] == round(2 / 3, 4)
    # xwOBA: K 0, BBE 0.5 and 1.5 (speed-angle, not the realized value), the
    # walk is untracked so it leaves numerator and denominator
    assert r["xwoba_against"] == round(2.0 / 3, 3) and r["xwoba_pa"] == 3
    assert r["ev_against"] == 102.5
    assert r["gb"] == 0.5
    assert r["k_pct"] == round(1 / 4, 4) and r["bb_pct"] == round(1 / 4, 4)
    assert r["fb_primary"] == "FF" and r["fb_velo_mean"] == 95.0
    # ride in inches, run arm side positive (RHP pfx_x -0.5 ft = 6 in arm side)
    assert r["fb_ivb"] == round(1.4 * 12, 2) and r["fb_hb_arm"] == 6.0
    assert r["whiff_br"] == 1.0 and r["arm_angle"] == 35.0


def test_hitter_definitions(frame):
    (r,) = T.hitter_rows(frame)
    assert r["bbe"] == 2 and r["ev_mean"] == 102.5 and r["ev_max"] == 105.0
    assert r["hard_hit"] == 1.0 and r["barrel"] == 0.5
    assert r["sweet_spot"] == 1.0          # 10 and 28 degrees both inside 8 to 32
    assert r["bat_speed"] is None


def test_sweet_spot_bounds():
    df = T.annotate(pd.DataFrame([
        _pitch(type="X", description="hit_into_play", launch_speed=90.0,
               launch_angle=la, events="field_out", woba_denom=1, woba_value=0.0)
        for la in (7.9, 8.0, 32.0, 32.1)]))
    (r,) = T.hitter_rows(df)
    assert r["sweet_spot"] == 0.5


def test_lefty_run_is_arm_side_positive():
    df = T.annotate(pd.DataFrame([_pitch(p_throws="L", pfx_x=0.5)]))
    assert float(df["hb_arm_in"].iat[0]) == 6.0


def test_astuff_features_match_served_featurize():
    """The applied model must see exactly the features it was trained on."""
    rows = [_pitch(release_speed=96.0), _pitch(pitch_type="SL", release_speed=86.0,
                                               pfx_x=0.3, arm_angle=None),
            _pitch(p_throws="L", release_speed=92.0, pfx_x=0.6, release_pos_x=1.9,
                   pitcher=10, release_spin_rate=None),
            # a stored zero takes the served default, as `_f(v) or default` does
            _pitch(pitcher=11, release_speed=90.0, arm_angle=0.0,
                   release_extension=0.0, release_pos_z=0.0)]
    df = pd.DataFrame(rows)
    mask, X = T.astuff_features(df)
    assert mask.all() and X.shape == (4, len(spa.FEATURES))
    for i, r in enumerate(rows):
        s = {k: ("" if v is None else str(v)) for k, v in r.items()}
        prim = max(x["release_speed"] for x in rows if x["pitcher"] == r["pitcher"])
        want, _lab = spa._featurize(s, prim)
        assert np.allclose(X[i], np.asarray(want)), (i, X[i], want)


def test_astuff_scale_direction_and_pool():
    rows = [{"season": 2025, "level": "AAA", "xrv_mean": 0.001 * i, "xrv_n": 400}
            for i in range(-15, 16)]
    rows.append({"season": 2023, "level": "A", "xrv_mean": -0.02, "xrv_n": 50})
    sc = T.astuff_scale(rows)
    assert sc["pool_n"] == 31
    best = min(rows[:-1], key=lambda r: r["xrv_mean"])
    worst = max(rows[:-1], key=lambda r: r["xrv_mean"])
    assert best["astuff_plus"] > 100 > worst["astuff_plus"]   # lower RV = better
    assert rows[-1]["astuff_plus"] > 100


def test_blackout_window():
    assert T.in_blackout(datetime(2026, 10, 14, 6, 0, tzinfo=timezone.utc))
    assert T.in_blackout(datetime(2026, 10, 14, 10, 59, tzinfo=timezone.utc))
    assert not T.in_blackout(datetime(2026, 10, 14, 11, 0, tzinfo=timezone.utc))
    assert not T.in_blackout(datetime(2026, 10, 14, 5, 59, tzinfo=timezone.utc))


def test_backoff_on_429_then_success(monkeypatch):
    monkeypatch.setattr(T, "in_blackout", lambda now=None: False)
    monkeypatch.setattr(T, "THROTTLE_S", 0.0)
    calls, slept = [], []

    def opener(url, timeout):
        calls.append(url)
        if len(calls) < 3:
            raise urllib.error.HTTPError(url, 429 if len(calls) == 1 else 503,
                                         "x", {}, None)
        return b"ok"

    assert T.http_get("u", opener=opener, sleep=slept.append) == b"ok"
    assert slept == [T.BACKOFF_S, T.BACKOFF_S * 2]


def test_404_is_not_retried(monkeypatch):
    monkeypatch.setattr(T, "in_blackout", lambda now=None: False)
    monkeypatch.setattr(T, "THROTTLE_S", 0.0)

    def opener(url, timeout):
        raise urllib.error.HTTPError(url, 404, "x", {}, None)

    with pytest.raises(urllib.error.HTTPError):
        T.http_get("u", opener=opener, sleep=lambda s: None)


def test_fetch_day_is_resumable_and_confined(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "DAYS_DIR", tmp_path / "days")
    body = ("pitch_type,game_date,pitcher,batter,des\nFF,2024-06-04,9,1,x\n").encode()
    got = []

    def getter(url):
        got.append(url)
        return body

    d = date(2024, 6, 4)
    assert T.fetch_day(d, getter=getter) == ("fetched", 1)
    assert T.fetch_day(d, getter=getter) == ("cached", -1)
    assert len(got) == 1 and "game_date_gt=2024-06-04" in got[0]
    gz, _empty = T.day_paths(d)
    with gzip.open(gz, "rt", encoding="utf-8") as fh:
        head = fh.readline().strip().split(",")
    assert head == list(T.KEEP)            # dropped columns never land
    assert T.fetch_day(date(2024, 1, 2), getter=lambda u: b"") == ("empty", 0)


def test_probe_day_is_a_wednesday_near_mid_june():
    for s in T.PROBE_SEASONS:
        d = T.probe_day(s)
        assert d.weekday() == 2 and date(s, 6, 9) <= d <= date(s, 6, 15)


def test_bat_speed_note_is_derived():
    assert "empty" in T._bat_speed_note({"2025": {"bat_speed": 0.0}})
    note = T._bat_speed_note({"2025": {"bat_speed": 0.0}, "2026": {"bat_speed": 0.4}})
    assert "2026 0.4" in note


def test_cache_paths_are_task_owned():
    for p in (T.CACHE_DIR, T.DAYS_DIR, T.SCHED_DIR, T.TABLE_DIR):
        assert p.relative_to(T.ROOT / ".cache").parts[0].startswith("efv5_")
    assert T.WORKERS <= 4


def test_coverage_artifact_shape():
    if not T.COVERAGE_PATH.exists():
        pytest.skip("tracking_coverage.json not built on this machine")
    d = json.loads(T.COVERAGE_PATH.read_text(encoding="utf-8"))
    cells = d["by_level_season_side"]
    assert cells and {c["side"] for c in cells} == {"pitcher", "hitter"}
    for c in cells:
        assert c["tracked_pitches"] <= c["pitches"]
        assert c["rows_qualified"] <= c["rows"]
        assert 2021 <= c["season"]
    text = json.dumps(d).lower()
    # development census only: no FV cell, no consensus, no realized WAR
    for banned in ("fv_cell", "consensus_fv", "realized_war", "war_mean"):
        assert banned not in text
    assert chr(0x2014) not in text
