# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The PJ-C holdout look (task PJ_5_COMPONENT_LOOK): the one read of the
component heads on the HOLDOUT frame, docs/PROJ_COMPONENTS_GATE.md sections
3 to 5; LANE_A 3.1.

WHAT RUNS, in this order:
  0. stdout and stderr are teed into the output directory before anything
     else runs (gate section 5, 'How', step 2);
  1. the whole reporting path is dry-run on the PJ_3 fixtures with nulls
     (the frame of test_proj_components_scorer.py's dry-run test, scored
     through the same verdict, tripwire and artifact code this look uses);
     the dry run writes only under the output directory;
  2. the frozen params are checked against the gate's recorded sha256, and
     the artifact is checked for a prior 'holdout' block (the look runs once);
  3. bases 2022 to 2024 are assembled exactly as the DEV driver assembled
     DEV (tools/proj_components_dev.Dev: the engine fitted point in time at
     B - 1, the aging_v3 component curves fitted at B - 1, the held constants
     of B - 1), the heads are built under the frozen params and scored by
     proj_eval.run_components(look=True) on the registered cells (2022, h1-h4),
     (2023, h1-h3), (2024, h1-h2) against both comparators, seed 20261124,
     B 1000, VIF 1.8;
  4. the Position Fit READ-EXCLUDED split (gate 4.7), the H0 / P0 exposure
     test (gate 4.3), the deterministic heads' receipts (gate 4.2) and the gap
     tripwire (gate section 2: served war minus component WAR at h1, the
     served engine's point-in-time paths, never a label);
  5. the verdict per head by the registered rule (gate 4.5 and 4.6), then the
     artifact data/proj_components_eval.json (only with --write).

An exception after scoring began STOPs: OWNER_QUESTION.md with the traceback
is written to the output directory, nothing is written under data/, and the
look is not rerun by this tool.

THE VERDICT RULE AS APPLIED (fixed here before the holdout was read):
  UNDERPOWERED  a head's DEV MDE95 (gate 4.5; per comparator, from
                model/proj_components/dev_receipt.json) exceeds 10% of the
                head's DEV NAIVE MAE against either comparator: the literal
                text of 4.5. The per-comparator reading PJ_4's receipt flagged
                (MDE95 against each comparator's own MAE) is published beside
                it; it decides nothing.
  PASS          h1 pooled ub95 < 0 against NAIVE and against IMPLICIT; h2 and
                h3 pooled ub95 below +10% of that comparator's MAE at that
                horizon, both; star-slice h1 ub95 below +10% of the
                comparator's star MAE, both. A null anywhere fails the check
                (a null is a finding; nothing ships on it).
  FAIL          otherwise.
  Exposure (H0 PA, P0 IP): PASS iff h1 pooled ub95 < 0 against prior_season
  and against w543; otherwise FAIL.

Usage:
    python tools/proj_components_look.py --out DIR            # dry run + look, nothing under data/
    python tools/proj_components_look.py --out DIR --write    # also writes data/proj_components_eval.json
    python tools/proj_components_look.py --out DIR --dry-run-only
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import logging
import pickle
import re
import subprocess
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

log = logging.getLogger("proj_components_look")

SEED = 20261124
VIF = 1.8
B_DEFAULT = 1000
HOLDOUT_BASES = (2022, 2023, 2024)
HOLDOUT_CELLS = [(2022, 1), (2022, 2), (2022, 3), (2022, 4),
                 (2023, 1), (2023, 2), (2023, 3),
                 (2024, 1), (2024, 2)]
VERDICT_HEADS = ("bsr", "fld_pos", "gmli_relief", "ra9_gap")
RECEIPT_HEADS = ("batting", "league", "replacement")
EXPOSURE_HEADS = ("pa", "ip")
ALL_HEADS = VERDICT_HEADS + RECEIPT_HEADS + EXPOSURE_HEADS
VERDICT_COMPARATORS = ("naive", "implicit")
EXPOSURE_COMPARATORS = ("prior_season", "w543")
HEAD_LABELS = {"bsr": "H3 BsR", "fld_pos": "H4 + H5 Fld + Pos",
               "gmli_relief": "P4 gmLI (through the relief runs it multiplies)",
               "ra9_gap": "P5 RA9 gap", "pa": "H0 PA (exposure test)",
               "ip": "P0 IP (exposure test)"}
GATE_DOC = ROOT / "docs" / "PROJ_COMPONENTS_GATE.md"
ARTIFACT_REL = "data/proj_components_eval.json"
GAP_TRIPWIRE_WAR = 0.30
TEN_PCT = 0.10
AGE_BANDS = ((None, 26, "<=26"), (27, 30, "27-30"), (31, 34, "31-34"), (35, None, "35+"))
# Position Fit's conversion test as registered (positional_fit.conversion_accuracy)
MOVER_FIRST, MOVER_MIN_INN, MOVER_PRIOR_CAP, MOVER_MIN_TRAIN = 2017, 200.0, 50.0, 100


class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)
        return len(s)

    def flush(self):
        for st in self.streams:
            st.flush()


def _utc_stamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def recorded_params_sha() -> str:
    doc = GATE_DOC.read_text(encoding="utf-8")
    found = re.findall(r"DEV frozen \d{4}-\d{2}-\d{2} at [0-9a-f]{7,40}, params sha256 ([0-9a-f]{64})", doc)
    if not found:
        raise RuntimeError("the gate's section 9 carries no DEV freeze record")
    return found[-1]


def registration_commit() -> str | None:
    try:
        out = subprocess.run(["git", "log", "--format=%h", "--diff-filter=A", "--",
                              str(GATE_DOC.relative_to(ROOT.parent)).replace("\\", "/")],
                             cwd=ROOT.parent, capture_output=True, text=True, check=True).stdout
        lines = [x.strip() for x in out.splitlines() if x.strip()]
        return lines[-1] if lines else None
    except (OSError, subprocess.CalledProcessError):
        return None


