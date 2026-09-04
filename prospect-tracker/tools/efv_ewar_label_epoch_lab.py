# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR label epoch's measurement (docs/efv-2026-09-03/EWAR_LABEL_EPOCH_GATE.md).

Clauses (b) through (e) live here; clause (f), the blast radius, is `--blast` and is run
at runbook step Z against the pre-epoch snapshot. This lab FITS NOTHING that ships, writes
nothing to prospects.db and edits no shipped code. One artifact:
data/xfv_ewar_label_epoch_eval.json.

WHAT MOVES THE LABEL. `career_war` was rebased to eWAR v2, whose identity is

    eWAR(season) = bWAR(season) + delta_pitch(season) / RPW      (fielding weight 0.0)

so a player-season moves only if it carries PITCHING. The gate registered the hitter side
as the REGEN CONTROL on the premise that the hitter label is byte-identical. THAT PREMISE
IS FALSE and this lab is what found it: 107 of 1,899 hitter rows move, every one of them a
position player who threw in a blowout (183 of the 187 moved seasons are under 10 IP). The
swap re-prices those innings on FIP, which strips the balls in play that are most of the
damage, so it can hand a hitter +0.68 WAR of pitching value for one inning. Hence the
fourth basis below.

THE FOUR LABEL BASES, all built on the SAME rows, the same window and the same weights, so
every comparison is paired and the only thing that varies is the WAR series:

    bwar   career_war.seasons_bwar, the frame the rebase preserved (clause b's
           reconstructibility requirement)
    ewar   career_war.seasons, what the epoch serves
    twin   clause (e)'s zero-information control: the per-season eWAR-minus-bWAR deltas are
           PERMUTED ACROSS PLAYERS within a season and added back to bWAR, so the twin has
           eWAR's marginal distribution and none of its information
    nopp   eWAR except that a season which is position-player mop-up pitching keeps its
           bWAR value. NOT a proposal, a MEASUREMENT: it says how much of the epoch's
           hitter-side movement is the artifact described above.

Run:
    python tools/efv_ewar_label_epoch_lab.py            # clauses b, c, d, e
    python tools/efv_ewar_label_epoch_lab.py --quick    # small B, for wiring checks
    python tools/efv_ewar_label_epoch_lab.py --blast    # clause f, needs the snapshot
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import efv_dataset as ds                    # noqa: E402  READ ONLY
import efv_model as E                       # noqa: E402  READ ONLY
import ewar                                 # noqa: E402  READ ONLY
import storage                              # noqa: E402  READ ONLY

sys.path.insert(0, str(ROOT / "tools"))
import efv_mde_lab as M                     # noqa: E402  the floors' own primitives

OUT_PATH = ROOT / "data" / "xfv_ewar_label_epoch_eval.json"
SNAP_DIR = ROOT.parent / "_pre_epoch_2026-09"

SEED = 20260807                 # the standard's seed; do not change
SIDES = ("hit", "pit")
BASES = ("bwar", "ewar", "twin", "nopp")
TOST_MARGIN = 0.02              # the owner's registered equivalence margin
COHORT_BANDS = ((2011, 2015), (2016, 2019), (2020, 2025))

# The `nopp` basis's rule. A season is POSITION-PLAYER PITCHING when the player batted like
# a regular and pitched like a mop-up man in the same season. Both bounds are needed:
# MIN_PA alone would catch two-way players, MAX_IP alone would catch a starter hurt in April.
POSPITCH_MAX_IP = 15.0
POSPITCH_MIN_PA = 50.0


# ------------------------------------------------------------------ the label bases
def _career_war() -> dict[str, dict]:
    with storage.connect() as con:
        return {r["player_key"]: json.loads(r["payload_json"])
                for r in con.execute("select player_key, payload_json from career_war")}


def _int_seasons(d: dict | None) -> dict[int, float]:
    return {int(y): float(v) for y, v in (d or {}).items() if v is not None}


