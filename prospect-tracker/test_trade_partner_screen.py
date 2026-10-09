# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The Trade Machine partner screen v1, built dark (wiring W08, task W08_1).

docs/trademachine-2026-10/TRADE_PARTNER_SCREEN_GATE.md registers the rule
partner_v1 and the frozen record. What is pinned here:
  * the rule reproduces the ranking from the slice: a fixture Franchise board,
    club files and CBT sidecar go through build_slice, and the JS rule
    (_tmPartnerScreen, in a real JS engine) and its Python twin
    (trade_partner_screen.rank_screen) both match an independent reference
    written here with exact fractions, ties and missing inputs included;
  * the twins agree on every distinct player signature of the served data;
  * no cap-space cell: no space, room or capacity key in the slice and no such
    word in the panel;
  * no verdict word in the panel source or on the rendered panel;
  * the frozen output: equal inputs give equal bytes and an equal hash, a
    same-day re-run writes nothing, an earlier day and a changed rule text are
    refused, the chain verifies and an edit is caught, and a stored entry
    replays from its own inputs;
  * the flag: TRADE_PARTNER_SCREEN_LIVE is True since the flip (W08_2,
    2026-10-09): live, the slice and the public chain land under data/ and the
    record under the cache's record/ directory; dark, nothing lands under data/;
    the page shell carries the switch only while the flag is on;
  * the panel renders at 390, 768 and 1440 px in both themes with the flag
    forced on in the harness, with no sideways page scroll.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import gzip
import json
import random
import re
from fractions import Fraction
from pathlib import Path

import pytest

import trade_partner_screen as T

ROOT = Path(__file__).resolve().parent
JS = ROOT / "assets" / "trademachine.js"
CBT_START = "// ---- CBT context (owner answer M27-4"
CBT_END = "// ---- end CBT context"
PANEL_START = "// ---- Trade partner screen panel (wiring W08)"
PANEL_END = "// One-subject card exports go through"
LABEL = "a screen, not a rumor board"
NOW = dt.datetime(2026, 10, 9, 12, 0, tzinfo=dt.timezone.utc)

#: Rumor, verdict and forecast words (gate section 8; the copy rules).
VERDICT_WORDS = re.compile(
    r"\b(rumou?rs?|suitors?|interested|in talks|linked|front-?runners?|favou?rites?|likely|"
    r"landing spots?|best fit|fits?|targets?|buyers?|sellers?|should|will|steals?|overpay|"
    r"underpay|verdicts?|winners?|losers?|ideal|perfect|must|luck|due|regress|trending|sleepers?)\b",
    re.I)
SPACE_WORDS = re.compile(r"\b(space|room|capacity)\b", re.I)
SPACE_KEYS = ("space", "room", "capacity", "projected_payroll", "payroll_forecast")


def _src() -> str:
    return JS.read_text(encoding="utf-8").replace("\r\n", "\n")


def _region(start: str, end: str) -> str:
    s = _src()
    i = s.index(start)
    return s[i:s.index(end, i)]


@pytest.fixture(scope="module")
def ctx():
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    c = MiniRacer()
    c.eval(_region(CBT_START, CBT_END))
    c.eval(T._between(_src(), T.JS_BEGIN, T.JS_END))
    return c


def _js(ctx, sl, player):
    ctx.eval(f"var __SL = {json.dumps(sl)};")
    return json.loads(ctx.eval(f"JSON.stringify(_tmPartnerScreen(__SL, {json.dumps(player)}))"))


# --------------------------------------------------------------------------- #
# a fixture Franchise board, club files and CBT sidecar
# --------------------------------------------------------------------------- #
def _codes() -> list[str]:
    import build_site
    return sorted(r["code"] for r in build_site._club_table()["rows"])


def _rules():
    import fa_cba
    return fa_cba.cbt_tax_rates(), list(fa_cba.cbt_surcharge_tiers())


