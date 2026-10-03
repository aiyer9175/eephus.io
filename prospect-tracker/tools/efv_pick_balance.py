# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DS-03 balance probe on the pick family's missingness indicator (EFV3_B4;
SP/efv3/LANE_B.md F-B7 and the D1 rule in s3).

"Has a known draft pick at V" could proxy "was drafted high enough to be tracked",
which could proxy the outcome, so pick_missing is tested for label balance exactly as
tools/efv_identity_balance.py tests milb_absent: on the list-vintage frame F-LV, every
development vintage 2011 to 2019, the W3 > 0 share and the R3 share of the rows with
the indicator against the rows without, by side, and the indicator's partial
coefficient in a linear probability model of W3 > 0 on the within-(side, vintage)
consensus percentile (a quadratic) and vintage effects, with a player-clustered
bootstrap CI95 (B_BAL draws). BALANCED when the CI95 covers zero. The verdict is
clause (f) of the screening lab's admission rule for the pick arms; the head is the
timing head on both sides whatever the verdict (DRIVER_SYSTEM_V2 D4: pick is never a
rank feature), so the probe decides admissibility, never the head.

The verdicts, the coverage receipt by (side, vintage) and the registration counts are
written under the key "pick" of data/efv_identity_balance.json; every other key of that
receipt is left byte for byte (the identity tool's and the text tool's own output). No
progress row, no ledger row: the column is scored only by the screening lab, and its
arm row is the registered run's (EFV3_B7).

This tool joins the labels; the builder (efv_pick_features.py) never sees them.
NEVER READ: list vintages 2020 and 2021 (the guard raises) and every player whose
effective debut year is 2025 or later (dropped before any statistic, count reported).
Nothing is grouped by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md).

Run:  python tools/efv_pick_balance.py [--dry-run]
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_identity_balance as IB  # noqa: E402
import efv_labels as L  # noqa: E402
import efv_pick_features as PK  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import source_backtest as SB  # noqa: E402

OUT = ROOT / "data" / "efv_identity_balance.json"
#: The key this probe writes under in the balance receipt.
BALANCE_KEY = "pick"
SEED = IB.SEED
B_BAL = IB.B_BAL
VINTAGES: tuple[int, ...] = tuple(F.DEV_VINTAGES)
INDICATOR = PK.INDICATOR
#: LANE_B.md F-B7 (laneB_coverage.json): rows joining a draft_history pick dated before
#: V on the outcome-blind id, hitters / pitchers, at the first and last development
#: vintage; the closed F-VM arm this column re-tests (data/xfv_arm_ledger.json D-1).
REGISTRATION = {
    "draft_history_pre_v_lane_b": {"2011": {"hit": [46, 69], "pit": [46, 58]},
                                   "2019": {"hit": [286, 543], "pit": [321, 489]}},
    "sidecar_pick_known_lane_b": "0 rows before V 2013",
    "retest_of": {"arm": PK.RETEST_OF, "frame": "vm (F-VM, debut year)",
                  "delta_rho": {"hit": -0.00171, "pit": -0.00759},
                  "floor_rho": {"hit": 0.0194, "pit": 0.0172},
                  "cleared_own_floor": False},
    "head": PK.HEAD,
    "head_rule": "DRIVER_SYSTEM_V2 D4: pick and bonus are never a rank feature",
    "source": "SP/efv3/LANE_B.md F-B7; data/xfv_arm_ledger.json",
}


def build_rows(universe=None, war=None, picks=None) -> tuple[list[dict], dict, dict]:
    """(probe rows, receipt, pick rows by side) on VINTAGES, R-VM players dropped.
    The frame is built without its MiLB block (the pick join needs the id, the window
    and the sidecar only)."""
    universe = universe if universe is not None else F.load_universe()
    war = war if war is not None else L.war_seasons_table()
    picks = picks if picks is not None else PK.load_draft_picks()
    rows, receipt = [], {"frame_rows": 0, "no_consensus": 0, "label_none": 0,
                         "dropped_rvm_players": 0, "vintages": list(VINTAGES)}
    rvm_keys = set()
    by_side: dict[str, dict[int, list[dict]]] = {}
    for side in F.SIDES:
        by_side[side] = {}
        for V in VINTAGES:
            F.guard_score_request(V, purpose="pick balance")
            frame = PK.attach_pick(F.build_frame(side, V, universe=universe, milb=False),
                                   picks)
            by_side[side][V] = frame
            receipt["frame_rows"] += len(frame)
            labs = L.labels_for_frame(frame, universe=universe, war=war)
            for r, lab in zip(frame, labs):
                if lab.get("debut_year") is not None and \
                        int(lab["debut_year"]) >= F.R_VM_FIRST_DEBUT_YEAR:
                    rvm_keys.add(r["player_key"])
                    continue
                c = (r.get("grades") or {}).get(SB.CONSENSUS_KEY)
                if c is None:
                    receipt["no_consensus"] += 1
                    continue
                if lab.get("w3") is None:
                    receipt["label_none"] += 1
                    continue
                rows.append({"pk": r["player_key"], "V": V, "side": side, "fv": float(c),
                             "w3": float(lab["w3"]), "r3": lab.get("r3"),
                             INDICATOR: float(r[INDICATOR])})
    receipt["dropped_rvm_players"] = len(rvm_keys)
    receipt["rows_scored"] = len(rows)
    return rows, receipt, by_side