def _is_pospitch(rec: dict | None) -> bool:
    """True when this eWAR season record is a position player's mop-up inning."""
    if not rec:
        return False
    ip, pa = rec.get("ip"), rec.get("pa")
    if ip is None or pa is None:
        return False
    return 0.0 < float(ip) <= POSPITCH_MAX_IP and float(pa) >= POSPITCH_MIN_PA


def build_series(cw: dict[str, dict], payload: dict, rng: np.random.Generator) -> dict:
    """{basis: {player_key: {year: war}}} plus the receipts the coverage clause needs."""
    out: dict[str, dict] = {b: {} for b in BASES}
    deltas_by_season: dict[int, list[float]] = {}
    owners: dict[int, list[str]] = {}
    pospitch_seasons = 0
    pospitch_players: set[str] = set()
    ewar_seasons = fallback_seasons = 0
    for pk, row in cw.items():
        ew = _int_seasons(row.get("seasons"))
        bw = _int_seasons(row.get("seasons_bwar")) or dict(ew)
        mid = (row.get("ewar_coverage") or {}).get("mlbam")
        out["bwar"][pk] = bw
        out["ewar"][pk] = ew
        nopp = {}
        for y, v in ew.items():
            rec = ewar.ewar_for(mid, y, payload) if mid else None
            if rec and rec.get("ewar") is not None:
                ewar_seasons += 1
            else:
                fallback_seasons += 1
            if _is_pospitch(rec):
                nopp[y] = bw.get(y, v)
                pospitch_seasons += 1
                pospitch_players.add(pk)
            else:
                nopp[y] = v
            deltas_by_season.setdefault(y, []).append(v - bw.get(y, v))
            owners.setdefault(y, []).append(pk)
        out["nopp"][pk] = nopp
    twin = {pk: dict(s) for pk, s in out["bwar"].items()}
    for y, dlist in deltas_by_season.items():
        arr = np.array(dlist, dtype=float)
        perm = rng.permutation(len(arr))
        for pk, d in zip(owners[y], arr[perm]):
            twin[pk][y] = twin[pk].get(y, 0.0) + float(d)
    out["twin"] = twin
    return {"series": out,
            "receipts": {"pospitch_seasons": pospitch_seasons,
                         "pospitch_players": len(pospitch_players),
                         "ewar_seasons": ewar_seasons,
                         "fallback_seasons": fallback_seasons}}


def twin_series(cw: dict[str, dict], rng: np.random.Generator) -> dict[str, dict[int, float]]:
    """Just the zero-information twin, with no eWAR artifact lookups.

    The permutation band needs one of these per draw, so it must not pay for the `nopp`
    basis's per-season record lookup. The construction is identical to build_series's:
    the eWAR-minus-bWAR deltas are permuted across players within a season.
    """
    deltas: dict[int, list[float]] = {}
    owners: dict[int, list[str]] = {}
    twin: dict[str, dict[int, float]] = {}
    for pk, row in cw.items():
        ew = _int_seasons(row.get("seasons"))
        bw = _int_seasons(row.get("seasons_bwar")) or dict(ew)
        twin[pk] = dict(bw)
        for y, v in ew.items():
            deltas.setdefault(y, []).append(v - bw.get(y, v))
            owners.setdefault(y, []).append(pk)
    for y, dlist in deltas.items():
        arr = np.array(dlist, dtype=float)
        for pk, d in zip(owners[y], arr[rng.permutation(len(arr))]):
            twin[pk][y] = twin[pk].get(y, 0.0) + float(d)
    return twin


