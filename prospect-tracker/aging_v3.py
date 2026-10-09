# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Aging v3: the one aging service (Part 9, PLAN section 9.3; registered in
docs/AGING_V3_GATE.md, which governs every choice here).

One fitted object, many consumers. ``fit(corpus, max_season, cfg, *, sidecar)``
returns an ``AgingModel`` whose methods are the only age adjustment this
program adds:

    rate_delta(side, comp, age, bucket=None, archetype=None)   the war_rate / pt delta into ``age``
    pt_next(side, role, pt_prev, age, bucket=None, health_z=None)  the next-season exposure
    level(side, age, bucket=None, archetype=None)             relative WAR level, peak 1.0, floor 0.25
    shape(side, debut_age, n_years, bucket=None, reliever=False)  mean-1.0 window shape (prospects)
    factor(age_now, yr_offset, side, bucket=None)             level(age + k) / level(age)
    component_curve(side, comp, bucket=None)                  the v2 component curves, unchanged
    meta                                                      version, provider, corpus_sig, ...

Every ladder arm (T playing time, S rate estimator, P positional buckets, R
skill archetypes) and the health family H are configurations of ONE config
dict (``default_config()``), and NO arm is active by default: with the default
config every method reproduces the incumbent v2 engine exactly (``rate_delta``
is ``fa_projection.curve_delta`` on the v2 curves, ``pt_next`` is the v2
additive pt step), so a consumer that selects ``aging="v3"`` against the dark
default moves nothing.

Selection is CALL-SCOPED, never a module global (the ``use_def`` precedent in
``fa_projection.fitted_models``): the consumer doors carry ``aging="v2"|"v3"``
with ``"v2"`` the default everywhere. The yaml block ``aging_v3`` in
fa_config.yaml holds one flag per consumer (``consumer_aging(name)`` reads it
at call time) and the ``health`` flag; all default false.

The fit cache is versioned, never deleted:
``.cache/aging_v3_fits_{max_season}_{first}_{last}_{sig}_{AGING_V3_VERSION}_{cfg8}.pkl``
where ``AGING_V3_VERSION`` carries a hash of the fit function's source (a test
recomputes it) and ``cfg8`` a hash of the config block plus the bucket and
archetype definitions. The incumbent ``fa_fits_*`` names are untouched and
``.cache/fa_corpus.pkl`` is never written here.

Bans enforced here (gate section 15): no archetype window containing its start
season (``fit`` raises); the K%, BB%, ISO, BABIP and HR component curves are the
v2 curves under every arm; no pooled side-free age correction.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import math
import pickle
from collections import defaultdict
from pathlib import Path

import fa_class
import fa_projection as fp

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
CACHE_DIR = fp.CACHE_DIR
SERVED_CURVES_PATH = ROOT / "data" / "aging_v3_curves.json"
PROVIDER_REQUIRED = "fwar"

# ---------------------------------------------------------------------------
# Registered definitions (docs/AGING_V3_GATE.md section 5)
# ---------------------------------------------------------------------------

CONSUMERS = ("proj_display", "team_outlook", "fa_pricing", "prospect_surplus",
             "contract_tail", "trade_fallback", "fantasy")
ARMS = ("T", "S", "P", "R")
SIDES = ("hit", "pit")

HIT_BUCKETS = ("C", "SS", "2B/3B", "CF", "LF/RF", "1B", "DH")
PIT_BUCKETS = ("SP", "RP")
HIT_PARENT = "HALL"           # the pooled hitter curve, parent of EVERY hitter bucket
PIT_PARENT = "PALL"           # the pooled pitcher curve, parent of SP and RP
PARENT = {"hit": HIT_PARENT, "pit": PIT_PARENT}
BUCKETS = {"hit": HIT_BUCKETS, "pit": PIT_BUCKETS}

# The registered bucket map (AG-Q1): a StatsAPI / board position abbreviation to
# its bucket. IF, UT, TWP, X (Unknown), P and a missing position map to None, the
# pooled side curve. A two-way player's HITTING side is DH (set by the caller,
# who knows the player is two-sided); his pitching side is SP or RP by role.
POSITION_BUCKET = {
    "C": "C", "SS": "SS", "2B": "2B/3B", "3B": "2B/3B", "CF": "CF",
    "LF": "LF/RF", "RF": "LF/RF", "OF": "LF/RF", "1B": "1B", "DH": "DH",
    "SP": "SP", "RP": "RP", "SIRP": "RP", "MIRP": "RP", "CL": "RP",
}
POOLED_POSITIONS = ("IF", "UT", "TWP", "X", "P", "RHP", "LHP", "")

HIT_ARCHETYPES = ("OLD_SKILLS", "YOUNG_SKILLS", "NEUTRAL")
PIT_ARCHETYPES = ("POWER", "COMMAND", "NEUTRAL")
ARCHETYPES = {"hit": HIT_ARCHETYPES, "pit": PIT_ARCHETYPES}
NEUTRAL = "NEUTRAL"
# Family (a), the exact rules over the out-of-window pooled z-scores and run rates.
ARCHETYPE_RULES = {
    "hit": {"old_iso_z": 0.75, "old_bb_z": 0.75, "old_bsr600_max": 0.0,
            "young_bsr600": 2.0, "young_k_z": -0.75, "young_fld600": 4.0},
    "pit": {"power_k_z": 0.75, "command_bb_z": -0.75, "command_k_z_below": 0.75},
}

PER = {"hit": 600.0, "pit": 250.0}          # the engine's WAR rate units
EXPO_KEY = {"hit": "pa", "pit": "bf"}
# ARM T tiers: regular if pt_prev >= the floor, else part (gate section 5).
TIER_FLOOR = {("hit", "C"): 450.0, ("hit", "H"): 450.0,
              ("pit", "SP"): 500.0, ("pit", "RP"): 200.0}
CAP_PERCENTILE = 99.5
MIN_MULTIPLIER = 0.25
HEALTH_FEATURES = ("il_days", "il_stints", "il60", "tj_prior", "age_x_il_days")
HEALTH_CLIP = (0.80, 1.05)
ROUND = 5                                   # the v2 rounding of every stored delta


class AgingV3Unavailable(RuntimeError):
    """aging="v3" was selected where no v3 model can serve."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def default_config() -> dict:
    """The one config dict. NO arm is active; every knob is the incumbent
    value (lambda 1.0, the 3-age moving average), so a fit under this config
    reproduces v2 and the dark build moves nothing."""
    return {
        "arms": {"T": False, "S": False, "P": False, "R": False},
        "health": False,
        # AG-Q5 'Fix both now': the comparator carries the PT cap, computed
        # call-scoped (gate section 4). Off here; the lab passes it.
        "pt_cap": False,
        "T": {"min_pool": 12},
        "S": {"lambda": 1.0, "smoother": "ma3", "penalty": 4},
        "P": {"k": 200},
        "R": {"k": 400, "window": [-3, -1], "min_seasons": 2,
              "min_pa": 600, "min_bf": 500, "z_floor_pa": 100, "z_floor_bf": 70},
        "H": {"alpha": 1.0, "clip": list(HEALTH_CLIP)},
    }


def _merge(base: dict, over: dict | None) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def normalize_config(cfg: dict | None) -> dict:
    """``default_config()`` with ``cfg`` merged over it and the arm flags coerced
    to bool. Raises if the ARM R window contains the pair's start season (offset
    0 or later): the ISO-cohort lesson made into a rule (gate section 15)."""
    out = _merge(default_config(), cfg)
    out["arms"] = {a: bool(out["arms"].get(a, False)) for a in ARMS}
    out["health"] = bool(out.get("health", False))
    out["pt_cap"] = bool(out.get("pt_cap", False))
    lo, hi = (int(x) for x in out["R"]["window"])
    if hi >= 0 or lo > hi:
        raise ValueError(f"ARM R window {out['R']['window']} contains the pair's "
                         "start season (offsets must be strictly negative)")
    return out


def config_hash(cfg: dict) -> str:
    """cfg8: eight hex chars over the normalized config block AND the bucket
    and archetype definitions, so a changed definition re-keys the cache."""
    blob = json.dumps({"cfg": normalize_config(cfg), "buckets": BUCKETS,
                       "parents": PARENT, "position_bucket": POSITION_BUCKET,
                       "pooled": POOLED_POSITIONS, "archetypes": ARCHETYPES,
                       "rules": ARCHETYPE_RULES, "tiers": {f"{k[0]}:{k[1]}": v
                                                           for k, v in TIER_FLOOR.items()}},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:8]


def yaml_block() -> dict:
    """The ``aging_v3`` block of fa_config.yaml, read at CALL time (the
    fa_class.get_config precedent), empty when absent."""
    try:
        return dict(fa_class.get_config().get("aging_v3") or {})
    except Exception:   # noqa: BLE001 - a missing block is the dark default
        return {}


def consumer_enabled(name: str) -> bool:
    """One consumer's flag (``aging_v3.consumers.<name>``), False when absent."""
    if name not in CONSUMERS:
        raise KeyError(f"unknown aging v3 consumer {name!r}; one of {CONSUMERS}")
    return bool((yaml_block().get("consumers") or {}).get(name, False))