def _fixture(tmp: Path) -> dict:
    """Thirty clubs with ties and two gaps on purpose; every money figure a
    multiple of $100,000 so the reference's whole-dollar bills are exact."""
    rnd = random.Random(20261009)
    codes = _codes()
    rates, tiers = _rules()
    pos = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]
    clubs, shards, cbt_clubs = [], {}, {}
    raw = {}
    for i, code in enumerate(codes):
        hem = {p: rnd.choice([85, 90, 95, 100, 105, 110]) for p in pos}
        if code == codes[3]:
            hem["SS"] = None
        dem = rnd.choice([95, 98, 100, 102, 105])
        tax = rnd.choice([150, 230, 238, 244, 250, 262, 290, 320]) * 1_000_000 + rnd.randrange(0, 10) * 100_000
        tier = rnd.choice(["Non-Tax", "1st-Time", "2nd-Time", "3+-Time"])
        farm = None if code == codes[7] else rnd.choice([200.0, 350.5, 410.0, 600.0])
        wins = rnd.choice([70.0, 75.5, 81.0, 88.2, 95.0])
        r = {"hem": hem, "dem": dem, "off": rnd.choice([95, 100, 105]),
             "rot": rnd.choice([90, 100, 110]), "bp": rnd.choice([92, 100, 108]),
             "wins": wins, "tax": tax, "tier": tier, "farm": farm,
             "po": rnd.choice([0.0, 0.2, 0.5, 1.0])}
        raw[code] = r
        lineup = [["Avg", f"{code} {p}", "R", hem[p], 300, f"{code}-{p}"] for p in pos if hem[p] is not None]
        align = [[p, f"{code} {p}", 100, 900.0, None, f"{code}-{p}"] for p in pos]
        shards[code] = {"code": code, "sections": {
            "roster": {"offense_plus": r["off"], "rotation_plus": r["rot"], "bullpen_plus": r["bp"],
                       "team_dem_plus": dem, "lineup": lineup, "alignment": align},
            "outlook": {"wins": wins, "by_year": [[2027, wins, 30.0, 1.0, 40], [2028, wins - 3, 20.0, 5.0, 30]]},
            "fin": {"tax_payroll_2027": tax, "payor_2027": {"value": tier, "basis": "fixture"},
                    "space_2027": {"spotrac_usd": 1}},
            "farm": {"farm_surplus_mm": farm},
            "odds": {"playoff_pct": r["po"]},
            "front_office": {"panels": [{"key": "trades", "tags": ["typical"], "window": "2022-present",
                                         "rows": [["volume", "players moved", 150, 0.0, 150, 40]]}]},
        }}
        clubs.append({"code": code, "name": f"Club {code}"})
        cbt_clubs[code] = {"2026": {"tax_payroll_usd": tax, "threshold_usd": 244_000_000, "carry_forward": False,
                                    "tier": tier},
                           "2027": {"tax_payroll_usd": tax, "threshold_usd": 244_000_000, "carry_forward": True,
                                    "tier": tier}}
    d = tmp / "data"
    (d / "franchise_clubs").mkdir(parents=True)
    board = {"generated_at": "2026-10-09T03:00:00+00:00", "season_now": 2026, "class_year": 2027,
             "basis": {}, "clubs": clubs, "codes": codes, "shards": {"dir": "franchise_clubs"}}
    (d / "franchise_board.json").write_text(json.dumps(board), encoding="utf-8")
    for code, sh in shards.items():
        (d / "franchise_clubs" / f"{code}.json").write_text(json.dumps(sh), encoding="utf-8")
    cbt = {"generated_at": "2026-10-09T03:00:00+00:00", "season_now": 2026, "class_year": 2027,
           "calendar": {"2026": {"start": "2026-03-25", "end": "2026-09-27", "days": 187}},
           "rates": rates, "surcharge_tiers_usd": tiers,
           "brackets": {"under": "under the threshold", "base": "base bracket"}, "payor_basis": {},
           "clubs": cbt_clubs}
    (d / "trade_cbt.json").write_text(json.dumps(cbt), encoding="utf-8")
    tv = {"players": [
        {"player_key": "fx_prospect", "mlbam_id": 900001, "player_name": "Fixture Prospect", "position": "SS",
         "org": codes[0], "status": "active", "posterior_surplus_mm": 10.0},
        {"player_key": "fx_of", "mlbam_id": 900002, "player_name": "Fixture Outfielder", "position": "OF",
         "org": codes[1], "status": "active", "posterior_surplus_mm": 5.0},
        {"player_key": "fx_board", "mlbam_id": 900004, "player_name": "Fixture Board Arm", "position": "RP",
         "org": codes[4], "status": "debuted", "posterior_surplus_mm": 3.0}]}
    det = {"players": {"fx_vet": {"name": "Fixture Veteran", "mlbam": 900003, "pos": "SP", "team": codes[2],
                                  "proj": {"surTotal": 50_000_000, "aav": 30_000_000, "thru": 2029,
                                           "salPath": [[2027, 30_000_000, 30_000_000, 30_000_000,
                                                        "signed", "contract", 0]]}}}}
    (d / "trade_values.json").write_text(json.dumps(tv), encoding="utf-8")
    (d / "mlb_player_detail.json").write_text(json.dumps(det), encoding="utf-8")
    return {"dir": d, "raw": raw, "codes": codes, "rates": rates, "tiers": tiers}


