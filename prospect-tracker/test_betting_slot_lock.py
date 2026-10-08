# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The two guards that make a published slot a one-time claim (repair R4-1).

Neither is a pricing change. No probability and no edge moves,
`betting_model.MODEL_VERSION` is untouched, and on a first build of a slate
every number the board serves is the number it served before: the lock has
nothing in it, so the selected row passes through and is written down.

  R4-1a  THE SLOT LOCK. Slot selection is deterministic in its INPUTS and not
         in time. `_potd_rank` reads `model_prob`, then the distance of the
         price from -110, then EV, all off a board rebuilt from whatever the
         odds cache and the schedule say at the moment of the build. So a
         second build of one slate, against a moved line or a game that has
         since started, can publish a DIFFERENT Pick of the Day for the same
         night. Today the production box builds the board once, at the 03:10 ET
         nightly, which is the only reason this has not happened; a manual
         rebuild, a retry after a failure, or the intraday rebuild that posted
         lineups would need are all second builds.

         `apply_slot_lock` writes the first published row of each slot to
         `.cache/betting/published_slots/<slate>.json` and serves it verbatim
         from then on, with what the current board would select riding beside
         it as `since_published`.

  R4-1b  THE RECORD GUARD. `maybe_publish_record` is idempotent per bet
         identity, and a second selection for one slot is a different bet, so
         it was a legal append: the public record could carry two Picks of the
         Day for one slate with nothing saying which was the claim. It is
         latent only because `RECORD_PUBLISH_ARMED` is False. The guard refuses
         a candidate whose `(slate_date, slot)` is already on the record, and
         names the refusal.

  The two protect DIFFERENT FILES. The lock lives under `.cache/`, which the
  nightly `git checkout -- .` cannot touch but which a fresh box has never
  written; the record guard reads the record itself. A record protected only by
  a cache file that may be absent is not protected.

Also pinned here: `betting_shadow`'s `pricing_basis` stamp. The uncapped
`board_all` tag is the one tag a second pass of a slate can add rows to, so it
is the tag that would pool two pricers' boards into one ROI the day a second
pricing basis exists. Every new row is stamped, unstamped rows keep their
meaning, and `_sweep_row` refuses a foreign basis.

Every write in this file goes to `tmp_path` or to an in-memory fake: nothing
here writes a betting artifact (plan stop-item X6).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

be = pytest.importorskip("betting_export")
bm = pytest.importorskip("betting_model")
bs = pytest.importorskip("betting_shadow")

DAY = "2026-09-17"


def _utc(s: str) -> datetime:
    """An aware UTC instant, so the slate tests pin the clock signal instead of
    inheriting the wall clock of the box they run on."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _row(**over) -> dict:
    """A slot row with the fields the lock, the record and the ledger read."""
    row = {"game_pk": 822845, "matchup": "BOS at TEX", "market": "runline",
           "side": "home", "point": 1.5, "label": "TEX +1.5", "book": "bovada",
           "book_title": "Bovada", "odds": -150, "decimal": 1.6667,
           "edge": 0.08116, "model_prob": 0.67142, "ev_per_unit": 0.11906,
           "start": "2026-09-18T00:05:00Z", "slot": "pick_of_the_day",
           "min_edge_used": 0.06, "provisional": True}
    row.update(over)
    return row


def _meta() -> dict:
    """The `pick_meta` shape `apply_slot_lock` updates in place."""
    return {"slots": {s: {"slot": s, "present": True, "reason": "the rule"}
                      for s in be.SLOT_LABELS}}


def _apply(slots, meta=None, *, root, **kw):
    kw.setdefault("slate_date", DAY)
    kw.setdefault("pick_reason", "the rule")
    return be.apply_slot_lock(slots, meta if meta is not None else _meta(),
                              root=root, **kw)


# ---------------------------------------------------------------------------
# R4-1a: the slot lock
# ---------------------------------------------------------------------------
def test_two_builds_of_one_slate_publish_one_pick(tmp_path):
    """THE TWO-BUILD TEST. Build, change the board so the slot moves, build
    again: the second build serves the FIRST build's row, byte for byte.

    MUTATION: in `apply_slot_lock`, serve `fresh` instead of the locked row
    when an entry exists. This test then reports the second build's side."""
    first = {"pick_of_the_day": _row(), "longshot_of_the_day": None}
    _apply(dict(first), root=tmp_path)

    # A SECOND BUILD, on a board that would now pick a different game.
    moved = _row(game_pk=824141, matchup="SEA at LAA", market="moneyline",
                 side="away", point=None, label="SEA", odds=125, book="fanduel",
                 edge=0.0912, model_prob=0.5301)
    slots = {"pick_of_the_day": moved, "longshot_of_the_day": None}
    meta = _meta()
    reason, state = _apply(slots, meta, root=tmp_path)

    served = slots["pick_of_the_day"]
    assert state["served_from_lock"] == ["pick_of_the_day"]
    assert served["game_pk"] == first["pick_of_the_day"]["game_pk"]
    assert served["label"] == "TEX +1.5"
    assert served["odds"] == -150
    assert served["locked"] is True
    # The published row is unchanged in every field it was published with.
    for k, v in first["pick_of_the_day"].items():
        assert served[k] == v, k

    # The later opinion is disclosure, beside the row and never in place of it.
    since = served["since_published"]
    assert since["status"] == "different_side"
    assert since["now_selected"]["game_pk"] == 824141
    assert since["now_selected"]["label"] == "SEA"
    assert "published" in reason
    assert meta["slots"]["pick_of_the_day"]["locked"] is True


def test_the_first_build_serves_exactly_what_it_selected(tmp_path):
    """A first build must not move a single number. The lock is empty, so the
    selected row passes through untouched and is recorded."""
    row = _row()
    slots = {"pick_of_the_day": dict(row), "longshot_of_the_day": None}
    reason, state = _apply(slots, root=tmp_path)
    assert slots["pick_of_the_day"] == row
    assert reason == "the rule"
    assert state["created"] == ["pick_of_the_day"]
    assert state["served_from_lock"] == []
    on_disk = json.loads(
        be.published_slots_path(DAY, root=tmp_path).read_text(encoding="utf-8"))
    assert on_disk["slots"]["pick_of_the_day"]["row"] == row
    assert on_disk["slots"]["pick_of_the_day"]["model_version"] == bm.MODEL_VERSION


def test_a_slot_the_first_build_left_empty_can_still_be_published(tmp_path):
    """First-write-wins is PER SLOT. A slate whose longshot slot was empty at
    03:10 can still publish one later, and doing so must not disturb the pick
    that is already locked."""
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
           root=tmp_path)
    late = _row(slot="longshot_of_the_day", game_pk=824141, market="moneyline",
                side="away", point=None, label="SEA", odds=260)
    slots = {"pick_of_the_day": _row(odds=-165), "longshot_of_the_day": late}
    _, state = _apply(slots, root=tmp_path)
    assert state["created"] == ["longshot_of_the_day"]
    assert state["served_from_lock"] == ["pick_of_the_day"]
    assert slots["pick_of_the_day"]["odds"] == -150       # the published price
    assert slots["longshot_of_the_day"]["odds"] == 260
    doc = be.load_slot_lock(DAY, root=tmp_path)
    assert sorted(doc["slots"]) == ["longshot_of_the_day", "pick_of_the_day"]
    assert doc["slots"]["pick_of_the_day"]["row"]["odds"] == -150


