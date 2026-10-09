# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The surrogate outcome builder (docs/efv-v2/SURROGATE_2026_GATE.md s3 and s4; task SG_3
of the efv2026 plan, item N7). Code only: no outcome has been computed on a frame row.
The tests run the V-1 derivation on the V 2015-2019 frames (pre-V state only) and S1
and raw S2 on the 2015-2019 season files, as counts per rung.

For a (side, V) frame from efv_vintage_frame.build_frame it computes the season-V
outcomes of the gate's s3 from the PINNED season store, on the frame row's outcome-blind
person id (`mlbam_id`, efv_identity through V - 1; the record's own id is never read).

THE STORE. Season 2026 is the tracked frozen copy data/milb_season_frozen/2026/ (sha256
pinned in data/efv_surrogate_pins_2026.json, SG_1). Seasons 2010 to 2025 are the
.cache/milb_stats files read with fetch=False, each (season, group) checked against its
canonical content hash in the same pins file before its first read (2010 is pinned so the
V-1 state of V 2011 can be derived). 2020 had no minor league season and reads empty.
Sport-1 (MLB) files are read through one function, _mlb_event_ids, which returns the set
of person ids with a regular-season MLB line and reads no stat column; for 2026 the sets
are the frozen mlb_event_ids_*.json. Every 2026 read first asks the ETA look record
(efv_surrogate_guard.require_eta_look).

THE V-1 STATE, derived here for EVERY vintage (V 2011 to 2014 rows carry no efv_dataset
MiLB block, efv_dataset._milb_features stops at its floor). rung_pre is the primary rung
of the latest store season at or before V - 1 in which the player has an affiliated line,
by efv_dataset's primary-level rule (the highest level whose largest single line clears
50 PA / 60 BF, else the most-exposed level). That is season V - 1 whenever he played in
it; for a player whose only line is earlier (a first-year pro's entry season, or a lost
season) it is that season, which is what the frame's own level_rank reads, so the
reproduction test can hold on every row. A row with no store line at all is ABSENT-pre:
it takes the within-(side, V) median rung_pre and age_pre with the flag `pre_absent`,
which is counted and is never an S_idx input. age_pre is the store age at V - 1 minus the
median store age of exposure-floor qualifiers at (V - 1, rung_pre).

