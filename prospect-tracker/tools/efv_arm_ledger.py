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
)

#: Development probes that are NOT feature arms: validity reads (a label-balance
#: screen, a leak regression). Counted and listed apart, like sweeps, and never summed
#: into the arm count, because they test the frame rather than a driver.
PROBES: tuple[tuple[str, str, str], ...] = (
    ("efv_identity_balance.json", "probes", "identity balance probes (DS-03)"),
    ("efv_v2_assembly.json", "probes", "combiner rule reads (DS-08)"),
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
    rows, missing = [], []
    for name, key, label in SOURCES:
        doc, why = _load(name)
        if doc is None:
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


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
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
    print()
    print(led["reading"])
    if write:
        print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
