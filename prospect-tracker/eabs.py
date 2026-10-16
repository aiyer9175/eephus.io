# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eABS v0, the pure core: the run value of ABS challenges of ball and strike calls.
docs/eabs-2026-10-15/EABS_GATE.md (eabs_v0), registered before any number.

THE VALUE (gate part 1). A zone challenge at balls b, strikes s, base bits and outs
is worth v = count_value.called_pitch_value(...) on the row season's RE288 and RE24
tables (the value after a ball minus the value after a strike) if the call is
overturned, signed for the challenger's club, and 0 if it stands.

THE BUDGET (gate part 2). Two challenges per club per game, kept on success, one
granted at the start of each inning from the 10th on to a club with none left. The
cost of a failed challenge is the option value of the challenge it spends: the
mean marginal value of a held challenge, V(h, k, m) - V(h, k - 1, m), at the start
of the challenge's half-inning and of the next one, where V is the mean run value a
club went on to draw from its challenges, by half-inning h, challenges held k and
score margin bucket m, shrunk toward the (h, k) mean with K_OPT. The disclosed
constant C0 (the run value a club drew per challenge it started a game with) is
carried beside it.

THE PLAYER (gate part 3). Runs gained = sum o v; failed-challenge cost = sum (1 - o) c;
eABS raw = their difference; eABS = sum (o - p_cell)(v + c), where p_cell is the
league overturn rate of the challenge's cell (side, balls, strikes).

THE STABILITY CHECK (gate part 5) lives in stability_* below and in
tools/eabs_stability.py.

Pure: no network, no writes.
"""
from __future__ import annotations

import math
from collections import defaultdict

import count_value as cv

EABS_VERSION = "eabs_v0"
GATE_DOC = "docs/eabs-2026-10-15/EABS_GATE.md"

#: Gate part 2.
START_CHALLENGES = 2
EXTRA_FROM_INNING = 10
BUDGET_VIOLATION_MAX = 0.01
K_OPT = 100.0
H_EXTRA = 18
MARGIN_BUCKETS = ("-3 or worse", "-2 to -1", "0", "+1 to +2", "+3 or better")

#: Gate part 4.
TOL = 1e-9

#: Gate part 5.
N_MIN = 8
N_MIN_HALF = 5
BOOT = 2000
B_PLANT = 500
SEED = 20261015
SEED_TWIN = 20261016
SEED_PLANT = 20261017
SEED_NULL_PLANT = 20261018
PLANT_SD = 0.5
ALPHA = 0.05
Z95 = 1.645
AAA_SEASONS = (2022, 2023, 2024, 2025, 2026)
ROLES = ("batter", "catcher", "pitcher")


class EabsRefusal(RuntimeError):
    """A build that must not write: the message names the invariant."""


# --------------------------------------------------------------------------
# rows
# --------------------------------------------------------------------------
def as_dicts(doc: dict) -> list[dict]:
    """The ledger's columnar rows as dicts."""
    f = doc["fields"]
    return [dict(zip(f, r)) for r in doc["rows"]]


def bases_bits(code) -> int:
    """'1_3' -> 5 (ebr.base_code bits: 1 first, 2 second, 4 third)."""
    s = str(code or "___")
    return (1 if s[0:1] == "1" else 0) | (2 if s[1:2] == "2" else 0) | (4 if s[2:3] == "3" else 0)


def flags_of(row) -> list:
    f = row.get("flags")
    if not f:
        return []
    return list(f) if isinstance(f, (list, tuple)) else [f]


def exclusion(row) -> str | None:
    """Gate part 1: the reason a row is left out, or None."""
    if row.get("kind") != "zone":
        return "not_zone"
    if "call_suspect" in flags_of(row):
        return "call_suspect"
    side = row.get("challenge_side")
    oc = row.get("original_call")
    if side == "batting" and oc != "C":
        return "call_side_mismatch"
    if side == "fielding" and oc != "B":
        return "call_side_mismatch"
    if side not in ("batting", "fielding"):
        return "no_side"
    return None


