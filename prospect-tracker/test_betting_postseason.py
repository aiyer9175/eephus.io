# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""/betting/ prices postseason games (owner decision 2026-10-01, INT-A1).

Task BET_POSTSEASON_PRICING, docs/diamond-betting.md section 8a. The owner
answered (c) "Yes, full": postseason games are priced, may fill both slots and
may post public record rows, although the pricer has never been fitted or
graded on a postseason game. The orchestrator's binding conditions, each
pinned below:

  1. every postseason card, slot candidate, shadow row and public record row
     carries the label "never graded on a postseason game" and a `game_type`
     field (F, D, L, W);
  2. the public record's postseason rows are their own sub-ledger, the
     regular-season headline excludes them and says so, and the paper ledger
     and data/betting_subledger.json gain the same split;
  3. (the registry row and the glossary; pinned in the last two tests);
  4. the per-slot record guard and the total-lean bar apply unchanged to
     postseason rows;
  5. nothing else in the pricer changes: postseason games enter through the
     game scope only, and no gate's frame takes a postseason row.

Every write here goes to tmp_path or to an in-memory fake.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import betting_export as be
import betting_model as bm
import betting_settle as bset
import betting_shadow as bs
import fantasy_schedule as fsched
from tools import betting_calibration as bc

ROOT = Path(__file__).resolve().parent
DAY = "2026-10-03"
LABEL = "never graded on a postseason game"

TEAMS = {"_scale": {"prev_mu": 100.0, "prev_sd": 10.0},
         "KCR": {"z_off": 0.10, "offense_plus": 102.0, "bullpen_plus": 101.0,
                 "rotation_plus": 100.0, "sp_ip_share": 0.60},
         "CHC": {"z_off": 0.05, "offense_plus": 101.0, "bullpen_plus": 100.0,
                 "rotation_plus": 100.0, "sp_ip_share": 0.60}}


def _sched_row(pk, *, game_type=None, date=DAY, home="KCR", away="CHC",
               start="2026-10-03T20:00:00Z"):
    row = {"game_pk": pk, "date": date, "datetime": start, "status": "Preview",
           "double_header": False, "venue": {"id": 1, "name": "Park"},
           "home": {"org": home, "team": home, "probable": None},
           "away": {"org": away, "team": away, "probable": None}}
    if game_type:
        row["game_type"] = game_type
        row["series"] = "AL Division Series"
    return row


def _side(side, label, *, odds, edge, prob, **extra):
    dec = (1 + odds / 100.0) if odds > 0 else (1 + 100.0 / -odds)
    return {"side": side, "label": label, "odds": odds, "book": "lowvig",
            "book_title": "LowVig.ag", "decimal": round(dec, 4), "edge": edge,
            "model_prob": prob, "market_fair_prob": round(prob - edge, 5),
            "ev_per_unit": round(prob * dec - 1, 4), **extra}


def _card(pk, *, game_type=None, ml=None, total=None, home="KCR", away="CHC"):
    card = {"game_pk": pk, "date": DAY, "start": "2026-10-03T20:00:00Z",
            "status": "Preview", "double_header": False,
            "home": {"org": home}, "away": {"org": away},
            "moneyline": ml or [], "runline": None,
            "total": total or {"line": None, "sides": None, "p_push": None}}
    if game_type:
        card.update(bset.postseason_fields(game_type))
        card["series"] = "AL Division Series"
    return card


def _post_card(pk=900001, game_type="D"):
    return _card(pk, game_type=game_type, ml=[
        _side("home", "KCR", odds=-120, edge=0.10, prob=0.645),
        _side("away", "CHC", odds=110, edge=-0.10, prob=0.355)])


def _reg_card(pk=800001):
    return _card(pk, ml=[
        _side("home", "KCR", odds=-130, edge=0.08, prob=0.645),
        _side("away", "CHC", odds=115, edge=-0.08, prob=0.355)])


# ---------------------------------------------------------------------------
# the vocabulary
# ---------------------------------------------------------------------------
def test_the_vocabulary_is_one_definition():
    assert bset.POSTSEASON_GAME_TYPES == ("F", "D", "L", "W")
    assert bset.POSTSEASON_LABEL == LABEL
    for gt in ("F", "D", "L", "W"):
        assert bset.postseason_fields(gt) == {"game_type": gt, "postseason_label": LABEL}
        assert bset.is_postseason({"game_type": gt})
    for gt in ("R", None, "", "S", "E"):
        assert bset.postseason_fields(gt) == {}
    # A row with no game_type is a regular-season row: every row written
    # before 2026-10-01 came off a regular-season-only board.
    assert bset.game_type_of({}) == "R" and not bset.is_postseason({})


