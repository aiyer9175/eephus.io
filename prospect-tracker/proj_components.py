# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The component projection FRAME: lag inputs and component labels per
(veteran, base season), built point in time, and the component HEADS
projected on it (task PJ_4, the section at the end). No score, no served key.

WHY THIS EXISTS. Owner ask 2026-10-01 (message 1): project the components of
WAR, not just WAR, and feed the projection more data. The plan is Part 9
section 9.2 'Component projections' and LANE_A sections 2.1 (the component set)
and 2.4 ('What more data means here'); the gate is docs/PROJ_COMPONENTS_GATE.md
(PJ-C, PJ-W), registered before any component number existed. This module is
task PJ_2_COMPONENT_FRAME: the frame the heads (PJ_4) are fitted on and the
scorer (PJ_3) reads. It computes no projection, no residual and no MAE.

WHAT A ROW IS. One per side ('hit', 'pit') and (mlbam, base B), over the
/projections/ veteran universe (proj_export: >= MIN_PA PA or >= MIN_IP IP in one
of the seasons B-1..B-3 of the corpus), with:

  lag features, from seasons B-1, B-2 and B-3 ONLY (suffix _l1, _l2, _l3):
    hitters   PA and games (raw StatsAPI hitting season cache); the vintage run
              parts per PA (batting, baseRunning, fielding, positional, wLeague,
              replacement, the framing residual, rar, war, wSb, ubr, wGdp);
              innings by position (FanGraphs fielding cache 'Inn' by 'Pos' from
              2011, the StatsAPI fielding cache before 2011) and FanGraphs
              CFraming on catcher rows; Savant sprint speed (2015+), OAA and
              fielding runs prevented summed over positions (2016+) and arm
              strength (2020+), each with a missing flag
    pitchers  IP, GS, G and BF (raw StatsAPI pitching season cache, ruling R6);
              the vintage war, rar and ra9War per IP; fip, xfip, gmli, exli,
              pli as published; (ra9War - war) per 100 IP
  age         proj_ml.age_from_history on the corpus history B-1..B-3
  labels      per horizon h = 1..5 with label season L = B+h-1 <= the frame's
              max label season and L not in PJC_EXCLUDED_LABEL_SEASONS: each
              run part, its rate (per PA, per IP, or per 100 IP for the RA9
              gap) and the exposures, plus `present` (the player has a vintage
              row in L)

THE LABEL SOURCE (unifier U2). Run parts come from the FROZEN fWAR vintage
(data/fwar_vintage.json through fwar_vintage.load()), never from the live
.cache/statsapi_saber_* payloads, which build_component_frame refuses outright.
Two exceptions, both from the raw StatsAPI season caches read through
fa_sources under scrapers.cache_only() (no fetch, no cache write):
  - pitcher innings, starts and games (ruling R6: the saber feed has none);
  - hitter PA (gate default D1: the vintage `plateAppearances` is null on
    every row of every season).

THE STINT GUARD. The vintage stores one row per id per season, resolved by
saber_feed.resolve_groups at freeze time; the frame asserts that receipt
(no ambiguous id, one row per player) on every season it reads and records
each season's multi-team count. A raw season cache with a repeated id is
resolved with saber_feed.resolve_groups and counted; an id with no unique
season-total row is summed over its team rows (D1) and counted.

THE GUARDS. PJC_LABEL_SEASON_MAX = 2025: a request for a later label season
raises (the 2027 forward path is PJ_11's, not this task's), and label season
2020 is excluded as Gate 1 excludes it. Every lag read goes through _lag,
which raises on a season >= B, so nothing a base cannot have known enters it.

CACHE. .cache/proj_components/frame_<schema tag>_<vintage id>_<first base>_<max
label>.pkl, where the schema tag hashes the column lists, FRAME_VERSION and the
corpus identity, so a schema change changes the file name and never reads a
stale frame. No file under data/ is written.
"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import pickle
from functools import lru_cache
from pathlib import Path

import fwar_vintage
import saber_feed

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
SRC_CACHE = ROOT / ".cache"
CACHE_DIR = SRC_CACHE / "proj_components"

#: Bumped by hand on any change to what a row means; folded into the schema tag.
FRAME_VERSION = 1

HORIZONS = 5
LAGS = (1, 2, 3)

#: The frame's label guards (task PJ_2; docs/PROJ_COMPONENTS_GATE.md section 3).
PJC_LABEL_SEASON_MAX = 2025
PJC_EXCLUDED_LABEL_SEASONS = frozenset({2020})

#: The /projections/ veteran universe (proj_export.MIN_PA, MIN_IP; pinned by test).
MIN_PA, MIN_IP = 100, 30

FG_FIELDING_FIRST = 2011
SPRINT_FIRST, OAA_FIRST, ARM_FIRST = 2015, 2016, 2020
FIELD_POSITIONS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF")
OAA_POS_CODES = (3, 4, 5, 6, 7, 8, 9)     # pos2 (catcher) returns no rows

#: Hitting vintage fields carried per PA. `framing` is the residual
#: rar - sum(RUN_PARTS), saber_feed.framing_residual's definition.
HIT_PARTS = tuple(saber_feed.RUN_PARTS) + ("framing", "rar", "war", "wSb", "ubr", "wGdp")
HIT_VINTAGE_FIELDS = tuple(saber_feed.RUN_PARTS) + ("rar", "war", "wSb", "ubr", "wGdp")
#: Pitching vintage fields: counts carried per IP, rates carried as published.
PIT_COUNT_PARTS = ("war", "rar", "ra9War")
PIT_RATE_PARTS = ("fip", "xfip", "gmli", "exli", "pli")
PIT_VINTAGE_FIELDS = PIT_COUNT_PARTS + PIT_RATE_PARTS

HIT_EXPOSURES = ("pa", "g")
PIT_EXPOSURES = ("ip", "gs", "g", "bf")
SAVANT_FIELDS = {"sprint": ("sprint_speed",), "oaa": ("oaa", "frp"),
                 "arm": ("arm_overall", "arm_max")}
SAVANT_FIRST = {"sprint": SPRINT_FIRST, "oaa": OAA_FIRST, "arm": ARM_FIRST}


class PJCLabelSeasonError(ValueError):
    """A label season beyond PJC_LABEL_SEASON_MAX was requested."""


class LiveLabelRefused(ValueError):
    """A live .cache/statsapi_saber_* payload (or anything that is not the
    frozen vintage) was offered as the label source."""


class LookaheadError(AssertionError):
    """A lag read asked for a season the base could not have known."""


class VintageShapeError(AssertionError):
    """A vintage season is not one row per player (the stint guard failed)."""


# --------------------------------------------------------------------------
# Schema and cache name
# --------------------------------------------------------------------------

def _lagged(names) -> list[str]:
    return [f"{n}_l{k}" for k in LAGS for n in names]


def feature_names(side: str) -> list[str]:
    """The lag feature keys of one side's rows, in a fixed order."""
    if side == "hit":
        base = (list(HIT_EXPOSURES) + [f"{p}_pa" for p in HIT_PARTS] + ["vintage_missing"]
                + [f"inn_{p}" for p in FIELD_POSITIONS] + ["inn_total", "cframing", "fld_missing"])
        for kind in ("sprint", "oaa", "arm"):
            base += list(SAVANT_FIELDS[kind]) + [f"{kind}_missing"]
        return _lagged(base)
    if side == "pit":
        base = (list(PIT_EXPOSURES) + ["gs_share"] + [f"{p}_ip" for p in PIT_COUNT_PARTS]
                + list(PIT_RATE_PARTS) + ["ra9gap_100ip", "vintage_missing"])
        return _lagged(base)
    raise ValueError(f"unknown side {side!r}")


def label_names(side: str) -> list[str]:
    """The keys of one horizon's label block."""
    if side == "hit":
        return (["season", "present"] + list(HIT_EXPOSURES) + list(HIT_PARTS)
                + [f"{p}_pa" for p in HIT_PARTS])
    if side == "pit":
        return (["season", "present"] + list(PIT_EXPOSURES) + list(PIT_VINTAGE_FIELDS)
                + ["ra9gap"] + [f"{p}_ip" for p in PIT_COUNT_PARTS] + ["ra9gap_100ip"])
    raise ValueError(f"unknown side {side!r}")


