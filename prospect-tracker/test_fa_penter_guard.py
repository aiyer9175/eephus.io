# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""fa_penter winter-shakedown guards (post-mortem 2026-08-12).

Pins the four behaviors that make the Oct-Jan shakedown trustworthy:
qo_offered stamping is gated to the Oct-Jan window, out-of-window rows
quarantine in place (never deleted), the served view excludes quarantined
rows, and a genuine in-window observation re-stamps a quarantined row to
its first VALID date. Synthetic rows on a throwaway DB; no network.

Every test names the mutation it kills, per the mutation-noted rule.
"""

from __future__ import annotations

import datetime
import json
import sqlite3

import pytest


@pytest.fixture()
def fa_db(tmp_path, monkeypatch):
    """Point storage at a throwaway DB with the fa_* schema applied."""
    import storage
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test_fa.db", raising=False)
    try:
        storage.init_db()
    except sqlite3.OperationalError:
        pytest.skip("storage cannot init on a temp path in this layout")
    yield storage


YEAR = 2027
IN_WINDOW = datetime.date(YEAR - 1, 11, 5)     # QOs due ~5 days post-WS
OUT_WINDOW = datetime.date(YEAR - 1, 8, 12)    # the defect's actual date


def _member(key, name, status="locked", **kw):
    return {"player_key": key, "player_name": name, "status": status,
            "position": kw.pop("position", "SP"), **kw}


def _plant_out_of_window_qo(fa_db, key, name, ev_date="2026-08-12"):
    """Reproduce a pre-guard row: qo_offered first-seen out of window.
    Written with explicit SQL because the guarded pipeline can no longer
    produce one (which is the point)."""
    con = sqlite3.connect(fa_db.DB_PATH)
    con.execute(
        "INSERT INTO fa_events (class_year, player_key, event_type,"
        " event_date, payload_json) VALUES (?, ?, 'qo_offered', ?, ?)",
        (YEAR, key, ev_date,
         json.dumps({"player_name": name, "position": "SP"})))
    con.commit()
    con.close()


def test_qo_offered_gated_outside_window(fa_db):
    """Kills: removing the option_window condition from the qo block.
    A qo-flag flip observed in August must stamp NOTHING (the 2026-08-12
    defect fired 16 prior-winter flags as fresh offers)."""
    import fa_pipeline
    prior = {"flagged_vet": _member("flagged_vet", "Flagged Vet")}
    avail = [_member("flagged_vet", "Flagged Vet", qo_offered=True)]
    out = fa_pipeline.track_winter_events(YEAR, prior, avail, signed_rows=[],
                                          as_of=OUT_WINDOW)
    assert out["inserted"] == 0
    assert fa_db.load_fa_events(YEAR) == []


def test_qo_offered_fires_inside_window(fa_db):
    """Kills: inverting or over-widening the gate (a guard that also
    blocks November would blind the tracker to every real QO)."""
    import fa_pipeline
    prior = {"real_qo": _member("real_qo", "Real Qo")}
    avail = [_member("real_qo", "Real Qo", qo_offered=True)]
    out = fa_pipeline.track_winter_events(YEAR, prior, avail, signed_rows=[],
                                          as_of=IN_WINDOW)
    assert out["inserted"] == 1
    ev = fa_db.load_fa_events(YEAR)
    assert len(ev) == 1 and ev[0]["event_type"] == "qo_offered"
    # storage.insert_fa_events_first_seen stamps with SQLite date('now'),
    # which is UTC; asserting the LOCAL date here flip-flopped by hour of
    # day (caught 2026-08-19 at 20:xx local when UTC had rolled to 08-20).
    assert ev[0]["event_date"] == (
        datetime.datetime.now(datetime.timezone.utc).date().isoformat())


def test_quarantine_marks_without_deleting(fa_db):
    """Kills: DELETE instead of UPDATE in the quarantine; dropping the
    reason field; breaking idempotence. Rows must survive with
    invalidated + invalid_reason set, and a second run must mark 0."""
    import fa_pipeline
    _plant_out_of_window_qo(fa_db, "aug_ghost", "Aug Ghost")
    out = fa_pipeline.quarantine_out_of_window_qo_events(YEAR)
    assert out == {"marked": 1, "already_marked": 0}
    ev = fa_db.load_fa_events(YEAR)
    assert len(ev) == 1                       # never deleted
    assert ev[0]["invalidated"] is True
    assert "Oct-Jan" in ev[0]["invalid_reason"]
    assert ev[0]["event_date"] == "2026-08-12"   # first-seen date untouched
    again = fa_pipeline.quarantine_out_of_window_qo_events(YEAR)
    assert again == {"marked": 0, "already_marked": 1}


def test_quarantine_leaves_in_window_rows_alone(fa_db):
    """Kills: a month check that quarantines valid winter rows (January
    is month 1 and must count as IN window)."""
    import fa_pipeline
    _plant_out_of_window_qo(fa_db, "jan_legit", "Jan Legit",
                            ev_date=f"{YEAR}-01-10")
    out = fa_pipeline.quarantine_out_of_window_qo_events(YEAR)
    assert out == {"marked": 0, "already_marked": 0}
    assert not fa_db.load_fa_events(YEAR)[0].get("invalidated")


def test_served_view_excludes_quarantined_rows(fa_db):
    """Kills: dropping the invalidated filter from served_fa_events. The
    served block (fa_class.json events, homepage wire) must not carry a
    quarantined row while the raw ledger still does."""
    import fa_pipeline
    _plant_out_of_window_qo(fa_db, "aug_ghost", "Aug Ghost")
    fa_pipeline.quarantine_out_of_window_qo_events(YEAR)
    assert len(fa_db.load_fa_events(YEAR)) == 1
    assert fa_pipeline.served_fa_events(YEAR) == []


def test_genuine_window_observation_revalidates(fa_db):
    """Kills: dropping the revalidation call (INSERT OR IGNORE would pin
    the winter's real QO to the quarantined August date forever) and
    kills clearing the audit trail (superseded date must be kept)."""
    import fa_pipeline
    _plant_out_of_window_qo(fa_db, "flagged_vet", "Flagged Vet")
    fa_pipeline.quarantine_out_of_window_qo_events(YEAR)
    prior = {"flagged_vet": _member("flagged_vet", "Flagged Vet")}
    avail = [_member("flagged_vet", "Flagged Vet", qo_offered=True)]
    out = fa_pipeline.track_winter_events(YEAR, prior, avail, signed_rows=[],
                                          as_of=IN_WINDOW)
    assert out["revalidated"] == 1
    ev = fa_db.load_fa_events(YEAR)
    assert len(ev) == 1
    assert ev[0]["event_date"] == IN_WINDOW.isoformat()
    assert not ev[0].get("invalidated")
    assert ev[0]["superseded_invalid_first_seen"] == "2026-08-12"
    assert fa_pipeline.served_fa_events(YEAR) == ev


def test_revalidation_never_touches_valid_rows(fa_db):
    """Kills: a revalidation that re-dates NON-quarantined rows (that
    would break the first-seen-never-drifts invariant of the ledger)."""
    import fa_pipeline
    prior = {"real_qo": _member("real_qo", "Real Qo")}
    avail = [_member("real_qo", "Real Qo", qo_offered=True)]
    fa_pipeline.track_winter_events(YEAR, prior, avail, signed_rows=[],
                                    as_of=IN_WINDOW)
    first = fa_db.load_fa_events(YEAR)[0]["event_date"]
    out = fa_pipeline.track_winter_events(YEAR, prior, avail, signed_rows=[],
                                          as_of=datetime.date(YEAR - 1, 12, 2))
    assert out["inserted"] == 0 and out["revalidated"] == 0
    ev = fa_db.load_fa_events(YEAR)
    assert len(ev) == 1 and ev[0]["event_date"] == first
    assert "superseded_invalid_first_seen" not in ev[0]
