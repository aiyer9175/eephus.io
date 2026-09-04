# WAR basis runbook: bWAR to eWAR v2, the rebuild wave

Written 2026-09-03 in wave 1 (code and tooling only). This is the ORDERED command list
for the later rebuild wave, gated on the design audit report and on Appendix A of
`docs/efv-2026-09-03/EWAR_LABEL_EPOCH_GATE.md` being frozen. Nothing in this file has been
run. Every step names what it writes, what it invalidates, and whether the box must run it
too. Run from `C:/Users/noah/baseball-projects/BaseballR/prospect-tracker` (the cwd drifts
between shells; cd every time).

Prior runbooks this extends: `docs/efv-2026-07-30/REGEN_AND_PUSH_RUNBOOK.md` (regen then
push, restamp from production output), `docs/efv-2026-08-13/GRADE_BASIS_EPOCH_GATE.md`
(epoch bump + fingerprint + prospx_current in one commit),
`docs/master-plan-2026-08-03-eight-asks.md` D3 (the Stage-2 cascade),
`docs/master-plan-2026-08-16-sdr-ewar.md` W3.5 (the war_source trap list IS the checklist).

## Rules that hold for the whole wave

- ORDER IS LOAD-BEARING. Floors before deltas. Curve before anchors. Retrain before the
  rebuild passes. Two rebuild passes because of the one-run lag. Margins LAST.
- One code commit carries the seam flip, the epoch bump and the `label=` fingerprint
  term together (step D + step U). Artifacts commit separately after step T. Never let
  the box's own `data/` churn ride inside a code commit.
- The suite runs BETWEEN edit batches, never alongside them (`conftest.py` reverts dirty
  tracked files at session end; an edit made during a run is silently undone).
- Nothing is restamped to make a red go green. A red is either an owed restamp named
  here or an open defect.
- No em-dashes in any copy or comment this wave writes. `python tools/copy_lint.py --check`.
- `prospects.db` is written by exactly two steps (C and the box mirror of C). Everything
  else reads.

## Step table

Legend: WRITES = artifacts the step produces. INVALIDATES = what is stale after it and
must be regenerated downstream. BOX = whether the deploy box must run it as well
(the box is a separate database seed and a single writer; see the deploy memory).

### A. Preconditions and the pre-epoch snapshot

    cd C:/Users/noah/baseball-projects/BaseballR/prospect-tracker
    git status --short | grep -v "^ M data/"       # code tree clean apart from data/ churn
    git status --short data/ ; sleep 300 ; git status --short data/   # stable twice = nightly idle
    mkdir -p ../_pre_epoch_2026-09 && cp prospects.db ../_pre_epoch_2026-09/prospects.db
    cp data/xfv.json data/timeseries.json data/trade_values.json data/star_label_view.json \
       data/farm_grade_eval.json data/mlb_projections.json data/arbitration.json \
       data/fv_outcome_curves_pooled.json data/value_framework_fitted.json \
       data/xfv_eval.json data/xfv_eval_pitcher.json data/xfv_mde_floor.json \
       data/xfv_power_eval.json data/source_backtest.json ../_pre_epoch_2026-09/

Why: clause (f) of the gate diffs every blast-radius statistic against THIS snapshot; the
`career_war` backup is also the bWAR-label input for the cross-label matrix (clause b).
Org letter grades (the WAG consumers) live inside `timeseries.json` and the DB table
`farm_grade_history`, both covered by the two copies above.
Confirm Appendix A of the gate is frozen and the design audit report is filed; if either
is missing, stop here. WRITES: the snapshot directory outside the repo. BOX: no.

### B. Build eWAR v2 across the whole label window

    python tools/build_ewar.py --first 2011 --last 2026 --write

