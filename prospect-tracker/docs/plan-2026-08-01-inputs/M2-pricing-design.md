All measurements below were made on main = ab56f7b, artifacts as served in `prospect-tracker/data/` (regen of 2026-08-01, calibration `isotonic-real-v6-evframe-2026-07-31`). Every number, line cite, and formula below was re-verified against the working tree on 2026-08-01 (adversarial pass; see Verification log).

# LANE M2 — Rest-of-current-season control pricing: verified design inputs

## 1. How vet surplus (surNpv) is computed today

All in `prospect-tracker/proj_export.py`.

**Horizon constants — the exclusion of 2026 is a hardcode, not a date computation** (proj_export.py:59-60):
```python
FIRST_SEASON = 2027          # first fully projected season (2026 is in progress)
HORIZON = 5                  # 2027..2031
```

**The formula** — `_apply_contract` (proj_export.py:283-312), stamped per vet row inside `_veteran_rows`:
```python
sal = {int(y): int(v) for y, v in (ct.get("salary_by_year") or {}).items()}
...
sur = []
npv = 0.0
any_sal = False
for t in range(HORIZON):
    season = FIRST_SEASON + t
    s_usd = sal.get(season)
    if s_usd is None:
        sur.append(None)
        continue
    any_sal = True
    v_usd = _season_value_usd(m["war"][t], t, dpw)
    d_usd = v_usd - s_usd
    sur.append(round(d_usd / 1e6, 1))
    npv += d_usd / ((1 + r) ** t)
if any_sal:
    m["sur"] = sur
    m["surNpv"] = int(npv)
```
- Seasons: exactly 2027-2031 (`FIRST_SEASON + t`, t=0..4). The 2026 season is never in the loop; a 2026-only contract (Minter) yields `any_sal=False` → no `sur`/`surNpv` at all. Discount exponent t=0 for 2027, i.e. NPV is "as of 2027", not as of today.
- WAR source: `m["war"][t]` = the FA Marcel engine mean path (`fm.contract_war_path(hist, side, FIRST_SEASON, HORIZON, ...)`, proj_export.py:347-349; fa_market.py:366-393), with the in-progress 2026 season blended via `in_prog = (FIRST_SEASON-1, frac)` (proj_export.py:253-254). Explicit comment: surplus prices off `war` (expected value), never `warPTH` (proj_export.py:434-436).
- Salary per season: Spotrac `salary_by_year` from the contract join (see §3); salary-missing seasons get `sur=None` and contribute nothing ("arb/pre-arb seasons carry projections but no surplus claim", proj_export.py:31 — note the same docstring sentence still says "discount at the platform 9%", stale wording vs the production 7% below).
- $/WAR: `_season_value_usd` (proj_export.py:226-231):
```python
base_flat = float(vf._config()["dollars_per_war"]["flat"])
infl = float(vf._config().get("dollars_per_war_inflation", 0.05))
return vf.tiered_war_value_usd(war) * (dpw_level / base_flat) * ((1 + infl) ** t)
```
  `dpw_level` = `_winter_dpw(FIRST_SEASON)` (proj_export.py:234-242, call at 1548) — the winter-2027 ex-ante level from the committed signings-implied series `data/fa_dpw_series.json` via `fm.winter_dpw` (fa_market.py:740-776). Served value: `dpw_usd = 15,640,340`. `tiered_war_value_usd` is the convex C1-smoothstep tier curve (value_framework.py:457-508), whose tier rates come from `value_framework_config.yaml:226-236` (flat 11.74e6, tiered lt_1 6.97 / 1_to_2 8.76 / 2plus 13.63). The base config's `fa_implied.enabled: true` rescale (yaml:251-253) is DISABLED under the production valuation set (`win_cost.disable_fa_implied: true`, config/valuation_sets/clemens_2026.yaml:84; valuation_sets.py:275-279), so the served rates are exactly the yaml table (runtime `_fa_reanchor` = None, flat = 11,740,000 — verified live).
