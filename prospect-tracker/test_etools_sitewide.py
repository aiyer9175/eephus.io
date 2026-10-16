# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""ETOOLS_SITEWIDE_FLIP (owner decision EW3-27, 2026-10-15): "eTools should be our shown
version of each tool across the site."

What these pin:
  * every surface that prints a prospect tool grade reads the same grade for a player:
    the PROSPX resolver, the PROSPX list-row strip, the MLB player page's Scouting pills
    and the Alchemy Lab's Prospect Watch bars all print data/etools.json's `shown` for a
    passing eTool, run as the shipped function bodies under a JS runtime (node, or the VS
    Code Electron binary run as node; skipped only when the box has neither);
  * a tool with no eTool keeps the consensus grade, rounded up, marked c; an eTool is
    marked e; the one Power grade reads game power's eTool;
  * with the flag off every resolver hands back the consensus map itself and no mark
    prints (the render check compares the cards to HEAD's page byte for byte);
  * every PROSPX display surface reads the resolver, and the composites, the POW+ / HIT+
    / DISC+ blends and the tiebreaker keep reading the consensus grades;
  * /scouting/ prints its eTools sentence only while data/etools.json says they are served.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import etools as E

ROOT = Path(__file__).parent
PROSPX = ROOT / "prospx" / "index.html"
SERVED = json.loads((ROOT / "data" / "etools.json").read_text(encoding="utf-8"))


def _extract(js: str, head: str) -> str:
    start = js.index(head)
    # a function body opens at its ") {" (a default argument can carry braces of its own)
    open_at = js.index(") {", start) + 2 if "function" in head else js.index("{", start)
    depth, end = 0, -1
    for i in range(open_at, len(js)):
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    assert end > 0, f"unbalanced braces after {head}"
    return js[start:end]


def _const(js: str, head: str) -> str:
    start = js.index(head)
    return js[start:js.index(";", start) + 1]


def _runtime():
    node = shutil.which("node")
    if node:
        return [node], {}
    code = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code" / "Code.exe"
    if code.exists():
        return [str(code)], {"ELECTRON_RUN_AS_NODE": "1"}
    return None, None


_PX_FUNCS = ["fvCeil", "toolFullName", "toolAbbrev", "_resolvePwr", "_eToolsFor", "_eToolRec", "_consToolVal",
             "toolGradeShown", "toolGradesShown", "toolBasis", "toolBasisMarkHTML", "toolBasisMarkText",
             "_eToolPts", "_eToolBand", "_eToolDrivers", "toolGradeTip", "_toolTier", "makeToolGradeChips"]
_PX_OBJECTS = ["const TOOL_DISPLAY_NAMES = {", "const _ETOOL_TOOL_OF = {", "const _ETOOL_KEY = {"]
_PX_STATEMENTS = ["const _BASIS_TOOLS = ", "const _HITTER_TOOL_ORDER = ", "const _PITCHER_TOOL_ORDER = "]

_STUB = r"""
var fs = require("fs");
var args = process.argv.slice(-3);
function escapeHtml(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"); }
function ensureETools() {}
var state = { section: "detail" };
var _ETOOLS_UI = true;
eval(fs.readFileSync(args[0], "utf8"));
var served = JSON.parse(fs.readFileSync(args[1], "utf8"));
var cases = JSON.parse(fs.readFileSync(args[2], "utf8"));
var byMlbam = {};
for (var k in served.players) byMlbam[String(served.players[k].mlbam)] = served.players[k];
var _ETOOLS = { players: served.players, byMlbam: byMlbam, tools: served.tools, labels: served.driver_labels };
var out = cases.map(function (c) {
  _ETOOLS_UI = true;
  var p = c.p;
  var r = { key: p.player_key, shown: {}, basis: {}, tips: {}, strip: makeToolGradeChips(p), map: toolGradesShown(p) };
  c.keys.forEach(function (k) {
    var s = toolGradeShown(p, k);
    r.shown[k] = s.shown; r.basis[k] = s.basis; r.tips[k] = toolGradeTip(p, k, s);
  });
  _ETOOLS_UI = false;
  r.off = { same: toolGradesShown(p) === p.tools.grades, mark: toolBasisMarkHTML("etool") + toolBasisMarkText("consensus"),
            strip: makeToolGradeChips(p) };
  return r;
});
process.stdout.write(JSON.stringify(out));
"""


def _cases(n_hit=25, n_pit=25):
    """Players from the served payload with a consensus map around each eTool: the
    passing tools at the payload's three-outlet consensus plus consensus-only tools."""
    hit, pit = [], []
    for pk, rec in sorted(SERVED["players"].items()):
        side = rec["side"]
        g = {t: r["consensus"] for t, r in rec["tools"].items() if r.get("consensus") is not None}
        if side == "hit":
            g.update({"raw_pwr": 52.5, "speed": 47.5, "field": 55.0, "throw": 50.0})
            if "game_pwr" in g:
                g["pwr"] = round(((g["game_pwr"] + 52.5) / 2) * 2) / 2
            keys = ["hit", "pwr", "speed", "field", "throw", "pitch_sel", "bat_ctrl"]
            bucket = hit
        else:
            g.update({"sl": 52.5, "ch": 47.5})
            keys = ["fb", "sl", "ch", "cmd"]
            bucket = pit
        if len(bucket) < (n_hit if side == "hit" else n_pit):
            bucket.append({"p": {"player_key": pk, "mlbam_id": rec["mlbam"], "position": "SS" if side == "hit" else "RHP",
                                 "statline": {"is_pitcher": side == "pit"}, "tools": {"grades": g}},
                           "keys": keys, "side": side})
    return hit + pit


def _run_prospx(tmp_path, cases):
    cmd, extra = _runtime()
    if cmd is None:
        pytest.skip("no JS runtime (node or VS Code) on this box")
    js = PROSPX.read_text(encoding="utf-8")
    parts = [_extract(js, c) + ";" for c in _PX_OBJECTS] + [_const(js, c) for c in _PX_STATEMENTS]
    parts += [_extract(js, f"function {n}(") for n in _PX_FUNCS]
    src = tmp_path / "px.js"
    src.write_text("\n".join(parts), encoding="utf-8")
    (tmp_path / "served.json").write_text(json.dumps(SERVED), encoding="utf-8")
    (tmp_path / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    out = subprocess.run(cmd + ["-e", _STUB, str(src), str(tmp_path / "served.json"), str(tmp_path / "cases.json")],
                         capture_output=True, text=True, env=dict(os.environ, **extra), timeout=120)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_prospx_resolver_and_strip_print_the_served_etool(tmp_path):
    cases = _cases()
    got = {r["key"]: r for r in _run_prospx(tmp_path, cases)}
    assert len(got) == 50
    moved = 0
    for c in cases:
        p, r = c["p"], got[c["p"]["player_key"]]
        et = SERVED["players"][p["player_key"]]["tools"]
        for k in c["keys"]:
            tool = "game_pwr" if k == "pwr" else k
            g = p["tools"]["grades"].get(k)
            if tool in et:
                assert r["shown"][k] == et[tool]["shown"] and r["basis"][k] == "etool", (p["player_key"], k)
                assert r["map"][k] == et[tool]["shown"]
                assert f"({E.TOOLS[tool]['key']})" in r["tips"][k] and "Consensus" in r["tips"][k]
                moved += int(et[tool]["shown"] != -(-g // 1))
            elif g is not None:
                # no eTool: the consensus grade, rounded up, marked c
                assert r["shown"][k] == int(-(-g // 1)) and r["basis"][k] == "consensus", (p["player_key"], k)
                assert "consensus grade, rounded up" in r["tips"][k]
        # the strip prints each shown grade with its mark (game power's eTool on the PWR chip)
        for k, code in (("hit", "HIT"), ("pwr", "PWR"), ("fb", "FB"), ("cmd", "CMD"), ("field", "DEF")):
            if r["shown"].get(k) is None:
                continue
            mark = "is-e" if r["basis"][k] == "etool" else "is-c"
            want = f'<span class="tg-code">{code}</span><span class="tg-val">{r["shown"][k]}<sup class="tool-basis {mark}"'
            assert want in r["strip"], (p["player_key"], k)
        # flag off: the consensus map itself, no mark, no eTool on the strip
        assert r["off"]["same"] is True and r["off"]["mark"] == ""
        assert "tool-basis" not in r["off"]["strip"]
    assert moved > 0


def _run_module(tmp_path, rel, heads, stub, cases):
    cmd, extra = _runtime()
    if cmd is None:
        pytest.skip("no JS runtime (node or VS Code) on this box")
    js = (ROOT / rel).read_text(encoding="utf-8")
    parts = []
    for h in heads:
        parts.append(_extract(js, h) if h.startswith("function") else _extract(js, h) + ";")
    src = tmp_path / "mod.js"
    src.write_text("\n".join(parts), encoding="utf-8")
    (tmp_path / "served.json").write_text(json.dumps(SERVED), encoding="utf-8")
    (tmp_path / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    out = subprocess.run(cmd + ["-e", stub, str(src), str(tmp_path / "served.json"), str(tmp_path / "cases.json")],
                         capture_output=True, text=True, env=dict(os.environ, **extra), timeout=120)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


_MLBP_STUB = r"""
var fs = require("fs");
var args = process.argv.slice(-3);
function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"); }
var MLBP_ETOOLS_ON = true;
eval(fs.readFileSync(args[0], "utf8"));
var served = JSON.parse(fs.readFileSync(args[1], "utf8"));
var byMlbam = {};
for (var k in served.players) byMlbam[String(served.players[k].mlbam)] = served.players[k];
var ETOOLS = { players: {}, byMlbam: byMlbam };
var cases = JSON.parse(fs.readFileSync(args[2], "utf8"));
process.stdout.write(JSON.stringify(cases.map(function (c) { return scoutToolPills(c); })));
"""

_PAL_STUB = r"""
var fs = require("fs");
var args = process.argv.slice(-3);
function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"); }
function bar(v) { return ""; }
var PAL_ETOOLS_ON = true;
eval(fs.readFileSync(args[0], "utf8"));
var ETOOLS = JSON.parse(fs.readFileSync(args[1], "utf8")).players;
var cases = JSON.parse(fs.readFileSync(args[2], "utf8"));
process.stdout.write(JSON.stringify(cases.map(function (c) { return toolBars(c.tools, c.player_key); })));
"""


def test_mlb_player_page_scouting_pills_print_the_same_grade(tmp_path):
    hit = [c for c in _cases(15, 0) if c["side"] == "hit"]
    cases = [{"mlbam": c["p"]["mlbam_id"], "isPit": False, "origin": {},
              "scout": {"tools": {k: v for k, v in c["p"]["tools"]["grades"].items() if k != "pwr"}}} for c in hit]
    heads = ["const TOOL_PILLS = {", "function gradeColor(", "function eToolsOf(", "function scoutToolPills("]
    out = _run_module(tmp_path, "assets/projections.js", heads, _MLBP_STUB, cases)
    labels = {"hit": "Hit", "game_pwr": "Game Pwr", "pitch_sel": "Pitch Sel", "bat_ctrl": "Bat Ctrl"}
    for c, html in zip(hit, out):
        et = SERVED["players"][c["p"]["player_key"]]["tools"]
        for tool, rec in et.items():
            want = re.compile(re.escape(labels[tool]) + r'<sup[^>]*>e</sup></span>\s*<span class="mlbp-toolpill-val"[^>]*>'
                              + str(rec["shown"]) + "</span>")
            assert want.search(html), (c["p"]["player_key"], tool)
        # a tool with no eTool prints its consensus grade, rounded up, marked c
        assert re.search(r'Field<sup[^>]*>c</sup></span>\s*<span class="mlbp-toolpill-val"[^>]*>55</span>', html)


def test_alchemy_lab_prospect_bars_print_the_same_grade(tmp_path):
    pit = [c for c in _cases(0, 15) if c["side"] == "pit"]
    cases = [{"player_key": c["p"]["player_key"], "tools": c["p"]["tools"]["grades"]} for c in pit]
    heads = ["function num(", "function fInt(", "function fCeil(", "function palETools(", "function toolBars("]
    out = _run_module(tmp_path, "assets/pal.js", heads, _PAL_STUB, cases)
    for c, html in zip(pit, out):
        et = SERVED["players"][c["p"]["player_key"]]["tools"]
        for tool, rec in et.items():
            want = (f'<span class="pal-ars-pitch">{tool.upper()}<sup style="font-size:8px;margin-left:1px;opacity:0.8;" '
                    f'aria-label="eTool">e</sup></span><span class="pal-ars-meta">{rec["shown"]}</span>')
            assert want in html, (c["p"]["player_key"], tool)
        assert '<span class="pal-ars-meta">53</span>' in html            # SL 52.5 consensus, rounded up


# --------------------------------------------------------------------------- #
# every PROSPX display surface reads the resolver; derived blends do not
# --------------------------------------------------------------------------- #
_DISPLAY = ["function makeToolGradeChips(", "function _toolGradeStripHTML(", "function _radarToolsFor(",
            "function _gfxInsight(", "function buildProspectCard(", "function buildCompareCard(",
            "function makeQuickReadSummaryParts(", "function makeCompareStatTable("]
_CONSENSUS_ONLY = ["function computePowerPlus(", "function computeDisciplinePlus(", "function computeHittingPlus(",
                   "function _perToolMax("]


def test_every_display_surface_reads_the_shown_grade():
    js = PROSPX.read_text(encoding="utf-8")
    for head in _DISPLAY:
        body = _extract(js, head)
        assert "toolGradesShown(" in body or "toolGradeShown(" in body, head
        if head != "function makeToolGradeChips(":     # it reads the map, then resolves it
            assert "(p.tools && p.tools.grades) || {}" not in body, head
    # the card's grade cells, the two-way card, the tool filter, the tool sort, the rail and the tile
    card = _extract(js, "function renderPlayerDetail(")
    assert card.count("toolGradeShown(p, key, t.grades)") == 1
    assert card.count('toolGradeShown(p, k, op.grades, otherIsPitcher ? "pit" : "hit")') == 2
    assert "const tg = toolGradesShown(p, tg0);" in card
    filt = _extract(js, "function getFilteredActives(")
    assert filt.count("toolGradesShown(p)") == 2
    rail = _extract(js, "function renderActiveContextRail(")
    assert "const tg = toolGradesShown(p);" in rail
    for head in _CONSENSUS_ONLY:
        body = _extract(js, head)
        assert "toolGradesShown(" not in body and "toolGradeShown(" not in body, head


def test_boot_waits_for_the_etools_payload_only_when_on():
    js = PROSPX.read_text(encoding="utf-8")
    boot = _extract(js, "async function _bootProspx(")
    assert boot.index("const _etoolsReady = ensureETools();") < boot.index("DATA = await loadData();")
    assert "if (_ETOOLS_UI && DATA && !DATA.__error)" in boot


def test_scouting_page_names_the_etools_only_while_served(monkeypatch, tmp_path):
    import build_site as B
    assert B._etools_served() is SERVED["flag_etools_on"] is E.ETOOLS_ON
    on = B._scouting_d_html()
    assert B.SCOUTING_COPY["D-5"].split(":")[0] in on
    monkeypatch.setattr(B, "ROOT", tmp_path)                    # no data/etools.json: off
    assert B._etools_served() is False
    assert "PROSPX shows the eTool" not in B._scouting_d_html()
    spec = (ROOT / "docs" / "scouting-2026-10" / "SCOUTING_PAGE.md").read_text(encoding="utf-8")
    assert B.SCOUTING_COPY["D-5"] in re.sub(r"\s+", " ", spec)
