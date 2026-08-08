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

---------------------------------------------------------------------------
SERVE-PATH MODE (Lane G, 2026-08-08).  `python tools/efv_board_serve_probe.py serve`

The four probes above answer "does the PAGE serve what the SERVER wrote". They say
nothing about whether the number either of them serves is the number the published
accuracy claim describes. data/xfv_eval.json scores an arm it calls `blend`; the board
serves vf.outcome_implied_fv of the MODEL leg alone, after live tilts, after floor
routing. Nothing scored the end of that chain.

Serve mode replays the chain out of fold on the resolved cohort under the published
protocol and writes data/xfv_serve_path_eval.json. Gate clauses G1-G7 are pre-registered
in docs/efv-2026-08-07b/SERVE_PATH_INTEGRITY.md, written before this mode existed.
Read-only: it writes exactly one artifact, under its own name.
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


# ===========================================================================
# SERVE-PATH MODE (Lane G).  Gate: docs/efv-2026-08-07b/SERVE_PATH_INTEGRITY.md
# ===========================================================================

SERVE_OUT = DATA / "xfv_serve_path_eval.json"
SIDES = ("hit", "pit")
PUBLISHED = {"hit": "xfv_eval.json", "pit": "xfv_eval_pitcher.json"}
# The ten fields the live overlays read. None may exist on a training row.
LIVE_ONLY_FIELDS = ("statcast_plus", "age_now", "il_on", "il_type", "il_days_12mo",
                    "il_stints_12mo", "eta_years", "fv_effective",
                    "anchor_stale_discount", "anchor_constant_only")
OVERLAY_FUNCS = ("_injury_factor", "_age_factor", "_role_factor", "_statcast_factor",
                 "overlay_fv", "route_floor_grade")
ALLOWED_OVERLAY_CALLERS = {"run_live", "run_backgrade"}
PERM_SEED = 20260808          # fixed integer; never hash() and never set iteration
VINTAGE_D1 = "2026-08-02"
VINTAGE_D2 = "2026-08-07"
# SUPPLEMENTARY, added AFTER the pre-registered pair returned. Not used to decide any
# verdict, and reported as a sensitivity. The pre-registered pair brackets the
# 2026-08-07 refresh, which nearly doubles the reconstructed pool, so it is the LOUD
# end of the composition-change distribution. This pair is a routine adjacent day and
# bounds the quiet end. Both are reported; neither replaces the other.
VINTAGE_Q1 = "2026-08-05"
VINTAGE_Q2 = "2026-08-06"
MATERIAL_SHARE = 0.05         # SELF-ADDED, disclosed in the gate doc and the headline


def _bootstrap_path():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


# --------------------------------------------------------------------------
# G1-G4: score the END of the serve chain, out of fold, on the published protocol
# --------------------------------------------------------------------------

