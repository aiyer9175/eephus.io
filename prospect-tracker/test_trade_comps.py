# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Trade Machine's Comparable real trades panel (wiring W07, owner ask 4, 2026-09-30).

Under the evaluator, the five real deals from the PROSPX Transactions Trade Audit nearest
the deal on the builder, by value moved per side, prospect and MLB mix, positions and
month, each with its value-today and realized-to-date legs. Contract pinned here:

  * the deal list (data/trade_audit_deals.json, trade_audit_export.py) is the audit's own:
    rebuilt with the page's rules, it matches every served audit card party for party,
    value for value and realized WAR for realized WAR;
  * the five comparables reproduce from that list under the rule the panel publishes
    (comps_v1), computed here independently of the page's code;
  * the only verdict words are the shared BALANCED_THRESHOLD_MM band or the club that
    received more; comparables print their time basis (value today plus the realized leg,
    owner answer M9-2) and name every party priced at $0 (M9-1).
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import pytest
from conftest import load_data_doc, serve_site

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import trade_audit_export as tae  # noqa: E402

JS = ROOT / "assets" / "trademachine.js"
PROSPX = ROOT / "prospx" / "index.html"
START = "// ---- Comparable real trades (wiring W07"
END = "// ---- end comparable real trades"
DEALS = "trade_audit_deals.json"
#: Words a comparable must never print: it reads a deal against the band, nothing more.
JUDGEMENT_WORDS = ("won", "winner", "wins", "lost", "loser", "steal", "fleece", "overpa",
                   "underpa", "lopsided", "robbery", "better", "worse", "should", "precedent says",
                   "fair price", "will ")


def _src() -> str:
    return JS.read_text(encoding="utf-8").replace("\r\n", "\n")


def _region() -> str:
    s = _src()
    return s[s.index(START):s.index(END)]


def _band() -> float:
    m = re.findall(r"^const BALANCED_THRESHOLD_MM = ([\d.]+);", _src(), re.M)
    assert len(m) == 1, "the Trade Machine defines its balanced band once"
    return float(m[0])


def _deals_doc():
    doc = load_data_doc(DEALS)
    if not doc or not doc.get("deals"):
        pytest.skip(f"data/{DEALS} not built")
    return doc


@pytest.fixture(scope="module")
def ctx():
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    c = MiniRacer()
    c.eval(f"const BALANCED_THRESHOLD_MM = {_band()};")
    c.eval(_region())
    return c


def _call(ctx, fn, *args):
    return json.loads(ctx.eval(f"JSON.stringify({fn}({', '.join(json.dumps(a) for a in args)}))"))


# ---------------------------------------------------------------------------
# comps_v1, written from the panel's method line (independent of the JS)
# ---------------------------------------------------------------------------
PITCH = {"SP", "RP", "P", "RHP", "LHP", "SHP", "SIRP", "MIRP", "CP", "CL"}


def _feat(mm, parts):
    f = {"mm": float(mm or 0), "p": 0, "m": 0, "hit": 0, "pit": 0}
    for kind, pos in parts:
        f["p" if kind == "P" else "m"] += 1
        t = str(pos or "").split("/")[0].strip().upper()
        if t:
            f["pit" if t in PITCH else "hit"] += 1
    return f


def _s(v, band):
    return math.copysign(1, v) * math.log(1 + abs(v) / band) if v else 0.0


def _side_d(x, y, band):
    return (abs(_s(x["mm"], band) - _s(y["mm"], band))
            + 0.5 * (abs(x["p"] - y["p"]) + abs(x["m"] - y["m"]))
            + 0.25 * (abs(x["hit"] - y["hit"]) + abs(x["pit"] - y["pit"])))


