# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Leverage Leaderboards (S-1).

Realized in-game LEVERAGE impact, self-computed from the MLB StatsAPI
winProbability feed (mlb_leverage), for the two sides the reliever board doesn't
cover:

  - BATTERS: WPA (win probability added, batter perspective), pLI (average
    leverage index faced), Clutch (WPA/pLI minus WPA/LI), and context-neutral
    WPA/LI.
  - STARTERS: per-start WPA and WPA/LI (the entry-inning==1 games the reliever
    fold drops).

Descriptive realized-impact metrics (the RIV+ / xREM+ precedent), NOT a predictive
model. The same warm winProbability cache the bullpen board already walks powers
this in ONE extra pass (mlb_leverage.fetch_season_all_leverage). Writes
data/leverage_leaderboards.json.

Run: `python leverage_export.py [season]`
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import mlb_leverage
from bullpen_export import load_season_pitching
from hitter_export import load_season_hitting

_log = logging.getLogger(__name__)
ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "leverage_leaderboards.json"

QUAL_PA = 250       # batter qualification (a regular's sample)
QUAL_STARTS = 5     # starter qualification


def _name_team(rows: list[dict]) -> dict:
    out: dict[int, tuple] = {}
    for r in rows:
        mid = r.get("mlbam")
        if mid is not None:
            out[int(mid)] = (r.get("name"), r.get("team"))
    return out


def export(season: Optional[int] = None, *, leverage_limit: Optional[int] = None,
           write: bool = True, log=print, today: Optional[str] = None) -> int:
    """Build data/leverage_leaderboards.json and return batters+starters count."""
    season = int(season or date.today().year)
    today = today or date.today().isoformat()

    log(f"  leverage: loading {season} name/team maps...")
    hit_rows = load_season_hitting(season)
    pit_rows = load_season_pitching(season)
    bat_nt = _name_team(hit_rows)
    pit_nt = _name_team(pit_rows)
    pit_gs: dict[int, int] = {}
    for r in pit_rows:
        mid = r.get("mlbam")
        if mid is not None:
            pit_gs[int(mid)] = int(r.get("GS") or 0)

    log(f"  leverage: walking winProbability feed ({season}); cached games are free...")
    _rel, bat, strt, cov = mlb_leverage.fetch_season_all_leverage(season, limit=leverage_limit)
    log(f"  leverage: {cov.get('games')}/{cov.get('games_total')} games; "
        f"{len(bat)} batters, {len(strt)} starters folded")

    batters = []
    for mid, m in bat.items():
        nt = bat_nt.get(mid)
        batters.append({
            "mlbam": mid, "name": m.get("name") or (nt[0] if nt else None),
            "team": nt[1] if nt else None,
            "pa": m.get("pa"), "wpa": m.get("wpa"), "pli": m.get("pli"),
            "clutch": m.get("clutch"), "wpa_li": m.get("wpa_li"),
            "qualified": (m.get("pa") or 0) >= QUAL_PA,
        })
    starters = []
    for mid, m in strt.items():
        if pit_gs.get(mid, 0) <= 0:      # keep only real starters (GS>0 on the season line)
            continue
        nt = pit_nt.get(mid)
        starters.append({
            "mlbam": mid, "name": m.get("name") or (nt[0] if nt else None),
            "team": nt[1] if nt else None,
            "starts": m.get("starts"), "wpa": m.get("wpa"),
            "wpa_per_start": m.get("wpa_per_start"), "wpa_li": m.get("wpa_li"),
            "gs": pit_gs.get(mid, 0),
            "qualified": (m.get("starts") or 0) >= QUAL_STARTS,
        })
    batters.sort(key=lambda r: (r["wpa"] if r["wpa"] is not None else -99), reverse=True)
    starters.sort(key=lambda r: (r["wpa"] if r["wpa"] is not None else -99), reverse=True)

    payload = {
        "generated_at": today, "season": season, "as_of": today,
        "coverage": cov,
        "note": ("Realized in-game leverage impact, self-computed from the MLB StatsAPI "
                 "winProbability feed (FanGraphs is blocked for autonomous pulls). Batters: "
                 "WPA, average Leverage Index faced (pLI), and Clutch (WPA/pLI minus WPA/LI). "
                 "Starters: per-start WPA and WPA/LI. Descriptive realized value, not a "
                 "predictive model."),
        "batters": batters, "starters": starters,
    }
    n = len(batters) + len(starters)
    log(f"  leverage: {len(batters)} batters ({sum(1 for b in batters if b['qualified'])} qualified), "
        f"{len(starters)} starters")
    if write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = OUT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(OUT_PATH)
        log(f"  leverage: wrote {OUT_PATH.name}")
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _season = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
    export(_season, log=print)
