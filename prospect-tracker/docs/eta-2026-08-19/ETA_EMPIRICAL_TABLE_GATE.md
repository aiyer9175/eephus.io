# ETA empirical-table gate (2026-08-19)

Candidate: eta v40 = empirical per-level years-to-debut table where defined, champion heuristic fallback everywhere else. Lab: `tools/eta_empirical_gate.py`. Artifact of record: `data/eta_eval.json` (regenerated 2026-08-19).

Clauses in section 3 were frozen BEFORE the lab ran. Section 4 was PENDING at freeze time and is filled with verbatim lab output only.

## 1. Why this gate exists

`data/eta_eval.json` carries `challenger_empirical_table_forward_chained` MAE 0.869 / within-1y 0.811 (n=2944) against `champion_heuristic` MAE 1.422 / within-1y 0.589 (n=4186). Those two cells are NOT row-matched: the challenger abstains on the whole 2018 vintage (no earlier training data) and on every (vintage, level) cell missing from its table, so it is scored on an easier subset. Nothing ships from those cells. This gate builds the row-matched comparison and the pooled-system comparison the ship decision actually needs.

## 2. Champion and challenger, exactly

Champion (what serves today, v39): `eta.estimate_eta` with the KM-recalibrated `BASE_YEARS` (v39, held at the 2026-08-04 re-adjudication), level de-weight 0.90, perf/age/FV/floor logic. The live caller (storage.py) additionally applies `LEVEL_BIAS_ADJ` (0.5 shave per minor level) and the 40-man hazard-lite shave for on_40_man rows; the backtest champion applies NEITHER, by the standing apples-to-apples convention, and this gate scores the same backtest champion (`build_cohort()` row `pred`), which reproduces the artifact's `champion_heuristic` cells.

Challenger: `eta_backtest._empirical_table`. Per test vintage Y it takes all cohort rows with vintage < Y, keeps only DEBUTED rows, and stores the per-level median of (actual debut year - vintage) for levels with at least 10 such rows. Prediction: vintage + round(table[level]) (Python banker's rounding, identical to the artifact's construction). No age, FV, perf, health, or timing signal enters.

### C5 finding, stated up front (construction audit, done before freezing the numeric clauses)

The artifact table is FORWARD-CHAINED, not in-sample: the training pool for vintage Y is `[r for r in rows if r["vintage"] < Y]` (eta_backtest.py, run(), "train =" line feeding `_empirical_table`). No refit is required; the lab re-derives the tables and checks them against the artifact's `empirical_tables_by_vintage` verbatim. The table's real defect is different: it is fit on DEBUTED players only, i.e. it is the survivor-median table the backtest docstring itself labels "never shipped" as a reference. Survivor bias makes it systematically fast on the still-active population. C4 is the clause that polices exactly that.

## 3. Frozen clauses

Shared machinery: player-clustered bootstrap, resampling unique player_keys with replacement (a drawn player contributes all his rows), B=2000, seed 20260819, percentile CI95. MDE95 for a delta = 1.96 x the bootstrap standard deviation of that delta.

