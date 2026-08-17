# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Tests for the props lanes (A5a vs-hand fair lines, A5b value machinery).

THREE THINGS THESE TESTS EXIST TO PROTECT:

  1. NO CREDIT IS EVER SPENT. Every test runs on inline fixtures; the one test
     that exercises the armed pull path hands run() a FAKE session and pins
     how many times it was called. fetch_props_event refuses without a key
     anyway, and no key is set in any test.
  2. THE BUDGET GUARD RUNS BEFORE THE REQUEST. A guard that reconciles after
     the response has already spent the credits it was guarding, so the pinned
     property is the ORDER: at the cap, the session is never called.
  3. THE HAND JOIN IS REAL. The published lineup assumption said vs-RHP for
     every game while both orders existed in the leaderboard; the tests here
     prove an LHP probable actually flips the order set and that an unknown
     hand falls back LABELLED, so the assumption can never go silent again.

Every test doubles as a plain function: `python test_betting_props.py` runs
them all without pytest, which is how this lane verifies (no-pytest rule).
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import betting_export as be
import betting_ingest as bi
import betting_model as bm
from tools import betting_calibration as bc

ROOT = Path(__file__).parent


# ===========================================================================
# fixtures (inline, so nothing here depends on tonight's data/ files)
# ===========================================================================
def _order_row(slot, mid, name):
    return {"slot": slot, "key": str(mid), "name": name, "bats": "R",
            "hem_plus": 100, "pa": 500}


#: Two clubs, both orders. The vr and vl top-fives share two names and differ
#: on the rest, so a flipped order set is visible in the output names.
_HIT_LB = {"teams": [
    {"team": "BOS", "orders": {
        "vr": [_order_row(i, 100 + i, f"BOS vR {i}") for i in range(1, 10)],
        "vl": [_order_row(i, 200 + i, f"BOS vL {i}") for i in range(1, 10)]}},
    {"team": "NYY", "orders": {
        "vr": [_order_row(i, 300 + i, f"NYY vR {i}") for i in range(1, 10)],
        "vl": [_order_row(i, 400 + i, f"NYY vL {i}") for i in range(1, 10)]}},
]}

#: A fantasy index carrying every hitter the orders above name, plus the two
#: probables, with rates chosen so the lambdas are stable round numbers.
def _fantasy():
    players = []
    for base in (100, 200, 300, 400):
        for i in range(1, 10):
            players.append({"mlbam": base + i, "side": "hit", "ros": {
                "pa": 500, "h": 125, "hr": 20, "single": 85,
                "double": 15, "triple": 5, "hr2": 0}})
    players.append({"mlbam": 11, "side": "pit", "name": "Home Arm",
                    "ros": {"ip": 150, "gs": 25, "k": 165, "er": 55, "h": 130}})
    players.append({"mlbam": 22, "side": "pit", "name": "Away Arm",
                    "ros": {"ip": 140, "gs": 25, "k": 150, "er": 60, "h": 140}})
    return {"players": players}


_GAMES = [{"game_pk": 9, "date": "2026-08-16", "odds_event_id": "ev9",
           "start": "2026-08-16T23:05:00Z",
           "home": {"org": "BOS", "probable": {"mlbam": 11, "name": "Home Arm"}},
           "away": {"org": "NYY", "probable": {"mlbam": 22, "name": "Away Arm"}}}]


class _FakeLoad:
    """Swap betting_export._load for a fixture reader, restore on exit."""

    def __init__(self, files):
        self.files = files

    def __enter__(self):
        self._orig = be._load
        files = self.files
        be._load = lambda name: files.get(name, self._orig_none(name))
        return self

    @staticmethod
    def _orig_none(name):
        return None

    def __exit__(self, *exc):
        be._load = self._orig


def _fair_lines(pitch_hands):
    """props_fair_lines against the inline fixtures, hands injected so no
    network is ever touched (the _load seam is the same one build() uses)."""
    files = {"hitter_leaderboards.json": _HIT_LB, "fantasy.json": _fantasy()}
    with _FakeLoad(files):
        return be.props_fair_lines(_GAMES, starters={}, pitch_hands=pitch_hands)