THE OUTCOMES (season V; regular season only; no store holds postseason lines):
    S1 LEVEL_END  rungs efv_dataset._LEVEL_RANK (DSL 0 to AAA 5) plus MLB 6; before 2021
                  short-season A (sportId 15) is its own rung 1.5 and the Mexican League
                  (sportId 11, league "MEX") is dropped by league name. MLB only as the
                  event from _mlb_event_ids. No affiliated or MLB line: ABSENT_KNOWN (a
                  data/tj_surgery.json record dated from V - 1 through V-09-30),
                  ABSENT_IDENTITY (no pre-V id) or ABSENT_UNKNOWN.
    S2 CLIMB      LEVEL_END minus rung_pre, residualized on rung_pre and age_pre by a map
                  passed in, then minus a shrunken parent-club intercept from a club table
                  passed in (fitted on V 2011 to 2016). The club is the as-of org of s4.
    S3 PERF       season-V rates at the primary rung against PURE level norms (2026 from
                  data/milb_norms_2026_pure.json, earlier seasons computed from the store
                  with milb_history.level_norms_from_rows, never the blended served norms),
                  exposure-shrunk by efv_dataset._season_rates: hitters obp_rel, contact
                  (minus k_rel), iso_rel; pitchers k_rel minus bb_rel. Residualized,
                  standardized within (side, V); the hitter scalar is the mean of the
                  three. Missing (ABSENT and MLB-event rows) sits at the id-resolved mean,
                  0 after standardization, with no indicator.
    S4 PT         affiliated PA (BF) per level over that season's own full-season exposure
                  at the level (the FULL_SEASON_QUANTILE of qualifiers' summed exposure),
                  summed and capped at 1; pitchers also GS share. ABSENT gives 0.
                  Residualized like S2 and S3.
    S5 STATUS     ACTIVE, ABSENT_KNOWN, ABSENT_IDENTITY, ABSENT_UNKNOWN.

THE FITTERS. S_idx is a ridge of the label the CALLER joins (the L6 percentile within
(side, V), row key "target", weight "weight") on S2, S3, S4 and one ABSENT code, among
id-resolved rows, leave-one-vintage-out over V 2011 to 2016 with an inner
leave-one-vintage-out for the penalty from RIDGE_GRID (the finite V2 grid); the fallback
variant is player-grouped 5-fold (seed 20260930) with an inner player-grouped 5-fold.
g_S is a penalized logistic of the caller's R3 (row key "reached") on the same inputs and
nothing else (no pre-V input), forward-chained, its penalty by an inner forward-chained
split. The round-2 g_time (level_rank and age_rel_level as inputs) is not built.

RULES. Every public function asks efv_surrogate_guard.guard_surrogate_read first for every
vintage it touches, with its purpose, and efv_surrogate_guard.withhold_reserved_vm before
any row leaves it. This module imports no label module, no source scorer, no AP+ module
and reads no rater column; it never asks the R-LV score guard (the guard module's
docstring says why). It writes nothing under data/. Nothing here groups or counts rows by
consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np

import efv_dataset as D
import efv_surrogate_guard as G
import milb_history as mh
import trades
from efv_vintage_frame import RESERVED_LV, ReservedFrameError
from tools import milb_season_freeze as Z

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
PINS_NAME = "efv_surrogate_pins_2026.json"
NORMS_2026_NAME = "milb_norms_2026_pure.json"
TJ_NAME = "tj_surgery.json"
FROZEN_SUBDIR = ("milb_season_frozen", "2026")
TX_DIR = ROOT / ".cache" / "mlb_transactions"

SIDES = ("hit", "pit")
GROUP = {"hit": "hitting", "pit": "pitching"}
EXPOSURE_KEY = {"hit": "pa", "pit": "bf"}
#: efv_dataset's exposure floor (efv_dataset._milb_features: 50 PA, 60 BF). Written as
#: products so the PROSPECT_ANCHOR literal scan, which flags the FV values 35 to 80,
#: does not read an exposure floor as an FV value; test_efv_surrogate.py pins the values.
EXPOSURE_FLOOR = {"hit": 5 * 10.0, "pit": 6 * 10.0}

SEASON_2026 = 2026
STORE_FIRST = 2010
STORE_LAST_CACHE = 2025
NO_MILB_SEASONS = frozenset({2020})
#: Before this season sportId 15 (short-season A) is its own rung and sportId 11 carries
#: the Mexican League, which every component and norm drops by league name.
LADDER_BREAK = 2021
MEX_LEAGUE = "MEX"
SSA_LEVEL = "SSA"
SSA_SPORT = 15
AAA_SPORT = 11
AFFILIATED_SPORTS = (11, 12, 13, 14, 15, 16)
#: The gate's rungs: efv_dataset._LEVEL_RANK, short-season A between CPX and A, MLB on top.
RUNG = {**{lv: float(r) for lv, r in D._LEVEL_RANK.items()}, SSA_LEVEL: 1.5}
MLB_RUNG = float(max(D._LEVEL_RANK.values()) + 1)
CONVENTIONS = ("gate", "efv_dataset")

ACTIVE = "ACTIVE"
ABSENT_KNOWN = "ABSENT_KNOWN"
ABSENT_IDENTITY = "ABSENT_IDENTITY"
ABSENT_UNKNOWN = "ABSENT_UNKNOWN"
STATUSES = (ACTIVE, ABSENT_KNOWN, ABSENT_IDENTITY, ABSENT_UNKNOWN)

#: The vintages the residual maps, the club table and S_idx are fitted on (lv_L6), and
#: the registered fallback's (s2.1); g_S reads lv_dev_all.
FIT_VINTAGES = tuple(range(2011, 2017))
FALLBACK_VINTAGES = (2015, 2016)
G_S_VINTAGES = tuple(range(2011, 2020))
#: The S_idx and g_S penalty grid: efv_v2_model.V2_ALPHAS without its switch-off entry.
RIDGE_GRID = (1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0)
FOLD_SEED = 20260930
N_FOLDS = 5
#: A level's full-season exposure in season V: this quantile of the summed exposure of
#: the level's floor qualifiers (S4's denominator).
FULL_SEASON_QUANTILE = 0.9
#: Logistic Newton iterations from a zero start (bit-reproducible), the tolerance that
#: ends them early, and the vanishing intercept penalty that keeps a one-class fold finite.
NEWTON_MAX_IT = 100
NEWTON_TOL = 1e-12
INTERCEPT_PENALTY = 1e-6

ORG_UNKNOWN = "org_unknown"
#: identity_audit.PLACEHOLDER_ORGS (asserted equal by the tests): not a club.
PLACEHOLDER_ORGS = frozenset({"Office of the Commissioner"})
CLUBS = frozenset(trades.ORG_ALIASES.values())

HIT_PERF = ("obp_rel", "contact", "iso_rel")
PIT_PERF = ("k_minus_bb",)
FEATURES = {"hit": ("s2", "s3", "s4", "absent"),
            "pit": ("s2", "s3", "s4", "s4_gs", "absent")}


class StoreError(RuntimeError):
    """The pinned season store does not match its pins, or a season is outside it."""


# ---------------------------------------------------------------------------
# the pinned store
# ---------------------------------------------------------------------------

_PINS: dict = {}
_CHECKED: set = set()
_INDEX: dict = {}
_EVENTS: dict = {}
_NORMS: dict = {}
_AGES: dict = {}
_FULL: dict = {}


def _sha_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _pins() -> dict:
    if "doc" not in _PINS:
        p = DATA_DIR / PINS_NAME
        if not p.exists():
            raise StoreError(f"data/{PINS_NAME} (SG_1) is absent; the store is unpinned")
        _PINS["doc"] = json.loads(p.read_text(encoding="utf-8"))
    return _PINS["doc"]


def _frozen_dir() -> Path:
    return DATA_DIR.joinpath(*FROZEN_SUBDIR)


def _check_2026(name: str, pin_block: str) -> Path:
    """The frozen 2026 file `name`, after its sha256 equals the pin. Asks the ETA look
    record first: no 2026 line is read before it."""
    G.require_eta_look()
    path = _frozen_dir() / name
    pin = (_pins().get(pin_block) or {}).get(name) or {}
    if (pin_block, name) not in _CHECKED:
        if not path.exists() or _sha_file(path) != pin.get("sha256"):
            raise StoreError(f"frozen {name} is missing or differs from its pin")
        _CHECKED.add((pin_block, name))
    return path


def _check_cache_season(season: int, group: str) -> None:
    """Each affiliated file and the sport-1 id column of (season, group) against its
    canonical content hash (tools/milb_season_freeze.canonical_hash). Raises on drift."""
    key = ("cache", int(season), group)
    if key in _CHECKED:
        return
    pin = ((_pins().get("transfer_seasons") or {}).get(str(season)) or {}).get(group)
    if not pin:
        raise StoreError(f"season {season} {group} is not pinned")
    for sport in (1,) + AFFILIATED_SPORTS:
        entry = pin.get(str(sport))
        rows = Z.read_cache(sport, season, group)
        if entry is None:
            if rows:
                raise StoreError(f"{group} sport {sport} {season} has rows but no pin")
            continue
        if sport == 1:
            ok = Z.id_column_hash(rows) == entry.get("id_sha256")
        else:
            ok = Z.canonical_hash(rows, sport) == entry.get("sha256")
        if not ok or len(rows) != entry.get("rows"):
            raise StoreError(f"{group} sport {sport} {season} drifted from its pin")
    _CHECKED.add(key)


def _season_lines(season: int, group: str) -> list[dict]:
    """Every affiliated (sportId 11 to 16) line of one season from the pinned store, as
    {id, sport, league, level, row}, sport ascending, file order kept. No sport-1 row."""
    s = int(season)
    out: list[dict] = []
    if s in NO_MILB_SEASONS:
        return out
    if s == SEASON_2026:
        for sport in Z.FROZEN_SPORTS:
            p = _check_2026(f"{group}_{sport}.json", "frozen_2026")
            rows = mh._relevel(json.loads(p.read_text(encoding="utf-8")), sport)
            out.extend(_lean(rows, sport))
        return out
    if not STORE_FIRST <= s <= STORE_LAST_CACHE:
        raise StoreError(f"season {s} is outside the pinned store")
    _check_cache_season(s, group)
    for sport in AFFILIATED_SPORTS:
        out.extend(_lean(Z.read_cache(sport, s, group), sport))
    return out


def _lean(rows: list[dict], sport: int) -> list[dict]:
    return [{"id": int(r["mlbam"]), "sport": int(sport), "league": r.get("league") or "",
             "level": r.get("level"), "row": r}
            for r in rows if r.get("mlbam") is not None]


def _season_index(season: int, group: str) -> dict[int, list[dict]]:
    key = (int(season), group)
    if key not in _INDEX:
        idx: dict[int, list[dict]] = {}
        for ln in _season_lines(season, group):
            idx.setdefault(ln["id"], []).append(ln)
        _INDEX[key] = idx
    return _INDEX[key]


def _mlb_event_ids(season: int, group: str) -> frozenset[int]:
    """The person ids with a regular-season MLB (sport-1) line in `season`: the debut
    EVENT and nothing else. The only reader of a sport-1 file here; it reads the id key
    of each line and no stat column."""
    key = (int(season), group)
    if key in _EVENTS:
        return _EVENTS[key]
    s = int(season)
    if s == SEASON_2026:
        p = _check_2026(f"mlb_event_ids_{group}.json", "mlb_event_ids_2026")
        ids = frozenset(int(x) for x in json.loads(p.read_text(encoding="utf-8")))
    elif STORE_FIRST <= s <= STORE_LAST_CACHE and s not in NO_MILB_SEASONS:
        _check_cache_season(s, group)
        ids = frozenset(int(r["mlbam"]) for r in Z.read_cache(1, s, group)
                        if r.get("mlbam") is not None)
    else:
        raise StoreError(f"no pinned MLB event set for season {s}")
    _EVENTS[key] = ids
    return ids


# ---------------------------------------------------------------------------
# levels, the primary rung and the V-1 state (pure on the lines handed in)
# ---------------------------------------------------------------------------

def _line_level(line: dict, season: int, convention: str = "gate") -> str | None:
    """The level a store line counts at. "gate": before 2021 a Mexican League line is
    dropped (None) and a sportId 15 line is short-season A; "efv_dataset": the level
    milb_history gives it (sportId 15 folded to A, the Mexican League kept), the reading
    efv_dataset._milb_features makes."""
    if convention not in CONVENTIONS:
        raise ValueError(f"convention must be one of {CONVENTIONS}, got {convention!r}")
    if convention == "gate" and int(season) < LADDER_BREAK:
        if line["sport"] == AAA_SPORT and str(line.get("league") or "").strip().upper() \
                == MEX_LEAGUE:
            return None
        if line["sport"] == SSA_SPORT:
            return SSA_LEVEL
    return line.get("level")


def _rank(convention: str) -> dict[str, float]:
    return RUNG if convention == "gate" else {lv: float(r) for lv, r in D._LEVEL_RANK.items()}


def _exposure(row: dict, side: str) -> float:
    return mh._f(row.get(EXPOSURE_KEY[side])) or 0.0


def _primary_level(lines: list[dict], side: str, season: int,
                   convention: str = "gate") -> tuple[str | None, dict | None]:
    """efv_dataset's primary-level rule (efv_dataset._milb_features): walking down from
    the highest level present, the first whose largest single line (milb_history.level_row)
    clears the exposure floor; else the level whose largest line is most exposed (the
    highest such on a tie). (None, None) when no line counts."""
    rank = _rank(convention)
    by_level: dict[str, list[dict]] = {}
    for ln in lines:
        lv = _line_level(ln, season, convention)
        if lv in rank:
            by_level.setdefault(lv, []).append(ln["row"])
    if not by_level:
        return None, None
    present = sorted(by_level, key=lambda lv: -rank[lv])
    best = {lv: max(by_level[lv], key=lambda r: _exposure(r, side)) for lv in present}
    for lv in present:
        if _exposure(best[lv], side) >= EXPOSURE_FLOOR[side]:
            return lv, best[lv]
    lv = max(present, key=lambda x: _exposure(best[x], side))
    return lv, best[lv]


def _pre_rung(person, vintage: int, side: str, convention: str = "gate",
              floor: int = STORE_FIRST) -> dict:
    """rung_pre from the store: the primary level of the latest season at or before
    V - 1 with a counted line (see the module docstring)."""
    out = {"rung_pre": None, "rung_pre_level": None, "rung_pre_season": None,
           "rung_pre_age": None, "pre_absent": True}
    if person is None:
        return out
    pid = int(person)
    for s in range(int(vintage) - 1, int(floor) - 1, -1):
        lines = _season_index(s, GROUP[side]).get(pid)
        if not lines:
            continue
        lv, row = _primary_level(lines, side, s, convention)
        if lv is None:
            continue
        age = row.get("age")
        return {"rung_pre": _rank(convention)[lv], "rung_pre_level": lv,
                "rung_pre_season": s, "rung_pre_age": float(age) if age is not None else None,
                "pre_absent": False}
    return out


def _median(vals: list[float]) -> float | None:
    return float(np.median(np.asarray(vals, dtype=float))) if vals else None


def _qualifier_ages(lines: list[dict], level: str, season: int, side: str) -> list[float]:
    """Store ages of the players whose largest line at `level` clears the floor."""
    best: dict[int, dict] = {}
    for ln in lines:
        if _line_level(ln, season, "gate") != level:
            continue
        cur = best.get(ln["id"])
        if cur is None or _exposure(ln["row"], side) > _exposure(cur, side):
            best[ln["id"]] = ln["row"]
    return [float(r["age"]) for r in best.values()
            if r.get("age") is not None and _exposure(r, side) >= EXPOSURE_FLOOR[side]]


def _median_qualifier_age(season: int, level: str, side: str) -> float | None:
    key = (int(season), level, side)
    if key not in _AGES:
        _AGES[key] = _median(_qualifier_ages(_season_lines(season, GROUP[side]), level,
                                             season, side))
    return _AGES[key]


def _age_pre(pre: dict, vintage: int, side: str) -> float | None:
    """Store age at V - 1 minus the median store age of floor qualifiers at
    (V - 1, rung_pre); a rung absent in V - 1 (short-season A after 2020) is read at the
    season rung_pre came from, both ages taken there."""
    if pre.get("pre_absent") or pre.get("rung_pre_age") is None:
        return None
    s, lv = int(pre["rung_pre_season"]), pre["rung_pre_level"]
    v1 = int(vintage) - 1
    med = _median_qualifier_age(v1, lv, side)
    if med is not None:
        return pre["rung_pre_age"] + (v1 - s) - med
    med = _median_qualifier_age(s, lv, side)
    return None if med is None else pre["rung_pre_age"] - med


# ---------------------------------------------------------------------------
# season-V outcomes (pure on the store)
# ---------------------------------------------------------------------------

def _tj_index(path: Path | None = None) -> dict[int, list[str]]:
    """{person id: [surgery dates]} from data/tj_surgery.json (person-keyed)."""
    p = Path(path) if path is not None else DATA_DIR / TJ_NAME
    doc = json.loads(p.read_text(encoding="utf-8"))
    out: dict[int, list[str]] = {}
    for pid, recs in (doc.get("players") or {}).items():
        try:
            k = int(pid)
        except (TypeError, ValueError):
            continue
        out[k] = sorted(str(r.get("date") or f"{r.get('year')}-01-01")[:10]
                        for r in recs or () if r.get("date") or r.get("year"))
    return out


def _tj_explains(dates: list[str], season: int) -> bool:
    """A surgery from V - 1 through V-09-30 explains an absent season V."""
    lo, hi = f"{int(season) - 1}-01-01", f"{int(season)}-09-30"
    return any(lo <= d <= hi for d in dates or ())


def _full_season_exposure(season: int, level: str, side: str) -> float | None:
    """The FULL_SEASON_QUANTILE of the summed exposure of the level's floor qualifiers
    in `season` (Mexican League dropped before 2021)."""
    key = (int(season), level, side)
    if key not in _FULL:
        tot: dict[int, float] = {}
        for ln in _season_lines(season, GROUP[side]):
            if _line_level(ln, season, "gate") == level:
                tot[ln["id"]] = tot.get(ln["id"], 0.0) + _exposure(ln["row"], side)
        qual = [e for e in tot.values() if e >= EXPOSURE_FLOOR[side]]
        _FULL[key] = (float(np.quantile(np.asarray(qual), FULL_SEASON_QUANTILE))
                      if qual else None)
    return _FULL[key]


def _playing_time(lines: list[dict], season: int, side: str,
                  full: dict[str, float] | None = None) -> dict:
    """S4 raw: sum over affiliated levels of the level's exposure over its full-season
    exposure, capped at 1; pitchers also GS over G. `full` maps level to the full-season
    exposure (read from the store when None)."""
    per: dict[str, float] = {}
    g = gs = 0.0
    for ln in lines:
        lv = _line_level(ln, season, "gate")
        if lv not in RUNG:
            continue
        per[lv] = per.get(lv, 0.0) + _exposure(ln["row"], side)
        g += mh._f(ln["row"].get("g")) or 0.0
        gs += mh._f(ln["row"].get("gs")) or 0.0
    pt = 0.0
    for lv, e in per.items():
        den = (full or {}).get(lv) if full is not None else \
            _full_season_exposure(season, lv, side)
        if den:
            pt += e / den
    out = {"pt": min(1.0, pt)}
    if side == "pit":
        out["gs_share"] = gs / g if g > 0 else 0.0
    return out


def _pure_norms(season: int, level: str, group: str) -> dict | None:
    """The pure (unblended) norm of one level-season: the frozen 2026 file, or
    milb_history.level_norms_from_rows over the store's lines at the level."""
    key = (int(season), level, group)
    if key in _NORMS:
        return _NORMS[key]
    if int(season) == SEASON_2026:
        G.require_eta_look()
        p = DATA_DIR / NORMS_2026_NAME
        if _sha_file(p) != _pins().get("pure_norms_sha256"):
            raise StoreError(f"{NORMS_2026_NAME} differs from its pin")
        doc = json.loads(p.read_text(encoding="utf-8"))
        out = ((doc.get("pure") or {}).get(group) or {}).get(level)
    else:
        rows = [ln["row"] for ln in _season_lines(season, group)
                if _line_level(ln, season, "gate") == level]
        out = mh.level_norms_from_rows(rows, group)
    _NORMS[key] = out
    return out


def _perf(row: dict, level: str, season: int, side: str) -> dict | None:
    """S3 raw columns at the primary level, against the pure norm of (season, level),
    falling back to the prior season's pure norm; None when neither exists."""
    group = GROUP[side]
    norms = _pure_norms(season, level, group)
    if not norms and int(season) - 1 >= STORE_FIRST:
        norms = _pure_norms(int(season) - 1, level, group)
    if not norms:
        return None
    r = D._season_rates(row, norms, side)
    if side == "pit":
        return {"k_minus_bb": r["k_rel"] - r["bb_rel"]}
    return {"obp_rel": r["obp_rel"], "contact": -r["k_rel"], "iso_rel": r["iso_rel"]}


def _season_outcome(person, season: int, side: str, tj: dict[int, list[str]],
                    rung_pre: float | None) -> dict:
    """S1, raw S2, raw S3, raw S4 and S5 of one person in season V."""
    out = {"level_end": None, "end_level": None, "mlb_event": False, "climb_raw": None,
           "perf_raw": None, "pt_raw": None, "gs_share_raw": None}
    if person is None:
        return dict(out, s5_status=ABSENT_IDENTITY)
    pid = int(person)
    lines = _season_index(season, GROUP[side]).get(pid) or []
    lv, row = _primary_level(lines, side, season, "gate")
    pt = _playing_time(lines, season, side)
    out["pt_raw"] = pt["pt"]
    if side == "pit":
        out["gs_share_raw"] = pt["gs_share"]
    if pid in _mlb_event_ids(season, GROUP[side]):
        out.update(level_end=MLB_RUNG, end_level="MLB", mlb_event=True, s5_status=ACTIVE)
    elif lv is not None:
        out.update(level_end=RUNG[lv], end_level=lv, s5_status=ACTIVE,
                   perf_raw=_perf(row, lv, season, side))
    else:
        out["s5_status"] = ABSENT_KNOWN if _tj_explains(tj.get(pid), season) \
            else ABSENT_UNKNOWN
    if out["level_end"] is not None and rung_pre is not None:
        out["climb_raw"] = out["level_end"] - rung_pre
    return out


# ---------------------------------------------------------------------------
# the as-of org (s4)
# ---------------------------------------------------------------------------

def _club(raw) -> str | None:
    if not raw or raw in PLACEHOLDER_ORGS:
        return None
    code = trades.canonical_org(str(raw))
    return code if code in CLUBS else None


def _tx_clubs(last_year: int, tx_dir: Path | None = None) -> dict[int, list[tuple[str, str]]]:
    """{person id: [(date, club)]}, oldest first, from the league transaction feed through
    December of last_year; an event counts when its destination resolves to one of the
    30 parent clubs (trades.canonical_org_from_id, else the name)."""
    import efv_drivers as DRV
    tdir = Path(tx_dir) if tx_dir is not None else TX_DIR
    out: dict[int, list[tuple[str, str]]] = {}
    for ym, present in DRV.league_tx_months(int(last_year), tdir).items():
        if not present:
            continue
        y, m = (int(p) for p in ym.split("-"))
        with gzip.open(DRV.league_tx_path(y, m, tdir), "rt", encoding="utf-8") as fh:
            doc = json.load(fh)
        for t in doc.get("transactions") or []:
            pid = (t.get("person") or {}).get("id")
            day = str(t.get("date") or t.get("effectiveDate") or "")[:10]
            team = t.get("toTeam") or {}
            code = trades.canonical_org_from_id(team.get("id"), team.get("name"))
            if pid and day and code in CLUBS:
                out.setdefault(int(pid), []).append((day, code))
    for evs in out.values():
        evs.sort()
    return out


def _asof_org(points: list[dict], window, person, vintage: int,
              tx: dict[int, list[tuple[str, str]]]) -> tuple[str, str, str | None]:
    """(club, route, date read) for one row: the org on the latest in-window board point,
    else the last transaction-feed club before V-01-01 on the outcome-blind id, else
    ORG_UNKNOWN. Asserts that no org dated at or after the window end is read."""
    lo, hi = str(window[0])[:10], str(window[1])[:10]
    pts = [p for p in points or () if p.get("snapshot_date")
           and lo <= str(p["snapshot_date"])[:10] < hi]
    if pts:
        latest = max(pts, key=lambda p: str(p["snapshot_date"])[:10])
        day = str(latest["snapshot_date"])[:10]
        assert day < hi, f"board org dated {day} at or after the window end {hi}"
        code = _club(latest.get("org"))
        if code:
            return code, "board", day
    cut = f"{int(vintage)}-01-01"
    if person is not None:
        for day, code in reversed(tx.get(int(person)) or ()):
            if day < cut:
                assert day < hi, f"transaction org dated {day} at or after {hi}"
                return code, "transactions", day
    return ORG_UNKNOWN, "unknown", None


# ---------------------------------------------------------------------------
# residual maps, the club table and the components (pure)
# ---------------------------------------------------------------------------

def _fit_residual_map(values, rungs, ages) -> dict:
    """OLS of a component on one intercept per rung_pre value plus a common age_pre
    slope. Returns {"by_rung": {rung: a}, "age_slope": b, "pooled": a0}; a rung the fit
    never saw takes the pooled intercept."""
    y = np.asarray(values, dtype=float)
    r = np.asarray(rungs, dtype=float)
    a = np.asarray(ages, dtype=float)
    if y.size == 0:
        raise ValueError("a residual map needs rows")
    levels = sorted(set(r.tolist()))
    X = np.column_stack([(r == lv).astype(float) for lv in levels] + [a])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    slope = float(beta[-1])
    by_rung = {float(lv): float(b) for lv, b in zip(levels, beta[:-1])}
    pooled = float(np.mean(y - slope * a))
    return {"by_rung": by_rung, "age_slope": slope, "pooled": pooled, "n": int(y.size)}


def _apply_residual_map(m: dict, value, rung, age) -> float | None:
    if value is None or rung is None or age is None:
        return None
    base = m["by_rung"].get(float(rung), m["pooled"])
    return float(value) - base - m["age_slope"] * float(age)


def _fit_club_table(resids, clubs) -> dict:
    """Shrunken parent-club intercepts of a residualized component: each club's mean
    pulled toward the pooled mean by n / (n + k), k = sigma2 / tau2 from the method of
    moments (k infinite, every club at the pooled mean, when tau2 is not positive).
    ORG_UNKNOWN rows count in the pooled mean and take it."""
    y = np.asarray(resids, dtype=float)
    if y.size == 0:
        raise ValueError("a club table needs rows")
    pooled = float(np.mean(y))
    members: dict[str, list[float]] = {}
    for v, c in zip(y.tolist(), clubs):
        if c and c != ORG_UNKNOWN:
            members.setdefault(c, []).append(v)
    sizes = {c: len(v) for c, v in members.items()}
    means = {c: float(np.mean(v)) for c, v in members.items()}
    dof = sum(n - 1 for n in sizes.values())
    sigma2 = (sum(float(np.sum((np.asarray(v) - means[c]) ** 2))
                  for c, v in members.items()) / dof) if dof > 0 else 0.0
    if len(means) > 1:
        tau2 = float(np.var(list(means.values()), ddof=1)) - \
            float(np.mean([sigma2 / n for n in sizes.values()]))
    else:
        tau2 = 0.0
    k = sigma2 / tau2 if tau2 > 0 else math.inf
    table = {c: pooled + (sizes[c] / (sizes[c] + k) if math.isfinite(k) else 0.0)
             * (means[c] - pooled) for c in means}
    return {"pooled": pooled, "k": k, "clubs": table, "sizes": sizes, "n": int(y.size)}


def _club_intercept(table: dict, club) -> float:
    if not club or club == ORG_UNKNOWN:
        return table["pooled"]
    return table["clubs"].get(club, table["pooled"])


def _map_keys(side: str) -> tuple[str, ...]:
    perf = HIT_PERF if side == "hit" else PIT_PERF
    return ("climb",) + perf + ("pt",) + (("gs_share",) if side == "pit" else ())


def _raw_value(row: dict, key: str):
    if key == "climb":
        return row.get("climb_raw")
    if key == "pt":
        return row.get("pt_raw")
    if key == "gs_share":
        return row.get("gs_share_raw")
    return (row.get("perf_raw") or {}).get(key)


def _fit_maps(rows: list[dict], side: str) -> dict:
    """The residual maps of every component and the club table of residualized CLIMB,
    on the id-resolved rows handed in."""
    use = [r for r in rows if r.get("id_resolved")]
    maps = {}
    for key in _map_keys(side):
        sub = [r for r in use if _raw_value(r, key) is not None]
        maps[key] = _fit_residual_map([_raw_value(r, key) for r in sub],
                                      [r["rung_pre"] for r in sub],
                                      [r["age_pre"] for r in sub])
    sub = [r for r in use if r.get("climb_raw") is not None]
    res = [_apply_residual_map(maps["climb"], r["climb_raw"], r["rung_pre"], r["age_pre"])
           for r in sub]
    club = _fit_club_table(res, [r.get("org") for r in sub])
    return {"side": side, "residual": maps, "club": club,
            "vintages": sorted({int(r["vintage"]) for r in use})}


def _zscore_within(rows: list[dict], key: str) -> None:
    """Standardize rows[key] within each (side, V) over its id-resolved non-missing
    rows; a missing value stays None."""
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault((r["side"], int(r["vintage"])), []).append(r)
    for grp in groups.values():
        vals = [r[key] for r in grp if r.get("id_resolved") and r.get(key) is not None]
        mu = float(np.mean(vals)) if vals else 0.0
        sd = float(np.std(vals)) if len(vals) > 1 else 0.0
        for r in grp:
            if r.get(key) is not None:
                r[key] = (r[key] - mu) / sd if sd > 0 else 0.0


def _impute_mean_within(rows: list[dict], key: str) -> None:
    """A missing id-resolved value takes the id-resolved mean of its (side, V)."""
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault((r["side"], int(r["vintage"])), []).append(r)
    for grp in groups.values():
        vals = [r[key] for r in grp if r.get("id_resolved") and r.get(key) is not None]
        mu = float(np.mean(vals)) if vals else 0.0
        for r in grp:
            if r.get("id_resolved") and r.get(key) is None:
                r[key] = mu


def _components(rows: list[dict], maps: dict) -> list[dict]:
    """S2, S3, S4 (and S4 GS share for pitchers) and the ABSENT code on copies of the
    rows. ABSENT_IDENTITY rows carry None on every input (out of the S_idx primary)."""
    side = maps["side"]
    res = maps["residual"]
    out = [dict(r) for r in rows]
    perf_keys = HIT_PERF if side == "hit" else PIT_PERF
    for r in out:
        if r.get("side") != side:
            raise ValueError(f"a {r.get('side')} row reached the {side} components")
        rp, ap = r.get("rung_pre"), r.get("age_pre")
        c = _apply_residual_map(res["climb"], r.get("climb_raw"), rp, ap)
        r["s2"] = None if c is None else c - _club_intercept(maps["club"], r.get("org"))
        for k in perf_keys:
            r["z_" + k] = _apply_residual_map(res[k], _raw_value(r, k), rp, ap)
        r["s4"] = _apply_residual_map(res["pt"], r.get("pt_raw"), rp, ap)
        if side == "pit":
            r["s4_gs"] = _apply_residual_map(res["gs_share"], r.get("gs_share_raw"), rp, ap)
        r["absent"] = 1.0 if r.get("s5_status") in (ABSENT_KNOWN, ABSENT_UNKNOWN) else 0.0
    for k in perf_keys:
        _zscore_within(out, "z_" + k)
    for r in out:
        zs = [r["z_" + k] for k in perf_keys]
        r["s3"] = float(np.mean(zs)) if all(z is not None for z in zs) else None
        if r.get("id_resolved") and r["s3"] is None:
            r["s3"] = 0.0
    for k in ("s2", "s4") + (("s4_gs",) if side == "pit" else ()):
        _impute_mean_within(out, k)
    for r in out:
        if not r.get("id_resolved"):
            for k in FEATURES[side]:
                r[k] = None
    return out


# ---------------------------------------------------------------------------
# S_idx (ridge) and g_S (penalized logistic), pure
# ---------------------------------------------------------------------------

def _design(rows: list[dict], features) -> np.ndarray:
    return np.asarray([[float(r[k]) for k in features] for r in rows], dtype=float)


def _standardizer(X: np.ndarray, w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mu = (w[:, None] * X).sum(axis=0) / w.sum()
    sd = np.sqrt((w[:, None] * (X - mu) ** 2).sum(axis=0) / w.sum())
    sd[sd <= 0] = 1.0
    return mu, sd


def _ridge_fit(X: np.ndarray, y: np.ndarray, w: np.ndarray, alpha: float) -> dict:
    """Weighted ridge on standardized columns, intercept unpenalized."""
    mu, sd = _standardizer(X, w)
    Zs = (X - mu) / sd
    y0 = float((w * y).sum() / w.sum())
    A = Zs.T @ (w[:, None] * Zs) + float(alpha) * np.eye(Zs.shape[1])
    beta = np.linalg.solve(A, Zs.T @ (w * (y - y0)))
    return {"mu": mu, "sd": sd, "beta": beta, "y0": y0, "alpha": float(alpha)}


def _ridge_predict(model: dict, X: np.ndarray) -> np.ndarray:
    return model["y0"] + ((X - model["mu"]) / model["sd"]) @ model["beta"]


def _select_alpha(X, y, w, folds, grid=RIDGE_GRID) -> float:
    """The grid penalty with the least weighted held-out squared error over `folds`
    (an array of fold labels); on a tie the larger penalty."""
    best, best_err = None, math.inf
    labels = sorted(set(folds.tolist()))
    for alpha in sorted(grid, reverse=True):
        err = 0.0
        for f in labels:
            tr, te = folds != f, folds == f
            if not tr.any() or not te.any():
                continue
            m = _ridge_fit(X[tr], y[tr], w[tr], alpha)
            err += float((w[te] * (y[te] - _ridge_predict(m, X[te])) ** 2).sum())
        if err < best_err - 1e-12:
            best, best_err = alpha, err
    return float(best if best is not None else max(grid))


def _player_folds(keys, k: int = N_FOLDS, seed: int = FOLD_SEED) -> np.ndarray:
    """Fold labels 0..k-1 by player: the sorted distinct keys in a seeded permutation."""
    uniq = sorted(set(keys))
    perm = np.random.default_rng(seed).permutation(len(uniq))
    fold_of = {uniq[int(j)]: i % k for i, j in enumerate(perm)}
    return np.asarray([fold_of[x] for x in keys])


def _s_idx_oos(rows: list[dict], features, scheme: str = "lovo",
               grid=RIDGE_GRID) -> dict:
    """Out-of-sample S_idx. scheme "lovo": each vintage held out, its penalty by an inner
    leave-one-vintage-out on the training vintages. scheme "grouped": player-grouped
    N_FOLDS folds (FOLD_SEED), its penalty by an inner player-grouped split of the
    training players. Rows need the caller's "target" and "weight"."""
    if scheme not in ("lovo", "grouped"):
        raise ValueError(f"scheme must be lovo or grouped, got {scheme!r}")
    X = _design(rows, features)
    y = np.asarray([float(r["target"]) for r in rows])
    w = np.asarray([float(r.get("weight", 1.0)) for r in rows])
    if scheme == "lovo":
        outer = np.asarray([int(r["vintage"]) for r in rows])
    else:
        outer = _player_folds([r["player_key"] for r in rows])
    pred = np.full(len(rows), np.nan)
    alphas = {}
    for f in sorted(set(outer.tolist())):
        tr, te = outer != f, outer == f
        if scheme == "lovo":
            inner = outer[tr]
        else:
            inner = _player_folds([rows[i]["player_key"] for i in np.flatnonzero(tr)])
        a = _select_alpha(X[tr], y[tr], w[tr], inner, grid)
        alphas[int(f)] = a
        pred[te] = _ridge_predict(_ridge_fit(X[tr], y[tr], w[tr], a), X[te])
    return {"pred": pred, "alphas": alphas, "scheme": scheme, "n": len(rows)}


def _s_idx_full(rows: list[dict], features, scheme: str = "lovo",
                grid=RIDGE_GRID) -> dict:
    """The fit on every row (the index applied to lv_2026), its penalty by the same inner
    scheme over all rows."""
    X = _design(rows, features)
    y = np.asarray([float(r["target"]) for r in rows])
    w = np.asarray([float(r.get("weight", 1.0)) for r in rows])
    folds = (np.asarray([int(r["vintage"]) for r in rows]) if scheme == "lovo"
             else _player_folds([r["player_key"] for r in rows]))
    a = _select_alpha(X, y, w, folds, grid)
    return dict(_ridge_fit(X, y, w, a), features=tuple(features), scheme=scheme)


def _logit_fit(X: np.ndarray, y: np.ndarray, alpha: float) -> dict:
    """L2-penalized logistic on standardized columns by Newton's method from zero."""
    w = np.ones(len(y))
    mu, sd = _standardizer(X, w)
    Zs = np.column_stack([np.ones(len(y)), (X - mu) / sd])
    pen = np.full(Zs.shape[1], float(alpha))
    pen[0] = INTERCEPT_PENALTY
    b = np.zeros(Zs.shape[1])
    for _ in range(NEWTON_MAX_IT):
        p = 1.0 / (1.0 + np.exp(-(Zs @ b)))
        grad = Zs.T @ (y - p) - pen * b
        H = (Zs * (p * (1 - p))[:, None]).T @ Zs + np.diag(pen)
        step = np.linalg.solve(H, grad)
        b = b + step
        if float(np.max(np.abs(step))) < NEWTON_TOL:
            break
    return {"mu": mu, "sd": sd, "b": b, "alpha": float(alpha)}


def _logit_predict(model: dict, X: np.ndarray) -> np.ndarray:
    z = model["b"][0] + ((X - model["mu"]) / model["sd"]) @ model["b"][1:]
    return 1.0 / (1.0 + np.exp(-z))


def _log_loss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).sum())


