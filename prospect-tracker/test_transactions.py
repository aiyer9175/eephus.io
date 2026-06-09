from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from stats import derive_level_changes


def test_arizona_fall_league_assignment_does_not_create_dsl_level_change():
    txs = [
        {
            "date": "2022-08-12",
            "type_code": "ASG",
            "description": "RHP Karson Milbrandt assigned to FCL Marlins.",
            "to_team_id": 467,
            "to_team_name": "FCL Marlins",
        },
        {
            "date": "2022-09-09",
            "type_code": "ASG",
            "description": "RHP Karson Milbrandt assigned to Jupiter Hammerheads from FCL Marlins.",
            "from_team_id": 467,
            "from_team_name": "FCL Marlins",
            "to_team_id": 479,
            "to_team_name": "Jupiter Hammerheads",
        },
        {
            "date": "2023-06-28",
            "type_code": "ASG",
            "description": "RHP Karson Milbrandt assigned to Beloit Sky Carp from Jupiter Hammerheads.",
            "from_team_id": 479,
            "from_team_name": "Jupiter Hammerheads",
            "to_team_id": 554,
            "to_team_name": "Beloit Sky Carp",
        },
        {
            "date": "2025-09-03",
            "type_code": "ASG",
            "description": "RHP Karson Milbrandt assigned to Pensacola Blue Wahoos from Beloit Sky Carp.",
            "from_team_id": 554,
            "from_team_name": "Beloit Sky Carp",
            "to_team_id": 4124,
            "to_team_name": "Pensacola Blue Wahoos",
        },
        {
            "date": "2025-09-10",
            "type_code": "ASG",
            "description": "RHP Karson Milbrandt assigned to Mesa Solar Sox.",
            "to_team_id": 555,
            "to_team_name": "Mesa Solar Sox",
        },
        {
            "date": "2026-06-02",
            "type_code": "ASG",
            "description": "RHP Karson Milbrandt assigned to Jacksonville Jumbo Shrimp from Pensacola Blue Wahoos.",
            "from_team_id": 4124,
            "from_team_name": "Pensacola Blue Wahoos",
            "to_team_id": 564,
            "to_team_name": "Jacksonville Jumbo Shrimp",
        },
    ]
    affiliations = {
        467: {"name": "FCL Marlins", "level": "CPX"},
        479: {"name": "Jupiter Hammerheads", "level": "A"},
        554: {"name": "Beloit Sky Carp", "level": "A+"},
        4124: {"name": "Pensacola Blue Wahoos", "level": "AA"},
        # Regression: MLB Stats API can surface Mesa under a DSL-ish sport id.
        # It still must not be treated as a Dominican Summer League move.
        555: {"name": "Mesa Solar Sox", "level": "DSL"},
        564: {"name": "Jacksonville Jumbo Shrimp", "level": "AAA"},
    }

    # Point-in-time signature: one affiliation map per event YEAR. This fixture's
    # clubs don't rename across the span, so the same map applies to each year.
    affil_by_year = {y: affiliations for y in range(2020, 2027)}
    events = derive_level_changes(txs, affil_by_year)

    assert all(ev["to_team"] != "Mesa Solar Sox" for ev in events)
    assert all(ev["to_level"] != "DSL" for ev in events)
    assert events[-1] == {
        "date": "2026-06-02",
        "kind": "promotion",
        "from_level": "AA",
        "to_level": "AAA",
        "from_team": "Pensacola Blue Wahoos",
        "to_team": "Jacksonville Jumbo Shrimp",
    }
