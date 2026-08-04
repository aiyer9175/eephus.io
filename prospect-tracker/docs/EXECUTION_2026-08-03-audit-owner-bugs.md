# Execution record 2026-08-03: audit lane A + two owner bug reports

Eight commits on `main` (`36beaa2` .. `947e58a`). Suite **2,889 passed / 2
failed**, both the documented pre-existing reds. Baseline at session start was
2,853 / 3. Nothing was pushed; beta untouched.

## What the box owes

1. `run_monthly.py` -> `python efv_export.py` -> `run_monthly.py --rebuild-only`
   (still owed from `docs/RUNBOOK_2026-08-03.md`; nothing here supersedes it).
2. **A resolution + stats pass** for the 2026 draft class. The id fix is code
   only. Until `bulk_resolve_ids` runs on the box, the ids are not in the cache
   there and no stat line reaches the board.
3. `data/xfv_reliability.json` regenerates with a new shape (`after` + `before`
   curve sets). The glossary card reads the old shape safely in the meantime.
4. **A `positional_fit` regen.** The served artifact is from 2026-07-24 and
   predates the `ladder.identification` block by a week, so /pal/ cannot yet
   explain which sum is zero. It degrades to the plain table until then.

No data artifacts were committed: the box is the single writer and a locally
regenerated copy is degraded by definition. Locally rebuilt `xfv.json`,
`MODEL_REGISTRY.md`, the FA class files and the rest were restored after each
verification pass.

---

## Owner bug 1: "why are Vahn Lackey / Roch Cholowsky missing stats"

It is not two players. **All 199 active 2026 draftees** were in the same state.

**Measured on the served board:** of 4,550 active players, all 4,296 carrying
an `mlbam_id` had stats and all 254 without one had none. The id is a perfect
discriminator, because it is the only key the MiLB stat fetch joins on.

**Root cause.** `resolve_mlbam_id` cached a failed lookup as null and
documented it as "suppress retries on future runs", with hand-deleting
`.cache/mlbam_ids.json` as the only escape. Correct for a wrong-identity
binding; wrong for a player who does not exist in StatsAPI *yet*. The class was
resolved once at draft ingest, before anyone had signed or been assigned, so
every lookup missed and every miss was cached permanently. They then signed,
were assigned, and started playing, and nothing ever asked again.

Proved rather than inferred: through the production entry point all three test
players returned `None`, but bypassing the cache, `PlayerIndex` resolves them
today (Cholowsky 800604, Lackey 822518, Emerson 815690). They were always
findable; only the cache said otherwise.

**Fix.** A hit stays permanent (ids never change); a miss now expires after 3
days, stamped in a sidecar so the id cache keeps its `{key: int|None}` on-disk
contract for every other reader. Misses with no stamp - everything cached
before this change - read as expired, so the poisoned entries heal on the next
pass with no manual cache wipe.

**The correction that mattered.** The first commit patched `resolve_mlbam_id`,
which `run_monthly` never calls: the pipeline resolves ids *only* through
`bulk_resolve_ids` (the per-player loop was removed for performance,
`run_monthly.py:3201`), and that function still had a bare `else: continue` on
a cached null. The fix was dead code exactly where it was needed. The bulk path
now honours the same TTL, stamps the nulls it writes (batched - it walks
thousands of keys), and clears stamps for anything that resolves.

**Heals**, dry run over the affected cohort: **227 of 254** statless players
resolve immediately, including **190 of the 199** 2026 draftees.

**Set expectations honestly.** Verified against StatsAPI directly:

| player | 2026 minor-league line | after the fix |
|---|---|---|
| Vahn Lackey | 4 G, .286/.500/.286, Fort Myers (A) | appears |
| Roch Cholowsky | none - rostered ACL White Sox, no game logged | still nothing to show |
| Grady Emerson | none - rostered FCL Rays, no game logged | still nothing to show |

Cholowsky is the headline name in the report and the site is currently
**correct** for him: MLB has recorded no games. He populates automatically once
he plays. The premise that both were "actively recording stats" holds for
Lackey only.

**Not fixed, worth doing.** Three ids already in the system never reach the
stats cache: `draft_players.mlbam_id` (populated for 136 of 565 signed 2026
draftees straight from the draft API), the `mlbam_id` inside tjstats snapshot
`_extras`, and `player_photos`. Seeding the known id at
`draft_promotion.seed_signed_draftees` would mean a signed draftee never
depends on name-search resolution at all.