- **Discounting — net-7%, NOT 9%/5%.** `r = float(vf._config()["discount_rate"])` (proj_export.py:255). The base yaml says 0.09 + 5% inflation (value_framework_config.yaml:258, 283), but production boots under the `clemens_2026` valuation set (`_DEFAULT_VALUATION_SET = "clemens_2026"`, value_framework.py:296-297), whose overlay sets `discount_rate = net_rate = 0.07` and `dollars_per_war_inflation = 0.0` (config/valuation_sets/clemens_2026.yaml:94-99; valuation_sets.py:285-298). Verified in the served artifact: `dpw_infl: 0.0`. So in production: value escalation per season is zero and discount is a flat 7%/yr.
- Ground truth from the served artifact: Aaron Judge `thru: 2031, aav: 40000000, sur: [40.4, 26.3, 7.9, -24.3, -37.7], surNpv: 23350804` (war path `[4.43, 3.65, 2.64, 1.36, 0.25]`; arithmetic re-run under the live config reproduces sur and surNpv byte-exactly); A.J. Minter `thru: 2026, aav: 7588208`, no `sur`/`surNpv` keys.
- `surNpv` is raw dollars; every consumer divides by 1e6 (bayes_trade_value.py:4128 comment: "surNpv is raw $; board surplus is $M").

## 2. Rest-of-season WAR candidates already in the repo

**(a) Current-season-to-date bWAR — EXISTS.** The FA corpus row for each (mlbam, season) carries `"war": war_map.get(key)` (fa_projection.py:245-254 hitters, analogous pitcher block), where `war_map` comes from `_war_age_maps()` (fa_projection.py:87-110): pybaseball `bwar_bat`/`bwar_pitch` (B-Ref war_daily, bat+pit summed per season) — this is the site-wide bWAR source and includes the in-progress 2026 season (the corpus is built through `date.today().year`, fa_projection.py:169, with a data-age staleness gate at fa_projection.py:113-154, `CORPUS_TTL_DAYS = 3`). So 2026 WAR-to-date per player = corpus row `(mlbam, 2026)["war"]`. Also on file: `realized_war` per player in xfv.json entries (career; present on 2,387 of 9,338 by_player entries; used by the backgrade temper, bayes_trade_value.py:4198).

**(b) 2027 projection to prorate — EXISTS.** `mlb_projections.json vets[i].war[0]` (the year-1 mean). A 2026-target projection could also be produced directly by the same engine (`fm.contract_war_path(hist, side, class_year=2026, ...)`) — that would be a new call, not new machinery.

**(c) Existing rest-of-season proration machinery — EXISTS in the fantasy module.** `fantasy_export.py:214-289` (`build_players`) is a complete ROS engine:
```python
frac = fp.season_fraction(league, cur)
remaining = max(0.0, 1.0 - frac)
in_prog = (cur, frac)
...
ros_pa = (proj.get("pt_proj") or 0) * remaining
```
(counting stats, not WAR — but the season-fraction × projected-full-season pattern is exactly the shape needed). Header spells it out: "ROS playing time = projected full-season PT × (1 − season_fraction)" (fantasy_export.py:17-18).

**(d) Season-fraction / remaining-schedule helpers — EXIST, two flavors.**
- League-PA-based: `fa_projection.season_fraction(league, season)` (fa_projection.py:644-651) — `cur_total_pa / prev_total_pa`, clamped [0.05, 1]; **returns 1.0 when either season's league PA is missing** (fa_projection.py:649-650), which is the safe degradation for a ROS leg built as `(1 − frac)` (missing data → remaining = 0, never an inflated remainder). Already imported and computed inside `_veteran_rows` (proj_export.py:253: `frac = fp.season_fraction(league, FIRST_SEASON - 1)`), so the fraction is available at the exact site where `_apply_contract` runs.
- Date/schedule-based (team level): `proj_current.remaining_schedule(season, today=...)` (proj_current.py:152-163) from the live StatsAPI schedule, with `balanced_remaining` fallback using `162 - gamesPlayed` (proj_export.py:1292-1297). Player-level fraction from this would be new code.

Note: nothing currently computes a per-player rest-of-season **WAR**; that leg is new code composed from (a)/(b)+(d).

**AP+ / pace lane is NOT usable here:** advancement pace is a prospect display metric contractually forbidden from model consumers (run_monthly.py:759-760: "Advancement Pace+ (W5, descriptive display ONLY - contract forbids any model consumer)").

## 3. Salary proration inputs (Spotrac)

