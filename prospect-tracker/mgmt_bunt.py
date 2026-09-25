#!/usr/bin/env python
"""The sacrifice bunt: the second decision family on /management/.

WHY A SECOND FAMILY AT ALL. The page's own copy says it: "the running game is one
decision family and the null it returned is about the running game". A bounded null on
stolen bases says nothing about whether managers give away value with the bunt, and
publishing one family while calling the section "In-Game Management" overstated the
coverage. This is the second family, priced on the same substrate.

THE COUNTERFACTUAL IS MEASURED, NOT MODELLED, and that is what makes it buildable today.
A proper per-batter bunt model needs the plate-appearance outcome engine the plan calls
M-ENG-1, which does not exist. What DOES exist is the corpus itself, so the alternative to
bunting is priced the way the running game prices the alternative to running: league-wide,
from the same pre-decision state.

    DV(S) = E[WE | bunt called from S] - E[WE | any other plate appearance from S]

Both sides are EXPECTATIONS over league outcomes from the identical base-out-score state.
Neither is the realized win-probability change of the play in front of you: realized WPA
is an outcome metric and the gate doc forbids it entering a decision metric. Every bunt
from the same state therefore carries the same decision value, which is the point. What
the manager chose is worth what it is worth; how it happened to turn out is a different
question.

THE SELECTION PROBLEM IS REAL AND IS NOT SOLVED HERE, so it is stated instead. Managers
bunt with the batters they least want swinging: pitchers, and the bottom of the order. So
`E[WE | bunt]` is measured over a WEAKER population of batters than `E[WE | swing]`, and
the difference therefore prices THE BUNT AS DEPLOYED rather than the bunt as a tactic.
Read as "what the league's bunting has been worth", it is sound. Read as "what bunting
would be worth if you did it with an average hitter", it is biased against the bunt, and
this module will not make that second claim.

TWO OUTS IS EXCLUDED for the reason management.py gives at length: with two down, an out
ends the half-inning and its value comes from the measured half-inning-start table while
the alternative comes from the smooth model. Those are two estimators and nothing
calibrates them against each other, so their difference has no guaranteed sign. A sacrifice
with two outs is also nearly nonexistent, so the exclusion costs almost nothing.

Deterministic.  python mgmt_bunt.py [--seasons 2018,2019]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CORPUS = ROOT / ".cache" / "pbp_corpus"
OUT = ROOT / "data" / "management_bunt.json"

#: The event the manager called. StatsAPI records the sacrifice explicitly.
BUNT_EVENTS = ("Sac Bunt",)
#: Bunt attempts that did NOT sacrifice successfully still belong to the decision:
#: the manager called the same play. A bunt into a double play is the decision's
#: downside, not a different decision.
BUNT_ALSO = ("Bunt Groundout", "Bunt Pop Out", "Bunt Lineout",
             "Sac Bunt Double Play", "Bunt Ground Out", "Bunt Popout")
#: A BUNT IS READ OFF THE BALL, NOT THE RESULT NAME (audit M10-02). The two lists
#: above name only bunts that ended in an out or a sacrifice. A bunt single reads
#: "Single", a bunt the fielder threw away "Field Error", a bunt turned into a
#: force "Forceout", so selecting on those names filed every bunt that WORKED
#: under the alternative, and the bases-empty cells could only hold outs. The
#: corpus now flags every plate appearance that ended on a bunt
#: (tools/build_pbp_corpus.is_bunted: the in-play pitch's hitData trajectory is
#: bunt_*, the result is one of the names above, or strike three came on a foul or
#: missed bunt), and that flag is the side.
BUNT_HIT_EVENTS = ("Single", "Double", "Triple")
#: A state needs this many of BOTH kinds before its cell is priced. Below it the
#: difference of two means is noise wearing a decimal point.
MIN_CELL = 25
MAX_OUTS = 1                    # two outs excluded; see the module docstring


def _load_plays(corpus: Path, seasons=None):
    import pandas as pd
    pl_dir = Path(corpus) / "plays"
    if not pl_dir.exists():
        return None
    want = list(seasons) if seasons else sorted(
        p.name for p in pl_dir.iterdir() if p.is_dir())
    frames = []
    for s in want:
        for f in sorted((pl_dir / s).glob("*.parquet")):
            frames.append(pd.read_parquet(f))
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def _state(df):
    """base_before (0-7), score_diff (home minus away) BEFORE the play, and the
    outs guard.

    THE SCORE IS PRE-PLAY (audit F07-02). The corpus score columns are the score
    AFTER the play, so reading them raw put both endpoints of every bunt
    comparison one run or more hotter than the state the manager actually faced.
    The delta across the two calls was still right, which is why the family's
    sign survived, but the level was wrong and the level is where the urgency
    interaction lives.
    """
    import numpy as np
    import win_expectancy as wx
    df = df.copy()
    # notna(), never astype(bool): these hold a runner id as float with NaN for
    # empty, and bool(NaN) is True, which reports every base occupied. That
    # defect cost the win expectancy table its first build.
    df["base_before"] = (df["on_first"].notna().astype(int)
                         + 2 * df["on_second"].notna().astype(int)
                         + 4 * df["on_third"].notna().astype(int))
    df["score_diff"] = wx.pre_play_score_diff(df)
    return df


def _attach_base_after(df):
    """The base state AFTER each play, taken from the NEXT play in the same half.

    THIS IS THE WHOLE CORRECTION, and getting it wrong inverted the family's
    verdict. A first cut priced every play's POST-play win expectancy while
    passing the PRE-play base state, so a single read as "nothing happened, no
    outs" while a bunt's out was counted in full. That undervalues the
    swing-away alternative far more than it undervalues the bunt, and it
    manufactured a +297-win endorsement of bunting that contradicts both the
    literature and the corpus's own realized WPA (bunts -0.139, alternatives
    +0.161 on the same rows).

    `on_first/on_second/on_third` are the state BEFORE a play, so the next
    at-bat in the same half-inning carries the state this one produced. The last
    play of a half-inning has no successor, and needs none: it ended the inning,
    outs reach three, and management._we_after switches to the measured
    half-inning-start boundary rather than reading a base state at all.
    """
    import numpy as np
    df = df.sort_values(["game_pk", "inning", "half", "at_bat_index"]).copy()
    grp = df.groupby(["game_pk", "inning", "half"], sort=False)
    nxt = grp["base_before"].shift(-1)
    df["base_after"] = nxt
    df["ends_half"] = nxt.isna()
    # where the half continues, the successor state is real; where it ends, the
    # value comes from the boundary and the base state is unused
    df["base_after"] = df["base_after"].fillna(0).astype(int)
    return df


def _we_after_play(W, row):
    """Offensive win expectancy AFTER this plate appearance.

    Post-play BASE state, pre-play outs plus the out delta, and the runs the play
    actually scored. management._we_after owns the third out and the terminal
    ninth-inning conditions.
    """
    import management as M
    return M._we_after(W, int(row["inning"]), str(row["half"]),
                       int(row["score_diff"]), int(row["outs_before"]),
                       int(row["base_after"]),
                       runs=int(row.get("runs_scored_on_play") or 0),
                       out_added=int(row["outs_after"]) - int(row["outs_before"]))


def price(*, corpus: Path | None = None, seasons=None, we=None) -> dict:
    """The bunt family, priced per base-out state and summed over the league."""
    import numpy as np
    import pandas as pd
    import win_expectancy as wx

    corpus = Path(corpus or CORPUS)
    df = _load_plays(corpus, seasons)
    if df is None or df.empty:
        return {"status": f"not built: no play corpus at {corpus}"}
    if "bunted" not in df.columns:
        # Refused, not guessed: the result names alone select on the outcome.
        return {"status": ("not built: the play corpus predates its bunted column; "
                           "rebuild it with python tools/build_pbp_corpus.py --force")}
    W = we or wx.WinExpectancy.load()
    df = _state(df)
    df = _attach_base_after(df)

    excluded = {"two_outs": 0, "unpriceable_state": 0, "thin_cell": 0}
    excluded["two_outs"] = int((df["outs_before"] > MAX_OUTS).sum())
    df = df[df["outs_before"] <= MAX_OUTS].copy()

    ev = df["event"].astype(str)
    df["is_bunt"] = (df["bunted"].fillna(False).astype(bool)
                     | ev.isin(list(BUNT_EVENTS) + list(BUNT_ALSO)))
    df["is_bunt_hit"] = df["is_bunt"] & ev.isin(list(BUNT_HIT_EVENTS))
    # the alternative is EVERY other plate appearance from the same state
    df["is_alt"] = ~df["is_bunt"]

    # THE VALUE OF A PLAY IS ITS DELTA, NOT ITS LEVEL, and this is the second
    # correction the family needed. Averaging WE_after within a base-out cell
    # still compares two different populations of GAME STATE: managers bunt in
    # close, late games where win expectancy sits near .500, while the swing-away
    # population includes every blowout, where it is pinned near 0 or 1. The
    # cell means then differ because of the score, not the decision.
    #
    # Differencing each play against its OWN pre-play state removes the level, so
    # what is left is what the plate appearance did. Both sides come from the
    # same model at both ends, which is the property management.py protects when
    # it refuses to mix the smooth model with the boundary table.
    we_after, we_before = [], []
    for row in df.itertuples(index=False):
        base = {"inning": row.inning, "half": row.half,
                "score_diff": row.score_diff, "outs_before": row.outs_before,
                "runs_scored_on_play": 0, "outs_after": row.outs_before}
        pre = _we_after_play(W, {**base, "base_after": row.base_before})
        post = _we_after_play(W, {"inning": row.inning, "half": row.half,
                                  "score_diff": row.score_diff,
                                  "outs_before": row.outs_before,
                                  "base_after": row.base_after,
                                  "runs_scored_on_play": getattr(row, "runs_scored_on_play", 0),
                                  "outs_after": row.outs_after})
        we_before.append(pre)
        we_after.append(post)
    df["we_before"] = we_before
    df["we_after"] = we_after
    df["dwe"] = df["we_after"] - df["we_before"]
    bad = df["we_after"].isna() | df["we_before"].isna()
    excluded["unpriceable_state"] += int(bad.sum())
    df = df[~bad].copy()

    cells, n_bunt_priced = [], 0
    total_dv = 0.0
    by_sit = {k: {"n_bunts_priced": 0, "n_bunt_hits": 0, "total": 0.0}
              for k in ("sacrifice", "for_a_hit")}
    for (outs, base), g in df.groupby(["outs_before", "base_before"]):
        b = g[g["is_bunt"]]
        a = g[g["is_alt"]]
        if len(b) < MIN_CELL or len(a) < MIN_CELL:
            excluded["thin_cell"] += int(len(b))
            continue
        e_bunt = float(b["dwe"].mean())
        e_alt = float(a["dwe"].mean())
        dv = e_bunt - e_alt
        total_dv += dv * len(b)
        n_bunt_priced += int(len(b))
        sit = _situation(int(base))
        by_sit[sit]["n_bunts_priced"] += int(len(b))
        by_sit[sit]["n_bunt_hits"] += int(b["is_bunt_hit"].sum())
        by_sit[sit]["total"] += dv * len(b)
        cells.append({
            "outs": int(outs), "base": int(base),
            "bases": _base_label(int(base)),
            "situation": sit,
            "n_bunt": int(len(b)), "n_alt": int(len(a)),
            "n_bunt_hit": int(b["is_bunt_hit"].sum()),
            "e_dwe_bunt": round(e_bunt, 5),
            "e_dwe_alt": round(e_alt, 5),
            "dv_per_bunt": round(dv, 5),
            "dv_total": round(dv * len(b), 4),
        })
    cells.sort(key=lambda c: (c["outs"], c["base"]))

    # AN INDEPENDENT CONTROL, because a family whose first two cuts both came out
    # backwards has to be checked against something it did not build. StatsAPI
    # ships its own win probability on every play (wp_home_before / wpa_home),
    # from a model with no connection to ours. Scoring the same bunts through it
    # is a second opinion on the SIGN and the ORDER OF MAGNITUDE, not a second
    # metric: it is realized WPA, so it must never become the published number.
    #
    # UNITS. wp_home_before runs 0.1 to 99.9, so those columns are PERCENTAGE
    # POINTS and divide by 100. A home run averages 12.75 of them.
    control = None
    try:
        sign = np.where(df["half"].astype(str).str.startswith("bot"), 1.0, -1.0)
        wpa_bat = df["wpa_home"].to_numpy(dtype=float) * sign / 100.0
        df2 = df.assign(_wpa_bat=wpa_bat)
        tot_c = 0.0
        ctl_sit = {"sacrifice": 0.0, "for_a_hit": 0.0}
        # THE RECONCILIATION (audit M10-02). Each total is the sum of the bunts'
        # own changes minus the alternative's cell mean times the bunt count, so
        # both split exactly by the bunt's result and show where the two win
        # expectancy models part.
        rec = {}
        alt_model = alt_feed = 0.0
        for (o, bs), g in df2.groupby(["outs_before", "base_before"]):
            bb, aa = g[g["is_bunt"]], g[g["is_alt"]]
            if len(bb) < MIN_CELL or len(aa) < MIN_CELL:
                continue
            part = (float(bb["_wpa_bat"].mean()) - float(aa["_wpa_bat"].mean())) * len(bb)
            tot_c += part
            ctl_sit[_situation(int(bs))] += part
            alt_model += float(aa["dwe"].mean()) * len(bb)
            alt_feed += float(aa["_wpa_bat"].mean()) * len(bb)
            for res, gg in bb.groupby(bb["event"].astype(str).map(_result_group)):
                r = rec.setdefault(res, {"n": 0, "model": 0.0, "control": 0.0})
                r["n"] += int(len(gg))
                r["model"] += float(gg["dwe"].sum())
                r["control"] += float(gg["_wpa_bat"].sum())
        reconciliation = {
            "identity": ("total = the bunts' own summed change, by result, minus the "
                         "alternative's cell mean times the bunt count; exact for both "
                         "the model and the control"),
            "by_result": {k: {"n": v["n"], "model_wins": round(v["model"], 3),
                              "control_wins": round(v["control"], 3),
                              "gap_wins": round(v["model"] - v["control"], 3)}
                          for k, v in sorted(rec.items(), key=lambda kv: -kv[1]["n"])},
            "alternative_offset": {"model_wins": round(alt_model, 3),
                                   "control_wins": round(alt_feed, 3),
                                   "gap_wins": round(alt_model - alt_feed, 3)},
        }
        worst = max(rec.items(), key=lambda kv: abs(kv[1]["model"] - kv[1]["control"])) if rec else None
        control = {
            "source": "StatsAPI wp_home_before / wpa_home, converted to the batting "
                      "team's frame and divided by 100 (those columns are percentage "
                      "points, not probabilities)",
            "total_wins": round(tot_c, 3),
            "by_situation_wins": {k: round(v, 3) for k, v in ctl_sit.items()},
            # DERIVED, not explained away: the two totals come from two
            # different win expectancy models over the same rows, and nothing
            # here calibrates one against the other.
            "model_over_control": (round(total_dv / tot_c, 3) if tot_c else None),
            "reconciliation": reconciliation,
            "largest_gap_sentence": (
                (f"The two models part most on {worst[0].replace('_', ' ')} "
                 f"({worst[1]['n']:,} bunts): {worst[1]['model']:+.1f} wins on the house "
                 f"model against {worst[1]['control']:+.1f} on the feed's.")
                if worst else None),
            "is_realized_wpa": True,
            "why_it_is_not_the_metric": (
                "it is the REALIZED win-probability change of the plays that "
                "happened, so it carries outcome variance the decision did not "
                "choose. It is here to check the sign and the size of the modelled "
                "number against a win-expectancy model this repo did not build."),
        }
    except Exception:                                       # noqa: BLE001
        control = None
    seasons_seen = sorted(int(s) for s in df["season"].unique()) if "season" in df else []
    return {
        "status": "built",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "produced_by": "mgmt_bunt.price",
        # which corpus this was priced from, so the page can say whether it is
        # the one the decision ledger's through-dates describe
        "corpus_built_at": _corpus_built_at(corpus),
        "seasons": seasons_seen,
        "n_plate_appearances": int(len(df)),
        "n_bunts_priced": n_bunt_priced,
        "min_cell": MIN_CELL,
        "excluded": excluded,
        "total_decision_value_wins": round(total_dv, 3),
        "dv_per_bunt_mean": (round(total_dv / n_bunt_priced, 5)
                             if n_bunt_priced else None),
        "by_situation": {
            k: {"n_bunts_priced": v["n_bunts_priced"], "n_bunt_hits": v["n_bunt_hits"],
                "total_decision_value_wins": round(v["total"], 3),
                "dv_per_bunt_mean": (round(v["total"] / v["n_bunts_priced"], 5)
                                     if v["n_bunts_priced"] else None)}
            for k, v in by_sit.items()},
        "situations": {
            "sacrifice": "a runner on and fewer than two out, where a bunt can move him up",
            "for_a_hit": ("the bases empty, where there is no runner to sacrifice and the "
                          "bunt is a try for a hit"),
        },
        "what_counts_as_a_bunt": (
            "every plate appearance that ended on a bunt, whatever the result: "
            "sacrifices, bunt outs, bunt hits, bunts reached on an error, bunt "
            "fielder's choices and strike three on a foul or missed bunt. A bunt fouled "
            "off or missed earlier in a plate appearance the batter then swung is not a "
            "bunt here; the decision ledger lists those as abandoned attempts."),
        "cells": cells,
        "independent_control": control,
        "what_this_is": (
            "DV(S) = E[change in WE | a bunt was called from state S] minus E[change "
            "in WE | any other plate appearance from S], both measured league-wide. "
            "Each play is differenced against its OWN pre-play state, so the score "
            "and inning cancel and what is left is what the plate appearance did, "
            "so every bunt from one state carries the same decision value. The "
            "realized outcome of an individual bunt never enters it."),
        "the_selection_problem": (
            "NOT SOLVED, STATED. Managers bunt with the batters they least want "
            "swinging, so E[WE | bunt] is measured over a weaker population than "
            "E[WE | swing]. This prices THE BUNT AS DEPLOYED, which is a fair read "
            "of what the league's bunting has been worth, and it is biased against "
            "the bunt as a tactic. Removing the bias needs a per-batter plate "
            "appearance model (the plan's M-ENG-1), which does not exist yet."),
        "two_outs_excluded": (
            "With two down an out ends the half-inning, so its value comes from the "
            "measured half-inning-start table while the alternative comes from the "
            "smooth model. Those are two estimators with nothing calibrating them "
            "against each other, so their difference has no guaranteed sign. A "
            "two-out sacrifice is also nearly nonexistent."),
        "no_per_club_metric": (
            "None is published here, and it is not an oversight. The running-game "
            "battery found per-agent decision value does not repeat between halves "
            "of a season; nothing has shown this family behaves differently, so a "
            "per-club column would be a ranking of noise a reader could not "
            "recognise as one. It needs its own split-half before it can ship."),
    }


def _corpus_built_at(corpus: Path):
    try:
        m = json.loads((Path(corpus) / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return m.get("built_at")


def _result_group(event: str) -> str:
    """The bunt's result, grouped the way the decision ledger names its kinds."""
    if event == "Sac Bunt":
        return "sacrifice"
    if event in BUNT_ALSO:
        return "bunt_out"
    if event in BUNT_HIT_EVENTS:
        return "bunt_hit"
    if event == "Strikeout":
        return "strike_three_on_a_bunt"
    return "reached_or_double_play"


