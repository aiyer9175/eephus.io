# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The one read of docs/ewar/LADDER_V2_GATE.md: the position-switcher ladder (v2)
against the Baseball-Reference inversion (v1).

    python tools/ladder_v2_lab.py --dry-run   # fixtures with null cells, plus a
                                              # loader smoke on the real data
                                              # (counts only, nothing scored)
    python tools/ladder_v2_lab.py --read      # THE read: runs once (gate part 7)
    python tools/ladder_v2_lab.py --restamp   # add the record's production date
                                              # (generated_at = the read's date) to a
                                              # record written before the field
                                              # existed; changes nothing else

The read writes data/positional_ladder_v2_eval.json (the record the Library
reads) and data/positional_ladder_v2.json (the fitted ladder). The fitting and
scoring code is ladder_v2.py; this file loads the data, runs the folds, applies
the gate's fixed-sequence rule and writes the record.
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

import ladder_v2 as L2  # noqa: E402

GATE = "docs/ewar/LADDER_V2_GATE.md"
REGISTERED_COMMIT = "7fa62e8a"
FOLDS = tuple(range(2016, 2027))
ALL_SEASONS = set(FOLDS)
BOOT_SEED = 20261015
BOOT_DRAWS = 2000
CI_SEED = 11
CI_DRAWS = 400
ERA_SPLITS = {"2016-2020": set(range(2016, 2021)), "2021-2026": set(range(2021, 2027))}
PRE_STATCAST = set(range(2011, 2016))


# ================================================================== loaders
def load_records(first: int = 2010, last: int = 2026) -> dict:
    """{(mlbam, season): record} from the files the gate's part 2 names."""
    import pandas as pd
    import saber_feed

    fi = json.loads((ROOT / "data" / "fielding_innings.json").read_text(encoding="utf-8"))
    recs: dict = {}
    for ys, byp in fi.get("seasons", {}).items():
        y = int(ys)
        if not (first <= y <= last):
            continue
        for ms, pos in byp.items():
            inn = {p: float((pos.get(p) or {}).get("inn", 0.0)) for p in L2.FIELD
                   if (pos.get(p) or {}).get("inn", 0.0)}
            recs[(int(ms), y)] = {
                "inn": inn,
                "p_inn": float((pos.get("P") or {}).get("inn", 0.0)),
                "dh_g": int((pos.get("DH") or {}).get("g", 0)),
                "fld_g": int(sum((pos.get(p) or {}).get("g", 0) for p in L2.FIELD)),
                "age": None, "runs": {"BREF": None, "FG": None}, "sav": None,
                "pa": None, "runs_bat": None, "runs_position": None, "fg_pos": None,
            }
    b = pd.read_parquet(ROOT / ".cache" / "war_daily" / "bat.parquet",
                        columns=["mlb_ID", "year_ID", "age", "PA", "runs_field", "runs_bat",
                                 "runs_position", "pitcher"])
    b = b[(b.year_ID >= first) & (b.year_ID <= last) & b.mlb_ID.notna()]
    b = b[b.pitcher.astype(str).str.upper() != "Y"]
    g = b.groupby(["mlb_ID", "year_ID"]).agg(
        age=("age", "max"), PA=("PA", "sum"), runs_field=("runs_field", "sum"),
        runs_bat=("runs_bat", "sum"), runs_position=("runs_position", "sum"))
    for (mid, y), row in g.iterrows():
        rec = recs.get((int(mid), int(y)))
        if rec is None:
            continue
        rec["age"] = None if pd.isna(row.age) else float(row.age)
        rec["pa"] = float(row.PA)
        rec["runs"]["BREF"] = float(row.runs_field)
        rec["runs_bat"] = float(row.runs_bat)
        rec["runs_position"] = float(row.runs_position)
    for y in range(max(first, 2011), last + 1):
        vals = (saber_feed.load_components(y) or {}).get("values") or {}
        for mid, v in vals.items():
            rec = recs.get((int(mid), y))
            if rec is None:
                continue
            if v.get("fld") is not None:
                rec["runs"]["FG"] = float(v["fld"])
            if v.get("pos") is not None:
                rec["fg_pos"] = float(v["pos"])
    oaa = json.loads((ROOT / "data" / "savant_oaa.json").read_text(encoding="utf-8"))
    for ms, byy in oaa.get("by_mlbam", {}).items():
        for ys, byp in byy.items():
            rec = recs.get((int(ms), int(ys)))
            if rec is None:
                continue
            sav = {p: float(r["frp"]) for p, r in byp.items()
                   if p in L2.OAA7 and isinstance(r, dict) and r.get("frp") is not None}
            if sav:
                rec["sav"] = sav
    return recs


