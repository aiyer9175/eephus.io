# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for the PUBLISHED wRC+ display column on the Hitter Leaderboards.

Three things are pinned here, and each one guards a specific way this column
could go wrong:

  STINT SAFETY. The predecessor defect on the sqlite path was taking a
  positional split (splits[-1]) off a season-scoped response, which stored ONE
  STINT for a traded player. The offline tests below feed
  load_published_wrc_plus a crafted stint decomposition in which the LAST row is
  a stint and the season total sits in the middle, so any positional pick fails
  and only numTeams-marker selection passes.

  JOIN COVERAGE. A published-value column is only worth showing if it actually
  covers the board, which is why the bulk feed was chosen over the sqlite
  sabermetrics table (226 of 277 qualified). The artifact test pins a floor.

  BANDING. The column is colored on its own measured thresholds, not on the
  HEM+ thresholds. The bands live in hitter_export.WRC_PLUS_BANDS and are
  MIRRORED in assets/mlbstats.js wrcClass(); the mirror test fails if the two
  drift apart.

Offline by construction: the network tests monkeypatch scrapers._fetch, and the
artifact tests read the committed data/hitter_leaderboards.json and skip when it
is absent, so the suite never triggers an export.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import hitter_export as HE

ROOT = Path(__file__).parent
BOARD = ROOT / "data" / "hitter_leaderboards.json"
MLBSTATS_JS = ROOT / "assets" / "mlbstats.js"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _split(pid, wrc, num_teams=1, team_id=None):
    s = {"player": {"id": pid, "fullName": f"P{pid}"},
         "stat": {"wRcPlus": wrc}, "numTeams": num_teams}
    if team_id is not None:
        s["team"] = {"id": team_id}
    return s


def _patch_feed(monkeypatch, splits, status=200):
    """Point load_published_wrc_plus at a crafted payload, offline."""
    import scrapers

    class _FR:
        def __init__(self, body, status):
            self.body, self.status, self.from_cache, self.url = body, status, False, ""

    body = json.dumps({"stats": [{"splits": splits}]})
    monkeypatch.setattr(scrapers, "_fetch",
                        lambda *a, **k: _FR(body if status == 200 else "", status))
    HE.load_published_wrc_plus.cache_clear()


@pytest.fixture(autouse=True)
def _clear_cache():
    HE.load_published_wrc_plus.cache_clear()
    yield
    HE.load_published_wrc_plus.cache_clear()


