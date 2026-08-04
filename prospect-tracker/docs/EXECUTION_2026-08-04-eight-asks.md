# EXECUTION 2026-08-04: the eight owner asks

Plan: `docs/master-plan-2026-08-03-eight-asks.md` (written 2026-08-03 from a 10-lane
read-only recon). This is the execution record. Numbers here are the acceptance record: if
a later run disagrees, something regressed.

Session opened by pushing the 23 pending commits (`7626fd0..5325440`), so `origin/main`
was clean before any new work landed.

---

## Owner decision taken during execution

**Hero cards keep their photos; photos come off the LISTS only.** The plan had flagged
this as an open question (plan Lane A2). The owner ruled: "the single-player hero cards
should keep their photos, I just want photos-off for the lists." Lane A was scoped to
exactly that.

---

## Lane A: generateGFX overhaul (commit 406ac05, plus cce3f23)

The owner's ask had four parts: remove player pictures, spend the space on the cramping,
stop the name truncation, and stop using the wrong font.

**Photos off the lists, kept on the cards.** `buildProspectCard`, `buildCompareCard`,
`_gfxMiniCard` and the legacy farm row renderer are untouched, as is the `photos` toggle
that feeds them. The toggle is relabelled "card photos" and now only appears on card
modes, because on a list it would be a control that silently does nothing.

**ROWS (the default board).** Dropping the 30px headshot and its 6px gutter hands 36px per
row straight to the name field, which is where the truncation came from. Measured by
running the shipped geometry functions under node, wide 16:9 at n=100:

| | before | after |
|---|---|---|
| grid | 6x17 | 4x25 |
| column width | 243px | 371px |
| name field | ~140px | ~275px |
| name size | 12.5px | 13px |
| meta size | 9px | 11px |
| empty cells | 2 | 0 |
| vertical fill | - | 97.8% |

The name step went UP even though the rows got denser, and the meta line rose 9px -> 11px,
closing the one place the board still broke the "nothing under 11px" floor the chip work
set. At a 600px-wide timeline render, 9px is 3.4px on screen.

**TILES (was "Chips").** This layout existed to showcase the headshot and its column search
literally maximised photo area. Rebuilt text-first: the search now maximises the NAME
budget, and with the photo well gone the vertical budget buys TWO LINES of name. That is
the actual fix for "missing spaces for prospect names" - the old chip ellipsised past
roughly 14 characters, so hyphenated and double surnames lost their second half on every
board. Names wrap now instead of truncating.

**Everything else in the same complaint family:**

- Card names had no ellipsis, no `min-width:0` and no step-down at 44/40/22/18px, so a long
  name wrapped and shoved the card body down. On the compare card it also broke the three
  columns out of alignment, because each is an independent flex column. Names step down to
  fit (`_gfxFitNamePx`) and the compare name sits in a fixed-height box, so the FV badge row
  is pinned across all three columns.
- **Three SVG helpers carried three DIFFERENT literal font stacks**, so one card could
  render its radar labels, overlay labels and axis labels in three different faces. This is
  the concrete "not using our preferred font" defect. html2canvas serializes inline SVG
  standalone where `var()` cannot resolve, so literals are necessary; there is now ONE,
  mirroring `--font-retro-mono` rung for rung.
- The webfont link pulled SIX families. Five (Inter, JetBrains Mono, Source Serif 4, VT323,
  Press Start 2P) appear in no `font-family` stack anywhere in the tree, verified by grep,
  and were racing `document.fonts.ready` before every capture for nothing.
- `fonts.ready` resolves for faces the document already decided it needs, and every face
  here is `font-display:swap`, so a cold first export could rasterise the fallback. The
  exact weights are now explicitly loaded before capture.
- The asset preloader only scanned INLINE `background-image` - correct for today's markup,
  silently wrong for any future class-based background.
- A board that does not fit its format extended past it in silence, so "Wide 16:9" could
  return a 16:9.4 PNG. The footer now discloses it.
- The card-pack sheet returned a hardcoded width of 1080 while styling itself to the
  selected format's width.
- Renderers handed a raw un-normalized row drew blank cells and threw nothing (escapeHtml
  returns "" for null). That is how the chip board shipped as a grid of logos on
  2026-08-03. It warns now.
- Tile height budget was itemised against the markup after a first pass under-reserved the
  meta line by 4px and forgot the 2px border - a 6px under-reserve that would have clipped
  on a tight canvas, i.e. the exact failure the rewrite exists to remove.
