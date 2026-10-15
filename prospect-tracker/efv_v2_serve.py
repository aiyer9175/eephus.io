# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Serving eFV V2 (DS-02 in docs/efv-v2/DRIVER_SYSTEM_V2.md, owner answer DS-Q1).

THE DEFECT THIS CLOSES (bug B2). Until this step the PROSPX board sorted on eFV v1's
model leg through the outcome map, the Source Comparison page scored v1's guarded blend,
surplus priced off a third number (a quantile remap of the blend) and the odds read a
fourth (the realized-implied grade). Four objects, one name.

ONE ORDER INDEX. Every served eFV number on a consensus-graded prospect now derives from
V2's order index (efv_v2_model.predict_v2):

    order_idx   u_c + w_skill * e_skill + w_time * e_time, inside (side, list year)
    grade       the consensus FV value of the group at order_idx's rank (output_map):
                THE board number (storage.BOARD_GRADE_FIELD, still the field
                `xfv_grade`), the sort key, the displayed grade and the pricing grade
    sort key    order_idx itself (board_sort_key), so an exact grade tie orders by the
                model rather than by name
    odds        value_framework.p_bucket_given_fv at the grade, the same table the
                consensus column reads at the consensus FV. DS-17: the V2 P(bust) head
                did not beat consensus alone on the development frame, so the served
                arm is "consensus" (efv_v2_model.pbust_serving_arm) and the odds are
                the consensus table read at the eFV grade
    dollars     value_framework priced at the grade (efv_score._reprice_surplus_on_display)
    WAR         the continuous consensus-FV-to-six-season-WAR line of the v1 matrices,
                evaluated at the grade (pricing context only, never ranked)

The Source Comparison page scores the same object out of sample: served_oos_scores()
returns, per matrix row, the grade a forward-chained V2 fit serves with the order index
breaking exact ties exactly as the board does.

WHO V2 GRADES. Every active prospect with a real consensus grade (a source published an
FV), with or without a MiLB record: a row without a block takes the has-block training
means (DS-04). Rows whose consensus is the last-resort constant (anchor_constant_only)
have no consensus to reorder, so V2 abstains on them and they keep the production-only
provisional grade (efv_ungraded), as 2,480 of them already did under v1.

THE PRODUCTION FIT. The next fold of the procedure the Source Comparison headline scores:
fit_v2 on the v1 matrices (frame "vm"), every decision year before the R-VM cohort
(efv_vintage_frame.R_VM_FIRST_DEBUT_YEAR), so no 2025+ debut is read and no reserved list
vintage is touched. Weights are the registered DS-08 weights (data/efv_v2_assembly.json);
admission runs inside the fit (DS-06); pitchers take the consensus order unless a pitcher
skill driver is admitted (owner DS-Q2), and on this fit none is. The live board is the
group (side, efv_dataset.CURRENT_SEASON). The fit reads the training labels; it computes
no statistic against any outcome.

WHY NOT THE LIST-VINTAGE FIT. V2 was also fitted on the list-vintage frame for the DS-16
development read. Serving that fit would re-open bug B2 from the other side: the page
scores the vintage-matched procedure, and the list-vintage fit reorders hitters by the hit
tool about twice as hard and admits the pitcher K rate, so the board would again serve an
object the page does not score. The choice is recorded as an owner question in the
DS_F_serve_v2 report.

CHIPS. The v1 driver chips are gone on both sides (DS-Q2 scraps the pitcher block; the
hitter chips described v1's ridge). A V2 row carries one chip per admitted driver that
moves its order index by at least CHIP_FLOOR_PCT percentile points, in those units, and
one labelled chip per DS-11 overlay that fires (efv_overlays.overlay_chips: injury, age,
reliever ceiling, Statcast+, the Statcast lean), which states the condition and moves
nothing.

FLAG. SERVE_EFV_V2 (env EEPHUS_SERVE_EFV_V2 "0"/"1" overrides it for a lab run). Landed
2026-09-25, before the fWAR label epoch's step A (docs/efv-2026-09-17/
FWAR_LABEL_EPOCH_GATE.md clause (l)); storage.BOARD_RANK_BASIS_EPOCH moved with it.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): consensus enters as a within-group
percentile and as the value multiset the grade is drawn from. Nothing here groups,
counts or averages rows by consensus-FV level.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"

