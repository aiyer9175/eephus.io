# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v4, the population-fitted MiLB-to-MLB translation column (EFV4_POPULATION_TRANSLATION;
owner decisions EW2-10 and EW2-12, 2026-10-08: "new rows as a new source approved for the
population translation column").

WHAT THIS BUILDS. One column, pop_proj_war: the six-season fWAR a KATOH-style translation
model forecasts from a player's last readable MiLB season. The model is fitted on the
FULL affiliated population (every pre-debut player-season with an exposure floor at any
level, sport ids 11 to 16, seasons 2005 to 2019) instead of the 1,000 to 2,000 listed
prospects a V2 fold holds, so its age-for-level, level and league slopes rest on about
fifty times the rows and carry no list-selection effect. The column is offered to the V2
SKILL head of each side (arms w4p_pop_hit and w4p_pop_pit) under the unchanged DS-06
admission rule, as a NAMED RE-TEST: its inputs overlap V2's obp_rel and contact (hitters)
and k_rel (pitchers), and the artifact discloses that overlap as rank correlations.

THE POPULATION ROW. Per (side, season, player): the player's lines that season at every
affiliated level, summed into rates made relative to the line's own (season, level,
league) pooled rate (the (season, level) rate when the league holds fewer than
LEAGUE_MIN_LINES lines), exposure-weighted; plus age, age relative to the level's mean
age, the highest and the mean level rank and the log exposure. Hitters: OBP, ISO, K, BB,
HR, SB per PA and BABIP. Pitchers: K and BB per batter faced, ERA, the start share and
outs per game. A row enters at LINE_MIN exposure (50 PA, 60 BF, efv_dataset's floors).
Only PRE-DEBUT player-seasons are population rows (no fWAR season and no sport-1 line at
or before the season), the frame's own domain.

THE LABEL JOIN. fWAR summed over the HORIZON seasons after the season, from the frozen
fWAR vintage the label itself is built on (data/fwar_vintage.json, FanGraphs' WAR as
MLB's StatsAPI publishes it, keyed by MLBAM id; hitting plus pitching per player-season,
fwar_vintage.season_totals); a player who never reached MLB takes 0, the label's own
convention. The join is written to data/_labs/efv_w2/pop_fwar.json (POP_FWAR_PATH) and
the fit reads it from there. No served module reads it (efv_identity is pinned by an AST
test).

AS OF, PER READ YEAR. A row read at year Y (a list vintage V, or a vintage-matched decision
year) is scored by the model of ITS OWN read year and frame kind, model(kind, Y, side),
fitted on population seasons s with s + HORIZON <= Y - 1, so every label it learns from
was resolved by Y-01-01 and every season ended before Y-01-01; every player of the
frame read at Y (lv: the list-vintage frame at V, both sides; vm: the matrix rows of
decision year Y, both sides) is left out of that fit. The row itself reads its last
MiLB season that had ended by its read (efv_dataset._milb_features' rule, through
efv_w2_milb.last_readable_season), walking back at most MAX_BACK seasons and never
below its MiLB floor. A row with no qualifying season, or a read year with no fittable
population (Y - 7 before 2005), is None and the fit imputes it at the observed training
mean, like every screening column.

READS. Development (choice): lv_dev (list vintages 2017 to 2019) and vm_dev (vm2, the
DS-16 rows), on the frozen fWAR label, through tools/efv_v3_backtest's Inputs (the V2
base reproduces the DS-16 block and efv_v3 at base_config reproduces V2 bit for bit
before anything is read). Spent (report only): R-LV (list vintages 2020 and 2021) and
R-VM (the 2025 debut cohort), read once on 2026-10-08 by the eFV v3 confirmation under
the owner's waiver and SPENT; this module reads them through the same guards on the same
registration sha, labels every such block "spent frame, read after the 10-08
confirmation", writes them to the artifact only (never a progress-ledger row, never the
chart) and chooses nothing on them (EW2-10). A permuted twin of the column (values
shuffled across players inside each (side, year)) is read on the development frames as
the column's no-information reference.

BANS. No served number moves: no exporter imports this module and no flag reads it.
Nothing here groups, counts or averages anything by consensus-FV level
(docs/PROSPECT_ANCHOR_GATE.md): the only strata are side, season, read year and level.
No list vintage 2020 or 2021 and no 2025 cohort row is computed without the committed
registration sha (efv_vintage_frame.guard_score_request / guard_vm_request).

Run:  python efv_w2_popmle.py --join        (write the label join)
      python efv_w2_popmle.py --dev-read    (development read; writes the artifact)
      python efv_w2_popmle.py --spent-read  (the spent-frame read; adds to the artifact)
      python efv_w2_popmle.py --ledger --ledger-path PATH   (development ledger rows)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np

import efv_dataset as D
import efv_vintage_frame as F
import milb_history as mh

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
LAB_DIR = DATA_DIR / "_labs" / "efv_w2"
POP_FWAR_PATH = LAB_DIR / "pop_fwar.json"
OUT_PATH = LAB_DIR / "efv_w2_popmle.json"
TOOL = "efv_w2_popmle.py"
ITEM = "EFV4_POPULATION_TRANSLATION"
MODEL_PREFIX = "efv_v2_screen:efv4:"
COLUMN = "pop_proj_war"
#: The committed registration the 2026-10-08 confirmation read opened the reserved frames
#: on (docs/efv-v2/EFV_V3_BACKTEST.md s5). The spent read reuses it; nothing else does.
CONFIRM_GATE_SHA = "e7931ce4e13110eebb53555bff455ff13ca7c502"
SPENT_NOTE = "spent frame, read after the 10-08 confirmation"
DEV_NOTE = ("eFV v4 population translation (EFV4_POPULATION_TRANSLATION), development "
            "read only: selects and adjudicates nothing")

#: The population: every affiliated pre-debut player-season of these seasons.
POP_SEASONS: tuple[int, ...] = tuple(range(2005, 2020))
#: Label: fWAR over the HORIZON seasons after the season (s + 1 .. s + HORIZON).
HORIZON = 6
LINE_MIN = {"hit": 50, "pit": 60}
#: A frame row reads its last readable season with a qualifying line, at most this many
#: seasons back from the last readable one.
MAX_BACK = 3
LEAGUE_MIN_LINES = 20
#: A read year's fit needs at least this many population rows, else the column is None.
MIN_TRAIN_ROWS = 2000
GROUPS = {"hit": "hitting", "pit": "pitching"}
SPORTS: tuple[int, ...] = tuple(mh.MINOR_SPORTS)
LEVEL_RANK = {lv: r for lv, r in mh._LEVEL_RANK.items() if lv != "MLB"}

