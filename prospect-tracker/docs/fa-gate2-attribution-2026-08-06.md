# FA Gate-2 attribution: which WAR input is costing AAV accuracy

Run 2026-08-06 on the owner's instruction to attribute before deciding. Four
runs, config only, using the two kill switches that `fa_projection` already
reads at call time (`EEPHUS_FA_REALWAR`, `EEPHUS_FA_DEF`). No code was edited and
nothing was persisted.

## Result

Model MAE, and in each cell the model's gap over its baseline. Higher gap is
better; lower MAE is better.

| arm | guarantee | AAV | years | mega guarantee |
|---|---|---|---|---|
| baseline, both on | 10.207 / +1.276 | 3.135 / +0.224 | 0.429 / +0.078 | 86.065 / +9.066 |
| REALWAR off | 10.054 / +1.149 | 3.100 / +0.183 | 0.430 / +0.082 | 81.931 / +15.519 |
| **DEF off** | **9.690 / +1.430** | **2.909 / +0.340** | 0.433 / +0.054 | **79.814 / +15.457** |
| both off | 9.926 / +1.221 | 3.032 / +0.232 | 0.432 / +0.079 | 87.029 / +12.976 |

**F-DEF is the input costing AAV accuracy.** Removing it improves AAV MAE by
0.226 $M, which is about 2.5 times the 0.091 $M MDE95 recorded for AAV, and it
widens the model's edge over its own baseline from +0.224 to +0.340. It is also
the best arm on guarantee (9.690 against 10.207) and on mega guarantee (79.814
against 86.065).

Removing REALWAR helps far less and costs edge on AAV (+0.183 against +0.224).
Removing both is worse than removing DEF alone on every money metric, so the two
are not additive and DEF is doing the damage on its own.

The only metric DEF-off loses on is years, where the gap narrows from +0.078 to
+0.054. Years is already the smallest and least valuable of the four.

## A correction to how this was first reported

A scoping pass flagged a "Gate-2 regression" between 2026-07-29 and 2026-08-03,
citing guarantee MAE 9.678 rising to 10.207 and AAV 2.959 rising to 3.135 on
identical rows. That framing does not survive checking.

The BASELINE moved with the model: guarantee base 10.860 to 11.483, AAV base
3.210 to 3.359. A model change cannot move its own baseline, and both artifacts
carry the same `model_version` (`fa_mkt_v2`), the same basis
(`npv_deferral_adjusted`) and the same test winters. So the sample moved, not the
model.

On the gap the gate actually uses, that window was mixed rather than a
regression: guarantee improved by 0.095, years improved by 0.036, AAV worsened by
0.027 which is inside its own 0.091 MDE95 and therefore not detectable, and mega
worsened by 8.05, which is the one real signal in it.

The attribution above is a cleaner instrument than that comparison, because all
four arms run on the same rows at the same time.

## What this does not settle

F-DEF won Gate 1. It improves the WAR projection and it costs money accuracy in
the market model. Those are different objectives and the measurement cannot
choose between them.

Turning DEF off inside `/fa/` only is a PIN: it would make free agent pricing
read a different WAR than `/projections/` does for the same player. There is
precedent, `use_ml=False` is already pinned for the market model, but a reader
seeing two different WAR figures for one player deserves an explanation on the
page rather than a discrepancy to discover.

That trade is the owner's call and nothing has been changed pending it. The
switches are config, so acting on this is a one-line change whenever the decision
is made.