def test_a_dry_build_never_creates_a_lock(tmp_path):
    """`write=False` is not a publication. It reads the lock and says what it
    would have locked, and the file stays absent."""
    slots = {"pick_of_the_day": _row(), "longshot_of_the_day": None}
    _, state = _apply(slots, root=tmp_path, write=False)
    assert not be.published_slots_path(DAY, root=tmp_path).exists()
    assert state["created"] == []
    assert "write=False" in state["reason"]
    # And it still SERVES an existing lock, so a dry run shows the live page.
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
           root=tmp_path)
    slots = {"pick_of_the_day": _row(odds=-190, edge=0.02),
             "longshot_of_the_day": None}
    _, state = _apply(slots, root=tmp_path, write=False)
    assert state["served_from_lock"] == ["pick_of_the_day"]
    assert slots["pick_of_the_day"]["odds"] == -150


def test_a_build_with_no_board_neither_locks_nor_serves(tmp_path):
    """The stale-board guard owns the empty-board case. Resurrecting a
    published row onto a carried board would put a live-looking claim on top of
    day-old prices, which is what `_carry_previous_board` exists to prevent.

    `has_board` is named for what the caller passes: `bool(bets)`, which is
    "is there a slate", not "did anything get priced". The unpriced board is
    the `blocked` refusal below, and the two are not the same case."""
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
           root=tmp_path)
    slots = {"pick_of_the_day": None, "longshot_of_the_day": None}
    _, state = _apply(slots, root=tmp_path, has_board=False)
    assert state["applied"] is False
    assert slots["pick_of_the_day"] is None
    assert "no board for this slate" in state["reason"]
    # And an empty first build writes nothing at all.
    _, state = _apply({"pick_of_the_day": None, "longshot_of_the_day": None},
                      root=tmp_path / "empty", has_board=False)
    assert not (tmp_path / "empty").exists()


def test_a_blocked_board_does_not_serve_the_lock(tmp_path):
    """An absent odds feed, or a cached snapshot belonging to another slate,
    empties both slots by policy: a selection needs a real market price to
    disagree with. The lock does not lift that stop, and it does not write
    through it either.

    MUTATION: drop the `meta.get("blocked")` branch in `apply_slot_lock`.
    `test_betting.test_build_is_offline_safe` then serves a pick on a board
    with no market at all."""
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
           root=tmp_path)
    meta = _meta()
    meta["blocked"] = True
    meta["blocked_reason"] = "no odds snapshot is cached"
    slots = {"pick_of_the_day": None, "longshot_of_the_day": None}
    _, state = _apply(slots, meta, root=tmp_path)
    assert slots == {"pick_of_the_day": None, "longshot_of_the_day": None}
    assert state["applied"] is False
    assert "no odds snapshot is cached" in state["reason"]
    # Nor does a blocked FIRST build lock an empty slate.
    fresh = tmp_path / "blocked"
    meta2 = _meta()
    meta2["blocked"] = True
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None}, meta2,
           root=fresh)
    assert not fresh.exists()


def test_an_empty_later_build_still_serves_the_published_row(tmp_path):
    """The slot's candidate is gone (the game started, the line moved through
    the floor). The published claim stands and says the board would now be
    empty; it is not quietly withdrawn."""
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
           root=tmp_path)
    slots = {"pick_of_the_day": None, "longshot_of_the_day": None}
    board = [{"game_pk": 822845, "status": "Live"}]
    _, state = _apply(slots, root=tmp_path, board=board)
    served = slots["pick_of_the_day"]
    assert served["label"] == "TEX +1.5"
    since = served["since_published"]
    assert since["status"] == "no_longer_selected"
    assert since["now_selected"] is None
    # A locked slot whose game has started stays shown, WITH its state.
    assert since["game_status"] == "Live"
    assert since["game_started"] is True


def test_the_same_side_at_a_moved_price_says_which_price_is_graded(tmp_path):
    """The identity is the bet, not the price, so this is not a second
    selection. It is still disclosed, because the ledgers grade the price the
    row was published at."""
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
           root=tmp_path)
    slots = {"pick_of_the_day": _row(odds=-135, decimal=1.7407, edge=0.0641),
             "longshot_of_the_day": None}
    _apply(slots, root=tmp_path)
    since = slots["pick_of_the_day"]["since_published"]
    assert since["status"] == "price_moved"
    assert slots["pick_of_the_day"]["odds"] == -150
    assert since["now_selected"]["odds"] == -135


def test_an_unchanged_second_build_carries_no_disclosure(tmp_path):
    """The ordinary re-run: same board, same row. Nothing to disclose, and the
    served row is the published one."""
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
           root=tmp_path)
    slots = {"pick_of_the_day": _row(), "longshot_of_the_day": None}
    _, state = _apply(slots, root=tmp_path)
    assert "since_published" not in slots["pick_of_the_day"]
    assert state["locked"]["pick_of_the_day"]["since_published"]["status"] == \
        "unchanged"


def test_a_model_version_bump_mid_slate_does_not_unpublish_the_row(tmp_path,
                                                                  monkeypatch):
    """A pricer bump between two builds of one slate is a new pricer, not a
    correction of last night's claim. The published row keeps the version that
    priced it, the newer pricer's opinion rides in `since_published`, and the
    RECORD ROW credits the version that actually priced the row."""
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
           root=tmp_path)
    monkeypatch.setattr(bm, "MODEL_VERSION", "betting_runs_v3")
    slots = {"pick_of_the_day": _row(odds=-120, edge=0.05),
             "longshot_of_the_day": None}
    _apply(slots, root=tmp_path)
    served = slots["pick_of_the_day"]
    since = served["since_published"]
    assert since["model_version_at_publish"] == "betting_runs_v2"
    assert since["model_version_now"] == "betting_runs_v3"
    assert served["model_version"] == "betting_runs_v2"
    rec = be.record_row(served, slate_date=DAY, evald=None)
    assert rec["model_version"] == "betting_runs_v2"
    # A row this build priced itself still takes the live constant.
    assert be.record_row(_row(), slate_date=DAY,
                         evald=None)["model_version"] == "betting_runs_v3"


def test_the_lock_file_is_first_write_wins(tmp_path):
    """The storage rule, exercised directly: a second document proposing a
    different row for a slot the file already holds never replaces it."""
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
           root=tmp_path)
    doc = be.load_slot_lock(DAY, root=tmp_path)
    doc["slots"]["pick_of_the_day"] = {"published_at": "2026-09-17T23:59:00+00:00",
                                       "model_version": "x",
                                       "row": _row(label="SEA", odds=999)}
    be._save_slot_lock(doc, root=tmp_path)
    back = be.load_slot_lock(DAY, root=tmp_path)
    assert back["slots"]["pick_of_the_day"]["row"]["label"] == "TEX +1.5"
    assert back["slots"]["pick_of_the_day"]["row"]["odds"] == -150


def test_an_unreadable_lock_is_loud_and_does_not_kill_the_build(tmp_path, caplog):
    """A corrupt sidecar must not stop the board from publishing, and must not
    pass silently either: an empty lock means the slate can be re-selected.

    The file is written through the real save and then corrupted in place, so
    this is the corrupt-file path and not the "another run wrote it" path.

    AND IT IS NOT OVERWRITTEN. A read-modify-write over a file this process
    cannot parse would replace a publication fact with one slot of its own; the
    write refuses, the build says so on the slot, and the bytes survive for
    whoever can read them."""
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
           root=tmp_path)
    p = be.published_slots_path(DAY, root=tmp_path)
    p.write_text("{not json", encoding="utf-8")
    with caplog.at_level("WARNING"):
        doc = be.load_slot_lock(DAY, root=tmp_path)
    assert doc["slots"] == {}
    assert "unlocked" in caplog.text
    meta = _meta()
    _, state = _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
                      meta, root=tmp_path)
    assert state["created"] == []
    assert state["error"]
    assert meta["slots"]["pick_of_the_day"]["locked"] is False
    assert p.read_text(encoding="utf-8") == "{not json"


