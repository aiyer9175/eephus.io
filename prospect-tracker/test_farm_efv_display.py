# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PROSPX farm pages print eFV, and a consensus grade only where it is named.

Owner ask 5 (2026-09-30): "Make sure eFV is being used as the only displayed FV source
across PROSPX ... specifically within farm system pages". The Part 8 lane
links_efv_display (B.2, B-F1 to B-F15) found fifteen farm spots printing the consensus
grade as a bare "FV": Recent movers, Promotion candidates, On the IL, Recent debuts,
Toolsiest, Versa watch, the depth heatmap, Comparable farms, the promotion ladder,
Positional depth "Top FV", Recent graduates, the roster rail "top by FV", Finances
Surplus details, the farm GFX distribution, the trade and waiver scoreboard and the
farm-list alumni badge.

Pinned here (task Q9_11):
  * flag off (storage.EFV_DISPLAY_SWAPS = False, today): every one of those consensus
    grades wears data-grade-basis="consensus", the C mark and a dashed border, or sits
    under words that name consensus; no printed digit moves;
  * flag on (Q9_15 flips it): the gates, sums, sorts, bins and badges read the eFV
    (nearest), eFV at debut for graduates, and the consensus grade survives only where
    it is named (Surplus details keeps the engine value, owner answer M9-3);
  * the sentinel regression: payload copies in a temp directory (never data/) with every
    consensus grade 76.4, every per-source grade 68.2 and every eFV 33.4, served over
    loopback, on #farm-org=CHW and every farm sub-tab, default and grade=fv, flag off and
    on: no visible or FV-headed cell prints 76, 77 or 76.4 unless its container carries
    data-grade-basis="consensus" or names consensus or a source, and no eFV prints 34.