log = logging.getLogger(__name__)

#: THE SWITCH. True serves V2 as the board order, grade, pricing, odds and the Source
#: Comparison scored object; False restores eFV v1 byte for byte.
SERVE_EFV_V2 = True
#: The registry row and the model id the Source Comparison ledger records.
SERVED_MODEL_ID = "efv_v2"
#: grade_basis on a V2-graded row.
GRADE_BASIS = "efv_v2"
#: A driver chip is shown when it moves the order index by at least this many
#: percentile points of the row's (side, list year) group.
CHIP_FLOOR_PCT = 0.5
#: Order-only tie break inside an exact grade tie on the scored object (served_score).
#: The distinct consensus values in the matrices differ by far more than
#: TIE_EPS * max|order_idx|, which served_score asserts on every call.
TIE_EPS = 1e-6
#: Per-driver chip labels. Timing drivers say they are about arrival, not talent.
CHIP_LABELS = {
    "obp_rel": "On-base rate vs level",
    "contact": "Contact (strikeout rate vs level)",
    "tool_hit": "Hit tool grade",
    "tool_speed": "Speed grade",
    "is_college": "College draftee",
    "level_rank": "Level reached",
    "k_rel": "Strikeout rate vs level",
    "bmi": "Body mass index",
    "pl_rev": "Pipeline revision",
    "age_rel_level": "Age for level (arrival)",
    "on_40man": "On the 40-man roster (arrival)",
    "nov_add": "November 40-man add (arrival)",
    "milb_absent": "No MiLB record yet (arrival)",
}

_MODELS: dict | None = None


def enabled() -> bool:
    """Is V2 the served eFV? The env override exists for lab toggling only."""
    env = os.environ.get("EEPHUS_SERVE_EFV_V2")
    if env in ("0", "1"):
        return env == "1"
    return bool(SERVE_EFV_V2)


def live_year() -> int:
    import efv_dataset as D
    return int(D.CURRENT_SEASON)


# ---------------------------------------------------------------------------
# the production fit
# ---------------------------------------------------------------------------

def production_models(*, refresh: bool = False) -> dict[str, dict]:
    """{side: fitted V2 model} on the v1 matrices, decision years before the R-VM cohort
    (memoized per process). Each model also carries `war_map_6yr`, the continuous
    consensus-FV-to-six-season-WAR line on the same rows (pricing context only)."""
    global _MODELS
    if _MODELS is not None and not refresh:
        return _MODELS
    import efv_v2_model as H
    import efv_v3 as V3
    import efv_v4 as V4
    import efv5_group_drivers as V5
    import efv_vintage_frame as F
    weights = H.load_weights()
    if V5.EFV_V5_ON:
        # DARK (efv5_group_drivers.EFV_V5_ON is False): eFV v5 group drivers at the
        # committed configuration; the ship rule of docs/efv-v2/EFV_V5_BACKTEST.md flips it.
        _MODELS = V5.production_models(weights=weights)
        return _MODELS
    if V4.EFV_V4_ON:
        # DARK (efv_v4.EFV_V4_ON is False): eFV v4 at its committed configuration on the
        # same rows; the ship rule of docs/efv-v2/EFV_V4_BACKTEST.md flips the flag.
        _MODELS = V4.production_models(weights=weights)
        return _MODELS
    if V3.EFV_V3_ON:
        # DARK (efv_v3.EFV_V3_ON is False): the selected eFV v3 configuration fitted on
        # the same rows; EFV3_W3_SHIP flips the flag after the confirmation read.
        _MODELS = V3.production_models(weights=weights)
        return _MODELS
    out = {}
    for side in F.SIDES:
        train = [r for r in H.matrix_training_rows(side)
                 if int(r["decision_year"]) < F.R_VM_FIRST_DEBUT_YEAR]
        m = H.fit_v2(train, side, frame="vm", weights=weights)
        m["war_map_6yr"] = H.fit_war_map(train)
        m["train_years"] = sorted({int(r["decision_year"]) for r in train})
        out[side] = m
    _MODELS = out
    return out


