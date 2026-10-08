# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v3: Driver System V2 with a selected configuration (EFV3_W3_SELECT_CONFIRM;
owner EW2-6, 2026-10-08; docs/efv-v2/EFV_V3_BACKTEST.md).

DARK. EFV_V3_ON is False: nothing served reads this module's fit while it is off
(efv_v2_serve.production_models checks the flag and fits V2 as before). The flag
flips only through the ship task (EFV3_W3_SHIP, owner EW2-7), after the one
confirmation read on the reserved frames.

THE CONFIGURATION SPACE. A v3 configuration is V2 (efv_v2_model.fit_v2: the same
heads, the same DS-06 admission inside every fold, the same nested penalty rule, the
same DS-07 output map and the same P5 weights of data/efv_v2_assembly.json) with up to
four named changes, each a step of the forward selection the backtest document fixes
BEFORE any combined read:

    anchor   None (V2's u_c, the within-(side, V) consensus percentile) or one of the
             wave-2 anchor arms of efv_w2_anchor (an1_rel, an1_pl, an2_pos): u_c is
             replaced by u_c*, the heads refit on it (efv_v2_candidates.fit_mc2_anchor's
             construction, through fit_v3 below). The comparator stays served consensus
             and the displayed consensus FV never changes (an anchor is an eFV input).
    scale    per (side, head) a factor in SCALES applied to the P5 weight of that head
             (1.0 is V2). It re-weights what a fitted head adds; it refits nothing
             (DIAG item 2: the heads point the right way and V2 pushes them too hard).
    remove   per (side, head) drivers withheld from that head's candidate list (DIAG
             item 4 and 5: the drivers that subtract on the frozen label).
    add      per (side, head) wave-2 columns offered to that head beside the side's
             own candidates, under the unchanged admission rule (W2_COLUMNS).

The committed configuration lives in data/efv_v3_spec.json (SPEC_PATH), written by
tools/efv_v3_backtest.py --select and read by load_spec / spec_config. base_config()
is V2 exactly: fit_v3 at base_config() with no anchor reproduces fit_v2 and predict_v2
bit for bit (test_efv_v3.py), so every delta the backtest reports is the configuration
and nothing else.

