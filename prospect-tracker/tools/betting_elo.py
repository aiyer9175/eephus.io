# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""betting_elo.py - a results-only Elo baseline for the benchmark ladder.

WHAT THIS IS FOR, AND WHAT IT MUST NEVER BE. The vintage backtest's benchmark
ladder (docs/diamond-betting.md section 6, pre-registered 2026-08-16) needs a
results-only floor: the probability a model earns from nothing but wins and
losses. A feature model that cannot beat this has features that are not paying
for themselves. It is a VALIDATION LADDER TIER ONLY - no served price, no slot,
no record row reads it, and the registry row (betting_elo_benchmark) says so.

THE CONFIGURATION IS A LITERATURE PRIOR, NEVER A FIT. Base rating 1500, K = 4,
home advantage 24 Elo points: the standard published MLB Elo constants
(FiveThirtyEight's long-running MLB Elo used K = 4 and a home advantage of ~24
points). They are deliberately NOT fitted on the eval window, or on anything
else here, because a ladder tier that tunes itself on the window it grades is
the exact leakage the ladder exists to expose in others. If somebody wants a
fitted Elo, that is a different model with its own gate section; this one's
honesty property is that it has zero free parameters touched by our data.

LEAK-FREENESS BY CONSTRUCTION. The walk is chronological and a game's
probability is computed BEFORE its own update, so every prediction uses only
strictly-prior results. Ratings start flat at the base every season, with no
carryover, because the completed-games cache this consumes is single-season by
construction (betting_model._topup_game_cache anchors to one season) and an
offseason is a real information boundary the leaderboards also reset across.
A flat April start makes early-season Elo weak, which is honest: that is what
a results-only model knows in April.

CLI:
    python tools/betting_elo.py            # walk the cached season, report Brier
"""
from __future__ import annotations

# The literature configuration, labelled as such. See the module docstring:
# these are priors from the published MLB Elo literature and are never fitted
# on anything in this repository.
LITERATURE_K = 4.0
LITERATURE_HOME_ADV_ELO = 24.0
BASE_RATING = 1500.0


def elo_win_prob(r_home: float, r_away: float,
                 home_adv: float = LITERATURE_HOME_ADV_ELO) -> float:
    """P(home win) from two ratings, the standard logistic-in-base-10 form."""
    return 1.0 / (1.0 + 10.0 ** (-((r_home - r_away + home_adv) / 400.0)))


def elo_probabilities(games: list[dict], *, k: float = LITERATURE_K,
                      home_adv: float = LITERATURE_HOME_ADV_ELO,
                      base: float = BASE_RATING) -> dict:
    """{game_pk: p_home} over a chronological walk of completed games.

    Each game's probability is computed from the ratings AS THEY STOOD before
    that game, then the game's result updates them: r_home += K*(y - p),
    r_away -= K*(y - p). Nothing later than a game can reach its prediction,
    which is the same strictly-before property the vintage store enforces for
    features, earned here by iteration order alone.

    `games` is expected to be ONE season of betting_model's compact rows
    (game_pk, date, home_org, away_org, home_runs, away_runs). Rows missing a
    side or a score are skipped and neither predicted nor learned from."""
    ratings: dict[str, float] = {}
    out: dict = {}
    for g in sorted(games or [],
                    key=lambda r: (r.get("date") or "", r.get("game_pk") or 0)):
        h, a = g.get("home_org"), g.get("away_org")
        hr, ar = g.get("home_runs"), g.get("away_runs")
        if not h or not a or hr is None or ar is None:
            continue
        r_h, r_a = ratings.get(h, base), ratings.get(a, base)
        p = elo_win_prob(r_h, r_a, home_adv)
        pk = g.get("game_pk")
        if pk is not None:
            out[pk] = p
        y = 1.0 if int(hr) > int(ar) else 0.0
        delta = k * (y - p)
        ratings[h] = r_h + delta
        ratings[a] = r_a - delta
    return out


def final_ratings(games: list[dict], *, k: float = LITERATURE_K,
                  home_adv: float = LITERATURE_HOME_ADV_ELO,
                  base: float = BASE_RATING) -> dict:
    """{org: rating} after walking the games. Diagnostic only."""
    ratings: dict[str, float] = {}
    for g in sorted(games or [],
                    key=lambda r: (r.get("date") or "", r.get("game_pk") or 0)):
        h, a = g.get("home_org"), g.get("away_org")
        hr, ar = g.get("home_runs"), g.get("away_runs")
        if not h or not a or hr is None or ar is None:
            continue
        r_h, r_a = ratings.get(h, base), ratings.get(a, base)
        p = elo_win_prob(r_h, r_a, home_adv)
        y = 1.0 if int(hr) > int(ar) else 0.0
        delta = k * (y - p)
        ratings[h] = r_h + delta
        ratings[a] = r_a - delta
    return ratings


if __name__ == "__main__":                                       # pragma: no cover
    import json
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))
    import betting_model as bm

    games = bm.completed_games(refresh=False)
    probs = elo_probabilities(games)
    pairs = [(probs[g["game_pk"]], 1 if g["home_runs"] > g["away_runs"] else 0)
             for g in games if g.get("game_pk") in probs]
    brier = (sum((p - y) ** 2 for p, y in pairs) / len(pairs)) if pairs else None
    print(json.dumps({
        "n_games": len(pairs),
        "brier": round(brier, 5) if brier is not None else None,
        "config": {"k": LITERATURE_K, "home_adv_elo": LITERATURE_HOME_ADV_ELO,
                   "base": BASE_RATING, "standing": "literature priors, never fitted"},
        "top": sorted(final_ratings(games).items(), key=lambda t: -t[1])[:5],
    }, indent=1))
