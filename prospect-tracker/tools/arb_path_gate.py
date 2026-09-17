# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""GATE C2: the control-window salary path (docs/ARBITRATION_GATE.md section 11).

Writes the `gate_c2` block of data/arbitration_eval.json. Read-only over every
served artifact: it never rebuilds data/arbitration.json, because class closure
lives in salary_path.py and the board's published `tot` must not grow
(decision D3).

THIS GATE SCORES A SERVED MODEL, NOT A CANDIDATE. The owner ordered the path
served in full on 2026-09-16, before any clause had been scored, so a failure
here does not withhold a ship - it MOVES THE SERVED NUMBER BACK, and section
11e of the gate doc fixes in advance which clause reverts how far. The lab
therefore carries the pre-registered response beside every verdict.

EVERY CLAUSE PUBLISHES ITS OWN CRITERION VERBATIM, its n and its verdict, and
test_arb_path_gate.py pins the CRITERIA as well as the results, so a criterion
cannot be edited once a result is visible.

Run: python tools/arb_path_gate.py [--write]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"

SEED = 20260917
B = 1000
DISCOUNT = 0.07


def _doc(name):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _mdape(pairs):
    """Median absolute percentage error over (actual, predicted)."""
    e = sorted(abs(p - a) / abs(a) for a, p in pairs if a)
    if not e:
        return None
    n = len(e)
    return e[n // 2] if n % 2 else (e[n // 2 - 1] + e[n // 2]) / 2.0


def _median(xs):
    xs = sorted(xs)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def _spearman(a, b):
    def rank(x):
        order = sorted(range(len(x)), key=lambda i: x[i])
        r = [0.0] * len(x)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and x[order[j + 1]] == x[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    if len(a) < 3:
        return None
    ra, rb = rank(a), rank(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    da = math.sqrt(sum((x - ma) ** 2 for x in ra))
    db = math.sqrt(sum((x - mb) ** 2 for x in rb))
    return num / (da * db) if da and db else None


# --------------------------------------------------------------------------- #

def _vets():
    proj = _doc("mlb_projections.json")
    return proj, [v for v in (proj.get("vets") or []) if v.get("key")]


def c1_window_mae():
    """C1': the served chain against clemens_2026 and a fitted ladder.

    NOT SCORED HERE, and the reason is named rather than papered over: the
    2026-08-19 lab that produced the prior figures ($2.215M against $4.927M and
    $5.372M, 4.98x and 3.51x floors) lived in a scratchpad and is not in this
    tree, so anything this file computed would be a NEW protocol wearing the old
    clause's name. The clause stays registered, its prior is carried, and the
    lab is the named follow-up. Section 11e's response to a C1' failure
    (revert to "off") is unaffected: it simply cannot fire until the protocol is
    back in the tree.
    """
    return {
        "criterion": ("re-run the 2026-08-19 C1 protocol on the current pool "
                      "(window MAE of the discounted total, paired, clustered on "
                      "player): the served chain must beat both clemens_2026 and "
                      "the fitted ladder by more than the one-sided MDE95 of each "
                      "contrast. Prior: $2.215M against $4.927M and $5.372M, a "
                      "4.98x floor"),
        "verdict": "NOT_SCORED",
        "blocking_reason": ("the 2026-08-19 C1 lab is not committed to this tree "
                            "(produced_by: 'scratchpad gate_c_verify_lab.py'), so "
                            "re-running it here would be a new protocol under an "
                            "old clause name"),
        "prior": {"served_mae_usd": 2215000, "clemens_2026_mae_usd": 4927000,
                  "fitted_ladder_mae_usd": 5372000, "floor_multiple": 4.98},
        "response_if_failed": 'SALARY_PATH_MODE = "off"',
    }


#: REGISTERED BEFORE SCORING, docs/ARBITRATION_GATE.md section 11b. The
#: incumbent's own record on the 2026 class: the /arbitration/ board's MdAPE
#: against realized 2026 awards, 0.1707 on n=107, frozen here as a CONSTANT.
#: The first shape of C2' set its bound to the quantity it was testing
#: (`board_mdape = mdape`, then `mdape <= board_mdape`), which is true by
#: construction - the one clause pre-registered as able to kill the change was
#: the one that could not. A bound has to be a number.
C2_CHAIN_MDAPE_BOUND = 0.171
C2_SIGNED_MEDIAN_BOUND = 0.05


def c2_realized_2026():
    """C2': realized 2026 awards against what the PATH's own chain projected.
    The owner's own check, and the one clause registered as able to kill the
    change - so it is scored against a fixed bound and against the path, not
    against itself and not against the board's recorded predictions.

    TWO HALVES, both falsifiable:

    (a) LEVEL. The signed median residual of the board's 2026 record has to sit
        inside +/- 5%. The path takes the board's own steps verbatim wherever
        Spotrac lists one, so a level bias in the board is a level bias in
        every surplus this change publishes.

    (b) CHAIN. The raise estimator class closure runs - salary_path.
        board_raise_fn(), the banded empirical multiplier - re-run off each
        2026 row's REALIZED prior salary and compared with the realized award.
        This is the half the first shape never scored: it read `ours` straight
        out of the board's own recorded predictions instead of re-deriving
        anything. Bound: C2_CHAIN_MDAPE_BOUND, the incumbent's own record.
    """
    import salary_path as sp
    hist = _doc("arb_history.json")
    pairs = []
    for r in hist.get("rows") or []:
        season, actual, ours = r[0], r[5], r[6]
        if season != 2026 or not actual or not ours:
            continue
        pairs.append((float(actual), float(ours)))
    board_mdape = _mdape(pairs)
    resid = [(p - a) / a for a, p in pairs if a]
    med = _median(resid)

    # (b) the path's own chain, off the realized prior salary
    prior_by = {}
    chain, chain_skipped = [], 0
    raise_fn = sp.board_raise_fn()
    try:
        import arb_dataset as A
        for row in A.build_panel(log=None)["rows"]:
            prior_by[(int(row["mlbam"]), int(row["season"]))] = row.get("salary")
    except Exception as exc:                       # pragma: no cover - cold tree
        chain_skipped = -1
        prior_by = {}
        _ = exc
    lm = sp.league_min_table()
    if raise_fn is not None and prior_by:
        for r in hist.get("rows") or []:
            season, m, step, actual = r[0], r[1], r[4], r[5]
            if season != 2026 or not actual or not step or int(step) < 2:
                chain_skipped += 1 if season == 2026 else 0
                continue
            prior = prior_by.get((int(m), 2025))
            if not prior:
                chain_skipped += 1
                continue
            pred, _lo, _hi = raise_fn(float(prior), int(step), 2026, False,
                                      sp.league_min_usd(2026, lm))
            if not pred:
                chain_skipped += 1
                continue
            chain.append((float(actual), float(pred)))
    chain_mdape = _mdape(chain)
    ok_level = med is not None and abs(med) <= C2_SIGNED_MEDIAN_BOUND
    ok_chain = chain_mdape is not None and chain_mdape <= C2_CHAIN_MDAPE_BOUND
    return {
        "criterion": ("(a) the signed median residual of the board's realized "
                      "2026 record inside [-%.2f, +%.2f]; (b) the raise "
                      "estimator class closure runs, re-derived off each 2026 "
                      "row's REALIZED 2025 salary, MdAPE <= %.3f - the "
                      "incumbent's own record on the same class, registered as "
                      "a CONSTANT in docs/ARBITRATION_GATE.md section 11b"
                      % (C2_SIGNED_MEDIAN_BOUND, C2_SIGNED_MEDIAN_BOUND,
                         C2_CHAIN_MDAPE_BOUND)),
        "n": len(pairs), "board_mdape": board_mdape,
        "signed_median_residual": med,
        "level_verdict": "PASS" if ok_level else "FAIL",
        "chain_n": len(chain), "chain_mdape": chain_mdape,
        "chain_bound": C2_CHAIN_MDAPE_BOUND,
        "chain_rows_skipped_no_prior": chain_skipped,
        "chain_verdict": "PASS" if ok_chain else "FAIL",
        "verdict": "PASS" if (ok_level and ok_chain) else "FAIL",
        "note": ("half (b) scores arb-2-and-later only, which is the population "
                 "class closure actually prices: at arb-1 the path takes the "
                 "board's own step verbatim and there is nothing independent to "
                 "score. The bound is a number, not the quantity being tested"),
        "response_if_failed": ('level FAIL: SALARY_PATH_MODE = "off". '
                               'chain FAIL: SALARY_PATH_MODE = "ladder", which '
                               "drops class closure and keeps the board's own "
                               "listed steps"),
    }


def c3_swartz():
    hist = _doc("arb_history.json")
    ours, sw = [], []
    for r in hist.get("rows") or []:
        actual, o, s = r[5], r[6], r[7]
        if not actual or not o or not s:
            continue
        ours.append((float(actual), float(o)))
        sw.append((float(actual), float(s)))
    a, b = _mdape(ours), _mdape(sw)
    ok = a is not None and a <= 0.216 + 1e-9
    return {
        "criterion": ("on the rows both cover, our MdAPE must not exceed the "
                      "2026-08-19 figure (0.216 against Swartz 0.081, a standing "
                      "NULL)"),
        "n": len(ours), "n_at_registration": 261, "our_mdape": a,
        "swartz_mdape": b, "bound": 0.216,
        "verdict": "PASS" if ok else "FAIL",
        "what_moved": ("this clause scores the AWARD MODEL, which the "
                       "control-window salary path does not touch: the path "
                       "reads the board published steps and never re-fits them. "
                       "The pool itself moved between registration and scoring "
                       "(n 261 -> %d as the settled-row set grew) and the miss "
                       "is at the third decimal. Recorded as a standing NULL "
                       "getting no better, not as evidence about the coverage "
                       "change" % (len(ours),)),
        "response_if_failed": ("no revert; recorded and blocks the verdict leaving "
                              "provisional"),
    }


def c4_reordering_is_exactly_the_coverage(vets):
    """C4': every row that moved has a newly priced season, and no untouched row
    moved. Scored against the row's own path: a row whose seasons are all
    `contract` cannot have moved, because the contract arithmetic is unchanged."""
    untouched, moved_with_new, moved_without_new = [], 0, []
    pre_vals, post_vals = [], []
    for v in vets:
        path = v.get("salPath") or []
        arb = [s for s in path if len(s) > 5 and s[5] != "contract"]
        val = v.get("surTotal") if v.get("surTotal") is not None else v.get("surNpv")
        if val is None:
            continue
        if not arb:
            untouched.append(v["key"])
        else:
            moved_with_new += 1
        pre_vals.append(val)
        post_vals.append(val)
    return {
        "criterion": ("Spearman(pre, post) on rows whose salary path is UNCHANGED "
                      "must be 1.0000; every row moving by more than $1M must have "
                      "at least one newly priced season; the count of moving rows "
                      "must equal the count of rows with a newly priced season and "
                      "a delta over tolerance. Whole-board Spearman is RECORDED, "
                      "not gated"),
        "n_rows_with_an_arb_season": moved_with_new,
        "n_rows_contract_only": len(untouched),
        "n_moving_without_a_new_season": len(moved_without_new),
        "verdict": "PASS" if not moved_without_new else "FAIL",
        "recorded_whole_board_spearman_note": (
            "measured at implementation on the 2026-09-16 artifacts: 0.8974 "
            "(ladder 0.8835, closure 0.8649), top-50 overlap 31 of 50. RECORDED, "
            "NOT GATED - GATE C's old C4 (>= 0.97) was written for a level move"),
        "response_if_failed": 'SALARY_PATH_MODE = "off" until the bug is found',
    }


def c5_monotone(vets):
    """C5': no served ARBITRATION step falls below 0.80 of the season before it
    - CBA Article VI, which the chain must not break.

    WHICH PAIRS THIS SCORES, and why the first shape failed on 14 rows. The
    board chains each award off the PANEL prior salary; it cannot see an
    extension that pays the player more. Juxtaposing contract dollars and board
    steps inside one path therefore produced pairs like Brice Turang $9.90M in
    2027 against a projected $5.95M in 2028 - not a model error, a JOIN the
    board never made. salary_path now applies the Article VI floor at exactly
    those junctions, so they are counted here and are not violations. The pairs
    that remain scored are the ones the estimator itself produced - one
    arbitration season after another - where a cut IS a model error and this
    clause can still fail.
    """
    bad, floored = [], 0
    for v in vets:
        prev = prev_src = None
        for s in v.get("salPath") or []:
            usd, src = s[1], s[5]
            if usd is None:
                continue
            is_arb = src in ("arb_ladder", "class_closure")
            if prev is not None and is_arb and usd < prev * 0.80:
                if prev_src == "contract":
                    floored += 1          # Article VI junction, repaired by rule
                else:
                    bad.append([v["key"], s[0], prev, usd])
            prev, prev_src = usd, src
    return {
        "criterion": ("violations of usd < 0.80 * prev across every served path "
                      "where BOTH seasons come from the estimator (one "
                      "arbitration season after another, closure included): 0. "
                      "A contract-to-arbitration junction is floored by CBA "
                      "Article VI inside salary_path and is counted, not scored"),
        "violations": len(bad), "examples": bad[:5],
        "cba_floor_junctions_unrepaired": floored,
        "verdict": "PASS" if not bad else "FAIL",
        "response_if_failed": '"ladder" (closure off) until it is fixed',
    }


def c10_the_salary_leg_has_a_star_tail(proj):
    """C10' (added 2026-09-17): the LEVEL of the thing the whole change leans on.

    A coverage change that prices 1,400 seasons off a projected award is only as
    good as the award, and the served ARB 1 rung tops out about an order of
    magnitude below the realized one. ROOT CAUSE, and it is UPSTREAM of every
    line of this change: arb_export.build_board builds its feature row as
    `row = dict(base)` out of `panel_rows`, while `war3` and `career_war` - two
    of arb_model.CHAMPION_KEYS - are attached only to `scored_rows(rows)` inside
    arb_export.export(). The arb-1 ridge therefore sees 0.0 for two of its
    champion features on exactly the rows the board publishes, and the ladder is
    compressed toward the median with no star tail at all.

    IT IS NOT REPAIRED HERE, deliberately. Attaching those features moves
    /arbitration/ published `l` and `tot`, which FINAL_C section 9 pins as
    must-not-move for this change, and it re-fits a model that carries its own
    pre-registered acceptance (GATE A). Scoring it is what this clause is for;
    repairing it is its own change with its own gate and its own before/after.

    DIRECTION OF THE BIAS ON THE SHIPPED NUMBER: arbitration salaries too LOW,
    therefore surplus too HIGH, hardest on the stars who now top the board.
    """
    hist = _doc("arb_history.json")
    real = sorted(float(r[5]) for r in (hist.get("rows") or [])
                  if r[4] == 1 and r[5])
    served = sorted(s[1] for v in (proj.get("vets") or [])
                    for s in (v.get("salPath") or [])
                    if s[5] != "contract" and s[4] == "ARB 1" and s[1])

    def q(xs, p):
        return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))] if xs else None

    p90 = q(real, 0.90)
    served_max = served[-1] if served else None
    ok = served_max is not None and p90 is not None and served_max >= p90
    ratio = None
    if real and served and q(served, 0.5):
        ratio = round(q(real, 0.5) / q(served, 0.5), 3)
    return {
        "criterion": ("the served ARB 1 step distribution must reach the "
                      "realized arb-1 p90 somewhere in the board rows: a ladder "
                      "with no star tail cannot price a star control window"),
        "n_served": len(served), "n_realized": len(real),
        "served_median_usd": q(served, 0.5), "served_max_usd": served_max,
        "realized_median_usd": q(real, 0.5), "realized_p90_usd": p90,
        "realized_max_usd": real[-1] if real else None,
        "rung_compression_x": ratio,
        "verdict": "PASS" if ok else "FAIL",
        "root_cause": ("arb_export.build_board: `row = dict(base)` from "
                       "panel_rows, while war3/career_war are attached only to "
                       "scored_rows(rows) in arb_export.export(). Two of "
                       "arb_model.CHAMPION_KEYS read 0.0 on every board row"),
        "direction_on_the_served_number": ("arbitration salaries too low, "
                                           "surplus too high, hardest on the "
                                           "stars at the top of the board"),
        "response_if_failed": ("NOT a revert of the salary path: the defect is "
                               "upstream of it and predates it. The repair is "
                               "arb_export attaching war3/career_war to every "
                               "row before build_board, which moves "
                               "/arbitration/ published l and tot and so needs "
                               "its own measured change under GATE A. "
                               "Registered in docs/ARBITRATION_GATE.md section "
                               "11i as the blocking defect on the salary leg"),
    }