def relabel(raw: list[dict], series: dict[str, dict[int, float]]) -> list[dict]:
    """The matrix rows with the label recomputed on one WAR series. Bust rows carry a label
    that does not come from career_war and are passed through untouched."""
    out = []
    for r in raw:
        if r.get("kind") != "debuted":
            out.append(r)
            continue
        pk = r.get("player_key")
        dy = r.get("debut_year")
        seasons = series.get(pk)
        if not seasons or dy is None:
            out.append(r)
            continue
        try:
            t_res, t_cens, cflag, w, n_obs = ds._label_6yr(seasons, int(dy), None)
        except ValueError:
            out.append(r)
            continue
        q = dict(r)
        q["target_resolved"] = t_res
        q["target_censored"] = t_cens
        q["censored"] = cflag
        q["weight"] = w
        q["observed_seasons"] = n_obs
        out.append(q)
    return out


def pool_for(side: str, raw: list[dict]) -> dict:
    """Same shape as efv_mde_lab.load_side, from rows already relabelled."""
    deb = [r for r in raw if r["kind"] == "debuted"]
    prep = E._prep(deb, "target_censored", side)
    keys, mono = E._feature_spec(side)
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float)
    return {
        "side": side, "keys": list(keys), "mono": mono, "X": X,
        "y": np.array([r["target"] for r in prep], dtype=float),
        "w": np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None),
        "fv": np.array([r["fv"] for r in prep], dtype=float),
        "dy": np.array([r["decision_year"] for r in prep], dtype=int),
        "pk": [r.get("player_key") for r in prep],
        "lam": E.blend_lambda(side),
        "n": len(prep),
    }


# ------------------------------------------------------------------ the cross chain
def chain_cross(D, y_fit, y_score, sel=None, years=None, lam=None):
    """Forward-chained margin with the FIT label and the SCORE label decoupled.

    Both legs, consensus OLS and the ridge, are fitted on y_fit and scored against y_score,
    so a cell never advantages one leg with information the other lacks.
    """
    years = tuple(E.SCORED_YEARS) if years is None else tuple(years)
    lam = D["lam"] if lam is None else lam
    if sel is None:
        sel = np.arange(D["n"])
    X, w, fv, dy = D["X"][sel], D["w"][sel], D["fv"][sel], D["dy"][sel]
    yf, ysc = y_fit[sel], y_score[sel]
    YR, C, B, T, W = [], [], [], [], []
    for yr in years:
        tr = np.flatnonzero(dy < yr)
        te = np.flatnonzero(dy == yr)
        if len(te) < 15 or len(tr) < 60:
            continue
        o = M.ols_fit(fv[tr], yf[tr])
        rg = M.ridge_fit(X[tr], yf[tr], w[tr])
        if o is None or rg is None:
            continue
        cons = np.maximum(0.0, o[0] + o[1] * fv[te])
        mod = M.ridge_pred(rg, X[te])
        YR.append(np.full(len(te), yr))
        C.append(cons)
        B.append((1 - lam) * cons + lam * mod)
        T.append(ysc[te])
        W.append(w[te])
    if not B:
        return None
    return tuple(np.concatenate(a) for a in (YR, C, B, T, W))


def margin_of(parts, weighted=True):
    if parts is None:
        return None
    _yr, cons, blend, tgt, w = parts
    ww = w if weighted else None
    c = float(M.wrho(cons, tgt, ww))
    b = float(M.wrho(blend, tgt, ww))
    return {"n": int(len(tgt)), "consensus": round(c, 5), "blend": round(b, 5),
            "margin": round(b - c, 5)}


def margin_from_parts(parts, sel, weighted=True):
    """A margin on a bootstrap resample of the SCORED rows (E_cond: no refit)."""
    _yr, cons, blend, tgt, w = parts
    ww = w[sel] if weighted else None
    return float(M.wrho(blend[sel], tgt[sel], ww)) - float(M.wrho(cons[sel], tgt[sel], ww))


def per_fold_margins(D, y_fit, y_score):
    out = {}
    for yr in E.SCORED_YEARS:
        m = margin_of(chain_cross(D, y_fit, y_score, years=(yr,)))
        if m:
            out[str(yr)] = m["margin"]
    return out