def _lt(a, b) -> bool | None:
    """a < b, None when either is None (a null never passes)."""
    if a is None or b is None:
        return None
    return float(a) < float(b)


# --------------------------------------------------------------------------
# Verdicts (gate 4.3, 4.5, 4.6)
# --------------------------------------------------------------------------

def head_verdict(head: str, hz: dict, dev_mde: dict | None) -> dict:
    """PASS, FAIL or UNDERPOWERED for one verdict head from its HOLDOUT
    horizons block and the DEV MDE95 table. Every check is recorded with the
    numbers it read; a None anywhere is a failed check."""
    checks: dict = {}
    reasons: list[str] = []
    dev_row = ((dev_mde or {}).get(head) or {}).get("comparators") or {}
    naive_mae_dev = (dev_row.get("naive") or {}).get("mae")
    bar = None if naive_mae_dev is None else TEN_PCT * float(naive_mae_dev)
    underpowered = []
    for c in VERDICT_COMPARATORS:
        m = (dev_row.get(c) or {}).get("mde95")
        own = (dev_row.get(c) or {}).get("mae")
        exceeds = None if (m is None or bar is None) else float(m) > bar
        checks[f"dev_mde95_vs_{c}"] = {
            "mde95": m, "bar_10pct_of_dev_naive_mae": None if bar is None else round(bar, 5),
            "exceeds": exceeds,
            "per_comparator_reading": {"own_mae": own,
                                       "exceeds_10pct_of_own_mae": (None if m is None or own is None
                                                                    else float(m) > TEN_PCT * float(own))}}
        if exceeds is None or exceeds:
            underpowered.append(c)
    h1 = hz.get(1) or hz.get("1") or {}
    for c in VERDICT_COMPARATORS:
        k = (h1.get("comparators") or {}).get(c) or {}
        pooled, star = k.get("pooled") or {}, k.get("star") or {}
        ok = _lt(pooled.get("ub95"), 0.0)
        checks[f"h1_ub95_below_0_vs_{c}"] = {"delta": pooled.get("delta"), "ub95": pooled.get("ub95"),
                                             "mde95": pooled.get("mde95"), "n_players": pooled.get("n_players"),
                                             "ok": ok}
        if not ok:
            reasons.append(f"h1 ub95 vs {c} not below 0 ({pooled.get('ub95')})")
        bar_star = None if k.get("mae_star") is None else TEN_PCT * float(k["mae_star"])
        ok_s = _lt(star.get("ub95"), bar_star)
        checks[f"star_h1_ub95_below_10pct_vs_{c}"] = {"delta": star.get("delta"), "ub95": star.get("ub95"),
                                                      "bar": None if bar_star is None else round(bar_star, 5),
                                                      "n_players": star.get("n_players"), "ok": ok_s}
        if not ok_s:
            reasons.append(f"star h1 ub95 vs {c} not below +10% of its star MAE ({star.get('ub95')} vs {bar_star})")
    for h in (2, 3):
        cell = hz.get(h) or hz.get(str(h)) or {}
        for c in VERDICT_COMPARATORS:
            k = (cell.get("comparators") or {}).get(c) or {}
            pooled = k.get("pooled") or {}
            bar_h = None if k.get("mae") is None else TEN_PCT * float(k["mae"])
            ok_h = _lt(pooled.get("ub95"), bar_h)
            checks[f"h{h}_ub95_below_10pct_vs_{c}"] = {"delta": pooled.get("delta"), "ub95": pooled.get("ub95"),
                                                       "bar": None if bar_h is None else round(bar_h, 5),
                                                       "n_players": pooled.get("n_players"), "ok": ok_h}
            if not ok_h:
                reasons.append(f"h{h} ub95 vs {c} not below +10% of its MAE ({pooled.get('ub95')} vs {bar_h})")
    if underpowered:
        verdict = "UNDERPOWERED"
        reasons.insert(0, "DEV MDE95 exceeds 10% of the DEV NAIVE MAE against: " + ", ".join(underpowered)
                       + " (gate 4.5); the head does not ship whatever the HOLDOUT says")
    elif not reasons:
        verdict = "PASS"
    else:
        verdict = "FAIL"
    return {"head": head, "label": HEAD_LABELS.get(head, head), "verdict": verdict,
            "rule": "gate 4.5 (UNDERPOWERED) and 4.6 (PASS: all of h1 ub95 < 0 vs both; h2 and h3 ub95 "
                    "< +10% of the comparator MAE vs both; star h1 ub95 < +10% of the comparator star MAE "
                    "vs both); a null fails its check",
            "h1_mae": h1.get("mae"), "h1_n_survived": h1.get("n_survived"), "h1_n_star": h1.get("n_star"),
            "h1_comparator_mae": {c: ((h1.get("comparators") or {}).get(c) or {}).get("mae")
                                  for c in VERDICT_COMPARATORS},
            "checks": checks, "reasons": reasons}


