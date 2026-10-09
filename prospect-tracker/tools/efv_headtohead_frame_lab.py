# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""M-1 floor lab: the head-to-head MDE95 on BOTH frames, from the same draws.

Pre-registration: docs/efv-2026-08-13/HEADTOHEAD_FRAME_GATE.md.

`tools/efv_mde_lab.py headtohead` derives the floor for the INCUMBENT frame, in
which a player's frozen pre-debut eFV grade is scored against consensus reads
from base years AFTER he debuted. This lab derives the floor for the CORRECTED
frame (those rows removed) and re-derives the incumbent one BESIDE it, in the
same run, from the SAME resampled draws at the same seed.

Two reasons that matters. A floor measured on one vintage against a delta
measured on another has crossed a verdict boundary twice in this program, so the
incumbent is never read off a stored constant here. And because both frames are
scored inside a single draw, the two are perfectly PAIRED, which also yields the
sd of the DIFFERENCE and lets the lab say whether the frames are distinguishable
rather than merely different.

Mechanics reuse `efv_mde_lab`'s primitives so the frames stay comparable to the
published floor: the same cluster paired bootstrap (resample the eFV matrix pool
BY PLAYER, refit the forward chain inside every draw, score both legs on the
common-set rows the resampled players own), the same one-sided 1.645*sd
convention. The pre-debut mask rides along in the per-row payload rather than
being recomputed, using the channel-recovery technique B-L6 documented:
`_h2h_pass`'s fold selection never touches `rows`, so a pool copy whose rows
carry a wider tuple returns the extra channel in the SAME emission order.

Usage:
    python tools/efv_headtohead_frame_lab.py [B]        # default 2000
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_model as E                                    # noqa: E402
from efv_mde_lab import SIDES, SEED, ols_fit, ridge_fit, ridge_pred, wrho  # noqa: E402


def _load_h2h_framed():
    """`efv_mde_lab._load_h2h`, with a pre-debut flag added to every scored row.

    Row payload is (consensus_fv, war, is_predebut) instead of (consensus_fv,
    war). The eligibility rule is the one already used by
    `source_backtest._xfv_vs_consensus_detail` and `_archetype_accuracy`: a base
    year strictly LATER than the debut year is a post-debut read; a base year
    EQUAL to the debut year is a preseason read and stays eligible.
    """
    import source_backtest as SB
    from efv_dataset import matrix_path
    uni = SB._load_universe(SB.DATA_DIR)
    years = SB._resolved_years(uni, SB.date.today().year)
    raters = list(SB.SCORED_SOURCES) + [SB.CONSENSUS_KEY]
    by_key: dict[str, list] = {}
    for p in uni:
        out = SB._outcome(p)
        dyr = out.get("debut_year")
        for y in years:
            g = SB._rater_grades_for_year(p, y)
            if g and all(r in g for r in raters):
                pre = (dyr is None) or (y <= dyr)
                by_key.setdefault(p.get("player_key"), []).append(
                    (float(g[SB.CONSENSUS_KEY]), float(out["war"]), bool(pre), int(y)))
    pools = {}
    for side in SIDES:
        raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        full = [r for r in raw if not (r["kind"] == "bust" and r.get("bust_recent"))]
        prep = E._prep(full, "target_censored", side)
        keys, _m = E._feature_spec(side)
        pools[side] = {
            "side": side, "keys": list(keys),
            "X": np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float),
            "y": np.array([r["target"] for r in prep], dtype=float),
            "w": np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None),
            "fv": np.array([r["fv"] for r in prep], dtype=float),
            "dy": np.array([r["decision_year"] for r in prep], dtype=int),
            "lam": E.blend_lambda(side),
            "n": len(prep),
            "rows": [by_key.get(r["player_key"]) or [] for r in prep],
        }
    return pools, len(by_key)


