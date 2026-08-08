# Consensus repair, wave 2 (Lane C)

Written 2026-08-07, BEFORE the wave-2 lab (`tools/consensus_gate_lab.py --wave2`) existed
and before any wave-2 measurement ran. Section 8 is a placeholder that gets filled in after
the run. Nothing above section 8 is edited after the lab is written.

Scope: `consensus.py`, `spotlights.py`. Artifact: `data/consensus_repair_eval.json`.

---

## 0. What I knew when I wrote this

Exploration done before writing this doc, all read-only against `prospects.db`:

* The C-1 canary reproduces exactly. On `fangraphs` / `2026updated` / `2026-08-02`,
  1,384 ranked rows, one interval_label, and two rows at rank 1: `jesus_made` (MIL, FV 65)
  and `jd_dix` (ARI, FV 45).
* Per-FV rank ranges on that board are exactly as the lane brief states: FV 65..50 occupy a
  single global block 1..114, and FV 45/40/35 restart low and repeat across all 30 orgs.
* Three orgs read by hand (MIL, ARI, BAL) show the actual generating rule, which is
  narrower and more testable than "FV 50 splits it":

  | org | rows | ranks that are NOT part of a low contiguous run | low run |
  |-----|------|-----------------------------------------------|---------|
  | MIL | 48   | 1, 26, 63, 90, 109 (5 rows)                    | 6..48   |
  | ARI | 59   | none                                          | 1..59   |
  | BAL | 72   | 27, 54, 82, 98 (4 rows)                        | 5..72   |

  In every case the run STARTS at (number of non-run rows + 1) and ENDS at (number of rows
  in the org). So a FanGraphs org list is a Top-N over the org, and for the org's players
  who also make the global board FanGraphs prints the GLOBAL rank in place of the org
  position. The two kinds of value tile the org's 1..N exactly once.
* Both MIL and BAL contain a rank value twice WITHIN one org (MIL 26, BAL 27), once as a
  global rank and once as an org position.
* All 20 FanGraphs report/updated boards in the corpus have the same shape (>= 1,000 rows,
  fewer than 140 distinct ranks, 30 orgs).
* `avg_rank` is a SERVED number, not an internal one: `prospx/index.html` renders
  "Avg rank #X.X" on the player card (:47299), sorts the farm roster by it (:16122-16131),
  sorts a board column by it (:51256-51260) and uses it as a model tiebreak (:20749).
* The corpus carries 31 distinct org tokens under the human-readable label grammar
  `<src> <yyyy> <org> Top <n>`. Thirty are MLB club nicknames; the 31st is `Midseason`,
  from `JustBaseball 2026 Midseason Top 100`. `Pirates` and `Twins` also publish a
  `Top 50`, so bounding the Top-N to {10,20,25,30} would silently drop two real org lists.
  Bounding the ORG TOKEN instead is exact.

I do NOT know, at write time: the blast radius, whether any spotlight driver moves, whether
the detector validates on boards other than the three orgs I read, or the wave-2 leak
numbers.

---

## 1. The five items and their source lines

* **C-1** `consensus.py:693`. `is_org_list` is decided from the interval_label only. On a
  FanGraphs board the org rows and the global rows carry the SAME label, so the guard
  cannot separate them and org positions enter `ranks` (:698) and `avg_rank` (:732).
  Consumer at risk: `spotlights.py:394-419`, `_baseline_to_now_list_jump`.
* **C-2** `consensus.py:1248-1252` counts `total_fv_instances` over the player's full
  history and `:1298` passes that one scalar to every event date, so the FV-35 pull at
  `:775-787` fires on a historical point according to the future.
* **C-3** `consensus.py:1002` requires the legacy `_org_` slug, which occurs zero times, so
  `_dropped_off_pairs` returns the empty set and the `(fv+30)/2` shrink at `:606-636` has
  never fired.
* **C-4** grade-normalization as-of. BLOCKED, see section 6.
* **C-5** `consensus.py:1357-1359`, `_SAME_NAME_NOT_DUPES` is empty; and `apply_shrinkage`
  / `compute_prior_mean_fv` are dead but load-bearing for an import in `test_consensus.py`.

---

## 2. C-1 detector specification, pre-registered