def exposure_verdict(head: str, hz: dict) -> dict:
    h1 = hz.get(1) or hz.get("1") or {}
    checks: dict = {}
    reasons: list[str] = []
    for c in EXPOSURE_COMPARATORS:
        k = (h1.get("comparators") or {}).get(c) or {}
        pooled = k.get("pooled") or {}
        ok = _lt(pooled.get("ub95"), 0.0)
        checks[f"h1_ub95_below_0_vs_{c}"] = {"delta": pooled.get("delta"), "ub95": pooled.get("ub95"),
                                             "mde95": pooled.get("mde95"), "n_players": pooled.get("n_players"),
                                             "comparator_mae": k.get("mae"), "ok": ok}
        if not ok:
            reasons.append(f"h1 ub95 vs {c} not below 0 ({pooled.get('ub95')})")
    return {"head": head, "label": HEAD_LABELS.get(head, head),
            "verdict": "PASS" if not reasons else "FAIL",
            "rule": "gate 4.3: h1 HOLDOUT survived-row exposure MAE, one-sided 95% upper bound of the "
                    "paired delta below 0 against the prior-season and the 5/4/3 exposure; a null fails",
            "h1_mae": h1.get("mae"), "h1_n_survived": h1.get("n_survived"),
            "checks": checks, "reasons": reasons}


# --------------------------------------------------------------------------
# The Position Fit movers (gate 4.7, READ-EXCLUDED)
# --------------------------------------------------------------------------

def position_fit_movers() -> dict:
    """The player-seasons Position Fit's conversion test scored, re-enumerated
    with that test's own rule (positional_fit.conversion_accuracy: a regular,
    >= 200 innings, at a in season t and at a different b in t + 1 with at
    most 50 prior innings at b; seasons 2017 to the feed's last season minus
    one; a season t enters only when at least 100 multi-position
    player-seasons precede it). The label season of a mover is t + 1."""
    import positional_fit as PF
    feeds = PF.Feeds()
    obs = feeds.rates()
    last = int(feeds.inn.get("last_season")) - 1
    movers: set = set()
    conversions = 0
    by_t: dict = defaultdict(int)
    for t in range(MOVER_FIRST, last + 1):
        train = {k: v for k, v in obs.items() if k[1] <= t}
        if sum(1 for d in train.values() if len(d) >= 2) < MOVER_MIN_TRAIN:
            continue
        for (mid, s), row in obs.items():
            if s != t:
                continue
            nxt = obs.get((mid, t + 1))
            if not nxt:
                continue
            src = {p: v for p, v in row.items() if v["inn"] >= MOVER_MIN_INN}
            if not src:
                continue
            for b, nv in nxt.items():
                if nv["inn"] < MOVER_MIN_INN or b in src:
                    continue
                prior = sum(obs.get((mid, y), {}).get(b, {}).get("inn", 0.0) for y in range(t - 2, t + 1))
                if prior > MOVER_PRIOR_CAP:
                    continue
                conversions += 1
                by_t[t] += 1
                movers.add((int(mid), int(t) + 1))
    art = {}
    try:
        pf = json.loads((ROOT / "data" / "positional_fit.json").read_text(encoding="utf-8"))
        ca = pf.get("conversion_accuracy") or {}
        art = {"n_conversions": ca.get("n_conversions"),
               "by_season_n": {k: (v or {}).get("n") for k, v in (ca.get("by_season") or {}).items()},
               "generated_at": pf.get("generated_at")}
    except (OSError, ValueError):
        pass
    return {"rule": "positional_fit.conversion_accuracy's mover rule, re-enumerated from data/savant_oaa.json "
                    "and data/fielding_innings.json; matched on (mlbam, label season t + 1)",
            "n_conversions": conversions, "by_move_season": dict(sorted(by_t.items())),
            "n_player_label_seasons": len(movers),
            "n_player_label_seasons_2022_2025": sum(1 for _m, L in movers if 2022 <= L <= 2025),
            "artifact_as_committed": art,
            "movers": sorted(movers)}


# --------------------------------------------------------------------------
# The gap tripwire (gate section 2)
# --------------------------------------------------------------------------

def _age_band(age) -> str:
    if age is None:
        return "unknown"
    a = float(age)
    for lo, hi, name in AGE_BANDS:
        if (lo is None or a >= lo) and (hi is None or a <= hi):
            return name
    return "unknown"


def _dist(xs: list[float]) -> dict:
    import numpy as np
    if not xs:
        return {"n": 0, "mean": None, "sd": None, "p10": None, "p50": None, "p90": None}
    a = np.asarray(xs, dtype=float)
    q = np.percentile(a, [10, 50, 90])
    return {"n": int(a.size), "mean": round(float(a.mean()), 4),
            "sd": round(float(a.std(ddof=1)), 4) if a.size > 1 else None,
            "p10": round(float(q[0]), 4), "p50": round(float(q[1]), 4), "p90": round(float(q[2]), 4)}