def test_the_lock_lives_under_the_cache_the_nightly_cannot_revert():
    """`data/` is git-tracked and the production nightly runs
    `git checkout -- .` between builds, so a lock there would be reverted
    exactly when it is needed. It belongs beside the record and the chain
    anchor."""
    assert be.published_slots_dir().parent == be.BETTING_CACHE_DIR
    assert be.published_slots_dir().name == "published_slots"
    assert be.published_slots_path(DAY).parent == be.published_slots_dir()


# ---------------------------------------------------------------------------
# R4-1b: the record guard
# ---------------------------------------------------------------------------
@pytest.fixture
def open_record(monkeypatch):
    """`maybe_publish_record` with every blocker open and an IN-MEMORY record.

    Nothing in this fixture touches `.cache/betting/record.jsonl` or
    `data/betting_record.json`; the rows live in a list the test can read."""
    rows: list[dict] = []
    monkeypatch.setattr(be, "load_record", lambda *a, **k: list(rows))
    monkeypatch.setattr(be, "append_record", lambda new, **k: rows.extend(new))
    # ONE open blocker, not an empty list: `record_publish_ok` requires a
    # non-empty list, so an empty one is "blocked" and the guard below would
    # never be reached.
    monkeypatch.setattr(be, "record_publish_blockers",
                        lambda **k: [{"id": "test", "open": True,
                                      "reason": "open for this test"}])
    return rows


def _payload(pick=None, longshot=None) -> dict:
    return {"slate_date": DAY, "pick_of_the_day": pick,
            "longshot_of_the_day": longshot}


def test_the_record_takes_one_row_per_slate_and_slot(open_record):
    """THE LATENT DOUBLE-HEADLINE DEFECT. Two builds of one slate that select
    two different sides for one slot propose two different `bet_id`s, and both
    are legal appends.

    MUTATION: drop the `slot_taken` check in `maybe_publish_record`. The record
    then carries two Pick of the Day rows for 2026-09-17."""
    first = be.maybe_publish_record(_payload(_row()))
    assert first["written"] == 1
    assert open_record[0]["slot"] == "pick_of_the_day"

    moved = _row(game_pk=824141, market="moneyline", side="away", point=None,
                 label="SEA", odds=125)
    second = be.maybe_publish_record(_payload(moved))
    assert second["written"] == 0
    assert second["n_refused"] == 1
    assert second["refused"][0]["slot"] == "pick_of_the_day"
    assert "already has a row" in second["refused"][0]["reason"]
    assert "already has a row" in second["reason"]
    assert len(open_record) == 1
    assert [r["slot"] for r in open_record] == ["pick_of_the_day"]


def test_the_guard_is_per_slot_and_per_slate(open_record):
    """It refuses a SECOND row for one slot, and nothing else: the other slot
    on the same slate, and the same slot on the next slate, both publish."""
    be.maybe_publish_record(_payload(_row()))
    long_row = _row(slot="longshot_of_the_day", game_pk=824141,
                    market="moneyline", side="away", point=None, label="SEA",
                    odds=260)
    out = be.maybe_publish_record(_payload(_row(), long_row))
    assert out["written"] == 1
    assert sorted(r["slot"] for r in open_record) == ["longshot_of_the_day",
                                                      "pick_of_the_day"]
    tomorrow = {"slate_date": "2026-09-18", "pick_of_the_day": _row(),
                "longshot_of_the_day": None}
    out = be.maybe_publish_record(tomorrow)
    assert out["written"] == 1
    assert len(open_record) == 3


def test_the_same_row_twice_is_still_idempotent_not_refused(open_record):
    """A plain re-run re-proposes the same bet. That is the `bet_id` path and
    it stays what it was: nothing written, nothing refused."""
    be.maybe_publish_record(_payload(_row()))
    out = be.maybe_publish_record(_payload(_row()))
    assert out["written"] == 0
    assert out["n_refused"] == 0
    assert "already on the record" in out["reason"]


def test_a_blocked_slate_never_reaches_the_guard(monkeypatch):
    """The blocker list is still the authority. With one closed, nothing is
    proposed, written or refused."""
    monkeypatch.setattr(be, "load_record", lambda *a, **k: [])
    monkeypatch.setattr(be, "append_record",
                        lambda *a, **k: pytest.fail("wrote while blocked"))
    out = be.maybe_publish_record(_payload(_row()))
    assert out["written"] == 0
    assert out["ok"] is False
    assert out["reason"].startswith("blocked:")


# ---------------------------------------------------------------------------
# the shadow ledger's pricing basis
# ---------------------------------------------------------------------------
def _ledger_row(**over) -> dict:
    row = {"shadow_id": "a" * 16, "slate_date": DAY, "game_pk": 822845,
           "market": "runline", "side": "home", "point": 1.5, "odds": -150,
           "decimal": 1.6667, "edge": 0.08116, "slot": bs.BOARD_ALL_TAG,
           "tags": [bs.BOARD_ALL_TAG], "result": "won"}
    row.update(over)
    return row


def _shadow_payload(basis=bs.PRICING_BASIS_CONSTRUCTED) -> dict:
    """A board that states which pricer priced it, as `build` writes it."""
    payload = {"slate_date": DAY, "status": {"odds_feed": "ok"},
               "team_bets": [{"game_pk": 822845, "matchup": "BOS at TEX",
                              "start": "2026-09-18T00:05:00Z",
                              "moneyline": [{"side": "home", "label": "TEX",
                                             "book": "bovada", "odds": -150,
                                             "decimal": 1.6667, "edge": 0.09,
                                             "model_prob": 0.67}]}]}
    if basis is not None:
        payload["model"] = {"pricing_basis": basis}
    return payload


def test_every_new_shadow_row_is_stamped_with_its_pricing_basis(tmp_path):
    """The stamp lands at write time, off the BOARD's own statement."""
    payload = {"slate_date": DAY, "status": {"odds_feed": "ok"},
               "model": {"pricing_basis": bs.PRICING_BASIS_CONSTRUCTED},
               "team_bets": [{"game_pk": 822845, "matchup": "BOS at TEX",
                              "start": "2026-09-18T00:05:00Z",
                              "moneyline": [{"side": "home", "label": "TEX",
                                             "book": "bovada", "odds": -150,
                                             "decimal": 1.6667, "edge": 0.09,
                                             "model_prob": 0.67}]}]}
    p = tmp_path / "shadow.json"
    out = bs.record_slate(payload, min_edge=0.06, include_board_all=True,
                          path=p, slots={})
    assert out["written"] >= 1
    rows = bs.load(p)
    assert rows
    assert {r["pricing_basis"] for r in rows} == {bs.PRICING_BASIS_CONSTRUCTED}
    assert bs.BOARD_ALL_TAG in {t for r in rows for t in bs.row_tags(r)}


def test_an_unknown_pricing_basis_is_refused(tmp_path):
    """A basis nobody registered is a typo, and a typo that reaches the ledger
    silently splits the sample."""
    with pytest.raises(ValueError):
        bs.record_slate({"slate_date": DAY, "status": {"odds_feed": "ok"}},
                        min_edge=0.06, pricing_basis="lineups",
                        path=tmp_path / "shadow.json")


def test_a_second_basis_never_pools_into_a_sweep(tmp_path):
    """THE POOLING THE STAMP EXISTS TO PREVENT. `board_all` is uncapped, so an
    intraday pass can add to it; if its rows were priced on a posted lineup
    they are a different sample and a threshold fitted to the union is wrong
    for both.

    MUTATION: drop the `sweeps_with_served_basis` check in `_sweep_row`. The
    sweepable count then reads 2."""
    p = tmp_path / "shadow.json"
    bs.write([_ledger_row(shadow_id="a" * 16,
                          pricing_basis=bs.PRICING_BASIS_CONSTRUCTED),
              _ledger_row(shadow_id="b" * 16, result="lost",
                          pricing_basis=bs.PRICING_BASIS_POSTED)], path=p)
    swept = bs.graded_bets(slot=bs.BOARD_ALL_TAG, path=p)
    assert len(swept) == 1
    assert swept[0]["won"] is True
    # The rows are still THERE and still counted; only the sweep refuses them.
    summary = bs.summary(path=p)
    assert summary["by_pricing_basis"][bs.PRICING_BASIS_POSTED]["n_rows"] == 1
    assert summary["by_pricing_basis"][bs.PRICING_BASIS_CONSTRUCTED]["n_rows"] == 1


