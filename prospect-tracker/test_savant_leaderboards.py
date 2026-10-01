# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Contract for the Savant custom-leaderboard display columns (X05-01).

Pinned here:
  SHAPE. A response that lacks a requested field or names another season is
  refused and never overwrites the cache (Savant has served season-inert pages).
  JOIN. Values land on the row by mlbam, percent -> fraction; an empty cell
  stays absent; the one derived column is SwStr%, whiff% x swing%, derived only
  when the caller asks (both pitcher boards ask since owner answer M17-4).
  COVERAGE. On the served boards the join reaches >= 99% of qualified rows and
  every board carries its provenance block.
  RENDER. Every served key has a column object and a Discipline view on its board.

Offline: the join tests pass a loader, the fetch test patches urlopen, and the
artifact tests read the committed boards and skip when a block is absent.
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pytest

import savant_leaderboards as SL

ROOT = Path(__file__).parent
JS = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8").replace("\r\n", "\n")

HEAD = '"last_name, first_name",player_id,year,' + ",".join(SL.SELECTIONS)


def _csv(rows, year=2026):
    out = [HEAD]
    for mid, vals in rows:
        out.append('"X, Y",%d,%d,' % (mid, year) + ",".join(vals))
    return "\n".join(out) + "\n"


# pa, whiff, swing, oz_swing, iz_contact, f_strike, sweet_spot, pull, fb speed
ROW_A = (1, ["300", "30.0", "50.0", "28.5", "85.0", "61.0", "33.0", "40.0", "95.4"])
ROW_B = (2, ["40", "", "44.0", "", "90.0", "55.0", "", "", ""])


def test_selection_list_is_pinned_and_skips_the_empty_fields():
    assert "linedrives_avg" not in SL.SELECTIONS
    assert "oppo_percent" not in SL.SELECTIONS
    for key, (field, _scale, per, sides) in SL.COLUMNS.items():
        assert field in SL.SELECTIONS, key
        assert per and sides, key
    assert set(SL.DERIVED) == {"swstr_pct"}
    assert SL.DERIVED["swstr_pct"][0] == "whiff_percent * swing_percent / 10000"


def test_shape_refuses_a_missing_field_or_another_season():
    good = _csv([ROW_A])
    assert SL.shape_ok(good, 2026)
    assert not SL.shape_ok(good, 2025)
    assert not SL.shape_ok(good.replace("sweet_spot_percent", "sweet_spot"), 2026)
    assert not SL.shape_ok("", 2026)
    assert not SL.shape_ok(HEAD + "\n", 2026)


def test_starter_join_stamps_fractions_and_the_one_derived_column():
    rows = [{"mlbam": 1, "qualified": True}, {"mlbam": 2, "qualified": False},
            {"mlbam": 3, "qualified": True}]
    meta = SL.join(rows, 2026, "pitcher", derive_swstr=True,
                   loader=lambda y, s: _csv([ROW_A, ROW_B]))
    a, b, c = rows
    assert a["whiff_pct"] == 0.30 and a["chase_pct"] == 0.285
    assert a["z_contact_pct"] == 0.85 and a["f_strike_pct"] == 0.61
    assert a["fb_velo"] == 95.4
    assert a["swstr_pct"] == pytest.approx(0.30 * 0.50)
    assert "sweet_spot_pct" not in a and "pull_pct" not in a   # batter-only keys
    assert "whiff_pct" not in b and "swstr_pct" not in b        # empty cell stays absent
    assert b["z_contact_pct"] == 0.90
    assert set(c) == {"mlbam", "qualified"}                     # no Savant row, nothing written
    assert meta["n_joined"] == 2 and meta["n_qualified"] == 2 and meta["n_qualified_joined"] == 1
    assert meta["columns"]["swstr_pct"]["formula"] == SL.DERIVED["swstr_pct"][0]
    assert meta["use"].startswith("display only")


def test_a_join_that_does_not_ask_leaves_swstr_alone():
    rows = [{"mlbam": 1, "qualified": True, "swstr_pct": 0.12}]
    meta = SL.join(rows, 2026, "pitcher", loader=lambda y, s: _csv([ROW_A]))
    assert rows[0]["swstr_pct"] == 0.12
    assert "swstr_pct" not in meta["columns"]


def test_both_pitcher_boards_derive_swstr_from_savant():
    """Owner answer M17-4: the Reliever board, its history and the Starter
    board all take SwStr% from Savant whiff% x swing%; no board reads the
    Baseball-Reference count any more."""
    import bullpen_export as be
    import starter_export as se
    for mod in (be, se):
        src = open(mod.__file__, encoding="utf-8").read()
        assert 'derive_swstr=True' in src, mod.__name__
    src = open(be.__file__, encoding="utf-8").read()
    body = src[src.index("def export("):src.index("def _history_swstr(")]
    assert "load_bref_swstr(" not in body, "a board still reads the Baseball-Reference SwStr%"
    rows = [{"mlbam": 1, "qualified": True}]
    be_meta = SL.join(rows, 2026, "pitcher", derive_swstr=True,
                      loader=lambda y, s: _csv([ROW_A]))
    assert rows[0]["swstr_pct"] == pytest.approx(0.15)
    assert be_meta["columns"]["swstr_pct"]["formula"] == SL.DERIVED["swstr_pct"][0]


