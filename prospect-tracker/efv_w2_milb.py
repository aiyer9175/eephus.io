# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV screening WAVE 2, MiLB performance-profile families (EFV3_W2_1b; owner EW2-6,
2026-10-08: "find more drivers so that it isn't just reliant on hit tool").

WHAT THIS BUILDS. Eight pre-declared candidate columns, each one level- and
age-relative MiLB rate, offered one at a time to the V2 SKILL head of its side through
the screening lab's machinery (tools/efv_screen_lab.py; efv_v2_model.fit_v2 extra=...)
and admitted or refused inside every fold by DS-06 exactly as wave 1's columns were:

    hitters   w2m_bb_hit    walk rate, BB / PA (separate from OBP, which V2 holds)
              w2m_k_hit     strikeout rate, SO / PA (separate; V2 holds only the merged
                            contact term)
              w2m_iso_hit   isolated power, (2B + 2 x 3B + 3 x HR) / AB
              w2m_hr_hit    home-run rate, HR / PA
              w2m_air_hit   air-out share, AO / (GO + AO): the fly-ball side of the
                            batted-ball profile (StatsAPI keeps ground and air outs only)
    pitchers  w2m_bb_pit    walk rate, BB / BF
              w2m_gb_pit    ground-out share, GO / (GO + AO)
              w2m_hr_pit    home-run rate, HR / BF

LEVEL AND AGE RELATIVE. Every (season, level) population of MiLB lines with at least
NORM_MIN exposure fits rate = a + b x age by least squares (the level-season's own
players, that season only: a contemporaneous norm, no outcome, no grade); a line's
value is its rate minus that fit at its own age. A level-season with fewer than
NORM_MIN_LINES qualifying lines borrows the prior season's fit at the same level; with
neither, the line gives no value. A line with no age takes the population mean age.

THE COLUMN. For a read at year V (a list vintage, or a vintage-matched decision year)
the walk goes from the last MiLB season that had ENDED by the read (the
efv_dataset._milb_features as-of rule, identical: season Y is readable only from
1 October of Y) down to the row's MiLB floor, keeps every line with at least
LINE_MIN exposure, and stops after MAX_SEASONS seasons that held one. The value is
the exposure-weighted mean of the lines' relative rates, shrunk by D / (D + K) on the
total denominator D read (K per statistic below, declared before any read; the
published stabilization points of each rate). A row with no qualifying line is None
and the lab imputes it at the fold's observed training mean, like every screening
column; no absence flag enters any head.

SOURCE. The MLB StatsAPI season lines (/api/v1/stats, stats=season, playerPool=ALL)
for sport ids 11 to 16, cached under .cache/milb_profile (one file per group, sport and
season; a past season is final). The served MiLB cache (.cache/milb_stats) drops
homeRuns for pitchers and groundOuts / airOuts for both sides, so this module keeps its
own lean copy and never writes the served cache. The person id is the row's
OUTCOME-BLIND id (`mlbam_id` on a list-vintage frame row; the matrix id on the
vintage-matched frame, as the base V2 reads it there).

COVERAGE NAMED, ABSENT DROPPED. Line-drive rate, pull rate and a true fly-ball rate
need batted-ball type and spray data. No dated MiLB source in this tree covers the
development vintages: the StatsAPI season line carries ground and air outs only, the
FanGraphs MiLB leaderboards were never pulled into any cache here (FanGraphs HTML
blocks scripted reads), prospects.db's MiLB tables (statlines, sabermetrics,
statcast_metrics, zone_metrics) hold the 2026 season only, and the minor-league
Statcast pulls (.cache/savant_minors, .cache/aaa_*) start in 2023. Those three
statistics are recorded in ABSENT and screened by nothing.