def _h2h_pass_framed(P, sel=None):
    """One forward-chained pass. Returns (efv, consensus, war, is_predebut, is_vintage_matched).

    Byte-for-byte the fold logic of `efv_mde_lab._h2h_pass`; the only difference
    is that the row payload carries extra channels which are emitted as masks.

    The SECOND mask is the adversarial control on this whole lane. eFV holds ONE
    grade per player, fitted at that player's decision year. A common-set row from
    a base year EARLIER than the decision year therefore compares eFV's grade
    against a consensus read taken before it, where eFV is the side holding extra
    information. The post-debut strip removes the rows where the CONSENSUS is
    advantaged and leaves those rows untouched, so the corrected frame is not
    symmetric and its margin must be read beside the vintage-matched cell, where
    base year == decision year and neither side has a timing edge.
    """
    G, C, T, M, V = [], [], [], [], []
    for side, D in P.items():
        s = np.arange(D["n"]) if sel is None else sel[side]
        X, y, w, fv, dy = D["X"][s], D["y"][s], D["w"][s], D["fv"][s], D["dy"][s]
        rows = [D["rows"][i] for i in s]
        lam = D["lam"]
        for yr in E.SCORED_YEARS:
            tr = np.flatnonzero(dy < yr)
            te = np.flatnonzero(dy == yr)
            if len(te) < 15 or len(tr) < 60:
                continue
            o = ols_fit(fv[tr], y[tr])
            rg = ridge_fit(X[tr], y[tr], w[tr])
            if o is None or rg is None:
                continue
            cal = E._fit_linear_calibration(
                list(zip(ridge_pred(rg, X[tr]).tolist(), y[tr].tolist())))
            a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
            cons = np.maximum(0.0, o[0] + o[1] * fv[te])
            mod = np.maximum(-2.0, a + b * ridge_pred(rg, X[te]))
            grade = (1 - lam) * cons + lam * mod
            for j, i in enumerate(te):
                dec_yr = int(dy[te[j]])
                for payload in rows[i]:
                    cfv, war, pre, base_yr = payload
                    G.append(grade[j])
                    C.append(cfv)
                    T.append(war)
                    M.append(pre)
                    V.append(base_yr == dec_yr)
    if not G:
        return None
    return (np.array(G), np.array(C), np.array(T),
            np.array(M, dtype=bool), np.array(V, dtype=bool))


def _deltas(g, c, t, m, v):
    """(all rows, pre-debut rows, vintage-matched rows)."""
    d_all = wrho(g, t) - wrho(c, t)
    d_pre = (wrho(g[m], t[m]) - wrho(c[m], t[m])) if m.sum() >= 40 else np.nan
    d_vin = (wrho(g[v], t[v]) - wrho(c[v], t[v])) if v.sum() >= 40 else np.nan
    return d_all, d_pre, d_vin


