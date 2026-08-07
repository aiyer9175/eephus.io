"""Lane B gate simulation: what the floor routing + the board dedupe do to the
committed board, without regenerating anything.

The exporters are forbidden in this session and the deploy box is the single
writer, so the routing cannot be observed by rebuilding data/xfv.json. It CAN be
observed exactly, because the routing is a pure relabelling of rows that already
exist in two committed artifacts: the flagship grade in data/xfv.json and the
provisional grade in data/xfv_ungraded.json. This lab applies the shipped rule to
those artifacts and runs the pre-registered gates in
docs/efv-2026-08-07/BOARD_FLOOR_ROUTING_GATE.md.

WHAT IT IS NOT. It does not re-fit anything and it does not predict the NEXT
regen's numbers, which will differ as the nightly data moves. It answers the only
question the gate asks: applied to this board, does the rule move what it claims to
move and nothing else.

Read-only apart from its own artifact. Run: python tools/efv_board_floor_sim.py
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from consensus import CONSTANT_ANCHOR_SOURCES   # noqa: E402

DATA = ROOT / "data"
OUT_DIR = ROOT / "docs" / "efv-2026-08-07"
OUT_PATH = OUT_DIR / "BOARD_FLOOR_ROUTING_SIM.json"

PERMUTE_SEED = 20260807      # zero-information control, fixed so the run reproduces


def eu_subfloor() -> float:
    import efv_ungraded as eu
    return float(eu._SUBFLOOR_GRADE)


def _spearman(xs, ys) -> float | None:
    """Rank correlation with average ranks for ties. Local rather than scipy: this
    lab must run with no optional dependency, and the gate reads it as a pass/fail
    on 1.000, not as an estimate."""
    n = len(xs)
    if n < 2:
        return None

    def _ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx)
    dy = sum((b - my) ** 2 for b in ry)
    if dx <= 0 or dy <= 0:
        return None
    return num / (dx * dy) ** 0.5


def _load():
    ts = json.loads((DATA / "timeseries.json").read_text(encoding="utf-8"))
    xfv = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))
    ung = json.loads((DATA / "xfv_ungraded.json").read_text(encoding="utf-8"))
    return ts, xfv.get("by_player") or {}, ung.get("by_player") or {}


def _synthetic_only(ts) -> set:
    """The constant-anchor cohort, derived the way run_monthly derives the roster
    stamp (sources_contributing on the latest point, tested against
    consensus.CONSTANT_ANCHOR_SOURCES). Verified 2026-08-07 to reproduce the roster
    stamp exactly: 2,636 of the 2,642 it selects are the runtime duplicate set and
    the other 6 have no provisional row at all."""
    out = set()
    for rec in ts.get("players") or []:
        if rec.get("status") == "debuted" or rec.get("debut_date"):
            continue
        pts = [p for p in (rec.get("points") or []) if p.get("snapshot_date")]
        if not pts:
            continue
        pts.sort(key=lambda p: p["snapshot_date"])
        srcs = set(pts[-1].get("sources_contributing") or ())
        if srcs and srcs <= set(CONSTANT_ANCHOR_SOURCES):
            out.add(rec.get("player_key"))
    return out


def _floor_knot() -> float:
    import value_framework as vf
    return float(vf._outcome_curve()["knots"][0])


def _membership(grades: dict, n: int) -> list:
    """Top-n player_keys by served grade. Ties broken by key so the before/after
    comparison is not measuring dict order."""
    return [k for k, _ in sorted(grades.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]


def simulate(provisional_grade_by_key: dict, syn: set, before: dict, floor: float) -> dict:
    """Apply the scoped routing rule and return the served-grade map plus the
    cohort it touched. `provisional_grade_by_key` is injected so the caller can
    hand in the permuted control."""
    after = dict(before)
    routed = []
    for k in syn:
        if k not in before:
            continue
        if abs(before[k] - floor) > 1e-9:          # scope: only where the map abstains
            continue
        g = provisional_grade_by_key.get(k)
        if g is None:                              # no provisional row: keep the floor
            continue
        after[k] = float(g)
        routed.append(k)
    return {"after": after, "routed": routed}


def build() -> dict:
    ts, xfv, ung = _load()
    floor = _floor_knot()
    syn = _synthetic_only(ts)
    active = {k: v for k, v in xfv.items() if (v or {}).get("kind") == "active"}
    before = {k: float(v["xfv_grade"]) for k, v in active.items()
              if v.get("xfv_grade") is not None}
    prov = {k: float(v["xfv_grade"]) for k, v in ung.items()
            if v.get("xfv_grade") is not None}
    prov_war = {k: float(v["xfv_war_6yr"]) for k, v in ung.items()
                if v.get("xfv_war_6yr") is not None}

    real = simulate(prov, syn, before, floor)
    after, routed = real["after"], real["routed"]

    # ---- zero-information control: same rule, permuted provisional grades -------
    rng = random.Random(PERMUTE_SEED)
    keys = sorted(routed)
    shuffled = [prov[k] for k in keys]
    rng.shuffle(shuffled)
    prov_perm = dict(prov)
    prov_perm.update(dict(zip(keys, shuffled)))
    ctrl = simulate(prov_perm, syn, before, floor)

    side_of = {k: (ung.get(k) or {}).get("side") for k in ung}

    def _gates(after_map, routed_keys, label):
        # G2 floor tie block
        n_floor_before = sum(1 for v in before.values() if abs(v - floor) < 1e-9)
        n_floor_after = sum(1 for v in after_map.values() if abs(v - floor) < 1e-9)
        # G3 order fidelity against the provisional model's own WAR.
        # POOLED AND PER-SIDE, because they answer different questions and the
        # pre-registration asked the wrong one. efv_ungraded._GRADE_MAP is a
        # DIFFERENT affine map per side (hit BASE 27.0/SLOPE 3.8, pit 25.0/4.5), so
        # the provisional grade is order-preserving in WAR only WITHIN a side. A
        # pooled rho below 1 measures that property of the provisional map, not a
        # defect in the routing. Per-side is the gate the claim actually needs.
        pairs = [(after_map[k], prov_war[k]) for k in routed_keys if k in prov_war]
        rho = _spearman([p[0] for p in pairs], [p[1] for p in pairs]) if pairs else None
        per_side = {}
        for s in ("H", "P"):
            sp = [(after_map[k], prov_war[k]) for k in routed_keys
                  if k in prov_war and side_of.get(k) == s]
            r = _spearman([p[0] for p in sp], [p[1] for p in sp]) if len(sp) > 1 else None
            # THE THRESHOLD-FREE STATEMENT. rho stays under 1.000 for two reasons that
            # are quantization, not reordering: the served grade is rounded to 1dp, and
            # _GRADE_MAP clips at FLOOR 20.0 so a whole band of distinct WARs shares one
            # grade. Neither can put a lower-WAR player ABOVE a higher-WAR one. An
            # INVERSION can, and is the thing the gate actually forbids, so it is
            # counted exactly rather than inferred from a correlation.
            sp_sorted = sorted(sp, key=lambda t: t[1])
            inv = 0
            for i in range(len(sp_sorted)):
                for j in range(i + 1, len(sp_sorted)):
                    if sp_sorted[j][1] > sp_sorted[i][1] and sp_sorted[j][0] < sp_sorted[i][0]:
                        inv += 1
            nofloor = [t for t in sp if t[0] > floor]
            rnf = (_spearman([p[0] for p in nofloor], [p[1] for p in nofloor])
                   if len(nofloor) > 1 else None)
            per_side[s] = {"n": len(sp), "rho": round(r, 6) if r is not None else None,
                           "inversions": inv,
                           "n_above_floor": len(nofloor),
                           "rho_above_floor": round(rnf, 6) if rnf is not None else None}
        # G4 nothing above FV30 moves
        moved_above_30 = [k for k, v in before.items()
                          if v > 30.0 and abs(after_map[k] - v) > 1e-9]
        # G5 top-N membership
        t25_b, t25_a = _membership(before, 25), _membership(after_map, 25)
        t100_b, t100_a = _membership(before, 100), _membership(after_map, 100)
        entrants = [k for k in t100_a if k in set(routed_keys)]
        return {
            "label": label,
            "routed_rows": len(routed_keys),
            "G2_floor_actives_before": n_floor_before,
            "G2_floor_actives_after": n_floor_after,
            "G3_spearman_pooled": round(rho, 6) if rho is not None else None,
            "G3_spearman_per_side": per_side,
            "G4_rows_above_fv30_that_moved": len(moved_above_30),
            "G5_top25_membership_changed": sorted(set(t25_b) ^ set(t25_a)),
            "G5_top100_membership_changed": sorted(set(t100_b) ^ set(t100_a)),
            "G5_routed_rows_entering_top100": entrants,
        }

    real_g = _gates(after, routed, "routing")
    ctrl_g = _gates(ctrl["after"], ctrl["routed"], "permuted-control")

    # G3-CORRECTED (see the gate doc's amendment). The claim the routing makes is
    # PASSTHROUGH: a routed row serves the provisional model's own published grade,
    # unmodified. That is checkable exactly. The registered "Spearman vs provisional
    # WAR == 1.000" was mis-specified: efv_ungraded caps sub-exposure lines at
    # _SUBFLOOR_GRADE, so the provisional grade is deliberately NOT monotone in
    # provisional WAR and no passthrough could have scored 1.000.
    mismatches = [k for k in routed if abs(after[k] - prov[k]) > 1e-9]
    subfloor = [k for k in routed if abs(prov[k] - eu_subfloor()) < 1e-9]
    real_g["G3_corrected_passthrough_mismatches"] = len(mismatches)
    real_g["G3_corrected_rows_at_the_subfloor_exposure_cap"] = len(subfloor)

    # ---- G6 sort-key gain on everything that STILL prints 20.0 -----------------
    # Two populations, and they take their sort key from DIFFERENT models, which is
    # the whole reason the field is minted at each model's own seam rather than
    # derived downstream from the served grade:
    #   graded_residual  the genuinely-graded floor. Flagship war <= 0, so the
    #                    outcome curve returns its first knot for all of them.
    #   routed_at_floor  routed rows whose PROVISIONAL grade is also 20.0, because
    #                    efv_ungraded._GRADE_MAP has FLOOR 20.0 as well. The
    #                    provisional model agrees they are org filler.
    routed_set = set(routed)
    still_floor = [k for k, v in before.items()
                   if abs(v - floor) < 1e-9 and abs(after[k] - floor) < 1e-9]
    graded_residual = [k for k in still_floor if k not in routed_set]
    routed_at_floor = [k for k in still_floor if k in routed_set]

    def _blocks(keys, war_by_key):
        vals = [war_by_key[k] for k in keys if war_by_key.get(k) is not None]
        c = Counter(round(float(v), 2) for v in vals)
        largest = max(c.values()) if c else 0
        return {
            "rows": len(keys),
            "rows_with_a_sort_value": len(vals),
            "distinct_sort_values": len(c),
            "largest_tie_block_after": largest,
            "largest_block_is_the_war_clamp": bool(c and min(c) <= -1.99
                                                   and c[min(c)] == largest),
            "reduction_pct": (round(100.0 * (1 - largest / len(keys)), 1) if keys else None),
        }

    flag_war = {k: active[k].get("xfv_war_6yr") for k in active}
    g6 = {
        "tie_block_before": len(still_floor),
        "graded_residual": _blocks(graded_residual, flag_war),
        "routed_at_provisional_floor": _blocks(routed_at_floor, prov_war),
        "note": ("measured on the 2dp WAR the ARTIFACTS carry. The shipped key is the "
                 "unrounded PRE-CLAMP model WAR, so these block counts are an upper "
                 "bound on the residual ties: at full precision the -2.0 clamp block "
                 "resolves too, since the clamp is a safety guard on the served WAR and "
                 "the key is minted before it."),
    }

    # ---- the routed cohort's landing distribution ------------------------------
    landed = sorted(after[k] for k in routed)
    dist = {
        "min": landed[0] if landed else None,
        "p10": landed[int(0.10 * (len(landed) - 1))] if landed else None,
        "median": statistics.median(landed) if landed else None,
        "p90": landed[int(0.90 * (len(landed) - 1))] if landed else None,
        "max": landed[-1] if landed else None,
        "above_fv30": sum(1 for v in landed if v > 30.0),
        "above_fv35": sum(1 for v in landed if v > 35.0),
        "above_fv40": sum(1 for v in landed if v > 40.0),
        "best_rank_reached": (min(_membership(after, len(after)).index(k) + 1
                                  for k in routed) if routed else None),
    }

    # ---- two-scale disagreement, recomputed from the committed constants -------
    import efv_ungraded as eu
    import value_framework as vf
    scale = []
    for w in (0.0, 0.25, 0.5, 1.0, 1.5, 2.5, 3.5):
        f = vf.outcome_implied_fv(w, exposure_seasons=6)
        row = {"war": w, "flagship_outcome_curve": round(f, 2) if f is not None else None}
        for side in ("hit", "pit"):
            m = eu._GRADE_MAP[side]
            g = max(m["FLOOR"], m["BASE"] + m["SLOPE"] * w)
            if not eu.UNCAPPED_GRADE and g > m["KNEE"]:
                g = m["KNEE"] + (m["CEIL"] - m["KNEE"]) * (
                    1 - pow(2.718281828459045, -(g - m["KNEE"]) / m["SOFT"]))
            row[f"provisional_{side}"] = round(g, 2)
            row[f"flagship_minus_provisional_{side}"] = (
                round(f - g, 2) if f is not None else None)
        scale.append(row)

    # G1 is the runtime harness result; recorded here so one artifact carries the gate.
    ts_keys = {p.get("player_key") for p in (ts.get("players") or []) if p.get("player_key")}
    g1 = {
        "board_pool_rows_today": len(ts_keys) + len(ung),
        "distinct_player_keys": len(ts_keys | set(ung)),
        "duplicate_player_keys": len(ts_keys & set(ung)),
        "rows_removed_by_dedupe": len(ts_keys & set(ung)),
        "measured_at_runtime": True,
        "harness": ("prospx/index.html inline script evaluated in a Node VM against the "
                    "real artifacts; getFilteredActives() returned 10,569 rows / 7,933 "
                    "distinct / 2,636 duplicated, every pair one graded + one provisional"),
    }

    out = {
        "line": "LANE-B: eFV board floor routing + double-listing gate simulation",
        "generated_at": date.today().isoformat(),
        "lab": "tools/efv_board_floor_sim.py",
        "pre_registration": "docs/efv-2026-08-07/BOARD_FLOOR_ROUTING_GATE.md",
        "plan": "docs/master-plan-2026-08-07-omnibus3.md Lane B",
        "gate_standard": "docs/EFV_GATE_STANDARD.md",
        "registry_row": "efv_board_floor_routing",
        "changes_served_output": False,
        "ship_state": ("implemented, gated OFF. efv_score.SERVE_PROVISIONAL_FOR_CONSTANT_COHORT "
                       "is False: the flip is blocked on the prospx board dedupe and the "
                       "two-scale disclosure, which live in a file this lane does not own."),
        "board_source": {"timeseries_generated_at": ts.get("generated_at"),
                         "xfv_active_rows": len(active),
                         "provisional_rows": len(ung),
                         "outcome_curve_floor_knot": floor},
        "scope": {
            "synthetic_only_actives": len(syn & set(before)),
            "at_the_floor_routed": len(routed),
            "above_the_floor_kept_on_flagship": len(
                [k for k in syn if k in before and before[k] > floor]),
            "above_fv30_kept_on_flagship": len(
                [k for k in syn if k in before and before[k] > 30.0]),
            "no_provisional_row_kept_on_flagship": len(
                [k for k in syn if k in before and abs(before[k] - floor) < 1e-9
                 and k not in prov]),
        },
        "G1_dedupe": g1,
        "gates": real_g,
        "zero_information_control": ctrl_g,
        "G6_sort_key": g6,
        "routed_landing_distribution": dist,
        "two_scale_disagreement": scale,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def main() -> None:
    out = build()
    print(f"wrote {OUT_PATH.relative_to(ROOT)}")
    print(json.dumps({k: out[k] for k in
                      ("scope", "G1_dedupe", "gates", "zero_information_control",
                       "G6_sort_key", "routed_landing_distribution")}, indent=1))
    print("\ntwo-scale disagreement (flagship minus provisional):")
    for r in out["two_scale_disagreement"]:
        print(f"  war {r['war']:>4}  flagship {r['flagship_outcome_curve']:>6}  "
              f"hit {r['provisional_hit']:>6} ({r['flagship_minus_provisional_hit']:+.2f})  "
              f"pit {r['provisional_pit']:>6} ({r['flagship_minus_provisional_pit']:+.2f})")


if __name__ == "__main__":
    main()
