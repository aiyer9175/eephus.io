# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The circularity guard of the core eWAR label epoch, read ONCE
(docs/efv-2026-10-22/EWAR_CORE_LABEL_EPOCH_GATE.md part 4).

    python tools/ewar_core_label_guard.py --dry-run   # fixtures with nulls, no real data
    python tools/ewar_core_label_guard.py --look      # THE LOOK: once; writes the record

G-1 (player): over hitter pairs with 300+ PA in Y and Y + 1 (Y in 2011 to 2018 and 2021
to 2024), the pair-weighted mean of within-season Spearman correlations with published
fWAR(Y + 1), for the core label against published fWAR(Y); gap = S(core) - S(fWAR);
player-clustered bootstrap B 2,000 seed 20261022; NON-INFERIOR when the 5th percentile of
the drawn gaps is above -0.02. The permuted twin (the label's departures permuted within
each season) is scored on the same draws and decides nothing.

G-2 (club): tools/swar_targets.team_guard verbatim (the eBR gate's 11.2.4) on next-season
runs scored, runs allowed, run differential and wins; NON-INFERIOR when dT - 1.645 sd >
-0.02 under both bootstraps for every carried outcome, and not underpowered (a half-width
above 0.02 is not NON-INFERIOR, part 4.2).

THE GUARD HOLDS when G-1 and G-2 are both NON-INFERIOR. Secondary legs (part 4.3) decide
nothing. Reads only the frozen fWAR vintage, data/ewar_core_label.json and the cached
Baseball-Reference stint frames and StatsAPI standings; never fetches; relates no dark
betting column to anything and reads no grade.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

GATE_DOC = "docs/efv-2026-10-22/EWAR_CORE_LABEL_EPOCH_GATE.md"
RECORD = ROOT / "docs" / "efv-2026-10-22" / "ewar_core_label_guard.json"
LAB_VERSION = "ewar_core_label_guard/1"

# --------------------------------------------------------------------------
# registered parameters (gate part 4)
# --------------------------------------------------------------------------

PREDICTOR_SEASONS = (2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2021, 2022, 2023, 2024)
R2_SEASONS = (2016, 2017, 2018, 2021, 2022, 2023, 2024)
MIN_PA = 300.0
MIN_PA_SECONDARY = 200.0
MIN_IP = 50.0
BOOT = 2000
SEED = 20261022
MARGIN = -0.02
Z95 = 1.645
FRAMING_RUNS_EPS = 0.05
GUARD_OUTCOMES = (("runs_scored", "hit"), ("runs_allowed", "hit"),
                  ("run_differential", "total"), ("wins", "total"))
HIT, PIT = "hit", "pit"


class GuardStop(RuntimeError):
    """A precondition failed before scoring began: nothing is written."""


# --------------------------------------------------------------------------
# inputs (the dry run subclasses this with fixtures)
# --------------------------------------------------------------------------

class GuardInputs:
    """Every input the look reads. Nothing here fetches."""

    def season_rows(self) -> dict:
        """{season: {"hit": {mlbam: {"war", "pa", "frm_runs"}}, "pit": {mlbam: {"war", "ip"}}}}
        from the frozen fWAR vintage."""
        import ewar_history as H
        import fwar_vintage
        vin = fwar_vintage.load()
        out: dict = {}
        for s in fwar_vintage.fwar_seasons(vin):
            hit, pit = H._season_rows(vin, s)
            out[int(s)] = {
                HIT: {int(m): {"war": _f(r.get("war")), "pa": _f(r.get("plateAppearances")),
                               "frm_runs": H._frm(r)} for m, r in hit.items()},
                PIT: {int(m): {"war": _f(r.get("war")),
                               "ip": (_f(r.get("outs")) / 3.0) if _f(r.get("outs")) is not None else None}
                      for m, r in pit.items()},
            }
        return out

    def departures(self, series: str) -> dict:
        import ewar_core_label
        return ewar_core_label.departures(series=series)

    def label_meta(self) -> dict:
        import ewar_core_label
        blob = ewar_core_label.load()
        return {"vintage_id": blob.get("vintage_id"), "content_sha256": blob.get("content_sha256"),
                "fwar_vintage_id": blob.get("fwar_vintage_id"),
                "file_sha256": _sha_file(ewar_core_label.OUT)}

    def bwar(self) -> dict:
        import swar_lab
        return swar_lab.LabInputs().bwar()

    def team_exposure(self) -> dict:
        import swar_targets as T
        return T.Readers().team_exposure()

    def standings(self, seasons) -> dict:
        import ewar
        return ewar.standings(seasons)

    def input_meta(self) -> dict:
        import war_source
        return {"bwar_cache_sha256": {s: _sha_file(war_source._cache_path(s)) for s in ("bat", "pit")}}


def _f(v) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _sha_file(path) -> Optional[str]:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


# --------------------------------------------------------------------------
# pure statistics
# --------------------------------------------------------------------------

def _rank(a: np.ndarray) -> np.ndarray:
    from scipy.stats import rankdata
    return rankdata(a, method="average")


def _spearman(x: np.ndarray, y: np.ndarray) -> Optional[float]:
    if len(x) < 3:
        return None
    rx, ry = _rank(x), _rank(y)
    if np.std(rx) == 0 or np.std(ry) == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def weighted_within(series: np.ndarray, target: np.ndarray, season: np.ndarray,
                    idx: Optional[np.ndarray] = None) -> Optional[float]:
    """The pair-count-weighted mean over seasons of the within-season Spearman of
    `series` with `target` (rows `idx`, with repeats, or every row)."""
    if idx is None:
        idx = np.arange(len(series))
    num, den = 0.0, 0
    s_idx = season[idx]
    for s in np.unique(s_idx):
        sel = idx[s_idx == s]
        rho = _spearman(series[sel], target[sel])
        if rho is None:
            continue
        num += rho * len(sel)
        den += len(sel)
    return num / den if den else None


def cluster_draws(players: np.ndarray, boot: int, seed: int) -> list[np.ndarray]:
    """Player-clustered draws: players with replacement, each with all its rows."""
    uniq = np.unique(players)
    rows_of = {p: np.flatnonzero(players == p) for p in uniq}
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(boot):
        pick = rng.integers(0, len(uniq), len(uniq))
        out.append(np.concatenate([rows_of[uniq[k]] for k in pick]))
    return out


def gap_cell(a: np.ndarray, b: np.ndarray, target: np.ndarray, season: np.ndarray,
             draws: list[np.ndarray], extra: Optional[Mapping[str, np.ndarray]] = None) -> dict:
    """gap = S(a) - S(b), its drawn distribution, lower (5th percentile), sd, MDE95 and
    the verdict; `extra` series are scored against b on the same draws (the twin)."""
    sa, sb = weighted_within(a, target, season), weighted_within(b, target, season)
    gap = None if sa is None or sb is None else sa - sb
    gs, ex = [], {k: [] for k in (extra or {})}
    for idx in draws:
        xb = weighted_within(b, target, season, idx)
        xa = weighted_within(a, target, season, idx)
        if xa is not None and xb is not None:
            gs.append(xa - xb)
        for k, v in (extra or {}).items():
            xv = weighted_within(v, target, season, idx)
            if xv is not None and xb is not None:
                ex[k].append(xv - xb)

    def summ(point, ds) -> dict:
        ds = np.asarray(ds, float)
        if point is None or len(ds) < 10:
            return {"gap": point, "lower": None, "sd": None, "mde95": None, "n_draws": int(len(ds)),
                    "non_inferior": False}
        lower = float(np.percentile(ds, 5))
        sd = float(np.std(ds, ddof=1))
        return {"gap": float(point), "lower": lower, "upper95": float(np.percentile(ds, 95)), "sd": sd,
                "mde95": Z95 * sd, "n_draws": int(len(ds)), "non_inferior": bool(lower > MARGIN)}

    out = {"s_series": sa, "s_fwar": sb, "n_pairs": int(len(a)),
           "n_seasons": int(len(np.unique(season))), **summ(gap, gs)}
    for k, v in (extra or {}).items():
        sv = weighted_within(v, target, season)
        out[k] = summ(None if sv is None or sb is None else sv - sb, ex[k])
    return out


# --------------------------------------------------------------------------
# pairs and series
# --------------------------------------------------------------------------

def hitter_pairs(rows: Mapping, seasons, min_pa: float) -> list[dict]:
    out = []
    for y in seasons:
        a, b = (rows.get(y) or {}).get(HIT) or {}, (rows.get(y + 1) or {}).get(HIT) or {}
        for m in sorted(a):
            r0, r1 = a[m], b.get(m)
            if r1 is None or r0.get("war") is None or r1.get("war") is None:
                continue
            if (r0.get("pa") or 0.0) < min_pa or (r1.get("pa") or 0.0) < min_pa:
                continue
            out.append({"mlbam": m, "season": y, "war": r0["war"], "pa": r0["pa"], "war1": r1["war"],
                        "pa1": r1["pa"], "frm_runs": r0.get("frm_runs") or 0.0})
    return out


def pitcher_pairs(rows: Mapping, seasons, min_ip: float) -> list[dict]:
    out = []
    for y in seasons:
        a, b = (rows.get(y) or {}).get(PIT) or {}, (rows.get(y + 1) or {}).get(PIT) or {}
        for m in sorted(a):
            r0, r1 = a[m], b.get(m)
            if r1 is None or r0.get("war") is None or r1.get("war") is None:
                continue
            if (r0.get("ip") or 0.0) < min_ip or (r1.get("ip") or 0.0) < min_ip:
                continue
            out.append({"mlbam": m, "season": y, "war": r0["war"], "war1": r1["war"]})
    return out


def twin_departures(rows: Mapping, deps: Mapping, seasons, seed: int) -> dict:
    """{(mlbam, season): d}: each season's hitting departures permuted among that
    season's hitting rows (seasons ascending, rows in ascending mlbam), one generator."""
    rng = np.random.default_rng(seed)
    out = {}
    for y in sorted(seasons):
        ms = sorted(m for m, r in ((rows.get(y) or {}).get(HIT) or {}).items() if r.get("war") is not None)
        vals = np.array([(deps.get((m, y)) or {}).get("bat", 0.0) for m in ms], float)
        perm = rng.permutation(len(ms))
        for m, v in zip(ms, vals[perm]):
            out[(m, y)] = float(v)
    return out


def _arr(pairs, f) -> np.ndarray:
    return np.array([f(p) for p in pairs], float)


def g1(rows: Mapping, deps: Mapping, twin: Mapping, seasons, min_pa: float, boot: int, seed: int,
       rate: bool = False, subset: Optional[Callable] = None) -> dict:
    pairs = hitter_pairs(rows, seasons, min_pa)
    if subset is not None:
        pairs = [p for p in pairs if subset(p)]
    if not pairs:
        return {"n_pairs": 0, "non_inferior": False, "gap": None}
    d = _arr(pairs, lambda p: (deps.get((p["mlbam"], p["season"])) or {}).get("bat", 0.0))
    tw = _arr(pairs, lambda p: twin.get((p["mlbam"], p["season"]), 0.0))
    war, pa = _arr(pairs, lambda p: p["war"]), _arr(pairs, lambda p: p["pa"])
    tgt = _arr(pairs, lambda p: p["war1"])
    if rate:
        scale = 600.0 / pa
        tgt = tgt * 600.0 / _arr(pairs, lambda p: p["pa1"])
        a, b, t = (war + d) * scale, war * scale, (war + tw) * scale
    else:
        a, b, t = war + d, war, war + tw
    season = _arr(pairs, lambda p: p["season"]).astype(int)
    players = _arr(pairs, lambda p: p["mlbam"]).astype(np.int64)
    draws = cluster_draws(players, boot, seed)
    out = gap_cell(a, b, tgt, season, draws, extra={"twin": t})
    out["n_players"] = int(len(np.unique(players)))
    out["n_pairs_departing"] = int(np.sum(d != 0.0))
    return out


def g1_pitchers_realized(rows: Mapping, real: Mapping, seasons, boot: int, seed: int) -> dict:
    pairs = pitcher_pairs(rows, seasons, MIN_IP)
    if not pairs:
        return {"n_pairs": 0, "gap": None, "non_inferior": False}
    d = _arr(pairs, lambda p: (real.get((p["mlbam"], p["season"])) or {}).get("pit", 0.0))
    war, tgt = _arr(pairs, lambda p: p["war"]), _arr(pairs, lambda p: p["war1"])
    season = _arr(pairs, lambda p: p["season"]).astype(int)
    players = _arr(pairs, lambda p: p["mlbam"]).astype(np.int64)
    out = gap_cell(war + d, war, tgt, season, cluster_draws(players, boot, seed))
    out["n_players"] = int(len(np.unique(players)))
    return out


def g2(rows: Mapping, deps: Mapping, bwar: Mapping, team_exp: Mapping, standings: Mapping,
       seasons, boot: int) -> dict:
    """The eBR gate's team guard (11.2.4) with frame = fWAR and part = the label."""
    import swar_targets as T
    ys = [int(y) for y in seasons]
    clubs = sorted({(y + 1, t) for y in ys for t in (standings.get(y + 1) or {})})
    if not clubs:
        raise GuardStop("the team guard has no club-season with standings")

    def num(v):
        x = _f(v)
        return np.nan if x is None else x

    outcomes = {
        "runs_scored": np.array([num(standings[s][t].get("rs")) for s, t in clubs], float),
        "runs_allowed": np.array([-num(standings[s][t].get("ra")) for s, t in clubs], float),
        "run_differential": np.array([num(standings[s][t].get("rs")) - num(standings[s][t].get("ra"))
                                      for s, t in clubs], float),
        "wins": np.array([float(standings[s][t]["w"]) for s, t in clubs], float),
    }
    expo_key = {HIT: "pa", PIT: "ip"}
    players = sorted({m for y in ys for side in (HIT, PIT) for m in ((rows.get(y) or {}).get(side) or {})})
    nxt = {side: {(s, m): e for (sd, s, m), e in team_exp.items() if sd == side} for side in (HIT, PIT)}

    def mat(side: str, value_of) -> np.ndarray:
        vals, expo = {}, {}
        for y in ys:
            for m, r in ((rows.get(y) or {}).get(side) or {}).items():
                vals[(y, m)] = value_of(m, y, r)
                expo[(y, m)] = r.get(expo_key[side])
        return T.roster_matrix(vals, expo, nxt[side], players, clubs)

    bkey = {HIT: "bat", PIT: "pit"}
    mats = {}
    for side in (HIT, PIT):
        frame = mat(side, lambda m, y, r: r.get("war"))
        ref = mat(side, lambda m, y, r, s=side: (bwar.get((m, y)) or {}).get(bkey[s]))
        if side == HIT:
            part = mat(side, lambda m, y, r: None if r.get("war") is None
                       else r["war"] + (deps.get((m, y)) or {}).get("bat", 0.0))
        else:
            part = frame
        mats[side] = {"frame": frame, "part": part, "ref": ref}
    g = T.team_guard(mats, outcomes, GUARD_OUTCOMES, clubs, boot=boot, seed=T.GUARD_SEED)
    g["seed"] = T.GUARD_SEED
    g["boot"] = boot
    g["holds"] = bool(g["non_inferior"] and not g["underpowered"])
    return g


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

def run(inputs: GuardInputs, boot: int = BOOT, log: Callable = print) -> dict:
    rows = inputs.season_rows()
    need = sorted({y for y in PREDICTOR_SEASONS} | {y + 1 for y in PREDICTOR_SEASONS})
    missing = [y for y in need if y not in rows]
    if missing:
        raise GuardStop(f"the vintage lacks seasons {missing}")
    deps = inputs.departures("headline")
    real = inputs.departures("realized")
    meta = inputs.label_meta()
    log(f"[guard] label {meta.get('vintage_id')}; predictor seasons {PREDICTOR_SEASONS}; B {boot}; "
        f"seed {SEED} (G-1), team guard seed per 11.2.4")
    twin = twin_departures(rows, deps, PREDICTOR_SEASONS, SEED)
    log("[guard] scoring began")
    G1 = g1(rows, deps, twin, PREDICTOR_SEASONS, MIN_PA, boot, SEED)
    log(f"[G-1] pairs {G1['n_pairs']} players {G1.get('n_players')} gap {G1.get('gap')} lower "
        f"{G1.get('lower')} sd {G1.get('sd')} => {'NON-INFERIOR' if G1['non_inferior'] else 'not non-inferior'}; "
        f"twin gap {G1.get('twin', {}).get('gap')} lower {G1.get('twin', {}).get('lower')}")
    standings = inputs.standings([y + 1 for y in PREDICTOR_SEASONS])
    G2 = g2(rows, deps, inputs.bwar(), inputs.team_exposure(), standings, PREDICTOR_SEASONS, boot)
    for name, o in G2["outcomes"].items():
        log(f"[G-2] {name:16s} n {o['n_club_seasons']} dT {o['dT']} lower player {o['player'].get('lower')} "
            f"club {o['club'].get('lower')} => {'NON-INFERIOR' if o['non_inferior'] else 'not non-inferior'}")
    log(f"[G-2] guard {'NON-INFERIOR' if G2['non_inferior'] else 'NOT NON-INFERIOR'}"
        f"{' (underpowered)' if G2['underpowered'] else ''}")
    sec = {
        "rate_per_600pa": g1(rows, deps, twin, PREDICTOR_SEASONS, MIN_PA, boot, SEED, rate=True),
        "floor_200pa": g1(rows, deps, twin, PREDICTOR_SEASONS, MIN_PA_SECONDARY, boot, SEED),
        "realized_core_pitchers": g1_pitchers_realized(rows, real, R2_SEASONS, boot, SEED),
        "framing_rows": g1(rows, deps, twin, PREDICTOR_SEASONS, MIN_PA, boot, SEED,
                           subset=lambda p: abs(p["frm_runs"]) > FRAMING_RUNS_EPS),
    }
    for k, v in sec.items():
        log(f"[secondary] {k}: n {v.get('n_pairs')} gap {v.get('gap')} lower {v.get('lower')}")
    holds = bool(G1["non_inferior"] and G2["holds"])
    twin_also = bool(G1.get("twin", {}).get("non_inferior"))
    log(f"[guard] THE GUARD {'HOLDS' if holds else 'DOES NOT HOLD'}"
        + (" (the permuted twin is also NON-INFERIOR: G-1 cannot separate the label's change from a random "
           "change of the same size)" if twin_also else ""))
    return {
        "schema": 1, "lab": LAB_VERSION, "registration": GATE_DOC,
        "label": meta, "inputs": inputs.input_meta(),
        "parameters": {"predictor_seasons": list(PREDICTOR_SEASONS), "min_pa": MIN_PA, "boot": boot,
                       "seed": SEED, "margin": MARGIN, "outcomes": [list(o) for o in GUARD_OUTCOMES],
                       "r2_seasons": list(R2_SEASONS), "min_ip": MIN_IP},
        "g1": G1, "g2": _jsonable(G2), "secondary": sec,
        "verdict": {"g1_non_inferior": G1["non_inferior"], "g2_non_inferior": G2["holds"],
                    "guard_holds": holds, "twin_also_non_inferior": twin_also},
    }


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return [_jsonable(v) for v in o.tolist()]
    return o


# --------------------------------------------------------------------------
# fixtures (the dry run; tests reuse them)
# --------------------------------------------------------------------------

class FixtureInputs(GuardInputs):
    """Synthetic seasons with nulls. `noise` sets the planted departure size:
    0.0 is the identity series (the label equals fWAR), a large value plants noise."""

    def __init__(self, noise: float = 0.0, seed: int = 7, n_players: int = 120):
        rng = np.random.default_rng(seed)
        self._rows: dict = {}
        self._deps: dict = {}
        talent = rng.normal(0, 1.5, n_players)
        teams = [f"T{i}" for i in range(10)]
        self._team = {}
        seasons = sorted({y for y in PREDICTOR_SEASONS} | {y + 1 for y in PREDICTOR_SEASONS})
        for y in seasons:
            hit, pit = {}, {}
            for i in range(n_players):
                m = 1000 + i
                war = None if (i + y) % 37 == 0 else float(talent[i] + rng.normal(0, 1.0))
                pa = float(rng.integers(150, 700))
                hit[m] = {"war": war, "pa": pa, "frm_runs": 0.2 if i % 15 == 0 else 0.0}
                pit[5000 + i] = {"war": float(rng.normal(1, 1)), "ip": float(rng.integers(20, 200))}
                if noise:
                    self._deps[(m, y)] = {"bat": float(rng.normal(0, noise))}
                self._team[(HIT, y, m)] = {teams[i % 10]: pa}
                self._team[(PIT, y, 5000 + i)] = {teams[i % 10]: 100.0}
            hit[999999] = {"war": None, "pa": None, "frm_runs": 0.0}
            self._rows[y] = {HIT: hit, PIT: pit}
        self._stand = {y: {t: {"w": int(rng.integers(60, 100)), "rs": float(rng.integers(600, 850)),
                               "ra": float(rng.integers(600, 850))} for t in teams} for y in seasons}

    def season_rows(self):
        return self._rows

    def departures(self, series):
        return dict(self._deps)

    def label_meta(self):
        return {"vintage_id": "fixture", "content_sha256": None, "fwar_vintage_id": "fixture",
                "file_sha256": None}

    def bwar(self):
        return {(m, y): {"bat": r["war"]} for y, blk in self._rows.items()
                for m, r in blk[HIT].items() if r["war"] is not None}

    def team_exposure(self):
        return self._team

    def standings(self, seasons):
        return {y: self._stand[y] for y in seasons if y in self._stand}

    def input_meta(self):
        return {"fixture": True}


def _git_head() -> Optional[str]:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="fixtures with nulls; no real data, no write")
    g.add_argument("--look", action="store_true", help="THE LOOK: once, on real data; writes the record")
    ap.add_argument("--boot", type=int, default=None, help="dry run only")
    a = ap.parse_args(argv)
    if a.dry_run:
        for noise in (0.0, 3.0):
            rec = run(FixtureInputs(noise=noise), boot=a.boot or 200)
            json.dumps(rec, allow_nan=True)
            print(f"[dry-run] planted departure sd {noise}: guard holds {rec['verdict']['guard_holds']}")
        return 0
    if a.boot is not None:
        print("--boot is fixed at the registered B on the look")
        return 2
    if RECORD.exists():
        print(f"REFUSED: {RECORD} exists; the look runs once")
        return 2
    started = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
    try:
        rec = run(GuardInputs(), boot=BOOT)
    except GuardStop as e:
        print(f"STOP before scoring: {e}")
        return 3
    rec["run"] = {"started_at": started,
                  "finished_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat(),
                  "git_head": _git_head(), "command": "python tools/ewar_core_label_guard.py --look"}
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps(_jsonable(rec), indent=1, ensure_ascii=True, allow_nan=True) + "\n",
                      encoding="utf-8")
    print(f"written {RECORD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
