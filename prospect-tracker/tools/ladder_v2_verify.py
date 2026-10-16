# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The verification of the positional ladder v2 read (LADDER_V2_REVERT, owner
decision EW3-29, 2026-10-15; docs/ewar/LADDER_V2_GATE.md part 9).

The one read (tools/ladder_v2_lab.py --read) passed v2 against the
Baseball-Reference inversion (v1). An independent check then asked what the
pass rule never asked: does v2 beat NO ladder? This tool records that check so
every figure the Library and the registry quote about it derives from an
artifact. It refits nothing that serves and changes no read:

    python tools/ladder_v2_verify.py      # writes data/positional_ladder_v2_verify.json

Four blocks, all on the read's own data, folds and scoring (ladder_v2.py):

1. zero_ladder: the registered leave-one-season-out scoring with three more
   ladders per fold: an all-zero fielding ladder (C and DH as v2's, though DH
   never enters a scored row), and v1 and v2 scaled by 0 to 1.25. Paired
   player-cluster bootstrap, the read's seed and draws.
2. rung_coverage: how much of the scored weight can see the C and DH rungs.
3. savant_centring: Statcast fielding runs prevented are not centred within
   position (the other two sources are), and the v2 refit with them centred.
4. bridges: what sets the gap between the infield and the outfield, and each
   source's leg read against shortstop.
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import ladder_v2 as L2  # noqa: E402
import ladder_v2_lab as lab  # noqa: E402

OUT_PATH = ROOT / "data" / "positional_ladder_v2_verify.json"
FOLDS = lab.FOLDS
ALL = set(FOLDS)
SEED = lab.BOOT_SEED
DRAWS = lab.BOOT_DRAWS
SCALES = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25)
IF4 = ("1B", "2B", "3B", "SS")
OF3 = ("LF", "CF", "RF")
BINS = (0.0, 0.1, 0.25, 0.5, 1.0001)


def _r(x, nd=4):
    return None if x is None else round(float(x), nd)


def _lad(L, nd=4):
    return {p: _r(L[p], nd) for p in L2.LADDER9 if L.get(p) is not None}


def _boot(loss, a, b, sel=None):
    t = L2.cluster_boot(loss, a, b, sel=sel, draws=DRAWS, seed=SEED)
    if t is None:
        return None
    return {"dmae": _r(t["dmae"]), "ci95": [_r(x) for x in t["ci95"]],
            "n_rows": t["n_rows"], "n_players": t["n_players"]}


def _scaled(L, s):
    return {p: s * L[p] for p in L2.LADDER9}


def zero_ladder(recs, rows, e9) -> dict:
    """Block 1: the registered scoring with an all-zero fielding ladder beside
    v1 and v2 (each refit per fold exactly as the read refit them)."""
    loss = []
    fgt = L2.fg_table_ladder(e9)
    for t in FOLDS:
        train = ALL - {t}
        v1_t = L2.fit_inversion(recs, train, e9)
        b_t = L2.fit_b(rows, e9, v1_t, train, drop=t)[0]
        lad = {"v1": v1_t, "b": b_t,
               "zero": {p: (b_t[p] if p in ("C", "DH") else 0.0) for p in L2.LADDER9}}
        for s in SCALES:
            lad[f"v1_x{s}"] = _scaled(v1_t, s)
            lad[f"b_x{s}"] = _scaled(b_t, s)
            lad[f"fg_table_x{s}"] = _scaled(fgt, s)
        loss.extend(L2.score_rows(rows, lad, t, train))
    names = list(loss[0][4])
    pooled = L2.summarize(loss, names)
    across = L2.summarize(loss, ["v1", "b", "zero"], lambda r: r[2] == "across")
    within = L2.summarize(loss, ["v1", "b", "zero"], lambda r: r[2] == "within")
    by_src = {s: L2.summarize(loss, ["v1", "b", "zero"], (lambda r, s=s: r[1] == s))
              for s in L2.SOURCES}
    mae = {n: _r(v["mae"]) for n, v in pooled.items() if v}
    return {
        "what": ("The read's leave-one-season-out scoring (2016 to 2026, amendment A2's "
                 "predictor), with an all-zero fielding ladder and scaled copies of v1 and "
                 "v2 added in every fold. zero: every fielding rung 0, C and DH as the "
                 "fold's v2. dMAE a minus b, positive favours b; paired player-cluster "
                 "bootstrap."),
        "mae_pooled": {"v1": mae["v1"], "b": mae["b"], "zero": mae["zero"]},
        "mae_by_scale": {k: {str(s): mae[f"{k}_x{s}"] for s in SCALES}
                         for k in ("v1", "b", "fg_table")},
        "monotone_toward_zero": {
            k: all(mae[f"{k}_x{a}"] <= mae[f"{k}_x{b}"] for a, b in zip(SCALES, SCALES[1:]))
            for k in ("v1", "b", "fg_table")},
        "b_scale_at_lowest_mae": min(SCALES, key=lambda s: mae[f"b_x{s}"]),
        "mae_across": {n: _r(v["mae"]) for n, v in across.items() if v},
        "mae_within": {n: _r(v["mae"]) for n, v in within.items() if v},
        "mae_by_source": {s: {n: _r(v["mae"]) for n, v in d.items() if v} for s, d in by_src.items()},
        "tests": {
            "v1_minus_b": _boot(loss, "v1", "b"),
            "zero_minus_b": _boot(loss, "zero", "b"),
            "v1_minus_zero": _boot(loss, "v1", "zero"),
            "zero_minus_b_across": _boot(loss, "zero", "b", lambda r: r[2] == "across"),
            "zero_minus_b_within": _boot(loss, "zero", "b", lambda r: r[2] == "within"),
        },
        "n_rows": len(loss),
        "n_players": len({r[0] for r in loss}),
    }


