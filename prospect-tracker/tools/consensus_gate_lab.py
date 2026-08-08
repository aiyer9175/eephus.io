# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Lane D1 -- quantify the retroactive contamination of historical consensus points.

READ-ONLY on consensus.py and grade_normalization.py. This lab replays
consensus.build_timeseries' per-player loop with each of the three contaminated
ingredients made as-of, and measures how far consensus_fv_raw moves at the exact
points the eFV training matrices consume.

Pre-registration, verdict rule and results:
    docs/efv-2026-08-07b/CONSENSUS_CONTAMINATION.md
Artifact:
    data/consensus_contamination_eval.json

Channels (see the gate doc section 1 for the source lines):
    C1  total_fv_instances   counted over the player's FULL history, applied to every point
    C2  dropped_off_pairs    computed over the FULL corpus, applied to every point
    C3  grade normalization  offsets built from the FULL snapshots table, applied per point

Run: python tools/consensus_gate_lab.py
"""
from __future__ import annotations

import json
import math
import random
import re
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import consensus as C                      # noqa: E402
import grade_normalization as GN           # noqa: E402
import storage                             # noqa: E402

DATA = _ROOT / "data"
OUT = DATA / "consensus_contamination_eval.json"
DB = _ROOT / "prospects.db"

TOL = 0.005                 # FV tolerance for "this row differs"
N_BOOT = 2000
SEED = 20260807

# Pre-registered thresholds. See gate doc section 5.
BAR_FIDELITY_PCT = 99.0
BAR_PCT_HALF_FV = 1.0       # (a) pct of joined rows moving >= 0.5 FV
BAR_MEAN_ABS = 0.25         # (b) mean |delta| over affected rows

ARMS = ("asof_c1", "asof_c2", "asof_c3", "asof_all",
        "fix_c2_detector", "fix_c2_detector_asof")

# Org-list label, human-readable form: "MLB Pipeline 2021 Nationals Top 30".
# consensus._dropped_off_pairs (:1001) only recognises the LEGACY slug form
# ("<source>_<year>_org_<slug>"), which occurs ZERO times in the corpus. This
# pattern is what a corrected detector would need; see the gate doc R2.
_ORG_LABEL_HUMAN = re.compile(r"^(?P<src>.*?)\s+(?P<yr>\d{4})\s+(?P<org>.+?)\s+Top\s+\d+$")


# ---------------------------------------------------------------------------
# as-of grade-normalization remapper
#
# Faithful re-implementation of grade_normalization.build_remapper (:227-295)
# with a date cutoff applied to the SELECT that feeds _all_latest (:72-101).
# Every constant and every fallback is imported from the module so the two
# cannot drift: REFERENCE, _MIN_N, _SYNTHETIC_SOURCES, _is_pitcher, _mappable,
# _apply_offset.
# ---------------------------------------------------------------------------

def _all_latest_asof(rows_sorted, cutoff: str) -> dict:
    """{(role, year): {player_key: {source: fv}}} over snapshots dated <= cutoff."""
    tmp: dict = {}
    for date, src, pk, pos, fvf in rows_sorted:
        if date > cutoff:
            break                       # rows_sorted is ascending by date
        yr = int(date[:4])
        role = "pitcher" if GN._is_pitcher(pos) else "hitter"
        k = (role, yr, pk, src)
        prev = tmp.get(k)
        if prev is None or date > prev[0]:
            tmp[k] = (date, fvf)
    out: dict = {}
    for (role, yr, pk, src), (_d, fvf) in tmp.items():
        out.setdefault((role, yr), {}).setdefault(pk, {})[src] = fvf
    return out


def _pairs_from(latest: dict, source: str, role: str, year: int):
    m = latest.get((role, year), {})
    return [(d[source], d[GN.REFERENCE]) for d in m.values()
            if source in d and GN.REFERENCE in d]


def _paired_dists_from(latest: dict, source: str, role: str, year: int):
    """Mirror of grade_normalization._paired_dists (:112-132) on an as-of `latest`."""
    pairs = _pairs_from(latest, source, role, year)
    pooled = False
    if len(pairs) < GN._MIN_N:
        allp: list = []
        for (r, y) in list(latest.keys()):
            if r == role:
                allp.extend(_pairs_from(latest, source, r, y))
        if len(allp) >= GN._MIN_N:
            pairs, pooled = allp, True
    if not pairs:
        return np.array([]), np.array([]), pooled
    src = np.sort(np.array([p[0] for p in pairs], dtype=float))
    ref = np.sort(np.array([p[1] for p in pairs], dtype=float))
    return src, ref, pooled


def build_remapper_asof(rows_sorted, cutoff: str, aliases: dict | None = None):
    """Mirror of grade_normalization.build_remapper (:227-295), cut off at `cutoff`."""
    latest = _all_latest_asof(rows_sorted, cutoff)
    sources: set[str] = set()
    for players in latest.values():
        for d in players.values():
            sources.update(d.keys())
    table: dict = {}
    for (role, yr) in list(latest.keys()):
        for src in sources:
            if src == GN.REFERENCE or src in GN._SYNTHETIC_SOURCES:
                continue
            s_sorted, r_sorted, _pooled = _paired_dists_from(latest, src, role, yr)
            if not (len(s_sorted) and len(r_sorted) and GN._mappable(s_sorted, r_sorted)):
                continue
            if len(s_sorted) < GN._MIN_N:
                continue
            table[(src, role, yr)] = (s_sorted, r_sorted)

    # _apply_offset (grade_normalization.py:155) reduces each cell to
    # mean(src) - mean(ref). The sorted arrays are never used for anything else,
    # which is what makes the incremental repair in build_offset_timeline exact.
    offsets = {k: float(np.mean(s) - np.mean(r)) for k, (s, r) in table.items()}

    alias_map = dict(aliases or {})

    def remap(fv, source, position, year):
        if fv is None:
            return None
        if source == GN.REFERENCE:
            return float(fv)
        try:
            yr = int(year)
        except (TypeError, ValueError):
            return float(fv)
        role = "pitcher" if GN._is_pitcher(position) else "hitter"
        ent = table.get((source, role, yr))
        if not ent:
            canon = alias_map.get(source)
            if canon and canon != source:
                ent = table.get((canon, role, yr))
        if not ent:
            return float(fv)
        src, ref = ent
        return GN._apply_offset(float(fv), src, ref)

    remap.offsets = offsets          # exposed for the incremental-repair check
    return remap


# ---------------------------------------------------------------------------
# REPAIR PROTOTYPE: incremental as-of offset timeline
#
# The naive as-of repair rebuilds the remapper at every event date, which is
# quadratic in a loop that already walks every event date for every player.
# This builds the WHOLE timeline in ONE ascending pass, maintaining running
# pair sums per (source, role, year), and is exact because _apply_offset only
# ever reads two means. Verified against the from-scratch builder below.
# ---------------------------------------------------------------------------

class _Cell:
    __slots__ = ("pairs", "sum_src", "sum_ref", "uniq_src", "uniq_ref")

    def __init__(self):
        self.pairs: dict = {}          # pk -> (src_fv, ref_fv)
        self.sum_src = 0.0
        self.sum_ref = 0.0
        self.uniq_src: dict = {}       # value -> count
        self.uniq_ref: dict = {}

    def _bump(self, d, v, k):
        n = d.get(v, 0) + k
        if n <= 0:
            d.pop(v, None)
        else:
            d[v] = n

    def set_pair(self, pk, sv, rv):
        old = self.pairs.get(pk)
        if old is not None:
            self.sum_src -= old[0]
            self.sum_ref -= old[1]
            self._bump(self.uniq_src, old[0], -1)
            self._bump(self.uniq_ref, old[1], -1)
        self.pairs[pk] = (sv, rv)
        self.sum_src += sv
        self.sum_ref += rv
        self._bump(self.uniq_src, sv, 1)
        self._bump(self.uniq_ref, rv, 1)

    @property
    def n(self):
        return len(self.pairs)

    def mappable(self):
        return len(self.uniq_src) >= 2 and len(self.uniq_ref) >= 2

    def offset(self):
        n = self.n
        return self.sum_src / n - self.sum_ref / n


def build_offset_timeline(rows_sorted, cut_dates):
    """{cut_date: {(source, role, year): offset}} in ONE ascending pass.

    `cut_dates` must be ascending. Mirrors build_remapper_asof's cell selection:
    a cell needs >= _MIN_N pairs after the pooled fallback, and _mappable on both
    sides. The pooled fallback pools the source's overlap across every year seen
    SO FAR, which is the as-of form of grade_normalization._paired_dists:121-127.
    """
    latest: dict = {}                   # (role, yr, pk) -> {source: fv}
    cells: dict = {}                    # (source, role, yr) -> _Cell
    pooled: dict = {}                   # (source, role) -> _Cell   (keyed by (pk, yr))
    role_years: set = set()             # every (role, year) _all_latest would key
    sources: set = set()                # every source _all_latest would expose

    def touch(src, role, yr, pk, sv, rv):
        cells.setdefault((src, role, yr), _Cell()).set_pair(pk, sv, rv)
        pooled.setdefault((src, role), _Cell()).set_pair((pk, yr), sv, rv)

    out: dict = {}
    ci = 0
    for date, src, pk, pos, fvf in rows_sorted:
        while ci < len(cut_dates) and cut_dates[ci] < date:
            out[cut_dates[ci]] = _snapshot_offsets(cells, pooled, role_years, sources)
            ci += 1
        yr = int(date[:4])
        role = "pitcher" if GN._is_pitcher(pos) else "hitter"
        role_years.add((role, yr))
        sources.add(src)
        d = latest.setdefault((role, yr, pk), {})
        # _all_latest (:96) keeps a row only when it is STRICTLY newer, so the
        # FIRST row wins a same-date tie. Mirror that or the pair sums drift.
        prev = d.get(src)
        if prev is not None and date <= prev[0]:
            continue
        d[src] = (date, fvf)
        if src == GN.REFERENCE:
            for s, (_sd, v) in d.items():
                if s == GN.REFERENCE or s in GN._SYNTHETIC_SOURCES:
                    continue
                touch(s, role, yr, pk, v, fvf)
        elif src not in GN._SYNTHETIC_SOURCES:
            rv = d.get(GN.REFERENCE)
            if rv is not None:
                touch(src, role, yr, pk, fvf, rv[1])
    while ci < len(cut_dates):
        out[cut_dates[ci]] = _snapshot_offsets(cells, pooled, role_years, sources)
        ci += 1
    return out


def _snapshot_offsets(cells, pooled, role_years, sources):
    """Freeze the current state into {(source, role, year): offset}.

    Iterates the SAME cross-product build_remapper does (:254-257): every
    (role, year) key of _all_latest crossed with every source seen anywhere. A
    (source, role, year) with no pairs of its own still gets a cell when the
    source's pooled overlap clears _MIN_N, which is the behaviour that makes the
    thin-cell pooling reach across years in the first place.
    """
    tbl = {}
    for (role, yr) in role_years:
        for src in sources:
            if src == GN.REFERENCE or src in GN._SYNTHETIC_SOURCES:
                continue
            c = cells.get((src, role, yr))
            use = c
            if c is None or c.n < GN._MIN_N:
                p = pooled.get((src, role))
                if p is not None and p.n >= GN._MIN_N:
                    use = p
                else:
                    continue                  # thin even pooled -> cell dropped
            if use is None or not use.mappable():
                continue
            tbl[(src, role, yr)] = use.offset()
    return tbl


# ---------------------------------------------------------------------------
# corrected drop-off detector
#
# Byte-for-byte consensus._dropped_off_pairs (:974-1032) EXCEPT that the org
# slug is also extracted from the human-readable label format. The legacy
# "_org_" slug the shipped detector requires does not occur in this corpus at
# all, so the shipped detector returns the empty set and the (fv+30)/2 shrink
# never fires. This function measures what the shrink WOULD do.
# ---------------------------------------------------------------------------

def _org_slug(label: str | None) -> str | None:
    if not label:
        return None
    if "_org_" in label:
        try:
            return label.split("_org_", 1)[1]
        except IndexError:
            return None
    m = _ORG_LABEL_HUMAN.match(label)
    return m.group("org") if m else None


def dropped_off_pairs_fixed(snapshots) -> set[tuple[str, str]]:
    grouped: dict[tuple[str, str], dict[str, tuple[str, set[str]]]] = {}
    for s in snapshots:
        slug = _org_slug(s.interval_label)
        if slug is None:
            continue
        key = (s.source, slug)
        bucket = grouped.setdefault(key, {})
        prev = bucket.get(s.interval_label)
        if prev is None:
            bucket[s.interval_label] = (s.snapshot_date, {s.player_key})
        else:
            latest_date, players = prev
            players.add(s.player_key)
            if s.snapshot_date > latest_date:
                latest_date = s.snapshot_date
            bucket[s.interval_label] = (latest_date, players)
    pairs: set[tuple[str, str]] = set()
    for (source, _slug), labels in grouped.items():
        if len(labels) < 2:
            continue
        sorted_labels = sorted(labels.items(), key=lambda kv: kv[1][0], reverse=True)
        latest_players = sorted_labels[0][1][1]
        prior_players = sorted_labels[1][1][1]
        for pk in prior_players - latest_players:
            pairs.add((pk, source))
    return pairs


# ---------------------------------------------------------------------------
# replay of build_timeseries' per-player loop (consensus.py:1197-1305)
# ---------------------------------------------------------------------------

def replay_point(player_snaps, target_date, *, instances_asof, dropped, grade_norm):
    """Rebuild the player's consensus point AT target_date under one arm.

    `player_snaps` is the collision-pruned snapshot list. `instances_asof` toggles
    channel 1. `dropped` is the pair set for this arm. `grade_norm` is the remapper
    for this arm. Everything else is byte-for-byte the production loop.
    """
    by_date: dict[str, list] = defaultdict(list)
    for s in player_snaps:
        by_date[s.snapshot_date].append(s)
    if target_date not in by_date:
        return None

    # C1: instance count. Production counts over the whole history (:1246-1252).
    seen_fv_keys: set[tuple[str, str]] = set()
    for s in player_snaps:
        if s.fv is not None and s.source not in C.CONSTANT_ANCHOR_SOURCES:
            if instances_asof and s.snapshot_date > target_date:
                continue
            seen_fv_keys.add((s.source, s.snapshot_date))
    total_fv_instances = len(seen_fv_keys)

    latest_by_source: dict[str, list] = {}
    for snap_date in sorted(by_date):
        if snap_date > target_date:
            break
        for s in by_date[snap_date]:
            prev_list = latest_by_source.get(s.source)
            if not prev_list:
                latest_by_source[s.source] = [s]
                continue
            prev_date = prev_list[0].snapshot_date
            if s.snapshot_date > prev_date:
                latest_by_source[s.source] = [s]
            elif s.snapshot_date == prev_date:
                already = any(
                    (e.interval_label == s.interval_label and e.fv == s.fv
                     and e.rank == s.rank)
                    for e in prev_list
                )
                if not already:
                    latest_by_source[s.source].append(s)
        if snap_date != target_date:
            continue
        event_label = by_date[snap_date][-1].interval_label
        day_snaps_flat = [s for lst in latest_by_source.values() for s in lst]
        return C.compute_consensus_point(
            day_snaps_flat,
            event_date=snap_date,
            event_label=event_label,
            single_source_k=C.SINGLE_SOURCE_K,
            total_fv_instances=total_fv_instances,
            dropped_off_pairs=dropped,
            source_weights=C._SOURCE_WEIGHTS,
            grade_norm=grade_norm,
        )
    return None


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------

def _rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    rx, ry = _rank(xs), _rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def describe(deltas, n_joined):
    """Delta distribution for one arm on one population."""
    aff = [d for d in deltas if abs(d) > TOL]
    n_half = sum(1 for d in deltas if abs(d) >= 0.5)
    n_one = sum(1 for d in deltas if abs(d) >= 1.0)
    mean = sum(deltas) / len(deltas) if deltas else 0.0
    sd = (statistics_sd(deltas) if len(deltas) > 1 else 0.0)
    mean_abs_aff = sum(abs(d) for d in aff) / len(aff) if aff else 0.0
    return {
        "n_rows": n_joined,
        "n_differ": len(aff),
        "pct_differ": round(100.0 * len(aff) / n_joined, 3) if n_joined else 0.0,
        "mean_delta_all": round(mean, 4),
        "sd_delta_all": round(sd, 4),
        "mean_abs_delta_affected": round(mean_abs_aff, 4),
        "max_abs_delta": round(max((abs(d) for d in deltas), default=0.0), 4),
        "n_abs_gt_0p5": n_half,
        "n_abs_gt_1p0": n_one,
        "pct_abs_gt_0p5": round(100.0 * n_half / n_joined, 3) if n_joined else 0.0,
    }


def statistics_sd(v):
    m = sum(v) / len(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def leak_test(rows, arm, target_key, rng):
    """rho(baseline, y) - rho(asof, y) on the AFFECTED subset, with a paired bootstrap."""
    sub = [r for r in rows
           if r["arms"].get(arm) is not None
           and abs(r["arms"][arm] - r["baseline"]) > TOL
           and r.get(target_key) is not None]
    n = len(sub)
    if n < 10:
        return {"n": n, "resolvable": False, "note": "n < 10, not measured"}
    b = [r["baseline"] for r in sub]
    a = [r["arms"][arm] for r in sub]
    y = [float(r[target_key]) for r in sub]
    rb, ra = spearman(b, y), spearman(a, y)
    if rb is None or ra is None:
        return {"n": n, "resolvable": False, "note": "degenerate"}
    d = rb - ra
    boots = []
    idx = list(range(n))
    for _ in range(N_BOOT):
        pick = [rng.choice(idx) for _ in range(n)]
        bb = [b[i] for i in pick]
        aa = [a[i] for i in pick]
        yy = [y[i] for i in pick]
        r1, r2 = spearman(bb, yy), spearman(aa, yy)
        if r1 is not None and r2 is not None:
            boots.append(r1 - r2)
    boots.sort()
    lo = boots[int(0.025 * len(boots))] if boots else float("nan")
    hi = boots[int(0.975 * len(boots))] if boots else float("nan")
    return {
        "n": n,
        "rho_baseline": round(rb, 4),
        "rho_asof": round(ra, 4),
        "d_rho": round(d, 4),
        "ci95": [round(lo, 4), round(hi, 4)],
        "excludes_zero": bool(lo > 0 or hi < 0),
        "resolvable": True,
    }


def leak_test_fullpool(rows, arm, target_key, rng):
    """Same statistic on the WHOLE side pool, not just the affected subset.

    ADDED POST-HOC. The affected-subset form is degenerate for channel 1: every
    affected row gets the SAME affine pull (2/3 x + 35/3), which is monotone, so
    the within-subset Spearman cannot move and d_rho is exactly 0 by construction.
    The board is ranked over the whole pool, so the full-pool form is the one that
    describes the served task. Reported alongside, not substituted for, the
    pre-registered criterion (c).
    """
    sub = [r for r in rows
           if r["arms"].get(arm) is not None and r.get(target_key) is not None]
    n = len(sub)
    if n < 10:
        return {"n": n, "resolvable": False, "note": "n < 10, not measured"}
    b = [r["baseline"] for r in sub]
    a = [r["arms"][arm] for r in sub]
    y = [float(r[target_key]) for r in sub]
    rb, ra = spearman(b, y), spearman(a, y)
    if rb is None or ra is None:
        return {"n": n, "resolvable": False, "note": "degenerate"}
    boots = []
    idx = list(range(n))
    for _ in range(N_BOOT):
        pick = [rng.choice(idx) for _ in range(n)]
        r1 = spearman([b[i] for i in pick], [y[i] for i in pick])
        r2 = spearman([a[i] for i in pick], [y[i] for i in pick])
        if r1 is not None and r2 is not None:
            boots.append(r1 - r2)
    boots.sort()
    lo = boots[int(0.025 * len(boots))] if boots else float("nan")
    hi = boots[int(0.975 * len(boots))] if boots else float("nan")
    return {"n": n, "rho_baseline": round(rb, 4), "rho_asof": round(ra, 4),
            "d_rho": round(rb - ra, 4), "ci95": [round(lo, 4), round(hi, 4)],
            "excludes_zero": bool(lo > 0 or hi < 0), "resolvable": True}


# ---------------------------------------------------------------------------
# D16: same-name collisions (consensus.py:1357-1405)
# ---------------------------------------------------------------------------

def _normalize_name_for_dedup(name: str) -> str:
    if not name:
        return ""
    cleaned = name.lower().replace(",", "").replace(".", "")
    cleaned = cleaned.replace("’", "'").replace("‘", "'")
    return " ".join(cleaned.split())


def d16_collisions(by_player, snaps_by_player):
    """Count normalized-name collisions the empty _SAME_NAME_NOT_DUPES merges silently."""
    groups: dict[str, list[str]] = defaultdict(list)
    for pk, snaps in by_player.items():
        name, _pos, _org = C._latest_meta(snaps)
        name = C._canonical_player_name(pk, name)
        groups[_normalize_name_for_dedup(name)].append(pk)
    colliding = {k: v for k, v in groups.items() if len(v) > 1}
    non_noid = []
    for nk, keys in sorted(colliding.items()):
        if any(k.endswith("__noid") for k in keys):
            continue
        detail = []
        for k in keys:
            ss = snaps_by_player[k]
            dates = sorted(s.snapshot_date for s in ss)
            orgs = sorted({s.org for s in ss if s.org})
            srcs = sorted({s.source for s in ss})
            detail.append({"player_key": k, "n_snaps": len(ss),
                           "first": dates[0], "last": dates[-1],
                           "orgs": orgs[:4], "sources": srcs[:6]})
        # Overlapping publication windows from DISJOINT orgs is the signature of
        # two different people being merged into one timeseries.
        spans = [(d["first"], d["last"]) for d in detail]
        overlap = any(spans[i][0] <= spans[j][1] and spans[j][0] <= spans[i][1]
                      for i in range(len(spans)) for j in range(i + 1, len(spans)))
        orgsets = [set(d["orgs"]) for d in detail]
        disjoint = all(not (orgsets[i] & orgsets[j])
                       for i in range(len(orgsets)) for j in range(i + 1, len(orgsets)))
        # Decisive case: two keys carrying DIFFERENT numeric id suffixes are two
        # different resolved identities, not two spellings of one.
        ids = [re.search(r"_(\d{5,})$", k) for k in keys]
        distinct_ids = sorted({m.group(1) for m in ids if m})
        two_ids = len(distinct_ids) >= 2
        non_noid.append({"normalized_name": nk, "keys": keys,
                         "windows_overlap": overlap, "orgs_disjoint": disjoint,
                         "distinct_numeric_ids": distinct_ids,
                         "provably_different_players": two_ids,
                         "detail": detail})
    return {
        "allowlist_is_empty": len(C_SAME_NAME_ALLOWLIST) == 0,
        "n_colliding_names": len(colliding),
        "n_keys_involved": sum(len(v) for v in colliding.values()),
        "n_keys_merged_away": sum(len(v) - 1 for v in colliding.values()),
        "n_noid_case": sum(1 for v in colliding.values()
                           if any(k.endswith("__noid") for k in v)),
        "n_non_noid": len(non_noid),
        "n_non_noid_overlapping_windows": sum(1 for d in non_noid if d["windows_overlap"]),
        "n_provably_different_players": sum(
            1 for d in non_noid if d["provably_different_players"]),
        "non_noid": non_noid,
    }


# `_SAME_NAME_NOT_DUPES` is a function-local in build_timeseries, so it cannot be
# imported. It is literally `set()` at consensus.py:1359; mirrored here for the
# artifact's `allowlist_is_empty` field, which is a source assertion, not a fit.
C_SAME_NAME_ALLOWLIST: set = set()


# ---------------------------------------------------------------------------

def main():
    t0 = time.time()
    rng = random.Random(SEED)

    print("loading snapshots ...", flush=True)
    raw_snaps = storage.load_all_snapshots()
    snaps = [C._canonicalize_player_snapshot(s) for s in raw_snaps]
    print(f"  {len(snaps)} snapshots", flush=True)

    by_player_all: dict[str, list] = defaultdict(list)
    for s in snaps:
        by_player_all[s.player_key].append(s)

    # Collision pruning is held CONSTANT across arms: it is a fourth, separate
    # retroactive channel (it uses future snapshots to pick the live cluster) and
    # measuring it here would confound the three under test. Ledgered, not measured.
    pruned = {pk: C._prune_collision_cluster(ss) for pk, ss in by_player_all.items()}

    # ---- matrices ----
    matrices = {}
    for side, fn in (("hit", "xfv_hitter_matrix.json"), ("pit", "xfv_pitcher_matrix.json")):
        matrices[side] = json.load(open(DATA / fn, encoding="utf-8"))
    targets = []
    for side, rows in matrices.items():
        for r in rows:
            if r.get("asof_date") and r.get("player_key"):
                targets.append((side, r))
    asof_dates = sorted({r["asof_date"] for _s, r in targets})
    print(f"  {len(targets)} matrix rows, {len(asof_dates)} distinct as-of dates", flush=True)

    # ---- baseline ingredients (production) ----
    print("building baseline ingredients ...", flush=True)
    dropped_full = C._dropped_off_pairs(snaps)
    gn_full = GN.build_remapper(aliases=C.SOURCE_ALIASES)
    print(f"  dropped_off_pairs (full corpus): {len(dropped_full)}", flush=True)

    # ---- as-of ingredients, one set per distinct as-of date ----
    con = sqlite3.connect(str(DB))
    try:
        db_rows = con.execute(
            "SELECT snapshot_date, source, player_key, position, fv FROM snapshots "
            "WHERE fv IS NOT NULL").fetchall()
    finally:
        con.close()
    rows_sorted = []
    for date, src, pk, pos, fv in db_rows:
        if not src or not pk or not date:
            continue
        try:
            fvf = float(fv)
        except (TypeError, ValueError):
            continue
        rows_sorted.append((str(date), src, pk, pos, fvf))
    rows_sorted.sort(key=lambda t: t[0])

    dropped_fixed_full = dropped_off_pairs_fixed(snaps)
    print(f"  dropped_off_pairs (CORRECTED detector, full corpus): "
          f"{len(dropped_fixed_full)}", flush=True)

    dropped_asof: dict[str, set] = {}
    dropped_fixed_asof: dict[str, set] = {}
    gn_asof: dict[str, object] = {}
    for i, d in enumerate(asof_dates, 1):
        sub = [s for s in snaps if s.snapshot_date <= d]
        dropped_asof[d] = C._dropped_off_pairs(sub)
        dropped_fixed_asof[d] = dropped_off_pairs_fixed(sub)
        gn_asof[d] = build_remapper_asof(rows_sorted, d, aliases=C.SOURCE_ALIASES)
        print(f"  [{i}/{len(asof_dates)}] {d}: dropped={len(dropped_asof[d])} "
              f"dropped_fixed={len(dropped_fixed_asof[d])}", flush=True)

    # ---- repair prototype: verify + time the incremental offset timeline ----
    print("verifying the incremental as-of offset timeline ...", flush=True)
    t_naive = time.time()
    naive_offsets = {d: build_remapper_asof(rows_sorted, d,
                                            aliases=C.SOURCE_ALIASES).offsets
                     for d in asof_dates}
    t_naive = time.time() - t_naive
    all_dates = sorted({s.snapshot_date for s in snaps if s.snapshot_date}
                       | set(asof_dates))
    t_inc = time.time()
    timeline = build_offset_timeline(rows_sorted, all_dates)
    t_inc = time.time() - t_inc
    mism = []
    for d in asof_dates:
        want, got = naive_offsets[d], timeline.get(d, {})
        for k in set(want) | set(got):
            a_, b_ = want.get(k), got.get(k)
            if a_ is None or b_ is None or abs(a_ - b_) > 1e-9:
                mism.append({"date": d, "cell": list(k), "from_scratch": a_,
                             "incremental": b_})
    repair_proto = {
        "cells_compared": sum(len(v) for v in naive_offsets.values()),
        "n_mismatch": len(mism),
        "exact": len(mism) == 0,
        "mismatch_sample": mism[:20],
        "naive_sec_for_45_dates": round(t_naive, 2),
        "incremental_sec_for_all_dates": round(t_inc, 2),
        "n_dates_incremental": len(all_dates),
        "naive_sec_extrapolated_to_all_dates": round(
            t_naive / max(1, len(asof_dates)) * len(all_dates), 1),
    }
    print(f"  incremental exact: {repair_proto['exact']} "
          f"({repair_proto['n_mismatch']} mismatched cells); "
          f"naive {t_naive:.1f}s/45 dates vs incremental {t_inc:.1f}s/"
          f"{len(all_dates)} dates", flush=True)

    # ---- replay ----
    print("replaying points ...", flush=True)
    recs = []
    unjoined = []
    for side, r in targets:
        pk, d = r["player_key"], r["asof_date"]
        ps = pruned.get(pk)
        if not ps:
            unjoined.append({"side": side, "player_key": pk, "asof_date": d,
                             "kind": r.get("kind"), "reason": "player_key absent"})
            continue
        base = replay_point(ps, d, instances_asof=False,
                            dropped=dropped_full, grade_norm=gn_full)
        if base is None or base.consensus_fv_raw is None:
            unjoined.append({"side": side, "player_key": pk, "asof_date": d,
                             "kind": r.get("kind"), "reason": "no point at asof_date"})
            continue
        arms = {}
        arms["asof_c1"] = replay_point(ps, d, instances_asof=True,
                                       dropped=dropped_full, grade_norm=gn_full)
        arms["asof_c2"] = replay_point(ps, d, instances_asof=False,
                                       dropped=dropped_asof[d], grade_norm=gn_full)
        arms["asof_c3"] = replay_point(ps, d, instances_asof=False,
                                       dropped=dropped_full, grade_norm=gn_asof[d])
        arms["asof_all"] = replay_point(ps, d, instances_asof=True,
                                        dropped=dropped_asof[d], grade_norm=gn_asof[d])
        arms["fix_c2_detector"] = replay_point(ps, d, instances_asof=False,
                                               dropped=dropped_fixed_full,
                                               grade_norm=gn_full)
        arms["fix_c2_detector_asof"] = replay_point(ps, d, instances_asof=False,
                                                    dropped=dropped_fixed_asof[d],
                                                    grade_norm=gn_full)
        dy = r.get("debut_year") if r.get("kind") == "debuted" else None
        if dy is None:
            c = str(r.get("cutoff") or "")
            dy = (int(c[:4]) + 1) if c[:4].isdigit() else 2026
        recs.append({
            "side": side, "player_key": pk, "asof_date": d, "kind": r.get("kind"),
            "decision_year": int(dy),
            "shipped": r.get("consensus_fv_raw"),
            "baseline": float(base.consensus_fv_raw),
            "arms": {k: (float(v.consensus_fv_raw)
                         if (v is not None and v.consensus_fv_raw is not None) else None)
                     for k, v in arms.items()},
            "target_censored": r.get("target_censored"),
            "target_resolved": r.get("target_resolved"),
        })
        if len(recs) % 500 == 0:
            print(f"  {len(recs)} replayed", flush=True)

    # ---- fidelity gate, PRE-REGISTERED form: replay vs the SHIPPED matrix ----
    fid_ok, fid_bad = 0, []
    for r in recs:
        sh = r["shipped"]
        if sh is None:
            continue
        if abs(float(sh) - r["baseline"]) <= TOL:
            fid_ok += 1
        else:
            fid_bad.append({"player_key": r["player_key"], "asof_date": r["asof_date"],
                            "side": r["side"], "shipped": sh, "replay": r["baseline"],
                            "delta": round(r["baseline"] - float(sh), 3)})
    n_fid = fid_ok + len(fid_bad)
    pct = 100.0 * fid_ok / n_fid if n_fid else 0.0
    big = [b for b in fid_bad if abs(b["delta"]) > 0.02]
    fidelity = {
        "basis": "replay baseline arm vs data/xfv_*_matrix.json consensus_fv_raw",
        "n_joined": n_fid,
        "n_within_tol": fid_ok,
        "pct_within_tol": round(pct, 3),
        "bar_pct": BAR_FIDELITY_PCT,
        "passes": bool(pct >= BAR_FIDELITY_PCT),
        "n_mismatch": len(fid_bad),
        "n_mismatch_le_0p02": len(fid_bad) - len(big),
        "n_mismatch_gt_0p02": len(big),
        "pct_within_0p02": round(100.0 * (fid_ok + len(fid_bad) - len(big)) / n_fid, 3)
        if n_fid else 0.0,
        "mismatch_sample": fid_bad[:40],
        "mismatch_gt_0p02": big[:60],
        "n_unjoined": len(unjoined),
        "unjoined_sample": unjoined[:40],
        "unjoined_by_kind": dict(_count(u.get("kind") for u in unjoined)),
        "unjoined_by_reason": dict(_count(u.get("reason") for u in unjoined)),
    }
    print(f"FIDELITY(shipped): {fid_ok}/{n_fid} = {pct:.3f}% within {TOL} FV "
          f"({'PASS' if fidelity['passes'] else 'FAIL'}); "
          f"{len(big)} exceed 0.02 FV", flush=True)

    # ---- fidelity check 2, ADDED AFTER the pre-registered check FAILED ----
    # The pre-registered check confounds two things: whether the replay copies
    # build_timeseries, and whether the shipped matrix was built at today's DB
    # vintage. This second check isolates the first by calling build_timeseries
    # itself, on the SAME snapshots, and comparing point-for-point. It is
    # reported as an addition, not as a replacement for the failed gate.
    print("running consensus.build_timeseries for the replay check ...", flush=True)
    t_bt = time.time()
    prod_ts = C.build_timeseries(raw_snaps, normalize=C.ADOPT_NORMALIZED_CONSENSUS)
    bt_sec = round(time.time() - t_bt, 1)
    prod_pt: dict[tuple[str, str], float] = {}
    for p in prod_ts:
        for pt in p.points:
            if pt.consensus_fv_raw is not None:
                prod_pt[(p.player_key, pt.snapshot_date)] = float(pt.consensus_fv_raw)
    r_ok, r_bad, r_missing = 0, [], 0
    for r in recs:
        v = prod_pt.get((r["player_key"], r["asof_date"]))
        if v is None:
            r_missing += 1
            continue
        if abs(v - r["baseline"]) <= TOL:
            r_ok += 1
        else:
            r_bad.append({"player_key": r["player_key"], "asof_date": r["asof_date"],
                          "build_timeseries": v, "replay": r["baseline"],
                          "delta": round(r["baseline"] - v, 3)})
    n_r = r_ok + len(r_bad)
    pct_r = 100.0 * r_ok / n_r if n_r else 0.0
    fidelity_replay = {
        "basis": "replay baseline arm vs consensus.build_timeseries on the same snapshots",
        "added_post_hoc": True,
        "why": ("the pre-registered check compares against a matrix artifact of unknown "
                "vintage; this one isolates whether the replay copies production"),
        "n_compared": n_r,
        "n_within_tol": r_ok,
        "pct_within_tol": round(pct_r, 3),
        "n_mismatch": len(r_bad),
        "mismatch_sample": r_bad[:40],
        "n_point_absent_from_build_timeseries": r_missing,
        "build_timeseries_sec": bt_sec,
    }
    print(f"FIDELITY(replay): {r_ok}/{n_r} = {pct_r:.3f}% within {TOL} FV; "
          f"{r_missing} points absent; build_timeseries took {bt_sec}s", flush=True)

    # Rows whose SHIPPED value differs from the replay by more than 0.02 FV are
    # excluded: those are the ones where the artifact vintage is genuinely a
    # different value, not a rounding hair. The sub-0.02 set is kept; excluding
    # it would drop 12% of the pool for a difference smaller than the display
    # precision of the column being measured.
    bad_keys = {(b["player_key"], b["asof_date"]) for b in big}
    clean = [r for r in recs if (r["player_key"], r["asof_date"]) not in bad_keys]
    print(f"  excluded {len(recs) - len(clean)} rows; {len(clean)} remain", flush=True)

    # ---- per-channel distributions ----
    channels = {}
    for arm in ARMS:
        per_side = {}
        for side in ("hit", "pit", "both"):
            sub = [r for r in clean if side == "both" or r["side"] == side]
            deltas = [(r["arms"][arm] - r["baseline"]) for r in sub
                      if r["arms"].get(arm) is not None]
            per_side[side] = describe(deltas, len(deltas))
        # fold profile
        folds = {}
        for r in clean:
            if r["arms"].get(arm) is None:
                continue
            k = f'{r["side"]}:{r["decision_year"]}'
            f = folds.setdefault(k, {"n": 0, "n_differ": 0, "sum": 0.0, "max_abs": 0.0})
            dlt = r["arms"][arm] - r["baseline"]
            f["n"] += 1
            f["sum"] += dlt
            if abs(dlt) > TOL:
                f["n_differ"] += 1
            f["max_abs"] = max(f["max_abs"], abs(dlt))
        for k, f in folds.items():
            f["mean_delta"] = round(f["sum"] / f["n"], 4)
            f["max_abs"] = round(f["max_abs"], 4)
            f["pct_differ"] = round(100.0 * f["n_differ"] / f["n"], 2)
            del f["sum"]
        worst = sorted(folds.items(),
                       key=lambda kv: -abs(kv[1]["mean_delta"]))[:6]
        leaks = {}
        leaks_full = {}
        for side in ("hit", "pit"):
            sub = [r for r in clean if r["side"] == side]
            leaks[f"{side}_censored"] = leak_test(sub, arm, "target_censored", rng)
            leaks[f"{side}_resolved"] = leak_test(sub, arm, "target_resolved", rng)
            leaks_full[f"{side}_censored"] = leak_test_fullpool(
                sub, arm, "target_censored", rng)
            leaks_full[f"{side}_resolved"] = leak_test_fullpool(
                sub, arm, "target_resolved", rng)
        # pre-registered verdict
        both = per_side["both"]
        crit_a = both["pct_abs_gt_0p5"] >= BAR_PCT_HALF_FV
        crit_b = both["mean_abs_delta_affected"] >= BAR_MEAN_ABS
        crit_c = any(v.get("excludes_zero") for v in leaks.values() if v.get("resolvable"))
        if both["n_differ"] == 0:
            verdict = "FALSE"
        elif crit_a or crit_b or crit_c:
            verdict = "CONFIRMED-MATERIAL"
        else:
            verdict = "CONFIRMED-IMMATERIAL"
        channels[arm] = {
            "by_side": per_side,
            "folds": folds,
            "worst_folds": [{"fold": k, **v} for k, v in worst],
            "leak": leaks,
            "leak_fullpool": leaks_full,
            "criteria": {"a_pct_ge_0p5": crit_a, "b_mean_abs_affected": crit_b,
                         "c_leak_ci_excludes_zero": crit_c},
            "verdict": verdict,
        }
        print(f"  {arm}: n_differ={both['n_differ']} pct={both['pct_differ']} "
              f"verdict={verdict}", flush=True)

    # ---- pairwise: contamination INSIDE a corrected drop-off detector ----
    # The shipped detector is dead, so "asof_c2 vs baseline" is trivially zero.
    # The live question for wave 2 is what the D1 channel-2 contamination costs
    # ONCE the detector works: that is asof-corrected minus full-corpus-corrected.
    pw_deltas = [(r["arms"]["fix_c2_detector_asof"] - r["arms"]["fix_c2_detector"])
                 for r in clean
                 if r["arms"].get("fix_c2_detector_asof") is not None
                 and r["arms"].get("fix_c2_detector") is not None]
    pw_rows = [dict(r, baseline=r["arms"]["fix_c2_detector"],
                    arms={"pw": r["arms"]["fix_c2_detector_asof"]})
               for r in clean
               if r["arms"].get("fix_c2_detector_asof") is not None
               and r["arms"].get("fix_c2_detector") is not None]
    pairwise = {
        "c2_corrected_asof_vs_corrected_full": {
            "basis": ("delta = fix_c2_detector_asof - fix_c2_detector. Isolates the D1 "
                      "channel-2 contamination on a detector that actually fires."),
            "both": describe(pw_deltas, len(pw_deltas)),
            "hit": describe([d for d, r in zip(pw_deltas, pw_rows) if r["side"] == "hit"],
                            sum(1 for r in pw_rows if r["side"] == "hit")),
            "pit": describe([d for d, r in zip(pw_deltas, pw_rows) if r["side"] == "pit"],
                            sum(1 for r in pw_rows if r["side"] == "pit")),
            "leak_hit_censored": leak_test([r for r in pw_rows if r["side"] == "hit"],
                                           "pw", "target_censored", rng),
            "leak_pit_censored": leak_test([r for r in pw_rows if r["side"] == "pit"],
                                           "pw", "target_censored", rng),
        }
    }

    # top movers, for the repair spec
    movers = sorted(
        ({"player_key": r["player_key"], "asof_date": r["asof_date"], "side": r["side"],
          "kind": r["kind"], "baseline": r["baseline"],
          "asof_all": r["arms"]["asof_all"],
          "delta": round((r["arms"]["asof_all"] or r["baseline"]) - r["baseline"], 3)}
         for r in clean if r["arms"].get("asof_all") is not None),
        key=lambda d: -abs(d["delta"]))[:25]

    art = {
        # MUST be "generated_at": model_registry._artifact_date only reads
        # generated_at / run_at / fit_date / as_of / date. Any other spelling
        # makes this artifact undated to the freshness map, which then falls
        # back to file mtime, which the deploy box rewrites nightly via
        # `git checkout -- .`.
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "lane": "D1",
        "gate_doc": "docs/efv-2026-08-07b/CONSENSUS_CONTAMINATION.md",
        "pre_registered": {
            "tol_fv": TOL, "bar_fidelity_pct": BAR_FIDELITY_PCT,
            "bar_pct_ge_0p5_fv": BAR_PCT_HALF_FV,
            "bar_mean_abs_affected_fv": BAR_MEAN_ABS,
            "n_bootstrap": N_BOOT, "seed": SEED,
        },
        "inputs": {
            "n_snapshots": len(snaps),
            "n_matrix_rows": len(targets),
            "n_asof_dates": len(asof_dates),
            "dropped_off_pairs_full_corpus": len(dropped_full),
            "adopt_normalized_consensus": C.ADOPT_NORMALIZED_CONSENSUS,
            "single_source_k": C.SINGLE_SOURCE_K,
            "grade_norm_min_n": GN._MIN_N,
        },
        "fidelity": fidelity,
        "fidelity_replay": fidelity_replay,
        "c2_detector": {
            "shipped_detector_pairs_full_corpus": len(dropped_full),
            "corrected_detector_pairs_full_corpus": len(dropped_fixed_full),
            "shipped_requires": "'_org_' in interval_label (consensus.py:1001)",
            "occurrences_of_legacy_slug_in_corpus": sum(
                1 for s in snaps if s.interval_label and "_org_" in s.interval_label),
            "occurrences_of_human_org_label_in_corpus": sum(
                1 for s in snaps if _org_slug(s.interval_label) is not None),
            "note": ("The legacy slug occurs ZERO times, so the shipped detector returns "
                     "the empty set and the (fv+30)/2 drop-off shrink at "
                     "consensus.py:606-636 NEVER FIRES in production."),
        },
        "channels": channels,
        "pairwise": pairwise,
        "repair_prototype": repair_proto,
        "top_movers_asof_all": movers,
        "d16": dict(
            d16_collisions(pruned, pruned),
            matrix_impact={
                "n_matrix_rows_whose_asof_point_is_not_the_player_own": len(unjoined),
                "n_matrix_rows_whose_value_the_merge_changed": len(r_bad),
                "total_matrix_rows_touched": len(unjoined) + len(r_bad),
                "of_matrix_rows": len(targets),
                "mechanism": ("consensus.py:1381-1391 pools points across the merged "
                              "keys and _asof_point (efv_dataset.py:409-418) then "
                              "selects one; when the merged-in key owns the point at "
                              "that date, the training row's consensus_fv_raw is a "
                              "DIFFERENT player's grade."),
                "worked_examples": [
                    {"matrix_key": "josh_smith__sa3009923", "asof_date": "2022-02-24",
                     "kind": "debuted",
                     "value_came_from": "josh_smith (fangraphs FV 50.0, org TEX)"},
                    {"matrix_key": "carlos_sanchez", "asof_date": "2026-08-07",
                     "kind": "bust",
                     "value_came_from": ("carlos_sanchez_801522 (performance_ingest "
                                         "FV 35.0, org MIA); the Reds prospect's own "
                                         "point is FV 45.0, org CIN")},
                    {"matrix_key": "luis_meza", "asof_date": "2023-08-01",
                     "kind": "bust",
                     "value_came_from": "luis_meza__sa3018423 (fangraphs FV 35.0, org TOR)"},
                ],
            }),
        "d5_hygiene": {
            "apply_shrinkage_production_callers": 0,
            "compute_prior_mean_fv_production_callers": 0,
            "only_importer": "test_consensus.py:24",
            "constants_inert": ["DEFAULT_SHRINKAGE_K", "DEFAULT_N_FULL", "FALLBACK_PRIOR_FV"],
            "constants_lines": "consensus.py:127-129",
            "note": ("Grepped tree-wide. The three constants appear only as defaults on "
                     "apply_shrinkage/compute_prior_mean_fv and on three build_timeseries "
                     "kwargs (consensus.py:1159-1161) whose names never recur in the body. "
                     "The docstring at consensus.py:1173-1180 is accurate."),
        },
        "runtime_sec": round(time.time() - t0, 1),
    }
    OUT.write_text(json.dumps(art, indent=2), encoding="utf-8")
    print(f"wrote {OUT}  ({art['runtime_sec']}s)", flush=True)


def _count(it):
    d = defaultdict(int)
    for x in it:
        d[str(x)] += 1
    return d


if __name__ == "__main__":
    main()
