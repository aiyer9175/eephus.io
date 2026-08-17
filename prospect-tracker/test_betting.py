# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Tests for the /betting/ module (betting_ingest / betting_model / betting_export).

FOUR THINGS THESE TESTS EXIST TO PROTECT, in order of how much damage their
absence would do:

  1. THE RECORD IS APPEND-ONLY. A published betting record whose rows can be
     edited is worth less than no record at all, because it looks like
     evidence. `check_append_only` must raise on a deletion, on any byte
     changing in a published row, and on a reused bet_id. If one of these ever
     goes green by accident the module is lying to readers.

  2. NO CREDIT IS EVER SPENT BY THE SUITE. Every odds test runs on
     test_fixtures/odds_api_mlb_sample.json. `fetch_snapshot` is never called,
     and it refuses to run without a key anyway.

  3. THE MODEL DOES NOT CLAIM VALIDATION IT DOES NOT HAVE. `min_edge` stays
     None, `pick_of_the_day` stays absent, and the payload keeps saying
     unvalidated until a clean out-of-sample test exists. The vintage half of
     that claim lives in test_leaderboard_vintages.py: the store, the
     strictly-before read, the two grading modes and the three gates on
     `min_edge`. What is pinned HERE is the shipped artifact.

  4. THE LEGAL BLOCK CANNOT GO MISSING. 21+, informational only, not legal
     everywhere, 1-800-GAMBLER, no affiliate links: pinned in the payload AND
     in the client source, including on the load-failure path.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

import betting_export as be
import betting_ingest as bi
import betting_model as bm

ROOT = Path(__file__).parent
FIXTURE = ROOT / "test_fixtures" / "odds_api_mlb_sample.json"
JS_PATH = ROOT / "assets" / "betting.js"
JS = JS_PATH.read_text(encoding="utf-8")
RAW = json.loads(FIXTURE.read_text(encoding="utf-8"))


# ===========================================================================
# 1. THE APPEND-ONLY RECORD (the load-bearing test in this file)
# ===========================================================================
def _fixture_record() -> list[dict]:
    return [
        {"bet_id": "aaaa1111bbbb2222", "posted_at": "2026-08-01T15:02:00+00:00",
         "slate_date": "2026-08-01", "market": "h2h", "selection": "NYM",
         "book": "draftkings", "odds_at_post": -140, "stake_units": 1.0,
         "result": "won", "settled_at": "2026-08-01T23:40:00+00:00",
         "odds_at_close": -160, "beat_close": True, "clv_pct": 8.929},
        {"bet_id": "cccc3333dddd4444", "posted_at": "2026-08-02T15:01:00+00:00",
         "slate_date": "2026-08-02", "market": "totals", "selection": "Under 8.5",
         "book": "fanduel", "odds_at_post": -105, "stake_units": 1.0,
         "result": "lost", "settled_at": "2026-08-02T23:50:00+00:00",
         "odds_at_close": -115, "beat_close": True, "clv_pct": 9.524},
    ]


def test_append_only_accepts_a_pure_append():
    existing = _fixture_record()
    proposed = existing + [{"bet_id": "eeee5555", "result": "open", "odds_at_post": 120}]
    be.check_append_only(existing, proposed)          # must not raise


def test_append_only_rejects_editing_a_published_row():
    """The would-be mutation: a loser quietly becomes a winner. This is the
    single failure mode the whole record design exists to make impossible."""
    existing = _fixture_record()
    mutated = json.loads(json.dumps(existing))
    mutated[1]["result"] = "won"
    with pytest.raises(be.RecordImmutabilityError) as exc:
        be.check_append_only(existing, mutated)
    assert "row 1" in str(exc.value)


def test_append_only_rejects_a_nudged_price():
    """A one-cent price edit is the same crime as flipping a result: it moves
    the ROI and the CLV without moving the W-L."""
    existing = _fixture_record()
    mutated = json.loads(json.dumps(existing))
    mutated[0]["odds_at_post"] = -135
    with pytest.raises(be.RecordImmutabilityError):
        be.check_append_only(existing, mutated)


def test_append_only_rejects_a_deletion():
    existing = _fixture_record()
    with pytest.raises(be.RecordImmutabilityError) as exc:
        be.check_append_only(existing, existing[:1])
    assert "shrink" in str(exc.value)


def test_append_only_rejects_a_reused_bet_id():
    existing = _fixture_record()
    dupe = existing + [dict(existing[0])]
    with pytest.raises(be.RecordImmutabilityError):
        be.check_append_only(existing, dupe)


def test_append_only_ignores_key_order():
    """Re-serializing a row must not read as a mutation, or the export would
    fail every run for a reason that is not a defect."""
    existing = _fixture_record()
    reordered = [dict(reversed(list(r.items()))) for r in existing]
    be.check_append_only(existing, reordered)


def test_write_record_refuses_a_mutation_on_disk(tmp_path):
    """End to end through the file: fixture record written, then a mutation
    attempted. The file must be untouched afterwards."""
    path = tmp_path / "betting_record.json"
    be.write_record(_fixture_record(), path=path)
    before = path.read_text(encoding="utf-8")
    mutated = json.loads(before)
    mutated[0]["result"] = "lost"
    with pytest.raises(be.RecordImmutabilityError):
        be.write_record(mutated, path=path)
    assert path.read_text(encoding="utf-8") == before


def test_append_record_grows_the_file(tmp_path):
    path = tmp_path / "betting_record.json"
    be.write_record(_fixture_record(), path=path)
    rows = be.append_record([{"bet_id": "ffff6666", "result": "open"}], path=path)
    assert len(rows) == 3
    assert json.loads(path.read_text(encoding="utf-8"))[2]["bet_id"] == "ffff6666"


def test_unreadable_record_raises_rather_than_resetting(tmp_path):
    """A corrupt file must NOT read as an empty record: that would hand the
    next write a blank baseline and let it overwrite everything."""
    path = tmp_path / "betting_record.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(be.RecordImmutabilityError):
        be.load_record(path)


def test_missing_record_is_an_empty_record(tmp_path):
    assert be.load_record(tmp_path / "nope.json") == []


# ---- the storage seam: which backend answers load_record() -----------------
def test_load_record_reads_the_jsonl_and_not_the_git_tracked_json(tmp_path, monkeypatch):
    """THE GO-LIVE FIX, pinned. The two backends are made to hold DIFFERENT
    rows and the untracked JSONL must win.

    Without this test the fix is revertible by accident and the suite stays
    green: every other record test passes an explicit `path`, so nothing
    exercised the no-path branch at all. The defect it protects against is the
    one that destroyed the record - data/betting_record.json is git-tracked and
    deploy/nightly-build.sh runs `git checkout -- .` before every pipeline, so
    a row appended at 21:00 was reverted to the committed `[]` at 03:10 and
    `check_append_only` then waved the same one-row proposal through as a legal
    append. If load_record ever reads the JSON while a log exists, that returns
    silently and nothing anywhere raises."""
    jsonl = tmp_path / "record.jsonl"
    legacy = tmp_path / "betting_record.json"
    durable = _fixture_record()
    # The JSON holds something a checkout could plausibly have restored: fewer
    # rows, and the one it shares carries a DIFFERENT result.
    reverted = [{**durable[0], "result": "lost"}]
    legacy.write_text(json.dumps(reverted), encoding="utf-8")
    monkeypatch.setattr(be, "RECORD_JSONL", jsonl)
    monkeypatch.setattr(be, "RECORD_PATH", legacy)
    be.write_record(durable, path=jsonl)

    rows = be.load_record()
    assert len(rows) == 2, "the JSONL has two rows; the reverted JSON has one"
    assert rows[0]["result"] == "won", (
        "load_record answered from the git-tracked JSON while an append-only "
        "log existed; that is the reverted-by-checkout defect")
    assert rows == durable
    # And the module says so out loud, because the blocker reads this.
    store = be.record_storage()
    assert store["backend"] == "jsonl" and store["durable"] is True
    assert store["authoritative_path"] == str(jsonl)
    assert store["chain_sha"] == be.chain_sha(durable)


def test_load_record_falls_back_to_the_json_only_when_no_log_exists(tmp_path, monkeypatch):
    """The other half of the seam. A fresh box with rows in the committed JSON
    and no log yet must read them rather than reporting an empty record."""
    monkeypatch.setattr(be, "RECORD_JSONL", tmp_path / "record.jsonl")
    legacy = tmp_path / "betting_record.json"
    legacy.write_text(json.dumps(_fixture_record()), encoding="utf-8")
    monkeypatch.setattr(be, "RECORD_PATH", legacy)
    assert be.load_record() == _fixture_record()
    assert be.record_storage()["durable"] is False


# ---- record summary math ---------------------------------------------------
def test_record_summary_on_the_fixture():
    r = be.record_summary(_fixture_record())
    assert (r["won"], r["lost"], r["n_settled"]) == (1, 1, 2)
    # The -140 winner returns 100/140 = +0.7143u; the -105 loser costs 1u, so
    # the ledger is -0.2857u on 2u risked, which is -14.29% ROI. A 1-1 record
    # with a favourite winner is a LOSING month, and the summary has to say so.
    assert r["net_units"] == pytest.approx(-0.286, abs=0.002)
    assert r["roi_pct"] == pytest.approx(-14.29, abs=0.02)
    assert r["beat_close_rate"] == 1.0
    assert r["stake_policy"] == "flat 1 unit"


def test_record_summary_empty_reports_empty_not_zero_roi():
    r = be.record_summary([])
    assert r["n_rows"] == 0 and r["roi_pct"] is None
    assert r["beat_close_rate"] is None and r["avg_clv_pct"] is None


def test_grade_clv_direction():
    """Backing -140 and watching it close -160 is a beat: the price shortened."""
    g = be.grade_clv(-140, -160)
    assert g["beat_close"] is True and g["clv_pct"] > 0
    bad = be.grade_clv(-160, -140)
    assert bad["beat_close"] is False and bad["clv_pct"] < 0
    assert be.grade_clv(None, -140)["beat_close"] is None


# ===========================================================================
# 2. INGEST: fixture only, never the network
# ===========================================================================
def test_credit_arithmetic_is_markets_times_regions():
    """A credit is markets x regions. This is the number the whole free-tier
    plan rests on, so it gets a test rather than a comment."""
    assert bi.credits_for(("h2h", "spreads", "totals"), ("us",)) == 3
    assert bi.credits_for(("h2h",), ("us", "uk")) == 2
    assert bi.credits_for() == 3
    assert bi.credits_for() * 2 * 31 < 500       # open + close, every day, with headroom


def test_parse_events_maps_both_org_code_sets():
    evs = bi.parse_events(RAW)
    assert len(evs) == 4
    pairs = {(e["away_org"], e["home_org"]) for e in evs}
    # canonical_org output, NOT the StatsAPI abbreviations: TBR not TB, WSN not WSH.
    assert ("TBR", "COL") in pairs and ("WSN", "PHI") in pairs


def test_parse_events_keeps_american_prices_and_points():
    ev = [e for e in bi.parse_events(RAW) if e["home_org"] == "CLE"][0]
    dk = ev["books"]["draftkings"]
    assert dk["h2h"] == {"home": 118, "away": -140}
    assert dk["spreads"]["home"]["point"] == 1.5
    assert dk["totals"]["over"]["point"] == 8.5


def test_parse_events_tolerates_a_book_with_one_market():
    ev = [e for e in bi.parse_events(RAW) if e["home_org"] == "PHI"][0]
    assert "h2h" in ev["books"]["betmgm"] and "totals" not in ev["books"]["betmgm"]


def test_best_price_takes_the_longest_price():
    ev = [e for e in bi.parse_events(RAW) if e["home_org"] == "CLE"][0]
    best = bi.best_price(ev, "h2h", "home")
    assert best["book"] == "fanduel" and best["price"] == 122   # +122 beats +118


def test_parse_events_accepts_a_snapshot_wrapper():
    wrapped = {"kind": "open", "events": RAW}
    assert len(bi.parse_events(wrapped)) == 4


def test_snapshots_are_immutable_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(bi, "CACHE_DIR", tmp_path)
    when = datetime(2026, 8, 4, 13, 5, tzinfo=timezone.utc)
    p = bi.write_snapshot(RAW, kind="open", when=when)
    assert p.name == "2026-08-04-1305.json"
    with pytest.raises(FileExistsError):
        bi.write_snapshot(RAW, kind="close", when=when)
    assert json.loads(p.read_text(encoding="utf-8"))["kind"] == "open"


def test_fetch_refuses_without_a_key(monkeypatch):
    """The suite must not be able to spend a credit even by accident."""
    monkeypatch.delenv(bi.ENV_KEY, raising=False)
    with pytest.raises(RuntimeError):
        bi.fetch_snapshot()


def test_odds_conversions_round_trip():
    assert bi.american_to_decimal(-110) == pytest.approx(1.90909, abs=1e-5)
    assert bi.american_to_decimal(150) == 2.5
    assert bi.decimal_to_american(2.5) == 150
    assert bi.decimal_to_american(1.90909090909) == -110
    assert bi.american_to_decimal(0) is None
    assert bi.decimal_to_american(1.0) is None


def test_closing_window_is_the_earliest_first_pitch():
    games = [{"datetime": "2026-08-04T23:40:00Z"}, {"datetime": "2026-08-04T22:35:00Z"}]
    assert bi.closing_window(games) == "2026-08-04T22:35:00Z"
    assert bi.closing_window([]) is None


# ===========================================================================
# 3. MODEL
# ===========================================================================
def test_devig_is_proportional_and_sums_to_one():
    """-110 / -110 is a 4.76% hold and de-vigs to exactly 50/50."""
    decs = {"a": bi.american_to_decimal(-110), "b": bi.american_to_decimal(-110)}
    fair = bm.devig(decs)
    assert fair["a"] == pytest.approx(0.5) and fair["b"] == pytest.approx(0.5)
    assert bm.hold_pct(decs) == pytest.approx(4.7619, abs=1e-3)
    assert sum(fair.values()) == pytest.approx(1.0)


def test_devig_lopsided_market_hand_checked():
    """-140 / +122: raw implieds 0.58333 and 0.45045 sum to 1.03378, so the
    proportional fair favourite is 0.58333 / 1.03378 = 0.56422."""
    decs = {"fav": bi.american_to_decimal(-140), "dog": bi.american_to_decimal(122)}
    fair = bm.devig(decs)
    assert fair["fav"] == pytest.approx(0.56427, abs=1e-4)


def test_devig_names_its_method_and_refuses_others():
    with pytest.raises(ValueError):
        bm.devig({"a": 2.0, "b": 2.0}, method="shin")


def test_ev_and_kelly_hand_checked():
    d = bi.american_to_decimal(-110)
    assert bm.ev_per_unit(0.55, d) == pytest.approx(0.05, abs=1e-6)
    assert bm.kelly_fraction(0.55, d) == pytest.approx(0.055, abs=1e-6)
    assert bm.kelly_fraction(0.45, d) == 0.0        # no bet, never a negative stake


def test_margin_distribution_is_a_distribution():
    dist = bm.margin_distribution(4.5, 4.2)
    assert sum(dist.values()) == pytest.approx(1.0, abs=1e-6)
    assert dist[1] > dist[6]


def test_equal_lambdas_give_a_symmetric_margin():
    dist = bm.margin_distribution(4.4, 4.4)
    for d in (1, 2, 3):
        assert dist[d] == pytest.approx(dist[-d], abs=1e-9)


def test_game_probabilities_complement_and_runline_ordering():
    teams = bm.team_inputs()
    if not teams:
        pytest.skip("leaderboards not built in this checkout")
    orgs = [o for o in teams if o != "_scale"]
    gp = bm.game_probabilities(orgs[0], orgs[1], teams=teams)
    assert gp is not None
    assert gp["p_home"] + gp["p_away"] == pytest.approx(1.0, abs=1e-4)
    # Winning by two is strictly harder than winning at all.
    assert gp["p_home_minus_1_5"] < gp["p_home"]
    assert gp["p_home_plus_1_5"] > gp["p_home"]
    assert 0.15 < gp["p_home"] < 0.85


