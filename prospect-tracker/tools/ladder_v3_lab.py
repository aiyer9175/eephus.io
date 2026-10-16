# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The one read of docs/ewar/LADDER_V3_GATE.md: the corrected re-read of the
position-switcher ladder (v3) against an all-zero fielding ladder, v1, scaled
v1 and the FanGraphs table, with a planted-ladder recovery check.

    python tools/ladder_v3_lab.py --dry-run   # the whole path on the v2 lab's
                                              # centred fixtures (nothing real
                                              # is fitted or scored)
    python tools/ladder_v3_lab.py --read      # THE read: runs once (gate part 8)

The read writes data/positional_ladder_v3_eval.json (the record the Library
reads). The fitting, scoring and simulation code is ladder_v3.py.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import ladder_v2 as L2  # noqa: E402
import ladder_v3 as L3  # noqa: E402
import ladder_v2_lab as lab2  # noqa: E402

GATE = "docs/ewar/LADDER_V3_GATE.md"
REGISTERED_COMMIT = "e283249d"
FOLDS = tuple(range(2016, 2027))
ALL_SEASONS = set(FOLDS)
BOOT_SEED = 20261015
BOOT_DRAWS = 2000
CI_SEED = 11
CI_DRAWS = 400
SCALES = (0.25, 0.5, 0.75, 1.0, 1.25)


def _r(x, nd=4):
    return None if x is None else round(float(x), nd)


def _boot(loss, a, b, sel=None, draws=BOOT_DRAWS):
    t = L2.cluster_boot(loss, a, b, sel=sel, draws=draws, seed=BOOT_SEED)
    if t is None:
        return None
    return {"dmae": _r(t["dmae"]), "ci95": [_r(x) for x in t["ci95"]],
            "dmse": _r(t["dmse"]), "dmse_ci95": [_r(x) for x in t["dmse_ci95"]],
            "n_rows": t["n_rows"], "n_players": t["n_players"]}


def _wm(players, cnt):
    """Per-row bootstrap multiplier: the draw count of the row's player."""
    pa = np.asarray(players, dtype=np.int64)
    c = np.asarray(cnt, dtype=float)

    def wm(ms):
        ms = np.asarray(ms, dtype=np.int64)
        i = np.clip(np.searchsorted(pa, ms), 0, len(pa) - 1)
        return np.where(pa[i] == ms, c[i], 0.0)
    return wm


def run_sim(recs, e9, seeds, sel=0.0, fam=0.0, log=print) -> dict:
    per = {}
    for sd in seeds:
        sim, G, _q = L3.simulate(recs, e9, sd, sel=sel, fam=fam)
        per[sd] = L3.recovery(sim, G, e9, ALL_SEASONS)
        log(f"  sim seed {sd} sel {sel} fam {fam}: ratios {per[sd]['ratios']}")
    keys = list(per[seeds[0]]["ratios"])
    mean = {}
    for p in keys:
        v = [per[s]["ratios"][p] for s in seeds if per[s]["ratios"].get(p) is not None]
        mean[p] = _r(np.mean(v)) if len(v) == len(seeds) else None
    return {"seeds": list(seeds), "sel": sel, "fam": fam, "per_seed": per, "mean_ratio": mean}


def sim_power(recs, e9, seed, draws, log=print) -> dict:
    """On one simulated set, the part 4 scoring of the true G against zero."""
    sim, G, q = L3.simulate(recs, e9, seed)
    rows = L3.build_rows(L3.centre_savant(sim))
    Gl = {p: G.get(p, q[p]) for p in L2.LADDER9}
    Gl["DH"] = q["DH"]
    Gl = L2.recentre(Gl, e9)
    zero = {p: (Gl[p] if p in ("C", "DH") else 0.0) for p in L2.LADDER9}
    loss = []
    for t in FOLDS:
        lr, _a2 = L3.score_rows(rows, {"G": Gl, "zero": zero}, t, ALL_SEASONS - {t})
        loss.extend(lr)
    sm = L2.summarize(loss, ["G", "zero"])
    out = {"seed": seed, "mae": {k: _r(v["mae"]) for k, v in sm.items() if v},
           "zero_minus_G": _boot(loss, "zero", "G", draws=draws)}
    log(f"  sim power (seed {seed}): {json.dumps(out)}")
    return out


