# Master Plan 2026-07-31: Fifteen Owner Asks

Written for Claude Opus 5 to implement and execute. Every claim below was MEASURED on
2026-07-31 by a seven-agent read-only investigation, most of it reproduced byte-exact
against served artifacts. Where a number is quoted, it was reproduced, not assumed.
Prior-session context lives in the memory files named in Appendix C; read
`surplus-ev-objective-2026-07-31`, `master-plan-2026-07-30-nine-asks`, and
`efv-fa-execution-2026-07-30` before touching any surplus/eFV/FA code.

## How to use this plan

- Execute phases in order. Phase 0 contains hotfixes for defects that are LIVE on the
  served site today; do not defer them behind feature work.
- `OWNER:` marks a decision that must go to the owner (AskUserQuestion) before shipping.
- `GATE:` marks a change that moves served numbers and must clear a pre-registered gate
  (registry row + eval artifact + verdict). A measured no-ship is registry verdict
  `deprecated` with its artifact attached, plus a MODEL_GLOSSARY entry ("internal").
- Last session, 3 of 5 single-pass agent verdicts were materially wrong and only an
  adversarial second pass caught them. Re-verify any measurement in this plan that a fix
  depends on before shipping the fix, and adversarially verify your own lane conclusions.
- Appendix A is the non-negotiable ground rules (regen choreography, commit hygiene,
  rounding rules). Violating them has cost full sessions before.

## Confirmed defect ledger (fix these along the way, they are not speculative)

| # | Defect | Severity | Lane |
|---|---|---|---|
| 1 | FA 2027 board FROZEN: Spotrac avail page went 2-column 07-30, parser bails, 0 players parsed, board silently serves a 07-30 snapshot while reading "fresh" | P0 | 0.3 |
| 2 | Three surplus calibration vintages served at once (xfv.json = v6; trade_values.json, mlb_projections.json, timeseries.json = v5; farm rollups = stale v5-era sums) | P0 | 0.4 |
| 3 | Surplus priced through RETIRED xfv_grade_quantile while board displays xfv_grade (Anderson shown 56, priced 60.1) | P1 | A |
| 4 | F-SIDE-FIX crosswalk terminal knot = Ohtani two-way WAR (34.59) on a pitcher row; single-player PAVA block promotes the #1 pitcher; tail holds Skenes at 41.4 extrapolated | P1 | A |
| 5 | Compare cart displays consensus fv_close as the player's FV (arias 59 vs board 60); same stale field on similar-prospects chips, tool-comp chips, trade-audit chips | P1 | B |
| 6 | Homepage _fv_pill colors on RAW grade while printing ROUNDED label (cholowsky 59.9 prints 60, fails >=60 gold test; made 60.9 prints 61, misses holo) | P1 | B |
| 7 | eFV delta chip arithmetic visibly inconsistent (59 + 2.2 shown next to 60): three roundings applied to two numbers | P2 | B |
| 8 | FA "signings stale" badge is a granularity bug: per-class touch (2027 = 0 rows, no-op) vs global MAX read; red since 07-10, would stay red until November | P1 | 0.3 |
| 9 | Just Baseball history corrupted: rolling permalink upserted into fixed 'JB 2026 Preseason' label/date; 126-row chimera with two different #1s | P1 | C |
| 10 | mlb_pipeline_international re-dates all 50 rows to today every run (freshness illusion, history rewrite, grade-norm year-cycle migration) | P2 | C |
| 11 | performance_ingest votes a synthetic flat FV-35 into consensus at full weight on 32 players that ALSO have real grades (same class as the killed BA-statcast FV-40) | P1 | C |
| 12 | TJStats had an 8-day silent outage (07-08..07-21) with zero forensic trail; pipeline logs go to stdout only, logs/pipeline_latest.log last written May 24 | P2 | C |
| 13 | Chisholm (and 360 other vets, 40.7 Y1 WAR) silently dropped from Team Outlook by name-only Spotrac join | P1 | D |
| 14 | Positional ladder not zero-sum in any equal-weight reading (ex-DH +9.5): no sum-to-zero constraint, DH exposure half of every other rung, pre-2022 bWAR not zero-sum; plus a DUPLICATE ladder fit and a retired folklore multiplier table still live in prospx RPS+ | P2 | D |
| 15 | FA board default sort `projGuar` orphaned (no header carries it, unreachable after one click); Projections "Contract" header secretly sorts by AGE; Projections season-sort UI lost (y0..y4 comparator alive, unreachable) | P2 | G |
| 16 | eFV "Seasons to reach level" chip narrates the raw suppressor penalty (fires DOWN on 99.8% of live hitter cards) undiscounted by calibration or blend | P2 | E |
| 17 | prospx/index.html:20204 dead `fvCloseLabel` var (delete in passing) | P3 | B |

---

## Phase 0: Finish outstanding + P0 hotfixes

### 0.1 Beta sync (outstanding)
Beta last synced to main@8d3ebed; main is now 320c747, 12 commits ahead (the whole v6
surplus round, trade-machine floor re-express, Platt odds, fantasy cards, D2 wOBA swap).
Beta is a DISJOINT orphan ops branch; the sync is a commit-tree fast-forward, never a
force push:
```
TREE=$(git rev-parse main^{tree})
SYNC=$(git commit-tree $TREE -p origin/beta -m "Sync beta to main@320c747")
git push origin $SYNC:refs/heads/beta
```
Verify pushed beta tree == main tree afterward. Do this AGAIN at the end of this program.

