# Aging treatments on the site: three curves, three populations

Rewritten 2026-10-08 (task AG_1_AGING_DOCS_TRUTH, plan Part 9 section 9.3 'Aging v3 (the one
aging service)'). The title line is kept from the 2026-07-01 page, which defended three
treatments. The site carries FIVE aging treatments (A1 to A5), plus three smaller served age
terms (A6 to A8), and their peaks disagree. This page says where each lives, who it covers,
who reads it and what is known to be wrong with it.

Every number here is one of: a value read from code or config at commit 0f9fb164, a value in a
committed artifact, a value in the cached served fit, or a descriptive count over a served
payload (dated where it is given). No number comes from a candidate curve, bucket, archetype or
health arm. Line numbers sit beside a function name and are pinned to 0f9fb164; if a number and
the name disagree later, the name wins.

## The five treatments at a glance

| # | Treatment | Code anchor | Population | Main consumers |
|---|---|---|---|---|
| A1 | Prospect tent | `value_framework._aging_multiplier()` and `_trajectory_shape()` | prospects (no MLB history) | prospect surplus, /projections/ prospect paths |
| A2 | Veteran champion curves | `fa_projection.fit_aging_curves()` and `curve_delta()`, walked by `fa_market._decay_path()` | MLB veterans | /fa/ pricing, `warChamp`, Team Outlook, fantasy dynasty |
| A3 | ML learned age response | `proj_ml` features `age`, `age_sq`, `age_x_war`, champion path stacked | MLB veterans | /projections/ headline `war`, arbitration forward WAR |
| A4 | Contract tail seam | `fa_market.chain_aging_tail()` | MLB veterans past the five-season horizon | `warTail`, `surTotal`, Trade Machine and Ledger values past 2031 |
| A5 | Trade fallback factor | `bayes_trade_value._aging_factor()` | debuted players the Trade Machine does not re-point | the `bayes_unrepointed` trade values |

## A1. Prospect tent (value_framework)

- Code: `value_framework._aging_multiplier()` (line 1474) is an asymmetric tent, peak 1.0:
  `1 - climb * (peak - age)` at or before the peak, `1 - decline * (age - peak)` after it,
  floored. `_trajectory_shape()` (line 1490) evaluates it at the player's age in each control
  season and renormalizes the window to mean 1.0. `prospect_prime_path()` (line 1422) and
  `prospect_peak_war()` (line 1451) build the display path and the headline prime on the same
  tent; `_aged_trajectory()` (line 1546) and `_bucket_season_wars()` (line 1534) carry it into
  the per-bucket paths.
- Config: the `aging:` block in value_framework_config.yaml: `hitter_peak_age 27`,
  `pitcher_peak_age 25`, `climb_per_year_before_peak 0.04`, `decline_per_year_after_peak 0.07`,
  `min_multiplier 0.25`.
- Window: 7 seasons. The default valuation set is `clemens_2026` (`valuation_sets.DEFAULT_SET`),
  whose `control: years: 7` overrides `service_time.control_years: 6` in the yaml. The yaml's
  comment under `aging:` still says "six control seasons"; the served window is seven.
- Population: prospects on the surplus and outcome-model paths. No MLB track record exists; the
  only age inputs are the projected debut age and the FV outcome bucket.
- What it does: it only redistributes WAR across the window (where on the curve the control
  seasons sit, which discounting then prices); the window average still reconciles to the FV
  anchor. A FV 55 hitter's `_trajectory_shape("hitter", a)` and
  `prospect_prime_path(55, False, a)["mean"]` at HEAD:
  - debut 21: shape 0.864, 0.909, 0.955, 1.000, 1.045, 1.091, 1.136; path 1.99, 2.09, 2.20,
    2.30, 2.40, 2.51, 2.61 WAR; `prospect_peak_war` 2.6.
  - debut 25: shape 1.042, 1.087, 1.133, 1.053, 0.974, 0.895, 0.816; path 2.40, 2.50, 2.61,
    2.42, 2.24, 2.06, 1.88 WAR; `prospect_peak_war` 2.6.
  So the prospect path already climbs until the prime and declines after it.
- Consumers: /projections/ prospect `war`, `warPTH`, `warPeak` (`proj_export` calls
  `prospect_prime_path`); prospect surplus `vf.surplus_value_mm`, served as xFV `surplus_mm`
  (Sur+, OrgSur+, the Trade Machine's `surplus_source = xfv` rows and the Ledger's prospect leg).
