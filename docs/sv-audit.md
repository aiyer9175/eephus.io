# Surplus-Value (SV) Pipeline Audit — As-Built

**Status:** Read-only audit. No code was modified. This is a faithful description of
what the code *currently does*, with file/line references, to be verified before any
refactor. Where the code's intent is ambiguous or a step looks double-counted, it is
**flagged** rather than guessed.

**Scope of the trace:** every file/function that turns a prospect's Future Value (FV)
into a surplus-value dollar figure. The mechanism lives almost entirely in one module;
the rest of the repo either calls it, mirrors it, or re-implements a piece of it.

All line numbers are against the repo as audited (commit `d870b88`). Paths are relative
to the repo root.

---

## 0. Pipeline map — who computes SV, and from what

The canonical formula lives in **one** module and is consumed by four production
surfaces (plus tests and one upstream calibration tool).

| Surface | File | How it gets SV | Re-implements? |
|---|---|---|---|
| **Source of truth** | `prospect-tracker/value_framework.py` | defines `surplus_value_mm()` and all constants | — |
| **Backend / org tree** | `prospect-tracker/storage.py` | imports & calls `surplus_value_mm` (aliased `_estimate_surplus_mm`) | one inline vet-WAR line; keeps its *own* FV→WAR career table for a different purpose |
| **Frontend (all cards/trees/audits)** | `prospect-tracker/index.html` | **re-implements the formula in JS** (`estimateSurplusValueMM`), reading scalar constants from the emitted snapshot | yes — JS mirror + a stale divergent `_SUR_TABLE` |
| **Veteran trade value** | `prospect-tracker/mlb_trade_lookup.py` | separate `_compute_surplus()`; borrows only the `$/WAR` tier rate | yes — a *different* (contract) surplus definition |
| Contract parsing | `prospect-tracker/spotrac.py` | no FV→$ math (parses contracts only) | n/a |
| Trade detection | `prospect-tracker/trades.py` | no FV→$ math (detects trades only) | n/a |
| Position-mult producer | `prospect-tracker/tools/calibrate_position_mults.py` | *upstream*: writes `data/position_multipliers.json` that `value_framework` reads | n/a |

A repo-wide sweep (`run_monthly.py`, `consensus.py`, `draft_export.py`, `eta.py`,
`spotlights.py`, `scrapers.py`, `ifa_export.py`, `overseas_export.py`, `mock-draft/*.js`,
root `*.py`) found **no other production consumers**. `run_monthly.py` touches only
storage's `career_war` *storage* helpers (persisting realized WAR), not any FV→$
conversion. `fangraphs_csv.py` defines an unrelated `_build_snapshot()` (a scouting
dataclass builder) — a name collision with `value_framework.build_snapshot()`, not a
valuation consumer.

The emitted snapshot (`data/value_framework.json` + `data/value_framework.js`, written by
`value_framework.emit_snapshots()`) carries the constants to the frontend as
`window.VALUE_FRAMEWORK`.

---

## The canonical formula (the spine everything else mirrors)

`surplus_value_mm()` — `prospect-tracker/value_framework.py:358-399`. Exact order of
operations as written:

```
1.  war_peak = fv_to_war_peak(fv, is_pitcher)          # line 380   (interpolated)
2.  if war_peak is None:        return None            # line 381-382
3.  if war_peak <= 0:           return 0.3             # line 383-385  (FV 20–30 floor)
4.  p     = success_prob(fv, is_pitcher)               # line 386   (interpolated)
5.  ramp  = 0.78 hitter / 0.72 pitcher                 # line 387
6.  rate  = dollars_per_war(war_peak)                  # line 388   (tier picked by war_peak)
7.  expected_war_6yr = war_peak * 6.0 * ramp * p       # line 390
8.  gross            = expected_war_6yr * rate         # line 391
9.  arb_cost  = 3.0 * war_peak * rate * 0.60 * ramp * p # line 392
10. cost_basis = 2.4 + arb_cost                        # line 393   (2.4 = pre-arb fixed)
11. surplus    = gross - cost_basis                    # line 395
12. if apply_position_mult: surplus *= position_multiplier(position)  # line 396-397
13. return round(max(0.3, surplus), 1)                 # line 399   (floor AFTER pos mult)
```