def _serve_arms(side: str) -> dict:
    """Forward-chained replay of efv_model._run_eval's debuted-KM folds, with the
    SERVE-PATH arms added. Every published arm is recomputed here rather than read,
    so G1 is a real reproduction and not a restatement."""
    import random
    import efv_model as M
    import value_framework as vf
    from efv_dataset import matrix_path
    from prospect_path import _score, _fit_linear_calibration

    keys, _mono = M._feature_spec(side)
    lam = M.blend_lambda(side)
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    data = M._prep([r for r in rows if r["kind"] == "debuted"], "target_censored", side)

    knot = None
    arms = ("baseline", "ridge", "blend", "cal_affine", "grade_unrounded",
            "served_grade", "blend_graded", "served_perm")
    pairs = {m: [] for m in arms}
    wts = {m: [] for m in arms}
    floor_hits = 0
    n_test = 0
    bad_slope = []
    by_fold = []
    within_fold_affine_ok = True

    rng = random.Random(PERM_SEED)
    for yr in M.SCORED_YEARS:
        train = [r for r in data if r["decision_year"] < yr]
        test = [r for r in data if r["decision_year"] == yr]
        if len(test) < 15 or len(train) < 60:
            continue
        ols = M._fit_ols_fv(train)
        ridge = M._fit_ridge(train, keys)
        if not (ols and ridge):
            continue
        # The fold's OWN output calibration, fit on TRAIN ONLY -- the within-fold
        # analogue of fit_production_stack's (a, b). Production fits it on the full
        # labeled pool; fitting it on train keeps the replay out of sample.
        cal = _fit_linear_calibration([(M._predict(ridge, r["feats"]), r["target"])
                                       for r in train])
        a_f, b_f = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
        if b_f <= 0:
            bad_slope.append(yr)
        fold_served = []
        for r in test:
            w = float(r.get("weight") or 1.0)
            t = r["target"]
            cons = max(0.0, M._pred_ols(ols, r["fv"]))
            pred = M._predict(ridge, r["feats"])
            blend = (1 - lam) * cons + lam * pred
            # THE SERVE CHAIN, in production's order (efv_score.run_live):
            #   calibrate -> clamp -> outcome_implied_fv -> round to 1dp
            war = max(-2.0, a_f + b_f * pred)
            g_raw = vf.outcome_implied_fv(war, exposure_seasons=6)
            if g_raw is None:
                continue
            if knot is None:
                import efv_score as _es
                knot = _es._outcome_floor_knot()
            served = round(g_raw, 1)
            # The SAME chain applied to the blend: isolates the tie/clamp/round cost
            # from the dropped-consensus-leg cost.
            bg = vf.outcome_implied_fv(max(-2.0, (1 - lam) * cons + lam * (a_f + b_f * pred)),
                                       exposure_seasons=6)
            n_test += 1
            if abs(served - knot) <= 1e-9:
                floor_hits += 1
            for m, v in (("baseline", cons), ("ridge", pred), ("blend", blend),
                         ("cal_affine", a_f + b_f * pred), ("grade_unrounded", g_raw),
                         ("served_grade", served),
                         ("blend_graded", round(bg, 1) if bg is not None else None)):
                if v is None:
                    continue
                pairs[m].append((v, t))
                wts[m].append(w)
            fold_served.append((served, t, w))
        # C-a PERMUTATION: shuffle the served VALUES within the fold against fixed
        # targets. Ordered list of ints, seeded Random -- no set, no hash().
        idx = list(range(len(fold_served)))
        rng.shuffle(idx)
        for j, k in enumerate(idx):
            pairs["served_perm"].append((fold_served[k][0], fold_served[j][1]))
            wts["served_perm"].append(fold_served[j][2])
        by_fold.append(fold_served)
        # POST-HOC DIAGNOSTIC for C-c, not a substitute clause. Spearman is invariant
        # to a strictly increasing affine map WITHIN a fold; it is NOT invariant when
        # each fold gets its OWN (a_f, b_f) and the folds are then pooled, which is the
        # same cross-fold reordering efv_model._lofo_calibrate's corrected docstring
        # already records. This measures the within-fold half so the pooled failure can
        # be attributed rather than guessed at.
        from prospect_path import _spearman as _sp
        _p = [M._predict(ridge, r["feats"]) for r in test]
        _t = [r["target"] for r in test]
        if len(_p) >= 8 and _sp(_p, _t) != _sp([a_f + b_f * v for v in _p], _t):
            within_fold_affine_ok = False

    # SUPPLEMENTARY multi-draw permutation, added after the single pre-registered
    # draw PASSED. It does not decide any verdict; it exists because one draw of a
    # null has sampling SE ~ 1/sqrt(n) (about 0.036 here), so a single |rho| of 0.04
    # is uninformative on its own about whether the null is centred at zero.
    perm_rhos = []
    rng2 = random.Random(PERM_SEED + 1)
    for _ in range(200):
        pp, ww = [], []
        for fold in by_fold:
            order = list(range(len(fold)))
            rng2.shuffle(order)
            for j, k in enumerate(order):
                pp.append((fold[k][0], fold[j][1]))
                ww.append(fold[j][2])
        s = _score(pp, ww)
        if s.get("spearman") is not None:
            perm_rhos.append(s["spearman"])
    perm_rhos.sort()

    scored = {m: (_score(pairs[m], wts[m]) if pairs[m] else {"n": 0}) for m in arms}
    pub = json.loads((DATA / PUBLISHED[side]).read_text(encoding="utf-8"))
    pub = pub["evals"]["debuted_km"]["pooled_oos"]
    return {
        "side": side, "lambda": lam, "arms": scored,
        "published": {m: {"n": pub[m]["n"], "spearman": pub[m]["spearman"]}
                      for m in ("baseline", "ridge", "blend")},
        "floor_knot": knot,
        "floor_share": round(floor_hits / n_test, 4) if n_test else None,
        "distinct_served_values": len({round(v, 1) for v, _ in pairs["served_grade"]}),
        "folds_with_nonpositive_calibration_slope": bad_slope,
        "within_fold_affine_invariance_holds": within_fold_affine_ok,
        "supplementary_permutation_200_draws": {
            "n": len(perm_rhos),
            "mean": round(sum(perm_rhos) / len(perm_rhos), 4) if perm_rhos else None,
            "p05": perm_rhos[int(0.05 * len(perm_rhos))] if perm_rhos else None,
            "p95": perm_rhos[int(0.95 * len(perm_rhos))] if perm_rhos else None,
            "max_abs": round(max(abs(x) for x in perm_rhos), 4) if perm_rhos else None,
            "note": "supplementary, added after the pre-registered single draw passed; "
                    "decides nothing",
        },
        "mde95": M.MDE95_POOLED_RHO[side],
    }


