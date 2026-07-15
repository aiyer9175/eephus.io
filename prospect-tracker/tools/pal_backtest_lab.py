# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""PAL conversion-screen backtest lab -> data/pal_eval.json (T1-6 harness repair).

Repairs the /pal/ backtest harness (zero model-weight changes) and runs the
pre-registered per-direction gate:

  HARNESS REPAIRS (vs the shipped pal_export backtest)
  1. TRUE pre-season scoring. detect_conversions pairs consecutive qualified
     seasons with gap b - a <= 2 (2020 is excluded from HISTORY_YEARS, and
     injury gaps happen), but the shipped backtest scored year-1
     (pal_export.py:469 `py = e["year"] - 1`), so every gap-2 event lost its
     pre-row and silently dropped from the labeled set (18 events, 12-13
     labeled). The pre row is e["pre"]["season"].
  2. Pedigree/platoon parity. The shipped backtest never set was_starter /
     p_throws on pre-conversion arms, so the +3.0 starter-pedigree nudge (and
     the reverse-platoon read) existed on the LIVE board but not in the
     evaluated scores. Backtested scores must be the deployed scores.
  3. Per-direction evaluation. RP->SP FIT and SP->RP FIT are two different
     0-100 scales (different components, different gating); pooling them into
     one Spearman was never meaningful. Each direction is scored separately
     against SAME-EVENT baselines: pre-year K-BB%, pre-year ERA (negated so
     higher = better), and pre-year REM+ (relievers, RP->SP) / SEM+ (starters,
     SP->RP).
  4. Continuous outcome. pal_export computed war_delta (post-season bWAR minus
     pre-season bWAR) at :490 and never used it at :511. It is the PRIMARY
     outcome here. The held-the-role label keeps two roles: a repaired binary
     reporting read, and a washout-imputation SENSITIVITY (held=None imputed
     as failure) that special-cases year-2019 events - their b+1 season is
     2020, which HISTORY_YEARS excludes, so their held=None is censoring, not
     attrition, and they are never imputed.
  5. Label hygiene. held labels for year-2025 events read the in-progress 2026
     season - excluded until 2026 closes. A b+1 season under CONV_MIN_IP
     (20 IP) is too thin to certify "held the new role a full season" -> None.
  6. Primary war_delta sample = events whose POST season is closed
     (year <= last closed season): a partial in-progress post season deflates
     post_war mechanically. Including the partial-2026 events is reported as a
     sensitivity arm only. (Decision made at lab-write time, before results.)

  PRE-REGISTERED GATE (per direction; seed 20260714, 2000 bootstrap reps):
     retain PROVISIONAL iff rho(FIT, war_delta) >= rho(best baseline) AND the
     bootstrap gap (rho_fit - rho_best_baseline) lo95 > -0.01. ANY direction
     failing downgrades the registry row. The legacy pooled rho (pre_fit vs
     held) is recomputed and kept as a REPORTING FIELD ONLY - it is never the
     gate. (pal.json's live stamp had drifted to 0.288 vs the registered
     0.223; this lab recomputes it from today's data.)

Fetches: StatsAPI season pitching (8 calls), bulk Statcast arsenal/velo per
season (pybaseball), ~1 sitCodes platoon call per historical conversion event
at its TRUE pre-year, one bulk sports/1/players call per season (pitch hand),
one bulk bwar_pitch pull. FanGraphs is not touched.

Run:  python tools/pal_backtest_lab.py [--out PATH] [--results PATH] [--write]
      --write   commit the eval to data/pal_eval.json (default: print only)
      --out     write the proposed eval JSON somewhere else (e.g. a lane
                workspace) without touching data/
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from datetime import date
from pathlib import Path

_HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("EEPHUS_ROOT") or _HERE.parent)
if not (ROOT / "pal_export.py").exists():          # lane-workspace copy: fall back
    for cand in (Path.cwd(), _HERE.parent.parent):
        if (cand / "pal_export.py").exists():
            ROOT = cand
            break
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
# T1-13 lane workspaces: the workspace holds the patched pal_* modules while the
# rest of the platform (bullpen_export, rem_plus, ...) stays in the real repo.
_REPO = os.environ.get("EEPHUS_REPO")
if _REPO:
    sys.path.append(str(Path(_REPO)))
    sys.path.append(str(Path(_REPO) / "tools"))

import bullpen_export as be          # noqa: E402
import pal_conversion as pc          # noqa: E402
import pal_export as pe              # noqa: E402
import rem_plus                      # noqa: E402
import sem_plus                      # noqa: E402
from rem_plus_backtest import _spearman, _ci   # noqa: E402  (shared stats helpers)

EVAL_PATH = ROOT / "data" / "pal_eval.json"

# ---- T1-13: disk caches for the two heavy re-runnable pulls ----------------- #
# (a lane re-runs this lab several times; bwar_pitch is a multi-MB download and
# season pitching is 8 live calls - cache them under .cache/pal_gamelogs)
_T113_CACHE = (Path(os.environ.get("EEPHUS_REPO") or ROOT) / ".cache" / "pal_gamelogs")
_T113_CACHE.mkdir(parents=True, exist_ok=True)

_orig_load_bwar = pe.load_bref_pitcher_war


def _cached_bwar():
    import pickle
    p = _T113_CACHE / "bwar_pitch.pkl"
    if p.exists() and (date.today().toordinal() - date.fromtimestamp(p.stat().st_mtime).toordinal()) < 7:
        try:
            return pickle.loads(p.read_bytes())
        except Exception:
            pass
    out = _orig_load_bwar()
    if out:
        try:
            p.write_bytes(pickle.dumps(out))
        except Exception:
            pass
    return out


pe.load_bref_pitcher_war = _cached_bwar