- Default count opens at 100 rather than 50, matching how the row board is actually used.

**cce3f23 - the OTHER GFX engine never waited for its font.** The site has two: the
DOM/html2canvas one in prospx, and the canvas-native `assets/eephus-gfx.js` that draws the
FA, Projections, MLB Stats and news boards. Canvas text does not wait on webfonts:
`g.font = "700 26px DotGothic16"` silently draws in the next family if the face has not
loaded, and every face is `font-display:swap`. So the FIRST graphic of a session could
rasterise in a different typeface than every later one. Now loads the exact weights once
per session, memoised, failures resolving rather than rejecting, raced against a 4s
timeout.

**Verification.** Extracted the shipped functions and ran them under node: the geometry
acceptance matrix (7 formats x n in 10/25/50/100) passes for both layouts on every check
(no name under 12px, no ragged column, name field >= 140px, tile cell >= its own text
budget); and the rendered HTML for both layouts carries no headshot URL and no photo
background layer while keeping every name. Full inline script syntax-checked with node.

---

## Lane E0: the eFV disagreement instrument, and a delta that pointed at a retired grade (commit 4eecb44)

The owner asked to get eFV "even closer on the biggest disagreements". There was no
committed answer to *where* those are on the live board: the resolved cohort publishes its
biggest movers, but `run_live` only ever emitted a mean and a max, so every discussion
started by rebuilding the list by hand. `run_live` now emits a ranked block, top 25 each
direction, with consensus, eFV, predicted WAR6 and surplus per row. Display only.

Building it surfaced a real doc-drift bug. The two delta fields now mean the OPPOSITE of
what the export comment says. That comment was itself "corrected" on 2026-07-23 to read:
*the realized delta does not track the displayed headline, the headline's delta is the
quantile one.* True then. Then 2026-07-25 flipped `BOARD_GRADE_FIELD` to `xfv_grade` and
retired the quantile map as the served grade, and the note was never revisited. So today:

- `xfv_minus_consensus` = `xfv_grade` minus consensus = **what the site actually shows**
- `xfv_minus_consensus_quantile` = a grade the site stopped serving in July

Anyone reading the comment to find "the headline's delta" was sent to the retired field.
The size of the gap is why this matters, measured on the 2026-08-03 live board:

| basis | mean abs delta | rows >= 5 FV apart |
|---|---|---|
| served (`xfv_minus_consensus`) | **12.47** | **1,597 of 2,015** |
| retired quantile | 0.56 | 18 of 2,015 |

A quantile remap onto the consensus distribution reproduces consensus almost by
construction, so quoting those numbers would say the model barely disagrees with the
industry, which is the reverse of the truth. The new block therefore names its bases
`board` and `legacy_quantile` rather than inheriting the misleading field names.

---

## Identity: `bind_player_ids` guarded the key and let the id be stolen (commit 1169ebf)

Found by the draft-id-seeding lane, fixed at source. A binding is a pair and only one half
was guarded. The docstring promises it skips a key already bound to a different id; that
half worked. An id already bound to a DIFFERENT key was repointed without a word, because
the key-side guard passes for an unseen key and then

    ON CONFLICT(mlbam_id) DO UPDATE SET
      player_key = COALESCE(excluded.player_key, player_photos.player_key)

overwrites the owner - `excluded.player_key` is never null on this path, so the COALESCE
could only ever choose the incoming key. It reads like a defensive merge and behaves like
an unconditional overwrite.

Live example: MLBAM 814385 belongs to `jackson_natili`; the draft feed spells the same pick
`jack_natili`; an unguarded harvest MOVED the id onto the draft slug. Since `player_photos`
is the canonical durable id-to-key table and the export's last-resort id source, that
propagates.

Guarded in both directions and deliberately twice: python skips an id owned by another key
so the skip is observable, and the SQL `DO UPDATE` only fires where `player_key IS NULL` so
a future caller that forgets the python guard still cannot corrupt a binding. Verified by
replaying both statements against a scratch table. Also covers the caller at
`run_monthly.py:2120`, which had the same exposure.

---

## Correction to standing memory: the NPB parser red is NOT red

Memory and the recon both carried "test_overseas_stats NPB failure is PRE-EXISTING /
still RED". Verified by actually running it: `python -m unittest test_overseas_stats`
returns **10/10 OK**, and `scrape_fg_player_stats` returns its 3 NPB rows from the cached
page. The recon's claim was static inference from a cache mtime, not a run. No parser fix
was needed and none was fabricated; the hardening half (making a zero-row parse loud
rather than silent) is the part still worth doing.

