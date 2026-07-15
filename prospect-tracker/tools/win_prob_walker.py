# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""win_prob_walker - shared per-pitcher-season aggregates from .cache/win_prob.

PROPOSED NEW MODULE (wave-3 improvement program, lane w3-walker-fbhr-csw).
Extends the per-game pass pattern of mlb_leverage.py (same play stream, same
matchup.pitcher attribution, same entry-inning convention) but instead of
leverage it digs into the parts of the winProbability payload the leverage walk
ignores: playEvents (pitch-by-pitch call codes + hitData.trajectory) and the
result/runners blocks. One table out, keyed (season, mlbam):

  pa                    plate appearances against (one play == one PA)
  pitches               isPitch events thrown
  called_strikes        details.call.code == C
  whiffs                details.call.code in {S, W, M}  (swinging strike,
                        swinging strike blocked, missed bunt; foul tips (T) and
                        fouls excluded - the standard CSW% numerator convention)
  csw / csw_pct         called_strikes + whiffs (+ per-pitch rate)
  batted_balls          pitch events carrying a hitData.trajectory
  fly_balls / popups / ground_balls / line_drives / bunts
                        trajectory buckets (bunt_* fold into bunts)
  hr_allowed            result.eventType == home_run
  fb_pct                fly_balls / batted_balls (fly only; popups separate so
                        consumers can run the popup sensitivity arm)
  tto1/2/3 wOBA splits  wOBA-against by times-through-order bucket (1st, 2nd,
                        3rd+ time this pitcher faces the same batter in a game),
                        each with numerator / denominator / PA counts
  appearances           games appeared
  start_games           games entered in the 1st inning (start/opener, the
                        mlb_leverage entry_inning==1 convention)
  outs / outs_per_appearance
                        runners[].movement.isOut count while on the mound

wOBA-against uses FIXED linear weights (wBB .69, wHBP .72, w1B .88, w2B 1.25,
w3B 1.58, wHR 2.02; denominator = PA - intentional walks - sac bunts - catcher
interference). Fixed-not-yearly is deliberate: the table's consumers compare
WITHIN a season pool or feed rank-based evals, where the small year-to-year
weight drift is irrelevant. Do NOT sum the tto numerators across seasons and
call it career wOBA.

READS THE CACHE ONLY - no network, no TTL logic, no repo writes. The season of
each game is derived from the payload itself (first play about.startTime year),
so the walker needs no schedule call and aggregates exactly what the cache
holds (2018-2026 regular season, no 2017/2020).

Run:
    python win_prob_walker.py OUT_DIR [--limit N] [--cache DIR]
writes OUT_DIR/win_prob_pitcher_seasons.parquet (falls back to .json.gz when
pandas/pyarrow are unavailable) + OUT_DIR/win_prob_walker_coverage.json.
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import time
from pathlib import Path

DEFAULT_CACHE = Path(__file__).resolve().parent.parent / ".cache" / "win_prob"

# CSW% convention: called strike + swinging strike (+blocked) + missed bunt.
CALLED = {"C"}
WHIFF = {"S", "W", "M"}

# fixed wOBA linear weights (see module docstring)
W_BB, W_HBP, W_1B, W_2B, W_3B, W_HR = 0.69, 0.72, 0.88, 1.25, 1.58, 2.02
_WOBA_NUM = {"walk": W_BB, "hit_by_pitch": W_HBP, "single": W_1B,
             "double": W_2B, "triple": W_3B, "home_run": W_HR}
# PAs excluded from the wOBA denominator entirely
_WOBA_EXCLUDED = {"intent_walk", "sac_bunt", "catcher_interf",
                  "sac_bunt_double_play", "batter_interference"}

_TRAJ_FIELD = {"fly_ball": "fly_balls", "popup": "popups",
               "ground_ball": "ground_balls", "line_drive": "line_drives",
               "bunt_grounder": "bunts", "bunt_popup": "bunts",
               "bunt_line_drive": "bunts"}


def _plays_of(payload) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("winProbability") or []
    return []


