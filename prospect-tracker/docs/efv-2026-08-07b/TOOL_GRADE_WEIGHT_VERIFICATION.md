# TOOL GRADE WEIGHT VERIFICATION (Lane V, 2026-08-08)

Adversarial verification of lane BA2, the only lane in the 2026-08-07b program that was
never independently checked. Target artifacts, both READ ONLY here:

- `data/ba_tool_grade_eval.json` (top-level `verdict: SHIP_SOME`)
- `docs/efv-2026-08-07b/TOOL_GRADE_WEIGHT_GATE.md`
- registry row `ba_tool_grade_weight` (`verdict: provisional`)

Everything below was recomputed from `prospects.db` (opened `mode=ro`) by three probe
scripts written for this lane only. They import NOTHING from `tools/ba_tool_grade_lab.py`,
`source_backtest.py`, `efv_tools.py` or `consensus.py`. The five constants
(`MIN_LAG_YEARS=3`, `WEIGHT_SHRINK_K=150`, `WEIGHT_CLAMP=(0.6,1.5)`, `SPEARMAN_FLOOR=0.05`,
window `-01-01`/`-05-01`) and the tool-to-stat map were READ out of the repo modules and
retyped, so a wrong constant would have shown up as a mismatch rather than being inherited.
Spearman, AUC, the shrunk weight estimator, the forward chain and the permutation null are
all independent reimplementations.

**BOTTOM LINE: PARTIAL.** The arithmetic is clean. Every primary number in the lane
reproduces to the last reported digit, which is unusual in this program. What does not
survive is the INTERPRETATION of the two cells the lane wrote its headline around, plus
three control claims. The lane's actual ship recommendation, "do not change
`consensus.py`", survives and is strengthened.

---

## 1. WHAT REPRODUCES EXACTLY (no copy suspicion)

Every figure in this section came out of my own probe before I compared it to the lane.

| claim | lane | mine | verdict |
|---|---|---|---|
| BA tool observations | 7,410 | **7,410** | CONFIRMED |
| BA per-key census | hit/game_pwr/speed/field 836, throw 835, fb 696, cmd 695, ch 647, sl 634, cb 404, ct 155 | **identical** | CONFIRMED |
| BA rows carrying `tools_json` | 1,535 | **1,535** | CONFIRMED |
| scoreable share | 3,899 of 7,410 = 52.6181% | **3,899 / 52.6181%** | CONFIRMED |
| arm A `hit` d_rho / d_auc | +0.013416 / +0.006575 | **+0.013416 / +0.006575** | CONFIRMED |
| arm A `game_pwr` | +0.003933 / +0.002698 | **identical** | CONFIRMED |
| arm A `speed` | +0.004258 / +0.003521 | **identical** | CONFIRMED |
| arm A `fb` | -0.006744 / -0.002765 | **identical** | CONFIRMED |
| arm A `cmd` | +0.004104 / +0.002691 | **identical** | CONFIRMED |
| every per-year derived weight, all 5 tools | see JSON | **identical to 4dp** | CONFIRMED |
| `hit` survivorship 3,740 / 1,878 / 50.2139% | | **identical** | CONFIRMED |
| B7 hitter 845/1917 = 44.0793%, BA 108/145 = 74.4828% | | **identical** | CONFIRMED |
| B7 pitcher 981/2040 = 48.0882%, BA 104/127 = 81.8898% | | **identical** | CONFIRMED |
| arm A `hit` lag 3/2/1 = +0.0134 / +0.0141 / +0.0132 | | **+0.013416 / +0.014114 / +0.013164** | CONFIRMED |
| BA shrunk weight range at relaxed lags 0.9267 to 1.1096 | | **0.9267 to 1.1096** | CONFIRMED |