def served_v1() -> tuple:
    """(served v1 ladder, its exposure vector, generated_at) from data/positional_fit.json."""
    d = json.loads((ROOT / "data" / "positional_fit.json").read_text(encoding="utf-8"))
    lad = d["fit"]["ladder"]
    return (dict(lad["values"]), dict(lad["identification"]["exposure_share"]),
            d.get("generated_at"), lad.get("seasons"))


# ================================================================ fixtures
def fixture_records(seed: int = 5) -> tuple:
    """Synthetic records shaped like the real ones. Every source centres its runs
    within position and season, as the real ones do, so the planted target is
    G_p, the innings-weighted mean glove of the players seen at p. Moves follow
    bad years (selection on the observed rate). Null cells: about 5% missing
    ages, FG absent in 2018, no Savant CF rows in 2019, Savant on a 0.6 run
    scale and FG on 0.9. Returns (records, target ladder recentred, e9)."""
    from collections import defaultdict as _dd
    rng = np.random.default_rng(seed)
    home_l = {"C": 10.0, "1B": -9.0, "2B": 5.0, "3B": 3.0, "SS": 9.0, "LF": -6.0,
              "CF": 4.0, "RF": -6.0}
    order = ["SS", "2B", "3B", "CF", "RF", "LF", "1B", "C"]
    raw = {}
    for i in range(1800):
        m = 100000 + i
        home = order[i % len(order)]
        g = home_l[home] + rng.normal(0, 4)
        start = int(rng.integers(2010, 2020))
        age0 = float(rng.integers(22, 30))
        pos, last = home, 0.0
        bat = rng.normal(-0.8 * home_l[home], 8)
        for y in range(start, min(2027, start + int(rng.integers(3, 9)))):
            if rng.random() < (0.5 if last < -4 else 0.12):
                pos = order[min(len(order) - 1, order.index(pos) + int(rng.integers(1, 3)))]
            inn = {pos: float(rng.integers(500, 1300))}
            if rng.random() < 0.3:
                alt = order[int(rng.integers(0, 7))]
                if alt != pos:
                    inn[alt] = float(rng.integers(150, 400))
            gg = g - 0.3 * (age0 + y - start - 27)
            talent = {p: gg + rng.normal(0, 6) for p in inn}
            dh_g = int(rng.integers(0, 70)) if pos == "1B" else 0
            if i % 40 == 6:
                dh_g = 400   # a DH regular (candidate c needs DH primaries)
            raw[(m, y)] = (inn, talent, gg, age0 + y - start, dh_g, bat)
            last = talent[pos] - home_l[pos]
    acc = _dd(lambda: [0.0, 0.0])
    gacc = _dd(lambda: [0.0, 0.0])
    for (m, y), (inn, talent, gg, a, dh_g, bat) in raw.items():
        for p, v in inn.items():
            acc[(p, y)][0] += v * talent[p]
            acc[(p, y)][1] += v
            gacc[p][0] += v * gg
            gacc[p][1] += v
    e9 = {"C": 0.1125, "1B": 0.1174, "2B": 0.1125, "3B": 0.1159, "SS": 0.1079,
          "LF": 0.1156, "CF": 0.1125, "RF": 0.1173, "DH": 0.0883}
    G = {p: gacc[p][0] / gacc[p][1] for p in L2.FIELD}
    G["DH"] = G["1B"] - 4.0
    recs = {}
    for (m, y), (inn, talent, gg, a, dh_g, bat) in raw.items():
        rate = {p: talent[p] - acc[(p, y)][0] / acc[(p, y)][1] for p in inn}
        runs_c = sum(inn[p] / L2.UNIT_INN * rate[p] for p in inn)
        fld = sum(inn.values())
        pa = fld / 1.97 + dh_g * 4.0
        sav = None
        if y >= 2016:
            sav = {p: 0.6 * inn[p] / L2.UNIT_INN * rate[p] for p in inn
                   if p in L2.OAA7 and not (y == 2019 and p == "CF")}
        recs[(m, y)] = {
            "inn": inn, "p_inn": 0.0, "dh_g": dh_g, "fld_g": int(fld / 9),
            "age": None if rng.random() < 0.05 else a,
            "runs": {"BREF": runs_c, "FG": None if (y == 2018 or y < 2011) else 0.9 * runs_c},
            "sav": sav or None, "pa": pa, "runs_bat": bat * pa / 650.0,
            "runs_position": (sum(v / L2.UNIT_INN * home_l[p] for p, v in inn.items())
                              - 13.0 * dh_g * 4.0 / 650.0),
            "fg_pos": sum(v / L2.UNIT_INN * home_l[p] * 1.1 for p, v in inn.items()),
        }
    return recs, L2.recentre(G, e9), e9