def reference_comps(items_a, items_b, month, doc, n=5):
    band = _band()
    fields = doc["party_fields"]
    A = _feat(sum(i["mm"] for i in items_a), [("P" if i["kind"] == "prospect" else "M", i["pos"]) for i in items_a])
    B = _feat(sum(i["mm"] for i in items_b), [("P" if i["kind"] == "prospect" else "M", i["pos"]) for i in items_b])
    out = []
    for d in doc["deals"]:
        ps = [dict(zip(fields, r)) for r in d["parties"]]
        a = _feat(d["a_mm"], [(p["kind"], p["pos"]) for p in ps if p["side"] == "a"])
        b = _feat(d["b_mm"], [(p["kind"], p["pos"]) for p in ps if p["side"] == "b"])
        ab = _side_d(A, a, band) + _side_d(B, b, band)
        ba = _side_d(A, b, band) + _side_d(B, a, band)
        mo = int(d["date"][5:7])
        gap = abs(month - mo) % 12
        gap = min(gap, 12 - gap)
        out.append((min(ab, ba) + gap / 6, d["date"], d["key"], ba < ab))
    out.sort(key=lambda t: (round(t[0], 6), _neg(t[1]), t[2]))
    return out[:n]


def _neg(s: str):
    return tuple(-ord(c) for c in s)


BUILT = [
    # (Side A items, Side B items, month): a deadline rental for two prospects, a
    # prospect swap, a one-for-one MLB deal in the offseason, an uneven package.
    ([{"kind": "mlb", "pos": "CF", "mm": 58.4}],
     [{"kind": "prospect", "pos": "SS", "mm": 39.5}, {"kind": "prospect", "pos": "CF", "mm": 38.5}], 7),
    ([{"kind": "prospect", "pos": "RHP", "mm": 12.0}], [{"kind": "prospect", "pos": "C", "mm": 9.5}], 12),
    ([{"kind": "mlb", "pos": "SP", "mm": 3.0}], [{"kind": "mlb", "pos": "RP", "mm": -2.0}], 1),
    ([{"kind": "mlb", "pos": "SS", "mm": 140.0}],
     [{"kind": "prospect", "pos": "SP", "mm": 20.0}, {"kind": "prospect", "pos": "3B", "mm": 15.0},
      {"kind": "prospect", "pos": "RP", "mm": 2.0}], 8),
]


# ---------------------------------------------------------------------------
# 1. The rule: the five comparables reproduce from the deal list
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("items_a,items_b,month", BUILT)
def test_the_five_comps_reproduce_from_the_deal_list_under_the_published_rule(ctx, items_a, items_b, month):
    doc = _deals_doc()
    got = _call(ctx, "_tmComps", items_a, items_b, month, doc, 5)
    ref = reference_comps(items_a, items_b, month, doc)
    assert len(got) == 5 == len(ref)
    assert [g["deal"]["key"] for g in got] == [r[2] for r in ref]
    for g, r in zip(got, ref):
        assert g["d"] == pytest.approx(r[0], abs=2e-6)
        assert g["flip"] == r[3]
    assert [g["d"] for g in got] == sorted(g["d"] for g in got)


def test_identical_deal_is_distance_zero_in_either_orientation(ctx):
    doc = _deals_doc()
    fields = doc["party_fields"]
    deal = next(d for d in doc["deals"]
                if {r[2] for r in d["parties"]} == {"a", "b"} and len(d["parties"]) >= 3)
    ps = [dict(zip(fields, r)) for r in deal["parties"]]
    side = lambda s: [{"kind": "prospect" if p["kind"] == "P" else "mlb", "pos": p["pos"],
                       "mm": (p["mm"] or 0) + 0} for p in ps if p["side"] == s]
    a, b = side("a"), side("b")
    # Side totals include the bonus pool and cash; put them on the first party.
    a[0]["mm"] += deal["a_mm"] - sum(x["mm"] for x in a)
    b[0]["mm"] += deal["b_mm"] - sum(x["mm"] for x in b)
    month = int(deal["date"][5:7])
    one = {"deals": [deal], "party_fields": fields}
    assert _call(ctx, "_tmComps", a, b, month, one, 5)[0]["d"] == pytest.approx(0, abs=1e-6)
    flipped = _call(ctx, "_tmComps", b, a, month, one, 5)[0]
    assert flipped["d"] == pytest.approx(0, abs=1e-6) and flipped["flip"] is True


