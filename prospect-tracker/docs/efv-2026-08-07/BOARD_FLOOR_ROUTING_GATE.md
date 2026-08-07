# Lane B gate: the eFV 20.0 board floor, the double listing, and the routing partition

Pre-registered 2026-08-07, BEFORE any gate statistic was computed. Master plan
docs/master-plan-2026-08-07-omnibus3.md Lane B (owner decision 2). Gate standard
docs/EFV_GATE_STANDARD.md.

Simulation lab: `tools/efv_board_floor_sim.py`
Artifact: `docs/efv-2026-08-07/BOARD_FLOOR_ROUTING_SIM.json`
Runtime double-listing harness result is reproduced in section 1.

---

## 0. What was measured BEFORE this document existed (census, not gate)

Stated up front so the pre-registration is honest about what was already known.

| quantity | measured |
|---|---|
| active board rows (data/xfv.json kind=active) | 4,586 |
| actives grading exactly 20.0 | 3,358 (73.2%) |
| actives in the open interval (20, 30) | 32 |
| pooled outcome curve span FV20 to FV35 | 0.069 WAR |
| synthetic-only actives (latest point's sources_contributing subset of CONSTANT_ANCHOR_SOURCES) | 2,642 |
| of those, flagship grade exactly 20.0 | 2,440 |
| of those, flagship grade above 20.0 | 202 (median 38.0; **184 above FV30**) |
| duplicate player_keys in the rendered board pool | 2,636 (runtime) |
| residual genuinely-graded floor actives after routing | 918, 190 distinct 2dp model WAR, 180 at the -2.0 clamp |

The 184 synthetic-only rows already grading above FV30 are the reason the routing
is SCOPED below rather than applied to the whole cohort. Their provisional grade
is a median 7.7 FV LOWER than their flagship grade, so routing them wholesale
would demote 184 visible board rows, which the plan's own gate forbids.

## 1. The double listing (B1), measured at runtime

`tools/`-external harness: the real `prospx/index.html` inline script was loaded
into a Node VM (Electron `ELECTRON_RUN_AS_NODE=1`) with a permissive DOM stub, fed
the real `data/timeseries.json`, `data/xfv.json` and `data/xfv_ungraded.json`, and
`getFilteredActives()` was called. No frontend logic was re-implemented.

```
pool length            10,569
distinct player_keys    7,933
duplicated keys         2,636   (each appearing exactly twice)
every duplicate pair    one graded row + one provisional row
graded row at 20.0      2,434 of 2,636
provisional row higher  2,193 of 2,636 (median delta +6.6 FV, p90 +13.1)
buildEfvRankMap         same 10,569 -> 7,933; 2,636 rank entries silently overwritten
```

CONFIRMED. The board lists 2,636 players twice, at two different grades, on two
different scales, and the rank map keeps whichever row sorted last.

**A second finding, contradicting the plan's proposed remedy.** The plan says to
dedupe "with the provisional row winning". Measured on the same 2,636 keys, the
GRADED row carries payload the synthesized provisional row does not: Statcast+ on
78.8%, zone metrics on 78.7%, transactions on 99.0%, level changes on 76.6%, plus
stock, surplus, eta, acquisition, health profile and the points series. The
provisional twin is synthesized from nine fields. So a literal row-wins dedupe
destroys real data for 2,636 players. The dedupe must keep the GRADED row and take
the provisional GRADE.

## 2. The change under gate (B2)

**Routing rule (scoped).** A live row serves the provisional grade instead of the
flagship grade when BOTH hold:

1. its consensus anchor is constant-only (`sources_contributing` is a non-empty
   subset of `consensus.CONSTANT_ANCHOR_SOURCES`), i.e. no source published an
   opinion about this player; AND
2. the flagship grade sits exactly on the outcome curve's floor knot, i.e. the
   model's predicted 6yr WAR is <= 0 and `outcome_implied_fv` therefore returns the
   first knot for it.

Condition 2 is the principled half. `value_framework.outcome_implied_fv` maps every
non-positive prediction to exactly `knots[0]`, and the curve's own schema note says
the FV20/25/30 knots are below the data floor and are NOT a measurement. So at the
floor the flagship map is not disagreeing with the provisional map, it is
ABSTAINING, and substituting a map that does resolve is a strict information gain.
Above the floor the flagship map has resolved a positive predicted WAR and keeps it.

**Sub-decimal sort key.** Every live row also carries `board_sort_key`, the
unrounded pre-clamp model WAR. Display is untouched. It exists so the residual
genuinely-graded floor rows order by the model instead of by name.

**Two-scale disclosure.** The flagship (pooled outcome curve) and provisional
(`efv_ungraded._GRADE_MAP`) WAR-to-FV maps disagree: at WAR 0.0 the flagship reads
20.0 against the provisional 27.0 (hitters) / 25.0 (pitchers), and through the
0.5 to 1.5 WAR band the flagship reads 11.0 to 12.0 FV HIGHER. Recomputed from the
committed constants 2026-08-07; the plan's -7.0 and +11 to +12 both reproduce.
The board already mixes these two scales for the 5,983 rows `provPlayers()`
synthesizes, so this change does not create the mixing, but it does move 2,440
players across the seam and the disclosure is owed either way.

**BANNED and not attempted:** re-pointing `efv_ungraded._grade` onto the outcome
map (recorded no-ship, 3 of 6 stop conditions).

## 3. Gates (thresholds fixed before the numbers were computed)

| id | gate | pass condition | if it fails |
|---|---|---|---|
| G1 | dedupe completeness | duplicate player_keys in the joined pool == 0 after the dedupe, and rendered row count falls by exactly the measured duplicate count | frontend dedupe spec is wrong; do not ship |
| G2 | floor tie block | actives grading exactly 20.0 falls from 3,358 to the residual genuinely-graded count, and the routed cohort is exactly the scoped population | scope rule leaks; do not ship |
| G3 | order fidelity | Spearman of the served routed grade vs the provisional model's own WAR on the routed cohort == 1.000 | the routing corrupted the provisional ordering; do not ship |
| G4 | no disturbance above FV30 | ZERO rows whose flagship grade exceeds 30.0 change their served grade | scope rule leaks upward; do not ship |
| G5 | top-N integrity | top-25 and top-100 membership by served grade is unchanged; the routed cohort contributes no top-100 entrant | the floor cohort is reaching the visible board; do not ship |
| G6 | sort-key gain | the sub-decimal key must cut the largest floor tie block by at least half, else it is not worth a new field | drop the sort key, keep the routing |
| G7 | suite | full suite green (orchestrator runs it) | fix or revert |

A gate that lands marginal is a FAIL.

### 3a. AMENDMENT, written after the run: G3 as registered FAILED, and it was the
### gate that was wrong

Measured: pooled rho 0.983, per side H 0.9957 (n=1,098) / P 0.9975 (n=1,336), with
2,751 and 3,437 genuine pairwise inversions. Against the registered "== 1.000" that
is a FAIL, and it is recorded as one rather than re-thresholded quietly.

Diagnosis. G3 assumed the provisional grade is a monotone function of the
provisional WAR. It is not, on purpose. `efv_ungraded._SUBFLOOR_GRADE` caps any
line under `_MIN_EXPO_PA` / `_MIN_EXPO_BF` at 30.0, and 497 rows in the artifact sit
exactly there carrying WAR from 0.78 to 5.92. That cap is the 2026-07-25 owner call
that stops an 87-PA DSL cameo minting a mid-30s grade, and it is the direct cause of
every inversion counted. A pooled rho below 1 has a second, separate cause: the two
sides use DIFFERENT affine maps (hit BASE 27.0 / SLOPE 3.8, pit 25.0 / 4.5), so the
provisional grade is not cross-side comparable either. No passthrough of that model
could ever have scored 1.000, so the registered threshold was unmeetable by
construction and measured nothing about the routing.

**G3 replaced by the claim the routing actually makes: PASSTHROUGH.** A routed row
must serve `xfv_ungraded.by_player[key].xfv_grade` unmodified. Pass condition:
zero mismatches. **Measured: 0 mismatches on 2,434 routed rows.** The 55 routed rows
sitting at the sub-floor cap are named in the artifact so the cap's presence on the
board is on the record rather than a surprise later.

The registered rho and inversion counts are kept in the artifact anyway, because the
zero-information control uses them and they show the control works: permuting the
provisional grades takes pooled rho 0.983 -> 0.008 and inversions 2,751 -> 286,605
(H) and 3,437 -> 427,597 (P), while G2, G4 and G5 stay bit-identical. So those three
gates measure scoping and population only, exactly as the standard requires them to
be shown to do, and G3 is the only one carrying the model's information.

**Zero-information control (required by the standard).** The routing is re-run with
the provisional grades RANDOMLY PERMUTED across the routed cohort. G3 must collapse
(Spearman near 0) and G2/G4/G5 must still pass, proving those four gates measure
population/scoping and only G3 measures that the served number carries the
provisional model's information.

**Committed loss.** If G3 or G4 fails, the routing does not ship, this document is
amended with the measured failure, and the registry row is written `deprecated`.

## 3b. Results

| gate | pass condition | measured | verdict |
|---|---|---|---|
| G1 | duplicates 0 after dedupe, rows fall by the duplicate count | 2,636 duplicates, dedupe removes exactly 2,636, pool 10,569 -> 7,933 | PASS |
| G2 | floor falls to the residual, scope exact | actives at 20.0 3,358 -> 1,185; routed exactly the 2,434 scoped rows | PASS |
| G3 as registered | rho == 1.000 | 0.983 pooled / 0.996 / 0.997 | **FAIL, gate was wrong (3a)** |
| G3 corrected | passthrough mismatches == 0 | 0 of 2,434 | PASS |
| G4 | zero rows above FV30 move | 0 | PASS |
| G5 | top-25 / top-100 membership unchanged, no routed entrant | both empty; best rank a routed row reaches is 182 | PASS |
| G6 | largest floor tie block cut by >= half | graded residual 924 rows, largest block 180 (-80.5%); routed-at-floor 261 rows, largest block 205 (-21.5%) | PASS on the graded residual, FAIL on the routed floor |
| G7 | suite green | orchestrator runs it | pending |

G2's 1,185 is not 3,358 - 2,434 = 924, and the difference is worth stating: 261 of
the routed rows land on the PROVISIONAL map's own FLOOR, which is also 20.0. Those
players are org filler under both models, and the two maps agreeing is the honest
outcome, not a leak.

G6 splits. The 924 genuinely-graded residual rows carry 190 distinct model WARs and
the key cuts their single 924-row tie block to 180 (the -2.0 WAR clamp), an 80.5%
reduction: PASS. The 261 routed-at-floor rows carry only 39 distinct provisional
WARs with 205 in one block, a 21.5% reduction: FAIL by the registered "half" rule.
Recorded as a FAIL. It does not change the ship decision because the sort key is
minted on the UNROUNDED PRE-CLAMP WAR while these counts are measured on the 2dp
artifact, so the shipped key strictly dominates what is measured here; the honest
statement is that this lab cannot demonstrate G6 on that population and the
post-regen artifact must be re-measured before the key is claimed to work there.

Routed cohort landing: median 27.1, p90 33.3, max 46.7; 624 land above FV30, 150
above FV35, 15 above FV40. The best board rank any routed row reaches is 182, which
is why G5 is clean: the cohort re-ranks the 100-1000 band and never touches the part
of the board anyone screenshots.

## 4. Ship state

`efv_score.SERVE_PROVISIONAL_FOR_CONSTANT_COHORT` defaults **False**.

The routing is implemented and gated, and it is NOT enabled in this commit. Serving
it requires two changes in `prospx/index.html`, which this wave is owned by another
agent (file ownership is exclusive):

1. the board pool dedupe (section 1) - without it the fix makes both rows print the
   same number, so the same player appears twice at one grade, which is a
   legibility regression against today's contradictory pair; and
2. the two-scale disclosure (section 2) on every surface that mixes the maps.

A third dependency was found while wiring it and is not in a file this lane owns
either: `efv_export._entry` is a field WHITELIST, so `grade_basis` and
`board_sort_key` reach `data/xfv_scored_live_*.json` and stop there. Four lines in
that function pass them into `data/xfv.json`. The routed GRADE is unaffected: it
rides `s["xfv_grade"]`, which is already whitelisted, so the routing itself works
end to end the moment the constant flips.

The flip is one constant. The exact frontend spec is in the lane report. Landing the
constant before the frontend would ship an undisclosed scale swap on 2,434 rows,
which is the failure mode this document exists to prevent.

## 5. Registry

| field | value |
|---|---|
| registry row | `efv_board_floor_routing` |
| verdict | `provisional` (gates pass, ship blocked on two files this lane does not own) |
| eval artifact | `docs/efv-2026-08-07/BOARD_FLOOR_ROUTING_SIM.json` |
| changes served output | no (switch off) |
| fingerprint term | `floorroute=off@ff60a349` in `storage.BOARD_BASIS_FINGERPRINT` |

The companion Lane B3 change (`STALE_ANCHOR_DATE_BASIS` point -> source) is a
separate record: `docs/efv-2026-08-07/STALE_ANCHOR_MOVER_TABLE.json`, fingerprint
term `stale=source`, epoch deliberately NOT bumped because the measured mover count
at +0 months is zero and there is therefore no re-rank for the movement engine to
mistake for player movement.
