# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EFV3_A5: frame version vm3, the development read (EFV3_PLAN.md s3 G2; lane A
E3-Q1 = A, the recommended option under the owner's standing instruction).

vm2, the headline, keeps a debut-cohort row only when FanGraphs and MLB Pipeline both
graded it in the debut year's preseason window. vm3 keeps every debut-cohort row with
an in-window PROSPX consensus read and a timing-pinned eFV score
(source_backtest._consensus_present_rows and _vm3_frame_rows, the frame's one
definition), and scores each source on ITS OWN rows, the lv_dev convention of
docs/efv-v2/STATUS.md. Same players, same raters, no fresh evidence: a DEVELOPMENT
frame. vm2 stays the headline; the headline switch is a frame change that only
EFV_V2_RESERVED_READ's record and a later owner answer can make.

In this order: the counts (`--check`, and `census` in the artifact), then the floors
(E_cond by the registered resampler, B 2000 seed 20260906, player-clustered, mde95
1.645 x sd; E_refit read from data/efv_vm3_frame_floor.json, written once by
`python tools/efv_headtohead_frame_lab.py vm3`), then the raters: the served eFV V2
(efv_v2_serve.served_oos_scores, the vm2 headline's scored object, timing-pinned),
eFV v1 (efv_model.oos_grades, timing-pinned), PROSPX consensus, MLB Pipeline and
FanGraphs. Nothing new is rated. Statistic: efv_v2_stat (within (side, vintage)
primary, pooled after the identical map secondary, contributor AUC veto), every
comparison on identical rows; the per-source Holm family of
source_backtest.H2H_HOLM_RATERS x H2H_HOLM_METRICS (k 6) unchanged, own rows.

Part (2), the Pipeline-only panel (EFV3_PLAN.md s3 G3): debut cohorts 2011 to 2016
with an in-window MLB Pipeline read (source_backtest.PIPELINE_PANEL_*), scored by eFV
v1 only (V2 has no out-of-sample score before 2017; v1 scores decision years from
efv_model.SCORED_YEARS, 2014), as frame vm_pipeline_2011_2016, role development.
Consensus on these rows is Pipeline alone and the receipt says so; a row with a
FanGraphs grade in its window is excluded and counted; never pooled with vm2 or vm3.

The artifact (data/efv_vm3_frame_eval.json) stamps the label the read ran on
(war_source.DEFAULT_PROVIDER, efv_dataset.RESOLVED_THROUGH): a read on any provider
but fwar is EXPLORATORY and says so. Its rows land in data/efv_progress.json with
frame vm3, role development (efv_progress.update_vm3), a post-epoch run as a new row,
never an edit, and one probe per frame read in data/xfv_arm_ledger.json.

BANS (asserted before any score): source_backtest.CANDIDATE_YEARS and
efv_model.SCORED_YEARS stay below the first reserved debut cohort
(efv_vintage_frame.reserved_vm_pins() empty); no list vintage is read (R-LV
untouched); nothing is grouped by consensus-FV level; no closed arm is re-run.

Run once:  python tools/efv_vm3_frame_read.py --check      (counts only, no write)
           python tools/efv_vm3_frame_read.py              (the read, the ledger rows)
           python tools/efv_vm3_frame_read.py --no-ledger  (the artifact alone)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_dataset as D  # noqa: E402
import efv_model as V1  # noqa: E402
import efv_v2_serve as V2S  # noqa: E402
import efv_v2_stat as S  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import source_backtest as SB  # noqa: E402
import war_source  # noqa: E402
from efv_v2_dev_read import _commit, _label_id, _sha  # noqa: E402

TASK = "EFV3_A5"
OUT_PATH = SB.DATA_DIR / "efv_vm3_frame_eval.json"
FLOOR_PATH = SB.DATA_DIR / "efv_vm3_frame_floor.json"
CONS = SB.CONSENSUS_KEY
#: Row columns: the served eFV V2 under source_backtest's own key, v1 beside it.
V2_KEY = "xfv"
V1_KEY = "efv_v1"
VM3_FRAME = "vm3"
#: (row column, artifact rater name); the ledger's V2_RATERS map reads these names.
VM3_RATERS_OUT = ((V2_KEY, "efv_v2"), (V1_KEY, "efv_v1"), (CONS, "prospx_consensus"),
                  ("mlb_pipeline", "mlb_pipeline"), ("fangraphs", "fangraphs"))
#: (name, a, b): every comparison, a minus b, on the rows both graded.
VM3_COMPARISONS = (("v2_vs_prospx_consensus", V2_KEY, CONS),
                   ("v2_vs_efv_v1", V2_KEY, V1_KEY),
                   ("efv_v1_vs_prospx_consensus", V1_KEY, CONS),
                   ("v2_vs_mlb_pipeline", V2_KEY, "mlb_pipeline"),
                   ("v2_vs_fangraphs", V2_KEY, "fangraphs"))
PRIMARY_COMPARISON = "v2_vs_prospx_consensus"
EXPLORATORY_NOTE = "exploratory, eWAR label, frame census; not a claim"
#: EFV3_A5 (G3): the Pipeline-only panel, debut cohorts 2011 to 2016
#: (source_backtest.PIPELINE_PANEL_*). Scored by eFV v1 only (its timing-pinned
#: out-of-sample score under the `xfv` column), against the consensus, which is MLB
#: Pipeline alone there; FanGraphs has no row and V2 no score. Never pooled with vm2
#: or vm3 rows: its cohorts end before the vintage-matched window begins.
PANEL_FRAME = SB.PIPELINE_PANEL_FRAME_KEY
PANEL_RATERS_OUT = ((V2_KEY, "efv_v1"), (CONS, "prospx_consensus"),
                    ("mlb_pipeline", "mlb_pipeline"))
PANEL_COMPARISONS = (("efv_v1_vs_prospx_consensus", V2_KEY, CONS),
                     ("efv_v1_vs_mlb_pipeline", V2_KEY, "mlb_pipeline"))
PANEL_PRIMARY_COMPARISON = "efv_v1_vs_prospx_consensus"


# ---------------------------------------------------------------------------
# guards, label, sides

def _guards(years: list[int]) -> dict:
    pins = F.reserved_vm_pins()
    if pins:
        raise F.ReservedFrameError("; ".join(pins))
    if not years or max(years) >= F.R_VM_FIRST_DEBUT_YEAR:
        raise F.ReservedFrameError(f"vm window reaches R-VM: {years}")
    if not set(years) <= set(SB.CANDIDATE_YEARS):
        raise ValueError(f"vm window {years} outside CANDIDATE_YEARS")
    return {"reserved_lv": sorted(F.RESERVED_LV),
            "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
            "reserved_vm_pins": pins,
            "candidate_years_max": max(SB.CANDIDATE_YEARS),
            "scored_years_max": max(V1.SCORED_YEARS),
            "vm_years_read": list(years),
            "list_vintages_read": [],
            "grouped_by_consensus_fv": False,
            "closed_arms_rerun": 0}


def _label() -> dict:
    provider = str(war_source.DEFAULT_PROVIDER)
    vintage = None
    if provider == "fwar":
        try:
            vin = json.loads((SB.DATA_DIR / "fwar_vintage.json").read_text(encoding="utf-8"))
            vintage = vin.get("vintage_id")
        except (OSError, ValueError, AttributeError):
            vintage = None
    return {"provider": provider, "resolved_through": int(D.RESOLVED_THROUGH),
            "id": _label_id(), "vintage": vintage,
            "exploratory": provider != "fwar"}


def _note(label: dict, frame: str = VM3_FRAME) -> str:
    if label.get("exploratory"):
        return EXPLORATORY_NOTE
    if frame == PANEL_FRAME:
        return (f"development read on the frozen fWAR label ({label.get('id')}); frame "
                "census, Pipeline-only panel 2011 to 2016, consensus on these rows is "
                "MLB Pipeline alone, eFV v1 only, never pooled with vm2 or vm3; not a claim")
    return (f"development read on the frozen fWAR label ({label.get('id')}); frame "
            "census, consensus-present rule; vm2 stays the headline; not a claim")


def _side_of() -> dict:
    """player_key -> side, from the matrix the row lives in (source_backtest's own
    rule: a two-way player keeps the first assignment, hit)."""
    out: dict = {}
    for side in F.SIDES:
        try:
            for r in json.loads(D.matrix_path(side).read_text(encoding="utf-8")):
                out.setdefault(r["player_key"], side)
        except (OSError, ValueError):
            pass
    return out


# ---------------------------------------------------------------------------
# the frame

def build_vm3(universe: list[dict], years: list[int], side_of: dict) -> tuple[list[dict], dict]:
    """The vm3 rows: source_backtest's consensus-present candidates, kept by
    _vm3_frame_rows on the served V2's timing-pinned score and receipt, with v1's
    timing-pinned score attached. Scores are the same objects source_backtest scores
    on the vm2 headline (DS-01: raw, no remap)."""
    v1_rec: dict = {}
    v1_pin: dict = {}
    for s in F.SIDES:
        v1_pin.update(V1.oos_grades(s, timing_pin=True, receipts=v1_rec))
    v2_rec: dict = {}
    v2_pin = V2S.served_oos_scores(timing_pin=True, receipts=v2_rec)
    cand = SB._consensus_present_rows(universe, years)
    rows, receipt = SB._vm3_frame_rows(cand, v2_pin, v2_rec)
    frame, dropped = [], {"no_v1_pinned_score": 0, "no_side": 0}
    for c in rows:
        k = c["key"]
        dy = (c.get("outcome") or {}).get("debut_year")
        if dy is None or dy >= F.R_VM_FIRST_DEBUT_YEAR or dy != c["year"]:
            raise F.ReservedFrameError(f"vm3 row outside the frame: {k} {dy}")
        v1s = v1_pin.get(k)
        if v1s is None:
            dropped["no_v1_pinned_score"] += 1
            continue
        side = side_of.get(k)
        if side not in F.SIDES:
            dropped["no_side"] += 1
            continue
        row = dict(c)
        row["grades"] = dict(c["grades"], **{V1_KEY: v1s})
        row["side"] = side
        row["group"] = f"{side}|{c['year']}"
        frame.append(row)
    meta = {"window": [min(years), max(years)], "years": list(years),
            "receipt": receipt, "dropped": dropped,
            "n_candidates": len(cand), "n_pinned_rows": len(rows),
            "v1_pinned_scores": len(v1_pin), "v2_pinned_scores": len(v2_pin),
            # the pinned maps themselves, for the census and the panel (never serialized)
            "_v2_pin": v2_pin, "_v2_rec": v2_rec, "_v1_pin": v1_pin, "_v1_rec": v1_rec}
    return frame, meta


def build_panel(universe: list[dict], side_of: dict, v1_pin: dict, v1_rec: dict,
                vm3_keys: set) -> tuple[list[dict], dict]:
    """The Pipeline-only panel's rows: source_backtest's panel candidates (an
    in-window Pipeline read, no FanGraphs grade), kept by _vm3_frame_rows on eFV v1's
    timing-pinned score and receipt (the `xfv` column is v1 here). Guards: the
    cohorts are PIPELINE_PANEL_YEARS, below the vintage-matched window, and no panel
    player is a vm3 row (never pooled)."""
    years = list(SB.PIPELINE_PANEL_YEARS)
    if max(years) >= min(SB.CANDIDATE_YEARS) or max(years) >= F.R_VM_FIRST_DEBUT_YEAR:
        raise ValueError(f"panel years {years} reach the vintage-matched window")
    cand, n_fg = SB._pipeline_panel_rows(universe, years)
    rows, receipt = SB._vm3_frame_rows(cand, v1_pin, v1_rec)
    receipt["frame_version"] = PANEL_FRAME
    receipt["rule"] = SB.PIPELINE_PANEL_RULE
    receipt["n_with_fangraphs_excluded"] = n_fg
    frame, dropped = [], {"no_side": 0, "fangraphs_in_window": 0}
    for c in rows:
        k = c["key"]
        if c["grades"].get("fangraphs") is not None:
            dropped["fangraphs_in_window"] += 1
            continue
        if k in vm3_keys or c["year"] not in years:
            raise ValueError(f"panel row pooled with vm3 or outside its cohorts: {k} {c['year']}")
        side = side_of.get(k)
        if side not in F.SIDES:
            dropped["no_side"] += 1
            continue
        row = dict(c)
        row["side"] = side
        row["group"] = f"{side}|{c['year']}"
        frame.append(row)
    receipt["n_with_fangraphs"] = sum(1 for c in frame if c["grades"].get("fangraphs") is not None)
    receipt["consensus"] = SB._panel_consensus_receipt(frame)
    meta = {"window": [min(years), max(years)], "years": years, "receipt": receipt,
            "dropped": dropped, "n_candidates": len(cand),
            "n_with_fangraphs_excluded": n_fg, "n_pinned_rows": len(rows)}
    return frame, meta


def _n_side(rows: list[dict]) -> dict:
    out: dict = {}
    for c in rows:
        out[c["side"]] = out.get(c["side"], 0) + 1
    return {k: out[k] for k in ("hit", "pit") if k in out}


def _frame_block(rows: list[dict], raters_out, comparisons) -> dict:
    """Rater stats on each rater's own rows; every comparison on the rows both
    graded, by the within, pooled and AUC statistics (efv_v2_stat, E_cond)."""
    def cols(sel, key):
        return [c["grades"][key] for c in sel]
    raters = {}
    for key, name in raters_out:
        sel = [c for c in rows if c["grades"].get(key) is not None]
        if not sel:
            continue
        st = S.rater_stats(cols(sel, key), [c["outcome"]["war"] for c in sel],
                           [bool(c["outcome"]["contributor"]) for c in sel],
                           [c["group"] for c in sel], cols(sel, CONS))
        raters[name] = {"spearman": st["within"], "auc": st["auc"], "n": st["n"],
                        "within": st["within"], "pooled": st["pooled"],
                        "within_rows": st["within_rows"],
                        "within_groups": st["within_groups"],
                        "own_rows": True}
    deltas = {}
    for name, a, b in comparisons:
        sel = [c for c in rows if c["grades"].get(a) is not None
               and c["grades"].get(b) is not None]
        legs = {}
        for stat, slot in (("within", "spearman"), ("pooled", "pooled"), ("auc", "auc")):
            d = S.paired_delta([c["key"] for c in sel], [c["group"] for c in sel],
                               [c["outcome"]["war"] for c in sel],
                               [bool(c["outcome"]["contributor"]) for c in sel],
                               cols(sel, a), cols(sel, b), cols(sel, CONS),
                               statistic=stat)
            d["reading"] = S.reading(d.get("ci95"))
            d["identical_rows"] = True
            legs[slot] = d
        deltas[name] = legs
    return {"raters": raters, "deltas": deltas}


def _secondary(block: dict) -> dict:
    return {"statistic": S.STAT_LABEL["pooled"],
            "raters": {n: r.get("pooled") for n, r in block["raters"].items()},
            "deltas": {n: {"delta": (d.get("pooled") or {}).get("delta"),
                           "ci95": (d.get("pooled") or {}).get("ci95"),
                           "mde95": (d.get("pooled") or {}).get("mde95"),
                           "reading": (d.get("pooled") or {}).get("reading")}
                       for n, d in block["deltas"].items()}}


def _holm_block(rows: list[dict], *, frame_key: str, basis: str) -> dict:
    """The per-source cells and the one Holm family (k 6), each source on its own
    rows, through source_backtest's own wrapper (own_rows=True). No headline verdict
    exists for a development frame, so the consensus Spearman cell never prints a
    word; the interval is the reading."""
    acc = {}
    for rater in [V2_KEY] + list(SB.H2H_HOLM_RATERS):
        rr = [c for c in rows if c["grades"].get(rater) is not None
              and c["grades"].get(V2_KEY) is not None]
        if not rr:
            continue
        sp = SB._spearman([c["grades"][rater] for c in rr], [c["outcome"]["war"] for c in rr])
        au = SB._auc([c["grades"][rater] for c in rr],
                     [bool(c["outcome"]["contributor"]) for c in rr])
        acc[rater] = {"n": len(rr), "basis": "own rows, pooled",
                      "spearman": None if sp is None else round(sp, 4),
                      "auc": None if au is None else round(au, 4)}
    out = SB._head_to_head_vs_sources(rows, acc, frame=frame_key, basis=basis,
                                      headline=None, own_rows=True)
    out["role"] = "development"
    out["reading_rule"] = ("development frame: no headline verdict exists for it, so "
                           "the PROSPX consensus Spearman cell carries no word; every "
                           "cell is read as its interval")
    return out


def _e_refit_floor() -> dict | None:
    """The vm3 E_refit floor, read from the lab's artifact when it exists."""
    try:
        doc = json.loads(FLOOR_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    cell = doc.get("vm3") or {}
    if cell.get("mde95") is None:
        return None
    return {"mde95": cell.get("mde95"), "sd": cell.get("sd"), "ci95": cell.get("ci95"),
            "delta": cell.get("delta"), "n_rows": (doc.get("point") or {}).get("vm3", {}).get("n_rows"),
            "estimator": "E_refit", "B_used": doc.get("B_used"), "seed": doc.get("seed"),
            "generated_at": doc.get("generated_at"),
            "source": f"data/{FLOOR_PATH.name} (tools/efv_headtohead_frame_lab.py vm3)",
            "measured_on": (doc.get("basis") or {}).get("efv"),
            "label": doc.get("label"),
            "vintage_matched_common_same_draws": doc.get("vintage_matched_common"),
            "paired_difference": doc.get("paired_difference")}


def _frame_doc(rows: list[dict], blk: dict, meta: dict, label: dict, *,
               holm: dict, e_refit: dict | None, frame: str = VM3_FRAME,
               primary: str = PRIMARY_COMPARISON) -> dict:
    prim = blk["deltas"][primary]["spearman"]
    if e_refit is not None:
        prim["mde95_e_refit"] = e_refit["mde95"]
        prim["mde95_e_refit_estimator"] = "E_refit, pooled Spearman, eFV v1 refit per draw"
        prim["mde95_e_refit_source"] = e_refit["source"]
    if frame == PANEL_FRAME:
        version, basis, rule = PANEL_FRAME, f"pooled_efv_{PANEL_FRAME}", SB.PIPELINE_PANEL_RULE
    else:
        version, basis, rule = SB.VM3_FRAME_VERSION, SB.VM3_BASIS, SB.VM3_RULE
    return {"frame_version": version, "basis": basis,
            "window": meta["window"], "rule": rule,
            "outcome": "career WAR to date",
            "contributor": f"career WAR >= {SB.CONTRIBUTOR_WAR}",
            "n": len(rows), "n_by_side": _n_side(rows),
            "n_players": len({c["key"] for c in rows}),
            "groups": sorted({c["group"] for c in rows}),
            "receipt": meta["receipt"], "dropped": meta["dropped"],
            "population_rows": meta["n_candidates"],
            "statistic": S.STAT_LABEL[S.PRIMARY],
            "raters": blk["raters"], "deltas": blk["deltas"],
            "secondary": _secondary(blk),
            "holm": holm,
            "e_refit_floor": e_refit,
            "resolvable": None,
            "verdict": prim["reading"],
            "note": _note(label, frame),
            "rows": [{"key": c["key"], "year": c["year"], "side": c["side"]} for c in rows]}


def _probe(frame: str, f: dict, primary: str, n_comparisons: int, label: dict) -> dict:
    prim = f["deltas"][primary]
    tag = f"{TASK}:{frame}.efv_vs_consensus"
    return {tag: {"tag": tag, "verdict": "READ", "ci95": prim["spearman"].get("ci95"),
                  "reason": (f"n {f['n']}; within delta {prim['spearman'].get('delta')}, "
                             f"pooled delta {prim['pooled'].get('delta')}; one frame read "
                             f"carrying {n_comparisons} comparisons by within, pooled and "
                             f"AUC; {_note(label, frame)}")}}


# ---------------------------------------------------------------------------
# the read

def run(*, check: bool = False, write: bool = True) -> dict:
    t0 = time.time()
    universe = SB._load_universe(SB.DATA_DIR)
    years = SB._resolved_years(universe, date.today().year)
    guards = _guards(years)
    label = _label()
    side_of = _side_of()
    rows, meta = build_vm3(universe, years, side_of)
    # the exporter's own census on the same pinned maps (counts first)
    census = SB.vm3_census(universe, years, meta.pop("_v2_pin"), meta.pop("_v2_rec"),
                           side_of)
    guards["vm_years_read"] = sorted({c["year"] for c in rows})
    if max(guards["vm_years_read"]) >= F.R_VM_FIRST_DEBUT_YEAR:
        raise F.ReservedFrameError(f"a reserved cohort was reached: {guards}")
    # the Pipeline-only panel (G3), on v1's pinned maps; never pooled with vm3
    panel_rows, panel_meta = build_panel(universe, side_of, meta.pop("_v1_pin"),
                                         meta.pop("_v1_rec"), {c["key"] for c in rows})
    panel_census = SB.pipeline_panel_census(universe)
    guards["panel_years_read"] = sorted({c["year"] for c in panel_rows})
    guards["panel_pooled_with_vm"] = bool({c["key"] for c in panel_rows}
                                          & {c["key"] for c in rows})
    if guards["panel_pooled_with_vm"]:
        raise ValueError("a panel row is also a vm3 row")
    counts = {"n": len(rows), "n_by_side": _n_side(rows), "receipt": meta["receipt"],
              "dropped": meta["dropped"], "census": census,
              "panel": {"n": len(panel_rows), "n_by_side": _n_side(panel_rows),
                        "receipt": panel_meta["receipt"], "dropped": panel_meta["dropped"],
                        "census": panel_census},
              "guards": guards, "label": label}
    if check:
        return {"check": True, **counts}
    e_refit = _e_refit_floor()
    blk = _frame_block(rows, VM3_RATERS_OUT, VM3_COMPARISONS)
    holm = _holm_block(rows, frame_key=SB.VM3_FRAME_KEY, basis=SB.VM3_BASIS)
    frame = _frame_doc(rows, blk, meta, label, holm=holm, e_refit=e_refit)
    probes = _probe(VM3_FRAME, frame, PRIMARY_COMPARISON, len(VM3_COMPARISONS), label)
    pblk = _frame_block(panel_rows, PANEL_RATERS_OUT, PANEL_COMPARISONS)
    pholm = _holm_block(panel_rows, frame_key=PANEL_FRAME, basis=f"pooled_efv_{PANEL_FRAME}")
    panel = _frame_doc(panel_rows, pblk, panel_meta, label, holm=pholm, e_refit=None,
                       frame=PANEL_FRAME, primary=PANEL_PRIMARY_COMPARISON)
    probes.update(_probe(PANEL_FRAME, panel, PANEL_PRIMARY_COMPARISON,
                         len(PANEL_COMPARISONS), label))
    code = {"commit": _commit(), "tool": "tools/efv_vm3_frame_read.py",
            "source_backtest_sha256": _sha(ROOT / "source_backtest.py"),
            "efv_v2_stat_sha256": _sha(ROOT / "efv_v2_stat.py")}
    gen = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    bootstrap = {"B": S.B_DEFAULT, "seed": S.SEED_DEFAULT, "estimator": "E_cond",
                 "unit": "player cluster"}
    sub = {"item": TASK, "role": "development", "generated_at": gen,
           "model_id": V2S.SERVED_MODEL_ID, "adjudicates": False, "selects": False,
           "exploratory": bool(label.get("exploratory")), "note": _note(label),
           "label": label, "code": code,
           "scored_object": {"efv_v2": ("efv_v2_serve.served_oos_scores(timing_pin=True): "
                                        "the vm2 headline's scored object"),
                             "efv_v1": "efv_model.oos_grades(timing_pin=True)"},
           "bootstrap": bootstrap,
           "frames": {VM3_FRAME: frame}}
    panel_sub = {"item": TASK, "role": "development", "generated_at": gen,
                 "model_id": "efv_v1", "adjudicates": False, "selects": False,
                 "exploratory": bool(label.get("exploratory")),
                 "note": _note(label, PANEL_FRAME),
                 "label": label, "code": code,
                 "scored_object": {"efv_v1": ("efv_model.oos_grades(timing_pin=True); V2 "
                                              "has no out-of-sample score before 2017")},
                 "consensus_is": "MLB Pipeline alone on these rows",
                 "never_pooled_with": ["vm2", "vm3"],
                 "bootstrap": bootstrap,
                 "frames": {PANEL_FRAME: panel}}
    doc = {"schema": 1, "task": TASK,
           "generated_at": gen,
           "produced_by": "tools/efv_vm3_frame_read.py",
           "plan": "EFV3_PLAN.md s3 (G2, G3); lane A E3-Q1 = A; vm2 stays the headline",
           "exploratory": bool(label.get("exploratory")),
           "label": label, "code": code,
           "statistic": {"primary": S.STAT_LABEL[S.PRIMARY],
                         "secondary": S.STAT_LABEL[S.SECONDARY],
                         "veto": S.STAT_LABEL["auc"],
                         "min_group_rows": S.MIN_GROUP_ROWS,
                         "group": "(side, debut year)",
                         "own_rows": "each source scored on the rows it graded",
                         "code": "efv_v2_stat.py"},
           "reserved_guard": guards,
           "census": {"vm3": census, "pipeline_panel": panel_census},
           VM3_FRAME: sub,
           PANEL_FRAME: panel_sub,
           "probes": probes, "n_probes": len(probes),
           "not_a_claim": ("development frames; vm2 stays the headline; the panel is "
                           "never pooled with vm2 or vm3; no served number reads this "
                           "file; copy keeps 'ties consensus'"),
           "elapsed_s": round(time.time() - t0, 1)}
    if write:
        tmp = OUT_PATH.with_name(OUT_PATH.name + ".tmp")
        tmp.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        tmp.replace(OUT_PATH)
        print("wrote", OUT_PATH)
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="build the frame and print the counts; no statistic, no write")
    ap.add_argument("--no-ledger", action="store_true",
                    help="write the artifact but do not update data/efv_progress.json")
    a = ap.parse_args(argv)
    if a.check:
        print(json.dumps(run(check=True, write=False), indent=1, default=str))
        return 0
    doc = run()
    f = doc[VM3_FRAME]["frames"][VM3_FRAME]
    for slot in ("spearman", "pooled", "auc"):
        d = f["deltas"][PRIMARY_COMPARISON][slot]
        print(f"vm3 {d['label']}: n {f['n']}, V2 {d['a']}, consensus {d['b']}, "
              f"delta {d['delta']} CI {d['ci95']} ({d['reading']})")
    if f.get("e_refit_floor"):
        print(f"vm3 E_refit floor (lab): mde95 {f['e_refit_floor']['mde95']}")
    pf = doc[PANEL_FRAME]["frames"][PANEL_FRAME]
    for slot in ("spearman", "pooled", "auc"):
        d = pf["deltas"][PANEL_PRIMARY_COMPARISON][slot]
        print(f"panel {d['label']}: n {pf['n']}, v1 {d['a']}, consensus {d['b']}, "
              f"delta {d['delta']} CI {d['ci95']} ({d['reading']})")
    if not a.no_ledger:
        import efv_progress
        print(efv_progress.summary_line(efv_progress.update_vm3(trigger="efv_change")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
