# fa_penter decision-level eval: pre-registration (FROZEN 2026-08-19)

Registered before any 2026-27 decision resolves. This document freezes the
population, metrics, baseline, and verdict procedure NOW; the eval RUNS after
the Oct 2026 - Jan 2027 resolutions land. Nothing below may change after the
first decision is observed. Any deviation is a new, separately registered eval.

- Model: `fa_penter` (registry row in data/model_registry.json)
- Champion at freeze: v2 band-priced P(enter) for player/club/opt-out types
  (fa_market.enter_probability_v2, log-normal on the Gate-2 band); v1 explicit
  priors for mutual (0.85) and conditional (0.5) types (fa_config.yaml)
- Eval artifact (to be written at eval time): `data/fa_penter_decision_eval.json`
- Eval clock: opens 2026-10-01, closes 2027-01-31 plus resolution lag; scored
  once, after the last in-window decision resolves.

## 1. Population (frozen)

All class-2027 (2026-27 winter) option and QO decisions that BOTH:

1. resolve inside the Oct 2026 - Jan 2027 window (fa_events rows of type
   option_exercised / option_declined, post window guard, invalidated rows
   excluded; QO accept/decline from the curated qo_history when merged), and
2. had a SERVED pre-decision P(enter): the member carried `enterProb` in a
   nightly data/fa_class.json generated strictly BEFORE the decision's
   first-seen event_date. The scored probability is the LAST served value
   before that date, read from artifact snapshots, never recomputed after the
   fact.

Label: enter = 1 when the player reaches free agency (club declines, player
opts out or declines his side, mutual not exercised, QO declined); enter = 0
when he does not (club exercises, player option taken, QO accepted).

Exclusions, fixed now: decisions with no served pre-decision P(enter) are
counted and listed in the artifact but not scored; the 16 quarantined
qo_offered rows of 2026-08-12 are not decisions and enter nothing.

## 2. Primary metrics (frozen)

Brier score and log loss of the served P(enter), each vs a per-option-type
base-rate baseline scored on the identical decision set. Loss clipped at
p in [0.01, 0.99] for log loss only; Brier unclipped. Win requires beating
the baseline on BOTH primaries; mixed = null.

Baseline, stated now: per-type historical option pickup rates, i.e.
P(enter | fa_type) estimated from the archived winters 2015-2026. That
historical option-decision table is the data lift the registry row has
flagged as blocked since WS-2d; it must be assembled and frozen INTO the
eval artifact BEFORE any 2026-27 outcome is joined to a prediction.
Fallback, also fixed now: if the lift is still unavailable at eval time, the
baseline is the documented v1 config priors (mutual 0.85, conditional 0.5)
and p = 0.5 for club/player/opt-out types, the artifact says
`baseline: "placeholder_priors"`, and the verdict vocabulary drops WIN
(a placeholder baseline can only support LOSS or NULL). No baseline choice
after outcomes are visible.

## 3. Secondary metric (frozen)

Calibration slope: logistic regression of outcome on logit(served p),
reported with its CI. Reported, never gated; slope moves no verdict.

## 4. n expectation and the honest power caveat (measured 2026-08-19)

From today's served data/fa_class.json (generated_at 2026-08-19) and the
class-2027 rows in prospects.db:

- 230 members, 47 pending_option: 32 club_option, 7 opt_out, 5 player_option,
  3 mutual_option.
- Served P(enter) TODAY: 3 members (the mutual v1 priors). v2 band-priced
  P(enter) served today: 0, because option_price_usd is present on only 2 of
  the 47 stored rows; Spotrac populates strikes late. 45 of 47 already carry
  the v2 band (projGuar), so each prices the day its strike lands.
- Discrepancy noted at freeze: the planning note said "~42 members priced by
  v2 today". The artifact says 0 served v2 prices today; ~45 is the plausible
  ceiling by decision time, not a current fact. The artifact is the record.

Power: n <= 47 no matter what; realistically ~35-45 scored. At n ~ 42 a
Brier gap under ~0.05 vs baseline is inside noise. Both primaries therefore
ship with bootstrap 95% CIs (10,000 resamples over decisions, seed 20260819,
fixed now), and a gap whose CI covers 0 reads NULL (power-limited), never
WIN or LOSS. One winter cannot certify this model; it can falsify it.

## 5. Verdict procedure (frozen)

- The verdict (WIN / LOSS / NULL power-limited) is computed from the frozen
  rules above and written to data/fa_penter_decision_eval.json.
- The fa_penter registry row verdict updates AT THAT POINT, citing the
  artifact and this document. It stays "provisional" until then; nothing in
  this pre-registration changes the row today beyond a note that the eval is
  registered and clocked.
- Results below are filled with verbatim numbers from the eval run only.
  Failures are reported as failures.

## 6. Results

PENDING (eval clock Oct 2026 - Jan 2027; nothing may be written here before
the window closes).

- n scored: PENDING
- Brier (model / baseline): PENDING
- Log loss (model / baseline): PENDING
- Calibration slope (CI): PENDING
- Verdict: PENDING

## 7. Integrity notes

- Window guard on qo_offered stamping shipped 2026-08-19 (fa_pipeline.py,
  same Oct-Jan gate as option inference). The 16 out-of-window qo_offered
  rows of 2026-08-12 are quarantined in place (payload invalidated flag,
  rows never deleted) and excluded from serving via
  fa_pipeline.served_fa_events.
- Residual semantic risk, declared now: Spotrac's qo flag on the available
  page marks prior-QO recipients, who are ineligible for a new QO. An
  in-window firing for a prior recipient is still suspect; eval-time QO
  labels come from the curated qo_history, not from that flag alone.
- Tests: prospect-tracker/test_fa_penter_guard.py pins the guard, the
  quarantine, the served filter, and the in-window revalidation.
