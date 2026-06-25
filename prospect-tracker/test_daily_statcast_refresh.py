from run_monthly import (
    _latest_statcast_log_date,
    _latest_statcast_metric_game_date,
    _statcast_logs_newer_than_metric,
)


def test_daily_statcast_detects_newer_game_log_than_cached_metric():
    metric = {
        "fetched_at": "2026-06-11",
        "pitch_movement": {
            "outings": [
                {"date": "2026-06-05", "pitches": 72},
            ],
        },
        "pitch_plot": {
            "points": [
                {"date": "2026-06-05", "pitch_type": "FF"},
            ],
        },
    }
    logs = [
        {"date": "2026-06-05", "_level": "MLB", "game": {"gamePk": 1}},
        {"date": "2026-06-11", "_level": "MLB", "game": {"gamePk": 2}},
    ]

    assert _latest_statcast_metric_game_date(metric) == "2026-06-05"
    assert _latest_statcast_log_date(logs, level_hint="MLB") == "2026-06-11"
    assert _statcast_logs_newer_than_metric(logs, metric, level_hint="MLB") is True


def test_daily_statcast_ignores_untracked_dsl_logs():
    metric = {
        "recent_games": [
            {"date": "2026-06-09"},
        ],
    }
    logs = [
        {"date": "2026-06-10", "_level": "DSL", "game": {"gamePk": 3}},
    ]

    assert _latest_statcast_log_date(logs, level_hint="DSL") is None
    assert _statcast_logs_newer_than_metric(logs, metric, level_hint="DSL") is False
