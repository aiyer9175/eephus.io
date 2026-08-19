"""V1 power projection: the RESOLVED_THROUGH-2026 label advance, PROJECTION ONLY.

Registration: docs/efv-2026-08-19/EPOCH_2026_PREREGISTRATION.md, section
"Power projection (runs NOW, projection only)". This lab adjudicates NOTHING.
It scales the STORED bootstrap components of the current C1-C4 claim-frame
floors (CONVICTION_PROGRAM.md V5 frame) to the projected pool sizes after the
2025 debut cohort is admitted, and publishes per cell: current floor, projected
floor, current delta, the delta needed to clear under Holm-4, and the honest
read on label-only resolvability.

Inputs (read only, never regenerated here):
  data/xfv_headtohead_frame_eval.json  vintage-matched pooled sd (C1/C2 basis)
  data/xfv_power_eval.json             headtohead_common refit share (verified,
                                       not quoted), debuted_km E_cond/E_refit
  data/xfv_auc_floor_eval.json         C3/C4 E_cond + E_refit components
  data/xfv_mde_floor.json              legacy pooled-rho floor, context row
  data/source_backtest.json            vintage-matched per-rater legs (best
                                       rater), pooled current delta
  data/debuts.json                     cohort sizing (2025 debuts, side split,
                                       2011-2024 tracked-debut base rates)

Output: data/xfv_epoch2026_power_projection.json with projection_only: true.
Deterministic, no bootstrap, no model refit. Rerunnable at will.
"""

from __future__ import annotations

import json
import math
import os
from statistics import NormalDist

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(DATA, "xfv_epoch2026_power_projection.json")

Z_MDE95 = 1.645  # one-sided, the EFV_GATE_STANDARD section 1 convention
# Holm across the four claim-frame cells, one-sided alphas by rank.
HOLM_ALPHAS = [0.0125, 0.05 / 3.0, 0.025, 0.05]
HOLM_Z = [round(NormalDist().inv_cdf(1.0 - a), 4) for a in HOLM_ALPHAS]

PIT_TOKENS = {"P", "SP", "RP", "SIRP", "MIRP", "LHP", "RHP", "SWING"}


def _load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


def _is_pitcher(position):
    pos = (position or "").upper()
    if not pos:
        return False
    parts = [p.strip() for p in pos.split("/") if p.strip()]
    return bool(parts) and all(p in PIT_TOKENS for p in parts)


def _debut_counts(debuts):
    """Tracked-debut headcounts: 2025 cohort and the 2011-2024 base by side."""
    c25 = {"hit": 0, "pit": 0}
    base = {"hit": 0, "pit": 0}
    for row in debuts:
        year = (row.get("debut_date") or "")[:4]
        if not year:
            continue
        side = "pit" if _is_pitcher(row.get("position")) else "hit"
        if year == "2025":
            c25[side] += 1
        elif "2011" <= year <= "2024":
            base[side] += 1
    return c25, base


def _project_sd(sd_total, refit_share, n_cur, n_proj):
    """Split sd^2 into a held-fixed refit component and a sampling component,
    scale the sampling component by n_cur/n_proj, recombine."""
    var = sd_total * sd_total
    refit_var = refit_share * var
    samp_var = (1.0 - refit_share) * var
    return math.sqrt(refit_var + samp_var * (n_cur / n_proj))


def _round(x, k=5):
    return None if x is None else round(x, k)


def _cell_block(name, frame, estimator, n_cur, n_inc, sd_cur, refit_share,
                delta_cur, delta_basis, notes):
    n_proj = n_cur + n_inc
    sd_proj = _project_sd(sd_cur, refit_share, n_cur, n_proj)
    floor_cur = Z_MDE95 * sd_cur
    floor_proj = Z_MDE95 * sd_proj
    holm_needed = {
        "worst_rank_z2.2414": HOLM_Z[0] * sd_proj,
        "rank2_z2.128": HOLM_Z[1] * sd_proj,
        "rank3_z1.96": HOLM_Z[2] * sd_proj,
        "best_rank_z1.645": HOLM_Z[3] * sd_proj,
    }
    return {
        "cell": name,
        "frame": frame,
        "estimator": estimator,
        "n_current": round(n_cur, 1),
        "n_increment_projected": round(n_inc, 1),
        "n_projected": round(n_proj, 1),
        "sd_current": _round(sd_cur),
        "sd_projected": _round(sd_proj),
        "floor_current_mde95": _round(floor_cur),
        "floor_projected_mde95": _round(floor_proj),
        "floor_reduction_pct": round(100.0 * (1.0 - floor_proj / floor_cur), 2),
        "refit_share_held_fixed": round(refit_share, 4),
        "delta_current": _round(delta_cur),
        "delta_current_basis": delta_basis,
        "delta_needed_holm4": {k: _round(v) for k, v in holm_needed.items()},
        "margin_x_projected_floor": (
            _round(delta_cur / floor_proj, 3) if delta_cur is not None else None
        ),
        "notes": notes,
    }