---

## Wave 1: one eFV basis across the site (commit adc7a8d)

**/projections/ was serving the RETIRED quantile as its eFV grade.** The board flipped to
`xfv_grade` on 2026-07-25 and `build_site` got the matching repair the same day, but
`proj_export` kept a private copy of the precedence and was never repointed, so the module a
reader would most naturally compare against the board disagreed with it. It now calls
`efv_board_scale.board_value`. Pricing stays on the quantile deliberately, because the value
curves were fitted on the consensus 20-80 scale, which is why the 07-30 refit moved zero
dollars; that split is now stated rather than implied.

Measured so the box regen is not a surprise: of the 201 active rows clearing the price gate
(the real /projections/ population) **196 display grades move, median +1.4 FV, range -3.8 to
+3.4**. The row SET does not change, because the gate still reads the quantile.

**/fantasy/ showed two different numbers under one name**: dynasty served the quantile, call-up
served the raw grade, both labelled "eFV". Display is unified on the board grade; the quantile
stays as the dynasty blend's score driver, which is a registered model input.

**Trade Machine: three served rows are not players.** `kelvin_herrera` is a live DSL arm born
2007 bolted to a 2011 debut and a career-WAR map ending 2020. The inactive rule could not see
them because it keys on `roster_status.mlb_seasons`, empty on 782 of 2,681 debuts rows.
`identity_collisions.json` does not know them either: it counts humans per slug in the CURRENT
roster feed, and the retired half of each pair is not in it, so each slug looks singular. The
guard reads the record's own internal contradiction instead (age under 17 at last MLB season).
Fires at 12.6 and 9.1; does NOT fire at 29.7 for a genuinely retired reliever.

**GRPO no longer shifts the prior**, so the tooltip promising it "does not change the surplus"
is true in every artifact state. The alternative (assert every row is repointed) was
implemented FIRST and then measured: 4,512 of 4,549 prospects carry a non-zero adjustment, so a
stale `xfv.json` would have deleted the prospect board instead of falling back to it.

**MLB Stats**: provisional-row opacity was ghosting the frozen first column; PAL was freezing a
rank digit while the name scrolled away; and a table-wide expanded panel (`colspan`) was being
pinned as an identity column, so it slid out from under its own row. Frozen-vintage dates that
the exporters have been passing for the frontend to disclose, and which nothing ever rendered,
are now shown.

**Homepage**: the scatter teaser was 16 random dots and is now 16 real players; the lead story
had been the same June 5 article for two months and now falls back to live wire data past 21
days; a new eFV distribution module deliberately EXCLUDES the 20-floor spike (3,257 of 4,549
rows) with the count stated, because plotting it drowns every real bar.

## The aStuff+ scale was lying (commit 28a4cdb)

Every 100+10z metric on the platform means "10 points is one standard deviation". aStuff+
divided the SHRUNK deviation by the RAW pool spread. Shrinking pulls every arm toward the mean,
so the denominator was strictly too wide and every z came out understated. Anchor pool: raw sd
0.003785971, shrunk sd 0.002712389, **ratio 0.716432, so the index moved 7.16 points per sigma
and an aStuff+ of 110 was plus 1.40 sigma, not plus 1.0**, while the pill tooltip, the glossary
and the docstring all promised otherwise.

The fix is genuinely ATOMIC. aStuff+ is the right-hand side of `efv_statcast_overlay`'s frozen
linear fits, so changing the denominator alone would have silently re-weighted a LIVE overlay
by up to 0.330 FV on 285 rows. But it needs no refit, and a refit is not permitted:
`tools/aaa_physics_screen_lab.py` is one-shot by design. An affine rescale of the predictor is
absorbed EXACTLY by re-parameterizing (slope' = r*slope, intercept' = intercept +
100*slope*(1-r)), leaving fitted values, residuals, `resid_sd` and every lo95 survivor verdict
untouched. Asserted to 1e-9 at three points on each of 15 fits.

Measured, both producers agreeing at `max_abs_diff 0.0` after regen:

| | before | after |
|---|---|---|
| anchor-pool sd | 7.16 | 10.000 |
| served sd | 7.034 | 9.816 |
| rows moved | - | 1,353 of 1,379 (mean abs 2.21, max 13.9) |
| strict order flips | - | **0**, checked over all 950,131 pairs |
| display bands crossed | - | 190 (green pills 72 to 150) |