def _corpus_tag(corpus: dict | None) -> dict:
    c = corpus or {}
    return {"first": c.get("first"), "last": c.get("last"),
            "war_provider": c.get("war_provider"), "label_shape": c.get("label_shape")}


def frame_schema(corpus: dict | None = None) -> dict:
    """Everything a row's meaning depends on, hashed into the cache name."""
    return {"version": FRAME_VERSION, "horizons": HORIZONS, "lags": list(LAGS),
            "label_max": PJC_LABEL_SEASON_MAX,
            "excluded": sorted(PJC_EXCLUDED_LABEL_SEASONS),
            "universe": [MIN_PA, MIN_IP],
            "features": {s: feature_names(s) for s in ("hit", "pit")},
            "labels": {s: label_names(s) for s in ("hit", "pit")},
            "corpus": _corpus_tag(corpus)}


def schema_tag(corpus: dict | None = None) -> str:
    blob = json.dumps(frame_schema(corpus), sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:10]


def cache_path(first_base: int, max_label_season: int, vintage_id: str,
               corpus: dict | None = None) -> Path:
    return CACHE_DIR / (f"frame_{schema_tag(corpus)}_{vintage_id}_"
                        f"{int(first_base)}_{int(max_label_season)}.pkl")


# --------------------------------------------------------------------------
# Guards
# --------------------------------------------------------------------------

def check_label_season(season: int) -> int:
    """Raise unless `season` may be a label of this frame."""
    season = int(season)
    if season > PJC_LABEL_SEASON_MAX:
        raise PJCLabelSeasonError(
            f"label season {season} is above PJC_LABEL_SEASON_MAX "
            f"{PJC_LABEL_SEASON_MAX}; the 2027 forward path is PJ_11's and is not built")
    return season


def resolve_vintage(vintage=None) -> dict:
    """The frozen vintage blob. None reads fwar_vintage.load(); a dict must be
    a fwar_vintage blob; a path must be a fwar_vintage file. A live
    .cache/statsapi_saber_* payload is refused whatever form it arrives in."""
    if vintage is None:
        return fwar_vintage.load()
    if isinstance(vintage, (str, Path)):
        p = Path(vintage)
        if p.name.startswith("statsapi_saber") or "statsapi_saber" in str(p).replace("\\", "/"):
            raise LiveLabelRefused(f"{p} is the live sabermetrics cache, never a label")
        blob = fwar_vintage.load(p)
    elif isinstance(vintage, dict):
        blob = vintage
    else:
        raise LiveLabelRefused(f"unsupported label source {type(vintage).__name__}")
    if blob.get("schema") != fwar_vintage.SCHEMA or not blob.get("vintage_id"):
        raise LiveLabelRefused("label source is not a frozen fwar_vintage blob "
                               f"(schema {blob.get('schema')!r})")
    return blob


def _lag(season: int, base: int) -> int:
    if int(season) > int(base) - 1:
        raise LookaheadError(f"lag read of season {season} for base {base}")
    return int(season)


# --------------------------------------------------------------------------
# Readers (cache only; each is the seam a test replaces)
# --------------------------------------------------------------------------