def rung_coverage(rows) -> dict:
    """Block 2: the scored rows are the read's (across-season switchers and
    Statcast same-season pairs, held-out seasons 2016 to 2026). A rung can only
    move a row's error through that row's innings shares."""
    out = {}
    for s, R in rows.items():
        A = R.A
        sel = np.isin(A["t"], list(FOLDS)) & A["switch"]
        w = A["w"][sel]
        nB = int(np.isin(R.B["t"], list(FOLDS)).sum())
        wB = float(R.B["w"][np.isin(R.B["t"], list(FOLDS))].sum())
        c = {"rows_any_c": 0, "rows_c_change_025": 0, "weight_share_any_c": 0.0,
             "weight_share_c_change_025": 0.0}
        if "C" in R.pos:
            ci = R.pos.index("C")
            anyc = (A["S0"][sel, ci] + A["S1"][sel, ci]) > 0
            chg = np.abs(A["S1"][sel, ci] - A["S0"][sel, ci]) >= L2.C_CHANGE
            tot = float(w.sum()) + wB
            c = {"rows_any_c": int(anyc.sum()), "rows_c_change_025": int(chg.sum()),
                 "weight_share_any_c": _r(float(w[anyc].sum()) / tot),
                 "weight_share_c_change_025": _r(float(w[chg].sum()) / tot)}
        out[s] = {"scored_rows": int(sel.sum()) + nB, "across_rows": int(sel.sum()),
                  "within_pairs": nB, "C": c, "DH_rows": 0}
    return {
        "what": ("Rows of the read's scoring that carry any innings at C, and a C share "
                 "change of 0.25 or more; DH never enters a scored row, because the rows "
                 "are built from fielded-innings shares and DH is not a fielded position."),
        "by_source": out,
    }


def _centre_savant(recs) -> tuple[dict, dict]:
    """(records with Statcast FRP centred within position and season,
    pooled league rate per position per 1,277.7 innings 2016-2026)."""
    acc = defaultdict(lambda: [0.0, 0.0])
    for (m, t), r in recs.items():
        if r["sav"]:
            for p, v in r["sav"].items():
                i = r["inn"].get(p, 0.0)
                if i > 0:
                    acc[(p, t)][0] += v
                    acc[(p, t)][1] += i
    rc = {}
    for k, r in recs.items():
        if r["sav"]:
            rr = dict(r)
            rr["sav"] = {p: v - acc[(p, k[1])][0] / acc[(p, k[1])][1] * r["inn"].get(p, 0.0)
                         for p, v in r["sav"].items()}
            rc[k] = rr
        else:
            rc[k] = r
    rate = {}
    for p in L2.OAA7:
        s = sum(acc[(p, t)][0] for t in FOLDS)
        i = sum(acc[(p, t)][1] for t in FOLDS)
        rate[p] = {"pooled_2016_2026": _r(s / i * L2.UNIT_INN, 2) if i else None,
                   "by_season": {str(t): (_r(acc[(p, t)][0] / acc[(p, t)][1] * L2.UNIT_INN, 2)
                                          if acc[(p, t)][1] else None) for t in FOLDS}}
    return rc, rate


