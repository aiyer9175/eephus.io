# Base-Config & Engine Verification (Prompt B)

**Scope.** The CORE surplus-value config + engine that every later block extends:
outcome buckets, P(bucket|FV) tables, the FV→WAR anchor, tiered $/WAR, discount
rate, the arbitration model, and the continuous-FV fit. Files:
`prospect-tracker/value_framework_config.yaml` (the single editable source of
truth), `prospect-tracker/value_framework.py` (the engine), and the generated
`prospect-tracker/data/value_framework_fitted.json` (fit output).

**Method.** Static trace + numeric verification (every number below was produced
by running the engine), plus a `--fit` reproduction and live perturbations.

**Verdict.** The base layer is **structurally and numerically sound.** Transform-
first wiring, average-not-peak reconciliation, monotonicity/continuity, and the
single-source-of-truth property all hold. **One structural gap was fixed**
(no config validation → added loud `ConfigError`). **No core value deviates from
the reference**, so nothing in the base config required a value change. A handful
of by-design items and two out-of-$-path parallel tables are **flagged** below for
your awareness, not overwritten.

---

## Fixes applied (structural / wiring / invariant)

| # | Fix | Where | Why |
|---|---|---|---|
| F1 | **Added loud config validation** — `ConfigError`, `_cfg_require`, `_validate_config`, called inside `_config()` | `value_framework.py:90-189` | Part 2: a missing/malformed CORE key now fails at load with a precise message (`missing required key: dollars_per_war.flat`, `discount_rate: expected a number in [0.0, 1.0]…`) instead of `KeyError` deep in a calc or a silent `.get()` default. |
| F2 | **Added base-config regression suite** (39 tests) | `test_config_base_verification.py` | Locks every invariant + reference value below so a future edit can't silently break them (a value retune trips a test = the "flag for confirmation" gate). |

No wiring/invariant **bugs** were found to fix — §4, §5, §6 below all passed as
built. The validation gap (§2) was the only structural defect.

---

## 1. Single source of truth

**Engine is clean.** A literal sweep of `value_framework.py` for the reference
numbers (`6.74 / 8.51 / 12.84 / 11.23 / 0.09 / 0.85 / arb fractions`) found **zero
hardcoded core values** — every core parameter is read from `_config()`. Core keys
use direct indexing (`_config()["discount_rate"]`, `cfg["dollars_per_war"]["tiered"]`,
`cfg["service_time"]…`) which fails loudly if missing; the `.get(key, default)`
fallbacks are confined to **optional/secondary** params (distribution draw counts,
aging sub-rates, bayes knobs, source-disagreement), which is acceptable belt-and-
suspenders, now backstopped by §2 validation for the core.

**The frontend gets the constants from the snapshot, not copies.** `fvToAvgWar()`
(`index.html:8596`) reads `window.VALUE_FRAMEWORK.fv_to_6yr_avg_war`; the surplus
dollars come from the precomputed `sv_curve` in the same snapshot. Good.

**🚩 Flagged duplications (outside the surplus-$ path — not base-engine bugs):**

- **`storage.py:3163` `FV_EXPECTED_WAR`** — a *career*-WAR FV table (e.g. 50→3.0,
  60→12.0) used for development-credit / WAG scoring, a **different quantity** from
  the engine's per-season WAR. Not in the dollar path (audit FLAG 15). Left as-is.
- **`index.html:16371` `FV_WAR_ANCHORS`** — a hardcoded JS table of FanGraphs
  *lower-bound* WAR/yr, used only by `fvExpectedWarPerYr()` for "actual − expected
  WAR" overlays (`index.html:16802`), **not** the surplus figure (which uses the
  snapshot `sv_curve`). It is a hardcoded copy of primer numbers that could drift
  from the config and is a *different* FV→WAR notion (lower-bound, not average).

