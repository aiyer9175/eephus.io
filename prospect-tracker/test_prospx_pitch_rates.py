# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PROSPX pitch rates: P/PA, P/IP, P/BF and PAR on the career rows and the statline
(owner ask 19; plan Part 8, lane design pitch_metrics.md section 5.4, task Q8_05).

What these pin:
  * storage.pitch_rate_fields joins pitch_rates.player_lines on (mlbam, season,
    level): a row in a usable level-season at or above the floor gets the rate,
    PAR, the anchor and its basis (and, for a pitcher, his majority role);
  * an untracked level-season (CPX 2023) gets no rate and no PAR, only its basis,
    so no consumer can print a pitch rate the feed did not log (plan STOP S2);
  * the floors hold: PA 50 for a hitter, 30 outs on the role line for a pitcher;
  * with pitch_rates.SERVE_PITCH_RATES off nothing is added: the lookup is None,
    the statline passes through as the same object and the shard block is empty;
  * the PROSPX career table carries P/IP and PAR in a pitcher's header (P/PA and
    PAR for a hitter) only when the rows carry the keys, prints no NaN or
    undefined, and the by-level table pools the rate over the level's PA or outs.
The JS behaviour runs the shipped function bodies under a JS runtime (node, or the
VS Code Electron binary run as node) and skips only when the box has neither.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import pitch_rates as P
import storage as S
from test_pitch_rates import _aaa_2025, _clubs, _hit, _pit, _put, sandbox  # noqa: F401

ROOT = Path(__file__).parent
PROSPX = ROOT / "prospx" / "index.html"
RATE_KEYS = {"p_pa", "p_ip", "p_bf", "par", "par_anchor", "par_role", "par_n"}


@pytest.fixture
def flag_on(monkeypatch):
    monkeypatch.setattr(P, "SERVE_PITCH_RATES", True)


def _row(season, level, is_pitcher):
    return {"season": season, "level": level, "is_pitcher": is_pitcher, "games": 10}


# --------------------------------------------------------------------------- #
# storage: the join, the guard, the floors, the flag
# --------------------------------------------------------------------------- #
def test_flag_off_adds_nothing(monkeypatch):
    monkeypatch.setattr(P, "SERVE_PITCH_RATES", False)
    assert S.make_pitch_rate_lookup() is None
    sl = {"season": 2025, "level": "AAA", "is_pitcher": False, "mlbam_id": 2}
    assert S.attach_pitch_rate_statline(sl, 2, None) is sl
    assert S.career_pitch_rate_shard([_row(2025, "AAA", False)], 2, None) == []


def test_a_usable_hitter_row_gets_p_pa_and_par(sandbox, flag_on):
    _aaa_2025(sandbox["cache"])
    lk = S.make_pitch_rate_lookup()
    got = S.pitch_rate_fields(_row(2025, "AAA", False), 2, lk)
    anchor = P.league_rates("AAA", 2025)["hit"]["p_pa"]
    assert got["p_pa"] == pytest.approx(1950 / 500, abs=1e-3)
    assert got["par"] == P.par(1950 / 500, anchor)
    assert got["par_anchor"] == pytest.approx(anchor, abs=1e-3)
    assert got["par_basis"] == "season_line" and got["par_n"] == 500
    assert "par_role" not in got and "p_ip" not in got


def test_a_usable_pitcher_row_takes_his_majority_role_line_and_its_anchor(sandbox, flag_on):
    _aaa_2025(sandbox["cache"])
    lk = S.make_pitch_rate_lookup()
    got = S.pitch_rate_fields(_row(2025, "AAA", True), 23, lk)
    lr = P.league_rates("AAA", 2025)
    # 250 BF as a starter against 130 in relief: the starter line and the starter anchor.
    assert got["par_role"] == "SP" and got["par_basis"] == P.BASIS_ROLE
    assert got["p_ip"] == pytest.approx(1100 / 60, abs=0.01)
    assert got["p_bf"] == pytest.approx(1100 / 250, abs=0.01)
    assert got["par"] == P.par(1100 / 60, lr["sp"]["p_ip"])
    assert got["par_anchor"] == pytest.approx(lr["sp"]["p_ip"], abs=0.01)
    assert got["par_n"] == 180
    reliever = S.pitch_rate_fields(_row(2025, "AAA", True), 22, lk)
    assert reliever["par_role"] == "RP"
    assert reliever["par"] == P.par(1500 / 80, lr["rp"]["p_ip"])


def test_an_untracked_cpx_2023_row_gets_no_rate_and_no_par(sandbox, flag_on):
    c = sandbox["cache"]
    _put(c, "hitting_16_2023.json", _clubs("CPX", "ACL", {i: 1.9 for i in range(1, 10)}))
    _put(c, "pitching_16_2023.json",
         [_pit(1000 + i, i, 1900, 300, 450, 12, 12, level="CPX", league="ACL") for i in range(1, 10)])
    lk = S.make_pitch_rate_lookup()
    for is_p, pid in ((False, 1000), (True, 1001)):
        got = S.pitch_rate_fields(_row(2023, "CPX", is_p), pid, lk)
        assert got == {"par_basis": "untracked"}
        assert not (RATE_KEYS & set(got))
    shard = S.career_pitch_rate_shard([_row(2023, "CPX", False)], 1000, lk)
    assert shard == [{"season": 2023, "level": "CPX", "par_basis": "untracked"}]


