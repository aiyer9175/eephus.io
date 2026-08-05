# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Card Market guards (/cards/ - card_prices_ingest + card_market_export).

FOUR THINGS THIS FILE EXISTS TO PIN, in the order they matter:

  1. THE STORE IS IMMUTABLE AND IDEMPOTENT. Re-ingesting the same drop file
     stores nothing new and rewrites nothing. If that ever stops being true,
     the local comp store stops being a durable record and the module's whole
     posture (store raw forever, publish derived only) is gone.

  2. NO RAW COMP REACHES THE PAYLOAD. Not a price, not a sale date, not a
     listing title, not a listing id. The owner decision that allowed scraping
     was conditional on exactly this, so it is asserted structurally (banned
     keys anywhere in the document) AND numerically (no stored comp price is
     published as a value).

  3. THE INDEX ARITHMETIC IS WHAT THE DOCS SAY. The trimmed median is checked
     against a hand-computed fixture with independent constants, not against a
     re-implementation of the same expression.

  4. IDENTITY GOES THROUGH bulk_resolve_ids. Never resolve_mlbam_id: the
     single-player path poisons a negative-id cache on a miss (the 2026-08-03
     draft-class outage). The resolver is stubbed, so nothing here touches a
     network.

Every test runs against a temp SQLite file and in-memory fixtures. Nothing
scrapes, nothing writes into data/, nothing reads the live DB.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

import card_market_export as cme
import card_prices_ingest as ci

ROOT = Path(__file__).parent


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def con(tmp_path):
    """A throwaway DB with the card schema. Passed explicitly to every call so
    no test can reach the real prospects.db."""
    c = sqlite3.connect(tmp_path / "cards.db")
    c.row_factory = sqlite3.Row
    c.executescript(ci.SCHEMA)
    yield c
    c.close()


@pytest.fixture()
def watchlist():
    return {
        "version": 1,
        "generated_at": "2026-08-05T00:00:00Z",
        "cards": [
            {"card_id": "alpha-one|bowman-chrome-prospect-auto|psa-10",
             "player_key": "alpha_one", "player_name": "Alpha One", "mlbam": 111,
             "org": "MIL", "tier": "prospect", "eta": 2027,
             "set_desc": "Bowman Chrome Prospect Auto", "grade_bucket": "PSA 10", "hot": True},
            {"card_id": "beta-two|bowman-chrome-prospect-auto|psa-10",
             "player_key": "beta_two", "player_name": "Beta Two", "mlbam": 222,
             "org": "BOS", "tier": "prospect", "eta": 2028,
             "set_desc": "Bowman Chrome Prospect Auto", "grade_bucket": "PSA 10", "hot": False},
            {"card_id": "gamma-three|bowman-chrome-prospect-auto|psa-10",
             "player_key": "gamma_three", "player_name": "Gamma Three",
             "org": "NYY", "tier": "prospect", "eta": 2029,
             "set_desc": "Bowman Chrome Prospect Auto", "grade_bucket": "PSA 10", "hot": False},
        ],
    }


@pytest.fixture()
def xfv():
    def rec(q, star, bust, surplus, kind="active"):
        return {"side": "H", "kind": kind, "xfv_grade": q, "xfv_grade_quantile": q,
                "p_bucket": {"star": star, "bust": bust}, "p_bust": bust,
                "surplus_mm": surplus}
    return {"by_player": {
        "alpha_one": rec(60.0, 0.20, 0.30, 90.0),
        "beta_two": rec(50.0, 0.05, 0.55, 30.0),
        "gamma_three": rec(45.0, 0.02, 0.70, 10.0),
    }}