---

## Owner bug 2: Top-100 Generate GFX

Two rounds, because the first report was a defect and the second was a change
of direction.

**Round 1 - blank fields.** The chip grid called `_gfxChipHtml(it, ...)` on the
raw snapshot item; the row layout it replaced calls
`_gfxRow(item, snap.kind, snap.meta)` first. Raw prospect objects carry
`player_name` / `fv_close` / `mlbam_id`, the renderer reads `name` / `fv` /
`mlbam`, so every lookup missed: no name, no badge, no headshot, no meta line.
`org` was the one key present on both shapes, which is why it still drew team
logos in a tidy grid and looked almost right. Nothing threw, because
`escapeHtml` returns `""` for null and the badge is null-guarded.

Every existing chip test greps the *renderer's* source for the fields it reads.
None could see that the *caller* passed a different object. That is how it
shipped green. Added a caller/callee contract test and verified it fires by
reverting the one-line fix.

**Round 2 - the owner redirect.** "Not a photo grid": a small headshot beside
the text, all 100 on one 16:9 canvas, in rows, filling the space, nothing
bleeding or cut off. The existing "Rows (compact)" dropdown option fell through
to the legacy 67px row renderer that spends a column on surplus and $DvM+ and
fits ~26 rows, so choosing it did not produce what the label promised.

New compact list layout, now default with the wide canvas. Measured by running
the shipped functions under node:

```
wide 1600x900, n=100 -> 4 cols x 25 rows, 100 cells, 0 empty,
371x28px rows, 22px headshot, 97.2% of the vertical space used
```

Each row carries rank, small headshot, name, eFV badge, club mark, plus
position/age/level inline (the row is short but wide, so the available space is
horizontal). Rank, photo, badge and logo are all `flex:none`; the name block is
the only element that absorbs slack, with `min-width:0` and its own ellipsis,
so a long meta gives way before the name and neither can push the badge out.
Row height and column width are capped so a 25-player list leaves margin rather
than stretching to 80px rows beside a 22px photo.

Chips remain selectable, and the chip geometry was fixed on the way past: the
`round(sqrt(cap * w/h))` heuristic returned 9 columns for 100 chips (9x12 = 108
cells, eight blanks in the last row) while the module's own comment specified
ten. The column count is now searched: **10x10, 0 empty, +19% photo**, and the
photo well is bounded on both sides so it stops being a 0.59 letterbox.

---

## Lane A: model / metric calibration

### A1.1 The live calibration monitor was grading the wrong distribution

`efv_reliability` reproduces `efv_score`'s path up to the grade inversion and
then read the raw `p_bucket_given_fv` curve. The scorer applies the
odds-dispersion Platt map at all three seams (wired 07-31); this module never
did. The public "model grading itself" card therefore published a pre-fix
miscalibration the site had already corrected, and called it "within the
documented standing miscalibration band" - a reassuring sentence about the
wrong number.

Measured on the current tree (forward-chained OOF, pooled n=2,825). The map
improves **every** bucket, which is also the first confirmation of it on this
frame:

| bucket | served | pre-map |
|---|---|---|
| bust | 0.07540 | 0.12809 |
| bench | 0.01603 | 0.02714 |
| regular | 0.03298 | 0.04917 |
| good | 0.02328 | 0.04048 |
| star | 0.00677 | 0.00939 |

The artifact now carries both curve sets; the tripwire judges the served one.
Threshold re-derived **0.14 -> 0.10**: the old value sat 1.9x above the number
it watched and could not fire. 0.10 leaves ~33% headroom over the served
baseline *and* sits below the 0.1281 pre-map level, so if the Platt map is ever
dropped from the scoring seams the curve reverts and the wire trips. The
tripwire now regression-tests the calibration it reports on.

The glossary card prefers `after`, falls back to `before` (the deployed
artifact predates this change and would otherwise render empty), and says which
basis it is showing. Closing copy no longer calls the miscalibration standing;
it states what is still true - bust lands above the diagonal in every bin, so
bust risk remains understated, by materially less than the uncorrected curve.

### A1.2 / A1.3 The Platt slope is not drifting