def gap_tripwire(H, heads: dict, corpus: dict) -> dict:
    """Pooled mean of (served war at h1 minus component WAR at h1) on the
    HOLDOUT rows of each base B, the served engine's point-in-time path:
    proj_ml.train_cached(corpus, B - 1) bundles (labels <= B - 1, the full
    quantile set) with the served lift-only mean blend and star top-up
    lambdas of model/proj_lgbm/meta.json, rows the bundle cannot score
    falling back to the champion path, exactly as the served war does.
    Component WAR is H8 (hitters, war_comp) or P3 (pitchers, war_fip). No
    label is read."""
    import proj_eval as pe
    import proj_ml
    live_meta = json.loads((ROOT / "model" / "proj_lgbm" / "meta.json").read_text(encoding="utf-8"))
    lifts = {"mean_blend": live_meta.get("mean_blend") or {}, "star_blend": live_meta.get("star_blend") or {}}
    rows: list[dict] = []
    n_no_comp = n_no_champ = 0
    for B in H.bases:
        curves, war_map = H.fits[B]
        bundle = proj_ml.train_cached(corpus, B - 1, quantiles=proj_ml.QUANTILES)
        served_bundle = dict(bundle, meta=dict(bundle["meta"], **lifts))
        for x in H.rows:
            r = x["row"]
            if int(r["base"]) != B:
                continue
            side = x["side"]
            blk = heads.get((side, r["mlbam"], B))
            if blk is None:
                n_no_comp += 1
                continue
            ln = blk["lines"][1]
            comp = ln["war_comp"] if side == "hit" else ln["war_fip"]
            if comp is None:
                n_no_comp += 1
                continue
            seasons = H.by_player[side].get(r["mlbam"]) or {}
            hist = [seasons[s] for s in (B - 1, B - 2, B - 3) if s in seasons]
            champ = pe.default_predict_fn(hist, side, B, r["age"], curves, war_map, H.league)
            if champ is None:
                n_no_champ += 1
                continue
            feats = proj_ml.build_features(hist, side, B, r["age"], curves, war_map, H.league, champ=champ)
            ml = proj_ml.predict_path(served_bundle, feats, side) if feats is not None else None
            served = float((ml or champ)["war_by_year"][0])
            rows.append({"side": side, "base": B, "age": r["age"], "ml": ml is not None,
                         "gap": served - float(comp), "served": served, "comp": float(comp)})
    gaps = [z["gap"] for z in rows]
    pooled = _dist(gaps)
    out = {
        "what": "served war minus component WAR at h1 on the HOLDOUT rows (bases 2022 to 2024), WAR; "
                "served = the point-in-time proj_lgbm_v1 bundle (labels <= B - 1, full quantiles) with the "
                "served lift-only mean blend and star top-up lambdas, falling back to the champion path; "
                "component WAR = H8 (hitters) or P3 (pitchers); no label read",
        "threshold_abs_war": GAP_TRIPWIRE_WAR,
        "lift_lambdas_applied": lifts,
        "pooled": pooled,
        "pooled_mean_gap_war": pooled["mean"],
        "blocks_flip": None if pooled["mean"] is None else abs(pooled["mean"]) > GAP_TRIPWIRE_WAR,
        "by_side": {s: _dist([z["gap"] for z in rows if z["side"] == s]) for s in ("hit", "pit")},
        "by_base": {str(B): _dist([z["gap"] for z in rows if z["base"] == B]) for B in H.bases},
        "by_age_band": {name: _dist([z["gap"] for z in rows if _age_band(z["age"]) == name])
                        for _lo, _hi, name in AGE_BANDS},
        "by_path": {"ml_scored": _dist([z["gap"] for z in rows if z["ml"]]),
                    "champion_fallback": _dist([z["gap"] for z in rows if not z["ml"]])},
        "served_h1": _dist([z["served"] for z in rows]),
        "component_h1": _dist([z["comp"] for z in rows]),
        "n_rows_without_component_war": n_no_comp,
        "n_rows_without_champion_path": n_no_champ,
    }
    return out


# --------------------------------------------------------------------------
# Receipts (gate 4.2) and assembly
# --------------------------------------------------------------------------

def _hz_summary(blk: dict) -> dict:
    out = {}
    for h, c in (blk.get("horizons") or {}).items():
        out[str(h)] = {"n": c.get("n"), "n_survived": c.get("n_survived"), "mae": c.get("mae"),
                       "bias": c.get("bias"), "mae_star": c.get("mae_star"), "runs_mae": c.get("runs_mae"),
                       "coverage": c.get("coverage"), "coverage_survived": c.get("coverage_survived"),
                       "comparator_mae": {n: k.get("mae") for n, k in (c.get("comparators") or {}).items()}}
    return out


def assemble_artifact(*, look_date: str, report: dict, verdicts: dict, exposure: dict, tripwire: dict,
                      read_excluded: dict | None, movers: dict | None, receipts: dict, dev_receipt: dict,
                      params_sha: str, frame_meta: dict, consts: dict, defaults: list[str],
                      n_rows: dict, elapsed_s: float, dry_run: bool) -> dict:
    return {
        "generated_at": _utc_stamp(),
        "task": "PJ_5_COMPONENT_LOOK",
        "dry_run": bool(dry_run),
        "look_date": look_date,
        "gate": "docs/PROJ_COMPONENTS_GATE.md",
        "registration": {"commit": registration_commit(),
                         "gate_doc_sha256": _sha256_bytes(GATE_DOC.read_bytes().replace(b"\r\n", b"\n"))
                         if GATE_DOC.exists() else None},
        "params_path": "model/proj_components/params.json",
        "params_sha256": params_sha,
        "scorer": "proj_eval.run_components(look=True)",
        "bootstrap": {"seed": SEED, "B": report.get("B"), "vif": VIF},
        "frame": frame_meta,
        "dev": {"source": "model/proj_components/dev_receipt.json (copied; PJ_4_COMPONENT_HEADS_DEV)",
                **{k: v for k, v in (dev_receipt or {}).items()}},
        "holdout": {
            "bases": list(HOLDOUT_BASES), "cells": [list(c) for c in HOLDOUT_CELLS],
            "label_seasons": report.get("label_seasons"),
            "n_rows": n_rows, "n_rows_in_cells": report.get("n_rows_in_cells"),
            "constants_by_season": consts,
            "components": report.get("components"),
            "summary": {c: _hz_summary(b) for c, b in (report.get("components") or {}).items()},
            "read_excluded_fld_pos": read_excluded,
            "position_fit_movers": (None if movers is None else {k: v for k, v in movers.items() if k != "movers"}),
            "receipts": receipts,
        },
        "verdicts": verdicts,
        "exposure_test": exposure,
        "gap_tripwire": tripwire,
        "rule_note": "Verdicts by gate 4.5 and 4.6 only; no WAR accuracy claim is made or implied by any "
                     "number here; copy never claims the WAR got more accurate (owner answer PJ-Q2).",
        "defaults": defaults,
        "elapsed_s": round(elapsed_s, 1),
    }