DEVELOPMENT READ ONLY (dev_read): lv_dev (list vintages 2017 to 2019, the lab's Frame)
and vm_dev (frame version vm2, the DS-16 rows) on the label the tree carries, within
delta of each column against the V2 base and against PROSPX consensus with E_cond CI95
per side. It adjudicates nothing and selects nothing; the artifact is
data/_labs/efv_w2/efv_w2_milb.json and the progress-ledger rows are role
"development".

BANS. No reserved frame is built or read: list vintages 2020 and 2021 raise through
efv_vintage_frame's guard, and the vm window stops before the 2025 debut cohort.
Nothing here groups, counts or averages anything by consensus-FV level
(docs/PROSPECT_ANCHOR_GATE.md): the only summaries are counts by (side, vintage) and
the level-season norms. No label, WAR or debut is read by any column builder.

Run:  python efv_w2_milb.py --warm            (fill .cache/milb_profile)
      python efv_w2_milb.py --dev-read        (the development read; writes the artifact)
      python efv_w2_milb.py --ledger          (this module's development ledger rows)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import efv_dataset as D
import efv_vintage_frame as F
import milb_history as mh

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache" / "milb_profile"
OUT_PATH = DATA_DIR / "_labs" / "efv_w2" / "efv_w2_milb.json"
TOOL = "efv_w2_milb.py"
WAVE = 2
MODEL_PREFIX = "efv_v2_screen:wave2:"

#: The seasons the cache holds: the lowest list-vintage MiLB floor (2005) through the
#: last season a vm_dev read can see (the 2023 decision year reads 2022).
SEASONS: tuple[int, ...] = tuple(range(2005, 2023))
SPORTS: tuple[int, ...] = tuple(mh.MINOR_SPORTS)
GROUPS = {"hit": "hitting", "pit": "pitching"}

#: Exposure floors: a line enters a level-season norm at NORM_MIN, a player's column
#: at LINE_MIN (the efv_dataset minpa convention: 50 PA, 60 BF).
NORM_MIN = {"hit": 100, "pit": 100}
NORM_MIN_LINES = 30
LINE_MIN = {"hit": 50, "pit": 60}
MAX_SEASONS = 3

#: Statistic -> (side, numerator, denominator, shrink K). Numerators and denominators
#: are names in _counts(). K is each rate's published stabilization point in its own
#: denominator (declared 2026-10-08 before any read; no K was tuned on any frame).
STATS: dict[str, dict] = {
    "bb_hit": {"side": "hit", "num": "bb", "den": "pa", "k": 120.0},
    "k_hit": {"side": "hit", "num": "so", "den": "pa", "k": 60.0},
    "iso_hit": {"side": "hit", "num": "xb", "den": "ab", "k": 160.0},
    "hr_hit": {"side": "hit", "num": "hr", "den": "pa", "k": 170.0},
    "air_hit": {"side": "hit", "num": "ao", "den": "bip", "k": 80.0},
    "bb_pit": {"side": "pit", "num": "bb", "den": "bf", "k": 170.0},
    "gb_pit": {"side": "pit", "num": "go", "den": "bip", "k": 70.0},
    "hr_pit": {"side": "pit", "num": "hr", "den": "bf", "k": 1000.0},
}
#: The arms, one per statistic, all offered to the skill head of their side.
ARMS: tuple[dict, ...] = tuple(
    {"name": f"w2m_{s}", "stat": s, "side": spec["side"], "head": "skill",
     "kind": "column", "retest": False,
     "column": {"source": "module", "module": "efv_w2_milb", "attr": "screen_column",
                "arg": s}}
    for s, spec in STATS.items())
#: Families the owner named that no dated MiLB source covers on the development
#: vintages (module docstring). Screened by nothing.
ABSENT: dict[str, str] = {
    "ld_rate": ("line-drive rate: no dated MiLB batted-ball-type source before 2023 in "
                "this tree (StatsAPI season lines keep ground and air outs only)"),
    "pull_rate": ("pull rate: no dated MiLB spray source before 2023 (FanGraphs MiLB "
                  "leaderboards never cached; minor-league Statcast starts 2023)"),
    "fb_rate_true": ("true fly-ball rate (fly balls over balls in play): absent; "
                     "w2m_air_hit reads the air-out share, which also holds line and "
                     "pop outs"),
    "prospects_db_milb": ("prospects.db statlines, sabermetrics, statcast_metrics and "
                          "zone_metrics hold season 2026 only"),
}

_BASE = mh.BASE
_UA = {"User-Agent": "Mozilla/5.0"}


# ---------------------------------------------------------------------------
# the cache: lean StatsAPI season lines
# ---------------------------------------------------------------------------

def _level(sport: int, league: str) -> str:
    return mh._level16(league) if int(sport) == 16 else mh.SPORT_LEVEL[int(sport)]


def _lean(split: dict, sport: int, season: int, group: str) -> dict:
    st = split.get("stat") or {}
    league = (split.get("league") or {}).get("name") or ""
    row = {"mlbam": (split.get("player") or {}).get("id"), "season": int(season),
           "sport": int(sport), "league": league, "level": _level(sport, league),
           "age": st.get("age"), "so": st.get("strikeOuts"), "bb": st.get("baseOnBalls"),
           "hr": st.get("homeRuns"), "go": st.get("groundOuts"), "ao": st.get("airOuts"),
           "hbp": st.get("hitByPitch")}
    if group == "hitting":
        row.update({"pa": st.get("plateAppearances"), "ab": st.get("atBats"),
                    "h": st.get("hits"), "doubles": st.get("doubles"),
                    "triples": st.get("triples")})
    else:
        row.update({"bf": st.get("battersFaced")})
    return row


def _cache_path(group: str, sport: int, season: int) -> Path:
    return CACHE_DIR / f"{group}_{int(sport)}_{int(season)}.json"


def fetch_season(sport: int, season: int, group: str, *, fetch: bool = True) -> list[dict]:
    """The lean lines of one (sport, season, group). A cached file is final (every
    season here has ended). fetch=False reads the cache only and returns [] without
    it."""
    path = _cache_path(group, sport, season)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["rows"]
    if not fetch:
        return []
    splits, offset, total = [], 0, None
    while True:
        url = (f"{_BASE}?stats=season&group={group}&season={int(season)}"
               f"&sportIds={int(sport)}&playerPool=ALL&limit=2000&offset={offset}")
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=90) as fh:
            d = json.loads(fh.read().decode("utf-8"))
        block = (d.get("stats") or [{}])[0]
        page = block.get("splits") or []
        splits.extend(page)
        total = block.get("totalSplits") or len(splits)
        offset += len(page)
        if not page or offset >= total:
            break
    rows = [_lean(s, sport, season, group) for s in splits]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    meta = {"sport": int(sport), "season": int(season), "group": group,
            "total_splits": total, "rows": len(rows),
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "statsapi.mlb.com/api/v1/stats stats=season playerPool=ALL"}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"meta": meta, "rows": rows}, separators=(",", ":")),
                   encoding="utf-8")
    tmp.replace(path)
    return rows


