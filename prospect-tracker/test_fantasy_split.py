# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Tests for the /fantasy/ split into /dynasty/, /redraft/ and /dfs/.

Three things are worth pinning after a split like this, and they are the three
ways a split silently breaks a site:

  1. THE NEW EXPORTER RUNS OFFLINE. dfs_export builds a VALID payload with no
     network, no slate, and no corpus, carrying its own `empty_reason`. A daily
     job that raises on an off day is a daily job that stops running.

  2. THE CLIENTS STAYED HONEST. Source guards over the three new JS files: each
     fetches its own sidecar and only that; none of them carries betting copy
     (fantasy pages take no gambling disclaimer, and they must not start
     looking like they should); none carries an em-dash; and none computes an
     eFV grade locally, which is the single-basis rule that /fantasy/ once
     broke by serving two different eFV numbers on one page.

  3. THE NUMBERS DID NOT MOVE. assets/redraft.js carries a port of the scoring
     code that used to live in assets/fantasy.js. Both files are driven in a
     real JS engine over ONE fixture payload, and their rendered board scores
     are compared in all four league formats. A drift in the port fails here
     rather than quietly re-ranking somebody's league.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
ASSETS = ROOT / "assets"
JS_FILES = {
    "dynasty": ASSETS / "dynasty.js",
    "redraft": ASSETS / "redraft.js",
    "dfs": ASSETS / "dfs.js",
}
SIDECAR = {"dynasty": "/data/fantasy.json", "redraft": "/data/fantasy.json",
           "dfs": "/data/dfs.json"}
# The shared player-card overlay. It is not a board CLIENT (it fetches no
# corpus and owns no payload; the host hands it one), so it stays out of
# JS_FILES and its own contract is pinned separately. It IS held to the same
# copy and single-eFV-basis rules, which is what GUARDED is for.
CARD_JS = ASSETS / "fantasy-card.js"
GUARDED = dict(JS_FILES, card=CARD_JS)


def _src(name: str) -> str:
    return GUARDED[name].read_text(encoding="utf-8")


def _code(name: str) -> str:
    """Source with whole-line comments removed. The guards below are about what
    the CODE does; a comment naming the server-side function it must not
    duplicate is the documentation working, not a violation."""
    return "\n".join(ln for ln in _src(name).splitlines()
                     if not ln.lstrip().startswith("//"))


# ===========================================================================
# 1. dfs_export offline
# ===========================================================================
def _fantasy_fixture() -> dict:
    """A minimal fantasy.json: two clubs, four bats, two arms, one scoring
    fraction. Everything dfs_export reads and nothing it does not."""
    def hit(mid, name, team, pa, hr, sb):
        return {"mlbam": mid, "name": name, "side": "hit", "pos": "H", "team": team,
                "elig": ["OF"], "skill": {"hem_plus": 120, "luck_gap": 3.0},
                "fpts_fgp": 200.0,
                "ros": {"pa": pa, "ab": pa * 0.9, "h": pa * 0.25, "single": pa * 0.16,
                        "double": pa * 0.05, "triple": pa * 0.005, "hr": hr,
                        "bb": pa * 0.09, "hbp": pa * 0.01, "so": pa * 0.2,
                        "sb": sb, "cs": sb * 0.26, "r": pa * 0.13, "rbi": pa * 0.12,
                        "avg": 0.278, "obp": 0.352, "slg": 0.470}}

    def sp(mid, name, team, ip, gs, k):
        return {"mlbam": mid, "name": name, "side": "pit", "pos": "SP", "team": team,
                "elig": ["P"], "skill": {"sem_plus": 118, "luck": 0.004},
                "fpts_fgp": 150.0,
                "ros": {"role": "SP", "ip": ip, "bf": ip * 4.2, "k": k, "bb": ip * 0.3,
                        "hr": ip * 0.12, "hbp": ip * 0.03, "h": ip * 0.85,
                        "er": ip * 0.38, "era": 3.42, "whip": 1.15, "gs": gs,
                        "qs": gs * 0.5, "w": gs * 0.35, "l": gs * 0.25}}
    return {
        "season": 2026, "season_fraction": 0.70, "generated_at": "2026-08-05T00:00:00Z",
        "players": [
            hit(1, "Alpha Bat", "BOS", 260, 12, 8),
            hit(2, "Bravo Bat", "BOS", 120, 4, 1),
            hit(3, "Charlie Bat", "NYY", 250, 14, 3),
            hit(4, "Delta Bat", "NYY", 60, 1, 0),
            sp(10, "Echo Arm", "BOS", 55, 10, 60),
            sp(11, "Foxtrot Arm", "NYY", 50, 9, 52),
        ],
    }


def _games_fixture(day="2026-08-05", game_pk=1):
    return [{
        "game_pk": game_pk, "date": day, "datetime": day + "T23:05:00Z",
        "status": "Preview", "double_header": False,
        "venue": {"id": 3313, "name": "Yankee Stadium"},
        "home": {"team_id": 147, "team": "New York Yankees", "org": "NYY",
                 "probable": {"mlbam": 11, "name": "Foxtrot Arm"}},
        "away": {"team_id": 111, "team": "Boston Red Sox", "org": "BOS",
                 "probable": {"mlbam": 10, "name": "Echo Arm"}},
    }]


def test_dfs_export_empty_slate_is_a_valid_payload():
    """An off day is the common case for eight months of the year. It must
    produce a payload the page can render, not an exception and not a blank."""
    import dfs_export as dx
    p = dx.build_payload(day="2026-01-15", fantasy=_fantasy_fixture(), games=[])
    assert p["n_games"] == 0 and p["n_players"] == 0
    assert p["games"] == [] and p["players"] == []
    assert "No MLB games scheduled for 2026-01-15" in p["empty_reason"]
    # The page still needs its furniture on an empty day: scoring tables, the
    # roster templates the optimizer runs on, and the salary provenance block.
    assert p["scoring"]["dk"]["hitter"]["hr"] > 0
    assert p["scoring_catalog"] and p["roster_templates"]
    assert p["salaries"]["source"] == "user"
    json.dumps(p)      # serializable, which is the whole job


def test_dfs_export_without_a_corpus_says_so():
    import dfs_export as dx
    p = dx.build_payload(day="2026-08-05", fantasy={}, games=None)
    assert p["n_players"] == 0
    assert "projection corpus" in p["empty_reason"]


def test_dfs_export_offline_refresh_writes_and_returns_zero(tmp_path):
    """The daily wiring calls refresh(). With a stubbed empty schedule it must
    write a payload and return 0 rather than raise."""
    import dfs_export as dx
    out = tmp_path / "dfs.json"
    n = dx.refresh(log=lambda *_a, **_k: None, day="2026-01-15", games=[], out_path=out)
    assert n == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["empty_reason"] and written["players"] == []


def test_dfs_export_prices_a_stubbed_slate():
    import dfs_export as dx
    p = dx.build_payload(day="2026-08-05", fantasy=_fantasy_fixture(),
                         games=_games_fixture(), positions={}, park={},
                         teams_ctx={"BOS": {"offense_plus": 108, "bullpen_plus": 96},
                                    "NYY": {"offense_plus": 104, "bullpen_plus": 101}})
    assert p["empty_reason"] is None
    assert p["n_games"] == 1
    ids = {(r["mlbam"], r["side"]) for r in p["players"]}
    # Both announced starters and all four bats are priced.
    assert (10, "pit") in ids and (11, "pit") in ids
    assert {(1, "hit"), (2, "hit"), (3, "hit"), (4, "hit")} <= ids
    for r in p["players"]:
        assert r["pts"]["dk"] is not None and r["pts"]["fd"] is not None
        assert r["elig"], r
        if r["side"] == "hit":
            assert 0 < r["start_rate"] <= 1.0
            # The line is conditional on starting, so a part-time bat still
            # shows a full game's plate appearances.
            assert r["line"]["pa"] > 3.0, r


