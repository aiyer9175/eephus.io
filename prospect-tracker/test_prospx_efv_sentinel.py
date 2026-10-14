# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV is the only grade PROSPX prints bare; a consensus grade appears only where it is named.

Owner ask 5 (2026-09-30): "Make sure eFV is being used as the only displayed FV source
across PROSPX". Part 8 lane links_efv_display, B.4 (section boards, the player card, sorts,
filters and the CSV) and B.6 (tests), task Q9_13. The lane's census scripts (build_taint.py
and probe_fv.py) are ported here as a regression test.

Pinned here:
  * the sentinel regression over every route of B.2 (farm pages), B.3 (drill-downs) and
    B.4 (section boards and the player card): payload copies in a temp directory (never
    data/) where every consensus grade is 76.4 (77 rounded up, 76 if a surface rounds a
    consensus grade to nearest), every per-source grade 68.2 and every eFV grade 33.4 (34
    would be an eFV rounded up), served over loopback, in the default eFV mode and the
    grade=fv mode, with storage.EFV_DISPLAY_SWAPS off (served today) and on (Q9_15): no
    visible FV-labelled number prints 76, 77 or 76.4 unless its spot names it as consensus
    or a source, and no eFV prints 34;
  * the Time Machine fallback pill: named (C mark, data-grade-basis) in both flag states,
    rounded up only with the flag on, so no printed digit moves before the flip;
  * the R-VM rule on the scatterplots: eFV at debut is never set against an MLB outcome for
    a debut cohort from efv_vintage_frame.R_VM_FIRST_DEBUT_YEAR on until its R-VM look is
    recorded in docs/efv-v2/EFV_V2_GATE.md part 9 (the page's two constants are pinned to
    the repo, and a chart that pairs them drops those rows);
  * the eFV movement the "Biggest movers" sort reads with the flag on, and the draft card's
    "eFV now" chip.