def run(B: int = 2000, write: bool = True):
    P, n_common_players = _load_h2h_framed()
    pt = _h2h_pass_framed(P)
    if pt is None:
        raise SystemExit("no scored rows")
    g, c, t, m, v = pt

    point = {
        "incumbent": {
            "n_rows": int(len(t)),
            "efv": round(float(wrho(g, t)), 5),
            "consensus": round(float(wrho(c, t)), 5),
        },
        "corrected": {
            "n_rows": int(m.sum()),
            "efv": round(float(wrho(g[m], t[m])), 5),
            "consensus": round(float(wrho(c[m], t[m])), 5),
        },
        "removed": {
            "n_rows": int((~m).sum()),
            "efv": round(float(wrho(g[~m], t[~m])), 5),
            "consensus": round(float(wrho(c[~m], t[~m])), 5),
        },
        "vintage_matched": {
            "n_rows": int(v.sum()),
            "efv": round(float(wrho(g[v], t[v])), 5),
            "consensus": round(float(wrho(c[v], t[v])), 5),
        },
    }
    for k in point:
        point[k]["delta"] = round(point[k]["efv"] - point[k]["consensus"], 5)

    rng = np.random.default_rng(SEED + 1)
    d_all_draws, d_pre_draws, d_vin_draws = [], [], []
    t0 = time.time()
    for i in range(B):
        sel = {s: rng.integers(0, P[s]["n"], P[s]["n"]) for s in P}
        r = _h2h_pass_framed(P, sel)
        if r is None:
            continue
        gg, cc, tt, mm, vv = r
        d_all, d_pre, d_vin = _deltas(gg, cc, tt, mm, vv)
        if np.isfinite(d_all) and np.isfinite(d_pre) and np.isfinite(d_vin):
            d_all_draws.append(d_all)
            d_pre_draws.append(d_pre)
            d_vin_draws.append(d_vin)
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{B}  {time.time()-t0:.0f}s", flush=True)

    a_all = np.array(d_all_draws, dtype=float)
    a_pre = np.array(d_pre_draws, dtype=float)
    a_vin = np.array(d_vin_draws, dtype=float)
    a_dif = a_pre - a_all

    def _cell(point_delta, arr):
        sd = float(arr.std(ddof=1))
        return {
            "delta": round(float(point_delta), 5),
            "sd": round(sd, 5),
            "mde95": round(1.645 * sd, 4),
            "mde95_twosided": round(1.96 * sd, 4),
            "ci95": [round(float(np.percentile(arr, 2.5)), 5),
                     round(float(np.percentile(arr, 97.5)), 5)],
            "p_gt_0": round(float((arr > 0).mean()), 4),
            "margin_x_floor": (round(float(point_delta) / (1.645 * sd), 3)
                               if sd > 0 else None),
            "resolvable": bool(abs(point_delta) >= 1.645 * sd),
            "verdict": (
                "beats consensus" if (point_delta > 0 and abs(point_delta) >= 1.645 * sd)
                else "loses to consensus" if (point_delta < 0 and abs(point_delta) >= 1.645 * sd)
                else "not resolvable at this power"),
        }

    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "produced_by": "tools/efv_headtohead_frame_lab.py",
        "pre_registration": "docs/efv-2026-08-13/HEADTOHEAD_FRAME_GATE.md",
        "basis": {
            "scored_years": list(E.SCORED_YEARS),
            "common_set_players": n_common_players,
            "frames": {
                "incumbent": "every eFV-covered common-set row, all base years",
                "corrected": ("post-debut consensus reads removed; a base year equal "
                              "to the debut year is a preseason read and is kept"),
            },
        },
        "protocol": (
            "cluster paired bootstrap, resampled BY PLAYER over the eFV matrix pool, "
            "forward chain refit inside every draw, both legs scored on the common-set "
            "rows the resampled players own. BOTH FRAMES ARE SCORED INSIDE THE SAME "
            "DRAW, so the incumbent is re-derived here rather than read off a stored "
            "constant, and the two frames are paired. MDE95 = 1.645 * sd(delta), "
            "one-sided, matching the convention of the floor it supersedes."),
        "B_requested": int(B), "B_used": int(len(a_all)), "seed": SEED + 1,
        "elapsed_s": round(time.time() - t0, 1),
        "point": point,
        "incumbent": _cell(point["incumbent"]["delta"], a_all),
        "corrected": _cell(point["corrected"]["delta"], a_pre),
        "vintage_matched": _cell(point["vintage_matched"]["delta"], a_vin),
        "asymmetry_control": {
            "question": ("does the corrected frame win because the strip removed the "
                         "consensus's timing advantage, or because it KEPT eFV's?"),
            "mechanism": ("eFV holds one grade per player, fitted at the decision "
                          "year. Rows from an EARLIER base year compare that grade "
                          "against a consensus read taken before it, where eFV is the "
                          "side with extra information. The strip removes only the "
                          "rows where the consensus is advantaged, so the corrected "
                          "frame is not symmetric."),
            "reading": ("if vintage_matched resolves in the same direction, the "
                        "corrected win is not an artifact of that asymmetry. If "
                        "vintage_matched is a tie, the corrected margin depends on "
                        "rows where eFV had more information and MUST be reported "
                        "with that qualifier."),
        },
        "paired_difference": {
            "delta": round(point["corrected"]["delta"] - point["incumbent"]["delta"], 5),
            "sd": round(float(a_dif.std(ddof=1)), 5),
            "ci95": [round(float(np.percentile(a_dif, 2.5)), 5),
                     round(float(np.percentile(a_dif, 97.5)), 5)],
            "note": ("the frames share their draws, so this is the sd of the paired "
                     "difference and not the difference of two independent sds"),
        },
        "direction_control": {
            "consensus_rho_retained": round(float(wrho(c[m], t[m])), 5),
            "consensus_rho_removed": round(float(wrho(c[~m], t[~m])), 5),
            "mechanism_holds": bool(wrho(c[~m], t[~m]) > wrho(c[m], t[m])),
            "note": ("the mechanism predicts the consensus orders the REMOVED rows "
                     "better, because on those it is grading players it has already "
                     "seen in the majors"),
        },
    }
    if write:
        p = ROOT / "data" / "xfv_headtohead_frame_eval.json"
        p.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("wrote", p)
    print(json.dumps(out, indent=1))
    return out


# ---------------------------------------------------------------------------
# EFV3_A5: the E_refit floor of frame version vm3 (the consensus-present rule), with
# the both-source (vm1 rule) vintage-matched floor re-derived beside it from the SAME
# draws. The spec's E_refit instrument is this lab's (tools/efv_mde_lab.py headtohead
# mechanics: resample the eFV matrix pool by player, refit the v1 forward chain in
# every draw, score both legs on the rows the resampled players own). As on the vm2
# headline, whose floor is carried from vm1, eFV here is v1 refit with the MATRIX
# consensus input, not the timing-pinned one; the development read's rows apply the
# pin, so its n sits at or under this lab's. Seed: source_backtest._CLAIM_SEED, the
# registered resampler's.
# ---------------------------------------------------------------------------