The module claimed per-fold slopes of 0.470 / 0.392 / 0.289 / 0.276
"monotonically DOWNWARD", concluding the shipped constants were the
conservative end of a drifting range. A monotone trend in a fixed constant is a
re-fit trigger, so it was measured rather than trusted:

| through | hit n | hit slope | pit n | pit slope |
|---|---|---|---|---|
| 2017 | 44 | 0.6526 | 39 | 0.4163 |
| 2018 | 81 | 0.2627 | 85 | 0.3139 |
| 2019 | 163 | 0.2910 | 164 | 0.2598 |
| 2020 | 244 | 0.3750 | 272 | 0.3602 |

**Neither side is monotone.** Both dip through the small-n middle and come
back, and the full-frame fit reproduces the shipped constants (hit 0.3750 vs
0.3749; pit 0.3602 vs 0.3553). These are converged values, not a conservative
bound on a drift. **No re-fit.** A re-fit was tested end to end anyway and does
not clear the pre-registered gate: the per-fold refit beats the incumbent on
Brier and log loss with the CI excluding zero but cannot beat a flat base-rate
constant, which the gate requires. That artifact reproduced to within noise of
its committed 07-30 values on this tree (d_inc_brier 0.0272 vs 0.0277,
identical n=1,925 frame), independently confirming the resolved frame has not
moved under the seam fix.

### A3.3 The freshness map could not report a stale eval

Three defects, all of which made it report health it had not checked:

* `STALE_DAYS = 240` against an oldest artifact of 54 days - 4.5x above
  anything it watched, so "nothing is stale" was a tautology. Now 90, with a
  test pinning it between today's oldest artifact and 3x that.
* Age came from **file mtime**, which `git checkout` and a fresh clone rewrite
  to the moment of checkout - so on the deploy box, the one place staleness
  matters, the whole registry read as brand new. Age now prefers the artifact's
  own `generated_at`, which **137 of 168** rows carry.
* Handling those stamps surfaced a third bug: they are mixed formats, and UTC
  ones (`2026-08-03T23:17:20Z`) parsed as local put the date hours in the
  future, giving `source_track_record` an age of **minus one day**.

Also closed a hole in `validate()`: non-JSON artifacts skipped the parse check
entirely, so an emptied file validated clean (`efv_il_severity` points at a
`.md`, the only such row).

### Phase 0 The cache guard could not see the thing it guarded

The three hand-authored pages hand-bumped a shared `?v=` date stamp that
nothing forced anyone to bump. site.css changed on 07-31 and all three still
advertised `?v=20260730` (pitcher_index `?v=20260709`), so the 7-day max-age on
`/assets/` served up to a week of stale CSS to exactly the pages that hand-edit
it - and any display or mobile fix would have been invisible there.
`test_asset_versioning` asserted only that a `?v=` *existed*, which a date
stamp satisfies forever, so it stayed green throughout.

`build_site` now stamps those pages from the same content hash the generated
pages use, and the new freshness test asserts the stamp equals current content.
Verified it fires by re-injecting `?v=20260730`.

### Lane C foundation (partial)

* `.mlb-card` named `var(--panel-bg, var(--card-bg, transparent))` and neither
  token has ever been defined, so the Projections and Free Agency boards were
  the only unpanelled lists on the site. Now `--bg-secondary`, the token the
  identical fantasy card already used.
* The FA verdict pills carried baked **light-palette** rgba literals that
  cannot flip with the theme, so VALUE and OVERPAY wore a light tint against
  the Topps-Chrome field. Now `color-mix` on the live token.

---

---

## Lane C: sticky that never stuck

Both defects had the same cause and neither was visible from the stylesheet
alone: an `overflow-x:auto` ancestor computes overflow-y to auto as well, which
makes it the sticky containing block, and its height is its content, so there
is no scrollport for `top` to resolve against. Measured in Chromium before and
after.

* **mlbstats header.** `.mlbstats-table th` has declared `position:sticky;
  top:0` all along. Before: scroll 400px, header moves 400px. After: moves 0.
  Bounding `.mlbstats-scroll` makes it a real scrollport, scoped with `:has()`
  to containers that hold a leaderboard and gated to >=1025px, because a nested
  scroll region reads as a data table on a wide screen and a trap on a phone.