def test_dfs_hitter_line_is_conditional_on_starting():
    """Two bats short of an everyday workload over the same remaining schedule
    get the SAME per-start plate appearances and different start rates. That
    split is the whole point: the optimizer prices the line, the reader reads
    the rate."""
    import dfs_export as dx
    most, r_most = dx._hitter_line({"pa": 180.0, "h": 45.0, "ab": 162.0}, 49, 1.0)
    part, r_part = dx._hitter_line({"pa": 120.0, "h": 30.0, "ab": 108.0}, 49, 1.0)
    assert r_most > r_part
    assert abs(most["pa"] - part["pa"]) < 0.001
    assert abs(part["pa"] - dx._PA_PER_START) < 0.001


def test_dfs_everyday_bat_clamps_at_a_full_start():
    """A bat projected past the league per-start anchor is not given a start
    rate above 1.0. He gets rate 1.0 and the longer game he actually plays."""
    import dfs_export as dx
    line, rate = dx._hitter_line({"pa": 260.0, "h": 65.0, "ab": 234.0}, 49, 1.0)
    assert rate == 1.0
    assert line["pa"] > dx._PA_PER_START


def test_dfs_matchup_multiplier_moves_the_right_way():
    """A tougher opposing pitching index lowers a hitter's projection and a
    better opposing offense raises a pitcher's runs allowed."""
    import dfs_export as dx
    easy, _ = dx._hitter_line({"pa": 200.0, "hr": 10.0, "ab": 180.0}, 49, 1.15)
    hard, _ = dx._hitter_line({"pa": 200.0, "hr": 10.0, "ab": 180.0}, 49, 0.85)
    assert easy["hr"] > hard["hr"]
    assert easy["pa"] == hard["pa"]      # playing time is not a matchup term
    good = dx._pitcher_line({"gs": 10, "ip": 55.0, "k": 60.0, "er": 20.0, "h": 47.0}, 0.9)
    bad = dx._pitcher_line({"gs": 10, "ip": 55.0, "k": 60.0, "er": 20.0, "h": 47.0}, 1.1)
    assert bad["er"] > good["er"] and bad["h"] > good["h"]
    assert bad["k"] == good["k"]         # a weak lineup does not hand out strikeouts


def test_dfs_scoring_tables_are_published_and_self_consistent():
    """The client re-scores from the payload's own tables, so a weight that is
    not in the payload is a weight nobody can audit."""
    import dfs_export as dx
    t = dx.scoring_tables()
    assert set(t) == {"dk", "fd"}
    line = {"single": 1.0, "double": 1.0, "hr": 1.0, "rbi": 2.0, "r": 1.0, "bb": 1.0}
    manual = sum(line[k] * dx.DK_HITTER[k] for k in line)
    assert abs(dx.score_line(line, "dk", "hit") - manual) < 1e-6
    pit = {"ip": 6.0, "k": 7.0, "er": 2.0, "h": 5.0, "bb": 2.0, "w": 1.0}
    manual_p = sum(pit[k] * dx.DK_PITCHER[k] for k in pit)
    assert abs(dx.score_line(pit, "dk", "pit") - manual_p) < 1e-6


def test_dfs_doubleheader_does_not_duplicate_a_player():
    """Two games for one club on one day must not put the same bat in a lineup
    twice. The better matchup wins the row and the row records both games."""
    import dfs_export as dx
    games = _games_fixture(game_pk=1) + _games_fixture(game_pk=2)
    p = dx.build_payload(day="2026-08-05", fantasy=_fantasy_fixture(), games=games,
                         positions={}, park={}, teams_ctx={})
    keys = [(r["mlbam"], r["side"]) for r in p["players"]]
    assert len(keys) == len(set(keys)), keys
    assert all(r["games_today"] == 2 for r in p["players"])


def test_dfs_position_eligibility_has_one_definition():
    """dfs_export must not carry a second copy of the eligibility rule. One
    definition lives in fantasy_export; this module reads the answer."""
    import dfs_export as dx
    import fantasy_export as fe
    assert dx.positions_by_mlbam.__doc__
    src = (ROOT / "dfs_export.py").read_text(encoding="utf-8")
    assert "fe._elig_positions()" in src
    assert dx._MIN_ELIG_GAMES == fe._ELIG_MIN_GAMES


def test_fantasy_export_elig_is_additive():
    """The shape addition must not disturb any existing reader: `pos` keeps its
    old value and `elig` is a new key."""
    import fantasy_export as fe
    players = [{"mlbam": 1, "side": "hit", "pos": "H"},
               {"mlbam": 10, "side": "pit", "pos": "SP"},
               {"mlbam": 11, "side": "pit", "pos": "RP"}]
    fe._enrich(players)
    assert players[0]["pos"] == "H"
    assert players[1]["elig"] == ["P"] and players[2]["elig"] == ["P"]
    assert "skill" in players[0] and "team" in players[0]


def test_fantasy_export_elig_positions_rule():
    """The games floor with a modal-position fallback, exercised directly so a
    change to the rule is a deliberate act."""
    import fantasy_export as fe
    raw = {"players": {
        "a": {"mlbam": 1, "positions": {"SS": {"games": 80}, "2B": {"games": 9},
                                        "LF": {"games": 2}}},
        "b": {"mlbam": 2, "positions": {"DH": {"games": 3}}},          # modal, under floor
        "c": {"mlbam": 3, "positions": {"P": {"games": 30}}},          # pitcher: no hitter slot
    }}
    import json as _json
    import tempfile
    # _elig_positions reads from disk, so drive the same rule through a
    # temporary artifact rather than reaching into module internals.
    d = Path(tempfile.mkdtemp())
    (d / "mlb_fielding_positions.json").write_text(_json.dumps(raw), encoding="utf-8")
    old = fe.DATA_DIR
    try:
        fe.DATA_DIR = d
        out = fe._elig_positions()
    finally:
        fe.DATA_DIR = old
    assert out[1] == ["SS", "2B"], out          # LF at 2 games is under the floor
    assert out[2] == ["UTIL"], out              # DH modal survives the floor
    assert 3 not in out                          # pitchers carry no fielding slot


# ===========================================================================
# 2. Source contracts over the three clients
# ===========================================================================
@pytest.mark.parametrize("name", sorted(JS_FILES))
def test_each_client_fetches_its_own_sidecar(name):
    src = _src(name)
    urls = re.findall(r'DATA_URL\s*=\s*"([^"]+)"', src)
    assert urls == [SIDECAR[name]], (name, urls)
    fetches = re.findall(r"fetch\(\s*([^,)]+)", src)
    assert fetches, name
    for f in fetches:
        assert f.strip() == "DATA_URL", (name, f)


@pytest.mark.parametrize("name", sorted(GUARDED))
def test_no_em_or_en_dashes(name):
    src = _src(name)
    assert "—" not in src, f"{name}.js carries an em-dash"
    assert "–" not in src, f"{name}.js carries an en-dash"


@pytest.mark.parametrize("name", sorted(GUARDED))
def test_fantasy_pages_carry_no_betting_copy(name):
    """The betting rails belong to the betting surfaces. A fantasy page that
    starts carrying a gambling disclaimer is a fantasy page somebody has begun
    treating as a betting product."""
    low = _src(name).lower()
    for term in ("1-800-gambler", "21+", "sportsbook", "wager", "parlay",
                 "problem gambling", "moneyline"):
        assert term not in low, f"{name}.js carries betting copy: {term}"


@pytest.mark.parametrize("name", sorted(GUARDED))
def test_no_local_efv_basis(name):
    """THE SINGLE-BASIS RULE. Every eFV number on the site comes out of
    efv_board_scale.board_value on the server. A client that reaches for a raw
    grade field, or does arithmetic on one, has started a second basis, which
    is exactly the defect that had /fantasy/ showing one prospect two different
    eFV grades a tab apart."""
    src = _code(name)
    for bad in ("xfv_grade", "xfv_grade_quantile", "xfv_grade_realized",
                "board_value", "boardValue", "efvBoardValue"):
        assert bad not in src, f"{name}.js reaches for a raw grade field: {bad}"
    # No arithmetic on the served grade: reading and rounding only.
    for m in re.finditer(r"\.efv\s*([+\-*/])", src):
        raise AssertionError(f"{name}.js does math on the served eFV grade: {m.group(0)}")
    for m in re.finditer(r"\.fvE\s*([+\-*/])", src):
        raise AssertionError(f"{name}.js does math on the served eFV grade: {m.group(0)}")


