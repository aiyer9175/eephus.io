# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

from statcast_metrics import (
    _calculate_vaa_from_coords,
    _estimate_xwoba,
    _finalize_contact,
    _finalize_pitch,
    _primary_level,
)


def test_finalize_pitch_summary_and_plot_points():
    points = [
        {
            "pitch_type": "FF",
            "pitch_name": "Four-Seam Fastball",
            "velo": 96.0,
            "hb": 10.0,
            "ivb": 18.0,
            "spin": 2200,
            "extension": 6.5,
            "release_height": 5.6,
            "plate_height": 2.7,
            "vaa": -4.8,
        },
        {
            "pitch_type": "FF",
            "pitch_name": "Four-Seam Fastball",
            "velo": 98.0,
            "hb": 12.0,
            "ivb": 20.0,
            "spin": 2400,
            "extension": 6.7,
            "release_height": 5.8,
            "plate_height": 2.9,
            "vaa": -5.0,
        },
        {"pitch_type": "SL", "pitch_name": "Slider", "velo": 84.0, "hb": -6.0, "ivb": 1.0, "spin": 2300},
    ]
    movement, plot = _finalize_pitch(points, outings=[])

    assert movement["tracked_pitches"] == 3
    assert movement["pitch_summary"][0]["pitch_type"] == "FF"
    assert movement["pitch_summary"][0]["avg_velo"] == 97.0
    assert movement["pitch_summary"][0]["avg_hb"] == 11.0
    assert movement["pitch_summary"][0]["avg_extension"] == 6.6
    assert movement["pitch_summary"][0]["avg_release_height"] == 5.7
    assert movement["pitch_summary"][0]["avg_plate_height"] == 2.8
    assert movement["pitch_summary"][0]["avg_vaa"] == -4.9
    assert round(sum(p["usage_pct"] for p in movement["pitch_summary"]), 1) == 100.0
    assert len(plot["points"]) == 3


def test_calculate_vaa_from_statcast_coordinates():
    coords = {
        "vY0": -141.88051222402854,
        "vZ0": -8.358292137377004,
        "aY": 27.913067237094754,
        "aZ": -15.419559917976526,
        "y0": 50.000683758692006,
    }

    assert _calculate_vaa_from_coords(coords) == -5.98


def test_finalize_pitch_usage_sums_to_100_after_rounding():
    points = []
    for code, count in [("FF", 183), ("ST", 119), ("SL", 64), ("FS", 12), ("CH", 3), ("CU", 1)]:
        for _ in range(count):
            points.append({"pitch_type": code, "pitch_name": code, "velo": 90.0, "hb": 1.0, "ivb": 1.0, "spin": 2000, "batter_side": "L"})

    movement, _plot = _finalize_pitch(points, outings=[])

    assert sum(p["count"] for p in movement["pitch_summary"]) == 382
    assert round(sum(p["usage_pct"] for p in movement["pitch_summary"]), 1) == 100.0
    assert round(sum(p["usage_by_batter_side"]["L"]["usage_pct"] for p in movement["pitch_summary"]), 1) == 100.0


def test_finalize_contact_quality_for_pitcher_allowed():
    rows = [
        {"launch_speed": 100.0, "launch_angle": 28.0},
        {"launch_speed": 90.0, "launch_angle": 5.0},
    ]
    cq = _finalize_contact(rows, is_pitcher=True)

    assert cq["batted_balls"] == 2
    assert cq["avg_ev"] == 95.0
    assert cq["max_ev"] == 100.0
    assert cq["p90_ev"] is not None
    assert cq["hard_hit_pct"] == 50.0
    assert cq["barrel_pct"] == 50.0
    assert cq["direction"] == "allowed"


def test_finalize_contact_adds_spray_locations_and_rolling_xwoba():
    rows = []
    for i in range(30):
        rows.append({
            "game_pk": 1000 + i,
            "date": f"2026-05-{(i % 28) + 1:02d}",
            "launch_speed": 92.0 + (i % 6),
            "launch_angle": 12.0 + (i % 12),
            "coord_x": 70.0 if i % 3 == 0 else (125.0 if i % 3 == 1 else 180.0),
            "coord_y": 85.0,
            "hit_type": "single" if i % 5 else "home_run",
            "batter_side": "R",
        })

    cq = _finalize_contact(rows, is_pitcher=False)

    assert cq["batted_balls"] == 30
    assert cq["xwoba_est"] is not None
    assert cq["spray"]["pull_pct"] > 0
    assert cq["spray"]["pull_air_pct"] > 0
    assert len(cq["hit_locations"]) == 30
    assert cq["hit_locations"][0]["spray"] in {"pull", "center", "oppo"}
    assert len(cq["rolling_xwoba"]) > 0


