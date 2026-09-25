#!/usr/bin/env python
"""Build data/hof_board.json, the payload behind /hof/.

WHAT THIS PAGE IS ALLOWED TO SAY, and it is much less than the module will
eventually say. Four sections ship live and four ship dark, and the dark ones
are dark for reasons that are data problems rather than modelling problems.

LIVE:
  The public benchmark bake-off, AND IT IS A LOSS. Baseball-Reference's own HoF
    Monitor separates the Hall better than our WAR shelf does, by more than this
    sample can resolve, on every one of our columns, surviving a multiplicity
    correction. It ships because the point of benchmarking against the public
    work rather than asserting over it is that the answer is allowed to be
    "theirs is better". The reason is missing data, not modelling: HoF Monitor
    counts batting titles, MVP shares, All-Star selections and postseason play,
    and none of that is in our feature set.
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
BAKEOFF = ROOT / "data" / "hof_bakeoff_eval.json"

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


def _predictor_panel() -> dict:
    """The predictor section. Dark, and now for a MEASURED reason.

    It used to say a merit model had not been gated yet and that "the honest
    expected outcome is a tie". The model has since been built (tools/hof_merit.py,
    H-PRED-3) and the outcome is not a tie, it is a loss, so this reports the
    numbers instead of a forecast. Reading them off the artifact rather than
    restating them keeps the page from drifting the way the FA verdict tooltip did.
    """
    p = ROOT / "data" / "hof_merit_eval.json"
    base = {"live": False, "blocked_on": "H-PRED-3",
            "why": ("No induction probability is published until a merit model has "
                    "passed its own gate against the best public baseline.")}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return base
    if d.get("verdict") == "SHIP":
        return {"live": True, "eval_artifact": "data/hof_merit_eval.json",
                "verdict": d["verdict"], "why": d.get("why")}
    best = d.get("best_public_arm")
    auc = d.get("auc") or {}
    house = {k: v for k, v in auc.items()
             if k not in ("merit", "hof_monitor", "hof_standard",
                          "WAR_career", "WAR_peak7", "JAWS")}
    best_house = max(house, key=house.get) if house else None
    return {
        "live": False,
        "blocked_on": "H-PRED-3",
        "eval_artifact": "data/hof_merit_eval.json",
        "verdict": d.get("verdict"),
        "why": (
            "The merit model lost its gate: AUC " + f"{auc.get('merit', 0):.4f}"
            + " against " + str(best) + " at " + f"{auc.get(best, 0):.4f}"
            + " on " + str(d.get("n_scored")) + " out-of-fold players, a "
            + f"{abs(d.get('delta_auc_vs_best_public', 0)):.4f}"
            + " deficit that clears its detection floor, and Brier "
            + f"{(d.get('calibration') or {}).get('merit', {}).get('brier', 0):.4f}"
            + " against " + f"{(d.get('calibration') or {}).get(best, {}).get('brier', 0):.4f}"
            + ". No induction probability is published on a model that loses to a "
            + "column already on the board."),
        "what_it_does_beat": (
            ("the best our own features produce: AUC "
             + f"{auc.get('merit', 0):.4f}" + " against " + f"{house.get(best_house, 0):.4f}"
             + " for " + str(best_house) + ", the strongest single in-house column. "
             + "The gap to " + str(best) + " is missing data, not modelling: that "
             + "metric counts batting titles, MVP shares, All-Star selections and "
             + "postseason play, none of which is in our feature set.")
            if best_house else None),
    }


def _bakeoff_panel() -> dict:
    """The public benchmark bake-off, reduced to what a reader needs.

    IT IS A LOSS AND IT SHIPS AS ONE. The point of benchmarking against the
    public work rather than asserting over it is that the answer is allowed to
    be "their column is better", and this panel says so in the first sentence.
    Only the primary label reaches the page: label_any's shelf hole is all
    positives and no negatives, so its pooled comparison is refused upstream
    and a refused comparison has no business on a page.
    """
    if not BAKEOFF.exists():
        return {"live": False, "blocked_on": "docs/HOF_BAKEOFF_GATE.md",
                "why": ("The public benchmark bake-off has not been run under its "
                        "gate, so this page makes no claim on whether our shelf "
                        "separates the Hall better or worse than "
                        "Baseball-Reference's HoF Monitor.")}
    d = json.loads(BAKEOFF.read_text(encoding="utf-8"))
    b = d["labels"][d["primary_label"]]
    disc = b["discrimination_full_frame"]
    fam = disc["families"]["resampled_public_argmax"]
    arms = sorted(disc["per_arm"].items(), key=lambda kv: -kv[1]["auc"])
    rows = []
    for a, c in arms:
        cell = fam["cells"].get(a) or {}
        fl = cell.get("floor_E_cond_in_run") or {}
        rows.append({
            "arm": a,
            "is_public": a in ("hof_monitor", "hof_standard", "WAR_career",
                               "WAR_peak7", "JAWS"),
            "auc": c["auc"],
            "tied_pair_share": c.get("tied_pair_share"),
            "delta_vs_best_public": fl.get("point_delta"),
            "mde95": fl.get("mde95"),
            "verdict": cell.get("verdict"),
        })
    cal = b["calibration"]
    # The headline's counts are read off the rows and the Holm block, never typed.
    house = [r for r in rows if not r["is_public"]]
    n_lose = sum(1 for r in house
                 if r["delta_vs_best_public"] is not None and r["mde95"] is not None
                 and r["delta_vs_best_public"] < -r["mde95"])
    keys = {r["arm"] for r in house}
    holm = [c for c in ((fam.get("holm") or {}).get("cells") or [])
            if c.get("key") in keys]
    n_holm = sum(1 for c in holm if c.get("reject_holm"))

    def _of(k, n):
        return f"all {n}" if k == n else f"{k} of {n}"

    return {
        "live": True,
        "gate_doc": "docs/HOF_BAKEOFF_GATE.md",
        "gate_frozen": d.get("gate_frozen"),
        "label": d["primary_label"],
        "n": b["frame"]["n_scored"],
        "n_positive": b["frame"]["n_positive"],
        "base_rate": b["frame"]["base_rate"],
        "best_public": disc["public_argmax"],
        "best_public_auc": disc["per_arm"][disc["public_argmax"]]["auc"],
        "rows": rows,
        "headline": (
            "Baseball-Reference's Hall of Fame Monitor separates the Hall better "
            "than our WAR shelf does. " + _of(n_lose, len(house)).capitalize()
            + " in-house columns lose to it by more than their detection floor"
            + (f", and {_of(n_holm, len(holm))} survive a Holm correction."
               if holm else ".")),
        "why_it_loses": (
            "HoF Monitor counts batting titles, MVP shares, All-Star selections and "
            "postseason play, and none of that is in our feature set: the gap is "
            "missing data, not modelling."),
        "population_note": b["frame"]["population_note"],
        "calibration": {
            "n_cells_clearing_holm": cal.get("n_cells_clearing_holm"),
            "n_cells": cal.get("n_cells"),
            "note": (
                "the same column has the lowest pooled Brier. The calibration-error "
                "leg resolves nothing; Brier and log loss resolve, every resolved "
                "cell the same way."),
        },
        # Rendered after "It does not show ", so this stays a clause.
        "what_it_does_not_show": (
            "that our shelf is wrong: it reproduces the public WAR shelf almost "
            "exactly. WAR alone orders Hall of Fame outcomes less well than a rule "
            "that also counts awards and postseason play."),
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
        "no field here says what a plaque says: the source records the "
        f"ELECTORATE that voted. {len(unverified_in_E)} inductees in the "
        "eligible universe carry a route we cannot verify, among them Connie "
        "Mack, Casey Stengel, Joe Torre, John McGraw, Clark Griffith, Miller "
        "Huggins, Ned Hanlon and Bill McKechnie, so a line sized on that count "
        "is not a player line. Excluding them makes each a resolved zero, and "
        "the page would then say Joe Torre is above the Hall line and not in "
        "the Hall of Fame.")

    out = {
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
                                    "from_hand_bridge", "unresolved")},
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
                f"roughly 1930: the catcher class holds {n_catchers} eligible "
                f"players, {n_catchers_pre1930} of them starting before 1930. "
                f"{n_rate_basis} rows fall back to the positional-rate basis, "
                f"{n_rate_pre53} of them last playing before 1953, when the "
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
                "A reproduction of a public shelf, not an improvement on it. The "
                "large disagreements are Negro Leagues and pre-1901 players, where "
                "the two sources count different seasons."),
        },

        "coverage": {
            "n_eligible_with_no_ballot_page": n_no_shelf,
            "why_a_blank_public_column_is_not_a_zero": (
                "A blank HoF Monitor or HoF Standards cell means the player never "
                "reached a Hall of Fame election page, so Baseball-Reference "
                "published no value. It is not a zero."),
            "war_ink_is_ours": (
                "WAR ink is ours, NOT Bill James's Black Ink or Gray Ink: "
                f"{hd.INK_LEAD_POINTS} points for a league-leading WAR season, "
                f"{hd.INK_TOPTEN_POINTS} for a top-{hd.INK_TOPTEN_DEPTH} season, "
                "hitters and pitchers ranked in one pool per league-season. Not "
                "comparable to a published Black Ink number."),
            "position_basis": (
                "Position class comes from the fielding run components from 1953 "
                "on and from the positional adjustment rate before that. Every "
                "pre-1930 catcher is misfiled; the basis column names the method "
                "for each row."),
            "induction_column": (
                "A writers' election as a player is the only induction this page "
                "can verify. Every other route reads route unverified: the source "
                "records the electorate, not the plaque. Hence no Hall line and no "
                "snub list."),
        },

        "leaderboard": [_row(r, b, shelf) for _, r in eligible.iterrows()],
        "watch": [_row(r, b, shelf) for _, r in watch.iterrows()],
        "not_yet_eligible": [_row(r, b, shelf) for _, r in nye.iterrows()],

        "sections": {
            "leaderboards": {"live": True},
            "quantile_ladder": {"live": True},
            "watch": {"live": True, "projection": False,
                      "why_no_projection": (
                          "Active players ranked by what they have already done, "
                          "on the retired board's shelf. A pace curve needs a "
                          "per-age remaining-career WAR model, a forward backtest "
                          "on retired players and a year-filtered feature frame; "
                          "none exists yet, so this page does not guess.")},
            # The band edges are read off the constants that cut the bands.
            "not_yet_eligible": {"live": True,
                                 "why": (
                                     f"{MIN_SEASONS}+ seasons, last played "
                                     f"{AS_OF - WAIT_YEARS + 1} to {ACTIVE_FROM - 1}: "
                                     f"inside the {WAIT_YEARS}-year wait, so on "
                                     "neither the eligible board nor the active "
                                     "board.")},
            "deserved": {"live": False, "blocked_on": "H-DATA-PLAQUE",
                         "why": blocked},
            "bakeoff": _bakeoff_panel(),
            "predictor": _predictor_panel(),
            "franchises": {"live": False, "blocked_on": "no franchise spine",
                           "why": ("The season frame carries no team column and "
                                   "there is no franchise continuity map. "
                                   "Crediting a multi-team career also needs a "
                                   "frozen attribution rule with the rejected "
                                   "alternative named.")},
        },

        "what_this_page_does_not_claim": None,
    }
    # DERIVED, not typed: the sentence used to say "four of its eight sections are
    # dark" and went false the day the bake-off went live.
    secs = out.get("sections") or {}
    n_dark = sum(1 for v in secs.values() if isinstance(v, dict) and not v.get("live"))
    out["what_this_page_does_not_claim"] = (
        "that it knows who belongs in the Hall of Fame, that it knows what a "
        "plaque says, or that its WAR shelf is better than the public one it "
        f"reproduces. {n_dark} of its {len(secs)} sections are dark and each says "
        "what it is blocked on.")
    return out


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
