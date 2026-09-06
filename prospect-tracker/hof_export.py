#!/usr/bin/env python
"""Build data/hof_board.json, the payload behind /hof/.

WHAT THIS PAGE IS ALLOWED TO SAY, and it is much less than the module will
eventually say. Four sections ship live and four ship dark, and the dark ones
are dark for reasons that are data problems rather than modelling problems.

LIVE:
  Cooperstown Leaderboards. Baseball-Reference's own career WAR, WAR7 and JAWS,
    reproduced from the same daily WAR file they publish from. This is a
    REPRODUCTION OF A PUBLIC SHELF, not an improvement on it, and the page says
    so in those words.
  The JAWS quantile ladder. Honest without knowing the size of the Hall, which
    is exactly why it ships where the Hall-sized line does not.
  Cooperstown Watch. Active players ranked by what they have ALREADY DONE. It
    carries no projection and no induction odds.
  Not Yet Eligible. The 141 players with ten or more seasons who last played in
    2022, 2023 or 2024. Without this band Albert Pujols, Zack Greinke, Robinson
    Cano, Miguel Cabrera and Joey Votto appear on neither board, and they are
    the single most likely thing a reader opens this page to look up.

DARK, each with its blocker named on the page:
  Deserved vs Inducted, and the Hall-sized line with it. A Hall-SIZED line needs
    the count of players inducted AS PLAYERS, and no plaque-role field exists in
    this repo. The source records the ELECTORATE that voted; at least fifteen
    manager and executive plaques reach the eligible universe. A line sized on a
    Hall that counts Connie Mack and Casey Stengel is not a player line, and
    excluding them does not help: dropping a contributor from the ledger does
    not unlabel him, it makes him a resolved zero, and the page would then
    publish that Joe Torre is above the line and not in the Hall of Fame.
  The by-class line, additionally, because position_class misfiles every catcher
    who retired before roughly 1930.
  The benchmark bake-off, until its gate doc is read.
  The predictor, until H-PRED-3 passes its ship rule.
  Franchises, because there is no franchise spine and no frozen attribution rule
    for a multi-team career.

EVERY STRING THE PAGE RENDERS IS BUILT HERE. No figure is typed into HTML or JS.

Deterministic and offline. Run:  python hof_export.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import hof_data as hd                              # noqa: E402

OUT = ROOT / "data" / "hof_board.json"
SHELF = ROOT / "data" / "hof_public_benchmarks.json"
REPRO = ROOT / "data" / "hof_benchmark_repro.json"
LEDGER = ROOT / "data" / "hof_ledger_eval.json"

AS_OF = 2026
ACTIVE_FROM = 2025           # last_season at or after this is "active"
WAIT_YEARS = 5               # the five-year wait, so 2022-2024 is the gap band
MIN_SEASONS = 10             # the eligibility floor hof_data already applies

QUANTILES = (0.50, 0.75, 0.90, 0.95, 0.99)

_R = hd.round_half_up


def _f(v, nd=1):
    """A published float, half-up, or None. FV-style rounding is deliberate:
    every number on this page is compared against a Baseball-Reference page that
    rounds the same way."""
    try:
        if v is None or v != v:
            return None
        return _R(float(v), nd)
    except (TypeError, ValueError):
        return None


def _shelf() -> dict:
    if not SHELF.exists():
        return {}
    d = json.loads(SHELF.read_text(encoding="utf-8"))
    out = {}
    for r in d.get("rows") or []:
        pid = r.get("player_id")
        if pid:
            out[pid] = r
    return out


def _induction_state(pid, b, shelf_row):
    """THREE STATES, NOT TWO, and the third is the honest one.

    `player_bbwaa` is a ballot-table election by the writers, which is
    unambiguously an induction as a player. `route_unverified` is every other
    resolved induction, because the source records which electorate voted and
    never what the plaque says. `none` is everybody else, and it carries whether
    the label is resolved or still censored so a reader is not told that a
    player still on the ballot has been rejected.
    """
    ind = (b.get("inducted") or {}).get(pid)
    if ind is None:
        return "none", None, None
    won = any(r.get("elected") for r in (b.get("by_pid") or {}).get(pid) or [])
    year = ind.get("election_year")
    return ("player_bbwaa" if won else "route_unverified",
            int(year) if year else None,
            ind.get("route"))


def _row(r, b, shelf):
    pid = r["player_ID"]
    s = shelf.get(pid) or {}
    state, iyear, iroute = _induction_state(pid, b, s)
    return {
        "id": pid,
        "name": r["name"],
        "first": int(r["first_season"]),
        "last": int(r["last_season"]),
        "seasons": int(r["n_seasons"]),
        "war": _f(r["career_war"]),
        "waa": _f(r["career_waa"]),
        "war7": _f(r["war7"]),
        "jaws": _f(r["jaws"]),
        "waa_pos": _f(r["waa_pos"]),
        "ink": _f(r["ink"], 0),
        "pos": r["pos_class"],
        "pos_basis": r["pos_basis"],
        # PUBLIC COLUMNS, and a blank is not a zero: a player who never reached
        # a Hall of Fame election page has no published value at all.
        "monitor": _f(s.get("hof_monitor"), 0),
        "standards": _f(s.get("hof_standard"), 0),
        "induction": state,
        "induction_year": iyear,
        "induction_route": iroute,
    }


def _shelf_agreement(cf, shelf) -> dict:
    """How close our reproduction is to Baseball-Reference's own published WAR.

    Measured on the players who HAVE a published value, which is the only
    population where the question is answerable, and reported with that
    population's size beside it rather than as a bare percentage.
    """
    n, exact, within, diffs = 0, 0, 0, []
    worst = []
    for _, r in cf.iterrows():
        s = shelf.get(r["player_ID"])
        if not s or s.get("WAR_career") is None:
            continue
        pub = float(s["WAR_career"])
        ours = float(r["career_war"])
        n += 1
        d = abs(_R(ours, 1) - _R(pub, 1))
        diffs.append(d)
        if d == 0:
            exact += 1
        if d <= 0.1:
            within += 1
        worst.append((d, r["player_ID"], r["name"], _R(ours, 1), _R(pub, 1)))
    worst.sort(reverse=True)
    return {
        "n_with_a_published_value": n,
        "n_exact_on_career_war": exact,
        "n_within_a_tenth": within,
        "mean_absolute_difference": _R(sum(diffs) / n, 2) if n else None,
        "largest_disagreements": [
            {"id": w[1], "name": w[2], "ours": w[3], "published": w[4],
             "difference": _R(w[0], 1)} for w in worst[:12]],
    }


def build() -> dict:
    hd.clear_cache()
    b = hd.ballots()
    cf = hd.career_frame(offline=True)
    shelf = _shelf()

    ten = cf[cf["n_seasons"] >= MIN_SEASONS]
    eligible = cf[cf["eligible"]].copy()
    watch = ten[ten["last_season"] >= ACTIVE_FROM].copy()
    nye = ten[(ten["last_season"] >= AS_OF - WAIT_YEARS + 1)
              & (ten["last_season"] < ACTIVE_FROM)].copy()

    for f in (eligible, watch, nye):
        f.sort_values("jaws", ascending=False, inplace=True)

    lab = hd.label_frame(offline=True, as_of_year=AS_OF, ballots_=b)

    qs = {}
    j = eligible["jaws"].dropna()
    for q in QUANTILES:
        qs[f"{q:.2f}"] = _f(j.quantile(q))

    ledger = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {}
    repro = json.loads(REPRO.read_text(encoding="utf-8")) if REPRO.exists() else {}
    agree = _shelf_agreement(cf, shelf)

    res = b.get("resolution") or {}
    unverified = res.get("plaque_role_unverified") or []
    uni = set(eligible["player_ID"])
    unverified_in_E = [r for r in unverified if r["player_id"] in uni]

    n_rate_basis = int((eligible["pos_basis"] == "positional_rate").sum())
    n_rate_pre53 = int(((eligible["pos_basis"] == "positional_rate")
                        & (eligible["last_season"] < 1953)).sum())
    n_catchers = int((eligible["pos_class"] == "C").sum())
    n_catchers_pre1930 = int(((eligible["pos_class"] == "C")
                              & (eligible["first_season"] < 1930)).sum())
    n_no_shelf = sum(1 for p in uni if p not in shelf)

    blocked = (
        "A Hall-sized line needs the count of players inducted AS PLAYERS, and "
        "no field in this data says what a plaque says. The source records the "
        f"ELECTORATE that voted, and {len(unverified_in_E)} inductees inside the "
        "eligible universe carry a route we cannot verify, among them Connie "
        "Mack, Casey Stengel, Joe Torre, John McGraw, Clark Griffith, Miller "
        "Huggins, Ned Hanlon and Bill McKechnie. A line sized on a Hall that "
        "counts them is not a player line. Excluding them does not fix it "
        "either: dropping a contributor from the ledger does not unlabel him, "
        "it makes him a resolved zero, and this page would then be publishing "
        "that Joe Torre is above the Hall line and not in the Hall of Fame.")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "produced_by": "hof_export.py",
        "as_of_year": AS_OF,
        "basis": {
            "war": "Baseball-Reference bWAR, war_daily, the same file they publish from",
            "eligible_universe": ("at least ten seasons carrying a WAR row, and a last "
                                  f"season at least {WAIT_YEARS} years back"),
            "jaws": "the mean of career WAR and WAR7, which is the published definition",
        },

        "counts": {
            "n_career_frame": int(len(cf)),
            "n_ten_plus_seasons": int(len(ten)),
            "n_eligible": int(len(eligible)),
            "n_watch": int(len(watch)),
            "n_not_yet_eligible": int(len(nye)),
            "bands_partition_the_ten_plus_population": bool(
                len(eligible) + len(watch) + len(nye) == len(ten)),
        },

        "ledger": {
            "n_statsapi_inductees": (ledger.get("ledger") or {}).get("n_statsapi"),
            "n_resolved_to_bbref": (ledger.get("ledger") or {}).get("n_resolved_after"),
            "n_in_eligible_universe": sum(1 for p in b.get("inducted") or {} if p in uni),
            "resolution": {k: v for k, v in res.items()
                           if k in ("from_ballot_tables", "from_mlbam_crosswalk",
                                    "unresolved")},
            "unresolved_names": res.get("unresolved_names") or [],
            "plaque_role_unverified": {
                "n": len(unverified),
                "n_in_eligible_universe": len(unverified_in_E),
                "players": unverified_in_E[:60],
                "blocking_lane": "H-DATA-PLAQUE",
            },
        },

        "labels": {
            "label_any": {"positive": int((lab["label_any"] == 1).sum()),
                          "negative": int((lab["label_any"] == 0).sum()),
                          "censored": int(lab["label_any"].isna().sum())},
            "label_bbwaa": {"positive": int((lab["label_bbwaa"] == 1).sum()),
                            "negative": int((lab["label_bbwaa"] == 0).sum()),
                            "censored": int(lab["label_bbwaa"].isna().sum())},
            "n_rows": int(len(lab)),
        },

        "line": {
            "pooled": None,
            "quantiles": qs,
            "blocked_because": blocked,
            "by_class": None,
            "by_class_blocked_because": (
                "position class misfiles every catcher who retired before "
                f"roughly 1930. The catcher class holds {n_catchers} players in "
                f"the eligible universe and {n_catchers_pre1930} of them started "
                "before 1930, which is not a fact about catchers. "
                f"{n_rate_basis} rows fall back to the positional-rate basis and "
                f"{n_rate_pre53} of those last played before 1953, when the "
                "fielding run components begin."),
        },

        "deserved": None,
        "deserved_blocked_because": blocked,

        "reproduction": {
            "hand_checked": {
                "n_players": repro.get("n_players"),
                "n_comparisons": repro.get("n_comparisons"),
                "n_exact": repro.get("n_comparisons_exact"),
                "all_exact": repro.get("all_exact"),
            },
            "against_the_public_shelf": agree,
            "what_it_means": (
                "this is a reproduction of a public shelf, not an improvement on "
                "it. The large disagreements sit in the Negro Leagues and "
                "pre-1901 population, where the two sources count different "
                "seasons."),
        },

        "coverage": {
            "n_eligible_with_no_ballot_page": n_no_shelf,
            "why_a_blank_public_column_is_not_a_zero": (
                "a blank HoF Monitor or HoF Standards cell means the player "
                "never appeared on a Hall of Fame election page, so "
                "Baseball-Reference published no value for him. It does not "
                "mean zero."),
            "war_ink_is_ours": (
                "WAR ink is ours and it is NOT Bill James's Black Ink or Gray "
                "Ink. It scores four points for a league-leading WAR season and "
                "one for a top-ten season, ranking hitters and pitchers in a "
                "single pool per league-season. Do not read it next to a "
                "published Black Ink number."),
            "position_basis": (
                "position class is inferred from the fielding run components "
                "where they exist, which is 1953 and later, and from the "
                "positional adjustment rate before that. Every pre-1930 catcher "
                "on this page is misfiled, and the basis column says which "
                "method produced each row."),
            "induction_column": (
                "inducted as a player by the writers is the only induction this "
                "page can verify from its own data. Every other route reads as "
                "route unverified, because the source records which electorate "
                "voted and not what the plaque says. That is why this page "
                "publishes no Hall line and no snub list."),
        },

        "leaderboard": [_row(r, b, shelf) for _, r in eligible.iterrows()],
        "watch": [_row(r, b, shelf) for _, r in watch.iterrows()],
        "not_yet_eligible": [_row(r, b, shelf) for _, r in nye.iterrows()],

        "sections": {
            "leaderboards": {"live": True},
            "quantile_ladder": {"live": True},
            "watch": {"live": True, "projection": False,
                      "why_no_projection": (
                          "this board ranks active players by what they have "
                          "already done, against the same shelf as the retired "
                          "board. A pace curve needs a per-age remaining-career "
                          "WAR model, a backtest run forward on players who have "
                          "already retired, and a year-filtered feature frame. "
                          "None of those three exists yet, so this page does not "
                          "guess.")},
            "not_yet_eligible": {"live": True,
                                 "why": (
                                     "these players have ten or more seasons and "
                                     "last played in 2022, 2023 or 2024, so they "
                                     "have not cleared the five-year wait and are "
                                     "on neither the eligible board nor the "
                                     "active board.")},
            "deserved": {"live": False, "blocked_on": "H-DATA-PLAQUE",
                         "why": blocked},
            "bakeoff": {"live": False, "blocked_on": "docs/HOF_BAKEOFF_GATE.md",
                        "why": ("the public benchmark bake-off has not been run "
                                "under its gate. Until it has, this page makes no "
                                "claim about whether our shelf separates the Hall "
                                "better or worse than Baseball-Reference's own "
                                "HoF Monitor.")},
            "predictor": {"live": False, "blocked_on": "H-PRED-3",
                          "why": ("no induction probability is published until a "
                                  "merit model has passed its own gate against "
                                  "the best public baseline. The public baselines "
                                  "are already near the ceiling on this label, so "
                                  "the honest expected outcome is a tie.")},
            "franchises": {"live": False, "blocked_on": "no franchise spine",
                           "why": ("the season frame carries no team column and "
                                   "there is no franchise continuity map in this "
                                   "repo. Beyond the map, crediting a multi-team "
                                   "career needs a frozen attribution rule with "
                                   "the rejected alternative named, which is a "
                                   "gate and not a query.")},
        },

        "what_this_page_does_not_claim": (
            "that it knows who belongs in the Hall of Fame, that it knows what a "
            "plaque says, or that its WAR shelf is better than the public one it "
            "reproduces. Four of its eight sections are dark and each says what "
            "it is blocked on."),
    }


def main() -> int:
    d = build()
    OUT.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    c = d["counts"]
    print(f"wrote {OUT.relative_to(ROOT)}  ({OUT.stat().st_size / 1e6:.2f} MB)")
    print(f"  eligible {c['n_eligible']}  watch {c['n_watch']}  "
          f"not yet eligible {c['n_not_yet_eligible']}")
    print(f"  bands partition the 10+ population: "
          f"{c['bands_partition_the_ten_plus_population']}")
    a = d["reproduction"]["against_the_public_shelf"]
    print(f"  shelf agreement: {a['n_exact_on_career_war']} exact and "
          f"{a['n_within_a_tenth']} within a tenth of "
          f"{a['n_with_a_published_value']}, mean |diff| "
          f"{a['mean_absolute_difference']}")
    print(f"  live sections: "
          f"{sorted(k for k, v in d['sections'].items() if v['live'])}")
    print(f"  dark sections: "
          f"{sorted(k for k, v in d['sections'].items() if not v['live'])}")
    if not c["bands_partition_the_ten_plus_population"]:
        print("  REFUSING: the three bands do not partition the population, so a "
              "player is on two boards or on none")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