def test_unknown_club_returns_none_rather_than_a_guess():
    assert bm.expected_runs("ZZZ", "YYY") is None
    assert bm.game_probabilities("ZZZ", "YYY") is None


def test_diff_shrink_pulls_probabilities_toward_even():
    teams = bm.team_inputs()
    if not teams:
        pytest.skip("leaderboards not built in this checkout")
    orgs = [o for o in teams if o != "_scale"]
    strong = max(orgs, key=lambda o: teams[o]["z_off"])
    weak = min(orgs, key=lambda o: teams[o]["z_off"])
    raw = bm.game_probabilities(strong, weak, teams=teams, diff_shrink=1.0)
    shr = bm.game_probabilities(strong, weak, teams=teams, diff_shrink=0.5)
    assert abs(shr["p_home"] - 0.5) < abs(raw["p_home"] - 0.5)


def test_shrink_leaves_the_fair_total_alone():
    """The shrink moves the run DIFFERENTIAL only. If it moved the total it
    would be silently re-pricing a market it was never fitted on."""
    teams = bm.team_inputs()
    if not teams:
        pytest.skip("leaderboards not built in this checkout")
    orgs = [o for o in teams if o != "_scale"]
    a = bm.game_probabilities(orgs[0], orgs[1], teams=teams, diff_shrink=1.0)
    b = bm.game_probabilities(orgs[0], orgs[1], teams=teams, diff_shrink=0.6)
    assert a["fair_total"] == pytest.approx(b["fair_total"], abs=0.02)


def test_home_field_adjustment_helps_the_home_side():
    teams = bm.team_inputs()
    if not teams:
        pytest.skip("leaderboards not built in this checkout")
    orgs = [o for o in teams if o != "_scale"]
    flat = bm.game_probabilities(orgs[0], orgs[1], teams=teams, home_adj=0.0)
    adj = bm.game_probabilities(orgs[0], orgs[1], teams=teams, home_adj=0.25)
    assert adj["p_home"] > flat["p_home"]


def test_literature_priors_are_the_documented_fallback():
    """A checkout with no fitted context still prices games, and says which
    constants it used."""
    assert bm.LITERATURE_COEFFS["source"] == "literature-priors"
    assert 4.0 < bm.LITERATURE_COEFFS["b0"] < 5.0
    assert bm.LITERATURE_COEFFS["b2"] < 0 < bm.LITERATURE_COEFFS["b1"]


def test_backtest_never_reports_itself_validated():
    """Whatever the numbers say, the artifact must not claim validation while
    the features are season-to-date."""
    art = ROOT / "data" / "betting_model_eval.json"
    if not art.exists():
        pytest.skip("backtest has not been run in this checkout")
    d = json.loads(art.read_text(encoding="utf-8"))
    assert d["validated"] is False
    assert d["contaminated"] is True
    assert d["gates_picks"] is False
    assert d["min_edge"] is None


def test_every_graded_block_in_the_artifact_names_its_mode():
    """A reader must never have to remember which column was contaminated.
    Skips on an artifact written before the vintage lane, which the next
    `--backtest` replaces."""
    art = ROOT / "data" / "betting_model_eval.json"
    if not art.exists():
        pytest.skip("backtest has not been run in this checkout")
    d = json.loads(art.read_text(encoding="utf-8"))
    if "modes" not in d:
        pytest.skip("eval artifact predates the vintage lane; re-run --backtest")
    assert d["modes"] == ["contaminated", "vintage"]
    assert d["headline_mode"] in ("contaminated", "vintage")
    for key in ("in_sample", "forward"):
        if d.get(key):
            assert d[key]["mode"] == "contaminated"
            assert d[key]["honest"] is False
    assert d["vintage"]["mode"] == "vintage"
    assert d["vintage"]["honest"] is True


def test_the_artifact_says_which_min_edge_gate_is_closed():
    """`min_edge: null` on its own is not an explanation. The artifact has to
    name the gate, or the next reader invents a threshold."""
    art = ROOT / "data" / "betting_model_eval.json"
    if not art.exists():
        pytest.skip("backtest has not been run in this checkout")
    d = json.loads(art.read_text(encoding="utf-8"))
    if "min_edge_gate" not in d:
        pytest.skip("eval artifact predates the vintage lane; re-run --backtest")
    gate = d["min_edge_gate"]
    assert gate["min_edge"] is None
    assert gate["all_gates_open"] is False
    ids = {g["id"] for g in gate["gates"]}
    assert ids == {"vintage_sample", "out_of_sample_skill", "graded_price_history"}
    assert any(g["open"] is False for g in gate["gates"])


def test_min_edge_cannot_be_set_from_the_contaminated_mode():
    """The gate reads the VINTAGE block only. Handing it a perfect contaminated
    result must still produce no threshold."""
    assert bm.min_edge_gate(None)["min_edge"] is None
    assert bm.min_edge_gate({"n_graded": 0,
                             "skill_vs_home_base": {"t": 99.0,
                                                    "beats_baseline_95": True}}
                            )["min_edge"] is None


# ===========================================================================
# 4. EXPORT
# ===========================================================================
def test_pick_is_absent_without_an_odds_feed():
    pick, why = be.pick_of_the_day([], min_edge=0.03, odds_configured=False)
    assert pick is None and "odds feed" in why


def test_pick_is_absent_without_a_measured_threshold():
    """The threshold is fitted or there is no pick. Inventing one is the
    failure this test exists to prevent."""
    pick, why = be.pick_of_the_day([], min_edge=None, odds_configured=True)
    assert pick is None and "unvalidated" in why


def test_pick_takes_the_highest_ev_above_the_threshold():
    bets = [{
        "game_pk": 1, "start": "x",
        "home": {"org": "NYM"}, "away": {"org": "PHI"},
        "moneyline": [
            {"side": "home", "label": "NYM", "edge": 0.02, "ev_per_unit": 0.9},
            {"side": "away", "label": "PHI", "edge": 0.06, "ev_per_unit": 0.10},
        ],
        "runline": None, "total": {"sides": [
            {"side": "over", "label": "Over 8.5", "edge": 0.05, "ev_per_unit": 0.08}]},
    }]
    pick, _ = be.pick_of_the_day(bets, min_edge=0.04, odds_configured=True)
    assert pick["label"] == "PHI"          # 0.02-edge row is below the threshold
    assert pick["stake_units"] == 1.0


# ---- the two provisional slots --------------------------------------------
def _slot_board():
    """One game carrying four floor-clearing sides across the price range.

    Deliberately shaped so the two selection rules disagree: the +450 longshot
    has the best EV on the board and the worst model probability, which is the
    exact configuration that put a +304 moneyline in the headline slot on
    2026-08-06."""
    return [{
        "game_pk": 1, "start": "2026-08-06T22:05:00Z",
        "home": {"org": "CIN"}, "away": {"org": "ATH"},
        "moneyline": [
            {"side": "away", "label": "ATH", "point": None, "edge": 0.10,
             "odds": 450, "decimal": 5.5, "book": "dk", "model_prob": 0.30,
             "ev_per_unit": 0.65, "kelly_full": 0.16},
            {"side": "home", "label": "CIN", "point": None, "edge": 0.07,
             "odds": -150, "decimal": 1.67, "book": "dk", "model_prob": 0.66,
             "ev_per_unit": 0.10, "kelly_full": 0.12},
        ],
        "runline": [
            {"side": "away", "label": "ATH +1.5", "point": 1.5, "edge": 0.13,
             "odds": -136, "decimal": 1.74, "book": "dk", "model_prob": 0.70,
             "ev_per_unit": 0.21, "kelly_full": 0.28},
        ],
        "total": {"line": 9.0, "sides": [
            {"side": "under", "label": "Under 9.0", "point": 9.0, "edge": 0.02,
             "odds": -110, "decimal": 1.91, "book": "dk", "model_prob": 0.55,
             "ev_per_unit": 0.05, "kelly_full": 0.06},
        ]},
    }]


def test_the_headline_slot_takes_confidence_not_the_longest_price():
    """UPDATED 2026-08-14. The expected label moved from "ATH +1.5" to "CIN"
    because the runline is now excluded from published slots while the
    dispersion correction is unserved (betting_model.market_is_publishable).

    THE TEST'S POINT IS UNCHANGED AND STILL EXERCISED: the +450 ATH row has the
    best EV on this board and the worst probability, and it still does not win.
    The winner is the highest-probability PUBLISHABLE row, 0.66, over a row with
    better EV at 0.30. Selecting on EV is what this slot exists to stop doing
    and this test still fails if it ever does."""
    slots, _, meta = be.provisional_picks(_slot_board(), odds_configured=True)
    potd = slots["pick_of_the_day"]
    assert potd["label"] == "CIN", (
        "the +450 row has the best EV on this board and the worst probability; "
        "selecting on EV is what this slot exists to stop doing")
    assert potd["model_prob"] == 0.66
    assert potd["market"] == "moneyline"
    assert meta["slots"]["pick_of_the_day"]["present"] is True


def test_the_longshot_slot_takes_the_long_price_by_ev():
    slots, _, _ = be.provisional_picks(_slot_board(), odds_configured=True)
    ls = slots["longshot_of_the_day"]
    assert ls["label"] == "ATH" and ls["odds"] == 450
    assert ls["suggested_units"] == 0.5 and ls["stake_units"] == be.STAKE_UNITS


def test_a_price_band_tie_breaks_toward_a_standard_price():
    """Two sides with the same model probability: the one priced nearest -110
    wins, because it is the more ordinary bet and the tiebreak has to be
    deterministic or two identical boards publish two different picks.

    REBUILT 2026-08-14. The tie used to be struck between a moneyline and a
    RUNLINE, and the runline is no longer publishable, so the old fixture had
    no tie left to break. The rule under test is unchanged: on equal model
    probability the price nearest -110 wins. It is now exercised between two
    publishable rows in different games, which is the real slate shape anyway.
    """
    bets = _slot_board()
    bets[0]["moneyline"][1].update({"model_prob": 0.70, "odds": -180,
                                    "decimal": 1.56, "edge": 0.09})
    second = {
        "game_pk": 2, "start": "2026-08-06T23:05:00Z",
        "home": {"org": "SEA"}, "away": {"org": "TEX"},
        "moneyline": [
            {"side": "home", "label": "SEA", "point": None, "edge": 0.09,
             "odds": -115, "decimal": 1.87, "book": "dk", "model_prob": 0.70,
             "ev_per_unit": 0.12, "kelly_full": 0.14},
        ],
        "runline": [], "total": {"line": 8.5, "sides": []},
    }
    bets.append(second)
    slots, _, _ = be.provisional_picks(bets, odds_configured=True)
    potd = slots["pick_of_the_day"]
    assert potd["label"] == "SEA", "-115 is nearer -110 than -180"
    assert potd["model_prob"] == 0.70 and potd["market"] == "moneyline"


def test_an_empty_longshot_slot_names_the_floor_it_could_not_clear():
    """The honest empty state. A second, lower floor invented so this slot
    always has something in it is the single most dishonest number this module
    could publish (docs/diamond-betting.md section 7)."""
    bets = _slot_board()
    bets[0]["moneyline"][0]["edge"] = 0.01        # the only long price fails
    slots, _, meta = be.provisional_picks(bets, odds_configured=True)
    assert slots["longshot_of_the_day"] is None
    sm = meta["slots"]["longshot_of_the_day"]
    assert sm["present"] is False
    assert "+200" in sm["band"]
    assert sm["min_edge"] == meta["min_edge"], "the empty slot keeps the floor"
    assert sm["reason"]


def test_neither_slot_ships_without_an_odds_feed():
    slots, why, meta = be.provisional_picks(_slot_board(), odds_configured=False)
    assert slots == {"pick_of_the_day": None, "longshot_of_the_day": None}
    assert "odds feed" in why
    for sm in meta["slots"].values():
        assert sm["present"] is False and sm["min_edge"] == meta["min_edge"]


def test_a_slot_row_is_the_board_row_plus_context_only():
    """The enumeration reads the board it was handed. Every priced field on the
    published row must be the same object's value, because an independent
    pricing pass is what fused two books into one row and produced a 0.38839
    edge on 2026-08-06.

    UPDATED 2026-08-14: the source row moved from the runline to the moneyline
    the slot now actually selects. The assertion is unchanged and so is its
    point, that every priced field on the published row is the SAME object's
    value rather than a re-priced one.
    """
    bets = _slot_board()
    src = bets[0]["moneyline"][1]                     # CIN, the row now chosen
    slots, _, _ = be.provisional_picks(bets, odds_configured=True)
    potd = slots["pick_of_the_day"]
    assert potd["label"] == src["label"], "fixture drift: the slot moved"
    for f in ("odds", "decimal", "book", "edge", "model_prob", "ev_per_unit",
              "kelly_full", "point"):
        assert potd[f] == src[f], f


def test_market_view_devigs_within_one_book():
    """Mixing books manufactures a fair line with a negative hold. The de-vig
    must come from a single two-sided market."""
    ev = [e for e in bi.parse_events(RAW) if e["home_org"] == "CLE"][0]
    mv = be._market_view(ev, "h2h", ("home", "away"))
    assert mv["fair_book"] in ("draftkings", "fanduel")
    assert sum(mv["fair"].values()) == pytest.approx(1.0, abs=1e-4)
    assert mv["hold_pct"] > 0
    assert mv["devig_method"] == "proportional"
    # best price can come from a DIFFERENT book than the de-vig source
    assert mv["best"]["home"]["price"] == 122


def test_market_view_is_none_when_a_side_is_missing():
    ev = [e for e in bi.parse_events(RAW) if e["home_org"] == "CHC"][0]
    assert be._market_view(ev, "h2h", ("home", "away")) is not None
    ev2 = dict(ev, books={})
    assert be._market_view(ev2, "h2h", ("home", "away")) is None


def test_priced_side_without_a_market_is_a_fair_line():
    row = be._priced_side("home", "NYM", 0.55, None)
    assert row["fair_odds"] is not None
    assert row["edge"] is None and row["ev_per_unit"] is None and row["odds"] is None


def test_prop_row_puts_the_line_on_a_half_point():
    r = be._prop_row("Strikeouts", 5.91)
    assert r["over_line"] == 6.5
    assert 0 < r["p_over"] < 1
    whole = be._prop_row("Strikeouts", 6.0)
    assert whole["over_line"] == 6.5      # never a whole number, which would push


def test_correlation_rules_block_the_moneyline_runline_pair():
    ids = {r["id"]: r for r in be.CORRELATION_RULES}
    assert ids["ml_runline_same_team"]["severity"] == "block"
    assert any(r["severity"] == "warn" for r in be.CORRELATION_RULES)


def test_parlay_context_has_no_featured_parlay_and_says_why():
    pc = be.parlay_context([])
    assert pc["featured_parlay"] is None
    assert "backtest" in pc["featured_reason"]


def test_disclaimer_carries_every_required_element():
    d = be.DISCLAIMER
    joined = " ".join(d.values())
    assert "21+" in joined
    assert "1-800-GAMBLER" in joined
    assert "not legal in all states" in joined
    assert "Informational" in joined or "informational" in joined
    assert "affiliate" in joined
    assert "flat 1 unit" in joined


def test_build_is_offline_safe(tmp_path, monkeypatch):
    """No key, no snapshot cache: the payload still builds and says why it is
    empty instead of raising."""
    monkeypatch.setattr(bi, "CACHE_DIR", tmp_path / "odds")
    monkeypatch.setattr(bi, "STATUS_PATH", tmp_path / "betting_status.json")
    monkeypatch.setattr(bi, "DATA_DIR", tmp_path)
    monkeypatch.delenv(bi.ENV_KEY, raising=False)
    p = be.build(write=False)
    assert p["status"]["odds_feed"] == "not_configured"
    assert p["pick_of_the_day"] is None
    assert p["model"]["validated"] is False
    assert p["status"]["empty_reasons"]