def _drop(tmp_path, rows, name="card_comps_2026-08-05.csv"):
    """Write a drop CSV. Built here rather than committed as a fixture file on
    purpose: *.csv is gitignored repo-wide, and a committed file of sale prices
    is precisely what this module refuses to create."""
    p = tmp_path / name
    lines = ["card_id,player_key,set,grade,sold_date,price,title,listing_id"]
    for r in rows:
        lines.append(",".join([
            r["card_id"], r.get("player_key", ""), r.get("set", "Bowman Chrome Prospect Auto"),
            r["grade"], r["sold_date"], str(r["price"]),
            '"%s"' % r.get("title", "fixture listing"), r.get("listing_id", ""),
        ]))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _comp_rows(card_id, prices, start=date(2026, 8, 1), grade="PSA 10"):
    return [{"card_id": card_id, "player_key": card_id.split("|")[0].replace("-", "_"),
             "grade": grade, "sold_date": (start - timedelta(days=i)).isoformat(),
             "price": p, "listing_id": f"{card_id}-{i}"}
            for i, p in enumerate(prices)]


# ---------------------------------------------------------------------------
# 1. the store is immutable and idempotent
# ---------------------------------------------------------------------------
def test_ingest_stores_comps_and_reingest_is_a_noop(tmp_path, con, watchlist):
    cid = watchlist["cards"][0]["card_id"]
    path = _drop(tmp_path, _comp_rows(cid, [100, 110, 120, 130, 140, 150]))

    first = ci.ingest_csv(path, watchlist, con=con)
    assert first["parsed"] == 6
    assert first["stored"] == 6

    second = ci.ingest_csv(path, watchlist, con=con)
    assert second["parsed"] == 6, "the parser must still see every row"
    assert second["stored"] == 0, "a re-drop must store nothing"
    assert second["duplicates"] == 6

    n = con.execute("SELECT COUNT(*) n FROM card_comps").fetchone()["n"]
    assert n == 6, "the store grew on a duplicate ingest"


def test_reingest_never_rewrites_a_stored_row(tmp_path, con, watchlist):
    """Immutability is stronger than 'no duplicates': the row that is already
    there must come back byte-identical, ingested_at included."""
    cid = watchlist["cards"][0]["card_id"]
    path = _drop(tmp_path, _comp_rows(cid, [100, 110, 120, 130, 140]))
    ci.ingest_csv(path, watchlist, con=con)
    before = [tuple(r) for r in con.execute(
        "SELECT card_id, listing_hash, sold_date, price_usd, grade, ingested_at "
        "FROM card_comps ORDER BY listing_hash")]

    # a second drop that repeats the same sales AND adds one genuinely new one
    extra = {"card_id": cid, "grade": "PSA 10", "sold_date": "2026-07-15",
             "price": 999, "listing_id": "brand-new-sale"}
    path2 = _drop(tmp_path, _comp_rows(cid, [100, 110, 120, 130, 140]) + [extra],
                  name="card_comps_2026-08-06.csv")
    res = ci.ingest_csv(path2, watchlist, con=con)
    assert res["stored"] == 1

    after = [tuple(r) for r in con.execute(
        "SELECT card_id, listing_hash, sold_date, price_usd, grade, ingested_at "
        "FROM card_comps ORDER BY listing_hash")]
    assert all(r in after for r in before), "an existing comp row was rewritten"
    assert len(after) == len(before) + 1


def test_listing_id_makes_two_identical_sales_two_rows(tmp_path, con, watchlist):
    """Two sales at the same price on the same day are two sales when the source
    numbers them, and one when it does not. Both behaviours are deliberate."""
    cid = watchlist["cards"][0]["card_id"]
    same = [{"card_id": cid, "grade": "PSA 10", "sold_date": "2026-08-01",
             "price": 500, "listing_id": lid} for lid in ("A", "B")]
    ci.ingest_csv(_drop(tmp_path, same), watchlist, con=con)
    assert con.execute("SELECT COUNT(*) n FROM card_comps").fetchone()["n"] == 2

    anon = [{"card_id": cid, "grade": "PSA 10", "sold_date": "2026-07-01",
             "price": 400, "title": "same title"} for _ in range(2)]
    ci.ingest_csv(_drop(tmp_path, anon, name="card_comps_2026-08-07.csv"), watchlist, con=con)
    assert con.execute(
        "SELECT COUNT(*) n FROM card_comps WHERE price_usd = 400").fetchone()["n"] == 1