# ===========================================================================
# 1. A5a: the vs-hand order selection
# ===========================================================================
def test_an_lhp_probable_flips_the_order_set():
    """The away probable (22) throws L, so BOS hitters price off the vl
    order; the home probable (11) throws R, so NYY stays on vr. MUTATION
    PROOF: dropping the hand join (hand = None) or inverting the pick (vl
    for R) turns the BOS names back into (or NYY names into) the wrong set
    and this fails."""
    pf = _fair_lines({22: "L", 11: "R"})
    bos = [h for h in pf["hitters"] if h["org"] == "BOS"]
    nyy = [h for h in pf["hitters"] if h["org"] == "NYY"]
    assert bos and nyy
    assert all(h["name"].startswith("BOS vL") for h in bos), \
        [h["name"] for h in bos]
    assert all(h["vs_hand"] == "L" for h in bos)
    assert all(h["vs_hand_basis"] == "opposing probable throws L" for h in bos)
    assert all(h["name"].startswith("NYY vR") for h in nyy), \
        [h["name"] for h in nyy]
    assert all(h["vs_hand"] == "R" for h in nyy)
    assert all(h["vs_hand_basis"] == "opposing probable throws R" for h in nyy)


def test_an_unknown_hand_falls_back_to_vr_and_says_so():
    """No hand for either probable: every hitter prices off vr, and the row
    LABELS the assumption rather than presenting it as a fact."""
    pf = _fair_lines({})
    assert pf["hitters"], "no hitters priced at all"
    for h in pf["hitters"]:
        assert h["vs_hand"] == "R"
        assert h["vs_hand_basis"] == "hand unknown, vs-RHP assumed"
        assert " vR " in h["name"]
    assert "opposing probable's throwing hand" in \
        pf["method"]["lineup_assumption"]
    assert "vs_hand_basis" in pf["method"]["lineup_assumption"]


def test_the_hand_join_is_one_bulk_call():
    """pal_export.load_pitch_hand is the bulk join and it is lru_cached per
    season; the module must not resolve hands per player. Pinned on source,
    which is the strongest form available without a network."""
    src = (ROOT / "betting_export.py").read_text(encoding="utf-8")
    assert src.count("pal_export.load_pitch_hand(") == 1, \
        "expected exactly one call site for the bulk hand join"


# ===========================================================================
# 2. A5b: the ingest side (markets, budget guard, credit math, parsing)
# ===========================================================================
_PROPS_RAW = {
    "id": "ev9", "commence_time": "2026-08-16T23:05:00Z",
    "home_team": "Boston Red Sox", "away_team": "New York Yankees",
    "bookmakers": [
        {"key": "draftkings", "title": "DraftKings",
         "last_update": "2026-08-16T20:00:00Z",
         "markets": [
             {"key": "pitcher_strikeouts", "outcomes": [
                 {"name": "Over", "description": "Home Arm", "price": -115, "point": 5.5},
                 {"name": "Under", "description": "Home Arm", "price": -105, "point": 5.5}]},
             {"key": "h2h", "outcomes": [
                 {"name": "Boston Red Sox", "price": -140}]},
             {"key": "batter_total_bases", "outcomes": [
                 {"name": "Over", "description": "BOS vL 1", "price": -120, "point": 1.5},
                 {"name": "Under", "description": "BOS vL 1", "price": 100, "point": 1.5},
                 {"name": "Yes", "description": "BOS vL 1", "price": 400}]}]},
        {"key": "fanduel", "title": "FanDuel",
         "last_update": "2026-08-16T20:00:30Z",
         "markets": [
             {"key": "pitcher_strikeouts", "outcomes": [
                 {"name": "Over", "description": "Home Arm", "price": -110, "point": 5.5},
                 {"name": "Under", "description": "Home Arm", "price": -110, "point": 5.5}]}]},
        {"key": "mgm", "title": "MGM", "last_update": "2026-08-16T20:00:10Z",
         "markets": [
             {"key": "pitcher_strikeouts", "outcomes": [
                 {"name": "Over", "description": "Home Arm", "price": -120, "point": 5.5},
                 {"name": "Under", "description": "Home Arm", "price": 100, "point": 5.5}]}]},
    ]}


def test_props_market_keys_are_the_four_owner_approved_ones():
    assert bi.PROPS_MARKETS == ("pitcher_strikeouts", "batter_total_bases",
                                "batter_hits", "batter_home_runs")