_orig_load_season_pitching = be.load_season_pitching


def _cached_season_pitching(season: int):
    import time as _t
    p = _T113_CACHE / f"season_pitching_{int(season)}.json"
    ttl = 6 * 3600 if int(season) >= date.today().year else 30 * 86400
    if p.exists() and _t.time() - p.stat().st_mtime <= ttl:
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    rows = _orig_load_season_pitching(season)
    if rows:
        try:
            p.write_text(json.dumps(rows), encoding="utf-8")
        except Exception:
            pass
    return rows


be.load_season_pitching = _cached_season_pitching

try:  # pybaseball's own disk cache (outside the repo) for arsenal/velo/bwar CSVs
    import pybaseball as _pyb
    _pyb.cache.enable()
except Exception:
    pass

SEED = 20260714
BOOT = 2000
GATE_LO95 = -0.01
HISTORY_YEARS = pe.HISTORY_YEARS                 # [2018, 2019, 2021, ..., 2026]
LAST_CLOSED = date.today().year - 1              # last completed MLB season
CENSOR_YEARS = {2019}                            # b+1 = 2020, excluded from HISTORY_YEARS
DIRECTIONS = ("RP->SP", "SP->RP")


# --------------------------------------------------------------------------- #
# stats helpers (rho + bootstrap gap CI; _spearman/_ci come from rem_plus_backtest)
# --------------------------------------------------------------------------- #
def _rho(xs, ys):
    r = _spearman(list(xs), list(ys))
    return None if r is None else round(r, 4)


def _boot_gap(fit, base, tgt, seed=SEED, reps=BOOT):
    """Bootstrap CI on rho(fit,tgt) - rho(base,tgt), resampling events."""
    n = len(tgt)
    if n < 4:
        return None
    rng = random.Random(seed)
    gaps = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        f = _spearman([fit[i] for i in idx], [tgt[i] for i in idx])
        b = _spearman([base[i] for i in idx], [tgt[i] for i in idx])
        if f is None or b is None:
            continue
        gaps.append(f - b)
    return _ci(gaps)


# --------------------------------------------------------------------------- #
# per-season baseline indices (REM+ for relievers, SEM+ for starters)
# --------------------------------------------------------------------------- #
def season_rem_raw(rows: list) -> dict:
    """{mlbam: rem_plus_raw} for the season's true relievers."""
    rel = be.build_relievers(rows, {}, {})
    pool_in = [r for r in rel if rem_plus.is_true_reliever(r)]
    for r in pool_in:
        rem_plus.derive_rates(r)
    pool = rem_plus.build_pool(pool_in)
    out = {}
    for r in pool_in:
        if rem_plus.rem_plus(r, pool) is not None:
            out[int(r.key)] = r.rem_plus_raw
    return out


def season_sem_raw(rows: list) -> dict:
    """{mlbam: sem_plus_raw} for the season's true starters."""
    starters = []
    for r in rows:
        starters.append(sem_plus.Starter(
            key=str(r["mlbam"]), mlbam=int(r["mlbam"]), name=r.get("name", ""),
            g=pc._num(r.get("G")) or 0.0, gs=pc._num(r.get("GS")) or 0.0,
            ip=be.ip_to_float(r.get("IP")), tbf=pc._num(r.get("BF")) or 0.0,
            so=pc._num(r.get("SO")) or 0.0, bb=pc._num(r.get("BB")) or 0.0,
            hbp=pc._num(r.get("HBP")) or 0.0, hr=pc._num(r.get("HR")) or 0.0,
            er=pc._num(r.get("ER")) or 0.0, r=pc._num(r.get("R")) or 0.0,
            go=pc._num(r.get("GO")) or 0.0, ao=pc._num(r.get("AO")) or 0.0,
        ))
    pool_in = [s for s in starters if sem_plus.is_true_starter(s)]
    for s in pool_in:
        sem_plus.derive_rates(s)
    pool = sem_plus.build_pool(pool_in)
    out = {}
    for s in pool_in:
        if sem_plus.sem_plus(s, pool) is not None:
            out[int(s.key)] = s.sem_plus_raw
    return out


# --------------------------------------------------------------------------- #
# repaired label
# --------------------------------------------------------------------------- #
def repaired_held(byyr: dict, event: dict):
    """Held-the-role label with the T1-6 hygiene: b+1 must be a CLOSED season
    (excludes year-2025 events until 2026 closes) with a real sample
    (>= CONV_MIN_IP), else None."""
    b = event["year"]
    rb = event["direction"].split("->")[1]
    nxt = b + 1
    if nxt > LAST_CLOSED or nxt not in byyr:
        return None
    row = byyr[nxt]
    if be.ip_to_float(row.get("IP")) < pc.CONV_MIN_IP:
        return None
    rn = pc.role_of(row.get("G"), row.get("GS"), row.get("IP"))
    return (rn == rb) if rn else None


