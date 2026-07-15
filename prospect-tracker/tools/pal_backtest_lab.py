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

import bullpen_export as be          # noqa: E402
import pal_conversion as pc          # noqa: E402
import pal_export as pe              # noqa: E402
import rem_plus                      # noqa: E402
import sem_plus                      # noqa: E402
from rem_plus_backtest import _spearman, _ci   # noqa: E402  (shared stats helpers)

EVAL_PATH = ROOT / "data" / "pal_eval.json"

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
def run(log=print) -> dict:
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write data/pal_eval.json")
    ap.add_argument("--out", help="also write the eval JSON to this path")
    ap.add_argument("--results", help="write a results.json copy to this path")
    args = ap.parse_args()
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
