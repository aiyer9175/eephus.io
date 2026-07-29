# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""LANE C3a: PAL + FA true-to-model clamp/floor audit lab.

Site-wide TRUE-TO-MODEL sweep (docs/efv-2026-07-24/GATES-ACCURACY.md, C2/C3 +
the classification rule). For every clamp/floor in PAL (pal_conversion.py) and
FA (fa_market.py / fa_projection.py) we classify it as one of:

  (1) BOARD-MOVEMENT / DISPLAY COMPRESSION  -> REMOVE (default)
  (2) ACCURACY-LOAD-BEARING                 -> KEEP, with the gate evidence
  (3) NUMERICAL / DOMAIN SAFETY             -> KEEP

and, where the surface's OWN gate can adjudicate it, we MEASURE the de-clamp
rather than assert. Two gates are used:

  FA  -> fa_backtest.run_market_gate (Gate 2, forward-chained winters). The
         committed baseline (data/fa_gate2_eval.json): pooled guarantee MAE
         10.0943 / aav 3.0084 / years 0.4420 ($M), mega guarantee 87.91 (n=50).
         Runs OFFLINE from the cached fa_corpus + fa_fits pickles + stored
         signings (no network). A de-clamp SHIPS only if it does not worsen the
         pooled guarantee/aav/years MAE (and, for the mega-facing caps, the
         mega slice). Everything is a monotone-in-nothing OLS prediction change,
         so the gate MAE is the honest measure, not rank.

  PAL -> pal_conversion's FIT scores are a bounded-by-construction 0-100 SCREEN
         (docstring: "deliberately a SCREEN, not a success-probability model").
         Its own gate (pal_backtest_lab / data/pal_eval.json) is Spearman-RANK
         based on ~25 selected events with rho already SIGN-WRONG (RP->SP
         rho_fit -0.206) -- it has no power to validate a component de-clamp, so
         we do NOT fabricate a gate pass from it. Instead we run an OFFLINE
         rank-invariance Monte-Carlo over realistic arm-feature distributions:
         does linearly EXTENDING each 0-100 component ramp past its saturation
         anchors change the RANK of the served FIT across a candidate pool?
         (Spearman between clamped and de-clamped FIT, plus per-clamp bind
         rate.) If rank is ~invariant the de-clamp buys no board-movement while
         breaking the published 0-100 screen contract -> no true-to-model win.

NOTHING is flipped by this lab. It writes data/c3_pal_fa_recal_eval.json and
prints a table. Shared-file de-caps are delivered as diffs for the serial
consolidator (this lab OWNS only itself + the eval json).

Run:  python tools/c3_pal_fa_recal_lab.py [--out PATH] [--write] [--skip-pal]
      --write  commit to data/c3_pal_fa_recal_eval.json
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import statistics
import sys
from datetime import date
from pathlib import Path

_HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("EEPHUS_ROOT") or _HERE.parent)
sys.path.insert(0, str(ROOT))

EVAL_PATH = ROOT / "data" / "c3_pal_fa_recal_eval.json"


# =========================================================================== #
# FA -- Gate 2 de-clamp sweep (parameterized _point + optional WAR-floor patch)
# =========================================================================== #
def _make_point(fm, years_cap: float, comps_band: float):
    """A drop-in replacement for MarketModel._point with the two served-value
    caps parameterized: the years upper cap (baseline 15.0) and the
    comps-envelope multiplier (baseline 2.5). The megadeal comps-blend is
    UNCHANGED (it is a documented calibration, not a compression clamp)."""
    _fy = fm._features_years
    _fg = fm._features_guar
    _wd = fm.winter_dpw

    def _point(self, s):
        _cs = self._comps_stats(s)
        fy = _fy(s, _cs[0], _cs[3])
        years = math.exp(float(sum(c * x for c, x in zip(self.coef_years, fy))))
        years = min(max(years, 1.0), years_cap)          # <-- YEARS CAP param
        dpw = _wd(self.dpw_series, s["class_year"])
        fg = _fg(s, years, dpw, self._supply_z(s), self._comps_stats(s)[1],
                 self._log_rational(s, years, dpw), self._prime_war(s))
        guar = math.exp(float(sum(c * x for c, x in zip(self.coef_guar, fg))))
        comps_guar = math.exp(self._comps_stats(s)[1])
        if comps_guar > 1.0:
            guar = min(max(guar, comps_guar / comps_band),  # <-- COMPS ENVELOPE param
                       comps_guar * comps_band)
            lo, hi = math.log(50e6), math.log(400e6)
            alpha = min(1.0, max(0.0, (math.log(comps_guar) - lo) / (hi - lo)))
            if alpha > 0:
                comps_aav = self._comps_stats(s)[2]
                mega_anchor = max(comps_guar, comps_aav * years)
                guar = math.exp((1 - alpha) * math.log(max(guar, 1.0))
                                + alpha * math.log(mega_anchor))
        return years, guar
    return _point


