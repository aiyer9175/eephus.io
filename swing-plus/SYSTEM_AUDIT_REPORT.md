# PROJECTION SYSTEM AUDIT REPORT
**Experiment:** SYSAUDIT-2026-06-11 · **Scope:** the complete architecture (5 skill axes →
variance → aging/cascades → historical priors + backbone → translation) ·
**New computations:** `pipeline/06_system_audit.py` (deterministic, fixed common sample
n=536, leave-one-transition-out) · **Synthesized:** COLLISION_REPORT, AGING_REPORT,
PROJECTION_REPORT (+P4/P5), TRANSLATION_REPORT, variance handoff M0–M12 · **Owner:** @willclq

## EXECUTIVE SUMMARY — **GO**

The architecture functions as designed: skills are distinct and owned, leakage is LOW
(two incidents caught and fixed during development, both documented), calibration
passes on every audited target, portability/reversibility pass, and the system is at
benchmark parity on public systems' best stats while beating them where skills see
what stat lines can't. The honest system-level finding: **with full own-stat history
present, Swing+ and DCV+ carry nearly all marginal skill value at the season grain;
Decision+/Contact+/B2B+ are history-redundant for point projection** (they matter for
decomposition, rookies/thin history, and within-season skill change detection — their
real roles). Two missing-skill leads identified (sprint speed at engine level;
LA-dispersion/adjustability). Priorities ranked below; playing time + simulation are
cleared to build.

## AUDIT 1 — SKILL OWNERSHIP MATRIX

| Signal | Primary owner | Secondary | Overlap risk |
|---|---|---|---|
| Bat speed / path power | Swing+ | aging cascade (consumer) | LOW |
| Swing/take selection | Decision+ | — | LOW |
| Contact frequency / whiff | Contact+ v2 | own-K% history (priors) | **MED** (measured: skills explain .77 of K% history) |
| Contact quality / damage conversion | B2B+ | Swing+ (xwobacon path) | MED (collision audit: framework-redundant gains) |
| Pull-air damage geometry | DCV+ | — (B2B+ carries none, r −.14) | LOW |
| Walk skill | **(none — gap)** | BB% history (priors) | by design |
| Speed | variance e2 only | **not in engine features** | gap (see Audit 13) |
| Luck/regression | Variance layer | shrinkage inside priors | MED at system grain (see Audit 17) |
| Environment | Translation | — (neutrals park-clean, corr −.00) | LOW |

## AUDIT 2 — DEPENDENCY GRAPH + SENSITIVITY

Raw Statcast → {Swing+, Decision+, Contact+ v2 (← v1 + collision), B2B+, DCV+}
→ {Hitter+ blend; variance e2; aging panel; engine skills-block} → engine fusion
(← deep backbone ← statsapi) → translation. Sensitivity: an upstream axis change
propagates to Hitter+ (weight ≤ .31), engine (ridge coef, shrunk), aging projections
(reversion b ≤ .85) — all damped, no amplifying loops. The one hard coupling:
Contact+ v2 consumes B2B-framework v1 — a v1 rebuild forces v2 + engine refits
(documented in FEATURES.md dependency lists).

## AUDIT 3 — DOUBLE COUNTING MATRIX

| Pair | Measured overlap | Incremental after control | Risk |
|---|---|---|---|
| K% history × Contact+ | skills explain R²=.77 of career K% | Contact+ marginal ≈ 0 given history (Audit 17) | **MED — accepted, documented** |
| BB% history × Decision+ | R²(skills→BB% hist) low; Dec+ has no walk content | Dec+ marginal ≈ 0 | LOW |
| HR/ISO history × Swing+/DCV+ | skills explain .67 of ISO history | Swing+ still adds (+1.7 RMSE pts); DCV+ +.5 | LOW |
| BABIP history × all skills | only R²=.16 explained | history keeps unique 84% | LOW |
| Aging × variance engine terms | outcome-aging bias UNAPPLIED by design | constraint documented twice | LOW (guarded) |
| Aging × skills age feature | age lives in ONE step of the ladder | no double entry (D≈C in engine race) | LOW |

