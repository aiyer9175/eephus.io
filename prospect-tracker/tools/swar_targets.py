# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The amended targets of the eWAR v3 skill look: part 11.2's primary targets,
bases and team guard, with the parts 11.3 to 11.6 added after it.

Registered in docs/ebr-2026-09-30/EBR_GATE.md part 11 (11.2.1 to 11.2.6, 11.3.4,
11.4.4, 11.5.2, 11.6.2 and 11.7). tools/swar_lab.py is the only caller: it scores
the cells, this module builds what they read.

TWO HALVES.
  * Pure arithmetic (no file, no network): the pitching target RA9* turned into
    runs prevented above average, PE-P's RSB, the catcher component S3c, PE-H's
    shrunk terms, the fielding-system rule of 11.2.2 and the team guard of 11.2.4
    (roster weighting, the player-clustered and club-clustered bootstraps,
    NON-INFERIOR).
  * Readers of caches only (class Readers), never a fetch: the Baseball-Reference
    stint frames (runs_field, team exposure), the FanGraphs fielding leaderboard
    files and the triangulation's frozen fit (through
    tools/fielding_triangulation_lab.load_real), the StatsAPI season and split
    lines and the play-by-play corpus (through tools/pitch_economy_lab), and the
    ladder gate's records. Each reader reports the sha256 of what it read.

Nothing here relates a season to the next: the readers return same-season
quantities only, and the team guard is a function the lab calls on its look day.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Iterable, Mapping, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import swar  # noqa: E402  (pure: recentre)

# --------------------------------------------------------------------------
# registered parameters (part 11.2.4, 11.6.2, 11.5.2)
# --------------------------------------------------------------------------

#: The team guard (11.2.4): two bootstraps, B = 2,000 each, seed 20261024.
GUARD_SEED = 20261024
GUARD_BOOT = 2000
#: NON-INFERIOR when dT - 1.645 sd is above -0.02 under both bootstraps.
GUARD_Z = 1.645
GUARD_MARGIN = -0.02
#: The catcher frame of S3c (11.6.2): 300 or more innings at C in season Y.
CATCHER_MIN_INN = 300.0
#: UZR is published through 2024 (11.5.2: "UZR alone, through 2024").
UZR_LAST = 2024
#: True relievers for lgRA9*_RP (11.4.4): GS / G at or below 0.10.
RELIEVER_MAX_START_SHARE = 0.10
#: The ladder gate the position part reads (11.2.3).
LADDER_EVAL = ROOT / "data" / "positional_ladder_v2_eval.json"
LADDER_VERIFY = ROOT / "data" / "positional_ladder_v2_verify.json"

#: Franchise of a Baseball-Reference club id, for the club-clustered bootstrap
#: (a franchise that moved or renamed keeps one cluster).
FRANCHISE_ALIAS = {"OAK": "ATH", "FLA": "MIA", "ANA": "LAA", "CAL": "LAA", "TBD": "TBR",
                   "MON": "WSN"}

# --------------------------------------------------------------------------
# the fielding systems (11.2.2)
# --------------------------------------------------------------------------