### 0.2 Deploy box runs (outstanding, owner-executed or next box session)
- `python tools/repair_sabermetrics_stint_rows.py --apply` on the BOX prospects.db
  (traded-player stint bug; scope on `numTeams > 1`, NOT on bulk disagreement).
- The two older `--apply` repairs from the 2026-07-16 sweep if the box still shows them
  pending, plus `scp` of the 2026 draft CSVs (2026-07-15 memory).
- Golden restamp rides the next box regen:
  `tools.pipeline_artifact_diff.fingerprint_file(Path('data/xfv.json'), None)` into
  `_GOLDEN_XFV_SHA256` (test_efv_export.py).

### 0.3 P0 hotfix: the frozen FA board + the false staleness badge
Two granularity bugs, opposite symptoms, one root style (global vs per-class):
1. `fa_sources.py:186-188`: the 2027 avail parser bails on Spotrac's new 2-column layout
   ("unrecognized header set ['players','previous aav']") and returns 0 players. Extend
   the header-set handling for the new layout, keep the bail as a loud failure (raise or
   record into ingest health, never a silent 0-row return). Acceptance: a fresh parse
   returns ~200+ members and the served 228-member board updates on the next export.
2. `fa_export.py:679-694` `_source_freshness` reads a GLOBAL `MAX(fetched_at) FROM
   fa_signings`, while `fa_pipeline.py:193` touches per-class (`storage.py:15657`,
   `WHERE class_year=?`), which no-ops with 0 rows for 2027. Fix: freshness must record
   "last checked" independent of row existence (an out-of-row stamp per class), and the
   client threshold at `assets/fa.js:299` (14d) reads that. `n_signed=0` for 2027 is
   correct and must not read as stale in July.

### 0.4 P0 hotfix: surplus frame convergence (defect 2)
One regen pass, from a FRESH interpreter (the 21:12 exporter served v5 because a
long-running chained build held a pre-14:42 in-memory config):
- Rebuild `data/trade_values.json` (bayes_trade_value), `data/mlb_projections.json`
  (proj_export), `data/timeseries.json` (storage.export_timeseries_json) so every
  surplus-carrying artifact prices under `isotonic-real-v6-evframe-2026-07-31`.
- Farm rollups (`org_summary._active_surplus_net_mm`, storage.py:7634-7643, 10967-10969)
  recompute inside the timeseries export; verify SEA gross ~447 not ~246.
- THEN harden: stamp `calibration.version` into the meta of every artifact that carries
  surplus dollars (xfv.json already knows its frame; add to trade_values,
  mlb_projections, timeseries surplus block), and add a cross-artifact vintage tripwire
  test that fails when two served artifacts disagree on calibration version. This is the
  board-fingerprint lesson applied to the calibration layer: a fingerprint only guards
  what it NAMES.
- Also fix while in there: `timeseries` consensus-toggle surplus `dist.mean_mm` is RAW
  while the eFV dist is calibrated (two conventions on one page); make both calibrated.
- Do not run this regen inside the nightly box window (00:30-04:00 local) and never run
  pytest concurrently with it.

### 0.5 Outstanding model debts (schedule, do not silently drop)
- Team-outlook recenter: folded into Lane D (D1); the standing red
  `test_recenter_remainder_near_zero` stays red until that lane lands. Do NOT widen the
  bound.
- Provisional/flagship grade-map disagreement (~10 FV through the 1.5-3.5 WAR band,
  efv_ungraded._grade vs outcome_implied_fv): needs its own gate; schedule after Lane A
  (it interacts with any grade-seam re-key). GATE.
- Position-census fielding double-count fix is in the builder but the artifact was never
  regenerated. Regenerate `positions_played`/census artifact in the Phase 6 regen batch.
  OWNER was already notified; treat as approved-with-regen.
- Surplus "flat bottom" (3,906 rows at exactly $0.70M, the v6 successor of zero-floor
  Arm 2, sequencing prerequisite C6 already repaired): OPTIONAL lane, only if Lane A's
  re-key ships first; pre-register a sub-cutover re-anchor gate before touching it.

---

## Lane A: Surplus coherence (the Kade Anderson question) [P1, biggest served-number lane]