def washout_held(byyr: dict, event: dict, held):
    """SENSITIVITY label: a held=None event whose b+1 season is closed and NOT
    the 2020 censor (year-2019 events) is imputed as a failure - the pitcher
    did not hold the new role a full season (washed out / <20 IP / no MLB
    season). Censored/pending events stay None."""
    if held is not None:
        return held
    b = event["year"]
    if b in CENSOR_YEARS or (b + 1) > LAST_CLOSED:
        return None
    return False


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def run(log=print, _ctx=None) -> dict:
    log(f"pal-lab: loading season pitching {HISTORY_YEARS[0]}-{HISTORY_YEARS[-1]}...")
    by_pid: dict = {}
    rows_by_year: dict = {}
    for y in HISTORY_YEARS:
        rows = be.load_season_pitching(y)
        rows_by_year[y] = rows
        for r in rows:
            r = dict(r)
            r["season"] = y
            by_pid.setdefault(r["mlbam"], {})[y] = r
        log(f"  {y}: {len(rows)} pitcher rows")

    events = pc.detect_conversions(by_pid)      # historical only (no in-progress)
    gap2 = [e for e in events if e["pre"]["season"] != e["year"] - 1]
    log(f"pal-lab: {len(events)} historical conversion events "
        f"({len(gap2)} gap-2 pairs the shipped backtest dropped)")

    log("pal-lab: pulling bulk arsenal + velo per season...")
    arsenal_by_year = {y: pe.load_arsenal(y) for y in HISTORY_YEARS}
    velo_by_year = {y: pe.load_velo(y) for y in HISTORY_YEARS}

    # platoon at the TRUE pre-year of each event (~1 sitCodes call per event)
    pre_pairs = sorted({(e["mlbam"], e["pre"]["season"]) for e in events})
    log(f"pal-lab: pulling platoon splits for {len(pre_pairs)} true pre-year pitcher-seasons...")
    platoon = pe.load_platoon(pre_pairs)

    # pitch hand: one bulk players call per season, merged (hand is static)
    hand: dict = {}
    for y in HISTORY_YEARS:
        hand.update(pe.load_pitch_hand(y) or {})
        pe.load_pitch_hand.cache_clear()         # stock lru maxsize=4; keep it honest
    log(f"pal-lab: pitch hand known for {len(hand)} pitchers")

    log("pal-lab: pulling bref pitcher WAR (bulk)...")
    war_by_year = pe.load_bref_pitcher_war()
    log(f"pal-lab: bref WAR seasons loaded: {sorted(war_by_year)[-5:] if war_by_year else 'NONE'}")

    # per-season baseline indices
    rem_by_year = {y: season_rem_raw(rows_by_year[y]) for y in HISTORY_YEARS}
    sem_by_year = {y: season_sem_raw(rows_by_year[y]) for y in HISTORY_YEARS}

    # ---- score every event on the REPAIRED harness -------------------------
    recs = []
    for e in events:
        py = e["pre"]["season"]                          # TRUE pre-season (repair 1)
        byyr = by_pid.get(e["mlbam"], {})
        pre_row = byyr.get(py)
        fit = None
        if pre_row and pre_row.get("mlbam") in arsenal_by_year.get(py, {}):
            arm = pe.build_arm(pre_row, arsenal_by_year.get(py, {}),
                               velo_by_year.get(py, {}), platoon, py)
            arm.p_throws = hand.get(arm.mlbam)           # repair 2
            arm.was_starter = pe._was_starter(by_pid, arm.mlbam, py)
            f = pc.rp_sp_fit(arm) if e["direction"] == "RP->SP" else pc.sp_rp_fit(arm)
            if arm.arsenal:
                fit = f["fit"]
        pre_war = (war_by_year.get(py) or {}).get(e["mlbam"])
        post_war = (war_by_year.get(e["post"]["season"]) or {}).get(e["mlbam"])
        war_delta = None if pre_war is None or post_war is None else post_war - pre_war
        held = repaired_held(byyr, e)
        kbb = (None if e["pre"]["k_pct"] is None or e["pre"]["bb_pct"] is None
               else e["pre"]["k_pct"] - e["pre"]["bb_pct"])
        era = e["pre"]["era"]
        idx = (rem_by_year if e["direction"] == "RP->SP" else sem_by_year)
        recs.append({
            "mlbam": e["mlbam"], "name": e["name"], "direction": e["direction"],
            "year": e["year"], "pre_season": py, "fit": fit,
            "war_delta": war_delta, "post_closed": e["year"] <= LAST_CLOSED,
            "held": held, "held_washout": washout_held(byyr, e, held),
            "b_kbb": kbb, "b_neg_era": None if era is None else -era,
            "b_index": (idx.get(py) or {}).get(e["mlbam"]),
        })

    # ---- per-direction gate -------------------------------------------------
    baselines = [("kbb_pre", "b_kbb"), ("neg_era_pre", "b_neg_era"), ("index_pre", "b_index")]
    per_dir = {}
    all_pass = True
    for d in DIRECTIONS:
        dr = [r for r in recs if r["direction"] == d]
        prim = [r for r in dr if r["post_closed"] and r["fit"] is not None
                and r["war_delta"] is not None
                and all(r[k] is not None for _, k in baselines)]
        fit = [r["fit"] for r in prim]
        tgt = [r["war_delta"] for r in prim]
        rho_fit = _rho(fit, tgt)
        base_rhos, gaps = {}, {}
        for name, key in baselines:
            bvals = [r[key] for r in prim]
            base_rhos[name] = _rho(bvals, tgt)
            gaps[name] = _boot_gap(fit, bvals, tgt)
        live = {k: v for k, v in base_rhos.items() if v is not None}
        best_name = max(live, key=live.get) if live else None
        best_rho = live.get(best_name)
        gap_best = gaps.get(best_name)
        ok = (rho_fit is not None and best_rho is not None and gap_best is not None
              and rho_fit >= best_rho and gap_best["lo95"] > GATE_LO95)
        all_pass = all_pass and ok

        # reporting arms (never the gate)
        held_lab = [r for r in dr if r["fit"] is not None and r["held"] is not None]
        wash_lab = [r for r in dr if r["fit"] is not None and r["held_washout"] is not None]
        war_all = [r for r in dr if r["fit"] is not None and r["war_delta"] is not None]
        per_dir[d] = {
            "n_events": len(dr),
            "n_gate": len(prim),
            "rho_fit_war_delta": rho_fit,
            "baseline_rho_war_delta": base_rhos,
            "best_baseline": best_name,
            "gap_ci_vs_best": gap_best,
            "gap_ci_vs_each": gaps,
            "gate": {"rule": "rho(FIT,war_delta) >= rho(best baseline) AND gap lo95 > -0.01",
                     "seed": SEED, "boot": BOOT, "pass": bool(ok)},
            "sensitivity": {
                "rho_fit_held_repaired": _rho([r["fit"] for r in held_lab],
                                              [1.0 if r["held"] else 0.0 for r in held_lab]),
                "n_held_repaired": len(held_lab),
                "rho_fit_held_washout_imputed": _rho([r["fit"] for r in wash_lab],
                                                     [1.0 if r["held_washout"] else 0.0 for r in wash_lab]),
                "n_held_washout": len(wash_lab),
                "rho_fit_war_delta_incl_partial_2026": _rho([r["fit"] for r in war_all],
                                                            [r["war_delta"] for r in war_all]),
                "n_war_incl_partial": len(war_all),
            },
        }
        log(f"pal-lab: {d}: n_gate={len(prim)} rho_fit={rho_fit} "
            f"best_baseline={best_name}={best_rho} gap_lo95="
            f"{gap_best['lo95'] if gap_best else None} -> {'PASS' if ok else 'FAIL'}")

    # ---- legacy pooled rho (REPORTING ONLY): replicate the shipped harness --
    leg_fits, leg_labels = [], []
    for e in events:
        py = e["year"] - 1                              # the shipped bug, verbatim
        pre_row = by_pid.get(e["mlbam"], {}).get(py)
        pre_fit = None
        if pre_row and pre_row.get("mlbam") in arsenal_by_year.get(py, {}):
            arm = pe.build_arm(pre_row, arsenal_by_year.get(py, {}),
                               velo_by_year.get(py, {}), platoon, py)
            f = pc.rp_sp_fit(arm) if e["direction"] == "RP->SP" else pc.sp_rp_fit(arm)
            if arm.arsenal:
                pre_fit = f["fit"]
        if pre_fit is not None and e.get("held") is not None:
            leg_fits.append(pre_fit)
            leg_labels.append(1.0 if e["held"] else 0.0)
    legacy = {
        "note": ("Shipped-harness replication (year-1 pre-row, no pedigree/p_throws, "
                 "unrepaired held labels), POOLED across the two fit scales. Reporting "
                 "field only - never the gate."),
        "n_labeled": len(leg_fits),
        "spearman_prefit_vs_held": _rho(leg_fits, leg_labels),
        "registered_stamp": 0.223,
        "live_pal_json_stamp": 0.288,
    }
    log(f"pal-lab: legacy pooled rho (replicated today) = {legacy['spearman_prefit_vs_held']} "
        f"(n={legacy['n_labeled']}; registered 0.223, live stamp 0.288)")

    status = "provisional" if all_pass else "downgraded"
    eval_doc = {
        "generated_at": date.today().isoformat(),
        "model": "pal_conversion",
        "lab": "tools/pal_backtest_lab.py (T1-6 harness repair)",
        "seasons": HISTORY_YEARS,
        "last_closed_season": LAST_CLOSED,
        "n_conversions": len(events),
        "n_gap2_recovered": len(gap2),
        "primary_outcome": ("war_delta: bref bWAR(post season) - bWAR(pre season), "
                            "closed post seasons only; per direction, never pooled"),
        "baselines": ["pre-year K-BB%", "pre-year ERA (negated)",
                      "pre-year REM+ (RP->SP) / SEM+ (SP->RP)"],
        "per_direction": per_dir,
        "legacy_pooled": legacy,
        "verdict": {
            "status": status,
            "gate": ("per direction: rho(FIT, war_delta) >= rho(best baseline) with "
                     f"bootstrap gap lo95 > {GATE_LO95} (seed {SEED}, {BOOT} reps); "
                     "any direction failing downgrades the registry row"),
            "summary": _summary(per_dir, legacy, status, len(events), len(gap2)),
        },
    }
    if _ctx is not None:      # T1-13: expose the assembled inputs for the lane arms
        _ctx.update(dict(
            by_pid=by_pid, rows_by_year=rows_by_year, events=events, recs=recs,
            arsenal_by_year=arsenal_by_year, velo_by_year=velo_by_year,
            platoon=platoon, hand=hand, war_by_year=war_by_year,
            rem_by_year=rem_by_year, sem_by_year=sem_by_year, per_dir=per_dir,
        ))
    return eval_doc