def gate_rows(art: dict, art_sha: str) -> list[str]:
    """One section 9 row per head, the exposure test and the tripwire."""
    d = art["look_date"]
    cite = f"{ARTIFACT_REL} sha256 {art_sha}"
    rows = []

    def f(v, nd=4):
        return "n/a" if v is None else f"{float(v):.{nd}f}"

    for head in VERDICT_HEADS:
        v = art["verdicts"][head]
        ch = v["checks"]
        parts = [f"{v['label']}: h1 HOLDOUT survived n {v['h1_n_survived']}, star n {v['h1_n_star']}, "
                 f"rate MAE {f(v['h1_mae'])}"]
        for c in VERDICT_COMPARATORS:
            k1 = ch[f"h1_ub95_below_0_vs_{c}"]
            ks = ch[f"star_h1_ub95_below_10pct_vs_{c}"]
            k2 = ch[f"h2_ub95_below_10pct_vs_{c}"]
            k3 = ch[f"h3_ub95_below_10pct_vs_{c}"]
            dm = ch[f"dev_mde95_vs_{c}"]
            parts.append(f"vs {c.upper()} (MAE {f(v['h1_comparator_mae'][c])}): h1 delta {f(k1['delta'])} "
                         f"ub95 {f(k1['ub95'])}; star delta {f(ks['delta'])} ub95 {f(ks['ub95'])} (bar {f(ks['bar'])}); "
                         f"h2 ub95 {f(k2['ub95'])} (bar {f(k2['bar'])}); h3 ub95 {f(k3['ub95'])} (bar {f(k3['bar'])}); "
                         f"DEV MDE95 {f(dm['mde95'])} against the 10% NAIVE bar {f(dm['bar_10pct_of_dev_naive_mae'])}"
                         + (" EXCEEDS" if dm.get("exceeds") else ""))
        if head == "fld_pos" and (art["holdout"].get("read_excluded_fld_pos") or {}).get("h1"):
            ex = art["holdout"]["read_excluded_fld_pos"]["h1"]
            parts.append(f"READ-EXCLUDED (Position Fit movers removed, {ex.get('n_removed_rows')} rows): "
                         f"MAE {f(ex.get('mae'))}, vs NAIVE delta {f(ex.get('naive_delta'))} ub95 {f(ex.get('naive_ub95'))}, "
                         f"vs IMPLICIT delta {f(ex.get('implicit_delta'))} ub95 {f(ex.get('implicit_ub95'))}; no verdict")
        if v["reasons"]:
            parts.append("reasons: " + "; ".join(v["reasons"]))
        rows.append(f"| {d} | PJ-C | {v['verdict']} ({v['label']}) | {cite} | " + ". ".join(parts) + ". |")
    for head in EXPOSURE_HEADS:
        v = art["exposure_test"][head]
        ch = v["checks"]
        parts = [f"{v['label']}: h1 HOLDOUT survived n {v['h1_n_survived']}, exposure MAE {f(v['h1_mae'], 2)}"]
        for c in EXPOSURE_COMPARATORS:
            k = ch[f"h1_ub95_below_0_vs_{c}"]
            parts.append(f"vs {c} (MAE {f(k['comparator_mae'], 2)}): delta {f(k['delta'], 2)} ub95 {f(k['ub95'], 2)} "
                         f"MDE95 {f(k['mde95'], 2)}")
        if v["reasons"]:
            parts.append("reasons: " + "; ".join(v["reasons"]))
        parts.append("PJ_8 serves the line only on a PASS; otherwise it prints 'not projected'")
        rows.append(f"| {d} | PJ-C | {v['verdict']} ({v['label']}) | {cite} | " + ". ".join(parts) + ". |")
    t = art["gap_tripwire"]
    p = t["pooled"]
    tv = ("BLOCKS the flip" if t.get("blocks_flip") else
          ("clear" if t.get("blocks_flip") is False else "n/a"))
    rows.append(f"| {d} | PJ-C | gap tripwire {tv} | {cite} | "
                f"Pooled mean (served war minus component WAR) at h1 on the HOLDOUT rows {f(p.get('mean'))} WAR "
                f"(threshold 0.30 either sign; n {p.get('n')}, sd {f(p.get('sd'))}, p10 {f(p.get('p10'))}, "
                f"p50 {f(p.get('p50'))}, p90 {f(p.get('p90'))}); hitters {f(t['by_side']['hit'].get('mean'))} "
                f"(n {t['by_side']['hit'].get('n')}), pitchers {f(t['by_side']['pit'].get('mean'))} "
                f"(n {t['by_side']['pit'].get('n')}); by age band "
                + ", ".join(f"{k} {f(v.get('mean'))} (n {v.get('n')})" for k, v in t["by_age_band"].items())
                + ". Served = point-in-time proj_lgbm_v1 bundles (labels <= B - 1) with the served lift lambdas, "
                  "champion fallback; never a label. |")
    return rows


# --------------------------------------------------------------------------
# The dry run on the PJ_3 fixtures with nulls (gate section 5, step 1)
# --------------------------------------------------------------------------

def _fixture_row(mlbam, base=2016, h=1, side="hit", exposure=600.0, labels=None,
                 exposure_base=550.0, exposure_hist=None, **extra):
    r = {"mlbam": mlbam, "side": side, "base": base, "h": h, "label_season": base + h - 1,
         "exposure": exposure, "exposure_base": exposure_base, "labels": labels or {}}
    if exposure_hist is not None:
        r["exposure_hist"] = exposure_hist
    r.update(extra)
    return r


