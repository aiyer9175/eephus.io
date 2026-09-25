# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Tests for fantasy_export.py helpers (synthetic inputs, no corpus build).

Covers the two data-shape/scoring fixes:
  * _name_from_links: player_links.json is {generated_at, byKey, byMlbam}; the
    mlbam->entry map is nested (string-keyed) under byMlbam, NOT at the top level.
  * _buy_sell: each side is scaled by its own spread before the combined
    sort. Hitter luck_gap was xHEM+ minus HEM+ (~+/-50) until 2026-09-24,
    ~500x wider than pitcher luck (~+/-0.05), and pitchers never reached
    either top-N list; both are wOBA points now, but the per-side scaling
    stays and the synthetic pools below still pin it on unequal scales."""
from __future__ import annotations

import json
from datetime import date

import pytest

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


# ---- season mode, pool floors and the empty-overwrite guard ---------------
# 2026-09-24 (M11-01). The floors read the rest-of-season remainder, so the
# pool emptied before the season ended and the 2026-09-23 build served 0
# players; export() wrote that over a populated file.
def test_season_mode_reads_the_calendar_then_the_pa_ratio():
    end = "2026-09-27"
    assert fe.season_mode(0.976, today=date(2026, 9, 24),
                          regular_season_end=end) == fe.MODE_ROS
    assert fe.season_mode(0.976, today=date(2026, 9, 27),
                          regular_season_end=end) == fe.MODE_ROS
    # The day after the last scheduled game, whatever the PA ratio says.
    assert fe.season_mode(0.990, today=date(2026, 9, 28),
                          regular_season_end=end) == fe.MODE_NEXT_SEASON
    # No calendar: only a ratio at the clamp is a finished season.
    assert fe.season_mode(0.976, today=date(2026, 11, 1)) == fe.MODE_ROS
    assert fe.season_mode(1.0, today=date(2026, 11, 1)) == fe.MODE_NEXT_SEASON


_HIT_PROJ = {"pt_proj": 600.0, "bb_pct": 0.08, "k_pct": 0.22, "hr_pa": 0.03,
             "babip": 0.300, "iso": 0.170}
_SP_PROJ = {"pt_proj": 709.5, "ip_proj": 165.0, "k_pct": 0.25, "bb_pct": 0.08,
            "hr_bf": 0.03, "fip_proj": 3.80}
_RP_PROJ = {"pt_proj": 258.0, "ip_proj": 60.0, "k_pct": 0.27, "bb_pct": 0.09,
            "hr_bf": 0.025, "fip_proj": 3.60}


def _stub_pool(monkeypatch, frac, projs=None):
    """A three-player corpus (a regular, a starter, a 60-inning reliever)
    through the real build_players, with every file and network read stubbed."""
    league = {2025: {"_total_pa": 1000.0}, 2026: {"_total_pa": 1000.0 * frac}}
    corpus = {"league": league,
              "hit": [{"mlbam": 1, "season": 2026, "pa": 600, "role": "SS", "age": 27}],
              "pit": [{"mlbam": 2, "season": 2026, "ip": 165, "role": "SP", "age": 28},
                      {"mlbam": 3, "season": 2026, "ip": 60, "role": "RP", "age": 29}]}
    projs = projs or {(1, "hit"): _HIT_PROJ, (2, "pit"): _SP_PROJ,
                      (3, "pit"): _RP_PROJ}

    def _proj(hist, side, target, curves, lg, age, role=None, in_progress=None):
        return dict(projs[(hist[0]["mlbam"], side)], role=role)
    monkeypatch.setattr(fe.fp, "build_corpus", lambda: corpus)
    monkeypatch.setattr(fe.fp, "fitted_models", lambda c, cur: ({}, {}))
    monkeypatch.setattr(fe.fp, "project_player", _proj)
    monkeypatch.setattr(fe, "_sb_rate_by_mlbam", lambda: {})
    monkeypatch.setattr(fe, "_rp_saves_holds", lambda: {3: {"sv": 20, "hld": 2}})
    monkeypatch.setattr(fe, "_ip_per_gs", lambda: {})
    monkeypatch.setattr(fe, "_names_from_leaderboards", lambda: {})
    monkeypatch.setattr(fe, "_load_json", lambda name: None)
    monkeypatch.setattr(fe, "_enrich", lambda players: None)
    monkeypatch.setattr(fe, "_active_roster_ids", lambda: None)


_CAL = {"start": "2026-03-25", "end": "2026-09-27"}


def test_the_pool_survives_the_last_week_of_the_season(monkeypatch):
    """At fraction 0.976 the old floors (20 ROS PA, 8 ROS IP) dropped all three:
    600 PA x 0.024 = 14.4 and 165 IP x 0.024 = 4.0."""
    _stub_pool(monkeypatch, 0.976)
    out = fe.build_players(today=date(2026, 9, 24), calendar=_CAL)
    assert out["mode"] == fe.MODE_ROS and out["target_season"] == 2026
    assert out["n_players"] == 3, out["players"]
    by = {p["mlbam"]: p for p in out["players"]}
    assert by[1]["ros"]["pa"] == round(600 * (1 - 0.976), 1)
    assert by[3]["pos"] == "RP" and by[3]["ros"]["ip"] > 0
    # Saves pace scales to what is left, off the season-to-date count.
    assert by[3]["ros"]["sv"] == round(20 * (1 - 0.976) / 0.976, 1)


def test_after_the_season_the_pool_serves_next_seasons_full_line(monkeypatch):
    _stub_pool(monkeypatch, 1.0)
    out = fe.build_players(today=date(2026, 10, 15), calendar=_CAL)
    assert out["mode"] == fe.MODE_NEXT_SEASON and out["target_season"] == 2027
    assert out["n_players"] == 3
    by = {p["mlbam"]: p for p in out["players"]}
    assert by[1]["ros"]["pa"] == 600.0          # the full season, not zero
    assert by[2]["ros"]["ip"] == 165.0
    assert by[3]["ros"]["sv"] == 20.0           # one full season of the pace
    assert all((p["fpts_fgp"] or 0) > 0 for p in out["players"])


def test_the_floors_read_full_season_playing_time(monkeypatch):
    """A 15-PA bench bat and a 5-inning arm stay out in every mode."""
    _stub_pool(monkeypatch, 0.5, projs={
        (1, "hit"): dict(_HIT_PROJ, pt_proj=15.0),
        (2, "pit"): dict(_SP_PROJ, ip_proj=5.0, pt_proj=21.5),
        (3, "pit"): _RP_PROJ})
    out = fe.build_players(today=date(2026, 7, 1), calendar=_CAL)
    assert [p["mlbam"] for p in out["players"]] == [3]


def test_export_refuses_to_replace_a_populated_file_with_an_empty_one(
        monkeypatch, tmp_path):
    out_path = tmp_path / "fantasy.json"
    prev = {"players": [{"mlbam": 1, "side": "hit"}, {"mlbam": 2, "side": "pit"}]}
    out_path.write_text(json.dumps(prev), encoding="utf-8")
    monkeypatch.setattr(fe, "OUT_PATH", out_path)
    monkeypatch.setattr(fe, "build_players", lambda limit=None: {
        "season": 2026, "season_fraction": 0.976, "mode": fe.MODE_ROS,
        "n_players": 0, "players": []})
    monkeypatch.setattr(fe, "_attach_schedule", lambda payload: None)
    monkeypatch.setattr(fe, "build_sections", lambda payload: {})
    red = []
    monkeypatch.setattr(fe, "_record_ingest_safe",
                        lambda source, **kw: red.append((source, kw)))
    with pytest.raises(ValueError):
        fe.export(log=None)
    assert json.loads(out_path.read_text(encoding="utf-8")) == prev
    assert red and red[0][0] == "fantasy_corpus" and red[0][1]["ok"] is False


def test_buy_sell_gate_reads_the_full_season_line():
    """10 rest-of-season points at share 0.1 is a 100-point player."""
    pool = [_mk_hit(1, 40.0), _mk_pit(2, 0.09)]
    pool[0]["fpts_fgp"] = 10.0
    buy, _sell = fe._buy_sell(pool, n=5, share=0.1)
    assert 1 in [e["mlbam"] for e in buy]
    assert fe._line_share({"mode": fe.MODE_NEXT_SEASON, "season_fraction": 1.0}) == 1.0
    assert abs(fe._line_share({"mode": fe.MODE_ROS, "season_fraction": 0.9}) - 0.1) < 1e-9
    assert fe._line_share({}) == 1.0


# ---- closer grid population (2026-09-24, M11-03) ---------------------------
def _rp(mid, team, gmli, sv=0, rem=100, qualified=True):
    return {"mlbam": mid, "name": f"Arm {mid}", "team": team, "gmli": gmli,
            "saves": sv, "rem_plus": rem, "qualified": qualified}


def test_closer_depth_keys_canonical_clubs_and_skips_thin_samples():
    board = {"relievers": [
        _rp(1, "CWS", 1.6, sv=10), _rp(2, "CHW", 1.2),     # one club, two codes
        _rp(3, "SD", 1.9, sv=37), _rp(4, "WSH", 1.7, sv=12),
        _rp(5, "TB", 3.38, qualified=False),                # one appearance
        _rp(6, "TB", 1.67, sv=40),
        _rp(7, "TB", None, sv=0),                           # no gmLI
    ]}
    depth, rows = fe._closer_depth(board)
    assert sorted(depth) == ["CHW", "SDP", "TBR", "WSN"]
    assert depth["CHW"] == [1, 2]
    assert depth["TBR"] == [6]
    assert rows["6"] == {"name": "Arm 6", "team": "TBR", "gmli": 1.67,
                         "saves": 40, "rem_plus": 100}


def test_closer_grid_covers_every_club_on_the_served_board():
    """Off the served reliever board and nothing else: 30 clubs, canonical
    codes, every arm qualified with a gmLI, whatever the projection pool
    holds (the 2026-09-23 pool held nothing)."""
    lb = fe._load_json("bullpen_leaderboards.json")
    if not lb or not lb.get("relievers"):
        pytest.skip("no bullpen_leaderboards.json in this checkout")
    depth, rows = fe._closer_depth(lb)
    assert len(depth) == 30, sorted(depth)
    assert all(fe._canon_org(k) == k for k in depth)
    by_id = {int(r["mlbam"]): r for r in lb["relievers"] if r.get("mlbam")}
    for ids in depth.values():
        assert 1 <= len(ids) <= 5
        for m in ids:
            assert by_id[m].get("qualified") and by_id[m].get("gmli") is not None
            assert str(m) in rows


def _light_sections(monkeypatch):
    monkeypatch.setattr(fe, "_teams_context", lambda: {})
    monkeypatch.setattr(fe, "_load_json", lambda name: None)
    monkeypatch.setattr(fe, "_callup_watch", lambda ts: [])
    monkeypatch.setattr(fe, "_dynasty_prospects", lambda ts, season: [])
    monkeypatch.setattr(fe, "_closer_depth", lambda: ({}, {}))


_SCHED = {"games": [{"date": "2026-09-24",
                     "home": {"org": "BOS", "probable": {"mlbam": 9}},
                     "away": {"org": "NYY", "probable": None}}],
          "two_start": {"9": [{"date": "2026-09-24", "opp_org": "NYY"},
                              {"date": "2026-09-29", "opp_org": "TOR",
                               "projected": True}]}}


def test_an_unpriced_two_start_row_carries_no_total(monkeypatch):
    _light_sections(monkeypatch)
    sec = fe.build_sections({"players": [], "mode": fe.MODE_ROS,
                             "season_fraction": 0.9, "schedule": _SCHED})
    assert sec["two_start"][0]["total_fgp"] is None     # not a projection of 0.0
    assert sec["daily_streamers"] == []


def test_next_season_mode_serves_no_slate_sections(monkeypatch):
    _light_sections(monkeypatch)
    sp = {"mlbam": 9, "side": "pit", "pos": "SP", "fpts_fgp": 500.0,
          "ros": {"gs": 30.0}}
    sec = fe.build_sections({"players": [sp], "mode": fe.MODE_NEXT_SEASON,
                             "season_fraction": 1.0, "schedule": _SCHED})
    assert sec["daily_streamers"] == [] and sec["two_start"] == []
    assert sec["ros_sp"] == [9]


def test_closer_rows_ride_only_for_arms_the_pool_lacks(monkeypatch):
    _light_sections(monkeypatch)
    rows = {"7": {"name": "Pooled", "team": "BOS", "gmli": 1.8, "saves": 30,
                  "rem_plus": 120},
            "8": {"name": "Unpooled", "team": "BOS", "gmli": 1.5, "saves": 2,
                  "rem_plus": 105}}
    monkeypatch.setattr(fe, "_closer_depth", lambda: ({"BOS": [7, 8]}, rows))
    rp = {"mlbam": 7, "side": "pit", "pos": "RP", "fpts_fgp": 50.0, "ros": {}}
    sec = fe.build_sections({"players": [rp], "mode": fe.MODE_ROS,
                             "season_fraction": 0.5, "schedule": {}})
    assert sec["closer_depth"] == {"BOS": [7, 8]}
    assert list(sec["closer_rows"]) == ["8"]
    empty = fe.build_sections({"players": [], "mode": fe.MODE_ROS,
                               "season_fraction": 0.5, "schedule": {}})
    assert sorted(empty["closer_rows"]) == ["7", "8"]


# ---- one club code set (M11-04, 2026-09-25) --------------------------------
def test_enrich_keys_every_player_by_the_canonical_club(monkeypatch):
    """The leaderboards key clubs MLB-style (AZ, CWS, KC, SD, SF, TB, WSH) and
    the detail fallback mixes both families; team_next7 and closer_depth key
    the canonical codes, so a raw copy dropped the card's next-7 strip for
    every player on those seven clubs."""
    boards = {"hitter_leaderboards.json": {1: {"team": "AZ"}},
              "starter_leaderboards.json": {2: {"team": "CWS"}},
              "bullpen_leaderboards.json": {3: {"team": "WSH"}}}
    monkeypatch.setattr(fe, "_lb_index", lambda fname, key: boards[fname])
    monkeypatch.setattr(fe, "_elig_positions", lambda: {})
    monkeypatch.setattr(fe, "_hitter_elig", lambda mid, elig, detail: None)
    monkeypatch.setattr(fe, "_detail_by_mlbam",
                        lambda: {5: {"team": "KC", "name": "Detail Only"}})
    players = [{"mlbam": 1, "side": "hit", "pos": "H"},
               {"mlbam": 2, "side": "pit", "pos": "SP"},
               {"mlbam": 3, "side": "pit", "pos": "RP"},
               {"mlbam": 5, "side": "hit", "pos": "H"}]
    fe._enrich(players)
    assert [p["team"] for p in players] == ["ARI", "CHW", "WSN", "KCR"]


def test_two_start_row_team_is_canonical(monkeypatch):
    _light_sections(monkeypatch)
    sched = {"games": [], "two_start": {"9": [
        {"date": "2026-09-24", "opp_org": "NYY", "team_org": "SD"},
        {"date": "2026-09-29", "opp_org": "TOR", "team_org": "SD"}]}}
    sec = fe.build_sections({"players": [], "mode": fe.MODE_ROS,
                             "season_fraction": 0.9, "schedule": sched})
    assert sec["two_start"][0]["team"] == "SDP"


def test_refresh_live_rekeys_an_old_corpus_to_canonical_clubs(monkeypatch, tmp_path):
    payload = {"players": [{"mlbam": 1, "side": "hit", "team": "AZ"},
                           {"mlbam": 2, "side": "pit", "team": "TB"},
                           {"mlbam": 3, "side": "pit", "team": "BOS"}],
               "schedule": {}}
    monkeypatch.setattr(fe, "_load_json",
                        lambda name: payload if name == "fantasy.json" else None)
    monkeypatch.setattr(fe, "_active_roster_ids", lambda: None)
    monkeypatch.setattr(fe, "_restamp_elig", lambda p, log=None: 0)
    monkeypatch.setattr(fe, "_attach_schedule", lambda p: None)
    monkeypatch.setattr(fe, "build_sections", lambda p: {})
    monkeypatch.setattr(fe, "update_two_start_ledger",
                        lambda *a, **k: {"projected_added": 0, "grades_added": 0,
                                         "n_rows": 0})
    out = tmp_path / "fantasy.json"
    monkeypatch.setattr(fe, "OUT_PATH", out)
    fe.refresh_live(log=None)
    got = json.loads(out.read_text(encoding="utf-8"))
    assert [p["team"] for p in got["players"]] == ["ARI", "TBR", "BOS"]


# ---- home or road on the slate sections (M11-05, 2026-09-25) --------------
def test_streamer_rows_and_two_start_legs_say_which_side_starts(monkeypatch):
    """Every streamer and two-start leg printed "@" because the rows carried
    no side; half of them were home starts."""
    _light_sections(monkeypatch)
    sp = {"mlbam": 9, "side": "pit", "pos": "SP", "fpts_fgp": 300.0,
          "ros": {"gs": 10.0}}
    sched = {"games": [{"date": "2026-09-24",
                        "home": {"org": "BOS", "probable": {"mlbam": 9}},
                        "away": {"org": "NYY", "probable": None}},
                       {"date": "2026-09-26",
                        "home": {"org": "TOR", "probable": None},
                        "away": {"org": "BOS", "probable": {"mlbam": 9}}}],
             "two_start": {"9": [{"date": "2026-09-24", "opp_org": "NYY",
                                  "is_home": True},
                                 {"date": "2026-09-29", "opp_org": "TOR",
                                  "is_home": False, "projected": True}]}}
    sec = fe.build_sections({"players": [sp], "mode": fe.MODE_ROS,
                             "season_fraction": 0.9, "schedule": sched})
    by_date = {r["date"]: r for r in sec["daily_streamers"]}
    assert by_date["2026-09-24"]["is_home"] is True
    assert by_date["2026-09-26"]["is_home"] is False
    legs = sec["two_start"][0]["legs"]
    assert [leg["is_home"] for leg in legs] == [True, False]


if __name__ == "__main__":
    import sys
    mod = sys.modules[__name__]
    import inspect
    # Fixture-taking tests (monkeypatch, tmp_path) run under pytest only.
    fns = [f for n, f in vars(mod).items() if n.startswith("test_") and callable(f)
           and not inspect.signature(f).parameters]
    for f in fns:
        f()
    print(f"ALL {len(fns)} fantasy_export tests PASS")