def balance(rows: list[dict], rng: np.random.Generator) -> dict:
    """The identity tool's balance formula on the one pick indicator."""
    out: dict = {}
    for side in F.SIDES:
        d = [r for r in rows if r["side"] == side]
        u = IB._within([r["fv"] for r in d], [r["V"] for r in d])
        ypos = np.array([float(r["w3"] > 0) for r in d])
        r3 = np.array([np.nan if r["r3"] is None else float(r["r3"]) for r in d])
        vs = sorted({r["V"] for r in d})
        dummies = np.column_stack([[float(r["V"] == v) for r in d] for v in vs[1:]]) \
            if len(vs) > 1 else np.zeros((len(d), 0))
        cl = IB._clusters([r["pk"] for r in d])
        x = np.array([r[INDICATOR] for r in d])
        n1 = int(x.sum())
        blk = {"n": len(d), "n_with": n1, "n_without": len(d) - n1}
        if n1 == 0 or n1 == len(d):
            blk.update({"verdict": "CONSTANT", "partial": None, "ci95": None})
            out[side] = {INDICATOR: blk}
            continue
        m1, m0 = x == 1, x == 0
        blk["w3_pos_share_with"] = round(float(ypos[m1].mean()), 4)
        blk["w3_pos_share_without"] = round(float(ypos[m0].mean()), 4)
        blk["w3_pos_gap"] = round(float(ypos[m1].mean() - ypos[m0].mean()), 4)
        ok = ~np.isnan(r3)
        if (ok & m1).any() and (ok & m0).any():
            blk["r3_share_with"] = round(float(r3[ok & m1].mean()), 4)
            blk["r3_share_without"] = round(float(r3[ok & m0].mean()), 4)
        X = np.column_stack([np.ones(len(d)), u, u ** 2, dummies, x])

        def coef(ix):
            b, *_ = np.linalg.lstsq(X[ix], ypos[ix], rcond=None)
            return float(b[-1])
        point = coef(np.arange(len(d)))
        draws = []
        for _ in range(B_BAL):
            pick = rng.integers(0, len(cl), len(cl))
            ix = np.concatenate([cl[j] for j in pick])
            if x[ix].min() == x[ix].max():
                continue
            draws.append(coef(ix))
        lo, hi = (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)))
        blk.update({"partial": round(point, 4), "ci95": [round(lo, 4), round(hi, 4)],
                    "B_used": len(draws),
                    "verdict": "BALANCED" if lo <= 0 <= hi else "IMBALANCED"})
        out[side] = {INDICATOR: blk}
    return out


def pick_block(bal: dict, receipt: dict, coverage: dict, commit: str | None) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "produced_by": "tools/efv_pick_balance.py",
        "builder": "efv_pick_features.py",
        "role": "development",
        "adjudicates": "nothing; the DS-03 missingness receipt for the pick family",
        "frame": (f"lv_dev (F-LV, list vintages {VINTAGES[0]} to {VINTAGES[-1]}), "
                  f"W3 on the {L.provider()} label"),
        "label": {"provider": L.provider(), "resolved_through": L.resolved_through()},
        "guards": {"reserved_lv": sorted(F.RESERVED_LV),
                   "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
                   "reserved_vm_pins": F.reserved_vm_pins(),
                   "vintages_read": list(VINTAGES)},
        "code": {"commit": commit, "builder_sha256": IB._sha(ROOT / "efv_pick_features.py"),
                 "tool_sha256": IB._sha(Path(__file__))},
        "rows": receipt,
        "indicator": {INDICATOR: "no draft pick known at V on the row: no draft_history "
                                 "pick dated before V on the outcome-blind id and no "
                                 "sidecar pick known at V"},
        "balance": bal,
        # the lab's clause (f) reads the verdict; the head is D4's, not the verdict's
        "admissible_clause_f": {side: bal[side][INDICATOR]["verdict"] in ("BALANCED", "CONSTANT")
                                for side in F.SIDES},
        "offered_columns": {side: [PK.column_name(side)] for side in F.SIDES},
        "head": PK.HEAD,
        "coverage": coverage,
        "settings": {"transform": PK.TRANSFORM, "join_id": "mlbam_id (outcome-blind, "
                                                            "efv_identity)",
                     "draft_year_rule": "latest draft year strictly below V",
                     "fallback": "acquisitions sidecar pick_overall when acq_known_at_v"},
        "registration": REGISTRATION,
        "not_in_efv_progress": ("the pick column is scored only by the screening lab; "
                                "this probe writes no progress row and no ledger row"),
        "seed": SEED, "B": B_BAL,
    }


def merge_pick_key(path: Path, block: dict) -> None:
    """Write `block` under BALANCE_KEY of the receipt at `path`, every other key and
    the file's own line ending kept. Idempotent."""
    raw = path.read_bytes()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    doc = json.loads(raw.decode("utf-8"))
    doc[BALANCE_KEY] = block
    text = json.dumps(doc, indent=1) + "\n"
    path.write_bytes(text.replace("\n", nl).encode("utf-8"))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    for V in VINTAGES:
        F.guard_score_request(V, purpose="pick balance")
    rng = np.random.default_rng(SEED)
    rows, receipt, by_side = build_rows()
    coverage = PK.coverage_receipt(by_side)
    bal = balance(rows, rng)
    try:
        commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                capture_output=True, text=True).stdout.strip() or None
    except OSError:
        commit = None
    block = pick_block(bal, receipt, coverage, commit)
    print(json.dumps({"rows": receipt, "balance": bal,
                      "admissible_clause_f": block["admissible_clause_f"],
                      "coverage": coverage["by_side_vintage"],
                      "draft_files": coverage["draft_files"]}, indent=1))
    if "--dry-run" not in argv:
        merge_pick_key(OUT, block)
        print(f"wrote key {BALANCE_KEY!r} of {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
