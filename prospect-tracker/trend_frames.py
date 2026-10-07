# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""trend_frames - the frames League Trends reads (League Trends plan 5.1).

League Trends owns this module (ruling R6); it never edits P8.2's
mlbstats_games. It reads the payload-direct pitch sidecar that
tools/build_pitch_physics.py writes under ``.cache/pbp_physics/`` and the
daily WAR frame ``.cache/war_daily/bat.parquet``, so everything here builds
where the play corpus is absent (the deploy box, plan 5.5).

CLUB IDENTITY, ``club_by_game(season)`` (ruling T5). The payloads carry no
team block, so a game's clubs are recovered by a vote: every plate appearance
of a half inning votes for its batter's clubs, weighted by his share of that
season's plate appearances with each club (``mgmt_teams.player_team_weights``,
imported, never copied; a traded batter votes for both clubs and is outvoted
by his teammates). The bottom half bats at home, so the bottom half's winning
club is the home club and the top half's the away club. A game is left
unresolved when the two halves vote for one club, when a half has no
attributable batter, or when a half's top two clubs tie exactly. A season whose
resolved share of the sidecar's games falls below
``mgmt_teams.MIN_RESOLVED_SHARE`` is refused, never returned partial, because a
partial map drops games in a way correlated with roster churn.

What it never does: call mgmt_teams' corpus map builder (it reads the corpus
and, validated, the betting results cache), open any betting cache or a
lineup, vintage, odds, weather or game-feed cache, or relate a club to a game
result or a price. Club identity labels cards and Teams rows only; it enters
no bar (plan 3.5 item 6).
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple, Optional

import pandas as pd

from mgmt_teams import MIN_RESOLVED_SHARE, player_team_weights

ROOT = Path(__file__).resolve().parent
PHYSICS_DIR = ROOT / ".cache" / "pbp_physics"


class ClubMap(NamedTuple):
    """{game_pk: {"home", "away", "season"}} and the season's counts."""
    games: dict
    meta: dict


def _table(physics_dir: Path, table: str, season: int) -> Path:
    return Path(physics_dir) / str(int(season)) / f"{table}-{int(season)}.parquet"


def resolve_clubs(season: int, *, physics_dir: Optional[Path] = None,
                  war_daily: Optional[Path] = None,
                  weights: Optional[pd.DataFrame] = None) -> ClubMap:
    """The half-inning batter vote for one season, with its counts. Raises
    ValueError below the resolved-share floor and FileNotFoundError when the
    sidecar holds no table for the season."""
    season = int(season)
    pdir = Path(physics_dir or PHYSICS_DIR)
    pit_p, gam_p = _table(pdir, "pitches", season), _table(pdir, "games", season)
    if not (pit_p.exists() and gam_p.exists()):
        raise FileNotFoundError(
            f"the pitch sidecar holds no {season} table under {pdir}; run "
            "tools/build_pitch_physics.py first")
    games = pd.read_parquet(gam_p, columns=["game_pk"])
    pas = (pd.read_parquet(pit_p, columns=["game_pk", "half", "at_bat_index", "batter"])
           .dropna(subset=["batter", "half"])
           .drop_duplicates(["game_pk", "half", "at_bat_index", "batter"]))
    pas["batter"] = pas["batter"].astype("int64")
    w = weights if weights is not None else player_team_weights(war_daily)
    wy = w[w["year_ID"] == season][["mlb_ID", "team_ID", "w"]]
    j = pas.merge(wy, left_on="batter", right_on="mlb_ID", how="inner")
    votes = j.groupby(["game_pk", "half", "team_ID"], as_index=False)["w"].sum()
    votes = votes.sort_values(["game_pk", "half", "w", "team_ID"],
                              ascending=[True, True, False, True], kind="mergesort")
    votes["rank"] = votes.groupby(["game_pk", "half"]).cumcount()
    top = votes[votes["rank"] == 0].set_index(["game_pk", "half"])
    second = votes[votes["rank"] == 1].set_index(["game_pk", "half"])["w"]
    top = top.join(second.rename("w2"))
    tied = top["w2"].notna() & (top["w"] == top["w2"])
    top.loc[tied, "team_ID"] = None
    win = top["team_ID"].unstack("half")
    out: dict = {}
    same = no_half = 0
    for gp, row in win.iterrows():
        home, away = row.get("bottom"), row.get("top")
        if not (isinstance(home, str) and isinstance(away, str)):
            no_half += 1
            continue
        if home == away:
            same += 1
            continue
        out[int(gp)] = {"home": home, "away": away, "season": season}
    ties = int(tied.sum())
    n_games = int(games["game_pk"].nunique())
    share = len(out) / n_games if n_games else 0.0
    meta = {"season": season, "games": n_games, "resolved": len(out),
            "share": round(share, 6), "same_club": same,
            "missing_or_tied_half": no_half, "tied_halves": ties,
            "floor": MIN_RESOLVED_SHARE}
    if share < MIN_RESOLVED_SHARE:
        raise ValueError(
            f"club identity resolved only {len(out):,} of {n_games:,} {season} games "
            f"({share:.4f}), below the {MIN_RESOLVED_SHARE} floor "
            f"(mgmt_teams.MIN_RESOLVED_SHARE); refused rather than returned partial")
    return ClubMap(out, meta)


def club_by_game(season: int, *, physics_dir: Optional[Path] = None,
                 war_daily: Optional[Path] = None) -> dict:
    """{game_pk: {"home": club, "away": club, "season": int}} for one season
    (see the module docstring). Refuses below the resolved-share floor."""
    return resolve_clubs(season, physics_dir=physics_dir, war_daily=war_daily).games


__all__ = ["ClubMap", "club_by_game", "resolve_clubs", "PHYSICS_DIR"]
