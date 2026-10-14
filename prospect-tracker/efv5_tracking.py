# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v5 tracking-era inputs: MiLB pitch tracking (Hawk-Eye / Statcast) per
player-season-level (EFV5_TRACKING_FETCH; owner 2026-10-14, decisions EW3-1 to
EW3-5).

WHAT THIS IS. The fetch and the per-player tables only. Nothing here scores a
player against consensus, a label or an FV cell, and nothing here feeds a served
number. The tracking-era head (EW3-1) and the metric atlas (EW3-2) read these
tables; they own every outcome read.

SOURCE. Baseball Savant's minor-league Statcast search (statcast-search-minors,
type=details, minors=true, regular season), the same request skeleton as
stuff_plus_aaa.SEARCH, asked one calendar day at a time with no player filter so
one request carries every tracked game of that day (about 5,500 pitches, well
under the search's row cap). Coverage, verified by probe on 2026-10-14 and
recorded in data/_labs/efv5/tracking_coverage.json:
    2019 and earlier   nothing served (a 2019-06-12 day returns 0 rows)
    2020               no MiLB season
    2021               Single-A Florida State League parks only
    2022 to 2026       Triple-A (International and Pacific Coast Leagues) plus
                       the Florida State League
    AA and High-A      never served
(the artifact's verified_coverage.summary is derived from the fetched rows).
Not every served game carries tracking: a share of 2021 pitches and most 2022
Triple-A pitches have the call and the result but no kinematics, and arm angle is
mostly absent before 2023 (the artifact's season_checks carry the shares). Every
kinematic and batted-ball metric
below is computed over TRACKED pitches only (release_speed and plate location
present); call-based rates (CSW, whiff) use every pitch.

LEVEL. Savant's rows carry no level column. Each game_pk is mapped to its level
through the StatsAPI schedule (sportId 11 AAA, 12 AA, 13 A+, 14 A), fetched once
per season into this module's cache.

CACHE (this task's own folder, never committed):
    .cache/efv5_savant_minors/days/<season>/<YYYY-MM-DD>.csv.gz  kept columns
    .cache/efv5_savant_minors/days/<season>/<YYYY-MM-DD>.empty   0-row day
    .cache/efv5_savant_minors/schedule/<season>.json             game_pk to level
    .cache/efv5_savant_minors/tables/pitcher_season_level.csv.gz
    .cache/efv5_savant_minors/tables/hitter_season_level.csv.gz
Closed seasons are immutable: a cached day is never refetched, so the fetch
resumes where it stopped. Requests are polite: at most WORKERS concurrent, one
request start per THROTTLE_S, exponential back-off on 429 and 5xx, and no
request at all between 06:00 and 11:00 UTC (the nightly fetch window).

DEFINITIONS (pitch descriptions as Savant serves them):
    swing     swinging_strike, swinging_strike_blocked, foul_tip, foul, foul_bunt,
              missed_bunt, bunt_foul_tip, hit_into_play
    whiff     swinging_strike, swinging_strike_blocked, foul_tip, missed_bunt
              (foul tips count as whiffs, the efv_w2_pbp convention)
    CSW       (called_strike + whiffs) / pitches
    zone      Savant zone 1 to 9 in, 11 to 14 out (tracked pitches only)
    chase     swings at out-of-zone pitches / out-of-zone pitches
    BBE       a ball in play (type X) with a measured exit velocity
    hard-hit  BBE at 95 mph or more; barrel = launch_speed_angle 6;
              sweet spot = launch angle 8 to 32 degrees
    xwOBA     sum over PAs whose last pitch is tracked of the speed-angle
              expected wOBA for a BBE, else the PA's wOBA value, divided by the
              wOBA denominator of the same PAs
    fastball  FF, SI, FT, FA for velo, ride and run; the pitch classes of
              whiff and aStuff+ by class (PITCH_CLASS) are fb = those plus FC,
              br = SL, ST, SV, CU, KC, CS, os = CH, FS, FO, SC, EP, KN
    ride      induced vertical break of the primary fastball (its most thrown of
              FF, SI, FT, FA), pfx_z in inches
    run       horizontal break of the same pitch, arm side positive, inches
    arm angle the mean of Savant's arm_angle column, the repo's method
              (aaa_physics_export); null where Savant serves none (most of 2021, 2022)

aStuff+. The repo's in-house stuff model, applied, never refit: model
stuff_plus_aaa v1 (model/stuff_plus_aaa.joblib), a LightGBM regressor on physics
only (velo, spin, extension, arm-side movement, release point, arm angle, velo
gap to the primary fastball, handedness) with label delta_run_exp per pitch,
trained on Savant AAA pitches 2023 and 2024, validated season-out on 2025, and
shipped as a fit on all three seasons. Features here are built exactly as
stuff_plus_aaa._featurize builds them (pinned by a test). The pitcher-season-
level score is the mean predicted run value, shrunk toward the pool mean with
k = stuff_plus_aaa.SHRINK_K and put on 100 + 10z, the pool being the AAA 2025
pitcher-season-levels with at least stuff_plus_aaa.MIN_POOL_PITCHES tracked
pitches in THIS cache (the served sidecar's pool convention). Two cautions ride
on every use: AAA 2023 to 2025 pitches are in the model's own training data, and
the Florida State League is outside it.
Location+ and Pitching+ have no in-repo model (no module fits either), so the
tables carry neither; building one would mean fitting a new model on outcomes,
which this task does not do.

Run: python efv5_tracking.py --probe   (one request per season, prints coverage)
     python efv5_tracking.py --fetch   (resumable day fetch + schedules)
     python efv5_tracking.py --build   (tables + coverage artifact)
     python efv5_tracking.py --all
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import logging
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache" / "efv5_savant_minors"
DAYS_DIR = CACHE_DIR / "days"
SCHED_DIR = CACHE_DIR / "schedule"
TABLE_DIR = CACHE_DIR / "tables"
COVERAGE_PATH = DATA_DIR / "_labs" / "efv5" / "tracking_coverage.json"
MODEL_PATH = ROOT / "model" / "stuff_plus_aaa.joblib"

PROBE_SEASONS = (2019, 2021, 2022, 2023, 2024, 2025, 2026)
SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)     # served, per the probe
WINDOW = ((3, 15), (10, 10))                      # month-day span asked per season
THROTTLE_S = 1.0
WORKERS = 3                                       # spec ceiling is 4
MAX_TRIES = 6
BACKOFF_S = 15.0
BLACKOUT_UTC = (6, 11)                            # [start, end) hours, no requests

SAVANT_DAY = ("https://baseballsavant.mlb.com/statcast-search-minors/csv?all=true"
              "&hfPT=&hfAB=&hfBBT=&hfPR=&hfZ=&stadium=&hfBBL=&hfNewZones="
              "&hfGT=R%7C&hfC=&hfSea={season}%7C&hfSit=&player_type=pitcher"
              "&hfOuts=&opponent=&pitcher_throws=&batter_stands=&hfSA="
              "&game_date_gt={day}&game_date_lt={day}&hfInfield=&team=&position="
              "&hfOutfield=&hfRO=&home_road=&hfFlag=&hfPull=&metric_1=&hfInn="
              "&min_pitches=0&min_results=0&group_by=name&sort_col=pitches"
              "&player_event_sort=api_p_release_speed&sort_order=desc&min_pas=0"
              "&type=details&minors=true")
SCHEDULE = ("https://statsapi.mlb.com/api/v1/schedule?sportId={sport}"
            "&season={season}&gameType=R&fields=dates,games,gamePk")
SPORT_LEVEL = {11: "AAA", 12: "AA", 13: "A+", 14: "A"}

KEEP = ("pitch_type", "game_date", "release_speed", "release_pos_x",
        "release_pos_z", "batter", "pitcher", "events", "description", "zone",
        "stand", "p_throws", "home_team", "away_team", "type", "bb_type",
        "balls", "strikes", "pfx_x", "pfx_z", "plate_x", "plate_z", "vx0",
        "vy0", "vz0", "ax", "ay", "az", "sz_top", "sz_bot", "hit_distance_sc",
        "launch_speed", "launch_angle", "effective_speed", "release_spin_rate",
        "release_extension", "game_pk", "release_pos_y",
        "estimated_ba_using_speedangle", "estimated_woba_using_speedangle",
        "woba_value", "woba_denom", "launch_speed_angle", "at_bat_number",
        "pitch_number", "inning", "inning_topbot", "outs_when_up", "spin_axis",
        "delta_run_exp", "bat_speed", "swing_length", "age_pit", "age_bat",
        "n_thruorder_pitcher", "arm_angle", "api_break_z_with_gravity",
        "api_break_x_arm", "game_year")

SWING = frozenset({"swinging_strike", "swinging_strike_blocked", "foul_tip",
                   "foul", "foul_bunt", "missed_bunt", "bunt_foul_tip",
                   "hit_into_play"})
WHIFF = frozenset({"swinging_strike", "swinging_strike_blocked", "foul_tip",
                   "missed_bunt"})
CALLED = frozenset({"called_strike"})
FASTBALLS = ("FF", "SI", "FT", "FA")
PITCH_CLASS = {"FF": "fb", "SI": "fb", "FT": "fb", "FA": "fb", "FC": "fb",
               "SL": "br", "ST": "br", "SV": "br", "CU": "br", "KC": "br",
               "CS": "br", "SC": "os", "CH": "os", "FS": "os", "FO": "os",
               "EP": "os", "KN": "os"}
K_EVENTS = frozenset({"strikeout", "strikeout_double_play"})
BB_EVENTS = frozenset({"walk", "intent_walk"})
HARD_HIT_MPH = 95.0
SWEET_SPOT = (8.0, 32.0)

_lock = threading.Lock()
_last = [0.0]


# ---------------------------------------------------------------- fetch
def in_blackout(now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return BLACKOUT_UTC[0] <= now.hour < BLACKOUT_UTC[1]


def _throttle() -> None:
    with _lock:
        wait = THROTTLE_S - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()


def _urlopen(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def http_get(url: str, *, opener=None, sleep=time.sleep, timeout: int = 180) -> bytes:
    """One polite GET: blackout refused, throttled, retried with exponential
    back-off on 429, 5xx and transport errors; other HTTP errors raise."""
    opener = opener or _urlopen
    for k in range(MAX_TRIES):
        if in_blackout():
            raise RuntimeError("06:00 to 11:00 UTC fetch window: no requests")
        _throttle()
        try:
            return opener(url, timeout)
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500:
                raise
            why = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            why = str(e)[:80]
        delay = BACKOFF_S * (2 ** k)
        log.warning("retry %d after %s (%.0f s): %s", k + 1, why, delay, url[-60:])
        sleep(delay)
    raise RuntimeError(f"gave up after {MAX_TRIES} tries: {url[-80:]}")


def season_days(season: int) -> list[date]:
    (m0, d0), (m1, d1) = WINDOW
    d, end = date(season, m0, d0), date(season, m1, d1)
    out = []
    while d <= end:
        out.append(d)
        d += timedelta(days=1)
    return out


def day_paths(day: date) -> tuple[Path, Path]:
    base = DAYS_DIR / str(day.year) / day.isoformat()
    return base.with_suffix(".csv.gz"), base.with_suffix(".empty")


def fetch_day(day: date, *, getter=None) -> tuple[str, int]:
    """('cached'|'fetched'|'empty', rows). A cached day is never refetched."""
    gz, empty = day_paths(day)
    if gz.exists() or empty.exists():
        return "cached", -1
    url = SAVANT_DAY.format(season=day.year, day=day.isoformat())
    raw = (getter or http_get)(url)
    text = raw.decode("utf-8-sig", "replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    if rows and "pitch_type" not in rows[0]:
        raise RuntimeError(f"unexpected Savant shape on {day}: {list(rows[0])[:5]}")
    gz.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        empty.write_text("0\n", encoding="utf-8")
        return "empty", 0
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=KEEP, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in KEEP})
    tmp = gz.with_name(gz.name + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", newline="") as fh:
        fh.write(buf.getvalue())
    tmp.replace(gz)
    return "fetched", len(rows)


def fetch_schedule(season: int, *, getter=None) -> dict[str, str]:
    """{game_pk: level} for every regular-season game of the four MiLB levels."""
    path = SCHED_DIR / f"{season}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for sport, level in SPORT_LEVEL.items():
        raw = (getter or http_get)(SCHEDULE.format(sport=sport, season=season))
        for d in json.loads(raw).get("dates") or []:
            for g in d.get("games") or []:
                out[str(g["gamePk"])] = level
    SCHED_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return out


def probe_day(season: int) -> date:
    d = date(season, 6, 15)
    return d - timedelta(days=(d.weekday() - 2) % 7)


def probe(seasons=PROBE_SEASONS, *, getter=None) -> list[dict]:
    """One mid-June Wednesday per season (the Wednesday on or before June 15;
    Monday is the minors' off day), nothing cached: rows and home parks."""
    out = []
    for s in seasons:
        day = probe_day(s)
        text = (getter or http_get)(SAVANT_DAY.format(season=s, day=day.isoformat())
                                    ).decode("utf-8-sig", "replace")
        rows = list(csv.DictReader(io.StringIO(text)))
        parks = sorted({r.get("home_team") or "" for r in rows} - {""})
        out.append({"season": s, "day": day.isoformat(), "rows": len(rows),
                    "home_parks": parks})
        log.info("probe %s: %d rows, parks %s", day, len(rows), parks)
    return out


def fetch_all(seasons=SEASONS, workers: int = WORKERS) -> dict:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    counts = {"cached": 0, "fetched": 0, "empty": 0, "failed": 0, "rows": 0}
    for s in seasons:
        fetch_schedule(s)
    todo = [d for s in seasons for d in season_days(s)
            if not any(p.exists() for p in day_paths(d))]
    log.info("days to fetch: %d", len(todo))
    with ThreadPoolExecutor(max_workers=min(workers, 4)) as ex:
        futs = {ex.submit(fetch_day, d): d for d in todo}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                st, n = f.result()
                counts[st] += 1
                counts["rows"] += max(n, 0)
            except Exception as e:                        # noqa: BLE001
                counts["failed"] += 1
                log.warning("day %s failed: %s", futs[f], e)
            if i % 25 == 0:
                log.info("%d / %d days, %s", i, len(todo), counts)
    return counts


# ---------------------------------------------------------------- load
def load_season(season: int):
    import pandas as pd
    files = sorted((DAYS_DIR / str(season)).glob("*.csv.gz"))
    if not files:
        return pd.DataFrame(columns=list(KEEP) + ["level"])
    df = pd.concat([pd.read_csv(f, low_memory=False) for f in files],
                   ignore_index=True)
    sched = fetch_schedule(season)
    df["level"] = df["game_pk"].astype("Int64").astype(str).map(sched).fillna("UNK")
    return df


# ---------------------------------------------------------------- metrics
def annotate(df):
    """Per-pitch flags every table reads. Pure; no I/O."""
    import numpy as np
    d = df.copy()
    desc = d["description"].fillna("")
    d["is_swing"] = desc.isin(SWING)
    d["is_whiff"] = desc.isin(WHIFF)
    d["is_called"] = desc.isin(CALLED)
    d["tracked"] = d["release_speed"].notna() & d["plate_x"].notna()
    z = pd_num(d["zone"])
    d["in_zone"] = d["tracked"] & z.between(1, 9)
    d["out_zone"] = d["tracked"] & z.between(11, 14)
    ls = pd_num(d["launch_speed"])
    d["is_bbe"] = (d["type"] == "X") & ls.notna()
    d["pclass"] = d["pitch_type"].map(PITCH_CLASS).fillna("")
    sign = np.where(d["p_throws"] == "L", 1.0, -1.0)     # arm side positive
    d["ivb_in"] = pd_num(d["pfx_z"]) * 12.0
    d["hb_arm_in"] = pd_num(d["pfx_x"]) * 12.0 * sign
    ev = d["events"].fillna("")
    d["pa_end"] = ev != ""
    d["is_k"] = ev.isin(K_EVENTS)
    d["is_bb"] = ev.isin(BB_EVENTS)
    # xwOBA numerator per PA-ending tracked pitch
    wd = pd_num(d["woba_denom"]).fillna(0.0)
    xw = pd_num(d["estimated_woba_using_speedangle"])
    wv = pd_num(d["woba_value"]).fillna(0.0)
    bip = d["type"] == "X"
    use = d["pa_end"] & d["tracked"] & (wd > 0) & (~bip | xw.notna())
    d["xw_num"] = np.where(use, np.where(bip, xw.fillna(0.0), wv), 0.0)
    d["xw_den"] = np.where(use, wd, 0.0)
    return d


def pd_num(s):
    import pandas as pd
    return pd.to_numeric(s, errors="coerce")


def _rate(num, den, nd=4):
    return round(float(num) / float(den), nd) if den else None


def _q(s, q):
    s = s.dropna()
    return round(float(s.quantile(q)), 2) if len(s) else None


def _mean(s, nd=2):
    s = s.dropna()
    return round(float(s.mean()), nd) if len(s) else None


def _common(g, side: str) -> dict:
    n = len(g)
    sw = int(g["is_swing"].sum())
    wh = int(g["is_whiff"].sum())
    oz = g["out_zone"]
    iz = g["in_zone"]
    zsw = int((iz & g["is_swing"]).sum())
    zwh = int((iz & g["is_whiff"]).sum())
    tr = int(g["tracked"].sum())
    pa = int(g["pa_end"].sum())
    bbe = g[g["is_bbe"]]
    ev = pd_num(bbe["launch_speed"])
    return {
        "pitches": n, "tracked_pitches": tr, "pa": pa, "bbe": int(len(bbe)),
        "games": int(g["game_pk"].nunique()),
        "csw": _rate(int(g["is_called"].sum()) + wh, n),
        "swstr": _rate(wh, n),
        "whiff": _rate(wh, sw),
        "zone": _rate(int(iz.sum()), tr),
        "chase": _rate(int((oz & g["is_swing"]).sum()), int(oz.sum())),
        "zone_contact": _rate(zsw - zwh, zsw),
        "k_pct": _rate(int(g["is_k"].sum()), pa),
        "bb_pct": _rate(int(g["is_bb"].sum()), pa),
        "xwoba": _rate(float(g["xw_num"].sum()), float(g["xw_den"].sum()), 3),
        "xwoba_pa": int(round(float(g["xw_den"].sum()))),
        "ev": _mean(ev, 1),
    }


def pitcher_rows(df) -> list[dict]:
    """One row per (pitcher, season, level) from annotated pitches."""
    out = []
    for (pid, season, level), g in df.groupby(["pitcher", "game_year", "level"]):
        row = {"mlbam": int(pid), "season": int(season), "level": level,
               "p_throws": g["p_throws"].mode().iat[0] if g["p_throws"].notna().any() else None,
               "age": int(pd_num(g["age_pit"]).mode().iat[0]) if pd_num(g["age_pit"]).notna().any() else None}
        row.update(_common(g, "pitcher"))
        row["ev_against"] = row.pop("ev")
        row["xwoba_against"] = row.pop("xwoba")
        row["k_minus_bb"] = (round(row["k_pct"] - row["bb_pct"], 4)
                             if row["k_pct"] is not None and row["bb_pct"] is not None else None)
        t = g[g["tracked"]]
        fb = t[t["pitch_type"].isin(FASTBALLS)]
        velo = pd_num(fb["release_speed"])
        row["fb_velo_mean"] = _mean(velo, 2)
        row["fb_velo_p95"] = _q(velo, 0.95)
        if len(fb):
            primary = fb["pitch_type"].value_counts().idxmax()
            pf = fb[fb["pitch_type"] == primary]
            row["fb_primary"] = primary
            row["fb_ivb"] = _mean(pf["ivb_in"], 2)
            row["fb_hb_arm"] = _mean(pf["hb_arm_in"], 2)
        else:
            row["fb_primary"] = row["fb_ivb"] = row["fb_hb_arm"] = None
        row["extension"] = _mean(pd_num(t["release_extension"]), 2)
        row["arm_angle"] = _mean(pd_num(t["arm_angle"]), 1)
        bbt = g[g["type"] == "X"]["bb_type"].dropna()
        row["gb"] = _rate(int((bbt == "ground_ball").sum()), len(bbt))
        for cls in ("fb", "br", "os"):
            c = g[g["pclass"] == cls]
            row[f"whiff_{cls}"] = _rate(int(c["is_whiff"].sum()), int(c["is_swing"].sum()))
            row[f"share_{cls}"] = _rate(len(c), len(g), 3)
        out.append(row)
    return out


def hitter_rows(df) -> list[dict]:
    """One row per (batter, season, level) from annotated pitches."""
    out = []
    for (bid, season, level), g in df.groupby(["batter", "game_year", "level"]):
        row = {"mlbam": int(bid), "season": int(season), "level": level,
               "stand": g["stand"].mode().iat[0] if g["stand"].notna().any() else None,
               "age": int(pd_num(g["age_bat"]).mode().iat[0]) if pd_num(g["age_bat"]).notna().any() else None}
        row.update(_common(g, "hitter"))
        bbe = g[g["is_bbe"]]
        ev = pd_num(bbe["launch_speed"])
        la = pd_num(bbe["launch_angle"])
        row["ev_mean"] = row.pop("ev")
        row["ev_p90"] = _q(ev, 0.90)
        row["ev_max"] = round(float(ev.max()), 1) if len(ev) else None
        row["hard_hit"] = _rate(int((ev >= HARD_HIT_MPH).sum()), len(ev))
        row["barrel"] = _rate(int((pd_num(bbe["launch_speed_angle"]) == 6).sum()), len(ev))
        row["la_sd"] = round(float(la.std(ddof=1)), 2) if la.notna().sum() >= 2 else None
        row["sweet_spot"] = _rate(int(la.between(*SWEET_SPOT).sum()), int(la.notna().sum()))
        bs = pd_num(g["bat_speed"]).dropna()
        row["bat_speed"] = round(float(bs.mean()), 1) if len(bs) else None
        out.append(row)
    return out


# ---------------------------------------------------------------- aStuff+
def astuff_features(df):
    """The stuff_plus_aaa feature matrix for every tracked pitch of df, built as
    stuff_plus_aaa._featurize builds it, primary velo = the pitcher's top velo
    within (pitcher, season, level). Returns (mask, X)."""
    import numpy as np
    velo = pd_num(df["release_speed"])
    mask = velo.notna().to_numpy()
    prim = velo.groupby([df["pitcher"], df["game_year"], df["level"]]).transform("max")
    throws_r = (df["p_throws"].fillna("R") == "R").to_numpy().astype(float)
    sign = np.where(throws_r == 1.0, 1.0, -1.0)

    def col(c, default):
        # stuff_plus_aaa._featurize reads `_f(v) or default`, so a stored 0.0
        # takes the default too (matters for extension, release height, arm angle)
        v = pd_num(df[c]).fillna(default)
        return v.mask(v == 0.0, default).to_numpy(dtype=float)

    X = np.column_stack([
        velo.fillna(0.0).to_numpy(dtype=float),
        col("release_spin_rate", 0.0),
        col("release_extension", 6.0),
        col("pfx_x", 0.0) * sign,
        col("pfx_z", 0.0),
        col("release_pos_x", 0.0) * sign,
        col("release_pos_z", 5.5),
        col("arm_angle", 30.0),
        (prim - velo).fillna(0.0).to_numpy(dtype=float),
        throws_r,
    ])
    return mask, X[mask]


def astuff_xrv(df, model=None):
    """Predicted delta_run_exp per pitch (NaN where release speed is missing)."""
    import numpy as np
    if model is None:
        import joblib
        model = joblib.load(MODEL_PATH)["model"]
    out = np.full(len(df), np.nan)
    mask, X = astuff_features(df)
    if len(X):
        import warnings
        with warnings.catch_warnings():    # the bundle was fit on unnamed columns
            warnings.simplefilter("ignore", UserWarning)
            out[mask] = model.predict(X)
    return out


def served_agreement(rows: list[dict], path: Path | None = None) -> dict:
    """Cross-check, read only: this table's AAA aStuff+ against the served
    sidecar (data/stuff_plus_aaa.json) on the pitcher-seasons both score."""
    import numpy as np
    path = path or DATA_DIR / "stuff_plus_aaa.json"
    try:
        served = json.loads(path.read_text(encoding="utf-8"))["players"]
    except (OSError, ValueError, KeyError):
        return {"n": 0, "r": None}
    pairs = []
    for r in rows:
        s = served.get(str(r["mlbam"]))
        if (s and r["level"] == "AAA" and s.get("season") == r["season"]
                and r.get("astuff_plus") is not None):
            pairs.append((r["astuff_plus"], s["stuff_plus"]))
    if len(pairs) < 20:
        return {"n": len(pairs), "r": None}
    a, b = np.array(pairs).T
    return {"n": len(pairs), "r": round(float(np.corrcoef(a, b)[0, 1]), 4),
            "mean_gap": round(float(np.mean(a - b)), 2),
            "note": "same model, same shrink and scale; rows differ in pitch set "
                    "(this cache is game-complete, the sidecar fetches per pitcher)"}


def astuff_scale(rows: list[dict], pool_season: int = 2025, pool_level: str = "AAA") -> dict:
    """Put pitcher rows' mean predicted RV on 100 + 10z (the served convention)."""
    import numpy as np
    import stuff_plus_aaa as sp
    k, floor = sp.SHRINK_K, sp.MIN_POOL_PITCHES
    pool = [(r["xrv_mean"], r["xrv_n"]) for r in rows
            if r.get("season") == pool_season and r.get("level") == pool_level
            and r.get("xrv_n", 0) >= floor and r.get("xrv_mean") is not None]
    if len(pool) < 20:
        return {"pool_n": len(pool), "mu": None, "sd": None}
    mu = float(np.mean([v for v, _n in pool]))
    sd = float(np.std([(v * n + mu * k) / (n + k) for v, n in pool])) or 1.0
    for r in rows:
        for key, nkey, out in (("xrv_mean", "xrv_n", "astuff_plus"),
                               ("xrv_fb", "xrv_fb_n", "astuff_plus_fb"),
                               ("xrv_br", "xrv_br_n", "astuff_plus_br"),
                               ("xrv_os", "xrv_os_n", "astuff_plus_os")):
            v, n = r.get(key), r.get(nkey) or 0
            if v is None or not n:
                r[out] = None
                continue
            shr = (v * n + mu * k) / (n + k)
            r[out] = round(100 + 10 * (mu - shr) / sd, 1)
    return {"pool_n": len(pool), "mu": round(mu, 6), "sd": round(sd, 6),
            "pool": f"{pool_level} {pool_season} pitcher-season-levels with >= {floor} "
                    f"scored pitches, shrink k={k}, z on the shrunk pool spread"}


def _attach_xrv(rows: list[dict], df) -> None:
    import numpy as np
    keyed = {(r["mlbam"], r["season"], r["level"]): r for r in rows}
    sub = df[df["xrv"].notna()]
    for (pid, season, level), g in sub.groupby(["pitcher", "game_year", "level"]):
        r = keyed.get((int(pid), int(season), level))
        if r is None:
            continue
        r["xrv_mean"], r["xrv_n"] = float(np.mean(g["xrv"])), int(len(g))
        for cls in ("fb", "br", "os"):
            c = g[g["pclass"] == cls]
            r[f"xrv_{cls}"] = float(np.mean(c["xrv"])) if len(c) else None
            r[f"xrv_{cls}_n"] = int(len(c))


# ---------------------------------------------------------------- build
FIELD_CHECK = ("release_speed", "pfx_z", "plate_x", "release_extension",
               "release_spin_rate", "arm_angle", "launch_speed",
               "estimated_woba_using_speedangle", "bat_speed", "delta_run_exp")


def _write_table(rows: list[dict], name: str) -> Path:
    import pandas as pd
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    path = TABLE_DIR / f"{name}.csv.gz"
    tmp = path.with_name(path.name + ".tmp")
    pd.DataFrame(rows).to_csv(tmp, index=False, compression="gzip")
    tmp.replace(path)
    return path


def load_table(side: str):
    """The built per player-season-level table ('pitcher' or 'hitter')."""
    import pandas as pd
    return pd.read_csv(TABLE_DIR / f"{side}_season_level.csv.gz")


def build(seasons=SEASONS, probes: list[dict] | None = None) -> dict:
    import joblib
    model = joblib.load(MODEL_PATH)["model"]
    meta = joblib.load(MODEL_PATH)["meta"]
    prow, hrow, cells, fields, parks = [], [], [], {}, {}
    for s in seasons:
        df = load_season(s)
        if not len(df):
            continue
        df = annotate(df)
        df["xrv"] = astuff_xrv(df, model)
        fields[str(s)] = {c: round(float(pd_num(df[c]).notna().mean()), 3)
                          for c in FIELD_CHECK}
        # the day request must stay under the search's row cap: the largest
        # day is recorded so a capped (truncated) day would show
        fields[str(s)]["max_pitches_one_day"] = int(df.groupby("game_date").size().max())
        fields[str(s)]["pitches_level_unmapped"] = int((df["level"] == "UNK").sum())
        pr = pitcher_rows(df)
        _attach_xrv(pr, df)
        hr = hitter_rows(df)
        prow += pr
        hrow += hr
        for level, g in df.groupby("level"):
            parks[f"{s}|{level}"] = sorted(g["home_team"].dropna().unique().tolist())
            gd = g["game_date"].astype(str)
            for side, rows, key, q in (("pitcher", pr, "pitches", 100),
                                       ("hitter", hr, "pa", 50)):
                rr = [r for r in rows if r["level"] == level]
                cells.append({
                    "season": int(s), "level": level, "side": side,
                    "rows": len(rr),
                    "rows_qualified": sum(1 for r in rr if (r.get(key) or 0) >= q),
                    "qualified_rule": f"{key} >= {q}",
                    "pitches": int(len(g)),
                    "tracked_pitches": int(g["tracked"].sum()),
                    "games": int(g["game_pk"].nunique()),
                    "parks": len(parks[f"{s}|{level}"]),
                    "first_date": gd.min(), "last_date": gd.max()})
        log.info("season %s: %d pitches, %d pitcher rows, %d hitter rows",
                 s, len(df), len(pr), len(hr))
        del df
    scale = astuff_scale(prow)
    scale["served_agreement"] = served_agreement(prow)
    for r in prow:
        for k in ("xrv_mean", "xrv_fb", "xrv_br", "xrv_os"):
            if r.get(k) is not None:
                r[k] = round(r[k], 5)
    _write_table(prow, "pitcher_season_level")
    _write_table(hrow, "hitter_season_level")
    cov = coverage_payload(cells, fields, parks, scale, meta, probes)
    write_coverage(cov)
    return cov


PITCHER_METRICS = ("fb_velo_p95", "fb_velo_mean", "fb_ivb", "fb_hb_arm",
                   "extension", "arm_angle", "csw", "swstr", "whiff", "whiff_fb",
                   "whiff_br", "whiff_os", "zone", "chase", "zone_contact",
                   "xwoba_against", "ev_against", "gb", "k_pct", "bb_pct",
                   "k_minus_bb", "astuff_plus", "astuff_plus_fb",
                   "astuff_plus_br", "astuff_plus_os")
HITTER_METRICS = ("ev_mean", "ev_p90", "ev_max", "hard_hit", "barrel", "la_sd",
                  "sweet_spot", "chase", "zone_contact", "whiff", "swstr",
                  "xwoba", "k_pct", "bb_pct", "bat_speed")


def coverage_summary(cells: list[dict], probes: list[dict] | None) -> str:
    """Derived from the fetched cells and the probes, never typed."""
    by: dict[int, set] = {}
    for c in cells:
        if c["pitches"] > 0 and c["level"] != "UNK":
            by.setdefault(c["season"], set()).add(c["level"])
    order = ["AAA", "AA", "A+", "A"]
    parts = [f"{p['season']}: nothing served (probe {p['day']})"
             for p in (probes or []) if p["rows"] == 0 and p["season"] not in by]
    parts += [f"{s}: " + ", ".join(lv for lv in order if lv in by[s])
              for s in sorted(by)]
    never = [lv for lv in order if not any(lv in v for v in by.values())]
    if never:
        parts.append("never served: " + ", ".join(never))
    return "; ".join(parts) + "; 2020 had no MiLB season"


def _bat_speed_note(fields: dict) -> str:
    """Derived from the per-season field shares, never typed."""
    got = {s: f.get("bat_speed") or 0.0 for s, f in sorted(fields.items())}
    if not any(got.values()):
        return "column requested but empty for every fetched pitch, every season"
    return ("served on part of the pitches, share by season: "
            + ", ".join(f"{s} {v}" for s, v in got.items())
            + "; the hitter table's bat_speed is the mean over served swings")


def coverage_payload(cells, fields, parks, scale, meta, probes) -> dict:
    cells = sorted(cells, key=lambda c: (c["season"], c["level"], c["side"]))
    return {
        "generated_at": date.today().isoformat(),
        "task": "EFV5_TRACKING_FETCH (owner 2026-10-14, EW3-1 to EW3-5)",
        "role": "development input census; adjudicates nothing, feeds no served number",
        "source": "Baseball Savant statcast-search-minors, type=details, "
                  "regular season, one request per calendar day",
        "levels_from": "StatsAPI schedule game_pk to sportId (11 AAA, 12 AA, 13 A+, 14 A)",
        "verified_coverage": {
            "summary": coverage_summary(cells, probes),
            "probes": probes or [],
        },
        "by_level_season_side": cells,
        "home_parks": parks,
        "season_checks": {"note": "field shares are the share of pitches with a value; max_pitches_one_day and pitches_level_unmapped are counts", "by_season": fields},
        "metrics": {"pitcher": list(PITCHER_METRICS), "hitter": list(HITTER_METRICS)},
        "not_available": {
            "location_plus": "no in-repo Location+ model; not built (a new model fit on outcomes is out of scope)",
            "pitching_plus": "no in-repo Pitching+ model; not built (same reason)",
            "sprint_speed": ("not a column of the pitch-level minors search; no other "
                             "minor-league sprint speed source was probed in this task"),
            "bat_speed": _bat_speed_note(fields),
        },
        "astuff": {
            "model": "stuff_plus_aaa v1, model/stuff_plus_aaa.joblib, applied, never refit",
            "training_data": (f"Savant AAA per-pitch, train seasons {meta.get('train_seasons')}, "
                              f"season-out validation {meta.get('valid_season')}, shipping fit "
                              f"on all three; label delta_run_exp; trained {meta.get('trained_at')}"),
            "cautions": ["AAA 2023 to 2025 pitches are in the model's own training data",
                         "Florida State League pitches are outside the training domain"],
            "scale": scale,
        },
        "tables": {"pitcher": ".cache/efv5_savant_minors/tables/pitcher_season_level.csv.gz",
                   "hitter": ".cache/efv5_savant_minors/tables/hitter_season_level.csv.gz",
                   "committed": False},
    }


def write_coverage(payload: dict, path: Path = COVERAGE_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    do_all = "--all" in sys.argv
    probes = None
    if do_all or "--probe" in sys.argv:
        probes = probe()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / "probe.json").write_text(json.dumps(probes, indent=1), encoding="utf-8")
    if do_all or "--fetch" in sys.argv:
        print("fetch:", fetch_all())
    if do_all or "--build" in sys.argv:
        if probes is None and (CACHE_DIR / "probe.json").exists():
            probes = json.loads((CACHE_DIR / "probe.json").read_text(encoding="utf-8"))
        cov = build(probes=probes)
        for c in cov["by_level_season_side"]:
            print(c)
