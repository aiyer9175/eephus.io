# eFV lane gates, 2026-07-30 (B1 / B2 / Phase C)

Lane owner: eFV model + scoring. Plan: `docs/master-plan-2026-07-29-efv-fa.md` sections 0, B, C.
Gate standard: `docs/EFV_GATE_STANDARD.md`. Every criterion below was written before its arm
ran. A sub-floor effect is reported as a NULL, not as a small win.

Measurement harnesses (all offline, read-only unless `--write`):

| harness | what it does |
| --- | --- |
| `tools/_c_agepipe_lab.py` | Phase C accuracy gate: forward-chained pooled rho / block-rho / t45, per-fold breakdown, paired bootstrap with refit, zero-information and permutation controls. Artifact `data/xfv_agepipe_eval.json`. |
| `tools/_c_agenorms.py` | builds the C2 candidate norm table from the MiLB cache over the prospect universe. |
| scratch A/B rig | captures `efv_score.run_live` for two code states with `scored_live_path` redirected to a scratchpad, then reconstructs the board. |

**Board reconstruction, validated before any arm ran.** Board pool = the 4,517 timeseries
actives that carry a served `overall_rank`; board grade = `BOARD_GRADE_FIELD`
(`xfv_grade`), live-first then backgrade, exactly as `efv_export` merges them; tie-break =
the served rank (the real chain is `-grade, -upside, -tbs_proxy, avg_rank` and no term in it
depends on anything this lane changes). The rig reproduces the committed
`xfv_scored_live*.json` **bit-for-bit** on `xfv_grade`, `xfv_grade_display`, `rank_war` and
`surplus_mm`, and reproduces the plan's own independently measured
**top-100 pitcher share = 8**. Reconstructed vs served rank for the named cases:
seth_hernandez 49/50, jackson_flora 77/76, bradfield 88/87, arias 2/2, luis_hernandez 63/61
(the 1-2 spot residual is `data/xfv.json` being one run stale, generated_at 2026-07-28).

---

## B1 - injury factor, days-aware short-IL branch

### The defect

`_injury_factor` dispatched on the IL type string only: `"60" -> 0.70`,
`"15"/"10" -> 0.82`, **else -> 0.90**. Measured on the shipped live matrices, the board
only ever carries three designations, and `"10"`/`"15"` is **never** one of them:

| il_type | hit rows | pit rows | old factor source |
| --- | --- | --- | --- |
| `7-day` | 133 | 178 | the else-branch, 0.90 |
| `60-day` | 47 | 90 | 0.70 |
| `full-season` | 21 | 32 | the else-branch, 0.90 |

The MiLB 7-day IL is the default landing spot for **any** minor-league injury, so it carries
no severity information, and it was being priced as a serious one. seth_hernandez: `7-day`,
**4** trailing IL days, 1 stint -> 0.90 -> -1.25 FV -> 18 board spots. The same branch also
priced the MiLB **full-season** IL (out for the year) at 0.90, i.e. *milder* than an MLB
60-day stint.

### Pre-registered gate

Bounded board-movement battery, not an accuracy gate: this is an owner-directed policy
overlay, and the resolved eval pool cannot adjudicate it (same argument as `_age_factor` /
`_role_factor`). Ship criteria, written first:

1. Every live row's factor stays in [0.5, 1.0] and moves **only upward** vs the retired
   dispatch (this fix is relief; a harsher row would mean a second, unauthorized change).
2. Rows already at or past the mild saturation point are **byte-identical**.
3. Top-25 unchanged; top-100 churn <= 2 rows; per-side pitcher share not reduced.
4. A pinned test companion to `test_injury_factor_bounds`.
5. Owner directives preserved: post-TJ status alone = no penalty; healthy = no penalty.

### Result: SHIP

Mechanism: severity types keep a type-based factor; the uninformative ones (7-day and
anything unrecognized) ramp from `_IL_MILD_DAY0 = 0.99` at day 0 to `_IL_MILD_FLOOR = 0.90`
at `_IL_MILD_FULL_DAYS = 30` trailing IL days, then the existing 60/120-day and 3-stint
chronicity modifiers apply unchanged. The ramp **saturates below the first modifier
threshold**, so days are never double-counted: every row a modifier can reach is already
pinned where the old code put it.

One guard the naive version needed. 30 live rows are on the IL with `il_days_12mo = 0`
**and** `il_stints_12mo = 0`. That is not a fresh placement, it is a placement older than the
365-day window (`storage._health_profile` counts open stints with their elapsed days) - they
were placed 2025-03 to 2025-07 and are still on the IL, i.e. the **longest** absences on the
board. A pure days ramp would have handed them a free pass. `0 days AND 0 stints` is
therefore read at the saturated floor, while a player placed *today* (stints=1, days=0) is
correctly day 0. Those 30 rows are byte-identical to the old code.