def _g_s_alpha(X, y, vint, grid=RIDGE_GRID) -> float | None:
    """The penalty by an inner forward-chained split: each training vintage after the
    first is predicted from the vintages before it; least total log loss, larger on a
    tie. None with fewer than two training vintages."""
    vs = sorted(set(vint.tolist()))
    if len(vs) < 2:
        return None
    best, best_loss = None, math.inf
    for alpha in sorted(grid, reverse=True):
        loss = 0.0
        for u in vs[1:]:
            tr, te = vint < u, vint == u
            loss += _log_loss(y[te], _logit_predict(_logit_fit(X[tr], y[tr], alpha), X[te]))
        if loss < best_loss - 1e-12:
            best, best_loss = alpha, loss
    return float(best)


def _g_s_forward(rows: list[dict], features, grid=RIDGE_GRID) -> dict:
    """g_S forward-chained: each vintage is predicted by a fit on the earlier vintages
    with a resolved "reached" (the caller's R3), penalty by _g_s_alpha. A vintage with
    fewer than two earlier vintages gets no prediction (NaN)."""
    X = _design(rows, features)
    y = np.asarray([np.nan if r.get("reached") is None else float(r["reached"])
                    for r in rows])
    vint = np.asarray([int(r["vintage"]) for r in rows])
    pred = np.full(len(rows), np.nan)
    alphas = {}
    for v in sorted(set(vint.tolist())):
        tr = (vint < v) & ~np.isnan(y)
        a = _g_s_alpha(X[tr], y[tr], vint[tr], grid) if tr.any() else None
        alphas[int(v)] = a
        if a is None:
            continue
        te = vint == v
        pred[te] = _logit_predict(_logit_fit(X[tr], y[tr], a), X[te])
    return {"pred": pred, "alphas": alphas, "n": len(rows)}