def warm_cache(seasons=SEASONS, *, workers: int = 6, log=print) -> dict:
    jobs = [(sp, se, g) for se in seasons for sp in SPORTS for g in GROUPS.values()]
    out = {"jobs": len(jobs), "rows": 0, "failed": []}

    def one(job):
        sp, se, g = job
        try:
            return job, len(fetch_season(sp, se, g)), None
        except Exception as exc:                              # noqa: BLE001
            return job, 0, str(exc)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for job, n, err in ex.map(one, jobs):
            out["rows"] += n
            if err:
                out["failed"].append({"job": list(job), "error": err})
                log(f"  failed {job}: {err}")
    return out


# ---------------------------------------------------------------------------
# lines, counts, level-season norms
# ---------------------------------------------------------------------------

def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _counts(row: dict, side: str) -> dict:
    """Additive counts of one lean line (None where the feed left a field out)."""
    c = {k: _f(row.get(k)) for k in ("so", "bb", "hr", "go", "ao")}
    if side == "hit":
        c["pa"], c["ab"] = _f(row.get("pa")), _f(row.get("ab"))
        d2, d3, hr = _f(row.get("doubles")), _f(row.get("triples")), c["hr"]
        c["xb"] = (d2 + 2.0 * d3 + 3.0 * hr) if None not in (d2, d3, hr) else None
    else:
        c["bf"] = _f(row.get("bf"))
    c["bip"] = (c["go"] + c["ao"]) if None not in (c["go"], c["ao"]) else None
    return c


@lru_cache(maxsize=None)
def season_lines(season: int, side: str) -> dict:
    """{mlbam: {level: {"counts": {...}, "age": float | None}}} for one season and
    side, summed over the lines a player has at one level (counts are additive)."""
    group = GROUPS[side]
    out: dict = {}
    for sp in SPORTS:
        for r in fetch_season(sp, season, group, fetch=False):
            pid = r.get("mlbam")
            lv = r.get("level")
            if not pid or lv not in mh._LEVEL_RANK or lv == "MLB":
                continue
            slot = out.setdefault(int(pid), {}).setdefault(lv, {"counts": {}, "age": None})
            for k, v in _counts(r, side).items():
                if v is None:
                    continue
                slot["counts"][k] = slot["counts"].get(k, 0.0) + v
            a = _f(r.get("age"))
            if a is not None and slot["age"] is None:
                slot["age"] = a
    return out


def exposure(counts: dict, side: str) -> float:
    return float(counts.get("pa" if side == "hit" else "bf") or 0.0)


def rate(counts: dict, stat: str) -> tuple[float | None, float]:
    spec = STATS[stat]
    num, den = counts.get(spec["num"]), counts.get(spec["den"])
    if num is None or not den:
        return None, 0.0
    return float(num) / float(den), float(den)


def _fit_line(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx) if sxx > 0 else 0.0
    return my - b * mx, b, mx


@lru_cache(maxsize=None)
def _norm_own(season: int, level: str, stat: str) -> dict | None:
    side = STATS[stat]["side"]
    xs, ys = [], []
    for lvls in season_lines(int(season), side).values():
        slot = lvls.get(level)
        if not slot or slot["age"] is None:
            continue
        if exposure(slot["counts"], side) < NORM_MIN[side]:
            continue
        r, _den = rate(slot["counts"], stat)
        if r is None:
            continue
        xs.append(float(slot["age"]))
        ys.append(r)
    if len(xs) < NORM_MIN_LINES:
        return None
    a, b, mean_age = _fit_line(xs, ys)
    return {"a": a, "b": b, "mean_age": mean_age, "n": len(xs), "season": int(season)}


def norm(season: int, level: str, stat: str) -> dict | None:
    """The level-season age line of `stat`, else the prior season's at the level."""
    return _norm_own(int(season), level, stat) or _norm_own(int(season) - 1, level, stat)