def _num(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def innings(raw) -> float:
    """Baseball-notation innings ('190.1', 1043.2) as true innings."""
    if raw in (None, ""):
        return 0.0
    s = str(raw).strip()
    whole, _, frac = s.partition(".")
    try:
        base = float(whole or 0)
    except ValueError:
        return 0.0
    return base + {"1": 1.0 / 3.0, "2": 2.0 / 3.0}.get(frac[:1], 0.0)


def vintage_group(blob: dict, season: int, group: str) -> dict | None:
    """{mlbam: {field: value}} for one frozen (season, group), or None when the
    vintage does not hold it frozen. Asserts the stint-guard receipt."""
    gb = ((blob.get("seasons") or {}).get(str(int(season))) or {}).get(group) or {}
    if gb.get("status") != "frozen":
        return None
    rows = gb.get("rows") or {}
    if gb.get("ambiguous_ids"):
        raise VintageShapeError(f"vintage {season} {group}: ambiguous ids "
                                f"{gb['ambiguous_ids'][:5]}; a multi-club season is not a total")
    if gb.get("n_players") is not None and int(gb["n_players"]) != len(rows):
        raise VintageShapeError(f"vintage {season} {group}: n_players {gb['n_players']} "
                                f"!= {len(rows)} rows")
    fields = list(gb.get("fields") or [])
    return {int(mid): dict(zip(fields, vals)) for mid, vals in rows.items()}


def exposures_from_splits(splits: list, group: str) -> tuple[dict, dict]:
    """({mlbam: exposures}, receipt) from raw StatsAPI season splits. A
    repeated id resolves to its numTeams > 1 total (saber_feed.resolve_groups);
    an id with no unique total is summed over its team rows (default D1)."""
    by_id: dict[int, list] = {}
    for s in splits or []:
        pid = (s.get("player") or {}).get("id")
        if pid is not None:
            by_id.setdefault(int(pid), []).append(s)
    resolved, ambiguous, _ = saber_feed.resolve_groups(splits)
    receipt = {"n_rows": len(splits or []), "n_repeated_ids": sum(1 for v in by_id.values() if len(v) > 1),
               "n_resolved_to_total": 0, "n_summed": len(ambiguous)}
    receipt["n_resolved_to_total"] = receipt["n_repeated_ids"] - receipt["n_summed"]

    def one(stat: dict) -> dict:
        if group == "hitting":
            return {"pa": _num(stat.get("plateAppearances")) or 0.0,
                    "g": _num(stat.get("gamesPlayed")) or 0.0}
        return {"ip": innings(stat.get("inningsPitched")),
                "gs": _num(stat.get("gamesStarted")) or 0.0,
                "g": _num(stat.get("gamesPlayed")) or 0.0,
                "bf": _num(stat.get("battersFaced")) or 0.0}

    out = {pid: one(row.get("stat") or {}) for pid, row in resolved.items()}
    for pid in ambiguous:
        tot: dict[str, float] = {}
        for row in by_id[pid]:
            for k, v in one(row.get("stat") or {}).items():
                tot[k] = tot.get(k, 0.0) + v
        out[pid] = tot
    return out, receipt


@lru_cache(maxsize=None)
def read_exposures(season: int, group: str) -> dict:
    """{mlbam: exposures} for one season from the raw StatsAPI season cache,
    read through fa_sources inside scrapers.cache_only(): a cached copy is
    served whatever its age and nothing is fetched or written."""
    import fa_sources
    import scrapers
    with scrapers.cache_only():
        splits = fa_sources.fetch_statsapi_season_stats(int(season), group)
    out, receipt = exposures_from_splits(splits, group)
    EXPOSURE_RECEIPTS[f"{int(season)}:{group}"] = receipt
    return out


#: {"<season>:<group>": stint receipt} of every raw season read_exposures parsed.
EXPOSURE_RECEIPTS: dict[str, dict] = {}


@lru_cache(maxsize=None)
def read_fielding(season: int) -> dict | None:
    """{mlbam: {"inn": {POS: innings}, "cframing": runs | None, "src": ...}}
    from the FanGraphs fielding cache (2011+), else the StatsAPI fielding
    cache. None when neither file is on disk. Cache only."""
    season = int(season)
    fg = SRC_CACHE / "fangraphs" / f"fielding_{season}.json"
    if season >= FG_FIELDING_FIRST and fg.exists():
        doc = json.loads(fg.read_text(encoding="utf-8"))
        out: dict[int, dict] = {}
        for r in doc.get("rows") or []:
            mid, pos = r.get("xMLBAMID"), r.get("Pos")
            if not mid or pos not in FIELD_POSITIONS:
                continue
            rec = out.setdefault(int(mid), {"inn": {}, "cframing": None, "src": "fangraphs"})
            rec["inn"][pos] = rec["inn"].get(pos, 0.0) + innings(r.get("Inn"))
            cf = _num(r.get("CFraming"))
            if pos == "C" and cf is not None:
                rec["cframing"] = (rec["cframing"] or 0.0) + cf
        return out
    sa = SRC_CACHE / "statsapi_field" / f"fld_{season}.json"
    if not sa.exists():
        return None
    import fielding_innings
    parsed = fielding_innings.parse_season(json.loads(sa.read_text(encoding="utf-8")))
    out = {}
    for mid, byp in parsed.items():
        inn = {p: float(v.get("inn") or 0.0) for p, v in byp.items() if p in FIELD_POSITIONS}
        if inn:
            out[int(mid)] = {"inn": inn, "cframing": None, "src": "statsapi"}
    return out


def _csv_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


@lru_cache(maxsize=None)
def read_savant(kind: str, season: int) -> dict | None:
    """{mlbam: {field: value}} for one Savant season, or None when the season
    predates the source or its file is not on disk. Cache only.

    sprint  .cache/savant_sprint/sprint_<season>.csv: sprint_speed
    oaa     .cache/savant_oaa/oaa_<season>_pos<3..9>.csv (min=1, one row per
            player and position), summed per player: oaa, frp; the
            unsuffixed oaa_<season>.csv (qualified only) when no position
            file exists
    arm     .cache/savant_arm/arm_<season>.csv: arm_overall, arm_max"""
    season = int(season)
    if kind not in SAVANT_FIRST:
        raise ValueError(f"unknown Savant kind {kind!r}")
    if season < SAVANT_FIRST[kind]:
        return None
    if kind == "sprint":
        p = SRC_CACHE / "savant_sprint" / f"sprint_{season}.csv"
        if not p.exists():
            return None
        return {int(r["player_id"]): {"sprint_speed": _num(r.get("sprint_speed"))}
                for r in _csv_rows(p) if (r.get("player_id") or "").strip()}
    if kind == "arm":
        p = SRC_CACHE / "savant_arm" / f"arm_{season}.csv"
        if not p.exists():
            return None
        return {int(r["player_id"]): {"arm_overall": _num(r.get("arm_overall")),
                                      "arm_max": _num(r.get("max_arm_strength"))}
                for r in _csv_rows(p) if (r.get("player_id") or "").strip()}
    files = [SRC_CACHE / "savant_oaa" / f"oaa_{season}_pos{c}.csv" for c in OAA_POS_CODES]
    files = [p for p in files if p.exists()]
    if not files:
        whole = SRC_CACHE / "savant_oaa" / f"oaa_{season}.csv"
        files = [whole] if whole.exists() else []
    if not files:
        return None
    out: dict[int, dict] = {}
    for p in files:
        for r in _csv_rows(p):
            pid = (r.get("player_id") or "").strip()
            if not pid:
                continue
            rec = out.setdefault(int(pid), {"oaa": 0.0, "frp": 0.0})
            rec["oaa"] += _num(r.get("outs_above_average")) or 0.0
            rec["frp"] += _num(r.get("fielding_runs_prevented")) or 0.0
    return out


def clear_reader_caches() -> None:
    for fn in (read_exposures, read_fielding, read_savant):
        cache_clear = getattr(fn, "cache_clear", None)
        if cache_clear:
            cache_clear()
    EXPOSURE_RECEIPTS.clear()


# --------------------------------------------------------------------------
# Row assembly
# --------------------------------------------------------------------------

def _rate(v, den, scale: float = 1.0):
    return None if (v is None or not den) else float(v) * scale / float(den)


def _hit_parts(vrow: dict | None) -> dict | None:
    """The hitting run parts of one vintage row with the framing residual."""
    if vrow is None:
        return None
    out = {k: _num(vrow.get(k)) for k in HIT_VINTAGE_FIELDS}
    out["framing"] = saber_feed.framing_residual(vrow)
    return out


def _pit_parts(vrow: dict | None) -> dict | None:
    if vrow is None:
        return None
    return {k: _num(vrow.get(k)) for k in PIT_VINTAGE_FIELDS}


class _Sources:
    """Per-build memo of the vintage groups; exposures, fielding and Savant
    are read through the module readers (the test seams)."""

    def __init__(self, blob: dict):
        self.blob = blob
        self._vin: dict = {}
        self.multi_team: dict = {}

    def vintage(self, season: int, group: str) -> dict | None:
        key = (int(season), group)
        if key not in self._vin:
            self._vin[key] = vintage_group(self.blob, season, group)
            gb = ((self.blob.get("seasons") or {}).get(str(int(season))) or {}).get(group) or {}
            if self._vin[key] is not None:
                self.multi_team[f"{int(season)}:{group}"] = gb.get("n_multi_team")
        return self._vin[key]


def _hit_lags(src: _Sources, mlbam: int, base: int) -> dict:
    f: dict = {}
    for k in LAGS:
        s = _lag(base - k, base)
        exp = (read_exposures(s, "hitting") or {}).get(mlbam) or {}
        pa = exp.get("pa")
        f[f"pa_l{k}"] = pa
        f[f"g_l{k}"] = exp.get("g")
        parts = _hit_parts((src.vintage(s, "hitting") or {}).get(mlbam))
        for p in HIT_PARTS:
            f[f"{p}_pa_l{k}"] = _rate((parts or {}).get(p), pa)
        f[f"vintage_missing_l{k}"] = 1 if parts is None else 0
        fld = read_fielding(s)
        rec = (fld or {}).get(mlbam)
        for p in FIELD_POSITIONS:
            f[f"inn_{p}_l{k}"] = (rec["inn"].get(p, 0.0) if rec else (0.0 if fld is not None else None))
        f[f"inn_total_l{k}"] = (sum(rec["inn"].values()) if rec else (0.0 if fld is not None else None))
        f[f"cframing_l{k}"] = rec["cframing"] if rec else None
        f[f"fld_missing_l{k}"] = 1 if fld is None else 0
        for kind in ("sprint", "oaa", "arm"):
            sv = read_savant(kind, s)
            srow = (sv or {}).get(mlbam)
            for name in SAVANT_FIELDS[kind]:
                f[f"{name}_l{k}"] = (srow or {}).get(name)
            f[f"{kind}_missing_l{k}"] = 1 if (srow is None or all(
                (srow or {}).get(n) is None for n in SAVANT_FIELDS[kind])) else 0
    return f


def _pit_lags(src: _Sources, mlbam: int, base: int) -> dict:
    f: dict = {}
    for k in LAGS:
        s = _lag(base - k, base)
        exp = (read_exposures(s, "pitching") or {}).get(mlbam) or {}
        ip = exp.get("ip")
        for e in PIT_EXPOSURES:
            f[f"{e}_l{k}"] = exp.get(e)
        f[f"gs_share_l{k}"] = _rate(exp.get("gs"), exp.get("g"))
        parts = _pit_parts((src.vintage(s, "pitching") or {}).get(mlbam))
        for p in PIT_COUNT_PARTS:
            f[f"{p}_ip_l{k}"] = _rate((parts or {}).get(p), ip)
        for p in PIT_RATE_PARTS:
            f[f"{p}_l{k}"] = (parts or {}).get(p)
        gap = None
        if parts and parts.get("ra9War") is not None and parts.get("war") is not None:
            gap = parts["ra9War"] - parts["war"]
        f[f"ra9gap_100ip_l{k}"] = _rate(gap, ip, 100.0)
        f[f"vintage_missing_l{k}"] = 1 if parts is None else 0
    return f


def make_sources(vintage=None) -> _Sources:
    """The per-build vintage memo for `lag_inputs` (the frozen vintage only;
    a live sabermetrics payload is refused by resolve_vintage)."""
    return _Sources(resolve_vintage(vintage))


def lag_inputs(src: _Sources, side: str, mlbam: int, base: int) -> dict:
    """One veteran's lag features at `base` exactly as the frame builds
    them (seasons B-1..B-3 only, through the _lag guard). No label is read.
    The served export (task PJ_6) calls this for the forward base."""
    return (_hit_lags if side == "hit" else _pit_lags)(src, int(mlbam), int(base))


def _hit_label(src: _Sources, mlbam: int, season: int) -> dict:
    exp = (read_exposures(season, "hitting") or {}).get(mlbam) or {}
    parts = _hit_parts((src.vintage(season, "hitting") or {}).get(mlbam))
    pa = exp.get("pa")
    lab = {"season": season, "present": parts is not None,
           "pa": pa, "g": exp.get("g")}
    for p in HIT_PARTS:
        lab[p] = (parts or {}).get(p)
        lab[f"{p}_pa"] = _rate(lab[p], pa)
    return lab


def _pit_label(src: _Sources, mlbam: int, season: int) -> dict:
    exp = (read_exposures(season, "pitching") or {}).get(mlbam) or {}
    parts = _pit_parts((src.vintage(season, "pitching") or {}).get(mlbam))
    ip = exp.get("ip")
    lab = {"season": season, "present": parts is not None}
    for e in PIT_EXPOSURES:
        lab[e] = exp.get(e)
    for p in PIT_VINTAGE_FIELDS:
        lab[p] = (parts or {}).get(p)
    lab["ra9gap"] = (None if lab["ra9War"] is None or lab["war"] is None
                     else lab["ra9War"] - lab["war"])
    for p in PIT_COUNT_PARTS:
        lab[f"{p}_ip"] = _rate(lab[p], ip)
    lab["ra9gap_100ip"] = _rate(lab["ra9gap"], ip, 100.0)
    return lab


def _in_universe(side: str, hist: list[dict]) -> bool:
    if side == "hit":
        return max(h.get("pa") or 0 for h in hist) >= MIN_PA
    return max(h.get("ip") or 0 for h in hist) >= MIN_IP


def label_seasons(base: int, max_label_season: int) -> dict[int, int]:
    """{h: label season} for the horizons a base carries a label on."""
    out = {}
    for h in range(1, HORIZONS + 1):
        L = int(base) + h - 1
        if L > int(max_label_season) or L in PJC_EXCLUDED_LABEL_SEASONS:
            continue
        out[h] = check_label_season(L)
    return out


def build_component_frame(corpus: dict, first_base: int, max_label_season: int,
                          use_cache: bool = True, *, vintage=None) -> dict:
    """{"hit": [rows], "pit": [rows], "meta": {...}} over bases first_base ..
    max_label_season (a base contributes horizon h only when its label season
    B+h-1 <= max_label_season and is not excluded). See the module docstring
    for a row's keys; `vintage` is the frozen fwar vintage (default: the
    committed one), and anything else raises LiveLabelRefused."""
    check_label_season(max_label_season)
    if int(first_base) > int(max_label_season):
        raise ValueError(f"first_base {first_base} > max_label_season {max_label_season}")
    blob = resolve_vintage(vintage)
    vid = blob["vintage_id"]
    frozen = set(fwar_vintage.fwar_seasons(blob))
    for L in range(int(first_base), int(max_label_season) + 1):
        if L not in PJC_EXCLUDED_LABEL_SEASONS and L not in frozen:
            raise VintageShapeError(f"label season {L} is not frozen in vintage {vid}")
    path = cache_path(first_base, max_label_season, vid, corpus)
    if use_cache and path.exists():
        with open(path, "rb") as fh:
            return pickle.load(fh)

    import proj_ml
    src = _Sources(blob)
    by_player: dict[str, dict] = {"hit": {}, "pit": {}}
    for side in ("hit", "pit"):
        for r in corpus.get(side) or []:
            if r.get("mlbam"):
                by_player[side].setdefault(int(r["mlbam"]), {})[int(r["season"])] = r
    out: dict = {"hit": [], "pit": []}
    for side in ("hit", "pit"):
        lags = _hit_lags if side == "hit" else _pit_lags
        label = _hit_label if side == "hit" else _pit_label
        for base in range(int(first_base), int(max_label_season) + 1):
            horizons = label_seasons(base, max_label_season)
            for mlbam in sorted(by_player[side]):
                seasons = by_player[side][mlbam]
                hist = [seasons[t] for t in (base - 1, base - 2, base - 3) if t in seasons]
                if not hist or not _in_universe(side, hist):
                    continue
                age = proj_ml.age_from_history(hist, base)
                if age is None:
                    continue
                out[side].append({
                    "mlbam": mlbam, "base": base, "age": age,
                    "role": hist[0].get("role"),
                    "feat": lags(src, mlbam, base),
                    "labels": {h: label(src, mlbam, L) for h, L in horizons.items()},
                })
    out["meta"] = {
        "schema_tag": schema_tag(corpus), "frame_version": FRAME_VERSION,
        "vintage_id": vid, "first_base": int(first_base),
        "max_label_season": int(max_label_season),
        "excluded_label_seasons": sorted(PJC_EXCLUDED_LABEL_SEASONS),
        "label_source": "frozen fwar vintage (fwar_vintage.load)",
        "exposure_source": "raw StatsAPI season cache via fa_sources, cache only",
        "n_rows": {s: len(out[s]) for s in ("hit", "pit")},
        "vintage_multi_team": dict(sorted(src.multi_team.items())),
        "exposure_stint": {k: dict(v) for k, v in sorted(EXPOSURE_RECEIPTS.items())},
        "corpus": _corpus_tag(corpus),
    }
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".pkl.tmp")
        with open(tmp, "wb") as fh:
            pickle.dump(out, fh)
        tmp.replace(path)
    return out