# ---------------------------------------------------------------------------
# the game scope (condition 5)
# ---------------------------------------------------------------------------
def test_fetch_probables_stamps_a_postseason_row_and_leaves_a_regular_row_alone(monkeypatch):
    raw = {"dates": [{"date": DAY, "games": [
        {"gamePk": 1, "gameType": "D", "seriesDescription": "AL Division Series",
         "officialDate": DAY, "gameDate": "2026-10-03T20:00:00Z",
         "status": {"abstractGameState": "Preview"}, "teams": {}},
        {"gamePk": 2, "gameType": "R", "officialDate": DAY,
         "gameDate": "2026-10-03T23:00:00Z",
         "status": {"abstractGameState": "Preview"}, "teams": {}}]}]}
    monkeypatch.setattr(fsched, "_cached_schedule", lambda *a, **k: raw)
    rows = {r["game_pk"]: r for r in fsched.fetch_probables(DAY, DAY)}
    assert rows[1]["game_type"] == "D" and rows[1]["series"] == "AL Division Series"
    assert "game_type" not in rows[2] and "series" not in rows[2]
    seen = {}
    monkeypatch.setattr(fsched, "_cached_schedule",
                        lambda s, e, gt, uc: seen.setdefault("gt", gt) and raw)
    fsched.fetch_postseason(DAY, DAY)
    assert seen["gt"] == "F,D,L,W"


def test_the_scope_joins_the_postseason_list_and_the_flag_removes_it(monkeypatch):
    fan = {"schedule": {"games": [_sched_row(10)],
                        "postseason_games": [_sched_row(11, game_type="D"),
                                             # a list row that is not what it says
                                             _sched_row(12, game_type="R")]}}
    monkeypatch.setattr(be, "_load", lambda name: fan if name == "fantasy.json" else None)
    monkeypatch.setattr(be, "BET_POSTSEASON_SCOPE", True)
    assert [g["game_pk"] for g in be._schedule_rows(fan)] == [10, 11]
    assert {g["game_pk"] for g in be.slate_games(DAY)} == {10, 11}
    monkeypatch.setattr(be, "BET_POSTSEASON_SCOPE", False)
    assert [g["game_pk"] for g in be.slate_games(DAY)] == [10]


def test_resolve_slate_reads_the_same_scope(monkeypatch):
    from datetime import datetime, timezone
    fan = {"schedule": {"games": [],
                        "postseason_games": [_sched_row(11, game_type="L")]}}
    monkeypatch.setattr(be, "_load", lambda name: fan if name == "fantasy.json" else None)
    monkeypatch.setattr(be, "BET_POSTSEASON_SCOPE", True)
    day, games = be.resolve_slate(now=datetime(2026, 10, 3, 12, tzinfo=timezone.utc),
                                  priceable={})
    assert day == DAY and [g["game_pk"] for g in games] == [11]
    monkeypatch.setattr(be, "BET_POSTSEASON_SCOPE", False)
    day, games = be.resolve_slate(now=datetime(2026, 10, 3, 12, tzinfo=timezone.utc),
                                  priceable={})
    assert day is None and games == []


# ---------------------------------------------------------------------------
# condition 1: the label on every row kind
# ---------------------------------------------------------------------------
def test_a_postseason_card_carries_the_label_and_a_regular_card_does_not():
    rows = be.team_bets([_sched_row(11, game_type="W"), _sched_row(10)], [],
                        teams=TEAMS, parks={"KCR": 1.0}, starters={})
    by = {r["game_pk"]: r for r in rows}
    assert by[11]["game_type"] == "W" and by[11]["postseason_label"] == LABEL
    assert by[11]["series"]
    for k in ("game_type", "postseason_label", "series"):
        assert k not in by[10], k
    # The pricer is the same pricer: one matchup, one probability, either way.
    assert by[11]["model"] == by[10]["model"]


def test_slot_candidates_and_published_slots_carry_the_label():
    cands = be._floor_clearing_sides([_post_card(), _reg_card()], 0.06,
                                     ledger_closed=frozenset())
    post = [c for c in cands if c["game_pk"] == 900001]
    reg = [c for c in cands if c["game_pk"] == 800001]
    assert post and all(c["game_type"] == "D" and c["postseason_label"] == LABEL
                        for c in post)
    assert reg and all("game_type" not in c and "postseason_label" not in c for c in reg)
    slots, _why, _meta = be.provisional_picks([_post_card()], odds_priceable=True, evald={})
    potd = slots["pick_of_the_day"]
    assert potd and potd["game_type"] == "D" and potd["postseason_label"] == LABEL


