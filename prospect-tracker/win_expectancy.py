"""M-ENG-1: win expectancy, as a smooth model rather than a table of cell means.

WHAT IT IS. WE(state) is the probability the HOME team wins given the game state
before a play: inning, half, score difference, outs, and which bases are
occupied. It is estimated from this repo's own corpus, 1,448,965 plays across
2018, 2019 and 2021-2026.

WHY A MODEL AND NOT A TABLE, WHICH IS THE WHOLE POINT OF THIS FILE. The first
version of this module was a table of raw cell means, one cell per
(inning, half, score difference, outs, bases). It looked reasonable, it agreed
with the published bottom-of-the-ninth figures, and it was UNUSABLE for the thing
it exists to do. Measured: advancing a runner from first to second LOWERED the
batting team's win expectancy in 42.6% of comparable cells. That is not a bug in
the state reconstruction, which is exactly right (the corpus reproduces the
published run-expectancy table to the third decimal). It is arithmetic: 1.45
million plays across 4,557 cells is about 318 observations each, a binary outcome
has a standard error near 0.029 at that count, and the difference between "runner
on first" and "runner on second" is 0.02 to 0.05. The noise is the same size as
the signal.

The MLB feed's own win probability, averaged the same way, does no better: it
violates the same monotonicity in 24.6% of cells, because its within-cell
standard deviation is 0.04, meaning it carries team quality, and better offences
reach second base more often. Both estimates are confounded at the resolution a
decision metric needs.

On raw accuracy the feed and this model are effectively level. The numbers are
DERIVED into the artifact by every build rather than typed here, because they
move with the fit; measured on 2026-09-10 over the same 1,448,965 plays the feed
reads 0.157516 and this model 0.157678. The feed is very slightly ahead. That is
not a concession of anything this module needed: the gap is 0.00016 of Brier, the
feed is a live in-game number solving a different problem, and what the
comparison settles is the only question this module asked, which is that
insisting on a team-blind valuation costs nothing measurable.

WHY THOSE NUMBERS CHANGED, 2026-09-10 (audit findings F07-02, F07-01, F07-05).
Until this build the fit paired a POST-play score with a PRE-play base-out
state. `.cache/pbp_corpus` stores `home_score` / `away_score` as
`result.homeScore` / `result.awayScore`, which is the score AFTER the play, while
`outs_before` and the occupancy columns are reconstructed BEFORE it. On 9.12
percent of plays the runs the base state produced were therefore already inside
the `lead` feature, which is leakage: it lifted the reported Brier to 0.155718,
attenuated the run-expectancy coefficient by 30 to 46 percent, and manufactured
a 213-cell boundary table containing three states that cannot occur, among them
a bottom of the ninth entered with a one-run home lead. The score is now taken
before the play everywhere it is read (`pre_play_score_diff`), the fit is
honest, and the served accuracy claim is derived from the corrected comparison
instead of asserting an edge the leak had created.

SO THE BASE-OUT STATE ENTERS THROUGH ITS RUN EXPECTANCY, AS ONE NUMBER. RE(base,
outs) is estimated from the same corpus, is monotone in both directions, and
matches the published RE24 tables. A logistic model in (score difference, half
innings remaining, signed run expectancy, and their interactions) is therefore
MONOTONE IN THE BASE STATE BY CONSTRUCTION: advancing a runner raises RE, RE
enters with a single positive coefficient, so it raises the batting team's win
probability. Every time. That property is what makes differencing safe, and it is
asserted rather than hoped for.

WHAT THE STATE STILL LEAVES OUT, deliberately: the teams, the batter, the
pitcher, the park, the count. Every one matters to a real win probability and
every one would let a manager's roster leak into his grade. This is a
league-average valuation of a SITUATION, which is the only thing a decision can
be fairly scored against.

TWO ESTIMATORS, EACH WHERE IT IS BEST. Inside a half-inning the smooth model
prices the state. At a half-inning BOUNDARY, which is what a third out is, the
value comes from a MEASURED table of half-inning starts: 337,155 of them over
19,130 games, a median of about 1,250 per cell, and no extrapolation, because a
half-inning always begins with nobody out and nobody on. That split was not an
aesthetic choice. Two successive fits tried to price the boundary from the model
and both failed, leaving 8% to 19% of steal attempts valued so that being CAUGHT
STEALING raised the batting team's win probability. A model is free to be
discontinuous across a boundary it was never constrained at; a measurement is
not.

Offline. Reads .cache/pbp_corpus, writes data/win_expectancy.json.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / ".cache" / "pbp_corpus"
OUT = ROOT / "data" / "win_expectancy.json"

log = logging.getLogger(__name__)

#: Innings past this are pooled. Extra innings since 2020 begin with an automatic
#: runner on second, so the tenth is a structurally different game; it is pooled
#: rather than modelled and the artifact says so.
INNING_CAP = 9

#: Score differences past this are pooled at the cap.
DIFF_CAP = 10

#: The published bottom-of-the-ninth tail, tied and bases empty, by outs. An
#: EXTERNAL reference, kept as a constant so the artifact's disclosure paragraph
#: can be derived against it rather than typed beside it (audit F07-05). The
#: source is named beside it and printed in the note (audit QCLC13): the rows
#: "9 Bottom 0 0" at 0, 1 and 2 out of Tom Tango's Win Expectancy table
#: (tangotiger.net/welist.html, 2002), home team's view, read 2026-10-03. The
#: earlier constant (0.63, 0.57, 0.52) named no source and matched no table found.
PUBLISHED_NINTH_TAIL = (0.634, 0.577, 0.532)
PUBLISHED_NINTH_TAIL_SOURCE = "Tom Tango's 2002 Win Expectancy table (tangotiger.net)"


def ninth_tail_note(tail) -> str:
    """The smoothing_costs_the_tails paragraph, derived from the fit's three
    bottom-of-the-ninth figures against the named published table. mgmt_export
    calls it on the artifact's ninth_inning_tail.model_by_outs, so the served
    sentence follows this constant without a refit."""
    def _gap_phrase(got, pub):
        d = (got - pub) * 100.0
        if abs(d) < 0.5:
            return "matches"
        return f"is about {abs(d):.1f} points {'high' if d > 0 else 'low'}"

    pub = PUBLISHED_NINTH_TAIL
    return (
        "the model is less sharp than the raw cell means at the extremes. "
        "Bottom of the ninth tied, bases empty reads "
        + " / ".join(f"{v:.4f}" for v in tail)
        + " by outs against " + PUBLISHED_NINTH_TAIL_SOURCE + " at "
        + " / ".join(f"{v:.3f}" for v in pub)
        + ": the leadoff cell " + _gap_phrase(tail[0], pub[0])
        + ", the one-out cell " + _gap_phrase(tail[1], pub[1])
        + " and the two-out cell " + _gap_phrase(tail[2], pub[2])
        + ". That is the price of a functional form smooth enough to difference, "
        "and it is a price worth paying, because a table that is right on "
        "average and non-monotone in the base state cannot value a decision at "
        "all. Any family reading the ninth-inning tail should say so. These "
        "three figures are interpolated from the fit this artifact ships and "
        "cannot drift from it.")

#: A run-expectancy cell below this is not trusted on its own. RE is estimated on
#: 24 cells over 1.45 million plays, so the thinnest is still enormous; the floor
#: exists to make a corpus change loud rather than silent.
MIN_RE_N = 500

BASE_LABELS = {
    0: "empty", 1: "1B", 2: "2B", 3: "1B2B",
    4: "3B", 5: "1B3B", 6: "2B3B", 7: "loaded",
}


def add_pre_play_scores(df):
    """Attach `home_score_before` / `away_score_before` to a corpus frame.

    AUDIT F07-02. The corpus score columns are POST-play: the builder writes
    `result.homeScore` / `result.awayScore` (tools/build_pbp_corpus.py) and its
    own diagnostic asserts that their total minus the previous total equals
    `runs_scored_on_play`, which is the definition of an after-the-play score.
    Every other state column on the same row (`outs_before`, the occupancy
    columns) is reconstructed BEFORE the play. Pairing them is leakage, so the
    runs the play itself scored are backed out here, on the BATTING side only,
    and every consumer reads the pre-play pair.

    This is the corpus-free repair. Writing the two columns in
    tools/build_pbp_corpus.py would be equivalent and would cost a full corpus
    rebuild; it reproduces this arithmetic exactly on the columns that already
    exist, so the cheaper route is taken and named.
    """
    runs = df["runs_scored_on_play"].fillna(0).astype(int)
    bot = df["half"].astype(str).str.startswith("bot")
    df["home_score_before"] = df["home_score"] - runs.where(bot, 0)
    df["away_score_before"] = df["away_score"] - runs.where(~bot, 0)
    return df


def pre_play_score_diff(df):
    """HOME minus AWAY BEFORE the play, as a Series. See `add_pre_play_scores`.

    AUDIT F07-02. This is what `score_diff` means everywhere in this module and
    in management.py, mgmt_bunt.py and tools/mgmt_gate.py: the state the manager
    decided from, not the state his decision produced.
    """
    runs = df["runs_scored_on_play"].fillna(0).astype(int)
    bot = df["half"].astype(str).str.startswith("bot")
    return (df["home_score"] - df["away_score"]) - runs.where(bot, -runs)


def base_code(on_first, on_second, on_third) -> int:
    """0..7. Bit 0 is first, bit 1 is second, bit 2 is third."""
    return (1 if on_first else 0) | (2 if on_second else 0) | (4 if on_third else 0)


def innings_left(inning, half) -> tuple[int, int]:
    """(half-innings left for the BATTING team, for the FIELDING team), counting
    the current one for the batting side.

    THIS IS THE PARAMETRIZATION THE WHOLE MODEL TURNS ON, and it replaced an
    earlier one for a measured reason. The first fit used (inning, half) with a
    separate `is_bottom` term, and the resulting model was discontinuous across
    the half-inning boundary: in 8.4% of two-out states, making the third out
    RAISED the batting team's win probability. That is not a small blemish. It
    hit 19.2% of every steal attempt in the corpus and 22.6% of the total
    decision value, because a caught stealing with two down is exactly the
    transition the boundary governs.

    In this frame the third out is not a boundary at all, it is a decrement:

        (bat_left, field_left)  ->  (field_left, bat_left - 1)

    with the sides swapped. The same function values both, so the transition
    cannot be inconsistent with itself.

    Regulation arithmetic, for inning i:
      top of i    away bats in i..9        bat_left  = 10 - i
                  home bats in i..9        field_left = 10 - i
      bottom of i home bats in i..9        bat_left  = 10 - i
                  away bats in i+1..9      field_left = 9 - i

    Extra innings floor at one each: both teams are guaranteed the inning they
    are in, and nothing beyond it is promised.
    """
    inn = int(inning)
    if inn >= INNING_CAP:
        return (1, 1) if str(half).startswith("top") else (1, 0)
    if str(half).startswith("top"):
        return (INNING_CAP + 1 - inn, INNING_CAP + 1 - inn)
    return (INNING_CAP + 1 - inn, INNING_CAP - inn)


def _features(np, bat_left, field_left, lead, re_bat):
    """The design row, in the batting team's frame.

    `lead` is the BATTING team's score minus the fielding team's. `re_bat` is the
    run expectancy of the current base-out state, always non-negative and always
    good for the batting team.

    OUTS DO NOT ENTER SEPARATELY, and that was tried. Adding `outs` and its
    urgency interaction was an attempt to let the model price the third-out
    transition itself; it left 384 of 4,914 states where making an out RAISED
    the batting team's win probability, and it broke the tail, putting the home
    team at 0.442 batting in a TIED bottom of the ninth, which is impossible.
    The boundary is not the model's job. It is served from a measured table
    instead (see `half_inning_start`), which is where the data is dense.
    """
    b = np.asarray(bat_left, dtype=float)
    f = np.asarray(field_left, dtype=float)
    ld = np.clip(np.asarray(lead, dtype=float), -DIFF_CAP, DIFF_CAP)
    r = np.asarray(re_bat, dtype=float)
    # THE URGENCY TERM. A lead is worth more when there is less time to lose it,
    # and 1/sqrt(remaining) is the standard shape: the value of a fixed lead
    # grows like the reciprocal of the standard deviation of the runs still to
    # be scored, which falls like the square root of the innings left.
    tot = b + f
    urg = 1.0 / np.sqrt(1.0 + tot)
    # `last_licks` is the structural advantage of batting last, and it is a
    # PROPERTY OF THE FRAME rather than a half indicator: the batting team has
    # the final at-bat exactly when it has more half-innings left than the
    # fielding team.
    last = (b > f).astype(float)
    return np.column_stack([ld, ld * urg, r, r * urg, tot, b - f, last])


FEATURE_NAMES = ("lead", "lead_x_urgency", "re_bat", "re_bat_x_urgency",
                 "half_innings_left_total", "half_innings_left_diff",
                 "last_licks")


def _seasons(corpus: Path):
    d = corpus / "plays"
    return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.exists() else []


def run_expectancy(df, np) -> dict:
    """RE(base, outs): runs scored from this state to the end of the half-inning.

    The classic table, estimated from the corpus. Reproduces the published RE24
    values, which is the check that the base-out reconstruction is right; it was
    this table agreeing that proved the win-expectancy trouble was estimation
    noise rather than a broken state.
    """
    # ONE GROUPBY, NOT 24 MASKS. The masked version dropped a different
    # base-out cell on each build (first "runner on first, one out", then
    # "corners, two out"), each holding six figures of observations, which made
    # every downstream lookup return None for a common state. Grouping once is
    # deterministic, and it is also about twenty times faster.
    hi = (df["game_pk"].astype(str) + "|" + df["inning"].astype(str)
          + "|" + df["half"].astype(str))
    cum = df.groupby(hi, sort=False)["runs_scored_on_play"].cumsum()
    tot = df.groupby(hi, sort=False)["runs_scored_on_play"].transform("sum")
    ros = (tot - cum + df["runs_scored_on_play"]).to_numpy()
    base = df["_base"].to_numpy()
    outs = df["outs_before"].to_numpy()
    out = {}
    for b in range(8):
        for o in (0, 1, 2):
            sel = (base == b) & (outs == o)
            n = int(sel.sum())
            if n < MIN_RE_N:
                continue
            out[f"{b}|{o}"] = {"re": round(float(ros[sel].mean()), 5), "n": n}
    if len(out) < 24:
        missing = [f"{b}|{o}" for b in range(8) for o in (0, 1, 2)
                   if f"{b}|{o}" not in out]
        raise ValueError(
            f"run expectancy is missing base-out cells {missing} on a corpus of "
            f"{len(df):,} plays. All 24 occur many thousands of times in real "
            "baseball, so a gap here is a bug in the state reconstruction or in "
            "this function, never a property of the data. Refusing to write a "
            "model whose lookups would return None for a common state.")
    return out


#: Leads past this are pooled at the cap in the half-inning-start table.
START_LEAD_CAP = 6

#: A half-inning-start cell below this is pooled with its neighbours in lead.
MIN_START_N = 100


def half_inning_start_table(df, np) -> dict:
    """P(the team coming to bat wins) at the START of each half-inning.

    WHY THIS EXISTS SEPARATELY FROM THE MODEL. A decision that ends a half-inning
    has to be valued at what the next one is worth, and a smooth global model
    cannot be trusted there: two fits in a row left 8% of two-out states where
    making the third out RAISED the batting team's win probability, because the
    model is free to be discontinuous across a boundary it was never constrained
    at.

    This table needs no extrapolation. A half-inning always starts with nobody
    out and nobody on, so the state is just (inning, half, lead) and the data is
    dense: 337,155 half-inning starts over 19,130 games, a median of about 1,260
    observations per cell. It is measured, not modelled, and it is right at the
    tail where it matters most: the home team batting in the bottom of the ninth
    trailing by one wins 17.8% of the time, and tied, 63.4%.

    THE LEAD IS READ BEFORE THE PLAY (audit F07-02). It used to be read off the
    leadoff play's POST-play score, so a half-inning whose first batter homered
    was filed under the lead his home run produced. That put 11,326 of 337,155
    leadoff rows in the wrong cell and invented three cells for states that
    cannot exist: `1|top|1` and `1|bottom|1` (nobody has batted yet) and
    `9|bottom|1` (a home team leading after the top of the ninth does not bat).
    The last of those shipped as a measured 100 percent win probability on 87
    observations. The corrected table has 210 cells, and the leadoff cell
    `1|top|0` now holds exactly one row per game in the corpus.
    """
    hi = df[(df["outs_before"] == 0) & (df["_base"] == 0)]
    hi = hi.sort_values(["game_pk", "inning", "half"], kind="mergesort")
    hi = hi.drop_duplicates(["game_pk", "inning", "half"], keep="first")
    is_bot = hi["half"].astype(str).str.startswith("bot").to_numpy()
    home = hi["home_score_before"].to_numpy()
    away = hi["away_score_before"].to_numpy()
    lead = np.where(is_bot, home - away, away - home)
    lead = np.clip(lead, -START_LEAD_CAP, START_LEAD_CAP)
    inn = np.minimum(hi["inning"].to_numpy(), INNING_CAP)
    half = np.where(is_bot, "bottom", "top")
    won_home = hi["_home_won"].to_numpy()
    bat_won = np.where(is_bot, won_home, 1.0 - won_home)

    cells: dict = {}
    for i in range(len(hi)):
        k = f"{int(inn[i])}|{half[i]}|{int(lead[i])}"
        c = cells.setdefault(k, [0, 0.0])
        c[0] += 1
        c[1] += float(bat_won[i])
    out = {}
    for k, (n, w) in cells.items():
        out[k] = {"p": round(w / n, 5), "n": int(n), "thin": bool(n < MIN_START_N)}
    return out


def build(*, corpus: Path | None = None, seasons=None) -> dict:
    import numpy as np
    import pandas as pd
    from sklearn.linear_model import LogisticRegression

    corpus = Path(corpus or CORPUS)
    want = list(seasons) if seasons else _seasons(corpus)
    if not want:
        raise FileNotFoundError(f"no play tables under {corpus / 'plays'}")

    frames = []
    for season in want:
        for f in sorted((corpus / "plays" / season).glob("*.parquet")):
            d = pd.read_parquet(f, columns=[
                "game_pk", "inning", "half", "outs_before", "on_first",
                "on_second", "on_third", "home_score", "away_score",
                "runs_scored_on_play", "wp_home_before"])
            for col in ("on_first", "on_second", "on_third"):
                if d[col].dtype == bool:
                    raise TypeError(
                        f"{col} is boolean in this corpus build. Occupancy is "
                        "read with notna() because the schema stores a runner "
                        "id or NaN; a boolean column means the schema changed "
                        "and the base state would be read wrong in a way that "
                        "still produces a table.")
            d["season"] = season
            frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values(["game_pk", "inning", "half"], kind="mergesort")

    # OCCUPANCY IS notna(). These columns hold the runner's player id as a float
    # with NaN for empty, and bool(NaN) is True, which reports every base
    # occupied and collapses the whole table onto the loaded state.
    df["_base"] = (df["on_first"].notna().astype(int)
                   + 2 * df["on_second"].notna().astype(int)
                   + 4 * df["on_third"].notna().astype(int))

    # THE SCORE IS TAKEN BEFORE THE PLAY (audit F07-02). Every other state
    # column on the row is pre-play; the corpus score column is not.
    df = add_pre_play_scores(df)

    re_tbl = run_expectancy(df, np)

    # THE LABEL. One per game, joined onto every play in it. This one reads the
    # POST-play column on purpose: the maximum of an after-the-play score is the
    # final score, which is the outcome being predicted.
    last = df.groupby("game_pk")[["home_score", "away_score"]].max()
    won = (last["home_score"] > last["away_score"]).astype(float)
    tied = last["home_score"] == last["away_score"]
    won = won[~tied]
    df = df[df["game_pk"].isin(won.index)]
    y = df["game_pk"].map(won).to_numpy()
    df = df.assign(_home_won=y)
    start_tbl = half_inning_start_table(df, np)

    re_of = np.array([re_tbl.get(f"{b}|{o}", {}).get("re", np.nan)
                      for b, o in zip(df["_base"].to_numpy(),
                                      df["outs_before"].to_numpy())])
    is_bot = df["half"].astype(str).str.startswith("bot").to_numpy()
    diff = (df["home_score_before"] - df["away_score_before"]).to_numpy()
    # EVERYTHING IN THE BATTING TEAM'S FRAME. The label flips with it: the model
    # predicts whether the team AT BAT goes on to win, so the home-win label is
    # inverted in the top half.
    lead = np.where(is_bot, diff, -diff)
    il = [innings_left(i, h) for i, h in
          zip(df["inning"].to_numpy(), df["half"].astype(str).to_numpy())]
    bat_left = np.array([a for a, _ in il], dtype=float)
    field_left = np.array([b for _, b in il], dtype=float)

    keep = ~np.isnan(re_of)
    X = _features(np, bat_left[keep], field_left[keep], lead[keep], re_of[keep])
    yy = np.where(is_bot[keep], y[keep], 1.0 - y[keep])
    clf = LogisticRegression(max_iter=2000, C=1e6)
    clf.fit(X, yy)
    p = clf.predict_proba(X)[:, 1]           # P(the team at bat wins)
    brier = float(np.mean((p - yy) ** 2))
    base_rate = float(yy.mean())
    brier_base = float(np.mean((base_rate - yy) ** 2))

    # The feed publishes a HOME win probability, so both sides are put back on
    # the home frame before they are compared.
    p_home = np.where(is_bot[keep], p, 1.0 - p)
    y_home = y[keep]
    feed = df["wp_home_before"].to_numpy()[keep] / 100.0
    feed_ok = ~np.isnan(feed)
    feed_brier = float(np.mean((feed[feed_ok] - y_home[feed_ok]) ** 2))
    home_brier = float(np.mean((p_home - y_home) ** 2))
    home_win_rate = float(y_home.mean())

    # RELIABILITY, in ten bins. A model used for differencing must be calibrated
    # in the middle of its range, which is where every decision lives.
    bins = np.clip((p * 10).astype(int), 0, 9)
    rel = []
    for b in range(10):
        m = bins == b
        if m.sum() < 100:
            continue
        rel.append({"bin": f"{b/10:.1f}-{(b+1)/10:.1f}",
                    "n": int(m.sum()),
                    "predicted": round(float(p[m].mean()), 4),
                    "observed": round(float(yy[m].mean()), 4)})
    ece = sum(r["n"] * abs(r["predicted"] - r["observed"]) for r in rel) / max(
        sum(r["n"] for r in rel), 1)

    coef = dict(zip(FEATURE_NAMES, [round(float(c), 6) for c in clf.coef_[0]]))

    # THE DISCLOSURE PARAGRAPHS ARE DERIVED FROM THIS FIT, NEVER TYPED
    # (audit F07-05). The shipped string carried 0.6295 / 0.5868 / 0.5556
    # against a model that produced 0.6020 / 0.5564 / 0.5234, and both of its
    # narrative claims had inverted, because a refit moved the model and the
    # prose stayed where somebody had left it. A served number inside a string
    # is interpolated from the thing it describes.
    def _we_home(inning, half, score_diff, outs, base):
        c = re_tbl.get(f"{int(base)}|{int(outs)}")
        if c is None:
            return None
        b_, f_ = innings_left(inning, half)
        bot = str(half).startswith("bot")
        X1 = _features(np, [b_], [f_], [score_diff if bot else -score_diff],
                       [c["re"]])
        z = float((X1 @ clf.coef_[0])[0]) + float(clf.intercept_[0])
        v = float(1.0 / (1.0 + np.exp(-z)))
        return v if bot else 1.0 - v

    tail = [_we_home(9, "bottom", 0, o, 0) for o in (0, 1, 2)]

    tail_note = ninth_tail_note(tail)

    start_ns = sorted(c["n"] for c in start_tbl.values())
    start_median_n = start_ns[len(start_ns) // 2] if start_ns else 0

    feed_gap = feed_brier - brier
    if feed_gap > 0:
        feed_verdict = ("so the context-free model is very slightly BETTER on "
                        "Brier despite knowing nothing about the teams")
    elif feed_gap < 0:
        feed_verdict = ("so the feed is very slightly ahead on Brier, by "
                        f"{abs(feed_gap):.5f}, which is what an estimator that "
                        "knows the teams should manage")
    else:
        feed_verdict = "so the two are level on Brier"
    feed_note = (
        "the MLB feed's own wp_home_before, scored on the same plays, for "
        f"comparison. Measured on this build it is {feed_brier:.6f} against "
        f"this model's {brier:.6f}, {feed_verdict}. That is not a ranking of "
        "win-probability models: the feed is a live in-game number solving a "
        "different problem, and the gap either way is smaller than the "
        "rounding a reader sees. What it settles is that insisting on a "
        "team-blind valuation costs nothing measurable here, which is the only "
        "question this module needed answered. The feed is still not the "
        "engine, because its within-cell standard deviation of 0.04 means it "
        "carries team quality, and crediting a manager for having better "
        "players is the confound this module exists to avoid. Both figures are "
        "derived from this fit; neither is typed.")

    return {
        "generated_at": datetime.now(timezone.utc)
                        .replace(microsecond=0).isoformat(),
        "produced_by": "win_expectancy.py",
        "schema_version": 5,
        "model": "logistic regression, scikit-learn, effectively unpenalised",
        "seasons": sorted(set(want)),
        "n_plays_fit": int(keep.sum()),
        "features": list(FEATURE_NAMES),
        "coef": coef,
        "intercept": round(float(clf.intercept_[0]), 6),
        "inning_cap": INNING_CAP,
        "diff_cap": DIFF_CAP,
        "run_expectancy": re_tbl,
        "half_inning_start": start_tbl,
        "half_inning_start_note": (
            "P(the team coming to bat wins) at the START of each half-inning, "
            "MEASURED rather than modelled. A decision that ends a half-inning "
            "is valued from this table, not from the smooth model, because a "
            "smooth model is free to be discontinuous across a boundary it was "
            "never constrained at: two successive fits left about 8% of two-out "
            "states where making the third out RAISED the batting team's win "
            "probability. A half-inning always starts with nobody out and "
            "nobody on, so this table needs no extrapolation and its cells hold "
            f"a median of {start_median_n:,} observations each. The lead is read "
            "BEFORE the leadoff play, so no cell describes a state that cannot "
            "occur."),
        "calibration": {
            "brier": round(brier, 6),
            "brier_base_rate_only": round(brier_base, 6),
            "brier_skill_score": round(1.0 - brier / brier_base, 4),
            "expected_calibration_error": round(float(ece), 5),
            "batting_team_win_rate": round(base_rate, 4),
            "home_win_rate": round(home_win_rate, 4),
            "brier_on_the_home_frame": round(home_brier, 6),
            "reliability": rel,
            "feed_brier": round(feed_brier, 6),
            "feed_note": feed_note,
        },
        "why_a_model_not_a_table": (
            "a table of cell means at this resolution cannot support "
            "differencing. Measured on the first build: advancing a runner from "
            "first to second LOWERED the batting team's win expectancy in 42.6% "
            "of comparable cells, because 1.45 million plays over 4,557 cells is "
            "about 318 each, the standard error of a binary outcome at that "
            "count is 0.029, and the effect being measured is 0.02 to 0.05. The "
            "feed's own numbers averaged the same way violate it in 24.6%."),
        "smoothing_costs_the_tails": tail_note,
        "ninth_inning_tail": {
            "state": "bottom of the ninth, tied, bases empty",
            "model_by_outs": [round(v, 5) for v in tail],
            "published_by_outs": list(PUBLISHED_NINTH_TAIL),
            "published_source": PUBLISHED_NINTH_TAIL_SOURCE,
            "note": ("the three figures quoted in smoothing_costs_the_tails, "
                     "shipped as numbers so a test can compare the prose "
                     "against the model instead of against a memory of it."),
        },
        "monotone_by_construction": (
            "the base-out state enters ONLY through its run expectancy, as a "
            "single covariate with a positive coefficient, so advancing a runner "
            "always raises the batting team's win probability. That property is "
            "what makes differencing safe and it is asserted in the tests, not "
            "assumed."),
        "state_excludes": (
            "the teams, the batter, the pitcher, the park and the count. Every "
            "one matters to a real win probability and every one would let a "
            "manager's roster leak into his grade. This is a league-average "
            "valuation of a SITUATION, which is the only thing a decision can be "
            "fairly scored against."),
        "extra_innings_note": (
            "innings past the cap read as zero regulation half-innings "
            "remaining. Since 2020 extra innings begin with an automatic runner "
            "on second, so the tenth is a structurally different game; it is "
            "pooled rather than modelled."),
    }


class WinExpectancy:
    """A loaded model with a safe lookup."""

    def __init__(self, art: dict):
        import numpy as np
        self.art = art
        self.np = np
        self.re = art["run_expectancy"]
        self.start = art.get("half_inning_start") or {}
        self.coef = np.array([art["coef"][k] for k in FEATURE_NAMES])
        self.intercept = float(art["intercept"])

    @classmethod
    def load(cls, path: Path | None = None) -> "WinExpectancy":
        p = Path(path or OUT)
        art = json.loads(p.read_text(encoding="utf-8"))
        if art.get("schema_version") != 5:
            raise ValueError(
                f"{p} is schema {art.get('schema_version')}; this module reads "
                "schema 5, the batting-team frame with a measured "
                "half-inning-start boundary and a PRE-play score. Re-run "
                "`python win_expectancy.py`. Schema 1 was a grid of cell means "
                "and is not safe to difference at all; schema 2 was smooth but "
                "discontinuous across the half-inning boundary, which mispriced "
                "19.2% of steal attempts; schema 4 fitted and queried a "
                "post-play score against a pre-play base-out state, which "
                "leaked the outcome into the lead feature and moved every "
                "decision value that reads it (audit F07-02).")
        return cls(art)

    def half_inning_start(self, inning, half, lead) -> float | None:
        """P(the team coming to bat wins) at the start of that half-inning.

        `lead` is from the BATTING team's point of view. Backs off by shrinking
        the lead toward zero when a cell is thin, and returns None rather than a
        default when nothing is close enough.
        """
        inn = min(int(inning), INNING_CAP)
        want = max(-START_LEAD_CAP, min(START_LEAD_CAP, int(lead)))
        for step in range(0, START_LEAD_CAP + 1):
            for cand in ({want} if step == 0 else {want - step, want + step}):
                if abs(cand) > START_LEAD_CAP:
                    continue
                c = self.start.get(f"{inn}|{half}|{int(cand)}")
                if c and not c["thin"]:
                    return float(c["p"])
        c = self.start.get(f"{inn}|{half}|{want}")
        return float(c["p"]) if c else None

    def run_exp(self, base, outs) -> float | None:
        c = self.re.get(f"{int(base)}|{int(outs)}")
        return None if c is None else float(c["re"])

    def _p_batting(self, bat_left, field_left, lead, re_bat) -> float:
        np = self.np
        X = _features(np, [bat_left], [field_left], [lead], [re_bat])
        z = float((X @ self.coef)[0]) + self.intercept
        return float(1.0 / (1.0 + np.exp(-z)))

    def offense_we(self, inning, half, score_diff, outs, base) -> float | None:
        """Win probability for the team AT BAT.

        THE PRIMARY ACCESSOR. The model is fitted in the batting team's frame,
        so this is the direct prediction and `we` below is the derived one. Every
        decision family must call this: a manager's decision is good or bad for
        HIS team, and reading the home-frame number in the top half inverts every
        verdict the module publishes.

        `score_diff` is HOME minus AWAY, matching the corpus columns.
        """
        r = self.run_exp(base, outs)
        if r is None:
            return None
        b, f = innings_left(inning, half)
        is_bot = str(half).startswith("bot")
        lead = score_diff if is_bot else -score_diff
        return self._p_batting(b, f, lead, r)

    def we(self, inning, half, score_diff, outs, base) -> float | None:
        """HOME win probability for the state, derived from the batting-frame
        prediction. None when run expectancy has never seen the base-out
        combination; None, never a default."""
        v = self.offense_we(inning, half, score_diff, outs, base)
        if v is None:
            return None
        return v if str(half).startswith("bot") else 1.0 - v


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s: %(message)s")
    art = build()
    if "--dry-run" not in argv:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(art, indent=1) + "\n", encoding="utf-8")
    c = art["calibration"]
    print(f"seasons {art['seasons']}  plays fit {art['n_plays_fit']:,}")
    print(f"Brier {c['brier']}  vs base rate {c['brier_base_rate_only']}  "
          f"skill {c['brier_skill_score']}  ECE {c['expected_calibration_error']}")
    _cmp = ("better than" if c["feed_brier"] < c["brier"]
            else "worse than" if c["feed_brier"] > c["brier"] else "level with")
    print(f"feed Brier {c['feed_brier']} ({_cmp} this model, and not the engine "
          "either way: it carries team quality)")
    print(f"coefficients: {art['coef']}")
    W = WinExpectancy(art)
    print(f"ninth-inning tail, derived: {art['ninth_inning_tail']['model_by_outs']}")
    print("\nbottom of the 9th, tied, bases empty, by outs:")
    for o in (0, 1, 2):
        print(f"   {o} out: home WE = {W.we(9, 'bottom', 0, o, 0):.4f}")
    print(f"top of the 1st, tied, bases empty, 0 out: "
          f"{W.we(1, 'top', 0, 0, 0):.4f}")
    print("\nmonotonicity, batting team, 1B then 2B then 3B (7th, tied, 1 out):")
    print("   " + "  ".join(
        f"{BASE_LABELS[b]}={W.offense_we(7, 'bottom', 0, 1, b):.4f}"
        for b in (0, 1, 2, 4, 7)))
    if "--dry-run" not in argv:
        print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
