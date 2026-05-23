from __future__ import annotations

from spotlights import build_spotlights


def _player(
    key: str,
    name: str,
    *,
    rank: int,
    fv: float = 45.0,
    low_fv: float = 40.0,
    ops: str = ".900",
    prior_ops: str = ".650",
    acq: dict | None = None,
    age: float = 20.0,
    prior_top100_sources: int = 0,
) -> dict:
    per_source = {}
    for i in range(prior_top100_sources):
        per_source[f"source_{i}"] = {"rank": 50}
    return {
        "player_key": key,
        "player_name": name,
        "position": "SS",
        "org": "ARI",
        "age": age,
        "overall_rank": rank,
        "fv_low": low_fv,
        "age_vs_level": {"tier": "young", "diff": -1.5},
        "points": [
            {"snapshot_date": "2025-02-01", "consensus_fv_raw": low_fv, "consensus_fv_label": str(int(low_fv))},
            {"snapshot_date": "2025-07-01", "consensus_fv_raw": low_fv, "consensus_fv_label": str(int(low_fv)), "per_source": per_source},
            {"snapshot_date": "2026-05-01", "consensus_fv_raw": fv, "consensus_fv_label": str(int(fv))},
        ],
        "statline": {
            "level": "AA",
            "season": 2026,
            "is_pitcher": False,
            "is_prior_season": False,
            "avg": ".300",
            "obp": ".390",
            "slg": ".510",
            "ops": ops,
            "hr": 6,
            "sb": 5,
            "bb_pct": 11.0,
            "k_pct": 17.0,
        },
        "career_stats": [
            {"season": 2026, "level": "AA", "ab": 120, "ops": ops, "hr": 6, "sb": 5, "is_pitcher": False},
            {"season": 2025, "level": "A+", "ab": 220, "ops": prior_ops, "is_pitcher": False},
        ],
        "acquisition": acq,
        "statcast": None,
        "pitch_arsenal": None,
    }


def test_kayson_cunningham_style_profile_is_rebounder():
    p = _player(
        "kayson_cunningham",
        "Kayson Cunningham",
        rank=224,
        fv=45,
        low_fv=35,
        ops=".917",
        prior_ops=".650",
        acq={
            "method": "draft",
            "pick_overall": 18,
            "bonus_usd": 4_581_900,
        },
    )
    out = build_spotlights([p], [])
    names = [x["player_name"] for x in out["rebounders"]]
    assert "Kayson Cunningham" in names


def test_ethan_salas_style_profile_can_rebound_despite_top100_rank():
    p = _player(
        "ethan_salas",
        "Ethan Salas",
        rank=17,
        fv=57.5,
        low_fv=50,
        ops=".881",
        prior_ops=".599",
        acq={"method": "international_fa"},
    )
    out = build_spotlights([p], [])
    names = [x["player_name"] for x in out["rebounders"]]
    assert "Ethan Salas" in names


def test_spotlights_export_keys():
    """v16 — Spotlights exports three buckets (risers / rebounders /
    fallers) plus a legacy `hot` alias kept for one rebuild cycle so
    older cached frontends still render. The `possible_regressors`
    bucket was dropped in v16 — it never populated meaningfully and
    was just empty noise on the UI."""
    out = build_spotlights([], [])
    assert set(out) == {"risers", "rebounders", "fallers", "hot"}


def test_stable_multi_source_top100_player_is_not_rebounder():
    p = _player(
        "walker_jenkins",
        "Walker Jenkins",
        rank=23,
        fv=52,
        low_fv=50,
        ops=".900",
        prior_ops=".700",
        prior_top100_sources=2,
        acq={"method": "draft", "pick_overall": 5, "bonus_usd": 7_144_200},
    )
    out = build_spotlights([p], [])
    assert "Walker Jenkins" not in [x["player_name"] for x in out["rebounders"]]


def test_back_of_top100_to_middle_top100_can_rebound():
    p = _player(
        "ethan_salas",
        "Ethan Salas",
        rank=17,
        fv=54,
        low_fv=50,
        ops=".881",
        prior_ops=".599",
        prior_top100_sources=0,
        acq={"method": "international_fa"},
    )
    p["points"] = [
        {
            "snapshot_date": "2026-01-22",
            "consensus_fv_raw": 58.0,
            "consensus_fv_label": "58",
            "avg_rank": 94,
            "per_source": {"tjstats": {"rank": 94}},
        },
        {
            "snapshot_date": "2026-03-04",
            "consensus_fv_raw": 50.0,
            "consensus_fv_label": "50",
            "avg_rank": 100,
            "per_source": {"just_baseball": {"rank": 100}},
        },
        {
            "snapshot_date": "2026-05-17",
            "consensus_fv_raw": 54.0,
            "consensus_fv_label": "54",
            "avg_rank": 58,
            "per_source": {"fangraphs": {"rank": 108}, "tjstats": {"rank": 7}},
        },
    ]
    p["fv_high"] = 60.0
    out = build_spotlights([p], [])
    names = [x["player_name"] for x in out["rebounders"]]
    assert "Ethan Salas" in names
    # v15 — drivers now dicts with .label, not raw strings.
    assert any("rank up" in (d.get("label") if isinstance(d, dict) else str(d))
               for d in out["rebounders"][0]["drivers"])


def test_age_25_plus_player_is_not_rebounder():
    p = _player(
        "older_breakout",
        "Older Breakout",
        rank=250,
        age=25.1,
        fv=45,
        low_fv=35,
        ops="1.000",
        prior_ops=".650",
        acq={"method": "draft", "pick_overall": 80, "bonus_usd": 1_200_000},
    )
    out = build_spotlights([p], [])
    assert "Older Breakout" not in [x["player_name"] for x in out["rebounders"]]