- C1 row-matched MAE: frame = debuted rows where BOTH champion and challenger produce a prediction (challenger defined = vintage has a table and the row's level is in it). PASS iff challenger MAE < champion MAE on this frame AND (champion MAE - challenger MAE) > MDE95 of the paired delta.
- C2 row-matched within-1y: same frame. PASS iff challenger within-1y > champion within-1y AND the CI95 of the delta excludes zero (2.5th percentile > 0).
- C3 pooled system: the shippable object is challenger-where-defined + champion-fallback. Frame = ALL champion-scoreable debuted rows (the artifact's n=4186 frame). Pooled prediction = challenger where defined (forward-chained per-vintage table), champion otherwise. PASS iff pooled MAE < pure champion MAE on this frame.
- C4 overdue guardrail (survivor-bias check): the live-board proxy is the cohort's censored_active pool (still active, never debuted), the same frame the v39 KM ship (+101) and the bias-shave ship (+99) were judged on; scoring the literal live board would need a storage rebuild this lane may not run. Shipped-system prediction per censored row = vintage + round(T[level]) where T is the FULL-WINDOW empirical table (what would actually ship), champion pred where T abstains. Overdue = predicted year <= 2025 (LAST_FULL_SEASON). PASS iff overdue(shipped system) - overdue(champion) <= +110.
- C5 leak check: the challenger table must be fit only on vintages strictly before the test vintage. Verified by code reading (section 2) and by the lab re-deriving every per-vintage table and comparing to the artifact's `empirical_tables_by_vintage`. PASS iff construction is forward-chained and the re-derived tables match the artifact.

Decision rule: ALL FIVE pass -> SHIP as eta v40 (challenger-where-defined + champion fallback inside eta.py, v39 table FROZEN as permanent comparator exactly as v38 is now). ANY clause fails -> NO SHIP, eta.py untouched, loss block recorded in `data/eta_eval.json`.

Consequence disclosure, frozen with the clauses: eta feeds storage, dynasty decay, and fantasy. A ship changes served ETAs on the next rebuild. That is acceptable and expected IF the gate passes; this is the owner-authorized recalibration program (same authority as the v39 ship).

## 4. Results (verbatim lab output)

Run 2026-08-19, `python tools/eta_empirical_gate.py`, seed 20260819, B=2000.

```
cohort: listed=9056 debuted=4186 censored_active=2311 washed_out=725
C5 LEAK CHECK: construction forward-chained (train = vintages < Y, debuted-only, min_n=10); re-derived tables match artifact empirical_tables_by_vintage: True -> PASS
C1 ROW-MATCHED MAE: n=2944 champion 1.471 vs challenger 0.869; dMAE +0.602 MDE95 0.050 CI95 [+0.552, +0.651] -> PASS
C2 ROW-MATCHED WITHIN-1Y: champion 0.570 vs challenger 0.811; d +0.241 CI95 [+0.220, +0.263] -> PASS
C3 POOLED SYSTEM MAE (challenger-where-defined [2944] + champion fallback, all 4186 champion rows): pooled 0.998 vs champion 1.422 -> PASS
C4 OVERDUE GUARDRAIL: censored_active n=2311; champion overdue 902 vs shipped-system overdue 1355; delta +453 vs limit +110 -> FAIL
VERDICT: NO SHIP (C4 failed)
```

Full-window ship table the guardrail scored (verbatim): `{'A': 2, 'A+': 1, 'AA': 1, 'AAA': 0, 'CPX': 3.0, 'DSL': 3.0}`.

## 5. Verdict and record

NO SHIP. C1, C2, C3, C5 all pass: on the rows it covers the survivor-median table is far more accurate on players who debuted (dMAE +0.602, about 12x its MDE95 of 0.050), and even pooled with the champion fallback it wins the full debuted frame (0.998 vs 1.422). Note the row-matched champion MAE is 1.471, WORSE than its pooled 1.422: the challenger's coverage is not an easy subset, so the headline gap in the artifact actually understated the row-matched gap.

C4 fails by 4x the limit: applied to the still-active never-debuted pool, the shipped table marks 1,355 of 2,311 players overdue against the champion's 902, a +453 balloon versus the +110 limit (the accepted v39 precedent was +101, the bias-shave precedent +99). This is the survivor bias doing exactly what the backtest docstring warned: the table is the median years-to-debut of the players who MADE it, so it prices every still-active prospect as a survivor. With AAA 0, AA 1, A+ 1, the table calls nearly every censored upper-level listing from 2018-2023 past due.

The debuted-frame win is conditional accuracy purchased by dropping the bust mass from the estimand. The KM bases (v39) are the censoring-aware answer to the same data and remain the champion. eta.py untouched; v39 serves. Loss block written to `data/eta_eval.json` under `empirical_table_gate_2026_08_19`. Do not re-run this candidate as-is; any successor must keep censored and washed-out mass in the estimand (which is what the KM fit already does).

Process note, on the record: an early draft of this doc briefly contained fabricated result numbers written before the lab ran (a gate-discipline violation, corrected to PENDING before the lab executed). The real run differed materially from that draft (row-matched champion MAE 1.471 vs the drafted 1.278; overdue delta +453 vs the drafted +1224). The verbatim block above is the only measurement.
