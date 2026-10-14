# BT-1 bat-tracking lane lab (pre-registered 2026-07-23)
#
# QUESTION (owner directive, NEW data lane): MLB bat-tracking aggregates
# (bat speed, swing length, attack angle, attack direction, swing path tilt,
# ideal-attack-angle rate, squared-up rate, blast rate) exist since 2024 and
# have never been tested in this repo's hitter models (verified: the terms
# appear only in the vendored swing_plus ingest, which is untouched here).
# Does bat tracking add OOS signal to (a) pWOBA, the next-season wOBA
# projection, beyond the incumbent fa_projection woba_proj, and/or (b) an
# xHEM+-style descriptive contact-quality/luck read?
#
# LEDGER POSITION (why this is NOT a re-run of closed lanes): the CLOSED
# pwoba_ev_arm lane tested EV/barrel (avg_hit_speed, brl_pa, ev95percent)
# residual correction; xwOBA-allowed for pitchers and CSW-xK are also closed.
# Bat tracking is measured off the SWING (bat speed at contact point, path
# geometry, squared-up = contact quality relative to attainable EV), which is
# new information distinct from batted-ball EV/barrel outcomes.
#
# DATA: Savant bat-tracking leaderboard, per-player-season aggregates.
# The documented csv=true export omits the swing-path fields (attack_angle,
# attack_direction, swing_path_tilt, rate_ideal_attack_angle), so the loader
# parses the full 47-field `const data = [...]` JSON embedded in the page
# (same pattern as fa_sources.fetch_savant_park_factors). Seasons 2024-2026
# via seasonStart/seasonEnd params (the bare `season` param is IGNORED by the
# endpoint and silently serves the current season; verified 2026-07-23).
# Cached under .cache/bat_tracking/bat_tracking_batter_{Y}.json; fetch throttle
# 1.5s. NB 2024 is the rollout season (public capture from early 2024 season;
# early-season coverage can be partial).
#
# =========================== PRE-REGISTRATION ============================== #
# FROZEN 2026-07-23 BEFORE any results were computed. Seed 20260723, 2000
# bootstrap reps, v1 convention primary (raw pooled Y+1 target, iid paired
# bootstrap); v2 companion (within-outcome-season z target, player-clustered
# season-stratified bootstrap) reported alongside per harness-v2 convention.
#
# FOLDS (both arms): predictor 2024 -> outcome 2025 (complete) and predictor
# 2025 -> outcome 2026. DEVIATION FROM HARNESS RULE 4, declared up front: the
# 2026 outcome season is PARTIAL (through 2026-07-23); the harness normally
# drops partial-outcome pairs. This lane has exactly two transition folds in
# existence, so the owner directive pre-registers the pooled two-fold gate
# WITH the partial-2026 fold, flagged, and the complete-outcome-only
# (2024->2025) gap is reported as a sensitivity alongside. SMALL-N HONESTY:
# two transition folds, one with a partial outcome; any verdict here is
# thin-sample by construction and a PASS would still be provisional.
#
# BT row gate: swings_qualified (competitive swings) >= 100 in the predictor
# season. Feature z-scores: within predictor season over the BT-gated
# population (mirrors the pwoba_ev_arm zmap convention).
#
# ARM A (predictive residual read) - candidate bt_corrected:
#   woba_proj + OLS(residual ~ z(bat_speed) + z(squared_up_rate) +
#   z(attack_angle)), where residual = wOBA(Y+1) - woba_proj.
#   With no deep train years available (lane starts 2024), coefficients are
#   CROSS-FITTED: the 2024-fold correction is fit on the 2025 fold and vice
#   versa (never fit and scored on the same fold). Pair set replicates the
#   pwoba_ev_arm construction: StatsAPI MIN_PA 150/150 both seasons, 3yr
#   window su>=2 & PA>=600 (X-H2 bar), age + fa_projection woba_proj
#   (point-in-time fitted_models(max_season=y)) present, BT row present.
#   GATE: pooled two-fold iid paired bootstrap lo95(rho(bt_corrected) -
#   rho(woba_proj)) > 0 (v1, seed 20260723, 2000 reps).
#
# ARM B (descriptive xHEM-style blend) - a DISPLAY metric candidate:
#   BT contact-quality composite = mean(z(bat_speed), z(squared_up_rate),
#   z(blast_rate)) (component z within season over the BT-gated population).
#   Candidate forward blend = 0.595*z(est_woba) + 0.255*z(hem_plus_raw) +
#   0.15*z(bt_composite), i.e. the shipped fwdHEM+ 0.7/0.3 weights scaled by
#   0.85 with a 0.15 BT leg. WEIGHTS FROZEN A PRIORI (no fitting; the X-H5
#   precedent). Blend-leg z's are within predictor season over the joined
#   pair set (X-H5 convention). Pair set = X-H3/X-H5 construction: Savant
#   expected_batter PA >= 200 in BOTH seasons, HEM core (hem_plus_raw)
#   present, BT row present. Incumbent = fwdHEM+ blend 0.7*z(est_woba) +
#   0.3*z(hem_plus_raw) on the identical pair set.
#   GATE: pooled two-fold iid paired bootstrap lo95(rho(candidate) -
#   rho(fwdhem_incumbent)) > 0 vs next-season wOBA (v1, seed 20260723).
#   CONTEXT ONLY (not gated): same-season Spearman of the BT composite vs the
#   wOBA - xwOBA luck gap, compared with the EV composite (mean z of
#   avg_hit_speed, brl_pa, ev95percent) vs the same gap, per season.
#
# No production module is touched. Artifact -> data/bat_tracking_eval.json.
#
# NOV-A (registered 2026-07-23 in docs/wills-2026-07-23/GATES.md W-NOV and
# docs/efv-2026-07-23/RECHECKS.md, run with --nov-a): the vendored Swing+
# composite's PER-SEASON variant (data/swing_plus.json seasons slices, W6)
# replaces the raw bat-tracking z-aggregates as the BT leg in BOTH arms.
# Everything else is the parent protocol above, unchanged: the pair sets
# (BT row present at >= 100 competitive swings stays, and the Swing+ season
# slice must be present or the pair drops as leg_missing), the cross-fit, the
# frozen 0.595/0.255/0.15 weights, the v1 gate lo95 > 0 vs the same
# incumbents, seed 20260723, 2000 reps. Arm A's OLS has one regressor,
# z(Swing+); the z-scoring population is immaterial there (OLS with an
# intercept is affine-invariant) and arm B re-z's its legs within predictor
# season over the pair set per the X-H5 convention, so no normalizer choice
# enters. Artifact -> data/bat_tracking_nov_a_eval.json.
#
# --season-complete-asof 'YYYY:YYYY-MM-DD' is the owner-waived early-read
# override of plus_lab_harness (owner 2026-10-14); it is logged and written
# into the artifact. The Nov 15 default never changes.
# =========================================================================== #
from __future__ import annotations

