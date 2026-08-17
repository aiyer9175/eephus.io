# Closer save-share model: pre-registered gate (2026-08-16)

Fantasy-evidence lane, task B4-3. Written and dated BEFORE the measurement
script existed or ran. The lab is `tools/fantasy_closer_lab.py`; it prints and
records the numbers this document names, and the result section at the bottom
is the ONLY part of this file written after the run. The clauses above it are
frozen: the lab result does not edit them.

This gate was pre-registered a second time in the model registry on the same
day (row `fantasy_closer_depth`, notes field), with the same baseline and the
same two metrics. This document is the full statement of those terms.

## Why a gate at all

Two shipped surfaces guess at reliever roles today:

* `/redraft/` ROS saves: `fantasy_export.build_players` prices every RP's
  rest-of-season SV as season-to-date saves extrapolated by season fraction
  (`sv * remaining / frac`). That is the PACE rule.
* the Closer Depth Chart: a hand-weighted role score
  (`gmli * 100 + saves * 3 + rem_plus * 0.2`), registered unvalidated.

A save-share model that allocates forward team saves across a bullpen from
trailing usage would replace both. It moves served numbers, so it does not
ship on plausibility: it ships if and only if it beats the pace rule on the
two metrics below, on data that existed before the model did.

## The claim under test

A per-team save share built from a trailing 30-day window of saves and gmLI
predicts each reliever's NEXT-14-DAY saves better than extrapolating that
reliever's own season-to-date pace.

## Champion (the challenger being gated)

For team t at replay date T, over the eligible pool (defined below), all from
the trailing window [T-30, T-1]:

    sv_share_i   = sv30_i / team_sv30          (team_sv30 = sum of sv30 over the pool)
    gmli_share_i = max(gmli30_i, 0) / sum_j max(gmli30_j, 0)
                   (gmli30_i = mean entry leverage index over the pitcher's
                    relief appearances for t in the window)
    share_i      = w_sv * sv_share_i + w_gmli * gmli_share_i

FIXED WEIGHTS, NO FITTING: `w_sv = 0.65`, `w_gmli = 0.35`. Stated here before
any number was computed and never tuned by the lab. Rationale: saves are the
direct evidence of the role; gmLI is the manager-trust signal that leads saves
when a role is changing hands. Degenerate cases, decided in advance: a team
with `team_sv30 = 0` drops the sv term and renormalizes onto gmli alone; a
pool whose gmli sum is 0 does the reverse; both zero means uniform shares.

    predicted next-14-day saves_i = share_i * team_sv30 * (14 / 30)

The team forecast term is deliberately the dumbest defensible one (trailing
saves scaled by days). Both arms predict raw saves so the MAE is comparable;
the share itself is what the Spearman isolates.

## Baseline (what ships today)

The pace rule, translated to the same 14-day horizon:

    predicted next-14-day saves_i = sv_std_i * 14 / days_elapsed

`sv_std_i` = the pitcher's season-to-date saves through T-1 (any club, which
is what the shipped leaderboard field carries), `days_elapsed` = days from the
season's first final game to T-1, inclusive. Same pool, same target.

## Frame

Replayed 2026 regular-season windows from data that existed before this gate:

* SAVES, per game per pitcher, with dates and clubs: the official save
  decision on the StatsAPI season schedule (`hydrate=decisions`), fetched once
  and cached under `.cache/closer_lab/`.
* gmLI, per relief appearance: entry leverage index from the committed
  `.cache/win_prob/{game_pk}.json` cache (18,862 games on this box; 1,876 of
  1,891 final 2026 games covered at pre-registration time). A relief
  appearance is an `entry_inning > 1` appearance, the same rule
  `mlb_leverage._merge_reliever` uses. Club per appearance comes from the
  play's half-inning side joined to the schedule's home and away orgs.
* ELIGIBLE POOL per (team, T): pitchers with at least 2 relief appearances
  for that club in [T-30, T-1].
* TARGET: saves in [T, T+13] credited while pitching for the same club.

Window starts: base 2026-04-24 (the first date with a full 30-day trailing
window inside the season), teams split into three groups by alphabetical org
index mod 3 with offsets 0, 5, 10 days, and each team's starts spaced exactly
14 days so its forward label windows never overlap. Starts run while
T+13 stays inside the resolved data. That yields roughly 22 distinct start
dates (7 to 8 per team, about 220 team-windows), which is the "~20
non-overlapping starts" this frame was asked to support.