def season_tables(count_value_doc: dict, season: int):
    """(t288, re24) lookups for one season of data/count_value.json."""
    blk = count_value_doc["by_season"][str(season)]
    t = blk["re288"]
    r = blk["re24"]

    def t288(b, s, base, o):
        return t[cv.cell(b, s, base, o)]

    def re24(base, o):
        return r[f"{base}|{o}"]
    return t288, re24


def challenge_value(row, t288, re24) -> float:
    """v: the run value of the challenge if overturned, for the challenger's club."""
    return float(cv.called_pitch_value(t288, re24, int(row["balls_before"]), int(row["strikes_before"]),
                                       bases_bits(row["bases_before"]), int(row["outs_before"])))


def half_index(inning: int, half: str) -> int:
    """h = 2 (inning - 1) + (0 top, 1 bottom) for innings 1 to 9; every extra half is 18."""
    inning = int(inning)
    if inning >= EXTRA_FROM_INNING:
        return H_EXTRA
    return 2 * (inning - 1) + (0 if half == "top" else 1)


def club_side(row) -> str:
    """'away' or 'home': the challenger's club."""
    top = row["half"] == "top"
    batting = row["challenge_side"] == "batting"
    return "away" if top == batting else "home"


def club_margin(row) -> int:
    bat = int(row.get("bat_score_before") or 0)
    fld = int(row.get("fld_score_before") or 0)
    return bat - fld if row["challenge_side"] == "batting" else fld - bat


def margin_bucket(m: int) -> int:
    m = int(m)
    if m <= -3:
        return 0
    if m < 0:
        return 1
    if m == 0:
        return 2
    if m <= 2:
        return 3
    return 4


def _order_key(row):
    return (int(row["inning"]), 0 if row["half"] == "top" else 1,
            int(row["at_bat_index"]), int(row.get("event_index") or 0))


# --------------------------------------------------------------------------
# the budget walk (gate 2.1)
# --------------------------------------------------------------------------
def _grant(k: dict, from_inning: int, to_inning: int) -> None:
    """Extra-inning grants for innings from_inning + 1 .. to_inning."""
    for j in range(from_inning + 1, to_inning + 1):
        if j >= EXTRA_FROM_INNING:
            for side in k:
                if k[side] == 0:
                    k[side] = 1


def budget_walk(rows: list) -> list[int]:
    """k_before for each row of ONE game (any order in, the input order out)."""
    order = sorted(range(len(rows)), key=lambda i: _order_key(rows[i]))
    k = {"away": START_CHALLENGES, "home": START_CHALLENGES}
    inning = 1
    out = [0] * len(rows)
    for i in order:
        r = rows[i]
        _grant(k, inning, int(r["inning"]))
        inning = max(inning, int(r["inning"]))
        side = club_side(r)
        out[i] = k[side]
        if not r["overturned"]:
            k[side] = max(0, k[side] - 1)
    return out


def half_points(rows: list, k_before: list, halves: list, start_scores: dict, values: list) -> list:
    """The option-model observation points of ONE game: (h, k, margin bucket, F) for
    each club at the start of each half-inning played. ``halves`` is the game's
    [(inning, half)] in order, ``start_scores`` {(inning, half): (away, home)} at that
    half's start, ``values`` v per row."""
    order = sorted(range(len(rows)), key=lambda i: _order_key(rows[i]))
    k = {"away": START_CHALLENGES, "home": START_CHALLENGES}
    inning = 1
    pts = []
    j = 0
    for (inn, half) in halves:
        hk = (int(inn), 0 if half == "top" else 1)
        while j < len(order) and _order_key(rows[order[j]])[:2] < hk:
            r = rows[order[j]]
            _grant(k, inning, int(r["inning"]))
            inning = max(inning, int(r["inning"]))
            if not r["overturned"]:
                s = club_side(r)
                k[s] = max(0, k[s] - 1)
            j += 1
        _grant(k, inning, int(inn))
        inning = max(inning, int(inn))
        away, home = start_scores.get((inn, half), (0, 0))
        h = half_index(inn, half)
        for side in ("away", "home"):
            fut = 0.0
            for i in order[j:]:
                if rows[i]["overturned"] and club_side(rows[i]) == side:
                    fut += values[i]
            m = (away - home) if side == "away" else (home - away)
            pts.append((h, k[side], margin_bucket(m), fut))
    return pts


