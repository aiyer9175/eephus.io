# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Offline tests for the Draft War Room poller (tools/draft_live_poller).

These run with NO live API: `scrapers.scrape_mlb_draft_tracker` is
monkeypatched to a small pick fixture. They lock in the launch-critical
invariants: the poller joins live picks to the committed board, prices them,
degrades to a valid artifact on an empty feed, and touches ONLY its out_path
(never prospects.db or draft_timeseries.json)."""
import json

import scrapers
import tools.draft_live_poller as dlp

YEAR = 2026

# Fixture rows mirror the real scrapers.scrape_mlb_draft_tracker dict shape:
# pick_overall, round_label, team, player_name, player_key, slot_usd, bonus_usd.
# Trevor Condon sits at board consensus_pick 18. Drafting him at pick 10 (8 spots
# EARLIER than our board rank) is a REACH: board_delta = 10 - 18 = -8.
_REACH_ROW = {
    "draft_year": YEAR, "pick_overall": 10, "round_label": "1",
    "pick_in_round": 10, "team": "LAD",
    "player_key": "draft_2026_trevor_condon", "player_name": "Trevor Condon",
    "school": "Somewhere", "slot_usd": 5_000_000, "bonus_usd": 5_250_000,
    "signed": 1, "source": "mlb_stats_api",
}
# Same board player (consensus_pick 18) falling to pick 25 is a STEAL for the
# drafting team: board_delta = 25 - 18 = +7.
_STEAL_ROW = {
    "draft_year": YEAR, "pick_overall": 25, "round_label": "1",
    "pick_in_round": 25, "team": "SFG",
    "player_key": "draft_2026_trevor_condon", "player_name": "Trevor Condon",
    "school": "Somewhere", "slot_usd": 3_000_000, "bonus_usd": 3_000_000,
    "signed": 1, "source": "mlb_stats_api",
}
# Not on the committed board -> off board, player_key None.
_OFFBOARD_ROW = {
    "draft_year": YEAR, "pick_overall": 11, "round_label": "1",
    "pick_in_round": 11, "team": "NYY",
    "player_key": "draft_2026_zzz_nobody", "player_name": "Zzz Nobody McFake",
    "school": "Nowhere", "slot_usd": 4_800_000, "bonus_usd": None,
    "signed": 0, "source": "mlb_stats_api",
}


def _patch(monkeypatch, rows):
    monkeypatch.setattr(scrapers, "scrape_mlb_draft_tracker",
                        lambda year, force=False: list(rows))


def test_build_returns_priced_joined_artifact(monkeypatch, tmp_path):
    _patch(monkeypatch, [_REACH_ROW, _OFFBOARD_ROW])
    out = tmp_path / "draft_live.json"
    art = dlp.build_draft_live(YEAR, out_path=out, now_iso="2026-07-12T18:00:00")

    assert art["status"] == "live"
    assert art["year"] == YEAR
    assert art["pick_count"] == 2
    assert len(art["picks"]) == 2
    assert art["generated_at"] == "2026-07-12T18:00:00"

    p = art["picks"][0]
    # Every pick carries the full priced schema.
    for field in ("pick_overall", "round", "team", "player_name", "player_key",
                  "consensus_fv", "efv", "mock_pick", "board_delta",
                  "reach_or_steal", "exp_first6_war", "exp_surplus_usd",
                  "signing_bonus_usd", "slot_usd", "bonus_vs_slot_usd"):
        assert field in p


def test_board_joined_pick_is_priced(monkeypatch, tmp_path):
    _patch(monkeypatch, [_REACH_ROW])
    art = dlp.build_draft_live(YEAR, out_path=tmp_path / "d.json")
    p = art["picks"][0]

    assert p["player_key"] == "draft_2026_trevor_condon"
    assert p["consensus_fv"] is not None
    assert p["board_delta"] == -8           # 10 - 18: taken 8 spots early
    assert p["reach_or_steal"] == "reach"   # -8 <= -threshold
    assert p["exp_first6_war"] is not None
    assert p["exp_surplus_usd"] is not None
    assert p["bonus_vs_slot_usd"] == 250_000  # 5_250_000 - 5_000_000


def test_faller_reads_as_steal(monkeypatch, tmp_path):
    """A board player who falls past his rank is a steal (positive delta)."""
    _patch(monkeypatch, [_STEAL_ROW])
    art = dlp.build_draft_live(YEAR, out_path=tmp_path / "d.json")
    p = art["picks"][0]
    assert p["board_delta"] == 7            # 25 - 18: fell 7 spots
    assert p["reach_or_steal"] == "steal"


def test_unmatched_name_is_off_board(monkeypatch, tmp_path):
    _patch(monkeypatch, [_OFFBOARD_ROW])
    art = dlp.build_draft_live(YEAR, out_path=tmp_path / "d.json")
    p = art["picks"][0]

    assert p["player_key"] is None
    assert p["reach_or_steal"] == "off board"
    assert p["board_delta"] is None
    assert p["consensus_fv"] is None
    # Slot-priced fields still populate off the pick number alone.
    assert p["exp_surplus_usd"] is not None
    assert p["bonus_vs_slot_usd"] is None   # bonus is None


def test_empty_feed_yields_waiting(monkeypatch, tmp_path):
    _patch(monkeypatch, [])
    out = tmp_path / "draft_live.json"
    art = dlp.build_draft_live(YEAR, out_path=out)  # must not raise

    assert art["status"] == "waiting"
    assert art["pick_count"] == 0
    assert art["picks"] == []
    # A valid artifact is still written to disk.
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk["status"] == "waiting"


def test_scrape_error_yields_error_status(monkeypatch, tmp_path):
    def _boom(year, force=False):
        raise RuntimeError("network down")
    monkeypatch.setattr(scrapers, "scrape_mlb_draft_tracker", _boom)
    art = dlp.build_draft_live(YEAR, out_path=tmp_path / "d.json")

    assert art["status"] == "error"
    assert art["picks"] == []


def test_writes_only_out_path(monkeypatch, tmp_path):
    """The poller must be READ-ONLY toward site state: prospects.db and
    draft_timeseries.json must be byte-identical after a build."""
    import os
    repo = os.path.dirname(dlp.__file__)  # tools/
    repo = os.path.dirname(repo)          # repo root
    db = os.path.join(repo, "prospects.db")
    ts = os.path.join(repo, "data", "draft_timeseries.json")

    before = {}
    for f in (db, ts):
        if os.path.exists(f):
            st = os.stat(f)
            before[f] = (st.st_mtime_ns, st.st_size)

    _patch(monkeypatch, [_STEAL_ROW, _OFFBOARD_ROW])
    dlp.build_draft_live(YEAR, out_path=tmp_path / "draft_live.json")

    for f, sig in before.items():
        st = os.stat(f)
        assert (st.st_mtime_ns, st.st_size) == sig, f"{f} was mutated"
    # And the poller wrote its artifact only under tmp_path.
    assert (tmp_path / "draft_live.json").exists()
