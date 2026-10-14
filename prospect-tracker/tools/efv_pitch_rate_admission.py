# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The DS-06 admission diagnostic for the pitch-rate sidecar columns (owner ask 19 of
2026-09-30, the eFV half; plan Part 8 lane pitch_metrics, pitch_metrics.md s7 step (c);
Q10_11_EFV_PITCH_RATE_ADMISSION, checklist PM-13).

WHY THIS MAY RUN AT ALL. The eFV feature frontier is closed (plan Part 2.2; the
2026-08-14 frontier closure), and for pitchers DS-Q2 keeps pitcher eFV in consensus order
until pitch-quality or K-rate data passes the sign-stability admission rule
(DECISIONS_FOR_OWNER.md DS-Q2). These two arms are reopened only by a new data field
(MiLB pitch counts, never before a model input) plus the owner's ask 19 of 2026-09-30,
and pbf_rel goes beyond DS-Q2 on that authority alone. The report beside this run states
each arm's correlation with the closed bb_rel arm (Q10_10's step (d), copied into the
artifact here) so a reader can see whether it is the closed walk-rate arm again.

REGISTRATION PATH. PM-Q4's answer (b) ("add to V2 now, before the frozen-label DS-16
re-run and before REGISTERED") could not be executed: the gate registered on 2026-10-08
(EW2-6) with DS-16 re-run on the frozen label the same day. The task's default (a),
re-asked 2026-10-08 and taken 2026-10-14 under EW3-5 as the recommended option, is what
runs here: the candidates do NOT enter V2's registration; the DS-06 rule runs on lv_dev
only, inside folds V 2017, 2018 and 2019 on each fold's own training vintages, per-vintage
signs stored; nothing is adjudicated; if both arms are admitted in all three folds they
are pre-declared for the NEXT registration before its first read.

THE RULE, verbatim from docs/efv-v2/EFV_V2_GATE.md s4.2 (efv_v2_model.admission_for_key):
a driver enters only if its coefficient's sign held in every training vintage that gives
a t (at least 60 rows, at least 2 such vintages) and its mean |t| is at least 1.0. The t
is read per training vintage in the OLS of the W3 percentile within (side, V) on
[1, consensus percentile, z(column)] over the has-block rows (the skill head's rows,
DS-04); a row without a pitch-rate value imputes at the fold's observed training mean,
as a sidecar driver does, and a vintage gives a t only when at least 60 of its rows
observe the column. The column is carried on each row's `v2` view under the screening
prefix (efv_v2_model.V2_SCREEN_PREFIX), exactly as tools/efv_screen_lab.py carries a
candidate, so efv_v2_model.has_block_means imputes it at the observed training mean.

FRAME. lv_dev only: tools/efv_v2_assemble.build_frames (every development list vintage
2011 to 2019 with its W3 / R3 labels on the frozen fWAR label), the training rows of
efv_v2_model.lv_training_rows, and for fold V the rows at list vintages below V with
every player of the V frame left out (gate s4.5). No order index is fitted, no
delta is read and no served number moves: this is the admission rule alone.

NEVER READ: list vintages 2020 and 2021 (R-LV; efv_vintage_frame's guard raises) and
the 2025 and later debut cohorts (R-VM; reserved_vm_pins asserted). A frame row whose
debut falls in a reserved cohort is kept at W3 = 0 on the training rows exactly as the
registered procedure keeps it (gate s5, B9b; counted in the artifact); the sidecar
dropped it before any count, so it carries no pitch-rate value and imputes at the
fold's training mean like any row without a block. Nothing is grouped, counted or
averaged by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md); the only groupings are
side, fold and training vintage. No table of PAR, P/PA or P/BF by grade or tier.

Run:  python tools/efv_pitch_rate_admission.py [--check | --dry-run]
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_labels as L  # noqa: E402
import efv_pitch_rate_features as PR  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_vintage_frame as F  # noqa: E402