def _ref(fx: dict, own: str, slot: str, charge: int) -> list[tuple]:
    """An independent reading of gate 2.3 in exact fractions."""
    import ledger_export as L
    raw, rates, tiers = fx["raw"], fx["rates"], fx["tiers"]
    cands = [c for c in fx["codes"] if c != own]

    def marginal(c):
        r = raw[c]
        b0 = L.computed_cbt_bill(r["tax"], 244_000_000, r["tier"], rates, tiers)["bill_usd"]
        b1 = L.computed_cbt_bill(r["tax"] + charge, 244_000_000, r["tier"], rates, tiers)["bill_usd"]
        return b1 - b0

    def score(val, higher):
        vals = {c: val(c) for c in cands}
        out = {}
        for c in cands:
            if vals[c] is None:
                out[c] = Fraction(1, 2)
                continue
            better = sum(1 for d in cands if vals[d] is not None and (vals[d] > vals[c] if higher else vals[d] < vals[c]))
            equal = sum(1 for d in cands if vals[d] is not None and vals[d] == vals[c])
            rank = Fraction(2 * (1 + better) + equal - 1, 2)
            out[c] = (29 - rank) / 28
        return out
    field = slot in ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF")
    if field:
        a = score(lambda c: raw[c]["hem"][slot], False)
        b = score(lambda c: raw[c]["dem"], False)
        need = {c: (a[c] + b[c]) / 2 for c in cands}
    else:
        k = {"DH": "off", "SP": "rot", "RP": "bp"}[slot]
        need = score(lambda c: raw[c][k], False)
    cont = score(lambda c: raw[c]["wins"], True)
    tax = score(marginal, False)
    pay = score(lambda c: raw[c]["farm"], True)
    rows = [(c, need[c], cont[c], tax[c], pay[c], need[c] + cont[c] + tax[c] + pay[c]) for c in cands]
    rows.sort(key=lambda r: (-r[5], -r[1], -r[2], -r[4], r[0]))
    return rows


@pytest.fixture(scope="module")
def fx(tmp_path_factory):
    return _fixture(tmp_path_factory.mktemp("tps"))


# --------------------------------------------------------------------------- #
# the rule reproduces the ranking from the slice
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("slot,charge", [("SS", 0), ("SP", 30_000_000), ("RP", 4_500_000),
                                         ("DH", 12_300_000), ("C", 0)])
def test_the_rule_reproduces_the_ranking_from_the_slice(ctx, fx, slot, charge):
    sl = T.build_slice("2026-10-09", fx["dir"])
    assert sl["contention"]["key"] == "wins_2027" and sl["tax"]["season"] == 2027
    for own in (fx["codes"][0], fx["codes"][3], fx["codes"][7]):
        ref = _ref(fx, own, slot, charge)
        player = {"slot": slot, "club": own, "cbt_usd": charge}
        py = T.rank_screen(sl, player)
        js = _js(ctx, sl, player)
        for got in (py, js):
            assert got["own"] == own and len(got["rows"]) == 29
            assert [r["club"] for r in got["rows"]] == [r[0] for r in ref]
            for r, e in zip(got["rows"], ref):
                u = r["u"]
                assert [Fraction(u[k], 112) for k in ("need", "contention", "tax", "pay", "score")] == list(e[1:])
            assert got["top"] == [r[0] for r in ref[:5]]


