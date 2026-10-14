# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""P/IP, P/BF, P/PA and PAR on the three MLB Stats boards (plan Part 8, PM-03).

What these pin:
  * the flag. With pitch_rates.SERVE_PITCH_RATES False an export writes no new
    key at all; with it True every existing key is byte-identical and the new
    keys are appended.
  * the definitions. A starter's P/IP reads his starts line only, a reliever's
    his relief line only; sp_ip_per_gs counts innings in starts; ip_per_gs is
    never touched.
  * absence. A player with no pitch count gets every new key as None, never 0.
  * the consumers that must not move: leaderboard_vintages.reduce_current and
    betting_model.starter_inputs() read the same bytes either way.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone

import pytest

import betting_model as bm
import bullpen_export as be
import hem_plus
import hitter_export as he
import leaderboard_vintages as lv
import pitch_rates as PR
import pitch_rates_boards as B
import starter_export as se


# --------------------------------------------------------------------------- #
# A synthetic season: anchors and player lines in pitch_rates' own shapes
# --------------------------------------------------------------------------- #
def _line(np_, outs, bf, g, gs):
    return {"np": np_, "outs": outs, "bf": bf, "g": g, "gs": gs}


def _ctx(basis=PR.BASIS_ROLE, status="usable"):
    lines = {
        # a starter with a few relief outings: 30 starts, 3 relief games
        1: {"hit": None, "pit": {
            "season_line": _line(2800, 540, 720, 33, 30),
            "sp": _line(2640, 510, 680, 30, 30),
            "rp": _line(160, 30, 40, 3, 0), "role": "SP", "basis": PR.BASIS_ROLE}},
        # a pure starter
        2: {"hit": None, "pit": {
            "season_line": _line(2400, 450, 600, 28, 28),
            "sp": _line(2400, 450, 600, 28, 28), "rp": None,
            "role": "SP", "basis": PR.BASIS_ROLE}},
        # a reliever with two spot starts
        3: {"hit": None, "pit": {
            "season_line": _line(1300, 210, 290, 60, 2),
            "sp": _line(120, 18, 26, 2, 2),
            "rp": _line(1180, 192, 264, 58, 0), "role": "RP", "basis": PR.BASIS_ROLE}},
        # a pure reliever
        4: {"hit": None, "pit": {
            "season_line": _line(1000, 180, 240, 55, 0), "sp": None,
            "rp": _line(1000, 180, 240, 55, 0), "role": "RP", "basis": PR.BASIS_ROLE}},
        # a pitcher whose feed carries no pitch count
        5: {"hit": None, "pit": {
            "season_line": {"outs": 90, "bf": 120, "g": 20, "gs": 0, "missing_np": 1},
            "sp": None, "rp": {"outs": 90, "bf": 120, "g": 20, "missing_np": 1},
            "role": "RP", "basis": PR.BASIS_ROLE}},
    }
    league = {"season": 2026, "basis": basis, "pitching_status": status,
              "tracking": status,
              "sp": {"p_ip": 16.0, "p_bf": 3.9, "pit_per_gs": 85.0,
                     "sp_ip_per_gs": 5.3, "n": 100},
              "rp": {"p_ip": 17.0, "p_bf": 3.9, "pit_per_g": 18.0, "n": 200},
              "hit": {"p_pa": 3.9, "n": 300}}
    return {"season": 2026, "league": league, "lines": lines}


def _starter_rows():
    return [{"mlbam": 1, "team": "AAA", "ip": 180.0, "ip_per_gs": 6.0},
            {"mlbam": 2, "team": "AAA", "ip": 150.0, "ip_per_gs": 5.36},
            {"mlbam": 3, "team": "BBB", "ip": 70.0, "ip_per_gs": 35.0},
            {"mlbam": 99, "team": "BBB", "ip": 10.0, "ip_per_gs": 5.0}]