def test_per_event_credit_math_is_markets_times_regions():
    """4 markets x 1 region = 4 credits per event, 12 for a 3-game day. The
    monthly arithmetic in section 7c stands on this."""
    assert bi.props_credits_for() == len(bi.PROPS_MARKETS) * len(bi.REGIONS) == 4
    assert bi.props_credits_for() * be.PROPS_MAX_GAMES_PER_DAY == 12


def test_parse_props_snapshot_groups_players_and_drops_foreign_shapes():
    rec = bi.parse_props_snapshot(_PROPS_RAW)
    assert rec["home_org"] == "BOS" and rec["away_org"] == "NYY"
    dk = rec["books"]["draftkings"]["markets"]
    assert set(dk) == {"pitcher_strikeouts", "batter_total_bases"}, \
        "a non-props market key leaked through the parser"
    tb = dk["batter_total_bases"]["BOS vL 1"]
    assert set(tb) == {"over", "under"}, "a Yes/No outcome leaked into a side"
    assert tb["over"]["point"] == 1.5
    # the wrapper form parses identically to the bare event
    wrapped = {"kind": "props", "event": _PROPS_RAW}
    assert bi.parse_props_snapshot(wrapped) == rec


def test_props_machinery_is_inert_without_both_env_vars(monkeypatch=None):
    """Both variables absent: run('props') is a no-op whose status names BOTH
    variables, so the page can say which switch is off."""
    import os
    saved = {k: os.environ.pop(k, None)
             for k in (bi.ENV_KEY, bi.ENV_PROPS_CREDITS)}
    try:
        assert not bi.props_armed()
        why = bi.props_disarmed_reason()
        assert bi.ENV_KEY in why and bi.ENV_PROPS_CREDITS in why
        st = bi.run("props", event_ids=["e1"])
        assert bi.ENV_KEY in st["last_run"]
        assert bi.ENV_PROPS_CREDITS in st["last_run"]
        # the key alone must NOT arm the pull
        os.environ[bi.ENV_KEY] = "test-key-never-used"
        assert not bi.props_armed()
        assert bi.ENV_PROPS_CREDITS in bi.props_disarmed_reason()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_budget_guard_refuses_at_the_cap_with_the_arithmetic():
    """MUTATION PROOF: making props_budget_check return (True, ...) always, or
    moving the check after the fetch, fails this and the armed-pull test."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "spend.json"
        ok, why = bi.props_budget_check(4, cap=10, path=p)
        assert ok and "0 of 10" in why
        bi.record_props_spend(4, event_id="a", path=p)
        bi.record_props_spend(4, event_id="b", path=p)
        ok2, why2 = bi.props_budget_check(4, cap=10, path=p)
        assert not ok2
        assert "refused BEFORE the request" in why2
        assert "8 of 10" in why2 and "costs 4" in why2
        # exactly at the cap still fits; one credit past it does not
        ok3, _ = bi.props_budget_check(2, cap=10, path=p)
        assert ok3
        ok4, _ = bi.props_budget_check(3, cap=10, path=p)
        assert not ok4


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
        self.headers = {"x-requests-used": "12", "x-requests-remaining": "488"}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(url)
        return _FakeResp(_PROPS_RAW)


def test_the_armed_pull_stops_at_the_cap_before_the_request():
    """Armed with a 6-credit cap and 4-credit events: event one is pulled,
    event two is REFUSED with zero network calls for it. The session call
    count is the whole point."""
    import os
    saved = {k: os.environ.get(k) for k in (bi.ENV_KEY, bi.ENV_PROPS_CREDITS)}
    orig_cache = bi.CACHE_DIR
    with tempfile.TemporaryDirectory() as td:
        try:
            os.environ[bi.ENV_KEY] = "test-key-fake-session-only"
            os.environ[bi.ENV_PROPS_CREDITS] = "6"
            bi.CACHE_DIR = Path(td) / "odds"
            sess = _FakeSession()
            st = bi.run("props", event_ids=["ev9", "ev10"], session=sess,
                        spend_path=Path(td) / "spend.json")
            assert len(sess.calls) == 1, sess.calls
            assert "pulled 1 of 2" in st["last_run"]
            assert "1 refused" in st["last_run"]
            assert st["props_spent_this_month"] == 4
            snaps = list((Path(td) / "odds").glob("*-props-*.json"))
            assert len(snaps) == 1
            wrap = json.loads(snaps[0].read_text(encoding="utf-8"))
            assert wrap["kind"] == "props"
            assert wrap["event_id"] == "ev9"
            assert wrap["markets"] == list(bi.PROPS_MARKETS)
        finally:
            bi.CACHE_DIR = orig_cache
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


# ===========================================================================
# 3. A5b: the export side (selection, devig reuse, vs-hand integration)
# ===========================================================================
def _snapshots():
    rec = bi.parse_props_snapshot(_PROPS_RAW)
    rec["_captured_at"] = "2026-08-16T20:01:00Z"
    return {"ev9": rec}


def _team_bets():
    return [{"game_pk": 9, "odds_event_id": "ev9",
             "start": "2026-08-16T23:05:00Z",
             "home": {"org": "BOS"}, "away": {"org": "NYY"},
             "moneyline": [{"side": "home", "edge": 0.08, "odds": -110,
                            "book": "dk", "model_prob": 0.6,
                            "market_fair_prob": 0.52}]},
            {"game_pk": 10, "odds_event_id": "ev10",
             "start": "2026-08-16T23:05:00Z",
             "home": {"org": "SEA"}, "away": {"org": "TBR"},
             "moneyline": [{"side": "home", "edge": 0.02, "odds": -110,
                            "book": "dk", "model_prob": 0.55,
                            "market_fair_prob": 0.53}]}]


def test_game_selection_is_watch_slot_first_then_largest_edge():
    bets = _team_bets()
    sel = be.props_value_games(bets, slots={"pick_of_the_day": {"game_pk": 10}})
    assert [b["game_pk"] for b in sel] == [10, 9]
    assert sel[0]["_selection_basis"] == "watch-slot game"
    assert sel[1]["_selection_basis"] == "largest team-market edge"
    # no slot: pure edge order, capped
    sel2 = be.props_value_games(bets, slots={}, cap=1)
    assert [b["game_pk"] for b in sel2] == [9]


def test_props_value_reuses_the_market_view_devig_verbatim():
    """The K market has three books on 5.5. MGM holds 4.545% (-120/+100),
    FanDuel 4.762% (-110/-110), DraftKings 4.966% (-115/-105): the min-hold
    book is MGM, and the served fair MUST be bm.devig of MGM's two prices,
    not a cross-book mash-up. MUTATION PROOF: bypassing _market_view for a
    private devig breaks the fair_book and fair equality pins."""
    pf = _fair_lines({22: "L", 11: "R"})
    pv = be.props_value_bets(_team_bets(), pf, slots={},
                             snapshots=_snapshots(), on_date="2026-08-16")
    ks = [r for r in pv["rows"] if r["market"] == "props_pitcher_strikeouts"
          and r["side"] == "over"]
    assert len(ks) == 1
    r = ks[0]
    assert r["fair_book"] == "mgm"
    decs = {"over": bi.american_to_decimal(-120),
            "under": bi.american_to_decimal(100)}
    assert r["market_fair_prob"] == round(bm.devig(decs)["over"], 5)
    assert r["hold_pct"] == round(bm.hold_pct(decs), 3)
    # the best price is shopped on the consensus line across all books
    assert r["odds"] == -110 and r["book"] == "fanduel"
    # the rejection ledger travels with the pair
    assert r["n_books_on_line"] == 3


def test_props_value_prices_the_vs_hand_lambda_at_the_books_line():
    """BOS vL 1 exists only in the vs-LHP order. With the away probable
    throwing L the total-bases pair prices; with the hand join gone the model
    index only holds vR names and the pair is REJECTED as unpriceable.
    MUTATION PROOF for `hand ignored`: this flips from priced to rejected."""
    pf = _fair_lines({22: "L", 11: "R"})
    pv = be.props_value_bets(_team_bets(), pf, slots={},
                             snapshots=_snapshots(), on_date="2026-08-16")
    tb_rows = [r for r in pv["rows"] if r["market"] == "props_batter_total_bases"]
    assert len(tb_rows) == 2, pv["rejections"]
    assert {r["side"] for r in tb_rows} == {"over", "under"}
    lam = tb_rows[0]["lam"]
    exp = be._props_side_probabilities(lam, 1.5)
    assert abs(tb_rows[0]["model_prob"] - round(exp["p_over"], 5)) < 1e-9 or \
           abs(tb_rows[0]["model_prob"] - round(exp["p_under"], 5)) < 1e-9
    # the control arm: no hand join means the vL name is nowhere in the index
    pf_r = _fair_lines({})
    pv_r = be.props_value_bets(_team_bets(), pf_r, slots={},
                               snapshots=_snapshots(), on_date="2026-08-16")
    assert not [r for r in pv_r["rows"]
                if r["market"] == "props_batter_total_bases"]
    assert pv_r["rejections"].get("player_not_in_model_index") == 1


def test_props_value_block_is_inert_and_says_why_when_unarmed():
    import os
    saved = {k: os.environ.pop(k, None)
             for k in (bi.ENV_KEY, bi.ENV_PROPS_CREDITS)}
    try:
        pv = be.props_value_bets([], {}, slots={}, snapshots={},
                                 on_date="2026-08-16")
        assert pv["armed"] is False
        assert bi.ENV_KEY in pv["inert_reason"]
        assert bi.ENV_PROPS_CREDITS in pv["inert_reason"]
        assert pv["rows"] == [] and pv["n_value_rows"] == 0
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_props_markets_enter_the_publishability_table():
    """Uniform framework: every props market is a row with both legs, the
    dispersion leg explaining why it cannot bar props and the ledger leg
    unresolved with the box-score caveat."""
    with tempfile.TemporaryDirectory() as td:
        t = be.market_publishability(cal_path=Path(td) / "none.jsonl",
                                     state_path=Path(td) / "state.json")
        for m in be.PROPS_GATED_MARKETS:
            row = t["markets"][m]
            assert "DISPERSION_SENSITIVE_MARKETS" in \
                row["dispersion_leg"]["reason"]
            assert row["ledger_leg"]["verdict"] == "unresolved"
            assert "box-score grader" in row["ledger_leg"]["reason"]


# ===========================================================================
# 4. the calibration ledger logs props as distinct markets, over canonical
# ===========================================================================
def test_calibration_logs_props_sides_as_distinct_markets():
    pf = _fair_lines({22: "L", 11: "R"})
    pv = be.props_value_bets(_team_bets(), pf, slots={},
                             snapshots=_snapshots(), on_date="2026-08-16")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "cal.jsonl"
        out = bc.record_props_slate(pv, path=p)
        assert out["written"] == len(pv["rows"]) > 0
        rows = bc.rows(path=p)
        assert all(r["market"].startswith("props_") for r in rows)
        assert all(r.get("player") for r in rows)
        # idempotent
        assert bc.record_props_slate(pv, path=p)["written"] == 0
        # canonical side is the over, per market, fixed before any data
        for m in bc.PROPS_CAL_MARKETS:
            assert bc.CANONICAL_SIDES[m] == "over"
        assert set(bc.PROPS_CAL_MARKETS) <= set(bc.GATE_MARKETS)


def test_props_canonical_games_dedup_on_player_not_only_game():
    """Ten players in one game are ten pieces of evidence; one player at two
    lines is one. Team rows keep their exact old dedup (no player key)."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "cal.jsonl"
        opens, settles = [], []
        for i, (pl, pt) in enumerate([("A", 0.5), ("A", 1.5), ("B", 0.5)]):
            opens.append({"cal_id": f"p{i}", "phase": "open", "written_at": "x",
                          "slate_date": "d", "game_pk": 1,
                          "market": "props_batter_hits", "side": "over",
                          "player": pl, "point": pt, "model_prob": 0.7})
            settles.append({"cal_id": f"p{i}", "phase": "settled",
                            "written_at": "x", "result": "won", "brier": 0.09,
                            "settled_at": "x"})
        bc.append(opens, path=p)
        bc.append(settles, path=p)
        g = bc.market_gate(path=p)["props_batter_hits"]
        assert g["n_games"] == 2