def _head_receipt(head: dict | None) -> dict | None:
    if head is None:
        return None
    return {"keys": list(head.get("keys") or []),
            "alpha": (None if head.get("alpha") is None or math.isinf(head["alpha"])
                      else float(head["alpha"])),
            "b_uc": round(float(head.get("b_uc", 0.0)), 6),
            "beta": [round(float(b), 6) for b in head.get("beta") or []],
            "n_train": head.get("n_train"),
            "admission": {k: {"admitted": v.get("admitted"), "sign": v.get("sign"),
                              "mean_abs_t": v.get("mean_abs_t"),
                              "per_vintage_signs": v.get("per_vintage_signs")}
                          for k, v in (head.get("admission") or {}).items()}}


def model_receipt(models: dict[str, dict] | None = None) -> dict:
    """What is served, per side: weights, admitted keys, penalties, slopes, the training
    vintages. Written into data/xfv.json meta so a reader can reproduce a grade."""
    models = production_models() if models is None else models
    out = {}
    for side, m in models.items():
        out[side] = {"w_skill": m["w_skill"], "w_time": m["w_time"],
                     "consensus_only": m["consensus_only"],
                     "consensus_only_reason": m.get("consensus_only_reason"),
                     "skill": _head_receipt(m.get("skill")),
                     "timing": _head_receipt(m.get("timing")),
                     "n_train": m["n_train"], "train_years": m.get("train_years"),
                     "frame": m.get("frame"),
                     "war_map_6yr": m.get("war_map_6yr")}
    return out


def fingerprint_term() -> str:
    """The board fingerprint's `served=` term: which eFV serves, and for V2 the hash of
    the registered weights and the serving constants, so a re-registration or a change
    to who V2 grades trips the pinned-fingerprint check."""
    if not enabled():
        return "efv_v1"
    try:
        import efv_v2_model as H
        w = H.load_weights()
        spec = json.dumps({"w": w, "chip_floor": CHIP_FLOOR_PCT, "tie": TIE_EPS,
                           "basis": GRADE_BASIS, "skill": {s: list(H.skill_candidates(s))
                                                           for s in ("hit", "pit")},
                           "w_max": H.W_MAX, "rule_last": H.RULE_LAST_YEAR,
                           "abstain": "anchor_constant_only"}, sort_keys=True)
        return f"{SERVED_MODEL_ID}@{hashlib.sha256(spec.encode()).hexdigest()[:8]}"
    except Exception:                                             # noqa: BLE001
        return "unavailable"


# ---------------------------------------------------------------------------
# live rows
# ---------------------------------------------------------------------------

def gradeable(r: dict) -> bool:
    """A live row V2 grades: a real consensus grade (not the constant anchor)."""
    if r.get("anchor_constant_only"):
        return False
    try:
        return math.isfinite(float(r.get("consensus_fv_raw")))
    except (TypeError, ValueError):
        return False


