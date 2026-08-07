# DFS park leg: pre-registered gate (2026-08-07)

Lane I6 / G3a. Written and committed to BEFORE any result was computed. The
measurement script is `tools/dfs_park_gate.py`; it prints the numbers this
document names and nothing else was inspected first.

## Why a gate at all

G3b (Vegas implied team totals) and G3c (confirmed lineups) are DISPLAY context.
They do not enter `pts`, so no served number moves and no gate is owed.

G3a is different. The park factor multiplies `hit_mult` and `allow_mult`, which
multiply the counting line, which is what `score_line` scores. Every hitter and
every starter on the board changes price. That is a served number moving, so it
needs a gate registered in advance, a zero-information control, and a stated
loss if it fails.

## The claim under test

The Savant runs index already on disk in `data/fa_meta.json` (29 of 30 clubs;
ATH has no entry), applied in the multiplicative form `dfs_export` already
writes (`x pf`, then clamped), predicts a team's actual runs in a game better
than the neutral park the module serves today.

This is deliberately the WEAKEST form of the claim, and it is the one the code
makes. The DFS module does not fit anything; it multiplies. So the gate asks
whether multiplying by this index, with no coefficient and no shrinkage, beats
multiplying by 1.0.

## Sample

`.cache/betting/completed_games.json`: every completed 2026 regular-season game
the betting module has cached, one row per game with `home_org`, `away_org`,
`home_runs`, `away_runs`. Both sides of a game are scored, so n team-games is
twice n games. Games whose home org has no `fa_meta` park entry (ATH) are
EXCLUDED from both arms rather than silently priced at neutral in one of them,
because including them would dilute a real effect toward zero in the treatment
arm only.

No neutral-site filter is applied here and the reason is worth stating: this
cache carries no venue id, so a neutral-site game is indistinguishable from a
home game in it. That biases the gate AGAINST the park leg (a handful of games
get the wrong park), which is the safe direction for a ship decision. The
SERVED path does not share the limitation: it resolves the venue id against the
StatsAPI club-venue map and refuses the leg when the game is not at the home
club's park.

## Predictors

Both predict runs for one team in one game.

* A (control, what ships today): `r_hat = mu`, the league mean runs per
  team-game over the sample.
* B (treatment): `r_hat = mu * pf(home_org)`, where `pf` is the fa_meta runs
  index over 100. Both sides of a game take the same multiplier, which is what
  a park factor means.

Nothing else differs. Offense, opponent, starter and home field are absent from
BOTH arms on purpose: this gate is about the park term in isolation, not about
whether a run model is any good.

## Decision rule, fixed in advance

Primary metric: RMSE over team-games. Secondary, reported but not decisive: MAE.

SHIP if BOTH hold:

1. RMSE(B) < RMSE(A). Any improvement at all counts here because B has zero
   free parameters, so there is no fitting to pay for.
2. The permutation p-value is < 0.05. The zero-information control shuffles the
   29 park indices across the 29 orgs (10,000 draws, fixed seed 20260807) and
   recomputes RMSE(B'). p is the share of draws with RMSE(B') <= RMSE(B). A real
   park signal must beat a park index that has been scrambled across parks.

NO-SHIP otherwise. Marginal is FAIL, and condition 2 is what makes "marginal"
decidable rather than a matter of taste.

## Committed loss if it fails

The park leg stays neutral. `park_source` keeps reporting that no factor applied
to MLB venues, and the payload note changes from "the committed artifact covers
the minor league ladder only" to the true and more embarrassing sentence: an MLB
park index exists on this box, we tested it against a season of games, and it
did not earn a place in the price. G3b and G3c ship regardless; they are not
downstream of this.

## Result (recorded after the rule above, not before)

```
sample: 1720 completed games, 3326 team-games priced,
        57 games dropped (home park has no fa_meta entry)
league mean runs per team-game (mu): 4.4330
park index spread: 0.830..1.280 over 29 parks
A neutral   RMSE 3.18655   MAE 2.53119
B park leg  RMSE 3.17302   MAE 2.51354
delta RMSE  -0.01353       delta MAE -0.01766
permutation control (10000 draws, seed 20260807):
        3 shuffled indices did at least as well -> p = 0.0003
VERDICT: SHIP
```

Both conditions hold. The effect is SMALL in absolute terms (0.42% of RMSE) and
that is the honest size of it: a single game's runs are dominated by count noise
with a standard deviation near 3.2, and no park index was ever going to move
that much. What the permutation control establishes is that the small
improvement is not luck. Three of ten thousand scrambled park assignments did as
well as the real one.

## What shipped, and one thing the gate forced that was not in the plan

The clamps on the matchup multiplier (`_HIT_MULT_CLAMP`, `_PIT_ALLOW_CLAMP`)
were sized against the spread of the opponent indexes, back when every MLB park
factor was exactly 1.00. Folding the newly-resolving park inside them made the
guard rail the operative term for the extreme parks, which are the parks
carrying the most park signal: measured on the 2026-08-07 slate, 0 of 30 game
sides bound the hit clamp without the park leg and 2 of 30 bound it with, both
at T-Mobile Park (0.83), where an honest multiplier of 0.707 was being clipped
to 0.800.

So the clamp now wraps the matchup index alone and the park multiplies the
clamped result. That reordering moves NO number that was ever served: clamping
before or after multiplying by exactly 1.0 is the same arithmetic, and 1.0 is
what every MLB park leg was until this change. `test_dfs_park_composition_never_moved_a_served_number`
pins the equivalence rather than leaving it as an assertion in a comment.

A separate guard clamps the park FACTOR itself to 0.70-1.45 and marks any leg it
had to touch. The committed table spans 0.83 to 1.28, so nothing honest reaches
it; it exists so a factor written as 108 rather than 1.08 cannot multiply a
club's whole slate, and so that a clipped value can never pass for a measured
one.

## What this gate does NOT establish

That the DFS point projections are accurate. Nothing on the board has been
graded against realized DFS scores, and this gate does not change that. It
establishes one narrow thing: the park multiplier carries information about
runs. The board keeps saying so.