def test_ties_take_the_average_rank_and_a_gap_scores_one_half(fx):
    sl = T.build_slice("2026-10-09", fx["dir"])
    gap_club = fx["codes"][3]          # no HEM+ at SS
    no_farm = fx["codes"][7]           # no farm surplus
    sc = T.rank_screen(sl, {"slot": "SS", "club": fx["codes"][0], "cbt_usd": 0})
    by = {r["club"]: r for r in sc["rows"]}
    assert by[gap_club]["raw"]["need_a"] is None and "need" in by[gap_club]["missing"]
    assert by[no_farm]["u"]["pay"] == 56 and "pay" in by[no_farm]["missing"]
    # A prospect carries no CBT charge: every club ties on tax at 0.5.
    assert {r["u"]["tax"] for r in sc["rows"]} == {56}


def test_the_twins_agree_on_every_player_of_the_served_data(ctx):
    if not (ROOT / "data" / "franchise_board.json").exists() or not (ROOT / "data" / "trade_values.json").exists():
        pytest.skip("served inputs not built on this machine")
    sl = T.build_slice("2026-10-09")
    pls, _ = T.players(sl)
    ctx.eval(f"var __SL = {json.dumps(sl)};")
    seen = {}
    for p in pls:
        seen.setdefault((p["slot"], p["club"], p["cbt_usd"]), p)
    assert len(seen) > 100
    bad = []
    for p in seen.values():
        player = {"slot": p["slot"], "club": p["club"], "cbt_usd": p["cbt_usd"]}
        js = json.loads(ctx.eval(f"JSON.stringify(_tmPartnerScreen(__SL, {json.dumps(player)}))"))
        py = T.rank_screen(sl, player)
        if [(r["club"], r["u"]) for r in js["rows"]] != [(r["club"], r["u"]) for r in py["rows"]]:
            bad.append(player)
    assert not bad, bad[:3]


def test_the_slot_mapping_is_the_trade_machine_classification(ctx):
    cases = {"SS": "SS", "2B/SS": "SS", "CF/LF": "CF", "DH": "DH", "1B/DH": "1B", "SP": "SP",
             "RHP": "SP", "LHP": "SP", "P": "SP", "RP": "RP", "CL": "RP", "SIRP": "RP", "MIRP": "RP",
             "CP": "RP", "OF": None, "INF": None, "TWP": None, "": None}
    for pos, slot in cases.items():
        assert T.partner_slot(pos) == slot, pos
        assert json.loads(ctx.eval(f"JSON.stringify(_tmPartnerSlot({json.dumps(pos)}))")) == slot, pos


def test_the_js_tax_arithmetic_matches_the_python_twin(ctx):
    rates, tiers = _rules()
    for tier in ("Non-Tax", "1st-Time", "2nd-Time", "3+-Time"):
        for before in (200_000_000, 243_900_000, 250_000_000, 266_000_000, 330_000_000):
            for charge, frac in ((0, 1.0), (17_250_000, 1.0), (30_000_000, 58 / 187)):
                fin = {"tax_payroll_2027": before, "payor_2027": tier, "threshold_usd": 244_000_000}
                py = T.partner_tax(fin, 2027, charge, frac, rates, tiers)
                js = json.loads(ctx.eval(
                    f"JSON.stringify(_tmPartnerTax({json.dumps(fin)}, 2027, {charge}, {frac}, "
                    f"{json.dumps(rates)}, {json.dumps(tiers)}))"))
                assert js["marginal"] == py["marginal"] and js["after"] == py["after"], (tier, before, charge)
                assert js["bracketAfter"] == py["bracket_after"]


# --------------------------------------------------------------------------- #
# no cap-space cell, no verdict word
# --------------------------------------------------------------------------- #
def _keys(o, out=None):
    out = [] if out is None else out
    if isinstance(o, dict):
        for k, v in o.items():
            out.append(str(k))
            _keys(v, out)
    elif isinstance(o, list):
        for v in o:
            _keys(v, out)
    return out


