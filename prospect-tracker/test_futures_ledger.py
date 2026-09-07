# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""A forward record can only start once, and it must not lie while it accrues.

data/futures.json ships this sentence: "These probabilities come from a simulator
with no validated forward record." That stays true forever unless something writes
the record down, because a probability published tonight and overwritten tomorrow
night can never be scored. By the time the season resolves, the only number on disk
is the last one, taken when most of the uncertainty had already gone.

The ledger records. It does NOT score, and this file pins that distinction as hard
as it pins the mechanics: a record that starts describing itself as a result is
worse than no record.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import proj_export as pe

HERE = Path(__file__).parent
LEDGER = HERE / "data" / "futures_ledger.json"


@pytest.fixture()
def board():
    p = HERE / "data" / "futures.json"
    if not p.exists():
        pytest.skip("data/futures.json not built on this machine")
    return json.loads(p.read_text(encoding="utf-8"))


def test_one_entry_per_day_however_many_times_the_box_runs(tmp_path, board):
    """Otherwise the record measures pipeline activity, not forecast accuracy."""
    p = tmp_path / "led.json"
    pe.append_futures_ledger(board, today="2026-09-05", path=p)
    for _ in range(4):
        out = pe.append_futures_ledger(board, today="2026-09-06", path=p)
    assert out["_meta"]["n_entries"] == 2, (
        "a date already present must REPLACE its entry, not add one; a day the "
        "pipeline ran four times would otherwise outweigh a day it ran once"
    )
    assert out["_meta"]["first_as_of"] == "2026-09-05"
    assert out["_meta"]["last_as_of"] == "2026-09-06"


def test_an_empty_board_appends_nothing(tmp_path):
    """build_futures degrades to an empty board on a partial standings read.

    An entry of thirty nulls is not a forecast, and once written it would sit in
    the record forever waiting to be scored against a season it never predicted.
    """
    p = tmp_path / "led.json"
    pe.append_futures_ledger({"clubs": [], "content_hash": None}, today="2026-09-05", path=p)
    out = pe.append_futures_ledger({"clubs": [], "content_hash": None},
                                   today="2026-09-06", path=p)
    assert out["_meta"]["n_entries"] == 0


def test_every_entry_records_what_would_let_it_be_rechecked(tmp_path, board):
    p = tmp_path / "led.json"
    out = pe.append_futures_ledger(board, today="2026-09-06", path=p)
    e = out["entries"][-1]
    for k in ("as_of", "season", "content_hash", "sims", "n_clubs", "resolved", "clubs"):
        assert k in e, f"the entry does not carry {k}, so it cannot be rechecked"
    assert e["content_hash"] == board.get("content_hash")
    assert e["resolved"] is False
    club = e["clubs"][0]
    for m in pe.LEDGER_MARKETS:
        assert m in club, f"{m} is not recorded, so it can never be scored"


def test_the_win_total_is_not_recorded_as_a_probability():
    """It is a count. Mixing it into a Brier over five outrights would be wrong."""
    assert "winTotal" not in pe.LEDGER_MARKETS
    assert "winTotalP10" not in pe.LEDGER_MARKETS


def test_the_ledger_does_not_claim_to_be_a_result(tmp_path, board):
    p = tmp_path / "led.json"
    out = pe.append_futures_ledger(board, today="2026-09-06", path=p)
    meta = out["_meta"]
    assert meta["n_resolved"] == 0
    assert "nothing_here_is_scored" in meta
    assert not any(k.startswith(("brier", "auc", "accuracy", "logloss"))
                   for k in meta), "the ledger has started publishing a score"


def test_the_board_points_at_the_record_without_overclaiming(board):
    led = board.get("ledger")
    if led is None:
        pytest.skip("futures.json predates the ledger block")
    assert led["path"] == "data/futures_ledger.json"
    assert led["n_resolved"] == 0
    assert "Nothing in it is scored yet" in led["what_it_is"]
    # and the disclaimer it was built to eventually retire is still standing
    assert "no validated forward record" in json.dumps(board), (
        "the board dropped its own no-forward-record disclaimer while the ledger "
        "still has nothing scored in it"
    )


