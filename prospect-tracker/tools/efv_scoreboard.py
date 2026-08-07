# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV Scoreboard (G-SCORE, Phase 0a) - the model's public report card.

One regenerable read that consolidates the eFV track record into a single
artifact, data/xfv_scoreboard_eval.json, with every cell carrying the eFV
value, the consensus baseline, and a win flag:

  - pooled OOS Spearman + contributor/star AUC per side (SAME-RUN read on the
    shipped forward-chained protocol: efv_lab_runner floors, SCORED_YEARS,
    identical rows for model and baseline - reproduces data/xfv_eval*.json);
  - per-era (<=2018 / 2019-2021 / 2022-2023) on the wider era protocol
    (2016-2023 folds, the efv_model._era_split convention, so the <=2018
    cell populates - reproduces era_split_debuted);
  - per-FV-tier and per-cohort (ifa/college/hs/draft/other) Spearman;
  - t45 + within-tier weighted mean (wm), model vs consensus;
  - head-to-head vs consensus / FanGraphs / MLB Pipeline plus the archetype
    table, lifted from data/source_backtest.json (oos_grades machinery;
    reran here only if the artifact is older than SB_MAX_AGE_DAYS);
  - top-20-percent WAR capture rate (capture curve, eFV vs consensus);
  - biggest-disagreement receipts (resolved, pre-debut vintage, who was right).

Descriptive only: no gate, no served-number change. Registered so the artifact
has a registration pointer: docs/efv-2026-07-24/GATES.md section G-SCORE.

Run:  python tools/efv_scoreboard.py
Idempotent: compare-before-write (generated_at excluded), so a no-change rerun
leaves the artifact untouched.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import os; os.chdir(ROOT)  # noqa: E702  (house idiom, matches efv_lab_runner)

import efv_lab_runner as LAB                      # noqa: E402
from efv_model import _feature_spec, _fit_ols_fv, _pred_ols, blend_lambda  # noqa: E402
from prospect_path import (_fit_ridge, _predict, _spearman,               # noqa: E402
                           _weighted_spearman)
from source_backtest import _auc, XFV_VS_CONSENSUS_MDE95   # noqa: E402

DATA = ROOT / "data"
OUT_PATH = DATA / "xfv_scoreboard_eval.json"
REGISTRATION = "docs/efv-2026-07-24/GATES.md section G-SCORE (Phase 0a, no gate)"
REGEN_CMD = "python tools/efv_scoreboard.py"

# Shared outcome labels (the auc_breakdown convention in data/xfv_eval*.json):
# first-6-season summed bWAR (target_censored), contributor >= 3.0, star >= 10.0.
CONTRIBUTOR_WAR = 3.0
STAR_WAR = 10.0

# Cell population floors (the lab-runner conventions).
TIER_MIN_N = 15
COHORT_MIN_N = 25
ERA_MIN_N = 15

# source_backtest.json freshness window: reuse if generated within this many
# days, rerun otherwise (the rerun loads timeseries + debuts + oos_grades,
# which is the expensive path - the artifact is nightly-regenerated anyway).
SB_MAX_AGE_DAYS = 7

# The pre-2026-08-06 scoreboard, verbatim, so the Diamond hub's old numbers stay
# readable as history instead of becoming unreproducible. Owner decision 2026-08-07:
# 11-fold pair-weighted is the headline everywhere, legacy 4-fold survives as a
# labeled dated footnote. Everything in here was measured on SCORED_YEARS
# (2020, 2021, 2022, 2023) with an UNWEIGHTED pooled rho, and no re-run of any
# current tool reproduces it, because both the fold set and the weighting changed.
LEGACY_4FOLD_FOOTNOTE = {
    "generated_at": "2026-07-30",
    "basis": "SCORED_YEARS = (2020, 2021, 2022, 2023), unweighted pooled Spearman",
    "retired_on": "2026-08-06 (owner promotion to the 11-fold chain)",
    "why_it_cannot_be_reproduced": (
        "efv_model.SCORED_YEARS is now the 11-fold chain and prospect_path._score "
        "pair-weights the pooled figure, so every tool that imports either lands on "
        "the new basis. efv_model.SCORED_YEARS_LEGACY_4FOLD is kept for archaeology."),
    "sides": {
        "hit": {"pooled_spearman": {"n": 353, "efv": 0.3882, "consensus": 0.3522},
                "pooled_auc_contributor": {"n": 353, "efv": 0.7768, "consensus": 0.7556}},
        "pit": {"pooled_spearman": {"n": 438, "efv": 0.3060, "consensus": 0.2671},
                "pooled_auc_contributor": {"n": 438, "efv": 0.7187, "consensus": 0.7023}},
    },
    "head_to_head_vs_consensus": {
        "n": 2200, "efv_spearman": 0.384, "consensus_spearman": 0.283,
        "efv_auc_contributor": 0.7572, "consensus_auc_contributor": 0.7316,
        "caveat": ("this pair is ALSO on the retired mixed-rows basis: eFV was scored "
                   "on its own covered rows and consensus on the full common set, so "
                   "the 0.101 margin is part protocol and part population"),
    },
    "top20_capture": {"pool_n": 1632, "efv": 0.6985, "consensus": 0.7039},
}


