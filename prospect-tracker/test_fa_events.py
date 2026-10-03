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
    # The option window reads the postseason schedule cache; an empty
    # directory makes every test run on the November 1 fallback.
    import fa_pipeline
    (tmp_path / "ps").mkdir()
    monkeypatch.setattr(fa_pipeline, "POSTSEASON_CACHE_DIR", tmp_path / "ps")
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
    import datetime
    import fa_pipeline
    prior = {
        "opt_in_guy":  _member("opt_in_guy", "Opt In Guy", "pending_option",
                               option_price_usd=12_000_000),
        "opt_out_guy": _member("opt_out_guy", "Opt Out Guy", "pending_option",
                               option_price_usd=15_000_000),
    }
    # Declined: re-listed as a locked UFA. Exercised: gone from the page.
    # as_of inside the Oct-Jan option window (decisions due days after
    # the World Series) - outside it the inference is gated off.
    avail = [_member("opt_out_guy", "Opt Out Guy", "locked")]
    out = fa_pipeline.track_winter_events(YEAR, prior, avail, signed_rows=[],
                                          as_of=datetime.date(YEAR - 1, 11, 5))
    assert out["inserted"] == 2
    types = {e["player_key"]: e["event_type"] for e in fa_db.load_fa_events(YEAR)}
    assert types == {"opt_out_guy": "option_declined", "opt_in_guy": "option_exercised"}


def test_option_inference_gated_outside_winter_window(fa_db):
    """The 2026-06-12 post-mortem pin: a June page restructure dropped
    every pending-option row at once and the disappearance heuristic
    mass-fired 77 false option_exercised events. Outside Oct-Jan the
    option branches must emit NOTHING - a vanished row in June is page
    noise, not an exercise."""
    import datetime
    import fa_pipeline
    prior = {f"opt_{i}": _member(f"opt_{i}", f"Opt {i}", "pending_option")
             for i in range(10)}
    out = fa_pipeline.track_winter_events(
        YEAR, prior, [_member("bystander", "By Stander", "locked")],
        signed_rows=[], as_of=datetime.date(YEAR - 1, 6, 12))
    assert out["inserted"] == 0
    assert fa_db.load_fa_events(YEAR) == []


def test_option_inference_skipped_on_empty_page(fa_db):
    """An empty available page is a scrape failure, not a mass exercise -
    option inference must not run against it even in-window."""
    import datetime
    import fa_pipeline
    prior = {f"opt_{i}": _member(f"opt_{i}", f"Opt {i}", "pending_option")
             for i in range(5)}
    out = fa_pipeline.track_winter_events(YEAR, prior, [], signed_rows=[],
                                          as_of=datetime.date(YEAR - 1, 11, 10))
    assert out["inserted"] == 0
    assert fa_db.load_fa_events(YEAR) == []


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
    # WINDOW GUARD (2026-08-19 penter hardening): qo_offered stamping rides
    # the same Oct-Jan window as option inference, because the August 2026
    # incident showed Spotrac's prior-recipient marker transiently reading as
    # a live offer pre-offseason (16 contaminated rows). This scenario runs
    # at a legitimate in-window date; the out-of-window refusal is pinned in
    # test_fa_penter_guard.py.
    import datetime as _dt
    import fa_pipeline
    in_window = _dt.date(YEAR - 1, 11, 5)
    prior = {"qo_man": _member("qo_man", "Qo Man", "locked")}
    avail = [_member("qo_man", "Qo Man", "locked", qo_offered=True)]
    out = fa_pipeline.track_winter_events(YEAR, prior, avail, signed_rows=[],
                                          as_of=in_window)
    assert out["inserted"] == 1
    assert fa_db.load_fa_events(YEAR)[0]["event_type"] == "qo_offered"
    # Already-offered prior state → no duplicate.
    prior2 = {"qo_man": _member("qo_man", "Qo Man", "locked", qo_offered=True)}
    out2 = fa_pipeline.track_winter_events(YEAR, prior2, avail, signed_rows=[],
                                           as_of=in_window)
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


# ---- HOME_1 (2026-10-02): the window opens the day after the World Series --

