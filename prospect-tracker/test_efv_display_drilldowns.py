# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PROSPX's drill-down pages print eFV, and a consensus grade only where it is named.

Owner ask 5 (2026-09-30) named "drilled down detail pages for high schools/countries/
different PROSPX sections". Part 8 lane links_efv_display B.3 (B-DD1 to B-DD8), task Q9_12.

Pinned here:
  * the country page's signee cell is _ifaFvProgHTML with EFV_DISPLAY_SWAPS on (eFV rounded
    to nearest, the consensus grade at signing muted and named), and the old cell with it
    off (so the flag-off page is unchanged in digits);
  * "eFV now" joins promoted_key, then milb_key, to a graded active or debuted eFV entry and
    rounds to nearest;
  * draft_export.DRAFT_CURRENT_FV_EFV is off, assigned only in draft_export.py; off, the
    overperformance fields are what they were (basis "board_fv"); on, current_fv is the eFV
    grade with current_fv_basis "efv" and expected_fv_for_pick / overperf_fv recompute on it;
  * the sentinel regression: with every consensus grade set to 76.4 and every eFV grade to
    33.4 in scratch copies of the drill-down payloads, the high-school, college, country,
    league, draftee and overseas pages print no consensus grade that is not named as one,
    in both flag states, and no eFV rounded up with the flag on.