Why: the committed `data/ewar.json` is the 2026-08-04 build (2016-2026, 15,512
player-seasons, 3,963 players); L1 rebuilt it in wave 1 to 2011-2026 (working tree:
generated 2026-09-03T12:35:09, 22,160 player-seasons, 5,136 players, pitcher-seasons 12,457
on FIP / 35 on B-Ref fallback). The eFV label window starts at debut year 2011; the gate's
two censuses show the 2011-2015 cohort's join going 41.5 to 89.9 percent on the rebuild,
with the residual being 239 no-id label seasons. The FIP corpus (`.cache/fa_corpus.pkl`)
reaches 2000, so the swap is computable for every season in the window; OAA is irrelevant
at fielding weight 0.0. RE-RUN this step if `ewar.py` changed after L1's artifact was
written, and re-run it after step E if the corpus was rebuilt (the FIP constant comes from
the corpus); then `--reapply` in step C. The eval flags (`--eval-first`, `--eval-last`)
default to the 2016 OAA era; leave them.
WRITES: `data/ewar.json`, `data/ewar_eval.json`. INVALIDATES: everything below.
BOX: yes, or ship the artifact; the box needs the same `ewar.json` the rebase read.

Draft slot curve note (decision for the owner before step K): `tools/fit_draft_slot_curve.py`
fits the 2005-2018 cohorts, so 2005-2010 pitcher seasons would stay on B-Ref pricing under a
2011 build. The corpus reaches 2000, so `--first 2005` is one build away. Either build from
2005 or have the slot artifact disclose the mixed basis for 2005-2010 pitchers. Position
players are identical either way.

### C. Rebase the career_war table (dry-run, then apply)

    python tools/rebase_career_war_to_ewar.py --json    # DRY RUN: coverage receipt, no write
    python tools/rebase_career_war_to_ewar.py --apply   # backs up prospects.db, writes once
    python tools/rebase_career_war_to_ewar.py --reapply # only after a REBUILT ewar.json (step B re-run)

Why: `career_war` (2,666 rows, `{player_key: {seasons {year: war}, career_war, war_per_yr,
war_seasons_count, source}}`) is the label funnel for `efv_dataset` (SQL read at
`efv_dataset.py:1091`), `empirical_anchors.py:63`, `surplus_backtest_real`,
`farm_grade_backtest`, WAG and the timeseries `career_war` payload that `source_backtest`
reads. Rebasing the table is what moves the label; nothing else does. What the L1 tool
does (its docstring is the contract; `test_career_war_ewar_funnel.py` pins it offline):

- resolves `player_key -> mlbam` from storage's durable `player_photos` binding first
  (keys bound to two ids excluded), then the two override files; unresolved rows are left
  as bWAR with `source bbref` and counted in the receipt;
- writes eWAR where `ewar.json` has the (mlbam, season) and the bWAR value where it does
  not, keeps the frame as `seasons_bwar`, stamps `source ewar_v2` and an `ewar_coverage`
  receipt; the 2026-09-03 dry run against the 2011-2026 artifact reported 0 pre-window
  fallbacks and 90 in-window fallbacks of 11,564 seasons;
- writes through `storage.upsert_career_war`, whose MERGE now unions `seasons_bwar` by the
  same rule as `seasons` and lets the new payload's `source` win (L1's `storage.py` change);
- is idempotent: an `ewar_v2` row re-derives from `seasons_bwar`, never from the served
  series, so apply twice equals apply once; plain `--apply` REFUSES on a table that
  already carries `ewar_v2` rows (use `--reapply`);
- takes the backup itself through sqlite's backup API (`prospects.db.bak-ewar-<date>`,
  WAL-safe; the plain copy in step A is the belt to this brace).

After `--apply`, assert from a read-only shell that no player-season is left with neither
value and that the coverage receipt matches the gate's clause (c) census within the
identity floor (69 no-id players).