# ------------------------------------------------------------------ clause (c)
def coverage(cw: dict[str, dict], pools: dict, payload: dict) -> dict:
    """Share of LABEL SEASONS served by eWAR against bWAR fallback, by side and cohort band."""
    out = {}
    for side in SIDES:
        D = pools[side]
        by_band = {}
        for lo, hi in COHORT_BANDS:
            n_lab = n_ew = 0
            no_id = 0
            players = 0
            for pk, dyv in zip(D["pk"], D["dy"]):
                row = cw.get(pk)
                if not row:
                    continue
                dy = int(dyv)
                if not (lo <= dy <= hi):
                    continue
                players += 1
                mid = (row.get("ewar_coverage") or {}).get("mlbam")
                if mid is None:
                    no_id += 1
                seasons = _int_seasons(row.get("seasons"))
                for y in range(dy, dy + ds.TARGET_SEASONS):
                    if y > ds.RESOLVED_THROUGH or y not in seasons:
                        continue
                    n_lab += 1
                    rec = ewar.ewar_for(mid, y, payload) if mid else None
                    if rec and rec.get("ewar") is not None:
                        n_ew += 1
            by_band[f"{lo}-{hi}"] = {
                "players": players, "label_seasons": n_lab, "join_ewar": n_ew,
                "share": round(n_ew / n_lab, 4) if n_lab else None,
                "players_no_id": no_id,
                "under_90_pct": bool(n_lab and (n_ew / n_lab) < 0.90),
            }
        out[side] = by_band
    return out


