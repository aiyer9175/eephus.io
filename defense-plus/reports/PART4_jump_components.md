# Part 4 (OF jump focus) — reliability, aging, predictive value
Date: 2026-06-16 · `pipeline/08_jump_aging_prediction.py` · Savant OF jump 2016–2025, n=930 OF-seasons (n≥20 attempts)

Components (ft vs league): **reaction** (0–1.5s read), **burst** (1.5–3s acceleration), **route** (efficiency), **jump-total** (boot-up).

## Test 1 — reliability (y2y): jump components ARE steadier than the OAA outcome
| signal | y2y r |
|---|--:|
| **reaction** | **0.82** |
| burst | 0.69 |
| jump-total | 0.68 |
| route | 0.66 |
| OAA (outcome) | 0.64 |

Every jump component is more reliable than OAA itself; **reaction (the read/first-step) is by far the steadiest** (.82) — a cognitive/anticipation skill measured over many plays. This supports the kernel of the hypothesis: jump is a steadier *talent signal* than the noisy outcome.

## Test 2 — aging  ⚠️ SUPERSEDED by hierarchical Bayesian model (see below)
The naive delta-by-age-band version is **survivorship-biased** and is retained only to show the bias. Use the Bayesian curves in `09_bayes_aging.py`.

### Bayesian within-player aging (correct method)
`pipeline/09_bayes_aging.py` — model `skill = player_i + b1·(age−27) + b2·(age−27)²`, player random intercepts (the *player* / sample selection) separated from the *skill's* age trajectory (identified within-career). n=811 OF-seasons, 205 players (≥2 seasons). Units = SD vs peers.

| skill | slope @27 (SD/yr) | 27→33 change | naive old-age delta | reading |
|---|--:|--:|--:|---|
| **burst** (athletic) | −0.121 | **−0.62 SD** | −0.125 | steep monotonic decline (no "ages up") |
| OAA (outcome) | −0.108 | −0.55 SD | −0.066 | declines *steeper* than naive implied |
| jump-total | −0.095 | −0.49 SD | −0.100 | burst-driven |
| **reaction** (read) | −0.060 | −0.19 SD | **+0.006** | slow decline — age-resistant, but NOT rising |
| **route** (efficiency) | +0.064 | +0.20 SD, peak ~33 | −0.021 | genuinely improves — learned compensation |

**What the correction reveals:**
1. **burst declines monotonically and steeply** (−0.62 SD by 33) — the athletic component ages as physics demands.
2. **reaction is age-resistant but still declines** (−0.19 SD); the naive "+0.006 / ages-up" was pure survivorship (only read-retaining vets still play OF at 32+).
3. **route genuinely improves with age** (peaks ~33) even within-player — a *learned compensation* for lost burst (consistent with route negatively predicting OAA in Test 3: efficient routes are what slowing fielders rely on).
4. **OAA's true age decline is steeper than the cross-section shows** (slope −.108 vs naive −.066) — survivorship hides defensive aging.

**Coherent story:** aging OF lose burst (athleticism) → reaction fades slowly → they compensate with better routes → net range (OAA) declines ~0.55 SD from 27 to 33. *Caveat:* residual dynamic survivorship (players who collapse then leave OF) is unobservable, so even these within-player declines are conservative (lower bounds).

### (naive, biased — retained to show the artifact)
| age band | reaction | burst | route | jump-total | n |
|---|--:|--:|--:|--:|--:|
| <25 | −0.06 | −0.20 | +0.03 | −0.23 | 162 |
| 25–27 | −0.07 | −0.14 | +0.03 | −0.19 | 169 |
| 28–30 | −0.04 | −0.19 | +0.07 | −0.17 | 127 |
| 31–33 | **+0.03** | −0.03 | −0.01 | −0.05 | 48 |

**The athletic component ages, the cognitive components don't.** Burst (explosiveness) declines steadily through the prime; reaction (instinct) declines slowly and even ticks *up* for older players; route (efficiency) holds or improves with age. Net jump peaks young (athleticism-driven, like sprint speed) but the decline *decelerates* as veterans substitute better reads/routes for lost burst — the classic "lost a step but takes a great route" profile. **Answers the prompt's "do elite route runners age slower?" — yes: route/reaction are the age-resistant pieces.**

## Test 3 — predictive value for FUTURE OAA (leakage-safe: never same-season)
**Safeguard in action:** same-season jump→OAA is r=+0.83 (circular — same tracked plays). The honest *future* number is far lower. corr(predictor_t, OAA_t+1), n=516:

| predictor_t | → OAA_t+1 |
|---|--:|
| OAA (baseline) | +0.64 |
| **burst** | **+0.59** |
| jump-total | +0.58 |
| reaction | +0.34 |
| route | **−0.15** |

- **Burst predicts next-year OAA almost as well as current OAA does** (.59 vs .64) — a strong leading indicator.
- **Marginal value:** jump-total adds partial R²=0.048 over OAA_t; OAA_t adds 0.148 over jump. So **jump complements OAA, doesn't replace it** (~5% projection lift). Even on the high-attempt subset, jump (.65) stays just behind OAA (.68).
- **Route negatively predicts OAA** (−0.15): efficient routes are a *compensation* signal (slower fielders need them), not a range signal — do **not** use route as a positive range feature.

## Verdict on the hypothesis
Partly confirmed, usefully tempered:
- ✅ Jump components are steadier than OAA (reaction .82, burst .69 vs OAA .64).
- ✅ **Burst** is the valuable piece — predictive of future OAA *and* reliable; it's the leading-indicator that "elite jump → elite defender" really points at.
- ⚠️ Jump does **not beat** OAA at projecting defense; it adds ~5% marginal R². Use burst as a **complementary** leading indicator in the range estimate (helps most at low OAA sample, since it stabilizes faster), not as the anchor.
- ❌ Reaction (most reliable) is least OAA-predictive; route is counterproductive. Don't equate "most stable" with "most valuable."

## Safeguards (mandatory if used in modeling)
1. **Never same-season jump→OAA** (r .83 circular). Validate only against future OAA.
2. **Report marginal value over OAA**, not raw correlation (jump ⊂ OAA mechanically).
3. **MLB-only**: no jump below MLB → jump CANNOT enter the MiLB→MLB translation layer (Part 6). It's an MLB-tier refinement of an already-established defender, not a prospect signal.

## Files
- `pipeline/08_jump_aging_prediction.py`, `reports/08_jump.csv`