#: rate -> (numerator, denominator) in line_counts' names.
RATES: dict[str, dict[str, tuple[str, str]]] = {
    "hit": {"obp": ("obp_n", "obp_d"), "iso": ("xb", "ab"), "k": ("so", "pa"),
            "bb": ("bb", "pa"), "hr": ("hr", "pa"), "sb": ("sb", "pa"),
            "babip": ("babip_n", "babip_d")},
    "pit": {"k": ("so", "bf"), "bb": ("bb", "bf"), "era": ("ra_n", "ra_d")},
}
FEATURES: dict[str, tuple[str, ...]] = {
    "hit": ("age", "age_rel", "lvl_max", "lvl_mean", "log_exp")
    + tuple(f"{r}_rel" for r in RATES["hit"]),
    "pit": ("age", "age_rel", "lvl_max", "lvl_mean", "log_exp")
    + tuple(f"{r}_rel" for r in RATES["pit"]) + ("gs_share", "outs_per_g"),
}
#: The translation model, declared 2026-10-08 before any read and never tuned on a frame:
#: a histogram gradient-boosted regressor (squared error, native missing-value handling),
#: deterministic (no subsampling, no early stopping, fixed seed).
GBM_PARAMS = {"loss": "squared_error", "learning_rate": 0.05, "max_iter": 300,
              "max_leaf_nodes": 15, "min_samples_leaf": 200, "l2_regularization": 1.0,
              "early_stopping": False, "random_state": 20261008}
TWIN_SEED = 20261009

#: EFV_FIX_A (owner decision EW3-21, docs/efv-v2/EFV_FIX_A.md): the population repairs.
#: (1) norms sums each distinct count column once; before it, a denominator shared by several
#: rates (pa for hitters' k, bb, hr and sb; bf for pitchers' k and bb) was added once per
#: rate, so every league reference rate read a quarter (hitters) or a half (pitchers) of the
#: truth and the *_rel features were not league-relative. (2) season_lines drops the
#: non-affiliated Mexican League lines (NON_AFFILIATED_LEAGUES at sport 11, through 2019),
#: which the affiliated population above never meant to hold. DARK: False keeps every path
#: byte-identical to the code before the repair, because the production heads refit on
#: every export and this column moves their slopes; EFV_FIX_B_REFIT turns it on with its
#: registered re-fit, never alone.
POP_REPAIR_ON = True
#: (sport id, league code) pairs of non-affiliated leagues in the MiLB cache files.
NON_AFFILIATED_LEAGUES = frozenset({(11, "MEX")})

ARMS: tuple[dict, ...] = (
    {"name": "w4p_pop_hit", "side": "hit", "head": "skill", "twin": False},
    {"name": "w4p_pop_pit", "side": "pit", "head": "skill", "twin": False},
)
TWINS: tuple[dict, ...] = (
    {"name": "w4p_pop_twin_hit", "side": "hit", "head": "skill", "twin": True},
    {"name": "w4p_pop_twin_pit", "side": "pit", "head": "skill", "twin": True},
)
#: The V2 drivers the column overlaps (the named re-test's disclosure).
OVERLAP_KEYS = {"hit": ("obp_rel", "contact", "k_rel"), "pit": ("k_rel",)}


# ---------------------------------------------------------------------------
# lines
# ---------------------------------------------------------------------------