#: The system each fielding source's runs come from, 2016 on, with the source's
#: own documentation. The DRS system is DRS with UZR (UZR runs on Sports Info
#: Solutions' batted-ball data, the provider DRS uses); the Statcast system is
#: OAA with FRP (docs/ewar/FIELDING_TRIANGULATION_GATE.md part 2).
FIELDING_SOURCES = {
    "fg_fld": ("Statcast", "FanGraphs' fielding runs (Fld) in WAR, FanGraphs Fielding Run "
                           "Prevention on Statcast (FanGraphs Library, 'FRP'); "
                           "FIELDING_TRIANGULATION_GATE.md part 2: FanGraphs Fld at the position level is FRP"),
    "fg_frm": ("FanGraphs framing", "FanGraphs' catcher framing runs (CFraming), counted on a fielder "
                                    "who caught (dem_plus.fld_total)"),
    "bref_runs_field": ("DRS", "Baseball-Reference runs_field (Rfield): Sports Info Solutions' Defensive "
                               "Runs Saved (Baseball-Reference, 'Position Player WAR Calculations and Details')"),
    "fg_drs": ("DRS", "Sports Info Solutions' Defensive Runs Saved as FanGraphs' fielding leaderboard "
                      "republishes it"),
    "fg_uzr": ("DRS", "FanGraphs' UZR on Sports Info Solutions batted-ball data (the DRS system), "
                      "published through 2024"),
    "fg_frp": ("Statcast", "FanGraphs Fielding Run Prevention, Statcast-based"),
    "savant_frv": ("Statcast", "Baseball Savant fielding run value"),
}
#: 11.2.2: a part's target is Baseball-Reference runs_field unless the part reads
#: that system in the season; then the next source in this order it does not read.
TARGET_ORDER = ("bref_runs_field", "savant_frv")
#: The sources each fielding arm reads.
PART_SOURCES = {
    "fld": ("fg_fld", "fg_frm"),                  # S3, DEM+
}
#: S3c's target is registered by name (11.6.2): DRS (the DRS system) in Y+1 from
#: the FanGraphs fielding files, summed over the player's positions.


def system_of(source: str) -> str:
    return FIELDING_SOURCES[source][0]


def fielding_target(part: str, season: int) -> str:
    """11.2.2's rule: the first source of TARGET_ORDER whose system the part does
    not read in `season`. The systems do not change by season from 2016 on (the
    table above), so `season` only names the row the record prints."""
    read = {system_of(s) for s in PART_SOURCES[part]}
    for src in TARGET_ORDER:
        if system_of(src) not in read:
            return src
    raise ValueError(f"no independent fielding target for {part} in {season}")


def system_table(seasons: Iterable[int]) -> dict:
    """The per-season table the record prints before any statistic."""
    return {str(int(y)): {s: {"system": FIELDING_SOURCES[s][0], "documentation": FIELDING_SOURCES[s][1]}
                          for s in FIELDING_SOURCES
                          if not (s == "fg_uzr" and int(y) > UZR_LAST)}
            for y in seasons}


# --------------------------------------------------------------------------
# pure target constructions
# --------------------------------------------------------------------------

def _f(v) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def league_ra9_star(rows: Iterable[Mapping], relievers_only: bool = False) -> Optional[float]:
    """lgRA9*_s: the innings-weighted mean RA9* over the season's pitchers with
    one (equivalently 9 x the pooled RA* per inning); `relievers_only` keeps true
    relievers (GS / G at or below 0.10), lgRA9*_RP of 11.4.4."""
    num = den = 0.0
    for r in rows:
        ra9, ip = _f(r.get("ra9_star")), _f(r.get("ip"))
        if ra9 is None or ip is None or ip <= 0:
            continue
        if relievers_only:
            g, gs = _f(r.get("g")) or 0.0, _f(r.get("gs")) or 0.0
            if g <= 0 or gs / g > RELIEVER_MAX_START_SHARE:
                continue
        num += ra9 * ip
        den += ip
    return num / den if den > 0 else None


def runs_prevented(lg_ra9s: Optional[float], ra9s: Optional[float], ip: Optional[float]) -> Optional[float]:
    """(lgRA9*_s - RA9*_j) x IP_j / 9: runs prevented above average, the sign of
    11.2.1's pitching target reversed so that fewer runs rank higher."""
    if lg_ra9s is None or ra9s is None or ip is None:
        return None
    return (float(lg_ra9s) - float(ra9s)) * float(ip) / 9.0


def rsb(outs: Optional[float], lg_ra9s_rp: Optional[float], ra9s: Optional[float]) -> Optional[float]:
    """RSB_j = (O_j / 27) (lgRA9*_RP - RA9*_j): runs saved over a league-average
    reliever across the outs he recorded (11.4.4)."""
    if outs is None or lg_ra9s_rp is None or ra9s is None:
        return None
    return float(outs) / 27.0 * (float(lg_ra9s_rp) - float(ra9s))