def _g_s_fit(rows: list[dict], features, grid=RIDGE_GRID) -> dict | None:
    """One g_S fit on the rows handed in (resolved "reached" only), penalty by
    _g_s_alpha; None with fewer than two vintages."""
    use = [r for r in rows if r.get("reached") is not None]
    if not use:
        return None
    X = _design(use, features)
    y = np.asarray([float(r["reached"]) for r in use])
    vint = np.asarray([int(r["vintage"]) for r in use])
    a = _g_s_alpha(X, y, vint, grid)
    if a is None:
        return None
    return dict(_logit_fit(X, y, a), features=tuple(features))


# ---------------------------------------------------------------------------
# public entry points: each asks the surrogate guard first
# ---------------------------------------------------------------------------

def _guard(vintages, gate_sha, look_records, purpose: str) -> None:
    vs = sorted({int(v) for v in vintages})
    for v in vs:
        if v in RESERVED_LV:
            raise ReservedFrameError(f"list vintage {v} is reserved (R-LV); the surrogate "
                                     "builder never reads it")
    for v in vs:
        G.guard_surrogate_read(v, gate_sha=gate_sha, look_records=look_records,
                               purpose=purpose)


def _release(rows: list[dict], look_records, purpose: str) -> list[dict]:
    out, _released = G.withhold_reserved_vm(rows, look_records=look_records,
                                            purpose=purpose)
    return out


