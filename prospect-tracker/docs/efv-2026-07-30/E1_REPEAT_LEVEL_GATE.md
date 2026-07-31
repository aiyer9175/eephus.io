# E1: the repeat-level feature. Measured, and the sign splits by side

Lane E1 of `docs/master-plan-2026-07-30-nine-asks.md`, run 2026-07-30. The gate design
below was fixed before the numbers were read; the verdict is at the top because the
headline is not what the lane was built to find.

## VERDICT

| arm | verdict |
|---|---|
| **hitters** | **NO SHIP, twice over.** Permutation p = 0.375 (5 of 15 nulls beat it), AND the fitted sign is the OPPOSITE of the theory. It would raise Taylor, not lower him. |
| **pitchers** | **PASSES the feature-specific null test** (p = 0.032, 0 of 30 nulls matched it) while remaining inside the generic sampling floor. Default off. **OWNER CALL.** |

## PERMUTATION NULL (added at owner request: "re-measure with more controls first")

Feature values redrawn from the TRUE empirical marginal with the row link broken, model
and data otherwise fixed. This corrects an earlier control that drew from a hand-made
pool rather than the observed distribution.

| side | real delta | null mean | null sd | null max | B | **p** |
|---|---|---|---|---|---|---|
| **pit** | **+0.0127** | -0.0004 | 0.0030 | +0.0064 | 30 | **0.032** |
| **hit** | +0.0033 | +0.0014 | 0.0035 | +0.0101 | 15 | **0.375** |

The test separates the two arms exactly as the sign split predicted. On pitchers the real
effect is roughly **twice the largest of thirty null draws** and about 4.2 null standard
deviations out. On hitters a third of the null draws beat it.

**Two different uncertainties, both true, not in conflict.** The permutation test asks
whether a meaningless column of this shape could produce this gain: on pitchers, no. The
MDE95 asks how far the estimate would move on a redrawn eval sample: about +/-0.016, so
the magnitude stays imprecise. The pitcher arm is therefore a REAL effect whose SIZE the
eval cannot pin down, which is a different thing from a null and should not be filed as
one. It also now satisfies this codebase's own stated bar for a feature gate, set after
the pitcher-label lane: a random-label null band plus a permutation p-value
(`docs/PITCHER_LABEL_LEDGER.md`).

Both arms ship DEFAULT OFF (`efv_model.E1_REPEAT_LEVEL`). The feature itself
(`seasons_at_level`) is now computed into both matrices unconditionally, because a key
that exists on only some rows crashes the LightGBM arm, which indexes `feats` directly.

## 1. What the feature is, and why it was worth building

Consecutive seasons the player has spent at his CURRENT level, counting back from the
most recent. 1 means he arrived this year; 3 means a third straight year on the rung.
A break in the run (a different level, or a missing season) resets it, so a player who
went AA, AAA, back to AA reads 1, not 2.

Nothing in the feature set saw this. Only the FINAL pre-decision season's rates enter, so
a player repeating a level after a collapse looked identical to one who just arrived and
is hitting well. `n_milb_seasons` does not cover it and is a declared suppressor for the
opposite reason (holding level and age fixed, more total seasons means more seasons spent
REACHING the level).

The cleanest demonstration that it is new information:

| player | level | n_milb_seasons | **seasons_at_level** |
|---|---|---|---|
| brayden_taylor | AA | 4.0 | **3.0** |
| franklin_arias | AA | 4.0 | **1.0** |

Identical on the existing feature, opposite on the new one.

## 2. Results

Primary metric: pooled OOS Spearman, `debuted_km`, blend arm, forward-chained.
MDE95 0.017 hit / 0.016 pit.

| cut | OFF | ON | delta |
|---|---|---|---|
| **hit debuted_km (PRIMARY)** | 0.3882 | 0.3915 | **+0.0033** (0.19x floor) |
| hit debuted_resolved | 0.3345 | 0.3385 | +0.0040 |
| hit full_pool_km | 0.2859 | 0.2877 | +0.0018 |
| **pit debuted_km (PRIMARY)** | 0.3060 | 0.3187 | **+0.0127** (0.79x floor) |
| pit debuted_resolved | 0.2432 | 0.2450 | +0.0018 |
| pit full_pool_km | 0.2560 | 0.2610 | +0.0050 |

All six cuts positive. Forward-chained folds: 3 of 4 improved on each side. Full-pool AUC
(the higher-SNR instrument the frontier audit recommended): pitchers gain on BOTH labels
(contributor +0.0041, star +0.0059); hitters split (+0.0021 / -0.0018).

**Zero-information control** (feature values redrawn from the observed marginal under
three seeds, breaking the link to the row, so a "gain" from merely adding a column would
reproduce): the real feature beats every control on both primaries.

| primary | real | control mean | control range |
|---|---|---|---|
| hit debuted_km | +0.0033 | -0.0005 | -0.0015 to +0.0005 |
| pit debuted_km | +0.0127 | -0.0030 | -0.0085 to +0.0005 |

So the signal is real. It is the SIZE that fails, not the existence.

## 3. The finding that actually matters: the sign splits

Fitted ridge weight on `seasons_at_level`, against a declared theory of -1:

| side | fitted | vs theory |
|---|---|---|
| hitters | **+0.0945** | **DISAGREES** |
| pitchers | **-0.1072** | AGREES (and it is the 4th largest weight in the pitcher model) |

For pitchers the theory holds: stalling on a rung is bad news. For hitters it inverts.
Conditional on level, age and production, a hitter who has been at a level for several
years is one the system has kept on the board, and that reads positive. This is the third
time this codebase has caught a declared sign being wrong conditionally (`k_rel`,
`n_milb_seasons` are the other two), and the pattern is the same each time: a marginal
intuition that reverses once the obvious covariates are held fixed.

**The consequence for the lane's motivating case is direct.** Taylor is a hitter with
`seasons_at_level` 3.0 against a modal 1.0, so at +0.0945 the feature adds about +0.19
to his predicted WAR. **It would move him UP the board, not down.** The feature built to
encode "a third year at Double-A after a collapse is a warning" says, for hitters, the
opposite.

That is worth stating plainly rather than burying: **the data does not support the model
learning what the owner asked for on the hitter side.** Which is a retrospective
vindication of how ask 5 was actually delivered. The age-penalty onset is a POLICY
overlay, declared as policy, precisely because the debuted-only training pool is
survivorship-censored against the never-debut old-prospect class it exists to price. The
model cannot learn that penalty from its own data; this lane is the direct evidence.

## 4. What ships, what does not, and what is owed

- **Hitter arm: no ship.** Sub-floor gain AND a sign that contradicts its own rationale.
  Shipping a feature whose fitted direction opposes the reason it was built, on evidence
  smaller than the measurement error, is how a model accumulates unexplainable weights.
- **Pitcher arm: candidate, owner call.** It is the strongest single result in this
  program's model lanes: +0.0127 pooled, sign matching theory, 4th largest weight,
  3 of 4 folds, both AUC labels up, beats every zero-information control. It is still
  0.79x the noise floor, and the house rule says do not add features on sub-floor
  evidence. The honest framing is that this is a real effect the eval cannot resolve to
  the bar, not a null. Flipping it on is a defensible owner decision; doing it silently
  is not.
- If the pitcher arm is ever taken: it is matrix-rebuild-coupled, so
  `BOARD_RANK_BASIS_EPOCH`, `BOARD_BASIS_FINGERPRINT` and `PINNED_MIX` move together,
  the sign declaration must be recorded as -1 CONFIRMED for pit, and
  `test_efv_sign_declarations` must be extended to cover it.