def live_rows(side: str, live: list[dict], *, today: str | None = None) -> list[dict]:
    """The live board as V2 rows for one side: v1's feature view of the live-matrix row,
    the V2 view (DS-04 missingness), BMI as of today (the only sidecar the vm-frame
    candidates read; protection status is never a vm-frame input, bug B4), and the list
    year as the group."""
    import efv_drivers as DRV
    import efv_model as V1
    import efv_v2_model as H
    V = live_year()
    today = today or date.today().isoformat()
    panel = DRV.load_bio_panel()
    out = []
    for r in live:
        if not gradeable(r):
            continue
        feats = V1._vec(r, side)
        extra = {"bmi": DRV.bmi_asof(r["player_key"], today, panel)}
        out.append({"player_key": r["player_key"], "decision_year": V,
                    "fv": float(r["consensus_fv_raw"]), "feats": feats, "extra": extra,
                    "v2": H.v2_row(feats, extra), "frame": "live",
                    "has_milb": bool(r.get("milb"))})
    return out


def _chip_parts(model: dict, rows: list[dict]) -> list[dict[str, float]]:
    """Per row {driver: contribution to order_idx, in percentile points}."""
    import efv_v2_model as H
    out = [dict() for _ in rows]
    for head_name, w in (("skill", model["w_skill"]), ("timing", model["w_time"])):
        head = model.get(head_name)
        if not (w > 0 and H.head_usable(head)):
            continue
        X = (H.skill_design(rows, head) if head_name == "skill"
             else H._v2_x(rows, head["keys"], head["means"]))
        Z = (X - np.asarray(head["mu"])) / np.asarray(head["sd"])
        contrib = Z * np.asarray(head["beta"])[None, :] * (w / head["b_uc"]) * 100.0
        for i in range(len(rows)):
            for j, k in enumerate(head["keys"]):
                out[i][k] = out[i].get(k, 0.0) + float(contrib[i, j])
    return out


def driver_chips(parts: dict[str, float]) -> list[dict]:
    """The chips for one row: every driver moving its order index by at least
    CHIP_FLOOR_PCT percentile points, largest first."""
    chips = [{"label": CHIP_LABELS.get(k, k), "driver": k,
              "dir": "up" if v > 0 else "down", "mag": round(abs(v), 2),
              "unit": "percentile points"}
             for k, v in parts.items() if abs(v) >= CHIP_FLOOR_PCT]
    return sorted(chips, key=lambda c: -c["mag"])


def score_live(side: str, live: list[dict], *, models: dict | None = None,
               today: str | None = None) -> dict[str, dict]:
    """{player_key: V2 prediction} for one side's live board: u_c, e_skill, e_time,
    order_idx, grade, the six-season WAR at the grade and the driver chips."""
    import efv_v2_model as H
    models = production_models() if models is None else models
    model = models[side]
    rows = live_rows(side, live, today=today)
    preds = H.predict_v2(model, rows)
    parts = _chip_parts(model, rows)
    grades = np.array([p["efv_grade"] for p in preds], dtype=np.float64)
    war6 = H.war_at(model.get("war_map_6yr"), grades) if preds else np.array([])
    # the row's place in its side's order by V2 and by consensus (1 = best; a consensus
    # tie takes its best place), so the card can say who passed whom
    n = len(preds)
    by_order = sorted(range(n), key=lambda i: (-preds[i]["order_idx"], preds[i]["player_key"]))
    o_rank = {i: pos + 1 for pos, i in enumerate(by_order)}
    fvs = [float(r["fv"]) for r in rows]
    c_rank = {i: 1 + sum(1 for v in fvs if v > fvs[i]) for i in range(n)}
    out = {}
    for i, (r, p) in enumerate(zip(rows, preds)):
        out[r["player_key"]] = dict(p, efv_war_6yr=float(war6[i]),
                                    order_rank=o_rank[i], consensus_rank=c_rank[i],
                                    group_n=n,
                                    has_block=bool(r["v2"]["has_block"]),
                                    has_milb=r["has_milb"],
                                    chips=driver_chips(parts[i]))
    return out