SIDECAR = ROOT / "data" / "_labs" / "efv_pitch_rate_features.json"
OUT = ROOT / "data" / "_labs" / "efv_pitch_rate_admission.json"
SCHEMA = "efv_pitch_rate_admission/1"
TASK = "Q10_11_EFV_PITCH_RATE_ADMISSION"
TOOL = "tools/efv_pitch_rate_admission.py"
#: The folds V2 is scored on (gate s2.1, s10.1): each reads its own training vintages.
FOLDS: tuple[int, ...] = (2017, 2018, 2019)
HEAD = "skill"
TARGET = "u_y"
ARM_PREFIX = "PM19"
#: The column key on the row's v2 view: the screening prefix makes has_block_means
#: impute an absent value at the observed TRAIN mean (DS-04), as a sidecar driver does.
KEYS = {s: f"{H.V2_SCREEN_PREFIX}{PR.column_name(s)}" for s in F.SIDES}
CLOSED_ARM = "D-1:bb_rel:hit"
WHY_THIS_MAY_RUN = (
    "The eFV feature frontier is closed (plan Part 2.2; the 2026-08-14 frontier "
    "closure), and for pitchers DS-Q2 keeps pitcher eFV in consensus order until "
    "pitch-quality or K-rate data passes the sign-stability admission rule; these arms "
    "are reopened only by a new data field (MiLB pitch counts, never before a model "
    "input) plus the owner's ask 19 of 2026-09-30, and pbf_rel goes beyond DS-Q2 on "
    "that authority alone. Each arm's correlation with the closed bb_rel arm (Q10_10 "
    "step d) is stated beside it so a reader can see whether it is the closed "
    "walk-rate arm again.")
REGISTRATION_PATH = (
    "PM-Q4 default (a), taken 2026-10-14 on the 2026-10-08 re-ask under EW3-5: the "
    "candidates do not enter V2's 2026 registration (REGISTERED 2026-10-08, EW2-6, "
    "before any amendment could land, so answer (b) could not be executed); the DS-06 "
    "rule runs on lv_dev inside folds 2017, 2018 and 2019 on each fold's own training "
    "vintages; nothing is adjudicated; admitted in all three folds on both sides, the "
    "pair is pre-declared for the NEXT registration (V3 or the prospective cohort, "
    "docs/efv-v2/PROGRAM.md Q4) before its first read.")


class SidecarMissing(RuntimeError):
    """The sidecar artifact (Q10_10) is not on this tree."""


# ---------------------------------------------------------------------------
# guards and receipts
# ---------------------------------------------------------------------------

def guards(folds=FOLDS) -> dict:
    """Asserted before any frame is built: no R-VM pin is widened, no fold is a
    reserved list vintage, the combiner rule's years sit below the folds, and the gate
    is REGISTERED at HEAD (the default (a) procedure runs only after registration)."""
    pins = F.reserved_vm_pins()
    if pins:
        raise F.ReservedFrameError("; ".join(pins))
    folds = tuple(int(v) for v in folds)
    for v in folds:
        F.guard_score_request(v, purpose="pitch-rate admission")
    bad = sorted(set(folds) & set(F.RESERVED_LV))
    if bad or max(folds) >= min(F.RESERVED_LV):
        raise F.ReservedFrameError(f"an admission fold is reserved: {folds}")
    if H.RULE_LAST_YEAR >= min(folds):
        raise ValueError("the combiner rule's years overlap the admission folds")
    text = (ROOT / F.GATE_DOC).read_text(encoding="utf-8", errors="replace")
    registered = F.gate_doc_registered(text)
    if not registered:
        raise RuntimeError(f"{F.GATE_DOC} is not REGISTERED: default (a) runs only "
                           "after V2's registration")
    return {"reserved_lv": sorted(F.RESERVED_LV),
            "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
            "reserved_vm_pins": pins, "lv_folds": list(folds),
            "rule_last_year": H.RULE_LAST_YEAR, "gate_registered": registered,
            "vm_dev_read": False, "closed_arms_rerun": False,
            "order_index_fitted": False, "delta_read": False}


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    except OSError:
        return None


def _commit() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], cwd=ROOT,
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def label() -> dict:
    """The label the training rows carry: the frozen fWAR vintage, or a refusal. The
    default (a) procedure is a development read on the frozen label (spec FRAMES)."""
    prov = L.provider()
    if prov != "fwar":
        raise RuntimeError(f"the label provider is {prov!r}, not the frozen fWAR label")
    import war_source
    vid = (war_source.fwar_index() or {}).get("vintage_id")
    return {"provider": prov, "label_id": f"fwar@{vid}", "target": "W3",
            "target_percentile": "within (side, list vintage), ties averaged"}


# ---------------------------------------------------------------------------
# the column, read off the sidecar
# ---------------------------------------------------------------------------

def load_sidecar(path: Path = SIDECAR) -> dict:
    if not Path(path).exists():
        raise SidecarMissing(f"{Path(path).relative_to(ROOT).as_posix()} is not built "
                             "(tools/efv_pitch_rate_sidecar.py, Q10_10)")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sidecar_values(doc: dict, side: str) -> dict[tuple[int, str], float]:
    """{(V, player_key): value} off the sidecar's rows block (has-block rows only; a
    row with no entry has no block and reads None when attached)."""
    out: dict = {}
    for V, blk in (doc.get("rows") or {}).get(side, {}).items():
        F.guard_score_request(int(V), purpose="pitch-rate admission")
        for pk, rec in blk.items():
            out[(int(V), str(pk))] = float(rec[0])
    return out