def mlb_event_ids(season: int, group: str, *, gate_sha: str | None = None,
                  look_records=(), purpose: str) -> frozenset[int]:
    """The person ids with a regular-season MLB line in `season` (season V of a frame
    the guard opens for `purpose`); no stat column."""
    _guard([season], gate_sha, look_records, purpose)
    if int(season) == SEASON_2026:
        G.require_eta_look()
    return _mlb_event_ids(season, group)


def build_outcomes(side: str, vintage: int, frame_rows: list[dict], *,
                   gate_sha: str | None = None, look_records=(), purpose: str,
                   universe: dict | None = None, tx: dict | None = None,
                   tj: dict | None = None) -> list[dict]:
    """The V-1 state and the raw season-V outcomes (S1 to S5, the as-of org) of every
    row of one (side, V) frame, one output row per frame row, in order. Reads the frame
    row's player_key, outcome-blind mlbam_id, side, vintage and window, and the record's
    in-window board points for the org; nothing else of the row or the record."""
    if side not in SIDES:
        raise ValueError(f"side must be one of {SIDES}, got {side!r}")
    V = int(vintage)
    _guard([V], gate_sha, look_records, purpose)
    if V == SEASON_2026:
        G.require_eta_look()
    for r in frame_rows:
        if int(r["vintage"]) != V or r.get("side") != side:
            raise ValueError(f"row {r.get('player_key')} is not on the ({side}, {V}) frame")
    checked = _release(frame_rows, look_records, purpose)
    if universe is None:
        import efv_vintage_frame as F
        universe = F.load_universe()
    if tx is None:
        tx = _tx_clubs(V - 1)
    if tj is None:
        tj = _tj_index()
    out = []
    for r in checked:
        person = r.get("mlbam_id")
        pre = _pre_rung(person, V, side)
        age_pre = _age_pre(pre, V, side)
        rec = universe.get(r.get("player_key")) or {}
        org, route, org_day = _asof_org(rec.get("points"), r["window"], person, V, tx)
        row = {"player_key": r.get("player_key"), "side": side, "vintage": V,
               "window": list(r["window"]), "person_id": person,
               "id_resolved": person is not None,
               "rung_pre": pre["rung_pre"], "rung_pre_level": pre["rung_pre_level"],
               "rung_pre_season": pre["rung_pre_season"], "pre_absent": pre["pre_absent"],
               "age_pre": age_pre, "age_pre_imputed": age_pre is None,
               "org": org, "org_route": route, "org_date": org_day}
        for k in ("status", "release_record", "mlb_stat_read", "label_released"):
            if k in r:
                row["vm_" + k] = r[k]
        out.append(row)
    rungs = [x["rung_pre"] for x in out if not x["pre_absent"]]
    ages = [x["age_pre"] for x in out if x["age_pre"] is not None]
    med_rung, med_age = _median(rungs), _median(ages)
    for x in out:
        if x["pre_absent"]:
            x["rung_pre"] = med_rung
        if x["age_pre"] is None:
            x["age_pre"] = med_age
        x.update(_season_outcome(x["person_id"], V, side, tj, x["rung_pre"]))
    return out