The band movement is CORRECT: those bands were written to mean plus or minus one sigma and had
been firing at 1.40 sigma. Found by an independent recomputation that reproduced the served
file byte-identically (1,379 of 1,379) BEFORE touching anything.

## Lane E: three registered gates run, all no-ships (a744797); incumbents re-measured (c4dd62d)

**Read the eval regen carefully.** Old vs new is NOT like-for-like: the 07-24 matrix is
gitignored and overwritten, so labels and the consensus anchor both moved. The clean control is
the hitter side, whose feature list is byte-identical to 07-24: its consensus BASELINE moved
+0.0201, itself above the 0.017 hitter MDE95. So any old-vs-new movement smaller than that is
data vintage. On that reading the -0.0110 hitter edge shrink and the +0.0119 pitcher edge gain
are BOTH drift and neither is a claim.

The one same-rows test that IS a claim: re-gating `seasons_at_level` on today's pitcher matrix,
same 438 rows, lambda fixed, reproduces the 07-30 ship evidence almost to the digit (rho
+0.0143, both AUCs up, 0 of 30 permutation draws beat it, p=0.032, 3.6 sd out).

- **PACE_FROM_ENTRY: NO-SHIP.** The pre-registered kill criterion FIRED and was not relaxed:
  the hitter arm fits a NEGATIVE weight on pace (-0.0419, negative in 3 of 4 folds), named in
  advance as the survivorship-censoring artifact. Permutation p=0.71 hit / 0.94 pit. The
  "fuller" triple variant is a RESOLVED HARM, not a null (CI95 excludes zero), so it must not
  return as the richer spec. Coverage was NOT the limiter (80 percent of eval rows are
  non-censored). The second arm's stated premise does not reproduce at all.
- **B3 LEVEL BLEND: NO-SHIP, all three arms.** 17 of 18 cells negative; the anchor arm is the
  worst and on pitchers exceeds MDE95 on all three cuts, a measured LOSS. Harness trustworthy:
  the flags-off rebuild is byte-identical to the shipped matrices. **The underlying defect stays
  open**: 22 percent of multi-level hitter rows and 19 percent of pitcher rows are scored on a
  level that is not their most-exposed one. Blending as specified is not the repair.
- **C3-ETA: NO-SHIP.** Loses BOTH legs of the criterion the incumbent shipped on, same 3,450
  rows: MAE 1.441 to 1.488, within-1y 0.579 to 0.562. Closes a gate owed since 07-30.

**The pitcher lambda discrepancy is closed, and the answer is that the number is noise.** The
served value is 0.57; the 0.59 and 0.54 were each true at their own matrix vintage. Pooled rho
across the entire selection band spans 0.16x the pitcher MDE and 0.21x the hitter MDE, and all
the movement the selector argmaxes over lives in a Spearman on 60 rows. Recorded so it stops
being re-derived and re-quoted.

## Lane F: the team-wins guard is close to green for the wrong reason (a60678e)

- **Cohort intercepts lose a third consecutive time** (7.27 vs 7.21). F-DEF did not
  rehabilitate the refit.
- **The 3.02 remainder decomposes exactly, and 77 percent of it is a stale constant.** Dropping
  the served 06-12 intercept vector takes it to 0.70, which is the genuine roster and depth gap.
  That vector is MAE-NEUTRAL today (7.18 vs 7.21), so removing it trades a level convention
  against nothing measured. **OWNER CALL, not a gate outcome.**
- **Shape improved while LEVEL got worse, on identical rows.** Player MAE 0.593 to 0.541, better
  in 8 of 8 cohorts. But the engine under-projects real 2025 rosters by **88.1 WAR** where the
  06-12 engine was within 8.3. Recentering forces 2,430, so no recentered MAE can see it; raw
  holdout MAE moved 7.73 to 8.31. Attribution: against the 07-31 post-E3 figure of 8.56, F-DEF
  IMPROVED the un-recentered level, and the bulk of the drop is E3.
- **`roster_war_sum` crossing 900 is NOT evidence the per-player regression was repaired.** The
  served roll-up is propped by body count (1,324 vet slots plus 311 depth) while the per-player
  deficit widened.
- **The harness's pooled bias understates by 1.75x**: 4,019 of 8,866 scored rows are players
  with no roster spot whose actual WAR is 0 by construction. Assigned-only bias is +0.086.
- **Gate 1 regen reproduces commit 4853e68's message to 5 decimals**, so the commit was telling
  the truth and only the file was stale. F-DEF recovered +186.5 WAR of level, all hitter-side.
  Note `fa_market` reads this artifact at SERVE time for bands, so the served bands move.