# ------------------------------------------------------------------ the main measurement
def run(B_cond: int, B_refit: int, B_perm: int, write: bool = True) -> dict:
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    payload = ewar.load()
    cw = _career_war()
    built = build_series(cw, payload, rng)
    series, receipts = built["series"], built["receipts"]
    print(f"series built: {receipts}", flush=True)

    from efv_dataset import matrix_path
    pools: dict[str, dict] = {}
    ys: dict[str, dict[str, np.ndarray]] = {}
    for side in SIDES:
        raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        base_pool = None
        ys[side] = {}
        for b in BASES:
            P = pool_for(side, relabel(raw, series[b]))
            if base_pool is None:
                base_pool = P
            elif P["pk"] != base_pool["pk"]:
                raise SystemExit(f"basis {b} changed the {side} row set; comparisons "
                                 f"would not be paired")
            ys[side][b] = P["y"]
        pools[side] = base_pool
        print(f"  {side}: {base_pool['n']} rows, lambda {base_pool['lam']}", flush=True)

    # ---- clause (b): the cross-label matrix, plus the two extra bases
    cross = {}
    for side in SIDES:
        D = pools[side]
        cells = {}
        for fit_b in BASES:
            for sc_b in ("bwar", "ewar"):
                m = margin_of(chain_cross(D, ys[side][fit_b], ys[side][sc_b]))
                if m:
                    cells[f"fit_{fit_b}__score_{sc_b}"] = m
        same_e = cells["fit_ewar__score_ewar"]["margin"]
        same_b = cells["fit_bwar__score_bwar"]["margin"]
        cells["_diagonal_difference"] = round(same_e - same_b, 5)
        cells["_reading"] = (
            "diagonal difference = the swap's effect on the margin. The off-diagonal cells "
            "separate 'the model learned the new label' (fit_ewar__score_bwar) from 'the "
            "label got easier for everyone' (fit_bwar__score_ewar).")
        cross[side] = cells

    # ---- clause (e) 3: per-fold signs on the diagonal difference
    folds = {}
    for side in SIDES:
        D = pools[side]
        fe = per_fold_margins(D, ys[side]["ewar"], ys[side]["ewar"])
        fb = per_fold_margins(D, ys[side]["bwar"], ys[side]["bwar"])
        common = sorted(set(fe) & set(fb))
        diffs = {y: round(fe[y] - fb[y], 5) for y in common}
        pos = sum(1 for v in diffs.values() if v > 0)
        folds[side] = {"n_folds": len(common), "per_fold_difference": diffs,
                       "folds_positive": pos, "folds_negative": len(common) - pos,
                       "meets_4_fold_rule": len(common) >= 4}

    # ---- clause (d): TOST on the diagonal difference, E_cond primary
    tost = {}
    boot = {}
    for side in SIDES:
        D = pools[side]
        pe = chain_cross(D, ys[side]["ewar"], ys[side]["ewar"])
        pb = chain_cross(D, ys[side]["bwar"], ys[side]["bwar"])
        n_te = len(pe[3])
        point = margin_of(pe)["margin"] - margin_of(pb)["margin"]
        cond = []
        for _ in range(B_cond):
            sel = rng.integers(0, n_te, n_te)
            cond.append(margin_from_parts(pe, sel) - margin_from_parts(pb, sel))
        cond = np.array([v for v in cond if np.isfinite(v)], dtype=float)
        refit = []
        for i in range(B_refit):
            sel = rng.integers(0, D["n"], D["n"])
            a = margin_of(chain_cross(D, ys[side]["ewar"], ys[side]["ewar"], sel=sel))
            b = margin_of(chain_cross(D, ys[side]["bwar"], ys[side]["bwar"], sel=sel))
            if a and b:
                refit.append(a["margin"] - b["margin"])
            if B_refit >= 100 and (i + 1) % 100 == 0:
                print(f"  {side} E_refit {i+1}/{B_refit}  {time.time()-t0:.0f}s", flush=True)
        refit = np.array([v for v in refit if np.isfinite(v)], dtype=float)

        def _ci(a):
            if not len(a):
                return None
            return [round(float(np.percentile(a, 2.5)), 5),
                    round(float(np.percentile(a, 97.5)), 5)]

        ci_c = _ci(cond)
        disp = "UNDECIDED"
        if ci_c:
            if ci_c[0] >= -TOST_MARGIN and ci_c[1] <= TOST_MARGIN:
                disp = "RULED OUT (equivalent within the registered margin)"
            elif ci_c[0] > TOST_MARGIN:
                disp = "SWAP GAIN"
            elif ci_c[1] < -TOST_MARGIN:
                disp = "SWAP LOSS"
        tost[side] = {
            "point_difference": round(float(point), 5),
            "E_cond_ci95": ci_c, "E_cond_sd": round(float(cond.std(ddof=1)), 5) if len(cond) > 1 else None,
            "E_refit_ci95": _ci(refit),
            "E_refit_sd": round(float(refit.std(ddof=1)), 5) if len(refit) > 1 else None,
            "tost_margin": TOST_MARGIN, "disposition": disp,
            "estimator_note": "E_cond is primary; E_refit is reported beside it.",
        }
        boot[side] = {"B_cond_used": int(len(cond)), "B_refit_used": int(len(refit))}

    # ---- clause (e) 1 and 2: the twin and the permutation band
    controls = {}
    for side in SIDES:
        D = pools[side]
        twin_m = margin_of(chain_cross(D, ys[side]["twin"], ys[side]["twin"]))
        same_e = cross[side]["fit_ewar__score_ewar"]["margin"]
        same_b = cross[side]["fit_bwar__score_bwar"]["margin"]
        band = []
        raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        for i in range(B_perm):
            s2 = twin_series(cw, np.random.default_rng(SEED + 1000 + i))
            P = pool_for(side, relabel(raw, s2))
            if P["pk"] != D["pk"]:
                continue
            m = margin_of(chain_cross(D, P["y"], P["y"]))
            if m:
                band.append(m["margin"] - same_b)
            if B_perm >= 20 and (i + 1) % 20 == 0:
                print(f"  {side} perm {i+1}/{B_perm}  {time.time()-t0:.0f}s", flush=True)
        band = np.array(band, dtype=float)
        obs = same_e - same_b
        controls[side] = {
            "zero_information_twin_margin": twin_m,
            "twin_minus_bwar": round(twin_m["margin"] - same_b, 5) if twin_m else None,
            "observed_difference": round(obs, 5),
            "permutation_B": int(len(band)),
            "permutation_band_ci95": ([round(float(np.percentile(band, 2.5)), 5),
                                       round(float(np.percentile(band, 97.5)), 5)]
                                      if len(band) else None),
            "p_two_sided": (round(float((np.abs(band) >= abs(obs)).mean()), 4)
                            if len(band) else None),
            "reading": ("if the twin's difference matches the observed one, there is no "
                        "result to attribute to the FIP swap"),
        }

    # ---- the nopp finding, quantified
    pospitch = {}
    for side in SIDES:
        ye, yn = ys[side]["ewar"], ys[side]["nopp"]
        moved = np.flatnonzero(np.abs(ye - yn) > 1e-9)
        pospitch[side] = {
            "rows_whose_label_the_swap_moved_via_position_player_pitching": int(len(moved)),
            "of_rows": int(pools[side]["n"]),
            "mean_label_inflation_WAR": round(float((ye - yn)[moved].mean()), 4) if len(moved) else 0.0,
            "max_label_inflation_WAR": round(float((ye - yn)[moved].max()), 4) if len(moved) else 0.0,
            "margin_ewar": cross[side]["fit_ewar__score_ewar"]["margin"],
            "margin_nopp": margin_of(chain_cross(pools[side], yn, yn))["margin"],
        }
        pospitch[side]["margin_cost_of_the_artifact"] = round(
            pospitch[side]["margin_ewar"] - pospitch[side]["margin_nopp"], 5)

    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "produced_by": "tools/efv_ewar_label_epoch_lab.py",
        "gate": "docs/efv-2026-09-03/EWAR_LABEL_EPOCH_GATE.md",
        "seed": SEED,
        "elapsed_s": round(time.time() - t0, 1),
        "bootstrap": boot,
        "label_bases": {
            "definitions": {
                "bwar": "career_war.seasons_bwar (the preserved frame)",
                "ewar": "career_war.seasons (what the epoch serves)",
                "twin": "bWAR plus the eWAR-minus-bWAR deltas permuted across players within a season",
                "nopp": f"eWAR except seasons with IP <= {POSPITCH_MAX_IP} and PA >= {POSPITCH_MIN_PA}, which keep bWAR",
            },
            "receipts": receipts,
        },
        "clause_b_cross_label_matrix": cross,
        "clause_c_coverage": coverage(cw, pools, payload),
        "clause_d_tost": tost,
        "clause_e_controls": controls,
        "clause_e_folds": folds,
        "position_player_pitching_finding": pospitch,
        "clause_f_blast_radius": "run tools/efv_ewar_label_epoch_lab.py --blast at runbook step Z",
    }
    if write:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("wrote", OUT_PATH)
    return out