def _num(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _outs(ip) -> float | None:
    """Innings as StatsAPI writes them ("12.1" is 12 innings and one out) in outs."""
    if ip is None:
        return None
    whole, _, frac = str(ip).partition(".")
    try:
        return float(int(whole or 0) * 3 + (int(frac[:1]) if frac else 0))
    except ValueError:
        return None


def line_counts(row: dict, side: str) -> dict | None:
    """Additive counts of one season line, or None without its exposure."""
    def g(k):
        return _num(row.get(k)) or 0.0
    if side == "hit":
        pa, ab = _num(row.get("pa")), _num(row.get("ab"))
        if not pa or ab is None:
            return None
        h, bb, hbp, sf, so, hr = (g(k) for k in ("h", "bb", "hbp", "sf", "so", "hr"))
        return {"exp": pa, "pa": pa, "ab": ab, "so": so, "bb": bb, "hr": hr, "sb": g("sb"),
                "xb": g("doubles") + 2.0 * g("triples") + 3.0 * hr,
                "obp_n": h + bb + hbp, "obp_d": ab + bb + hbp + sf,
                "babip_n": h - hr, "babip_d": max(ab - so - hr + sf, 0.0)}
    bf = _num(row.get("bf"))
    if not bf:
        return None
    outs = _outs(row.get("ip")) or 0.0
    era = _num(row.get("era"))
    ok = era is not None and outs > 0
    return {"exp": bf, "bf": bf, "so": g("so"), "bb": g("bb"), "g": g("g"), "gs": g("gs"),
            "outs": outs, "ra_n": era * outs if ok else 0.0, "ra_d": outs if ok else 0.0}


@lru_cache(maxsize=None)
def season_lines(season: int, side: str) -> tuple:
    """((mlbam, level, league, age, counts), ...) for one season's affiliated lines."""
    out = []
    for sp in SPORTS:
        for r in mh.season_splits(int(sp), int(season), GROUPS[side], fetch=False):
            pid, lv = r.get("mlbam"), r.get("level")
            if not pid or lv not in LEVEL_RANK:
                continue
            if POP_REPAIR_ON and (int(sp), str(r.get("league") or "")) in NON_AFFILIATED_LEAGUES:
                continue
            c = line_counts(r, side)
            if c is None:
                continue
            out.append((int(pid), lv, str(r.get("league") or ""), _num(r.get("age")), c))
    return tuple(out)


def count_columns(side: str) -> tuple[str, ...]:
    """Every distinct count column RATES reads for the side, once each (a denominator
    shared by several rates appears once)."""
    return tuple(sorted({c for pair in RATES[side].values() for c in pair}))


@lru_cache(maxsize=None)
def norms(season: int, side: str) -> dict:
    """Pooled rates per (level, league) and per level, and the exposure-weighted mean age
    per level, over every line of the season. Contemporaneous; no outcome. With
    POP_REPAIR_ON each count column is summed once (the legacy loop, kept byte-identical
    while the flag is off, summed a shared denominator once per rate)."""
    acc: dict = {"lg": {}, "lv": {}, "age": {}}
    cols = count_columns(side)
    for _pid, lv, lg, age, c in season_lines(int(season), side):
        for key, slot in (((lv, lg), acc["lg"]), (lv, acc["lv"])):
            a = slot.setdefault(key, {"n": 0})
            a["n"] += 1
            if POP_REPAIR_ON:
                for col in cols:
                    a[col] = a.get(col, 0.0) + c[col]
                continue
            for num, den in RATES[side].values():
                a[num] = a.get(num, 0.0) + c[num]
                a[den] = a.get(den, 0.0) + c[den]
        if age is not None:
            s = acc["age"].setdefault(lv, [0.0, 0.0])
            s[0] += age * c["exp"]
            s[1] += c["exp"]

    def rates(a):
        return {r: (a[num] / a[den] if a.get(den) else None)
                for r, (num, den) in RATES[side].items()} | {"n": a["n"]}
    return {"lg": {k: rates(a) for k, a in acc["lg"].items()},
            "lv": {k: rates(a) for k, a in acc["lv"].items()},
            "age": {k: (s[0] / s[1] if s[1] else None) for k, s in acc["age"].items()}}


def _norm_rate(nm: dict, lv: str, lg: str, rate: str) -> float | None:
    a = nm["lg"].get((lv, lg))
    if a and a["n"] >= LEAGUE_MIN_LINES and a.get(rate) is not None:
        return a[rate]
    return (nm["lv"].get(lv) or {}).get(rate)


@lru_cache(maxsize=None)
def player_seasons(season: int, side: str) -> dict:
    """{mlbam: features} for every player with an affiliated line in the season (no
    exposure floor here; LINE_MIN is applied by the readers)."""
    nm = norms(int(season), side)
    acc: dict = {}
    for pid, lv, lg, age, c in season_lines(int(season), side):
        a = acc.setdefault(pid, {"exp": 0.0, "lvl_max": -1, "lvl_w": 0.0, "age_w": 0.0,
                                 "age_x": 0.0, "agerel_x": 0.0, "agerel_w": 0.0,
                                 "rel": {r: [0.0, 0.0] for r in RATES[side]},
                                 "g": 0.0, "gs": 0.0, "outs": 0.0})
        e = c["exp"]
        a["exp"] += e
        rk = LEVEL_RANK[lv]
        a["lvl_max"] = max(a["lvl_max"], rk)
        a["lvl_w"] += rk * e
        if age is not None:
            a["age_x"] += age * e
            a["age_w"] += e
            mean_age = nm["age"].get(lv)
            if mean_age is not None:
                a["agerel_x"] += (age - mean_age) * e
                a["agerel_w"] += e
        for r, (num, den) in RATES[side].items():
            if c[den] <= 0:
                continue
            ref = _norm_rate(nm, lv, lg, r)
            if ref is None:
                continue
            a["rel"][r][0] += (c[num] / c[den] - ref) * c[den]
            a["rel"][r][1] += c[den]
        if side == "pit":
            a["g"] += c["g"]
            a["gs"] += c["gs"]
            a["outs"] += c["outs"]
    out = {}
    nan = float("nan")
    for pid, a in acc.items():
        f = {"exp": a["exp"], "lvl_max": float(a["lvl_max"]),
             "lvl_mean": a["lvl_w"] / a["exp"] if a["exp"] else nan,
             "log_exp": math.log(a["exp"]) if a["exp"] > 0 else nan,
             "age": a["age_x"] / a["age_w"] if a["age_w"] else nan,
             "age_rel": a["agerel_x"] / a["agerel_w"] if a["agerel_w"] else nan}
        for r, (x, w) in a["rel"].items():
            f[f"{r}_rel"] = x / w if w > 0 else nan
        if side == "pit":
            f["gs_share"] = a["gs"] / a["g"] if a["g"] > 0 else nan
            f["outs_per_g"] = a["outs"] / a["g"] if a["g"] > 0 else nan
        out[pid] = f
    return out


def vector(f: dict, side: str) -> list[float]:
    return [float(f.get(k, float("nan"))) for k in FEATURES[side]]


# ---------------------------------------------------------------------------
# the label join (frozen fWAR vintage -> data/_labs/efv_w2/pop_fwar.json)
# ---------------------------------------------------------------------------

def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def population_ids() -> set[int]:
    ids: set[int] = set()
    for side in GROUPS:
        for s in POP_SEASONS:
            ids |= set(player_seasons(s, side))
    return ids


def build_label_join(*, blob: dict | None = None) -> dict:
    """The join document: for every population member who appears in the frozen fWAR
    vintage, {season: fWAR} (hitting plus pitching), and the first MLB season on the
    evidence (an fWAR row or a sport-1 line). Members absent here never reached MLB and
    take 0."""
    import fwar_vintage as FV
    blob = FV.load() if blob is None else blob
    totals = FV.season_totals(blob)
    pop = population_ids()
    by: dict[str, dict[str, float]] = {}
    first: dict[str, int] = {}
    for (mid, s), w in sorted(totals.items()):
        if mid not in pop:
            continue
        by.setdefault(str(mid), {})[str(s)] = round(float(w), 5)
        k = str(mid)
        first[k] = min(first.get(k, s), s)
    for s in range(POP_SEASONS[0], max(FV.fwar_seasons(blob)) + 1):
        for g in GROUPS.values():
            for r in mh.season_splits(1, s, g, fetch=False):
                mid = r.get("mlbam")
                if mid and int(mid) in pop:
                    k = str(int(mid))
                    first[k] = min(first.get(k, s), s)
    counts = {side: {str(s): sum(1 for f in player_seasons(s, side).values()
                                 if f["exp"] >= LINE_MIN[side]) for s in POP_SEASONS}
              for side in GROUPS}
    return {"schema": 1, "item": ITEM, "produced_by": TOOL, "generated_at": _now(),
            "role": "development", "served": False,
            "source": {"path": "data/fwar_vintage.json", "vintage_id": blob.get("vintage_id"),
                       "sha256": _sha(DATA_DIR / "fwar_vintage.json"),
                       "rule": ("fwar_vintage.season_totals: hitting war plus pitching war "
                                "per (mlbam, season), frozen per season")},
            "horizon": HORIZON, "population_seasons": [POP_SEASONS[0], POP_SEASONS[-1]],
            "never_reached": "absent from by_mlbam; takes 0 (the label's own convention)",
            "population_rows_at_line_min": counts,
            "n_members": len(pop), "n_reached": len(by),
            "by_mlbam": dict(sorted(by.items(), key=lambda kv: int(kv[0]))),
            "first_mlb_season": dict(sorted(first.items(), key=lambda kv: int(kv[0])))}


def write_json(doc: dict, out: Path, *, indent=1) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=indent, ensure_ascii=False, default=str) + "\n"
    for ch in (chr(0x2014), chr(0x2013)):
        if ch in text:
            raise RuntimeError("an em-dash or en-dash reached the artifact")
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(out)
    return out