"""
from __future__ import annotations

import functools
import http.server
import json
import re
import socketserver
import threading
from pathlib import Path

import pytest

from test_efv_display_helpers import _FUNCS, _STUBS, _src, js_const, js_function

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

_FARM_FUNCS = ["consFvBadgeHTML", "farmEfvBadgeHTML", "efvAtDebutValue", "efvAtDebutBadgeHTML"]


@pytest.fixture()
def js():
    mr = pytest.importorskip("py_mini_racer")
    src = _src()
    ctx = mr.MiniRacer()
    ctx.eval(_STUBS)
    ctx.eval(js_const(src, "CONS_FALLBACK_TIP"))
    ctx.eval(js_const(src, "GRADE_C_MARK"))
    for f in _FUNCS + _FARM_FUNCS:
        ctx.eval(js_function(src, f))
    return ctx


def _flag(js, on: bool, load: str = "ready"):
    js.eval("DATA.flags = {efv_display_swaps: %s}; _EFV_LOAD = %s;" % (
        "true" if on else "false", json.dumps(load)))


_EFV_ROW = ('{player_key: "e1", fv_close: 55, points: [{consensus_fv_label: "55"}], '
            '_x: {xfv_grade: 57.4, consensus_fv: 55}}')
_CONS_ROW = '{player_key: "c1", fv_close: 55, points: [{consensus_fv_label: "55"}]}'


# ---------------------------------------------------------------------------
# 1. The farm helpers
# ---------------------------------------------------------------------------

def test_consensus_badge_is_named_and_rounds_up(js):
    html = js.eval('consFvBadgeHTML(54.2, "size-sm")')
    assert 'data-grade-basis="consensus"' in html and ">C</sup>" in html
    assert "border-style:dashed" in html and ">55<" in html
    assert 'title="Consensus FV 55"' in html
    # a snapshot label prints as published
    assert ">45+<" in js.eval('consFvBadgeHTML("45+", "size-sm")')
    assert js.eval("consFvBadgeHTML(null)") == ""


def test_farm_efv_badge_prints_efv_nearest_and_labels_the_fallback(js):
    _flag(js, True)
    html = js.eval('farmEfvBadgeHTML(%s, "size-xs")' % _EFV_ROW)
    assert ">57<" in html and 'data-grade-basis="efv"' in html and "grade-c-mark" not in html
    fb = js.eval('farmEfvBadgeHTML(%s, "size-xs")' % _CONS_ROW)
    assert 'data-grade-basis="consensus"' in fb and ">C</sup>" in fb
    assert "Consensus FV (no eFV for this player)" in fb
    _flag(js, True, "loading")
    assert 'data-grade-basis="pending"' in js.eval('farmEfvBadgeHTML(%s, "size-xs")' % _CONS_ROW)


def test_efv_at_debut_is_the_debut_grade_nearest(js):
    _flag(js, True)
    g = '{player_key: "g1", fv_close: 60, _x: {kind: "debuted", xfv_grade: 56.7, xfv_grade_at_debut: 59.6}}'
    assert js.eval("efvAtDebutValue(%s)" % g) == 60
    html = js.eval('efvAtDebutBadgeHTML(%s, "size-sm")' % g)
    assert ">60<" in html and 'data-grade-basis="efv"' in html and "eFV at debut 60" in html
    # the locked grade where the debut field is absent
    assert js.eval('efvAtDebutValue({_x: {kind: "debuted", xfv_grade: 48.4}})') == 48
    # no eFV entry: the labelled consensus grade at debut
    fb = js.eval('efvAtDebutBadgeHTML({player_key: "g2", fv_close: 50}, "size-sm")')
    assert 'data-grade-basis="consensus"' in fb and "Consensus FV at debut" in fb


# ---------------------------------------------------------------------------
# 2. Every farm spot reads the flag and prints through the helpers
# ---------------------------------------------------------------------------

def _farm_body() -> str:
    return js_function(_src(), "_renderFarmDetailBody")


_BARE_BADGE = re.compile(r'fv-badge \$\{fvClass\(String\((?:fvCeil\()?\w+\.fv_close')


@pytest.mark.parametrize("name", ["_renderFarmDetailBody", "makeFarmGraduates",
                                  "makeFarmPositionalNeed", "makeFarmTransactionsSummary"])
def test_no_farm_spot_prints_a_bare_consensus_badge(name):
    body = js_function(_src(), name)
    assert not _BARE_BADGE.search(body), f"{name} still prints fv_close in an unlabelled badge"
    assert "efvDisplaySwaps()" in body, f"{name} does not read EFV_DISPLAY_SWAPS"


def test_overview_cards_swap_behind_the_flag():
    body = _farm_body()
    # B-F1 movers: eFV deltas from the history, printed integers subtracted
    assert "const delta = now - Math.round(priorRaw);" in body
    assert "No prospects moved ≥5 ${unit} in the last 30 days." in body
    # B-F2 promotion candidates: gate, score and copy on the unit
    assert 'const fv = swaps ? gradeBlock(rp, { primary: "xfv" }).efvVal : rp.fv_close;' in body
    assert "${unit} ≥ 50 or RPS+ ≥ 110" in body
    # B-F4 recent debuts on eFV at debut; B-F5 Versa sorted on efvRankValue
    assert 'efvAtDebutBadgeHTML(g, "size-xs")' in body
    assert "efvRankValue(b.rp) - efvRankValue(a.rp)" in body
    # B-F6 heatmap: no imputed 40 with the flag on
    assert "const ev = efvBoardValue(getEfv(p));" in body
    # B-F7 comparable farms bin prospects[].xfv_grade
    assert "(_cmpSwaps && pr.xfv_grade != null) ? Math.round(Number(pr.xfv_grade))" in body
    # B-F13 the GFX distribution names its basis
    assert 'distBasis: _distEfv ? "efv" : "consensus"' in body
    # B-F12 Surplus details keeps the engine value and names it (M9-3)
    assert "Surplus by consensus FV tier" in body and "<td>Consensus FV ${tier}</td>" in body


def test_rail_ladder_scoreboard_and_alumni_name_their_basis():
    src = _src()
    rail = js_function(src, "_farmDetailSidebarCards")
    assert 'top by ${swaps ? "eFV" : "consensus FV"}' in rail
    assert '"60+ eFV"' in rail and '"Total eFV"' in rail
    ladder = js_function(src, "makePromotionLadder")
    assert '${swaps ? "eFV" : "consensus FV"} ${_gradeOf(p) ?? "?"}' in ladder
    tx = js_function(src, "makeFarmTransactionsSummary")
    assert "'Trade consensus FV net'" in tx and "'Waiver consensus FV net'" in tx
    assert "Trade FV Net" not in tx and "Waiver FV Net" not in tx
    farms = js_function(src, "renderFarmSystems")
    assert "efvAtDebutValue(g)" in farms and '"eFV at debut" : "consensus FV"' in farms
    card = js_function(src, "buildFarmCard")
    assert '"eFV distribution" : "Consensus FV distribution"' in card


# ---------------------------------------------------------------------------
# 3. The sentinel regression on the served farm pages
# ---------------------------------------------------------------------------

C, CL, S, E = 76.4, "77", 68.2, 33.4
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
    for pt in p.get("points") or []:
        if not isinstance(pt, dict):
            continue
        for k in _POINT_CONS:
            if _num(pt.get(k)):
                pt[k] = C
        if pt.get("consensus_fv_label") is not None:
            pt["consensus_fv_label"] = CL
        for d in (pt.get("per_source") or {}).values():
            if isinstance(d, dict):
                for k in ("fv_published", "fv_adjusted", "fv"):
                    if _num(d.get(k)):
                        d[k] = S
    for k in _EFV_KEYS:
        if _num(p.get(k)):
            p[k] = E


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


def _load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _dump(path: Path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")


@pytest.fixture(scope="module")
def taint_dir(tmp_path_factory):
    need = ("timeseries.json", "debuts.json", "debuts_lite.json", "xfv.json",
            "xfv_ungraded.json", "xfv_history.json")
    if not all((DATA / n).is_file() for n in need):
        pytest.skip("the PROSPX payloads are not built in data/")
    out = tmp_path_factory.mktemp("farm_sentinel")
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
    for flag in ("off", "on"):
        ts["flags"] = {"efv_display_swaps": flag == "on"}
        _dump(out / flag / "timeseries.json", ts)
    del ts
    for n in ("debuts.json", "debuts_lite.json"):
        d = _load(n)
        for p in (d if isinstance(d, list) else []):
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
            if _num(pt.get("x")):
                pt["x"] = E
            if _num(pt.get("c")):
                pt["c"] = C
    _dump(out / "common" / "xfv_history.json", h)
    return out


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


_SCAN = r"""() => {
  const CONS = /(^|[^\d#$.\w])(76\.4|77|76)(?![\d%])/;
  const EFV_CEIL = /(^|[^\d#$.\w])(34)(?![\d%.])/;
  const NAMED = /consensus|cons\.|fangraphs|pipeline|espn|baseball america|just baseball|source|published/i;
  const visible = el => { const cs = getComputedStyle(el);
    return cs.visibility !== "hidden" && cs.display !== "none" && el.getClientRects().length > 0; };
  const headOf = el => { const td = el.closest("td"); if (!td) return "";
    const tr = td.parentElement, i = Array.from(tr.children).indexOf(td);
    const h = td.closest("table") && td.closest("table").querySelector("thead tr");
    return h && h.children[i] ? h.children[i].innerText.trim() : ""; };
  const bad = [], seen = { cons: 0, efv: 0 };
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = tw.nextNode())) {
    const t = (n.nodeValue || "").trim();
    const el = n.parentElement;
    if (!t || t.length > 300 || !el || el.closest("script,style,noscript,svg") || !visible(el)) continue;
    const th = headOf(el), badge = !!el.closest(".fv-badge");
    if (badge && el.closest('[data-grade-basis="efv"]') && t === "33") seen.efv++;
    if (!badge && !/\bFV\b|eFV|grade/i.test(t) && !/\bFV\b|eFV|grade/i.test(th)) continue;
    const box = el.closest("td,li,.ctx-row,div") || el.parentElement;
    const boxText = (box ? box.innerText || "" : "").slice(0, 200);
    const cm = CONS.exec(t);
    if (cm) {
      seen.cons++;
      const named = !!el.closest('[data-grade-basis="consensus"]') || NAMED.test(boxText) || NAMED.test(th) || NAMED.test(t);
      if (!named) bad.push("consensus " + cm[2] + " unnamed: " + boxText.replace(/\s+/g, " ").slice(0, 90));
    }
    if (EFV_CEIL.exec(t) && (badge || /\bFV\b|eFV|grade/i.test(th) || /eFV/.test(t)))
      bad.push("eFV printed 34 (rounded up): " + boxText.replace(/\s+/g, " ").slice(0, 90));
  }
  return { bad, seen };
}"""

_TABS = ["", "&ftab=roster", "&ftab=development", "&ftab=tendencies", "&ftab=finances",
         "&ftab=transactions"]


@pytest.mark.browser
@pytest.mark.parametrize("variant", ["off", "on"])
def test_farm_pages_print_no_unnamed_consensus_grade(taint_dir, variant):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    httpd = _serve(taint_dir, variant)
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    failures, errors, efv_seen = [], [], 0
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            for mode in ("", "&grade=fv"):
                # 1600 px so the farm context rail (shown from 1500 px) is on the page
                pg = b.new_page(viewport={"width": 1600, "height": 1000})
                pg.on("pageerror", lambda e: errors.append(str(e)[:200]))
                pg.on("console", lambda m: errors.append(m.text[:200])
                      if m.type == "error" and "ERR_FAILED" not in m.text
                      and "Failed to load resource" not in m.text else None)
                pg.route(re.compile(r"^https?://(?!127\.0\.0\.1)"), lambda r: r.abort())
                pg.goto(base + "/prospx/index.html#farm-org=CHW" + mode, timeout=240_000)
                pg.wait_for_function("() => typeof DATA !== 'undefined' && DATA && DATA.players"
                                     " && DATA.players.length > 100", timeout=240_000)
                pg.wait_for_timeout(5000)
                for tab in _TABS:
                    h = "#farm-org=CHW" + tab + mode
                    pg.evaluate("h => { location.hash = h; }", h)
                    pg.wait_for_timeout(3000)
                    out = pg.evaluate(_SCAN)
                    failures += [f"{variant} {h}: {x}" for x in out["bad"]]
                    if tab == "":
                        efv_seen += out["seen"]["efv"]
                pg.close()
            b.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert not failures, "\n".join(failures[:40])
    assert not errors, errors[:5]
    if variant == "on":
        # the swap happened: the overview cards print eFV badges (33 under the sentinel)
        assert efv_seen >= 10, efv_seen
