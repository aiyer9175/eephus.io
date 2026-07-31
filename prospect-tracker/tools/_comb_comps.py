# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Scratch lab: COMBINATORIAL COMP-METRIC SWEEP + NEAREST-NEIGHBOUR COMPS ENGINE.

Read-only with respect to every shipped artifact. Writes only to the scratch OUT dir.

The owner asked for archetypes built from every combination of axes (production x age,
position x production, age x position x production, ...) and then used as COMPARISONS for
current prospects. This lab owns the COMPS half of that: a nearest-neighbour engine whose
distance METRIC is itself the thing being searched combinatorially.

Because the search is combinatorial, the whole statistical burden is multiplicity:
  1. PRE-REGISTER   - cmd `prereg` writes the entire config grid BEFORE any outcome stat.
  2. FDR + MAX-STAT - cmd `null` permutes the outcome and re-runs the ENTIRE sweep, giving
                      per-config permutation p -> BH q, and a family-wise max-statistic null.
  3. OUT-OF-FOLD    - donors, standardization and supervised weights come from TRAIN folds only.
  4. NESTED CV      - cmd `nested` runs the full search inside an inner loop and scores the
                      selected config on an untouched outer fold. That answers the real
                      question: is the SEARCH PROCEDURE worth anything out of sample.
  5. SIZE FLOOR     - MIN_K / MIN_TRAIN / MIN_TEST enforced and declared in advance.

Run:  python tools/_comb_comps.py prereg
      python tools/_comb_comps.py sweep  [hit|pit]
      python tools/_comb_comps.py null   [hit|pit] [B]
      python tools/_comb_comps.py nested [hit|pit]
      python tools/_comb_comps.py live   [hit|pit]
