# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Tests for the props box-score grader (betting_settle, 2026-08-19).

WHAT THESE TESTS PIN:

  1. THE FOUR REGISTERED MARKETS AND NOTHING ELSE. The grader's stat table is
     pinned against betting_ingest.PROPS_MARKETS and the calibration ledger's
     PROPS_CAL_MARKETS, so the three copies cannot drift and a fifth market
     cannot be graded by accident.
  2. THE OUTCOME TABLE. Over/under win and lose off the player's own count,
     a whole-number line landing exactly is a PUSH (the total-market
     convention), a player with no action in a FINAL game is a VOID (stake
     back, no evidence), and everything the grader cannot prove stays OPEN:
     a live game, a missing feed, an ambiguous name, a missing stat key.
  3. INERT-SAFETY. With zero props rows stored, settle_props reads no feed,
     writes no byte and logs no line. Today's ledgers hold zero props rows,
     so this is the branch every nightly takes until the owner's arming
     produces rows.
  4. THE WIRING. betting_settle.run carries the props leg, first, inside its
     own try, so a props failure cannot stop the team ledgers from settling.

Every test doubles as a plain function: `python test_props_grader.py` runs
them all without pytest (the no-pytest rule).
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import betting_ingest as bi
import betting_settle as bs
import betting_shadow
from tools import betting_calibration as bc

ROOT = Path(__file__).parent


# ===========================================================================
# fixtures (inline; nothing here reads tonight's data/ or .cache/ files)
# ===========================================================================
def _feed(game_pk, *, final=True, home_players=(), away_players=(),
          home_runs=5, away_runs=3):
    """A minimal StatsAPI game feed: exactly the paths the grader reads."""
    def team(players):
        return {"players": {
            f"ID{900000 + i}": {
                "person": {"fullName": nm},
                "stats": {"batting": dict(bat), "pitching": dict(pit)},
            } for i, (nm, bat, pit) in enumerate(players)}}
    return {
        "gamePk": game_pk,
        "gameData": {"status": {
            "abstractGameState": "Final" if final else "Live"}},
        "liveData": {
            "linescore": {"teams": {"home": {"runs": home_runs},
                                    "away": {"runs": away_runs}}},
            "boxscore": {"teams": {"home": team(home_players),
                                   "away": team(away_players)}},
        },
    }


_HOME = (
    ("Casey Whiff", {}, {"strikeOuts": 7, "inningsPitched": "6.0"}),
    ("Ronald Acuña Jr.", {"hits": 2, "totalBases": 5, "homeRuns": 1,
                               "atBats": 4}, {}),
    ("Bench Guy", {}, {}),
    ("Sam Same", {"hits": 1, "totalBases": 1, "homeRuns": 0, "atBats": 3}, {}),
)
_AWAY = (
    ("Sam Same", {"hits": 0, "totalBases": 0, "homeRuns": 0, "atBats": 4}, {}),
    ("Only Batter", {"hits": 3, "totalBases": 4, "homeRuns": 0,
                     "atBats": 5}, {}),
)


def _feed_dir(tmp: Path) -> Path:
    d = tmp / "game_feeds"
    d.mkdir(parents=True, exist_ok=True)
    (d / "77.json").write_text(json.dumps(
        _feed(77, home_players=_HOME, away_players=_AWAY)), encoding="utf-8")
    (d / "78.json").write_text(json.dumps(
        _feed(78, final=False, home_players=_HOME)), encoding="utf-8")
    return d


def _box(tmp: Path, game_pk=77):
    return bs.load_boxscore(game_pk, feed_dir=_feed_dir(tmp))