# ---------------------------------------------------------------------------
# cells
# ---------------------------------------------------------------------------
def _cell(efv, cons, n):
    """One scoreboard cell: eFV value vs the consensus baseline on identical
    rows. win = strictly better (a tie is not a win)."""
    if efv is None or cons is None:
        return {"n": n, "efv": None, "consensus": None, "win": None, "margin": None}
    return {"n": n, "efv": round(efv, 4), "consensus": round(cons, 4),
            "win": efv > cons, "margin": round(efv - cons, 4)}


def _sp_cell(rows, min_n, weighted=True):
    """One Spearman cell.

    PAIR-WEIGHTED by default since 2026-08-07, matching the published headline
    (prospect_path._score). Unweighted, this scoreboard read 0.3910 hit while
    data/xfv_eval.json read 0.3993 on the identical 755 rows, and the Diamond hub
    and the glossary printed the two numbers side by side with nothing saying that
    the only difference was the censored 2024 cohort's 0.333 weight. With every
    weight 1.0 _weighted_spearman is algebraically the unweighted form, so the
    cells that carry no censored rows are unchanged.

    `weighted=False` is for the era cells, which promise to reproduce
    efv_model._era_split, and that function is unweighted by construction.
    """
    if len(rows) < min_n:
        return None
    y = [r["y"] for r in rows]
    blend, cons = [r["blend"] for r in rows], [r["cons"] for r in rows]
    # A constant leg has no rank correlation, full stop. _spearman returns None for
    # it (vx == 0), but _weighted_spearman's weighted rank mean lands a few ulps off
    # the constant rank, leaves vx microscopically positive, and reports rho = 0.0000
    # for an UNDEFINED quantity. That is how a whole FV-35 hitter cell (53 rows, every
    # consensus prediction clamped to 0 WAR) arrived on the scoreboard reading
    # "eFV 0.1314 vs consensus 0.0000 WIN" against a baseline that never had an
    # ordering to beat. Degeneracy is decided here, on the values, not on a variance
    # that survived rounding.
    if len(set(blend)) < 2 or len(set(cons)) < 2 or len(set(y)) < 2:
        return None
    if weighted:
        w = [r.get("w", 1.0) for r in rows]
        b = _weighted_spearman(blend, y, w)
        c = _weighted_spearman(cons, y, w)
    else:
        b = _spearman(blend, y)
        c = _spearman(cons, y)
    if b is None or c is None:
        return None
    return _cell(b, c, len(rows))


def _auc_cell(rows, thr, min_n):
    if len(rows) < min_n:
        return None
    labels = [r["y"] >= thr for r in rows]
    b = _auc([r["blend"] for r in rows], labels)
    c = _auc([r["cons"] for r in rows], labels)
    if b is None or c is None:
        return None
    out = _cell(b, c, len(rows))
    out["n_pos"] = sum(1 for v in labels if v)
    return out


