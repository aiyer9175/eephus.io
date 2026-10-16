# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""SDR in-house: run Will Cahoon's defense-plus pipeline on public caches.

WHY THIS EXISTS (owner decision EW3-18, 2026-10-15). Will's whole Defense+ method
is in the repo at BaseballR/defense-plus (pipeline/00 to 27, build_defense_card.py),
but its raw inputs lived on his machine: the stages read ~/defense_plus/data/raw/
(fg_field_full_<year>.csv and the Savant leaderboards) and the card writes to
~/swing_plus/. This module is the thin adapter that lets the method run here
WITHOUT EDITING IT:

  fetch    pulls the public inputs the stages read into .cache/sdr/home/
           defense_plus/data/raw/, under the file names Will's code expects, and
           records url, sha256, row count and fetch time per file in
           .cache/sdr/fetch_manifest.json. Polite: one request per second.
  stage    copies one of Will's scripts, byte for byte, into the staging home
           .cache/sdr/home/defense_plus/, applies a DECLARED config patch (the
           season window, the shipped season and the output file names; every
           patch must match exactly once or the run refuses), and runs it in a
           subprocess whose USERPROFILE and HOME point at the staging home, so his
           expanduser("~/...") paths land in the cache and never on a real path.
           The method lines (the blend, the reliability weights, the innings
           shrink 269, the positional adjustment) are never touched; the patch
           list and the sha256 of his original file go into the run manifest.
  drop     maps the per-season cards onto sdr_intake.DEFENSE_CARD_CONTRACT and
           writes data/drops/wills/sdr_defense_card__<date>.csv (gitignored, as
           every drop is; this command rebuilds it byte for byte from the cache).
  milb     builds the two inputs 15_milb_translation reads from his other
           projects (usage_spine.parquet, milb_fielding.parquet) out of the
           cached StatsAPI season fielding lines, then runs the stage unpatched.

THE SEASON WINDOW. 06_total_defense_plus.py ships one season from a trailing
five-season window (YEARS 2021 to 2025, ship 2025). The adapter keeps that
convention per season S: window max(2016, S - 4) to S, ship S. Statcast OAA and
FRP start in 2016, so the first season with a year-to-year pair inside its own
window is 2017; SDR coverage is 2017 to 2026 by that rule, stated in the census.
No season's number reads a later season.

INPUTS NOT REPRODUCIBLE HERE (named, never improvised): ~/projection_engine/data/
deep_mlb.parquet (ages), ~/mlb-aging-curves/bayesian_curves.py (his Bayesian
aging fitter), ~/playing_time_model/data/processed/grades_long.parquet (his
scouting-grade snapshots), defense_plus/data/raw/body.parquet and the Savant
jump and directional files. The stages that need them (07 to 13, 16 to 25 aging
and career parts, 26, 27) are inventoried in docs/sdr-2026-08-18/
SDR_INHOUSE_RUNBOOK.md and not run.

Usage:
    python tools/sdr_inhouse.py fetch
    python tools/sdr_inhouse.py stages            # 06 per season, card per season, LOO variants
    python tools/sdr_inhouse.py milb              # 15_milb_translation
    python tools/sdr_inhouse.py drop              # the contract drop for sdr_intake
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
WILL = REPO / "defense-plus"
SDR_CACHE = Path(os.environ.get("SDR_CACHE_DIR") or (ROOT / ".cache" / "sdr"))
HOME_STAGE = SDR_CACHE / "home"
DP_HOME = HOME_STAGE / "defense_plus"
RAW = DP_HOME / "data" / "raw"
REPORTS = DP_HOME / "reports"
LOGS = SDR_CACHE / "logs"
FETCH_MANIFEST = SDR_CACHE / "fetch_manifest.json"
RUN_MANIFEST = SDR_CACHE / "run_manifest.json"
STATSAPI_MLB = ROOT / ".cache" / "statsapi_field"
STATSAPI_MILB = ROOT / ".cache" / "statsapi_field_season"
DROPS_DIR = ROOT / "data" / "drops" / "wills"