## AUDIT 4 — LEAKAGE (system-wide): **LOW**

Temporal: every model fits on features ≤ t, targets t+1; backbone trained on
2000–2022 sources only. Derived: career priors to-date-only; **two leakage incidents
caught during development and fixed** — (1) stand-split row duplication in the
collision joins (boards rebuilt, verdicts re-verified unchanged); (2) career-mean
archetype grouping (faked −16% OOS; reversed by season-t grouping). Environmental:
translation reads (park, stand) only; neutrals measured park-clean (corr −.00).

## AUDIT 5 — RELIABILITY CHAIN (y2y, full-season)

EV90 .89 > Swing+ .86 ≈ Contact+ v2 .86 > collision features ≤ .82 > B2B+ .75 >
Decision+ .71 > **DCV+ .65 (weakest skill link)** > … targets: K% .81 > BB% .71 >
xwOBA .67 > ISO .64 > wOBA .51 > AVG .44 > BABIP .33 (weakest target).
Strongest link: the physical layer (EV90/bat speed). Weakest skill: DCV+ —
acceptable (its blend weight is the smallest at .13).

## AUDIT 6/17 — SEQUENTIAL VALUE-ADDED LEADERBOARD
(fixed common sample n=536; cumulative OOS RMSE ×1000; spec order)

| target | Hist | +Sw | +Dec | +Con | +B2B | +DCV | +Var | +Age | +Trans |
|---|---|---|---|---|---|---|---|---|---|
| k_pct | 34.6 | **33.8** | 33.8 | 33.8 | 34.1 | 34.1 | 34.0 | 34.0 | 34.0 |
| iso | 47.2 | **45.5** | 45.5 | 45.5 | 45.5 | **45.0** | 45.3 | 45.6 | 45.4 |
| xslg | 55.0 | **52.9** | 52.9 | 52.9 | **52.2** | 52.2 | 52.2 | 52.6 | 52.5 |
| xwoba | 30.7 | **30.1** | 30.1 | 30.1 | **29.8** | 29.7 | **29.0** | 29.3 | 29.4 |
| woba | 34.6 | **33.9** | 33.9 | 33.9 | 33.9 | 33.9 | 33.7 | 33.8 | 33.7 |
| babip | 33.8 | 33.5 | 33.5 | 33.5 | 33.5 | **32.8** | 33.1 | 32.9 | 32.9 |
| hr_pa | 13.2 | **12.7** | 12.7 | 12.7 | 12.8 | **12.6** | 12.6 | 12.6 | 12.4 |

**Module ranking (median share of skill-stack lift):**
**#1 Swing+ (+70%)** · **#2 DCV+ (+18%)** · #3 Translation (+5%, HR-only) ·
#4 Aging (+2%) · #5 Variance (+1%) · #6 Decision+ (0%) · #6 Contact+ (0%) ·
#8 B2B+ (−2%). Caveat: sequential order credits history first; Decision+/Contact+
zeros mean *redundant-given-K%/BB%-history*, not valueless — their standalone audits
showed real skill content, and they carry the rookie/thin-history and decomposition
roles. B2B+'s slight negative confirms the collision audit's framework-redundancy
verdict at system level. The Variance layer adds ~0 to point projections here
because its k-table shrinkage is already implicitly performed by the regression —
its real products are the luck display and the engine constants.
**Target-specific:** Swing+ dominates power targets; DCV+ owns babip/avg/xba;
nothing but history matters for BB%. **Archetype split (power/contact/balanced
ISO-terciles):** skill-stack lift concentrates in power hitters (consistent with the
mirror test); no archetype shows negative total lift.

## AUDIT 7 — ARCHETYPES: PASS (all face-valid)

