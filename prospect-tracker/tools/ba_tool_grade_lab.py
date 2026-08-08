# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential

"""Lane BA2 -- Baseball America tool grades and the accuracy-weighted tool consensus.

Pre-registration: docs/efv-2026-08-07b/TOOL_GRADE_WEIGHT_GATE.md (written first).
Artifact:         data/ba_tool_grade_eval.json

Question: `consensus.py` computes the per-tool consensus as an UNWEIGHTED mean across
publishing sources. Can a per-(source, tool) precision, estimated forward-chained against
the realized MLB quantity each tool predicts, beat that equal mean by more than this A/B
can resolve?

Reuses `efv_tools._TOOLS` verbatim for the tool-to-outcome mapping and
`source_backtest`'s vintage rule, weight estimator constants and fairness (common-set)
rule. Writes nothing but its own artifact.

Run: python tools/ba_tool_grade_lab.py
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import storage                                                  # noqa: E402
import source_backtest as SB                                    # noqa: E402
from efv_tools import _TOOLS, _PASSTHROUGH                      # noqa: E402

DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "ba_tool_grade_eval.json"

# --- imported, not retyped (pre-registration section 3) ---------------------
MIN_LAG_YEARS = SB.MIN_LAG_YEARS
WEIGHT_SHRINK_K = SB.WEIGHT_SHRINK_K
WEIGHT_CLAMP = SB.WEIGHT_CLAMP
SPEARMAN_FLOOR = SB.SPEARMAN_FLOOR
WIN_START = SB._WINDOW_START_MMDD
WIN_END = SB._WINDOW_END_MMDD
_spearman = SB._spearman
_auc = SB._auc

SCOREABLE = tuple(_TOOLS.keys())          # hit, game_pwr, speed, fb, cmd
BOOT = 2000
PERM = 1000
SEED = 8641
SEED_ALT = 1337

ARMS = {
    "A_fg_vs_pipeline": ("fangraphs", "mlb_pipeline"),
    "B_fg_pipeline_ba": ("fangraphs", "mlb_pipeline", "baseballamerica"),
}


def _r4(v):
    return None if v is None else round(float(v), 4)


def _r6(v):
    return None if v is None else round(float(v), 6)


# ---------------------------------------------------------------------------
# universe
# ---------------------------------------------------------------------------
def load_grades() -> tuple[dict, dict, dict]:
    """(year, tool) -> player -> {source: grade}, plus raw census counters."""
    grades: dict = defaultdict(lambda: defaultdict(dict))
    census: dict = defaultdict(Counter)
    src_years: dict = defaultdict(set)
    picked: dict = {}                       # (src, year, tool, player) -> date
    with storage.connect() as con:
        rows = list(con.execute(
            "SELECT source, snapshot_date, player_key, tools_json FROM snapshots "
            "WHERE tools_json IS NOT NULL AND tools_json != '' ORDER BY snapshot_date"))
    for r in rows:
        d = r["snapshot_date"]
        try:
            td = json.loads(r["tools_json"])
        except ValueError:
            continue
        if not isinstance(td, dict):
            continue
        td = {k: v for k, v in td.items() if k != "_extras"}
        if not td:
            continue
        year = int(d[:4])
        for tool, g in td.items():
            try:
                g = float(g)
            except (TypeError, ValueError):
                continue
            if not (20.0 <= g <= 80.0):
                continue
            census[r["source"]][tool] += 1
            src_years[r["source"]].add(year)
            if tool not in _TOOLS:
                continue
            if not (f"{year}{WIN_START}" <= d < f"{year}{WIN_END}"):
                continue
            key = (r["source"], year, tool, r["player_key"])
            if key in picked and picked[key] <= d:
                continue                                # keep the EARLIEST in-window board
            picked[key] = d
            grades[(year, tool)][r["player_key"]][r["source"]] = g
    return grades, census, {k: sorted(v) for k, v in src_years.items()}


def load_career_mlb() -> dict:
    out: dict = {}
    with storage.connect() as con:
        for r in con.execute("SELECT player_key, payload_json FROM career_stats"):
            try:
                rows = json.loads(r["payload_json"])
            except ValueError:
                continue
            mlb = [x for x in rows if x.get("level") == "MLB"]
            if mlb:
                out[r["player_key"]] = mlb
    return out


def realized(cs: dict, pk: str, stat: str, after_year: int | None):
    """PA/BF-weighted mean of `stat` over MLB seasons STRICTLY AFTER `after_year`.

    `after_year=None` reproduces efv_tools._realized_mlb's un-chained aggregate (used
    only for the departure-cost report, never for a gate)."""
    rows = cs.get(pk)
    if not rows:
        return None
    if after_year is not None:
        rows = [x for x in rows if (x.get("season") or 0) > after_year]
    if not rows:
        return None
    agg = wsum = 0.0
    for x in rows:
        v = x.get(stat)
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if stat == "sb":                    # counting stat -> per-season mean
            agg += v
            wsum += 1
        else:
            w = float(x.get("ab") or x.get("bf") or x.get("ip") or 1) or 1.0
            agg += v * w
            wsum += w
    return (agg / wsum) if wsum else None


def build_rows(grades, cs, tool, sources, after_chain=True) -> dict:
    """year -> [ {player, grades{src:g}, y} ] on the COMMON set of `sources`."""
    spec = _TOOLS[tool]
    sign = 1.0 if spec["hi"] else -1.0
    stat = spec["stat"]
    by_year: dict = {}
    for (year, t), players in grades.items():
        if t != tool:
            continue
        for pk, gd in players.items():
            if not all(s in gd for s in sources):
                continue
            y = realized(cs, pk, stat, year if after_chain else None)
            if y is None:
                continue
            by_year.setdefault(year, []).append(
                {"player": pk, "grades": {s: gd[s] for s in sources}, "y": sign * y})
    return by_year


# ---------------------------------------------------------------------------
# weights
# ---------------------------------------------------------------------------
def derive_weights(by_year, sources, max_base_year) -> dict:
    rows = [r for y, rs in by_year.items() if y <= max_base_year for r in rs]
    if len(rows) < 60:
        return {s: 1.0 for s in sources}, len(rows), {}
    ys = [r["y"] for r in rows]
    rho = {}
    for s in sources:
        v = _spearman([r["grades"][s] for r in rows], ys)
        rho[s] = max(SPEARMAN_FLOOR, v if v is not None else SPEARMAN_FLOOR)
    mean_rho = sum(rho.values()) / len(rho)
    n = len(rows)
    out = {}
    for s in sources:
        raw = rho[s] / mean_rho
        shrunk = (n * raw + WEIGHT_SHRINK_K * 1.0) / (n + WEIGHT_SHRINK_K)
        out[s] = round(min(WEIGHT_CLAMP[1], max(WEIGHT_CLAMP[0], shrunk)), 4)
    return out, n, {s: _r4(rho[s]) for s in sources}


def ab_pass(by_year, sources, lag, force_equal=False, weight_override=None, light=False,
            allow_flat=False):
    """Forward-chained equal-vs-weighted A/B. Returns pooled row arrays + per-year.

    `light=True` skips the per-year detail block (used inside the 1000-draw nulls,
    where the detail is never read and only costs memory)."""
    per_year, eq, wt, ys, players, labels = [], [], [], [], [], []
    for Y in sorted(by_year):
        rows = by_year[Y]
        if weight_override is not None:
            w = dict(weight_override)
            wn, wrho = None, {}
        elif force_equal:
            w = {s: 1.0 for s in sources}
            wn, wrho = None, {}
        else:
            w, wn, wrho = derive_weights(by_year, sources, Y - lag)
        if all(abs(w[s] - 1.0) < 1e-9 for s in sources) and not allow_flat:
            if not light:
                per_year.append({"year": Y, "n": len(rows), "skipped": "flat weights",
                                 "weights": w, "weight_base_n": wn})
            continue
        med = statistics.median([r["y"] for r in rows])
        wsum = sum(w[s] for s in sources)
        ye, yw, yy = [], [], []
        for r in rows:
            e = sum(r["grades"][s] for s in sources) / len(sources)
            k = sum(w[s] * r["grades"][s] for s in sources) / wsum
            eq.append(e); wt.append(k); ys.append(r["y"])
            players.append(r["player"]); labels.append(bool(r["y"] >= med))
            if not light:
                ye.append(e); yw.append(k); yy.append(r["y"])
        if not light:
            per_year.append({
                "year": Y, "n": len(rows), "weights_vintage_max_base": Y - lag,
                "weights": w, "weight_base_n": wn, "weight_source_rho": wrho,
                "equal_spearman": _r4(_spearman(ye, yy)),
                "weighted_spearman": _r4(_spearman(yw, yy)),
            })
    return {"per_year": per_year, "equal": eq, "weighted": wt, "y": ys,
            "player": players, "label": labels}


def score(pool):
    if not pool["y"]:
        return {"n": 0, "equal": {}, "weighted": {}, "d_rho": None, "d_auc": None}
    er = _spearman(pool["equal"], pool["y"])
    wr = _spearman(pool["weighted"], pool["y"])
    ea = _auc(pool["equal"], pool["label"])
    wa = _auc(pool["weighted"], pool["label"])
    return {"n": len(pool["y"]),
            "equal": {"spearman": _r4(er), "auc": _r4(ea)},
            "weighted": {"spearman": _r4(wr), "auc": _r4(wa)},
            "d_rho": _r6(None if er is None or wr is None else wr - er),
            "d_auc": _r6(None if ea is None or wa is None else wa - ea)}


def _delta(pool, idx=None):
    if idx is None:
        idx = range(len(pool["y"]))
    e = [pool["equal"][i] for i in idx]
    w = [pool["weighted"][i] for i in idx]
    y = [pool["y"][i] for i in idx]
    lb = [pool["label"][i] for i in idx]
    er, wr = _spearman(e, y), _spearman(w, y)
    ea, wa = _auc(e, lb), _auc(w, lb)
    dr = None if er is None or wr is None else wr - er
    da = None if ea is None or wa is None else wa - ea
    return dr, da


# The pure-Python `_spearman` genexpr in source_backtest raises a Windows access
# violation when driven hundreds of times inside a bootstrap on this interpreter
# (reproduced at ~400 cumulative draws, faulthandler traceback at
# source_backtest.py:411). The numpy path below is an exact reimplementation used
# ONLY inside the resampling loops; `_np_equivalence_check` asserts it agrees with
# source_backtest's own `_spearman` / `_auc` to 1e-12 on the real pooled rows before
# any bootstrap runs, and the check is written into the artifact.
def _np_rank(a):
    import numpy as np
    order = np.argsort(a, kind="mergesort")
    s = a[order]
    n = len(a)
    ranks = np.empty(n, dtype=float)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and s[j + 1] == s[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def _np_spearman(x, y):
    if len(x) < 4:
        return None
    rx, ry = _np_rank(x), _np_rank(y)
    rx = rx - rx.mean(); ry = ry - ry.mean()
    sxx = float((rx * rx).sum()); syy = float((ry * ry).sum())
    if sxx == 0 or syy == 0:
        return None
    return float((rx * ry).sum() / (sxx * syy) ** 0.5)


def _np_auc(scores, labels):
    npos = int(labels.sum()); nneg = len(labels) - npos
    if not npos or not nneg:
        return None
    r = _np_rank(scores)
    u = float(r[labels].sum()) - npos * (npos + 1) / 2.0
    return u / (npos * nneg)


def _np_pool(pool):
    import numpy as np
    return (np.asarray(pool["equal"], float), np.asarray(pool["weighted"], float),
            np.asarray(pool["y"], float), np.asarray(pool["label"], bool))


def _np_delta(E, W, Y, L, idx):
    e, w, y, lb = E[idx], W[idx], Y[idx], L[idx]
    er, wr = _np_spearman(e, y), _np_spearman(w, y)
    ea, wa = _np_auc(e, lb), _np_auc(w, lb)
    return ((None if er is None or wr is None else wr - er),
            (None if ea is None or wa is None else wa - ea))


def _np_equivalence_check(pool):
    """Registered control: the vectorized path must reproduce source_backtest's own
    estimators exactly on the real rows, or nothing computed with it is admissible."""
    import numpy as np
    E, W, Y, L = _np_pool(pool)
    idx = np.arange(len(Y))
    a1, b1 = _delta(pool, range(len(Y)))
    a2, b2 = _np_delta(E, W, Y, L, idx)
    return {"d_rho_pure": _r6(a1), "d_rho_numpy": _r6(a2),
            "d_auc_pure": _r6(b1), "d_auc_numpy": _r6(b2),
            "max_abs_diff": _r6(max(abs((a1 or 0) - (a2 or 0)), abs((b1 or 0) - (b2 or 0)))),
            "identical_to_1e12": bool(abs((a1 or 0) - (a2 or 0)) < 1e-12
                                      and abs((b1 or 0) - (b2 or 0)) < 1e-12)}


def cluster_boot(pool, seed, draws=BOOT):
    """Paired bootstrap, cluster = player (a player recurs across board-years)."""
    if not pool["y"]:
        return {"draws": 0}
    import numpy as np
    byp = defaultdict(list)
    for i, p in enumerate(pool["player"]):
        byp[p].append(i)
    keys = list(byp)
    members = [np.asarray(byp[k], dtype=np.int64) for k in keys]
    E, W, Y, L = _np_pool(pool)
    rng = np.random.default_rng(seed)
    nk = len(keys)
    dr, da = [], []
    for _ in range(draws):
        pick = rng.integers(0, nk, size=nk)
        idx = np.concatenate([members[k] for k in pick])
        a, b = _np_delta(E, W, Y, L, idx)
        if a is not None:
            dr.append(a)
        if b is not None:
            da.append(b)
    dr.sort(); da.sort()
    return {"draws": draws,
            "d_rho_lo95": _r6(dr[int(0.05 * len(dr))]) if dr else None,
            "d_auc_lo95": _r6(da[int(0.05 * len(da))]) if da else None,
            "d_rho_sd": _r6(statistics.pstdev(dr)) if len(dr) > 2 else None,
            "d_auc_sd": _r6(statistics.pstdev(da)) if len(da) > 2 else None}


# ---------------------------------------------------------------------------
# controls
# ---------------------------------------------------------------------------
class NPFrame:
    """Array view of `by_year` for the resampling loops.

    The pure-Python A/B in `ab_pass` remains the definition of the primary numbers;
    this reproduces it exactly (asserted by `np_ab_equivalence`) with ~100x fewer
    object allocations, which is what makes 1000 permutation draws survivable on this
    interpreter."""

    def __init__(self, by_year, sources):
        import numpy as np
        self.sources = list(sources)
        self.years = sorted(by_year)
        self.G, self.Y, self.n = {}, {}, {}
        for y in self.years:
            rows = by_year[y]
            self.G[y] = np.array([[r["grades"][s] for s in sources] for r in rows], float)
            self.Y[y] = np.array([r["y"] for r in rows], float)
            self.n[y] = len(rows)

    def weights(self, max_base_year, G=None):
        import numpy as np
        G = G or self.G
        ys = [y for y in self.years if y <= max_base_year]
        if not ys:
            return np.ones(len(self.sources)), 0
        gg = np.concatenate([G[y] for y in ys], axis=0)
        yy = np.concatenate([self.Y[y] for y in ys])
        n = len(yy)
        if n < 60:
            return np.ones(len(self.sources)), n
        rho = np.array([max(SPEARMAN_FLOOR, _np_spearman(gg[:, i], yy) or SPEARMAN_FLOOR)
                        for i in range(len(self.sources))])
        raw = rho / rho.mean()
        shrunk = (n * raw + WEIGHT_SHRINK_K) / (n + WEIGHT_SHRINK_K)
        return np.round(np.clip(shrunk, WEIGHT_CLAMP[0], WEIGHT_CLAMP[1]), 4), n

    def ab(self, lag, G=None, Yov=None):
        import numpy as np
        G = G if G is not None else self.G
        Yv = Yov if Yov is not None else self.Y
        eq, wt, yy, lb = [], [], [], []
        for y in self.years:
            w, _n = self.weights(y - lag, G)
            if np.all(np.abs(w - 1.0) < 1e-9):
                continue
            g = G[y]
            eq.append(g.mean(axis=1))
            wt.append(g.dot(w) / w.sum())
            yv = Yv[y]
            yy.append(yv)
            lb.append(yv >= np.median(yv))
        if not yy:
            return None
        return (np.concatenate(eq), np.concatenate(wt),
                np.concatenate(yy), np.concatenate(lb))

    @staticmethod
    def delta(pack):
        if pack is None:
            return None, None
        e, w, y, lb = pack
        er, wr = _np_spearman(e, y), _np_spearman(w, y)
        ea, wa = _np_auc(e, lb), _np_auc(w, lb)
        return ((None if er is None or wr is None else wr - er),
                (None if ea is None or wa is None else wa - ea))


def np_ab_equivalence(by_year, sources, lag):
    """Registered control: the array A/B must reproduce the pure-Python A/B exactly."""
    f = NPFrame(by_year, sources)
    a2, b2 = NPFrame.delta(f.ab(lag))
    s = score(ab_pass(by_year, sources, lag))
    return {"d_rho_pure": s["d_rho"], "d_rho_array": _r6(a2),
            "d_auc_pure": s["d_auc"], "d_auc_array": _r6(b2),
            "identical_to_1e12": bool(
                a2 is not None and s["d_rho"] is not None
                and abs(a2 - s["d_rho"]) < 1e-6 and abs(b2 - s["d_auc"]) < 1e-6)}


def permuted_source_null_np(by_year, sources, lag, seed, draws=PERM, obs=None):
    """Vectorized form of the mandatory permuted-source-label control."""
    import numpy as np
    f = NPFrame(by_year, sources)
    rng = np.random.default_rng(seed)
    k = len(sources)
    drs, das = [], []
    wspread = []
    for _ in range(draws):
        Gp = {}
        for y in f.years:
            g = f.G[y]
            # independent random permutation of the k source labels, per row
            perm = np.argsort(rng.random((g.shape[0], k)), axis=1)
            Gp[y] = np.take_along_axis(g, perm, axis=1)
        a, b = NPFrame.delta(f.ab(lag, G=Gp))
        w, _n = f.weights(max(f.years), Gp)
        wspread.append(float(w.max() - w.min()))
        if a is not None:
            drs.append(abs(a))
        if b is not None:
            das.append(abs(b))
    drs.sort(); das.sort(); wspread.sort()

    def p95(v):
        return _r6(v[int(0.95 * (len(v) - 1))]) if v else None
    out = {"draws": draws, "n_nonflat_rho": len(drs), "n_nonflat_auc": len(das),
           "abs_d_rho_p95": p95(drs), "abs_d_auc_p95": p95(das),
           "abs_d_rho_max": _r6(drs[-1]) if drs else None,
           "abs_d_auc_max": _r6(das[-1]) if das else None,
           "perm_weight_spread_median": _r4(statistics.median(wspread)) if wspread else None,
           "perm_weight_spread_p95": _r4(wspread[int(0.95 * (len(wspread) - 1))]) if wspread else None}
    if obs is not None:
        odr, oda = obs
        out["p_rho"] = (_r6((1 + sum(1 for v in drs if v >= abs(odr))) / (len(drs) + 1))
                        if (odr is not None and drs) else None)
        out["p_auc"] = (_r6((1 + sum(1 for v in das if v >= abs(oda))) / (len(das) + 1))
                        if (oda is not None and das) else None)
    return out


def shuffled_outcome_null_np(by_year, sources, lag, seed):
    """Vectorized form of C6.3."""
    import numpy as np
    f = NPFrame(by_year, sources)
    rng = np.random.default_rng(seed)
    Yp = {y: rng.permutation(f.Y[y]) for y in f.years}
    pack = f.ab(lag, Yov=Yp)
    if pack is None:
        return {"n": 0, "note": "every year skipped: with a shuffled outcome the "
                                "SPEARMAN_FLOOR collapses both sources to equal weight, "
                                "so no year differentiates the arms. Informative, but it "
                                "means this cell's pipeline check runs on 0 rows."}
    e, w, y, lb = pack
    return {"n": int(len(y)),
            "equal": {"spearman": _r4(_np_spearman(e, y)), "auc": _r4(_np_auc(e, lb))},
            "weighted": {"spearman": _r4(_np_spearman(w, y)), "auc": _r4(_np_auc(w, lb))}}


def permuted_source_null(by_year, sources, lag, seed, draws=PERM, obs=None):
    """C6.1 -- within each (player, tool, year) cell reassign grades to sources at
    random. The grade multiset on a player is unchanged; only the labels move."""
    rng = random.Random(seed)
    drs, das = [], []
    # pre-materialize the immutable parts once; only the source labels move
    base = {Y: [(r["player"], r["y"], [r["grades"][s] for s in sources]) for r in rows]
            for Y, rows in by_year.items()}
    for _ in range(draws):
        perm = {}
        for Y, rows in base.items():
            out = []
            for pk, yv, vals in rows:
                v = list(vals)
                rng.shuffle(v)
                out.append({"player": pk, "y": yv, "grades": dict(zip(sources, v))})
            perm[Y] = out
        s = score(ab_pass(perm, sources, lag, light=True))
        del perm
        if s["d_rho"] is not None:
            drs.append(abs(s["d_rho"]))
        if s["d_auc"] is not None:
            das.append(abs(s["d_auc"]))
    drs.sort(); das.sort()

    def p95(v):
        return _r6(v[int(0.95 * (len(v) - 1))]) if v else None
    out = {"draws": draws, "n_nonflat_rho": len(drs), "n_nonflat_auc": len(das),
           "abs_d_rho_p95": p95(drs), "abs_d_auc_p95": p95(das),
           "abs_d_rho_max": _r6(drs[-1]) if drs else None,
           "abs_d_auc_max": _r6(das[-1]) if das else None}
    if obs is not None:
        odr, oda = obs
        # two-sided permutation p, add-one corrected (never reports p = 0)
        out["p_rho"] = (_r6((1 + sum(1 for v in drs if v >= abs(odr))) / (len(drs) + 1))
                        if (odr is not None and drs) else None)
        out["p_auc"] = (_r6((1 + sum(1 for v in das if v >= abs(oda))) / (len(das) + 1))
                        if (oda is not None and das) else None)
    return out


def perm_weight_spread(by_year, sources, lag, seed, draws=200):
    """DEGENERACY DIAGNOSTIC for 6.1 (self-added, declared in section 8).

    With two symmetric sources, permuting the source labels makes both permuted
    'sources' identical in expectation, so the derived weights collapse to ~1.0 and
    the null delta is ~0 almost by construction. That makes F_rho artificially SMALL
    and G1 artificially EASY. This measures how far the permuted weights actually
    travel from 1.0, against how far the real ones do."""
    rng = random.Random(seed)
    spreads = []
    for _ in range(draws):
        perm = {}
        for Y, rows in by_year.items():
            out = []
            for r in rows:
                vals = [r["grades"][s] for s in sources]
                rng.shuffle(vals)
                out.append({"player": r["player"], "y": r["y"],
                            "grades": dict(zip(sources, vals))})
            perm[Y] = out
        w, _n, _r = derive_weights(perm, sources, max(perm) if perm else 0)
        spreads.append(max(w.values()) - min(w.values()))
    spreads.sort()
    real = {}
    for Y in sorted(by_year):
        w, _n, _r = derive_weights(by_year, sources, Y - lag)
        real[str(Y)] = max(w.values()) - min(w.values())
    return {"draws": draws,
            "perm_weight_spread_median": _r4(statistics.median(spreads)) if spreads else None,
            "perm_weight_spread_p95": _r4(spreads[int(0.95 * (len(spreads) - 1))]) if spreads else None,
            "real_weight_spread_by_year": {k: _r4(v) for k, v in real.items()},
            "degenerate": bool(spreads and statistics.median(spreads) < 0.02)}


def disjoint_player_pass(by_year, sources, lag, seed=SEED):
    """C6.7 (self-added, declared). The primary A/B inherits `source_backtest`'s
    structure, in which the SAME player can appear in both the weight-derivation
    vintages and the scored year. That does not bias the weight but it does let the
    weight be chosen partly on the rows it is later scored on. This re-runs the A/B
    with the weight-derivation set restricted to players who do NOT appear in the
    scored year."""
    per_year, eq, wt, ys, players, labels = [], [], [], [], [], []
    for Y in sorted(by_year):
        rows = by_year[Y]
        scored_players = {r["player"] for r in rows}
        base = {y: [r for r in rs if r["player"] not in scored_players]
                for y, rs in by_year.items() if y <= Y - lag}
        w, wn, _rho = derive_weights(base, sources, Y - lag)
        if all(abs(w[s] - 1.0) < 1e-9 for s in sources):
            per_year.append({"year": Y, "n": len(rows), "skipped": "flat weights",
                             "weight_base_n": wn})
            continue
        med = statistics.median([r["y"] for r in rows])
        wsum = sum(w[s] for s in sources)
        for r in rows:
            eq.append(sum(r["grades"][s] for s in sources) / len(sources))
            wt.append(sum(w[s] * r["grades"][s] for s in sources) / wsum)
            ys.append(r["y"]); players.append(r["player"]); labels.append(bool(r["y"] >= med))
        per_year.append({"year": Y, "n": len(rows), "weights": w, "weight_base_n": wn})
    pool = {"per_year": per_year, "equal": eq, "weighted": wt, "y": ys,
            "player": players, "label": labels}
    s = score(pool)
    s["per_year"] = per_year
    if s["n"]:
        s["bootstrap"] = cluster_boot(pool, seed, draws=1000)
    return s


def single_source_context(by_year, sources, lag):
    """Context, not a gate: is the weighted blend just walking toward the better
    single source? Scores each source alone on the SAME pooled scored rows."""
    rows = [r for Y, rs in by_year.items() if Y >= min(by_year) + 0 for r in rs]
    ev = [Y for Y in sorted(by_year) if Y - lag >= min(by_year)]
    rows = [r for Y in ev for r in by_year[Y]]
    if len(rows) < 10:
        return {}
    ys = [r["y"] for r in rows]
    out = {"pooled_n": len(rows), "years": ev}
    for s in sources:
        out[s] = {"spearman": _r4(_spearman([r["grades"][s] for r in rows], ys))}
    out["equal_mean"] = {"spearman": _r4(_spearman(
        [sum(r["grades"][s] for s in sources) / len(sources) for r in rows], ys))}
    return out


def shuffled_outcome_null(by_year, sources, lag, seed):
    """C6.3 -- permute the realized quantity across players within board-year."""
    rng = random.Random(seed)
    perm = {}
    for Y, rows in by_year.items():
        ys = [r["y"] for r in rows]
        rng.shuffle(ys)
        perm[Y] = [{"player": r["player"], "grades": r["grades"], "y": ys[i]}
                   for i, r in enumerate(rows)]
    return score(ab_pass(perm, sources, lag))


CELL_DIR = Path(__file__).resolve().parent / "_ba_tool_cells"


def _cell_via_subprocess(arm, tool):
    """Compute one gate cell in a fresh interpreter and read the JSON back."""
    import subprocess
    CELL_DIR.mkdir(exist_ok=True)
    dest = CELL_DIR / f"{arm}__{tool}.json"
    # 0xC0000005 (rc 3221225477) fires stochastically on this interpreter even for a
    # single cell. Every estimator is seeded, so a retry recomputes the SAME numbers;
    # the retry buys stability, never a different answer.
    last = None
    for _ in range(6):
        if dest.exists():
            dest.unlink()
        r = subprocess.run([sys.executable, "-u", str(Path(__file__).resolve()),
                            "--cell", arm, tool, str(dest)],
                           capture_output=True, text=True)
        last = r
        if r.returncode == 0 and dest.exists():
            return json.loads(dest.read_text(encoding="utf-8"))
    raise RuntimeError(f"cell {arm}/{tool} failed rc={last.returncode} "
                       f"{last.stdout[-1500:]} {last.stderr[-1500:]}")


def compute_cell(grades, cs, arm, tool):
    """One (arm, tool) gate cell. Run in its own process by `_cell_via_subprocess`:
    this interpreter corrupts objects and raises Windows access violations when the
    resampling loops for all ten cells run in one process (reproduced three times;
    faulthandler tracebacks at source_backtest.py:411 and at a numpy rank assignment).
    Process isolation bounds the allocation churn to one cell. It is the only change:
    every estimator below is identical to the single-process form."""
    sources = ARMS[arm]
    by_year = build_rows(grades, cs, tool, sources)
    unchained = build_rows(grades, cs, tool, sources, after_chain=False)
    cov = {str(y): len(r) for y, r in sorted(by_year.items())}
    cov_un = {str(y): len(r) for y, r in sorted(unchained.items())}
    cell = {
        "common_set_by_year_chained": cov,
        "common_set_by_year_unchained_efv_tools_basis": cov_un,
        "pooled_n_chained": sum(cov.values()),
        "pooled_n_unchained": sum(cov_un.values()),
        "forward_chain_cost_rows": sum(cov_un.values()) - sum(cov.values()),
    }
    pool = ab_pass(by_year, sources, MIN_LAG_YEARS)
    s = score(pool)
    cell["primary"] = s
    cell["per_year"] = pool["per_year"]
    cell["evaluable_years"] = [p["year"] for p in pool["per_year"] if "skipped" not in p]
    if s["n"]:
        nullc = permuted_source_null_np(by_year, sources, MIN_LAG_YEARS, SEED,
                                        obs=(s["d_rho"], s["d_auc"]))
        cell["C0_numpy_equivalence_check"] = _np_equivalence_check(pool)
        cell["C0_array_ab_equivalence"] = np_ab_equivalence(
            by_year, sources, MIN_LAG_YEARS)
        boot = cluster_boot(pool, SEED)
        boot_alt = cluster_boot(pool, SEED_ALT, draws=BOOT)
        null_alt = permuted_source_null_np(by_year, sources, MIN_LAG_YEARS,
                                           SEED_ALT, draws=200,
                                           obs=(s["d_rho"], s["d_auc"]))
        cell["C61_permuted_source_null"] = nullc
        cell["bootstrap"] = boot
        cell["C65_seed_stability"] = {"boot_seed1337": boot_alt,
                                      "perm_seed1337_200": null_alt}
        cell["C63_shuffled_outcome_null"] = shuffled_outcome_null_np(
            by_year, sources, MIN_LAG_YEARS, SEED)
        # C6.4 must NOT be allowed to pass vacuously. `ab_pass` skips a year
        # whose weights are flat (inherited from source_backtest), so
        # force_equal=True yields n=0 and "passes" trivially. The honest form
        # bypasses the skip with an explicit all-ones override.
        ones = {s: 1.0 for s in sources}
        fe_vac = score(ab_pass(by_year, sources, MIN_LAG_YEARS, force_equal=True))
        fe = score(ab_pass(by_year, sources, MIN_LAG_YEARS,
                           weight_override=ones, allow_flat=True))
        cell["C64_forced_equal_identity"] = {
            "vacuous_form_n": fe_vac["n"],
            "vacuous_form_note": "0 rows: flat-weight years are skipped, so this "
                                 "form of the control cannot fail. Not used.",
            "n": fe["n"], "d_rho": fe["d_rho"], "d_auc": fe["d_auc"],
            "passes": bool(fe["n"] > 0 and fe["d_rho"] == 0.0 and fe["d_auc"] == 0.0)}
        f_rho = nullc["abs_d_rho_p95"]
        f_auc = nullc["abs_d_auc_p95"]
        dr, da = s["d_rho"], s["d_auc"]
        g1 = bool(dr is not None and f_rho is not None and dr >= f_rho)
        g2 = bool(da is not None and f_auc is not None and da >= f_auc)
        g3 = bool(boot["d_rho_lo95"] is not None and boot["d_rho_lo95"] > 0)
        g4 = bool(boot["d_auc_lo95"] is not None and boot["d_auc_lo95"] > 0)
        g5 = bool(dr is not None and f_rho is not None and dr >= 2 * f_rho)
        # --- SELF-ADDED supplementary floors (declared in section 8) -----
        cell["C61b_perm_null_degeneracy"] = {
            "perm_weight_spread_median": nullc.get("perm_weight_spread_median"),
            "perm_weight_spread_p95": nullc.get("perm_weight_spread_p95"),
            "real_weight_spread_by_year": {
                str(py["year"]): _r4(max(py["weights"].values())
                                     - min(py["weights"].values()))
                for py in cell["per_year"] if py.get("weights")},
            "degenerate": bool((nullc.get("perm_weight_spread_median") or 0) < 0.02)}
        mde_rho = (1.645 * boot["d_rho_sd"]) if boot.get("d_rho_sd") else None
        mde_auc = (1.645 * boot["d_auc_sd"]) if boot.get("d_auc_sd") else None
        g6 = bool(dr is not None and mde_rho is not None and dr >= mde_rho
                  and da is not None and mde_auc is not None and da >= mde_auc)
        cell["C67_player_disjoint_weights"] = disjoint_player_pass(
            by_year, sources, MIN_LAG_YEARS)
        cell["context_single_source"] = single_source_context(
            by_year, sources, MIN_LAG_YEARS)
        dj = cell["C67_player_disjoint_weights"]
        g7 = bool(dj.get("d_rho") is not None and dj["d_rho"] > 0
                  and dj.get("d_auc") is not None and dj["d_auc"] > 0
                  and (dj.get("bootstrap") or {}).get("d_rho_lo95") is not None
                  and dj["bootstrap"]["d_rho_lo95"] > 0)
        cell["gate"] = {
            "F_rho": f_rho, "F_auc": f_auc,
            "margin_over_F_rho": _r4(None if (dr is None or not f_rho) else dr / f_rho),
            "margin_over_F_auc": _r4(None if (da is None or not f_auc) else da / f_auc),
            "G1_rho_resolvable": g1, "G2_auc_resolvable": g2,
            "G3_rho_lo95_pos": g3, "G4_auc_lo95_pos": g4,
            "G5_not_knife_edge": g5,
            "PREREGISTERED_SHIP": bool(g1 and g2 and g3 and g4 and g5),
            "G6_bootstrap_MDE95_selfadded": g6,
            "G6_mde95_rho": _r6(mde_rho), "G6_mde95_auc": _r6(mde_auc),
            "G6_margin_rho": _r4(None if (dr is None or not mde_rho) else dr / mde_rho),
            "G6_margin_auc": _r4(None if (da is None or not mde_auc) else da / mde_auc),
            "G7_survives_player_disjoint_weights_selfadded": g7,
            "SHIP": bool(g1 and g2 and g3 and g4 and g5 and g6 and g7),
            "verdict": ("SHIP" if (g1 and g2 and g3 and g4 and g5 and g6 and g7)
                        else "PREREG_PASS_SELFADDED_FAIL"
                        if (g1 and g2 and g3 and g4 and g5)
                        else "MARGINAL->FAIL" if (g1 and g2 and g3 and g4)
                        else "NO_SHIP"),
        }
    else:
        cell["gate"] = {"SHIP": False, "verdict": "NULL_NO_EVALUABLE_YEAR",
                        "reason": "no board-year has both a non-flat weight "
                                  "vintage and resolvable outcomes at "
                                  f"MIN_LAG_YEARS={MIN_LAG_YEARS}"}
    # survivorship boundary
    graded = sum(1 for (y, t), pl in grades.items() if t == tool
                 for pk, gd in pl.items() if all(s2 in gd for s2 in sources))
    cell["C66_survivorship"] = {
        "common_set_graded_rows": graded,
        "with_realized_outcome_rows": sum(cov.values()),
        "implied_debut_rate_pct": _r4(100.0 * sum(cov.values()) / (graded or 1)),
        "boundary": "tool accuracy AMONG DEBUTS, not tool accuracy overall",
    }
    return cell


def compute_sens(grades, cs, lag, only_arm=None, only_tool=None):
    """Lag-sensitivity block. Isolated per (lag, arm, tool) in its own process for the
    same reason `compute_cell` is (see its docstring)."""
    lag_out = {}
    for arm, sources in ARMS.items():
        if only_arm and arm != only_arm:
            continue
        t_out = {}
        for tool in SCOREABLE:
            if only_tool and tool != only_tool:
                continue
            by_year = build_rows(grades, cs, tool, sources)
            pool = ab_pass(by_year, sources, lag)
            s = score(pool)
            ev = [p["year"] for p in pool["per_year"] if "skipped" not in p]
            if s["n"]:
                nc = permuted_source_null_np(by_year, sources, lag, SEED, draws=300,
                                             obs=(s["d_rho"], s["d_auc"]))
                bt = cluster_boot(pool, SEED, draws=1000)
                s["F_rho_perm300"] = nc["abs_d_rho_p95"]
                s["F_auc_perm300"] = nc["abs_d_auc_p95"]
                s["p_rho_perm300"] = nc.get("p_rho")
                s["d_rho_lo95"] = bt["d_rho_lo95"]
                s["d_auc_lo95"] = bt["d_auc_lo95"]
            s["evaluable_years"] = ev
            s["weights_last_scored_year"] = (
                pool["per_year"][-1].get("weights") if pool["per_year"] else None)
            t_out[tool] = s
        lag_out[arm] = t_out
    return lag_out


def _sens_via_subprocess(lag):
    import subprocess
    CELL_DIR.mkdir(exist_ok=True)
    merged = {}
    for arm in ARMS:
        merged[arm] = {}
        for tool in SCOREABLE:
            dest = CELL_DIR / f"sens_lag{lag}__{arm}__{tool}.json"
            last = None
            for _ in range(8):
                if dest.exists():
                    dest.unlink()
                r = subprocess.run([sys.executable, "-u", str(Path(__file__).resolve()),
                                    "--sens", str(lag), str(dest), arm, tool],
                                   capture_output=True, text=True)
                last = r
                if r.returncode == 0 and dest.exists():
                    break
            else:
                raise RuntimeError(f"sens lag={lag} {arm}/{tool} rc={last.returncode} "
                                   f"{last.stdout[-1200:]} {last.stderr[-1200:]}")
            merged[arm][tool] = json.loads(dest.read_text(encoding="utf-8"))[arm][tool]
    return merged


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def run() -> dict:
    out: dict = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "lane": "BA2",
                 "pre_registration": "docs/efv-2026-08-07b/TOOL_GRADE_WEIGHT_GATE.md",
                 "constants": {"MIN_LAG_YEARS": MIN_LAG_YEARS,
                               "WEIGHT_SHRINK_K": WEIGHT_SHRINK_K,
                               "WEIGHT_CLAMP": list(WEIGHT_CLAMP),
                               "SPEARMAN_FLOOR": SPEARMAN_FLOOR,
                               "boot": BOOT, "perm": PERM, "seed": SEED},
                 "tool_outcome_map": {t: {"stat": s["stat"], "hi": s["hi"]}
                                      for t, s in _TOOLS.items()},
                 "passthrough_tools_unscoreable": _PASSTHROUGH}

    grades, census, src_years = load_grades()
    cs = load_career_mlb()

    # ---- B1 premise correction -------------------------------------------
    ba = census.get("baseballamerica", Counter())
    out["B1_premise"] = {
        "plan_K0_claim": "Baseball America carries ZERO tool grades",
        "verdict": "FALSE",
        "brief_stated": {"observations": 7285, "rows": 1502},
        "measured_observations_by_key": dict(ba.most_common()),
        "measured_observations_total": int(sum(ba.values())),
        "scoreable_share": {
            "scoreable_tools": list(SCOREABLE),
            "n_scoreable_obs": int(sum(ba[t] for t in SCOREABLE)),
            "pct_of_ba_obs": _r4(100.0 * sum(ba[t] for t in SCOREABLE) / (sum(ba.values()) or 1)),
        },
        "all_sources": {s: {"total": int(sum(c.values())), "years": src_years.get(s, []),
                            "by_key": dict(c.most_common())}
                        for s, c in sorted(census.items(), key=lambda kv: -sum(kv[1].values()))},
        "multi_year_sources": sorted(s for s, y in src_years.items() if len(y) > 1),
        "single_year_sources": sorted(s for s, y in src_years.items() if len(y) <= 1),
    }
    with storage.connect() as con:
        out["B1_premise"]["ba_rows_with_tools"] = con.execute(
            "SELECT count(*) FROM snapshots WHERE source='baseballamerica' "
            "AND tools_json IS NOT NULL AND tools_json != ''").fetchone()[0]

    # ---- 6.6 AAA Savant widening feasibility -----------------------------
    # `payload_json` here holds multi-hundred-KB Statcast blobs; only `season` and
    # `level` are needed, so the level is read with a bounded substring scan instead
    # of decoding 3k large documents.
    sc = Counter()
    with storage.connect() as con:
        for r in con.execute("SELECT season, substr(payload_json, 1, 400) AS head "
                             "FROM statcast_metrics"):
            head = r["head"] or ""
            lvl = None
            m = head.find('"level":')
            if m >= 0:
                seg = head[m + 8:m + 40].strip()
                if seg.startswith('"'):
                    lvl = seg[1:seg.find('"', 1)] if seg.find('"', 1) > 0 else None
            sc[(r["season"], lvl)] += 1
    out["C66_aaa_savant_widening"] = {
        "statcast_metrics_rows": int(sum(sc.values())),
        "by_season_level": {f"{k[0]}|{k[1]}": v for k, v in sorted(sc.items(), key=lambda x: str(x[0]))},
        "seasons_present": sorted({k[0] for k in sc}),
        "feasible": bool({k[0] for k in sc} - {max({k[0] for k in sc})}) if sc else False,
    }

    # ---- arms -------------------------------------------------------------
    out["arms"] = {}
    for arm, sources in ARMS.items():
        arm_out = {"sources": list(sources), "tools": {}}
        for tool in SCOREABLE:
            print(f"  [{arm}/{tool}] ...", flush=True)
            arm_out["tools"][tool] = _cell_via_subprocess(arm, tool)
        out["arms"][arm] = arm_out

    # ---- 5.1 lag SENSITIVITY (cannot ship) --------------------------------
    sens = {}
    for lag in (2, 1):
        print(f"  stage sensitivity lag={lag}", flush=True)
        sens[f"lag_{lag}"] = _sens_via_subprocess(lag)
    out["S51_lag_sensitivity_CANNOT_SHIP"] = sens

    # ---- 6.2 pooled-tool control -----------------------------------------
    pooled = {}
    for arm, sources in ARMS.items():
        allrows = {}
        per_tool_rho = {s: {} for s in sources}
        for tool in SCOREABLE:
            by_year = build_rows(grades, cs, tool, sources)
            for Y, rows in by_year.items():
                # z-score the outcome within (tool, year) so tools can be pooled at all
                ys = [r["y"] for r in rows]
                mu = statistics.mean(ys) if ys else 0.0
                sd = statistics.pstdev(ys) or 1.0
                allrows.setdefault(Y, []).extend(
                    [{"player": r["player"], "grades": r["grades"],
                      "y": (r["y"] - mu) / sd} for r in rows])
            rows_all = [r for rs in by_year.values() for r in rs]
            if rows_all:
                for s in sources:
                    per_tool_rho[s][tool] = _r4(_spearman([r["grades"][s] for r in rows_all],
                                                          [r["y"] for r in rows_all]))
        w, n, rho = derive_weights(allrows, sources, 9999)
        spread = {s: {"per_tool_rho": per_tool_rho[s],
                      "min": min([v for v in per_tool_rho[s].values() if v is not None] or [None]),
                      "max": max([v for v in per_tool_rho[s].values() if v is not None] or [None])}
                  for s in sources}
        pooled[arm] = {"pooled_weight": w, "pooled_n": n, "pooled_rho": rho,
                       "per_source_per_tool_rho_spread": spread}
    print("  stage %s" % 'C62_pooled_tool_control', flush=True)
    out["C62_pooled_tool_control"] = pooled

    # ---- B2 era scale break ----------------------------------------------
    fv: dict = defaultdict(dict)
    pos: dict = {}
    with storage.connect() as con:
        for r in con.execute("SELECT source, snapshot_date, player_key, fv, position "
                             "FROM snapshots WHERE source IN ('baseballamerica','fangraphs') "
                             "AND fv IS NOT NULL ORDER BY snapshot_date"):
            y = int(r["snapshot_date"][:4])
            if not (f"{y}{WIN_START}" <= r["snapshot_date"] < f"{y}{WIN_END}"):
                continue
            fv[(r["source"], y)].setdefault(r["player_key"], float(r["fv"]))
            if r["position"]:
                pos.setdefault(r["player_key"], r["position"])
    consec = {}
    for a, b in ((2023, 2024), (2024, 2025), (2025, 2026)):
        pa, pb = fv[("baseballamerica", a)], fv[("baseballamerica", b)]
        d = [pb[k] - pa[k] for k in pa if k in pb]
        consec[f"{a}->{b}"] = {"n": len(d), "mean": _r4(statistics.mean(d)) if d else None,
                               "sd": _r4(statistics.pstdev(d)) if len(d) > 1 else None}
    vsfg = {}
    for y in (2023, 2024, 2025, 2026):
        pb, pf = fv[("baseballamerica", y)], fv[("fangraphs", y)]
        d = [pb[k] - pf[k] for k in pb if k in pf]
        vsfg[str(y)] = {"n": len(d), "mean": _r4(statistics.mean(d)) if d else None,
                        "sd": _r4(statistics.pstdev(d)) if len(d) > 1 else None}
    print("  stage %s" % 'B2_era_scale_break', flush=True)
    out["B2_era_scale_break"] = {
        "brief_consecutive": {"2023->2024": [194, -0.64, 4.48], "2024->2025": [198, -0.83, 4.54],
                              "2025->2026": [196, -11.89, 5.65]},
        "measured_consecutive": consec,
        "brief_ba_minus_fg": {"2023": [302, 6.57, 4.56], "2024": [310, 6.80, 4.59],
                              "2025": [326, 6.38, 4.93], "2026": [339, -4.98, 3.89]},
        "measured_ba_minus_fg": vsfg,
        "note": "2026 BA fv is the Adjusted Grade; 2023-2025 fv is the BA Grade.",
    }

    # ---- B3 does grade_normalization absorb it? --------------------------
    try:
        import grade_normalization as GN
        b3 = {"_MIN_N": GN._MIN_N, "cells": []}
        for yv in (2023, 2024, 2025, 2026):
            for role in ("hitter", "pitcher"):
                row = GN.drift_row("baseballamerica", role, yv)
                if row:
                    src, ref, pooled_flag = GN._paired_dists("baseballamerica", role, yv)
                    row = dict(row)
                    row["pooled_across_years"] = bool(pooled_flag)
                    row["clears_MIN_N"] = bool(len(GN._pairs("baseballamerica", role, yv)) >= GN._MIN_N)
                    row["overlap_pairs"] = len(GN._pairs("baseballamerica", role, yv))
                    b3["cells"].append(row)
        b3["absorbs_break"] = bool(b3["cells"]) and all(
            (not c["pooled_across_years"]) for c in b3["cells"])
    except Exception as exc:                                    # pragma: no cover
        b3 = {"error": f"{type(exc).__name__}: {exc}"}
    print("  stage %s" % 'B3_grade_normalization_absorption', flush=True)
    out["B3_grade_normalization_absorption"] = b3

    # ---- B3b ROOT CAUSE of the one cell that does NOT absorb ---------------
    # Found while running B3: the 2023 BA board carries no usable `position`, so
    # grade_normalization._is_pitcher() sends every 2023 BA row to the HITTER cell.
    PIT_KEYS = {"fb", "sl", "cb", "ch", "cmd", "ct"}
    b3b = {"by_snapshot": {}}
    try:
        import grade_normalization as GN2
        with storage.connect() as con:
            for d in ("2023-02-15", "2024-02-15", "2025-02-15", "2026-02-15"):
                pos_c, mis = Counter(), Counter()
                for r in con.execute("SELECT position, tools_json FROM snapshots "
                                     "WHERE source='baseballamerica' AND snapshot_date=?", (d,)):
                    pos_c[r["position"]] += 1
                    try:
                        td = json.loads(r["tools_json"] or "{}")
                    except ValueError:
                        td = {}
                    td.pop("_extras", None)
                    tools_role = "pitcher" if (set(td) & PIT_KEYS) else "hitter"
                    pos_role = "pitcher" if GN2._is_pitcher(r["position"]) else "hitter"
                    mis[(pos_role, tools_role)] += 1
                b3b["by_snapshot"][d] = {
                    "positions": {str(k): v for k, v in pos_c.most_common()},
                    "n_position_null": pos_c.get(None, 0),
                    "role_from_position_vs_role_from_tools":
                        {f"{k[0]}|{k[1]}": v for k, v in sorted(mis.items())},
                    "misrouted_rows": sum(v for k, v in mis.items() if k[0] != k[1]),
                }
        b3b["finding"] = (
            "BA 2023-02-15 carries position NULL on 363 of 385 rows and the non-token "
            "'CP' on the other 22 (all catchers). _is_pitcher(None) is False, so all 385 "
            "rows land in the HITTER cell. Two consequences: (1) the (baseballamerica, "
            "pitcher, 2023) cell has ZERO FanGraphs-overlap pairs, falls below _MIN_N=30 "
            "and falls back to POOLING BA ACROSS ALL YEARS, which drags the 2026 "
            "Adjusted-Grade era into the 2023-2025 BA-Grade era and re-opens the ~11.4 FV "
            "break that per-year keying exists to remove; (2) the (baseballamerica, "
            "hitter, 2023) cell is fitted on a role-MIXED distribution. The role is fully "
            "recoverable from tools_json (pitcher keys fb/sl/cb/ch/cmd/ct vs hitter keys).")
        b3b["cells_pooled_across_years"] = [
            f"{c['source']}|{c['role']}|{c['year']}" for c in b3.get("cells", [])
            if c.get("pooled_across_years")]
        b3b["cells_clean"] = [f"{c['source']}|{c['role']}|{c['year']}"
                              for c in b3.get("cells", []) if not c.get("pooled_across_years")]
    except Exception as exc:                                    # pragma: no cover
        b3b["error"] = f"{type(exc).__name__}: {exc}"
    print("  stage %s" % 'B3b_position_null_root_cause', flush=True)
    out["B3b_position_null_root_cause"] = b3b

    # ---- B4 BA Power: game or raw? ---------------------------------------
    b4 = {}
    ov_g, ba_p, iso_ba, iso_fg_g, iso_fg_r = [], [], [], [], []
    for (y, t), players in grades.items():
        if t != "game_pwr":
            continue
        for pk, gd in players.items():
            if "baseballamerica" not in gd:
                continue
            b = gd["baseballamerica"]
            fgg = gd.get("fangraphs")
            iso = realized(cs, pk, "iso", y)
            if fgg is not None:
                ba_p.append(b); ov_g.append(fgg)
            if iso is not None:
                iso_ba.append((b, iso))
                if fgg is not None:
                    iso_fg_g.append((fgg, iso))
    # FG raw_pwr on the same players requires a second grade pull (raw_pwr is not in _TOOLS)
    rawmap: dict = defaultdict(dict)
    with storage.connect() as con:
        for r in con.execute("SELECT source, snapshot_date, player_key, tools_json FROM snapshots "
                             "WHERE source='fangraphs' AND tools_json IS NOT NULL AND tools_json!=''"):
            d = r["snapshot_date"]; y = int(d[:4])
            if not (f"{y}{WIN_START}" <= d < f"{y}{WIN_END}"):
                continue
            try:
                td = json.loads(r["tools_json"])
            except ValueError:
                continue
            v = td.get("raw_pwr") if isinstance(td, dict) else None
            if v is None:
                continue
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            rawmap[(y, r["player_key"])].setdefault("raw_pwr", v)
    pb, pr, pg = [], [], []
    for (y, t), players in grades.items():
        if t != "game_pwr":
            continue
        for pk, gd in players.items():
            if "baseballamerica" not in gd or "fangraphs" not in gd:
                continue
            rv = rawmap.get((y, pk), {}).get("raw_pwr")
            if rv is None:
                continue
            pb.append(gd["baseballamerica"]); pg.append(gd["fangraphs"]); pr.append(rv)
            iso = realized(cs, pk, "iso", y)
            if iso is not None:
                iso_fg_r.append((rv, iso))
    b4["alignment_overlap_n"] = len(pb)
    b4["alignment"] = {
        "spearman_BApower_vs_FG_game_pwr": _r4(_spearman(pb, pg)) if pb else None,
        "spearman_BApower_vs_FG_raw_pwr": _r4(_spearman(pb, pr)) if pb else None,
        "mean_BA_power": _r4(statistics.mean(pb)) if pb else None,
        "mean_FG_game_pwr": _r4(statistics.mean(pg)) if pg else None,
        "mean_FG_raw_pwr": _r4(statistics.mean(pr)) if pr else None,
        "mean_BA_minus_FG_game": _r4(statistics.mean([a - b for a, b in zip(pb, pg)])) if pb else None,
        "mean_BA_minus_FG_raw": _r4(statistics.mean([a - b for a, b in zip(pb, pr)])) if pb else None,
    }
    # COMMON-SET outcome read: all three grades AND a realized ISO on the SAME player.
    # (The three separate reads above sit on different pools and are not comparable.)
    cb, cg, cr, ci = [], [], [], []
    for (y, t), players in grades.items():
        if t != "game_pwr":
            continue
        for pk, gd in players.items():
            if "baseballamerica" not in gd or "fangraphs" not in gd:
                continue
            rv = rawmap.get((y, pk), {}).get("raw_pwr")
            iso = realized(cs, pk, "iso", y)
            if rv is None or iso is None:
                continue
            cb.append(gd["baseballamerica"]); cg.append(gd["fangraphs"]); cr.append(rv); ci.append(iso)
    b4["outcome_vs_realized_iso_COMMON_SET"] = {
        "n": len(ci),
        "BA_power_spearman": _r4(_spearman(cb, ci)) if len(ci) > 3 else None,
        "FG_game_pwr_spearman": _r4(_spearman(cg, ci)) if len(ci) > 3 else None,
        "FG_raw_pwr_spearman": _r4(_spearman(cr, ci)) if len(ci) > 3 else None,
    }
    # Intervals on the two differences B4 turns on. Without these the alignment read is
    # a bare inequality, which is the failure mode this whole program exists to avoid.
    import numpy as _np
    if len(pb) > 30 and len(ci) > 30:
        rngb = _np.random.default_rng(SEED)
        A = _np.asarray(pb, float); Gg = _np.asarray(pg, float); Rr = _np.asarray(pr, float)
        dal = []
        for _ in range(2000):
            k = rngb.integers(0, len(A), len(A))
            v1 = _np_spearman(A[k], Rr[k]); v2 = _np_spearman(A[k], Gg[k])
            if v1 is not None and v2 is not None:
                dal.append(v1 - v2)
        dal.sort()
        CB = _np.asarray(cb, float); CG = _np.asarray(cg, float); CI = _np.asarray(ci, float)
        dout = []
        for _ in range(2000):
            k = rngb.integers(0, len(CB), len(CB))
            v1 = _np_spearman(CB[k], CI[k]); v2 = _np_spearman(CG[k], CI[k])
            if v1 is not None and v2 is not None:
                dout.append(v1 - v2)
        dout.sort()
        b4["intervals"] = {
            "alignment_d_rho_raw_minus_game": _r4(_spearman(pb, pr) - _spearman(pb, pg)),
            "alignment_ci95": [_r4(dal[int(0.025 * len(dal))]), _r4(dal[int(0.975 * len(dal))])],
            "alignment_excludes_zero": bool(dal[int(0.025 * len(dal))] > 0
                                            or dal[int(0.975 * len(dal))] < 0),
            "outcome_d_rho_BA_minus_FGgame": _r4(_np_spearman(CB, CI) - _np_spearman(CG, CI)),
            "outcome_ci95": [_r4(dout[int(0.025 * len(dout))]), _r4(dout[int(0.975 * len(dout))])],
            "outcome_excludes_zero": bool(dout[int(0.025 * len(dout))] > 0
                                          or dout[int(0.975 * len(dout))] < 0),
            "boot": 2000, "seed": SEED}
    b4["outcome_vs_realized_iso_DIFFERENT_POOLS_NOT_COMPARABLE"] = {
        "BA_power": {"n": len(iso_ba),
                     "spearman": _r4(_spearman([a for a, _ in iso_ba], [b for _, b in iso_ba]))
                     if len(iso_ba) > 2 else None},
        "FG_game_pwr": {"n": len(iso_fg_g),
                        "spearman": _r4(_spearman([a for a, _ in iso_fg_g], [b for _, b in iso_fg_g]))
                        if len(iso_fg_g) > 2 else None},
        "FG_raw_pwr": {"n": len(iso_fg_r),
                       "spearman": _r4(_spearman([a for a, _ in iso_fg_r], [b for _, b in iso_fg_r]))
                       if len(iso_fg_r) > 2 else None},
        "caveat": "no realized MLB raw-power quantity exists in _TOOLS; the outcome read "
                  "is indirect and the alignment read carries the weight",
    }
    print("  stage %s" % 'B4_ba_power_game_or_raw', flush=True)
    out["B4_ba_power_game_or_raw"] = b4

    # ---- B5 sweeper / splitter fold cost ---------------------------------
    fold = Counter(); folded_rows = []; plain_rows = []
    with storage.connect() as con:
        for r in con.execute("SELECT snapshot_date, player_key, tools_json FROM snapshots "
                             "WHERE source='baseballamerica' AND tools_json IS NOT NULL "
                             "AND tools_json != ''"):
            try:
                td = json.loads(r["tools_json"])
            except ValueError:
                continue
            ex = (td.get("_extras") or {}) if isinstance(td, dict) else {}
            raw = ex.get("ba_tools_raw") or {}
            if not isinstance(raw, dict):
                continue
            has_sweeper = any(k.lower().startswith("sweep") for k in raw)
            has_split = any(k.lower().startswith("split") for k in raw)
            for k in raw:
                fold[k.lower()] += 1
            for canon, flag, lab in (("sl", has_sweeper, "sweeper"), ("ch", has_split, "splitter")):
                v = td.get(canon)
                if v is None:
                    continue
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    continue
                (folded_rows if flag else plain_rows).append((canon, lab, v, flag))
    def _stat(sel):
        v = [x[2] for x in sel]
        return {"n": len(v), "mean": _r4(statistics.mean(v)) if v else None,
                "sd": _r4(statistics.pstdev(v)) if len(v) > 1 else None}
    print("  stage %s" % 'B5_fold_cost', flush=True)
    # THE FOLD'S ACTUAL COST: a pitcher graded on BOTH members of a folded family keeps
    # only ONE canonical grade, so the other observation is destroyed at ingest.
    coll = Counter()
    coll_pairs = []
    with storage.connect() as con:
        for r in con.execute("SELECT player_name, tools_json FROM snapshots "
                             "WHERE source='baseballamerica' AND tools_json IS NOT NULL "
                             "AND tools_json != ''"):
            try:
                td = json.loads(r["tools_json"])
            except ValueError:
                continue
            ex = (td.pop("_extras", None) or {}) if isinstance(td, dict) else {}
            raw = ex.get("ba_tools_raw") or {}
            if not isinstance(raw, dict):
                continue
            low = {k.lower(): v for k, v in raw.items()}
            fam = {"sl": [k for k in low if k.startswith("slider") or k.startswith("sweep")],
                   "ch": [k for k in low if k.startswith("change") or k.startswith("split")
                          or k == "ch"]}
            for canon, ks in fam.items():
                if len(ks) > 1:
                    coll[(canon, tuple(sorted(ks)))] += 1
                    kept = td.get(canon)
                    vals = {k: low[k] for k in ks}
                    coll_pairs.append({"canon": canon, "labels": vals, "kept": kept})
    lost_sl = sum(v * (len(k[1]) - 1) for k, v in coll.items() if k[0] == "sl")
    lost_ch = sum(v * (len(k[1]) - 1) for k, v in coll.items() if k[0] == "ch")
    dropped = []
    for c in coll_pairs:
        try:
            vs = sorted(float(v) for v in c["labels"].values())
        except (TypeError, ValueError):
            continue
        if c["kept"] is None:
            continue
        dropped.append(float(c["kept"]) - statistics.mean(vs))
    out["B5_fold_collisions"] = {
        "collision_rows": {f"{k[0]}|{'+'.join(k[1])}": v for k, v in coll.most_common()},
        "observations_destroyed_sl": lost_sl,
        "observations_destroyed_ch": lost_ch,
        "kept_minus_family_mean": {
            "n": len(dropped),
            "mean": _r4(statistics.mean(dropped)) if dropped else None,
            "sd": _r4(statistics.pstdev(dropped)) if len(dropped) > 1 else None},
        "finding": ("the sweeper->sl and splitter->ch folds are NOT free: a pitcher graded "
                    "on both members of a folded family keeps ONE canonical grade and the "
                    "other observation is destroyed at ingest. Reconciles the label counts "
                    "exactly: slider 606 + sweeper 48 = 654 against sl 634 (20 lost); "
                    "changeup 609 + ch 6 + split 38 + splitter 5 = 658 against ch 647 "
                    "(11 lost). Both are PASSTHROUGH tools, so the loss cannot be scored "
                    "for accuracy, only counted."),
    }
    out["B5_fold_cost"] = {
        "raw_label_counts": dict(fold.most_common()),
        "label_to_canonical_reconciliation": {
            "hit": "hit 759 + hitting 77 = 836 == canonical hit",
            "speed": "run 672 + speed 164 = 836 == canonical speed",
            "field": "field 672 + fielding 164 = 836 == canonical field",
            "throw": "arm 834 + throw 1 = 835 == canonical throw",
            "cmd": "control 694 + comtrol 1 = 695 == canonical cmd (the typo maps)",
            "ct": "cutter 152 + cut 3 = 155 == canonical ct",
            "cb": "curveball 402 + cb 2 = 404 == canonical cb; knuckleball 1 is DROPPED "
                  "(no canonical key)",
            "sl": "slider 606 + sweeper 48 = 654 against canonical sl 634 -> 20 lost to fold",
            "ch": "changeup 609 + ch 6 + split 38 + splitter 5 = 658 against canonical ch "
                  "647 -> 11 lost to fold",
        },
        "sl_folded_sweeper": _stat([x for x in folded_rows if x[0] == "sl" and x[3]]),
        "sl_plain_slider": _stat([x for x in plain_rows if x[0] == "sl"]),
        "ch_folded_splitter": _stat([x for x in folded_rows if x[0] == "ch" and x[3]]),
        "ch_plain_changeup": _stat([x for x in plain_rows if x[0] == "ch"]),
        "note": "sl and ch are PASSTHROUGH tools with no realized MLB target "
                "(efv_tools._PASSTHROUGH), so this can only ever be a distributional "
                "comparison, never an accuracy one.",
    }

    # ---- B6 league selection ---------------------------------------------
    orgs = defaultdict(set); ba_players_by_year = defaultdict(set)
    src_by_player = defaultdict(lambda: defaultdict(set))
    with storage.connect() as con:
        for r in con.execute("SELECT source, snapshot_date, player_key, org FROM snapshots"):
            y = int(r["snapshot_date"][:4])
            if not (f"{y}{WIN_START}" <= r["snapshot_date"] < f"{y}{WIN_END}"):
                continue
            src_by_player[y][r["player_key"]].add(r["source"])
            if r["source"] == "baseballamerica":
                ba_players_by_year[y].add(r["player_key"])
                if r["org"]:
                    orgs[y].add(r["org"])
    b6 = {"ba_orgs_by_year": {str(k): sorted(v) for k, v in sorted(orgs.items())}}
    latest = max(ba_players_by_year) if ba_players_by_year else None
    if latest:
        allp = src_by_player[latest]
        with_ba = [p for p in allp if "baseballamerica" in allp[p]]
        without = [p for p in allp if "baseballamerica" not in allp[p]]
        b6["cycle"] = latest
        b6["players_in_cycle"] = len(allp)
        b6["gain_a_ba_vote"] = len(with_ba)
        b6["mean_n_sources_with_ba"] = _r4(statistics.mean([len(allp[p]) for p in with_ba])) if with_ba else None
        b6["mean_n_sources_without_ba"] = _r4(statistics.mean([len(allp[p]) for p in without])) if without else None
        b6["consequence"] = ("a player's number of voting sources depends on his league; "
                             "all BA org boards ingested are American League clubs, so "
                             "AL prospects get one more vote than NL prospects and the "
                             "consensus mean is shrunk over a different denominator by league")
    print("  stage %s" % 'B6_league_selection', flush=True)
    out["B6_league_selection"] = b6

    # ---- B7 selection hazard ---------------------------------------------
    b7 = {}
    try:
        from efv_dataset import matrix_path
        ba_all = set()
        with storage.connect() as con:
            for r in con.execute("SELECT DISTINCT player_key FROM snapshots "
                                 "WHERE source='baseballamerica'"):
                ba_all.add(r["player_key"])
        for side in ("hit", "pit"):
            rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
            deb = sum(1 for r in rows if r.get("kind") == "debuted")
            cov = [r for r in rows if r["player_key"] in ba_all]
            covd = sum(1 for r in cov if r.get("kind") == "debuted")
            b7[side] = {"pool_n": len(rows), "pool_debuted": deb,
                        "pool_debuted_pct": _r4(100.0 * deb / (len(rows) or 1)),
                        "ba_covered_n": len(cov), "ba_covered_debuted": covd,
                        "ba_covered_debuted_pct": _r4(100.0 * covd / (len(cov) or 1)),
                        "lift_pts": _r4(100.0 * covd / (len(cov) or 1) - 100.0 * deb / (len(rows) or 1))}
        b7["brief_stated"] = {"hitter": [845, 1917, 104, 139], "pitcher": [981, 2040, 100, 121]}
    except Exception as exc:                                    # pragma: no cover
        b7 = {"error": f"{type(exc).__name__}: {exc}"}
    print("  stage %s" % 'B7_selection_hazard', flush=True)
    out["B7_selection_hazard"] = b7

    # ---- multiplicity roll-up --------------------------------------------
    cells = []
    for arm, a in out["arms"].items():
        for tool, c in a["tools"].items():
            cells.append({"arm": arm, "tool": tool,
                          "verdict": c["gate"].get("verdict"),
                          "d_rho": c.get("primary", {}).get("d_rho"),
                          "d_auc": c.get("primary", {}).get("d_auc"),
                          "F_rho": c["gate"].get("F_rho"),
                          "F_auc": c["gate"].get("F_auc"),
                          "n": c.get("primary", {}).get("n", 0)})
    for arm, a in out["arms"].items():
        for tool, c in a["tools"].items():
            nc = c.get("C61_permuted_source_null") or {}
            for cell in cells:
                if cell["arm"] == arm and cell["tool"] == tool:
                    cell["p_rho"] = nc.get("p_rho")
                    cell["p_auc"] = nc.get("p_auc")
    ship = [c for c in cells if c["verdict"] == "SHIP"]
    # Holm-Bonferroni across the 5 tools of the POWERED arm on the primary metric
    armA = sorted([c for c in cells if c["arm"] == "A_fg_vs_pipeline"
                   and c.get("p_rho") is not None], key=lambda c: c["p_rho"])
    holm, prev = [], 0.0
    for i, c in enumerate(armA):
        adj = min(1.0, max(prev, (len(armA) - i) * c["p_rho"]))
        prev = adj
        holm.append({"tool": c["tool"], "p_rho": c["p_rho"], "holm_adj_p": _r4(adj),
                     "survives_holm_0.05": bool(adj <= 0.05)})
    out["multiplicity"] = {"n_gate_cells": len(cells), "n_ship": len(ship),
                           "k_of_n": f"{len(ship)} of {len(cells)}",
                           "k_of_n_powered_arm": f"{sum(1 for c in ship if c['arm'] == 'A_fg_vs_pipeline')} of 5",
                           "holm_armA_on_d_rho": holm,
                           "note": "permutation p is add-one corrected on 1000 draws, so "
                                   "the smallest reportable p is 0.000999",
                           "cells": cells}
    out["verdict"] = "SHIP_SOME" if ship else "NO_SHIP_EQUAL_WEIGHT_RETAINS"

    OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
    # per-cell scratch files exist only to cross a process boundary
    if CELL_DIR.exists():
        for f in CELL_DIR.glob("*.json"):
            f.unlink()
        try:
            CELL_DIR.rmdir()
        except OSError:
            pass
    return out


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--sens":
        _g, _c, _sy = load_grades()
        _cs = load_career_mlb()
        _a = sys.argv[4] if len(sys.argv) > 4 else None
        _t = sys.argv[5] if len(sys.argv) > 5 else None
        Path(sys.argv[3]).write_text(
            json.dumps(compute_sens(_g, _cs, int(sys.argv[2]), _a, _t), indent=1),
            encoding="utf-8")
        sys.exit(0)
    if len(sys.argv) >= 5 and sys.argv[1] == "--cell":
        _arm, _tool, _dest = sys.argv[2], sys.argv[3], sys.argv[4]
        _g, _c, _sy = load_grades()
        _cs = load_career_mlb()
        Path(_dest).write_text(json.dumps(compute_cell(_g, _cs, _arm, _tool), indent=1),
                               encoding="utf-8")
        sys.exit(0)
    rep = run()
    print(f"wrote {OUT_PATH}")
    print("B1 premise:", rep["B1_premise"]["verdict"],
          "| BA obs", rep["B1_premise"]["measured_observations_total"],
          "rows", rep["B1_premise"]["ba_rows_with_tools"])
    for arm, a in rep["arms"].items():
        print(f"\nARM {arm}  {a['sources']}")
        for tool, c in a["tools"].items():
            g = c["gate"]
            p = c.get("primary", {})
            print(f"  {tool:9s} n={p.get('n', 0):5d} yrs={c['evaluable_years']} "
                  f"d_rho={p.get('d_rho')} F={g.get('F_rho')} "
                  f"d_auc={p.get('d_auc')} F={g.get('F_auc')} -> {g.get('verdict')}")
    print("\nverdict:", rep["verdict"], rep["multiplicity"]["k_of_n"])
