# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Projections-lane measurement harness (2026-07-24).

Scores an ARM of the champion projection engine against the shipped engine
under docs/EFV_GATE_STANDARD.md:

  1. PAIRED CLUSTER BOOTSTRAP resampling the whole player pool (train AND
     test) with a REFIT of the aging curves + WAR map on every draw.
  2. A ZERO-INFORMATION CONTROL beside every claim (the arm's own
     perturbation, row-permuted across players so the marginal distribution
     is identical and the information is gone).
  3. A PERMUTATION NULL BAND for the same statistic.
  4. The effect averaged over >= 4 independent time splits (one per base
     season), reported per split as well as pooled.

Arms
  ipage   pitcher ip_proj follows the AGED BF exposure (EEPHUS_PIT_IP_AGE)
  lgpit   league hitter means exclude pitchers batting (corpus-level)

Nothing here writes to the repo except the requested --out artifact.
Run: python tools/proj_lane_lab.py --arm ipage --draws 200
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fa_market as fm            # noqa: E402
import fa_projection as fp        # noqa: E402

HORIZONS = 5
SCRATCH = Path(os.environ.get("PROJ_LAB_SCRATCH") or (ROOT / ".cache"))


# --------------------------------------------------------------------------- #
# corpora
# --------------------------------------------------------------------------- #

def load_corpus(path: Path | None) -> dict:
    if path is None:
        return fp.build_corpus()
    import pickle
    with open(path, "rb") as fh:
        return pickle.load(fh)


def contaminate_league(corpus: dict) -> dict:
    """Rebuild the league HITTER block WITH pitchers batting folded into the
    denominators - the pre-fix (BUG-5) state, reconstructed on the SAME
    corpus so the lgpit arm is not confounded with corpus freshness."""
    import fa_sources
    out = copy.deepcopy(corpus)
    a = fp._pcfg()["assembly"]
    raw = fa_sources.fetch_statsapi_season_range(corpus["first"], corpus["last"])
    for season in range(corpus["first"], corpus["last"] + 1):
        lg = out["league"].get(season)
        if not lg or not lg.get("woba"):
            continue
        tot = {k: 0.0 for k in ("pa", "ab", "h", "d", "t", "hr", "bb", "so",
                                "hbp", "sf", "r")}
        for s in raw.get((season, "hitting"), []):
            st = s.get("stat") or {}
            pa = fp._f(st.get("plateAppearances"))
            if pa <= 0:
                continue
            for k, key in (("pa", "plateAppearances"), ("ab", "atBats"), ("h", "hits"),
                           ("d", "doubles"), ("t", "triples"), ("hr", "homeRuns"),
                           ("bb", "baseOnBalls"), ("so", "strikeOuts"),
                           ("hbp", "hitByPitch"), ("sf", "sacFlies"), ("r", "runs")):
                tot[k] += fp._f(st.get(key))
        if tot["pa"] <= 0:
            continue
        w = a["woba_weights"]
        singles = tot["h"] - tot["d"] - tot["t"] - tot["hr"]
        num = (w["bb"] * tot["bb"] + w["hbp"] * tot["hbp"] + w["single"] * singles
               + w["double"] * tot["d"] + w["triple"] * tot["t"] + w["hr"] * tot["hr"])
        lg.update({
            "_total_pa": tot["pa"], "woba": num / tot["pa"],
            "r_pa": tot["r"] / tot["pa"],
            "k_pct": tot["so"] / tot["pa"], "bb_pct": tot["bb"] / tot["pa"],
            "iso": (tot["d"] + 2 * tot["t"] + 3 * tot["hr"]) / tot["ab"],
            "babip": (tot["h"] - tot["hr"]) / (tot["ab"] - tot["so"] - tot["hr"] + tot["sf"]),
            "hr_pa": tot["hr"] / tot["pa"],
        })
    return out


# --------------------------------------------------------------------------- #
# scoring
# --------------------------------------------------------------------------- #

def index_corpus(corpus: dict):
    by_player = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
    war_actual = fp.war_actual_map(corpus)  # the ONE label (809902c6); never sum r['war'] across sides
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r
    return by_player, war_actual


