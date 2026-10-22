# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eWAR's named parts on the MLB player card (owner answer SWAR-Q4, the residual
of task EBR_3_EWAR_V3 that EWAR_V3_ASSEMBLE did not carry).

What is pinned:
  (a) _war_parts_map reads data/ewar_v3.json's parts per player-season and side:
      parts.abs.<side>.wins as "eabs", parts.r2 as "r2" on the pitching side,
      rounded to 2dp, a 0.00 part left out, an absent file an empty map;
  (b) the card rows gain war_parts and nothing else moves: war, war_bwar,
      war_fwar, war_real and war_ewar2 are the same with and without it;
  (c) on the served artifacts (when both are present), every war_parts cell
      equals the artifact's part at 2dp, and eWAR minus FanGraphs WAR on a
      card row is the eabs part within display rounding.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import ewar_v3
import mlb_player_export as mpe
from test_mlb_player_fwar_reference import _maps, lines  # noqa: F401  (fixture)

ROOT = Path(__file__).parent
DETAIL = ROOT / "data" / "mlb_player_detail.json"

_FIX = {"players": {
    "660271": {"2026": {"f": {"bat": 6.0, "pit": 2.0}, "dh": {"bat": 0.2, "pit": -0.004},
                        "dr": {"bat": 0.2, "pit": 0.5},
                        "parts": {"abs": {"bat": {"wins": 0.2}, "pit": {"wins": -0.004}},
                                  "r2": 0.504}}},
    "694973": {"2024": {"f": {"pit": 4.27}, "dh": {}, "dr": {"pit": -0.31},
                        "parts": {"r2": -0.31}},
               "2025": {"f": {"pit": 5.0}, "dh": {}, "dr": {"pit": 0.001},
                        "parts": {"r2": 0.001}}},
}}


def test_the_parts_map_reads_each_part_by_side():
    m = mpe._war_parts_map(_FIX)
    assert m[660271][2026] == {"bat": {"eabs": 0.2}, "pit": {"r2": 0.5}}
    assert m[694973][2024] == {"pit": {"r2": -0.31}}
    assert 2025 not in m[694973]          # 0.001 rounds to 0.00: left out
    assert set(m) == {660271, 694973}
    assert set(ewar_v3.PART_LABELS) == {"eabs", "r2", "xhem"}
    # the xHEM+ part (EBR_GATE.md 11.11): hitters, headline only, read when the artifact carries it
    fx = {"players": {"1": {"2024": {"f": {"bat": 2.0}, "dh": {"bat": 0.123}, "dr": {},
                                     "dx": {}, "parts": {"xhem": {"runs": 2.4, "wins": 0.123, "arm": "xhem"}}},
                            "2025": {"f": {"bat": 2.0}, "dh": {"bat": 0.004}, "dr": {},
                                     "dx": {}, "parts": {"xhem": {"runs": 0.08, "wins": 0.004, "arm": "hem"}}}}}}
    assert mpe._war_parts_map(fx) == {1: {2024: {"bat": {"xhem": 0.12}}}}


def test_an_absent_artifact_drops_the_parts_not_the_card(monkeypatch):
    monkeypatch.setattr(ewar_v3, "available", lambda: False)
    assert mpe._war_parts_map() == {}


def test_card_rows_gain_war_parts_and_nothing_else_moves(lines):  # noqa: F811
    served, bwar, ref, _provider = _maps()
    parts = {694973: {2024: {"pit": {"r2": -0.31}}},
             660271: {2023: {"bat": {"eabs": 0.2}, "pit": {"eabs": -0.1, "r2": 0.4}}}}
    for mid, is_pit in ((545361, False), (660271, False), (660271, True), (694973, True)):
        before = mpe._career_rows(mid, is_pit, served, bwar, ref, {"real": {}, "ewar2": {}})
        after = mpe._career_rows(mid, is_pit, served, bwar, ref,
                                 {"real": {}, "ewar2": {}, "parts": parts})
        assert [r["y"] for r in before] == [r["y"] for r in after]
        for b, a in zip(before, after):
            assert {k: v for k, v in a.items() if k != "war_parts"} == b
            want = ((parts.get(mid) or {}).get(a["y"]) or {}).get("pit" if is_pit else "bat")
            if want and a.get("war") is not None:
                assert a["war_parts"] == want
            else:
                assert "war_parts" not in a
    pit = {r["y"]: r for r in mpe._career_rows(660271, True, served, bwar, ref,
                                                {"parts": parts})}
    assert pit[2023]["war_parts"] == {"eabs": -0.1, "r2": 0.4}


def test_the_payload_note_names_war_parts():
    assert "war_parts = eWAR v3's named parts" in mpe._CAREER_NOTE_V3


def test_served_card_parts_match_the_artifact():
    if not (DETAIL.exists() and ewar_v3.OUT.exists()):
        pytest.skip("data/mlb_player_detail.json or data/ewar_v3.json absent")
    d = json.loads(DETAIL.read_text(encoding="utf-8"))
    rows = [(p.get("mlbam"), r, "pit" if p.get("isPit") else "bat")
            for p in d["players"].values() for r in (p.get("career") or [])]
    if not any("war_parts" in r for _m, r, _s in rows):
        pytest.skip("the served cards predate war_parts")
    m = mpe._war_parts_map(ewar_v3.load())
    n = 0
    for mid, r, side in rows:
        want = ((m.get(int(mid)) or {}).get(r["y"]) or {}).get(side) if mid else None
        if r.get("war") is None:
            assert "war_parts" not in r
            continue
        assert r.get("war_parts") == (want or None) or ("war_parts" not in r and not want), (mid, r["y"])
        if r.get("war_parts") and r.get("war_fwar") is not None:
            # eWAR minus FanGraphs WAR is the eabs part, within two 1dp roundings
            assert abs(r["war"] - r["war_fwar"] - r["war_parts"].get("eabs", 0.0)) <= 0.1 + 1e-9
            n += 1
    assert n > 0