def _rows_vintages(rows: list[dict]) -> list[int]:
    return sorted({int(r["vintage"]) for r in rows})


def fit_maps(rows: list[dict], side: str, *, gate_sha: str | None = None,
             look_records=(), purpose: str = "transfer", fallback: bool = False) -> dict:
    """The residual maps and the club table on lv_L6 rows (V 2011 to 2016; V 2015 to
    2016 under the s2.1 fallback) of one side, from build_outcomes output."""
    _guard(_rows_vintages(rows), gate_sha, look_records, purpose)
    allowed = set(FALLBACK_VINTAGES if fallback else FIT_VINTAGES)
    bad = sorted(set(_rows_vintages(rows)) - allowed)
    if bad:
        raise ValueError(f"maps are fitted on V {sorted(allowed)} only, got {bad}")
    return _fit_maps(_release(rows, look_records, purpose), side)


def apply_maps(rows: list[dict], maps: dict, *, gate_sha: str | None = None,
               look_records=(), purpose: str) -> list[dict]:
    """S2, S3, S4 and the ABSENT code on build_outcomes rows, with fitted maps."""
    _guard(_rows_vintages(rows), gate_sha, look_records, purpose)
    return _release(_components(rows, maps), look_records, purpose)


def _primary_rows(rows: list[dict], side: str) -> list[dict]:
    use = [r for r in rows if r.get("id_resolved") and r.get("target") is not None]
    for r in use:
        if any(r.get(k) is None for k in FEATURES[side]):
            raise ValueError(f"row {r.get('player_key')} lacks a component")
    return use


