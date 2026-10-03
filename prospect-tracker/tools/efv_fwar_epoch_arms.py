# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Build the fWAR label epoch's clause (i) arm matrices (runbook step F).

docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md clause (i) and part 6; the arm set fixed by
owner answer EPOCH-Q3 ("R, A1 and A2, each shipping only if its own clauses pass, no L1
flooring"). Per side, from ONE code path with named flag overrides:

    E0     the incumbent: eWAR v2 label (career_war.seasons_ewar_v2, the series the step C
           rebase keeps, gate note 2; never the live provider), RESOLVED_THROUGH 2025,
           every candidate flag off
    Estar  the full candidate AS BUILT: published fWAR (career_war.seasons after step C),
           RESOLVED_THROUGH as the module reads it at step F (2026 under EPOCH_RUN's RT
           commit; the builder refuses any other value), Arm R, A1 and A2 all ON
    F1..F5 one LEAVE-ONE-OUT arm per admitted matrix factor: Estar with exactly that
           factor reverted to its E0 value (F1 the basis, F2 RESOLVED_THROUGH, F3 Arm R,
           F4 A1, F5 A2)

Seven matrices per side, fourteen in all. F6 (F-DEF) is a BUNDLE arm inside step M, not a
matrix (gate part 5 table): this builder does not build it.

WHERE IT WRITES. Only under data/_labs/fwar_epoch_arms/, which ships in neither deploy
consumer (test_publish_manifest.py pins data/_labs/ out of both). Never the served
matrices (efv_dataset.matrix_path), never prospects.db (it calls efv_dataset.build_matrix,
a read, and never efv_dataset.run, the function that writes the canonical path), never a
gate document. A path guard refuses anything else.

WHAT A2 DOES NOT CHANGE. The A2 flag (efv_model.NEUTRAL_MILB_IMPUTE) changes the imputation
applied INSIDE a ridge fit, not the matrix, so F5's rows are identical to Estar's by
construction. The arm file is still written and the flag state recorded in the manifest,
so the epoch lab reads one path per arm and applies A2 at fit time from the recorded
flags (tools/efv_fwar_label_epoch_lab.py).

A FAILED ARM (clause (i) point 5). `--omit F3 --omit-reason "..."` leaves that factor out:
no leave-one-out arm is built for it, Estar carries every OTHER admitted factor (the
omitted one sits at its E0 value), and the manifest records the omission with its reason
so the lab reports that factor's attribution as UNAVAILABLE and never infers it. EPOCH_RUN
omits F3 when the BUST2 union invariant fails at step F.

NO L1 FLOORING. Rows are written exactly as build_matrix returns them; a negative
six-season label stays negative on every arm (part 6: the L1 flooring may not ride).

Importing this module does nothing. Run (EPOCH_RUN step F, after step C, after
test_bust2_union_invariant.py's live part):
    python tools/efv_fwar_epoch_arms.py --side both --arm all
    python tools/efv_fwar_epoch_arms.py --side both --arm all --omit F3 --omit-reason "BUST2 union invariant failed at step F: <n> rows"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import efv_dataset as ed          # noqa: E402
import efv_model as em            # noqa: E402

SCHEMA = "fwar_epoch_arms/1"
SEED = 20260807                     # the standard's seed convention, recorded for the lab
GATE = "docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md"

#: The only directory this builder writes. One level below data/ (data/_labs/ ships in
#: neither consumer) and a named subdirectory of it, so no file lands at data/ depth one.
LABS_ROOT = ROOT / "data" / "_labs"
OUT_DIR = LABS_ROOT / "fwar_epoch_arms"

#: E0's resolution clock (gate clause (i): "RESOLVED_THROUGH 2025") and the value the
#: module must read at step F for Estar (owner decision O2: the bundle advances it to
#: 2026). Estar never sets the constant; it uses the module's and refuses any other value.
E0_RESOLVED_THROUGH = 2025
ESTAR_RESOLVED_THROUGH = 2026

#: The label series each basis reads off a career_war payload (efv_dataset.LABEL_SEASONS_KEY).
INCUMBENT_LABEL_KEY = "seasons_ewar_v2"    # eWAR v2, kept by the step C rebase (note 2)
CANDIDATE_LABEL_KEY = "seasons"            # what the table serves after step C: fwar

#: factor id -> (name, module, attribute, E0 value, Estar value). Estar's RESOLVED_THROUGH
#: is None on purpose: "as the module reads it" (asserted equal to ESTAR_RESOLVED_THROUGH).
FACTORS = {
    "F1": ("basis_published_fwar", "efv_dataset", "LABEL_SEASONS_KEY",
           INCUMBENT_LABEL_KEY, CANDIDATE_LABEL_KEY),
    "F2": ("resolved_through_2026", "efv_dataset", "RESOLVED_THROUGH",
           E0_RESOLVED_THROUGH, None),
    "F3": ("arm_r_never_resolution", "efv_dataset", "NEVER_RESOLUTION_ARM_R", False, True),
    "F4": ("a1_service_aligned_window", "efv_dataset", "SERVICE_ALIGNED_WINDOW", False, True),
    "F5": ("a2_neutral_milb_impute", "efv_model", "NEUTRAL_MILB_IMPUTE", False, True),
}
#: The factors an owner decision ships regardless (gate part 0; no ship clause) and the
#: candidates that ship only on their own clauses (part 6).
OWNER_DECISION_FACTORS = ("F1", "F2")
CANDIDATE_FACTORS = ("F3", "F4", "F5")

ARMS = ("E0", "Estar", *FACTORS)
SIDES = ("hit", "pit")

_MODULES = {"efv_dataset": ed, "efv_model": em}


class ArmRefused(RuntimeError):
    """A build this tool will not do: a path outside its directory, a RESOLVED_THROUGH the
    gate does not expect, an unknown arm or factor, an omission without a reason."""


# ------------------------------------------------------------------ the arm table
def estar_value(fid: str) -> object:
    """The value factor `fid` takes on Estar. F2 is the module's constant as read now."""
    name, mod, attr, e0, es = FACTORS[fid]
    if es is None:
        return getattr(_MODULES[mod], attr)
    return es


def arm_factor_values(arm: str, omitted: tuple[str, ...] = ()) -> dict[str, object]:
    """{factor id: value} for one arm. E0 is every factor at its E0 value; Estar every
    admitted factor at its Estar value; F<k> is Estar with factor k at its E0 value. An
    omitted factor sits at its E0 value on EVERY arm (it is out of the epoch's candidate
    set), and its own leave-one-out arm does not exist."""
    if arm not in ARMS:
        raise ArmRefused(f"unknown arm {arm!r}; the arms are {ARMS}")
    for o in omitted:
        if o not in FACTORS:
            raise ArmRefused(f"cannot omit {o!r}: not a factor ({tuple(FACTORS)})")
    if arm in omitted:
        raise ArmRefused(f"arm {arm} is omitted (a FAILED ARM); it is not built")
    out = {}
    for fid in FACTORS:
        e0 = FACTORS[fid][3]
        if arm == "E0" or fid in omitted or fid == arm:
            out[fid] = e0
        else:
            out[fid] = estar_value(fid)
    return out


def factor_reverted(arm: str) -> str | None:
    """The one factor an F-arm reverts, or None for E0 and Estar."""
    return arm if arm in FACTORS else None


def flags_by_attribute(values: dict[str, object]) -> dict[str, object]:
    """{module.attribute: value}, the form the manifest records and the lab reads."""
    return {f"{FACTORS[f][1]}.{FACTORS[f][2]}": v for f, v in values.items()}


def label_provider(values: dict[str, object]) -> str:
    """What the arm's label is read from, named for the manifest."""
    if values["F1"] == INCUMBENT_LABEL_KEY:
        return f"ewar_v2 (career_war.{INCUMBENT_LABEL_KEY}, kept by the step C rebase)"
    import war_source
    return f"{war_source.DEFAULT_PROVIDER} (career_war.{CANDIDATE_LABEL_KEY}, as the table serves it)"


# ------------------------------------------------------------------ the path guard
def arm_path(side: str, arm: str, out_dir: Path | None = None) -> Path:
    """data/_labs/fwar_epoch_arms/xfv_<side>_matrix__<arm>.json, guarded."""
    canon = ed.matrix_path(side)
    p = (OUT_DIR if out_dir is None else out_dir) / f"{canon.stem}__{arm}{canon.suffix}"
    assert_lab_path(p, side)
    return p


def manifest_path(side: str, out_dir: Path | None = None) -> Path:
    p = (OUT_DIR if out_dir is None else out_dir) / f"manifest_{side}.json"
    assert_lab_path(p, side)
    return p


def assert_lab_path(p: Path, side: str | None = None) -> Path:
    """Refuse any write that is not strictly inside OUT_DIR, which must itself sit inside
    LABS_ROOT (data/_labs/); refuse the served matrix paths and prospects.db by name."""
    rp = Path(p).resolve()
    out = Path(OUT_DIR).resolve()
    labs = Path(LABS_ROOT).resolve()
    if out == labs or labs not in out.parents:
        raise ArmRefused(f"OUT_DIR {out} is not a subdirectory of the labs root {labs}")
    if out not in rp.parents:
        raise ArmRefused(f"refusing to write outside {out}: {rp}")
    served = {ed.matrix_path(s).resolve() for s in SIDES} | {
        ed.live_matrix_path(s).resolve() for s in SIDES}
    if rp in served or rp.name in {s.name for s in served}:
        raise ArmRefused(f"refusing to write a served matrix name: {rp}")
    if rp.name.startswith("prospects.db"):
        raise ArmRefused(f"refusing to touch the database: {rp}")
    return rp


# ------------------------------------------------------------------ one arm
def build_arm(side: str, arm: str, omitted: tuple[str, ...] = ()):
    """(rows, acct, values) for one arm. Sets every factor's attribute on its module for
    the duration of ONE build_matrix call and restores all of them, on failure too."""
    values = arm_factor_values(arm, omitted)
    if arm != "E0" and "F2" not in omitted and arm != "F2":
        rt = values["F2"]
        if rt != ESTAR_RESOLVED_THROUGH:
            raise ArmRefused(
                f"efv_dataset.RESOLVED_THROUGH reads {rt}; Estar expects "
                f"{ESTAR_RESOLVED_THROUGH} (EPOCH_RUN's RT commit, owner decision O2). "
                f"The builder never sets it for Estar; land the RT commit first")
    saved = {}
    try:
        for fid, v in values.items():
            _n, mod, attr, _e0, _es = FACTORS[fid]
            saved[(mod, attr)] = getattr(_MODULES[mod], attr)
            setattr(_MODULES[mod], attr, v)
        rows, acct = ed.build_matrix(side)
    finally:
        for (mod, attr), v in saved.items():
            setattr(_MODULES[mod], attr, v)
    return rows, acct, values


def _sha256_blob(blob: str) -> str:
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def serialise(rows: list[dict]) -> str:
    """The SAME serialisation efv_dataset.run uses for the served matrix, so a byte
    comparison between an arm and a served build is meaningful. Rows untouched: no
    flooring, no rounding, no column added."""
    return json.dumps(rows, indent=0)


def census(rows: list[dict], acct: dict, values: dict[str, object]) -> dict:
    """Row counts the lab and part 9 read first. Counts only: no statistic, no score."""
    deb = [r for r in rows if r.get("kind") == "debuted"]
    busts = [r for r in rows if r.get("kind") == "bust"]
    excluded = [r for r in busts if r.get("bust_recent")]
    resolved_deb = [r for r in deb if not r.get("censored")]
    neg = [r for r in resolved_deb
           if r.get("target_resolved") is not None and float(r["target_resolved"]) < 0.0]
    out = {
        "rows": len(rows), "debuted": len(deb), "busts": len(busts),
        "busts_excluded_from_pool": len(excluded),
        "busts_resolved": len(busts) - len(excluded),
        "debuted_resolved": len(resolved_deb), "debuted_censored": len(deb) - len(resolved_deb),
        "resolved_debuted_labels_below_zero": len(neg),
        "window_shifted": acct.get("debuted_window_shifted", 0),
        "label_seasons_key_fallback_rows": acct.get("label_seasons_key_fallback_rows"),
    }
    if acct.get("arm_r"):
        out["arm_r"] = acct["arm_r"]
    return out


# ------------------------------------------------------------------ the run
def build_side(side: str, arms: list[str], omitted: dict[str, str], write: bool = True,
               out_dir: Path | None = None) -> dict:
    """Build the named arms for one side, write each under OUT_DIR, and write the side's
    manifest. Returns the manifest."""
    omit_ids = tuple(sorted(omitted))
    for o in omit_ids:
        if not (omitted[o] or "").strip():
            raise ArmRefused(f"omitting {o} needs a reason (--omit-reason)")
    manifest = {
        "schema": SCHEMA, "producer": "tools/efv_fwar_epoch_arms.py", "gate": GATE,
        "side": side, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seed": SEED, "scored_years": list(em.SCORED_YEARS),
        "resolved_through_at_build": ed.RESOLVED_THROUGH,
        "estar_resolved_through": ESTAR_RESOLVED_THROUGH,
        "e0_resolved_through": E0_RESOLVED_THROUGH,
        "factors": {f: {"name": FACTORS[f][0], "flag": f"{FACTORS[f][1]}.{FACTORS[f][2]}",
                        "e0_value": FACTORS[f][3],
                        "kind": "owner decision (ships regardless, no ship clause)"
                        if f in OWNER_DECISION_FACTORS else
                        "candidate (ships only if its own clauses pass)"}
                    for f in FACTORS},
        "omitted": {o: {"reason": omitted[o], "attribution": "UNAVAILABLE",
                        "note": "FAILED ARM (clause (i) point 5): never inferred from the "
                                "total, never estimated from the other arms; Estar carries "
                                "every other admitted factor"}
                    for o in omit_ids},
        "arms": {},
    }
    for arm in arms:
        if arm in omit_ids:
            continue
        t0 = time.time()
        rows, acct, values = build_arm(side, arm, omit_ids)
        blob = serialise(rows)
        entry = {
            "arm": arm, "factor_reverted": factor_reverted(arm),
            "factor_values": dict(values), "flags": flags_by_attribute(values),
            "label_provider": label_provider(values),
            "label_seasons_key": values["F1"], "resolved_through": values["F2"],
            "rows": len(rows), "sha256": _sha256_blob(blob),
            "census": census(rows, acct, values), "seconds": round(time.time() - t0, 1),
        }
        if write:
            p = arm_path(side, arm, out_dir)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(blob, encoding="utf-8")
            entry["file"] = p.name
            print(f"wrote {p} ({len(rows)} rows, sha256 {entry['sha256'][:16]})")
        manifest["arms"][arm] = entry
        print(f"--- {side} {arm}: reverted={entry['factor_reverted']} flags={entry['flags']}")
        for k, v in entry["census"].items():
            print(f"    {k:40s} {v}")
    if write:
        mp = manifest_path(side, out_dir)
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        print(f"wrote {mp}")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--side", default="both", choices=(*SIDES, "both"))
    ap.add_argument("--arm", action="append", default=None,
                    help="an arm to build (repeatable); default all")
    ap.add_argument("--omit", action="append", default=[],
                    help="a FAILED ARM's factor id to leave out (repeatable)")
    ap.add_argument("--omit-reason", action="append", default=[],
                    help="the reason, one per --omit, in order")
    ap.add_argument("--no-write", action="store_true", help="census only; write nothing")
    a = ap.parse_args(argv)
    arms = list(ARMS) if not a.arm or "all" in a.arm else list(a.arm)
    if len(a.omit) != len(a.omit_reason):
        raise ArmRefused("every --omit needs its own --omit-reason, in order")
    omitted = dict(zip(a.omit, a.omit_reason))
    sides = list(SIDES) if a.side == "both" else [a.side]
    for side in sides:
        build_side(side, arms, omitted, write=not a.no_write)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