# --------------------------------------------------------------------------- #
# Rows
# --------------------------------------------------------------------------- #
def test_starter_reads_his_starts_line_only():
    rows = _starter_rows()
    B.stamp_pitcher_rows(rows, _ctx(), "sp")
    r = rows[0]
    assert r["p_ip"] == round(2640 / (510 / 3), 2)
    assert r["p_bf"] == round(2640 / 680, 3)
    assert r["pit_per_gs"] == round(2640 / 30, 1)
    assert r["sp_ip_per_gs"] == round(510 / 3 / 30, 2)
    # ip_per_gs is never redefined: it still divides ALL innings by starts.
    assert r["ip_per_gs"] == 6.0 and r["sp_ip_per_gs"] < r["ip_per_gs"]
    assert r["par"] == PR.par(2640 / 170, 16.0)
    assert r["par_delta"] == round(2640 / 170 - 16.0, 2)
    assert r["role_line_basis"] == PR.BASIS_ROLE


def test_reliever_reads_his_relief_line_only():
    rows = [{"mlbam": 3, "team": "BBB"}, {"mlbam": 4, "team": "BBB"}]
    B.stamp_pitcher_rows(rows, _ctx(), "rp")
    assert rows[0]["p_ip"] == round(1180 / 64, 2)
    assert rows[0]["pit_per_g"] == round(1180 / 58, 1)
    assert rows[0]["par"] == PR.par(1180 / 64, 17.0)
    assert set(rows[0]) - {"mlbam", "team"} == set(B.RP_ROW_KEYS)


def test_no_pitches_means_none_never_zero():
    rows = [{"mlbam": 5, "team": "BBB"}, {"mlbam": 99, "team": "BBB"},
            {"mlbam": None, "team": "BBB"}]
    meta = B.stamp_pitcher_rows(rows, _ctx(), "rp")
    for r in rows:
        assert all(r[k] is None for k in B.RP_ROW_KEYS), r
    assert meta == {"rows": 3, "stamped": 0, "season_line_fallback": 0}
    hit = [{"mlbam": 7, "pa": 400}, {"mlbam": 8, "pa": 0}]
    B.stamp_hitter_rows(hit, {7: None, 8: 10}, _ctx())
    for r in hit:
        assert all(r[k] is None for k in B.HIT_ROW_KEYS), r


def test_new_keys_are_typed():
    rows = _starter_rows()
    B.stamp_pitcher_rows(rows, _ctx(), "sp")
    r = rows[0]
    for k in ("p_ip", "p_bf", "par_delta", "pit_per_gs", "sp_ip_per_gs"):
        assert isinstance(r[k], float), k
    assert isinstance(r["par"], int) and isinstance(r["role_line_basis"], str)
    hit = [{"mlbam": 7, "pa": 500}]
    B.stamp_hitter_rows(hit, {7: 2000.0}, _ctx())
    assert isinstance(hit[0]["p_pa"], float) and isinstance(hit[0]["par_delta"], float)
    assert isinstance(hit[0]["par"], int) and isinstance(hit[0]["pit"], int)
    assert hit[0]["p_pa"] == 4.0 and hit[0]["par"] == 103 and hit[0]["pit"] == 2000


def test_season_line_fallback_is_stamped_and_keeps_per_start_honest():
    rows = _starter_rows()
    meta = B.stamp_pitcher_rows(rows, _ctx(basis=PR.BASIS_FALLBACK), "sp")
    assert meta["season_line_fallback"] == 3
    swing, pure = rows[0], rows[1]
    assert swing["role_line_basis"] == PR.BASIS_FALLBACK
    assert swing["p_ip"] == round(2800 / 180, 2)
    # 3 relief games in the season line: no starts-only figure from it
    assert swing["pit_per_gs"] is None and swing["sp_ip_per_gs"] is None
    # every game a start: the season line IS the starts line
    assert pure["sp_ip_per_gs"] == round(450 / 3 / 28, 2)


def test_untracked_season_prints_nothing():
    rows = _starter_rows()
    B.stamp_pitcher_rows(rows, _ctx(status="untracked"), "sp")
    assert all(r["p_ip"] is None for r in rows)
    hit = [{"mlbam": 7, "pa": 500}]
    B.stamp_hitter_rows(hit, {7: 2000.0}, _ctx(status="untracked"))
    assert hit[0]["p_pa"] is None