def test_month_gap_wraps_the_year(ctx):
    assert ctx.eval("_tmCompMonthGap(12, 1)") == 1
    assert ctx.eval("_tmCompMonthGap(1, 7)") == 6
    assert ctx.eval("_tmCompMonthGap(7, 8)") == 1


def test_no_comps_until_both_sides_hold_a_player(ctx):
    doc = _deals_doc()
    assert _call(ctx, "_tmComps", [], [{"kind": "mlb", "pos": "C", "mm": 3}], 7, doc, 5) == []
    assert _call(ctx, "_tmComps", [{"kind": "mlb", "pos": "C", "mm": 3}], [], 7, doc, 5) == []


# ---------------------------------------------------------------------------
# 2. Verdict words: the shared band and nothing else
# ---------------------------------------------------------------------------

def test_the_band_is_the_shared_one():
    assert _band() == 5
    m = re.search(r"^const BALANCED_THRESHOLD_MM = ([\d.]+);", PROSPX.read_text(encoding="utf-8"), re.M)
    assert m and float(m.group(1)) == _band(), "the audit and the Trade Machine share one band"
    region = _region()
    assert "BALANCED_THRESHOLD_MM" in region
    assert not re.search(r"Math\.abs\([^)]*\)\s*<\s*\d", region), "no second, hard-coded band"


def test_verdict_words_are_balanced_or_received_more(ctx):
    for net in (-40.2, -5.0, -4.99, 0, 4.99, 5.0, 12.34):
        v = _call(ctx, "_tmCompVerdict", net, "AAA", "BBB")
        if abs(net) < 5:
            assert v == {"kind": "balanced", "text": "Balanced: within $5M"}
        else:
            club = "AAA" if net > 0 else "BBB"
            assert v["text"] == f"{club} received ${abs(net):.1f}M more"
    assert _call(ctx, "_tmCompVerdict", None, "AAA", "BBB") is None


def test_the_panel_code_prints_no_judgement_word():
    s = _src()
    i, j = s.index(START), s.index("function _tmPaintComps()")
    literals = [a or b for a, b in re.findall(r"`([^`]*)`|\"([^\"]*)\"", s[i:j])]
    text = " ".join(literals).lower()
    assert "balanced: within" in text and "received $" in text
    for w in JUDGEMENT_WORDS:
        assert not re.search(r"\b" + re.escape(w.strip()) + r"\b", text), (
            f"the comparables panel prints '{w}'")


def test_the_panel_publishes_its_rule_basis_and_unpriced_parties():
    s = _src()
    body = s[s.index(START):s.index("function _tmPaintComps()")]
    for needle in ("Method (rule ${TM_COMP_RULE}", "s(v) = sign(v) x ln(1 + |v| / $${BALANCED_THRESHOLD_MM}M)",
                   "${TM_COMP_W.mix} per prospect and per MLB player of difference",
                   "${TM_COMP_W.pos} per hitter and per pitcher of difference",
                   "the months between the deal months over 6",
                   "Context, not a price precedent", "not on its deal date",
                   "Realized to date", "Unpriced, valued at $0:", "$0, unpriced"):
        assert needle in body, needle
    assert 'const TM_COMP_W = { mix: 0.5, pos: 0.25, month: 1 / 6 };' in body
    assert 'fetch(DATA_BASE + "trade_audit_deals.json"' in s


# ---------------------------------------------------------------------------
# 3. The deal list: the audit's own rows
# ---------------------------------------------------------------------------

def _jsr(x, k):
    return math.floor(x * k + 0.5) / k


