# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v5 metric atlas, second part: tool grades and individual Statcast components
(EFV5_ATLAS_TOOLS_STATCAST; owner 2026-10-15, decision EW3-7 in
`_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, verbatim: "Can we recheck tool grades using
the same methodology, checking for positional splits, age splits, and level splits? Can
we also recheck individual Statcast components?").

THE SAME METHODOLOGY as the first atlas (efv5_atlas.py, EFV5_METRIC_ATLAS), reused
rather than restated: the same rows and labels (efv5_atlas.LABELS: reach3, reach5, w3,
l6, reach_h, war_rate_h, each with its resolution rule and its clean frame), the same
raw score and INCREMENTAL score over PROSPX consensus FV out of fold
(efv5_atlas.score_cell), the same player-clustered bootstrap CI95 (efv5_atlas.
cell_weights), the same minimum cell (efv5_atlas.MIN_PLAYERS players and MIN_POS
reachers), the same spent-frame flag (reserved_overlap, efv5_atlas.SPENT_NOTE) and the
same candidate rule (efv5_atlas._is_candidate). Benjamini-Hochberg q runs within each
(family, label) of the two NEW families below, so the first atlas's q values are not
diluted and this module's are not borrowed. The first atlas's artifacts are never
written here.

FAMILY "tools": scouting tool grades as of each list date. A row is one (player,
season S) with a PROSPX consensus read in the V = S + 1 preseason window (the same
efv_vintage_frame row the first atlas reads), placed at the player's LEVEL AS OF THE
LIST: the highest level with a qualified line in S (the level the player finished S
at). The grades are read off the dated FanGraphs and MLB Pipeline boards in the
prospects.db snapshots through efv_w2_scout.SnapshotIndex, restricted to the row's own
list: per source, the latest board dated inside the V window (V-01-01) and on or before
the frame row's as-of date. No board from another list vintage is carried in, so no
grade from the reserved list vintages 2020 and 2021 (R-LV) is ever read, and no
snapshot dated on or after TOOL_SNAPSHOT_CAP is loaded at all. Per tool:
    fut     the future grade, the mean of the sources that carry it
    pre     the present grade (FanGraphs from 2017; Pipeline only inside the
            2011 to 2013 report text), the mean of the sources that carry it
    gap     future minus present (projected growth), per source then averaged over
            the sources that carry both
    fgmp    FanGraphs future minus Pipeline future, where both carry the tool
Hitters: hit, raw power (FanGraphs only), game power, run (speed), field, arm
(FanGraphs throw, else its _extras arm; Pipeline throw). Pitchers: fastball, slider,
curveball, changeup, cutter (FanGraphs carries it on a handful of rows), control or
command (Pipeline control, FanGraphs command).

FAMILY "statcast": the individual tracked components, each on its own rather than as
Stuff+, on the first atlas's (player, S, level) rows at the tracked levels only
(Triple-A 2022 to 2025 and the Florida State League, Single-A, 2021 to 2025), with the
first atlas's exposure rule (efv5_atlas.TRACK_MIN). From efv5_tracking's tables:
pitchers fastball mean and 95th-percentile velocity, primary fastball induced vertical
and arm-side horizontal break, extension, arm angle; hitters mean, 90th-percentile and
max exit velocity, hard-hit, barrel and sweet-spot rates, launch-angle sd, chase rate,
zone contact, whiff rate, and bat speed (served on no tracked pitch: the column is kept
so the artifact says so). Computed here from the same cached pitches
(.cache/efv5_savant_minors/days, read only, no fetch): the primary fastball's spin rate,
vertical approach angle (at the front of the plate, from the pitch's release velocity and
acceleration) and release height, and by pitch class (efv5_tracking.PITCH_CLASS: fastball,
breaking, offspeed) the whiff rate (whiffs / swings), the called-strike rate (called
strikes / pitches) and the chase rate induced (swings at out-of-zone tracked pitches /
out-of-zone tracked pitches), each defined when the class has at least CLASS_MIN pitches.

GROUPS as in the first atlas: side x level x age-for-level band (terciles inside the
level-season, plus all) x hitter position group (C, SS, CF, other IF, corner OF, 1B/DH,
from the listing position inside the V window; listed rows only) or pitcher role (SP/RP
by the EFV3_C05 rule on the row's own season line). Never a cell by FV level.

REDUNDANCY RECEIPT. Tool grades are inputs to the consensus FV itself (the graders
read the same tools), so their INCREMENTAL lift is expected to be small; the artifact
carries, per metric, the within-season Spearman of the metric against consensus FV on
the listed rows (a continuous association, no FV cell), which says how much of the
metric consensus has already priced.

BANS. No served number moves and nothing served imports this module. Nothing groups,
counts or averages anything by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md);
consensus FV is a covariate and a comparator only. No projections retrain, no backtest
module call, no network request at all. The artifacts are development only.

Run:  python efv5_atlas_tools.py --check          (coverage only: no label is read)
      python efv5_atlas_tools.py --run [--b 400]  (both families; writes the artifacts)
      python efv5_atlas_tools.py --md PATH        (ATLAS_TOOLS.md from the artifact)
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

import efv5_atlas as A
import efv5_tracking as TR
import efv_vintage_frame as F
import efv_w2_scout as SC
import source_backtest as SB

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "efv5_atlas_tools.json"
CELLS_PATH = DATA_DIR / "_labs" / "efv5" / "efv5_atlas_tools_cells.json"
TOOL = "efv5_atlas_tools.py"
ITEM = "EFV5_ATLAS_TOOLS_STATCAST"
SCHEMA = 1
NOTE = ("eFV v5 metric atlas, tool grades and individual Statcast components, development "
        "read (EW3-7): nothing served moves, no cell by consensus-FV level, consensus FV a "
        "covariate only")
FAMILIES = ("tools", "statcast")

#: Declared before any read.
TOOL_SOURCES = SC.SOURCES                                  # fangraphs, mlb_pipeline
#: No snapshot dated on or after this day is loaded: the end of the last list window
#: the atlas reads (V = HORIZON), so no in-season board of the horizon year enters.
TOOL_SNAPSHOT_CAP = f"{A.HORIZON}{SB._WINDOW_END_MMDD}"
TRACK_LEVELS = ("A", "AAA")
TRACK_SEASONS: tuple[int, ...] = tuple(s for s in A.SEASONS if s >= 2021)
CLASS_MIN = 25                                             # pitches of the class
CLASSES = ("fb", "br", "os")
CLASS_LABEL = {"fb": "fastballs", "br": "breaking balls", "os": "offspeed"}
TOP_CELLS = 25
#: Vertical approach angle: the plate front, feet from the tip of home plate, and the
#: Statcast release reference (vx0, vy0, vz0 and ax, ay, az are given at y = 50 ft).
VAA_Y0 = 50.0
VAA_YF = 17.0 / 12.0

#: tool -> (side, per-source key, what). Pipeline carries no raw power and FanGraphs
#: carries a cutter on a handful of rows only; the artifact counts what is carried.
TOOLS: dict[str, tuple[str, str, str]] = {
    "hit": ("hit", "hit", "hit tool"),
    "raw_pwr": ("hit", "raw_pwr", "raw power"),
    "game_pwr": ("hit", "game_pwr", "game power"),
    "run": ("hit", "speed", "run (speed)"),
    "field": ("hit", "field", "field"),
    "arm": ("hit", "throw", "arm"),
    "fb": ("pit", "fb", "fastball"),
    "sl": ("pit", "sl", "slider"),
    "cb": ("pit", "cb", "curveball"),
    "ch": ("pit", "ch", "changeup"),
    "ct": ("pit", "ct", "cutter"),
    "cmd": ("pit", "cmd", "control (Pipeline) or command (FanGraphs)"),
}
TOOL_PARTS = {"fut": "future grade (mean of the sources that carry it)",
              "pre": "present grade (mean of the sources that carry it)",
              "gap": "future minus present, per source, averaged (projected growth)",
              "fgmp": "FanGraphs future minus Pipeline future (source disagreement)"}

#: Metric -> (family, side, what).
METRICS: dict[str, tuple[str, str, str]] = {}


def _m(name, family, side, what):
    METRICS[name] = (family, side, what)


for _t, (_s, _k, _w) in TOOLS.items():
    for _p, _pw in TOOL_PARTS.items():
        _m(f"tg_{_t}_{_p}_{_s}", "tools", _s, f"{_w}: {_pw}")

#: Statcast components read off efv5_tracking's tables (column -> what).
SC_PIT_TABLE = {
    "fb_velo_mean": "fastball velocity, mean", "fb_velo_p95": "fastball velocity, 95th pct",
    "fb_ivb": "primary fastball induced vertical break (inches)",
    "fb_hb_arm": "primary fastball horizontal break, arm side positive (inches)",
    "extension": "release extension (feet)", "arm_angle": "arm angle (degrees)",
}
#: Computed here from the cached pitches.
SC_PIT_PITCH = {
    "fb_spin": "primary fastball spin rate (rpm)",
    "fb_vaa": "primary fastball vertical approach angle at the plate front (degrees)",
    "fb_rel_z": "primary fastball release height (feet)",
}
for _c in CLASSES:
    SC_PIT_PITCH[f"whiff_{_c}"] = f"whiffs / swings on {CLASS_LABEL[_c]}"
    SC_PIT_PITCH[f"cstr_{_c}"] = f"called strikes / pitches on {CLASS_LABEL[_c]}"
    SC_PIT_PITCH[f"chase_{_c}"] = (f"swings / out-of-zone pitches on {CLASS_LABEL[_c]} "
                                   f"(chase induced)")
SC_HIT_TABLE = {
    "ev_mean": "exit velocity, mean", "ev_p90": "exit velocity, 90th pct",
    "ev_max": "max exit velocity", "hard_hit": "hard-hit rate (95 mph or more)",
    "barrel": "barrel rate", "sweet_spot": "sweet-spot rate (8 to 32 degrees)",
    "la_sd": "launch angle sd", "chase": "chase rate", "zone_contact": "zone contact",
    "whiff": "whiffs / swings", "bat_speed": "bat speed (where served)",
}
for _k, _w in SC_PIT_TABLE.items():
    _m(f"sc_{_k}_pit", "statcast", "pit", _w)
for _k, _w in SC_PIT_PITCH.items():
    _m(f"sc_{_k}_pit", "statcast", "pit", _w)
for _k, _w in SC_HIT_TABLE.items():
    _m(f"sc_{_k}_hit", "statcast", "hit", _w)


def side_metrics(family: str, side: str) -> list[str]:
    return [m for m, (fam, s, _w) in METRICS.items() if fam == family and s == side]


# ---------------------------------------------------------------------------
# consensus reads with their as-of date (the first atlas's rows, one more field)
# ---------------------------------------------------------------------------

def consensus_reads_asof(side: str, listings: dict, *, vintages=A.CONSENSUS_VINTAGES,
                         universe=None, log=print) -> dict:
    """efv5_atlas.consensus_reads with the frame row's as-of date and window kept:
    {(mlbam, S = V - 1): {"fv", "player_key", "group", "asof", "window", "vintage"}}.
    The fv, player_key and group are the first atlas's, row for row (test-pinned)."""
    universe = universe if universe is not None else F.load_universe()
    out: dict = {}
    for V in vintages:
        assert int(V) not in F.RESERVED_LV
        rows = F.build_frame(side, int(V), universe=universe, milb=False, sidecars=False)
        n = 0
        for r in rows:
            fv = A._f((r.get("grades") or {}).get(SB.CONSENSUS_KEY))
            pid = r.get("mlbam_id")
            if fv is None or not pid:
                continue
            lo, hi = r["window"]
            pos = A.listing_position(listings, r["player_key"], lo, hi) or r.get("position")
            key = (int(pid), int(V) - 1)
            if key in out:
                continue
            out[key] = {"fv": fv, "player_key": r["player_key"],
                        "group": A.position_group(pos) if side == "hit" else None,
                        "asof": r.get("asof_date"), "window": [lo, hi], "vintage": int(V)}
            n += 1
        log(f"  consensus {side} V {V}: {len(rows)} frame rows, {n} with a consensus and an id")
    return out


# ---------------------------------------------------------------------------
# family "tools": the grades as of the list
# ---------------------------------------------------------------------------

def load_tool_index(path: Path | str | None = None) -> SC.SnapshotIndex:
    return SC.SnapshotIndex.from_db(path or SC.DB_PATH, cap=TOOL_SNAPSHOT_CAP)


def list_entries(index: SC.SnapshotIndex, player_key: str, asof: str | None,
                 window_lo: str) -> dict[str, tuple]:
    """{source: entry}: per source the latest board dated inside [window_lo, asof]."""
    if not asof:
        return {}
    hi = str(asof)[:10]
    lo = str(window_lo)[:10]
    if hi < lo:
        return {}
    days = (date.fromisoformat(hi) - date.fromisoformat(lo)).days
    return {s: e for s, e in index.asof(player_key, hi, lookback_days=days).items()
            if e[0] >= lo}


def _tool_pair(entry: tuple, key: str) -> tuple[float | None, float | None]:
    """(future, present) of one tool off one source's entry; arm falls back to the
    FanGraphs _extras arm (efv_w2_scout's rule)."""
    _sd, _s, tools, present, extras, _pos = entry
    fut = tools.get(key)
    if fut is None and key == "throw":
        fut = extras.get("arm")
    return fut, present.get(key)


def tool_values(per_source: dict[str, tuple], side: str) -> dict[str, float]:
    """{metric: value} for the side's tools off the as-of entries of each source."""
    out: dict[str, float] = {}
    for t, (s, key, _w) in TOOLS.items():
        if s != side:
            continue
        futs, pres, gaps, by_src = [], [], [], {}
        for src in TOOL_SOURCES:
            e = per_source.get(src)
            if e is None:
                continue
            f, p = _tool_pair(e, key)
            if f is not None:
                futs.append(f)
                by_src[src] = f
            if p is not None:
                pres.append(p)
            if f is not None and p is not None:
                gaps.append(f - p)
        if futs:
            out[f"tg_{t}_fut_{side}"] = float(sum(futs) / len(futs))
        if pres:
            out[f"tg_{t}_pre_{side}"] = float(sum(pres) / len(pres))
        if gaps:
            out[f"tg_{t}_gap_{side}"] = float(sum(gaps) / len(gaps))
        if "fangraphs" in by_src and "mlb_pipeline" in by_src:
            out[f"tg_{t}_fgmp_{side}"] = float(by_src["fangraphs"] - by_src["mlb_pipeline"])
    return out


def list_level_rows(T: A.Table) -> dict[tuple[int, int], int]:
    """{(pid, S): row index} of the player's highest-level qualified line in S, over
    the rows with a consensus read (the level as of the list)."""
    best: dict[tuple[int, int], int] = {}
    for i in np.flatnonzero(np.isfinite(T.fv)):
        k = (int(T.pid[i]), int(T.season[i]))
        j = best.get(k)
        if j is None or A.LEVEL_RANK[T.level[i]] > A.LEVEL_RANK[T.level[j]]:
            best[k] = int(i)
    return best


def _row_from(T: A.Table, i: int, m: dict) -> dict:
    return {"pid": int(T.pid[i]), "season": int(T.season[i]), "level": str(T.level[i]),
            "band": str(T.band[i]), "group": (str(T.group[i]) or None),
            "fv": float(T.fv[i]) if np.isfinite(T.fv[i]) else None, "m": m,
            "y": {lb: (None if not np.isfinite(T.y[lb][i]) else float(T.y[lb][i]))
                  for lb in A.LABELS}}


def tools_table(T: A.Table, cons: dict, index: SC.SnapshotIndex) -> tuple[A.Table, dict]:
    """The tools family's table: one row per (player, S) at the level as of the list,
    with every tool metric the list carries. Rows without any tool grade are left out."""
    side = T.side
    rows, n_empty = [], 0
    for (pid, season), i in sorted(list_level_rows(T).items()):
        cr = cons.get((pid, season))
        if cr is None:
            continue
        per = list_entries(index, cr["player_key"], cr.get("asof"), cr["window"][0])
        m = tool_values(per, side)
        if not m:
            n_empty += 1
            continue
        rows.append(_row_from(T, i, m))
    meta = {"rows": len(rows), "listed_rows_without_a_tool_grade": n_empty}
    return A.Table(side, rows, side_metrics("tools", side)), meta


# ---------------------------------------------------------------------------
# family "statcast": the individual components
# ---------------------------------------------------------------------------

def vaa_deg(vy0, vz0, ay, az, y0: float = VAA_Y0, yf: float = VAA_YF):
    """Vertical approach angle in degrees at y = yf (negative: the pitch descends),
    from the release-reference velocity and acceleration. Arrays or scalars."""
    vy0, vz0, ay, az = (np.asarray(v, dtype=np.float64) for v in (vy0, vz0, ay, az))
    with np.errstate(invalid="ignore", divide="ignore"):
        vyf = -np.sqrt(vy0 * vy0 - 2.0 * ay * (y0 - yf))
        t = (vyf - vy0) / ay
        vzf = vz0 + az * t
        return -np.degrees(np.arctan(vzf / vyf))


_PITCH_COLS = ("pitch_type", "release_speed", "release_pos_z", "release_spin_rate",
               "pitcher", "description", "zone", "plate_x", "vy0", "vz0", "ay", "az",
               "game_pk", "game_year")


def load_pitches(season: int):
    """The cached pitches of one season (read only) with their level from the cached
    schedule. A season without a cached schedule raises: nothing is fetched."""
    import pandas as pd
    files = sorted((TR.DAYS_DIR / str(int(season))).glob("*.csv.gz"))
    sched_path = TR.SCHED_DIR / f"{int(season)}.json"
    if not files:
        return pd.DataFrame(columns=list(_PITCH_COLS) + ["level"])
    if not sched_path.exists():
        raise FileNotFoundError(f"no cached schedule for {season}; this module never fetches")
    sched = json.loads(sched_path.read_text(encoding="utf-8"))
    df = pd.concat([pd.read_csv(f, usecols=list(_PITCH_COLS), low_memory=False) for f in files],
                   ignore_index=True)
    df["level"] = df["game_pk"].astype("Int64").astype(str).map(sched).fillna("UNK")
    return df


def pitch_components(df, *, min_pitches: float = A.TRACK_MIN["pit"],
                     class_min: int = CLASS_MIN) -> dict:
    """{(pitcher, season, level): {metric: value}} for the computed pitcher components
    (SC_PIT_PITCH) of one frame of pitches. Pure; no I/O."""
    import pandas as pd
    d = df[df["level"].isin(TRACK_LEVELS)].copy()
    if d.empty:
        return {}
    desc = d["description"].fillna("")
    d["sw"] = desc.isin(TR.SWING).astype(np.int64)
    d["wh"] = desc.isin(TR.WHIFF).astype(np.int64)
    d["cs"] = desc.isin(TR.CALLED).astype(np.int64)
    num = lambda c: pd.to_numeric(d[c], errors="coerce")       # noqa: E731
    tracked = num("release_speed").notna() & num("plate_x").notna()
    z = num("zone")
    d["oz"] = (tracked & z.between(11, 14)).astype(np.int64)
    d["ozsw"] = d["oz"] * d["sw"]
    d["pclass"] = d["pitch_type"].map(TR.PITCH_CLASS).fillna("")
    d["vaa"] = vaa_deg(num("vy0"), num("vz0"), num("ay"), num("az"))
    d["spin"] = num("release_spin_rate")
    d["relz"] = num("release_pos_z")
    d["n"] = 1
    keys = ["pitcher", "game_year", "level"]
    tot = d.groupby(keys)["n"].sum()
    keep = tot[tot >= min_pitches].index
    out: dict = {}
    for k in keep:
        out[(int(k[0]), int(k[1]), str(k[2]))] = {}
    # by class
    cls = d[d["pclass"].isin(CLASSES)].groupby(keys + ["pclass"])[["n", "sw", "wh", "cs", "oz", "ozsw"]].sum()
    for (pid, season, lv, c), r in cls.iterrows():
        slot = out.get((int(pid), int(season), str(lv)))
        if slot is None or r["n"] < class_min:
            continue
        slot[f"sc_cstr_{c}_pit"] = float(r["cs"] / r["n"])
        if r["sw"] > 0:
            slot[f"sc_whiff_{c}_pit"] = float(r["wh"] / r["sw"])
        if r["oz"] > 0:
            slot[f"sc_chase_{c}_pit"] = float(r["ozsw"] / r["oz"])
    # the primary fastball (efv5_tracking's rule: the most thrown of FASTBALLS among
    # tracked pitches; a tie goes to the pitch type first in alphabetical order)
    fb = d[tracked & d["pitch_type"].isin(TR.FASTBALLS)]
    if len(fb):
        cnt = fb.groupby(keys + ["pitch_type"])["n"].sum().reset_index()
        cnt = cnt.sort_values(keys + ["n", "pitch_type"], ascending=[True, True, True, False, True])
        prim = cnt.groupby(keys).head(1)[keys + ["pitch_type"]]
        pf = fb.merge(prim, on=keys + ["pitch_type"], how="inner")
        agg = pf.groupby(keys)[["spin", "vaa", "relz"]].mean()
        for (pid, season, lv), r in agg.iterrows():
            slot = out.get((int(pid), int(season), str(lv)))
            if slot is None:
                continue
            for col, name in (("spin", "sc_fb_spin_pit"), ("vaa", "sc_fb_vaa_pit"),
                              ("relz", "sc_fb_rel_z_pit")):
                v = A._f(r[col])
                if v is not None:
                    slot[name] = v
    return out


def table_components(side: str) -> dict:
    """{(mlbam, season, level): {metric: value}} from efv5_tracking's tables, the first
    atlas's exposure rule (efv5_atlas.TRACK_MIN)."""
    path = TR.TABLE_DIR / ("hitter_season_level.csv.gz" if side == "hit" else "pitcher_season_level.csv.gz")
    if not path.exists():
        return {}
    names = SC_HIT_TABLE if side == "hit" else SC_PIT_TABLE
    out: dict = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            exp = A._f(r.get("pa") if side == "hit" else r.get("pitches")) or 0.0
            if exp < A.TRACK_MIN[side] or r["level"] not in TRACK_LEVELS:
                continue
            if int(r["season"]) not in TRACK_SEASONS:
                continue
            vals = {}
            for k in names:
                v = A._f(r.get(k))
                if v is not None:
                    vals[f"sc_{k}_{side}"] = v
            out[(int(r["mlbam"]), int(r["season"]), r["level"])] = vals
    return out


def statcast_components(side: str, *, log=print) -> dict:
    comp = table_components(side)
    if side == "pit":
        for season in TRACK_SEASONS:
            t0 = time.time()
            pc = pitch_components(load_pitches(season))
            n = 0
            for k, v in pc.items():
                if k in comp:
                    comp[k].update(v)
                    n += 1
            log(f"  statcast pit {season}: {len(pc)} pitcher-season-levels computed, "
                f"{n} joined to the table ({time.time() - t0:.0f} s)")
    return comp


def statcast_table(T: A.Table, comp: dict) -> tuple[A.Table, dict]:
    """The statcast family's table: the first atlas's rows at the tracked levels and
    seasons that carry a component line."""
    rows = []
    for i in range(T.n):
        lv = str(T.level[i])
        if lv not in TRACK_LEVELS or int(T.season[i]) not in TRACK_SEASONS:
            continue
        m = comp.get((int(T.pid[i]), int(T.season[i]), lv))
        if not m:
            continue
        rows.append(_row_from(T, i, dict(m)))
    return A.Table(T.side, rows, side_metrics("statcast", T.side)), {"rows": len(rows)}


# ---------------------------------------------------------------------------
# the tables and the run
# ---------------------------------------------------------------------------

def build_tables(log=print) -> dict:
    """{"tools": {side: Table}, "statcast": {side: Table}, "_meta": {...}}."""
    t0 = time.time()
    mlb = A.mlb_seasons()
    war, vintage_id = A.fwar_totals()
    listings = A.load_listings()
    universe = F.load_universe()
    index = load_tool_index()
    out: dict = {"tools": {}, "statcast": {}}
    meta: dict = {"fwar_vintage_id": vintage_id, "mlb_players": len(mlb),
                  "listings_players": len(listings), "tool_snapshot_cap": TOOL_SNAPSHOT_CAP,
                  "tool_index_players": len(index.by_key), "by_side": {}}
    for side in ("hit", "pit"):
        cons = consensus_reads_asof(side, listings, universe=universe, log=log)
        base = A.build_table(side, mlb=mlb, war=war, cons=cons, log=log)
        Tt, mt = tools_table(base, cons, index)
        Ts, ms = statcast_table(base, statcast_components(side, log=log))
        out["tools"][side], out["statcast"][side] = Tt, Ts
        meta["by_side"][side] = {"base_rows": int(base.n), "base_listed": int(np.isfinite(base.fv).sum()),
                                 "tools": mt, "statcast": ms}
        log(f"  {side}: tools {mt}, statcast {ms}")
    meta["seconds_tables"] = round(time.time() - t0, 1)
    out["_meta"] = meta
    return out


def run_family(tables: dict, family: str, *, B: int = A.B_DEFAULT, seed: int = A.SEED,
               log=print) -> list[dict]:
    """efv5_atlas.run_atlas's loop over one family's tables with this module's metric
    list; BH q within (family, label)."""
    t0 = time.time()
    rows: list[dict] = []
    for side in ("hit", "pit"):
        T = tables[family][side]
        if T.n == 0:
            continue
        folds_all = A.player_folds(T.pid, A.FOLDS, seed)
        for lv, band, g, mask in A.cell_masks(T):
            for label, frame, m_frame in [(lb, fr, m) for lb in A.LABELS
                                          for fr, m in A.label_frames(lb, T.season)]:
                mask_f = mask & m_frame
                weights = A.cell_weights(T, mask_f, label, B, seed)
                if weights is None:
                    continue
                for metric in T.metrics:
                    r = A.score_cell(T, mask_f, metric, label, B=B, seed=seed,
                                     folds_all=folds_all, weights=weights)
                    if r is None:
                        continue
                    full, listed = r.get("full"), r.get("listed")
                    s_max = max((full or listed)["seasons"][1], (listed or full)["seasons"][1])
                    population = ("listed" if family == "tools" else
                                  ("full" if (g == "all" or side == "pit") else "listed"))
                    rows.append({
                        "side": side, "level": lv, "age_band": band, "group": g,
                        "metric": metric, "family": family, "label": label, "frame": frame,
                        "population": population,
                        "n_full": full["n"] if full else None,
                        "players_full": full["players"] if full else None,
                        "pos_full": full["pos"] if full else None,
                        "seasons_full": full["seasons"] if full else None,
                        "raw_full": full["score"] if full else None,
                        "raw_full_ci95": full["ci95"] if full else None,
                        "n_listed": listed["n"] if listed else None,
                        "players_listed": listed["players"] if listed else None,
                        "pos_listed": listed["pos"] if listed else None,
                        "seasons_listed": listed["seasons"] if listed else None,
                        "raw_listed": listed["score"] if listed else None,
                        "consensus_raw": listed["consensus"] if listed else None,
                        "model_c": listed["model_c"] if listed else None,
                        "model_cm": listed["model_cm"] if listed else None,
                        "incr": listed["delta"] if listed else None,
                        "incr_ci95": listed["ci95"] if listed else None,
                        "incr_sd": listed["sd"] if listed else None,
                        "p": None if not listed else listed["p"],
                        "q": None,
                        "reserved_overlap": A.label_max_debut(label, s_max) >= F.R_VM_FIRST_DEBUT_YEAR,
                    })
            log(f"  {family} {side} {lv} {band} {g}: {int(mask.sum())} rows, {len(rows)} tests "
                f"so far ({time.time() - t0:.0f} s)")
    by_label: dict = {}
    for i, r in enumerate(rows):
        by_label.setdefault((r["family"], r["label"]), []).append(i)
    for idx in by_label.values():
        for i, q in zip(idx, A.bh_q([rows[i]["p"] for i in idx])):
            rows[i]["q"] = q
    return rows


# ---------------------------------------------------------------------------
# receipts: coverage and redundancy with consensus
# ---------------------------------------------------------------------------

def coverage(T: A.Table) -> dict:
    by_lv = {}
    for lv in A.LEVELS:
        m = T.level == lv
        if not m.any():
            continue
        by_lv[lv] = {"rows": int(m.sum()), "players": int(np.unique(T.pid[m]).size),
                     "listed": int(np.isfinite(T.fv[m]).sum()),
                     "seasons": [int(T.season[m].min()), int(T.season[m].max())]}
    per_metric = {}
    for mt in T.metrics:
        ok = np.isfinite(T.x[mt])
        seasons = T.season[ok]
        per_metric[mt] = {"rows": int(ok.sum()), "listed": int((ok & np.isfinite(T.fv)).sum()),
                          "seasons": ([int(seasons.min()), int(seasons.max())] if ok.any() else None)}
    groups = A.GROUPS[T.side]
    return {"rows": int(T.n), "players": int(np.unique(T.pid).size) if T.n else 0,
            "listed": int(np.isfinite(T.fv).sum()), "by_level": by_lv,
            "groups": {g: int((T.group == g).sum()) for g in groups if g != "all"},
            "bands": {b: int((T.band == b).sum()) for b in A.BANDS if b != "all"},
            "per_metric": per_metric}


def redundancy(T: A.Table) -> dict:
    """{metric: within-season Spearman of the metric against consensus FV on the listed
    rows (each row once), n}. A continuous association: no FV cell is formed."""
    out = {}
    for mt in T.metrics:
        m = np.isfinite(T.x[mt]) & np.isfinite(T.fv)
        if m.sum() < A.MIN_GROUP_ROWS:
            out[mt] = {"rho_with_consensus": None, "n": int(m.sum())}
            continue
        r = A.within_rho(T.x[mt][m], T.fv[m], T.season[m])
        out[mt] = {"rho_with_consensus": None if r is None else round(float(r), 4),
                   "n": int(m.sum())}
    return out


def top_cells(rows: list[dict], family: str, n: int = TOP_CELLS) -> dict:
    """The family's top cells by incremental lift: every frame, and the clean ones."""
    def pick(rs):
        rs = sorted(rs, key=lambda r: -r["incr"])[:n]
        return [{"metric": r["metric"], "side": r["side"], "level": r["level"],
                 "age_band": r["age_band"], "group": r["group"], "label": r["label"],
                 "frame": r["frame"], "incr": r["incr"], "ci95": r["incr_ci95"], "q": r["q"],
                 "n": r["n_listed"], "players": r["players_listed"],
                 "raw_listed": r["raw_listed"], "consensus_raw": r["consensus_raw"],
                 "passes_rule": A._is_candidate(r),
                 "status": "spent-overlap" if r["reserved_overlap"] else "clean"} for r in rs]
    fam = [r for r in rows if r["family"] == family and r.get("incr") is not None]
    return {"any": pick(fam), "clean": pick([r for r in fam if not r["reserved_overlap"]])}


RAW_LABELS = ("reach3", "reach_h")


def raw_by_level(rows: list[dict], family: str) -> dict:
    """The chart's view per (side, level, label): every metric's raw score in the
    level's all-ages, all-groups cell on the `all` frame, oriented above 0.5 for a
    reached label, beside consensus's raw score and the incremental lift on the
    listed rows. Descriptive: only the incremental score admits anything."""
    out: dict = {}
    for r in rows:
        if (r["family"] != family or r["age_band"] != "all" or r["group"] != "all"
                or r["frame"] != "all" or r["label"] not in RAW_LABELS):
            continue
        raw = r["raw_full"] if r["raw_full"] is not None else r["raw_listed"]
        ori, direction = A.oriented(raw)
        key = f"{r['side']}|{r['level']}|{r['label']}"
        out.setdefault(key, []).append({
            "metric": r["metric"], "raw": raw, "oriented": None if ori is None else round(ori, 4),
            "direction": direction, "population": "full" if r["raw_full"] is not None else "listed",
            "n": r["n_full"] if r["raw_full"] is not None else r["n_listed"],
            "raw_listed": r["raw_listed"], "consensus_raw": r["consensus_raw"],
            "incr": r["incr"], "q": r["q"],
            "status": "spent-overlap" if r["reserved_overlap"] else "clean"})
    for v in out.values():
        v.sort(key=lambda e: -(e["oriented"] or 0.0))
    return dict(sorted(out.items(), key=lambda kv: (kv[0].split("|")[0],
                                                     A.LEVEL_RANK.get(kv[0].split("|")[1], 99),
                                                     kv[0])))


def family_summary(rows: list[dict], family: str) -> dict:
    fam = [r for r in rows if r["family"] == family]
    inc = [r for r in fam if r.get("incr") is not None]
    qs = [r["q"] for r in inc if r.get("q") is not None]
    clean = [r for r in inc if not r["reserved_overlap"]]
    return {"tests": len(fam), "with_incremental": len(inc),
            "clean_with_incremental": len(clean),
            "passing_rule": sum(1 for r in inc if A._is_candidate(r)),
            "passing_rule_clean": sum(1 for r in clean if A._is_candidate(r)),
            "best_q": min(qs) if qs else None,
            "best_q_clean": min((r["q"] for r in clean if r.get("q") is not None), default=None),
            "positive_lift_share": (round(sum(1 for r in inc if r["incr"] > 0) / len(inc), 4)
                                    if inc else None),
            "median_lift": round(float(np.median([r["incr"] for r in inc])), 4) if inc else None}


# ---------------------------------------------------------------------------
# the artifact
# ---------------------------------------------------------------------------

CELL_COLUMNS = A.CELL_COLUMNS


def declared() -> dict:
    d = {k: v for k, v in A.declared().items()
         if k not in ("pbp_min", "bb_min", "woba_weights")}
    d.update({
        "families": list(FAMILIES),
        "bh": "Benjamini-Hochberg q within (family, label) of this module's two families",
        "tool_sources": list(TOOL_SOURCES),
        "tool_read": ("per source, the latest board dated inside the row's own V window "
                      "(V-01-01) and on or before the frame row's as-of date; no board from "
                      "another list vintage"),
        "tool_snapshot_cap": TOOL_SNAPSHOT_CAP,
        "tool_level": "the highest level with a qualified line in S (the level as of the list)",
        "track_levels": list(TRACK_LEVELS), "track_seasons": list(TRACK_SEASONS),
        "class_min": CLASS_MIN, "vaa": f"at y = {VAA_YF:.4f} ft from the release reference at y = {VAA_Y0:.0f} ft",
    })
    return d


def write_artifact(rows: list[dict], tables: dict, *, B: int, seconds: float,
                   path: Path = OUT_PATH, cells_path: Path = CELLS_PATH) -> tuple[Path, Path]:
    top_by_group, cands = A.summarise(rows)
    doc = {
        "schema": SCHEMA, "generated_at": A._now(), "tool": TOOL, "item": ITEM, "note": NOTE,
        "role": "development", "served": False, "spent_note": A.SPENT_NOTE,
        "companion": {"artifact": "data/efv5_metric_atlas.json", "tool": A.TOOL, "item": A.ITEM,
                      "note": "the first atlas; untouched here"},
        "declared": declared(), "bootstrap_b": B,
        "labels": {k: {kk: vv for kk, vv in v.items() if kk != "debut_lag"} for k, v in A.LABELS.items()},
        "metrics": {m: {"family": f, "side": s, "what": w} for m, (f, s, w) in METRICS.items()},
        "groups": {"hit": list(A.HIT_GROUPS), "pit": list(A.PIT_GROUPS), "labels": A.GROUP_LABEL,
                   "age_bands": list(A.BANDS)},
        "inputs": tables.get("_meta", {}),
        "coverage": {fam: {side: coverage(tables[fam][side]) for side in ("hit", "pit")}
                     for fam in FAMILIES},
        "redundancy_with_consensus": {fam: {side: redundancy(tables[fam][side]) for side in ("hit", "pit")}
                                      for fam in FAMILIES},
        "tests": len(rows),
        "tests_by_family": {fam: sum(1 for r in rows if r["family"] == fam) for fam in FAMILIES},
        "summary_by_family": {fam: family_summary(rows, fam) for fam in FAMILIES},
        "top_cells": {fam: top_cells(rows, fam) for fam in FAMILIES},
        "raw_by_level": {fam: raw_by_level(rows, fam) for fam in FAMILIES},
        "cells_with_incremental": sum(1 for r in rows if r.get("incr") is not None),
        "candidates": cands,
        "top_by_group": top_by_group,
        "cells_file": str(cells_path.relative_to(ROOT)).replace("\\", "/"),
        "seconds": round(seconds, 1),
    }
    cells = {"schema": SCHEMA, "generated_at": doc["generated_at"], "tool": TOOL, "item": ITEM,
             "note": NOTE, "columns": list(CELL_COLUMNS),
             "rows": [[r[c] for c in CELL_COLUMNS] for r in rows]}
    cells_path.parent.mkdir(parents=True, exist_ok=True)
    cells_path.write_text(json.dumps(cells, separators=(",", ":")), encoding="utf-8")
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return path, cells_path


# ---------------------------------------------------------------------------
# ATLAS_TOOLS.md
# ---------------------------------------------------------------------------

_fmt = A._fmt


def _cell_line(r: dict) -> str:
    return (f"| {r['metric']} | {r['side']} | {r['level']} | {r['age_band']} | "
            f"{A.GROUP_LABEL.get(r['group'], r['group'])} | {r['label']} | {r['frame']} | "
            f"{_fmt(r['incr'])} | {_fmt(r['ci95'])} | {_fmt(r['q'], 3)} | {r['n']} | "
            f"{_fmt(r['raw_listed'], 4)} | {_fmt(r['consensus_raw'], 4)} | "
            f"{'yes' if r['passes_rule'] else 'no'} | {r['status']} |")


_CELL_HEAD = ("| metric | side | level | age band | group | label | frame | lift | CI95 | q | n | "
              "raw (listed) | consensus raw | passes | status |\n"
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")


def atlas_md(doc: dict) -> str:
    L: list[str] = []
    d = doc["declared"]
    L.append("# eFV v5 metric atlas, part two: tool grades and Statcast components (EFV5_ATLAS_TOOLS_STATCAST)")
    L.append("")
    L.append(f"Generated {doc['generated_at']} by `{doc['tool']}` ({doc['seconds']} s, B {doc['bootstrap_b']}). "
             f"{doc['note']}. Tests: {doc['tests']} (tools {doc['tests_by_family']['tools']}, "
             f"statcast {doc['tests_by_family']['statcast']}); {doc['cells_with_incremental']} with an incremental score.")
    L.append("")
    L.append("## 1. Method (the first atlas's, unchanged)")
    L.append("")
    L.append(f"- minimum cell: {d['min_players']} players and {d['min_pos']} reachers (or non-zero WAR rows); "
             f"incremental: {d['incremental']}")
    L.append(f"- interval: {d['interval']}; {d['bh']}; candidate rule: {d['candidate_rule']}")
    L.append(f"- tool grades: {d['tool_read']}; sources {', '.join(d['tool_sources'])}; level: {d['tool_level']}")
    L.append(f"- Statcast: levels {', '.join(d['track_levels'])}, seasons {d['track_seasons'][0]} to {d['track_seasons'][-1]}; "
             f"class rates need {d['class_min']} pitches of the class; VAA {d['vaa']}")
    L.append(f"- {doc['spent_note']}")
    L.append("")
    for fam in FAMILIES:
        s = doc["summary_by_family"][fam]
        L.append(f"## {2 if fam == 'tools' else 3}. Family `{fam}`")
        L.append("")
        L.append(f"{s['tests']} tests, {s['with_incremental']} with an incremental score "
                 f"({s['clean_with_incremental']} on clean frames); {s['passing_rule']} pass the rule "
                 f"({s['passing_rule_clean']} clean); best q {_fmt(s['best_q'], 3)} (clean {_fmt(s['best_q_clean'], 3)}); "
                 f"share of positive lifts {_fmt(s['positive_lift_share'], 3)}, median lift {_fmt(s['median_lift'])}.")
        L.append("")
        for which, title in (("clean", "Top cells by incremental lift, clean frames"),
                             ("any", "Top cells by incremental lift, every frame (spent cells select nothing)")):
            L.append(f"### {title}")
            L.append("")
            rs = doc["top_cells"][fam][which]
            if not rs:
                L.append("None (no cell met the minimum).")
            else:
                L.append(_CELL_HEAD)
                for r in rs:
                    L.append(_cell_line(r))
            L.append("")
        L.append("### Raw scores per level (the chart's view; all ages, all groups, frame all)")
        L.append("")
        L.append("Oriented score: AUC read above 0.5 with the direction that gets there (reached labels). "
                 "Descriptive only: the lift column is what admits a driver.")
        L.append("")
        for key, ents in doc["raw_by_level"][fam].items():
            side, lv, label = key.split("|")
            L.append(f"#### {side} {lv}, label {label}")
            L.append("")
            L.append("| metric | oriented | direction | population | n | raw (listed) | consensus raw | lift | q | status |")
            L.append("|---|---|---|---|---|---|---|---|---|---|")
            for e in ents:
                L.append(f"| {e['metric']} | {_fmt(e['oriented'], 3)} | {e['direction'] or 'n/a'} | {e['population']} | "
                         f"{e['n']} | {_fmt(e['raw_listed'], 3)} | {_fmt(e['consensus_raw'], 3)} | {_fmt(e['incr'])} | "
                         f"{_fmt(e['q'], 3)} | {e['status']} |")
            L.append("")
        L.append("### Association with consensus FV (within-season Spearman, listed rows)")
        L.append("")
        L.append("| metric | what | hitters rho (n) | pitchers rho (n) |")
        L.append("|---|---|---|---|")
        red = doc["redundancy_with_consensus"][fam]
        for mt, info in doc["metrics"].items():
            if info["family"] != fam:
                continue
            side = info["side"]
            r = red[side].get(mt) or {}
            cell = f"{_fmt(r.get('rho_with_consensus'), 3)} ({r.get('n', 0)})"
            L.append(f"| {mt} | {info['what']} | {cell if side == 'hit' else ''} | {cell if side == 'pit' else ''} |")
        L.append("")
    L.append("## 4. Candidates (every cell passing the rule)")
    L.append("")
    if not doc["candidates"]:
        L.append("None. No cell cleared the rule.")
    else:
        L.append("| metric | family | side | level | age band | group | label | frame | lift | CI95 | q | n | players | status |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in doc["candidates"]:
            L.append(f"| {r['metric']} | {r['family']} | {r['side']} | {r['level']} | {r['age_band']} | {r['group']} | "
                     f"{r['label']} | {r['frame']} | {_fmt(r['incr'])} | {_fmt(r['ci95'])} | {_fmt(r['q'], 3)} | "
                     f"{r['n']} | {r['players']} | {r['status']} |")
    L.append("")
    L.append("## 5. Coverage")
    L.append("")
    for fam in FAMILIES:
        for side, c in doc["coverage"][fam].items():
            L.append(f"- {fam} {side}: {c['rows']} rows, {c['players']} players, {c['listed']} listed; groups "
                     + ", ".join(f"{k} {v}" for k, v in c["groups"].items()) + "; bands "
                     + ", ".join(f"{k} {v}" for k, v in c["bands"].items()))
            for lv, b in c["by_level"].items():
                L.append(f"  - {lv}: rows {b['rows']}, players {b['players']}, listed {b['listed']}, "
                         f"seasons {b['seasons'][0]}-{b['seasons'][1]}")
            L.append("  - per metric (rows / listed): " + "; ".join(
                f"{k} {v['rows']}/{v['listed']}" for k, v in c["per_metric"].items()))
    L.append("")
    return "\r\n".join(L) + "\r\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="coverage only; no label is scored")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--b", type=int, default=A.B_DEFAULT)
    ap.add_argument("--md", default=None, help="write ATLAS_TOOLS.md from the artifact to PATH")
    a = ap.parse_args(argv)
    if a.check or a.run:
        t0 = time.time()
        tables = build_tables()
        for fam in FAMILIES:
            for side in ("hit", "pit"):
                c = coverage(tables[fam][side])
                print(f"{fam} {side}: {c['rows']} rows, {c['players']} players; levels "
                      + ", ".join(f"{lv} {b['rows']}" for lv, b in c["by_level"].items()))
                print("   " + "; ".join(f"{k} {v['rows']}" for k, v in c["per_metric"].items()))
        if a.run:
            rows = []
            for fam in FAMILIES:
                rows.extend(run_family(tables, fam, B=a.b))
            p, c = write_artifact(rows, tables, B=a.b, seconds=time.time() - t0)
            print(f"wrote {p} and {c}: {len(rows)} tests in {time.time() - t0:.1f} s")
    if a.md:
        doc = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        Path(a.md).write_bytes(atlas_md(doc).encode("utf-8"))
        print(f"wrote {a.md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