Two order-of-operations facts matter because the function is non-linear:

- **The `$/WAR` tier is chosen once, from `war_peak`** (step 6), and that single rate is
  applied to *both* the 6-year gross (step 8) and the arb cost (step 9). It is not a
  per-year tier.
- **The position multiplier multiplies the *net* surplus** `(gross − cost_basis)`
  (step 12), so it scales the cost-basis subtraction as well as the value, and it is
  applied *before* the `max(0.3, …)` floor (step 13).

---

## 1. FV → WAR

**What quantity does each FV map to?** The code treats the FV→WAR number as a
**single-season PEAK WAR/yr** figure.

- Source numbers: the FanGraphs scouting-primer `(low, high)` WAR ranges per FV grade,
  split by role — `_PRIMER_RANGE_HITTER` (`value_framework.py:128-137`) and
  `_PRIMER_RANGE_PITCHER` (`value_framework.py:139-147`).
- Reduction: the **midpoint** of each range, `_midpoint()` (`value_framework.py:150-151`),
  built into `FV_TO_WAR_HITTER` / `FV_TO_WAR_PITCHER` by `_build_fv_to_war()`
  (`value_framework.py:154-173`).
- The code's own words, `value_framework.py:122-123`:
  *"For valuation purposes we use the MIDPOINT as the peak-year projection."* The function
  is named `fv_to_war_peak` (`value_framework.py:176`), the variable is `war_peak`, and the
  docstring says *"FV grade -> projected **peak** WAR/yr."*

Resulting grid (from the emitted snapshot `data/value_framework.json`):

| FV | 40 | 45 | 50 | 55 | 60 | 65 | 70 | 75 | 80 |
|---|---|---|---|---|---|---|---|---|---|
| hitter peak WAR | 0.35 | 1.15 | 2.0 | 2.9 | 4.15 | 5.08 | 6.0 | 7.0 | 8.0 |
| pitcher peak WAR | 0.45 | 1.35 | 2.15 | 3.0 | 4.2 | 5.1 | 6.0 | 7.0 | 8.0 |

> ### 🚩 FLAG 1 (HIGH, conceptual) — "peak" vs "average-annual" interpretation
> The reviewer's belief is well-supported by the code's own behavior. The FanGraphs
> primer presents its FV→WAR bands as **average annual WAR over the first six controlled
> years**, not peak. The primer's own example: **Sonny Gray peaked at 3.8 WAR yet is a
> 60 FV** — and this code maps a 60-FV pitcher to **4.2 "peak" WAR**
> (`value_framework.py:145`, midpoint of 3.5–4.9). A band midpoint (4.2) that *exceeds* a
> real 60-FV pitcher's actual career peak (3.8) is only coherent if the band is an
> average-annual / talent-level figure — **not** a peak. So the code appears to mislabel
> an average-annual quantity as "peak."
>
> This is not cosmetic: the "peak" label is what justifies the `ramp` discount in §2.
> If the primer numbers are already average-annual, the ramp double-discounts (see §2).

---

## 2. The `ramp` variable

- **Definition / values:** `RAMP_FACTOR_HITTER = 0.78`, `RAMP_FACTOR_PITCHER = 0.72`
  (`value_framework.py:247-248`). Documented as *"Avg WAR / peak WAR over the 6yr
  cost-controlled window"* (`value_framework.py:245-246`).
- **How applied to WAR:** as a flat scalar in two places —
  - `expected_war_6yr = war_peak * 6.0 * ramp * p` (`value_framework.py:390`)
  - `arb_cost = 3.0 * war_peak * rate * 0.60 * ramp * p` (`value_framework.py:392`)
  So it multiplies the per-year peak WAR everywhere a WAR quantity is used.
- **Derived vs assumed:** **assumed/hand-tuned.** The comment (`value_framework.py:246-249`)
  says it is *"Tuned so a top prospect's expected 6yr WAR roughly matches the primer's
  '5-7 WAR/yr at peak' framing."* There is no data derivation; it is a reverse-engineered
  fudge factor selected to make the output land in a target range.

