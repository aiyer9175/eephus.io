"""Phase 1B, step 1: build a team/venue-stratified sample with real
per-pitcher volume, replacing Phase 1A's venue-coverage sample (which was
3 games/venue -- fine for a coverage audit, useless for reliability work).

Two different stratification units, because coverage itself has two
different shapes (see Phase 1A's DATA_AUDIT_REPORT.md):

- AAA / AA / High-A: coverage (or its absence) is uniform across the whole
  level, so the right unit is TEAM -- pick N teams, pull ~30 of each team's
  games (home + away, since a pitching staff travels), pooling their full
  pitching workload.
- Low-A: coverage is a property of 10 specific venues, not of any team (and
  several of those venues are shared by more than one franchise -- they're
  Florida spring-training complexes serving multiple FSL clubs). The right
  unit there is VENUE -- deepen the sample at exactly the 10 venues Phase 1A
  already confirmed are tracked (from reports/TRUST_MATRIX.json), taking
  ~30 games at each regardless of which team was "home" that day.

Output: data_cache/samples/{level}_team_stratified.json

Usage: python sample_team_stratified.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import LEVELS, DATA_CACHE, REPORTS_DIR, load_json, save_json  # noqa: E402

GAMES_PER_UNIT = 30
N_TEAMS = 10


def evenly_spaced(games: list[dict], n: int) -> list[dict]:
    """Pick up to n games, evenly spaced by date order (deterministic)."""
    games_sorted = sorted(games, key=lambda g: g["officialDate"])
    if len(games_sorted) <= n:
        return games_sorted
    step = len(games_sorted) / n
    idxs = sorted({int(i * step) for i in range(n)})
    return [games_sorted[i] for i in idxs]


def sample_team_level(level: str) -> list[dict]:
    schedule = load_json(DATA_CACHE / "schedules" / f"{level}.json")

    all_teams = sorted({r["home_team"] for r in schedule})
    selected_teams = all_teams[:N_TEAMS]

    by_team_games: dict[str, list[dict]] = {t: [] for t in selected_teams}
    for r in schedule:
        for t in (r["home_team"], r["away_team"]):
            if t in by_team_games:
                by_team_games[t].append(r)

    sampled_by_gamepk: dict[int, dict] = {}
    for team, games in by_team_games.items():
        chosen = evenly_spaced(games, GAMES_PER_UNIT)
        for g in chosen:
            row = sampled_by_gamepk.setdefault(
                g["gamePk"],
                {
                    "gamePk": g["gamePk"],
                    "venue_id": g["venue_id"],
                    "venue_name": g["venue_name"],
                    "officialDate": g["officialDate"],
                    "sampled_for_teams": [],
                },
            )
            row["sampled_for_teams"].append(team)

    return list(sampled_by_gamepk.values()), selected_teams


def tracked_low_a_venue_ids() -> list[int]:
    trust = load_json(REPORTS_DIR / "TRUST_MATRIX.json")
    lowa = trust["Low-A"]
    return [
        int(vid)
        for vid, v in lowa.items()
        if v["pitch_trust"].get("start_speed") == "TRUSTED"
    ]


def sample_low_a() -> list[dict]:
    schedule = load_json(DATA_CACHE / "schedules" / "Low-A.json")
    tracked_ids = set(tracked_low_a_venue_ids())

    by_venue_games: dict[int, list[dict]] = {vid: [] for vid in tracked_ids}
    for r in schedule:
        if r["venue_id"] in tracked_ids:
            by_venue_games[r["venue_id"]].append(r)

    sampled_by_gamepk: dict[int, dict] = {}
    for venue_id, games in by_venue_games.items():
        chosen = evenly_spaced(games, GAMES_PER_UNIT)
        for g in chosen:
            sampled_by_gamepk[g["gamePk"]] = {
                "gamePk": g["gamePk"],
                "venue_id": g["venue_id"],
                "venue_name": g["venue_name"],
                "officialDate": g["officialDate"],
                "sampled_for_teams": [g["home_team"]],
            }

    return list(sampled_by_gamepk.values())


def main() -> None:
    samples_dir = DATA_CACHE / "samples"
    total = 0
    for level in ["AAA", "AA", "High-A"]:
        sampled, teams = sample_team_level(level)
        out_path = samples_dir / f"{level}_team_stratified.json"
        save_json(out_path, sampled)
        print(f"{level}: {len(teams)} teams selected, {len(sampled)} unique games -> {out_path}")
        print(f"  teams: {', '.join(teams)}")
        total += len(sampled)

    sampled_lowa = sample_low_a()
    out_path = samples_dir / "Low-A_team_stratified.json"
    save_json(out_path, sampled_lowa)
    tracked_ids = tracked_low_a_venue_ids()
    print(f"Low-A: {len(tracked_ids)} tracked venues deepened, {len(sampled_lowa)} unique games -> {out_path}")
    total += len(sampled_lowa)

    print(f"Total games across all levels: {total}")


if __name__ == "__main__":
    main()
