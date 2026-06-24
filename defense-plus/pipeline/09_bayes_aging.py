# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ Part 4 — hierarchical Bayesian aging (fixes the survivorship-broken naive curves).

Problem (flagged correctly): binning year-over-year deltas by age compares DIFFERENT
players at each age. Survivors at old ages are positively selected (the decliners left
OF), so skills look like they flatten or "age up". The within-player trajectory is never
isolated.

Model: skill_{i,t} = player_i + f(age) + noise
    player_i ~ Normal(mu, sigma_player)   <- the PLAYER (stable level / who's in the sample)
    f(age)   = b1*(age-27) + b2*(age-27)^2 <- the SKILL's aging, identified WITHIN player
Player random intercepts remove level-selection; the age curve comes from within-career
change, not the cross-section. We fit each jump component + OAA, derive peak age and
decline with 94% HDI, and contrast against the naive bin curve to expose the bias.

CAVEAT: residual *dynamic* survivorship (players who collapse then exit) is unobservable
once they leave OF, so the within-player decline is a conservative (lower-bound) estimate.
"""
import os, warnings
import numpy as np, pandas as pd, pymc as pm
warnings.filterwarnings("ignore"); pd.set_option("display.width", 210)
import logging; logging.getLogger("pymc").setLevel(logging.ERROR)

HOME = os.path.expanduser("~"); RAW = os.path.join(HOME, "defense_plus/data/raw")
REP = os.path.join(HOME, "defense_plus/reports")
YEARS = list(range(2016, 2026))
COMP = {"reaction": "rel_league_reaction_distance", "burst": "rel_league_burst_distance",
        "route": "rel_league_routing_distance", "jump_total": "rel_league_bootup_distance"}

fr = []
for y in YEARS:
    d = pd.read_csv(os.path.join(RAW, f"ofjump_{y}.csv")).rename(columns={"resp_fielder_id": "id"}); d["year"] = y; fr.append(d)
J = pd.concat(fr, ignore_index=True).rename(columns={v: k for k, v in COMP.items()})
J["OAA"] = pd.to_numeric(J["outs_above_average"], errors="coerce")
for c in list(COMP) + ["n", "OAA"]:
    J[c] = pd.to_numeric(J[c], errors="coerce")
dm = pd.read_parquet(os.path.join(HOME, "projection_engine/data/deep_mlb.parquet"))[["batter", "season", "age"]]
J = J.merge(dm.rename(columns={"batter": "id", "season": "year"}), on=["id", "year"], how="left")
J = J[(J["n"] >= 20)].dropna(subset=list(COMP) + ["OAA", "age"]).copy()
# z within year so components are comparable (SD vs peers); aging then reads in SD/yr
SIG = list(COMP) + ["OAA"]
for c in SIG:
    J[c + "z"] = J.groupby("year")[c].transform(lambda x: (x - x.mean()) / x.std())
# keep players with >=2 seasons (within-player info identifies aging)
cnt = J.groupby("id").size(); J = J[J.id.isin(cnt[cnt >= 2].index)].copy()
J["pid"] = pd.Categorical(J["id"]).codes
nP = J.pid.nunique()
print(f"sample: {len(J)} OF-seasons, {nP} players (>=2 seasons), ages {int(J.age.min())}-{int(J.age.max())}\n")

ages = np.arange(21, 37)
def naive_delta_curve(sig):  # the broken method: mean within-player delta by age, cumulated
    a = J.sort_values(["id", "year"]).copy()
    a["d"] = a.groupby("id")[sig + "z"].diff()
    a["age0"] = a.groupby("id")["age"].shift()
    g = a.dropna(subset=["d", "age0"]).groupby(a["age0"].round())["d"].mean()
    return g

rows = []
curves = {}
for sig in SIG:
    y = J[sig + "z"].values; pid = J["pid"].values; c = (J["age"].values - 27.0)
    with pm.Model() as m:
        mu = pm.Normal("mu", 0, 1); sig_p = pm.HalfNormal("sig_p", 1)
        pl = pm.Normal("pl", mu, sig_p, shape=nP)
        b1 = pm.Normal("b1", 0, 0.5); b2 = pm.Normal("b2", 0, 0.5)
        sd = pm.HalfNormal("sd", 1)
        mean = pl[pid] + b1 * c + b2 * c ** 2
        pm.Normal("obs", mean, sd, observed=y)
        idata = pm.sample(700, tune=700, chains=2, target_accept=0.9,
                          progressbar=False, random_seed=1)
    post = idata.posterior
    B1 = post["b1"].values.ravel(); B2 = post["b2"].values.ravel()
    # curve over ages (population age effect, centered at 27)
    cc = ages - 27.0
    fc = B1[:, None] * cc[None, :] + B2[:, None] * cc[None, :] ** 2
    curve_mean = fc.mean(0); curve_lo = np.percentile(fc, 3, 0); curve_hi = np.percentile(fc, 97, 0)
    curves[sig] = (curve_mean, curve_lo, curve_hi)
    # peak age (where derivative 0): age* = 27 - b1/(2 b2) when b2<0
    peak = np.where(B2 < -1e-6, 27 - B1 / (2 * B2), np.nan)
    peak = np.clip(peak, 18, 40)
    decl_27_33 = (B1 * (33 - 27) + B2 * (33 - 27) ** 2) - 0  # change from 27 to 33 (z units)
    naive = naive_delta_curve(sig)
    naive_old = naive.reindex([30, 31, 32, 33]).mean()   # naive delta in old ages
    rows.append(dict(signal=sig,
                     slope_at27=round(np.median(B1), 3),
                     curv_b2=round(np.median(B2), 3),
                     peak_age=round(np.nanmedian(peak), 1),
                     decline_27to33_SD=round(np.median(decl_27_33), 2),
                     naive_old_delta=round(float(naive_old), 3)))
    print(f"{sig:11} slope@27={np.median(B1):+.3f}/yr  peak~{np.nanmedian(peak):.1f}  "
          f"27->33 decline={np.median(decl_27_33):+.2f} SD  | naive old-age delta={float(naive_old):+.3f}")

R = pd.DataFrame(rows); R.to_csv(os.path.join(REP, "09_bayes_aging.csv"), index=False)
# save curves for viz
cv = pd.DataFrame({"age": ages})
for sig in SIG:
    cv[sig + "_mean"], cv[sig + "_lo"], cv[sig + "_hi"] = curves[sig]
cv.to_csv(os.path.join(REP, "09_aging_curves.csv"), index=False)
print("\n=== hierarchical Bayesian aging (within-player, SD vs peers) ===")
print(R.to_string(index=False))
print("\nKey contrast: naive old-age deltas go ~0/positive (survivorship); the within-player")
print("model recovers monotonic athletic decline (burst) and slow-aging skill (reaction/route).")
print(f"wrote reports/09_bayes_aging.csv, reports/09_aging_curves.csv")