def _shadow_row(sid, market, player, side, point, *, game_pk=77,
                decimal=1.91, odds=-110):
    """The record_props_slate row shape, condensed to the graded fields."""
    return {"shadow_id": sid, "posted_at": "2026-08-18T00:00:00+00:00",
            "provisional": True, "stake_units": 1.0, "min_edge_used": 0.06,
            "gate_state": {}, "result": None, "settled_at": None,
            "profit_units": None, "slate_date": "2026-08-18",
            "game_pk": game_pk, "matchup": "NYY at ATL", "market": market,
            "player": player, "side": side,
            "selection": f"{player} {side} {point}", "point": point,
            "book": "bk", "odds_at_post": odds, "decimal": decimal,
            "edge": 0.07, "model_prob": 0.55, "market_fair_prob": 0.5,
            "ev_per_unit": 0.05, "slot": market}


def _cal_open(cid, market, player, side, point, *, game_pk=77,
              model_prob=0.6):
    return {"cal_id": cid, "phase": bc.PHASE_OPEN,
            "written_at": "2026-08-18T00:00:00+00:00",
            "slate_date": "2026-08-18", "game_pk": game_pk,
            "matchup": "NYY at ATL", "market": market, "side": side,
            "player": player, "label": f"{player} {side} {point}",
            "point": point, "model_prob": model_prob,
            "best_odds": -110, "best_book": "bk", "best_decimal": 1.91}


# ===========================================================================
# 1. the registration: four markets, three copies, zero drift
# ===========================================================================
def test_stat_table_matches_the_registered_markets():
    """PROPS_STAT_KEYS grades exactly the four registered markets, in the
    props_<key> vocabulary, and agrees with the calibration ledger's copy."""
    registered = tuple(f"props_{m}" for m in bi.PROPS_MARKETS)
    assert tuple(bs.PROPS_STAT_KEYS) == registered
    assert set(bc.PROPS_CAL_MARKETS) == set(registered)
    # Every market names a real facet and a count-valued StatsAPI key.
    for group, key in bs.PROPS_STAT_KEYS.values():
        assert group in ("batting", "pitching")
        assert key in ("strikeOuts", "totalBases", "hits", "homeRuns")


def test_an_unregistered_market_grades_none():
    with tempfile.TemporaryDirectory() as td:
        box = _box(Path(td))
        assert bs.grade_props(market="props_batter_rbis", side="over",
                              point=0.5, player="Only Batter", box=box) is None
        assert bs.grade_props(market="moneyline", side="home", point=None,
                              player="Only Batter", box=box) is None


# ===========================================================================
# 2. the outcome table: win / loss / push / void / open
# ===========================================================================
def test_over_and_under_grade_off_the_players_own_count():
    """Casey Whiff struck out 7. Over 6.5 wins, under 6.5 loses, over 7.5
    loses, under 7.5 wins."""
    with tempfile.TemporaryDirectory() as td:
        box = _box(Path(td))
        g = lambda side, pt: bs.grade_props(  # noqa: E731
            market="props_pitcher_strikeouts", side=side, point=pt,
            player="Casey Whiff", box=box)
        assert g("over", 6.5) == "won"
        assert g("under", 6.5) == "lost"
        assert g("over", 7.5) == "lost"
        assert g("under", 7.5) == "won"


def test_a_whole_number_line_landing_exactly_is_a_push():
    """Acuna had 2 hits; over 2 and under 2 both PUSH, the total-market
    convention. The half line beside it does not."""
    with tempfile.TemporaryDirectory() as td:
        box = _box(Path(td))
        for side in ("over", "under"):
            assert bs.grade_props(market="props_batter_hits", side=side,
                                  point=2.0, player="Ronald Acuna Jr",
                                  box=box) == "push"
        assert bs.grade_props(market="props_batter_hits", side="over",
                              point=1.5, player="Ronald Acuna Jr",
                              box=box) == "won"


def test_no_action_in_a_final_game_is_a_void():
    """A scratched player (not in the box score) and a bench bat with an
    empty batting line both VOID; a pitcher market on a position player who
    never threw voids too."""
    with tempfile.TemporaryDirectory() as td:
        box = _box(Path(td))
        assert bs.grade_props(market="props_batter_hits", side="over",
                              point=0.5, player="Scratched Star",
                              box=box) == "void"
        assert bs.grade_props(market="props_batter_hits", side="over",
                              point=0.5, player="Bench Guy", box=box) == "void"
        assert bs.grade_props(market="props_pitcher_strikeouts", side="over",
                              point=3.5, player="Only Batter",
                              box=box) == "void"