- Known issues: one curve for every position (a catcher, a shortstop and a first baseman share
  it); no link to A2, whose hitter rate curve peaks about 2.5 years earlier (finding ii); pitcher
  paths for a projected debut at 25 or later fall from the first season by construction (peak
  25).

## A2. Veteran champion curves (fa_projection, walked by fa_market)

- Code: `fa_projection.fit_aging_curves()` (line 651) fits per-age additive deltas by the delta
  method, per (side, role group, component), for K%, BB%, ISO, BABIP and HR per PA (hitters),
  K%, BB% and HR per BF (pitchers), plus a WAR rate (per 600 PA or 250 BF) and playing time (PA
  or BF). `curve_delta()` (line 832) reads a delta at the nearest supported age.
  `profile_role()` (line 816) assigns the profile cohort. `fa_market._decay_path()` (line 297)
  walks a year-1 WAR forward: the rate and the exposure each add their delta at the advancing
  age. `fa_projection.project_player()` (line 1571) adds one component step into age for the
  year-1 line.
- Method and constants (fa_config.yaml): WAR rate fitted on rates regressed toward the season
  league rate (`war_rate_regression {hit_pa: 600, pit_bf: 350}`); `survivorship_lambda 1.0`;
  3-age smoothing; `min_exposure_pair {pa: 100, bf: 70}`; `age_range [21, 42]`. Fit meta
  `method = "delta_pa_weighted+survivorship+regressed_rate_v2"`.
- Roles: hitters C and H; pitchers SP and RP. Profile cohorts: pitcher K% cohorts are live
  (`k_hi 1.15`, `k_lo 0.85`, giving SP|pwr, SP|fin, RP|pwr, RP|fin); hitter ISO cohorts are
  parked neutral (`iso_hi 99.0`, `iso_lo 0.0`) because they measured worse (the fa_config.yaml
  note: season-ISO cohorts cut the horizon-5 tail ratio from 0.131 to about 0.09).
- Population: MLB veterans with recent MLB history.
- Consumers: /fa/ contract pricing (the FA market stack pins `use_ml=False`, fa_config.yaml
  `ml:` note); `warChamp` and `warY1Champ` on /projections/; Team Outlook sums
  (`proj_export._team_outlook()`, line 2359, reads `warChamp`), and through it Franchise's
  outlook leg, the Ledger's Cost+ and /betting/ Futures; A3's stack features
  (`proj_ml.build_features()`, line 209, calls `fa_market.contract_war_path()`); A4's tail;
  fantasy dynasty. Betting `lineup_strength` reads `vets[].woba[0]`, a year-1 component line that
  includes one A2 component step.
- Known issues: findings (i), (ii) and (iii) below. The live pitcher cohorts select on the same
  season's K%, the selection rule that measured worse for hitter ISO; they are not adjudicated
  against an out-of-window alternative anywhere.

## A3. ML learned age response (proj_ml)

- Code: `proj_ml.feature_names()` (line 178) lists `age`, `age_sq` and `age_x_war` beside WAR
  lags, exposure lags, component lines and the champion path medians `champ_h1` to `champ_h5`
  (stacked, so the trees start from A2 and learn its residuals). There is no explicit curve:
  the LightGBM quantile heads, one per (side, horizon 1 to 5, quantile), learn the age response
  from outcomes. The label is the season's WAR in B + h - 1 with an absent season scored 0.
- Population: the same veteran universe as A2.
- Consumers: /projections/ veterans `war`, `warP10`, `warP90`, `warPTH`, `surNpv` for horizons
  1 to 5; arbitration forward WAR (`arb_export._projected_war()`, line 90, reads `vets[].war`).
- Known issues: finding (v). Because the label scores an absent season as 0, the median falls
  with horizon for everyone (attrition, not aging), and independent heads add a sawtooth.
  docs/PROJ_PATH_SHAPE_GATE.md owns this path.

## A4. Contract tail seam (fa_market)

- Code: `fa_market.chain_aging_tail()` (line 405) extends a five-season path past its last
  season along A2's relative decay: season t prices `champ[t] * (series[h-1] / champ[h-1])`,
  floored at 0 unless `floor=False`; where the champion anchor is 0.05 WAR or less it decays the
  last value by the champion's year-over-year ratio, capped at 1.0 (0.7 where the prior champion
  season is itself about zero). `branch_champ` keeps a band and its point on the same branch.
- Population: veterans with guaranteed seasons past the horizon (past 2031).
- Consumers: `fa_market.contract_war_path()` for horizons 6 and later of the ML path and its
  P10/P90 heads; `proj_export._tail_war()` (line 146) for `warTail` and `surTotal` past 2031
  (40 rows carry `warTail` on the 2026-10-07 data/mlb_projections.json); `fa_export` for /fa/
  tails; the Trade Machine's `surTotal` and the Ledger NPV read the result.
