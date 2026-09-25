# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The home "Across eephus.io" strip keeps its Fantasy card when the board is
empty.

Census M13-03: the 2026-09-23 build wrote data/fantasy.json with 0 players and
_cross_module_strip dropped the Fantasy card with no trace, so the home page
ran without it from 5492801d on and nothing said why. An empty board now
renders the card with an empty-state row and the artifact date; a missing or
unreadable file still drops it (there is no date to print)."""

from __future__ import annotations

import build_site


def _strip_with(monkeypatch, fantasy_payload):
    real = build_site._cached_data_json

    def fake(name):
        if name == "fantasy.json":
            return fantasy_payload
        return real(name)

    monkeypatch.setattr(build_site, "_cached_data_json", fake)
    return build_site._cross_module_strip()


def test_empty_board_keeps_the_card_with_its_build_date(monkeypatch):
    out = _strip_with(monkeypatch, {"generated_at": "2026-09-23T17:46:10Z",
                                    "n_players": 0, "players": [],
                                    "sections": {"ros_hitter": []}})
    assert "Fantasy</span>" in out
    assert "board built 2026-09-23 is empty" in out


def test_populated_board_prints_points_leaders(monkeypatch):
    out = _strip_with(monkeypatch, {
        "generated_at": "2026-09-25T02:04:40Z",
        "players": [{"mlbam": 1, "side": "hit", "name": "A Hitter", "team": "CLE",
                     "fpts_fgp": 88.4}],
        "sections": {"ros_hitter": [1]}})
    assert "A Hitter" in out and "88 FG pts" in out
    assert "is empty" not in out


def test_missing_file_still_drops_the_card(monkeypatch):
    out = _strip_with(monkeypatch, {})
    assert "rest-of-season hitter points leaders" not in out