def test_open_states_stay_open():
    """A live game, a missing feed and an ambiguous name all grade None:
    every one of them could resolve differently later or is a matching
    failure, and none of them may become a guess."""
    with tempfile.TemporaryDirectory() as td:
        fd = _feed_dir(Path(td))
        live = bs.load_boxscore(78, feed_dir=fd)
        assert live is not None and live["final"] is False
        assert bs.grade_props(market="props_pitcher_strikeouts", side="over",
                              point=5.5, player="Casey Whiff",
                              box=live) is None
        assert bs.load_boxscore(999999, feed_dir=fd) is None
        assert bs.grade_props(market="props_batter_hits", side="over",
                              point=0.5, player="Casey Whiff",
                              box=None) is None
        # Two Sam Sames, one per team: refusing to guess which was bet.
        box = bs.load_boxscore(77, feed_dir=fd)
        status, _ = bs.props_actual(box, market="props_batter_hits",
                                    player="Sam Same")
        assert status == "open"
        assert bs.grade_props(market="props_batter_hits", side="over",
                              point=0.5, player="Sam Same", box=box) is None


def test_accent_and_suffix_normalization_match_the_feed():
    """The odds feed strips accents and sometimes the suffix; both forms must
    reach the same statline."""
    with tempfile.TemporaryDirectory() as td:
        box = _box(Path(td))
        for name in ("Ronald Acuna Jr.", "Ronald Acuña Jr.",
                     "ronald acuna jr", "Ronald Acuna"):
            status, actual = bs.props_actual(
                box, market="props_batter_total_bases", player=name)
            assert (status, actual) == ("ok", 5), (name, status, actual)


def test_void_and_push_return_the_stake():
    assert bs.profit_units(result="void", decimal=1.91) == 0.0
    assert bs.profit_units(result="push", decimal=1.91) == 0.0
    assert bs.profit_units(result="won", decimal=1.91) == 0.91
    assert bs.profit_units(result="lost", decimal=1.91) == -1.0


# ===========================================================================
# 3. settle_props: the shadow ledger
# ===========================================================================
def test_settle_props_grades_the_shadow_ledger():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        fd = _feed_dir(tmp)
        sh = tmp / "shadow.json"
        cal = tmp / "cal.jsonl"
        rows = [
            _shadow_row("s1", "props_pitcher_strikeouts", "Casey Whiff",
                        "over", 6.5),                          # won
            _shadow_row("s2", "props_pitcher_strikeouts", "Casey Whiff",
                        "under", 6.5),                         # lost
            _shadow_row("s3", "props_batter_hits", "Ronald Acuna Jr",
                        "over", 2.0),                          # push
            _shadow_row("s4", "props_batter_home_runs", "Bench Guy",
                        "over", 0.5),                          # void
            _shadow_row("s5", "props_batter_hits", "Sam Same",
                        "over", 0.5),                          # open: ambiguous
            _shadow_row("s6", "props_batter_hits", "Ronald Acuna Jr",
                        "over", 1.5, game_pk=78),              # open: live game
        ]
        betting_shadow.write(rows, path=sh)
        out = bs.settle_props(shadow_path=sh, cal_path=cal, feed_dir=fd)
        assert out["shadow"]["settled"] == 4
        assert out["shadow"]["void"] == 1
        assert out["shadow"]["open"] == 2
        got = {r["shadow_id"]: r for r in betting_shadow.load(sh)}
        assert got["s1"]["result"] == "won"
        assert got["s1"]["profit_units"] == 0.91
        assert got["s1"]["final_home_runs"] == 5
        assert got["s1"]["final_away_runs"] == 3
        assert got["s2"]["result"] == "lost"
        assert got["s2"]["profit_units"] == -1.0
        assert got["s3"]["result"] == "push"
        assert got["s3"]["profit_units"] == 0.0
        assert got["s4"]["result"] == "void"
        assert got["s4"]["profit_units"] == 0.0
        assert got["s5"]["result"] is None
        assert got["s6"]["result"] is None
        # Idempotent: a second pass settles nothing and rewrites nothing.
        again = bs.settle_props(shadow_path=sh, cal_path=cal, feed_dir=fd)
        assert again["shadow"]["settled"] == 0
        assert again["shadow"]["open"] == 2


