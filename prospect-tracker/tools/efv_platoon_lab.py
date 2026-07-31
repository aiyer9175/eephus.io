# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
# LANE-SENTINEL-W-PLATOON-20260724
"""W-PLATOON (docs/efv-2026-07-24/GATES.md Phase 2a) - platoon split features, ONE
attempt per arm, marginal = FAIL.

FROZEN HEADER - written and frozen BEFORE any correlation was computed.
=======================================================================

Data: .cache/milb_platoon/platoon_table.json (statsapi statSplits vl/vr, sportIds
11/12/13/14/16, 2011-2026; rows[mlbam][season][level][side], side in {hit,pit};
hit splits are vs PITCHER hand (exposure key pa), pit splits are vs BATTER hand
(exposure key bf)). Coverage 99.3 pct of matrix player-seasons (coverage_summary.json)
so STOP-D (60 pct bar) is CLEARED before any arm runs.

woba_proxy (FROZEN): woba_proxy = 0.6*obp + 0.4*slg, computed per split block from
the block's obp/slg. None if either component is None.

Handedness source (investigated, documented): the DB players table has NO bats/throws
column; draft_players.bats (98 rows with mlbam) and overseas_players.bats (0 rows with
mlbam) have ZERO overlap with the debuted eval pool (measured 0/845 hitters). Therefore
handedness comes from StatsAPI /v1/people (batSide.code, pitchHand.code), a data-phase
bulk pull cached at .cache/milb_platoon/hand_map.json for the union of all platoon-table
player ids + all matrix mlbam ids. This is the same source hitter_export.load_bat_side
already uses for MLB lineups.

Join (FROZEN): matrix row (kind=debuted, eval pool identical to efv_lab_runner.load_side)
joins platoon_table at (mlbam_id, milb_season, milb_level) - the FINAL pre-decision
season at the PRIMARY level, exactly the season/level whose k_rel/obp_rel the shipped
model reads. No other season, no career weighting (final-season features only, per the
frozen list). Missing join / missing hand / missing split blocks -> feature = missing.

Features (FROZEN; side conventions mirror efv_dataset._season_rates: level-relative
where normed, reliability-shrunk w = exposure/(exposure+K)):
  Split exposure for a two-sided gap (FROZEN): h = harmonic mean = 2*a*b/(a+b) of the
  two sides' exposure (pa for hit, bf for pit); the variance of a difference of two
  split rates scales as 1/a + 1/b = 2/h, so h is the natural single exposure number.
  Shrink: w = h/(h + K), K = 100 (K_SPLIT = 100 per the GATES registration, both sides).

  hit (splits vs pitcher hand; weak side for a hitter = SAME-hand matchup):
    platoon_gap_rel = w * (gap - norm[season,level,hit]) where
        gap = woba_proxy(same-hand block) - woba_proxy(opposite-hand block)
        (bats L -> same = vl; bats R -> same = vr). More negative = bigger platoon
        vulnerability; positive = reverse split.
    same_hand_share = pa_same / (pa_vl + pa_vr)   (exposure context; NOT normed,
        NOT shrunk - it is itself an exposure measure)
    bats_s = 1.0 if batSide == 'S' else 0.0
    Switch hitters (S) take essentially no same-hand PA: platoon_gap_rel = 0.0 and
    same_hand_share = 0.0 are DEFINED (inert in a linear model), not missing.
  pit (splits vs batter hand; vulnerability side for a pitcher = OPPOSITE hand):
    platoon_gap_rel = w * (gap - norm[season,level,pit]) where
        gap = woba_proxy_allowed(opp-hand block) - woba_proxy_allowed(same-hand block)
        (throws L -> opp = vr; throws R -> opp = vl). Positive = more vulnerable to
        opposite-hand bats (the normal platoon direction).
    opp_hand_share = bf_opp / (bf_vl + bf_vr)
    pitchHand 'S' (ambidextrous) -> missing (too rare to define).

Level norms (FROZEN; mirrors _resolved_norms' contemporaneous-then-fallback chain):
  norm[season,level,side] = exposure-weighted (weight = h) mean of the UNSHRUNK gap
  over ALL platoon-table players at that season+level with known hand (non-switch),
  both sides >= 10 exposure and both proxies present; cell needs >= 20 qualifying
  players, else fall back to (season-1, level), else to the pooled all-season level
  norm, else 0.0. Contemporaneous league-wide norms = leakage-safe (the _season_rates
  convention). Norms are pooled across L and R (no handedness-conditional norms -
  frozen simplicity; bats_s + same_hand_share carry composition context).

Imputation (FROZEN; the _TOOL_IMPUTE lesson): missing lane features are imputed at the
observed TRAIN mean per forward-chained fold, never zero. Switch-hitter zeros are
defined values, not imputed.

Arms (efv_lab_runner protocol: forward-chained SCORED_YEARS 2020-2023, shipped ridge +
OLS-FV anchor, live blend lambda; primary target censored, resolved reported as
sensitivity; ONE attempt each, judged independently):
  ARM-HIT: lean hitter set + [platoon_gap_rel, same_hand_share, bats_s]
  ARM-PIT: lean pitcher set + [platoon_gap_rel, opp_hand_share]
Bars (FROZEN, per GATES W-PLATOON):
  full-set ship bar per side: pooled OOS blend Spearman delta >= +0.004 AND
  within-tier weighted-mean delta >= -0.0011.
  If the full-set pooled read is flat (fails), the PRE-REGISTERED FRINGE READ of the
  same run (no new fit, the LR-FRINGE convention): t45 delta >= +0.015 with pooled
  delta >= -0.0011 AND wm delta >= -0.0011.
Bootstrap (descriptive, not the bar): paired player-clustered bootstrap of the pooled
delta, 2000 reps, seed 20260724.
Cohort hypothesis (recorded a-priori, reported DESCRIPTIVELY, never gating): target
weak cells = int'l bats (hit per-cohort ifa) + top-25 pitchers (pit high tiers).

Artifact: data/xfv_platoon_eval.json. Touches NO production code; no flags flipped.

Run:  python tools/efv_platoon_lab.py --pull-hands   (data-phase, resumable)
      python tools/efv_platoon_lab.py --coverage     (join/parity dry run, no treatment)
      python tools/efv_platoon_lab.py --run          (the ONE gated attempt)
"""
from __future__ import annotations