# ---- the shipped payload ---------------------------------------------------
@pytest.fixture(scope="module")
def payload():
    p = ROOT / "data" / "betting.json"
    if not p.exists():
        pytest.skip("data/betting.json has not been built in this checkout")
    return json.loads(p.read_text(encoding="utf-8"))


def test_an_unvalidated_pick_is_always_labelled_provisional(payload):
    """POLICY CHANGED BY OWNER DECISION, 2026-08-06. This test used to assert
    that no pick may ship while the model is unvalidated. The owner decided to
    publish one anyway rather than show an empty module for a season.

    The guard is not removed, it is retargeted, and it is now STRICTER than
    what it replaced: an unvalidated pick may ship, but it may never ship
    UNLABELLED, and none of the honesty the module already had may be traded
    away to get it. A quiet pick with no qualifier is the outcome this file
    exists to prevent, and it would be far worse than the empty slot it
    replaced.

    EXTENDED 2026-08-07, when a second slot was added. The guard now iterates
    EVERY published slot rather than the one it was written for, because a new
    slot added beside an old one is exactly how a pick ships unlabelled: the
    test passes on the slot it names and never looks at the other.

    So while `validated` is false, all of these must hold at once."""
    if payload["model"]["validated"]:
        return                              # a validated build ships plainly

    meta = payload.get("pick_meta") or {}
    assert meta.get("provisional") is True, (
        "an unvalidated build must declare its pick provisional in pick_meta, "
        "which is what every surface keys its labelling off")
    assert meta.get("basis") == "provisional_policy_floor", (
        "the basis must name the floor as a POLICY, not imply a measurement")

    # 1. The reason is always present, pick or no pick.
    assert payload["pick_reason"]

    # 2. The model still reports itself unvalidated. A provisional pick must
    #    not launder the model's status.
    assert payload["model"]["validated"] is False

    # 3. The measured threshold is still null. The floor is not a measurement
    #    and must never be published as one.
    assert payload["model"].get("min_edge") is None

    # 4. Every blocker is still published, unchanged. A provisional pick does
    #    not make any of them untrue.
    blockers = payload.get("pick_blockers") or []
    assert blockers, "the reasons the model is ungated must stay on the page"

    # 5. EVERY slot that shipped a row carries its own label and the floor it
    #    cleared, so a row lifted out of the payload is still self-describing.
    for key in _published_slots(payload):
        pick = payload.get(key)
        if pick is None:
            continue
        assert pick.get("provisional") is True, key
        assert pick.get("min_edge_used") == meta.get("min_edge"), key
        assert pick.get("odds") is not None and pick.get("book"), (
            f"{key}: a pick without a real taken price is not a pick")
        if _is_two_slot_build(payload):
            assert pick.get("slot") == key, (
                f"{key}: a published row must name the slot that chose it, or "
                "the shadow ledger cannot tag it and the sweep cannot condition "
                "on it")

    # 6. Every slot has a meta sub-block, present or not, reading the SAME
    #    floor on the SAME basis. A slot that could quietly carry its own
    #    threshold is a threshold invented to make a pick appear.
    if not _is_two_slot_build(payload):
        return
    for key in PUBLISHED_SLOTS:
        sm = (meta.get("slots") or {}).get(key)
        assert sm, f"{key}: no pick_meta.slots entry, so a reader gets a row " \
                   "with no provisional treatment around it"
        assert sm.get("provisional") is True, key
        assert sm.get("basis") == meta.get("basis"), key
        assert sm.get("min_edge") == meta.get("min_edge"), (
            f"{key}: slot floor {sm.get('min_edge')} differs from the shared "
            f"floor {meta.get('min_edge')}; no slot may lower it")
        assert sm.get("reason"), f"{key}: an empty slot must say why"
        assert sm.get("present") is (payload.get(key) is not None), key
        # The recorded stake is flat everywhere. A variable recorded stake makes
        # the published ROI unauditable from the rows.
        assert sm.get("stake_units") == be.STAKE_UNITS, key


# The slots the payload publishes. Named once so a third slot added later is a
# one-line change here and is then covered by every guard below.
PUBLISHED_SLOTS = ("pick_of_the_day", "longshot_of_the_day")


def _is_two_slot_build(payload) -> bool:
    """Whether this artifact came from the two-slot builder (2026-08-07).

    THE ARTIFACT LAGS THE CODE BY A NIGHT. data/betting.json is written by the
    daily pipeline, not by the test suite, so a checkout can hold yesterday's
    one-slot payload against today's two-slot source. The guards that apply to
    BOTH shapes stay unconditional; the ones that describe the new shape say
    which build they need instead of failing on an artifact that is merely old.
    `pick_meta.slots` is the marker because it is the block the new builder adds
    and the old one cannot have."""
    return bool((payload.get("pick_meta") or {}).get("slots"))


def _published_slots(payload) -> tuple:
    return PUBLISHED_SLOTS if _is_two_slot_build(payload) else ("pick_of_the_day",)


def test_each_slot_stays_inside_its_own_price_band(payload):
    """The two slots exist BECAUSE the price bands are disjoint. Selecting on EV
    alone drove the headline slot to the longest price on the board every time
    (EV is probability times payout and payout dominates), which is how a +304
    moneyline at a 32.9% model probability ended up as the flagship pick on
    2026-08-06. If the bands ever overlap, the same row can fill both slots and
    the page publishes one pick twice."""
    lo, hi = be.POTD_ODDS_BAND
    assert hi < be.LONGSHOT_MIN_ODDS, "the bands must not overlap"
    if not _is_two_slot_build(payload):
        pytest.skip("artifact predates the two-slot builder; re-run betting_export")
    potd = payload.get("pick_of_the_day")
    if potd is not None:
        assert lo <= potd["odds"] <= hi, (
            f"pick of the day is priced {potd['odds']}, outside {lo} to {hi}")
    ls = payload.get("longshot_of_the_day")
    if ls is not None:
        assert ls["odds"] >= be.LONGSHOT_MIN_ODDS, (
            f"longshot is priced {ls['odds']}, shorter than the "
            f"{be.LONGSHOT_MIN_ODDS} floor of its own band")
    if potd is not None and ls is not None:
        assert (potd["game_pk"], potd["market"], potd["side"]) != \
               (ls["game_pk"], ls["market"], ls["side"]), \
               "one side cannot fill both slots"


def test_every_published_slot_is_a_row_off_the_board(payload):
    """NO SLOT MAY RE-PRICE ANYTHING. The 0.38839 edge that shipped on
    2026-08-06 came from shopping each side of a market independently, which
    fused one book's runline with another book's price for the opposite side.
    The structural defence is that a published slot is a row that is already on
    the board: same book, same price, same de-vigged fair probability, same
    edge. If a slot ever computes its own, this test is what catches it."""
    priced = ("side", "label", "point", "book", "odds", "decimal", "model_prob",
              "implied_prob", "market_fair_prob", "edge", "ev_per_unit",
              "kelly_full")
    board = {}
    for b in payload.get("team_bets") or []:
        for market, rows in (("moneyline", b.get("moneyline") or []),
                             ("runline", b.get("runline") or []),
                             ("total", (b.get("total") or {}).get("sides") or [])):
            for r in rows or []:
                board[(b.get("game_pk"), market, r.get("side"), r.get("point"))] = r
    for key in _published_slots(payload):
        pick = payload.get(key)
        if pick is None:
            continue
        src = board.get((pick.get("game_pk"), pick.get("market"),
                         pick.get("side"), pick.get("point")))
        assert src is not None, (
            f"{key} names a side that is not on the published board, so the "
            "reader cannot check the pick against the table it came from")
        for f in priced:
            assert pick.get(f) == src.get(f), (
                f"{key}.{f} is {pick.get(f)!r} on the pick and {src.get(f)!r} on "
                "the board; a slot that re-prices its own row is the defect "
                "that manufactured a 38.8 point edge")


def test_the_longshot_slot_never_lowers_the_floor(payload):
    """The one number this module may never publish. An empty longshot slot on a
    day when nothing long clears the floor is the honest outcome; a second,
    lower floor invented so the slot always has something in it is a threshold
    invented to make a pick appear."""
    meta = payload.get("pick_meta") or {}
    thr = meta.get("min_edge")
    if thr is None:
        pytest.skip("no floor resolved in this build")
    for key in _published_slots(payload):
        pick = payload.get(key)
        if pick is None:
            continue
        assert pick["min_edge_used"] == thr, key
        assert pick["edge"] >= thr, (
            f"{key} cleared {pick['edge']} against a {thr} floor")


def test_the_recorded_stake_is_flat_on_every_slot(payload):
    """Suggested units may differ per slot; the RECORDED stake may not. A
    published ROI over variable recorded stakes cannot be audited from the rows,
    because a reader would have to take it on trust that the sizing was decided
    before the result and not after it."""
    if not _is_two_slot_build(payload):
        pytest.skip("artifact predates the two-slot builder; re-run betting_export")
    for key in PUBLISHED_SLOTS:
        pick = payload.get(key)
        if pick is None:
            continue
        assert pick["stake_units"] == be.STAKE_UNITS, key
        assert pick["suggested_units"] == be.SLOT_DISPLAY_UNITS[key], key
        if pick.get("kelly_full") is not None:
            assert pick["kelly_quarter"] == pytest.approx(
                pick["kelly_full"] / 4.0, abs=1e-5), key


def test_a_runline_or_total_pick_carries_the_underdispersion_caveat(payload):
    """All three markets are eligible for the headline slot, which means two of
    them can be selected on a probability the model is documented to overstate.
    The caveat rides the ROW rather than a page-level limits list, so a client
    that renders the pick and not the list cannot drop it."""
    if not _is_two_slot_build(payload):
        pytest.skip("artifact predates the two-slot builder; re-run betting_export")
    for key in PUBLISHED_SLOTS:
        pick = payload.get(key)
        if pick is None:
            continue
        if pick.get("market") in ("runline", "total"):
            assert pick.get("caveat"), (
                f"{key} is a {pick.get('market')} and carries no caveat about "
                "the Poisson underdispersion that inflates its probability")
        else:
            assert pick.get("caveat") is None


def test_payload_carries_the_legal_block(payload):
    joined = " ".join((payload.get("disclaimer") or {}).values())
    assert "21+" in joined and "1-800-GAMBLER" in joined


def test_payload_probabilities_are_sane(payload):
    for b in payload.get("team_bets") or []:
        m = b["model"]
        assert 0.05 < m["p_home"] < 0.95
        assert m["p_home"] + m["p_away"] == pytest.approx(1.0, abs=1e-3)
        assert 4.0 < m["fair_total"] < 16.0


def test_payload_props_are_labelled_model_only(payload):
    pf = payload["props_fair_lines"]
    assert pf["model_only"] is True
    assert pf.get("no_book_comparison_reason")
    for p in (pf.get("pitchers") or []):
        for pr in p["props"]:
            assert pr.get("fair_line") is not None


def test_preview_slice_exists_for_the_gating_seam():
    p = ROOT / "data" / "betting_preview.json"
    if not p.exists():
        pytest.skip("preview not built in this checkout")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert "disclaimer" in d and "pick_of_the_day" in d
    assert len(d.get("team_bets") or []) <= be.PREVIEW_GAMES
    # THE LABEL TRAVELS WITH THE PICK. The preview omitted `pick_meta` for as
    # long as it existed, so a free-tier reader got a pick with no provisional
    # flag, no floor and no basis beside it.
    if "longshot_of_the_day" not in d:
        pytest.skip("preview predates the two-slot builder; re-run betting_export")
    assert "pick_meta" in d, (
        "the free slice must carry the provisional treatment, not just the pick")


# ===========================================================================
# 5. CLIENT SOURCE GUARDS (assets/betting.js)
# ===========================================================================
def test_client_has_no_em_or_en_dashes():
    """assets/*.js is inside the copy gate's target list."""
    assert "—" not in JS and "–" not in JS


def test_client_carries_a_legal_fallback_for_the_failed_load():
    """The disclaimer normally comes from the payload. If the payload never
    arrives, the notice must still render, so a second copy lives in the JS."""
    assert "LEGAL_FALLBACK" in JS
    fb = JS.split("var LEGAL_FALLBACK = {", 1)[1].split("};", 1)[0]
    assert "21+" in fb
    assert "1-800-GAMBLER" in fb
    assert "not legal in all states" in fb
    assert "affiliate" in fb


def test_client_renders_the_legal_block_before_fetching():
    """renderLegal() runs at the top of boot(), before the fetch that can
    fail. Ordering is the contract; a legal notice behind a network call is
    not a legal notice."""
    body = JS.split("function boot() {", 1)[1].split("function ", 1)[0]
    assert body.index("renderLegal()") < body.index("fetch(")


def test_client_links_nowhere_off_site():
    """No affiliate links, and no bare sportsbook links either: an outbound
    link to a book is where state licensing attaches. The strongest form of
    this test is that the module contains no absolute URL at all."""
    low = JS.lower()
    assert "http://" not in low and "https://" not in low
    for token in ("draftkings.com", "fanduel.com", "betmgm.com", "caesars.com",
                  "bet365", "pointsbet", "aff_id", "btag=", "affiliate.", "?ref="):
        assert token not in low, token


def test_client_blocks_naive_same_game_parlay_math():
    """A warning is not enough. The builder must refuse to print a product for
    correlated legs, in both the board builder and the standalone calculator."""
    assert "blocked" in JS
    assert JS.count("bt-block") >= 3          # style + two refusal paths
    assert "Same-game legs" in JS
    assert "Same-game parlay: no number" in JS


def test_client_calls_the_account_api_it_does_not_own():
    for fn in ("listBets", "addBet", "updateBet"):
        assert fn in JS
    assert "eephus_bets_v1" in JS             # the logged-out fallback


def test_client_calculators_do_not_depend_on_the_payload():
    """Calculators and My Bets must work with no data file. Neither renderer
    may read S.data."""
    for fn in ("function renderCalc()", "function wireCalc()", "function renderMyBets()"):
        body = JS.split(fn, 1)[1]
        body = body.split("\n  function ", 1)[0]
        assert "S.data" not in body, fn


def test_client_uses_theme_tokens_for_colour():
    """House rule: no literal hex outside a var() fallback."""
    css = JS.split("css.textContent = [", 1)[1].split("].join(\"\");", 1)[0]
    for m in re.finditer(r"#[0-9a-fA-F]{3,6}\b", css):
        start = css.rfind("var(", 0, m.start())
        assert start != -1 and css.find(")", start) > m.start(), \
            f"hardcoded colour outside a var() fallback: {css[max(0, m.start()-60):m.end()+5]}"


def test_client_kelly_is_labelled_informational():
    assert "flat" in JS and "1u flat" in JS
    assert "informational" in JS.lower()


def test_shell_page_carries_the_legal_block():
    """The SHELL owns the disclaimer in production (build_site renders a
    `.betting-disclaimer` card above the section nav), and betting.js suppresses
    its own copy when it finds that class. Both halves are pinned here: the
    legal text, which is non-negotiable, and the class name, which is what keeps
    the page from rendering the notice twice."""
    p = ROOT / "betting" / "index.html"
    if not p.exists():
        pytest.skip("/betting/ has not been built in this checkout")
    html = p.read_text(encoding="utf-8")
    assert "21+" in html
    assert "1-800-GAMBLER" in html
    assert ("not legal in every state" in html or "not legal in all states" in html)
    assert "affiliate" in html
    assert "betting-disclaimer" in html, \
        "the shell renamed its disclaimer class; update the selector in betting.js " \
        "renderLegal or the page will render the notice twice"
    assert "assets/betting.js" in html