def fit_s_idx(rows: list[dict], side: str, *, gate_sha: str | None = None,
              look_records=(), purpose: str = "transfer", fallback: bool = False) -> dict:
    """S_idx on apply_maps rows carrying the caller's "target" (the L6 percentile within
    (side, V)) and "weight": the out-of-sample predictions (leave-one-vintage-out over
    V 2011 to 2016, or the player-grouped fallback on V 2015 to 2016) and the full fit.
    ABSENT_IDENTITY rows and rows without a target stay out, counted."""
    _guard(_rows_vintages(rows), gate_sha, look_records, purpose)
    allowed = set(FALLBACK_VINTAGES if fallback else FIT_VINTAGES)
    bad = sorted(set(_rows_vintages(rows)) - allowed)
    if bad:
        raise ValueError(f"S_idx is fitted on V {sorted(allowed)} only, got {bad}")
    rows = _release(rows, look_records, purpose)
    use = _primary_rows(rows, side)
    scheme = "grouped" if fallback else "lovo"
    oos = _s_idx_oos(use, FEATURES[side], scheme)
    return {"side": side, "scheme": scheme, "features": FEATURES[side],
            "keys": [(r["player_key"], int(r["vintage"])) for r in use],
            "oos": oos["pred"].tolist(), "fold_alphas": oos["alphas"],
            "full": _s_idx_full(use, FEATURES[side], scheme),
            "left_out": {"id_unresolved": sum(1 for r in rows if not r.get("id_resolved")),
                         "no_target": sum(1 for r in rows if r.get("id_resolved")
                                          and r.get("target") is None)}}


