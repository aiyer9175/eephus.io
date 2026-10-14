# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v5 metric atlas (EFV5_METRIC_ATLAS; owner 2026-10-14, decisions EW3-1 to
EW3-5, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`).

THE QUESTION. The owner shared a chart (Robert Stock, Single-A pitchers) that scores
each statistic by how often it ranks a player who reached MLB by 2026 above one who
did not (an AUC, 50 a coin flip), and asked for the same for every metric, level, age
band, role and position group, built into eFV drivers. THE DISTINCTION THAT DECIDES
EVERYTHING: a raw "reaches the majors" score is not what makes eFV better; eFV gains
only from information PROSPX consensus FV has not priced. So every (metric, group,
label) cell carries TWO scores:

    raw           the chart's score: AUC of the metric alone against a reached-MLB
                  label (pooled over the cell), or the size-weighted within-season
                  Spearman of the metric against a WAR label; read on the FULL MiLB
                  population of the cell and again on its LISTED rows (the rows with a
                  PROSPX consensus read)
    incremental   the lift from adding the metric to consensus FV, out of fold: for a
                  reached label, the AUC of a logistic model on [consensus FV, metric,
                  season] minus the AUC of the same model without the metric; for a
                  WAR label, the within-season Spearman of a ridge model on the same
                  columns (target: within-season percentile of the label) minus that
                  of the model without the metric. Five folds grouped by player,
                  fixed seed. ONLY the incremental score can admit a driver.

Every incremental cell carries a player-clustered bootstrap CI95 (scores fixed,
players resampled, B draws), a normal-approximation p from the bootstrap SD, and a
Benjamini-Hochberg q within its (family, label) family. The raw full-population score
carries the same bootstrap CI95.

ROWS. One row per (player, season S, level L, side): every MiLB season line of the
StatsAPI cache (.cache/milb_stats, 2005 to 2025, sport ids 11 to 16) with at least
QUAL exposure at that level and season (hitters PA, pitchers batters faced), for a
player with NO major-league line in any season at or before S. The row's metrics are
that level-season's, so every input is from a season finished before any label
season; the consensus FV is the PROSPX consensus read inside the V = S + 1 preseason
window (efv_vintage_frame, the F-LV frame row of the OUTCOME-BLIND id), so the grade
is the one the industry held after season S and before any label season.

GROUPS. side x level (DSL, CPX, A-, A, A+, AA, AAA) x age-for-level band (young,
average, old: terciles of age inside the level-season's qualified lines; plus "all")
x role (pitchers: SP or RP by the EFV3_C05 rule, games started over games below
RP_GS_SHARE is RP, read on the row's own season line; plus "all") or hitter position
group (C, SS, CF, other IF, corner OF, 1B/DH from the listing position dated inside
the V window, generic "OF" read as corner OF; plus "all"). Position groups exist only
on listed rows (the full population has no as-of position); a position cell reads its
listed rows for both scores and says so (`population`). Never a cell by FV level.

LABELS, each stated per cell with its resolution rule (H = the last season with MLB
lines and frozen fWAR on disk, 2026):
    reach3      reached MLB within 3 seasons after S (first MLB line in S+1..S+3);
                resolved when S + 3 <= H
    reach5      within 5 seasons; resolved when S + 5 <= H
    w3          fWAR over the first three MLB seasons for a reach3 player, 0 without a
                debut in the window; resolved when S + 5 <= H (SHORT, early WAR)
    l6          six-season fWAR from the debut for a reach3 player, 0 without;
                resolved when S + 8 <= H (LONG, the frozen label's horizon)
    reach_h     reached MLB by H (horizon-censored: a 2025 row has one season of
                exposure, a 2021 row five); the chart's own label
    war_rate_h  fWAR per MLB season through H for a reach_h player (sum over seasons
                with a MLB line, over their count), 0 without; horizon-censored
fWAR is the frozen vintage `data/fwar_vintage.json` (label fwar@..., the epoch's own
file), summed over hitting and pitching per (mlbam, season). MLB lines are the sport-1
season lines of the same cache, hitting or pitching.

RESERVED. List vintages 2020 and 2021 (R-LV) are never built: CONSENSUS_VINTAGES
leaves them out, so rows at S 2019 and 2020 carry no consensus (raw scores only), and
efv_vintage_frame's guard would raise if they were asked. A cell whose label window
reaches a debut cohort of 2025 or later (R-VM, spent since the 10-08 confirmation)
is flagged `reserved_overlap` and labelled SPENT_NOTE: the owner authorised these
short-horizon, consensus-scored reads for the tracking era (EW3-1) and they select
nothing. Because a cell pooled over every season always holds its latest rows, the
reach3 and reach5 labels are read on TWO frames: `all` (every resolved row, flagged
where the window reaches 2025) and `clean` (rows whose window closes before the 2025
cohort: reach3 at S <= 2021, reach5 at S <= 2019). w3 and l6 are clean by their
resolution rule; reach_h and war_rate_h have no clean frame. The candidates list keeps
clean cells apart from spent-overlap cells.

MINIMUM CELL, declared before any read: MIN_PLAYERS distinct players and MIN_POS
reached players (a binary label) or MIN_POS rows with a non-zero label (a WAR label),
on the population the score is read on.

FAMILIES. box (season lines 2005+: rates, their level-and-age-relative versions, age,
age for level), pbp (pitch calls, .cache/efv4_pbp_discipline: AAA 2007+, AA 2008+,
A+ 2013+, A 2015+, through 2024), bb (batted-ball trajectory and spray,
.cache/efv4_pbp_bb/agg, same eras), tracking (Savant minors pitch tracking,
EFV5_TRACKING_FETCH tables: AAA 2022+, Florida State League Single-A 2021+). The
profile counts (ground and air outs, pitcher home runs) come from .cache/milb_profile
(2005 to 2022) extended by this module's own cache .cache/efv5_profile (2023 to 2025,
the same lean StatsAPI line, fetched politely and never between 06:00 and 11:00 UTC).

BANS. No served number moves and nothing served imports this module. Nothing here
groups, counts or averages anything by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md);
consensus FV enters only as a covariate. No projections retrain, no backtest module call,
no fetch outside .cache/efv5_profile. The artifact is development only.

Run:  python efv5_atlas.py --warm-profile        (fill .cache/efv5_profile, 2023 to 2025)
      python efv5_atlas.py --chart               (the owner's chart, replicated, printed)
      python efv5_atlas.py --run [--b 400]       (the atlas; writes the artifact)
      python efv5_atlas.py --md PATH             (ATLAS.md from the artifact)
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import sqlite3
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import efv_vintage_frame as F
import milb_history as mh
import source_backtest as SB

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "efv5_metric_atlas.json"
CELLS_PATH = DATA_DIR / "_labs" / "efv5" / "efv5_metric_atlas_cells.json"
PROFILE_DIR = ROOT / ".cache" / "efv5_profile"
MILB_PROFILE_DIR = ROOT / ".cache" / "milb_profile"
PBP_AGG_DIR = ROOT / ".cache" / "efv4_pbp_discipline"
BB_AGG_DIR = ROOT / ".cache" / "efv4_pbp_bb" / "agg"
TRACK_DIR = ROOT / ".cache" / "efv5_savant_minors" / "tables"
DB_PATH = ROOT / "prospects.db"
TOOL = "efv5_atlas.py"
ITEM = "EFV5_METRIC_ATLAS"
SCHEMA = 1
NOTE = ("eFV v5 metric atlas, development read (EW3-1 to EW3-3): nothing served moves, "
        "no cell by consensus-FV level, consensus FV a covariate only")
SPENT_NOTE = ("spent: the label window reaches a 2025+ debut cohort (R-VM, spent since "
              "the 10-08 confirmation); an owner-authorised short-horizon read (EW3-1) "
              "that selects nothing")

#: Declared before any read.
SEASONS: tuple[int, ...] = tuple(y for y in range(2005, 2026) if y != 2020)
HORIZON = 2026
LEVELS: tuple[str, ...] = ("DSL", "CPX", "A-", "A", "A+", "AA", "AAA")
LEVEL_RANK = {lv: i for i, lv in enumerate(LEVELS)}
QUAL = {"hit": 100.0, "pit": 100.0}          # PA, batters faced, per level-season line
MIN_PLAYERS = 150
MIN_POS = 30
MIN_GROUP_ROWS = 20                           # a season enters the within statistic
NORM_MIN_LINES = 30                           # lines for a level-season age line
FOLDS = 5
SEED = 20261014
B_DEFAULT = 400
RIDGE = 1.0                                   # on standardised columns, both heads
NEWTON_ITERS = 12
RP_GS_SHARE = 0.5                             # the EFV3_C05 rule
BANDS = ("all", "young", "average", "old")
HIT_GROUPS = ("all", "C", "SS", "CF", "IF", "COF", "1B/DH")
PIT_GROUPS = ("all", "SP", "RP")
GROUPS = {"hit": HIT_GROUPS, "pit": PIT_GROUPS}
#: Listing position token (before "/") -> hitter group; "OF" reads as corner OF.
POS_GROUP = {"C": "C", "SS": "SS", "CF": "CF", "2B": "IF", "3B": "IF", "IF": "IF",
             "INF": "IF", "UTIL": "IF", "UT": "IF", "MI": "IF", "CI": "IF",
             "LF": "COF", "RF": "COF", "OF": "COF", "1B": "1B/DH", "DH": "1B/DH"}
GROUP_LABEL = {"all": "all", "C": "catchers", "SS": "shortstops", "CF": "center fielders",
               "IF": "other infielders (2B, 3B, IF)", "COF": "corner outfielders (LF, RF, OF)",
               "1B/DH": "first basemen and DHs", "SP": "starters", "RP": "relievers"}
#: Consensus reads: the development vintages and the post-reserved vintages. 2020 and
#: 2021 (R-LV) are never built here.
CONSENSUS_VINTAGES: tuple[int, ...] = tuple(range(2011, 2020)) + tuple(range(2022, 2027))
LISTING_SOURCES = ("mlb_pipeline", "fangraphs", "baseballamerica", "espn", "just_baseball",
                   "mlb_pipeline_international")
SPORT_LEVEL = {11: "AAA", 12: "AA", 13: "A+", 14: "A", 15: "A-", 16: "CPX"}
PBP_MIN = {"hit": 100.0, "pit": 100.0}        # PA / BF in full games
BB_MIN = 50.0                                 # balls in play
TRACK_MIN = {"hit": 50.0, "pit": 100.0}       # PA / pitches (the fetch's rule)
#: The candidates rule, declared: incremental lift above 0 with the CI95 lower bound
#: above 0 and q at or below this.
CANDIDATE_Q = 0.10
WOBA_W = {"bb": 0.69, "hbp": 0.72, "1b": 0.88, "2b": 1.25, "3b": 1.59, "hr": 2.05}
_UA = {"User-Agent": "Mozilla/5.0"}
BLACKOUT_UTC = (6, 11)

LABELS: dict[str, dict] = {
    "reach3": {"kind": "binary", "horizon": "short", "what": "reached MLB within 3 seasons after S",
               "resolved": "S + 3 <= H", "max_s": HORIZON - 3, "debut_lag": 3,
               "clean_max_s": F.R_VM_FIRST_DEBUT_YEAR - 1 - 3},
    "reach5": {"kind": "binary", "horizon": "short", "what": "reached MLB within 5 seasons after S",
               "resolved": "S + 5 <= H", "max_s": HORIZON - 5, "debut_lag": 5,
               "clean_max_s": F.R_VM_FIRST_DEBUT_YEAR - 1 - 5},
    "w3": {"kind": "rank", "horizon": "short",
           "what": "fWAR over the first three MLB seasons, debut within 3 seasons of S, 0 without",
           "resolved": "S + 5 <= H", "max_s": HORIZON - 5, "debut_lag": 3},
    "l6": {"kind": "rank", "horizon": "long",
           "what": "six-season fWAR from the debut, debut within 3 seasons of S, 0 without",
           "resolved": "S + 8 <= H", "max_s": HORIZON - 8, "debut_lag": 3},
    "reach_h": {"kind": "binary", "horizon": "censored",
                "what": f"reached MLB by {HORIZON} (horizon-censored)",
                "resolved": "S <= H - 1", "max_s": HORIZON - 1, "debut_lag": None},
    "war_rate_h": {"kind": "rank", "horizon": "censored",
                   "what": f"fWAR per MLB season through {HORIZON}, 0 without a MLB line (horizon-censored)",
                   "resolved": "S <= H - 1", "max_s": HORIZON - 1, "debut_lag": None},
}

#: Metric -> (family, side, what). Direction is free: the artifact reports the AUC of
#: the metric as defined and its oriented value with the sign that reads above 0.5.
METRICS: dict[str, tuple[str, str, str]] = {}


def _m(name, family, side, what):
    METRICS[name] = (family, side, what)


for _s in ("hit", "pit"):
    _m(f"age_{_s}", "box", _s, "age in the season")
    _m(f"age_rel_level_{_s}", "box", _s, "age minus the level-season mean age of qualified lines")
_HIT_BOX = {
    "k_pct": "strikeouts / PA", "bb_pct": "walks / PA", "bb_minus_k": "(walks - strikeouts) / PA",
    "hr_pct": "home runs / PA", "iso": "isolated power", "avg": "batting average",
    "obp": "on-base percentage", "slg": "slugging", "ops": "OPS",
    "babip": "batting average on balls in play", "woba": "wOBA (fixed linear weights)",
    "sb_rate": "stolen bases / PA", "gb_pct": "ground outs / (ground + air outs)",
}
_PIT_BOX = {
    "k_pct": "strikeouts / BF", "bb_pct": "walks / BF", "k_minus_bb": "(strikeouts - walks) / BF",
    "hr_pct": "home runs / BF", "gb_pct": "ground outs / (ground + air outs)",
    "era": "earned run average", "bf_per_g": "batters faced per game",
    "gs_share": "games started / games",
}
for _k, _w in _HIT_BOX.items():
    _m(f"{_k}_hit", "box", "hit", _w)
    _m(f"{_k}_rel_hit", "box", "hit", _w + ", minus the level-season age line")
for _k, _w in _PIT_BOX.items():
    _m(f"{_k}_pit", "box", "pit", _w)
    _m(f"{_k}_rel_pit", "box", "pit", _w + ", minus the level-season age line")
_HIT_PBP = {"swstr": "whiffs / pitches", "contact": "contact / swings",
            "swing": "swings / pitches", "two_strike_contact": "contact / swings at two strikes",
            "fstrike_taken": "first-pitch called strikes / PA",
            "k_resid": "z(K rate) minus the pool slope times z(whiff rate)"}
_PIT_PBP = {"swstr": "whiffs / pitches", "cstr": "called strikes / pitches",
            "csw": "(called strikes + whiffs) / pitches", "fstrike": "first-pitch strikes / BF",
            "ball_rate": "balls / pitches",
            "k_resid": "z(K rate) minus the pool slope times z(whiff rate)"}
for _k, _w in _HIT_PBP.items():
    _m(f"pbp_{_k}_hit", "pbp", "hit", _w)
for _k, _w in _PIT_PBP.items():
    _m(f"pbp_{_k}_pit", "pbp", "pit", _w)
_HIT_BB = {"gb": "ground balls / balls in play", "ld": "line drives / balls in play",
           "fb": "fly balls / balls in play", "pu": "popups / balls in play",
           "hard": "hard-graded balls in play / balls in play",
           "pull": "pull-side balls in play / balls in play with a side",
           "oppo_hard": "hard opposite-side balls in play / opposite-side balls in play"}
_PIT_BB = {"gb": "ground balls / balls in play against", "ld": "line drives / balls in play against",
           "fb": "fly balls / balls in play against", "pu": "popups / balls in play against"}
for _k, _w in _HIT_BB.items():
    _m(f"bb_{_k}_hit", "bb", "hit", _w)
for _k, _w in _PIT_BB.items():
    _m(f"bb_{_k}_pit", "bb", "pit", _w)
_PIT_TRACK = {
    "fb_velo_mean": "fastball velocity, mean", "fb_velo_p95": "fastball velocity, 95th pct (top end)",
    "fb_ivb": "primary fastball induced vertical break (ride)",
    "fb_hb_arm": "primary fastball arm-side run", "extension": "release extension",
    "arm_angle": "arm angle", "csw": "CSW", "swstr": "whiffs / pitches", "whiff": "whiffs / swings",
    "zone": "zone rate", "chase": "chase rate induced", "zone_contact": "zone contact allowed",
    "k_pct": "K / PA (tracked)", "bb_pct": "BB / PA (tracked)", "k_minus_bb": "K-BB% (tracked)",
    "xwoba_against": "xwOBA against", "ev_against": "exit velocity against, mean",
    "gb": "ground-ball share of balls in play", "whiff_fb": "fastball whiff rate",
    "whiff_br": "breaking-ball whiff rate", "whiff_os": "offspeed whiff rate",
    "astuff_plus": "aStuff+ (stuff_plus_aaa v1, applied)", "astuff_plus_fb": "aStuff+ fastballs",
    "astuff_plus_br": "aStuff+ breaking balls", "astuff_plus_os": "aStuff+ offspeed",
}
_HIT_TRACK = {
    "ev_mean": "exit velocity, mean", "ev_p90": "exit velocity, 90th pct", "ev_max": "max exit velocity",
    "hard_hit": "hard-hit rate", "barrel": "barrel rate", "la_sd": "launch angle sd",
    "sweet_spot": "sweet-spot rate", "chase": "chase rate", "zone_contact": "zone contact",
    "whiff": "whiffs / swings", "swstr": "whiffs / pitches", "xwoba": "xwOBA",
    "k_pct": "K / PA (tracked)", "bb_pct": "BB / PA (tracked)",
}
for _k, _w in _PIT_TRACK.items():
    _m(f"trk_{_k}_pit", "tracking", "pit", _w)
for _k, _w in _HIT_TRACK.items():
    _m(f"trk_{_k}_hit", "tracking", "hit", _w)
FAMILIES = ("box", "pbp", "bb", "tracking")

#: The owner's chart (Robert Stock, Single-A pitchers, reached MLB by 2026): label ->
#: (our metric, orientation: +1 higher is the chart's direction, -1 lower).
CHART: tuple[tuple[str, str | None, int, int], ...] = (
    ("Pitching+", None, 1, 75), ("K-BB%", "trk_k_minus_bb_pit", 1, 72),
    ("Top-end fastball velo", "trk_fb_velo_p95_pit", 1, 72), ("Stuff+", "trk_astuff_plus_pit", 1, 69),
    ("xwOBA against", "trk_xwoba_against_pit", -1, 68), ("K%", "trk_k_pct_pit", 1, 68),
    ("CSW%", "trk_csw_pit", 1, 68), ("Location+", None, 1, 65), ("BB% (low)", "trk_bb_pct_pit", -1, 64),
    ("Age (young)", "age_pit", -1, 58), ("Fastball ride", "trk_fb_ivb_pit", 1, 56),
    ("Exit velo against", "trk_ev_against_pit", -1, 56), ("Ground-ball %", "trk_gb_pit", 1, 54),
    ("Breaking-ball whiff %", "trk_whiff_br_pit", 1, 53), ("Arm angle", "trk_arm_angle_pit", 1, 49),
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def in_blackout(now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return BLACKOUT_UTC[0] <= now.hour < BLACKOUT_UTC[1]


# ---------------------------------------------------------------------------
# the profile extension (this module's own cache)
# ---------------------------------------------------------------------------

def _lean_profile(split: dict, sport: int, season: int, group: str) -> dict:
    """efv_w2_milb._lean, the same lean line."""
    st = split.get("stat") or {}
    league = (split.get("league") or {}).get("name") or ""
    level = mh._level16(league) if int(sport) == 16 else mh.SPORT_LEVEL[int(sport)]
    row = {"mlbam": (split.get("player") or {}).get("id"), "season": int(season),
           "sport": int(sport), "league": league, "level": level,
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


def profile_path(group: str, sport: int, season: int) -> Path:
    """The lean profile file: milb_profile's own for its seasons, else this cache."""
    p = MILB_PROFILE_DIR / f"{group}_{int(sport)}_{int(season)}.json"
    if p.exists():
        return p
    return PROFILE_DIR / f"{group}_{int(sport)}_{int(season)}.json"


def profile_rows(group: str, sport: int, season: int) -> list[dict]:
    p = profile_path(group, sport, season)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))["rows"]


def fetch_profile(sport: int, season: int, group: str, *, opener=None) -> int:
    """One (sport, season, group) into PROFILE_DIR when no file holds it. Polite:
    sequential pages, refused in the nightly window."""
    if profile_path(group, sport, season).exists():
        return 0
    if in_blackout():
        raise RuntimeError("no fetch between 06:00 and 11:00 UTC")
    opener = opener or (lambda url: urllib.request.urlopen(
        urllib.request.Request(url, headers=_UA), timeout=90).read())
    splits, offset = [], 0
    while True:
        url = (f"{mh.BASE}?stats=season&group={group}&season={int(season)}"
               f"&sportIds={int(sport)}&playerPool=ALL&limit=2000&offset={offset}")
        d = json.loads(opener(url).decode("utf-8"))
        block = (d.get("stats") or [{}])[0]
        page = block.get("splits") or []
        splits.extend(page)
        total = block.get("totalSplits") or len(splits)
        offset += len(page)
        if not page or offset >= total:
            break
        time.sleep(0.5)
    rows = [_lean_profile(s, sport, season, group) for s in splits]
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    meta = {"sport": int(sport), "season": int(season), "group": group, "rows": len(rows),
            "fetched_at": _now(), "tool": TOOL,
            "source": "statsapi.mlb.com/api/v1/stats stats=season playerPool=ALL"}
    path = PROFILE_DIR / f"{group}_{int(sport)}_{int(season)}.json"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"meta": meta, "rows": rows}, separators=(",", ":")),
                   encoding="utf-8")
    tmp.replace(path)
    return len(rows)


def warm_profile(seasons=(2023, 2024, 2025), *, workers: int = 4, log=print) -> dict:
    jobs = [(sp, se, g) for se in seasons for sp in SPORT_LEVEL for g in ("hitting", "pitching")]
    out = {"jobs": len(jobs), "rows": 0, "failed": []}

    def one(job):
        sp, se, g = job
        try:
            return job, fetch_profile(sp, se, g), None
        except Exception as exc:                                    # noqa: BLE001
            return job, 0, str(exc)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for job, n, err in ex.map(one, jobs):
            out["rows"] += n
            if err:
                out["failed"].append({"job": list(job), "error": err})
            log(f"  {job}: {n} rows{(' ' + err) if err else ''}")
    return out


# ---------------------------------------------------------------------------
# the population: box-score lines per (player, season, level)
# ---------------------------------------------------------------------------

def _ip_outs(ip) -> float | None:
    x = _f(ip)
    if x is None:
        return None
    whole = math.floor(x)
    frac = round((x - whole) * 10)
    return whole * 3.0 + float(frac)


def box_lines(side: str, seasons=SEASONS) -> dict:
    """{(mlbam, season, level): counts} summed over stints, from the season-line cache
    (milb_stats) plus the profile counts (ground and air outs, pitcher home runs and
    hit by pitch)."""
    group = "hitting" if side == "hit" else "pitching"
    keys = (("pa", "ab", "h", "doubles", "triples", "hr", "so", "bb", "ibb", "hbp", "sf", "sb")
            if side == "hit" else ("bf", "so", "bb", "g", "gs"))
    out: dict = {}
    for season in seasons:
        for sport in SPORT_LEVEL:
            for r in mh.season_splits(sport, season, group, fetch=False):
                pid, lv = r.get("mlbam"), r.get("level")
                if not pid or lv not in LEVEL_RANK:
                    continue
                slot = out.setdefault((int(pid), int(season), lv), {"age": None, "outs": 0.0})
                for k in keys:
                    v = _f(r.get(k))
                    if v is not None:
                        slot[k] = slot.get(k, 0.0) + v
                if side == "pit":
                    o = _ip_outs(r.get("ip"))
                    if o is not None:
                        slot["outs"] += o
                    er = _f(r.get("era"))
                    if er is not None and o:
                        slot["er"] = slot.get("er", 0.0) + er * o / 27.0
                a = _f(r.get("age"))
                if a is not None and slot["age"] is None:
                    slot["age"] = a
            for r in profile_rows(group, sport, season):
                pid, lv = r.get("mlbam"), r.get("level")
                if not pid or lv not in LEVEL_RANK:
                    continue
                slot = out.get((int(pid), int(season), lv))
                if slot is None:
                    continue
                for k in ("go", "ao") + (("hr", "hbp") if side == "pit" else ()):
                    v = _f(r.get(k))
                    if v is not None:
                        slot[k] = slot.get(k, 0.0) + v
    return out


def hit_rates(c: dict) -> dict:
    pa, ab = c.get("pa") or 0.0, c.get("ab") or 0.0
    h, d2, d3, hr = c.get("h", 0.0), c.get("doubles", 0.0), c.get("triples", 0.0), c.get("hr", 0.0)
    so, bb, hbp, sf = c.get("so", 0.0), c.get("bb", 0.0), c.get("hbp", 0.0), c.get("sf", 0.0)
    ibb = c.get("ibb", 0.0)
    out = {"k_pct": so / pa if pa else None, "bb_pct": bb / pa if pa else None,
           "bb_minus_k": (bb - so) / pa if pa else None, "hr_pct": hr / pa if pa else None,
           "sb_rate": c.get("sb", 0.0) / pa if pa else None}
    out["iso"] = (d2 + 2 * d3 + 3 * hr) / ab if ab else None
    out["avg"] = h / ab if ab else None
    obp_den = ab + bb + hbp + sf
    out["obp"] = (h + bb + hbp) / obp_den if obp_den else None
    out["slg"] = (h + d2 + 2 * d3 + 3 * hr) / ab if ab else None
    out["ops"] = (out["obp"] + out["slg"]) if None not in (out["obp"], out["slg"]) else None
    bden = ab - so - hr + sf
    out["babip"] = (h - hr) / bden if bden > 0 else None
    wden = ab + bb - ibb + sf + hbp
    singles = h - d2 - d3 - hr
    out["woba"] = ((WOBA_W["bb"] * (bb - ibb) + WOBA_W["hbp"] * hbp + WOBA_W["1b"] * singles
                    + WOBA_W["2b"] * d2 + WOBA_W["3b"] * d3 + WOBA_W["hr"] * hr) / wden
                   if wden > 0 else None)
    go, ao = c.get("go"), c.get("ao")
    out["gb_pct"] = go / (go + ao) if go is not None and ao is not None and (go + ao) > 0 else None
    return out


def pit_rates(c: dict) -> dict:
    bf = c.get("bf") or 0.0
    so, bb, g, gs = c.get("so", 0.0), c.get("bb", 0.0), c.get("g", 0.0), c.get("gs", 0.0)
    out = {"k_pct": so / bf if bf else None, "bb_pct": bb / bf if bf else None,
           "k_minus_bb": (so - bb) / bf if bf else None}
    hr = c.get("hr")
    out["hr_pct"] = hr / bf if hr is not None and bf else None
    go, ao = c.get("go"), c.get("ao")
    out["gb_pct"] = go / (go + ao) if go is not None and ao is not None and (go + ao) > 0 else None
    outs = c.get("outs") or 0.0
    out["era"] = (c.get("er", 0.0) * 27.0 / outs) if outs > 0 and "er" in c else None
    out["bf_per_g"] = bf / g if g else None
    out["gs_share"] = gs / g if g else None
    return out


# ---------------------------------------------------------------------------
# pitch calls, batted balls, tracking
# ---------------------------------------------------------------------------

def _read_gz_json(path: Path):
    with gzip.open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def pbp_metrics(side: str) -> dict:
    """{(mlbam, season, level): {metric: value}} from the pitch-call aggregates, lines
    with at least PBP_MIN exposure in full games; k_resid inside each pool."""
    out: dict = {}
    for p in sorted(PBP_AGG_DIR.glob("*.v1.json.gz")):
        d = _read_gz_json(p)
        sport, season = int(d["sport"]), int(d["season"])
        lv = SPORT_LEVEL.get(sport)
        if lv is None:
            continue
        cols = d[f"{side}_cols"]
        lines = {}
        for k, v in d[side].items():
            c = dict(zip(cols, v))
            exp = c["pa"] if side == "hit" else c["bf"]
            if exp < PBP_MIN[side] or c["pitches"] <= 0:
                continue
            if side == "hit":
                swings, two = c["swings"], c["two_swings"]
                r = {"swstr": c["whiffs"] / c["pitches"],
                     "contact": (swings - c["whiffs"]) / swings if swings else None,
                     "swing": swings / c["pitches"],
                     "two_strike_contact": (two - c["two_whiffs"]) / two if two else None,
                     "fstrike_taken": c["fp_called"] / c["fp_den"] if c["fp_den"] else None,
                     "_k": c["so"] / c["pa"]}
            else:
                r = {"swstr": c["whiffs"] / c["pitches"], "cstr": c["called"] / c["pitches"],
                     "csw": (c["called"] + c["whiffs"]) / c["pitches"],
                     "fstrike": c["fp_strike"] / c["fp_den"] if c["fp_den"] else None,
                     "ball_rate": c["balls"] / c["pitches"], "_k": c["so"] / c["bf"]}
            lines[int(k)] = r
        if len(lines) >= NORM_MIN_LINES:
            ks = np.array([r["_k"] for r in lines.values()])
            sw = np.array([r["swstr"] for r in lines.values()])
            zk = (ks - ks.mean()) / (ks.std() or 1.0)
            zs = (sw - sw.mean()) / (sw.std() or 1.0)
            b = float((zk * zs).mean())
            for (pid, r), a, bb_ in zip(lines.items(), zk, zs):
                r["k_resid"] = float(a - b * bb_)
        for pid, r in lines.items():
            r.pop("_k", None)
            out[(pid, season, lv)] = {f"pbp_{k}_{side}": v for k, v in r.items()}
    return out


_BAT_COLS = ("pa", "ob", "bip", "gb", "ld", "fb", "pu", "hard", "spray", "pull", "oppo", "oppo_hard")
_PIT_COLS = ("bf", "bip", "gb", "ld", "fb", "pu")


def bb_metrics(side: str) -> dict:
    """{(mlbam, season, level): {metric: value}} from the batted-ball aggregates, lines
    with at least BB_MIN balls in play."""
    out: dict = {}
    for p in sorted(BB_AGG_DIR.glob("*.v1.json.gz")):
        d = _read_gz_json(p)
        sport, season = int(d["sport"]), int(d["season"])
        lv = SPORT_LEVEL.get(sport)
        if lv is None:
            continue
        rows = d["bat"] if side == "hit" else d["pit"]
        cols = _BAT_COLS if side == "hit" else _PIT_COLS
        for k, v in rows.items():
            c = dict(zip(cols, v))
            bip = float(c.get("bip") or 0)
            if bip < BB_MIN:
                continue
            r = {"gb": c["gb"] / bip, "ld": c["ld"] / bip, "fb": c["fb"] / bip, "pu": c["pu"] / bip}
            if side == "hit":
                r["hard"] = c["hard"] / bip
                r["pull"] = c["pull"] / c["spray"] if c.get("spray") else None
                r["oppo_hard"] = c["oppo_hard"] / c["oppo"] if c.get("oppo") else None
            out[(int(k), season, lv)] = {f"bb_{kk}_{side}": vv for kk, vv in r.items()}
    return out


def tracking_metrics(side: str) -> dict:
    """{(mlbam, season, level): {metric: value}} from the EFV5_TRACKING_FETCH tables."""
    path = TRACK_DIR / ("hitter_season_level.csv.gz" if side == "hit" else "pitcher_season_level.csv.gz")
    if not path.exists():
        return {}
    names = _HIT_TRACK if side == "hit" else _PIT_TRACK
    out: dict = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            exp = _f(r.get("pa") if side == "hit" else r.get("pitches")) or 0.0
            if exp < TRACK_MIN[side]:
                continue
            key = (int(r["mlbam"]), int(r["season"]), r["level"])
            vals = {}
            for k in names:
                v = _f(r.get(k))
                if v is not None:
                    vals[f"trk_{k}_{side}"] = v
            if vals:
                out[key] = vals
    return out


# ---------------------------------------------------------------------------
# outcomes: MLB lines and frozen fWAR (labels only; no grade is read here)
# ---------------------------------------------------------------------------

def mlb_seasons() -> dict[int, set[int]]:
    """{mlbam: {season with a MLB line}} over the sport-1 season lines on disk."""
    out: dict[int, set[int]] = {}
    for season in range(2005, HORIZON + 1):
        for g in ("hitting", "pitching"):
            for r in mh.season_splits(1, season, g, fetch=False):
                pid = r.get("mlbam")
                if pid:
                    out.setdefault(int(pid), set()).add(int(season))
    return out


def fwar_totals() -> tuple[dict, str]:
    import fwar_vintage as FV
    blob = FV.load()
    return FV.season_totals(blob), str(blob.get("vintage_id"))


def labels_for_row(pid: int, season: int, mlb: dict, war: dict) -> dict | None:
    """Every label of one (player, season S) row, None where unresolved; None for the
    row when the player had a MLB line at or before S (not a prospect at S)."""
    seasons = mlb.get(pid) or set()
    if any(s <= season for s in seasons):
        return None
    first = min(seasons) if seasons else None

    def war_sum(y0, n):
        return float(sum(war.get((pid, y), 0.0) for y in range(y0, y0 + n)))
    out: dict = {}
    for name, spec in LABELS.items():
        if season > spec["max_s"]:
            out[name] = None
            continue
        lag = spec["debut_lag"]
        if name in ("reach3", "reach5"):
            out[name] = 1.0 if (first is not None and first <= season + lag) else 0.0
        elif name == "w3":
            out[name] = war_sum(first, 3) if (first is not None and first <= season + 3) else 0.0
        elif name == "l6":
            out[name] = war_sum(first, 6) if (first is not None and first <= season + 3) else 0.0
        elif name == "reach_h":
            out[name] = 1.0 if first is not None else 0.0
        elif name == "war_rate_h":
            if first is None:
                out[name] = 0.0
            else:
                n = len([s for s in seasons if s <= HORIZON])
                out[name] = float(sum(war.get((pid, s), 0.0) for s in seasons if s <= HORIZON)) / n
    return out


def label_max_debut(name: str, s_max: int) -> int:
    lag = LABELS[name]["debut_lag"]
    return HORIZON if lag is None else min(HORIZON, int(s_max) + lag)


def label_frames(name: str, season: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """[("all", every row), ("clean", rows whose window closes before the first R-VM
    cohort)] for a label with a clean frame, else [("all", every row)]."""
    out = [("all", np.ones(season.size, dtype=bool))]
    cm = LABELS[name].get("clean_max_s")
    if cm is not None:
        out.append(("clean", season <= cm))
    return out


# ---------------------------------------------------------------------------
# consensus and position, as of the V = S + 1 preseason window
# ---------------------------------------------------------------------------

def load_listings(db_path: Path | None = None) -> dict[str, list[tuple[str, str, str]]]:
    """{player_key: [(date, source, position)]} from the snapshots table, read-only."""
    p = Path(db_path or DB_PATH)
    if not p.exists():
        return {}
    con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
    try:
        q = ("SELECT player_key, snapshot_date, source, position FROM snapshots "
             "WHERE position IS NOT NULL AND position != '' AND source IN (%s)"
             % ",".join("?" * len(LISTING_SOURCES)))
        out: dict = {}
        for pk, sd, src, pos in con.execute(q, LISTING_SOURCES):
            out.setdefault(pk, []).append((str(sd or "")[:10], src, str(pos)))
    finally:
        con.close()
    return out


def position_group(position) -> str | None:
    tok = str(position or "").upper().split("/")[0].strip()
    return POS_GROUP.get(tok)


def listing_position(listings: dict, player_key: str, lo: str, hi: str) -> str | None:
    best, best_key = None, None
    for sd, src, pos in listings.get(player_key) or ():
        if not (lo <= sd < hi):
            continue
        key = (sd, -LISTING_SOURCES.index(src))
        if best_key is None or key > best_key:
            best, best_key = pos, key
    return best


def consensus_reads(side: str, listings: dict, *, vintages=CONSENSUS_VINTAGES,
                    universe=None, log=print) -> dict:
    """{(mlbam, S = V - 1): {"fv", "player_key", "group"}} over the frame rows of every
    consensus vintage. The reserved vintages are not in CONSENSUS_VINTAGES; the frame's
    guard would raise on them."""
    universe = universe if universe is not None else F.load_universe()
    out: dict = {}
    for V in vintages:
        assert int(V) not in F.RESERVED_LV
        rows = F.build_frame(side, int(V), universe=universe, milb=False, sidecars=False)
        n = 0
        for r in rows:
            fv = _f((r.get("grades") or {}).get(SB.CONSENSUS_KEY))
            pid = r.get("mlbam_id")
            if fv is None or not pid:
                continue
            lo, hi = r["window"]
            pos = listing_position(listings, r["player_key"], lo, hi) or r.get("position")
            key = (int(pid), int(V) - 1)
            if key in out:
                continue
            out[key] = {"fv": fv, "player_key": r["player_key"],
                        "group": position_group(pos) if side == "hit" else None}
            n += 1
        log(f"  consensus {side} V {V}: {len(rows)} frame rows, {n} with a consensus and an id")
    return out


# ---------------------------------------------------------------------------
# the table
# ---------------------------------------------------------------------------

class Table:
    """Column arrays over the rows of one side."""

    def __init__(self, side: str, rows: list[dict], metrics: list[str]):
        self.side = side
        self.n = len(rows)
        self.pid = np.array([r["pid"] for r in rows], dtype=np.int64)
        self.season = np.array([r["season"] for r in rows], dtype=np.int64)
        self.level = np.array([r["level"] for r in rows])
        self.band = np.array([r["band"] for r in rows])
        self.group = np.array([r["group"] or "" for r in rows])
        self.fv = np.array([np.nan if r["fv"] is None else r["fv"] for r in rows], dtype=np.float64)
        self.metrics = metrics
        self.x = {m: np.array([np.nan if r["m"].get(m) is None else r["m"][m] for r in rows],
                              dtype=np.float64) for m in metrics}
        self.y = {lb: np.array([np.nan if r["y"].get(lb) is None else r["y"][lb] for r in rows],
                               dtype=np.float64) for lb in LABELS}


def _relative(values: dict, ages: dict, qual: dict, keys: list, stat_keys: list) -> dict:
    """{key: {stat_rel: value}}: each rate minus its level-season age line fitted on the
    qualified lines of that level-season (NORM_MIN_LINES or more with an age)."""
    pools: dict = {}
    for k in keys:
        if not qual[k]:
            continue
        pools.setdefault((k[1], k[2]), []).append(k)
    fits: dict = {}
    for pool, ks in pools.items():
        for s in stat_keys:
            xs, ys = [], []
            for k in ks:
                v, a = values[k].get(s), ages.get(k)
                if v is None or a is None:
                    continue
                xs.append(a)
                ys.append(v)
            if len(xs) < NORM_MIN_LINES:
                continue
            x, y = np.array(xs), np.array(ys)
            mx, my = x.mean(), y.mean()
            sxx = float(((x - mx) ** 2).sum())
            b = float(((x - mx) * (y - my)).sum() / sxx) if sxx > 0 else 0.0
            fits[(pool, s)] = (my - b * mx, b, mx)
    out: dict = {}
    for k in keys:
        pool = (k[1], k[2])
        rel = {}
        for s in stat_keys:
            fit = fits.get((pool, s))
            v = values[k].get(s)
            if fit is None or v is None:
                continue
            a0, b, mx = fit
            age = ages.get(k)
            rel[s + "_rel"] = v - (a0 + b * (age if age is not None else mx))
        out[k] = rel
    return out


def _age_bands(keys: list, ages: dict, qual: dict) -> dict:
    """Tercile band of age inside each (season, level) over the qualified lines."""
    pools: dict = {}
    for k in keys:
        if qual[k] and ages.get(k) is not None:
            pools.setdefault((k[1], k[2]), []).append(k)
    out: dict = {}
    for pool, ks in pools.items():
        a = np.array([ages[k] for k in ks])
        lo, hi = np.percentile(a, [100.0 / 3.0, 200.0 / 3.0])
        for k, v in zip(ks, a):
            out[k] = "young" if v <= lo else ("old" if v > hi else "average")
    return out


def build_table(side: str, *, mlb: dict, war: dict, cons: dict, log=print) -> Table:
    lines = box_lines(side)
    rate_fn = hit_rates if side == "hit" else pit_rates
    stat_keys = list(_HIT_BOX if side == "hit" else _PIT_BOX)
    values, ages, qual = {}, {}, {}
    exp_key = "pa" if side == "hit" else "bf"
    for k, c in lines.items():
        qual[k] = (c.get(exp_key) or 0.0) >= QUAL[side]
        ages[k] = c.get("age")
        values[k] = rate_fn(c)
    keys = list(lines)
    rel = _relative(values, ages, qual, keys, stat_keys)
    bands = _age_bands(keys, ages, qual)
    mean_age: dict = {}
    for k in keys:
        if qual[k] and ages.get(k) is not None:
            mean_age.setdefault((k[1], k[2]), []).append(ages[k])
    mean_age = {p: float(np.mean(v)) for p, v in mean_age.items()}
    pbp, bb, trk = pbp_metrics(side), bb_metrics(side), tracking_metrics(side)
    rows = []
    n_labelled = 0
    for k in keys:
        if not qual[k]:
            continue
        pid, season, lv = k
        y = labels_for_row(pid, season, mlb, war)
        if y is None:
            continue
        n_labelled += 1
        c = lines[k]
        m = {f"{s}_{side}": v for s, v in values[k].items()}
        m.update({f"{s}_{side}": v for s, v in rel[k].items()})
        a = ages.get(k)
        m[f"age_{side}"] = a
        m[f"age_rel_level_{side}"] = (a - mean_age[(season, lv)]) if (a is not None and (season, lv) in mean_age) else None
        m.update(pbp.get(k) or {})
        m.update(bb.get(k) or {})
        m.update(trk.get(k) or {})
        cr = cons.get((pid, season))
        if side == "pit":
            g = c.get("g") or 0.0
            group = ("RP" if (c.get("gs") or 0.0) / g < RP_GS_SHARE else "SP") if g > 0 else None
        else:
            group = cr["group"] if cr else None
        rows.append({"pid": pid, "season": season, "level": lv, "band": bands.get(k, "unknown"),
                     "group": group, "fv": cr["fv"] if cr else None, "m": m, "y": y})
    metrics = [m for m, (fam, s, _w) in METRICS.items() if s == side]
    log(f"  {side}: {len(lines)} level-season lines, {sum(qual.values())} qualified, "
        f"{len(rows)} prospect rows, {sum(1 for r in rows if r['fv'] is not None)} listed; "
        f"pbp {len(pbp)}, bb {len(bb)}, tracking {len(trk)} lines")
    return Table(side, rows, metrics)


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------

def auc(score: np.ndarray, pos: np.ndarray) -> float | None:
    """Pooled AUC with ties at one half."""
    pos = pos.astype(bool)
    n1, n0 = int(pos.sum()), int((~pos).sum())
    if n1 == 0 or n0 == 0:
        return None
    order = np.argsort(score, kind="mergesort")
    s = score[order]
    r = np.empty(s.size)
    # average ranks over ties
    i = 0
    while i < s.size:
        j = i
        while j + 1 < s.size and s[j + 1] == s[i]:
            j += 1
        r[i:j + 1] = (i + j) / 2.0 + 1.0
        i = j + 1
    ranks = np.empty(s.size)
    ranks[order] = r
    return float((ranks[pos].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def auc_weighted(score: np.ndarray, pos: np.ndarray, W: np.ndarray) -> np.ndarray:
    """AUC under each row-weight vector of W (B x n), ties at one half."""
    order = np.argsort(score, kind="mergesort")
    s = score[order]
    y = pos[order].astype(np.float64)
    Wo = W[:, order]
    starts = np.flatnonzero(np.r_[True, s[1:] != s[:-1]])
    wp = np.add.reduceat(Wo * y, starts, axis=1)
    wn = np.add.reduceat(Wo * (1.0 - y), starts, axis=1)
    below = np.cumsum(wn, axis=1) - wn
    num = (wp * (below + 0.5 * wn)).sum(axis=1)
    den = wp.sum(axis=1) * wn.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = num / den
    out[den <= 0] = np.nan
    return out


def _ranks(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x, kind="mergesort")
    s = x[order]
    r = np.empty(s.size)
    i = 0
    while i < s.size:
        j = i
        while j + 1 < s.size and s[j + 1] == s[i]:
            j += 1
        r[i:j + 1] = (i + j) / 2.0 + 1.0
        i = j + 1
    out = np.empty(s.size)
    out[order] = r
    return out


def within_pct(y: np.ndarray, season: np.ndarray) -> np.ndarray:
    """Within-season percentile rank of y (0 to 1), the ridge target."""
    out = np.empty(y.size)
    for s in np.unique(season):
        m = season == s
        r = _ranks(y[m])
        out[m] = (r - 0.5) / m.sum()
    return out


def within_rho(pred: np.ndarray, y: np.ndarray, season: np.ndarray,
               W: np.ndarray | None = None):
    """Size-weighted within-season Spearman over seasons holding at least
    MIN_GROUP_ROWS rows (efv_v2_stat.within's convention). With W (B x n) the ranks
    stay fixed and each season's weighted Pearson of the ranks is combined by its
    drawn size (E_cond: scores fixed, players resampled)."""
    seasons, counts = np.unique(season, return_counts=True)
    keep = seasons[counts >= MIN_GROUP_ROWS]
    if keep.size == 0:
        return None if W is None else np.full(W.shape[0], np.nan)
    if W is None:
        tot = n = 0.0
        for s in keep:
            m = season == s
            rp, ry = _ranks(pred[m]), _ranks(y[m])
            if rp.std() <= 0 or ry.std() <= 0:
                continue
            tot += float(np.corrcoef(rp, ry)[0, 1]) * m.sum()
            n += m.sum()
        return tot / n if n else None
    B = W.shape[0]
    tot, n = np.zeros(B), np.zeros(B)
    for s in keep:
        m = season == s
        rp, ry = _ranks(pred[m]), _ranks(y[m])
        Wg = W[:, m]
        sw = Wg.sum(axis=1)
        ok = sw > 0
        mx = (Wg @ rp) / np.where(ok, sw, 1.0)
        my = (Wg @ ry) / np.where(ok, sw, 1.0)
        sxx = (Wg @ (rp * rp)) / np.where(ok, sw, 1.0) - mx * mx
        syy = (Wg @ (ry * ry)) / np.where(ok, sw, 1.0) - my * my
        sxy = (Wg @ (rp * ry)) / np.where(ok, sw, 1.0) - mx * my
        den = np.sqrt(np.clip(sxx, 0, None) * np.clip(syy, 0, None))
        good = ok & (den > 1e-12)
        r = np.where(good, sxy / np.where(den > 0, den, 1.0), 0.0)
        tot += np.where(good, r * sw, 0.0)
        n += np.where(good, sw, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = tot / n
    out[n <= 0] = np.nan
    return out


def _design(cols: list[np.ndarray], season: np.ndarray) -> np.ndarray:
    """[1, season dummies (reference: the first season), cols...]."""
    seasons = np.unique(season)
    parts = [np.ones(season.size)]
    for s in seasons[1:]:
        parts.append((season == s).astype(np.float64))
    parts.extend(cols)
    return np.column_stack(parts)


def _standardise(Xtr: np.ndarray, Xte: np.ndarray, n_fixed: int):
    """Standardise the trailing feature columns by the training rows (dummies and the
    intercept stay). A constant column is zeroed."""
    Xtr, Xte = Xtr.copy(), Xte.copy()
    for j in range(n_fixed, Xtr.shape[1]):
        mu, sd = Xtr[:, j].mean(), Xtr[:, j].std()
        if sd <= 1e-12:
            Xtr[:, j] = 0.0
            Xte[:, j] = 0.0
        else:
            Xtr[:, j] = (Xtr[:, j] - mu) / sd
            Xte[:, j] = (Xte[:, j] - mu) / sd
    return Xtr, Xte


def fit_logistic(X: np.ndarray, y: np.ndarray, ridge: float = RIDGE) -> np.ndarray:
    """Newton steps on the ridge-penalised log likelihood (the intercept unpenalised)."""
    n, p = X.shape
    w = np.zeros(p)
    pen = np.full(p, ridge)
    pen[0] = 0.0
    for _ in range(NEWTON_ITERS):
        z = X @ w
        pr = 1.0 / (1.0 + np.exp(-z))
        g = X.T @ (pr - y) + pen * w
        s = pr * (1.0 - pr)
        Hs = (X * s[:, None]).T @ X + np.diag(pen)
        try:
            step = np.linalg.solve(Hs, g)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(Hs, g, rcond=None)[0]
        w = w - step
        if float(np.abs(step).max()) < 1e-8:
            break
    return w


def fit_ridge(X: np.ndarray, y: np.ndarray, ridge: float = RIDGE) -> np.ndarray:
    p = X.shape[1]
    pen = np.full(p, ridge)
    pen[0] = 0.0
    A = X.T @ X + np.diag(pen)
    try:
        return np.linalg.solve(A, X.T @ y)
    except np.linalg.LinAlgError:
        return np.linalg.lstsq(A, X.T @ y, rcond=None)[0]


def player_folds(pid: np.ndarray, k: int = FOLDS, seed: int = SEED) -> np.ndarray:
    """Fold of each row: players shuffled once, assigned round robin."""
    players = np.unique(pid)
    rng = np.random.default_rng(seed)
    perm = rng.permutation(players.size)
    fold_of = {int(p): int(perm[i] % k) for i, p in enumerate(players)}
    return np.array([fold_of[int(p)] for p in pid])


def oof_predictions(cols: list[np.ndarray], y: np.ndarray, season: np.ndarray,
                    folds: np.ndarray, kind: str) -> np.ndarray:
    """Out-of-fold linear predictor of the model on [season, cols]."""
    X = _design(cols, season)
    n_fixed = X.shape[1] - len(cols)
    out = np.empty(y.size)
    target = y if kind == "binary" else within_pct(y, season)
    for f in np.unique(folds):
        te = folds == f
        tr = ~te
        Xtr, Xte = _standardise(X[tr], X[te], n_fixed)
        if kind == "binary":
            w = fit_logistic(Xtr, target[tr])
        else:
            w = fit_ridge(Xtr, target[tr])
        out[te] = Xte @ w
    return out


def cluster_weights(pid: np.ndarray, B: int, seed: int) -> np.ndarray:
    """B x n draw counts: players resampled with replacement, every row of a drawn
    player drawn with it."""
    players, inv = np.unique(pid, return_inverse=True)
    rng = np.random.default_rng(seed)
    counts = rng.multinomial(players.size, np.full(players.size, 1.0 / players.size), size=B)
    return counts[:, inv].astype(np.float64)


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def interval(draws: np.ndarray) -> dict:
    d = draws[np.isfinite(draws)]
    if d.size < 50:
        return {"ci95": None, "sd": None, "p": None, "draws": int(d.size)}
    sd = float(d.std(ddof=1))
    lo, hi = np.percentile(d, [2.5, 97.5])
    return {"ci95": [round(float(lo), 4), round(float(hi), 4)], "sd": round(sd, 5),
            "draws": int(d.size)}


def p_normal(delta: float | None, sd: float | None) -> float | None:
    if delta is None or sd is None or sd <= 0:
        return None
    return float(2.0 * (1.0 - _phi(abs(delta) / sd)))


def bh_q(ps: list) -> list:
    """Benjamini-Hochberg q over the given p values (None stays None)."""
    idx = [i for i, p in enumerate(ps) if p is not None]
    out = [None] * len(ps)
    if not idx:
        return out
    m = len(idx)
    order = sorted(idx, key=lambda i: ps[i])
    q = [0.0] * m
    prev = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        val = min(prev, ps[i] * m / rank)
        q[rank - 1] = val
        prev = val
    for rank, i in enumerate(order):
        out[i] = round(float(min(1.0, q[rank])), 5)
    return out


def oriented(a: float | None):
    """(oriented score, direction) with the score read above 0.5."""
    if a is None:
        return None, None
    return (a, "higher") if a >= 0.5 else (1.0 - a, "lower")


# ---------------------------------------------------------------------------
# one cell
# ---------------------------------------------------------------------------

def raw_score(x: np.ndarray, y: np.ndarray, season: np.ndarray, kind: str,
              W: np.ndarray | None):
    if kind == "binary":
        point = auc(x, y)
        draws = auc_weighted(x, y, W) if W is not None else None
    else:
        point = within_rho(x, y, season)
        draws = within_rho(x, y, season, W) if W is not None else None
    return point, draws


def enough(pid: np.ndarray, y: np.ndarray, kind: str) -> bool:
    if np.unique(pid).size < MIN_PLAYERS:
        return False
    k = int((y > 0).sum()) if kind == "binary" else int((y != 0).sum())
    if k < MIN_POS:
        return False
    if kind == "binary" and int((y <= 0).sum()) < MIN_POS:
        return False
    return True


def cell_weights(T: Table, mask: np.ndarray, label: str, B: int, seed: int) -> dict | None:
    """The draw counts of one (cell, label), shared by every metric of the cell: the
    players of the cell's labelled rows are resampled once (full population) and once
    more on its listed rows; a metric's test takes the columns of its own rows."""
    m = mask & np.isfinite(T.y[label])
    if not m.any():
        return None
    ml = m & np.isfinite(T.fv)
    return {"mask": m, "full": cluster_weights(T.pid[m], B, seed),
            "listed": cluster_weights(T.pid[ml], B, seed + 1) if ml.any() else None}


def score_cell(T: Table, mask: np.ndarray, metric: str, label: str, *, B: int,
               seed: int, folds_all: np.ndarray, weights: dict | None = None) -> dict | None:
    kind = LABELS[label]["kind"]
    y_all, x_all = T.y[label], T.x[metric]
    m_full = mask & np.isfinite(y_all) & np.isfinite(x_all)
    if not m_full.any():
        return None
    out = {"metric": metric, "label": label}
    pid, y, x, season = T.pid[m_full], y_all[m_full], x_all[m_full], T.season[m_full]
    if enough(pid, y, kind):
        W = (weights["full"][:, m_full[weights["mask"]]] if weights is not None
             else cluster_weights(pid, B, seed))
        point, draws = raw_score(x, y, season, kind, W)
        iv = interval(draws)
        out["full"] = {"n": int(y.size), "players": int(np.unique(pid).size),
                       "pos": int((y > 0).sum()) if kind == "binary" else int((y != 0).sum()),
                       "seasons": [int(season.min()), int(season.max())],
                       "score": None if point is None else round(point, 4),
                       "ci95": iv["ci95"]}
    m_listed = m_full & np.isfinite(T.fv)
    pid, y, x, season, fv = (T.pid[m_listed], y_all[m_listed], x_all[m_listed],
                             T.season[m_listed], T.fv[m_listed])
    if enough(pid, y, kind):
        W = (weights["listed"][:, m_listed[weights["mask"] & np.isfinite(T.fv)]]
             if weights is not None else cluster_weights(pid, B, seed + 1))
        raw_l, _ = raw_score(x, y, season, kind, None)
        raw_c, _ = raw_score(fv, y, season, kind, None)
        folds = folds_all[m_listed]
        p_c = oof_predictions([fv], y, season, folds, kind)
        p_cm = oof_predictions([fv, x], y, season, folds, kind)
        if kind == "binary":
            s_c, s_cm = auc(p_c, y), auc(p_cm, y)
            d_c, d_cm = auc_weighted(p_c, y, W), auc_weighted(p_cm, y, W)
        else:
            s_c, s_cm = within_rho(p_c, y, season), within_rho(p_cm, y, season)
            d_c, d_cm = within_rho(p_c, y, season, W), within_rho(p_cm, y, season, W)
        delta = None if (s_c is None or s_cm is None) else float(s_cm - s_c)
        iv = interval(d_cm - d_c)
        out["listed"] = {"n": int(y.size), "players": int(np.unique(pid).size),
                         "pos": int((y > 0).sum()) if kind == "binary" else int((y != 0).sum()),
                         "seasons": [int(season.min()), int(season.max())],
                         "score": None if raw_l is None else round(raw_l, 4),
                         "consensus": None if raw_c is None else round(raw_c, 4),
                         "model_c": None if s_c is None else round(s_c, 4),
                         "model_cm": None if s_cm is None else round(s_cm, 4),
                         "delta": None if delta is None else round(delta, 4),
                         "ci95": iv["ci95"], "sd": iv["sd"],
                         "p": p_normal(delta, iv["sd"])}
    if "full" not in out and "listed" not in out:
        return None
    return out


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def cell_masks(T: Table):
    for lv in LEVELS:
        m_lv = T.level == lv
        if not m_lv.any():
            continue
        for band in BANDS:
            m_b = m_lv if band == "all" else (m_lv & (T.band == band))
            for g in GROUPS[T.side]:
                m = m_b if g == "all" else (m_b & (T.group == g))
                if m.sum() < MIN_PLAYERS:
                    continue
                yield lv, band, g, m


CELL_COLUMNS = ("side", "level", "age_band", "group", "metric", "family", "label", "frame", "population",
                "n_full", "players_full", "pos_full", "seasons_full", "raw_full", "raw_full_ci95",
                "n_listed", "players_listed", "pos_listed", "seasons_listed", "raw_listed",
                "consensus_raw", "model_c", "model_cm", "incr", "incr_ci95", "incr_sd", "p", "q",
                "reserved_overlap")


def run_atlas(*, B: int = B_DEFAULT, seed: int = SEED, sides=("hit", "pit"), log=print,
              tables: dict | None = None) -> dict:
    t0 = time.time()
    if tables is None:
        tables = build_tables(log=log)
    rows: list[dict] = []
    for side in sides:
        T = tables[side]
        folds_all = player_folds(T.pid, FOLDS, seed)
        n_cells = 0
        for lv, band, g, mask in cell_masks(T):
            n_cells += 1
            for label, frame, m_frame in [(lb, fr, m) for lb in LABELS
                                          for fr, m in label_frames(lb, T.season)]:
                mask_f = mask & m_frame
                weights = cell_weights(T, mask_f, label, B, seed)
                if weights is None:
                    continue
                for metric in T.metrics:
                    r = score_cell(T, mask_f, metric, label, B=B, seed=seed, folds_all=folds_all,
                                   weights=weights)
                    if r is None:
                        continue
                    full, listed = r.get("full"), r.get("listed")
                    s_max = max((full or listed)["seasons"][1],
                                (listed or full)["seasons"][1])
                    rows.append({
                        "side": side, "level": lv, "age_band": band, "group": g,
                        "metric": metric, "family": METRICS[metric][0], "label": label,
                        "frame": frame,
                        "population": "full" if (g == "all" or side == "pit") else "listed",
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
                        "reserved_overlap": label_max_debut(label, s_max) >= F.R_VM_FIRST_DEBUT_YEAR,
                    })
            log(f"  {side} {lv} {band} {g}: {int(mask.sum())} rows, {len(rows)} tests so far "
                f"({time.time() - t0:.0f} s)")
        log(f"  {side}: {n_cells} cells")
    # BH within (family, label)
    fam_lab: dict = {}
    for i, r in enumerate(rows):
        fam_lab.setdefault((r["family"], r["label"]), []).append(i)
    for idx in fam_lab.values():
        qs = bh_q([rows[i]["p"] for i in idx])
        for i, q in zip(idx, qs):
            rows[i]["q"] = q
    return {"rows": rows, "seconds": round(time.time() - t0, 1), "tables": tables}


def build_tables(log=print) -> dict:
    t0 = time.time()
    mlb = mlb_seasons()
    war, vintage_id = fwar_totals()
    listings = load_listings()
    universe = F.load_universe()
    tables = {}
    for side in ("hit", "pit"):
        cons = consensus_reads(side, listings, universe=universe, log=log)
        tables[side] = build_table(side, mlb=mlb, war=war, cons=cons, log=log)
    log(f"  tables built in {time.time() - t0:.0f} s; fWAR vintage {vintage_id}; "
        f"{len(mlb)} players with a MLB line")
    tables["_meta"] = {"fwar_vintage_id": vintage_id, "mlb_players": len(mlb),
                       "listings_players": len(listings)}
    return tables


# ---------------------------------------------------------------------------
# the owner's chart, replicated
# ---------------------------------------------------------------------------

def chart_replication(T: Table, *, seasons=(2021, 2025), B: int = B_DEFAULT,
                      seed: int = SEED) -> dict:
    """Single-A pitchers (the Florida State League, the only tracked Single-A league),
    seasons [lo, hi], label reach_h (reached MLB by HORIZON): the AUC of every chart
    statistic oriented as the chart orients it, on the full population and on the
    listed rows, with the chart's own number beside each."""
    lo, hi = seasons
    base = ((T.level == "A") & (T.season >= lo) & (T.season <= hi) & np.isfinite(T.y["reach_h"])
            & np.isfinite(T.x["trk_csw_pit"]))        # the tracked population, every statistic
    y_all = T.y["reach_h"]
    rows = []
    for label, metric, sign, chart_val in CHART:
        if metric is None:
            rows.append({"chart_label": label, "metric": None, "chart": chart_val, "ours": None,
                         "note": "no in-repo model (Location+ and Pitching+ are not built here)"})
            continue
        x_all = T.x[metric]
        m = base & np.isfinite(x_all)
        x, y, pid = sign * x_all[m], y_all[m], T.pid[m]
        row = {"chart_label": label, "metric": metric, "direction": "higher" if sign > 0 else "lower",
               "chart": chart_val, "n": int(y.size), "players": int(np.unique(pid).size),
               "reached": int(y.sum()), "ours": None, "ci95": None, "listed": None}
        if y.size and 0 < y.sum() < y.size:
            a = auc(x, y)
            W = cluster_weights(pid, B, seed)
            iv = interval(auc_weighted(x, y, W))
            row["ours"] = None if a is None else round(100.0 * a, 1)
            row["ci95"] = None if iv["ci95"] is None else [round(100.0 * iv["ci95"][0], 1),
                                                           round(100.0 * iv["ci95"][1], 1)]
            row["gap"] = None if a is None else round(100.0 * a - chart_val, 1)
            ml = m & np.isfinite(T.fv)
            if ml.sum() >= MIN_POS and 0 < y_all[ml].sum() < ml.sum():
                al = auc(sign * x_all[ml], y_all[ml])
                ac = auc(T.fv[ml], y_all[ml])
                row["listed"] = {"n": int(ml.sum()), "reached": int(y_all[ml].sum()),
                                 "ours": None if al is None else round(100.0 * al, 1),
                                 "consensus": None if ac is None else round(100.0 * ac, 1)}
        rows.append(row)
    done = [r for r in rows if r.get("ours") is not None]
    gaps = [r["gap"] for r in done]
    return {"frame": {"side": "pit", "level": "A (Florida State League, the only tracked Single-A league)",
                      "seasons": [lo, hi], "label": LABELS["reach_h"]["what"],
                      "qualification": f"batters faced >= {QUAL['pit']:.0f} on the season line and pitches >= {TRACK_MIN['pit']:.0f} in the tracking table",
                      "population": "every tracked FSL pitcher-season with no prior MLB line (one population for every statistic)"},
            "rows": rows,
            "summary": {"statistics_compared": len(done),
                        "mean_gap": round(float(np.mean(gaps)), 1) if gaps else None,
                        "mean_abs_gap": round(float(np.mean(np.abs(gaps))), 1) if gaps else None,
                        "rank_agreement": _rank_agreement(done)},
            "spent": SPENT_NOTE}


def _rank_agreement(done: list[dict]):
    if len(done) < 3:
        return None
    a = np.array([r["chart"] for r in done], dtype=np.float64)
    b = np.array([r["ours"] for r in done], dtype=np.float64)
    ra, rb = _ranks(a), _ranks(b)
    if ra.std() <= 0 or rb.std() <= 0:
        return None
    return round(float(np.corrcoef(ra, rb)[0, 1]), 3)


# ---------------------------------------------------------------------------
# summaries and the artifact
# ---------------------------------------------------------------------------

def _is_candidate(r: dict) -> bool:
    ci = r.get("incr_ci95")
    return (r.get("incr") is not None and r["incr"] > 0 and ci is not None and ci[0] > 0
            and r.get("q") is not None and r["q"] <= CANDIDATE_Q)


def summarise(rows: list[dict], top: int = 8) -> tuple[dict, list[dict]]:
    """top_by_group: per (side, level, age band, group, label) the top metrics by
    incremental lift; candidates: every cell passing the declared rule, clean cells
    first, spent-overlap cells flagged."""
    by_group: dict = {}
    for r in rows:
        if r.get("incr") is None:
            continue
        key = f"{r['side']}|{r['level']}|{r['age_band']}|{r['group']}|{r['label']}|{r['frame']}"
        by_group.setdefault(key, []).append(r)
    top_by_group = {}
    for key, rs in by_group.items():
        rs.sort(key=lambda r: -r["incr"])
        top_by_group[key] = [{"metric": r["metric"], "family": r["family"], "incr": r["incr"],
                              "ci95": r["incr_ci95"], "q": r["q"], "n": r["n_listed"],
                              "raw_listed": r["raw_listed"], "consensus_raw": r["consensus_raw"],
                              "reserved_overlap": r["reserved_overlap"]} for r in rs[:top]]
    cands = [r for r in rows if _is_candidate(r)]
    cands.sort(key=lambda r: (r["reserved_overlap"], -(r["incr"] or 0.0)))
    out = [{"metric": r["metric"], "family": r["family"], "side": r["side"], "level": r["level"],
            "age_band": r["age_band"], "group": r["group"], "label": r["label"],
            "frame": r["frame"], "incr": r["incr"], "ci95": r["incr_ci95"], "q": r["q"], "n": r["n_listed"],
            "players": r["players_listed"], "raw_listed": r["raw_listed"],
            "consensus_raw": r["consensus_raw"],
            "status": "spent-overlap" if r["reserved_overlap"] else "clean"} for r in cands]
    return top_by_group, out


def coverage(tables: dict) -> dict:
    out = {}
    for side in ("hit", "pit"):
        T = tables[side]
        by_lv = {}
        for lv in LEVELS:
            m = T.level == lv
            if not m.any():
                continue
            by_lv[lv] = {"rows": int(m.sum()), "players": int(np.unique(T.pid[m]).size),
                         "listed": int(np.isfinite(T.fv[m]).sum()),
                         "seasons": [int(T.season[m].min()), int(T.season[m].max())],
                         "with_pbp": int(np.isfinite(T.x[f"pbp_swstr_{side}"][m]).sum()),
                         "with_bb": int(np.isfinite(T.x[f"bb_gb_{side}"][m]).sum()),
                         "with_tracking": int(np.isfinite(T.x[f"trk_swstr_{side}"][m]).sum())}
        out[side] = {"rows": int(T.n), "players": int(np.unique(T.pid).size),
                     "listed": int(np.isfinite(T.fv).sum()), "by_level": by_lv,
                     "groups": {g: int((T.group == g).sum()) for g in GROUPS[side] if g != "all"},
                     "bands": {b: int((T.band == b).sum()) for b in BANDS if b != "all"}}
    return out


def declared() -> dict:
    return {"seasons": [SEASONS[0], SEASONS[-1]], "no_season": [2020], "horizon": HORIZON,
            "levels": list(LEVELS), "qualification": QUAL, "min_players": MIN_PLAYERS,
            "min_pos": MIN_POS, "min_group_rows": MIN_GROUP_ROWS, "folds": FOLDS, "seed": SEED,
            "ridge": RIDGE, "rp_gs_share": RP_GS_SHARE, "age_bands": "terciles of age within (level, season)",
            "position_groups": {"map": POS_GROUP, "note": "listing position dated inside the V = S + 1 window; generic OF reads as corner OF; the full population carries no position"},
            "consensus_vintages": list(CONSENSUS_VINTAGES), "reserved_lv_never_built": sorted(F.RESERVED_LV),
            "pbp_min": PBP_MIN, "bb_min": BB_MIN, "tracking_min": TRACK_MIN,
            "candidate_rule": f"incremental lift > 0, CI95 lower bound > 0, BH q <= {CANDIDATE_Q} within (family, label)",
            "incremental": "out-of-fold (5 player folds) AUC of logistic[season, consensus FV, metric] minus logistic[season, consensus FV]; WAR labels: within-season Spearman of ridge on the same columns (target within-season percentile)",
            "interval": "player-clustered bootstrap, scores fixed, players resampled (E_cond); p from the bootstrap SD (normal)",
            "woba_weights": WOBA_W}


def write_artifact(result: dict, chart: dict, *, B: int, path: Path = OUT_PATH,
                   cells_path: Path = CELLS_PATH) -> tuple[Path, Path]:
    rows = result["rows"]
    tables = result["tables"]
    top_by_group, cands = summarise(rows)
    fam_counts = {}
    for r in rows:
        fam_counts[r["family"]] = fam_counts.get(r["family"], 0) + 1
    doc = {
        "schema": SCHEMA, "generated_at": _now(), "tool": TOOL, "item": ITEM, "note": NOTE,
        "role": "development", "served": False, "spent_note": SPENT_NOTE,
        "declared": declared(), "bootstrap_b": B,
        "labels": {k: {kk: vv for kk, vv in v.items() if kk != "debut_lag"} for k, v in LABELS.items()},
        "metrics": {m: {"family": f, "side": s, "what": w} for m, (f, s, w) in METRICS.items()},
        "groups": {"hit": list(HIT_GROUPS), "pit": list(PIT_GROUPS), "labels": GROUP_LABEL,
                   "age_bands": list(BANDS)},
        "inputs": tables.get("_meta", {}),
        "coverage": coverage(tables),
        "chart_replication": chart,
        "tests": len(rows), "tests_by_family": fam_counts,
        "cells_with_incremental": sum(1 for r in rows if r.get("incr") is not None),
        "candidates": cands,
        "top_by_group": top_by_group,
        "cells_file": str(cells_path.relative_to(ROOT)).replace("\\", "/"),
        "seconds": result["seconds"],
    }
    cells = {"schema": SCHEMA, "generated_at": doc["generated_at"], "tool": TOOL, "item": ITEM,
             "note": NOTE, "columns": list(CELL_COLUMNS),
             "rows": [[r[c] for c in CELL_COLUMNS] for r in rows]}
    cells_path.parent.mkdir(parents=True, exist_ok=True)
    cells_path.write_text(json.dumps(cells, separators=(",", ":")), encoding="utf-8")
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return path, cells_path


# ---------------------------------------------------------------------------
# ATLAS.md
# ---------------------------------------------------------------------------

def _fmt(v, nd=4):
    if v is None:
        return "n/a"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_fmt(x, nd) for x in v) + "]"
    if isinstance(v, float):
        return f"{v:+.{nd}f}" if nd == 4 else f"{v:.{nd}f}"
    return str(v)


def atlas_md(doc: dict, cells: dict | None = None) -> str:
    L = []
    L.append("# eFV v5 metric atlas (EFV5_METRIC_ATLAS), development read")
    L.append("")
    L.append(f"Generated {doc['generated_at']} by `{doc['tool']}` ({doc['seconds']} s, B {doc['bootstrap_b']}). "
             f"{doc['note']}. Tests: {doc['tests']} (by family: "
             + ", ".join(f"{k} {v}" for k, v in sorted(doc["tests_by_family"].items()))
             + f"); {doc['cells_with_incremental']} with an incremental score.")
    L.append("")
    d = doc["declared"]
    L.append("## 1. Declared before any read")
    L.append("")
    L.append(f"- rows: MiLB season lines {d['seasons'][0]} to {d['seasons'][1]} (no 2020), levels {', '.join(d['levels'])}; "
             f"qualification hitters PA >= {d['qualification']['hit']:.0f}, pitchers BF >= {d['qualification']['pit']:.0f}; "
             f"a player with a MLB line at or before S is not a row at S")
    L.append(f"- minimum cell: {d['min_players']} players and {d['min_pos']} reachers (or non-zero WAR rows) on the population scored")
    L.append(f"- incremental: {d['incremental']}")
    L.append(f"- interval: {d['interval']}; candidate rule: {d['candidate_rule']}")
    L.append(f"- consensus vintages {d['consensus_vintages'][0]} to {d['consensus_vintages'][-1]} without {d['reserved_lv_never_built']} (R-LV, never built); "
             f"{doc['spent_note']}")
    L.append("")
    L.append("## 2. The owner's chart, replicated")
    L.append("")
    for span, ch in doc["chart_replication"]["spans"].items():
        L.append(f"### Seasons {span}")
        L.append("")
        L.append(f"Frame: {ch['frame']['side']} {ch['frame']['level']}, seasons {ch['frame']['seasons'][0]} to {ch['frame']['seasons'][1]}, "
                 f"label {ch['frame']['label']}; {ch['frame']['population']}; {ch['frame']['qualification']}. {ch['spent']}.")
        L.append("")
        L.append("| chart statistic | our metric | chart | ours (CI95) | n (reached) | listed: ours / consensus (n) |")
        L.append("|---|---|---|---|---|---|")
        for r in ch["rows"]:
            if r.get("metric") is None:
                L.append(f"| {r['chart_label']} | none | {r['chart']} | n/a | | {r['note']} |")
                continue
            lst = r.get("listed")
            lst_s = (f"{_fmt(lst['ours'], 1)} / {_fmt(lst['consensus'], 1)} ({lst['n']})" if lst else "n/a")
            ci = r.get("ci95")
            ours = (f"{_fmt(r['ours'], 1)} ({_fmt(ci[0], 1)} to {_fmt(ci[1], 1)})" if ci
                    else _fmt(r.get("ours"), 1))
            L.append(f"| {r['chart_label']} | {r['metric']} ({r['direction']}) | {r['chart']} | {ours} | "
                     f"{r['n']} ({r['reached']}) | {lst_s} |")
        s = ch["summary"]
        L.append("")
        L.append(f"Summary: {s['statistics_compared']} statistics compared; mean gap (ours minus chart) {_fmt(s['mean_gap'], 1)}, "
                 f"mean absolute gap {_fmt(s['mean_abs_gap'], 1)}, rank agreement (Spearman of the two orderings) {_fmt(s['rank_agreement'], 3)}.")
        L.append("")
    L.append("## 3. Top metrics by INCREMENTAL lift over consensus, per group")
    L.append("")
    L.append("Each block: the top metrics of one (side, level, age band, group, label) by the out-of-fold lift "
             "over consensus FV, with CI95 and BH q. `spent` marks a cell whose label window reaches a 2025+ debut cohort.")
    L.append("")
    keys = sorted(doc["top_by_group"], key=lambda k: (k.split("|")[0], LEVEL_RANK.get(k.split("|")[1], 99), k))
    for key in keys:
        side, lv, band, g, label, frame = key.split("|")
        rs = doc["top_by_group"][key]
        if not rs:
            continue
        L.append(f"### {side} {lv}, age {band}, {GROUP_LABEL.get(g, g)}, label {label}, frame {frame}")
        L.append("")
        L.append("| metric | family | lift | CI95 | q | n | raw (listed) | consensus raw | note |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for r in rs:
            L.append(f"| {r['metric']} | {r['family']} | {_fmt(r['incr'])} | {_fmt(r['ci95'])} | {_fmt(r['q'], 3)} | "
                     f"{r['n']} | {_fmt(r['raw_listed'], 4)} | {_fmt(r['consensus_raw'], 4)} | {'spent' if r['reserved_overlap'] else ''} |")
        L.append("")
    L.append("## 4. Candidates for the driver tasks")
    L.append("")
    L.append(f"Rule: {d['candidate_rule']}. Clean cells first; spent-overlap cells are listed for the tracking-era head only and select nothing.")
    L.append("")
    if not doc["candidates"]:
        L.append("None. No cell cleared the rule.")
    else:
        L.append("| metric | family | side | level | age band | group | label | frame | lift | CI95 | q | n | players | status |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in doc["candidates"]:
            L.append(f"| {r['metric']} | {r['family']} | {r['side']} | {r['level']} | {r['age_band']} | {r['group']} | {r['label']} | {r['frame']} | "
                     f"{_fmt(r['incr'])} | {_fmt(r['ci95'])} | {_fmt(r['q'], 3)} | {r['n']} | {r['players']} | {r['status']} |")
    L.append("")
    L.append("## 5. Coverage")
    L.append("")
    for side, c in doc["coverage"].items():
        L.append(f"- {side}: {c['rows']} rows, {c['players']} players, {c['listed']} listed; groups "
                 + ", ".join(f"{k} {v}" for k, v in c["groups"].items()) + "; bands "
                 + ", ".join(f"{k} {v}" for k, v in c["bands"].items()))
        for lv, b in c["by_level"].items():
            L.append(f"  - {lv}: rows {b['rows']}, players {b['players']}, listed {b['listed']}, seasons {b['seasons'][0]}-{b['seasons'][1]}, "
                     f"with pbp {b['with_pbp']}, bb {b['with_bb']}, tracking {b['with_tracking']}")
    L.append("")
    return "\r\n".join(L) + "\r\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--warm-profile", action="store_true")
    ap.add_argument("--chart", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--b", type=int, default=B_DEFAULT)
    ap.add_argument("--sides", default="hit,pit")
    ap.add_argument("--md", default=None, help="write ATLAS.md from the artifact to PATH")
    a = ap.parse_args(argv)
    if a.warm_profile:
        out = warm_profile()
        print(json.dumps({k: v for k, v in out.items()}, indent=1))
    if a.chart or a.run:
        tables = build_tables()
        chart = {"primary": "2021-2025",
                 "spans": {f"{s[0]}-{s[1]}": chart_replication(tables["pit"], seasons=s, B=a.b)
                           for s in ((2021, 2025), (2021, 2024))}}
        for span, ch in chart["spans"].items():
            print(f"chart replication, seasons {span}:")
            for r in ch["rows"]:
                print(f"  {r['chart_label']:<24} chart {r['chart']:>3}  ours {_fmt(r.get('ours'), 1):>5}  "
                      f"n {r.get('n', '')} reached {r.get('reached', '')}")
            print(f"  summary {ch['summary']}")
        if a.run:
            res = run_atlas(B=a.b, sides=tuple(a.sides.split(",")), tables=tables)
            p, c = write_artifact(res, chart, B=a.b)
            print(f"wrote {p} and {c}: {len(res['rows'])} tests in {res['seconds']} s")
    if a.md:
        doc = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        Path(a.md).write_bytes(atlas_md(doc).encode("utf-8"))
        print(f"wrote {a.md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