def _new_row(name: str) -> dict:
    return {"name": name, "pa": 0, "pitches": 0, "called_strikes": 0,
            "whiffs": 0, "batted_balls": 0, "fly_balls": 0, "popups": 0,
            "ground_balls": 0, "line_drives": 0, "bunts": 0, "hr_allowed": 0,
            "appearances": 0, "start_games": 0, "outs": 0,
            "tto1_num": 0.0, "tto1_den": 0, "tto1_pa": 0,
            "tto2_num": 0.0, "tto2_den": 0, "tto2_pa": 0,
            "tto3_num": 0.0, "tto3_den": 0, "tto3_pa": 0}


def fold_game(acc: dict, plays: list) -> dict:
    """Fold one game's winProbability plays into the running per-pitcher season
    accumulator `acc` ({mlbam: row}). Pure; returns per-game counters for the
    coverage report."""
    gstat = {"plays": 0, "pitch_events": 0, "bb_with_traj": 0}
    faced: dict = {}          # (pid, bid) -> times faced this game
    entered: dict = {}        # pid -> entry inning
    for play in plays:
        matchup = play.get("matchup") or {}
        p = matchup.get("pitcher") or {}
        pid = p.get("id")
        if not pid:
            continue
        gstat["plays"] += 1
        row = acc.get(pid)
        if row is None:
            row = acc[pid] = _new_row(p.get("fullName", ""))
        elif p.get("fullName"):
            row["name"] = p["fullName"]
        if pid not in entered:
            entered[pid] = (play.get("about") or {}).get("inning")
        row["pa"] += 1

        # ---- pitch events: CSW + batted-ball trajectory ---- #
        for ev in (play.get("playEvents") or []):
            if not ev.get("isPitch"):
                continue
            row["pitches"] += 1
            gstat["pitch_events"] += 1
            code = ((ev.get("details") or {}).get("call") or {}).get("code")
            if code in CALLED:
                row["called_strikes"] += 1
            elif code in WHIFF:
                row["whiffs"] += 1
            traj = (ev.get("hitData") or {}).get("trajectory")
            if traj:
                row["batted_balls"] += 1
                gstat["bb_with_traj"] += 1
                f = _TRAJ_FIELD.get(traj)
                if f:
                    row[f] += 1

        # ---- result: HR + TTO wOBA-against ---- #
        et = (play.get("result") or {}).get("eventType")
        if et == "home_run":
            row["hr_allowed"] += 1
        bid = (matchup.get("batter") or {}).get("id")
        if bid is not None:
            k = (pid, bid)
            faced[k] = faced.get(k, 0) + 1
            b = min(faced[k], 3)
            row[f"tto{b}_pa"] += 1
            if et not in _WOBA_EXCLUDED:
                row[f"tto{b}_den"] += 1
                row[f"tto{b}_num"] += _WOBA_NUM.get(et, 0.0)

        # ---- outs recorded while on the mound ---- #
        for rn in (play.get("runners") or []):
            if ((rn.get("movement") or {}).get("isOut")):
                row["outs"] += 1

    for pid, inn in entered.items():
        acc[pid]["appearances"] += 1
        if inn == 1:
            acc[pid]["start_games"] += 1
    return gstat


def finalize(acc_by_season: dict) -> list[dict]:
    """{season: {mlbam: row}} -> flat list of finalized rows with derived rates."""
    out = []
    for season in sorted(acc_by_season):
        for pid, r in sorted(acc_by_season[season].items()):
            row = {"season": int(season), "mlbam": int(pid)}
            row.update(r)
            row["csw"] = r["called_strikes"] + r["whiffs"]
            row["csw_pct"] = (row["csw"] / r["pitches"]) if r["pitches"] else None
            row["fb_pct"] = (r["fly_balls"] / r["batted_balls"]) if r["batted_balls"] else None
            row["fb_popup_pct"] = ((r["fly_balls"] + r["popups"]) / r["batted_balls"]
                                   if r["batted_balls"] else None)
            row["outs_per_appearance"] = (r["outs"] / r["appearances"]
                                          if r["appearances"] else None)
            for b in (1, 2, 3):
                den = r[f"tto{b}_den"]
                row[f"tto{b}_woba"] = (r[f"tto{b}_num"] / den) if den else None
            out.append(row)
    return out