import json
import math
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import os
os.chdir(ROOT)

import efv_lab_runner as LAB
from efv_model import _fit_ols_fv, _pred_ols, blend_lambda, _feature_spec
from efv_dataset import matrix_path
from prospect_path import _spearman, _fit_ridge, _predict

SEED = 20260724
N_BOOT = 2000
K_SPLIT = 100.0
NORM_MIN_SIDE_EXP = 10.0
NORM_MIN_PLAYERS = 20
BAR_POOLED = 0.004
BAR_WM = -0.0011
BAR_FRINGE_T45 = 0.015
BAR_FRINGE_FLOOR = -0.0011

CACHE_DIR = ROOT / ".cache" / "milb_platoon"
TABLE_PATH = CACHE_DIR / "platoon_table.json"
HAND_PATH = CACHE_DIR / "hand_map.json"
OUT_PATH = ROOT / "data" / "xfv_platoon_eval.json"

HIT_FEATS = ["platoon_gap_rel", "same_hand_share", "bats_s"]
PIT_FEATS = ["platoon_gap_rel", "opp_hand_share"]


# ---------------------------------------------------------------------------
# data-phase: handedness pull (StatsAPI /v1/people, batched, resumable cache)
# ---------------------------------------------------------------------------

def _all_needed_ids():
    tbl = json.loads(TABLE_PATH.read_text(encoding="utf-8"))["rows"]
    ids = set(tbl.keys())
    for side in ("hit", "pit"):
        for r in json.loads(matrix_path(side).read_text(encoding="utf-8")):
            m = r.get("mlbam_id")
            if m:
                ids.add(str(int(m)))
    return sorted(ids, key=int)