`spotrac.py` `_parse_team_contract_table` (spotrac.py:314-409) emits per player:
`salary_usd` (current-year), `aav_usd`, `total_usd`, `salary_by_year` (dict {year: int$}), `years_remaining`, `signed_through`, `current_year` (spotrac.py:395-408). Crucially the page is "FUTURE-only — it shows current-year salary plus the remaining contract years" (spotrac.py:258-261), so **the 2026 salary IS in `salary_by_year` mid-season** — `_apply_contract` simply never reads it (`sal.get(season)` only for 2027+). `current_year = min(salary_by_year.keys())` (spotrac.py:393). The contract dict reaching proj_export additionally gets `team_code` (proj_export.py:1543-1547), and the join is the mlbam-resolved `_resolve_contracts` (proj_export.py:190-223).

**Service-time / arb status (inventory only):** no per-player observed service-time ingest exists anywhere (no `serviceTime` reads in fa_sources.py or any repo .py — grep returns nothing). What exists is *model-level* service-path machinery in value_framework.py: `service_time.{control_years, pre_arb_years, league_min_usd, arb_model.fractions_of_fa_value, arb_basis, super_two}` config (validated at value_framework.py:164-168; consumed at 1179-1246; value_framework_config.yaml), and — most relevant to a future pre-arb lane — `_remaining_path_surplus_usd(season_wars, start_k, super_two)` + `_remaining_bucket_sv_usd` / `_effective_remaining_bucket_sv` (value_framework.py:2062-2134), which already price surplus over a *remaining* control window from year `start_k` for debuted players (used by the eFV backgrade seam) and discount from NOW (first remaining season undiscounted — the opposite origin convention from surNpv, see §7.5). bayes_trade_value.py:4339-4342 explicitly registers pricing the `no_contract` (pre-arb) group as "a modelling decision, registered rather than smuggled in here."

## 4. Adjacent machinery

- **QO/comp-pick pricing exists:** `fa_market.qo_tax_usd(payor_tier, as_of)` (fa_market.py:1156-1184) prices forfeited picks in dollars off the realized draft-slot curve through `_slot_surplus_usd` → `vf._service_path_surplus_usd` (fa_market.py:1150-1153); wired into the FA meta payload per payor tier (`fa_export._qo_tax_block`, fa_export.py:727-743). This is the *signing-team* tax; a *comp-pick gain to the losing team* for an expiring star is not priced anywhere, but the slot→dollars machinery to build it exists (`data/draft_slot_curve.json` on disk; tools/fit_draft_slot_curve.py:31-34).
- **FA module — no double-count conflict:** the FA board prices the **next contract** for the winter-2027 class (`CLASS_YEAR = 2027`, fa_export.py:48) — value to the *signing* team from 2027 on. Rest-of-2026 control surplus accrues to the *current* team through season end; the two are disjoint in both season range and beneficiary. The current doctrine being overturned is written at bayes_trade_value.py:4334-4335: "A pending free agent is not a trade asset; the FA module prices him."
- **apply_platform_surplus** (bayes_trade_value.py:4095-4264): MLB rows re-point to `proj_sur[k] = r["surNpv"]/1e6` from `mlb_projections.json` vets+prospects (4121-4128, 4190-4191); vets absent from the prospect-derived board are *appended* from the same `proj_sur` (`_append_projection_only_rows`, 4267-4315 — the Judge fix). **Therefore a new value component that lands inside surNpv in proj_export flows to the trade board automatically with zero bayes_trade_value changes**; a component added anywhere else would need its own plumbing in both the re-point loop and the append path. Called from `export_trade_values_json` (bayes_trade_value.py:4408-4428). `_unpriced_vets` (4322-4362) classifies Minter as `reason: "expiring"` via `thru < proj["first_season"]` (4359) — once an expiring vet carries surNpv he leaves this list automatically (4350: skips rows with `surNpv is not None`).
- **trademachine.js:** MLB assets are added with `mm: d.proj.surNpv / 1e6` from `mlb_player_detail.json` (assets/trademachine.js:163-164, 187-191); board rows display `trade_value_mm` (assets/trademachine.js:457, 463, 730, 837). `mlb_player_export.py` copies `"sur", "surNpv"` into the detail sidecar (mlb_player_export.py:507-510). So there are THREE consuming surfaces, all downstream of the one proj_export field.

