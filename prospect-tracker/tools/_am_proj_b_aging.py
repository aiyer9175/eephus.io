"""AM-PROJ (b): is the shipped war_rate aging curve right?

PRE-REGISTERED ARMS (all are post-fit transforms of the curve dict, applied
identically at every base; no lookahead, no new data):

  base : shipped curves, untouched.
  A1   : n-guard. The shipped cell guard is `n_pool < 12`, but n_pool counts
         the age-t POOL while the delta is built from n_stay PAIRS -- cells
         with 3 pairs ship. A1 drops war_rate/pt cells with n_stay < NGUARD;
         curve_delta's nearest-supported-age lookup covers the hole.
  A2   : monotone tail. For ages >= MONO_FROM the smoothed war_rate delta is
         forced non-increasing (running min). Rationale stated ex ante: an
         aging curve must not become LESS punitive as a player gets older, and
         the shipped hit/H curve does exactly that (-0.509 at 40 -> -0.254 at
         41 -> -0.161 at 42, n = 31/14/12), as do pit/SP|fin (+0.010 at 38,
         +0.119 at 39) and pit/RP|fin (positive from 24 through 33).
  A3   : A1 + A2.
  C2   : ZERO-INFORMATION CONTROL for A2. Identical edit magnitudes, applied at
         a RANDOM permutation of the same curve's ages instead of in age order.
         Same marginal perturbation, no aging information. If C2 scores like
         A2 there is no result.

METRIC  forward-chained pooled |pred - act| over h1..h5, absent season = 0,
        exactly proj_eval's contract. Effect = MAE(base) - MAE(arm); positive
        favours the arm. Reported per horizon and pooled.
FLOOR   paired CLUSTER bootstrap over players, resampling the pool that both
        FITS the curves and is SCORED, refit per draw per arm. MDE95 = 1.96*sd.
"""
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fa_market as fm  # noqa: E402
import fa_projection as fp  # noqa: E402

H = 5
NGUARD = 25
MONO_FROM = 31
BASES = [2014, 2015, 2016, 2017, 2018, 2019, 2021]
SEED = 20260725


def transform(curves: dict, arm: str, rng=None) -> dict:
    if arm == "base":
        return curves
    import copy
    c = copy.deepcopy(curves)
    for side in ("hit", "pit"):
        for role, comps in c[side].items():
            for comp in ("war_rate", "pt"):
                cur = comps.get(comp)
                if not cur:
                    continue
                if arm in ("A1", "A3", "C1"):
                    thin = [k for k in cur if cur[k].get("n", 0) < NGUARD]
                    if arm == "C1":
                        # ZERO-INFORMATION CONTROL for A1: drop the SAME NUMBER
                        # of cells, chosen at random instead of by pair count.
                        allk = sorted(cur.keys(), key=int)
                        thin = ([] if not thin else
                                list(rng.choice(allk, size=min(len(thin), len(allk)),
                                                replace=False)))
                    for a in thin:
                        del cur[a]
                    ages = sorted(int(a) for a in cur)
                    for a in ages:            # re-smooth on the surviving cells
                        vals = [cur[str(x)]["delta"] for x in (a - 1, a, a + 1)
                                if str(x) in cur]
                        cur[str(a)]["delta_smooth"] = sum(vals) / len(vals)
            cur = comps.get("war_rate")
            if not cur:
                continue
            if arm in ("A2", "A3", "C2"):
                ages = sorted(int(a) for a in cur)
                tail = [a for a in ages if a >= MONO_FROM]
                if len(tail) < 2:
                    continue
                vals = [cur[str(a)].get("delta_smooth", cur[str(a)]["delta"]) for a in tail]
                new, run = [], vals[0]
                for v in vals:
                    run = min(run, v)
                    new.append(run)
                edits = [n - v for n, v in zip(new, vals)]      # <= 0 everywhere
                if arm == "C2":
                    edits = list(rng.permutation(edits))        # same edits, random ages
                for a, v, e in zip(tail, vals, edits):
                    cur[str(a)]["delta_smooth"] = v + e
    return c