class HistoryGrader:
    """The FV-history chart's V2 series, as a retrospective on today's board: a past
    snapshot's consensus is placed inside today's (side, list year) consensus values
    (u_c, ties averaged as within_pct does), its drivers are read off that snapshot's
    features by the served heads, and the order index is mapped onto today's
    order-index-to-grade line (linear between today's rows, flat past either end). A
    player's latest snapshot therefore lands on his served grade, and the series moves
    only when his consensus or his drivers moved. It is today's model scoring old
    snapshots, as the v1 series always was, not the grade that would have shown then."""

    def __init__(self, side: str, live: list[dict], *, models: dict | None = None):
        import efv_v2_model as H
        self.side = side
        self.model = (production_models() if models is None else models)[side]
        preds = score_live(side, live, models={side: self.model} if models is None
                           else models)
        self.keys = set(preds)
        cons = {r["player_key"]: float(r["consensus_fv_raw"]) for r in live
                if r.get("player_key") in preds}
        self.ref = np.sort(np.array(list(cons.values()), dtype=np.float64))
        pairs = sorted((p["order_idx"], p["efv_grade"]) for p in preds.values())
        xs, ys = [], []
        for x, y in pairs:
            if xs and x == xs[-1]:
                continue
            xs.append(x)
            ys.append(y)
        self.xs, self.ys = np.array(xs), np.array(ys)
        self._H = H

    def u_c(self, fv: float) -> float:
        n = self.ref.size
        lo = int(np.searchsorted(self.ref, fv, side="left"))
        hi = int(np.searchsorted(self.ref, fv, side="right"))
        eq = hi - lo
        rank = lo + (eq + 1) / 2.0 if eq else lo + 0.5
        return float(rank / n) if n else 0.5

    def grades(self, rows: list[dict]) -> list[float]:
        """rows: [{"fv", "feats", "extra"}] for one player's snapshots."""
        if not rows or self.xs.size == 0:
            return []
        H = self._H
        v2rows = [{"v2": H.v2_row(r["feats"], r.get("extra"))} for r in rows]
        m = self.model
        es = H.e_skill(m["skill"], v2rows) if m["w_skill"] > 0 else np.zeros(len(rows))
        et = H.e_time(m["timing"], v2rows) if m["w_time"] > 0 else np.zeros(len(rows))
        order = (np.array([self.u_c(float(r["fv"])) for r in rows])
                 + m["w_skill"] * es + m["w_time"] * et)
        return np.interp(order, self.xs, self.ys).tolist()


# ---------------------------------------------------------------------------
# the scored object, out of sample (Source Comparison)
# ---------------------------------------------------------------------------

def served_score(grades, order_idx) -> list[float]:
    """The board's ordering as one number: the grade, with the order index breaking an
    exact grade tie (the board's board_sort_key rule). Raises when the tie break could
    cross a gap between two distinct grades."""
    g = np.asarray(grades, dtype=np.float64)
    o = np.asarray(order_idx, dtype=np.float64)
    if g.size == 0:
        return []
    span = TIE_EPS * float(np.max(np.abs(o)))
    u = np.unique(g)
    if u.size > 1 and float(np.min(np.diff(u))) <= 2.0 * span:
        raise ValueError("served_score tie break would cross a gap between grades")
    return (g + TIE_EPS * o).tolist()


