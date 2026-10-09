# FA Gate 2 re-save and verdict edge re-cut (2026-10-08)

Owner answers M14-1 and M14-2 (2026-09-25, `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`
rows M14-1 and M14-2). Files the re-save may touch: `fa_backtest.py`, `fa_market.py`
(the verdict edge constants only), `data/fa_gate2_eval.json`, the FA sidecars the
re-export rewrites (`data/fa_class.json`, `data/fa_archive.json`, `data/fa_meta.json`,
`data/fa_class_2028.json`, `data/fa_class_2029.json`), the registry rows `fa_market`
and `fa_rational_value`, the glossary entries `m_guarantee`, `m_years` and `deal_plus`,
and their tests.

This document is committed alone, before the re-save runs and before any verdict edge
is computed on the current corpus. Section 7 is appended by the re-save commit with
the verbatim numbers, whatever they are.

## 1. Decision record

| id | question | owner answer |
|---|---|---|
| M14-1 | /fa/ Gate figures source | Auto re-export: the gate lab re-runs the FA export after saving a gate |
| M14-2 | FA Gate 2 re-save | Re-save now and re-cut the verdict edges under a new gate doc |

## 2. What kind of decision this is

A re-measurement and a recalibration of three-way labels, not a model change. No
market model parameter, recal mode (`RECAL_MODE` stays "shift"), pinned weight, blend
or $/WAR series moves. `data/fa_dpw_series.json` is not written (`persist_dpw=False`).
The three hard gates keep their criteria: on each of guarantee, AAV and years the
pooled model MAE must be below the nearest-comps baseline MAE. Whatever the re-save
reads is written and served, pass or fail; a failed gate moves the `fa_market`
registry verdict off validated in the same commit.

`fa_mc.QUAD_TAUS` stays on the shipped i/20 grid: the quadrature question in
`docs/fa-2026-09-06/QUAD_CONVERGENCE.md` is held (its option 1), and the re-cut below is
that document's option 3, the owed group re-cut on the shipped grid.

Nothing here reads a prospect FV cell, an eFV list vintage or a betting column.

## 3. The Gate 2 frame

- Corpus: `fa_market.enriched_signings(2015, 2026)`, the NPV deferral-adjusted basis
  at `fa_market._discount_rate()`, stamped into the artifact as `discount_rate`.
- Folds: forward chained. Winters through 2017 train only; each test winter 2018 to
  2026 is scored by a model trained on winters strictly before it, with its own
  train-only $/WAR series. Rows with no comps are not scored (as since 2026-06).
- WAR label: the `war_source` facade default at run time, read through the corpus and
  stamped as `war_provider`. Since the fWAR label epoch (step Z entry, 2026-10-03) that
  is published fWAR, the label the served board prices on (`fa_meta.war_provider`). The
  2026-08-19 artifact predates both the eWAR v2 (2026-09-03) and the fWAR (2026-10-03)
  label moves; a different label is a different definition, not a gain in accuracy
  (epoch gate clause (l)), and no copy may say otherwise.
- Baseline: the median of the 5 nearest prior-winter comps, trend inflated, NPV basis.
- The census read on the eWAR v2 label (2026-09-24, about 9.48 against 11.08 $M on
  guarantee) is context, not a floor.
- Disclosed: one non-persisting timing run of `run_market_gate(persist=False)` on
  2026-10-08, before this document, read the pooled table on the fWAR label as
  guarantee 9.8524 against 10.7358, AAV 3.1199 against 3.1879, years 0.4370 against
  0.4921 (n 1,199). Nothing in sections 3 to 5 was changed after it, and no verdict
  edge was computed before this commit.

## 4. How the verdict edges are re-derived

The edges are corpus terciles of Deal+ by construction, so they go stale whenever the
pricing basis moves (the `fa_market.py` T1.4 block). The re-derivation is fixed here:

1. Corpus rows: every signing in `enriched_signings(2015, 2026)` whose winter has at
   least 100 prior-winter training rows (winters 2017 to 2026 on today's corpus, the
   2026-08-19 recipe), with a WAR path (`_war_path.war_by_year`).
2. For each winter W, fit `MarketModel` on winters strictly before W with the
   train-only series `dollars_per_war_by_winter(train)` and the winter's supply.
3. Deal+ on basis A: `100 * expected_rational_value_usd(path, min(predicted years, 10),
   W, winter_dpw(series, W), infl=_destale_rate(series, W)) / max(actual NPV
   guarantee, 1)`. A row whose value raises is dropped and counted.
4. Group by `fa_market._pos_group(position)` (SP, RP, C, POS) and pooled.
5. p33 and p67 by linear interpolation between order statistics (position
   p * (n - 1) on the sorted values), each rounded half up to an integer. The group's
   overpay edge is its p33 and its value edge its p67: overpay below lo, value at or
   above hi, market between.