def _ws_cache(dirpath, season, *, last_day, finished, fetched_at):
    """A postseason schedule cache in postseason.py's on-disk shape: one World
    Series (gameType W, best of 7). finished=True writes four final wins for
    club 1, the fourth on last_day; finished=False writes two final games."""
    import datetime as _dt
    import json as _json
    end = _dt.date.fromisoformat(last_day)
    n = 4 if finished else 2
    games = []
    for i in range(n):
        day = (end - _dt.timedelta(days=n - 1 - i)).isoformat()
        games.append({"gamePk": 900 + i, "gameType": "W", "gamesInSeries": 7,
                      "officialDate": day, "status": {"codedGameState": "F"},
                      "teams": {"home": {"team": {"id": 1}, "isWinner": True},
                                "away": {"team": {"id": 2}, "isWinner": False}}})
    doc = {"season": season, "fetched_at": fetched_at, "complete": finished,
           "body": {"series": [{"series": {"id": "W_1", "gameType": "W"}, "games": games}]}}
    (dirpath / f"statsapi_postseason_{season}.json").write_text(_json.dumps(doc), encoding="utf-8")


def test_window_opens_the_day_after_the_last_world_series_game(fa_db, tmp_path):
    import datetime as _dt
    import fa_pipeline
    ps = tmp_path / "ps"
    _ws_cache(ps, YEAR - 1, last_day=f"{YEAR - 1}-10-30", finished=True,
              fetched_at=f"{YEAR - 1}-10-31T08:00:00+00:00")
    opens, basis = fa_pipeline.winter_window_opens(YEAR, _dt.date(YEAR - 1, 10, 31))
    assert opens == _dt.date(YEAR - 1, 10, 31) and "2026-10-30" in basis
    assert fa_pipeline.winter_window_open(YEAR, _dt.date(YEAR - 1, 10, 30))[0] is False
    assert fa_pipeline.winter_window_open(YEAR, _dt.date(YEAR - 1, 10, 31))[0] is True
    assert fa_pipeline.winter_window_open(YEAR, _dt.date(YEAR, 1, 31))[0] is True
    assert fa_pipeline.winter_window_open(YEAR, _dt.date(YEAR, 2, 1))[0] is False
    # A future class's winter follows a later World Series: never in window now.
    assert fa_pipeline.winter_window_open(YEAR + 1, _dt.date(YEAR - 1, 11, 15))[0] is False


def test_window_falls_back_to_november_1_when_the_schedule_cannot_answer(fa_db, tmp_path):
    import datetime as _dt
    import fa_pipeline
    ps = tmp_path / "ps"
    # No file on disk: November 1.
    assert fa_pipeline.winter_window_opens(YEAR, _dt.date(YEAR - 1, 10, 2))[0] == _dt.date(YEAR - 1, 11, 1)
    # An unfinished series on a fresh read: not open yet, no date.
    _ws_cache(ps, YEAR - 1, last_day=f"{YEAR - 1}-10-25", finished=False,
              fetched_at=f"{YEAR - 1}-10-26T08:00:00+00:00")
    assert fa_pipeline.winter_window_opens(YEAR, _dt.date(YEAR - 1, 10, 27))[0] is None
    # The same unfinished series read a week ago is a failed read: November 1.
    assert fa_pipeline.winter_window_opens(YEAR, _dt.date(YEAR - 1, 11, 3))[0] == _dt.date(YEAR - 1, 11, 1)


def test_no_option_event_is_stamped_before_the_world_series_ends(fa_db, tmp_path):
    """The 2026-10-02 defect: the window opened on October 1 by month, the
    postseason was in its first round, and a Spotrac re-listing stamped 25
    declines and 7 exercises. Before the World Series ends nothing stamps,
    neither a re-listed row nor a vanished one, nor a QO flag."""
    import datetime as _dt
    import fa_pipeline
    _ws_cache(tmp_path / "ps", YEAR - 1, last_day=f"{YEAR - 1}-10-01", finished=False,
              fetched_at=f"{YEAR - 1}-10-02T08:00:00+00:00")
    prior = {
        "mutual_guy": _member("mutual_guy", "Mutual Guy", "pending_option", option_price_usd=30_000_000),
        "club_guy": _member("club_guy", "Club Guy", "pending_option", option_price_usd=4_000_000),
        "qo_guy": _member("qo_guy", "Qo Guy", "locked"),
    }
    avail = [_member("mutual_guy", "Mutual Guy", "locked"),
             _member("qo_guy", "Qo Guy", "locked", qo_offered=True)]
    out = fa_pipeline.track_winter_events(YEAR, prior, avail, signed_rows=[],
                                          as_of=_dt.date(YEAR - 1, 10, 2))
    assert out["inserted"] == 0
    assert fa_db.load_fa_events(YEAR) == []


def _plant_event(fa_db, key, etype, ev_date, payload):
    import json as _json
    con = sqlite3.connect(fa_db.DB_PATH)
    con.execute("INSERT INTO fa_events (class_year, player_key, event_type, event_date, payload_json)"
                " VALUES (?, ?, ?, ?, ?)", (YEAR, key, etype, ev_date, _json.dumps(payload)))
    con.commit()
    con.close()