def row_counts(frame: dict) -> dict:
    """Counts only: rows per side, the base range, and labelled rows per horizon."""
    out = {}
    for side in ("hit", "pit"):
        rows = frame.get(side) or []
        bases = sorted({r["base"] for r in rows})
        out[side] = {"rows": len(rows),
                     "bases": [bases[0], bases[-1]] if bases else None,
                     "labelled_by_h": {h: sum(1 for r in rows if h in r["labels"])
                                       for h in range(1, HORIZONS + 1)}}
    return out


# ==========================================================================
# THE HEADS (task PJ_4_COMPONENT_HEADS_DEV; docs/PROJ_COMPONENTS_GATE.md
# section 1, LANE_A 2.1 and 2.2)
# ==========================================================================
#
# project_components(...) projects, per veteran and base, the FanGraphs-frame
# WAR components as MEANS for horizons 1 to 5, exactly the forms the gate
# registers. Everything a head needs from the incumbent engine is read through
# the engine itself (fa_projection.project_player, rate_path, curve_delta;
# fa_market._band_bucket) and everything in runs goes through fwar_frame's
# pure functions. The one WAR a hitter head returns is H8 (components summed
# over the season's runs per win) and the one a pitcher head returns is P3
# (the FIP-based chain) with P5 beside it; no head reads a WAR label, none is
# fitted on one, and no function here predicts WAR in any other form.
#
# WHAT IS HELD. Every league constant is the last completed season's
# (data/league_constants.json at B - 1, plus the terms derived from that
# season's frozen vintage: the league batting term, the league adjustment rate,
# WARIP), held across the horizon as rate_path holds its run environment. Park
# factor 1.0 on every head; no framing charge on a pitcher.
#
# THE AGE TERMS (unifier U5, PLAN 9.7 'One aging service'). H3 and H4 carry no
# local age fit: their deltas are aging_v3.AgingModel.component_curve('hit',
# 'bsr' | 'fld'), passed in by the caller point-in-time per base. Framing (the
# catcher residual inside H4) carries no age term.
#
# THE FROZEN CHOICES (model/proj_components/params.json, written once by
# tools/proj_components_dev.py on the DEV frame): the four shrink constants
# from their fixed grids, the Savant admissions with their slopes, the
# residual range quantiles by horizon and exposure tier, the gmLI constant R,
# and the frame schema the choices were made on.

#: The fixed four-point grids (LANE_A 2.1; never extended after the look).
K_GRIDS: dict[str, tuple[int, ...]] = {
    "bsr_pa": (300, 600, 1200, 2400),        # H3, PA
    "fld_inn": (1000, 2000, 4000, 8000),     # H4, innings (framing shares it)
    "gmli_g": (20, 40, 80, 160),             # P4, relief games, toward 1.0
    "ra9gap_ip": (200, 400, 800, 1600),      # P5, IP, toward 0
}
#: The Savant terms a DEV decision may admit: term -> (head, lag feature).
SAVANT_TERMS: dict[str, tuple[str, str]] = {
    "sprint": ("bsr", "sprint_speed"),
    "oaa": ("fld", "oaa"),
    "arm": ("fld", "arm_overall"),
}
BF_PER_IP = 4.3                    # the engine's BF-to-IP convention (P-IPAGE)
NAIVE_WEIGHTS = (5.0, 4.0, 3.0)    # the Gate 1 naive comparator form
HEADS_VERSION = 1

PARAMS_DIR = ROOT / "model" / "proj_components"
PARAMS_PATH = PARAMS_DIR / "params.json"
DEV_RECEIPT_PATH = PARAMS_DIR / "dev_receipt.json"

#: The keys of a hitter season line and of a pitcher season line.
HIT_LINE_KEYS = ("pa", "k_pct", "bb_pct", "iso", "babip", "hr_pa", "woba", "wrc_plus",
                 "bat", "bsr", "fld", "pos", "lg", "rep", "war_comp", "fld_pos",
                 "inn", "dh_inn", "inn_c", "bsr600", "fld1000", "frm1000")
