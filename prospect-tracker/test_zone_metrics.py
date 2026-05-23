from zone_metrics import PitchRow, _metric_set


def _pitch(zone: int, code: str) -> PitchRow:
    return PitchRow(
        game_pk=1,
        batter_id=10,
        batter_name="Test Hitter",
        pitcher_id=20,
        pitcher_name="Test Pitcher",
        pitch_x_gameday=120.0,
        pitch_y_gameday=170.0,
        k_zone_top=3.4,
        k_zone_bot=1.6,
        actual_zone=zone,
        call_code=code,
    )


def test_metric_set_zone_swing_contact_and_whiff_rates():
    rows = [
        (_pitch(5, "C"), 5),    # zone take
        (_pitch(2, "F"), 2),    # zone contact
        (_pitch(4, "S"), 4),    # zone whiff
        (_pitch(11, "B"), 11),  # out-zone take
        (_pitch(12, "X"), 12),  # out-zone contact
        (_pitch(14, "W"), 14),  # out-zone whiff
    ]

    metrics = _metric_set(rows, use_predicted=True)

    assert metrics["zone_rate"] == 50.0
    assert metrics["z_swing_pct"] == 66.7
    assert metrics["o_swing_pct"] == 66.7
    assert metrics["z_contact_pct"] == 50.0
    assert metrics["o_contact_pct"] == 50.0
    assert metrics["overall_contact_pct"] == 50.0
    assert metrics["whiff_pct"] == 50.0