def test_shell_section_ids_match_the_client():
    """The shell's data-bettingsection ids ARE the contract. A mismatch is a
    page whose tabs do nothing, and nothing else fails to make it visible."""
    p = ROOT / "betting" / "index.html"
    if not p.exists():
        pytest.skip("/betting/ has not been built in this checkout")
    html = p.read_text(encoding="utf-8")
    shell = set(re.findall(r'data-bettingsection="([^"]+)"', html))
    client = set(re.findall(r'var SECTIONS = \[([^\]]+)\]', JS)[0].replace('"', "").split(","))
    client = {c.strip() for c in client}
    assert shell == client, f"shell {sorted(shell)} vs client {sorted(client)}"


def test_client_wires_the_diamond_gate_but_defaults_open():
    """The flag is wired and OFF. With no gating helper on the page at all,
    every reader must get the FULL payload: this preview ships public by owner
    decision.

    PIN UPDATED 2026-08-16 (gating-contract lane): the gate read routes
    through window.EephusDiamond (assets/eephus-diamond.js) now. The block
    this test used to pin read EEPHUS_DIAMOND directly and probed
    EephusAccount.isDiamond() synchronously at boot, before the deferred
    account layer could resolve, so a paying member's first paint would have
    been the preview slice. Both reads are banned here; the refetch seam that
    replaces the sync probe is pinned alongside."""
    assert "EEPHUS_DIAMOND" not in JS, "betting.js reads the raw config again"
    assert "isDiamond" not in JS, (
        "betting.js probes the account layer itself again; membership goes "
        "through EephusDiamond.gated()")
    assert "betting_preview.json" in JS
    body = JS.split("function gated()", 1)[1].split("\n  function ", 1)[0]
    assert "window.EephusDiamond" in body, "gated() no longer routes through the helper"
    # The member-first-paint fix: entitlement resolving to a different payload
    # URL re-runs boot. Both halves must exist or the bug is back.
    assert "onEntitlement" in JS
    assert "dataUrl() !== LOADED_URL" in JS


def test_client_section_router_uses_an_alternation_not_a_map():
    """`#section=constructor` must not resolve off Object.prototype."""
    assert "SECTION_PAT" in JS and "SECTIONS.join" in JS


# ===========================================================================
# 6. CLIENT RENDER SMOKE (py_mini_racer; skipped when unavailable)
# ===========================================================================
# The import is LAZY on purpose. A module-level importorskip would skip this
# whole file on a machine without py_mini_racer, taking the append-only record
# tests with it, and those are the ones that must never quietly stop running.
PRELUDE = """
var __html = {};
function __el(id) {
  return new Proxy(function () { return __el(id); }, {
    get: function (t, k) {
      if (k === 'innerHTML') return __html[id] || '';
      if (k === 'classList') return {add:function(){},remove:function(){},
                                     toggle:function(){},contains:function(){return false;}};
      if (k === 'querySelectorAll') return function () { return []; };
      if (k === 'querySelector') return function () { return null; };
      if (k === 'getAttribute') return function () { return null; };
      if (k === 'setAttribute' || k === 'addEventListener' || k === 'removeEventListener'
          || k === 'appendChild' || k === 'insertBefore' || k === 'focus') return function () {};
      if (k === 'value' || k === 'textContent') return '';
      if (k === 'parentNode' || k === 'firstChild' || k === 'nextSibling') return null;
      return __el(id);
    },
    set: function (t, k, v) { if (k === 'innerHTML') __html[id] = v; return true; },
    apply: function () { return __el(id); }
  });
}
function __btn(sec) {
  var hs = [];
  return { __sec: sec,
    getAttribute: function (n) { return n === 'data-bettingsection' ? sec : null; },
    setAttribute: function () {},
    classList: {add:function(){},remove:function(){},toggle:function(){},
                contains:function(){return false;}},
    addEventListener: function (t, cb) { if (t === 'click') hs.push(cb); },
    click: function () { hs.forEach(function (h) { h({}); }); } };
}
var __btns = ['potd','teams','props','parlays','calculators','record',
              'validation','mybets'].map(__btn);
function __show(sec) {
  for (var i = 0; i < __btns.length; i++) if (__btns[i].__sec === sec) __btns[i].click();
  return __html['betting-app-root'] || '';
}
function FT(v) { return { then: function (cb) { var r = cb(v); return (r && r.then) ? r : FT(r); },
                          catch: function () { return FT(v); } }; }
function FR(e) { return { then: function () { return FR(e); },
                          catch: function (cb) { var r = cb(e); return (r && r.then) ? r : FT(r); } }; }
var __nav = { querySelector: function () { return null; }, appendChild: function () {} };
var location = { href: '', hash: '', origin: 'https://eephus.io', pathname: '/betting/' };
var document = { readyState: 'complete',
  getElementById: function (id) { return __el(id); },
  querySelector: function (sel) { return sel === '.mlbstats-sectionnav' ? __nav : __el('q'); },
  querySelectorAll: function (sel) {
    return sel === '.mlbstats-sectionbtn[data-bettingsection]' ? __btns : [];
  },
  createElement: function () { return __el('c'); },
  addEventListener: function () {},
  head: __el('head'), body: __el('body') };
var EEPHUS_HUB = { teamLogo: function (t) { return '<img alt="' + t + '">'; },
                   links: function () { return FT({ byMlbam: {} }); } };
var window = { location: location, document: document,
               EEPHUS_HUB: EEPHUS_HUB, addEventListener: function () {} };
"""

# THE STUB ROUTES ON URL. betting.js fetches the board and then, lazily, the
# three side artifacts the validation and record tabs read
# (betting_learning.json, betting_model_eval.json, betting_clv.json). A stub
# that answered every url with the board would hand each of those the wrong
# file, and the tests would then assert against a shape production never
# serves. An unrouted url 404s, which is the real behaviour on a checkout
# where the nightly has not written that artifact yet.
FETCH_ROUTER = """
var __ROUTES = %s;
var fetch = function (url) {
  var d = __ROUTES[url];
  if (d === undefined) return FR(new Error('HTTP 404'));
  return FT({ ok: true, json: function () { return FT(d); } });
};
"""
BAD_FETCH = "var fetch = function () { return FR(new Error('HTTP 404')); };\n"

_ROUTE_NAMES = {"main": "/data/betting.json", "preview": "/data/betting_preview.json",
                "learning": "/data/betting_learning.json",
                "evald": "/data/betting_model_eval.json",
                "clv": "/data/betting_clv.json"}


def _fetch_js(**routes) -> str:
    """{name: raw json text} -> the routing stub. Values are RAW JSON text so a
    test can paste an artifact fragment verbatim."""
    body = ",\n".join(f"  {json.dumps(_ROUTE_NAMES.get(k, k))}: {txt}"
                      for k, txt in routes.items())
    return FETCH_ROUTER % ("{\n" + body + "\n}")

SMOKE_PAYLOAD = """{
 "slate_date": "2026-08-04", "n_games": 1,
 "status": {"odds_feed": "not_configured", "odds_note": "odds feed not configured",
            "model": "unvalidated", "empty_reasons": ["odds feed not configured"]},
 "model": {"version": "betting_runs_v1", "validated": false, "stage": "Diamond preview",
           "known_limits": ["Poisson underdisperses run scoring"],
           "coefficients": {"b1": 0.28, "b2": -0.32, "b3": 3.14, "source": "fitted", "n_rows": 3410},
           "league_context": {"n_games": 1705, "lg_rpg": 4.49, "home_win_rate": 0.5232,
                              "extra_inning_home_rate": 0.4875},
           "backtest": {"contamination": "features leak",
                        "in_sample": {"label": "in-sample", "n": 1705, "brier": 0.24164,
                                      "brier_flat_500": 0.25, "brier_home_base": 0.24946,
                                      "accuracy": 0.5672},
                        "note": "no threshold set"},
           "min_edge": null},
 "disclaimer": {"age": "21+ only.", "purpose": "Informational and entertainment purposes only.",
                "legality": "Sports betting is not legal in all states.",
                "help": "If gambling stops being fun, call 1-800-GAMBLER.",
                "affiliates": "eephus.io takes no affiliate money from any sportsbook.",
                "staking": "Every row on the public record is a flat 1 unit."},
 "pick_of_the_day": null,
 "pick_reason": "the model is unvalidated",
 "team_bets": [{"game_pk": 1, "date": "2026-08-04", "venue": "Citizens Bank Park",
   "home": {"org": "PHI", "probable": {"mlbam": 1, "name": "Home Arm"}},
   "away": {"org": "WSN", "probable": null},
   "model": {"p_home": 0.62, "p_away": 0.38, "fair_total": 9.1, "park_index": 1.02,
             "home_prevention": {"starter_plus": 112, "bullpen_plus": 104},
             "away_prevention": {"starter_plus": 95, "bullpen_plus": 99}},
   "moneyline": [{"side": "home", "label": "PHI", "model_prob": 0.62, "fair_odds": -163},
                 {"side": "away", "label": "WSN", "model_prob": 0.38, "fair_odds": 163}],
   "runline": null, "total": {"line": null, "sides": null, "fair_total": 9.1},
   "market": null}],
 "props_fair_lines": {"model_only": true, "no_book_comparison_reason": "free tier",
   "method": {"pitchers": "rate per inning", "hitters": "rate per PA",
              "lineup_assumption": "projected order", "distribution": "Poisson"},
   "pitchers": [{"mlbam": 1, "name": "Home Arm", "org": "PHI", "opp": "WSN",
                 "expected_ip": 5.3,
                 "props": [{"prop": "Strikeouts", "fair_line": 5.9, "over_line": 6.5, "p_over": 0.38},
                           {"prop": "Earned runs", "fair_line": 2.2},
                           {"prop": "Hits allowed", "fair_line": 4.6}]}],
   "hitters": []},
 "parlay_context": {"rules": [{"id": "ml_runline_same_team", "severity": "block",
                               "when": "moneyline and runline on the same team",
                               "why": "one bet with two prices"}],
                    "legs": [], "featured_parlay": null,
                    "featured_reason": "no backtest supports one",
                    "math_note": "independent legs multiply"},
 "record": {"n_rows": 0}, "record_url": "/data/betting_record.json",
 "record_policy": "Append only."
}"""


def _ctx(fetch_js: str):
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    c = MiniRacer()
    c.eval(PRELUDE + fetch_js + JS)
    return c


def _visible_text(html: str) -> str:
    """The rendered copy with tags removed, for assertions about what a READER
    sees rather than about markup.

    Wrapping a term in a glossary span splits the sentence in the source but not
    on screen, so a raw substring check on the html fails on a copy improvement
    that changed nothing a reader can perceive. Assert against this instead
    whenever the contract is about wording."""
    return re.sub(r"<[^>]+>", "", html)


@pytest.fixture(scope="module")
def ok_ctx():
    return _ctx(_fetch_js(main=SMOKE_PAYLOAD))


def test_render_legal_block_is_present_on_a_good_load(ok_ctx):
    legal = ok_ctx.eval("__html['betting-legal'] || ''")
    assert "21+" in legal
    assert "1-800-GAMBLER" in legal
    assert "not legal in all states" in legal


def test_render_legal_block_survives_a_failed_load():
    """The whole point of LEGAL_FALLBACK: a 404 on the payload must not take
    the 21+ notice down with it."""
    c = _ctx(BAD_FETCH)
    legal = c.eval("__html['betting-legal'] || ''")
    assert "21+" in legal and "1-800-GAMBLER" in legal
    root = c.eval("__html['betting-app-root'] || ''")
    assert "failed to load" in root


def test_render_pick_section_says_there_is_no_pick(ok_ctx):
    html = ok_ctx.eval("__show('potd')")
    text = _visible_text(html)
    # The contract is the honest empty state, not one phrasing: the slot has to
    # say plainly that nothing qualified AND name the floor it refused to lower.
    # Publishing a pick by lowering the threshold is the failure this asserts
    # against, so the second clause is the load-bearing one.
    assert "Nothing qualifies today" in text
    # Watch vocabulary (owner decision 2026-08-16): the payload carries no
    # measured threshold, so the noun is "selection", not "pick".
    assert "never lowered to make a selection appear" in text
    assert "0.24164" in html                     # the backtest table rendered
    assert "does not count" in html or "contamination" in html or "leak" in html


def test_render_record_section_says_the_record_is_empty(ok_ctx):
    html = ok_ctx.eval("__show('record')")
    assert "record starts when the selections do" in html
    assert "Append only" in html
    assert "closing line" in html.lower()


def test_render_team_section_shows_fair_prices_without_a_market(ok_ctx):
    html = ok_ctx.eval("__show('teams')")
    assert "WSN" in html and "PHI" in html
    assert "no odds feed" in html.lower()
    assert "probable not announced" in html      # the away side has none


def test_render_props_section_is_labelled_model_only(ok_ctx):
    html = ok_ctx.eval("__show('props')")
    assert "Model fair lines, no book comparison" in html
    assert "Home Arm" in html


def test_render_calculators_work_with_no_payload():
    c = _ctx(BAD_FETCH)
    html = c.eval("__show('calculators')")
    for box in ("Odds converter", "Vig and hold", "Expected value", "Kelly", "Parlay"):
        assert box in html, box
    assert "flat" in html


def test_render_my_bets_works_logged_out():
    c = _ctx(BAD_FETCH)
    html = c.eval("__show('mybets')")
    assert "My bets" in html
    assert "works signed out" in html


def test_render_parlay_section_carries_the_block_rule(ok_ctx):
    html = ok_ctx.eval("__show('parlays')")
    assert "block" in html
    assert "no parlay of the day" in _visible_text(html).lower()


# ===========================================================================
# 7. THE VALIDATION TAB, THE FEED STRIP, AND THE THREE SIDE ARTIFACTS
# ===========================================================================
# The module state is "the close half has never run" and nothing on screen said
# so. These fixtures are cut down from the real artifacts (their key names and
# their nesting are verbatim), because the whole point of this lane is that the
# page READS published numbers rather than carrying its own.

FULL_STATUS = """
 "status": {"odds_feed": "ok", "odds_note": "odds feed configured",
            "odds_captured_at": "2026-08-09T18:22:49+00:00", "odds_kind": "open",
            "model": "unvalidated", "model_mode": "contaminated",
            "n_slate_games": 5, "stale_board": false, "empty_reasons": [],
            "n_events_dropped_in_progress": 2,
            "n_games_unpriced_time_mismatch": 1,
            "feed_health": {"n_slates": 4, "n_slates_with_close": 0,
                            "n_slates_missing_close": 4, "ever_captured_close": false,
                            "hours_since_last_close": null, "window_days": 14,
                            "red": true,
                            "diagnosis": "no close snapshot has ever been captured, CLV is unrecoverable for every slate above, and the close cron is either not installed or is running in the wrong timezone window"}}"""

