# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eBR (eephus baserunning): the pure core. docs/ebr-2026-09-30/EBR_GATE.md part 2.

WHAT IT IS. Runs above average a runner added or cost on the bases in one MLB
regular season, against an average runner in the same spot, from MLB's per-runner
play-by-play (the runner record of tools/build_runner_moves.py). Descriptive: it
counts what happened and predicts nothing. Five parts, each summing to zero over
every runner of a season:

  eSB      steals, caught stealing and pickoff caught stealing, priced on the run
           expectancy change of each attempt (a double steal: the lead runner
           first, the trail runner from that intermediate state), centred by the
           league value per opportunity from each base;
  ePK      pickoffs of a runner not attempting, centred per base;
  eXB_adv, advancement and outs on the bases on hits, caught air balls and
  eXB_oob  unforced ground-ball outs (classes H, B, A, G), each chance priced
           against the league outcome distribution in the same context
           (hierarchical backoff, kappa 20 pseudo-counts), split exactly into the
           advance part and the out part, centred per season and class;
  eGDP     the batter's double plays against the league rate in his base-out
           state at the final pitch, at that state's cost.

Display parts: SB runs = eSB + ePK; XB runs = eXB_adv + eXB_oob; DP runs = eGDP;
eBR = their sum.

THE RUN BASIS. Per-season RE24 on a fit set (innings 1 to 8 and the top of the
9th, or 1 to 6 and the top of the 7th in a scheduled seven-inning game; half
innings that reached three outs; none carrying a runner_placed event), by the
recipe of win_expectancy.run_expectancy re-implemented here (that function
refuses a cell under MIN_RE_N 500 and is never called), shrunk toward a pooled
table over P = 2018, 2019, 2021 to 2026 with one constant K by the method of
moments, clipped to [500, 5000]. The pool, K and the pooled outcome counts are
computed ONCE and frozen with EBR_VERSION (FROZEN_* below): adding a later season
never moves a completed one. Each season's table is monotone or the build
refuses, and ships with its sha256.

WHAT IT IS NOT. Not the /management/ steal number (win expectancy, a league
runner, two-out attempts left out); never summed with it. No park term and no
fielder-arm term in the number: arms P and F are computed beside it
(``arm_reports``) and never change it. No shrinkage of player values. No
year-to-year, split-half or forward statistic is computed here or by any caller
other than tools/ebr_gate.py on its registered day.

Pure: no network, no writes. tools/build_ebr.py reads the record and writes the
previews.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict

EBR_VERSION = "ebr_v1"
POOL_SEASONS: tuple[int, ...] = (2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026)
KAPPA = 20.0
K_CLIP = (500.0, 5000.0)
CELLS = tuple(f"{b}|{o}" for b in range(8) for o in (0, 1, 2))

#: The frozen pool of ebr_v1: K and the sha256 of the frozen pool document
#: (pooled RE24 cells and pooled outcome counts), pinned after the one
#: computation on P (2026-10-14; the same digest as the first computation of
#: 2026-10-09: W 1.54068, tau^2 0.00093129, K_raw 1654.4, inside the clip). A
#: build whose recomputed pool differs refuses.
FROZEN_K: float | None = 1654.4
FROZEN_POOL_SHA256: str | None = "83d30956fafca3e44b183baab82aa80f5332c3c65ed940eaab31b6faba09de24"

# outcome labels for eXB: a safe base (1, 2, 3, 4 = home), OUT, DP
OUT, DP = 5, 6
OUTCOMES = (1, 2, 3, 4, OUT, DP)
CLASSES = ("H", "B", "A", "G")
HIT_EVENTS = {"single": 1, "double": 2}
AIR_TRAJ = {"fly_ball": "F", "line_drive": "L", "popup": "P"}
AIR_EVENTS = ("field_out", "sac_fly", "double_play", "sac_fly_double_play")
GROUND_EVENTS = ("field_out", "force_out", "fielders_choice", "fielders_choice_out",
                 "grounded_into_double_play", "double_play")
GROUND_NON_DP = ("field_out", "force_out", "fielders_choice", "fielders_choice_out")
LOC_GROUP = {"7": "LF", "8": "CF", "9": "RF", "1": "IF", "2": "IF", "3": "IF", "4": "IF",
             "5": "IF", "6": "IF"}
HB_TRAJ = {"ground_ball": "G", "bunt_grounder": "G", "fly_ball": "A", "line_drive": "A",
           "popup": "A", "bunt_popup": "A", "bunt_line_drive": "A"}
HOME_X, HOME_Y = 125.42, 198.27
_BASE_NUM = {"1B": 1, "2B": 2, "3B": 3}
_SCORE = ("score", "4B")
_TARGET = {"2b": 2, "3b": 3, "home": 4}
GIDP_STATES = (1, 3, 5, 7)


class EbrRefusal(RuntimeError):
    """A build that must not write: the message names the season and the cause."""


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _isna(v) -> bool:
    return v is None or (isinstance(v, float) and v != v) or str(v) in ("<NA>", "nan")


def _bits3(a, b, c) -> int:
    return (0 if _isna(a) else 1) | (0 if _isna(b) else 2) | (0 if _isna(c) else 4)


def _int(v):
    return None if _isna(v) else int(v)


# --------------------------------------------------------------------------
# 2.3 the run basis
# --------------------------------------------------------------------------
def base_code(df):
    """The 3-bit occupancy of the PA-start state, occupancy read with notna()."""
    return (df["on_first"].notna().astype(int) + 2 * df["on_second"].notna().astype(int)
            + 4 * df["on_third"].notna().astype(int))


def runs_to_end(df):
    """Runs from each play to the end of its half-inning, inclusive, in row order:
    the recipe of win_expectancy.run_expectancy (one groupby, cumsum)."""
    hi = (df["game_pk"].astype(str) + "|" + df["inning"].astype(str) + "|" + df["half"].astype(str))
    cum = df.groupby(hi, sort=False)["runs_scored_on_play"].cumsum()
    tot = df.groupby(hi, sort=False)["runs_scored_on_play"].transform("sum")
    return (tot - cum + df["runs_scored_on_play"]).astype(float)