def test_a_props_candidate_on_a_postseason_game_carries_the_label():
    prop = {"market": "props_batter_hits", "game_pk": 900001, "edge": 0.09,
            "odds": 120, "book": "lowvig", "label": "Over 0.5", "side": "over"}
    cands = be._floor_clearing_sides([_post_card()], 0.06, ledger_closed=frozenset(),
                                     extra_rows=[prop])
    got = [c for c in cands if c.get("market") == "props_batter_hits"]
    assert got and got[0]["game_type"] == "D" and got[0]["postseason_label"] == LABEL


def test_a_record_row_carries_the_label_and_a_regular_row_keeps_its_shape():
    slot = {**_post_card()["moneyline"][0], "market": "moneyline", "game_pk": 900001,
            "matchup": "CHC at KCR", "slot": "pick_of_the_day", "min_edge_used": 0.06,
            "provisional": True, **bset.postseason_fields("D")}
    row = be.record_row(slot, slate_date=DAY, evald={})
    assert row["game_type"] == "D" and row["postseason_label"] == LABEL
    reg = {k: v for k, v in slot.items() if k not in ("game_type", "postseason_label")}
    row_r = be.record_row(reg, slate_date=DAY, evald={})
    assert "game_type" not in row_r and "postseason_label" not in row_r
    assert set(row) - set(row_r) == {"game_type", "postseason_label"}


def _payload(cards, **kw):
    return {"slate_date": DAY, "status": {"odds_feed": "ok"},
            "model": {"pricing_basis": "constructed"}, "team_bets": cards,
            "pick_of_the_day": None, "longshot_of_the_day": None, **kw}


def test_a_shadow_row_carries_the_label(tmp_path):
    led = tmp_path / "shadow.json"
    out = bs.record_slate(_payload([_post_card(), _reg_card()]), min_edge=0.06,
                          path=led, include_board_all=True)
    assert out["written"] == 2
    rows = {r["game_pk"]: r for r in bs.load(led)}
    assert rows[900001]["game_type"] == "D" and rows[900001]["postseason_label"] == LABEL
    assert "game_type" not in rows[800001] and "postseason_label" not in rows[800001]


def test_a_calibration_side_names_its_game_type(tmp_path):
    led = tmp_path / "cal.jsonl"
    bc.record_slate(_payload([_post_card(), _reg_card()]), path=led)
    rows = bc.rows(path=led)
    assert {r["game_type"] for r in rows if r["game_pk"] == 900001} == {"D"}
    assert all("game_type" not in r for r in rows if r["game_pk"] == 800001)


# ---------------------------------------------------------------------------
# condition 2: the sub-ledger, and the regular-season pin
# ---------------------------------------------------------------------------
def _rec(pk, result, *, gt=None, odds=-110):
    r = {"bet_id": f"b{pk}", "slate_date": DAY, "game_pk": pk, "slot": "pick_of_the_day",
         "odds_at_post": odds, "stake_units": 1.0, "posted_at": "2026-10-03T12:00:00+00:00"}
    r.update(bset.postseason_fields(gt))
    return r, {"settled": True, "result": result}


HEADLINE = ("n_rows", "n_settled", "n_open", "won", "lost", "push", "net_units",
            "roi_pct", "n_clv_graded", "beat_close_rate", "avg_clv_pct")


def test_regular_season_record_counts_are_unchanged_by_postseason_rows():
    reg = [_rec(1, "won"), _rec(2, "lost"), _rec(3, "won", odds=120)]
    post = [_rec(4, "won", gt="D", odds=250), _rec(5, "won", gt="L"), _rec(6, "lost", gt="W")]
    rows_r = [r for r, _ in reg]
    rows_all = rows_r + [r for r, _ in post]
    sett = {r["bet_id"]: {"bet_id": r["bet_id"], **s} for r, s in reg + post}
    only = be.record_summary(rows_r, clv={}, settlement=sett)
    both = be.record_summary(rows_all, clv={}, settlement=sett)
    assert {k: only[k] for k in HEADLINE} == {k: both[k] for k in HEADLINE}
    assert both["n_rows"] == 3 and both["won"] == 2 and both["lost"] == 1
    assert both["n_rows_all"] == 6 and both["n_postseason_rows"] == 3
    assert both["scope"] == "regular_season" and "excluded" in both["scope_note"]
    ps = both["postseason"]
    assert ps["n_rows"] == 3 and ps["won"] == 2 and ps["lost"] == 1
    assert ps["label"] == LABEL
    assert ps["by_game_type"] == {"F": 0, "D": 1, "L": 1, "W": 1}
    # The chain proves the WHOLE record was appended to.
    assert both["chain_sha"] == be.chain_sha(rows_all) != only["chain_sha"]
    assert only["postseason"]["n_rows"] == 0