def test_a_partial_level_season_gets_no_rate(sandbox, flag_on):
    c = sandbox["cache"]
    rows = _clubs("A+", "Carolina League", {i: 3.85 for i in range(1, 15)})
    rows += _clubs("A+", "Carolina League", {99: 2.1}, pid0=9000)
    _put(c, "hitting_13_2017.json", rows)
    got = S.pitch_rate_fields(_row(2017, "A+", False), 1000, S.make_pitch_rate_lookup())
    assert got == {"par_basis": "partial"}


def test_the_floors_hold(sandbox, flag_on):
    c = sandbox["cache"]
    _aaa_2025(c)
    hit = json.loads((c / "hitting_11_2025.json").read_text())["rows"]
    hit += [_hit(31, 13, 196, 49), _hit(32, 13, 200, 50)]
    _put(c, "hitting_11_2025.json", hit)
    season = json.loads((c / "pitching_11_2025.json").read_text())["rows"]
    roles = json.loads((c / "pitching_sprp_11_2025.json").read_text())["rows"]
    for pid, outs in ((41, 29), (42, 30)):
        season.append(_pit(pid, 13, 160, outs, 42, 8, 0))
        roles.append(_pit(pid, 13, 160, outs, 42, 8, 0, code="rp"))
    _put(c, "pitching_11_2025.json", season)
    _put(c, "pitching_sprp_11_2025.json", roles)
    lk = S.make_pitch_rate_lookup()
    assert S.pitch_rate_fields(_row(2025, "AAA", False), 31, lk) == {"par_basis": "below_floor"}
    assert S.pitch_rate_fields(_row(2025, "AAA", False), 32, lk)["par"] is not None
    assert S.pitch_rate_fields(_row(2025, "AAA", True), 41, lk) == {"par_basis": "below_floor"}
    assert S.pitch_rate_fields(_row(2025, "AAA", True), 42, lk)["par"] is not None
    assert (S.PITCH_RATE_MIN_PA, S.PITCH_RATE_MIN_OUTS) == (50, 30)


def test_a_player_missing_from_the_lines_is_no_line_not_a_rate(sandbox, flag_on):
    _aaa_2025(sandbox["cache"])
    lk = S.make_pitch_rate_lookup()
    assert S.pitch_rate_fields(_row(2025, "AAA", False), 999999, lk) == {"par_basis": "no_line"}
    assert S.pitch_rate_fields(_row(2025, "AAA", False), None, lk) == {"par_basis": "no_line"}


def test_the_statline_carries_the_keys_without_par_n(sandbox, flag_on):
    _aaa_2025(sandbox["cache"])
    lk = S.make_pitch_rate_lookup()
    sl = {"season": 2025, "level": "AAA", "is_pitcher": False, "mlbam_id": 2, "ops": ".800"}
    out = S.attach_pitch_rate_statline(sl, None, lk)
    assert out is not sl and out["ops"] == ".800" and "par" in out and "par_n" not in out
    assert "par" not in sl


def test_the_export_wires_the_statline_and_the_shard():
    src = (ROOT / "storage.py").read_text(encoding="utf-8")
    assert '"statline": attach_pitch_rate_statline(sl_out, _mlbam, _pitch_rate_lookup)' in src
    assert 'detail["pitch_rates"] = {"career": _pr_rows}' in src
    # the career rows in the boot payload stay as stored
    assert '"career_stats": career_stats.get(p.player_key, []),' in src


# --------------------------------------------------------------------------- #
# PROSPX: the career tables
# --------------------------------------------------------------------------- #
def _extract(js: str, head: str) -> str:
    start = js.index(head)
    depth, end = 0, -1
    for i in range(js.index("{", start), len(js)):
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    assert end > 0, f"unbalanced braces after {head}"
    return js[start:end]


def test_a_pitchers_career_table_header_carries_p_ip_and_par():
    js = PROSPX.read_text(encoding="utf-8")
    body = _extract(js, "function makeCareerTable(")
    pit = body[body.index("if (isP) {"):body.index("// Hitter table groupings")]
    assert '_sh("p_ip", "P/IP"' in pit and '_sh("par", "PAR"' in pit
    hit = body[body.index("// Hitter table groupings"):]
    assert '_sh("p_pa", "P/PA"' in hit and '_sh("par", "PAR"' in hit
    # PAR has no direction: it never joins the lower-is-better set.
    m = re.search(r"LOWER_IS_BETTER = new Set\(\[([^\]]*)\]\)", body)
    assert m and "par" not in m.group(1) and "p_ip" not in m.group(1)


_JS_NAMES = ["_prHas", "_prRoleWord", "_prNum", "_prRateText", "_prAvgLabel", "_prGapText",
             "_prBlankTd", "_prCareerCells", "_prLevelCells", "_prStatlineLine",
             "makeCareerTable", "makeCareerByLevelTable"]

