"""Part 2 of the independent re-run: the quantity that actually matters.

The lane reports a permutation null (0.4874) for the model's advantage over
CARRY_OVER, then separately reports a zero-information control. Under
docs/EFV_GATE_STANDARD.md section 2 the claim must clear its CONTROL, so the
quantity needing a null band is (mae_control - mae_model), not
(mae_carry_over - mae_model). That band is computed here, together with the
per-season splits of the control-adjusted effect.
"""
import os, random, statistics, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import positional_fit as pf

FIRST, MIN_INN, CAP = 2017, 200.0, 50.0


def prep(o):
    x = {k: {p: v for p, v in d.items() if v["inn"] >= pf.MIN_PAIR_INN}
         for k, d in o.items()}
    return {k: d for k, d in x.items() if d}


def build_rows(obs_all, sig_full):
    rows = []
    for t in range(FIRST, 2026):
        train = {k: v for k, v in obs_all.items() if k[1] <= t}
        multi = {k: d for k, d in train.items() if len(d) >= 2}
        if len(multi) < 100:
            continue
        beta = pf._solve_D(pf._pairs_from(multi))
        Dt = {p: float(beta[pf.IDX[p]]) for p in pf.OAA_POSITIONS}
        sg = pf.fit_signal(prep(train))
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
                rows.append({"season": t, "from": a, "to": b, "z": z,
                             "actual": nv["rate"], "Dt": Dt, "sg": sg,
                             "model": Dt[b] + sg[b]["signal_sd"] * z,
                             "carry_over": src[a]["rate"]})
    return rows


def mae(rs, a):
    return statistics.mean(abs(r[a] - r["actual"]) for r in rs)


def shuffled_mae(rows, rng, per_season=True):
    """One realisation of the zero-information arm."""
    pred = {}
    groups = ({t: [r for r in rows if r["season"] == t]
               for t in {r["season"] for r in rows}} if per_season
              else {0: rows})
    for sub in groups.values():
        zs = [r["z"] for r in sub]
        rng.shuffle(zs)
        for r, zz in zip(sub, zs):
            pred[id(r)] = r["Dt"][r["to"]] + r["sg"][r["to"]]["signal_sd"] * zz
    return statistics.mean(abs(pred[id(r)] - r["actual"]) for r in rows), pred


def main():
    feeds = pf.Feeds()
    obs_all = feeds.rates()
    rows = build_rows(obs_all, None)
    m_model = mae(rows, "model")
    print("n=%d  model %.4f  carry_over %.4f" % (len(rows), m_model, mae(rows, "carry_over")))

    # NULL BAND for the control-adjusted effect: under H0 the model arm is just
    # another shuffle, so draw TWO independent shuffles and take their difference.
    rng = random.Random(2026)
    nulls, ctl_maes = [], []
    for _ in range(4000):
        a, _ = shuffled_mae(rows, rng)
        b, _ = shuffled_mae(rows, rng)
        nulls.append(b - a)
        ctl_maes.append(a)
    nulls = np.array(nulls)
    ctl = np.array(ctl_maes)
    obs_effect = ctl.mean() - m_model
    print("control arm MAE: mean over 8000 shuffles %.4f (single realisation the lane "
          "shipped: 6.2435)" % ctl.mean())
    print("CONTROL-ADJUSTED EFFECT (mean-control): %.4f" % obs_effect)
    print("null band on the same quantity: sd %.4f  p95 %.4f  p99 %.4f  max %.4f"
          % (nulls.std(), np.percentile(nulls, 95), np.percentile(nulls, 99), nulls.max()))
    print("effect / null p95 = %.2fx     p_value(one-sided) = %.4f"
          % (obs_effect / np.percentile(nulls, 95), (nulls >= obs_effect).mean()))

    # per-season splits of the control-adjusted effect (control = mean of 400 shuffles)
    print("\nper-season, control = MEAN of 400 shuffles (not a single draw):")
    pos = 0
    seasons = sorted({r["season"] for r in rows})
    effs = []
    for t in seasons:
        sub = [r for r in rows if r["season"] == t]
        if len(sub) < 10:
            continue
        r2 = random.Random(t)
        cm = np.mean([shuffled_mae(sub, r2)[0] for _ in range(400)])
        e = cm - mae(sub, "model")
        effs.append(e)
        pos += e > 0
        print("  %d  n=%-3d model %.3f  control %.3f  effect %+.3f"
              % (t, len(sub), mae(sub, "model"), cm, e))
    effs = np.array(effs)
    print("  mean %+.4f  sd %.4f  positive in %d/%d  t=%.2f"
          % (effs.mean(), effs.std(ddof=1), pos, len(effs),
             effs.mean() / (effs.std(ddof=1) / np.sqrt(len(effs)))))


if __name__ == "__main__":
    main()