| measurement | value |
| --- | --- |
| distinct (type, days, stints) shapes on the live board | 361 |
| shapes whose factor moves | 45, **all upward** |
| live rows whose factor moves | 85 of 501 on-IL (max +0.090) |
| live rows whose `xfv_war_6yr` moves | 72 (mean 0.069, max +0.55, seth_hernandez) |
| live rows whose **board grade** moves | 29 (mean 0.49 FV, max **+1.2 FV**, ike_irish) |
| backgrade rows affected | 1 (only 1 of 5,068 carries an injury factor at all) |
| board ranks moved | 405 of 4,517, max \|move\| 38 |
| top-100 churn | ramon_ramirez in, dillon_lewis out |
| top-25 churn | none |
| top-100 pitcher share | 8 -> 8 |
| mean on-IL factor | hit 0.793 -> 0.802, pit 0.760 -> 0.766 |
| **seth_hernandez** | grade 55.5 -> 56.4, board rank **49 -> 31** (the plan's 18 spots) |

All five criteria pass. Tests: `test_injury_factor_short_il_is_days_aware` and
`test_injury_factor_matches_the_committed_live_board` in `test_efv_score.py` (the second
asserts the monotone-upward property against a verbatim copy of the retired dispatch, over
every shape the shipped live matrices actually carry).

### B1b - MiLB full-season IL severity: OWNER DECISION, dial defaulted to incumbent

Making the else-branch days-aware **forces** a decision on `full-season`: leaving it there
would relieve season-ending injuries that have not yet accrued trailing days (a full-season
row at 7 days would read 0.97), which is a worse defect than the one B1 fixes. So it now has
its own branch - but pinned to the **incumbent 0.90** (`_IL_FULL_SEASON = _IL_MILD_FLOOR`),
because moving it to `_IL_SEVERE` is board movement the owner has not authorized. Measured
effect of flipping it to 0.70:

| measurement | value |
| --- | --- |
| live rows whose factor moves | 64 (all downward, -0.15 to -0.20) |
| live rows whose board grade moves | 21 (mean 1.26 FV, max **-2.3 FV**, james_ellwanger) |
| board ranks moved | 674 of 4,517, max \|move\| 96 |
| top-100 / top-25 churn | none / none |
| top-100 pitcher share | 8 -> 8 |

Recommendation: flip it. Out for the season cannot be milder than out for two months. One
line, `_IL_FULL_SEASON = _IL_SEVERE`.

---

## B2 - backgrade-path factor coverage: option (b), exemption documented, NOT excluded

### What the path actually is

`run_backgrade` scores 5,068 rows: 2,527 `debuted`, 2,284 `bust`, **257 `active`**. The
2,525 / 1,279-pitcher figure in the plan is the **`xfv_provisional`** count (prior-anchored,
no MiLB block), which spans all three kinds - it is not the population of the injury block at
`efv_score.py:1746`. The 257 `active` rows are the ones that matter: they are on the served
board because `run_live` abstains on rows with no pro track record, and they are **all**
provisional. Board composition is exactly 4,260 live + 257 backgrade-active = 4,517.

### Why the path is bare, audited term by term

- **debuted / bust (4,811 rows): deliberately exempt.** `_age_factor` and `_role_factor` are
  both documented "LIVE board only, never the resolved eval", and these rows are anchored at
  a historical snapshot whose age is the age *at that season*. Taxing a 2016 graduate's
  as-of-2015 grade with a 2026 age penalty is a category error.
- **age / role on the 257 active rows: unreachable, not exempt.** `_age_factor` reads
  `age_now` / `milb.age`; the backgrade row dict carries neither, so the penalties were dead
  code - the same shape as the 2026-07-14 fix that wired the IL fields in after finding the
  backgrade injury penalty dead. The owner directive ("a 26.9yo AA reliever must not rank
  top-100") was therefore open on the one cohort the model cannot see.
- **statcast tilt / S-XLINE lean: declined, with the number.** Both price a MODEL-leg
  production signal, and 2,525 of these rows are prior-anchored with no model leg at all -
  the tilt would land on a consensus/draft-slot anchor. Measured: exactly **1** of the 257
  active rows carries a `statcast_plus`, tilt **1.007**, which cannot move a 0.1-rounded
  grade. B4 is separately re-gating overlay level-reliability; this is its lane, not B2's.
- **side-fairness: declined, structurally.** It reassigns a per-side scored pool's top-band
  display-value multiset. This path has no pool; it maps onto `run_live`'s grade scale
  (`_build_grade_map`), which the fix has already been applied to. Running it again
  double-applies.

### Decision

**Option (b): exemption documented in code, plus wire the two owner directives shut.** Age
and role are now applied on the `kind == "active"` branch. **Measured blast radius: zero.**
Of the 257 active rows, 8 have a resolvable age at all and **none is over 25.0**, and none is
RP-designated at 25+, so every factor is exactly 1.0 and `inj * agef * rolef == inj`
identically - every served grade, rank and dollar is byte-identical. This closes a directive,
it does not move the board.

**Top-100 eligibility is NOT restricted**, against the plan's suggested alternative. Measured:
excluding this path deletes **10 of the served top 100** - roch_cholowsky #4, eric_booth_jr
#25, tyler_bell #32, grady_emerson #46, vahn_lackey #47, drew_burress #62, aj_gracia #71,
jackson_flora #77, zion_rose #89, jacob_lombard #92 - i.e. the entire top of the 2026 draft
class, whose only defect is not having played a pro game. `xfv_provisional` already flags
them for any consumer that wants to treat them differently.

**Latent risk logged, not fixed here:** 249 of the 257 active rows have **no birth_date and
no age** in the timeseries payload, so the age directive cannot bind on them even now. That is
an ingestion gap on freshly signed players, not a scoring gap. If an old no-track-record
signee ever lands on the board with a missing birth date, the ramp will read 1.0.

---

## Phase C - age pipeline

Accuracy arbiter for every C arm: `tools/_c_agepipe_lab.py`, artifact
`data/xfv_agepipe_eval.json`. Forward-chained shipped guarded blend, **8 independent time
splits** (2017-2024, gate standard 2.4) reported alongside `SCORED_YEARS` (2020-2023) for
comparability; pooled rho **and** fold-block-normalized rho (the two-metric gate's rank half);
FV45-fringe t45; paired bootstrap **B=250 resampling train AND test with a refit per draw**;
zero-information controls. Base arm reproduces the shipped `milb.age` and
`milb.age_rel_level` columns with max abs error **0.00e+00** on both sides before anything
else runs. Test rows: 1,522 hit / 1,591 pit; base rho 0.2455 hit / 0.1845 pit.

Full-pool debut/no-debut AUC is deliberately **not** used: no C arm can sense MiLB-block
missingness (every matrix row in the eval carries a block), but pooled rho and block-rho are
the admissible pair either way and adding a third metric would only widen the multiple-
comparison surface on arms that are all nulls.

### C1 - decimal season-midpoint age, unconditionally

`efv_dataset.py`: the decimal branch was gated behind `if age is None` and was therefore
**dead** - the model saw an integer StatsAPI age on 4,260 of 4,260 live rows. Precedence is
now reversed: decimal preferred, integer as the fallback.

**Pre-registered gate: no-regression + a zero-information control.** Explicitly NOT an
accuracy claim (a prior decimal probe read 0.3308 -> 0.3291). The zero-information control
is the honest one for this change: integer age plus a **row-permuted fractional part**, so it
has c1's exact marginal distribution and zero information about the row.

| arm | hit rho | hit block | hit t45 | pit rho | pit block | pit t45 |
| --- | --- | --- | --- | --- | --- | --- |
| c1 (delta vs base, 8 folds) | +0.00030 | -0.00020 | +0.0133 | +0.00180 | +0.00010 | -0.0085 |
| **c1 zero-info control** | -0.00050 | +0.00000 | +0.0022 | **+0.00170** | +0.00140 | -0.0075 |
| MDE95 | 0.017 | 0.0149 | 0.055 | 0.016 | 0.0149 | 0.10 |

SCORED_YEARS: hit +0.00020, pit +0.00020. Per-fold: 3 of 8 positive on each side. Paired
bootstrap: hit mean **-0.0009** CI95 [-0.0137, +0.0071] P(positive) 0.424; pit mean
**-0.0006** CI95 [-0.0131, +0.0104] P(positive) 0.464.

**Verdict: SHIP as a CORRECTNESS fix. There is no accuracy result here, in either
direction.** The pit point estimate (+0.0018) is reproduced entirely by the
zero-information control (+0.0017), the bootstrap means are very slightly *negative*, every
interval straddles zero, and everything is 10-20x inside the floor. Said plainly: the
instrument cannot tell decimal ages from integer ages, so the case for shipping is the
correctness case only -

- the StatsAPI baseball age is `floor(age at June 30)`, so it loses a mean **0.52 yr**;
- worse, it loses a *different* amount by birth month, flattering a July-born player by up to
  **0.91 yr** against a June-born one at the same true age;
- an integer age meeting an integer norm manufactures a fake neutral: **752 of 4,260** live
  rows (17.6%) sat at `age_rel_level` exactly 0.0.

**Data-conflict guard (added on measurement, not planned).** The first run moved one age by
**9.0 years**: a `luis_gonzalez` carrying birth_date 2005-07-15 against a StatsAPI age of 23
in 2019, i.e. a birth date bound to the wrong player. The two ages can only differ by under a
year by construction, so a wider gap is a data conflict and `AGE_CONFLICT_MAX_YR = 1.05` keeps
the feed's own age. Affected: 4 labeled-matrix rows (1 hit, 3 pit), **0 live rows**. With the
guard, max age move is exactly 1.0 yr.

**C1 is inert against today's artifacts** - it changes a matrix-build input, and the
prebuilt matrices already carry integer ages. Forward blast radius, simulated by patching
`age`/`age_rel_level` on both the labeled and live matrices exactly as the shipped code now
would and re-running `run_live`:

| grade band | rows | grade moved | mean \|dFV\| | max \|dFV\| |
| --- | --- | --- | --- | --- |
| 20.0 (floor) | 3,140 | 99 | 4.76 | 8.90 |
| 20.0-35.0 | 487 | 481 | 1.79 | 7.70 |
| 35.0-45.0 | 360 | 341 | 0.60 | 2.90 |
| 45.0-50.0 | 165 | 107 | 0.22 | 0.60 |
| 50.0-55.0 | 54 | 43 | 0.20 | 0.40 |
| 55.0+ | 54 | 37 | 0.14 | 0.30 |

Board: 4,403 of 4,517 ranks move, max \|move\| 3,129; top-25 unchanged; top-100 churn 1 in
(dillon_lewis) / 1 out (thomas_white); top-100 pitcher share 8 -> 7. Named cases:
**bradfield 88 -> 91** (-0.1 FV), **arias 2 -> 2** (-0.1 FV), **luis_hernandez 63 -> 63**
(-0.1 FV, i.e. very slightly worse, as the plan predicted), seth_hernandez 31 -> 33.

Read that table carefully before the next rebuild: **the row count is large and the top of
the board barely moves.** The big numbers all sit where projected WAR is near zero and the
WAR-to-grade map is near-vertical (trystan_vrieling: WAR -0.01 -> +0.20 is grade
20.0 -> 28.9). That steepness is a pre-existing property of the grade floor
(`BOARD_GRADE_FIELD` provenance already accepts ~3.1k rows on 20.0), not something C1
introduces, but it does mean the rebuild will publish thousands of large rank moves inside
the floor block, and `BOARD_RANK_BASIS_EPOCH` does not gate them.

**Interaction found, and it is the one worth escalating.** Several of the largest upward
moves are pitchers who got *older*. That is the inverted pit `age` coefficient (+0.0589
against a declared -1) getting finer-grained input to act on: decimalization gives the
wrong-signed term more resolution. C1 does not create the defect, but it does amplify it,
which strengthens the C4 case rather than the reverse. Do not rebuild the pitcher matrix
expecting C1 alone to be neutral.

### C2 - prospect-filtered decimal per-level norms: NULL, NOT SHIPPED

Built for the first time (`tools/_c_agenorms.py`): decimal season-midpoint medians over the
tracked prospect universe (6,880 players with birth_date + mlbam), under the **same** exposure
gate `_milb_features` applies when it picks a primary level (>= 50 PA / >= 60 BF), 32,616
qualified prospect-season-level rows, seasons 2014-2026.

| level | eFV static | `eta.EXPECTED_AGES` | live empirical (contaminated) | **C2 prospect-filtered decimal** | n |
| --- | --- | --- | --- | --- | --- |
| DSL | 18.0 | 18.0 | 18.28 | **18.10** | 3,216 |
| CPX | 19.0 | 18.5 | 19.78 | **19.58** | 3,652 |
| A | 20.0 | 21.0 | 21.79 | **21.45** | 6,779 |
| A+ | 21.0 | 22.0 | 23.03 | **22.77** | 6,154 |
| AA | 22.5 | 23.0 | 24.58 | **24.08** | 6,361 |
| AAA | 24.0 | 24.0 | 26.32 | **25.86** | 6,454 |

So the site and the model really do tell opposite stories, and the model's table is the
younger of the two by up to **1.86 yr**. The prospect filter is real but modest - it pulls AAA
from 26.32 to 25.86 and AA from 24.58 to 24.08 - so most of the gap is not veteran
contamination, it is that the hand-set table describes an aspirational prospect rather than
the median prospect who plays the level. Side split worth recording: pitchers run
**0.5 to 1.0 yr older than hitters at every level** (AAA 26.08 vs 25.56, A 21.97 vs 20.98)
and the model norms both sides off one table.

Pre-registered gate: full `EFV_GATE_STANDARD` (never evaluated before; the 2026-07-25 probe
`tools/_av_agelevel_verify.py:25` tested `eta.EXPECTED_AGES`, not the empirical norms).

| arm | hit rho | hit block | pit rho | pit block | SY hit | SY pit |
| --- | --- | --- | --- | --- | --- | --- |
| c2 | +0.00050 | +0.00010 | **-0.00190** | **-0.00510** | +0.00110 | **-0.00750** |
| c2 zero-info (perm) | -0.00240 | -0.00260 | -0.00330 | -0.00260 | -0.00130 | +0.00070 |
| c2 feature-killed (zero) | -0.00230 | -0.00230 | -0.00230 | -0.00260 | -0.00110 | +0.00250 |
| c1c2 (coupled) | +0.00140 | +0.00140 | **-0.00250** | **-0.00630** | +0.00170 | **-0.00890** |

Paired bootstrap: c2 hit +0.00099 CI95 [-0.0093, +0.0123] P 0.628; c2 pit **-0.00138** CI95
[-0.0195, +0.0194] P 0.412. c1c2 pit **-0.00233** CI95 [-0.0236, +0.0152] P 0.408. Per-fold
5 of 8 positive both sides for c2; the pit side carries a -0.046 fold.

**Verdict: NULL - NOT SHIPPED.** Every effect is 3-10x inside MDE95, every interval straddles
zero, and the sign on the pitcher side (the side with no `level_rank` feature, where
`age_rel_level` has the most work to do) is **negative on both fold sets and on block-rho**,
worst on `SCORED_YEARS` where c1c2 reads -0.0089. `_TYPICAL_LEVEL_AGE` stands. The measured
table is published as the **reconciliation reference for the DISPLAY tables** rather than
forced into the model on sub-floor evidence, which is the coherence half of the ask without
the unmeasured half. Owner note: the site/model disagreement is real and the fix belongs on
the display side, where it needs no accuracy gate.

### C3 - hard gates to continuous ramps

Four separate arms, each with its own blast radius.

#### C3-AGE: `_age_factor` onset dial. SHIPPED OUTPUT-NEUTRAL; onset is an OWNER DECISION (D2)

`_AGE_PENALTY_ONSET = 25.0` is now a named module constant with the ramp in a pure helper
(`_age_ramp`). Slope (`0.10/yr`) and floor (`0.75`) are held fixed while the onset moves, so
the dial has exactly one meaning. **Verified arithmetically identical to the retired hard
gate at every age** (None, 20, 24.9, 25.0, 25.1, 26, 27, 27.5, 28, 40), so the commit moves
nothing. Do not pick the onset from an accuracy metric: the debuted-only eval pool is
survivorship-censored against the never-debut old-prospect class the ramp exists to price,
which is why it shipped owner-directed rather than fitted.

Measured board effect of each candidate onset, against the shipped 25.0:

| onset | live grades moved | mean \|dFV\| | max \|dFV\| | ranks moved | max \|drank\| | top-100 in/out | top-100 P | **bradfield** | arias | seth_h | luis_h |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **25.0 (shipped)** | 0 | 0.000 | 0.0 | 0 | 0 | 0/0 | 8 | **88** | 2 | 31 | 63 |
| 24.0 | 263 | 0.490 | -2.3 | 1,146 | 86 | 0/0 | 8 | **100** | 2 | 31 | 63 |
| 23.0 | 437 | 0.793 | -4.3 | 1,227 | 145 | 2/2 | 8 | **123** | 2 | 31 | 63 |
| 22.0 | 635 | 1.031 | -5.4 | 1,295 | 175 | 6/6 | **6** | **131** | 2 | 30 | 60 |

Top-100 churn detail. onset 23.0: in chris_hacopian, jared_grindlinger; out
**enrique_bradfield_jr**, seaver_king. onset 22.0: in blake_mitchell, chris_hacopian,
jared_grindlinger, justin_lebron, ryder_helfrick, trevor_condon; out emmanuel_rodriguez,
**enrique_bradfield_jr**, gage_wood, hagen_smith, james_tibbs_iii, seaver_king.

Two things the owner should weigh. Onset 24.0 is the smallest change that moves Bradfield out
of the top 100 (to exactly 100, and 123 at onset 23.0). And **onset 22.0 costs two pitchers
out of the top 100 (8 -> 6)**, which runs directly against what Phase A is trying to repair -
old-for-level is more common on the pitcher side (366 of the 489 rows pinned at
`age_rel_level` +3.5 are pitchers), so an early onset taxes pitchers hardest. My reading:
22.0 is the wrong end of the dial for that reason, and the real choice is 24.0 vs 25.0. It is
still the owner's call and I have not moved the default.

Bradfield's numbers differ from the plan's (83 -> 104 at onset 23) because this baseline is
post-B1 and the reconstruction is the rig described above; direction and ordering agree.

#### C3-ROLE: `_role_factor` staircase to ramp. SHIPPED

The retired form stepped **twenty points** of projected WAR at exactly age 25.0 (1.0 -> 0.80)
and another ten at 26.0. It is now the same ramp as `_age_factor` - same -0.10/yr slope,
moving with the same owner onset dial - offset by `_ROLE_RAMP_OFFSET_YR = -1.5`, which is
*derived*, not tuned: with that slope it is the offset that makes the ramp pass through the
retired staircase's own tier midpoints, (25.5, 0.80) and (26.5, 0.70). Each tier's central
tendency stays where the owner directive put it instead of being re-tuned under cover of a
shape fix. Floor stays 0.70; the RP-designation and `model_war >= 1.5` gates are untouched.

Blast radius: **12 live rows** move the board grade (mean 0.575 FV, max -1.4 FV,
alexander_alberto); 208 of 4,517 ranks move, max \|58\|; **no top-100 or top-25 churn**;
pitcher share 8 -> 8. The whole affected population, in served-rank order:

| player | grade | rank | pos | age |
| --- | --- | --- | --- | --- |
| jacob_kmatz | 47.4 -> 47.3 | 182 -> 184 | SIRP | 23.8 |
| miguel_mendez | 46.3 -> 46.1 | 231 -> 243 | SIRP | 24.1 |
| tucker_musgrove | 45.4 -> 45.0 | 285 -> 319 | SIRP | 24.5 |
| alexander_alberto | 45.0 -> 43.6 | 321 -> 369 | SIRP | 24.7 |
| javen_coleman | 44.0 -> 42.7 | 360 -> 395 | SIRP | 24.7 |
| andrew_baker | 42.6 -> 42.9 | 396 -> 391 | SIRP | 26.3 |
| brody_brecht | 42.4 -> 42.1 | 402 -> 413 | SIRP | 23.8 |
| cooper_hjerpe | 42.1 -> 42.2 | 413 -> 411 | MIRP | 25.4 |
| tekoah_roby | 41.4 -> 40.1 | 437 -> 495 | MIRP | 24.9 |
| matt_jachec | 40.2 -> 40.8 | 495 -> 469 | MIRP | 25.0 |
| alonzo_tredwell | 38.5 -> 37.9 | 577 -> 595 | MIRP | 24.2 |
| yordanny_monegro | 37.7 -> 37.4 | 611 -> 630 | SIRP | 23.8 |

Nine move down (the 23.5-25.5 band now carries the small penalty the staircase gave it for
free), three move up (25.0-26.3, where the staircase was harsher than the ramp). Nothing
inside the top 180. This is a correctness fix on a tiny population, exactly as the plan said.

#### C3-CLIP: `age_rel_level` hard clip to smooth saturation. NULL - implemented, DEFAULT OFF

The asymmetry is real and measured: **489 live rows pinned at exactly +3.5** (123 hit, 366
pit) against **4** at -3.5, so in practice the cap protects old-for-level org filler and
essentially never touches a young-for-level prospect. `AGE_REL_SOFT` replaces the clip with a
`tanh` saturation over the same effective range (odd, monotone, derivative 1 at 0, so small
gaps are untouched and only the extremes bend).

| arm | hit rho | hit block | hit t45 | pit rho | pit block | pit t45 |
| --- | --- | --- | --- | --- | --- | --- |
| c3clip | +0.00630 | +0.00270 | -0.0183 | +0.00140 | -0.00040 | +0.0033 |

SCORED_YEARS: hit -0.00030, pit +0.00180. Paired bootstrap: hit +0.00013 CI95
[-0.0043, +0.0037] P 0.556; pit +0.00006 CI95 [-0.0032, +0.0031] P 0.512. Per-fold 4 of 8
positive on hit, and the +0.0063 hit point estimate is **one fold carrying +0.0426**.

**Verdict: NULL.** 0.37x the hit MDE95, driven by a single fold, hit t45 *down* 0.018, and the
bootstrap collapses it to +0.0001. The gate standard does not license shipping a feature-shape
change on sub-floor evidence, so `AGE_REL_SOFT = False`. The dial exists, is pinned by test,
and is off; flip it only on a new gate or an explicit owner call on the asymmetry argument.

#### C3-ETA: `eta.py` integer-diff staircase to interpolation. IMPLEMENTED, DEFAULT OFF, GATE **OWED**

The shipped `age_adj` is a nine-tier staircase on `diff = age - level_median` that jumps
0.35-0.40 yr of projected ETA at every integer boundary: `diff` -0.99 and -1.00 are a
hundredth of a year apart in age and **0.40 yr** apart in forecast ETA. `age_adj_for_diff`
now holds both forms; `AGE_ADJ_CONTINUOUS` interpolates the staircase's own boundary knots
and clamps past +/-4, so every boundary value is preserved exactly and only the interior
smooths (-0.99 now differs from -1.00 by 0.004 yr). The one deliberate difference is the dead
zone: the staircase returns a flat 0.0 across the whole open interval (-1, +1), the ramp
passes through (0, 0), so a 0.7-yr-old-for-level prospect gets +0.245 yr rather than nothing.

Verified byte-identical to the staircase over `diff` in [-6, +6] at 0.01 steps with the flag
off, exact at all eight knots with it on, and monotone non-decreasing throughout.

**GATE OWED, not passed.** ETA is a forecast with censored outcomes, so its arbiter is
`eta_backtest.py`'s KM/censoring-aware protocol, which needs a resolved-cohort rebuild this
lane is not permitted to run. Flipping the flag without that backtest would ship an
unmeasured change to every ETA on the site. Registered here as owed.

#### C3-TBS: `age_level.py` 5-tier staircase. NO CHANGE - the premise does not hold

Audited rather than converted, and the finding is that there is nothing to convert:

- The **number is already continuous**, and the number is what every scoring consumer reads.
  `diff` feeds `$DvM+`'s trajectory term (`storage`: `age_term = -diff`), the GRPO
  `age_vs_level` feature, and `bayes_trade_value.age_for_level_buffer`
  (`years_young * 0.30`, capped) - all linear in `diff`, none tier-aware.
- **Nothing in the board ordering reads a tier.** `storage._tbs_proxy` is tool composite +
  Statcast+ + the '+' upside flag + an IL drag. It never touches age-for-level, so the
  "TBS staircase reorders the board through `fvCmpDesc`" hypothesis is false and the measured
  board movement from this file is **zero rows**.
- The tiers are a **display label** (plus two org counters and the spotlight riser/faller
  gate), and a label must agree with the number printed beside it. `diff` is rounded to 1dp
  for display, so bucketing the *unrounded* value would put "-2.0 / young for level" on
  **155 of 4,254** live cards - trading a phantom problem for a visible contradiction.

Recorded as a docstring block in `age_level.py` so the next continuity pass does not
re-open it.

**Real bug found next door, NOT in this lane's files:** `storage.py` (org rollup) tests
`avl.tier == "very-old"`, a tier `age_level` never emits - the vocabulary is
`very-young / young / neutral / old / too-old`. So `very_old_count` is permanently 0 and the
farm Readiness net (very_young - very_old) is one-sided. Renaming the tier from this side
would break every other consumer of the documented vocabulary, so it is handed to the
`storage.py` owner.

### C4 - pitcher age terms

#### C4(a) drop pit `age`: NULL - KEEP the feature, KEEP the chip hidden

Independently re-measured on this harness, not taken on trust:

| base arm | keep rho | drop rho | delta for dropping | pit MDE95 |
| --- | --- | --- | --- | --- |
| shipped columns | +0.18450 | +0.18870 | **+0.00420** (0.26x floor) | 0.016 |
| under C2 norms | +0.18260 | +0.18360 | **+0.00100** (0.06x floor) | 0.016 |

+0.0042 reproduces the registered sign-audit's +0.00377 (`data/xfv_sign_audit.json`) to within
a rounding, on a different fold set and a different harness. That audit already ran the full
gate: paired bootstrap B=2000 CI95 [-0.0089, +0.0175] P(drop helps) 0.68, zero-information
control +0.00252 (two thirds of the "gain" reproduced by destroying the column's information
without removing it), permutation p 0.382, helps in 4 of 11 folds.

**Verdict: NULL. Leave the feature in, keep the chip hidden, document why** - which is exactly
the outcome gate standard section 6 requires ("do not add and do not remove features on
sub-floor evidence"). The declaration stays 0 with the omitted-variable note, and
`_EXPLAINER_SKIP_SIDE = {"pit": {"age"}}` stays: the sign has not become defensible, and a
confounded coefficient must not be narrated to a reader as that player's age.

One new piece of information, from C1's forward simulation: decimalizing ages gives the
wrong-signed pit `age` coefficient **finer resolution to act on**, and several of the largest
upward grade moves in that simulation are pitchers who got older. That is not evidence for
dropping (still sub-floor) but it is evidence that the pitcher head, not the age column, is
the thing to fix - i.e. it belongs to Phase B7, after Phase A lands.

#### C4(b) pit `age_rel_level` under the C2 norms: NULL

This is the pitcher half of the C2 arm: rho -0.00190, block-rho **-0.00510**, SCORED_YEARS
**-0.00750**, bootstrap -0.00138 CI95 [-0.0195, +0.0194] P 0.412. Negative on both fold sets
and on block-rho. **NOT SHIPPED.** The pit side is where `age_rel_level` should matter most
(`_FEATURES_PIT` has no `level_rank`, so `age` is the only term that can absorb how far an arm
has climbed) and it is the side the new norms hurt, which is worth remembering before anyone
re-opens this.

---

## Combined lane blast radius on today's served artifacts

Everything this lane ships, measured together against the committed live pools. C1 is not in
this number because it is inert until the next matrix rebuild (its forward estimate is in the
C1 section); C2, C3-CLIP and C3-ETA are not in it because they did not ship or shipped off.

| measurement | base -> shipped |
| --- | --- |
| board grades moved | 41 of 4,260 (mean 0.515 FV, max -1.4, alexander_alberto) |
| display grades moved | 26 (max +1.4, ramon_ramirez) |
| `xfv_war_6yr` moved | 85 (mean 0.075, max +0.55, seth_hernandez) |
| surplus dollars moved | 13 rows (max +$5.0M, ramon_ramirez) |
| board ranks moved | 530 of 4,517, max \|move\| 58 |
| top-100 churn | ramon_ramirez in, dillon_lewis out |
| top-25 churn | none |
| top-100 pitcher share | 8 -> 8 |
| seth_hernandez | 55.5 -> 56.4 FV, rank **49 -> 31** |
| bradfield / arias / luis_hernandez / flora | 88 -> 88 / 2 -> 2 / 63 -> 63 / 77 -> 78, all 0.0 FV |

Verified stable across a re-capture after the `_resolve_season_age` refactor (0 rows drift).

Not touched, deliberately: `data/xfv.json` and the golden fingerprint. `test_efv_export.py`
`test_xfv_golden_fingerprint` was **already red before this lane started** (committed
`data/xfv.json` sha a6e3f94a against golden e975a35d, file unmodified since commit 017d3bc)
and the golden may only be restamped from a production `efv_export.py --all` run, which this
lane is not permitted to make.

## Standing summary

| arm | verdict |
| --- | --- |
| B1 short-IL days-awareness | **SHIP** (bounded battery pass; 29 grades, max +1.2 FV; seth_hernandez 49 -> 31) |
| B1b full-season severity | dial added, **defaulted to incumbent**; owner decision, recommend flipping |
| B2 backgrade coverage | **option (b)** - exemption documented, age/role wired shut, measured zero movement, top-100 eligibility retained |
| C1 decimal ages | **SHIP as correctness**, no accuracy claim in either direction; inert until the next matrix rebuild |
| C1 conflict guard | **SHIP** (4 labeled rows, 0 live) |
| C2 prospect-filtered norms | **NULL - NOT SHIPPED**; table published as the display-side reconciliation reference |
| C3-AGE onset dial | **SHIP output-neutral**; onset is owner decision D2, table above |
| C3-ROLE ramp | **SHIP**; 12 rows, none inside the top 180 |
| C3-CLIP soft saturation | **NULL - implemented, DEFAULT OFF** |
| C3-ETA interpolation | implemented, **DEFAULT OFF, gate OWED** (`eta_backtest` KM protocol) |
| C3-TBS age_level tiers | **NO CHANGE** - premise refuted, zero board rows; storage `"very-old"` bug reported |
| C4(a) drop pit age | **NULL** - keep feature, keep chip hidden |
| C4(b) pit age_rel_level on C2 norms | **NULL** - not shipped |