- Known issues: it inherits A2's shape after the horizon, including finding (ii); nothing past
  h5 is validatable yet (the proj_ml docstring calls it a documented seam).

## A5. Trade fallback factor (bayes_trade_value)

- Code: `bayes_trade_value._aging_factor()` (line 1480); config block `aging_curve:` in
  value_framework_config.yaml: hitter peak 27.0 and decline 0.07, pitcher peak 25.0 and decline
  0.07, catcher peak 25.0 and decline 0.09, `min_multiplier 0.25`, `catcher_min_multiplier 0.20`
  (the code's fallback default for the catcher floor is 0.25; the yaml value serves).
- What it does: after the peak, `max(min_mult, 1 - decline * (age_at - peak))`; at or before the
  peak, `min(1.10, 1.0 + 0.025 * (peak - age_at))`.
- Population: debuted players whose Trade Machine value is bayes' own number.
- Consumers: `_gross_war_pv()` (line 1667) and `_contract_surplus_mm()` (line 1700). Their result
  serves only where `apply_platform_surplus()` (line 4950) does not re-point the row to the
  platform value: the `surplus_source = "bayes_unrepointed"` rows, 171 of 6,310 on the
  2026-10-07 data/trade_values.json, one of them under age 27 (26.4).
- Known issues: finding (iv).

## Findings at HEAD, with the evidence each rests on

**(i) The committed curve file is a stale snapshot, and its registry row is unvalidated.**
data/fa_aging_curves.json was last written 2026-06-10 (commit 081e5ffc; meta corpus seasons 2000
to 2026, the bWAR era) and nothing writes it any more: the only `fit_aging_curves()` caller is
`fa_projection.fitted_models()` (line 608), which passes `write=False`, and nothing reads the file
back. Served curves are refit at run time on the current corpus and cached in
`.cache/fa_fits_{max_season}_{first}_{last}_{sig}[_def].pkl` (the newest at HEAD is
`fa_fits_2027_2000_2026_5b3b9a75.pkl`, written 2026-10-03). The cache key digests corpus rows and
league context, not code, so a change to curve code with an unchanged corpus loads the old fit.
The registry row `fa_aging_curves` is **unvalidated** ("no standalone eval"; the curves are
exercised only through the FA gates). The file's freshness is no evidence about what serves.

**(ii) The survivorship correction flattens the hitter rate curve's top near age 24.5.** The
correction is `raw_delta + harm * lambda * attrition * |selection gap|` inside
`fit_aging_curves()`, with the harm direction -1 for the WAR rate, so it always subtracts. In
the committed fit (H, WAR per 600 PA, unsmoothed) it subtracts 0.021, 0.021, 0.024, 0.034 and
0.036 at ages 23 to 27 (raw minus corrected; 0.0205 to 0.0364, about 0.02 to 0.04 a year). Into
24: raw +0.042, corrected +0.022. Into 25: raw +0.030, corrected +0.005. Into 26: raw -0.042,
corrected -0.076. The cached served fit shows the same shape: the correction is 0.018 to 0.033
at ages 23 to 27, and the smoothed rate delta is +0.029 into 24 and -0.002 into 25. The raw
rise at 24 and 25 becomes a flat top, so the rate curve peaks about 2.5 years before A1's hitter
peak of 27. The pre-epoch calibration artifact (data/proj_calibration_eval.json, bWAR, measured
on the champion engine, a prior and never a comparator) points the same way: `age:<=24:hit`
-0.198, `age:34+:hit` +0.127.

**(iii) The additive playing-time delta has no ceiling.** `_decay_path()` does
`e += curve_delta(curves, side, role, "pt", a)` then `e = max(0.0, e)`: a floor at zero, no cap.
The PT delta is a pool average (part-timers promoted) added to a regular. On the cached served
fit, a 22-year-old hitter at 3.0 WAR and 650 PA walks 650, 723, 762, 789, 798, 793 PA, reaching
798 PA at 26, beyond any real full season; his WAR path is 3.00, 3.49, 3.71, 3.85, 3.84, 3.68,
mostly playing time. A 24-year-old at the same line walks 650, 678, 686, 682, 669, 649 PA and
3.00, 3.13, 3.12, 2.98, 2.79, 2.53 WAR: one season up on playing time, then down.

**(iv) A5's pre-peak branch is inverted, and a config comment contradicts the config.**
`_aging_factor()` returns `min(1.10, 1.0 + 0.025 * (peak - age_at))` at or before the peak:
above 1.0 and falling toward the peak, against its own docstring ("slight growth before
peak"). A 23-year-old hitter (peak 27) reads 1.10, 1.075, 1.05, 1.025 and 1.00 for offsets 0 to
4, then 0.93: a decline from the first season, priced above his peak level while young. The
comment above `catcher_dev` in value_framework_config.yaml says catchers peak late ("peak age
~29 vs 27"), while `aging_curve.catcher_peak_age` is 25 with the fastest decline (0.09).

**(v) The /projections/ ML path falls with horizon for most young regulars.** On the
2026-10-01 data/mlb_projections.json, among one-plus-WAR veterans aged 23 and under, the ML
`war` at h5 sat below h1 for 14 of 22 (mean h5 minus h1 -0.47 WAR), against 1 of 22 for
`warChamp` (mean +0.40). The 2026-10-07 payload at HEAD reads 17 of 22 (mean -0.33) against 0
of 22 (mean +0.42). This is the absent-season-equals-0 label plus independent heads (A3), an
attrition effect, not an aging curve. docs/PROJ_PATH_SHAPE_GATE.md owns it (ARM A, the
smoothness refit, and ARM B, the bias levers including a side-keyed age slope).

## Three smaller served age terms

- **A6. Glove aging (positional_fit).** `positional_fit.fit_aging()` (line 773) pairs
  same-position seasons; `fit_all()` (line 1386) fits a weighted mean change of the standardized
  glove per year. Served fit (data/positional_fit.json `fit.aging`, 2026-08-12): `n` 2,111,
  `mean_delta_z_per_year` -0.1386 (95% interval -0.2117 to -0.0639), `applied: true`. It is a
  uniform straight line: `estimate_players()` (line 830) adds `age_slope * lag` (a negative
  term) to each older glove read, the same at every age. The measured age interaction (-0.02213 a year, interval
  -0.04586 to -0.00141) is recorded but not applied. Served on /pal/ through
  data/positional_fit_ui.json.
- **A7. Veteran trade-lookup decline (mlb_trade_lookup).** `mlb_trade_lookup._compute_surplus()`
  (line 307) starts from career WAR per WAR season, capped at 6, and subtracts
  `max(0.0, 0.4 * (age - 29))` WAR a season, flat before 29 and additive whatever the level. It
  writes `projected_war_remaining` and `surplus_mm` into prospects.db and the published sidecar
  data/mlb_trade_players.json (`storage.export_timeseries_json`). The Transactions tab Trade
  Audit no longer reads it: since ff0761c0 (2026-09-24) every audit party is priced at
  data/trade_values.json, and test_trade_audit_basis.py pins the sidecar loader's absence. The
  term is computed and published but read by no page.
- **A8. Catcher development bonus (bayes_trade_value).** The `catcher_dev:` block in
  value_framework_config.yaml (`late_peak_bonus 0.08`, `age_threshold 24`) gives catchers aged
  24 and under a factor of (1 + 0.08) on bayes' posterior surplus (the AGE_CURVE catcher bonus step of
  the trade value assembly). It reaches a served price only on a
  `bayes_unrepointed` row; none of the 171 on the 2026-10-07 board is 24 or under. It would
  double-count once a catcher bucket factor (plan task AG_12 (b)) applies.

## Where this is going

Aging v3 (plan Part 9 section 9.3) replaces the fork with ONE aging service, `aging_v3.py`: one
fitted object, many consumers, selected per call (`aging="v2" | "v3"`), with ONE flag per
consumer under `fa_config.yaml aging_v3.consumers`, every flag default off. No consumer moves
until docs/AGING_V3_GATE.md (once registered) records a pass for it, and each flip carries its
own golden test. The existing K%, BB%, ISO, BABIP and HR component curves do not change, so the
betting input stays byte-identical. The ML heads (A3) move only through a later forward read.

One point from the 2026-07-01 page stands: prospects have no MLB history to fit a personal
curve on, so a prospect's path stays a shaped prior over a fixed window total. Under v3 a
prospect gets a position bucket only. Archetypes are declined for prospects (an archetype is
assigned from the three MLB seasons before each change, and a prospect has none), and so is any
health term (its features are MLB injured-list and Tommy John histories; the minor league
injury record is too sparse to fit).

Until then, if any one treatment changes, re-run its own eval (proj_eval.py for the veteran
curves) and make sure the next fit is not read from a stale `.cache/fa_fits_*.pkl` (the key does
not hash code; while the path-shape battery holds its pins, version the key rather than deleting
the files).