def relative(slot: dict, season: int, level: str, stat: str) -> tuple[float | None, float]:
    """(rate minus the level-season age line at the line's age, denominator)."""
    r, den = rate(slot["counts"], stat)
    if r is None:
        return None, 0.0
    nm = norm(season, level, stat)
    if nm is None:
        return None, 0.0
    age = slot["age"] if slot.get("age") is not None else nm["mean_age"]
    return r - (nm["a"] + nm["b"] * float(age)), den


# ---------------------------------------------------------------------------
# the as-of column
# ---------------------------------------------------------------------------

def last_readable_season(read_year: int, cutoff: str | None) -> int:
    """efv_dataset._milb_features' as-of rule, identical: read_year - 1, lowered when
    the cutoff falls before 1 October of a season (that season had not ended)."""
    first = int(read_year) - 1
    if cutoff:
        try:
            cy, cm = int(str(cutoff)[:4]), int(str(cutoff)[5:7])
            first = min(first, cy if cm >= 10 else cy - 1)
        except (ValueError, IndexError):
            pass
    return first


def profile(mlbam, read_year: int, cutoff: str | None, side: str, floor: int,
            stats=None) -> dict:
    """{stat: value | None} for one person read at `read_year` (as of `cutoff`), plus
    "_seasons": the seasons read. Only seasons from the floor up to the last readable
    one are walked; nothing after the read is touched."""
    stats = [s for s in (stats or STATS) if STATS[s]["side"] == side]
    out: dict = {s: None for s in stats}
    out["_seasons"] = []
    if not mlbam:
        return out
    pid = int(mlbam)
    top = last_readable_season(read_year, cutoff)
    acc = {s: [0.0, 0.0] for s in stats}
    used = 0
    for season in range(top, int(floor) - 1, -1):
        lvls = season_lines(season, side).get(pid) or {}
        lines = [(lv, slot) for lv, slot in lvls.items()
                 if exposure(slot["counts"], side) >= LINE_MIN[side]]
        if not lines:
            continue
        used += 1
        out["_seasons"].append(season)
        for lv, slot in lines:
            for s in stats:
                rel, den = relative(slot, season, lv, s)
                if rel is None or den <= 0:
                    continue
                acc[s][0] += rel * den
                acc[s][1] += den
        if used >= MAX_SEASONS:
            break
    for s in stats:
        num, den = acc[s]
        if den > 0:
            k = STATS[s]["k"]
            out[s] = (num / den) * (den / (den + k))
    return out


def lv_profiles(side: str, frames: dict, vintages=None) -> dict:
    """{(V, player_key): profile} on the list-vintage frame rows of the side. Each row
    reads on its outcome-blind id at its own window start and MiLB floor."""
    by_v = (frames.get(side) or {})
    out = {}
    for V in sorted(by_v):
        if vintages is not None and int(V) not in vintages:
            continue
        F.guard_score_request(int(V), purpose="w2 milb column")
        for r in by_v[V][0]:
            out[(int(V), r["player_key"])] = profile(
                r.get("mlbam_id"), int(V), (r.get("window") or [None])[0], side,
                int(r.get("milb_floor") or D.MILB_FLOOR_DEFAULT))
    return out


_LV_CACHE: dict = {}


def screen_column(stat: str, side: str, frames: dict) -> dict:
    """The screening lab's builder hook (column source "module", arg = statistic):
    {(V, player_key): value | None} on the side's list-vintage frame rows."""
    if STATS[stat]["side"] != side:
        raise ValueError(f"{stat} is a {STATS[stat]['side']} column, not {side}")
    key = (side, id(frames))
    if key not in _LV_CACHE:
        _LV_CACHE.clear()
        _LV_CACHE[key] = lv_profiles(side, frames)
    return {slot: p.get(stat) for slot, p in _LV_CACHE[key].items()}


def vm_profiles(side: str, data: list[dict], raw_by_key: dict) -> dict:
    """{player_key: profile} on the vintage-matched matrix rows: read at the row's
    decision year, as of its matrix cutoff, from the served default floor (the floor
    the matrices were built at)."""
    out = {}
    for d in data:
        raw = raw_by_key.get(d["player_key"]) or {}
        out[d["player_key"]] = profile(raw.get("mlbam_id"), int(d["decision_year"]),
                                       raw.get("cutoff"), side, D.MILB_FLOOR_DEFAULT)
    return out


def coverage(values: dict) -> dict:
    """{str(year): {"rows", "with_value"}} of a {(year, key): value} column."""
    out: dict = {}
    for (y, _k), v in values.items():
        c = out.setdefault(str(y), {"rows": 0, "with_value": 0})
        c["rows"] += 1
        c["with_value"] += int(v is not None)
    return dict(sorted(out.items()))