"""
from __future__ import annotations

import copy
import json
import os
import re
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"


def _src() -> str:
    return PROSPX.read_text(encoding="utf-8")


def js_function(src: str, name: str) -> str:
    m = re.search(r"^(?:async )?function %s\(" % re.escape(name), src, re.M)
    assert m, f"{name} not found in prospx/index.html"
    i = src.index("{", src.index(")", m.end()))
    depth = 0
    for j in range(i, len(src)):
        c = src[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
    raise AssertionError(f"unbalanced braces in {name}")


def js_const(src: str, name: str) -> str:
    m = re.search(r"^const %s = .*?;$" % re.escape(name), src, re.M)
    assert m, f"const {name} not found in prospx/index.html"
    return m.group(0)


_STUBS = r"""
var DATA = {flags: {}};
var _E = {};
function getEfv(p) { return p ? (_E[p.player_key] || null) : null; }
function escapeHtml(s) { return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;"); }
function fvClass(v) { return "fv-" + v; }
"""
_FUNCS = ["fvCeil", "efvDisplaySwaps", "efvBoardValue", "efvGradeDisplay", "_ifaIsEfv", "_ifaIsFloor",
          "_ifaCurLabel", "_ifaSigLabel", "_ifaFvProgHTML", "_countrySigneeFvCell", "_draftEfvNow",
          "_draftEfvNowHTML", "_draftNowIsEfv", "_draftVsSlotTip"]


@pytest.fixture()
def js():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    src = _src()
    ctx = mr.MiniRacer()
    ctx.eval(_STUBS)
    ctx.eval(js_const(src, "_IFA_FLOOR_TIP"))
    # Q9_13: the IFA cell marks a consensus grade with the C mark.
    ctx.eval(js_const(src, "GRADE_C_MARK"))
    for f in _FUNCS:
        ctx.eval(js_function(src, f))
    return ctx


def _flag(js, on: bool):
    js.eval("DATA.flags = {efv_display_swaps: %s};" % ("true" if on else "false"))


_SIGNEES = [
    {"fv": 46.5, "fv_label": "47", "fv_basis": "xfv", "fv_signing": 45.0, "fv_signing_label": "45"},
    {"fv": 33.4, "fv_basis": "xfv", "fv_signing": 76.4},
    {"fv": 20.0, "fv_label": "20", "fv_basis": "xfv", "fv_is_floor": True, "fv_signing": 40.0},
    {"fv": 41.2, "fv_basis": "xfv"},
    {"fv_signing": 40.0},
    {},
]


# ---------------------------------------------------------------------------
# 1. The country page's signee cell (B-DD5)
# ---------------------------------------------------------------------------

def test_country_signee_cell_is_the_ifa_cell_with_the_flag_on(js):
    _flag(js, True)
    for s in _SIGNEES:
        arg = json.dumps(s)
        assert js.eval("_countrySigneeFvCell(%s)" % arg) == js.eval("_ifaFvProgHTML(%s)" % arg)
    # 33.4 prints 33 (nearest), never 34; the 76.4 signing grade prints 77 (up), named.
    cell = js.eval("_countrySigneeFvCell(%s)" % json.dumps(_SIGNEES[1]))
    assert ">33<" in cell and ">34<" not in cell
    assert ">77<" in cell and "consensus FV at signing 77" in cell


def test_country_signee_cell_is_unchanged_with_the_flag_off(js):
    _flag(js, False)
    # The pre-flag cell, digits included (the eFV is rounded up there; the flag fixes it).
    assert js.eval("_countrySigneeFvCell(%s)" % json.dumps(_SIGNEES[1])) == "77 &rarr; 34"
    assert js.eval("_countrySigneeFvCell(%s)" % json.dumps(_SIGNEES[0])) == "45 &rarr; 47"
    assert js.eval("_countrySigneeFvCell(%s)" % json.dumps(_SIGNEES[4])) == "40"
    assert js.eval("_countrySigneeFvCell({})") == " - "
    assert "eFV floor" in js.eval("_countrySigneeFvCell(%s)" % json.dumps(_SIGNEES[2]))


def test_country_page_calls_the_cell_and_drops_the_cross_scale_drift_behind_the_flag():
    src = _src()
    body = js_function(src, "renderCountryDetail")
    assert "const fvProg = _countrySigneeFvCell(s);" in body
    assert "fvCeil(s.fv)" not in body
    assert "const _dropDrift = efvDisplaySwaps();" in body
    assert '(_dropDrift ? "" : _statTileHTML("eFV vs cons. at signing"' in body
    assert '(_dropDrift ? "" : cmpRow("eFV vs cons. at signing"' in body
    for lbl in ("Top tier (eFV 50+)", "Mean eFV (raw)", "Mean eFV (shrunk)", 'cmpRow("Mean eFV"',
                "Cons. at signing &rarr; eFV"):
        assert lbl in body, lbl
    board = js_function(src, "_renderIFACountries")
    assert 'label: "Shrunk eFV"' in board
    assert 'if (!efvDisplaySwaps()) cols.push({ key: "fvDrift"' in board


# ---------------------------------------------------------------------------
# 2. eFV now (B-DD1 to B-DD4, B-DD8)
# ---------------------------------------------------------------------------

def test_efv_now_joins_promoted_then_milb_key_and_rounds_to_nearest(js):
    js.eval('_E = {pro: {kind: "active", xfv_grade: 46.5}, mi: {kind: "debuted", xfv_grade: 52.4},'
            ' gone: {kind: "bust", xfv_grade: 30.0}, none: {kind: "active", xfv_grade: null}};')
    ev = lambda e: json.loads(js.eval("JSON.stringify(%s)" % e))  # noqa: E731
    r = ev('_draftEfvNow({promoted_key: "pro", milb_key: "mi"})')
    assert r["key"] == "pro" and r["val"] == 47 and r["raw"] == 46.5 and r["debuted"] is False
    r = ev('_draftEfvNow({promoted_key: "missing", milb_key: "mi"})')
    assert r["key"] == "mi" and r["val"] == 52 and r["debuted"] is True
    # A bust entry, an ungraded entry and the draft board's own player_key do not join.
    assert ev('_draftEfvNow({promoted_key: "gone"})') is None
    assert ev('_draftEfvNow({milb_key: "none"})') is None
    assert ev('_draftEfvNow({player_key: "pro"})') is None
    html = js.eval('_draftEfvNowHTML({promoted_key: "pro"})')
    assert 'data-grade-basis="efv"' in html and ">47<" in html
    assert " - " in js.eval('_draftEfvNowHTML({})')


def test_vs_slot_tooltip_follows_the_served_draft_basis(js):
    js.eval('DATA.draft = {classes: [{overperf_coverage: {basis: "board_fv"}}]};')
    assert js.eval("_draftVsSlotTip()").startswith("Consensus FV now minus")
    js.eval('DATA.draft = {classes: [{}, {overperf_coverage: {basis: "efv"}}]};')
    assert js.eval("_draftVsSlotTip()").startswith("eFV now minus")


def test_drilldown_value_swaps_ride_the_display_flag():
    src = _src()
    hs = js_function(src, "_renderHSEntityDetail")
    assert "const _efvCol = efvDisplaySwaps();" in hs
    assert ">Cons. FV</th>" in hs and ">eFV now</th>" in hs
    col = js_function(src, "renderCollegeDetail")
    assert "const _efvCol = efvDisplaySwaps();" in col and "_draftEfvNowHTML(" in col
    assert "if (efvDisplaySwaps()) cols.push({ key: \"meanEfv\"" in js_function(src, "_hsRenderLeaderboard")
    assert "if (efvDisplaySwaps()) cols.splice(5, 0, { key: \"meanEfv\"" in js_function(src, "_renderColleges")
    dd = js_function(src, "renderDraftDetail")
    assert "efvDisplaySwaps() && _draftEfvNow(p)" in dd
    assert 'data-grade-basis="consensus" title="${escapeHtml(DRAFT_FV_TIP)}"' in dd
    assert "class consensus FV distribution" in dd
    lg = js_function(src, "renderLeagueDetail")
    assert ">Cons. FV</th>" in lg and 'data-grade-basis="consensus"' in lg


# ---------------------------------------------------------------------------
# 3. draft_export: DRAFT_CURRENT_FV_EFV (B-DD6)
# ---------------------------------------------------------------------------

def test_draft_current_fv_flag_is_one_constant_and_off():
    import draft_export
    assert draft_export.DRAFT_CURRENT_FV_EFV is False
    pat = re.compile(r"^\s*(?:[\w.]+\.)?DRAFT_CURRENT_FV_EFV\s*(?::[^=\n]*)?=(?!=)", re.M)
    skip = {".cache", "data", "node_modules", "__pycache__", ".git", "_labs", ".venv", "venv"}
    hits = []
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in skip]
        for fn in fns:
            if not fn.endswith(".py") or fn.startswith("test_"):
                continue
            text = (Path(dp) / fn).read_text(encoding="utf-8", errors="replace")
            if "DRAFT_CURRENT_FV_EFV" in text and pat.search(text):
                hits.append(fn)
    assert hits == ["draft_export.py"], hits


def _fixture_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    (d / "timeseries.json").write_text(json.dumps({"players": [
        {"player_key": f"p{i}", "fv_close": 40 + i, "career_war": {"career_war": None}} for i in range(1, 7)
    ]}), encoding="utf-8")
    (d / "debuts.json").write_text(json.dumps({"players": [
        {"player_key": "d1", "fv_close": 55, "career_war": {"career_war": 4.2}}]}), encoding="utf-8")
    by = {f"p{i}": {"kind": "active", "xfv_grade": 30.0 + 2.5 * i} for i in range(1, 7)}
    by["d1"] = {"kind": "debuted", "xfv_grade": 61.3}
    by["b1"] = {"kind": "bust", "xfv_grade": 25.0}
    (d / "xfv.json").write_text(json.dumps({"by_player": by}), encoding="utf-8")
    return d


def _classes():
    rows = [{"player_key": f"draft_p{i}", "promoted_key": f"p{i}", "drafted_pick": i, "consensus_fv": 50}
            for i in range(1, 7)]
    rows.append({"player_key": "draft_d1", "milb_key": "d1", "drafted_pick": 2, "consensus_fv": 55})
    rows.append({"player_key": "draft_b1", "promoted_key": "b1", "drafted_pick": 3, "consensus_fv": 45})
    rows.append({"player_key": "draft_u", "consensus_fv": 40})
    return [{"year": 2024, "is_current": False, "prospects": rows},
            {"year": 2027, "is_current": True, "prospects": [{"player_key": "x", "consensus_fv": 50}]}]


def test_draft_overperformance_off_is_the_board_basis(tmp_path, monkeypatch):
    import draft_export
    d = _fixture_dir(tmp_path)
    monkeypatch.setattr(draft_export, "DRAFT_CURRENT_FV_EFV", False)
    cls = _classes()
    draft_export._attach_overperformance(cls, data_dir=d)
    rows = {p["player_key"]: p for p in cls[0]["prospects"]}
    assert rows["draft_p3"]["current_fv"] == 43 and rows["draft_p3"]["current_fv_basis"] == "board_fv"
    assert rows["draft_d1"]["current_fv"] == 55 and rows["draft_d1"]["career_war"] == 4.2
    assert rows["draft_b1"]["current_fv_basis"] == "unresolved"
    assert cls[0]["overperf_coverage"]["basis"] == "board_fv"
    # pick band 1-5 median of [41, 42, 43, 44, 45, 55] -> 43.5
    assert rows["draft_p1"]["expected_fv_for_pick"] == 43.5
    assert rows["draft_p1"]["overperf_fv"] == -2.5
    assert "current_fv" not in cls[1]["prospects"][0]


def test_draft_overperformance_on_is_the_efv_basis(tmp_path, monkeypatch):
    import draft_export
    d = _fixture_dir(tmp_path)
    monkeypatch.setattr(draft_export, "DRAFT_CURRENT_FV_EFV", True)
    cls = _classes()
    draft_export._attach_overperformance(cls, data_dir=d)
    rows = {p["player_key"]: p for p in cls[0]["prospects"]}
    assert rows["draft_p3"]["current_fv"] == 37.5 and rows["draft_p3"]["current_fv_basis"] == "efv"
    # The debuted player's eFV (locked at debut); career WAR still from the board payload.
    assert rows["draft_d1"]["current_fv"] == 61.3 and rows["draft_d1"]["career_war"] == 4.2
    # A bust entry is not a current grade.
    assert rows["draft_b1"]["current_fv"] is None and rows["draft_b1"]["current_fv_basis"] == "unresolved"
    assert cls[0]["overperf_coverage"] == {"n_drafted": 8, "n_resolved": 7, "n_unresolved": 1, "basis": "efv"}
    # pick band 1-5 median of eFV [32.5, 35, 37.5, 40, 42.5, 61.3] -> 38.75
    assert rows["draft_p1"]["expected_fv_for_pick"] == round(38.75, 1)
    assert rows["draft_p1"]["overperf_fv"] == round(32.5 - 38.75, 1)


def test_draft_overperformance_off_matches_the_pre_flag_export(tmp_path, monkeypatch):
    """Flag off, a second run over the same input is the same bytes, and the fields the
    flag owns never mention eFV."""
    import draft_export
    d = _fixture_dir(tmp_path)
    monkeypatch.setattr(draft_export, "DRAFT_CURRENT_FV_EFV", False)
    a, b = _classes(), _classes()
    draft_export._attach_overperformance(a, data_dir=d)
    draft_export._attach_overperformance(copy.deepcopy(b), data_dir=d)
    draft_export._attach_overperformance(b, data_dir=d)
    assert json.dumps(a) == json.dumps(b)
    assert "efv" not in json.dumps(a)


# ---------------------------------------------------------------------------
# 4. The sentinel regression on the served pages (headless Chromium)
# ---------------------------------------------------------------------------

_C, _CL, _E, _EL = 76.4, "77", 33.4, "33"
_CONS = ("consensus_fv", "consensus_fv_raw", "current_fv", "expected_fv_for_pick", "fv_close", "fv_open",
         "fv_high", "fv_low", "fv_close_raw")
_PT_CONS = ("consensus_fv", "consensus_fv_raw", "consensus_fv_pre_shrinkage", "avg_fv", "rank_implied_fv",
            "fv_min", "fv_max")
_EFV = ("xfv_grade", "xfv_grade_odds", "xfv_grade_quantile", "xfv_grade_realized", "xfv_grade_at_debut",
        "xfv_grade_model_raw")


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _taint_row(p):
    for k in _CONS:
        if _num(p.get(k)):
            p[k] = _C
    for pt in p.get("points") or []:
        if isinstance(pt, dict):
            for k in _PT_CONS:
                if _num(pt.get(k)):
                    pt[k] = _C
    if _num(p.get("overperf_fv")):
        p["overperf_fv"] = 0.0


def _build_taint(out: Path) -> dict:
    data = ROOT / "data"
    docs = {}
    for name in ("draft_timeseries.json", "overseas_timeseries.json", "ifa_timeseries.json", "xfv.json"):
        p = data / name
        if not p.exists():
            pytest.skip(f"data/{name} not built")
        docs[name] = json.loads(p.read_text(encoding="utf-8"))
    for c in docs["draft_timeseries.json"]["classes"]:
        for p in c.get("prospects") or []:
            _taint_row(p)
    for lg in docs["overseas_timeseries.json"].get("leagues") or []:
        for p in (lg.get("prospects") or []) + (lg.get("signings") or []):
            _taint_row(p)
    for c in docs["ifa_timeseries.json"]["classes"]:
        for s in c.get("signings") or []:
            if s.get("fv_basis") == "xfv" and _num(s.get("fv")):
                s["fv"] = _E
                if s.get("fv_label") is not None and not s.get("fv_is_floor"):
                    s["fv_label"] = _EL
            if _num(s.get("fv_signing")):
                s["fv_signing"] = _C
            if s.get("fv_signing_label") is not None:
                s["fv_signing_label"] = _CL
    for e in docs["xfv.json"]["by_player"].values():
        for k in _EFV:
            if _num(e.get(k)):
                e[k] = _E
        if _num(e.get("consensus_fv")):
            e["consensus_fv"] = _C
    out.mkdir(parents=True, exist_ok=True)
    bodies = {}
    for name, doc in docs.items():
        bodies[name] = json.dumps(doc).encode("utf-8")
    signed = next(p["player_key"] for c in docs["draft_timeseries.json"]["classes"] if not c.get("is_current")
                  for p in c["prospects"] if p.get("promoted_key") and p.get("drafted_pick")
                  and p["drafted_pick"] <= 5 and p["promoted_key"] in docs["xfv.json"]["by_player"])
    ovs = next(p["player_key"] for lg in docs["overseas_timeseries.json"]["leagues"]
               for p in lg.get("prospects") or [] if p.get("player_key"))
    return {"bodies": bodies, "signed": signed, "overseas": ovs}


# Every visible number that reads as a grade (an FV, eFV or "vs Slot" header, a tile or text
# naming FV, or a grade badge), with whether the spot names it as consensus.
_SCAN = r"""() => {
  const FAM = [["cons", /(^|[^\d#$.\w])(76\.4|77|76)(?![\d%.])/],
               ["efv_ceil", /(^|[^\d#$.\w])(34)(?![\d%.])/],
               ["efv", /(^|[^\d#$.\w])(33(\.4)?)(?![\d%])/]];
  const LBL = /consensus|cons\.|draft fv|source|published/i;
  const vis = el => { const cs = getComputedStyle(el); return cs.visibility !== "hidden" && cs.display !== "none" && el.getClientRects().length > 0; };
  const thOf = el => { const td = el.closest("td"); if (!td) return ""; const tr = td.parentElement;
    const i = Array.from(tr.children).indexOf(td); const h = td.closest("table").querySelector("thead tr");
    const th = h && h.children[i]; return th ? th.innerText.trim() + " " + (th.getAttribute("title") || "") : ""; };
  const out = [];
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = tw.nextNode())) {
    const t = (n.nodeValue || "").trim();
    const el = n.parentElement;
    if (!t || t.length > 300 || !el || el.closest("script,style,noscript") || !vis(el)) continue;
    const par = ((el.parentElement && el.parentElement.innerText) || "").slice(0, 60);
    for (const [fam, rx] of FAM) {
      const m = rx.exec(t);
      if (!m) continue;
      const th = thOf(el);
      if (th.trim() === "#") continue;
      let ctx = "";
      for (let c = el, i = 0; c && i < 5; i++, c = c.parentElement) ctx += " " + ((c.getAttribute && c.getAttribute("title")) || "");
      const tile = el.closest(".rs-stat");
      if (tile) ctx += " " + ((tile.querySelector(".rs-stat-label") || {}).innerText || "");
      ctx += " " + th;
      const whole = t === m[2] || /^\(?\d+(\.\d)?\)?$/.test(t);
      const fvish = /FV|grade/i.test(t) || /FV/.test(par) || /FV|grade|vs slot/i.test(th)
        || !!(tile && /FV/i.test(ctx)) || (whole && !!el.closest(".fv-badge,[data-grade-basis]"));
      if (!fvish) continue;
      const bEl = el.closest("[data-grade-basis]");
      const basis = bEl ? bEl.getAttribute("data-grade-basis") : null;
      if (fam !== "cons" && !(basis === "efv" || /eFV|→/.test(t + " " + ctx + " " + par.slice(0, 40)))) continue;
      out.push({ fam, text: t.slice(0, 80), th: th.slice(0, 50),
                 labelled: basis === "consensus" || LBL.test(t + " " + ctx + " " + par) });
    }
  }
  return out;
}"""

_ROUTES = [
    ("hs_states", "#tab=draft&dyear=overall&dview=hs-details", None),
    ("hs_schools", "#tab=draft&dyear=overall&dview=hs-details&dhsmode=schools", None),
    ("hs_state_tx", "#tab=draft&dyear=overall&dview=hs-details&dhsk=TX", None),
    ("colleges", "#tab=draft&dyear=overall&dview=colleges", None),
    ("college", "#college=Vanderbilt", None),
    ("countries", "#tab=ifa", "state.ifaView = 'countries';"),
    ("country", "#country=Dominican%20Republic", None),
    ("league", "#league=NPB", None),
    ("draftee", "#draft=__SIGNED__", None),
    ("overseas", "#overseas=__OVERSEAS__", None),
]


@pytest.fixture(scope="module")
def sentinel_report(tmp_path_factory):
    pw = pytest.importorskip("playwright.sync_api")
    from conftest import serve_site
    t = _build_taint(tmp_path_factory.mktemp("efv_drill_taint"))
    report = {}
    with serve_site() as base, pw.sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 1000})
        for name, body in t["bodies"].items():
            def _mk(_b):
                def _h(route):
                    route.fulfill(status=200, body=_b, content_type="application/json")
                return _h
            ctx.route("**/data/" + name + "*", _mk(body))
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)[:200]))
        page.goto(base + "prospx/index.html", wait_until="load", timeout=240_000)
        page.wait_for_function("() => typeof DATA !== 'undefined' && DATA && DATA.players && DATA.players.length > 10",
                               timeout=240_000)
        page.wait_for_timeout(2000)
        for flag in (False, True):
            page.evaluate("f => { DATA.flags = Object.assign({}, DATA.flags || {}, {efv_display_swaps: f}); }", flag)
            for name, h, pre in _ROUTES:
                h = h.replace("__SIGNED__", t["signed"]).replace("__OVERSEAS__", t["overseas"])
                page.evaluate("() => { location.hash = '#'; }")
                page.wait_for_timeout(300)
                if pre:
                    page.evaluate("() => { " + pre + " }")
                page.evaluate("h => { location.hash = h; }", h)
                page.wait_for_timeout(2500)
                report[(name, flag)] = page.evaluate(_SCAN)
        b.close()
    report["errors"] = errors
    return report


def test_sentinel_no_page_errors(sentinel_report):
    assert sentinel_report["errors"] == []


@pytest.mark.parametrize("flag", [False, True])
@pytest.mark.parametrize("route", [r[0] for r in _ROUTES])
def test_sentinel_every_consensus_grade_is_named(sentinel_report, route, flag):
    hits = sentinel_report[(route, flag)]
    bad = [h for h in hits if h["fam"] == "cons" and not h["labelled"]]
    assert not bad, f"{route} flag={flag}: unnamed consensus grade(s): {bad[:5]}"


@pytest.mark.parametrize("route", [r[0] for r in _ROUTES])
def test_sentinel_no_efv_rounded_up_with_the_flag_on(sentinel_report, route):
    bad = [h for h in sentinel_report[(route, True)] if h["fam"] == "efv_ceil"]
    assert not bad, f"{route}: eFV rounded up: {bad[:5]}"


def test_sentinel_the_flag_puts_efv_on_the_pages(sentinel_report):
    def n_efv(route, flag):
        return sum(1 for h in sentinel_report[(route, flag)] if h["fam"] == "efv")
    # The country signee cell: eFV rounded up with the flag off (60 rows), nearest with it on.
    assert sum(1 for h in sentinel_report[("country", False)] if h["fam"] == "efv_ceil") > 0
    assert n_efv("country", True) > 0
    # eFV now on the high-school, college and draftee pages only with the flag on.
    for route in ("hs_state_tx", "college", "draftee"):
        assert n_efv(route, False) == 0, route
        assert n_efv(route, True) > 0, route