def catcher_g(sc: Optional[float], b0: float, nonc_frp: float, c_inn: float) -> float:
    """g_cat,i = SC_i - BC_i, BC_i = Fld_i + Frm_i - O_i, when i has a catcher row
    with innings at C above 0, else 0 (11.6.1). A catcher row with no FRP gives 0."""
    if not c_inn or c_inn <= 0 or sc is None:
        return 0.0
    return float(sc) - (float(b0) - float(nonc_frp or 0.0))


def catcher_deltas(rows: Mapping[int, Mapping], pa: Mapping[int, float],
                   pitcher_batters: Iterable[int]) -> dict[int, float]:
    """d_cat per hitter of one season: g_cat re-centred per PA (swar.recentre),
    pitcher-batters at 0 outside the re-centring. `rows`: {mlbam: {sc, b0,
    nonc_frp, c_inn}}; a hitter absent from `rows` carries g_cat 0."""
    pb = set(int(x) for x in pitcher_batters)
    g = {}
    for mid in pa:
        r = rows.get(mid) or {}
        g[mid] = 0.0 if mid in pb else catcher_g(r.get("sc"), r.get("b0") or 0.0,
                                                  r.get("nonc_frp") or 0.0, r.get("c_inn") or 0.0)
    return swar.recentre(g, pa, pb)


def fldt_deltas(t_runs: Mapping[int, float], b0: Mapping[int, float], pa: Mapping[int, float],
                pitcher_batters: Iterable[int]) -> dict[int, float]:
    """d_fldt per hitter of one season (FIELDING_TRIANGULATION_GATE.md part 4):
    g = T_i - the base's fielding, re-centred per PA; a hitter with no fielding
    row carries T 0; pitcher-batters 0 outside the re-centring."""
    pb = set(int(x) for x in pitcher_batters)
    g = {mid: (0.0 if mid in pb else float(t_runs.get(mid, 0.0)) - float(b0.get(mid) or 0.0))
         for mid in pa}
    return swar.recentre(g, pa, pb)


def pe_h_terms(res: Mapping, w: float, k_cl: Optional[float], k_p: Optional[float]) -> tuple[float, float]:
    """PE-H's two shrunk terms (11.4.3): CLres x n / (n + K_CL) and
    w x Pres x m / (m + K_P); their sum is pitch_economy.pe_h_raw."""
    import pitch_economy as pe
    n, m = float(res.get("n") or 0.0), float(res.get("m") or 0.0)
    return (float(res.get("clres") or 0.0) * pe.reliability(n, k_cl),
            float(w) * float(res.get("pres") or 0.0) * pe.reliability(m, k_p))


def pe_h_deltas(resid: Mapping[int, Mapping], pa_all: Mapping[int, float], w: float,
                k_cl: Optional[float], k_p: Optional[float]) -> dict[str, dict[int, float]]:
    """{"peh", "cl", "p"}: d_PEH and each term alone, re-centred per PA over every
    hitting row (pitch_economy.recentre), as the lab of part 11.4.6 does."""
    g, gc, gp = {}, {}, {}
    for mid in pa_all:
        a, b = pe_h_terms(resid.get(mid) or {}, w, k_cl, k_p)
        gc[mid], gp[mid], g[mid] = a, b, a + b
    import pitch_economy as pe
    return {"peh": pe.recentre(g, pa_all), "cl": pe.recentre(gc, pa_all), "p": pe.recentre(gp, pa_all)}


# --------------------------------------------------------------------------
# the team guard (11.2.4), pure
# --------------------------------------------------------------------------

#: The outcomes a part carries: (outcome, the roster side it reads).
OUTCOMES_HIT = (("runs_scored", "hit"), ("run_differential", "total"), ("wins", "total"))
OUTCOMES_PIT = (("runs_allowed", "pit"), ("run_differential", "total"), ("wins", "total"))
OUTCOMES_FIELD = (("run_differential", "total"), ("wins", "total"))


def franchise(team: str) -> str:
    return FRANCHISE_ALIAS.get(str(team), str(team))


def _pearson(x: np.ndarray, y: np.ndarray) -> Optional[float]:
    if len(x) < 4:
        return None
    sx, sy = float(np.std(x)), float(np.std(y))
    if sx == 0.0 or sy == 0.0:
        return None
    return float(np.mean((x - x.mean()) * (y - y.mean())) / (sx * sy))