def run(recs_raw: dict, e9: dict, v1_served: dict, v2_vec, boot_draws: int, ci_draws: int,
        sim_seeds=L3.SIM_SEEDS, log=print) -> dict:
    t0 = time.time()
    recs = L3.centre_savant(recs_raw)
    rows = L3.build_rows(recs)
    reg = L3.regulars(recs)
    counts = {s: {"across": int(len(R.A["m"])), "across_switch": int(R.A["switch"].sum()),
                  "with_earlier": int((R.A["miss"] == 0).sum()), "within": int(len(R.B["m"])),
                  "season_rows": int(len(R.S["m"]))}
              for s, R in rows.items()}
    counts["regulars"] = int(len(reg["m"]))
    log(f"rows: {json.dumps(counts)}")
    v1s = L2.recentre(v1_served, e9)
    fgtab = L2.fg_table_ladder(e9)

    loss, loss2, folds = [], [], {}
    for t in FOLDS:
        train = ALL_SEASONS - {t}
        v1_t = L2.fit_inversion(recs, train, e9)
        v3_t, sh_t, info_t = L3.fit_v3(rows, reg, e9, v1_t, train, drop=t)
        off_t = L3.offense(reg, train, e9)
        c_t = None
        if off_t is not None and v1_t is not None:
            c_t = dict(off_t)
            c_t["C"] = L3.carry_c(c_t, v1_t, e9)
            c_t = L2.recentre(c_t, e9)
        ladders = {"v3": v3_t, "v1": v1_t, "fg_table": fgtab, "offense": c_t,
                   "v3_shapes_on_zero": sh_t, "v2_as_read": v2_vec}
        if v3_t is not None:
            ladders["zero"] = {p: (v3_t[p] if p in ("C", "DH") else 0.0) for p in L2.LADDER9}
        for s in SCALES:
            ladders[f"v1_x{s}"] = (None if v1_t is None
                                   else {p: s * v1_t[p] for p in L2.LADDER9})
        lr, lr2 = L3.score_rows(rows, ladders, t, train)
        loss.extend(lr)
        loss2.extend(lr2)
        folds[t] = {"n_rows": len(lr), "ladders": {k: L3.ladder_round(v, 3) for k, v in ladders.items()},
                    "v3_info": {k: v for k, v in (info_t or {}).items() if k != "fits"},
                    "v3_movers": {g: {s: (f or {}).get("n_movers") for s, f in fs.items()}
                                  for g, fs in (info_t or {}).get("fits", {}).items()}}
        log(f"fold {t}: {len(lr)} scored rows, {time.time() - t0:.0f}s")

    names = ["v3", "zero", "v1", "fg_table", "offense", "v3_shapes_on_zero", "v2_as_read"] + \
        [f"v1_x{s}" for s in SCALES]
    names = [n for n in names if loss and all(n in r[4] for r in loss)]
    is_across = (lambda r: r[2] == "across")  # noqa: E731
    scores = {
        "pooled": L2.summarize(loss, names),
        "across_ew3_23": L2.summarize(loss, names, is_across),
        "within_savant": L2.summarize(loss, names, lambda r: r[2] == "within"),
        "by_source": {s: L2.summarize(loss, names, (lambda r, s=s: r[1] == s)) for s in L2.SOURCES},
        "by_fold": {t: L2.summarize(loss, ["v3", "zero", "v1"], (lambda r, t=t: r[5] == t))
                    for t in FOLDS},
        "a2_predictor_pooled": L2.summarize(loss2, names),
    }
    boot = lambda a, b, sel=None, L=loss: _boot(L, a, b, sel, boot_draws)  # noqa: E731
    tests = {
        "zero_minus_v3_pooled": boot("zero", "v3"),
        "v1_minus_v3_pooled": boot("v1", "v3"),
        "zero_minus_v3_across": boot("zero", "v3", is_across),
        "zero_minus_v3_within": boot("zero", "v3", lambda r: r[2] == "within"),
        "v1_minus_zero_pooled": boot("v1", "zero"),
        "fg_table_minus_v3_pooled": boot("fg_table", "v3"),
        "offense_minus_v3_pooled": boot("offense", "v3"),
        "zero_minus_v3_shapes_on_zero_pooled": boot("zero", "v3_shapes_on_zero"),
        "zero_minus_v2_as_read_pooled": boot("zero", "v2_as_read"),
        "zero_minus_v3_by_source": {s: boot("zero", "v3", (lambda r, s=s: r[1] == s))
                                    for s in L2.SOURCES},
        "a2_zero_minus_v3_pooled": boot("zero", "v3", None, loss2),
        "a2_v1_minus_v3_pooled": boot("v1", "v3", None, loss2),
    }
    log(f"scoring done, {time.time() - t0:.0f}s")

    log("simulation ...")
    sim = {"base": run_sim(recs_raw, e9, list(sim_seeds), log=log),
           "stress_selection": run_sim(recs_raw, e9, list(sim_seeds), sel=L3.SIM_STRESS, log=log),
           "stress_familiarity": run_sim(recs_raw, e9, list(sim_seeds), fam=L3.SIM_STRESS, log=log),
           "power": sim_power(recs_raw, e9, sim_seeds[0], boot_draws, log=log)}
    log(f"simulation done, {time.time() - t0:.0f}s")

    # ------------------------------------------------- the pass rule (part 7)
    pm = {n: (v or {}).get("mae") for n, v in scores["pooled"].items()}
    z, v = tests["zero_minus_v3_pooled"], tests["v1_minus_v3_pooled"]
    za = tests["zero_minus_v3_across"]
    ratios = sim["base"]["mean_ratio"]
    c1 = bool(z and z["ci95"][0] > 0)
    c2 = bool(v and v["ci95"][0] > 0)
    c3 = bool(pm.get("v3") is not None and all(
        pm.get(k) is not None and pm["v3"] < pm[k] for k in [f"v1_x{s}" for s in SCALES] + ["fg_table"]))
    c4 = bool(za and za["ci95"][1] >= 0)
    c5 = bool(ratios and all(r is not None and L3.RECOVERY_LO <= r <= L3.RECOVERY_HI
                             for r in ratios.values()))
    passed = c1 and c2 and c3 and c4 and c5
    verdict = {
        "1_beats_zero": c1, "2_beats_v1": c2, "3_below_scaled_v1_and_fg_table": c3,
        "4_not_worse_than_zero_next_season": c4, "5_recovers_planted_ladder": c5,
        "passed": passed,
        "position_fit": "v1 (unchanged; v3 built dark, owner question)" if passed else "v1 (v3 failed)",
        "rule": ("v3 passes when it beats the zero ladder and the v1 refit with CI95 lower bounds "
                 "above 0, has lower pooled error than v1 scaled by 0.25 to 1.25 and the FanGraphs "
                 "table, is not significantly worse than zero on the next-season rows, and "
                 "recovers each within-group gap of a planted ladder at 0.80 to 1.25 of its size"),
    }
    log(f"verdict: {json.dumps(verdict)}")

    # ------------------------------------------------------- recorded fit
    log("final fit on 2016-2026 ...")
    v3_all, sh_all, info_all, fits_all = L3.fit_v3(rows, reg, e9, v1s, ALL_SEASONS, return_fits=True)
    off_all = L3.offense(reg, ALL_SEASONS, e9)
    v1_1626 = L2.fit_inversion(recs, ALL_SEASONS, e9)
    log(f"bootstrap CI ({ci_draws} draws) ...")
    ci, ci_n = {}, 0
    if v3_all is not None and ci_draws:
        rng = np.random.default_rng(CI_SEED)
        players = sorted({int(m) for R in rows.values() for arr in (R.A["m"], R.B["m"]) for m in arr}
                         | {int(m) for m in reg["m"]})
        draws = []
        for _ in range(ci_draws):
            cnt = rng.multinomial(len(players), np.full(len(players), 1.0 / len(players)))
            Lb, _s, _i = L3.fit_v3(rows, reg, e9, v1s, ALL_SEASONS, wmult=_wm(players, cnt))
            if Lb is not None:
                draws.append([Lb[p] for p in L2.LADDER9])
        draws = np.array(draws)
        ci_n = len(draws)
        if ci_n:
            ci = {p: [_r(np.percentile(draws[:, i], 2.5), 2), _r(np.percentile(draws[:, i], 97.5), 2)]
                  for i, p in enumerate(L2.LADDER9)}
    gaps = {}
    if v3_all is not None:
        gaps = {"IF_vs_SS": {p: _r(v3_all[p] - v3_all["SS"], 2) for p in ("1B",) + L3.IF3},
                "OF_vs_CF": {p: _r(v3_all[p] - v3_all["CF"], 2) for p in L3.OF3},
                "IF_level_minus_OF_level": _r(L3.group_level(v3_all, L3.IF3, e9)
                                               - L3.group_level(v3_all, L3.OF3, e9), 2)}
    comparison = {
        "positions": list(L2.LADDER9),
        "columns": {
            "v3_2016_2026": L3.ladder_round(v3_all, 2),
            "v1_served": L3.ladder_round(v1s, 2),
            "v1_refit_2016_2026": L3.ladder_round(v1_1626, 2),
            "offense_anchor_2016_2026": L3.ladder_round(off_all, 2),
            "fg_table_rescaled": L3.ladder_round(fgtab, 2),
            "v2_as_read": L3.ladder_round(v2_vec, 2),
        },
        "note": ("every column recentred on one exposure vector (gate part 5); v3's C is carried "
                 "from v1 and its group levels, 1B and DH are the offense anchor's"),
    }
    out = {
        "model": "positional_ladder_v3_eval",
        "gate": GATE,
        "registered_commit": REGISTERED_COMMIT,
        "amended_commit": "b4675e45",
        "generated_at": _dt.date.today().isoformat(),
        "read_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "unit_innings": L2.UNIT_INN,
        "exposure_share": e9,
        "seeds": {"bootstrap": BOOT_SEED, "draws": boot_draws, "ci": CI_SEED, "ci_draws": ci_draws,
                  "sim": list(sim_seeds)},
        "row_counts": counts,
        "savant_league_rate_before_centring": L3.savant_league_rates(recs_raw, ALL_SEASONS),
        "verdict": verdict,
        "tests": tests,
        "scores": scores,
        "simulation": sim,
        "folds": folds,
        "comparison": comparison,
        "v3": {
            "values": L3.ladder_round(v3_all, 2),
            "ci95": ci, "ci_draws": ci_n, "ci_seed": CI_SEED,
            "gaps": gaps,
            "shapes": info_all.get("shapes"),
            "source_fits": info_all.get("fits"),
            "offense": info_all.get("offense"),
            "c_rule": "carried from v1: v1's offset to v1's exposure-weighted seven-position mean",
            "dh_rule": "the offense anchor; no scored row contains DH",
            "status": ("passed the re-read; built dark, Position Fit values with v1 until the owner "
                       "answers" if passed else "failed the re-read; not served, no ladder artifact"),
        },
        "runtime_s": round(time.time() - t0, 1),
    }
    return out


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.floating):
        return None if math.isnan(float(o)) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, float) and math.isnan(o):
        return None
    return o