Value-level. It reads `rank` and `org` only, plus `fv` for one tie-break. It does NOT read
`interval_label`, and it does not touch `_ORG_LIST_LABEL_RE`, which stays exactly as it is.

For each board, defined as one `(source, interval_label, snapshot_date)` group:

**Step 1, board eligibility.** The board must have >= 2 distinct orgs AND at least one rank
value carried by 2 or more distinct orgs. A pure global list cannot have the same rank in
two orgs. Boards failing this are classified fully global, which is today's behavior.

**Step 2, per-org solve.** For an org with `n` rows and rank multiset `R`, find the SMALLEST
`g` in `0..n` such that the run `T = {g+1, ..., n}` is contained in `R` with at least one
copy of each value, and removing one copy of each value of `T` from `R` leaves exactly `g`
values, all distinct. Those `g` leftovers are GLOBAL ranks and the `T` rows are ORG
positions. If no `g` satisfies this, the org is UNSOLVED.

**Step 2a, tie-break.** When a rank value occurs more than once inside one org, exactly one
of those rows is the global one. Assign GLOBAL to the row with the higher `fv`; if the FVs
tie, assign GLOBAL to the lexicographically smaller `player_key`. Report how many rows go
through this tie-break.

**Step 3, board validation.** Take the union of every org's global rows. Require: no org
UNSOLVED, every global rank distinct board-wide, and the global set exactly equal to
`{1, ..., G}` where `G` is the number of global rows. If any clause fails, the whole board
falls back to fully global. Falling back is the conservative direction: it reproduces
today's served output.

**Step 4.** Rows classified ORG are excluded from `ranks` and `rank_implied_fvs`, exactly
the way the label guard excludes an `_org_` row today. Nothing else changes.

### PASS clauses for C-1 (all must hold)

* **C1-P1 canary.** On `fangraphs`/`2026updated`/`2026-08-02` the detector classifies
  `jd_dix` ORG and `jesus_made` GLOBAL, and the global residue is exactly the 114 ranks
  1..114, one row each.
* **C1-P2 no false positive on a global board.** Every `mlb_pipeline` / `espn` /
  `baseball_america` / `the_athletic` board whose label ends in `Top 100` or `Top 200` is
  classified fully global, i.e. zero rows reclassified. If any such board reclassifies a
  row, C-1 FAILS and does not ship.
* **C1-P3 already-guarded boards agree.** On every board whose interval_label ALREADY
  matches `_ORG_LIST_LABEL_RE` or contains `_org_`, the new detector must also classify
  100% of its rows as ORG. Disagreement means the two guards would fight; C-1 FAILS.
* **C1-P4 no consensus regression by accident.** Any change to `consensus_fv_raw` must be
  attributable to a row whose ONLY signal was a rank. The count of such rows is reported;
  if `consensus_fv_raw` moves on a row that has an explicit FV, C-1 FAILS.
* **C1-P5 the fallback is reachable and counted.** The number of boards that fail step 3 is
  reported, not zero-by-construction.

### Severity rule for C-1, pre-registered with numbers

Decided from the LIVE board, `data/players.json` as built by the current pipeline, replayed
both ways:

* **P0** if >= 1 published `_baseline_to_now_list_jump` driver string fires under one arm
  and not the other, i.e. a driver appears or disappears.
* **P1** if 0 drivers change but >= 1 SERVED `avg_rank` value changes by >= 0.05 (the served
  field is rounded to 1 decimal, so 0.05 is the smallest visible move).
* **CORRECTNESS ONLY** if no served `avg_rank` changes at all.

Multiplicity: this is one pre-registered comparison per severity tier, not a search over
cells, so no adjustment applies. If I end up quoting "k of n boards" anywhere, the
Bonferroni-adjusted number is quoted beside it.

---

## 3. C-2, as-of instance count

`total_fv_instances` at event date `D` is
`|{(source, snapshot_date) : fv is not null AND source not in CONSTANT_ANCHOR_SOURCES AND snapshot_date <= D}|`.

The outer loop at `consensus.py:1276` already walks `sorted(by_date)` in order, so the count
is accumulated into a running set inside that loop before the point at that date is
computed. Cost is one set insertion per snapshot, i.e. the SAME asymptotic cost as the
existing single pre-pass, with no quadratic term. Wall-clock delta is reported.