# --------------------------------------------------------------------------
# the option-value model (gate 2.3)
# --------------------------------------------------------------------------
class OptionModel:
    def __init__(self, points: list, k_opt: float = K_OPT):
        hk = defaultdict(lambda: [0, 0.0])
        hkm = defaultdict(lambda: [0, 0.0])
        for h, k, m, f in points:
            hk[(h, k)][0] += 1
            hk[(h, k)][1] += f
            hkm[(h, k, m)][0] += 1
            hkm[(h, k, m)][1] += f
        self.k_opt = float(k_opt)
        self.hk = {key: (n, s / n) for key, (n, s) in hk.items() if n}
        self.hkm = {key: (n, s / n) for key, (n, s) in hkm.items() if n}
        self.n_points = len(points)

    def v_hk(self, h: int, k: int) -> float:
        return self.hk.get((h, k), (0, 0.0))[1]

    def v(self, h: int, k: int, m: int) -> float:
        base = self.v_hk(h, k)
        n, mean = self.hkm.get((h, k, m), (0, 0.0))
        return (n * mean + self.k_opt * base) / (n + self.k_opt)

    def cost(self, h: int, k_before: int, m: int) -> float:
        """c of a failed challenge (gate 2.3)."""
        if k_before <= 0:
            return 0.0

        def dv(x):
            return self.v(x, k_before, m) - self.v(x, k_before - 1, m)
        if h >= H_EXTRA:
            return max(0.0, dv(H_EXTRA))
        return max(0.0, (dv(h) + dv(min(h + 1, H_EXTRA))) / 2.0)

    def table(self) -> dict:
        """V(h, k) with n, for the payload."""
        return {f"{h}|{k}": {"n": n, "v": mean} for (h, k), (n, mean) in sorted(self.hk.items())}


def constant_cost(total_overturn_value: float, club_games: int) -> float:
    """C0 (gate 2.2)."""
    return total_overturn_value / club_games / 2.0 if club_games else 0.0


# --------------------------------------------------------------------------
# cells and players (gate part 3)
# --------------------------------------------------------------------------
def mix_cell(row) -> tuple:
    return (row["challenge_side"], int(row["balls_before"]), int(row["strikes_before"]))


def cell_rates(rows: list) -> dict:
    n = defaultdict(int)
    w = defaultdict(int)
    for r in rows:
        c = mix_cell(r)
        n[c] += 1
        w[c] += 1 if r["overturned"] else 0
    return {c: w[c] / n[c] for c in n}


def player_line(items: list) -> dict:
    """items: dicts with o, v, c, c0, p. The per-player quantities of gate part 3."""
    n = len(items)
    won = sum(1 for x in items if x["o"])
    rg = sum(x["v"] for x in items if x["o"])
    fc = sum(x["c"] for x in items if not x["o"])
    fc0 = sum(x["c0"] for x in items if not x["o"])
    eabs = sum((x["o"] - x["p"]) * (x["v"] + x["c"]) for x in items)
    return {"n": n, "won": won, "lost": n - won, "ovr": won / n if n else None,
            "x_ovr": sum(x["p"] for x in items) / n if n else None,
            "rg": rg, "fc": fc, "fc0": fc0, "raw": rg - fc, "raw0": rg - fc0, "eabs": eabs}


