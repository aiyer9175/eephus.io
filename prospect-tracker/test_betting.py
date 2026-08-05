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


def test_payload_never_ships_a_pick_while_unvalidated(payload):
    if payload["model"]["validated"]:
        return                              # a future validated build may ship one
    assert payload["pick_of_the_day"] is None
    assert payload["pick_reason"]


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
    """The flag is wired and OFF. With no diamond-config.js at all, and with
    gating false, every reader must get the FULL payload: this preview ships
    public by owner decision."""
    assert "EEPHUS_DIAMOND" in JS
    assert "betting_preview.json" in JS
    body = JS.split("function gated()", 1)[1].split("\n  function ", 1)[0]
    assert "gatingOn()" in body and "isDiamond()" in body
    cfg = JS.split("function diamondCfg()", 1)[1].split("\n  function ", 1)[0]
    assert "window.EEPHUS_DIAMOND || {}" in cfg      # absent config reads as open


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
var __btns = ['potd','teams','props','parlays','calculators','record','mybets'].map(__btn);
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

OK_FETCH = "var fetch = function () { return FT({ ok: true, json: function () { return FT(%s); } }); };\n"
BAD_FETCH = "var fetch = function () { return FR(new Error('HTTP 404')); };\n"

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
                "staking": "Every pick on the public record is a flat 1 unit."},
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


@pytest.fixture(scope="module")
def ok_ctx():
    return _ctx(OK_FETCH % SMOKE_PAYLOAD)


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
    assert "No pick today" in html
    assert "0.24164" in html                     # the backtest table rendered
    assert "does not count" in html or "contamination" in html or "leak" in html


def test_render_record_section_says_the_record_is_empty(ok_ctx):
    html = ok_ctx.eval("__show('record')")
    assert "record starts when the picks do" in html
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
    assert "no parlay of the day" in html.lower()