def raw_cells(df) -> dict:
    """{cell: {"n", "mean", "var"}} over the rows given (the recipe, no MIN_RE_N)."""
    import numpy as np
    ros = runs_to_end(df).to_numpy()
    base = df["_base"].to_numpy() if "_base" in df.columns else base_code(df).to_numpy()
    outs = df["outs_before"].astype(int).to_numpy()
    out = {}
    for b in range(8):
        for o in (0, 1, 2):
            sel = (base == b) & (outs == o)
            n = int(sel.sum())
            if n == 0:
                continue
            x = ros[sel]
            out[f"{b}|{o}"] = {"n": n, "mean": float(x.mean()),
                               "var": float(x.var(ddof=1)) if n > 1 else 0.0}
    return out


def fit_mask(pa):
    """The fit set F_s of a season's play rows (EBR_GATE.md 2.3)."""
    import numpy as np
    sched = pa["scheduled_innings"].fillna(9).astype(int).to_numpy() if "scheduled_innings" in pa else 9
    inning = pa["inning"].astype(int).to_numpy()
    top = pa["half"].astype(str).str.startswith("top").to_numpy()
    reg = (inning <= (sched - 1)) | ((inning == sched) & top)
    hi = (pa["game_pk"].astype(str) + "|" + pa["inning"].astype(str) + "|" + pa["half"].astype(str))
    maxouts = pa.groupby(hi, sort=False)["outs_after"].transform("max").fillna(0).astype(int).to_numpy()
    if "runner_placed" in pa.columns:
        placed = pa.groupby(hi, sort=False)["runner_placed"].transform("max").astype(bool).to_numpy()
    else:
        placed = np.zeros(len(pa), dtype=bool)
    return reg & (maxouts == 3) & (~placed)


def season_raw(pa) -> dict:
    """Raw per-season cells on the fit set. The runs-to-end are computed on the
    whole half-inning first (a fit-set half keeps every play of its half)."""
    d = pa.copy()
    d["_base"] = base_code(d)
    d["_ros"] = runs_to_end(d)
    d = d[fit_mask(pa)]
    import numpy as np
    out = {}
    base = d["_base"].to_numpy()
    outs = d["outs_before"].astype(int).to_numpy()
    ros = d["_ros"].to_numpy()
    for b in range(8):
        for o in (0, 1, 2):
            sel = (base == b) & (outs == o)
            n = int(sel.sum())
            if n == 0:
                continue
            x = ros[sel]
            out[f"{b}|{o}"] = {"n": n, "mean": float(x.mean()),
                               "var": float(np.var(x, ddof=1)) if n > 1 else 0.0}
    return out


def pool_table(raw_by_season: dict) -> dict:
    """{cell: pooled mean} over the given seasons' raw cells."""
    pool = {}
    for c in CELLS:
        n = sum(raw_by_season[s][c]["n"] for s in raw_by_season if c in raw_by_season[s])
        if n == 0:
            raise EbrRefusal(f"pool cell {c} is empty")
        pool[c] = sum(raw_by_season[s][c]["n"] * raw_by_season[s][c]["mean"]
                      for s in raw_by_season if c in raw_by_season[s]) / n
    return pool


def season_lambda(raw: dict, pool: dict) -> float:
    num = sum(raw[c]["n"] * raw[c]["mean"] for c in CELLS if c in raw)
    den = sum(raw[c]["n"] * pool[c] for c in CELLS if c in raw)
    return num / den


def shrink_constant(raw_by_season: dict, pool: dict) -> dict:
    """K = W / tau^2 by the method of moments over the 24 cells (the bundle's
    _re24_cells.py): per cell the lambda-adjusted season means, their between-season
    variance net of sampling variance (tau^2 of the cell, floored at 0) and the
    n-weighted within-cell variance; W and tau^2 are the means over cells;
    K clipped to [500, 5000]."""
    import numpy as np
    seasons = sorted(raw_by_season)
    lam = {s: season_lambda(raw_by_season[s], pool) for s in seasons}
    within, tau = [], []
    for c in CELLS:
        ms = np.array([raw_by_season[s][c]["mean"] / lam[s] for s in seasons])
        ns = np.array([raw_by_season[s][c]["n"] for s in seasons], dtype=float)
        vs = np.array([raw_by_season[s][c]["var"] / lam[s] ** 2 for s in seasons])
        between = float(np.var(ms, ddof=1)) if len(seasons) > 1 else 0.0
        samp = float(np.mean(vs / ns))
        tau.append(max(between - samp, 0.0))
        within.append(float(np.average(vs, weights=ns)))
    w = float(np.mean(within))
    t2 = float(np.mean(tau))
    k_raw = (w / t2) if t2 > 0 else float("inf")
    k = min(max(k_raw, K_CLIP[0]), K_CLIP[1])
    return {"K": round(k, 1), "K_raw": (round(k_raw, 1) if math.isfinite(k_raw) else None),
            "W": round(w, 6), "tau2": round(t2, 8)}


ADD_RUNNER = {1: (0,), 2: (0,), 3: (1, 2), 4: (0,), 5: (1, 4), 6: (2, 4), 7: (3, 5, 6)}


def monotone_violations(table: dict) -> list:
    v = []
    for o in (0, 1, 2):
        for b, lows in ADD_RUNNER.items():
            for lo in lows:
                if table[f"{b}|{o}"] < table[f"{lo}|{o}"]:
                    v.append(f"{lo}->{b}@{o}")
    for b in range(8):
        for o in (0, 1):
            if table[f"{b}|{o + 1}"] > table[f"{b}|{o}"]:
                v.append(f"{b}@{o}->{o + 1}")
    return v