# ---------------------------------------------------------------------------
# same-run forward-chained reads (shipped machinery, identical rows both raters)
# ---------------------------------------------------------------------------
def _forward_read(side, years, min_train, min_test):
    """Forward-chained OOS predictions for the shipped blend AND the consensus
    OLS(FV) anchor on the same test rows. Mirrors efv_lab_runner.run_variant
    (pooled protocol) / efv_model._era_split (era protocol) depending on the
    floors passed in."""
    rows = LAB.data_for(side)
    keys = _feature_spec(side)[0]
    lam = blend_lambda(side)
    out = []
    for yr in years:
        tr = [r for r in rows if r["decision_year"] < yr]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(te) < min_test or len(tr) < min_train:
            continue
        ols = _fit_ols_fv([{"fv": r["fv"], "target": r["target_censored"]} for r in tr])
        ridge = _fit_ridge([{"feats": r["feats"], "target": r["target_censored"],
                             "weight": r["weight"], "fv": r["fv"]} for r in tr], keys)
        if not (ols and ridge):
            continue
        for r in te:
            cw = max(0.0, _pred_ols(ols, r["fv"]))
            out.append({"blend": (1 - lam) * cw + lam * _predict(ridge, r["feats"]),
                        "cons": cw, "fv": r["fv"], "y": r["target_censored"],
                        "w": float(r.get("weight") or 1.0),
                        "cohort": r["cohort"], "year": yr})
    return out


def _side_block(side):
    """All matrix cells for one side: pooled + tier + cohort on the lab pooled
    protocol (SCORED_YEARS, floors 50/12 - reproduces xfv_eval pooled_oos);
    eras on the wider era protocol (2016-2023, floors 60/10 - reproduces
    era_split_debuted, so the <=2018 cell populates)."""
    pooled = _forward_read(side, LAB.SCORED_YEARS, 50, 12)
    era_rows = _forward_read(side, range(2016, 2024), 60, 10)

    block = {"pooled": {
        "spearman": _sp_cell(pooled, 30),
        "auc_contributor": _auc_cell(pooled, CONTRIBUTOR_WAR, 30),
        "auc_star": _auc_cell(pooled, STAR_WAR, 30),
    }}

    # per-FV-tier (nearest-5 consensus tier, the lab convention) + t45 + wm
    tiers = {}
    for r in pooled:
        tiers.setdefault(LAB._tier(r["fv"]), []).append(r)
    tier_cells, wm_b, wm_c, wm_n = {}, 0.0, 0.0, 0
    for tk in sorted(tiers):
        cell = _sp_cell(tiers[tk], TIER_MIN_N)
        if cell is None:
            continue
        tier_cells[str(tk)] = cell
        wm_b += cell["efv"] * cell["n"]
        wm_c += cell["consensus"] * cell["n"]
        wm_n += cell["n"]
    block["by_fv_tier"] = tier_cells
    block["t45"] = tier_cells.get("45")
    block["wm"] = (_cell(wm_b / wm_n, wm_c / wm_n, wm_n) if wm_n else None)

    # per-cohort (ifa / college / hs / draft / other)
    cohorts = {}
    for r in pooled:
        cohorts.setdefault(r["cohort"], []).append(r)
    coh_cells = {}
    for ck in ("ifa", "college", "hs", "draft", "other"):
        grp = cohorts.get(ck) or []
        cell = _sp_cell(grp, COHORT_MIN_N)
        if cell is not None:
            coh_cells[ck] = cell
        elif grp:
            coh_cells[ck] = {"n": len(grp), "efv": None, "consensus": None,
                             "win": None, "margin": None,
                             "note": f"under the {COHORT_MIN_N}-row cell floor"}
    block["by_cohort"] = coh_cells

    # per-era (wider protocol so <=2018 exists)
    eras = {}
    for r in era_rows:
        eras.setdefault(LAB._era(r["year"]), []).append(r)
    era_cells = {}
    for ek in ("<=2018", "2019-2021", "2022-2023"):
        grp = eras.get(ek) or []
        sp = _sp_cell(grp, ERA_MIN_N, weighted=False)
        if sp is None:
            continue
        era_cells[ek] = {"spearman": sp,
                         "auc_contributor": _auc_cell(grp, CONTRIBUTOR_WAR, ERA_MIN_N)}
    block["by_era"] = era_cells
    return block


