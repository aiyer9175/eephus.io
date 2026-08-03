# Master plan 2026-08-01: Top-100 Generate-GFX redesign + rest-of-season control pricing (Minter)

**Executor**: written for Claude Opus 5 to implement end-to-end, including the bugs and logical inconsistencies catalogued below. Every root cause in this plan was measured against `main@ab56f7b` on 2026-08-01 and adversarially verified; the four verified investigation briefs live in `docs/plan-2026-08-01-inputs/` (G1 render map, G2 space arithmetic, M1 Minter trace, M2 pricing design). Cite them before re-deriving anything. Where this plan says MEASURED, the number came from the artifact or code, not an estimate.

**The two owner asks**:
1. Top-100 prospects Generate-GFX: remove the surplus/$DvM+ column, spend the space on bigger, legible chips. MUST keep: player photo, eFV grade, ranking. PREFER: level/age/position. Header/footer compressed. Landscape allowed. No text overlap/cramping anywhere.
2. A.J. Minter shows as not tradeable with no trade value. He has ~0.5y of control left (through 2026); calculate surplus on that remaining control.

---

## Ground rules (house, binding)

- Owner display rules: consensus FV/tool grades display CEILING; eFV and "+" stats round to nearest. The GFX already does this correctly (`prospx/index.html:32257-32260` eFV round-nearest, `:12691-12696` fvCeil) - preserve it.
- User-facing copy must pass `python strip_emdashes.py --check` and `copy_lint`; no em-dashes in any UI string you add.
- Pre-register any gate before fitting/measuring; a NO-SHIP is recorded as "deprecated"/loss ledger, never an invented verdict. This plan contains no fitted-model work; if you find yourself fitting something, stop and re-read the scope.
- `value_framework.py` is NOT to be edited in this plan (the RoS leg lives in `proj_export.py`). If you do end up touching it, its edits require `--emit-snapshots`.
- Semantic changes to `mlb_projections.json` need TWO export passes before `trade_values.json` agrees (MEASURED: `rebuild_only` never runs proj_export; the trade export inside d9 reads the PRIOR night's `mlb_projections.json`; the d9b re-bake lands after - M2 brief, one-cycle skew). Run the export chain twice and verify convergence.
- Do not touch the `beta` branch or any sync tooling: the webmaster is mid-repair on a deliberate rollback (see `docs/beta-recovery-record-2026-08-01.md`). All work lands on `main` only.
- Commit discipline: one logical change per commit, suite green before each, descriptive bodies (they are this repo's institutional memory).

## Phase 0 - unblock the data plane (do this first; both lanes depend on it)

**0a. Fix the run_backgrade P0.** `efv_score.py:2066` in `run_backgrade` reads `r.get("milb")` where `r` is unbound (loop vars are `rec`/`row`; the only non-comprehension `r`; confirmed by AST scan - M2 brief). Introduced by `3ada6a0` (07-31). Every regen since crashes the eFV tail silently (`run_monthly.py:742-747` swallows it), leaving `data/xfv.json`, backgrade, history, tools, and the valuation curve stale. Fix: `r.get("milb")` -> `row.get("milb")`. Add a regression test that imports and runs `run_backgrade` over one synthetic row with a `milb` block (nothing exercises this seam today - that is HOW a one-line NameError shipped).

**0b. Fix the resolved-seam Platt no-op (spec compliance).** `efv_score.py:1292` passes `provisional=not (r.get("milb") or {})` computed from the `_prep` row, which never carries a `milb` key, so `recalibrate_bucket` is a no-op for the entire resolved cohort. The registered spec is `provisional=not src.get("milb")` (`tools/_prem_odds.patch:30-31`). Fix to read the source row. Before/after: diff the p_bust distribution on the resolved cohort and record the shift in the commit body (this is a spec-compliance fix of the 07-31 Platt ship, not a new model decision; live and backgrade seams already work).

**0c. Full regen, in the correct order.** The nightly monthly does NOT run `efv_export` (leaves `xfv.json` stale): run the pipeline, then `efv_export`, then a second `--rebuild-only` pass. Verify: `xfv.json`, `xfv_backgrade.json`, `mlb_projections.json`, `trade_values.json` mtimes all advance and the calibration vintage stamp agrees across all four priced artifacts (`test_calibration_vintage.py`).

## Phase 1 - Top-100 Generate-GFX redesign

### What exists (MEASURED - G1/G2 briefs; all line refs `prospx/index.html`)

The Top-100 board GFX is the PROSPX in-page DOM+html2canvas engine - it does NOT use `assets/eephus-gfx.js` (disjoint systems; prospx never loads it). Pipeline: `_gfxSet` (:33250) -> `openGfxModal` (:35031, list default format "wide" :35043) -> `buildGfxBoard` (:34817) -> detached div -> `exportElementAsImage` (:33118, scale 2, useCORS) -> PNG.

Current "wide" Top-100: 1600px wide, **~1929px tall** (the "16:9" label is false - min-height only, no fit-down), 4 cols x 25 rows of **359x67px chips**, exported ~3200x3858. Chip anatomy: 30px rank + 40px grade badge + **40x52 avatar (8.6% of the chip)** + ellipsized name/meta (~148px, ~19 chars) + ~45px value column (surplus $ over "$DvM+ nnn" at **10px - the legibility floor**). Header band 93px with its own inlined branding + QR; footer 41px. On a 600px-wide social timeline the 15px names render at ~5.6px: the owner's complaint is real and measured.

### The redesign (execute this spec)

**Format**: make the Top-100 default a true-portrait **1600x2000 canvas, 10x10 grid** (exports 3200x4000, 4:5 - the share-friendly ratio). Chip cell: **141x164px** (with 12px gaps and slim chrome; the parametric formula and full candidate table are in G2 brief section 5 - re-run it if you adjust chrome). Add a **landscape option 1920x1080, 20x5 grid** (81x156 vertical chips) for the owner's landscape preference; keep "wide" for other list kinds. Both formats must use a real fit-to-frame ladder, not min-height (working precedent: `assets/eephus-gfx.js:307-317`).

**Chip layout (portrait cell 141x164)**, top to bottom:
- Headshot **~137x92** (cover-cropped, see defect fix 2), rank badge overlaid top-left (3-digit safe), eFV grade badge overlaid top-right (round-to-nearest, existing `getEfv`/`efvGradeDisplay` chain).
- Name line, 14px, ellipsized (longest board name is 28 chars - MEASURED; never let it collide with badges).
- One meta line, 11px: `POS · LVL · AGE` (e.g. `SS · AA · 19.2`). This keeps all three owner-preferred fields at legible size, so DO keep them. Multi-position strings are up to 8 chars on 5 players (G2) - ellipsize, never wrap.
- **No surplus, no $DvM+, no value column anywhere on the Top-100 board** (the ask). The `$DvM+` producer (`storage.py:10703-10782`) and other consumers are untouched - this is display removal only.

**Header/footer**: replace the 93px inlined band with the shared `_gfxHeader`-style single strip (~40px: wordmark + "Top 100 Prospects" + as-of date inline); footer stays <=41px with the grade-scale legend. This also fixes defect 5 (duplicated branding block). Net chrome target: <=120px vertical total.

**Coverage guards (MEASURED, they will bite)**: `mlbam_id` (headshots) is 94.5% - design the no-photo fallback (initials tile) at full chip size, not a collapse. `age` 94.5%, `statline_level` 94.3%, position ~100% via the display chain. Do NOT source position from `position_observed` (43.1% coverage); use the same field the current meta line uses (`:33566-33571`). `pitch_arsenal`/`sabermetrics` are null on ALL rows - do not reach for them.

**Also fix while in there (all reproduced; G1 defects 1-5, G2 defects 1-8)**:
1. Aspect lie: implement the fit-down ladder for every list format (G2-1/G1: `min-height` only at :34910).
2. Stretched headshots: html2canvas 1.4.1 ignores `object-fit:cover` on `img` (:33702; zero object-fit support in vendor bundle - MEASURED). Swap the avatar to a div with `background-image`/`background-size:cover` (the logo path already got the equivalent fix at :33709-33714), or pre-crop via canvas.
3. Show=All catastrophic export: cap the GFX list render (cap 200 with a visible "GFX renders top N" note); 4,526 rows currently builds a ~152,000px canvas that silently fails.
4. Dead code: `buildGfxBoard`'s unread `w`/`h` return, dead `_GFX_FORMATS[*].label`s, impossible `variant || "detailed"` fallback (:34997), pack-branch `offsetHeight` on a detached div (:34859).
5. Unknown-format fallback mismatch: `buildGfxBoard` falls back portrait (:34826) while `_gfxColumnCount` falls back wide (:34806) - unify to one constant.
6. `_gradePrimary` (:32421) claims eFV-lead for ANY non-fv sort (age sort renders eFV badges/legend/surplus source) - make it resolve the actual sort key.
7. Empty 36px spacer for grade-less rows (:34868-34871) - render the fallback tile instead.
8. Rank box `width:30px` overflows at 4 digits (:34879) - size for the cap you choose in fix 3.
9. Animate (foil-sweep) offered on list boards where it is card-designed (:35050-35051) - gate it off for lists.
10. Top-100 flow: `count` never defaults to 100 (`_gfxOpts.count:50` persists; `openGfxModal` resets title/format but not count) - the "Top 100" entry point must set count=100.
11. Glossary collision: `data/glossary.json` id `dvm_plus` defines the FARM-system "Development vs Mean"; the per-player `$DvM+` (`p.dollar_dvm_plus`, chip title at :9800) has NO entry, and `build_site.py:1777` uses the farm sense. Add a distinct per-player glossary entry (`dollar_dvm_plus`) and point the chip tooltip at it. ($DvM+ leaves the GFX but remains on the site's leaderboard.)
12. Optional, small: GFX as-of reads `DATA.generated_at` (:33779) with no eFV-staleness indicator; after Phase 0 this is moot, but consider stamping xfv vintage in the footer.

**Acceptance (Phase 1)**: generated PNG at 1600x2000x2 shows 100 chips with no clipped/overlapping text at the longest measured name (28ch), a 3-digit rank, an 8-char position string, and a missing headshot, verified by actually generating the image (headless browser or manual) and eyeballing at 100% AND at 600px timeline width; smallest text on the image >=11px logical (up from 10); em-dash/copy lint green; no other GFX mode (mini cards, farm/compare/prospect cards, news/eephus-gfx.js surfaces) visually changed - `_gfxRow`/`rowHtml`/avatar helpers are shared by ALL list kinds (G1 blast radius), so isolate chip changes behind the list-kind or a new board variant. No test exercises these functions today; add at least a DOM-structure smoke test for buildGfxBoard (100-row fixture: grid dims, no value column, count default).

## Phase 2 - price rest-of-season control (Minter and the expiring class)

### Root cause and the decision being superseded (MEASURED - M1/M2 briefs)

`surNpv` sums seasons `FIRST_SEASON=2027..2031` only (`proj_export.py:59-60, 283-312`). Spotrac DOES store Minter's 2026 salary (`{2026: $7,588,208}`) - `_apply_contract` just never reads the current season (:299-300). So rest-of-2026 control is structurally invisible to the entire pricing stack. `docs/efv-2026-07-31/TRADE_BOARD_COVERAGE.md` then RULED this correct ("a pending free agent is not a trade asset") and `test_trade_board_coverage.py` + `test_proj_export.py:123-131` pin it. **The owner has now overruled that: a deadline rental IS a trade asset.** Amend the doc with a dated supersession note; do not silently contradict it.

The measured mess this must also clean up - one class, three treatments (M1-D2): of 221 expiring vets, **145 are priced on a 6-year eFV backgrade basis** (Gleyber Torres $80.1M with two months of control - indefensible), 72 ship dimmed as "not tradeable" (Minter), 4 fall to raw-bayes. Plus: **840 valued graduated/debuted rows are unreachable in Trade Machine search** (M1-D1, incl. Skubal, Chisholm), 9 valued rows have `surplus_source: null` (M1-D3, worst: Jose Quintana age 38, fv 0.0, tv 95.9, rank #40 - raw-bayes junk at elite rank), the coverage stamp and the unpriced ledger use different denominators (M1-D4: 581 stamped vs 240 shipped, unexplained in-artifact), Minter's FA row says `from: MIN` (M1-D5: Spotrac page error passed through; contract store correctly says Mets), and the dimmed copy "contract ends 2026 - no controlled season to trade" is false at the deadline (M1-D6).

### The design (execute this; deviations need a recorded reason)

**New rest-of-season leg in `proj_export.py`** (NOT `value_framework.py`), computed for EVERY vet with a known 2026 salary and a projection:

```
season_frac_remaining = clamp(regular-season days remaining at run date / total season days, 0, 1)
ros_war    = war[0] * season_frac_remaining          # war[0] = the 2027 projection, the nearest full-season estimate
ros_salary = salary_by_year[2026] * season_frac_remaining
sur_ros    = ros_war * season_value_per_war - ros_salary   # UNDISCOUNTED (t=0: it is money and wins now)
sur_total  = sur_ros + surNpv
```

- `season_value_per_war` = the same tiered kernel the 2027 leg uses (`tiered_war_value_usd * (dpw 15,640,340 / 11.74e6)`, M2-verified) at t=0. Do NOT reuse `value_framework._remaining_path_surplus_usd` (it discounts from NOW while surNpv discounts from 2027 - the dual-convention conflict is real, M2 defect 5; keep the new leg trivially undiscounted and record the convention in a comment).
- `sur_ros`/`sur_total` are **new scalar fields**. Never append a 2026 element to `sur[]`/`war[]` - they are index-aligned to `first_season` in `projections.js` (`warAt` :164-171) and pinned by `test_proj_export.py:145-157` (M2 defect 8).
- **Uniformity decision (recorded here, execute as such)**: the leg applies to ALL vets, not just expiring ones - pricing Minter's 2026 remainder while ignoring Judge's would be a new inconsistency of exactly the class this repo keeps paying to remove. Consequence: every vet's board value shifts up by his 2026 remainder; the trade board and `/projections/` move together (the $0.15M per-player cohesion test keys on `surplus_source=="projection"`, `test_calibration_vintage.py:112-146`, and both read `mlb_projections.json` - land the leg once, in proj_export).
- Board value + routing: trade board consumes `sur_total` via `apply_platform_surplus` (`bayes_trade_value.py:4121-4128`) and the `_append_projection_only_rows` path (:4267-4315). Expiring vets with a 2026 salary now form a projection-basis price, so the existing `projection > xfv_backgrade > raw-bayes` routing (:4190-4235) automatically re-routes the Torres-145 off the 6yr backgrade basis. Add the invariant test: **no MLB vet with zero controlled seasons beyond the current one may carry a backgrade-basis (6yr) price**.
- `_unpriced_vets` classifier (:4322-4362): `expiring` narrows to "contract ends 2026 AND no 2026 salary on file"; expected shipped-unpriced expiring count drops from 72 toward ~0. `no_contract` (pre-arb, 360) stays REGISTERED-NOT-FIXED - it needs the salary-assumption model the coverage doc already scoped; do not smuggle it in here.
- Season fraction: compute from the regular-season calendar (Opening Day / final day constants or the schedule store if one exists - M1/M2 found no existing helper, so write one; missing-data fallback = 1.0 so a broken date zeroes nothing silently... no: fallback 1.0 prices a FULL season. Fallback must be the safe side: if the date math fails, `sur_ros = None` and the vet keeps his current treatment. Log it.)
- Negative results are correct results: Minter's honest number may be near zero or negative (war5 0.6 over five years; ~$2.5M remaining salary vs ~0.1-0.2 RoS WAR). He becomes TRADEABLE with that value - the ask is to calculate it, not to make it positive. The v6 EV frame already removed the $0 floor; do not reintroduce one here.
- Do NOT add QO/comp-pick value in this pass (`fa_market.qo_tax_usd` exists and could price the pick attached to an expiring star); register it as a gated follow-up candidate in the registry instead.

**Also fix (all confirmed)**: D1 (Trade Machine search: `!_tbIsMlb` filter at `trademachine.js:1045` + `proj.surNpv != null` gate at :187 - make them `sur_total`-aware and let valued graduated/debuted rows through; acceptance: Skubal findable); D3 (kill the raw-bayes `surplus_source: null` fallback for MLB vets at `bayes_trade_value.py:4234-4235` - route to projection basis or unpriced-with-reason; acceptance: Quintana no longer rank #40); D4 (one denominator: coverage stamp and unpriced ledger apply the same on-board exclusion, both published, labeled); D5 (contract-store org outranks the fa_avail page org in `fa_export.py:300`; Minter shows NYM); D6 (deadline-aware copy, lint-clean).

**Docs/registry/tests**: supersession note in `TRADE_BOARD_COVERAGE.md`; registry row for the RoS pricing change (deterministic formula, no gate needed - but record vintage); amend `test_trade_board_coverage.py` (expiring-with-salary now priced; unpriced ledger still never leaks into rankings), `test_proj_export.py` (new scalar fields; array shape unchanged), `test_calibration_vintage.py` expectations, new invariant tests from above. Update `data/glossary.json` surplus-adjacent entries if they state "2027+" horizons.

**Regen + acceptance (Phase 2)**: two full export passes (the one-cycle skew, M2 defect 6); then verify IN THE SERVED ARTIFACTS: Minter present in `trade_values.json.players[]` with `surplus_source:"projection"`, his `sur_ros` consistent with `{2026: 7,588,208}` and the run date; Judge's value = old surNpv + his 2026 remainder; Torres off the $80.1M backgrade basis; expiring-unpriced ~0; coverage stamp reconciles; calibration vintage identical across `xfv.json` / `mlb_projections.json` / `trade_values.json` / `value_framework.json`; full suite green (the one deliberate recenter red stays red).

## Execution order

Phase 0 (0a -> 0b -> 0c) -> Phase 2 (data plane; it needs the regen fresh anyway) -> Phase 1 (GFX; reads the regenerated board) -> final: both acceptance blocks, `strip_emdashes --check`, `copy_lint`, suite, single push to `main` only. If any measured number above disagrees with what you find, STOP and re-measure before proceeding - this plan's authority is its measurements, and a drifted repo state invalidates the affected step, not the whole plan.
