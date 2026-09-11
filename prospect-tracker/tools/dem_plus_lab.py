# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DEM+ lab: the pre-registered forward validation of the fielding member of the
+stat family, HARNESS v2 (tools/plus_lab_harness.py). Every choice below was
fixed in docs/dem-plus-2026-09-11/DEM_PLUS_GATE.md before this file existed.

  k-fit  The shrink constants, refit on the pre-registered window (predictor
         seasons 2016 to 2018) with the positional_fit.fit_signal rule and
         compared against the values frozen into dem_plus.K_INN. A mismatch is a
         drift in the published series, reported, never silently re-frozen.

  X-D1   DEM+(Y) against the published fielding rate in Y+1, predictor seasons
         2021 to 2024 (outside the fit window). PASS needs: gap vs fielding
         percentage lo95 > 0, gap vs innings lo95 > 0, gap vs the raw unshrunk
         rate lo95 >= -0.01, and a zero-information twin (DEM+ permuted within
         season) that FAILS the fielding-percentage clause. v1 primary, v2 beside.

  X-D2   Innings-weighted 3-year DEM+ against 1-year on the same pairs.

Runs offline against the caches the exporter warms. All stochastic steps seeded.
Run: python tools/dem_plus_lab.py [--no-write]
"""
from __future__ import annotations

import json
import math
import os
import random
import statistics
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(os.environ.get("EEPHUS_ROOT") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import dem_plus  # noqa: E402
import defense_export as de  # noqa: E402
import plus_lab_harness as plh  # noqa: E402

DATA = ROOT / "data"
EVAL = DATA / "dem_plus_eval.json"
MULTI_EVAL = DATA / "dem_plus_multiyear_eval.json"

FIT_SEASONS = [2016, 2017, 2018]            # k-fit predictor seasons (outcomes to 2019)
SEASONS = [2021, 2022, 2023, 2024]          # X-D1 primary predictor seasons
SENS_SEASONS = [2016, 2017, 2018, 2019]     # in-sample sensitivity (inside the fit window)
MIN_INN_Y = 200.0
MIN_INN_NEXT = 300.0
FIT_MIN_INN = 300.0
FIT_MIN_SHARE = 0.8
FIT_MIN_PAIRS = 30
BOOT = 2000
SEED = 20260911
TAG_MIN_SEASONS = 2
TAG_MIN_INN = 1000.0

TARGET_V1 = "published fielding rate (fielding + framing per 1,000 innings) in Y+1, raw pooled"
TARGET_V2 = "published fielding rate in Y+1"


def _r4(v):
    return None if v is None else round(v, 4)


def load_season(y: int) -> dict:
    """MLBAM -> unrounded record for season Y, scored exactly as the board is."""
    res = de.score_season(y, log=lambda *_: None, file_red=False)
    if not res:
        return {}
    out = {}
    for f in res["fielders"]:
        if f.dem_plus_raw is None or f.rate is None:
            continue
        out[int(f.mlbam)] = {
            "dem_plus_raw": f.dem_plus_raw, "dem_plus": f.dem_plus,
            "rate": f.rate, "inn": f.inn, "fld_pct": dem_plus.fielding_pct(f),
            "prim": f.primary_pos, "name": f.name,
            "share": (float(f.inn_by_pos.get(f.primary_pos) or 0) / f.inn) if f.inn else 0.0,
            "c_share": (float(f.inn_by_pos.get("C") or 0) / f.inn) if f.inn else 0.0,
            "pinn": float(f.inn_by_pos.get(f.primary_pos) or 0),
        }
    print(f"  {y}: {len(out)} fielders scored (framing "
          f"{'on' if res['framing']['framing_available'] else 'OFF'})")
    return out


def k_fit(by_season: dict) -> dict:
    """The fit_signal rule on the pre-registered window, per position."""
    out = {}
    for p in dem_plus.DEF_POSITIONS:
        xs, px, py, hm = [], [], [], []
        for y in FIT_SEASONS:
            a, b = by_season.get(y) or {}, by_season.get(y + 1) or {}
            for mid, r in a.items():
                if r["prim"] != p or r["share"] < FIT_MIN_SHARE or r["pinn"] < FIT_MIN_INN:
                    continue
                xs.append(r["rate"])
                q = b.get(mid)
                if (q and q["prim"] == p and q["share"] >= FIT_MIN_SHARE
                        and q["pinn"] >= FIT_MIN_INN):
                    px.append(r["rate"]); py.append(q["rate"])
                    hm.append(2.0 / (1.0 / r["pinn"] + 1.0 / q["pinn"]))
        if len(px) < FIT_MIN_PAIRS:
            out[p] = {"n_pairs": len(px), "fallback": "positional_fit constant",
                      "k_inn": dem_plus.K_INN[p]}
            continue
        mx, my = sum(px) / len(px), sum(py) / len(py)
        cov = sum((a - mx) * (b - my) for a, b in zip(px, py))
        vx = sum((a - mx) ** 2 for a in px) ** 0.5
        vy = sum((b - my) ** 2 for b in py) ** 0.5
        r = cov / (vx * vy) if vx and vy else 0.0
        rc = min(max(r, 0.05), 0.95)
        hmm = statistics.mean(hm)
        out[p] = {"n": len(xs), "n_pairs": len(px), "yoy_r": round(r, 4),
                  "hm_inn": round(hmm, 0), "obs_sd": round(statistics.pstdev(xs), 3),
                  "k_inn": round(hmm * (1 - rc) / rc, 0)}
    drift = {p: {"frozen": dem_plus.K_INN[p], "refit": v["k_inn"]}
             for p, v in out.items() if abs(float(v["k_inn"]) - dem_plus.K_INN[p]) > 0.5}
    return {"window": FIT_SEASONS, "rule": ("positional_fit.fit_signal on single-position "
                                            "player-seasons (share >= 0.8, 300+ innings at "
                                            "the position both years)"),
            "by_position": out, "frozen": dict(dem_plus.K_INN),
            "drift_vs_frozen": drift, "matches_frozen": not drift}


def _pairs(by_season: dict, seasons: list, *, min_y=MIN_INN_Y, non_c=False):
    cols = {k: [] for k in ("dem", "raw", "pct", "inn", "tgt", "mid", "py", "oy")}
    dropped = 0
    for y in seasons:
        cur, nxt = by_season.get(y) or {}, by_season.get(y + 1) or {}
        for mid, a in cur.items():
            b = nxt.get(mid)
            if not b or a["inn"] < min_y or b["inn"] < MIN_INN_NEXT:
                continue
            if a["fld_pct"] is None:
                continue
            if non_c and (a["c_share"] > 0 or b["c_share"] > 0):
                continue
            if not plh.season_complete(y + 1):
                dropped += 1
                continue
            cols["dem"].append(a["dem_plus_raw"]); cols["raw"].append(a["rate"])
            cols["pct"].append(a["fld_pct"]); cols["inn"].append(a["inn"])
            cols["tgt"].append(b["rate"]); cols["mid"].append(mid)
            cols["py"].append(y); cols["oy"].append(y + 1)
    return cols, dropped


def _twin(cols: dict, seed: int) -> list:
    """DEM+ permuted across players within each predictor season."""
    rng = random.Random(seed)
    out = list(cols["dem"])
    by: dict = {}
    for i, y in enumerate(cols["py"]):
        by.setdefault(y, []).append(i)
    for y in sorted(by):
        idx = by[y]
        vals = [cols["dem"][i] for i in idx]
        rng.shuffle(vals)
        for i, v in zip(idx, vals):
            out[i] = v
    return out


def _dual(primary, baselines, cols, seed=SEED):
    tgt = cols["tgt"]
    tgt_v2 = plh.zscore_within(cols["oy"], tgt)
    rp1 = plh.spearman(primary, tgt)
    rp2 = plh.spearman(primary, tgt_v2)
    return {
        "v1": {"rho_primary": _r4(rp1),
               "rho_baselines": {k: _r4(plh.spearman(s, tgt)) for k, s in baselines.items()},
               "gap_ci": plh.iid_boot_gaps(primary, baselines, tgt, BOOT, seed)},
        "v2": {"rho_primary": _r4(rp2),
               "rho_baselines": {k: _r4(plh.spearman(s, tgt_v2)) for k, s in baselines.items()},
               "gap_ci": plh.cluster_boot_gaps(primary, baselines, tgt_v2, cols["mid"],
                                               cols["py"], BOOT, seed),
               "cluster": plh.cluster_summary(cols["mid"], cols["py"])},
    }


def _gate(res: dict, conv: str) -> dict:
    g = res[conv]["gap_ci"]
    c = {
        "beats_fld_pct": bool(g.get("vs_fld_pct") and g["vs_fld_pct"]["lo95"] > 0),
        "beats_innings": bool(g.get("vs_innings") and g["vs_innings"]["lo95"] > 0),
        "not_worse_than_raw": bool(g.get("vs_raw_rate") and g["vs_raw_rate"]["lo95"] >= -0.01),
    }
    c["all"] = all(c.values())
    return c


def _dem3(by_season, mid, y):
    num = den = 0.0
    su = 0
    for yy in (y - 2, y - 1, y):
        rec = (by_season.get(yy) or {}).get(mid)
        if rec and rec.get("dem_plus_raw") is not None and rec.get("inn"):
            num += rec["dem_plus_raw"] * rec["inn"]; den += rec["inn"]; su += 1
    return (num / den if den else None), su, den


def _multiyear_proposed(by_season: dict, cur: int) -> dict:
    now = by_season.get(cur) or {}
    players, vals = {}, []
    for mid, row in now.items():
        if row.get("dem_plus") is None or (row.get("inn") or 0) < dem_plus.POOL_MIN_INN:
            continue
        v, su, inn = _dem3(by_season, mid, cur)
        if v is None:
            continue
        tag = "established" if su >= TAG_MIN_SEASONS and inn >= TAG_MIN_INN else "provisional"
        players[str(mid)] = {"name": row.get("name"), "dem_plus_now": row.get("dem_plus"),
                             "dem_plus_3yr": int(round(v)), "seasons_used": su,
                             "inn_total": round(inn, 1), "tag": tag}
        vals.append((str(mid), v))
    s = sorted(v for _, v in vals)
    for mid, v in vals:
        lo = sum(1 for x in s if x < v)
        eq = sum(1 for x in s if x == v)
        players[mid]["pct"] = int(round(100.0 * (lo + (eq + 1) / 2.0 - 0.5) / len(s))) if s else None
    return {"season": cur, "window": [cur - 2, cur - 1, cur], "metric": "dem_plus_3yr",
            "display_name": "DEM+ (3yr)",
            "definition": ("innings-weighted mean DEM+ over the trailing 3 seasons, each "
                           "season scored against its own pool; tag 'established' with "
                           f"{TAG_MIN_SEASONS}+ seasons and {int(TAG_MIN_INN)}+ innings"),
            "n_with_value": len(players), "players": players}


def run(write: bool = True) -> dict:
    t0 = time.time()
    need = sorted(set(FIT_SEASONS + [s + 1 for s in FIT_SEASONS] + SENS_SEASONS
                      + [s + 1 for s in SENS_SEASONS] + SEASONS + [s + 1 for s in SEASONS]
                      + [min(SEASONS) - 2, min(SEASONS) - 1]))
    cur = date.today().year
    need = sorted(set(need) | {cur - 2, cur - 1, cur} - {2020})
    by_season = {}
    for y in need:
        s = load_season(y)
        if s:
            by_season[y] = s
    kf = k_fit(by_season)

    cols, dropped = _pairs(by_season, SEASONS)
    n = len(cols["dem"])
    base = {"vs_fld_pct": cols["pct"], "vs_innings": cols["inn"], "vs_raw_rate": cols["raw"]}
    xd1 = _dual(cols["dem"], base, cols)
    twin = _twin(cols, SEED + 1)
    xtw = _dual(twin, {"vs_fld_pct": cols["pct"]}, cols)
    twin_fails = not bool(xtw["v1"]["gap_ci"]["vs_fld_pct"]
                          and xtw["v1"]["gap_ci"]["vs_fld_pct"]["lo95"] > 0)
    g1 = _gate(xd1, "v1")
    g2 = _gate(xd1, "v2")
    sign_agree = all(
        (xd1["v1"]["gap_ci"][k]["mean"] > 0) == (xd1["v2"]["gap_ci"][k]["mean"] > 0)
        for k in base if xd1["v1"]["gap_ci"].get(k) and xd1["v2"]["gap_ci"].get(k))
    passed = bool(g1["all"] and twin_fails)

    sens = {}
    for label, kw, seasons in (("fit_window_2016_2019_in_sample", {}, SENS_SEASONS),
                               ("non_catchers", {"non_c": True}, SEASONS),
                               ("predictor_floor_300", {"min_y": 300.0}, SEASONS)):
        sc, _ = _pairs(by_season, seasons, **kw)
        if len(sc["dem"]) < 30:
            sens[label] = {"n": len(sc["dem"])}
            continue
        sb = {"vs_fld_pct": sc["pct"], "vs_innings": sc["inn"], "vs_raw_rate": sc["raw"]}
        r = _dual(sc["dem"], sb, sc)
        sens[label] = {"n": len(sc["dem"]), "v1": {k: r["v1"][k] for k in ("rho_primary", "rho_baselines", "gap_ci")},
                       "gate_v1": _gate(r, "v1")}

    # X-D2: 3-year vs 1-year on the same pairs
    one3, three3 = [], []
    c3 = {k: [] for k in ("tgt", "mid", "py", "oy")}
    for y in SEASONS:
        a_s, b_s = by_season.get(y) or {}, by_season.get(y + 1) or {}
        for mid, a in a_s.items():
            b = b_s.get(mid)
            if not b or a["inn"] < MIN_INN_Y or b["inn"] < MIN_INN_NEXT:
                continue
            if not plh.season_complete(y + 1):
                continue
            v, su, inn = _dem3(by_season, mid, y)
            if v is None or su < TAG_MIN_SEASONS or inn < TAG_MIN_INN:
                continue
            one3.append(a["dem_plus_raw"]); three3.append(v)
            c3["tgt"].append(b["rate"]); c3["mid"].append(mid)
            c3["py"].append(y); c3["oy"].append(y + 1)
    n3 = len(one3)
    xd2 = _dual(three3, {"vs_1yr": one3}, c3) if n3 >= 30 else None
    gap3 = xd2["v1"]["gap_ci"]["vs_1yr"] if xd2 else None
    passed3 = bool(xd2 and xd2["v1"]["rho_primary"] is not None
                   and xd2["v1"]["rho_baselines"]["vs_1yr"] is not None
                   and xd2["v1"]["rho_primary"] > xd2["v1"]["rho_baselines"]["vs_1yr"]
                   and gap3 and gap3["lo95"] >= 0)

    fs = {"dem_plus": xd1["v1"]["rho_primary"],
          "raw_rate": xd1["v1"]["rho_baselines"]["vs_raw_rate"],
          "fld_pct": xd1["v1"]["rho_baselines"]["vs_fld_pct"],
          "innings": xd1["v1"]["rho_baselines"]["vs_innings"],
          "twin": xtw["v1"]["rho_primary"]}
    g = xd1["v1"]["gap_ci"]
    summary = (f"Forward-chained over predictor seasons {SEASONS[0]} to {SEASONS[-1]} "
               f"({n} Y to Y+1 pairs): DEM+ rho {fs['dem_plus']} against the raw rate "
               f"{fs['raw_rate']}, fielding percentage {fs['fld_pct']} and innings "
               f"{fs['innings']}; the permuted twin reads {fs['twin']}. Gap CIs: vs "
               f"fielding percentage {g['vs_fld_pct']}, vs innings {g['vs_innings']}, vs "
               f"the raw rate {g['vs_raw_rate']}. ")
    summary += ("VALIDATED: every pre-registered clause holds and the twin fails."
                if passed else
                "PROVISIONAL: at least one pre-registered clause fails; the board "
                "displays DEM+ as a sample-shrunk fielding rating with no forecast claim.")
    dur = round(time.time() - t0, 1)
    payload = {
        "generated_at": date.today().isoformat(), "seasons": SEASONS, "seed": SEED,
        "experiment": "X-D1", "model": "dem_plus",
        "preregistration": "docs/dem-plus-2026-09-11/DEM_PLUS_GATE.md",
        "conventions": {"predictor_year": f"year Y (innings >= {int(MIN_INN_Y)})",
                        "target": f"published fielding rate in Y+1 (innings >= {int(MIN_INN_NEXT)})",
                        "excluded": "2020 (60-game season)",
                        "n_partial_outcome_pairs_dropped": dropped},
        "harness": plh.convention_meta(TARGET_V1, TARGET_V2),
        "k_fit": kf,
        "n_forward_pairs": n,
        "forward_spearman_vs_rate_next": fs,
        "gap_ci_vs_fld_pct": g["vs_fld_pct"], "gap_ci_vs_innings": g["vs_innings"],
        "gap_ci_vs_raw_rate": g["vs_raw_rate"],
        "twin": {"rho": fs["twin"], "gap_ci_vs_fld_pct": xtw["v1"]["gap_ci"]["vs_fld_pct"],
                 "fails_as_required": twin_fails},
        "results_by_convention": xd1,
        "sensitivities": sens,
        "gate": {"bar": ("gap vs fielding percentage lo95 > 0 AND vs innings lo95 > 0 AND vs "
                         "the raw rate lo95 >= -0.01 AND the permuted twin fails"),
                 "convention": "v1", "clauses_v1": g1, "clauses_v2": g2,
                 "v2_sign_agrees": sign_agree, "pass": passed},
        "runtime_seconds": dur,
        "verdict": {"status": "validated" if passed else "provisional", "summary": summary},
    }
    cur_season = max(by_season)
    multi = {
        "generated_at": date.today().isoformat(), "seasons": SEASONS, "seed": SEED,
        "experiment": "X-D2", "model": "dem_plus_3yr", "n_forward_pairs": n3,
        "preregistration": "docs/dem-plus-2026-09-11/DEM_PLUS_GATE.md",
        "conventions": {"predictor_year": ("innings-weighted trailing 3 seasons through Y "
                                           f"({TAG_MIN_SEASONS}+ seasons, {int(TAG_MIN_INN)}+ innings)"),
                        "target": f"published fielding rate in Y+1 (innings >= {int(MIN_INN_NEXT)})"},
        "harness": plh.convention_meta(TARGET_V1, TARGET_V2),
        "dem_1yr_forward_rho_on_3yr_set": xd2["v1"]["rho_baselines"]["vs_1yr"] if xd2 else None,
        "dem_3yr_forward_rho": xd2["v1"]["rho_primary"] if xd2 else None,
        "gap_ci_3yr_minus_1yr": gap3, "results_by_convention": xd2,
        "gate": {"bar": "3yr rho > 1yr rho on the same set AND gap lo95 >= 0",
                 "convention": "v1", "pass": passed3},
        "verdict": ("PASS: 3-year DEM+ forecasts next season's fielding rate better than one "
                    "season; ship dem_plus_3yr as a companion column." if passed3 else
                    "MARGINAL: 3-year DEM+ does not clear the same-set gate; it ships "
                    "provisional with the numbers published."),
        "runtime_seconds": dur,
        "proposed_values": _multiyear_proposed(by_season, cur_season),
    }
    print(json.dumps({"k_fit_matches_frozen": kf["matches_frozen"], "n": n, "rho": fs,
                      "gap_v1": g, "gate": payload["gate"], "twin": payload["twin"],
                      "X-D2": {"n": n3, "gap": gap3, "pass": passed3}}, indent=1))
    if write:
        for path, pl in ((EVAL, payload), (MULTI_EVAL, multi)):
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(pl, indent=1) + "\n", encoding="utf-8")
            tmp.replace(path)
            print(f"wrote {path.relative_to(ROOT)}")
    return {EVAL: payload, MULTI_EVAL: multi}


if __name__ == "__main__":
    run(write="--no-write" not in sys.argv[1:])