def consumer_aging(name: str) -> str:
    """The engine a consumer door selects, read at call time: "v3" only when
    its flag is true, else "v2"."""
    return "v3" if consumer_enabled(name) else "v2"


def health_enabled() -> bool:
    return bool(yaml_block().get("health", False))


def active_config() -> dict:
    """The fit config a served v3 consumer uses: the defaults with the yaml
    block's optional ``fit`` sub-block (arms, knobs) merged over them, and the
    ``health`` flag. A flip task writes the sub-block; until then no arm is on."""
    blk = yaml_block()
    cfg = normalize_config(blk.get("fit") or {})
    cfg["health"] = bool(blk.get("health", False))
    return cfg


# ---------------------------------------------------------------------------
# Buckets and archetypes
# ---------------------------------------------------------------------------

def bucket_from_position(position, is_pitcher: bool | None = None,
                         two_way_hitting: bool = False) -> str | None:
    """The registered bucket for a position string, or None for the pooled
    side curve. ``C/1B`` reads its first token; SIRP and RP read RP; IF, UT,
    TWP, X and a missing position read None. ``two_way_hitting`` is the
    caller's statement that this is a two-way player's hitting side, which is
    DH by rule."""
    if two_way_hitting:
        return "DH"
    if position is None:
        return None
    pos = str(position).strip().upper()
    if "/" in pos:
        pos = pos.split("/", 1)[0].strip()
    if pos in POOLED_POSITIONS:
        return None
    b = POSITION_BUCKET.get(pos)
    if b is None:
        return None
    if is_pitcher is True and b not in PIT_BUCKETS:
        return None
    if is_pitcher is False and b in PIT_BUCKETS:
        return None
    return b


def base_role(side: str, bucket: str | None, role: str | None) -> str:
    """The v2 base role a (bucket, role) pair maps to: hit C or H, pit SP or RP."""
    if side == "hit":
        if (role or "").split("|")[0] == "C" or bucket == "C":
            return "C"
        return "H"
    r = (role or "").split("|")[0]
    if r in PIT_BUCKETS:
        return r
    if bucket in PIT_BUCKETS:
        return bucket
    return "SP"


def window_seasons(start_season: int, cfg: dict) -> list[int]:
    """The ARM R window of a pair starting at ``start_season``: seasons t-3 to
    t-1 by the registered offsets, never season t. Raises if the window would
    contain the start season."""
    lo, hi = (int(x) for x in cfg["R"]["window"])
    seasons = [start_season + k for k in range(lo, hi + 1)]
    if any(s >= start_season for s in seasons):
        raise ValueError(f"archetype window {seasons} contains the start season {start_season}")
    return seasons


def _wmean(pairs) -> float | None:
    num = den = 0.0
    for v, w in pairs:
        if v is None or not w:
            continue
        num += v * w
        den += w
    return (num / den) if den > 0 else None


def _wmedian(values: list[tuple[float, float]]) -> float | None:
    """Exposure-weighted median of (value, weight) pairs."""
    vals = [(v, w) for v, w in values if v is not None and w and w > 0]
    if not vals:
        return None
    vals.sort(key=lambda t: t[0])
    total = sum(w for _, w in vals)
    acc = 0.0
    for v, w in vals:
        acc += w
        if acc >= total / 2.0:
            return float(v)
    return float(vals[-1][0])


def _zstats(values: list[float]) -> tuple[float, float]:
    n = len(values)
    if n < 2:
        return (values[0] if values else 0.0), 1.0
    mu = sum(values) / n
    var = sum((v - mu) ** 2 for v in values) / (n - 1)
    return mu, (math.sqrt(var) if var > 0 else 1.0)


def _season_z_tables(corpus: dict, cfg: dict, max_season: int | None) -> dict:
    """{side: {season: {comp: (mean, sd)}}} of the REGRESSED rates over the
    season's MLB players at or above the pair floor (completion C7)."""
    reg_k = fp._pcfg()["regression_k"]
    out = {"hit": {}, "pit": {}}
    for side in SIDES:
        comps = ("k_pct", "bb_pct", "iso") if side == "hit" else ("k_pct", "bb_pct")
        floor = cfg["R"]["z_floor_pa"] if side == "hit" else cfg["R"]["z_floor_bf"]
        ek = EXPO_KEY[side]
        by_season: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for r in corpus[side]:
            if max_season is not None and r["season"] > max_season:
                continue
            e = r.get(ek) or 0
            if e < floor:
                continue
            for comp in comps:
                v = _regressed_rate(r, side, comp, corpus["league"], reg_k)
                if v is not None:
                    by_season[r["season"]][comp].append(v)
        out[side] = {s: {c: _zstats(v) for c, v in comps_v.items()}
                     for s, comps_v in by_season.items()}
    return out


def _regressed_rate(r: dict, side: str, comp: str, league: dict, reg_k: dict) -> float | None:
    """A row's rate regressed toward its season league mean at the
    fa_config.yaml ``regression_k`` constant (hit k_pct 60, bb_pct 120, iso 160;
    pit k_pct 70, bb_pct 170)."""
    v = r.get(comp)
    if v is None:
        return None
    lg = league.get(r["season"]) or {}
    lg_key = comp if side == "hit" else {"k_pct": "p_k_pct", "bb_pct": "p_bb_pct"}[comp]
    lg_v = lg.get(lg_key)
    if lg_v is None:
        return None
    e = r.get(EXPO_KEY[side]) or 0
    k = float(reg_k["hit" if side == "hit" else "pit"][comp])
    return (v * e + lg_v * k) / (e + k) if (e + k) > 0 else lg_v