WRITES: `prospects.db` (`career_war`), the `.bak-ewar-<date>` file. INVALIDATES: matrices,
evals, floors, curve, anchors, surplus and farm backtests, WAG, timeseries, star odds.
BOX: YES, and it is the step most likely to be forgotten. The box database is a separate
seed and the table is not tracked by git; run the same `--apply` there. The nightly's own
refetch (`run_monthly.py` step 3d) now goes through `war_source.career_war_bulk` on the
default provider (L1's `run_monthly.py` change, pinned by the funnel test), so once step D
flips the default the nightly writes eWAR-basis rows and does not undo this step. If step D
has NOT landed when a nightly runs, the refetch writes bWAR under `source bbref` for the
refetched cohort and `--reapply` restores the basis; order the deploy so that cannot
happen.

### D. Flip the facade default (L2 commit)

    # war_source.DEFAULT_PROVIDER 'bwar' -> 'ewar_v2'; _require stops raising for it
    python -m pytest test_war_source.py -q -p no:cacheprovider -x

Why: every read the sites make goes through `war_source` (career_war_bulk,
career_war_table, side_war_by_season, stint_frame, condensed_frame, run_value_frame,
name_index). `test_war_source.py::test_bwar_is_the_default_provider_everywhere` and the
DataUnavailable wording test change in the SAME commit; provider='bwar' stays byte-exact.
Check that `war_source.stint_frame(side)` under the new default carries eWAR in the WAR
column that `fa_projection._war_age_maps` (`fa_projection.py:87-96`) and
`arb_dataset.war_daily_spine` read, or the projections and the arbitration spine stay on
bWAR while the copy says otherwise. `war_source.py:33-39` (the trap comment) and
`_UNAVAILABLE['ewar_v2']` are rewritten to describe the served state.
WRITES: code only. INVALIDATES: `fa_corpus.pkl` (step E), the arb dataset, the display WAR
on every MLB surface. BOX: pulls with the code.

### E. Invalidate the caches that hold WAR per row

    rm -f .cache/fa_corpus.pkl
    rm -f .cache/fa_fits_*.pkl
    rm -f .cache/proj_ml_frame_*.pkl
    # KEEP .cache/war_daily/{bat,pit}.parquet: that is the bWAR INPUT the frame is built on

Why: `fa_projection.build_corpus` caches `war` per player-season row in
`.cache/fa_corpus.pkl`, and `_corpus_stale_reason` (`fa_projection.py:134-155`) only fires
on a newer in-progress-season source file or a 3-day age; a WAR-basis change is not a
trigger and a completed-season corpus never expires. `fa_fits_*` is keyed on
`_corpus_sig(corpus)` and would self-invalidate once the corpus content moves, but it is
deleted anyway so the directory tells the truth. `proj_ml_frame_*` is keyed on schema tag,
base year and the corpus first/last ONLY (`proj_ml.py:308-309`), not on content, so it
would serve a bWAR training frame under an eWAR corpus; it MUST be deleted.
WRITES: nothing. INVALIDATES: the FA corpus, aging fits, projection frames. BOX: yes.

### F. Labeled matrices and evals, both sides

    python efv_dataset.py            # hit
    python efv_dataset.py --pit
    python efv_model.py              # hit
    python efv_model.py --pit

Why: the matrices carry the label (`_label_6yr` over the rebased `career_war`); the evals
are the forward-chained governance artifacts the floors resample. `build_live` inside
`efv_dataset.run` reads `data/timeseries.json`; on this first pass it reads the pre-epoch
timeseries, which is fine for the LABELED matrix and is why step P runs `regen_all` again
later. WRITES: `data/xfv_hitter_matrix.json`, `data/xfv_pitcher_matrix.json`,
`data/xfv_dataset_report.json`, `data/xfv_pitcher_dataset_report.json`,
`data/xfv_eval.json`, `data/xfv_eval_pitcher.json`. INVALIDATES: floors, curve. BOX: no
(the box regenerates these itself on its nightly; the dev run is for the measurement).

### G. Floors FIRST

    python tools/efv_mde_lab.py mde 2000
    python tools/efv_power_lab.py all 2000

Why: clause (a). The bWAR-frame floors (E_cond 0.0206 / 0.0212 / 0.0209 / 0.0290)
adjudicate nothing on the new frame. Seed 20260807 is the standard's; do not change it.
WRITES: `data/xfv_mde_floor.json`, `data/xfv_power_eval.json` (the power lab's own
docstring warns that changing any existing function moves every published number in it;
add, do not edit). INVALIDATES: every stored margin verdict. BOX: no.

### H. The label-epoch lab (the gate's measurement)

    python tools/efv_ewar_label_epoch_lab.py     # to be written by the rebuild wave

Why: clauses (b) through (f) need one producer that reads the eWAR matrices (step F), the
pre-epoch snapshot (step A) for the bWAR label and the bWAR-fitted model, and the floors
(step G). It fits nothing new on the served path and writes exactly one artifact. The
zero-information twin permutes eWAR-minus-bWAR deltas across players within (season,
side); the permutation band and the >= 4 fold average are the standard's. Prior art for
the lab shape: `tools/efv_label_replacement_lab.py` (pins asserted, one artifact,
read-only on production modules). WRITES: `data/xfv_ewar_label_epoch_eval.json`.
BOX: no. Read its numbers only after step T (the margin re-read rule, step Z).

### I. The pooled FV outcome curve

    python tools/fv_outcome_curve_pooled.py

Why: `xfv_grade` is the inverse of this curve (`vf.outcome_implied_fv`), the curve is fit on
realized first-6yr WAR from `career_war`, and its content hash is the `grademap=` term of
`storage.BOARD_BASIS_FINGERPRINT` (`outcome_pooled@6dbe8353f3bb` today). The hash WILL move
and `test_board_basis_coherence` will fail until step U restamps it; that is the device
working. WRITES: `data/fv_outcome_curves_pooled.json`. INVALIDATES: every served grade,
the fingerprint pin, `realized_implied_fv` consumers, WAG survivor anchors. BOX: yes, or
ship the artifact (the curve is committed, not nightly).

### J. Empirical anchors and the valuation sets

    python value_framework.py --fit
    # then re-capture prospx_current INSIDE the set, in a python shell:
    #   import value_framework as vf
    #   with vf.valuation_set("prospx_current"): <the capture the 2026-08-13 epoch used>

Why: `--fit` calls `empirical_anchors.derive_empirical_war_anchors` (`value_framework.py:3544`),
which reads `career_war`, and writes the fitted ordered-logit plus the anchors into
`data/value_framework_fitted.json`; `survivor_expected_war` (WAG's FV -> WAR/yr basis) and
`expected_surplus_usd` read from it. The `prospx_current` set must be captured inside its
own `valuation_set` context or the capture prices off the wrong engine
(`GRADE_BASIS_EPOCH_GATE.md` condition 8). Then sync the frontend mirror
`prospx/index.html:22494` (`FV_WAR_ANCHORS`) to the derived survivor curve; it is a hand
mirror, not generated. WRITES: `data/value_framework_fitted.json`,
`config/valuation_sets/prospx_current.yaml`, the prospx mirror. INVALIDATES: surplus
dollars everywhere, WAG, trade values. BOX: yes (committed config).

### K. Draft slot curve refit

    python tools/fit_draft_slot_curve.py

Why: `storage._PICK_SLOT_EXPECTED_WAR` seeds the QO pick-tax chain and the draft surplus;
the tool fits realized WAR per pick from war_daily through `war_source`. Coverage note in
step B applies. WRITES: `data/draft_slot_curve.json`. INVALIDATES: draft pick surplus,
QO pricing. BOX: yes, or ship the artifact.

### L. WAR/PA+ and WAR/IP+ vintages

    python tools/war_rate_plus_lab.py

Why: the two Arkmetrics are batting and pitching WAR per PA / IP indexed 100 + 10z, served
from FROZEN lab artifacts (`bullpen_export.py:819-820`, `hitter_export.py:600`), and
`test_claims_freshness.GLOSSARY_CLAIMS` pins the glossary's quoted numbers to
`data/war_rate_plus_eval.json` at 0.005. WAR/PA+ is hitter-side and does not move; WAR/IP+
does. Re-run the lab, then let the glossary copy re-derive; edit the claims table only if
the copy shape changed. WRITES: `data/war_rate_plus_eval.json`,
`data/war_rate_plus_multiyear_eval.json`. INVALIDATES: the mlbstats boards' rate columns,
their glossary claims. BOX: yes, or ship the artifacts.

### M. Projections retrain

    python tools/train_proj_models.py --final

Why: `proj_ml` trains on `fa_projection._war_age_maps` labels, which come from
`war_source.stint_frame` under the flipped default (step D) through the rebuilt corpus
(step E). Four pins move together or the retrain did not happen: the feature schema
length (`test_proj_ml.py:54`), `model/proj_lgbm/meta.json` `train_hash`
(`proj_ml.py:397`, `test_proj_ml.py:140`), the ml_config gate
(`test_ml_config_gate_defaults_off_until_shipped`: bundle + hash + registry champion), and
the `star_blend` pin (`test_star_blend_pinned_to_artifact` against
`data/proj_star_blend.json`; h2 must stay 0). Re-read `fa_backtest` Gate 1 afterwards and
expect the R3b direction (the naive carry-forward gains more than the model on a more
persistent label); record it in the registry as the mechanism, not as a regression.
The `mean_blend` pin (`data/proj_mean_blend.json`) is checked the same way.
WRITES: `model/proj_lgbm/models.joblib`, `model/proj_lgbm/meta.json`. INVALIDATES:
`data/mlb_projections.json`, trade values (`bayes_trade_value.apply_platform_surplus`
prices off the projections on disk), `proj_export`'s league benchmark note
(`proj_export.py:1597`, "1000 bWAR"). BOX: pulls the bundle with the commit.

### N. Star odds artifacts and the shadow constant

    grep -n "_RESOLVED_THROUGH = " tools/build_star_odds_artifacts.py   # 27: 2025, must equal efv_dataset.RESOLVED_THROUGH
    python tools/build_star_odds_artifacts.py

Why: `data/star_label_view.json` is the Clemens star label (>= 2 control seasons of 4+
WAR); a pitcher whose FIP-priced season crosses 4.0 flips. The tool carries its own copy
of `RESOLVED_THROUGH`; this epoch does not move that constant, but the check is in the
same-commit checklist for every epoch, so run it. WRITES: `data/star_label_view.json`,
`data/star_odds_eval.json`. INVALIDATES: star odds copy, BREAKOUT's label (a later
program). BOX: the nightly runs this itself (`run_monthly.py:5345`).

### O. Site rebuild, pass 1

    python run_monthly.py --rebuild-only

Why: `rebuild_only` loads snapshots plus the rebased `career_war`, builds the timeseries,
runs the eFV regen inside it, exports `mlb_projections.json` between the eFV regen and the
trade-value export, then `source_backtest` and the star odds. On THIS pass the eFV regen's
live matrix still reads the previous timeseries (the one-run lag the 2026-08-07 note at
`run_monthly.py:2199-2212` describes), so pass 1 exists to put a new-basis timeseries on
disk for pass 2. WRITES: `data/timeseries.json` and the whole export set. BOX: this IS the
nightly; the box does it on its own schedule once the code and DB are in place.

### P. eFV regen with the eval, on the new timeseries

    python efv_export.py --all --eval

Why: `regen_all(include_eval=True)` runs matrices (labeled AND live, now against the pass-1
timeseries), evals, resolved scores, live scores, backgrade, `score_history` (which restamps
`xfv_history.json` with the new fingerprint so `xfv_history_is_on_board_basis` returns True
again after step U), tool eFVs and the ungraded model. This is the PRODUCTION output the
golden is restamped from (step V). WRITES: `data/xfv.json`, `data/xfv_history.json`,
`data/xfv_live_*_matrix.json`, `data/xfv_tools*.json`, `data/xfv_ungraded.json`, and the
evals again. INVALIDATES: the golden hash, the pass-1 trade values. BOX: runs inside the
nightly's rebuild_only.

### Q. Source backtest

    python source_backtest.py         # run_source_backtest(write=True) by default

Why: `data/source_backtest.json` is where the head-to-head and the C1-C4 claim cells live,
and it reads the timeseries `career_war` payload (now eWAR) and `debuts.json`. Pass 1
already wrote it; re-running here makes the served artifact read the step P grades.
WRITES: `data/source_backtest.json`. INVALIDATES: the derived accuracy copy's inputs (it
re-derives; nothing to edit). BOX: nightly.