"""
from __future__ import annotations

import functools
import http.server
import json
import re
import socketserver
import threading
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
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


# ---------------------------------------------------------------------------
# 1. Helpers in V8
# ---------------------------------------------------------------------------

_STUBS = r"""
var DATA = {flags: {}};
var state = {};
var _H = {};
var _E = {};
function efvDisplaySwaps() { return !!(DATA.flags && DATA.flags.efv_display_swaps === true); }
function escapeHtml(s) { return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;"); }
function getEfvHistory(p) { return _H[p.player_key] || null; }
function getEfv(p) { return p ? (_E[p.player_key] || null) : null; }
function efvBoardValue(x) { return (x && x.xfv_grade != null) ? Number(x.xfv_grade) : null; }
function efvGradeDisplay(x) { const v = efvBoardValue(x); return v != null ? Math.round(v) : null; }
"""


@pytest.fixture()
def js():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    src = _src()
    ctx = mr.MiniRacer()
    ctx.eval(_STUBS)
    ctx.eval(js_const(src, "GRADE_C_MARK"))
    for c in ("_RVM_FIRST_DEBUT_YEAR", "_RVM_OPEN_COHORTS", "_CHART_OUTCOME_KEYS"):
        ctx.eval(js_const(src, c))
    for f in ("fvCeil", "_tmFvPill", "chartRvmHeld", "rvmReservedDebut", "efvSeriesMove",
              "chartFvDimLabel", "_draftEfvNow", "_draftEfvNowChipHTML"):
        ctx.eval(js_function(src, f))
    return ctx


def _flag(js, on: bool):
    js.eval("DATA.flags = {efv_display_swaps: %s};" % ("true" if on else "false"))


def test_time_machine_fallback_pill_is_named_and_rounds_up_only_with_the_flag(js):
    _flag(js, False)
    off = js.eval("_tmFvPill(76.4, false)")
    assert 'data-grade-basis="consensus"' in off and "grade-c-mark" in off
    assert ">76<" in off and ">77<" not in off   # the nearest round it always had: no digit moves
    _flag(js, True)
    on = js.eval("_tmFvPill(76.4, true)")
    assert 'data-grade-basis="consensus"' in on and ">77+<" in on   # consensus rounds UP
    assert js.eval("_tmFvPill(null, false)") == ""


def test_r_vm_constants_match_the_repo_and_the_gate():
    src = _src()
    import efv_vintage_frame as F
    assert js_const(src, "_RVM_FIRST_DEBUT_YEAR") == "const _RVM_FIRST_DEBUT_YEAR = %d;" % F.R_VM_FIRST_DEBUT_YEAR
    gate = (ROOT / "docs" / "efv-v2" / "EFV_V2_GATE.md").read_text(encoding="utf-8")
    part9 = gate.split("## 9. Results", 1)[1].split("\n## ", 1)[0]
    if "R-VM" not in part9:
        # No R-VM look record yet: every cohort from the first reserved year stays held.
        assert js_const(src, "_RVM_OPEN_COHORTS") == "const _RVM_OPEN_COHORTS = [];"


def test_r_vm_pairing_is_held_on_debuted_charts(js):
    _flag(js, True)
    held = lambda *a: js.eval("chartRvmHeld(%s)" % ", ".join(json.dumps(x) for x in a))  # noqa: E731
    assert held("debuted", "career_war", "efv_debut", "none", "none") is True
    assert held("debuted", "efv_debut", "age", "war_per_yr", "none") is True
    assert held("debuted", "age", "career_war", "none", "fv") is True       # eFV colour with the flag on
    assert held("debuted", "efv_debut", "age", "none", "none") is False     # no outcome encoded
    assert held("debuted", "fv", "career_war", "none", "none") is False     # consensus at debut
    assert held("prospects", "efv_debut", "career_war", "none", "none") is False
    _flag(js, False)
    assert held("debuted", "age", "career_war", "none", "fv") is False      # colour is consensus off
    assert js.eval('rvmReservedDebut({debut_date: "2025-04-01"})') is True
    assert js.eval('rvmReservedDebut({debut_date: "2024-09-30"})') is False
    assert js.eval("rvmReservedDebut({})") is True


def test_efv_series_move_and_the_chart_filter_label(js):
    js.eval('_H = {a: [{d: "2025-01-01", x: 44.6}, {d: "2026-01-01", x: 47.4}], b: [{d: "2026-01-01", x: 40}]};')
    m = json.loads(js.eval('JSON.stringify(efvSeriesMove({player_key: "a"}))'))
    assert m["printed"] == 47 - 45 and abs(m["raw"] - 2.8) < 1e-9
    assert js.eval('efvSeriesMove({player_key: "b"})') is None
    _flag(js, False)
    assert js.eval('chartFvDimLabel("prospects")') == "Cons. FV"
    assert js.eval('chartFvDimLabel("debuted")') == "Cons. FV at debut"
    _flag(js, True)
    assert js.eval('chartFvDimLabel("prospects")') == "eFV"
    assert js.eval('chartFvDimLabel("debuted")') == "eFV at debut"
    assert js.eval('chartFvDimLabel("draft")') == "Cons. FV"


def test_draft_card_efv_now_chip_rides_the_flag(js):
    js.eval('_E = {pro: {kind: "active", xfv_grade: 46.5}};')
    _flag(js, False)
    assert js.eval('_draftEfvNowChipHTML({promoted_key: "pro"})') == ""
    _flag(js, True)
    chip = js.eval('_draftEfvNowChipHTML({promoted_key: "pro"})')
    assert 'data-grade-basis="efv"' in chip and "eFV now 47" in chip
    assert js.eval("_draftEfvNowChipHTML({})") == ""


def test_the_value_swaps_ride_the_display_flag():
    src = _src()
    traded = js_function(src, "renderRecentlyTraded")
    assert "const _gradeSortNum = efvDisplaySwaps() ? (row => efvRankValue(row.p)) : _fvNum;" in traded
    assert ">eFV · stock</span>" in traded
    asof = js_function(src, "_boardAsOf")
    assert "(_efvFirst ? ((b.efv != null) - (a.efv != null)) : 0)" in asof
    gfa = js_function(src, "getFilteredActives")
    assert "const _efvMv = efvDisplaySwaps();" in gfa
    dims = js_function(src, "_chartDims")
    assert "efvDisplaySwaps() ? efvBoardValue(getEfv(e))" in dims and "efvDisplaySwaps() ? efvAtDebutRaw(e)" in dims
    axes = js_function(src, "chartAxesFor")
    assert "[war, _CHART_EFV_DEBUT_AXIS]" in axes
    assert 'label: "Consensus FV at debut"' in src and 'label: "Prospect FV"' not in src
    qr = js_function(src, "makeQuickReadSummaryParts")
    assert "Consensus FV ${escapeHtml(latest.consensus_fv_label)}" in qr and " FV</span>`" not in qr
    # the Debuted class-strength strip was computed and never rendered; it is gone.
    assert "classStrengthStrip" not in src


# ---------------------------------------------------------------------------
# 2. The sentinel regression on the served pages (port of build_taint.py + probe_fv.py)
# ---------------------------------------------------------------------------

C, CL = 76.4, "77"
S = 68.2
E, EL = 33.4, "33"

_PLAYER_CONS = ("fv_close", "fv_close_raw", "fv_open", "fv_high", "fv_low", "consensus_fv",
                "consensus_fv_raw", "consensus_fv_pre_shrinkage", "current_fv", "expected_fv_for_pick")
_PLAYER_CONS_LABEL = ("fv_high_label", "fv_low_label", "consensus_fv_label", "fv_open_label",
                      "fv_close_label")
_POINT_CONS = ("consensus_fv", "consensus_fv_raw", "consensus_fv_pre_shrinkage", "avg_fv",
               "rank_implied_fv", "fv_min", "fv_max")
_EFV_KEYS = ("xfv_grade", "xfv_grade_odds", "xfv_grade_quantile", "xfv_grade_realized",
             "xfv_grade_at_debut", "xfv_grade_model_raw")


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _taint_points(pts):
    for pt in pts or []:
        if not isinstance(pt, dict):
            continue
        for k in _POINT_CONS:
            if _num(pt.get(k)):
                pt[k] = C
        if pt.get("consensus_fv_label") is not None:
            pt["consensus_fv_label"] = CL
        for d in (pt.get("per_source") or {}).values():
            if not isinstance(d, dict):
                continue
            for k in ("fv_published", "fv_adjusted", "fv"):
                if _num(d.get(k)):
                    d[k] = S
            for ex in d.get("extras") or []:
                if isinstance(ex, dict):
                    for k in ("fv_published", "fv_adjusted", "fv"):
                        if _num(ex.get(k)):
                            ex[k] = S


def _taint_player(p):
    if not isinstance(p, dict):
        return
    for k in _PLAYER_CONS:
        if _num(p.get(k)):
            p[k] = C
    for k in _PLAYER_CONS_LABEL:
        if p.get(k) is not None:
            p[k] = CL
    sp = p.get("surplus")
    if isinstance(sp, dict):
        for k in ("fv_used", "fv_continuous"):
            if _num(sp.get(k)):
                sp[k] = C
    _taint_points(p.get("points"))
    for k in _EFV_KEYS:
        if _num(p.get(k)):
            p[k] = E
    if _num(p.get("overperf_fv")):
        p["overperf_fv"] = 0.0


def _taint_efv(e):
    if not isinstance(e, dict):
        return
    for k in _EFV_KEYS:
        if _num(e.get(k)):
            e[k] = E
    if _num(e.get("consensus_fv")):
        e["consensus_fv"] = C
    for h in e.get("xfv_history") or []:
        if isinstance(h, dict):
            if _num(h.get("x")):
                h["x"] = E
            if _num(h.get("c")):
                h["c"] = C


def _rows(doc):
    if isinstance(doc, list):
        return doc
    return doc.get("players") or doc.get("debuts") or []


def _load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _dump(path: Path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")


_NEED = ("timeseries.json", "debuts.json", "debuts_lite.json", "xfv.json", "xfv_ungraded.json",
         "xfv_history.json", "draft_timeseries.json", "overseas_timeseries.json", "ifa_timeseries.json")


def _build_taint(out: Path) -> dict:
    """Write the sentinel payload copies under `out` (off/, on/, common/); return the keys
    the routes need."""
    meta = {}
    ts = _load("timeseries.json")
    for p in ts.get("players") or []:
        _taint_player(p)
    for o in ts.get("org_summary") or []:
        for pr in o.get("prospects") or []:
            if _num(pr.get("fv_raw")):
                pr["fv_raw"] = C
            if pr.get("fv_label") is not None:
                pr["fv_label"] = CL
            if _num(pr.get("xfv_grade")):
                pr["xfv_grade"] = E
        tp = o.get("top_prospect")
        if isinstance(tp, dict):
            if tp.get("fv_label") is not None:
                tp["fv_label"] = CL
            for k in ("fv_raw", "fv"):
                if _num(tp.get(k)):
                    tp[k] = C
    meta["player"] = next(p["player_key"] for p in ts["players"]
                          if p.get("player_key") and len(p.get("points") or []) > 3)
    for flag in ("off", "on"):
        ts["flags"] = dict(ts.get("flags") or {}, efv_display_swaps=(flag == "on"))
        _dump(out / flag / "timeseries.json", ts)
    del ts
    for n in ("debuts.json", "debuts_lite.json"):
        d = _load(n)
        for p in _rows(d):
            _taint_player(p)
        _dump(out / "common" / n, d)
    x = _load("xfv.json")
    for e in (x.get("by_player") or {}).values():
        _taint_efv(e)
    _dump(out / "common" / "xfv.json", x)
    u = _load("xfv_ungraded.json")
    for grp in ("by_player", "by_mlbam"):
        for e in (u.get(grp) or {}).values():
            _taint_efv(e)
    _dump(out / "common" / "xfv_ungraded.json", u)
    h = _load("xfv_history.json")
    for s in (h.get("by_player") or {}).values():
        for pt in s or []:
            if isinstance(pt, dict):
                if _num(pt.get("x")):
                    pt["x"] = E
                if _num(pt.get("c")):
                    pt["c"] = C
    _dump(out / "common" / "xfv_history.json", h)
    d = _load("draft_timeseries.json")
    for c in d.get("classes") or []:
        for p in c.get("prospects") or []:
            _taint_player(p)
    by = x.get("by_player") or {}
    meta["signed"] = next(p["player_key"] for c in d["classes"] if not c.get("is_current")
                          for p in c.get("prospects") or [] if p.get("promoted_key")
                          and p.get("drafted_pick") and p["promoted_key"] in by)
    meta["signed_year"] = next(c["year"] for c in d["classes"] if not c.get("is_current")
                               and any(p.get("promoted_key") in by for p in c.get("prospects") or []))
    _dump(out / "common" / "draft_timeseries.json", d)
    o = _load("overseas_timeseries.json")
    for lg in o.get("leagues") or []:
        for p in (lg.get("prospects") or []) + (lg.get("signings") or lg.get("past_signings") or []):
            _taint_player(p)
    for p in o.get("signings") or []:
        _taint_player(p)
    meta["overseas"] = next(p["player_key"] for lg in o["leagues"] for p in lg.get("prospects") or []
                            if p.get("player_key"))
    _dump(out / "common" / "overseas_timeseries.json", o)
    i = _load("ifa_timeseries.json")
    for c in i.get("classes") or []:
        for s in c.get("signings") or []:
            if s.get("fv_basis") == "xfv":
                if _num(s.get("fv")):
                    s["fv"] = E
                if s.get("fv_label") is not None and not s.get("fv_is_floor"):
                    s["fv_label"] = EL
            elif s.get("fv_basis") == "consensus":
                if _num(s.get("fv")):
                    s["fv"] = C
                if s.get("fv_label") is not None:
                    s["fv_label"] = CL
            if _num(s.get("fv_signing")):
                s["fv_signing"] = C
            if s.get("fv_signing_label") is not None:
                s["fv_signing_label"] = CL
    _dump(out / "common" / "ifa_timeseries.json", i)
    return meta


@pytest.fixture(scope="module")
def taint(tmp_path_factory):
    if not all((DATA / n).is_file() for n in _NEED):
        pytest.skip("the PROSPX payloads are not built in data/")
    out = tmp_path_factory.mktemp("prospx_sentinel")
    return out, _build_taint(out)


def _serve(taint: Path, variant: str):
    """The site over loopback; /data/<file> answers from the sentinel copies first."""
    class H(http.server.SimpleHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def translate_path(self, path):
            p = path.split("?", 1)[0].split("#", 1)[0]
            if p.startswith("/data/") and "/" not in p[6:]:
                for d in (taint / variant, taint / "common"):
                    c = d / p[6:]
                    if c.is_file():
                        return str(c)
            return super().translate_path(path)

    httpd = socketserver.ThreadingTCPServer(
        ("127.0.0.1", 0), functools.partial(H, directory=str(ROOT)), bind_and_activate=False)
    httpd.daemon_threads = True
    httpd.allow_reuse_address = True
    httpd.server_bind()
    httpd.server_activate()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


# probe_fv.py's scan, narrowed the way the B.2 and B.3 tests narrowed it: every visible
# number that reads as a grade (an FV, eFV or grade header or tile, text naming FV, or a
# grade badge), with whether the spot names it as consensus or a source.
_SCAN = r"""() => {
  const FAM = [["cons", /(^|[^\d#$.\w\/])(76\.4|77|76)(?![\d%.\/])/],
               ["efv_ceil", /(^|[^\d#$.\w\/])(34)(?![\d%.\/])/]];
  const LBL = /consensus|cons\.|draft fv|fangraphs|pipeline|espn|baseball america|just baseball|source|published/i;
  const vis = el => { const cs = getComputedStyle(el); return cs.visibility !== "hidden" && cs.display !== "none" && el.getClientRects().length > 0; };
  const thOf = el => { const td = el.closest("td"); if (!td) return ""; const tr = td.parentElement;
    const i = Array.from(tr.children).indexOf(td); const t = td.closest("table"); const h = t && t.querySelector("thead tr");
    const th = h && h.children[i]; return th ? th.innerText.trim() + " " + (th.getAttribute("title") || "") : ""; };
  const out = [];
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = tw.nextNode())) {
    const t = (n.nodeValue || "").trim();
    const el = n.parentElement;
    if (!t || t.length > 300 || !el || el.closest("script,style,noscript,svg") || !vis(el)) continue;
    // a Time Machine rank, or a rank move (an arrow and a count), is not a grade
    if (el.closest(".tm-rank") || /^[▲▼]\s*\d+$/.test(t)) continue;
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
      const whole = t === m[2] || /^\(?\d+(\.\d)?\+?\)?$/.test(t);
      const fvish = /FV|grade/i.test(t) || /FV/.test(par) || /FV|grade/i.test(th)
        || !!(tile && /FV/i.test(ctx)) || (whole && !!el.closest(".fv-badge,.tm-fv,[data-grade-basis]"));
      if (!fvish) continue;
      const bEl = el.closest("[data-grade-basis]");
      const basis = bEl ? bEl.getAttribute("data-grade-basis") : null;
      if (fam === "efv_ceil" && !(basis === "efv" || /eFV/.test(t + " " + ctx + " " + par.slice(0, 40)))) continue;
      out.push({ fam, text: t.slice(0, 80), th: th.slice(0, 50), par: par.replace(/\s+/g, " ").slice(0, 60),
                 labelled: basis === "consensus" || LBL.test(t + " " + ctx + " " + par) });
    }
  }
  return out;
}"""

_FARM = [("farm_list", "#tab=farm", None)] + [
    ("farm" + (t or "_overview"), "#farm-org=CHW" + (("&ftab=" + t) if t else ""), None)
    for t in ("", "roster", "development", "tendencies", "finances", "transactions")]
_DRILL = [
    ("hs_states", "#tab=draft&dyear=overall&dview=hs-details", None),
    ("hs_schools", "#tab=draft&dyear=overall&dview=hs-details&dhsmode=schools", None),
    ("hs_state_tx", "#tab=draft&dyear=overall&dview=hs-details&dhsk=TX", None),
    ("colleges", "#tab=draft&dyear=overall&dview=colleges", None),
    ("college", "#college=Vanderbilt", None),
    ("countries", "#tab=ifa", "state.ifaView = 'countries'; renderIFA();"),
    ("country", "#country=Dominican%20Republic", None),
    ("league", "#league=NPB", None),
    ("draftee", "#draft=__SIGNED__", None),
    ("overseas_detail", "#overseas=__OVERSEAS__", None),
]
_BOARDS = [
    ("board", "#tab=active", None),
    ("board_movers", "#tab=active&sort=stock_movers", None),
    ("draft_cards", "#tab=draft&dyear=__SYEAR__", None),
    ("draft_cards_current", "#tab=draft", None),
    ("draft_leaderboard", "#tab=draft&dyear=__SYEAR__&dview=leaderboard", None),
    ("class_strength", "#tab=draft&dyear=overall&dview=class-strength", None),
    ("overperformers", "#tab=draft&dyear=overall&dview=overperformers", None),
    ("overperformers_value", "#tab=draft&dyear=overall&dview=overperformers",
     "_draftOverperfMode = 'value'; renderDraft();"),
    ("war_room", "#tab=draft&dview=war-room", None),
    ("mock_draft", "#tab=draft&dview=mock-draft", None),
    ("simulate", "#tab=draft&dview=simulate", None),
    ("ifa_signings", "#tab=ifa", "state.ifaView = 'signings'; state.ifaYear = 2025; renderIFA();"),
    ("ifa_all_time", "#tab=ifa", "state.ifaView = 'signings'; state.ifaYear = 'all'; renderIFA();"),
    ("ifa_efficiency", "#tab=ifa", "state.ifaView = 'efficiency'; state.ifaYear = 'all'; renderIFA();"),
    ("overseas_cards", "#tab=overseas", None),
    ("overseas_leaderboard", "#tab=overseas", "state.overseasView = 'leaderboard'; renderOverseas();"),
    ("time_machine", "#tab=timemachine", None),
    ("time_machine_diff", "#tab=timemachine&tmmode=diff", None),
    ("charts", "#tab=charts", None),
    ("charts_debuted", "#tab=charts",
     "state.chartMode = 'debuted'; state.chartX = null; state.chartY = null; renderCharts();"),
    ("traded", "#tab=traded", None),
    ("injured", "#tab=injured", None),
    ("debuts", "#tab=debuts", None),
    ("leaderboards", "#tab=leaderboards", None),
    ("spotlights", "#tab=spotlights", None),
    ("player_card", "#player=__PLAYER__", None),
    ("player_details", "#player=__PLAYER__&ptab=details", None),
]
_ROUTES = _FARM + _DRILL + _BOARDS


def _settle(pg):
    """Wait out a section's lazy payload fetch (the IFA and draft boards load their own)."""
    try:
        pg.wait_for_load_state("networkidle", timeout=20_000)
    except Exception:  # noqa: BLE001 - a slow fetch fails the scan, not the wait
        pass
    pg.wait_for_timeout(300)


def _census(base: str, meta: dict, mode: str) -> tuple[dict, list]:
    from playwright.sync_api import sync_playwright
    report, errors = {}, []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        # 1600 px so the farm context rail (shown from 1500 px) is on the page
        pg = b.new_page(viewport={"width": 1600, "height": 1000})
        pg.on("pageerror", lambda e: errors.append(str(e)[:200]))
        pg.on("console", lambda m: errors.append(m.text[:200])
              if m.type == "error" and "ERR_FAILED" not in m.text
              and "Failed to load resource" not in m.text else None)
        pg.route(re.compile(r"^https?://(?!127\.0\.0\.1)"), lambda r: r.abort())
        pg.goto(base + "/prospx/index.html#tab=active" + mode, timeout=240_000)
        pg.wait_for_function("() => typeof DATA !== 'undefined' && DATA && DATA.players"
                             " && DATA.players.length > 100", timeout=240_000)
        pg.wait_for_timeout(5000)
        for name, h, pre in _ROUTES:
            h = (h.replace("__SIGNED__", meta["signed"]).replace("__OVERSEAS__", meta["overseas"])
                  .replace("__PLAYER__", meta["player"]).replace("__SYEAR__", str(meta["signed_year"])))
            pg.evaluate("() => { location.hash = '#'; }")
            pg.wait_for_timeout(300)
            pg.evaluate("h => { location.hash = h; }", h + mode)
            pg.wait_for_timeout(2500)
            _settle(pg)
            if pre:
                pg.evaluate("() => { " + pre + " }")
                pg.wait_for_timeout(1500)
                _settle(pg)
            report[name] = pg.evaluate(_SCAN)
        b.close()
    return report, errors


@pytest.fixture(scope="module")
def census(taint):
    pytest.importorskip("playwright.sync_api")
    tdir, meta = taint
    out = {}
    for variant in ("off", "on"):
        httpd = _serve(tdir, variant)
        try:
            base = f"http://127.0.0.1:{httpd.server_address[1]}"
            for mode in ("", "&grade=fv"):
                out[(variant, mode)] = _census(base, meta, mode)
        finally:
            httpd.shutdown()
            httpd.server_close()
    return out


_CASES = [(v, m) for v in ("off", "on") for m in ("", "&grade=fv")]


@pytest.mark.browser
@pytest.mark.parametrize("variant,mode", _CASES)
def test_sentinel_every_consensus_grade_is_named(census, variant, mode):
    report, _ = census[(variant, mode)]
    bad = [f"{route}: {h['text']!r} (th {h['th']!r}, near {h['par']!r})"
           for route, hits in report.items() for h in hits if h["fam"] == "cons" and not h["labelled"]]
    assert not bad, f"{variant}{mode}: {len(bad)} unnamed consensus grade(s):\n" + "\n".join(bad[:40])


@pytest.mark.browser
@pytest.mark.parametrize("variant,mode", _CASES)
def test_sentinel_no_efv_rounded_up(census, variant, mode):
    report, _ = census[(variant, mode)]
    if variant == "off":
        # Q9_12's country signee cell keeps its pre-flag digits (eFV rounded up) until the flip.
        report = {k: v for k, v in report.items() if k != "country"}
    bad = [f"{route}: {h['text']!r}" for route, hits in report.items() for h in hits if h["fam"] == "efv_ceil"]
    assert not bad, f"{variant}{mode}: eFV printed rounded up:\n" + "\n".join(bad[:40])


@pytest.mark.browser
@pytest.mark.parametrize("variant,mode", _CASES)
def test_sentinel_no_page_errors(census, variant, mode):
    _, errors = census[(variant, mode)]
    assert errors == [], errors[:5]


@pytest.mark.browser
def test_sentinel_saw_every_route(census):
    for key, (report, _) in census.items():
        assert set(report) == {r[0] for r in _ROUTES}, key