def assign_archetype(side: str, start_season: int, seasons: dict[int, dict],
                     sidecar_rows: dict, ztab: dict, cfg: dict, league: dict,
                     *, strict_parts: bool = False) -> tuple[str, list[int]]:
    """The archetype of a pair starting at ``start_season`` from the window
    seasons ONLY (t-3 to t-1), pooled over at least ``min_seasons`` seasons with
    exposure and at least 600 PA / 500 BF, each rate regressed then z-scored
    within its season, the z pooled exposure-weighted. Returns (archetype,
    the window seasons read). NEUTRAL where the window is too thin. With
    ``strict_parts`` a hitter window season with exposure whose run parts the
    vintage does not carry raises (the gate's 'run parts absent' stop)."""
    window = window_seasons(start_season, cfg)
    ek = EXPO_KEY[side]
    rows = [(s, seasons[s]) for s in window if s in seasons and (seasons[s].get(ek) or 0) > 0]
    min_expo = cfg["R"]["min_pa"] if side == "hit" else cfg["R"]["min_bf"]
    if len(rows) < int(cfg["R"]["min_seasons"]) or sum(r.get(ek) or 0 for _, r in rows) < min_expo:
        return NEUTRAL, window
    reg_k = fp._pcfg()["regression_k"]
    comps = ("k_pct", "bb_pct", "iso") if side == "hit" else ("k_pct", "bb_pct")
    z = {}
    for comp in comps:
        pairs = []
        for s, r in rows:
            st = (ztab.get(side) or {}).get(s, {}).get(comp)
            v = _regressed_rate(r, side, comp, league, reg_k)
            if st is None or v is None:
                continue
            pairs.append(((v - st[0]) / st[1], r.get(ek) or 0))
        z[comp] = _wmean(pairs)
    rules = ARCHETYPE_RULES[side]
    if side == "pit":
        kz, bz = z.get("k_pct"), z.get("bb_pct")
        if kz is None or bz is None:
            return NEUTRAL, window
        if kz >= rules["power_k_z"]:
            return "POWER", window
        if bz <= rules["command_bb_z"] and kz < rules["command_k_z_below"]:
            return "COMMAND", window
        return NEUTRAL, window
    # hitters: run parts per 600 PA over the window seasons (the frozen vintage)
    pa = bsr = fld = 0.0
    parts_seen = False
    for s, r in rows:
        sc = sidecar_rows.get((r.get("mlbam"), s)) or {}
        if sc.get("bsr") is None or sc.get("fld") is None:
            if strict_parts:
                raise ValueError(f"run parts absent for ({r.get('mlbam')}, {s}): "
                                 "BLOCKER: other run parts absent")
            continue
        parts_seen = True
        pa += r.get("pa") or 0
        bsr += float(sc["bsr"])
        fld += float(sc["fld"])
    kz, bz, iz = z.get("k_pct"), z.get("bb_pct"), z.get("iso")
    if kz is None or bz is None or iz is None or not parts_seen or pa <= 0:
        return NEUTRAL, window
    bsr600, fld600 = bsr / pa * 600.0, fld / pa * 600.0
    old = (iz >= rules["old_iso_z"] or bz >= rules["old_bb_z"]) and bsr600 <= rules["old_bsr600_max"]
    young = (bsr600 >= rules["young_bsr600"] or kz <= rules["young_k_z"]
             or fld600 >= rules["young_fld600"])
    if old and not young:
        return "OLD_SKILLS", window
    if young and not old:
        return "YOUNG_SKILLS", window
    return NEUTRAL, window


# ---------------------------------------------------------------------------
# The estimator (the incumbent delta method, generalized to cells)
# ---------------------------------------------------------------------------

def _pair_rows(corpus: dict, side: str, max_season: int | None) -> tuple[list[dict], dict]:
    """The rows the v2 fit sees (age in range, pair lands at or before
    ``max_season``) and the per-player season map."""
    cfg = fp._pcfg()
    a_lo, a_hi = cfg["age_range"]
    rows = [r for r in corpus[side] if r.get("age") and a_lo <= r["age"] <= a_hi
            and (max_season is None or r["season"] + 1 <= max_season)]
    by_player: dict[int, dict[int, dict]] = {}
    for r in rows:
        if r.get("mlbam") is not None:
            by_player.setdefault(r["mlbam"], {})[r["season"]] = r
    return rows, by_player


def _league_rates(rows: list[dict], side: str) -> dict[int, float]:
    """League WAR rate per exposure unit per season, the v2 shrink target."""
    per = PER[side]
    ek = EXPO_KEY[side]
    acc_w: dict[int, float] = defaultdict(float)
    acc_e: dict[int, float] = defaultdict(float)
    for r in rows:
        if r.get("war") is not None and (r.get(ek) or 0) > 0:
            acc_w[r["season"]] += r["war"]
            acc_e[r["season"]] += r[ek]
    return {s: acc_w[s] / e * per for s, e in acc_e.items() if e > 0}


def _value(r: dict, side: str, comp: str, lg_rate: dict, min_expo: float, k_reg: float):
    """The v2 value getter: war_rate regressed toward the season league rate,
    pt the exposure, a component its rate; bsr per 600 PA and fld per 1,000
    innings (the U5 run-part curves)."""
    ek = EXPO_KEY[side]
    per = PER[side]
    if comp == "war_rate":
        w = r.get("war")
        e = r.get(ek) or 0
        if w is None or e < min_expo:
            return None
        raw = w / e * per
        lg = lg_rate.get(r["season"], 0.0)
        return (raw * e + lg * k_reg) / (e + k_reg)
    if comp == "pt":
        return r.get(ek)
    if comp == "bsr":
        v, e = r.get("_bsr"), r.get("pa") or 0
        return None if v is None or e <= 0 else float(v) / e * 600.0
    if comp == "fld":
        v, inn = r.get("_fld"), r.get("_inn")
        return None if v is None or not inn or inn <= 0 else float(v) / float(inn) * 1000.0
    return r.get(comp)


def _accumulate(by_player: dict, side: str, comp: str, cells_of, lg_rate: dict,
                min_expo: float, k_reg: float) -> dict:
    """{cell: {age: slot}} of delta sums, harmonic weights, the age-t pool and
    the stayers, exactly the v2 bookkeeping, for every cell ``cells_of(r)``
    returns for a row (its own cell and its parents)."""
    ek = EXPO_KEY[side]
    acc: dict[str, dict[int, dict]] = defaultdict(dict)
    for mlbam, seasons in by_player.items():
        for s, r in seasons.items():
            if (r.get(ek) or 0) < min_expo:
                continue
            v0 = _value(r, side, comp, lg_rate, min_expo, k_reg)
            if v0 is None:
                continue
            nxt = seasons.get(s + 1)
            ok = bool(nxt) and (nxt.get(ek) or 0) >= min_expo
            v1 = _value(nxt, side, comp, lg_rate, min_expo, k_reg) if ok else None
            a = r["age"] + 1                                   # delta lands at age t+1
            for cell in cells_of(r):
                slot = acc[cell].setdefault(a, {"d": 0.0, "w": 0.0, "pool": [], "stay": [],
                                               "n_pool": 0, "n_stay": 0,
                                               "e0": 0.0, "e1": 0.0, "lg0_pool": [], "lg0_stay": []})
                slot["pool"].append(v0)
                slot["n_pool"] += 1
                slot["lg0_pool"].append(math.log(r[ek]))
                if not ok or v1 is None:
                    continue
                w = 2.0 / (1.0 / r[ek] + 1.0 / nxt[ek])          # harmonic exposure weight
                slot["d"] += (v1 - v0) * w
                slot["w"] += w
                slot["stay"].append(v0)
                slot["n_stay"] += 1
                slot["e0"] += r[ek]
                slot["e1"] += nxt[ek]
                slot["lg0_stay"].append(math.log(r[ek]))
    return acc


def _corrected(acc_cell: dict, side: str, comp: str, lam: float, min_pool: int) -> dict:
    """The survivorship-corrected per-age deltas of one cell (v2 form):
    raw + harm * lambda * attrition * |selection gap|, rounded as v2 rounds."""
    harm = fp.HARM_DIR[side].get(comp, -1)
    curve = {}
    for a, slot in sorted(acc_cell.items()):
        if slot["w"] <= 0 or slot["n_pool"] < min_pool:
            continue
        raw_delta = slot["d"] / slot["w"]
        attrition = 1.0 - slot["n_stay"] / slot["n_pool"]
        sel_gap = ((sum(slot["stay"]) / len(slot["stay"]))
                   - (sum(slot["pool"]) / len(slot["pool"]))) if slot["stay"] else 0.0
        corrected = raw_delta + harm * lam * attrition * abs(sel_gap)
        curve[a] = {"delta": round(corrected, ROUND), "raw": round(raw_delta, ROUND),
                    "n": slot["n_stay"], "attrition": round(attrition, 3),
                    "w": round(slot["w"], 3)}
    return curve


def _nearest(curve: dict, age: int):
    if not curve:
        return None
    a = min(curve, key=lambda x: abs(x - age))
    return curve[a]