def norms_receipt() -> dict:
    """Counts of the level-season norms each statistic could fit (no rate value)."""
    out = {}
    for s in STATS:
        have, borrowed, none = 0, 0, 0
        for season in SEASONS:
            for lv in ("DSL", "CPX", "A", "A+", "AA", "AAA"):
                if _norm_own(season, lv, s):
                    have += 1
                elif norm(season, lv, s):
                    borrowed += 1
                else:
                    none += 1
        out[s] = {"own": have, "borrowed_prior_season": borrowed, "none": none}
    return out


def cache_receipt() -> dict:
    files = sorted(CACHE_DIR.glob("*.json")) if CACHE_DIR.exists() else []
    return {"dir": ".cache/milb_profile", "files": len(files),
            "expected": len(SEASONS) * len(SPORTS) * len(GROUPS),
            "seasons": [min(SEASONS), max(SEASONS)], "sports": list(SPORTS)}


# ---------------------------------------------------------------------------
# the development read (lv_dev through the screening lab's Frame; vm_dev at vm2)
# ---------------------------------------------------------------------------

NOTE = ("eFV screening wave 2 (EFV3_W2_1b MiLB profile), development read only: "
        "selects and adjudicates nothing")


def _tools():
    p = str(ROOT / "tools")
    if p not in sys.path:
        sys.path.insert(0, p)


def _cand(arm: dict) -> dict:
    """The arm in the screening lab's candidate shape."""
    out = {k: arm[k] for k in ("name", "side", "head", "kind", "retest", "column")}
    out["what"] = f"{arm['stat']}: level- and age-relative MiLB rate (efv_w2_milb)"
    return out


def lv_read(arms, *, B: int, log=print) -> dict:
    """Every arm on lv_dev (list vintages 2017 to 2019) through the lab's own Frame and
    measure_arm (refit inside every fold under DS-06, the zero-information twin, the
    DS-03 balance probe on the column's missingness) with its consensus leg. No floor
    and no permutation null: a development read forms no verdict."""
    _tools()
    import efv_screen_lab as LAB
    t0 = time.time()
    frame, frames = LAB.real_frame()
    log(f"lv_dev frame built in {time.time() - t0:.0f} s")
    base_vs_cons = {}
    for s in F.SIDES:
        order = {}
        for V in frame.folds:
            for pk, idx in frame.base(s, V)["order"].items():
                order[(V, pk)] = idx
        base_vs_cons[s] = LAB._vs_consensus(frame, (s,), order, B=B)
    out = {"frame": {"id": "lv_dev", "folds": list(frame.folds), "counts": frame.counts,
                     "w_star_dev": frame.w_star, "label": frame.label},
           "coverage": {}, "arms": {}}
    for s in F.SIDES:
        prof = lv_profiles(s, frames)
        out["coverage"][s] = {st: coverage({k: p.get(st) for k, p in prof.items()})
                              for st in STATS if STATS[st]["side"] == s}
    for arm in arms:
        t1 = time.time()
        values = screen_column(arm["stat"], arm["side"], frames)
        a = LAB.measure_arm(frame, _cand(arm), values, {}, B=B, n_perm=0,
                            base_vs_cons=base_vs_cons)
        a.pop("_order", None)
        a.pop("permutation_null", None)
        a["tag"] = f"SCREEN-W{WAVE}:{arm['side']}.skill.{arm['name']}"
        a["model_id"] = f"{MODEL_PREFIX}{arm['name']}:{arm['side']}"
        a["frame"]["note"] = NOTE
        out["arms"][arm["name"]] = a
        w = a["within"]
        vc = a["frame"]["deltas"]["candidate_vs_prospx_consensus"]["spearman"]
        log(f"  lv {arm['name']}: admitted {a['admitted_folds']}/{a['n_folds']}, within vs "
            f"V2 {w.get('delta')} {w.get('ci95')}, vs consensus {vc.get('delta')} "
            f"{vc.get('ci95')} ({time.time() - t1:.0f} s)")
    return out


def _vm_attach(rows: list[dict], key: str | None, values: dict) -> list[dict]:
    if key is None:
        return rows
    return [dict(r, v2=dict(r["v2"], **{key: values.get(r["player_key"])})) for r in rows]


