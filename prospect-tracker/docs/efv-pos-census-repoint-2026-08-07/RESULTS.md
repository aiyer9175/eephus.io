# LANE P: repointing the eFV observed-position feature at the as-of census

**Date:** 2026-08-07
**Files touched:** `efv_model.py` (the pos-premium block only),
`test_fielding_census_asof.py` (+12 tests), `tools/pos_census_repoint_lab.py` (new).
**Served grades, ranks and dollars moved:** none. `POS_PREMIUM_USES_OBSERVED` is still
`False` and the flag-off path is proved a byte-for-byte no-op on all 4,046 train + live
hitter rows.

Everything below was re-measured on the current tree by `tools/pos_census_repoint_lab.py`.
Nothing is quoted from `data/xfv_driver_pos_census.json` or from the lane brief without
re-deriving it, and three of the briefed premises did not survive.

---

## 1. What the brief said, and what measured

| Premise as briefed | Measured today | Verdict |
|---|---|---|
| `positions_played.json` training coverage 33.5% | 33.5% (642 / 1,917), debuted 5.1%, bust 55.9% | **holds** |
| The as-of rebuild sits beside it at 91.8% | 91.8% **only through `data/fielding_census_ids.json`**. Through the model's own row fields it is **58.6%** | **wrong as an input to this model** |
| Debuted-minus-bust gap +13.5pp (+6.5pp on id-resolved rows) | +13.5pp / +6.5pp with the lab binding; **+17.9pp / +8.9pp** on the route the model can actually use | **holds for the lab route, worse for the real one** |
| About 87 rows cannot resolve at all | **86** (81 with no id, 5 with an id absent from the census) | **holds, 86 not 87** |
| Those rows are "dominated by NPB/KBO players who never played affiliated ball, for whom a null is PERMANENTLY correct" | **10 of 86 (11.6%)** are NPB/KBO. The rest are name-join failures against players who ARE in the census | **wrong, and it is the load-bearing premise of P3** |
| Live-pool coverage | Never measured by the driver lane. The as-of route covers **76.1%** of the live pool against the career route's 93.9% | **new** |

### 1a. The 91.8% is not reachable from inside the model

`data/fielding_census_ids.json` is a census-scoped `player_key -> mlbam` name join. It
supplies **646 ids the matrix rows do not carry**, and those ids are worth **635 of the
1,759 covered training rows (36%)**. Facts about that file:

- It has **no builder anywhere in the tree**. It was committed as a one-off artifact in
  `fef6599`; `resolve_census_ids` exists in `fielding_positions.py`, but the script that
  called it over the board does not.
- It is frozen at `generated_at: 2026-07-30` and cannot be refreshed for new players.
- It is **excluded from deploy** (`deploy/data_exclude.txt:66`).

A model input cannot depend on an artifact nothing in the repo can rebuild. The repoint
therefore binds on the row's own `mlbam_id`, and the honest coverage number for the
shipped code path is 58.6%, not 91.8%. On the live pool the lab file is worth almost
nothing anyway (it adds 0 ids and 2 covered rows), because live rows carry `mlbam_id`
2,120 times out of 2,129. The identity problem is entirely historical.

---

## 2. Why the repoint is a correctness fix on its own

This is the part that does not depend on the flag ever flipping. Read the **same**
census both ways over the **same** 1,759 bound training rows:

- the career-to-date read disagrees with the as-of read on **330 rows (18.8%)**;
- the median training row has **63.0% of its career fielding games AFTER its own
  decision date**, and **1,325 of 1,831** rows are over half.

`data/positions_played.json` answers "where does he play now". The feature claims to ask
"where had he played when the grade was set". On four rows in five those are different
questions, and the old artifact cannot answer the second one without importing the
future. That is true whether or not `POS_PREMIUM_USES_OBSERVED` is ever `True`, which is
why the repoint lands now and the flag does not.

### What the flag would MEAN after the repoint

Before: "resolve the position from a per-player, pre-debut, career-to-build-date census,
keyed by player_key."

After: "resolve the position from games played in seasons **complete at this row's own
`asof_date`**, for rows carrying an mlbam id, and use the listed position for everyone
else."

Lower coverage, different quantity. The coverage drop on the live pool (93.9% to 76.1%)
is the as-of rule refusing to credit the in-progress 2026 season, which is correct by
construction: `season_visible_through` counts a season only once it has ended.

### Scale, if it were ever unblocked

| Pool | covered | changed | gain premium | lose premium |
|---|---|---|---|---|
| training (1,917) | 1,124 | 271 | 230 | 41 |
| live (2,129) | 1,619 | 342 | 249 | 93 |

With the flag OFF: **0 of 4,046** rows move.

---

## 3. The 86-row decision, taken

The brief offered three options and told me to pick with evidence. The evidence killed
the first one.

**Composition of the 86, measured name by name against the affiliated census
(490,091 lean rows, 154 of 154 league-seasons cached, 43,525 distinct normalized names):**