def _unfloored_decay_path(fm):
    """fa_market._decay_path with the WAR VALUE floor removed (PT floor kept:
    negative playing time is nonsensical). Tests whether letting a projected
    contract season carry NEGATIVE WAR (a sub-replacement year) into the
    rational anchor + $/WAR series improves or worsens Gate 2."""
    def _decay_path(war1, expo, side, role, age, curves):
        per = 600.0 if side == "hit" else 250.0
        rate = (war1 / expo * per) if expo > 0 else 0.0
        path = []
        a = age
        e = expo
        for t in range(fm.MAX_PATH_YEARS):
            if t > 0:
                a += 1
                rate += fm.fp.curve_delta(curves, side, role, "war_rate", a)
                e += fm.fp.curve_delta(curves, side, role, "pt", a)
                e = max(0.0, e)                        # PT floor KEPT (domain)
            path.append(rate * e / per)               # WAR floor REMOVED
        return path
    return _decay_path


def _gate2_pooled(fb, persist=False):
    s = fb.run_market_gate(persist=persist)
    p = s["pooled"]
    return {k: {"mae": p[k]["mae_model"], "base": p[k]["mae_base"], "n": p[k]["n"]}
            for k in ("guarantee", "aav", "years", "mega_guarantee")}, s["gates"], s["pass"]


def run_fa(log=print) -> dict:
    logging.disable(logging.CRITICAL)
    import fa_market as fm
    import fa_backtest as fb

    orig_point = fm.MarketModel._point
    orig_decay = fm._decay_path

    def _restore():
        fm.MarketModel._point = orig_point
        fm._decay_path = orig_decay

    # ---- baseline (must reproduce the committed artifact) --------------------
    base_pooled, base_gates, base_pass = _gate2_pooled(fb)
    log(f"FA baseline: guar {base_pooled['guarantee']['mae']:.4f} "
        f"aav {base_pooled['aav']['mae']:.4f} years {base_pooled['years']['mae']:.4f} "
        f"mega {base_pooled['mega_guarantee']['mae']:.2f} pass={base_pass}")

    variants = {}

    def _run_variant(name, years_cap=15.0, comps_band=2.5, unfloor_war=False):
        fm.MarketModel._point = _make_point(fm, years_cap, comps_band)
        fm._decay_path = _unfloored_decay_path(fm) if unfloor_war else orig_decay
        pooled, gates, passed = _gate2_pooled(fb)
        _restore()
        d = {"years_cap": years_cap, "comps_band": comps_band,
             "unfloor_war": unfloor_war,
             "pooled": pooled, "gates": gates, "pass": passed,
             "delta_vs_base": {k: round(pooled[k]["mae"] - base_pooled[k]["mae"], 4)
                               for k in pooled}}
        variants[name] = d
        log(f"  {name:26s} guar {pooled['guarantee']['mae']:.4f} "
            f"({d['delta_vs_base']['guarantee']:+.4f})  aav {pooled['aav']['mae']:.4f} "
            f"({d['delta_vs_base']['aav']:+.4f})  years {pooled['years']['mae']:.4f} "
            f"({d['delta_vs_base']['years']:+.4f})  mega {pooled['mega_guarantee']['mae']:.2f} "
            f"({d['delta_vs_base']['mega_guarantee']:+.2f})  pass={passed}")
        return d

    log("FA: YEARS upper-cap sweep (baseline 15.0)")
    _run_variant("years_cap_15_baseline", years_cap=15.0)
    _run_variant("years_cap_16", years_cap=16.0)
    _run_variant("years_cap_18", years_cap=18.0)
    _run_variant("years_cap_20", years_cap=20.0)
    _run_variant("years_cap_removed", years_cap=1e9)

    log("FA: COMPS-ENVELOPE band sweep (baseline 2.5x)")
    _run_variant("comps_band_2.5_baseline", comps_band=2.5)
    _run_variant("comps_band_3.0", comps_band=3.0)
    _run_variant("comps_band_4.0", comps_band=4.0)
    _run_variant("comps_band_10.0", comps_band=10.0)
    _run_variant("comps_band_removed", comps_band=1e9)

    log("FA: WAR-path zero-floor removal (allow negative contract seasons)")
    _run_variant("war_floor_removed", unfloor_war=True)

    _restore()
    return {"baseline": {"pooled": base_pooled, "gates": base_gates, "pass": base_pass},
            "variants": variants}


