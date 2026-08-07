# eFV regen tripwires: coverage, served weights, explainer churn

Lane T of the omnibus-3 program. Instrumentation only. Nothing here moves a served
grade, rank or dollar, and no existing artifact under `data/` was rewritten.

Code: `tools/efv_regen_tripwire.py`, plus `efv_model.served_ridge_weights` and one
best-effort call in `run_monthly.rebuild_only`.
Reproduce the report with `python tools/efv_regen_tripwire.py` from `prospect-tracker/`
(reports only; `--record` is what writes).

---

## 0. The failure class

On 2026-08-04 the hitter training matrix gained 210 labeled players with a real MiLB
production block in a single regen, taking coverage from 48.0 to 59.2 percent after
three byte-stable vintages. The refit that followed moved the entire production weight
block: level premium down 32 percent, on-base down 36, OPS down 12, age-for-level up 46.

Nothing gated it, because it was a refit rather than a ship. Nothing connected the
coverage jump to the grade churn it caused. The owner found it by noticing that one
prospect had moved, and answering the question took a full lab session reconstructing
affine maps out of committed explainer arrays
(`docs/ARIAS_ATTRIBUTION_2026-08-07.md`).

Three quantities would have made that answer immediate, and all three were computed and
then discarded on every regen. This lane records them.

---

## 1. What is recorded, per regen

`data/xfv_regen_ledger.json`, one entry per vintage, newest last, last 30 kept.
`data/xfv_regen_digest.json`, per-player explainer hashes for the latest vintage only,
which is the state T3 needs because `data/xfv.json` is overwritten in place.

| | quantity | source |
|---|---|---|
| T1 | `milb_feature_coverage.level_rank`, per side, and its move | `data/xfv_dataset_report.json` and the pitcher twin |
| T2 | the served ridge weights (`w`, `mu`, `sd`), the intercept, the output calibration `(a, b)`, and the per-feature affine change against the previous vintage | `efv_model.served_ridge_weights`, which is `fit_production_stack` on the on-disk training matrix |
| T3 | share of live board cards whose explainer changed, three ways, beside the board basis fingerprint | `data/xfv.json` factors arrays, `storage.board_basis_fingerprint()` |

The affine map in T2 is exact, not a smoothing convenience. Holding a feature VALUE
fixed, `c = (w/sd)(x - mu)` gives

```
c_new = p * c_old + q      p = (w_new * sd_old) / (w_old * sd_new)
                           q = (w_new / sd_new) * (mu_old - mu_new)
```

so `p - 1` IS the sentence "this feature's contribution was rescaled by this much", and
`p = 0.6433` is "the on-base weight was cut 36 percent". `q` moves everyone equally and
therefore reorders nothing.

---

## 2. Thresholds, and how each was chosen

Every threshold is the geometric midpoint of a GAP measured in the committed history.
Each is gap-invariant: any value inside the stated interval partitions the measured
history identically, so the instrument does not turn on where in the gap the constant
sits.

### T1 coverage: 0.00502

All 35 committed vintages of `data/xfv_dataset_report.json` and its pitcher twin,
2026-06-22 to 2026-08-06, give 68 consecutive-vintage deltas of
`milb_feature_coverage.level_rank / rows_total`. 27 are exactly zero. The 41 nonzero
have one gap:

```
... 0.0015 0.0017 0.0029 0.0029 | 0.0087 0.0099 0.0110 0.0131 0.0156
    0.0257 0.0313 0.0478 0.1121 0.1233 0.1243 0.1631 0.1634
```

Below the gap is roster churn: a ~2,000 row pool gaining or losing a handful is 0.0005
to 0.003 by construction. Above it are the pipeline landings, including the 08-04
identity repair at +0.1121 hit and +0.0478 pit. 13 of 68 fire.

### T2 weight scale: |p - 1| > 0.0858

The map above, fitted on committed explainer arrays across the 6 consecutive vintage
pairs from 297d7eb (07-30) to 193c644 (08-06), both sides, ridge labels only, keeping
fits with r2 > 0.90: 95 feature-vintage maps.

```
... 0.0434 0.0458 0.0600 0.0690 | 0.1066 0.1106 0.1142 0.1144 0.1206
    0.1227 0.1512 0.1667 0.1667 0.1717 0.1940 0.3228 0.3567 0.4639 0.5717
```