def test_no_cap_space_cell_in_the_slice_or_the_panel(fx):
    sl = T.build_slice("2026-10-09", fx["dir"])
    bad = [k for k in _keys(sl) if any(f in k.lower() for f in SPACE_KEYS)]
    assert not bad, bad
    # The fixture's FIN carries space_2027 like the served one; it never reaches the slice.
    assert "space_2027" not in json.dumps(sl)
    panel = _region(PANEL_START, PANEL_END) + T._between(_src(), T.JS_BEGIN, T.JS_END)
    assert "space_" not in panel
    strings = " ".join(re.findall(r"`[^`]*`|\"[^\"]*\"", panel))
    assert not SPACE_WORDS.search(strings), SPACE_WORDS.search(strings)


def test_no_verdict_word_in_the_panel_source():
    panel = _region(PANEL_START, PANEL_END) + T._between(_src(), T.JS_BEGIN, T.JS_END)
    assert panel.count(LABEL) == 1
    text = panel.replace(LABEL, "")
    hits = sorted({m.group(0).lower() for m in VERDICT_WORDS.finditer(text)})
    assert not hits, hits


def test_the_page_label_and_method_are_printed():
    panel = _region(PANEL_START, PANEL_END)
    assert "Trade partner screen" in panel and LABEL in panel
    for bit in ("(29 - rank) / 28", "equal weight", "weight 0", "not on file", "marginal tax",
                "payor tier", "threshold"):
        assert bit in panel, bit


# --------------------------------------------------------------------------- #
# the frozen output (gate 3)
# --------------------------------------------------------------------------- #
def _run(fx, cache: Path, now=NOW, **kw):
    return T.run(now=now, machine="local", live=False, data_dir=fx["dir"], cache_dir=cache,
                 log_fn=lambda *_: None, **kw)


def test_the_frozen_output_hash_is_stable_for_an_unchanged_slice(fx, tmp_path):
    a = _run(fx, tmp_path / "a")
    b = _run(fx, tmp_path / "b")
    assert a["status"] == b["status"] == "written"
    assert a["content_sha256"] == b["content_sha256"]
    pa, pb = Path(a["path"]), Path(b["path"])
    assert pa.read_bytes() == pb.read_bytes()
    raw = gzip.decompress(pa.read_bytes())
    assert T._sha(raw) == a["content_sha256"]
    # gzip header mtime is 0, so equal content gives equal bytes on any day.
    assert pa.read_bytes()[4:8] == b"\x00\x00\x00\x00"
    entry = json.loads(raw)
    h = entry["header"]
    assert h["rule_version"] == "partner_v1" and h["rule_sha256"] == T.rule_sha256()
    assert h["rule_py_sha256"] == T.rule_py_sha256()
    assert h["slice_sha256"] == T._sha(Path(a["slice"]).read_bytes())
    assert T.replay(entry)
    # Three of the four fixture players are screened; the outfielder has no slot.
    assert entry["n_players"] == 3 and h["skipped_players"]["no_slot_by_position"] == {"OF": 1}
    row = next(r for r in entry["players"] if r["key"] == "fx_vet")
    assert row["cbt_usd"] == 30_000_000 and len(row["candidates"]) == 29 and len(row["top5"]) == 5
    assert entry["header"]["candidate_fields"] == ["club", "need", "contention", "tax", "pay", "score"]


def test_first_write_wins_and_no_earlier_day_is_written(fx, tmp_path):
    first = _run(fx, tmp_path)
    before = Path(first["path"]).read_bytes()
    again = _run(fx, tmp_path, now=NOW + dt.timedelta(hours=2))
    assert again["status"] == "exists" and Path(first["path"]).read_bytes() == before
    with pytest.raises(T.ScreenRefusal, match="earlier"):
        _run(fx, tmp_path, now=NOW - dt.timedelta(days=2))
    nxt = _run(fx, tmp_path, now=NOW + dt.timedelta(days=1))
    assert nxt["status"] == "written"
    ch = T.load_chain(Path(first["path"]).parent)
    assert [r["as_of"] for r in ch["rows"]] == ["2026-10-09", "2026-10-10"]
    assert ch["rows"][1]["prev_row_hash"] == ch["rows"][0]["row_hash"]