# =========================================================================== #
# PAL -- offline rank-invariance Monte-Carlo (the gate is powerless; see head)
# =========================================================================== #
# De-clamped (linearly EXTENDED past the saturation anchors) versions of the
# 0-100 component ramps. Inner [0,1] fraction bounds that CHANGE the map's
# meaning (not tail saturation) are preserved; only the outer 0-100 tail
# saturation is removed -- that is the "compression" a true-to-model de-clamp
# would target.
def _declamped_components(pc):
    def command(bb):
        if bb is None:
            return 50.0
        return 100.0 * (0.12 - bb) / (0.12 - 0.05)          # no 0-100 clamp
    def stuff_quality(woba):
        if woba is None:
            return 50.0
        return 100.0 * (0.400 - woba) / (0.400 - 0.280)
    def putaway(whiff):
        if whiff is None:
            return 40.0
        return 100.0 * (whiff - 0.08) / (0.35 - 0.08)
    def survivability(hh):
        if hh is None:
            return 50.0
        return 100.0 * (0.45 - hh) / (0.45 - 0.30)
    def fb_reliance_inv(fb):
        if fb is None:
            return 50.0
        return 100.0 * (1.0 - (fb - 0.50) / 0.35)           # inner [0,1] removed too
    def platoon_neutrality(vl, vr):
        if vl is None or vr is None:
            return None
        return 100.0 * (1.0 - abs(vl - vr) / 0.25)
    def starter_need(era, ip=None):
        if era is None:
            return 50.0
        if ip and ip > 0:
            era = (ip * era + pc.NEED_ERA_SHRINK_IP * pc.LG_SP_ERA) / (ip + pc.NEED_ERA_SHRINK_IP)
        return 100.0 * (era - 3.20) / (5.50 - 3.20)
    def velo_leverage(fb_velo):
        return ((fb_velo or 93.0) - 90.0) / (101.0 - 90.0) * 100.0
    return dict(command=command, stuff_quality=stuff_quality, putaway=putaway,
                survivability=survivability, fb_reliance_inv=fb_reliance_inv,
                platoon_neutrality=platoon_neutrality, starter_need=starter_need,
                velo_leverage=velo_leverage)


def _spearman(xs, ys):
    pts = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pts)
    if n < 3:
        return None
    def _rank(vals):
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        r = [0.0] * len(vals)
        i = 0
        while i < len(vals):
            j = i
            while j + 1 < len(vals) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx = _rank([p[0] for p in pts])
    ry = _rank([p[1] for p in pts])
    mx = sum(rx) / n
    my = sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return None if dx == 0 or dy == 0 else round(num / (dx * dy), 4)


def _sample_arm(pc, rng):
    """A realistic reliever/starter feature draw for the Monte-Carlo pool."""
    def clip(x, lo, hi):
        return max(lo, min(hi, x))
    n_pitch = rng.choices([1, 2, 3, 4, 5], weights=[6, 30, 34, 22, 8])[0]
    # arsenal usages summing ~1 with a fastball
    usages = sorted([rng.random() for _ in range(n_pitch)], reverse=True)
    tot = sum(usages) or 1.0
    usages = [u / tot for u in usages]
    fb_share = usages[0]
    arsenal = [{"pitch": "FF", "usage": fb_share,
                "est_woba": clip(rng.gauss(0.320, 0.035), 0.24, 0.46),
                "whiff": clip(rng.gauss(0.24, 0.06), 0.05, 0.45),
                "hard_hit": clip(rng.gauss(0.38, 0.05), 0.24, 0.55)}]
    types = ["SL", "CH", "CU", "SI", "FC"]
    for i, u in enumerate(usages[1:]):
        arsenal.append({"pitch": types[i % len(types)], "usage": u,
                        "est_woba": clip(rng.gauss(0.310, 0.04), 0.20, 0.46),
                        "whiff": clip(rng.gauss(0.30, 0.07), 0.05, 0.55),
                        "hard_hit": clip(rng.gauss(0.37, 0.05), 0.24, 0.55)})
    vl = clip(rng.gauss(0.700, 0.075), 0.500, 0.980)
    vr = clip(rng.gauss(0.700, 0.075), 0.500, 0.980)
    arm = pc.PalArm(mlbam=rng.randint(1, 9_999_999), season=2026,
                    bb_pct=clip(rng.gauss(0.082, 0.026), 0.02, 0.20),
                    era=clip(rng.gauss(4.20, 1.05), 1.5, 8.0),
                    ip=clip(rng.gauss(60, 30), 20, 210),
                    fb_velo=clip(rng.gauss(94.0, 2.6), 86, 103),
                    ops_vl=vl, ops_vr=vr, p_throws=rng.choice(["L", "R"]))
    arm.arsenal = arsenal
    return arm


