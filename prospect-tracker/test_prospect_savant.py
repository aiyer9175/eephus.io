from __future__ import annotations

from prospect_savant import attach_prospect_savant, load_prospect_savant
from spotlights import build_spotlights


def test_loads_and_attaches_prospect_savant_csv(tmp_path):
    (tmp_path / "ps_aaa_hitters.csv").write_text(
        "Name,Org,Pos,Age,PA,PS Score,EV,Max EV,90th% EV,Hard Hit%,BB%,K%,BA,OBP,SLG,HR\n"
        "Walker Jenkins,MIN,OF,21,111,0.997,92.2,112.3,107.2,44.4,17.1,16.2,.256,.396,.389,2\n",
        encoding="utf-8",
    )
    metrics = load_prospect_savant(tmp_path)
    assert ("walker jenkins", "MIN") in metrics
    assert metrics[("walker jenkins", "MIN")]["max_ev"] == 112.3

    players = [{"player_name": "Walker Jenkins", "org": "MIN"}]
    assert attach_prospect_savant(players, tmp_path) == 1
    assert players[0]["prospect_savant"]["ps_score"] == 0.997


def test_underlying_metrics_push_surface_miss_into_hot_and_rebounder():
    player = {
        "player_key": "george_lombard_jr",
        "player_name": "George Lombard Jr.",
        "position": "SS",
        "org": "NYY",
        "age": 20.0,
        "overall_rank": 16,
        "fv_low": 50.0,
        "age_vs_level": {"tier": "very-young", "diff": -4.0},
        "points": [
            {"consensus_fv_raw": 58.0, "consensus_fv_label": "58"},
            {"consensus_fv_raw": 54.0, "consensus_fv_label": "54"},
        ],
        "statline": {
            "level": "AAA",
            "season": 2026,
            "is_pitcher": False,
            "is_prior_season": False,
            "avg": ".153",
            "obp": ".359",
            "slg": ".153",
            "ops": ".512",
            "hr": 0,
            "sb": 3,
            "bb_pct": 21.8,
            "k_pct": 15.4,
        },
        "career_stats": [
            {"season": 2026, "level": "AAA", "ab": 59, "ops": ".512", "is_pitcher": False},
        ],
        "acquisition": {"method": "draft", "pick_overall": 26, "bonus_usd": 3_300_000},
        "prospect_savant": {
            "role": "hitter",
            "level": "AAA",
            "ps_score": 0.983,
            "ev": 91.7,
            "max_ev": 109.1,
            "ev_90": 104.5,
            "hard_hit_pct": 48.9,
        },
    }
    out = build_spotlights([player], [])
    assert [x["player_name"] for x in out["hot"]] == ["George Lombard Jr."]
    assert [x["player_name"] for x in out["rebounders"]] == ["George Lombard Jr."]
    assert "104.5 mph 90th EV" in out["hot"][0]["drivers"]
    assert all("PS Score" not in d for d in out["hot"][0]["drivers"])