def vm_orders(side: str, data: list[dict], weights: dict, years, *,
              key: str | None = None, values: dict | None = None) -> tuple[dict, dict]:
    """V2 on the vintage-matched frame exactly as efv_v2_model.v2_vm_scores(timing_pin=
    True) scores it, with one screening column attached to every row (train and the
    pinned test rows) and offered to the skill head when `key` is given.
    Returns ({player_key: order_idx}, {year: fold receipt})."""
    import efv_drivers as DRV
    import efv_v2_model as H
    mine: dict = {}
    pinned = H.pinned_inputs(side, data, mine)
    panel = DRV.load_bio_panel()
    vals = values or {}
    order, folds = {}, {}
    for yr in years:
        tr = [r for r in data if r["decision_year"] < yr]
        te = [r for r in data if r["decision_year"] == yr]
        if len(te) < H.MIN_TEST_ROWS or len(tr) < H.MIN_TRAIN_ROWS:
            continue
        te2 = []
        for r in te:
            pin = pinned.get(r["player_key"])
            if pin is None:
                continue
            extra = {"bmi": DRV.bmi_asof(r["player_key"],
                                         mine[r["player_key"]].get("asof_date"), panel)}
            te2.append(dict(r, feats=pin["feats"], fv=pin["fv"], extra=extra,
                            v2=H.v2_row(pin["feats"], extra)))
        tr_x, te_x = _vm_attach(tr, key, vals), _vm_attach(te2, key, vals)
        model = H.fit_v2(tr_x, side, frame="vm", weights=weights,
                         extra=({"skill": (key,)} if key else None))
        adm = ((((model.get("skill") or {}).get("admission") or {}).get(key) or {})
               if key else {})
        folds[str(yr)] = {"n_train": len(tr_x), "n_test": len(te_x),
                          "admitted": bool(adm.get("admitted")) if key else None,
                          "per_vintage_signs": adm.get("per_vintage_signs") if key else None,
                          "skill_keys": list((model.get("skill") or {}).get("keys") or []),
                          "consensus_only": model["consensus_only"]}
        for p in H.predict_v2(model, te_x):
            order[p["player_key"]] = p["order_idx"]
    return order, folds


def _vm_block(rows: list[dict], cand: dict, *, B: int) -> dict:
    """The vm_dev frame block of one arm on one side in the screening ledger shape:
    raters and the within / pooled / AUC deltas of the candidate against the V2 base
    and against consensus, paired on identical rows (E_cond, player-clustered)."""
    import efv_v2_stat as S
    import source_backtest as SB
    _tools()
    import efv_v2_dev_read as DR
    sel = [c for c in rows if cand.get(c["key"]) is not None]
    keys = [c["key"] for c in sel]
    groups = [c["group"] for c in sel]
    y = [c["outcome"]["war"] for c in sel]
    pos = [bool(c["outcome"]["contributor"]) for c in sel]
    a = [float(cand[c["key"]]) for c in sel]
    b = [float(c["grades"][DR.V2_KEY]) for c in sel]
    cons = [float(c["grades"][SB.CONSENSUS_KEY]) for c in sel]

    def legs(x, z):
        out = {}
        for stat, slot in (("within", "spearman"), ("pooled", "pooled"), ("auc", "auc")):
            d = S.paired_delta(keys, groups, y, pos, x, z, cons, statistic=stat, B=B)
            d["reading"] = S.reading(d.get("ci95"))
            out[slot] = d
        return out
    raters = {}
    for name, sc in (("efv_v2_candidate", a), ("efv_v2_base", b),
                     ("prospx_consensus", cons)):
        st = S.rater_stats(sc, y, pos, groups, cons)
        raters[name] = {"spearman": st["within"], "auc": st["auc"], "n": st["n"],
                        "within": st["within"], "pooled": st["pooled"],
                        "within_rows": st["within_rows"],
                        "within_groups": st["within_groups"]}
    for src in SB.SCORED_SOURCES:
        ix = [i for i, c in enumerate(sel) if c["grades"].get(src) is not None]
        if ix:
            st = S.rater_stats([sel[i]["grades"][src] for i in ix], [y[i] for i in ix],
                               [pos[i] for i in ix], [groups[i] for i in ix],
                               [cons[i] for i in ix])
            raters[src] = {"spearman": st["within"], "auc": st["auc"], "n": st["n"],
                           "within": st["within"], "pooled": st["pooled"]}
    deltas = {"candidate_vs_efv_v2_base": legs(a, b),
              "candidate_vs_prospx_consensus": legs(a, cons),
              "efv_v2_base_vs_prospx_consensus": legs(b, cons)}
    years = sorted({int(g.split("|")[1]) for g in groups})
    return {"frame_version": "vm2", "window": [min(years), max(years)] if years else None,
            "n": len(sel), "n_by_side": {sel[0]["side"]: len(sel)} if sel else {},
            "n_players": len(set(keys)), "groups": sorted(set(groups)),
            "statistic": S.STAT_LABEL[S.PRIMARY], "raters": raters, "deltas": deltas,
            "secondary": {"statistic": S.STAT_LABEL["pooled"],
                          "raters": {n: r.get("pooled") for n, r in raters.items()},
                          "deltas": {n: {"delta": (d.get("pooled") or {}).get("delta"),
                                         "ci95": (d.get("pooled") or {}).get("ci95"),
                                         "mde95": (d.get("pooled") or {}).get("mde95"),
                                         "reading": (d.get("pooled") or {}).get("reading")}
                                     for n, d in deltas.items()}},
            "verdict": None, "note": NOTE}


