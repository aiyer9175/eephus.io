# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eWAR and the recorded wOBA on the four history boards (MLB Stats overhaul,
wave 6: E6 and E8, owner decision O5).

The live boards and the history boards fail in opposite directions, which is why
this join needed its own rules rather than a copy of the live one:

  * A HISTORY ROW IS A PAST SEASON, so the value must come from THAT season's
    cell. A join that read the live season would print 2026 numbers under a 2021
    pill and nothing on the page would say so.
  * THE RATES DO NOT TRAVEL AND THE COUNT DOES. WAR/IP+ and WAR/PA+ are
    standardised on the LIVE pool, so they stay off these boards; eWAR is a
    season count, so it goes on. The two facts live in one place (the JS drop
    lists, pinned by test_war_rate_plus) and are asserted here on the export
    side, where the values are actually produced.
  * A SEASON THE ARTIFACT BARELY COVERS must refuse ALONE. Refusing the whole
    file would blank four good years over one bad one; stamping it anyway would
    print a handful of numbers that read as a real column.
  * THE SIDE IS THE BOARD'S SIDE on the three player boards and BOTH SIDES on
    Defense, exactly as on the live ones, so a two-way player's past season
    reads the way his present one does.
  * E8: the hitter history row served the SHRUNK wOBA under a bare "wOBA"
    header. The recorded value now ships beside it, so the label repair the live
    board got is true on a past season too.

THE FOUR CALL SITES ARE DRIVEN THROUGH THE EXPORT, not only through the shared
helper. The wave's deliverable is the join on four boards, and a helper's unit
tests say nothing about whether a board calls it, passes its own side, or passes
the season it is building. The `_BOARDS` table runs all four exports offline and
asserts on the SERVED payload.