def test_dynasty_rounds_efv_to_nearest_and_consensus_to_ceiling():
    """House grade conventions: scouting FV displays as a ceiling, eFV and
    plus-stats display to nearest."""
    src = _src("dynasty")
    assert "Math.round(c.fvE)" in src, "eFV must display to nearest"
    assert "Math.ceil(c.fv)" in src, "consensus FV must display as a ceiling"


def test_diamond_gate_is_read_but_never_asserted():
    """Every client reads window.EEPHUS_DIAMOND defensively and treats a
    missing config as gating OFF. Nothing here may turn gating on."""
    for name in JS_FILES:
        src = _src(name)
        assert "EEPHUS_DIAMOND" in src, name
        assert "gating: true" not in src and "gating:true" not in src, name


def test_dfs_client_does_not_scrape_salaries():
    """Salaries are the user's. The client must not fetch them from anywhere."""
    src = _src("dfs")
    for bad in ("draftkings", "fanduel.com", "api.draftkings", "salaries.json"):
        assert bad not in src.lower(), f"dfs.js reaches for a salary feed: {bad}"
    assert "localStorage" in src


def test_dynasty_keeper_calculator_is_arithmetic_only():
    """The keeper tool compares a pick number against a served rank. It must
    not invent a dollar value, because no dynasty dollar curve has been fit."""
    src = _src("dynasty")
    assert "function breakEvenRound" in src
    assert "localStorage" in src
    assert re.search(r"dollar", src, re.IGNORECASE), (
        "the calculator should say out loud that it does not publish dollars")


# ===========================================================================
# 3. Scoring parity: redraft.js reproduces fantasy.js
# ===========================================================================
MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer

# Hitting weights are format-independent in fantasy_scoring; pitching is not.
# Multiple players per pool so the roto z-scores are not degenerate.
PARITY_PAYLOAD = json.dumps({
    "season": 2026, "season_fraction": 0.66, "n_players": 6,
    "scoring": {
        "hitter": {"ab": -1.0, "h": 5.6, "double": 2.9, "triple": 5.7, "hr": 9.4,
                   "bb": 3.0, "hbp": 3.0, "sb": 1.9, "cs": -2.8},
        "pitcher": {"fgp": {"ip": 7.4, "k": 2.0, "h": -2.6, "bb": -3.0, "hbp": -3.0,
                            "hr": -12.3, "sv": 5.0, "hld": 4.0},
                    "sabr": {"ip": 5.0, "k": 2.0, "bb": -3.0, "hbp": -3.0,
                             "hr": -13.0, "sv": 5.0, "hld": 4.0}}},
    "scoring_catalog": [
        {"id": "fgp", "kind": "points", "label": "FanGraphs Points", "default": True},
        {"id": "sabr", "kind": "points", "label": "SABR Points"},
        {"id": "5x5", "kind": "roto", "label": "Old School (5x5)"},
        {"id": "4x4", "kind": "roto", "label": "Ottoneu Classic (4x4)"}],
    "players": [
        {"mlbam": 660271, "name": "Shohei Ohtani", "side": "hit", "pos": "DH", "team": "LAD",
         "elig": ["UTIL"], "fpts_fgp": 284.8, "skill": {"hem_plus": 168, "luck_gap": 11.0},
         "ros": {"pa": 260, "ab": 224, "h": 66, "double": 13, "triple": 1, "hr": 28,
                 "bb": 33, "hbp": 3, "sb": 9, "cs": 2, "r": 48, "rbi": 60,
                 "avg": 0.295, "obp": 0.402, "slg": 0.611}},
        {"mlbam": 592450, "name": "Aaron Judge", "side": "hit", "pos": "RF", "team": "NYY",
         "elig": ["OF"], "fpts_fgp": 260.0, "skill": {"hem_plus": 175, "luck_gap": -6.0},
         "ros": {"pa": 270, "ab": 226, "h": 71, "double": 15, "triple": 0, "hr": 25,
                 "bb": 41, "hbp": 3, "sb": 3, "cs": 1, "r": 52, "rbi": 65,
                 "avg": 0.314, "obp": 0.440, "slg": 0.628}},
        {"mlbam": 665742, "name": "Juan Soto", "side": "hit", "pos": "LF", "team": "NYM",
         "elig": ["OF"], "fpts_fgp": 240.0, "skill": {"hem_plus": 160, "luck_gap": 2.0},
         "ros": {"pa": 255, "ab": 205, "h": 60, "double": 12, "triple": 1, "hr": 18,
                 "bb": 46, "hbp": 2, "sb": 5, "cs": 2, "r": 45, "rbi": 50,
                 "avg": 0.293, "obp": 0.436, "slg": 0.541}},
        {"mlbam": 694973, "name": "Paul Skenes", "side": "pit", "pos": "SP", "team": "PIT",
         "elig": ["P"], "fpts_fgp": 210.0, "skill": {"sem_plus": 146, "luck": 0.002},
         "ros": {"ip": 62, "k": 78, "h": 47, "bb": 15, "hbp": 2, "hr": 5, "gs": 11,
                 "qs": 7, "w": 4, "era": 2.35, "whip": 1.00}},
        {"mlbam": 434378, "name": "Zack Wheeler", "side": "pit", "pos": "SP", "team": "PHI",
         "elig": ["P"], "fpts_fgp": 190.0, "skill": {"sem_plus": 131, "luck": -0.003},
         "ros": {"ip": 58, "k": 66, "h": 50, "bb": 12, "hbp": 3, "hr": 8, "gs": 10,
                 "qs": 6, "w": 4, "era": 3.10, "whip": 1.07}},
        {"mlbam": 656302, "name": "Dylan Cease", "side": "pit", "pos": "SP", "team": "SDP",
         "elig": ["P"], "fpts_fgp": 170.0, "skill": {"sem_plus": 118, "luck": 0.006},
         "ros": {"ip": 55, "k": 71, "h": 49, "bb": 22, "hbp": 2, "hr": 9, "gs": 10,
                 "qs": 5, "w": 3, "era": 3.68, "whip": 1.29}},
    ],
    "sections": {
        "ros_hitter": [660271, 592450, 665742],
        "ros_sp": [694973, 434378, 656302],
        "ros_rp": [],
        "buy_low": [{"mlbam": 660271, "side": "hit"}],
        "sell_high": [{"mlbam": 592450, "side": "hit"}],
        "closer_depth": {},
        "callup_watch": [],
        "daily_streamers": [],
        "two_start": [],
        "dynasty": [],
    },
})