def score(corpus, by_player, war_actual, bases, arms, rng=None,
          player_filter=None):
    """{arm: {h: (sum_abs_err, n)}} forward-chained over `bases`."""
    league = corpus["league"]
    acc = {a: defaultdict(lambda: [0.0, 0]) for a in arms}
    for B in bases:
        base_curves = fp.fit_aging_curves(corpus, max_season=B - 1, write=False)
        war_map = fp.fit_war_map(corpus, max_season=B - 1)
        cur = {a: transform(base_curves, a, rng) for a in arms}
        for side in ("hit", "pit"):
            for mlbam, seasons in by_player[side].items():
                if player_filter is not None and mlbam not in player_filter:
                    continue
                hist = [seasons[t] for t in (B - 1, B - 2, B - 3) if t in seasons]
                if not hist:
                    continue
                age_row = next((h for h in hist if h.get("age")), None)
                if age_row is None:
                    continue
                age = age_row["age"] + (B - age_row["season"])
                for arm in arms:
                    path = fm.contract_war_path(hist, side, B, H, age, cur[arm],
                                                war_map, league, use_ml=False)
                    if path is None:
                        continue
                    for h in range(1, H + 1):
                        target = B + h - 1
                        if target > corpus["last"] - 1:
                            continue
                        act = war_actual.get((mlbam, target), 0.0)
                        cell = acc[arm][h]
                        cell[0] += abs(path["war_by_year"][h - 1] - act)
                        cell[1] += 1
    return acc


def pooled(acc_arm):
    s = sum(v[0] for v in acc_arm.values())
    n = sum(v[1] for v in acc_arm.values())
    return s / n if n else float("nan")


def index_corpus(corpus):
    by_player = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
    war_actual = {}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r
                if r.get("war") is not None:
                    k = (r["mlbam"], r["season"])
                    war_actual[k] = war_actual.get(k, 0.0) + r["war"]
    return by_player, war_actual


def main():
    draws = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    arms = (["base", "A1", "A2", "A3", "C2"] if draws <= 0
            else ["base", "A1", "A2", "A3"])
    rng = np.random.default_rng(SEED)
    corpus = fp.build_corpus()
    by_player, war_actual = index_corpus(corpus)

    t0 = time.time()
    acc = score(corpus, by_player, war_actual, BASES, arms, rng)
    print("point estimate, %.0fs" % (time.time() - t0))
    print(f"{'arm':<6} {'pooled MAE':>11} {'delta':>9}  " +
          "  ".join(f"h{h}" for h in range(1, H + 1)))
    p_base = pooled(acc["base"])
    point = {}
    for a in arms:
        p = pooled(acc[a])
        point[a] = p
        per = "  ".join(f"{acc[a][h][0]/acc[a][h][1]:.4f}" for h in range(1, H + 1))
        print(f"{a:<6} {p:>11.5f} {p_base-p:>9.5f}  {per}")
    print("n per horizon:", {h: acc["base"][h][1] for h in range(1, H + 1)})

    if draws <= 0:
        json.dump({"point": point}, open(ROOT / "tools" / "_am_proj_out_aging.json", "w"), indent=1)
        return

    # paired cluster bootstrap: resample PLAYERS; the resampled pool both fits
    # the curves and is scored; refit per draw per arm.
    players = {s: sorted(by_player[s].keys()) for s in ("hit", "pit")}
    boot = {a: [] for a in arms if a != "base"}
    for d in range(draws):
        t1 = time.time()
        keep = {s: set(rng.choice(players[s], size=len(players[s]), replace=True))
                for s in ("hit", "pit")}
        sub = {"first": corpus["first"], "last": corpus["last"],
               "league": corpus["league"],
               "hit": [r for r in corpus["hit"] if r.get("mlbam") in keep["hit"]],
               "pit": [r for r in corpus["pit"] if r.get("mlbam") in keep["pit"]]}
        bp, wa = index_corpus(sub)
        a_d = score(sub, bp, wa, BASES, arms, rng)
        pb = pooled(a_d["base"])
        for a in boot:
            boot[a].append(pb - pooled(a_d[a]))
        if d < 3 or d % 10 == 0:
            print(f"  draw {d} {time.time()-t1:.0f}s " +
                  " ".join(f"{a}={boot[a][-1]:+.5f}" for a in boot))
    out = {"point": point, "draws": draws, "boot": {}}
    for a, v in boot.items():
        v = np.asarray(v)
        out["boot"][a] = {"mean": float(v.mean()), "sd": float(v.std(ddof=1)),
                          "mde95": float(1.96 * v.std(ddof=1)),
                          "ci95": [float(np.percentile(v, 2.5)),
                                   float(np.percentile(v, 97.5))],
                          "p_pos": float((v > 0).mean())}
        b = out["boot"][a]
        print(f"{a:<4} mean {b['mean']:+.5f} sd {b['sd']:.5f} "
              f"MDE95 {b['mde95']:.5f} CI95 [{b['ci95'][0]:+.5f},{b['ci95'][1]:+.5f}] "
              f"P(+) {b['p_pos']:.3f}")
    json.dump(out, open(ROOT / "tools" / "_am_proj_out_aging.json", "w"), indent=1)


if __name__ == "__main__":
    main()