@lru_cache(maxsize=1)
def _join() -> dict:
    if not POP_FWAR_PATH.exists():
        raise FileNotFoundError(f"{POP_FWAR_PATH} is missing: run python {TOOL} --join")
    return json.loads(POP_FWAR_PATH.read_text(encoding="utf-8"))


def label(mid: int, season: int, join: dict | None = None) -> float:
    """fWAR over seasons season + 1 .. season + HORIZON; 0 when never reached."""
    j = _join() if join is None else join
    seasons = j["by_mlbam"].get(str(int(mid))) or {}
    return float(sum(seasons.get(str(t), 0.0)
                     for t in range(int(season) + 1, int(season) + HORIZON + 1)))


def first_mlb(mid: int, join: dict | None = None) -> int | None:
    j = _join() if join is None else join
    v = j["first_mlb_season"].get(str(int(mid)))
    return None if v is None else int(v)


# ---------------------------------------------------------------------------
# the translation model, one per (frame kind, read year, side)
# ---------------------------------------------------------------------------

def train_seasons(read_year: int) -> list[int]:
    """Population seasons a read at `read_year` may learn from: every label window
    (s + 1 .. s + HORIZON) closed by read_year - 1, so it was resolved by read_year-01-01."""
    last = int(read_year) - 1 - HORIZON
    return [s for s in POP_SEASONS if s <= last]


def training_rows(side: str, read_year: int, excluded: frozenset, *,
                  join: dict | None = None) -> tuple[np.ndarray, np.ndarray, dict]:
    seasons = train_seasons(read_year)
    X, y = [], []
    rec = {"seasons": [min(seasons), max(seasons)] if seasons else None, "rows": 0,
           "left_out_frame_players": 0, "left_out_post_debut": 0}
    for s in seasons:
        assert s + HORIZON <= int(read_year) - 1
        for mid, f in player_seasons(s, side).items():
            if f["exp"] < LINE_MIN[side]:
                continue
            if mid in excluded:
                rec["left_out_frame_players"] += 1
                continue
            fm = first_mlb(mid, join)
            if fm is not None and fm <= s:
                rec["left_out_post_debut"] += 1
                continue
            X.append(vector(f, side))
            y.append(label(mid, s, join))
    rec["rows"] = len(y)
    return np.asarray(X, dtype=np.float64), np.asarray(y, dtype=np.float64), rec


def fit_translation(X: np.ndarray, y: np.ndarray):
    from sklearn.ensemble import HistGradientBoostingRegressor
    m = HistGradientBoostingRegressor(**GBM_PARAMS)
    m.fit(X, y)
    return m


class Translator:
    """Fits and caches model(kind, read_year, side). `excluded[(kind, read_year)]` holds
    the MLBAM ids of every player of the frame read at that year (both sides); they are
    left out of that fit. `gate_sha` opens a reserved read year (R-LV vintages, the
    R-VM cohort) and nothing else."""

    def __init__(self, excluded: dict, *, gate_sha: str | None = None,
                 join: dict | None = None):
        self.excluded = {k: frozenset(v) for k, v in excluded.items()}
        self.gate_sha = gate_sha
        self.join = join
        self.models: dict = {}
        self.receipts: dict = {}

    def guard(self, kind: str, read_year: int) -> None:
        if kind == "lv":
            F.guard_score_request(int(read_year), gate_sha=self.gate_sha,
                                  purpose="population translation column")
        elif kind == "vm":
            F.guard_vm_request([int(read_year)], gate_sha=self.gate_sha,
                               purpose="population translation column")
        else:
            raise ValueError(kind)

    def model(self, kind: str, read_year: int, side: str):
        key = (kind, int(read_year), side)
        if key in self.models:
            return self.models[key]
        self.guard(kind, read_year)
        if (kind, int(read_year)) not in self.excluded:
            raise KeyError(f"no exclusion set for {kind} {read_year}")
        X, y, rec = training_rows(side, read_year, self.excluded[(kind, int(read_year))],
                                  join=self.join)
        m = None
        if len(y) >= MIN_TRAIN_ROWS:
            t0 = time.time()
            m = fit_translation(X, y)
            rec["fit_s"] = round(time.time() - t0, 2)
            rec["label_mean"] = round(float(y.mean()), 4)
            rec["share_label_nonzero"] = round(float((y != 0).mean()), 4)
        else:
            rec["status"] = f"under {MIN_TRAIN_ROWS} rows; column None at this read year"
        self.models[key] = m
        self.receipts[f"{kind}|{int(read_year)}|{side}"] = rec
        return m

    def value(self, side: str, kind: str, mlbam, read_year: int, cutoff: str | None,
              floor: int) -> tuple[float | None, int | None]:
        """(pop_proj_war, the season read) for one frame row."""
        from efv_w2_milb import last_readable_season
        self.guard(kind, read_year)
        if not mlbam:
            return None, None
        mid = int(mlbam)
        top = last_readable_season(int(read_year), cutoff)
        low = max(int(floor), top - MAX_BACK + 1)
        for s in range(top, low - 1, -1):
            f = player_seasons(s, side).get(mid)
            if f is None or f["exp"] < LINE_MIN[side]:
                continue
            m = self.model(kind, read_year, side)
            if m is None:
                return None, s
            return float(m.predict(np.asarray([vector(f, side)]))[0]), s
        return None, None