# --------------------------------------------------------------------------- #
# Teams
# --------------------------------------------------------------------------- #
def test_rotation_units_pool_starts_lines_and_skip_missing_members():
    rows = _starter_rows()
    teams = [{"team": "AAA"}, {"team": "BBB"}, {"team": "CCC"}]
    n = B.stamp_pitcher_teams(teams, rows, _ctx(), "sp")
    assert n == 2
    a, b, c = teams
    assert a["rot_p_ip"] == round((2640 + 2400) / ((510 + 450) / 3), 2)
    assert a["rot_pit_per_gs"] == round((2640 + 2400) / 58, 1)
    # BBB: only the spot starts of player 3 (player 99 has no line, never zero)
    assert b["rot_p_ip"] == round(120 / 6, 2)
    assert c["rot_p_ip"] is None and c["rot_par"] is None
    ra, rb = (2640 + 2400) / 320, 120 / 6
    mean = (ra + rb) / 2
    assert a["rot_par"] == PR.par(100 * ra / mean, 100.0)
    assert b["rot_par"] == PR.par(100 * rb / mean, 100.0)


def test_team_par_averages_100_on_the_board_clubs():
    rows = [{"mlbam": i, "team": f"T{i % 6}", "pa": 300 + 7 * i} for i in range(60)]
    np_by_id = {i: (300 + 7 * i) * (3.7 + 0.01 * (i % 13)) for i in range(60)}
    teams = [{"team": f"T{k}"} for k in range(6)]
    B.stamp_hitter_teams(teams, rows, np_by_id, {}, _ctx())
    exact = PR.team_par({t["team"]: t["lineup_p_pa"] for t in teams})
    assert abs(sum(exact.values()) / 6 - 100.0) < 1e-9
    assert abs(sum(t["lineup_par"] for t in teams) / 6 - 100.0) <= 0.5


def test_lineup_units_leave_pitchers_bats_out():
    rows = [{"mlbam": 1, "team": "AAA", "pa": 500}, {"mlbam": 2, "team": "AAA", "pa": 3}]
    teams = [{"team": "AAA"}]
    B.stamp_hitter_teams(teams, rows, {1: 2000.0, 2: 30.0}, {1: "SS", 2: "P"}, _ctx())
    assert teams[0]["lineup_p_pa"] == 4.0


# --------------------------------------------------------------------------- #
# The exporter: flag off writes nothing new; flag on moves no existing byte
# --------------------------------------------------------------------------- #
def _split(pid, name, gs, ip, np_=1300):
    return {"player": {"id": pid, "fullName": name}, "team": {"id": 108},
            "position": {"abbreviation": "P"},
            "stat": {"gamesPitched": gs + 3, "gamesStarted": gs, "inningsPitched": ip,
                     "earnedRuns": 30, "runs": 32, "baseOnBalls": 25, "strikeOuts": 90,
                     "homeRuns": 9, "hitByPitch": 3, "battersFaced": 330,
                     "numberOfPitches": np_, "completeGames": 0, "groundOuts": 80,
                     "airOuts": 70, "strikes": 820}}