15 of 95 fire, and they fall in exactly TWO of the six vintage pairs.

### T3 explainer label-set churn: 0.1683

Measured through `build_digest` and `churn` themselves, so the threshold is calibrated
on the figure the instrument emits. 12 side-vintage measurements of the share of live
cards whose ridge factor LABEL SET changed:

```
0.000 0.002 0.027 0.038 0.044 0.050 0.095 0.108 0.112 | 0.253 0.493 0.597
```

3 of 12 fire, in the SAME two vintage pairs T2 flags.

The naive "share of explainer arrays that changed at all" figure is recorded but is NOT
the alarm. It runs 0.042 to 0.987 over the same 12 measurements while the median
per-player magnitude move is 0.000: it is dominated by the 2dp rounding in the committed
arrays, so it reports a redecoration as a revolution.

---

## 3. Why all three, and not one

The two vintage pairs T2 and T3 flag are `7626fd0 -> d50c1af` (the 08-04 refit) and
`297d7eb -> fe670dd`.

**The second one had no coverage move at all.** Hitter coverage was 0.4800 at both
vintages and pitcher coverage 0.4561 at both, byte-identical, while the pitcher
age-for-level contribution was rescaled by p = 1.5717, the largest weight move in the
measured record. A coverage tripwire alone would have missed it completely.

That is the case for keeping the three instruments separate: coverage explains the 08-04
refit and says nothing about the 08-01 one, and two instruments built on different
artifacts (one on the training matrix, one on the served board) agreeing on which 2 of 6
regens were refits is the closest thing to a control this lane has.

---

## 4. Validation

**The weights are the served weights.** `efv_score._fit_production` calls
`efv_model.fit_production_stack(rows, side, keys)` on the on-disk training matrix and
serves the ridge it returns; `served_ridge_weights` is the same call. Verified by
recomputing `efv_score._factors` from this fit and comparing to the committed explainer
arrays in `data/xfv.json`: every ridge contribution reproduced to the 2dp the arrays
carry, on 1,839 live hitters and 2,226 live pitchers. The residual rows are display
relabels (`_relabel_pace_factor`) and overlay chips, not weight disagreements. The fit
is deterministic (two consecutive fits returned identical `w`, `mu`, `sd`) and costs
0.17s hit / 0.03s pit. It also reproduces the Arias lab's constants exactly:
n_train 1883, alpha-selected ridge intercept 1.6976, a 0.0319, b 1.0448.

**The affine map is exact.** Fitting the production stack twice, once on the full
hitter matrix and once on a seeded 80 percent row subsample, then checking
`p * c_old + q` against the directly computed new contribution over 8,400 real
per-player contributions: max absolute error 3.0e-06, which is the 6dp rounding applied
when the weights are stored.

