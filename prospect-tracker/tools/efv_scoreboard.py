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
from prospect_path import _fit_ridge, _predict, _spearman                 # noqa: E402
from source_backtest import _auc                  # noqa: E402

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


def _sp_cell(rows, min_n):
    if len(rows) < min_n:
        return None
    b = _spearman([r["blend"] for r in rows], [r["y"] for r in rows])
    c = _spearman([r["cons"] for r in rows], [r["y"] for r in rows])
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
        sp = _sp_cell(grp, ERA_MIN_N)
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
def _load_source_backtest():
    p = DATA / "source_backtest.json"
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            d = None
        gen = (d or {}).get("generated_at")
        if gen:
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
               "rule": f"reran (artifact missing or older than {SB_MAX_AGE_DAYS} days)"}


def _head_to_head(sb):
    """eFV vs each public rater on the common resolved set (identical players,
    OOS eFV grades). Cells per rival: Spearman + contributor AUC."""
    pooled = ((sb.get("accuracy") or {}).get("pooled")) or {}
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
        xa = (a.get("raters") or {}).get("xfv") or {}
        ca = (a.get("raters") or {}).get("prospx_consensus") or {}
        if xa.get("spearman") is None or ca.get("spearman") is None:
            continue
        arch.append({"archetype": a.get("archetype"), "label": a.get("label"),
                     "n": xa.get("n"),
                     "spearman": _cell(xa.get("spearman"), ca.get("spearman"), xa.get("n")),
                     "auc_contributor": _cell(xa.get("auc"), ca.get("auc"), xa.get("n"))})
    return {"protocol": ("common resolved set (players every scored source graded that "
                         "preseason); eFV enters with its forward-chained OOS grade, "
                         "never an in-sample fit"),
            "common_n": (sb.get("accuracy") or {}).get("common_n"),
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