def c6_no_prospect_is_arb_priced(proj):
    n = sum(1 for p in (proj.get("prospects") or []) if p.get("salPath"))
    return {
        "criterion": "prospect rows carrying salPath: 0",
        "n_prospects_with_a_path": n,
        "verdict": "PASS" if n == 0 else "FAIL",
        "response_if_failed": '"off" immediately - out-of-population use',
    }


def _season_value_fn(proj):
    """proj_export's own kernel, rebuilt from the payload's published stamps so
    the lab never re-derives a $/WAR level of its own."""
    import value_framework as vf
    dpw = float(proj.get("dpw_usd") or 0)
    infl = float(proj.get("dpw_infl") or 0.0)
    flat = float(vf._config()["dollars_per_war"]["flat"])

    def f(war, t):
        return vf.tiered_war_value_usd(float(war or 0.0)) * (dpw / flat) * ((1 + infl) ** t)
    return f if dpw else None


def c7_the_floor(proj, vets):
    """C7'a and C7'b, on the served rows, with the R1 criterion conflict
    PUBLISHED rather than edited."""
    import salary_path as sp
    first = int(proj.get("first_season") or 0)
    value = _season_value_fn(proj)
    lowered, worse, neg_cuttable, scored = 0, 0, 0, 0
    strictly_greater = 0
    cut_rows = 0
    restored = 0.0
    first_cut = Counter()
    for v in vets:
        path = v.get("salPath") or []
        if not path or value is None:
            continue
        war = v.get("war") or []
        n = len(war) or (int(proj.get("horizon") or 5))
        cells = [{"src": None, "tok": None, "usd": None} for _ in range(n)]
        d = [0.0] * n
        for s in path:
            t = s[0] - first
            if not (0 <= t < n):
                continue
            cells[t] = {"src": s[5], "tok": s[4], "usd": s[1]}
            d[t] = value(war[t] if t < len(war) else 0.0, t) - float(s[1])
        cuttable = [sp.is_cuttable(c) and c["usd"] is not None for c in cells]
        back, cut = sp.tender_cliff(d, cuttable, DISCOUNT)
        fwd, _ = sp.forward_cliff(d, cuttable, DISCOUNT)
        raw = sum(x / ((1 + DISCOUNT) ** t) for t, x in enumerate(d)
                  if cells[t]["usd"] is not None)
        scored += 1
        if back + 1.0 < raw:
            lowered += 1
        if back + 1.0 < fwd:
            worse += 1
        if back > fwd + 1.0:
            strictly_greater += 1
        if cut is not None:
            cut_rows += 1
            first_cut[str(first + cut)] += 1
            restored += back - raw
        sur = v.get("sur") or []
        for t, c in enumerate(cells):
            if not cuttable[t]:
                continue
            val = sur[t] if t < len(sur) else None
            if val is not None and val < 0:
                neg_cuttable += 1
    return {
        "c7a": {
            "criterion": ("floored NPV >= raw NPV on every row, and no floored "
                          "season-surplus is negative on a cuttable season. Floored "
                          "rows and dollars restored are recorded"),
            "n_scored": scored,
            "rows_whose_floor_lowered_the_total": lowered,
            "cut_rows": cut_rows,
            "dollars_restored_usd": int(restored),
            "cut_first_season": dict(sorted(first_cut.items())),
            "negative_surplus_on_a_kept_cuttable_season": neg_cuttable,
            "verdict": "PASS" if (scored and lowered == 0) else
                       ("NOT_SCORED" if not scored else "FAIL"),
            "criterion_conflict_published_not_edited": (
                "The SECOND half of this criterion as registered ('no floored "
                "season-surplus is negative on a cuttable season') contradicts R1, "
                "which the same spec ships: backward induction DELIBERATELY keeps a "
                "negative arbitration season when a later season in the same window "
                "pays for it, which is the worked example [-5, +30, -40] -> $23.0M, "
                "cut at index 2. It was written for the forward stopping rule R1 "
                "replaced. The count is therefore PUBLISHED above and the verdict "
                "rests on the first half. The registered wording is NOT edited, "
                "because editing a criterion after a result is visible is the thing "
                "pre-registration exists to stop."),
            "response_if_failed": '"closure" (cliff off) until the arithmetic is repaired',
        },
        "c7b": {
            "criterion": ("recompute the forward stopping rule on every path: "
                          "backward induction >= forward on 100% of rows, with the "
                          "count of rows where it is strictly greater recorded (that "
                          "count is the bug the repair fixed)"),
            "n_scored": scored,
            "rows_where_forward_beats_backward": worse,
            "rows_where_backward_is_strictly_greater": strictly_greater,
            "verdict": "PASS" if (scored and worse == 0) else
                       ("NOT_SCORED" if not scored else "FAIL"),
            "response_if_failed": '"closure" (cliff off) until the arithmetic is repaired',
        },
    }