Measured state (all byte-reproduced): Anderson serves surplus_mm 87.4 (#1) with
xfv_grade 56.0, xfv_war_6yr 8.11; Made 80.4 at grade 60.9 / WAR 11.50. Anderson prices
at $10.8M per projected WAR vs $6.6-7.4M for the hitters below him. Decomposition: the
ENTIRE gap is the pricing-grade seam. Surplus prices `xfv_grade_display` ==
`xfv_grade_quantile` (retired 07-25 as the displayed grade) at `efv_score.py:892-945`
(`_reprice_surplus_on_display`, live call :1810-1812, export seam efv_export.py:44).
The quantile map caps a pitcher at the pitcher pool's consensus max (58.8), then
`_apply_side_fairness_fix` (efv_score.py:983-1072) joint-orders the >=52.5 band on an
expected-WAR crosswalk whose pitcher curve at q=1.0 is a SINGLE-PLAYER PAVA block:
Ohtani's two-way, hitting-inclusive 34.59 realized WAR sitting on a side=P row. Anderson
(q=1.0) inherits the band's top display value 60.1 and prices as an FV60.1 pitcher.
Counterfactuals: without the promotion he prices $78.8M (not #1); at his displayed
outcome grade he prices $59.6M. Side curves and ETA are exonerated (all four top players
share eta 0.5; pit/hit price ratio at equal grade is 0.92-0.97).

### A1. Crosswalk hygiene (ship first, smallest blast radius) GATE
In the F-SIDE-FIX crosswalk pool construction (pairs at efv_score.py:1116-1117):
- Strip two-way batting WAR from side=P realized targets (the Ohtani row must carry his
  PITCHING WAR on the pitcher side; his hitting belongs to the hitter row only).
- Decide the censored-extrapolation policy for the tail: paul_skenes carries 41.4
  "realized" WAR from the rate x 6 extrapolation (efv_dataset.py:664-667) with ~3 real
  seasons. Either exclude censored rows from the crosswalk or cap their leverage.
- Guard the terminal PAVA knot: minimum block size (>=3) or trimmed top, so no single
  player defines a curve endpoint.
- Re-run the W-FSIDE gate (its shipped purpose was DEMOTING over-promoted pitchers, top
  band pit share 0.37 -> 0.21; verify the repaired version still achieves that).
Acceptance: Anderson's pricing grade falls out of the joint-band top; board surplus #1
returns to a top-graded player unless the EV math genuinely says otherwise.

### A2. Re-key the dollar seam to the displayed grade OWNER + GATE
The registered follow-up already exists (POOLED_OUTCOME_REFIT.md section 1.3). Pricing
must consume the grade the board displays (`xfv_grade`, outcome_pooled), or the board
must display the grade pricing consumes; one coherent basis. Recommendation: re-key to
`xfv_grade`. This restamps every prospect dollar on the site, so: pre-register the gate,
owner heads-up with the blast radius (board total moves, order moves where quantile and
outcome grades disagree), extend `BOARD_BASIS_FINGERPRINT` to name the surplus pricing
key (it names grade field/scale/grademap/roles/feats today, NOT the pricing seam), and
remember the surplus backtest scores RAW predictions so it gates anchor changes, not
this; the EV-frame calibration gate (per-player MAE + bias diagnostics on the
normalized frame) is the governing instrument.
Sequencing: A1 before A2 (A1 changes the quantile grades A2 retires from pricing;
measuring A2's blast radius against un-repaired quantiles double-counts).
Note: p_bust/p_bucket stay PINNED to `_odds_grade` (measured decision, 07-30); do not
ride an odds re-key along with this.

### A3. Cross-side pricing honesty (LARGER, only if owner wants it) OWNER + GATE
The quantile pricing grade is denominated in consensus units where pitcher FV is
measured 2.21x optimistic at FV55+ (CROSS_SIDE_WAR_FINDING.md). A2 removes that channel
structurally. If A2 is refused, the fallback is a per-side outcome-consistent pricing
map. Do not do both.

### A4. Consistency tripwire
After A1/A2 land: one test asserting PROSPX board surplus == trade_values.json
trade_value_mm's surplus component == mlb_projections surNpv basis for a sampled set of
players, all carrying the same calibration.version. The consumers table from the
investigation (board -> xfv.json; trade machine -> trade_values.json; projections ->
mlb_projections.json; farm rollups -> timeseries org_summary; fantasy tiebreak ->
fantasy.json) is the checklist.

---

## Lane B: FV display coherence (compare tool, delta arithmetic, chip color)

The sanctioned resolver pair already exists: `gradeBlock(p)` (prospx/index.html:32248)
in JS, `_primary_fv` + `_fv_label` (build_site.py:875-903) in Python. Every fix below
routes through them; do not invent a third resolver. Rounding rules: eFV rounds to
NEAREST; consensus/scout FV and tool grades display CEILING.

### B1. Compare cart and the stale-field sweep
- `makeCompareSideBySide` prospx/index.html:53228 + 53241: replace `fvCloseLabel(p)`
  with `gradeBlock(p).label` (+ `fvClass` on the label). The GFX compare card
  (:34634) already does this; the interactive cart never got the migration.
- `makeCompareStatTable` :53058: the row labeled "Current FV" reads `fv_close`. Either
  point it at the eFV resolver, or relabel "Consensus FV" and ADD a "eFV / FV" row.
  Recommendation: both rows, labeled honestly.
- Similar-prospects badge :48461 (reads fv_close_raw with Math.round: wrong field AND
  wrong rounding), tool-comp chips :19900 (Math.round on consensus; must ceil or move
  to eFV), embedded trade-machine tab seeds :21165/:21184 and assets/trademachine.js
  :159/:179, trade-audit chips :22024-22027: same treatment, eFV-first via gradeBlock,
  consensus fallback ceiled and labeled.
- /trademachine/ board FV column (trademachine.js:715): trade_values.json rows already
  carry `xfv_grade` unused (bayes_trade_value.py:3779 exports consensus as `fv`).
  Display eFV-first like projections.js:314-320 does (the model implementation of the
  dual rule).
- pal.js:682 (pal_export.py:260 emits fv_close) and fantasy.js:500 Call-up Watch
  (fantasy_export.py:420): add xfv_grade to the exports, display eFV-first.
- Delete the dead var at prospx:20204.
Acceptance: arias reads 60 everywhere an eFV-graded surface shows a headline FV; any
consensus number on screen is labeled Consensus.

### B2. Delta chip arithmetic OWNER (display-style choice)
Stored values are consistent (58.1 raw consensus + 2.2 = 60.3 eFV); the display triple
(59, +2.2, 60) applies three roundings to two numbers. Two coherent options:
(a) chip subtracts the two DISPLAYED integers: `efvGradeDisplay - fvCeil(consensus_fv)`
    -> "Consensus 59 +1 -> eFV 60" (apply at :32489, :32557, tooltip :32353);
(b) print raw precision alongside: "consensus 58.1 +2.2 -> eFV 60.3".
Recommendation: (a) for cards, (b) inside the tooltip. Never mixed on one line.

### B3. Homepage chip color (build_site.py, NOT prospx)
`_fv_pill` build_site.py:895-903 tiers on the RAW grade while `_fv_label` :888 prints
floor(g+0.5). Compute the displayed integer once, tier on IT (disp >= 61 holo,
disp >= 60 gold). Same pattern at build_site.py:1732 (ticker holo border). Verify in the
GENERATED index.html: cholowsky ('fv-pill gold','60'), made ('fv-pill holo','61').
OWNER note (informational): this upgrades made's chip to holo; flag it, don't ask.
All `_fv_pill` call sites (Top Prospects, Movers, Debuts, wire, OTD) inherit the fix.

---

## Lane C: Scraper + consensus integrity (TJStats et al.)

TJStats verdict first, because the owner asked: the scraper WORKS (tjstats.py, last
capture 2026-07-31 12:58 UTC, parse byte-faithful). Arias showed #4 because TJStats
reshuffled INTRADAY after our capture; a fresh probe returned Arias #1. The PROSPX
per-source table correctly shows latest-stored-per-source. Fix cadence + visibility,
not the parser.

### C1. Ingest observability (the 8-day silent outage)
- Write `data/ingest_health.json` every run: per source, date, ok/fail, row count,
  message (run_tjstats_pipeline already returns status and never raises,
  tjstats.py:505-526; today that status is discarded).
- Tee pipeline stdout to `logs/` with rotation in deploy/nightly-build.sh.
- Red-line the run summary when any scheduled grade source writes 0 rows.
- Optional surface: a staleness banner per source on the PROSPX source table using the
  sidecar `captured_at` ("as of <time>").

### C2. TJStats cadence
Add a second Live capture to run_daily (endpoint is one person's JSON API; two polite
pulls/day). Alternatively accept 24h lag and stamp capture time in the UI. Do both
halves of C1 regardless.

### C3. Just Baseball repair GATE (touches stored history)
- Code: date-stamp rolling-page captures like tjstats does (label `JB Live <date>`,
  snapshot_date = capture date), gated by a content hash so a row set is written only
  when the page changes. Commit the currently-repo-absent midseason ingest path.
- Data repair: split the chimera under 'JB 2026 Preseason' (restore true March rows,
  re-label the June-content rows to their real interval). This edits snapshots that
  feed consensus history: back up the affected rows, and expect small consensus/eFV
  history diffs for affected players; run the repair through a script in tools/ with
  --dry-run/--apply like prior repairs, and run it on the deploy box too.

### C4. mlb_pipeline_international re-dating
Replace `date.today()` (scrapers.py:1720-1725) with a stable per-publication date,
advancing only when content changes (same hash gate as C3). Decide whether to repair
the 50 already-re-dated rows to the list's true publication date (recommended, same
--apply pattern).

### C5. performance_ingest synthetic votes GATE (moves consensus for 32 players)
Exclude synthetic sources from the FV vote in `compute_consensus_point` (skip
performance_ingest when appending explicit FVs), mirroring the killed BA-statcast
FV-40. The 2,808 flat-35 rows can stay for their other uses; they just must not vote
against real grades. Verify the 32 affected players' consensus moves are sane and the
single-instance FV-35 pull (consensus.py:701-713) still covers the truly-ungraded.

### C6. BA + ESPN cadence
- BA: no scraper exists (manual .txt drops, last 06-03). Either automate the monthly
  BA Top 100 through the same WebFetch-to-drop-file flow used for FG, or add a
  staleness banner (age > 45d) to the run summary. OWNER: pick automation vs banner.
- ESPN: hardcoded per-article URLs (scrapers.py:1093-1111). Add a probe that detects a
  newer McDaniel ranking article and prompts the manual URL add.

### C7. Consensus staleness policy OWNER + GATE (do NOT ship unilaterally)
Today a stale source votes at full weight forever (forward-fill, consensus.py:1181-1207,
equal weights :607-608; no decay, no expiry). If the owner wants recency decay, the seam
is `_fv_weights` inside `compute_consensus_point` (each vote carries snapshot_date).
This moves the whole served board: full gate + golden restamp + two export passes.

---

## Lane D: FA engine program (Chisholm, staleness done in 0.3, $/WAR page, ladder)

### D1. The star tail / Chisholm / team-outlook recenter (one lane, one root)
Measured decomposition of Chisholm's $12.9M AAV (served row reproduced byte-exact):
warY1 1.76 is ~100% of the gap. Components: bat term collapses to +0.09 WAR because the
in-progress 98 wRC+ 2026 carries Marcel weight 5 of [5,3,2]; the 07-30 PT refit shaves
40.8 PA (-0.17 WAR); defense recovers only +0.21 of his ~+1.2 (map is defense-blind
except a K=1200-shrunk realized-residual channel). At warY1 2.5 the same market model
outputs $39.6M AAV, past realistic, exposing a comps-anchor cliff (k=5 nearest-comps
median jumps tiers discontinuously: guarantee x4.6 from 1.76 -> 2.5). Naylor signed
5/$92.5M at a projected 1.91.

Work items, in order:
1. OWNER: the team-outlook recenter decision. Both measured candidates FAIL their own
   gates (cohort refit loses holdout 7.29 vs 7.19; PT re-anchor re-introduces a measured
   PA error, +51.3 vs -13.6). The tradeoff is LEVEL vs measured accuracy
   (TEAM_OUTLOOK_RECENTER_VERDICT.md). Present it as: accept the level convention and
   close the red with a documented recenter-at-aggregation (re-anchor only the summed
   team outlook, not per-player), or keep hunting a per-player fix. A
   recenter-at-aggregation candidate was never measured and is the natural third option.
2. GATE: star-tail cell repair. >=4-bWAR hitters: map predicts 2.66 vs 5.56 actual, cell
   MAE 2.92 vs naive carry-forward 2.37. Cheapest lever with an existing measurement:
   REALWAR_K x0.5 scored BETTER (fa_projection.py:921-922); sweep K properly. Second
   lever: defense as a real feature in the FA WAR map (mlb_def_history.json +
   savant_oaa.json exist and already feed proj_ml's pos_adj_prior; never tried in the
   FA map). Gate on Gate-1 WAR MAE AND the bias fields (per-tier bias is the instrument
   that caught the last regression; a per-player MAE gate cannot see level).
3. GATE: comps cliff. Kernel-weighted comps or larger k with distance weights
   (fa_market.py:1524-1552, comps_for :1717). Acceptance: guarantee is continuous in
   warY1 over [1.5, 3.0] (no >2x jump for +0.75 WAR).
4. GATE: market recal middle ground. Shift-only leaves per-tier bias -2 to -15 $M
   (fa_market.py:126-127); full log-log overshot twice. Untested middle: per-group
   INTERCEPT-only shift. Golden restamps owed at fa_market.py:139, fa_projection.py:768,
   :923 ride whichever ships.
5. Fix the vet join (defect 13): mlbam-keyed Spotrac contract join with name-normalize
   fallback (suffix handling: "Jazz Chisholm Jr."), StatsAPI roster fallback for team
   assignment (proj_export.py:161-183, :800-802). Acceptance: dropped vets 361 -> <50,
   Chisholm appears in NYY Team Outlook.
6. Optional gated follow-ups if time: POS_GROUP_MODE v2 (premium/corner split, measured
   hitter underpricing $7.52M vs pit $4.02M), AAV integer-years division (measured
   null twice; leave unless owner asks), guarantee-band scale re-gate as corpus grows.
Acceptance for the lane: Chisholm's served AAV lands in a defensible range (the model's
own comps say ~$18-25M at his talent level), star-slice bias shrinks toward the
baseline -2.11, and the recenter red is CLOSED by decision, not by widening the bound.

### D2. $/WAR by winter: full detail page
Data exists, zero new ingest: fa_signings 1,760 rows / 12 winters with pos, years,
guarantee, aav, qo, mlbam; ledger realized fields on 1,429; already client-side in
fa_archive.json. Build:
- A dedicated page (pattern: /trademachine/ split; generate via build_site.py shell +
  a new assets/fa_dpw.js or extend fa.js with a route) reachable by CLICKING the
  existing dpwTrendChart sparkline (fa.js:724, mounted :789).
- Content: implied $/WAR by winter (existing series fa_market.py:500-521); realized
  $/WAR by winter from the ledger; per-position-group per-winter $/WAR (SP/RP/IF/OF/C);
  by length bucket (1yr / 2-3 / 4-6 / 7+ pooled); by guarantee tier; deal counts,
  total spend, QO share.
- EXPORT PREREQUISITE: client-side realized math needs `paid_to_date_usd` + elapsed
  fraction, currently stripped at fa_export.py:658-667. Add `paidTd`/`elapsed` fields;
  without them recent winters overstate wildly ($40M+/WAR).
- Age-at-signing is computable server-side (fa_market.py:1793 `_age`) but not persisted;
  persist it if the position/age cuts want it. Signing DATE does not exist anywhere;
  do not promise a within-winter timeline.
- Follow dataviz + site theme conventions; wire glossary tooltips (eephus-gl).

### D3. Positional ladder repair GATE (low blast radius, measured consumers)
Root causes (all three verified): lstsq with no sum-to-zero constraint (level
unidentified since shares sum to 1), DH exposure 0.0718 vs ~0.115 (equal-weight reading
under-cancels), pre-2022 bWAR positional runs sum ~-10/season league-wide. The owner's
+8 is the ex-DH equal-weight sum (+9.5 measured).
- Refit on the modern window per the ask: `fit_ladder(first=2012)` is a parameter
  change; also fit 2018+ as a sensitivity (2018-2026 sums to -1.98 already). Impose the
  identification explicitly: exposure-weighted sum-to-zero constraint, and PUBLISH both
  readings (weighted sum == 0 by construction; equal-weight sum reported with the DH
  caveat) in the eval artifact so the "+8 mystery" cannot recur.
- Deduplicate: prospect_def_value.py:127-138 POS_ADJ vs positional_fit.py:167-249
  fit_ladder (the eval artifact itself flags duplicate_ladders_found). Pick ONE owner
  (recommendation: positional_fit.py fits, prospect_def_value imports the artifact).
- Kill the legacy leak: prospx `_RPS_POSITION_MULTIPLIERS` still encodes the retired
  folklore table into RPS+. Re-derive from the refit ladder or route through the
  artifact.
- Blast radius: only prospect_def_value/def_value consumers (~87% of graduated comps
  reorder); def_home.json byte-identical; proj_ml and FA pricing do NOT consume it.
  Still: registry row + eval artifact + snapshot diff.

---

## Lane E: eFV pace program (Arias / de Paula "seasons to reach level")

Measured truth to carry into this lane: the penalty is real but SMALL, and arias' net
pace+age treatment is POSITIVE (+0.066 WAR6: n_milb_seasons -0.302, age_rel_level
+0.274, age +0.094). de_paula nets -0.150. Worst case ~0.3-0.4 FV. Both grade ABOVE
consensus today (+2.2 / +1.9). The louder defect is narration (defect 16): the chip
shows the raw -0.30 undiscounted. Also: n_milb_seasons counts DSL/CPX seasons with no
entry-level conditioning, and the ONLY entry-pathway machinery (is_ifa dummy) is inert
(-0.0010), so a DSL starter does mechanically carry more counted seasons than a college
draftee at the same rung. AP+ is EXACTLY the starting-level-aware construct (peer
baseline = starting_level x experience_year fixed effects + entry-age/era/position/
pathway dummies) and rates arias 112.4 (91st pct), de_paula 108.4.

### E1. Chip narration fix (ship immediately, display-only)
Suppress or re-label the "Seasons to reach level" chip when the player's pace from
entry is fast (compute `pace_from_entry` display-side in the exporter, or join AP+ for
display only, which the isolation contract ALLOWS - it forbids MODEL consumption).
Minimum: scale the chip magnitude by calibration x blend so it reads the served effect
(-0.09 FV for arias, not -0.30 WAR), and only fire it when the net of the pace+age
group is negative. Wire through `efv_factor_groups` so the explainer groups stay
coherent.

### E2. The AP+ / pace test program GATE + OWNER (contract)
- OWNER first: AP+ is contractually forbidden from feeding eFV three ways (vendored
  fail-closed isolation test, export header, artifact display_contract). Options:
  (a) amend the contract to allow a gated model test, or (b) build an eFV-NATIVE pace
  feature in efv_dataset._milb_features from milb_history (same substrate, no AP+
  import, works for pitchers, as-of-correct by construction). Recommend (b); it needs
  no contract change.
- Candidate encodings, in gate order:
  1. `pace_from_entry` = (level_rank - entry_level_rank) / n_milb_seasons (arias 1.00,
     de_paula 0.80, college-at-AA-yr2 1.00: the DSL start becomes numerator, not
     penalty).
  2. `entry_level_rank` alongside n_milb_seasons (collinearity warning: is_ifa /
     is_college may wake or split; pre-declare the explainer group).
  3. AP+-style peer-adjusted residual computed on train folds only (mirror
     _resolved_norms leakage pattern).
  4. Interaction pace_from_entry x age_rel_level.
- Emit unconditionally in `efv_model._vec` (the _fit_lgbm_mono KeyError trap), impute
  at train mean behind milb_missing, guard left-censored pre-2015 entrants with an
  entry_observed flag (AP+'s own 2014-guard pattern).
- Coverage: ~42% of labeled rows get a real value (818 hit / 838 pit), same support as
  the shipped milb block.
- PRE-REGISTER the expected failure: three precedents of survivorship sign inversion
  on exactly this feature family (n_milb_seasons marginal +, conditional -; E1
  seasons_at_level hitter arm inverted at p 0.375; pit age_rel_level flipped). An
  inverted hitter sign is the artifact, not a finding; do not ship it as "DSL starters
  are worse". Gates: forward-chained pooled rho vs MDE95 floors 0.017/0.016, zero-info
  permuted-column control, feature-specific permutation null (30 draws, the E1 bar),
  paired bootstrap B=2000. Matrices are gitignored: back up, verify restore (arias
  ops_rel 0.24769633507853406, level AA), `git checkout` the two *_dataset_report.json
  after.
- Likely best consumer insight: the same pace column fits -0.59 in the fv-anchor-free
  efv_ungraded set vs ~0 in the anchored flagship; if the flagship arm nulls, gate it
  into efv_ungraded instead, where pace signal is not already priced by scouts.

---

## Lane F: New display features

### F1. Healthy FV for injured players
The factor is stored separately but the served grade is NOT client-side invertible
(factor multiplies the model leg of the lambda-blend, then nonlinear outcome map, then
quantile display map). Compute at export:
- efv_score.py run_live (:1639-1676, quantile block :1777-1793) and run_backgrade
  (:2019-2121): when inj < 1.0, recompute the counterfactual with inj=1.0 KEEPING
  sc/agef/rolef, through the same maps -> emit `xfv_grade_healthy` (and optionally the
  display-map sibling).
- efv_export.py:62-63: passthrough next to injury_factor into data/xfv.json.
- If efv_board_scale ever enables, stamp_doc must calibrate the sibling too.
- Display: append to the existing injury glyph tooltip (prospx:32422-32423) and the
  efvTooltip penalty line (:32367); visible line in the "Currently on X IL" amber
  block (:47661-47686) and the efvDetailCard explainer row (:32555-32567).
- Do NOT fake it client-side from injury_factor (double-penalty bug class) and do not
  touch the separate tiebreakerScore x0.70 IL multiplier (display-order only).
- Artifact shape is test-pinned (test_efv_export.py); healthy sibling mirrors the
  xfv_grade basis and eFV round-to-nearest.

### F2. Lottery odds: top-6 chance + GB to the top-3 slot
The cached Tankathon table already contains 'Top 6' percentages and W-L records; we
parse only the '#1 OVR' cell.
- scrapers.py:3038-3108: capture `top6_pct` (cells[-2]), `wins`/`losses` (cells[2]
  "W - L"). Index from the END deliberately (rows carry a trailing empty cell vs the
  header); playoff rows (picks 19-30) have no % cells; comp-pick rows carry synthetic
  pick_pos 31-42 and are excluded from GB math.
- storage.py: ALTER-TABLE migration on draft_lottery_odds (+odds_top6_pct REAL, +wins
  INTEGER, +losses INTEGER) following the :1859-1909 pattern; extend upsert :3090 and
  load :3113.
- draft_export.py:816-823: pass through.
- prospx `_renderDraftLottery` :23171-23208: add "% Top 6" column and "GB to 3rd"
  computed client-side vs the pick_pos==3 row: GB = ((W_t - W_3) + (L_3 - L_t)) / 2.
  (Tankathon's own GB column is vs the WORST record; do not reuse it. The top-3 seeds
  share identical odds by CBA design, so 3rd-worst record IS the top-3-odds boundary.)
- Nullable columns: historical rows lack the new fields; frontend tolerates null (same
  as odds_pct on picks 7+).

### F3. Tool comparison radar on the compare panel
Pure reuse, no new function: `_gfxRadarOverlay` (prospx:34580-34592, SVG string) is
already used in the live DOM by the Scouting-tab tool comp (:19884-19905) with theme
tokens. In `makeCompareSideBySide` (:53223), between the FV overlay (:53251) and the
stat table (:53252): build series via `_radarToolsFor(p)` (:19862) + COMPARE_COLORS,
gate to all-hitters or all-pitchers (side detection :53054-53055; mixed cart already
renders a notice :53216), size ~300 for the ~880px panel, legend like :19902, per-player
"no tool grades" gate like :19886 (else a gradeless player draws a collapsed 20-floor
polygon). Do NOT touch buildCompareCard's concrete-hex palette (html2canvas cannot
resolve var()); share the series builder, never the palette.

---

## Lane G: List layout unification (FA + Projections on the PROSPX/fantasy chassis)

The reference implementations: PROSPX rows (fixed 136px, shared header/row grid class,
`minmax(0,1fr) auto` row template, delegated sort with aria-sort + URL round-trip) and
fantasy's `.ff-card` (fixed 104px, the most faithful port, WITH `.ff-sortbar` giving
row-2 tape chips their own sort buttons: site.css:2738-2805). Tables stay tables
(mlbstats, PAL, trade machine, FA secondary views, Team Outlook are the density gold
standard; fantasy.js:146-155 documents why).