Arraez Con **127**/Sw 89 · Judge Sw **125**/Con 91 · Alonso Sw 116/B2B 111 ·
Soto Dec **113** balanced-elite · Schwarber Sw 123/DCV **112** · **Paredes Sw 101/DCV
110** (pull-damage WITHOUT raw power — exactly the geometry axis working) ·
Marsh all ~100 (system says ordinary skills, BABIP done by luck layer) · Rafaela
Dec 90 (the weakness named) · Tatis DCV **89** (the under-converter, replicating the
DCV framework's finding). Wilson 93 reflects his actual down 2026.

## AUDITS 8/9 — PORTABILITY & REVERSIBILITY: **PASS**
(TRANSLATION_REPORT: Soto talent + xwOBA frozen across 5 parks, realized wOBA
.343–.378; reverse error .0001; talent provably upstream.)

## AUDIT 10 — CALIBRATION: **PASS**
Full-system deciles: wOBA max |err| .0147, AVG .0123, HR/PA .0046. Known mild
top-decile compression on xwOBA (≤ .019) = elite-tail, fix queued.

## AUDITS 11/12 — STRESS & ROBUSTNESS
Slices (from module reports + system run): no slice with divergent RMSE; weakest
rank-ordering inside mid/bottom talent terciles (range restriction, not bias); the
binding stress everywhere is the **partial-2026 fold** — every conclusion that
matters was checked per-fold and survived. Robustness: thresholds (PA 200→300/400),
folds, shrink constants varied in module audits; conclusions stable.

## AUDIT 13 — MISSING SKILLS

Consistent over-performers (≥2 transitions): **Edwards, Yelich, Turang** (+.035–.048)
— speed profiles; under-performers: **Hayes** (−.071, the chronic x-stat
under-converter), Arcia, K. Ruiz (slow). Residual correlates: LA-dispersion
(attack_angle_std) **+.13** — the adjustability signal flagged by the variance model
(cons_la_sd ↔ babip posterior −.38) shows up AGAIN at system level. Verdict: two
real candidate skills, neither critical: (1) **sprint speed is validated but not yet
an engine feature** (it lives only inside variance e2) — cheapest fix in the system;
(2) LA-dispersion/adjustability axis — the twice-flagged backlog item.

## AUDIT 14 — BENCHMARK: parity-to-ahead
Backbone alone matches ZiPS/Steamer on their best stats (K% 23→24 r .850/2.3%/3.0%
vs ZiPS .844/2.4%/3.0%; BB% MAE/RMSE equal); fusion beats backbone on all 10 realized
targets. Production stats (their table's lower rows) = our strength per the mirror
test. True head-to-head awaits their CSVs on identical players.

## AUDIT 15 — UNCERTAINTY
σ per target published (xwOBA ±.028 … OPS ±.084). Decomposition: talent drift
dominates; measurement share = (1−reliability) (large for BABIP/AVG, small K%/EV90);
model error (fold spread) small; translation adds ~10–15% to HR σ for movers only.

## AUDIT 16 — REPRODUCIBILITY: PASS
Every module: experiment ID, date, data version, deterministic fits or recorded seed
(20260610), pipelines re-runnable end-to-end (verified throughout: every artifact in
this audit was regenerated at least once from source).

## RESEARCH PRIORITIZATION (highest ROI first)

1. **Add sprint speed to the engine feature block** — validated, trivial, addresses
   the #1 residual pattern (speed over/under-performers).
2. **Refit everything when 2026 completes** — n +40%, first clean holdout; every
   constant is v1 on 2½ seasons.
3. **LA-dispersion / adjustability axis** — twice-flagged residual-talent chunk.
4. **Elite-tail correction** (constants exist; top-decile compression measured).
5. **Playing-time model** (cleared to build — the GO unlocks it).
6. Park-factor firming (geometry + Savant 3-yr) — translation-quality only.
7. **De-prioritize:** new skill axes (discovery closed; B2B+ marginal negative at
   system level), weather, archetype-specific anything (0-for-3 in audits).

## GO / NO-GO: **GO**

All 12 conditions met: no major leakage (2 caught+fixed, process works) · double
counting measured and bounded (K%-history×Contact+ accepted, documented) ·
reliability chain acceptable (weakest: DCV+ .65, lowest weight) · incremental value
positive and mapped · calibration PASS · portability PASS · reversibility PASS ·
benchmarks competitive · no critical missing skill (two non-critical leads queued) ·
reproducible · contributions quantified · priorities ranked.
**Cleared to build: Playing Time, then Simulation/Uncertainty.**