def _artifact_crosscheck(side_blocks):
    """Non-gating sanity read of the committed eval artifacts next to the
    same-run numbers. A drift over 0.002 prints a console warning (the
    artifacts are regenerated on their own cadence, so this never fails)."""
    checks = []
    for side, fn in (("hit", "xfv_eval.json"), ("pit", "xfv_eval_pitcher.json")):
        p = DATA / fn
        if not p.exists():
            continue
        try:
            ev = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        pooled = ((ev.get("evals") or {}).get("debuted_km") or {}).get("pooled_oos") or {}
        art_blend = (pooled.get("blend") or {}).get("spearman")
        art_cons = (pooled.get("baseline") or {}).get("spearman")
        cell = (side_blocks.get(side) or {}).get("pooled", {}).get("spearman") or {}
        row = {"side": side, "artifact": f"data/{fn}",
               "artifact_generated_at": ev.get("generated_at"),
               "artifact_blend_spearman": art_blend,
               "artifact_consensus_spearman": art_cons,
               "same_run_blend_spearman": cell.get("efv"),
               "same_run_consensus_spearman": cell.get("consensus")}
        drift = None
        if art_blend is not None and cell.get("efv") is not None:
            drift = round(abs(art_blend - cell["efv"]), 4)
            if drift > 0.002:
                print(f"WARN {side}: same-run blend rho {cell['efv']} vs "
                      f"artifact {art_blend} (drift {drift})")
        row["blend_drift"] = drift
        checks.append(row)
    return checks


# ---------------------------------------------------------------------------
# source_backtest consolidation (head-to-head / capture / receipts)
# ---------------------------------------------------------------------------
def _sb_has_identical_rows_basis(d) -> bool:
    """Does this source_backtest artifact carry every identical-rows block this
    consolidation reads? Checking only the pooled block is not enough: an artifact
    written between the two 2026-08-07 commits passed that check and still fed the
    archetype table its mixed-basis rows."""
    acc = (d or {}).get("accuracy") or {}
    if acc.get("pooled_efv_common") is None:
        return False
    arch = acc.get("by_archetype") or []
    return bool(arch) and all(a.get("raters_efv_common") is not None for a in arch)