def test_rows_written_before_the_stamp_are_swept_and_not_backfilled(tmp_path):
    """Every row on disk today was priced on the constructed nine, because no
    other pricer has ever written to this ledger. They are read as `unstamped`
    rather than relabelled, and they keep entering the sweeps they always
    entered."""
    p = tmp_path / "shadow.json"
    bs.write([_ledger_row(shadow_id="c" * 16)], path=p)
    row = bs.load(p)[0]
    assert "pricing_basis" not in row
    assert bs.pricing_basis_of(row) == bs.PRICING_BASIS_UNSTAMPED
    assert bs.sweeps_with_served_basis(row) is True
    assert len(bs.graded_bets(slot=bs.BOARD_ALL_TAG, path=p)) == 1


def test_the_served_basis_is_the_constructed_nine():
    """Nothing in the tree prices a posted lineup, and nothing may until 5j
    passes. This pins the served basis so that flipping it is a deliberate act
    with a failing test beside it."""
    assert bs.SERVED_PRICING_BASIS == bs.PRICING_BASIS_CONSTRUCTED
    assert set(bs.PRICING_BASES) == {"constructed", "posted"}


def test_the_live_ledger_is_one_sample(tmp_path):
    """MEASURED, on whatever the box holds. Every row of the real ledger reads
    as one basis: no sweep to date has pooled two pricers. Skipped where the
    ledger is absent, so a fresh checkout does not fail on a missing file."""
    rows = bs.load()
    if not rows:
        pytest.skip("no shadow ledger on this box")
    bases = {bs.pricing_basis_of(r) for r in rows}
    assert bases <= {bs.PRICING_BASIS_UNSTAMPED, bs.PRICING_BASIS_CONSTRUCTED}
    assert all(bs.sweeps_with_served_basis(r) for r in rows)


def test_the_lock_store_on_this_box_is_well_formed():
    """MEASURED, on whatever the box holds.

    The first cut of this test asserted only that any lock present was
    non-empty, which zero locks and fifty locks both pass: it could not fail
    for the claim it made. This one reads every document the store holds and
    checks the shape the serving path depends on, so a lock the nightly wrote
    wrong fails here rather than on the page. Skipped where the directory does
    not exist, which is a fresh checkout and not a defect."""
    d = be.published_slots_dir()
    if not d.is_dir():
        pytest.skip("no lock store on this box yet")
    locks = sorted(d.glob("*.json"))
    if not locks:
        pytest.skip("the lock store is empty on this box")
    for p in locks:
        doc = json.loads(Path(p).read_text(encoding="utf-8"))
        assert doc.get("schema") == be.SLOT_LOCK_SCHEMA, p.name
        assert doc.get("slate_date") == p.stem, p.name
        slots = doc.get("slots") or {}
        assert slots, f"{p.name} holds no published slot"
        for slot, entry in slots.items():
            assert slot in be.SLOT_LABELS, f"{p.name}: unknown slot {slot}"
            assert isinstance(entry.get("row"), dict), f"{p.name}: {slot}"
            assert entry.get("published_at"), f"{p.name}: {slot}"
            assert entry["row"].get("game_pk") is not None, f"{p.name}: {slot}"
# ---------------------------------------------------------------------------
# R4-1a: what the page is told once the lock engages
# ---------------------------------------------------------------------------
def _board(status="Preview", game_pk=822845, start=None) -> list[dict]:
    """One board row, the shape `_since_published` reads the game state off.

    `start` is the row's own first pitch. It is the SECOND signal `_has_started`
    reads, and a board row carries it in production, so a helper that omitted it
    could only ever exercise the status string."""
    return [{"game_pk": game_pk, "date": DAY, "status": status,
             "datetime": start, "matchup": "BOS at TEX"}]


def test_a_started_game_says_so_in_a_field_the_page_renders(tmp_path):
    """THE DISCLOSURE HAS TO REACH A READER. A locked row whose game has
    started still carries its price, and assets/betting.js renders none of
    `since_published`, `locked`, `published_at` or `lock_note`: the row would
    be badged exactly like a fresh selection at a price nobody can take.

    MUTATION: drop the `_join_caveat` line in `apply_slot_lock`. The served row
    then carries the whole story in fields the client never reads."""
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
           root=tmp_path)
    slots = {"pick_of_the_day": _row(), "longshot_of_the_day": None}
    _apply(slots, root=tmp_path, board=_board("In Progress"))
    served = slots["pick_of_the_day"]
    since = served["since_published"]
    assert since["game_started"] is True
    assert since["game_called_off"] is False
    # `caveat` is the pick card's note line, which the client already renders.
    assert "has started" in served["caveat"]
    assert "not one you can take now" in served["caveat"]


def test_a_postponed_game_is_not_a_started_game(tmp_path):
    """A POSTPONED GAME HAS NOT STARTED, and the first cut of this read said it
    had: "postponed" is not "preview", so the disclosure told a reader the
    first pitch had been thrown on a game that will not be played. `_is_called_off`
    is the module's one reading of that state and it is what answers here.

    MUTATION: go back to `status not in ("preview", "")`. `game_started` then
    reads True for a postponement."""
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
           root=tmp_path)
    slots = {"pick_of_the_day": _row(), "longshot_of_the_day": None}
    _apply(slots, root=tmp_path, board=_board("postponed"))
    since = slots["pick_of_the_day"]["since_published"]
    assert since["game_called_off"] is True
    assert since["game_started"] is False
    assert "called off" in slots["pick_of_the_day"]["caveat"]


def test_a_stale_preview_row_past_first_pitch_is_started(tmp_path):
    """ONE DEFINITION OF STARTED, NOT FOUR. `_has_started` is the module's
    single reading and it takes two signals: the status string and a first
    pitch at or before now. The first cut of this block tested the string
    alone, which answered "not started" for exactly the row the clock signal
    exists for - a schedule block refreshed before the game started and not
    since - and served a published price with no word about it.

    MUTATION: go back to `status not in ("preview", "")`. `game_started` reads
    False here and the caveat loses its second sentence."""
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
           root=tmp_path)
    slots = {"pick_of_the_day": _row(), "longshot_of_the_day": None}
    _apply(slots, root=tmp_path,
           board=_board("Preview", start="2026-09-18T00:05:00Z"),
           now="2026-09-18T01:30:00Z")
    since = slots["pick_of_the_day"]["since_published"]
    assert since["game_status"] == "Preview"
    assert since["game_started"] is True
    assert "has started" in slots["pick_of_the_day"]["caveat"]
    # The same row read BEFORE first pitch is not started, so the clock is
    # being read and not just the presence of a datetime.
    quiet = {"pick_of_the_day": _row(), "longshot_of_the_day": None}
    _apply(quiet, root=tmp_path,
           board=_board("Preview", start="2026-09-18T00:05:00Z"),
           now="2026-09-17T23:00:00Z")
    assert "since_published" not in quiet["pick_of_the_day"]