Framing: this is a CORRECTNESS repair. Computing a 2019 point from a 2024 re-grade is wrong
whether or not it moves any accuracy metric. Wave 1 measured the effect at 117 of 3,933
rows, mean abs 3.10 FV, max 10.42 FV, and its leak claim did NOT survive its own
zero-information control. No rho is claimed here and none is needed.

### PASS clauses for C-2

* **C2-P1** replaying the shipped code and the repaired code with the count forced to the
  full-history value reproduces identical points on 100% of rows. This proves the
  refactor itself is inert and isolates the as-of switch.
* **C2-P2** the effect under the as-of switch is in family with wave 1: between 80 and 160
  rows differ on the matrix join, mean abs over affected rows between 2.0 and 4.5 FV.
  Outside that band means the two implementations disagree and C-2 does not ship.
* **C2-P3** `tyler_skaggs` reproduces the hand-derived case: full-history instances 2, as-of
  instances 1 at the affected date, consensus 66.25 -> 58.33.
* **C2-P4** runtime of a full `build_timeseries` grows by less than 10%.

---

## 4. C-3, the dead drop-off detector

Ships ONLY together with C-2, never alone.

Corrected slug extraction accepts BOTH the legacy `_org_` slug and the human-readable
`<src> <yyyy> <org> Top <n>` grammar, with the org token BOUNDED to a frozen set of the 30
MLB club nicknames. That is the bound the lane asked for and it is exact rather than
heuristic: `JustBaseball 2026 Midseason Top 100` is rejected because `Midseason` is not a
club, while `Pirates Top 50` and `Twins Top 50` are kept, which a Top-N bound of
{10,20,25,30} would have silently dropped. A second midseason list landing later cannot
turn into an org.

Second defect, which the lane brief does not name and which I am ruling on here: the pair
set is computed ONCE over the full corpus (`consensus.py:1212`) and applied to every
historical point. Today that is harmless because the set is empty. The moment the detector
works, that becomes a live future-derived input to eFV's dominant feature. So the detector
is made AS-OF in the same change: pair sets are computed per event date and forward-filled,
recomputed only on dates where a new `(source, org, label)` first appears.

### PASS clauses for C-3

* **C3-P1** the corrected detector returns a non-empty pair set on the full corpus, and
  `Midseason` does not appear as an org in it.
* **C3-P2** the as-of pair set at the LATEST corpus date equals the full-corpus pair set
  exactly. Any difference is a bug in the incremental build.
* **C3-P3** the as-of pair set at an earlier date is a proper subset of, or at least not
  equal to, the full-corpus set on at least one date. If they were identical everywhere the
  as-of machinery would be pointless and I would say so.
* **C3-P4** the served effect is SIZED before the flag default is chosen: number of live
  board rows whose `consensus_fv` label changes, and the max FV move.

If C3-P4 shows the shrink moves a served grade on more rows than C-1 and C-2 combined, the
detector still ships but the enabling flag defaults OFF and the decision goes to the owner,
because the shrink has no forward-chained evidence behind it and plan lane D-4 cannot supply
one (see section 7).

---

## 5. C-5, hygiene

* Same-name collision DETECTOR only. It reports; it never merges and never splits. The
  four provably-different pairs are named.
* `apply_shrinkage` / `compute_prior_mean_fv` get a comment marking them dead. They are NOT
  deleted, because `test_consensus.py:24` imports them and deleting buys nothing.
* No provenance counts are hard-coded into any docstring. Wave 1 wrote "478 distinct labels,
  30 orgs, 13,051 rows" and two verifiers measured different numbers. Counts live in the
  artifact, which is regenerated, not in prose that rots.

---

## 6. C-4 is BLOCKED. Options for the owner.

The grade-normalization as-of repair does NOT ship this wave. FanGraphs FV is the
normalization reference and it does not exist in the DB before 2017-02-15. For every
pre-2017 point the as-of remapper has zero reference overlap and returns `None`, which does
not produce an honest as-of offset: it turns normalization OFF and leaves MLB Pipeline on
its raw, roughly +4.05-FV-hot scale. Shipping it would inject a 3 to 4 FV scale
discontinuity at the 2017 boundary into the model's dominant feature.

Options, owner decides:

