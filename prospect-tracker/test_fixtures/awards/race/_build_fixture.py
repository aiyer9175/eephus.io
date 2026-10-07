# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Builds test_fixtures/awards/race/trimmed.json.gz (AWARDS_5_RACE) on the dev box.

For each season 2021 to 2026, three players whose every season part sits on a board: a
race finalist batter (the first MVP finalist whose reconciliation is exact and who has no
pitching), a race finalist starter (the first Cy Young finalist whose reconciliation is
exact) and one reliever from the bullpen board with relief games only. The fixture keeps
every corpus play where one of them bats or pitches (so a pitcher's first play of each
game, which decides a start, is kept), every other id set to 0 and the plays encoded
compactly (encode() below) to keep the file small, each kept game's date from the race's own date
source, and the board rows copied as they stand: the leverage board's batters[] and
starters[] wpa and the bullpen board's relievers[] wpa (the history boards for 2021 to
2025). test_awards_race.py folds the trimmed plays and checks I5 against those rows.

Run: python test_fixtures/awards/race/_build_fixture.py
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)


def encode(keep, table: list) -> dict:
    """The kept plays, compact: game_pk as [pk, n] runs, half as a string of t and b,
    batter and pitcher as one digit each into `table`, wpa_home in integer tenths.
    test_awards_race.decode() reverses it into the corpus columns."""
    runs = []
    for pk in keep["game_pk"].tolist():
        if runs and runs[-1][0] == int(pk):
            runs[-1][1] += 1
        else:
            runs.append([int(pk), 1])
    where = {v: str(i) for i, v in enumerate(table)}
    return {"ids": table, "game_pk": runs,
            "half": "".join("b" if h == "bottom" else "t" for h in keep["half"].tolist()),
            "inning": [int(x) for x in keep["inning"].tolist()],
            "at_bat_index": [int(x) for x in keep["at_bat_index"].tolist()],
            "batter": "".join(where[int(x)] for x in keep["batter_id"].tolist()),
            "pitcher": "".join(where[int(x)] for x in keep["pitcher_id"].tolist()),
            "wpa_tenths": [int(round(float(x) * 10)) for x in keep["wpa_home"].tolist()]}


def main() -> None:
    import awards_export as E
    import awards_race as R

    ctx, _labs = E._context()
    out = {"schema": 1, "seasons": {}}
    for S in SEASONS:
        race = json.loads((R.LABS / f"race_{S}.json").read_text(encoding="utf-8"))
        board = R.board_wpa(ctx.inp, S, ctx.board_season)
        plays = R.load_plays(S)
        folded = R.fold(plays)
        bad = {r["id"] for r in race["reconciliation"]["finalists"]["not_exact"]}

        def choose(keys, ok):
            for k in keys:
                for f in race[k]["finalists"]:
                    if f["id"] not in bad and ok(int(f["id"])):
                        return int(f["id"])
            raise SystemExit(f"{S}: no clean player in {keys}")

        batter = choose(("MVP_AL", "MVP_NL"), lambda m: m in board["bat"]
                      and m not in folded["start"] and m not in folded["relief"])
        starter = choose(("CY_AL", "CY_NL"), lambda m: m in board["start"]
                       and m not in folded["relief"])
        reliever = next(m for m in sorted(board["relief"])
                        if m not in folded["start"] and m in folded["relief"]
                        and m not in board["start"])
        ids = {batter, starter, reliever}
        keep = plays[plays["batter_id"].isin(ids) | plays["pitcher_id"].isin(ids)]
        keep = keep.sort_values(["game_pk", "at_bat_index"], kind="mergesort").copy()
        # Kept small: an id that is not one of the three reads 0 (the fold skips a 0
        # batter or pitcher); the scores are not kept (no Manager check reads this file).
        keep.loc[~keep["batter_id"].isin(ids), "batter_id"] = 0
        keep.loc[~keep["pitcher_id"].isin(ids), "pitcher_id"] = 0
        pks = sorted({int(x) for x in keep["game_pk"]})
        meta = R.game_meta(pks, abbrev=ctx.abbrev, team_map={})
        cols = encode(keep, [0, batter, starter, reliever])
        out["seasons"][str(S)] = {
            "batter": batter, "starter": starter, "reliever": reliever,
            "plays": cols,
            "dates": {str(pk): meta[pk]["date"] for pk in pks},
            "board": {"bat": {str(batter): board["bat"][batter]},
                      "start": {str(starter): board["start"][starter]},
                      "relief": {str(reliever): board["relief"][reliever]}},
        }
        print(S, "batter", batter, "starter", starter, "reliever", reliever, "plays", len(keep))
    raw = json.dumps(out, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    path = HERE / "trimmed.json.gz"
    with path.open("wb") as f, gzip.GzipFile(filename="", mode="wb", fileobj=f, mtime=0) as fh:
        fh.write(raw)
    print(f"wrote {path} ({path.stat().st_size:,} bytes, {len(raw):,} raw)")


if __name__ == "__main__":
    main()