def test_every_deal_adds_up():
    doc = _deals_doc()
    fields = doc["party_fields"]
    dpw = doc["dollars_per_war_mm"]
    assert len(doc["deals"]) == doc["count"] >= tae.MIN_DEALS
    unpriced = 0
    for d in doc["deals"]:
        ps = [dict(zip(fields, r)) for r in d["parties"]]
        for s in ("a", "b"):
            priced = sum(p["mm"] for p in ps if p["side"] == s and p["mm"] is not None)
            assert d[f"{s}_mm"] == pytest.approx(_jsr(priced + d[f"{s}_extra"], 10), abs=0.051), d["key"]
            war = sum(p["rwar"] for p in ps if p["side"] == s)
            assert d[f"rz_{s}_war"] == pytest.approx(war, abs=0.002), d["key"]
            assert d[f"rz_{s}_mm"] == pytest.approx(_jsr(d[f"rz_{s}_war"] * dpw, 10), abs=1e-9)
        assert d["net"] == pytest.approx(_jsr(d["a_mm"] - d["b_mm"], 10), abs=1e-9)
        assert d["a"] != d["b"] and re.match(r"^\d{4}-\d{2}-\d{2}$", d["date"])
        for p in ps:
            assert p["kind"] in ("P", "M")
            if p["mm"] is None:
                unpriced += 1
                assert p["why"], p
    assert unpriced > 0, "the list carries the $0 parties the panel must name"


def test_priced_parties_carry_the_served_trade_value():
    doc = _deals_doc()
    slim = load_data_doc("trade_values_slim.json") or load_data_doc("trade_values.json")
    if not slim:
        pytest.skip("trade values not built")
    assert doc["values_as_of"] == str(slim["generated_at"])[:10], (
        "the deal list was not repriced with the board (tools/export_trade_values.py writes both)")
    by_mlbam: dict[int, set] = {}
    for r in slim["players"]:
        if r.get("mlbam_id") is not None and r.get("trade_value_mm") is not None:
            by_mlbam.setdefault(int(r["mlbam_id"]), set()).add(float(r["trade_value_mm"]))
    fields = doc["party_fields"]
    checked = 0
    for d in doc["deals"]:
        for r in d["parties"]:
            p = dict(zip(fields, r))
            if p["mm"] is not None and p["mlbam"] in by_mlbam:
                assert p["mm"] in by_mlbam[p["mlbam"]], p
                checked += 1
    assert checked > 300


def test_the_served_list_is_a_fresh_build():
    doc = _deals_doc()
    need = [ROOT / "data" / n for n in (tae.TIMESERIES_NAME, tae.DEBUTS_NAME, tae.INACTIVE_NAME)]
    if not all(p.exists() for p in need):
        pytest.skip("the audit's inputs are not on this machine")
    d = ROOT / "data"
    price = tae._read(d / tae.SLIM_NAME if (d / tae.SLIM_NAME).exists() else d / tae.BOARD_NAME)
    rz = tae._read(d / tae.REALIZED_NAME) if (d / tae.REALIZED_NAME).exists() else None
    fresh = tae.build_deals(tae._read(d / tae.TIMESERIES_NAME).get("players") or [],
                            tae._read(d / tae.DEBUTS_NAME), tae._read(d / tae.INACTIVE_NAME), price, rz)
    assert fresh == doc["deals"]


def test_js_string_helpers_match_the_page():
    mr = pytest.importorskip("py_mini_racer")
    src = PROSPX.read_text(encoding="utf-8")
    m = re.search(r"^function _taFold\([^)]*\) \{.*?\n\}\n", src, re.S | re.M)
    h = re.search(r"  const _hashDesc = \(s\) => \{.*?\n  \};\n", src, re.S)
    x = re.search(r"  const _parseTradeExtras = \(desc\) => \{.*?\n  \};\n", src, re.S)
    assert m and h and x
    c = mr.MiniRacer()
    c.eval(m.group(0))
    c.eval(h.group(0).replace("const _hashDesc", "var _hashDesc", 1))
    c.eval(x.group(0).replace("const _parseTradeExtras", "var _parseTradeExtras", 1))
    for s in ("A traded B to C for $500,000 in international bonus pool space and $1.5M cash.",
              "X traded Y to Z for cash considerations.", "Q traded R to S for $2 million in cash.",
              "International bonus pool slot value of $750,000 went the other way.", ""):
        assert tae.parse_extras(s) == json.loads(c.eval(f"JSON.stringify(_parseTradeExtras({json.dumps(s)}))")), s
    # This engine may ship without ICU normalization (the browser has it, and the served
    # card test covers accented names there), so accented folds run only where it works.
    icu = c.eval("String.fromCharCode(233).normalize('NFKD').length") == 2
    for s in ("Jos\u00e9 Sori\u00e1no", "C.J. Abrams", "D'Angelo O\u2019Neil Jr.", "Slater de Brun",
              "  Tampa Bay Rays traded RHP Shane Baz to Baltimore Orioles.  ", "\u00c9mile \u00d8 caf\u00e9"):
        if icu or s.isascii():
            assert tae.fold(s) == c.eval(f"_taFold({json.dumps(s)})"), s
        assert tae._desc_hash(s) == c.eval(f"_hashDesc({json.dumps(s)})"), s
    assert tae.fold("Jos\u00e9 Sori\u00e1no") == "jose_soriano" and tae.fold("C.J. Abrams") == "cj_abrams"


