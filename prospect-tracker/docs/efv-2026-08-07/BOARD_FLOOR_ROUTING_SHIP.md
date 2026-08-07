# Ship record: the eFV floor routing goes live, and the frontend defect it uncovered

Companion to the pre-registration at `BOARD_FLOOR_ROUTING_GATE.md` (omnibus-3 Lane B2,
finished as Lane F). That document registered the gates and recorded the routing as
implemented but switched OFF. This one records the flip, the re-run of every gate on the
current artifacts, and one thing the gate document did not know about.

Simulation lab `tools/efv_board_floor_sim.py` (re-run 2026-08-07).
Serve probe `tools/efv_board_serve_probe.py` (new; see section 2).

---

## 1. What shipped, in one commit

| item | change |
|---|---|
| F1 two-scale disclosure | `prospx efvScaleNote`, wired into the row tooltip, the detail header and the explainer head |
| F2 export whitelist | `efv_export._entry` passes `grade_basis`, `board_sort_key`, `factors_more` through to `data/xfv.json` |
| F3 sub-decimal sort key | `board_sort_key` enters the tiebreak chain in `prospx fvCmpDesc` AND `storage._active_key`, at the same position, with the same sentinel |
| F4 the flip | `efv_score.SERVE_PROVISIONAL_FOR_CONSTANT_COHORT` False to True, `floorroute=off` to `on`, `BOARD_RANK_BASIS_EPOCH` 2026-07-30 to 2026-08-07 |
| F5 explainer cut | top-4 kept and justified; `factors_more` admits what was dropped |
| (unplanned) | `_dedupeProvPool` merges the provisional twin onto `_prov_entry`, not `_xfv_entry` |

## 2. THE DEFECT THE GATE DOCUMENT COULD NOT SEE

Section 4 of the gate document listed the board dedupe as a PRECONDITION for the flip.
The dedupe shipped (9b7272c) and the precondition was treated as met. It was not, and the
reason is that every check on it was python-side or artifact-side, and the thing that
decides what a reader sees is neither.

`getEfv(p)` returns `p._xfv_entry` BEFORE it consults `_EFV`. `_dedupeProvPool` was
assigning the provisional twin's entry to exactly that field on the surviving graded row.
So the board did not serve the server's number at all: it served the PROVISIONAL grade
for all 2,636 dual-listed rows, with no scope whatsoever.

Measured 2026-08-07 by loading the shipped `prospx/index.html` function bodies into a JS
engine against the committed artifacts (`tools/efv_board_serve_probe.py`):

```
pool 7933   distinct 7933   duplicates 0
graded survivors carrying a merged provisional entry   2636
served grade != data/xfv.json xfv_grade                2374
served grade == the provisional grade                  2636
rows with flagship > FV30 whose served grade MOVED      183
   ryan_bourassa   38.1 -> 24.1  (-14.0)
   kenyon_yovan    41.1 -> 27.4  (-13.7)
   benny_thompson  37.8 -> 24.4  (-13.4)
   nicolo_pinazzi  42.6 -> 30.0  (-12.6)
```