def main():
    h2h_frame = _load("xfv_headtohead_frame_eval.json")
    power = _load("xfv_power_eval.json")
    auc = _load("xfv_auc_floor_eval.json")
    mde = _load("xfv_mde_floor.json")
    backtest = _load("source_backtest.json")
    debuts = _load("debuts.json")

    c25, base = _debut_counts(debuts)
    base_total = base["hit"] + base["pit"]

    # --- verify the head-to-head refit share from stored components (never quote it)
    h2h_cell = power["partb_floors"]["cells"]["headtohead_common"]
    sd_refit = h2h_cell["E_refit"]["sd"]
    sd_cond = h2h_cell["E_cond"]["sd"]
    h2h_refit_share = 1.0 - (sd_cond / sd_refit) ** 2
    h2h_refit_share_stored = h2h_cell["refit_share_of_variance"]

    # --- C1/C2 basis: pooled vintage-matched cluster bootstrap (refit inside draw)
    vm = h2h_frame["vintage_matched"]
    vm_point = h2h_frame["point"]["vintage_matched"]
    n_vm = vm_point["n_rows"]
    sd_vm_pooled = vm["sd"]  # refit-inclusive by protocol

    # per-side split assumption: proportional to tracked-debut side shares
    n_vm_hit = n_vm * base["hit"] / base_total
    n_vm_pit = n_vm * base["pit"] / base_total
    vm_rate = n_vm / base_total  # vintage-matched rows per tracked debut
    inc_vm_hit = c25["hit"] * vm_rate
    inc_vm_pit = c25["pit"] * vm_rate

    # pooled sampling variance -> per-side current sd (sampling scales by n,
    # refit component held fixed at the verified head-to-head share)
    vm_var = sd_vm_pooled * sd_vm_pooled
    vm_refit_var = h2h_refit_share * vm_var
    vm_samp_var_pooled = (1.0 - h2h_refit_share) * vm_var

    def vm_side_sd(n_side, with_refit):
        samp = vm_samp_var_pooled * (n_vm / n_side)
        return math.sqrt(samp + (vm_refit_var if with_refit else 0.0))

    # current best-rater legs on the pooled vintage-matched frame
    vm_raters = backtest["accuracy"]["pooled_efv_common_vintage_matched"]
    best_name, best_rho = max(
        ((k, v["spearman"]) for k, v in vm_raters.items() if k != "xfv"),
        key=lambda kv: kv[1],
    )
    xfv_rho = vm_raters["xfv"]["spearman"]
    pooled_delta_vs_best = xfv_rho - best_rho

    cells = []
    for side, n_side, inc in (
        ("C1", n_vm_hit, inc_vm_hit),
        ("C2", n_vm_pit, inc_vm_pit),
    ):
        sd_cond_side = vm_side_sd(n_side, with_refit=False)
        sd_refit_side = vm_side_sd(n_side, with_refit=True)
        label = "hitters" if side == "C1" else "pitchers"
        common_notes = [
            "per-side vintage-matched floors are CONSTRUCTED here from the pooled "
            "sd {} (xfv_headtohead_frame_eval.json, refit-inside-draw cluster "
            "bootstrap); no per-side floor is stored anywhere".format(sd_vm_pooled),
            "per-side n split assumed proportional to tracked-debut side shares "
            "({} hit / {} pit over 2011-2024)".format(base["hit"], base["pit"]),
            "refit share {} transferred from the headtohead_common cell (verified "
            "from stored sds, stored value {}); assumption: it transfers from the "
            "all-vintages frame to the vintage-matched frame".format(
                round(h2h_refit_share, 4), h2h_refit_share_stored
            ),
            "delta_current is the POOLED vintage-matched delta vs the best rater "
            "({} {}); per-side deltas vs best rater are NOT stored and the pooled "
            "read is NEGATIVE: no floor reduction clears a negative delta".format(
                best_name, round(best_rho, 4)
            ),
        ]
        refit_share_for_cell_cond = 0.0  # E_cond: fit held fixed, all sampling
        cells.append(
            _cell_block(
                side,
                "{}, vintage-matched common set, Spearman vs best rater".format(label),
                "E_cond primary (constructed), E_refit beside",
                n_side,
                inc,
                sd_cond_side,
                refit_share_for_cell_cond,
                pooled_delta_vs_best,
                "pooled vintage-matched xfv {} minus best rater {} {} "
                "(source_backtest.json); PROXY, not the per-side cell delta".format(
                    round(xfv_rho, 4), best_name, round(best_rho, 4)
                ),
                common_notes,
            )
        )
        # E_refit companion for the same cell
        cells[-1]["E_refit_beside"] = {
            "sd_current": _round(sd_refit_side),
            "sd_projected": _round(
                math.sqrt(
                    vm_refit_var
                    + vm_samp_var_pooled * (n_vm / (n_side + inc))
                )
            ),
            "floor_projected_mde95": _round(
                Z_MDE95
                * math.sqrt(
                    vm_refit_var
                    + vm_samp_var_pooled * (n_vm / (n_side + inc))
                )
            ),
        }

    # --- C3/C4: debuted_km contributor AUC, stored E_cond + E_refit components
    auc_specs = (
        ("C3", "hit.debuted_km.contributor", "hit"),
        ("C4", "pit.debuted_km.contributor", "pit"),
    )
    for name, key, side in auc_specs:
        cell = auc["cells"][key]
        n_cur = cell["n"]
        rate = n_cur / base[side]  # shared-label rows per tracked debut, 14y avg
        inc = c25[side] * rate
        sd_c = cell["E_cond"]["sd"]
        sd_r = cell["E_refit"]["sd"]
        label = "hitters" if side == "hit" else "pitchers"
        notes = [
            "increment = 2025 {} debuts ({}) x historical entry rate {} "
            "(= cell n {} / tracked {} debuts 2011-2024 {})".format(
                label, c25[side], round(rate, 3), n_cur, label, base[side]
            ),
            "delta_current is vs the CONSENSUS baseline (stored cell margin); the "
            "claim frame compares vs the BEST rater, which can only tighten it",
            "prevalence of the contributor label among new rows assumed equal to "
            "the pool's; new rows carry only 2 observed seasons, so their KM "
            "labels are noisier and pure sqrt-n scaling OVERSTATES the reduction",
        ]
        block = _cell_block(
            name,
            "{}, debuted_km, contributor AUC vs best rater".format(label),
            "E_cond primary (stored)",
            n_cur,
            inc,
            sd_c,
            0.0,  # E_cond resamples test rows conditional on the fit
            cell["margin"],
            "stored margin vs consensus baseline (xfv_auc_floor_eval.json)",
            notes,
        )
        # E_refit beside: refit variance = sd_refit^2 - sd_cond^2 held fixed
        refit_var = sd_r * sd_r - sd_c * sd_c
        samp_proj = sd_c * sd_c * (n_cur / (n_cur + inc))
        sd_r_proj = math.sqrt(refit_var + samp_proj)
        block["E_refit_beside"] = {
            "sd_current": _round(sd_r),
            "sd_projected": _round(sd_r_proj),
            "floor_projected_mde95": _round(Z_MDE95 * sd_r_proj),
            "refit_share_implied": _round(refit_var / (sd_r * sd_r), 4),
        }
        cells.append(block)

    # order C1..C4
    cells.sort(key=lambda c: c["cell"])

    out = {
        "projection_only": True,
        "adjudicates": "NOTHING. Floors are derived on the measurement frame at "
        "measurement time (EPOCH_2026_PREREGISTRATION.md protocol step 1); these "
        "numbers exist to size expectations for the V1 label advance and may not "
        "be cited as floors, margins, or verdicts.",
        "generated_at": "2026-08-19",
        "produced_by": "tools/efv_epoch_power_projection.py",
        "registration": "docs/efv-2026-08-19/EPOCH_2026_PREREGISTRATION.md "
        "(Power projection section); companion on the conviction program V1 lane",
        "claim_frame": "CONVICTION_PROGRAM.md V5, C1-C4, Holm across four, "
        "E_cond primary",
        "method": {
            "scaling": "sd^2 split into refit component (held fixed) and sampling "
            "component (scaled by n_cur/n_proj); MDE95 = 1.645 * sd one-sided",
            "holm_z_one_sided": dict(zip(
                ["rank1_alpha_.0125", "rank2_alpha_.0167",
                 "rank3_alpha_.025", "rank4_alpha_.05"], HOLM_Z)),
            "direction_of_error": [
                "refit component held fixed: more training labels should shrink "
                "refit noise, so E_refit projections are conservative (too high)",
                "sqrt-n on headcount ignores censoring: 2025-cohort rows carry 2 "
                "observed seasons (weight 1/3 in pair-weighted rho, noisier KM "
                "labels in AUC), so projected reductions are OVERSTATED, "
                "especially for the weighted Spearman cells",
                "entry rates are 14-year averages; recent cohorts are covered "
                "more densely, so headcount increments are modestly understated",
                "C1/C2 may also gain earlier-debut players whose decision year "
                "is 2025 (new fold); not counted, increments understated there",
            ],
        },
        "cohort": {
            "debuts_2025_total": c25["hit"] + c25["pit"],
            "debuts_2025_hit": c25["hit"],
            "debuts_2025_pit": c25["pit"],
            "tracked_debuts_2011_2024": {"hit": base["hit"], "pit": base["pit"]},
            "side_rule": "position all pitcher tokens (P/SP/RP/SIRP/MIRP/LHP/RHP)"
            " -> pit, else hit",
        },
        "headtohead_refit_share_verification": {
            "stored": h2h_refit_share_stored,
            "recomputed_from_components": round(h2h_refit_share, 6),
            "components": {"sd_E_refit": sd_refit, "sd_E_cond": sd_cond},
            "formula": "1 - (sd_E_cond / sd_E_refit)^2",
            "match": abs(h2h_refit_share - h2h_refit_share_stored) < 5e-4,
        },
        "context_floors_not_projected": {
            "pooled_rho_legacy_mde95": mde["weighted"]["hit"]["mde95"],
            "note": "xfv_mde_floor.json is the 11-fold pooled-rho floor (0.044 "
            "convention); it is not a claim-frame cell and is listed for "
            "orientation only",
        },
        "cells": cells,
        "honest_read": {
            "any_cell_plausibly_resolves_on_labels_alone": False,
            "per_cell": {
                "C1": "NO. Pooled vintage-matched delta vs best rater is "
                "negative; a 4-5 pct floor reduction cannot clear a negative "
                "delta. Resolution requires the delta itself to move (V2/V3), "
                "or the per-side measurement to land far from the pooled read.",
                "C2": "NO. Same structure as C1.",
                "C3": "CLOSEST BUT NO at the stored margin. Projected E_cond "
                "floor stays above the stored 0.00965 consensus-baseline "
                "margin even in the most favorable Holm slot, and the "
                "best-rater comparator can only tighten the margin.",
                "C4": "NO. Stored margin sits near 0.2x of the projected floor.",
            },
            "expected_value_of_V1": "a 4-8 pct floor reduction across the four "
            "cells plus the first pitcher-stuff fold; the label-pool lever "
            "alone does not resolve the claim frame at current deltas, matching "
            "the prereg's 'no cell clears' pre-committed interpretation as the "
            "central expectation.",
        },
    }

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
        fh.write("\n")
    print("wrote", os.path.normpath(OUT))
    for c in out["cells"]:
        print(
            c["cell"],
            "floor", c["floor_current_mde95"], "->", c["floor_projected_mde95"],
            "({}% lower), delta_cur".format(c["floor_reduction_pct"]),
            c["delta_current"],
            "needed(worst Holm)", c["delta_needed_holm4"]["worst_rank_z2.2414"],
        )


if __name__ == "__main__":
    main()