def test_the_committed_ledger_is_well_formed():
    if not LEDGER.exists():
        pytest.skip("no ledger on this machine yet")
    d = json.loads(LEDGER.read_text(encoding="utf-8"))
    seen = set()
    for e in d.get("entries") or []:
        key = (e.get("season"), e.get("as_of"))
        assert key not in seen, f"duplicate ledger entry for {key}"
        seen.add(key)
        assert e.get("n_clubs"), "an entry with no clubs was recorded"
    assert d["_meta"]["n_entries"] == len(d.get("entries") or [])

# --------------------------------------------------------------------------
# Where the ledger LIVES, which is the part that already destroyed one of these
# --------------------------------------------------------------------------

def test_the_source_of_truth_is_outside_data():
    """An accruing file in data/ cannot survive a night on the box.

    deploy/nightly-build.sh runs `git checkout -- .` before every pipeline. A
    TRACKED ledger is reverted at 03:10 with every entry the night before added,
    silently: that is what killed the public betting record, and .gitignore says
    so at length. UNTRACKED AND UNIGNORED is worse, because it survives today and
    one `git add -A` arms the tracked failure later. Only `.cache/` escapes the
    checkout AND sits on the backup list in deploy/WEBMASTER.md.

    This ledger landed in exactly the worst state on 2026-09-06 and was moved.
    """
    cache = pe.FUTURES_LEDGER_CACHE
    assert ".cache" in cache.parts, (
        f"the source of truth is {cache}, which `git checkout -- .` will revert "
        f"or a `git add -A` will track; it must live under .cache/"
    )
    assert pe.FUTURES_LEDGER_PATH == cache, (
        "the default path every path-less call resolves to is not the cache copy"
    )
    assert pe.FUTURES_LEDGER_DERIVED.parent.name == "data"


def test_the_derived_copy_is_gitignored():
    gi = (HERE / ".gitignore").read_text(encoding="utf-8")
    assert "data/futures_ledger.json" in gi, (
        "the derived copy is not ignored, so it is untracked AND unignored, the "
        "state .gitignore itself calls the worst of the three"
    )


def test_both_copies_are_written_and_agree(tmp_path, board, monkeypatch):
    cache = tmp_path / ".cache" / "futures" / "ledger.json"
    derived = tmp_path / "data" / "futures_ledger.json"
    monkeypatch.setattr(pe, "FUTURES_LEDGER_CACHE", cache)
    monkeypatch.setattr(pe, "FUTURES_LEDGER_DERIVED", derived)
    pe.append_futures_ledger(board, today="2026-09-06", path=cache)
    assert cache.exists() and derived.exists()
    assert json.loads(cache.read_text(encoding="utf-8")) ==         json.loads(derived.read_text(encoding="utf-8")), (
        "the published copy disagrees with the source of truth")


def test_a_pre_seam_ledger_in_data_is_adopted_not_discarded(tmp_path, board, monkeypatch):
    """A box that already accrued entries under the old path keeps them.

    Otherwise moving the file restarts the clock at zero and silently throws away
    however many days had been logged, which is the same loss the move exists to
    prevent.
    """
    cache = tmp_path / ".cache" / "futures" / "ledger.json"
    derived = tmp_path / "data" / "futures_ledger.json"
    monkeypatch.setattr(pe, "FUTURES_LEDGER_CACHE", cache)
    monkeypatch.setattr(pe, "FUTURES_LEDGER_DERIVED", derived)
    # a ledger written before the seam existed: only the data/ copy is on disk
    pe.append_futures_ledger(board, today="2026-09-01", path=derived)
    assert not cache.exists()
    out = pe.append_futures_ledger(board, today="2026-09-06", path=cache)
    assert out["_meta"]["n_entries"] == 2, (
        "the pre-seam entry was dropped, restarting the forward record at zero")
    assert out["_meta"]["first_as_of"] == "2026-09-01"