def score_rows(corpus, by_player, war_actual, bases, arm_on: bool,
               fits: dict | None = None, permute_seed: int | None = None):
    """One pass over (base, player, horizon). Returns rows
    (base, side, mlbam, h, pred, act). ``permute_seed`` builds the
    ZERO-INFORMATION control: the arm is applied, but the AGE the arm's
    perturbation keys on is row-permuted across players within the base
    season, so the perturbation has the same marginal size and no
    information about who is actually old."""
    league = corpus["league"]
    rows = []
    prev = os.environ.get("EEPHUS_PIT_IP_AGE")
    os.environ["EEPHUS_PIT_IP_AGE"] = "1" if arm_on else "0"
    try:
        for B in bases:
            if fits is not None and B in fits:
                curves, war_map = fits[B]
            else:
                # NEVER fp.fitted_models(..., use_cache=True) here: the cache key
                # is (max_season, first, last) and knows nothing about the rows,
                # so a corpus VARIANT would both read the champion's fits and
                # overwrite them. Fit in-process, cache nothing.
                curves, war_map = fp.fitted_models(corpus, B - 1, use_cache=False)
            for side in ("hit", "pit"):
                cand = []
                for mlbam, seasons in by_player[side].items():
                    hist = [seasons[t] for t in (B - 1, B - 2, B - 3) if t in seasons]
                    if not hist:
                        continue
                    ar = next((h for h in hist if h.get("age")), None)
                    if ar is None:
                        continue
                    cand.append((mlbam, hist, ar["age"] + (B - ar["season"])))
                ages = [c[2] for c in cand]
                if permute_seed is not None:
                    random.Random(permute_seed + B * 7 + (0 if side == "hit" else 1)).shuffle(ages)
                for (mlbam, hist, true_age), use_age in zip(cand, ages):
                    proj = fp.project_player(hist, side, B, curves, league, true_age)
                    if proj is None:
                        continue
                    if arm_on and permute_seed is not None and side == "pit":
                        # placebo: re-derive ip_proj from a pt aged at a
                        # PERMUTED age (same marginal delta, no information)
                        base_pt = proj["pt_proj"] - fp.curve_delta(curves, side, proj["role"], "pt", true_age)
                        pt2 = max(0.0, base_pt + fp.curve_delta(curves, side, proj["role"], "pt", use_age))
                        proj = dict(proj)
                        proj["ip_proj"] = round(pt2 / 4.3, 1)
                        fipc = fp._league_recent(league, B, "fip_constant") or 3.1
                        pt = proj["pt_proj"]
                        proj["fip_proj"] = round(
                            (13 * proj["hr_bf"] * pt + 3 * (proj["bb_pct"] * pt + 0.008 * pt)
                             - 2 * proj["k_pct"] * pt) / max(proj["ip_proj"], 1) + fipc, 2)
                    war1 = fp.war_from_projection(proj, side, war_map, league, B)
                    role = fp.profile_role(hist, side, proj["role"], league)
                    path = fm._decay_path(war1, proj["pt_proj"], side, role, true_age, curves)
                    for h in range(1, HORIZONS + 1):
                        target = B + h - 1
                        if target > corpus["last"] - 1:
                            continue
                        rows.append((B, side, mlbam, h, path[h - 1],
                                     war_actual.get((mlbam, target), 0.0)))
    finally:
        if prev is None:
            os.environ.pop("EEPHUS_PIT_IP_AGE", None)
        else:
            os.environ["EEPHUS_PIT_IP_AGE"] = prev
    return rows


def mae_by(rows, side=None, h=None):
    sel = [r for r in rows
           if (side is None or r[1] == side) and (h is None or r[3] == h)]
    if not sel:
        return None, 0
    return sum(abs(r[4] - r[5]) for r in sel) / len(sel), len(sel)


def bias_by(rows, side=None, h=None):
    sel = [r for r in rows
           if (side is None or r[1] == side) and (h is None or r[3] == h)]
    if not sel:
        return None, 0
    return sum(r[4] - r[5] for r in sel) / len(sel), len(sel)


# --------------------------------------------------------------------------- #
# bootstrap
# --------------------------------------------------------------------------- #