def shrunk_table(raw: dict, pool: dict, k: float, season=None) -> dict:
    """RE_s(c) = [n raw + K lambda pool] / [n + K]; 24 cells, monotone, or refuse."""
    if any(c not in raw for c in CELLS):
        missing = [c for c in CELLS if c not in raw]
        raise EbrRefusal(f"season {season}: RE24 fit set lacks cells {missing}")
    lam = season_lambda(raw, pool)
    t = {c: (raw[c]["n"] * raw[c]["mean"] + k * lam * pool[c]) / (raw[c]["n"] + k) for c in CELLS}
    bad = monotone_violations(t)
    if bad:
        raise EbrRefusal(f"season {season}: RE24 is not monotone ({bad})")
    return t


def table_sha(table: dict) -> str:
    return _sha({c: round(table[c], 6) for c in CELLS})


def pool_doc_sha(doc: dict) -> str:
    return _sha({k: v for k, v in doc.items() if k != "sha256"})


def frozen_pool_document(raw_by_season: dict, opps_by_season: dict) -> dict:
    """The ebr_v1 pool, computed ONCE over P: the pooled RE24 cells, K with its
    method-of-moments inputs, and the pooled eXB outcome counts at the root of the
    backoff chain. Every P season must be present."""
    missing = [s for s in POOL_SEASONS if s not in raw_by_season or s not in opps_by_season]
    if missing:
        raise EbrRefusal(f"the frozen pool needs every season of P; missing {missing}")
    raw = {s: raw_by_season[s] for s in POOL_SEASONS}
    pool = pool_table(raw)
    k = shrink_constant(raw, pool)
    doc = {"ebr_version": EBR_VERSION, "pool_seasons": list(POOL_SEASONS), "kappa": KAPPA,
           "k_clip": list(K_CLIP), "re_pool": {c: round(pool[c], 9) for c in CELLS},
           "K": k["K"], "K_raw": k["K_raw"], "W": k["W"], "tau2": k["tau2"],
           "fit_set_plays": {str(s): int(sum(v["n"] for v in raw[s].values())) for s in POOL_SEASONS},
           "lambda": {str(s): round(season_lambda(raw[s], pool), 6) for s in POOL_SEASONS},
           "xb_pool_counts": pool_counts({s: opps_by_season[s] for s in POOL_SEASONS})}
    doc["sha256"] = pool_doc_sha(doc)
    return doc


def check_frozen_pool(doc: dict) -> None:
    """Refuse a pool document that is not the one frozen with EBR_VERSION."""
    if doc.get("ebr_version") != EBR_VERSION or tuple(doc.get("pool_seasons") or ()) != POOL_SEASONS:
        raise EbrRefusal("the pool document is not ebr_v1's")
    if doc.get("sha256") != pool_doc_sha(doc):
        raise EbrRefusal("the pool document's sha256 does not match its content")
    if FROZEN_POOL_SHA256 is not None and doc["sha256"] != FROZEN_POOL_SHA256:
        raise EbrRefusal(f"the pool differs from the one frozen with {EBR_VERSION} "
                         f"({doc['sha256'][:12]} against {FROZEN_POOL_SHA256[:12]})")
    if FROZEN_K is not None and float(doc["K"]) != float(FROZEN_K):
        raise EbrRefusal(f"K {doc['K']} differs from the frozen {FROZEN_K}")


class RE:
    """A season's RE24 lookup with RE(., 3) = 0."""

    def __init__(self, table: dict):
        self.t = [[table[f"{b}|{o}"] for o in (0, 1, 2)] for b in range(8)]

    def __call__(self, bits: int, outs: int) -> float:
        return 0.0 if outs >= 3 else self.t[bits][outs]


# --------------------------------------------------------------------------
# 2.5 eSB and ePK
# --------------------------------------------------------------------------
def _reason_kind(reason: str):
    if not reason:
        return None
    if reason.startswith("r_stolen_base"):
        return "sb"
    if reason.startswith(("r_caught_stealing", "r_pickoff_caught_stealing")):
        return "cs"
    if reason.startswith("r_pickoff_error"):
        return None
    if reason in ("r_pickoff_1b", "r_pickoff_2b", "r_pickoff_3b"):
        return "pk"
    return None


def _target(reason: str):
    suf = reason.rsplit("_", 1)[-1]
    return _TARGET.get(suf)


def attempt_values(rn, re_: RE) -> list:
    """[(runner, team, game_pk, kind, origin, rv)] for every steal attempt and every
    pickoff of a runner not attempting, valued at its own playIndex group state;
    on the final-pitch group the batter's own outcome comes first."""
    out = []
    reasons = rn["movement_reason"].fillna("").astype(str)
    sel = reasons.map(lambda r: _reason_kind(r) is not None)
    pk_rows = rn[sel & ~((reasons.isin(["r_pickoff_1b", "r_pickoff_2b", "r_pickoff_3b"]))
                         & ~rn["is_out"].astype(bool))]
    if not len(pk_rows):
        return out
    keys = set(zip(pk_rows["game_pk"], pk_rows["at_bat_index"], pk_rows["play_index"]))
    grp_rows = rn[[k in keys for k in zip(rn["game_pk"], rn["at_bat_index"], rn["play_index"])]]
    by = defaultdict(list)
    for r in grp_rows.itertuples(index=False):
        by[(r.game_pk, r.at_bat_index, r.play_index)].append(r)
    for key in sorted(by):
        rows = sorted(by[key], key=lambda r: r.seq)
        first = rows[0]
        bits, outs = int(first.base_before_group), int(first.outs_before_group)
        if bool(first.is_final_pitch_group):
            for r in rows:
                if bool(r.is_batter):
                    if bool(r.is_out):
                        outs += 1
                    elif r.end in _BASE_NUM:
                        bits |= 1 << (_BASE_NUM[r.end] - 1)
                    break
        atts = [r for r in rows if _reason_kind(str(r.movement_reason or "")) is not None
                and not (str(r.movement_reason) in ("r_pickoff_1b", "r_pickoff_2b", "r_pickoff_3b")
                         and not bool(r.is_out))]
        lead = {}
        for r in atts:
            o = _BASE_NUM.get(r.start)
            if o is not None:
                lead.setdefault(r.runner_id, o)
        atts.sort(key=lambda r: (-(lead.get(r.runner_id) or 0), r.seq))
        for r in atts:
            origin = _BASE_NUM.get(r.start)
            kind = _reason_kind(str(r.movement_reason))
            if origin is None:
                continue
            b0, o0 = bits, outs
            b1, o1, runs = b0 & ~(1 << (origin - 1)), o0, 0
            if kind == "sb":
                t = _target(str(r.movement_reason))
                if t is None:
                    continue
                if t == 4:
                    runs = 1
                else:
                    b1 |= 1 << (t - 1)
            else:
                o1 = o0 + 1
            rv = (runs if o0 < 3 else 0) + re_(b1, o1) - re_(b0, o0)
            bits, outs = b1, o1
            out.append((int(r.runner_id), _int(r.bat_team_id), int(r.game_pk),
                        "pk" if kind == "pk" else "sb", origin, rv,
                        1 if kind == "sb" else 0, 1 if kind == "cs" else 0))
    return out