def _shrink(child: dict, parent: dict, k: float, key: str = "delta") -> dict:
    """``delta_b(a) = w * delta_b_raw(a) + (1 - w) * delta_parent(a)``,
    ``w = n_b(a) / (n_b(a) + k)``, over every age the parent supports; an age the
    child lacks takes the parent's value (w = 0). The parent's nearest age
    stands in where it lacks the child's age."""
    out = {}
    ages = sorted(set(parent) | set(child))
    for a in ages:
        p = parent.get(a) or _nearest(parent, a)
        c = child.get(a)
        if p is None and c is None:
            continue
        if p is None:
            out[a] = dict(c, w_shrink=1.0)
            continue
        n = float(c["n"]) if c else 0.0
        w = n / (n + float(k)) if (n + k) > 0 else 0.0
        val = w * (c[key] if c else 0.0) + (1.0 - w) * p[key]
        out[a] = {key: round(val, ROUND), "raw": round((c or p)["raw"], ROUND),
                  "n": int(n), "attrition": (c or p)["attrition"],
                  "w": (c or p).get("w", 0.0), "w_shrink": round(w, 4)}
    return out


def _smooth(curve: dict, smoother: str, penalty: float, key: str = "delta") -> dict:
    """The smoother: ``ma3`` is the incumbent 3-age moving average over the
    ages present; ``pen`` a second-difference penalized fit of the per-age
    values weighted by their pair weights, over the consecutive age run."""
    ages = sorted(curve)
    if not ages:
        return curve
    if smoother == "ma3":
        for a in ages:
            vals = [curve[x][key] for x in (a - 1, a, a + 1) if x in curve]
            curve[a][key + "_smooth"] = round(sum(vals) / len(vals), ROUND)
        return curve
    if smoother != "pen":
        raise ValueError(f"unknown smoother {smoother!r}")
    import numpy as np
    n = len(ages)
    y = np.array([curve[a][key] for a in ages], dtype=float)
    wts = np.array([max(float(curve[a].get("w", 1.0)), 1e-9) for a in ages], dtype=float)
    wts = wts / wts.mean()
    A = np.diag(wts)
    if n >= 3:
        D = np.zeros((n - 2, n))
        for i in range(n - 2):
            D[i, i], D[i, i + 1], D[i, i + 2] = 1.0, -2.0, 1.0
        # gaps in the age run: a second difference across a gap is not penalized
        keep = [i for i in range(n - 2) if ages[i + 2] - ages[i] == 2]
        D = D[keep] if keep else np.zeros((0, n))
        A = A + float(penalty) * D.T @ D
    f = np.linalg.solve(A, wts * y)
    for i, a in enumerate(ages):
        curve[a][key + "_smooth"] = round(float(f[i]), ROUND)
    return curve


def _rho_corrected(acc_cell: dict, lam: float, min_pool: int) -> dict:
    """ARM T: the exposure-weighted mean ratio of next to current exposure
    over surviving pairs (sum e1 / sum e0), the v2 survivorship form applied to
    log rho with the selection gap in log exposure."""
    curve = {}
    for a, slot in sorted(acc_cell.items()):
        if slot["n_stay"] <= 0 or slot["e0"] <= 0 or slot["n_pool"] < min_pool:
            continue
        rho_raw = slot["e1"] / slot["e0"]
        if rho_raw <= 0:
            continue
        attrition = 1.0 - slot["n_stay"] / slot["n_pool"]
        gap = (sum(slot["lg0_stay"]) / len(slot["lg0_stay"])
               - sum(slot["lg0_pool"]) / len(slot["lg0_pool"])) if slot["lg0_stay"] else 0.0
        log_rho = math.log(rho_raw) - lam * attrition * abs(gap)      # HARM -1 for pt
        curve[a] = {"delta": round(log_rho, ROUND), "raw": round(math.log(rho_raw), ROUND),
                    "n": slot["n_stay"], "attrition": round(attrition, 3),
                    "w": round(slot["e0"], 3)}
    return curve


def _caps(corpus: dict, max_season: int | None) -> dict:
    """The 99.5th percentile of single-season exposure by side and base role
    over corpus rows with season <= max_season: computed by the fit, never
    tuned (gate section 4)."""
    import numpy as np
    out = {}
    for side in SIDES:
        ek = EXPO_KEY[side]
        pools: dict[str, list[float]] = defaultdict(list)
        for r in corpus[side]:
            if max_season is not None and r["season"] > max_season:
                continue
            e = r.get(ek) or 0
            if e > 0:
                pools[base_role(side, None, r.get("role"))].append(float(e))
        for role, vals in pools.items():
            out[f"{side}:{role}"] = float(np.percentile(np.array(vals), CAP_PERCENTILE))
    return out


def _ref_levels(corpus: dict, side: str, cells_of, max_season: int | None) -> dict:
    """Per cell: R_ref, the exposure-weighted median raw WAR rate of
    regular-tier rows, and E_ref, their exposure-weighted median exposure."""
    ek = EXPO_KEY[side]
    per = PER[side]
    rates: dict[str, list] = defaultdict(list)
    expos: dict[str, list] = defaultdict(list)
    for r in corpus[side]:
        if max_season is not None and r["season"] > max_season:
            continue
        e = r.get(ek) or 0
        br = base_role(side, None, r.get("role"))
        if e < TIER_FLOOR[(side, br)] or r.get("war") is None:
            continue
        for cell in cells_of(r):
            rates[cell].append((r["war"] / e * per, e))
            expos[cell].append((e, e))
    return {cell: {"R_ref": _wmedian(rates[cell]), "E_ref": _wmedian(expos[cell])}
            for cell in rates}


def fit_source_hash() -> str:
    """sha256 over the source of the fit function and the estimator helpers
    it calls; the cache key carries its first eight hex chars."""
    h = hashlib.sha256()
    for fn in _FIT_SOURCE:
        h.update(inspect.getsource(fn).encode("utf-8").replace(b"\r\n", b"\n"))
    return h.hexdigest()[:8]


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------

