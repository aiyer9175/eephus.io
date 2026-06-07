# Surplus-Value (SV) Methodology — As-Built (v2 engine)

> **v47 (current): EMPIRICAL RECALIBRATION.** The `FV → expected WAR` anchors were
> re-grounded in realized 2017–2020 cohort outcomes (the model had been ~3–4× over
> realized/public because the old anchors were the survivor/ceiling-flavored
> FanGraphs primer). Bucket WAR levels are now **FV-dependent** (`_fv_war_scale`) so
> the de-inflation reconciles at every FV with no smoothness break, and the convex
> `$/WAR` is **continuous** (v46). Surplus by tier dropped from 2–4× to **0.7–1.2×
> the public Edwards scale**, out-of-sample validated. Full empirical foundation,
> validation, and benchmark table: [`surplus-recalibration.md`](surplus-recalibration.md).
> The framework below (risk-adjusted, PV-discounted mixture expectation) is unchanged
> — only the WAR-magnitude input and the midpoint mechanism were recalibrated.

**Status:** Authoritative description of the **current** surplus-value engine
(`prospect-tracker/value_framework.py`, config in `value_framework_config.yaml`),
the career-path **mixture model** that replaced the v1 point-estimate pipeline.

This supersedes [`sv-audit.md`](sv-audit.md), which documents the **retired** v1
pipeline (a single ramp × p_success point estimate) and its flags. Read that only
for the history of *why* the model changed; everything below is what the code does
now.

The engine is the **single source of truth**: `storage.py` bakes its per-player
outputs into the export, and `index.html` renders those baked numbers verbatim —
the UI never re-derives the model in JS, so the displayed value equals the engine
output. The frontend snapshot (`data/value_framework.{json,js}` →
`window.VALUE_FRAMEWORK`) carries the constants/curves; per-player outputs ride on
each player's `surplus` / `debuted_value` block.

---

## 0. The shape of the model

A prospect has not played, so his surplus is a **distribution**, not a number. The
engine models a career as a **mixture over five outcome buckets** and aggregates
**last**:

```
expected_SV(FV) = Σ over buckets  P(bucket | FV) × bucket_surplus
bucket_surplus  = Σ over the 6 controlled seasons [ tiered_$/WAR(season WAR) − season salary ],
                  present-value discounted, busts floored at $0
```

**Why bucket-by-bucket, season-by-season** (the central design principle):
the WAR→$ map is non-linear, and `E[f(X)] ≠ f(E[X])`. The market pays a *star* rate
for star seasons and a *fringe* rate for fringe seasons, and a busted prospect
contributes **$0** (a released player owes nothing), not a negative. Collapsing to one
"expected WAR" before the non-linear $/WAR and salary steps would average the star
premium down and average the bust's floored $0 up. So the engine **transforms at the
finest grain — every bucket, every season — and aggregates last.**

The five buckets, by WAR band (`buckets` in config):

| bucket | band (WAR/yr) | meaning |
|---|---|---|
| bust | < 0.5 | washes out / org filler (≈ $0) |
| bench | 0.5–1.5 | up-and-down role player |
| regular | 1.5–2.5 | everyday starter |
| good | 2.5–4.0 | above-average regular |
| star | 4.0+ | All-Star tier |

---

## 1. Inputs (with units)

- **FV** — the 20-80 scouting grade; sets the bucket probabilities. Used
  **continuous** (e.g. 57.3), never snapped to the 5-pt ladder.
- **P(bucket | FV)** — five probabilities, an **ordered-logit (proportional-odds)**
  fit on published grade→outcome data (Clemens 2025), separate for hitters/pitchers,
  smooth and monotone in FV. (`p_bucket_given_fv`.)
- **FV → WAR anchor** — the **FanGraphs average annual WAR over the first six
  controlled years — NOT peak.** (The primer's own Sonny Gray example: peaked at 3.8
  WAR yet grades 60 FV, only coherent as an average.) It calibrates the bucket WAR
  *levels* so the probability-weighted six-year-average matches the anchor; nothing
  reads it as a peak and there is **no ramp**. (`fv_to_6yr_avg_war`,
  `_calibrated_midpoints`.)
