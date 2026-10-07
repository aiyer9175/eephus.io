# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Paired, clustered bootstrap intervals on a model's improvement gap over the
benchmark its eval already scores it against (LIBRARY_14, owner answer LB-Q4,
2026-10-02: "print now, add intervals").

An interval is a MEASUREMENT on rows the eval already scored. It adds no frame,
no label and no cut, it never moves the point values beside it, and it changes
no verdict (a verdict is hand-committed). The edge rule in model_updates.edge()
reads it through the registry card's `gap_ci` paths.

THE GAP. Oriented so positive means the model is better: benchmark minus model
for a lower-is-better statistic (MAE, Brier), model minus benchmark otherwise
(r, Spearman, within-one-year rate).

THE BOOTSTRAP. Whole clusters (a player's rows, a team's seasons, a slate's
games) are drawn with replacement, the cluster count held at the sample's, and
BOTH arms are scored on every draw, so the interval is on the paired gap.
Predictions are held fixed: nothing is refit inside a draw, because the
question is how much the gap on these rows moves with the rows, not how much a
refit model would. 95% percentile interval, one fresh generator per call
(numpy default_rng(seed)), so every block reproduces on its own.

write_beside() is how a producer adds the block to an artifact it last wrote
on an earlier day: it re-runs the producer in memory, refuses unless every
protected block reproduces exactly and the file re-serialises byte for byte,
and then writes the file as it stood plus the new keys, so no existing value
moves.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

#: Draws per interval, the repository's standard (eta_fg_blend_gate, the eFV
#: gate standard, tools/arb_gate_a at its registered run).
B = 2000
#: The seed for producers that had no seed of their own before LIBRARY_14,
#: date-coded like every seed in the repository (the date the intervals were
#: registered). A producer with a seed of its own (tools/arb_gate_a.SEED)
#: keeps it.
SEED = 20261007
ORIENTATION = ("improvement: benchmark minus model for a lower-is-better "
               "statistic, model minus benchmark otherwise; positive means "
               "the model is better")
METHOD = ("paired percentile bootstrap: whole clusters drawn with replacement, "
          "both arms scored on every draw, predictions held fixed (no refit)")


def _finite(v) -> bool:
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)