def test_pull_air_pct_uses_total_batted_balls_denominator():
    rows = [
        {"launch_speed": 95.0, "launch_angle": 20.0, "coord_x": 70.0, "coord_y": 85.0, "batter_side": "R", "hit_type": "FlyBall"},
        {"launch_speed": 90.0, "launch_angle": -6.0, "coord_x": 70.0, "coord_y": 85.0, "batter_side": "R", "hit_type": "GroundBall"},
        {"launch_speed": 88.0, "launch_angle": 18.0, "coord_x": 125.0, "coord_y": 85.0, "batter_side": "R", "hit_type": "FlyBall"},
        {"launch_speed": 91.0, "launch_angle": 22.0, "coord_x": 180.0, "coord_y": 85.0, "batter_side": "R", "hit_type": "FlyBall"},
        {"launch_speed": 93.0, "launch_angle": 5.0, "coord_x": 70.0, "coord_y": 85.0, "batter_side": "R", "hit_type": "LineDrive"},
        {"launch_speed": 82.0, "launch_angle": 60.0, "coord_x": 70.0, "coord_y": 85.0, "batter_side": "R", "hit_type": "Popup"},
    ]

    cq = _finalize_contact(rows, is_pitcher=False)

    assert cq["spray"]["pull_air_bbe"] == 3
    assert cq["spray"]["air_bbe"] == 5
    assert cq["spray"]["pull_air_pct"] == 50.0


def test_soft_contact_profile_does_not_pop_as_power_xwoba():
    rows = []
    for i in range(25):
        rows.append({
            "launch_speed": 82.0 + (i % 7),
            "launch_angle": 10.0 + (i % 10),
            "date": "2026-05-01",
        })
    rows.extend([
        {"launch_speed": 97.0, "launch_angle": 16.0, "date": "2026-05-02"},
        {"launch_speed": 99.0, "launch_angle": 5.0, "date": "2026-05-02"},
        {"launch_speed": 78.0, "launch_angle": -4.0, "date": "2026-05-02"},
        {"launch_speed": 84.0, "launch_angle": 22.0, "date": "2026-05-02"},
        {"launch_speed": 86.0, "launch_angle": 14.0, "date": "2026-05-02"},
    ])

    cq = _finalize_contact(rows, is_pitcher=False)

    assert cq["avg_ev"] < 86.0
    assert cq["hard_hit_pct"] < 30.0
    assert cq["barrel_pct"] <= 2.0
    assert cq["xwobacon_adjustment"] < 0
    assert cq["xwobacon_est"] < 0.340


def test_xwoba_knn_contact_surface_for_moderate_line_drive_profile():
    # Regression for Ralphy Velazquez's 2026 Statcast feed shape: the old
    # linear formula averaged .471 on these same EV/LA pairs, far above
    # Prospect Savant's .335 estimate.
    pairs = [
        (93.8, -8.0), (90.2, 15.0), (92.0, -3.0), (80.8, -5.0),
        (84.6, -37.0), (94.5, -2.0), (80.0, -10.0), (105.1, 10.0),
        (77.2, -32.0), (104.4, 11.0), (106.8, 3.0), (103.1, 24.0),
        (85.9, -13.0), (86.1, 10.0), (104.8, 25.0), (81.7, -15.0),
        (79.6, -16.0), (98.6, 13.0), (107.3, -5.0), (77.4, -36.0),
        (99.2, 45.0), (88.8, 48.0), (100.3, 8.0), (77.1, -21.0),
        (92.7, 54.0), (89.2, 43.0), (101.2, 26.0), (63.7, -52.0),
    ]
    vals = [_estimate_xwoba(ev, la) for ev, la in pairs]

    # KNN contact-only estimate; export folds in BB/K rates to produce
    # the PA-level xwOBA shown in the UI.
    assert round(sum(vals) / len(vals), 3) == 0.357


def test_finalize_contact_keeps_contact_only_estimate_available():
    rows = [
        {"launch_speed": ev, "launch_angle": la, "date": "2026-05-01"}
        for ev, la in [
            (93.8, -8.0), (90.2, 15.0), (92.0, -3.0), (80.8, -5.0),
            (84.6, -37.0), (94.5, -2.0), (80.0, -10.0), (105.1, 10.0),
            (77.2, -32.0), (104.4, 11.0), (106.8, 3.0), (103.1, 24.0),
            (85.9, -13.0), (86.1, 10.0), (104.8, 25.0), (81.7, -15.0),
            (79.6, -16.0), (98.6, 13.0), (107.3, -5.0), (77.4, -36.0),
            (99.2, 45.0), (88.8, 48.0), (100.3, 8.0), (77.1, -21.0),
            (92.7, 54.0), (89.2, 43.0), (101.2, 26.0), (63.7, -52.0),
        ]
    ]
    cq = _finalize_contact(rows, is_pitcher=False)

    assert cq["xwoba_est"] == 0.357
    assert cq["xwobacon_est"] == 0.357
    assert cq["p90_ev"] == 104.9


def test_primary_level_uses_hint_when_present_otherwise_largest_split():
    logs = [{"_level": "A"}, {"_level": "A"}, {"_level": "A+"}]

    assert _primary_level(logs, "A+") == "A+"
    assert _primary_level(logs, "AA") == "A"