> ### 🚩 FLAG 2 (HIGH, conceptual) — ramp double-discounts if §1 is average-annual
> `ramp` converts a *peak* figure into a 6-year *average*. That is only a valid operation
> if the input is genuinely peak. If FLAG 1 is correct and the primer numbers are already
> average-annual, applying `0.78`/`0.72` on top is a **spurious second discount** of
> 22–28%. Either §1's numbers are peak (then `ramp` is right but §1's source is being
> used against its documented meaning), or they are average-annual (then `ramp` should be
> ~1.0). The code currently has it both ways: it sources average-annual primer values,
> *labels* them peak, and *ramps* them as if peak.

---

## 3. `p_success`

- **Where defined:** `success_prob()` (`value_framework.py:220-237`), backed by
  `BUST_PROB_HITTER` / `BUST_PROB_PITCHER` (`value_framework.py:208-217`).
- **What it means:** documented as **P(MLB regular | FV)**, where "MLB regular" is defined
  as *accumulating ≥ 2 career WAR* (`value_framework.py:201-206`). Pitchers run lower at
  each grade (TJ + role-conversion risk). Linear-interpolated between 5-pt anchors, floor
  0.005, cap 0.95 (`value_framework.py:237`).
- **Exactly how it multiplies in:** `p` enters as a flat multiplier in **both** the value
  and the cost terms:
  - `expected_war_6yr = war_peak * 6.0 * ramp * p` (`value_framework.py:390`)
  - `arb_cost = 3.0 * war_peak * rate * 0.60 * ramp * p` (`value_framework.py:392`)

So a prospect's entire WAR output (and the arb cost it would generate) is scaled by the
probability it becomes a ≥2-WAR regular.

> ### 🚩 FLAG 3 (HIGH, conceptual) — possible double-count of bust risk against §1
> `war_peak` comes from the primer's FV→WAR band. If that band is the *expected*
> (probability-blended) WAR for a player of that FV — which is the standard reading of the
> primer's tiers — then it **already embeds** the chance of busting. Multiplying it again
> by `p_success` (an explicit bust haircut) discounts for the same risk twice. The code is
> only self-consistent if `war_peak` is the WAR *conditional on becoming a regular* and
> `p_success` is the probability of reaching that state — but nothing in §1 establishes
> that conditioning, and the primer's framing argues against it. Combined with FLAG 2, the
> WAR term may carry **two stacked discounts** (`ramp` and `p_success`) that are each only
> conditionally justified.

---

## 4. `$/WAR`

- **Tiered, non-linear, 3-tier.** `dollars_per_war()` (`value_framework.py:91-108`) picks
  among three tiers by projected WAR: `<1.0 → "0-1"`, `1.0–2.0 → "1-2"`, `≥2.0 → "2+"`.
  The module deliberately rejects a flat rate (`value_framework.py:12-18`) to capture the
  "star premium." A flat `dollars_per_war_flat()` (overall mean) also exists
  (`value_framework.py:111-116`) and is used only for career-WAR vet valuation (§ below).
- **Tier rates:** a **rolling 3-year average of 2024–2026** (`DEFAULT_WINDOW_YEARS`,
  `value_framework.py:68`) over `_DPW_BY_YEAR` (`value_framework.py:54-63`), averaged by
  `dollars_per_war_for_window()` (`value_framework.py:71-84`). Default tiers (from the
  snapshot): `0-1 = $6.973M`, `1-2 = $8.763M`, `2+ = $13.627M`, `overall = $11.743M`.
- **Applied to a single averaged WAR figure, not per-year.** The tier is chosen once from
  `war_peak` (`value_framework.py:388`), and that one rate multiplies the entire
  `expected_war_6yr` aggregate (`value_framework.py:391`). Individual years are never
  re-tiered.
- **Inflation by year?** **No.** There is no annual escalation of `$/WAR`.
- **Present-value discounting?** **No.** Six years of future surplus are summed at face
  value; no discount rate is applied anywhere.