PIT_LINE_KEYS = ("ip", "bf", "g", "gs", "gs_share", "relief_ip", "k_pct", "bb_pct", "hr_bf",
                 "fip", "gmli", "war_fip", "war_ra9", "ra9gap_100ip", "fip_runs_100ip",
                 "raap9", "drpw")


class ParamsHashMismatch(AssertionError):
    """model/proj_components/params.json does not hash to the recorded value."""


# --------------------------------------------------------------------------
# Readers and the held constants
# --------------------------------------------------------------------------

def read_mlb_games(season: int) -> float | None:
    """MLB games played in `season` from the cached standings
    (.cache/statsapi_standings_<season>.json); None when the file is absent."""
    p = SRC_CACHE / f"statsapi_standings_{int(season)}.json"
    if not p.exists():
        return None
    try:
        blob = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None
    gp = 0.0
    for rec in blob.get("records") or []:
        for t in rec.get("teamRecords") or []:
            gp += float(t.get("gamesPlayed") or 0)
    return gp / 2.0 if gp > 0 else None


def realized_pitching(season: int, consts: dict, vintage=None) -> list[dict]:
    """The pitcher chain on REALIZED inputs for one season: every vintage
    pitcher with innings in the raw cache, priced on his published FIP and
    gmLI at PF 1.0 with no framing charge and the single blended line. Used
    for the WARIP pin of `season_constants` and the DEV receipts; nothing
    here is a projection."""
    import fwar_frame as F
    blob = resolve_vintage(vintage)
    pit = vintage_group(blob, season, "pitching") or {}
    exp = read_exposures(season, "pitching") or {}
    lg9 = consts["lg_fipr9"]
    out = []
    for mid, v in pit.items():
        e = exp.get(mid) or {}
        ip, g, gs = e.get("ip") or 0.0, e.get("g") or 0.0, e.get("gs") or 0.0
        fip_v, gm = _num(v.get("fip")), _num(v.get("gmli"))
        if ip <= 0 or g <= 0 or fip_v is None:
            continue
        pfr = F.pfipr9(F.fipr9(fip_v, consts["lg_ra9"], consts["lg_era"]), 1.0)
        line = F.blended_line(ip, g, gs, lg9, lg9, pfr, gm)
        out.append({"mlbam": mid, "ip": ip, "g": g, "gs": gs, "fip": fip_v, "gmli": gm,
                    "raap9": F.raap9(lg9, pfr), "drpw": line["drpw"], "war0": line["war0"],
                    "reliever": (gs / g) < 0.5})
    return out


def season_constants(season: int, corpus: dict, vintage=None) -> dict:
    """The constants every head holds at the last completed season `season`:
    the solved block of data/league_constants.json plus the terms it does not
    carry, derived from that season's frozen vintage and raw exposures.

      lg_nonp_wrc_pa  league non-pitcher wRC per PA (the league batting term
                      of fwar_frame.league_batting_runs): lgR/PA plus the
                      non-pitcher wRAA per PA, non-pitchers being the hitters
                      the corpus carries (it excludes pitchers batting)
      lg_adj_rate     fwar_frame.league_adjustment_rate on the vintage's
                      batting + baserunning + fielding + positional + framing
                      summed MLB-wide over every MLB plate appearance
      rep_per_pa      fwar_frame.replacement_per_pa(games, rpw, lg_pa) at the
                      season's own MLB game count, the count that produced
                      lg_pa (2430 in a full season, 898 in 2020; the per-PA
                      rate FanGraphs itself handed out that season)
      lg_fipr9        the league FIPR9: league FIP equals league ERA by the
                      FIP constant's construction, so FIPR9 is lgRA9 (MLB,
                      not the pitcher's own league: a projection has no league)
      warip           fwar_frame.warip pinning the realized chain's MLB
                      pitcher total to 430 per 2430 games that season
      inn_per_pa      lineup-slot innings per MLB plate appearance (2 clubs x
                      9 slots x 9 innings x games / lgPA), the DH conversion
      eng_lg_woba     the engine's own league wOBA anchor (corpus league), the
                      baseline the projected wOBA is measured from
    """
    import league_constants as LC
    import fwar_frame as F
    season = int(season)
    blk = LC.load().get(season)
    if not blk or "rpw" not in blk or "woba_scale" not in blk:
        raise ValueError(f"data/league_constants.json has no solved block for {season}")
    blob = resolve_vintage(vintage)
    hit = vintage_group(blob, season, "hitting") or {}
    hexp = read_exposures(season, "hitting") or {}
    nonp = {int(r["mlbam"]) for r in (corpus.get("hit") or [])
            if r.get("mlbam") and int(r.get("season") or 0) == season}
    s_wraa = s_pa = s_parts = 0.0
    n_nonp = n_parts = 0
    for mid, v in hit.items():
        parts = _hit_parts(v)
        if parts and all(parts.get(p) is not None for p in ("batting", "baseRunning",
                                                              "fielding", "positional")):
            s_parts += sum(parts[p] for p in ("batting", "baseRunning", "fielding", "positional"))
            s_parts += parts.get("framing") or 0.0
            n_parts += 1
        pa = (hexp.get(mid) or {}).get("pa") or 0.0
        w = _num(v.get("wRaa"))
        if mid in nonp and pa > 0 and w is not None:
            s_wraa += w
            s_pa += pa
            n_nonp += 1
    lg_pa = float(blk["lg_pa"])
    rpw = float(blk["rpw"])
    games = read_mlb_games(season)
    games_src = "statsapi standings cache"
    if games is None:
        games, games_src = F.FULL_SEASON_GAMES, "2430 (standings cache absent)"
    out = {
        "season": season,
        "lg_r_pa": float(blk["lg_r_pa"]), "lg_ra9": float(blk["lg_ra9"]),
        "lg_era": float(blk["lg_era"]), "rpw": rpw, "fip_constant": float(blk["fip_constant"]),
        "lg_pa": lg_pa, "woba_scale": float(blk["woba_scale"]), "lg_woba_feed": blk.get("lg_woba"),
        "eng_lg_woba": ((corpus.get("league") or {}).get(season) or {}).get("woba"),
        "lg_nonp_wrc_pa": float(blk["lg_r_pa"]) + (s_wraa / s_pa if s_pa > 0 else 0.0),
        "lg_adj_rate": F.league_adjustment_rate(s_parts, lg_pa),
        "rep_per_pa": F.replacement_per_pa(float(games), rpw, lg_pa),
        "lg_fipr9": float(blk["lg_ra9"]),
        "mlb_games": float(games),
        "inn_per_pa": 2.0 * 9.0 * 9.0 * float(games) / lg_pa,
        "pf": 1.0,
    }
    lines = realized_pitching(season, out, blob)
    sum_war0 = sum(x["war0"] for x in lines)
    sum_ip = sum(x["ip"] for x in lines)
    target = F.replacement_totals(games)[1]
    out["warip"] = F.warip(target, sum_war0, sum_ip) if sum_ip > 0 else 0.0
    out["receipt"] = {
        "n_vintage_hitters": len(hit), "n_nonpitcher_wraa_rows": n_nonp,
        "nonpitcher_pa": s_pa, "n_parts_rows": n_parts, "league_runs_sum": round(s_parts, 3),
        "n_pitchers_priced": len(lines), "pitcher_ip": round(sum_ip, 1),
        "pitcher_war0_sum": round(sum_war0, 3), "pitcher_target_war": round(target, 2),
        "mlb_games_source": games_src,
    }
    return out


# --------------------------------------------------------------------------
# Marcel helpers (5/3/2 with shrink; the 5/4/3 naive form for comparators)
# --------------------------------------------------------------------------

def _engine_weights() -> list[float]:
    import fa_projection as fp
    return list(fp._marcel_weights())


def marcel_rate(items, k_shrink: float, target: float = 0.0, weights=None):
    """(shrunk rate, exposure weight) from [(lag, rate, exposure)]: the
    engine's 5/3/2 recency weights normalized to the platform season, each
    multiplied by the lag's exposure (fa_projection.def_rate's form), the
    exposure-weighted rate shrunk toward `target` by den / (den + K).
    (None, 0.0) when no lag carries both a rate and an exposure."""
    w = weights or _engine_weights()
    num = den = 0.0
    for lag, v, e in items:
        if v is None or e is None or e <= 0:
            continue
        wl = float(w[int(lag) - 1]) / float(w[0])
        num += wl * float(e) * float(v)
        den += wl * float(e)
    if den <= 0:
        return None, 0.0
    rate = num / den
    k = float(k_shrink or 0.0)
    return target + (rate - target) * den / (den + k), den