def report(out: dict, log=print):
    t = out["tests"]

    def fm(d):
        if not d:
            return "n/a"
        return (f"{d['dmae']:+.4f} CI95 [{d['ci95'][0]:+.4f}, {d['ci95'][1]:+.4f}]  "
                f"rows {d['n_rows']} players {d['n_players']}")
    log("=" * 78)
    log("POSITIONAL LADDER v3 RE-READ (docs/ewar/LADDER_V3_GATE.md)")
    log("=" * 78)
    for k, d in t.items():
        if isinstance(d, dict) and "dmae" in d:
            log(f"  {k:<38} {fm(d)}")
    for s, d in (t.get("zero_minus_v3_by_source") or {}).items():
        log(f"  zero_minus_v3 [{s:<6}]               {fm(d)}")
    log("  MAE pooled: " + "  ".join(f"{n} {d['mae']:.4f}" for n, d in out["scores"]["pooled"].items() if d))
    sim = out["simulation"]
    for k in ("base", "stress_selection", "stress_familiarity"):
        log(f"  sim {k}: mean ratios {sim[k]['mean_ratio']}")
    log(f"  sim power: {json.dumps(sim['power'])}")
    log(f"  VERDICT: {json.dumps(out['verdict'])}")
    comp = out["comparison"]["columns"]
    log(f"  {'pos':<4}" + "".join(f"{k[:16]:>18}" for k in comp))
    for p in out["comparison"]["positions"]:
        log(f"  {p:<4}" + "".join(
            f"{(c or {}).get(p) if (c or {}).get(p) is not None else float('nan'):>18.2f}"
            for c in comp.values()))
    v3 = out["v3"]
    log(f"  v3 CI95: {v3['ci95']}")
    log(f"  v3 gaps: {v3['gaps']}")
    log(f"  shapes: {json.dumps(v3['shapes'])}")
    log(f"  source fits: {json.dumps(v3['source_fits'])}")