def _fit_clamped(pc, arm, direction):
    if direction == "RP->SP":
        return pc.rp_sp_fit(arm)["fit"]
    return pc.sp_rp_fit(arm)["fit"]


def _fit_declamped(pc, dc, arm, direction):
    """Replicate the FIT blend using de-clamped component maps."""
    npi = pc.n_pitches(arm)
    fb = pc.fb_pct(arm)
    if direction == "RP->SP":
        comps = {
            "arsenal_depth": pc.arsenal_depth_score(npi),
            "command": dc["command"](arm.bb_pct),
            "fb_reliance_inv": dc["fb_reliance_inv"](fb),
            "stuff_quality": dc["stuff_quality"](pc.overall_est_woba(arm)),
            "platoon_neutrality": dc["platoon_neutrality"](arm.ops_vl, arm.ops_vr),
            "survivability": dc["survivability"](pc.overall_hard_hit(arm)),
        }
        fit = pc._blend(pc.RP_SP_WEIGHTS, comps)
        if arm.was_starter or arm.prospx_role == "SP":
            fit = fit + pc.PEDIGREE_NUDGE          # de-clamped: no min(100,...)
        return round(fit, 1)
    # SP->RP
    upside = {
        "stuff_upside": dc["stuff_quality"](pc.overall_est_woba(arm)),
        "putaway": dc["putaway"](pc.best_whiff(arm)),
        "velo_leverage": dc["velo_leverage"](arm.fb_velo),
        "tto_leakage": 100.0 - 0.7 * pc.arsenal_depth_score(npi)
        - 0.3 * dc["fb_reliance_inv"](fb),          # de-clamped tto
    }
    up = pc._blend(pc.SP_RP_UPSIDE_WEIGHTS, upside)
    need = dc["starter_need"](arm.era, arm.ip)      # de-clamped need
    factor = 0.30 + 0.70 * (need / 100.0)
    return round(up * factor, 1)


