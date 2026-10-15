# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""BT Blend (btblend_plus), the served construction registered in
docs/BAT_TRACKING_SERVED_GATE.md: the builder matches the registration, the
flag (hitter_export.BTBLEND_SERVE) gates the only call site, and with the flag
off the exporter reads nothing, fetches nothing and leaves every board row
byte-identical."""
from __future__ import annotations

import copy
import inspect
import json
import sys
from pathlib import Path

import pytest

import bat_tracking_blend as bbt
import hitter_export as he

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))


def _bt_row(mid, swings, speed, sq, blast, **over):
    r = {"id": mid, "swings_qualified": swings,
         "avg_sweetspot_speed_mph_qualified": speed, "swing_length_qualified": 7.2,
         "attack_angle": 10.0, "attack_direction_pullopp": 1.0,
         "avg_plane_vertical_angle": 30.0, "rate_ideal_attack_angle": 0.5,
         "squared_up_per_swing": sq, "squared_up_with_speed_per_swing": blast}
    r.update(over)
    return r


BT_ROWS = [
    _bt_row(1, 400, 72.1, 0.28, 0.10),
    _bt_row(2, 350, 70.4, 0.31, 0.08),
    _bt_row(3, 500, 74.9, 0.25, 0.14),
    _bt_row(4, 220, 69.0, 0.33, 0.06),
    _bt_row(5, 99, 80.0, 0.40, 0.30),                       # under the swings floor
    _bt_row(6, 300, 71.0, 0.29, 0.09, attack_angle=None),   # a mapped field missing
    _bt_row(7, 260, 73.3, 0.27, 0.12),
]
SAVANT = [
    {"player_id": "1", "est_woba": "0.360", "pa": "450"},
    {"player_id": "2", "est_woba": "0.310", "pa": "300"},
    {"player_id": "3", "est_woba": "0.390", "pa": "520"},
    {"player_id": "4", "est_woba": "0.290", "pa": "120"},
    {"player_id": "7", "est_woba": "0.330", "pa": "99"},     # under the PA floor
    {"player_id": "8", "est_woba": "0.340", "pa": "200"},    # no BT row
]
HEM = {1: 118.0, 2: 96.5, 3: 131.2, 4: 84.0, 7: 101.0, 8: 104.0}


# --------------------------------------------------------------------------- #
# the registration, pinned
# --------------------------------------------------------------------------- #
def test_constants_are_the_registered_ones():
    import bat_tracking_lab as btl
    import mlb_player_export as mpe
    assert (bbt.W_XWOBA, bbt.W_HEM, bbt.W_BT) == btl.CAND_W
    assert bbt.MIN_SWINGS == btl.BT_MIN_SWINGS == 100.0
    assert bbt.MIN_PA == 100.0
    assert bbt.BT_URL == btl.BT_URL
    assert set(bbt.REQUIRED_FIELDS) == set(btl.BT_FIELD_MAP)
    assert tuple(btl.BT_FIELD_MAP[c] for c in bbt.COMPONENTS) == btl.ARM_B_COMPOSITE_FEATS
    assert bbt.LIVE_TTL_S == mpe._SAVANT_LIVE_TTL_S


def test_the_flag_is_off_until_the_reread_flips_it():
    assert he.BTBLEND_SERVE is False
    assert he.BTBLEND_PREVIEW_ENV == "EEPHUS_BTBLEND_PREVIEW"


# --------------------------------------------------------------------------- #
# the builder
# --------------------------------------------------------------------------- #
def test_composite_is_the_labs_component_normalizer():
    import bat_tracking_lab as btl
    comp = bbt.composite_map(BT_ROWS)
    assert set(comp) == {1, 2, 3, 4, 7}            # floor and missing field drop
    pop = {}
    for r in BT_ROWS:
        if r["swings_qualified"] < 100 or r["attack_angle"] is None:
            continue
        pop[r["id"]] = {btl.BT_FIELD_MAP[k]: float(r[k]) for k in bbt.REQUIRED_FIELDS}
    z = btl.zmap(pop, btl.ARM_B_COMPOSITE_FEATS)
    for m, v in comp.items():
        want = sum(z[m][k] for k in btl.ARM_B_COMPOSITE_FEATS) / 3
        assert v == pytest.approx(want, abs=1e-12)


def test_served_values_follow_the_registered_recipe():
    xw = bbt.savant_xwoba_map(SAVANT)
    assert set(xw) == {1, 2, 3, 4, 8}
    comp = bbt.composite_map(BT_ROWS)
    vals, p = bbt.served_values(xw, HEM, comp)
    assert set(vals) == {1, 2, 3, 4}                # J(Y): all three legs
    assert p["n_pool"] == 4
    unr = {m: bbt.blend_unrounded(xw[m], HEM[m], comp[m], p) for m in vals}
    # the affine map lands J(Y) on its own HEM+ location and spread
    mu = sum(unr.values()) / 4
    sd = (sum((v - mu) ** 2 for v in unr.values()) / 3) ** 0.5
    hm = sum(HEM[m] for m in vals) / 4
    hs = (sum((HEM[m] - hm) ** 2 for m in vals) / 3) ** 0.5
    assert mu == pytest.approx(hm) and sd == pytest.approx(hs)
    for m, v in vals.items():
        assert v == int(round(unr[m])) and isinstance(v, int)
    # the plain blend is the frozen weights over J(Y) leg z
    zx = (xw[1] - p["mu_x"]) / p["sd_x"]
    zh = (HEM[1] - p["mu_h"]) / p["sd_h"]
    zc = (comp[1] - p["mu_c"]) / p["sd_c"]
    assert bbt.blend_z(xw[1], HEM[1], comp[1], p) == pytest.approx(
        0.595 * zx + 0.255 * zh + 0.15 * zc)


def test_a_degenerate_pool_serves_nothing():
    assert bbt.served_values({1: 0.3}, {1: 100.0}, {1: 0.1}) == ({}, None)
    assert bbt.served_values({}, HEM, bbt.composite_map(BT_ROWS)) == ({}, None)
    assert bbt.composite_map([]) == {}


# --------------------------------------------------------------------------- #
# fetch and cache
# --------------------------------------------------------------------------- #
def _html(rows):
    return "<script>const data = " + json.dumps(rows) + ";</script>"


def test_fetch_caches_closed_seasons_forever(tmp_path):
    calls = []

    def get(url):
        calls.append(url)
        return _html(BT_ROWS)

    from datetime import date
    rows = bbt.fetch_leaderboard(2025, cache_dir=tmp_path, getter=get, today=date(2026, 10, 14))
    assert rows == BT_ROWS and len(calls) == 1 and "seasonStart=2025" in calls[0]
    rows = bbt.fetch_leaderboard(2025, cache_dir=tmp_path, getter=get, today=date(2026, 10, 14),
                                 now=9e12)
    assert rows == BT_ROWS and len(calls) == 1


def test_current_season_refreshes_and_falls_back_to_stale(tmp_path):
    from datetime import date
    today = date(2026, 10, 14)
    bbt.fetch_leaderboard(2026, cache_dir=tmp_path, getter=lambda u: _html(BT_ROWS[:2]),
                          today=today)
    path = tmp_path / "bat_tracking_batter_2026.json"
    mt = path.stat().st_mtime
    fresh = bbt.fetch_leaderboard(2026, cache_dir=tmp_path, today=today, now=mt + 60,
                                  getter=lambda u: _html(BT_ROWS))
    assert fresh == BT_ROWS[:2]                     # inside the TTL: no refresh
    newer = bbt.fetch_leaderboard(2026, cache_dir=tmp_path, today=today,
                                  now=mt + bbt.LIVE_TTL_S + 1,
                                  getter=lambda u: _html(BT_ROWS))
    assert newer == BT_ROWS

    def boom(u):
        raise OSError("offline")
    stale = bbt.fetch_leaderboard(2026, cache_dir=tmp_path, today=today,
                                  now=path.stat().st_mtime + bbt.LIVE_TTL_S + 1, getter=boom)
    assert stale == BT_ROWS
    assert bbt.fetch_leaderboard(2024, cache_dir=tmp_path / "empty", getter=boom,
                                 today=today) == []
    assert bbt.fetch_leaderboard(2024, cache_dir=tmp_path / "nodata",
                                 getter=lambda u: "<html></html>", today=today) == []


# --------------------------------------------------------------------------- #
# the flag
# --------------------------------------------------------------------------- #
def _board():
    return [{"mlbam": m, "name": f"P{m}", "hem_plus": int(HEM[m]), "fwdhem_plus": 100}
            for m in (1, 2, 3, 4, 7, 8)] + [{"mlbam": None, "name": "no id"}]


@pytest.fixture
def _no_reads(monkeypatch):
    import mlb_player_export as mpe

    def boom(*a, **k):
        raise AssertionError("nothing may be read while BTBLEND_SERVE is off")
    monkeypatch.setattr(mpe, "_savant", boom)
    monkeypatch.setattr(bbt, "fetch_leaderboard", boom)
    monkeypatch.delenv(he.BTBLEND_PREVIEW_ENV, raising=False)


def test_flag_off_reads_nothing_and_leaves_the_board_byte_identical(monkeypatch, _no_reads):
    monkeypatch.setattr(he, "BTBLEND_SERVE", False)
    board = _board()
    before = json.dumps(board, indent=1)
    assert he._btblend_step(board, dict(HEM), 2026, log=lambda *a: None) == 0
    assert json.dumps(board, indent=1) == before


def test_preview_writes_only_the_preview_file(monkeypatch, tmp_path):
    import mlb_player_export as mpe
    monkeypatch.setattr(he, "BTBLEND_SERVE", False)
    monkeypatch.setenv(he.BTBLEND_PREVIEW_ENV, "1")
    monkeypatch.setattr(mpe, "_savant", lambda kind, year, side="batter": SAVANT)
    monkeypatch.setattr(bbt, "fetch_leaderboard", lambda season: BT_ROWS)
    monkeypatch.setattr(bbt, "PREVIEW_DIR", tmp_path)
    board = _board()
    before = copy.deepcopy(board)
    assert he._btblend_step(board, dict(HEM), 2026, log=lambda *a: None) == 0
    assert board == before
    doc = json.loads((tmp_path / "btblend_preview_2026.json").read_text(encoding="utf-8"))
    assert doc["flag_on"] is False and doc["n_pool"] == 4
    assert sorted(r["mlbam"] for r in doc["rows"]) == [1, 2, 3, 4]
    assert [p.name for p in tmp_path.iterdir()] == ["btblend_preview_2026.json"]


def test_flag_on_stamps_only_rows_in_the_joined_pool(monkeypatch):
    import mlb_player_export as mpe
    monkeypatch.setattr(he, "BTBLEND_SERVE", True)
    monkeypatch.setattr(mpe, "_savant", lambda kind, year, side="batter": SAVANT)
    monkeypatch.setattr(bbt, "fetch_leaderboard", lambda season: BT_ROWS)
    board = _board()
    assert he._btblend_step(board, dict(HEM), 2026, log=lambda *a: None) == 4
    want, _ = bbt.served_values(bbt.savant_xwoba_map(SAVANT), HEM, bbt.composite_map(BT_ROWS))
    got = {r["mlbam"]: r["btblend_plus"] for r in board if "btblend_plus" in r}
    assert got == want


def test_flag_on_with_a_failed_source_ships_the_board_without_the_column(monkeypatch):
    import mlb_player_export as mpe

    def boom(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(he, "BTBLEND_SERVE", True)
    monkeypatch.setattr(mpe, "_savant", boom)
    board = _board()
    assert he._btblend_step(board, dict(HEM), 2026, log=lambda *a: None) == 0
    assert not any("btblend_plus" in r for r in board)


def test_the_exporter_has_one_call_site():
    src = inspect.getsource(he.export)
    assert src.count("_btblend_step(") == 1
    assert "btblend" not in src.replace("_btblend_step(scored[\"hitters\"], _hem_raw, season, log=log)", "")


# --------------------------------------------------------------------------- #
# the re-read lab's decision rule (gate section 6)
# --------------------------------------------------------------------------- #
def _ci(lo, hi):
    return {"gap_ci": {"mean": (lo + hi) / 2, "lo95": lo, "hi95": hi}}


def test_decision_rule_needs_both_conventions():
    import bat_tracking_served_lab as lab
    assert lab.decide({"v1": _ci(.001, .02), "v2": _ci(.002, .02)})["verdict"] == "PASS"
    assert lab.decide({"v1": _ci(.001, .02), "v2": _ci(-.01, .02)})["verdict"] == "FAIL"
    assert lab.decide({"v1": _ci(-.01, .02), "v2": _ci(-.01, .02)})["verdict"] == "FAIL"
    assert lab.decide({"v1": _ci(-.05, -.01), "v2": _ci(.001, .02)})["verdict"] == "REFUTED"
    assert lab.decide(None)["verdict"] == "INCOMPLETE"
    assert lab.decide({"v1": {"gap_ci": None}, "v2": None})["flip"] is False
    assert lab.SEED == 20261014 and lab.BOOT == 2000
    assert lab.OUT_PATH.name == "bat_tracking_served_eval.json"