| Bucket | n | Is a null permanently correct? |
|---|---|---|
| NPB / KBO, no affiliated appearance (Do Yeong Kim, Tatsuki Mizuno, Chusei Mannami, Shugo Maki, Rui Muneyama, Shion Matsuo, Baek-ho Kang, Ju Won Kim, Ryusei Terachi, Seiya Yokoyama) | 10 | **yes** |
| Ambiguous name, dropped by design by `resolve_census_ids` | 33 | no, needs a birth date or an id |
| Same last name, our first name is a prefix of a census first name or vice versa (Josh Mears is there as "Joshua Mears", Mike Carico as "Michael Carico", Matt Wood as "Matthew Wood", Cameron Cannon as "Cam Cannon") | 14 | no, a formal-name variant |
| Same last name, same first initial only | 20 | probably not |
| No same-initial candidate | 7 | mostly no. 4 have no census player with that last name **because our spelling is wrong**: "Wladimir Gallindo" is in the census as "wladimir galindo"; "Ricky De La Torrre" carries a triple R |
| Unique name match that was still not bound (Malfrin Sosa, Jose Carlos Urena) | 2 | no |

Two further facts that decide the call:

1. **All 86 are BUST rows. Zero are DEBUTED.** The residual missingness sits 100% on one
   label class.
2. **Only 6 of the 86 carry a birth date** in `inactive.json`, which is exactly why the
   birth-year guard in `resolve_census_ids` could not break the 33 ambiguous names.

**Decision: option (c), keep the flag gated, and reclassify the blocker.** Specifically:

- **Rejected: "treat unresolvable as a permanent correct null and say so."** At most 10
  of 86 qualify. Documenting the other 76 as correct absences would be writing a data
  defect into the methodology as though it were a fact about the players.
- **Rejected: "exclude those rows from the feature entirely."** Inside a ridge that means
  either a missing indicator (forbidden here, and the reason is now stronger than when
  the rule was written: with missingness 100% on busts the indicator senses the label
  through its own absence) or dropping the rows, which would remove 86 busts and no
  debuts from the fit. Both make the leak worse. Note that "no observation" already
  degrades to the listed position, so a row that cannot resolve is not silently nulled.
- **Taken: the flag stays gated, and the blocker is now recorded as an IDENTITY
  RESOLUTION deliverable rather than a census one.** The census job is done. What is not
  done is binding our historical bust rows to it.

---

## 4. The flag stays FALSE, and the condition to change that

`POS_PREMIUM_USES_OBSERVED = False`. Pre-registered criterion, unchanged: coverage must
stop separating debuted rows from bust rows. It does not. +17.9pp on the shipped route,
+13.5pp on the lab route. Both are learnable by a ridge, and both point the same way as
the label.

No fit was run, deliberately. Fitting on a feature whose definition still tracks the
target measures the residual leak and reports it as skill.

**To ungate, in this order, each as its own commit:**

1. A **reproducible** `player_key -> mlbam` binding: a builder in the tree, an artifact
   that ships, and coverage on the 86. The cheapest real lever is backfilling birth
   dates for those rows, which unblocks the birth-year guard and the 33 ambiguous names
   directly. Name normalization (nickname folding, the mojibake in "V. V. Mesa", the
   "Glenallen, Jr. Hill" suffix mangling, the Gallindo/Torrre spellings) is the second
   lever and is worth roughly 20 more.
2. Re-measure the debuted-minus-bust coverage gap. If it does not clear the criterion,
   stop; that is the whole answer.
3. Only then, the full eFV accuracy battery (`docs/EFV_GATE_STANDARD.md`) on the refit,
   with a zero-information control and a committed loss.

A coverage change and a model change in the same commit is unauditable. Do not combine
steps 1 and 3.

---

## 5. Reproduce

```
python tools/pos_census_repoint_lab.py cover    # artifacts, coverage, label gaps
python tools/pos_census_repoint_lab.py miss     # why each uncovered row is uncovered
python tools/pos_census_repoint_lab.py idsrc    # row mlbam_id vs the lab binding
python tools/pos_census_repoint_lab.py flips    # flip scale + the flag-off no-op proof
```

Read-only. It writes nothing under `data/` and fires no network request (the season
census is read with `fetch=False` off the complete 154-file cache).

Tests, driven directly rather than through pytest (concurrent lanes own the suite):

```
python -c "import unittest,test_fielding_census_asof as T; \
 unittest.TextTestRunner().run(unittest.TestLoader().loadTestsFromModule(T))"     # 58 OK
python -c "import unittest,test_position_role_phase5 as T; \
 unittest.TextTestRunner().run(unittest.TestLoader().loadTestsFromModule(T))"     # 40 OK
```

`test_position_role_phase5.TestObservedPositionConsumers` is the cross-lane pin on which
consumers read the observation. It mocks `efv_model._observed_pos_map`, so that seam was
kept rather than deleted; it is now empty by default and marked deprecated, with the
condition for removing it written into its docstring.

---

## 6. Not done, and owed elsewhere

- **`prospect_def_value._observed_pos_map` has the identical defect** and its own gated
  flag `DEF_VALUE_USES_OBSERVED`. Not my file, not repointed. Its blocker is documented
  as leakage rather than coverage, and the as-of census answers exactly that objection,
  so it is a live follow-up.
- **`MODEL_REGISTRY.md`** row `xfv_pos_census` and the comment at
  `test_methodology_freshness.py:235` both describe the wiring defect as present tense.
  Both are stale now. Neither file is mine.
- **`docs/efv-drivers-2026-08-07/GATE_RECORD.md` section 4** records the 91.8% figure
  without the caveat that it needs a file with no builder. Not mine.
- Pre-existing in `efv_model.py`, untouched and unrelated: an em-dash in the comment at
  line 1512, and a ruff F401 on the unused `_calibration` import at line 40.