def test_settled_props_rows_enter_only_their_own_tag():
    """The team pool (slot=None) must never see a settled props row; the
    props tag reaches it by name. This is the seam the min_edge clocks
    condition on."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        fd = _feed_dir(tmp)
        sh = tmp / "shadow.json"
        betting_shadow.write([
            _shadow_row("s1", "props_pitcher_strikeouts", "Casey Whiff",
                        "over", 6.5),
        ], path=sh)
        bs.settle_props(shadow_path=sh, cal_path=tmp / "cal.jsonl",
                        feed_dir=fd)
        assert betting_shadow.graded_bets(slot=None, path=sh) == []
        tagged = betting_shadow.graded_bets(
            slot="props_pitcher_strikeouts", path=sh)
        assert len(tagged) == 1 and tagged[0]["won"] is True


# ===========================================================================
# 4. settle_props: the calibration ledger and the gate's counting rules
# ===========================================================================
def test_settle_props_scores_the_calibration_ledger():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        fd = _feed_dir(tmp)
        sh = tmp / "shadow.json"
        cal = tmp / "cal.jsonl"
        bc.append([
            _cal_open("c1", "props_pitcher_strikeouts", "Casey Whiff",
                      "over", 6.5, model_prob=0.6),            # won
            _cal_open("c2", "props_pitcher_strikeouts", "Casey Whiff",
                      "under", 6.5, model_prob=0.4),           # lost
            _cal_open("c3", "props_batter_hits", "Ronald Acuna Jr",
                      "over", 2.0),                            # push
            _cal_open("c4", "props_batter_home_runs", "Bench Guy",
                      "over", 0.5),                            # void
            _cal_open("c5", "props_batter_hits", "Ronald Acuna Jr",
                      "over", 1.5, game_pk=78),                # open
        ], path=cal)
        out = bs.settle_props(shadow_path=sh, cal_path=cal, feed_dir=fd)
        assert out["calibration"]["settled"] == 4
        assert out["calibration"]["void"] == 1
        assert out["calibration"]["open"] == 1
        got = {r["cal_id"]: r for r in bc.rows(path=cal)}
        assert got["c1"]["result"] == "won"
        assert got["c1"]["brier"] == round((0.6 - 1.0) ** 2, 6)
        assert got["c2"]["result"] == "lost"
        assert got["c2"]["brier"] == round(0.4 ** 2, 6)
        # A push and a void carry no Brier: the binary never resolved.
        assert got["c3"]["result"] == "push" and got["c3"]["brier"] is None
        assert got["c4"]["result"] == "void" and got["c4"]["brier"] is None
        assert got["c5"].get("result") is None
        # Second pass: idempotent.
        again = bs.settle_props(shadow_path=sh, cal_path=cal, feed_dir=fd)
        assert again["calibration"]["settled"] == 0


def test_canonical_counting_takes_won_or_lost_overs_only():
    """The section 7b gate counts one canonical (over) side per (market,
    game, player), won/lost only: a push, a void and an under add no canonical
    game. Pinned here because the min_edge and gate clocks start off exactly
    this count."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        fd = _feed_dir(tmp)
        cal = tmp / "cal.jsonl"
        bc.append([
            _cal_open("c1", "props_pitcher_strikeouts", "Casey Whiff",
                      "over", 6.5),                            # won: counts
            _cal_open("c2", "props_pitcher_strikeouts", "Casey Whiff",
                      "under", 6.5),                           # not canonical
            _cal_open("c3", "props_batter_hits", "Ronald Acuna Jr",
                      "over", 2.0),                            # push: no count
            _cal_open("c4", "props_batter_home_runs", "Bench Guy",
                      "over", 0.5),                            # void: no count
            _cal_open("c5", "props_batter_hits", "Only Batter",
                      "over", 1.5),                            # won: counts
        ], path=cal)
        bs.settle_props(shadow_path=tmp / "shadow.json", cal_path=cal,
                        feed_dir=fd)
        by_market = bc.canonical_settled_games(bc.rows(path=cal))
        assert len(by_market["props_pitcher_strikeouts"]) == 1
        assert len(by_market["props_batter_hits"]) == 1
        assert len(by_market["props_batter_home_runs"]) == 0


