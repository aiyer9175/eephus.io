# S1 / S2 — surplus levers — pre-registered gates (2026-07-19)

Registered BEFORE the arms are run (program rule). Both move served surplus $ and
BOTH require a real surplus backtest AND an owner golden restamp of `trade_values.json`
before shipping. Config: `surplus_levers` in `value_framework_config.yaml`; both
`enabled: false`. With the flags off, both are byte-identical to today (verified).

Backtest harness / artifact: the real surplus backtest (`data/surplus_backtest_real.json`).
Golden diff: `data/trade_values.json` (owner-signed restamp).

---

## S1 — super-two population blend for unknown-status serviced players (audit B1)

### What
A serviced player (`service_time > 0`) whose super-two status is genuinely UNKNOWN is
currently treated as **non**-super-two (`super_two_fraction = 0`), denying the ~22%
population chance he reaches arbitration a year early. When `super_two_population_blend`
is on AND the caller passes `super_two_known=False`, the player uses the same population
fraction (`service_time.super_two.fraction = 0.22`) that a just-debuted player already
gets. KNOWN-status players (`super_two_known=True`, the default) are unchanged.

### Gate (ALL required)
1. **Off / known invariant:** with the flag off, OR for every `super_two_known=True`
   call, surplus $ is bit-for-bit identical to today. (Unit-tested.)
2. **Direction:** for an unknown-status player who would otherwise get 0, the blended
   surplus is **between** the non-super-two value and the super-two value, and strictly
   `≥` the non-super-two value (extra early-arb cost lowers surplus, so the blended
   value is `≤` the naive-0 value by at most the population fraction × the arb-year cost).
   No sign flips.
3. **Backtest not worse:** on `surplus_backtest_real.json`, the surplus ranking metric
   (the harness's headline) is **≥ baseline − 0.002** with the blend applied to the
   genuinely-unknown subset. A real improvement is a bonus, not required — the claim is
   "more correct treatment of a known-uncertain input, at no measured cost."
4. **Population-rate consistency:** the fraction used equals the shipped
   `service_time.super_two.fraction`; S1 introduces no new empirical estimate.

PASS all ⇒ enable, wire the callers to pass `super_two_known` honestly, box regen,
owner restamp. Fail ⇒ committed loss.

---

## S2 — positional scarcity into core surplus (audit B2) — HAZARD, expect committed loss

### What
Wire the comp-calibrated `trade_value.positional_scarcity` table (C 1.22, SS 1.12, …)
into CORE surplus as a WAR-input multiplier, via the existing `position_multiplier`
hook, double-gated behind `apply_market_scarcity` AND
`positional_scarcity_in_core_surplus`.

### KNOWN HAZARD (read before enabling)
That table was fit on **AAV data**. WAR already embeds the defensive positional
adjustment, so an AAV-derived positional multiplier **double-counts** the positional
value (this is exactly why core surplus applies NO position multiplier today — see the
`position:` block comment and `docs/sv-audit.md` FLAG 7). Shipping the AAV table into
core surplus is therefore expected to be a **LOSS**, not a win. This wiring exists to
carry that as a committed loss and to be ready for a CLEAN, non-AAV-confounded
re-estimation — it is NOT a green light to enable the current table.

### Gate (ALL required — and clause 0 is expected to FAIL on the current table)
0. **No double-count (the real bar):** the positional multiplier must be estimated on a
   basis ORTHOGONAL to the positional adjustment already in WAR (e.g. residual trade
   returns by position after controlling for WAR), NOT on AAV. Using the current
   AAV-fit table fails this by construction ⇒ committed loss; do not ship.
1. **Off invariant:** flags off ⇒ `position_multiplier` returns 1.0 for every position,
   surplus bit-for-bit identical. (Unit-tested.)
2. **Backtest strictly better:** on `surplus_backtest_real.json`, the surplus ranking
   metric improves by ≥ +0.005 with scarcity applied vs off. (An AAV table is not
   expected to clear this honestly.)
3. **No position inversion:** applying scarcity does not reorder positions against the
   real trade-return evidence (a sanity check the multiplier points the right way).

PASS all (which requires a clean re-estimated table, clause 0) ⇒ enable, box regen,
owner restamp. On the current AAV table ⇒ **committed loss recorded here; flag stays off.**

## RESULTS

_Pending the canonical surplus-backtest run + owner restamp on the box._