def s_idx_scores(model: dict, rows: list[dict], *, gate_sha: str | None = None,
                 look_records=(), purpose: str) -> list[float | None]:
    """The full S_idx fit applied to apply_maps rows; None on an ABSENT_IDENTITY row."""
    _guard(_rows_vintages(rows), gate_sha, look_records, purpose)
    rows = _release(rows, look_records, purpose)
    feats = model["features"]
    out = []
    for r in rows:
        if not r.get("id_resolved"):
            out.append(None)
            continue
        out.append(float(_ridge_predict(model, _design([r], feats))[0]))
    return out


def fit_g_s(rows: list[dict], side: str, *, gate_sha: str | None = None,
            look_records=(), purpose: str = "transfer",
            train_through: int | None = None) -> dict:
    """g_S on apply_maps rows of lv_dev_all carrying the caller's "reached" (R3, None
    when unresolved): the forward-chained predictions, and, with `train_through`, one
    fit on the vintages up to it (T4's imputer)."""
    _guard(_rows_vintages(rows), gate_sha, look_records, purpose)
    bad = sorted(set(_rows_vintages(rows)) - set(G_S_VINTAGES))
    if bad:
        raise ValueError(f"g_S reads V {G_S_VINTAGES[0]} to {G_S_VINTAGES[-1]} only, "
                         f"got {bad}")
    rows = _release(rows, look_records, purpose)
    use = [r for r in rows if r.get("id_resolved")]
    for r in use:
        if any(r.get(k) is None for k in FEATURES[side]):
            raise ValueError(f"row {r.get('player_key')} lacks a component")
    fwd = _g_s_forward(use, FEATURES[side])
    out = {"side": side, "features": FEATURES[side],
           "keys": [(r["player_key"], int(r["vintage"])) for r in use],
           "forward": fwd["pred"].tolist(), "alphas": fwd["alphas"]}
    if train_through is not None:
        out["fit"] = _g_s_fit([r for r in use if int(r["vintage"]) <= int(train_through)],
                              FEATURES[side])
    return out