def _starter_export(tmp_path, monkeypatch, flag, tag):
    splits = [_split(1, "A", 30, "180.0"), _split(2, "B", 28, "150.0"),
              _split(3, "C", 14, "85.2")]
    monkeypatch.setattr(PR, "SERVE_PITCH_RATES", flag)
    monkeypatch.setattr(B, "season_context", lambda season, fetch=True: _ctx())
    monkeypatch.setattr(be, "_team_abbrev_map", lambda: {108: "LAA"})
    monkeypatch.setattr(be, "apply_current_team", lambda rows, label="": 0)
    monkeypatch.setattr(se, "load_season_pitching",
                        lambda season, positions=("P",): be.rows_from_pitching_splits(
                            splits, season, positions))
    monkeypatch.setattr(se, "_active_mlbam_ids", lambda season: None)
    monkeypatch.setattr(se, "_join_xsem_plus", lambda starters, season: 0)
    monkeypatch.setattr(se, "_join_savant_custom", lambda starters, season: {})
    monkeypatch.setattr(se, "_join_war_ip_plus", lambda starters, season: {})
    monkeypatch.setattr(se, "_join_war_ip_plus_3yr", lambda starters: {})
    monkeypatch.setattr(se, "_war_source_vintage", lambda as_of=None: {})
    monkeypatch.setattr(se, "stamp_team_war", lambda teams, rows, season, side: {})
    monkeypatch.setattr(se, "MULTIYR_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(be, "WINDOW_L3_PATH", tmp_path / "missing_window_l3.json")
    monkeypatch.setattr(se, "EVAL_PATH", tmp_path / "missing_eval.json")
    out = tmp_path / f"starters_{tag}.json"
    se.export(2026, out_path=out, write=True, log=lambda *a, **k: None, today="2026-10-07")
    return out


def _strip(doc, list_key, row_keys, team_keys):
    doc = copy.deepcopy(doc)
    doc.pop(B.PAYLOAD_KEY)
    for r in doc[list_key]:
        for k in row_keys:
            r.pop(k)
    for t in doc["teams"]:
        for k in team_keys:
            t.pop(k)
    return doc


def test_starter_export_flag_off_writes_no_new_key_and_on_moves_no_existing_byte(
        tmp_path, monkeypatch):
    off_path = _starter_export(tmp_path, monkeypatch, False, "off")
    on_path = _starter_export(tmp_path, monkeypatch, True, "on")
    off = json.loads(off_path.read_text(encoding="utf-8"))
    on = json.loads(on_path.read_text(encoding="utf-8"))
    assert B.PAYLOAD_KEY not in off
    for r in off["starters"]:
        assert not set(B.SP_ROW_KEYS) & set(r)
    for t in off["teams"]:
        assert not set(B.SP_TEAM_KEYS) & set(t)
    # every existing key, in order, byte for byte
    stripped = _strip(on, "starters", B.SP_ROW_KEYS, B.SP_TEAM_KEYS)
    assert json.dumps(stripped, indent=1) == json.dumps(off, indent=1)
    # the new keys sit after every existing key
    for r_on, r_off in zip(on["starters"], off["starters"]):
        assert list(r_on)[:len(r_off)] == list(r_off)
        assert list(r_on)[len(r_off):] == list(B.SP_ROW_KEYS)
    blk = on[B.PAYLOAD_KEY]
    for k in ("as_of", "season", "basis", "anchors", "n"):
        assert k in blk
    assert blk["anchors"]["p_ip"] == 16.0 and blk["as_of"] == "2026-10-07"


def test_starter_inputs_unchanged_by_the_new_keys(tmp_path, monkeypatch):
    off = json.loads(_starter_export(tmp_path, monkeypatch, False, "off").read_text(
        encoding="utf-8"))
    on = json.loads(_starter_export(tmp_path, monkeypatch, True, "on").read_text(
        encoding="utf-8"))
    got = []
    for tag, doc in (("off", off), ("on", on)):
        d = tmp_path / f"data_{tag}"
        d.mkdir()
        (d / "starter_leaderboards.json").write_text(json.dumps(doc), encoding="utf-8")
        monkeypatch.setattr(bm, "DATA_DIR", d)
        got.append(json.dumps(bm.starter_inputs(), sort_keys=True))
    assert got[0] == got[1]


# --------------------------------------------------------------------------- #
# leaderboard_vintages.reduce_current: byte-identical on fixture boards
# --------------------------------------------------------------------------- #
class _FixedNow(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)


def _fixture_boards(data_dir, stamped: bool):
    orgs = ("NYM", "PHI", "ATL", "WSN")
    hit = {"season": "2026", "as_of": "2026-10-06",
           "teams": [{"team": o, "offense_plus": 110 - 2 * i} for i, o in enumerate(orgs)],
           "hitters": [{"mlbam": 301 + i, "team": o, "hem_plus": 100 + i, "pa": 500}
                       for i, o in enumerate(orgs)]}
    rot = {"season": "2026", "as_of": "2026-10-06",
           "teams": [{"team": o, "rotation_plus": 104 - 3 * i, "starter_ip": 560.0}
                     for i, o in enumerate(orgs)],
           "starters": [{"mlbam": 101 + i, "team": o, "sem_plus": 110 - 5 * i,
                         "ip_per_gs": 5.5, "role": "SP"} for i, o in enumerate(orgs)]}
    pen = {"season": "2026", "as_of": "2026-10-06",
           "teams": [{"team": o, "bullpen_plus": 101 - 2 * i, "relief_ip": 380.0}
                     for i, o in enumerate(orgs)],
           "relievers": [{"mlbam": 201 + i, "team": o, "rem_plus": 103 - 4 * i}
                         for i, o in enumerate(orgs)]}
    if stamped:
        for i, r in enumerate(rot["starters"]):
            r.update({"p_ip": 16.0 + i, "p_bf": 3.9, "par": 97 + i, "par_delta": -0.4,
                      "pit_per_gs": 88.0, "sp_ip_per_gs": 5.1,
                      "role_line_basis": PR.BASIS_ROLE})
        for r in pen["relievers"]:
            r.update({"p_ip": 17.0, "p_bf": 3.9, "par": 101, "par_delta": 0.2,
                      "pit_per_g": 18.0, "role_line_basis": PR.BASIS_ROLE})
        for r in hit["hitters"]:
            r.update({"p_pa": 3.9, "par": 100, "par_delta": 0.0, "pit": 1950})
        for t in rot["teams"]:
            t.update({"rot_p_ip": 16.2, "rot_par": 99, "rot_pit_per_gs": 87.0})
        for t in pen["teams"]:
            t.update({"pen_p_ip": 16.9, "pen_par": 101})
        for t in hit["teams"]:
            t.update({"lineup_p_pa": 3.9, "lineup_par": 100})
        for doc in (hit, rot, pen):
            doc[B.PAYLOAD_KEY] = {"as_of": "2026-10-06", "season": 2026}
    for name, doc in (("hitter_leaderboards.json", hit),
                      ("starter_leaderboards.json", rot),
                      ("bullpen_leaderboards.json", pen)):
        (data_dir / name).write_text(json.dumps(doc), encoding="utf-8")


def test_reduce_current_byte_identical_with_the_new_keys(tmp_path, monkeypatch):
    import pal_export
    monkeypatch.setattr(lv, "datetime", _FixedNow)
    monkeypatch.setattr(pal_export, "load_pitch_hand",
                        lambda season: {101: "L", 102: "R", 103: "R", 104: "L"})
    out = []
    for stamped in (False, True):
        d = tmp_path / f"data_{stamped}"
        d.mkdir()
        _fixture_boards(d, stamped)
        rec = lv.reduce_current(on_date="2026-10-07", data_dir=d)
        assert rec is not None
        out.append(json.dumps(rec, sort_keys=True))
    assert out[0] == out[1]


# --------------------------------------------------------------------------- #
# The hitter loader carries the pitch count, and only the P/PA join reads it
# --------------------------------------------------------------------------- #
def test_hitter_np_rides_the_row_and_the_record_not_the_board_row():
    rows = [{"mlbam": 7, "name": "X", "team": "AAA", "PA": 500, "AB": 450, "H": 120,
             "2B": 25, "3B": 2, "HR": 20, "BB": 40, "IBB": 2, "HBP": 5, "SF": 4,
             "SO": 110, "SB": 5, "CS": 2, "RBI": 70, "R": 65, "primary_pos": "SS",
             "NP": 1960}]
    hs = he.build_hitters(rows)
    assert hs[0].np == 1960.0
    scored = hem_plus.score_pool(hs)
    assert "np" not in scored["hitters"][0] and "pit" not in scored["hitters"][0]
    np_by_id, pos_by_id = he._np_pos_by_id(hs)
    assert np_by_id == {7: 1960.0} and pos_by_id == {7: "SS"}


def test_check_board_catches_a_key_without_its_block_and_a_wrong_par():
    dark = {"starters": [{"mlbam": 1, "p_ip": 16.0}], "teams": []}
    assert B.check_board(dark, "sp")
    rows = _starter_rows()
    teams = [{"team": "AAA"}, {"team": "BBB"}]
    B.stamp_pitcher_rows(rows, _ctx(), "sp")
    B.stamp_pitcher_teams(teams, rows, _ctx(), "sp")
    doc = {"starters": rows, "teams": teams,
           B.PAYLOAD_KEY: B.payload_block(_ctx(), "sp", "2026-10-07", {"rows": 4})}
    assert B.check_board(doc, "sp") == []
    rows[0]["par"] += 2
    assert B.check_board(doc, "sp")


def test_the_flag_is_on_after_the_flip():
    """TRIPWIRE. The flip landed in its own commit after the fWAR epoch's step Z
    (Q8_06); turning it back off is its own decision, not a side effect."""
    assert PR.SERVE_PITCH_RATES is True
    assert B.serving() is True
