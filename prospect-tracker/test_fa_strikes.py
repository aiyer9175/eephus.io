# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Spotrac contract-page strike parser (owner answer M14-4, fa_strikes.py).

Pinned here: the parser reads an option season's salary (club, player, mutual)
and an opt-out's remaining guarantee off the contract-breakdown table and its
note row; it never prices a season that is not an option; a row keeps a known
strike (the AVAILABLE page's, else the previous run's) when the page yields
none; every strike carries its source; network reads are budgeted and spaced;
the page cache keeps a week; and the served board names each strike's source.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

import fa_strikes as fs

HERE = Path(__file__).parent

_HEAD = ('<table class="table table-white premium contract-breakdown"><thead><tr>'
         '<th>Year</th><th></th><th>Age</th><th>YOS</th><th>Status</th>'
         '<th>Payroll<span class="info2">Annual</span></th><th>Luxury Tax</th></tr></thead><tbody>')


def _row(year, status_html, pay):
    return (f'<tr><td class="text-left">\n  {year}  \n<a href="#"></a></td><td><img src="x.png"></td>'
            f'<td>30</td><td>-</td><td class="text-center">{status_html}</td>'
            f'<td class="highlight"> {pay} </td><td>{pay}</td></tr>')


def _page(*rows):
    return "<html><body>" + _HEAD + "".join(rows) + "</tbody></table></body></html>"


CLUB = _page(_row(2026, "", "$5,750,000"),
             _row(2027, '<div class="option option-club">Club</div>', "$20,000,000"),
             '<tr><td>2028</td><td></td><td>32</td><td>-</td><td><div class="option option-ufa">UFA</div></td></tr>')
OPT_OUT = _page(_row(2026, "", "$42,000,000"),
                '<tr><td colspan="11">PLAYER OPT-OUT:    AVAILABLE \n <strong>2027</strong>, 2 YR, '
                '$84,000,000 REMAINING</td></tr>',
                _row(2027, '<div class="option option-early-termination">Opt-Out</div>', "$42,000,000"),
                _row(2028, '<div class="option option-player">Player</div>', "$42,000,000"))


def test_a_club_option_strike_is_the_option_season_salary():
    got = fs.parse_contract_page(CLUB, 2027)
    assert got == {"strike_usd": 20_000_000, "strike_type": "club_option",
                   "strike_type_raw": "Club", "strike_basis": "option_year_salary"}


def test_an_opt_out_strike_is_the_remaining_guarantee_from_the_note_row():
    got = fs.parse_contract_page(OPT_OUT, 2027)
    assert got["strike_usd"] == 84_000_000 and got["strike_type"] == "opt_out"
    assert got["strike_basis"] == "remaining_guarantee" and got["remaining_years"] == 2
    # The next season on the same page is a player option, priced on salary.
    assert fs.parse_contract_page(OPT_OUT, 2028)["strike_type"] == "player_option"


def test_no_strike_is_invented():
    assert fs.parse_contract_page(CLUB, 2026) is None            # not an option season
    assert fs.parse_contract_page(CLUB, 2028) is None            # UFA
    assert fs.parse_contract_page(CLUB, 2031) is None            # no such season
    assert fs.parse_contract_page("<html>no table</html>", 2027) is None
    no_note = _page(_row(2027, '<div class="option option-early-termination">Opt-Out</div>',
                         "$42,000,000"))
    assert fs.parse_contract_page(no_note, 2027) is None         # opt-out needs its note
    blank = _page(_row(2027, '<div class="option option-club">Club</div>', "-"))
    assert fs.parse_contract_page(blank, 2027) is None


def test_the_label_text_types_a_season_whose_class_is_unknown():
    page = _page(_row(2027, '<div class="option option-new">Mutual</div>', "$6,000,000"))
    assert fs.parse_contract_page(page, 2027)["strike_type"] == "mutual_option"
    arb = _page(_row(2027, '<div class="option option-arbitration-3-bypassed-player">ARB 3</div>',
                     "$6,000,000"))
    assert fs.parse_contract_page(arb, 2027) is None


class _Fetch:
    """A fake scrapers._fetch: pages by spotrac id, a network read unless cached."""

    def __init__(self, pages, cached=()):
        self.pages, self.cached, self.calls = pages, set(cached), []

    def __call__(self, url, key, force=False):
        self.calls.append(key)
        sid = key.rsplit("_", 1)[1]
        body = self.pages.get(sid)
        return SimpleNamespace(body=body or "", status=200 if body else 404,
                               from_cache=sid in self.cached)