def _summary(per_dir, legacy, status, n_events, n_gap2) -> str:
    parts = []
    for d, v in per_dir.items():
        g = v["gap_ci_vs_best"] or {}
        parts.append(f"{d}: rho_fit={v['rho_fit_war_delta']} vs best baseline "
                     f"{v['best_baseline']}={v['baseline_rho_war_delta'].get(v['best_baseline'])} "
                     f"(gap lo95 {g.get('lo95')}, n={v['n_gate']}) -> "
                     f"{'PASS' if v['gate']['pass'] else 'FAIL'}")
    return (f"T1-6 repaired harness: {n_events} conversions (true pre-season scoring "
            f"recovered {n_gap2} gap-2 events; pedigree/p_throws set on backtest arms; "
            f"held labels IP-gated + 2025-pending excluded + 2019 censor-aware). "
            f"Primary outcome = continuous war_delta, per direction. "
            + " | ".join(parts) +
            f". Legacy pooled rho (reporting only) = {legacy['spearman_prefit_vs_held']} "
            f"(registered 0.223; stale live stamp 0.288). Verdict: {status.upper()}.")


# =========================================================================== #
# T1-13: PAL game-log walk (Lane A recovery sensitivity + Lane B usage lane)
# =========================================================================== #
import pal_gamelogs as pg                                     # noqa: E402
from plus_lab_harness import (zscore_within, cluster_boot_gaps,   # noqa: E402
                              cluster_summary)