That is gate G4 ("ZERO rows whose flagship grade exceeds 30.0 change their served
grade") failing on the live board, through the front door, while the server-side switch
that G4 was written about sat at False. The scoping the gate document spends a page
defending was being bypassed by the field name the entry landed on.

**Fix.** The twin's entry lands on `_prov_entry`, which nothing resolves a grade from.
The board number is `data/xfv.json` again, and the single decision about which map a row
serves is `efv_score.route_floor_grade`, server-side and scoped. Re-measured after the
fix, same probe:

```
pool 7933   distinct 7933   duplicates 0
client overrides of the served xfv_grade    0
rows above FV30 moved by the client         0
```

**The lesson, stated so it is not re-learned.** A gate that reasons about the artifact is
not a gate on the board while the frontend has its own resolution chain. The probe is
committed for that reason: it is the only check in the suite that asserts the rendered
board grade equals the served one.

## 3. Gates, re-run 2026-08-07 on the current artifacts

The lab was re-run rather than trusted. Its artifact
(`BOARD_FLOOR_ROUTING_SIM.json`) came back byte-identical to the committed copy, so the
board data has not drifted since the pre-registration and every number below is a fresh
measurement, not a citation.

| gate | pass condition | measured | verdict |
|---|---|---|---|
| G1 | duplicates 0 after dedupe; rows fall by the duplicate count | 2,636 duplicates, 10,569 to 7,933, removed exactly 2,636 | PASS |
| G2 | floor falls to the residual; scope exact | actives at 20.0 3,358 to 1,185; routed exactly the 2,434 scoped rows | PASS |
| G3 as registered | Spearman == 1.000 | 0.9829 pooled, H 0.9957 (n 1,098), P 0.9975 (n 1,336) | FAIL, and the gate was wrong (gate doc section 3a) |
| G3 corrected | passthrough mismatches == 0 | 0 of 2,434 | PASS |
| G4 | zero rows above FV30 move | 0 (server) and 0 (client, section 2) | PASS |
| G5 | top-25 / top-100 membership unchanged; no routed entrant | both empty; best rank a routed row reaches is 182 | PASS |
| G6 | largest floor tie block cut by >= half | graded residual 924 rows, largest block 180 (-80.5%); routed-at-floor 261 rows, largest block 205 (-21.5%) | PASS on the graded residual, FAIL on the routed floor |
| G7 | suite green | orchestrator runs it | pending |

**Zero-information control** (provisional grades randomly permuted across the routed
cohort, seed 20260807): pooled rho 0.9829 to 0.0080, hitter inversions 2,751 to 286,605,
pitcher 3,437 to 427,597, while G2, G4 and G5 stay bit-identical. So those three gates
measure scoping and population only, and G3 is the one carrying model information.
The control behaves exactly as the standard requires.

**G6 is still a split, and it is still recorded as a partial FAIL.** The 21.5% reduction
on the routed-at-floor rows is measured on the 2dp WAR the artifacts carry, while the
SHIPPED key is the unrounded pre-clamp WAR, so the lab structurally cannot demonstrate
the gate on that population. The honest statement is unchanged from the pre-registration:
re-measure it on the post-regen artifact before claiming the key works there. It does not
change the ship decision, because G6's stated failure mode is "drop the sort key, keep
the routing" and the key demonstrably clears the bar on the population it was designed
for (924 genuinely-graded floor rows, one tie block cut to 180).

**Landing distribution of the routed cohort**: median 27.1, p90 33.3, max 46.7. 624 land
above FV30, 150 above FV35, 15 above FV40, and the best board rank any of them reaches is
182. That is why the epoch bump is about the 100-1000 band and not about the top.

## 4. The two-scale disagreement, recomputed

| predicted WAR | flagship (pooled outcome curve) | provisional hit | provisional pit | gap hit / pit |
|---|---|---|---|---|
| 0.00 | 20.00 | 27.0 | 25.0 | -7.00 / -5.00 (INVERTED) |
| 0.25 | 38.54 | 27.95 | 26.12 | +10.59 / +12.41 |
| 0.50 | 40.30 | 28.90 | 27.25 | +11.40 / +13.05 |
| 1.00 | 42.78 | 30.80 | 29.50 | +11.98 / +13.28 |
| 1.50 | 43.66 | 32.70 | 31.75 | +10.96 / +11.91 |
| 3.50 | 47.62 | 40.30 | 37.73 | +7.32 / +9.89 |

The plan's -7.0 and +11 to +12 both reproduce on the hitter side; the pitcher side runs
to +13.3, which is why the shipped copy says "up to 13 FV" rather than the plan's range.

## 5. Why the epoch bumped here and did not for the stale-anchor flip

The epoch has ONE job: tell the movement engine that ranks were re-based, so it does not
publish a one-time re-rank as player movement.

- STALE_ANCHOR_DATE_BASIS point to source measured ZERO movers. Nothing re-ranked, so
  bumping would have suppressed a night of genuine movement to hide a re-rank that did
  not happen. Correctly not bumped.
- This change moves 2,434 served grades and re-orders the residual floor block on both
  readers. Thousands of ranks re-base. Bumped.

Cost, paid knowingly: rank-movement chips and rank deltas read empty until post-epoch
history accrues (the gate is strictly-after, so the first usable snapshot is 2026-08-08).
`data/xfv_history.json` also carries the pre-flip fingerprint, so the eFV-delta movement
signal stays suppressed until `score_history` restamps it on the next regen. Both are the
suppression working, not a side effect.

## 6. One-cycle lag, stated rather than discovered

`data/xfv.json` is written by the nightly box. Between this commit and the next regen:

- the routed cohort serves the flagship floor knot (20.0) again, because the committed
  artifact predates the flip. That is the pre-dedupe behaviour and it is honest.
- `grade_basis` is absent, so `efvScaleNote` returns "" and no disclosure renders. There
  is nothing to disclose yet, which is the correct pairing.
- `board_sort_key` is absent, so `efvBoardSortKey` returns the sentinel for every row and
  the tiebreak term is a no-op. The ordering is byte-identical to today's.
- `factors_more` is absent, so no "and N smaller factors" line renders.

Every one of those is the same field being absent on both readers at once, which is why
the lag is safe rather than a half-shipped state.

## 7. Registry

| field | value |
|---|---|
| registry row | `efv_board_floor_routing` |
| verdict | `provisional` (gates pass; the served population is the un-scouted floor cohort and its grades have never been outcome-validated below FV45) |
| eval artifact | `docs/efv-2026-08-07/BOARD_FLOOR_ROUTING_SIM.json` |
| changes served output | YES as of 2026-08-07 (2,434 grades, the 100-1000 rank band) |
| fingerprint term | `floorroute=on@ff60a349` |
| epoch | `BOARD_RANK_BASIS_EPOCH = 2026-08-07` |

Standing caveat, unchanged: a routed grade is `efv_ungraded`'s number and that model has
never been outcome-calibrated at these levels. It is a production-only leading indicator
served because the flagship map ABSTAINS there, not because it has been shown to be
right. Never present a sub-45 eFV grade as outcome-calibrated.

## 8. Owed, not done here

1. `test_efv_export._GOLDEN_XFV_SHA256` must be restamped on the first regen that carries
   the three new fields. It cannot be computed without that regen.
2. The glossary is a fourth surface that mixes the two maps (`assets/glossary.js`,
   `build_glossary_data.py`). Neither file is owned by this lane; the disclosure there is
   an unshipped follow-up.
3. G6 on the routed-at-floor population must be re-measured on the post-regen artifact
   before the sort key is claimed to work there.