def dry_run(out_dir: Path) -> dict:
    """The fixtures of test_proj_components_scorer.py's dry-run test, scored
    on DEV cells (look=False) and pushed through every reporting function
    this look uses, with nulls everywhere: a cell with no rows, a component
    with no label, a comparator returning None, one-player cells, an empty
    DEV MDE table and an empty tripwire. Writes only under out_dir."""
    import proj_eval as pe
    frame = [
        _fixture_row(10, labels={"bsr": 1.0, "fld_pos": None}, exposure_base=300.0),
        _fixture_row(11, labels={"bsr": -0.5, "fld_pos": None}, exposure=250.0, exposure_base=300.0),
        _fixture_row(20, side="pit", exposure=150.0, exposure_base=160.0, labels={"ra9_gap": 2.0}),
        _fixture_row(21, side="pit", exposure=70.0, exposure_base=130.0,
                     labels={"gmli_relief": 1.5}, exposures={"gmli_relief": 60.0}),
        _fixture_row(30, exposure=420.0, exposure_hist={2015: 300.0}),
        _fixture_row(31, side="pit", exposure=0.0, exposure_hist={2015: 100.0, 2014: 80.0}),
    ]
    preds = {
        "bsr": lambda r: 0.5,
        "fld_pos": lambda r: {"rate": 1.0, "exposure": 500.0},
        "ra9_gap": lambda r: {"rate": 0.0},
        "gmli_relief": lambda r: {"rate": 4.0, "exposure": 60.0, "p10": 0.0, "p90": 5.0},
        "batting": lambda r: None,
        "league": lambda r: {"rate": 0.0, "exposure": 500.0},
        "replacement": lambda r: {"rate": 0.0, "exposure": 500.0},
        "pa": lambda r: {"exposure": 400.0} if r.get("exposure_hist") else None,
        "ip": lambda r: {"exposure": 90.0} if r.get("exposure_hist") else None,
    }
    comps = {
        "bsr": {"naive": lambda r: 0.0, "implicit": lambda r: 0.0},
        "fld_pos": {"naive": lambda r: 0.0, "implicit": lambda r: 0.0},
        "ra9_gap": {"naive": lambda r: None, "implicit": lambda r: 0.0},
        "gmli_relief": {"naive": lambda r: 3.8, "implicit": lambda r: 3.8},
        "batting": {"naive": lambda r: 0.0},
        "league": {"naive": lambda r: 0.0},
        "replacement": {"naive": lambda r: 0.0},
    }
    rep = pe.run_components(frame, preds, comps, [(2016, 1), (2016, 3)], SEED, B=100, vif=VIF)
    print(pe.format_components_report(rep))
    dev_mde_null = {h: {"comparators": {c: {"mde95": None, "mae": None} for c in VERDICT_COMPARATORS}}
                    for h in VERDICT_HEADS}
    verdicts = {h: head_verdict(h, rep["components"][h]["horizons"], dev_mde_null) for h in VERDICT_HEADS}
    exposure = {h: exposure_verdict(h, rep["components"][h]["horizons"]) for h in EXPOSURE_HEADS}
    tripwire = {"what": "dry run", "threshold_abs_war": GAP_TRIPWIRE_WAR, "lift_lambdas_applied": {},
                "pooled": _dist([]), "pooled_mean_gap_war": None, "blocks_flip": None,
                "by_side": {"hit": _dist([]), "pit": _dist([])}, "by_base": {},
                "by_age_band": {name: _dist([]) for _lo, _hi, name in AGE_BANDS},
                "by_path": {"ml_scored": _dist([]), "champion_fallback": _dist([])},
                "served_h1": _dist([]), "component_h1": _dist([]),
                "n_rows_without_component_war": 0, "n_rows_without_champion_path": 0}
    read_ex = {"h1": {"n_removed_rows": 0, "mae": None, "naive_delta": None, "naive_ub95": None,
                      "implicit_delta": None, "implicit_ub95": None}}
    art = assemble_artifact(look_date="dry-run", report=rep, verdicts=verdicts, exposure=exposure,
                            tripwire=tripwire, read_excluded=read_ex, movers=None, receipts={},
                            dev_receipt={}, params_sha="0" * 64, frame_meta={}, consts={}, defaults=[],
                            n_rows={}, elapsed_s=0.0, dry_run=True)
    text = json.dumps(art, indent=1, sort_keys=True)
    rows = gate_rows(art, _sha256_bytes(text.encode("utf-8")))
    (out_dir / "dry_run_artifact.json").write_text(text + "\n", encoding="utf-8")
    (out_dir / "dry_run_gate_rows.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print("dry run verdicts:", {h: v["verdict"] for h, v in verdicts.items()},
          {h: v["verdict"] for h, v in exposure.items()})
    for row in rows:
        print(row[:160] + ("..." if len(row) > 160 else ""))
    for h in VERDICT_HEADS:
        assert verdicts[h]["verdict"] in ("PASS", "FAIL", "UNDERPOWERED")
    assert all(v["verdict"] in ("PASS", "FAIL") for v in exposure.values())
    return art


# --------------------------------------------------------------------------
# The look
# --------------------------------------------------------------------------

class Holdout:
    """The DEV driver's assembly on the HOLDOUT bases (same engine, aging and
    constants rules; the cells are the registered holdout cells)."""

    def __init__(self, corpus, frame, blob):
        import proj_components_dev as D
        self.D = D
        self.dev = D.Dev(corpus, frame, blob, list(HOLDOUT_BASES))
        self.dev.cells = list(HOLDOUT_CELLS)