# ================================================================== the read
def run(records: dict, e9: dict, v1_served: dict, boot_draws: int, ci_draws: int,
        log=print) -> dict:
    t0 = time.time()
    rows = L2.build_rows(records)
    counts = {s: {"across": int(len(R.A["m"])), "across_switch": int(R.A["switch"].sum()),
                  "within": int(len(R.B["m"])), "dh_type": int(len(R.DHT["m"]))}
              for s, R in rows.items()}
    log(f"rows: {json.dumps(counts)}")
    v1s = L2.recentre(v1_served, e9)
    fgtab = L2.fg_table_ladder(e9)

    loss_rows, folds = [], {}
    for t in FOLDS:
        train = ALL_SEASONS - {t}
        v1_t = L2.fit_inversion(records, train, e9)
        b_t, Vb_t, info_t = L2.fit_b(rows, e9, v1_t, train, drop=t)
        c_t = L2.fit_offense(records, train, e9)
        fginv_t = L2.fit_inversion(records, train, e9, y_key="fg_pos")
        single_b, single_bv, single_v1, single_v1v = {}, {}, {}, {}
        for s in sorted(train):
            Lb, Vb, _ = L2.fit_b(rows, e9, v1_t, {s}, drop=t)
            single_b[s], single_bv[s] = Lb, Vb
            Lv, Vv = L2.fit_inversion(records, {s}, e9, want_var=True)
            single_v1[s], single_v1v[s] = Lv, Vv
        nb = [t - 1, t + 1]
        d_b_t = (L2.per_season_shrunk(single_b, b_t, single_bv, nb)[0]
                 if b_t is not None else None)
        d_v1_t = (L2.per_season_shrunk(single_v1, v1_t, single_v1v, nb)[0]
                  if v1_t is not None else None)
        ladders = {"v1": v1_t, "b": b_t, "c": c_t, "fg_inv": fginv_t, "fg_table": fgtab,
                   "v1_served": v1s, "d_b": d_b_t, "d_v1": d_v1_t}
        lr = L2.score_rows(rows, ladders, t, train)
        loss_rows.extend(lr)
        folds[t] = {"n_rows": len(lr),
                    "ladders": {k: L2.ladder_round(v, 3) for k, v in ladders.items()},
                    "b_info": {k: v for k, v in (info_t or {}).items() if k != "legs"}}
        log(f"fold {t}: {len(lr)} scored rows, {time.time() - t0:.0f}s")

    names = ("v1", "b", "c", "fg_inv", "fg_table", "v1_served", "d_b", "d_v1")
    is_across = (lambda r: r[2] == "across")
    scores = {
        "pooled": L2.summarize(loss_rows, names),
        "across_ew3_23": L2.summarize(loss_rows, names, is_across),
        "within_savant": L2.summarize(loss_rows, names, lambda r: r[2] == "within"),
        "by_source": {s: L2.summarize(loss_rows, names, (lambda r, s=s: r[1] == s))
                      for s in L2.SOURCES},
        "by_fold": {},
    }
    boot = lambda a, b, sel=None: L2.cluster_boot(loss_rows, a, b, sel, boot_draws, BOOT_SEED)  # noqa: E731
    tests = {
        "v1_minus_b_pooled": boot("v1", "b"),
        "v1_minus_b_across": boot("v1", "b", is_across),
        "v1_served_minus_b_pooled": boot("v1_served", "b"),
        "b_minus_d_b_pooled": boot("b", "d_b"),
        "v1_minus_d_v1_pooled": boot("v1", "d_v1"),
        "v1_minus_c_pooled": boot("v1", "c"),
        "v1_minus_fg_inv_pooled": boot("v1", "fg_inv"),
        "v1_minus_fg_table_pooled": boot("v1", "fg_table"),
        "v1_minus_b_by_source": {s: boot("v1", "b", (lambda r, s=s: r[1] == s))
                                 for s in L2.SOURCES},
        "v1_minus_b_within": boot("v1", "b", lambda r: r[2] == "within"),
    }
    # per-fold MAE (point only; the gate's CI is pooled)
    for t in FOLDS:
        scores["by_fold"][t] = L2.summarize(loss_rows, ("v1", "b", "d_b", "v1_served"),
                                            (lambda r, t=t: r[5] == t))
    log(f"scoring done, {time.time() - t0:.0f}s")

    # ---------------------------------------------------- the fixed-sequence rule
    p1 = tests["v1_minus_b_pooled"]
    p1a = tests["v1_minus_b_across"]
    step1 = bool(p1 and p1["ci95"][0] > 0 and p1a and p1a["ci95"][1] >= 0)
    step2 = None
    if step1:
        p2 = tests["b_minus_d_b_pooled"]
        step2 = bool(p2 and p2["ci95"][0] > 0)
    served = ("d_b" if step2 else "b") if step1 else "v1"
    verdict = {
        "step1_b_replaces_v1": step1, "step2_d_replaces_b": step2,
        "served_on_position_fit": "v2" if step1 else "v1",
        "v2_vector": None if not step1 else ("d (per-season shrunk b, target 2026)"
                                              if step2 else "b (pooled 2016-2026)"),
        # Wording changed after the read for the copy lint (no spaced minus
        # signs); the record of 2026-10-15 keeps the text it was written with.
        "rule": ("b replaces v1 when the pooled error gap of v1 over b has a CI95 lower bound "
                 "above 0 and the next-season gap has a CI95 upper bound at or above 0; then "
                 "d replaces b when the gap of b over d has a CI95 lower bound above 0"),
    }
    log(f"verdict: {json.dumps(verdict)}")

    # ------------------------------------------------------------ recorded fits
    log("final fits on 2016-2026 ...")
    b_all, Vb_all, info_all = L2.fit_b(rows, e9, v1_served, ALL_SEASONS)
    single_b, single_bv = {}, {}
    for s in sorted(ALL_SEASONS):
        Lb, Vb, _ = L2.fit_b(rows, e9, v1_served, {s})
        single_b[s], single_bv[s] = Lb, Vb
    d_all, d_fac, d_tau = (L2.per_season_shrunk(single_b, b_all, single_bv, [2025])
                           if b_all is not None else (None, {}, {}))
    v1_1626 = L2.fit_inversion(records, ALL_SEASONS, e9)
    c_all = L2.fit_offense(records, ALL_SEASONS, e9)
    fginv_all = L2.fit_inversion(records, ALL_SEASONS, e9, y_key="fg_pos")
    era = {}
    for k, ss in ERA_SPLITS.items():
        Le, _Ve, ie = L2.fit_b(rows, e9, v1_served, ss)
        era[k] = {"b": L2.ladder_round(Le, 2), "legs": ie.get("legs"),
                  "c_branch": ie.get("c_branch")}
    pre = {}
    for s in ("BREF", "FG"):
        R = rows[s]
        f_pre = L2.fit_network(R, e9, L2._season_mask_A(R.A, PRE_STATCAST))
        f_post = L2.fit_network(R, e9, L2._season_mask_A(R.A, ALL_SEASONS))
        pre[s] = {"2011-2015": (L2.source_ladder(f_pre, e9) if f_pre else {}),
                  "2016-2026": (L2.source_ladder(f_post, e9) if f_post else {})}
        pre[s] = {k: {p: round(v[0], 2) for p, v in leg.items()} for k, leg in pre[s].items()}
    log(f"bootstrap CI ({ci_draws} draws) ...")
    ci = {}
    if b_all is not None and ci_draws:
        rng = np.random.default_rng(CI_SEED)
        players = sorted({int(m) for R in rows.values()
                          for arr in (R.A["m"], R.B["m"], R.DHT["m"]) for m in arr})
        idx = {m: i for i, m in enumerate(players)}
        draws = []
        for _ in range(ci_draws):
            cnt = rng.multinomial(len(players), np.full(len(players), 1.0 / len(players)))

            def wm(ms, cnt=cnt):
                return np.array([cnt[idx[int(m)]] for m in ms], dtype=float)
            Lb, _V, _i = L2.fit_b(rows, e9, v1_served, ALL_SEASONS, wmult=wm)
            if Lb is not None:
                draws.append([Lb[p] for p in L2.LADDER9])
        draws = np.array(draws)
        ci = {p: [round(float(np.percentile(draws[:, i], 2.5)), 2),
                  round(float(np.percentile(draws[:, i], 97.5)), 2)]
              for i, p in enumerate(L2.LADDER9)} if len(draws) else {}
        ci_n = len(draws)
    else:
        ci_n = 0
    served_vec = None
    if step1:
        served_vec = d_all if step2 else b_all
    legs_aligned = {}
    if b_all is not None:
        m7 = L2.mean7(b_all, e9)
        for s, leg in (info_all.get("legs") or {}).items():
            legs_aligned[s] = {p: round(v + m7, 2) for p, v in leg.items()}
    comparison = {
        "positions": list(L2.LADDER9),
        "columns": {
            "v2_b_2016_2026": L2.ladder_round(b_all, 2),
            "v2_d_2026": L2.ladder_round(d_all, 2),
            "v1_served": L2.ladder_round(v1s, 2),
            "v1_refit_2016_2026": L2.ladder_round(v1_1626, 2),
            "fg_inversion_2016_2026": L2.ladder_round(fginv_all, 2),
            "fg_table_rescaled": L2.ladder_round(fgtab, 2),
            "offense_equalizing_2016_2026": L2.ladder_round(c_all, 2),
        },
        "source_legs_on_v2_zero": legs_aligned,
        "note": ("every column recentred on one exposure vector (gate part 4), so gaps and "
                 "levels compare directly; the source legs are shifted to the v2 "
                 "seven-position mean and carry the positions each source rates"),
    }
    ladder_artifact = {
        "model": "positional_ladder_v2",
        "gate": GATE,
        "status": ("served on Position Fit" if step1 else
                   "candidate: did not replace v1 (gate part 5); not served"),
        "units": "runs per 650 PA (per 1,277.7 fielded innings), exposure-weighted sum zero",
        "method": ("same-player position-switcher network: per fielding source (Baseball-"
                   "Reference runs_field, FanGraphs fld, Savant FRP) a weighted least squares "
                   "of next-season fielding runs on the change in innings shares with a glove "
                   "persistence and an age term, plus Savant same-season pairs; sources "
                   "pooled by inverse variance; DH = 1B + the 1B rate of DH-type seasons; "
                   "C by the gate's part 3 rule"),
        "values": L2.ladder_round(served_vec if served_vec is not None else b_all, 2),
        "values_basis": served if step1 else "b",
        "ci95": ci,
        "ci_draws": ci_n,
        "ci_seed": CI_SEED,
        "exposure_share": e9,
        "seasons": [min(ALL_SEASONS), max(ALL_SEASONS)],
        "c_branch": info_all.get("c_branch"),
        "c_network": info_all.get("c_network"),
        "c_network_se": info_all.get("c_network_se"),
        "dh_mu": info_all.get("dh_mu"),
        "dh_mu_se": info_all.get("dh_mu_se"),
        "source_fits": info_all.get("fits"),
        "per_season_shrink": {"factor": {p: _rnd(v, 3) for p, v in d_fac.items()},
                              "tau2": {p: _rnd(v, 3) for p, v in d_tau.items()},
                              "neighbour": 2025},
        "era_splits": era,
        "pre_statcast_legs": pre,
    }
    out = {
        "model": "positional_ladder_v2_eval",
        "gate": GATE,
        "registered_commit": REGISTERED_COMMIT,
        "generated_at": _dt.date.today().isoformat(),
        "read_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "unit_innings": L2.UNIT_INN,
        "exposure_share": e9,
        "seeds": {"bootstrap": BOOT_SEED, "draws": boot_draws, "ci": CI_SEED, "ci_draws": ci_draws},
        "row_counts": counts,
        "verdict": verdict,
        "tests": tests,
        "scores": scores,
        "folds": folds,
        "comparison": comparison,
        "ladder_artifact": ladder_artifact,
        "runtime_s": round(time.time() - t0, 1),
    }
    return out


