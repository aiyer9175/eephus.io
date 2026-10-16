# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""SDR_CATCHER_GATE, read once (docs/sdr-2026-08-18/SDR_CATCHER_GATE.md).

Every choice below was fixed in the registration (committed alone, af4ffee9)
before this file existed:

  E1  self-persistence on two-season-apart pairs (Y, Y+2), Y 2017 to 2024:
      SDR_C against B-Ref rfield (I-R) and Savant's catcher runs (I-S, FRP at C);
      LB95 of d over the better incumbent, of rho_SDR (zero comparator Z) and of
      d_PT (playing-time comparator PT: innings at C in Y) must clear 0.
  E2  next-season realized catcher runs, EBR_GATE.md 11.2.2's leave-one-system-out
      form: SDR_C without DRS against I-S on DRS(Y+1); SDR_C without Statcast
      against I-R on FRP(Y+1); the gap is the mean of the two; g_Z and g_PT clear 0.
  Player-clustered bootstrap B 2,000 seed 20261017; Holm k 2 alpha 0.05; twin
  (sdr_runs and both variants permuted within season, seed 20261018) must fail.
  PASS when both pass, PARTIAL one, FAIL none.

Part 6's checks run before the read: --dry-run (a fixture with nulls) and
--simulate (planted, null and playing-time-only worlds on the real design, seed
20261019; every metric value replaced).

Usage:
    python tools/sdr_catcher_gate.py --dry-run
    python tools/sdr_catcher_gate.py --simulate
    python tools/sdr_catcher_gate.py            # the read, once; writes the artifact
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import sdr_eval_gate as G  # noqa: E402

OUT = ROOT / "data" / "_labs" / "sdr_catcher" / "sdr_catcher_eval.json"
REGISTRATION = "docs/sdr-2026-08-18/SDR_CATCHER_GATE.md"

E1_SEASONS = tuple(range(2017, 2025))          # Y; outcome Y + 2
E2_SEASONS = tuple(range(2017, 2026))          # Y; outcome Y + 1
INN_FLOOR = 300.0
B = 2000
SEED = 20261017
TWIN_SEED = 20261018
SIM_SEED = 20261019
ALPHA = 0.05

RUN_COLS = ["sdr", "sdr_nodrs", "sdr_nosc"]


@dataclass
class Inputs:
    drop: pd.DataFrame          # catcher rows: player_id, season, innings, sdr_runs, framing_runs, player_name
    fg: pd.DataFrame            # FanGraphs catcher rows: player_id, season, Inn, DRS, FRP, fFRP, bFRP, tFRP
    rfield: pd.DataFrame        # player_id, season, runs_field, inn
    variants: dict              # no_drs / no_statcast -> player_id, season, sdr_runs (catcher rows)
    meta: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# frame
# ---------------------------------------------------------------------------