def closed_arm_correlation(doc: dict, side: str) -> dict:
    """Q10_10's step (d) reading against the closed bb_rel column, copied, not re-read."""
    probe = (doc.get("probes") or {}).get(f"{ARM_PREFIX}:corr.{PR.column_name(side)}:{side}") or {}
    return {"closed_arm": CLOSED_ARM,
            "spearman_vs_bb_rel": (probe.get("spearman") or {}).get("bb_rel"),
            "n": (probe.get("n") or {}).get("bb_rel"),
            "source": "data/_labs/efv_pitch_rate_features.json probes (step d, no outcome)"}


def attach(rows: list[dict], key: str, values: dict) -> None:
    """The column on every row's v2 view (None where the row has no block), so
    efv_v2_model.screen_keys sees it on every row and has_block_means imputes it."""
    for r in rows:
        r["v2"][key] = values.get((int(r["decision_year"]), str(r["player_key"])))


# ---------------------------------------------------------------------------
# the rule, per fold
# ---------------------------------------------------------------------------

def fold_train(train: list[dict], V: int, frame_keys: set[str]) -> list[dict]:
    """Rows at list vintages below V with every player of the V frame left out."""
    V = int(V)
    return [r for r in train if int(r["decision_year"]) < V
            and str(r["player_key"]) not in frame_keys]


def _observed_by_vintage(tr: list[dict], key: str) -> dict[str, dict]:
    out: dict = {}
    for r in tr:
        yr = str(int(r["decision_year"]))
        b = out.setdefault(yr, {"rows": 0, "has_block": 0, "observed": 0})
        b["rows"] += 1
        if r["v2"]["has_block"]:
            b["has_block"] += 1
            if r["v2"].get(key) is not None:
                b["observed"] += 1
    return out


def admission_arm(side: str, train: list[dict], frame_keys_by_fold: dict[int, set[str]],
                  *, folds=FOLDS, closed: dict | None = None) -> dict:
    """One arm: the DS-06 rule for the side's column inside every fold on the fold's
    own training vintages, per-vintage signs stored. No verdict beyond the rule's own
    word; nothing is adjudicated."""
    key = KEYS[side]
    col = PR.column_name(side)
    by_fold: dict = {}
    for V in folds:
        V = int(V)
        F.guard_score_request(V, purpose="pitch-rate admission")
        tr = fold_train(train, V, frame_keys_by_fold.get(V) or set())
        chk = H.admission_for_key(tr, key, target=TARGET, has_block_only=True)
        by_fold[str(V)] = {
            "admitted": bool(chk["admitted"]), "reason": chk["reason"],
            "per_vintage_signs": chk["per_vintage_signs"],
            "t_by_vintage": chk["t_by_vintage"],
            "vintages_without_t": chk["vintages_without_t"],
            "n_valid_vintages": chk["n_valid_vintages"],
            "mean_abs_t": chk["mean_abs_t"], "sign": chk["sign"],
            "n_train": len(tr),
            "n_train_has_block": sum(1 for r in tr if r["v2"]["has_block"]),
            "n_train_observed": sum(1 for r in tr if r["v2"]["has_block"]
                                    and r["v2"].get(key) is not None),
            "training_vintages": sorted({int(r["decision_year"]) for r in tr}),
            "by_vintage": _observed_by_vintage(tr, key),
        }
    admitted_folds = [V for V, f in by_fold.items() if f["admitted"]]
    all_folds = len(admitted_folds) == len(folds)
    signs = {V: f["sign"] for V, f in by_fold.items()}
    one_sign = all_folds and len({s for s in signs.values()}) == 1
    return {
        "tag": f"{ARM_PREFIX}:{side}.{HEAD}.{col}",
        "side": side, "head": HEAD, "driver": col, "column_key": key,
        "target": TARGET, "rows": "has_block", "item": "DS-06",
        "frame": "lv_dev, folds 2017 to 2019, each on its own training vintages",
        "verdict": "ADMITTED" if all_folds else "REFUSED",
        "verdict_scope": ("the DS-06 rule inside every fold; ADMITTED only when all "
                          "three folds admit; a development reading that adjudicates "
                          "nothing"),
        "admitted": all_folds, "admitted_folds": admitted_folds,
        "n_admitted_folds": len(admitted_folds), "n_folds": len(folds),
        "fold_signs_agree": one_sign,
        "reason": ("admitted in every fold" if all_folds else
                   "; ".join(f"{V}: {f['reason']}" for V, f in by_fold.items()
                             if not f["admitted"])),
        "per_vintage_signs": {V: f["per_vintage_signs"] for V, f in by_fold.items()},
        "mean_abs_t": {V: f["mean_abs_t"] for V, f in by_fold.items()},
        "n_valid_vintages": {V: f["n_valid_vintages"] for V, f in by_fold.items()},
        "by_fold": by_fold,
        "sign_predicted": None,
        "closed_arm_comparison": closed,
        "delta": None, "floor_rho": None,
        "reads": "the W3 percentile and the consensus percentile on training rows only; "
                 "no order index, no delta, no served number",
    }


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def run_on_rows(rows_by_side: dict[str, list[dict]], values_by_side: dict[str, dict],
                *, folds=FOLDS, closed_by_side: dict | None = None) -> dict:
    """The arms on labelled V2 rows alone (each carrying player_key, decision_year,
    fv, target, reached, v2): the rows at a fold year are its frame. Fixtures and the
    real run share this path."""
    folds = tuple(int(v) for v in folds)
    arms: dict = {}
    counts: dict = {}
    for side, rows in rows_by_side.items():
        for r in rows:
            F.guard_score_request(int(r["decision_year"]), purpose="pitch-rate admission")
        H._check_years({int(r["decision_year"]) for r in rows})
        attach(rows, KEYS[side], values_by_side.get(side) or {})
        frame_keys = {V: {str(r["player_key"]) for r in rows
                          if int(r["decision_year"]) == V} for V in folds}
        arm = admission_arm(side, rows, frame_keys, folds=folds,
                            closed=(closed_by_side or {}).get(side))
        arms[arm["tag"]] = arm
        counts[side] = {"training_rows": len(rows),
                        "has_block": sum(1 for r in rows if r["v2"]["has_block"]),
                        "observed": sum(1 for r in rows if r["v2"].get(KEYS[side]) is not None)}
    return {"arms": arms, "counts": counts}