VALIDATION_BLOCK = """
  "validation": {"available": true, "artifact": "data/betting_model_eval.json",
    "generated_at": "2026-08-09T20:54:18+00:00", "model_version": "betting_runs_v1",
    "validated": false, "headline_mode": "contaminated",
    "mode_meaning": {"contaminated": "features contain the graded games",
                     "vintage": "priced on leaderboards dated strictly before each game"},
    "graded_blocks": [
      {"label": "in-sample", "mode": "contaminated", "honest": false, "n": 1766,
       "brier": 0.24224, "brier_flat_500": 0.25, "brier_home_base": 0.24941,
       "accuracy": 0.5623, "key": "in_sample"},
      {"label": "vintage", "mode": "vintage", "honest": true, "key": "vintage",
       "n": 221, "n_graded": 221, "brier": 0.25045, "brier_flat_500": 0.25,
       "brier_home_base": 0.24885, "accuracy": 0.5068,
       "skill_vs_home_base": {"delta": -0.001603, "sd": 0.0546, "t": -0.435,
                              "beats_baseline_95": false, "n_for_95": null,
                              "baseline": 0.545}}],
    "vintage": {"status": "graded", "n_graded": 221, "n_gradable": 419,
                "n_skipped_no_vintage": 1347, "min_graded_games_for_min_edge": 600,
                "first_graded_date": "2026-07-06", "last_graded_date": "2026-08-09"},
    "coverage": {"n_vintages": 15, "first": "2026-07-05", "last": "2026-08-09",
                 "missing_dates": [], "earliest_gradable_game_date": "2026-07-06"},
    "n_games_completed": 1766,
    "gate": {"all_gates_open": false, "n_open": 0, "n_gates": 3,
      "gates": [
        {"id": "vintage_sample", "need": "600 vintage-graded games", "have": 221,
         "open": false, "why": "600 is a floor and not a pass"},
        {"id": "out_of_sample_skill",
         "need": "paired Brier vs the home-field baseline, t >= 1.645", "have": -0.435,
         "open": false, "why": "sample size is not evidence"},
        {"id": "graded_price_history",
         "need": "settled bets with a taken price, enough that some edge threshold clears an ROI lower bound of zero on at least 100 of them",
         "have": 2, "open": false, "why": "an edge threshold is a claim about EV"}],
      "policy": "min_edge stays null until all three gates are open."}}"""

LEARNING_ARTIFACT = """{
 "latest": {
  "clocks": {
   "vintage_sample": {"id": "vintage_sample", "have": 221, "need": 600, "pct": 0.3683,
     "rate": {"per_day": 6.0286, "window_days": 28, "window_from": "2026-07-13",
              "basis": "counted arrivals over the 28 calendar days since 2026-07-13"},
     "eta": {"days": 63, "short_by": 379, "is_projection": true},
     "may_go_backwards": "yes. A refit can change which games are eligible."},
   "graded_price_history": {"id": "graded_price_history", "need_per_tag": 100,
     "by_tag": {
       "ev_rank": {"have": 1, "need": 100, "ready": false,
                   "rate": {"per_day": 0.0357}, "eta": {"days": 2774}},
       "potd_band": {"have": 1, "need": 100, "ready": false,
                     "rate": {"per_day": 0.0357}, "eta": {"days": 2774}}},
     "why_per_tag": "a pooled ROI measures a mixture nobody bet",
     "cost": "100 settled rows PER TAG"}},
  "calibration": {"n_rows": 30, "n_settled": 24, "n_open": 6, "n_push": 0,
    "n_slate_days": 1, "brier": 0.297511, "log_loss": 0.793144,
    "bins": [{"bin": "0.0-0.1", "n": 0, "pred": null, "actual": null},
             {"bin": "0.1-0.2", "n": 0, "pred": null, "actual": null},
             {"bin": "0.2-0.3", "n": 2, "pred": 0.29467, "actual": 1.0},
             {"bin": "0.3-0.4", "n": 2, "pred": 0.36465, "actual": 0.0},
             {"bin": "0.4-0.5", "n": 8, "pred": 0.461945, "actual": 0.75},
             {"bin": "0.5-0.6", "n": 8, "pred": 0.538055, "actual": 0.25},
             {"bin": "0.6-0.7", "n": 2, "pred": 0.63535, "actual": 1.0},
             {"bin": "0.7-0.8", "n": 2, "pred": 0.70533, "actual": 0.0},
             {"bin": "0.8-0.9", "n": 0, "pred": null, "actual": null},
             {"bin": "0.9-1.0", "n": 0, "pred": null, "actual": null}],
    "not_gate_1": "calibration is NOT the model's first validation gate."},
  "by_market": {
    "moneyline": {"n_rows": 10, "n_settled": 8, "brier": 0.282285,
      "log_loss": 0.758113, "mean_hold_pct": 1.8292,
      "canonical_side": {"n": 4, "mean_model_prob": 0.494993,
        "mean_market_fair_prob": 0.485563, "hit_rate": 0.25, "bias": 0.245,
        "note": "one side per market"}},
    "runline": {"n_rows": 10, "n_settled": 8, "brier": 0.315327,
      "log_loss": 0.8379, "mean_hold_pct": null,
      "canonical_side": {"n": 4, "mean_model_prob": 0.596055,
        "mean_market_fair_prob": 0.533543, "hit_rate": 0.25, "bias": 0.3461,
        "note": "one side per market"}},
    "total": {"n_rows": 10, "n_settled": 8, "brier": 0.294922,
      "log_loss": 0.78342, "mean_hold_pct": 4.7824,
      "canonical_side": {"n": 4, "mean_model_prob": 0.513397,
        "mean_market_fair_prob": 0.496812, "hit_rate": 0.25, "bias": 0.2634,
        "note": "one side per market"}}}}}"""

EVAL_ARTIFACT = """{
 "run_dispersion": {"status": "ran", "split_q": 0.7, "runline_side": "both",
  "n_fit": 1223, "n_eval_games": 552, "passed": true, "alpha": 0.27704,
  "verdict": "indeterminate", "served": false, "served_alpha": null,
  "verdict_note": "`passed` is the pre-registered single split. `verdict` is the ship decision and comes from `sensitivity`.",
  "runline_side_note": "criterion 2's estimand: home is the log loss on home margin >= 2.",
  "criteria": "fit on the fit half of a 70% date split; all four must hold on the held-out half",
  "criteria_v1": "V1 said only margin >= 2 and did not name a side",
  "sensitivity": {"status": "ran", "quantiles": [0.6, 0.7, 0.8],
   "verdict": "indeterminate", "ship": false,
   "rule": "the amended criterion 2 must pass at EVERY split quantile",
   "verdict_by_side": {"home": "fail", "away": "pass", "both": "indeterminate"},
   "grid": [
    {"split_q": 0.6, "split_date": "2026-06-14", "n_eval_games": 721, "alpha": 0.27404,
     "other_three_pass": true,
     "by_side": {"home": {"delta": -0.003628, "t": -0.972, "pass": false},
                 "away": {"delta": 0.015004, "t": 3.86, "pass": true},
                 "both": {"delta": 0.011376, "t": 3.069, "pass": true}},
     "gate_by_side": {"home": false, "away": true, "both": true}},
    {"split_q": 0.7, "split_date": "2026-06-27", "n_eval_games": 552, "alpha": 0.27704,
     "other_three_pass": true,
     "by_side": {"home": {"delta": -0.00328, "t": -0.769, "pass": false},
                 "away": {"delta": 0.015018, "t": 3.367, "pass": true},
                 "both": {"delta": 0.011738, "t": 2.799, "pass": true}},
     "gate_by_side": {"home": false, "away": true, "both": true}},
    {"split_q": 0.8, "split_date": "2026-07-11", "n_eval_games": 362, "alpha": 0.2779,
     "other_three_pass": true,
     "by_side": {"home": {"delta": -0.004701, "t": -0.886, "pass": false},
                 "away": {"delta": 0.011155, "t": 2.034, "pass": true},
                 "both": {"delta": 0.006454, "t": 1.224, "pass": false}},
     "gate_by_side": {"home": false, "away": true, "both": false}}]}}}"""

CLV_EMPTY = """{"n_rows": 3, "n_graded": 0, "n_ungraded": 3,
 "beat_close_rate": null, "avg_clv_pct": null,
 "ungraded_reasons": {"no closing snapshot": 3}, "picks": []}"""

CLV_GRADED = """{"n_rows": 4, "n_graded": 4, "beat_close_rate": 0.75,
 "avg_clv_pct": 2.117, "ungraded_reasons": {"graded": 4},
 "picks": [{"bet_id": "a", "graded": true, "clv_pct": 8.929, "beat_close": true},
           {"bet_id": "b", "graded": true, "clv_pct": -1.2, "beat_close": false},
           {"bet_id": "c", "graded": true, "clv_pct": 0.4, "beat_close": true},
           {"bet_id": "d", "graded": true, "clv_pct": 0.34, "beat_close": true}]}"""

LIVE_PAYLOAD = ("""{
 "slate_date": "2026-08-09", "n_games": 2,""" + FULL_STATUS + """, "model": {
   "version": "betting_runs_v1", "validated": false, "stage": "Diamond preview",
   "min_edge": null,""" + VALIDATION_BLOCK + """},
 "disclaimer": {"age": "21+ only.", "purpose": "Informational only.",
                "legality": "Not legal in all states.",
                "help": "If gambling stops being fun, call 1-800-GAMBLER.",
                "affiliates": "No affiliate money.", "staking": "Flat 1 unit."},
 "pick_of_the_day": {"side": "under", "label": "Under 9.0", "market": "total",
   "model_prob": 0.55837, "odds": 102, "decimal": 2.02, "implied_prob": 0.49505,
   "market_fair_prob": 0.48045, "edge": 0.07792, "ev_per_unit": 0.11191,
   "kelly_full": 0.12539, "kelly_quarter": 0.03135, "book": "lowvig",
   "point": 9.0, "p_push": 0.12508, "ev_per_unit_if_no_push": 0.1279,
   "matchup": "TBR at SEA", "game_pk": 823104, "provisional": true,
   "stake_units": 1.0, "suggested_units": 1.0, "min_edge_used": 0.06,
   "caveat": "this is a runline or total, and the margin model is a Poisson difference"},
 "longshot_of_the_day": null,
 "pick_reason": "nothing at +200 or longer cleared the floor",
 "pick_meta": {"provisional": true, "min_edge": 0.06,
   "basis": "provisional_policy_floor", "n_floor_clearing_sides": 6,
   "slots": {"pick_of_the_day": {"band": "american odds from -199 to +199",
                                 "provisional": true, "min_edge": 0.06},
             "longshot_of_the_day": {"band": "american odds of +200 or longer",
                                     "provisional": true, "min_edge": 0.06,
                                     "reason": "6 side(s) cleared the floor and none of them are priced at american odds of +200 or longer"}}},
 "pick_blockers": [{"id": "min_edge", "reason": "no measured threshold exists",
                    "need": "600 vintage-graded games", "have": 221}],
 "team_bets": [
  {"game_pk": 1, "date": "2026-08-09", "venue": "T-Mobile Park",
   "start": "2026-08-09T20:10:00Z",
   "odds_event_id": "e1", "odds_commence_time": "2026-08-09T20:10:00Z",
   "home": {"org": "SEA", "probable": {"mlbam": 1, "name": "Home Arm"}},
   "away": {"org": "TBR", "probable": {"mlbam": 2, "name": "Away Arm"}},
   "model": {"p_home": 0.55, "p_away": 0.45, "fair_total": 8.4, "park_index": 0.96,
             "home_prevention": {"starter_plus": 110, "bullpen_plus": 103},
             "away_prevention": {"starter_plus": 98, "bullpen_plus": 99}},
   "moneyline": [{"side": "home", "label": "SEA", "model_prob": 0.55, "odds": -124,
                  "book": "draftkings", "market_fair_prob": 0.5446, "edge": 0.0054,
                  "ev_per_unit": 0.0063, "kelly_full": 0.0078, "p_push": null},
                 {"side": "away", "label": "TBR", "model_prob": 0.45, "odds": 116,
                  "book": "draftkings", "market_fair_prob": 0.4554, "edge": -0.0054,
                  "ev_per_unit": -0.043, "kelly_full": 0.0, "p_push": null}],
   "runline": null,
   "total": {"line": 9.0, "p_push": 0.12508,
     "sides": [{"side": "over", "label": "Over 9.0", "model_prob": 0.44163,
                "odds": -113, "book": "betrivers", "market_fair_prob": 0.51955,
                "edge": -0.07792, "ev_per_unit": -0.14657, "kelly_full": 0.0,
                "p_push": 0.12508},
               {"side": "under", "label": "Under 9.0", "model_prob": 0.55837,
                "odds": 102, "book": "lowvig", "market_fair_prob": 0.48045,
                "edge": 0.07792, "ev_per_unit": 0.11191, "kelly_full": 0.12539,
                "p_push": 0.12508}]},
   "market": {"moneyline_hold_pct": 1.653, "total_hold_pct": 4.587,
              "moneyline_fair_book": "pinnacle", "moneyline_hold_range": [1.653, 4.902],
              "moneyline_n_books_on_line": 5, "total_fair_book": "lowvig",
              "total_hold_range": [4.587, 6.1], "total_n_books_on_line": 3,
              "fair_book_rule": "min_hold",
              "n_books_rejected": {"moneyline": {"hold": 1, "stale": 0,
                                                 "consensus": 0, "on_line": 5}},
              "devig_method": "proportional"}},
  {"game_pk": 2, "date": "2026-08-09", "venue": "Yankee Stadium",
   "start": "2026-08-09T23:05:00Z", "odds_event_id": null,
   "home": {"org": "NYY", "probable": null}, "away": {"org": "BOS", "probable": null},
   "model": {"p_home": 0.6, "p_away": 0.4, "fair_total": 9.2, "park_index": 1.04,
             "home_prevention": {"starter_plus": 105, "bullpen_plus": 101},
             "away_prevention": {"starter_plus": 97, "bullpen_plus": 100}},
   "moneyline": [{"side": "home", "label": "NYY", "model_prob": 0.6, "fair_odds": -150},
                 {"side": "away", "label": "BOS", "model_prob": 0.4, "fair_odds": 150}],
   "runline": null, "total": {"line": null, "sides": null, "fair_total": 9.2},
   "market": null}],
 "props_fair_lines": {"model_only": true, "pitchers": [], "hitters": [],
                      "no_book_comparison_reason": "free tier"},
 "parlay_context": {"rules": [], "legs": [], "featured_parlay": null,
                    "featured_reason": "no backtest supports one",
                    "math_note": "independent legs multiply"},
 "record": {"n_rows": 3, "n_settled": 2, "n_open": 1, "won": 1, "lost": 1, "push": 0,
            "net_units": -0.09, "roi_pct": -4.5, "n_clv_graded": 0,
            "beat_close_rate": null, "avg_clv_pct": null, "stake_policy": "flat 1 unit",
            "chain_sha": "9f2c1a77bb0e4d5566aa889900112233445566778899aabbccddeeff00112233",
            "chain_note": "sha256 folded row by row over the record"},
 "record_url": "/data/betting_record.json",
 "clv_url": "/data/betting_clv.json",
 "settlement_url": "/data/betting_settlement.json",
 "record_policy": "Append only.",
 "record_publish": {"written": false, "reason": "2 of 5 blockers are closed"},
 "record_publish_blockers": [
   {"id": "close_snapshot", "open": false, "need": "a close odds snapshot for slate 2026-08-09",
    "have": "0 of 4 slates in the last 14 days have one",
    "reason": "no close snapshot for this slate, so the selection could never be CLV-graded"},
   {"id": "odds_slate", "open": true, "need": "the board priced against its own slate",
    "have": "matched", "reason": "the snapshot belongs to this slate"},
   {"id": "dispersion_gate", "open": true,
    "need": "betting_model's run-dispersion gate to have RUN (not to have passed)",
    "have": "ran", "reason": "the dispersion gate ran on 552 held-out games"},
   {"id": "record_storage", "open": false,
    "need": "the append-only JSONL under .cache/betting/ to be authoritative",
    "have": {"backend": "json", "chain_sha": "9f2c1a77bb0e", "chain_extends": true},
    "reason": "the record is still the git-tracked JSON"},
   {"id": "settlement_current", "open": true, "need": "every stale row settled",
    "have": "0 stale", "reason": "nothing is past the settle window"}]
}""")


@pytest.fixture(scope="module")
def live_ctx():
    """The board wired to all three side artifacts, close never captured."""
    return _ctx(_fetch_js(main=LIVE_PAYLOAD, learning=LEARNING_ARTIFACT,
                          evald=EVAL_ARTIFACT, clv=CLV_EMPTY))