* **Frozen name column.** Those boards carry 23-24 nowrap columns and run wider
  than the wrap at every desktop width, so scrolling right orphaned every
  number from its player. First cell is now left-sticky, which needs no height
  bound, so it applies on phones too. Verified both axes hold at once: name at
  left 0 through a 600px horizontal scroll while the header holds top 0 through
  a 300px vertical one.
* **FA rail.** `#fa-rows { overflow-x:auto }` was a blanket that also trapped
  `.fa-board-rail`. The identical rail on /projections/ always worked purely
  because `#proj-rows` carries no overflow. After: the FA rail pins at 8px and
  holds through 3,000px of scroll.

**Worth recording as method.** My first probe called the FA rail broken, then
called it fixed, for the wrong reason both times: it scrolled 500px at a rail
that starts 545px down, so the rail never engaged. The honest test is whether
it pins near its offset at deep scroll, and the honest control was restoring
the old blanket to confirm causation - `pinned=False` with it, `pinned=True`
without.

## Lane B: mobile

Measured at 390px with touch emulation across ten surfaces.

**Document bleed was already zero everywhere**, including `/glossary/`, which
the recon predicted would pan sideways because its `table-scroll-x` wrapper
class is only defined in prospx. It does not, at that width. Predicted defects
still have to be measured.

**Touch targets.** PROSPX got a 44px pass long ago; the seven `.fa-app`
surfaces never did, and their primary filter control was not merely small but
SMALLER on a phone - `.fa-app button.chip` drops to 3px/11px at <=720px, which
measures 19px. Counted under 44px, before -> after: `/fa/` 50 -> 15,
`/glossary/` 18 -> 2, `/news/` 22 -> 1, `/mlbstats/` 40 -> 26,
`/collegesavant/` 6 -> 1, `/pal/` 18 -> 10.

Per-row affordances sit in fixed-height cards, so growing the box would
relayout the board. They get a transparent inset overlay instead, verified by
hit-testing outside the visual box: projections compare 16px -> 38px effective,
prospx compare-add 24 -> 46, row expand 28 -> 50, all three now take the tap.
The residual counts are dominated by those same buttons plus 28 trademachine
`span.chip` labels the probe flags but which have no handler. Honest exception:
`.fa-sort` did not gain its overlay, because the sort strip sits directly under
the filter bar which paints over it; left at 23px rather than fight the
stacking order.

**iOS input zoom: closed.** Every text field on the site was under the 16px
threshold at which iOS zooms the viewport on focus - 11px on the projections
scatter axes, 12px on the mlbstats bar, 13px on four searches, 15px on the
command palette. Only prospx's GFX modal ever got it right. Now zero fields
under 16px on all ten surfaces. Three resisted the first fix for three
different reasons: a bare element selector losing on specificity; INLINE
font-size on `#tb-search` and the scatter axes, which no stylesheet can
outrank, so those moved into CSS; and `#trade-machine .tm-search`, an ID
selector in a stylesheet that loads after site.css, fixed in its own file
rather than with `!important`.

**Also:** the swipe-strip pattern now covers the module filter bars, the
mlbstats tab and season tiers, and the card sortbar (without it, 25 FA chips at
44px wrap into six rows); `#tb-group-panel`, a sibling of `#tradeboard-content`,
never inherited its overflow rule; and CollegeSavant, whose stylesheet stopped
at 720px, got a phone tier for the first time.

The sortbar strip needed a second pass: the rule was added to the shared swipe
block, but `.mlb-sortbar { flex-wrap: wrap }` is defined ~290 lines later at
equal specificity and simply won. Overrides belong next to the rule they beat.

## Lane C, part 2: the unification pass

* **One table dialect.** `.mlbstats-table` and `.fa-app .detail-table`
  disagreed on font-size, cell padding, header background, header colour and
  header face. `.proj-app` already overrode its header to `--bg-secondary`,
  which made `.fa-app` the odd one out of three rather than the standard, so FA
  moved onto the other two. Verified by computed style: the FA header now
  resolves to `rgb(250,245,230)` / `rgb(112,107,92)` / MS Gothic, matching
  mlbstats. Cell density unified at `6px 10px` / 12.5px. Numeric alignment was
  deliberately NOT unified - right-aligned is correct for a stat table and
  centred is correct for the comparison tables.