def test_the_lock_searches_the_rows_that_left_the_board(tmp_path):
    """THE GAMES THIS DISCLOSURE EXISTS FOR ARE NOT ON THE BOARD. `build`
    hands the lock the board `_drop_started_rows` returned, and that filter
    removes started AND called-off rows first, so a lock given only the board
    finds nothing for exactly the row it has to speak about. `dropped` is the
    other half of the same slate.

    MUTATION: drop the `dropped` walk in `_since_published`. Both halves fail
    with no game state on the block at all."""
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
           root=tmp_path)
    slots = {"pick_of_the_day": _row(), "longshot_of_the_day": None}
    _apply(slots, root=tmp_path, board=[], dropped=_board("In Progress"))
    since = slots["pick_of_the_day"]["since_published"]
    assert since["game_started"] is True
    assert "has started" in slots["pick_of_the_day"]["caveat"]

    off = {"pick_of_the_day": _row(), "longshot_of_the_day": None}
    _apply(off, root=tmp_path, board=[], dropped=_board("postponed"))
    since = off["pick_of_the_day"]["since_published"]
    assert since["game_called_off"] is True
    assert since["game_started"] is False
    assert "called off" in off["pick_of_the_day"]["caveat"]


def _sched(day="2026-09-18") -> list[dict]:
    """Three rows of one date: one still to come, one under way, one called
    off. The second is the case that matters, because `is_bettable` removes a
    Live row BEFORE the started filter runs and the payload's started count
    therefore never sees it."""
    return [
        {"game_pk": 1, "date": day, "status": "Preview",
         "datetime": f"{day}T23:05:00Z", "home": {"org": "TEX"},
         "away": {"org": "BOS"}},
        {"game_pk": 2, "date": day, "status": "In Progress",
         "datetime": f"{day}T17:05:00Z", "home": {"org": "NYY"},
         "away": {"org": "TOR"}},
        {"game_pk": 3, "date": day, "status": "postponed",
         "datetime": f"{day}T22:05:00Z", "home": {"org": "CHC"},
         "away": {"org": "MIL"}}]


def _fantasy(monkeypatch, games):
    """Point every schedule read in the module at `games`."""
    monkeypatch.setattr(
        be, "_load",
        lambda name, *a, **k: ({"schedule": {"games": list(games)}}
                               if "fantasy" in str(name) else {}))


def test_the_filter_hands_over_every_row_that_is_not_on_the_board(monkeypatch):
    """`resolve_slate` is where the board and the rest of the date part
    company, so it is where the rest has to be produced. Two reasons this
    cannot be read off the two published blocks: they carry a REDUCED row,
    truncated at twenty and without `date` or `datetime`, and they are counted
    over the BETTABLE rows alone, which is the one population a game under way
    has already left.

    MUTATION: define the handoff as the started plus called-off buckets. Game 2
    is missing from it, which is precisely the game a locked slot would be
    serving a dead price on."""
    day = "2026-09-18"
    games = _sched(day)
    _fantasy(monkeypatch, games)
    stats: dict = {}
    _, board = be.resolve_slate(day, now=_utc(f"{day}T20:00:00Z"),
                                stats=stats, priceable={})
    dropped = stats["dropped_board_rows"]
    assert [g["game_pk"] for g in board] == [1]
    assert sorted(g["game_pk"] for g in dropped) == [2, 3]
    # WHOLE ROWS, so the two state reads work on what comes out of here.
    for g in dropped:
        assert g.get("date") and g.get("datetime")
    assert be._has_started(dropped[0], _utc(f"{day}T20:00:00Z")) is True
    assert be._is_called_off(dropped[1]) is True
    # The published counts are unchanged: neither row was bettable, so neither
    # reached the filter the two blocks report on.
    assert stats["started_rows_dropped"]["n"] == 0
    assert stats["called_off_rows_dropped"]["n"] == 0

    # THE WALK REACHES THE SAME ANSWER AS THE EXPLICIT DATE. Two paths into one
    # filter, and L14-12 is the defect that happens when they drift.
    walk: dict = {}
    _, wboard = be.resolve_slate(now=_utc(f"{day}T20:00:00Z"), stats=walk,
                                 priceable={})
    assert [g["game_pk"] for g in wboard] == [1]
    assert sorted(g["game_pk"] for g in walk["dropped_board_rows"]) == [2, 3]


def test_the_never_blank_fallback_does_not_drop_a_row_twice(monkeypatch):
    """When every bettable row on the card is a stale Preview past first pitch,
    the filter puts them BACK on the board, so they did not leave it and the
    lock finds them where it looks first. Leaving them in the handoff as well
    would be one row in two places.

    MUTATION: compute the handoff from the started bucket. The same game is
    then both on the board and among the rows that left it."""
    day = "2026-09-18"
    games = [{"game_pk": 2, "date": day, "status": "Preview",
              "datetime": f"{day}T17:05:00Z", "home": {"org": "NYY"},
              "away": {"org": "TOR"}}]
    _fantasy(monkeypatch, games)
    stats: dict = {}
    _, board = be.resolve_slate(day, now=_utc(f"{day}T20:00:00Z"),
                                stats=stats, priceable={})
    assert [g["game_pk"] for g in board] == [2]
    assert stats["started_rows_dropped"]["applied"] is False
    assert stats["dropped_board_rows"] == []


def test_a_quiet_second_build_adds_no_note(tmp_path):
    """Same side, same price, game not started: there is nothing to disclose
    and the page gets no note. A caveat on every build of the evening is noise,
    and noise is how a real disclosure stops being read."""
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
           root=tmp_path)
    slots = {"pick_of_the_day": _row(), "longshot_of_the_day": None}
    _apply(slots, root=tmp_path, board=_board("Preview"))
    served = slots["pick_of_the_day"]
    assert "since_published" not in served
    assert served.get("caveat") is None
    assert be.lock_disclosure(None) is None


def test_the_lock_note_rides_beside_a_caveat_the_row_already_had(tmp_path):
    """The row's own caveat is about the model; the lock's is about the price
    in front of it. Neither may hide the other."""
    _apply({"pick_of_the_day": _row(caveat=be.POISSON_CAVEAT),
            "longshot_of_the_day": None}, root=tmp_path)
    slots = {"pick_of_the_day": _row(caveat=be.POISSON_CAVEAT, odds=-135),
             "longshot_of_the_day": None}
    _apply(slots, root=tmp_path, board=_board("Preview"))
    cav = slots["pick_of_the_day"]["caveat"]
    assert cav.startswith(be.POISSON_CAVEAT)
    assert "served from the lock" in cav


def test_the_published_sentence_is_served_back(tmp_path):
    """SERVING THE ROW VERBATIM INCLUDES THE SENTENCE PUBLISHED WITH IT. The
    lock used to overwrite `pick_reason` with its own policy on every later
    build, including a build with nothing to disclose. That string is the
    page's fallback copy for an EMPTY slot (assets/betting.js renders
    `pick_reason` under "Nothing qualifies today"), so the caching policy could
    print where the selection rule belongs.

    MUTATION: replace `base` with SLOT_LOCK_POLICY. Both halves fail."""
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
           root=tmp_path, pick_reason="the published sentence")
    # A quiet re-run: the published sentence, and only it.
    reason, _ = _apply({"pick_of_the_day": _row(),
                        "longshot_of_the_day": None},
                       root=tmp_path, pick_reason="a later sentence")
    assert reason == "the published sentence"
    # A build whose board moved: the published sentence, then the disclosure.
    reason, _ = _apply({"pick_of_the_day": _row(odds=-135),
                        "longshot_of_the_day": None},
                       root=tmp_path, pick_reason="a later sentence")
    assert reason.startswith("the published sentence ")
    assert "served from the lock" in reason
    assert be.SLOT_LOCK_POLICY not in reason