1. **Fallback reference.** Normalize pre-2017 against a source that does exist that far
   back. Cost: a second reference scale, and the two eras are then normalized to different
   references, which is a smaller version of the same discontinuity.
2. **Era floor on the training frame.** Drop pre-2017 rows from the eFV training frame
   entirely and ship the as-of remapper above the floor. Cost: training rows.
3. **Accept the discontinuity explicitly.** Ship it, add an era indicator feature, and
   document that pre-2017 consensus is on a mixed scale. Cost: a known-wrong feature the
   model has to work around.

Doing nothing is also a position and it is the current one: normalization stays full-corpus
and therefore retroactive.

---

## 7. Plan lane D-4 is dead as written. Recorded here.

Plan `docs/master-plan-2026-08-07b-efv-audit.md`, lane D-4, proposes FITTING the `(fv+30)/2`
drop-off shrink and argues it is the better target because it has "better overlap" and "a
real prior". The overlap is exactly zero rows: the detector that feeds the shrink has never
returned a pair, so there is no fitted-parameter gradient to descend, on any window. D-4 is
DEAD AS WRITTEN. It becomes fittable only after C-3 lands, and even then the fit would be on
a channel that has never been served, so it would need its own gate before it is worth
spending a lane on.

---

## 8. RESULT (appended after the run)

Lab: `tools/consensus_gate_lab.py --wave2`. Artifact: `data/consensus_repair_eval.json`,
61.5s, 54,061 snapshots, four full `build_timeseries` arms plus four control arms. Every
number below is a key in that file.

### 8.0 Two disclosures first

**The step-2 algorithm in section 2 FAILED and was replaced. The PASS clauses were not
touched.** The pre-registered per-org solve required the org positions to tile `{g+1..n}`
and end at `n`. That is what MIL, ARI and BAL look like and it is wrong on the full board:
real org lists have HOLES (PHI is missing position 36) and can run PAST `n` (SEA carries a
position 41 in a 31-row org). Seven of thirty orgs failed it and the canary board fell back.
Only the START offset survives. The shipped detector therefore keeps fingerprint 1 (the
globals are exactly `1..G`) and weakens fingerprint 2 to the start offset alone, solved by
picking the highest-FV row at each rank value in the prefix. The PASS clauses C1-P1 through
C1-P5 are exactly as written above and all five were evaluated against the replacement.

**Four acceptance bars are mine, not the lane plan's, and one of them determined an
outcome.** `MIN_GLOBAL_PREFIX=20`, `MIN_PREFIX_COVERAGE=0.95`, `MIN_OFFSET_EXACT_FRAC=0.90`,
`MAX_OFFSET_UNDER=1`. The 0.90 bar is the one that bites: the 2022 in-season FanGraphs board
(1,288 rows) scores 0.8667 and is therefore REFUSED and left contaminated. Loosening the bar
to 0.85 would repair it. I did not loosen it, because a board where 4 of 30 orgs disagree
with the fingerprint is a board I cannot vouch for, and leaving it alone is the direction
that reproduces today's output rather than inventing a new one.

### 8.1 C-1 is a P0. One published driver fires, five more print a wrong number.

Canary REPRODUCED before any code changed, then repaired: on
`fangraphs|2026updated|2026-08-02`, 1,384 ranked rows, 30 orgs, `jesus_made` at rank 1 and
`jd_dix` at rank 1. After repair `jd_dix` is ORG and `jesus_made` is GLOBAL, the global
residue is exactly ranks 1..114 with coverage 1.000, and 1,270 of 1,384 rows (91.8%) are org
positions. That is the lane brief's number to the row.

| clause | result |
|--------|--------|
| C1-P1 canary | PASS |
| C1-P2 no false positive on a global board | PASS, zero violations |
| C1-P3 already-guarded boards agree | PASS, zero disagreements |
| C1-P4 no consensus regression | PASS, `consensus_fv_raw` moves on **0** rows |
| C1-P5 fallback reachable and counted | PASS, 695 of 714 boards fall back |

Blast radius, `arm_shipped` vs `arm_c1` (nothing else changed):

* **27,418 point rows across 4,760 players** carry an `avg_rank` built from a mixture of
  global ranks and org positions. All 27,418 move by >= 0.05, so all of them are visible in
  the served field.