def _rnd(v, nd):
    return None if v is None else round(float(v), nd)


def _clean(o):
    """JSON-safe: tuples to lists, numpy to python, int keys to str."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating,)):
        return None if math.isnan(float(o)) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, float) and math.isnan(o):
        return None
    return o


def report(out: dict, log=print):
    v = out["verdict"]
    t = out["tests"]

    def fm(d):
        if not d:
            return "n/a"
        return (f"{d['dmae']:+.4f} CI95 [{d['ci95'][0]:+.4f}, {d['ci95'][1]:+.4f}]  "
                f"dMSE {d['dmse']:+.3f}  rows {d['n_rows']} players {d['n_players']}")
    log("=" * 78)
    log("POSITIONAL LADDER v2 READ (docs/ewar/LADDER_V2_GATE.md)")
    log("=" * 78)
    for k in ("v1_minus_b_pooled", "v1_minus_b_across", "v1_minus_b_within",
              "v1_served_minus_b_pooled", "b_minus_d_b_pooled", "v1_minus_d_v1_pooled",
              "v1_minus_c_pooled", "v1_minus_fg_inv_pooled", "v1_minus_fg_table_pooled"):
        log(f"  {k:<28} {fm(t.get(k))}")
    for s, d in (t.get("v1_minus_b_by_source") or {}).items():
        log(f"  v1_minus_b [{s:<6}]          {fm(d)}")
    log("  MAE pooled: " + "  ".join(f"{n} {d['mae']:.4f}" for n, d in out["scores"]["pooled"].items() if d))
    log(f"  VERDICT: {json.dumps(v)}")
    comp = out["comparison"]["columns"]
    log(f"  {'pos':<4}" + "".join(f"{k[:14]:>15}" for k in comp))
    for p in out["comparison"]["positions"]:
        log(f"  {p:<4}" + "".join(
            f"{(c or {}).get(p) if (c or {}).get(p) is not None else float('nan'):>15.2f}"
            for c in comp.values()))
    la = out["ladder_artifact"]
    log(f"  served-basis values: {la['values']}  CI95: {la['ci95']}")
    log(f"  C branch {la['c_branch']} (network {la['c_network']} se {la['c_network_se']}); "
        f"DH mu {la['dh_mu']} se {la['dh_mu_se']}")
    log(f"  source fits: {json.dumps(la['source_fits'])}")


def restamp() -> int:
    """The record of 2026-10-15 predates the generated_at field the registry's
    freshness check reads. Add it as the read's own date (read_at), insert it
    after registered_commit, and change nothing else. Idempotent."""
    if not L2.EVAL_PATH.exists():
        print("no record to restamp")
        return 1
    ev = json.loads(L2.EVAL_PATH.read_text(encoding="utf-8"))
    if ev.get("generated_at"):
        print(f"record already stamped {ev['generated_at']}; nothing written")
        return 0
    date = str(ev.get("read_at") or "")[:10]
    if len(date) != 10:
        print("record has no read_at to stamp from")
        return 1
    out = {}
    for k, v in ev.items():
        out[k] = v
        if k == "registered_commit":
            out["generated_at"] = date
    out.setdefault("generated_at", date)
    L2.write_eval(out)
    print(f"stamped generated_at {date}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--read", action="store_true")
    g.add_argument("--restamp", action="store_true")
    ap.add_argument("--out", type=Path, default=None, help="dry-run output directory")
    a = ap.parse_args()
    if a.restamp:
        return restamp()
    if a.dry_run:
        recs, true_l, e9 = fixture_records()
        print(f"fixtures: {len(recs)} records; planted target {L2.ladder_round(true_l, 2)}")
        rows_fx = L2.build_rows(recs)
        m7 = L2.mean7(true_l, e9)
        for s_, R_ in rows_fx.items():
            f_ = L2.fit_network(R_, e9)
            leg = L2.source_ladder(f_, e9) if f_ else {}
            print(f"  fixture leg {s_}: k {f_ and round(f_['k'], 3)} "
                  + " ".join(f"{p} {v[0]:+.2f}/{true_l[p] - m7:+.2f}" for p, v in leg.items()))
        out = run(recs, e9, true_l, boot_draws=50, ci_draws=8)
        out = _clean(out)
        report(out)
        if a.out:
            a.out.mkdir(parents=True, exist_ok=True)
            (a.out / "dry_run_eval.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
        # loader smoke on the real data: counts only, nothing fitted or scored
        real = load_records()
        rows = L2.build_rows(real)
        print("real loader smoke:", json.dumps({
            "records": len(real),
            "with_bref": sum(1 for r in real.values() if r["runs"]["BREF"] is not None),
            "with_fg": sum(1 for r in real.values() if r["runs"]["FG"] is not None),
            "with_savant": sum(1 for r in real.values() if r["sav"]),
            "with_age": sum(1 for r in real.values() if r["age"] is not None),
            "rows": {s: {"across": int(len(R.A["m"])), "within": int(len(R.B["m"])),
                         "dh_type": int(len(R.DHT["m"]))} for s, R in rows.items()}}))
        v1, e9r, gen, seasons = served_v1()
        print(f"served v1 ({gen}, {seasons}): {v1}; exposure {e9r}")
        print("dry run: clean")
        return 0
    recs = load_records()
    v1, e9, gen, seasons = served_v1()
    print(f"read: {len(recs)} records; served v1 {gen} {seasons}")
    out = _clean(run(recs, e9, v1, boot_draws=BOOT_DRAWS, ci_draws=CI_DRAWS))
    out["v1_served_artifact"] = {"generated_at": gen, "seasons": seasons}
    report(out)
    L2.write_eval(out)
    print(f"wrote {L2.EVAL_PATH}")
    return L2.main()


if __name__ == "__main__":
    sys.exit(main())