Two notes on the census. The lane's own count of 7,410 / 1,535 is right and the registry
row's 7,285 / 1,502 with the per-key list 821/821/821/821/821/684/683/635/624/400/154 is
the one that does not reproduce; see the requested edit in section 6. Also, 1,535 is the
count of rows with a non-empty `tools_json`; only 1,529 of them carry at least one grade
that parses and lands inside [20, 80]. The lane's sentence is accurate as written.

**Plan Lane K0's premise ("Baseball America carries ZERO tool grades") is FALSE.**
Independently confirmed. BA publishes across 2023 to 2026 on 5 dated boards
(2023-02-15 385 rows, 2024-02-15 383, 2025-02-15 384, 2026-02-15 383, 2026-06-03 100
rank-only). This is the single most load-bearing thing the lane asserts and it holds.

## 2. THE PERMUTED-SOURCE-LABEL CONTROL WAS REALLY RUN, AND IT REPLICATES

This is the control whose absence produced the FV weights that had to be reverted on
2026-07-25, so it gets its own section.

It exists in the code (`permuted_source_null_np`), it permutes source labels within each
(player, tool, board-year) row so the grade multiset on a player is unchanged, it
re-derives the weights from scratch on the permuted data, it re-runs the full
forward-chained A/B, and its p95 IS the gate floor. That is the right construction on the
right pool.

I rebuilt it independently and ran 1,000 draws at five seeds on the `hit` cell:

| seed | F_rho | margin d_rho / F_rho | G5 (>= 2.00x) |
|---|---|---|---|
| 8641 | 0.005949 | 2.2551 | PASS |
| 1337 | 0.006048 | 2.2181 | PASS |
| 101 | 0.005929 | 2.2628 | PASS |
| 202 | 0.006053 | 2.2163 | PASS |
| 303 | 0.005767 | 2.3264 | PASS |

The lane's F_rho of 0.006049 sits at the top of my five-seed range (0.005767 to 0.006053).
p_rho is at the add-one floor (0.000999) on every seed. **The control replicates. VERDICT:
CONFIRMED.**

## 3. WHAT DOES NOT SURVIVE

### 3.1 The `hit` SHIP cell measures a tie-break, not a weight. REFUTED as framed.

The control the lane did not run is the dumbest one: **skip the estimator entirely and
apply a fixed arbitrary tilt.** Same rows, same evaluable years 2020-2025, no forward
chain, no shrinkage, no vintage rule, no data used at all beyond the direction.

| fixed weight (fg, pipeline) | d_rho | share of the lane's +0.013416 | d_auc | share of +0.006575 |
|---|---|---|---|---|
| (0.9900, 1.0100) | +0.012840 | **95.7%** | +0.006502 | **98.9%** |
| (0.9750, 1.0250) | +0.012840 | 95.7% | +0.006502 | 98.9% |
| (0.9500, 1.0500) | +0.012840 | 95.7% | +0.006502 | 98.9% |
| (0.9250, 1.0750) | +0.012840 | 95.7% | +0.006502 | 98.9% |
| (0.9000, 1.1000) | +0.012840 | 95.7% | +0.006502 | 98.9% |
| (0.8575, 1.1425) = the lane's own derived weight, held constant | +0.012840 | 95.7% | +0.006502 | 98.9% |

`d_rho` is **bit-identical across a 14-point band of tilt magnitudes.** The reason is
mechanical: tool grades live on a coarse 5-point lattice, both metrics are rank-based, and
any tilt small enough not to reorder across lattice levels produces exactly the same
ranking. The estimated weight's MAGNITUDE does no work whatsoever. All the estimator
contributes is a SIGN.

So the shipped cell does not show that a forward-chained per-source precision beats the
equal mean. It shows that MLB Pipeline's `hit` grade is better than FanGraphs' and that
breaking ties toward Pipeline helps. The lane's own section 8.3 gestures at this
(Pipeline alone 0.3215 against the equal consensus 0.2750) and deserves credit for
publishing it, but it reports the effect as "a small fraction of a gap" rather than as
"the estimator's numeric output is inert", and the headline "at 2.22x its permutation
floor" reads as if the estimator earned something.