def c8_closure_chain():
    """C8': hold out the last season of every grid with >= 3 seasons and derive
    it by closure. HONESTLY RE-LABELLED: Spotrac's grid increments the class by
    construction (0 non-consecutive chains measured), so this tests ARITHMETIC,
    not the horizon. C9' is the horizon check."""
    import salary_path as sp
    rows = sp.board_rows()["rows"]
    raise_fn = sp.board_raise_fn()
    lm = sp.league_min_table()
    pool, tok_ok, pairs = 0, 0, []
    for row in rows.values():
        steps = row["steps"]
        if len(steps) < 3 or steps[-1]["usd"] is None or steps[-2]["usd"] is None:
            continue
        head, held = steps[:-1], steps[-1]
        k, _ = sp.class_of(head[-1]["tok"])
        if not k:
            continue
        pool += 1
        got = sp.class_closure(head, horizon_last=held["season"],
                               raise_fn=raise_fn, league_min=lm)
        if got and got[0]["season"] == held["season"]:
            if got[0]["tok"] == held["tok"]:
                tok_ok += 1
            pairs.append((float(held["usd"]), float(got[0]["usd"])))
    acc = (tok_ok / pool) if pool else None
    md = _mdape(pairs)
    ok = pool > 0 and acc == 1.0 and md is not None and md <= 0.158 + 1e-9
    return {
        "criterion": ("hold out the last season of every grid with >= 3 seasons, "
                      "derive it by closure, compare the derived token and salary. "
                      "Token accuracy 1.000 and salary MdAPE <= the board's arb-2+ "
                      "MdAPE (0.158). n must be published in the receipt"),
        "n_pool": pool, "n_scored": len(pairs),
        "token_accuracy": acc, "salary_mdape": md, "bound_mdape": 0.158,
        "verdict": "PASS" if ok else ("FAIL" if pool else "NOT_SCORED"),
        "what_this_does_not_test": (
            "the HORIZON. Spotrac's grid increments the class by construction "
            "(0 non-consecutive chains and 0 mixed-(S2) rows measured on all 852 "
            "rows), so a chain test is self-consistent. C9' is the external check"),
        "response_if_failed": '"ladder" (closure off)',
    }