def run(*, frames: dict | None = None, sidecar: dict | None = None, folds=FOLDS,
        log=print) -> dict:
    """The document. `frames` ({side: {V: (rows, labels)}}) is for tests; None builds
    lv_dev with tools/efv_v2_assemble.build_frames on the frozen label."""
    t0 = time.time()
    g = guards(folds)
    lab = label()
    doc = load_sidecar() if sidecar is None else sidecar
    if frames is None:
        import efv_v2_assemble as ASM
        frames = ASM.build_frames()
        log(f"lv frames built ({round(time.time() - t0, 1)} s)")
    rows_by_side: dict = {}
    values_by_side: dict = {}
    closed_by_side: dict = {}
    frame_keys: dict = {}
    kept: dict = {}
    for side in F.SIDES:
        by_v = frames[side]
        for V in by_v:
            F.guard_score_request(int(V), purpose="pitch-rate admission")
        rows_by_side[side] = H.lv_training_rows(side, by_v)
        values_by_side[side] = sidecar_values(doc, side)
        closed_by_side[side] = closed_arm_correlation(doc, side)
        frame_keys[side] = {int(V): {str(r["player_key"]) for r in by_v[V][0]}
                            for V in by_v}
        # B9b: a reserved_vm label kept at W3 = 0 is a training row with no
        # pitch-rate value (the sidecar dropped it before any count); counted here
        in_train = {(int(r["decision_year"]), str(r["player_key"]))
                    for r in rows_by_side[side]}
        kept[side] = sum(1 for V in by_v for lab in by_v[V][1]
                         if lab.get("status") == "reserved_vm"
                         and (int(V), str(lab.get("player_key"))) in in_train)
    folds = tuple(int(v) for v in folds)
    arms: dict = {}
    counts: dict = {}
    for side in F.SIDES:
        rows = rows_by_side[side]
        attach(rows, KEYS[side], values_by_side[side])
        arm = admission_arm(side, rows, frame_keys[side], folds=folds,
                            closed=closed_by_side[side])
        arms[arm["tag"]] = arm
        counts[side] = {"training_rows": len(rows),
                        "has_block": sum(1 for r in rows if r["v2"]["has_block"]),
                        "observed": sum(1 for r in rows if r["v2"].get(KEYS[side]) is not None),
                        "reserved_vm_kept_w3_zero": kept[side],
                        "by_vintage": _observed_by_vintage(rows, KEYS[side])}
        log(f"  {arm['tag']}: {arm['verdict']} (folds admitted "
            f"{arm['admitted_folds'] or 'none'})")
    both = all(a["admitted"] for a in arms.values())
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "produced_by": TOOL, "task": TASK, "code_commit": _commit(),
        "owner_ask": ("19 (2026-09-30): calculate P/IP, P/PA and PAR relative to each "
                      "level for prospects, and check if any can be used as a driver "
                      "for eFV"),
        "why_this_may_run": WHY_THIS_MAY_RUN,
        "registration_path": REGISTRATION_PATH,
        "role": "development diagnostic on a spent frame; adjudicates nothing; no served number",
        "adjudicates": "nothing",
        "frame": "lv_dev", "folds": list(folds), "head": HEAD, "target": TARGET,
        "guards": g, "label": lab,
        "rule": {"statement": ("a driver enters only if its coefficient's sign held in "
                               "every training vintage that gives a t (at least 60 rows, "
                               "at least 2 such vintages) and its mean |t| is at least "
                               "1.0 (docs/efv-v2/EFV_V2_GATE.md s4.2, DS-06)"),
                 "min_rows": H.ADMIT_MIN_ROWS, "min_vintages": H.ADMIT_MIN_VINTAGES,
                 "min_mean_abs_t": H.ADMIT_MIN_MEAN_ABS_T,
                 "rows": "has-block rows (the skill head's, DS-04)",
                 "imputation": "absent value at the fold's observed training mean, no flag",
                 "training": "efv_v2_model.lv_training_rows at list vintages below V, "
                             "every V-frame player excluded (gate s4.5)",
                 "function": "efv_v2_model.admission_for_key(target=u_y, has_block_only=True)"},
        "inputs": {
            "sidecar": SIDECAR.relative_to(ROOT).as_posix(),
            "sidecar_sha256": _sha(SIDECAR),
            "sidecar_generated_at": doc.get("generated_at"),
            "efv_v2_model.py": _sha(ROOT / "efv_v2_model.py"),
            "efv_pitch_rate_features.py": _sha(ROOT / "efv_pitch_rate_features.py"),
            "efv_vintage_frame.py": _sha(ROOT / "efv_vintage_frame.py"),
            "milb_floor": {s: F.lv_milb_floor(s) for s in F.SIDES},
        },
        "counts": counts,
        "arms": arms, "n_arms": len(arms),
        "admitted_all_folds_both_sides": both,
        "pre_declaration": (
            "owed: both arms admitted in all three folds; write the dated "
            "pre-declaration for the NEXT registration before its first read"
            if both else
            "not owed: at least one arm is refused in at least one fold; the pair is "
            "not pre-declared and enters no candidate list"),
        "balance_probe": ("step (b) of pitch_metrics.md s7 is Q10_10's re-arm "
                          "(tools/efv_pitch_rate_sidecar.py), not this tool's"),
        "never": ["list vintages 2020 and 2021 (R-LV)", "debut cohorts 2025+ (R-VM)",
                  "any grouping by consensus-FV level", "any order index or delta",
                  "any served eFV change"],
        "elapsed_s": round(time.time() - t0, 1),
    }