def test_the_paper_ledger_and_the_subledger_artifact_split_the_postseason(tmp_path):
    led = tmp_path / "shadow.json"
    bs.record_slate(_payload([_reg_card()]), min_edge=0.06, path=led,
                    include_board_all=True)
    before = bs.summary(path=led)
    bs.record_slate(_payload([_post_card()]), min_edge=0.06, path=led,
                    include_board_all=True)
    games = [{"game_pk": 800001, "home_runs": 5, "away_runs": 2},
             {"game_pk": 900001, "home_runs": 6, "away_runs": 1, "game_type": "D"}]
    bs.settle(games=games, path=led)
    after = bs.summary(path=led)
    assert after["n_rows"] == before["n_rows"] == 1
    assert after["n_rows_all"] == 2 and after["n_postseason_rows"] == 1
    assert after["by_market"]["moneyline"]["n_rows"] == 1
    ps = after["postseason"]
    assert ps["n_rows"] == 1 and ps["won"] == 1 and ps["label"] == LABEL
    assert set(ps["by_game_type"]) == {"D"} and set(ps["by_market"]) == {"moneyline"}
    # No sweep, cell or readiness count takes the postseason row.
    assert len(bs.graded_bets(path=led)) == 1
    cells = bs.sweep_readiness_by_market_tag(path=led)
    assert all(b["n"] <= 1 for t in cells.values() for b in t.values())
    art = bs.readiness_artifact(path=led)
    assert art["n_rows"] == 1 and art["n_rows_all"] == 2
    assert art["postseason"]["n_rows"] == 1 and art["scope"] == "regular_season"


def test_no_gate_frame_takes_a_postseason_side(tmp_path):
    led = tmp_path / "cal.jsonl"
    bc.record_slate(_payload([_post_card(), _reg_card()]), path=led)
    bc.settle(games=[{"game_pk": 800001, "home_runs": 5, "away_runs": 2},
                     {"game_pk": 900001, "home_runs": 6, "away_runs": 1}], path=led)
    canon = bc.canonical_settled_games(bc.rows(path=led))
    assert [r["game_pk"] for r in canon["moneyline"]] == [800001]
    summ = bc.summary(path=led)
    assert summ["by_market"]["moneyline"]["n_rows"] == 2
    assert summ["postseason"]["n_rows"] == 2 and summ["n_rows_all"] == 4
    assert bs._sweep_row({"result": "won", "edge": 0.1, "decimal": 2.0,
                          "game_type": "F"}) is None
    assert bs._sweep_row({"result": "won", "edge": 0.1, "decimal": 2.0}) is not None


# ---------------------------------------------------------------------------
# condition 4: the guard and the bar, unchanged, on postseason rows
# ---------------------------------------------------------------------------
@pytest.fixture
def open_record(monkeypatch):
    rows: list[dict] = []
    monkeypatch.setattr(be, "load_record", lambda *a, **k: list(rows))
    monkeypatch.setattr(be, "append_record", lambda new, **k: rows.extend(new))
    monkeypatch.setattr(be, "record_publish_blockers",
                        lambda **k: [{"id": "test", "open": True, "reason": "open"}])
    return rows


def _slot(pk, side="home", odds=-120):
    return {"game_pk": pk, "matchup": "CHC at KCR", "market": "moneyline",
            "side": side, "point": None, "label": "KCR", "book": "lowvig",
            "odds": odds, "decimal": 1.8333, "edge": 0.1, "model_prob": 0.645,
            "slot": "pick_of_the_day", "min_edge_used": 0.06, "provisional": True,
            **bset.postseason_fields("D")}


def test_the_per_slot_guard_holds_on_postseason_rows(open_record):
    first = be.maybe_publish_record({"slate_date": DAY, "pick_of_the_day": _slot(900001),
                                     "longshot_of_the_day": None})
    assert first["written"] == 1
    assert open_record[0]["game_type"] == "D" and open_record[0]["postseason_label"] == LABEL
    second = be.maybe_publish_record({"slate_date": DAY,
                                      "pick_of_the_day": _slot(900002, side="away", odds=105),
                                      "longshot_of_the_day": None})
    assert second["written"] == 0 and second["n_refused"] == 1
    assert "already has a row" in second["refused"][0]["reason"]
    assert len(open_record) == 1