def roster_matrix(values: Mapping[tuple, Optional[float]], exposure_y: Mapping[tuple, Optional[float]],
                  exposure_next: Mapping[tuple, Mapping[str, float]], players: list, clubs: list
                  ) -> np.ndarray:
    """(players x club-seasons): entry (i, c) = sum over predictor seasons Y of
    (v_i(Y) / n_i(Y)) x n_ic(Y+1). `values` and `exposure_y` are keyed (Y, mlbam);
    `exposure_next` (Y+1, mlbam) -> {team: exposure}; `clubs` lists (Y+1, team).
    A player with no exposure in Y, or no value, enters at 0."""
    pidx = {p: i for i, p in enumerate(players)}
    cidx = {c: j for j, c in enumerate(clubs)}
    M = np.zeros((len(players), len(clubs)))
    for (y, mid), v in values.items():
        n = exposure_y.get((y, mid))
        if v is None or n is None or n <= 0 or mid not in pidx:
            continue
        for team, e in (exposure_next.get((y + 1, mid)) or {}).items():
            j = cidx.get((y + 1, team))
            if j is not None and e:
                M[pidx[mid], j] += float(v) / float(n) * float(e)
    return M


def team_guard(mats: Mapping[str, Mapping[str, np.ndarray]], outcomes: Mapping[str, np.ndarray],
               carried: Iterable[tuple], clubs: list, boot: int = GUARD_BOOT,
               seed: int = GUARD_SEED) -> dict:
    """One part's guard. `mats[side][series]` for side in {hit, pit} and series in
    {frame, part, ref} are roster_matrix arrays on one player list and club list;
    `outcomes[name]` the club-season outcome (runs_allowed already sign-reversed);
    `carried` the (outcome, side) pairs the part carries.

    dT = r(part sum, outcome) - r(frame sum, outcome); two bootstraps (players
    drawn with replacement with all their rows, every club sum recomputed;
    franchises drawn with replacement with all their club-seasons), the same
    seed for each; NON-INFERIOR when dT - 1.645 sd > -0.02 under both, for every
    carried outcome. bWAR's r and the part's r minus bWAR's are reported beside."""
    n_players = next(iter(mats["hit"].values())).shape[0]

    def sums(weights: Optional[np.ndarray]) -> dict:
        out = {}
        for series in ("frame", "part", "ref"):
            h = mats["hit"][series]
            p = mats["pit"][series]
            sh = h.sum(axis=0) if weights is None else weights @ h
            sp = p.sum(axis=0) if weights is None else weights @ p
            out[series] = {"hit": sh, "pit": sp, "total": sh + sp}
        return out

    full = sums(None)
    rng_p = np.random.default_rng(seed)
    p_draws = []
    for _ in range(boot):
        w = np.bincount(rng_p.integers(0, n_players, n_players), minlength=n_players).astype(float)
        p_draws.append(sums(w))
    fr = [franchise(t) for (_y, t) in clubs]
    by_fr: dict = {}
    for j, f in enumerate(fr):
        by_fr.setdefault(f, []).append(j)
    fr_keys = sorted(by_fr)
    rng_c = np.random.default_rng(seed)
    c_draws = []
    for _ in range(boot):
        pick = rng_c.integers(0, len(fr_keys), len(fr_keys))
        c_draws.append(np.concatenate([np.asarray(by_fr[fr_keys[k]], dtype=np.int64) for k in pick]))

    out = {"n_club_seasons": len(clubs), "n_franchises": len(fr_keys), "outcomes": {}}
    all_ok = True
    for name, side in carried:
        y = np.asarray(outcomes[name], float)
        ok = np.isfinite(y)
        r = {s: _pearson(full[s][side][ok], y[ok]) for s in ("frame", "part", "ref")}
        dt = None if r["part"] is None or r["frame"] is None else r["part"] - r["frame"]
        dps = []
        for d in p_draws:
            a, b = _pearson(d["part"][side][ok], y[ok]), _pearson(d["frame"][side][ok], y[ok])
            if a is not None and b is not None:
                dps.append(a - b)
        dcs = []
        for idx in c_draws:
            idx = idx[ok[idx]]
            a = _pearson(full["part"][side][idx], y[idx])
            b = _pearson(full["frame"][side][idx], y[idx])
            if a is not None and b is not None:
                dcs.append(a - b)
        legs = {}
        verdicts = []
        for leg, ds in (("player", dps), ("club", dcs)):
            ds = np.asarray(ds, float)
            if len(ds) < 10 or dt is None:
                legs[leg] = {"n_draws": int(len(ds)), "sd": None, "half_width95": None, "lower": None,
                             "non_inferior": False}
                verdicts.append(False)
                continue
            sd = float(np.std(ds, ddof=1))
            s = np.sort(ds)
            n = len(s)
            hw = (float(s[max(0, int(0.975 * n) - 1)]) - float(s[min(n - 1, int(0.025 * n))])) / 2.0
            lower = dt - GUARD_Z * sd
            ni = bool(lower > GUARD_MARGIN)
            legs[leg] = {"n_draws": n, "sd": sd, "half_width95": hw, "lower": lower, "non_inferior": ni,
                         "underpowered": bool(hw > abs(GUARD_MARGIN))}
            verdicts.append(ni)
        non_inf = all(verdicts)
        all_ok = all_ok and non_inf
        out["outcomes"][name] = {
            "side": side, "n_club_seasons": int(ok.sum()), "r_frame": r["frame"], "r_part": r["part"],
            "dT": dt, "r_bwar_reference": r["ref"],
            "r_part_minus_bwar": (None if r["part"] is None or r["ref"] is None else r["part"] - r["ref"]),
            "player": legs["player"], "club": legs["club"], "non_inferior": non_inf}
    out["non_inferior"] = bool(all_ok)
    out["underpowered"] = any(o[leg].get("underpowered") for o in out["outcomes"].values()
                              for leg in ("player", "club"))
    return out


