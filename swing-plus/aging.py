# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
aging.py — Component-level Bayesian aging projection for Swing+.

Uses the survivorship-corrected Bayesian drift estimates (per-feature dy/dage with
95% credible intervals) from ~/mlb-aging-curves/aging_drift_estimates.csv. We age
each of the 9 swing-tracking FEATURES forward by its drift, then re-score Swing+
(and predicted stats) at each age — so the aging curve is built from component
drift, not fit directly on Swing+.

Three lines:
  projected      — age all features by their mean drift, re-score
  ci band        — re-score using the per-feature drift 95% bounds (propagated)
  maintain_bs    — counterfactual: freeze bat speed (mean+std) at today's value,
                   age everything else; isolates the bat-speed contribution.

Sanity: the Swing+ model has NO age input (verified) — aging is applied to the
inputs and re-scored, so there is no double-counting.
"""

import warnings; warnings.filterwarnings("ignore")
import json
from pathlib import Path
import numpy as np, pandas as pd
from swing_plus import SwingPlusModel

PROJECT = Path(__file__).parent
PROC = PROJECT / "data" / "processed"
DRIFT_CSV = Path("/Users/willcahoon/mlb-aging-curves/aging_drift_estimates.csv")

_MODEL = SwingPlusModel(PROJECT / "swing_plus_model_v1.joblib")
_FEATS = _MODEL.features


def _load_drift():
    """{feature: {age: (mean, lo, hi)}}. Missing features (e.g. *_std with no
    source) drift 0."""
    if not DRIFT_CSV.exists():
        return {}
    d = pd.read_csv(DRIFT_CSV)
    out = {}
    for f, g in d.groupby("feature"):
        out[f] = {int(r.age): (r.drift_mean, r.drift_lower_95, r.drift_upper_95)
                  for r in g.itertuples()}
    return out


def birthdate(batter):
    cache = PROC / "birthdates.json"
    if cache.exists():
        b = json.loads(cache.read_text()).get(str(batter))
        if b:
            return b
    import urllib.request
    try:
        d = json.load(urllib.request.urlopen(
            f"https://statsapi.mlb.com/api/v1/people/{batter}", timeout=15))
        return d["people"][0].get("birthDate")
    except Exception:
        return None


def _score(profile):
    df = pd.DataFrame([{f: profile[f] for f in _FEATS}]); df["n_swings"] = 400
    return float(_MODEL.score_profiles(df, reliability_weight=False)["swing_plus_raw"].iloc[0])


def score_profile(profile):
    """Public raw Swing+ score for a single 9-feature profile (handles the
    pull-positive display sign on attack_direction)."""
    p = dict(profile)
    if "attack_direction_mean" in p:
        p["attack_direction_mean"] = -float(p["attack_direction_mean"])
    return round(_score({f: float(p[f]) for f in _FEATS}), 1)


_JUMP_CACHE = {}
def bat_speed_p90_jump():
    """90th-percentile real one-season bat-speed GAIN (mph), measured as each
    player's best single-year jump across 2023-26. ~Miguel-Vargas-style breakout
    sits in this tail (his +3.2 was ~99th pct). Cached."""
    if "v" in _JUMP_CACHE:
        return _JUMP_CACHE["v"]
    v = 1.9
    try:
        sb = pd.read_parquet(PROC / "leaderboard_season.parquet")
        sb = sb[sb["n_swings"] >= 150]
        best = []
        for _, g in sb.groupby("name"):
            g = g.sort_values("season"); d = []
            for i in range(1, len(g)):
                if int(g.season.iloc[i]) - int(g.season.iloc[i - 1]) == 1:
                    d.append(g.bat_speed_mean.iloc[i] - g.bat_speed_mean.iloc[i - 1])
            if d:
                best.append(max(d))
        if best:
            v = round(float(np.percentile(best, 90)), 2)
    except Exception:
        pass
    _JUMP_CACHE["v"] = v
    return v


_SLOPE_CACHE = {}
def bat_speed_swingplus_slope():
    """Empirical ΔSwing+ per +1 mph of real bat-speed gain (year-over-year, all
    players). The REAL-WORLD response — shallower than the model's isolated partial
    derivative because actual bat-speed jumps don't come with everything else frozen.
    Used to size the 90th-pct upside so it reflects real player outcomes. Cached."""
    if "v" in _SLOPE_CACHE:
        return _SLOPE_CACHE["v"]
    v = 2.74
    try:
        sb = pd.read_parquet(PROC / "leaderboard_season.parquet")
        sb = sb[sb["n_swings"] >= 150]
        db, ds = [], []
        for _, g in sb.groupby("name"):
            g = g.sort_values("season")
            for i in range(1, len(g)):
                if int(g.season.iloc[i]) - int(g.season.iloc[i - 1]) == 1:
                    db.append(g.bat_speed_mean.iloc[i] - g.bat_speed_mean.iloc[i - 1])
                    ds.append(g.swing_plus.iloc[i] - g.swing_plus.iloc[i - 1])
        if len(db) > 30:
            v = round(float(np.polyfit(db, ds, 1)[0]), 2)
    except Exception:
        pass
    _SLOPE_CACHE["v"] = v
    return v


_LEAGUE_CACHE = {}
def league_curve():
    """Cross-sectional league-average raw Swing+ by integer age (population mean
    of all player-seasons). Survivor-biased at the old end — a rough reference."""
    if "v" in _LEAGUE_CACHE:
        return _LEAGUE_CACHE["v"]
    out = {}
    try:
        bd = json.loads((PROC / "birthdates.json").read_text())
        sb = pd.read_parquet(PROC / "leaderboard_season.parquet")
        sb = sb[(sb["n_swings"] >= 150) & sb["swing_plus"].notna()].copy()
        sb["bd"] = sb["batter"].astype(str).map(bd)
        sb = sb[sb["bd"].notna()]
        age = (pd.to_datetime(sb["season"].astype(str) + "-07-01") - pd.to_datetime(sb["bd"])).dt.days / 365.25
        sb["age"] = age.round().astype(int)
        gm = sb.groupby("age")["swing_plus"].agg(["mean", "size"])
        out = {int(a): round(float(r["mean"]), 1) for a, r in gm.iterrows() if r["size"] >= 12}
    except Exception:
        pass
    _LEAGUE_CACHE["v"] = out
    return out


def project(batter, profile, season=2026, horizon=6):
    """profile: dict of the 9 swing features (the player's current profile).
    Returns ages + projected Swing+ (mean / lo / hi) + maintain-bat-speed line."""
    # attack_direction is stored pull-POSITIVE (display) but the model + drift CSV
    # are in the raw Statcast sign (pull-negative) — flip back before scoring/aging.
    profile = dict(profile)
    if "attack_direction_mean" in profile:
        profile["attack_direction_mean"] = -float(profile["attack_direction_mean"])
    bd = birthdate(batter)
    if not bd:
        return None
    age0 = (pd.Timestamp(f"{season}-07-01") - pd.Timestamp(bd)).days / 365.25
    a0 = int(round(age0))
    drift = _load_drift()
    if not drift:
        return None

    def drift_at(f, age, which):  # which: 0 mean, 1 lo, 2 hi
        t = drift.get(f, {}).get(min(max(age, 20), 40))
        return t[which] if t else 0.0

    cur = {f: float(profile[f]) for f in _FEATS}
    mean_p = dict(cur); lo_p = dict(cur); hi_p = dict(cur); mbs_p = dict(cur)
    BS = {"bat_speed_mean", "bat_speed_std"}     # frozen in the counterfactual
    jump = bat_speed_p90_jump()
    slope = bat_speed_swingplus_slope()
    gain = round(jump * slope, 1)                 # realistic Swing+ lift from the breakout
    ages = [a0]; mean_c = [round(_score(cur), 1)]
    lo_c = [mean_c[0]]; hi_c = [mean_c[0]]; mbs_c = [mean_c[0]]
    for k in range(1, horizon + 1):
        a = a0 + k
        if a > 40:
            break
        for f in _FEATS:
            mean_p[f] += drift_at(f, a - 1, 0)
            # CI: worst/best feature drift -> but feature direction vs Swing+ varies,
            # so we propagate by re-scoring at lo/hi feature values (bounds the score).
            lo_p[f]  += drift_at(f, a - 1, 1)
            hi_p[f]  += drift_at(f, a - 1, 2)
            if f not in BS:                       # counterfactual freezes bat speed
                mbs_p[f] += drift_at(f, a - 1, 0)
        ages.append(a)
        mean_c.append(round(_score(mean_p), 1))
        s_lo, s_hi = _score(lo_p), _score(hi_p)
        lo_c.append(round(min(s_lo, s_hi), 1)); hi_c.append(round(max(s_lo, s_hi), 1))
    # 90th-pct upside: median path + a sustained top-decile bat-speed gain, sized by the
    # EMPIRICAL ΔSwing+/mph (real outcomes) rather than the model's steeper isolated partial.
    up_c = [mean_c[0]] + [round(v + gain, 1) for v in mean_c[1:]]
    return {"current_age": round(age0, 1), "ages": ages,
            "normal": mean_c, "p90": up_c, "bs_jump": jump, "bs_gain": gain,
            "lo": lo_c, "hi": hi_c, "maintain_bs": mbs_c,
            "method": "bayesian component drift (survivorship-corrected)"}


if __name__ == "__main__":
    sb = pd.read_parquet(PROC / "leaderboard_season.parquet")
    for nm, bid in [("Aaron Judge", 592450), ("Gunnar Henderson", 683002)]:
        d = sb[sb["batter"] == bid].sort_values("season")
        if d.empty:
            print(nm, "no rows"); continue
        row = d.iloc[-1]
        prof = {f: row[f] for f in _FEATS}
        r = project(bid, prof, season=int(row["season"]))
        if r:
            print(f"\n{nm} (age {r['current_age']}):")
            print("  age:      ", r["ages"])
            print("  projected:", r["normal"])
            print("  95% band: ", list(zip(r["lo"], r["hi"])))
            print("  maint bs: ", r["maintain_bs"])