### G1. FA class board (assets/fa.js)
- Row 1 tracks: # | Player (name/pos/age/from/hand/QO) | Status | proj AAV | Yrs/Guar |
  Surplus | Verdict. This RESTORES sortable AAV and Guarantee (the card conversion at
  commit 53355d9 deleted the `sHead("projAAV","projAav")` header while the comparator
  at fa.js:523-533 still handles any member key; the affordance died, not the sort).
- Tape (all sortable via a sortbar clone of .ff-sortbar): WAR y1, Deal WAR, rational,
  warCvar10, star odds, option, length band. Fits/comps move to the expander or the
  #player card (widest, least scannable content; currently the unbounded-width chips).
- Fixed height ~88-96px, content-sized (the ff-card lesson: do NOT copy 136px),
  `contain-intrinsic-size` matched, `minmax(0,...)` on every flexible track, tape
  scrolls in its own overflow-x box, <=720px releases fixed height and the header
  becomes a chip strip.
- Fix defect 15a: `boardState.sort` default must be a key a header carries (restore
  projGuar's header or default to surplus to match "#"); first paint shows an active
  indicator.
### G2. Projections players board (assets/projections.js)
- Row 1: # | Player | 5y WAR | AAV (new sortable, m.aav exists) | Age (own header,
  stop overloading "Contract") | Surplus.