## Metrics, fixed in advance

1. MAE of predicted next-14-day saves per RP, pooled over all rows of a
   window start (across its teams), and pooled overall.
2. Within-team Spearman of the predicted allocation against realized
   next-14-day saves, per (team, T), computed only where the pool has at
   least 3 arms and neither vector is constant; a window start's value is the
   mean over its valid teams. Both arms are ranked by their own predictions.

Reported but NOT decisive: the same numbers for a saves-only share
(`w_sv = 1.0`), so a pass or fail also says whether gmLI earned its weight.
Coverage counts (games with cached win_prob, teams skipped, constant-vector
skips) are reported alongside.

## Ship bar, fixed in advance

SHIP the share model only if ALL THREE hold:

1. pooled MAE: champion < baseline;
2. overall mean within-team Spearman: champion > baseline;
3. sign-consistency: the champion wins BOTH metrics (MAE delta < 0 AND
   Spearman delta > 0) in at least 70% of the window starts. A tie on either
   metric counts against the champion.

RED otherwise. Marginal is FAIL.

## Data-blocked clause

If the win_prob cache covers under 90% of final 2026 games, or the schedule
returns no save decisions, or fewer than 15 window starts survive the frame,
the lab STOPS and reports DATA_BLOCKED with what it searched. It does not
substitute a coarser frame, and nothing ships.

## Committed loss if it fails

The pace rule stays in `fantasy_export.build_players` exactly as shipped. The
Closer Depth Chart keeps its hand score and its unvalidated verdict. The
refusal is recorded in the lab's eval artifact
(`.cache/closer_lab/fantasy_closer_gate_eval.json`) and in this document, and
the registry row's gate language gets the outcome noted by the orchestrator.
No served number moves.

## What ships if it passes

Only what was measured: the RP rest-of-season SV allocation in
`fantasy_export._pitcher_ros` / `build_players` moves to the share model, and
`closer_depth` orders by the measured share. HLD stays on pace regardless,
because holds were not in the target and a green save gate is not evidence
about holds.

## Result (recorded after the rule above, not before)

Transcribed verbatim from the lab's first and only run, 2026-08-16:

```
frame:    2026 regular season 2026-03-25..2026-08-16
          1885 final games; win_prob cached for 1876 (99.5%); 966 official save decisions
          22 window starts, 220 team-windows, 2389 RP rows, 212 rank cells (8 skipped)
pooled MAE   champion 0.3104   baseline 0.2845   delta +0.0259 (+9.1%)
mean rho     champion 0.3894   baseline 0.4155   delta -0.0261
per-start    champion wins BOTH metrics in 3 of 22 starts (13.6%; bar 70%)
sv-only ref  (w_sv=1.0)  MAE 0.2737  rho 0.4914
VERDICT: RED
```

All three ship conditions FAILED, not marginally: the champion is 9.1% worse
on pooled MAE, worse on mean within-team Spearman, and wins both metrics in 3
of 22 window starts against a 70% bar. The pace rule stays, exactly as the
committed-loss clause says, and no served number moves.

The reported-but-not-decisive reference is the finding worth keeping: the
SAVES-ONLY share (w_sv = 1.0) beat BOTH the registered champion and the pace
baseline on both pooled metrics (MAE 0.2737 vs 0.2845, rho 0.4914 vs 0.4155).
The gmLI term, registered at 0.35 on the trust rationale, actively HURT: mean
entry leverage is high for setup arms too, so the blend spreads the team's
forward saves across the seventh and eighth innings while actual saves
concentrate on the ninth. That is evidence a DIFFERENT champion exists, and it
is exactly what this document does not permit shipping: a saves-only share
was not the registered claim, and promoting the reference arm after seeing
these numbers would be fitting the champion to the test set with one degree
of freedom. If the shop wants that model, it re-registers a new gate with the
saves-only share as the named champion on windows this run never scored
(2027 data, or a differently-seeded frame), and the pace rule keeps serving
until that gate passes.

Per-window detail, coverage counts and the full config echo are in
`.cache/closer_lab/fantasy_closer_gate_eval.json`. The registry row
(`fantasy_closer_depth`) still carries the pre-registered gate language; the
orchestrator records this RED outcome there, since data/model_registry.json
is outside this lane's file ownership.