def write(doc: dict, path: Path = OUT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(doc, indent=1) + "\n").encode("utf-8"))


def _echo(doc: dict) -> None:
    for tag, a in doc["arms"].items():
        print(f"{a['verdict']:9s} {tag}")
        for V, f in a["by_fold"].items():
            print(f"    fold {V}: admitted {f['admitted']!s:5s} signs {f['per_vintage_signs']} "
                  f"t {f['t_by_vintage']} mean|t| {f['mean_abs_t']} "
                  f"(train {f['n_train']}, has_block {f['n_train_has_block']}, "
                  f"observed {f['n_train_observed']}) {f['reason']}")
        c = a.get("closed_arm_comparison") or {}
        print(f"    vs {c.get('closed_arm')}: spearman {c.get('spearman_vs_bb_rel')} "
              f"(n {c.get('n')})")
    print(f"pre-declaration: {doc['pre_declaration']}")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--check" in argv:
        g = guards()
        lab = label()
        doc = load_sidecar()
        print(json.dumps({"guards": g, "label": lab,
                          "sidecar_generated_at": doc.get("generated_at"),
                          "sidecar_rows": {s: sum(len(b) for b in doc["rows"][s].values())
                                           for s in F.SIDES}}, indent=1))
        return 0
    doc = run()
    _echo(doc)
    if "--dry-run" not in argv:
        write(doc)
        print(f"wrote {OUT.relative_to(ROOT).as_posix()} ({doc['elapsed_s']} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
