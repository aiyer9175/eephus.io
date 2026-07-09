# ELO data contract

The exported table is the stable boundary between the team luck/variance model
and downstream ELO modeling. It contains one row per team-game.

| Field | Type | Definition |
| --- | --- | --- |
| `team_id` | string | Stable identifier for the team. |
| `team_abbr` | string | Team abbreviation used for readable joins and inspection. |
| `season` | integer | Season associated with the team-game. |
| `game_date` | datetime | Date of the game. |
| `game_id` | string | Stable identifier for the game. |
| `luck_runs` | float | Estimated short-term run impact from non-persistent team luck. |
| `variance_runs` | float | Estimated run impact from short-term variance components. |
| `injury_context_index` | float | Team-level context index derived from roster health/injury model outputs. |
| `roster_health_index` | float | Aggregate roster availability/health index. |
| `schedule_variance_index` | float | Schedule, travel, rest, weather, or other context volatility, if available. |
| `expected_win_delta` | float | Estimated team-game win probability adjustment for ELO. |
| `confidence` | float | Model confidence between 0 and 1, inclusive. |
| `model_version` | string | Version string for reproducibility. |

Exports reject player-level or medical-detail fields. Consumers should depend
on this table and `load_elo_features`, not on internal model outputs.