def test_unparseable_rows_are_dropped_not_guessed(tmp_path, con, watchlist):
    cid = watchlist["cards"][0]["card_id"]
    p = tmp_path / "card_comps_2026-08-08.csv"
    p.write_text(
        "card_id,grade,sold_date,price\n"
        f"{cid},PSA 10,2026-08-01,150\n"
        f"{cid},PSA 10,not-a-date,150\n"
        f"{cid},PSA 10,2026-08-02,\n"
        f"{cid},PSA 10,2026-08-03,free\n", encoding="utf-8")
    res = ci.ingest_csv(p, watchlist, con=con)
    assert res["parsed"] == 1
    prices = [r["price_usd"] for r in con.execute("SELECT price_usd FROM card_comps")]
    assert prices == [150.0], "a bad row became a zero instead of being dropped"


# ---------------------------------------------------------------------------
# 2. no raw comp reaches the payload
# ---------------------------------------------------------------------------
BANNED_KEYS = {"comps", "raw_comps", "listings", "listing", "listing_hash", "listing_id",
               "sold_date", "sold_dates", "price_usd", "prices", "title", "titles",
               "seller", "url", "source_url", "item_id"}


def _walk_keys(obj, path="$"):
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in BANNED_KEYS:
                hits.append(f"{path}.{k}")
            hits += _walk_keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits += _walk_keys(v, f"{path}[{i}]")
    return hits


def test_payload_carries_screen_true_and_no_raw_comps(tmp_path, con, watchlist, xfv):
    cid = watchlist["cards"][0]["card_id"]
    rows = _comp_rows(cid, [101.11, 202.22, 303.33, 404.44, 505.55, 606.66, 707.77])
    ci.ingest_csv(_drop(tmp_path, rows), watchlist, con=con)

    comps = ci.load_comps([c["card_id"] for c in watchlist["cards"]], con=con)
    payload = cme.build_payload(watchlist, comps, xfv, None, as_of=date(2026, 8, 5))

    assert payload["screen"] is True
    assert payload["meta"]["raw_comps_published"] is False
    assert _walk_keys(payload) == [], "a raw-comp field reached the payload"

    # and no stored price is published as a value anywhere in the document
    stored = {round(float(r["price_usd"]), 2)
              for r in con.execute("SELECT price_usd FROM card_comps")}
    published = set()

    def _vals(o):
        if isinstance(o, dict):
            for v in o.values():
                _vals(v)
        elif isinstance(o, list):
            for v in o:
                _vals(v)
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            published.add(round(float(o), 2))
    _vals(payload)
    assert not (stored & published), (
        f"a stored comp price is published verbatim: {sorted(stored & published)}")


def test_load_comps_drops_the_local_only_fields(tmp_path, con, watchlist):
    cid = watchlist["cards"][0]["card_id"]
    ci.ingest_csv(_drop(tmp_path, _comp_rows(cid, [10, 20, 30, 40, 50])), watchlist, con=con)
    comps = ci.load_comps([cid], con=con)
    for c in comps[cid]:
        assert set(c) == {"sold_date", "price_usd", "grade"}, (
            "load_comps is the seam that keeps titles and hashes out of the model; "
            "it must not widen")


def test_written_payload_file_has_no_comp_fields(tmp_path, con, watchlist, xfv):
    """The serialized artifact, not just the in-memory dict."""
    cid = watchlist["cards"][1]["card_id"]
    ci.ingest_csv(_drop(tmp_path, _comp_rows(cid, [50, 60, 70, 80, 90, 100])),
                  watchlist, con=con)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "card_watchlist.json").write_text(json.dumps(watchlist), encoding="utf-8")
    (data_dir / "xfv.json").write_text(json.dumps(xfv), encoding="utf-8")

    out = data_dir / "card_market.json"
    cme.export(out_path=out, as_of=date(2026, 8, 5), data_dir=data_dir, con=con)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["screen"] is True
    assert _walk_keys(doc) == []
    assert "fixture listing" not in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 3. the index arithmetic is what the docs say