PARITY_PRELUDE = """
var __html = {};
var __hashHandlers = [];
function __el(id) {
  return new Proxy(function () { return __el(id); }, {
    get: function (t, k) {
      if (k === 'innerHTML') return __html[id] || '';
      if (k === 'classList') return {add:function(){},remove:function(){},toggle:function(){},contains:function(){return false;}};
      if (k === 'querySelectorAll') return function () { return []; };
      if (k === 'querySelector') return function () { return null; };
      if (k === 'getAttribute') return function () { return null; };
      if (k === 'setAttribute' || k === 'addEventListener' || k === 'removeEventListener'
          || k === 'focus' || k === 'appendChild' || k === 'insertBefore') return function () {};
      if (k === 'value' || k === 'textContent') return '';
      if (k === 'nextSibling') return null;
      if (k === 'files') return null;
      if (k === 'dataset') return {};
      return __el(id);
    },
    set: function (t, k, v) { if (k === 'innerHTML') __html[id] = v; return true; },
    apply: function () { return __el(id); }
  });
}
function __btn(sec) {
  var hs = [];
  return { __sec: sec,
    getAttribute: function (n) {
      return (n === 'data-fantasysection' || n === 'data-redraftsection') ? sec : null; },
    setAttribute: function () {},
    classList: { add: function () {}, remove: function () {},
                 toggle: function () {}, contains: function () { return false; } },
    addEventListener: function (t, cb) { if (t === 'click') hs.push(cb); },
    click: function () { hs.forEach(function (h) { h({}); }); } };
}
var __btns = ['streamers','two_start','ros_sp','ros_rp','ros_hitter','buysell',
              'closers','callups','dynasty'].map(__btn);
function FT(val) { return { then: function (cb) { var r = cb(val); return (r && r.then) ? r : FT(r); },
                            catch: function () { return FT(val); } }; }
var PAYLOAD = %s;
var fetch = function () { return FT({ ok: true, json: function () { return FT(PAYLOAD); } }); };
var location = { href: '', hash: '', pathname: '/redraft/' };
var __nav = { querySelector: function () { return {}; }, appendChild: function () {},
              insertBefore: function () {} };
var document = { readyState: 'complete',
  getElementById: function (id) { return __el(id); },
  querySelector: function (sel) { return sel === '.mlbstats-sectionnav' ? __nav : null; },
  querySelectorAll: function (sel) {
    // The redraft shell selector resolves to nothing here on purpose: the
    // module has to fall back to the fantasy-era nav, which is the tolerance
    // the split depends on while the shells land in another lane.
    return sel === '.mlbstats-sectionbtn[data-fantasysection]' ? __btns : [];
  },
  createElement: function () { return __el('c'); },
  addEventListener: function () {},
  head: __el('head'), body: __el('body') };
var EEPHUS_GL = { wire: function () {} };
var EEPHUS_HUB = { teamLogo: function (t) { return '<i>' + t + '</i>'; },
                   links: function () { return FT({ byMlbam: {} }); } };
var window = { location: location, document: document, fetch: fetch,
               EEPHUS_HUB: EEPHUS_HUB, EEPHUS_GL: EEPHUS_GL,
               addEventListener: function (t, cb) { if (t === 'hashchange') __hashHandlers.push(cb); } };
// The module reads the BARE globals inside its window guards, exactly as a
// browser would resolve them.
function __go(hash) {
  location.hash = hash;
  __hashHandlers.forEach(function (h) { h({}); });
  return __html['redraft-app-root'] || __html['fantasy-app-root'] || '';
}
""" % PARITY_PAYLOAD

SCORE_RE = re.compile(
    r'class="mlb-metric (?:ff|rd)-strong"><span class="mlb-metric-label">[^<]*</span>([^<]*)</span>')


def _scores(html: str) -> list:
    return SCORE_RE.findall(html or "")


def _boot(js_path: Path) -> "MiniRacer":
    c = MiniRacer()
    c.eval(PARITY_PRELUDE + js_path.read_text(encoding="utf-8"))
    return c


@pytest.fixture(scope="module")
def parity_ctxs():
    return _boot(ASSETS / "fantasy.js"), _boot(ASSETS / "redraft.js")


@pytest.mark.parametrize("system", ["fgp", "sabr", "5x5", "4x4"])
@pytest.mark.parametrize("section", ["ros_hitter", "ros_sp"])
def test_redraft_scoring_matches_fantasy(parity_ctxs, section, system):
    """THE PORT CHECK. Both files render the same board from the same payload
    in the same format, through their own hash routers and their own card
    renderers, and the score column has to agree cell for cell."""
    old, new = parity_ctxs
    h = "#section=%s&sys=%s" % (section, system)
    a = _scores(old.eval("__go(%s)" % json.dumps(h)))
    b = _scores(new.eval("__go(%s)" % json.dumps(h)))
    assert a, ("the retired /fantasy/ board rendered no scores", section, system)
    assert a == b, (section, system, a, b)


def test_parity_fixture_actually_separates_the_formats(parity_ctxs):
    """A parity test over four formats is worthless if the four formats
    produce the same numbers. Pin that they do not."""
    old, _ = parity_ctxs
    seen = set()
    for system in ("fgp", "sabr", "5x5", "4x4"):
        seen.add(tuple(_scores(old.eval('__go("#section=ros_sp&sys=%s")' % system))))
    assert len(seen) == 4, seen


def test_redraft_drops_the_prospect_sections(parity_ctxs):
    """The split moved Dynasty and Call-up Watch to /dynasty/. /redraft/ must
    not carry them, and asking it for one must land on a rendered default board
    rather than a blank page."""
    src = _code("redraft")
    sections = re.search(r"var SECTIONS = \[(.*?)\];", src, re.DOTALL)
    assert sections, "redraft.js must declare its section alternation"
    names = re.findall(r'"([a-z_]+)"', sections.group(1))
    assert "dynasty" not in names and "callups" not in names, names
    assert "renderDynasty" not in src and "callup_watch" not in src
    _, new = parity_ctxs
    html = new.eval('__go("#section=dynasty")')
    assert html.strip(), "an unknown section must fall back to a rendered board"


# ===========================================================================
# 4. The DFS lineup optimizer, driven end to end
# ===========================================================================
# A pool small enough to brute-force in Python, and shaped so the greedy build
# CANNOT reach the optimum on its own: the greedy spends first on the highest
# projection at each slot and paints itself into a 24-point lineup, while the
# best legal lineup under the cap is 26. If the local-search pass ever stops
# working, this test drops from 26 to 24 and says so.
OPT_PLAYERS = [
    # (mlbam, name, side, elig, team, pts, salary)
    (1, "Ace Arm", "pit", ["P"], "AAA", 10.0, 9000),
    (2, "Cheap Arm", "pit", ["P"], "BBB", 6.0, 4000),
    (3, "Star Catcher", "hit", ["C"], "CCC", 8.0, 8000),
    (4, "Cheap Catcher", "hit", ["C"], "DDD", 3.0, 2000),
    (5, "Big Bat", "hit", ["OF"], "EEE", 9.0, 7000),
    (6, "Good Bat", "hit", ["OF"], "FFF", 7.0, 5000),
    (7, "Fine Bat", "hit", ["OF"], "GGG", 5.0, 3000),
    (8, "Punt Bat", "hit", ["OF"], "HHH", 2.0, 2000),
]
OPT_CAP = 20000
OPT_TEMPLATE = {
    "id": "mini", "label": "Mini: P, C, 2 OF", "scoring": "dk", "cap": OPT_CAP,
    "max_per_team": 2, "min_games": 1, "default": True,
    "slots": [{"slot": "P"}, {"slot": "C"}, {"slot": "OF"}, {"slot": "OF"}],
}


def _opt_payload() -> str:
    return json.dumps({
        "slate_date": "2026-08-05", "season": 2026, "n_games": 1, "n_players": len(OPT_PLAYERS),
        "empty_reason": None,
        "games": [{"game_pk": 1, "date": "2026-08-05", "venue": "Test Park",
                   "park_source": "none",
                   "home": {"org": "AAA", "probable": {"mlbam": 1, "name": "Ace Arm"}},
                   "away": {"org": "BBB", "probable": {"mlbam": 2, "name": "Cheap Arm"}}}],
        "players": [{"mlbam": m, "name": n, "side": s, "elig": e, "team": t,
                     "opp": "ZZZ", "is_home": True, "game_pk": 1,
                     "start_rate": 1.0 if s == "hit" else None,
                     "line": {}, "pts": {"dk": p, "fd": p}}
                    for (m, n, s, e, t, p, _sal) in OPT_PLAYERS],
        "scoring": {"dk": {"hitter": {}, "pitcher": {}}, "fd": {"hitter": {}, "pitcher": {}}},
        "scoring_catalog": [{"id": "dk", "label": "Classic", "default": True},
                            {"id": "fd", "label": "Full"}],
        "scoring_note": "test", "roster_templates": [OPT_TEMPLATE],
        "salaries": {"source": "user"}, "notes": [], "anchors": {"pa_per_start": 4.15},
    })


