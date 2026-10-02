# $/WAR path gate: pre-registration (2026-09-25)

Target path in the repo: `docs/dpw-2026-09-25/DPW_PATH_GATE.md`. It is committed ALONE, with only
its pin test `test_dpw_path_gate_registration.py`, before any number in it is computed. This text
was revised after three adversarial reviews (economics, statistics, repository) on 2026-09-25; the
resolutions are outside the repo and nothing in them was scored.

**The question.** This gate covers ONE question, asked by the owner on 2026-09-25 ("can we use the
$/war data we already have/have already computed to project $/war for future years, then use these
projections to improve surplus value by using projected $/war for each year in the calculations for
projected surplus value for that year?"). Its forecasting half:

> Does a growth rule for the per-winter $/WAR level, built only from the repository's own
> per-winter series, forecast the level one to five winters ahead more accurately than the rule
> behind the escalator the site serves?

**What this gate does not govern.** The other half of the ask is pricing every season at its own
projected $/WAR and discounting at one fixed nominal rate. That is owner decision L4(c)
(`_audit_2026-09-09/DECISIONS_FOR_OWNER.md:209`), implemented as plumbing behind `SERVE_DPW_PATH`.
This gate does not govern it (section 0a).

**Producers, none of which exist yet:**
- `dpw_path.py`: a pure standard-library module holding the six methods of section 3, the gap rule,
  the taper of section 9, the band of section 11, the ledger helpers and the blindness check of
  section 10;
- the one writer, `fa_market.write_dpw_series` (VAL_1's, already called at the top of
  `run_monthly.rebuild_only` and by the Gate 2 persist in VAL_1's tree), which writes the
  `dpw_path` block of `data/fa_dpw_series.json`, including the truth series of section 1, ONLY
  while a committed block switch is on. The switch is off in the build commit and is turned on
  only by the wiring commit after the step Z entry; until then every caller (the nightly step, the
  Gate 2 persist, a hand run) writes VAL_1's keys only, and a test asserts that no caller writes a
  `dpw_path` key while the switch is off;
- `tools/dpw_path_gate.py`: the one lab. It is built and tested on synthetic series in its own
  commit before the look. It has three modes:
  - synthetic (the default), for its tests;
  - `--prelook`, run once for the pre-look amendment. It computes forecasts, the I-3 and I-5
    records, the stamps and the origin-2026 ledger forecast rows. It WRITES the `dpw_path_gate`
    stub block (verdict `REGISTERED`, the truth sha256, those records, and, when it appends ledger
    rows, the ledger's head sha256 and row count). It asserts that no error of any arm is computed
    and that the oracle search of section 6 is never called, and it refuses if the block already
    exists with any verdict other than `REGISTERED` or with any result key;
  - `--real`, the look. It refuses unless exactly one amendment commit exists (section 14) and the
    `dpw_path_gate` block of `data/dpw_forecast_eval.json` AT THAT COMMIT reads `REGISTERED`. It
    reads the pinned `dpw_path` block and `data/dpw_path_owner.json` from that commit, never from
    the live files.
  The lab is read-only over production modules. It writes only that block and rows of
  `data/dpw_path_ledger.json`. It is the only writer of the block's verdict; the
  `data/fa_dpw_series.json` block carries no verdict.

**Pins and registry.**
- Pinned by `test_dpw_path_gate_registration.py` (criteria) and, from the lab's commit, by
  `test_dpw_path_lab.py` (the lab prints each criterion's text byte-identical to this document).
- Registry: a `dpw_path` row is created by the build commit with verdict `unvalidated` and no eval
  artifact (the enum at `model_registry.py:40` has no "registered"; `validate()` rejects an
  `unvalidated` row that carries an artifact, `model_registry.py:94-95`); the `fa_dpw_series` row's
  notes cite this document. The row's verdict after the look is fixed per outcome in section 15.

**Shape.** Written in the shape of `docs/PROSPECT_ANCHOR_GATE.md`, under the rules of
`docs/diamond-betting.md` 5c. Where a code fact in section 0 and a later reading of the code
disagree, the later reading is recorded in section 0's last column. Line citations outside section
0 locate code as it stood at `64bf1bb3`; where the same code has merely moved to another line by
the registering HEAD (VAL_1's uncommitted `fa_market.py` inserts 109 lines after line 841, for
example), the registering writer records the old and new positions in section 0's last column and
changes nothing in the body. No other part of this document yields to a later measurement.

---

## G-0. Honesty clause, first

**Nothing was scored to write this document.** None of the following has been done, by the
designers or by the reviewers:
- no error of the challenger `A` or of the descriptive arm `B` was computed at any origin, on any
  series;
- no error of the descriptive arm `T` was computed at any horizon above 1;
- no realized-surplus comparison was made;
- no statistic was computed by consensus-FV cell.

**What was seen, and is therefore not blind:**
1. Every winter of the series, in three published copies (G-0.1 item 3).
2. `T` at horizon 1 on origins 2018 to 2025. The `trend` column of `data/dpw_forecast_eval.json`
   is exactly `T`'s one-winter-ahead error: `tools/fit_dpw_forecast.py:23-30` forecasts winter Y
   with `fa_market._fit_log_trend` on the winters before Y. These cells are SPENT (section 7). The
   same tool computes, at horizon 1 only, a fixed 5 percent carry (`flat5`) and `trend_cbt`
   (`tools/fit_dpw_forecast.py:27-30`, `:38`; `:20` is the test-winter list); neither is an arm of this gate.
3. The challenger's growth `g_A` at every origin is a closed-form function of the published first
   log differences and can be read off the published series by inspection. The economics reviewer
   printed those differences on 2026-09-25 while checking the step narrative; no median, forecast or
   error was computed.
4. The challenger was chosen by designers who had read the whole series, because the incumbent's
   slope is driven by one level step. The development frame of section 4.1 is therefore not
   confirmatory, and a pass on it serves nothing by itself (section 9).

**Looking early disqualifies, defined mechanically.** An EARLY LOOK is any computation, on a real
series, before the look of section 14, of a quantity that compares a forecast of `A` (any horizon),
`B` (any horizon) or `T` (horizons 2 to 5) with a realized winter level, or of any summary of such
quantities; or, on a real series before the look, of the oracle growth `g*_o`, of `Q(g*)`, of the
P2 attainability bound, or of any statistic of a planted challenger (section 6). Those are computed
only inside the look, after the integrity gates, because for a constant-growth arm from anchor
`A(o)` the per-origin loss depends on growth alone, so the registered `g*_o` grid evaluates `S_o`
within 0.00025 of `g_A` at every origin and `P2_UNATTAINABLE` says outright whether a pass is
possible; an early power check would let OD-6 or OD-7 be recorded with the result in view. An early
look VOIDS this registration, whatever it measured; the question may then return only as a new
registration that discloses the early read. The following are NOT early looks:
- computing any arm's forecast, or `g_A` or `g_I`, at any origin (a forecast is not an error);
- computing errors of `I`, `F` or `carry_const`;
- running `tools/fit_dpw_forecast.py` with its registered method list (`flat5`, `trend`,
  `trend_cbt`) at horizon 1 only, on any series, real or synthetic, including after its
  build-commit refactor (carry-forward of the `dpw_path_gate` block, and an argument for the series
  and the output path). Horizon 1 is defined mechanically: a target winter is forecast only if the
  winter before it is present in the series the tool is given, and the refactored tool skips every
  other target. (The tool has no horizon parameter: `_forecast`, `tools/fit_dpw_forecast.py:23-30`,
  fits every winter before Y and evaluates at Y, so on a series missing winter Y-1 it would be `T`
  at origin Y-2, horizon 2, and a jackknife replicate of the truth would publish that cell.) Its
  `trend` cells are `T` at horizon 1 and are spent; its `flat5` and `trend_cbt` cells are not arms.
  The method list and the horizon rule are pinned by `test_fit_dpw_forecast_carry_forward.py` on a
  synthetic series with a gap.

Running that tool on a real series after modifying it to compute a horizon above 1, or any method
other than `flat5`, `trend`, `trend_cbt`, `carry_destale`, `carry_zero` and `carry_const`, IS an
early look. (Adding the served carry, whose errors are `I`'s and allowed above, is not one; adding
`robust_drift` or `damped`, or a second horizon for `trend`, and running it on a real series is.)

**Pseudo-real-time, not real time.** Each development forecast is ex ante at the level of the
series: every winter's level is built from WAR projections fitted on seasons before that winter
(the `fitted_models(corpus, year - 1)` call and the `(year - 1, year - 2, year - 3)` history
window of `fa_market.enriched_signings`) and every forecast uses winters at or before its origin. The
projection hyperparameters and model-class choices (the Marcel weights, the playing-time fit mode,
`FA_PRICING_USE_DEF` chosen on Gate 2 across all winters) and the fWAR vintage are full-sample. The
development frame is a pseudo-real-time read on today's vintage.

### G-0.1 The priors read during design, recorded so a run cannot quietly beat them

1. **`data/dpw_forecast_eval.json`** (generated 2026-08-19): forward-chained one-winter-ahead MAPE
   over 9 winters (2018-2026).

   | Method | MAPE |
   |---|---|
   | flat carry at a FIXED 5 percent | 0.1043 |
   | trend (= `T` at horizon 1) | 0.1046 |
   | trend_cbt | 0.1313 |

   The older 2026-06-11 figures at `fa_config.yaml:29-36` are 0.102, 0.122 and 0.132. The served
   carry (`_destale_rate`) has never been scored.
2. **Commit `a7383712`** (2026-06-10): the fitted forecasts lost to the flat carry one winter ahead.
3. **The three published copies of the series**, arithmetic: `data/fa_dpw_series.json`
   `usd_per_war_by_winter`, `data/fa_class.json` `dpw_series_pricing` and
   `data/dpw_forecast_eval.json` `actual_usd` disagree on one winter by up to 0.0801 in log (2015);
   the median across the 12 winters of the max/min log spread is 0.0244.
4. **The step identity**, arithmetic: on 12 equally spaced winters a single level step after the
   6th moves the OLS log slope by 0.12587 per unit of step; the 2020-to-2021 step alone (committed
   series 0.2980 log) implies an escalator of 0.0382, against the full-series 0.0392.
5. **Endpoint growth of the in-run series**, 2015 to 2026, arithmetic: 0.0316 a year against its
   OLS 0.0416. This is the MEAN of the first log differences; the challenger uses their MEDIAN.
6. **The paired published horizon-1 errors**, arithmetic: trend minus fixed 5 percent has sd 0.0537
   over 9 winters, SE 0.0179 and one-sided MDE95 0.0294. This is a NON-TRANSFERABLE HEURISTIC: a
   different contrast (one horizon, trend against a fixed 5 percent, a structural zero at 2018),
   not this gate's statistic. The label of section 7 is decided only by the power block.
7. **Descriptive growth of other nominal indexes** (published by the design's data reader): QO
   0.030, tax payroll 0.037, CBT 0.028, arbitration index 0.022, league minimum 0.054.
8. **Class 2021 discounted projected WAR per deal** is 0.69, against 1.53-1.56 in 2019-2020, and the
   code reading of section 0 F15: no 2020 proration in the FA playing-time inputs.
9. **Owner decisions and census items:** decisions 26 ("Align on 0.0407",
   `DECISIONS_FOR_OWNER.md:162`), L4(c) (`:209`) and FP2-1 (`:375`); census X02-03, X02-06, X02-13
   and X02-17.
10. **The three reviews of 2026-09-25**, including item 3's display of the first log differences.

This gate is therefore a development read against a published tie at horizon 1, on a frame whose
winters are spent and whose challenger's errors are unseen, followed by a blind prospective check.

---

## 0. What is being decided, measured first

Every row was read at HEAD `9a53d29f` on 2026-09-25 and re-checked at `64bf1bb3` the same day; no
file cited in this table changed between the two. **The registering writer re-verifies each row
at its own HEAD before committing and fills the last column; a changed line is recorded there, not
silently corrected above.**

| # | Fact | Where | At the registering HEAD |
|---|---|---|---|
| F1 | The per-winter level is the sum of sticker-or-deferral-NPV guarantees over the sum of WAR discounted at `discount_rate`; a winter is kept only if n >= 25 and discounted WAR > 20 | `fa_market.py:566-587`; `disc_war` `:521-526` || Holds at `204a785d`. Position only: `dollars_per_war_by_winter` is `fa_market.py:601-622` (numerator `:618`, filter `:621-622`); `disc_war` is `:556-561` |
| F2 | The served carry is the last prior winter carried at `_destale_rate`: OLS log slope over >= 4 winters, `exp(b)-1` clipped to [0, 0.12]; with fewer than 4 winters it returns `_dpw_inflation()`, which is 0.0 under clemens_2026 and 0.05 under prospx_current | `fa_market.py:800-839`, `:249-281`, `:245-246` || Holds at `204a785d`. Position only: `winter_dpw` `fa_market.py:835-874`; `_destale_rate` `:249-281` (clip `:280`, fallback `:281`); `_dpw_inflation` `:245-246`. VAL_1 (`410cccce`) also carries this rule into the written `pricing.carry_rate` (`:924`) |
| F3 | The published eval scores a FIXED 5 percent carry and `_fit_log_trend(prior, with_cbt)` one winter ahead over test winters 2018-2026, and rewrites its artifact wholesale; the artifact's top-level `generated_at` is 2026-08-19 | `tools/fit_dpw_forecast.py:20`, `:23-30`, `:33-69` || Holds at `204a785d`, same lines (`:20`, `:23-30`, `:33-72`, the write at `:68-69`); top-level `generated_at` still 2026-08-19 |
| F4 | /fa/ escalates rational value at `destale` while discounting at the 0.07 net rate | `fa_export.py:622`, `:629`, `:756-770`; `fa_market.py:846-869` || Holds at `204a785d`. Position only: destale `fa_export.py:702`, level `:694-695`, rational value at `destale` `:829-843` and `:886-887`; `rational_value_usd` `fa_market.py:990-1013`. Since VAL_1 the level is the written `pricing.level_usd` (`:694`) and the destale rate is taken on the written series (`:654`, `:702`); the in-run series is kept as a check (`:653`, `:655-667`) |
| F5 | Veterans price at `winter_dpw` of the committed series, escalated at `dollars_per_war_inflation` (0.0 under clemens, code default 0.05); first projected season 2027, horizon 5 | `proj_export.py:530-535`, `:556-564`, `:67-68` || Holds at `204a785d`. Position only: `_season_value_usd` `proj_export.py:624-629` (0.05 default `:628`), `_winter_dpw` `:650-657` (now `fm.written_pricing_level_usd`, VAL_1's `pricing.level_usd`, the same carry), `FIRST_SEASON`/`HORIZON` `:73-74`. Disclosure: VAL_2 (`fff020a1`) prices a guaranteed season past 2031 on the champion's aging curve, so contracted veteran strips can run past the 5-season horizon; no formula, arm, frame or criterion of this document reads it |
| F6 | Prospects apply one net factor `((1+infl)/(1+r))^(eta+t)`; the league minimum is one constant 0.76M | `value_framework.py:1154-1176` (`:1174`), `:1216`; `value_framework_config.yaml:301` || Holds at `204a785d`. Position only: `value_framework.py:1225-1247` (net `:1245-1246`), league minimum `:1287`; `value_framework_config.yaml:301` unchanged |
| F7 | The league minimum and the arbitration deflator carry their last tabled year flat | `salary_path.py:247-259`, `:301` || Holds at `204a785d`. Position only: `league_min_usd` `salary_path.py:249-261`; the deflator carry `:303` |
| F8 | Gate 2 builds its own train-only series in-run; its baseline inflates at `dollars_per_war_inflation`; `persist_dpw` defaults True and rewrites the committed series | `fa_backtest.py:559-560`, `:553`, `:587-589`, `:524`, `:724-738` || Holds at `204a785d`: `fa_backtest.py:559-560`, `:553`, `:587-589`, `:524` (`persist_dpw: bool = True`) unchanged; the persist at `:724-732` now calls VAL_1's one writer `fm.write_dpw_series(_CLASS_YEAR)` instead of writing its own copy (VAL_1, `410cccce`) |
| F9 | The Ledger reads one `rate` from `fa_market._discount_rate()` and uses it for the strip NPV, the deferral labels, the surplus-basis copy and the served `accountability.discount_rate` | `ledger_export.py:596-606`, `:819`, `:1430`, `:1656-1660`, `:1679`, `:2093` || Holds at `204a785d`. Position only: `rate` read at `ledger_export.py:1201`; strip NPV `npv_of_strip` `:919-928`, used at `:1899`; deferral NPV `:1400` (through `deferral_npv_usd`, which reads `_discount_rate()` itself); deferral labels `:2148-2152`; surplus-basis copy `:2177`; `accountability.discount_rate` `:2740` |
| F10 | The calibration tool prices every realized season 2014-2034 at today's flat rate, calls `run_backtest`, and labels its output "v3" | `tools/fit_surplus_calibration.py:62-63`, `:66-67`, `:82` || Holds at `204a785d`, same lines (`:62-63`, `:66-67`, `:82`); VAL_1 added `fit_dpw_flat_usd` at `:86` |
| F11 | `run_backtest` always computes `by_fv_tier` and a sensitivity table | `backtest.py:682-684` || Holds at `204a785d`, same lines (`by_fv_tier` `:682`, `sensitivity` `:684`) |
| F12 | The `regimes` config (covid 2021, lockout 2022) is read by no $/WAR code | `fa_config.yaml:38-42` || Holds at `204a785d`. Position only: `fa_config.yaml:39-43`. The one regime notion in $/WAR-adjacent code is the Gate 2 market model's default-off `X_FEATURES["regime"]` arm (`fa_market.py:1625-1630`), which hardcodes 2021 and 2022 dummies and does not read the config |
| F13 | Deal+ verdict edges are terciles to be regenerated "whenever the pricing basis moves" | `fa_market.py:1998` || Holds at `204a785d`. Position only: `fa_market.py:2141-2142` |
| F14 | The registry verdict enum is `validated / provisional / unvalidated / deprecated` | `model_registry.py:40` || Holds at `204a785d`, same line (`model_registry.py:40`) |
| F15 | The FA playing-time formula reads raw prior-season exposures (hitters `e1`, `e2`, `e3`; pitchers `ip1`, `ip2`, `ip3`); `fa_projection.py` contains no 2020 scaling (its "2020" mentions are evaluation comments at `:378`, `:1039`, `:1202`); the tree's only 2020 proration is arbitration's | `fa_projection.py:1645-1646`, `:1649-1657` (the bounce term and `e3`), `:1664-1668`; `arb_dataset.py:430` || Holds at `204a785d`, same lines (`fa_projection.py:1645-1646`, `:1649-1657`, `:1664-1668`; the 2020 mentions at `:378`, `:1039`, `:1202`); `arb_dataset.py:430` unchanged |
| F16 | The nightly FA export builds classes 2028 and 2029 through `enriched_signings(2015, class_year - 1)`, so later winters enter an in-run series as soon as they pass the thin-winter filter; on 2026-09-25 every served `dpw_series_pricing` ends at 2026 | `fa_export.py:594`, `:1451`, `:1541`; `data/fa_class*.json` || Holds at `204a785d`. Position only: `enriched_signings(2015, class_year - 1)` `fa_export.py:646` and `:1138`; the future classes `:1525`, `:1615`. Since VAL_1 the class boards price on the written series through `class_year - 1` (`:654`), and the writer enriches through the class winter, so a later winter reaches `dpw_series_pricing` (`:1067`) through the written file; on `204a785d` every served `dpw_series_pricing` still ends at 2026 |
| F17 | The registry flags a stamped eval artifact older than 90 days, and `test_stale_threshold_is_reachable` fails when any stamped artifact is older than `STALE_DAYS` | `model_registry.py:63`, `:362-368`; `test_model_registry.py:171-202` || Holds at `204a785d`. Position only: `model_registry.py:63`, `:370-379` (`stale` at `:377`); `test_model_registry.py:224-255` |
| F18 | Valuation-set discount forms: `net_flat`/`net_7_flat` set `discount_rate` to a net rate and `dollars_per_war_inflation` to 0; `rate_minus_growth` sets a nominal rate and a growth (prospx_current: 0.09 and 0.05); the production default is clemens_2026, whose literal form string is `net_7_flat` and whose net 7 percent is "a 10% discount rate minus 3% annual win-cost growth" | `valuation_sets.py:58`, `:289-296`; `config/valuation_sets/prospx_current.yaml:136-138`; `config/valuation_sets/clemens_2026.yaml:94-99` || Holds at `204a785d`. Position only: `DEFAULT_SET` `valuation_sets.py:57`, the form branch `:297-305`; `prospx_current.yaml:140-143`; `clemens_2026.yaml:101-106` (the comment `:101-103`, `form: net_7_flat` `:106`) |
| F19 | The level's numerator takes `npv_guarantee_usd` where a deferral schedule is attached, else the sticker; `deferral_npv_usd` discounts EVERY scheduled flow from year offset 0 at `discount_rate`, while its docstring says the adjustment should capture only the deferral-versus-level difference; all 6 `deferred: true` entries of `data/deferrals.json` carry flows | `fa_market.py:583`, `:942-956`; `data/deferrals.json` || Holds at `204a785d`. Position only: `fa_market.py:618` (also `:735` in `dpw_breakdowns`), `deferral_npv_usd` `:1086-1102` (the docstring convention `:1091-1096`); 26 entries, all 6 `deferred: true` carry flows |
| F20 | The FA projection reads seven switches from the environment at call time: `EEPHUS_PT_RISK`, `EEPHUS_PIT_IP_AGE`, `EEPHUS_PT_TJ`, `EEPHUS_FA_REALWAR`, `EEPHUS_FA_DEF`, `EEPHUS_FA_PTFIT` (default `hit`) and `EEPHUS_FA_MARCEL` | `fa_projection.py:974`, `:1052`, `:1143`, `:1261`, `:1352`, `:1479`, `:1503` || Holds at `204a785d`, same lines |

### 0a. What this gate does NOT do, so the absence is a decision

- **It does not govern the unified plumbing**: one written path, one stored nominal rate, one base
  season, the companion salary legs, the served level basis and the removal of the /fa/ double
  count. These implement owner-locked conventions and ship by owner flip after the fWAR epoch's
  step Z, with invariants and a blast radius, whatever this gate reads.
- **No owner answer enters this document's truth, frames, statistic or pass rule.** The served level
  basis (OD-1), the nominal rate (OD-2), the base season (OD-3), the companion legs (OD-4), the
  Trade Machine convention (OD-5) and the calibration route (OD-8) are recorded beside the series
  and never read by this gate. What a development pass serves (OD-6, section 9) and how the
  escalator may change (OD-7, section 12) are named here with their admissible answers fixed now.
- **Owner answers are recorded in the repository** in `data/dpw_path_owner.json` (date, question id,
  question text, verbatim answer, option code, and the `DECISIONS_FOR_OWNER.md` line it was copied
  from). The file is append-only and hash-chained like the ledger of section 10, and it is excluded
  from the public webroot (`deploy/data_exclude.txt`); where an id has several rows, the last row
  for that id in chain order binds. The two answers this gate reads (OD-6 for section 9, OD-7 for
  section 12) are read only as they stood in the amendment commit, copied into the `dpw_path_gate`
  block by the lab (section 15) as option codes, dates and row hashes, never as text, because
  `data/dpw_forecast_eval.json` ships publicly. The one exception is OD-7 option (c), which exists
  only after the look and is read from the block's `owner_after_look` (section 12).
- **It makes no surplus-accuracy claim** and reads no calibration.
- **The lab and this gate's verdict make no statistic by consensus-FV cell, never call
  `backtest.run_backtest` and never import `surplus_backtest_real`** (section 8). The ONE
  sanctioned importer of `surplus_backtest_real` under this registration is the calibration refit
  of the plumbing flip commit, or of a serving commit, through `backtest.fit_calibration_knots`,
  which builds its records with `surplus_backtest_real.build_cohorts` (as
  `tools/fit_surplus_calibration.py:35`, `:50`, `:66` does today), fits the knots and computes no
  statistic of any kind. It is not part of this gate's read, and it never calls
  `backtest.run_backtest`.
- **It makes no Gate 2 claim.** The market model's inputs are untouched by construction.
- **It makes no claim about seasons after 2031.**

---

## 1. The estimand and the truth

**The truth series `A(W)`.** For winter W (class year W, the offseason ending before season W):

`A(W) = sum_i G_i / sum_i disc_war_r(i)`

over winter W's enriched MLB deals, where `disc_war_r` discounts the champion WAR path at
`discount_rate` (0.07 under clemens_2026; `fa_market.py:521-526`), the enrichment applies
correction P20 (section 1.1), the deal filter and the thin-winter rule are those of
`fa_market.py:566-587`, and `G_i` is the deal's LEVEL-EQUIVALENT STICKER:

- for a deal with no schedule in the deferral ledger, `G_i` is the sticker guarantee;
- for a deal with a schedule (flows `{year_offset, amount_usd}`), `G_i = sticker_i x
  PV_r(schedule_i) / PV_r(level_i)`, where `level_i` pays `sticker_i / years_i` at year offsets
  0 to `years_i - 1` and `PV_r` discounts at `discount_rate` from offset 0. `G_i` is the sticker of
  the level deal with the same present value.

This departs from the code's estimator for scheduled deals only (F19): the code enters them at the
present value of every flow, which puts them on a different basis from level deals (Ohtani 2024
enters at $274.8M against a level-equivalent sticker of $365.7M; Scherzer 2015 at $140.4M against
$170.4M; closed-form arithmetic on the publicly reported schedules, no series statistic). Six of
the twelve winters hold a scheduled deal, including 2024 and 2025, which anchor the late origins.
Level deals are unchanged. The one
writer stores the truth as `dpw_path.truth.by_winter` with estimator id
`sticker_leveleq_r_over_disc_war_r_p20_v1`. Under OD-1's round-trip option the served level is a
separate object (it discounts all cash at R) and is unaffected; under OD-1's sticker option the
served level IS this series (the same estimator id and the same `G_i`), so no served winter enters
a scheduled deal on a basis different from level deals.

- **Growth-free.** No growth parameter, no nominal rate R and no owner answer enters `A`. The served
  level basis and the served nominal rate are recorded in the same file and never read here. A
  round-trip level would discount cash at R, which is set from an escalator estimated on winters
  through 2026, so every early origin would carry look-ahead; and two truth series in view would let
  a basis be chosen after seeing both.
- **Growth is what is scored and what is served.** Every method's growth is computed on `A`. The
  growth rule scored is the growth rule served; it is applied to the served level (section 9). The
  truth and the served level grow alike only under a stable term mix, because the ratio of sticker
  to round-trip level runs from 1.054 to 1.549 by term (section 5.1 reports the term-mix index; the
  amendment records `g_I(N)` on both bases).
- **Convention.** Season s is priced at the level of winter s (as `fa_class.py:244-256` already
  does). A winter's level mixes seasons W to W+N-1 of each deal; that is stated, not solved.

### 1.1 Correction P20, fixed now

Section 0 F15 shows that the class-2021, 2022 and 2023 enrichments project playing time from the
60-game 2020 season without proration. The one admissible correction for this gate's truth, fixed
before any read:

- In `fa_projection.project_player`'s playing-time formula ONLY, every exposure read from season
  2020 (the hitter terms `e1`, `e2`, `e3` and the pitcher terms `ip1`, `ip2`, `ip3`, including their
  use inside the bounce term) is multiplied by 162/60.
- Rate inputs and their exposure weights, the aging curves, the WAR map and every other season are
  unchanged.
- It is a flag, off by default everywhere. Only the dpw_path writer's enrichment sets it, so Gate 1,
  Gate 2, the in-run /fa/ series and every served projection are untouched.
- It moves the class 2021, 2022 and 2023 winters only (their Y-1 to Y-3 windows contain 2020).
- No other form of 2020 handling may be adopted for this gate's truth.

### 1.2 Error, weights and loss

- **Anchor-scaled error:** `u_{o,h}(P) = (P_o(o+h) - A(o+h)) / A(o)`. The scale `A(o)` is known at
  the origin, so the squared loss below is minimised by the conditional mean of the future level.
  Served surplus is an expected value (owner decision v6 evframe), and a median-type loss would
  reward a path that discards genuine jumps.
- **Weights:** `w_{o,h} = 1.113763^-h / sum_{k=1..H_o} 1.113763^-k`. The rationale: `u` is a
  dollar error in origin-level units (it already carries the level's growth, because the error is
  scaled by `A(o)`, not by `A(o+h)`), and `1.113763^-h` is the present value at the design-default
  nominal rate R of a dollar in season o+h. The base 1.113763 is fixed now, whatever OD-2 answers.
  With all five horizons the weights are 0.2452, 0.2202, 0.1977, 0.1775 and 0.1594. (Weighting by
  `1.07^-h` would count growth twice: on the relative error `P/A - 1` it would put flat to slightly
  rising weight on the later horizons.)
- **Per-origin loss:** `S_o(P) = sum_{h <= H_o} w_{o,h} u_{o,h}(P)^2`.

---

## 2. Integrity gates. Nothing is read if these fail.

Each gate is recorded in the artifact with its evidence. A failure found at the look makes the look
**VOID**. A precondition unmet on the look date makes it **NOT_AVAILABLE**, and the look slips.

- **I-1, post-epoch.**
  - `docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` part 9 carries the entry for step Z. A
    precondition disclosure is not that entry.
  - The pinned block's `enrichment.war_provider` is `fwar`.
- **I-2, one pinned block.**
  - VAL_1's one written series and its writer are committed, and the one writer wrote the block.
  - The pinned object is `dpw_path.truth` with its estimator stamps. The pre-look amendment records
    the sha256 of its canonical JSON (sorted keys, no whitespace).
  - Two writes by the one writer, on different calendar days, on the machine that makes the
    amendment commit, give the same sha. The second is a FORCED recompute that bypasses the
    writer's basis-key skip. Both shas are recorded. (The box's nightly does not count: it runs
    on its own database and its tracked files are reset each night.)
  - The amendment commit includes `data/fa_dpw_series.json` as written by the second write.
  - The lab reads the pinned block from the amendment commit (`git show <commit>:<path>`), never
    from the live file, and checks that the sha256 of the committed `dpw_path.truth` equals the
    recorded sha.
- **I-3, P20 applied.** The block's `enrichment.p20` is `true`; the build's synthetic P20 test
  passes; the amendment records the class-2021, 2022 and 2023 discounted WAR per deal on the pinned
  block (properties of the series, not errors).
- **I-4, growth-free basis.** The truth's estimator id (`sticker_leveleq_r_over_disc_war_r_p20_v1`)
  and its numerator and denominator rates are stamped (both `discount_rate`; no R, no growth). The
  amendment records, per winter, the count of scheduled deals and their share of the winter's
  numerator (properties of the series, not errors). The served R, `g_ref` and owner answers are
  recorded beside it and not read.
- **I-5, parity and point-in-time.** On synthetic series (the build's tests) AND on the pinned
  block, forecasts only:
  - `carry_destale` equals `fa_market._destale_rate`'s carry at every development origin, to 1e-12
    relative. Every development origin has at least 4 winters, so F2's per-set fallback is never
    reached;
  - `trend_line` equals `fa_market._fit_log_trend(with_cbt=False)`, to 1e-12 relative;
  - the writer's stamps show every class's enrichment used `fitted_models(corpus, class_year - 1)`
    and `use_ml` False;
  - the writer's `enrichment.projection_switches` stamp records, for each of the seven switches of
    F20, the raw environment value at write time (`null` when unset) and the value the projection
    resolved. I-5 passes when every raw value is `null` or equals the resolved default (no override
    was set when the block was written). `--prelook` evaluates it on the pinned block and records
    the result beside each switch's default as it stands in the amendment commit's code
    (`git show <amendment>:fa_projection.py`); a later change of a code default (a gate flip in
    another lane) is a disclosure in the block, never a failure.
- **I-6, no writes.**
  - The md5 of `data/fa_dpw_series.json` is recorded at the start and end of the lab run and is
    unchanged. The look never overlaps a rebuild or any exporter run.
  - The lab imports neither `backtest` nor `surplus_backtest_real` and never calls
    `run_market_gate`.
  - The lab writes nothing but its block and ledger rows.
- **I-7, the tested code.** The `--real` run records the git blob shas of `tools/dpw_path_gate.py`
  AND of `dpw_path.py` (which holds the arms, the gap rule, the taper, the blindness check and the
  ledger helpers). Each equals the blob committed with the lab's synthetic tests, or that of a later
  commit whose message states it changed no criterion text, formula, seed, frame or order. The
  synthetic tests of both files passed at those blobs, recorded.
- **I-8, clock.** The look date satisfies section 14.

---

## 3. The candidates. The list is closed at this commit.

Each method sees the winters of `A` at or before origin o and returns `P_o(o+h)`.

| id | `P_o(o+h)` | role |
|---|---|---|
| `carry_destale` | `A(o) (1 + g_I(o))^h`, `g_I(o) = fa_market._destale_rate({W: A(W), W <= o}, o + 1)` | **incumbent `I`**: the served rule, applied ex ante |
| `carry_zero` | `A(o)` | **floor `F`**: zero information; anything that serves must beat it |
| `robust_drift` | `A(o) (1 + g_A(o))^h`, `g_A(o) = min(0.12, max(0, exp(median of d over winters <= o) - 1))` | **the one challenger `A`** |
| `trend_line` | `exp(a_o + b_o (o+h))`, the OLS of ln A on year over winters <= o | **descriptive `T`**, no pass role; horizon 1 SPENT (G-0) |
| `damped` | growth in step h is `g_I(o) + (g_A(o) - g_I(o)) x 0.8^(h-1)`, compounded | **descriptive `B`**, no pass role; the only non-constant growth shape |
| `carry_const` | `A(o) (1 + g_ref)^h`, with the `g_ref` recorded when the forecast is made | **prospective comparator only.** Never scored on the development frame, because 0.0409 was estimated on winters through 2026 |

- **Differences and the gap rule.** `d` runs over consecutive AVAILABLE winters `W' < W`:
  `d = ln(A(W)/A(W')) / (W - W')`. A gap of k winters (a winter dropped as thin, or deleted by the
  jackknife of section 5) enters once, annualized. The same rule applies to every method that uses
  differences.
- **Median.** The median of an odd count is the middle value; of an even count, the mean of the
  two middle values (Python's `statistics.median`). Origins 2019, 2021, 2023 and 2025 have an even
  count of differences, and a jackknife deletion can change the parity.
- **Clip.** The [0, 0.12] clip on `g_A` matches `fa_market.py:280`, for parity.
- **Minimum data.** Every method needs at least 4 winters (3 differences). Fewer falls back to
  `carry_zero`.
- **Seasons after the fifth.** No method is scored beyond h = 5. How a served path continues is
  section 9's taper, which is an assumption.
- **Excluded:** `trend_cbt` (its covariate is carried forward flat at an "explicitly-unknown" value
  after 2026, `fa_cba.py:89-96`); any QO, payroll, CBT, CPI, arbitration-index or regime-dated
  covariate; any method with more than two parameters.
- **Frozen.** No arm may be added, tuned or re-parameterised after this commit. The 0.8, the clip,
  the 4-winter minimum, the median and the gap rule are fixed here.

---

## 4. Frames, and how they stay disjoint

### 4.1 DEV, the development frame (spent winters)

- **Origins.** o in {2018, ..., 2025}, 8 origins. 2018 is the first origin with 4 winters.
- **Horizons.** h in {1, ..., H_o}, `H_o = min(5, 2026 - o)`: 5, 5, 5, 5, 4, 3, 2, 1, for **30
  (origin, horizon) pairs**. No target later than 2026 is in DEV.
- **Sub-periods.** S1 = origins 2018-2020 (windows cross the 2020-to-2021 step); S2 = origins
  2021-2025.
- **REGIME targets.** 2021 (covid) and 2022 (lockout), from `fa_config.yaml:38-42`. The labels were
  written after the fact, so they partition the frame and never enter a forecast. REGIME pairs stay
  IN the primary statistic and are also reported separately (P6).

### 4.2 PROSPECTIVE, the blind frame (section 10)

An append-only forecast ledger, `data/dpw_path_ledger.json`, whose rows are blind by the mechanical
test of section 10. Its first blind origin is 2026 if that test passes when the origin-2026 rows
are committed, otherwise the first later origin that passes.

### 4.3 The prospective REGIME rule, fixed now

A prospective target winter W is REGIME if any of these holds, judged from `data/cba_rules.json` as
encoded when W is scored:
- (a) a work stoppage (lockout or strike) is in effect on any day from the day after the previous
  World Series to opening day of season W;
- (b) the agreement governing W's signing period differs in structure from the 2022 agreement: a
  salary cap or floor, a change to free-agency or arbitration eligibility, or a luxury tax that is
  replaced or restructured beyond its threshold and rate values;
- (c) W's base CBT threshold differs by more than 10 percent from season W-1's as encoded (for
  W = 2027, from the carried $244M);
- (d) the estimator drops W as thin (`fa_market.py:587`).

If the agreement governing W is not encoded when W is pinned, W is not scored until it is.

A REGIME target can veto and can never confirm (section 10).

### 4.4 Separation from every other frame

- **VAL_3's frame.** This gate never reads `surplus_backtest_real` or its resolved 2017-2019
  cohort, VAL_3's registered frame (`docs/efv-2026-09-25/SURPLUS_ODDS_GATE.md`, queued).
- **The fWAR epoch.** Only the post-epoch series is read. The epoch's clause (f) and part 9 never
  record an effect of this lever, because nothing served lands between steps A and Z.
- **Other gates.** No projection frame of `docs/PROJ_PATH_SHAPE_GATE.md`, no anchor frame of
  `docs/PROSPECT_ANCHOR_GATE.md`, no frame of `docs/eta-2026-09-25/ETA_FG_BLEND_GATE.md`, no betting
  column.

---

## 5. The statistic, its uncertainty, and the margin

- **Primary statistic.** `D_o(P, Q) = S_o(P) - S_o(Q)`; `Dbar(A, I)` = the mean of `D_o(A, I)`
  over the 8 origins. Negative favours A.
- **RMS scale.** `Q(P) = sqrt(mean over the 8 origins of S_o(P))`, the PV-weighted root mean squared
  anchor-scaled error, used for the margin.
- **Bias.** `b_o(P) = sum_h w_{o,h} u_{o,h}(P)`, and `bbar(P)` = its mean over origins (level
  terms).
- **Secondary, reported with no pass role:** per-horizon `MSE_h` (mean `u^2`) and `BIAS_h` (mean
  `u`) over the origins available at h; the absolute-log loss `L_o(P) = sum_h w_{o,h} |ln P_o(o+h) -
  ln A(o+h)|` and its contrast; `|b_o|`; each origin's influence on `Dbar` (Dbar with that origin
  removed); errors against the term-mix index of section 5.1.
- **Sub-frame contrasts.** S1 and S2 are the means of `D_o` over their origins. The non-REGIME
  contrast drops pairs with a REGIME target, renormalises each origin's weights over its remaining
  horizons, drops origins with none left, and averages.
- **Ties.** An origin with `|D_o| < 1e-12` is TIED. Ties arise where both arms' growth clips to the
  same value.
- **SE_jack (primary): delete winter y EVERYWHERE**, for each y in 2015 to 2026 (12 replicates):
  y is removed from every origin's input series (by the gap rule), from the origins and from the
  targets, and every forecast is recomputed. In a replicate, each surviving origin's weights
  renormalise over its remaining horizons, with h keeping its original value (as in the non-REGIME
  contrast). An origin left with fewer than 4 winters, or with no target, drops from that
  replicate. `SE_jack = sqrt((n-1)/n x sum_y (Dbar_(-y) - mean)^2)`, n = 12.
- **SE_boot.** Resample the 8 origins with replacement, each with its whole horizon vector.
  B = 2000, seed 20260925. It is expected to be anticonservative.
- **`SE* = max(SE_jack, SE_boot)`.**
- **Critical value.** `c = t_{0.95, 7} = 1.894579` (8 origins minus one), unless the size run of
  section 6 raises it.
- **Exact sign-flip test.** All 2^8 = 256 sign patterns applied to the vector `(D_o)`; the one-sided
  p is the share of patterns whose mean is at or below the observed `Dbar`. A tied origin
  contributes zero to every pattern, so with k ties the smallest attainable p is `2^k / 256`. It is
  approximate, because overlapping origins are not independent, and it is never used alone.
- **Margin M = 0.025 on the RMS scale**, fixed now. It is the planted power alternative (section 6)
  and the practical threshold (P2). Its size is the median cross-vintage restatement of one winter
  (0.0244, G-0.1 item 3): a forecast gain smaller than the amount by which the truth itself restates
  between vintages would not survive the next restatement. It is not a noise floor for the paired
  contrast, because both arms are scored against the same pinned truth.
- **Multiplicity.** One challenger and one look; there is no family.

### 5.1 The term-mix index (descriptive, no pass role)

For each winter: the level within each term bucket (1 year, 2 to 3 years, 4 or more years), as
`sum G / sum disc_war_r` over the same deals and the same `G_i` as `A`; the index is the weighted
mean of the bucket levels with weights frozen here at the committed file's pooled discounted-WAR
shares: 484.74, 611.99 and 829.46 (the last is the 4-6 and 7+ buckets together) of 1926.19 in
`data/fa_dpw_series.json` `breakdown.pooled.len` (written 2026-08-04), that is 0.2517, 0.3177 and
0.4306, which sum to 1. A bucket with no deal in a winter drops and the remaining weights
renormalise to sum to 1, disclosed per winter. At the look, after the verdict, the
lab reports each arm's errors against it and the served rule's growth computed on it through 2026.

---

## 6. Power and size, published before any cell of A, T or B

**Order.** The lab writes the `power` block BEFORE computing any error of `A`, `T` or `B`, and the
lab's test asserts the order. The block uses the truth, `I` and `F` only. Inside the block the
order is fixed too: first the size run of item 2(a) at each `rho` (it needs the truth and `I`
only), which fixes `c` for the rest of the block and for the verdict; then item 1 and its flag,
evaluated with the `c` the size run left; then the detection run of item 2(b); then items 3 and 5.
Nothing in the block, and nothing in items 2 and 5 in particular, is computed on a real series
before the look (G-0).

1. **Errors of `I` and `F`** on all 30 pairs; `Dbar(I, F)`, `SE*(I, F)`; `MSE_h` and `BIAS_h` of
   both; the flag `INCUMBENT_BELOW_FLOOR` (below), computed once, with the `c` the size run left
   (raised or 1.894579), never at both values.
2. **The planted challenger, in growth space.** For draw j (seed `20260925 + j`) and each origin:

   `g_C(o) = min(0.12, max(0, g_I(o) + kappa x (g*_o - g_I(o)) + sigma_g x z_o))`,
   `P_C(o, h) = A(o) (1 + g_C(o))^h`

   - `g*_o` is the constant growth minimising `S_o` from anchor `A(o)` over [-0.20, 0.30]: a grid
     scan at step 0.0005, then golden-section search inside the two grid cells around the best
     grid point, to a tolerance of 1e-10. It is used unclipped inside the pull;
   - `z_o` is persistent across origins: `z_2018 = e_2018`, `z_o = rho z_(o-1) + sqrt(1 - rho^2)
     e_o`, with `e_o ~ N(0, 1)` drawn once per origin per draw. Every run below is made twice, at
     `rho = 0` and at `rho = 0.8`;
   - `sigma_g = max(sd across the 8 origins of ln(1 + g_I(o)), 0.01)`;
   - common random numbers: draw j uses seed `20260925 + j` for every `kappa`, `sigma` and `rho`
     evaluated;
   - inside a draw, `SE*` uses the same jackknife and a bootstrap of B = 500 (declared), and the
     sign-flip test runs as registered; under a jackknife deletion, `g_I(o)` and `g*_o` are
     recomputed on the reduced series and `z_o` is kept.

   **(a) Size run, first, at each `rho`.** Let `f(kappa, sigma)` be the mean over 1000 draws of
   `Dbar(C, I)`, and let the tolerance `tol` be 0.05 times the median `SE*(C, I)` across the same
   draws. The plant is found as follows, and the steps are recorded:
   1. If `f(0, sigma_g)` and `f(1, sigma_g)` bracket 0 (opposite signs, or either within `tol`),
      bisect `kappa` in [0, 1].
   2. Otherwise, if `f(0, sigma_g) < 0` (the clip at 0 makes the noise one-sided and the noise
      alone beats `I`), bisect `kappa` in [-3, 0] if `f(-3, sigma_g) >= 0`. A negative `kappa`
      pulls away from the oracle.
   3. Otherwise (`f > 0` at both 0 and 1: the noise outweighs the oracle's gain), halve `sigma` from
      `sigma_g`, at most 6 times. At EACH halved `sigma`, re-run steps 1 and 2 (the [0, 1]
      bracket first, then the [-3, 0] bracket) before halving again, and bisect at the first
      `sigma` where either brackets a root. Where `g_I` clips at 0 the one-sided noise gain shrinks
      with `sigma` while the noise cost shrinks with `sigma^2`, so halving can push `f(0, sigma)`
      below zero: the root then sits in [-3, 0], and step 2 finds it instead of the run reading
      UNAVAILABLE. The halvings may go below the 0.01 floor and are recorded.
   4. Bisection stops after 30 steps or when `|f| <= tol`. If the final `|f| > tol`, or no
      bracket was found, the size run at that `rho` is UNAVAILABLE.

   The size run is never made at a plant whose `|f|` exceeds `tol`. At each `rho` where it is
   available, `size_full` = the share of the size draws passing P1 to P8 at `c = 1.894579`. If
   `size_full > 0.05` at any available `rho`, `c` is raised to the larger of the available 95th
   percentiles of `-Dbar / SE*` across the size draws, and that `c` holds for the rest of the
   block and for the verdict. `size_status` is one of `FULL` (available at both `rho`), `PARTIAL`
   (available at one `rho` only; the block names the unavailable `rho`, `c` is raised on the
   available run's `size_full` by the same rule, and the section 17 sentence adds that false
   passes were size-controlled only at the available `rho`) and `UNAVAILABLE` (available at
   neither; `c` stays 1.894579 and the section 17 sentence adds that false passes were not
   size-controlled). It is a status of the power block, not a verdict.

   **(b) Detection run, at each `rho`.** `kappa` is set by bisection in [0, 1] (at `sigma_g`) so
   that the mean over 1000 draws of `Q(I) - Q(C)` equals M. If `kappa = 1` cannot reach M, that
   is recorded and the run uses `kappa = 1`. The block records, at each `rho`:
   - `detection_full` = the share of draws passing P1 to P8;
   - `detection_p1` = the share passing P1 alone;
   - `type_m` = the mean of `Q(I) - Q(C)` over passing draws divided by the mean of `Q(I) - Q(C)`
     over all draws (how far a pass overstates the planted gain, whether or not the plant reached
     M);
   - `detectable_gain_q` = the median `Q(I) - Q(C)` among passing draws, on the Q scale;
   - when no draw passes (certain under `P2_UNATTAINABLE`), `type_m` and `detectable_gain_q` are
     `null` with reason `NO_PASSING_DRAW`, and section 8a's `DeltaUSD / type_m` is not printed.
   The label of section 7 uses the SMALLER of the two `detection_full` values.
3. **`MDE95 = c x`** the median `SE*` across the detection draws at `rho = 0.8`. Its unit is the
   `Dbar` scale (a difference of PV-weighted mean squared anchor-scaled errors), which is NOT the
   scale of M (the Q scale, a root mean square). The block prints `detectable_gain_q` beside it
   for the Q-scale reading.
4. **`INCUMBENT_BELOW_FLOOR`** is raised if `Dbar(I, F) - c x SE*(I, F) > 0`, with `c` the value
   the size run of item 2(a) left: the served rule forecasts worse than no growth beyond the bound.
   It switches nothing and sends OD-7 back to the owner (section 12), whose option (c) it admits.
5. **P2 attainability**, from the truth and `I` only. `A`'s growth lies in [0, 0.12], inside
   `g*_o`'s search interval, so `S_o(A) >= S_o(g*_o)` at every origin and
   `Q(I) - Q(A) <= Q(I) - Q(g*)`, where `Q(g*)` uses `g*_o` at each origin. If
   `Q(I) - Q(g*) < M/2`, no pass is possible: the block records `P2_UNATTAINABLE` and a non-pass
   reads NULL_UNDERPOWERED.

**Power-honest statement, fixed now.**
- No figure of G-0.1 item 6 is carried into this rule; `detection_full` alone decides whether a
  non-pass reads NULL or NULL_UNDERPOWERED.
- A non-pass is expected to read **NULL_UNDERPOWERED**. It means twelve winters cannot tell the two
  rules apart at the margin. **It is not evidence that constant growth is right**, and no copy may
  present it as such.
- The false-pass rate is controlled only as far as the size run shows, at the two registered
  dependence levels (`rho` 0 and 0.8) and on a plant with equal expected loss. P2 to P8 can only
  lower it further. Where the size run is PARTIAL, false passes are size-controlled at one `rho`
  only; where it is UNAVAILABLE, they are not size-controlled; the block and the sentence say
  which.

**Why the challenger is still computed when power is low.** Waiting for power at M would mean
waiting many more winters, a promise never kept. A significant result is not invalidated by low
power; low power is a reason to label a null, not to hide a cell. The house convention labels a
low-power read without changing its rule (`docs/PROSPECT_ANCHOR_GATE.md` section 8). The blind
ledger of section 10 is what gives a successor a frame with no spent winters.

**Pre-registered expectation:** NULL_UNDERPOWERED, on the published record (fitted forecasts tied
or lost one winter ahead on 2026-06-10 and 2026-08-19) and the small frame.

---

## 7. The decision rule

`A` reaches **PASS_DEV** only if ALL of these hold. Each criterion's text is printed verbatim beside
its result.

- **P1, bound and sign-flip.** `Dbar(A, I) + c x SE* < 0`, AND the exact one-sided sign-flip
  p <= 0.05.
- **P2, practical size.** `Q(I) - Q(A) >= M/2` on the point estimate.
- **P3, horizon one not worse.** `MSE_1(A) <= MSE_1(I)` on the point estimate.
- **P4, time splits.** `D_o(A, I) < 0` at 6 or more of the 8 origins (a tied origin does not count).
- **P5, both sub-periods.** `Dbar(A, I) < 0` on S1 and on S2.
- **P6, without REGIME targets.** `Dbar(A, I) < 0` on the non-REGIME pairs. This drops REGIME
  targets only; REGIME winters stay as inputs and anchors, and P7 covers that channel.
- **P7, no single winter carries it.** `Dbar_(-y)(A, I) < 0` for every jackknife replicate of
  section 5 that keeps at least 4 origins.
- **P8, beats the floor and is no more biased.** `Dbar(A, F) < 0` on the point estimate, AND
  `|bbar(A)| <= |bbar(I)| + M/2`.

**Verdicts. The vocabulary is closed:**

| verdict | when |
|---|---|
| **PASS_DEV** | P1 to P8 all hold. A development pass; what it serves is section 9 |
| **WORSE** | `Dbar(A, I) - c x SE* > 0`; recorded as a loss |
| **NULL** | neither PASS_DEV nor WORSE, `detection_full >= 0.80` at both `rho` values, and a pass was attainable |
| **NULL_UNDERPOWERED** | neither PASS_DEV nor WORSE, and `detection_full < 0.80` (the smaller of its two `rho` values) or a pass was unattainable (reason `PASS_UNATTAINABLE`: fewer than 6 untied origins, a smallest attainable sign-flip p above 0.05, or `P2_UNATTAINABLE` from the power block) |
| **VOID** | an integrity gate failed at the look, or an early look (G-0) happened |
| **NOT_AVAILABLE** | a precondition is unmet on the look date; the look slips |

A tie is NULL or NULL_UNDERPOWERED: the incumbent and the owner's lock win ties.

**Blind status, a separate closed field:** `NOT_ARMED` (no PASS_DEV), `PENDING`, `CONFIRMED`,
`VETOED` (section 10).

**Flags. Neither switches anything:**
- `INCUMBENT_BELOW_FLOOR` (section 6);
- `BAND_COVERAGE`: the share of development pairs whose target lies inside the ex-ante P10/P90 band
  of `I`, per horizon, against 0.80, the band built at each origin from winters at or before it by
  the formula of section 11.

**Descriptive arms.** `T` and `B` are computed after the verdict on `A` is written and labelled
DESCRIPTIVE; `T`'s horizon-1 cells are labelled SPENT. They can never ship under this registration,
and a successor that proposes either must disclose these cells.

---

## 8. The surplus effect: what this gate reports, and why not the realized-surplus backtest

The owner's question is about surplus. The obvious frame, the realized-surplus backtest with WAR
held at realized values and only the $/WAR path varied, is not used for a verdict or otherwise,
because it cannot isolate the path:

1. **It is a re-weighting of this gate's frame with less in it.** With WAR fixed, the $-layer
   difference between two paths is `sum_s w_is (P_L(s) - A(s)) d_L(s) ~= sum_h W_L(h) e_{L,h}`, a
   cohort-weighted re-weighting of this gate's errors at origins 2017-2019: 3 origins instead of 8,
   no trend form at 2017 (3 prior winters), and every window crossing the 2021 step.
2. **Its realized leg is on another basis**: the FanGraphs-style `historical_dollars_per_war`, with
   pre-2020 seasons at the 2020 row and today's tiers for arbitration.
3. **Its prediction leg uses today's config for every listing year**, so the $ layer carries
   look-ahead by design.
4. **The served number is post-calibration**, and a monotone refit absorbs any path close to a
   per-listing-year scalar.
5. **`backtest.run_backtest` always computes `by_fv_tier`** (F11), a realized statistic by
   consensus-FV cell that `docs/PROSPECT_ANCHOR_GATE.md` forbids, and the cohort is VAL_3's one
   registered frame.

**What the gate reports instead. Neither has a pass role.**

- **(a) The dollar translation, `DeltaUSD`.**
  - Exposure `X(h)`: the served value-leg dollars of season 2026 + h times
    `season_discount(2026 + h)`, that is, present value at R to the base season B, the basis of
    every served total. Summed over prospects, veterans and free agents, from the unified plumbing
    forced on for the lab process only (`value_framework.dpw_path_forced(True,
    series_path=<copy>)`, never the environment), pricing with `carry_const`, from the payload
    files on disk at the look (several are untracked, `.gitignore`), each file's sha256 recorded in
    the block. The forced-on accessors read the `dpw_path` block from a temporary copy of `git show
    <amendment>:data/fa_dpw_series.json`, never from the live file (section 16), and that copy's
    sha256 is recorded in the block beside the payload shas; `test_dpw_path_lab.py` asserts it. A
    player is counted once: on /projections/ if present there, else on /fa/. Aggregated by surface
    only; no FV cell.
  - `X*(h) = X(h)` for h = 1 to 4; `X*(5) = X(5) + sum_{k=1..4} (1 - k/5) X(5+k)`, the taper
    seasons of section 9. This fold ASSUMES that each arm's error in season N+5+k is `(1 - k/5)`
    times its h = 5 error, which holds only if the escalator path is exact from season N+10 on. `I`
    never tapers and never serves; it is folded the same way only so that the two arms are
    translated on one exposure.
  - Relative error `e_{o,h}(P) = P_o(o+h) / A(o+h) - 1`; per-origin dollar error
    `E_o(P) = |sum_{h <= H_o} X*(h) e_{o,h}(P)|` (signed within the origin, because a $/WAR error
    is common to every player).
  - `DeltaUSD` = the mean over the four full-horizon origins 2018-2021 of `E_o(A) - E_o(I)`. The
    all-origin mean is secondary. `DeltaUSD / type_m` is printed beside it when `type_m` is
    defined (section 6: `null` with reason `NO_PASSING_DRAW` when no detection draw passes).
- **(b) The prediction-only blast radius** of section 13, published with the method switch if it
  happens.

---

## 9. What ships under each outcome, fixed in advance

**Independent of this gate.** The unified plumbing with `carry_const` flips by the owner's hand
after the fWAR epoch's step Z, under the landing rule, with invariants and a blast radius. It
already prices every season at its own projected $/WAR. This gate decides only whether the growth of
seasons N+1 to N+5 changes.

**The SERVE CONDITION.** `DPW_PATH_METHOD` may read `robust_drift` only when the gate block's
verdict is PASS_DEV, its blind status is not VETOED, and one of:
- (i) the blind status is CONFIRMED (section 10). This is the conservative default and binds when
  the amendment commit's `data/dpw_path_owner.json` holds no OD-6 row;
- (ii) the OD-6 answer in the amendment commit's `data/dpw_path_owner.json` is "serve at the
  development pass, with the veto armed" (option code `serve_at_dev_pass`).

It never holds if that answer is "never under this registration" (`never`). **OD-6 is read only as
it stood in the amendment commit.** At the look the lab reads `git show
<amendment>:data/dpw_path_owner.json`, takes the last OD-6 row in chain order, and writes its
option code, date and row sha256, or the id's absence, with the file's chain head sha256 and row
count, into the block's `owner_at_amendment` (never the answer's text: the block ships publicly).
The guard and the SERVE CONDITION read OD-6 from that record, by option code and never by an
option number, and never from the live owner file, so an answer added or changed after the
amendment commit, whatever date it carries, is void for this registration.

**What a served `robust_drift` path is.** At serving time, with N the last realized winter:
- `g_A(N)` is computed by section 3's rule on the then-current truth series through N;
- `P(N+h) = P_served(N) x (1 + g_A(N))^h` for h = 1 to 5, where `P_served(N)` is the served level
  of winter N on the recorded level basis;
- the TAPER: for k = 1 to 4, `ln P(N+5+k) = ln P_const(N+5+k) + (1 - k/5) x 5 ln((1 + g_A(N)) /
  (1 + g_ref))`, and from N+10 on `P = P_const`, where `P_const(s) = P_served(N) (1 + g_ref)^(s-N)`.
  The taper is an assumption, not a forecast; it keeps the served deviation inside the horizons
  that were scored plus four fading seasons;
- recomputed at each post-season roll by the same rule; never re-tuned.

| verdict | what serves | what else happens |
|---|---|---|
| **PASS_DEV** | `carry_const` until the SERVE CONDITION holds; then `robust_drift`, in its own commit | blind status PENDING; registry per section 15; the serving commit carries one procedural knot refit or bridge under the route the owner chose for calibration, and its own blast radius |
| **NULL** or **NULL_UNDERPOWERED** | `carry_const` keeps serving | the block records the verdict; `A`'s blind forecasts keep accruing; registry per section 15 |
| **WORSE** | `carry_const` keeps serving | recorded as a loss; registry per section 15 |
| **VOID** | nothing moves | the question returns only as a new registration that discloses the void read |
| **NOT_AVAILABLE** | nothing moves | the look slips (section 14) |

---

## 10. The prospective frame: ledger, blindness, confirmation, veto, successor

**The ledger.** `data/dpw_path_ledger.json` is append-only and hash-chained: each row carries
`prev_sha256`, the sha256 of the previous row's canonical JSON (the first row carries 64 zeros). A
backward chain detects an edited, inserted or reordered row but not the removal of the last rows,
so the head is also recorded: the sha256 of the last row and the row count are written into the
`dpw_path_gate` block and into the message of every commit that appends rows, and the ledger test
fails unless the file's head and count equal the block's record. With both, no row can be edited
or removed undetected.
- Forecast rows: `{origin, made_at, truth_sha256, basis_id, arm, h, season, anchor_usd, growth,
  forecast_usd, g_ref_recorded, blind_check}` for all six arms of section 3, h = 1 to 5, where
  `anchor_usd` is `A(o)` as the forecast saw it and `growth` is the arm's growth at the origin
  (for `damped`, its step-1 growth, which equals `g_I(o)`; for `trend_line`, `exp(b_o) - 1`).
  For those two arms `growth` is a disclosure only and is NEVER used to re-anchor, because
  `growth` does not generate their path: `A(o)(1 + g_I(o))^h` is `I`'s path, not `damped`'s, at
  h >= 2, and `trend_line` is not anchored at `A(o)` at all.
- Scoring rows: `{target, actual_usd, tau_W, truth_sha256, regime, anchors_restated}`, where
  `anchors_restated` records the scoring vintage's value of each stored anchor winter, so a
  restatement is visible.

**Blindness, mechanical.** Forecast rows for origin o are BLIND only if NO enriched class o+1 deal
exists when they are committed, tested two ways, both recorded in the rows' `blind_check`:
1. no REALIZED-LEVEL map holds winter o+1 as a key (or, where named, as a value). The count is
   zero, not a threshold: `fa_market.dpw_breakdowns` (`fa_market.py:685-719`) keys `by_winter` on
   every winter with at least ONE enriched deal and prints that winter's `spend` and `war` from the
   first deal (its `dpw` is suppressed only below 8 deals and 4 WAR, `:608-609`, `:675-682`), and
   VAL_1's writer enriches through the class winter `N + 1`, so a level is derivable from the first
   deal of winter o+1. The realized-level maps are, by JSON path:
   - in `data/fa_dpw_series.json`: `usd_per_war_by_winter`, `breakdown.by_winter` (and every
     `pos`, `len` and `tier` cell inside it), `breakdown.realized`, `dpw_path.truth.by_winter`,
     `dpw_path.truth.tau_by_winter`, `dpw_path.truth.term_mix_index.by_winter` and
     `dpw_path.served_level.by_winter`;
   - in every `data/fa_class*.json`: `dpw_series_pricing`;
   - in `data/fa_meta.json`: `dpw_series.usd_per_war_by_winter`, `dpw_series.breakdown.by_winter`,
     `dpw_series.breakdown.realized` and `dpw_pricing.usd_per_war_by_winter`;
   - in `data/dpw_forecast_eval.json`: the `test_winters` values and the `per_winter[].winter`
     VALUES (`tools/fit_dpw_forecast.py:43`, `:58`);
   - in `data/fa_archive.json`: the `winters[].year` values.
   Forecast, path, band and salary-index maps are NOT realized levels and are excluded by name:
   `dpw_path.path.*` (including `usd_by_season`, `kind_by_season` and `band`), `dpw_path.salary_index.*`,
   the served path summary in `data/fa_meta.json`, and the ledger's own forecast rows. Any other
   year-keyed map found in these files is listed in `blind_check.unclassified_year_maps` as a
   disclosure; it does not decide blindness. For the tracked files (`data/fa_dpw_series.json`,
   `data/fa_meta.json`, `data/fa_class*.json`, `data/dpw_forecast_eval.json`,
   `data/fa_archive.json` are all tracked at `64bf1bb3`) the check is evaluated on the blobs of the
   commit that adds the rows (`git show <commit>:<path>`): `--prelook` evaluates it on the working
   tree that the amendment commit will hold, and the ledger test re-checks it on the amendment
   commit's blobs and fails if they differ;
2. the count of class o+1 signings in `prospects.db` `fa_signings` that pass the estimator's deal
   filter (MLB deal with years, guarantee and MLBAM id; the filter of `fa_market.enriched_signings`)
   is ZERO, counted on the committing machine immediately after a same-day
   `fa_pipeline.refresh_current_class(o+1)` and a writer run on that machine, with the scrape time
   recorded in `blind_check.scrape_at`. Only the box scrapes the class daily (`run_monthly.py`
   step d10, `:3486-3497`, in `fa_pipeline.DAILY_SCRAPE_MONTHS`, `fa_pipeline.py:369`) and serves
   /fa/ from its own database; a dev database refreshed on demand would otherwise let the committer
   choose, by choosing when to refresh, whether origin o enters the ledger.

A failed check means origin o is not blind; the ledger then starts at the next origin whose check
passes. The origin-2026 rows are written in the pre-look amendment commit if they pass, which in
practice requires that commit before the first class-2027 major-league deal is signed and
enriched (the first week of November 2026 or so); later origins are written at the post-season run
of section 14.

**Scoring.** At the post-season M14-3 run of season W (the owner's yearly rebuild, first around
October 2027), the lab appends the scoring row for target W, then forecast rows from origin W if
blind. Errors on the ledger are computed only:
- for `I`, `F` and `carry_const`, in a dated disclosure block;
- for `A` against `carry_const`, for confirmation and veto;
- by a successor registration.

**Which side a target lands on, in growth terms on the scoring vintage.** For a scored blind target
W with h = 1 forecast rows from origin W-1: let `r = ln(A_s(W) / A_s(W-1))`, with BOTH levels
taken from the scoring vintage's truth. The target is on A's side if
`|ln(1 + g_A(W-1)) - r| < |ln(1 + g_ref_recorded) - r|` strictly, using the STORED growths of the
two forecast rows; otherwise it is on `carry_const`'s side. This equals re-anchoring both stored
forecasts at the restated anchor, so a restatement of winter W-1 between the forecast vintage and
the scoring vintage (a label or fWAR revision, a corpus or deferral repair, a projection switch)
cannot decide the side. A target whose anchor winter W-1 is absent from the scoring vintage is not
sided and is recorded as such. Every later scoring of the ledger's forecasts, a successor's
included, re-anchors the same way: a stored forecast is compared with a target only as
`A_s(o) x forecast_usd / anchor_usd`, on the scoring vintage's anchor. For the four constant-growth
arms this equals `A_s(o)(1 + growth)^h`, so the h = 1 side rule above is unchanged; for `damped`
and `trend_line` it is the only admissible re-anchoring (their stored `growth` does not generate
their path), so a successor that proposes either scores the forecast that was made. An UNSIDED
target is skipped by the confirmation, veto and reversion rules below exactly as a REGIME target on
A's side is: it does not count toward the first two non-REGIME targets, and it neither extends nor
resets a consecutive count.

**Confirmation (armed by PASS_DEV while `A` is not serving).** CONFIRMED when the first two scored,
sided, NON-REGIME blind targets are both on A's side. VETOED as soon as any scored, sided blind
target (REGIME or not) before confirmation is on `carry_const`'s side.

**Veto, while `A` serves** (after CONFIRMED, or from PASS_DEV under OD-6 option (ii), in which case
the single-miss rule above does not apply and the status reads PENDING until two sided non-REGIME
targets land on A's side). Revert to `carry_const`, and set the status VETOED, when two consecutive
scored, sided blind targets are on `carry_const`'s side. A REGIME target on A's side, or an unsided
target, is skipped: it neither extends nor resets the count. A reversion is its own commit, with the
section 17 sentence.

**Successor.** It may register at any time, as a NEW document that discloses this read. Its verdict
frame holds only targets whose scoring rows are appended AFTER its registration commit. Its
challenger list and criteria are frozen before those actuals exist. Forecast rows written earlier
may be used.

---

## 11. The two switches, and the band

**`SERVE_DPW_PATH`** (value_framework).
- A committed constant, default `False`. `dpw_path_on()` is its one read site.
- The environment variable `EEPHUS_SERVE_DPW_PATH=0` forces it OFF at call time. No environment
  value turns it ON.
- A context manager `dpw_path_forced(on, stages=None)` exists for tests, the lab and the
  prediction-only blast-radius tool (`tools/dpw_blast_radius.py`) only; a lint test fails if any
  other module calls it. `stages` switches the levers on one at a time for the blast radius; it is
  never read by a served path.
- OFF gives every legacy branch verbatim. It is not governed by this gate.

**`DPW_PATH_METHOD`** (`dpw_path.py`).
- `"carry_const"`, with no environment override. The writer is its one read site.
- `test_dpw_path_method_guard.py` fails unless it reads `carry_const`, or `robust_drift` with the
  SERVE CONDITION of section 9, read only from the `dpw_path_gate` block of
  `data/dpw_forecast_eval.json` (verdict, blind status and `owner_at_amendment`). It never reads
  OD-6 from the live `data/dpw_path_owner.json`.
- **This is the only served object this gate governs.**

**The band, disclosure only.**

```
V_h = tau_N^2 + h s_d^2 + h^2 c_m s_d^2 / n_d
P10/P90 = P exp(-/+ t_{0.90, n_d - 1} sqrt(V_h))
```

- `s_d`: the ordinary sd of the truth series' differences (gap rule), including the 2021 step.
- `n_d`: their count.
- `c_m`: 1 for `carry_const` and `carry_destale`, pi/2 for `robust_drift`.
- `tau_N`: the SE of `ln A(N)` from a within-winter deal bootstrap, B = 500, seed 20260925.

It is labelled `forecast` for h <= 5 under a served forecast method, `convention` under
`carry_const`, and `assumption` beyond h = 5. It is never added to player draws. The served path is
a central path: under lognormal price risk the expected price is higher by `exp(V_h/2)`, which is
published and not applied.

---

## 12. The escalator and the nominal rate: what may change them

- **`g_ref` is 0.0409** (owner L4(c)). OD-7 is answered ONCE per registration, as a rule choice,
  and the rule then runs without further choice:
  - (a) constant: `g_ref` stays 0.0409;
  - (b) the served rule, re-applied mechanically at the plumbing flip and at every later
    post-season roll: `g_ref` = `fa_market._destale_rate` applied to the then-current truth
    series through N (P20 included), and nothing else;
  - (c) 0, which may be chosen only if `INCUMBENT_BELOW_FLOOR` was raised at the look, and then
    replaces (a) or (b) for the rest of this registration. It is the ONE answer given after the
    look: it is recorded then, as a new row of `data/dpw_path_owner.json` (option code
    `zero_if_floor`), and the lab's next run, or the flip commit, copies its option code, date and
    row sha256, with the file's chain head sha256 and row count, into the block as
    `owner_after_look`. That record is valid only while the block's `INCUMBENT_BELOW_FLOOR` is
    true, and it is the one other permitted read of OD-7 (section 16); the writer reads `g_ref`
    from `owner_at_amendment` and, when a valid `owner_after_look` exists, from it.
- The choice between (a) and (b) does not depend on the look. It counts only as it stood in the
  amendment commit's `data/dpw_path_owner.json` (the last OD-7 row in chain order; copied into the
  block's `owner_at_amendment` as its option code `keep_0409` or `remeasure_served_rule`, its date
  and its row sha256, as for OD-6); with no row recorded there, (a) binds. It may not alternate:
  switching between (a) and (b), or any other change of rule, needs a new registration.
- Under (b) the first re-measurement is made at the plumbing flip itself, before the switch is
  turned on: the flip task computes the rule-(b) `g_ref` on the then-current truth series and
  records it, and a fresh OD-2 answer (a new R, or the owner's confirmation of 0.113763 at the new
  raise) is recorded before `SERVE_DPW_PATH` is set. The value leg is PV-neutral only at `g_ref`
  = 0.0409 with R = 0.113763; from the flip on, under (b), it is not.
- **Banned:** any `g_ref` derived from development errors, from `g_A`, from `T` or `B`, from any
  forecast error, or from any series other than the truth series (payroll, QO, CBT, arbitration
  index). Any other value needs its own registered read on blind targets.
- **The nominal rate R** is a stored owner constant (OD-2). It is never derived from a path or from
  `g_ref`, never set per season, and changes only by owner answer. When `g_ref` changes under (b)
  or (c), R does not follow it, so the value leg stops being PV-neutral; OD-2 goes back on the
  owner list, and any new R is a new owner answer.
- Neither enters this gate's truth. `carry_const` rows use the `g_ref` recorded when they are
  written.

---

## 13. Served numbers that move under the method switch, with bands, and those that must not

These apply to the method switch. The plumbing flip carries its own copy of the same table.

**Measurement.** Prediction-only, before against after, by surface and listing year. No realized
value and no FV cell.

**Bands that trigger an owner decision.** They are not pass criteria:
- sum of veteran `surNpv` +/- 7.5 percent (baseline `docs/PROJ_PATH_SHAPE_GATE.md:1297-1298`);
- sum of prospect surplus +/- 25 percent;
- any single row +/- 50 percent (counted only where the row's base exceeds $5M in absolute value,
  so a near-zero contract row that changes sign does not trip it) or $15M, each listed by name;
- Trade Machine top-100 membership change > 10 rows;
- OrgSur+ Spearman < 0.95;
- FA Deal+ verdict flips per position group;
- non-tender cut decisions that change, listed by name.

**Must not move, asserted pre and post:**
- eFV grades and board ranks;
- pBust;
- every WAR number;
- /arbitration/ awards;
- Gate 2 (`data/fa_gate2_eval.json` and /fa/ price predictions);
- betting, DFS and fantasy numbers;
- the provisional freeze (`test_provisional_freeze_pin.py`).

---

## 14. The clock. One look, on fixed conditions.

**Looking early disqualifies** (G-0). A look after its conditions requires an amendment filed before
the look, saying what moved on disk since this document was committed (the 5c amendment form). An
amendment changes no threshold, frame, arm, order or criterion.

| when | what | may it happen before |
|---|---|---|
| this commit | this registration and its pin test, results EMPTY | - |
| any date after this commit, EXCEPT between the fWAR epoch's steps A and Z (`FWAR_LABEL_EPOCH_GATE.md` part 7) | the build with both serving switches off and the `dpw_path` block switch off: VAL_1's writer stays wired where VAL_1 put it and every caller writes VAL_1's keys only; method tests on synthetic series only | not between steps A and Z |
| any date after the build, with the same exception | the lab, in its own commit, tested on synthetic series only; `--real` refuses | not between steps A and Z |
| after the step Z entry in `FWAR_LABEL_EPOCH_GATE.md` part 9 | the block switch turned on in the one writer, which VAL_1 already calls at the top of the rebuild ahead of every pricer that reads the file; then, on the machine that will make the amendment commit, one ordinary write and one forced recompute on a later calendar day (I-2) | not before the step Z entry |
| after ALL of: VAL_1's writer committed; the step Z entry; the two writes with equal shas; P20 stamped | **the pre-look amendment** (5c form), a section headed `## Amendment 1 (pre-look)` placed immediately before section 18, committed together with: `data/fa_dpw_series.json` as the second write left it; the `dpw_path_gate` stub block written by `tools/dpw_path_gate.py --prelook` (verdict `REGISTERED`, the truth sha256, the I-3 and I-5 records, the stamps, the served rule's growth `g_I(N)` on the truth series and on the served level basis, which are forecast quantities, not errors); `data/dpw_path_owner.json` with every owner answer recorded by then; and the origin-2026 ledger rows if they pass section 10's check, with the ledger head. The amendment text records the truth sha256, both write shas, the lab and `dpw_path.py` blob shas and the owner answers present | not before every condition holds |
| **the LATER of 7 days after the step Z entry and the day after the amendment commit**; never on the same day as another registered look (PROJ_PATH_SHAPE 2026-10-02, 2026-10-09, 2026-10-23, 2026-11-06, 2026-11-13 and 2027-02-15; the PROSPECT_ANCHOR look; the ETA_FG_BLEND look; VAL_3's registered read; any 5c look; the fWAR epoch's step Z margins); never concurrent with another lab or the chunked suite | **THE LOOK. Once.** Integrity gates; the size run, then the `power` block from the truth, `I` and `F`; then the cells of `A` and the verdict; then the descriptive `T` and `B`, the term-mix index, `BAND_COVERAGE` and `DeltaUSD` | not before. If the conditions are unmet, the look slips; the development frame is unchanged by a slip because its targets end at 2026 and the lab reads the pinned block |
| each post-season M14-3 run (first around October 2027) | ledger scoring rows; confirmation or veto; forecast rows from the new origin if blind | - |
| any time | a successor registration, scored only on targets appended after its commit | - |

**The amendment commit** is the one commit that adds the heading `## Amendment 1 (pre-look)` to
this document, as a line of its own with no trailing whitespace. The lab finds it with
`git log -G '^## Amendment 1 [(]pre-look[)]$' --format=%H -- docs/dpw-2026-09-25/DPW_PATH_GATE.md`,
a line-anchored regex over the diff's added and removed lines, and refuses `--real` unless exactly
one commit matches. A substring search (`-S`) would not do: it lists every commit that changes the
number of occurrences of the string anywhere in the file, and this document mentions the heading
mid-line in the clock table and in this paragraph, so the registration commit would match as well
and `--real` would refuse forever. Every mention of the heading in this document is mid-line, never
at the start of a line, and `test_dpw_path_lab.py` runs the registered lookup on a scratch
repository seeded with this document's own text, an unrelated edit and the amendment heading, and
fails unless it returns the amendment commit alone.

**Why not now, on today's series.** Three reasons, each sufficient:
- the series restates at the fWAR epoch (step E deletes `fa_corpus.pkl`; step S reruns the FA
  exports);
- P20 restates the 2021 to 2023 winters;
- the three published copies already disagree by up to 8 percent on one winter.

---

## 15. The artifact, and the tests that stop a criterion being edited

**The block.** `data/dpw_forecast_eval.json` gains a `dpw_path_gate` block with its own
`generated_at`; the file's top-level `generated_at` belongs to `tools/fit_dpw_forecast.py` and is
not touched by the lab. `tools/fit_dpw_forecast.py` gains carry-forward of the block in the build
commit, before the block first exists (following `fa_backtest.py:708-722`), so a re-run of the
published eval never deletes it.

**Who writes it.** The stub (verdict `REGISTERED`, the truth sha256, the I-3 and I-5 records, the
stamps, `g_I(N)` on both bases, and, whenever `--prelook` appends the origin-2026 ledger rows, the
ledger's head sha256 and row count) is written by `tools/dpw_path_gate.py --prelook` and committed
in the amendment commit, so the ledger test can check the head and count from the amendment on.
Everything else is written by `--real` at the look, and by the lab at each post-season scoring run
(which refreshes the ledger head and count and, after the look, may add `owner_after_look`). No
other writer touches the block.

**What the block carries:**
- the pin stamps and I-1 to I-8 with their evidence;
- `owner_at_amendment`: for OD-6 and for OD-7, the option code, the date and the row sha256 of
  the last row for that id in chain order in the amendment commit's `data/dpw_path_owner.json` (or
  `null` for an id absent there), with that file's chain head sha256 and row count. Never the
  answer's text or the question text: the block ships publicly and the owner file does not;
- `owner_after_look`: absent unless `INCUMBENT_BELOW_FLOOR` is true and an OD-7 option (c) row
  was recorded after the look; then that row's option code, date and row sha256, with the file's
  chain head sha256 and row count at the copy (section 12);
- the ledger's head sha256 and row count (section 10);
- the sha256 of every payload file read for `DeltaUSD` (section 8a), and of the temporary copy of
  the amendment commit's `data/fa_dpw_series.json` the forced-on accessors priced from;
- the size run with its plant search and `size_status`, and the `power` block (first), including
  `P2_UNATTAINABLE`;
- per-pair errors of `I`, `F` and `A`;
- `S_o`, `D_o`, `Dbar`, `Q`, `SE_jack`, `SE_boot`, `SE*`, `c`, the sign-flip p, ties, sub-frame
  contrasts, jackknife replicates and per-origin influence;
- P1 to P8, **each with its criterion text verbatim beside its result**;
- the verdict and the blind status;
- the flags; the DESCRIPTIVE `T`, `B` and term-mix cells; `DeltaUSD`;
- the seeds, B values and wall time.

**`test_dpw_path_gate_registration.py` pins the CRITERIA, not a result, as text of this
document** (it is committed before any code it describes exists):
- the arm list and formulas, the gap rule, the clip, the 0.8, the 4-winter minimum and the median
  with its even-count rule;
- the truth estimator id, the level-equivalent `G_i` formula and P20's text;
- `u`, the weights (base 1.113763 and the five values), `S_o`, `Q`, M = 0.025 and M/2,
  `c = 1.894579` and the size-run raise rule;
- the seeds (20260925), B = 2000 / 500 / 1000, the plant search (the `kappa` brackets [0, 1] and
  [-3, 0], at most 6 halvings with steps 1 and 2 re-run at each, 30 bisection steps, `tol` = 0.05
  median `SE*`), `rho` 0 and 0.8, the `size_status` values FULL, PARTIAL and UNAVAILABLE, the
  `sigma_g` floor 0.01, the `type_m` definition with `NO_PASSING_DRAW`, and `g*_o`'s grid,
  interval and tolerance;
- the order inside the `power` block (the size run first, the flag with the `c` it left);
- the jackknife definition (12 winters, delete everywhere, weights renormalised) and the tie rule;
- the frames (origins 2018-2025, `H_o`, 30 pairs), S1, S2, the REGIME targets and the prospective
  REGIME rule;
- the term-mix weights 0.2517, 0.3177 and 0.4306 and the exposure's discount (section 8a), and
  that the forced-on accessors price from the amendment commit's copy of the series file;
- the verdict vocabulary and the blind-status vocabulary (both closed), and `P2_UNATTAINABLE`;
- the early-look definition (including the oracle, attainability and planted-challenger clause)
  and its tool exception with the mechanical horizon-1 rule and the six-method list;
- the SERVE CONDITION with OD-6 read from `owner_at_amendment` by option code, the taper, the OD-7
  rules with `owner_after_look` for option (c), and the OD-7 option codes `keep_0409`,
  `remeasure_served_rule` and `zero_if_floor`;
- the blindness check with its named JSON paths and its zero count on both conditions, the side
  rule in growth terms, the re-anchoring rule `A_s(o) x forecast_usd / anchor_usd`, the unsided
  target rule, the hash chain and the head record;
- that the `power` block precedes the cells;
- the clock table and the amendment-commit rule with its `-G` lookup, and that every mention of
  the amendment heading in this document is mid-line;
- the $5M base below which the single-row percent band does not count (section 13);
- that section 18 reads EMPTY AT REGISTRATION;
- that the text says `DPW_PATH_METHOD` defaults to `carry_const`.

The code facts are pinned by the build's tests, from the commit that creates the code: the
`DPW_PATH_METHOD` default by `test_dpw_path_method_guard.py` (commit 2); the arms, the median and
the side rule by `test_dpw_path_methods.py` (commit 2); the hash chain, the head record and the
blindness check by `test_dpw_path_lab.py` (commit 2b) and by the ledger test that the amendment
commit adds.

**The result pin.** When section 18 is filled in, the result pin goes in its own file
(`test_dpw_path_gate_result.py`), for the reason `test_fwar_label_epoch_registration.py` gives: a
result pin beside a criterion pin invites editing the criterion to match the result.

**Registry.**
- `fa_dpw_series` notes cite the block.
- The `dpw_path` row is `unvalidated` with no eval artifact until the look (`model_registry.py:94-95`
  rejects an `unvalidated` row that carries one). At the look it gains
  `eval_artifact: data/dpw_forecast_eval.json` and moves, by outcome:

  | outcome at the look | before the plumbing flip | after the plumbing flip (`carry_const` serving) | after a method switch |
  |---|---|---|---|
  | PASS_DEV | `provisional` / `measured_not_adopted` | `provisional` / `shipped_partial_measurement` | `provisional` / `shipped_partial_measurement` |
  | NULL, NULL_UNDERPOWERED, WORSE | `provisional` / `measured_not_adopted` | `provisional` / `shipped_partial_measurement` | (none) |
  | VOID, NOT_AVAILABLE | stays `unvalidated`, no eval artifact | stays `unvalidated`, no eval artifact; the notes cite the void or missing read | (none) |

  `shipped_partial_measurement` because the served `carry_const` was never scored on the
  development frame. No outcome of this gate makes the row `validated`.
- `MODEL_REGISTRY.md` is regenerated by `tools/gen_audit_docs.py`, never edited.

---

## 16. Banned, and enforced mechanically where code can enforce it

- An early look (G-0). It VOIDS the registration.
- Adding, tuning or re-parameterising an arm; running `tools/fit_dpw_forecast.py` on a real
  series after modifying it to compute a horizon above 1, or any method other than `flat5`,
  `trend`, `trend_cbt`, `carry_destale`, `carry_zero` and `carry_const` (running it on any series
  with its registered method list at its mechanical horizon 1 is allowed, G-0); changing M, `c`,
  a seed, the weights, the frames, the order or a criterion after this commit, other than by a
  pre-look amendment that names what moved on disk.
- Computing, on a real series before the look, `g*_o`, `Q(g*)`, the P2 attainability bound or
  any statistic of a planted challenger (G-0); `--prelook` never calls the oracle search, and
  `test_dpw_path_lab.py` asserts it.
- Reading the pre-epoch series, the live file at the look (by the lab's forced-on accessors
  included, section 8a), or any truth other than section 1's.
- Any 2020 handling other than P20 in the truth.
- In the lab or in this gate's verdict: calling `backtest.run_backtest`, importing
  `surplus_backtest_real`, or computing any statistic by consensus-FV cell. Anywhere under this
  registration: computing a statistic by consensus-FV cell, or calling `backtest.run_backtest`.
  The one sanctioned importer of `surplus_backtest_real` is the knots-only calibration refit of
  section 0a.
- Reading OD-6 or OD-7 from anywhere but the block's `owner_at_amendment`, or OD-7 option (c)
  from anywhere but the block's `owner_after_look` (section 12); mapping either by an option
  number rather than its option code.
- Calling `fa_backtest.run_market_gate` from the lab, or writing `data/fa_dpw_series.json` from the
  lab (the md5 check of I-6).
- Scoring any horizon beyond 5, or any copy calling a season after 2031 a forecast.
- Serving `robust_drift` without the SERVE CONDITION (the guard test).
- Setting the nominal rate per season to match a path, which makes any path PV-neutral and any gate
  pass by construction. Deriving R from a path. Writing R into `discount_rate`. Implementing the
  path through `dollars_per_war_inflation`, `winter_dpw` or `_destale_rate`, which would move Gate 2
  with no model change.
- Any `g_ref` outside section 12's admissible set.
- Counting a REGIME winter toward a confirmation, or a pre-registration actual toward a successor's
  verdict frame.
- Turning `SERVE_DPW_PATH` on through the environment.
- Any copy presenting NULL_UNDERPOWERED as evidence that constant growth is right, or saying the path
  improves surplus accuracy.

---

## 17. Pre-commitments: the exact sentence each outcome publishes

- **PASS_DEV:** *"On the eight forward-chained origins 2018 to 2025, a $/WAR growth rule based on
  the median of the series' own year-over-year changes forecast the level one to five winters ahead
  better than the rule behind the served escalator (mean PV-weighted squared error contrast [Dbar],
  bound [ub], [k] of 8 origins[; the size run was unavailable, so false passes were not
  size-controlled / ; false passes were size-controlled only at rho = x]). Its designers chose it
  after reading every winter of the series, so this frame
  was not blind, and nothing switches until [the blind condition]."*
- **Served after the SERVE CONDITION:** *"Seasons [N+1] to [N+5] are now priced at a $/WAR path
  whose growth is the median of the series' own year-over-year changes, after [blind confirmation on
  winters X and Y / the owner's decision to serve at the development pass]. The four seasons after
  return in equal steps to the owner's [g_ref] percent escalator path, which is an assumption, not a
  forecast. Each new winter is a blind check that can reverse it."*
- **NULL:** *"On the eight forward-chained origins 2018 to 2025, a median-based growth rule did not
  forecast the $/WAR level better than the rule behind the served escalator ([Dbar], bound [ub]).
  Each season is priced at the one written $/WAR path, which grows at the escalator the owner
  set."*
- **NULL_UNDERPOWERED:** *"Twelve winters cannot tell a median-based growth rule from the rule behind
  the served escalator at a 2.5 percent margin (detection [x] against 0.80[; a pass was unattainable
  because (reason)]). Each season is priced at the one written $/WAR path, which grows at the
  escalator the owner set. This is not evidence that constant growth is right. Blind forecasts
  accrue each winter from [first blind origin]."*
- **WORSE:** *"The median-based growth rule forecast the $/WAR level worse than the rule behind the
  served escalator at horizons one to five ([Dbar], lower bound [lb]); recorded as a loss. The one
  written path keeps growing at the owner's escalator."*
- **INCUMBENT_BELOW_FLOOR raised:** *"The rule behind the served escalator forecast the $/WAR level
  worse than no growth at all on the forward-chained origins ([Dbar], lower bound [lb]). Nothing
  switches; the escalator goes back to the owner."*
- **BLIND_VETOED:** *"The [season] winter came in nearer the owner's escalator path than the
  median-based rule's forecast, before the rule was confirmed; it will not serve under this
  registration."*
- **Reversion (veto while serving):** *"Two winters in a row came in nearer the owner's escalator
  path than the served forecast; seasons [N+1] to [N+5] revert to the escalator path."*
- **VOID / NOT_AVAILABLE:** *"The registered $/WAR path read was [voided because (reason) / not
  taken because (condition)]. Nothing served changed."*
- **Unconditionally, in every artifact:** *"Every number here is a statement about the
  signings-implied $/WAR series on its growth-free sticker basis (deferred deals at their
  level-equivalent sticker), built from WAR projections fitted
  before each winter on the fWAR label with the 2020 playing-time correction; the projection
  settings and the label vintage are today's. The series is the price the winning bidder paid per
  projected win; it leaves out the tax a payroll above the threshold pays, minor-league deals and
  extensions. No surplus accuracy was measured, and seasons after 2031 are an assumption, not a
  forecast."*

---

## 18. Results

**EMPTY AT REGISTRATION.**

No error, loss, contrast, interval, power figure, size figure, detection rate, flag, band coverage,
ledger score or dollar translation has been computed at this commit. None may be written anywhere
above this line, and nothing above this line may be edited once anything is written below it,
except by a dated amendment filed BEFORE the look under the 5c amendment form, which names what moved
on disk and changes no threshold, frame, arm, order or criterion.

The first entry here is dated, names the commit that produced it, records the truth sha256 and the
stamps of I-1 to I-8, and states the verdict and the blind status in section 7's vocabulary.
Section 17's sentences bind it.

---

Nothing in this document was scored. Every number above is a value in a committed artifact or
config, a figure in a commit message, a line of code read for what it does, or arithmetic on such
figures labelled as such. The direction of the answer has a published prior, recorded in G-0.1, and
this gate is written as a development read that can fail in either direction, followed by a blind
check that can only hold a pass back.
