# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Logic tests for the CollegeSavant NCAA box-score expansion.

The expansion itself renders stats.ncaa.org via headless Chrome, which cannot run
in CI, so this covers the pure logic that decides what gets written and how:
  - the confidence threshold that maps a CS team code to a school (and rejects
    name collisions / weak pluralities), and
  - the NCAA-payload -> player-page box conversion, including the percent ->
    decimal rescale that would otherwise render a 1250% walk rate.
The live render + population is validated on the next real run_monthly.
"""
from __future__ import annotations

import college_stats as cs
import college_translation as ct


def test_learn_code_schools_confidence(monkeypatch):
    # Controlled draft universe: name -> school. GEO_BUL gets a clear Georgia
    # majority; OSU_BUC gets a single colliding "Arkansas" vote; MIN_GOL gets none.
    fake = {
        "p1": {"player_name": "Aaa Georgia", "school": "Georgia"},
        "p2": {"player_name": "Bbb Georgia", "school": "Georgia"},
        "p3": {"player_name": "Ccc Georgia", "school": "Georgia"},
        "p4": {"player_name": "Ddd Glue", "school": "Georgia Gwinnett"},
        "p5": {"player_name": "Eee Collide", "school": "Arkansas"},
    }
    monkeypatch.setattr(cs, "load_draft_players", lambda: fake)
    by_code = {
        "GEO_BUL": [{"name": "Aaa Georgia"}, {"name": "Bbb Georgia"},
                    {"name": "Ccc Georgia"}, {"name": "Ddd Glue"}, {"name": "Zzz Untracked"}],
        "OSU_BUC": [{"name": "Eee Collide"}, {"name": "Yyy Untracked"}],
        "MIN_GOL": [{"name": "Nobody Here"}],
    }
    out = cs._learn_code_schools(by_code)
    assert out.get("GEO_BUL") == "Georgia", "a clear majority should resolve"
    assert "OSU_BUC" not in out, "a single colliding vote must be rejected"
    assert "MIN_GOL" not in out, "no votes -> unresolved"


def test_learn_code_schools_weak_plurality_rejected(monkeypatch):
    # 2 of 5 votes for the top school (40% < 60% share) must be rejected.
    fake = {
        "a": {"player_name": "One Duck", "school": "Oregon"},
        "b": {"player_name": "Two Duck", "school": "Oregon"},
        "c": {"player_name": "Three X", "school": "Florida State"},
        "d": {"player_name": "Four Y", "school": "Moorpark College"},
        "e": {"player_name": "Five Z", "school": "Fairfield"},
    }
    monkeypatch.setattr(cs, "load_draft_players", lambda: fake)
    by_code = {"ORE_DUC": [{"name": n} for n in
                           ("One Duck", "Two Duck", "Three X", "Four Y", "Five Z")]}
    assert "ORE_DUC" not in cs._learn_code_schools(by_code)


def test_ncaa_box_rescales_rates_to_decimal():
    # NCAA payload carries bb%/k% as percentages; the player-page panel expects
    # the decimal convention. avg/obp/slg/iso pass through; woba/wRC+ blank.
    payload = {"avg": 0.321, "obp": 0.430, "slg": 0.612, "iso": 0.291,
               "hr": 14, "pa": 240, "bb_pct": 12.5, "k_pct": 15.0, "ab": 200}
    box = ct._ncaa_box_to_display(payload, 2025, "Georgia")
    assert box["bb_pct"] == 0.125 and box["k_pct"] == 0.15, "percent -> decimal"
    assert box["avg"] == 0.321 and box["iso"] == 0.291
    assert box["hr"] == 14 and box["pa"] == 240
    assert box["team"] == "Georgia" and box["level"] == "NCAA" and box["season"] == 2025
    assert box["woba"] is None and box["wrc_plus"] is None


def test_refresh_collegesavant_stats_no_universe(monkeypatch):
    # With an empty CS universe the pass is a clean no-op (never touches a browser).
    monkeypatch.setattr(cs, "_cs_universe", lambda: {})
    assert cs.refresh_collegesavant_stats(2025) == 0