def test_the_slot_block_describes_the_row_it_serves(tmp_path):
    """`pick_meta.slots[<slot>]` used to read `present: True` beside a reason,
    a floor and a basis belonging to THIS build's refused selection: on a
    `no_longer_selected` build the block said nothing cleared the floor next to
    a row that was on the page."""
    meta = {"slots": {s: {"slot": s, "present": True, "reason": "published",
                          "min_edge": 0.06, "provisional": True,
                          "basis": "provisional_policy_floor"}
                      for s in be.SLOT_LABELS}}
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
           meta, root=tmp_path)
    later = {"slots": {s: {"slot": s, "present": False, "reason": "nothing "
                           "cleared the floor", "min_edge": 0.09,
                           "provisional": False, "basis": "swept"}
                       for s in be.SLOT_LABELS}}
    _apply({"pick_of_the_day": None, "longshot_of_the_day": None},
           later, root=tmp_path)
    sm = later["slots"]["pick_of_the_day"]
    assert sm["present"] is True
    assert sm["reason"] == "published"
    assert sm["min_edge"] == 0.06
    assert sm["basis"] == "provisional_policy_floor"
    # And this build's own answer is kept, under a name that says whose it is.
    assert sm["current_board"]["reason"] == "nothing cleared the floor"
    assert sm["current_board"]["min_edge"] == 0.09


def test_a_failed_lock_write_is_not_a_publication(tmp_path, monkeypatch):
    """A FAILED WRITE MAY NOT CLAIM A PUBLICATION. The slot was stamped
    `locked: true` with a timestamp before the write was attempted, so a slate
    with no lock file on disk reported itself as published: the one fact this
    store exists to hold, asserted off a file that does not exist."""
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(be, "_save_slot_lock", boom)
    meta = _meta()
    _, state = _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
                      meta, root=tmp_path)
    assert state["created"] == []
    assert state["error"]
    sm = meta["slots"]["pick_of_the_day"]
    assert sm["locked"] is False
    assert sm["published_at"] is None
    assert "unpublished" in sm["lock_note"]
    assert not list(tmp_path.glob("*.json"))


def test_the_state_reports_a_serve_and_a_publication_together(tmp_path):
    """A build that serves one slot and publishes the other used to report
    only the serve, so the night the longshot was first published read as a
    night on which nothing happened."""
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
           root=tmp_path)
    long_row = _row(slot="longshot_of_the_day", game_pk=824141,
                    market="moneyline", side="away", point=None, label="SEA",
                    odds=260)
    _, state = _apply({"pick_of_the_day": _row(),
                       "longshot_of_the_day": long_row}, root=tmp_path)
    assert state["served_from_lock"] == ["pick_of_the_day"]
    assert state["created"] == ["longshot_of_the_day"]
    assert "served from the lock: pick_of_the_day" in state["reason"]
    assert "locked longshot_of_the_day" in state["reason"]


# ---------------------------------------------------------------------------
# R4-1a: who may create a lock, and which locks are read
# ---------------------------------------------------------------------------
def test_a_build_that_named_its_slate_serves_a_lock_and_mints_none(tmp_path):
    """THE CLI CANNOT MINT A PUBLICATION. `python betting_export.py --date
    2026-09-05` defaults to write=True, and the store is first-write-wins, so
    an ad-hoc back-dated run would permanently become that night's published
    claim. Serving an existing lock on such a build stays correct.

    MUTATION: default `may_lock` to True in `build`. The first half fails."""
    meta = _meta()
    _, state = _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
                      meta, root=tmp_path, may_lock=False)
    assert state["created"] == []
    assert not list(tmp_path.glob("*.json"))
    assert meta["slots"]["pick_of_the_day"]["locked"] is False
    assert "named its slate explicitly" in state["reason"]
    # The same build SERVES what is already published.
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
           root=tmp_path)
    slots = {"pick_of_the_day": _row(odds=-135), "longshot_of_the_day": None}
    _, state = _apply(slots, root=tmp_path, may_lock=False)
    assert state["served_from_lock"] == ["pick_of_the_day"]
    assert slots["pick_of_the_day"]["odds"] == -150


def test_a_lock_this_run_did_not_write_is_ignored_under_pytest(tmp_path):
    """TEST ISOLATION MAY NOT DEPEND ON PRODUCTION CACHE STATE. conftest
    mirrors the whole of `.cache/betting/` into the per-session directory, so
    the night after this lands every test that builds today's slate would
    inherit the box's REAL published row and assert against a publication it
    never made. Under pytest a lock is a fact only if this run created it.

    MUTATION: drop the `_lock_written_here` check. The planted row is served
    and the first assertion fails."""
    planted = {"schema": be.SLOT_LOCK_SCHEMA, "slate_date": DAY,
               "policy": be.SLOT_LOCK_POLICY,
               "slots": {"pick_of_the_day": {
                   "published_at": "2026-09-17T00:00:00Z",
                   "model_version": "someone-elses",
                   "row": _row(label="NOT OURS", odds=-900)}}}
    p = tmp_path / f"{DAY}.json"
    p.write_text(json.dumps(planted), encoding="utf-8")
    assert be.load_slot_lock(DAY, root=tmp_path)["slots"] == {}
    slots = {"pick_of_the_day": _row(), "longshot_of_the_day": None}
    _apply(slots, root=tmp_path)
    assert slots["pick_of_the_day"]["label"] == "TEX +1.5"
    # A lock THIS run wrote is read back exactly as before.
    assert be.load_slot_lock(DAY, root=tmp_path)["slots"]
    # AND THE PLANTED ROW DOES NOT SURVIVE THE WRITE. The save is a
    # read-modify-write, so a merge with the foreign file would hand the
    # planted row straight back on the next build of the same run: the test
    # would pass on a dev checkout and fail on the box the nightly runs on.
    later = {"pick_of_the_day": _row(), "longshot_of_the_day": None}
    _, state = _apply(later, root=tmp_path)
    assert state["served_from_lock"] == ["pick_of_the_day"]
    assert later["pick_of_the_day"]["label"] == "TEX +1.5"
    assert later["pick_of_the_day"]["odds"] == -150


def test_a_lock_in_an_unknown_schema_is_neither_served_nor_overwritten(tmp_path):
    """SLOT_LOCK_SCHEMA exists so a later field can be added without a reader
    guessing, and the reader has to actually check it. A schema-2 file read
    under schema-1 rules would serve a row under rules it was not written by;
    replacing it would destroy a publication fact.

    MUTATION: drop the schema check in `load_slot_lock`. The file is then read
    blindly and the second assertion fails."""
    _apply({"pick_of_the_day": _row(), "longshot_of_the_day": None},
           root=tmp_path)
    p = tmp_path / f"{DAY}.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["schema"] = 2
    doc["slots"]["pick_of_the_day"]["row"]["label"] = "FROM THE FUTURE"
    p.write_text(json.dumps(doc), encoding="utf-8")
    slots = {"pick_of_the_day": _row(), "longshot_of_the_day": None}
    _, state = _apply(slots, root=tmp_path)
    assert state["unreadable_schema"] == 2
    assert slots["pick_of_the_day"]["label"] == "TEX +1.5"
    assert state["created"] == []
    assert "schema 2" in state["reason"]
    # The file is exactly as it was: the publication fact is not destroyed.
    assert json.loads(p.read_text(encoding="utf-8"))["schema"] == 2
    assert (json.loads(p.read_text(encoding="utf-8"))
            ["slots"]["pick_of_the_day"]["row"]["label"]) == "FROM THE FUTURE"


# ---------------------------------------------------------------------------
# R4-1a: the two-build test at the level the runbook names it
# ---------------------------------------------------------------------------
@pytest.fixture
def _no_artifact_writes(monkeypatch):
    """`build(write=True)` without any of its data/ writes.

    The lock itself is NOT stubbed: `published_slots_dir()` resolves into the
    per-session cache mirror, which is the seam under test."""
    monkeypatch.setattr(be, "_write", lambda *a, **k: None)
    monkeypatch.setattr(be, "render_record", lambda *a, **k: None)
    monkeypatch.setattr(be, "ensure_record_log", lambda *a, **k: None)
    monkeypatch.setattr(be, "append_record",
                        lambda *a, **k: pytest.fail("wrote the public record"))