# ---------------------------------------------------------------------------
# frame values
# ---------------------------------------------------------------------------

def lv_exclusions(frames_lv: dict) -> dict:
    """{("lv", V): mlbam ids of the list-vintage frame at V, both sides}."""
    out: dict = {}
    for side, by_v in frames_lv.items():
        for V, (rows, _labs) in by_v.items():
            s = out.setdefault(("lv", int(V)), set())
            s |= {int(r["mlbam_id"]) for r in rows if r.get("mlbam_id")}
    return out


def vm_exclusions(raw_by_side: dict, years) -> dict:
    """{("vm", Y): mlbam ids of the matrix rows of decision year Y, both sides}."""
    out: dict = {("vm", int(y)): set() for y in years}
    want = {int(y) for y in years}
    for side, raw in raw_by_side.items():
        for r in raw.values():
            dy = r.get("decision_year")
            if dy is None or int(dy) not in want or not r.get("mlbam_id"):
                continue
            out[("vm", int(dy))].add(int(r["mlbam_id"]))
    return out


def lv_values(tr: Translator, side: str, frames_side: dict) -> dict:
    """{(V, player_key, kind): value} over every list-vintage frame row of the side, one
    value per (V, player) for both roles (a training row of a later fold is the same
    read)."""
    out = {}
    for V, (rows, _labs) in frames_side.items():
        for r in rows:
            v, _s = tr.value(side, "lv", r.get("mlbam_id"), int(V),
                             (r.get("window") or [None])[0],
                             int(r.get("milb_floor") or D.MILB_FLOOR_DEFAULT))
            for kind in ("train", "test"):
                out[(int(V), r["player_key"], kind)] = v
    return out


def vm_values(tr: Translator, side: str, by_fold: dict, raw: dict, pinned_asof: dict) -> dict:
    """{(decision_year, player_key, kind): value} over a vm frame's fold blocks: a
    training row reads at its matrix cutoff, a test row at its pinned preseason read."""
    out = {}
    for _fold, blk in by_fold.items():
        for kind in ("train", "test"):
            for r in blk[kind]:
                key = (int(r["decision_year"]), r["player_key"], kind)
                if key in out:
                    continue
                rw = raw.get(r["player_key"]) or {}
                cut = rw.get("cutoff")
                if kind == "test" and pinned_asof.get(r["player_key"]):
                    cut = pinned_asof[r["player_key"]]
                v, _s = tr.value(side, "vm", rw.get("mlbam_id"), int(r["decision_year"]),
                                 cut, D.MILB_FLOOR_DEFAULT)
                out[key] = v
    return out


def twin_values(vals: dict) -> dict:
    """The permuted twin: within each (year, kind), values reassigned across players by a
    fixed-seed shuffle. Same marginal, no information about the player."""
    rng = np.random.default_rng(TWIN_SEED)
    groups: dict = {}
    for key in sorted(vals, key=lambda k: (k[0], k[2], k[1])):
        groups.setdefault((key[0], key[2]), []).append(key)
    out = {}
    for _g, keys in sorted(groups.items()):
        v = [vals[k] for k in keys]
        perm = rng.permutation(len(keys))
        for i, k in enumerate(keys):
            out[k] = v[int(perm[i])]
    return out


def coverage(vals: dict) -> dict:
    """{str(year): {"rows", "with_value"}} over the test-role keys."""
    out: dict = {}
    for (y, _pk, kind), v in vals.items():
        if kind != "test":
            continue
        c = out.setdefault(str(y), {"rows": 0, "with_value": 0})
        c["rows"] += 1
        c["with_value"] += int(v is not None)
    return dict(sorted(out.items()))


# ---------------------------------------------------------------------------
# the reads (tools/efv_v3_backtest's Inputs)
# ---------------------------------------------------------------------------

def _bt():
    p = str(ROOT / "tools")
    if p not in sys.path:
        sys.path.insert(0, p)
    import efv_v3_backtest as BT
    return BT


def register_columns(arms) -> None:
    """Make the arms addable in this process only (efv_v3.W2_COLUMNS is not edited on
    disk): each is a skill-head column of its side under the screening prefix."""
    import efv_v2_model as H
    import efv_v3 as V3
    for a in arms:
        V3.W2_COLUMNS[a["name"]] = {"side": a["side"], "head": "skill",
                                    "module": "efv_w2_popmle", "arg": a["side"],
                                    "key": f"{H.V2_SCREEN_PREFIX}{a['name']}"}


def config_for(arms) -> dict:
    import efv_v3 as V3
    cfg = V3.base_config()
    for a in arms:
        cfg["add"][a["side"]]["skill"].append(a["name"])
    return V3.validate_config(cfg)


CAND, BASE = "efv_v3", "efv_v2"
COMPARISONS = (("candidate_vs_efv_v2_base", CAND, BASE),
               ("candidate_vs_prospx_consensus", CAND, "prospx_consensus"),
               ("efv_v2_base_vs_prospx_consensus", BASE, "prospx_consensus"))
_RENAME = {"efv_v3": "efv_v2_candidate", "efv_v2": "efv_v2_base"}


def _rnd(v, d=5):
    return None if v is None else round(float(v), d)


def block(rows: list[dict], *, B: int, stats=("within", "pooled", "auc"),
          comparisons=COMPARISONS) -> dict:
    """The screening-ledger frame shape on `rows`: raters (renamed), deltas per
    comparison with E_cond CI95, and the pooled secondary."""
    import efv_v2_stat as S
    BT = _bt()
    fb = BT.frame_block(rows, B=B, stats=stats, comparisons=comparisons, scopes=("both",))
    raters = {_RENAME.get(k, k): v for k, v in fb["raters"].items()}
    out = {"n": fb["n"], "n_by_side": fb["n_by_side"], "n_players": fb["n_players"],
           "groups": fb["groups"], "statistic": S.STAT_LABEL[S.PRIMARY],
           "raters": raters, "deltas": fb["deltas"]}
    if "pooled" in stats:
        out["secondary"] = {
            "statistic": S.STAT_LABEL["pooled"],
            "raters": {n: r.get("pooled") for n, r in raters.items()},
            "deltas": {n: {k: (d.get("pooled") or {}).get(k)
                           for k in ("delta", "ci95", "mde95", "reading")}
                       for n, d in fb["deltas"].items()}}
    return out


