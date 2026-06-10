# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Winter event ledger: first-seen semantics + transition detection.

Spotrac publishes no per-signing dates, so fa_events stamps each
transition the day the pipeline FIRST observes it and never re-dates
it. These tests run track_winter_events against synthetic scrape rows
(signed_rows injected — no network) on a throwaway DB.
"""

from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture()
def fa_db(tmp_path, monkeypatch):
    """Point storage at a throwaway DB with the fa_* schema applied."""
    import storage
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test_fa.db", raising=False)
    # Some storage layouts route through a module-level path constant with a
    # different name — re-resolve via init_db on whatever connect() uses.
    try:
        storage.init_db()
    except sqlite3.OperationalError:
        pytest.skip("storage cannot init on a temp path in this layout")
    yield storage


YEAR = 2027


def _member(key, name, status, **kw):
    return {"player_key": key, "player_name": name, "status": status,
            "position": kw.pop("position", "SP"), **kw}


def test_signing_event_first_seen_is_stable(fa_db):
    import fa_pipeline
    prior = {"ace_starter": _member("ace_starter", "Ace Starter", "locked")}
    avail = [_member("ace_starter", "Ace Starter", "locked")]
    signed = [{"player_key": "ace_starter", "player_name": "Ace Starter",
               "position": "SP", "from_team": "DET", "to_team": "NYY",
               "years": 6, "guarantee_usd": 210_000_000, "aav_usd": 35_000_000,
               "qo": True, "mlb_deal": True}]
    out = fa_pipeline.track_winter_events(YEAR, prior, avail, signed_rows=signed)
    assert out["inserted"] == 1
    ev = fa_db.load_fa_events(YEAR)
    assert len(ev) == 1 and ev[0]["event_type"] == "signing"
    first_date = ev[0]["event_date"]
    assert ev[0]["to_team"] == "NYY" and ev[0]["guarantee_usd"] == 210_000_000

    # Re-observing the same signing later must be a no-op (no re-date).
    out2 = fa_pipeline.track_winter_events(YEAR, prior, avail, signed_rows=signed)
    assert out2["inserted"] == 0
    ev2 = fa_db.load_fa_events(YEAR)
    assert len(ev2) == 1 and ev2[0]["event_date"] == first_date

    # Status reconciled on the class row (column, not payload).
    fa_db.upsert_fa_class_players(YEAR, [_member("ace_starter", "Ace Starter", "locked")])
    fa_pipeline.track_winter_events(YEAR, prior, avail, signed_rows=signed)
    con = sqlite3.connect(fa_db.DB_PATH)
    st = con.execute("SELECT status FROM fa_class_players WHERE player_key='ace_starter'").fetchone()
    assert st[0] == "signed"


def test_option_declined_vs_exercised(fa_db):
    import fa_pipeline
    prior = {
        "opt_in_guy":  _member("opt_in_guy", "Opt In Guy", "pending_option",
                               option_price_usd=12_000_000),
        "opt_out_guy": _member("opt_out_guy", "Opt Out Guy", "pending_option",
                               option_price_usd=15_000_000),
    }
    # Declined: re-listed as a locked UFA. Exercised: gone from the page.
    avail = [_member("opt_out_guy", "Opt Out Guy", "locked")]
    out = fa_pipeline.track_winter_events(YEAR, prior, avail, signed_rows=[])
    assert out["inserted"] == 2
    types = {e["player_key"]: e["event_type"] for e in fa_db.load_fa_events(YEAR)}
    assert types == {"opt_out_guy": "option_declined", "opt_in_guy": "option_exercised"}


def test_pending_player_who_signed_is_not_exercised(fa_db):
    """A pending_option player who leaves the available page BECAUSE he
    signed must produce a signing event, never option_exercised."""
    import fa_pipeline
    prior = {"quick_sign": _member("quick_sign", "Quick Sign", "pending_option")}
    signed = [{"player_key": "quick_sign", "player_name": "Quick Sign",
               "position": "RP", "to_team": "LAD", "years": 1,
               "guarantee_usd": 8_000_000, "aav_usd": 8_000_000, "mlb_deal": True}]
    fa_pipeline.track_winter_events(YEAR, prior, [], signed_rows=signed)
    types = sorted(e["event_type"] for e in fa_db.load_fa_events(YEAR))
    assert types == ["signing"]


def test_qo_offered_fires_once_on_publication(fa_db):
    import fa_pipeline
    prior = {"qo_man": _member("qo_man", "Qo Man", "locked")}
    avail = [_member("qo_man", "Qo Man", "locked", qo_offered=True)]
    out = fa_pipeline.track_winter_events(YEAR, prior, avail, signed_rows=[])
    assert out["inserted"] == 1
    assert fa_db.load_fa_events(YEAR)[0]["event_type"] == "qo_offered"
    # Already-offered prior state → no duplicate.
    prior2 = {"qo_man": _member("qo_man", "Qo Man", "locked", qo_offered=True)}
    out2 = fa_pipeline.track_winter_events(YEAR, prior2, avail, signed_rows=[])
    assert out2["inserted"] == 0


def test_export_events_block_shape():
    """The shipped fa_class.json carries the events block (empty preseason)
    and the tracker fields stay absent until a signing is observed."""
    import json
    from pathlib import Path
    path = Path(__file__).parent / "data" / "fa_class.json"
    if not path.exists():
        pytest.skip("no export on this machine")
    d = json.loads(path.read_text(encoding="utf-8"))
    assert "events" in d and isinstance(d["events"], list)
    assert "n_signed" in d
    for e in d["events"]:
        assert e.get("date") and e.get("type") and e.get("key")