### R. Site rebuild, pass 2

    python run_monthly.py --rebuild-only

Why: the one-run lag. Pass 2's eFV regen reads the pass-1 timeseries, `proj_export` reads
the step M bundle, and the trade-value export reads the fresh `mlb_projections.json`. The
2026-08-16 plan called for THREE passes on the full epoch; run a third if any served
artifact still carries a pre-epoch stamp after two (check `generated_at` on `xfv.json`,
`trade_values.json`, `mlb_projections.json`). WRITES: the export set. BOX: nightly.

### S. The remaining exports

    python fa_export.py
    python arb_export.py
    python hitter_export.py
    python starter_export.py
    python bullpen_export.py
    python mlb_player_export.py

Why: FA (`fa_projection` corpus WAR, the `fa_def_pin` signature), arbitration
(`arb_dataset.war_daily_spine`, the WAR column of the salary spine, then the award model
re-read under `docs/ARBITRATION_GATE.md`), the three mlbstats boards (display WAR via
`war_source.side_war_by_season`, WAR/PA+ and WAR/IP+ from step L), and the player pages
(`mlb_player_export._war_daily` per-season display WAR). Some of these run inside
`rebuild_only` already; running them standalone is cheap and removes the doubt.
WRITES: `data/fa_class.json` (+ `_2028`, `_2029`), `data/arbitration.json`,
`data/arb_history.json`, `data/hitter_leaderboards.json`, `data/hitter_history.json`,
`data/starter_leaderboards.json`, `data/starter_history.json`,
`data/bullpen_leaderboards.json`, `data/bullpen_history.json`,
`data/mlb_player_detail.json`. BOX: nightly.