def pearson(x: np.ndarray, y: np.ndarray) -> float | None:
    """Pearson r, or None when either side has no spread."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if len(x) < 3:
        return None
    xc, yc = x - x.mean(), y - y.mean()
    sxx, syy = float((xc * xc).sum()), float((yc * yc).sum())
    if sxx <= 0 or syy <= 0:
        return None
    return float((xc * yc).sum() / math.sqrt(sxx * syy))


def _avg_ranks(v: np.ndarray) -> np.ndarray:
    """1-based ranks with ties averaged (the rank Spearman uses)."""
    v = np.asarray(v, float)
    order = np.argsort(v, kind="mergesort")
    sv = v[order]
    ranks = np.empty(len(v), float)
    i = 0
    n = len(v)
    while i < n:
        j = i
        while j + 1 < n and sv[j + 1] == sv[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(x: np.ndarray, y: np.ndarray) -> float | None:
    """Spearman rho as Pearson r on tie-averaged ranks."""
    if len(x) < 3:
        return None
    return pearson(_avg_ranks(x), _avg_ranks(y))


def paired_cluster_interval(cluster_ids, gaps, *, seed: int, cluster: str,
                            b: int = B, ndigits: int = 4) -> dict:
    """The interval block for one comparison.

    `cluster_ids` holds one id per row; `gaps(idx)` returns {leg: gap} for a
    numpy index array over those rows (np.arange(n) gives the point). A draw
    where a leg is undefined (None or not finite) is dropped for that leg and
    the count of kept draws is reported."""
    ids = list(cluster_ids)
    n = len(ids)
    if n == 0:
        raise ValueError("no rows to bootstrap")
    order: dict = {}
    for i, c in enumerate(ids):
        order.setdefault(c, []).append(i)
    members = [np.asarray(v, dtype=np.int64) for v in order.values()]
    k = len(members)
    point = gaps(np.arange(n, dtype=np.int64))
    draws: dict[str, list[float]] = {leg: [] for leg in point}
    rng = np.random.default_rng(seed)
    for _ in range(b):
        pick = rng.integers(0, k, k)
        idx = np.concatenate([members[j] for j in pick])
        for leg, g in gaps(idx).items():
            if _finite(g):
                draws[leg].append(float(g))
    out: dict = {}
    for leg, p in point.items():
        if not _finite(p) or len(draws[leg]) < b // 2:
            raise ValueError(f"leg {leg!r}: point {p!r} or too few defined draws "
                             f"({len(draws[leg])} of {b})")
        lo, hi = np.percentile(np.asarray(draws[leg]), [2.5, 97.5])
        leg_out = {"point": round(float(p), ndigits),
                   "lo95": round(float(lo), ndigits),
                   "hi95": round(float(hi), ndigits)}
        if len(draws[leg]) < b:
            leg_out["draws_used"] = len(draws[leg])
        out[leg] = leg_out
    out.update({"B": b, "seed": seed, "cluster": cluster, "clusters": k, "n": n,
                "orientation": ORIENTATION, "method": METHOD})
    return out


# ---------------------------------------------------------------------------
# writing the block beside values written on an earlier day
# ---------------------------------------------------------------------------


def _dig(doc, dotted: str):
    cur = doc
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(dotted)
        cur = cur[part]
    return cur


def _drop(doc, dotted: str) -> None:
    parent, _, leaf = dotted.rpartition(".")
    try:
        holder = _dig(doc, parent) if parent else doc
    except KeyError:
        return
    if isinstance(holder, dict):
        holder.pop(leaf, None)


def _put(doc, dotted: str, value) -> None:
    parent, _, leaf = dotted.rpartition(".")
    holder = _dig(doc, parent) if parent else doc
    if not isinstance(holder, dict):
        raise KeyError(dotted)
    holder.pop(leaf, None)
    holder[leaf] = value


def _beside(path: Path, fresh: dict, new_keys: list[str], *,
            protect: list[str], dumps_kw: dict | None = None):
    """(kw, stored doc with the new keys set, {key: block}); raises
    RuntimeError naming what does not reproduce."""
    kw = {"indent": 1, **(dumps_kw or {})}
    protect = [p for p in protect if p not in new_keys]
    text = Path(path).read_text(encoding="utf-8")
    stored = json.loads(text)
    if json.dumps(stored, **kw) != text:
        raise RuntimeError(f"{path} does not re-serialise byte for byte; "
                           "refusing to rewrite it")
    fresh = json.loads(json.dumps(fresh, **kw))
    blocks = {k: _dig(fresh, k) for k in new_keys}
    bare_fresh = json.loads(json.dumps(fresh))
    bare_stored = json.loads(json.dumps(stored))
    for k in new_keys:
        _drop(bare_fresh, k)
        _drop(bare_stored, k)
    moved = []
    for p in protect:
        try:
            a, b = _dig(bare_fresh, p), _dig(bare_stored, p)
        except KeyError:
            moved.append(f"{p} (missing)")
            continue
        if a != b:
            moved.append(p)
    if moved:
        raise RuntimeError(f"{Path(path).name}: the rerun does not reproduce {moved}; "
                           "an interval cannot sit beside values it was not measured on")
    if any(not isinstance(v, dict) for v in blocks.values()):
        raise RuntimeError(f"{Path(path).name}: the rerun produced no interval for "
                           f"{[k for k, v in blocks.items() if not isinstance(v, dict)]}")
    for k, v in blocks.items():
        _put(stored, k, v)
    return kw, stored, blocks


def check_beside(path: Path, fresh: dict, new_keys: list[str], *,
                 protect: list[str], dumps_kw: dict | None = None) -> dict:
    """write_beside without the write: {key: block}, or RuntimeError."""
    return _beside(path, fresh, new_keys, protect=protect, dumps_kw=dumps_kw)[2]


def write_beside(path: Path, fresh: dict, new_keys: list[str], *,
                 protect: list[str], dumps_kw: dict | None = None) -> dict:
    """Write `path` as it stands plus each dotted key of `new_keys` copied from
    `fresh` (the producer's in-memory rerun). Refuses, writing nothing, unless
    the file re-serialises byte for byte (so nothing else can move) and every
    dotted path in `protect` holds the same value in `fresh` as on disk once
    the new keys are set aside. Returns {key: block} as written."""
    kw, stored, blocks = _beside(path, fresh, new_keys, protect=protect,
                                 dumps_kw=dumps_kw)
    Path(path).write_text(json.dumps(stored, **kw), encoding="utf-8")
    return blocks