- **Soft in-config duplication:** `buckets.<b>.midpoint_war` (`1.0/2.0/3.2/5.0`) and
  `fit.midpoint_priors` (`[1.0, 2.0, 3.2, 5.0]`) hold the same seed numbers in two
  keys (a seed fallback vs. the calibration ridge target). They are independent
  knobs that happen to coincide — **keep in sync** if you retune one.

> Fixing the two JS/storage parallel tables is a frontend/storage behavior change
> outside this base-config scope, so they are flagged, not changed.

## 2. Schema & types — **validation added (was absent)**

Before this pass `_config()` did a bare `yaml.safe_load` with **no validation**: a
missing core key surfaced as a cryptic `KeyError` mid-calculation, and several
reads silently defaulted. **Fix F1** adds `_validate_config()` (run at load) that
checks presence + type + range of every core block and raises `ConfigError` with a
precise path. Verified it accepts the real config and rejects: missing
`discount_rate`, out-of-range `discount_rate=9.0`, negative `2plus` rate,
non-ascending breakpoints, wrong `buckets.order`, missing `dollars_per_war.flat`, a
P(bucket) row missing a bucket, missing `fv_to_6yr_avg_war`, missing
`service_time.control_years`. Optional keys intentionally keep `.get(default)`.

## 3. Value sanity vs reference — **no deviations**

Every reference value matches the config exactly; **nothing to flag for change.**

| Reference | Expected | Config | ✓ |
|---|---|---|---|
| Bucket bands | bust <0.5 / bench 0.5-1.5 / regular 1.5-2.5 / good 2.5-4.0 / star 4.0+ | identical | ✓ |
| FV→WAR anchor (AVERAGE) | 50→2.0, 55→2.5, 60→3.0 | `fv_to_6yr_avg_war` 2.0 / 2.5 / 3.0 | ✓ |
| Tiered $/WAR | 6.74 / 8.51 / 12.84 M | `rates` 6.74e6 / 8.51e6 / 12.84e6 | ✓ |
| Flat $/WAR | 11.23 M | `dollars_per_war.flat` 11.23e6 | ✓ |
| Discount rate | ~0.09 | `discount_rate` 0.09 | ✓ |
| Projection haircut | ~0.85 | `projection_haircut.value` 0.85 (`apply:false`, by design) | ✓ |
| "+" grades | 45+ →47.5, 40+ →42.5 | `plus_grade_axis` / `fit.role_axes` 47.5, 42.5 | ✓ |

**By-design notes (informational, not overwritten):**
- The **calibrated** bucket midpoints (hitter `2.15/2.75/3.35/4.75`, pitcher
  `2.33/2.93/3.64/5.02`) sit *above* the Clemens band centers. This is intended:
  with bust pinned at 0 WAR, reconciling the bust-inclusive mixture to the primer
  average forces the surviving buckets up. The bands are outcome *shape*; the
  midpoints are the primer-reconciled *levels* (documented in the config).
- The seed `midpoint_war` values (`1.0/2.0/3.2/5.0`) are priors only; the engine
  reads the calibrated values from the fitted file.

## 4. Invariants — all hold (tests added)

| Invariant | Result |
|---|---|
| Training P(bucket\|FV) rows sum to 1 (±0.02) | ✓ — most exactly 1.000; hitter `45+`, hitter `55`, pitcher `55` = **1.010** (Clemens published rounding; within tol). **Not overwritten** — editing published cells would corrupt the source; the runtime renormalizes. |
| **Fitted curve** rows sum to 1 | ✓ exactly (`_normalize_clip`) |
| Monotone: bust↓, star↑ over FV 35–70 | ✓ both roles (proportional-odds guarantees it even though the *raw* cells are noisily non-monotone — that is the point of fitting a monotone model) |
| Fit reproduces grid cells | within bound — max \|fit−cell\| **0.123** hitter (`45+` bust: cell .52 vs fit .397, the non-monotone bump the model must smooth) and **0.196** pitcher (`60` good, n=12 thin cell shrunk by hierarchical pooling). Bounded by a regression test at ≤0.25. |
| No discontinuity at grade boundaries (54→55→56, etc.) | ✓ max 1-FV step ≈ 0.03–0.044 across 44/45, 49/50, 54/55, 59/60 |
| `45+` resolves to 47.5 (not 45/50 or a string) | ✓ `fit.role_axes["45+"] = 47.5`; runtime evaluates the smooth curve at 47.5 |

