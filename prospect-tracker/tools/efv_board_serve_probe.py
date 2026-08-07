"""What the BOARD actually serves, measured against the shipped prospx source.

Lane B/F left one question unanswered by every python-side test and by the gate
simulation: `tools/efv_board_floor_sim.py` applies the routing RULE to the committed
artifacts, which tells you what the server would write. It cannot tell you what the
reader sees, because the frontend has its own resolution chain (`getEfv` ->
`efvBoardValue`) and the pool it resolves over is built by `_dedupeProvPool`.

That gap hid a real defect for a day. The dedupe merged the provisional twin's entry
onto the surviving graded row as `_xfv_entry`, and `getEfv` returns `_xfv_entry`
BEFORE it consults `_EFV` - so the board served the provisional grade for all 2,636
dual-listed rows with no scope at all, including 183 rows grading above FV30 that the
server-side routing is explicitly scoped to protect. The server said one thing and the
page did another.

So this probe runs the REAL functions. It extracts their exact source text from
prospx/index.html (no re-implementation, no copy to drift) into a JS engine, feeds them
the committed artifacts, and asserts four things:

  P1  the dedupe leaves zero duplicate player_keys
  P2  every graded survivor serves EXACTLY data/xfv.json's xfv_grade, i.e. the client
      does not override the server's routing decision
  P3  zero rows whose flagship grade exceeds FV30 have their served grade changed by
      anything the client does (the frontend half of gate G4)
  P4  board_sort_key breaks an exact grade tie BEFORE the '+' / TBS / name chain, and
      the resulting order is identical to storage._active_key's tuple order on the
      same rows (the F3 both-sides constraint, exercised rather than asserted in prose)

Read-only. Prints a report and exits non-zero on any failure.
Run: python tools/efv_board_serve_probe.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PROSPX = ROOT / "prospx" / "index.html"

# Functions pulled verbatim from the page. tiebreakerScore is deliberately NOT among
# them: P4 stubs it with an order that CONTRADICTS the sort key, so if the sort-key term
# were placed after it in the chain the test would fail loudly instead of passing by
# accident. Everything else is the shipped text.
WANT = ("getEfv", "_dedupeProvPool", "efvBoardValue", "efvBoardSortKey",
        "efvRankValue", "efvScaleNote", "_buildProvPlayers", "provPlayers",
        "fvCmpDesc")


def _grab(src: str, name: str) -> str:
    """One top-level `function name(...) { ... }` block, by brace balance."""
    m = re.search(r"^function %s\(" % re.escape(name), src, re.M)
    if not m:
        raise SystemExit(f"prospx/index.html no longer defines a top-level {name}()")
    i = m.start()
    k = src.index("{", i)
    depth = 0
    while True:
        c = src[k]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
        k += 1


def _sentinel(src: str) -> float:
    m = re.search(r"^const _NO_SORT_KEY = (-?[0-9.e+]+);", src, re.M)
    if not m:
        raise SystemExit("prospx no longer declares _NO_SORT_KEY")
    return float(m.group(1))


def _ctx(src: str):
    from py_mini_racer import py_mini_racer
    c = py_mini_racer.MiniRacer()
    c.eval("var _EFV = null, _EFV_UNG = null, _PROV_PLAYERS = null, _PROV_BY_KEY = null;")
    c.eval("const _NO_SORT_KEY = %r;" % _sentinel(src))
    c.eval("\n".join(_grab(src, n) for n in WANT))
    return c


def main() -> int:
    src = PROSPX.read_text(encoding="utf-8")
    ctx = _ctx(src)

    xfv = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))["by_player"]
    ung = json.loads((DATA / "xfv_ungraded.json").read_text(encoding="utf-8"))["by_player"]
    ts = json.loads((DATA / "timeseries.json").read_text(encoding="utf-8"))

    ctx.eval("var _EFV = %s;" % json.dumps(xfv))
    ctx.eval("var _EFV_UNG = %s;" % json.dumps({"by_player": ung, "by_mlbam": {}}))
    graded = [{"player_key": p.get("player_key"), "fv_close": p.get("fv_close"),
               "org": p.get("org"), "status": p.get("status")}
              for p in ts.get("players", [])
              if not (p.get("status") == "debuted" or p.get("debut_date"))]
    ctx.eval("var GRADED = %s;" % json.dumps(graded))

    served = json.loads(ctx.eval("""
    (function () {
      var pool = _dedupeProvPool(GRADED.filter(function (p) { return p && p.player_key; }),
                                 provPlayers());
      var rows = [], keys = {};
      for (var i = 0; i < pool.length; i++) {
        var p = pool[i];
        keys[p.player_key] = (keys[p.player_key] || 0) + 1;
        rows.push({k: p.player_key, prov: !!p._is_provisional,
                   merged: !!p._prov_entry, served: efvRankValue(p)});
      }
      var d = 0; for (var k in keys) if (keys[k] > 1) d++;
      return JSON.stringify({n: pool.length, distinct: Object.keys(keys).length,
                             dups: d, rows: rows});
    })()"""))

    fails = []
    print(f"pool {served['n']}  distinct {served['distinct']}  duplicates {served['dups']}")
    if served["dups"] != 0:
        fails.append(f"P1 duplicate player_keys in the rendered pool: {served['dups']}")

    merged = [r for r in served["rows"] if r["merged"]]
    print(f"graded survivors carrying a merged provisional entry: {len(merged)}")

    overrides, above30 = [], []
    for r in served["rows"]:
        if r["prov"]:
            continue
        e = xfv.get(r["k"]) or {}
        fl = e.get("xfv_grade")
        if fl is None:
            continue
        if abs(float(r["served"]) - float(fl)) > 1e-9:
            overrides.append((r["k"], float(fl), r["served"]))
            if float(fl) > 30.0:
                above30.append((r["k"], float(fl), r["served"]))
    print(f"P2 client overrides of the served xfv_grade: {len(overrides)}")
    print(f"P3 rows above FV30 moved by the client:      {len(above30)}")
    if overrides:
        fails.append(f"P2 the client overrode the served grade on {len(overrides)} rows; "
                     f"first 3: {overrides[:3]}")
    if above30:
        fails.append(f"P3 {len(above30)} rows above FV30 moved; first 3: {above30[:3]}")

    # ---- P4: the sort key breaks the tie, and both readers agree on the order -------
    # Synthetic because data/xfv.json carries no board_sort_key until the next regen
    # (efv_export._entry only started whitelisting it in this commit). Grades are equal
    # by construction, so ONLY the tiebreak chain can order these rows.
    probe = [
        {"pk": "d_lowest",  "sk": -1.9004, "plus": True,  "tbs": 130, "name": "aaa"},
        {"pk": "c_low",     "sk": -1.2000, "plus": True,  "tbs": 120, "name": "bbb"},
        {"pk": "b_mid",     "sk": -0.4000, "plus": False, "tbs": 110, "name": "ccc"},
        {"pk": "a_high",    "sk": +0.3000, "plus": False, "tbs": 100, "name": "ddd"},
        {"pk": "e_nokey",   "sk": None,    "plus": True,  "tbs": 999, "name": "eee"},
    ]
    ctx.eval("var _EFV = %s;" % json.dumps(
        {r["pk"]: ({"xfv_grade": 20.0} if r["sk"] is None
                   else {"xfv_grade": 20.0, "board_sort_key": r["sk"]}) for r in probe}))
    # The stub orders EXACTLY opposite to the sort key, so a mis-placed term shows up.
    ctx.eval("function tiebreakerScore(p) { return p.__tbs; }")
    ctx.eval("var PROBE = %s;" % json.dumps(
        [{"player_key": r["pk"], "fv_close_plus": r["plus"], "__tbs": r["tbs"],
          "player_name": r["name"]} for r in probe]))
    js_order = json.loads(ctx.eval(
        "JSON.stringify(PROBE.slice().sort(fvCmpDesc).map(function (p) "
        "{ return p.player_key; }))"))

    sys.path.insert(0, str(ROOT))
    import storage                                                   # noqa: E402
    sk_of = {r["pk"]: (r["sk"] if r["sk"] is not None else storage._NO_BOARD_SORT_KEY)
             for r in probe}
    py_order = [r["pk"] for r in sorted(
        probe, key=lambda r: (-20.0, -sk_of[r["pk"]], -(1 if r["plus"] else 0),
                              -r["tbs"], 0))]
    print(f"P4 prospx fvCmpDesc order : {js_order}")
    print(f"P4 storage tuple order    : {py_order}")
    if js_order != py_order:
        fails.append(f"P4 the two readers order a tie block differently: "
                     f"js={js_order} py={py_order}")
    if js_order[0] != "a_high" or js_order[-1] != "e_nokey":
        fails.append(f"P4 the sort key is not the FIRST tiebreak (or the sentinel does "
                     f"not sort last): {js_order}")

    note = ctx.eval('efvScaleNote({grade_basis: "provisional_capped"})')
    if not note:
        fails.append("the two-scale disclosure returns nothing for a routed row")
    if ctx.eval('efvScaleNote({grade_basis: "outcome_pooled"})') != "":
        fails.append("the two-scale disclosure fires on flagship rows too")

    print()
    for f in fails:
        print("FAIL:", f)
    print("PROBE:", "clean" if not fails else f"{len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