## 5. The consistency question (all vets vs expiring only)

- **The binding invariant** is `test_calibration_vintage.py:112-146`, `test_the_same_player_is_worth_the_same_on_every_surface`:
```python
if row.get("surplus_source") != "projection":
    continue          # eFV-sourced rows are a different basis by design
...
if abs(float(row["trade_value_mm"]) - v["surNpv"] / 1e6) > 0.15:
    mismatched.append(...)
```
  It pins trade board == `/projections/` **per player** (tolerance $0.15M) for every projection-sourced row. Consequence: rest-of-season surplus cannot be bolted onto the trade board alone; it must be added inside proj_export's surNpv (or equally to both). Once it is in surNpv, mechanically **every** vet with a 2026 salary on file gets it — Judge's 2026 remainder stacks on his $23.35M exactly like Minter's. An "expiring-only" carve-out would have to be implemented inside `_apply_contract` itself and would create a discontinuity (a vet signed through 2027 gets no 2026 credit while a vet through 2026 does) — no code enforces against that, but the artifact note (proj_export.py:1587: "veteran surplus only on salary-known (contracted) seasons") and `test_vet_surplus_only_on_contracted_seasons` (test_proj_export.py:123-131, requires `thru` whenever surNpv present) frame surplus as a uniform property of contracted seasons, not of a vet class.
- Vintage agreement across artifacts: `test_calibration_vintage.py:89-109` (the four artifacts in `_SURPLUS_ARTIFACTS` at :35-40 — xfv.json / trade_values.json / mlb_projections.json / timeseries.json — must share one calibration version; stamp written at proj_export.py:1573, verified present and equal in the served mlb_projections.json, trade_values.json and xfv.json: all `isotonic-real-v6-evframe-2026-07-31`).
- Tests that move if expiring vets become priced: `test_trade_board_coverage.py:132-147` documents "A.J. Minter is the canonical `expiring` case ... his absence from the VALUED board is correct" — the assertions themselves (reason ∈ {expiring, no_contract}; expiring ⇒ thru < first) stay green, but the docstring/owner rationale is inverted by this ask, and `coverage.unpriceable_expiring` (served today: 221 expiring of 581 unpriceable, alongside 360 no_contract, out of 1,321 vets / 740 priced / missing 0; computed at bayes_trade_value.py:4392-4404) will drop toward 0. `test_unpriceable_vets_are_published_with_a_reason` (test_trade_board_coverage.py:70-79) asserts the unpriced list is non-empty — survives via the 360 `no_contract` rows.

## 6. Regen/ship mechanics