_STUB = r"""
var fs = require("fs");
var args = process.argv.slice(-2);
var state = { careerSort: "season" };
function escapeHtml(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;"); }
function _careerOrgAndStints(s, player, fn) { return { orgCell: "<td></td>", stintRows: "" }; }
function _rowOpsPlus(s) { return null; }
eval(fs.readFileSync(args[0], "utf8"));
var cases = JSON.parse(fs.readFileSync(args[1], "utf8"));
process.stdout.write(JSON.stringify(cases.map(function (c) {
  return { table: makeCareerTable(c, "2003-05-01", {}), level: makeCareerByLevelTable(c, "2003-05-01"),
           line: c.length ? _prStatlineLine(c[0]) : "" };
})));
"""


def _runtime():
    node = shutil.which("node")
    if node:
        return [node], {}
    code = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code" / "Code.exe"
    if code.exists():
        return [str(code)], {"ELECTRON_RUN_AS_NODE": "1"}
    return None, None


def _render(cases, tmp_path):
    cmd, extra = _runtime()
    if cmd is None:
        pytest.skip("no JS runtime (node or VS Code) on this box")
    js = PROSPX.read_text(encoding="utf-8")
    parts = [_extract(js, "const _PR_BLANK_TIP = ") + ";",
             re.search(r"const _LEVEL_SORT = \[[^\]]*\];", js).group(0)]
    parts += [_extract(js, f"function {n}(") for n in _JS_NAMES]
    src = tmp_path / "pr.js"
    src.write_text("\n".join(parts), encoding="utf-8")
    payload = tmp_path / "pr.json"
    payload.write_text(json.dumps(cases), encoding="utf-8")
    out = subprocess.run(cmd + ["-e", _STUB, str(src), str(payload)], capture_output=True,
                         text=True, env=dict(os.environ, **extra), timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _pit_row(season, level, **kw):
    r = {"season": season, "level": level, "is_pitcher": True, "games": 20, "ip": 80.0,
         "era": "3.10", "whip": 1.1, "k_pct": 25.0, "bb_pct": 8.0, "hr_per_9": 0.8}
    r.update(kw)
    return r


def _hit_row(season, level, **kw):
    r = {"season": season, "level": level, "is_pitcher": False, "games": 90, "ab": 330,
         "avg": ".270", "obp": ".350", "slg": ".440", "ops": ".790", "bb_pct": 10.0, "k_pct": 20.0}
    r.update(kw)
    return r


def test_career_tables_render_the_rates_blanks_and_pooling(tmp_path):
    pitcher = [
        _pit_row(2026, "AA", p_ip=15.83, p_bf=3.81, par=94, par_anchor=16.84,
                 par_basis="role_split", par_role="SP", par_n=240),
        _pit_row(2025, "AA", p_ip=17.2, p_bf=3.9, par=103, par_anchor=16.7,
                 par_basis="role_split", par_role="RP", par_n=120),
        _pit_row(2023, "CPX", par_basis="untracked"),
        _pit_row(2024, "A", par_basis="below_floor"),
    ]
    hitter = [
        _hit_row(2026, "AA", p_pa=4.12, par=106, par_anchor=3.89, par_basis="season_line", par_n=400),
        _hit_row(2023, "DSL", par_basis="untracked"),
    ]
    flag_off = [_pit_row(2026, "AA")]
    res = _render([pitcher, hitter, flag_off], tmp_path)
    for r in res:
        for k in ("table", "level"):
            assert "NaN" not in r[k] and "undefined" not in r[k]
    p, h, off = res
    assert ">P/IP<" in p["table"] and ">PAR<" in p["table"] and ">Pitches<" in p["table"]
    assert ">15.8<" in p["table"] and ">94<" in p["table"]
    assert "PAR 94 = 100 x P/IP / 16.8, the AA 2026 starter average: 1.0 fewer pitches an inning" in p["table"]
    assert "0.23 more pitches a plate appearance" in h["table"]
    assert "No pitch count in this league and season" in p["table"]
    assert "Too few plate appearances or innings" in p["table"]
    # by level: (15.83 x 240 + 17.2 x 120) / 360 over (16.84 x 240 + 16.7 x 120) / 360
    rate = (15.83 * 240 + 17.2 * 120) / 360
    anchor = (16.84 * 240 + 16.7 * 120) / 360
    assert f">{rate:.1f}<" in p["level"] and f">{round(100 * rate / anchor)}<" in p["level"]
    assert ">P/PA<" in h["table"] and ">4.12<" in h["table"] and ">106<" in h["table"]
    assert p["line"] == "P/IP 15.8 vs 16.8 AA 2026 starter mean (PAR 94)"
    assert h["line"] == "P/PA 4.12 vs 3.89 AA 2026 mean (PAR 106)"
    # flag off: no row carries par_basis, so no column and no line
    assert "P/IP" not in off["table"] and "PAR" not in off["table"] and "PAR" not in off["level"]
    assert off["line"] == ""