- Tape sortbar re-exposes the still-working y0..y4 season comparators (:243-253,
  currently reachable only via #sort=y0 URL) plus contract-status chip.
### G3. Acceptance
Every column visible on either board is sortable; keyboard + aria-sort parity with
PROSPX; no overlap at 1280/1024/720/390 widths; fantasy untouched; tables untouched.
Run the a11y sort tests serially after (expect the documented one-red-after-editing
cold-load artifact; two consecutive reds on an unchanged tree = real).

---

## Sequencing and regen choreography

Order: Phase 0 (0.1-0.4 immediately) -> Lane B (display-only, no artifact regen except
homepage rebuild) -> Lane C (C1/C2 free; C3/C4/C5 need --apply repairs + consensus
diffs) -> Lane A (A1 gate, then A2 owner + gate) -> Lane D (D1 owner call early, work
items in order; D3 independent) -> Lanes F and G (display/features, parallelizable) ->
Lane E (model program, longest gates) -> D2 page last (depends on export additions).

Regen batching: collect every artifact-moving ship (A1/A2, C3/C4/C5 repairs, D1
projection changes, D3 ladder, F1 healthy field, census regen from 0.5) into as few
full-chain regens as possible. Remember:
- A basis change needs TWO export passes (overall_rank lags xfv.json by one run).
- rebuild_only runs the WHOLE eFV chain; efv_export --all afterward is redundant.
- Never regen or pytest during the nightly box window (00:30-04:00); check
  `git status prospect-tracker/data/` before diagnosing any red.
- value_framework.py edits require `python value_framework.py --emit-snapshots`.
- Golden restamp after served numbers move; PINNED_MIX is a band, fingerprint exact.
- Final: suite serially ONCE per phase (never in parallel agents), commit explicit
  paths (never add -A; an external reverter watches sentinels), push main, sync beta
  (0.1 recipe), deploy-box runs (0.2), verify the three coordination points
  (fingerprint match, xfv_history_is_on_board_basis() True, side-mix band).

## Acceptance criteria summary (the owner-visible outcomes)

1. Kade Anderson's surplus rank follows from a coherent grade basis; toggling
   consensus/eFV no longer flips him between $87.4M/#1 and $63.4M/#4; trade machine,
   projections, farm rollups and board all price on one stamped calibration vintage.
2. Compare tool and every headline FV surface show current eFV (arias 60), consensus
   only where labeled; the delta chip arithmetic is visibly consistent; cholowsky's 60
   chip is gold on the homepage.
3. TJStats verdict documented (works; intraday lag), second daily capture or as-of
   stamp; ingest health visible; JB/intl/BA/ESPN/performance_ingest defects fixed;
   every grade source's cadence is enumerable from ingest_health.json.
4. Injured players show a healthy eFV somewhere sensible.
5. Lottery section shows % Top 6 and GB-to-3rd.
6. Tool radar on the compare panel.
7. Arias/de Paula pace: chip narration fixed; pace feature tested under pre-registered
   gates with the inversion expectation on record; AP+ contract decision recorded.
8. eFV display+calc audit (B) leaves one resolver pair, two rounding rules, applied
   exactly once, everywhere.
9. FA/Projections lists: compact fixed-height rows, AAV sortable again, every visible
   column sortable, no overlap.
10. Chisholm's AAV is defensible or the residual gap is measured and documented as a
    market-model limitation; the 361 dropped vets are joined; the recenter red is
    closed by decision.
11. $/WAR winter chart clicks through to a full page with per-position and realized
    series.
12. FA signings staleness reads truthfully (and the frozen 2027 board is unfrozen,
    which is a today-P0).
13. Positional ladder sums to zero under its stated convention, refit on the modern
    window, one fit owner, folklore table gone.

## Appendix A: Ground rules (non-negotiable, learned expensively)

1. NEVER run pytest while a regen is running, and never in parallel agents; conftest
   git-restores dirtied artifacts at session end and will destroy concurrent work.
2. Commit explicit paths only. Never `git add -A` (external reverter + nightly churn).
3. The nightly box pipeline (00:30-04:00 local) rewrites data artifacts under you.
4. eFV matrices are GITIGNORED. Back up before matrix experiments, verify the restore.
5. Registry rules: measured no-ship = `deprecated` WITH artifact + MODEL_GLOSSARY
   entry; `unvalidated` REQUIRES eval_artifact null. Check after every lane.
6. Rounding: consensus/tools CEIL, eFV/'+' stats NEAREST. Color tiers key on the
   DISPLAYED integer (Lane B's whole point).
7. Copy: no em-dashes in user-facing prose; strip_emdashes --check + copy_lint gate.
8. prospx/index.html is HAND-MAINTAINED (build_site.py generates homepage/shells; the
   homepage drawer lives in the generator).
9. Savant endpoints: the param is `year`; `season=` is accepted and silently ignored.
10. Commit messages with $ or quotes: `git commit -F file`.
11. conftest pins test_value_framework to the IDENTITY valuation set; drive constructed
    configs, and re-capture prospx_current.yaml INSIDE its own valuation_set context.
12. A fingerprint only guards what it NAMES. Extend it when you move a seam it does not
    name (Lane A extends it with the pricing key; 0.4 adds calibration vintage).
13. Adversarially verify agent measurements before acting on them (3 of 5 were wrong
    on 2026-07-31 round 2).

## Appendix B: Explicitly NOT re-attempted (spent levers; do not re-open blind)

Surrogate labels (both sides), B3 level blend, K_REL_PA revert, ADOPT_NORMALIZED
consensus off, WAR-rate into FA projections (G2 fail), odds cohort offsets (killed by
its own shuffle control; Platt shipped instead), per-side FV outcome curves (null),
tool-grade additive offsets (do not replicate), DRS ingestion (Cloudflare), arm-gate
raw thresholds (throw context), K-prior, park/age/velo/decay lanes. See the memory
index for the full loss ledgers.

## Appendix C: Read-first list

Memory: surplus-ev-objective-2026-07-31, master-plan-2026-07-30-nine-asks,
efv-fa-execution-2026-07-30, fv-industry-framework, deploy-hosting-state,
pytest-pollutes-data-files, copy-style-no-emdash-no-llm, grades-round-up.
Docs: docs/efv-2026-07-30/TEAM_OUTLOOK_RECENTER_VERDICT.md, POOLED_OUTCOME_REFIT.md,
CROSS_SIDE_WAR_FINDING.md, TRADE_ARCHETYPE_FLOOR_GATE.md, REGEN_AND_PUSH_RUNBOOK.md,
docs/METHODOLOGY.md, deploy/WEBMASTER.md.