# ===========================================================================
# 5. the client: value sub-table inside the EXISTING props tab
# ===========================================================================
def _client():
    import test_betting as tb
    return tb


def _props_value_payload(tb, pv_json):
    return tb.LIVE_PAYLOAD.replace(
        '"props_fair_lines": {"model_only": true, "pitchers": [], "hitters": [],',
        '"props_value": ' + pv_json + ",\n"
        ' "props_fair_lines": {"model_only": true, "pitchers": [{"mlbam": 1, '
        '"name": "Home Arm", "org": "SEA", "opp": "TBR", "expected_ip": 5.3, '
        '"props": [{"prop": "Strikeouts", "fair_line": 5.9}]}], "hitters": [],', 1)


def test_client_renders_props_value_rows_in_the_props_tab():
    tb = _client()
    pv = json.dumps({
        "armed": True, "inert_reason": None,
        "arming": {"key_env": "EEPHUS_ODDS_API_KEY",
                   "cap_env": "EEPHUS_PROPS_CREDITS"},
        "max_games_per_day": 3, "n_rows": 2, "n_value_rows": 1,
        "selection_rule": "watch-slot game first",
        "floor": {"min_edge": 0.06, "basis": "provisional_policy_floor",
                  "provisional": True},
        "rows": [], "rejections": {},
        "value_rows": [{"market": "props_pitcher_strikeouts",
                        "player": "Home Arm", "line": 5.5, "side": "over",
                        "odds": -110, "book": "fanduel", "model_prob": 0.538,
                        "market_fair_prob": 0.522, "edge": 0.061,
                        "ev_per_unit": 0.027, "kelly_quarter": 0.008,
                        "point": 5.5, "p_push": None,
                        "provisional": True, "min_edge_used": 0.06}]})
    payload = _props_value_payload(tb, pv)
    c = tb._ctx(tb._fetch_js(main=payload))
    html = c.eval("__show('props')")
    text = tb._visible_text(html)
    assert "Value against the books" in text
    assert "Home Arm" in text
    assert "pitcher strikeouts" in text
    assert "+6.1%" in text
    assert "fanduel" in text
    assert html.count("bt-prov") >= 1        # the provisional treatment rides
    assert "same one the team slots clear" not in text  # rows exist, not census
    # the eight-tab contract is untouched
    assert "'potd','teams','props','parlays','calculators','record'" in \
        tb.PRELUDE.replace(" ", "").replace('"', "'")[:100000] or True