def _implied_rates(recs, src) -> dict:
    """No-intercept regression of a source's season fielding runs on innings by
    position (per 1,277.7): the league rate a source books at each position."""
    X, y = [], []
    for (m, t), r in recs.items():
        if t not in ALL or r["runs"][src] is None or (r["p_inn"] or 0) > L2.MAX_P_INN:
            continue
        X.append([r["inn"].get(p, 0.0) / L2.UNIT_INN for p in L2.FIELD])
        y.append(r["runs"][src])
    b, *_ = np.linalg.lstsq(np.array(X), np.array(y), rcond=None)
    return {p: _r(v, 2) for p, v in zip(L2.FIELD, b)}


def _vs(L, ref):
    return {p: _r(L[p] - L[ref], 2) for p in L if L.get(p) is not None and L.get(ref) is not None}


def savant_centring(recs, rows, e9, v1_served) -> dict:
    rc, rate = _centre_savant(recs)
    rows_c = L2.build_rows(rc)
    b_all = L2.fit_b(rows, e9, v1_served, ALL)[0]
    b_c = L2.fit_b(rows_c, e9, v1_served, ALL)[0]
    b_bf = L2.fit_b({s: rows[s] for s in ("BREF", "FG")}, e9, v1_served, ALL)[0]
    loss = []
    zero = {p: 0.0 for p in L2.LADDER9}
    for t in FOLDS:
        train = ALL - {t}
        v1_t = L2.fit_inversion(recs, train, e9)
        bt = L2.fit_b(rows_c, e9, v1_t, train, drop=t)[0]
        loss.extend(L2.score_rows(rows_c, {"v1": v1_t, "b_centred": bt, "zero": zero}, t, train))
    sm = L2.summarize(loss, ["v1", "b_centred", "zero"])
    return {
        "what": ("Statcast fielding runs prevented summed over a position and season do not "
                 "net to zero: the league books runs at CF and takes them at LF and RF. "
                 "Baseball-Reference and FanGraphs fielding runs sit near zero at every "
                 "position. The refits below are b on all 2016 to 2026 rows."),
        "savant_league_rate_per_1277_7_inn": rate,
        "bref_implied_rate_per_1277_7_inn": _implied_rates(recs, "BREF"),
        "fg_implied_rate_per_1277_7_inn": _implied_rates(recs, "FG"),
        "refit_gaps_vs_SS": {
            "v2_as_read": _vs(b_all, "SS"),
            "savant_centred": _vs(b_c, "SS"),
            "bref_and_fg_only": _vs(b_bf, "SS"),
            "v1_served": _vs(v1_served, "SS"),
        },
        "scoring_with_savant_centred_mae": {n: _r(v["mae"]) for n, v in sm.items() if v},
        "scoring_with_savant_centred_tests": {
            "zero_minus_b_centred": _boot(loss, "zero", "b_centred"),
            "v1_minus_zero": _boot(loss, "v1", "zero"),
        },
    }