def resample_corpus(corpus: dict, rng: random.Random) -> dict:
    """Cluster bootstrap over PLAYERS: draw mlbams with replacement and
    re-key duplicates so both the FIT and the SCORE see the same resampled
    pool (a test-only bootstrap understates sd 1.6-1.8x)."""
    ids = sorted({r["mlbam"] for side in ("hit", "pit") for r in corpus[side]
                  if r.get("mlbam")})
    draw = [ids[rng.randrange(len(ids))] for _ in range(len(ids))]
    counts: dict[int, int] = defaultdict(int)
    for m in draw:
        counts[m] += 1
    out = {"league": corpus["league"], "first": corpus["first"], "last": corpus["last"]}
    for side in ("hit", "pit"):
        rows = []
        for r in corpus[side]:
            m = r.get("mlbam")
            n = counts.get(m, 0) if m else 0
            for c in range(n):
                if c == 0:
                    rows.append(r)
                else:
                    rr = dict(r)
                    rr["mlbam"] = -(m * 16 + c)      # distinct synthetic id
                    rows.append(rr)
        out[side] = rows
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=("ipage", "lgpit", "lgsplit"), required=True)
    ap.add_argument("--bases", default="2014,2015,2016,2017,2018,2019,2021")
    ap.add_argument("--draws", type=int, default=200)
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--seed", type=int, default=20260724)
    ap.add_argument("--out", default=None)
    ap.add_argument("--draws-out", default=None,
                    help="dump the raw per-draw deltas here (chunked runs)")
    ap.add_argument("--draws-in", default=None,
                    help="comma-separated raw-draw dumps to pool instead of "
                         "running the bootstrap in this process")
    args = ap.parse_args()
    bases = [int(b) for b in args.bases.split(",")]
    corpus = load_corpus(Path(args.corpus) if args.corpus else None)

    if args.arm == "ipage":
        c_base, c_arm = corpus, corpus
        arm_on_base, arm_on_arm = False, True
    elif args.arm == "lgpit":
        c_base, c_arm = contaminate_league(corpus), corpus
        arm_on_base = arm_on_arm = False
    else:
        # lgsplit: the league dict serves TWO different jobs. The component
        # means (k_pct/bb_pct/iso/babip/hr_pa) are the Marcel REGRESSION TARGET
        # for a hitter, so they want the non-pitcher population; woba and r_pa
        # are the wRAA / wRC+ BASELINE, and bWAR's run environment is the
        # all-batters one. Fix the first, leave the second.
        c_base = contaminate_league(corpus)
        c_arm = copy.deepcopy(corpus)
        for s, lg in c_arm["league"].items():
            src = c_base["league"].get(s) or {}
            for k in ("woba", "r_pa"):
                if src.get(k) is not None:
                    lg[k] = src[k]
        arm_on_base = arm_on_arm = False

    res: dict = {"arm": args.arm, "bases": bases, "draws": args.draws,
                 "corpus": str(args.corpus or fp.CORPUS_CACHE)}

    # ---- point estimate, full pool -----------------------------------------
    idx_b = index_corpus(c_base)
    idx_a = index_corpus(c_arm)
    t0 = time.time()
    rows_b = score_rows(c_base, *idx_b, bases, arm_on_base)
    rows_a = score_rows(c_arm, *idx_a, bases, arm_on_arm)
    print(f"point pass {time.time()-t0:.1f}s  n={len(rows_b)}/{len(rows_a)}")
    point = {}
    for label, side in (("pooled", None), ("hit", "hit"), ("pit", "pit")):
        blk = {}
        for h in range(1, HORIZONS + 1):
            mb, n = mae_by(rows_b, side, h)
            ma, _ = mae_by(rows_a, side, h)
            bb, _ = bias_by(rows_b, side, h)
            ba, _ = bias_by(rows_a, side, h)
            if mb is None:
                continue
            blk[h] = {"n": n, "mae_base": round(mb, 5), "mae_arm": round(ma, 5),
                      "d_mae": round(ma - mb, 5),
                      "bias_base": round(bb, 5), "bias_arm": round(ba, 5)}
        point[label] = blk
    res["point"] = point

    # ---- per-time-split (>= 4 independent splits) ---------------------------
    splits = {}
    for B in bases:
        blk = {}
        for label, side in (("pooled", None), ("pit", "pit")):
            rb = [r for r in rows_b if r[0] == B]
            ra = [r for r in rows_a if r[0] == B]
            mb, n = mae_by(rb, side)
            ma, _ = mae_by(ra, side)
            if mb is None:
                continue
            blk[label] = {"n": n, "d_mae": round(ma - mb, 5)}
        splits[B] = blk
    res["by_split"] = splits

    # ---- zero-information control ------------------------------------------
    if args.arm == "ipage":
        rows_ctl = score_rows(c_arm, *idx_a, bases, True, permute_seed=args.seed)
        ctl = {}
        for label, side in (("pooled", None), ("pit", "pit")):
            blk = {}
            for h in range(1, HORIZONS + 1):
                mb, n = mae_by(rows_b, side, h)
                mc, _ = mae_by(rows_ctl, side, h)
                if mb is None:
                    continue
                blk[h] = {"n": n, "d_mae_control": round(mc - mb, 5)}
            ctl[label] = blk
        res["zero_info_control"] = ctl

    # ---- paired cluster bootstrap with refit --------------------------------
    rng = random.Random(args.seed)
    draws: dict[str, list[float]] = defaultdict(list)
    if args.draws_in:
        for f in args.draws_in.split(","):
            chunk = json.loads(Path(f.strip()).read_text(encoding="utf-8"))
            for k, v in chunk.items():
                draws[k].extend(v)
        args.draws = 0
    t0 = time.time()
    for d in range(args.draws):
        rc_a = resample_corpus(c_arm, rng)
        ib = index_corpus(rc_a)
        fits = {B: fp.fitted_models(rc_a, B - 1, use_cache=False) for B in bases}
        ra = score_rows(rc_a, *ib, bases, arm_on_arm, fits=fits)
        if args.arm == "ipage":
            rb = score_rows(rc_a, *ib, bases, arm_on_base, fits=fits)
        else:
            rc_b = dict(rc_a); rc_b["league"] = c_base["league"]
            fits_b = {B: fp.fitted_models(rc_b, B - 1, use_cache=False) for B in bases}
            rb = score_rows(rc_b, *ib, bases, arm_on_base, fits=fits_b)
        for label, side in (("pooled", None), ("pit", "pit"), ("hit", "hit")):
            for h in (1, 2, 3, 4, 5):
                mb, n = mae_by(rb, side, h)
                ma, _ = mae_by(ra, side, h)
                if mb is None:
                    continue
                draws[f"{label}:h{h}"].append(ma - mb)
            mb, _ = mae_by(rb, side)
            ma, _ = mae_by(ra, side)
            if mb is not None:
                draws[f"{label}:all"].append(ma - mb)
        if (d + 1) % 5 == 0:
            print(f"  draw {d+1}/{args.draws}  {time.time()-t0:.0f}s", flush=True)
            if args.draws_out:
                Path(args.draws_out).write_text(json.dumps(draws), encoding="utf-8")
    if args.draws_out and args.draws:
        Path(args.draws_out).write_text(json.dumps(draws), encoding="utf-8")
    boot = {}
    for k, v in draws.items():
        v = sorted(v)
        n = len(v)
        boot[k] = {"n_draws": n, "mean": round(sum(v) / n, 5),
                   "ci95": [round(v[int(0.025 * (n - 1))], 5),
                            round(v[int(0.975 * (n - 1))], 5)],
                   "sd": round((sum((x - sum(v) / n) ** 2 for x in v) / max(n - 1, 1)) ** 0.5, 5),
                   "p_improve": round(sum(1 for x in v if x < 0) / n, 3)}
    res["bootstrap"] = boot
    # MDE95 = the width the null band would have to clear (2 * sd of the paired delta)
    res["noise_floor_mde95"] = {k: round(1.96 * b["sd"], 5) for k, b in boot.items()}

    out = json.dumps(res, indent=1)
    print(out[:4000])
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
        print("wrote", args.out)


if __name__ == "__main__":
    main()