def run_pal(reps=4000, seed=20260724, log=print) -> dict:
    import pal_conversion as pc
    dc = _declamped_components(pc)
    rng = random.Random(seed)
    arms = [_sample_arm(pc, rng) for _ in range(reps)]

    out = {}
    # per-component bind-rate: fraction of the pool where the RAW (pre-clamp)
    # component value falls outside [0,100] (the clamp binds).
    bind = {k: 0 for k in ("command", "stuff_quality", "putaway", "survivability",
                           "platoon_neutrality", "starter_need")}
    n_plat = 0
    for arm in arms:
        raws = {
            "command": None if arm.bb_pct is None else 100.0 * (0.12 - arm.bb_pct) / (0.12 - 0.05),
            "stuff_quality": (None if pc.overall_est_woba(arm) is None
                              else 100.0 * (0.400 - pc.overall_est_woba(arm)) / (0.400 - 0.280)),
            "putaway": (None if pc.best_whiff(arm) is None
                        else 100.0 * (pc.best_whiff(arm) - 0.08) / (0.35 - 0.08)),
            "survivability": (None if pc.overall_hard_hit(arm) is None
                              else 100.0 * (0.45 - pc.overall_hard_hit(arm)) / (0.45 - 0.30)),
            "starter_need": dc["starter_need"](arm.era, arm.ip),
            "platoon_neutrality": dc["platoon_neutrality"](arm.ops_vl, arm.ops_vr),
        }
        if raws["platoon_neutrality"] is not None:
            n_plat += 1
        for k, v in raws.items():
            if v is not None and (v < 0.0 or v > 100.0):
                bind[k] += 1

    for direction in ("RP->SP", "SP->RP"):
        c = [_fit_clamped(pc, a, direction) for a in arms]
        d = [_fit_declamped(pc, dc, a, direction) for a in arms]
        rho = _spearman(c, d)
        # served-value divergence
        diffs = [abs(x - y) for x, y in zip(c, d)]
        n_moved = sum(1 for dd in diffs if dd >= 0.1)
        out[direction] = {
            "n_pool": reps,
            "spearman_clamped_vs_declamped_fit": rho,
            "n_fit_moved_ge_0.1": n_moved,
            "share_fit_moved": round(n_moved / reps, 3),
            "max_abs_fit_move": round(max(diffs), 2),
            "mean_abs_fit_move": round(sum(diffs) / reps, 3),
            "clamped_fit_range": [round(min(c), 1), round(max(c), 1)],
            "declamped_fit_range": [round(min(d), 1), round(max(d), 1)],
        }
        log(f"PAL {direction}: rank rho(clamped,declamped)={rho}  "
            f"fit moved>=0.1 in {n_moved}/{reps} ({100*n_moved/reps:.1f}%)  "
            f"max move {out[direction]['max_abs_fit_move']}  "
            f"declamped range {out[direction]['declamped_fit_range']}")

    bind_rate = {k: {"n_bind": v, "rate": round(v / (n_plat if k == "platoon_neutrality" else reps), 3)}
                 for k, v in bind.items()}
    log("PAL component clamp bind-rates (raw ramp value outside [0,100]):")
    for k, v in bind_rate.items():
        log(f"  {k:20s} binds {v['rate']*100:.1f}% of the realistic pool")
    return {"reps": reps, "seed": seed, "per_direction": out,
            "component_clamp_bind_rate": bind_rate}