def start_opportunities(pa) -> list:
    """[(runner, team, game_pk, base, steal_opportunity)] from every play's start
    state: E for the steal parts (1B with 2B open, 2B with 3B open, 3B) and P for
    the pickoff part (any start on that base)."""
    out = []
    cols = (pa["on_first"].tolist(), pa["on_second"].tolist(), pa["on_third"].tolist(),
            pa["bat_team_id"].tolist(), pa["game_pk"].tolist())
    for f, s, t, team, g in zip(*cols):
        f, s, t = _int(f), _int(s), _int(t)
        team = _int(team)
        if f is not None:
            out.append((f, team, int(g), 1, s is None))
        if s is not None:
            out.append((s, team, int(g), 2, t is None))
        if t is not None:
            out.append((t, team, int(g), 3, True))
    return out


def steal_parts(pa, rn, re_: RE) -> tuple[list, dict]:
    """Event-level credits of eSB and ePK and the league blocks (m, mPK)."""
    atts = attempt_values(rn, re_)
    opps = start_opportunities(pa)
    rv_sb, rv_pk = defaultdict(float), defaultdict(float)
    for _, _, _, kind, origin, rv, _, _ in atts:
        (rv_sb if kind == "sb" else rv_pk)[origin] += rv
    e_n, p_n = defaultdict(int), defaultdict(int)
    for _, _, _, base, is_e in opps:
        p_n[base] += 1
        if is_e:
            e_n[base] += 1
    m = {b: (rv_sb[b] / e_n[b] if e_n[b] else 0.0) for b in (1, 2, 3)}
    mpk = {b: (rv_pk[b] / p_n[b] if p_n[b] else 0.0) for b in (1, 2, 3)}
    credits = []
    for runner, team, g, kind, origin, rv, sb, cs in atts:
        credits.append((runner, team, g, kind, rv))
    for runner, team, g, base, is_e in opps:
        if is_e and m[base]:
            credits.append((runner, team, g, "sb", -m[base]))
        if mpk[base]:
            credits.append((runner, team, g, "pk", -mpk[base]))
    league = {"m_sb": {str(b): round(m[b], 6) for b in m}, "m_pk": {str(b): round(mpk[b], 6) for b in mpk},
              "attempts": sum(1 for a in atts if a[3] == "sb"),
              "pickoffs": sum(1 for a in atts if a[3] == "pk"),
              "sb": sum(a[6] for a in atts), "cs": sum(a[7] for a in atts),
              "steal_opportunities": {str(b): e_n[b] for b in (1, 2, 3)},
              "starts_on_base": {str(b): p_n[b] for b in (1, 2, 3)}}
    return credits, league


# --------------------------------------------------------------------------
# 2.5 eXB
# --------------------------------------------------------------------------
def _runner_outcome(entries: list, k: int, m: int):
    """(outcome, error_truncated) of one runner from his contact-group entries:
    the end of his last segment without an error credit; m if the first carries one."""
    segs = []
    trunc = False
    for e in entries:
        if bool(e.error_credit):
            trunc = True
            break
        segs.append(e)
    if trunc and not segs:
        return m, True
    if not segs:
        return k, trunc
    if any(bool(e.is_out) for e in segs):
        return OUT, trunc
    end = segs[-1].end
    if end in _SCORE:
        return 4, trunc
    if end in _BASE_NUM:
        return _BASE_NUM[end], trunc
    return k, trunc


def _actual_end(entries: list, k: int):
    """A runner ahead's actual end (context): base, 4 scored, OUT, regardless of errors."""
    if not entries:
        return k
    if any(bool(e.is_out) for e in entries):
        return OUT
    end = entries[-1].end
    if end in _SCORE:
        return 4
    if end in _BASE_NUM:
        return _BASE_NUM[end]
    return k


def _depth(x, y):
    if _isna(x) or _isna(y):
        return None
    return math.hypot(float(x) - HOME_X, HOME_Y - float(y))


