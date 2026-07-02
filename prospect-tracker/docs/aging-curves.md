# Aging treatments on the site: three curves, three populations

Written 2026-07-01 (pre-Beta audit, lane B). The platform carries three
separate aging treatments. That is deliberate, not drift. Each one is fitted
to (or shaped for) a different population with different available inputs,
and each does a different job. This page documents all three so the fork is
never mistaken for duplication and "unified" by accident.

## 1. FA Marcel fitted curves (veterans, component level)

- Code: fa_projection.py. Artifact: data/fa_aging_curves.json
  (CURVES_PATH, declared around line 50; written by the curve fitter around
  line 394). The artifact is LIVE and committed: it is the fitted model, not
  a cache. Do not delete or hand-edit it.
- Population: MLB veterans with recent MLB history (the FA class board and
  the /projections/ veteran engine).
- What it is: per-side, per-role, per-component age-to-age deltas (hitters:
  K%, BB%, ISO, BABIP, HR/PA; pitchers: K%, BB%, HR/BF; plus war_rate and
  playing time), with a survivorship correction (dropouts were headed the
  bad way, so the observed stay-in-sample delta is corrected by attrition
  times the selection gap) and 3-age smoothing. Profile cohorts (power vs
  contact hitters, power vs finesse pitchers) get their own curves where the
  data supports it.
- Why fitted curves here: veterans carry enough MLB history to age at the
  component level, and multi-year contract paths need component decay, not
  a scalar. The regressed-rate form (projection v2, commit 7416ef2) fixed
  the multi-year tail collapse the naive form produced.

## 2. LightGBM-learned aging (proj_ml quantile bands)

- Code: proj_ml.py. Features include age, age squared, and age x last-year
  WAR (see the feature list around line 173), alongside WAR lags and the
  engine projections themselves.
- Population: the same veteran universe, but a different job: calibrated
  P10-P90 uncertainty bands around the projection, not the central path.
- What it is: no explicit curve. The gradient-boosted quantile models learn
  the age response directly from historical outcomes. The fitted Marcel
  curves still enter indirectly, because the engine projections that use
  them are input features.
- Why learned here: the band model's job is honest uncertainty. Imposing
  the fitted curve a second time would double-count the age signal already
  present in the features, and the quantile loss lets the data say how age
  widens or narrows the outcome distribution (which a mean-path curve
  cannot express).

## 3. Bucket tent multiplier (value_framework prospect paths)

- Code: value_framework.py, _aging_multiplier (around line 901), used by
  _trajectory_shape and the prime-anchored peak projection. Config:
  value_framework_config.yaml `aging:` block (hitter peak 27, pitcher peak
  25, ~4%/yr climb before peak, ~7%/yr decline after, floor 0.25).
- Population: prospects on the surplus and outcome-model paths. No MLB
  track record exists; the only age inputs are projected debut age and the
  FV outcome bucket.
- What it is: an asymmetric tent, peak normalized to 1.0, evaluated at the
  player's age in each control season and renormalized to mean 1.0 across
  the six-year window. It only redistributes WAR across the window (where
  on the curve the control years sit, which the discounting then prices);
  the window average still reconciles to the bucket midpoint.
- Why a shaped prior here: there is nothing to fit a personal curve on. A
  component-level veteran curve applied to a 19-year-old with zero MLB
  seasons would be false precision. The tent encodes the one thing reliably
  known (peak age and rough slope) and deliberately never changes the total.

## Why the fork is defensible

- Different populations: FA veterans (1), the ML band model over the same
  veterans but a different target (2), and prospects with no MLB history (3).
- Different inputs: full component histories (1), feature vectors with age
  terms (2), debut age and FV bucket only (3).
- Different jobs: central multi-year paths (1), calibrated uncertainty
  bands (2), redistribution of a fixed control-window total for pricing (3).

Collapsing them into one curve would either starve the veteran engine of
component detail, double-count age in the band model, or grant prospects a
fitted specificity the data cannot support. If any one treatment changes,
re-run its own eval (proj_eval.py for the veteran curves is the standing
rule) rather than reaching for a shared object.