def admitted(rec: dict, key: str, side: str) -> dict:
    folds = {k: v for k, v in rec.items() if k.startswith(f"{side}|")}
    n = sum(1 for v in folds.values() if key in (v.get("skill_keys") or []))
    return {"admitted_folds": n, "n_folds": len(folds),
            "by_fold": {k.split("|")[1]: key in (v.get("skill_keys") or [])
                        for k, v in sorted(folds.items())}}


def overlap(inp, fid: str, cols: dict) -> dict:
    """Spearman rank correlation of the column with the V2 drivers it overlaps, on each
    side's test rows (the named re-test's disclosure). Copies of the rows' own views."""
    import efv_v2_stat as S  # noqa: F401
    from scipy.stats import spearmanr
    out = {}
    for a in ARMS:
        side = a["side"]
        vals = cols[side][a["name"]]
        res = {}
        for drv in OVERLAP_KEYS[side]:
            xs, ys = [], []
            for fold, blk in inp.frames[fid]["by_side"][side].items():
                for r in blk["test"]:
                    v = vals.get((int(r["decision_year"]), r["player_key"], "test"))
                    d = (r.get("v2") or {}).get(drv)
                    if v is not None and d is not None:
                        xs.append(v)
                        ys.append(float(d))
            rho = spearmanr(xs, ys).statistic if len(xs) >= 20 else None
            res[drv] = {"spearman": _rnd(rho, 4), "n": len(xs)}
        out[side] = res
    return out


def read_frame(inp, fid: str, cols: dict, *, B: int, role: str, note: str,
               twin: bool, log=print) -> dict:
    """One frame: the arms' column attached, the configuration's orders, the both-sides
    block and the per-side blocks (each arm's ledger frame), and the twin's within legs."""
    BT = _bt()
    import efv_v2_model as H
    inp.cols = {fid: cols}
    cfg = config_for(ARMS)
    t0 = time.time()
    orders, rec = inp.orders(fid, cfg)
    rows = inp.rows_with(fid, orders)
    out = {"frame_version": BT.FRAME_VERSION[fid], "role": role, "note": note,
           "window": [min(inp.frames[fid]["folds"]), max(inp.frames[fid]["folds"])],
           "receipts": rec, "both": block(rows, B=B), "arms": {}}
    for a in ARMS:
        side = a["side"]
        key = f"{H.V2_SCREEN_PREFIX}{a['name']}"
        sel = [c for c in rows if c["side"] == side]
        blk = block(sel, B=B)
        blk.update({"frame_version": BT.FRAME_VERSION[fid], "window": out["window"],
                    "note": note, **admitted(rec, key, side),
                    "fold_deltas_vs_v2": BT.fold_deltas(sel, CAND, BASE),
                    "fold_deltas_vs_consensus": BT.fold_deltas(sel, CAND, "prospx_consensus")})
        w = blk["deltas"]["candidate_vs_efv_v2_base"]["spearman"]
        c = blk["deltas"]["candidate_vs_prospx_consensus"]["spearman"]
        blk["verdict"] = (f"{'DEVELOPMENT ONLY' if role == 'development' else 'SPENT FRAME'}: "
                          f"within vs V2 {_rnd(w.get('delta'), 4)} (CI95 {w.get('ci95')}), vs "
                          f"consensus {_rnd(c.get('delta'), 4)} (CI95 {c.get('ci95')}); "
                          f"admitted in {blk['admitted_folds']} of {blk['n_folds']} folds; "
                          "adjudicates nothing")
        out["arms"][a["name"]] = blk
        log(f"  {fid} {a['name']}: admitted {blk['admitted_folds']}/{blk['n_folds']}, within "
            f"vs V2 {w.get('delta')} {w.get('ci95')}, vs consensus {c.get('delta')} "
            f"{c.get('ci95')}")
    if twin:
        tcols = {s: dict(cols[s]) for s in cols}
        for a, t in zip(ARMS, TWINS):
            tcols[a["side"]][t["name"]] = twin_values(cols[a["side"]][a["name"]])
        inp.cols = {fid: tcols}
        to, trec = inp.orders(fid, config_for(TWINS))
        trows = inp.rows_with(fid, to)
        out["twin"] = {}
        for t in TWINS:
            sel = [c for c in trows if c["side"] == t["side"]]
            tb = block(sel, B=B, stats=("within",), comparisons=COMPARISONS[:2])
            tb.update(admitted(trec, f"{H.V2_SCREEN_PREFIX}{t['name']}", t["side"]))
            out["twin"][t["name"]] = tb
            w = tb["deltas"]["candidate_vs_efv_v2_base"]["spearman"]
            log(f"  {fid} {t['name']} (twin): admitted {tb['admitted_folds']}/{tb['n_folds']}, "
                f"within vs V2 {w.get('delta')} {w.get('ci95')}")
    out["overlap"] = overlap(inp, fid, cols)
    out["coverage"] = {a["side"]: coverage(cols[a["side"]][a["name"]]) for a in ARMS}
    out["elapsed_s"] = round(time.time() - t0, 1)
    inp.cols = {}
    return out