def test_narrative_parsers():
    d = ("Tampa Bay Rays traded RHP Shane Baz to Baltimore Orioles for C Caden Bodine, OF Slater "
         "de Brun, RHP Michael Forret, OF Austin Overn and Draft Pick.")
    assert tae.parse_orgs(d) == ["TBR", "BAL"]
    assert tae.parse_orgs("Oakland Athletics traded LHP X Y to New York Yankees.") == ["ATH", "NYY"]
    assert tae.parse_orgs("Signed by somebody") is None
    # "Slater de Brun" stops at the lowercase particle, as on the page.
    assert tae.extract_names(d) == ["Shane Baz", "Caden Bodine", "Slater", "Michael Forret", "Austin Overn"]
    assert tae.resolve_side(d, "Shane Baz", "TBR", "BAL") == "BAL"
    assert tae.resolve_side(d, "Caden Bodine", "TBR", "BAL") == "TBR"
    assert tae.resolve_side(d, "Nobody", "TBR", "BAL") is None
    x = tae.parse_extras("A traded B to C for $500,000 in international bonus pool space.")
    assert x == {"ibp_mm": 0.5, "cash_mm": 0}


# ---------------------------------------------------------------------------
# 4. The writer and its wiring
# ---------------------------------------------------------------------------

def test_export_refuses_missing_inputs_and_keeps_the_file(tmp_path):
    out = tmp_path / DEALS
    out.write_text("{\"keep\": 1}", encoding="utf-8")
    assert tae.export(out_path=out, data_dir=tmp_path, log=lambda *_: None) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == {"keep": 1}


def test_export_refuses_a_dead_read(tmp_path):
    for name, doc in ((tae.TIMESERIES_NAME, {"players": []}), (tae.DEBUTS_NAME, []),
                      (tae.INACTIVE_NAME, []), (tae.SLIM_NAME, {"generated_at": "g", "players": []})):
        (tmp_path / name).write_text(json.dumps(doc), encoding="utf-8")
    assert tae.export(out_path=tmp_path / DEALS, data_dir=tmp_path, log=lambda *_: None) == 0
    assert not (tmp_path / DEALS).exists()


def test_a_redirected_trade_value_run_never_touches_the_served_list(tmp_path, monkeypatch):
    import bayes_trade_value
    from tools import export_trade_values as etv
    real = ROOT / "data" / DEALS
    before = real.stat().st_mtime_ns if real.exists() else None
    (tmp_path / "timeseries.json").write_text(json.dumps({"players": []}), encoding="utf-8")

    def _fake_export(players, out_path, level_norms=None):
        Path(out_path).write_text(json.dumps({"generated_at": "g", "players": []}), encoding="utf-8")
        return 0
    monkeypatch.setattr(bayes_trade_value, "export_trade_values_json", _fake_export)
    monkeypatch.setattr(bayes_trade_value, "_reset_cache", lambda: None)
    assert etv.main(["--data-dir", str(tmp_path), "--passes", "1"]) == 0
    assert etv.DEALS_NAME == DEALS
    after = real.stat().st_mtime_ns if real.exists() else None
    assert before == after, "a redirected run wrote the served deal list"