def _brute_force_best() -> float:
    """The true optimum for OPT_PLAYERS under the cap and the per-team limit."""
    import itertools
    by = {m: (elig, team, pts, sal) for (m, _n, _s, elig, team, pts, sal) in
          [(p[0], p[1], p[2], p[3], p[4], p[5], p[6]) for p in OPT_PLAYERS]}
    ps = [m for m in by if "P" in by[m][0]]
    cs = [m for m in by if "C" in by[m][0]]
    ofs = [m for m in by if "OF" in by[m][0]]
    best = 0.0
    for p in ps:
        for c in cs:
            for o1, o2 in itertools.combinations(ofs, 2):
                pick = [p, c, o1, o2]
                if len(set(pick)) != 4:
                    continue
                if sum(by[m][3] for m in pick) > OPT_CAP:
                    continue
                teams = {}
                for m in pick:
                    teams[by[m][1]] = teams.get(by[m][1], 0) + 1
                if max(teams.values()) > OPT_TEMPLATE["max_per_team"]:
                    continue
                best = max(best, sum(by[m][2] for m in pick))
    return best


APP_PRELUDE = """
var __html = {};
var __nodes = {};
var __hashHandlers = [];
var __LS = {};
var localStorage = {
  getItem: function (k) { return Object.prototype.hasOwnProperty.call(__LS, k) ? __LS[k] : null; },
  setItem: function (k, v) { __LS[k] = String(v); },
  removeItem: function (k) { delete __LS[k]; } };
function __mkNode(sel) {
  var hs = {};
  return { __sel: sel, value: '', checked: false, files: null,
    getAttribute: function () { return null; },
    setAttribute: function () {},
    addEventListener: function (t, cb) { (hs[t] = hs[t] || []).push(cb); },
    focus: function () {},
    __reset: function () { hs = {}; },
    __fire: function (t) { (hs[t] || []).forEach(function (c) { c({}); }); } };
}
// One node object per selector so a test can seed an input's value before the
// click that reads it, but its LISTENERS are dropped on every query: a render
// rebinds, and without the reset one click would fire N stacked handlers.
function __node(sel) {
  var n = __nodes[sel];
  if (!n) { n = __mkNode(sel); __nodes[sel] = n; }
  n.__reset();
  return n;
}
function __out() {
  return __html['dfs-app-root'] || __html['dynasty-app-root'] ||
         __html['redraft-app-root'] || __html['fantasy-app-root'] || '';
}
function __fireEvent(sel, type) {
  var n = __nodes[sel];
  if (!n) throw new Error('no node registered for ' + sel);
  n.__fire(type);
  return __out();
}
function __click(sel) { return __fireEvent(sel, 'click'); }
function __el(id) {
  return new Proxy(function () { return __el(id); }, {
    get: function (t, k) {
      if (k === 'innerHTML') return __html[id] || '';
      if (k === 'classList') return {add:function(){},remove:function(){},toggle:function(){},contains:function(){return false;}};
      if (k === 'querySelectorAll') return function () { return []; };
      if (k === 'querySelector') return function (sel) { return __node(sel); };
      if (k === 'getAttribute') return function () { return null; };
      if (k === 'setAttribute' || k === 'addEventListener' || k === 'removeEventListener'
          || k === 'focus' || k === 'appendChild' || k === 'insertBefore') return function () {};
      if (k === 'value' || k === 'textContent') return '';
      if (k === 'files' || k === 'nextSibling') return null;
      return __el(id);
    },
    set: function (t, k, v) { if (k === 'innerHTML') __html[id] = v; return true; },
    apply: function () { return __el(id); }
  });
}
function FT(val) { return { then: function (cb) { var r = cb(val); return (r && r.then) ? r : FT(r); },
                            catch: function () { return FT(val); } }; }
var PAYLOAD = %s;
var fetch = function () { return FT({ ok: true, json: function () { return FT(PAYLOAD); } }); };
var location = { href: '', hash: '', pathname: '/dfs/' };
// Ids a test declares ABSENT, so the harness can reproduce the real shell
// (the /dfs/ shell has no scoring bar; a proxy for every id would hide that
// and the inline-selector fallback would never be exercised).
var __MISSING = {};
function __hide(id) { __MISSING[id] = 1; }
var document = { readyState: 'complete',
  getElementById: function (id) { return __MISSING[id] ? null : __el(id); },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; },
  createElement: function () { return __el('c'); },
  addEventListener: function () {},
  head: __el('head'), body: __el('body') };
var EEPHUS_GL = { wire: function () {} };
var EEPHUS_HUB = { teamLogo: function (t) { return '<i>' + t + '</i>'; },
                   links: function () { return FT({ byMlbam: {} }); } };
var window = { location: location, document: document, fetch: fetch,
               localStorage: localStorage,
               EEPHUS_HUB: EEPHUS_HUB, EEPHUS_GL: EEPHUS_GL,
               addEventListener: function (t, cb) { if (t === 'hashchange') __hashHandlers.push(cb); } };
function __go(hash) {
  location.hash = hash;
  __hashHandlers.forEach(function (h) { h({}); });
  return __out();
}
function __seedSalaries(json) { __LS['eephus.dfs.salaries'] = json; }
function __setValue(sel, v) {
  var n = __nodes[sel];
  if (!n) { n = __mkNode(sel); __nodes[sel] = n; }
  n.value = v;
}
"""


def _dfs_boot(payload_json: str, salaries: bool = False):
    """Boot assets/dfs.js over a payload, with the shell's actual furniture:
    the /dfs/ page has no scoring bar, so those ids are absent here too."""
    c = MiniRacer()
    c.eval(APP_PRELUDE % payload_json)
    c.eval("__hide('dfs-scoring'); __hide('fantasy-scoring');")
    if salaries:
        rows = {"%d|%s" % (m, s): {"salary": sal}
                for (m, _n, s, _e, _t, _p, sal) in OPT_PLAYERS}
        c.eval("__seedSalaries(%s)" % json.dumps(json.dumps(
            {"slate_date": "2026-08-05", "saved_at": "2026-08-05T00:00:00Z", "rows": rows})))
    c.eval((ASSETS / "dfs.js").read_text(encoding="utf-8"))
    return c


def _dfs_ctx():
    return _dfs_boot(_opt_payload(), salaries=True)


def test_dfs_optimizer_finds_the_best_legal_lineup():
    """End to end through the shipped client: seeded salaries, the optimizer
    tab, a real click on Optimize. The greedy build alone lands on 24 points
    here; the local-search pass has to find 26, which brute force confirms is
    the best lineup the cap and the per-team limit allow."""
    c = _dfs_ctx()
    c.eval('__go("#section=optimizer")')
    html = c.eval('__click("#dfs-run")')
    assert "projected points" in html, html[:400]
    pts = float(re.search(r"<b>([\d.]+)</b> projected points", html).group(1))
    assert pts == _brute_force_best() == 26.0, (pts, html[:600])
    used = int(re.search(r"<b>\$([\d,]+)</b> of", html).group(1).replace(",", ""))
    assert used <= OPT_CAP, used
    # Four filled slots, four distinct players (the fifth <tr> is the header).
    assert html.count("<tr><td>") == 4, html
    for who in ("Cheap Arm", "Star Catcher", "Good Bat", "Fine Bat"):
        assert who in html, (who, html[:600])


def test_dfs_optimizer_reports_missing_salaries_instead_of_guessing():
    """With no salary sheet loaded the optimizer must say what it is missing.
    Inventing a price would be the one thing this module refuses to do."""
    c = _dfs_boot(_opt_payload())
    html = c.eval('__go("#section=optimizer")')
    assert "No salaries loaded" in html, html[:400]