def naive_rate(items):
    """The Gate 1 NAIVE comparator: the 5/4/3 exposure-weighted raw rate over
    the seasons present (no shrink, no age term); None with no season."""
    num = den = 0.0
    for lag, v, e in items:
        if v is None or e is None or e <= 0:
            continue
        w = NAIVE_WEIGHTS[int(lag) - 1]
        num += w * float(e) * float(v)
        den += w * float(e)
    return num / den if den > 0 else None


def _curve_at(curve: dict | None, age: float) -> float:
    """The smoothed delta moving INTO `age` on a {age: slot} curve, nearest
    supported age (fa_projection.curve_delta's rule); 0 without a curve."""
    if not curve:
        return 0.0
    ages = sorted(int(a) for a in curve)
    a = min(ages, key=lambda x: abs(x - age))
    slot = curve.get(a, curve.get(str(a)))
    return float(slot.get("delta_smooth", slot["delta"]))


def age_walk(curve: dict | None, age, horizon: int = HORIZONS) -> list[float]:
    """Cumulative age deltas by horizon: the delta into `age` at year 1 (the
    step project_player applies to every component), then into age + t."""
    a0 = float(age) if age else 30.0
    out, c = [], 0.0
    for t in range(horizon):
        c += _curve_at(curve, a0 + t)
        out.append(c)
    return out


def component_age_curves(model) -> dict:
    """{'bsr': {role: curve}, 'fld': {role: curve}} off an aging_v3.AgingModel
    (unifier U5); {} when the model is None."""
    if model is None:
        return {}
    return {c: model.component_curve("hit", c) for c in ("bsr", "fld")}


def _lag_items(feat: dict, rate_key: str, expo_key: str, scale: float = 1.0) -> list:
    return [(k, (None if feat.get(f"{rate_key}_l{k}") is None
                 else float(feat[f"{rate_key}_l{k}"]) * scale),
             feat.get(f"{expo_key}_l{k}")) for k in LAGS]


def exposure_walk(pt_y1, side: str, role: str, age, curves: dict,
                  horizon: int = HORIZONS) -> list[float]:
    """H0 / P0: the champion's exposure walk. Year 1 is project_player's
    pt_proj; each later year adds the 'pt' curve delta at the advancing age
    (fa_projection.curve_delta, the profile role), floored at 0, exactly as
    fa_market._decay_path walks e. Pitchers walk BF (IP = BF / 4.3)."""
    import fa_projection as fp
    a = int(age) if age else 30
    e = float(pt_y1 or 0.0)
    out = []
    for t in range(horizon):
        if t > 0:
            a += 1
            e += fp.curve_delta(curves, side, role, "pt", a)
            e = max(0.0, e)
        out.append(e)
    return out


def engine_projection(hist: list[dict], side: str, base: int, age, curves: dict,
                      league: dict, horizon: int = HORIZONS,
                      in_progress: tuple[int, float] | None = None) -> dict | None:
    """The incumbent engine's part of a line: project_player at `base`, its
    rate_path walk (H1 / P1 / P2) and the exposure walk (H0 / P0). None when
    the engine has no projection for the history. `in_progress` is the
    served export's (season, fraction) for the season under way, passed to
    project_player exactly as fa_market.contract_war_path passes it, so the
    served component lines walk the same projection the served row does
    (task PJ_6); the DEV frame passes None."""
    import fa_projection as fp
    if not hist:
        return None
    proj = fp.project_player(hist, side, int(base), curves, league, age,
                             in_progress=in_progress)
    if proj is None:
        return None
    role = proj["role"]
    drole = fp.profile_role(hist, side, role, league)
    rates = fp.rate_path(proj, side, curves, league, horizon)
    if len(rates) < horizon:
        return None
    return {"proj": proj, "role": role, "decay_role": drole, "rates": rates,
            "expo": exposure_walk(proj["pt_proj"], side, drole, age, curves, horizon),
            "pt_y1": float(proj["pt_proj"] or 0.0), "age": age}


# --------------------------------------------------------------------------
# The Savant terms
# --------------------------------------------------------------------------

def savant_value(feat: dict, term: str):
    """The most recent lag's value of a Savant term as the head reads it:
    sprint speed (ft/s), OAA per 1,000 fielded innings, arm strength; None
    when no lag carries it."""
    _head, key = SAVANT_TERMS[term]
    for k in LAGS:
        v = feat.get(f"{key}_l{k}")
        if v is None:
            continue
        if term == "oaa":
            inn = feat.get(f"inn_total_l{k}")
            if not inn or inn <= 0:
                continue
            return float(v) / float(inn) * 1000.0
        return float(v)
    return None


def _savant_term(feat: dict, term: str, params: dict | None) -> float:
    """beta x (value - center) when the term is admitted and present, else 0."""
    spec = ((params or {}).get("savant") or {}).get(term) or {}
    if not spec.get("admitted") or spec.get("beta") is None:
        return 0.0
    v = savant_value(feat, term)
    if v is None:
        return 0.0
    return float(spec["beta"]) * (v - float(spec.get("center") or 0.0))


# --------------------------------------------------------------------------
# The heads
# --------------------------------------------------------------------------

def _range_for(params: dict | None, comp: str, h: int, tier: str):
    r = (((params or {}).get("ranges") or {}).get(comp) or {}).get(str(h)) or {}
    q = r.get(tier)
    if not q or q.get("q10") is None or q.get("q90") is None:
        return None
    return float(q["q10"]), float(q["q90"])