def _situation(base: int) -> str:
    """sacrifice with a runner on (the family prices outs 0 and 1 only), for_a_hit
    with the bases empty."""
    return "sacrifice" if base else "for_a_hit"


def _base_label(b: int) -> str:
    if not b:
        return "empty"
    parts = []
    if b & 1:
        parts.append("1B")
    if b & 2:
        parts.append("2B")
    if b & 4:
        parts.append("3B")
    return "+".join(parts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons")
    ap.add_argument("--corpus")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    seasons = a.seasons.split(",") if a.seasons else None
    out = price(corpus=Path(a.corpus) if a.corpus else None, seasons=seasons)
    if out.get("status") != "built":
        print(out.get("status"))
        return 1
    print(f"seasons {out['seasons']}  PAs {out['n_plate_appearances']:,}  "
          f"bunts priced {out['n_bunts_priced']:,}")
    print(f"total decision value: {out['total_decision_value_wins']:+.3f} wins "
          f"({out['dv_per_bunt_mean']:+.5f} per bunt)")
    print(f"{'outs':>4} {'bases':<10} {'n bunt':>7} {'n alt':>7} {'DV/bunt':>9} {'DV total':>9}")
    for c in out["cells"]:
        print(f"{c['outs']:>4} {c['bases']:<10} {c['n_bunt']:>7} {c['n_alt']:>7} "
              f"{c['dv_per_bunt']:>+9.5f} {c['dv_total']:>+9.3f}")
    if not a.dry:
        OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