def _rows():
    return [
        {"player_key": "a", "fa_type": "club_option", "spotrac_id": "1", "spotrac_slug": "a"},
        {"player_key": "b", "fa_type": "opt_out", "spotrac_id": "2", "spotrac_slug": "b"},
        {"player_key": "c", "fa_type": "player_option", "spotrac_id": "3",
         "option_price_usd": 9_000_000},
        {"player_key": "d", "fa_type": "club_option", "spotrac_id": "4"},
        {"player_key": "e", "fa_type": "club_option", "spotrac_id": "5"},
        {"player_key": "f", "fa_type": "ufa", "spotrac_id": "6"},
        {"player_key": "g", "fa_type": "opt_out", "spotrac_id": "7"},
    ]


def test_each_row_gets_a_strike_and_its_source_or_none(monkeypatch):
    monkeypatch.setattr(fs, "_page_as_of", lambda key: "2026-10-08")
    fetch = _Fetch({"1": CLUB, "2": OPT_OUT, "7": CLUB})
    prior = {"d": {"option_price_usd": 7_000_000, "fa_type": "club_option",
                   "strike_src": fs.SRC_CONTRACT_PAGE, "strike_as_of": "2026-10-01",
                   "strike_url": "u"},
             "e": {"option_price_usd": 7_000_000, "fa_type": "player_option"}}
    rows = _rows()
    counts = fs.attach_strikes(rows, 2027, prior, fetch=fetch, sleep=lambda s: None)
    by = {r["player_key"]: r for r in rows}
    assert by["a"]["option_price_usd"] == 20_000_000
    assert by["a"]["strike_src"] == fs.SRC_CONTRACT_PAGE and by["a"]["strike_as_of"] == "2026-10-08"
    assert by["a"]["strike_url"].endswith("/id/1/a")
    assert by["b"]["option_price_usd"] == 84_000_000 and by["b"]["strike_basis"] == "remaining_guarantee"
    # the page has nothing: the AVAILABLE page's own strike is kept
    assert by["c"]["option_price_usd"] == 9_000_000 and by["c"]["strike_src"] == fs.SRC_AVAILABLE_PAGE
    # nothing new: the previous run's strike (same type) is kept with its provenance
    assert by["d"]["option_price_usd"] == 7_000_000 and by["d"]["strike_src"] == fs.SRC_KEPT_PRIOR
    assert by["d"]["strike_as_of"] == "2026-10-01"
    # a prior strike of another option type is not this option's strike
    assert by["e"]["option_price_usd"] is None and "strike_src" not in by["e"]
    # a UFA row is never touched
    assert "option_price_usd" not in by["f"] and "6" not in "".join(fetch.calls)
    # an opt-out row against a page whose season is a club option: units differ
    assert by["g"]["option_price_usd"] is None
    assert counts["basis_mismatch"] == 1
    assert counts[fs.SRC_CONTRACT_PAGE] == 2 and counts[fs.SRC_AVAILABLE_PAGE] == 1
    assert counts[fs.SRC_KEPT_PRIOR] == 1 and counts["none"] == 2


def test_network_reads_are_budgeted_and_spaced(monkeypatch):
    monkeypatch.setattr(fs, "_page_as_of", lambda key: None)
    monkeypatch.setattr(fs, "_is_cached", lambda key: key == "spotrac_player_3")
    waits = []
    fetch = _Fetch({"1": CLUB, "2": OPT_OUT, "3": CLUB}, cached={"3"})
    rows = (_rows()[:2] + [{"player_key": "x", "fa_type": "club_option", "spotrac_id": "9"}]
            + [_rows()[2]])
    fs.attach_strikes(rows, 2027, {}, fetch=fetch, sleep=waits.append, max_fetches=2)
    # two network reads spent the budget, so the third uncached page is never
    # requested; the cached page is still read, and without a wait
    assert fetch.calls == ["spotrac_player_1", "spotrac_player_2", "spotrac_player_3"]
    assert len(waits) == 1 and 0 < waits[0] <= fs.STRIKE_FETCH_SPACING_S