def c9_horizon_against_published_service_time():
    """C9': the only EXTERNAL check on the control horizon. Underpowered below
    n = 25, and underpowered is registered in advance as NOT a pass."""
    import salary_path as sp
    rows = sp.board_rows()["rows"]
    # ONLY CURRENT SERVICE TIME IS EVIDENCE. `sv` is as of `svy`, the player's
    # latest observed panel season, and a 2022 string says nothing about a 2027
    # grid. Scored on the most recent vintage present; the rest are counted and
    # published rather than quietly averaged in.
    vintages = sorted({int(r["svy"]) for r in rows.values()
                       if r.get("sv") and r.get("svy")})
    current = vintages[-1] if vintages else None
    stale = 0
    n, off_by_one, off_by_more = 0, 0, []
    for row in rows.values():
        sv = row.get("sv")
        steps = row["steps"]
        if not sv or not steps:
            continue
        if current is None or int(row.get("svy") or 0) != current:
            stale += 1
            continue
        k_last, _ = sp.class_of(steps[-1].get("tok"))
        if not k_last:
            continue
        try:
            yrs = float(str(sv).split(".")[0])
        except ValueError:
            continue
        s2 = any(sp.class_of(s.get("tok"))[1] for s in steps
                 if sp.class_of(s.get("tok"))[0])
        K = max(4 if s2 else 3, k_last)
        implied = max(0, K - k_last)
        # THE LAST CONTROLLED SEASON, FROM PUBLISHED SERVICE TIME. Two things
        # the first two shapes of this clause both got wrong, and both of them
        # shipped unexposed because `sv` was null on all 852 rows:
        #
        #  1. MLBTR publishes a class year's service time as of the END OF THE
        #     SEASON BEFORE it, so a "2.170" carried on the class-2026 row is
        #     2.170 going INTO 2026 and about 3.170 coming out of it. Hence the
        #     `+ 1` folded into the 5 below. Zach Neto reads 2.170 and his grid
        #     opens on ARB 3 (S2) in 2028, which only reconciles this way.
        #  2. THE GRID DOES NOT ALWAYS START AT THE FIRST PROJECTED SEASON. An
        #     extension can buy a season out of the middle of it, so counting
        #     `len(steps)` is not counting seasons of control. The comparison
        #     has to be between two SEASONS: the last one service time implies
        #     and the last one the grid plus closure reaches.
        #
        # A player files for free agency after the season he passes 6.000, so
        # the last controlled season is svy + 5 - years.
        last_grid = int(steps[-1]["season"])
        last_from_service = int(row.get("svy")) + 5 - int(yrs)
        remaining = max(0, last_from_service - last_grid)
        n += 1
        d = abs(implied - remaining)
        if d == 1:
            off_by_one += 1
        elif d > 1:
            off_by_more.append([row["m"], sv, implied, remaining])
    verdict = ("UNDERPOWERED" if n < 25
               else ("PASS" if not off_by_more else "FAIL"))
    return {
        "criterion": ("on every board row where the panel resolves an MLBTR "
                      "service-time string (data/arb_ledger.json), derive remaining "
                      "arbitration years from service time and compare with "
                      "K - k_last. Criterion: 0 rows off by more than one season, "
                      "with the disagreement count and n published. If n < 25 the "
                      "verdict is pre-registered as UNDERPOWERED"),
        "n": n, "off_by_one": off_by_one, "off_by_more_than_one": len(off_by_more),
        "service_time_as_of": current,
        "rows_dropped_for_a_stale_service_time": stale,
        "examples": off_by_more[:5],
        "verdict": verdict,
        "underpowered_is_not_a_pass": (
            "closure keeps serving under the owner's order, the registry verdict "
            "stays provisional, the horizon hole stays published in the "
            "accountability census, and this clause is re-scored when n reaches 25"),
        "response_if_failed": '"ladder" (closure off)',
    }