def _load_source_backtest():
    p = DATA / "source_backtest.json"
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            d = None
        gen = (d or {}).get("generated_at")
        # A fresh artifact is not a USABLE one. The identical-rows head-to-head
        # basis landed 2026-08-07; an artifact written before it parses fine, is
        # inside the age window, and silently hands this consolidation the
        # mixed-basis numbers it exists to stop publishing. Age AND schema.
        if gen and _sb_has_identical_rows_basis(d):
            try:
                ts = datetime.strptime(gen, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - ts <= timedelta(days=SB_MAX_AGE_DAYS):
                    return d, {"reran": False, "artifact_generated_at": gen,
                               "rule": f"reused (fresh within {SB_MAX_AGE_DAYS} days)"}
            except ValueError:
                pass
    import source_backtest as SB
    d = SB.run_source_backtest(write=True)
    return d, {"reran": True, "artifact_generated_at": d.get("generated_at"),
               "rule": (f"reran (artifact missing, older than {SB_MAX_AGE_DAYS} days, "
                        "or predating the identical-rows head-to-head basis)")}


def _head_to_head(sb):
    """eFV vs each public rater on the common resolved set (identical players,
    OOS eFV grades). Cells per rival: Spearman + contributor AUC.

    BASIS FIX 2026-08-07. This read `accuracy.pooled`, where each rater is scored
    on the rows IT graded. eFV covers a subset (3,210 of 4,259), so every cell here
    compared eFV's number against a rival's number computed on rows eFV never saw,
    and the Diamond hub printed the difference as a head-to-head margin. It now
    reads `pooled_efv_common`, which re-scores every rater on the eFV rows.
    """
    acc = sb.get("accuracy") or {}
    pooled = acc.get("pooled_efv_common") or acc.get("pooled") or {}
    basis = ("identical rows (accuracy.pooled_efv_common)"
             if acc.get("pooled_efv_common") else
             "MIXED: each rater on its own rows (accuracy.pooled); "
             "regenerate source_backtest.json for the identical-rows basis")
    x = pooled.get("xfv") or {}
    if x.get("spearman") is None:
        return None
    rivals = {}
    for key, label in (("prospx_consensus", "PROSPX consensus"),
                       ("fangraphs", "FanGraphs"),
                       ("mlb_pipeline", "MLB Pipeline")):
        r = pooled.get(key) or {}
        if r.get("spearman") is None:
            continue
        rivals[key] = {"label": label,
                       "spearman": _cell(x.get("spearman"), r.get("spearman"),
                                         x.get("n")),
                       "auc_contributor": _cell(x.get("auc"), r.get("auc"),
                                                x.get("n"))}
    arch = []
    for a in ((sb.get("accuracy") or {}).get("by_archetype")) or []:
        # Same basis rule as the tiles above: prefer the rater table scored on the
        # eFV-covered rows. Falls back to the mixed table only on an artifact that
        # predates it, so the hub never silently loses the archetype rows.
        rt = a.get("raters_efv_common") or a.get("raters") or {}
        xa = rt.get("xfv") or {}
        ca = rt.get("prospx_consensus") or {}
        if xa.get("spearman") is None or ca.get("spearman") is None:
            continue
        arch.append({"archetype": a.get("archetype"), "label": a.get("label"),
                     "n": xa.get("n"),
                     "basis": ("identical rows" if a.get("raters_efv_common")
                               else "MIXED: each rater on its own rows"),
                     "spearman": _cell(xa.get("spearman"), ca.get("spearman"), xa.get("n")),
                     "auc_contributor": _cell(xa.get("auc"), ca.get("auc"), xa.get("n"))})
    return {"protocol": ("common resolved set (players every scored source graded that "
                         "preseason); eFV enters with its forward-chained OOS grade, "
                         "never an in-sample fit"),
            "basis": basis,
            "common_n": acc.get("common_n"),
            "common_n_efv": acc.get("common_n_efv"),
            "verdict_vs_consensus": acc.get("head_to_head_verdict"),
            "vs": rivals, "by_archetype_vs_consensus": arch}


def _top20_capture(sb):
    cc = ((sb.get("accuracy") or {}).get("capture_curve")) or {}
    xfv, cons = cc.get("xfv") or {}, cc.get("consensus") or {}
    if xfv.get("top20") is None or cons.get("top20") is None:
        return None
    return {"protocol": ("share of the full graded pool's realized WAR captured by the "
                         "top 20 percent of each board (busts included at 0)"),
            "pool_n": cc.get("pool_n"),
            "top20": _cell(xfv["top20"], cons["top20"], cc.get("pool_n")),
            "curve_area": _cell(xfv.get("area"), cons.get("area"), cc.get("pool_n"))}


def _receipts(sb):
    det = ((sb.get("accuracy") or {}).get("xfv_vs_consensus_detail")) or {}
    if not det:
        return None
    share = det.get("xfv_right_share_on_disagreements")
    return {"protocol": ("resolved players where eFV and consensus placed the player "
                         ">= 15 percentile points apart, pre-debut vintage grades only; "
                         "'right' = whose placement sat closer to the realized-WAR "
                         "placement"),
            "n_pool": det.get("n"),
            "n_disagreements": det.get("n_disagreements"),
            "efv_right_share": share,
            "win": (share is not None and share > 0.5),
            "biggest": det.get("receipts") or []}


# ---------------------------------------------------------------------------
# weak cells
# ---------------------------------------------------------------------------
def _collect_weak(sides, h2h, cap, rec):
    weak = []

    def _chk(path, cell, metric):
        if cell and cell.get("win") is False:
            weak.append({"cell": path, "metric": metric, "n": cell.get("n"),
                         "efv": cell.get("efv"), "consensus": cell.get("consensus"),
                         "margin": cell.get("margin")})

    for side, blk in sides.items():
        for m in ("spearman", "auc_contributor", "auc_star"):
            _chk(f"{side}.pooled", blk["pooled"].get(m), m)
        for tk, cell in (blk.get("by_fv_tier") or {}).items():
            _chk(f"{side}.fv_tier.{tk}", cell, "spearman")
        for ck, cell in (blk.get("by_cohort") or {}).items():
            _chk(f"{side}.cohort.{ck}", cell, "spearman")
        for ek, cell in (blk.get("by_era") or {}).items():
            _chk(f"{side}.era.{ek}", cell.get("spearman"), "spearman")
            _chk(f"{side}.era.{ek}", cell.get("auc_contributor"), "auc_contributor")
        _chk(f"{side}.t45", blk.get("t45"), "spearman")
        _chk(f"{side}.wm", blk.get("wm"), "spearman")
    if h2h:
        for key, r in (h2h.get("vs") or {}).items():
            _chk(f"head_to_head.{key}", r.get("spearman"), "spearman")
            _chk(f"head_to_head.{key}", r.get("auc_contributor"), "auc_contributor")
        for a in h2h.get("by_archetype_vs_consensus") or []:
            _chk(f"head_to_head.archetype.{a['archetype']}", a.get("spearman"), "spearman")
            _chk(f"head_to_head.archetype.{a['archetype']}", a.get("auc_contributor"),
                 "auc_contributor")
    if cap:
        _chk("capture.top20", cap.get("top20"), "war_capture")
        _chk("capture.curve_area", cap.get("curve_area"), "war_capture")
    if rec and rec.get("win") is False:
        weak.append({"cell": "receipts.disagreements", "metric": "right_share",
                     "n": rec.get("n_disagreements"),
                     "efv": rec.get("efv_right_share"), "consensus": 0.5,
                     "margin": (round(rec["efv_right_share"] - 0.5, 4)
                                if rec.get("efv_right_share") is not None else None)})
    return weak


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def build():
    sides = {"hit": _side_block("hit"), "pit": _side_block("pit")}
    sb, sb_fresh = _load_source_backtest()
    # Second leg of the two-metric gate, computed live rather than lifted from
    # data/xfv_eval*.json: those artifacts are rebuilt on the pipeline's cadence, so
    # lifting would leave this scoreboard a rebuild behind its own gate.
    try:
        from efv_model import block_rho_eval
        block = block_rho_eval()
    except Exception as exc:                                  # noqa: BLE001
        print(f"WARN block-rho leg unavailable: {exc}")
        block = {"error": str(exc)}
    h2h = _head_to_head(sb)
    cap = _top20_capture(sb)
    rec = _receipts(sb)
    weak = _collect_weak(sides, h2h, cap, rec)
    return {
        # Local run date (the xfv_eval.json stamp convention; a post-midnight-UTC
        # evening run should still stamp the owner's run day).
        "generated_at": date.today().isoformat(),
        "registration": REGISTRATION,
        "regen_cmd": REGEN_CMD,
        # WHICH PROTOCOL PRODUCED THESE NUMBERS. Without this stamp the Diamond hub
        # printed 0.384 off a frozen 4-fold artifact while the glossary printed 0.351
        # off the live 11-fold one, and nothing on either page said why they differed.
        "basis": {
            "scored_years": list(LAB.SCORED_YEARS),
            "folds": len(LAB.SCORED_YEARS),
            "source_of_folds": "efv_model.SCORED_YEARS (imported, never copied)",
            "pooled_weighting": ("pair-weighted (row weight = observed_seasons/6), the "
                                 "same basis as data/xfv_eval*.json, so the pooled / tier "
                                 "/ cohort Spearman cells reproduce the published headline"),
            "unweighted_cells": ("by_era (it reproduces efv_model._era_split, which is "
                                 "unweighted by construction) and every AUC cell (no AUC "
                                 "in this codebase is weighted)"),
            "mde95_model_vs_consensus": XFV_VS_CONSENSUS_MDE95,
            "mde95_source": "tools/efv_mde_lab.py (data/xfv_mde_floor.json)",
            "note": ("descriptive scoreboard: a win flag here is a raw inequality on "
                     "identical rows, NOT a resolved result. Check the margin against "
                     "mde95_model_vs_consensus before quoting any cell as a win."),
        },
        "legacy_4fold_footnote": LEGACY_4FOLD_FOOTNOTE,
        "purpose": ("G-SCORE scoreboard: the eFV track record in one artifact, every "
                    "cell = eFV vs the consensus baseline on identical rows, win/loss "
                    "marked. Descriptive; the weak_cells list feeds the experiment "
                    "queue (the 2026-07-24 gate file)."),
        "protocol": {
            "pooled": ("forward-chained OOS, debuted cohort, first-6-season bWAR "
                       "(KM-censored target); folds = efv_model.SCORED_YEARS, floors "
                       "train>=50 / test>=12 (efv_lab_runner convention; reproduces "
                       "data/xfv_eval*.json pooled_oos)"),
            "era": ("same read on 2016-2023 folds, floors train>=60 / test>=10 "
                    "(efv_model._era_split convention; reproduces era_split_debuted, "
                    "populating the <=2018 cell)"),
            "labels": {"contributor_war": CONTRIBUTOR_WAR, "star_war": STAR_WAR},
            "baseline": ("consensus = OLS(consensus FV) anchor fit on the same training "
                         "folds; monotone in FV, so its Spearman/AUC equal raw consensus "
                         "FV's"),
        },
        "sides": sides,
        "block_rho": block,
        "head_to_head": h2h,
        "top20_capture": cap,
        "disagreement_receipts": rec,
        "artifact_crosscheck": _artifact_crosscheck(sides),
        "source_backtest_freshness": sb_fresh,
        "weak_cells": weak,
        "weak_cells_note": ("every cell above with win=false, verbatim; these drive "
                            "the experiment queue, they are not smoothed away"),
    }


def _strip_gen(d):
    return {k: v for k, v in d.items() if k != "generated_at"}


def main():
    result = build()
    if OUT_PATH.exists():
        try:
            prev = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        except ValueError:
            prev = None
        if prev and _strip_gen(prev) == _strip_gen(result):
            print(f"unchanged (compare-before-write): {OUT_PATH}")
            _print_summary(result)
            return 0
    OUT_PATH.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    _print_summary(result)
    return 0


def _print_summary(r):
    def f(c, k="efv"):
        v = (c or {}).get(k)
        return "-" if v is None else f"{v:.4f}"

    def wl(c):
        w = (c or {}).get("win")
        return "-" if w is None else ("WIN" if w else "LOSS")

    print("\n=== eFV SCOREBOARD (value / baseline / verdict) ===")
    for side in ("hit", "pit"):
        blk = r["sides"][side]
        p = blk["pooled"]
        print(f"\n[{side}] pooled  rho {f(p['spearman'])}/{f(p['spearman'], 'consensus')} {wl(p['spearman'])}"
              f"  aucC {f(p['auc_contributor'])}/{f(p['auc_contributor'], 'consensus')} {wl(p['auc_contributor'])}"
              f"  aucS {f(p['auc_star'])}/{f(p['auc_star'], 'consensus')} {wl(p['auc_star'])}")
        print(f"  t45 {f(blk['t45'])}/{f(blk['t45'], 'consensus')} {wl(blk['t45'])}"
              f"   wm {f(blk['wm'])}/{f(blk['wm'], 'consensus')} {wl(blk['wm'])}")
        for ek, cell in blk["by_era"].items():
            print(f"  era {ek:<10} rho {f(cell['spearman'])}/{f(cell['spearman'], 'consensus')} {wl(cell['spearman'])}")
        for tk, cell in blk["by_fv_tier"].items():
            print(f"  tier {tk:<9} rho {f(cell)}/{f(cell, 'consensus')} {wl(cell)}  n={cell['n']}")
        for ck, cell in blk["by_cohort"].items():
            print(f"  cohort {ck:<7} rho {f(cell)}/{f(cell, 'consensus')} {wl(cell)}  n={cell['n']}")
    h2h = r.get("head_to_head") or {}
    for key, riv in (h2h.get("vs") or {}).items():
        print(f"h2h vs {key:<17} rho {f(riv['spearman'])}/{f(riv['spearman'], 'consensus')} {wl(riv['spearman'])}"
              f"  aucC {f(riv['auc_contributor'])}/{f(riv['auc_contributor'], 'consensus')} {wl(riv['auc_contributor'])}")
    for a in h2h.get("by_archetype_vs_consensus") or []:
        print(f"h2h arch {a['archetype']:<13} rho {f(a['spearman'])}/{f(a['spearman'], 'consensus')} {wl(a['spearman'])}")
    cap = r.get("top20_capture") or {}
    if cap:
        print(f"top20 capture {f(cap['top20'])}/{f(cap['top20'], 'consensus')} {wl(cap['top20'])}")
    rec = r.get("disagreement_receipts") or {}
    if rec:
        print(f"disagreement right-share {rec.get('efv_right_share')} on n={rec.get('n_disagreements')}"
              f" ({'WIN' if rec.get('win') else 'LOSS'})")
    print(f"\nweak cells: {len(r['weak_cells'])}")
    for w in r["weak_cells"]:
        print(f"  {w['cell']} [{w['metric']}] efv={w['efv']} cons={w['consensus']} margin={w['margin']} n={w['n']}")


if __name__ == "__main__":
    sys.exit(main())