# ===========================================================================
# 5. inert-safety: zero props rows settles nothing, reads nothing, says nothing
# ===========================================================================
def test_zero_props_rows_is_a_silent_no_op():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        logged = []
        orig = bs.load_boxscore
        bs.load_boxscore = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("a feed was read with zero props rows stored"))
        try:
            out = bs.settle_props(shadow_path=tmp / "none.json",
                                  cal_path=tmp / "none.jsonl",
                                  feed_dir=tmp / "no_feeds",
                                  log_fn=logged.append)
        finally:
            bs.load_boxscore = orig
        assert out["reason"] == "no open props rows in any ledger"
        assert out["shadow"]["settled"] == 0
        assert out["calibration"]["settled"] == 0
        assert logged == []
        assert not (tmp / "none.json").exists()
        assert not (tmp / "none.jsonl").exists()


def test_team_rows_alone_are_also_a_no_op():
    """A ledger holding only TEAM rows takes the same silent branch: the
    props leg keys on the props_ prefix, never on the ledger being non-empty."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        sh = tmp / "shadow.json"
        betting_shadow.write([{
            "shadow_id": "t1", "slate_date": "2026-08-18", "game_pk": 77,
            "market": "moneyline", "side": "home", "odds_at_post": -110,
            "decimal": 1.91, "edge": 0.07, "stake_units": 1.0,
            "result": None, "settled_at": None, "profit_units": None,
            "slot": "ev_rank",
        }], path=sh)
        out = bs.settle_props(shadow_path=sh, cal_path=tmp / "cal.jsonl",
                              feed_dir=tmp / "no_feeds")
        assert out["reason"] == "no open props rows in any ledger"
        assert betting_shadow.load(sh)[0]["result"] is None


# ===========================================================================
# 6. the wiring: run() carries the props leg, isolated in its own try
# ===========================================================================
def test_run_carries_the_props_leg_first_and_isolated():
    orig = (bs.settle_props, betting_shadow.settle, bc.settle)
    calls = []
    try:
        bs.settle_props = lambda **kw: (calls.append("props")
                                        or {"reason": "stub"})
        betting_shadow.settle = lambda **kw: (calls.append("shadow")
                                              or {"settled": 0})
        bc.settle = lambda **kw: (calls.append("cal") or {"settled": 0})
        out = bs.run(games=[])
        assert out["props"] == {"reason": "stub"}
        assert calls == ["props", "shadow", "cal"]
        # A props failure is contained: the team legs still settle.
        calls.clear()
        def _boom(**kw):
            raise RuntimeError("props leg exploded")
        bs.settle_props = _boom
        out = bs.run(games=[])
        assert str(out["props"]["reason"]).startswith("failed:")
        assert calls == ["shadow", "cal"]
    finally:
        bs.settle_props, betting_shadow.settle, bc.settle = orig


# ===========================================================================
# runner (the no-pytest rule: python test_props_grader.py runs everything)
# ===========================================================================
def main() -> int:
    import traceback
    fns = [(k, v) for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"{len(fns) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
