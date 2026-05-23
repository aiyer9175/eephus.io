from statcast_metrics import _finalize_contact, _finalize_pitch, _primary_level


def test_finalize_pitch_summary_and_plot_points():
    points = [
        {"pitch_type": "FF", "pitch_name": "Four-Seam Fastball", "velo": 96.0, "hb": 10.0, "ivb": 18.0, "spin": 2200},
        {"pitch_type": "FF", "pitch_name": "Four-Seam Fastball", "velo": 98.0, "hb": 12.0, "ivb": 20.0, "spin": 2400},
        {"pitch_type": "SL", "pitch_name": "Slider", "velo": 84.0, "hb": -6.0, "ivb": 1.0, "spin": 2300},
    ]
    movement, plot = _finalize_pitch(points, outings=[])

    assert movement["tracked_pitches"] == 3
    assert movement["pitch_summary"][0]["pitch_type"] == "FF"
    assert movement["pitch_summary"][0]["avg_velo"] == 97.0
    assert movement["pitch_summary"][0]["avg_hb"] == 11.0
    assert round(sum(p["usage_pct"] for p in movement["pitch_summary"]), 1) == 100.0
    assert len(plot["points"]) == 3


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
    assert cq["hard_hit_pct"] == 50.0
    assert cq["barrel_pct"] == 50.0
    assert cq["direction"] == "allowed"


def test_primary_level_uses_hint_when_present_otherwise_largest_split():
    logs = [{"_level": "A"}, {"_level": "A"}, {"_level": "A+"}]

    assert _primary_level(logs, "A+") == "A+"
    assert _primary_level(logs, "AA") == "A"