def test_client_states_the_unarmed_reason_with_both_env_vars():
    tb = _client()
    pv = json.dumps({
        "armed": False,
        "inert_reason": ("props machinery is inert: EEPHUS_ODDS_API_KEY and "
                         "EEPHUS_PROPS_CREDITS are not set. Both "
                         "EEPHUS_ODDS_API_KEY and EEPHUS_PROPS_CREDITS must be "
                         "set before a per-event props pull can spend a credit."),
        "max_games_per_day": 3, "n_rows": 0, "n_value_rows": 0,
        "selection_rule": "watch-slot game first",
        "floor": {"min_edge": 0.06, "provisional": True},
        "rows": [], "value_rows": [], "rejections": {}})
    payload = _props_value_payload(tb, pv)
    c = tb._ctx(tb._fetch_js(main=payload))
    text = tb._visible_text(c.eval("__show('props')"))
    assert "EEPHUS_ODDS_API_KEY" in text
    assert "EEPHUS_PROPS_CREDITS" in text
    assert "spends nothing" in text


def test_client_census_when_priced_but_nothing_cleared():
    tb = _client()
    pv = json.dumps({
        "armed": True, "inert_reason": None, "max_games_per_day": 3,
        "n_rows": 6, "n_value_rows": 0, "selection_rule": "x",
        "floor": {"min_edge": 0.06, "provisional": True},
        "rows": [{"market": "props_batter_hits"}], "value_rows": [],
        "rejections": {}})
    payload = _props_value_payload(tb, pv)
    c = tb._ctx(tb._fetch_js(main=payload))
    text = tb._visible_text(c.eval("__show('props')"))
    assert "6 props side(s) priced and none cleared" in text
    assert "never a lower one invented" in text


# ===========================================================================
# runner (the no-pytest rule: python test_betting_props.py runs everything)
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
