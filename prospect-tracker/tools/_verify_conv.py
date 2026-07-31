"""Independent re-run of positional_fit's PRIMARY claim under the gate standard.

Two deviations from the lane's harness, both required by docs/EFV_GATE_STANDARD.md:
  1. sig (signal_sd, k_inn) refit EX-ANTE on seasons <= t.  The shipped harness
     passes a sig fit on ALL seasons (2016-2026) including the label season t+1.
  2. Paired bootstrap resampling the WHOLE pool (players) with a REFIT of sig and D
     on every draw, instead of resampling the 169 finished test rows only.
"""
import math, os, random, statistics, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import positional_fit as pf

FIRST, MIN_INN, CAP = 2017, 200.0, 50.0


def build_rows(obs_all, sig_mode, seed=61, sig_full=None):
    """sig_mode: 'full' = lane behaviour, 'exante' = refit sig on seasons <= t."""
    last = 2025
    rows = []
    for t in range(FIRST, last + 1):
        train = {k: v for k, v in obs_all.items() if k[1] <= t}
        multi = {k: d for k, d in train.items() if len(d) >= 2}
        if len(multi) < 100:
            continue
        beta = pf._solve_D(pf._pairs_from(multi))
        Dt = {p: float(beta[pf.IDX[p]]) for p in pf.OAA_POSITIONS}
        sg = sig_full if sig_mode == "full" else pf.fit_signal(prep(train))
        for (mid, s), row in obs_all.items():
            if s != t:
                continue
            nxt = obs_all.get((mid, t + 1))
            if not nxt:
                continue
            src = {p: v for p, v in row.items() if v["inn"] >= MIN_INN}
            if not src:
                continue
            for b, nv in nxt.items():
                if nv["inn"] < MIN_INN or b in src:
                    continue
                prior = sum(obs_all.get((mid, y), {}).get(b, {}).get("inn", 0.0)
                            for y in range(t - 2, t + 1))
                if prior > CAP:
                    continue
                a = max(src, key=lambda p: src[p]["inn"])
                z, _ = pf._shrunk_z(src, Dt, sg)
                rows.append({"mlbam": mid, "season": t, "from": a, "to": b,
                             "actual": nv["rate"], "z": z, "Dt": Dt, "sg": sg,
                             "model": Dt[b] + sg[b]["signal_sd"] * z,
                             "carry_over": src[a]["rate"],
                             "d_shift": src[a]["rate"] - Dt[a] + Dt[b],
                             "league_avg": Dt[b]})
    return rows


def mae(rs, a):
    return statistics.mean(abs(r[a] - r["actual"]) for r in rs)


def add_control(rows, rng):
    for t in sorted({r["season"] for r in rows}):
        sub = [r for r in rows if r["season"] == t]
        zs = [r["z"] for r in sub]
        rng.shuffle(zs)
        for r, zz in zip(sub, zs):
            r["permuted"] = r["Dt"][r["to"]] + r["sg"][r["to"]]["signal_sd"] * zz


def prep(obs_source):
    obs = {k: {p: v for p, v in d.items() if v["inn"] >= pf.MIN_PAIR_INN}
           for k, d in obs_source.items()}
    return {k: d for k, d in obs.items() if d}


def main():
    feeds = pf.Feeds()
    # EXACT lane replication: conversion_accuracy uses the RAW rates for row
    # construction, and a sig fit on the MIN_PAIR_INN-filtered pool (from fit_all).
    obs_all = feeds.rates()
    sig_full = pf.fit_signal(prep(obs_all))
    rng = random.Random(61)

    out = {}
    for mode in ("full", "exante"):
        rows = build_rows(obs_all, mode, sig_full=sig_full)
        add_control(rows, random.Random(61))
        out[mode] = {
            "n": len(rows),
            "mae": {a: round(mae(rows, a), 4) for a in
                    ("model", "carry_over", "d_shift", "league_avg", "permuted")},
            "adv_carry": round(mae(rows, "carry_over") - mae(rows, "model"), 4),
            "adv_ctl": round(mae(rows, "permuted") - mae(rows, "model"), 4),
        }
        print(mode, json.dumps(out[mode]))

    # ---- exact permutation p-value for the model's advantage over carry_over ----
    rows = build_rows(obs_all, "exante")
    base_adv = mae(rows, "carry_over") - mae(rows, "model")
    rngp = random.Random(7)
    nulls = []
    for _ in range(2000):
        zs = [r["z"] for r in rows]
        rngp.shuffle(zs)
        m = statistics.mean(abs(r["Dt"][r["to"]] + r["sg"][r["to"]]["signal_sd"] * zz
                                - r["actual"]) for r, zz in zip(rows, zs))
        nulls.append(mae(rows, "carry_over") - m)
    nulls = np.array(nulls)
    print("PERM NULL (ex-ante sig): adv=%.4f  null mean %.4f  p95 %.4f  p99 %.4f  max %.4f  "
          "p_value %.4f" % (base_adv, nulls.mean(), np.percentile(nulls, 95),
                            np.percentile(nulls, 99), nulls.max(),
                            (nulls >= base_adv).mean()))

    # ---- PAIRED BOOTSTRAP over the WHOLE pool with a refit each draw ----
    players = sorted({k[0] for k in obs_all})
    B = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    rb = random.Random(101)
    dc, dctl, ns = [], [], []
    for i in range(B):
        pick = [players[rb.randrange(len(players))] for _ in players]
        boot_obs = {}
        for j, p in enumerate(pick):
            for (m, y), d in obs_all.items():
                if m == p:
                    boot_obs[(j, y)] = d
        r2 = build_rows(boot_obs, "exante")
        if len(r2) < 30:
            continue
        add_control(r2, random.Random(1000 + i))
        dc.append(mae(r2, "carry_over") - mae(r2, "model"))
        dctl.append(mae(r2, "permuted") - mae(r2, "model"))
        ns.append(len(r2))
        if (i + 1) % 25 == 0:
            print("  draw %d/%d  n_rows~%d  adv_carry %.3f  adv_ctl %.3f"
                  % (i + 1, B, int(np.mean(ns)), np.mean(dc), np.mean(dctl)))
    for name, v in (("vs carry_over", dc), ("vs zero-info control", dctl)):
        v = np.array(v)
        print("PAIRED BOOT REFIT %s: mean %.4f  sd %.4f  CI95 [%.4f, %.4f]  P(>0) %.3f"
              % (name, v.mean(), v.std(ddof=1), np.percentile(v, 2.5),
                 np.percentile(v, 97.5), (v > 0).mean()))


if __name__ == "__main__":
    main()