## 5. Average-not-peak reconciliation — passes at named targets

Live `expected_six_year_avg_war` (= Σ P(bucket\|FV)·calibrated_midpoint) vs the
`fv_to_6yr_avg_war` anchor (tolerance `reconcile_tol = 0.15`):

| FV | hitter wavg | resid | pitcher wavg | resid |
|---|---|---|---|---|
| 45 | 1.292 | −0.208 ⚠ | 1.346 | −0.154 ⚠ |
| **50** | 1.937 | **−0.063** ✓ | 1.963 | **−0.037** ✓ |
| **55** | 2.531 | **+0.031** ✓ | 2.529 | **+0.029** ✓ |
| **60** | 3.030 | **+0.030** ✓ | 2.989 | **−0.011** ✓ |

The required targets (50/55/60) reconcile well inside tolerance — confirming the
WAR levels are AVERAGE, not peak, and the calibration scalar is correct. ⚠ **FV 45
is looser by design** and not a named target: it sits at the Edwards low-tier
bridge (FV ≤ 45), where the direct dollar anchor — not the bucket mixture — governs
valuation. (Informational, no fix.)

`--fit` was re-run from the config to a temp path and **reproduced the committed
`fitted.json`** (slopes and calibrated midpoints match to 1e-3), confirming the
fit is deterministic and config-driven. The committed file was left untouched.

## 6. Transform-first wiring (no Jensen collapse)

Traced `expected_surplus_usd → _pipeline_surplus_from_svs → _bucket_sv_usd →
_service_path_surplus_usd → tiered_war_value_usd`:

- **Per-bucket, per-season tiering.** `_service_path_surplus_usd` loops seasons and
  calls `tiered_war_value_usd(war)` on **each season's own WAR**
  (`value_framework.py:690-691`); buckets are aggregated **last** via
  `Σ_b P(b|FV)·bucket_SV` (`:837-838`). The convex $/WAR is never applied to a
  blended/averaged WAR. (`point_estimate_surplus_usd` is the explicit *collapsed*
  comparator E[f(X)]≠f(E[X]), clearly marked not-production.)
- **Discounting.** Each season grows by `$/WAR` inflation and discounts at
  `discount_rate`, netted to `((1+infl)/(1+r))^(eta+t)` (`:686-698`). Future years
  are discounted.
- **Arbitration is WAR-adaptive per year**, not a fixed dollar shift: pre-arb =
  `league_min`; arb years = `fraction × tiered_war_value_usd(that season's WAR)`
  (`:692-697`), super-two blended.