- **Tiered $/WAR** ($M per win) — convex 3-tier market rate (2026 FA study), applied
  to **each season's own WAR** (per-season, per-bucket), not an averaged WAR. A flat
  overall rate (~$11.23M) is used only for realized career aggregates.
  (`tiered_war_value_usd`, `dollars_per_war`.)
- **Performance-adaptive arbitration** — pre-arb seasons cost ~league minimum
  (~$0.76M); the three arb seasons cost an escalating share (~40/60/80%) of *that
  season's* market value, so salary scales with production. Super-Two converts one
  pre-arb year into an early arb year (population-blended for a just-debuted player).
  (`_service_path_surplus_usd`, `service_time` config.)
- **Present-value discounting** — future surplus discounted ~9%/yr; timing from the
  **projected debut** (ETA) + an empirical aging curve, with $/WAR inflation netted
  against the discount rate. (`present_value`, `aging`, `discount_from`.)
- **Positional adjustment** — **none** as a dollar multiplier (WAR already contains a
  positional adjustment by construction; layering another double-counts). Market-
  scarcity multiplier ships **off**. Relievers are the one role adjustment: their WAR
  is haircut to a full-season bullpen equivalent (source bands normalized to 200 IP).

---

## 2. Standard output contract (per prospect)

`sv_distribution(fv, is_pitcher, position, age, eta_years, …)` returns the full
contract; `storage._build_surplus_payload` bakes it onto each player's `surplus`:

- `value_mm` — **expected (mean) surplus, POST-calibration** (the headline).
- `dist.percentiles` — **P10 / P25 / P50 / P75 / P90** ($M), from a mean-preserving
  Monte-Carlo over the buckets (the UI draws this as a percentile **fan**).
- `dist.p_bust` — P(career = bust), whose surplus floors at ~$0.
- `dist.downside_mm` — CVaR (mean of the worst-decile outcomes).
- `dist.risk_adjusted_mm` — **risk-adjusted score** `mean − λ·(mean − downside)` at the
  configured risk-aversion **λ** (`risk_aversion_lambda`); at λ=0 it equals the mean.
- `buckets` — the five `P(bucket|FV)` probabilities (the stacked bar).
- `fv_continuous` / `fv_used` — the **exact FV the engine priced** (display honesty).
- `ci` — epistemic credible interval on the expected value (hierarchical-Bayes
  parameter uncertainty), distinct from the outcome range.
- `dist.fv_dispersion` — cross-source FV disagreement widens the spread **without
  moving the mean** (Prompt I).

---

## 3. Debuted players (realized + remaining)

Once a prospect reaches MLB, value splits (Prompt D; `debuted_player_value`, baked as
`debuted_value`):

- **realized_mm** — surplus already captured: market value of WAR played − salary paid
  (Spotrac actuals where available, else the engine's own service model via
  `realized_consumed_seasons`), present-valued. Sunk; does not transfer in a trade.
- **trade_value_mm** — expected surplus of the **remaining** control years only,
  **Bayes-updated** by realized MLB WAR (Marcel-style regression of the outcome-bucket
  prior toward the observed rate) and shortened by consumed service time.
- **total_value_mm** — realized + remaining.
- **posterior** — the Bayes-updated bucket mix (the debuted stacked bar uses this, not
  the FV prior).

A 0-MLB prospect carries **no** `debuted_value`, so the UI hides every debuted-only
field.

### WAG — WAR Above Grade (Prompt M)

WAG is the **single, canonical** WAR-Above-Grade metric across the site
(`value_framework.wag` + the shared `expected_war` core; the legacy
static-baseline `storage._grad_wag` family is retired). It is built on the SAME
FV-projection core as surplus value and the debuted update — no separate FV→WAR
lookup — and is **baked per graduate** as `debuted_value.wag`, read verbatim by the
UI (the WAG pill, the Debuted-list columns/sorts, WARWAG, the per-season chart) and
by the backend boom/bust label + per-org farm-grade rollups.