> ### 🚩 FLAG 4 (MEDIUM) — no PV discount AND no $/WAR inflation
> The model sums six future years of value at a single, current, nominal rate. It neither
> discounts future dollars to present value nor inflates `$/WAR` over the window. The two
> omissions push in opposite directions and *partially* offset, but neither is modeled
> explicitly, so the net bias is unquantified and tied to whatever the current 3-yr `$/WAR`
> window happens to be.
>
> ### 🚩 FLAG 5 (LOW) — tier dispatched on `war_peak`, which is a ramped/peak number
> The tier boundary check uses `war_peak` (the un-ramped, un-bust-adjusted peak), while the
> WAR being *priced* is `expected_war_6yr` (ramped × bust). A prospect whose peak is 2.1
> (→ "2+" star tier) but whose *expected* per-year WAR after ramp×p is ~0.5 is still priced
> at the star rate. Tier selection and the quantity being priced use different WAR
> definitions.

---

## 5. Arbitration

The cost basis has two parts (`value_framework.py:393`, `cost_basis = 2.4 + arb_cost`):

- **Pre-arb: a fixed dollar shift.** `PRE_ARB_TOTAL_MM = 2.4` (`value_framework.py:251`) =
  3 years × ~MLB minimum. It does **not** scale with WAR.
- **Arb: percentage *and* performance-based.** `ARB_PCT_OF_FA = 0.60`
  (`value_framework.py:255`), documented as a single blended average across the 3 arb years
  (Arb1 ≈ 40% / Arb2 ≈ 60% / Arb3 ≈ 80% of FA value → one 0.60).
  `arb_cost = 3.0 * war_peak * rate * 0.60 * ramp * p` (`value_framework.py:392`).
  - It **scales with projected WAR** (`war_peak`), with the same `$/WAR` tier `rate`, and
    with the same `ramp` and `p_success` haircuts as the gross value. So arb cost is "3
    arb-years of the player's ramped, bust-adjusted WAR, paid at 60% of free-agent value."
  - There is no per-year arb escalation; it is 3 × (one blended 60%).

> ### 🚩 FLAG 6 (LOW–MEDIUM) — position multiplier scales the cost basis too
> Because the position multiplier is applied to `(gross − cost_basis)` (step 12 above), a
> premium position (e.g. SS ×1.18) multiplies not just the player's value but also the
> pre-arb + arb cost being subtracted. A SS and a 1B with identical projected WAR are
> modeled as having *different* arb/pre-arb costs purely because of position, which is not
> how arb actually works. This is a side effect of multiplying the net rather than the
> gross.

---

## 6. Positional adjustment

- **Where it enters:** the very last value step. `surplus *= position_multiplier(position)`
  (`value_framework.py:396-397`), `position_multiplier()` defined at
  `value_framework.py:333-342`.
- **Values:** `_POSITION_MULT_DEFAULTS` (`value_framework.py:293-313`), optionally
  overridden by `data/position_multipliers.json` if present
  (`_load_position_mult_overrides`, `value_framework.py:318-330`). **No override file is
  present**, so defaults are live: e.g. `SS 1.18`, `CF 1.05`, `C 0.95`, `2B 0.88`,
  `1B 0.70`, `OF 0.65`, `DH 0.78`; pitchers `SP/RHP 1.00`, `LHP 1.04`, `RP 0.55`,
  `MIRP 0.75`, `SIRP 0.65`. These are **market-AAV-derived scarcity priors**, hand-curated
  from `tools/calibrate_position_mults.py` output (the comment block at
  `value_framework.py:260-292` explains which were validated, raised, or rejected as
  star-biased).

