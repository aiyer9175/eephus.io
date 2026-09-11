# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The breakout star tooltip prints the bar the player actually cleared.

WHY THIS EXISTS (audit F06-01, 2026-09-09, verified CONFIRMED). The star tooltip
typed one threshold per perf_gate, and for stf_plus_periph it typed 115 for every
row. storage._compute_breakout_flag runs TWO blocks with different bars on that
field: the stat-only block (the only block that emits reason "stats") at
_BREAKOUT_STAT_STF_PLUS_GATE = 115, and the window block (the only block that emits
reason "fv", "upside" or "tools") at _BREAKOUT_PITCHER_STF_PLUS_GATE = 105. On the
served board 21 of the 26 stf_plus_periph breakout rows were window rows flagged at
105 to 114 and were told they had cleared 115. The SC+ branch had already been split
on meta.reason for exactly this reason; nothing asserted the other branches, so the
same defect sat one line above the fix.

The same function also had no branch for reason "upside", so every upside row (13 of
30 served breakouts) got the generic "flagged by the breakout screen" line.

What is pinned here:
  1. every bar in the client table equals the storage constant it names;
  2. the reason-to-path mapping the table relies on is total, read off storage.py;
  3. the tooltip reads the table rather than typing a number;
  4. on the served artifact, every flagged row clears the bar its tooltip prints.