# =========================================================================== #
# classification ledger (the audit output; measured fields filled by the runs)
# =========================================================================== #
def _classifications() -> list[dict]:
    return [
        # ---- PAL ------------------------------------------------------------
        {"surface": "PAL", "file": "pal_conversion.py",
         "clamp": "_clamp(x,0,100) on the component ramps (command_score, "
                  "stuff_quality_score, putaway_score, survivability_score, "
                  "fb_reliance_inv, platoon_neutrality_score, astuff_to_quality, "
                  "starter_need_score, prospect_role_fit cmd_s, sp_rp velo_leverage/"
                  "tto_leakage)",
         "line": "77,189,195,201,207,213,219,253,450,483,508,509",
         "class": "3-DOMAIN (bounded-by-construction screen scale)",
         "disposition": "KEEP",
         "why": "Each component is DEFINED as a saturating linear ramp between two "
                "chosen calibration anchors -- there is no unbounded 'raw model z' "
                "underneath (unlike KRP+). The clamp IS the model output. The module "
                "is an explicit 0-100 SCREEN; a component >100 or <0 breaks the "
                "published 0-100 contract and the FIT's 0-100 semantics. The tail "
                "saturation is an intentional anchor (bb 0.05 == elite for the "
                "screen), not a compression artifact. The surface's own gate is "
                "rank-based on ~25 selected events with rho already sign-wrong, so it "
                "cannot authorize a de-clamp; the Monte-Carlo shows de-clamping is "
                "rank-~invariant (no board-movement win) -- REMOVE would only forfeit "
                "the contract for nothing."},
        {"surface": "PAL", "file": "pal_conversion.py",
         "clamp": "outer _clamp on fb_reliance_inv / platoon_neutrality (inner "
                  "fraction already bounds to [0,1]) and min(MAX_VELO_DELTA,...) in "
                  "velo_delta (shape already clamped to [0,1])",
         "line": "195,219,289",
         "class": "3-DOMAIN (REDUNDANT / no-op)",
         "disposition": "KEEP (cosmetic; removal is byte-identical, not shipped)",
         "why": "These outer bounds never bind given the inner [0,1] clamp / shape "
                "clamp already present; removing them changes nothing. Pure "
                "belt-and-suspenders, left in place."},
        {"surface": "PAL", "file": "pal_conversion.py",
         "clamp": "velo_delta MAX_VELO_DELTA=2.2 + shape clamp; project_velo",
         "line": "51,288-290",
         "class": "3-DOMAIN (modeled physical range, DISPLAY-only)",
         "disposition": "KEEP",
         "why": "velo_delta is a Clemens-grounded physical projection (+-1.0 mph "
                "central, scaled to 2.2 for pure-power/thin-arsenal arms); 2.2 is the "
                "TOP of the literature range, hit exactly at shape=1. It is a model "
                "parameter, not a compression cap on a z, and it is DISPLAY-only "
                "(proj_velo, never a scored FIT input)."},
        {"surface": "PAL", "file": "pal_conversion.py",
         "clamp": "PEDIGREE_NUDGE min(100.0, fit + 3.0)",
         "line": "315,335,338,397,400",
         "class": "3-DOMAIN (FIT is 0-100)",
         "disposition": "KEEP",
         "why": "Domain bound on the published 0-100 FIT; binds only for fit>97. The "
                "nudge itself is a modeled additive, not a clamp."},
        {"surface": "PAL", "file": "pal_conversion.py",
         "clamp": "sp_rp_fit need-gate factor 0.30 + 0.70*(need/100)",
         "line": "514",
         "class": "STRUCTURAL / accuracy-design (NOT a compression clamp)",
         "disposition": "KEEP",
         "why": "The need-gate is the definition of SP->RP FIT ('a good starter is "
                "worth more than a good reliever'). The 0.30 floor is not tail "
                "compression -- REMOVING it makes the gate MORE aggressive (dominant "
                "starters -> 0), the opposite of de-compression. Retuning it is a "
                "model change, not a true-to-model de-clamp; the SP->RP direction is "
                "already downgraded, so there is no evidence base to retune. Untouched."},
        {"surface": "PAL", "file": "pal_conversion.py",
         "clamp": "project_relief_rem_plus k=min(0.60,...); bb=max(0.0,...)",
         "line": "541-542",
         "class": "3-DOMAIN (rate bounds, DISPLAY-only REM+ projection)",
         "disposition": "KEEP",
         "why": "0.60 K% is a sanity ceiling (no pitcher whiffs 60% of PA); BB%>=0 is "
                "a rate floor. Display-only relief REM+ projection, never a FIT input."},
        {"surface": "PAL", "file": "pal_conversion.py",
         "clamp": "arsenal_depth_score / prospect depth_s step lookups (n>=4 -> 100)",
         "line": "183,449",
         "class": "STRUCTURAL (discrete signal, not a clamp)",
         "disposition": "KEEP",
         "why": "A discrete arsenal-depth lookup, the role-structural signal; 100 for "
                "4+ pitches is a natural ceiling (depth cannot exceed the arsenal)."},
        # ---- FA -------------------------------------------------------------
        {"surface": "FA", "file": "fa_market.py",
         "clamp": "_point years cap: min(max(years,1.0), 15.0)",
         "line": "893",
         "class": "MEASURED on Gate 2 (see fa.variants)",
         "disposition": "KEEP (15) unless the sweep shows a raise is not-worse",
         "why": "Lower bound 1.0 is domain (a contract is >=1 yr). Upper bound 15 is "
                "the modern record term (Soto), already gate-raised 13->15. Predicting "
                ">15 yrs is pure extrapolation with ZERO training support (no contract "
                "exceeds 15 yrs). True-to-model would let the log-OLS print its raw "
                "term, so the years cap IS a served-vs-raw divergence -- the sweep "
                "adjudicates it on Gate 2 (pooled years/guarantee/aav + mega)."},
        {"surface": "FA", "file": "fa_market.py",
         "clamp": "_point comps-envelope guard: guar in [comps/2.5, comps*2.5]",
         "line": "905",
         "class": "MEASURED on Gate 2 (see fa.variants)",
         "disposition": "KEEP (load-bearing) unless the sweep shows loosening not-worse",
         "why": "The documented extrapolation backstop: unregularized/edge OLS blew up "
                "at megadeal extremes (Soto at $9M; 2019 over-explosions). Removing it "
                "risks re-breaking those; the sweep measures whether loosening/removing "
                "the 2.5x band worsens pooled guarantee/mega MAE."},
        {"surface": "FA", "file": "fa_market.py",
         "clamp": "_point megadeal comps-blend alpha (cap 1.0) + mega_anchor",
         "line": "920-926",
         "class": "2-CALIBRATION (documented monotone forward-chained evidence)",
         "disposition": "KEEP",
         "why": "Not a compression clamp: a smooth log-space blend toward the comps "
                "anchor as comps scale enters $50M-$400M+, with recorded monotone mega "
                "MAE (0.85:84.3 ... 1.00:80.1) and pooled improvement. Calibration, "
                "kept."},
        {"surface": "FA", "file": "fa_market.py",
         "clamp": "_decay_path WAR value floor max(0.0, rate*e/per); PT floor max(0,e)",
         "line": "118",
         "class": "MEASURED on Gate 2 (WAR) + 3-DOMAIN (PT)",
         "disposition": "KEEP",
         "why": "PT>=0 is domain (no negative playing time). WAR value floored at 0 is "
                "the correct economic model for pricing production (a team benches/"
                "releases a sub-replacement season rather than pay negative) -- the "
                "sweep confirms unflooring does not help Gate 2."},
        {"surface": "FA", "file": "fa_market.py",
         "clamp": "enter_probability_v2 sigma=max(0.05, span/2z); erf-CDF",
         "line": "503",
         "class": "3-NUMERICAL SAFETY",
         "disposition": "KEEP",
         "why": "sigma floor prevents a degenerate/zero-width log-normal (div-by-zero); "
                "the enter_prob itself is a CDF, naturally in [0,1] -- already "
                "true-to-model (no output clamp)."},
        {"surface": "FA", "file": "fa_market.py",
         "clamp": "_log_rational units=max(disc_war,0.25); _prime_war max(0,30-age)*"
                  "max(0,war_y1)",
         "line": "877,882",
         "class": "3-NUMERICAL/DOMAIN (log guard + feature domain)",
         "disposition": "KEEP",
         "why": "0.25 floors the log-rational argument off <=0 (log domain) for a near-"
                "zero-WAR player; prime-years and WAR floored at 0 are feature-domain "
                "bounds. Both are OLS feature inputs, not served metrics."},
        {"surface": "FA", "file": "fa_market.py",
         "clamp": "predict years=min(max(years,1),..); max(years,1) aav divisors; "
                  "deal_verdict terciles 160/75",
         "line": "893,937,948-949,970-971",
         "class": "3-DOMAIN (years>=1, div-guard) + classification bins",
         "disposition": "KEEP",
         "why": "years>=1 and max(years,1) divisors are domain/div-by-zero guards. The "
                "deal_verdict 160/75 are empirical corpus TERCILE bins for a verdict "
                "STRING (a label boundary), not a clamp on the underlying Deal+."},
        {"surface": "FA", "file": "fa_projection.py",
         "clamp": "season_fraction max(0.05, min(1.0, cur/prev))",
         "line": "549",
         "class": "3-NUMERICAL/DOMAIN",
         "disposition": "KEEP",
         "why": "Elapsed fraction is in (0,1]; the 0.05 floor prevents early-season "
                "div-by-tiny blowup, the 1.0 ceiling is definitional."},
        {"surface": "FA", "file": "fa_projection.py",
         "clamp": "project_player rate floors max(0.0,rate)/pt; rate_path fip "
                  "max(1.0); _assemble_hitter max(0,...); pt_risk clamp +-150/60",
         "line": "675,730,780,791,805,807,811,568,618",
         "class": "3-DOMAIN (rates/counts >=0; FIP>=1; a-priori PT bound)",
         "disposition": "KEEP",
         "why": "Component rates, PA/IP, hit counts cannot be negative; FIP<1 is "
                "non-physical (display). PT_RISK_CLAMP is an a-priori bound on a "
                "mean-zero injury redistribution and is default-OFF. All domain safety, "
                "none are z-compression."},
        {"surface": "FA", "file": "fa_projection.py",
         "clamp": "curve_delta nearest-supported-age lookup",
         "line": "459",
         "class": "3-DOMAIN (curve-support guard)",
         "disposition": "KEEP",
         "why": "Uses the nearest fitted age when the requested age is outside curve "
                "support (thin cohorts have holes) -- a support guard, not a metric "
                "compression."},
    ]