def walk_cache(cache_dir: Path = DEFAULT_CACHE, *, limit: int | None = None,
               progress=None) -> tuple[list[dict], dict]:
    """Walk every cached winProbability game file (no network), derive each
    game's season from its own payload, and return (rows, coverage)."""
    files = sorted(f for f in os.listdir(cache_dir) if f.endswith(".json"))
    if limit is not None:
        files = files[:limit]
    acc_by_season: dict = {}
    cov: dict = {}
    skipped = 0
    t0 = time.time()
    for i, fn in enumerate(files):
        try:
            plays = _plays_of(json.loads(
                (cache_dir / fn).read_text(encoding="utf-8")))
        except (OSError, ValueError):
            skipped += 1
            continue
        if not plays:
            skipped += 1
            continue
        st = ((plays[0].get("about") or {}).get("startTime")
              or (plays[0].get("about") or {}).get("endTime") or "")
        try:
            season = int(st[:4])
        except ValueError:
            skipped += 1
            continue
        acc = acc_by_season.setdefault(season, {})
        g = fold_game(acc, plays)
        c = cov.setdefault(season, {"games": 0, "plays": 0, "pitch_events": 0,
                                    "bb_with_traj": 0})
        c["games"] += 1
        c["plays"] += g["plays"]
        c["pitch_events"] += g["pitch_events"]
        c["bb_with_traj"] += g["bb_with_traj"]
        if progress and (i % 1000 == 0 or i == len(files) - 1):
            progress(i + 1, len(files))
    rows = finalize(acc_by_season)
    coverage = {
        "cache_dir": str(cache_dir),
        "files_seen": len(files), "files_skipped_or_empty": skipped,
        "walk_seconds": round(time.time() - t0, 1),
        "seasons": {str(s): dict(cov[s], pitcher_seasons=len(acc_by_season[s]))
                    for s in sorted(cov)},
        "conventions": {
            "csw": "called (C) + whiff (S/W/M) per pitch; foul tips (T) excluded",
            "fb_pct": "fly_ball / batted_balls (popups SEPARATE; see fb_popup_pct)",
            "tto_woba": ("fixed linear weights BB .69 HBP .72 1B .88 2B 1.25 "
                         "3B 1.58 HR 2.02; den = PA - IBB - sac bunt - interference"),
            "outs": "runners[].movement.isOut while on the mound",
            "start_games": "entered in inning 1 (mlb_leverage convention)",
        },
    }
    return rows, coverage


def write_table(rows: list[dict], out_dir: Path) -> Path:
    """Persist the one table: parquet preferred, .json.gz fallback."""
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        import pandas as pd
        path = out_dir / "win_prob_pitcher_seasons.parquet"
        pd.DataFrame(rows).to_parquet(path, index=False)
        return path
    except Exception:  # noqa: BLE001 - pandas/pyarrow absent -> portable fallback
        path = out_dir / "win_prob_pitcher_seasons.json.gz"
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            json.dump(rows, fh)
        return path


def load_table(path: Path) -> dict:
    """{(season, mlbam): row} from either persisted format."""
    if str(path).endswith(".parquet"):
        import pandas as pd
        rows = pd.read_parquet(path).to_dict("records")
    else:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            rows = json.load(fh)
    return {(int(r["season"]), int(r["mlbam"])): r for r in rows}


def main(argv: list[str]) -> None:
    out_dir = Path(argv[0]) if argv else Path(".")
    limit = None
    cache = DEFAULT_CACHE
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
    if "--cache" in argv:
        cache = Path(argv[argv.index("--cache") + 1])
    rows, coverage = walk_cache(cache, limit=limit,
                                progress=lambda i, n: print(f"  {i}/{n}", flush=True))
    path = write_table(rows, out_dir)
    covp = out_dir / "win_prob_walker_coverage.json"
    covp.write_text(json.dumps(coverage, indent=1), encoding="utf-8")
    print(f"wrote {path} ({len(rows)} pitcher-seasons) + {covp.name}")
    print(json.dumps(coverage["seasons"], indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