def served_oos_scores(*, timing_pin: bool = False, receipts: dict | None = None,
                      years=None) -> dict[str, float]:
    """{player_key: served score} for every v1 matrix row V2 can score out of sample:
    each decision year from V2_FIRST_SCORED_YEAR, before the R-VM cohort, by a V2 fit on
    earlier matrix rows (efv_v2_model.v2_vm_scores, the DS-16 path). timing_pin=True
    reads each debuted row's consensus at the raters' preseason point (vm2). receipts,
    when a dict, gets the v1-shaped timing receipt per pinned row."""
    import efv_model as V1
    import efv_v2_model as H
    import efv_vintage_frame as F
    weights = H.load_weights()
    ys = [y for y in (V1.SCORED_YEARS if years is None else years)
          if H.V2_FIRST_SCORED_YEAR <= y < F.R_VM_FIRST_DEBUT_YEAR]
    out: dict[str, float] = {}
    for side in F.SIDES:
        mine: dict = {}
        res = H.v2_vm_scores(side, weights=weights, years=ys, timing_pin=timing_pin,
                             receipts=mine if timing_pin else None)
        for yr in sorted(res):
            rows = res[yr]["rows"]
            sc = served_score([p["efv_grade"] for p in rows],
                              [p["order_idx"] for p in rows])
            for p, s in zip(rows, sc):
                out[p["player_key"]] = float(s)
        if timing_pin and receipts is not None:
            raw = json.loads(H._matrix_path(side).read_text(encoding="utf-8"))
            by = {r["player_key"]: r for r in raw}
            for k, rec in mine.items():
                m = by.get(k) or {}
                receipts[k] = dict(rec, matrix_asof_date=m.get("asof_date"),
                                   matrix_consensus_fv_raw=m.get("consensus_fv_raw"))
    return out


# ---------------------------------------------------------------------------
# the claim the board and card print
# ---------------------------------------------------------------------------

def served_claim(progress: dict | None = None, *, model_id: str = SERVED_MODEL_ID) -> dict:
    """What the board may say about the served eFV against PROSPX consensus, derived from
    data/efv_progress.json and nothing else (owner DS-Q1: "ties consensus" until a
    reserved read says otherwise).

    Precedence: the latest reserved-frame look row for the served model decides; with
    none, the latest headline-frame row decides, and it can only ever read "ties" (CI95
    spans zero, not resolvable) or "trails" (resolvable and below); a lead on a spent
    frame is not a reserved read, so it reads "ties". With no row for the served model,
    the claim is "not yet scored"."""
    if progress is None:
        p = DATA_DIR / "efv_progress.json"
        try:
            progress = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            progress = {}
    rows = [r for r in (progress or {}).get("rows") or []
            if (r.get("model_id") or "") == model_id]
    head = (progress or {}).get("headline_frame") or "vm"
    looks = [r for r in rows if r.get("role") == "reserved" and r.get("trigger") == "look"]
    heads = [r for r in rows if r.get("frame") == head]
    row = (looks or heads or [None])[-1]
    if row is None:
        return {"word": "not yet scored", "model_id": model_id,
                "text": "Not yet scored against PROSPX consensus.",
                "source": "data/efv_progress.json"}
    leg = ((row.get("deltas") or {}).get("vs_prospx_consensus") or {}).get("spearman") or {}
    d, ci = leg.get("delta"), leg.get("ci95")
    res = row.get("resolvable")
    reserved = row in looks
    if res and d is not None and d < 0:
        word = "trails"
    elif res and d is not None and d > 0 and reserved:
        word = "leads"
    else:
        word = "ties"
    frame = ((progress or {}).get("frames") or {}).get(row.get("frame"), {}).get(
        "label") or row.get("frame")
    ci_txt = (f", CI95 {ci[0]:+.3f} to {ci[1]:+.3f}" if isinstance(ci, list) and len(ci) == 2
              and all(isinstance(v, (int, float)) for v in ci) else "")
    d_txt = f"{d:+.4f}" if isinstance(d, (int, float)) else "n/a"
    text = (f"{'Ties' if word == 'ties' else word.capitalize()} PROSPX consensus: "
            f"Spearman difference {d_txt}{ci_txt} on the {frame.lower()} frame "
            f"(n {row.get('n')}, {row.get('date')}).")
    return {"word": word, "model_id": model_id, "frame": row.get("frame"),
            "frame_label": frame, "delta": d, "ci95": ci, "n": row.get("n"),
            "resolvable": res, "date": row.get("date"), "run_id": row.get("run_id"),
            "reserved_read": reserved, "text": text,
            "source": "data/efv_progress.json"}