- **No double position multiplier.** `position_multiplier` returns **1.0** unless
  `position.apply_market_scarcity` (off); WAR already embeds the positional
  adjustment. Relievers are handled by a **WAR-input** normalization
  (`_reliever_level`), not a $ multiplier. Verified `SV(SS)=SV(1B)=SV(None)` for an
  identical hitter. (These are the audit's FLAG 5/6/7/8, now resolved.)

## 7. Config is live (perturbation)

In-memory perturbation of the **runtime** layer (derived caches cleared; config
restored after each — verified the baseline `SV(FV55 SS)=$119.5M` returns):

| Perturbation | SV(FV55 SS) | Expectation | ✓ |
|---|---|---|---|
| baseline | $119.5M | — | — |
| `2plus` $/WAR ×1.2 | $143.3M | rises | ✓ |
| all tiers ×1.10 | $131.6M (ratio 1.101) | ~proportional | ✓ |
| `discount_rate` 0.09→0.15 | $108.5M | falls | ✓ |
| `league_min` 0.76M→5M | $109.8M | falls | ✓ |
| `eta_years=3` | $106.8M | falls (extra discount) | ✓ |
| FV 50→55→60 | bust 0.299→0.151→0.069; star 0.025→0.058→0.129 | weights shift smoothly | ✓ |

**Two-layer liveness (documented design):** the **dollar/timing** layer
($/WAR, discount, arb, anchor, aging) is live at runtime. The **probability/level**
layer (`p_bucket_given_fv_*` tables, `fv_to_6yr_avg_war`, bucket bands) feeds the
**`--fit`** step and is read at runtime from `fitted.json` — so a "widen a bucket
band / move an anchor" perturbation moves outputs **after `--fit`**, not before.
Demonstrated: perturbing the FV50 anchor 2.0→3.0 and re-fitting shifted the hitter
calibrated midpoints `[2.15, 2.75, 3.35, 4.75] → [2.54, 3.14, 3.74, 4.34]`. This is
intentional (the spec ships a precomputed fit) and is now documented so it is not
mistaken for a stale hardcode.

## 8. Doc ↔ implementation

- **Glossary (Prompt C, `index.html`)** matches the implementation:
  - `fv_to_war_table` entry: *"FanGraphs FV → six-year AVERAGE annual WAR — NOT a
    peak… used only to calibrate the outcome-bucket WAR levels; nothing in the
    model reads it as a peak projection."* (`index.html:21430`) — exactly the
    implemented role of `fv_to_6yr_avg_war`.
  - `surplus_value` / `value_framework` entries: *"career-path mixture model… Σ_b
    P(bucket\|FV) × Σ_season[ tiered_$/WAR(WAR) − salary ], discounted; busts
    floored at $0"* (`:21378`, `:21414`) — matches the transform-first pipeline.
  - Vet path: *"realized career WAR × $/WAR_overall (≈ $11.23M)"* — matches flat.
- **Audit (Prompt A, `docs/sv-audit.md`)** describes the **old v1** model; its
  headline fixes are in place in v2: peak→**average** (FLAG 1/2/3 → `fv_to_6yr_avg_war`
  + calibrated midpoints, no ramp/`p_success` double-discount), PV discount + $/WAR
  inflation added (FLAG 4), per-season tiering (FLAG 5), and position multiplier
  defaulted to 1.0 with relievers handled via WAR normalization (FLAG 6/7/8).

No doc↔implementation drift found in the base layer.

---

## Items flagged for your confirmation (none overwritten)

1. **Training-cell rounding:** hitter `45+`/`55`, pitcher `55` rows sum to 1.010
   (Clemens published rounding). Within tolerance; runtime renormalizes. Leave, or
   renormalize the published cells? (Recommend: leave — they're the cited source.)
2. **FV 45 reconciliation** residual −0.21 (hitter) / −0.15 (pitcher), outside the
   0.15 tol but **not a named target** (governed by the Edwards bridge at FV ≤ 45).
   Confirm this is acceptable (it is, by design) or tighten the bridge.
3. **Two parallel FV→WAR tables outside the $ path** — `storage.FV_EXPECTED_WAR`
   (career WAR, dev-credit) and `index.html FV_WAR_ANCHORS` (primer lower bound,
   WAR overlays). Not bugs in the surplus path; flagged for single-source hygiene.
4. **`midpoint_war` vs `fit.midpoint_priors`** hold the same seed numbers in two
   keys — keep in sync on any retune.

## Tests

`test_config_base_verification.py` — 39 tests, all passing: validation
accept/reject, reference-value pins, row-sum/monotonicity/continuity/`45+`
invariants, named-target reconciliation, transform-first + no-double-position, and
the live perturbations. Full SV-engine suite green after the changes.