def xb_opportunities(pa, rn) -> list:
    """Every eXB chance of a season, with its context and everything needed to price it."""
    by_pa = defaultdict(list)
    for r in rn.itertuples(index=False):
        by_pa[(r.game_pk, r.at_bat_index)].append(r)
    opps = []
    for p in pa.itertuples(index=False):
        if _isna(p.in_play_index):
            continue
        et = p.event_type
        traj = None if _isna(p.trajectory) else str(p.trajectory)
        o = _int(p.fp_outs) or 0
        on = {1: _int(p.fp_on_first), 2: _int(p.fp_on_second), 3: _int(p.fp_on_third)}
        h = HIT_EVENTS.get(et)
        is_air = traj in AIR_TRAJ and et in AIR_EVENTS and o < 2
        is_gb = traj == "ground_ball" and et in GROUND_EVENTS and o < 2
        if h is None and not is_air and not is_gb:
            continue
        ip = int(p.in_play_index)
        ents = sorted((e for e in by_pa.get((p.game_pk, p.at_bat_index), ()) if int(e.play_index) >= ip),
                      key=lambda e: e.seq)
        by_runner = defaultdict(list)
        for e in ents:
            if not _isna(e.runner_id):
                by_runner[int(e.runner_id)].append(e)
        batter = _int(p.batter_id)
        bat_ents = list(by_runner.get(batter, [])) if batter is not None else []
        batter_out = any(bool(e.is_out) for e in bat_ents)
        actual = {k: _actual_end(by_runner.get(on[k], []), k) for k in (1, 2, 3) if on[k] is not None}
        loc = LOC_GROUP.get(None if _isna(p.hit_location) else str(p.hit_location))
        dist = _depth(p.coord_x, p.coord_y)
        flag = int(o == 2 and _int(p.fp_balls) == 3 and _int(p.fp_strikes) == 2)
        base_ctx = {"game_pk": int(p.game_pk), "team": _int(p.bat_team_id), "o": o,
                    "on": on, "actual": actual, "batter": batter, "batter_out": batter_out,
                    "loc": loc, "dist": dist, "flag": flag, "venue": _int(p.venue_id),
                    "home_team": (_int(p.fld_team_id) if str(p.half).startswith("top") else _int(p.bat_team_id)),
                    "fielder_loc": (None if _isna(p.hit_location) else str(p.hit_location)),
                    "of_ids": {"LF": _int(p.of_left_id), "CF": _int(p.of_center_id), "RF": _int(p.of_right_id)}}
        if h is not None:
            mins = {}
            prev = h
            for k in (1, 2, 3):
                if on[k] is None:
                    continue
                mins[k] = max(k, prev + 1)
                prev = mins[k]
            tg = HB_TRAJ.get(traj)
            for k in (1, 2, 3):
                if on[k] is None or (h == 2 and k == 3):
                    continue
                opps.append(dict(base_ctx, c="H", k=k, r=on[k], m=mins[k], h=h, traj=tg,
                                 ents=by_runner.get(on[k], [])))
            if batter is not None:
                opps.append(dict(base_ctx, c="B", k=0, r=batter, m=h, h=h, traj=tg,
                                 ents=[e for e in bat_ents]))
        elif is_air:
            for k in (1, 2, 3):
                if on[k] is None:
                    continue
                opps.append(dict(base_ctx, c="A", k=k, r=on[k], m=k, h=None, traj=AIR_TRAJ[traj],
                                 ents=by_runner.get(on[k], [])))
        else:
            for k in (2, 3):
                if on[k] is None:
                    continue
                forced = (on[1] is not None) if k == 2 else (on[1] is not None and on[2] is not None)
                if forced:
                    continue
                opps.append(dict(base_ctx, c="G", k=k, r=on[k], m=k, h=None, traj=None,
                                 ents=by_runner.get(on[k], [])))
    return opps


def _ahead_info(op):
    """(L label, upper bound on r's safe base) from the runners ahead of r."""
    k, on, actual = op["k"], op["on"], op["actual"]
    ahead = [j for j in (1, 2, 3) if j > k and on[j] is not None]
    bound = 5
    for j in ahead:
        a = actual[j]
        if a in (1, 2, 3):
            bound = min(bound, a)
    if not ahead:
        return "none", bound
    a = actual[min(ahead)]
    if a == 4:
        lab = "S"
    elif a == OUT:
        lab = "O"
    else:
        lab = f"B{a}"
    return lab, bound


def finalize_opportunities(opps: list) -> None:
    """Outcome, feasible set and context keys of each chance (in place). Depth
    terciles are cut within (class, location group) of the season's own chances."""
    import numpy as np
    cuts = {}
    by = defaultdict(list)
    for op in opps:
        if op["c"] in ("H", "B", "A") and op["loc"] in ("LF", "CF", "RF") and op["dist"] is not None:
            by[(op["c"], op["loc"])].append(op["dist"])
    for key, xs in by.items():
        cuts[key] = (float(np.quantile(xs, 1 / 3)), float(np.quantile(xs, 2 / 3)))
    for op in opps:
        c, k, m = op["c"], op["k"], op["m"]
        lab, bound = _ahead_info(op)
        op["L"] = lab
        safe = [y for y in (1, 2, 3, 4) if m <= y < bound]
        feas = safe + [OUT] + ([DP] if c == "G" else [])
        op["Y"] = feas
        y, trunc = _runner_outcome(op["ents"], k if c != "B" else op["h"], m)
        if c == "G" and y == OUT and op["batter_out"]:
            y = DP
        clamped = False
        if y in (1, 2, 3, 4) and y not in safe:
            clamped = True
            y = (safe[0] if y < m and safe else (safe[-1] if safe else OUT))
        op["y"], op["trunc"], op["clamped"] = y, trunc, clamped
        loc, d = op["loc"], op["dist"]
        if c in ("H", "B", "A"):
            if loc in ("LF", "CF", "RF"):
                if d is None:
                    depth = None
                else:
                    lo, hi = cuts[(c, loc)]
                    depth = 0 if d <= lo else (1 if d <= hi else 2)
            else:
                depth = "-"
            op["depth"] = depth
        else:
            op["depth"] = "-"
        base = (c, k, op["o"], lab)
        if c == "G":
            f = op["fielder_loc"] if op["fielder_loc"] in ("1", "2", "3", "4", "5", "6") else None
            levels = [base + ("f", f) if f is not None else None, None, None, base]
        else:
            tr = op["traj"]
            l1 = (base + (loc, tr, depth) + ((op["flag"],) if c in ("H", "B") else ())
                  if loc is not None and tr is not None and depth is not None else None)
            l2 = base + (loc, tr) if loc is not None and tr is not None else None
            l3 = base + (loc,) if loc is not None else None
            levels = [l1, l2, l3, base]
        op["levels"] = levels