> ### 🚩 FLAG 7 (MEDIUM–HIGH, conceptual) — positional value is already inside WAR
> WAR includes a defensive **positional adjustment by construction** (a SS earns more WAR
> than a 1B for the same raw performance). The pipeline derives surplus from that WAR and
> then multiplies by an *additional* position multiplier. The code defends this as a
> distinct *market-scarcity* premium ("what teams pay per position") rather than the on-field
> positional adjustment — but the multipliers were **calibrated from per-position AAV
> medians** (`value_framework.py:260-272`), and AAV already reflects the WAR those players
> produce (which already contains the positional adjustment). So calibrating off AAV and
> re-applying to a WAR-derived value risks **re-introducing the positional signal that is
> already in WAR** — a partial double-count, upward for premium spots (SS ×1.18) and
> downward for 1B/OF.
>
> ### 🚩 FLAG 8 (MEDIUM, conceptual) — relievers are discounted twice
> The module comment claims SP/RP are differentiated *only* via the `$/WAR` WAR-tier rate
> "no need to double-count" (`value_framework.py:286-288`). But relievers also get a sub-1.0
> position multiplier (`RP 0.55`, `SIRP 0.65`, `MIRP 0.75`). A reliever therefore takes a
> low WAR (→ low tier rate) **and** a sub-1.0 position multiplier — exactly the double-count
> the comment says is avoided.

---

## 7. Continuous (non-grid) FV handling

- **The system carries continuous FVs.** Backend valuation reads
  `latest.consensus_fv_raw` — the continuous pre-snap FV (e.g. `47.5`, `58.33`), rounded to
  2 decimals in `consensus.py` — **not** the snapped grade `consensus_fv` /
  `consensus_fv_label` (`storage.py:7193, 7430`). Trade events store `round(fv_now, 1)`
  (`storage.py:5050, 5055`). So FV is never snapped to a 5-pt grade before valuation.
- **Non-grid FV does not round and does not break.** Both lookup functions **linearly
  interpolate between 5-pt anchors**:
  - `fv_to_war_peak` (`value_framework.py:193-196`): `lo = int(f//5)*5; t = (f-lo)/5; …`
  - `success_prob` (`value_framework.py:234-237`): same interpolation pattern.
  Clamps: `f ≥ 80 → 80`, `f ≤ 20 → 20`.
- **The grade *tables* have only 5-pt keys, but they are never indexed by a raw FV for live
  valuation** — the *functions* interpolate, and that's what every consumer calls. The
  precomputed `surplus_value_mm` table in the snapshot (keys `"20"…"80"`) is **dead** in the
  frontend (see FLAG 11).
- **Subtlety — the SV-vs-FV curve is continuous but kinked.** Because the `$/WAR` tier is
  chosen from `war_peak`, the surplus curve has kinks at the FVs where `war_peak` crosses
  1.0 and 2.0. `test_value_framework_integration.py` even asserts that FV 47 surplus sits
  *below* a naive FV45→FV50 interpolation, because its `war_peak ≈ 1.49` keeps it on the
  cheaper "1-2" tier. So "continuous" ≠ "smooth/linear."

---

## Consumer-level divergences (the "every file" part)

These are places where a consumer's number can differ from what `surplus_value_mm()`
returns. They matter because the same player can show different SV in different views.