def build_rows(inp: Inputs) -> pd.DataFrame:
    """One row per drop catcher row with every metric's runs and rate."""
    d = inp.drop[["player_id", "season", "innings", "sdr_runs", "framing_runs",
                  "player_name"]].copy()
    d = d.rename(columns={"innings": "inn", "sdr_runs": "sdr", "framing_runs": "cfram"})
    for name, col in (("no_drs", "sdr_nodrs"), ("no_statcast", "sdr_nosc")):
        v = inp.variants.get(name)
        if v is None or not len(v):
            d[col] = np.nan
            continue
        v = v[["player_id", "season", "sdr_runs"]].rename(columns={"sdr_runs": col})
        d = d.merge(v, on=["player_id", "season"], how="left", validate="one_to_one")
    f = inp.fg[["player_id", "season", "DRS", "FRP", "fFRP", "bFRP", "tFRP"]].rename(
        columns={"DRS": "drs", "FRP": "frp", "fFRP": "ffrp", "bFRP": "bfrp", "tFRP": "tfrp"})
    d = d.merge(f, on=["player_id", "season"], how="left", validate="one_to_one")
    for c in ("sdr", "sdr_nodrs", "sdr_nosc", "cfram", "drs", "frp", "ffrp", "bfrp", "tfrp"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
        d[c + "_rate"] = d[c] / d.inn
    # Savant blocking starts in 2018: bFRP before it is a placeholder zero, not a reading
    d.loc[d.season < 2018, "bfrp_rate"] = np.nan
    d["is_rate"] = d.frp_rate
    rf = inp.rfield.copy()
    rf["rfield_rate"] = np.where(rf.inn > 0, rf.runs_field / rf.inn.replace(0, np.nan), np.nan)
    d = d.merge(rf[["player_id", "season", "rfield_rate"]], on=["player_id", "season"],
                how="left")
    return d.reset_index(drop=True)


def target_rows(inp: Inputs) -> pd.DataFrame:
    """FanGraphs catcher rows at 300+ innings: the E2 targets."""
    t = inp.fg[pd.to_numeric(inp.fg.Inn, errors="coerce") >= INN_FLOOR].copy()
    t["inn"] = pd.to_numeric(t.Inn, errors="coerce")
    t["t_drs_rate"] = pd.to_numeric(t.DRS, errors="coerce") / t.inn
    t["t_frp_rate"] = pd.to_numeric(t.FRP, errors="coerce") / t.inn
    t["t_drs"] = pd.to_numeric(t.DRS, errors="coerce")
    t["t_frp"] = pd.to_numeric(t.FRP, errors="coerce")
    return t[["player_id", "season", "inn", "t_drs_rate", "t_frp_rate", "t_drs", "t_frp"]]


def _pairs(a: pd.DataFrame, b: pd.DataFrame, gap: int, seasons) -> pd.DataFrame:
    a = a[a.season.isin(seasons)]
    b = b.copy()
    b["season"] = b.season - gap
    return a.merge(b, on=["player_id", "season"], suffixes=("", "_n"))


E1_NEED = ["sdr_rate", "rfield_rate", "is_rate"]


def e1_frame(rows: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    p = _pairs(rows, rows, 2, E1_SEASONS)
    need = [c for m in E1_NEED for c in (m, m + "_n")] + ["inn"]
    q = p.dropna(subset=need).reset_index(drop=True)
    return q, int(len(p) - len(q))


E2_NEED = ["sdr_nodrs_rate", "sdr_nosc_rate", "is_rate", "rfield_rate", "inn",
           "t_drs_rate", "t_frp_rate"]


def e2_frame(rows: pd.DataFrame, targets: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    t = targets.rename(columns={"inn": "inn_t"})
    p = _pairs(rows, t, 1, E2_SEASONS)
    q = p.dropna(subset=E2_NEED).reset_index(drop=True)
    return q, int(len(p) - len(q))


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------

sp = G.spearman


def e1_stats(p: pd.DataFrame) -> dict | None:
    r = {"sdr": sp(p.sdr_rate, p.sdr_rate_n), "rfield": sp(p.rfield_rate, p.rfield_rate_n),
         "savant": sp(p.is_rate, p.is_rate_n), "pt": sp(p.inn, p.sdr_rate_n)}
    if any(v is None for v in r.values()):
        return None
    return r


def e2_stats(p: pd.DataFrame) -> dict | None:
    r = {"drs_leg_sdr": sp(p.sdr_nodrs_rate, p.t_drs_rate),
         "drs_leg_inc": sp(p.is_rate, p.t_drs_rate),
         "drs_leg_pt": sp(p.inn, p.t_drs_rate),
         "sc_leg_sdr": sp(p.sdr_nosc_rate, p.t_frp_rate),
         "sc_leg_inc": sp(p.rfield_rate, p.t_frp_rate),
         "sc_leg_pt": sp(p.inn, p.t_frp_rate)}
    if any(v is None for v in r.values()):
        return None
    r["gap"] = 0.5 * ((r["drs_leg_sdr"] - r["drs_leg_inc"]) + (r["sc_leg_sdr"] - r["sc_leg_inc"]))
    r["g_z"] = 0.5 * (r["drs_leg_sdr"] + r["sc_leg_sdr"])
    r["g_pt"] = 0.5 * ((r["drs_leg_sdr"] - r["drs_leg_pt"]) + (r["sc_leg_sdr"] - r["sc_leg_pt"]))
    return r


def _boot(p: pd.DataFrame, fn, keys, b: int, seed: int) -> dict:
    """Player-clustered bootstrap; returns key -> finite draws."""
    _, members = G._cluster_index(p.player_id.to_numpy())
    rng = np.random.default_rng(seed)
    out = {k: np.full(b, np.nan) for k in keys}
    n = len(members)
    for i in range(b):
        pick = rng.integers(0, n, n)
        idx = np.concatenate([members[k] for k in pick]) if n else np.array([], int)
        s = fn(p.iloc[idx])
        if s is None:
            continue
        for k in keys:
            out[k][i] = s[k]
    return {k: v[np.isfinite(v)] for k, v in out.items()}


def _ci(v: np.ndarray) -> dict:
    if not len(v):
        return {"lb95": None, "ub95": None, "sd": None}
    return {"lb95": G._r(float(np.percentile(v, 2.5))), "ub95": G._r(float(np.percentile(v, 97.5))),
            "sd": G._r(float(np.std(v, ddof=1)))}


def e1_read(rows: pd.DataFrame, b: int = B, seed: int = SEED) -> dict:
    p, dropped = e1_frame(rows)
    r = e1_stats(p) if len(p) >= 3 else None
    if r is None:
        return {"n_pairs": int(len(p)), "left_out_missing": dropped, "status": "not computable"}
    better = "rfield" if r["rfield"] >= r["savant"] else "savant"

    def fn(q):
        s = e1_stats(q)
        if s is None:
            return None
        return {"d": s["sdr"] - s[better], "rho_sdr": s["sdr"], "d_pt": s["sdr"] - s["pt"]}

    dr = _boot(p, fn, ["d", "rho_sdr", "d_pt"], b, seed)
    cd, cz, cp = _ci(dr["d"]), _ci(dr["rho_sdr"]), _ci(dr["d_pt"])
    pval = float(np.mean(dr["d"] <= 0)) if len(dr["d"]) else None
    return {
        "n_pairs": int(len(p)), "n_catchers": int(p.player_id.nunique()),
        "left_out_missing": dropped,
        "predictor_seasons": sorted(int(s) for s in p.season.unique()),
        "bootstrap_sd_d": cd["sd"], "mde95_d": G._r(1.96 * cd["sd"]) if cd["sd"] else None,
        "rho": {"sdr": G._r(r["sdr"]), "rfield": G._r(r["rfield"]), "savant": G._r(r["savant"]),
                "pt_on_sdr_next": G._r(r["pt"])},
        "better_incumbent": better, "d_point": G._r(r["sdr"] - r[better]),
        "d_ci": cd, "zero_comparator": {"rho_sdr": G._r(r["sdr"]), **cz},
        "playing_time": {"d_pt": G._r(r["sdr"] - r["pt"]), **cp},
        "p_one_sided": G._r(pval, 5),
        "beats_both_at_point": bool(r["sdr"] > r["rfield"] and r["sdr"] > r["savant"]),
        "lb_d_above_0": bool(cd["lb95"] is not None and cd["lb95"] > 0),
        "clears_zero": bool(cz["lb95"] is not None and cz["lb95"] > 0),
        "clears_pt": bool(cp["lb95"] is not None and cp["lb95"] > 0),
    }


def e2_read(rows: pd.DataFrame, targets: pd.DataFrame, b: int = B, seed: int = SEED) -> dict:
    p, dropped = e2_frame(rows, targets)
    r = e2_stats(p) if len(p) >= 3 else None
    if r is None:
        return {"n_pairs": int(len(p)), "left_out_missing": dropped, "status": "not computable"}
    dr = _boot(p, e2_stats, ["gap", "g_z", "g_pt"], b, seed)
    cg, cz, cp = _ci(dr["gap"]), _ci(dr["g_z"]), _ci(dr["g_pt"])
    pval = float(np.mean(dr["gap"] <= 0)) if len(dr["gap"]) else None
    return {
        "n_pairs": int(len(p)), "n_catchers": int(p.player_id.nunique()),
        "left_out_missing": dropped,
        "predictor_seasons": sorted(int(s) for s in p.season.unique()),
        "bootstrap_sd_gap": cg["sd"], "mde95_gap": G._r(1.96 * cg["sd"]) if cg["sd"] else None,
        "per_system": {
            "drs_left_out": {"target": "DRS per inning at C, Y+1",
                             "sdr_without_drs": G._r(r["drs_leg_sdr"]),
                             "savant_incumbent": G._r(r["drs_leg_inc"]),
                             "pt": G._r(r["drs_leg_pt"]),
                             "gap": G._r(r["drs_leg_sdr"] - r["drs_leg_inc"])},
            "statcast_left_out": {"target": "FRP per inning at C, Y+1",
                                  "sdr_without_statcast": G._r(r["sc_leg_sdr"]),
                                  "rfield_incumbent": G._r(r["sc_leg_inc"]),
                                  "pt": G._r(r["sc_leg_pt"]),
                                  "gap": G._r(r["sc_leg_sdr"] - r["sc_leg_inc"])}},
        "gap_point": G._r(r["gap"]), "gap_ci": cg,
        "zero_comparator": {"g_z": G._r(r["g_z"]), **cz},
        "playing_time": {"g_pt": G._r(r["g_pt"]), **cp},
        "p_one_sided": G._r(pval, 5),
        "gap_positive_lb": bool(r["gap"] > 0 and cg["lb95"] is not None and cg["lb95"] > 0),
        "clears_zero": bool(cz["lb95"] is not None and cz["lb95"] > 0),
        "clears_pt": bool(cp["lb95"] is not None and cp["lb95"] > 0),
    }


def _e1_ok(c: dict) -> bool:
    return bool(c.get("beats_both_at_point") and c.get("lb_d_above_0") and c.get("clears_zero")
                and c.get("clears_pt"))


def _e2_ok(c: dict) -> bool:
    return bool(c.get("gap_positive_lb") and c.get("clears_zero") and c.get("clears_pt"))


# ---------------------------------------------------------------------------
# twin
# ---------------------------------------------------------------------------

def permute_runs(rows: pd.DataFrame, seed: int) -> pd.DataFrame:
    """sdr and both variants' runs permuted jointly within season among the frame's
    catcher rows; every row keeps its own innings; rates recomputed."""
    rng = np.random.default_rng(seed)
    out = rows.copy()
    vals = out[RUN_COLS].to_numpy(copy=True)
    for _, idx in out.groupby("season").indices.items():
        vals[idx] = vals[rng.permutation(idx)]
    out[RUN_COLS] = vals
    for c in RUN_COLS:
        out[c + "_rate"] = out[c] / out.inn
    return out


# ---------------------------------------------------------------------------
# reported beside (R1 to R6)
# ---------------------------------------------------------------------------

R1_METRICS = {"sdr": "sdr_rate", "rfield": "rfield_rate", "savant": "is_rate", "drs": "drs_rate",
              "framing_statcast": "ffrp_rate", "blocking_statcast": "bfrp_rate",
              "throwing_statcast": "tfrp_rate", "framing_cframing": "cfram_rate"}


def _persist(p: pd.DataFrame, metrics: dict) -> dict:
    out = {}
    for k, c in metrics.items():
        q = p.dropna(subset=[c, c + "_n"])
        out[k] = {"n_pairs": int(len(q)), "rho": G._r(sp(q[c], q[c + "_n"]))}
    return out


def reported(rows: pd.DataFrame, targets: pd.DataFrame, e1p: pd.DataFrame,
             e2p: pd.DataFrame) -> dict:
    p1 = _pairs(rows, rows, 1, E2_SEASONS)
    r1 = _persist(p1, R1_METRICS)
    q = p1.dropna(subset=["inn", "sdr_rate_n"])
    r1["pt_on_sdr_next"] = {"n_pairs": int(len(q)), "rho": G._r(sp(q.inn, q.sdr_rate_n))}
    r2 = {}
    for tname, tcol in (("drs_next", "t_drs_rate"), ("frp_next", "t_frp_rate")):
        r2[tname] = {k: G._r(sp(e2p[c], e2p[tcol])) for k, c in
                     (("sdr_full", "sdr_rate"), ("rfield", "rfield_rate"), ("savant", "is_rate"),
                      ("pt", "inn"))}
    r2["n_pairs"] = int(len(e2p))
    tot = e2p.assign(nodrs=e2p.sdr_nodrs, nosc=e2p.sdr_nosc, sav=e2p.frp,
                     rf=e2p.rfield_rate * e2p.inn)
    r3 = {"drs_left_out": {"sdr_without_drs": G._r(sp(tot.nodrs, tot.t_drs)),
                           "savant_incumbent": G._r(sp(tot.sav, tot.t_drs))},
          "statcast_left_out": {"sdr_without_statcast": G._r(sp(tot.nosc, tot.t_frp)),
                                "rfield_incumbent": G._r(sp(tot.rf, tot.t_frp))},
          "note": "runs in Y (rate x innings at C) against target runs in Y+1"}
    s1 = e1_stats(e1p[~e1p.season.isin([2018, 2020])])
    s2 = e2_stats(e2p[~e2p.season.isin([2019, 2020])])
    r4 = {"e1": {"n_pairs": int((~e1p.season.isin([2018, 2020])).sum()),
                 **({k: G._r(v) for k, v in s1.items()} if s1 else {})},
          "e2": {"n_pairs": int((~e2p.season.isin([2019, 2020])).sum()),
                 **({k: G._r(v) for k, v in s2.items()} if s2 else {})}}
    r5 = _persist(e1p, {k: v for k, v in R1_METRICS.items()
                        if k not in ("sdr", "rfield", "savant")})
    last = int(rows.season.max()) if len(rows) else None
    b26 = rows[rows.season == last].sort_values("sdr", ascending=False)
    def rec(r):
        return {"player": r.player_name, "player_id": int(r.player_id),
                "innings": round(float(r.inn), 1), "sdr_runs": round(float(r.sdr), 1)}

    r6 = {"season": last, "n": int(len(b26)), "top": [rec(r) for r in b26.head(10).itertuples()],
          "bottom": [rec(r) for r in b26.tail(10).iloc[::-1].itertuples()]}
    return {"R1_consecutive_pairs": r1, "R2_full_sdr_on_targets": r2, "R3_total_cell": r3,
            "R4_without_2020": r4, "R5_components_on_e1_pairs": r5, "R6_board": r6}


# ---------------------------------------------------------------------------
# the read
# ---------------------------------------------------------------------------

def evaluate(inp: Inputs, b: int = B, with_reported: bool = True) -> dict:
    rows = build_rows(inp)
    targets = target_rows(inp)
    twin = permute_runs(rows, TWIN_SEED)
    e1 = e1_read(rows, b=b)
    e2 = e2_read(rows, targets, b=b)
    e1t = e1_read(twin, b=b)
    e2t = e2_read(twin, targets, b=b)
    h = G.holm({"E1": e1.get("p_one_sided"), "E2": e2.get("p_one_sided")}, ALPHA)
    ht = G.holm({"E1": e1t.get("p_one_sided"), "E2": e2t.get("p_one_sided")}, ALPHA)
    clauses = {}
    for k, c, ct, ok in (("E1", e1, e1t, _e1_ok), ("E2", e2, e2t, _e2_ok)):
        twin_pass = bool(ok(ct) and ht[k]["rejects"])
        tw = {kk: ct.get(kk) for kk in ("rho", "d_point", "d_ci", "per_system", "gap_point",
                                        "gap_ci", "zero_comparator", "playing_time")
              if kk in ct}
        clauses[k] = {**c, "holm": h[k], "twin": {**tw, "passes_rule": twin_pass},
                      "passes": bool(ok(c) and h[k]["rejects"] and not twin_pass)}
    n_pass = sum(1 for v in clauses.values() if v["passes"])
    out = {"clauses": clauses, "verdict": {2: "PASS", 1: "PARTIAL", 0: "FAIL"}[n_pass]}
    if with_reported:
        e1p, _ = e1_frame(rows)
        e2p, _ = e2_frame(rows, targets)
        out["reported"] = reported(rows, targets, e1p, e2p)
        out["frame_rows_by_season"] = {int(s): int(n) for s, n in
                                       rows.season.value_counts().sort_index().items()}
    return out


# ---------------------------------------------------------------------------
# part 6: simulation on the real design
# ---------------------------------------------------------------------------

def simulate_inputs(design: Inputs, world: str, seed: int = SIM_SEED) -> Inputs:
    """The real frame's rows (players, seasons, innings) with every metric value
    replaced. world: planted, null, playing_time."""
    rng = np.random.default_rng(seed)
    d = design.drop[["player_id", "season", "innings", "player_name"]].copy().reset_index(drop=True)
    fgd = design.fg[["player_id", "season", "Inn"]].copy().reset_index(drop=True)
    players = np.union1d(d.player_id.unique(), fgd.player_id.unique())
    talent = dict(zip(players, rng.normal(size=len(players)) if world == "planted"
                      else np.zeros(len(players))))

    def rate(frame, inn_col, sd):
        t = frame.player_id.map(talent).to_numpy()
        inn = frame[inn_col].astype(float)
        if world == "playing_time":
            z = frame.assign(_i=inn).groupby("season")._i.transform(
                lambda x: (x - x.mean()) / x.std(ddof=1) if x.std(ddof=1) > 0 else x * 0)
            base = 0.5 * z.to_numpy()
            sd = 1.0
        else:
            base = t
        return base + rng.normal(scale=sd, size=len(frame))

    inn = d.innings.astype(float)
    planted = world == "planted"
    d["sdr_runs"] = rate(d, "innings", 0.5) * inn / 1000.0
    d["framing_runs"] = rate(d, "innings", 1.0) * inn / 1000.0
    nd = d[["player_id", "season"]].assign(sdr_runs=rate(d, "innings", 0.5) * inn / 1000.0)
    ns = d[["player_id", "season"]].assign(sdr_runs=rate(d, "innings", 0.5) * inn / 1000.0)
    finn = fgd.Inn.astype(float)
    fg = fgd.copy()
    fg["DRS"] = rate(fgd, "Inn", 1.0) * finn / 1000.0
    fg["FRP"] = rate(fgd, "Inn", 1.5) * finn / 1000.0      # I-S in Y and the FRP target in Y+1
    for c in ("fFRP", "bFRP", "tFRP"):
        fg[c] = rate(fgd, "Inn", 1.5) * finn / 1000.0
    rfi = d[["player_id", "season", "innings"]].rename(columns={"innings": "inn"})
    if planted or world == "null":
        rv = rng.normal(size=len(rfi))                      # I-R carries no talent
    else:
        rv = rate(rfi.assign(innings=rfi.inn), "innings", 1.0)
    rf = rfi.assign(runs_field=rv * rfi.inn / 1000.0)
    return Inputs(drop=d, fg=fg, rfield=rf, variants={"no_drs": nd, "no_statcast": ns},
                  meta={"simulated": world, "seed": seed})


def run_simulations(design: Inputs, b: int = B) -> dict:
    out = {}
    for world in ("planted", "null", "playing_time"):
        res = evaluate(simulate_inputs(design, world), b=b, with_reported=False)
        c = res["clauses"]
        out[world] = {"verdict": res["verdict"],
                      "E1": {k: c["E1"].get(k) for k in ("rho", "d_point", "d_ci", "zero_comparator",
                                                         "playing_time", "passes")},
                      "E2": {k: c["E2"].get(k) for k in ("per_system", "gap_point", "gap_ci",
                                                         "zero_comparator", "playing_time",
                                                         "passes")}}
    pl, nu, pt = out["planted"], out["null"], out["playing_time"]
    checks = {
        "planted_reads_pass": pl["verdict"] == "PASS",
        "null_reads_fail": nu["verdict"] == "FAIL",
        "null_does_not_clear_zero": not any(
            (nu[k]["zero_comparator"] or {}).get("lb95", 0) is not None
            and (nu[k]["zero_comparator"] or {}).get("lb95", 0) > 0 for k in ("E1", "E2")),
        "playing_time_not_pass": pt["verdict"] != "PASS",
        "pt_stops_both_clauses": all(
            not ((pt[k]["playing_time"] or {}).get("lb95") or 0) > 0 for k in ("E1", "E2")),
    }
    out["checks"] = checks
    out["all_behave"] = all(checks.values())
    return out


# ---------------------------------------------------------------------------
# real inputs
# ---------------------------------------------------------------------------

def load_real() -> Inputs:
    import sdr_inhouse as S                          # noqa: PLC0415
    import sdr_intake                                # noqa: PLC0415
    drop_path = sdr_intake.newest_accepted("sdr_defense_card")
    if drop_path is None:
        raise SystemExit("no accepted sdr_defense_card drop; run sdr_intake --accept first")
    drop_all = pd.read_csv(drop_path)
    drop = drop_all[drop_all.primary_position == "C"].copy()
    fgs = []
    for s in sorted(drop_all.season.unique()):
        f = pd.read_csv(S.RAW / f"fg_field_full_{s}.csv").rename(columns={"xMLBAMID": "player_id"})
        f["player_id"] = pd.to_numeric(f.player_id, errors="coerce")
        f = f[f.player_id.notna() & (f.Pos == "C")].copy()
        f["player_id"] = f.player_id.astype(int)
        f["season"] = int(s)
        f["Inn"] = pd.to_numeric(f.Inn, errors="coerce")
        fgs.append(f[["player_id", "season", "Inn", "DRS", "FRP", "fFRP", "bFRP", "tFRP"]])
    fg = pd.concat(fgs, ignore_index=True)
    wd = pd.read_parquet(G.WAR_DAILY)
    wd["player_id"] = pd.to_numeric(wd.mlb_ID, errors="coerce")
    wd["season"] = pd.to_numeric(wd.year_ID, errors="coerce")
    for c in ("runs_field", "Inn"):
        wd[c] = pd.to_numeric(wd[c], errors="coerce")
    wd = wd.dropna(subset=["player_id", "season"])
    rf = wd.groupby(["player_id", "season"], as_index=False).agg(
        runs_field=("runs_field", lambda x: x.sum(min_count=1)), inn=("Inn", "sum"))
    rf = rf.astype({"player_id": int, "season": int})
    variants = {}
    for v in ("no_drs", "no_statcast"):
        parts = []
        for s in sorted(drop_all.season.unique()):
            p = S.REPORTS / f"06_defense_plus_{s}__{v}.csv"
            if p.exists():
                x = pd.read_csv(p).rename(columns={"id": "player_id", "dplus_runs": "sdr_runs"})
                x = x[x.Pos == "C"].copy()
                x["season"] = int(s)
                parts.append(x[["player_id", "season", "sdr_runs"]])
        if parts:
            variants[v] = pd.concat(parts, ignore_index=True)
    meta = {
        "drop": {"path": str(drop_path.relative_to(ROOT)).replace("\\", "/"),
                 "sha256": G._sha_file(drop_path), "rows": int(len(drop_all)),
                 "catcher_rows": int(len(drop))},
        "war_daily_bat": {"path": ".cache/war_daily/bat.parquet",
                          "sha256": G._sha_file(G.WAR_DAILY),
                          "modified": datetime.fromtimestamp(G.WAR_DAILY.stat().st_mtime,
                                                             timezone.utc).isoformat()},
        "fg_fielding": {s: G._sha_file(S.RAW / f"fg_field_full_{s}.csv")[:16]
                        for s in sorted(int(x) for x in drop_all.season.unique())},
        "fetch_manifest": ".cache/sdr/fetch_manifest.json",
        "run_manifest": ".cache/sdr/run_manifest.json",
    }
    return Inputs(drop=drop, fg=fg, rfield=rf, variants=variants, meta=meta)


def run(write: bool = True, b: int = B) -> dict:
    inp = load_real()
    print("inputs:", json.dumps(inp.meta, indent=1), flush=True)
    res = evaluate(inp, b=b)
    doc = {
        "generated_at": date.today().isoformat(),
        "status": "measured",
        "read_kind": "OWNER-WAIVED EARLY READ (owner decision EW3-5); owner decision EW3-33",
        "registration": REGISTRATION,
        "question": ("does Will's SDR at catcher measure catchers better than B-Ref rfield and "
                     "Savant's catcher runs, on two-season-apart self-persistence and on "
                     "next-season realized catcher runs (EW3-23 form)"),
        "inputs": inp.meta,
        "frame": {"positions": ["C"], "innings_floor": INN_FLOOR,
                  "e1_predictor_seasons": list(E1_SEASONS), "e2_predictor_seasons": list(E2_SEASONS),
                  "bootstrap_b": b, "seed": SEED, "twin_seed": TWIN_SEED, "alpha_holm": ALPHA},
        **res,
    }
    if write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="the reporting path on a fixture with nulls; writes nothing")
    ap.add_argument("--simulate", action="store_true",
                    help="part 6: planted, null and playing-time worlds on the real design")
    ap.add_argument("--b", type=int, default=B)
    a = ap.parse_args(argv)
    if a.dry_run:
        from test_sdr_catcher_gate import fixture_inputs  # noqa: PLC0415
        res = evaluate(fixture_inputs(), b=50)
        print(json.dumps({"verdict": res["verdict"],
                          "E1": res["clauses"]["E1"].get("rho"),
                          "E2": res["clauses"]["E2"].get("per_system"),
                          "reported_keys": sorted(res["reported"])}, indent=1))
        return 0
    if a.simulate:
        sims = run_simulations(load_real(), b=a.b)
        print(json.dumps(sims, indent=1))
        return 0 if sims["all_behave"] else 2
    doc = run(b=a.b)
    print(json.dumps({"verdict": doc["verdict"],
                      "E1": {k: doc["clauses"]["E1"].get(k) for k in
                             ("n_pairs", "bootstrap_sd_d", "mde95_d", "rho", "d_point", "d_ci",
                              "zero_comparator", "playing_time", "holm", "passes")},
                      "E2": {k: doc["clauses"]["E2"].get(k) for k in
                             ("n_pairs", "bootstrap_sd_gap", "mde95_gap", "per_system", "gap_point",
                              "gap_ci", "zero_comparator", "playing_time", "holm", "passes")}},
                     indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