def test_dfs_empty_slate_renders_a_loud_state_not_a_blank_page():
    """An off day must reassure, and it must do so on the payload production
    actually emits. dfs_export._empty always stamps `empty_reason_kind`, so the
    fixture carries it too; without it this asserted the old one-message
    contract against a shape the exporter no longer produces."""
    empty = json.loads(_opt_payload())
    empty.update({"players": [], "games": [], "n_games": 0, "n_players": 0,
                  "empty_reason": "No MLB games scheduled for 2026-01-15.",
                  "empty_reason_kind": "no_games_scheduled"})
    c = _dfs_boot(json.dumps(empty))
    html = c.eval('__go("#section=pitchers")')
    assert "No games today" in html and "No MLB games scheduled" in html
    assert "Nothing is broken" in html


def test_dfs_pipeline_failure_does_not_claim_nothing_is_broken():
    """The other half of the same contract, and the reason the kinds exist. A
    schedule feed that did not answer is OUR outage, so the page must NOT tell
    the reader everything is fine, and must read as broken. An unknown kind gets
    the same treatment: silence is not a promise that we are healthy."""
    rendered = {}
    for kind in ("schedule_unavailable", None):
        broken = json.loads(_opt_payload())
        broken.update({"players": [], "games": [], "n_games": 0, "n_players": 0,
                       "empty_reason": "The schedule feed did not answer."})
        if kind:
            broken["empty_reason_kind"] = kind
        c = _dfs_boot(json.dumps(broken))
        rendered[kind] = c.eval('__go("#section=pitchers")')
        assert "Nothing is broken" not in rendered[kind], (
            f"kind={kind!r} wrongly reassures: {rendered[kind][:220]}")
    # A NAMED outage also has to LOOK like one, not merely withhold the
    # reassurance - is-broken is what styles the panel as a failure.
    assert "is-broken" in rendered["schedule_unavailable"], rendered["schedule_unavailable"][:220]
    assert "is-broken" not in rendered[None], (
        "an UNKNOWN kind must not be styled as a confirmed outage either")


def test_dfs_slate_section_renders_both_boards_and_the_selector():
    """The shell gives this page no scoring bar, so the contest-format selector
    has to ride inside the section or the reader cannot switch formats at all."""
    c = _dfs_ctx()
    html = c.eval('__go("#section=slate")')
    assert "Probable starters" in html and ">Hitters<" in html
    assert "Contest scoring" in html, html[:400]
    # Each board names its own sort state; sharing one is how a click on a
    # hitter column re-sorts the pitchers by a column they do not have.
    assert 'data-dfsboard="pitchers"' in html and 'data-dfsboard="hitters"' in html


def test_dfs_value_board_is_honest_without_salaries():
    c = _dfs_boot(_opt_payload())
    html = c.eval('__go("#section=value")')
    assert "nothing to value" in html
    assert "Name,Position,Salary" in html          # the import form is right there
    priced = _dfs_ctx().eval('__go("#section=value")')
    assert "Pts/$1k" in priced and "Ace Arm" in priced


def test_dfs_stacks_refuses_to_dress_a_sum_as_a_stack_projection():
    c = _dfs_ctx()
    html = c.eval('__go("#section=stacks")')
    assert "Top 4" in html and "Top 5" in html
    assert "correlation" in html.lower(), html[:600]
    assert "we do not model it" in html


# ---------------------------------------------------------------------------
# The C1/C2 seam: the generated shells and the clients must agree
# ---------------------------------------------------------------------------
SHELLS = {"dynasty": (ROOT / "dynasty" / "index.html", "data-dynastysection"),
          "redraft": (ROOT / "redraft" / "index.html", "data-redraftsection"),
          "dfs": (ROOT / "dfs" / "index.html", "data-dfssection")}


@pytest.mark.parametrize("name", sorted(SHELLS))
def test_shell_section_keys_are_known_to_the_client(name):
    """The shell's nav attribute values ARE the canonical section names: the
    client compares them directly when it paints the active tab. A tab the
    client does not know renders the fallback board under a nav announcing
    something else, which is the exact bug this pins."""
    path, attr = SHELLS[name]
    if not path.exists():
        pytest.skip(f"{path.name} is generated by build_site and is not in the tree yet")
    keys = set(re.findall(attr + r'="([a-z_]+)"', path.read_text(encoding="utf-8")))
    assert keys, f"{name} shell declares no sections"
    src = _code(name)
    m = re.search(r"var SECTIONS = \[(.*?)\];", src, re.DOTALL)
    assert m, f"{name}.js must declare its section alternation"
    known = set(re.findall(r'"([a-z_]+)"', m.group(1)))
    assert keys <= known, (name, sorted(keys - known))


@pytest.mark.parametrize("name", sorted(SHELLS))
def test_shell_loads_its_own_client(name):
    path, _attr = SHELLS[name]
    if not path.exists():
        pytest.skip(f"{path.name} is generated by build_site and is not in the tree yet")
    html = path.read_text(encoding="utf-8")
    assert re.search(r"/assets/%s\.js\?v=" % name, html), name
    # The Diamond flag has to be on the page before the app reads it.
    assert "diamond-config.js" in html, name


def test_dfs_csv_import_matches_by_name_and_reports_misses():
    """The salary reader finds its columns by header name, joins on a folded
    name key, and tells the reader exactly what it could not place."""
    c = _dfs_boot(_opt_payload())
    c.eval('__go("#section=salaries")')
    csv = ("Position,Name,Salary,TeamAbbrev\n"
           "P,Ace Arm,9000,AAA\n"
           "C,Star Catcher,8000,CCC\n"
           "OF,\"Nobody Here\",4000,ZZZ\n")
    c.eval("__setValue('#dfs-csv-text', %s)" % json.dumps(csv))
    html = c.eval('__click("#dfs-csv-go")')
    assert "matched 2 to the slate" in html, html[:500]
    assert "Nobody Here" in html, html[:500]


# ===========================================================================
# 5. The dynasty client and its keeper calculator
# ===========================================================================
DYN_PAYLOAD = json.dumps({
    "season": 2026, "n_players": 0,
    "scoring_catalog": [], "players": [],
    "sections": {
        "dynasty": [
            {"mlbam": 101, "name": "First Kid", "org": "BOS", "pos": "SS", "eta": 2027,
             "efv": 62.4, "star": 31, "bust": 12, "surplus": 88.0, "band": [15.0, 190.0],
             "score": 9.1, "rank": 1, "tier": "Elite"},
            {"mlbam": 102, "name": "Middle Kid", "org": "SEA", "pos": "SP", "eta": 2029,
             "efv": 51.6, "star": 12, "bust": 28, "surplus": 22.0, "band": [0.0, 70.0],
             "score": 5.2, "rank": 25, "tier": "Tier 1"},
            {"mlbam": 103, "name": "Depth Kid", "org": "NYM", "pos": "OF", "eta": 2030,
             "efv": 44.2, "star": 5, "bust": 44, "surplus": 6.0, "band": [0.0, 30.0],
             "score": 2.1, "rank": 240, "tier": "Depth"},
        ],
        "callup_watch": [
            {"mlbam": 201, "name": "Almost Up", "org": "TEX", "pos": "C",
             "eta": 2026, "fv": 52.5, "fvE": 54.4},
        ],
    },
})


def _dyn_ctx():
    c = MiniRacer()
    c.eval(APP_PRELUDE % DYN_PAYLOAD)
    c.eval((ASSETS / "dynasty.js").read_text(encoding="utf-8"))
    return c


def test_dynasty_board_renders_served_grades_only():
    c = _dyn_ctx()
    html = c.eval('__go("#section=board")')
    assert "First Kid" in html and "Depth Kid" in html
    # The served rank leads and the eFV grade displays to nearest (62.4 -> 62).
    assert ">62<" in html, html[:800]
    assert "Keep by" in html


def test_dynasty_lens_is_a_preset_over_served_columns():
    """The contend and rebuild lenses re-sort the SAME board. Nothing about the
    model changes, so the eFV column must be identical under every lens."""
    c = _dyn_ctx()
    def grades(h):
        return sorted(re.findall(r'mlb-metric-label">.*?eFV.*?</span>(\d+)', c.eval(
            '__go(%s)' % json.dumps(h))))
    base = grades("#section=board")
    assert base, "the board must render an eFV column"
    assert grades("#section=board&lens=contend") == base
    assert grades("#section=board&lens=rebuild") == base