VM3_FLOOR_PATH = ROOT / "data" / "efv_vm3_frame_floor.json"


def _load_h2h_vm3():
    """`_load_h2h_framed` under the CONSENSUS-PRESENT rule (EFV3_A5): a player's
    payload rows are every resolved base year with an in-window PROSPX consensus read,
    each tagged with whether FanGraphs and MLB Pipeline BOTH graded it (the vm1 and vm2
    membership rule). Payload: (consensus_fv, war, is_common, base_year)."""
    import source_backtest as SB
    from efv_dataset import matrix_path
    uni = SB._load_universe(SB.DATA_DIR)
    years = SB._resolved_years(uni, SB.date.today().year)
    by_key: dict[str, list] = {}
    for p in uni:
        out = SB._outcome(p)
        for y in years:
            g = SB._rater_grades_for_year(p, y)
            if not g or SB.CONSENSUS_KEY not in g:
                continue
            common = all(r in g for r in SB.SCORED_SOURCES)
            by_key.setdefault(p.get("player_key"), []).append(
                (float(g[SB.CONSENSUS_KEY]), float(out["war"]), bool(common), int(y)))
    pools = {}
    for side in SIDES:
        raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
        full = [r for r in raw if not (r["kind"] == "bust" and r.get("bust_recent"))]
        prep = E._prep(full, "target_censored", side)
        keys, _m = E._feature_spec(side)
        pools[side] = {
            "side": side, "keys": list(keys),
            "X": np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float),
            "y": np.array([r["target"] for r in prep], dtype=float),
            "w": np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None),
            "fv": np.array([r["fv"] for r in prep], dtype=float),
            "dy": np.array([r["decision_year"] for r in prep], dtype=int),
            "lam": E.blend_lambda(side),
            "n": len(prep),
            "rows": [by_key.get(r["player_key"]) or [] for r in prep],
        }
    return pools, len(by_key), years


def _h2h_pass_vm3(P, sel=None):
    """One forward-chained pass under the consensus-present payload. Returns
    (efv, consensus, war, is_vm3, is_vm_common): the vintage-matched mask (base year
    equals the decision year) and the same mask restricted to both-source rows. The
    fold logic is `_h2h_pass_framed`'s byte for byte."""
    G, C, T, V3, VC = [], [], [], [], []
    for side, D in P.items():
        s = np.arange(D["n"]) if sel is None else sel[side]
        X, y, w, fv, dy = D["X"][s], D["y"][s], D["w"][s], D["fv"][s], D["dy"][s]
        rows = [D["rows"][i] for i in s]
        lam = D["lam"]
        for yr in E.SCORED_YEARS:
            tr = np.flatnonzero(dy < yr)
            te = np.flatnonzero(dy == yr)
            if len(te) < 15 or len(tr) < 60:
                continue
            o = ols_fit(fv[tr], y[tr])
            rg = ridge_fit(X[tr], y[tr], w[tr])
            if o is None or rg is None:
                continue
            cal = E._fit_linear_calibration(
                list(zip(ridge_pred(rg, X[tr]).tolist(), y[tr].tolist())))
            a, b = (cal["a"], cal["b"]) if cal else (0.0, 1.0)
            cons = np.maximum(0.0, o[0] + o[1] * fv[te])
            mod = np.maximum(-2.0, a + b * ridge_pred(rg, X[te]))
            grade = (1 - lam) * cons + lam * mod
            for j, i in enumerate(te):
                dec_yr = int(dy[te[j]])
                for cfv, war, common, base_yr in rows[i]:
                    G.append(grade[j])
                    C.append(cfv)
                    T.append(war)
                    V3.append(base_yr == dec_yr)
                    VC.append(base_yr == dec_yr and common)
    if not G:
        return None
    return (np.array(G), np.array(C), np.array(T),
            np.array(V3, dtype=bool), np.array(VC, dtype=bool))


def _label_stamp() -> dict:
    """The label the floor was measured on (EFV3_A5: provider and resolved_through
    stamped on every read)."""
    import efv_dataset as _ed
    import war_source as _ws
    return {"provider": _ws.DEFAULT_PROVIDER, "resolved_through": _ed.RESOLVED_THROUGH}