> ### 🚩 FLAG 9 (HIGH) — frontend has a second, stale surplus table
> `index.html:35565-35584` defines `_SUR_TABLE`
> (`[[80,145],[75,90],[70,60],[65,40],[60,25],[55,15],[50,9],[45,4],[40,1.5],[35,0.5],[30,0]]`)
> and `computeTradeValue()` linearly interpolates it for the per-row **"Sur+" pill**. This
> table is **not** linked to `window.VALUE_FRAMEWORK`, has **no hitter/pitcher split, no
> position multiplier, and no bust/ramp/arb decomposition**, and is **3–5× lower** than the
> canonical values (e.g. FV 60 → `$25M` here vs snapshot `112.5` hitter / `84.1` pitcher;
> FV 80 → `$145M` vs `326.2` / `277.8`). The same UI shows the *canonical* number elsewhere
> (player card, org tree, trade audit), so two contradictory surplus figures for one player
> coexist. Regenerating the snapshot will not update `_SUR_TABLE`.
>
> ### 🚩 FLAG 10 (MEDIUM) — frontend adds a "TBS" multiplier with no Python equivalent
> `estimateSurplusValueMM` (`index.html:16608-16637`) faithfully mirrors the Python formula
> using snapshot constants, **except** it applies `_tbsOptMult` (a tie-breaker-score nudge,
> ~0.88–1.12; `index.html:16635, 16641-16648`). This multiplier exists only when the caller
> passes `{player}` or `{tbs}`. The **player card** (`index.html:30692`) and **trade audit**
> (`index.html:15733`) pass it; the **org-tree leaf** (`index.html:34364`), **farm sort**
> (`index.html:27392`), **roster sort** (`index.html:33089`) and **FV-badge tooltip**
> (`index.html:8661`) do not. Result: the same player's surplus differs by up to ±12% across
> views, and the player-card/trade-audit numbers diverge from the Python source of truth.
>
> ### 🚩 FLAG 11 (MEDIUM) — dead snapshot table + misleading comment
> `const SURPLUS_VALUE_MM` (`index.html:16533`) reads the snapshot's precomputed surplus
> grid but is **never indexed** anywhere. The trade-audit comment (`index.html:15637-15642`)
> claims surplus is "read from value_framework's re-derived surplus table," but the code
> actually calls `estimateSurplusValueMM` (re-derives the formula). The dead constant has
> only multiple-of-5 string keys, so a future maintainer who indexes it by a non-grid FV
> (e.g. `SURPLUS_VALUE_MM["58.33"]`) gets `undefined`. (The live path is safe; the trap is
> latent.)
>
> ### 🚩 FLAG 12 (MEDIUM) — veteran surplus is a different definition, summed on the same ledger
> `mlb_trade_lookup.py::_compute_surplus` (`mlb_trade_lookup.py:299-343`) computes a
> **contract** surplus for veterans: project remaining WAR from `career_war / war_seasons`
> with a hand-rolled aging penalty (`max(0, 0.4*(age-29))` per year), pick the `$/WAR` tier
> via `dollars_per_war(avg_per_year)` (`mlb_trade_lookup.py:341`), then subtract **full
> remaining AAV**. It does **not** use `career_war_value_mm`, applies **no** pre-arb/arb cost
> basis and **no** position multiplier. The trade audit (`index.html` grouping ~15919-16009)
> then **nets veteran contract-surplus against prospect cost-controlled-surplus on one
> ledger**, as if the two definitions were commensurable. Note also the tier is dispatched on
> the *average* remaining WAR for vets but on *peak* WAR for prospects — inconsistent tier
> selection between the two halves of a trade.
>
> ### 🚩 FLAG 13 (MEDIUM) — `is_pitcher` is re-derived locally and omits bare `"P"`
> `storage.py` classifies pitchers via local hardcoded sets `PITCHER_POS_SET`
> (`storage.py:5194`) and `PITCHER_POS` (`storage.py:7129`) — both `{RHP, LHP, SP, RP, MIRP,
> SIRP}` — instead of the imported `is_pitcher_position`, whose regex also matches bare `"P"`
> (`value_framework.py:315`). A prospect with position exactly `"P"` would be valued on the
> **hitter** WAR curve and hitter ramp. The frontend also detects pitcher inconsistently:
> some paths read `statline.is_pitcher` (`index.html:32702, 34362`), others use a position
> regex (`index.html:8660, 15732, 27391, 30688, 33088`) — a source-of-truth inconsistency
> that can pick the wrong FV→WAR curve.
>
> ### 🚩 FLAG 14 (LOW) — inline vet valuation duplicates `career_war_value_mm`
> `storage.py:8955` computes `round(career_war * dollars_per_war_flat(), 2)` inline rather
> than calling `value_framework.career_war_value_mm()`. It is **numerically identical today**,
> but it is a parallel code path that won't track future changes (floors, window, rounding) to
> the canonical function.
>
> ### 🚩 FLAG 15 (LOW) — a second, unrelated FV→WAR table lives in storage
> `storage.py:3163-3231` defines `FV_EXPECTED_WAR` / `FV_EXPECTED_WAR_PER_YR_*` (FV →
> *career* WAR, e.g. `50→3.0, 60→12.0, 70→25.0`). This is a **different quantity** from
> `value_framework`'s peak-WAR/yr and is used for development-credit/trajectory and grad-WAG
> scoring (`storage.py:5028-5030`), **not** for the dollar/surplus calc. It is not a divergence
> in the SV path, but it means the repo carries two distinct "FV→WAR" sources of truth.
>
> ### 🚩 FLAG 16 (LOW) — JS FV 20–30 floor isn't flat like Python
> For `war_peak ≤ 0` (FV 20–30), Python returns a flat `0.3` (`value_framework.py:385`,
> *no* position mult). The JS floor branch returns `0.3 * positionMult * tbsMult`
> (`index.html:16620`), so an FV-25 SS reads ~`$0.4M` in JS vs `$0.3M` in Python. Sub-$0.1M,
> but a real JS↔Python divergence.
>
> ### 🚩 FLAG 17 (LOW) — dead imports in storage
> `storage.py:4347-4350` imports `position_multiplier`, `is_pitcher_position`, and the tiered
> `dollars_per_war` but never calls them (tiering and position mult happen *inside*
> `surplus_value_mm`). Harmless but misleading.