# --------------------------------------------------------------------------
# the stability check (gate part 5)
# --------------------------------------------------------------------------
def rankdata(x):
    import numpy as np
    x = np.asarray(x, dtype=float)
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x), dtype=float)
    xs = x[order]
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and xs[j + 1] == xs[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def spearman(x, y) -> float | None:
    import numpy as np
    if len(x) < 3:
        return None
    rx, ry = rankdata(x), rankdata(y)
    sx, sy = rx.std(), ry.std()
    if sx == 0 or sy == 0:
        return None
    return float(np.mean((rx - rx.mean()) * (ry - ry.mean())) / (sx * sy))


def skill(items: list, cost_key: str = "c0", rate: bool = False) -> float:
    """Per-challenge decision skill: mean (o - p)(v + c), or mean (o - p) when rate."""
    if rate:
        return sum(x["o"] - x["p"] for x in items) / len(items)
    return sum((x["o"] - x["p"]) * (x["v"] + x[cost_key]) for x in items) / len(items)


def pair_observations(by_ps: dict, seasons=AAA_SEASONS, n_min: int = N_MIN, cost_key="c0", rate=False) -> list:
    """[(player, pair_label, s_Y, s_Y1)] over consecutive season pairs.
    by_ps: {(player, season): [items]}."""
    out = []
    for y0, y1 in zip(seasons[:-1], seasons[1:]):
        lab = f"{y0}-{y1}"
        players = sorted({p for (p, s) in by_ps if s == y0} & {p for (p, s) in by_ps if s == y1})
        for p in players:
            a, b = by_ps[(p, y0)], by_ps[(p, y1)]
            if len(a) >= n_min and len(b) >= n_min:
                out.append((p, lab, skill(a, cost_key, rate), skill(b, cost_key, rate)))
    return out


def _rho_of(obs: list):
    return spearman([o[2] for o in obs], [o[3] for o in obs])


def bootstrap_rho(obs: list, b: int = BOOT, seed: int = SEED) -> dict:
    """Player-clustered bootstrap of the pooled Spearman rho (gate 5.3)."""
    import numpy as np
    rho = _rho_of(obs)
    players = sorted({o[0] for o in obs})
    by_p = defaultdict(list)
    for o in obs:
        by_p[o[0]].append(o)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(b):
        pick = rng.integers(0, len(players), len(players)) if players else []
        sample = [o for i in pick for o in by_p[players[i]]]
        r = _rho_of(sample)
        if r is not None:
            draws.append(r)
    draws = np.asarray(draws, dtype=float)
    if rho is None or not len(draws):
        return {"rho": rho, "n_obs": len(obs), "n_players": len(players), "draws": int(len(draws)),
                "sd": None, "lo95": None, "p": None, "mde95": None}
    sd = float(draws.std(ddof=1))
    return {"rho": rho, "n_obs": len(obs), "n_players": len(players), "draws": int(len(draws)),
            "sd": sd, "lo95": float(np.percentile(draws, 5)), "p": float(np.mean(draws <= 0.0)),
            "mde95": Z95 * sd}


def permuted_twin(obs: list, seed: int = SEED_TWIN) -> list:
    """Within each season pair, the Y+1 values permuted across that pair's players."""
    import numpy as np
    rng = np.random.default_rng(seed)
    out = []
    for lab in sorted({o[1] for o in obs}):
        grp = [o for o in obs if o[1] == lab]
        perm = rng.permutation(len(grp))
        for o, j in zip(grp, perm):
            out.append((o[0], o[1], o[2], grp[j][3]))
    return out


def holm(pvals: dict, alpha: float = ALPHA) -> dict:
    """Holm-adjusted p per key (None stays None)."""
    keys = sorted((k for k, p in pvals.items() if p is not None), key=lambda k: pvals[k])
    m = len(keys)
    adj, run = {}, 0.0
    for i, k in enumerate(keys):
        run = max(run, min(1.0, (m - i) * pvals[k]))
        adj[k] = run
    for k, p in pvals.items():
        if p is None:
            adj[k] = None
    return adj


def disposition(real: dict, twin: dict, plant: dict, null_plant: dict, p_holm, crashed: bool = False) -> str:
    """Gate 5.4, precedence top to bottom."""
    def lo(d):
        return None if d is None else d.get("lo95")
    if crashed or real.get("rho") is None:
        return "VOID"
    if (lo(twin) is not None and lo(twin) > 0) or (lo(null_plant) is not None and lo(null_plant) > 0):
        return "VOID"
    if lo(plant) is None or lo(plant) <= 0:
        return "UNDERPOWERED"
    if p_holm is not None and p_holm < ALPHA:
        gap = real["rho"] - (twin.get("rho") or 0.0)
        return "PERSISTS" if real.get("mde95") is not None and gap > real["mde95"] else "SMALL"
    return "NULL"


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def expit(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))