def test_a_premature_option_stamp_is_held_then_restamped_in_window(fa_db):
    """Kills: a quarantine that deletes, one that leaves the exercised status
    on the class row, a served view that keeps held rows, and a tracker that
    cannot see a held decline again (the row was re-listed as locked the same
    night, so the stored class row no longer reads pending_option)."""
    import datetime as _dt
    import fa_pipeline
    pay = {"player_name": "Mutual Guy", "position": "SP", "option_price_usd": 30_000_000}
    _plant_event(fa_db, "mutual_guy", "option_declined", f"{YEAR - 1}-10-02", pay)
    _plant_event(fa_db, "club_guy", "option_exercised", f"{YEAR - 1}-10-02",
                 {"player_name": "Club Guy", "position": "SP", "option_price_usd": 4_000_000})
    fa_db.upsert_fa_class_players(YEAR, [_member("mutual_guy", "Mutual Guy", "locked"),
                                         _member("club_guy", "Club Guy", "pending_option")])
    fa_db.set_fa_class_player_status(YEAR, "club_guy", "option_exercised")

    out = fa_pipeline.quarantine_premature_winter_events(YEAR, as_of=_dt.date(YEAR - 1, 10, 2))
    assert out["marked"] == 2 and out["status_restored"] == [f"{YEAR}:club_guy"]
    raw = fa_db.load_fa_events(YEAR)
    assert len(raw) == 2 and all(e["invalidated"] for e in raw)
    assert all(e["event_date"] == f"{YEAR - 1}-10-02" for e in raw)
    assert "World Series" in raw[0]["invalid_reason"]
    assert fa_pipeline.served_fa_events(YEAR) == []
    con = sqlite3.connect(fa_db.DB_PATH)
    st = con.execute("SELECT status FROM fa_class_players WHERE player_key='club_guy'").fetchone()[0]
    con.close()
    assert st == "pending_option"
    again = fa_pipeline.quarantine_premature_winter_events(YEAR, as_of=_dt.date(YEAR - 1, 10, 3))
    assert again["marked"] == 0 and again["already_marked"] == 2

    # In window (the November 1 fallback): the decline is still re-listed and
    # the exercise is still gone, so both re-stamp to the in-window day.
    in_window = _dt.date(YEAR - 1, 11, 4)
    prior = {k: p for (k, _y), p in fa_db.load_fa_class_players(YEAR).items()}
    avail = [_member("mutual_guy", "Mutual Guy", "locked"), _member("bystander", "By Stander", "locked")]
    out = fa_pipeline.track_winter_events(YEAR, prior, avail, signed_rows=[], as_of=in_window)
    assert out["revalidated"] == 2
    ev = {e["player_key"]: e for e in fa_db.load_fa_events(YEAR)}
    for key, etype in (("mutual_guy", "option_declined"), ("club_guy", "option_exercised")):
        assert ev[key]["event_type"] == etype and ev[key]["event_date"] == in_window.isoformat()
        assert not ev[key].get("invalidated")
        assert ev[key]["superseded_invalid_first_seen"] == f"{YEAR - 1}-10-02"
    assert len(fa_pipeline.served_fa_events(YEAR)) == 2
    # And a re-run of the quarantine leaves the in-window stamps alone.
    assert fa_pipeline.quarantine_premature_winter_events(YEAR, as_of=in_window)["marked"] == 0


def test_the_wire_names_the_basis_of_an_option_row(tmp_path, monkeypatch):
    import build_site
    # _collect_events prunes and saves the FV first-seen ledger; keep it off data/.
    monkeypatch.setattr(build_site, "_WIRE_FV_LEDGER", tmp_path / "wire_fv_first_seen.json")
    events = build_site._collect_events([], [], [
        {"date": "2026-11-04", "type": "option_declined", "key": "mutual_guy", "name": "Mutual Guy"},
        {"date": "2026-11-04", "type": "option_exercised", "key": "club_guy", "name": "Club Guy"},
        {"date": "2026-11-20", "type": "signing", "key": "ace", "name": "Ace", "to": "NYY",
         "years": 6, "guar": 210_000_000},
    ])
    feed = build_site._feed_html(events, 12)
    assert feed.count('title="Spotrac status change, first seen 2026-11-04"') == 2
    assert feed.count("Spotrac status change") == 2, "a signing row carries no option basis"
    ticker = build_site._ticker_html(events)
    assert ticker.count('title="Spotrac status change, first seen 2026-11-04"') == 4  # the track is doubled
    news = build_site._news_feed_html(events, {})
    assert news.count('title="Spotrac status change, first seen 2026-11-04"') == 2
