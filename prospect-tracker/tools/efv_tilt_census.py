"""A-CLAIM-7: what the board SERVES versus what the accuracy claim EVALUATES.

THE QUESTION. Every head-to-head cell in data/source_backtest.json scores an
object: the model's predicted six-year WAR, or a rank derived from it. The board
a reader looks at serves three other things: an ORDER (storage bakes
`overall_rank` off `board_sort_key`), a DISPLAYED HEADLINE
(`xfv_grade_quantile`), and a PURE-MODEL REFERENCE (`xfv_grade`). Nothing has
ever published how far those four objects are from each other, so "eFV ties the
consensus on ordering" has been quoted without anyone being able to check which
ordering.

WHY DISCORDANT PAIRS AND NOT CORRELATION. Spearman rho on these fields is
dominated by ties: the FV scale is coarse and the quantile map is coarser still,
so 32% of hitter pairs and 53% of pitcher pairs are tied in the displayed grade.
A low rho against a tie-heavy field looks like disagreement and is mostly
granularity. The honest statistic is the share of pairs that are UNTIED IN BOTH
fields and ordered oppositely, which is a real inversion and cannot be produced
by rounding. Both are published; the discordance is the one to read.

WHAT IT FOUND, 2026-09-06:

  * The flagship map is EXACTLY monotone. Within `grade_basis == outcome_pooled`,
    zero of roughly a million untied pairs are discordant on either side. The
    docstring in efv_score.py that claims this is telling the truth.
  * The provisional map is not, and it is not close. Within
    `grade_basis == provisional_capped` the served grade is discordant with the
    model's own predicted WAR on 25.4% of untied hitter pairs and 48.8% of
    pitcher pairs. Half is what independence looks like.
  * That basis is MOST OF THE LIVE BOARD: 1,091 hitters and 1,386 pitchers,
    2,477 of 4,546 rows.
  * Every one of those rows carries consensus FV exactly 35.0, the placeholder
    constant. They are precisely the constant-anchor population A-CLAIM-12
    counts, arriving from the other direction.
  * The ORDER is fine. `board_sort_key` is discordant with predicted WAR on only
    7.7% of hitter pairs and 6.3% of pitcher pairs, and rho is 0.988 and 0.986.

SO THE GAP IS IN THE GRADE, NOT THE RANKING. A reader who compares two
provisional players by their displayed eFV grades is reading a number that
ordered them differently from the way the board ordered them, and differently
again from the object the accuracy page scores. That may well be deliberate: a
player with no professional track record is graded off a prior rather than off a
ridge prediction nobody should trust yet. It has simply never been measured or
disclosed, and it bounds what the head-to-head result can be said to cover.

This census DESCRIBES. It changes no grade, no rank and no dollar. Offline,
reads data/xfv.json, writes data/xfv_tilt_census.json.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BOARD = DATA / "xfv.json"
OUT = DATA / "xfv_tilt_census.json"

#: The object every accuracy cell is computed on, and the one everything here is
#: compared against.
EVALUATED = "xfv_war_6yr"

#: The three served objects, in the order a reader meets them.
SERVED = (
    ("board_sort_key", "the ORDER: storage bakes overall_rank off this key"),
    ("xfv_grade_quantile", "the DISPLAYED headline grade"),
    ("xfv_grade", "the pure-model reference grade"),
)


def _np():
    import numpy as np
    return np


def discordance(a, b):
    """(concordant, discordant, tied) over pairs untied in BOTH fields.

    Exact, via an n x n comparison matrix. n is a couple of thousand per side, so
    this is a few million booleans and finishes in well under a second; an
    O(n log n) inversion count would be faster and much harder to check by eye,
    and being obviously correct matters more here than being fast.
    """
    np = _np()
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    da = np.sign(a[:, None] - a[None, :])
    db = np.sign(b[:, None] - b[None, :])
    iu = np.triu_indices(len(a), k=1)
    da, db = da[iu], db[iu]
    live = (da != 0) & (db != 0)
    conc = int(((da == db) & live).sum())
    disc = int(((da != db) & live).sum())
    tied = int((~live).sum())
    return conc, disc, tied


def spearman(a, b):
    np = _np()

    def rank(x):
        x = np.asarray(x, dtype=float)
        order = np.argsort(x, kind="mergesort")
        r = np.empty(len(x), dtype=float)
        sx = x[order]
        i = 0
        while i < len(x):
            j = i
            while j + 1 < len(x) and sx[j + 1] == sx[i]:
                j += 1
            r[order[i:j + 1]] = (i + j) / 2.0
            i = j + 1
        return r

    ra, rb = rank(a), rank(b)
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def _cell(rows, field):
    have = [r for r in rows
            if r.get(field) is not None and r.get(EVALUATED) is not None]
    if len(have) < 2:
        return {"n": len(have), "note": "too few rows to compare"}
    a = [r[field] for r in have]
    b = [r[EVALUATED] for r in have]
    conc, disc, tied = discordance(a, b)
    live = conc + disc
    total = len(have) * (len(have) - 1) // 2
    return {
        "n": len(have),
        "spearman_vs_evaluated": (round(spearman(a, b), 4)
                                  if spearman(a, b) is not None else None),
        "pairs_total": total,
        "pairs_untied_in_both": live,
        "pairs_tied": tied,
        "tied_share": round(tied / total, 4) if total else None,
        "discordant": disc,
        "discordant_share": round(disc / live, 4) if live else None,
    }


def census(board: dict | None = None) -> dict:
    doc = board if board is not None else json.loads(
        BOARD.read_text(encoding="utf-8"))
    bp = doc.get("by_player") or {}
    out_sides = {}
    for side, label in (("H", "hitters"), ("P", "pitchers")):
        # THE LIVE BOARD ONLY. board_sort_key is emitted for active rows and not
        # for backgraded or resolved ones, and the question is about what a
        # reader sees on the board today.
        rows = [v for v in bp.values()
                if v.get("side") == side
                and v.get("board_sort_key") is not None
                and v.get(EVALUATED) is not None]
        if not rows:
            out_sides[side] = {"n": 0, "note": "no live rows on this side"}
            continue
        bases = sorted({(r.get("grade_basis") or "(unlabelled)") for r in rows})
        served = {f: _cell(rows, f) for f, _why in SERVED}

        by_basis = {}
        for b in bases:
            sub = [r for r in rows
                   if (r.get("grade_basis") or "(unlabelled)") == b]
            cons = sorted({r.get("consensus_fv") for r in sub
                           if r.get("consensus_fv") is not None})
            by_basis[b] = {
                "n": len(sub),
                "share_of_side": round(len(sub) / len(rows), 4),
                "grade_vs_evaluated": _cell(sub, "xfv_grade"),
                "order_vs_evaluated": _cell(sub, "board_sort_key"),
                "distinct_consensus_fv": len(cons),
                # The A-CLAIM-12 join, stated where it is visible. When a basis
                # carries ONE consensus value it is the placeholder constant and
                # this basis IS the no-published-opinion population.
                "consensus_fv_single_value": (cons[0] if len(cons) == 1 else None),
            }

        # ROUTING. How much of the whole side's grade discordance comes from
        # mixing the two bases rather than from either map on its own.
        whole = served["xfv_grade"]
        within_disc = sum(v["grade_vs_evaluated"].get("discordant") or 0
                          for v in by_basis.values())
        within_live = sum(v["grade_vs_evaluated"].get("pairs_untied_in_both") or 0
                          for v in by_basis.values())
        cross_disc = (whole.get("discordant") or 0) - within_disc
        cross_live = (whole.get("pairs_untied_in_both") or 0) - within_live
        out_sides[side] = {
            "label": label,
            "n": len(rows),
            "grade_bases": {b: v["n"] for b, v in by_basis.items()},
            "served_vs_evaluated": served,
            "by_grade_basis": by_basis,
            "routing": {
                "cross_basis_pairs_untied": cross_live,
                "cross_basis_discordant": cross_disc,
                "cross_basis_discordant_share": (round(cross_disc / cross_live, 4)
                                                 if cross_live else None),
                "share_of_all_grade_discordance_that_is_cross_basis": (
                    round(cross_disc / whole["discordant"], 4)
                    if whole.get("discordant") else None),
                "what_this_measures": (
                    "a pair whose two rows were graded through DIFFERENT maps. "
                    "Each map can be perfectly monotone on its own rows and the "
                    "composite still not be, which is what routing reorder "
                    "means and why it is separated from the maps themselves."),
            },
        }
    return {
        "generated_at": datetime.now(timezone.utc)
                        .replace(microsecond=0).isoformat(),
        "produced_by": "tools/efv_tilt_census.py",
        "evaluated_object": EVALUATED,
        "served_objects": {f: why for f, why in SERVED},
        "is_additional_view": True,
        "changes_no_served_number": True,
        "sides": out_sides,
        "why_discordance_not_correlation": (
            "Spearman rho against these fields is dominated by ties: the FV "
            "scale is coarse and the quantile map coarser, so a third to a half "
            "of pairs are tied in the displayed grade. A low rho there is mostly "
            "granularity. The share of pairs untied in BOTH fields and ordered "
            "oppositely is a real inversion and cannot be produced by rounding. "
            "Both are published; read the discordance."),
        "reading": _reading(out_sides),
    }


def _reading(sides: dict) -> str:
    bits = []
    for side, s in sides.items():
        if not s.get("n"):
            continue
        who = s["label"]
        order = s["served_vs_evaluated"]["board_sort_key"]
        prov = s["by_grade_basis"].get("provisional_capped") or {}
        pooled = s["by_grade_basis"].get("outcome_pooled") or {}
        pd = (prov.get("grade_vs_evaluated") or {}).get("discordant_share")
        od = (pooled.get("grade_vs_evaluated") or {}).get("discordant_share")
        bits.append(
            f"{who}: the board's ORDER is close to the evaluated object "
            f"({100 * (order.get('discordant_share') or 0):.1f}% of untied pairs "
            f"inverted, rho {order.get('spearman_vs_evaluated')}). "
            + (f"The flagship grade map is exactly monotone on its own rows "
               f"({100 * od:.1f}% inverted over "
               f"{pooled.get('grade_vs_evaluated', {}).get('pairs_untied_in_both')} "
               f"untied pairs). " if od is not None else "")
            + (f"The provisional grade served to {prov.get('n')} rows "
               f"({100 * (prov.get('share_of_side') or 0):.0f}% of the side) is "
               f"inverted against it on {100 * pd:.1f}% of untied pairs."
               if pd is not None else ""))
    return (" ".join(bits) + " The gap is in the GRADE, not the ranking. A reader "
            "comparing two provisional players by their displayed eFV grades is "
            "reading a number that ordered them differently from the way the "
            "board ordered them, and differently again from the object the "
            "accuracy page scores. That may be deliberate, since a player with "
            "no professional track record is graded off a prior rather than off "
            "a ridge prediction nobody should trust yet; it had simply never "
            "been measured, and it bounds what the head-to-head covers.")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    c = census()
    if "--dry-run" not in argv:
        OUT.write_text(json.dumps(c, indent=1) + "\n", encoding="utf-8")
    for side, s in c["sides"].items():
        if not s.get("n"):
            continue
        print(f"=== {s['label']} (n={s['n']})  bases={s['grade_bases']}")
        for f, cell in s["served_vs_evaluated"].items():
            print(f"   {f:20s} rho={cell.get('spearman_vs_evaluated')}  "
                  f"discordant={cell.get('discordant_share')} of "
                  f"{cell.get('pairs_untied_in_both')} untied  "
                  f"tied={cell.get('tied_share')}")
        for b, v in s["by_grade_basis"].items():
            g = v["grade_vs_evaluated"]
            print(f"   basis {b:20s} n={v['n']:5d}  grade discordant="
                  f"{g.get('discordant_share')}  consensus_fv values="
                  f"{v['distinct_consensus_fv']}"
                  + (f" (all {v['consensus_fv_single_value']})"
                     if v["consensus_fv_single_value"] is not None else ""))
        r = s["routing"]
        print(f"   routing: {r['cross_basis_discordant_share']} of cross-basis "
              f"pairs inverted; {r['share_of_all_grade_discordance_that_is_cross_basis']} "
              "of all grade discordance is cross-basis")
        print()
    print(c["reading"])
    if "--dry-run" not in argv:
        print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