- **Market challenger NO-SHIP**: loses all three criteria, and under-prices the top of the
  market by an additional 805M dollars across 50 megadeals.
- **My Gate 3 premise was REFUTED.** I asserted the artifact predated the shipped weights; it did
  not, and the accuracy half comes back byte-identical. Concentration moved from the DATA regen
  (0.5219 to 0.5833), and the old Giants-tops-pitchers pattern was a roster-vintage artifact
  that today's regen erased, replacing it with more Dodgers. No need and behaviour split tested
  passes.

## Wave 2: prospx (commit 0188c82)

`_gradePrimary()` returned "xfv" for every `state.sort` value that was not literally "fv", but
that field carries about 25 ordering choices, so switching to Consensus and then sorting by age,
or opening a shared `sort=eta` link, silently flipped every grade, rank, surplus and GFX badge
back to eFV. `state.gradePrimary` now holds the choice, shaped like the existing
`state.debutGrade` precedent; legacy `#sort=fv` links still land on the consensus lead. All 13
consumers were re-checked individually.

Overview went from fifteen stacked sections to nine anchored ones with a jump strip, nothing
deleted. The jump chips call `preventDefault`, which matters: a bare `href="#ov-x"` rewrites
`location.hash`, and the global `hashchange` listener re-runs `syncFromURL()` plus `render()`,
ejecting the reader mid-scroll. The detail sidebar was `display:none` below 1300px, so its Key
Signals card was unreachable on every tablet and phone; it now stacks under the tab content
reusing the SAME DOM node, so double-rendering is structurally impossible.


---

# PART 2 (same day): the repair plan, docs/master-plan-2026-08-04-repairs-ewar2.md

Executed against a RUNNING PIPELINE. `python run_monthly.py` was live 13:16-14:21, so
every lane was resequenced source-first and no artifact was written until it exited.
Suite at close: **3,044 passed / 4 failed / 21 skipped / 1 xfailed** (opened at 3,001 / 1).

## The one deliberate red is GONE

Re-running proj_backtest with persist flipped `challenger_wins` to false, so
`_cohort_intercepts()` returns `{}` and the 2026-06-12 vector no longer serves. The league
remainder fell **3.02 -> 0.69** wins per team and `test_recenter_remainder_near_zero` passes
for the first time since 2026-07-30. Verified it passes on a REAL value (0.69 present in
`league_sum_accounting`), not a missing one.

**My own justification for that was wrong, and the new instrument caught it.** The plan said
the vector was "MAE-neutral". The arm that scores the vector proj_export ACTUALLY SERVES,
which the challenger-vs-incumbent gate never did, returns 2025 holdout MAE **7.18 against
7.21** for plain recentering, i.e. on the holdout it was the BEST of four arms. Across all
four targets it is 2 wins and 2 losses, every gap inside noise on 30 teams. The drop still
stands, but because it costs nothing resolvable and buys back 2.3 wins/team of accounting,
not because it was free. Quoting the holdout alone would have argued the other way.

Now measured every run instead of in a scratch script: the assigned-roster level deficit is
**persistent, not a 2025 artifact** (-131.6, -83.7, -114.9, -88.1 across 2022-25 against a
stable ~920 actual), and pooled bias dilutes 1.75x because the 3,837 unassigned rows carry
bias -0.0 and r 0.0 BY CONSTRUCTION.

## eWAR v2: the fielding swap is REMOVED, on measurement

A blend axis was built to rescue it. Grid over 2016-2025, 300 team-seasons:

| w | wins r | wins mae0 | next-yr r | prevention abs r |
|---|---|---|---|---|
| 0.00 | 0.8595 | 4.306 | **0.2524** | **0.3780** |
| 0.50 | 0.8667 | 4.251 | 0.2452 | 0.3718 |
| 1.00 | 0.8686 | 4.347 | 0.2359 | 0.3559 |
| bWAR | 0.8803 | 3.787 | 0.2481 | 0.4290 |

**Both forward legs are monotone decreasing in w**, across five points and two independent
gates, so there is no weight at which the Statcast read pays for itself. At w=0 eWAR BEATS
bWAR on the forward leg (0.2524 vs 0.2481) while losing same-season fit: exactly the trade
the FIP pitching swap exists to make, and now the whole of eWAR v2.