def test_a_same_day_rerun_re_renders_the_public_chain(fx, tmp_path):
    """Gate 3.2: each run re-renders the public chain. A checkout that lost its
    gitignored copy gets it back from the record on a same-day re-run, and the
    re-run writes no day file."""
    first = _run(fx, tmp_path)
    where = T.paths(False, fx["dir"], tmp_path)
    pub = Path(where["public_chain"])
    want = (Path(where["record"]) / "chain.json").read_bytes()
    pub.unlink()
    day = Path(first["path"]).read_bytes()
    again = _run(fx, tmp_path, now=NOW + dt.timedelta(hours=3))
    assert again["status"] == "exists"
    assert pub.read_bytes() == want and Path(first["path"]).read_bytes() == day


def test_a_changed_rule_text_is_refused_and_an_edited_chain_is_caught(fx, tmp_path):
    first = _run(fx, tmp_path)
    rec = Path(first["path"]).parent
    sl = T.build_slice("2026-10-10", fx["dir"])
    raw = T.slice_bytes(sl)
    pls, sk = T.players(sl, fx["dir"])
    js = _src().replace("const TM_PARTNER_TOP = 5;", "const TM_PARTNER_TOP = 6;")
    entry = T.build_entry(sl, raw, pls, sk, now=NOW + dt.timedelta(days=1), machine="local", js_text=js)
    with pytest.raises(T.ScreenRefusal, match="rule text changed"):
        T.write_day(entry, rec, rec / T.CHAIN_PUBLIC_NAME)
    ch = json.loads((rec / "chain.json").read_text(encoding="utf-8"))
    ch["rows"][0]["content_sha256"] = "0" * 64
    (rec / "chain.json").write_text(json.dumps(ch), encoding="utf-8")
    with pytest.raises(T.ScreenRefusal, match="edited"):
        T.load_chain(rec)


# --------------------------------------------------------------------------- #
# the flag
# --------------------------------------------------------------------------- #
def test_the_flag_is_on_and_live_files_land_where_the_gate_says(fx, tmp_path):
    """W08_2_PARTNER_SCREEN_FLIP: the flag is on; a live run writes the slice and
    trade_partner_screen_chain.json beside the board and freezes the day under
    record/, and the public chain is the record's chain byte for byte."""
    assert T.TRADE_PARTNER_SCREEN_LIVE is True
    res = T.run(now=NOW, machine="local", data_dir=fx["dir"], cache_dir=tmp_path, log_fn=lambda *_: None)
    assert res["live"] is True and res["status"] == "written"
    rec = tmp_path / "trade_partner_screen" / "record"
    assert {p.name for p in rec.iterdir()} == {"2026-10-09.json.gz", "chain.json"}
    assert (fx["dir"] / "trade_partner_slice.json").is_file()
    pub = fx["dir"] / "trade_partner_screen_chain.json"
    assert pub.read_bytes() == (rec / "chain.json").read_bytes()
    assert not (tmp_path / "trade_partner_screen" / "preview").exists()


def test_dark_runs_land_nothing_under_data(fx, tmp_path):
    before = sorted(p.name for p in fx["dir"].rglob("*"))
    res = T.run(now=NOW, machine="local", live=False, data_dir=fx["dir"], cache_dir=tmp_path,
                log_fn=lambda *_: None)
    assert res["live"] is False
    assert sorted(p.name for p in fx["dir"].rglob("*")) == before
    pv = tmp_path / "trade_partner_screen" / "preview"
    assert {p.name for p in pv.iterdir()} == {"2026-10-09.json.gz", "chain.json", T.SLICE_NAME,
                                              T.CHAIN_PUBLIC_NAME}
    live = T.paths(True, fx["dir"], tmp_path)
    assert live["slice"] == fx["dir"] / "trade_partner_slice.json"
    assert live["record"] == tmp_path / "trade_partner_screen" / "record"


def test_the_page_shell_carries_the_switch_only_when_live(monkeypatch):
    import build_site as B
    on = B.build_trademachine()
    assert 'id="proj-view-trademachine" data-tm-partner="live"' in on
    assert 'data-tm-partner="live"' in (ROOT / "trademachine" / "index.html").read_text(encoding="utf-8")
    monkeypatch.setattr(T, "TRADE_PARTNER_SCREEN_LIVE", False)
    off = B.build_trademachine()
    assert "data-tm-partner" not in off
    assert on.replace(' data-tm-partner="live"', "") == off