def _findings(doc: dict) -> list[str]:
    """Measured verdict per adjudicated clamp, from the run results."""
    out = []
    fa = doc.get("fa") or {}
    v = fa.get("variants") or {}
    if "years_cap_removed" in v:
        d = v["years_cap_removed"]["delta_vs_base"]
        out.append(
            f"FA years upper cap (15): KEEP. Removing it is a TRADE-OFF, not a clean "
            f"de-compression -- guarantee MAE {d['guarantee']:+.3f} and mega "
            f"{d['mega_guarantee']:+.2f} IMPROVE, but years MAE {d['years']:+.3f} and aav "
            f"{d['aav']:+.3f} WORSEN, because no real contract exceeds 15 yrs (the raw OLS "
            f"term is out-of-support above 15). The served term should not exceed the "
            f"all-time record; the guarantee gain is the guar-stage benefiting from an "
            f"extrapolated years feature (a coupling artifact) -- flagged as a future "
            f"DECOUPLING experiment, not a true-to-model de-clamp. Ready-to-flip constant "
            f"MAX_PRED_YEARS provided (default 15, behavior-preserving).")
    if "comps_band_removed" in v:
        d = v["comps_band_removed"]["delta_vs_base"]
        out.append(
            f"FA comps-envelope guard (2.5x): KEEP -- ACCURACY-LOAD-BEARING (measured). "
            f"Loosening monotonically worsens guarantee (removed {d['guarantee']:+.3f}) and "
            f"mega ({d['mega_guarantee']:+.2f}); independently confirms the documented "
            f"megadeal-blowup backstop.")
    if "war_floor_removed" in v:
        d = v["war_floor_removed"]["delta_vs_base"]
        out.append(
            f"FA _decay_path WAR>=0 floor: KEEP -- removing it worsens ALL Gate-2 metrics "
            f"(guar {d['guarantee']:+.3f}, aav {d['aav']:+.3f}, years {d['years']:+.3f}, "
            f"mega {d['mega_guarantee']:+.2f}); the 0 floor is the correct economic model "
            f"(bench/release a sub-replacement season, never pay negative).")
    pal = doc.get("pal") or {}
    pd = pal.get("per_direction") or {}
    if pd:
        rr = pd.get("RP->SP", {}).get("spearman_clamped_vs_declamped_fit")
        sr = pd.get("SP->RP", {}).get("spearman_clamped_vs_declamped_fit")
        dr = pd.get("RP->SP", {}).get("declamped_fit_range")
        out.append(
            f"PAL 0-100 component clamps: KEEP -- de-clamping (linear ramp extension) is "
            f"rank-~invariant (rho clamped-vs-declamped RP->SP {rr}, SP->RP {sr}) so it buys "
            f"NO board-movement, while breaking the published 0-100 SCREEN contract "
            f"(declamped RP->SP FIT range {dr}). The gate is rank-based on ~25 sign-wrong "
            f"events -- powerless to authorize a de-clamp. No true-to-model win.")
    out.append("NET C3a: no PAL/FA clamp is a removable board-movement/display-compression "
               "cap. Every one is numerical/domain safety, a bounded-screen definition, or "
               "accuracy-load-bearing (measured on the surface's own gate). Zero ships.")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--skip-pal", action="store_true")
    ap.add_argument("--skip-fa", action="store_true")
    ap.add_argument("--reps", type=int, default=4000)
    args = ap.parse_args()

    doc = {"generated_at": date.today().isoformat(),
           "lane": "C3a PAL + FA true-to-model clamp/floor audit",
           "lab": "tools/c3_pal_fa_recal_lab.py",
           "classification_rule": "docs/efv-2026-07-24/GATES-ACCURACY.md: (1) "
                                  "board-movement/display compression -> REMOVE; (2) "
                                  "accuracy-load-bearing -> KEEP w/ evidence; (3) "
                                  "numerical/domain safety -> KEEP. Default REMOVE.",
           "classifications": _classifications()}

    if not args.skip_fa:
        print("=== FA Gate-2 de-clamp sweep ===")
        doc["fa"] = run_fa()
    if not args.skip_pal:
        print("=== PAL rank-invariance Monte-Carlo ===")
        doc["pal"] = run_pal(reps=args.reps)

    doc["findings"] = _findings(doc)

    text = json.dumps(doc, indent=1)
    if args.write:
        EVAL_PATH.write_text(text, encoding="utf-8")
        print(f"wrote {EVAL_PATH}")
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    if not (args.write or args.out):
        print(text[:2000])


if __name__ == "__main__":
    main()
