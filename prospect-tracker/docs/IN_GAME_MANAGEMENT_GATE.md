# In-Game Management: the gate battery for the running-game family

Frozen 2026-09-06. This document is written BEFORE the gate numbers are computed, and the
policies below may not be edited once a number has been read against them.

## What is being gated

`management.py` prices 13,971 stolen-base attempts from 2018, 2019 and 2021-2026 and splits
each into a DECISION value (priced at the league success rate, so a manager is scored as though
he had a league-average runner) and an EXECUTION residual (attributed to the runner). The two
sum to the realized win-probability change exactly.

The question this battery asks is not whether the pricing is right. It is whether the resulting
per-agent number is a REPEATABLE PROPERTY OF THE AGENT or noise. A decision metric that cannot
survive a split-half is measuring the schedule.

## The agent

Team-season, not manager. There is no manager entity anywhere on disk: the win probability
cache is a bare play list with no `gameData`, and the corpus tables carry no team identity at
all. Team attribution is recovered offline from `.cache/war_daily/bat.parquet` by assigning each
batter to the club he took the most plate appearances for in that season and reading the bottom
half's batting team as the home team.

A team-season is a WEAKER agent than a manager, and in one specific direction: managers change
and teams do not, so team-season persistence is an UPPER BOUND on manager persistence. If the
team-season signal is null, the manager signal cannot be larger. That is what makes a null here
decisive rather than merely unhelpful.

## THE DECISION MADE BEFORE THE GATE RAN, and why it was made first

A preflight measured split-half stability two ways and they disagreed by an order of magnitude:

| series | split-half pearson on mean DV | one-way ICC |
|---|---|---|
| raw decision value | +0.7789 | 0.11226 |
| season-controlled | +0.0691 | 0.00538 |

The raw series is not a measure of the agent. Decomposing the variance of team-season summed
decision value: **season alone explains 0.7961 of it, and team identity alone explains 0.0223**.
Both halves of a team-season sit in the same season, so any league-wide year effect shows up as
split-half agreement while saying nothing whatever about the team.

A prior design note guessed the driver was TARGET MIX, meaning teams that attempt more steals of
third. That guess is wrong and the correction is recorded here: the correlation between a
team-season's summed decision value and its share of attempts that are steals of second is
-0.0667, which is nothing. The driver is the season.

**THE PUBLISHED SERIES IS THE SEASON-CONTROLLED ONE.** The raw series is published beside it and
labelled as season-driven, with the 0.7961 decomposition attached, so that a reader who
encounters the larger number elsewhere can see why it is not the answer.

This choice was made before the null bands, the placebo or the captured share were computed. It
is a choice about WHICH QUANTITY IS THE AGENT'S, not a choice about which result to report, and
recording the distinction is the point of freezing it here.

## THE HEURISTIC MANAGER, frozen

Owner decision 11 makes a written-down policy the headline baseline, chosen because it is the
only baseline a reader can argue with. For the running game the policy is:

> **Attempt a steal of second with nobody out or one out whenever the state's break-even success
> rate p\* is at or below the season's league success rate, choosing spots AT RANDOM among the
> qualifying opportunities, and attempt at the same overall rate the league actually attempted
> at in that season. Never attempt otherwise.**

That policy's key in the artifact is `random_among_qualifying`, and this document uses the
artifact's own keys throughout so a policy string and a number cannot drift apart.

Two other policies were considered and are NAMED HERE so that the one used cannot be swapped
afterwards for a friendlier number:

- `random_among_all`, the all-opportunities random policy: attempt at the league rate chosen at
  random among ALL opportunities, ignoring p\*.
- `margin_5pct`, the margin policy: attempt only where p\* is cleared by five percentage points.

The captured share is `(actual - heuristic) / (optimal - heuristic)`. It is known in advance
that this quantity can change SIGN between these three policies, because the heuristic term
appears in both numerator and denominator. **All three are computed and all three are
published.** A captured share quoted without its policy string is meaningless, and the artifact
carries the policy string beside every value.

## The opportunity set

`outs_before < 2`, a runner on first, second base empty. This matches the population
`management.py` prices: two-out attempts are excluded from the family because the hold value and
the caught-stealing value would come from two different estimators, and nothing calibrates them
against each other.

## The four legs

1. **Split-half stability.** Alternate each agent-season's attempts by (game_pk, at_bat_index)
   into halves, keep agents with at least 10 in each half, correlate. The null is
   OPPORTUNITY-PRESERVING: permute decision value WITHIN season across all attempts, which holds
   every agent-season's attempt count fixed. A null that reassigns attempt counts destroys the
   structure being tested and produces a band that anything clears.
2. **Persistence.** Year-over-year on season-demeaned agent numbers. This is a TEAM proxy for
   manager persistence and is recorded as such, with the upper-bound argument stated.
3. **Placebo.** Shuffle decision value within matched state cells and re-run leg 1. The metric
   must collapse. If the cells are thin the shuffle approaches an identity and the artifact must
   say so with the median cell size attached.
4. **Captured share**, under all three policies above.

## The stop rule

If leg 1 fails or leg 3 does not collapse, the family ships **descriptive only**: the board
renders and the plus metric is withheld, exactly as `leverage_board` does today. In that case
the board may be sorted by attempt VOLUME, which is a style axis, and never by decision value.

**A null here also decides M-MWAR-2.** If a team-season, which is an upper bound, carries no
repeatable decision signal in this family, then fetching the manager entity in order to attribute
that signal is not worth building for this family. The artifact must say so explicitly rather
than leaving the fetch on a backlog.

## What a null does NOT mean

It does not mean managers do not matter. It means THIS FAMILY, the stolen base, priced on
league-average success and restricted to the 60 percent of attempts that can be priced with one
estimator, carries no measurable team-to-team spread. The running game is the family where the
league already sits at the point of indifference: 75.00 percent success against a 75.03 percent
swing-weighted break-even. A family with more room, the bullpen or the pinch hit, could still
carry signal, and this document does not speak to those.