def vm_read(arms, *, B: int, log=print) -> dict:
    """Every arm on vm_dev at frame version vm2: the DS-16 rows
    (tools/efv_v2_dev_read.v2_vm_dev, the base V2 order on them), then per arm the
    same forward-chained V2 with the column offered to the skill head. The base is
    recomputed by vm_orders and must equal DS-16's on every row (parity)."""
    import efv_v2_model as H
    _tools()
    import efv_v2_dev_read as DR
    t0 = time.time()
    weights = H.load_weights()
    rows, meta = DR.v2_vm_dev(DATA_DIR, weights)
    years = meta["fold_years"]
    if any(int(y) >= F.R_VM_FIRST_DEBUT_YEAR for y in years):
        raise F.ReservedFrameError(f"vm years reach R-VM: {years}")
    log(f"vm_dev rows built in {time.time() - t0:.0f} s ({len(rows)} rows)")
    out = {"frame": {"id": "vm_dev", "frame_version": "vm2", "window": meta["window"],
                     "fold_years": years, "dropped": meta["dropped"],
                     "population_rows": meta["population_rows"]},
           "coverage": {}, "parity": {}, "arms": {}}
    key = f"{H.V2_SCREEN_PREFIX}cand"
    for s in F.SIDES:
        data = H.matrix_training_rows(s)
        raw = json.loads(H._matrix_path(s).read_text(encoding="utf-8"))
        raw_by_key = {r["player_key"]: r for r in raw}
        prof = vm_profiles(s, data, raw_by_key)
        side_rows = [c for c in rows if c["side"] == s]
        base, _f0 = vm_orders(s, data, weights, years)
        mism = sum(1 for c in side_rows
                   if base.get(c["key"]) is None
                   or abs(base[c["key"]] - float(c["grades"][DR.V2_KEY])) > 1e-9)
        out["parity"][s] = {"rows": len(side_rows), "mismatched_base_order": mism}
        if mism:
            raise RuntimeError(f"vm base parity failed on {s}: {mism} rows")
        scored = {c["key"] for c in side_rows}
        dy = {d["player_key"]: int(d["decision_year"]) for d in data}
        out["coverage"][s] = {}
        for st in STATS:
            if STATS[st]["side"] != s:
                continue
            out["coverage"][s][st] = {
                "train_rows": coverage({(dy[k], k): p.get(st) for k, p in prof.items()}),
                "scored_rows": coverage({(dy[k], k): p.get(st) for k, p in prof.items()
                                         if k in scored})}
        for arm in [a for a in arms if a["side"] == s]:
            t1 = time.time()
            vals = {k: p.get(arm["stat"]) for k, p in prof.items()}
            cand, folds = vm_orders(s, data, weights, years, key=key, values=vals)
            blk = _vm_block(side_rows, cand, B=B)
            out["arms"][arm["name"]] = {
                "name": arm["name"], "side": s, "head": "skill", "folds": folds,
                "admitted_folds": sum(1 for f in folds.values() if f["admitted"]),
                "n_folds": len(folds), "frame": blk}
            w = blk["deltas"]["candidate_vs_efv_v2_base"]["spearman"]
            vc = blk["deltas"]["candidate_vs_prospx_consensus"]["spearman"]
            log(f"  vm {arm['name']}: admitted "
                f"{out['arms'][arm['name']]['admitted_folds']}/{len(folds)}, within vs V2 "
                f"{w.get('delta')} {w.get('ci95')}, vs consensus {vc.get('delta')} "
                f"{vc.get('ci95')} ({time.time() - t1:.0f} s)")
    return out


def _git(*args) -> str | None:
    import subprocess
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _sha(path: Path) -> str | None:
    import hashlib
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def summary(doc: dict) -> list[dict]:
    """One line per arm and frame: rows, admitted folds, within delta vs V2 and vs
    consensus with CI95. Copies only."""
    out = []
    for arm in doc.get("arms_declared") or []:
        n = arm["name"]
        row = {"arm": n, "side": arm["side"], "stat": arm["stat"]}
        for fid in ("lv_dev", "vm_dev"):
            a = ((doc.get(fid) or {}).get("arms") or {}).get(n)
            if not a:
                continue
            d = a["frame"]["deltas"]
            v2 = d["candidate_vs_efv_v2_base"]["spearman"]
            vc = d["candidate_vs_prospx_consensus"]["spearman"]
            row[fid] = {"n": a["frame"]["n"],
                        "admitted_folds": f"{a['admitted_folds']}/{a['n_folds']}",
                        "vs_v2": [v2.get("delta"), v2.get("ci95")],
                        "vs_consensus": [vc.get("delta"), vc.get("ci95")]}
        out.append(row)
    return out