"""
from __future__ import annotations

import ast
import json
import re
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"
STORAGE = ROOT / "storage.py"

# perf_gate -> (stat-only constant or None, window constant or None). None means
# storage never emits that gate on that path, so the tooltip must print no number.
GATE_CONSTANTS = {
    "wrc_plus":        ("_BREAKOUT_STAT_WRC_PLUS_GATE", "_BREAKOUT_HITTER_WRC_PLUS_GATE"),
    "wrc_plus_level":  ("_BREAKOUT_STAT_OPS_PLUS_LEVEL_GATE", None),
    "stf_plus_periph": ("_BREAKOUT_STAT_STF_PLUS_GATE", "_BREAKOUT_PITCHER_STF_PLUS_GATE"),
    "fip_minus":       (None, "_BREAKOUT_PITCHER_FIP_MINUS_GATE"),
    "statcast_plus":   ("_BREAKOUT_STAT_STATCAST_PLUS_GATE", "_BREAKOUT_STATCAST_PLUS_GATE"),
}
# The field each gate reads, and which way it must clear.
GATE_FIELD = {
    "wrc_plus":        (lambda p: (p.get("sabermetrics") or {}).get("wrc_plus"), "ge"),
    "wrc_plus_level":  (lambda p: ((p.get("statline") or {}).get("wrc_plus_level")
                                   if (p.get("statline") or {}).get("wrc_plus_level") is not None
                                   else (p.get("statline") or {}).get("ops_plus_level")), "ge"),
    "stf_plus_periph": (lambda p: (p.get("statline") or {}).get("stf_plus_periph"), "ge"),
    "fip_minus":       (lambda p: (p.get("sabermetrics") or {}).get("fip_minus"), "le"),
    "statcast_plus":   (lambda p: p.get("statcast_plus"), "ge"),
}


def _src() -> str:
    return PROSPX.read_text(encoding="utf-8")


def _storage_constants() -> dict:
    tree = ast.parse(STORAGE.read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id.startswith("_BREAKOUT_"):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return out


def _function_source(src: str, name: str) -> str:
    m = re.search(r"^function %s\([^)]*\) \{.*?\n\}\n" % re.escape(name), src, re.S | re.M)
    assert m, f"{name} not found in prospx/index.html"
    return m.group(0)


def _client_table() -> dict:
    src = _src()
    m = re.search(r"^const BREAKOUT_GATE_BARS = \{(.*?)\n\};\n", src, re.S | re.M)
    assert m, "BREAKOUT_GATE_BARS table not found in prospx/index.html"
    rows = {}
    for r in re.finditer(
            r'(\w+):\s*\{\s*label:\s*"([^"]+)",\s*op:\s*"([^"]+)",\s*'
            r'stats:\s*(null|\d+(?:\.\d+)?),\s*window:\s*(null|\d+(?:\.\d+)?)\s*\}',
            m.group(1)):
        num = (lambda s: None if s == "null" else float(s))
        rows[r.group(1)] = {"label": r.group(2), "op": r.group(3),
                            "stats": num(r.group(4)), "window": num(r.group(5))}
    assert rows, "BREAKOUT_GATE_BARS parsed to nothing; the row shape changed"
    return rows


def _compute_breakout_source() -> str:
    text = STORAGE.read_text(encoding="utf-8")
    m = re.search(r"^def _compute_breakout_flag\(.*?(?=^def )", text, re.S | re.M)
    assert m, "storage._compute_breakout_flag not found"
    return m.group(0)


# ---------------------------------------------------------------------------
# 1. The table is the storage constants, bar for bar
# ---------------------------------------------------------------------------

def test_every_bar_equals_the_storage_constant_it_names():
    consts = _storage_constants()
    table = _client_table()
    assert set(table) == set(GATE_CONSTANTS), (
        f"client gates {sorted(table)} != the gates this test knows {sorted(GATE_CONSTANTS)}. "
        "A new perf_gate needs a row in BREAKOUT_GATE_BARS AND a line in GATE_CONSTANTS.")
    for gate, (stat_c, win_c) in GATE_CONSTANTS.items():
        for col, cname in (("stats", stat_c), ("window", win_c)):
            want = None if cname is None else float(consts[cname])
            got = table[gate][col]
            assert got == want, (
                f"{gate}/{col}: the tooltip would print {got}, storage gates at "
                f"{cname} = {want}. Change both together or the star lies again.")
    assert table["fip_minus"]["op"] == "≤", "FIP- is a lower-is-better gate"
    assert all(table[g]["op"] == "≥" for g in table if g != "fip_minus")


# ---------------------------------------------------------------------------
# 2. The mapping reason === "stats" -> stat-only column is TOTAL
# ---------------------------------------------------------------------------

def test_reason_stats_is_emitted_only_by_the_stat_only_block():
    fn = _compute_breakout_source()
    stat_block, _, window_block = fn.partition("points = payload.get(\"points\")")
    assert window_block, "could not split _compute_breakout_flag at the window block"
    # The stat-only block returns literal reason "stats" with a literal perf_gate.
    stat_pairs = re.findall(r'"reason":\s*"(\w+)",\s*"perf_gate":\s*"(\w+)"', stat_block)
    assert stat_pairs and {r for r, _ in stat_pairs} == {"stats"}, stat_pairs
    # The window block assigns reason from a closed set that excludes "stats".
    window_reasons = set(re.findall(r'reason = "(\w+)"', window_block))
    assert window_reasons == {"fv", "upside", "tools"}, window_reasons
    assert '"reason": "stats"' not in window_block
    window_gates = set(re.findall(r'perf_gate_passed = "(\w+)"', window_block))
    table = _client_table()
    for g in {gt for _, gt in stat_pairs}:
        assert table[g]["stats"] is not None, f"stat-only block emits {g}; no stats bar"
    for g in window_gates:
        assert table[g]["window"] is not None, f"window block emits {g}; no window bar"


# ---------------------------------------------------------------------------
# 3. The tooltip reads the table; no typed bar survives
# ---------------------------------------------------------------------------

def test_tooltip_reads_the_table_and_types_no_threshold():
    fn = _function_source(_src(), "fvBadgeBreakoutMarkHTML")
    assert "breakoutGateText(meta)" in fn
    typed = re.findall(r"[≥≤]\s*\d+", fn)
    assert not typed, f"a threshold is typed into the tooltip again: {typed}"


def test_upside_reason_has_its_own_branch():
    fn = _function_source(_src(), "fvBadgeBreakoutMarkHTML")
    assert 'meta.reason === "upside"' in fn, (
        "reason 'upside' falls through to the generic line again")
    assert "upside_sources" in fn


# ---------------------------------------------------------------------------
# 4. Behaviour, in V8: the right bar for each path
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def js():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    src = _src()
    ctx = mr.MiniRacer()
    for pat in (r"^const SOURCE_LABELS = \{.*?\n\};\n",
                r"^const BREAKOUT_GATE_BARS = \{.*?\n\};\n"):
        m = re.search(pat, src, re.S | re.M)
        if m:                     # the table is absent on the pre-fix source; the
            ctx.eval(m.group(0))  # served-row test below must still run there
    for name in ("escapeHtml", "breakoutGateText", "fvBadgeBreakoutClass",
                 "fvBadgeBreakoutMarkHTML"):
        if name == "breakoutGateText" and "function breakoutGateText(" not in src:
            continue
        ctx.eval(_function_source(src, name))
    return ctx


def _tip(ctx, meta) -> str:
    html = ctx.eval("fvBadgeBreakoutMarkHTML(%s)" % json.dumps(
        {"breakout_flag": True, "breakout_meta": meta}))
    m = re.search(r'title="([^"]*)"', html)
    assert m, html
    return (m.group(1).replace("&quot;", '"').replace("&amp;", "&")
            .replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">"))


def test_window_path_prints_the_window_bar(js):
    t = _tip(js, {"reason": "fv", "perf_gate": "stf_plus_periph", "fv_upgrade": 5.2})
    assert "Peripheral Stuff+ ≥ 105" in t and "115" not in t, t


def test_stat_only_path_prints_the_stat_only_bar(js):
    t = _tip(js, {"reason": "stats", "perf_gate": "stf_plus_periph"})
    assert "Peripheral Stuff+ ≥ 115" in t, t
    t = _tip(js, {"reason": "stats", "perf_gate": "statcast_plus"})
    assert "SC+ ≥ 143" in t, t


def test_upside_row_names_its_sources_and_its_bar(js):
    t = _tip(js, {"reason": "upside", "perf_gate": "statcast_plus",
                  "upside_sources": ["fangraphs", "just_baseball"]})
    assert "FanGraphs, Just Baseball added a \"+\" upside mark" in t, t
    assert "SC+ ≥ 122" in t, t
    assert "flagged by the breakout screen" not in t


def test_a_pairing_storage_never_emits_prints_no_number(js):
    t = _tip(js, {"reason": "stats", "perf_gate": "fip_minus"})
    assert "FIP- gate" in t and not re.search(r"[≥≤]\s*\d", t), t
    assert "performance gate" in _tip(js, {"reason": "fv", "perf_gate": "nonsense"})


# ---------------------------------------------------------------------------
# 5. The served artifact: every flagged row clears the bar it is shown
# ---------------------------------------------------------------------------

_PRINTED_BAR = re.compile(r"(Peripheral Stuff\+|SC\+|wRC\+ vs level|wRC\+|FIP-) ([≥≤]) (\d+(?:\.\d+)?)")
_LABEL_TO_GATE = {"Peripheral Stuff+": "stf_plus_periph", "SC+": "statcast_plus",
                  "wRC+ vs level": "wrc_plus_level", "wRC+": "wrc_plus", "FIP-": "fip_minus"}


def test_every_served_star_prints_a_bar_the_row_cleared(js, timeseries_doc):
    """The test that would have caught F06-01: render the REAL tooltip for every
    served breakout row and compare the printed number with the row's own value.
    On the pre-fix source this fails on 21 rows (window-path pStuff+ 105-114 shown
    'Peripheral Stuff+ >= 115')."""
    flagged = [p for p in timeseries_doc.get("players") or [] if p.get("breakout_flag")]
    if not flagged:
        pytest.skip("no served breakout rows to check")
    bad, unexplained = [], []
    for p in flagged:
        meta = p.get("breakout_meta") or {}
        tip = _tip(js, meta)
        m = _PRINTED_BAR.search(tip)
        if m is None:
            continue              # a tooltip that prints no number claims no bar
        gate = _LABEL_TO_GATE[m.group(1)]
        getter, way = GATE_FIELD[gate]
        v, bar = getter(p), float(m.group(3))
        if v is None or (float(v) < bar if way == "ge" else float(v) > bar):
            bad.append((p.get("player_key"), meta.get("reason"), m.group(0), v))
        if "flagged by the breakout screen" in tip:
            unexplained.append((p.get("player_key"), meta.get("reason")))
    assert not bad, (
        f"{len(bad)} of {len(flagged)} served breakout stars print a bar the player did "
        f"not clear (key, reason, printed, value): {bad[:10]}")
    assert not unexplained, (
        f"served breakouts whose star falls through to the generic line: {unexplained}")


def test_every_served_breakout_clears_the_bar_its_star_prints(timeseries_doc):
    table = _client_table()
    players = timeseries_doc.get("players") or []
    flagged = [p for p in players if p.get("breakout_flag")]
    if not flagged:
        pytest.skip("no served breakout rows to check")
    bad, generic = [], []
    for p in flagged:
        meta = p.get("breakout_meta") or {}
        gate = meta.get("perf_gate")
        row = table.get(gate)
        assert row is not None, f"{p.get('player_key')}: served gate {gate!r} has no bar"
        bar = row["stats"] if meta.get("reason") == "stats" else row["window"]
        assert bar is not None, (
            f"{p.get('player_key')}: storage emitted {gate} on reason "
            f"{meta.get('reason')!r}, a pairing the tooltip calls impossible")
        getter, way = GATE_FIELD[gate]
        v = getter(p)
        ok = v is not None and (float(v) >= bar if way == "ge" else float(v) <= bar)
        if not ok:
            bad.append((p.get("player_key"), meta.get("reason"), gate, v, bar))
        if meta.get("reason") not in ("fv", "upside", "tools", "stats"):
            generic.append((p.get("player_key"), meta.get("reason")))
    assert not bad, (
        f"{len(bad)} of {len(flagged)} served breakout rows would print a bar they did "
        f"not clear (key, reason, gate, value, printed bar): {bad[:10]}")
    assert not generic, f"rows with a reason the tooltip has no branch for: {generic}"