def hitter_heads(eng: dict, feat: dict, params: dict | None, consts: dict,
                 age_curves: dict | None, horizon: int = HORIZONS) -> dict:
    """H0 to H8 for one hitter from the engine part, his lag inputs and the
    frozen params. A component with no history returns None on every season
    and is listed in `not_projected`."""
    import fwar_frame as F
    p = params or {}
    shrink = p.get("shrink") or {}
    k_bsr = float(shrink.get("bsr_pa", 0.0))
    k_fld = float(shrink.get("fld_inn", 0.0))
    role = "C" if eng["role"] == "C" else "H"
    ac = age_curves or {}
    bsr_curve = (ac.get("bsr") or {}).get(role) or (ac.get("bsr") or {}).get("H")
    fld_curve = (ac.get("fld") or {}).get(role) or (ac.get("fld") or {}).get("H")
    not_projected: list[str] = []

    # H3 ingredients: baserunning runs per 600 PA, shrunk toward 0 by PA
    bsr0, _ = marcel_rate(_lag_items(feat, "baseRunning_pa", "pa", 600.0), k_bsr, 0.0)
    if bsr0 is not None:
        bsr0 += _savant_term(feat, "sprint", p)
    bsr_age = age_walk(bsr_curve, eng["age"], horizon)

    # H4 / H5 ingredients: fielding per 1,000 innings, framing per 1,000
    # catcher innings, fielded innings per PA and the position mix
    fld_items, frm_items, inn_items = [], [], []
    inn_by_pos = {pos: 0.0 for pos in FIELD_POSITIONS}
    inn_w = 0.0
    w = _engine_weights()
    for k in LAGS:
        pa, inn = feat.get(f"pa_l{k}"), feat.get(f"inn_total_l{k}")
        if feat.get(f"fld_missing_l{k}") or inn is None or pa is None or pa <= 0:
            continue
        inn_items.append((k, float(inn) / float(pa), pa))
        fpa = feat.get(f"fielding_pa_l{k}")
        if fpa is not None and inn > 0:
            fld_items.append((k, float(fpa) * float(pa) / float(inn) * 1000.0, inn))
        inn_c = feat.get(f"inn_C_l{k}") or 0.0
        frm = feat.get(f"framing_pa_l{k}")
        if frm is not None and inn_c > 0:
            frm_items.append((k, float(frm) * float(pa) / float(inn_c) * 1000.0, inn_c))
        wl = float(w[k - 1]) / float(w[0])
        for pos in FIELD_POSITIONS:
            inn_by_pos[pos] += wl * float(feat.get(f"inn_{pos}_l{k}") or 0.0)
        inn_w += wl * float(inn)
    r_inn, _ = marcel_rate(inn_items, 0.0)
    shares = ({pos: v / inn_w for pos, v in inn_by_pos.items()} if inn_w > 0
              else {pos: 0.0 for pos in FIELD_POSITIONS})
    fld0, _ = marcel_rate(fld_items, k_fld, 0.0)
    if fld0 is None and inn_items and r_inn == 0.0:
        fld0 = 0.0                    # a pure DH fields nothing and is projected 0
    if fld0 is not None:
        fld0 += _savant_term(feat, "oaa", p) + _savant_term(feat, "arm", p)
    frm0, _ = marcel_rate(frm_items, k_fld, 0.0)
    if frm0 is None:
        frm0 = 0.0                    # no catcher innings: no framing line
    fld_age = age_walk(fld_curve, eng["age"], horizon)

    if bsr0 is None:
        not_projected.append("bsr")
    if r_inn is None:
        not_projected.extend(["fld", "pos"])
    elif fld0 is None:
        not_projected.append("fld")

    import fa_market as fm
    tier = fm._band_bucket("hit", eng["pt_y1"])
    lines = {}
    for t in range(horizon):
        h = t + 1
        pa = float(eng["expo"][t])
        rt = eng["rates"][t]
        woba = rt["woba"]
        wraa = F.wraa(woba, consts["eng_lg_woba"], consts["woba_scale"], pa)
        bat = (wraa + F.park_runs(pa, consts["lg_r_pa"], consts["pf"])
               + F.league_batting_runs(pa, consts["lg_r_pa"], consts["lg_nonp_wrc_pa"]))
        bsr600 = None if bsr0 is None else bsr0 + bsr_age[t]
        bsr = None if bsr600 is None else bsr600 * pa / 600.0
        if r_inn is None:
            inn = dh_inn = inn_c = fld = pos = fld1000 = None
        else:
            inn = r_inn * pa
            dh_inn = max(0.0, consts["inn_per_pa"] * pa - inn)
            inn_c = shares["C"] * inn
            pos = F.positional({pos_: shares[pos_] * inn for pos_ in FIELD_POSITIONS}, dh_inn)
            if fld0 is None:
                fld = fld1000 = None
            else:
                fld1000 = fld0 + fld_age[t]
                fld = fld1000 * inn / 1000.0 + frm0 * inn_c / 1000.0
        lg = consts["lg_adj_rate"] * pa
        rep = consts["rep_per_pa"] * pa
        war_comp = (None if any(v is None for v in (bat, bsr, fld, pos))
                    else (bat + bsr + fld + pos + lg + rep) / consts["rpw"])
        line = {"pa": pa, "k_pct": None, "bb_pct": None, "iso": None, "babip": None,
                "hr_pa": None, "woba": woba, "wrc_plus": rt.get("wrc_plus"),
                "bat": bat, "bsr": bsr, "fld": fld, "pos": pos, "lg": lg, "rep": rep,
                "war_comp": war_comp,
                "fld_pos": (None if fld is None or pos is None else fld + pos),
                "inn": inn, "dh_inn": dh_inn, "inn_c": inn_c, "bsr600": bsr600,
                "fld1000": fld1000, "frm1000": frm0}
        ranges = {}
        for comp, runs in (("bsr", bsr), ("fld_pos", line["fld_pos"]), ("batting", bat),
                           ("league", lg), ("replacement", rep), ("pa", pa)):
            q = _range_for(p, comp, h, tier)
            if q is not None and runs is not None:
                ranges[comp] = (runs + q[0], runs + q[1])
        line["ranges"] = ranges
        lines[h] = line
    # the year-1 rates come from the engine's own projection
    for c in ("k_pct", "bb_pct", "iso", "babip", "hr_pa"):
        lines[1][c] = eng["proj"].get(c)
    return {"role": eng["role"], "decay_role": eng["decay_role"], "age": eng["age"],
            "pt_y1": eng["pt_y1"], "tier": tier, "shares": shares, "lines": lines,
            "not_projected": sorted(set(not_projected))}


def pitcher_heads(eng: dict, feat: dict, params: dict | None, consts: dict,
                  horizon: int = HORIZONS, *, price_gmli: bool = True) -> dict:
    """P0 to P5 for one pitcher: the IP walk, the role mix, FIP from
    rate_path, the fwar_frame chain at PF 1.0 with no framing charge and the
    single blended line (replacement continuous in GS/G, the gmLI multiplier
    on the relief share), WARIP held, P4 gmLI shrunk toward 1.0 by relief
    games, P5 the RA9 gap shrunk toward 0 by IP.

    price_gmli False (the served export when the P4 head is not served,
    task PJ_8) prices the relief share at gmLI 1.0, the value the served
    engine assumes, so the runs gmLI adds ride in the gap line; the P4 gmLI
    line itself is still computed. The DEV and holdout frames keep True."""
    import fwar_frame as F
    p = params or {}
    shrink = p.get("shrink") or {}
    k_gm = float(shrink.get("gmli_g", 0.0))
    k_gap = float(shrink.get("ra9gap_ip", 0.0))
    not_projected: list[str] = []
    ipg_items = [(k, (None if not feat.get(f"g_l{k}") else
                      float(feat.get(f"ip_l{k}") or 0.0) / float(feat[f"g_l{k}"])),
                  feat.get(f"g_l{k}")) for k in LAGS]
    ip_per_g, _ = marcel_rate(ipg_items, 0.0)
    gs_share, _ = marcel_rate(_lag_items(feat, "gs_share", "g"), 0.0)
    gm_items = [(k, feat.get(f"gmli_l{k}"),
                 (None if feat.get(f"g_l{k}") is None
                  else float(feat[f"g_l{k}"]) - float(feat.get(f"gs_l{k}") or 0.0)))
                for k in LAGS]
    gmli, _ = marcel_rate(gm_items, k_gm, 1.0)
    gap100, _ = marcel_rate(_lag_items(feat, "ra9gap_100ip", "ip"), k_gap, 0.0)
    if gmli is None and eng["role"] == "RP":
        not_projected.append("gmli")
    if gap100 is None:
        not_projected.append("ra9_gap")
    if ip_per_g is None or gs_share is None:
        not_projected.append("war_fip")
    import fa_market as fm
    tier = fm._band_bucket("pit", eng["pt_y1"])
    lg9 = consts["lg_fipr9"]
    lines = {}
    for t in range(horizon):
        h = t + 1
        bf = float(eng["expo"][t])
        ip = bf / BF_PER_IP
        fip = eng["rates"][t]["fip"]
        pfr = F.pfipr9(F.fipr9(fip, consts["lg_ra9"], consts["lg_era"]), consts["pf"])
        pfr += F.framing_charge_per9(0.0, ip)          # no framing charge
        raap9 = F.raap9(lg9, pfr)
        g = gs = relief_ip = war_fip = drpw = None
        if ip_per_g is not None and gs_share is not None and ip > 0 and ip_per_g > 0:
            g = ip / ip_per_g
            gs = gs_share * g
            relief_ip = ip * (1.0 - gs_share)
            line = F.blended_line(ip, g, gs, lg9, lg9, pfr, gmli if price_gmli else None)
            war_fip, _rar = F.pitcher_war([line], consts["warip"])
            drpw = line["drpw"]
        elif ip_per_g is not None and gs_share is not None:
            g = gs = relief_ip = 0.0
            war_fip = 0.0
        war_ra9 = (None if war_fip is None or gap100 is None
                   else war_fip + gap100 * ip / 100.0)
        line_out = {"ip": ip, "bf": bf, "g": g, "gs": gs, "gs_share": gs_share,
                    "relief_ip": relief_ip, "k_pct": None, "bb_pct": None, "hr_bf": None,
                    "fip": fip, "gmli": gmli, "war_fip": war_fip, "war_ra9": war_ra9,
                    "ra9gap_100ip": gap100, "fip_runs_100ip": raap9 * 100.0 / 9.0,
                    "raap9": raap9, "drpw": drpw}
        ranges = {}
        gm_rate = None if gmli is None else F.leverage_multiplier(gmli) * float(p.get("R_relief") or 0.0)
        for comp, runs in (("ra9_gap", None if gap100 is None else gap100 * consts["rpw"] * ip / 100.0),
                           ("gmli_relief", None if gm_rate is None or relief_ip is None
                            else gm_rate * relief_ip / 100.0),
                           ("ip", ip)):
            q = _range_for(p, comp, h, tier)
            if q is not None and runs is not None:
                ranges[comp] = (runs + q[0], runs + q[1])
        line_out["ranges"] = ranges
        lines[h] = line_out
    for c in ("k_pct", "bb_pct", "hr_bf"):
        lines[1][c] = eng["proj"].get(c)
    return {"role": eng["role"], "decay_role": eng["decay_role"], "age": eng["age"],
            "pt_y1": eng["pt_y1"], "tier": tier, "lines": lines,
            "not_projected": sorted(set(not_projected))}


