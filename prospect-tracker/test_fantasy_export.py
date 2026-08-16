# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Tests for fantasy_export.py helpers (synthetic inputs, no corpus build).

Covers the two data-shape/scoring fixes:
  * _name_from_links: player_links.json is {generated_at, byKey, byMlbam}; the
    mlbam->entry map is nested (string-keyed) under byMlbam, NOT at the top level.
  * _buy_sell: hitter luck_gap (~+/-50) and pitcher luck (~+/-0.05) are ~500x
    apart, so each side is scaled by its own spread before the combined sort;
    otherwise pitchers never reach either top-N list."""
from __future__ import annotations

import fantasy_export as fe


# ---- _name_from_links (fix 9: correct byMlbam nesting) ---------------------
def test_name_from_links_correct_nesting():
    links = {"generated_at": "x", "byKey": {}, "byMlbam": {
        "660271": {"name": "Shohei Ohtani", "key": "shohei_ohtani"}}}
    # int mlbam is coerced to the string key the map uses.
    assert fe._name_from_links(links, 660271) == "Shohei Ohtani"
    assert fe._name_from_links(links, "660271") == "Shohei Ohtani"


def test_name_from_links_missing_mlbam_returns_none():
    links = {"byMlbam": {"660271": {"name": "Shohei Ohtani"}}}
    assert fe._name_from_links(links, 111111) is None


def test_name_from_links_ignores_top_level_keys():
    # Regression guard for the old bug: the mlbam must NOT resolve off the
    # top-level dict (that path always missed -> dead fallback -> name=None).
    links = {"660271": {"name": "Wrong Path"}, "byMlbam": {}}
    assert fe._name_from_links(links, 660271) is None


def test_name_from_links_none_and_bad_shapes():
    assert fe._name_from_links(None, 660271) is None
    assert fe._name_from_links({}, 660271) is None
    assert fe._name_from_links({"byMlbam": None}, 660271) is None


def test_name_from_links_bare_string_and_missing_name():
    assert fe._name_from_links({"byMlbam": {"5": "Legacy Name"}}, 5) == "Legacy Name"
    assert fe._name_from_links({"byMlbam": {"5": {"key": "k"}}}, 5) is None


# ---- _player_luck (side-aware luck accessor) -------------------------------
def test_player_luck_side_accessor():
    hit = {"side": "hit", "skill": {"luck_gap": 12.0, "luck": 0.03}}
    pit = {"side": "pit", "skill": {"luck_gap": 12.0, "luck": 0.03}}
    assert fe._player_luck(hit) == 12.0    # hitter reads luck_gap
    assert fe._player_luck(pit) == 0.03    # pitcher reads luck
    assert fe._player_luck({"side": "hit", "skill": {}}) is None
    assert fe._player_luck({"side": "pit"}) is None


# ---- _buy_sell (fix 10: per-side scale normalization) ---------------------
def _mk_hit(mid, gap):
    return {"mlbam": mid, "side": "hit", "fpts_fgp": 300.0,
            "skill": {"luck_gap": gap}}


def _mk_pit(mid, luck):
    return {"mlbam": mid, "side": "pit", "fpts_fgp": 200.0,
            "skill": {"luck": luck}}


def _synthetic_pool():
    # Many hitters on the plus-stat scale (~+/-10) plus a few pitchers on the
    # wOBA-point scale (~+/-0.06). Raw magnitudes are ~150x apart.
    hitters = [_mk_hit(1000 + i, gap) for i, gap in
               enumerate([10, 8, 6, 4, 2, -2, -4, -6, -8, -10])]
    pitchers = [_mk_pit(2000 + i, luck) for i, luck in
                enumerate([0.06, 0.02, -0.02, -0.06])]
    return hitters + pitchers


def test_buy_sell_surfaces_pitchers_after_normalization():
    pool = _synthetic_pool()
    buy, sell = fe._buy_sell(pool, n=5)
    # Entries carry side as of 2026-07-31 (see the two-way regression below), so
    # read the id out rather than comparing against a bare int.
    buy_ids = [e["mlbam"] for e in buy]
    sell_ids = [e["mlbam"] for e in sell]
    # The most-unlucky pitcher (luck=+0.06) reaches the buy list, and the
    # most-lucky pitcher (luck=-0.06) reaches the sell list, despite raw
    # magnitudes ~150x smaller than the hitters'.
    assert 2000 in buy_ids, buy      # pitcher luck=+0.06
    assert 2003 in sell_ids, sell    # pitcher luck=-0.06


def test_buy_sell_raw_sort_would_bury_pitchers():
    # Contrast check: a NAIVE raw combined sort keeps pitchers out of the top-5
    # entirely (this is exactly the bug the normalization fixes).
    pool = _synthetic_pool()
    raw_buy = [p["mlbam"] for p in
               sorted(pool, key=lambda p: -fe._player_luck(p))[:5]]
    assert all(m < 2000 for m in raw_buy), raw_buy   # all hitters, no pitcher


def test_buy_sell_sign_preserved():
    # Scaling (not mean-centering) preserves sign: buy rows are unlucky (luck>0),
    # sell rows overperforming (luck<0), so the displayed gap stays consistent
    # with the Buy/Sell labels.
    pool = _synthetic_pool()
    # Key by (mlbam, side) - the same fix the client got on 2026-07-31. Keying on
    # mlbam alone is what silently collapsed two-way players.
    by_id = {(p["mlbam"], p["side"]): p for p in pool}
    buy, sell = fe._buy_sell(pool, n=5)
    assert all(fe._player_luck(by_id[(e["mlbam"], e["side"])]) > 0 for e in buy), buy
    assert all(fe._player_luck(by_id[(e["mlbam"], e["side"])]) < 0 for e in sell), sell


def test_buy_sell_respects_fpts_gate():
    # fpts_fgp <= 20 excludes a player from the luckable pool.
    pool = [_mk_hit(1, 40.0), _mk_pit(2, 0.09)]
    pool[0]["fpts_fgp"] = 10.0     # below the >20 gate
    buy, sell = fe._buy_sell(pool, n=5)
    assert 1 not in buy and 1 not in sell


# ---- dynasty prospect ranking (eFV-derived) -------------------------------
def _mk_ts_row(key, name, mid, pos="SS", org="BOS", eta_year=2026):
    eta = {"year": eta_year} if eta_year is not None else None
    return {"player_key": key, "player_name": name, "mlbam_id": mid,
            "position": pos, "org": org, "eta": eta}


def _mk_xfv_row(q, star=0.10, bust=0.10, surplus=20.0, band=(0.0, 60.0)):
    return {"xfv_grade_quantile": q, "p_bucket": {"star": star, "bust": bust},
            "p_bust": bust, "surplus_mm": surplus,
            "band_p10_mm": band[0], "band_p90_mm": band[1]}


def _dynasty_inputs():
    ts = {"players": [
        _mk_ts_row("elite", "Elite Bat", 1, eta_year=2026),
        _mk_ts_row("mid", "Mid Arm", 2, pos="SP", eta_year=2027),
        _mk_ts_row("far", "Far Away", 3, eta_year=2029),
        _mk_ts_row("nomlb", "No Mlbam", None, eta_year=2026),   # dropped: no mlbam
        _mk_ts_row("noxfv", "No Efv Match", 9, eta_year=2026),  # dropped: no xfv row
    ]}
    xfv = {"by_player": {
        "elite": _mk_xfv_row(65.0, star=0.30, bust=0.03, surplus=95.0, band=(20.0, 190.0)),
        "mid": _mk_xfv_row(50.0, star=0.10, bust=0.15, surplus=25.0, band=(0.0, 70.0)),
        "far": _mk_xfv_row(48.0, star=0.08, bust=0.20, surplus=15.0, band=(0.0, 50.0)),
        # "noxfv" intentionally absent so that ts row is dropped.
    }}
    return ts, xfv


def test_dynasty_ordering_and_shape():
    ts, xfv = _dynasty_inputs()
    rows = fe._dynasty_prospects(ts, 2026, xfv=xfv)
    # Only the three prospects with BOTH an mlbam and an xfv row survive.
    assert [r["mlbam"] for r in rows] == [1, 2, 3], rows
    # Sorted by composite score descending, ranks are sequential from 1.
    scores = [r["score"] for r in rows]
    assert scores == sorted(scores, reverse=True), scores
    assert [r["rank"] for r in rows] == [1, 2, 3]
    # Shape: every expected display field is present on each row.
    keys = {"mlbam", "name", "org", "pos", "eta", "efv", "star", "bust",
            "surplus", "band", "score", "rank", "tier"}
    for r in rows:
        assert keys <= set(r), set(r)
    # eFV outcome band is passed through as [p10, p90] $M.
    assert rows[0]["band"] == [20.0, 190.0]
    assert rows[0]["tier"] == "Elite"


def test_dynasty_efv_is_primary_driver():
    """The BOARD grade drives the rank (2026-08-16 driver swap), not the retired
    quantile. The fixture makes the two scales disagree on purpose: 'lo' wins on
    the quantile (62 vs 45) and loses on the board grade (48 vs 61), so a mutant
    that reverts the score driver to xfv_grade_quantile ranks lo first (66.8 vs
    49.8) and fails both assertions. Hand-computed with the shared weights
    (star .10, bust .10, eta 2026 in season 2026 so proximity 1.0, surplus 20):
        lo: 48 + 10(.10) - 6(.10) + 4(1.0) + 2(.20) = 48 + 1 - .6 + 4 + .4 = 52.8
        hi: 61 + 1 - .6 + 4 + .4 = 65.8"""
    ts = {"players": [_mk_ts_row("lo", "Low Board", 1),
                      _mk_ts_row("hi", "High Board", 2)]}
    xfv = {"by_player": {"lo": dict(_mk_xfv_row(62.0), xfv_grade=48.0),
                         "hi": dict(_mk_xfv_row(45.0), xfv_grade=61.0)}}
    rows = fe._dynasty_prospects(ts, 2026, xfv=xfv)
    assert [r["mlbam"] for r in rows] == [2, 1], rows
    assert [r["score"] for r in rows] == [65.8, 52.8], rows
    # driver and displayed column are the same number now
    assert [r["efv"] for r in rows] == [61.0, 48.0], rows


def test_dynasty_eta_proximity_breaks_ties():
    # Identical eFV/star/bust/surplus: the nearer-ETA prospect ranks higher.
    ts = {"players": [_mk_ts_row("soon", "Soon", 1, eta_year=2026),
                      _mk_ts_row("late", "Late", 2, eta_year=2030)]}
    xfv = {"by_player": {"soon": _mk_xfv_row(55.0), "late": _mk_xfv_row(55.0)}}
    rows = fe._dynasty_prospects(ts, 2026, xfv=xfv)
    assert [r["mlbam"] for r in rows] == [1, 2], rows
    assert rows[0]["score"] > rows[1]["score"]


def test_dynasty_excludes_rows_without_efv():
    # A joined xfv row missing any grade is dropped.
    ts = {"players": [_mk_ts_row("nograde", "No Grade", 1)]}
    xfv = {"by_player": {"nograde": {"p_bucket": {"star": 0.2}}}}
    assert fe._dynasty_prospects(ts, 2026, xfv=xfv) == []


def test_dynasty_falls_back_to_xfv_grade():
    # A row carrying only xfv_grade still ranks and displays: xfv_grade is the
    # first link in _board_grade's chain (board_value reads it when the side
    # scale is off), so it is the driver, not a fallback, since 2026-08-16.
    ts = {"players": [_mk_ts_row("g", "Grade Only", 1)]}
    xfv = {"by_player": {"g": {"xfv_grade": 52.0, "p_bucket": {}, "p_bust": 0.1}}}
    rows = fe._dynasty_prospects(ts, 2026, xfv=xfv)
    assert len(rows) == 1 and rows[0]["efv"] == 52.0


def test_dynasty_empty_on_bad_inputs():
    assert fe._dynasty_prospects(None, 2026, xfv={"by_player": {}}) == []
    assert fe._dynasty_prospects({"players": []}, 2026, xfv={}) == []
    assert fe._dynasty_prospects({"players": [_mk_ts_row("a", "A", 1)]}, 2026,
                                 xfv={"by_player": None}) == []


def test_dynasty_tier_buckets():
    assert fe._dynasty_tier(1) == "Elite"
    assert fe._dynasty_tier(10) == "Elite"
    assert fe._dynasty_tier(11) == "Tier 1"
    assert fe._dynasty_tier(25) == "Tier 1"
    assert fe._dynasty_tier(26) == "Tier 2"
    assert fe._dynasty_tier(50) == "Tier 2"
    assert fe._dynasty_tier(51) == "Tier 3"
    assert fe._dynasty_tier(100) == "Tier 3"
    assert fe._dynasty_tier(101) == "Tier 4"
    assert fe._dynasty_tier(200) == "Tier 4"
    assert fe._dynasty_tier(201) == "Depth"


def test_dynasty_respects_top_n_cap():
    ts = {"players": [_mk_ts_row("p%d" % i, "P%d" % i, i) for i in range(1, 21)]}
    xfv = {"by_player": {"p%d" % i: _mk_xfv_row(40.0 + i) for i in range(1, 21)}}
    rows = fe._dynasty_prospects(ts, 2026, xfv=xfv, n=5)
    assert len(rows) == 5
    # Cap keeps the five highest-eFV prospects (grades 60..56 -> ids 20..16).
    assert [r["mlbam"] for r in rows] == [20, 19, 18, 17, 16], rows


def test_buy_sell_entries_carry_side_for_two_way_players():
    """Regression, 2026-07-31. Every section list is bare mlbam ids, which is fine
    for the single-sided sections (a renderer of ROS Hitters knows it wants "hit").
    buy/sell is the one COMBINED ranking, so a two-way player's two records are
    both eligible and a bare id cannot be resolved. It was being resolved by a
    client map keyed on mlbam alone, last-write-wins, and "pit" is appended
    second: Shohei Ohtani rendered his 172.6 PITCHER points on the ROS Hitters
    board and a pitcher skill object under a row ranked in on hitter luck.
    Entries now carry their own side."""
    def mk(mlbam, side, luck, fpts):
        skill = {"luck_gap": luck} if side == "hit" else {"luck": luck}
        return {"mlbam": mlbam, "side": side, "fpts_fgp": fpts, "skill": skill,
                "pos": "DH" if side == "hit" else "SP"}
    players = [
        mk(1, "hit", 40.0, 300.0), mk(2, "hit", -35.0, 250.0),
        mk(3, "pit", 0.04, 200.0), mk(4, "pit", -0.05, 190.0),
        # the two-way player: BOTH records eligible, different sides
        mk(99, "hit", 31.0, 284.8), mk(99, "pit", 0.01, 172.6),
    ]
    buy, sell = fe._buy_sell(players, n=6)
    for entry in list(buy) + list(sell):
        assert isinstance(entry, dict), f"entry must carry side, got {entry!r}"
        assert entry.get("side") in ("hit", "pit"), entry
        assert entry.get("mlbam") is not None, entry
    # The two-way id must be resolvable to a SPECIFIC record, which is the whole
    # point: a bare 99 could mean either row.
    two_way = [e for e in buy + sell if e["mlbam"] == 99]
    assert two_way, "two-way player should rank on at least one side"
    for e in two_way:
        match = [p for p in players if p["mlbam"] == 99 and p["side"] == e["side"]]
        assert len(match) == 1, e


def test_single_sided_sections_stay_bare_ids():
    """The side-carrying shape is deliberately scoped to buy/sell. The other
    sections are single-sided by construction and their renderers supply the side,
    so widening the shape everywhere would be churn with no defect behind it."""
    import inspect
    src = inspect.getsource(fe.build_sections)
    for name in ("ros_hitter", "ros_sp", "ros_rp"):
        assert f'"{name}": rank(' in src, (
            f"{name} should still be built by rank() as a bare-id list; if this "
            "changed, assets/fantasy.js scored()/recOf() must change with it")


if __name__ == "__main__":
    import sys
    mod = sys.modules[__name__]
    fns = [f for n, f in vars(mod).items() if n.startswith("test_") and callable(f)]
    for f in fns:
        f()
    print(f"ALL {len(fns)} fantasy_export tests PASS")