# ---- 7a. the feed-health strip ---------------------------------------------
def test_feed_strip_says_the_close_half_has_never_run(live_ctx):
    """THE SINGLE MOST IMPORTANT NEW PIXEL. Every price on the page comes from
    an OPEN snapshot; the CLOSE snapshot is a separate cron that has never
    fired, and a slate whose close was missed can never be CLV-graded however
    much runs tomorrow. Before this the page said nothing at all."""
    strip = live_ctx.eval("__html['betting-feedhealth'] || ''")
    text = _visible_text(strip)
    assert "NEVER CAPTURED" in text
    assert "2026-08-09" in text                    # the open capture date
    assert "board" in text.lower()
    # the diagnosis names the REPAIR, and it rides as the title
    assert "close cron" in strip


def test_feed_strip_renders_even_when_the_payload_never_arrived():
    """The state it reports is worst exactly when the fetch failed, so it may
    not depend on the fetch succeeding."""
    c = _ctx(BAD_FETCH)
    strip = c.eval("__html['betting-feedhealth'] || ''")
    assert strip, "the strip vanished on a failed load"
    assert "payload not loaded" in _visible_text(strip)


def test_feed_strip_is_above_the_tabs_in_the_shell():
    """It is true on every tab, so it may not live inside the section body."""
    p = ROOT / "betting" / "index.html"
    if not p.exists():
        pytest.skip("/betting/ has not been built in this checkout")
    html = p.read_text(encoding="utf-8")
    assert 'id="betting-feedhealth"' in html
    assert html.index('id="betting-feedhealth"') < html.index("mlbstats-sectionnav")


# ---- 7b. the validation tab ------------------------------------------------
def test_validation_tab_leads_with_the_result_and_does_not_soften_it(live_ctx):
    """The honest backtest LOSES to "always take the home team" and the page
    has to say so in the first block, with the numbers, and with no adjective
    in front of them."""
    html = live_ctx.eval("__show('validation')")
    text = _visible_text(html)
    assert "LOSES to" in text
    assert "0.25045" in text and "0.24885" in text        # brier vs home baseline
    assert "50.68%" in text                                # accuracy
    assert "-0.001603" in text and "-0.435" in text        # paired skill and t
    assert "221" in text
    # the headline is the FIRST thing in the section, not below a fold
    assert html.index("LOSES to") < html.index("Two clocks")


def test_validation_tab_keeps_the_two_clocks_apart(live_ctx):
    """Merging them is what produced the "600 bets" question. One counts games
    the model was graded on; the other counts settled paper bets per tag."""
    html = live_ctx.eval("__show('validation')")
    text = _visible_text(html)
    assert "Clock A" in text and "Clock B" in text
    assert "may never be added together" in text
    assert "221" in text and "600" in text                 # clock A
    assert "ev_rank" in text and "potd_band" in text       # clock B, per tag
    assert "6.03" in text                                  # the MEASURED per-day rate
    assert text.index("Clock A") < text.index("Clock B")


def test_validation_gate_table_carries_a_distance_column(live_ctx):
    html = live_ctx.eval("__show('validation')")
    text = _visible_text(html)
    assert "Distance" in text
    assert "379 games short" in text                       # 600 - 221
    assert "2.080 t short" in text                         # 1.645 - (-0.435)
    assert "98 settled rows short" in text                 # 100 - 2


def test_validation_calibration_panel_has_ten_bins_and_the_gap(live_ctx):
    html = live_ctx.eval("__show('validation')")
    text = _visible_text(html)
    assert "0.0-0.1" in text and "0.9-1.0" in text
    assert "|pred - actual|" in text
    assert "0.7053" in text                                # a bin's predicted value
    assert "0.2947" in text
    for market in ("moneyline", "runline", "total"):
        assert market in text
    assert "NOT the model's first validation gate" in text


def test_validation_dispersion_is_indeterminate_not_a_pass_or_a_fail(live_ctx):
    """`verdict` GOVERNS. The single pre-registered split has passed=true and
    the sweep is indeterminate; rendering the boolean would publish a pass the
    module refused to serve."""
    html = live_ctx.eval("__show('validation')")
    text = _visible_text(html)
    assert "indeterminate" in text
    assert "Not a pass and not a failure" in text
    assert "0.27704" in text                               # the fitted alpha
    # BOTH honest readings: the split that clears and the split that does not
    assert "+0.011738" in text and "+0.006454" in text
    assert "-0.003280" in text                             # the home side, every split
    assert "3.069" in text and "1.224" in text
    assert "none, prices stay Poisson" in text


def test_validation_dispersion_says_the_variance_ratio_is_not_published(live_ctx):
    """FINDING, pinned so it cannot be quietly papered over: betting_model
    measures the variance ratio at fit time (its own header carries 2.3748x on
    the margin and 2.3385x per scoring side) and publishes alpha alone, with
    the ratios only inside a prose note. Deriving 1 + alpha*lambda in the
    client would be the page inventing a number, so it says which file would
    have to carry it."""
    html = live_ctx.eval("__show('validation')")
    assert "not published by data/betting_model_eval.json" in _visible_text(html)


def test_validation_dispersion_renders_the_variance_ratio_the_day_it_ships():
    """The reader is wired for the shaped form the REPORTED EDIT to
    betting_model would publish, so the fix is a producer change with no client
    change behind it."""
    art = EVAL_ARTIFACT.replace(
        '"alpha": 0.27704,',
        '"alpha": 0.27704, "variance_ratio": {"runs_var_over_mean": 2.3385, '
        '"margin_var": 21.3057, "margin_var_skellam_implied": 8.9714, '
        '"margin_ratio": 2.3748, "n_scoring_rows": 3532},', 1)
    c = _ctx(_fetch_js(main=LIVE_PAYLOAD, learning=LEARNING_ARTIFACT, evald=art))
    text = _visible_text(c.eval("__show('validation')"))
    assert "2.3748x on the margin, 2.3385x per scoring side" in text


def test_validation_tab_degrades_when_the_side_artifacts_are_missing():
    """learning / eval / clv are lazily fetched and may 404 on a checkout whose
    nightly has not run. Every panel then names the file it is missing."""
    c = _ctx(_fetch_js(main=LIVE_PAYLOAD))
    html = c.eval("__show('validation')")
    text = _visible_text(html)
    assert "/data/betting_learning.json" in text
    assert "/data/betting_model_eval.json" in text
    # the payload half still renders: the headline result comes from the board
    assert "LOSES to" in text


# ---- 7c. the pick tab ------------------------------------------------------
def test_pick_says_how_often_a_whole_number_total_pushes(live_ctx):
    html = live_ctx.eval("__show('potd')")
    text = _visible_text(html)
    assert "9 is a push 12.5% of the time" in text
    assert "returns the stake" in text


def test_pick_carries_the_dispersion_line_in_the_caveat_slot(live_ctx):
    html = live_ctx.eval("__show('potd')")
    text = _visible_text(html)
    assert "Margin model" in text
    assert "indeterminate" in text
    assert "NOT served" in text


def test_client_renders_the_provisional_badge_and_styles_it(live_ctx):
    """The client half of the labelling contract, unpinned until now: provBadge
    could be gutted and the suite stayed green, and betting.js records at its
    own provBadge comment that exactly that regression already shipped once.
    Two badges on the pick tab, one per slot header, and the .bt-prov class the
    badge carries has a rule in the injected sheet rather than being a dead
    styling hook.

    MUTATION PROOF: making provBadge return "" kills the count and the visible
    "provisional"; deleting the .bt-prov line from the css array kills the
    source assert; flipping provBadge's guard so `provisional === false` still
    badges kills the negative case at the end."""
    html = live_ctx.eval("__show('potd')")
    assert html.count("bt-prov") == 2            # the pick slot and the empty slot
    assert "provisional" in _visible_text(html)
    assert '".bt-prov{' in JS                    # the class has a rule, not just markup
    payload = LIVE_PAYLOAD.replace('"provisional": true', '"provisional": false')
    c = _ctx(_fetch_js(main=payload, learning=LEARNING_ARTIFACT, evald=EVAL_ARTIFACT))
    assert "bt-prov" not in c.eval("__show('potd')")


def test_an_empty_board_renders_the_census_not_an_outage():
    """N sides priced, M cleared the floor, none in the band. Without it an
    empty pick tab reads as a broken feed."""
    payload = LIVE_PAYLOAD.replace('"pick_of_the_day": {"side": "under"',
                                   '"pick_of_the_day": null, "unused_pick": {"side": "under"')
    c = _ctx(_fetch_js(main=payload, learning=LEARNING_ARTIFACT, evald=EVAL_ARTIFACT))
    text = _visible_text(c.eval("__show('potd')"))
    assert "Census." in text
    assert "4 sides priced" in text          # the served rows with a price and a book
    assert "6 cleared the 6.0% floor" in text
    assert "american odds from -199 to +199" in text
    assert "not a failure to load one" in text


# ---- 7d. the team board ----------------------------------------------------
def test_team_board_publishes_the_devig_book_and_its_spread(live_ctx):
    html = live_ctx.eval("__show('teams')")
    text = _visible_text(html)
    assert "pinnacle" in text and "lowvig" in text          # the de-vig book per market
    assert "1.65%" in text                                  # its hold
    assert "1.65% to 4.90%" in text                         # the spread across books
    assert "Books on line" in text
    assert "1 hold" in text                                 # refused for hold


def test_an_unpriced_game_stays_on_the_board_and_says_why(live_ctx):
    """An absent row reads as an absent game. Both filters that can strip a
    game's prices are named, with the counts from status."""
    html = live_ctx.eval("__show('teams')")
    text = _visible_text(html)
    assert "NYY" in text                                    # the game is still there
    assert "unpriced: no pre-game odds event within 3h of first pitch" in text
    assert "already under way" in text
    assert "3 odds events did not price a game" in text     # 2 in progress + 1 mismatch


def test_a_blocked_build_suppresses_the_best_value_badge_and_says_why(live_ctx):
    """pick_meta.blocked used to be read by pickCensus alone, and the server
    fills pick_meta.min_edge BEFORE its block branch, so a hard-stopped build
    with both slots nulled still badged the team board green off the surviving
    floor and its head note asserted agreement with picks that did not exist.

    MUTATION PROOF: deleting the `if (m.blocked) return null` branch from
    pickFloor re-badges the board and kills the bt-bestval and head-note
    asserts; deleting the blocked note from renderTeam kills the reason
    assert. The unblocked control line pins that the suppression asserts are
    not passing vacuously."""
    assert "bt-bestval" in live_ctx.eval("__show('teams')")   # control: it does badge
    payload = LIVE_PAYLOAD.replace(
        '"pick_of_the_day": {"side": "under"',
        '"pick_of_the_day": null, "unused_pick": {"side": "under"')
    payload = payload.replace(
        '"pick_meta": {"provisional": true, "min_edge": 0.06,',
        '"pick_meta": {"provisional": true, "blocked": true, '
        '"blocked_reason": "no odds api key at build time, the events are a cached snapshot", '
        '"min_edge": 0.06,')
    c = _ctx(_fetch_js(main=payload, learning=LEARNING_ARTIFACT, evald=EVAL_ARTIFACT))
    html = c.eval("__show('teams')")
    text = _visible_text(html)
    assert "bt-bestval" not in html
    assert "no odds api key at build time" in text            # the reason, above the board
    assert "No best value badges today" in text
    assert "never disagree about the bar" not in text         # the head note goes down too


def test_the_team_board_discloses_the_push_on_a_whole_number_total(live_ctx):
    """The push disclosure lived on the two pick cards alone while the board
    rendered the same push-discounted EV and push-conditional model probability
    with zero occurrences of "push" on the whole tab. The board's total block
    now says the line pushes, that the Model column is conditional on the bet
    resolving, and that the EV/u column carries the (1 - p_push) discount.

    MUTATION PROOF: dropping the fourth argument from gameCard's total
    marketBlock call, or the pushText block inside marketBlock, removes the
    sentence and kills the first two asserts; the count pins it to the one
    whole-number posted line on the fixture board (game 2 has none). The potd
    asserts pin the render-order fix: pushLine said "the expected value above"
    while pickCard renders the EV chip below it; reverting "below" to "above"
    kills them."""
    text = _visible_text(live_ctx.eval("__show('teams')"))
    assert "9 is a push 12.5% of the time" in text
    assert "the Model column is the chance to cash given the bet resolves" in text
    assert "the EV/u column is that conditional value scaled by the 87.5%" in text
    assert text.count("is a push") == 1
    potd = _visible_text(live_ctx.eval("__show('potd')"))
    assert "the expected value above" not in potd
    assert "the expected value below is that conditional value" in potd


# ---- 7e. the record tab ----------------------------------------------------
def test_record_tab_is_three_panels_and_prints_the_chain(live_ctx):
    html = live_ctx.eval("__show('record')")
    text = _visible_text(html)
    assert "The public record" in text
    assert "Closing line value" in text
    assert "What gates the first published row" in text
    assert "9f2c1a77bb0e" in text                           # the chain hash
    assert "Joined across three files on bet_id" in text
    assert "recompute the chain by folding sha256" in text
    # the validation accounting MOVED to its own tab
    assert "Clock A" not in text


def test_record_clv_panel_renders_the_sidecar_reasons_when_nothing_graded(live_ctx):
    html = live_ctx.eval("__show('record')")
    text = _visible_text(html)
    assert "no closing snapshot" in text
    assert "unrecoverable after the fact" in text


def test_record_clv_panel_draws_a_decile_histogram_from_theme_tokens():
    c = _ctx(_fetch_js(main=LIVE_PAYLOAD, learning=LEARNING_ARTIFACT,
                       evald=EVAL_ARTIFACT, clv=CLV_GRADED))
    html = c.eval("__show('record')")
    assert "bt-bar" in html                                 # bars, no chart library
    assert "4 graded selections in ten" in _visible_text(html)
    assert "+8.93%" in _visible_text(html)


def test_record_publish_blockers_are_listed_whether_or_not_they_pass(live_ctx):
    html = live_ctx.eval("__show('record')")
    text = _visible_text(html)
    for bid in ("close_snapshot", "odds_slate", "dispersion_gate", "record_storage",
                "settlement_current"):
        assert bid in text, bid
    assert "3 of 5 are open" in text


# ---- 7f. the preview slice (D16) -------------------------------------------
def test_client_renders_a_redacted_pick_without_inventing_a_selection():
    """The preview keeps the whole trust surface and withholds the SELECTION.
    A client handed a redacted slot renders the market and the floor, and no
    side, no price and no book."""
    redacted = """{"slot": "pick_of_the_day",
      "slot_label": "Model Watch: largest disagreement", "slot_frame": "watch",
      "market": "total", "provisional": true, "min_edge_used": 0.06,
      "redacted": true,
      "redaction_note": "Preview slice: the market and the floor this pick cleared, not the selection."}"""
    payload = LIVE_PAYLOAD.replace(
        '"pick_of_the_day": {"side": "under"',
        '"pick_of_the_day": ' + redacted + ', "unused_pick": {"side": "under"')
    c = _ctx(_fetch_js(main=payload, learning=LEARNING_ARTIFACT, evald=EVAL_ARTIFACT))
    text = _visible_text(c.eval("__show('potd')"))
    assert "Selection withheld" in text
    assert "total" in text and "6.0%" in text
    assert "Under 9.0" not in text
    assert "lowvig" not in text
    assert "Census." not in text            # a redacted slot is a pick, not an empty one