def test_a_stored_contract_strike_is_kept_not_relabelled(monkeypatch):
    """restrike_stored hands attach_strikes the stored rows: a strike an earlier
    run read off the contract page stays that strike, under kept_prior_run with
    its first provenance, when the page now yields nothing."""
    monkeypatch.setattr(fs, "_page_as_of", lambda key: None)
    old = {"player_key": "a", "fa_type": "club_option", "spotrac_id": "1",
           "option_price_usd": 20_000_000, "strike_src": fs.SRC_CONTRACT_PAGE,
           "strike_as_of": "2026-10-08", "strike_url": "u", "strike_basis": "option_year_salary"}
    avail = {"player_key": "c", "fa_type": "club_option", "spotrac_id": "3",
             "option_price_usd": 4_000_000, "strike_src": fs.SRC_AVAILABLE_PAGE,
             "strike_as_of": "2026-10-02"}
    rows = [dict(old), dict(avail)]
    fs.attach_strikes(rows, 2027, {"a": old, "c": avail}, fetch=_Fetch({}), sleep=lambda s: None)
    assert rows[0]["option_price_usd"] == 20_000_000 and rows[0]["strike_src"] == fs.SRC_KEPT_PRIOR
    assert rows[0]["strike_as_of"] == "2026-10-08" and rows[0]["strike_url"] == "u"
    assert rows[1]["strike_src"] == fs.SRC_AVAILABLE_PAGE and rows[1]["strike_as_of"] == "2026-10-02"


def test_contract_pages_keep_a_week():
    import scrapers
    assert scrapers._cache_ttl_for_key("spotrac_player_20008") == 7 * 24 * 3600


def test_restrike_updates_payloads_and_leaves_fetched_at(monkeypatch, tmp_path):
    import storage
    db = tmp_path / "t.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE fa_class_players (player_key TEXT, class_year INT, mlbam_id INT, "
                "position TEXT, status TEXT, payload_json TEXT, fetched_at TEXT)")
    rows = [{"player_key": "a", "fa_type": "club_option", "status": "pending_option",
             "spotrac_id": "1", "spotrac_slug": "a"},
            {"player_key": "z", "fa_type": "ufa", "status": "locked"}]
    for r in rows:
        con.execute("INSERT INTO fa_class_players VALUES (?, 2027, NULL, NULL, ?, ?, '2026-10-02')",
                    (r["player_key"], r["status"], json.dumps(r)))
    con.commit()
    con.close()
    monkeypatch.setattr(storage, "connect", lambda: sqlite3.connect(db))
    monkeypatch.setattr(storage, "load_fa_class_players", lambda cy: {
        (k, cy): json.loads(p) for k, p in sqlite3.connect(db).execute(
            "SELECT player_key, payload_json FROM fa_class_players WHERE class_year = ?", (cy,))})
    monkeypatch.setattr(fs, "_page_as_of", lambda key: "2026-10-08")
    import fa_class
    monkeypatch.setattr(fa_class, "exercise_probability",
                        lambda r: {"enter_prob": 0.5, "method": "fixture"})
    out = fs.restrike_stored(2027, fetch=_Fetch({"1": CLUB}), sleep=lambda s: None)
    assert out["rows_updated"] == 1
    got = dict(sqlite3.connect(db).execute(
        "SELECT player_key, payload_json FROM fa_class_players").fetchall())
    a = json.loads(got["a"])
    assert a["option_price_usd"] == 20_000_000 and a["strike_src"] == fs.SRC_CONTRACT_PAGE
    assert a["enter_prob"] == 0.5 and a["enter_prob_method"] == "fixture"
    assert json.loads(got["z"]) == rows[1]
    stamps = {r[0] for r in sqlite3.connect(db).execute("SELECT fetched_at FROM fa_class_players")}
    assert stamps == {"2026-10-02"}


def test_the_served_board_names_each_strike_source():
    p = HERE / "data" / "fa_class.json"
    if not p.exists():
        pytest.skip("fa_class.json not built")
    members = json.loads(p.read_text(encoding="utf-8"))["members"]
    pending = [m for m in members if m.get("status") == "pending_option"]
    if not any(m.get("optPriceSrc") for m in pending):
        pytest.skip("the board on disk predates the strike parser")
    for m in pending:
        if m.get("optPrice"):
            assert m.get("optPriceSrc") in (fs.SRC_CONTRACT_PAGE, fs.SRC_AVAILABLE_PAGE,
                                            fs.SRC_KEPT_PRIOR), m["key"]
            assert m.get("optPriceAsOf"), m["key"]
        else:
            assert "optPriceSrc" not in m, m["key"]
