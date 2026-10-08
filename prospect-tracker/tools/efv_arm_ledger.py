"""A-CLAIM-15: how many arms has this program actually tested?

WHY IT MATTERS, stated plainly. Every driver lane in this repo reports honest
per-lane statistics: a floor derived on the lane's own frame, a Holm correction
across the lane's own family, a zero-information twin, permutation nulls. Each
lane is defensible on its own terms. What no artifact has ever said is how many
lanes there have BEEN.

That number is the one a reader needs to interpret any survivor. Fifty arms tested
at a nominal 5% produce about two spurious passes on pure noise, and each of those
two arrives wearing a per-lane Holm correction that is perfectly correct and
completely beside the point. The per-lane corrections control the error rate
WITHIN a lane. Nothing has ever controlled it ACROSS lanes, because nothing
counted them.

WHAT THIS IS AND IS NOT. It is a COUNT, assembled from the committed artifacts.
It is not a retrospective correction: applying a program-wide Holm after the fact
to arms that were gated under different frames, different pools and different
label definitions would be arithmetic theatre, and it would imply a joint family
that never existed. What the count does is make the denominator visible, so that
the next survivor is read against it rather than against its own lane alone.

THE ONE PLACE IT BINDS. Under the alpha-spending clause
(docs/efv-2026-08-19/EPOCH_2026_PREREGISTRATION.md) exactly one confirmatory read
of the claim family is declared. A survivor found during exploration and confirmed
on the reserved 2025 fold is worth something. A survivor found and confirmed on
the same rows is worth nothing, however many bootstraps it carries, and this
ledger is how anyone can tell which of the two they are looking at.

Offline. Reads committed artifacts only, spends nothing, and writes
data/xfv_arm_ledger.json.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "xfv_arm_ledger.json"

#: Every artifact that holds gated arms, and where the arms live inside it.
#: A lane missing from this list is a lane the count cannot see, which is why the
#: ledger publishes `sources_missing` rather than quietly producing a smaller
#: number.
SOURCES: tuple[tuple[str, str, str], ...] = (
    ("xfv_driver_freekeys.json", "arms", "free _vec keys (D-1)"),
    ("xfv_driver_extras.json", "arms", "tools_json _extras arms (D-2)"),
    ("xfv_driver_gated_pairs.json", "arms", "pre-registered pairs"),
    ("xfv_driver_handedness.json", "arms", "handedness sidecar"),
    ("xfv_driver_sb_rate.json", None, "stolen-base rate"),
    ("xfv_driver_wrc.json", None, "wRC+ add arm"),
    # Driver System V2 (docs/efv-v2/DRIVER_SYSTEM_V2.md s5 DS-06): every candidate
    # driver the admission rule checked, with its per-vintage signs.
    ("xfv_driver_admission.json", "arms", "admission rule (DS-06)"),
    # The assembled V2 (DS-09, DS-10, the BMI re-test, PV-12): the admission rule on the
    # list-vintage frame, per development fold, for every V2 candidate.
    ("efv_v2_assembly.json", "arms", "V2 assembly admission (list vintages)"),
    # The screening lab (tools/efv_screen_lab.py, EFV3 lane B s4): every (candidate,
    # side) arm of a wave with the floor it was read against (`floor_rho` on the arm),
    # written by the registered run only (EFV3_B7).
    ("xfv_screen_wave1.json", "arms", "screening lab wave 1"),
    # Z1, the driver re-test on the frozen fWAR label (kill rule 8 of
    # docs/efv-2026-10-03/LABEL_V3_DRIVER_RETEST_GATE.md: the denominator is published with
    # this registration as a new lane). The two `fv` liveness controls sit in the
    # artifact's `liveness` block, outside `arms`, so they are not counted as arms.
    ("xfv_driver_retest.json", "arms", "Z1 driver re-test (fWAR label)"),
)

#: Sources registered before their producer's registered run. Absent, they are listed
#: under `sources_pending` (a lane that has not run yet), not `sources_missing` (a lane
#: the count cannot see); present, they are read like any other. The producer's
#: registered run removes the name here in its own commit.
PENDING: frozenset[str] = frozenset({"xfv_screen_wave1.json"})

#: Development probes that are NOT feature arms: validity reads (a label-balance
#: screen, a leak regression). Counted and listed apart, like sweeps, and never summed
#: into the arm count, because they test the frame rather than a driver.
PROBES: tuple[tuple[str, str, str], ...] = (
    ("efv_identity_balance.json", "probes", "identity balance probes (DS-03)"),
    ("efv_v2_assembly.json", "probes", "combiner rule reads (DS-08)"),
    # DS-11: each served overlay graded out of sample, per side; DS-17: each P(bust)
    # arm scored by Brier and log loss, per side and frame. Reads of the label, so they
    # are counted; they test a served overlay or a calibration, not a rank driver.
    ("efv_overlay_oos_eval.json", "probes", "served overlay grades (DS-11)"),
    ("efv_v2_pbust_eval.json", "probes", "P(bust) calibration reads (DS-17)"),
    # DS-16: the one pre-declared development read of the assembled V2, one probe per
    # frame (each carries five comparisons by the within, pooled and AUC statistics).
    # A dotted key names a block inside the artifact.
    ("efv_v2_dev_eval.json", "ds16.probes", "V2 development read (DS-16)"),
    # EFV3_C03: the one model-class screen (docs/efv-v2/MODEL_CLASS_SCREEN.md), one
    # probe per arm and frame (ten), each carrying the arm-minus-V2 within delta, its
    # twin, its permutation p and its Holm-adjusted p; a failed arm reads NULL.
    ("efv_v2_model_class_screen.json", "probes", "model-class screen (EFV3_C03)"),
    # EFV3 lane A G7: the one validity read of the bust pool ids (W3 > 0 share by the
    # bust_id_resolved indicator on the lv_dev pool rows); counts, never a score.
    ("efv_bust_pool_receipt.json", "probes", "bust pool id balance (EFV3 G7)"),
    # Q10_10 (owner ask 19): the pitch-rate sidecar's no-outcome steps, coverage by
    # (V, side) and descriptive correlations with obp_rel, k_rel and bb_rel.
    ("_labs/efv_pitch_rate_features.json", "probes", "pitch-rate sidecar probes (PM19)"),
)

#: Fields an arm may carry that the ledger copies through unchanged, so a driver's
#: per-vintage signs sit next to its gate (DS-06).
PASS_THROUGH = ("per_vintage_signs", "mean_abs_t", "n_valid_vintages", "admitted",
                "head", "reason", "delta_vs_consensus", "ci95", "partial")

#: Lanes whose artifact holds sweeps rather than arms. Counted separately and
#: NEVER pooled with the arm count: a sweep over a continuous knob is not the
#: same multiplicity object as an independent feature arm, and adding them would
#: overstate the count as surely as ignoring them understates it.
SWEEPS: tuple[tuple[str, str], ...] = (
    ("xfv_driver_lambda_sweep.json", "blend-lambda sweep"),
    ("xfv_driver_elite_band.json", "elite-band raise sweep"),
)


def _load(name: str):
    p = DATA / name
    if not p.exists():
        return None, "absent"
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except (OSError, ValueError) as exc:
        return None, f"unreadable: {exc}"


def _side_of(tag: str) -> str | None:
    """"hit" or "pit" out of an arm tag like "D1:hit.fv_trend" or "hit.tool_gap"."""
    t = str(tag or "")
    if "hit" in t:
        return "hit"
    if "pit" in t:
        return "pit"
    return None


def _verdict_of(arm: dict) -> str:
    """The arm's own recorded verdict, or an honest statement that it has none.

    Most committed arms predate the verdict vocabulary entirely: the driver lab
    only began writing `verdict` on 2026-09-06, and neither freekeys nor extras
    carries one. Those arms were adjudicated by a human reading the delta against
    the floor. Reporting them as PASS or NULL here would be inventing a record,
    so they are counted as adjudicated-without-a-stored-verdict and the reader is
    told how many there are.
    """
    v = arm.get("verdict")
    if isinstance(v, str) and v:
        return v
    return "NO_STORED_VERDICT"


def collect() -> dict:
    rows, missing, pending = [], [], []
    for name, key, label in SOURCES:
        doc, why = _load(name)
        if doc is None:
            if name in PENDING and why == "absent":
                pending.append({"artifact": name, "why": "registered; producer has "
                                                          "not run", "lane": label})
            else:
                missing.append({"artifact": name, "why": why, "lane": label})
            continue
        stamp = doc.get("generated_at") or doc.get("produced_at")
        if key is None:
            # A single-arm artifact: the whole document IS the arm.
            rows.append({
                "lane": label, "artifact": name,
                "arm": doc.get("tag") or name,
                "verdict": _verdict_of(doc),
                "delta_rho": ((doc.get("delta") or {}).get("rho")
                              if isinstance(doc.get("delta"), dict) else None),
                "generated_at": stamp,
            })
            continue
        arms = doc.get(key) or {}
        if isinstance(arms, list):
            # A screening artifact lists its arms; the MEASURED ones are arms, an arm
            # whose column could not be built on the run's tree was never a look.
            arms = {str(a.get("tag") or i): a for i, a in enumerate(arms)
                    if isinstance(a, dict) and a.get("measured", True)}
        if not isinstance(arms, dict):
            missing.append({"artifact": name, "why": f"{key} is not a mapping",
                            "lane": label})
            continue
        floors = doc.get("floors") or {}
        for arm_key, arm in sorted(arms.items()):
            if not isinstance(arm, dict):
                continue
            d = arm.get("delta")
            rho = d.get("rho") if isinstance(d, dict) else None
            side = _side_of(arm.get("tag") or arm_key)
            # TWO SPELLINGS, because the two lanes were written months apart:
            # freekeys records the floor as `rho`, extras as `MDE95_pooled_rho`.
            # They are the same quantity (the one-sided MDE95 on pooled rho,
            # taken at the max of three noise seeds). Reading only one of them
            # silently halved the scoreable count, which is exactly the kind of
            # quiet shortfall this ledger exists to make visible.
            fblk = floors.get(side) if isinstance(floors.get(side), dict) else {}
            floor = fblk.get("rho")
            if floor is None:
                floor = fblk.get("MDE95_pooled_rho")
            if floor is None:
                # The screening lab records the floor on the arm itself (per head
                # and side, derived in the same run, before the arm).
                floor = arm.get("floor_rho")
            if floor is None:
                # The Z1 re-test keys its floors by (side, frame, scope) and records the
                # one each arm was read against on the arm (`floors_used`).
                floor = (arm.get("floors_used") or {}).get("rho")
            rows.append({
                "lane": label, "artifact": name,
                "arm": arm.get("tag") or arm_key,
                "verdict": _verdict_of(arm),
                "delta_rho": rho,
                "side": side,
                "floor_rho": floor,
                # CLEARED means the point delta reached the lane's own recorded
                # floor. It is not a verdict and must not be read as one: a
                # verdict needs the Holm correction across that lane's family
                # and, for an arm gated after 2026-09-06, the co-primary AUC leg.
                # This is the weakest possible bar, published so the count of
                # arms that even reached it is on the record.
                "cleared_own_floor": (None if (rho is None or floor is None)
                                      else bool(rho >= floor)),
                "generated_at": stamp,
            })
            rows[-1].update({k: arm[k] for k in PASS_THROUGH if k in arm})

    sweeps = []
    for name, label in SWEEPS:
        doc, why = _load(name)
        if doc is None:
            missing.append({"artifact": name, "why": why, "lane": label})
            continue
        # Count the knob settings, not the arms.
        n = 0
        for v in (doc.get("sides") or doc.get("arms") or {}).values():
            n += len(v) if isinstance(v, dict) else 1
        sweeps.append({"lane": label, "artifact": name, "settings": n,
                       "generated_at": doc.get("generated_at")})

    probes = []
    for name, key, label in PROBES:
        doc, why = _load(name)
        if doc is None:
            missing.append({"artifact": name, "why": why, "lane": label})
            continue
        *path, key = key.split(".")
        for part in path:
            doc = doc.get(part) if isinstance(doc, dict) else None
        if not isinstance(doc, dict):
            missing.append({"artifact": name, "why": f"no block {'.'.join(path)}",
                            "lane": label})
            continue
        for tag, pr in sorted((doc.get(key) or {}).items()):
            if isinstance(pr, dict):
                probes.append({"lane": label, "artifact": name,
                               "probe": pr.get("tag") or tag,
                               "verdict": _verdict_of(pr),
                               "generated_at": doc.get("generated_at"),
                               **{k: pr[k] for k in PASS_THROUGH if k in pr}})

    by_lane: dict = {}
    by_verdict: dict = {}
    for r in rows:
        by_lane[r["lane"]] = by_lane.get(r["lane"], 0) + 1
        by_verdict[r["verdict"]] = by_verdict.get(r["verdict"], 0) + 1

    n = len(rows)
    scored = [r for r in rows if r.get("cleared_own_floor") is not None]
    cleared = [r for r in scored if r["cleared_own_floor"]]
    # The arithmetic a reader would otherwise have to do in their head, and the
    # reason the count is worth publishing at all.
    expected_false = round(0.05 * n, 1)
    return {
        "generated_at": datetime.now(timezone.utc)
                        .replace(microsecond=0).isoformat(),
        "produced_by": "tools/efv_arm_ledger.py",
        "n_arms": n,
        "by_lane": dict(sorted(by_lane.items(), key=lambda kv: -kv[1])),
        "by_verdict": dict(sorted(by_verdict.items(), key=lambda kv: -kv[1])),
        "n_without_stored_verdict": by_verdict.get("NO_STORED_VERDICT", 0),
        "sweeps": sweeps,
        "sweeps_are_not_arms": (
            "a sweep over a continuous knob is not the same multiplicity object "
            "as an independent feature arm; the two are reported apart and must "
            "not be summed"),
        "arms": rows,
        "probes": probes,
        "n_probes": len(probes),
        "probes_are_not_arms": (
            "a validity probe tests the frame or the resolver, not a driver; probes "
            "are listed and counted apart and never summed into the arm count"),
        "sources_missing": missing,
        "sources_pending": pending,
        "expected_spurious_passes_at_nominal_5pct": expected_false,
        "n_scoreable_against_a_floor": len(scored),
        "n_cleared_own_floor": len(cleared),
        "cleared_own_floor": [r["arm"] for r in cleared],
        "cleared_is_the_weakest_bar": (
            "`cleared_own_floor` compares the point delta to the lane's recorded "
            "rho floor and nothing else. It is not a verdict: a verdict needs "
            "the Holm correction across that lane's family, and for anything "
            "gated after 2026-09-06 the co-primary contributor-AUC leg as well. "
            "It is published because the count of arms that reached even this "
            "bar is the honest way to describe the program's yield."),
        "reading": (
            f"{n} arms have been adjudicated across {len(by_lane)} lanes, "
            f"{len(scored)} of them scoreable against a recorded floor, and "
            f"{len(cleared)} reached that floor on the point estimate. At a "
            f"nominal 5% per arm, pure noise alone would be expected to produce "
            f"about {expected_false} passes across {n} arms. "
            + ("Fewer arms cleared than noise alone would produce, which says "
               "the per-lane floors are, if anything, conservative, and that "
               "the program's run of nulls is a real result rather than a "
               "reporting artifact."
               if len(cleared) < expected_false else
               "That is at or above the noise expectation, so no survivor from "
               "this set may be read on its lane's correction alone.")
            + " Every lane's own Holm correction is correct and controls the "
            "error rate WITHIN that lane; nothing has ever controlled it across "
            "lanes, because until now nothing counted them. Read any survivor "
            "against this denominator."),
        "this_is_not_a_correction": (
            "no program-wide Holm is applied and none should be. The arms were "
            "gated on different frames, pools and label definitions, so a "
            "retrospective joint family would imply a structure that never "
            "existed. The count makes the denominator visible; the reserved 2025 "
            "fold is what actually buys confirmation."),
        "reserved_fold": {
            "cohort": "2025 base year",
            "status": "not yet resolvable",
            "enters_at_run_year": 2028,
            "rule": ("held out of every exploratory read so the confirmatory "
                     "read has rows the exploration never touched. A survivor "
                     "found and confirmed on the same rows is worth nothing."),
            "registered_in": "docs/efv-2026-08-19/EPOCH_2026_PREREGISTRATION.md",
        },
    }


# =============================================================================
# Z1: THE DERIVED ARM LIST (plan docs/master-plan-2026-09-11-war-epoch-drivers-betting.md
# section 2.1 P5, written for the fWAR label epoch's driver re-test).
#
# P5 asks for "every distinct add column from the loss-ledger artifacts, including the
# 4-fold era and the 09-04 families", deduplicated by column definition, with the
# mechanism rule (2.2) and the exclusions applied mechanically, each arm assigned to its
# family (2.3). This block does exactly that and nothing else: it READS committed
# artifacts (one of them at a pinned historical commit, named below), scores nothing,
# and writes only the file it is pointed at. It never rewrites data/xfv_arm_ledger.json.
#
# WHY THE COLUMN DEFINITIONS ARE A TABLE. Most 4-fold-era artifacts never stored a
# machine-readable column definition: efv_lab_runner variants were ad hoc spec files
# that were not committed. Each definition below is read off the artifact's own text
# (or the producing tool, cited) and the extractor RAISES on an arm id the table does
# not define, so the list cannot silently shrink when an artifact gains an arm.
# =============================================================================

Z1_SCHEMA = "z1_arm_list/1"

#: plan 2.3, the family alphas (O8). ABL is a removal family, alpha for removal only.
Z1_FAMILY_ALPHA = {"H-MECH": 0.025, "P-MECH": 0.015, "H-NOMECH": 0.005,
                   "P-NOMECH": 0.005, "ABL": 0.05}

#: The frames an arm may run on (plan 2.4 "identical rows"): the 11-fold pair-weighted
#: basis for D-1, the C program and the 4-fold-era arms (the retired 4-fold basis is not
#: reproduced), the six-fold frame for the D-2 tools_json arms. The 09-04 families keep
#: their original scopes on the 11-fold years. Pinned by test against the lab constants.
Z1_FRAMES = {
    "deb11": {"years": [2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024],
              "source": "efv_model.SCORED_YEARS"},
    "deb6": {"years": [2019, 2020, 2021, 2022, 2023, 2024],
             "source": "tools/efv_driver_lab.EXTRAS_YEARS"},
}

#: Scopes (row sets inside a frame). `debuted` is load_pool's pool; the others are the
#: 09-04 families' own populations, copied from their labs.
Z1_SCOPES = {
    "debuted": "matrix rows kind == 'debuted' with a censored target and a consensus FV "
               "(tools/efv_driver_lab.load_pool)",
    "readable": "the debuted pool restricted to rows with at least one MiLB season readable "
                "at the decision point (tools/efv_volume_driver_lab.build_pool readable_only)",
    "full_observable": "every matrix row (debuted and bust) restricted to the IL-observable "
                       "cohort (tools/efv_health_profile_lab.build_pool full_pool + "
                       "observable_mask)",
    "debuted_observable": "the debuted pool restricted to the IL-observable cohort "
                          "(tools/efv_health_profile_lab.build_pool + observable_mask)",
}

#: The one artifact read at a pinned commit: the health family's gated block exists only
#: at d500e8d1. fc24963d re-ran the lab --describe-only and the HEAD file no longer
#: carries the arms it adjudicated, but they were adjudicated and they count.
Z1_PINNED = {"xfv_health_profile_eval.json": "d500e8d1"}


def _col(kind: str, **kw) -> dict:
    d = {"kind": kind}
    d.update(kw)
    return d


def _vec(key: str) -> list:
    return [_col("vec", key=key)]


#: Mechanism components (plan 2.2), declared per column and frozen with the list. For
#: hitters the re-priced component is fielding (positional arms stay with it because item
#: 17's refutation record names them); for pitchers it is strikeout / walk / home-run skill
#: (runs allowed to FIP) and starter-versus-reliever career shape. A column carries a tag
#: only when the column MEASURES that component; a column that merely shares an input
#: with it (tool_gap averages six bat and glove tools) carries none.
_MECH_HIT = {"fielding", "position"}
_MECH_PIT = {"k_skill", "bb_skill", "hr_skill", "runs_allowed_to_fip", "sp_rp_shape"}

#: Tags for the bare _vec keys and named sources that occur in the arm sources.
_MECH_BY_VEC = {
    ("hit", "tool_field"): ["fielding"],
    ("hit", "pos_prem"): ["position"],
    ("pit", "pos_prem"): ["sp_rp_shape"],          # _pos_premium: starters over relievers
    ("pit", "tool_cmd"): ["bb_skill"],
    ("pit", "tool_sl"): ["k_skill"],
    ("pit", "tool_ch"): ["k_skill"],
    ("pit", "era_rel"): ["runs_allowed_to_fip"],
    ("pit", "starter_shape"): ["sp_rp_shape"],
    ("pit", "arsenal_depth"): ["sp_rp_shape"],
    ("pit", "relief_flag"): ["sp_rp_shape"],
    ("pit", "peak_bb_rel"): ["bb_skill"],
}
_MECH_BY_EXTRAS = {
    # plan 2.7 item 8b: on a FIP label, velocity and spin act through strikeouts
    ("pit", "sits_mid"): ["k_skill"], ("pit", "tops"): ["k_skill"],
    ("pit", "rpm_fb"): ["k_skill"],
}


def _mech_of(side: str, columns: list) -> list:
    tags = set()
    for c in columns:
        if c.get("mech"):
            tags.update(c["mech"])
        elif c["kind"] == "vec":
            tags.update(_MECH_BY_VEC.get((side, c["key"]), []))
        elif c["kind"] == "extras":
            tags.update(_MECH_BY_EXTRAS.get((side, c["key"]), []))
    return sorted(tags)


# ----------------------------------------------------------------- 4-fold-era tables
#: Every arm id each 4-fold-era artifact carries, with its column definition. The
#: definitions are the artifact's own words, and the citation says where they were read.
_FOURFOLD: dict[str, dict] = {
    "xfv_leanplus_eval.json": {
        "where": "results_additive (+ results_replacement, + regate_2026_07_15.results); "
                 "method.candidates names each as a key 'computed in efv_model._vec'",
        "arms": {
            "hit_prod_trend": ("hit", _vec("prod_trend")),
            "hit_fv_trend": ("hit", _vec("fv_trend")),
            "hit_ops_rel": ("hit", _vec("ops_rel")),
            "hit_pos_prem": ("hit", _vec("pos_prem")),
            "hit_il_stints_pre": ("hit", _vec("il_stints_pre")),
            "hit_n_sources": ("hit", _vec("n_sources")),
            "pit_prod_trend": ("pit", _vec("prod_trend")),
            "pit_fv_trend": ("pit", _vec("fv_trend")),
            "pit_il_stints_pre": ("pit", _vec("il_stints_pre")),
            "pit_n_sources": ("pit", _vec("n_sources")),
            "hit_ops_rel_for_obp_rel": ("hit", None),     # a swap, not an add
        },
    },
    "xfv_defense_tools_eval.json": {
        "where": "variants[].id; protocol.arms gives each definition "
                 "('field (tool_field)', 'dtool_proxy (0.7*field + 0.3*speed)', "
                 "'field_x_pos (field * pos_prem)', 'field_plus_interaction'); "
                 "protocol.ledger_position records tool_throw as registered and "
                 "not vectorized at the time",
        "arms": {
            "field": ("hit", _vec("tool_field")),
            "dtool_proxy": ("hit", [_col(
                "expr", name="dtool_proxy",
                expr="0.7*g(f,'tool_field') + 0.3*g(f,'tool_speed')", mech=["fielding"])]),
            "field_x_pos": ("hit", [_col(
                "expr", name="field_x_pos", expr="g(f,'tool_field') * g(f,'pos_prem')",
                mech=["fielding", "position"])]),
            "field_plus_interaction": ("hit", [_col("vec", key="tool_field"), _col(
                "expr", name="field_x_pos", expr="g(f,'tool_field') * g(f,'pos_prem')",
                mech=["fielding", "position"])]),
            # never measured (plan 2.3: "tool_throw alone (never measured; 717 of 845 now
            # covered)"). Encoded the way efv_model._vec encodes every non-lean tool grade
            # (raw grade, 45.0 when absent: efv_model.py _TOOL_IMPUTE comment, "Non-lean
            # tools (... field/throw) keep 45.0").
            "tool_throw (registered, unmeasured)": ("hit", [_col(
                "rawtool", key="tool_throw", impute_value=45.0, mech=["fielding"])]),
        },
    },
    "xfv_feature_arms_eval.json": {
        "where": "variants[].id; protocol.arms",
        "arms": {
            "hit_level_rank": ("hit", _vec("level_rank")),
            "hit_peak_obp_rel": ("hit", _vec("peak_obp_rel")),
            "hit_peak_ops_rel": ("hit", _vec("peak_ops_rel")),
            "hit_bb_rel": ("hit", _vec("bb_rel")),
            "pit_level_rank": ("pit", _vec("level_rank")),
            "pit_peak_bb_rel": ("pit", _vec("peak_bb_rel")),
        },
    },
    "xfv_relief_shape_eval.json": {
        "where": "gates RS-1..RS-3; definitions from tools/efv_relief_shape_lab.py ARMS "
                 "(g(f,'starter_shape'), g(f,'arsenal_depth'), g(f,'relief_flag'))",
        "arms": {
            "RS-1": ("pit", _vec("starter_shape")),
            "RS-2": ("pit", _vec("arsenal_depth")),
            "RS-3": ("pit", _vec("relief_flag")),
        },
    },
    "xfv_repeat_level_eval.json": {
        "where": "results.hit / results.pit (E1 seasons_at_level, efv_model._vec key)",
        "arms": {
            "hit": ("hit", _vec("seasons_at_level")),
            "pit": ("pit", _vec("seasons_at_level")),
        },
    },
    "xfv_weight_recal_eval.json": {
        "where": "sides.<side>.feature_addbacks; definitions from the producing tool "
                 "tools/efv_weight_recal_lab.py _added_features (deleted at 8fecb2f5, "
                 "read at 8fecb2f5^)",
        "arms": {
            "hit.iso_rel": ("hit", _vec("iso_rel")),
            "hit.peak_iso_rel": ("hit", _vec("peak_iso_rel")),
            "hit.kbb_rel": ("hit", [_col("expr", name="kbb_rel",
                                         expr="g(f,'bb_rel') - g(f,'k_rel')")]),
            "pit.level_rank": ("pit", _vec("level_rank")),
            "pit.kbb_rel": ("pit", [_col("expr", name="kbb_rel",
                                         expr="g(f,'k_rel') - g(f,'bb_rel')",
                                         mech=["k_skill", "bb_skill"])]),
            "pit.peak_bb_rel": ("pit", _vec("peak_bb_rel")),
        },
    },
    "xfv_wrc_eval.json": {
        "where": "arms A1_replace / A2_add / SB_add and A4.arm; definitions from "
                 "tools/efv_wrc_lab.py (build_join + inject zero; clause_m + "
                 "_composite_feature for A4)",
        "arms": {
            "A1_replace": ("hit", None),                   # a swap, not an add
            "A2_add": ("hit", [_col("wrc", key="wrc_rel")]),
            "SB_add": ("hit", [_col("wrc", key="hit_sb_rel")]),
            "A4_composite": ("hit", [_col("wrc", key="wrc_comp")]),
        },
    },
    "docs/efv-sb-athleticism-2026-08-05/results.json": {
        "where": "runs (the _CTRL runs are the arms' own permuted controls, not arms); "
                 "definitions in docs/efv-sb-athleticism-2026-08-05/run_lab.py augment()",
        "arms": {
            # sb_rate_rel recomputed through efv_dataset._milb_features, the production
            # path that wrote the matrix's stored milb block: the same definition as C1a.
            "b4_sb": ("hit", [_col("milb", key="sb_rate_rel")]),
            "b4_blend50": ("hit", [_col("sbath", name="spd_sb_50")]),
            "b4_blend70": ("hit", [_col("sbath", name="spd_sb_70")]),
            "b5_athl3": ("hit", [_col("sbath", name="athl3", mech=["fielding"])]),
            "b5_sf": ("hit", [_col("sbath", name="athl_sf", mech=["fielding"])]),
            "b5_st": ("hit", [_col("sbath", name="athl_st", mech=["fielding"])]),
        },
    },
    "xfv_physical_eval.json": {
        "where": "variants lean_physical (efv_ml_lab extra_join=physical over "
                 "data/xfv_extra_physical.json, every key with a non-null value)",
        "arms": {
            "lean_physical": ("hit", [_col("xjoin", join="physical",
                                           mech=["position"])]),
        },
    },
    "prospect_def_value_eval.json": {
        "where": "xfv_swap_gate lean_plus_def_value / full_plus_def_value (xfv_ml_lab "
                 "extra_join=defense over data/xfv_extra_defense.json)",
        "arms": {
            "lean_plus_def_value": ("hit", [_col("xjoin", join="defense",
                                                 mech=["fielding", "position"])]),
            "full_plus_def_value": ("hit", [_col("xjoin", join="defense",
                                                 mech=["fielding", "position"])]),
        },
    },
    "xfv_age_feature_eval.json": {
        "where": "variants hit_age / hit_age_only / pit_age / pit_age_only (age, with and "
                 "without the age_missing indicator); age SHIPPED and is a served feature",
        "arms": {
            "hit_age": ("hit", _vec("age") + _vec("age_missing")),
            "hit_age_only": ("hit", _vec("age")),
            "pit_age": ("pit", _vec("age") + _vec("age_missing")),
            "pit_age_only": ("pit", _vec("age")),
        },
    },
}


#: How each 4-fold-era producer read a _vec key, which decides one thing only: the sign of
#: a zero. efv_lab_runner's g() is float(f.get(k, 0.0) or 0.0), so a -0.0 reads 0.0
#: ("lab_g"); efv_weight_recal_lab's f.get(k, 0.0) and efv_model's own X build
#: (feats.get(k, 0.0), the E1 flag path) keep -0.0 ("raw"), as D-1's getter does. The
#: values are equal either way; the port reproduces the producer's bits, and an arm with a
#: lab_runner origin reads lab_g.
_FOURFOLD_READ = {
    "xfv_leanplus_eval.json": "lab_g", "xfv_defense_tools_eval.json": "lab_g",
    "xfv_feature_arms_eval.json": "lab_g", "xfv_relief_shape_eval.json": "lab_g",
    "xfv_repeat_level_eval.json": "raw", "xfv_weight_recal_eval.json": "raw",
}


def _fourfold_ids(name: str, doc: dict) -> list[str]:
    """The arm ids an artifact actually carries, read from the artifact."""
    if name == "xfv_leanplus_eval.json":
        ids = list(doc.get("results_additive") or {}) + list(doc.get("results_replacement") or {})
        ids += list(((doc.get("regate_2026_07_15") or {}).get("results")) or {})
        return sorted(set(ids))
    if name in ("xfv_defense_tools_eval.json", "xfv_feature_arms_eval.json",
                "xfv_physical_eval.json", "xfv_age_feature_eval.json"):
        ids = [v["id"] for v in doc.get("variants") or [] if not str(v["id"]).startswith("BASE")]
        if name == "xfv_defense_tools_eval.json" and "tool_throw" in str(
                (doc.get("protocol") or {}).get("ledger_position")):
            ids.append("tool_throw (registered, unmeasured)")
        return ids
    if name == "xfv_relief_shape_eval.json":
        return sorted(doc.get("gates") or {})
    if name == "xfv_repeat_level_eval.json":
        return sorted(doc.get("results") or {})
    if name == "xfv_weight_recal_eval.json":
        return [f"{s}.{k}" for s, blk in sorted((doc.get("sides") or {}).items())
                for k in (blk.get("feature_addbacks") or {})]
    if name == "xfv_wrc_eval.json":
        ids = sorted(doc.get("arms") or {})
        if (doc.get("A4") or {}).get("arm"):
            ids.append("A4_composite")
        return ids
    if name == "docs/efv-sb-athleticism-2026-08-05/results.json":
        return [k for k in (doc.get("runs") or {})
                if not k.endswith("_CTRL") and k not in ("baseline", "stock_baseline")]
    if name == "prospect_def_value_eval.json":
        return [k for k in (doc.get("xfv_swap_gate") or {}) if k.endswith("plus_def_value")]
    raise KeyError(name)


#: Lanes read and set aside whole, each with the rule that sets it aside. They are listed
#: in the arm list so a reader can see they were considered, not missed.
Z1_EXCLUDED_LANES = (
    ("xfv_driver_gated_pairs.json", "plan 2.7: C3 threshold pairs, killed for a "
     "label-independent reason (the live blow-up clause)"),
    ("xfv_driver_pos_census.json", "plan 2.7: C1b observed positions, no add arm"),
    ("xfv_driver_lambda_sweep.json", "a sweep over a continuous knob (C5), not an add column"),
    ("xfv_driver_elite_band.json", "plan 2.7: C4a elite lambda, a sweep, not an add column"),
    ("xfv_pace_entry_eval.json", "plan 2.7: pace-from-entry, NO"),
    ("xfv_level_blend_arms_eval.json", "plan 0.3 X16: the B3 level blend is not in Z1"),
    ("xfv_pitcher_stuff_eval.json", "plan 2.7 item 8a: pitcher stuff opens by its own "
     "clock in its own registration (Z1c), not Z1"),
    ("xfv_model_class_sweep_eval.json", "model class: its own registration (Z1b), not an "
     "add column"),
    ("xfv_level_rank_fringe_eval.json", "level_rank shipped for hitters: a served feature, "
     "read in ABL"),
    ("xfv_ops_rel_fringe_eval.json", "ops_rel shipped for hitters: a served feature, read "
     "in ABL"),
    ("xfv_driver_admission.json", "eFV v2 admission rule on the list-vintage frame: not "
     "gated on the flagship ridge"),
    ("efv_v2_assembly.json", "eFV v2 assembly admission on the list-vintage frame: not "
     "gated on the flagship ridge"),
    ("xfv_screen_wave1.json", "eFV v2 screening lab: not gated on the flagship ridge"),
    ("xfv_improve_sweep_eval.json", "calibration, recency, IPCW, stacking and hurdle "
     "estimators: no add column"),
    ("xfv_cohort_lambda_eval.json", "a lambda selection, not an add column"),
    ("xfv_cohort_lambda_hier_eval.json", "a lambda selection, not an add column"),
    ("xfv_disagreements_eval.json", "lambda and shrink interventions, not an add column"),
    ("xfv_peak_war_eval.json", "a target change, not an add column"),
    ("xfv_level_weight_eval.json", "plan 2.7: the 09-04 level weights are a descriptive "
     "order, re-read as a receipt"),
)


def _git_root() -> Path:
    return ROOT.parent


def _read_artifact(name: str):
    """(doc, ref, sha256 of the bytes read). `name` is relative to data/ unless it starts
    with docs/. A pinned artifact is read from git at its pin, never from the tree."""
    rel = name if name.startswith("docs/") else f"data/{name}"
    ref = Z1_PINNED.get(name)
    if ref:
        import subprocess
        raw = subprocess.check_output(
            ["git", "show", f"{ref}:{ROOT.name}/{rel}"], cwd=str(_git_root()))
    else:
        raw = (ROOT / rel).read_bytes()
        ref = "HEAD"
    import hashlib
    return json.loads(raw.decode("utf-8")), ref, hashlib.sha256(raw).hexdigest()


def _cand(origin: dict, side: str, columns, frame="deb11", scope="debuted",
          drop=(), impute="zero", nomech_by=None, exclude=None) -> dict:
    import copy
    return {"origin": origin, "side": side, "frame": frame, "scope": scope,
            "columns": copy.deepcopy(columns), "drop": list(drop), "impute": impute,
            "nomech_by": nomech_by, "exclude": exclude}


def _z1_candidates(served: dict) -> tuple[list, list]:
    """Every candidate arm from every source, before dedupe. Returns (cands, sources)."""
    cands, sources = [], []

    def _src(name, doc_ref_sha, n):
        sources.append({"artifact": name, "ref": doc_ref_sha[1],
                        "sha256": doc_ref_sha[2], "n_candidates": n})

    # ---- the 4-fold era (frame deb11; the retired 4-fold basis is not reproduced) ----
    for name, spec in _FOURFOLD.items():
        got = _read_artifact(name)
        ids = _fourfold_ids(name, got[0])
        for aid in ids:
            if aid not in spec["arms"]:
                raise KeyError(f"{name}: arm {aid!r} has no column definition in _FOURFOLD")
            side, cols = spec["arms"][aid]
            origin = {"artifact": name, "ref": got[1], "arm": aid, "era": "4fold",
                      "read": _FOURFOLD_READ.get(name, "raw"),
                      "definition_read_from": spec["where"]}
            if cols is None:
                cands.append(_cand(origin, side, [], exclude={
                    "rule": "R-SWAP", "reason": "a replacement of a served feature, not "
                                                "an add column"}))
                continue
            port = ("never_measured" if any(c["kind"] == "rawtool" for c in cols)
                    else "ported_4fold")
            origin["port"] = port
            cands.append(_cand(origin, side, cols))
        _src(name, got, len(ids))

    # ---- the 11-fold driver lab (D-1, D-2, the C program) ----
    got = _read_artifact("xfv_driver_freekeys.json")
    for k in sorted(got[0].get("arms") or {}):
        side, key = k.split(".", 1)
        cands.append(_cand({"artifact": "xfv_driver_freekeys.json", "ref": got[1], "arm": k,
                            "era": "11fold", "port": "reused_builder"}, side, _vec(key)))
    for k, why in sorted((got[0].get("skipped") or {}).items()):
        side, key = k.split(".", 1)
        cands.append(_cand({"artifact": "xfv_driver_freekeys.json", "ref": got[1], "arm": k,
                            "era": "11fold"}, side, _vec(key), exclude={
            "rule": "R-DEGENERATE", "reason": f"not read in its original lane: {why}"}))
    _src("xfv_driver_freekeys.json", got,
         len(got[0].get("arms") or {}) + len(got[0].get("skipped") or {}))

    got = _read_artifact("xfv_driver_extras.json")
    for k in sorted(got[0].get("arms") or {}):
        side, key = k.split(".", 1)
        cands.append(_cand({"artifact": "xfv_driver_extras.json", "ref": got[1], "arm": k,
                            "era": "6fold", "port": "reused_builder"}, side,
                           [_col("extras", key=key)], frame="deb6"))
    _src("xfv_driver_extras.json", got, len(got[0].get("arms") or {}))

    got = _read_artifact("xfv_driver_sb_rate.json")
    cands.append(_cand({"artifact": "xfv_driver_sb_rate.json", "ref": got[1],
                        "arm": got[0].get("tag"), "era": "11fold", "port": "reused_builder"},
                       "hit", [_col("milb", key="sb_rate_rel")]))
    _src("xfv_driver_sb_rate.json", got, 1)

    got = _read_artifact("xfv_driver_wrc.json")
    cands.append(_cand({"artifact": "xfv_driver_wrc.json", "ref": got[1],
                        "arm": got[0].get("tag"), "era": "11fold", "port": "reused_builder"},
                       "hit", [_col("wrc", key="wrc_rel")]))
    _src("xfv_driver_wrc.json", got, 1)

    got = _read_artifact("xfv_driver_handedness.json")
    hand = {"a_is_lhp_pit": ("pit", [_col("hand", key="is_lhp")]),
            "b_bats_side_hit": ("hit", [_col("hand", key="bats_l"),
                                        _col("hand", key="bats_s")])}
    for k in sorted(got[0].get("arms") or {}):
        side, cols = hand[k]
        cands.append(_cand({"artifact": "xfv_driver_handedness.json", "ref": got[1],
                            "arm": k, "era": "11fold", "port": "reused_builder"}, side, cols,
                           impute="mean"))
    _src("xfv_driver_handedness.json", got, len(got[0].get("arms") or {}))

    # ---- the 2026-09-04 families, in their original scopes, NOMECH by O8 ----
    got = _read_artifact("xfv_volume_driver_eval.json")
    n = 0
    for side in ("hit", "pit"):
        for scope_key, scope in (("full_pool", "debuted"), ("readable_only", "readable")):
            for r in got[0]["sides"][side][scope_key]["gated"]["results"]:
                n += 1
                excl = None
                if "holm_p" not in r:
                    excl = {"rule": "R-DEGENERATE", "reason": "outside its original Holm "
                            f"family: {r.get('skipped') or 'no p-value'}"}
                cands.append(_cand({"artifact": "xfv_volume_driver_eval.json", "ref": got[1],
                                    "arm": f"{side}.{scope_key}.{r['name']}", "era": "0904",
                                    "port": "reused_builder"}, side,
                                   [_col("vol", name=r["name"])], scope=scope,
                                   impute="none", nomech_by="O8", exclude=excl))
    _src("xfv_volume_driver_eval.json", got, n)

    got = _read_artifact("xfv_age_interaction_eval.json")
    n = 0
    for side in ("hit", "pit"):
        for r in got[0]["sides"][side]["results"]:
            n += 1
            drop = ["age_rel_level"] if r.get("drops_flat_age") else []
            excl = None if "holm_p" in r else {"rule": "R-DEGENERATE",
                                               "reason": "outside its original Holm family"}
            cands.append(_cand({"artifact": "xfv_age_interaction_eval.json", "ref": got[1],
                                "arm": f"{side}.{r['name']}", "era": "0904",
                                "port": "reused_builder"}, side,
                               [_col("agex", name=r["name"],
                                     n_columns=int(r.get("n_extra_cols") or 1))],
                               drop=drop, impute="none", nomech_by="O8", exclude=excl))
    _src("xfv_age_interaction_eval.json", got, n)

    got = _read_artifact("xfv_health_profile_eval.json")
    n = 0
    for side in ("hit", "pit"):
        for pool_key, scope in (("full_pool", "full_observable"),
                                ("debuted_only", "debuted_observable")):
            for r in got[0]["sides"][side][pool_key]["gated"]["results"]:
                n += 1
                excl = None
                if "holm_p" not in r:
                    excl = {"rule": "R-DEGENERATE", "reason": "outside its original Holm "
                            f"family: {r.get('skipped') or 'no p-value'}"}
                cands.append(_cand({"artifact": "xfv_health_profile_eval.json",
                                    "ref": got[1], "arm": f"{side}.{pool_key}.{r['name']}",
                                    "era": "0904", "port": "reused_builder"}, side,
                                   [_col("health", name=r["name"])], scope=scope,
                                   impute="none", nomech_by="O8", exclude=excl))
    _src("xfv_health_profile_eval.json", got, n)

    # ---- the extra-join keys, resolved the way efv_ml_lab._load_extra resolves them
    #      (the union of every key carrying a non-null value), so the list freezes the
    #      exact columns and the run refuses if the join file now yields others ----
    for c in cands:
        for col in c["columns"]:
            if col["kind"] == "xjoin" and "keys" not in col:
                raw = json.loads((DATA / f"xfv_extra_{col['join']}.json")
                                 .read_text(encoding="utf-8"))
                col["keys"] = sorted({k for r in raw for k, v in r.items()
                                      if k not in ("mlbam_id", "player_key", "name")
                                      and v is not None})

    # ---- the mechanical exclusions that apply across sources ----
    for c in cands:
        if c["exclude"]:
            continue
        keys = [col["key"] for col in c["columns"] if col["kind"] == "vec"]
        if any(k in served[c["side"]] for k in keys):
            c["exclude"] = {"rule": "R-SERVED", "reason": "carries a served feature; the "
                            "served feature is read as a removal arm in ABL"}
        elif "il_stints_pre" in keys:
            c["exclude"] = {"rule": "R-27", "reason": "plan 2.7: il_stints_pre, killed for "
                            "a label-independent reason"}
    return cands, sources


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _arm_slug(c: dict) -> str:
    parts = []
    for col in c["columns"]:
        parts.append(col.get("key") or col.get("name") or col.get("join"))
    s = "+".join(parts)
    if c["drop"]:
        s += "-drop-" + "+".join(c["drop"])
    if c["scope"] != "debuted":
        s += f"@{c['scope']}"
    if c["frame"] != "deb11":
        s += f"@{c['frame']}"
    return s


def derive_z1_arm_list() -> dict:
    """The frozen Z1 arm list. Reads committed artifacts, scores nothing."""
    sys.path.insert(0, str(ROOT))
    import efv_model as E
    served = {s: list(E._feature_spec(s)[0]) for s in ("hit", "pit")}
    cands, sources = _z1_candidates(served)

    # dedupe by (side, frame, scope, column definition, drop): a column read in two lanes
    # on the frame Z1 assigns to both is ONE arm with two origins.
    def _defn(col):
        return {k: v for k, v in col.items() if k not in ("mech", "read")}

    arms: dict[str, dict] = {}
    excluded = []
    for c in cands:
        if c["exclude"]:
            excluded.append({"origin": c["origin"], "side": c["side"],
                             "columns": c["columns"], **c["exclude"]})
            continue
        key = _canon([c["side"], c["frame"], c["scope"],
                      [_defn(x) for x in c["columns"]], c["drop"]])
        if key in arms:
            arms[key]["origins"].append(c["origin"])
            continue
        mech = _mech_of(c["side"], c["columns"])
        if c["nomech_by"]:
            fam = ("H" if c["side"] == "hit" else "P") + "-NOMECH"
        elif c["side"] == "hit":
            fam = "H-MECH" if set(mech) & _MECH_HIT else "H-NOMECH"
        else:
            fam = "P-MECH" if set(mech) & _MECH_PIT else "P-NOMECH"
        arms[key] = {"family": fam, "side": c["side"], "frame": c["frame"],
                     "scope": c["scope"], "years": Z1_FRAMES[c["frame"]]["years"],
                     "columns": c["columns"], "drop": c["drop"], "impute": c["impute"],
                     "mechanism": mech,
                     "family_rule": ("O8: the 09-04 families run in the no-mechanism "
                                     "families in their original scopes" if c["nomech_by"]
                                     else "plan 2.2 mechanism tags"),
                     "origins": [c["origin"]]}

    out_arms = []
    for a in arms.values():
        reads = {o.get("read", "raw") for o in a["origins"]}
        for col in a["columns"]:
            if col["kind"] == "vec":
                col["read"] = "lab_g" if "lab_g" in reads else "raw"
        a["port"] = sorted({o.get("port", "reused_builder") for o in a["origins"]})
        a["id"] = f"{a['family']}.{a['side']}.{_arm_slug(a)}"
        out_arms.append(a)
    # ABL: every served feature dropped, fv per side as the liveness control (plan 2.3).
    for side in ("hit", "pit"):
        for k in served[side]:
            out_arms.append({
                "id": f"ABL.{side}.drop-{k}", "family": "ABL", "side": side,
                "frame": "deb11", "scope": "debuted", "years": Z1_FRAMES["deb11"]["years"],
                "columns": [], "drop": [k], "impute": "none", "mechanism": [],
                "family_rule": "plan 2.3 ABL: a drop test on a served feature",
                "liveness_control": k == "fv",
                "origins": [{"artifact": "efv_model._feature_spec", "ref": "HEAD",
                             "arm": f"{side}.{k}", "era": "served"}],
                "port": ["served_feature"]})
    order = {f: i for i, f in enumerate(Z1_FAMILY_ALPHA)}
    out_arms.sort(key=lambda a: (order[a["family"]], a["side"], a["id"]))
    ids = [a["id"] for a in out_arms]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate arm ids in the derived list")

    fams = {}
    for f, alpha in Z1_FAMILY_ALPHA.items():
        n = sum(1 for a in out_arms if a["family"] == f)
        n_ctrl = sum(1 for a in out_arms if a["family"] == f and a.get("liveness_control"))
        fams[f] = {"alpha": alpha, "arms": n, "liveness_controls": n_ctrl,
                   "holm_legs": 2 * (n - n_ctrl),
                   "legs_rule": "both legs of every arm (rho and contributor AUC) count in m; "
                                "the fv liveness controls are run first and sit outside m"}
    return {
        "schema": Z1_SCHEMA,
        "produced_by": "tools/efv_arm_ledger.py --z1-arm-list",
        "plan": "docs/master-plan-2026-09-11-war-epoch-drivers-betting.md section 2",
        "reads_only": "committed artifacts; no arm, floor or margin is read on any label",
        "frames": Z1_FRAMES, "scopes": Z1_SCOPES, "families": fams,
        "n_arms": len(out_arms),
        "n_reads": len(out_arms),
        "rules": {
            "dedupe": "one arm per (side, frame, scope, column definition, dropped columns); "
                      "a column read in several lanes carries every origin",
            "frame": "4-fold-era arms run on the 11-fold basis (the retired 4-fold basis is "
                     "not reproduced, plan 2.4); D-2 on the six-fold frame; the 09-04 "
                     "families on their original scopes",
            "mechanism": "plan 2.2: a hitter column tagged fielding or position goes to "
                         "H-MECH; a pitcher column tagged k/bb/hr skill, runs allowed to FIP "
                         "or starter/reliever shape goes to P-MECH; the 09-04 families go to "
                         "the no-mechanism families by O8",
            "posture": "where an artifact read one column under two imputation postures "
                       "(xfv_weight_recal_eval.json mean and zero), the arm carries the "
                       "shipped-convention zero posture that every other lane reading the "
                       "same column used; the train-fold mean posture is fold-dependent "
                       "and is not a column",
            "exclusions": "R-SERVED (carries a served feature: ABL reads it), R-SWAP (a "
                          "replacement, not an add), R-27 (plan 2.7 NO), R-DEGENERATE "
                          "(outside its original Holm family: constant on its scope or "
                          "degenerate)",
        },
        "arms": out_arms,
        "excluded_arms": excluded,
        "excluded_lanes": [{"artifact": a, "reason": r} for a, r in Z1_EXCLUDED_LANES],
        "sources": sources,
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--z1-arm-list" in argv:
        i = argv.index("--z1-arm-list")
        dest = Path(argv[i + 1])
        lst = derive_z1_arm_list()
        dest.parent.mkdir(parents=True, exist_ok=True)
        # LF bytes, written as bytes: the registration pins this file by sha256, and a
        # platform newline translation would change the bytes it pins (.gitattributes
        # keeps git from converting them on checkout).
        dest.write_bytes((json.dumps(lst, indent=1) + "\n").encode("utf-8"))
        for f, v in lst["families"].items():
            print(f"  {f:9s} alpha {v['alpha']:<6} arms {v['arms']:4d}  holm legs "
                  f"{v['holm_legs']}")
        print(f"arms {lst['n_arms']}  excluded arms {len(lst['excluded_arms'])}  "
              f"excluded lanes {len(lst['excluded_lanes'])}")
        print(f"wrote {dest}")
        return 0
    led = collect()
    write = "--dry-run" not in argv
    if write:
        OUT.write_text(json.dumps(led, indent=1) + "\n", encoding="utf-8")
    print(f"arms: {led['n_arms']} across {len(led['by_lane'])} lanes")
    for lane, n in led["by_lane"].items():
        print(f"  {n:4d}  {lane}")
    print(f"verdicts: {led['by_verdict']}")
    print(f"cleared own floor: {led['n_cleared_own_floor']} of "
          f"{led['n_scoreable_against_a_floor']} scoreable"
          + (f"  {led['cleared_own_floor']}" if led["cleared_own_floor"] else ""))
    print(f"sweeps (not arms): {[(s['lane'], s['settings']) for s in led['sweeps']]}")
    print(f"validity probes (not arms): {led['n_probes']}")
    if led["sources_missing"]:
        print("MISSING SOURCES (the count is a lower bound):")
        for m in led["sources_missing"]:
            print(f"  {m['artifact']}: {m['why']}")
    if led.get("sources_pending"):
        print("PENDING SOURCES (registered; the producer has not run):")
        for m in led["sources_pending"]:
            print(f"  {m['artifact']}: {m['lane']}")
    print()
    print(led["reading"])
    if write:
        print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