# ---- 7g. the charts package (A6, 2026-08-16) -------------------------------
# Inline SVG, no chart library, tokens only through classes, and every chart
# has an absence branch that names WHY it is not drawable. The fixtures below
# extend the section 7 artifacts with the two series the charts read (the
# learning history and shadow_by_tag), because the committed fixtures predate
# both.
def _learning_with_series() -> str:
    art = json.loads(LEARNING_ARTIFACT)
    art["history"] = [
        {"date": "2026-08-13", "calibration_brier": 0.2921,
         "calibration_n_settled": 120},
        {"date": "2026-08-14", "calibration_brier": 0.2812,
         "calibration_n_settled": 180},
        {"date": "2026-08-15", "calibration_brier": None},
        {"date": "2026-08-16", "calibration_brier": 0.2736,
         "calibration_n_settled": 310},
    ]
    art["latest"]["shadow_by_tag"] = {
        "board_all": {"n_rows": 83, "n_settled": 73, "won": 33, "lost": 39,
                      "push": 1, "net_units": -8.555, "roi": -0.1188},
        "potd_band": {"n_rows": 7, "n_settled": 6, "won": 4, "lost": 2,
                      "push": 0, "net_units": 1.2, "roi": 0.2},
        "longshot": {"n_rows": 2, "n_settled": 0, "won": 0, "lost": 0,
                     "push": 0, "net_units": None, "roi": None},
    }
    return json.dumps(art)


EVAL_WITH_BENCHMARKS = json.dumps({
    **json.loads(EVAL_ARTIFACT),
    "benchmarks": {
        "claim_rule": "never claim an unmeasured tier",
        "status": "ran",
        "window": {"split_date": "2026-07-28", "n": 269,
                   "first_date": "2026-07-28", "last_date": "2026-08-16"},
        "tiers": {
            "model_vintage": {"n": 269, "brier": 0.25053,
                              "source": "the vintage block's own eval window"},
            "home_constant": {"n": 269, "brier": 0.24875,
                              "source": "home win rate as a constant"},
            "elo_literature": {"n": 269, "brier": 0.24556,
                               "source": "literature-prior Elo"},
            "market_open_devig": {"n": 122, "brier": 0.24254,
                                  "subsample_note": "122 of 269 games have a "
                                                    "cached open capture",
                                  "same_games": {"model": 0.25356,
                                                 "home_constant": 0.24671,
                                                 "elo_literature": 0.24347},
                                  "source": "de-vig of the open snapshot"},
            "market_close_devig": {"n": 0, "brier": None,
                                   "status": "no close capture matched a "
                                             "graded eval game; this tier is "
                                             "unmeasured and claims nothing"},
        }}})


@pytest.fixture(scope="module")
def charts_ctx():
    return _ctx(_fetch_js(main=LIVE_PAYLOAD, learning=_learning_with_series(),
                          evald=EVAL_WITH_BENCHMARKS, clv=CLV_EMPTY))


def test_reliability_curve_draws_one_dot_per_populated_bin(charts_ctx):
    """Six of the fixture's ten bins carry pred and actual, so the curve is
    six dots, a connecting path, and the dashed diagonal. The bin-n row and
    the table stay beside it: the picture never replaces the numbers.

    MUTATION PROOF: nulling one bin's actual in the fixture drops the dot
    count to five and fails the count; deleting the bt-svg-ref line from
    reliabilitySVG fails the diagonal assert."""
    html = charts_ctx.eval("__show('validation')")
    i = html.index("bt-svg-rel")
    rel = html[i:html.index("</svg>", i)]
    assert rel.count("<circle") == 6
    assert 'class="bt-svg-ref"' in rel
    assert "<path" in rel
    text = _visible_text(html)
    assert "Bin n, low bin to high: 0, 0, 2, 2, 8, 8, 2, 2, 0, 0" in text
    # per-market bins do not exist in the artifact, and the panel says so
    assert "per-market summaries without per-market bins" in text


def test_brier_trend_draws_the_history_against_the_coin_line(charts_ctx):
    """Three usable nightly rows (the null one is dropped, not drawn as zero)
    against the dashed 0.25 reference. First render of this series anywhere.

    MUTATION PROOF: corrupting the fixture series (nulling a second row)
    drops the dot count; dropping the goldref line kills the coin assert."""
    html = charts_ctx.eval("__show('validation')")
    i = html.index("bt-svg-trend")
    tr = html[i:html.index("</svg>", i)]
    assert tr.count("<circle") == 3
    assert 'class="bt-svg-goldref"' in tr
    assert "coin 0.25" in tr
    assert "2026-08-13" in tr and "2026-08-16" in tr


def test_clocks_panel_carries_three_svg_metered_clocks(charts_ctx):
    """Clock A, Clock B (a bar per tag) and Clock C, all on SVG progress
    bars. Clock C has no clock in the learning artifact, so its rate cell
    NAMES that instead of inventing a rate."""
    html = charts_ctx.eval("__show('validation')")
    text = _visible_text(html)
    assert "Clock C" in text
    assert "gradable games (the pool)" in text
    assert "419" in text                       # the payload's n_gradable
    assert "carries no gradable_games clock" in text
    assert html.count("bt-svg-meter") >= 4     # A + two tag rows + C
    assert "Not a gate" in text


def test_benchmark_ladder_order_matches_the_fixture_and_model_shows_last(charts_ctx):
    """The full-window tiers sort by measured Brier, best first, so the order
    is elo, home constant, model, and the model row is LAST and labelled. The
    subsample renders apart inside its same-games block and the unmeasured
    tier renders its status sentence, never a number.

    MUTATION PROOF: sorting descending, or pinning the model first, breaks
    the index ordering; dropping the unmeasured branch kills its sentence."""
    html = charts_ctx.eval("__show('validation')")
    text = _visible_text(html)
    i_elo = text.index("elo_literature")
    i_home = text.index("home_constant")
    i_model = text.index("model_vintage")
    assert i_elo < i_home < i_model
    assert "The model is last on this window" in text
    assert "0.25053" in text and "0.24556" in text
    assert "market_open_devig, a subsample (122 of 269 games)" in text
    assert "no close capture matched a graded eval game" in text


def test_benchmark_ladder_absent_state_names_the_missing_block(live_ctx):
    """The section 7 eval fixture has no benchmarks block, and the ladder
    names that rather than rendering an empty table."""
    text = _visible_text(live_ctx.eval("__show('validation')"))
    assert "Benchmark ladder: not measured yet" in text
    assert "carries no benchmarks block" in text


def test_roi_by_tag_bars_are_labelled_paper_bets_not_the_record(charts_ctx):
    """Horizontal bars off shadow_by_tag, polarity red/green, tag name and
    number as text on every bar, on the Record tab under a heading that says
    what they are NOT. The tag with no settled rows draws no bar."""
    html = charts_ctx.eval("__show('record')")
    text = _visible_text(html)
    assert "ROI by selection rule (paper bets, not the record)" in text
    i = html.index("bt-svg-roi")
    roi = html[i:html.index("</svg>", i)]
    assert roi.count("bt-svg-neg") == 1        # board_all, -11.9%
    assert roi.count("bt-svg-pos") == 1        # potd_band, +20%
    assert "board_all" in roi and "potd_band" in roi
    assert "longshot" not in roi               # roi null, nothing to draw
    assert "never pooled" in text


def test_roi_by_tag_absent_state_names_the_reason(live_ctx):
    """The committed learning fixture has no shadow_by_tag: the panel says
    which block is missing instead of drawing an empty axis.

    MUTATION PROOF: dropping the absence branch (returning the bare panel)
    kills this and the chartAbsent phrasing assert."""
    text = _visible_text(live_ctx.eval("__show('record')"))
    assert "ROI by tag: not measured yet" in text
    assert "carries no shadow_by_tag block" in text


def test_every_chart_absence_branch_survives_a_missing_artifact():
    """No learning artifact at all: reliability, trend and ROI all name the
    file they are missing, and the page still renders."""
    c = _ctx(_fetch_js(main=LIVE_PAYLOAD))
    vtext = _visible_text(c.eval("__show('validation')"))
    assert vtext.count("/data/betting_learning.json") >= 2
    rtext = _visible_text(c.eval("__show('record')"))
    assert "ROI by tag: not measured yet" in rtext


def test_clv_absent_state_names_the_crontab_and_the_selfcheck(live_ctx):
    """The A6 item 6 check: the empty CLV panel names the CONCRETE repair,
    both the crontab install and the selfcheck command, not just the
    symptom."""
    text = _visible_text(live_ctx.eval("__show('record')"))
    assert "deploy/betting-crontab.example" in text
    assert "crontab -e" in text
    assert "python tools/betting_close_job.py --selfcheck" in text
    assert "NEVER RUN" in text


def test_chart_colors_are_theme_tokens_only():
    """Every SVG chart class in the injected sheet resolves through a CSS
    custom property; no literal hex is the FIRST value of any chart rule."""
    css = JS.split("var css = document.createElement", 1)[1]
    for cls in ("bt-svg-line", "bt-svg-dot", "bt-svg-ref", "bt-svg-goldref",
                "bt-svg-grid", "bt-svg-axis", "bt-svg-track", "bt-svg-fill",
                "bt-svg-pos", "bt-svg-neg"):
        i = css.index("." + cls + "{")
        rule = css[i:css.index("}", i)]
        for decl in ("fill:", "stroke:"):
            j = rule.find(decl)
            if j >= 0:
                val = rule[j + len(decl):].split(";", 1)[0]
                assert val.startswith("var(") or val in ("none",), (cls, val)


# ===========================================================================
# 8. D13: THE CLIENT MATH IS PINNED TO THE PYTHON MATH
# ===========================================================================
# assets/betting.js reimplements six primitives betting_model and
# betting_ingest already own. Nothing connected the two, so a fix on one side
# was invisible on the other. THREE checks, in increasing strength:
#
#   1. the fixture is REGENERATED from Python and must match,
#   2. the JS is EXECUTED on those vectors in py_mini_racer,
#   3. the JS source expression is pinned to a string, so a rewrite that
#      happens to agree on 60 vectors still has to be deliberate.
#
# NOTE ON (2): the lane brief said there is no JS runtime here. There is.
# py_mini_racer is in requirements.txt and this file already drives the whole
# client through it. Executing the vectors is strictly stronger than diffing
# source, so both ship.
VECTORS_PATH = ROOT / "test_fixtures" / "odds_math_vectors.json"
VECTORS = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))

JS_MATH_FNS = ("amToDec", "decToAm", "decToImplied", "devig", "evPerUnit", "kelly")


def _js_fn_source(name: str) -> str:
    """One function, verbatim, as it appears in assets/betting.js."""
    i = JS.index("function " + name + "(")
    j = JS.index("\n  function ", i + 1)
    return JS[i:j].rstrip()


def _py_expect(fn: str, args: list):
    """The PYTHON side of each primitive. This is the definition the fixture is
    generated from, so a change in betting_model has to land here to stay
    green."""
    if fn == "amToDec":
        return bi.american_to_decimal(args[0])
    if fn == "decToAm":
        return bi.decimal_to_american(args[0])
    if fn == "decToImplied":
        return 1.0 / args[0]
    if fn == "devig":
        fair = bm.devig({str(i): d for i, d in enumerate(args[0])})
        return [fair[str(i)] for i in range(len(args[0]))]
    if fn == "evPerUnit":
        p, dec, pp = args[0], args[1], args[2]
        ev = bm.ev_per_unit(p, dec)
        return (1.0 - pp) * ev if pp else ev
    if fn == "kelly":
        return bm.kelly_fraction(args[0], args[1])
    raise AssertionError(f"no python side for {fn}")


def test_odds_vectors_regenerate_from_python():
    """The fixture is a RECORD of the Python side, not an independent claim. If
    betting_model's math moves this fails first, and the fixture is then
    rewritten deliberately rather than the two drifting apart."""
    rows = VECTORS["vectors"]
    assert len(rows) == 60 and VECTORS["n_vectors"] == 60
    assert {r["fn"] for r in rows} == set(JS_MATH_FNS)
    for r in rows:
        assert r["expect"] == _py_expect(r["fn"], r["args"]), r["id"]


def test_odds_vectors_cover_a_whole_number_total():
    """evPerUnit now carries the push adjustment the export applies at the call
    site. Without a whole-number vector the third argument is untested and the
    two implementations can differ by 1 / (1 - p_push) unnoticed."""
    push = [r for r in VECTORS["vectors"] if r["fn"] == "evPerUnit" and r["args"][2]]
    assert len(push) >= 3
    for r in push:
        p, dec, pp = r["args"]
        assert abs(r["expect"] - (1.0 - pp) * bm.ev_per_unit(p, dec)) < 1e-15
        assert abs(r["expect"]) < abs(bm.ev_per_unit(p, dec))     # the push discounts it


def test_client_odds_math_matches_python_on_every_vector():
    """THE STRONG CHECK: the shipped JS, executed."""
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    c = MiniRacer()
    c.eval("\n".join(_js_fn_source(n) for n in JS_MATH_FNS))
    for r in VECTORS["vectors"]:
        got = c.call(r["fn"], *r["args"])
        exp = r["expect"]
        if isinstance(exp, list):
            assert got is not None and len(got) == len(exp), r["id"]
            for a, b in zip(got, exp):
                assert abs(a - b) <= 1e-15, r["id"]
        else:
            assert got is not None and abs(got - exp) <= 1e-15, (r["id"], got, exp)


def test_client_floors_american_prices_below_100_where_python_does_not():
    """A DELIBERATE DIVERGENCE, pinned. American odds run +100 / -100 outward
    and there is nothing in the gap, so the client refuses a half-typed "-1"
    rather than converting it to decimal 101 and printing "+10000". Python has
    no such floor because it is never handed a typed string."""
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    c = MiniRacer()
    c.eval(_js_fn_source("amToDec"))
    for g in VECTORS["js_only_guards"]:
        assert c.call("amToDec", *g["args"]) is None, g["args"]
        assert bi.american_to_decimal(g["args"][0]) == g["py"]


def test_known_rounding_divergence_at_an_exact_half_price():
    """FINDING, pinned rather than hidden: JS Math.round is round-half-UP and
    Python round() is round-half-to-EVEN, so decimal 2.045 converts to +105 in
    the browser and +104 in the export. The two disagree by one american point
    on any price whose (decimal - 1) * 100 lands exactly on a half. The
    reachable surface is the odds converter, where a reader types the decimal.
    The fix belongs in betting_ingest.decimal_to_american, which this lane does
    not own; when it lands this test fails and the fixture is regenerated."""
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    c = MiniRacer()
    c.eval(_js_fn_source("decToAm"))
    for d in VECTORS["known_divergences"]:
        assert c.call("decToAm", *d["args"]) == d["js"], d["args"]
        assert bi.decimal_to_american(d["args"][0]) == d["py"], d["args"]
    assert any(not d["same"] for d in VECTORS["known_divergences"]), \
        "the divergence was fixed; regenerate test_fixtures/odds_math_vectors.json"


# The pinned source. Whitespace-normalized so reindenting is not a failure, but
# every operator, every guard and every constant is here: a rewrite that agrees
# on 60 vectors still has to be a deliberate edit to this string.
PINNED_JS_MATH = {
    "amToDec": "function amToDec(a) { var n = Number(a); if (!isFinite(n) || "
               "Math.abs(n) < 100) return null; return 1 + (n > 0 ? n / 100 : "
               "100 / Math.abs(n)); }",
    "decToAm": "function decToAm(d) { var n = Number(d); if (!isFinite(n) || n <= 1) "
               "return null; return n >= 2 ? Math.round((n - 1) * 100) : "
               "Math.round(-100 / (n - 1)); }",
    "decToImplied": "function decToImplied(d) { var n = Number(d); return (!isFinite(n) "
                    "|| n <= 1) ? null : 1 / n; }",
    "devig": "function devig(decimals) { var raw = [], sum = 0, i; for (i = 0; i < "
             "decimals.length; i++) { var q = decToImplied(decimals[i]); if (q == null) "
             "return null; raw.push(q); sum += q; } if (!sum) return null; return "
             "raw.map(function (q) { return q / sum; }); }",
    "evPerUnit": "function evPerUnit(p, dec, pPush) { var pp = (pPush > 0 && pPush < 1) "
                 "? Number(pPush) : 0; return (1 - pp) * (p * (dec - 1) - (1 - p)); }",
    "kelly": "function kelly(p, dec) { var b = dec - 1; if (b <= 0) return 0; return "
             "Math.max(0, (p * b - (1 - p)) / b); }",
}