# ---------------------------------------------------------------------------
def test_trimmed_median_on_a_hand_fixture():
    """Three five-dollar lot sales polluting four real sales.

    Raw median of [5, 5, 5, 100, 101, 102, 103] is 100, so the band is
    [0.20 x 100, 5.00 x 100] = [20, 500]. The three 5s fall out, leaving
    [100, 101, 102, 103]; the median of four is (101 + 102) / 2 = 101.5."""
    assert cme.trimmed_median([5, 5, 5, 100, 101, 102, 103]) == 101.5

    # High side: two absurd sales in a window of six real ones. Raw median of
    # [100, 101, 102, 103, 104, 105, 50000, 60000] is (103 + 104) / 2 = 103.5,
    # band [20.7, 517.5], both big sales drop, median of the six is 102.5.
    assert cme.trimmed_median([100, 101, 102, 103, 104, 105, 50000, 60000]) == 102.5

    assert cme.trimmed_median([]) is None


def test_the_trim_is_by_value_because_a_count_trim_cannot_move_a_median():
    """This is the reason the module does not ship the obvious implementation.

    Symmetric count-trimming leaves the middle order statistics untouched, so a
    'ten percent trimmed median' equals a plain median at every n. The test
    proves it, so nobody re-introduces the decorative version."""
    for xs in ([1, 2, 3, 4, 5, 6, 7], [1, 2, 3, 4, 5, 6, 7, 8],
               [1, 1, 1, 100, 101, 102, 900, 900]):
        n = len(xs)
        s = sorted(xs)
        plain = cme._median(s)
        for k in (1, 2):
            if 2 * k >= n:
                continue
            assert cme._median(s[k:n - k]) == plain

    # the value trim, on the same third fixture, genuinely moves it
    assert cme.trimmed_median([1, 1, 1, 100, 101, 102, 900, 900]) != cme._median(
        [1, 1, 1, 100, 101, 102, 900, 900])


def test_trim_keeps_a_clean_sample_untouched():
    """A window with no junk in it must come back unchanged, or the band is
    quietly editing honest data."""
    clean = [100, 101, 102, 103, 104]
    assert cme.trim(clean) == clean
    assert cme.trimmed_median(clean) == 102


def test_grade_adjustment_moves_a_lower_grade_onto_the_target():
    """A PSA 9 at $420 with factor 0.42 is a $1,000 PSA-10-equivalent."""
    assert cme.grade_adjust(420.0, "PSA 9", "PSA 10") == pytest.approx(1000.0)
    assert cme.grade_adjust(1000.0, "PSA 10", "PSA 10") == pytest.approx(1000.0)
    # an unknown grade is dropped, never assumed
    assert cme.grade_adjust(500.0, "MYSTERY 11", "PSA 10") is None


def test_card_index_needs_min_comps_and_says_why():
    comps = [{"sold_date": "2026-08-01", "price_usd": 100, "grade": "PSA 10"}] * 4
    thin = cme.card_index(comps, "PSA 10", date(2026, 8, 5))
    assert thin["index"] is None
    assert thin["reason"] == "thin"

    none = cme.card_index([], "PSA 10", date(2026, 8, 5))
    assert none["index"] is None and none["reason"] == "no comps"


def test_card_index_end_to_end_arithmetic():
    """Five PSA 10 sales and two PSA 9 sales. The PSA 9s lift to 100/0.42 =
    238.10 and 200/0.42 = 476.19, giving adjusted
    [100, 200, 238.10, 300, 400, 476.19, 500]. The raw median is 300, so the
    band is [60, 1500] and nothing is trimmed; the median of seven is the
    fourth, 300. Published on the grid (nearest $5 between $100 and $1,000)
    that is 300."""
    comps = ([{"sold_date": "2026-08-01", "price_usd": p, "grade": "PSA 10"}
              for p in (100, 200, 300, 400, 500)] +
             [{"sold_date": "2026-08-01", "price_usd": p, "grade": "PSA 9"}
              for p in (100, 200)])
    res = cme.card_index(comps, "PSA 10", date(2026, 8, 5))
    assert res["n"] == 7
    assert res["index_exact"] == pytest.approx(300.0)
    assert res["index"] == 300