def run_vm3(B: int = 2000, write: bool = True, seed: int | None = None):
    import source_backtest as SB
    seed = SB._CLAIM_SEED if seed is None else int(seed)
    P, n_players, years = _load_h2h_vm3()
    pt = _h2h_pass_vm3(P)
    if pt is None:
        raise SystemExit("no scored rows")
    g, c, t, v3, vc = pt
    point = {
        "vm3": {"n_rows": int(v3.sum()), "efv": round(float(wrho(g[v3], t[v3])), 5),
                "consensus": round(float(wrho(c[v3], t[v3])), 5)},
        "vintage_matched_common": {"n_rows": int(vc.sum()),
                                   "efv": round(float(wrho(g[vc], t[vc])), 5),
                                   "consensus": round(float(wrho(c[vc], t[vc])), 5)},
    }
    for k in point:
        point[k]["delta"] = round(point[k]["efv"] - point[k]["consensus"], 5)
    rng = np.random.default_rng(seed)
    d3, dc = [], []
    t0 = time.time()
    for i in range(B):
        sel = {s: rng.integers(0, P[s]["n"], P[s]["n"]) for s in P}
        r = _h2h_pass_vm3(P, sel)
        if r is None:
            continue
        gg, cc, tt, m3, mc = r
        a3 = (wrho(gg[m3], tt[m3]) - wrho(cc[m3], tt[m3])) if m3.sum() >= 40 else np.nan
        ac = (wrho(gg[mc], tt[mc]) - wrho(cc[mc], tt[mc])) if mc.sum() >= 40 else np.nan
        if np.isfinite(a3) and np.isfinite(ac):
            d3.append(a3)
            dc.append(ac)
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{B}  {time.time()-t0:.0f}s", flush=True)
    a3 = np.array(d3, dtype=float)
    ac = np.array(dc, dtype=float)
    ad = a3 - ac

    def _cell(point_delta, arr):
        sd = float(arr.std(ddof=1))
        return {"delta": round(float(point_delta), 5), "sd": round(sd, 5),
                "mde95": round(1.645 * sd, 4), "mde95_twosided": round(1.96 * sd, 4),
                "ci95": [round(float(np.percentile(arr, 2.5)), 5),
                         round(float(np.percentile(arr, 97.5)), 5)],
                "p_gt_0": round(float((arr > 0).mean()), 4),
                "estimator": "E_refit",
                "reading": "development only; a floor, not a claim"}

    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "produced_by": "tools/efv_headtohead_frame_lab.py vm3",
        "task": "EFV3_A5",
        "role": "development",
        "label": _label_stamp(),
        "basis": {
            "scored_years": list(E.SCORED_YEARS),
            "window": [min(years), max(years)] if years else None,
            "consensus_present_players": n_players,
            "frames": {
                "vm3": ("vintage-matched rows (base year equal to the decision year) "
                        "under the consensus-present rule: an in-window PROSPX "
                        "consensus read, FanGraphs and MLB Pipeline optional"),
                "vintage_matched_common": ("the same rows restricted to those FanGraphs "
                                           "and MLB Pipeline both graded (the vm1 and "
                                           "vm2 membership rule), re-derived here"),
            },
            "efv": ("eFV v1 refit in every draw, scored with the MATRIX consensus "
                    "input (the vm1 convention carried by the vm2 headline); the "
                    "development read applies the timing pin to its rows, so its n "
                    "sits at or under this lab's"),
        },
        "protocol": ("cluster paired bootstrap, resampled BY PLAYER over the eFV matrix "
                     "pool, forward chain refit inside every draw, both legs scored on "
                     "the consensus-present rows the resampled players own; both frames "
                     "scored inside the same draw. MDE95 = 1.645 * sd(delta), one-sided"),
        "B_requested": int(B), "B_used": int(len(a3)), "seed": seed,
        "elapsed_s": round(time.time() - t0, 1),
        "point": point,
        "vm3": _cell(point["vm3"]["delta"], a3),
        "vintage_matched_common": _cell(point["vintage_matched_common"]["delta"], ac),
        "paired_difference": {
            "delta": round(point["vm3"]["delta"] - point["vintage_matched_common"]["delta"], 5),
            "sd": round(float(ad.std(ddof=1)), 5),
            "ci95": [round(float(np.percentile(ad, 2.5)), 5),
                     round(float(np.percentile(ad, 97.5)), 5)],
            "note": "the frames share their draws; the sd is the paired difference's",
        },
        "not_a_claim": ("a development floor on a spent frame; vm2 stays the headline "
                        "and no served number reads this file"),
    }
    if write:
        VM3_FLOOR_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("wrote", VM3_FLOOR_PATH)
    print(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    _args = sys.argv[1:]
    if _args and _args[0] == "vm3":
        run_vm3(int(_args[1]) if len(_args) > 1 else 2000)
    else:
        run(int(_args[0]) if _args else 2000)