def _git(*args) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def doc_header() -> dict:
    import efv_labels as L
    import efv_v2_model as H
    import efv_v2_stat as S
    BT = _bt()
    return {"schema": 1, "item": ITEM, "produced_by": TOOL, "generated_at": _now(),
            "role": "development", "adjudicates": False, "selects": False,
            "exploratory": False, "note": DEV_NOTE,
            "owner_decision": ("EW2-10 (choose on lv_dev and vm_dev only; R-LV and R-VM are "
                               "spent and reported as such) and EW2-12 (new rows as a new "
                               "source approved for this column), 2026-10-08"),
            "named_retest": ("the column overlaps V2's obp_rel and contact (hitters) and k_rel "
                             "(pitchers); the overlap is disclosed per frame under 'overlap'"),
            "label": BT._label() | {"provider": L.provider(),
                                    "resolved_through": L.resolved_through()},
            "code": {"commit": _git("rev-parse", "--short=8", "HEAD"), "tool": TOOL,
                     "module_sha256": _sha(Path(__file__)),
                     "efv_v3_backtest_sha256": _sha(ROOT / "tools" / "efv_v3_backtest.py"),
                     "efv_v2_model_sha256": _sha(ROOT / "efv_v2_model.py")},
            "assembly_sha256": _sha(H.ASSEMBLY_PATH),
            "estimator": {"name": "E_cond", "B": None, "seed": S.SEED_DEFAULT,
                          "clusters": "player", "statistic": S.STAT_LABEL[S.PRIMARY]},
            "construction": {
                "column": COLUMN, "population_seasons": [POP_SEASONS[0], POP_SEASONS[-1]],
                "population_rows": "pre-debut affiliated player-seasons at LINE_MIN exposure",
                "line_min": LINE_MIN, "horizon": HORIZON, "max_back": MAX_BACK,
                "league_min_lines": LEAGUE_MIN_LINES, "min_train_rows": MIN_TRAIN_ROWS,
                "features": FEATURES, "rates": RATES, "model": "sklearn "
                "HistGradientBoostingRegressor", "params": GBM_PARAMS,
                "label": ("fWAR over seasons s + 1 .. s + 6 from data/fwar_vintage.json via "
                          "data/_labs/efv_w2/pop_fwar.json; 0 when never reached"),
                "as_of": ("model(kind, Y, side) fits seasons s with s + 6 <= Y - 1 and leaves "
                          "out every player of the frame read at Y; the row reads its last "
                          "MiLB season ended by its read (efv_dataset._milb_features rule)")},
            "label_join": {"path": "data/_labs/efv_w2/pop_fwar.json",
                           "sha256": _sha(POP_FWAR_PATH)},
            "arms_declared": [dict(a) for a in ARMS], "twins_declared": [dict(t) for t in TWINS],
            "guards": {"reserved_lv": sorted(F.RESERVED_LV),
                       "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
                       "anchor_gate_grouping": False}}


def dev_read(*, B: int | None = None, log=print) -> dict:
    BT = _bt()
    import efv_v2_assemble as ASM
    import efv_v2_model as H
    import efv_v2_stat as S
    B = S.B_DEFAULT if B is None else int(B)
    t0 = time.time()
    frames_lv = ASM.build_frames()
    orig = ASM.build_frames
    ASM.build_frames = lambda *a, **k: frames_lv
    try:
        inp = BT.build_dev(log=log)
    finally:
        ASM.build_frames = orig
    register_columns(ARMS + TWINS)
    log(f"development inputs built ({round(time.time() - t0, 1)} s)")
    raw_by_side = {s: {r["player_key"]: r for r in json.loads(
        H._matrix_path(s).read_text(encoding="utf-8"))} for s in F.SIDES}
    vm_years = sorted({int(r["decision_year"]) for s in F.SIDES
                       for blk in inp.frames["vm_dev"]["by_side"][s].values()
                       for r in blk["train"] + blk["test"]})
    if any(y >= F.R_VM_FIRST_DEBUT_YEAR for y in vm_years):
        raise F.ReservedFrameError(f"vm_dev reaches R-VM: {vm_years}")
    if any(int(V) in F.RESERVED_LV for s in F.SIDES for V in frames_lv[s]):
        raise F.ReservedFrameError("lv_dev frames carry a reserved vintage")
    excl = lv_exclusions(frames_lv) | vm_exclusions(raw_by_side, vm_years)
    tr = Translator(excl)
    pinned = {}
    for s in F.SIDES:
        mine: dict = {}
        H.pinned_inputs(s, H.matrix_training_rows(s), mine)
        pinned[s] = {pk: rec.get("asof_date") for pk, rec in mine.items()}
    cols = {"lv_dev": {s: {} for s in F.SIDES}, "vm_dev": {s: {} for s in F.SIDES}}
    for a in ARMS:
        s = a["side"]
        t1 = time.time()
        cols["lv_dev"][s][a["name"]] = lv_values(tr, s, frames_lv[s])
        cols["vm_dev"][s][a["name"]] = vm_values(tr, s, inp.frames["vm_dev"]["by_side"][s],
                                                 raw_by_side[s], pinned[s])
        log(f"  column {a['name']}: values built ({round(time.time() - t1, 1)} s)")
    doc = doc_header()
    doc["estimator"]["B"] = B
    doc["population_fits"] = dict(sorted(tr.receipts.items()))
    for fid in BT.FRAMES_DEV:
        doc[fid] = read_frame(inp, fid, cols[fid], B=B, role="development",
                              note=DEV_NOTE, twin=True, log=log)
    doc["base_parity"] = {"ds16": inp.meta.get("base_parity", {}).get("reproduces"),
                          "v3_base": inp.meta.get("v3_base_parity")}
    doc["summary"] = summary(doc)
    doc["elapsed_s"] = round(time.time() - t0, 1)
    write_json(doc, OUT_PATH)
    log(f"wrote {OUT_PATH} in {doc['elapsed_s']} s")
    return doc