def test_two_builds_of_one_slate_through_build_itself(_no_artifact_writes,
                                                      monkeypatch):
    """THE TEST docs/diamond-betting.md 5i NAMES, at the level it names it:
    build a slate, change one input so the slot would move, build again, and
    read what `build` served.

    Every other test here calls `apply_slot_lock` directly. This one exercises
    the ORDERING: the lock sits above the payload, so the props re-ordering,
    the shadow slot tagging, the public record and the preview slice all have
    to read the locked rows rather than the fresh selection.

    Skipped when the box has no cached slate to price, which is a checkout
    without an odds cache and not a defect."""
    first = be.build(write=True)
    if not first.get("pick_of_the_day"):
        pytest.skip("no slot was published on this box's cached slate")
    published = first["pick_of_the_day"]
    # THE FIRST BUILD MOVES NOTHING. It publishes the row it selected, exactly
    # as it selected it: the lock adds to `pick_meta` and to its own block and
    # touches no field of the served row.
    assert first["slot_lock"]["created"] == ["pick_of_the_day"]
    assert "locked" not in published
    assert "since_published" not in published
    assert first["pick_meta"]["slots"]["pick_of_the_day"]["locked"] is True

    real = be.provisional_picks

    def moved(*a, **k):
        slots, reason, meta = real(*a, **k)
        p = slots.get("pick_of_the_day")
        if p:
            slots["pick_of_the_day"] = {**p, "side": "away",
                                        "label": "A DIFFERENT SIDE",
                                        "odds": 175, "edge": 0.4}
        return slots, "a second build's sentence", meta

    monkeypatch.setattr(be, "provisional_picks", moved)
    second = be.build(write=True)
    assert second["slate_date"] == first["slate_date"]
    served = second["pick_of_the_day"]
    assert second["slot_lock"]["served_from_lock"] == ["pick_of_the_day"]
    assert second["slot_lock"]["created"] == []
    # The published row, verbatim, on every field that is the bet or its price.
    for k in ("game_pk", "market", "side", "point", "label", "book", "odds",
              "edge", "model_prob", "ev_per_unit"):
        assert served.get(k) == published.get(k), k
    assert served["published_at"] == \
        first["pick_meta"]["slots"]["pick_of_the_day"]["published_at"]
    assert served["since_published"]["status"] == "different_side"
    assert served["since_published"]["now_selected"]["label"] == \
        "A DIFFERENT SIDE"
    # The page is told, in the field it renders, and the published sentence is
    # the one that is served.
    assert "served from the lock" in served["caveat"]
    assert second["pick_reason"].startswith(first["pick_reason"])
    assert "a second build's sentence" not in second["pick_reason"]
    # The preview slice reads the payload, so the free tier sees the same row.
    assert second["pick_meta"]["slots"]["pick_of_the_day"]["locked"] is True
    # And the record proposes at most one row per slot for this slate.
    proposed = second["record"].get("publish") or second.get("record_publish")
    if isinstance(proposed, dict):
        assert proposed.get("n_new", 0) <= 1


@pytest.mark.parametrize("status,phrase", [
    ("In Progress", "has started"),
    ("postponed", "called off"),
])
def test_the_game_state_disclosure_reaches_the_page_through_build(
        _no_artifact_writes, monkeypatch, status, phrase):
    """THE SENTENCE THE LOCK EXISTS TO PUBLISH, MEASURED WHERE IT IS SERVED.
    Every other test of it hands `apply_slot_lock` a board by hand. This one
    publishes a slot through `build`, flips that game's schedule row, builds
    again and reads the caveat off the payload.

    IT IS THE TEST THAT CATCHES THE REAL DEFECT. `build` passes the board, and
    a game that has started is not on the board: `is_bettable` removes a Live
    row before the started filter ever runs, and the filter removes a
    called-off one. So the disclosure was unreachable in production while two
    hand-built-board tests passed, and a reader looking at a -175 price on a
    game under way was told the slot would be empty rather than that the price
    could not be taken.

    MUTATION: pass `board=bets` alone into `apply_slot_lock`. The served caveat
    loses its second sentence and both parameters fail.

    Skipped when the box has no cached slate to price."""
    first = be.build(write=True)
    if not first.get("pick_of_the_day"):
        pytest.skip("no slot was published on this box's cached slate")
    pk = first["pick_of_the_day"]["game_pk"]
    real = be._load

    def loaded(name, *a, **k):
        d = real(name, *a, **k)
        if "fantasy" in str(name) and isinstance(d, dict):
            d = json.loads(json.dumps(d))
            for g in ((d.get("schedule") or {}).get("games") or []):
                if g.get("game_pk") == pk:
                    g["status"] = status
        return d

    monkeypatch.setattr(be, "_load", loaded)
    second = be.build(write=True)
    served = second["pick_of_the_day"]
    assert second["slot_lock"]["served_from_lock"] == ["pick_of_the_day"]
    # THE GAME IS GONE FROM THE BOARD, which is the whole difficulty.
    assert pk not in {b.get("game_pk") for b in second["team_bets"]}
    since = served["since_published"]
    assert since["game_status"] == status
    assert since["game_started"] is (status == "In Progress")
    assert since["game_called_off"] is (status == "postponed")
    # `caveat` is the field assets/betting.js renders under the pick card.
    assert phrase in served["caveat"]
    # And the row is still the published one, at the published price.
    assert served["odds"] == first["pick_of_the_day"]["odds"]


# ---------------------------------------------------------------------------
# the record guard, keyed on the payload
# ---------------------------------------------------------------------------
def test_the_slot_is_the_payload_key_not_a_field_on_the_row(open_record):
    """THE GUARD MAY NOT DEPEND ON ANOTHER SEAM HAVING WRITTEN SOMETHING.
    `record_row` copies `slot` off the row it is handed. Production always sets
    it, so keying the refusal on that copy worked until a row arrived without
    it, at which point two Pick of the Day rows land on one slate and
    `n_refused` reads 0.

    MUTATION: go back to `record_row(...)["slot"]`. The record then carries two
    picks for 2026-09-17."""
    bare = _row()
    bare.pop("slot")
    assert be.maybe_publish_record(_payload(bare))["written"] == 1
    assert open_record[0]["slot"] == "pick_of_the_day"
    moved = _row(game_pk=824141, market="moneyline", side="away", point=None,
                 label="SEA", odds=125)
    moved.pop("slot")
    out = be.maybe_publish_record(_payload(moved))
    assert out["written"] == 0
    assert out["n_refused"] == 1
    assert len(open_record) == 1


def test_the_same_bet_in_both_slots_is_named_not_silently_dropped(open_record):
    """Unreachable today: the Pick of the Day's price band and the longshot's
    +260 floor are disjoint. A row that does not reach the record says why
    anyway, because `n_refused: 0` beside a missing row is the reading this
    block exists to prevent."""
    row = _row()
    out = be.maybe_publish_record(_payload(row, dict(row)))
    assert out["written"] == 1
    assert out["n_refused"] == 1
    assert out["refused"][0]["slot"] == "longshot_of_the_day"
    assert "same bet as pick_of_the_day" in out["refused"][0]["reason"]
    assert [r["slot"] for r in open_record] == ["pick_of_the_day"]


