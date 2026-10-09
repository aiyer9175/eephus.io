# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The component projection FRAME: lag inputs and component labels per
(veteran, base season), built point in time. No model, no score, no served key.

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
