# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Every graded + provisional pool goes through _dedupeProvPool. No exceptions.

WHY THIS EXISTS (audit L15-F1, 2026-09-09, verified CONFIRMED with a corrected
count). 2,688 players carry BOTH a graded board row and a provisional twin in
data/xfv_ungraded.json. _dedupeProvPool exists to collapse the pair (the graded row
wins; the twin's entry lands on _prov_entry, never _xfv_entry). It was applied at
four of the EIGHT concat sites. The four bare ones fed:
  * the homepage rail's eFV distribution and its "N rated" (2,688 rows high);
  * the farm-rankings "live top prospect" cell;
  * the farm-list Top-3 strip;
  * the farm-detail pool behind "N prospects tracked", the histogram, the depth
    chart, the pyramid, the scatter, the promotion ladder and pagination:
    2,669 duplicate rows inside the 30 orgs (Cleveland 373 rows for 265 players),
    while the org-rank denominator on the same site, built on the site-wide deduped
    pool, printed a smaller "of N".
The fix moved every one of those counts by design. Nothing baked moved.

The farm pools are slices of ONE site-wide deduped pool (oneRowActivePool), not a
dedupe inside each org: 19 players (same mlbam id on both rows) carry a graded row in
one org and a provisional twin in another after a move, which a per-org dedupe cannot
see. So on top of "each player once per org" this pins "each player in ONE org", and
"farm header == org-rank denominator".

The structural invariant is asserted structurally: every call of provPlayers()
outside its own definition is an argument of _dedupeProvPool. A new pool that forgets
the dedupe fails here instead of on a farm page.
"""
from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"
DATA = ROOT / "data"


def _src() -> str:
    return PROSPX.read_text(encoding="utf-8")


def _strip_comments(src: str) -> str:
    """Blank // line comments (start-of-line or whitespace-preceded, so URLs in
    strings survive), keeping offsets line-stable."""
    return "\n".join(re.sub(r"(^|\s)//.*$", r"\1", ln) for ln in src.splitlines())


def _function_source(src: str, name: str) -> str:
    m = re.search(r"^function %s\([^)]*\) \{.*?\n\}\n" % re.escape(name), src, re.S | re.M)
    assert m, f"{name} not found in prospx/index.html"
    return m.group(0)


def _enclosed_by_dedupe(code: str, at: int, window: int = 4000) -> bool:
    """True when position `at` sits inside the argument list of a
    _dedupeProvPool( ... ) call. Walks outward through every enclosing open
    paren; string contents at these sites carry no bare parens."""
    depth = 0
    lo = max(0, at - window)
    i = at - 1
    while i >= lo:
        ch = code[i]
        if ch == ")":
            depth += 1
        elif ch == "(":
            if depth == 0:
                if re.search(r"_dedupeProvPool\s*$", code[max(0, i - 40):i]):
                    return True
            else:
                depth -= 1
        i -= 1
    return False


def _enclosing_function(code: str, at: int) -> str | None:
    """Name of the top-level `function NAME(` the position sits in (column 0)."""
    m = None
    for m in re.finditer(r"^function (\w+)\(", code[:at], re.M):
        pass
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# 1. Structure
# ---------------------------------------------------------------------------

def test_every_provisional_pool_is_deduped_against_the_graded_board():
    code = _strip_comments(_src())
    calls = [m.start() for m in re.finditer(r"\bprovPlayers\(\)", code)]
    assert calls, "provPlayers() vanished; this test needs re-pointing"
    bare = []
    for at in calls:
        line_start = code.rfind("\n", 0, at) + 1
        line = code[line_start:code.find("\n", at)]
        if re.match(r"\s*function provPlayers\(\)", line):
            continue                                   # the definition itself
        if _enclosing_function(code, at) == "oneRowActivePool":
            continue    # the one pool's own input; test below pins that it is deduped
        if not _enclosed_by_dedupe(code, at):
            bare.append((code.count("\n", 0, at) + 1, line.strip()[:140]))
    assert not bare, (
        "a graded + provisional pool is built without _dedupeProvPool, so every player "
        "with a provisional twin is counted twice on that surface (audit L15-F1). "
        f"Route it through _dedupeProvPool or oneRowOrgPool: {bare}")


def test_the_one_pool_actually_dedupes_its_input():
    fn = _function_source(_src(), "oneRowActivePool")
    assert "_dedupeProvPool(src.filter(p => p), prov)" in fn


def test_no_pool_concatenates_the_provisional_list_directly():
    code = _strip_comments(_src())
    hits = re.findall(r"\.concat\(\s*\(?\s*typeof provPlayers[^\n]*", code)
    assert not hits, f"bare .concat of the provisional list: {hits}"


def test_the_four_formerly_bare_surfaces_read_the_one_pool():
    code = _strip_comments(_src())
    assert "const _distPool = oneRowActivePool();" in code          # homepage rail
    assert "const _wlPool = oneRowOrgPool(org.org)" in code          # farm rankings
    assert "const _orgPool = oneRowOrgPool(org.org)" in code         # farm list Top-3
    assert "const rosterPlayersAll = oneRowOrgPool(orgCode);" in code  # farm detail


# ---------------------------------------------------------------------------
# 2. Behaviour in V8
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def js():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    src = _src()
    ctx = mr.MiniRacer()
    ctx.eval("var DATA = {players: []}; var __PROV = [];"
             " function provPlayers() { return __PROV; }")
    ctx.eval(_function_source(src, "_dedupeProvPool"))
    m = re.search(r"^let _ONE_ROW_POOL = null[^\n]*\n", src, re.M)
    if m:                                  # absent on the pre-fix source
        ctx.eval(m.group(0))
        ctx.eval(_function_source(src, "oneRowActivePool"))
        ctx.eval(_function_source(src, "oneRowOrgPool"))
    return ctx


def test_graded_row_wins_and_the_twin_never_lands_on_xfv_entry(js):
    out = json.loads(js.eval("""JSON.stringify((() => {
      const g = [{player_key: "a", org: "CLE"}, {player_key: "b", org: "CLE"}];
      const q = [{player_key: "a", org: "CLE", _is_provisional: true, _xfv_entry: {xfv_grade: 30}},
                 {player_key: "c", org: "CLE", _is_provisional: true, _xfv_entry: {xfv_grade: 35}}];
      const pool = _dedupeProvPool(g, q);
      return {keys: pool.map(p => p.player_key), provFlags: pool.map(p => !!p._is_provisional),
              a: pool[0]};
    })())"""))
    assert out["keys"] == ["a", "b", "c"]
    assert out["provFlags"] == [False, False, True]
    assert out["a"].get("_prov_entry") == {"xfv_grade": 30}
    assert "_xfv_entry" not in out["a"], (
        "the twin's entry landed on _xfv_entry, which getEfv returns first: that is the "
        "2026-08-07 bug that served 2,636 provisional grades on the board")


def test_a_player_who_moved_orgs_is_in_one_farm_not_two(js):
    out = json.loads(js.eval("""JSON.stringify((() => {
      DATA = {players: [{player_key: "m", org: "BOS"}, {player_key: "x", org: "CLE"}]};
      __PROV = [{player_key: "m", org: "CLE", _is_provisional: true, _xfv_entry: {}},
                {player_key: "y", org: "CLE", _is_provisional: true, _xfv_entry: {}}];
      return {bos: oneRowOrgPool("BOS").map(p => p.player_key),
              cle: oneRowOrgPool("CLE").map(p => p.player_key)};
    })())"""))
    assert out == {"bos": ["m"], "cle": ["x", "y"]}, out


def test_the_memo_follows_a_provisional_reload(js):
    out = json.loads(js.eval("""JSON.stringify((() => {
      DATA = {players: [{player_key: "a", org: "SEA"}]};
      __PROV = [];
      const before = oneRowOrgPool("SEA").length;
      __PROV = [{player_key: "b", org: "SEA", _is_provisional: true, _xfv_entry: {}}];
      const after = oneRowOrgPool("SEA").length;
      const p = oneRowOrgPool("SEA"); p.pop();
      return {before, after, notShared: oneRowOrgPool("SEA").length};
    })())"""))
    assert out == {"before": 1, "after": 2, "notShared": 2}, out


# ---------------------------------------------------------------------------
# 3. The served artifacts
# ---------------------------------------------------------------------------

def test_served_farm_pools_hold_each_player_once_site_wide(js, timeseries_doc):
    """The real client functions over the real served pools: no player twice inside
    an org, no player in two orgs, and every farm header equal to the org-rank
    denominator buildEfvOrgRankMap computes from the same pool."""
    if "function oneRowOrgPool(" not in _src():
        pytest.fail("oneRowOrgPool is missing: the farm pools are not one-row-per-player")
    path = DATA / "xfv_ungraded.json"
    if not path.exists():
        pytest.skip("data/xfv_ungraded.json not built")
    ung = json.loads(path.read_text(encoding="utf-8")).get("by_player") or {}
    graded = [{"player_key": p["player_key"], "org": p.get("org")}
              for p in timeseries_doc.get("players") or [] if p and p.get("player_key")]
    prov = [{"player_key": k, "org": e.get("org"), "_is_provisional": True, "_xfv_entry": {}}
            for k, e in ung.items() if e]
    js.eval("DATA = {players: %s}; __PROV = %s;" % (json.dumps(graded), json.dumps(prov)))
    res = json.loads(js.eval("""JSON.stringify((() => {
      const orgs = Array.from(new Set(DATA.players.map(p => p.org).concat(__PROV.map(p => p.org))))
        .filter(o => o);
      const byOrg = {};
      for (const o of orgs) byOrg[o] = oneRowOrgPool(o).map(p => p.player_key);
      const rankTotal = {};
      _dedupeProvPool(DATA.players.filter(p => p && p.player_key), provPlayers())
        .forEach(p => { const o = p.org || "?"; rankTotal[o] = (rankTotal[o] || 0) + 1; });
      return {byOrg, rankTotal};
    })())"""))
    seen, twice, twin_orgs = {}, [], []
    for org, keys in res["byOrg"].items():
        if len(keys) != len(set(keys)):
            twice.append((org, len(keys) - len(set(keys))))
        for k in keys:
            if k in seen and seen[k] != org:
                twin_orgs.append((k, seen[k], org))
            seen[k] = org
        assert len(keys) == res["rankTotal"].get(org, 0), (
            f"{org}: farm header would read {len(keys)} while the org rank says of "
            f"{res['rankTotal'].get(org, 0)}")
    assert not twice, f"players listed twice inside one farm: {twice}"
    assert not twin_orgs, f"players listed in two farms: {twin_orgs[:10]}"
    overlap = sum(1 for p in prov if p["player_key"] in {g["player_key"] for g in graded})
    if overlap == 0:
        pytest.skip("no graded/provisional overlap on this artifact, so the dedupe had "
                    "nothing to do and this check proved nothing")