def _norm_js(src: str) -> str:
    """Comments stripped, whitespace collapsed. The expression survives; the
    formatting does not."""
    src = re.sub(r"^\s*//.*$", "", src, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", src).strip()


def test_client_odds_math_source_is_pinned():
    for name, pinned in PINNED_JS_MATH.items():
        assert _norm_js(_js_fn_source(name)) == _norm_js(pinned), name


def test_client_ev_carries_the_push_factor_the_export_applies():
    """The one place the two implementations were structurally different: the
    export scales EV by (1 - p_push) at the CALL SITE and the client had no
    third argument at all, so a whole-number total recomputed in the browser
    came out 1 / (1 - p_push) too generous."""
    assert "pPush" in _js_fn_source("evPerUnit")
    assert "p_push" in JS                      # the row key the page reads


# ===========================================================================
# 9. THE <= 640px TIER
# ===========================================================================
def test_mobile_tier_is_additive_and_does_not_move_the_720_rule():
    """tools/verify_site.py fails any route that scrolls sideways at 390px. The
    720px rule is left exactly where it was so nothing between 641 and 720
    shifts, and the phone tier is a second block below it."""
    css = JS.split("css.textContent = [", 1)[1].split('].join("");', 1)[0]
    assert "@media (max-width:720px){.bt-markets{grid-template-columns:minmax(0,1fr)}" in css
    assert "@media (max-width:640px){" in css
    assert css.index("max-width:720px") < css.index("max-width:640px")
    for rule in (".bt-clocks{grid-template-columns:minmax(0,1fr)}",
                 ".bt-fh-seg{white-space:normal}",
                 ".bt-kv{grid-template-columns:minmax(0,1fr)}"):
        assert rule in css, rule
    # mybets, calculators, props and parlays keep their layout
    tier = css.split("@media (max-width:640px){", 1)[1]
    for untouched in (".bt-calc", ".bt-betform", ".bt-legpick", ".bt-field"):
        assert untouched not in tier, untouched


def test_gate_why_collapses_into_a_details_rather_than_being_deleted(live_ctx):
    """The `why` paragraph is the widest cell in the gate table. It folds into
    a disclosure on a phone; it must not be display:none'd, which would delete
    the reason instead of folding it."""
    html = live_ctx.eval("__show('validation')")
    assert "bt-gate-more" in html
    assert "why this gate exists" in html
    assert "600 is a floor and not a pass" in html          # still in the DOM
    css = JS.split("css.textContent = [", 1)[1].split('].join("");', 1)[0]
    assert ".bt-gate-why{display:none}" not in css


def test_every_new_table_scrolls_inside_its_own_box():
    """A wide table must scroll itself, not the document. Every table this lane
    added carries the .bt-scroll wrapper the 720px rule already relies on."""
    n_tables = JS.count('<table class="bt-table')
    n_wraps = JS.count('bt-scroll mlbstats-scroll')
    assert n_wraps >= n_tables, (n_wraps, n_tables)


# ===========================================================================
# 10. MODEL WATCH (owner decision 2026-08-16, docs/diamond-betting.md 7a)
# ===========================================================================
# While the three gates are closed, user-facing language and payload prose
# retire the word "pick"; the STRUCTURAL keys keep their names because the
# shadow ledger's slot continuity and the record funnel depend on them. The
# self-lift is coded: a payload that says the gates opened brings the pick
# vocabulary back with no client edit. These tests drive the shipped client
# against both payload shapes.

#: The four key names the ruling exempts. They are plumbing, not prose, and
#: they are removed from the rendered text before the guard runs so an
#: incidental echo of a key name cannot pass for vocabulary.
WATCH_STRUCTURAL_KEYS = ("pick_of_the_day", "longshot_of_the_day",
                         "pick_meta", "pick_blockers", "pick_reason")

_POTD_TAG_RECORD = {"available": True, "tag": "potd_band", "n_settled": 6,
                    "won": 2, "lost": 4, "push": 0, "net_units": -2.876,
                    "roi": -0.4793, "small_n": True, "sweep_floor": 100,
                    "source": "betting_shadow.summary() by_tag"}
_LONG_TAG_RECORD = {"available": True, "tag": "longshot", "n_settled": 1,
                    "won": 0, "lost": 1, "push": 0, "net_units": -1.0,
                    "roi": -1.0, "small_n": True, "sweep_floor": 100,
                    "source": "betting_shadow.summary() by_tag"}


def _watch_payload() -> str:
    """LIVE_PAYLOAD as the 2026-08-16 server writes it: watch frame, watch
    slot labels, the slot's own tag record inline, and the potd row pointing
    at its own game so the worked de-vig has board rows to price from."""
    d = json.loads(LIVE_PAYLOAD)
    p = d["pick_of_the_day"]
    p["game_pk"] = 1                       # TBR at SEA is game 1 on this board
    p["slot"] = "pick_of_the_day"
    p["slot_label"] = "Model Watch: largest disagreement"
    p["slot_frame"] = "watch"
    p["tag_record"] = dict(_POTD_TAG_RECORD)
    m = d["pick_meta"]
    m["frame"] = "watch"
    for key, lab, rec in (
            ("pick_of_the_day", "Model Watch: largest disagreement",
             _POTD_TAG_RECORD),
            ("longshot_of_the_day", "Model Watch: long-price disagreement",
             _LONG_TAG_RECORD)):
        s = m["slots"][key]
        s["slot_label"] = lab
        s["slot_frame"] = "watch"
        s["tag_record"] = dict(rec)
    return json.dumps(d)


def _open_payload() -> str:
    """The same board after the gates open: frame pick, measured floor, pick
    labels. This is the self-lift shape."""
    d = json.loads(_watch_payload())
    p = d["pick_of_the_day"]
    p["slot_label"] = "Pick of the Day"
    p["slot_frame"] = "pick"
    p["provisional"] = False
    m = d["pick_meta"]
    m["frame"] = "pick"
    m["provisional"] = False
    m["basis"] = "measured"
    m["min_edge"] = 0.031
    for key in m["slots"]:
        m["slots"][key]["provisional"] = False
        m["slots"][key]["slot_frame"] = "pick"
        m["slots"][key]["slot_label"] = (
            "Pick of the Day" if key == "pick_of_the_day"
            else "Longshot Value of the Day")
    return json.dumps(d)


@pytest.fixture(scope="module")
def watch_ctx():
    return _ctx(_fetch_js(main=_watch_payload(), learning=LEARNING_ARTIFACT,
                          evald=EVAL_ARTIFACT, clv=CLV_EMPTY))


@pytest.fixture(scope="module")
def open_ctx():
    return _ctx(_fetch_js(main=_open_payload(), learning=LEARNING_ARTIFACT,
                          evald=EVAL_ARTIFACT, clv=CLV_EMPTY))


def _depick(text: str) -> str:
    for tok in WATCH_STRUCTURAL_KEYS:
        text = text.replace(tok, "")
    return text


def test_watch_language_guard_no_pick_noun_anywhere_visible(watch_ctx):
    """THE LANGUAGE GUARD. Gates closed, every tab the payload reaches, the
    banner, and the feed strip: no user-visible "pick"/"Pick" outside the
    structural-key allowlist.

    MUTATION PROOF: hardcoding any label or sentence back to the pick noun
    (SLOTS titles, noPickHeadline, the record panels, the blocker sentence)
    puts the word back in one of these renders and fails the tab that shows
    it. The allowlist is exact key names, so a prose sentence containing
    "pick" cannot hide behind it."""
    for tab in ("potd", "teams", "record", "validation", "parlays", "props",
                "calculators", "mybets"):
        text = _visible_text(watch_ctx.eval(f"__show({tab!r})"))
        assert "pick" not in _depick(text).lower(), (tab, text[:400])
    for host in ("betting-feedhealth", "betting-banner", "betting-legal"):
        text = _visible_text(watch_ctx.eval(f"__html[{host!r}] || ''"))
        assert "pick" not in _depick(text).lower(), (host, text[:400])


def test_a_pre_frame_payload_defaults_to_watch(live_ctx):
    """A payload built before 2026-08-16 carries no frame and no slot_label.
    Every such payload was a gates-closed payload, so the client's fallback
    must be the WATCH vocabulary, not the pick one. MUTATION PROOF: hardcoding
    slotTitle's fallback to the pick title is invisible on the served-label
    fixtures and fails exactly here."""
    text = _visible_text(live_ctx.eval("__show('potd')"))
    assert "Model Watch: largest disagreement" in text
    assert "Pick of the Day" not in text


def test_watch_card_carries_the_watch_frame_and_labels(watch_ctx):
    html = watch_ctx.eval("__show('potd')")
    text = _visible_text(html)
    assert "Model Watch: largest disagreement" in text
    assert "Model Watch: long-price disagreement" in text
    assert "not a recommendation" in text
    # the provisional labelling contract is INTACT under the reframe
    assert html.count("bt-prov") == 2
    assert "provisional" in text


def test_watch_card_shows_its_own_tag_record(watch_ctx):
    """The slot's own selection rule's settled record, inline and small-n
    labelled. MUTATION PROOF: dropping the tagRecordLine block from pickCard
    removes all three fragments; dropping only the small-n label kills the
    third."""
    text = _visible_text(watch_ctx.eval("__show('potd')"))
    assert "2-4" in text
    assert "-47.9%" in text
    assert "small sample: 6 settled" in text
    assert "potd_band" in text


def test_watch_card_devig_example_matches_the_row(watch_ctx):
    """The collapsible worked de-vig, computed from the served board rows.
    Expected values are recomputed HERE from the same fixture rows with the
    same arithmetic (raw implied = 1/decimal, overround = sum - 1, fair =
    raw/sum, edge = model - fair), so the client cannot drift from the math
    without this failing.

    MUTATION PROOF: breaking any step of the client arithmetic (dropping the
    proportional division, summing decimals instead of implieds, using the
    raw instead of the fair probability in the edge) changes at least one
    printed percentage below."""
    over_dec = 1 + 100 / 113          # -113
    under_dec = 2.02                  # +102
    q_over, q_under = 1 / over_dec, 1 / under_dec
    s = q_over + q_under
    fair_under = q_under / s
    model = 0.55837
    text = _visible_text(watch_ctx.eval("__show('potd')"))
    assert f"{q_over * 100:.1f}%" in text                     # 53.1% raw over
    assert f"{q_under * 100:.1f}%" in text                    # 49.5% raw under
    assert f"{s * 100:.1f}%" in text                          # 102.6% sum
    assert f"{(s - 1) * 100:.1f}%" in text                    # 2.6% overround
    assert f"{fair_under * 100:.1f}%" in text                 # 48.3% fair
    assert f"+{(model - fair_under) * 100:.1f} points" in text  # +7.6 points
    # the served fair (48.0%, one book's two-sided quote) differs from the
    # best-price fair above, and the example says which one the edge uses
    assert "ONE book" in text


def test_gates_open_payload_restores_the_pick_vocabulary(open_ctx):
    """THE SELF-LIFT. A payload whose pick_meta says frame "pick" brings the
    vocabulary back everywhere, and the pick rendering returns without the
    watch additions. MUTATION PROOF: pinning watchMode() to true (or the
    labels to the watch strings) fails the title assert; leaving the watch
    additions unconditional fails the two negative asserts."""
    html = open_ctx.eval("__show('potd')")
    text = _visible_text(html)
    assert "Pick of the Day" in text
    assert "Longshot Value of the Day" in text
    assert "Model Watch" not in text
    assert "bt-tagrec" not in html
    assert "bt-devigex" not in html
    record = _visible_text(open_ctx.eval("__show('record')"))
    assert "A pick is written to the public record" in record
    assert "How a pick gets graded" in record


def test_the_potd_tab_label_follows_the_served_frame():
    """The tab button copy follows slot_label's frame. The harness's stub
    buttons swallow textContent, so the contract is pinned at the source: the
    label is derived from watchMode() inside syncTabs, and the gates-closed
    default in SECTION_LABELS is the watch word."""
    assert 'var potdLabel = watchMode() ? "Model Watch" : "Pick of the Day";' in JS
    assert 'potd: "Model Watch"' in JS


def test_export_payload_prose_is_pick_free_while_gates_are_closed():
    """The server half of the guard: provisional_picks, pick_blockers and the
    record label, rendered as JSON, carry the pick noun ONLY inside the
    structural key names. MUTATION PROOF: reverting any of the de-picked
    sentences in betting_export (the policy line, the shared-floor note, the
    record label, the min_edge blocker) puts the word into this blob."""
    board = [{
        "game_pk": 1, "start": "2026-08-16T23:05:00Z",
        "away": {"org": "AAA"}, "home": {"org": "BBB"},
        "moneyline": [{"side": "home", "label": "BBB", "edge": 0.20,
                       "odds": -110, "book": "b", "model_prob": 0.60,
                       "market_fair_prob": 0.40, "kelly_full": 0.2,
                       "ev_per_unit": 0.1}],
        "runline": None, "total": {"sides": None},
    }]
    slots, reason, meta = be.provisional_picks(board, odds_configured=True,
                                               evald=None)
    blob = json.dumps({
        "slots": slots, "reason": reason, "meta": meta,
        "blockers": be.pick_blockers(min_edge=None, odds_configured=True),
        "label": be.provisional_record_label(None, min_edge=0.06,
                                             provisional=True),
    })
    assert "pick" not in _depick(blob).lower(), blob
    assert meta["frame"] == "watch"
    assert slots["pick_of_the_day"]["slot_label"] == "Model Watch: largest disagreement"
    assert slots["pick_of_the_day"]["slot_frame"] == "watch"


def test_export_self_lift_restores_the_pick_labels():
    """Gates open in the eval artifact -> resolve_min_edge flips provisional
    off -> the labels and the frame return, with no other change."""
    board = [{
        "game_pk": 1, "start": "2026-08-16T23:05:00Z",
        "away": {"org": "AAA"}, "home": {"org": "BBB"},
        "moneyline": [{"side": "home", "label": "BBB", "edge": 0.20,
                       "odds": -110, "book": "b", "model_prob": 0.60,
                       "market_fair_prob": 0.40, "kelly_full": 0.2,
                       "ev_per_unit": 0.1}],
        "runline": None, "total": {"sides": None},
    }]
    evald = {"min_edge_gate": {"min_edge": 0.031, "all_gates_open": True},
             "validated": True, "min_edge": 0.031}
    slots, _, meta = be.provisional_picks(board, odds_configured=True,
                                          evald=evald)
    assert meta["frame"] == "pick"
    p = slots["pick_of_the_day"]
    assert p["slot_label"] == "Pick of the Day"
    assert p["slot_frame"] == "pick"
    assert p["provisional"] is False
    assert p["min_edge_used"] == 0.031


def test_export_slots_carry_their_own_tag_record():
    """Both slot metas carry tag_record with the tag names the shadow ledger
    actually writes, read from betting_shadow.summary() by tag and never
    pooled. MUTATION PROOF: dropping the tag_record key from _slot_meta, or
    pooling the tags into one record, breaks the per-slot tag names."""
    board = []
    _, _, meta = be.provisional_picks(board, odds_configured=True, evald=None)
    potd = meta["slots"]["pick_of_the_day"]["tag_record"]
    lng = meta["slots"]["longshot_of_the_day"]["tag_record"]
    assert potd is not None and lng is not None
    if potd.get("available"):
        assert potd["tag"] == "potd_band"
        assert lng["tag"] == "longshot"
        assert "n_settled" in potd and "roi" in potd and "net_units" in potd
        assert isinstance(potd["small_n"], bool)