- **Core:** WAG = observed MLB WAR − the FV-implied expectation **over the same
  exposure**. The FV trajectory is truncated to the player's actual service / PA /
  IP and **age-placed** on the aging curve (so a strong rookie one season in reads
  ahead of grade, not behind — the key fix over the old full-window baseline).
- **Two forms:** *counting* (cumulative WAR − exposure-matched expected) and *rate*
  (per 600 PA / 200 IP). They diverge by exposure — an injured-but-good player's
  excellence shows in the rate, a healthy-but-mediocre player's deficit compounds in
  the counting total.
- **Standardized headline:** the **percentile (PIT)** of observed WAR in the FV's
  predicted cumulative-WAR distribution at that exposure (0.5 = on grade) — plus a
  z-score. Distribution-aware and comparable across FVs.
- **Regression + flag:** the reported value is a reliability-**regressed**
  true-talent WAG (shrunk toward 0 by the same sample-weight the debuted Bayes update
  uses, with an uncertainty band); exposure below `wag.meaningful_exposure`
  (200 PA / 80 IP) is flagged and the boom/bust label is `unsettled`.
- **Debuted consistency:** WAG is the residual that drives the Prompt-D posterior —
  same `_talent_regression`, same sample weight, same pre-debut FV baseline, so WAG
  and the bucket-posterior shift move with one sign and magnitude (the per-player
  bake passes the observed PA/IP so the posterior genuinely updates).
- **Reliever-safe:** graded on the band/talent scale; the reliever role-VALUE haircut
  is a $ effect applied only downstream.
- **Boom/Bust label** (`wag_boom_bust`): keyed on the standardized percentile
  (boom ≥ 0.80, bust ≤ 0.20, settled middle, unsettled below meaningful exposure;
  thresholds in `config.wag.boom_bust`).
- **Aggregates:** WAG risers/fallers (the sortable Debuted list), and mean WAG by
  source (→ Prompt N source-calibration), org, position, and level
  (`wag_leaderboard` / `wag_mean_by`).

---

## 4. System rollup (Prompt K)

`system_surplus_distribution` rolls a farm system up as a **distribution, not a sum of
means**: single-factor outcome **correlation** (booms/busts co-move → wider P10–P90,
same mean) and a **roster-realization (logjam)** discount (a position-stacked system
can't play everyone; the blocked excess realizes only at a trade discount). Baked onto
`org_summary.system_surplus`.

---

## 5. Calibration

Every displayed `value_mm` is **POST-calibration**: the raw mixture output passes
through `apply_calibration` — a documented, **reversible, versioned** monotone map
(linear or isotonic) that corrects systematic predicted-vs-realized bias found by the
backtest. It **ships as the identity** (`calibration.enabled: false`), so today's
displayed values equal the raw model output; when a real-data backtest (`backtest.py`,
Prompt F) fits the map, the whole site moves with it (every surface reads the same
baked, calibrated value).

---

## 6. Continuity & non-grid FV

FV changes only the bucket **probabilities** along a smooth monotone curve, never the
value of an outcome — so a 47.3-FV prospect is valued directly. The debuted path
reduces **exactly** to the prospect model at 0 PA/IP. Relievers stay on the capped
relief curve under any role tag.

---

## Where it's surfaced (UI)

- **Player card** — expected SV (with the continuous FV), the outcome-bucket bar, the
  P10–P90 fan + P(bust), risk-adjusted SV, model CI; for debuted players: trade vs
  total vs realized + WAG. Reads `p.surplus` / `p.debuted_value` directly.
- **Active list** — a "Surplus · outcomes" column (expected SV + mini bucket bar +
  mini fan + P(bust)); sortable by expected SV, risk-adjusted SV, P10, P90, P(bust),
  WAG; filterable by position / level / org / age / ETA.
- **Farm detail** — the system surplus distribution (P10–P90 + logjam discount + fan).
- **Glossary** — every metric links here: `surplus_value`, `value_framework`,
  `sv_distribution`, `risk_adjusted_sv`, `trade_total_value`, `system_surplus`,
  `bust_prob`, `fv_to_war_table`, `dpw_tier`, `continuous_fv`, `sv_calibration`, `wag`.

All parameters live in `value_framework_config.yaml` and are tunable without touching
the logic.