def v2_as_read(e9):
    p = ROOT / "data" / "positional_ladder_v2_eval.json"
    if not p.exists():
        return None
    ev = json.loads(p.read_text(encoding="utf-8"))
    vals = (ev.get("ladder_artifact") or {}).get("values")
    return L2.recentre(vals, e9) if vals else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--read", action="store_true")
    ap.add_argument("--out", type=Path, default=None, help="dry-run output directory")
    a = ap.parse_args()
    if a.dry_run:
        recs, true_l, e9 = lab2.fixture_records()
        # null cells on top of the v2 fixtures: a source missing a season, and
        # earlier seasons absent for the first two seasons of every player
        print(f"fixtures: {len(recs)} records; planted target {L3.ladder_round(true_l, 2)}")
        out = _clean(run(recs, e9, true_l, None, boot_draws=50, ci_draws=6, sim_seeds=(7, 8)))
        report(out)
        if a.out:
            a.out.mkdir(parents=True, exist_ok=True)
            (a.out / "dry_run_eval.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("dry run: clean")
        return 0
    import scrapers
    with scrapers.cache_only():
        recs = lab2.load_records()
    v1, e9, gen, seasons = lab2.served_v1()
    print(f"read: {len(recs)} records; served v1 {gen} {seasons}")
    out = _clean(run(recs, e9, v1, v2_as_read(e9), boot_draws=BOOT_DRAWS, ci_draws=CI_DRAWS))
    out["v1_served_artifact"] = {"generated_at": gen, "seasons": seasons}
    report(out)
    L3.write_eval(out)
    print(f"wrote {L3.EVAL_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