No network and no artifact: the side map, the season lines and the defense
season scorer are injected, so these run anywhere.
"""
from __future__ import annotations

import pytest

import bullpen_export as be
import defense_export as de
import hem_plus
import hitter_export as he
import starter_export as se


def _quiet(*_a, **_k):
    return None


#: "the WAR read itself fails", as a war map a board builder can be handed.
_BROKEN = object()


def _map(season=2026, **sides):
    """{mlbam: {season: {"bat": x, "pit": y}}}, the side_war_by_season shape."""
    out: dict = {}
    for side, by_id in sides.items():
        for mid, v in by_id.items():
            out.setdefault(int(mid), {}).setdefault(int(season), {})[side] = v
    return out


def _merge(*maps):
    out: dict = {}
    for m in maps:
        for mid, by_season in m.items():
            for season, cell in by_season.items():
                out.setdefault(mid, {}).setdefault(season, {}).update(cell)
    return out


def _patch_map(monkeypatch, war_map):
    if war_map is _BROKEN:
        def _boom():
            raise RuntimeError("artifact unreadable")
        monkeypatch.setattr(be, "_side_war_by_season", _boom)
        return
    monkeypatch.setattr(be, "_side_war_by_season", lambda: war_map)


def _rows(n, *, first=1):
    return [{"mlbam": first + i, "name": f"P {first + i}"} for i in range(n)]


# ------------------------------------------------- E6: the season is the season

def test_a_history_row_carries_that_seasons_ewar_not_the_live_one(monkeypatch):
    """The join key is (mlbam, season). A board built for 2021 that read the
    live cell would print this year's eWAR under a 2021 pill, and no column
    title on the page says which season a number came from."""
    war = _merge(_map(2021, pit={1: 1.4, 2: 0.7}),
                 _map(2026, pit={1: 5.9, 2: 6.1}))
    _patch_map(monkeypatch, war)
    rows = [{"mlbam": 1}, {"mlbam": 2}]
    meta = be.stamp_history_war(rows, 2021, side="pit")
    assert [r["war"] for r in rows] == [1.4, 0.7]
    assert meta["season"] == 2021 and meta["n_stamped"] == 2 and meta["available"]


def test_the_side_is_the_boards_side_on_a_past_season(monkeypatch):
    """A two-way player is his BATTING side on the hitter history board and his
    PITCHING side on the two pitcher ones, never the sum: the same rule the
    live boards hold to, so his 2021 reads the way his 2026 does."""
    _patch_map(monkeypatch, _map(2021, bat={9: 3.5}, pit={9: 2.7}))
    on_hitters = [{"mlbam": 9}]
    on_pitchers = [{"mlbam": 9}]
    be.stamp_history_war(on_hitters, 2021, side="bat")
    be.stamp_history_war(on_pitchers, 2021, side="pit")
    assert on_hitters[0]["war"] == 3.5
    assert on_pitchers[0]["war"] == 2.7


def test_an_uncovered_history_row_is_blank_and_a_zero_is_a_value(monkeypatch):
    """Absent iff no cell for that (player, season). A 0.0 is a real
    replacement-level season and prints; it is never a negative zero, and a row
    the artifact does not cover carries no key at all, which is what lets the
    page drop an uncovered column instead of rendering one of blanks."""
    covered = {i: 1.0 for i in range(1, 9)}
    covered[3] = -0.04          # rounds to zero
    _patch_map(monkeypatch, _map(2021, pit=covered))
    rows = _rows(10)            # ids 1..10; 9 and 10 uncovered
    rows.append({"name": "no id at all"})
    meta = be.stamp_history_war(rows, 2021, side="pit")
    assert rows[2]["war"] == 0.0 and str(rows[2]["war"]) == "0.0"
    assert "war" not in rows[8] and "war" not in rows[9] and "war" not in rows[10]
    assert meta["n_stamped"] == 8 and meta["n_with_id"] == 10


def test_a_history_row_needs_no_denominator(monkeypatch):
    """The WAR-RATE columns gate on a positive denominator because they DIVIDE
    by it, and implementer constraint (b) of the spec is written for them. The
    constraint is REVERSED on these four boards on purpose (stamp_history_war's
    docstring states it, and E3 and E4 already stamp with no such gate): a row
    whose innings did not survive the history projection still carries its
    count, because nothing here divides by them."""
    _patch_map(monkeypatch, _map(2021, pit={1: 1.4, 2: 0.9}))
    rows = [{"mlbam": 1, "ip": 0.0}, {"mlbam": 2}]
    be.stamp_history_war(rows, 2021, side="pit")
    assert rows[0]["war"] == 1.4 and rows[1]["war"] == 0.9


def test_a_season_the_artifact_barely_covers_refuses_alone(monkeypatch):
    """Three covered arms in sixty is the degenerate fetch score_war_rate
    refuses on, and this refuses with it. PER SEASON: refusing the whole file
    would blank four good years over one bad one, and the refusal is named in
    the payload so "0 stamped" is never read as a coverage fact."""
    war = _merge(_map(2020, pit={1: 1.0, 2: 1.0, 3: 1.0}),
                 _map(2021, pit={i: 1.0 for i in range(1, 61)}))
    _patch_map(monkeypatch, war)
    thin, full = _rows(60), _rows(60)
    thin_meta = be.stamp_history_war(thin, 2020, side="pit")
    full_meta = be.stamp_history_war(full, 2021, side="pit")
    assert all("war" not in r for r in thin)
    assert thin_meta["refused"] and not thin_meta.get("available")
    assert "3 of 60" in thin_meta["refused"]
    assert full_meta["n_stamped"] == 60 and full_meta["available"]


def test_a_refused_season_says_what_the_reader_loses(monkeypatch):
    """A refusal has nowhere to go on the page: an all-blank column is dropped
    from the history board, so a refused season looks exactly like a column that
    was never there. The payload is the only place that can say otherwise, and
    it says it in a sentence rather than leaving a reader to infer it from
    n_stamped 0."""
    _patch_map(monkeypatch, _map(2020, pit={1: 1.0}))
    meta = be.stamp_history_war(_rows(60), 2020, side="pit")
    assert meta["note"] == be.HISTORY_JOIN_REFUSAL_NOTE
    assert "dropped from the board" in meta["note"]
    ok = be.stamp_history_war(_rows(1), 2020, side="pit")
    assert "note" not in ok, "a season that served its column has nothing to say"


def test_a_failed_war_read_leaves_the_history_blank_and_says_so(monkeypatch):
    """An unreadable artifact and an uncovered season are different facts. The
    export stays up either way (a disclosure must not take a board down) and the
    served block says which one happened."""
    _patch_map(monkeypatch, _BROKEN)
    rows = _rows(40)
    meta = be.stamp_history_war(rows, 2021, side="pit")
    assert all("war" not in r for r in rows)
    assert "WAR fetch failed" in meta["refused"] and not meta.get("available")
    assert meta["note"] == be.HISTORY_JOIN_REFUSAL_NOTE


def test_the_join_logs_what_it_did_on_the_pool_it_could_see(monkeypatch):
    """The three pitcher/hitter history exports share one sentence rather than
    each writing their own, and a refusal says so on the same line. BOTH LINES
    ARE DENOMINATED ON THE ROWS CARRYING AN ID: a board with an id-less row that
    said "40 of 41 joined" and then "0 of 40 covered" would be quoting two
    different pools one line apart."""
    _patch_map(monkeypatch, _map(2021, bat={i: 1.0 for i in range(1, 41)}))
    said: list[str] = []
    rows = _rows(40) + [{"name": "no id at all"}]
    be.stamp_history_war(rows, 2021, side="bat", label="hitter-history",
                         log=said.append)
    be.stamp_history_war(_rows(40, first=500), 2021, side="bat",
                         label="hitter-history", log=said.append)
    assert "hitter-history: 2021 eWAR joined for 40/40 rows" in said[0]
    assert "eWAR refused" in said[1] and "0 of 40" in said[1]


# ----------------------------------------------------- E6: the defense history

def test_the_defense_history_row_is_whole_player_and_rounds_once(monkeypatch):
    """Defense carries WHOLE-PLAYER eWAR, both sides summed UNROUNDED and
    rounded once: 1.25 + 1.24 is 2.5, while rounding each side first gives 2.4,
    a full display step of drift. A player with one side serves that side
    alone and an uncovered row stays blank."""
    _patch_map(monkeypatch, _map(2019, bat={1: 1.25, 2: 3.4, 4: 0.0},
                                 pit={1: 1.24, 3: 0.9}))
    rows = [{"mlbam": 1}, {"mlbam": 2}, {"mlbam": 3}, {"mlbam": 4}, {"mlbam": 5}]
    meta = de._stamp_war(rows, 2019)
    assert rows[0]["war"] == 2.5 and meta["n_two_sided"] == 1
    assert rows[1]["war"] == 3.4 and rows[2]["war"] == 0.9
    assert rows[3]["war"] == 0.0 and str(rows[3]["war"]) == "0.0"
    assert "war" not in rows[4]
    assert meta["n_with_id"] == 5 and meta["n_covered"] == 4


def test_the_defense_history_reads_the_season_it_is_building(monkeypatch):
    """Defense history walks back to 2016, further than any other board, so the
    per-season read is the one most likely to be quietly wrong."""
    war = _merge(_map(2016, bat={1: 0.4}), _map(2025, bat={1: 4.4}))
    _patch_map(monkeypatch, war)
    old, new = [{"mlbam": 1}], [{"mlbam": 1}]
    de._stamp_war(old, 2016)
    de._stamp_war(new, 2025)
    assert old[0]["war"] == 0.4 and new[0]["war"] == 4.4


# -------------------------------------------- the four exports, driven offline
#
# ONE WAR MAP FOR EVERY BOARD. Both sides carry a value for every id and every
# season and no two (side, season) pairs agree, so a call site that read the
# wrong side, or the live season instead of the one it is building, moves every
# row rather than agreeing by coincidence on most of them.

_SEASONS = (2021, 2022)
_PITCHER_IDS = tuple(range(1, 121))
_HITTER_IDS = tuple(range(100, 140))
_FIELDER_IDS = tuple(range(1, 121))


def _bat(mid: int, season: int) -> float:
    return 0.5 + (mid % 11) * 0.3 + (season - 2021)


def _pit(mid: int, season: int) -> float:
    return 3.07 + (mid % 7) * 0.41 + (season - 2021) * 2


def _war_map(ids, seasons=_SEASONS) -> dict:
    return {mid: {y: {"bat": _bat(mid, y), "pit": _pit(mid, y)} for y in seasons}
            for mid in ids}


def _expected(mid: int, season: int, side: str) -> float:
    if side == "bat + pit":
        return round(_bat(mid, season) + _pit(mid, season), 1)
    return round(_bat(mid, season) if side == "bat" else _pit(mid, season), 1)


def _pit_line(pid: int, *, ip: str = "70.0", gs: int = 0, g: int = 65) -> dict:
    """One flat StatsAPI season pitching row (build_relievers/build_starters)."""
    return {"mlbam": pid, "name": f"Arm {pid}", "team": "SEA", "IP": ip, "G": g,
            "GS": gs, "SO": 80, "BB": 20, "H": 55, "HR": 6, "ER": 22, "R": 24,
            "TBF": 280, "BF": 280, "Pit": 1100, "SV": 3, "HLD": 12, "BS": 1,
            "GO": 60, "AO": 55, "CG": 0, "SHO": 0, "W": 4, "L": 3, "WP": 2,
            "HBP": 3, "IBB": 1, "BK": 0, "SF": 2, "SH": 1, "2B": 10, "3B": 1,
            "AB": 250, "numberOfPitches": 1100, "strikes": 700,
            "groundOuts": 60, "airOuts": 55}


def _hit_line(pid: int, *, pa: int = 600, h: int = 160, hr: int = 25,
              bb: int = 60, so: int = 110) -> dict:
    """One flat StatsAPI season hitting row (hitter_export.build_hitters shape)."""
    return {"mlbam": pid, "name": f"Bat {pid}", "team": "SEA", "PA": pa,
            "AB": pa - bb - 5, "H": h, "2B": 30, "3B": 2, "HR": hr, "BB": bb,
            "IBB": 3, "HBP": 4, "SF": 5, "SO": so, "SB": 8, "CS": 3,
            "RBI": 85, "R": 90}


def _bullpen_history(monkeypatch, war, seasons=_SEASONS) -> dict:
    monkeypatch.setattr(be, "load_season_pitching",
                        lambda season: [_pit_line(i) for i in _PITCHER_IDS])
    monkeypatch.setattr(be, "load_bref_swstr", lambda season: {})
    import mlb_leverage
    monkeypatch.setattr(mlb_leverage, "fetch_season_leverage",
                        lambda season: ({}, {"games": 0, "games_total": 0}))
    _patch_map(monkeypatch, war)
    return be.export_history(list(seasons), write=False, log=_quiet)


def _starter_history(monkeypatch, war, seasons=_SEASONS) -> dict:
    monkeypatch.setattr(se, "load_season_pitching",
                        lambda season: [_pit_line(i, ip="180.0", gs=30, g=30)
                                        for i in _PITCHER_IDS])
    _patch_map(monkeypatch, war)
    return se.export_history(list(seasons), write=False, log=_quiet)


def _hitter_history(monkeypatch, war, seasons=_SEASONS) -> dict:
    lines = [_hit_line(i, h=140 + (i - 100), hr=10 + (i - 100))
             for i in _HITTER_IDS[:38]]
    # Two short qualified seasons at the ends of the pool: the shrink is by PA,
    # so a 600-PA regular barely moves and these are where the two wOBA columns
    # visibly separate.
    lines.append(_hit_line(138, pa=210, h=70, hr=14, bb=30, so=32))
    lines.append(_hit_line(139, pa=210, h=38, hr=2, bb=13, so=78))
    monkeypatch.setattr(he, "load_season_hitting",
                        lambda season: [dict(r) for r in lines])
    _patch_map(monkeypatch, war)
    return he.export_history(list(seasons), write=False, log=_quiet)


def _defense_history(monkeypatch, war, seasons=_SEASONS) -> dict:
    def _fake_score_season(season, log=None, file_red=False):
        fielders = [{"mlbam": i, "name": f"F {i}", "team": "SEA", "pos": "SS",
                     "inn": 1200.0, "dem_plus": 100 + i % 30, "tier": "avg",
                     "fld_runs": 1.0, "frm_runs": None, "fld_total": 1.0,
                     "pos_runs": 0.5, "pos_runs_fg": 0.4, "def_runs": 1.5,
                     "rate_1000": 1.0, "fld_pct": 0.98, "qualified": True}
                    for i in _FIELDER_IDS]
        return {"scored": {"fielders": fielders}, "basis_rows": [],
                "framing": {"framing_available": True}}

    monkeypatch.setattr(de, "score_season", _fake_score_season)
    _patch_map(monkeypatch, war)
    return de.export_history(list(seasons), write=False, log=_quiet)


#: (builder, the payload's row key, the side that board joins on, its ids)
_BOARDS = [
    pytest.param(_bullpen_history, "relievers", "pit", _PITCHER_IDS, id="bullpen"),
    pytest.param(_starter_history, "starters", "pit", _PITCHER_IDS, id="starter"),
    pytest.param(_hitter_history, "hitters", "bat", _HITTER_IDS, id="hitter"),
    pytest.param(_defense_history, "fielders", "bat + pit", _FIELDER_IDS,
                 id="defense"),
]


@pytest.mark.parametrize("build,row_key,side,ids", _BOARDS)
def test_every_history_export_serves_its_own_side_and_its_own_season(
        monkeypatch, build, row_key, side, ids):
    """THE WAVE'S DELIVERABLE, board by board, on the SERVED payload. Three
    mistakes fail silently and only this catches them: an export that never
    calls the join at all (the column simply does not appear, and the page drops
    it without a word), one that passes the other side (a plausible number in
    the wrong frame), and one that reads the live season while building a past
    one. Every (id, side, season) in the injected map differs, so each of those
    moves every row on the board."""
    doc = build(monkeypatch, _war_map(ids))
    for y in _SEASONS:
        rows = doc["history"][str(y)][row_key]
        assert rows, f"{row_key} {y} built no rows"
        served = {r["mlbam"]: r for r in rows}
        assert set(served) == set(ids)
        for mid, r in served.items():
            assert "war" in r, f"{row_key} {y} row {mid} carries no eWAR"
            assert r["war"] == _expected(mid, y, side), (
                f"{row_key} {y} row {mid}: {r['war']} is not that season's "
                f"{side} cell")
        other = [yy for yy in _SEASONS if yy != y][0]
        assert any(served[m]["war"] != _expected(m, other, side) for m in served), (
            "the two seasons served the same numbers")


@pytest.mark.parametrize("build,row_key,side,ids", _BOARDS)
def test_every_history_payload_discloses_the_join_the_same_way(
        monkeypatch, build, row_key, side, ids):
    """ONE SHAPE ACROSS THE FOUR FILES. A consumer walking ewar_join[<season>]
    must not meet a different set of keys on the fourth board: the whole-player
    defense join keeps its two extras (n_two_sided, basis) but names its season
    and its side like the rest. The block is also where the call site's own
    arguments are readable, which the served numbers alone cannot show."""
    doc = build(monkeypatch, _war_map(ids))
    joins = doc["ewar_join"]
    assert set(joins) == {str(y) for y in _SEASONS}
    for y in _SEASONS:
        block = joins[str(y)]
        assert set(block) >= {"season", "side", "n_rows", "n_with_id",
                              "n_covered", "n_stamped", "available"}, block
        assert block["season"] == y and block["side"] == side
        assert block["available"] is True
        assert block["n_stamped"] == block["n_covered"] == len(ids)
        assert block["n_with_id"] == block["n_rows"] == len(ids)
        assert "refused" not in block and "note" not in block


@pytest.mark.parametrize("build,row_key,side,ids", _BOARDS)
def test_a_history_export_survives_an_unreadable_artifact(
        monkeypatch, build, row_key, side, ids):
    """A disclosure must never take a board down. With the WAR read broken each
    of the four exports still returns its seasons and its rows, serves no eWAR
    key anywhere (blank, never zero), dates no column it does not carry, and
    names the failure season by season."""
    doc = build(monkeypatch, _BROKEN)
    assert set(doc["history"]) == {str(y) for y in _SEASONS}
    for y in _SEASONS:
        rows = doc["history"][str(y)][row_key]
        assert rows and all("war" not in r for r in rows)
        block = doc["ewar_join"][str(y)]
        assert "WAR fetch failed" in block["refused"]
        assert block["available"] is False
        assert block["note"] == be.HISTORY_JOIN_REFUSAL_NOTE
    assert "ewar_vintage" not in doc, (
        "a board with no eWAR column is dating a column it does not serve")


@pytest.mark.parametrize("build,row_key,side,ids", _BOARDS)
def test_no_history_board_carries_a_war_rate_column(
        monkeypatch, build, row_key, side, ids):
    """The counting stat travels and the LIVE-POOL rates do not. The JS drop
    lists say so (test_war_rate_plus pins them); this pins the export, which is
    where a stray stamp would actually come from."""
    doc = build(monkeypatch, _war_map(ids))
    for y in _SEASONS:
        for r in doc["history"][str(y)][row_key]:
            for k in r:
                assert not k.startswith("war_"), f"{row_key} {y}: {k}"


# --------------------------------------------- E8: the recorded wOBA on hitters

def test_the_hitter_history_board_serves_ewar_and_the_recorded_woba(monkeypatch):
    """E8, on the export itself. `woba` is the POOL-SHRUNK value HEM+ is scaled
    from, and a history row that served only that one under a bare "wOBA" header
    told the reader it was the season's wOBA. Both now ship, and they differ
    where the shrink bites."""
    doc = _hitter_history(monkeypatch, _war_map(_HITTER_IDS))
    rows21 = doc["history"]["2021"]["hitters"]
    by21 = {r["mlbam"]: r for r in rows21}
    assert by21[100]["war"] == _expected(100, 2021, "bat")
    for r in rows21:
        assert r["woba_raw"] is not None and r["woba"] is not None
        if r["pa"] >= 500:      # a full season barely shrinks
            assert r["woba"] == pytest.approx(r["woba_raw"], abs=0.02)
    # The shrink is toward the pool by PA, so the short seasons are where the
    # two columns separate: a board serving one value twice fails here.
    moved = [r for r in rows21 if r["woba_raw"] != r["woba"]]
    assert {r["mlbam"] for r in moved} >= {138, 139}, (
        "the shrunk value is being served as the recorded one")
    assert by21[138]["woba"] < by21[138]["woba_raw"]
    assert by21[139]["woba"] > by21[139]["woba_raw"]


def test_the_history_board_ships_the_build_stamp_iff_it_ships_the_column(
        monkeypatch):
    """ewar_vintage dates an eWAR column, so it rides with one and not without:
    the same iff the live boards and the leverage history hold to. It is a
    PAYLOAD receipt (no history column title renders it, so a reader meets it
    only in the file), while the join meta ships either way, because "the read
    failed" is the thing a reader of a missing column most needs told."""
    doc = _hitter_history(monkeypatch, _war_map(_HITTER_IDS))
    assert "ewar_vintage" in doc
    assert set(doc["ewar_join"]) == {"2021", "2022"}
    assert doc["ewar_join"]["2021"]["n_stamped"] == len(_HITTER_IDS)
    blank = _hitter_history(monkeypatch, _BROKEN, seasons=(2021,))
    assert "ewar_vintage" not in blank
    assert blank["ewar_join"]["2021"]["refused"]
    assert all("war" not in r for r in blank["history"]["2021"]["hitters"])


