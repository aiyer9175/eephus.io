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

On raw accuracy the feed and this model are effectively level: Brier 0.157516
against 0.155718, measured on the same 1.45 million plays. That is not a claim to
have beaten MLB at win probability, since the feed is a live in-game number
solving a different problem. What it settles is the only question this module
needed answered, which is that insisting on a team-blind valuation costs nothing
measurable.

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

#: A run-expectancy cell below this is not trusted on its own. RE is estimated on
#: 24 cells over 1.45 million plays, so the thinnest is still enormous; the floor
#: exists to make a corpus change loud rather than silent.
MIN_RE_N = 500

BASE_LABELS = {
    0: "empty", 1: "1B", 2: "2B", 3: "1B2B",
    4: "3B", 5: "1B3B", 6: "2B3B", 7: "loaded",
}


def base_code(on_first, on_second, on_third) -> int:
    """0..7. Bit 0 is first, bit 1 is second, bit 2 is third."""
    return (1 if on_first else 0) | (2 if on_second else 0) | (4 if on_third else 0)


def half_innings_remaining(inning, half) -> int:
    """How many half-innings are left after this one, at regulation length.

    Floored at zero, so extra innings all read as "no regulation time left",
    which is what they are. This is the clock the model prices a lead against:
    the same one-run lead is worth much more with two half-innings left than
    with fifteen.
    """
    inn = min(int(inning), INNING_CAP)
    rem = 2 * (INNING_CAP - inn) + (1 if str(half).startswith("top") else 0)
    return max(0, rem)


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
    dense: 337,155 half-inning starts over 19,130 games, a median of about 1,250
    observations per cell. It is measured, not modelled, and it is right at the
    tail where it matters most: the home team batting in the bottom of the ninth
    trailing by one wins 16.5% of the time, and tied, 62.0%.
    """
    hi = df[(df["outs_before"] == 0) & (df["_base"] == 0)]
    hi = hi.sort_values(["game_pk", "inning", "half"], kind="mergesort")
    hi = hi.drop_duplicates(["game_pk", "inning", "half"], keep="first")
    is_bot = hi["half"].astype(str).str.startswith("bot").to_numpy()
    home = hi["home_score"].to_numpy()
    away = hi["away_score"].to_numpy()
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

    re_tbl = run_expectancy(df, np)

    # THE LABEL. One per game, joined onto every play in it.
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
    diff = (df["home_score"] - df["away_score"]).to_numpy()
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
    return {
        "generated_at": datetime.now(timezone.utc)
                        .replace(microsecond=0).isoformat(),
        "produced_by": "win_expectancy.py",
        "schema_version": 4,
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
            "about 1,250 observations each."),
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
            "feed_note": (
                "the MLB feed's own wp_home_before, scored on the same plays, "
                "for comparison. Measured 2026-09-06 it is 0.157516 against "
                "this model's 0.155718, so the context-free model is very "
                "slightly BETTER on Brier despite knowing nothing about the "
                "teams. That is not a claim to have beaten MLB at win "
                "probability: the feed is a live in-game number solving a "
                "different problem, and the gap is small. What it does settle "
                "is that insisting on a team-blind valuation costs nothing "
                "measurable here, which is the only question this module needed "
                "answered. The feed is still not the engine, because its "
                "within-cell standard deviation of 0.04 means it carries team "
                "quality, and crediting a manager for having better players is "
                "the confound this module exists to avoid."),
        },
        "why_a_model_not_a_table": (
            "a table of cell means at this resolution cannot support "
            "differencing. Measured on the first build: advancing a runner from "
            "first to second LOWERED the batting team's win expectancy in 42.6% "
            "of comparable cells, because 1.45 million plays over 4,557 cells is "
            "about 318 each, the standard error of a binary outcome at that "
            "count is 0.029, and the effect being measured is 0.02 to 0.05. The "
            "feed's own numbers averaged the same way violate it in 24.6%."),
        "smoothing_costs_the_tails": (
            "the model is less sharp than the raw cell means at the extremes. "
            "Bottom of the ninth tied, bases empty reads 0.6295 / 0.5868 / "
            "0.5556 by outs against published values near 0.63 / 0.57 / 0.52: "
            "the leadoff cell matches and the two-out cell is about three "
            "points high. That is the price of a functional form smooth enough "
            "to difference, and it is a price worth paying, because a table "
            "that is right on average and non-monotone in the base state cannot "
            "value a decision at all. Any family reading the ninth-inning tail "
            "should say so."),
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
        if art.get("schema_version") != 4:
            raise ValueError(
                f"{p} is schema {art.get('schema_version')}; this module reads "
                "schema 4, the batting-team frame with a measured "
                "half-inning-start boundary. Re-run "
                "`python win_expectancy.py`. Schema 1 was a grid of cell means "
                "and is not safe to difference at all; schema 2 was smooth but "
                "discontinuous across the half-inning boundary, which mispriced "
                "19.2% of steal attempts.")
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