# ------------------------------------------------------------------ clause (f)
def blast(write: bool = True) -> dict:
    """Diff the served artifacts against the pre-epoch snapshot (runbook step A)."""
    if not SNAP_DIR.exists():
        raise SystemExit(f"no snapshot at {SNAP_DIR}; clause (f) cannot be measured")

    def _load(name):
        a = SNAP_DIR / name
        b = ROOT / "data" / name
        if not a.exists() or not b.exists():
            return None, None
        return (json.loads(a.read_text(encoding="utf-8")),
                json.loads(b.read_text(encoding="utf-8")))

    # The snapshot lives OUTSIDE the repo, so its absolute path names the build machine and
    # the operator's home directory. data/*.json is published, and
    # test_published_payload_hygiene refuses absolute build-machine paths in published
    # payloads for exactly that reason. Record the directory NAME, which is the part a
    # reader needs in order to know which snapshot this was diffed against.
    out: dict = {"snapshot": SNAP_DIR.name,
                 "snapshot_note": "a sibling directory of the repo root, not published"}
    old, new = _load("xfv.json")
    if old and new:
        ob, nb = old.get("by_player", {}), new.get("by_player", {})
        shared = sorted(set(ob) & set(nb))

        def _ranked(bp, keys):
            vals = [(k, bp[k].get("xfv_war_6yr")) for k in keys]
            vals = [(k, v) for k, v in vals if isinstance(v, (int, float))]
            vals.sort(key=lambda kv: -kv[1])
            return {k: i + 1 for i, (k, _) in enumerate(vals)}

        ro, rn = _ranked(ob, shared), _ranked(nb, shared)
        common = sorted(set(ro) & set(rn))
        d = np.array([abs(ro[k] - rn[k]) for k in common], dtype=float)
        gd = [abs((nb[k].get("xfv_grade") or 0) - (ob[k].get("xfv_grade") or 0)) for k in common]
        gd = np.array([g for g in gd if np.isfinite(g)], dtype=float)
        out["board"] = {
            "rows_compared": len(common),
            "rows_moved": int((d > 0).sum()),
            "rank_delta_median": float(np.median(d)) if len(d) else None,
            "rank_delta_p90": float(np.percentile(d, 90)) if len(d) else None,
            "rank_delta_max": float(d.max()) if len(d) else None,
            "grade_moved_rows": int((gd > 1e-9).sum()) if len(gd) else 0,
            "grade_delta_mean": round(float(gd.mean()), 4) if len(gd) else None,
        }
        for cut in (10, 25, 100, 250):
            a = {k for k in common if ro[k] <= cut}
            b = {k for k in common if rn[k] <= cut}
            out["board"][f"membership_change_top{cut}"] = len(a ^ b) // 2
    old, new = _load("star_label_view.json")
    if old and new:
        def _flat(o):
            """`players` is a LIST of rows keyed by player_key, not a dict. Reading it as
            a dict compared the eight top-level metadata keys and reported 2 changes, which
            looked like a star-label result and was not one."""
            if isinstance(o, dict):
                for k in ("by_player", "players", "rows"):
                    v = o.get(k)
                    if isinstance(v, dict):
                        return v
                    if isinstance(v, list):
                        return {r.get("player_key"): r for r in v
                                if isinstance(r, dict) and r.get("player_key")}
            return o if isinstance(o, dict) else {}
        a, b = _flat(old), _flat(new)
        keys = set(a) & set(b)

        def _star(r):
            for k in ("is_star", "star", "star_window", "star_career"):
                if k in r:
                    return bool(r[k])
            return None
        flips = sum(1 for k in keys if _star(a[k]) != _star(b[k]))
        changed = sum(1 for k in keys
                      if json.dumps(a[k], sort_keys=True) != json.dumps(b[k], sort_keys=True))
        out["star_label"] = {
            "compared": len(keys), "star_flag_flips": flips, "rows_changed_any_field": changed,
            "added": len(set(b) - set(a)), "dropped": len(set(a) - set(b)),
        }
    if write:
        p = ROOT / "data" / "xfv_ewar_label_epoch_blast.json"
        p.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("wrote", p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true", help="small B, for wiring checks")
    ap.add_argument("--blast", action="store_true", help="clause (f) against the snapshot")
    ap.add_argument("--b-cond", type=int, default=2000)
    ap.add_argument("--b-refit", type=int, default=400)
    ap.add_argument("--b-perm", type=int, default=200)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    if a.blast:
        print(json.dumps(blast(write=not a.no_write), indent=1))
        return 0
    if a.quick:
        a.b_cond, a.b_refit, a.b_perm = 50, 5, 3
    out = run(a.b_cond, a.b_refit, a.b_perm, write=not a.no_write)
    print(json.dumps({"clause_b": out["clause_b_cross_label_matrix"],
                      "clause_d": out["clause_d_tost"],
                      "pospitch": out["position_player_pitching_finding"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