The permutation null is not wrong here, it is just answering the narrower question. It
destroys the source labels, so it correctly tests "do the two sources differ in accuracy
at all". It does not and cannot test "is the derived weight better than an arbitrary one",
because there is nothing to test: they are the same number.

### 3.2 `fb` is not a resolved loss of the fastball tool. REFUTED.

The lane's section 8.2 calls `fb` "the finding the brief predicted and it points the WRONG
WAY: weighting the fastball tool LOSES", and 8.3 builds a mechanism on it
("where the sources are complementary, blending is right and tilting destroys the
complementarity").

Run the same zero-information control, a fixed 1% tilt in the direction the estimator
itself ends at in its final year, on all five tools:

| tool | lane d_rho (estimator) | 1% constant tilt, same direction | share | derived weight, last year |
|---|---|---|---|---|
| hit | +0.013416 | +0.012840 | 95.7% | (0.8575, 1.1425) |
| game_pwr | +0.003933 | **+0.005323** | **135.4%** | (0.9639, 1.0361) |
| speed | +0.004258 | **+0.004974** | **116.8%** | (0.9523, 1.0477) |
| fb | **-0.006744** | **+0.001492** | **-22.1%** | (1.0253, 0.9747) |
| cmd | +0.004104 | **+0.007827** | **190.7%** | (0.8548, 1.1452) |

A constant tilt matches or beats the estimator on four of five tools, and on `fb` it flips
the sign. `fb`'s per-year derived weights are 1.0230, 0.9977, 0.9933, 0.9545, 1.0035,
1.0253: they cross 1.0 four times. The negative pooled `d_rho` is the estimator changing
its mind year to year, not the fastball tool resisting weighting. **The correct statement
is that the ESTIMATOR loses on `fb`, and it loses because it is unstable, which is a
stronger argument for the lane's own recommendation than the one it made.**

### 3.3 C6.5 seed stability: the clause was reported as passing without being evaluated.

The pre-registration, section 6.5: "Re-run the bootstrap and permutation at seed 1337. A
verdict that moves between seeds is reported as unstable and treated as FAIL." The result
doc, section 8.4: "C6.5 seed stability | Seed 1337: `hit` lo95 0.007631 against 0.007728;
every verdict unchanged."

Only the bootstrap half was checked. The lane's own JSON carries the alternate-seed
permutation floor, and recomputing the gate on it:

`C65_seed_stability.perm_seed1337_200.abs_d_rho_p95 = 0.006799`
`0.013416 / 0.006799 = 1.9732`, against the G5 bar of 2.00. **G5 FAILS, so
`PREREGISTERED_SHIP` would be false and the one SHIP cell in the lane would not ship.**
The claim "every verdict unchanged" is contradicted by the artifact it cites.

In fairness to the lane: the alternate-seed null runs 200 draws against the primary's
1,000, and my five-seed 1,000-draw replication in section 2 puts the margin at 2.2163 to
2.3264 with no seed near the bar. **The underlying verdict IS stable; the reported control
is not a control.** It asserts a pass over a number it never computed, which is failure
mode G from the standing rules.

### 3.4 The self-added M2 binary DID determine the verdict, and the pre-registered
### downgrade clause was not honored.

Pre-registration section 4.1 declares the within-board-year median split as a self-added
threshold and binds itself: "If a gate verdict turns on M2 and would flip under a
different binary, section 8 says so in its first line and the finding is downgraded."

Section 8's first line instead reads "No self-added threshold determined any verdict."

I re-ran M2 under four binaries, re-measuring the permutation floor separately under each
one so `d_auc` and `F_auc` are always on the same definition (600 draws, seed 8641):

| binary | positive rate | d_auc | F_auc | margin | p | G2 (d_auc >= F_auc) |
|---|---|---|---|---|---|---|
| within-year median (shipped) | 0.503 | +0.006575 | 0.002988 | 2.20x | 0.0017 | PASS |
| within-year top tercile | 0.336 | +0.005559 | 0.003320 | 1.67x | 0.0033 | PASS |
| within-year top quartile | 0.252 | +0.003904 | 0.003624 | **1.08x** | 0.0366 | PASS (barely) |
| within-year top decile | 0.102 | +0.004227 | 0.005152 | **0.82x** | 0.1181 | **FAIL** |

G2 is a necessary condition for SHIP. Under a top-decile binary the `hit` cell does not
ship. **The verdict turns on M2 and does flip under a different binary. The lane's own
clause required this to be disclosed in its first line and the finding downgraded, and it
was not.** The median split remains the most defensible single choice, and the decile cell
has only about 126 positives, so this is a disclosure failure rather than proof the result
is wrong. But the lane wrote the clause, and the clause fired.

### 3.5 C6.4 forced-equal identity is still vacuous after being "fixed".

The lane deserves credit for spotting that the naive form returns n=0 and passes
trivially, and it says so in the artifact. The replacement, however, cannot fail either.
In `ab_pass`, the equal score `e` and the weighted score `k` are appended inside the same
loop over the same row `r`. With `weight_override = {s: 1.0}`, `k` reduces to
`sum(1.0*g)/len(sources)`, which is `e` by algebra, on rows that are by construction the
same rows. There is no asymmetry that this control could ever detect. It is `f(X) == f(X)`,
the exact pattern the standing rules name. Reported as CONFIRMED-but-vacuous. The real
protection against a row-construction asymmetry is that an independent reimplementation
reproduces all ten primary numbers, which section 1 now supplies.

### 3.6 C6.3 shuffled-outcome, as executed, does not shuffle the weight derivation.

`NPFrame.weights()` reads `self.Y` (the real outcome) even when `ab()` is called with the
`Yov` shuffled-outcome override. So in the control that ran, the weights are derived from
the REAL outcomes and only the SCORING outcome is permuted. Section 6.3 pre-registered a
stronger check. The pure-Python `shuffled_outcome_null`, which does derive weights on the
permuted outcome, is dead code and is never called (`compute_cell` calls the `_np` form).
`permuted_source_null` and `perm_weight_spread` are likewise dead. Consequence: the
control still correctly catches a row-alignment leak and it passes, so no number moves;
but the note inside the function ("with a shuffled outcome the SPEARMAN_FLOOR collapses
both sources to equal weight") describes the version that did not run.

### 3.7 The artifact's own top-level verdict contradicts the lane's recommendation.

`data/ba_tool_grade_eval.json` closes with `"verdict": "SHIP_SOME"`, set mechanically at
`ba_tool_grade_lab.py:1406` as `"SHIP_SOME" if ship else ...` whenever any gate cell is
SHIP. Section 8.8 of the gate doc says "**Do not change `consensus.py`. Equal weight
retains on all eleven tool keys.**" A reader of the artifact or of the registry row sees
SHIP_SOME and would reasonably conclude a weight is being shipped. Nothing is.

---

## 4. CONTROLS I RAN THAT DID NOT EMBARRASS THE LANE

Reported because a verification that only lists hits is not a verification.

**The bootstrap prices no weight-estimation error, and it survives anyway.** The shipped
`cluster_boot` resamples players but holds the per-year weights fixed at their real
estimates, so `d_rho`'s interval understates uncertainty. I re-ran a 1,000-draw
player-clustered bootstrap that RE-DERIVES the weights from the resampled base years
inside every draw:

| convention | mean d_rho | lo95 |
|---|---|---|
| fixed weights (shipped) | +0.013115 | +0.007447 |
| weights re-derived in-draw | +0.012004 | **+0.004612** |
| weights re-derived in-draw, d_auc | +0.005615 | **+0.001635** |

Both lower bounds stay above zero. **G3 and G4 survive the honest bootstrap.** The lane's
+0.007728 / +0.003466 are optimistic by roughly 40% but not wrong in sign.

**Nothing was pooled across tools in any gate.** Every weight in every gate cell is
indexed by tool. The pooled estimator appears once, as the declared C6.2 control, and its
finding (the pooled weight tilts toward Pipeline while FanGraphs reads `fb` better,
0.2251 against 0.2036, so a pooled weight would apply an anti-signal tilt on `fb`)
reproduces from the JSON and matches the prose. CONFIRMED.

**The survivorship boundary is stated, not smuggled.** Section 6.6 states it in advance,
every cell carries `C66_survivorship`, the debut rate is 50.1% to 53.5%, and the headline
sentence in 8.4 says "Every number in this lane is tool accuracy AMONG DEBUTS." I
reproduce `hit` at 3,740 graded / 1,878 with outcome / 50.2139%. CONFIRMED, and the lane
handled this better than most in the program.

**BA's thinness produced no manufactured weight.** Arm B returns
`NULL_NO_EVALUABLE_YEAR` on all five tools and I confirm the arithmetic reason
independently: the three-source common set has zero rows before 2023, so for board-years
2023 to 2025 the base pool at lag 3 is empty and the weights are flat, and 2026 has no
`season > 2026` outcome. Coverage 96 / 79 / 48 on `hit` reproduces exactly. At the relaxed
lags the lane reports as SENSITIVITY and forbids from shipping, I independently derive BA
weights of 0.9267, 1.0142, 1.0139, 1.1096, 0.9959 (lag 2) and 0.9292, 1.0222, 1.0208,
1.1028, 1.1005 (lag 1), a range of **0.9267 to 1.1096**, which is the lane's stated range
to the digit. **Baseball America shrinks to equal.** CONFIRMED.

**No RNG is seeded off a set or a string hash.** Seeds are the literals 8641 and 1337.
Iteration orders come from insertion-ordered dicts built off `ORDER BY snapshot_date`
queries. The one set in the analysis path (`scored_players` in `disjoint_player_pass`) is
membership-tested only, never iterated.

**Holm is arithmetically correct**, including the monotonicity step that pins `cmd` at
0.2717 rather than 0.2368, and multiplicity is reported as 1 of 10 and 1 of 5 as rule C
requires.

**Prose against JSON.** I checked every numeric claim in sections 8.1 through 8.6 of the
gate doc against the artifact. They agree, including the six per-year `hit` gains
(+0.0128, +0.0102, +0.0055, +0.0109, +0.0208, +0.0126), the 8.3 single-source table, the
C6.2 rho spreads and the shuffled-outcome ranges. The single contradiction is the top-level
`verdict` string of section 3.7. This is notably better than the program's base rate.

**No threshold was added after an unfavourable result.** G6 and G7 are labelled
`_selfadded` in the JSON keys and declared in section 8; G5's 2x bar is in the
pre-registration; and the self-added gates never flipped a cell's outcome, so the lane's
"no self-added threshold determined any verdict" is true AS RESTRICTED TO G6 and G7. It is
false once the M2 binary is counted as the self-added threshold the lane itself declared
it to be (section 3.4).

**Staleness exposure is nil.** The session's warning that the served eFV matrices
reproduce `consensus_fv_raw` on only 74.8% of rows does not bite here. The only place this
lane touches a matrix is B7, and B7 reads only `player_key` and the debut flag, which are
structural. I reproduced B7 off `debut_year` while the lab used `kind == "debuted"` and got
identical counts.

---

## 5. DISPOSITION OF EVERY EDIT THE LANE REQUESTED

The lane requests no code change to `consensus.py`. It hands two items to the orchestrator
and neither is a weighting change.

| lane item | disposition |
|---|---|
| **Do not change `consensus.py`; equal weight retains on all eleven tool keys** | **UPHELD, and strengthened.** Section 3.1 shows the one passing cell is an inert tie-break; section 3.2 shows the estimator's `fb` behaviour is instability. Both are additional reasons not to couple this into `consensus_fv_raw`. |
| **BA 2023 `position` defect (B3b): 363 of 385 rows have no position, 161 are pitchers by their `tools_json` signature, all 385 route to the hitter normalization cell, the empty pitcher cell then pools BA across the 2026 Adjusted-Grade boundary** | **NOT RE-VERIFIED HERE, and it does not need to be by me.** The registry row for `ba_source_class` records that lane BA1 independently confirmed the same 2023 position gap and that it has since been fixed. Two lanes finding it separately is the corroboration. Out of my scope and not touched. |
| **AL-only coverage asymmetry (B6): 383 of 1,660 players in the 2026 cycle gain a BA vote, 2.78 voting sources against 1.45, worth a disclosure line** | **UPHELD as a disclosure, NOT re-derived.** The 13 orgs are American League in all four vintages, which I confirmed from the board census. The 383 / 2.7781 / 1.4503 figures come from the lane's own consensus walk and I did not rebuild it. Treat them as lane-reported, not verifier-confirmed. |

I requested no edit to any file I do not own. My requested edits to files owned by others
are in section 6.

---

## 6. WHAT SHOULD CHANGE, FOR THE OWNER OF EACH FILE

1. `data/model_registry.json`, row `ba_tool_grade_weight`: the `verdict` should move off
   `provisional` now that a check has run, and the note's census figures (7,285 / 1,502
   and the 821/684/683/635/624/400/154 per-key list) do not reproduce. The correct census
   is 7,410 across 1,535 rows with 836/836/836/836/835/696/695/647/634/404/155. Exact
   old/new text is filed in this lane's `edits_requested`.
2. `data/ba_tool_grade_eval.json`: top-level `"verdict": "SHIP_SOME"` should read
   `"NO_SHIP_EQUAL_WEIGHT_RETAINS_ONE_INERT_CELL"` or equivalent, so the artifact string
   stops contradicting section 8.8. This is a one-line change at
   `tools/ba_tool_grade_lab.py:1406` plus a re-emit, or a hand edit to the artifact. I did
   not make it: the artifact is not mine.
3. `docs/efv-2026-08-07b/TOOL_GRADE_WEIGHT_GATE.md`: section 8's first line and the C6.5
   row of the 8.4 table both need the corrections in sections 3.3 and 3.4 above. That file
   is the lane's pre-registration and its RESULT placeholder is already filled, so I have
   not edited it; this document is the correction of record.

---

## 7. FINAL VERDICT

**PARTIAL.**

SURVIVES: the corrected premise (BA carries 7,410 tool observations, plan Lane K0 is
false); every primary number in all ten gate cells; the permuted-source-label control,
which was really run on the right pool and replicates across five independent seeds; the
per-tool discipline with no pooling in any gate; the stated and reproduced survivorship
boundary; Baseball America shrinking to equal at every lag with no manufactured weight;
the honest-bootstrap survival of G3 and G4; and the ship recommendation itself.

DOES NOT SURVIVE: the framing of the `hit` SHIP cell, which is 96% to 99% reproducible by
a 1% constant tilt that uses no data; the characterization of `fb` as a resolved loss of
the fastball tool, when a constant tilt in the same direction gains; the C6.5 seed-stability
pass, which was asserted over a number the lane never computed and which fails when
computed; the C6.4 forced-equal control, which remains vacuous after being announced as
de-vacuumed; the C6.3 shuffled-outcome control, which as executed leaves the weight
derivation on the real outcome; and the section 8 assertion that no self-added threshold
determined a verdict, which the lane's own M2 clause contradicts.

The lane's practical output was already the right one. Its headline was not.