def test_both_rebuild_paths_write_the_list_after_its_inputs():
    rm = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    i, j = rm.index("_export_trade_realized(out_path"), rm.index("_export_trade_audit_deals(out_path")
    assert i < j, "rebuild_only writes the deal list after the realized leg"
    etv_src = (ROOT / "tools" / "export_trade_values.py").read_text(encoding="utf-8")
    assert etv_src.index("write_slim_sidecar(out_path") < etv_src.index("trade_audit_export.export(")


def test_catalogued_and_copy_linted():
    import data_catalog
    assert any(r["file"] == DEALS and r["pinned_by"] == "test_trade_comps.py" for r in data_catalog.ARTIFACTS)
    assert '"trade_audit_export.py"' in (ROOT / "tools" / "strip_emdashes.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 5. Served: the audit cards and the panel
# ---------------------------------------------------------------------------

_CARDS = r"""() => [...document.querySelectorAll('.trade-audit-card')].map(c => {
  const lines = [...c.children].filter(d => d.querySelector && d.querySelector('.px-club'));
  const rz = c.querySelector('.ta-realized');
  return {
    net: c.getAttribute('data-ta-net'),
    rza: rz && rz.getAttribute('data-ta-rz-a'), rzb: rz && rz.getAttribute('data-ta-rz-b'),
    sides: lines.map(d => ({ code: ((d.querySelector('.px-club') || {}).innerText || '').trim(),
      chips: [...d.querySelectorAll('[data-ta-kind]')].map(s => {
        const nm = s.querySelector('a') || [...s.children].find(x => x.style && x.style.fontWeight === '600');
        return { name: nm ? nm.innerText : null, mm: s.getAttribute('data-ta-mm'),
                 rwar: s.getAttribute('data-ta-rwar'), mlbam: s.getAttribute('data-ta-mlbam') };
      }) })),
  };
})"""


def _browser(p):
    try:
        return p.chromium.launch(headless=True)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"chromium not installed for playwright: {exc}")


def test_the_list_matches_every_served_audit_card():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    doc = _deals_doc()
    with serve_site() as base, sync_playwright() as p:
        browser = _browser(p)
        page = browser.new_page()
        page.add_init_script("try{localStorage.setItem('prospect-tracker.gate-unlocked','1')}catch(e){}")
        errs: list[str] = []
        page.on("pageerror", lambda err: errs.append(err.message))
        page.goto(base + "prospx/index.html#tab=traded&acq=trade", wait_until="load", timeout=180_000)
        page.wait_for_function(
            "() => typeof DATA !== 'undefined' && DATA && (DATA.inactive || []).length > 0"
            " && (DATA.debuts || []).length > 0", timeout=240_000)
        page.evaluate("() => { state.tradedShowAll = true; renderRecentlyTraded(); }")
        page.wait_for_function(
            "() => { const c = document.querySelectorAll('.trade-audit-card');"
            " return c.length > 5 && ![...c].some(x => x.getAttribute('data-ta-verdict') === 'pending')"
            " && ![...document.querySelectorAll('.ta-realized')].some(z => z.getAttribute('data-ta-rz') !== 'ready'); }",
            timeout=240_000)
        cards = page.evaluate(_CARDS)
        browser.close()
    assert not errs, errs[:3]
    deals = doc["deals"]
    fields = doc["party_fields"]
    assert len(cards) == len(deals), "one deal per served audit card"
    for card, d in zip(cards, deals):
        assert [s["code"] for s in card["sides"]] == [d["a"], d["b"]], d["key"]
        assert float(card["net"]) == pytest.approx(d["net"], abs=1e-9), d["key"]
        assert float(card["rza"]) == pytest.approx(d["rz_a_war"], abs=1e-9)
        assert float(card["rzb"]) == pytest.approx(d["rz_b_war"], abs=1e-9)
        for side, chips in zip(("a", "b"), (s["chips"] for s in card["sides"])):
            mine = [dict(zip(fields, r)) for r in d["parties"] if r[2] == side]
            assert [c["name"] for c in chips] == [m["name"] for m in mine], d["key"]
            for c, m in zip(chips, mine):
                assert float(c["mm"]) == pytest.approx(m["mm"] or 0, abs=1e-9)
                assert float(c["rwar"]) == pytest.approx(m["rwar"], abs=1e-9)
                assert (c["mlbam"] or None) == (str(m["mlbam"]) if m["mlbam"] is not None else None)


