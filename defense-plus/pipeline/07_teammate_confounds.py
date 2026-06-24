# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ Part 3 — teammate / positioning confounds.

The Part-2 latent model removed metric-specific noise but NOT variance SHARED across
metrics (positioning, park, opportunity, scorer, roster construction). Part 3 asks how
big that shared confound is and whether Defense+ must adjust for it. Every test carries
a permutation/placebo floor — teammate "effects" are the textbook season-grain
confound-factory, so nothing counts unless it beats chance.

Test A — shared team-season component (ICC): do teammates' OAA correlate beyond chance?
         ICC_hat = mean(z_i * z_j) over within-team-season teammate pairs (z = OAA z-scored
         within position-year). Permutation null (shuffle players across teams) ~ 0.
Test B — does talent TRAVEL: y2y OAA persistence for players who CHANGED teams vs stayed.
         If movers persist as well as stayers, OAA is player talent, not team context.
Test C — OF opportunity cannibalization: does a corner OF's opportunity rate (BIZ/Inn)
         fall when paired with a high-range CF? Placebo = random CF pairing.
"""
import os, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)

HOME = os.path.expanduser("~"); RAW = os.path.join(HOME, "defense_plus/data/raw")
REP = os.path.join(HOME, "defense_plus/reports")
YEARS = list(range(2021, 2026))
OF = ["CF", "LF", "RF"]; IF = ["SS", "2B", "3B"]
MIN_INN = 400
rng = np.random.default_rng(0)

# ---- load FG fielding + team from usage_spine ----
fr = []
for y in YEARS:
    d = pd.read_csv(os.path.join(RAW, f"fg_field_full_{y}.csv")).rename(columns={"xMLBAMID": "id"})
    d["year"] = y; fr.append(d)
F = pd.concat(fr, ignore_index=True)
for c in ["id", "Inn", "OAA", "DRS", "BIZ"]:
    F[c] = pd.to_numeric(F[c], errors="coerce")
F = F[F.id.notna() & (F.Inn >= MIN_INN) & F.Pos.isin(OF + IF)].copy(); F["id"] = F.id.astype(int)
u = pd.read_parquet(os.path.join(HOME, "playing_time_model/data/processed/usage_spine.parquet"))
F = F.merge(u[["mlbam_id", "season", "team_id"]].rename(columns={"mlbam_id": "id", "season": "year"}),
            on=["id", "year"], how="left").dropna(subset=["team_id"])
F["team_id"] = F.team_id.astype(int)
F["oaa_z"] = F.groupby(["Pos", "year"])["OAA"].transform(lambda x: (x - x.mean()) / x.std())
F["biz_rate"] = F["BIZ"] / F["Inn"]

# ================= Test A — shared team-season component (ICC) =================
def icc_test(d, group):
    """mean product of z-OAA over within-(team,year) teammate pairs; permutation null."""
    pairs = []
    for (t, y), g in d.groupby(["team_id", "year"]):
        z = g["oaa_z"].dropna().values
        for i in range(len(z)):
            for j in range(i + 1, len(z)):
                pairs.append((z[i], z[j]))
    pairs = np.array(pairs)
    if len(pairs) < 30: return None
    obs = np.mean(pairs[:, 0] * pairs[:, 1])
    # permutation: reshuffle the z values across all players, keep group structure
    zall = d["oaa_z"].dropna().values
    sizes = d.dropna(subset=["oaa_z"]).groupby(["team_id", "year"]).size().values
    null = []
    for _ in range(1000):
        perm = rng.permutation(zall); idx = 0; pr = []
        for s in sizes:
            grp = perm[idx:idx + s]; idx += s
            for i in range(len(grp)):
                for j in range(i + 1, len(grp)):
                    pr.append(grp[i] * grp[j])
        null.append(np.mean(pr))
    null = np.array(null)
    p = (np.sum(np.abs(null) >= abs(obs)) + 1) / (len(null) + 1)
    return dict(group=group, n_pairs=len(pairs), icc=round(obs, 3),
                null_sd=round(null.std(), 3), p=round(p, 3))

print("===== Test A — shared team-season component of OAA (ICC vs permutation null) =====")
for grp, pos in [("OF (CF/LF/RF)", OF), ("IF (SS/2B/3B)", IF)]:
    r = icc_test(F[F.Pos.isin(pos)], grp)
    if r: print(f"  {grp:16} ICC={r['icc']:+.3f}  (null sd {r['null_sd']}, p={r['p']}, {r['n_pairs']} pairs)")
print("  ICC ~ 0 => OAA is well-isolated from teammates (no team de-meaning needed)")
print("  ICC > 0 => shared positioning/park/scorer confound => Defense+ should team-adjust\n")

# ================= Test B — does talent travel across team changes =================
print("===== Test B — OAA persistence: movers (changed team) vs stayers =====")
pairs = []
for pos, g in F.groupby("Pos"):
    a = g[["id", "year", "oaa_z", "team_id"]]
    b = g[["id", "year", "oaa_z", "team_id"]].rename(columns={"year": "y0", "oaa_z": "z0", "team_id": "team0"})
    b["year"] = b["y0"] + 1
    m = a.merge(b[["id", "year", "z0", "team0"]], on=["id", "year"]).dropna(subset=["oaa_z", "z0"])
    pairs.append(m)
P = pd.concat(pairs, ignore_index=True)
P["moved"] = (P["team_id"] != P["team0"]).astype(int)
for lab, sub in [("stayers", P[P.moved == 0]), ("movers ", P[P.moved == 1])]:
    r = np.corrcoef(sub["z0"], sub["oaa_z"])[0, 1]
    print(f"  {lab}: y2y OAA r = {r:.3f}  (n={len(sub)})")
print("  similar r => OAA travels with the PLAYER (talent, not context)\n")

# ================= Test C — OF opportunity cannibalization =================
print("===== Test C — corner-OF opportunity rate vs CF range (cannibalization) =====")
of = F[F.Pos.isin(OF)].copy()
prim = of.sort_values("Inn").groupby(["team_id", "year", "Pos"]).tail(1)
cf = prim[prim.Pos == "CF"][["team_id", "year", "oaa_z", "biz_rate"]].rename(
    columns={"oaa_z": "cf_oaa_z", "biz_rate": "cf_biz"})
corners = prim[prim.Pos.isin(["LF", "RF"])][["team_id", "year", "Pos", "biz_rate", "oaa_z"]]
cc = corners.merge(cf, on=["team_id", "year"]).dropna(subset=["biz_rate", "cf_oaa_z"])
r_opp = np.corrcoef(cc["cf_oaa_z"], cc["biz_rate"])[0, 1]
# placebo: shuffle CF across team-seasons
null = [np.corrcoef(cc["cf_oaa_z"].sample(frac=1, random_state=int(s)).values, cc["biz_rate"])[0, 1]
        for s in range(1000)]
p = (np.sum(np.abs(null) >= abs(r_opp)) + 1) / 1001
print(f"  corr(CF range z, corner opportunity rate BIZ/Inn) = {r_opp:+.3f}  (placebo sd {np.std(null):.3f}, p={p:.3f}, n={len(cc)})")
print("  negative & beats placebo => elite CF steals corner opportunities (cannibalization on COUNT)")

pd.DataFrame([{"note": "Part 3 results in stdout / PART3 report"}]).to_csv(os.path.join(REP, "07_teammate.csv"), index=False)