- **Pipeline order (run_monthly.py):** `rebuild_only()` (run_monthly.py:556-849) runs the eFV regen (`efv_export.regen_all`, try-block at run_monthly.py:742-747) then GRPO (:820) then the bayes trade-values export (`export_trade_values_json`, block at run_monthly.py:826-849). Nightly chained daily: d9 `rebuild_only` (run_monthly.py:1396-1397) → d9b re-runs `proj_export.export()` AFTER the eFV regen (run_monthly.py:1399-1412) → d9b2 re-bakes `mlb_player_detail.json` (:1414+). Monthly step 6b is a deliberate SKIP ("6b SKIP: chained d9b re-exports mlb_projections post-regen", run_monthly.py:3341-3351). **Ordering defect to respect:** rebuild_only itself never runs proj_export, so within one d9 pass trade_values.json is exported against the *previous* mlb_projections.json, and d9b's re-bake lands *after* — on a night when surNpv changes semantically the board is one cycle behind `/projections/` until the next d9. This is exactly why memory records "basis change needs TWO export passes / run a --rebuild-only second pass by hand." The vintage test tolerates it only if the calibration version string is unchanged; the per-player test (§5) would flag >$0.15M drifts until the second pass.
- **value_framework.py:** this change should NOT need to touch value_framework.py (the vet leg lives in proj_export; the discount/dpw come from config reads). If the plan does touch it (e.g. a new helper), `python value_framework.py --emit-snapshots` must be re-run — `test_value_framework_integration.py:37-48` fails on snapshot drift ("re-run `python value_framework.py --emit-snapshots`"; `emit_snapshots` at value_framework.py:4062-4076, CLI flag at :4127).
- **efv_score.py:2066 P0 interplay:** the trade-value regen does **not** call `run_backgrade` directly, but its input artifact does: `efv_export.regen_all` calls `efv_score.run_backgrade(persist)` at efv_export.py:319, before the consolidating `run(persist)` at efv_export.py:340 that writes xfv.json. The P0 —
```python
if row.get("milb"):
    xfv_war = max(-2.0, a + b * _predict(ridge, feats))
    factors = _factors(ridge, feats, side=side)
    factors = _relabel_pace_factor(factors, r.get("milb"))   # efv_score.py:2066 — `r` is unbound (loop var is `rec`, dict is `row`)
```
— raises NameError on the first row with milb features (AST-verified: within `run_backgrade`, efv_score.py:1966-2238, the only non-comprehension occurrence of `r` is the load at 2066; the loop variable is `rec` at 2014 and the feature dict is `row`, whose `milb` key is set at 2060; the identical expression at efv_score.py:1713 is CORRECT there because `run_live`'s loop variable is `r`). `regen_all` dies inside rebuild_only's catch-all ("eFV regen crashed in rebuild_only — continuing", run_monthly.py:742-747), xfv.json is never rewritten, and the subsequent trade export prices prospects/backgrades off the **stale** xfv.json while surNpv-sourced vet rows update — a cross-vintage split the calibration tests exist to catch (undetected while the calibration version string happens to be unchanged). The plan must fix efv_score.py:2066 (`r` → `row`) before/with any regen it triggers.
- Calibration stamps: proj_export stamps `vf.calibration_stamp()` at proj_export.py:1573; trade_values.json carries its own; both currently `isotonic-real-v6-evframe-2026-07-31`.

## 7. Defects found (plan must fix / decide)

1. **(KNOWN P0, confirmed by AST scope analysis)** `efv_score.py:2066` — `r.get("milb")` NameError (`r` unbound in `run_backgrade`; should be `row`), kills `run_backgrade` → `regen_all` tail → xfv.json frozen silently under rebuild_only's broad except (run_monthly.py:742-747).
2. **FIRST_SEASON is a hardcoded rollover bomb** (proj_export.py:59): derived from nothing; at the 2026→2027 boundary every consumer (surNpv window, `fa_export.CLASS_YEAR=2027` at fa_export.py:48, the `_unpriced_vets` `expiring` classifier at bayes_trade_value.py:4359) requires a coordinated manual bump. Any rest-of-season feature adds a second date sensitivity (season fraction → 0 at season end must gracefully zero the new leg — note `season_fraction`'s missing-data fallback of 1.0 already zeroes `(1 − frac)` — and off-season Spotrac pages drop the played year from `salary_by_year`, spotrac.py:258-261).
3. **Spotrac `aav_usd` is mislabeled**: it is `total_usd // max(1, years_remaining)` over the FUTURE-only `salary_by_year` (spotrac.py:380-387), i.e. average *remaining* salary, not contract AAV — correct for uniform deals (Judge $40M) but wrong for back/front-loaded ones; it ships to the board as `aav_mm` (bayes_trade_value.py:4306-4312) and to `/projections/` as `aav` (proj_export.py:294-295). Adjacent, worth a registered note if salary proration starts leaning on it; the proration itself should use `salary_by_year[2026]`, which is genuine.
4. **`current_year`/`salary_usd` semantics** (spotrac.py:390-394): `min(salary_by_year)` is only "current" if the contract has already started; a future-start contract's `salary_usd` is its first future year. Harmless today (unused in surNpv) but a trap for a 2026-proration reading `salary_usd` instead of `salary_by_year.get(2026)`.
5. **Discount origin mismatch (design decision, currently latent):** surNpv discounts 2027 at t=0 — "present" = start of 2027. A 2026-remainder leg naively appended at t=-1 would be *inflated* by (1.07)^1; alternatively re-basing the whole NPV to today changes every served surNpv. (The eFV-side `_remaining_path_surplus_usd` already uses the discount-from-NOW convention, value_framework.py:2062-2066 — so the repo currently carries both conventions on different surfaces.) Either is defensible; the plan must pick one and say so (mid-season staleness of the served number is the flip side: surNpv is constant across the season while actual remaining control decays — the exact staleness the owner's ask surfaces).
6. **One-cycle artifact skew** (§6 ordering): trade_values exports (inside d9 rebuild_only) before the same night's d9b proj_export re-bake; a semantic surNpv change needs a deliberate second `--rebuild-only`/proj_export+trade re-export pass, or the per-player invariant test (test_calibration_vintage.py:112-146) will (correctly) fail in the interim.
7. **2026-only option years:** Spotrac's `salary_by_year` does not distinguish guaranteed vs option seasons (the parser reads only the year columns' data-export integers, spotrac.py:362-375); the FA module's option machinery (`fa_class.py:91-166`, `pending_option` status, Oct-Jan-gated heuristic per fa-module-state memory) is class-scoped and not consulted by `_apply_contract` — a vet whose 2027+ years are club options is priced as if guaranteed today; a rest-of-2026 leg inherits the same simplification (acceptable, but should be disclosed in the export notes like proj_export.py:1584-1590 do for other assumptions).
8. **Frontend array-shape constraint:** `war`/`sur` arrays are index-aligned to `first_season..+HORIZON-1` throughout assets/projections.js (e.g. `warAt`/`bandAt` at lines 157-181, `DATA.first_season + k` at 496) and consumed by season-offset logic in tests (test_proj_export.py:145-157 `_last_controlled_season`). The 2026 leg must ship as new scalar/field(s) (e.g. alongside `surNpv`, or folded into it) — inserting a sixth element into `sur`/`war` breaks every season-offset consumer.

### Verification log

Adversarial verification pass, 2026-08-01, on main = ab56f7b (clean tree). Every line cite, number, formula and quoted snippet opened and checked; arithmetic re-run live. Findings:

- **Reproduced §1 arithmetic exactly**: under the live config (active set `clemens_2026`, discount_rate 0.07, infl 0.0, flat 11,740,000, tiered {6.97, 8.76, 13.63}e6, kernel smoothed, `_winter_dpw(2027)` = 15,640,340.14), Judge's war path [4.43, 3.65, 2.64, 1.36, 0.25] at $40M/yr yields sur [40.4, 26.3, 7.9, -24.3, -37.7] and npv 23,350,804 — byte-identical to the served artifact. Minter served row confirmed (`thru: 2026`, no sur/surNpv keys).
- **Confirmed defect 1 (P0) by AST**: within `run_backgrade` (efv_score.py:1966-2238) there is NO non-comprehension binding of `r`; the sole load is line 2066. Loop var is `rec` (:2014), dict is `row` (`row["milb"]` set at :2060, guarded truthy at :2063). The look-alike at efv_score.py:1713 is legitimate (`run_live` loops `for r in live`). regen_all order confirmed: run_backgrade at efv_export.py:319 precedes the xfv.json-writing `run(persist)` at :340; the swallowing catch is run_monthly.py:742-747.
- **Confirmed defects 2-8** by reading the cited code: FIRST_SEASON hardcode (proj_export.py:59), CLASS_YEAR=2027 (fa_export.py:48), expiring classifier (bayes_trade_value.py:4359); `aav_usd = total_usd // max(1, years_remaining)` over future-only years (spotrac.py:380-387) shipped at bayes_trade_value.py:4310 and proj_export.py:294-295; `current_year = min(salary_by_year)` (spotrac.py:393); t=0-at-2027 discount origin (proj_export.py:309); rebuild_only contains no proj_export call, so the d9 trade export reads the prior night's mlb_projections.json and d9b (run_monthly.py:1399-1412) re-bakes after; option years indistinguishable in the parser (spotrac.py:362-375); projections.js index alignment (`warAt` :164-171, `DATA.first_season + k` :496). All 8 stand; none struck.
- **Served coverage verified** from trade_values.json: vets 1321, priced_vets 740, priced_on_board 740, missing 0, unpriceable 581 = 221 expiring + 360 no_contract. Calibration stamps equal across mlb_projections.json, trade_values.json, xfv.json (`isotonic-real-v6-evframe-2026-07-31`). (The code comment at bayes_trade_value.py:4251 says "325 of 1,319" — a 2026-08-01 measurement note; the served count is now 1,321.)
- **Corrections applied** (all minor cite precision, no claim reversed):
  1. fa_projection staleness-gate cite 113-133 → 113-154 (`CORPUS_TTL_DAYS = 3` at :130, `_corpus_stale_reason` :133-154).
  2. `qo_tax_usd` cite fa_market.py:1156-1176 → 1156-1184; routed via `_slot_surplus_usd` (fa_market.py:1150-1153) into `vf._service_path_surplus_usd`. `_qo_tax_block` 727-742 → 727-743.
  3. d9b cite run_monthly.py:1402-1412 → 1399-1412 (`_step` at :1407); d9 1396-1398 → 1396-1397.
  4. `build_players` cite fantasy_export.py:214-283 → 214-289 (function extends past 283; quoted lines verified at :221-223, :268).
  5. clemens_2026 discount cite 94-98 → 94-99 (net_rate :98, form :99).
  6. test_value_framework_integration cite 39-46 → 37-48; snapshot cite narrowed to `emit_snapshots` value_framework.py:4062-4076 + CLI :4127.
  7. mlb_player_export "sur","surNpv" cite 507-509 → 507-510. warPTH comment cite 434-435 → 434-436. test_proj_export `_last_controlled_season` cite 145-149 → 145-157. Doctrine quote cite 4334-4336 → 4334-4335. projections.js 157-178 → 157-181.
- **Material additions**:
  1. clemens_2026 sets `win_cost.disable_fa_implied: true` (clemens_2026.yaml:84; applied at valuation_sets.py:275-279), so the base config's fa_implied $/WAR re-anchor is OFF in production and the yaml tier table is served as-written (runtime `_fa_reanchor` = None — verified live). Without this the §1 "tier rates come from yaml:226-236" claim would be conditional.
  2. `season_fraction` returns 1.0 (not the 0.05 clamp) when league PA is missing (fa_projection.py:649-650) — the safe direction for a `(1 − frac)` ROS leg (missing data zeroes the remainder).
  3. `_remaining_path_surplus_usd` discounts from NOW (first remaining season undiscounted, value_framework.py:2063-2066) — the repo already carries the opposite discount-origin convention from surNpv, strengthening defect 5's "pick one and say so".
  4. xfv.json `realized_war` coverage quantified: 2,387 of 9,338 by_player entries.
  5. Flagged proj_export.py:31 module docstring's "platform 9%" as stale wording vs the production 7% (doc-only; the code reads config).
  6. `_SURPLUS_ARTIFACTS` map location pinned (test_calibration_vintage.py:35-40); coverage-split computation pinned (bayes_trade_value.py:4392-4404).
- **Claims verified with no change** (spot list): _apply_contract quoted verbatim (proj_export.py:283-312); `_season_value_usd` verbatim (:226-231); `_winter_dpw` (:234-242, call :1548); contract_war_path signature (fa_market.py:366-370); winter_dpw (fa_market.py:740-776); tiered_war_value_usd (value_framework.py:457-508); `_DEFAULT_VALUATION_SET` (value_framework.py:296-297); valuation_sets discount overlay (:285-298); spotrac FUTURE-only comment (:258-261) and emit dict (:395-408); `_resolve_contracts` (proj_export.py:190-223); team_code merge (:1543-1547); notes block (:1584-1590); AP+ contract comment (run_monthly.py:759-760); 6b SKIP (:3341-3351); apply_platform_surplus re-point (bayes_trade_value.py:4121-4128, 4190-4191), append path (4267-4315), `_unpriced_vets` (4322-4362, skip at 4350, classifier at 4359), export entry (4408-4428); invariant test quoted verbatim with $0.15M tolerance (test_calibration_vintage.py:112-146); vintage test (:89-109); test_vet_surplus_only_on_contracted_seasons (test_proj_export.py:123-131); Minter docstring (test_trade_board_coverage.py:132-147); non-empty unpriced assertion (:70-79); trademachine.js cites (163-164, 187-191, 457, 463, 730, 837); no `serviceTime` ingest anywhere (repo-wide grep empty); data/draft_slot_curve.json and data/fa_dpw_series.json both on disk.
