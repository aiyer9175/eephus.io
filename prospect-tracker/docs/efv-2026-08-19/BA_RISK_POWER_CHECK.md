# BA risk ordinal power check (2026-08-19)

Pre-condition for omnibus-4 item D1 (risk into the p_bust chain). Report only:
NO fitting, NO wiring, no gate opened. All counts read live from prospects.db,
data/debuts.json, data/inactive.json, data/xfv_{hitter,pitcher}_matrix.json on
2026-08-19.

## 1. Inventory: usable risk ordinals

- BA rows total: 4,556 (snapshots, source=baseballamerica, 2023-02-15 to
  2026-08-10). 4,456 carry `tools_json._extras.ba_risk`; the 100-row 2026-06-03
  Top 100 is the only risk-free pull.
- Era vocabularies split exactly on the 2026 adjusted-era boundary:
  - 2023-2025 preseason (2,589 rows): Low 7 / Medium 367 / High 1,379 /
    Very High 92 / Extreme 744.
  - 2026 vintages (1,867 rows: 2026-02-15, 2026-08-05 Top 100, 2026-08-10
    midseason): Low 5 / Mild 127 / Average 767 / High 708 / Extreme 260.
    Medium and Very High vanish; Mild and Average appear.
- Ordinal map used here (the D1 proposal): Low=0, Mild=Medium=Average=1,
  High=2, Very High=Extreme=3. Low is unusable at any horizon (n=2 in the
  outcome pool); Very High merges into Extreme.

## 2. The resolved outcome pool (2023 base year)

Task memory said "~750 resolvable was the last count". That count does NOT
verify. Measured today, two definitions:

- STRICT (row present in the shipped xfv outcome matrices, bust or debuted,
  DEBUT_YEARS 2011-2024, RESOLVED_THROUGH=2025): 474 of the 874 risk-bearing
  2023-02-15 rows (357 debuted, 117 bust; 123 with fully resolved WAR windows).
- GENEROUS (bust-classification only: debuted at ANY date through today per
  debuts.json, or terminal never-MLB per inactive.json): 629 of 874
  (509 debuted, 120 bust, bust rate 19.1%). 245 rows still open.

629 is the honest ceiling for a bust-classification fit today. Later vintages
are far thinner: 2024 gives 430 resolvable (11 busts), 2025 gives 344 (4
busts). Bust labels arrive years behind debut labels.

Survivor-bias caveat, load-bearing: debuts resolve in 1-3 years, busts
terminal-resolve in 4-6. The 245 open 2023 rows skew heavily toward eventual
busts (full-history base rate in the xfv matrices is 54% bust; the resolved
2023 slice shows 19%). Any fit on today's pool trains on a bust-depleted,
risk-correlated sample. This is the same defect class the ETA overdue
guardrail caught on 08-18 (+453 survivor bias); n alone understates the
problem.

## 3. MDE at today's n (2023 base year, generous pool, n=629)

Tier counts (ordinal, n, busts, rate): ord1 117 / 8 / 6.8%; ord2 372 / 66 /
17.7%; ord3 138 / 46 / 33.3% (Extreme 105 + Very High 33); ord0 n=2, dropped.

Method A, adjacent-tier two-proportion z (alpha .05 two-sided, power .80,
MDE = 2.802 * sqrt(pbar*(1-pbar)*(1/n1+1/n2))):
- ord1 vs ord2 (n 117/372, pooled p .151): MDE = 10.6 pp of bust rate.
- ord2 vs ord3 (n 372/138, pooled p .220): MDE = 11.6 pp.

Method B, AUC (Hanley-McNeil SE at the null, one-sided alpha .05, power .80,
MDE = 2.487 * sqrt((1/12)(1/n_bust + 1/n_nonbust))):
- n_bust 120, n_nonbust 509: detectable AUC lift = 0.073 above 0.5.

Conditioning penalty: rho(risk ordinal, BA fv) = +0.31 in the pool, VIF 1.10,
so the covariate-adjusted MDE inflates a further 1.05x. Small. The real
attenuation is in the EFFECT, not the SE: the registered question is
incremental discrimination beyond consensus FV + eFV, and only the component
of risk orthogonal to those features counts.

## 4. Plausible effect size

- BA's own arithmetic: adjusted = raw - 5*risk_ordinal, so one tier = 5 FV pts.
- Known bust-rate curve: 51% at FV45 vs 14% at FV60 = 2.47 pp per FV pt.
- Plausible MARGINAL effect: 5 * 2.47 = 12.3 pp of bust rate per tier.
- Plausible INCREMENTAL effect: strictly smaller; if consensus FV + eFV absorb
  half (they already price BA's adjusted grade, which embeds the ordinal),
  ~6 pp per tier, or ~0.01-0.03 incremental AUC in the Method B frame.

## 5. Verdict: UNDERPOWERED NOW

- Marginal frame: MDE 10.6-11.6 pp vs plausible 12.3 pp. Nominal power ~0.80
  only if the FULL marginal effect were the estimand. It is not.
- Registered (incremental) frame: plausible ~6 pp vs MDE ~11 pp, or ~0.01-0.03
  AUC vs MDE 0.073. Underpowered by roughly 2x in the proportion frame and
  2-5x in the AUC frame.
- Survivor bias independently disqualifies a fit today regardless of n.

Resolution arithmetic for year X: at RESOLVED_THROUGH=2027 (the 2028 cycle)
the 2023 vintage is ~90% terminal and 2024 adds its bust wave; projected pool
~1,380 rows, ~610 busts. Method B MDE drops to 0.039 AUC; adjacent-tier MDE to
~9 pp, below the 12.3 pp marginal and near the attenuated incremental range.
At RESOLVED_THROUGH=2028 (2029 cycle, +2025 vintage, ~850 busts / ~1,050
non-busts): AUC MDE 0.033, tier MDE ~7 pp.

**Underpowered until 2028 for the tier-level contrast; the strict
incremental-AUC frame stays marginal until 2029.** This matches the omnibus-4
registered revival clock (BA risk 2027-28). Correct action now: keep the
feature dark (computed, not consumed), keep the clock, re-run this arithmetic
when RESOLVED_THROUGH advances. Projected-pool numbers in section 5 are
projections, labeled as such; every other number above is measured.