def test_dynasty_keeper_break_even_math():
    """12 teams, pick 6, a prospect the board ranks 25th: the keeper pays for
    itself from round 3 on, because pick 30 (round 3, slot 6) is the first
    pick later than his rank. At the default round 5 (pick 54) the verdict is
    keep with a +29 edge."""
    c = _dyn_ctx()
    html = c.eval('__go("#section=keeper")')
    assert "costs pick <b>54</b>" in html, html[:900]
    row = re.search(r"Middle Kid.*?</tr>", html, re.DOTALL)
    assert row, html[:1200]
    assert "R3" in row.group(0), row.group(0)
    assert "keep" in row.group(0) and "+29" in row.group(0), row.group(0)
    # No dollar valuation anywhere on the surface.
    assert "$" not in row.group(0), row.group(0)


def test_dynasty_keeper_settings_change_the_answer():
    """Editing a league setting re-renders the table off the new numbers and
    persists them, so the reader does not retype his league every visit."""
    c = _dyn_ctx()
    c.eval('__go("#section=keeper")')
    c.eval("__setValue('#dyn-k-teams', '20')")
    html = c.eval("__fireEvent('#dyn-k-teams', 'change')")
    # 20 teams, pick 6, round 5 -> pick 86 overall.
    assert "costs pick <b>86</b>" in html, html[:900]
    assert json.loads(c.eval("__LS['eephus.dynasty.keeper']"))["teams"] == 20


def test_dynasty_callup_watch_prefers_efv():
    c = _dyn_ctx()
    html = c.eval('__go("#section=callups")')
    assert "Almost Up" in html
    assert ">54<" in html, html[:800]     # eFV 54.4 to nearest, not the 53 ceiling of 52.5


def test_dynasty_empty_payload_is_a_note_not_a_blank():
    c = MiniRacer()
    c.eval(APP_PRELUDE % json.dumps({"season": 2026, "sections": {}}))
    c.eval((ASSETS / "dynasty.js").read_text(encoding="utf-8"))
    html = c.eval('__go("#section=board")')
    assert "nightly build" in html and "Nothing is broken" in html


# ===========================================================================
# 6. The scoring control is SCOPED to the tabs it can move (2026-08-07)
# ===========================================================================
# The owner reported the league-format selector as broken. It was not: it
# re-ranks 230 of 250 SP under SABR and 342 of 350 hitters under 5x5. What was
# broken was WHERE it rendered. The shell reserves a bar above the section nav
# and redraft.js filled it on all seven tabs, including the default landing tab
# (Daily Streamers), which is scored server-side in FanGraphs Points and cannot
# move. A control that visibly does nothing is indistinguishable from a broken
# one, so these pin the scoping rather than the re-ranking.
SCORED_TABS = ["ros_sp", "ros_rp", "ros_hitter"]
UNSCORED_TABS = ["streamers", "two_start", "buysell", "closers"]


def _redraft_ctx():
    c = MiniRacer()
    c.eval(PARITY_PRELUDE)
    c.eval(CARD_JS.read_text(encoding="utf-8"))
    c.eval((ASSETS / "redraft.js").read_text(encoding="utf-8"))
    return c


def _bar(c) -> str:
    return c.eval("__html['redraft-scoring'] || __html['fantasy-scoring'] || ''")


@pytest.mark.parametrize("section", SCORED_TABS)
def test_format_bar_renders_on_the_sections_it_moves(section):
    c = _redraft_ctx()
    c.eval('__go("#section=%s")' % section)
    assert "rd-scorebtn" in _bar(c), section


@pytest.mark.parametrize("section", UNSCORED_TABS)
def test_format_bar_is_absent_where_it_would_do_nothing(section):
    c = _redraft_ctx()
    c.eval('__go("#section=%s")' % section)
    assert "rd-scorebtn" not in _bar(c), (
        f"the league-format bar renders on {section}, which does not read it")


def test_leaving_a_scored_tab_clears_the_bar():
    """The bar is emptied on the way OUT, not merely skipped on the way in. A
    tab change that only re-rendered the section left the previous tab's bar
    sitting above a board that ignores it."""
    c = _redraft_ctx()
    c.eval('__go("#section=ros_sp")')
    assert "rd-scorebtn" in _bar(c)
    c.eval('__go("#section=closers")')
    assert "rd-scorebtn" not in _bar(c)


def test_ros_hitters_says_the_two_points_formats_share_one_table():
    """fantasy.json carries ONE scoring.hitter dict, because FanGraphs Points
    and SABR Points differ only on the pitching side. That is Ottoneu's rule,
    not a gap in ours, and the board says so rather than leaving a reader to
    conclude the selector is dead."""
    c = _redraft_ctx()
    html = c.eval('__go("#section=ros_hitter")')
    assert "share one hitter table" in html, html[:400]


def test_streamer_copy_does_not_point_at_a_bar_that_is_not_there():
    c = _redraft_ctx()
    html = c.eval('__go("#section=streamers")')
    assert "switch formats above" not in html


# ===========================================================================
# 7. The fantasy player card
# ===========================================================================
def test_card_is_not_a_second_corpus():
    """It fetches ONE thing, tonight's slate, and only when a reader opens a
    card. The rest is a lookup into the payload the host already downloaded, so
    there is no page-per-player build and no second copy of fantasy.json."""
    src = _src("card")
    urls = re.findall(r'DFS_URL\s*=\s*"([^"]+)"', src)
    assert urls == ["/data/dfs.json"], urls
    fetches = [f.strip() for f in re.findall(r"fetch\(\s*([^,)]+)", src)]
    assert fetches == ["DFS_URL"], fetches
    assert "/data/fantasy.json" not in _code("card")


def test_card_does_not_carry_a_second_scoring_port():
    """The four-format line comes from the HOST, because the port lives in
    assets/redraft.js and test_redraft_scoring_matches_fantasy drives THAT file
    against the frozen assets/fantasy.js. A copy here would be a third
    implementation nobody is comparing."""
    src = _code("card")
    for bad in ("function scorePoints", "function rotoValue", "scoring.hitter",
                "scoring_catalog[", "fpts_fgp"):
        assert bad not in src, f"fantasy-card.js grew its own scoring: {bad}"
    assert "HOST.scoreLine" in src


def _card_html(c) -> str:
    """The overlay is created through document.createElement, which both JS
    harnesses register under the id 'c'."""
    return c.eval("__html['c'] || ''")


def test_card_renders_a_pitcher_with_every_format_and_his_line():
    c = _redraft_ctx()
    c.eval('__go("#section=ros_sp&player=694973")')
    assert c.eval("window.EEPHUS_FANTASY_CARD.isOpen()") is True
    html = _card_html(c)
    assert "Paul Skenes" in html
    labels = re.findall(r'fc-score-l">([^<]+)', html)
    assert labels == ["FanGraphs Points", "SABR Points",
                      "Old School (5x5)", "Ottoneu Classic (4x4)"], labels
    # The served projection, not a recomputation of it.
    assert re.search(r'fc-stat-l">IP</span>62\.0', html), html[:900]
    assert 'data-gl="sem_plus"' in html


def test_card_renders_a_hitter_with_the_luck_and_buy_signal():
    c = _redraft_ctx()
    c.eval('__go("#section=ros_hitter&player=660271")')
    html = _card_html(c)
    assert "Shohei Ohtani" in html
    assert 'data-gl="hem_plus"' in html and 'data-gl="xhem_plus"' in html
    assert "buy low" in html
    # The two POINTS formats agree on a hitter, which is the same Ottoneu fact
    # the board note states. Seeing it on the card is the point of the row.
    vals = re.findall(r'fc-score-v">([^<]+)', html)
    assert vals[0] == vals[1], vals