### T. Build the site

    python build_site.py

Why: hand pages are content-hash stamped; the bWAR strings at `build_site.py:1407` ("career
bWAR"), `:2875` and `:3694`/`:3708` ("five-year bWAR"), `:5221` ("WAR site-wide is
Baseball-Reference's bWAR: one source, every surface") and `:5730` are replaced by the frame
disclosure BEFORE this runs (step X), so the build stamps the new copy. WRITES: every
`index.html` under the site plus `SITE_MAP.md` inputs. BOX: nightly.

### U. Epoch bump and the fingerprint term (in the step D commit)

    # storage.py: BOARD_RANK_BASIS_EPOCH "2026-08-13" -> the flip date (strictly-after gate)
    # storage.board_basis_fingerprint(): add a label= term; storage.BOARD_BASIS_FINGERPRINT restamped
    python -m pytest test_board_basis_coherence.py -q -p no:cacheprovider -x

Why: the movement engine differences board ranks across the epoch date; without the bump
the re-rank publishes as player movement (2026-07-29 incident). The fingerprint has no
`label=` term today, so it would report "no change" through a served-label flip; add one
that names the provider and the build identity of the label series (for example
`label=ewar_v2@<ewar.json generated_at or a career_war digest>`), cheap and import-safe like
the other terms, and restamp the pinned string with the new `grademap=` hash from step I.
Check `PINNED_MIX` ({"top10": 0, "top25": 1, "top50": 2, "top100": 6}) against the new
top-100 side mix; re-record only if breached, and say why in the commit. Expect
`xfv_history_is_on_board_basis()` False for one cycle until step P's `score_history`
restamps the history artifact. WRITES: `storage.py`. BOX: pulls with the code.

### V. Golden restamp, OUTSIDE pytest

    python -c "import hashlib,json; ..."   # the volatile-key-stripped sha256 test_efv_export computes

Why: `test_efv_export._GOLDEN_XFV_SHA256` (`687aab4b...` today) and `_GOLDEN_XFV_ROWCOUNT`
(9,379) pin `data/xfv.json`. The standing convention (`test_efv_export.py:366-368`): restamp
from the PRODUCTION `efv_export.py --all` output of step P, never from a tree pytest has
run against (a mid-suite test regenerates `xfv.json` under fixtures). Record the cause
beside the constant: "eWAR label epoch, 2026-09". WRITES: `test_efv_export.py`. BOX: no
(deploy mode shape-checks the rowcount only).

### W. Registry edits, then the generated docs

    # data/model_registry.json: ewar row consumers off "NONE"; eFV rows label_basis ewar_v2;
    # fa_war_paths_decay champion/train_hash; war_rate_plus rows re-read; fa_gate1 note (R3b direction)
    python tools/gen_audit_docs.py
    python -m pytest test_generated_docs_in_sync.py test_model_registry.py -q -p no:cacheprovider -x

Why: `MODEL_REGISTRY.md`, `SITE_MAP.md` and `DATA_SOURCES.md` are GENERATED from the
registry (`tools/gen_audit_docs.py:49`); editing them by hand desyncs the suite. Every
model whose label, anchor or eval moved gets its row touched with the eval artifact path
and the date. WRITES: `data/model_registry.json`, the three generated docs. BOX: committed.

### X. Copy, then the linter

    grep -rn "bWAR" --include=*.py --include=*.js --include=*.html . | grep -v "^./data\|^./docs\|^./.cache\|test_" 
    python tools/copy_lint.py --check

Why: 413 occurrences across 103 files outside data/docs/cache at registration
(`assets/projections.js` 25, `prospx/index.html` 21, `assets/fa.js` 14, `assets/mlbstats.js`
13, `bullpen_export.py` 12, `build_site.py` 9). Every SERVED claim becomes the frame
disclosure; comments that describe the INPUT ("the war_daily bWAR frame") stay, because
bWAR is still the input. The derived three-branch accuracy copy (`assets/glossary.js:618`,
`:1301`, `:2653`, `assets/diamond.js:152`) is not edited: its inputs regenerated. The copy
gates listed in the gate's clause (g) flip in the same commit as the strings they assert.
WRITES: copy surfaces, the tests that pin them. BOX: committed.

### Y. The suite, chunked, unpiped

    python tools/run_suite.py --out suite.json

Why: the full suite crashes in one process (`tools/run_suite.py` docstring); run it from
`prospect-tracker/`, never piped, and read the return codes and `suite.json`, not a parsed
total. Baseline is exactly two reds (`KNOWN_BASELINE_REDS`: the golden until step V lands,
`test_proj_export::test_vet_surplus_only_on_contracted_seasons`). Every other red is either
an owed restamp named in this file or a defect; nothing is silenced. Run it only when no
edit is in flight. WRITES: `suite.json` (untracked). BOX: no.

### Z. Margin re-read AFTER regeneration, then fill the gate's part 9

    # read: data/xfv_mde_floor.json, data/xfv_power_eval.json (step G)
    #       data/xfv_ewar_label_epoch_eval.json (step H, RE-RUN after step P so it reads served grades)
    #       data/xfv_eval.json, data/xfv_eval_pitcher.json, data/source_backtest.json (steps P, Q)

Why: a margin read against an artifact even two days stale has crossed a verdict boundary
before (`EFV_GATE_STANDARD.md` 7.5). The lab in step H is re-run here so the blast-radius
block diffs the FINAL served artifacts against the step A snapshot, and the matrix cells
read the final matrices. Only then is part 9 of the gate written, with the estimator named
on every number, and Holm across the cells the gate registered. Then commit the artifacts
as their own commit, and hand the owner the push (owner pushes; sync beta by fast-forward
per the webmaster handoff, never revert or merge).

## What the box must do, collected

1. Pull the step D + U code commit (facade default, epoch, fingerprint, nightly routing).
2. Back up its database, then run the step C rebase `--apply` on it.
3. Delete the step E caches on the box.
4. Receive `data/ewar.json`, `fv_outcome_curves_pooled.json`, `draft_slot_curve.json`,
   `war_rate_plus_*_eval.json`, `value_framework_fitted.json`, `prospx_current.yaml`, the
   `proj_lgbm` bundle, all committed.
5. Its nightly then does steps O through T on its own; the FIRST nightly's movement chips
   read empty (epoch gate) and that is correct.

## What this runbook could not settle in wave 1

- Whether `war_source.stint_frame` under `ewar_v2` carries eWAR in the WAR column or in a
  separate column (L2 design; `war_source.py` was unmodified in the working tree when this
  file was written). Step D's check is what settles it; step M and the arb spine depend
  on it.
- The shared transform helper the rebase tool looks for at run time
  (`war_source.ewar_seasons_from_bwar`): if L2 ships it, the funnel and the rebase agree
  bit for bit by construction; if not, the tool's inline rule runs and the two must be
  compared by test.
- The draft slot curve's 2005-2010 basis (step B note): owner call.
- Appendix A of the gate: filled from the design audit before step F.
- The `label=` fingerprint term's exact string (step U): the storage owner's call; the
  requirement is only that it moves when the served label basis or its build moves.