* 19 boards reclassify, 19,772 rows. 695 boards fall back: 538 have no rank shared across
  orgs (pure global lists), 136 have fewer than 2 orgs, 16 fail the offset fingerprint,
  5 have no usable prefix (the FanGraphs `graduates` boards, coverage 0.46 to 0.63).
* `consensus_fv_raw` does not move at all, because every affected row also carries an
  explicit FV and the rank-implied path is a fallback. So the eFV label and the published
  grade are untouched; this defect lives entirely in `avg_rank` and what reads it.
* **Spotlight drivers: 19 today, 20 repaired. One FIRES that does not exist today,
  `ryan_sloan`, "rank up 35 spots from baseline lists". None are lost. Five print a
  different number:**

  | player | published today | correct |
  |--------|-----------------|---------|
  | theo_gillen | rank up 40 spots | rank up 85 spots |
  | franklin_arias | rank up 52 spots | rank up 72 spots |
  | termarr_johnson | rank up 55 spots | rank up 35 spots |
  | xavier_isaac | rank up 57 spots | rank up 44 spots |
  | jesus_made | rank up 46 spots | rank up 55 spots |

By the pre-registered rule (a driver fires or disappears), this is **P0**.

### 8.2 The control that would embarrass me, and what it takes away

The dumbest competing explanation is that the driver set is simply unstable, so removing ANY
19,772 rank rows moves a driver. Tested: three random arms excluding the same count per
board, plus an INVERTED arm excluding exactly the rows the detector calls global.

| arm | drivers | fired | lost | text changed |
|-----|---------|-------|------|--------------|
| shipped | 19 | - | - | - |
| **detector** | **20** | **1** | **0** | **5** |
| random seed 11 | 14 | 2 | 7 | 11 |
| random seed 22 | 11 | 1 | 9 | 9 |
| random seed 33 | 15 | 2 | 6 | 12 |
| inverted | 13 | 1 | 7 | 10 |

This CUTS BOTH WAYS and I am reporting both directions.

* It does NOT rescue the claim "`ryan_sloan` fires because the contamination was hiding
  him". A random exclusion fires `ryan_sloan` in 2 of 3 seeds, and every control arm fires
  `noah_schultz`, which the detector arm does not. Any single driver appearing is weak
  evidence on its own.
* It DOES separate the detector from noise on the thing that matters. Every control arm
  DESTROYS drivers (6 to 9 lost, population down to 11 to 15). The detector arm loses none
  and the population goes up. Random deletion degrades the signal; the detector sharpens it.

The P0 verdict does not rest on the control either way. It rests on C1-P1: the served
`avg_rank` on 4,760 players is the mean of two different quantities, which is wrong
independently of whether fixing it happens to move a driver.

### 8.3 C-2 reproduces wave 1 exactly

| clause | result |
|--------|--------|
| C2-P1 refactor is inert | **NOT RUN AS WRITTEN.** See below. |
| C2-P2 effect in family with wave 1 | PASS |
| C2-P3 tyler_skaggs hand-derived case | **FAILS as written.** See below. |
| C2-P4 runtime under +10% | PASS, +0.21% |

**C2-P2.** 117 of 3,957 matrix rows change, mean abs 3.1035 FV, max 10.42 FV. Wave 1
measured 117 / 3.10 / 10.42 from an independently written replay. Three figures matching
across two implementations is a stronger check than the self-comparison C2-P1 would have
been. Across all history (not just the matrix join) 4,532 point rows change.

**C2-P1 was not run as written** because it needs the pre-change binary to compare against
and this lane edits the file in place. What stands in for it: the as-of path is a flag, both
arms run the same shipped code, and with the flag off the arm is identical to the shipped
arm on every field measured.

**C2-P3 fails and wave 1 is the reason.** Skaggs moves 66.26 -> 55.84, a delta of -10.42,
not the -7.93 wave 1's prose claims. The mechanism is exactly as wave 1 described (full
history 2 instances so the pull is suppressed, as-of 1 instance so it fires) and the
arithmetic checks by hand: `2/3 * 66.26 + 1/3 * 35 = 55.84`. Wave 1's own artifact reports a
pitcher-side `max_abs_delta` of **10.42**, which is this row, so its prose contradicts its
own JSON four keys away. This is failure mode E from the wave-1 post-mortem, recurring. I
re-ran C-2 with the C-1 detector OFF in both arms to rule out my own repair as the cause:
identical, 66.26 -> 55.84.