def pool_counts(opps_by_season: dict) -> dict:
    """Pooled outcome counts for the root of the backoff chain: by (c, k, o, L),
    (c, k, o) and (c, k), as {key string: {outcome: n}}."""
    acc = defaultdict(lambda: defaultdict(int))
    for s, opps in opps_by_season.items():
        for op in opps:
            c, k, o, lab = op["c"], op["k"], op["o"], op["L"]
            for key in (f"{c}|{k}|{o}|{lab}", f"{c}|{k}|{o}", f"{c}|{k}"):
                acc[key][op["y"]] += 1
    return {key: {str(y): n for y, n in sorted(v.items())} for key, v in sorted(acc.items())}


def _outcome_space(c):
    return (1, 2, 3, 4, OUT, DP) if c == "G" else (1, 2, 3, 4, OUT)


class Backoff:
    """pi(y | x) over the chain full z -> drop depth -> drop trajectory -> drop
    location -> (s, c, k, o, L) -> the frozen pool (internally (c, k, o, L) ->
    (c, k, o) -> (c, k), its root the empirical (c, k) share with half a count
    per outcome so no outcome has zero mass)."""

    def __init__(self, opps: list, pool: dict, kappa: float = KAPPA):
        self.kappa = kappa
        self.pool = pool
        self.n = defaultdict(lambda: defaultdict(int))
        for op in opps:
            for key in op["levels"]:
                if key is not None:
                    self.n[key][op["y"]] += 1
        self._cache = {}

    def _pool_pi(self, c, k, o, lab):
        key = ("P", c, k, o, lab)
        if key in self._cache:
            return self._cache[key]
        ys = _outcome_space(c)
        root = self.pool.get(f"{c}|{k}") or {}
        nr = sum(root.values())
        pi = {y: (root.get(str(y), 0) + 0.5) / (nr + 0.5 * len(ys)) for y in ys}
        for sub in (f"{c}|{k}|{o}", f"{c}|{k}|{o}|{lab}"):
            cnt = self.pool.get(sub) or {}
            n = sum(cnt.values())
            pi = {y: (cnt.get(str(y), 0) + self.kappa * pi[y]) / (n + self.kappa) for y in ys}
        self._cache[key] = pi
        return pi

    def pi(self, op) -> tuple[dict, int, int]:
        """(pi over the class's outcomes, the starting level, n at that level)."""
        c, k, o, lab = op["c"], op["k"], op["o"], op["L"]
        pi = self._pool_pi(c, k, o, lab)
        ys = _outcome_space(c)
        levels = op["levels"]
        start = None
        for i, key in enumerate(levels):
            if key is not None:
                start = i
                break
        n_start = 0
        for i in range(len(levels) - 1, -1, -1):
            key = levels[i]
            if key is None or i < start:
                continue
            cnt = self.n.get(key) or {}
            n = sum(cnt.values())
            pi = {y: (cnt.get(y, 0) + self.kappa * pi[y]) / (n + self.kappa) for y in ys}
            if i == start:
                n_start = n
        return pi, start, n_start


def outcome_value(op, y, re_: RE) -> float:
    """v(y | x) on the fixed reference of EBR_GATE.md 2.5."""
    c, k, on, actual = op["c"], op["k"], op["on"], op["actual"]
    bits, outs, runs = 0, op["o"], 0
    for j in (1, 2, 3):
        if on[j] is None or j <= k:
            continue
        a = actual[j]
        if a == OUT:
            outs += 1
        elif a == 4:
            runs += 1
        else:
            bits |= 1 << (a - 1)
    if y == OUT:
        outs += 1
    elif y == DP:
        outs += 2
    elif y == 4:
        runs += 1
    else:
        bits |= 1 << (y - 1)
    if c == "H":
        bits |= 1 << (op["h"] - 1)
        prev = op["h"]
        for j in (1, 2, 3):
            if j >= k or on[j] is None:
                continue
            mj = max(j, prev + 1)
            prev = mj
            if mj >= 4:
                runs += 1
            else:
                bits |= 1 << (mj - 1)
    elif c == "A":
        outs += 1
        for j in (1, 2, 3):
            if j < k and on[j] is not None:
                bits |= 1 << (j - 1)
    elif c == "G":
        if y == OUT:
            bits |= 1
        elif y != DP:
            outs += 1
        for j in (1, 2, 3):
            if j >= k or on[j] is None:
                continue
            forced = (j == 1) or (j == 2 and on[1] is not None)
            if forced:
                a = actual[j]
                if a == OUT:
                    outs += 1
                elif a == 4:
                    runs += 1
                else:
                    bits |= 1 << (a - 1)
            else:
                bits |= 1 << (j - 1)
    return runs + re_(bits, outs)


