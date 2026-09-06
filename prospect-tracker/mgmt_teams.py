"""Team attribution for the play corpus, recovered offline.

THE PROBLEM. `.cache/pbp_corpus` carries 1,448,967 plays and no team identity at all: the
plays table has game_pk, inning, half, the base-out state and the participants, and nothing
that says who was playing. The source cache is no better. `.cache/win_prob` payloads are a
bare play list with no `gameData` block, so the teams were never fetched, not merely dropped.

Every In-Game Management number needs an AGENT to attribute to, and without a team there is no
agent at any resolution. This module recovers it without a single network call.

HOW. `.cache/war_daily/bat.parquet` carries (mlb_ID, year_ID, team_ID, PA) for 126,518
player-seasons. A batter is assigned to the club he took the most plate appearances for that
season, which collapses stints and lets a traded player vote for both of his clubs weighted by
playing time. Each game's BOTTOM half is batted by the home team by definition, so the modal
club among a game's bottom-half batters IS the home team, and the modal club among its top-half
batters is the away team.

WHY THIS IS TRUSTWORTHY. It is not an inference from one player, it is a vote among every
batter who appeared in a half-inning, typically thirty to forty plate appearances a side. A
traded player who votes for the wrong club is outvoted by his teammates. The module VALIDATES
itself against `.cache/betting/completed_games.json`, which carries real home_org / away_org for
2026, and refuses to return a map that disagrees with ground truth beyond a stated tolerance.

WHAT IT IS NOT. It is not a manager. There is no manager anywhere on disk. A team-season is a
weaker agent than a manager in one specific direction, and that direction is the useful one:
managers change and teams do not, so team-season persistence is an UPPER BOUND on manager
persistence. A null at team-season level therefore decides the manager question too.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / ".cache" / "pbp_corpus"
WAR_BAT = ROOT / ".cache" / "war_daily" / "bat.parquet"
GROUND_TRUTH = ROOT / ".cache" / "betting" / "completed_games.json"

log = logging.getLogger(__name__)

#: Below this share of games resolved, the map is refused rather than returned
#: partial. A partial map silently drops agent-seasons and biases whichever
#: clubs happen to resolve worst.
MIN_RESOLVED_SHARE = 0.98

#: Below this agreement with ground truth on the seasons where ground truth
#: exists, the map is refused. Measured 2026-09-06: 2,122 of 2,124 home and
#: 2,124 of 2,124 away.
MIN_GROUND_TRUTH_AGREEMENT = 0.99


def _season_dirs(corpus: Path):
    d = Path(corpus) / "plays"
    return sorted((p for p in d.iterdir() if p.is_dir()), key=lambda p: p.name) \
        if d.exists() else []


def player_team_weights(war_daily: Path | None = None):
    """(mlb_ID, year_ID, team_ID) -> share of that season's plate appearances.

    A traded player appears once per club with the weight he earned there, so
    he votes for both, proportionally. Rows with no id or no club are dropped
    rather than guessed.
    """
    import pandas as pd

    p = Path(war_daily or WAR_BAT)
    if not p.exists():
        raise FileNotFoundError(
            f"{p} is missing. Team attribution is derived from the daily WAR "
            "frame; without it there is no agent to attribute a decision to, "
            "and the In-Game Management battery cannot run.")
    war = pd.read_parquet(p, columns=["mlb_ID", "year_ID", "team_ID", "PA"])
    war = war.dropna(subset=["mlb_ID", "team_ID"])
    war["mlb_ID"] = war["mlb_ID"].astype("int64")
    war["year_ID"] = war["year_ID"].astype(int)
    g = war.groupby(["mlb_ID", "year_ID", "team_ID"], as_index=False)["PA"].sum()
    tot = g.groupby(["mlb_ID", "year_ID"])["PA"].transform("sum")
    g["w"] = (g["PA"] / tot).where(tot > 0, 0.0)
    return g


def build_map(*, corpus: Path | None = None, war_daily: Path | None = None,
              validate: bool = True) -> dict:
    """{game_pk: {"home": club, "away": club, "season": int}}.

    Raises if the map is too incomplete or disagrees with ground truth, because
    a quietly partial map is worse than none: it drops agent-seasons in a way
    that is correlated with roster churn.
    """
    import pandas as pd

    corpus = Path(corpus or CORPUS)
    weights = player_team_weights(war_daily)
    out: dict = {}
    per_season = {}
    for season_dir in _season_dirs(corpus):
        season = int(season_dir.name)
        files = sorted(season_dir.glob("*.parquet"))
        if not files:
            continue
        pl = pd.concat(
            [pd.read_parquet(f, columns=["game_pk", "half", "batter_id"])
             for f in files], ignore_index=True)
        wy = weights[weights["year_ID"] == season][["mlb_ID", "team_ID", "w"]]
        j = pl.merge(wy, left_on="batter_id", right_on="mlb_ID", how="inner")
        votes = j.groupby(["game_pk", "half", "team_ID"], as_index=False)["w"].sum()
        votes = (votes.sort_values("w", ascending=False)
                 .drop_duplicates(["game_pk", "half"]))
        piv = votes.pivot(index="game_pk", columns="half", values="team_ID")
        n_ok = 0
        for gp, row in piv.iterrows():
            home = row.get("bottom")
            away = row.get("top")
            # A game whose two halves vote for the SAME club is not resolved.
            # It happens when one half has almost no attributable batters, and
            # returning it would put both sides of a decision on one agent.
            if isinstance(home, str) and isinstance(away, str) and home != away:
                out[int(gp)] = {"home": home, "away": away, "season": season}
                n_ok += 1
        per_season[season] = {"games": int(len(piv)), "resolved": n_ok}

    total = sum(v["games"] for v in per_season.values())
    resolved = sum(v["resolved"] for v in per_season.values())
    share = resolved / total if total else 0.0
    if validate and share < MIN_RESOLVED_SHARE:
        raise ValueError(
            f"team attribution resolved only {resolved:,} of {total:,} games "
            f"({share:.4f}), below the {MIN_RESOLVED_SHARE} floor. A partial "
            "map drops agent-seasons in a way correlated with roster churn, so "
            "it is refused rather than returned.")
    if validate:
        chk = validate_against_ground_truth(out)
        if chk["checked"] and chk["agreement"] < MIN_GROUND_TRUTH_AGREEMENT:
            raise ValueError(
                f"team attribution agrees with ground truth on only "
                f"{chk['agreement']:.4f} of {chk['checked']} games, below the "
                f"{MIN_GROUND_TRUTH_AGREEMENT} floor: {chk}")
    return out


def validate_against_ground_truth(mapping: dict,
                                  path: Path | None = None) -> dict:
    """Score the derived map against real home_org / away_org.

    `.cache/betting/completed_games.json` carries the truth for 2026 only, so
    this checks one season out of eight. That is a real limit and the caller
    publishes it: the other seasons rest on the internal consistency checks
    (thirty clubs per season, a plausible game count each) rather than on an
    external label.
    """
    p = Path(path or GROUND_TRUTH)
    if not p.exists():
        return {"checked": 0, "agreement": None,
                "why": f"{p} is absent; no external truth to check against"}
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"checked": 0, "agreement": None, "why": f"unreadable: {exc}"}
    home_ok = away_ok = n = 0
    misses = []
    for r in rows:
        gp = r.get("game_pk")
        got = mapping.get(int(gp)) if gp is not None else None
        if not got:
            continue
        n += 1
        if got["home"] == r.get("home_org"):
            home_ok += 1
        elif len(misses) < 10:
            misses.append({"game_pk": gp, "side": "home",
                           "derived": got["home"], "truth": r.get("home_org")})
        if got["away"] == r.get("away_org"):
            away_ok += 1
        elif len(misses) < 10:
            misses.append({"game_pk": gp, "side": "away",
                           "derived": got["away"], "truth": r.get("away_org")})
    return {
        "checked": n,
        "home_correct": home_ok,
        "away_correct": away_ok,
        "agreement": ((home_ok + away_ok) / (2 * n)) if n else None,
        "misses": misses,
        "coverage_note": (
            "ground truth exists for 2026 only, so this checks one season of "
            "eight. The other seasons rest on internal consistency (thirty "
            "clubs per season at a plausible game count), not on an external "
            "label."),
    }


def season_shape(mapping: dict) -> dict:
    """Per season: distinct clubs and games per club. Thirty clubs at roughly
    162 games each is the shape that says the map is sane without needing an
    external label."""
    per = {}
    for g in mapping.values():
        s = per.setdefault(g["season"], {})
        per[g["season"]][g["home"]] = s.get(g["home"], 0) + 1
        per[g["season"]][g["away"]] = per[g["season"]].get(g["away"], 0) + 1
    out = {}
    for season, clubs in sorted(per.items()):
        counts = sorted(clubs.values())
        out[str(season)] = {
            "clubs": len(clubs),
            "games_min": counts[0],
            "games_max": counts[-1],
            "games_median": counts[len(counts) // 2],
        }
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    m = build_map()
    print(f"games attributed: {len(m):,}")
    v = validate_against_ground_truth(m)
    print(f"ground truth: {v['home_correct']}/{v['checked']} home, "
          f"{v['away_correct']}/{v['checked']} away, "
          f"agreement {v['agreement']:.4f}")
    for season, s in season_shape(m).items():
        print(f"  {season}: {s['clubs']} clubs, games per club "
              f"{s['games_min']}-{s['games_max']} (median {s['games_median']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