def test_the_total_lean_bar_holds_on_postseason_rows(monkeypatch):
    # The market policy is a separate rule; hold it at "any" so only the lean
    # bar can take the total out.
    monkeypatch.setattr(be, "slot_market_policy_legs",
                        lambda *a, **k: {"dispersion_bars": False, "ledger_bars": False})
    monkeypatch.setattr(be, "BAR_TOTAL_LEAN_SLOTS", True)
    over = _side("over", "Over 7.5", odds=-105, edge=0.09, prob=0.60,
                 total_level_caveat="the slate's totals lean Over")
    card = _card(900003, game_type="L",
                 total={"line": 7.5, "sides": [over], "p_push": 0.0})
    stats: dict = {}
    cands = be._floor_clearing_sides([card], 0.06, ledger_closed=frozenset(), stats=stats)
    assert cands == [] and stats["n_total_lean_barred_sides"] == 1
    monkeypatch.setattr(be, "BAR_TOTAL_LEAN_SLOTS", False)
    cands = be._floor_clearing_sides([card], 0.06, ledger_closed=frozenset())
    assert len(cands) == 1 and cands[0]["game_type"] == "L"


# ---------------------------------------------------------------------------
# settlement, without touching the fit's input
# ---------------------------------------------------------------------------
def _raw(pk, gt, *, state="Final"):
    return {"gamePk": pk, "season": "2026", "officialDate": DAY, "gameType": gt,
            "status": {"abstractGameState": state},
            "teams": {"home": {"team": {"name": "Kansas City Royals"}, "score": 4},
                      "away": {"team": {"name": "Chicago Cubs"}, "score": 2}},
            "linescore": {"teams": {"home": {"runs": 4}, "away": {"runs": 2}},
                          "currentInning": 9}}


def test_the_fit_input_stays_regular_season():
    assert bm._row_from_schedule(_raw(1, "D"), None) is None
    reg = bm._row_from_schedule(_raw(2, "R"), None)
    assert reg and "game_type" not in reg
    post = bm._row_from_schedule(_raw(1, "D"), None,
                                 game_types=bm.POSTSEASON_SCHEDULE_TYPES)
    assert post and post["game_type"] == "D"
    assert set(post) - set(reg) == {"game_type"}


def test_the_settlement_path_adds_postseason_finals(monkeypatch):
    reg = [{"game_pk": 1, "home_runs": 3, "away_runs": 2}]
    post = [{"game_pk": 2, "home_runs": 1, "away_runs": 0, "game_type": "W"},
            {"game_pk": 1, "home_runs": 9, "away_runs": 9, "game_type": "W"}]
    monkeypatch.setattr(bm, "completed_games", lambda *a, **k: list(reg))
    monkeypatch.setattr(bm, "postseason_finals", lambda *a, **k: list(post))
    games = bset.load_completed()
    assert [g["game_pk"] for g in games] == [1, 2]
    assert games[0] == reg[0], "a regular-season row is never replaced"


def test_postseason_finals_offline_reads_its_own_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(bm, "GAME_CACHE", tmp_path)
    (tmp_path / bm.POSTSEASON_FINALS_FILE).write_text(json.dumps([
        {"game_pk": 5, "season": "2026", "game_type": "D"},
        {"game_pk": 6, "season": "2025", "game_type": "D"}]), encoding="utf-8")
    assert [r["game_pk"] for r in bm.postseason_finals("2026", refresh=False)] == [5]
    assert not (tmp_path / "completed_games.json").exists()


# ---------------------------------------------------------------------------
# condition 3 and the page
# ---------------------------------------------------------------------------
def test_the_registry_row_and_the_glossary_say_the_evidence_is_regular_season():
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    row = [m for m in reg["models"] if m["model_id"] == "betting_game_prob"][0]
    assert "regular-season only" in row["notes"]
    assert "owner decision of 2026-10-01" in row["notes"]
    gl = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    entry = [e for e in gl["entries"] if e["id"] == "provisional_pick"][0]
    assert "regular-season game" in entry["methodology"]
    assert "owner decision of 2026-10-01" in entry["methodology"]


def test_the_page_renders_the_label_and_the_sub_ledger():
    js = (ROOT / "assets" / "betting.js").read_text(encoding="utf-8")
    assert "function postseasonTag(" in js and "postseasonTag(b)" in js
    assert "postseasonTag(p)" in js and "postseasonLabel(p)" in js
    assert "function postseasonRecordBlock(" in js and "r.scope_note" in js
    doc = (ROOT / "docs" / "diamond-betting.md").read_text(encoding="utf-8")
    assert "## 8a. Postseason games are priced (owner decision 2026-10-01, INT-A1)" in doc
