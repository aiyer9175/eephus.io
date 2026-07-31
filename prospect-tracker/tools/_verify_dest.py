"""The one claim in positional_fit with NO control beside it.

data/positional_fit.json records destination_top1 = {"model": 0.5458,
"control": null}.  The gate standard requires a zero-information control on
every claim.  Two trivial baselines are scored here on the identical rows.
"""
import os, random, sys, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import positional_fit as pf

feeds = pf.Feeds()
f = pf.fit_all(feeds, verbose=False)
lad, sig, feas = f["ladder"]["values"], f["signal"], f["feasibility"]
inn650 = f["inn_per_650pa"]
obs_all = feeds.rates()
recs = []
for t in range(2017, 2026):
    train = {k: v for k, v in obs_all.items() if k[1] <= t}
    multi = {k: d for k, d in train.items() if len(d) >= 2}
    if len(multi) < 100:
        continue
    beta = pf._solve_D(pf._pairs_from(multi))
    Dt = {p: float(beta[pf.IDX[p]]) for p in pf.OAA_POSITIONS}
    for (mid, s), row in obs_all.items():
        if s != t:
            continue
        cur = feeds.primary_position(mid, t)
        if cur not in pf.OAA_POSITIONS or sum(v["inn"] for v in row.values()) < 400.0:
            continue
        nxt = feeds.primary_position(mid, t + 1)
        if nxt is None:
            continue
        if sum(v["inn"] for p, v in feeds.innings(mid, t + 1).items() if p != "P") < 200.0:
            continue
        if not (lad.get(nxt, -99) < lad[cur] - 0.5):
            continue                                   # keep the 'moved down' rows
        z, _ = pf._shrunk_z(row, Dt, sig)
        cand = set(feas["allowed"].get(cur, ["DH"])) | {
            p for p, v in row.items() if v["inn"] >= 100} | {"DH", cur}
        vals = {}
        for p in cand:
            if p == "DH":
                vals["DH"] = lad["DH"]
            elif p in pf.OAA_POSITIONS:
                vals[p] = (Dt[p] + sig[p]["signal_sd"] * z) * inn650 / 1000.0 + lad[p]
        downs = {p: v for p, v in vals.items() if lad[p] < lad[cur] - 0.5}
        if not downs:
            continue
        recs.append({"from": cur, "to": nxt, "downs": downs,
                     "model": max(downs, key=lambda p: downs[p]),
                     # BASELINE A: the smallest demotion available (ladder only,
                     # zero player information)
                     "shortest": max(downs, key=lambda p: lad[p]),
                     "season": t})

n = len(recs)
print("moved-down rows with a feasible down candidate: %d" % n)
print("model  top1 = %.4f" % (sum(r["to"] == r["model"] for r in recs) / n))
print("ladder top1 (smallest available demotion, NO player info) = %.4f"
      % (sum(r["to"] == r["shortest"] for r in recs) / n))
# BASELINE B: the modal realised destination for that origin, from PRIOR seasons
hit = 0
for r in recs:
    prior = collections.Counter(x["to"] for x in recs
                                if x["from"] == r["from"] and x["season"] < r["season"])
    if prior and prior.most_common(1)[0][0] == r["to"]:
        hit += 1
print("modal-destination-for-this-origin (prior seasons only) = %.4f" % (hit / n))
print("destination mix:", collections.Counter(r["to"] for r in recs).most_common())