RESERVED FRAMES. Nothing here reads a frame or a label. fit_v3 runs
efv_v2_candidates.guard_training_rows first: a reserved list vintage or a 2025+ year
in the training rows raises unless the committed gate's sha is handed in (the
confirmation read's own documented path; efv_vintage_frame.gate_sha_committed).

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): consensus enters as a within-group
percentile (or the anchor built from the sources' within percentiles) and as the value
multiset the grade is drawn from. Nothing here groups, counts or averages rows by
consensus-FV level; test_efv_v3.py scans this source.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import numpy as np

import efv_v2_candidates as C
import efv_v2_model as H
import efv_vintage_frame as F

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"

#: THE SWITCH. False: nothing served reads a v3 fit. Flips through EFV3_W3_SHIP only.
EFV_V3_ON = False
MODEL_ID = "efv_v3"
#: The committed configuration (tools/efv_v3_backtest.py --select writes it once).
SPEC_PATH = DATA_DIR / "efv_v3_spec.json"
#: The selection rule and the step log.
BACKTEST_DOC = "docs/efv-v2/EFV_V3_BACKTEST.md"
HEADS: tuple[str, ...] = ("skill", "timing")
#: The anchor arms a configuration may name (efv_w2_anchor.ARMS, by name).
ANCHORS: tuple[str, ...] = ("an1_rel", "an1_pl", "an2_pos")
#: The weight factors a (side, head) may take beside 1.0 (V2).
SCALES: tuple[float, ...] = (0.0, 0.25, 0.5)
#: Wave-2 columns a configuration may add, by arm name: the registered wave-2 arms
#: (efv_w2_milb.ARMS, efv_w2_scout.ARMS) whose development read admitted the column in
#: at least one fold on either frame (data/_labs/efv_w2/*.json); a column refused in
#: every fold is V2 itself there and cannot lift. Each is offered to the skill head
#: of its side, as its own module declares. `key` is the screening key the column
#: travels under on a row's v2 view (efv_v2_model.V2_SCREEN_PREFIX).
W2_COLUMNS: dict[str, dict] = {
    "w2m_k_hit": {"side": "hit", "head": "skill", "module": "efv_w2_milb", "arg": "k_hit"},
    "w2m_iso_hit": {"side": "hit", "head": "skill", "module": "efv_w2_milb", "arg": "iso_hit"},
    "w2m_air_hit": {"side": "hit", "head": "skill", "module": "efv_w2_milb", "arg": "air_hit"},
    "w2m_gb_pit": {"side": "pit", "head": "skill", "module": "efv_w2_milb", "arg": "gb_pit"},
    "w2s_brk_pit": {"side": "pit", "head": "skill", "module": "efv_w2_scout", "arg": "brk"},
    "w2s_cmd_pit": {"side": "pit", "head": "skill", "module": "efv_w2_scout", "arg": "cmd"},
    "w2s_pwr_present_hit": {"side": "hit", "head": "skill", "module": "efv_w2_scout",
                            "arg": "pwr_present"},
    "w2s_game_pwr_hit": {"side": "hit", "head": "skill", "module": "efv_w2_scout",
                         "arg": "game_pwr"},
    "w2s_posval_hit": {"side": "hit", "head": "skill", "module": "efv_w2_scout",
                       "arg": "posval"},
}
for _name, _spec in W2_COLUMNS.items():
    _spec["key"] = f"{H.V2_SCREEN_PREFIX}{_name}"


# ---------------------------------------------------------------------------
# configurations
# ---------------------------------------------------------------------------

def base_config() -> dict:
    """V2 exactly: no anchor, every factor 1.0, nothing removed, nothing added."""
    return {"anchor": None,
            "scale": {s: {h: 1.0 for h in HEADS} for s in F.SIDES},
            "remove": {s: {h: [] for h in HEADS} for s in F.SIDES},
            "add": {s: {h: [] for h in HEADS} for s in F.SIDES}}


def validate_config(cfg: dict) -> dict:
    """The configuration, checked: a known anchor or None, factors in SCALES or 1.0,
    removed drivers that are candidates of their head, added columns in W2_COLUMNS on
    their own side and head."""
    if cfg.get("anchor") not in (None,) + ANCHORS:
        raise ValueError(f"unknown anchor {cfg.get('anchor')!r}")
    for s in F.SIDES:
        for h in HEADS:
            k = float(cfg["scale"][s][h])
            if k != 1.0 and k not in SCALES:
                raise ValueError(f"scale {k} is not in {SCALES} for {s} {h}")
            cands = (H.skill_candidates(s) if h == "skill"
                     else H.timing_candidates(s, ids_outcome_blind=True, absence_admitted=True))
            for d in cfg["remove"][s][h]:
                if d not in cands:
                    raise ValueError(f"{d} is not a {s} {h} candidate")
            for a in cfg["add"][s][h]:
                spec = W2_COLUMNS.get(a)
                if spec is None or spec["side"] != s or spec["head"] != h:
                    raise ValueError(f"{a} is not an addable {s} {h} column")
    return cfg


def is_base(cfg: dict) -> bool:
    return (cfg.get("anchor") is None
            and all(float(cfg["scale"][s][h]) == 1.0 for s in F.SIDES for h in HEADS)
            and not any(cfg["remove"][s][h] or cfg["add"][s][h]
                        for s in F.SIDES for h in HEADS))


def config_side(cfg: dict, side: str) -> dict:
    """The part of a configuration that one side's fit reads."""
    return {"anchor": cfg.get("anchor"), "scale": dict(cfg["scale"][side]),
            "remove": {h: list(cfg["remove"][side][h]) for h in HEADS},
            "add": {h: list(cfg["add"][side][h]) for h in HEADS}}


def describe(cfg: dict) -> str:
    parts = []
    if cfg.get("anchor"):
        parts.append(f"anchor {cfg['anchor']}")
    for s in F.SIDES:
        for h in HEADS:
            k = float(cfg["scale"][s][h])
            if k != 1.0:
                parts.append(f"{s} {h} weight x {k:g}")
            for d in cfg["remove"][s][h]:
                parts.append(f"{s} {h} minus {d}")
            for a in cfg["add"][s][h]:
                parts.append(f"{s} {h} plus {a}")
    return "; ".join(parts) if parts else "V2 as assembled (no step)"


def head_candidates(cfg: dict, side: str, head: str, *, ids_outcome_blind: bool,
                    absence_admitted: bool) -> tuple[str, ...]:
    """The head's candidate list under the configuration: V2's list for the frame,
    minus the removed drivers, plus the added columns' keys (after the side's own)."""
    if head == "skill":
        base = H.skill_candidates(side)
    else:
        base = H.timing_candidates(side, ids_outcome_blind=ids_outcome_blind,
                                   absence_admitted=absence_admitted)
    rm = set(cfg["remove"][side][head])
    add = tuple(W2_COLUMNS[a]["key"] for a in cfg["add"][side][head])
    out = tuple(k for k in base if k not in rm) + add
    if H.V2_ABSENCE_KEY in out and head == "skill":
        raise ValueError("the absence flag may not enter the skill head (DS-04)")
    return out


# ---------------------------------------------------------------------------
# the fit (V2's heads, admission and penalty rule on the configured candidates)
# ---------------------------------------------------------------------------

def fit_v3(train: list[dict], side: str, *, frame: str, weights: dict[str, dict],
           cfg: dict, u_train=None, absent_ok: bool | None = None,
           gate_sha: str | None = None) -> dict:
    """v3 on one fold's training rows (each carrying `v2`, `fv`, `target`, `reached`,
    `decision_year`; an added column already on the v2 view). `u_train` is the anchor
    value per training row when the configuration names one (None otherwise; the
    caller builds it from the rows' grades through efv_w2_anchor.anchor_column).
    At base_config() with u_train None this is fit_v2's model, bit for bit."""
    if frame not in ("lv", "vm"):
        raise ValueError(f"frame must be lv or vm, got {frame!r}")
    validate_config(cfg)
    C.guard_training_rows(train, frame, gate_sha=gate_sha)
    if (u_train is None) != (cfg.get("anchor") is None):
        raise ValueError("an anchor configuration needs u_train, and only one does")
    if u_train is not None:
        u = np.asarray(u_train, dtype=np.float64)
        if u.size != len(train):
            raise ValueError("one anchor value per training row")
        rows = [dict(r, **{C.ANCHOR_KEY: float(u[i])}) for i, r in enumerate(train)]
    else:
        rows = train
    ob = frame == "lv"
    ab = ob and (H.absence_admitted(side) if absent_ok is None else bool(absent_ok))
    side_cfg = config_side(cfg, side)
    s_cands = head_candidates(cfg, side, "skill", ids_outcome_blind=ob, absence_admitted=ab)
    skill = None
    if s_cands:
        keys, checks = C._admitted_keys_a(rows, s_cands, target="u_y", has_block_only=True)
        if keys:
            def fit_s(tr, a):
                return C._skill_fit_g(tr, keys, a, C._v2_design(keys))
            a_s = C._select_alpha_g(rows, fit_s, C._skill_loss)
            skill = fit_s(rows, a_s)
            if skill is not None:
                skill.update({"side": side, "admission": checks, "candidates": list(s_cands),
                              "anchor": u_train is not None})
                skill["score_sd"] = C._score_sd(skill, H.skill_training_rows(rows))
    timing = None
    why = None
    if side == "pit" and not H.head_usable(skill):
        why = ("owner DS-Q2: no pitcher skill driver passed the admission rule in this "
               "fold, so pitchers take the consensus order")
    else:
        t_cands = head_candidates(cfg, side, "timing", ids_outcome_blind=ob,
                                  absence_admitted=ab)
        tkeys, tchecks = C._admitted_keys_a(rows, t_cands, target="reached",
                                            has_block_only=False)

        def fit_t(tr, a):
            return C._timing_fit_g(tr, tkeys, a, C._v2_design(tkeys))
        a_t = C._select_alpha_g(rows, fit_t, C._timing_loss)
        timing = fit_t(rows, a_t)
        if timing is not None:
            timing.update({"side": side, "admission": tchecks, "candidates": list(t_cands),
                           "ids_outcome_blind": bool(ob), "anchor": u_train is not None})
            timing["score_sd"] = C._score_sd(timing, rows)
    w = weights[side]
    w_s0 = float(w["w_skill"]) if H.head_usable(skill) else 0.0
    w_t0 = float(w["w_time"]) if H.head_usable(timing) else 0.0
    w_s = w_s0 * float(side_cfg["scale"]["skill"])
    w_t = w_t0 * float(side_cfg["scale"]["timing"])
    if why is None and w_s <= 0 and w_t <= 0:
        why = "no usable head carries a positive weight under the configuration"
    return {"model_id": MODEL_ID, "base_model_id": H.V2_ASSEMBLED_ID, "side": side,
            "frame": frame, "config": side_cfg, "skill": skill, "timing": timing,
            "w_skill": w_s, "w_time": w_t, "w_skill_unscaled": w_s0, "w_time_unscaled": w_t0,
            "consensus_only": w_s <= 0 and w_t <= 0, "consensus_only_reason": why,
            "war_map": H.fit_war_map(train), "n_train": len(train),
            "train_years": sorted({int(r["decision_year"]) for r in train})}


def parts_v3(model: dict, rows: list[dict], *, u_rows=None) -> dict:
    """The order's three parts per row, each independent of the weights: the anchor
    (u_rows, else the consensus percentile within decision year), e_skill and e_time
    in consensus-percentile equivalents (0 where the head is unusable). A caller
    re-weights these without a refit (the scale steps)."""
    if not rows:
        return {"u": np.zeros(0), "e_skill": np.zeros(0), "e_time": np.zeros(0)}
    groups = [int(r["decision_year"]) for r in rows]
    fv = np.array([r["fv"] for r in rows], dtype=np.float64)
    u = H.within_pct(fv, groups) if u_rows is None else np.asarray(u_rows, dtype=np.float64)
    if u.size != len(rows):
        raise ValueError("one anchor value per row")
    return {"u": u, "e_skill": C._e(model["skill"], rows), "e_time": C._e(model["timing"], rows)}


def order_index(parts: dict, w_skill: float, w_time: float) -> np.ndarray:
    return parts["u"] + float(w_skill) * parts["e_skill"] + float(w_time) * parts["e_time"]


def predict_v3(model: dict, rows: list[dict], *, u_rows=None) -> list[dict]:
    """predict_v2's output under the configuration (efv_v2_candidates._predict with the
    anchor when the configuration names one). At base_config() this is predict_v2."""
    if (u_rows is None) != (model.get("config", {}).get("anchor") is None):
        raise ValueError("an anchor model needs u_rows, and only one does")
    u = None if u_rows is None else np.asarray(u_rows, dtype=np.float64)
    return C._predict(model, rows, u_c=u)


# ---------------------------------------------------------------------------
# the committed spec and the dark production fit
# ---------------------------------------------------------------------------

def load_spec(path: Path | None = None) -> dict:
    p = SPEC_PATH if path is None else Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def spec_config(spec: dict | None = None) -> dict:
    """The committed configuration, validated."""
    doc = load_spec() if spec is None else spec
    return validate_config(copy.deepcopy(doc["config"]))


def production_models(*, weights: dict | None = None) -> dict[str, dict]:
    """The dark production fit: v3 at the committed configuration on the v1 matrices,
    decision years before the R-VM cohort (efv_v2_serve.production_models' rows). Read
    only while EFV_V3_ON is True. A configuration that names an anchor needs the live
    rows' per-source grades, which the ship task wires; until then it raises rather
    than serving a half-built anchor."""
    cfg = spec_config()
    if cfg.get("anchor"):
        raise NotImplementedError("the live path has no per-source grades for the anchor "
                                  "yet (EFV3_W3_SHIP)")
    if cfg["add"]["hit"]["skill"] or cfg["add"]["pit"]["skill"]:
        raise NotImplementedError("the live path has no wave-2 column builder yet "
                                  "(EFV3_W3_SHIP)")
    w = H.load_weights() if weights is None else weights
    out = {}
    for side in F.SIDES:
        train = [r for r in H.matrix_training_rows(side)
                 if int(r["decision_year"]) < F.R_VM_FIRST_DEBUT_YEAR]
        m = fit_v3(train, side, frame="vm", weights=w, cfg=cfg)
        m["war_map_6yr"] = H.fit_war_map(train)
        out[side] = m
    return out


def _is_finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))