def test_index_window_excludes_older_sales():
    old = [{"sold_date": "2026-01-01", "price_usd": 1000, "grade": "PSA 10"}] * 10
    new = [{"sold_date": "2026-08-01", "price_usd": 100, "grade": "PSA 10"}] * 6
    res = cme.card_index(old + new, "PSA 10", date(2026, 8, 5), window_days=45)
    assert res["n"] == 6, "a sale outside the window was counted"
    assert res["index"] == 100


def test_publish_grid_is_coarse_by_design():
    assert cme._publish_round(87.4) == 87
    assert cme._publish_round(312.0) == 310
    assert cme._publish_round(4013.0) == 4025
    assert cme._publish_round(None) is None


def test_talent_score_clones_the_dynasty_blend():
    """Independent arithmetic, not a re-call of the function under test:
    q=60, star=0.20, bust=0.30, surplus=90, eta 2027 with season 2026 ->
    60 + 10(0.20) - 6(0.30) + 4(1 - 0.25*1) + 2(0.90)
    = 60 + 2.0 - 1.8 + 3.0 + 1.8 = 65.0."""
    rec = {"side": "H", "kind": "active", "xfv_grade": 60.0, "xfv_grade_quantile": 60.0,
           "p_bucket": {"star": 0.20, "bust": 0.30}, "p_bust": 0.30, "surplus_mm": 90.0}
    score, efv = cme.talent_score(rec, 2027, season=2026)
    assert score == pytest.approx(65.0)
    assert efv == pytest.approx(60.0)


def test_efv_reads_go_through_the_one_basis():
    """The displayed grade must be efv_board_scale.board_value (via
    fantasy_export._board_grade), not a second basis invented here."""
    import efv_board_scale as ebs
    rec = {"side": "H", "kind": "active", "xfv_grade": 57.3, "xfv_grade_quantile": 44.0}
    _score, efv = cme.talent_score(rec, 2027, season=2026)
    assert efv == pytest.approx(ebs.board_value(rec))
    assert efv != pytest.approx(44.0), "the retired quantile leaked into the display"


def test_percentiles_and_gap_are_within_tier(watchlist, xfv):
    """A prospect's forward eFV and a debuted player's cohort grade are different
    quantities; ranking them together would be the Quantity A/B trap."""
    wl = {"cards": watchlist["cards"] + [
        {"card_id": "vet-one|topps-chrome-rookie-refractor|psa-10",
         "player_key": "vet_one", "player_name": "Vet One", "tier": "mlb",
         "set_desc": "Topps Chrome Rookie Refractor", "grade_bucket": "PSA 10"}]}
    x = {"by_player": dict(xfv["by_player"])}
    x["by_player"]["vet_one"] = {"side": "H", "kind": "debuted", "xfv_grade": 70.0,
                                 "xfv_grade_quantile": 70.0,
                                 "p_bucket": {"star": 0.5, "bust": 0.1}, "surplus_mm": 200.0}
    comps = {}
    for c in wl["cards"]:
        comps[c["card_id"]] = [{"sold_date": "2026-08-01", "price_usd": 100,
                                "grade": "PSA 10"}] * 6
    payload = cme.build_payload(wl, comps, x, None, as_of=date(2026, 8, 5))
    vet = [r for r in payload["cards"] if r["tier"] == "mlb"][0]
    # the only MLB card in the pool: a percentile of one is 50, not 100
    assert vet["talent_pct"] == 50.0
    assert vet["market_pct"] == 50.0
    # the top prospect is still top among prospects despite the 70-grade vet
    pros = [r for r in payload["cards"] if r["tier"] == "prospect"]
    top = max(pros, key=lambda r: r["talent_score"])
    assert top["talent_pct"] == 100.0


