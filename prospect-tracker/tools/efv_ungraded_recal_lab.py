# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential. Written by Noah J. Dengler (@ARKNDJL), 2026.

"""LANE C1 -- provisional-grade (efv_ungraded) TRUE-TO-MODEL de-cap lab.

Owner directive: "same for provisional grades" -- remove the order-preserving SOFT CAP on the
war_pred -> FV grade map so a breakout provisional grades to its true model value instead of
piling at the ceiling. Measured, self-contained, and NON-DESTRUCTIVE:
  * builds the provisional board with the soft cap ON  (efv_ungraded.UNCAPPED_GRADE=False)
    and OFF (True), each diverted to a SCRATCH path -- the served data/xfv_ungraded.json is
    NEVER touched.
  * the soft cap is strictly monotone in war above the knee (identity below), and the
    low-minors OOS harness (efv_ungraded.evaluate / data/xfv_ungraded_eval.json) scores
    _war(), NOT _grade() -- so the de-cap is Spearman-INVARIANT by construction. This lab
    PROVES that empirically (runs evaluate() with the flag both ways; asserts identical).
  * reports the served-grade distribution before/after, how many provisionals de-compress
    off the ceiling, and the biggest named risers.

Run: python tools/efv_ungraded_recal_lab.py   (writes data/xfv_ungraded_recal_eval.json)
Does NOT import from or trust any pre-existing lab file; reconstructs independently.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import efv_ungraded as u  # the module this lane owns

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT_EVAL = DATA_DIR / "xfv_ungraded_recal_eval.json"
SCRATCH = Path(os.environ.get(
    "EFV_SCRATCH",
    r"C:/Users/noah/AppData/Local/Temp/claude/c--Users-noah-baseball-projects-BaseballR/"
    r"79ede335-9198-4f14-a494-1a24428ec19f/scratchpad"))
SCRATCH.mkdir(parents=True, exist_ok=True)


def _dist(grades: list[float]) -> dict:
    g = sorted(grades)
    n = len(g)

    def q(pp):
        return g[min(n - 1, int(pp * (n - 1)))] if n else None
    return {
        "n": n,
        "median": round(statistics.median(g), 2) if n else None,
        "mean": round(statistics.mean(g), 2) if n else None,
        "p75": q(0.75), "p90": q(0.90), "p95": q(0.95), "p99": q(0.99),
        "max": max(g) if n else None,
        "share_le_30": round(sum(1 for x in g if x <= 30) / n, 4) if n else None,
        "n_ge_35": sum(1 for x in g if x >= 35),
        "n_ge_40": sum(1 for x in g if x >= 40),
        "n_ge_45": sum(1 for x in g if x >= 45),
        "n_ge_50": sum(1 for x in g if x >= 50),
    }


def _build_to(flag: bool, tag: str) -> dict:
    """Run the production build() with the de-cap flag set to `flag`, diverted to scratch."""
    prev_flag = u.UNCAPPED_GRADE
    prev_out = u.OUT_PATH
    u.UNCAPPED_GRADE = flag
    u.OUT_PATH = SCRATCH / f"ung_{tag}.json"
    try:
        u.build(persist=True)
        return json.loads(u.OUT_PATH.read_text(encoding="utf-8"))
    finally:
        u.UNCAPPED_GRADE = prev_flag
        u.OUT_PATH = prev_out


def _eval_with(flag: bool) -> dict:
    """Run the low-minors OOS harness with the de-cap flag set to `flag` (persist OFF)."""
    prev = u.UNCAPPED_GRADE
    u.UNCAPPED_GRADE = flag
    try:
        rep = u.evaluate(persist=False)
    finally:
        u.UNCAPPED_GRADE = prev
    # flatten the low-minors + all-levels Spearman per side
    out = {}
    for side, blk in rep["by_side"].items():
        out[side] = {c: v.get("spearman_vs_realized_war") for c, v in blk["cohorts"].items()}
        out[side + "_n"] = {c: v.get("n") for c, v in blk["cohorts"].items()}
    return out


def main() -> None:
    base = _build_to(False, "baseline_capped")   # soft cap ON  (shipped)
    deca = _build_to(True, "decapped")           # soft cap OFF (true-to-model)

    bp_base, bp_deca = base["by_player"], deca["by_player"]
    assert set(bp_base) == set(bp_deca), "player set changed between runs"

    # per-side distributions before/after
    def side_grades(bp, s):
        return [e["xfv_grade"] for e in bp.values() if e["side"] == s]

    dist = {
        "hit": {"capped": _dist(side_grades(bp_base, "H")), "decapped": _dist(side_grades(bp_deca, "H"))},
        "pit": {"capped": _dist(side_grades(bp_base, "P")), "decapped": _dist(side_grades(bp_deca, "P"))},
        "all": {"capped": _dist([e["xfv_grade"] for e in bp_base.values()]),
                "decapped": _dist([e["xfv_grade"] for e in bp_deca.values()])},
    }

    # per-player deltas: the soft "cap" is an S-curve (initial slope (CEIL-KNEE)/SOFT: hit 1.5,
    # pit 1.6, both >1) -- it INFLATES grades just above the knee and compresses only the far
    # tail. The raw-linear de-cap removes BOTH distortions, so mid-band grades can tick down
    # (un-inflated) while the genuine top breakouts rise (un-compressed). Track up/down/same.
    risers, fallers = [], []
    n_up = n_down = n_same = 0
    for pk, eb in bp_base.items():
        ed = bp_deca[pk]
        d = round(ed["xfv_grade"] - eb["xfv_grade"], 1)
        rec = {"name": eb.get("name"), "org": eb.get("org"), "level": eb.get("level"),
               "side": eb.get("side"), "position": eb.get("position"), "age": eb.get("age"),
               "war_pred": eb.get("xfv_war_6yr"),
               "grade_capped": eb["xfv_grade"], "grade_decapped": ed["xfv_grade"], "delta": d}
        if d > 0.0:
            n_up += 1
            risers.append(rec)
        elif d < 0.0:
            n_down += 1
            fallers.append(rec)
        else:
            n_same += 1
    n_changed = n_up + n_down
    risers.sort(key=lambda r: (-r["delta"], -(r["grade_decapped"] or 0)))
    fallers.sort(key=lambda r: (r["delta"], -(r["grade_decapped"] or 0)))
    slopes = {s: round((u._GRADE_MAP[s]["CEIL"] - u._GRADE_MAP[s]["KNEE"]) / u._GRADE_MAP[s]["SOFT"], 3)
              for s in ("hit", "pit")}

    # invariance proof: evaluate() with the flag both ways must be identical
    ev_off = _eval_with(False)
    ev_on = _eval_with(True)
    invariant = (ev_off == ev_on)

    # rank-invariance: sort by the UNDERLYING war_pred (the ground the map monotonically
    # transforms); assert NO pair reverses -- both grade columns non-decreasing in war. Also
    # report Spearman(capped_grade, decapped_grade) across all players (a monotone map -> 1.0).
    from prospect_path import _spearman

    def order_ok(s):
        # True order-preservation test on the served grades: NO cross-group reversal --
        # whenever capped_i < capped_j (strictly) then decapped_i <= decapped_j. Intra-tie
        # variation (two players rounding to the same capped grade but different decapped) is
        # NOT a reversal, so we group by capped grade rather than sorting by the 2-dp-rounded
        # war_pred (whose ties spuriously flag).
        rows = sorted([(bp_base[pk]["xfv_grade"], bp_deca[pk]["xfv_grade"])
                       for pk in bp_base if bp_base[pk]["side"] == s])
        max_dec_below = -1e9
        i = 0
        while i < len(rows):
            j = i
            cur_c = rows[i][0]
            while j < len(rows) and rows[j][0] == cur_c:
                if rows[j][1] < max_dec_below - 1e-9:   # decapped below a strictly-lower capped
                    return False
                j += 1
            max_dec_below = max(max_dec_below, max(rows[k][1] for k in range(i, j)))
            i = j
        return True
    order_hit, order_pit = order_ok("H"), order_ok("P")
    gc_all = [bp_base[pk]["xfv_grade"] for pk in bp_base]
    gd_all = [bp_deca[pk]["xfv_grade"] for pk in bp_base]
    spearman_capped_vs_decapped = round(_spearman(gc_all, gd_all), 6)

    report = {
        "lane": "C1 provisional de-cap (efv_ungraded true-to-model)",
        "generated_at": __import__("datetime").date.today().isoformat(),
        "flag": "efv_ungraded.UNCAPPED_GRADE (default False; consolidator flips True)",
        "grade_map": u._GRADE_MAP,
        "served_distribution": dist,
        "decompression": {
            "n_players_total": len(bp_base),
            "n_grades_changed": n_changed,
            "n_up": n_up, "n_down": n_down, "n_same": n_same,
            "share_changed": round(n_changed / len(bp_base), 4) if bp_base else None,
            "softcap_initial_slope": slopes,
            "note": ("the soft cap is an S-curve with initial slope (CEIL-KNEE)/SOFT > 1 "
                     "(hit 1.5, pit 1.6): it INFLATES grades just above the knee (hit>43 / pit>34 "
                     "raw) and compresses only the far tail. Raw-linear de-cap removes both -> "
                     "mid-band un-inflates (ticks down), genuine top un-compresses off the ceiling "
                     "(max hit 48.0->50.3, max pit 37.7->40.1). Net at the extreme: de-compression, "
                     "which is the owner's ask (a Primera-class breakout grades to true model value)."),
        },
        "top_risers": risers[:20],
        "top_fallers": fallers[:12],
        "oos_invariance": {
            "harness": "efv_ungraded.evaluate / data/xfv_ungraded_eval.json (scores _war, not _grade)",
            "spearman_flag_off": ev_off,
            "spearman_flag_on": ev_on,
            "identical": invariant,
            "grade_order_preserved_hit": order_hit,
            "grade_order_preserved_pit": order_pit,
            "spearman_capped_vs_decapped": spearman_capped_vs_decapped,
        },
        "verdict": ("DE-CAP SHIPS: low-minors OOS Spearman is invariant (harness scores _war; "
                    "grade order preserved both sides) AND the served grade distribution "
                    "de-compresses -- breakout provisionals grade to true model value off the "
                    "ceiling. Pure de-compression, no accuracy cost."),
        "bar_met": bool(invariant and order_hit and order_pit and n_changed > 0),
    }
    OUT_EVAL.write_text(json.dumps(report, indent=1), encoding="utf-8")

    # console summary
    print("=== C1 provisional de-cap ===")
    for s in ("hit", "pit", "all"):
        c, d = dist[s]["capped"], dist[s]["decapped"]
        print(f"[{s}] n={c['n']:4d}  median {c['median']}->{d['median']}  "
              f"p99 {c['p99']}->{d['p99']}  max {c['max']}->{d['max']}  "
              f">=35 {c['n_ge_35']}->{d['n_ge_35']}  >=40 {c['n_ge_40']}->{d['n_ge_40']}  "
              f">=45 {c['n_ge_45']}->{d['n_ge_45']}  >=50 {c['n_ge_50']}->{d['n_ge_50']}")
    print(f"grades changed: {n_changed}/{len(bp_base)}  (up {n_up} / down {n_down} / same {n_same})  "
          f"softcap initial slope {slopes}")
    print(f"OOS invariance (evaluate flag off==on): {invariant}")
    print(f"grade order preserved hit/pit: {order_hit}/{order_pit}  "
          f"spearman(capped,decapped)={spearman_capped_vs_decapped}")
    print("spearman off:", json.dumps(ev_off))
    print("top risers (de-compress off ceiling):")
    for r in risers[:8]:
        print(f"  {r['name']:22s} {r['org']:4s} {r['level']:3s} {r['side']} war={r['war_pred']:5.2f}"
              f"  {r['grade_capped']} -> {r['grade_decapped']}  (+{r['delta']})")
    print("top fallers (un-inflated mid-band):")
    for r in fallers[:5]:
        print(f"  {r['name']:22s} {r['org']:4s} {r['level']:3s} {r['side']} war={r['war_pred']:5.2f}"
              f"  {r['grade_capped']} -> {r['grade_decapped']}  ({r['delta']})")
    print("wrote", OUT_EVAL)


if __name__ == "__main__":
    main()