# ------------------------------------------------- the field lists behind it all

def test_the_history_field_lists_still_hold_their_deep_link_keys():
    """A sort key that leaves _HISTORY_FIELDS is a dead deep link, silently:
    readSort validates against the column array, not the payload, so the board
    would open on a column with no values. E8 ADDS to the hitter list."""
    assert "woba_raw" in he._HISTORY_FIELDS and "woba" in he._HISTORY_FIELDS
    for k in ("mlbam", "hem_plus", "pa", "hr", "avg", "obp", "slg", "ops",
              "iso", "bb_pct", "k_pct", "babip", "qualified"):
        assert k in he._HISTORY_FIELDS, k
    for k in ("mlbam", "rem_plus", "riv_plus", "ip", "g", "era", "fip",
              "k_pct", "bb_pct", "k_bb_pct", "swstr_pct", "gmli", "wpa",
              "saves", "holds"):
        assert k in be._HISTORY_FIELDS, k
    for k in ("mlbam", "sem_plus", "ip", "gs", "era", "fip", "k_bb_pct",
              "gb_pct", "ip_per_gs", "hr9"):
        assert k in se._HISTORY_FIELDS, k
    for k in ("mlbam", "pos", "inn", "dem_plus", "fld_runs", "frm_runs",
              "fld_total", "pos_runs", "pos_runs_fg", "def_runs", "fld_pct"):
        assert k in de._HISTORY_FIELDS, k


def test_every_history_field_is_a_key_the_scored_row_actually_carries():
    """The history board is a projection built with .get, so a field name that
    does not exist on the scored row serves a column of nulls rather than
    failing. E8 adds one, which is exactly the way that goes wrong."""
    pool = hem_plus.score_pool(he.build_hitters(
        [_hit_line(200 + i, h=140 + i, hr=10 + i) for i in range(30)]))
    row = pool["hitters"][0]
    assert row["woba_raw"] is not None and row["woba"] is not None
    assert row["woba_raw"] != row["woba"] or row["pa"] >= 500
    missing = [k for k in he._HISTORY_FIELDS if k not in row]
    assert not missing, missing