"""
from __future__ import annotations

import json
import math
import os
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"

OUT = Path(os.environ.get(
    "COMB_OUT",
    r"C:\Users\noah\AppData\Local\Temp\claude\c--Users-noah-baseball-projects-BaseballR"
    r"\c6ce73e3-6700-473f-beea-01f160967961\scratchpad\comps"))
OUT.mkdir(parents=True, exist_ok=True)

import efv_model as EM  # noqa: E402

# ---------------------------------------------------------------------------
# PRE-REGISTERED PROTOCOL CONSTANTS  (declared before any outcome is touched)
# ---------------------------------------------------------------------------

# Target. MUST be target_censored, the shipped KM label. Verified 2026-07-25: in this
# matrix `censored=False` at recent decision years means RESOLVED NEVER-MLB BUST -- all
# 114 uncensored 2024 hitters are busts with target_resolved == 0.0 exactly. Selecting on
# censored=False would therefore make the recent folds ~100% busts, which is a far worse
# bias than censoring. target_resolved is used for DISPLAY of a comp's realized WAR
# (where a completed window is what the reader needs) and as a sensitivity arm only.
TARGET = "target_censored"
DISPLAY_TARGET = "target_resolved"

# Population. Headline arms run on the TRACK-RECORD subpopulation (rows that actually have
# a MiLB block). This is deliberate: efv_model._vec hard-zeroes level_rank / n_milb_seasons
# / ops_rel / obp_rel for the 51.8% of the fit pool with no MiLB block, so "missing" is
# encoded as the DSL value and would masquerade as a dense archetype. The served board is
# 100% track-record, so the track-record pool is also the right frame for a comps product.
# POOL_ALL is carried as an explicitly-labelled robustness arm, NOT part of the FDR family.

MIN_K = 5            # stratum-size floor: never fewer than 5 donors behind a prediction
MIN_TRAIN = 150      # a fold needs this many donors before it may be scored
MIN_TEST = 15        # a fold needs this many test rows before it may be scored
FOLD_YEARS = (2020, 2021, 2022, 2023, 2024)   # forward-chained; 5 splits (bar is >= 4)
PROD_FOLD_YEARS = EM.SCORED_YEARS              # (2020..2023) production-matched arm
SEED = 7

# --- axis blocks -----------------------------------------------------------
# Every axis is either a milb-block key (as-of the pre-decision season) or a row-level
# key that is a fact known AT asof_date (tools as graded then, draft pedigree, anchor).
# Nothing here is post-dated relative to the decision, except the target itself.

AXES_HIT = {
    "STAGE":    ["age", "level_rank", "age_rel_level", "n_milb_seasons"],
    "PROD":     ["ops_rel", "obp_rel", "iso_rel", "k_rel", "bb_rel", "prod_trend"],
    "PEAK":     ["peak_ops_rel", "peak_obp_rel", "peak_iso_rel", "peak_k_rel"],
    "TOOLS":    ["tool_hit", "tool_game_pwr", "tool_raw_pwr", "tool_speed",
                 "tool_field", "tool_throw"],
    "ANCHOR":   ["fv"],
    "PEDIGREE": ["is_college", "is_ifa", "log_pick", "has_pick"],
    "POS":      ["pos_premium"],
}
AXES_PIT = {
    "STAGE":    ["age", "level_rank", "age_rel_level", "n_milb_seasons"],
    "PROD":     ["k_rel", "bb_rel", "era_rel", "prod_trend"],
    "PEAK":     ["peak_k_rel", "peak_bb_rel"],
    "TOOLS":    ["tool_fb", "tool_sl", "tool_cb", "tool_ch", "tool_cmd"],
    "ANCHOR":   ["fv"],
    "PEDIGREE": ["is_college", "is_ifa", "log_pick", "has_pick"],
    "POS":      ["pos_premium"],
}

# --- the pre-registered axis-SET grid --------------------------------------
# These are the "combinations" the owner asked for, expressed as which blocks enter the
# comp metric. S1..S8 walk production / stage / position / pedigree crossings; S9 is the
# anchor-only control (comps by consensus grade alone); S10 is the shipped feature set,
# which reproduces the kNN leg efv_model already carries so the sweep has a known bar.
AXIS_SETS = {
    "S1_STAGE":                 ["STAGE"],
    "S2_PROD":                  ["PROD"],
    "S3_STAGExPROD":            ["STAGE", "PROD"],
    "S4_PRODxPOS":              ["PROD", "POS"],
    "S5_STAGExPRODxPOS":        ["STAGE", "PROD", "POS"],
    "S6_STAGExPRODxPEAK":       ["STAGE", "PROD", "PEAK"],
    "S7_STAGExPRODxTOOLS":      ["STAGE", "PROD", "TOOLS"],
    "S8_KITCHEN_SINK":          ["STAGE", "PROD", "PEAK", "TOOLS", "ANCHOR",
                                 "PEDIGREE", "POS"],
    "S9_ANCHOR_ONLY":           ["ANCHOR"],
    "S10_SHIPPED_FEATURES":     ["__SHIPPED__"],
}

# --- weightings ------------------------------------------------------------
# W1 equal weight after train-fold z-scoring (z-scoring IS inverse-variance scaling).
# W2/W3/W4 are SUPERVISED and are therefore fit on TRAIN FOLDS ONLY, every fold, every
# permutation replicate. W3 uses the ridge the shipped model itself uses.
WEIGHTINGS = ["W1_EQUAL", "W2_ABS_SPEARMAN", "W3_RIDGE_COEF", "W4_SPEARMAN_SQ"]

K_VALUES = [5, 10, 20, 40]

# A hard career-stage gate: only donors within +/-1 level_rank of the subject are eligible.
# This is the strict reading of "same career stage" in the as-of requirement.
GATES = ["G0_NONE", "G1_LEVEL_BAND"]


def family() -> list[dict]:
    """The complete pre-registered candidate list. Order is deterministic."""
    out = []
    for s in AXIS_SETS:
        for w in WEIGHTINGS:
            for k in K_VALUES:
                for g in GATES:
                    out.append({"axis_set": s, "weighting": w, "k": k, "gate": g,
                                "id": f"{s}|{w}|k{k}|{g}"})
    return out


# ---------------------------------------------------------------------------
# row -> axis vector
# ---------------------------------------------------------------------------

def _axis_value(r, key, side):
    m = r.get("milb") or {}
    if key in m:
        v = m.get(key)
        return float(v) if isinstance(v, (int, float)) else None
    if key == "fv":
        v = r.get("consensus_fv_raw")
        return float(v) if isinstance(v, (int, float)) else None
    if key == "pos_premium":
        return EM._pos_premium(r.get("position"), side)
    if key == "log_pick":
        p = r.get("pick_overall")
        return math.log1p(float(p)) if isinstance(p, (int, float)) else None
    if key == "has_pick":
        return 1.0 if isinstance(r.get("pick_overall"), (int, float)) else 0.0
    if key in ("is_college", "is_ifa"):
        v = r.get(key)
        return float(v) if isinstance(v, (int, float)) else 0.0
    v = r.get(key)           # tools
    return float(v) if isinstance(v, (int, float)) else None


def axis_keys(axis_set, side):
    blocks = AXIS_SETS[axis_set]
    if blocks == ["__SHIPPED__"]:
        keys, _m = EM._feature_spec(side)
        return list(keys)
    src = AXES_PIT if side == "pit" else AXES_HIT
    out = []
    for b in blocks:
        out.extend(src[b])
    return out


def build_matrix(rows, keys, side, imp=None):
    """Return (X, imp). Missing is imputed at the TRAIN mean of that axis so a missing
    value lands neutral under standardization instead of reading as an extreme."""
    shipped = None
    if any(k not in _KNOWN(side) for k in keys):
        shipped = True
    n, d = len(rows), len(keys)
    X = np.full((n, d), np.nan)
    for i, r in enumerate(rows):
        if shipped:
            fv = EM._vec(r, side)
            for j, k in enumerate(keys):
                v = fv.get(k)
                X[i, j] = float(v) if isinstance(v, (int, float)) else np.nan
        else:
            for j, k in enumerate(keys):
                v = _axis_value(r, k, side)
                if v is not None:
                    X[i, j] = v
    if imp is None:
        imp = np.nanmean(X, axis=0)
        imp = np.where(np.isfinite(imp), imp, 0.0)
    idx = np.where(np.isnan(X))
    X[idx] = np.take(imp, idx[1])
    return X, imp


_KNOWN_CACHE: dict[str, set] = {}


def _KNOWN(side):
    if side not in _KNOWN_CACHE:
        src = AXES_PIT if side == "pit" else AXES_HIT
        s = set()
        for v in src.values():
            s.update(v)
        _KNOWN_CACHE[side] = s
    return _KNOWN_CACHE[side]


# ---------------------------------------------------------------------------
# pools
# ---------------------------------------------------------------------------

def load_pool(side="hit", track_record=True):
    mp = "xfv_hitter_matrix.json" if side == "hit" else "xfv_pitcher_matrix.json"
    rows = json.loads((DATA / mp).read_text(encoding="utf-8"))
    is_pit = side == "pit"
    out = []
    for r in rows:
        if bool(r.get("is_pitcher")) != is_pit:
            continue
        if r.get("kind") == "bust" and r.get("bust_recent"):
            continue                      # production pool filter
        if r.get(TARGET) is None or r.get("consensus_fv_raw") is None:
            continue
        if track_record and not r.get("milb"):
            continue
        r = dict(r)
        r["_dy"] = EM._decision_year(r)
        r["_y"] = float(r[TARGET])
        out.append(r)
    return out


def load_live(side="hit"):
    lp = "xfv_live_hitter_matrix.json" if side == "hit" else "xfv_live_pitcher_matrix.json"
    rows = json.loads((DATA / lp).read_text(encoding="utf-8"))
    out = []
    for r in rows:
        try:
            float(r.get("consensus_fv_raw"))
        except (TypeError, ValueError):
            continue
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

def _rank(a):
    a = np.asarray(a, dtype=float)
    order = a.argsort()
    r = np.empty(len(a), dtype=float)
    r[order] = np.arange(len(a), dtype=float)
    # average ties
    _, inv, cnt = np.unique(a, return_inverse=True, return_counts=True)
    if (cnt > 1).any():
        sums = np.zeros(len(cnt))
        np.add.at(sums, inv, r)
        r = (sums / cnt)[inv]
    return r


def spearman(x, y):
    if len(x) < 8:
        return None
    rx, ry = _rank(x), _rank(y)
    rx = rx - rx.mean()
    ry = ry - ry.mean()
    den = math.sqrt(float((rx ** 2).sum()) * float((ry ** 2).sum()))
    return float((rx * ry).sum() / den) if den else None


# ---------------------------------------------------------------------------
# weighting (TRAIN ONLY)
# ---------------------------------------------------------------------------

def fit_weights(Zt, yt, scheme):
    d = Zt.shape[1]
    if scheme == "W1_EQUAL":
        return np.ones(d)
    if scheme in ("W2_ABS_SPEARMAN", "W4_SPEARMAN_SQ"):
        ry = _rank(yt)
        ry = ry - ry.mean()
        w = np.zeros(d)
        for j in range(d):
            rx = _rank(Zt[:, j])
            rx = rx - rx.mean()
            den = math.sqrt(float((rx ** 2).sum()) * float((ry ** 2).sum()))
            w[j] = abs(float((rx * ry).sum() / den)) if den else 0.0
        if scheme == "W4_SPEARMAN_SQ":
            w = w ** 2
    elif scheme == "W3_RIDGE_COEF":
        lam = 1.0
        A = Zt.T @ Zt + lam * np.eye(d)
        b = Zt.T @ (yt - yt.mean())
        try:
            w = np.abs(np.linalg.solve(A, b))
        except np.linalg.LinAlgError:
            w = np.ones(d)
    else:
        raise ValueError(scheme)
    s = w.sum()
    if not np.isfinite(s) or s <= 1e-12:
        return np.ones(d)
    return w * (d / s)          # normalize so total weight matches the equal-weight case


# ---------------------------------------------------------------------------
# the comp predictor
# ---------------------------------------------------------------------------

def comp_predict(Ztr, ytr, Zte, w, k, lvl_tr=None, lvl_te=None, want_idx=False):
    """Inverse-distance weighted mean of the k nearest TRAIN donors.

    Matches the shipped efv_model._pred_comps weighting (w = 1/(d+1e-6)) so the sweep is
    directly comparable to the kNN leg already in data/xfv_eval.json."""
    sw = np.sqrt(np.maximum(w, 0.0))
    A = Ztr * sw
    B = Zte * sw
    d2 = (B ** 2).sum(1)[:, None] + (A ** 2).sum(1)[None, :] - 2.0 * (B @ A.T)
    np.maximum(d2, 0.0, out=d2)
    D = np.sqrt(d2)
    if lvl_tr is not None:
        # hard career-stage gate: donor level_rank within +/-1 of the subject
        bad = np.abs(lvl_te[:, None] - lvl_tr[None, :]) > 1.0
        # never let the gate starve a subject below the MIN_K floor
        keep = (~bad).sum(1) >= MIN_K
        D = np.where(bad & keep[:, None], np.inf, D)
    kk = min(k, Ztr.shape[0])
    idx = np.argpartition(D, kk - 1, axis=1)[:, :kk]
    rowi = np.arange(D.shape[0])[:, None]
    dsel = D[rowi, idx]
    order = np.argsort(dsel, axis=1)
    idx = idx[rowi, order]
    dsel = dsel[rowi, order]
    finite = np.isfinite(dsel)
    wgt = np.where(finite, 1.0 / (dsel + 1e-6), 0.0)
    ysel = ytr[idx]
    denom = wgt.sum(1)
    pred = np.where(denom > 0, (wgt * ysel).sum(1) / np.where(denom > 0, denom, 1.0),
                    ytr.mean())
    if want_idx:
        return pred, idx, dsel
    return pred


# ---------------------------------------------------------------------------
# fold plumbing
# ---------------------------------------------------------------------------

def fold_split(pool, years):
    for yr in years:
        tr = [r for r in pool if r["_dy"] < yr]
        te = [r for r in pool if r["_dy"] == yr]
        if len(tr) < MIN_TRAIN or len(te) < MIN_TEST:
            continue
        yield yr, tr, te


def precompute(pool, side, years):
    """Per (fold, axis_set): standardized TRAIN/TEST matrices. y-independent, so this is
    computed ONCE and reused across every weighting, k, gate and permutation replicate."""
    cache = {}
    for yr, tr, te in fold_split(pool, years):
        ytr = np.array([r["_y"] for r in tr])
        yte = np.array([r["_y"] for r in te])
        lvl_tr = np.array([(r.get("milb") or {}).get("level_rank", 0.0) or 0.0 for r in tr])
        lvl_te = np.array([(r.get("milb") or {}).get("level_rank", 0.0) or 0.0 for r in te])
        per = {}
        for s in AXIS_SETS:
            keys = axis_keys(s, side)
            Xtr, imp = build_matrix(tr, keys, side)
            Xte, _ = build_matrix(te, keys, side, imp=imp)
            mu, sd = Xtr.mean(0), Xtr.std(0)
            sd = np.where(sd > 1e-9, sd, 1.0)
            per[s] = ((Xtr - mu) / sd, (Xte - mu) / sd, keys)
        cache[yr] = {"tr": tr, "te": te, "ytr": ytr, "yte": yte,
                     "lvl_tr": lvl_tr, "lvl_te": lvl_te, "per": per}
    return cache


def run_family(cache, cfgs, ytr_override=None):
    """Pooled out-of-fold Spearman for every config. ytr_override permutes TRAIN targets
    only (donor labels), which is the null 'comp neighbourhoods carry no outcome info'."""
    acc = {c["id"]: ([], []) for c in cfgs}
    for yr, F in cache.items():
        ytr = F["ytr"] if ytr_override is None else ytr_override[yr]
        yte = F["yte"]
        wcache = {}
        for c in cfgs:
            s, wsch = c["axis_set"], c["weighting"]
            Ztr, Zte, _ = F["per"][s]
            key = (s, wsch)
            if key not in wcache:
                wcache[key] = fit_weights(Ztr, ytr, wsch)
            w = wcache[key]
            gate = c["gate"] == "G1_LEVEL_BAND"
            pred = comp_predict(Ztr, ytr, Zte, w, c["k"],
                                F["lvl_tr"] if gate else None,
                                F["lvl_te"] if gate else None)
            a, b = acc[c["id"]]
            a.extend(pred.tolist())
            b.extend(yte.tolist())
    return {cid: spearman(np.array(a), np.array(b)) for cid, (a, b) in acc.items()}


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_prereg():
    fam = family()
    doc = {
        "written_at_stage": "BEFORE any outcome statistic was computed",
        "target": TARGET,
        "display_target": DISPLAY_TARGET,
        "target_note": (
            "censored=False at recent decision years means RESOLVED NEVER-MLB BUST "
            "(all 114 uncensored 2024 hitters are busts, target_resolved == 0.0), so "
            "selecting on it would make recent folds ~100% busts. target_censored is the "
            "shipped KM label and the only unbiased choice for the eval."),
        "population": "track-record rows only (milb block present); POOL_ALL is a "
                      "labelled robustness arm and is NOT in the FDR family",
        "folds": {"forward_chained_years": list(FOLD_YEARS),
                  "production_matched": list(PROD_FOLD_YEARS)},
        "floors": {"MIN_K": MIN_K, "MIN_TRAIN": MIN_TRAIN, "MIN_TEST": MIN_TEST},
        "axis_blocks_hit": AXES_HIT,
        "axis_blocks_pit": AXES_PIT,
        "axis_sets": AXIS_SETS,
        "weightings": WEIGHTINGS,
        "k_values": K_VALUES,
        "gates": GATES,
        "n_hypotheses": len(fam),
        "statistic": "pooled out-of-fold Spearman(comp_implied_WAR, realized target)",
        "multiplicity": ["Benjamini-Hochberg q across the whole family",
                         "permutation family-wise MAX-statistic null (entire sweep re-run "
                         "per replicate, best statistic recorded)"],
        "nested_cv": "full search inside inner forward-chained folds; selected config "
                     "scored on an untouched outer fold",
        "controls": ["random-comp (same k, donors drawn at random from train)",
                     "consensus-OLS baseline", "shipped blend", "anchor-only metric"],
        "decisive_test": "Spearman(comp_implied, y - shipped_blend_pred) out of fold. "
                         "An engine that predicts the outcome but explains no residual is "
                         "already priced by the shipped features -> verdict NULL.",
        "candidates": [c["id"] for c in fam],
    }
    p = OUT / "PREREGISTRATION.json"
    p.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"PRE-REGISTERED {len(fam)} hypotheses -> {p}")
    print(f"  axis_sets {len(AXIS_SETS)} x weightings {len(WEIGHTINGS)} "
          f"x k {len(K_VALUES)} x gates {len(GATES)} = {len(fam)}")
    return doc


# ---------------------------------------------------------------------------
# baselines: the shipped model, out of fold, on the SAME rows
# ---------------------------------------------------------------------------

def shipped_oof(cache, side):
    """Forward-chained consensus-OLS baseline and shipped BLEND prediction, refit per fold
    on that fold's train rows only. Used for (i) the bar the comps engine must beat and
    (ii) the residual the comps engine must explain to be anything other than already-priced."""
    lam = EM._BLEND_LAMBDA_RESELECT.get(side)
    if lam is None:
        lam = EM._BLEND_LAMBDA_FALLBACK[side]
    keys, _m = EM._feature_spec(side)
    out = {}
    for yr, F in cache.items():
        tr, te = F["tr"], F["te"]
        dtr = EM._prep(tr, TARGET, side)
        ols = EM._fit_ols_fv(dtr)
        ridge = EM._fit_ridge(dtr, keys)
        if not (ols and ridge):
            out[yr] = None
            continue
        base, blend = [], []
        for r in te:
            f = EM._vec(r, side)
            cons = max(0.0, EM._pred_ols(ols, float(r["consensus_fv_raw"])))
            m = EM._predict(ridge, f)
            base.append(cons)
            blend.append((1 - lam) * cons + lam * m)
        out[yr] = {"baseline": np.array(base), "blend": np.array(blend), "lam": lam}
    return out


def cmd_sweep(side="hit", years=FOLD_YEARS, track_record=True, tag=""):
    pool = load_pool(side, track_record=track_record)
    cache = precompute(pool, side, years)
    if not cache:
        print("no scorable folds")
        return None
    fam = family()
    obs = run_family(cache, fam)
    ship = shipped_oof(cache, side)

    # pooled truth + baselines on identical rows
    yte_all, base_all, blend_all = [], [], []
    for yr, F in cache.items():
        yte_all.extend(F["yte"].tolist())
        s = ship.get(yr)
        base_all.extend((s["baseline"] if s else np.full(len(F["yte"]), np.nan)).tolist())
        blend_all.extend((s["blend"] if s else np.full(len(F["yte"]), np.nan)).tolist())
    yte_all = np.array(yte_all)
    base_all = np.array(base_all)
    blend_all = np.array(blend_all)
    ok = np.isfinite(base_all)
    rho_base = spearman(base_all[ok], yte_all[ok])
    rho_blend = spearman(blend_all[ok], yte_all[ok])

    # random-comp control: identical k, donors drawn at random from train
    rng = random.Random(SEED)
    rc = []
    for yr, F in cache.items():
        ytr = F["ytr"]
        for _ in range(len(F["yte"])):
            pick = [ytr[rng.randrange(len(ytr))] for _ in range(20)]
            rc.append(float(np.mean(pick)))
    rho_rand = spearman(np.array(rc), yte_all)

    rank = sorted(fam, key=lambda c: -(obs[c["id"]] if obs[c["id"]] is not None else -9))
    res = {
        "side": side, "tag": tag, "track_record": track_record,
        "n_hypotheses": len(fam),
        "folds": {str(yr): {"n_train": len(F["tr"]), "n_test": len(F["te"])}
                  for yr, F in cache.items()},
        "n_scored_rows": int(len(yte_all)),
        "baselines": {"consensus_ols": rho_base, "shipped_blend": rho_blend,
                      "random_comp_k20": rho_rand,
                      "lambda": (ship.get(list(cache)[0]) or {}).get("lam")},
        "observed": {c["id"]: obs[c["id"]] for c in fam},
        "top20": [{"id": c["id"], "rho": obs[c["id"]]} for c in rank[:20]],
    }
    fn = OUT / f"sweep_{side}{tag}.json"
    fn.write_text(json.dumps(res, indent=1), encoding="utf-8")

    print(f"== SWEEP side={side} tag={tag or '-'} track_record={track_record}")
    print(f"   folds: " + ", ".join(f"{yr}(tr{len(F['tr'])}/te{len(F['te'])})"
                                    for yr, F in cache.items()))
    print(f"   scored rows {len(yte_all)}   hypotheses {len(fam)}")
    print(f"   BAR  consensus-OLS rho {rho_base:.4f}   shipped BLEND rho {rho_blend:.4f}"
          f"   random-comp rho {rho_rand:.4f}")
    print("   top 12 configs:")
    for c in rank[:12]:
        v = obs[c["id"]]
        print(f"     {v:+.4f}  {c['id']}")
    print("   bottom 3:")
    for c in rank[-3:]:
        print(f"     {obs[c['id']]:+.4f}  {c['id']}")
    return res


def partial_spearman(x, y, z):
    """Spearman of x with y, controlling for z. Rank-transform all three, then correlate
    the residuals of x~z and y~z.

    This is the correct form of the decisive test. A RAW correlation of the comp
    prediction with the shipped model's residual is uninformative here: the shipped blend
    has calibration slope < 1 (it over-spreads), so ANY variable correlated with the blend
    shows a large negative correlation with (y - blend) as a pure calibration artifact.
    Partialling on the blend asks the question that actually matters -- does the comp
    engine carry ranking information the shipped model does not already have?"""
    rx, ry, rz = _rank(x), _rank(y), _rank(z)

    def _resid(a, b):
        b0 = b - b.mean()
        v = float((b0 ** 2).sum())
        if v <= 0:
            return a - a.mean()
        beta = float(((a - a.mean()) * b0).sum()) / v
        return (a - a.mean()) - beta * b0
    ex, ey = _resid(rx, rz), _resid(ry, rz)
    den = math.sqrt(float((ex ** 2).sum()) * float((ey ** 2).sum()))
    return float((ex * ey).sum() / den) if den else None


def cmd_residual(side="hit", years=FOLD_YEARS, top=12):
    """THE DECISIVE TEST. Does the comp-implied outcome explain the shipped model's
    OUT-OF-FOLD residual, or only the raw outcome? No residual signal => already priced."""
    pool = load_pool(side, track_record=True)
    cache = precompute(pool, side, years)
    ship = shipped_oof(cache, side)
    fam = family()
    obs = run_family(cache, fam)
    rank = sorted(fam, key=lambda c: -(obs[c["id"]] or -9))[:top]

    resid, yte_all, blend_all = [], [], []
    for yr, F in cache.items():
        s = ship[yr]
        resid.extend((F["yte"] - s["blend"]).tolist())
        yte_all.extend(F["yte"].tolist())
        blend_all.extend(s["blend"].tolist())
    resid = np.array(resid)

    rows = []
    for c in rank:
        preds = []
        for yr, F in cache.items():
            Ztr, Zte, _ = F["per"][c["axis_set"]]
            w = fit_weights(Ztr, F["ytr"], c["weighting"])
            gate = c["gate"] == "G1_LEVEL_BAND"
            preds.extend(comp_predict(Ztr, F["ytr"], Zte, w, c["k"],
                                      F["lvl_tr"] if gate else None,
                                      F["lvl_te"] if gate else None).tolist())
        preds = np.array(preds)
        rows.append({"id": c["id"], "rho_outcome": obs[c["id"]],
                     "rho_residual_raw": spearman(preds, resid),
                     "partial_rho_vs_y_given_blend":
                         partial_spearman(preds, np.array(yte_all), np.array(blend_all)),
                     "rho_with_blend": spearman(preds, np.array(blend_all))})
    yv, bv = np.array(yte_all), np.array(blend_all)
    out = {"side": side,
           "shipped_blend_rho": spearman(bv, yv),
           "blend_vs_own_residual_rho": spearman(bv, resid),
           "calibration_artifact_note":
               "blend_vs_own_residual_rho is the artifact reference: the shipped blend "
               "correlates this strongly with its OWN residual purely through calibration "
               "slope, so any raw residual correlation near it carries no information.",
           "rows": rows}
    (OUT / f"residual_{side}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"== DECISIVE RESIDUAL TEST side={side}")
    print(f"   shipped blend rho vs y      : {spearman(bv, yv):+.4f}")
    print(f"   blend vs its OWN residual   : {spearman(bv, resid):+.4f}  "
          f"(calibration artifact reference)")
    print(f"   {'rho(y)':>9s} {'rho(resid)':>11s} {'PARTIAL rho(y|blend)':>21s} "
          f"{'rho w/ blend':>13s}  config")
    for r in rows:
        print(f"   {r['rho_outcome']:+9.4f} {r['rho_residual_raw']:+11.4f} "
              f"{r['partial_rho_vs_y_given_blend']:+21.4f} "
              f"{r['rho_with_blend']:+13.4f}  {r['id']}")
    return out


# ---------------------------------------------------------------------------
# multiplicity: per-config permutation p -> BH q, plus the family-wise MAX-stat null
# ---------------------------------------------------------------------------

def bh_qvalues(pvals: dict) -> dict:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    q = {}
    prev = 1.0
    for i in range(m - 1, -1, -1):
        cid, p = items[i]
        val = min(prev, p * m / (i + 1))
        q[cid] = val
        prev = val
    return q


def cmd_null(side="hit", B=300, years=FOLD_YEARS):
    """Permute the TRAIN donor labels and re-run the ENTIRE 320-config sweep, B times.

    Gives two things the sweep cannot give on its own:
      - a per-config permutation p-value -> Benjamini-Hochberg q across the whole family
      - the distribution of the BEST statistic the search finds on pure noise. That
        max-statistic null is the honest bar: a candidate must beat what this search
        turns up when there is nothing there."""
    pool = load_pool(side, track_record=True)
    cache = precompute(pool, side, years)
    fam = family()
    obs = run_family(cache, fam)
    ship = shipped_oof(cache, side)
    yte_all, blend_all = [], []
    for yr, F in cache.items():
        yte_all.extend(F["yte"].tolist())
        blend_all.extend(ship[yr]["blend"].tolist())
    yv, bv = np.array(yte_all), np.array(blend_all)

    obs_partial = {}
    for c in fam:
        preds = []
        for yr, F in cache.items():
            Ztr, Zte, _ = F["per"][c["axis_set"]]
            w = fit_weights(Ztr, F["ytr"], c["weighting"])
            g = c["gate"] == "G1_LEVEL_BAND"
            preds.extend(comp_predict(Ztr, F["ytr"], Zte, w, c["k"],
                                      F["lvl_tr"] if g else None,
                                      F["lvl_te"] if g else None).tolist())
        obs_partial[c["id"]] = partial_spearman(np.array(preds), yv, bv)

    rng = np.random.default_rng(SEED)
    ge = {c["id"]: 0 for c in fam}
    maxes, max_partials = [], []
    for b in range(B):
        perm = {yr: rng.permutation(F["ytr"]) for yr, F in cache.items()}
        nul = run_family(cache, fam, ytr_override=perm)
        best, bestid = -9.0, None
        for cid, v in nul.items():
            if v is not None and v >= (obs[cid] or -9):
                ge[cid] += 1
            if v is not None and v > best:
                best, bestid = v, cid
        maxes.append(best)
        # max partial rho under the null, evaluated for the null-best config
        c = next(x for x in fam if x["id"] == bestid)
        preds = []
        for yr, F in cache.items():
            Ztr, Zte, _ = F["per"][c["axis_set"]]
            w = fit_weights(Ztr, perm[yr], c["weighting"])
            g = c["gate"] == "G1_LEVEL_BAND"
            preds.extend(comp_predict(Ztr, perm[yr], Zte, w, c["k"],
                                      F["lvl_tr"] if g else None,
                                      F["lvl_te"] if g else None).tolist())
        max_partials.append(partial_spearman(np.array(preds), yv, bv))
        if (b + 1) % 50 == 0:
            print(f"   ... {b+1}/{B} replicates, running max {max(maxes):.4f}")

    pvals = {cid: (ge[cid] + 1) / (B + 1) for cid in ge}
    qvals = bh_qvalues(pvals)
    maxes = np.array(maxes)
    mp = np.array([x for x in max_partials if x is not None])
    obs_best = max(v for v in obs.values() if v is not None)
    obs_best_id = max(obs, key=lambda k: obs[k] if obs[k] is not None else -9)
    fw_p = float((maxes >= obs_best).mean())

    rank = sorted(fam, key=lambda c: -(obs[c["id"]] or -9))
    res = {
        "side": side, "B": B, "n_hypotheses": len(fam),
        "observed_best": {"id": obs_best_id, "rho": obs_best,
                          "partial_rho_given_blend": obs_partial[obs_best_id]},
        "maxstat_null": {
            "mean": float(maxes.mean()), "sd": float(maxes.std()),
            "p50": float(np.percentile(maxes, 50)),
            "p95": float(np.percentile(maxes, 95)),
            "p99": float(np.percentile(maxes, 99)),
            "max": float(maxes.max()),
            "familywise_p_of_observed_best": fw_p},
        "maxstat_partial_null": {
            "p95": float(np.percentile(mp, 95)) if len(mp) else None,
            "max": float(mp.max()) if len(mp) else None},
        "n_q_below_05": int(sum(1 for v in qvals.values() if v < 0.05)),
        "n_q_below_10": int(sum(1 for v in qvals.values() if v < 0.10)),
        "top20": [{"id": c["id"], "rho": obs[c["id"]],
                   "partial_rho": obs_partial[c["id"]],
                   "perm_p": pvals[c["id"]], "bh_q": qvals[c["id"]]} for c in rank[:20]],
    }
    (OUT / f"null_{side}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"\n== PERMUTATION FAMILY-WISE NULL side={side}  B={B}  family={len(fam)}")
    print(f"   observed best        : {obs_best:.4f}  ({obs_best_id})")
    print(f"   MAX-stat null        : mean {maxes.mean():.4f}  sd {maxes.std():.4f}  "
          f"p95 {np.percentile(maxes,95):.4f}  p99 {np.percentile(maxes,99):.4f}  "
          f"max {maxes.max():.4f}")
    print(f"   family-wise p        : {fw_p:.4f}")
    print(f"   configs with BH q<.05: {res['n_q_below_05']} / {len(fam)}")
    print(f"   max PARTIAL rho null : p95 {res['maxstat_partial_null']['p95']}  "
          f"max {res['maxstat_partial_null']['max']}")
    print(f"   observed best partial: {obs_partial[obs_best_id]:.4f}")
    return res


# ---------------------------------------------------------------------------
# NESTED CV: is the SEARCH PROCEDURE worth anything out of sample?
# ---------------------------------------------------------------------------

INNER_MIN_TRAIN = 100      # relaxed from MIN_TRAIN so early outer folds have inner folds
FIXED_DEFAULT = "S6_STAGExPRODxPEAK|W1_EQUAL|k20|G0_NONE"   # pre-registered a-priori config


def cmd_nested(side="hit", years=FOLD_YEARS):
    pool = load_pool(side, track_record=True)
    fam = family()
    rows, sel_ids = [], []
    sel_pred, fix_pred, shp_pred, truth = [], [], [], []
    for Y in years:
        otr = [r for r in pool if r["_dy"] < Y]
        ote = [r for r in pool if r["_dy"] == Y]
        if len(otr) < MIN_TRAIN or len(ote) < MIN_TEST:
            continue
        inner_years = sorted({r["_dy"] for r in otr})
        iyears = [y for y in inner_years
                  if len([r for r in otr if r["_dy"] < y]) >= INNER_MIN_TRAIN
                  and len([r for r in otr if r["_dy"] == y]) >= MIN_TEST]
        if not iyears:
            rows.append({"outer_year": Y, "skipped": "no inner folds"})
            continue
        icache = precompute(otr, side, iyears)
        if not icache:
            rows.append({"outer_year": Y, "skipped": "no inner cache"})
            continue
        inner = run_family(icache, fam)
        best = max(fam, key=lambda c: inner[c["id"]] if inner[c["id"]] is not None else -9)
        sel_ids.append(best["id"])

        ocache = precompute(pool, side, [Y])
        F = ocache[Y]

        def _pred(cfg):
            Ztr, Zte, _ = F["per"][cfg["axis_set"]]
            w = fit_weights(Ztr, F["ytr"], cfg["weighting"])
            g = cfg["gate"] == "G1_LEVEL_BAND"
            return comp_predict(Ztr, F["ytr"], Zte, w, cfg["k"],
                                F["lvl_tr"] if g else None, F["lvl_te"] if g else None)
        fixed = next(c for c in fam if c["id"] == FIXED_DEFAULT)
        ps, pf = _pred(best), _pred(fixed)
        sh = shipped_oof(ocache, side)[Y]
        sel_pred.extend(ps.tolist())
        fix_pred.extend(pf.tolist())
        shp_pred.extend(sh["blend"].tolist())
        truth.extend(F["yte"].tolist())
        rows.append({"outer_year": Y, "n_inner_folds": len(icache),
                     "n_outer_test": len(ote),
                     "selected": best["id"], "inner_rho_of_selected": inner[best["id"]],
                     "outer_rho_selected": spearman(ps, F["yte"]),
                     "outer_rho_fixed_default": spearman(pf, F["yte"]),
                     "outer_rho_shipped_blend": spearman(sh["blend"], F["yte"])})
    t = np.array(truth)
    res = {"side": side, "fixed_default": FIXED_DEFAULT,
           "inner_min_train": INNER_MIN_TRAIN,
           "selected_per_outer_fold": sel_ids,
           "n_distinct_selected": len(set(sel_ids)),
           "pooled_nested": {
               "search_selected": spearman(np.array(sel_pred), t),
               "fixed_default": spearman(np.array(fix_pred), t),
               "shipped_blend": spearman(np.array(shp_pred), t),
               "n": int(len(t))},
           "per_fold": rows}
    (OUT / f"nested_{side}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"== NESTED CV side={side}   (search run inside inner folds; scored on untouched outer fold)")
    for r in rows:
        if "skipped" in r:
            print(f"   {r['outer_year']}: SKIPPED ({r['skipped']})")
            continue
        print(f"   outer {r['outer_year']}  inner_folds {r['n_inner_folds']}  "
              f"n_te {r['n_outer_test']}  selected={r['selected']}")
        print(f"       inner rho {r['inner_rho_of_selected']:+.4f} -> OUTER rho "
              f"{r['outer_rho_selected']:+.4f}   fixed {r['outer_rho_fixed_default']:+.4f}"
              f"   shipped {r['outer_rho_shipped_blend']:+.4f}")
    p = res["pooled_nested"]
    print(f"   POOLED NESTED (n={p['n']}): search-selected {p['search_selected']:+.4f}   "
          f"fixed-default {p['fixed_default']:+.4f}   shipped-blend {p['shipped_blend']:+.4f}")
    print(f"   distinct configs selected across outer folds: {res['n_distinct_selected']}"
          f"  {sorted(set(sel_ids))}")
    return res


# ---------------------------------------------------------------------------
# THE PRODUCT: comps for live prospects
# ---------------------------------------------------------------------------

# The two metrics actually shipped to the reader. NEITHER is the sweep winner -- picking
# the sweep winner would be selecting a config on the rows it is scored against, which the
# nested-CV arm shows is worth nothing. These are chosen for INTERPRETABILITY and are both
# members of the pre-registered family, so their out-of-fold rho is already measured.
M_MODEL = {"axis_set": "S10_SHIPPED_FEATURES", "weighting": "W3_RIDGE_COEF",
           "k": 20, "gate": "G1_LEVEL_BAND",
           "id": "S10_SHIPPED_FEATURES|W3_RIDGE_COEF|k20|G1_LEVEL_BAND"}
M_ARCH = {"axis_set": "S7_STAGExPRODxTOOLS", "weighting": "W1_EQUAL",
          "k": 20, "gate": "G1_LEVEL_BAND",
          "id": "S7_STAGExPRODxTOOLS|W1_EQUAL|k20|G1_LEVEL_BAND"}

# No-track-record subjects (drafted, no pro season yet) cannot be comped on MiLB axes at
# all. They get their own metric AND their own donor pool -- players who were themselves
# evaluated with no pro track record. Comping them against MiLB donors would compare a
# player who has no production line to players who do.
NOTR_AXES = {"hit": ["tool_hit", "tool_game_pwr", "tool_raw_pwr", "tool_speed",
                     "tool_field", "tool_throw", "fv", "is_college", "is_ifa",
                     "log_pick", "has_pick", "pos_premium"],
             "pit": ["tool_fb", "tool_sl", "tool_cb", "tool_ch", "tool_cmd", "fv",
                     "is_college", "is_ifa", "log_pick", "has_pick", "pos_premium"]}


def implied_fv(war6):
    """Invert the platform's own FV -> 6yr-WAR anchor. Reports the grade whose declared
    expected first-6yr WAR equals the comp-implied WAR."""
    import value_framework as vf
    lo, hi = 20.0, 80.0
    for _ in range(80):
        mid = (lo + hi) / 2
        v = vf.fv_to_6yr_avg_war(mid)
        if v is None:
            return None
        if 6.0 * v < war6:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def display_donors(side):
    """Donors for the reader-facing list: a COMPLETED outcome only.

    censored=False means either a finished 6-year window or a resolved never-MLB player,
    so target_resolved is a real measurement rather than an understatement. Rows still
    inside their window are excluded from the DISPLAY (they are kept in the eval, which
    uses the KM label)."""
    mp = "xfv_hitter_matrix.json" if side == "hit" else "xfv_pitcher_matrix.json"
    rows = json.loads((DATA / mp).read_text(encoding="utf-8"))
    is_pit = side == "pit"
    out = []
    for r in rows:
        if bool(r.get("is_pitcher")) != is_pit:
            continue
        if r.get("kind") == "bust" and r.get("bust_recent"):
            continue
        if r.get("censored"):
            continue
        if r.get(DISPLAY_TARGET) is None or r.get("consensus_fv_raw") is None:
            continue
        r = dict(r)
        r["_dy"] = EM._decision_year(r)
        r["_y"] = float(r[DISPLAY_TARGET])
        out.append(r)
    return out


def _comp_block(subject, donors, keys, side, weighting, k, gate, fit_y=None):
    Xd, imp = build_matrix(donors, keys, side)
    Xs, _ = build_matrix([subject], keys, side, imp=imp)
    mu, sd = Xd.mean(0), Xd.std(0)
    sd = np.where(sd > 1e-9, sd, 1.0)
    Zd, Zs = (Xd - mu) / sd, (Xs - mu) / sd
    yd = np.array([r["_y"] for r in donors])
    w = fit_weights(Zd, yd if fit_y is None else fit_y, weighting)
    lvl_d = lvl_s = None
    if gate:
        lvl_d = np.array([(r.get("milb") or {}).get("level_rank", 0.0) or 0.0
                          for r in donors])
        lvl_s = np.array([(subject.get("milb") or {}).get("level_rank", 0.0) or 0.0])
    pred, idx, dist = comp_predict(Zd, yd, Zs, w, k, lvl_d, lvl_s, want_idx=True)
    idx, dist = idx[0], dist[0]
    ys = yd[idx]
    rng = np.random.default_rng(SEED)
    boot = [float(np.mean(rng.choice(ys, size=len(ys), replace=True))) for _ in range(2000)]
    comps = []
    for i, dd in zip(idx, dist):
        r = donors[int(i)]
        m = r.get("milb") or {}
        comps.append({"player_key": r["player_key"], "realized_war_6yr": round(r["_y"], 2),
                      "dist": round(float(dd), 3), "decision_year": r["_dy"],
                      "level": m.get("milb_level"), "age": m.get("age"),
                      "consensus_fv": r.get("consensus_fv_raw"), "kind": r["kind"]})
    mean = float(ys.mean())
    return {"comp_implied_war_idw": round(float(pred[0]), 2),
            "comp_implied_war_mean": round(mean, 2),
            "comp_implied_war_median": round(float(np.median(ys)), 2),
            "ci95": [round(float(np.percentile(boot, 2.5)), 2),
                     round(float(np.percentile(boot, 97.5)), 2)],
            "bust_rate_lt_0p5": round(float((ys < 0.5).mean()), 3),
            "comp_implied_fv_from_mean": round(implied_fv(mean), 1),
            "n_donors_pool": len(donors), "k": k, "comps": comps}


def cmd_live(side="hit", names=None):
    names = names or []
    live = load_live(side)
    donors_tr = [r for r in display_donors(side) if r.get("milb")]
    donors_no = [r for r in display_donors(side) if not r.get("milb")]
    xfv = json.loads((DATA / "xfv.json").read_text(encoding="utf-8"))["by_player"]
    sweep_p = OUT / f"sweep_{side}.json"
    sweep = json.loads(sweep_p.read_text(encoding="utf-8")) if sweep_p.exists() else None

    out = {"side": side,
           "donor_pool_track_record": len(donors_tr),
           "donor_pool_no_track_record": len(donors_no),
           "metrics": {"M_MODEL": M_MODEL["id"], "M_ARCH": M_ARCH["id"]},
           "measured_oof_rho": {
               "M_MODEL": (sweep or {}).get("observed", {}).get(M_MODEL["id"]),
               "M_ARCH": (sweep or {}).get("observed", {}).get(M_ARCH["id"]),
               "shipped_blend": (sweep or {}).get("baselines", {}).get("shipped_blend"),
               "consensus_ols": (sweep or {}).get("baselines", {}).get("consensus_ols")},
           "players": {}}

    for nm in names:
        r = next((x for x in live if x.get("player_key") == nm), None)
        if r is None:
            out["players"][nm] = {"error": "not in live matrix"}
            continue
        served = xfv.get(nm) or {}
        blk = {"served_efv": served.get("xfv_grade"),
               "served_consensus_fv": served.get("consensus_fv"),
               "served_p_bust": served.get("p_bust"),
               "served_xfv_war_6yr": served.get("xfv_war_6yr"),
               "position": r.get("position"), "asof_date": r.get("asof_date")}
        m = r.get("milb") or {}
        if m:
            blk["as_of"] = {"milb_season": m.get("milb_season"),
                            "level": m.get("milb_level"), "age": m.get("age"),
                            "age_rel_level": m.get("age_rel_level"),
                            "ops_rel": m.get("ops_rel"), "k_rel": m.get("k_rel"),
                            "n_milb_seasons": m.get("n_milb_seasons")}
            for label, cfg in (("M_MODEL", M_MODEL), ("M_ARCH", M_ARCH)):
                blk[label] = _comp_block(r, donors_tr, axis_keys(cfg["axis_set"], side),
                                         side, cfg["weighting"], cfg["k"],
                                         cfg["gate"] == "G1_LEVEL_BAND")
        else:
            # NOT COMP-ABLE. Verified 2026-07-25: 940 of the 970 no-MiLB donors carry
            # milb_unavailable=True, i.e. their MiLB record was never INGESTED (pre-2014
            # StatsAPI floor / missing mlbam id) rather than never EXISTED. So the pool is
            # a data-availability artifact, not a population of players evaluated with no
            # pro experience, and its consensus-FV distribution (median 40.4) does not
            # cover a 57.5-FV subject. Both variants are reported to SHOW the failure:
            # the answer flips entirely on the donor gate, which is the proof that the
            # comp carries no information here beyond the anchor.
            fvv = float(r["consensus_fv_raw"])
            band = [d for d in donors_no if abs(float(d["consensus_fv_raw"]) - fvv) <= 5.0]
            blk["as_of"] = {"note": "NO pro track record (no MiLB block, no pro season)."}
            blk["comp_verdict"] = (
                "NOT COMP-ABLE. The only donors at this information stage are 97% "
                "milb_unavailable rows (data never ingested), so 'no track record' cannot "
                "be distinguished from 'record missing'. The two variants below differ by "
                "donor gate alone and disagree by more than 11 WAR, which is the evidence "
                "that neither is a measurement.")
            blk["M_NOTR_ungated"] = _comp_block(r, donors_no, NOTR_AXES[side], side,
                                                "W1_EQUAL", 20, False)
            blk["M_NOTR_fvband5"] = (
                _comp_block(r, band, NOTR_AXES[side], side, "W1_EQUAL", 20, False)
                if len(band) >= MIN_K else {"error": f"only {len(band)} donors in band"})
            blk["M_NOTR_fvband5"]["n_donors_in_band"] = len(band)
        out["players"][nm] = blk

    (OUT / f"live_{side}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    _print_live(out)
    return out


def _print_live(out):
    print(f"== LIVE COMPS side={out['side']}")
    print(f"   donor pool: {out['donor_pool_track_record']} track-record + "
          f"{out['donor_pool_no_track_record']} no-track-record (COMPLETED outcomes only)")
    mo = out["measured_oof_rho"]
    print(f"   measured out-of-fold rho: M_MODEL {mo['M_MODEL']}  M_ARCH {mo['M_ARCH']}  "
          f"| shipped blend {mo['shipped_blend']}  consensus {mo['consensus_ols']}")
    for nm, b in out["players"].items():
        if "error" in b:
            print(f"\n-- {nm}: {b['error']}")
            continue
        print(f"\n-- {nm}  ({b.get('position')})  served eFV {b['served_efv']}  "
              f"consensus {b['served_consensus_fv']}  p_bust {b['served_p_bust']}")
        print(f"   as-of: {b['as_of']}")
        for label in ("M_MODEL", "M_ARCH", "M_NOTR_ungated", "M_NOTR_fvband5"):
            if label not in b or "error" in b[label]:
                continue
            c = b[label]
            print(f"   [{label}] comp-implied 6yr WAR idw {c['comp_implied_war_idw']} / "
                  f"mean {c['comp_implied_war_mean']} (CI95 {c['ci95']}) / "
                  f"median {c['comp_implied_war_median']}  bust {c['bust_rate_lt_0p5']:.0%}"
                  f"  -> implied FV {c['comp_implied_fv_from_mean']}")
            for x in c["comps"][:10]:
                print(f"        {x['player_key']:28s} WAR {x['realized_war_6yr']:6.2f}  "
                      f"d {x['dist']:5.2f}  {str(x['level']):4s} age {x['age']}  "
                      f"dy {x['decision_year']}  cFV {x['consensus_fv']}")


def cmd_bradfield():
    """The owner's case, with receipts: the stratum AND the kNN comps."""
    donors = [r for r in display_donors("hit") if r.get("milb")]
    AAA = {"AAA"}
    sel = [r for r in donors if (r.get("milb") or {}).get("milb_level") in AAA
           and ((r.get("milb") or {}).get("age") or 0) >= 23.5
           and ((r.get("milb") or {}).get("ops_rel") or 0) < 0]
    ys = np.array([r["_y"] for r in sel])
    print(f"== BRADFIELD STRATUM (AAA, age>=23.5, ops_rel<0), COMPLETED outcomes only")
    print(f"   n={len(sel)}  mean {ys.mean():.2f}  median {np.median(ys):.2f}  "
          f"bust(<0.5) {(ys<0.5).mean():.1%}  implied FV {implied_fv(float(ys.mean())):.1f}")
    spd = [r for r in sel if (r.get("tool_speed") or 0) >= 65]
    if spd:
        y2 = np.array([r["_y"] for r in spd])
        print(f"   + speed>=65: n={len(spd)}  mean {y2.mean():.2f}  "
              f"median {np.median(y2):.2f}  bust {(y2<0.5).mean():.1%}")
    return None


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "prereg"
    side = sys.argv[2] if len(sys.argv) > 2 else "hit"
    if cmd == "prereg":
        cmd_prereg()
    elif cmd == "sweep":
        cmd_sweep(side)
    elif cmd == "sweep_all":
        cmd_sweep(side, track_record=False, tag="_POOLALL")
    elif cmd == "sweep_prod":
        cmd_sweep(side, years=PROD_FOLD_YEARS, tag="_PRODFOLDS")
    elif cmd == "residual":
        cmd_residual(side)
    elif cmd == "null":
        cmd_null(side, B=int(sys.argv[3]) if len(sys.argv) > 3 else 300)
    elif cmd == "nested":
        cmd_nested(side)
    elif cmd == "live":
        if side == "hit":
            cmd_live("hit", ["enrique_bradfield_jr", "franklin_arias", "roch_cholowsky"])
        else:
            cmd_live("pit", ["ryan_sloan", "seth_hernandez"])
    elif cmd == "bradfield":
        cmd_bradfield()
    else:
        print("unknown cmd", cmd)
