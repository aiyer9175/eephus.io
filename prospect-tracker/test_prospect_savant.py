# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

from __future__ import annotations

from prospect_savant import attach_prospect_savant, load_prospect_savant


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