* **One active state.** `.mlbstats-season.active` was the only solid-fill
  active control on the site, a gold block with inverted text sitting two rows
  below two tiers that both mark active with a gold underline. Now the house
  device (outline, gold border, iridescent rule). Its `border-radius: 999px`
  is gone too: the global reset always flattened it, so it only implied a
  lozenge the site never had.
* **One null marker.** mlbstats rendered an absent value as an EMPTY CELL where
  the other two render the site marker - on the one surface where whole columns
  are legitimately absent for unqualified players, a missing number and a
  rendering bug looked identical. Note the constant is called `EM_DASH` in
  fa.js but is a spaced hyphen, because real em-dashes are banned in copy and
  `strip_emdashes` lints `assets/*.js`.
* **Nav, 641-1024px.** The hamburger only takes over at <=640, so between those
  widths the link strip is a silent swipe with `scrollbar-width: none` while 10
  links at 12.5px need about 900px. A thin scrollbar now appears in that band -
  deliberately a scrollbar and not a fade mask, because the strip is
  right-aligned by `margin-left:auto`, so a mask would dim the last link
  whenever the links DO fit.

---

## Owner bug 3: the positional ladder's zero

Reported as the Fitted (runs/650) column not summing to zero, "which it should
by definition", plus surprise that 2B outranks CF.

**The zero is a WEIGHTED one.** The adjustment is centred on an
exposure-weighted sum, imposed exactly by `positional_fit._recentre`. Verified
as an invariant rather than trusted: `_recentre` subtracts a scalar from every
rung, which only zeroes the weighted sum if the weights sum to 1, and they do
because `_ladder_design` normalises each row of innings by that row's total.
The new test builds a design under that convention and asserts the weighted
sum lands at zero to 1e-9, and that recentring shifts the level without
changing the shape.

Adding the nine displayed rungs with equal weight gives **-4.27**, which is
not an error: DH is about 7% of league exposure rather than a ninth, so equal
weighting counts the large negative DH rung nine times too heavily. With the
weighted sum pinned at zero the eight fielding rungs are then forced to
**+9.49**. Only the weighted sum is a constraint; the other two follow from it.

**Why it looked wrong.** `positional_fit` has published all three sums in
`ladder.identification` since 2026-07-31, and the page could show none of it
for two independent reasons: `build_positional_fit_payload` did not forward the
block, and the SERVED artifact was generated **2026-07-24**, a week before the
block existed, so the source data could not answer the question either. A
correct number with no way to check it is indistinguishable from a wrong one.
The payload now forwards it and /pal/ explains it, rendering only when the
artifact carries the block. **The box owes a `positional_fit` regen.**

**2B above CF is real, and it is a statement about Baseball-Reference.** The
fit is an INVERSION: it recovers the constants BRef themselves used, so a rung
reads as what BRef prices a position at, not as an independent measure of how
hard it is to play. The gap is stable across four independently recentred era
splits spanning 26 seasons:

| era | 2B | CF | 2B - CF |
|---|---|---|---|
| 2000-2005 | +4.61 | +3.49 | +1.12 |
| 2006-2011 | +4.47 | +3.47 | +1.00 |
| 2012-2017 | +4.42 | +3.47 | +0.95 |
| 2018-2026 | +5.02 | +4.01 | +1.01 |
| full | +4.65 | +3.63 | +1.02 |

The 95% CIs do not overlap. The folklore table prices the two positions
identically (+2.5 each), which is exactly the kind of gap the difference column
exists to show. The ladder note now states the inversion framing explicitly.

## Open, deliberately not done

Nothing outstanding from the plan's Lane B or Lane C. Still carried forward:
the three number-formatting *implementations* remain three (only the null
convention was unified; `projections.js` still reimplements `money()`/`fmtWar()`
locally rather than importing fa.js's `formatMetric`), and `projections.js`
still carries 93 inline `style=` attributes that are invisible to the theme
system.

## Gotcha worth keeping

**Never edit source while the suite runs.** `conftest.py`'s
`_restore_committed_build_artifacts` snapshots dirty files at session start and
`git checkout`s anything that became dirty by session end. Edits made during a
run look exactly like test pollution: it silently reverted `build_site.py`,
`test_asset_versioning.py` and three restamped HTML files mid-session. The
guard is behaving exactly as documented; the workflow was wrong.
