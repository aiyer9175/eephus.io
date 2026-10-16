#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""extract_feed_fielders - the pitch ledger's feed extract (docs/ewar/PITCH_LEDGER_GATE.md part 1).

One read-only pass over the cached MLB game feeds the play-by-play corpus was built from
(.cache/win_prob/<game_pk>.json, a list of allPlays). Per playEvent it keeps the defense
alignment (pitcher, catcher and the seven fielders), the home-plate umpire, and, on the play's
in-play pitch, the batted-ball data; per play, the first fielder credited on any runner.

Writes .cache/ewar_innovate_ledger/feed_extract/<season>.parquet for each corpus season; a
game is assigned to the season whose corpus plays hold its game_pk. Measures nothing.

Run: python tools/extract_feed_fielders.py [--seasons 2018,2019,...]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEEDS = ROOT / ".cache" / "win_prob"
CORPUS = ROOT / ".cache" / "pbp_corpus"
OUT = ROOT / ".cache" / "ewar_innovate_ledger" / "feed_extract"
SEASONS = (2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026)
SLOTS = ("pitcher", "catcher", "first", "second", "third", "shortstop", "left", "center", "right")
FIELDING_CREDITS = ("f_fielded_ball", "f_putout", "f_assist", "f_assist_of", "f_deflection",
                    "f_fielding_error", "f_throwing_error", "f_error_dropped_ball",
                    "f_touch", "f_interference", "f_catcher_interf")


def _pid(d) -> int | None:
    if not isinstance(d, dict):
        return None
    v = d.get("id")
    return int(v) if isinstance(v, int) else None


def game_rows(game_pk: int, plays: list) -> list[dict]:
    """Rows for one game. Pure."""
    out = []
    for p in plays:
        ab = (p.get("about") or {}).get("atBatIndex", p.get("atBatIndex"))
        if ab is None:
            continue
        first_f, first_pos = None, None
        for r in p.get("runners") or ():
            for c in r.get("credits") or ():
                if c.get("credit") in FIELDING_CREDITS and first_f is None:
                    first_f = _pid(c.get("player"))
                    first_pos = (c.get("position") or {}).get("abbreviation")
        for e in p.get("playEvents") or ():
            dfn = e.get("defense") or {}
            off = e.get("officials") or []
            hp = None
            for o in off:
                if o.get("officialType") == "Home Plate":
                    hp = _pid(o.get("official"))
            hd = e.get("hitData") or {}
            co = hd.get("coordinates") or {}
            det = e.get("details") or {}
            row = {
                "game_pk": int(game_pk), "at_bat_index": int(ab), "index": int(e.get("index", -1)),
                "play_id": e.get("playId"), "is_pitch": bool(e.get("isPitch")),
                "pitch_number": e.get("pitchNumber"), "code": det.get("code"),
                "hp_umpire_id": hp,
                "launch_speed": hd.get("launchSpeed"), "launch_angle": hd.get("launchAngle"),
                "total_distance": hd.get("totalDistance"),
                "hc_x": co.get("coordX"), "hc_y": co.get("coordY"),
                "first_fielder_id": first_f, "first_fielder_pos": first_pos,
            }
            for s in SLOTS:
                row[f"{s}_id"] = _pid(dfn.get(s))
            out.append(row)
    return out


def season_of_games(seasons) -> dict[int, int]:
    import pandas as pd
    m = {}
    for s in seasons:
        f = CORPUS / "plays" / str(s) / f"plays-{s}.parquet"
        g = pd.read_parquet(f, columns=["game_pk"])["game_pk"].unique()
        for k in g:
            m[int(k)] = int(s)
    return m


def run(seasons=SEASONS, feeds: Path = FEEDS, out: Path = OUT) -> dict:
    import orjson
    import pandas as pd
    t0 = time.time()
    which = season_of_games(seasons)
    out.mkdir(parents=True, exist_ok=True)
    rec = {}
    for s in seasons:
        s = int(s)
        rs, seen, missing = [], 0, 0
        for gk in sorted(k for k, v in which.items() if v == s):
            f = feeds / f"{gk}.json"
            if not f.exists():
                missing += 1
                continue
            plays = orjson.loads(f.read_bytes())
            if isinstance(plays, dict):
                plays = ((plays.get("liveData") or {}).get("plays") or {}).get("allPlays") or []
            rs.extend(game_rows(gk, plays))
            seen += 1
        df = pd.DataFrame(rs)
        del rs
        if len(df):
            for c in ("launch_speed", "launch_angle", "total_distance", "hc_x", "hc_y"):
                df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
            for c in [f"{x}_id" for x in SLOTS] + ["hp_umpire_id", "first_fielder_id", "pitch_number"]:
                df[c] = pd.array(df[c], dtype="Int64")
        df.to_parquet(out / f"{s}.parquet", index=False)
        rec[str(s)] = {"games": seen, "games_missing": missing, "rows": int(len(df))}
        print(s, rec[str(s)], round(time.time() - t0, 1), flush=True)
        del df
    rec["seconds"] = round(time.time() - t0, 1)
    (out / "manifest.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default=",".join(str(s) for s in SEASONS))
    a = ap.parse_args(argv)
    seasons = [int(x) for x in a.seasons.split(",") if x]
    print(json.dumps(run(seasons), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