class AgingModel:
    """One fitted aging service. Built by ``fit``; serialized by ``to_dict`` /
    ``from_dict`` (the committed ``data/aging_v3_curves.json`` of a flip)."""

    def __init__(self, *, cfg: dict, v2: dict, cells: dict, rho: dict, caps: dict,
                 refs: dict, extra: dict, assign: dict, health: dict, meta: dict):
        self.cfg = cfg
        self.v2 = v2                      # the incumbent curves dict (fit_aging_curves)
        self.cells = cells                # {side: {cell: {comp: {age: {...delta_smooth}}}}}
        self.rho = rho                    # {side: {cell: {tier: {age: {...delta_smooth (log rho)}}}}}
        self.caps = caps                  # {"side:role": cap}
        self.refs = refs                  # {side: {cell: {R_ref, E_ref}}}
        self.extra = extra                # {"bsr": {role: curve}, "fld": {role: curve}}
        self.assign = assign              # {side: {"bucket": {(mlbam, season): b}, "archetype": {...}}}
        self.health = health              # {"gamma": [...] | None, "z": {season: {feat: (mu, sd)}}}
        self.meta = meta

    # ---- arms -------------------------------------------------------------
    def arm_active(self, arm: str) -> bool:
        return bool(self.cfg["arms"].get(arm, False))

    @property
    def any_rate_arm(self) -> bool:
        return any(self.arm_active(a) for a in ("S", "P", "R"))

    # ---- cell resolution --------------------------------------------------
    def _cell(self, side: str, bucket: str | None, archetype: str | None,
              role: str | None) -> str:
        if self.arm_active("P"):
            cell = bucket if bucket in BUCKETS[side] else PARENT[side]
        else:
            cell = base_role(side, bucket, role)
            # the v2 profile cohort ('SP|pwr') where the role names one and the cell exists
            if role and "|" in role:
                cand = f"{cell}|{role.split('|', 1)[1]}"
                if cand in self.cells.get(side, {}):
                    cell = cand
        if (self.arm_active("R") and archetype and archetype != NEUTRAL
                and f"{cell}|{archetype}" in self.cells.get(side, {})):
            cell = f"{cell}|{archetype}"
        return cell

    def bucket_of(self, mlbam, season: int, side: str, role: str | None = None) -> str | None:
        """The sidecar-assigned bucket of (mlbam, season); for pitchers the role
        when no assignment exists."""
        b = ((self.assign.get(side) or {}).get("bucket") or {}).get((mlbam, season))
        if b is None and side == "pit":
            return base_role(side, None, role)
        return b

    def archetype_of(self, mlbam, start_season: int, side: str) -> str:
        """The archetype of a pair starting at ``start_season`` (window t-3 to
        t-1), NEUTRAL when none is assigned."""
        return ((self.assign.get(side) or {}).get("archetype") or {}).get(
            (mlbam, start_season), NEUTRAL)

    # ---- the API ----------------------------------------------------------
    def rate_delta(self, side: str, comp: str, age: int, bucket: str | None = None,
                   archetype: str | None = None, *, role: str | None = None) -> float:
        """The smoothed delta applied moving INTO ``age`` for ``war_rate`` or
        ``pt``; any other component is the v2 component curve, unchanged under
        every arm. With no rate arm active this IS ``fa_projection.curve_delta``
        on the v2 curves (the base role, or the profile role the caller names)."""
        if comp not in ("war_rate", "pt") or not self.any_rate_arm:
            r = role or base_role(side, bucket, None)
            return fp.curve_delta(self.v2, side, r, comp, int(age))
        cell = self._cell(side, bucket, archetype, role)
        c = ((self.cells.get(side) or {}).get(cell) or {}).get(comp) or {}
        if not c:
            c = ((self.cells.get(side) or {}).get(PARENT[side]) or {}).get(comp) or {}
        if not c:
            return 0.0
        slot = _nearest(c, int(age))
        return float(slot.get("delta_smooth", slot["delta"]))

    def cap(self, side: str, role: str | None, bucket: str | None = None) -> float | None:
        return self.caps.get(f"{side}:{base_role(side, bucket, role)}")

    def tier(self, side: str, role: str | None, pt_prev: float, bucket: str | None = None) -> str:
        return "regular" if pt_prev >= TIER_FLOOR[(side, base_role(side, bucket, role))] else "part"

    def rho_at(self, side: str, role: str | None, tier: str, age: int,
               bucket: str | None = None) -> float:
        cell = self._cell(side, bucket, None, role)
        c = (((self.rho.get(side) or {}).get(cell) or {}).get(tier) or {})
        if not c:
            c = (((self.rho.get(side) or {}).get(PARENT[side]) or {}).get(tier) or {})
        if not c:
            return 1.0
        slot = _nearest(c, int(age))
        return math.exp(float(slot.get("delta_smooth", slot["delta"])))

    def health_multiplier(self, health_z) -> float:
        """exp(gamma . z) clipped to the registered band; 1.0 without a fitted
        gamma, without the health arm, or without features."""
        gamma = self.health.get("gamma")
        if not self.cfg.get("health") or gamma is None or health_z is None:
            return 1.0
        lo, hi = self.cfg["H"]["clip"]
        s = sum(float(g) * float(z) for g, z in zip(gamma, health_z))
        return min(float(hi), max(float(lo), math.exp(s)))

    def pt_next(self, side: str, role: str | None, pt_prev: float, age: int,
                bucket: str | None = None, health_z=None) -> float:
        """The next-season exposure. ARM T off: the v2 additive pt step
        (``pt_prev + delta``); ARM T on: ``min(cap, pt_prev * rho[tier, age])``.
        The comparator cap applies under ``pt_cap``; the health multiplier under
        the health flag. Floored at 0."""
        cap = self.cap(side, role, bucket)
        if self.arm_active("T"):
            pt = float(pt_prev) * self.rho_at(side, role, self.tier(side, role, pt_prev, bucket),
                                              age, bucket)
            if cap is not None:
                pt = min(cap, pt)
        else:
            pt = float(pt_prev) + self.rate_delta(side, "pt", age, bucket=bucket, role=role)
            if self.cfg.get("pt_cap") and cap is not None:
                pt = min(cap, pt)
        pt *= self.health_multiplier(health_z)
        return max(0.0, pt)

    def _support(self, side: str, cell: str, comp: str = "war_rate") -> list[int]:
        c = ((self.cells.get(side) or {}).get(cell) or {}).get(comp) or {}
        if not c:
            c = ((self.cells.get(side) or {}).get(PARENT[side]) or {}).get(comp) or {}
        return sorted(c)

    def _level_curve(self, side: str, bucket: str | None, archetype: str | None,
                     role: str | None) -> dict[int, float]:
        """m(a) = (R_ref + C(a)) / max_a (R_ref + C(a)) over the supported ages,
        C(a) the cumulative sum of the cell's smoothed deltas from the youngest
        supported age, floored at MIN_MULTIPLIER."""
        cell = self._cell(side, bucket, archetype, role)
        ages = self._support(side, cell)
        if not ages:
            return {}
        ref = ((self.refs.get(side) or {}).get(cell) or
               (self.refs.get(side) or {}).get(PARENT[side]) or {})
        r_ref = ref.get("R_ref")
        if r_ref is None:
            r_ref = 1.0
        lvl, c = {}, 0.0
        for i, a in enumerate(ages):
            if i > 0:
                c += self.rate_delta(side, "war_rate", a, bucket=bucket, archetype=archetype, role=role)
            lvl[a] = r_ref + c
        top = max(lvl.values())
        if top <= 0:
            return {a: 1.0 for a in ages}
        return {a: max(MIN_MULTIPLIER, v / top) for a, v in lvl.items()}

    def level(self, side: str, age, bucket: str | None = None, archetype: str | None = None,
              *, role: str | None = None) -> float:
        """Relative WAR level at ``age``: peak 1.0, floor 0.25, nearest supported
        age outside the support."""
        curve = self._level_curve(side, bucket, archetype, role)
        if not curve:
            return 1.0
        a = min(curve, key=lambda x: abs(x - float(age)))
        return float(curve[a])

    def factor(self, age_now, yr_offset: int, side: str, bucket: str | None = None) -> float:
        """level(age + k) / level(age): the A5 (trade fallback) replacement."""
        if age_now is None:
            return 1.0
        base = self.level(side, age_now, bucket)
        if base <= 0:
            return 1.0
        return self.level(side, float(age_now) + int(yr_offset), bucket) / base

    def _pt_curve(self, side: str, bucket: str | None, role: str | None) -> dict[int, float]:
        """The regular-tier PT curve relative to its maximum: E_ref walked
        along the cell's pt deltas (ARM T on: the regular-tier rho chain under
        the cap)."""
        cell = self._cell(side, bucket, None, role)
        ages = self._support(side, cell, "pt") or self._support(side, cell)
        if not ages:
            return {}
        ref = ((self.refs.get(side) or {}).get(cell) or
               (self.refs.get(side) or {}).get(PARENT[side]) or {})
        e = ref.get("E_ref") or TIER_FLOOR[(side, base_role(side, bucket, role))]
        cap = self.cap(side, role, bucket)
        path = {}
        for i, a in enumerate(ages):
            if i > 0:
                if self.arm_active("T"):
                    e = e * self.rho_at(side, role, "regular", a, bucket)
                    if cap is not None:
                        e = min(cap, e)
                else:
                    e = max(0.0, e + self.rate_delta(side, "pt", a, bucket=bucket, role=role))
            path[a] = e
        top = max(path.values())
        if top <= 0:
            return {a: 1.0 for a in ages}
        return {a: v / top for a, v in path.items()}

    def shape(self, side: str, debut_age, n_years: int, bucket: str | None = None,
              reliever: bool = False) -> list[float]:
        """level() times the regular-tier PT curve at each age of the window,
        renormalized to mean 1.0 exactly like value_framework._trajectory_shape,
        so the FV-anchored window mean is unchanged and only the timing moves.
        Prospects get a bucket only: never an archetype, never a health term."""
        n = int(n_years)
        if n <= 0:
            return []
        role = ("RP" if reliever else "SP") if side == "pit" else None
        if side == "pit" and bucket not in PIT_BUCKETS:
            bucket = role
        ptc = self._pt_curve(side, bucket, role)
        raw = []
        for k in range(n):
            a = float(debut_age) + k
            lv = self.level(side, a, bucket, role=role)
            if ptc:
                pa = min(ptc, key=lambda x: abs(x - a))
                lv *= ptc[pa]
            raw.append(lv)
        mean = (sum(raw) / n) or 1.0
        return [v / mean for v in raw]

    def component_curve(self, side: str, comp: str, bucket: str | None = None):
        """The v2 component curves (K%, BB%, ISO, BABIP, HR) returned unchanged
        under every arm, by base role ({role: curve}; one curve when a bucket
        names the role). 'bsr' (baserunning runs per 600 PA) and 'fld' (fielding
        runs per 1,000 innings, catcher framing inside) are the U5 curves fitted
        with the incumbent estimator; both hitter-side."""
        if comp in ("bsr", "fld"):
            if side != "hit":
                raise KeyError(f"{comp} is a hitter-side curve")
            table = self.extra.get(comp) or {}
        else:
            comps = fp.HIT_COMPONENTS if side == "hit" else fp.PIT_COMPONENTS
            if comp not in comps:
                raise KeyError(f"unknown component {comp!r} for side {side!r}")
            roles = ("C", "H") if side == "hit" else ("SP", "RP")
            table = {r: ((self.v2.get(side) or {}).get(r) or {}).get(comp) or {} for r in roles}
        if bucket is None:
            return {r: dict(c) for r, c in table.items()}
        return dict(table.get(base_role(side, bucket, None)) or {})

    # ---- health helpers (the lab fits gamma on the H DEV frame) -------------
    def health_features(self, side: str, age, sidecar_rows: dict, tj: dict, mlbam,
                        season: int) -> list[float] | None:
        """Raw features as of the end of ``season``: IL days, stints and 60-day
        placements over t-2..t, tj_prior (pitchers), age x IL days; None when the
        feature window lies outside the transactions coverage."""
        days = stints = il60 = 0.0
        for s in (season - 2, season - 1, season):
            sc = sidecar_rows.get((mlbam, s))
            if sc is None or sc.get("il_days") is None:
                return None
            days += float(sc["il_days"] or 0)
            stints += float(sc["il_stints"] or 0)
            il60 += float(sc.get("il60") or 0)
        tj_prior = float(sum(1 for y in (tj.get(mlbam) or []) if y <= season)) if side == "pit" else 0.0
        return [days, stints, il60, tj_prior, float(age or 0) * days]

    def health_z(self, season: int, feats: list[float] | None) -> list[float] | None:
        """Within-season z-scores from the fit's per-season tables."""
        if feats is None:
            return None
        st = (self.health.get("z") or {}).get(season)
        if not st:
            return None
        return [(f - st[name][0]) / (st[name][1] or 1.0) for f, name in zip(feats, HEALTH_FEATURES)]

    def fit_health_gamma(self, Z: list[list[float]], y: list[float]) -> list[float]:
        """Ridge (alpha from cfg, z-features, no intercept) of log exposure
        ratios on the z-features; stores and returns gamma."""
        import numpy as np
        if not Z:
            self.health["gamma"] = None
            return []
        X = np.asarray(Z, dtype=float)
        t = np.asarray(y, dtype=float)
        alpha = float(self.cfg["H"]["alpha"])
        g = np.linalg.solve(X.T @ X + alpha * np.eye(X.shape[1]), X.T @ t)
        self.health["gamma"] = [float(v) for v in g]
        return self.health["gamma"]

    # ---- serialization ----------------------------------------------------
    def to_dict(self) -> dict:
        def _ages(c):
            return {str(a): v for a, v in c.items()}
        return {
            "meta": self.meta, "cfg": self.cfg, "caps": self.caps,
            "refs": self.refs,
            "v2": self.v2,
            "cells": {s: {cell: {comp: _ages(c) for comp, c in comps.items()}
                          for cell, comps in cells.items()} for s, cells in self.cells.items()},
            "rho": {s: {cell: {tier: _ages(c) for tier, c in tiers.items()}
                        for cell, tiers in cells.items()} for s, cells in self.rho.items()},
            "extra": {comp: {r: _ages(c) for r, c in t.items()} for comp, t in self.extra.items()},
            "assign": {s: {k: {f"{m}|{y}": v for (m, y), v in d.items()} for k, d in a.items()}
                       for s, a in self.assign.items()},
            "health": {"gamma": self.health.get("gamma"),
                       "z": {str(s): v for s, v in (self.health.get("z") or {}).items()}},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AgingModel":
        def _ages(c):
            return {int(a): v for a, v in c.items()}
        cells = {s: {cell: {comp: _ages(c) for comp, c in comps.items()}
                     for cell, comps in cs.items()} for s, cs in (d.get("cells") or {}).items()}
        rho = {s: {cell: {tier: _ages(c) for tier, c in tiers.items()}
                   for cell, tiers in cs.items()} for s, cs in (d.get("rho") or {}).items()}
        extra = {comp: {r: _ages(c) for r, c in t.items()} for comp, t in (d.get("extra") or {}).items()}
        assign = {}
        for s, a in (d.get("assign") or {}).items():
            assign[s] = {}
            for k, dd in a.items():
                out = {}
                for key, v in dd.items():
                    m, y = key.rsplit("|", 1)
                    out[(int(m), int(y))] = v
                assign[s][k] = out
        health = {"gamma": (d.get("health") or {}).get("gamma"),
                  "z": {int(s): v for s, v in ((d.get("health") or {}).get("z") or {}).items()}}
        return cls(cfg=normalize_config(d.get("cfg")), v2=d.get("v2") or {"hit": {}, "pit": {}},
                   cells=cells, rho=rho, caps=d.get("caps") or {}, refs=d.get("refs") or {},
                   extra=extra, assign=assign, health=health, meta=d.get("meta") or {})


# ---------------------------------------------------------------------------
# fit
# ---------------------------------------------------------------------------

def _hit_cells_v2(r: dict, league: dict) -> list[str]:
    """The v2 cell set of a hitter row: its base role, the profile cohort v2
    builds (H only: 'H|pwr', 'H|con'), and the pooled parent."""
    base = "C" if r.get("role") == "C" else "H"
    prof = fp._row_profile(r, "hit", league) if base == "H" else ""
    return [base] + ([f"{base}|{prof}"] if prof else []) + [HIT_PARENT]


def _pit_cells_v2(r: dict, league: dict) -> list[str]:
    base = r.get("role") or "SP"
    prof = fp._row_profile(r, "pit", league)
    return [base] + ([f"{base}|{prof}"] if prof else []) + [PIT_PARENT]


def fit(corpus: dict, max_season: int | None, cfg: dict | None = None, *,
        sidecar: dict | None = None) -> AgingModel:
    """Fit the service on ``corpus`` with pairs landing at or before
    ``max_season`` (the no-lookahead hook) under ``cfg`` (``default_config()``
    merged). ``sidecar`` (aging_v3_sidecar.load) supplies positions, run parts
    and IL features; it is required only when ARM P, ARM R or the health family
    is active, or for the U5 run-part curves (skipped without it).

    The v2 curves are fitted first (``fa_projection.fit_aging_curves``) and are
    the component curves under every arm. The war_rate and pt cells are then
    estimated by the same delta method over the cell set the active arms
    define, shrunk toward the pooled parent with ``n / (n + k)``."""
    cfg = normalize_config(cfg)
    if corpus.get("war_provider") not in (None, PROVIDER_REQUIRED):
        log.warning("aging v3 fit on war_provider %r (the gate requires %r)",
                    corpus.get("war_provider"), PROVIDER_REQUIRED)
    needs_sidecar = cfg["arms"]["P"] or cfg["arms"]["R"] or cfg["health"]
    if needs_sidecar and sidecar is None:
        raise ValueError("ARM P, ARM R and the health family need the sidecar "
                         "(aging_v3_sidecar.load(corpus))")
    sc_rows = (sidecar or {}).get("rows") or {}
    league = corpus["league"]
    pcfg = fp._pcfg()
    lam = float(cfg["S"]["lambda"]) if cfg["arms"]["S"] else float(pcfg["survivorship_lambda"])
    smoother = cfg["S"]["smoother"] if cfg["arms"]["S"] else "ma3"
    penalty = float(cfg["S"]["penalty"])
    min_pool = int(cfg["T"]["min_pool"])
    reg_k = pcfg.get("war_rate_regression") or {"hit_pa": 600, "pit_bf": 350}

    v2 = fp.fit_aging_curves(corpus, max_season=max_season, write=False)

    cells: dict = {"hit": {}, "pit": {}}
    rho: dict = {"hit": {}, "pit": {}}
    refs: dict = {"hit": {}, "pit": {}}
    assign: dict = {"hit": {"bucket": {}, "archetype": {}}, "pit": {"bucket": {}, "archetype": {}}}
    extra: dict = {}
    counts: dict = {}
    ztab = _season_z_tables(corpus, cfg, max_season) if cfg["arms"]["R"] else {}

    for side in SIDES:
        rows, by_player = _pair_rows(corpus, side, max_season)
        min_expo = pcfg["min_exposure_pair"]["pa" if side == "hit" else "bf"]
        k_reg = float(reg_k["hit_pa"] if side == "hit" else reg_k["pit_bf"])
        lg_rate = _league_rates(rows, side)
        parent = PARENT[side]

        # --- the bucket of every fit row (ARM P), from the sidecar ------------
        if cfg["arms"]["P"]:
            for r in rows:
                sc = sc_rows.get((r.get("mlbam"), r["season"])) or {}
                if side == "hit":
                    b = bucket_from_position(sc.get("pos"), False, two_way_hitting=bool(sc.get("two_way")))
                else:
                    b = base_role("pit", None, r.get("role"))
                assign[side]["bucket"][(r.get("mlbam"), r["season"])] = b
        # --- the archetype of every pair start (ARM R), out of window --------
        if cfg["arms"]["R"]:
            for mlbam, seasons in by_player.items():
                for t in seasons:
                    arch, window = assign_archetype(side, t, seasons, sc_rows, ztab, cfg,
                                                    league, strict_parts=True)
                    if any(s >= t for s in window):
                        raise ValueError("a fit row's archetype window contains its start season")
                    assign[side]["archetype"][(mlbam, t)] = arch

        def cells_of(r, _side=side, _parent=parent):
            if cfg["arms"]["P"]:
                b = assign[_side]["bucket"].get((r.get("mlbam"), r["season"]))
                out = ([b] if b else []) + [_parent]
            else:
                out = (_hit_cells_v2(r, league) if _side == "hit" else _pit_cells_v2(r, league))
            if cfg["arms"]["R"]:
                arch = assign[_side]["archetype"].get((r.get("mlbam"), r["season"]), NEUTRAL)
                if arch != NEUTRAL:
                    out = out + [f"{c}|{arch}" for c in out if c != _parent]
            return out

        def _parent_of(cell: str, _parent=parent) -> str | None:
            if cell == _parent:
                return None
            if "|" in cell:
                head, tail = cell.rsplit("|", 1)
                if tail in ARCHETYPES[side]:
                    return head                     # archetype -> its bucket / role
                return head                         # v2 profile cohort -> base role
            return _parent if cfg["arms"]["P"] else None

        for comp in ("war_rate", "pt"):
            acc = _accumulate(by_player, side, comp, cells_of, lg_rate, min_expo, k_reg)
            corr = {cell: _corrected(acc[cell], side, comp, lam, min_pool) for cell in acc}
            done: dict[str, dict] = {}

            def _resolve(cell: str) -> dict:
                if cell in done:
                    return done[cell]
                p = _parent_of(cell)
                if p is None or p not in corr:
                    out = corr[cell]
                else:
                    tail = cell.rsplit("|", 1)[1] if "|" in cell else ""
                    if tail in ARCHETYPES[side]:
                        k = float(cfg["R"]["k"])
                    elif cfg["arms"]["P"]:
                        k = float(cfg["P"]["k"])
                    else:
                        k = None                    # v2 profile cohorts: no shrinkage (v2 form)
                    out = corr[cell] if k is None else _shrink(corr[cell], _resolve(p), k)
                done[cell] = out
                return out

            for cell in corr:
                curve = _smooth({a: dict(v) for a, v in _resolve(cell).items()}, smoother, penalty)
                cells[side].setdefault(cell, {})[comp] = curve
                counts[f"{side}:{cell}:{comp}"] = sum(v["n"] for v in curve.values())

        # --- ARM T: rho by cell and tier --------------------------------------
        if cfg["arms"]["T"]:
            for tier in ("regular", "part"):
                def _tier_cells(r, _tier=tier):
                    br = base_role(side, None, r.get("role"))
                    is_reg = (r.get(EXPO_KEY[side]) or 0) >= TIER_FLOOR[(side, br)]
                    if (_tier == "regular") != is_reg:
                        return []
                    return cells_of(r)
                acc = _accumulate(by_player, side, "pt", _tier_cells, lg_rate, min_expo, k_reg)
                corr = {cell: _rho_corrected(acc[cell], lam, min_pool) for cell in acc}
                for cell in corr:
                    p = _parent_of(cell)
                    base_curve = corr[cell]
                    if p is not None and p in corr and (cfg["arms"]["P"] or
                                                        cell.rsplit("|", 1)[-1] in ARCHETYPES[side]):
                        k = float(cfg["R"]["k"] if cell.rsplit("|", 1)[-1] in ARCHETYPES[side]
                                  else cfg["P"]["k"])
                        base_curve = _shrink(corr[cell], corr[p], k)
                    curve = _smooth({a: dict(v) for a, v in base_curve.items()}, smoother, penalty)
                    rho[side].setdefault(cell, {})[tier] = curve

        refs[side] = _ref_levels(corpus, side, cells_of, max_season)

        # --- U5: the run-part curves, incumbent estimator, hitters only -------
        if side == "hit" and sc_rows:
            rows_x = []
            for r in rows:
                sc = sc_rows.get((r.get("mlbam"), r["season"])) or {}
                rows_x.append(dict(r, _bsr=sc.get("bsr"), _fld=sc.get("fld"), _inn=sc.get("inn")))
            bp: dict[int, dict[int, dict]] = {}
            for r in rows_x:
                if r.get("mlbam") is not None:
                    bp.setdefault(r["mlbam"], {})[r["season"]] = r
            lam_inc = float(pcfg["survivorship_lambda"])
            for comp in ("bsr", "fld"):
                acc = _accumulate(bp, side, comp,
                                  lambda r: ["C" if r.get("role") == "C" else "H"],
                                  lg_rate, min_expo, k_reg)
                extra[comp] = {cell: _smooth({a: dict(v) for a, v in
                                              _corrected(acc[cell], side, comp, lam_inc, 12).items()},
                                             "ma3", penalty)
                               for cell in acc}

    # --- health z tables (within season, across all MLB players with exposure)
    health = {"gamma": None, "z": {}}
    if cfg["health"]:
        tj = (sidecar or {}).get("tj") or {}
        per_season: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        tmp = AgingModel(cfg=cfg, v2=v2, cells=cells, rho=rho, caps={}, refs=refs,
                         extra=extra, assign=assign, health=health, meta={})
        for side in SIDES:
            for r in corpus[side]:
                if max_season is not None and r["season"] > max_season:
                    continue
                if (r.get(EXPO_KEY[side]) or 0) <= 0:
                    continue
                f = tmp.health_features(side, r.get("age"), sc_rows, tj, r.get("mlbam"), r["season"])
                if f is None:
                    continue
                for name, v in zip(HEALTH_FEATURES, f):
                    per_season[r["season"]][name].append(v)
        health["z"] = {s: {name: _zstats(v) for name, v in feats.items()}
                       for s, feats in per_season.items()}

    caps = _caps(corpus, max_season)
    meta = {
        "version": AGING_V3_VERSION, "provider": corpus.get("war_provider"),
        "corpus_sig": fp._corpus_sig(corpus), "corpus_seasons": [corpus.get("first"), corpus.get("last")],
        "max_season": max_season, "buckets": {s: list(v) for s, v in BUCKETS.items()},
        "parents": dict(PARENT), "archetypes": {s: list(v) for s, v in ARCHETYPES.items()},
        "arms": dict(cfg["arms"]), "health": cfg["health"],
        "k_values": {"k_P": cfg["P"]["k"], "k_R": cfg["R"]["k"]},
        "lambda": lam, "smoother": smoother, "penalty": penalty, "caps": caps,
        "pt_cap": cfg["pt_cap"], "cfg8": config_hash(cfg),
        "sidecar": ((sidecar or {}).get("meta") or {}).get("sig"),
        "cells": counts,
        "method": "delta_pa_weighted+survivorship+regressed_rate_v2 (v3 cells)",
    }
    return AgingModel(cfg=cfg, v2=v2, cells=cells, rho=rho, caps=caps, refs=refs,
                      extra=extra, assign=assign, health=health, meta=meta)


_FIT_SOURCE = (fit, _pair_rows, _league_rates, _value, _accumulate, _corrected, _shrink,
               _smooth, _rho_corrected, _caps, _ref_levels, _season_z_tables,
               _regressed_rate, assign_archetype, window_seasons, _hit_cells_v2, _pit_cells_v2)
AGING_V3_VERSION = "v3-" + fit_source_hash()


# ---------------------------------------------------------------------------
# Cache, attach, serve
# ---------------------------------------------------------------------------

def cache_path(corpus: dict, max_season: int | None, cfg: dict | None = None) -> Path:
    """``aging_v3_fits_{max_season}_{first}_{last}_{sig}_{AGING_V3_VERSION}_{cfg8}.pkl``."""
    return (CACHE_DIR / f"aging_v3_fits_{max_season}_{corpus['first']}_{corpus['last']}"
                        f"_{fp._corpus_sig(corpus)}_{AGING_V3_VERSION}_{config_hash(cfg or {})}.pkl")


def fitted(corpus: dict, max_season: int | None, cfg: dict | None = None, *,
           sidecar: dict | None = None, use_cache: bool = True) -> AgingModel:
    """``fit`` through the versioned cache. ``use_cache=False`` neither reads
    nor writes (the P-FITCACHE rule: a lab never overwrites a served fit)."""
    path = cache_path(corpus, max_season, cfg)
    if use_cache and path.exists():
        with open(path, "rb") as fh:
            return pickle.load(fh)
    model = fit(corpus, max_season, cfg, sidecar=sidecar)
    if use_cache:
        CACHE_DIR.mkdir(exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(model, fh)
    return model


def attach(curves: dict, corpus: dict, max_season: int | None, *, use_cache: bool = True,
           cfg: dict | None = None, sidecar: dict | None = None) -> dict:
    """A shallow copy of the v2 ``curves`` dict carrying the fitted model under
    ``_aging_v3`` (``fitted_models(..., aging="v3")``). Every other key is the v2
    curve, so ``curve_delta`` on the components reads exactly what v2 reads."""
    cfg = active_config() if cfg is None else normalize_config(cfg)
    if sidecar is None and (cfg["arms"]["P"] or cfg["arms"]["R"] or cfg["health"]):
        import aging_v3_sidecar
        sidecar = aging_v3_sidecar.load(corpus)
    model = fitted(corpus, max_season, cfg, sidecar=sidecar, use_cache=use_cache)
    out = dict(curves)
    out["_aging_v3"] = model
    return out


def model_of(curves: dict | None) -> AgingModel | None:
    """The attached model of a curves dict, or None."""
    return (curves or {}).get("_aging_v3") if isinstance(curves, dict) else None


_SERVED: dict = {"model": None, "mtime": None, "injected": None}


def set_served_model(model: AgingModel | None) -> None:
    """Inject the model ``served_model`` returns (labs, tests); None clears it."""
    _SERVED["injected"] = model


def served_model() -> AgingModel:
    """The committed full fit a corpus-free consumer (the prospect path, the
    trade fallback) reads: ``data/aging_v3_curves.json``, written by the flip
    that serves it; else an injected model; else raises AgingV3Unavailable."""
    if _SERVED["injected"] is not None:
        return _SERVED["injected"]
    if SERVED_CURVES_PATH.exists():
        mt = SERVED_CURVES_PATH.stat().st_mtime
        if _SERVED["model"] is None or _SERVED["mtime"] != mt:
            _SERVED["model"] = AgingModel.from_dict(
                json.loads(SERVED_CURVES_PATH.read_text(encoding="utf-8")))
            _SERVED["mtime"] = mt
        return _SERVED["model"]
    raise AgingV3Unavailable(
        "aging='v3' selected but no served model exists: data/aging_v3_curves.json is "
        "written by the flip task after docs/AGING_V3_GATE.md records a pass")


def recentre_health(exposures: list[float], multipliers: list[float]) -> list[float]:
    """Recentre a season's health multipliers so the league's projected
    exposure is unchanged by construction: m_i' = m_i * sum(e) / sum(e m)."""
    num = sum(float(e) for e in exposures)
    den = sum(float(e) * float(m) for e, m in zip(exposures, multipliers))
    if den <= 0:
        return [1.0 for _ in multipliers]
    s = num / den
    return [float(m) * s for m in multipliers]


def check_corpus(corpus: dict) -> list[str]:
    """The gate's corpus precondition (section 6): war_provider fwar and every
    season 2000-2026 present on both sides. Returns the problems."""
    probs = []
    if corpus.get("war_provider") != PROVIDER_REQUIRED:
        probs.append(f"war_provider {corpus.get('war_provider')!r} != {PROVIDER_REQUIRED!r}: "
                     "BLOCKER: task EPOCH_RUN")
    for side in SIDES:
        have = {r["season"] for r in corpus.get(side) or [] if r.get("war") is not None}
        missing = [s for s in range(2000, 2027) if s not in have]
        if any(s <= 2010 for s in missing):
            probs.append(f"{side}: seasons {[s for s in missing if s <= 2010]} absent from the "
                         "fwar label: BLOCKER: other pre-2011 fWAR absent")
        elif missing:
            probs.append(f"{side}: seasons {missing} absent")
    return probs


def _main(argv=None) -> int:
    """``python aging_v3.py --smoke``: a fit on the real corpus as a smoke test
    that fit() returns, printing cell counts and nothing else."""
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--max-season", type=int, default=None)
    ap.add_argument("--sidecar", action="store_true", help="fit with the sidecar loaded")
    a = ap.parse_args(argv)
    if not a.smoke:
        ap.print_help()
        return 0
    with open(fp.CORPUS_CACHE, "rb") as fh:
        corpus = pickle.load(fh)
    probs = check_corpus(corpus)
    if probs:
        print("\n".join(probs))
        return 2
    sidecar = None
    if a.sidecar:
        import aging_v3_sidecar
        sidecar = aging_v3_sidecar.load(corpus)
    m = fit(corpus, a.max_season, default_config(), sidecar=sidecar)
    print(f"aging v3 smoke: version {AGING_V3_VERSION} cfg8 {m.meta['cfg8']} "
          f"provider {m.meta['provider']} max_season {a.max_season}")
    for side in SIDES:
        for cell, comps in sorted(m.cells[side].items()):
            print(f"  {side} {cell}: " + ", ".join(f"{c} {len(v)} ages" for c, v in comps.items()))
    print("  caps:", {k: round(v, 1) for k, v in m.caps.items()})
    print("  extra:", {k: {r: len(c) for r, c in t.items()} for k, t in m.extra.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