def run_look(out_dir: Path, B: int, write: bool) -> int:
    import fa_projection as fp
    import fwar_vintage
    import proj_components as PC
    import proj_components_dev as D
    import proj_eval as pe

    t0 = time.time()
    look_date = _dt.date.today().isoformat()
    defaults: list[str] = []

    # -- checks before any scoring ------------------------------------------
    recorded = recorded_params_sha()
    params = PC.check_params(PC.load_params(), recorded)
    log.info("frozen params ok: sha256 %s", recorded)
    art_path = ROOT / ARTIFACT_REL
    if art_path.exists():
        prior = json.loads(art_path.read_text(encoding="utf-8"))
        if isinstance(prior, dict) and "holdout" in prior:
            print(f"STOP: {ARTIFACT_REL} already carries a holdout block; the look is spent")
            return 2
    dev_receipt = json.loads(PC.DEV_RECEIPT_PATH.read_text(encoding="utf-8"))
    if dev_receipt.get("params_sha256") != recorded:
        print("STOP: dev_receipt.json params_sha256 differs from the gate's record")
        return 2

    with open(fp.CORPUS_CACHE, "rb") as fh:
        corpus = pickle.load(fh)
    blob = fwar_vintage.load()
    if blob["vintage_id"] != params["vintage_id"]:
        print(f"STOP: vintage {blob['vintage_id']} is not the frozen params' {params['vintage_id']}")
        return 2
    frame = PC.build_component_frame(corpus, D.DEV_FIRST_BASE, PC.PJC_LABEL_SEASON_MAX)
    if frame["meta"]["schema_tag"] != params["frame_schema_tag"]:
        print("STOP: the frame schema differs from the frozen params' schema tag")
        return 2
    H = Holdout(corpus, frame, blob).dev
    bad = [c for c in H.cells if c[0] + c[1] - 1 >= pe.COMPONENT_LOOK_LABEL_CEILING
           or c[0] + c[1] - 1 in PC.PJC_EXCLUDED_LABEL_SEASONS]
    if bad:
        print(f"STOP: a holdout cell reads an unreadable label season: {bad}")
        return 2
    log.info("holdout cells %s", H.cells)

    # -- scoring (an exception from here on STOPs, no rerun) ----------------
    scoring_began = False
    try:
        H.prepare()
        r_relief = float(params["R_relief"])
        scored_rows = H.scorer_rows(r_relief)
        for r in scored_rows:
            assert not any(str(k).lower() == "war" for k in r["labels"])
        comps = D.make_comparators(H, r_relief)
        heads = H.heads(params)
        preds = D.make_predictors(heads, H, r_relief, with_ranges=True)
        n_rows = {"hit": sum(1 for x in H.rows if x["side"] == "hit"),
                  "pit": sum(1 for x in H.rows if x["side"] == "pit"),
                  "scorer_rows": len(scored_rows)}
        log.info("assembled %s (%.1fs)", n_rows, time.time() - t0)

        # Label-free steps first, so a defect in them surfaces before any
        # label is read: the Position Fit movers (gate 4.7) and the gap
        # tripwire (gate section 2; two projections, never a label).
        movers = position_fit_movers()
        mset = set(tuple(m) for m in movers["movers"])
        log.info("position fit movers: %d conversions, %d player-seasons (%.1fs)",
                 movers["n_conversions"], movers["n_player_label_seasons"], time.time() - t0)
        tripwire = gap_tripwire(H, heads, corpus)
        print(f"gap tripwire: pooled mean {tripwire['pooled_mean_gap_war']} WAR on n {tripwire['pooled']['n']} "
              f"-> {'BLOCKS the flip' if tripwire['blocks_flip'] else 'clear'}")
        log.info("tripwire done (%.1fs)", time.time() - t0)

        scoring_began = True
        report = pe.run_components(scored_rows, {c: preds[c] for c in ALL_HEADS},
                                   {c: comps[c] for c in ALL_HEADS if c in comps},
                                   H.cells, SEED, B=B, vif=VIF, look=True)
        log.info("holdout scoring done (%.1fs)", time.time() - t0)
        print(pe.format_components_report(report))

        # READ-EXCLUDED split (gate 4.7): H4 + H5 h1 with the Position Fit
        # movers' player-seasons removed; no verdict.
        rows_ex = [r for r in scored_rows
                   if r["side"] == "hit" and (int(r["mlbam"]), int(r["label_season"])) not in mset]
        n_removed = sum(1 for r in scored_rows if r["side"] == "hit"
                        and (int(r["mlbam"]), int(r["label_season"])) in mset and int(r["h"]) == 1)
        rep_ex = pe.run_components(rows_ex, {"fld_pos": preds["fld_pos"]}, {"fld_pos": comps["fld_pos"]},
                                   [(b, 1) for b in HOLDOUT_BASES], SEED, B=B, vif=VIF, look=True)
        c1 = rep_ex["components"]["fld_pos"]["horizons"].get(1) or {}
        k = c1.get("comparators") or {}
        read_excluded = {
            "what": "H4 + H5 h1 HOLDOUT statistics with the Position Fit conversion-test movers' "
                    "player-seasons removed (gate 4.7, default D3); carries no verdict",
            "h1": {"n_removed_rows": n_removed, "n": c1.get("n"), "n_survived": c1.get("n_survived"),
                   "mae": c1.get("mae"), "bias": c1.get("bias"),
                   "naive_mae": (k.get("naive") or {}).get("mae"),
                   "naive_delta": ((k.get("naive") or {}).get("pooled") or {}).get("delta"),
                   "naive_ub95": ((k.get("naive") or {}).get("pooled") or {}).get("ub95"),
                   "implicit_mae": (k.get("implicit") or {}).get("mae"),
                   "implicit_delta": ((k.get("implicit") or {}).get("pooled") or {}).get("delta"),
                   "implicit_ub95": ((k.get("implicit") or {}).get("pooled") or {}).get("ub95")},
            "full": rep_ex["components"]["fld_pos"],
        }
        log.info("read-excluded split done: %d h1 rows removed (%.1fs)", n_removed, time.time() - t0)

        # verdicts (gate 4.5, 4.6) and the exposure test (4.3)
        dev_mde = dev_receipt.get("mde95") or {}
        verdicts = {h: head_verdict(h, report["components"][h]["horizons"], dev_mde) for h in VERDICT_HEADS}
        exposure = {h: exposure_verdict(h, report["components"][h]["horizons"]) for h in EXPOSURE_HEADS}
        print("verdicts:", {h: v["verdict"] for h, v in verdicts.items()},
              "exposure:", {h: v["verdict"] for h, v in exposure.items()})

        # receipts (gate 4.2): deterministic heads on HOLDOUT beside DEV and Gate 1
        receipts = {
            "deterministic_heads_holdout": {c: _hz_summary(report["components"][c]) for c in RECEIPT_HEADS},
            "deterministic_heads_dev": {c: ((dev_receipt.get("dev_tables") or {}).get("components") or {}).get(c, {}).get("horizons")
                                        for c in RECEIPT_HEADS},
            "p3_fip_runs_leg_holdout": D.fip_runs_receipt(H, heads),
            "p3_fip_runs_leg_dev": (dev_receipt.get("receipts") or {}).get("p3_fip_runs_leg_dev"),
            "gate1_figures_beside": D._gate1_figures(),
            "fwar_replica_vs_vintage_2011_2021": "see dev.receipts (PJ_4); unchanged by this look",
            "not_projected_counts": {},
            "note": "receipts, not verdicts (gate 4.2); no WAR residual is computed on any row",
        }
        n_np: dict = defaultdict(int)
        for blk in heads.values():
            for c in blk["not_projected"]:
                n_np[c] += 1
        receipts["not_projected_counts"] = dict(sorted(n_np.items()))

        consts ={str(s): {k: v for k, v in c.items() if k != "receipt"} for s, c in sorted(H.consts.items())
                  if s >= 2021}
        frame_meta = {k: v for k, v in frame["meta"].items() if k not in ("vintage_multi_team", "exposure_stint")}
        defaults.append("D-look-1: the UNDERPOWERED test applied per comparator against 10% of the head's DEV "
                        "NAIVE MAE (the literal text of gate 4.5); the per-comparator reading is published beside it")
        defaults.append("D-look-2: the served point-in-time path of the gap tripwire applies the served lift-only "
                        "mean blend and star top-up lambdas (model/proj_lgbm/meta.json) to the proj_ml.train_cached "
                        "bundle, falling back to the champion path where the bundle cannot score a row")
        defaults.append("D-look-3: the Position Fit movers are re-enumerated from the committed data files with "
                        "conversion_accuracy's own rule, since data/positional_fit.json lists counts, not players")
        art = assemble_artifact(look_date=look_date, report=report, verdicts=verdicts, exposure=exposure,
                                tripwire=tripwire, read_excluded=read_excluded, movers=movers,
                                receipts=receipts, dev_receipt=dev_receipt, params_sha=recorded,
                                frame_meta=frame_meta, consts=consts, defaults=defaults, n_rows=n_rows,
                                elapsed_s=time.time() - t0, dry_run=False)
    except Exception:
        tb = traceback.format_exc()
        q = out_dir / "OWNER_QUESTION.md"
        q.write_text("# PJ_5_COMPONENT_LOOK: exception during the look\n\n"
                     f"scoring_began: {scoring_began}\n\nThe look was not rerun. Traceback:\n\n```\n{tb}```\n",
                     encoding="utf-8")
        print(f"STOP: exception (scoring_began={scoring_began}); wrote {q}")
        print(tb)
        return 4

    text = json.dumps(art, indent=1, sort_keys=True) + "\n"
    (out_dir / "proj_components_eval.preview.json").write_text(text, encoding="utf-8")
    rows = gate_rows(art, _sha256_bytes(text.encode("utf-8")))
    (out_dir / "gate_rows.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
    if write:
        art_path.parent.mkdir(parents=True, exist_ok=True)
        art_path.write_text(text, encoding="utf-8")
        print(f"wrote {ARTIFACT_REL} sha256 {_sha256_bytes(text.encode('utf-8'))}")
    else:
        print(f"preview only: {out_dir / 'proj_components_eval.preview.json'} (nothing under data/)")
    print(f"gate rows: {out_dir / 'gate_rows.txt'}")
    print(f"elapsed {time.time() - t0:.1f}s")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, required=True, help="output directory (tee, dry run, preview)")
    ap.add_argument("--write", action="store_true", help="write data/proj_components_eval.json")
    ap.add_argument("--dry-run-only", action="store_true")
    ap.add_argument("--bootstrap", type=int, default=B_DEFAULT)
    a = ap.parse_args(argv)
    out_dir: Path = a.out
    out_dir.mkdir(parents=True, exist_ok=True)
    f_out = open(out_dir / "look_stdout.txt", "a", encoding="utf-8", buffering=1)
    f_err = open(out_dir / "look_stderr.txt", "a", encoding="utf-8", buffering=1)
    sys.stdout = _Tee(sys.__stdout__, f_out)
    sys.stderr = _Tee(sys.__stderr__, f_err)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    print(f"=== PJ_5_COMPONENT_LOOK {_utc_stamp()} (write={a.write}, B={a.bootstrap}) ===")
    print("--- dry run on the PJ_3 fixtures with nulls ---")
    dry_run(out_dir)
    print("--- dry run ok ---")
    if a.dry_run_only:
        return 0
    try:
        return run_look(out_dir, a.bootstrap, a.write)
    finally:
        sys.stdout.flush()
        sys.stderr.flush()


if __name__ == "__main__":
    raise SystemExit(main())