def guard_floors(g: Mapping) -> dict:
    """The sd and half-width of each outcome under both bootstraps (printed first)."""
    return {name: {leg: {"sd": o[leg].get("sd"), "half_width95": o[leg].get("half_width95")}
                   for leg in ("player", "club")} for name, o in (g.get("outcomes") or {}).items()}


# --------------------------------------------------------------------------
# the position part (11.2.3): the ladder gate's out-of-sample rule
# --------------------------------------------------------------------------

def ladder_test(eval_rec: Mapping, verify_rec: Optional[Mapping], standing: str,
                comparator: str = "fg_inv") -> dict:
    """The one test of candidate part 3 off the ladder gate's read: the dMAE in
    the standing ladder's favour over FanGraphs' published positional adjustment
    (the gate's FanGraphs inversion; the table form reported beside) with its
    bootstrap interval, and the null control (the verification's zero ladder:
    the control fails when the ladder beats it, lo95 of dMAE(zero - ladder)
    above 0). `standing` is positional_fit.POSFIT_LADDER ("v1" or "v2")."""
    key = {"v1": "v1", "v2": "b"}.get(standing)
    tests = (eval_rec or {}).get("tests") or {}
    out = {"standing_ladder": standing, "comparator": comparator, "registration": "11.2.3",
           "gate": (eval_rec or {}).get("gate"), "seed": ((eval_rec or {}).get("seeds") or {}).get("bootstrap"),
           "draws": ((eval_rec or {}).get("seeds") or {}).get("draws")}
    rec = tests.get(f"{key}_minus_{comparator}_pooled") if key else None
    if rec is None:
        out.update(available=False, reason=(f"the gate's read carries no {key}-minus-{comparator} test: "
                                            "11.2.3 asks the skill look to compute it in the run"))
        return out
    lo, hi = rec["ci95"]
    out.update(available=True, n_rows=rec.get("n_rows"), n_players=rec.get("n_players"),
               dmae_ladder_favour=-float(rec["dmae"]), lo95=-float(hi), hi95=-float(lo))
    side = tests.get(f"{key}_minus_fg_table_pooled")
    if side is not None:
        out["beside_fg_table"] = {"dmae_ladder_favour": -float(side["dmae"]),
                                  "lo95": -float(side["ci95"][1]), "hi95": -float(side["ci95"][0])}
    z = (((verify_rec or {}).get("zero_ladder") or {}).get("tests") or {}).get(f"{key}_minus_zero")
    if z is None:
        out.update(control={"available": False}, control_fails=False)
    else:
        zlo = -float(z["ci95"][1])
        out["control"] = {"available": True, "what": "the zero ladder of the gate's verification",
                          "dmae_zero_minus_ladder": -float(z["dmae"]), "lo95": zlo,
                          "hi95": -float(z["ci95"][0])}
        out["control_fails"] = bool(zlo > 0.0)
    out["passes"] = bool(out["lo95"] > 0.0 and out["control_fails"])
    return out


