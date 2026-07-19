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
    # The most-unlucky pitcher (luck=+0.06) reaches the buy list, and the
    # most-lucky pitcher (luck=-0.06) reaches the sell list, despite raw
    # magnitudes ~150x smaller than the hitters'.
    assert 2000 in buy, buy      # pitcher luck=+0.06
    assert 2003 in sell, sell    # pitcher luck=-0.06


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
    by_id = {p["mlbam"]: p for p in pool}
    buy, sell = fe._buy_sell(pool, n=5)
    assert all(fe._player_luck(by_id[m]) > 0 for m in buy), buy
    assert all(fe._player_luck(by_id[m]) < 0 for m in sell), sell


def test_buy_sell_respects_fpts_gate():
    # fpts_fgp <= 20 excludes a player from the luckable pool.
    pool = [_mk_hit(1, 40.0), _mk_pit(2, 0.09)]
    pool[0]["fpts_fgp"] = 10.0     # below the >20 gate
    buy, sell = fe._buy_sell(pool, n=5)
    assert 1 not in buy and 1 not in sell


if __name__ == "__main__":
    import sys
    mod = sys.modules[__name__]
    fns = [f for n, f in vars(mod).items() if n.startswith("test_") and callable(f)]
    for f in fns:
        f()
    print(f"ALL {len(fns)} fantasy_export tests PASS")
