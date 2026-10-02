"""In-Game Management: decision value, starting with the running game.

THE IDEA IN ONE LINE. A manager's decision is worth the win probability it buys
against the alternative he declined, valued at the state BEFORE he decided.

    DV = E[WP | decide] - WP(do nothing)

and it is deliberately NOT the win probability change that actually happened. A
manager who sends a runner in a spot that justified it and watches him get thrown
out made a good decision and a bad outcome, and a metric that cannot tell those
apart is measuring the runner, the defence and the weather. So every attempt
splits in two:

    DV   the DECISION, priced with a LEAGUE-AVERAGE success rate. Was sending
         anybody here a good idea?
    ER   the EXECUTION RESIDUAL, realized minus expected. Did this runner beat
         the throw?

    DV + ER = the realized win-probability change, exactly, by construction.

THE STEAL IS THE FIRST FAMILY ON PURPOSE. It is the decision with the cleanest
counterfactual in baseball: the alternative to sending the runner is not sending
him, the resulting states are fully determined (a base ahead, or an out and a
base empty), and the break-even success rate falls straight out of the win
expectancy table. Nothing has to be modelled that is not already measured. Every
harder family, the bullpen, the pinch hit, the lineup, needs a counterfactual
that has to be estimated, and none of them should be attempted until this one has
passed its gate.

WHY LEAGUE-AVERAGE AND NOT THE RUNNER'S OWN RATE. Because the runner's speed is
a roster fact, and crediting a manager for having Ronald Acuna is the confound
this module exists to avoid. The manager's decision is scored as though he had a
league-average runner; whether THIS runner beat that expectation is the execution
residual, and it is reported separately and attributed to the runner.

THE BREAK-EVEN RATE IS PUBLISHED BESIDE EVERY ATTEMPT, because it is the thing a
reader can argue with: p* = (WE_hold - WE_fail) / (WE_success - WE_fail). If the
league succeeds more often than p*, the attempt was justified. Three summaries of
it ship, and only one decides: DV is (WE_success - WE_fail) times (league_p - p*),
so the sum is positive exactly when the league rate beats the SWING-WEIGHTED mean
of p*. The median and the plain mean are the readable numbers and neither
determines the verdict.

TWO-OUT ATTEMPTS ARE EXCLUDED, and that is 45% of them. With nobody out or one
out, a caught stealing leaves the inning alive and both sides of the comparison
come from the same monotone model. With two out it ends the inning, so the
alternative comes from a different estimator, and nothing calibrates the two
against each other. Measured across three builds of the engine, that mismatch
priced between 8.7% and 19.2% of attempts so that being CAUGHT STEALING HELPED
the batting team, carrying up to 22.6% of the total decision value. A metric that
says being thrown out improved your chances is not a metric. The excluded
attempts are counted and published; pricing them needs an inning-level model that
predicts the boundary and the mid-inning state together, and that has not been
built.

THE COUNT DID NOT CLOSE UNTIL 2026-09-11 (audit F02-01). A steal that ENDS a
plate appearance, a caught stealing for the third out above all, is not a
playEvent: it is the play's own result and it lives only in the corpus's plays
table. This module read the events table alone, so 40.56% of every caught
stealing in the corpus was neither priced nor counted, 2,455 two-out attempts
were missing from the exclusion row, and the share above read 40%. Both tables
are read now, and the artifact's `attempt_census` carries the corpus count
beside priced plus excluded so the identity is checked rather than promised.

WHAT IT FOUND, restated 2026-09-10 on the corrected win model and again
2026-09-11 on the complete census, over 13,973 priceable attempts:

  stealing second   the league succeeds 75.00% against a swing-weighted
                    break-even of 75.29%. Eight seasons of decision value sum to
                    -2.60 wins across 11,977 attempts. Managers collectively
                    still run the stolen base at close to the point of
                    indifference.
  stealing third    76.2% against 73.1%, worth +5.99 wins. Two
                    plate-appearance-ending steals of third, both with one out
                    in the eleventh, joined the priced pool with the census
                    repair; they are the only attempts it added below two out.
  stealing home     25.8% against 73.5%, worth -4.08 wins.
  net               -0.69 wins, where the 2026-09-06 build read +1.79.

WHY THOSE NUMBERS MOVED (audit F07-02). The state this module prices is the one
"BEFORE he decided", and until 2026-09-10 the score in that state was read off
the corpus's POST-play score column while the outs and the bases were read
pre-play. 2,388 of the 13,971 attempts (17.09%) sit in a plate appearance that
scored, so the runner was valued against a scoreboard that already contained
runs driven in after he broke; for a steal of home the run being stolen was in
the score and `_we_after` then added it a second time. The score is now taken
from `win_expectancy.pre_play_score_diff`. The win model was refit on the same
correction, which moves these numbers again and by more, because the leak had
attenuated the run-expectancy coefficient the whole family differences.

Offline. Reads .cache/pbp_corpus and data/win_expectancy.json.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

#: Regulation length. Mirrors win_expectancy.INNING_CAP and is asserted equal
#: to it in the tests: the terminal conditions below and the model's own
#: inning pooling have to agree about when "late" starts.
INNING_CAP = 9

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / ".cache" / "pbp_corpus"
OUT = ROOT / "data" / "management_running.json"

log = logging.getLogger(__name__)

#: Every event type that is a steal attempt. A pickoff-caught-stealing IS an
#: attempt: the runner broke for the next base and was retired. A plain pickoff
#: is NOT, because the runner never committed, and counting it would blame a
#: manager for a decision nobody made.
STEAL_EVENTS: dict[str, tuple[str, bool]] = {
    "stolen_base_2b": ("2B", True),
    "stolen_base_3b": ("3B", True),
    "stolen_base_home": ("HOME", True),
    "caught_stealing_2b": ("2B", False),
    "caught_stealing_3b": ("3B", False),
    "caught_stealing_home": ("HOME", False),
    "pickoff_caught_stealing_2b": ("2B", False),
    "pickoff_caught_stealing_3b": ("3B", False),
    "pickoff_caught_stealing_home": ("HOME", False),
}

#: One steal attempt, as both corpus tables can name it. See
#: `_play_result_steals` for why event_type has to stay in the key.
STEAL_KEY = ["game_pk", "at_bat_index", "event_type"]

#: Events that CHANGE the base-out state inside a plate appearance. An attempt
#: preceded by one of these cannot be priced from the play's starting state, so
#: it is excluded and the exclusion is counted. Measured on 2024: this keeps
#: 98.2% of attempts, so the restriction is cheap.
STATE_CHANGING = set(STEAL_EVENTS) | {
    "wild_pitch", "passed_ball", "balk", "error", "runner_placed",
    "pickoff_1b", "pickoff_2b", "pickoff_3b", "other_advance",
    "defensive_indiff", "stolen_base_2b_bad", "advance",
}

#: The base the runner starts on, per target.
ORIGIN_BIT = {"2B": 1, "3B": 2, "HOME": 4}
TARGET_BIT = {"2B": 2, "3B": 4, "HOME": 0}


def _next_half(inning: int, half: str) -> tuple[int, str]:
    return (inning, "bottom") if str(half).startswith("top") else (inning + 1, "top")


def _we_after(W, inning, half, score_diff, outs, base, *, runs=0, out_added=0):
    """Offensive win expectancy after a transition, handling the third out.

    THE THIRD OUT IS NOT A DETAIL. A caught stealing with two down ends the
    half-inning, and the value of the resulting state is the value of the NEXT
    half-inning with the bases empty and nobody out, read from the other team's
    point of view. Pricing it as "two outs, bases empty" instead would understate
    the cost of the worst possible time to be thrown out, which is exactly the
    decision the metric most needs to get right.
    """
    outs2 = int(outs) + int(out_added)
    # score_diff is HOME minus AWAY throughout this module. The batting team
    # scoring moves it toward its own side: UP in the bottom half, DOWN in the
    # top. Getting this backwards would make a steal of home look like a
    # disaster for the away team, and it is the kind of sign error that produces
    # a plausible-looking number rather than a crash.
    diff2 = int(score_diff) + (
        int(runs) if str(half).startswith("bot") else -int(runs))
    # THE GAME CAN END HERE, and until 2026-09-06 this function did not know it.
    # Three terminal conditions, all in the ninth inning or later:
    #
    #   a walk-off. The home team takes the lead while batting in the bottom of
    #     the ninth or later. The game stops at once and the home team has won.
    #   the last out. The home team makes its third out in the bottom of the
    #     ninth or later while NOT ahead: if it trails, it has lost; if the game
    #     is tied it goes to extras and is not terminal.
    #   the top-half close-out. The away team makes its third out in the top of
    #     the ninth or later while the home team leads. The home team does not
    #     bat and has won.
    #
    # Pricing these as "the next half-inning" is not a rounding error. The worst
    # case measured was the bottom of the ninth trailing by one with two out,
    # where being thrown out ends the game at a win probability of zero and the
    # old code returned 0.44, so making the final out of a loss scored as a
    # 0.056 IMPROVEMENT for the batting team.
    late = int(inning) >= INNING_CAP
    is_bot = str(half).startswith("bot")
    if late and is_bot and runs and diff2 > 0:
        return 1.0                                  # walk-off, batting team wins
    if outs2 >= 3 and late:
        if is_bot and diff2 < 0:
            return 0.0                              # home makes the last out, loses
        if not is_bot and diff2 > 0:
            return 0.0                              # away makes the last out, loses
    if outs2 < 3:
        return W.offense_we(inning, half, diff2, outs2, base)
    # THE BOUNDARY COMES FROM THE MEASURED TABLE, NOT THE MODEL. A half-inning
    # always starts with nobody out and nobody on, so P(the next batting team
    # wins) is directly observed on about 1,250 games per cell and needs no
    # extrapolation. Evaluating the smooth model at the next half-inning instead
    # was tried twice and failed both times: it left about 8% of two-out states
    # where making the third out RAISED the batting team's win probability,
    # which touched 19.2% of every steal attempt in the corpus and 22.6% of the
    # total decision value. A model is free to be discontinuous across a
    # boundary it was never constrained at; a measurement is not.
    inn2, half2 = _next_half(inning, half)
    is_bot2 = half2.startswith("bot")
    lead_next = diff2 if is_bot2 else -diff2
    v = W.half_inning_start(inn2, half2, lead_next)
    # The NEXT half's batting team is the other one, so the value to the team
    # that just made the out is one minus that team's win probability.
    return None if v is None else 1.0 - v


def attempts(*, corpus: Path | None = None, seasons=None, we=None):
    """Every priceable steal attempt, with its decision value. Returns a
    DataFrame."""
    import pandas as pd
    import win_expectancy as wx

    corpus = Path(corpus or CORPUS)
    W = we or wx.WinExpectancy.load()
    ev_dir = corpus / "events"
    pl_dir = corpus / "plays"
    want = list(seasons) if seasons else sorted(
        p.name for p in ev_dir.iterdir() if p.is_dir())

    frames = []
    excluded = {"prior_state_change": 0, "origin_base_empty": 0,
                "no_play_row_to_price_from": 0,
                "two_outs_crosses_the_boundary": 0, "unpriceable_state": 0}
    census = {"from_the_events_table": 0, "from_the_play_result_only": 0,
              "play_result_already_an_event_row": 0, "seasons": []}
    pa_key = ["game_pk", "at_bat_index"]
    for season in want:
        efs = sorted((ev_dir / season).glob("*.parquet"))
        pfs = sorted((pl_dir / season).glob("*.parquet"))
        if not efs or not pfs:
            continue
        ev = pd.concat([pd.read_parquet(f) for f in efs], ignore_index=True)
        pl = pd.concat([pd.read_parquet(f) for f in pfs], ignore_index=True)

        ev = ev.sort_values(["game_pk", "at_bat_index", "index"])
        ev["is_sc"] = ev["event_type"].isin(STATE_CHANGING)
        by_pa = ev.groupby(pa_key)["is_sc"]
        ev["prior_sc"] = by_pa.cumsum() - ev["is_sc"].astype(int)
        st_ev = ev.loc[ev["event_type"].isin(STEAL_EVENTS),
                       STEAL_KEY + ["prior_sc"]]
        st_pl, n_dup = _play_result_steals(pd, st_ev, pl, by_pa.sum())
        census["from_the_events_table"] += int(len(st_ev))
        census["from_the_play_result_only"] += int(len(st_pl))
        census["play_result_already_an_event_row"] += n_dup
        census["seasons"].append(str(season))
        st = pd.concat([st_ev, st_pl], ignore_index=True)
        excluded["prior_state_change"] += int((st["prior_sc"] > 0).sum())
        st = st[st["prior_sc"] == 0]
        if st.empty:
            continue
        st["target"] = st["event_type"].map(lambda e: STEAL_EVENTS[e][0])
        st["success"] = st["event_type"].map(lambda e: STEAL_EVENTS[e][1])

        keep = ["game_pk", "at_bat_index", "inning", "half", "outs_before",
                "on_first", "on_second", "on_third", "home_score", "away_score",
                "runs_scored_on_play"]
        # A LEFT JOIN, COUNTED. The inner join this replaced would have dropped
        # an attempt whose plate appearance has no play row without a trace,
        # which is the shape of audit F02-01: an attempt neither priced nor
        # counted. It measured zero on the 2026-09-11 corpus, and it is counted
        # so that it stays visible if it ever is not.
        j = st.merge(pl[keep], on=pa_key, how="left", indicator=True)
        nop = (j["_merge"] == "left_only").to_numpy()
        excluded["no_play_row_to_price_from"] += int(nop.sum())
        j = j[~nop].drop(columns="_merge")
        # Arithmetic rather than bit shifts: a pandas Series has no <<, and the
        # three terms are disjoint powers of two so addition IS the OR here.
        # Occupancy is notna(), never astype(bool): these columns hold the
        # runner's player id as a float with NaN for empty, and bool(NaN) is
        # True, which reports every base occupied. That defect cost the win
        # expectancy table its first build.
        j["base_before"] = (j["on_first"].notna().astype(int)
                            + 2 * j["on_second"].notna().astype(int)
                            + 4 * j["on_third"].notna().astype(int))
        # THE SCORE IS THE ONE HE DECIDED FROM (audit F07-02). The corpus
        # score columns are POST-play, so on a plate appearance that scored they
        # already contain runs driven in after the runner broke. Reading them
        # raw paired an after-the-play score with a before-the-play base-out
        # state on 17.09% of attempts and moved every decision value in the
        # family.
        j["score_diff"] = wx.pre_play_score_diff(j)
        j["origin_bit"] = j["target"].map(ORIGIN_BIT)
        # THE ORIGIN BASE MUST BE OCCUPIED. A "steal of second" whose first base
        # is empty is not a steal this module can price: it means the state
        # reconstruction and the event disagree, and pricing it anyway would
        # invent a decision. Counted, excluded, and reported.
        bad = (j["base_before"].to_numpy() & j["origin_bit"].to_numpy()) == 0
        excluded["origin_base_empty"] += int(bad.sum())
        j = j[~bad].copy()
        # TWO OUTS IS EXCLUDED, AND THIS IS THE MOST IMPORTANT LINE IN THE FILE.
        #
        # With nobody out or one out, a caught stealing leaves the inning alive,
        # so BOTH sides of every comparison come from the same monotone model and
        # the difference is safe. With two out, being caught ends the inning, so
        # `hold` comes from the smooth model and `fail` from the measured
        # half-inning-start table. Those are two different estimators and nothing
        # calibrates them against each other, so their difference has no
        # guaranteed sign.
        #
        # That is not theoretical. Measured across three successive builds of the
        # engine, the share of attempts where being CAUGHT was priced as HELPING
        # the batting team ran 19.2%, then 8.65%, all of them at two outs, and
        # they carried 14.7% of the total decision value even in the best
        # version. A metric that says being thrown out improved your chances is
        # not a metric.
        #
        # So the family is restricted to the attempts it can price honestly,
        # about 53% of the corpus, and the two-out 45% is counted and published
        # rather than quietly absorbed. Until 2026-09-11 those shares read 60%
        # and 40%, because the plate-appearance-ending caught stealings were
        # never read (audit F02-01) and almost every one of them is a two-out
        # attempt. Pricing a two-out attempt needs an inning-level model
        # that predicts the boundary and the mid-inning state together; that is a
        # real lane and it has not been built.
        excluded["two_outs_crosses_the_boundary"] += int((j["outs_before"] >= 2).sum())
        j = j[j["outs_before"] < 2].copy()
        if j.empty:
            continue
        j["season"] = season
        frames.append(j)

    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)

    # LEAGUE SUCCESS RATE, by season and target. The manager-neutral prior the
    # decision is priced with.
    lg = (df.groupby(["season", "target"])["success"].mean()
          .rename("league_p").reset_index())
    df = df.merge(lg, on=["season", "target"], how="left")

    hold, succ, fail, be, dv, er, real = [], [], [], [], [], [], []
    for r in df.itertuples(index=False):
        base, tgt = int(r.base_before), r.target
        obit = ORIGIN_BIT[tgt]
        tbit = TARGET_BIT[tgt]
        base_s = (base & ~obit) | tbit
        base_f = base & ~obit
        runs = 1 if tgt == "HOME" else 0
        h = W.offense_we(r.inning, r.half, r.score_diff, r.outs_before, base)
        s_ = _we_after(W, r.inning, r.half, r.score_diff, r.outs_before, base_s,
                       runs=runs)
        f_ = _we_after(W, r.inning, r.half, r.score_diff, r.outs_before, base_f,
                       out_added=1)
        hold.append(h)
        succ.append(s_)
        fail.append(f_)
        if h is None or s_ is None or f_ is None or s_ == f_:
            be.append(None)
            dv.append(None)
            er.append(None)
            real.append(None)
            continue
        p_star = (h - f_) / (s_ - f_)
        exp = r.league_p * s_ + (1.0 - r.league_p) * f_
        realized = s_ if r.success else f_
        be.append(p_star)
        dv.append(exp - h)
        er.append(realized - exp)
        real.append(realized - h)
    df["we_hold"] = hold
    df["we_success"] = succ
    df["we_fail"] = fail
    df["breakeven_p"] = be
    df["dv"] = dv
    df["er"] = er
    df["realized_delta"] = real
    excluded["unpriceable_state"] = int(df["dv"].isna().sum())
    df.attrs["excluded"] = excluded
    df.attrs["attempt_census"] = census
    return df


def _play_result_steals(pd, st_ev, pl, sc_per_pa):
    """The steal attempts that exist ONLY as a play's own result (audit F02-01).

    The corpus writes a steal in one of two places. A steal in the middle of a
    plate appearance is a non-pitch playEvent and lands in the `events` table.
    A steal that ENDS the plate appearance, the usual case being a caught
    stealing for the third out, is not a playEvent at all: it is the play's own
    `result.eventType`, and it lands only in the `plays` table. Until 2026-09-11
    this module read the events table alone, and 40.56% of every caught
    stealing in the corpus was neither priced nor counted while the artifact
    said the excluded attempts were counted.

    THE DE-DUPLICATION KEY KEEPS event_type. A play result that is ALSO an event
    row of the same type in the same plate appearance is the same attempt and is
    counted once. A play result whose plate appearance holds a steal event of a
    DIFFERENT type is a second, real attempt (a runner steals second, then is
    caught at third to end the inning), and keying on the plate appearance alone
    would silently drop it. Measured 2026-09-11: 13 such attempts.

    THE PLAY RESULT COMES LAST. Every playEvent in the plate appearance precedes
    it, so every state change in the plate appearance is a PRIOR state change for
    it, and it is excluded under the same rule as an event row would be.

    Returns (frame with STEAL_KEY + prior_sc, count of play results that were
    already event rows).
    """
    st_pl = pl.loc[pl["event_type"].isin(STEAL_EVENTS), STEAL_KEY].copy()
    if st_pl.empty:
        return st_pl.assign(prior_sc=0), 0
    seen = st_ev[STEAL_KEY].drop_duplicates()
    st_pl = st_pl.merge(seen, on=STEAL_KEY, how="left", indicator=True)
    dup = st_pl["_merge"] == "both"
    st_pl = st_pl[~dup].drop(columns="_merge")
    sc = sc_per_pa.rename("prior_sc").reset_index()
    st_pl = st_pl.merge(sc, on=["game_pk", "at_bat_index"], how="left")
    st_pl["prior_sc"] = st_pl["prior_sc"].fillna(0).astype(int)
    return st_pl, int(dup.sum())


def _census(census: dict, n_priced: int, excluded: dict) -> dict:
    """Every steal attempt in the corpus, and the identity that accounts for it.

    THE LAW (audit F02-02): priced plus excluded equals the corpus's own
    attempt count. The artifact carries both sides and whether they agree, so
    the served-invariant test can hold it over the published file, and a
    reader of the exclusion table can see that the table closes.
    """
    ev = int(census.get("from_the_events_table", 0))
    po = int(census.get("from_the_play_result_only", 0))
    accounted = int(n_priced) + int(sum(excluded.values()))
    return {
        "from_the_events_table": ev,
        "from_the_play_result_only": po,
        "play_result_already_an_event_row": int(
            census.get("play_result_already_an_event_row", 0)),
        "total": ev + po,
        "priced_plus_excluded": accounted,
        "reconciles": accounted == ev + po,
        "seasons": list(census.get("seasons") or []),
        "note": (
            "a steal attempt reaches the corpus in one of two places. A steal "
            "in the middle of a plate appearance is a row in the events table; "
            "a steal that ENDS the plate appearance, such as a caught stealing "
            "for the third out, is only the play's own result. Both are read, "
            "and a play result that is also an event row of the same type in "
            "the same plate appearance is counted once. Every attempt is either "
            "priced or counted in the exclusion table, and priced_plus_excluded "
            "equal to total is the check that says so."),
    }


def summarize(df) -> dict:
    """The artifact. Counts and sums, with the identity checked rather than
    asserted in prose."""
    ok = df[df["dv"].notna()]
    ident_max = float((ok["dv"] + ok["er"] - ok["realized_delta"]).abs().max()) \
        if len(ok) else None
    by_target = {}
    for tgt, g in ok.groupby("target"):
        swing = g["we_success"] - g["we_fail"]
        sw_ok = float(swing[g["success"]].mean())
        sw_no = float(swing[~g["success"]].mean())
        by_target[tgt] = {
            "n": int(len(g)),
            "success_rate": round(float(g["success"].mean()), 4),
            # BOTH the mean and the median break-even. They disagree sharply on
            # steals of home (0.672 against 0.507), because a handful of states
            # carry an enormous p* and drag the mean past 1. Publishing the mean
            # alone would say the average attempt was unjustified while the sum
            # of decision values says the opposite, and the median is the
            # summary that matches the arithmetic.
            "mean_breakeven_p": round(float(g["breakeven_p"].mean()), 4),
            "median_breakeven_p": round(float(g["breakeven_p"].median()), 4),
            "share_of_attempts_below_their_own_breakeven": round(
                float((g["breakeven_p"] < g["league_p"]).mean()), 4),
            # THE SWING-WEIGHTED BREAK-EVEN, which is the one that predicts the
            # sign exactly. DV for an attempt is (WE_success - WE_fail) times
            # (league_p - p*), so the sum of decision values is positive exactly
            # when the league rate beats the SWING-WEIGHTED average of p*, not
            # the plain average and not the median. Publishing the other two
            # without this one invites a reader to check the sign against a
            # number that does not determine it: on steals of second the league
            # rate clears the median break-even and the summed decision value is
            # still slightly negative.
            "swing_weighted_breakeven_p": round(
                float((g["breakeven_p"] * swing).sum() / swing.sum()), 4)
            if float(swing.sum()) else None,
            "mean_dv": round(float(g["dv"].mean()), 6),
            "sum_dv_wins": round(float(g["dv"].sum()), 2),
            "mean_er": round(float(g["er"].mean()), 6),
            "sum_er_wins": round(float(g["er"].sum()), 2),
            # THE SWING ASYMMETRY, which is why the execution residual does not
            # sum to zero even though the success rate it is priced against is
            # the group's own mean.
            "mean_swing_on_success": round(sw_ok, 5),
            "mean_swing_on_failure": round(sw_no, 5),
            "swing_ratio_failure_over_success": round(sw_no / sw_ok, 4)
            if sw_ok else None,
        }
    by_season = {}
    for s, g in ok.groupby("season"):
        by_season[str(s)] = {
            "n": int(len(g)),
            "success_rate": round(float(g["success"].mean()), 4),
            "sum_dv_wins": round(float(g["dv"].sum()), 2),
            "sum_er_wins": round(float(g["er"].sum()), 2),
        }
    excluded = dict(df.attrs.get("excluded", {}))
    return {
        "generated_at": datetime.now(timezone.utc)
                        .replace(microsecond=0).isoformat(),
        "produced_by": "management.py",
        "family": "running game: the stolen base decision",
        "n_attempts_priced": int(len(ok)),
        "excluded": excluded,
        "attempt_census": _census(df.attrs.get("attempt_census") or {},
                                  int(len(ok)), excluded),
        "decomposition": {
            "dv": ("the DECISION, priced with the league-average success rate "
                   "for that season and target base. Was sending anybody here a "
                   "good idea?"),
            "er": ("the EXECUTION RESIDUAL, realized minus expected. Did this "
                   "runner beat the throw? Attributed to the runner, never to "
                   "the manager."),
            "identity": "DV + ER = the realized win-probability change, exactly",
            "identity_max_abs_error": ident_max,
        },
        "by_target": by_target,
        "by_season": by_season,
        "why_execution_residual_does_not_sum_to_zero": (
            "ER is priced against the group's OWN mean success rate, so "
            "successes and failures balance in count but need not balance in "
            "value: sum ER equals the sum over attempts of (success minus "
            "league_p) times the win-probability swing, an identity this "
            "artifact checks. RESOLVED 2026-09-06. On the full population the "
            "swing on failed attempts ran about 1.5 times the swing on "
            "successful ones, which invited a behavioural reading (defences "
            "hold runners better when it matters). It was MECHANICAL. Once the "
            "two-out attempts are excluded, and with them every caught stealing "
            "that ends an inning, the ratio falls to 1.00 on steals of second "
            "and 1.05 on steals of third. The asymmetry was the third out, not "
            "the defence. Whatever residual remains is small enough that the "
            "execution term now nearly sums to zero, which is what it should do "
            "when it is priced against its own group's mean."),
        "league_average_is_deliberate": (
            "the decision is scored as though the manager had a league-average "
            "runner, because the runner's speed is a roster fact and crediting "
            "a manager for having a fast team is the confound this module "
            "exists to avoid."),
        "which_breakeven_predicts_the_sign": (
            "the swing-weighted one. DV for an attempt is (WE_success minus "
            "WE_fail) times (league_p minus p*), so the summed decision value "
            "for a group is positive exactly when the league success rate beats "
            "the swing-weighted mean of p*. The median and the plain mean are "
            "published because they are the readable summaries, and neither "
            "determines the verdict."),
        "breakeven_is_published": (
            "p* = (WE_hold - WE_fail) / (WE_success - WE_fail) rides every "
            "attempt, because it is the number a reader can argue with: if the "
            "league succeeds more often than p*, the attempt was justified."),
        "third_out_handling": (
            "a caught stealing with two down ends the half-inning, and the "
            "resulting state is valued as the NEXT half-inning from the other "
            "team's point of view. Pricing it as two-outs-bases-empty would "
            "understate the cost of the worst possible time to be thrown out."),
        "two_out_attempts_are_excluded": (
            "with nobody out or one out a caught stealing leaves the inning "
            "alive, so both sides of the comparison come from the same monotone "
            "model. With two out it ends the inning, so the alternative comes "
            "from the measured half-inning-start table instead, and nothing "
            "calibrates the two estimators against each other. Across three "
            "builds of the engine that mismatch priced between 8.7% and 19.2% "
            "of attempts so that being CAUGHT STEALING HELPED the batting team, "
            "carrying up to 22.6% of the total decision value. Those attempts "
            "are excluded and counted. Pricing them needs an inning-level model "
            "that predicts the boundary and the mid-inning state together, "
            "which has not been built."),
        "not_yet_attributed_to_managers": (
            "this artifact stops at the attempt. Attributing an attempt to a "
            "manager needs the manager entity (M-MWAR-2), and no MWAR number "
            "may be published before the gate battery runs."),
    }


def corpus_built_at(corpus: Path | None = None):
    """The play corpus manifest's built_at, or None.

    Stamped on the artifact so /management/ can say which corpus the Running
    Game tab was priced from, and whether it is the corpus the decision ledger
    (which carries the per-season through-dates) was built from.
    """
    try:
        m = json.loads((Path(corpus or CORPUS) / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return m.get("built_at")


def build() -> dict:
    """The management_running.json payload on the corpus at CORPUS (main writes it;
    the nightly step mgmt_nightly.py calls this and write())."""
    df = attempts()
    art = summarize(df)
    art["corpus_built_at"] = corpus_built_at()
    # The league totals the page's headline prints, on THIS artifact's attempts.
    # They were read off the frozen gate eval, which is right only while the gate
    # and this file share a corpus; after a corpus rebuild the headline would
    # sum a different set of attempts from the cards beside it.
    ok = df[df["dv"].notna()]
    art["net_dv_wins"] = float(ok["dv"].sum())
    art["sum_abs_dv_wins"] = float(ok["dv"].abs().sum())
    try:
        _m = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
        art["games_in_corpus"] = int(sum(int(v.get("games") or 0)
                                         for v in (_m.get("seasons") or {}).values()))
    except (OSError, ValueError):
        art["games_in_corpus"] = None
    return art


def write(art: dict) -> None:
    OUT.write_text(json.dumps(art, indent=1) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s: %(message)s")
    art = build()
    if "--dry-run" not in argv:
        write(art)
    print(f"priced attempts: {art['n_attempts_priced']:,}  "
          f"excluded {art['excluded']}")
    c = art["attempt_census"]
    print(f"attempt census: {c['total']:,} in the corpus "
          f"({c['from_the_events_table']:,} event rows + "
          f"{c['from_the_play_result_only']:,} play results only); "
          f"priced + excluded = {c['priced_plus_excluded']:,}  "
          f"reconciles={c['reconciles']}")
    print(f"DV + ER identity, max abs error: "
          f"{art['decomposition']['identity_max_abs_error']}")
    print("\nby target base:")
    for t, v in art["by_target"].items():
        print(f"  {t:5s} n={v['n']:6d} success={v['success_rate']:.3f} "
              f"breakeven med={v['median_breakeven_p']:.3f} "
              f"mean={v['mean_breakeven_p']:.3f}  "
              f"sum DV={v['sum_dv_wins']:+8.2f}  "
              f"sum ER={v['sum_er_wins']:+8.2f}  "
              f"swing fail/succ={v['swing_ratio_failure_over_success']:.2f}")
    if "--dry-run" not in argv:
        print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