def xb_parts(opps: list, re_: RE, backoff: Backoff, *, pi_override=None) -> tuple[list, dict]:
    """Event-level eXB credits (adv and oob, centred per class) and the league block."""
    rows = []
    stats = defaultdict(lambda: defaultdict(float))
    for op in opps:
        if pi_override is not None:
            pi, start, n_start = pi_override(op)
        else:
            pi, start, n_start = backoff.pi(op)
        feas = op["Y"]
        tot = sum(pi[y] for y in feas)
        if tot <= 0:
            continue
        pf = {y: pi[y] / tot for y in feas}
        v = {y: outcome_value(op, y, re_) for y in feas}
        v_m = outcome_value(op, op["m"], re_) if op["m"] not in v else v[op["m"]]
        E = sum(pf[y] * v[y] for y in feas)
        yi = op["y"]
        e = v[yi] - E
        oob = sum(((1.0 if yi == y else 0.0) - pf[y]) * (v[y] - v_m) for y in feas if y in (OUT, DP))
        adv = e - oob
        rows.append([op["r"], op["team"], op["game_pk"], op["c"], adv, oob])
        st = stats[op["c"]]
        st["n"] += 1
        st["clamped"] += int(op["clamped"])
        st["truncated_for_error"] += int(op["trunc"])
        st["priced_n50"] += int(n_start >= 50)
        st["sum_adv"] += adv
        st["sum_oob"] += oob
    means = {c: ((stats[c]["sum_adv"] / stats[c]["n"]) if stats[c]["n"] else 0.0,
                 (stats[c]["sum_oob"] / stats[c]["n"]) if stats[c]["n"] else 0.0) for c in CLASSES}
    credits = []
    for r, team, g, c, adv, oob in rows:
        ma, mo = means[c]
        credits.append((r, team, g, "xb_adv", adv - ma))
        credits.append((r, team, g, "xb_oob", oob - mo))
    league = {"opportunities": {c: int(stats[c]["n"]) for c in CLASSES},
              "clamped": {c: int(stats[c]["clamped"]) for c in CLASSES},
              "truncated_for_error": {c: int(stats[c]["truncated_for_error"]) for c in CLASSES},
              "share_priced_from_cell_n50": {c: (round(stats[c]["priced_n50"] / stats[c]["n"], 4)
                                                  if stats[c]["n"] else None) for c in CLASSES},
              "class_mean_before_centring": {c: [round(means[c][0], 6), round(means[c][1], 6)]
                                             for c in CLASSES}}
    return credits, league


# --------------------------------------------------------------------------
# 2.5 eGDP
# --------------------------------------------------------------------------
def dp_parts(pa, re_: RE) -> tuple[list, dict]:
    """Event-level eGDP credits and the league table p_s(b, o), c_s(b, o)."""
    opps = []
    n_start_opps = 0
    for p in pa.itertuples(index=False):
        if not bool(p.is_pa):
            continue
        if not _isna(p.on_first) and (_int(p.outs_before) or 0) < 2:
            n_start_opps += 1
        if _isna(p.fp_on_first):
            continue
        o = _int(p.fp_outs) or 0
        if o >= 2:
            continue
        b = _bits3(p.fp_on_first, p.fp_on_second, p.fp_on_third)
        gidp = p.event_type == "grounded_into_double_play"
        after = (_int(p.runs_fp) or 0) + re_(_bits3(p.end_on_first, p.end_on_second, p.end_on_third),
                                             _int(p.end_outs) or 0)
        gb_non_dp = (str(p.trajectory) == "ground_ball" and p.event_type in GROUND_NON_DP)
        opps.append((_int(p.batter_id), _int(p.bat_team_id), int(p.game_pk), b, o, gidp, gb_non_dp, after))
    n = defaultdict(int)
    g = defaultdict(int)
    nd_sum, nd_n, dp_sum, dp_n = (defaultdict(float), defaultdict(int), defaultdict(float),
                                  defaultdict(int))
    for _, _, _, b, o, gidp, gnd, after in opps:
        n[(b, o)] += 1
        g[(b, o)] += int(gidp)
        if gidp:
            dp_sum[(b, o)] += after
            dp_n[(b, o)] += 1
        elif gnd:
            nd_sum[(b, o)] += after
            nd_n[(b, o)] += 1
    p_s = {key: g[key] / n[key] for key in n}
    c_s = {key: ((nd_sum[key] / nd_n[key]) - (dp_sum[key] / dp_n[key])
                 if nd_n[key] and dp_n[key] else 0.0) for key in n}
    credits = []
    for batter, team, gm, b, o, gidp, _, _ in opps:
        if batter is None:
            continue
        credits.append((batter, team, gm, "dp", -((1.0 if gidp else 0.0) - p_s[(b, o)]) * c_s[(b, o)]))
    league = {"table": {f"{b}|{o}": {"opportunities": n[(b, o)], "gidp": g[(b, o)],
                                     "p": round(p_s[(b, o)], 6), "cost": round(c_s[(b, o)], 6)}
                        for (b, o) in sorted(n)},
              "opportunities_final_pitch": len(opps), "opportunities_pa_start": n_start_opps,
              "gidp": sum(g.values())}
    return credits, league


# --------------------------------------------------------------------------
# a season, end to end
# --------------------------------------------------------------------------
PARTS = ("sb", "pk", "xb_adv", "xb_oob", "dp")


def season_credits(pa, rn, re_table: dict, pool_counts_: dict, *, opps=None) -> tuple[list, dict, list]:
    """(credits, league, opps): credits are (mlbam, team, game_pk, part, runs),
    one per priced event or opportunity, summing per season to zero by part."""
    re_ = RE(re_table)
    c_sb, l_sb = steal_parts(pa, rn, re_)
    if opps is None:
        opps = xb_opportunities(pa, rn)
        finalize_opportunities(opps)
    bo = Backoff(opps, pool_counts_)
    c_xb, l_xb = xb_parts(opps, re_, bo)
    c_dp, l_dp = dp_parts(pa, re_)
    return c_sb + c_xb + c_dp, {"steal": l_sb, "xb": l_xb, "dp": l_dp}, opps