def test_the_nightly_writes_the_screen_after_the_franchise_board():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    i = src.index("def _export_franchise_board(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert body.index("_fr.write(_frd)") < body.index("_export_trade_partner_screen(log)")
    helper = src[src.index("def _export_trade_partner_screen("):src.index("def _export_fscore(")]
    assert "_tps.run(" in helper
    assert '_record_ingest("trade_partner_screen", True' in helper
    assert '_record_ingest("trade_partner_screen", False' in helper
    import run_monthly
    assert "trade_partner_screen" in run_monthly.SCHEDULED_EXPORTS
    assert run_monthly._ingest_kind("trade_partner_screen") == "export"


# --------------------------------------------------------------------------- #
# render: 390, 768 and 1440 px, both themes, flag forced on in the harness
# --------------------------------------------------------------------------- #
@contextlib.contextmanager
def _live_page(base, width, theme, page_html, slice_raw):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=theme)
            ctx.add_init_script("try{localStorage.setItem('prospect-tracker.theme',%r);}catch(e){}" % theme)
            pg = ctx.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.route("**/trademachine/", lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8",
                                                              body=page_html))
            pg.route("**/data/trade_partner_slice.json*",
                     lambda r: r.fulfill(status=200, content_type="application/json", body=slice_raw))
            pg.goto(base + "trademachine/", wait_until="load", timeout=90_000)
            pg.wait_for_selector(".tm-board-table tbody tr", timeout=90_000)
            yield pg, errors
        finally:
            browser.close()


def _shots_dir(tmp_path: Path) -> Path:
    import os
    d = Path(os.environ.get("TPS_SHOT_DIR") or tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("width", [390, 768, 1440])
def test_the_panel_renders_in_both_themes(monkeypatch, tmp_path, width, theme):
    if not (ROOT / "data" / "trade_values.json").exists() or not (ROOT / "data" / "franchise_board.json").exists():
        pytest.skip("served inputs not built on this machine")
    import build_site as B
    from conftest import serve_site
    monkeypatch.setattr(T, "TRADE_PARTNER_SCREEN_LIVE", True)
    html = B.build_trademachine()
    sl = T.build_slice("2026-10-09")
    raw = T.slice_bytes(sl).decode("utf-8")
    tv = json.loads((ROOT / "data" / "trade_values.json").read_text(encoding="utf-8"))
    pick = next(p for p in tv["players"] if p.get("status") not in ("graduated", "debuted")
                and p.get("posterior_surplus_mm") is not None and T.partner_slot(p.get("position"))
                and T._club_code(p.get("org")) and len(p.get("player_name") or "") > 6)
    with serve_site() as base, _live_page(base, width, theme, html, raw) as (pg, errors):
        inp = pg.locator('input[data-tm-search="a"]')
        inp.click()
        inp.fill(pick["player_name"])
        pg.wait_for_selector('[data-tm-results="a"] .tm-hit:not(.is-unpriced)', timeout=30_000)
        pg.locator('[data-tm-results="a"] .tm-hit:not(.is-unpriced)').first.click()
        pg.wait_for_selector("#tm-partner .tm-partner-table tbody tr", timeout=30_000)
        rows = pg.locator("#tm-partner .tm-partner-table tbody tr")
        assert rows.count() == 30
        assert pg.locator("#tm-partner tr.tm-partner-own").count() == 1
        text = pg.inner_text("#tm-partner")
        assert LABEL in text and "Trade partner screen" in text
        assert not VERDICT_WORDS.search(text.replace(LABEL, "")), VERDICT_WORDS.search(text.replace(LABEL, ""))
        assert not SPACE_WORDS.search(text)
        assert pg.evaluate("document.documentElement.scrollWidth") <= width
        got = pg.evaluate("document.documentElement.getAttribute('data-theme')")
        assert got in (None, theme)
        bg = pg.evaluate("getComputedStyle(document.querySelector('#tm-partner .tm-partner-table thead th')).backgroundColor")
        assert bg and bg != "rgba(0, 0, 0, 0)"
        pg.locator("#tm-partner").scroll_into_view_if_needed()
        pg.locator("#tm-partner").screenshot(path=str(_shots_dir(tmp_path) / f"partner_{width}_{theme}.png"))
        assert not errors, errors