**The whole chain reproduces the event it exists for.** Seeding the ledger with an
08-03-shaped vintage (that vintage's committed coverage counts, and hitter weights
divided by the Arias table's measured `p` values) and then running the instrument
against HEAD produced, unprompted:

```
coverage/hit      hitter MiLB feature coverage moved UP 11.2 points, 925/1927 to 1134/1917
weight_scale/hit  age_rel_level contribution rescaled UP 46 percent (p=1.4639)
weight_scale/hit  obp_rel       contribution rescaled DOWN 36 percent (p=0.6433)
weight_scale/hit  level_rank    contribution rescaled DOWN 32 percent (p=0.6772)
weight_scale/hit  ops_rel       contribution rescaled DOWN 12 percent (p=0.8794)
explainer_churn   61 percent of live hitter cards are showing a DIFFERENT set of reasons
coverage/pit      pitcher MiLB feature coverage moved UP 4.8 points, 941/2063 to 1029/2042
```

That is the Arias document's section 5 and its refit-slope column, produced by the
instrument in one line of log instead of a lab session.

**A rerun that regenerated nothing does not file a fake refit.** Each entry carries a
fingerprint over the coverage, the weights and the digest; an identical fingerprint
stamps `last_seen_at` on the existing row instead of appending.

**One dead night does not blind two.** Each side and each instrument resolves its own
baseline by walking back to the most recent entry whose block was actually observed
(`_last_observed`). Simulated: a run with the dataset report made unreadable filed
`observed: false`, and the next healthy run still compared coverage against the last
real vintage.

---

## 5. Design constraints this respects

* **Reports, never gates.** Nothing here can block a run, change a grade, or be cited as
  evidence for shipping or dropping a feature. `run()` swallows its own exceptions and
  the caller in `rebuild_only` wraps it again.
* **A firing is not a RED.** `_record_ingest("efv_regen_tripwire", ...)` files ok=False
  ONLY when the instrument could not observe at all: a missing dataset report, an
  unfittable production stack, an unwritable ledger. That is the one condition worth a
  red, because a watch that has silently stopped watching is the failure class this lane
  exists for. A tripwire FIRING leaves ok True and rides `log.warning` plus the ledger.
  The measured base rate of a firing is roughly one regen in three, and a RED at that
  rate is a RED nobody reads.
* **The source name is in `run_monthly.SCHEDULED_EXPORTS`**, so the dead-watch row
  survives `write_ingest_health`'s drain instead of being classified `unwatched` and
  dropped. That allow-list gap is what hid the `fa_class_identity` outage for a day.
* **No fourth WAR-to-FV map, no fourth ordering, nothing that reads like a model.** The
  only new computation is the affine identity above, which is arithmetic on two weight
  vectors.
* **The ledger is outside the `data/*_eval*.json` glob** that `test_model_registry.py`
  polices, because it is not an eval and has no registry row, and it carries no
  top-level `verdict` string, which `test_model_report_cards.py` collects.

---

## 6. Operational notes

**Both sidecars should stay UNTRACKED**, like `data/build_info.json`.
`deploy/nightly-build.sh` runs `git checkout -- .` before every pull, so a tracked
ledger would be restored to its last committed state at the start of every night and the
box would never accumulate history. The code is correct either way, and each entry
records the vintage it compared against, but untracked is what makes the ledger a
history rather than a two-row window. The lines belong in `prospect-tracker/.gitignore`
beside the other nightly-regenerated artifacts:

```
data/xfv_regen_ledger.json
data/xfv_regen_digest.json
```

**The digest should not ship to the public webroot.** It is model internals no page
fetches, the same class as `xfv_dataset_report.json` which is already listed. One line
in `deploy/data_exclude.txt`:

```
xfv_regen_digest.json
```

The ledger itself is small (about 8.3KB per entry) and readable and can ship.

---

## 7. Limits, and one thing this found on the way

* The threshold histories are short. T1 has 68 measured deltas, T2 has 95 feature
  maps over 6 vintage pairs, T3 has 12. Each threshold is the midpoint of a gap that is
  real in that record and could close as the record grows. They are reporting
  thresholds with no gate attached, which is the only reason that is acceptable.
* Refit variance on THIN features is large and will make this fire. Refitting the
  hitter stack on a seeded 80 percent subsample of the same matrix moved `obp_rel` to
  p = 1.97 and `age_rel_level` to p = 0.63, both far past the T2 threshold, with no data
  change at all. `obp_rel` is carried by 128 of the live hitters in the Arias-era
  explainer fit. A firing on a thin feature means "the fit is unstable here", not "the
  data moved", and the ledger cannot tell those apart. The coverage row beside it is
  what distinguishes them.
* 41 percent of labeled hitters still train on imputed production, so T1 will fire
  again, and that is the point.
* T2 records the weights of the SERVED ridge only. The eval-only LightGBM challenger,
  the blend lambda and the isotonic surplus calibration are not instrumented here.
* T3 compares the live board (`kind == "active"`) only. Debuted and bust rows carry
  explainer arrays too and are not counted.

**A defect found while classifying labels, not fixed here.** The pitcher explainer
renders the raw feature key `seasons_at_level` as its own chip label, with no human
wording, on **851 of 2,366 live pitcher cards (36.0 percent)** in the current
`data/xfv.json`. It is a genuine ridge term (it appears in
`efv_model._feature_spec("pit")`) but it has no entry in `efv_score._FACTOR_LABELS`, so
`efv_factor_groups.display_label` falls through to the key. This is the same class as
the `ops_rel` leak of 2026-07-07 and the `age` leak of 2026-07-14, both of which were
fixed by adding a label. `efv_score.py` is not this lane's file, so it is reported
rather than patched: the fix is one entry in `_FACTOR_LABELS`.