FIRST_STATCAST = 2016
COVERAGE = tuple(range(2017, 2027))         # seasons SDR is shipped for
FETCH_SEASONS = tuple(range(2016, 2027))
WINDOW = 5                                    # Will's trailing window length
MIN_INTERVAL_S = 1.0

FG_URL = "https://www.fangraphs.com/api/leaders/major-league/data"
# Will's own Savant header (01_reliability.py); FanGraphs gets the library
# default User-Agent, the transport rule fg_leaderboards.py measured.
SAVANT_HDRS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# Variants of 06 for the leave-one-source-out cell of the amended estimand
# (EBR_GATE.md 11.2.2): the full blend, the blend without DRS, and the blend
# without the Statcast system (OAA and FRP are one system). The removed system's
# weight in blend() is set to 0; TOT itself stays whole because 06's own
# diagnostic block indexes every system's z column (a first attempt that
# shortened TOT crashed there, 2026-10-15).
TOT_VARIANTS = {
    "full": None,
    "no_drs": '["OAA", "FRP"]',
    "no_statcast": '["DRS"]',
}
BLEND_WEIGHT_LINE = "    w = {c: max(rel[c], 0.05) for c in TOT}"

_last = [0.0]


def _throttle() -> None:
    wait = MIN_INTERVAL_S - (time.monotonic() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.monotonic()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _load_manifest(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def _save_manifest(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------

def fg_params(season: int, stats: str = "fld", team: str = "0") -> dict:
    """The fielding leaderboard request Will's 02 stage makes (and that
    fg_leaderboards.request_for makes), with the team switch: '0' one row per
    player-position across clubs (his convention), '0,to' split by club,
    '0,ts' club totals."""
    return {
        "age": "", "pos": "all", "stats": stats, "lg": "all", "qual": 0,
        "season": season, "season1": season, "startdate": "", "enddate": "",
        "month": 0, "hand": "", "team": team, "pageitems": 5000, "pagenum": 1,
        "ind": 0, "rost": 0, "players": "", "type": 8, "postseason": "",
        "sortdir": "default", "sortstat": "Defense" if stats == "fld" else "WAR",
    }


def _get(url: str, params: dict | None = None, headers: dict | None = None):
    import requests                                  # noqa: PLC0415
    _throttle()
    r = requests.get(url, params=params, headers=headers, timeout=120)
    r.raise_for_status()
    return r


def fetch_fg(season: int, kind: str, man: dict, force: bool = False) -> None:
    """kind: 'full' (Will's fg_field_full), 'split' (by club), 'team_pit'."""
    import pandas as pd                              # noqa: PLC0415
    names = {"full": f"fg_field_full_{season}.csv",
             "split": f"fg_field_split_{season}.csv",
             "team_pit": f"fg_team_pit_{season}.csv"}
    out = RAW / names[kind]
    if out.exists() and not force and names[kind] in man:
        return
    params = {"full": fg_params(season), "split": fg_params(season, team="0,to"),
              "team_pit": fg_params(season, stats="pit", team="0,ts")}[kind]
    r = _get(FG_URL, params=params)
    body = r.content
    j = r.json()
    rows = j["data"] if isinstance(j, dict) and "data" in j else j
    total = j.get("totalCount") if isinstance(j, dict) else None
    if total is not None and int(total) != len(rows):
        raise RuntimeError(f"FG {kind} {season}: {len(rows)} rows of totalCount {total}")
    df = pd.DataFrame(rows)
    if "Season" in df.columns and kind != "team_pit":
        bad = (pd.to_numeric(df["Season"], errors="coerce") != season).sum()
        if bad:
            raise RuntimeError(f"FG {kind} {season}: {bad} rows from another season")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    man[names[kind]] = {"url": r.url, "raw_sha256": _sha(body), "rows": len(df),
                        "fetched_at": _now(), "source": "FanGraphs leaderboard JSON"}


SAVANT = {
    # stem: (url template, first season, Will's stage that reads it)
    "oaa_if": ("https://baseballsavant.mlb.com/leaderboard/outs_above_average?type=Fielder"
               "&startYear={y}&endYear={y}&split=no&team=&range=year&min=q&pos=if"
               "&roles=&viz=show&csv=true", 2016, "01"),
    "oaa_of": ("https://baseballsavant.mlb.com/leaderboard/outs_above_average?type=Fielder"
               "&startYear={y}&endYear={y}&split=no&team=&range=year&min=q&pos=of"
               "&roles=&viz=show&csv=true", 2016, "01"),
    "poptime": ("https://baseballsavant.mlb.com/leaderboard/poptime?year={y}"
                "&team=&min2b=5&min3b=0&csv=true", 2016, "01, 05, 25"),
    "arm": ("https://baseballsavant.mlb.com/leaderboard/arm-strength?type=player"
            "&year={y}&minThrows=50&csv=true", 2020, "01, 05, 19, 27"),
    # Will's 25 asks catcher-blocking?year={y}; the CSV ignores 'year' and
    # returns the CURRENT season for every year (measured 2026-10-15: every
    # file came back start_year 2026). The season_start/season_end form is
    # year-sensitive; fetch_savant refuses a file whose start_year is wrong.
    "blocking": ("https://baseballsavant.mlb.com/leaderboard/catcher-blocking?game_type=Regular"
                 "&n=q&season_end={y}&season_start={y}&split=no&team=&type=Cat"
                 "&with_team_only=1&csv=true", 2018, "25"),
    "framing": ("https://baseballsavant.mlb.com/catcher_framing?year={y}&team=&min=q&type=catcher",
                2016, "01, 05, 25"),
}


def fetch_savant(stem: str, season: int, man: dict, force: bool = False) -> None:
    import pandas as pd                              # noqa: PLC0415
    from io import StringIO                          # noqa: PLC0415
    tmpl, first, _ = SAVANT[stem]
    if season < first:
        return
    name = (f"oaa_{stem[4:]}_{season}.csv" if stem.startswith("oaa_")
            else f"{stem}_{season}.csv")
    out = RAW / name
    if out.exists() and not force and name in man:
        return
    url = tmpl.format(y=season)
    r = _get(url, headers=SAVANT_HDRS)
    body = r.content
    if stem == "framing":
        # Will's 01 parser: the year-sensitive page embeds the grid as data = [...]
        m = re.search(r"\bdata\s*=\s*(\[\{.*?\}\])\s*;", r.text, re.DOTALL)
        if not m:
            raise RuntimeError(f"framing {season}: no data grid in the page")
        df = pd.DataFrame(json.loads(m.group(1)))
        keep = [c for c in ("id", "name", "rv_tot", "pct_tot", "pitches") if c in df.columns]
        df = df[keep]
    else:
        df = pd.read_csv(StringIO(r.text))
    if not len(df):
        raise RuntimeError(f"savant {stem} {season}: empty")
    if "start_year" in df.columns:
        yrs = set(pd.to_numeric(df["start_year"], errors="coerce").dropna().astype(int))
        if yrs != {season}:
            raise RuntimeError(f"savant {stem} {season}: rows from seasons {sorted(yrs)}")
    df.to_csv(out, index=False)
    man[name] = {"url": url, "raw_sha256": _sha(body), "rows": len(df),
                 "fetched_at": _now(), "source": "Baseball Savant leaderboard"}


def cmd_fetch(force: bool = False, seasons=FETCH_SEASONS) -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    man = _load_manifest(FETCH_MANIFEST)
    failures = []
    for y in seasons:
        for kind in ("full", "split", "team_pit"):
            try:
                fetch_fg(y, kind, man, force)
            except Exception as exc:                 # noqa: BLE001
                failures.append(f"fg {kind} {y}: {exc}")
            _save_manifest(FETCH_MANIFEST, man)
        for stem in SAVANT:
            try:
                fetch_savant(stem, y, man, force)
            except Exception as exc:                 # noqa: BLE001
                failures.append(f"savant {stem} {y}: {exc}")
            _save_manifest(FETCH_MANIFEST, man)
    man["_failures"] = failures
    _save_manifest(FETCH_MANIFEST, man)
    return {"files": len([k for k in man if not k.startswith("_")]), "failures": failures}


# ---------------------------------------------------------------------------
# stage runner: Will's file, copied, config-patched, run under a staged home
# ---------------------------------------------------------------------------

def window(season: int) -> tuple[int, int]:
    return max(FIRST_STATCAST, season - (WINDOW - 1)), season


def patches_06(season: int, variant: str = "full") -> list[tuple[str, str]]:
    lo, hi = window(season)
    sfx = "" if variant == "full" else f"__{variant}"
    p = [
        ("YEARS = list(range(2021, 2026))", f"YEARS = list(range({lo}, {hi + 1}))"),
        ("cur = F[F.year == 2025].copy()", f"cur = F[F.year == {season}].copy()"),
        ('"06_defense_plus_2025.csv"', f'"06_defense_plus_{season}{sfx}.csv"'),
        ('"06_total_oos.csv"', f'"06_total_oos_{season}{sfx}.csv"'),
    ]
    keep = TOT_VARIANTS[variant]
    if keep is not None:
        p.append((BLEND_WEIGHT_LINE,
                  f"    w = {{c: (max(rel[c], 0.05) if c in {keep} else 0.0) for c in TOT}}"))
    return p


def patches_card(season: int) -> list[tuple[str, str]]:
    return [
        ('"06_defense_plus_2025.csv"', f'"06_defense_plus_{season}.csv"'),
        ('"fg_field_full_2025.csv"', f'"fg_field_full_{season}.csv"'),
        ('"defense_card.parquet"', f'"defense_card_{season}.parquet"'),
    ]


def apply_patches(src: str, patches: list[tuple[str, str]]) -> str:
    """Apply each (old, new) exactly once. A patch that matches zero or several
    times means Will's file changed under us: refuse, never guess."""
    out = src
    for old, new in patches:
        n = out.count(old)
        if n != 1:
            raise RuntimeError(f"patch {old!r} matched {n} times (need exactly 1)")
        out = out.replace(old, new)
    return out


def run_stage(rel: str, tag: str, patches: list[tuple[str, str]], man: dict,
              dest_dir: Path | None = None) -> int:
    """Copy WILL/rel into the staged home, patch, run. Returns the exit code."""
    src_path = WILL / rel
    raw = src_path.read_bytes()
    src = raw.decode("utf-8")
    patched = apply_patches(src, patches)
    dest_dir = dest_dir or (DP_HOME / Path(rel).parent)
    dest_dir.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (HOME_STAGE / "swing_plus" / "data" / "processed").mkdir(parents=True, exist_ok=True)
    (DP_HOME / "data" / "processed").mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    run_file = dest_dir / f"{Path(rel).stem}__{tag}.py"
    run_file.write_text(patched, encoding="utf-8", newline="")
    env = dict(os.environ)
    env["USERPROFILE"] = str(HOME_STAGE)
    env["HOME"] = str(HOME_STAGE)
    env["PYTHONIOENCODING"] = "utf-8"
    env["MPLBACKEND"] = "Agg"
    log_path = LOGS / f"{Path(rel).stem}__{tag}.log"
    with open(log_path, "w", encoding="utf-8") as fh:
        proc = subprocess.run([sys.executable, str(run_file)], cwd=str(dest_dir),
                              stdout=fh, stderr=subprocess.STDOUT, env=env)
    man.setdefault("runs", {})[f"{rel}::{tag}"] = {
        "will_file": rel, "will_sha256": _sha(raw), "patches": patches,
        "run_file": str(run_file.relative_to(SDR_CACHE)), "exit": proc.returncode,
        "log": str(log_path.relative_to(SDR_CACHE)), "ran_at": _now(),
    }
    return proc.returncode


def cmd_stages(seasons=COVERAGE, variants=("full", "no_drs", "no_statcast")) -> dict:
    man = _load_manifest(RUN_MANIFEST)
    bad = []
    for v in variants:
        for s in seasons:
            rc = run_stage("pipeline/06_total_defense_plus.py", f"{s}_{v}",
                           patches_06(s, v), man)
            if rc:
                bad.append(f"06 {s} {v} exit {rc}")
            _save_manifest(RUN_MANIFEST, man)
    for s in seasons:
        rc = run_stage("build_defense_card.py", str(s), patches_card(s), man,
                       dest_dir=DP_HOME)
        if rc:
            bad.append(f"card {s} exit {rc}")
        _save_manifest(RUN_MANIFEST, man)
    man["_failures"] = bad
    _save_manifest(RUN_MANIFEST, man)
    return {"failures": bad}


# ---------------------------------------------------------------------------
# 15_milb_translation: inputs from the cached StatsAPI season fielding lines
# ---------------------------------------------------------------------------

POS15 = ["C", "SS", "CF", "2B", "3B", "RF", "LF", "1B", "DH"]


def build_usage_spine():
    """mlbam_id, season, gs_total, gs_<pos>: MLB games started by position per
    player-season, from .cache/statsapi_field/fld_<year>.json (StatsAPI season
    fielding, sportId 1; its lines carry DH games started too, so gs_dh is
    filled from the feed). Will's own spine builder lives in his
    playing_time_model, which is not in the repo, so his cohort count (462 on
    2026-06-18) is not expected to match exactly (disclosed in the artifact)."""
    import pandas as pd                              # noqa: PLC0415
    rows = []
    for p in sorted(STATSAPI_MLB.glob("fld_*.json")):
        m = re.match(r"fld_(\d{4})\.json$", p.name)
        if not m:
            continue
        season = int(m.group(1))
        doc = json.loads(p.read_text(encoding="utf-8"))
        block = (doc.get("stats") or [{}])[0]
        splits = block.get("splits") or []
        if block.get("totalSplits") not in (None, len(splits)):
            raise RuntimeError(f"{p.name}: {len(splits)} of {block.get('totalSplits')} splits")
        for sp in splits:
            pos = (sp.get("position") or {}).get("abbreviation")
            pid = (sp.get("player") or {}).get("id")
            if not pid or not pos or pos == "P":
                continue
            rows.append({"mlbam_id": int(pid), "season": season, "pos": pos,
                         "gs": int((sp.get("stat") or {}).get("gamesStarted") or 0)})
    d = pd.DataFrame(rows)
    piv = d.pivot_table(index=["mlbam_id", "season"], columns="pos", values="gs",
                        aggfunc="sum", fill_value=0)
    piv.columns = [f"gs_{c.lower()}" for c in piv.columns]
    piv["gs_total"] = piv.sum(axis=1)
    return piv.reset_index()


def build_milb_fielding(ids):
    """Will's milb_fielding.parquet cache, one row per mlbam: primary AAA
    position by games started summed over every AAA season (sportId 11), else
    AA (12), else 'none', from .cache/statsapi_field_season/fld_v2_<sport>_<y>.json.
    His stage pulls the same quantity per player from people/{id}/stats
    yearByYear; with every id pre-cached here it makes no request."""
    import pandas as pd                              # noqa: PLC0415
    gs: dict[int, dict[int, dict[str, int]]] = {11: {}, 12: {}}
    for sport in (11, 12):
        for p in sorted(STATSAPI_MILB.glob(f"fld_v2_{sport}_*.json")):
            for r in json.loads(p.read_text(encoding="utf-8")):
                pos = r.get("pos")
                if not pos or pos == "P" or r.get("mlbam") is None:
                    continue
                d = gs[sport].setdefault(int(r["mlbam"]), {})
                d[pos] = d.get(pos, 0) + int(r.get("gs") or 0)
    out = []
    for pid in ids:
        rec, lvl = None, "none"
        for sport, name in ((11, "AAA"), (12, "AA")):
            g = gs[sport].get(int(pid))
            if g:
                prim = max(g, key=g.get)
                rec = dict(pos=prim, gs=g[prim], total=sum(g.values()),
                           played_ss=g.get("SS", 0), played_cf=g.get("CF", 0),
                           played_c=g.get("C", 0))
                lvl = name
                break
        if rec is None:
            rec = dict(pos=None, gs=0, total=0, played_ss=0, played_cf=0, played_c=0)
        rec.update(mlbam_id=int(pid), milb_level=lvl)
        out.append(rec)
    return pd.DataFrame(out)


def cmd_milb() -> dict:
    man = _load_manifest(RUN_MANIFEST)
    spine_dir = HOME_STAGE / "playing_time_model" / "data" / "processed"
    spine_dir.mkdir(parents=True, exist_ok=True)
    spine = build_usage_spine()
    spine.to_parquet(spine_dir / "usage_spine.parquet", index=False)
    RAW.mkdir(parents=True, exist_ok=True)
    milb = build_milb_fielding(sorted(spine["mlbam_id"].unique()))
    milb.to_parquet(RAW / "milb_fielding.parquet")
    rc = run_stage("pipeline/15_milb_translation.py", "statsapi_cache", [], man)
    _save_manifest(RUN_MANIFEST, man)
    return {"exit": rc, "spine_rows": int(len(spine)), "milb_rows": int(len(milb))}


# ---------------------------------------------------------------------------
# the contract drop
# ---------------------------------------------------------------------------

def card_frame(season: int, variant: str = "full"):
    """One season's SDR rows: Will's 06 board (player-position, Inn >= 300)
    joined to his card (def_runs, def_sd and his sub-components) for 'full',
    or the bare 06 board for a leave-one-source-out variant."""
    import pandas as pd                              # noqa: PLC0415
    sfx = "" if variant == "full" else f"__{variant}"
    board = pd.read_csv(REPORTS / f"06_defense_plus_{season}{sfx}.csv")
    board = board.rename(columns={"id": "player_id"})
    board["season"] = season
    if variant != "full":
        return board
    card = pd.read_parquet(HOME_STAGE / "swing_plus" / "data" / "processed"
                           / f"defense_card_{season}.parquet")
    card = card.rename(columns={"batter": "player_id"})
    m = board.merge(card[["player_id", "Pos", "def_runs", "def_sd", "d_oaa", "d_drs",
                          "d_frp", "d_framing", "def_source"]
                         if "d_framing" in card.columns else
                         [c for c in ["player_id", "Pos", "def_runs", "def_sd", "d_oaa",
                                      "d_drs", "d_frp", "def_source"] if c in card.columns]],
                    on=["player_id", "Pos"], how="left", validate="one_to_one")
    return m


def build_drop(as_of: str | None = None):
    """The sdr_defense_card drop: one row per (player, season, position) that
    Will's 06 ships (Inn >= 300 at a position), sdr_runs = his def_runs
    (dplus_runs: the reliability-weighted OAA/DRS/FRP z-blend, scaled to runs by
    the position's DRS sd and shrunk by Inn / (Inn + 269)). Component columns
    are the source's own runs on the same player-position row, carried beside
    SDR for coverage and the census, never summed into it:
      range_runs    DRS range runs (rPM)       arm_runs     DRS arm runs (rARM)
      dp_runs       DRS double-play runs (rGDP) framing_runs FanGraphs CFraming
      blocking_runs Savant catcher blocking runs (catchers, 2018 on)"""
    import numpy as np                               # noqa: PLC0415
    import pandas as pd                              # noqa: PLC0415
    as_of = as_of or datetime.now().date().isoformat()
    parts = []
    for s in COVERAGE:
        m = card_frame(s)
        fg = pd.read_csv(RAW / f"fg_field_full_{s}.csv").rename(columns={"xMLBAMID": "player_id"})
        fg["player_id"] = pd.to_numeric(fg["player_id"], errors="coerce")
        fg = fg[fg.player_id.notna()].copy()
        fg["player_id"] = fg.player_id.astype(int)
        comp = fg[["player_id", "Pos", "rPM", "rARM", "rGDP", "CFraming", "TeamNameAbb"]]
        m = m.merge(comp, on=["player_id", "Pos"], how="left", validate="one_to_one")
        bp = RAW / f"blocking_{s}.csv"
        if bp.exists():
            b = pd.read_csv(bp)
            b = b.rename(columns={"player_id": "player_id_b"})
            b = b[["player_id_b", "catcher_blocking_runs"]].rename(
                columns={"player_id_b": "player_id"})
            b["player_id"] = pd.to_numeric(b["player_id"], errors="coerce")
            b = b.dropna(subset=["player_id"]).astype({"player_id": int})
            b = b.groupby("player_id", as_index=False)["catcher_blocking_runs"].sum()
            m = m.merge(b, on="player_id", how="left")
            m.loc[m.Pos != "C", "catcher_blocking_runs"] = np.nan
        else:
            m["catcher_blocking_runs"] = np.nan
        parts.append(m)
    d = pd.concat(parts, ignore_index=True)
    out = pd.DataFrame({
        "player_id": d.player_id.astype("int64"),
        "season": d.season.astype("int64"),
        "primary_position": d.Pos,
        "innings": d.Inn.astype(float),
        "sdr_runs": d.def_runs.astype(float).round(2),
        "sdr_runs_sd": d.def_sd.astype(float).round(2),
        "reliability": (d.Inn / (d.Inn + 269.0)).round(4),
        "range_runs": pd.to_numeric(d.rPM, errors="coerce"),
        "arm_runs": pd.to_numeric(d.rARM, errors="coerce"),
        "dp_runs": pd.to_numeric(d.rGDP, errors="coerce"),
        "framing_runs": pd.to_numeric(d.CFraming, errors="coerce").round(2),
        "blocking_runs": pd.to_numeric(d.catcher_blocking_runs, errors="coerce"),
        "dplus_total": d.dplus_total.astype(float).round(2),
        "d_oaa": d.get("d_oaa"), "d_drs": d.get("d_drs"), "d_frp": d.get("d_frp"),
        "d_framing": d.get("d_framing"),
        "level": "MLB",
        "team": d.TeamNameAbb,
        "as_of_date": as_of,
        "player_name": d.PlayerName,
        "def_source": d.def_source,
    })
    out = out.sort_values(["season", "primary_position", "player_id"]).reset_index(drop=True)
    return out


def cmd_drop(as_of: str | None = None) -> Path:
    d = build_drop(as_of)
    DROPS_DIR.mkdir(parents=True, exist_ok=True)
    as_of = str(d["as_of_date"].iloc[0])
    path = DROPS_DIR / f"sdr_defense_card__{as_of}.csv"
    d.to_csv(path, index=False, lineterminator="\n")
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--force", action="store_true")
    sub.add_parser("stages")
    sub.add_parser("milb")
    dp = sub.add_parser("drop")
    dp.add_argument("--as-of", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "fetch":
        res = cmd_fetch(force=a.force)
    elif a.cmd == "stages":
        res = cmd_stages()
    elif a.cmd == "milb":
        res = cmd_milb()
    else:
        res = {"drop": str(cmd_drop(a.as_of))}
    print(json.dumps(res, indent=1, default=str))
    return 0 if not res.get("failures") else 1


if __name__ == "__main__":
    raise SystemExit(main())