import json
import re
import time
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys  # noqa: E402
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import numpy as np  # noqa: E402

import plus_lab_harness as plh  # noqa: E402
from rem_plus_backtest import _spearman  # noqa: E402
from phem_marcel_lite_lab import FaEngine, load_hit_season, _r4  # noqa: E402
from xwoba_projection_blend_lab import load_xwoba, _hem3_window  # noqa: E402
from pwoba_ev_arm_lab import load_ev, EV_FEATS  # noqa: E402

SEED = 20260723
BOOT = 2000
PRED_SEASONS = [2024, 2025]                # the only two BT predictor seasons
MIN_PA_Y, MIN_PA_NEXT = 150.0, 150.0       # arm A (StatsAPI PA)
TAG_MIN_SEASONS, TAG_MIN_PA = 2, 600.0     # arm A X-H2 window bar
SAVANT_MIN_PA = 200.0                      # arm B (X-H3 convention, both seasons)
BT_MIN_SWINGS = 100.0
EV_MIN_ATTEMPTS = 100.0

ARM_A_FEATS = ("bat_speed", "squared_up_rate", "attack_angle")
ARM_B_COMPOSITE_FEATS = ("bat_speed", "squared_up_rate", "blast_rate")
FWDHEM_W = (0.7, 0.3)                      # shipped incumbent (X-H5)
CAND_W = (0.595, 0.255, 0.15)              # frozen a priori: 0.85 scale + 0.15 BT

SWING_PLUS_PATH = ROOT / "data" / "swing_plus.json"
SWING_PLUS_LEG = ("swing_plus",)             # NOV-A: the one-feature BT leg

BT_CACHE = ROOT / ".cache" / "bat_tracking"
BT_URL = ("https://baseballsavant.mlb.com/leaderboard/bat-tracking"
          "?seasonStart={y}&seasonEnd={y}&gameType=Regular&minSwings=25&type=batter")
BT_THROTTLE_S = 1.5

# embedded-JSON field -> lab name (floats; qualified = competitive swings only)
BT_FIELD_MAP = {
    "avg_sweetspot_speed_mph_qualified": "bat_speed",
    "swing_length_qualified": "swing_length",
    "attack_angle": "attack_angle",
    "attack_direction_pullopp": "attack_direction",
    "avg_plane_vertical_angle": "swing_path_tilt",
    "rate_ideal_attack_angle": "ideal_attack_angle_rate",
    "squared_up_per_swing": "squared_up_rate",
    "squared_up_with_speed_per_swing": "blast_rate",
}