# --------------------------------------------------------------------------
# readers (caches only)
# --------------------------------------------------------------------------

def sha256_of(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


class Readers:
    """Every cache the amended targets read; nothing fetches. Each method
    returns same-season quantities only."""

    def __init__(self):
        self.meta: dict = {}
        self._fielding = None

    # -- the FanGraphs fielding files, Baseball-Reference runs_field and the triangulation
    def _fielding_inputs(self):
        if self._fielding is None:
            import fielding_triangulation_lab as FTL
            inp, _names = FTL.load_real()
            self._fielding = inp
            self.meta["fielding"] = inp.meta
        return self._fielding

    def fielding_by_player(self) -> dict:
        """{season: {mlbam: {drs, uzr, frp, c_inn, sc, nonc_frp, runs_field}}}: sums
        over the player's non-pitcher positions (None when no row carries the
        reading), the catcher row's innings and FRP, and Baseball-Reference
        runs_field summed over stints."""
        import pandas as pd
        inp = self._fielding_inputs()
        R = inp.rows
        out: dict = {}
        for (pid, s), grp in R.groupby(["player_id", "season"]):
            rec = {}
            for col in ("drs", "uzr", "frp"):
                v = pd.to_numeric(grp[col], errors="coerce")
                rec[col] = float(v.sum()) if v.notna().any() else None
            c = grp[grp.pos == "C"]
            rec["c_inn"] = float(c.inn.sum()) if len(c) else 0.0
            cf = pd.to_numeric(c.frp, errors="coerce") if len(c) else None
            rec["sc"] = float(cf.sum()) if (cf is not None and cf.notna().any()) else None
            nc = pd.to_numeric(grp[grp.pos != "C"].frp, errors="coerce")
            rec["nonc_frp"] = float(nc.sum()) if nc.notna().any() else 0.0
            cd = pd.to_numeric(c.drs, errors="coerce") if len(c) else None
            rec["c_drs"] = float(cd.sum()) if (cd is not None and cd.notna().any()) else None
            out.setdefault(int(s), {})[int(pid)] = rec
        for pid, s, rf in zip(inp.rfield.player_id, inp.rfield.season, inp.rfield.runs_field):
            if rf is None or (isinstance(rf, float) and not math.isfinite(rf)):
                continue
            out.setdefault(int(s), {}).setdefault(int(pid), {})["runs_field"] = float(rf)
        return out

    def triangulation_runs(self) -> dict:
        """{season: {mlbam: {config: T_i}}}: the triangulated fielding runs of each
        configuration (FULL, X_DRS, X_SC, X_UZR) on the frozen fit, non-catcher
        rows at T_rate x innings / 1,000 plus catcher rows' T_C
        (FIELDING_TRIANGULATION_GATE.md part 4)."""
        import fielding_triangulation as FT
        import fielding_triangulation_lab as FTL
        inp = self._fielding_inputs()
        fit_path = FTL.FIT_OUT
        if not fit_path.exists():
            raise FileNotFoundError(f"the triangulation's frozen fit is absent: {fit_path}")
        fitd = json.loads(fit_path.read_text(encoding="utf-8"))
        self.meta["triangulation_fit"] = {"path": str(fit_path.relative_to(ROOT)).replace("\\", "/"),
                                          "sha256": sha256_of(fit_path)}
        import warnings
        with warnings.catch_warnings():
            # apply_fit's equal-weight blend (reported only, unread here) averages empty rows
            warnings.simplefilter("ignore", RuntimeWarning)
            P = FTL.apply_fit(fitd, FTL.prepare(inp.rows))
        nonc = (P.pos != FT.CATCHER).to_numpy()
        inn = P.inn.to_numpy(float)
        tc = np.nan_to_num(P["T_C"].to_numpy(float))
        out: dict = {}
        cols = {cfg: np.nan_to_num(P[f"T_{cfg}"].to_numpy(float)) for cfg in FT.CONFIGS}
        pids, seas = P.player_id.to_numpy(), P.season.to_numpy()
        for i in range(len(P)):
            rec = out.setdefault(int(seas[i]), {}).setdefault(int(pids[i]), {c: 0.0 for c in FT.CONFIGS})
            for cfg, arr in cols.items():
                rec[cfg] += (arr[i] * inn[i] / FT.PER) if nonc[i] else tc[i]
        return out

    # -- pitch economy (11.4): PE-P per pitcher, PE-H residuals per hitter
    def pitch_economy_pitchers(self, season: int) -> dict:
        """{"delta": {variant: {mlbam: Delta_PE runs}}, "w": starter-wear runs per
        pitch, "coverage": {...}} for one season (11.4.2), on both home-run terms
        of S2's skill FIP; nopp rows and pitchers without a split line carry 0."""
        import pitch_economy as pe
        import pitch_economy_lab as pel
        lines = pel.pit_lines(season)
        sprp = pel.sprp_lines(season)
        consts = pel.season_constants(season)
        cfip = consts["cfip"]
        pools = pel.s2_pools(lines, cfip)
        rf = pel.role_fip(lines, cfip)
        lr = pel.league_role(sprp)
        pi = consts["lg_pa"] / (consts["lg_ip"] * 3.0)
        t9s = pe.t9(pi, pe.DELTA_TTO)
        cov = {"no_split": 0, "nopp": 0, "no_ip": 0}
        raw = {v: {} for v in swar.HR_VARIANTS}
        for pid, ln in lines.items():
            if ln["pos"] not in ("P", "TWP"):
                cov["nopp"] += 1
                continue
            if ln["ip"] <= 0 or ln["tbf"] <= 0:
                cov["no_ip"] += 1
                continue
            rl = sprp.get(pid)
            if not rl:
                cov["no_split"] += 1
                continue
            o_sp = (rl.get("SP") or {}).get("outs", 0.0)
            o_all = o_sp + (rl.get("RP") or {}).get("outs", 0.0)
            sigma = o_sp / o_all if o_all else 0.0
            nu = pe.s2_targets(pools["sp"], pools["rp"], sigma)
            lines_r = {r: {"n": v["n"], "pitches": v["pitches"], "outs": v["outs"]} for r, v in rl.items()}
            for variant in swar.HR_VARIANTS:
                fsk = pe.s2_skill_fip({"k": ln["k"], "bb": ln["bb"], "hbp": ln["hbp"], "hr": ln["hr"]},
                                      ln["tbf"], ln["ip"], nu, cfip, shrink_hr=(variant == swar.HR_SHRUNK))
                raw[variant][pid] = pe.pe_p_raw(lines_r, fsk, rf["RP"], t9s, lr)
        return {"delta": {v: pe.pe_p_delta(raw[v]) for v in swar.HR_VARIANTS},
                "w": pe.wear_price(rf["RP"], rf["SP"], t9s, lr["SP"]["l_ppo"]), "coverage": cov}

    def pitch_economy_wear(self, season: int) -> float:
        """w_s alone (11.4.3): the season's starter-wear runs per pitch, from the
        pooled role FIPs and the role lines; no pitcher's delta is computed."""
        import pitch_economy as pe
        import pitch_economy_lab as pel
        lines = pel.pit_lines(season)
        sprp = pel.sprp_lines(season)
        consts = pel.season_constants(season)
        rf = pel.role_fip(lines, consts["cfip"])
        lr = pel.league_role(sprp)
        t9s = pe.t9(consts["lg_pa"] / (consts["lg_ip"] * 3.0), pe.DELTA_TTO)
        return pe.wear_price(rf["RP"], rf["SP"], t9s, lr["SP"]["l_ppo"])

    def pitch_economy_hitters(self, season: int) -> Optional[dict]:
        """{"resid": {mlbam: {n, clres, m, pres}}, "pa": {mlbam: PA}} for one corpus
        season (11.4.3), or None outside the corpus. The RE288 identity must hold
        on the share pitch_economy_lab requires, or the reader raises."""
        import pitch_economy_lab as pel
        man = json.loads((pel.RECORD / "manifest.json").read_text(encoding="utf-8"))
        corpus = pel.CORPUS / "plays" / str(int(season)) / f"plays-{int(season)}.parquet"
        if str(int(season)) not in (man.get("seasons") or {}) or not corpus.exists():
            return None
        cv_doc = self._count_value()
        blk = (cv_doc.get("by_season") or {}).get(str(int(season)))
        if not blk:
            return None
        d = pel.load_corpus_season(int(season))
        w = pel.walk_corpus_season(int(season), d, blk["re288"], blk["re24"], self._dates())
        share = w["receipt"].get("identity_share") or 0.0
        if share < pel.IDENTITY_SHARE:
            raise RuntimeError(f"corpus {season}: the RE288 identity holds on {share}, under "
                               f"{pel.IDENTITY_SHARE}")
        hit = pel.hit_lines(int(season))
        pbat = {p for p, h in hit.items() if h["pos"] == "P"}
        clbar, pbar = pel.class_means(w["rows"])
        res = pel.hitter_residuals(w["rows"], clbar, pbar, pbat)
        self.meta.setdefault("re288_receipts", {})[str(int(season))] = w["receipt"]
        return {"resid": {int(b): {k: h[k] for k in ("n", "clres", "m", "pres")} for b, h in res.items()},
                "pa": {int(b): h["pa"] for b, h in hit.items() if h["pos"] != "P"}}

    def _count_value(self) -> dict:
        import pitch_economy_lab as pel
        if not hasattr(self, "_cv"):
            self._cv = json.loads(pel.COUNT_VALUE.read_text(encoding="utf-8"))
            self.meta["count_value_sha256"] = sha256_of(pel.COUNT_VALUE)
        return self._cv

    def _dates(self) -> dict:
        import pitch_economy_lab as pel
        if not hasattr(self, "_dt"):
            self._dt = pel._game_dates()
        return self._dt

    # -- the team guard's Y+1 club exposure, off the Baseball-Reference stint frames
    def team_exposure(self) -> dict:
        """{(side, season, mlbam): {team: exposure}}: PA by club (hit) and innings
        by club, IPouts / 3 (pit), from war_source's last-good stint cache."""
        import war_source
        out: dict = {}
        for side, col, key, scale in (("bat", "PA", "hit", 1.0), ("pit", "IPouts", "pit", 1.0 / 3.0)):
            df = war_source._load_last_good(side)
            if df is None or col not in df.columns:
                continue
            sub = df[["mlb_ID", "year_ID", "team_ID", col]].dropna()
            for mid, y, t, e in zip(sub["mlb_ID"], sub["year_ID"], sub["team_ID"], sub[col]):
                try:
                    k = (key, int(y), int(mid))
                except (TypeError, ValueError):
                    continue
                if float(e) <= 0:
                    continue
                blk = out.setdefault(k, {})
                blk[str(t)] = blk.get(str(t), 0.0) + float(e) * scale
        return out

    # -- the ladder gate's records
    def ladder_records(self) -> tuple[Optional[dict], Optional[dict], str]:
        import positional_fit
        ev = json.loads(LADDER_EVAL.read_text(encoding="utf-8")) if LADDER_EVAL.exists() else None
        ve = json.loads(LADDER_VERIFY.read_text(encoding="utf-8")) if LADDER_VERIFY.exists() else None
        self.meta["ladder"] = {"eval_sha256": sha256_of(LADDER_EVAL), "verify_sha256": sha256_of(LADDER_VERIFY),
                               "standing": positional_fit.POSFIT_LADDER}
        return ev, ve, str(positional_fit.POSFIT_LADDER)
