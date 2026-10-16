# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""eFV Pass 6 -- consolidate the per-side scores + tool eFVs into one artifact the
site can consume (data/xfv.json): per player the headline grade (re-anchored to the
20-80 scale), the realized 6yr-WAR projection, the 5-bucket distribution, surplus $,
the uncertainty band, the consensus FV for side-by-side comparison, and tool eFVs.

Run: python efv_export.py   (after efv_score for both sides + xfv_tools)
"""
from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import value_framework as vf

from efv_score import scored_path, scored_live_path

log = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "xfv.json"
# eFV valuation curve (glossary Methodology surface): per-FV-tier worth of a
# grade under the production valuation set -- the published FanGraphs 2026
# anchor vs the value_framework model vs the live board's medians. Written by
# _valuation_curve(), fetched by assets/glossary.js (_methValuationCurveHTML),
# pinned by test_valuation_curve_surface.py. Diagnostic only.
VALUATION_CURVE_PATH = DATA_DIR / "xfv_valuation_curve.json"


_ANCHOR_CONST: dict | None = None


def _anchor_constant_map() -> dict:
    """player_key -> anchor_constant_only, read from the LIVE matrices.

    `run_live` stamps this onto its own rows, but it is not the only path that
    reaches the served board (see `_delta_fields`), and the other one has no anchor
    on its rows at all. The matrices carry the flag for all 4,657 live players,
    including the ones run_live skipped, so this is where the missing half comes
    from. Best effort: a missing map degrades to "not a placeholder", which is the
    pre-C-6 behaviour rather than a crash."""
    global _ANCHOR_CONST
    if _ANCHOR_CONST is None:
        m: dict = {}
        for fn in ("xfv_live_hitter_matrix.json", "xfv_live_pitcher_matrix.json"):
            p = DATA_DIR / fn
            if not p.exists():
                continue
            try:
                for r in json.loads(p.read_text(encoding="utf-8")):
                    m[r.get("player_key")] = bool(r.get("anchor_constant_only"))
            except (OSError, json.JSONDecodeError, TypeError):
                log.warning("anchor map unreadable from %s; placeholder "
                            "suppression degrades to off for rows it would cover", fn)
        _ANCHOR_CONST = m
    return _ANCHOR_CONST


def _delta_fields(s, kind) -> dict:
    """The consensus delta and its two reason markers, for ANY path into xfv.json.

    THE FUNNEL FIX (C-6b, 2026-08-14), and it closes a hole in C-6 as shipped.
    C-6 applied `consensus_delta` in `run_live` only, on the stated scope that the
    resolved path feeds evaluation frames. That was right about the resolved path
    and wrong about the board: `run_live` SKIPS 168 active players for having no pro
    track record, `run_backgrade` scores them instead, and `efv_export.run` writes
    them into xfv.json as `kind: "active"`. Measured on the first C-7 rebuild, all
    168 published a delta, and **34 of them sat on the FV20 abstention knot and 19
    carried the fabricated consensus 35.0**. So 53 rows on the served board were
    still publishing exactly the manufactured comparison C-6 exists to suppress,
    with `consensus_is_placeholder: false` beside them, which is worse than absent
    because the page guard reads the false and renders the chip.

    This is the "a new seam must be applied at EVERY site" lesson from 2026-08-13b
    repeating inside the very next lane. Fixed at the export because that is the one
    funnel all scoring paths pass through to reach the board.

    Scope: `kind == "active"`, the served board. Resolved and backgraded-graduate
    rows keep their unconditional delta, as C-6's gate scoped, and that remaining
    inconsistency is recorded rather than silently widened.

    Calls the SHIPPED predicate, never a copy of it."""
    if kind != "active":
        return {"xfv_minus_consensus": s.get("xfv_minus_consensus")}
    if "consensus_is_placeholder" in s:          # run_live already decided this row
        return {"xfv_minus_consensus": s.get("xfv_minus_consensus"),
                "consensus_is_placeholder": bool(s.get("consensus_is_placeholder")),
                "xfv_grade_is_floor": bool(s.get("xfv_grade_is_floor"))}
    from efv_score import consensus_delta
    d, ph, fl = consensus_delta(
        s.get("xfv_grade"), s.get("consensus_fv"),
        anchor_constant_only=_anchor_constant_map().get(s.get("player_key"), False),
        # These rows never route: run_backgrade has no provisional path, so a grade
        # on the knot here is always the outcome map abstaining.
        grade_from_outcome_map=True)
    return {"xfv_minus_consensus": d,
            "consensus_is_placeholder": ph, "xfv_grade_is_floor": fl}


def _entry(s, side, kind):
    e = {
        "side": "P" if side == "pit" else "H",
        "kind": kind,                    # "active" | "resolved" | backgrade kinds ("debuted"/"bust")
        # COMMENT CORRECTED 2026-07-14 (audit; the flip shipped 2026-07-06):
        # xfv_grade_quantile IS the displayed headline site-wide (prospx,
        # build_site, proj_export, fa_fit all read it first) and surplus_mm is
        # priced on it -- see meta.grade_scale. xfv_grade / xfv_grade_realized
        # is the honest pure-model reference (realized_implied_fv(E[6yr WAR]),
        # deflated).
        #
        # THAT LINE USED TO SAY "which still drives p_bucket / p_bust (validated
        # odds)". IT IS FALSE and was corrected 2026-08-07b (audit lane C2, two
        # verifiers confirming at source). The odds are keyed on `_odds_grade`,
        # which efv_score sets from vf.realized_implied_fv; this field is set from
        # the OUTCOME-implied grade. They are different maps.
        #
        # SINCE 2026-09-04 BOTH ARE HERE: `xfv_grade_odds` below carries
        # `_odds_grade` itself (audit F09 step 1, owner decision S-3 of
        # 2026-08-13), so p_bucket, p_bust, surplus_mm and the band are now
        # reproducible from this file. Read the odds at THAT field, never at
        # xfv_grade or xfv_grade_quantile.
        #
        # HISTORY, measured 2026-08-07b, kept because it sizes the gap the new
        # field closes: agreement between the two maps, broken out by display
        # grade, was 76.8 percent below FV40, 1.6 percent in (40,45) and 0.0
        # percent above FV45. They agree where the board is dense and dull and
        # disagree totally at the top, which is where an odds claim matters. A
        # verifier tested whether the ~50 percent pooled agreement was an artifact
        # of an unidentifiable inversion and it is not: the plateau width at 3dp
        # is median 0.050 FV, p95 0.091, max 0.170. That measurement is why
        # xfv_grade_odds is emitted at 3dp.
        # The artifact shape (xfv_grade == realized alias) is test-pinned.
        "xfv_grade": s.get("xfv_grade"),                 # outcome-implied (pure model) reference
        "xfv_grade_realized": s.get("xfv_grade"),        # alias (identical; kept for back-compat reads)
        "xfv_grade_quantile": s.get("xfv_grade_display"),# RETIRED as the display 2026-07-25; prices surplus only
        "consensus_fv": s.get("consensus_fv"),
        # COMMENT RE-CORRECTED 2026-08-04. The 2026-07-23 version of this note
        # said the realized delta "does NOT track the displayed headline - the
        # headline's delta is xfv_minus_consensus_quantile". That was true when
        # the quantile map WAS the headline. It was retired as the served grade
        # on 2026-07-25 (BOARD_GRADE_FIELD = xfv_grade), so the two lines below
        # now mean the OPPOSITE of what the old note claimed, and anyone reading
        # it got the wrong field. Same drift class as the FanGraphs/bWAR comments
        # fixed in 5325440.
        #   xfv_minus_consensus          = xfv_grade - consensus = THE SERVED delta.
        #   xfv_minus_consensus_quantile = the RETIRED quantile display's delta,
        #                                  kept only for back-compat reads.
        # The gap is large: on the 2026-08-03 live board the served basis
        # disagrees with consensus by a mean 12.5 FV, the retired quantile basis
        # by 0.56, because a quantile remap onto the consensus distribution
        # reproduces consensus by construction.
        # C-6 2026-08-14: this is now NULL where no comparison exists, and the two
        # markers below carry the reason. They are not decoration: prospx reads them
        # to decide whether to render a delta chip at all, and without them the page
        # falls back to subtracting the two displayed numbers and re-manufactures
        # exactly the delta the scorer withheld.
        # docs/efv-2026-08-13/CONSENSUS_DELTA_HONESTY_GATE.md
        **_delta_fields(s, kind),
        "xfv_minus_consensus_quantile": s.get("xfv_minus_consensus_display"),  # retired quantile - consensus
        "xfv_war_6yr": s.get("xfv_war_6yr"),
        # THE GUARDED BLEND. efv_score writes rank_war on every scored row,
        # (1-lam)*consensus_OLS + lam*model, and this file published the grade,
        # the delta and the projected WAR but never the blend, so no reader could
        # check the board against it. It is NOT xfv_war_6yr, which is the model
        # leg alone and is what the eval scores; meta.serve_vs_eval_census
        # measures how far apart they run.
        "p_bucket": s.get("p_bucket"),
        "surplus_mm": s.get("surplus_mm"),
        "band_p10_mm": s.get("band_p10_mm"),
        "band_p90_mm": s.get("band_p90_mm"),
        "p_bust": s.get("p_bust"),
    }
    if s.get("dist") is not None:                        # live: full surplus fan + comparison
        e["dist"] = s["dist"]
    if s.get("consensus_surplus_mm") is not None:
        e["consensus_surplus_mm"] = s["consensus_surplus_mm"]
    if s.get("injury_factor") is not None:               # live injury penalty (<1.0 = hurt)
        e["injury_factor"] = s["injury_factor"]
    # xfv_grade_healthy is on the SERVED grade's basis (audit F12, fixed
    # 2026-09-04 in efv_score.run_live): the flagship map on a normal row, the
    # provisional map on a routed one, null where the routed basis cannot express
    # the counterfactual. Before that fix it was always the flagship map, so on
    # 192 routed cards it rendered BELOW the grade it sits beside.
    if s.get("xfv_grade_healthy") is not None:
        e["xfv_grade_healthy"] = s["xfv_grade_healthy"]
    if s.get("statcast_factor") is not None:             # live Statcast+ tilt (!=1.0)
        e["statcast_factor"] = s["statcast_factor"]
    if s.get("krp_plus") is not None:                    # KRP+ (K-backed Run Prevention), pitchers
        e["krp_plus"] = s["krp_plus"]
    if s.get("factors"):                                 # per-prospect eFV explainer
        e["factors"] = s["factors"]
    if s.get("factors_more"):                            # groups the top-4 cut dropped
        e["factors_more"] = s["factors_more"]            # ({n, mag}); see efv_score._factors
    # THE ROOKIE-WINDOW PAIR, and they are named here for the reason the block
    # below this one exists: a field efv_score writes and this whitelist does not
    # name never reaches data/xfv.json, which is the file storage reads.
    #   xfv_grade_at_debut  the grade the player carried INTO the majors.
    #                       storage pins the WAG baseline to THIS, never to the
    #                       served grade, because wag_calibration regresses on
    #                       that block and its regressand already sees the
    #                       future. Dropping this field silently un-pins the
    #                       leak rather than failing.
    #   xfv_rookie_window   set only when the window actually moved the scored
    #                       point off the debut anchor, so a surface can say
    #                       which graduates are still being re-graded.
    if s.get("xfv_grade_at_debut") is not None:
        e["xfv_grade_at_debut"] = s["xfv_grade_at_debut"]
    if s.get("xfv_rookie_window"):
        e["xfv_rookie_window"] = s["xfv_rookie_window"]
    # THE ODDS KEY, whitelisted 2026-09-04 (audit F09 step 1; owner decision S-3 of
    # 2026-08-13). vf.realized_implied_fv(xfv_war), the grade p_bucket, p_bust,
    # surplus_mm, dist and the band were actually read at. Emitted only where the
    # scorer wrote it, so a pre-2026-09-04 scored file still serializes; adding a
    # field moves no existing number.
    if s.get("xfv_grade_odds") is not None:
        e["xfv_grade_odds"] = s["xfv_grade_odds"]
    # ── THE WHITELIST GAP, closed 2026-08-07 (Lane F2) ─────────────────────────
    # This function is a field WHITELIST, so anything efv_score writes and this does not
    # name reaches data/xfv_scored_live_*.json and stops there. Both fields below were
    # emitted on 2026-08-07 and neither reached data/xfv.json, which is the file the
    # board actually reads, so the disclosure had nothing to read and the ordering had
    # no key to break ties on.
    #   grade_basis      WHICH WAR-to-FV map produced xfv_grade on this row:
    #                    "outcome_pooled" (the flagship pooled outcome curve) or
    #                    "provisional_capped" (efv_ungraded._GRADE_MAP, served under the
    #                    floor routing). The two disagree by -7.0 FV at WAR 0.0 and +11
    #                    to +12 through the 0.5-1.5 band, so a surface showing both owes
    #                    the reader a label, and prospx efvScaleNote reads this field.
    #   board_sort_key   ORDER-ONLY, never displayed: the model's unrounded PRE-clamp
    #                    predicted WAR. outcome_implied_fv maps every non-positive
    #                    prediction to one knot, so the floor is a single enormous tie
    #                    block; this lets storage._active_key and prospx fvCmpDesc break
    #                    it by the model instead of by name. Both readers must see the
    #                    SAME key or the baked overall_rank and the rendered order
    #                    diverge, which is the three-orderings bug BOARD_GRADE_FIELD
    #                    exists to prevent.
    # Emitted only where present, so backgraded/resolved rows (which carry neither) are
    # byte-identical and the artifact does not grow a wall of nulls.
    if s.get("grade_basis") is not None:
        e["grade_basis"] = s["grade_basis"]
    if s.get("board_sort_key") is not None:
        e["board_sort_key"] = s["board_sort_key"]
    #   rank_war         THE GUARDED BLEND, (1-lam)*consensus_OLS + lam*model.
    #                    efv_score writes it on every scored row at all three emit
    #                    sites and this whitelist never named it, so the file
    #                    published the grade, the delta and the projected WAR but
    #                    not the quantity the blend actually produced. It is NOT
    #                    xfv_war_6yr, which is the model leg alone and is what the
    #                    eval scores; meta.serve_vs_eval_census measures how far
    #                    apart they run. Conditional for the same reason as the two
    #                    above: a row without it must stay byte-identical.
    if s.get("rank_war") is not None:
        e["rank_war"] = s["rank_war"]
    #   efv_v2          DS-02: on a V2-graded row, the order index and its parts
    #                    (u_c, e_skill, e_time, order_idx, the (side, list year) group).
    #                    board_sort_key carries the same order index, so the sort and
    #                    the grade on this row come from one number.
    if s.get("efv_v2") is not None:
        e["efv_v2"] = s["efv_v2"]
    if s.get("xline_note"):                              # S-XLINE measurement note (annotation only,
        e["xline_note"] = s["xline_note"]                # live covered players; never a ranked factor)
    if s.get("xfv_provisional"):                          # prior-anchored (no pro track record)
        e["xfv_provisional"] = True
    if s.get("realized_war") is not None:                # backgraded graduate's career eWAR (displayed series)
        e["realized_war"] = s["realized_war"]
    return e


def _untied_inversions(pairs):
    """(untied_pairs, inverted, rho) for [(x, y), ...].

    `inverted` counts pairs whose x-order and y-order disagree, over pairs untied
    on BOTH coordinates, so a block of equal grades is scored as neither
    agreement nor disagreement. Exact and O(n log n) via a Fenwick tree over
    ranked y: a 2,400-row side is 2.9 million pairs and the quadratic form has no
    business in a nightly build. Validated against a brute-force reference on 400
    random tie-heavy cases plus the degenerate ones.

    `rho` is Spearman on the same rows (average ranks), reported beside the share
    because they answer different questions and can disagree loudly: a map with
    zero inversions and a low rho is not disordered, it is flat.
    """
    n = len(pairs)
    if n < 2:
        return 0, 0, None

    def _avg_ranks(vals):
        order = sorted(range(n), key=lambda i: vals[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    xs = [q[0] for q in pairs]
    ys = [q[1] for q in pairs]
    rx, ry = _avg_ranks(xs), _avg_ranks(ys)
    mx = sum(rx) / n
    my = sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    rho = round(num / den, 4) if den else None

    total = n * (n - 1) // 2

    def _tied(vals):
        c = {}
        for v in vals:
            c[v] = c.get(v, 0) + 1
        return sum(k * (k - 1) // 2 for k in c.values())

    untied = total - _tied(xs) - _tied(ys) + _tied(list(zip(xs, ys)))

    ys_sorted = sorted(set(ys))
    yrank = {v: i + 1 for i, v in enumerate(ys_sorted)}
    m = len(ys_sorted)
    tree = [0] * (m + 1)

    def _add(i):
        while i <= m:
            tree[i] += 1
            i += i & -i

    def _sum(i):
        t = 0
        while i > 0:
            t += tree[i]
            i -= i & -i
        return t

    # ascending x; within an x-tie block, count BEFORE inserting, so pairs tied
    # on x are never counted as discordant
    order = sorted(range(n), key=lambda i: (xs[i], ys[i]))
    disc = 0
    seen = 0
    i = 0
    while i < n:
        j = i
        while j + 1 < n and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            disc += seen - _sum(yrank[ys[order[k]]])
        for k in range(i, j + 1):
            _add(yrank[ys[order[k]]])
            seen += 1
        i = j + 1
    return untied, disc, rho


def _map_leg(rows):
    """One grade map against the model's own predicted WAR, both failure modes.

    Inversions catch a map that REORDERS the model. They say nothing about one
    that FLATTENS it, so the tie share, the distinct-value count and the modal
    grade ride alongside: an inversion count on a collapsed column reads as a
    clean bill of health.

    THE FIELD NAME IS LOAD-BEARING. `xfv_grade` is the board number
    (meta.grade_scale: "the displayed grade, the sort key and the basis of
    overall_rank"). `xfv_grade_quantile` is the RETIRED quantile map, kept only
    to price surplus, and measuring that one instead reports a completely
    different picture: near-total collapse, 3 distinct values across 1,387
    provisional pitchers, zero inversions.
    """
    n = len(rows)
    grades = [r["xfv_grade"] for r in rows]
    u, d, rho = _untied_inversions([(r["xfv_war_6yr"], g) for r, g in zip(rows, grades)])
    total = n * (n - 1) // 2
    counts = {}
    for g in grades:
        counts[g] = counts.get(g, 0) + 1
    modal, modal_n = None, 0
    for g, c in counts.items():
        if c > modal_n:
            modal, modal_n = g, c
    return {
        "grade_field": "xfv_grade",
        "n": n,
        "distinct_displayed_grades": len(counts),
        "modal_grade": modal,
        "modal_share": round(modal_n / n, 4) if n else None,
        "tied_pair_share": round(1.0 - (u / total), 4) if total else None,
        "rho_vs_predicted_war": rho,
        "untied_pairs": u,
        "inverted": d,
        "inverted_share": round(d / u, 4) if u else None,
    }


def _serve_vs_eval_census(by_player: dict) -> dict:
    """How far the SERVED grade and the guarded blend sit from the model leg.

    Measured, published, and not filed as a defect. The map legs split on
    `grade_basis` because the flagship map and the provisional cap are meant to
    behave differently, and pooling them hides it.
    """
    out = {
        "what_this_is": (
            "xfv_grade is the SERVED board number (storage.BOARD_GRADE_FIELD): the "
            "displayed grade, the sort key and the basis of overall_rank. xfv_war_6yr "
            "is the model leg the eval scores. rank_war is the guarded blend. This "
            "counts how far apart those orderings run, per side, on pairs untied on "
            "both coordinates, and splits the grade map by routing basis. It reads "
            "xfv_grade and NOT xfv_grade_quantile, which is the retired map kept to "
            "price surplus and which reports a completely different picture."),
        "what_it_measured_when_written": (
            "Flagship map exactly monotone: 0 inversions over 879,105 untied pairs "
            "across both sides. Provisional cap inverts against the model's own "
            "predicted WAR on 25.4% of hitter and 49.2% of pitcher untied pairs, and "
            "is served to 51% and 58% of the live board. Half is what independence "
            "looks like. A player with no professional record is graded off a prior by "
            "design, so this is the design, not a defect."),
        "read_a_flat_column_correctly": (
            "Inversions catch a map that REORDERS the model and say nothing about one "
            "that FLATTENS it, so read distinct_displayed_grades and modal_share "
            "beside inverted_share before calling a low count a clean result."),
        "why_it_is_published": (
            "It bounds what a head-to-head on this artifact covers. Where the served "
            "grade carries little information about the model's own prediction, a rank "
            "claim over the whole board is really a claim about the rows where it "
            "does."),
        "sides": {},
    }
    v2 = _v2_order_census(by_player)
    if v2:
        out["v2_board_order"] = v2
    for side in ("H", "P"):
        rows = [e for e in by_player.values()
                if e.get("side") == side and e.get("kind") == "active"
                and e.get("xfv_war_6yr") is not None]
        if len(rows) < 2:
            continue
        blk = {"n_active": len(rows), "map": {}}
        blended = [e for e in rows if e.get("rank_war") is not None]
        if len(blended) >= 2:
            u, d, rho = _untied_inversions(
                [(e["rank_war"], e["xfv_war_6yr"]) for e in blended])
            blk["blend_vs_model_leg"] = {
                "x": "rank_war", "y": "xfv_war_6yr", "n": len(blended), "rho": rho,
                "untied_pairs": u, "inverted": d,
                "inverted_share": round(d / u, 4) if u else None,
            }
        graded = [e for e in rows if e.get("xfv_grade") is not None]
        if len(graded) >= 2:
            leg = _map_leg(graded)
            leg["share_of_active"] = round(len(graded) / len(rows), 4)
            blk["map"]["ALL"] = leg
        for basis in sorted({str(e.get("grade_basis")) for e in graded}):
            sub = [e for e in graded if str(e.get("grade_basis")) == basis]
            if len(sub) < 2:
                continue
            leg = _map_leg(sub)
            leg["share_of_active"] = round(len(sub) / len(rows), 4)
            blk["map"][basis] = leg
        out["sides"][side] = blk
    return out


def _v2_order_census(by_player: dict) -> dict:
    """DS-02, measured on the artifact: inside each side, the order the board sorts V2
    rows in (xfv_grade descending, then board_sort_key descending, the storage and
    prospx rule) against the order of efv_v2.order_idx. One order index means zero
    rows out of place. {} when no row is V2-graded."""
    out = {}
    for side in ("H", "P"):
        rows = [(k, e) for k, e in by_player.items()
                if e.get("side") == side and e.get("kind") == "active"
                and e.get("efv_v2") is not None]
        if not rows:
            continue
        board = [k for k, _e in sorted(rows, key=lambda kv: (-float(kv[1]["xfv_grade"]),
                                                              -float(kv[1]["board_sort_key"]),
                                                              kv[0]))]
        idx = [k for k, _e in sorted(rows, key=lambda kv: (-float(kv[1]["efv_v2"]["order_idx"]),
                                                            kv[0]))]
        out[side] = {"n": len(rows),
                     "rows_out_of_place": sum(1 for a, b in zip(board, idx) if a != b),
                     "board_order_equals_order_index": board == idx}
    return out


def _served_model_meta() -> dict:
    """What serves, and what the board may say about it. The claim is derived from
    data/efv_progress.json (efv_v2_serve.served_claim), never written here."""
    import efv_v2_serve as _v2s
    if not _v2s.enabled():
        return {"model_id": "efv_v1", "grade_basis": "outcome_pooled"}
    import efv5_refit as _r5
    # EFV_FIX_B_REFIT (dark): with the re-fit flipped, the board names the model it serves
    # and prints the claim re-derived from the re-fit's own development read
    refit = bool(_r5.EFV_V5_REFIT_ON)
    out = {"model_id": _r5.SERVED_MODEL_ID if refit else _v2s.SERVED_MODEL_ID,
           "grade_basis": _v2s.GRADE_BASIS,
           "registry": "data/model_registry.json#efv_v2",
           "claim": _r5.served_claim() if refit else _v2s.served_claim(),
           "receipt": _v2s.model_receipt(),
           "who": ("every active prospect with a real consensus grade; rows whose "
                   "consensus is the last-resort constant are served by the "
                   "production-only provisional model (grade_basis "
                   "provisional_capped)")}
    # EFV_FIX_A A3 (owner decision EW3-21): the served key set, the dark families, the live
    # read season and the head weights' standing, derived from the fit and the live read.
    disc = _v2s.served_disclosures()
    if disc is not None:
        out["disclosures"] = disc
    return out


_GRADE_SCALE_V2 = (
    "xfv_grade is THE board number: the displayed grade, the sort key and the basis of "
    "overall_rank (storage.BOARD_GRADE_FIELD). Since 2026-09-25 (DS-02) it is eFV V2 on "
    "every row with grade_basis efv_v2: the consensus FV value of the prospect's (side, "
    "list year) group at the rank of V2's order index (efv_v2.order_idx, also the "
    "board_sort_key), so consensus sets the level and the model only reorders. The same "
    "grade prices surplus_mm, the band and dist (xfv_grade_quantile equals it on these "
    "rows) and keys the odds: p_bucket and p_bust are the consensus outcome table read at "
    "this grade (xfv_grade_odds). xfv_war_6yr is the consensus-FV-to-six-season-WAR line "
    "at the grade, context only. Rows with grade_basis provisional_capped have no source "
    "grade and are served by the production-only provisional model. Graduates and busts "
    "(kind debuted / bust) keep eFV v1.")


def run(persist: bool = True) -> dict:
    from efv_model import blend_lambda   # local: avoids a module-level cycle
    by_player = {}
    counts = {"resolved": 0, "active": 0}
    # resolved (backtest cohort -- known outcomes; powers the Debuted views) FIRST, then
    # the live board OVERWRITES any overlap so a current prospect shows its live grade.
    for side in ("hit", "pit"):
        for s in json.loads(scored_path(side).read_text(encoding="utf-8")):
            by_player[s["player_key"]] = _entry(s, side, "resolved")
            counts["resolved"] += 1
    # Backgrade: every other graded prospect (graduates + lingering/no-track-record actives),
    # scored on the live grade scale. Overwrites the resolved-scale entry so the WHOLE site
    # reads on one scale; the live board (next) wins for current prospects.
    from efv_score import backgrade_path
    bp = backgrade_path()
    if bp.exists():
        for s in json.loads(bp.read_text(encoding="utf-8")).get("scored", []):
            by_player[s["player_key"]] = _entry(s, s.get("side") == "pit" and "pit" or "hit",
                                                s.get("kind", "backgrade"))
            counts["backgrade"] = counts.get("backgrade", 0) + 1
    for side in ("hit", "pit"):
        lp = scored_live_path(side)
        if not lp.exists():
            continue
        for s in json.loads(lp.read_text(encoding="utf-8")):
            by_player[s["player_key"]] = _entry(s, side, "active")
            counts["active"] += 1

    # tool eFVs: resolved first, then live overlays (live wins for board players).
    for fn in ("xfv_tools.json", "xfv_tools_live.json"):
        fp = DATA_DIR / fn
        if not fp.exists():
            continue
        for pk, tv in json.loads(fp.read_text(encoding="utf-8")).get("by_player", {}).items():
            if pk in by_player:
                by_player[pk]["tool_xfv"] = tv

    out = {
        "meta": {
            "generated_at": date.today().isoformat(),
            # Which dollar calibration priced surplus_mm on these rows. Four
            # served artifacts silently disagreed on 2026-07-31 because none of
            # them recorded it; test_calibration_vintage_agreement now pins it.
            "calibration": vf.calibration_stamp(),
            # TOOL PROVENANCE (plan item J2, 2026-08-06). A served tool_xfv is a
            # bare {tool: grade}, so a reader cannot tell a grade that BLENDS
            # MiLB production from one that passes the consensus grade straight
            # through. That distinction became material the same day: the tool
            # gate gained a real paired-bootstrap MDE, `hit` failed it, and FOUR
            # OF FIVE tools are now grade-only. Nothing on any surface said so.
            #
            # Published here rather than per player because it is a per-TOOL
            # fact, identical on every row, and duplicating it 3,007 times would
            # be wire weight for no information.
            "tool_provenance": _tool_provenance(),
            "n_players": len(by_player),
            # bughunt SCORE d (2026-07-23): count kind=="active" rows in the
            # MERGED artifact - the backgrade contributes prior-anchored
            # kind=="active" rows (264 at fix time, all xfv_provisional) on top
            # of the live-board count, so counts["active"] undercounted the
            # artifact's own active universe.
            "n_active": sum(1 for e in by_player.values() if e.get("kind") == "active"),
            # AUDIT FIX 2026-07-14: the LIVE blend lambda, stamped on every
            # regen - the governance eval artifacts (xfv_eval*.json) record
            # their own lambda at eval time and had silently desynced from
            # the live value twice; this stamp is the always-current truth
            # to compare them against.
            "live_lambda": {"hit": round(blend_lambda("hit"), 4),
                            "pit": round(blend_lambda("pit"), 4)},
            # RESTAMPED 2026-07-30. This string was stale on BOTH of its claims: it still
            # called xfv_grade_quantile the site-wide displayed grade (retired 2026-07-25,
            # when storage.BOARD_GRADE_FIELD moved to raw xfv_grade), and it described
            # xfv_grade through realized_implied_fv (retired 2026-07-30 by the pooled
            # outcome refit). A grade that changes meaning without its documentation
            # following is the exact drift this program spent the session correcting.
            "grade_scale": "xfv_grade is THE board number: the displayed grade, the sort key "
                           "and the basis of overall_rank (storage.BOARD_GRADE_FIELD). Since "
                           "2026-07-30 it is value_framework.outcome_implied_fv(E[6yr WAR]) -- "
                           "the inverse of the POOLED empirical outcome curve fitted on resolved "
                           "cohorts (data/fv_outcome_curves_pooled.json), so a grade states the "
                           "FV whose measured first-six-year bWAR matches this prediction. It is "
                           "a pure function of predicted WAR: unlike the retired map it takes no "
                           "age or position, so two rows with equal predictions grade equally. "
                           "Below about FV45 the curve is flat and the sub-floor knots are a "
                           "shape-preserving re-spread, so a sub-45 grade is NOT outcome-"
                           "calibrated and must not be read as one. xfv_grade_quantile is the "
                           "RETIRED per-side quantile map onto the consensus distribution; it is "
                           "no longer displayed but surplus_mm is still priced through it, which "
                           "is why the refit moved zero dollars. p_bucket / p_bust stay on the "
                           "retired realized_implied_fv map on purpose (they were ground-truthed "
                           "on it and a re-key has not been measured). Live board players carry "
                           "kind=active + a surplus dist; they require a pro track record (eFV "
                           "abstains on players with no MiLB production).",
            # DS-02: which eFV serves and the claim the board prints about it.
            "served_model": _served_model_meta(),
            "eval": {"hitter": "data/xfv_eval.json", "pitcher": "data/xfv_eval_pitcher.json",
                     "tools": "data/xfv_tools.json"},
            "status": "provisional",
            # A-CLAIM-7. The divergence between the object the eval SCORES, the
            # blend the model produces and the grade the board SERVES, recomputed
            # on this artifact instead of recorded once in a plan document where
            # it could not go stale loudly. See _serve_vs_eval_census, and read
            # its field-name note before quoting any number out of it.
            "serve_vs_eval_census": _serve_vs_eval_census(by_player),
        },
        "by_player": by_player,
    }
    if out["meta"]["served_model"].get("model_id") != "efv_v1":
        out["meta"]["grade_scale"] = _GRADE_SCALE_V2
        out["meta"]["eval"]["served"] = "data/efv_v2_dev_eval.json"
    if persist:
        OUT_PATH.write_text(json.dumps(out, indent=0), encoding="utf-8")
        log.info("wrote %s (%d players)", OUT_PATH, len(by_player))
    return out


# Tier axis for the valuation curve: the published FV tiers and the numeric
# grade each one prices at (the "+" half-grades sit at the midpoint). Matches
# valuation_sets._TIER_AXIS; duplicated as a literal so the artifact shape is
# stable even if the sets module reorders.
_VC_TIER_FV = {"35+": 37.5, "40": 40.0, "40+": 42.5, "45": 45.0, "45+": 47.5,
               "50": 50.0, "55": 55.0, "60": 60.0, "65": 65.0, "70": 70.0}
_VC_SET = "clemens_2026"
_VC_MIN_LIVE_N = 5     # thin-tier honesty: below this, ship n but no medians


def _valuation_curve(by_player=None) -> dict:
    """Bake data/xfv_valuation_curve.json: what an eFV grade is worth, per FV
    tier and role, three ways --

      published: the FanGraphs 2026 anchor table the valuation set commits to
                 (valuation_sets.tier_table: surplus $M, 7yr-control WAR,
                 star odds under the published 2-seasons-of-4+-WAR definition);
      model:     the same three quantities as the value_framework engine prices
                 them under the production set (surplus_value_mm, expected_war
                 mean at 7 service years, star_odds -- SAME star definition as
                 published, so the two columns are directly comparable);
      live:      medians over the current active board (data/xfv.json,
                 kind == "active") snapped to the nearest tier midpoint of the
                 displayed grade. NOTE p_star_median is the eFV 5-bucket "star"
                 outcome probability, a DIFFERENT quantity from the published
                 2x4 star odds -- both are kept, under clearly separate keys.

    Diagnostic only: measures the served numbers, changes none of them.
    Standalone: python -c "import efv_export; efv_export._valuation_curve()".
    """
    from statistics import median
    import valuation_sets                      # leaf import (no engine cycle)
    import value_framework

    if by_player is None:
        by_player = json.loads(OUT_PATH.read_text(encoding="utf-8")).get("by_player", {})

    # --- live board medians, bucketed by nearest tier midpoint ---------------
    live = {role: {t: {"surplus": [], "war6": [], "pstar": []}
                   for t in _VC_TIER_FV} for role in ("hitter", "pitcher")}
    for e in by_player.values():
        if e.get("kind") != "active":
            continue
        q = e.get("xfv_grade_quantile")
        if q is None:
            continue
        role = "pitcher" if e.get("side") == "P" else "hitter"
        tier = min(_VC_TIER_FV, key=lambda t: (abs(float(q) - _VC_TIER_FV[t]),
                                               _VC_TIER_FV[t]))
        b = live[role][tier]
        b["surplus"].append(e.get("surplus_mm"))
        b["war6"].append(e.get("xfv_war_6yr"))
        b["pstar"].append((e.get("p_bucket") or {}).get("star"))

    def _live_block(role, tier):
        b = live[role][tier]
        n = len(b["surplus"])                  # players snapped to the tier
        out = {"n": n}
        if n >= _VC_MIN_LIVE_N:
            for key, vals, dp in (("surplus_mm_median", b["surplus"], 1),
                                  ("war6_median", b["war6"], 2),
                                  ("p_star_median", b["pstar"], 4)):
                got = [float(v) for v in vals if v is not None]
                if got:
                    out[key] = round(median(got), dp)
        return out

    # --- published anchor + engine model, per role/tier ----------------------
    tiers = {}
    with value_framework.valuation_set(_VC_SET):
        for role in ("hitter", "pitcher"):
            pub_table = valuation_sets.tier_table(_VC_SET, role)
            is_pit = role == "pitcher"
            rt = {}
            for tier, fv in _VC_TIER_FV.items():
                pub = pub_table.get(tier) or {}
                ew = value_framework.expected_war(fv, is_pit, service_years=7)
                sv = value_framework.surplus_value_mm(fv, is_pit)
                # bughunt F4 (2026-07-23): a like-for-like RAW column. The
                # monitor used to conflate bases (model = calibrated engine $,
                # live = the then-RAW served surplus_mm) and could not see the
                # drift it exists to measure (hitter FV45 read +51% when the
                # like-for-like gap was -23%). Served surplus_mm is CALIBRATED
                # now (efv_score seam, same 2026-07-23 ship), so live medians
                # compare like-for-like against model.surplus_mm; surplus_mm_raw
                # keeps the pre-calibration engine dollars visible so drift in
                # the calibration layer itself is also measurable.
                sv_raw = value_framework.expected_surplus_usd(fv, is_pit)
                so = value_framework.star_odds(fv, is_pit)
                rt[tier] = {
                    "fv": fv,
                    "published": {"surplus_mm": pub.get("surplus_musd"),
                                  "ctrl_war": pub.get("ctrl_war"),
                                  "star_odds": pub.get("star_odds")},
                    "model": {"surplus_mm": None if sv is None else round(sv, 1),
                              "surplus_mm_raw": None if sv_raw is None else round(sv_raw / 1e6, 1),
                              "expected_war": None if not ew else round(ew["mean"], 2),
                              "star_odds": None if so is None else round(so, 4)},
                    "live": _live_block(role, tier),
                }
            tiers[role] = rt

    star_def = (valuation_sets.engine_params(_VC_SET).get("star_definition")
                or {"min_seasons": 2, "war_threshold": 4.0})
    out = {
        "generated_at": date.today().isoformat(),
        "valuation_set": _VC_SET,
        # THE LABEL THE GLOSSARY PRINTS VERBATIM. "7yr control window" named this
        # 7-season valuation object with the same three words /projections/ uses
        # for a 4-season club control window, on a page a reader reaches from
        # either one. The renderer maps the legacy value for artifacts written
        # before this line changed.
        "war_window": "7-season valuation window (published ctrl_war basis)",
        "star_def": {"min_seasons": star_def.get("min_seasons", 2),
                     "war_threshold": star_def.get("war_threshold", 4.0)},
        "surplus_basis": ("model.surplus_mm and live.surplus_mm_median are both "
                          "CALIBRATED engine dollars (served surplus_mm prices "
                          "through apply_calibration since 2026-07-23); "
                          "model.surplus_mm_raw is the raw pre-calibration engine "
                          "figure. live is timing-aware (age+ETA), model is "
                          "timing-naive - the remaining basis gap is timing only."),
        "tiers": tiers,
    }
    VALUATION_CURVE_PATH.write_text(json.dumps(out, indent=0), encoding="utf-8")
    log.info("wrote %s", VALUATION_CURVE_PATH)
    return out


def _tool_provenance() -> dict:
    """{tool: {"basis": "blended"|"grade_only", ...}} from the tool artifact.

    Reads the gate's own verdicts rather than restating them, so this can never
    drift from what actually decided the served grade. An absent artifact yields
    an empty dict and the surface simply shows no chip, which is honest: we do
    not know the basis, so we do not claim one."""
    try:
        import json as _json
        d = _json.loads((DATA_DIR / "xfv_tools.json").read_text(encoding="utf-8"))
    except Exception:                                         # noqa: BLE001
        return {}
    tools = (d.get("meta") or {}).get("modeled_tools") or {}
    out = {}
    for name, t in tools.items():
        oos = t.get("oos_validation") or {}
        blended = bool(oos.get("validated"))
        out[name] = {
            "basis": "blended" if blended else "grade_only",
            "label": ("grade plus MiLB production" if blended
                      else "consensus grade only"),
            "why": ("the MiLB blend cleared the gate for this tool"
                    if blended else
                    "the MiLB blend did not beat the grade alone out of sample, "
                    "so the consensus grade is passed through unchanged"),
            "margin": oos.get("margin"),
            "delta_lo95": oos.get("delta_lo95"),
        }
    for name in (d.get("meta") or {}).get("passthrough_tools") or []:
        out.setdefault(str(name), {
            "basis": "grade_only",
            "label": "consensus grade only",
            "why": ((d.get("meta") or {}).get("passthrough_reason")
                    or "no realized MLB metric to validate a blend against"),
        })
    return out


@contextmanager
def _regen_stage(name: str, step=None):
    """PERF_9 (2026-10-03): time one regen_all stage. With `step` (run_monthly's
    rebuild_only hands its _step recorder down) the stage becomes a named row in the
    pipeline step table; without it the stage still logs its elapsed time. Timing
    only: every stage makes the same calls in the same order as before."""
    t0 = time.monotonic()
    ok = False
    try:
        if step is None:
            yield
        else:
            with step(name):
                yield
        ok = True
    finally:
        log.info("regen_all stage %s %s in %.1fs", name, "done" if ok else "raised",
                 time.monotonic() - t0)


def regen_all(persist: bool = True, include_eval: bool = False, step=None) -> dict:
    """Run the whole eFV pipeline in dependency order and consolidate data/xfv.json:
    training matrix -> live matrix -> resolved scores -> live scores -> tool eFVs ->
    export. The forward-chained backtest eval (efv_model, the governance artifact) is
    heavy and stable, so it is OPT-IN (include_eval). Requires data/timeseries.json
    (run after the site export). One call for what was five manual module runs.

    `step`, when given, is a callable stage_name -> context manager (run_monthly's
    step recorder); each stage below runs inside it so the nightly step table ranks
    the stages. Without it each stage only logs its own elapsed time."""
    import efv_dataset
    import efv_score
    import efv_tools
    with _regen_stage("dataset", step):
        for side in ("hit", "pit"):
            efv_dataset.run(persist, side)          # labeled training matrix + baseline
            efv_dataset.build_live(persist, side)   # current active-board feature matrix
    if include_eval:
        import efv_model
        with _regen_stage("eval", step):
            for side in ("hit", "pit"):
                efv_model.run(persist, side)         # forward-chained eval (registry artifact)
    with _regen_stage("score", step):
        for side in ("hit", "pit"):
            efv_score.run(persist, side)             # resolved cohort scores
            efv_score.run_live(persist, side)        # live board scores (gated on track record)
    with _regen_stage("backgrade", step):
        efv_score.run_backgrade(persist)              # backgrade the rest of the site (graduates etc.)
    with _regen_stage("history", step):
        efv_score.score_history(persist)              # eFV-over-time per snapshot (FV history chart)
    with _regen_stage("tools", step):
        efv_tools.run(persist)                        # resolved tool eFVs
        efv_tools.run_live(persist)                   # live tool eFVs
    # UNGRADED prospects -- production-only leading indicator for the source-ungraded roster
    # players (DSL/CPX breakouts etc.). Separate model + artifact (data/xfv_ungraded.json);
    # NOT folded into the flagship xfv.json or the farm-rank composite. Needs rosters_by_org.json
    # (written by the site export) + the labeled matrix (built above). Best-effort.
    with _regen_stage("ungraded", step):
        try:
            import efv_ungraded
            efv_ungraded.build(persist)
        except Exception:
            log.exception("efv_ungraded.build failed -- continuing without ungraded grades")
    # PROVISIONAL v2 (PV-06): for the same source-ungraded universe, the chance of a first
    # grade within the next list cycle (ANY / FanGraphs / Pipeline x 6 / 12 months) and the
    # expected first FV on each source's own scale, plus its forward-chained BACKCAST eval
    # (data/provisional_v2.json, data/provisional_v2_eval.json). Reads grades and the MiLB /
    # draft caches only, never WAR; feeds nothing above. Skipped when not persisting.
    if persist:
        with _regen_stage("provisional_v2", step):
            try:
                import provisional_v2
                provisional_v2.build(persist)
            except Exception:
                log.exception("provisional_v2.build failed -- continuing without provisional v2")
    # C1: refresh the shipped-distribution reliability curves + drift tripwire.
    # Diagnostic only (no served number depends on them); regen_all previously
    # omitted it, leaving data/xfv_reliability.json stale. Best-effort.
    with _regen_stage("reliability", step):
        try:
            import efv_reliability
            efv_reliability.build(persist)
        except Exception:
            log.exception("efv_reliability.build failed -- continuing without reliability regen")
    with _regen_stage("consolidate", step):
        out = run(persist)
    # Valuation curve (glossary Methodology surface): what a grade is worth per
    # tier -- published anchor vs engine model vs live-board medians. Best-effort
    # like the reliability block above, fed the freshly consolidated by_player
    # so its live medians can never lag the export they describe. Skipped when
    # not persisting (a dry run must not touch committed data/ artifacts).
    if persist:
        with _regen_stage("valuation_curve", step):
            try:
                _valuation_curve(out.get("by_player"))
            except Exception:
                log.exception("_valuation_curve failed -- continuing without valuation-curve regen")
        # S-XLINE-4 overlay signal bake (data/statcast_alevel_signals.json):
        # refresh the A/CPX whiff/velo z legs from the stored zone/statcast
        # payloads for the NEXT scoring pass (frozen coefficients re-emitted
        # verbatim, never refit). Best-effort like the blocks above; offline.
        with _regen_stage("statcast_alevel", step):
            try:
                import statcast_alevel_export
                statcast_alevel_export.run()
            except Exception:
                log.exception("statcast_alevel_export failed -- continuing with the prior signal bake")
    return out


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "--all" in sys.argv:
        rep = regen_all(include_eval="--eval" in sys.argv)
    else:
        rep = run()
    print("eFV consolidated export:", rep["meta"]["n_players"], "players",
          f"({rep['meta']['n_active']} active) ->", OUT_PATH)