def test_signal_bands_are_the_documented_conventions():
    assert cme.signal_for(cme.BUY_GAP) == "buy"
    assert cme.signal_for(cme.BUY_GAP - 0.1) == "hold"
    assert cme.signal_for(cme.FADE_GAP) == "fade"
    assert cme.signal_for(None) == "unpriced"
    note = (cme.METHOD["bands"].get("note") or "").lower()
    assert "not fitted" in note or "conventions" in note, (
        "the payload must say in words that these thresholds are not fitted")


def test_index_history_accumulates_across_exports(tmp_path, con, watchlist, xfv):
    cid = watchlist["cards"][0]["card_id"]
    ci.ingest_csv(_drop(tmp_path, _comp_rows(cid, [100, 110, 120, 130, 140, 150])),
                  watchlist, con=con)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "card_watchlist.json").write_text(json.dumps(watchlist), encoding="utf-8")
    (data_dir / "xfv.json").write_text(json.dumps(xfv), encoding="utf-8")
    out = data_dir / "card_market.json"

    p1 = cme.export(out_path=out, as_of=date(2026, 8, 5), data_dir=data_dir, con=con)
    row1 = [r for r in p1["cards"] if r["card_id"] == cid][0]
    assert len(row1["history"]) == 1, "the first export must publish its own point"

    p2 = cme.export(out_path=out, as_of=date(2026, 8, 6), data_dir=data_dir, con=con)
    row2 = [r for r in p2["cards"] if r["card_id"] == cid][0]
    assert len(row2["history"]) == 2
    assert [h["d"] for h in row2["history"]] == ["2026-08-05", "2026-08-06"]


# ---------------------------------------------------------------------------
# 4. identity through bulk_resolve_ids
# ---------------------------------------------------------------------------
def test_watchlist_identities_resolve_through_bulk_resolve_ids(watchlist):
    """gamma_three has no mlbam. It must be resolved by the BULK path.

    resolve_mlbam_id writes a negative-id cache entry on a miss, and a later
    good lookup then reads the poisoned entry; that defect left a whole draft
    class without stats in 2026-08. The stub proves which entry point is used
    and keeps the test off the network."""
    seen = {}

    def fake_bulk(players, season=None, **kw):
        seen["players"] = list(players)
        return ({"gamma_three": 333}, {}, None)

    got = ci.resolve_identities(watchlist, resolver=fake_bulk)
    assert got == {"gamma_three": 333}
    assert [p[0] for p in seen["players"]] == ["gamma_three"], (
        "only the unresolved keys should be sent to the resolver")
    gamma = [c for c in watchlist["cards"] if c["player_key"] == "gamma_three"][0]
    assert gamma["mlbam"] == 333
    # already-resolved entries are untouched
    assert watchlist["cards"][0]["mlbam"] == 111


def test_ingest_module_never_calls_resolve_mlbam_id():
    """The prose may NAME the banned entry point (it explains why it is banned);
    what must not exist is a CALL to it."""
    src = (ROOT / "card_prices_ingest.py").read_text(encoding="utf-8")
    assert "resolve_mlbam_id(" not in src, (
        "the card lane must resolve identities through bulk_resolve_ids only")
    assert "bulk_resolve_ids" in src


def test_resolver_failure_degrades_quietly(watchlist):
    def boom(players, season=None, **kw):
        raise RuntimeError("network down")
    assert ci.resolve_identities(watchlist, resolver=boom) == {}


# ---------------------------------------------------------------------------
# scraper posture
# ---------------------------------------------------------------------------
def test_scraper_is_off_unless_the_flag_is_set(monkeypatch, watchlist, con):
    monkeypatch.delenv(ci.SCRAPE_ENV_FLAG, raising=False)
    res = ci.scrape_cards(watchlist["cards"], con=con)
    assert res["enabled"] is False and res["stored"] == 0
    assert con.execute("SELECT COUNT(*) n FROM card_comps").fetchone()["n"] == 0