# --------------------------------------------------------------------------
# G5: live-only containment
# --------------------------------------------------------------------------

def _g5_field_containment() -> dict:
    from efv_dataset import matrix_path, live_matrix_path
    out = {}
    for side in SIDES:
        tr = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        lv = json.loads(live_matrix_path(side).read_text(encoding="utf-8"))
        out[side] = {
            "n_train": len(tr), "n_live": len(lv),
            "train_rows_carrying": {f: sum(1 for r in tr if f in r) for f in LIVE_ONLY_FIELDS},
            "live_rows_carrying": {f: sum(1 for r in lv if f in r) for f in LIVE_ONLY_FIELDS},
        }
    return out


def _g5_call_sites() -> dict:
    """AST, not grep: the enclosing function of every call to each overlay."""
    import ast
    src = (ROOT / "efv_score.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    found = {f: set() for f in OVERLAY_FUNCS}

    def walk(node, enclosing):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                walk(child, child.name)
                continue
            if isinstance(child, ast.Call):
                fn = child.func
                name = (fn.id if isinstance(fn, ast.Name)
                        else fn.attr if isinstance(fn, ast.Attribute) else None)
                if name in found:
                    found[name].add(enclosing or "<module>")
            walk(child, enclosing)

    walk(tree, None)
    return {f: sorted(found[f]) for f in OVERLAY_FUNCS}


def _g5_xline() -> dict:
    """S-XLINE is the DECLARED exception: it must reach TRAINING rows. Verified by
    recomputing _milb_features with the flag forced on and off in one process and
    comparing BOTH against each other and against the committed matrix."""
    import os
    import efv_statcast_line as XL
    from efv_dataset import matrix_path
    import efv_dataset as DS

    res = {"defaults": {"XLINE_HIT_DEFAULT": XL.XLINE_HIT_DEFAULT,
                        "XLINE_PIT_DEFAULT": XL.XLINE_PIT_DEFAULT,
                        "XISO_HIT_DEFAULT": XL.XISO_HIT_DEFAULT},
           "per_side": {}}
    env_key = {"hit": "EEPHUS_XLINE_HIT", "pit": "EEPHUS_XLINE_PIT"}
    for side in SIDES:
        rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        # Deterministic candidate order: sort by player_key, never set iteration.
        # DEBUTED rows only, because efv_dataset.py:1127 calls _milb_features with
        # (mlbam, debut_year, birth, side, cutoff=cutoff) there and the bust loop at
        # :1213 derives its decision year differently. Reconstructing with the wrong
        # arguments does not test the flag, it tests my guess: the first run of this
        # clause did exactly that (decision_year=int(cutoff[:4]), no cutoff) and left
        # 1 of 23 hitter and 4 of 22 pitcher rows matching NEITHER branch. Recorded in
        # the gate doc's result rather than quietly corrected.
        cand = sorted((r for r in rows
                       if r.get("mlbam_id") and r.get("milb")
                       and r.get("kind") == "debuted" and r.get("debut_year")),
                      key=lambda r: r["player_key"])
        differ, matches_on, matches_off, checked = [], 0, 0, 0
        prev = os.environ.get(env_key[side])
        try:
            for r in cand:
                if checked >= 400 or len(differ) >= 25:
                    break
                checked += 1
                # _milb_features is uncached and efv_statcast_line._gap_index is keyed
                # on (season, side) only, so the flag is re-read on every call and the
                # two branches below cannot be served from one cached answer.
                args = (r["mlbam_id"], int(r["debut_year"]), r.get("birth_date"), side)
                kw = {"cutoff": r.get("cutoff")}
                os.environ[env_key[side]] = "1"
                on = DS._milb_features(*args, **kw)
                os.environ[env_key[side]] = "0"
                off = DS._milb_features(*args, **kw)
                if on == off:
                    continue
                differ.append(r["player_key"])
                committed = r.get("milb")
                if committed == on:
                    matches_on += 1
                elif committed == off:
                    matches_off += 1
        finally:
            if prev is None:
                os.environ.pop(env_key[side], None)
            else:
                os.environ[env_key[side]] = prev
        res["per_side"][side] = {"checked": checked, "n_differ": len(differ),
                                 "committed_matches_flag_on": matches_on,
                                 "committed_matches_flag_off": matches_off,
                                 "examples": differ[:5]}
    return res


# --------------------------------------------------------------------------
# G6: abstention
# --------------------------------------------------------------------------

def _g6_abstention() -> dict:
    import efv_model as M
    from efv_dataset import live_matrix_path
    from efv_score import scored_live_path
    out = {"per_side": {}, "milb_missing_weight": {}}
    for side in SIDES:
        lv = json.loads(live_matrix_path(side).read_text(encoding="utf-8"))
        sc = json.loads(scored_live_path(side).read_text(encoding="utf-8"))
        no_track = [r["player_key"] for r in lv if not r.get("milb")]
        keys_scored = {s["player_key"] for s in sc}
        leaked = sorted(set(no_track) & keys_scored)
        out["per_side"][side] = {
            "n_live": len(lv), "n_no_milb": len(no_track), "n_scored_live": len(sc),
            "arithmetic_ok": (len(lv) - len(no_track)) == len(sc),
            "n_leaked_into_scored": len(leaked), "leaked_examples": leaked[:5],
        }
        w = M.served_ridge_weights(side) or {}
        zw = dict(zip(w.get("keys") or [], w.get("w") or []))
        out["milb_missing_weight"][side] = (round(zw["milb_missing"], 4)
                                            if "milb_missing" in zw else None)
    return out


# --------------------------------------------------------------------------
# LIVE-BOARD CENSUS. Descriptive, NO pass clause, and deliberately so: the gate
# doc's scope statement puts the live-only chain steps outside G1-G4 because the
# resolved cohort has no analogue for them. This counts, from committed artifacts
# and with no modelling at all, how much of the served board those steps reach --
# i.e. how much of the board the published accuracy claim is silent about.
# --------------------------------------------------------------------------

def _live_board_census() -> dict:
    import efv_score as ES
    from efv_score import scored_live_path
    knot = ES._outcome_floor_knot()
    out = {"floor_knot": knot, "per_side": {}}
    for side in SIDES:
        sc = json.loads(scored_live_path(side).read_text(encoding="utf-8"))
        n = len(sc)
        routed = [s for s in sc if s.get("grade_basis") == "provisional_capped"]
        flat = [s for s in sc if s.get("grade_basis") != "provisional_capped"
                and abs(float(s["xfv_grade"]) - knot) <= 1e-9]
        out["per_side"][side] = {
            "n_scored": n,
            # route_floor_grade returns None unless the flagship grade IS the knot,
            # so routed + flat is exactly the flagship-floor population.
            "n_flagship_grade_at_floor_knot": len(routed) + len(flat),
            "share_flagship_at_floor_knot": round((len(routed) + len(flat)) / n, 4),
            "n_served_on_provisional_map": len(routed),
            "share_served_on_provisional_map": round(len(routed) / n, 4),
            "n_served_flat_at_knot": len(flat),
            "n_carrying_statcast_tilt": sum(1 for s in sc if s.get("statcast_factor") is not None),
            "n_carrying_injury_tilt": sum(1 for s in sc if s.get("injury_factor") is not None),
            "n_carrying_xline_note": sum(1 for s in sc if s.get("xline_note")),
            "distinct_served_grades": len({round(float(s["xfv_grade"]), 1) for s in sc}),
        }
    return out


# --------------------------------------------------------------------------
# G7: the pool-relative display grade
# --------------------------------------------------------------------------

def _display_map(pool):
    """efv_score's quantile map, verbatim in structure: sort the pool's consensus_fv,
    order players by (rank_war, player_key), read the target vector at your own rank.
    pool = [(player_key, rank_war, consensus_fv)]. Returns {player_key: display}."""
    m = len(pool)
    if not m:
        return {}
    target = sorted(c for _, _, c in pool)
    order = sorted(range(m), key=lambda i: (pool[i][1], pool[i][0]))
    out = {}
    for rank_pos, i in enumerate(order):
        p = (rank_pos / (m - 1)) if m > 1 else 0.0
        pos = p * (m - 1)
        lo = int(pos)
        hi = min(m - 1, lo + 1)
        frac = pos - lo
        out[pool[i][0]] = round(target[lo] * (1 - frac) + target[hi] * frac, 1)
    return out


def _vintage_pools(dates):
    """As-of replay of the live scored pool at each date in `dates`.

    Mirrors efv_score.score_history's per-snapshot feature construction and
    run_live's abstention (no MiLB block => not scored). Both requested dates fall
    in the same season, so _milb_features is season-identical across them and is
    computed ONCE per player: any rank_war difference between the vintages is then
    a consensus-anchor difference, which is what makes the unchanged subset exact."""
    import efv_score as ES
    import efv_model as M
    from efv_dataset import (_prior_features, _milb_features, _load_sidecars,
                             _cohort_flags, _injury_features, _side_match, _f,
                             CURRENT_SEASON)

    players = json.loads((DATA / "timeseries.json").read_text(encoding="utf-8"))["players"]
    fit = {s: ES._fit_production(s) for s in SIDES}
    lam = {s: M.blend_lambda(s) for s in SIDES}
    acq, il = _load_sidecars({p["player_key"] for p in players if p.get("player_key")})

    pools = {d: {s: [] for s in SIDES} for d in dates}
    ctx = {}
    for rec in sorted(players, key=lambda r: r.get("player_key") or ""):
        pk = rec.get("player_key")
        if not pk:
            continue
        pts = sorted((pt for pt in (rec.get("points") or [])
                      if pt.get("snapshot_date") and _f(pt.get("consensus_fv_raw")) is not None),
                     key=lambda pt: pt["snapshot_date"])
        if not pts:
            continue
        side = "pit" if _side_match(rec, "pit") else "hit"
        ridge, a, b, ols, _k = fit[side]
        milb = _milb_features(rec.get("mlbam_id"), min(2026, CURRENT_SEASON) + 1,
                              rec.get("birth_date"), side)
        if not milb:
            continue                      # run_live's skipped_no_track abstention
        a_sc = acq.get(pk) or {}
        ilf = _injury_features(il.get(pk), None)
        for d in dates:
            asof = [pt for pt in pts if pt["snapshot_date"] <= d]
            if not asof:
                continue                  # not on the board at this vintage
            pt = asof[-1]
            cons_fv = _f(pt.get("consensus_fv_raw"))
            row = {"consensus_fv_raw": cons_fv, "pick_overall": a_sc.get("pick_overall"),
                   "bonus_usd": a_sc.get("bonus_usd"), "acq_year": a_sc.get("year"), **ilf}
            row["is_ifa"], row["is_college"] = _cohort_flags(
                a_sc.get("method"), a_sc.get("year"), rec.get("birth_date"))
            row.update(_prior_features(rec, pt, side))
            row["milb"] = milb
            cons_war = max(0.0, M._pred_ols(ols, cons_fv))
            model_war = max(-2.0, a + b * M._predict(ridge, M._vec(row, side)))
            rank_war = (1 - lam[side]) * cons_war + lam[side] * model_war
            pools[d][side].append((pk, rank_war, round(cons_fv, 1)))
            ctx[pk] = {"side": side, "position": rec.get("position"),
                       "age": _f(rec.get("age")), "eta": _f(rec.get("eta_years"))}
    return pools, ctx


def _g7(d1: str, d2: str) -> dict:
    import value_framework as vf
    import movement
    from efv_score import scored_live_path, PROSPECT_ETA_FALLBACK_YEARS

    pools, ctx = _vintage_pools((d1, d2))
    eps = movement._EPS
    out = {"vintages": {"d1": d1, "d2": d2}, "movement_eps": eps,
           "material_share_threshold": MATERIAL_SHARE,
           "material_share_threshold_is_self_added": True, "per_side": {}}

    for side in SIDES:
        p1 = {pk: (r, c) for pk, r, c in pools[d1][side]}
        p2 = {pk: (r, c) for pk, r, c in pools[d2][side]}
        g1 = _display_map(pools[d1][side])
        g2 = _display_map(pools[d2][side])
        both = sorted(set(p1) & set(p2))
        unchanged = [pk for pk in both
                     if p1[pk][0] == p2[pk][0] and p1[pk][1] == p2[pk][1]]

        deltas, dollars = [], []
        for pk in unchanged:
            dg = g2[pk] - g1[pk]
            deltas.append(abs(dg))
            c = ctx.get(pk) or {}
            eta = c.get("eta")
            eta = float(eta) if eta is not None else PROSPECT_ETA_FALLBACK_YEARS
            s1 = vf.expected_surplus_usd(g1[pk], side == "pit", c.get("position"),
                                         age=c.get("age"), eta_years=eta)
            s2 = vf.expected_surplus_usd(g2[pk], side == "pit", c.get("position"),
                                         age=c.get("age"), eta_years=eta)
            if s1 is not None and s2 is not None:
                dollars.append(abs(s2 - s1) / 1e6)

        # P4 full decomposition on every player present in both pools. Exactly
        # separable: G is an explicit function of (own rank_war, pool).
        own_t = pool_t = res_t = tot_t = 0.0
        for pk in both:
            r1, c1 = p1[pk]
            r2, c2 = p2[pk]
            cf_own = _display_map([(k, (r2 if k == pk else v[0]), v[1])
                                   for k, v in p1.items()])[pk]
            cf_pool = _display_map([(k, (r1 if k == pk else v[0]), v[1])
                                    for k, v in p2.items()])[pk]
            d_tot = g2[pk] - g1[pk]
            own = cf_own - g1[pk]
            pooled = cf_pool - g1[pk]
            own_t += abs(own)
            pool_t += abs(pooled)
            res_t += abs(d_tot - own - pooled)
            tot_t += abs(d_tot)

        def q(xs, f):
            return round(sorted(xs)[min(len(xs) - 1, int(f * len(xs)))], 3) if xs else None

        n_move = sum(1 for x in deltas if x >= eps)
        out["per_side"][side] = {
            "n_pool_d1": len(p1), "n_pool_d2": len(p2), "n_in_both": len(both),
            "n_unchanged": len(unchanged),
            "underpowered": len(unchanged) < 100,
            "pool_only_abs_delta_fv": {
                "median": q(deltas, 0.50), "p90": q(deltas, 0.90),
                "max": round(max(deltas), 3) if deltas else None,
                "n_over_eps": n_move,
                "share_over_eps": round(n_move / len(unchanged), 4) if unchanged else None,
            },
            "pool_only_abs_delta_surplus_mm": {
                "median": q(dollars, 0.50), "p90": q(dollars, 0.90),
                "max": round(max(dollars), 3) if dollars else None,
                "n": len(dollars),
            },
            "decomposition_share_of_total_abs_movement": {
                "own_rank": round(own_t / tot_t, 4) if tot_t else None,
                "pool_composition": round(pool_t / tot_t, 4) if tot_t else None,
                "interaction_residual": round(res_t / tot_t, 4) if tot_t else None,
                "total_abs_fv": round(tot_t, 1),
            },
        }

        # P3 replay-fidelity control: does the replay describe production at all?
        from prospect_path import _spearman
        prod = {s["player_key"]: s.get("xfv_grade_display")
                for s in json.loads(scored_live_path(side).read_text(encoding="utf-8"))}
        common = sorted(k for k in g2 if prod.get(k) is not None)
        rho = (_spearman([g2[k] for k in common], [prod[k] for k in common])
               if len(common) >= 8 else None)
        out["per_side"][side]["replay_fidelity"] = {
            "n_common": len(common), "spearman_vs_production": rho,
            "pass": bool(rho is not None and rho >= 0.80),
        }
    return out


# --------------------------------------------------------------------------

def mode_serve() -> int:
    _bootstrap_path()

    report = {"generated_at": __import__("datetime").date.today().isoformat(),
              "gate_doc": "docs/efv-2026-08-07b/SERVE_PATH_INTEGRITY.md",
              "lane": "G", "clauses": {}}

    print("G1-G4  serve-chain arms, forward-chained ...")
    report["serve_chain"] = {s: _serve_arms(s) for s in SIDES}

    g1 = {}
    for s in SIDES:
        r = report["serve_chain"][s]
        ok = True
        for m in ("baseline", "blend"):
            d = abs((r["arms"][m]["spearman"] or 0) - (r["published"][m]["spearman"] or 0))
            ok = ok and d <= 0.0010 and r["arms"][m]["n"] == r["published"][m]["n"]
        g1[s] = ok
    report["clauses"]["G1_reproduction"] = {"per_side": g1, "pass": all(g1.values())}

    g2 = {}
    for s in SIDES:
        r = report["serve_chain"][s]
        rb = r["arms"]["blend"]["spearman"]
        rs = r["arms"]["served_grade"]["spearman"]
        g2[s] = {"rho_blend": rb, "rho_served": rs, "rho_baseline": r["arms"]["baseline"]["spearman"],
                 "gap": round(rs - rb, 4), "mde95": r["mde95"],
                 "pass": bool(rs >= rb - r["mde95"]),
                 "served_loses_to_consensus": bool(rs < r["arms"]["baseline"]["spearman"])}
    report["clauses"]["G2_serve_equivalence"] = {
        "per_side": g2, "pass": all(v["pass"] for v in g2.values()), "n_tests": 2}

    g3 = {}
    for s in SIDES:
        a = report["serve_chain"][s]["arms"]
        mde = report["serve_chain"][s]["mde95"]
        tie_cost = round((a["blend_graded"]["spearman"] or 0) - (a["blend"]["spearman"] or 0), 4)
        leg_cost = round((a["served_grade"]["spearman"] or 0) - (a["blend"]["spearman"] or 0), 4)
        g3[s] = {"rho": {k: a[k]["spearman"] for k in
                         ("baseline", "ridge", "blend", "cal_affine", "grade_unrounded",
                          "served_grade", "blend_graded")},
                 "tie_and_round_cost_vs_blend": tie_cost,
                 "total_serve_cost_vs_blend": leg_cost,
                 "causes_separable_at_mde": bool(abs(tie_cost - leg_cost) > mde)}
    report["clauses"]["G3_attribution"] = g3

    g4 = {}
    for s in SIDES:
        r = report["serve_chain"][s]
        a = r["arms"]
        perm = a["served_perm"]["spearman"]
        g4[s] = {
            "C_a_permutation_rho": perm,
            "C_a_pass": bool(perm is not None and abs(perm) < 0.05),
            "C_b_floor_share": r["floor_share"],
            "C_b_distinct_served_values": r["distinct_served_values"],
            "C_b_pass": bool(r["floor_share"] is not None and r["floor_share"] <= 0.50),
            "C_c_affine_rho": a["cal_affine"]["spearman"],
            "C_c_ridge_rho": a["ridge"]["spearman"],
            "C_c_pass": bool(a["cal_affine"]["spearman"] == a["ridge"]["spearman"]),
            "C_c_bad_slope_folds": r["folds_with_nonpositive_calibration_slope"],
            "C_d_blend_graded_rho": a["blend_graded"]["spearman"],
        }
    report["clauses"]["G4_controls"] = {"per_side": g4, "n_controls": 4, "n_sides": 2}

    report["live_board_census"] = _live_board_census()

    print("G5     live-only containment ...")
    fields = _g5_field_containment()
    calls = _g5_call_sites()
    l1 = all(v == 0 for s in SIDES for v in fields[s]["train_rows_carrying"].values()) and \
        all(fields[s]["live_rows_carrying"][f] > 0 for s in SIDES for f in LIVE_ONLY_FIELDS)
    l2 = {f: sorted(set(calls[f]) - ALLOWED_OVERLAY_CALLERS) for f in OVERLAY_FUNCS}
    print("G5-L3  S-XLINE flag toggle over training rows (this reads the DB) ...")
    xline = _g5_xline()
    l3 = all(xline["per_side"][s]["n_differ"] > 0
             and xline["per_side"][s]["committed_matches_flag_on"] ==
             xline["per_side"][s]["n_differ"]
             and xline["per_side"][s]["committed_matches_flag_off"] == 0
             for s in SIDES)
    report["clauses"]["G5_live_only_containment"] = {
        "L1_fields": fields, "L1_pass": bool(l1),
        "L2_call_sites": calls, "L2_violations": l2,
        "L2_pass": all(not v for v in l2.values()),
        "L3_xline": xline, "L3_pass": bool(l3),
        "L4_estale_pass": bool(all(fields[s]["train_rows_carrying"][f] == 0
                                   and fields[s]["live_rows_carrying"][f] > 0
                                   for s in SIDES
                                   for f in ("fv_effective", "anchor_stale_discount"))),
    }

    print("G6     abstention ...")
    g6 = _g6_abstention()
    g6["A1_pass"] = all(g6["per_side"][s]["arithmetic_ok"] for s in SIDES)
    g6["A2_pass"] = all(g6["per_side"][s]["n_leaked_into_scored"] == 0 for s in SIDES)
    g6["A3_pass"] = any((g6["milb_missing_weight"][s] or 0) < 0 for s in SIDES)
    report["clauses"]["G6_abstention"] = g6

    print("G7     pool-relative display grade, two-vintage replay (slow) ...")
    g7 = _g7(VINTAGE_D1, VINTAGE_D2)
    mat = {}
    for s in SIDES:
        d = g7["per_side"][s]
        share = d["pool_only_abs_delta_fv"]["share_over_eps"]
        mat[s] = (None if d["underpowered"] else
                  bool(share is not None and share >= MATERIAL_SHARE))
    g7["material"] = mat
    print("G7-S   sensitivity vintage pair (supplementary) ...")
    q = _g7(VINTAGE_Q1, VINTAGE_Q2)
    q["role"] = ("SUPPLEMENTARY sensitivity, added after the pre-registered pair "
                 "returned. Decides no verdict. The pre-registered pair brackets the "
                 "2026-08-07 refresh; this pair is a routine adjacent day.")
    g7["sensitivity_quiet_pair"] = q
    report["clauses"]["G7_pool_relative_display"] = g7

    SERVE_OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"\nwrote {SERVE_OUT}")
    for k, v in report["clauses"].items():
        print(" ", k, json.dumps(v)[:200])
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        raise SystemExit(mode_serve())
    raise SystemExit(main())