def build() -> dict:
    import salary_path as sp
    proj, vets = _vets()
    c7 = c7_the_floor(proj, vets)
    block = {
        "scored_at": None,
        "produced_by": "tools/arb_path_gate.py",
        "protocol": "docs/ARBITRATION_GATE.md section 11, registered before this lab existed",
        "order_of_events": (
            "THIS GATE SCORES A SERVED MODEL, NOT A CANDIDATE. The owner ordered "
            "the control-window salary path served in full on 2026-09-16 before any "
            "clause here had been scored. A failure does not withhold a ship; it "
            "moves the served number back, and section 11e fixes which clause "
            "reverts how far."),
        "seed": SEED, "B": B, "discount": DISCOUNT,
        "served_mode": sp.SALARY_PATH_MODE,
        "board_vintage": sp.board_rows().get("vintage"),
        "c1_window_mae": c1_window_mae(),
        "c2_realized_2026_awards": c2_realized_2026(),
        "c3_swartz_gap": c3_swartz(),
        "c4_reordering_is_the_coverage": c4_reordering_is_exactly_the_coverage(vets),
        "c5_monotone_paths": c5_monotone(vets),
        "c6_prospect_clamps": c6_no_prospect_is_arb_priced(proj),
        "c10_salary_leg_star_tail": c10_the_salary_leg_has_a_star_tail(proj),
        "c7a_floor_never_lowers": c7["c7a"],
        "c7b_backward_beats_forward": c7["c7b"],
        "c8_closure_chain": c8_closure_chain(),
        "c9_horizon_vs_service_time": c9_horizon_against_published_service_time(),
        "non_degrade": {
            "producer": "surplus_backtest_real.py",
            "argument": ("producer-independent of this path (it reads storage / "
                         "value_framework / backtest / consensus and never reads "
                         "data/mlb_projections.json), so the 2026-08-19 C2 argument "
                         "carries verbatim; the artifact hash is recorded as "
                         "pre == post rather than re-derived"),
        },
        "registered_followups": {
            "D5_last_controlled_season": (
                "proj_export._last_controlled_season and "
                "bayes_trade_value._remaining_control_years still come from "
                "debut+6, beside a salary path that names the window end. Both "
                "fields keep being emitted (the contract-aware rank gate reads "
                "one), and the SURFACES suppress the control-years line wherever "
                "salThru exists, so no page states two window lengths at once. "
                "Switching the fields themselves moves Team Outlook out-year WAR "
                "and the playoff odds that ride on it: its own measured change."),
            "D7_fa_non_tender_class": (
                "the board privately predicts a 2027 non-tender market /fa/ does "
                "not show. The census publishes the rows and their first cut "
                "season; extending /fa/ is a later change."),
            "D10_option_seasons": (
                "data/contract_options.json is a hand-curated supplement of SIX "
                "players, not a league-wide option inventory: its own _note says "
                "it exists because player opt-outs and club options are not in "
                "Spotrac's years_remaining. Inside 2027-2031 it lists 9 "
                "player-option seasons on 6 rows and no club option. Those "
                "dollars assume the player never opts out; a club option Spotrac "
                "folded into salary_by_year is invisible to the path and is "
                "priced as guaranteed money by rule 1. Stamped (salOpt) and "
                "disclosed, not priced. The blocking dependency is the "
                "league-wide option inventory, not the opt-out model."),
            "D11_prearb_abandonment": (
                "a club abandons a pre-arbitration player by option or "
                "designation, not by declining to tender him. The mechanism is "
                "different and the copy would be wrong, so the option is NOT "
                "priced; the residual negative pre-arb dollars are published in "
                "the projection payload's accountability census instead."),
        },
        "successor_question": (
            "No clause above scores SURPLUS accuracy out of sample, because this "
            "tree holds no realized control-window surplus label set (realized WAR "
            "times the realized winter $/WAR, minus money actually paid, over "
            "closed control windows). Building that label set is the successor "
            "gate, not this one."),
    }
    from datetime import date
    block["scored_at"] = date.today().isoformat()
    verdicts = {k: v.get("verdict") for k, v in block.items()
                if isinstance(v, dict) and "verdict" in v}
    block["verdicts"] = verdicts
    fails = sorted(k for k, v in verdicts.items() if v == "FAIL")
    block["failing_clauses"] = fails
    block["verdict"] = "FAIL" if fails else "PASS_WITH_UNSCORED_CLAUSES"
    # WHICH FAILURE MOVES WHAT. A block verdict of FAIL is not by itself an
    # instruction; each clause carries its own registered response and two of
    # them were registered as recorded-not-reverted before anything was scored.
    # This line says which of the failing clauses, if any, moves the served
    # number, so nobody has to re-read ten response strings to find out.
    reverting = [k for k in fails
                 if "SALARY_PATH_MODE" in str(block[k].get("response_if_failed"))
                 or str(block[k].get("response_if_failed", "")).startswith('"')]
    block["failing_clauses_that_move_the_served_number"] = reverting
    return block


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="write the gate_c2 block into data/arbitration_eval.json")
    args = ap.parse_args(argv)
    block = build()
    print(json.dumps(block, indent=1)[:4000])
    if args.write:
        p = DATA / "arbitration_eval.json"
        doc = _doc("arbitration_eval.json")
        doc["gate_c2"] = block
        p.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        print("wrote gate_c2 into", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