def project_components(hist_by_side: dict, base: int, age, curves: dict, war_map: dict,
                       league: dict, consts: dict, frame_inputs: dict, params: dict | None,
                       *, age_curves: dict | None = None, horizon: int = HORIZONS,
                       in_progress: tuple[int, float] | None = None,
                       price_gmli: bool = True) -> dict:
    """The component lines of one veteran at `base` for horizons 1..`horizon`.

    hist_by_side  {"hit": [corpus rows B-3..B-1], "pit": [...]}; a two-way
                  player carries both sides
    curves        the point-in-time fitted_models(corpus, B - 1) curves
    war_map       accepted for parity with the engine's call shape; no head
                  reads it (a WAR map is a WAR-label model)
    consts        season_constants(B - 1, ...)
    frame_inputs  {"hit": feat, "pit": feat}: the frame row's lag features
    params        the frozen params (None: no shrink, no Savant term, no range)
    age_curves    component_age_curves(aging_v3 model fitted at B - 1)
    in_progress   the served export's (season, fraction) (engine_projection);
                  None on the DEV frame
    price_gmli    passed to pitcher_heads (False: relief priced at gmLI 1.0)

    Returns {"hit": block | None, "pit": block | None, "two_way": bool}; a
    block carries `lines` {h: line}, `not_projected` and the exposure tier.
    A component the player has no history in is None on every season of its
    line and named in `not_projected`."""
    out: dict = {"hit": None, "pit": None, "base": int(base)}
    for side in ("hit", "pit"):
        hist = (hist_by_side or {}).get(side) or []
        feat = (frame_inputs or {}).get(side)
        if not hist or feat is None:
            continue
        eng = engine_projection(hist, side, base, age, curves, league, horizon,
                                in_progress=in_progress)
        if eng is None:
            continue
        if side == "hit":
            out[side] = hitter_heads(eng, feat, params, consts, age_curves, horizon)
        else:
            out[side] = pitcher_heads(eng, feat, params, consts, horizon,
                                      price_gmli=price_gmli)
    out["two_way"] = out["hit"] is not None and out["pit"] is not None
    return out


# --------------------------------------------------------------------------
# Comparators and scorer rows (proj_eval.run_components contract)
# --------------------------------------------------------------------------

def naive_components(side: str, feat: dict) -> dict:
    """The NAIVE comparator per scored component: the 5/4/3 exposure-weighted
    raw rate of the lag inputs, in the scorer's units (runs per 600 PA, runs
    per 100 IP; gmLI and the RA9 gap as their own quantities)."""
    if side == "hit":
        fp_items = []
        for k in LAGS:
            pa = feat.get(f"pa_l{k}")
            parts = [feat.get(f"{p}_pa_l{k}") for p in ("fielding", "framing", "positional")]
            if pa and all(v is not None for v in parts):
                fp_items.append((k, sum(parts) * 600.0, pa))
        return {
            "bsr": naive_rate(_lag_items(feat, "baseRunning_pa", "pa", 600.0)),
            "fld_pos": naive_rate(fp_items),
            "batting": naive_rate(_lag_items(feat, "batting_pa", "pa", 600.0)),
            "league": naive_rate(_lag_items(feat, "wLeague_pa", "pa", 600.0)),
            "replacement": naive_rate(_lag_items(feat, "replacement_pa", "pa", 600.0)),
        }
    gm_items = [(k, feat.get(f"gmli_l{k}"),
                 (None if feat.get(f"g_l{k}") is None
                  else float(feat[f"g_l{k}"]) - float(feat.get(f"gs_l{k}") or 0.0)))
                for k in LAGS]
    return {"gmli": naive_rate(gm_items),
            "ra9gap_100ip": naive_rate(_lag_items(feat, "ra9gap_100ip", "ip")),
            "fip": naive_rate(_lag_items(feat, "fip", "ip"))}


def implicit_def_rate(mlbam, base: int) -> float:
    """IMPLICIT for Fld + Pos: fa_projection.def_rate (the served engine's
    shrunk defensive plus positional runs per 600 PA, point in time)."""
    import fa_projection as fp
    return float(fp.def_rate(mlbam, int(base)))


def scorer_rows(frame_row: dict, side: str, cells, consts_by_season: dict,
                r_relief: float) -> list[dict]:
    """The proj_eval.run_components rows of one frame row, one per horizon
    inside `cells`. Labels are the frame's frozen-vintage run parts in runs:
    bsr = baseRunning; fld_pos = fielding + framing + positional; batting,
    league (wLeague), replacement; for pitchers ra9_gap = (ra9War - war) x the
    label season's runs per win, gmli_relief = m(gmli) x R x relief IP / 100
    with m the relief multiplier and relief IP = IP x (1 - GS / G); pa and ip
    are the exposure labels. No row carries a key named war."""
    import fwar_frame as F
    feat = frame_row["feat"]
    base = int(frame_row["base"])
    cell_set = {(int(b), int(h)) for b, h in cells}
    out = []
    for h, lab in (frame_row.get("labels") or {}).items():
        if (base, int(h)) not in cell_set:
            continue
        L = int(lab["season"])
        if side == "hit":
            pa = lab.get("pa")
            exposure = float(pa) if pa else 0.0
            fp_parts = [lab.get("fielding"), lab.get("framing"), lab.get("positional")]
            labels = {"bsr": lab.get("baseRunning"),
                      "fld_pos": (sum(fp_parts) if all(v is not None for v in fp_parts) else None),
                      "batting": lab.get("batting"), "league": lab.get("wLeague"),
                      "replacement": lab.get("replacement")}
            hist = {base - k: feat.get(f"pa_l{k}") for k in LAGS if feat.get(f"pa_l{k}") is not None}
            row = {"mlbam": frame_row["mlbam"], "side": "hit", "base": base, "h": int(h),
                   "label_season": L, "exposure": exposure,
                   "exposure_base": feat.get("pa_l1"), "exposure_hist": hist, "labels": labels}
        else:
            ip = lab.get("ip")
            exposure = float(ip) if ip else 0.0
            g, gs = lab.get("g"), lab.get("gs")
            relief_ip = (exposure * (1.0 - float(gs or 0.0) / float(g)) if g else 0.0)
            rpw_l = (consts_by_season.get(L) or {}).get("rpw")
            gap = lab.get("ra9gap")
            gm = lab.get("gmli")
            labels = {"ra9_gap": (None if gap is None or rpw_l is None else float(gap) * float(rpw_l)),
                      "gmli_relief": (None if gm is None
                                      else F.leverage_multiplier(gm) * r_relief * relief_ip / 100.0)}
            hist = {base - k: feat.get(f"ip_l{k}") for k in LAGS if feat.get(f"ip_l{k}") is not None}
            row = {"mlbam": frame_row["mlbam"], "side": "pit", "base": base, "h": int(h),
                   "label_season": L, "exposure": exposure,
                   "exposures": {"gmli_relief": relief_ip},
                   "exposure_base": feat.get("ip_l1"), "exposure_hist": hist, "labels": labels}
        out.append(row)
    return out


# --------------------------------------------------------------------------
# The frozen params
# --------------------------------------------------------------------------

def params_hash(params: dict) -> str:
    """sha256 of the canonical JSON of the params (sorted keys, no spaces),
    so the hash does not depend on the file's line endings or indent."""
    blob = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_params(path: Path | None = None) -> dict:
    p = Path(path) if path else PARAMS_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def check_params(params: dict, recorded_hash: str) -> dict:
    """Raise unless the params hash to `recorded_hash` (the gate's record)."""
    got = params_hash(params)
    if got != str(recorded_hash).strip().lower():
        raise ParamsHashMismatch(f"params hash {got} != recorded {recorded_hash}")
    return params
