# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

import zone_metrics
from zone_metrics import PitchRow, _build_metric_row, _metric_set


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


class _AllOutModel:
    def predict(self, features):
        return [14 for _feature in features]


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


def test_all_game_logs_merges_mlb_and_milb_splits(monkeypatch):
    def split(game_pk: int, level: str, date: str) -> dict:
        return {
            "game": {"gamePk": game_pk},
            "sport": {"abbreviation": level},
            "date": date,
        }

    responses = {
        "mlb_milb": [split(1, "AAA", "2026-05-01"), split(2, "MLB", "2026-05-22")],
        "milb_full": [split(1, "AAA", "2026-05-01"), split(3, "AAA", "2026-05-02")],
        None: [split(2, "MLB", "2026-05-22")],
    }

    def fake_get_json(_url, params=None, ttl_seconds=None):
        league = (params or {}).get("leagueListId")
        return {"stats": [{"splits": responses[league]}]}

    monkeypatch.setattr(zone_metrics, "_get_json", fake_get_json)

    logs = zone_metrics.all_game_logs(699013, 2026)

    assert [
        ((s["game"] or {})["gamePk"], (s["sport"] or {})["abbreviation"])
        for s in logs
    ] == [(1, "AAA"), (2, "MLB"), (3, "AAA")]


def test_all_game_logs_normalizes_complex_league_rok_hydrate(monkeypatch):
    def fake_get_json(url, params=None, ttl_seconds=None):
        params = params or {}
        if url.endswith("/stats"):
            return {"stats": []}
        if "sportId=16" in params.get("hydrate", ""):
            return {"people": [{"stats": [{"splits": [{
                "game": {"gamePk": 44},
                "league": {"name": "Arizona Complex League"},
                "sport": {"abbreviation": "ROK"},
                "date": "2026-06-01",
            }]}]}]}
        return {"people": [{"stats": [{"splits": []}]}]}

    monkeypatch.setattr(zone_metrics, "_get_json", fake_get_json)

    logs = zone_metrics.all_game_logs(829034, 2026)

    assert len(logs) == 1
    assert logs[0]["game"]["gamePk"] == 44
    assert logs[0]["sport"]["abbreviation"] == "CPX"


def test_metric_row_prefers_actual_zone_when_available():
    rows = [
        _pitch(1, "C"),
        _pitch(2, "F"),
        _pitch(11, "B"),
        _pitch(12, "S"),
    ]
    predicted_all_out = [11, 11, 12, 12]

    row = _build_metric_row(
        player_key="x",
        player_name="X",
        mlbam_id=1,
        season=2026,
        level="CPX",
        is_pitcher=False,
        leagues=["Arizona Complex League"],
        games=1,
        rows=rows,
        predicted=predicted_all_out,
    )

    assert row.zone_rate == 50.0
    assert row.actual_zone_rate == 50.0
    assert row.actual_in_zone_accuracy == 50.0


def test_cpx_taken_pitch_model_calibrates_missing_zone_feed():
    rows = []
    for i in range(60):
        rows.append(_pitch(None, "C"))
        rows[-1].pitch_x_gameday = 112.0 + (i % 5)
        rows[-1].pitch_y_gameday = 300.0 + (i % 5)
        rows.append(_pitch(None, "B"))
        rows[-1].pitch_x_gameday = 45.0 + (i % 5)
        rows[-1].pitch_y_gameday = 370.0 + (i % 5)

    model = zone_metrics._train_taken_pitch_zone_model(rows, min_samples=20)
    assert model is not None

    zone_like = _pitch(None, "X")
    zone_like.pitch_x_gameday = 114.0
    zone_like.pitch_y_gameday = 302.0
    out_like = _pitch(None, "X")
    out_like.pitch_x_gameday = 47.0
    out_like.pitch_y_gameday = 372.0

    predicted = zone_metrics._predict_zone_ids(
        [zone_like, out_like],
        _AllOutModel(),
        taken_pitch_model=model,
    )

    assert predicted == [5, 14]