SEED_B = 20260715      # Lane B pre-registered seed
BASELINES = [("kbb_pre", "b_kbb"), ("neg_era_pre", "b_neg_era"), ("index_pre", "b_index")]


def _identity_check(by_pid) -> dict:
    """Legacy event set must reproduce BYTE-IDENTICAL from the workspace
    pal_conversion (recovery lives in pal_gamelogs and returns tagged events
    only - detect_conversions is untouched). Compares against the REAL repo
    module loaded by file path."""
    import hashlib
    import importlib.util
    repo = Path(os.environ.get("EEPHUS_REPO") or ROOT)
    spec = importlib.util.spec_from_file_location("_pc_repo_t113", repo / "pal_conversion.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["_pc_repo_t113"] = m       # dataclasses needs the module registered
    spec.loader.exec_module(m)
    a = json.dumps(pc.detect_conversions(by_pid), sort_keys=True)
    b = json.dumps(m.detect_conversions(by_pid), sort_keys=True)
    return {
        "byte_identical": a == b,
        "workspace_sha256": hashlib.sha256(a.encode()).hexdigest(),
        "repo_sha256": hashlib.sha256(b.encode()).hexdigest(),
        "n_events": len(pc.detect_conversions(by_pid)),
    }


def _score_events(events, ctx, usage_map=None) -> list:
    """run()'s event-scoring block, replicated verbatim, plus (T1-13 Lane B)
    fit_v2/stamina for RP->SP events when a usage read exists."""
    usage_map = usage_map or {}
    recs = []
    for e in events:
        py = e["pre"]["season"]
        byyr = ctx["by_pid"].get(e["mlbam"], {})
        pre_row = byyr.get(py)
        fit = fit_v2 = stamina = None
        if pre_row and pre_row.get("mlbam") in ctx["arsenal_by_year"].get(py, {}):
            arm = pe.build_arm(pre_row, ctx["arsenal_by_year"].get(py, {}),
                               ctx["velo_by_year"].get(py, {}), ctx["platoon"], py)
            arm.p_throws = ctx["hand"].get(arm.mlbam)
            arm.was_starter = pe._was_starter(ctx["by_pid"], arm.mlbam, py)
            f = pc.rp_sp_fit(arm) if e["direction"] == "RP->SP" else pc.sp_rp_fit(arm)
            if arm.arsenal:
                fit = f["fit"]
                if e["direction"] == "RP->SP":
                    usage = usage_map.get((e["mlbam"], py))
                    f2 = pc.rp_sp_fit_v2(arm, usage)
                    fit_v2 = f2["fit"]
                    stamina = f2["components"].get("stamina_usage")
        pre_war = (ctx["war_by_year"].get(py) or {}).get(e["mlbam"])
        post_war = (ctx["war_by_year"].get(e["post"]["season"]) or {}).get(e["mlbam"])
        war_delta = None if pre_war is None or post_war is None else post_war - pre_war
        held = repaired_held(byyr, e)
        kbb = (None if e["pre"]["k_pct"] is None or e["pre"]["bb_pct"] is None
               else e["pre"]["k_pct"] - e["pre"]["bb_pct"])
        era = e["pre"]["era"]
        idx = (ctx["rem_by_year"] if e["direction"] == "RP->SP" else ctx["sem_by_year"])
        recs.append({
            "mlbam": e["mlbam"], "name": e["name"], "direction": e["direction"],
            "year": e["year"], "pre_season": py, "fit": fit,
            "fit_v2": fit_v2, "stamina": stamina,
            "recovered": e.get("recovered"),
            "war_delta": war_delta, "post_closed": e["year"] <= LAST_CLOSED,
            "held": held, "held_washout": washout_held(byyr, e, held),
            "b_kbb": kbb, "b_neg_era": None if era is None else -era,
            "b_index": (idx.get(py) or {}).get(e["mlbam"]),
        })
    return recs


def _gate_direction(dr, seed=SEED, boot=BOOT) -> dict:
    """run()'s per-direction gate block on an arbitrary rec list (one
    direction), plus the harness-v2 companion (within-post-season z target +
    player-clustered season-stratified bootstrap) reported alongside."""
    prim = [r for r in dr if r["post_closed"] and r["fit"] is not None
            and r["war_delta"] is not None
            and all(r[k] is not None for _, k in BASELINES)]
    fit = [r["fit"] for r in prim]
    tgt = [r["war_delta"] for r in prim]
    rho_fit = _rho(fit, tgt)
    base_rhos, gaps = {}, {}
    for name, key in BASELINES:
        bvals = [r[key] for r in prim]
        base_rhos[name] = _rho(bvals, tgt)
        gaps[name] = _boot_gap(fit, bvals, tgt, seed=seed, reps=boot)
    live = {k: v for k, v in base_rhos.items() if v is not None}
    best_name = max(live, key=live.get) if live else None
    best_rho = live.get(best_name)
    gap_best = gaps.get(best_name)
    ok = (rho_fit is not None and best_rho is not None and gap_best is not None
          and rho_fit >= best_rho and gap_best["lo95"] > GATE_LO95)

    # ---- harness v2 companion (convention v2; reported, never the v1 gate) --
    v2 = None
    if len(prim) >= 4:
        tgt_z = zscore_within([r["year"] for r in prim], tgt)
        players = [r["mlbam"] for r in prim]
        preds = [r["pre_season"] for r in prim]
        rho_fit_z = _rho(fit, tgt_z)
        base_z = {name: _rho([r[key] for r in prim], tgt_z) for name, key in BASELINES}
        live_z = {k: v for k, v in base_z.items() if v is not None}
        best_z = max(live_z, key=live_z.get) if live_z else None
        cgaps = cluster_boot_gaps(fit, {name: [r[key] for r in prim] for name, key in BASELINES},
                                  tgt_z, players, preds, BOOT, seed)
        gap_best_z = cgaps.get(best_z)
        ok_z = (rho_fit_z is not None and best_z is not None and gap_best_z is not None
                and rho_fit_z >= live_z[best_z] and gap_best_z["lo95"] > GATE_LO95)
        v2 = {"rho_fit_war_delta_z": rho_fit_z, "baseline_rho_z": base_z,
              "best_baseline": best_z, "cluster_gap_ci_vs_best": gap_best_z,
              "cluster": cluster_summary(players, preds), "pass_under_v2": bool(ok_z)}

    return {
        "n_gate": len(prim),
        "rho_fit_war_delta": rho_fit,
        "baseline_rho_war_delta": base_rhos,
        "best_baseline": best_name,
        "gap_ci_vs_best": gap_best,
        "gate": {"rule": "rho(FIT,war_delta) >= rho(best baseline) AND gap lo95 > -0.01",
                 "seed": seed, "boot": boot, "pass": bool(ok)},
        "harness_v2": v2,
        "sensitivity": {
            "rho_fit_held_repaired": _rho(
                [r["fit"] for r in dr if r["fit"] is not None and r["held"] is not None],
                [1.0 if r["held"] else 0.0 for r in dr if r["fit"] is not None and r["held"] is not None]),
            "n_held_repaired": sum(1 for r in dr if r["fit"] is not None and r["held"] is not None),
        },
    }


def _lane_b_gate(recs_rpsp, seed=SEED_B, boot=BOOT) -> dict:
    """Lane B pre-registered gate (declared before results; convention v1):
    on the EXPANDED RP->SP labeled set (legacy + recovered; post_closed, both
    fits + war_delta present):
      (1) sign-check: rho(stamina_usage score, war_delta) > 0 (events with a
          usage read),
      (2) delta-rho point: rho(fit_v2, war_delta) - rho(fit, war_delta) > 0,
      (3) bootstrap gap lo95 >= -0.01 (seed 20260715, 2000 reps, iid v1),
      (4) sign agreement: reported - is rho(fit_v2, war_delta) itself > 0?
          (RP->SP's incumbent rho is sign-wrong; a lane can help relatively
          while the direction stays unvalidated.)
    Ceiling: PROVISIONAL, and only as an RP->SP candidate lane - never a
    weight change shipped from this lane. v2 companion reported alongside."""
    prim = [r for r in recs_rpsp if r["post_closed"] and r["fit"] is not None
            and r["fit_v2"] is not None and r["war_delta"] is not None]
    fit = [r["fit"] for r in prim]
    fit2 = [r["fit_v2"] for r in prim]
    tgt = [r["war_delta"] for r in prim]
    rho_inc = _rho(fit, tgt)
    rho_v2 = _rho(fit2, tgt)
    stam = [(r["stamina"], r["war_delta"]) for r in prim if r["stamina"] is not None]
    rho_stamina = _rho([s for s, _ in stam], [w for _, w in stam])
    gap = _boot_gap(fit2, fit, tgt, seed=seed, reps=boot)
    delta = None if rho_inc is None or rho_v2 is None else round(rho_v2 - rho_inc, 4)
    sign_ok = rho_stamina is not None and rho_stamina > 0
    delta_ok = delta is not None and delta > 0
    ci_ok = gap is not None and gap["lo95"] >= -0.01
    # v2 companion: z target + clustered CI
    v2 = None
    if len(prim) >= 4:
        tgt_z = zscore_within([r["year"] for r in prim], tgt)
        cg = cluster_boot_gaps(fit2, {"incumbent_fit": fit}, tgt_z,
                               [r["mlbam"] for r in prim], [r["pre_season"] for r in prim],
                               boot, seed)["incumbent_fit"]
        rho_v2_z, rho_inc_z = _rho(fit2, tgt_z), _rho(fit, tgt_z)
        v2 = {"rho_fit_v2_z": rho_v2_z, "rho_incumbent_z": rho_inc_z,
              "delta_rho_z": (None if rho_v2_z is None or rho_inc_z is None
                              else round(rho_v2_z - rho_inc_z, 4)),
              "cluster_gap_ci": cg,
              "pass_under_v2": bool(sign_ok and rho_v2_z is not None and rho_inc_z is not None
                                    and rho_v2_z - rho_inc_z > 0 and cg and cg["lo95"] >= -0.01)}
    return {
        "n_gate": len(prim), "n_with_usage_read": len(stam),
        "rho_incumbent_fit": rho_inc, "rho_fit_v2": rho_v2,
        "rho_stamina_feature": rho_stamina,
        "delta_rho": delta, "gap_ci_v2_minus_incumbent": gap,
        "gate": {
            "rule": ("sign-check rho(stamina,war_delta) > 0 AND delta-rho point > 0 AND "
                     "gap lo95 >= -0.01 vs incumbent FIT on the expanded labeled set"),
            "seed": seed, "boot": boot,
            "sign_check_pass": bool(sign_ok), "delta_rho_pass": bool(delta_ok),
            "ci_pass": bool(ci_ok), "pass": bool(sign_ok and delta_ok and ci_ok),
        },
        "direction_sign_agreement_vs_war_delta": (None if rho_v2 is None else bool(rho_v2 > 0)),
        "harness_v2": v2,
        "ceiling": "provisional (candidate lane only; RP->SP direction remains downgraded)",
    }


def _census(by_pid, log=print) -> dict:
    """Lane C fast-fail label census (exploratory; these labels feed NOTHING).
    Ladder: all SWING seasons -> >=20 IP -> strict mid-year switch -> switch
    with a clean old-role anchor (the recoverable attempts)."""
    years = set(HISTORY_YEARS)
    hist_years = {y for y in years if y <= LAST_CLOSED}
    swing_any = [(p, y) for p, byyr in by_pid.items() for y, row in byyr.items()
                 if pc.role_of(row.get("G"), row.get("GS"), row.get("IP")) == "SWING"]
    swing_20 = pg.swing_seasons(by_pid, years=years)
    swing_20_hist = [(p, y) for p, y in swing_20 if y in hist_years]
    return {
        "raw_swing_seasons_any_ip": len(swing_any),
        "raw_swing_seasons_20ip_all_years": len(swing_20),
        "raw_swing_seasons_20ip_historical": len(swing_20_hist),
        "note": ("strict-switch and anchored-attempt counts are filled in by "
                 "run_t113 after the game-log walk"),
    }


def run_t113(out_dir: Path, log=print) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- arm 0: the incumbent lab, verbatim (its own seed / gate) -----------
    ctx: dict = {}
    doc0 = run(log=log, _ctx=ctx)
    by_pid, events = ctx["by_pid"], ctx["events"]

    # ---- byte-identity of the legacy event set ------------------------------
    ident = _identity_check(by_pid)
    log(f"t113: legacy event set byte-identical={ident['byte_identical']} "
        f"(n={ident['n_events']})")

    # ---- Lane C census (pre-recovery counts) --------------------------------
    census = _census(by_pid, log=log)

    # ---- Lane A: game-log walk + recovery -----------------------------------
    recovered = pg.recover_events(by_pid, HISTORY_YEARS, events, log=log)
    n_mid = sum(1 for e in recovered if e["recovered"] == "mid_year")
    n_bridge = sum(1 for e in recovered if e["recovered"] == "swing_bridge")
    log(f"t113: recovered {len(recovered)} tagged events "
        f"({n_mid} mid-year, {n_bridge} swing-bridge)")

    # census: strict-switch counts over the walked SWING seasons
    swings = pg.swing_seasons(by_pid, years=set(HISTORY_YEARS))
    strict_hits = []
    for pid, y in swings:
        sw = pg.detect_midyear_switch(pg.appearances(pid, y))
        if sw:
            strict_hits.append({"mlbam": pid, "season": y,
                                "name": by_pid[pid][y].get("name", ""),
                                "direction": sw["direction"],
                                "pre_seg": sw["pre"], "post_seg": sw["post"]})
    census["strict_midyear_switches"] = len(strict_hits)
    census["anchored_midyear_attempts"] = n_mid
    census["swing_bridge_recoveries"] = n_bridge
    census["plausible_true_attempts_total"] = len(recovered)

    # hand-audit dump: 20 deterministic samples of the strict switches
    rngc = random.Random(SEED_B)
    audit = rngc.sample(strict_hits, min(20, len(strict_hits)))
    audit_rows = []
    for h in audit:
        apps = pg.appearances(h["mlbam"], h["season"])
        audit_rows.append({**h, "sequence": [
            f"{a['date']}{'*' if a['start'] else ''}({a['outs']})" for a in apps]})
    (out_dir / "hand_audit.json").write_text(json.dumps(audit_rows, indent=1), encoding="utf-8")
    log(f"t113: wrote {len(audit_rows)}-event hand-audit dump")

    # ---- platoon top-up for recovered pre-years -----------------------------
    need = sorted({(e["mlbam"], e["pre"]["season"]) for e in recovered}
                  - set(ctx["platoon"].keys()))
    if need:
        log(f"t113: pulling platoon splits for {len(need)} recovered pre-years...")
        ctx["platoon"].update(pe.load_platoon(need))

    # ---- Lane B usage features for every RP->SP pre-year ---------------------
    usage_map = {}
    rp_pre = sorted({(e["mlbam"], e["pre"]["season"])
                     for e in list(events) + recovered if e["direction"] == "RP->SP"})
    log(f"t113: game-log usage features for {len(rp_pre)} RP->SP pre-years...")
    for pid, y in rp_pre:
        usage_map[(pid, y)] = pg.relief_usage_features(pg.appearances(pid, y))

    # ---- rescore: legacy (consistency-checked) + recovered -------------------
    recs_legacy = _score_events(events, ctx, usage_map)
    mismatch = 0
    for a, b in zip(recs_legacy, ctx["recs"]):
        for k in ("fit", "war_delta", "held", "b_kbb", "b_neg_era", "b_index"):
            if a[k] != b[k]:
                mismatch += 1
    log(f"t113: legacy rescore consistency mismatches = {mismatch} (must be 0)")
    recs_rec = _score_events(recovered, ctx, usage_map)
    labelable = [r for r in recs_rec if r["post_closed"] and r["fit"] is not None
                 and r["war_delta"] is not None]
    log(f"t113: recovered events labelable for the war_delta gate: {len(labelable)}")

    # ---- Arm A: expanded per-direction sensitivity (incumbent gate machinery) -
    arm_a = {}
    for d in DIRECTIONS:
        legacy_d = [r for r in recs_legacy if r["direction"] == d]
        exp_d = legacy_d + [r for r in recs_rec if r["direction"] == d]
        ga_legacy = _gate_direction(legacy_d)
        ga_exp = _gate_direction(exp_d)
        arm_a[d] = {"legacy": ga_legacy, "expanded": ga_exp,
                    "n_recovered_in_gate": ga_exp["n_gate"] - ga_legacy["n_gate"]}
        log(f"t113 armA {d}: legacy rho={ga_legacy['rho_fit_war_delta']} "
            f"(n={ga_legacy['n_gate']}, pass={ga_legacy['gate']['pass']}) -> expanded "
            f"rho={ga_exp['rho_fit_war_delta']} (n={ga_exp['n_gate']}, "
            f"pass={ga_exp['gate']['pass']}, v2={ga_exp['harness_v2'] and ga_exp['harness_v2']['pass_under_v2']})")

    # ---- Arm B: usage lane gate on the expanded RP->SP set -------------------
    rpsp_exp = ([r for r in recs_legacy if r["direction"] == "RP->SP"]
                + [r for r in recs_rec if r["direction"] == "RP->SP"])
    arm_b = _lane_b_gate(rpsp_exp)
    log(f"t113 armB: n={arm_b['n_gate']} rho_inc={arm_b['rho_incumbent_fit']} "
        f"rho_v2={arm_b['rho_fit_v2']} rho_stamina={arm_b['rho_stamina_feature']} "
        f"delta={arm_b['delta_rho']} lo95={arm_b['gap_ci_v2_minus_incumbent'] and arm_b['gap_ci_v2_minus_incumbent']['lo95']} "
        f"-> pass={arm_b['gate']['pass']}")

    # ---- current pool demo (display-only): fit vs fit_v2 on 2026 relievers ---
    season = HISTORY_YEARS[-1]
    pool_rows = []
    cur = ctx["rows_by_year"].get(season) or []
    for r in cur:
        if be.ip_to_float(r.get("IP")) < pe.CAND_MIN_IP:
            continue
        if pc.role_of(r.get("G"), r.get("GS"), r.get("IP")) != "RP":
            continue
        if r["mlbam"] not in ctx["arsenal_by_year"].get(season, {}):
            continue
        arm = pe.build_arm(r, ctx["arsenal_by_year"][season], ctx["velo_by_year"][season],
                           ctx["platoon"], season)   # platoon mostly absent here (noted)
        arm.p_throws = ctx["hand"].get(arm.mlbam)
        arm.was_starter = pe._was_starter(by_pid, arm.mlbam, season)
        usage = pg.relief_usage_features(pg.appearances(arm.mlbam, season))
        f1 = pc.rp_sp_fit(arm)
        f2 = pc.rp_sp_fit_v2(arm, usage)
        pool_rows.append({"mlbam": arm.mlbam, "name": arm.name, "team": arm.team,
                          "fit": f1["fit"], "fit_v2": f2["fit"],
                          "delta": round(f2["fit"] - f1["fit"], 1),
                          "usage": usage})
    pool_rows.sort(key=lambda x: abs(x["delta"]), reverse=True)
    with_usage = [p for p in pool_rows if p["usage"]]
    mis = sorted(p["usage"]["multi_inning_share"] for p in with_usage)
    b2b = sorted(p["usage"]["b2b_rate"] for p in with_usage)

    def _q(v, q):
        return v[int(q * (len(v) - 1))] if v else None

    pool = {
        "season": season, "n_rp_candidates": len(pool_rows),
        "n_with_usage_read": len(with_usage),
        "multi_inning_share_quartiles": [_q(mis, q) for q in (0.25, 0.5, 0.75)],
        "b2b_rate_quartiles": [_q(b2b, q) for q in (0.25, 0.5, 0.75)],
        "top_movers": pool_rows[:12],
        "note": ("platoon splits were not pulled for the pool (event pre-years only), "
                 "so platoon_neutrality drops from both blends equally; deltas are "
                 "internally consistent. Display demo only - nothing ships from here."),
    }
    log(f"t113 pool: {len(pool_rows)} 2026 RP candidates, {len(with_usage)} with usage reads; "
        f"median mi_share={_q(mis, .5)} b2b={_q(b2b, .5)}")

    doc = {
        "generated_at": date.today().isoformat(),
        "lane": "T1-13 PAL game-log walk (sportId=1)",
        "incumbent_eval": doc0,
        "legacy_byte_identity": ident,
        "legacy_rescore_mismatches": mismatch,
        "lane_c_census": census,
        "lane_a": {
            "n_recovered": len(recovered), "n_mid_year": n_mid, "n_swing_bridge": n_bridge,
            "n_labelable_war_delta": len(labelable),
            "n_labelable_held": sum(1 for r in recs_rec
                                    if r["fit"] is not None and r["held"] is not None),
            "recovered_events": [{k: e[k] for k in
                                  ("mlbam", "name", "direction", "year", "held", "recovered")}
                                 for e in recovered],
            "per_direction": arm_a,
        },
        "lane_b": arm_b,
        "current_pool": pool,
    }
    (out_dir / "t113_full.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write data/pal_eval.json")
    ap.add_argument("--out", help="also write the eval JSON to this path")
    ap.add_argument("--results", help="write a results.json copy to this path")
    ap.add_argument("--t113", help="run the T1-13 lane arms; value = output dir")
    args = ap.parse_args()
    if args.t113:
        doc = run_t113(Path(args.t113))
        print("T113 done ->", Path(args.t113) / "t113_full.json")
        return
    doc = run()
    text = json.dumps(doc, indent=1)
    if args.write:
        EVAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        EVAL_PATH.write_text(text, encoding="utf-8")
        print(f"wrote {EVAL_PATH}")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    if args.results:
        Path(args.results).parent.mkdir(parents=True, exist_ok=True)
        Path(args.results).write_text(text, encoding="utf-8")
        print(f"wrote {args.results}")
    if not (args.write or args.out or args.results):
        print(text)
    print("VERDICT:", doc["verdict"]["status"].upper())


if __name__ == "__main__":
    main()