6. The served constants (`VERDICT_GROUP_EDGES`, and the pooled fallback
   `VERDICT_OVERPAY_MAX` / `VERDICT_VALUE_MIN`) are set to the derived edges in the
   re-save commit. `VERDICT_BAND_MODE` stays "group".
7. The artifact records, per group and pooled: n, p33, p67, the old and new edges,
   the counts under each and the corpus rows whose verdict flips; and the served
   board's verdict counts before and after.

`run_market_gate(persist=True)` re-derives the edges on every persist and writes them
under `verdict_edges.derived`, beside the served constants. When a later persist
derives edges that differ from the served constants, `test_fa_ptier_gate.py` goes red:
moving the served constants again moves published verdicts and is an owner decision,
not a side effect of a re-persist.

## 5. The automatic re-export (M14-1)

After a gate artifact is persisted (Gate 1 or Gate 2, `persist=True`), `fa_backtest`
re-runs `fa_export.export_all()` so `/fa/#view=model` and the class bands follow the
gate at once. The re-export:

- runs with the page caches forced (`scrapers.cache_only()`): a cached Spotrac, Savant
  or StatsAPI page is read whatever its age and a missing one is not fetched, so the
  re-export costs no new page request;
- logs each served file it rewrites with its byte size and a short content hash before
  and after, and the files it left unchanged;
- never runs on `persist=False`, so every lab that reads Gate 2 through
  `GATE2_COLLECT` or `persist=False` (the FA destination lab among them) cannot
  trigger it.

## 6. What it moves

The Gate 2 table on `/fa/#view=model` (through `fa_meta.gate2`), the `fa_market` card
and summary, the `fa_rational_value` summary, the glossary `m_guarantee` and `m_years`
figures (pinned by `test_claims_freshness.py`), the `deal_plus` edge list, and the
served verdict on every class row whose Deal+ crosses a moved edge. No dollar figure
on the board moves through the edges.

## 7. Results

Re-saved 2026-10-08 (`python fa_backtest.py --gate2`, artifact generated_at
2026-10-08T23:11:22Z, war_provider fwar, discount rate 0.07). All three hard gates pass.

| metric | model MAE | comps MAE | n | 2026-08-19 table (bWAR label of its day) |
|---|---|---|---|---|
| guarantee ($M) | 9.8524 | 10.7358 | 1,199 | 9.6902 / 11.1205 |
| AAV ($M) | 3.1199 | 3.1879 | 1,199 | 2.9089 / 3.2491 |
| years | 0.4370 | 0.4921 | 1,199 | 0.4329 / 0.4871 |
| megadeals ($M, tracked) | 81.61 | 97.24 | 50 | 79.81 / 95.27 |

Guarantee bias by predicted tier ($M): lt10 -1.73, 10to20 -6.96, 20to50 -12.05,
ge50 +4.78 (2026-08-19: -2.18, -7.50, -12.88, -23.46). No tier exceeds the +10 $M cap.

Verdict edges (section 4 recipe, n 1,300, winters 2017 to 2026, 0 rows dropped):

| group | n | p33 | p67 | edges | served before | split under new edges | split under old edges | corpus flips |
|---|---|---|---|---|---|---|---|---|
| pooled | 1300 | 76.027 | 180.473 | 76 / 180 | 89 / 198 | 429 / 440 / 431 | 493 / 424 / 383 | 112 |
| SP | 297 | 96.775 | 214.467 | 97 / 214 | 86 / 182 | 99 / 98 / 100 | 89 / 91 / 117 | 27 |
| RP | 450 | 45.163 | 101.070 | 45 / 101 | 65 / 146 | 147 / 152 / 151 | 218 / 136 / 96 | 126 |
| C | 102 | 139.690 | 240.434 | 140 / 240 | 101 / 243 | 34 / 34 / 34 | 20 / 49 / 33 | 15 |
| POS | 451 | 109.106 | 245.750 | 109 / 246 | 103 / 237 | 149 / 153 / 149 | 135 / 161 / 155 | 20 |

Splits are overpay / market / value. Served 2027 board (232 priced rows):
106 / 119 / 7 before, 86 / 140 / 6 after; 37 rows change verdict. The 2028 board moves
52 / 121 / 10 to 45 / 121 / 17 (26 rows) and the 2029 board 46 / 68 / 21 to 41 / 74 / 20
(34 rows). No dollar figure moved. The reliever edges move furthest; this record measures
that and does not attribute it.

The automatic re-export ran from cached pages and rewrote fa_class.json, fa_meta.json,
fa_class_2028.json and fa_class_2029.json; fa_archive.json was unchanged.