def ledger_docs(doc: dict) -> list[dict]:
    """One development document per (arm, frame) in the shape efv_progress.build_dev_rows
    reads (the screening lab's: model_id efv_v2_screen:wave2:<arm>:<side>, the frame
    block, a `screening` block naming the frame). Copies only."""
    out = []
    for arm in doc.get("arms_declared") or []:
        for fid in ("lv_dev", "vm_dev"):
            a = ((doc.get(fid) or {}).get("arms") or {}).get(arm["name"])
            if not a:
                continue
            out.append({"role": "development",
                        "model_id": f"{MODEL_PREFIX}{arm['name']}:{arm['side']}",
                        "generated_at": doc.get("generated_at"),
                        "label": doc.get("label") or {}, "code": doc.get("code") or {},
                        "screening": {"wave": f"{WAVE} ({fid})", "exploratory": False,
                                      "development_only": True, "adjudicates": False,
                                      "selects": False, "head": "skill",
                                      "statistic_column": arm["stat"],
                                      "admitted_folds": a["admitted_folds"],
                                      "n_folds": a["n_folds"]},
                        "frames": {fid: a["frame"]}})
    return out


def update_ledger(doc: dict | None = None, *, path: Path = OUT_PATH, ledger_path=None,
                  out_path=None, trigger: str = "efv_change") -> dict:
    """Append this module's development rows (and only them) to data/efv_progress.json
    through efv_progress.build_dev_rows and commit_rows. Idempotent: a row whose
    content is already its frame's last row for its model only moves
    last_verified_at."""
    import efv_progress as P
    doc = doc if doc is not None else json.loads(Path(path).read_text(encoding="utf-8"))
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


def dev_read(*, B: int | None = None, out: Path = OUT_PATH, log=print) -> dict:
    """The development read of every arm on lv_dev and vm_dev; writes the artifact."""
    import efv_labels as L
    import efv_v2_model as H
    import efv_v2_stat as S
    _tools()
    import efv_screen_lab as LAB
    B = S.B_DEFAULT if B is None else int(B)
    LAB.guards()
    t0 = time.time()
    doc = {"schema": 1,
           "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "produced_by": TOOL, "wave": WAVE, "role": "development",
           "adjudicates": False, "selects": False, "exploratory": False, "note": NOTE,
           "owner_decision": "EW2-6 (2026-10-08): select on development frames only",
           "label": {"provider": L.provider(), "resolved_through": L.resolved_through(),
                     "id": LAB.label_id()},
           "code": {"commit": _git("rev-parse", "--short=8", "HEAD"), "tool": TOOL,
                    "module_sha256": _sha(Path(__file__)),
                    "efv_v2_model_sha256": _sha(ROOT / "efv_v2_model.py")},
           "assembly_sha256": _sha(H.ASSEMBLY_PATH),
           "estimator": {"name": "E_cond", "B": B, "seed": S.SEED_DEFAULT,
                         "clusters": "player", "statistic": S.STAT_LABEL[S.PRIMARY]},
           "construction": {"stats": STATS, "norm_min": NORM_MIN,
                            "norm_min_lines": NORM_MIN_LINES, "line_min": LINE_MIN,
                            "max_seasons": MAX_SEASONS,
                            "norm": ("per (season, level) least-squares rate on age; "
                                     "the prior season's at the level when thin"),
                            "as_of": ("efv_dataset._milb_features rule (season Y "
                                      "readable from 1 October of Y)")},
           "source": cache_receipt(), "norms": norms_receipt(), "absent": ABSENT,
           "arms_declared": [{k: a[k] for k in ("name", "stat", "side", "head")}
                             for a in ARMS],
           "guards": {"reserved_lv": sorted(F.RESERVED_LV),
                      "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
                      "lv_folds": list(LAB.FOLDS), "anchor_gate_grouping": False}}
    doc["lv_dev"] = lv_read(ARMS, B=B, log=log)
    doc["vm_dev"] = vm_read(ARMS, B=B, log=log)
    doc["summary"] = summary(doc)
    doc["elapsed_s"] = round(time.time() - t0, 1)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8",
                   newline="\n")
    tmp.replace(out)
    log(f"wrote {out} in {doc['elapsed_s']} s")
    return doc


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--warm", action="store_true", help="fill .cache/milb_profile")
    ap.add_argument("--dev-read", action="store_true", help="the development read")
    ap.add_argument("--ledger", action="store_true",
                    help="append this module's development rows from the artifact")
    ap.add_argument("--ledger-path", default=None,
                    help="durable ledger path (default: efv_progress's own)")
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--B", type=int, default=None)
    a = ap.parse_args()
    if a.warm:
        t0 = time.time()
        print(json.dumps(warm_cache(), indent=1), f"{time.time() - t0:.1f} s")
    if a.dev_read:
        res = dev_read(B=a.B, out=Path(a.out))
        print(json.dumps(res["summary"], indent=1))
    if a.ledger:
        print(json.dumps(update_ledger(path=Path(a.out), ledger_path=a.ledger_path),
                         indent=1))