# ---------------------------------------------------------------------------
# the pricing basis is a fact about the board
# ---------------------------------------------------------------------------
def test_the_basis_is_read_off_the_board_not_the_caller(tmp_path):
    """THE STAMP IS A FACT, NOT A PROMISE. A default keyword would let an
    intraday pass priced on a posted lineup stamp `constructed` on its rows by
    forgetting an argument; the rows would pool into every sweep and this
    module never backfills, so the contamination would be permanent.

    MUTATION: restore `pricing_basis=PRICING_BASIS_CONSTRUCTED` as the default
    and ignore the payload. The posted rows then read `constructed`."""
    p = tmp_path / "shadow.json"
    out = bs.record_slate(_shadow_payload(bs.PRICING_BASIS_POSTED),
                          min_edge=0.06, include_board_all=True, path=p,
                          slots={})
    assert out["written"] >= 1
    assert out["pricing_basis"] == bs.PRICING_BASIS_POSTED
    rows = bs.load(p)
    assert {bs.pricing_basis_of(r) for r in rows} == {bs.PRICING_BASIS_POSTED}
    assert not any(bs.sweeps_with_served_basis(r) for r in rows)


def test_a_keyword_that_disagrees_with_the_board_raises(tmp_path):
    """One of the two is then wrong about the same board, and a ledger written
    off either is a sample nobody can describe."""
    with pytest.raises(ValueError):
        bs.record_slate(_shadow_payload(bs.PRICING_BASIS_POSTED),
                        min_edge=0.06, pricing_basis=bs.PRICING_BASIS_CONSTRUCTED,
                        path=tmp_path / "shadow.json")
    # A board that states a basis nobody registered is refused too.
    with pytest.raises(ValueError):
        bs.record_slate(_shadow_payload("lineups"), min_edge=0.06,
                        path=tmp_path / "shadow.json")


def test_a_board_that_names_no_basis_leaves_its_rows_unstamped(tmp_path):
    """The honest degrade. Inferring a basis for a board that stated none would
    assert a fact this module never knew, which is exactly what the 323 rows
    written before the stamp existed read as."""
    p = tmp_path / "shadow.json"
    out = bs.record_slate(_shadow_payload(None), min_edge=0.06,
                          include_board_all=True, path=p, slots={})
    assert out["written"] >= 1
    assert out["pricing_basis"] is None
    rows = bs.load(p)
    assert all("pricing_basis" not in r for r in rows)
    assert all(bs.sweeps_with_served_basis(r) for r in rows)


def test_the_build_stamps_the_basis_it_priced_on():
    """The two halves meet on the payload: `build` states the basis and
    `record_slate` reads it. MEASURED on the shipped artifact when there is
    one, so a build that stopped stating it fails here."""
    p = Path(be.OUT_PATH)
    if not p.exists():
        pytest.skip("data/betting.json has not been built in this checkout")
    payload = json.loads(p.read_text(encoding="utf-8"))
    basis = (payload.get("model") or {}).get("pricing_basis")
    if basis is None:
        pytest.skip("this artifact predates the pricing basis stamp")
    assert basis == bs.SERVED_PRICING_BASIS


def test_a_refused_row_is_counted_where_the_clock_reads(tmp_path):
    """A GUARD THAT DROPS IS NOT A GUARD. `_sweep_row` returns None for a row
    of another basis, and a silent `return None` stalls gate 3's per-tag count
    with no reason attached to it.

    MUTATION: drop `n_refused_basis` from the readiness blocks. The clock then
    reports a smaller n and says nothing about why."""
    p = tmp_path / "shadow.json"
    bs.write([_ledger_row(shadow_id="a" * 16,
                          pricing_basis=bs.PRICING_BASIS_CONSTRUCTED),
              _ledger_row(shadow_id="b" * 16, result="lost",
                          pricing_basis=bs.PRICING_BASIS_POSTED),
              _ledger_row(shadow_id="c" * 16, result="won",
                          pricing_basis=bs.PRICING_BASIS_POSTED)], path=p)
    cells = bs.sweep_readiness_by_market_tag(path=p)
    cell = cells["runline"][bs.BOARD_ALL_TAG]
    assert cell["n"] == 1
    assert cell["n_refused_basis"] == 2
    assert cell["refused_bases"] == {bs.PRICING_BASIS_POSTED: 2}
    tag = bs.sweep_readiness(path=p)[bs.BOARD_ALL_TAG]
    assert tag["n"] == 1
    assert tag["n_refused_basis"] == 2
    assert tag["refused_bases"] == {bs.PRICING_BASIS_POSTED: 2}


def test_the_refusal_is_counted_on_the_sample_it_belongs_to(tmp_path):
    """ONE ARTIFACT, ONE QUANTITY, ONE DENOMINATOR (section 5b). Two counts sit
    beside `n` and neither may be measured on a different population than `n`
    is:

      * inside a cell, `sweepable_n` is ONE budget era when the cap split
        applies, so the refusal beside it is that era's; the whole-cell figure
        keeps its own name, `n_refused_basis_cell`.
      * on a tag, `n` is the LARGEST (market, tag) cell since L14-05, so the
        refusal beside it is that cell's; the tag-wide sum is published as
        `n_refused_basis_pooled`, beside `n_pooled`, the count it belongs to.

    MUTATION: sum the tag's cells into `n_refused_basis`, or take the cell's
    refusals over both eras. Each half of this fails.

    ev_rank is the tag whose cells split, and moneyline is deliberately NOT the
    tag's largest cell here, so a pooled sum and the right cell differ."""
    p = tmp_path / "shadow.json"
    old, new = "2026-09-01", "2026-09-10"   # either side of BUDGET_SPLIT_DATE
    rows = []
    # runline|ev_rank: two swept rows in the new era, one refusal in the OLD.
    rows.append(_ledger_row(shadow_id="r1" + "0" * 14, market="runline",
                            slate_date=new, slot="ev_rank", tags=["ev_rank"]))
    rows.append(_ledger_row(shadow_id="r2" + "0" * 14, market="runline",
                            slate_date=new, slot="ev_rank", tags=["ev_rank"],
                            result="lost"))
    rows.append(_ledger_row(shadow_id="r3" + "0" * 14, market="runline",
                            slate_date=old, slot="ev_rank", tags=["ev_rank"],
                            pricing_basis=bs.PRICING_BASIS_POSTED))
    # moneyline|ev_rank: the smaller cell, and the one carrying a NEW-era
    # refusal. A tag-wide sum would put it beside the runline cell's n.
    rows.append(_ledger_row(shadow_id="m1" + "0" * 14, market="moneyline",
                            slate_date=new, slot="ev_rank", tags=["ev_rank"],
                            pricing_basis=bs.PRICING_BASIS_POSTED))
    bs.write(rows, path=p)
    cells = bs.sweep_readiness_by_market_tag(path=p)
    run = cells["runline"]["ev_rank"]
    assert run["era_split"] is True
    assert run["sweepable_n"] == 2
    # The old-era refusal is NOT beside a count that excludes the old era.
    assert run["n_refused_basis"] == 0
    assert run["n_refused_basis_cell"] == 1
    tag = bs.sweep_readiness(path=p)["ev_rank"]
    assert tag["n"] == 2 and tag["largest_cell"] == "runline|ev_rank"
    assert tag["n_refused_basis"] == 0
    assert tag["refused_bases"] == {}
    # The tag-wide sum is published, under the name that says its scope.
    assert tag["n_refused_basis_pooled"] == 2
    assert "n_refused_basis" in tag["basis"]


def test_todays_ledger_refuses_nothing(tmp_path):
    """MEASURED. One basis has ever written to this ledger, so the refusal
    counts are zero on every cell: this repair takes no row out of any sweep
    that is running today. Skipped where the ledger is absent."""
    if not bs.load():
        pytest.skip("no shadow ledger on this box")
    assert bs.basis_refusals(bs.load()) == {}
    for tag in bs.sweep_readiness().values():
        assert tag["n_refused_basis"] == 0