---

## Worked example — a real non-grid-FV prospect, traced end to end

**Prospect:** **Grady Emerson**, found in
`prospect-tracker/data/draft_timeseries.json` →
`classes[year=2026].prospects[draft_2026_grady_emerson].consensus_fv_raw`.

**Inputs (as read from the data):**

| field | value | source |
|---|---|---|
| FV (continuous) | **58.33** | `consensus_fv_raw` (non-grid, not a multiple of 5) |
| position | **SS** | prospect record |
| is_pitcher | **False** (hitter) | from position |

These numbers were produced by **actually running `value_framework.py`** (Anaconda
Python 3.13.9 at `C:\Users\noahd\anaconda3\python.exe` — note the `python`/`py` launchers
on this machine are WindowsApps stubs that error, so the real interpreter must be invoked
directly). Every intermediate matches the canonical order of operations in §"The canonical
formula":

| # | step | expression | value |
|---|---|---|---|
| 1 | `war_peak` | `fv_to_war_peak(58.33, False)` — interp FV55 `2.9` → FV60 `4.15`, t = (58.33−55)/5 = 0.666 | **3.73** |
| 2 | `p_success` | `success_prob(58.33, False)` — interp BUST_PROB_HITTER 55 `0.45` → 60 `0.62` | **0.563** |
| 3 | `ramp` | `RAMP_FACTOR_HITTER` | **0.78** |
| 4 | `rate` | `dollars_per_war(3.73)` → 3.73 ≥ 2.0 → "2+" tier = avg(14.13, 13.91, 12.84) | **13.627** ($M) |
| 5 | `expected_war_6yr` | `3.73 × 6 × 0.78 × 0.563` | **9.828** WAR |
| 6 | `gross` | `9.828 × 13.627` | **133.93** ($M) |
| 7 | `arb_cost` | `3 × 3.73 × 13.627 × 0.60 × 0.78 × 0.563` | **40.18** ($M) |
| 8 | `cost_basis` | `2.4 + 40.18` | **42.58** ($M) |
| 9 | `surplus_pre_position` | `133.93 − 42.58` | **91.35** ($M) |
| 10 | `position_mult` | `position_multiplier("SS")` | **1.18** |
| 11 | `surplus_final` | `round(max(0.3, 91.35 × 1.18), 1)` | **$107.8M** |

`surplus_value_mm(58.33, False, "SS")` returns **107.8**, exactly matching
`round(max(0.3, surplus_pre_position × position_mult), 1)` (verified equal).

### What the flags do to this one number (illustrative, not as-built)

To make FLAGS 1–3 and 7 concrete on this prospect (these are *sensitivity* illustrations,
not how the code runs):