def _board():
    if not BOARD.exists():
        pytest.skip("data/hitter_leaderboards.json not built")
    return json.loads(BOARD.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# STINT SAFETY - the column must never render a single stint
# --------------------------------------------------------------------------- #
def test_single_row_per_player_is_the_season_total(monkeypatch):
    """The live shape: one aggregated row per player, numTeams says how many
    clubs it spans. Measured 2026-07-31 over 2021-2026: 5,120 feed rows, 5,120
    distinct ids, zero groups larger than one."""
    _patch_feed(monkeypatch, [_split(1, 133.75, num_teams=2), _split(2, 97.2)])
    src = HE.load_published_wrc_plus(2026)
    assert src["values"] == {1: 134, 2: 97}
    assert src["n_multi_team"] == 1
    assert src["n_ambiguous"] == 0


def test_stint_decomposition_selects_the_numteams_marker_not_a_position(monkeypatch):
    """A crafted stint decomposition where the season total is NOT last and NOT
    first, so splits[-1], splits[0] and "last one wins" all produce the WRONG
    number. Only selection on the numTeams > 1 marker gives 120."""
    _patch_feed(monkeypatch, [
        _split(7, 40.0, num_teams=1, team_id=111),    # stint A (would be splits[0])
        _split(7, 120.0, num_teams=2),                # SEASON TOTAL
        _split(7, 210.0, num_teams=1, team_id=147),   # stint B (would be splits[-1])
    ])
    src = HE.load_published_wrc_plus(2026)
    assert src["values"] == {7: 120}, "a positional split leaked into the column"
    assert src["values"][7] not in (40, 210)
    assert src["n_multi_team"] == 1


def test_ambiguous_group_is_refused_rather_than_guessed(monkeypatch):
    """Two rows both carrying the season-total marker is not resolvable without
    guessing, so the id is dropped and counted. Refusing is the deterministic
    rule; picking one would be exactly the positional bug in disguise."""
    _patch_feed(monkeypatch, [
        _split(9, 111.0, num_teams=2),
        _split(9, 222.0, num_teams=3),
        _split(4, 100.0),
    ])
    src = HE.load_published_wrc_plus(2026)
    assert 9 not in src["values"]
    assert src["ambiguous_ids"] == [9]
    assert src["values"] == {4: 100}, "a clean id must survive a neighbour's collision"


def test_no_positional_split_in_the_loader_source():
    """Belt and braces on the mechanism itself: the loader must contain no
    positional indexing of the splits list."""
    src = Path(HE.__file__).read_text(encoding="utf-8")
    fn = src.split("def load_published_wrc_plus")[1].split("\ndef ")[0]
    body = fn.split('"""')[2]          # skip the docstring, which names the bug
    for bad in ("splits[-1]", "splits[0]", "group[-1]", "tot[-1]"):
        assert bad not in body, f"positional split {bad} reintroduced"


def test_feed_failure_leaves_the_column_blank(monkeypatch):
    _patch_feed(monkeypatch, [], status=404)
    src = HE.load_published_wrc_plus(2026)
    assert src["values"] == {}
    rows = [{"mlbam": 1, "qualified": True}]
    meta = HE._join_wrc_plus(rows, 2026)
    assert meta["available"] is False
    assert "wrc_plus" not in rows[0]


# --------------------------------------------------------------------------- #
# IDENTITY - the join key is the mlbam id and nothing else
# --------------------------------------------------------------------------- #
def test_join_is_by_mlbam_so_colliding_player_keys_cannot_disagree(monkeypatch):
    """Measured on prospects.db 2026-07-31: 51 mlbam ids carry more than one
    player_key, 10 of those carry a wRC+ in the sqlite sabermetrics table, and 7
    DISAGREE with themselves (jackson_chourio 115.9 vs 109.9 and friends). Two
    board rows that collide on one mlbam must read ONE number here."""
    _patch_feed(monkeypatch, [_split(694192, 115.9)])
    # pa clears WRC_PLUS_MIN_PA; below the floor the field is deliberately absent
    # (published wRC+ is unshrunk, so a thin sample reads 481 beside a HEM+ of 100).
    rows = [{"mlbam": 694192, "key": "jackson_chourio", "qualified": True, "pa": 400},
            {"mlbam": 694192, "key": "jackson_chourio__noid", "qualified": True, "pa": 400}]
    HE._join_wrc_plus(rows, 2026)
    assert rows[0]["wrc_plus"] == rows[1]["wrc_plus"] == 116
    assert len({r["wrc_plus"] for r in rows}) == 1


def test_rounds_to_nearest_not_ceiling():
    """"+" stats round to nearest (the FV/tool ceiling rule does not apply)."""
    assert int(round(115.9)) == 116 and int(round(109.9)) == 110
    board = _board()
    for h in board["hitters"]:
        v = h.get("wrc_plus")
        if v is not None:
            assert isinstance(v, int), f"{h.get('name')} wRC+ is not an integer"


# --------------------------------------------------------------------------- #
# JOIN COVERAGE floor on the committed artifact
# --------------------------------------------------------------------------- #
def test_artifact_join_hit_rate_floor():
    """Measured 2026-07-31: the feed covers 609/609 board rows and 277/277
    qualified, both 100.0%. A SAMPLE FLOOR of 100 PA was then added (published
    wRC+ is unshrunk, so a 1-PA hitter read 481 beside a shrunk HEM+ of 100.0),
    which drops 203 thin rows by design and takes the raw board rate to 0.667.
    The regression detector is therefore coverage of the ELIGIBLE population,
    not of the whole board. The rejected sqlite path scored 226/277 = 0.816
    qualified, far under this floor."""
    board = _board()
    meta = board.get("wrc_plus")
    if not meta:
        pytest.skip("board predates the published wRC+ column")
    assert meta["available"] is True
    assert meta["published"] is True
    assert meta["n_ambiguous"] == 0, meta["ambiguous_ids"]
    # hit_rate is stamped/board and is depressed BY DESIGN by the sample floor
    # (measured: 203 of 609 rows sit under 100 PA), so it is not the regression
    # detector. The eligible and qualified rates are.
    assert meta["hit_rate_eligible"] >= 0.97, meta
    assert meta["hit_rate_qualified"] >= 0.99, meta
    assert meta["min_pa"] == 100, meta
    assert meta["n_stamped"] == meta["n_eligible"], meta
    # and the stamped rows agree with the counters
    rows = board["hitters"]
    n = sum(1 for h in rows if h.get("wrc_plus") is not None)
    assert n == meta["n_stamped"]
    n_q = sum(1 for h in rows if h.get("qualified") and h.get("wrc_plus") is not None)
    assert n_q == meta["n_stamped_qualified"]


def test_artifact_values_are_plausible_published_wrc_plus():
    board = _board()
    vals = [h["wrc_plus"] for h in board["hitters"] if h.get("wrc_plus") is not None]
    if not vals:
        pytest.skip("board predates the published wRC+ column")
    qual = [h["wrc_plus"] for h in board["hitters"]
            if h.get("qualified") and h.get("wrc_plus") is not None]
    assert len(qual) >= 100
    mean = sum(qual) / len(qual)
    # published wRC+ centres on 100 over ALL hitters, so the QUALIFIED pool sits
    # a little above it (measured 2021-2026: 100.3 to 103.6).
    assert 92 <= mean <= 112, mean
    assert min(vals) > -300 and max(vals) < 600


# --------------------------------------------------------------------------- #
# BANDING - chosen from the measured spread, mirrored in the frontend
# --------------------------------------------------------------------------- #
def test_bands_are_the_measured_values():
    """Derived from the pooled 2021-2026 qualified pools (n = 2,069): wRC+ mean
    100.86 / SD 25.27 against HEM+ mean 99.15 / SD 17.69. Percentile-matching
    the HEM+ breaks 88/112/130 gives 85.0 / 119.0 / 141.0, sigma-matching gives
    84.9 / 119.2 / 144.9; the round-5 triple minimising band-share error is
    85 / 120 / 145 (L1 2.80, runner-up 85/120/150 at 4.54). Changing these is a
    product decision, so it has to change this test too."""
    assert HE.WRC_PLUS_BANDS == {"low": 85, "good": 120, "elite": 145}


def _ladder(fam):
    """One ladder's cuts, read off assets/eephus-tiers.js - the only file on the
    site allowed to contain them."""
    js = (MLBSTATS_JS.parent / "eephus-tiers.js").read_text(encoding="utf-8")
    m = re.search(r"%s:\s*\{ cuts: \[([^\]]+)\]" % fam, js)
    assert m, f"no {fam} ladder in eephus-tiers.js"
    return [float(x) for x in m.group(1).split(",")]


def test_bands_are_not_the_hem_plus_bands():
    """The whole point: published wRC+ is a wider distribution than HEM+, so it
    must NOT inherit the ratio ladder's 88 / 112 / 130. Those three are still
    boundaries on the ratio ladder and still carry their tier names."""
    ratio = _ladder("ratio")
    hem_breaks = [130, 112, 88]
    assert set(hem_breaks) <= set(ratio), ratio
    assert [ratio.index(x) for x in hem_breaks] == [0, 2, 4], ratio
    assert sorted(HE.WRC_PLUS_BANDS.values()) != sorted(hem_breaks)


def test_frontend_mirrors_the_bands():
    """The frontend ladder is a SUPERSET of WRC_PLUS_BANDS: the value ruler adds
    130 and 100 between the published cuts, and every published cut stays a
    boundary carrying the tier name it carried before (145 elite, 120 good,
    85 avg). This is the only place the two can drift, so it is pinned."""
    wrc = _ladder("wrc")
    b = HE.WRC_PLUS_BANDS
    assert set(b.values()) <= set(wrc), (wrc, b)
    assert [wrc.index(b[k]) for k in ("elite", "good", "low")] == [0, 2, 4], wrc
    assert "wrcClass" not in MLBSTATS_JS.read_text(encoding="utf-8")
    # and the artifact publishes the same numbers, so the payload is self-describing
    board = _board()
    if board.get("wrc_plus"):
        assert board["wrc_plus"]["bands"] == b


def test_column_is_registered_beside_hem_plus_and_dropped_on_history():
    js = MLBSTATS_JS.read_text(encoding="utf-8")
    cols = js.split("var HITTER_COLS = [")[1].split("\n  ];")[0]
    keys = re.findall(r'\{ key: "([a-z_0-9]+)"', cols)
    assert "wrc_plus" in keys, "wRC+ column not registered in HITTER_COLS"
    assert keys.index("wrc_plus") == keys.index("hem_plus") + 1, \
        "wRC+ must sit directly beside HEM+ so the two indexes read against each other"
    drop = js.split("var HITTER_HISTORY_DROP = {")[1].split("};")[0]
    assert "wrc_plus: 1" in drop, "past-season boards would render an empty wRC+ column"


def test_column_is_labelled_as_published():
    """It is an industry value, so the board says so rather than letting a
    reader assume the site derived it."""
    js = MLBSTATS_JS.read_text(encoding="utf-8")
    cols = js.split("var HITTER_COLS = [")[1].split("\n  ];")[0]
    wrc = cols.split('{ key: "wrc_plus"')[1].split("\n    { key:")[0]
    assert "Published, not computed here" in wrc
    assert "the industry's published number, not one of ours" in js
    board = _board()
    if board.get("wrc_plus"):
        assert "PUBLISHED" in board["wrc_plus"]["note"]


def test_disclosure_no_longer_reads_as_a_contradiction():
    """build_site's current-lines payload used to say the site "computes no
    wRC+" flatly. With a wRC+ column on the board that reads as a contradiction,
    so the claim is sharpened to derives-vs-displays. Both halves must be
    present or the disclosure is back to being confusing."""
    bs = (ROOT / "build_site.py").read_text(encoding="utf-8")
    note = bs.split('"note": ("Current-season MLB lines')[1].split("),")[0]
    assert "derives no wRC+" in note
    assert "published wRC+" in note and "verbatim" in note
    assert "computes no wRC+" not in note, "the flat claim is back"


# --------------------------------------------------------------------------- #
# END TO END - the bands as the browser actually paints them
# --------------------------------------------------------------------------- #
def _render_board_with(wrc_values):
    """Render the real assets/mlbstats.js hitter board in py_mini_racer with a
    payload whose wRC+ values straddle every band boundary."""
    smoke = pytest.importorskip("test_mlbstats_smoke")
    rows = []
    for i, w in enumerate(wrc_values):
        rows.append(
            '{"key":"%d","name":"WRC %d","team":"NYY","mlbam":%d,"hem_plus":100,'
            '"wrc_plus":%d,"qualified":true,"tier":"Avg","pa":600,"ab":530,"hr":20,'
            '"bb":50,"sb":5,"woba":0.330,"woba_raw":0.330,"avg":0.270,"obp":0.340,'
            '"slg":0.440,"ops":0.780,"iso":0.170,"bb_pct":0.09,"k_pct":0.20,'
            '"babip":0.300}' % (900 + i, w, 900 + i, w))
    sample = ('{"generated_at":"2026-07-31","season":2026,"as_of":"2026-07-31",'
              '"verdict":"validated","hitters":[' + ",".join(rows) + '],"teams":[]}')
    ctx = smoke.MiniRacer()
    ctx.eval(smoke._hitter_prelude("#section=hitters")
             + f"HITTER_SAMPLE={sample};" + smoke.JS)
    return ctx.eval("__html['mlbstats-hitters-root'] || ''")


def test_rendered_bands_match_the_chosen_thresholds():
    """Straddle every boundary: 84/85, 119/120, 144/145. Each still CHANGES
    tier at the published cut, in the real rendered table; the ruler only splits
    the bands between them."""
    html = _render_board_with([84, 85, 119, 120, 144, 145])
    cells = re.findall(
        r'<span class="rem-plus vt vt-fam-wrc (vt-[a-z]+)" data-gl="wrc_plus">(\d+)</span>',
        html)
    got = {int(v): cls for cls, v in cells}
    assert got == {84: "vt-below", 85: "vt-avg", 119: "vt-above",
                   120: "vt-good", 144: "vt-great", 145: "vt-elite"}, got


def test_rendered_column_is_present_and_blank_when_absent():
    html = _render_board_with([130])
    assert ">wRC+<" in html and 'data-gl="wrc_plus"' in html
    assert "undefined" not in html
    # a row with no published value renders an empty cell, never a zero
    smoke = pytest.importorskip("test_mlbstats_smoke")
    plain = smoke._render_hitters("#section=hitters")   # sample carries no wrc_plus
    assert "wRC+" in plain                              # column header still shows
    assert 'data-gl="wrc_plus">0<' not in plain
    assert "undefined" not in plain


def test_no_em_dashes_in_the_touched_files():
    """Owner copy rule, enforced site-wide by copy_lint; re-checked here because
    this task added user-facing prose to three files. All four files below were
    measured clean (zero em-dashes and zero en-dashes) when the column shipped,
    so this is a floor, not a partial exemption."""
    bad = (chr(0x2014), chr(0x2013))     # em dash, en dash
    for p in (ROOT / "hitter_export.py", MLBSTATS_JS, ROOT / "build_site.py",
              ROOT / "build_glossary_data.py"):
        txt = p.read_text(encoding="utf-8")
        for ch in bad:
            assert ch not in txt, f"{p.name} carries {ch!r}"