def test_scraper_throttle_floor_cannot_be_lowered():
    calls = []
    t = ci.Throttle(interval=0.001, clock=lambda: 0.0, sleeper=calls.append)
    assert t.interval >= ci.MIN_REQUEST_INTERVAL
    t.wait()
    t.wait()
    assert calls and calls[0] >= ci.MIN_REQUEST_INTERVAL


def test_scrape_parses_a_fixture_and_stores_it(con, watchlist):
    """Fixture HTML only. No test in this file makes a network request."""
    cid = watchlist["cards"][0]["card_id"]
    html = "".join(
        '<li class="s-item"><div class="t">2024 Bowman Chrome Alpha One Auto PSA 10</div>'
        f'<span>${p}.00</span><span>Sold Aug {d}, 2026</span></li>'
        for p, d in ((900, 1), (950, 2), (1000, 3), (1050, 4), (1100, 5), (1150, 6)))
    rows = ci.parse_sold_html(html)
    assert len(rows) == 6
    assert rows[0]["grade"] == "PSA 10"
    assert rows[0]["sold_date"] == "2026-08-01"

    res = ci.scrape_cards([watchlist["cards"][0]], fetch=lambda url: html,
                          throttle=ci.Throttle(clock=lambda: 1e9, sleeper=lambda s: None),
                          con=con)
    assert res["stored"] == 6
    assert con.execute("SELECT COUNT(*) n FROM card_comps WHERE card_id = ?",
                       (cid,)).fetchone()["n"] == 6
    # and again: the same page is the same sales
    res2 = ci.scrape_cards([watchlist["cards"][0]], fetch=lambda url: html,
                           throttle=ci.Throttle(clock=lambda: 1e9, sleeper=lambda s: None),
                           con=con)
    assert res2["stored"] == 0


def test_broken_layout_yields_zero_rows_not_garbage():
    """The designed failure mode: a redesign produces nothing, never a wrong
    price. A block with a price but no sale date is not a sold comp."""
    assert ci.parse_sold_html("<div>totally different markup $1,000</div>") == []
    assert ci.parse_sold_html('<li class="s-item">$1,000 buy it now</li>') == []
    assert ci.parse_sold_html("") == []


# ---------------------------------------------------------------------------
# committed watchlist + payload contract
# ---------------------------------------------------------------------------
def test_committed_watchlist_is_well_formed():
    p = ROOT / "data" / "card_watchlist.json"
    if not p.exists():
        pytest.skip("watchlist not generated in this checkout")
    doc = json.loads(p.read_text(encoding="utf-8"))
    cards = doc["cards"]
    assert 20 <= len(cards) <= 400
    ids = [c["card_id"] for c in cards]
    assert len(ids) == len(set(ids)), "duplicate card_id in the watchlist"
    for c in cards:
        assert c["player_key"] and c["set_desc"] and c["grade_bucket"]
        assert c["card_id"] == ci.card_id(c["player_key"], c["set_desc"], c["grade_bucket"])
        assert c["grade_bucket"] in ci.GRADE_BUCKETS


def test_committed_payload_if_present_is_a_screen_with_no_raw_comps():
    p = ROOT / "data" / "card_market.json"
    if not p.exists():
        pytest.skip("card_market.json not exported in this checkout")
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc.get("screen") is True
    assert _walk_keys(doc) == []


def test_eval_stub_is_a_preregistration_not_a_claim():
    stub = cme.eval_stub({"meta": {"n_cards": 40, "n_priced": 0}, "as_of": "2026-08-05"})
    assert stub["status"] == "screen"
    assert stub["verdict"] == "unvalidated"
    assert stub["pre_registration"]["baselines"], "a gate with no baseline is not a gate"
    assert "zero-information" in " ".join(stub["pre_registration"]["baselines"])