def test_the_served_panel_prints_the_reproduced_comps():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    doc = _deals_doc()
    tv = load_data_doc("trade_values.json")
    if not tv:
        pytest.skip("trade values not built")
    wanted = {}
    for r in tv["players"]:
        if r.get("status") == "active" and r.get("posterior_surplus_mm") is not None:
            wanted.setdefault(r["player_name"], r)
    picks = [n for n in wanted if 15 < wanted[n]["posterior_surplus_mm"] < 45
             and sum(1 for x in tv["players"] if x["player_name"] == n) == 1][:3]
    if len(picks) < 3:
        pytest.skip("no three unique mid-value prospects on the board")
    with serve_site() as base, sync_playwright() as p:
        browser = _browser(p)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errs: list[str] = []
        page.on("pageerror", lambda err: errs.append(err.message))
        fetched: list[str] = []
        page.on("request", lambda r: fetched.append(r.url.split("?")[0].rsplit("/", 1)[-1]))
        page.goto(base + "trademachine/", wait_until="load", timeout=120_000)
        page.wait_for_function("() => document.querySelector('#tradeboard-content table')", timeout=120_000)
        assert page.locator("#tm-comps").inner_text().strip() == "", "nothing until both sides hold a player"
        assert DEALS not in fetched, "the deal list is read only once both sides hold a player"
        for side, name in (("a", picks[0]), ("b", picks[1]), ("b", picks[2])):
            inp = page.locator(f'[data-tm-search="{side}"]')
            inp.click()
            inp.fill(name)
            page.wait_for_selector(f'[data-tm-results="{side}"] [data-tm-add]', timeout=60_000)
            page.locator(f'[data-tm-results="{side}"] [data-tm-add]').first.click()
        page.wait_for_selector("#tm-comps .tm-comp", timeout=60_000)
        got = page.evaluate("""() => ({
          month: Number(document.querySelector('#tm-comps [data-tm-comp-month]').value),
          items: [...document.querySelectorAll('#tm-comps .tm-comp')].map(li => ({
            key: li.dataset.tmComp, d: Number(li.dataset.tmCompD), text: li.innerText })),
          text: document.getElementById('tm-comps').innerText })""")
        browser.close()
    assert not errs, errs[:3]
    item = lambda n: {"kind": "prospect", "pos": wanted[n]["position"], "mm": wanted[n]["posterior_surplus_mm"]}
    ref = reference_comps([item(picks[0])], [item(picks[1]), item(picks[2])], got["month"], doc)
    assert [g["key"] for g in got["items"]] == [r[2] for r in ref]
    for g, r in zip(got["items"], ref):
        assert g["d"] == pytest.approx(r[0], abs=2e-6)
    text = got["text"]
    assert "Context, not a price precedent" in text and "not on its deal date" in text
    assert doc["values_as_of"] in text and doc["realized_as_of"] in text
    assert "Method (rule comps_v1" in text
    fields = doc["party_fields"]
    by_key = {d["key"]: d for d in doc["deals"]}
    for g in got["items"]:
        d = by_key[g["key"]]
        assert "value today" in g["text"].lower() and "realized to date" in g["text"].lower()
        for r in d["parties"]:
            p = dict(zip(fields, r))
            if p["mm"] is None:
                assert f"{p['name']} (to " in g["text"], "every $0 party is named"
    low = text.lower()
    for w in JUDGEMENT_WORDS:
        assert not re.search(r"\b" + re.escape(w.strip()) + r"\b", low), w