- NEW GATE 1b (team runs) needed no fetch: the cached standings already carried
  runsScored/runsAllowed and `standings()` was discarding them. Its OFFENCE ARM IS AN EXACT
  NULL CONTROL (r 0.3132 both series), which is what licenses trusting the prevention
  comparison.
- Endpoints verified on real rows: w=1.0 reproduces v1 to 0.0, w=0.0 reproduces bWAR's
  rfield to 0.0 over 6,640 batter-seasons.
- **CATCHER FRAMING: probed and REFUSED.** Savant responds and rv_tot is genuinely framing
  runs (per-zone integers sum to it), but the season parameter is INERT: every spelling
  returns one identical undated payload, md5 b389177d5e. Ingesting it would assign one
  snapshot to ten seasons.
- A trap caught in the rebuild: with the default now w=0, the `fielding_swap_only`
  attribution arm was being built AT THE DEFAULT and came back as bWAR under a label
  promising the opposite. It now asks at w=1.0 explicitly.

## Two standing gates were grading something other than their own rule

**SIDE FAIRNESS.** S1 declares the top-25 mean AND median co-primary; the coded B4 check read
the MEAN ONLY and stamped `median_ci90` without ever testing it. On the shipped lambdas the
mean CI90 excludes zero and **the median CI90 [-0.64, 6.53] does not**. B4 now tests both.
Critically a control at the OLD lambdas on the SAME rows also fails the median leg, so this
is 11 days of matrix drift, NOT the pitcher pin.

**GATE 3.** Four rounds of re-weighting had failed on the assumption that NEED was saturated.
Wrong: need is the healthiest component (3.9% club effect, supplying 75.6% of the composite's
interaction). **BEHAVIOR is saturated** - LAD is its #1 for 228 of 228 with zero ties. One
level deeper: `behavior = 0.5*reach + 0.3*recent + 0.2*rich` and ONLY reach takes a player
input; `recent` divides by the league-max 3-winter outlay, which IS LAD, so they score 1.0 BY
CONSTRUCTION. Those constants hand LAD a 0.500 floor against a league median of 0.077 before
the free agent is consulted. **You cannot re-weight your way to a constant**, which is why
four rounds failed. All three candidates NO-SHIP; a 386-vector passing set exists and the
best was declined for zero slack and for zeroing the components that encode known failures.

## GFX rendered in a browser, and a defect only a picture could show

24/24 list cases pass: exact 2x dimensions, non-blank, and ZERO headshot URLs or
background-images in every list board, while the hero and compare cards keep theirs.

Looking at the export showed a top-25 board filling only 83.6% of its canvas. The cause was
an inherited constant: MAX_ROW_H was 44 because a row used to be "44px beside a 22px
headshot", and the headshot left today. Swept the cap across the whole matrix rather than
fixing the case in front of me: **52 improves every case and regresses none** (wide/25
83.6 -> 95.1, portrait/25 94.8 -> 98.5); 56 fills wide better but collapses portrait to 67%.

## The 4 remaining reds, each attributed

None are caused by source changes in this session; all are surfaced by the nightly regen.

1. **efv_sign_declarations[hit]** - hitter `age` fits +0.042 against a declared -1 on the
   rebuilt matrix. Same class as the pitcher `age_rel_level` case resolved 07-30, whose
   sanctioned remedy is a drop-gate adjudication and then moving the DECLARATION, not the
   feature. Owed: that gate.
2. **identity_collisions (2)** - jack_natili, jose_rodriguez and three more. Verified NOT
   from this session's id seeding: jack_natili is absent from player_photos because the new
   symmetric guard REFUSED to bind it, and the pipeline started before that code was
   committed. Owed: split the NEWCOMER onto a discriminated key, never re-key the incumbent.
   `tools/identity_age_sweep.py` (new) generalises the detection and finds 15 impossible
   bindings, 13 of them invisible to the trade-board inactive rule.
3. **eta_bases_match_km** - the pipeline refit KM at 14:08 (A+ 3.25) while `eta.BASE_YEARS`
   stays 3.0. The constants owe an update through the eta backtest gate.

## Other work landed

Pre-arb pricing for the 167 published no_contract vets on the registered league-minimum
basis, with a no-inversion invariant. `roster_status.mlb_seasons` backfilled from career_war
(the empty field on 782 of 2,681 rows is what let a fused identity reach the board).
/fantasy/ hash router. projections.js inline styles 58 -> 19, every survivor computed. The
Methodology page stopped describing a grade the site retired in July. `composite_at_shipped`
now records the shipped lambda instead of the selector's. Pitcher lambda pinned at 0.57.