def player_rows(credits: list, pa, opps: list) -> dict:
    """{mlbam: {"teams": {team: parts}, "pa", "starts_on_base", "opp_sb", "opp_xb",
    "opp_dp"}} from a season's credits and the record."""
    out = defaultdict(lambda: {"teams": defaultdict(lambda: defaultdict(float)),
                               "pa": defaultdict(int), "starts_on_base": 0, "opp_sb": 0,
                               "opp_xb": 0, "opp_dp": 0})
    for mid, team, _, part, v in credits:
        if mid is None:
            continue
        out[mid]["teams"][team][part] += v
    for p in pa.itertuples(index=False):
        b = _int(p.batter_id)
        if b is not None and bool(p.is_pa):
            out[b]["pa"][_int(p.bat_team_id)] += 1
            if not _isna(p.fp_on_first) and (_int(p.fp_outs) or 0) < 2:
                out[b]["opp_dp"] += 1
        for base, col, nxt in ((1, p.on_first, p.on_second), (2, p.on_second, p.on_third),
                               (3, p.on_third, None)):
            r = _int(col)
            if r is None:
                continue
            out[r]["starts_on_base"] += 1
            if base == 3 or _isna(nxt):
                out[r]["opp_sb"] += 1
    for op in opps:
        out[op["r"]]["opp_xb"] += 1
    return out


def substrate_rows(season: int, players: dict, *, digits: int = 3) -> list:
    """Rows in integration.md 4.5's field order: mlbam, season, pa, starts_on_base,
    opp_sb, opp_xb, opp_dp, sb, pk, xb_adv, xb_oob, dp, ebr, stints."""
    rows = []
    for mid in sorted(players):
        blk = players[mid]
        tot = defaultdict(float)
        for team, parts in blk["teams"].items():
            for p, v in parts.items():
                tot[p] += v
        teams = sorted(set(blk["teams"]) | set(blk["pa"]), key=lambda t: (t is None, t))
        vals = [round(tot[p], digits) for p in PARTS]
        ebr_v = round(sum(tot[p] for p in PARTS), digits)
        stints = None
        if len([t for t in teams if t is not None]) > 1:
            stints = []
            for t in teams:
                parts = blk["teams"].get(t) or {}
                stints.append([t, int(blk["pa"].get(t, 0))] + [round(parts.get(p, 0.0), digits) for p in PARTS])
        rows.append([int(mid), int(season), int(sum(blk["pa"].values())), int(blk["starts_on_base"]),
                     int(blk["opp_sb"]), int(blk["opp_xb"]), int(blk["opp_dp"])] + vals + [ebr_v, stints])
    return rows


FIELDS = ("mlbam", "season", "pa", "starts_on_base", "opp_sb", "opp_xb", "opp_dp",
          "sb", "pk", "xb_adv", "xb_oob", "dp", "ebr", "stints")


# --------------------------------------------------------------------------
# 2.8 arms P and F: beside the number, never in it
# --------------------------------------------------------------------------
def arm_p_override(opps: list, prior_opps: list, backoff: Backoff, kappa: float = KAPPA):
    """pi under arm P: a venue x location-group level above the primary chain,
    counted from VISITING runners only over the prior seasons given."""
    n = defaultdict(lambda: defaultdict(int))
    for op in prior_opps:
        if op["team"] is None or op["team"] == op["home_team"] or op["loc"] is None:
            continue
        n[(op["venue"], op["c"], op["k"], op["o"], op["loc"])][op["y"]] += 1

    def over(op):
        pi, start, n0 = backoff.pi(op)
        key = (op["venue"], op["c"], op["k"], op["o"], op["loc"])
        cnt = n.get(key)
        if not cnt or op["loc"] is None:
            return pi, start, n0
        tot = sum(cnt.values())
        return {y: (cnt.get(y, 0) + kappa * pi[y]) / (tot + kappa) for y in pi}, start, n0
    return over


def arm_f_override(opps: list, arm_tercile, backoff: Backoff, kappa: float = KAPPA):
    """pi under arm F: the fielding outfielder's prior-season arm tercile as a
    level for outfield-fielded balls (``arm_tercile(fielder_id) -> 0, 1, 2 or None``)."""
    def tercile(op):
        if op["loc"] not in ("LF", "CF", "RF") or op["c"] == "G":
            return None
        fid = op["of_ids"].get(op["loc"])
        return None if fid is None else arm_tercile(fid)
    n = defaultdict(lambda: defaultdict(int))
    for op in opps:
        t = tercile(op)
        top = next((k for k in op["levels"] if k is not None), None)
        if t is not None and top is not None:
            n[top + ("arm", t)][op["y"]] += 1

    def over(op):
        pi, start, n0 = backoff.pi(op)
        t = tercile(op)
        top = next((k for k in op["levels"] if k is not None), None)
        if t is None or top is None:
            return pi, start, n0
        cnt = n.get(top + ("arm", t)) or {}
        tot = sum(cnt.values())
        return {y: (cnt.get(y, 0) + kappa * pi[y]) / (tot + kappa) for y in pi}, start, n0
    return over


def xb_by_runner(credits: list) -> dict:
    out = defaultdict(float)
    for r, _, _, part, v in credits:
        if part in ("xb_adv", "xb_oob"):
            out[r] += v
    return out


def arm_report(primary_rows: list, opps: list, re_table: dict, backoff: Backoff, override,
               *, movers_runs: float = 1.0) -> dict:
    """Correlation of each runner's eBR under the arm with the primary, and the
    count of runners moved by at least ``movers_runs`` (never names)."""
    import numpy as np
    c_arm, _ = xb_parts(opps, RE(re_table), backoff, pi_override=override)
    xb_arm = xb_by_runner(c_arm)
    prim = {r[0]: r for r in primary_rows}
    a, b = [], []
    for mid, row in prim.items():
        e = row[FIELDS.index("ebr")]
        xb = row[FIELDS.index("xb_adv")] + row[FIELDS.index("xb_oob")]
        a.append(e)
        b.append(e - xb + xb_arm.get(mid, 0.0))
    a, b = np.array(a), np.array(b)
    r = float(np.corrcoef(a, b)[0, 1]) if len(a) > 2 and a.std() > 0 and b.std() > 0 else None
    d = np.abs(b - a)
    return {"r_with_primary": (round(r, 4) if r is not None else None), "n_runners": int(len(a)),
            "n_moved_1_run_or_more": int((d >= movers_runs).sum()),
            "max_abs_move_runs": round(float(d.max()), 3) if len(d) else None}