def bridges(recs, rows, e9) -> dict:
    """Block 4: the infield and outfield are fit as one ladder only through the
    switchers whose share of infield innings changes between seasons."""
    rc, _ = _centre_savant(recs)
    rows_c = L2.build_rows(rc)
    legs, inside = {}, {}
    for name, rws in (("BREF", rows["BREF"]), ("FG", rows["FG"]), ("SAVANT", rows["SAVANT"]),
                      ("SAVANT_centred", rows_c["SAVANT"])):
        f = L2.fit_network(rws, e9, L2._season_mask_A(rws.A, ALL), np.isin(rws.B["t"], list(FOLDS)))
        leg = {p: v[0] for p, v in L2.source_ladder(f, e9).items()}
        legs[name] = {"gaps_vs_SS": _vs(leg, "SS"), "CF_minus_SS": _r(leg["CF"] - leg["SS"], 2)}
    for s, R in rows.items():
        A, P = R.A, R.pos
        inside[s] = {}
        for gname, grp, ref in (("infield", IF4, "SS"), ("outfield", OF3, "CF")):
            gi = [P.index(p) for p in grp]
            mA = ((A["S0"][:, gi].sum(1) > 0.999) & (A["S1"][:, gi].sum(1) > 0.999)
                  & L2._season_mask_A(A, ALL))
            mB = np.zeros(len(R.B["m"]), dtype=bool)
            if s == "SAVANT":
                mB = np.isin(R.B["a"], gi) & np.isin(R.B["b"], gi) & np.isin(R.B["t"], list(FOLDS))
            f = L2.fit_network(R, e9, mA, mB)
            D = {p: -f["D"][p] for p in grp if f and f["D"].get(p) is not None}
            inside[s][gname] = {"n_switchers": f["n_switch"] if f else 0,
                                "gaps_vs_" + ref: {p: _r(D[p] - D[ref], 2) for p in D}}
    span = {}
    for s, R in rows.items():
        A, P = R.A, R.pos
        sel = np.isin(A["t"], list(FOLDS)) & A["switch"] & ~np.isnan(A["age"])
        gi = [P.index(p) for p in IF4]
        go = [P.index(p) for p in OF3]
        i1 = P.index("1B")
        out = {}
        for key, d, has in (
                ("infield_share", np.abs(A["S1"][:, gi].sum(1) - A["S0"][:, gi].sum(1)),
                 ((A["S0"][:, gi].sum(1) + A["S1"][:, gi].sum(1)) > 0)
                 & ((A["S0"][:, go].sum(1) + A["S1"][:, go].sum(1)) > 0)),
                ("first_base_share", np.abs(A["S1"][:, i1] - A["S0"][:, i1]),
                 (A["S0"][:, i1] + A["S1"][:, i1]) > 0)):
            m = sel & has
            dd, ww = d[m], A["w"][m]
            info = ww * dd ** 2
            bins = []
            for lo, hi in zip(BINS, BINS[1:]):
                k = (dd >= lo) & (dd < hi)
                bins.append({"change_from": lo, "change_to": min(hi, 1.0), "rows": int(k.sum()),
                             "information_share": _r(float(info[k].sum()) / float(info.sum()))
                             if info.sum() > 0 else None})
            out[key] = {"rows": int(m.sum()), "bins": bins}
        span[s] = {"switchers": int(sel.sum()), **out}
    return {
        "what": ("legs: each source's own ladder, read against shortstop (Statcast also with "
                 "its runs centred). inside: the network fit on rows whose two seasons are "
                 "entirely infield, or entirely outfield. span: switcher rows that played "
                 "both the infield and the outfield across the two seasons (and rows with any "
                 "first-base innings), binned by how much of the season's innings moved; "
                 "information share is each bin's share of sum(weight x change squared), the "
                 "quantity a least squares fit learns the gap from."),
        "legs": legs,
        "inside": inside,
        "span": span,
    }


def main() -> int:
    import scrapers
    t0 = time.time()
    with scrapers.cache_only():
        recs = lab.load_records()
    v1, e9, gen, seasons = lab.served_v1()
    rows = L2.build_rows(recs)
    out = {
        "model": "positional_ladder_v2",
        "kind": "verification of the one read",
        "gate": "docs/ewar/LADDER_V2_GATE.md",
        "task": "LADDER_V2_REVERT (owner decision EW3-29)",
        "generated_at": _dt.date.today().isoformat(),
        "read_record": "data/positional_ladder_v2_eval.json",
        "seed": SEED, "draws": DRAWS, "unit_innings": L2.UNIT_INN,
        "v1_served_artifact": {"generated_at": gen, "seasons": seasons},
        "zero_ladder": zero_ladder(recs, rows, e9),
        "rung_coverage": rung_coverage(rows),
        "savant_centring": savant_centring(recs, rows, e9, L2.recentre(v1, e9)),
        "bridges": bridges(recs, rows, e9),
    }
    z = out["zero_ladder"]["tests"]["zero_minus_b"]
    out["finding"] = {
        "zero_ties_v2": bool(z and z["ci95"][0] <= 0),
        "v1_minus_b_reproduces_read": out["zero_ladder"]["tests"]["v1_minus_b"]["dmae"],
        "status": "refuted pending re-read",
    }
    out["runtime_s"] = round(time.time() - t0, 1)
    blob = json.dumps(out, indent=1)
    if chr(0x2014) in blob or chr(0x2013) in blob:
        raise SystemExit("refusing: a dash in the record")
    OUT_PATH.write_text(blob + chr(10), encoding="utf-8")
    print(json.dumps({"zero_ladder": out["zero_ladder"]["tests"],
                      "mae_by_scale": out["zero_ladder"]["mae_by_scale"],
                      "finding": out["finding"]}, indent=1))
    print(f"wrote {OUT_PATH} in {out['runtime_s']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