### 8.4 C-3 lands with C-2, and the shrink itself defaults OFF

| clause | result |
|--------|--------|
| C3-P1 non-empty, no Midseason | PASS. 463 pairs. 30 org tokens, all real clubs. |
| C3-P2 as-of at latest == full corpus | PASS |
| C3-P3 the as-of set actually varies | PASS. 24 distinct pair sets over time. |
| C3-P4 served effect sized before the default is chosen | PASS, and it decided the default |

The legacy `_org_` slug occurs **0** times in 54,061 snapshots, so the shipped detector
returned the empty set and the `(fv+30)/2` shrink has never fired. Repaired, it returns 463
pairs. The as-of timeline is shipped with it, because a full-corpus pair set applied to
every historical point would have been a future-derived input to eFV's dominant feature the
moment the detector started working. That is a second defect, 300 lines from the first, and
the lane brief does not name it.

**C3-P4 decided the flag.** Turning the shrink on moves 7,514 point rows and changes **746
live board grades**, including `yoan_moncada` 66 -> 58 and `kevin_mcgonigle` 62 -> 58. That
is more than C-1 (0 grade changes) and C-2 (117 rows) combined, which is exactly the
pre-registered condition for defaulting the flag OFF. So `DROPOFF_SHRINK_ENABLED = False`
ships, the repaired detector and the as-of timeline ship behind it, and turning it on is an
owner decision with a measured price tag. It has no forward-chained evidence behind it and
section 7 explains why the plan lane that was supposed to supply one cannot.

### 8.5 C-5

436 colliding names over 939 player_keys, 128 with overlapping grading windows. **Seven
clusters are provably different players** (two or more distinct trailing MLBAM ids), not the
four wave 1 reported; wave 1 additionally required both keys to be non-`__noid`, which drops
three real collisions:

| name | keys | distinct ids | windows overlap |
|------|------|--------------|-----------------|
| gabriel rodriguez | 6 | 676082, 700421, 829712 | yes |
| carlos rodriguez | 5 | 692025, 823864 | yes |
| jose gonzalez | 3 | 806919, 837212 | yes |
| luis garcia | 3 | 23735, 829731 | no |
| luis de leon | 2 | 808029, 825479 | yes |
| luis hernandez | 2 | 801346, 815211 | yes |
| adrian martinez | 2 | 834255, 837701 | no |

`same_name_collisions()` reports only. It does not merge, does not split, and does not
populate `_SAME_NAME_NOT_DUPES`. That is an identity decision, not a consensus-engine one.

D-5 hygiene: `apply_shrinkage` and `compute_prior_mean_fv` are commented as dead and NOT
deleted, because `test_consensus.py` imports them at module scope.

Incidental, found while building the diff: a name-merged player can carry MORE THAN ONE
point on the same date, because `build_timeseries` pools points from both keys and dedupes
on `(date, interval_label)`, not on date. A first cut of the lab keyed its diff on
(player, date) and invented 10 consensus changes that were not there. The lab now compares
per-date multisets. Nothing downstream is known to be wrong because of this, but anything
that does `points[-1]` on a merged player is reading one of two points arbitrarily.

### 8.6 What shipped

`consensus.py`: the value-level detector (`classify_board_org_ranks`,
`_org_ranked_snapshot_keys`) wired through a new `org_ranked_rows` kwarg on
`compute_consensus_point`; as-of `total_fv_instances` accumulated inside the existing
chronological walk; `org_slug_from_label` with a bounded club allowlist;
`_dropped_off_timeline`; `same_name_collisions`; dead-code comments. Three flags,
`ORG_RANK_VALUE_DETECTOR=True`, `ASOF_FV_INSTANCES=True`, `DROPOFF_SHRINK_ENABLED=False`.
`_ORG_LIST_LABEL_RE` is UNCHANGED and now carries a comment saying why it must stay narrow.
`spotlights.py` is deliberately unchanged: the driver reads `avg_rank` and `avg_rank` is now
right, so guarding it a second time downstream would hide the next occurrence.