def pull_hands(batch=100, sleep=0.25):
    import feed_cache
    have = {}
    if HAND_PATH.exists():
        have = json.loads(HAND_PATH.read_text(encoding="utf-8"))
    ids = [i for i in _all_needed_ids() if i not in have]
    print(f"hand pull: {len(have)} cached, {len(ids)} to fetch")
    fetched = 0
    for i in range(0, len(ids), batch):
        chunk = ids[i:i + batch]
        try:
            resp = feed_cache.SESSION.get(
                "https://statsapi.mlb.com/api/v1/people",
                params={"personIds": ",".join(chunk),
                        "fields": "people,id,batSide,pitchHand,code"},
                timeout=45)
            resp.raise_for_status()
            for p in resp.json().get("people", []):
                pid = str(p.get("id"))
                have[pid] = {"bats": (p.get("batSide") or {}).get("code"),
                             "throws": (p.get("pitchHand") or {}).get("code")}
            # ids the API did not echo back: record as unknown so we do not re-loop
            for c in chunk:
                have.setdefault(c, {"bats": None, "throws": None})
            fetched += len(chunk)
        except Exception as e:  # noqa: BLE001 - resumable best-effort pull
            print(f"  batch at {i} failed ({e}); saving progress and continuing")
        if (i // batch) % 20 == 0:
            HAND_PATH.write_text(json.dumps(have), encoding="utf-8")
            print(f"  ...{fetched}/{len(ids)} fetched")
        time.sleep(sleep)
    HAND_PATH.write_text(json.dumps(have), encoding="utf-8")
    known = sum(1 for v in have.values() if v.get("bats") or v.get("throws"))
    print(f"hand pull done: {len(have)} ids cached, {known} with known handedness")


# ---------------------------------------------------------------------------
# feature construction (frozen definitions above)
# ---------------------------------------------------------------------------

def _proxy(blk):
    if not blk:
        return None
    obp, slg = blk.get("obp"), blk.get("slg")
    if obp is None or slg is None:
        return None
    return 0.6 * float(obp) + 0.4 * float(slg)


def _harm(a, b):
    a, b = float(a or 0), float(b or 0)
    return (2.0 * a * b / (a + b)) if (a > 0 and b > 0) else 0.0


def _load_table():
    return json.loads(TABLE_PATH.read_text(encoding="utf-8"))["rows"]


def _load_hands():
    return json.loads(HAND_PATH.read_text(encoding="utf-8"))


def _gap_for(sides, side, hand):
    """Unshrunk gap + harmonic exposure for one player-season-level block.
    hit: gap = proxy(same-hand) - proxy(opp-hand), needs bats in {L,R}.
    pit: gap = proxy(opp-hand batters) - proxy(same-hand batters), throws in {L,R}.
    Returns (gap, h) or (None, 0)."""
    blk = (sides or {}).get(side) or {}
    vl, vr = blk.get("vl"), blk.get("vr")
    ek = "pa" if side == "hit" else "bf"
    if hand not in ("L", "R") or not vl or not vr:
        return None, 0.0
    if side == "hit":
        same, opp = (vl, vr) if hand == "L" else (vr, vl)
    else:
        opp, same = (vr, vl) if hand == "L" else (vl, vr)
    ps, po = _proxy(same), _proxy(opp)
    if ps is None or po is None:
        return None, 0.0
    h = _harm(same.get(ek), opp.get(ek))
    if h <= 0:
        return None, 0.0
    if side == "hit":
        return ps - po, h
    return po - ps, h   # already ordered opp-minus-same above


def build_norms(tbl, hands):
    """norm[(season, level, side)] = h-weighted mean UNSHRUNK gap over qualifying
    league players (known non-switch hand, both sides >= NORM_MIN_SIDE_EXP,
    proxies present). Fallback: season-1 same level -> pooled level -> 0.0."""
    acc = defaultdict(lambda: [0.0, 0.0, 0])   # (sum h*gap, sum h, n)
    pooled = defaultdict(lambda: [0.0, 0.0, 0])
    for mid, seasons in tbl.items():
        hd = hands.get(mid) or {}
        for season, levels in seasons.items():
            for level, sides in levels.items():
                for side in ("hit", "pit"):
                    hand = hd.get("bats" if side == "hit" else "throws")
                    blk = sides.get(side) or {}
                    vl, vr = blk.get("vl"), blk.get("vr")
                    if not vl or not vr:
                        continue
                    ek = "pa" if side == "hit" else "bf"
                    if (float(vl.get(ek) or 0) < NORM_MIN_SIDE_EXP
                            or float(vr.get(ek) or 0) < NORM_MIN_SIDE_EXP):
                        continue
                    gap, h = _gap_for(sides, side, hand)
                    if gap is None:
                        continue
                    for d in (acc[(int(season), level, side)], pooled[(level, side)]):
                        d[0] += h * gap
                        d[1] += h
                        d[2] += 1
    cells = {k: (v[0] / v[1], v[2]) for k, v in acc.items() if v[1] > 0}
    pool = {k: (v[0] / v[1]) for k, v in pooled.items() if v[1] > 0}

    def norm_of(season, level, side):
        for s in (season, season - 1):
            c = cells.get((s, level, side))
            if c and c[1] >= NORM_MIN_PLAYERS:
                return c[0]
        return pool.get((level, side), 0.0)
    return norm_of, cells, pool


def build_features(side):
    """{player_key: {feat: val|None}} for the eval pool + a per-player debug block.
    None = missing (train-mean imputed per fold). Uses the FINAL pre-decision
    season at the PRIMARY level from the matrix row (frozen join)."""
    tbl = _load_table()
    hands = _load_hands()
    norm_of, cells, pool = build_norms(tbl, hands)
    feats, debug = {}, {}
    names = HIT_FEATS if side == "hit" else PIT_FEATS
    for r in json.loads(matrix_path(side).read_text(encoding="utf-8")):
        if r.get("kind") != "debuted":
            continue
        pk = r["player_key"]
        out = {k: None for k in names}
        m = r.get("milb") or {}
        mid = str(int(r["mlbam_id"])) if r.get("mlbam_id") else None
        season, level = m.get("milb_season"), m.get("milb_level")
        hd = (hands.get(mid) or {}) if mid else {}
        hand = hd.get("bats" if side == "hit" else "throws")
        sides = (((tbl.get(mid) or {}).get(str(season)) or {}).get(level)
                 if (mid and season and level) else None)
        blk = (sides or {}).get(side) or {}
        vl, vr = blk.get("vl"), blk.get("vr")
        ek = "pa" if side == "hit" else "bf"
        tot = float((vl or {}).get(ek) or 0) + float((vr or {}).get(ek) or 0)
        if side == "hit":
            if hand == "S":
                out = {"platoon_gap_rel": 0.0, "same_hand_share": 0.0, "bats_s": 1.0}
            elif hand in ("L", "R"):
                out["bats_s"] = 0.0
                if tot > 0:
                    same_blk = vl if hand == "L" else vr
                    out["same_hand_share"] = float((same_blk or {}).get(ek) or 0) / tot
                gap, h = _gap_for(sides, side, hand)
                if gap is not None:
                    w = h / (h + K_SPLIT)
                    nv = norm_of(int(season), level, side)
                    out["platoon_gap_rel"] = w * (gap - nv)
                    debug[pk] = {"mlbam": mid, "season": season, "level": level,
                                 "hand": hand, "vl": vl, "vr": vr, "gap_raw": gap,
                                 "h": h, "w": w, "norm": nv,
                                 "feature": out["platoon_gap_rel"]}
        else:
            if hand in ("L", "R"):
                if tot > 0:
                    opp_bf = float(((vr if hand == "L" else vl) or {}).get(ek) or 0)
                    out["opp_hand_share"] = opp_bf / tot
                gap, h = _gap_for(sides, side, hand)
                if gap is not None:
                    w = h / (h + K_SPLIT)
                    nv = norm_of(int(season), level, side)
                    out["platoon_gap_rel"] = w * (gap - nv)
                    debug[pk] = {"mlbam": mid, "season": season, "level": level,
                                 "hand": hand, "vl": vl, "vr": vr, "gap_raw": gap,
                                 "h": h, "w": w, "norm": nv,
                                 "feature": out["platoon_gap_rel"]}
        feats[pk] = out
    return feats, debug


# ---------------------------------------------------------------------------
# forward-chained eval (mirrors efv_lab_runner.run_variant exactly, plus
# per-fold train-mean imputation for the lane features)
# ---------------------------------------------------------------------------

def _tier(fv):
    return round(fv / 5) * 5


def _era(yr):
    return "<=2018" if yr <= 2018 else ("2019-2021" if yr <= 2021 else "2022-2023")


def run_arm(side, target, extra_names, extra_map):
    """extra_names [] -> the baseline (must reproduce LAB.run_variant exactly).
    extra_map: {player_key: {name: val|None}}. Missing (None / absent player) values
    are imputed at the observed TRAIN mean of that fold, never zero."""
    tkey = {"censored": "target_censored", "resolved": "target_resolved"}[target]
    keys = _feature_spec(side)[0] + list(extra_names)
    rows = [r for r in LAB.data_for(side) if r.get(tkey) is not None]
    base_lam = blend_lambda(side)

    def lane_val(r, name):
        d = extra_map.get(r["player_key"]) or {}
        return d.get(name)

    pooled, per_year = [], defaultdict(list)
    for yr in LAB.SCORED_YEARS:
        tr = [r for r in rows if r["decision_year"] < yr]
        te = [r for r in rows if r["decision_year"] == yr]
        if len(te) < 12 or len(tr) < 50:
            continue
        # per-fold train means for imputation
        mu = {}
        for name in extra_names:
            obs = [lane_val(r, name) for r in tr]
            obs = [v for v in obs if v is not None]
            mu[name] = (sum(obs) / len(obs)) if obs else 0.0

        def fx(r):
            if not extra_names:
                return r["feats"]
            f = dict(r["feats"])
            for name in extra_names:
                v = lane_val(r, name)
                f[name] = float(v) if v is not None else mu[name]
            return f

        trf = [{"feats": fx(r), "target": r[tkey], "weight": r["weight"], "fv": r["fv"]}
               for r in tr]
        ols = _fit_ols_fv([{"fv": r["fv"], "target": r[tkey]} for r in tr])
        ridge = _fit_ridge(trf, keys)
        if not (ols and ridge):
            continue
        for r in te:
            rp = _predict(ridge, fx(r))
            cw = max(0.0, _pred_ols(ols, r["fv"]))
            blend = (1 - base_lam) * cw + base_lam * rp
            pooled.append((blend, r[tkey], r["fv"], r["cohort"], r["player_key"]))
            per_year[yr].append((blend, r[tkey]))

    sp = _spearman([a for a, _, _, _, _ in pooled], [b for _, b, _, _, _ in pooled])
    byt = defaultdict(list)
    for pr, t, fv, _, _ in pooled:
        byt[_tier(fv)].append((pr, t))
    wsum = wn = 0
    t45 = None
    per_tier = {}
    for tk, grp in byt.items():
        if len(grp) < 15:
            continue
        rr = _spearman([a for a, _ in grp], [b for _, b in grp])
        if rr is None:
            continue
        per_tier[tk] = {"n": len(grp), "rho": round(rr, 4)}
        wsum += rr * len(grp)
        wn += len(grp)
        if tk == 45:
            t45 = round(rr, 4)
    bye = defaultdict(list)
    for yr, prs in per_year.items():
        bye[_era(yr)].extend(prs)
    era = {k: round(_spearman([a for a, _ in g], [b for _, b in g]), 4)
           for k, g in bye.items()
           if len(g) >= 15 and _spearman([a for a, _ in g], [b for _, b in g]) is not None}
    byc = defaultdict(list)
    for pr, t, fv, c, _ in pooled:
        byc[c].append((pr, t))
    coh = {k: {"n": len(g), "rho": round(_spearman([a for a, _ in g], [b for _, b in g]), 4)}
           for k, g in byc.items()
           if len(g) >= 25 and _spearman([a for a, _ in g], [b for _, b in g]) is not None}
    return {"n": len(pooled), "spearman": round(sp, 4),
            "within_tier_wm": round(wsum / wn, 4) if wn else None,
            "t45": t45, "per_tier": per_tier, "era": era, "per_cohort": coh,
            "_pooled": pooled}


def boot_delta(base_pooled, treat_pooled, seed=SEED, reps=N_BOOT):
    """Paired player-clustered bootstrap of (rho_treat - rho_base). Rows are one per
    player (asserted), so player-clustered = row resampling here."""
    assert len(base_pooled) == len(treat_pooled)
    for b, t in zip(base_pooled, treat_pooled):
        assert b[4] == t[4], "pooled rows misaligned"
    pks = [b[4] for b in base_pooled]
    assert len(pks) == len(set(pks)), "player appears twice; need clustering"
    n = len(base_pooled)
    rng = random.Random(seed)
    deltas = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        rb = _spearman([base_pooled[i][0] for i in idx], [base_pooled[i][1] for i in idx])
        rt = _spearman([treat_pooled[i][0] for i in idx], [treat_pooled[i][1] for i in idx])
        if rb is not None and rt is not None:
            deltas.append(rt - rb)
    deltas.sort()
    if not deltas:
        return None
    lo = deltas[int(0.025 * len(deltas))]
    hi = deltas[min(len(deltas) - 1, int(0.975 * len(deltas)))]
    return {"reps": len(deltas), "mean": round(sum(deltas) / len(deltas), 4),
            "lo95": round(lo, 4), "hi95": round(hi, 4)}


# ---------------------------------------------------------------------------
# coverage / parity dry run (no treatment correlations computed)
# ---------------------------------------------------------------------------

def coverage():
    for side in ("hit", "pit"):
        names = HIT_FEATS if side == "hit" else PIT_FEATS
        fmap, dbg = build_features(side)
        pool = LAB.data_for(side)
        n = len(pool)
        cov = {k: sum(1 for r in pool if (fmap.get(r["player_key"]) or {}).get(k) is not None)
               for k in names}
        print(f"{side}: eval pool {n}; feature coverage " +
              ", ".join(f"{k}={v} ({100.0*v/n:.1f}%)" for k, v in cov.items()))
        mine = run_arm(side, "censored", [], {})
        ref = LAB.run_variant({"id": f"parity:{side}", "side": side, "target": "censored"})
        ok = (mine["spearman"] == ref["spearman"] and mine["n"] == ref["n"]
              and mine["within_tier_wm"] == ref["within_tier_wm"])
        print(f"{side}: parity vs efv_lab_runner baseline: "
              f"mine rho={mine['spearman']} wm={mine['within_tier_wm']} n={mine['n']} | "
              f"ref rho={ref['spearman']} wm={ref['within_tier_wm']} n={ref['n']} -> "
            f"{'OK' if ok else 'MISMATCH'}")


# ---------------------------------------------------------------------------
# the ONE gated run
# ---------------------------------------------------------------------------

def _delta(t, b, key):
    tv, bv = t.get(key), b.get(key)
    if tv is None or bv is None:
        return None
    return round(tv - bv, 4)


def run():
    rng_note = {"seed": SEED, "bootstrap_reps": N_BOOT, "clustered": "player"}
    hands = _load_hands()
    known = sum(1 for v in hands.values() if v.get("bats") or v.get("throws"))
    artifact = {
        "generated_at": "2026-07-24",
        "experiment": "W-PLATOON: platoon split features (headline lane, one attempt per arm)",
        "registration": "docs/efv-2026-07-24/GATES.md section W-PLATOON (Phase 2a)",
        "sentinel": "LANE-SENTINEL-W-PLATOON-20260724",
        "frozen": {
            "woba_proxy": "0.6*obp + 0.4*slg per split block",
            "split_exposure": "harmonic mean h = 2ab/(a+b) of the two sides' pa/bf",
            "shrink": "w = h/(h + 100)",
            "norm": "h-weighted league mean unshrunk gap per (season, level, side), "
                    "cells >= 20 players w/ >= 10 exposure both sides; fallback "
                    "season-1 -> pooled level -> 0; contemporaneous = leakage-safe",
            "join": "final pre-decision season at the matrix PRIMARY level only",
            "imputation": "per-fold TRAIN observed means, never zero",
            "switch_hitters": "gap_rel = 0.0, same_hand_share = 0.0, bats_s = 1.0 (defined)",
            "hit_weak_side": "same-hand matchup; gap = proxy(same) - proxy(opp)",
            "pit_gap": "opposite-hand vulnerability; gap = proxy(opp) - proxy(same)",
            "bats_source": "StatsAPI /v1/people batSide/pitchHand (DB players table has no "
                           "bats column; draft_players/overseas_players bats overlap with the "
                           "debuted eval pool is ZERO - measured 0/845)",
            "primary_target": "censored (resolved = sensitivity only)",
            "declared_before_first_run": True,
            "one_attempt": True,
        },
        "bars": {"full_pooled": BAR_POOLED, "full_wm_floor": BAR_WM,
                 "fringe_t45": BAR_FRINGE_T45, "fringe_floor": BAR_FRINGE_FLOOR},
        "bootstrap": rng_note,
        "hand_map": {"ids_cached": len(hands), "known_handedness": known},
        "stop_d": {"bar": "split coverage < 60% of matrix player-seasons 2015+",
                   "measured": "99.3% (coverage_summary.json)", "triggered": False},
        "arms": {},
    }

    for side in ("hit", "pit"):
        names = HIT_FEATS if side == "hit" else PIT_FEATS
        fmap, dbg = build_features(side)
        pool = LAB.data_for(side)
        n = len(pool)
        cov = {k: sum(1 for r in pool if (fmap.get(r["player_key"]) or {}).get(k) is not None)
               for k in names}
        arm = {"features": names,
               "eval_pool_n": n,
               "coverage": {k: {"n": v, "pct": round(100.0 * v / n, 1)} for k, v in cov.items()}}

        res_by_target = {}
        for target in ("censored", "resolved"):
            base = run_arm(side, target, [], {})
            treat = run_arm(side, target, names, fmap)
            d = {
                "spearman": _delta(treat, base, "spearman"),
                "within_tier_wm": _delta(treat, base, "within_tier_wm"),
                "t45": _delta(treat, base, "t45"),
                "era": {e: round((treat["era"].get(e) or 0) - (base["era"].get(e) or 0), 4)
                        for e in set(base["era"]) | set(treat["era"])},
                "per_tier": {tk: round(treat["per_tier"][tk]["rho"] - base["per_tier"][tk]["rho"], 4)
                             for tk in set(base["per_tier"]) & set(treat["per_tier"])},
                "per_cohort": {c: round(treat["per_cohort"][c]["rho"] - base["per_cohort"][c]["rho"], 4)
                               for c in set(base["per_cohort"]) & set(treat["per_cohort"])},
            }
            entry = {
                "baseline": {k: base[k] for k in ("n", "spearman", "within_tier_wm", "t45",
                                                  "era", "per_cohort", "per_tier")},
                "treatment": {k: treat[k] for k in ("n", "spearman", "within_tier_wm", "t45",
                                                    "era", "per_cohort", "per_tier")},
                "delta": d,
            }
            if target == "censored":
                entry["bootstrap_delta"] = boot_delta(base["_pooled"], treat["_pooled"])
            res_by_target[target] = entry
        arm["results_by_target"] = res_by_target

        prim = res_by_target["censored"]["delta"]
        full_pass = (prim["spearman"] is not None and prim["spearman"] >= BAR_POOLED
                     and prim["within_tier_wm"] is not None
                     and prim["within_tier_wm"] >= BAR_WM)
        arm["gate_full"] = {
            "pooled_delta": prim["spearman"], "bar": BAR_POOLED,
            "wm_delta": prim["within_tier_wm"], "wm_floor": BAR_WM,
            "pass": full_pass,
        }
        if not full_pass:
            fr_pass = (prim["t45"] is not None and prim["t45"] >= BAR_FRINGE_T45
                       and prim["spearman"] is not None and prim["spearman"] >= BAR_FRINGE_FLOOR
                       and prim["within_tier_wm"] is not None
                       and prim["within_tier_wm"] >= BAR_FRINGE_FLOOR)
            arm["gate_fringe"] = {
                "note": "pre-registered read of the SAME run (no new fit)",
                "t45_delta": prim["t45"], "bar": BAR_FRINGE_T45,
                "pooled_delta": prim["spearman"], "wm_delta": prim["within_tier_wm"],
                "floor": BAR_FRINGE_FLOOR, "pass": fr_pass,
            }
            arm["verdict"] = "SHIP-FRINGE" if fr_pass else "FAIL"
        else:
            arm["verdict"] = "SHIP"

        # a-priori cohort reads (descriptive only, never gating)
        arm["cohort_reads_descriptive"] = {
            "note": "a-priori weak cells: int'l bats (hit ifa) + top-25 pitchers "
                    "(high tiers); +-0.01 AUC-scale noise floor stands; NEVER gating",
            "hit_ifa_delta": prim["per_cohort"].get("ifa") if side == "hit" else None,
            "pit_high_tier_deltas": ({tk: v for tk, v in prim["per_tier"].items() if tk >= 50}
                                     if side == "pit" else None),
        }

        # named extreme examples with hand-checkable raw splits
        exs = sorted(dbg.items(), key=lambda kv: -abs(kv[1]["feature"]))
        pool_pks = {r["player_key"] for r in pool}
        exs = [(pk, d) for pk, d in exs if pk in pool_pks][:3]
        arm["named_examples"] = [
            {"player_key": pk,
             "season": d["season"], "level": d["level"], "hand": d["hand"],
             "vl": d["vl"], "vr": d["vr"],
             "woba_proxy_vl": round(_proxy(d["vl"]), 4) if _proxy(d["vl"]) is not None else None,
             "woba_proxy_vr": round(_proxy(d["vr"]), 4) if _proxy(d["vr"]) is not None else None,
             "gap_raw": round(d["gap_raw"], 4), "level_norm": round(d["norm"], 4),
             "harmonic_exposure": round(d["h"], 1), "shrink_w": round(d["w"], 3),
             "platoon_gap_rel": round(d["feature"], 4)}
            for pk, d in exs]

        artifact["arms"][f"ARM-{side.upper()}"] = arm
        print(f"ARM-{side.upper()}: pooled d={prim['spearman']} wm d={prim['within_tier_wm']} "
              f"t45 d={prim['t45']} -> {arm['verdict']}")

    verdicts = {k: v["verdict"] for k, v in artifact["arms"].items()}
    if all(v == "FAIL" for v in verdicts.values()):
        artifact["loss_ledger"] = {
            "verdict": "FAIL both sides",
            "summary": "Platoon split features (final pre-decision season, frozen list) did "
                       "not clear the pre-registered pooled bar or the fringe read on either "
                       "side at the current matrix vintage. One attempt per arm spent; lean "
                       "sets unchanged (byte-neutral); no re-litigation.",
        }
    artifact["verdicts"] = verdicts
    OUT_PATH.write_text(json.dumps(artifact, indent=1), encoding="utf-8")
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    if "--pull-hands" in sys.argv:
        pull_hands()
    elif "--coverage" in sys.argv:
        coverage()
    elif "--run" in sys.argv:
        run()
    else:
        print(__doc__)