def test_card_never_scores_a_category_format_against_a_pool_of_one():
    """A category value is a POSITION IN A POOL. A player the served board does
    not carry has no pool, so the two roto rows are left off rather than
    computed against a pool that does not contain him. The points rows still
    render: those are a dot product and need nobody else."""
    payload = json.loads(PARITY_PAYLOAD)
    payload["sections"]["ros_sp"] = [694973, 434378]      # Cease dropped
    c = MiniRacer()
    c.eval(PARITY_PRELUDE.replace(PARITY_PAYLOAD, json.dumps(payload)))
    c.eval(CARD_JS.read_text(encoding="utf-8"))
    c.eval((ASSETS / "redraft.js").read_text(encoding="utf-8"))
    c.eval('__go("#section=ros_sp&player=656302")')
    html = _card_html(c)
    assert "Dylan Cease" in html, html[:400]
    labels = re.findall(r'fc-score-l">([^<]+)', html)
    assert labels == ["FanGraphs Points", "SABR Points"], labels


def test_card_falls_back_to_the_dynasty_row_for_a_prospect():
    """A prospect on the dynasty board has no rest-of-season record, which is
    not an error: he has not played in the majors. The card is still a card."""
    c = MiniRacer()
    c.eval(APP_PRELUDE % DYN_PAYLOAD)
    c.eval(CARD_JS.read_text(encoding="utf-8"))
    c.eval((ASSETS / "dynasty.js").read_text(encoding="utf-8"))
    c.eval('__go("#section=dynasty&player=102")')
    html = _card_html(c)
    assert "Middle Kid" in html
    # eFV 51.6 displays to NEAREST (52), served verbatim, never recomputed.
    assert re.search(r'data-gl="xfv">eFV</span></b>52<', html), html[:900]
    # The keeper break-even is this page's own arithmetic, handed in by the host.
    assert "Keep by" in html and "R3" in html


def test_card_link_carries_the_whole_board_state():
    """A card link copied out of the page has to restore the board it was
    opened from, so the href is the full hash and not a bare #player=."""
    c = _redraft_ctx()
    board = c.eval('__go("#section=ros_sp&sys=sabr")')
    hrefs = re.findall(r'href="(#[^"]*player=694973)"', board)
    assert hrefs, board[:600]
    assert "section=ros_sp" in hrefs[0] and "sys=sabr" in hrefs[0], hrefs[0]


# ===========================================================================
# 8. DFS freshness: the client self-check and the exporter's crash path
# ===========================================================================
def test_dfs_client_flags_a_past_slate_that_carries_no_stamp():
    """stale_slate is written by the PUBLISH DECISION, so it only exists on the
    paths that reached one. A run that never happened, or one that died before
    it, leaves an old payload on disk with no flag: on 2026-08-07 /dfs/ served
    the 2026-08-05 slate at full confidence for exactly that reason. A slate
    date in the past is enough to know."""
    payload = json.loads(_opt_payload())
    payload["slate_date"] = "2020-04-01"      # unambiguously behind any clock
    payload.pop("stale_slate", None)
    c = _dfs_boot(json.dumps(payload))
    html = c.eval('__go("#section=slate")')
    assert "This is the 2020-04-01 slate, not today's." in html, html[:400]
    # The exporter's own claim must NOT be borrowed here: nobody decided to keep
    # this board, the build simply never replaced it.
    assert "We kept the last board" not in html
    assert "old slate" in c.eval("__html['dfs-banner'] || ''")


def test_dfs_client_leaves_todays_slate_alone():
    import datetime
    payload = json.loads(_opt_payload())
    payload["slate_date"] = datetime.date.today().isoformat()
    c = _dfs_boot(json.dumps(payload))
    html = c.eval('__go("#section=slate")')
    assert "not today's" not in html
    assert "old slate" not in c.eval("__html['dfs-banner'] || ''")


def test_dfs_client_still_prefers_the_exporters_own_reason():
    """When the exporter DID make the call, its sentence and its checked-at
    stamp are what the reader sees. The self-check is a floor, not a rewrite."""
    payload = json.loads(_opt_payload())
    payload.update({"slate_date": "2020-04-01", "stale_slate": True,
                    "stale_reason": "the schedule feed did not answer",
                    "stale_checked_at": "2020-04-02T00:00:00Z"})
    c = _dfs_boot(json.dumps(payload))
    html = c.eval('__go("#section=slate")')
    assert "the schedule feed did not answer" in html
    assert "We kept the last board" in html
    assert "Checked 2020-04-02T00:00:00Z" in html


def _crash_refresh(monkeypatch, out, day, prev=None):
    import dfs_export as dx
    if prev is not None:
        out.write_text(json.dumps(prev), encoding="utf-8")

    def boom(**_kw):
        raise RuntimeError("simulated build crash")

    monkeypatch.setattr(dx, "build_payload", boom)
    n = dx.refresh(log=lambda *_a, **_k: None, day=day, out_path=out)
    return n, json.loads(out.read_text(encoding="utf-8"))


def test_dfs_crash_path_stamps_the_board_it_leaves_serving(tmp_path, monkeypatch):
    """The `except` around build_payload used to return 0 without touching the
    file, so a crashed run left the previous payload UNSTAMPED and the page
    served it as today's. A build that died is the same publish decision as a
    build we refused."""
    import datetime
    today = datetime.date.today()
    prev = {"slate_date": (today - datetime.timedelta(days=1)).isoformat(),
            "n_players": 42, "players": [{"mlbam": 1}]}
    n, got = _crash_refresh(monkeypatch, tmp_path / "dfs.json", today.isoformat(), prev)
    assert n == 42                       # what is SERVED, which is the old board
    assert got["stale_slate"] is True
    assert got["stale_kind"] == "build_failed"
    assert got["stale_age_days"] == 1
    assert got["stale_checked_at"]


def test_dfs_crash_path_respects_the_carry_bound(tmp_path, monkeypatch):
    """Past the bound the stale board is worse than the honest empty state, and
    the crash path gets that rule too rather than freezing /dfs/ forever."""
    import datetime
    import dfs_export as dx
    today = datetime.date.today()
    old = (today - datetime.timedelta(days=dx._MAX_STALE_CARRY_DAYS + 5)).isoformat()
    prev = {"slate_date": old, "n_players": 42, "players": [{"mlbam": 1}]}
    n, got = _crash_refresh(monkeypatch, tmp_path / "dfs.json", today.isoformat(), prev)
    assert n == 0
    assert got["empty_reason_kind"] == "build_failed"
    assert got["slate_date"] == today.isoformat()
    assert got["previous_slate_dropped"]["slate_date"] == old


def test_dfs_crash_path_with_nothing_on_disk_publishes_the_empty_state(tmp_path, monkeypatch):
    import datetime
    n, got = _crash_refresh(monkeypatch, tmp_path / "dfs.json",
                            datetime.date.today().isoformat())
    assert n == 0
    assert got["empty_reason_kind"] == "build_failed"
    assert got["players"] == []


def test_the_client_knows_the_build_failed_kind():
    """Every kind the exporter can stamp needs a headline here, or the payload
    says one thing and the page renders the generic fallback."""
    import dfs_export as dx
    src = _src("dfs")
    for kind in dx._KEEP_PREVIOUS_KINDS:
        assert kind + ":" in src, f"dfs.js has no empty-state copy for {kind}"


# ---------------------------------------------------------------------------
# The shells load the card module
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["dynasty", "redraft"])
def test_card_hosts_ship_the_card_module(name):
    """Both fantasy board shells load it, and BEFORE their own client: the host
    attaches to an API that has to already exist. Both tags are deferred, so
    document order is execution order."""
    path = ROOT / name / "index.html"
    if not path.exists():
        pytest.skip(f"{path.name} is generated by build_site and is not in the tree yet")
    html = path.read_text(encoding="utf-8")
    assert re.search(r"/assets/fantasy-card\.js\?v=", html), name
    assert html.index("fantasy-card.js") < html.index("/assets/%s.js" % name), name


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