def spent_read(*, B: int | None = None, gate_sha: str = CONFIRM_GATE_SHA, log=print) -> dict:
    """The spent-frame read (R-LV, R-VM), added to the development artifact under
    `spent`. Report only: nothing is chosen on it and no ledger row is written."""
    BT = _bt()
    import efv_v2_assemble as ASM
    import efv_v2_model as H
    import efv_v2_stat as S
    import efv_v3 as V3
    B = S.B_DEFAULT if B is None else int(B)
    if not OUT_PATH.exists():
        raise FileNotFoundError("the development read comes first (it is the choice)")
    doc = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    if doc.get("spent"):
        raise RuntimeError("the spent frames were already read into this artifact")
    t0 = time.time()
    inp = BT.build_reserved(V3.base_config(), gate_sha=gate_sha, log=log)
    register_columns(ARMS)
    universe = F.load_universe()
    frames_dev = ASM.build_frames()
    frames_res = {s: {V: (F.build_frame(s, V, gate_sha=gate_sha, universe=universe), [])
                      for V in sorted(F.RESERVED_LV)} for s in F.SIDES}
    frames_all = {s: {**frames_dev[s], **frames_res[s]} for s in F.SIDES}
    raw_by_side = {s: {r["player_key"]: r for r in json.loads(
        H._matrix_path(s).read_text(encoding="utf-8"))} for s in F.SIDES}
    vm_years = sorted({int(r["decision_year"]) for s in F.SIDES
                       for blk in inp.frames["vm_pros"]["by_side"][s].values()
                       for r in blk["train"] + blk["test"]})
    excl = lv_exclusions(frames_all) | vm_exclusions(raw_by_side, vm_years)
    tr = Translator(excl, gate_sha=gate_sha)
    pinned = {}
    for s in F.SIDES:
        mine: dict = {}
        H.pinned_inputs(s, H.matrix_training_rows(s), mine)
        pinned[s] = {pk: rec.get("asof_date") for pk, rec in mine.items()}
    cols = {"lv_res": {s: {} for s in F.SIDES}, "vm_pros": {s: {} for s in F.SIDES}}
    for a in ARMS:
        s = a["side"]
        cols["lv_res"][s][a["name"]] = lv_values(tr, s, frames_all[s])
        cols["vm_pros"][s][a["name"]] = vm_values(tr, s, inp.frames["vm_pros"]["by_side"][s],
                                                  raw_by_side[s], pinned[s])
    spent = {"note": SPENT_NOTE, "gate_sha": gate_sha, "guards": inp.guards,
             "chooses_nothing": True, "ledger_rows": False,
             "population_fits": dict(sorted(tr.receipts.items()))}
    for fid in BT.FRAMES_RES:
        spent[fid] = read_frame(inp, fid, cols[fid], B=B, role="spent", note=SPENT_NOTE,
                                twin=False, log=log)
    spent["elapsed_s"] = round(time.time() - t0, 1)
    doc["spent"] = spent
    doc["summary"] = summary(doc)
    write_json(doc, OUT_PATH)
    log(f"spent frames added to {OUT_PATH} ({spent['elapsed_s']} s)")
    return doc


def summary(doc: dict) -> list[dict]:
    """One line per arm: per frame rows, admitted folds and the within deltas against V2
    and consensus with CI95. Copies only."""
    out = []
    frames = [(fid, doc.get(fid)) for fid in ("lv_dev", "vm_dev")]
    frames += [(fid, (doc.get("spent") or {}).get(fid)) for fid in ("lv_res", "vm_pros")]
    for a in ARMS + ("both",):
        name = a if a == "both" else a["name"]
        row = {"arm": name}
        for fid, f in frames:
            if not f:
                continue
            blk = f["both"] if name == "both" else f["arms"][name]
            d = blk["deltas"]
            v2 = d["candidate_vs_efv_v2_base"]["spearman"]
            vc = d["candidate_vs_prospx_consensus"]["spearman"]
            ent = {"n": blk["n"], "vs_v2": [v2.get("delta"), v2.get("ci95")],
                   "vs_consensus": [vc.get("delta"), vc.get("ci95")]}
            if name != "both":
                ent["admitted_folds"] = f"{blk['admitted_folds']}/{blk['n_folds']}"
            if fid in ("lv_res", "vm_pros"):
                ent["note"] = SPENT_NOTE
            row[fid] = ent
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# progress-ledger rows (development frames only)
# ---------------------------------------------------------------------------

def ledger_docs(doc: dict) -> list[dict]:
    out = []
    for a in ARMS:
        for fid in ("lv_dev", "vm_dev"):
            f = doc.get(fid) or {}
            blk = (f.get("arms") or {}).get(a["name"])
            if not blk:
                continue
            out.append({"role": "development",
                        "model_id": f"{MODEL_PREFIX}{a['name']}:{a['side']}",
                        "generated_at": doc.get("generated_at"),
                        "label": doc.get("label") or {}, "code": doc.get("code") or {},
                        "screening": {"wave": f"efv4 ({fid})", "exploratory": False,
                                      "development_only": True, "adjudicates": False,
                                      "selects": False, "head": "skill",
                                      "statistic_column": COLUMN, "named_retest": True,
                                      "admitted_folds": blk["admitted_folds"],
                                      "n_folds": blk["n_folds"]},
                        "frames": {fid: blk}})
    return out


def update_ledger(*, path: Path = OUT_PATH, ledger_path=None, out_path=None,
                  trigger: str = "efv_change") -> dict:
    import efv_progress as P
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    now_dt = datetime.now(timezone.utc)
    now_iso = P._now_iso(now_dt)
    src = [{"path": P._rel(Path(path)), "generated_at": doc.get("generated_at"),
            "sha256": _sha(path)}]
    cands = []
    for d in ledger_docs(doc):
        cands += P.build_dev_rows(d, sources=src, date=now_dt.date().isoformat(),
                                  trigger=trigger, now_iso=now_iso,
                                  frames=tuple(d["frames"]), raters=P.SCREEN_RATERS,
                                  deltas=P.SCREEN_DELTAS, statistic_fields=True)
    if not cands:
        return {"appended": [], "status": "no development rows"}
    res = P.commit_rows(cands, out_path=out_path, ledger_path=ledger_path,
                        sb=P._load_json(P.DATA_DIR / P.SB_NAME), now_iso=now_iso)
    res["status"] = "ok"
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--join", action="store_true", help="write the label join")
    ap.add_argument("--dev-read", action="store_true", help="the development read")
    ap.add_argument("--spent-read", action="store_true", help="the spent-frame read")
    ap.add_argument("--ledger", action="store_true", help="development ledger rows")
    ap.add_argument("--ledger-path", default=None, help="durable ledger path")
    ap.add_argument("--B", type=int, default=None)
    a = ap.parse_args()

    def _log(msg):
        print(msg, flush=True)
    if a.join:
        t = time.time()
        j = build_label_join()
        write_json(j, POP_FWAR_PATH, indent=None)
        _log(f"wrote {POP_FWAR_PATH}: {j['n_members']} members, {j['n_reached']} reached "
             f"({round(time.time() - t, 1)} s)")
    if a.dev_read:
        r = dev_read(B=a.B, log=_log)
        _log(json.dumps(r["summary"], indent=1))
    if a.spent_read:
        r = spent_read(B=a.B, log=_log)
        _log(json.dumps(r["summary"], indent=1))
    if a.ledger:
        _log(json.dumps(update_ledger(ledger_path=a.ledger_path), indent=1, default=str))