def test_batter_join_carries_only_batter_columns():
    rows = [{"mlbam": 1, "qualified": True}]
    SL.join(rows, 2026, "batter", loader=lambda y, s: _csv([ROW_A]))
    assert rows[0]["sweet_spot_pct"] == 0.33 and rows[0]["pull_pct"] == 0.40
    assert "fb_velo" not in rows[0] and "f_strike_pct" not in rows[0]


def test_a_changed_shape_never_overwrites_the_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(SL, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(SL, "_MIN_INTERVAL", 0.0)
    good = _csv([ROW_A], year=2020)
    SL.cache_path(2020, "pitcher").write_text(good, encoding="utf-8")

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    bad = good.replace("pull_percent", "pull_pct_new")
    monkeypatch.setattr(SL.urllib.request, "urlopen",
                        lambda req, timeout=60: _Resp(bad.encode("utf-8")))
    assert SL.fetch_text(2020, "pitcher", force=True) == good
    assert SL.cache_path(2020, "pitcher").read_text(encoding="utf-8") == good


BOARDS = [("hitter_leaderboards.json", "hitters", "batter"),
          ("starter_leaderboards.json", "starters", "pitcher"),
          ("bullpen_leaderboards.json", "relievers", "pitcher")]


@pytest.mark.parametrize("fname,key,side", BOARDS)
def test_served_board_join_covers_qualified_rows(fname, key, side):
    p = ROOT / "data" / fname
    if not p.exists():
        pytest.skip("board absent")
    d = json.loads(p.read_text(encoding="utf-8"))
    m = d.get("savant_custom")
    if not m or not m.get("available"):
        pytest.skip("Savant block unavailable on this build")
    assert m["side"] == side and m["season"] == d["season"]
    assert m["source"] == SL.SOURCE and m["source_url"]
    assert m["n_qualified"] > 0
    assert m["n_qualified_joined"] / m["n_qualified"] >= 0.99
    served = set(m["columns"])
    q = [r for r in d[key] if r.get("qualified")]
    for col in served:
        have = sum(1 for r in q if r.get(col) is not None)
        # FB velo is absent for a pitcher Savant logs no fastball for.
        floor = 0.95 if col == "fb_velo" else 0.99
        assert have / len(q) >= floor, (fname, col, have, len(q))
    # SwStr% is Savant's on both pitcher boards (M17-4), never on the hitters'.
    assert ("swstr_pct" in served) == (side == "pitcher"), (fname, served)


def _array_keys(name):
    m = re.search(r"\n  var %s = \[\n(.*?)\n  \];" % re.escape(name), JS, re.S)
    assert m, name
    return set(re.findall(r'^    \{ key: "([a-z0-9_]+)"', m.group(1), re.M))


@pytest.mark.parametrize("array,side,derived,board", [
    ("HITTER_COLS", "batter", False, "hit"),
    ("STARTER_COLS", "pitcher", True, "sp"),
    ("REL_COLS", "pitcher", True, "rel")])
def test_every_served_key_has_a_column_and_a_discipline_view(array, side, derived, board):
    keys = _array_keys(array)
    want = {k for k, spec in SL.COLUMNS.items() if side in spec[3]}
    if derived:
        want.add("swstr_pct")
    assert want <= keys, sorted(want - keys)
    reg = re.search(r"\n  var COL_VIEWS = \{\n(.*?)\n  \};", JS, re.S).group(1)
    seg = re.search(r"\n    %s: \[(.*?)\n    \]" % board, "\n" + reg, re.S).group(1)
    view = re.search(r'\{ id: "discipline", label: "Discipline",(.*?)\] \}', seg, re.S)
    assert view, board
    listed = set(re.findall(r'"([a-z0-9_]+)"', view.group(1)))
    assert want <= listed, sorted(want - listed)


def test_one_swstr_source_on_both_headers():
    """Both pitcher boards' SwStr% headers name the one source, and neither
    names Baseball-Reference."""
    for array in ("STARTER_COLS", "REL_COLS"):
        m = re.search(r"\n  var %s = \[\n(.*?)\n  \];" % array, JS, re.S)
        col = re.search(r'\{ key: "swstr_pct".*?\},?\n', m.group(1), re.S).group(0)
        assert "Baseball Savant" in col and "whiff% x swing%" in col, (array, col)
        assert "Baseball-Reference" not in col, (array, col)