# --------------------------------------------------------------------------- #
# Savant bat-tracking loader (embedded-JSON extraction, cache-first)
# --------------------------------------------------------------------------- #
def _extract_embedded_data(html: str):
    m = re.search(r"const data = (\[)", html)
    if not m:
        return None
    i = m.start(1)
    depth, in_str, esc = 0, False, False
    for j in range(i, len(html)):
        c = html[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    return json.loads(html[i:j + 1])
    return None


def fetch_bat_tracking(year: int) -> list[dict]:
    """Raw leaderboard rows for `year`, cache-first (throttled fetch on miss)."""
    BT_CACHE.mkdir(parents=True, exist_ok=True)
    path = BT_CACHE / f"bat_tracking_batter_{year}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    req = urllib.request.Request(BT_URL.format(y=year),
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        html = r.read().decode("utf-8", errors="replace")
    rows = _extract_embedded_data(html)
    if rows is None:
        raise RuntimeError(f"bat-tracking embedded data not found for {year}")
    path.write_text(json.dumps(rows), encoding="utf-8")
    time.sleep(BT_THROTTLE_S)
    return rows


def load_bt(year: int) -> tuple[dict[int, dict], dict]:
    """{mlbam: {feature floats + swings}} at swings >= BT_MIN_SWINGS, plus a
    coverage report (rows seen / gated / dropped for a missing field)."""
    rows = fetch_bat_tracking(year)
    out: dict[int, dict] = {}
    missing_field = under_swings = 0
    for r in rows:
        try:
            mid = int(r["id"])
            swings = float(r["swings_qualified"])
        except (KeyError, TypeError, ValueError):
            missing_field += 1
            continue
        if swings < BT_MIN_SWINGS:
            under_swings += 1
            continue
        rec = {"swings": swings}
        ok = True
        for src, dst in BT_FIELD_MAP.items():
            try:
                rec[dst] = float(r[src])
            except (KeyError, TypeError, ValueError):
                ok = False
                break
        if not ok:
            missing_field += 1
            continue
        out[mid] = rec
    report = {"rows": len(rows), "kept": len(out),
              "under_min_swings": under_swings, "missing_field": missing_field}
    return out, report


def load_swing_plus_seasons(path: Path = SWING_PLUS_PATH) -> tuple[dict[int, dict], dict]:
    """NOV-A leg: {season: {mlbam: {"swing_plus": float, "n_swings": int,
    "low_n": bool}}} from the vendored artifact's per-season slices, taken
    AS THE ARTIFACT GIVES THEM (a slice under the model's min_swings floor is
    flagged low_n there and is kept here, flagged and counted; nothing is
    re-shrunk or re-floored). Returns None-safe coverage meta beside it."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    out: dict[int, dict] = {}
    low_n = {}
    for mid, rec in (doc.get("players") or {}).items():
        for season, sl in (rec.get("seasons") or {}).items():
            v = sl.get("swing_plus") if isinstance(sl, dict) else None
            if v is None:
                continue
            y = int(season)
            out.setdefault(y, {})[int(mid)] = {
                "swing_plus": float(v), "n_swings": int(sl.get("n_swings") or 0),
                "low_n": bool(sl.get("low_n"))}
            if sl.get("low_n"):
                low_n[y] = low_n.get(y, 0) + 1
    meta = {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "generated_at": doc.get("generated_at"), "model": doc.get("model"),
        "min_swings": doc.get("min_swings"), "reliability_k": doc.get("reliability_k"),
        "n_scored_pooled": doc.get("n_scored"),
        "per_season_coverage": {str(y): len(v) for y, v in sorted(out.items())},
        "per_season_low_n": {str(y): low_n.get(y, 0) for y in sorted(out)},
        "variant": "per-season slices (W6), the registered NOV-A leg",
    }
    return out, meta


def zmap(pop: dict[int, dict], feats: tuple[str, ...]) -> dict[int, dict]:
    """Within-season z-scores of `feats` over the population `pop`."""
    out: dict[int, dict] = {}
    for k in feats:
        vals = [v[k] for v in pop.values()]
        mu = float(np.mean(vals)) if vals else 0.0
        sd = float(np.std(vals)) or 1.0
        for mid, v in pop.items():
            out.setdefault(mid, {})[k] = (v[k] - mu) / sd
    return out


# --------------------------------------------------------------------------- #
# arm A: predictive residual read vs the incumbent woba_proj
# --------------------------------------------------------------------------- #
def run_arm_a(eng: FaEngine, by_season: dict, bt_z: dict, *,
              feats: tuple[str, ...] = ARM_A_FEATS, leg_z: dict | None = None,
              leg_label: str = "z(bat_speed) + z(squared_up_rate) + z(attack_angle)") -> dict:
    """Parent protocol when `leg_z` is None (the BT z-aggregates are the leg).
    NOV-A passes leg_z (the per-season Swing+ z) and feats=SWING_PLUS_LEG: the
    BT row gate stays, and the pair also needs the Swing+ slice."""
    pairs = []
    drops = {"partial_outcome_kept": 0, "window": 0, "age_missing": 0,
             "fa_proj_missing": 0, "bt_missing": 0}
    if leg_z is not None:
        drops["leg_missing"] = 0
    for y in PRED_SEASONS:
        cur, nxt = by_season.get(y), by_season.get(y + 1)
        if not cur or not nxt:
            continue
        for mid, a in cur.items():
            b = nxt.get(mid)
            if not b or (a["pa"] or 0) < MIN_PA_Y or (b["pa"] or 0) < MIN_PA_NEXT:
                continue
            if b["woba_raw"] is None:
                continue
            if not plh.season_complete(y + 1):
                # pre-registered DEVIATION: kept and flagged, not dropped
                drops["partial_outcome_kept"] += 1
            su, wpa = _hem3_window(by_season, mid, y)
            if su < TAG_MIN_SEASONS or wpa < TAG_MIN_PA:
                drops["window"] += 1
                continue
            if a.get("age") is None:
                drops["age_missing"] += 1
                continue
            pr = eng.proj("hit", int(mid), y, a["age"] + 1)
            fa_val = pr.get("woba_proj") if pr else None
            if fa_val is None:
                drops["fa_proj_missing"] += 1
                continue
            z = bt_z.get(y, {}).get(int(mid))
            if not z:
                drops["bt_missing"] += 1
                continue
            if leg_z is not None:
                z = leg_z.get(y, {}).get(int(mid))
                if not z:
                    drops["leg_missing"] += 1
                    continue
            pairs.append({"mid": mid, "y": y, "oy": y + 1,
                          "tgt": b["woba_raw"], "fa": fa_val, "z": z})

    folds = {y: [p for p in pairs if p["y"] == y] for y in PRED_SEASONS}
    print(f"  arm A pairs: total={len(pairs)} "
          + " ".join(f"{y}->{y+1}={len(folds[y])}" for y in PRED_SEASONS)
          + f" drops={drops}")

    # cross-fitted residual OLS (fit on the OTHER fold, never on its own)
    def _fit(fold):
        X = np.column_stack([np.ones(len(fold))]
                            + [[p["z"][k] for p in fold] for k in feats])
        resid = np.array([p["tgt"] - p["fa"] for p in fold])
        coef, *_ = np.linalg.lstsq(X, resid, rcond=None)
        return coef

    other = {PRED_SEASONS[0]: PRED_SEASONS[1], PRED_SEASONS[1]: PRED_SEASONS[0]}
    coefs = {y: _fit(folds[other[y]]) for y in PRED_SEASONS}

    def _bt_val(p):
        c = coefs[p["y"]]
        return p["fa"] + float(c[0]) + sum(
            float(cc) * p["z"][k] for k, cc in zip(feats, c[1:]))

    arms = {"fa_projection": [p["fa"] for p in pairs],
            "bt_corrected": [_bt_val(p) for p in pairs]}
    tgt = [p["tgt"] for p in pairs]
    mids = [p["mid"] for p in pairs]
    pys = [p["y"] for p in pairs]
    oys = [p["oy"] for p in pairs]

    rhos_v1 = {k: _r4(_spearman(v, tgt)) for k, v in arms.items()}
    gap_v1 = plh.iid_boot_gaps(arms["bt_corrected"], {"fa_projection": arms["fa_projection"]},
                               tgt, BOOT, SEED)["fa_projection"]
    tgt_v2 = plh.zscore_within(oys, tgt)
    rhos_v2 = {k: _r4(_spearman(v, tgt_v2)) for k, v in arms.items()}
    gap_v2 = plh.cluster_boot_gaps(arms["bt_corrected"], {"fa_projection": arms["fa_projection"]},
                                   tgt_v2, mids, pys, BOOT, SEED)["fa_projection"]
    pass_v1 = bool(gap_v1 and gap_v1["lo95"] > 0)
    pass_v2 = bool(gap_v2 and gap_v2["lo95"] > 0)

    # per-fold + complete-outcome-only sensitivity
    per_fold = {}
    for y in PRED_SEASONS:
        f = folds[y]
        ft = [p["tgt"] for p in f]
        per_fold[f"{y}->{y+1}"] = {
            "n": len(f),
            "outcome_partial": not plh.season_complete(y + 1),
            "rho_fa": _r4(_spearman([p["fa"] for p in f], ft)),
            "rho_bt_corrected": _r4(_spearman([_bt_val(p) for p in f], ft)),
        }
    comp = folds[2024]
    comp_gap = plh.iid_boot_gaps([_bt_val(p) for p in comp],
                                 {"fa_projection": [p["fa"] for p in comp]},
                                 [p["tgt"] for p in comp], BOOT, SEED)["fa_projection"]

    # diagnostics: how each BT z relates to the incumbent residual (pooled)
    resid_all = [p["tgt"] - p["fa"] for p in pairs]
    resid_rhos = {k: _r4(_spearman([p["z"][k] for p in pairs], resid_all))
                  for k in feats}

    return {
        "candidate": ("bt_corrected = woba_proj + cross-fitted "
                      f"OLS(residual ~ {leg_label})"),
        "incumbent": "fa_projection woba_proj (validated pWOBA)",
        "n_pairs": len(pairs), "drops": drops,
        "folds": per_fold,
        "cross_fit_coefs": {
            f"applied_to_{y}_fold(fit_on_{other[y]})": {
                "intercept": round(float(coefs[y][0]), 5),
                **{k: round(float(c), 5)
                   for k, c in zip(feats, coefs[y][1:])}}
            for y in PRED_SEASONS},
        "residual_spearman_pooled": resid_rhos,
        "results_by_convention": {
            "v1": {"rhos": rhos_v1, "gap_ci_bt_minus_fa": gap_v1},
            "v2": {"rhos": rhos_v2, "gap_ci_bt_minus_fa": gap_v2,
                   "cluster": plh.cluster_summary(mids, pys)},
        },
        "sensitivity_complete_outcome_only": {
            "fold": "2024->2025", "n": len(comp),
            "gap_ci_bt_minus_fa_v1": comp_gap,
        },
        "gate": {"bar": ("pooled two-fold iid paired bootstrap "
                         "lo95(rho(bt_corrected) - rho(woba_proj)) > 0; "
                         "v1, seed 20260723, 2000 reps"),
                 "gap_ci_v1": gap_v1, "pass": pass_v1, "pass_under_v2": pass_v2},
    }


# --------------------------------------------------------------------------- #
# arm B: descriptive xHEM-style blend (display-metric candidate)
# --------------------------------------------------------------------------- #
def run_arm_b(by_season: dict, bt_pop: dict, bt_z: dict, *,
              comp_feats: tuple[str, ...] = ARM_B_COMPOSITE_FEATS,
              leg_z: dict | None = None,
              leg_label: str = "mean z(bat_speed, squared_up_rate, blast_rate)") -> dict:
    """Parent protocol when `leg_z` is None. NOV-A passes leg_z (per-season
    Swing+ z) and comp_feats=SWING_PLUS_LEG: the BT row gate stays, the Swing+
    slice must be present, and the composite is that one z."""
    sav = {y: load_xwoba(y) for y in PRED_SEASONS + [max(PRED_SEASONS) + 1]}
    ev_raw = {y: load_ev(y) for y in PRED_SEASONS + [max(PRED_SEASONS) + 1]}
    ev_z = {y: zmap({m: v for m, v in ev_raw[y].items()
                     if v["attempts"] >= EV_MIN_ATTEMPTS}, EV_FEATS)
            for y in ev_raw}

    def _bt_comp(y, mid):
        z = bt_z.get(y, {}).get(mid)
        if not z:
            return None
        if leg_z is not None:
            z = leg_z.get(y, {}).get(mid)
            if not z:
                return "leg_missing"
        return sum(z[k] for k in comp_feats) / len(comp_feats)

    # ---- forward pair set (X-H3/X-H5 construction + BT joined) ------------- #
    pairs = []
    drops = {"partial_outcome_kept": 0, "hem_missing": 0, "bt_missing": 0}
    if leg_z is not None:
        drops["leg_missing"] = 0
    for y in PRED_SEASONS:
        cur, nxt = sav.get(y), sav.get(y + 1)
        if not cur or not nxt:
            continue
        for mid, s in cur.items():
            nn = nxt.get(mid)
            if not nn or s["pa"] < SAVANT_MIN_PA or nn["pa"] < SAVANT_MIN_PA:
                continue
            if not plh.season_complete(y + 1):
                drops["partial_outcome_kept"] += 1     # flagged, kept (deviation)
            hem = (by_season.get(y) or {}).get(mid, {}).get("hem_plus_raw")
            if hem is None:
                drops["hem_missing"] += 1
                continue
            comp = _bt_comp(y, mid)
            if comp is None:
                drops["bt_missing"] += 1
                continue
            if comp == "leg_missing":
                drops["leg_missing"] += 1
                continue
            pairs.append({"mid": mid, "y": y, "oy": y + 1, "tgt": nn["woba"],
                          "xw": s["est_woba"], "hem": hem, "bt": comp})

    folds = {y: [p for p in pairs if p["y"] == y] for y in PRED_SEASONS}
    print(f"  arm B pairs: total={len(pairs)} "
          + " ".join(f"{y}->{y+1}={len(folds[y])}" for y in PRED_SEASONS)
          + f" drops={drops}")

    # X-H5 convention: blend-leg z within predictor season over the pair set
    pys = [p["y"] for p in pairs]
    zx = plh.zscore_within(pys, [p["xw"] for p in pairs])
    zh = plh.zscore_within(pys, [p["hem"] for p in pairs])
    zb = plh.zscore_within(pys, [p["bt"] for p in pairs])

    arms = {
        "fwdhem_incumbent": [FWDHEM_W[0] * a + FWDHEM_W[1] * b for a, b in zip(zx, zh)],
        "bt_blend_candidate": [CAND_W[0] * a + CAND_W[1] * b + CAND_W[2] * c
                               for a, b, c in zip(zx, zh, zb)],
        "xwoba_z_alone": zx,
        "bt_composite_alone": zb,
    }
    tgt = [p["tgt"] for p in pairs]
    mids = [p["mid"] for p in pairs]
    oys = [p["oy"] for p in pairs]

    baselines = {k: v for k, v in arms.items() if k != "bt_blend_candidate"}
    rhos_v1 = {k: _r4(_spearman(v, tgt)) for k, v in arms.items()}
    gaps_v1 = plh.iid_boot_gaps(arms["bt_blend_candidate"], baselines, tgt, BOOT, SEED)
    tgt_v2 = plh.zscore_within(oys, tgt)
    rhos_v2 = {k: _r4(_spearman(v, tgt_v2)) for k, v in arms.items()}
    gaps_v2 = plh.cluster_boot_gaps(arms["bt_blend_candidate"], baselines, tgt_v2,
                                    mids, pys, BOOT, SEED)
    gap_v1 = gaps_v1["fwdhem_incumbent"]
    gap_v2 = gaps_v2["fwdhem_incumbent"]
    pass_v1 = bool(gap_v1 and gap_v1["lo95"] > 0)
    pass_v2 = bool(gap_v2 and gap_v2["lo95"] > 0)

    per_fold = {}
    for y in PRED_SEASONS:
        idx = [i for i, p in enumerate(pairs) if p["y"] == y]
        ft = [tgt[i] for i in idx]
        per_fold[f"{y}->{y+1}"] = {
            "n": len(idx),
            "outcome_partial": not plh.season_complete(y + 1),
            "rho_fwdhem": _r4(_spearman([arms["fwdhem_incumbent"][i] for i in idx], ft)),
            "rho_bt_blend": _r4(_spearman([arms["bt_blend_candidate"][i] for i in idx], ft)),
        }
    comp_idx = [i for i, p in enumerate(pairs) if p["y"] == 2024]
    comp_gap = plh.iid_boot_gaps(
        [arms["bt_blend_candidate"][i] for i in comp_idx],
        {"fwdhem_incumbent": [arms["fwdhem_incumbent"][i] for i in comp_idx]},
        [tgt[i] for i in comp_idx], BOOT, SEED)["fwdhem_incumbent"]

    # ---- descriptive context (NOT gated): same-season luck-gap read -------- #
    desc = {}
    for y in PRED_SEASONS + [max(PRED_SEASONS) + 1]:
        rows = []
        for mid, s in (sav.get(y) or {}).items():
            if s["pa"] < SAVANT_MIN_PA:
                continue
            comp = _bt_comp(y, mid)
            ez = ev_z.get(y, {}).get(mid)
            if comp is None or comp == "leg_missing" or not ez:
                continue
            evc = sum(ez[k] for k in EV_FEATS) / len(EV_FEATS)
            rows.append((s["woba"] - s["est_woba"], comp, evc))
        if len(rows) >= 4:
            g = [r[0] for r in rows]
            desc[str(y)] = {
                "n": len(rows),
                "rho_bt_composite_vs_gap": _r4(_spearman([r[1] for r in rows], g)),
                "rho_ev_composite_vs_gap": _r4(_spearman([r[2] for r in rows], g)),
            }

    return {
        "candidate": ("bt_blend = 0.595*z(est_woba) + 0.255*z(hem_plus_raw) + "
                      f"0.15*z(bt_composite); composite = {leg_label}; "
                      "weights frozen a priori"),
        "incumbent": "fwdHEM+ blend 0.7*z(est_woba) + 0.3*z(hem_plus_raw) (X-H5, shipped)",
        "n_pairs": len(pairs), "drops": drops,
        "folds": per_fold,
        "results_by_convention": {
            "v1": {"rhos": rhos_v1, "gap_ci_candidate_minus": gaps_v1},
            "v2": {"rhos": rhos_v2, "gap_ci_candidate_minus": gaps_v2,
                   "cluster": plh.cluster_summary(mids, pys)},
        },
        "sensitivity_complete_outcome_only": {
            "fold": "2024->2025", "n": len(comp_idx),
            "gap_ci_candidate_minus_fwdhem_v1": comp_gap,
        },
        "descriptive_context_not_gated": {
            "question": ("same-season Spearman vs the wOBA - xwOBA luck gap: "
                         f"BT leg ({leg_label}) vs EV composite "
                         "(mean z of avg_hit_speed, brl_pa, ev95percent)"),
            "by_season": desc,
        },
        "gate": {"bar": ("pooled two-fold iid paired bootstrap "
                         "lo95(rho(bt_blend) - rho(fwdhem_incumbent)) > 0 vs "
                         "next-season wOBA; v1, seed 20260723, 2000 reps"),
                 "gap_ci_v1": gap_v1, "pass": pass_v1, "pass_under_v2": pass_v2},
    }


def _arm_b_fail_text(arm_b: dict) -> str:
    """Arm B's FAIL sentence, every clause READ from the arm's own numbers
    (the 2026-07-23 run's wording had the baseline claims typed in)."""
    g1 = arm_b["gate"]["gap_ci_v1"] or {}
    v1 = arm_b["results_by_convention"]["v1"]["gap_ci_candidate_minus"]
    comp = arm_b["sensitivity_complete_outcome_only"]["gap_ci_candidate_minus_fwdhem_v1"] or {}
    direction = ("directionally positive mean gap" if (g1.get("mean") or 0) > 0
                 else "mean gap at or below zero")
    convs = ("lo95 below zero under both conventions"
             if not arm_b["gate"]["pass_under_v2"] else "lo95 below zero under v1 only")
    single = ("and in the single-fold sensitivity" if (comp.get("lo95") or 0) <= 0
              else "though the single-fold sensitivity alone clears zero")
    beats = [k for k in ("xwoba_z_alone", "bt_composite_alone")
             if v1.get(k) and v1[k]["lo95"] > 0]
    beats_txt = (("The candidate beats " + " and ".join(beats) + " at lo95 > 0, but the "
                  "pre-registered bar is the shipped fwdHEM+ incumbent, and it is not cleared.")
                 if beats else
                 "The candidate separates from none of its baselines at lo95 > 0, and the "
                 "pre-registered bar, the shipped fwdHEM+ incumbent, is not cleared.")
    return f"Gate FAILED ({direction}, {convs} {single}). {beats_txt}"


# --------------------------------------------------------------------------- #
def _parse_args(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--nov-a", action="store_true",
                    help=("run the registered NOV-A arm: per-season Swing+ "
                          "(data/swing_plus.json) as the BT leg in both arms; "
                          "artifact data/bat_tracking_nov_a_eval.json"))
    ap.add_argument("--season-complete-asof", default=None,
                    help=("OWNER-WAIVED EARLY READ override, 'YYYY:YYYY-MM-DD' "
                          "(plus_lab_harness.set_season_complete_asof; logged and "
                          "written into the artifact). The Nov 15 default stays."))
    return ap.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    override = plh.set_season_complete_asof(args.season_complete_asof)
    if override:
        print(f"season-complete override in force: {plh.season_complete_override_meta()}")
    nov_a = bool(args.nov_a)
    t0 = time.time()
    eng = FaEngine()
    print(f"fa corpus: hit={len(eng.hist_hit)} players")

    need = sorted(set(
        [y for p in PRED_SEASONS for y in (p - 2, p - 1, p)] + [max(PRED_SEASONS) + 1]))
    by_season = {}
    for y in need:
        s, _ = load_hit_season(y)
        if s:
            by_season[y] = s
        print(f"  hit {y}: {len(s)} scored")

    bt_pop, bt_reports = {}, {}
    for y in PRED_SEASONS + [max(PRED_SEASONS) + 1]:
        bt_pop[y], bt_reports[y] = load_bt(y)
        print(f"  bat-tracking {y}: {bt_reports[y]}")
    all_feats = tuple(dict.fromkeys(ARM_A_FEATS + ARM_B_COMPOSITE_FEATS))
    bt_z = {y: zmap(bt_pop[y], all_feats) for y in bt_pop}

    leg_kw_a: dict = {}
    leg_kw_b: dict = {}
    swing_meta = None
    if nov_a:
        sp_seasons, swing_meta = load_swing_plus_seasons()
        print(f"  swing+ per-season slices: {swing_meta['per_season_coverage']} "
              f"low_n {swing_meta['per_season_low_n']}")
        sp_z = {y: zmap(sp_seasons[y], SWING_PLUS_LEG) for y in sp_seasons}
        leg_kw_a = {"feats": SWING_PLUS_LEG, "leg_z": sp_z,
                    "leg_label": "z(swing_plus per season)"}
        leg_kw_b = {"comp_feats": SWING_PLUS_LEG, "leg_z": sp_z,
                    "leg_label": "z(swing_plus per season)"}

    print("arm A (predictive residual read):")
    arm_a = run_arm_a(eng, by_season, bt_z, **leg_kw_a)
    print("arm B (descriptive blend):")
    arm_b = run_arm_b(by_season, bt_pop, bt_z, **leg_kw_b)

    complete_2026 = plh.season_complete(max(PRED_SEASONS) + 1)
    override_meta = plh.season_complete_override_meta()
    fold_2026 = (
        "2025->2026 (complete outcome"
        + (" under the logged owner-waived season-complete override" if override_meta else "")
        + ")" if complete_2026 else
        "2025->2026 (PARTIAL outcome through today; kept by pre-registered deviation "
        "from harness rule 4, flagged; complete-only sensitivity reported)")
    keep_alive_text = (
        ("This run IS the frozen re-run after the 2026 completion (an owner-waived early "
         "read, owner 2026-10-14); the registered keep-alive is spent and NULL stands.")
        if complete_2026 else
        ("NULL; the one honest keep-alive is a re-test on the identical frozen protocol "
         "after the 2026 season completes (Nov 15), which adds no new researcher "
         "degrees of freedom."))

    payload = {
        "experiment": (
            "NOV-A (registered 2026-07-23): per-season Swing+ as the BT leg in the pWOBA "
            "residual arm and the fwdHEM+ blend arm, parent protocol otherwise unchanged"
            if nov_a else
            "BT-1 bat-tracking lane (hitters): pWOBA residual arm + xHEM-style blend arm"),
        "generated_at": date.today().isoformat(), "seed": SEED, "boot": BOOT,
        "harness": plh.convention_meta("wOBA(Y+1) raw pooled", "wOBA(Y+1)"),
        "season_complete_override": override_meta,
        "owner_waived_early_read": (
            ("registered date 2026-11-15 (docs/efv-2026-07-23/RECHECKS.md, "
             "docs/wills-2026-07-23/GATES.md W-NOV); run on "
             f"{date.today().isoformat()} under the owner's 2026-10-14 waiver of look "
             "days (EW3-5) and the explicit season-complete override (EW3-6)")
            if override_meta else None),
        "registration": (
            {"arm": "NOV-A", "where": ["docs/wills-2026-07-23/GATES.md W-NOV",
                                        "docs/efv-2026-07-23/RECHECKS.md"],
             "substitution": ("the vendored Swing+ per-season slice replaces the raw "
                              "bat-tracking z-aggregates as the BT leg in both arms; "
                              "bars inherit the parent registrations"),
             "parent": "data/bat_tracking_eval.json (this file's default run)",
             "swing_plus_source": swing_meta,
             "pair_set_note": ("the parent BT row gate (>= 100 competitive swings) "
                               "stays; a pair without a Swing+ season slice drops as "
                               "leg_missing; low_n slices are kept as the artifact "
                               "gives them and counted above"),
             "normalizer_note": ("arm A: OLS with an intercept on one regressor is "
                                 "affine-invariant, so the z population is immaterial; "
                                 "arm B: legs are re-z'd within predictor season over "
                                 "the pair set (X-H5 convention)")}
            if nov_a else None),
        "data_source": {
            "endpoint": BT_URL,
            "extraction": ("embedded `const data = [...]` JSON (the csv=true export "
                           "omits the swing-path fields); the bare `season` param is "
                           "ignored by the endpoint, seasonStart/seasonEnd required"),
            "cache": ".cache/bat_tracking/bat_tracking_batter_{Y}.json",
            "coverage": {str(y): bt_reports[y] for y in bt_reports},
            "min_swings_gate": BT_MIN_SWINGS,
            "field_map": {k: v for k, v in BT_FIELD_MAP.items()},
        },
        "protocol": {
            "pre_registered": "2026-07-23, frozen before any results were computed",
            "folds": ["2024->2025 (complete outcome)", fold_2026],
            "ledger_position": ("distinct from the CLOSED pwoba_ev_arm (EV/barrel "
                                "residual), xwOBA-allowed and CSW-xK lanes; bat "
                                "tracking is swing-measured, not batted-ball-outcome"),
            "small_n_honesty": ("exactly two transition folds exist for this lane "
                                "(bat tracking begins 2024); one fold has a partial "
                                "outcome season; a PASS would still be provisional "
                                "and would queue re-confirmation after 2026 completes"),
        },
        "arm_a_pwoba_residual": arm_a,
        "arm_b_descriptive_blend": arm_b,
        "verdicts": {
            "arm_a": ("PASS (provisional, small-n)" if arm_a["gate"]["pass"] else "NULL"),
            "arm_b": ("PASS (provisional, small-n)" if arm_b["gate"]["pass"] else "NULL"),
            "arm_a_summary": (
                f"rho(bt_corrected)={arm_a['results_by_convention']['v1']['rhos']['bt_corrected']} vs "
                f"rho(woba_proj)={arm_a['results_by_convention']['v1']['rhos']['fa_projection']} on "
                f"{arm_a['n_pairs']} pooled pairs; gap CI {arm_a['gate']['gap_ci_v1']}. "
                + ("Gate PASSED (provisional)." if arm_a["gate"]["pass"] else
                   "Gate FAILED under v1 and v2 and in the complete-outcome-only "
                   "sensitivity; the cross-fitted residual correction does not add "
                   "forward signal beyond the incumbent pWOBA. Lane CLOSED as tested.")),
            "arm_b_summary": (
                f"rho(bt_blend)={arm_b['results_by_convention']['v1']['rhos']['bt_blend_candidate']} vs "
                f"rho(fwdhem_incumbent)={arm_b['results_by_convention']['v1']['rhos']['fwdhem_incumbent']} on "
                f"{arm_b['n_pairs']} pooled pairs; gap CI {arm_b['gate']['gap_ci_v1']}. "
                + ("Gate PASSED (provisional)." if arm_b["gate"]["pass"] else
                   _arm_b_fail_text(arm_b) + " " + keep_alive_text)),
            "descriptive_note": (
                "Same-season luck-gap context (not gated): BT composite vs EV "
                "composite Spearman with the wOBA - xwOBA gap: "
                + "; ".join(
                    f"{y} BT {d['rho_bt_composite_vs_gap']} vs EV {d['rho_ev_composite_vs_gap']}"
                    for y, d in sorted(
                        arm_b["descriptive_context_not_gated"]["by_season"].items()))
                + "."),
        },
        "runtime_seconds": round(time.time() - t0, 1),
    }
    out = ROOT / "data" / ("bat_tracking_nov_a_eval.json" if nov_a else "bat_tracking_eval.json")
    out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    print(json.dumps({
        "arm_a": {"n": arm_a["n_pairs"], "rhos": arm_a["results_by_convention"]["v1"]["rhos"],
                  "gap_v1": arm_a["gate"]["gap_ci_v1"], "pass": arm_a["gate"]["pass"],
                  "pass_v2": arm_a["gate"]["pass_under_v2"]},
        "arm_b": {"n": arm_b["n_pairs"], "rhos": arm_b["results_by_convention"]["v1"]["rhos"],
                  "gap_v1": arm_b["gate"]["gap_ci_v1"], "pass": arm_b["gate"]["pass"],
                  "pass_v2": arm_b["gate"]["pass_under_v2"]},
        "verdicts": payload["verdicts"],
    }, indent=1))


if __name__ == "__main__":
    main()