- The two stacked WAR haircuts are `ramp × p_success = 0.78 × 0.563 = 0.439`. The model
  prices **44%** of the naive `war_peak × 6 = 22.4` WAR. If the primer band is
  average-annual (FLAG 1) the `ramp` (FLAG 2) should be ~1.0, and if `war_peak` already
  embeds bust risk (FLAG 3) the `p_success` factor is partly redundant — removing just the
  ramp would lift `expected_war_6yr` from 9.83 to **12.60 WAR** and the gross from $134M to
  **~$172M**.
- The SS position multiplier (FLAG 7) adds **$16.4M** on top of the $91.3M pre-position
  surplus — on a player whose shortstop defensive value is *already* in the WAR that
  produced that $91.3M.

The point of the worked example is that a single mid-tier non-grid FV flows through
**five** multiplicative judgment calls (peak-vs-avg, ramp, bust, tier rate, position),
several of which interact, so the order and the interpretation in §1–§7 materially move the
final dollar figure.

---

## Summary of flags

| # | Sev | Where | Issue |
|---|---|---|---|
| 1 | HIGH | `value_framework.py:122-176` | Primer FV→WAR used as **peak** but is almost certainly **average-annual** (Sonny Gray 60-FV/3.8-peak case); mislabels the quantity. |
| 2 | HIGH | `value_framework.py:247, 390-392` | `ramp` (0.78/0.72) is an **assumed/tuned** peak→avg factor; **double-discounts** if §1 is average-annual. |
| 3 | HIGH | `value_framework.py:386, 390-392` | `war_peak × p_success` likely **double-counts bust risk** if the primer band is already expected/probability-weighted. |
| 4 | MED | `value_framework.py:390-391` | **No PV discounting and no $/WAR inflation** over the 6-yr window. |
| 5 | LOW | `value_framework.py:388` | Tier chosen from `war_peak`, but the WAR being priced is the ramped/bust-adjusted aggregate. |
| 6 | LOW–MED | `value_framework.py:396` | Position mult multiplies the **net** surplus, so it also scales the arb/pre-arb cost basis. |
| 7 | MED–HIGH | `value_framework.py:396` | Position multiplier applied on top of WAR, which **already includes a positional adjustment** → partial double-count (AAV-calibrated). |
| 8 | MED | `value_framework.py:286-313` | Relievers discounted **twice** (low WAR tier **and** sub-1.0 position mult), contradicting the in-code comment. |
| 9 | HIGH | `index.html:35565` | Stale `_SUR_TABLE` "Sur+" pill, 3–5× below canonical, not linked to the snapshot. |
| 10 | MED | `index.html:16635` | JS-only TBS multiplier (±12%) on some views but not others → inconsistent SV per player/view and vs Python. |
| 11 | MED | `index.html:16533, 15637` | Dead snapshot surplus table + misleading comment; latent non-grid-key `undefined` trap. |
| 12 | MED | `mlb_trade_lookup.py:299-343` | Veteran **contract** surplus is a different definition, netted against prospect surplus on one ledger; tier on avg vs peak WAR. |
| 13 | MED | `storage.py:5194, 7129` | Local `is_pitcher` sets omit bare `"P"`; inconsistent pitcher detection across backend/frontend. |
| 14 | LOW | `storage.py:8955` | Inline vet valuation duplicates `career_war_value_mm` (identical today). |
| 15 | LOW | `storage.py:3163-3231` | Second, unrelated FV→WAR (career-WAR) table — separate source of truth (not in the $ path). |
| 16 | LOW | `index.html:16620` | JS FV 20–30 floor applies pos/TBS mult; Python returns flat `0.3`. |
| 17 | LOW | `storage.py:4347-4350` | Dead imports (`position_multiplier`, `is_pitcher_position`, tiered `dollars_per_war`). |

**Headline for the refactor conversation:** the single most consequential question is §1/§2/§3
— whether the primer FV→WAR bands are *peak* or *average-annual*, and whether they already
embed bust probability. The code currently treats them as peak-and-unconditional and stacks a
`ramp` *and* a `p_success` discount on top; if the reviewer is right that they are
average-annual, those two factors are largely spurious and the whole surplus scale is biased
low. Everything else (position double-count, the stale frontend table, the vet/prospect
definition mismatch) is real but secondary to that interpretation question.
