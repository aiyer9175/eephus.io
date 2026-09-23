# PORT SPECIFICATION: eephus.io to git.eephus.io/eephus/eephus

Final. Written 2026-09-18 for the owner and the webmaster, after two adversarial reviews
(one on safety, one from the webmaster's seat). Every number below was measured on
`C:/Users/noah/baseball-projects/BaseballR`, branch `efv-conviction-2026-08-08`, on
2026-09-18. Read-only pass: nothing was edited, no tests were run, no remote was touched,
no network was used.

Supporting inventories: `portspec/I1/NOTES.md` (served surface), `portspec/I2/NOTES.md`
(models and evidence), `portspec/I3/NOTES.md` (leakage guards), `portspec/I4/NOTES.md`
(ingest, identity, deploy), `portspec/review_a/MEASUREMENTS.md` (safety review),
`portspec/review_b/NOTES.md` (webmaster-seat review), `portspec/cache_inventory.tsv`
(406,315-row cache inventory generated for this revision).

**What changed in this revision.** The previous draft had five gates, three of which a
broken port could have passed, and a copy-first list that omitted the point-in-time model
bundles. Both reviews landed. Section 11 maps every defect to its resolution. The short
version: Gate C now has a mechanism, a liveness precondition and a positive control; the
cache rule is computed from `prune_cache.SAFE_CACHES` instead of hand-listed; Gate B no
longer forbids the frontend rebuild the owner asked for; and section 9 says plainly which
parts of this platform are not earning their place.

---

## 0. BOTTOM LINE, FIVE SENTENCES

1. **The port is a data migration, not a code migration.** 95.7 percent of the served data
   by volume is not in git. Cloning the repo onto a new remote produces a site that 404s on
   1,617 MB of its 1,689 MB payload.
2. **The webmaster is right about five things and they are worth doing**, in particular the
   integer identity spine and the per-player change detection (a measured 272 MB of
   pointless rewriting per night), and he is right that some of this platform's machinery
   is not earning its place. Section 9 names what to drop, with measurements.
3. **Three items in his plan must be reordered, not rejected**: the site should not
   live-query the database, the ML rewrite must follow the port, and Chadwick is the
   crosswalk rather than the active register. All three corrections follow from his own
   premise that the data is mostly static.
4. **Phase 0 is not optional and it is bigger than it looks.** Five things do not exist yet
   that the gates depend on: a frozen-input mode, a dependency lock, a recorded test
   baseline, an eval-sidecar partition, and a loud failure when a point-in-time model
   bundle is missing. Build those before anything moves.
5. **Two served-number defects are live right now** and must be resolved before the port so
   a new backend is not blamed for them: the `proj_def_prior` bundle pin (section 1.5) and
   the two-scale `tj_stuff_plus` in `data/pitch_plots/` (section 9.2, found during this
   revision, 58,270 affected points).

---

# 1. WHAT IS BEING MOVED

## 1.1 The served surface: 12,235 files, 1,768.91 MB

| segment | files | MB |
|---|---:|---:|
| pages, assets, vendor, collegesavant (`deploy/publish_paths.txt`, 35 entries) | 135 | 80.75 |
| `data/*.json` shipped (400 of 430) | 400 | 353.33 |
| `data/*.js` | 3 | 1.86 |
| `data/pitch_plots/<player_key>.json` | 1,789 | 1,003.62 |
| `data/player_detail/<player_key>.json` | 7,147 | 255.02 |
| `data/debuts_full/<player_key>.json` | 2,761 | 74.33 |
| **total published** | **12,235** | **1,768.91** |

**Routes.** 29 written by `build_site.main()` (`build_site.py:6492-6523`): `/`, `/news/`,
`/history/`, `/articles/`, `/articles/<slug>/`, `/forums/`, `/fa/`, `/projections/`,
`/mlbstats/`, `/pal/`, `/trademachine/`, `/arbitration/`, `/fantasy/`, `/dynasty/`,
`/redraft/`, `/dfs/`, `/betting/`, `/diamond/`, `/parks/`, `/hof/`, `/management/`,
`/models/`, `/glossary/`, `/teams/`, `/team/`, `/sources/`, `/report/`, `/404.html`,
`/robots.txt`, `/sitemap.xml`.

4 more are **hand-maintained and NOT generated**: `/prospx/` (a 3.09 MiB single-file inline
app, 48 top-level JSON plus 3 templated patterns), `/collegesavant/` and
`/collegesavant/pitcher_index.html` (71.94 MB with its data embedded as `.js` modules and
zero JSON fetches), and `/player/` (the canonical deep-link router). A port that only runs
the generator ships 29 of 33 routes.

**Deep-link keys**, a public contract because they are bookmarked: `projections.js`
`#player= #section= #team= #view= #window=`; `mlbstats.js` `#player= #section= #team=
#view=`; `betting.js` `#player= #section=`; `fantasy-hub.js` `#player= #section=`; `fa.js`
`#player= #view=`; `trademachine.js` `#player= #tab=`; `glossary.js` `#player= #tab=
#view=`; `pal.js` `#player=`; `parks.js` `#view=`; prospx `#tab=` over 11 values.
Canonical player entry point is `/player/#<player_key-or-mlbam>`, resolved through
`data/player_links.json`.

**The URL space is keyed on `player_key` name slugs**, not on any external ID. 11,697
per-player file URLs plus every deep link above. See decision D4.

## 1.2 Five templated fetch forms a fetch-list port will drop

- `data/pitch_plots/{player_key}.json`
- `data/player_detail/{player_key}.json`
- `data/debuts_full/{player_key}.json`
- `${c.prefix}${idx}.json`, the scout-report chunk contract. Verified at
  `storage.py:16803-16806`: `_SCOUT_CHUNKS = 8`, shard is `sum(ord(c) for c in key) % 8`,
  mirrored by `_scoutChunkOf` in `prospx/index.html`. Change the hash and every cached boot
  payload fetches the wrong chunk.
- `${base}draft_timeseries.json`, `${base}overseas_timeseries.json`,
  `${base}mlb_trade_players.json`, `${name}.json`.

**`SITE_MAP.md` is wrong in both directions and must not be the port checklist.** It misses
`mlb_trade_players.json` and the `/player/` route because `tools/gen_audit_docs.py` regexes
fetch strings and does not resolve template literals, and it invents `grpo_scores.json` as a
`/trademachine/` payload by regexing a filename out of a code comment at
`assets/trademachine.js:503-505` (the real fetch at line 1422 is `grpo_public.json`).

## 1.3 The artifacts

430 top-level `data/*.json`, 436.48 MB. **400 ship (353.33 MB). 30 are withheld
(83.15 MB)** by `deploy/data_exclude.txt`: 30 non-comment entries, all 30 exist, none is a
`model_registry` `eval_artifact`, so `test_publish_manifest.py` currently holds.

**The withhold list is a leakage control, not a size control.** It bars
`star_label_view.json` (per-player training labels), `xfv_scored*.json` and the
`xfv_*_matrix` files (model internals), and `identity_collisions.json` (an ops ledger naming
players whose records fuse two humans). Publishing any of them hands a reader the label side
of the fit.

## 1.4 The state that is NOT in the repository, which is the actual port

| store | size | in git? |
|---|---:|---|
| `prospect-tracker/prospects.db` | **1,878,773,760 bytes (1.879 GB)**, 53 tables, 0 views, 0 triggers | no |
| `.cache/` total | **406,315 files, 56.84 GB** (re-counted in full for this revision) | no |
| `.cache/` **must-carry subset** | **115,412 files, 3.77 GB** (rule below) | no |
| 32 top-level `data/*.json` | 281.53 MB | no, gitignored |
| 3 per-player directories | 11,697 files, 1,332.97 MB | no, gitignored (.gitignore:99,102,105) |
| git-tracked share of the 1,689 MB served payload | **71.80 MB, 4.3 percent** | yes |

### 1.4.1 The cache copy rule. This replaces the previous eight-directory list.

The previous draft said "198 files, 364 MB, everything else is in `prune_cache.SAFE_CACHES`
and is refetchable." **That was measurably false and it is the most dangerous single error
the reviews caught.** Full inventory, 406,315 rows, taken today:

```
TOTAL under .cache/                       406,315 files   56.84 GB
in a SAFE_CACHES directory (refetchable)  290,903 files   53.07 GB
on the old eight-directory copy list          198 files    0.35 GB
NEITHER: not prunable, not on the list    115,214 files    3.42 GB   <- dropped by omission
   of which loose at the .cache/ root      97,818 files    2.88 GB   <- the pruner never walks these
```

`prune_cache.py:49-51` states the design in its own words: `SAFE_CACHES` is an allowlist
"so a future cache holding non-refetchable state is never pruned by accident." The previous
draft inverted that allowlist into a denylist. Named members of the dropped 3.42 GB:

```
proj_ml_pit_*.joblib        29 files   756.7 MB  POINT-IN-TIME model bundles (section 1.4.2)
savant_pitches_*         2,162 files   556.7 MB
mlb_pipeline_*             535 files   472.3 MB  Pipeline board snapshots back to 2011
mlb_<urlhash>          ~81,000 files   427.7 MB  StatsAPI URL cache (refetchable, but slow)
fa_fits_*.pkl              219 files     7.5 MB  FA aging-curve fits
ewar_bwar_{bat,pit}.pkl      2 files    64.4 MB  bWAR label caches
proj_ml_frame_*.pkl          6 files    64.9 MB  training frames (all tagged _ewar_v2)
fg_*                       271 files    94.2 MB  FanGraphs pages. deploy/README.md:32, verbatim:
                                                 "FG blocks Python; CANNOT refetch"
spotrac_*                   89 files    77.0 MB  rate-limited contract scrapes
aaa_pitches_vaa/         1,085 files   112.6 MB
milb_platoon/              164 files    65.4 MB
pal_gamelogs/            1,262 files    54.1 MB
statsapi_field_season/     154 files    46.4 MB    statsapi_field/    29 files  44.1 MB
milb_full_stats/            82 files    29.9 MB    mlb_transactions/ 141 files  24.8 MB
hof/                        92 files    23.5 MB    anchor_probe/      21 files  18.7 MB
draft_bonus/                10 files    15.6 MB    milb_pbp/      12,838 files  15.9 MB
fangraphs/                  48 files     9.1 MB    amateur_leagues/   36 files   7.6 MB
```

The `fg_*` line is the one that would have hurt most: the previous draft correctly protected
`data/fangraphs_imports/` because the production box is Cloudflare-blocked from FanGraphs,
and then left the FanGraphs page cache behind.

**THE RULE, which is what goes in the runbook:**

> Copy everything under `.cache/` that is **not** inside a directory named in
> `prune_cache.SAFE_CACHES`. Pin the copy script to that tuple by importing it, not by
> transcribing it. **115,412 files, 3.77 GB.** Verify with a sha256 manifest.
> Then add a test that fails if any directory under `.cache/` appears in neither
> `SAFE_CACHES` nor the migration allowlist, so the next cache does not fall in the same hole.

3.77 GB is trivial beside a 1.879 GB database and it removes an entire class of judgement.
`deploy/README.md`'s existing seed recipe (`fg_*`, `milb_stats`, `savant_*`, `spotrac_*`,
`fa_*`) stays useful for speed but is **not** a substitute: `milb_stats` and `savant_*` are
in `SAFE_CACHES` (refetchable), while `fg_*` and `spotrac_*` are not, and the README list
misses the point-in-time bundles entirely.

### 1.4.2 The point-in-time bundles, and an honest statement of what losing them costs

`proj_ml.train_cached()` (`proj_ml.py:565-584`) is the no-lookahead twin of the shipped
bundle. `proj_eval.py:219` calls it per base year so historical enrichment never sees the
live model. Its own docstring: "The shipped live bundle (model/proj_lgbm) must NEVER enrich
historical winters: it has seen their outcomes."

Three measured facts:

1. **The bundles are cache files and they were not on the copy list.** 29 files, 756.7 MB,
   at the `.cache/` root.
2. **A cache miss retrains silently.** The code is `if cache.exists(): load` else
   `models = train(corpus, max_label_season)` followed by `joblib.dump` under the same name.
   Nothing warns, nothing raises, and the new file is indistinguishable from the old one.
3. **The key does not digest the corpus.** It is
   `proj_ml_pit_{MODEL_VERSION}_{_SCHEMA_TAG}_{max_label_season}_{qtag}{_war_tag(corpus)}`.
   `_war_tag` is a WAR-provider label, not a content hash. Contrast
   `fa_projection.py:469-471`, which keys on `_corpus_sig(corpus)` and says why in a
   comment: a caller passing a modified corpus was "silently overwriting the production fits
   for every other consumer."

**Where the safety review overstated it, and the correction matters.** The review said a
retrain would produce "a model that has seen more recent labels." It would not:
`proj_ml.train()` takes `max_label_season` and `build_training_frame` filters labels to
`<= max_label_season`; `test_proj_ml.py` has a no-lookahead property test over exactly that.
What a silent retrain actually costs is (a) **reproducibility of a registered verdict**, and
(b) **feature vintage**: the corpus is rebuilt from today's knowledge, so revised historical
stats and a changed player pool move the numbers. That is a served number moving without
being named, which this platform already treats as a failure. It is an evidence loss, not a
label leak. Say it that way, because overclaiming it is how a real finding gets dismissed.

**And a live one nobody had.** All 29 bundles on disk are **bWAR-basis**: none carries the
`_ewar_v2` suffix, while every `proj_ml_frame_*.pkl` on the same disk does. The eWAR v2
epoch (2026-09-03) moved pitcher labels and therefore moved `_war_tag`. So under the current
epoch **every one of those 29 filenames already misses**, and the next Gate-2 corpus
enrichment retrains all of them, on this box, before any port happens. The bundles are still
worth copying (they are the frozen evidence behind the pre-epoch verdicts), but the fix is
not "copy them" alone.

**Fix, three parts, all in Phase 0:**
- Add `.cache/proj_ml_pit_*`, `.cache/proj_ml_frame_*`, `.cache/fa_fits_*`,
  `.cache/ewar_bwar_*.pkl`, `.cache/eta_cohort_c3gate.pkl`, `.cache/fa_corpus.pkl`,
  `.cache/xstats.pkl` to the copy set. The 1.4.1 rule already covers them; name them anyway
  so the manifest can be checked by eye.
- **Make the miss loud.** Gate `train_cached`'s training branch on `EEPHUS_ALLOW_PIT_RETRAIN=1`
  and raise otherwise, exactly as `nightly-build.sh:131` already gates `prospects.db` behind
  `EEPHUS_ALLOW_COLD_REBUILD`. The precedent and the wording are already in the tree.
- **Add the corpus signature to the key**, the way `fa_projection` does, and record in the
  meta which basis (`bwar` / `ewar_v2`) each bundle was trained on.

## 1.5 The models and their evidence

- **311 registry rows**: 54 validated, 130 provisional, 41 unvalidated, 86 deprecated.
  173 served / 138 internal. All 41 unvalidated rows are SERVED.
- **260 rows name an eval artifact; all 260 paths exist; 234 distinct files; zero validated
  rows lack one; `stale: true` on 0 of 311.** This is a clean accountability surface and it
  is the thing most likely to be lost in a rewrite, because it is documentation, not runtime.
- **4 shipped model bundles, all Python joblib pickles**: `model/proj_lgbm/models.joblib`
  (37.7 MB, LightGBM quantile heads at 0.10/0.25/0.50/0.75/0.90),
  `model/tjstuff_plus/lgbm_model_2020_2023.joblib` (3.1 MB, vendored third party with its own
  LICENSE), `model/stuff_plus_aaa.joblib` (1.1 MB), `model/swing_plus/swing_plus_model_v1.joblib`.
  **No `model_to_string`, `save_model`, `dump_model` or ONNX export exists anywhere in the
  repo. An Odin process cannot read any of these four files.**
- **14 of the 34 validated served models are stdlib-only arithmetic.** `hem_plus.py`,
  `sem_plus.py`, `dem_plus.py`, `rem_plus.py`, `consensus.py`, `eta.py`,
  `efv_odds_calibration.py`, `efv_ungraded.py`, `prospect_def_value.py` and the four
  exporters import no numeric library at all. So do `storage.py` (17,309 lines) and
  `build_site.py` (6,584 lines). This is the strongest evidence for the webmaster's premise.
- **The shipped eFV is not scikit.** `prospect_path._fit_ridge` and `efv_model._fit_ridge`
  solve weighted normal equations with `np.linalg.solve`. `efv_model._fit_lgbm_mono`
  (line 1529) is the eval-only challenger and four comments say "never the shipped".

### A served accountability string is false right now, re-confirmed today

`data/model_registry.json` and `MODEL_REGISTRY.md:127` pin `proj_def_prior`'s champion as
`proj_lgbm_v1 with pos_adj_prior (hash 6a691e03ff096a35)`. The bundle on disk,
`model/proj_lgbm/meta.json`, carries `train_hash: 4baf67400e5af498`, `max_label_season 2025`.
Commit `44c089c2` (2026-09-04, "Epoch fallout") retrained it one day after the eWAR label
epoch locked and restamped the blends but not the registry.

It is on the served side too. `data/mlb_projections.json`, `generated_at: 2026-09-18`, ships
an accountability note under `fa_war_paths_decay` reading `Bundle retrained -> hash
6a691e03ff096a35 (was 442428a6498b1426)`. That artifact is published and rendered on
`/projections/` and `/models/`. **A published accountability claim names a bundle that is not
the bundle producing the numbers on that page, and it was regenerated today.**

`test_proj_ml.py:130-148` asserts `meta.get("train_hash")` is truthy and that the champion
string contains "lgbm". It never asserts equality, so any retrain passes with a stale pin.
Fix in Phase 0: assert the bundle hash appears verbatim in every registry row that names the
bundle, and assert the bundle's WAR provider equals `war_source.DEFAULT_PROVIDER`.

## 1.6 The registrations

- **90 `*GATE*.md` files**, of which **84 are named from Python** and are wired into tests.
  These are pre-registrations, not documentation. Deleting them breaks the code that reads
  them. The brief's `.md` undercount (257 vs a measured 375) is largely these.
- **42 dated leaderboard vintages** in `.cache/leaderboard_vintages/`, 2026-07-05 to
  2026-09-18.
- **Epoch constants and the basis fingerprint**: `storage.BOARD_RANK_BASIS_EPOCH` =
  `"2026-09-04"` at `storage.py:4935`, applied strictly-after at `storage.py:4131`. Measured
  on the live DB: `metric_snapshots` holds 316,707 rows over 81 dates, and **269,873 rows
  (85.2 percent) are dropped by that one WHERE clause**. Nothing forces a bump; the
  fingerprint pinned by `test_board_basis_coherence.py` is what forces it.
- **The fit half**: `data/betting_model_eval.json`, `split_date 2026-08-01`,
  `n_gradable 947`, `n_graded 642`, `fit_window.n_games 305` (2026-07-06 to 2026-07-31),
  and a `why_not_graded` string naming training data. 947 - 642 = 305 exactly.

## 1.7 The frontend and the deploy contract

66 files / 4.18 MB under `assets/` (site.css, 2 woff2, 6 icons, ~35 JS modules including the
shared runtime `eephus-nav/gl/hub/account/bg/csv/export/tiers/ui/gfx/diamond`), `vendor/`
2 files, 4 module CSS files, favicon.

Serving contract items that look like implementation details and are not:
- `deploy/publish_paths.txt` (35 entries) is the single include-list for both deploy paths.
- `deploy/data_exclude.txt` (30 entries) is the withhold list, pinned by
  `test_publish_manifest.py`.
- `tools/strip_prospx_comments.py` runs **after** the rsync and **before** precompression,
  against the WEBROOT copy only, and fails open. Wrong order and the `.gz` twin is built from
  the wrong file.
- `gzip -9` precompressed `.gz` twins for nginx `gzip_static`. Without them the boot JSON
  page weight roughly octuples.
- `build_site.py:53` bakes `SITE_ORIGIN = "https://eephus.io"` into every canonical and
  `og:url`. A staging host that serves the built tree advertises the production origin.
  Make it an environment override before Phase 3, or the parallel-run week seeds wrong
  canonicals into crawlers.
- The three hand-maintained pages load `assets/site.css` **unversioned** while generated
  pages get `build_site._asset_ver()`. Stale CSS can outlive a deploy on the two
  highest-traffic surfaces. Fix this in the port rather than carrying it.
- `assets/eephus-config.js` is a **committed blank stub** (tracked; `.gitignore:144`
  documents the change). The port hazard: if anyone fills it in place on the new box, the
  nightly `git checkout -- .` reverts it (section 6.6) and any value in it is published.
  A Supabase anon key is publishable by design; a `service_role` key never is. Config for
  the account layer goes in `/etc/eephus.env` and is injected at build time, or it stays
  blank.

## 1.8 The tests are the publish gate, and they are port scope

**433 `test_*.py` modules, 5,248 test functions**, verified by count today.
`deploy/nightly-build.sh:207` runs `EEPHUS_DEPLOY_RUN=1 python -m pytest -q` and **the rsync
does not run if it fails**. That is the mechanism that has been catching served-number
defects all year.

Two measured weaknesses in that command, both of which Gate A must close (section 2.1):
- `EEPHUS_DEPLOY_RUN=1` is a deliberate relaxation. `nightly-build.sh:204-206`: it "relaxes
  the dev-time exact-hash golden tripwires (xfv.json et al.) to shape checks."
  `test_efv_export.py:762` implements it and seven more comment sites (147, 280, 311, 329,
  346, 369, 593) record which goldens stop being exact. `xfv.json` is one of the nine
  artifacts Gate C names as the product.
- **17 test modules import playwright** and skip themselves when chromium is absent
  (`test_index_html_loads.py:64`). A fresh box with no chromium reports exit 0 with those
  17 modules silently skipped.

**The Odin question, answered so it stops being a question (W-12).** The gate never moves.
Python stays the test runner permanently, even after compute moves to Odin: Odin writes
artifacts, Python asserts over them, the rsync stays behind the same exit code. 433 modules
and 5,248 assertions are not a line item to reimplement, and nothing about a compiled
backend requires it. This costs nothing and it is the webmaster's own suggestion.

## 1.9 The identity adjudication layer, which is not inferable from data

Four hand-built tables plus a repair, none of it recoverable by re-running anything:
`scrapers.py:539 _CANONICAL_KEYS` (8 entries), `scrapers.py _SPLIT_KEYS` (~12, keyed on
`(slug, mlbam_id)`), `consensus.py:333 PLAYER_KEY_ALIASES` (41 entries, applied at read
time), and `tools/repair_identity_residue_2026_08_19.py` (11 of 12 C7 merges, 8 of 10 C4
splits) with its frozen pre-registered case policy. 496 minted fork keys exist in `players`.

Current health, `data/identity_collisions.json` generated 2026-09-18T13:28Z: 9,788 board
rows, 4,680 active, **200 colliding slugs**, held to 7 critical keys and 1 critical active
key, with `c3_unresolved_active: 0` and `frankenstein_records: 0`. The ladder currently
resolves every active row. Any spine change must re-earn those two zeros.

---

# 2. TESTABLE DEFINITION OF DONE

"Everything works as intended" becomes five gates. **All five must pass before any DNS or
traffic moves. A port that changes a served number silently is a failed port even if every
page renders.**

Three rules apply to all five, because the reviews showed the previous draft failing all
three:

- **Every gate needs a positive control.** A gate that only proves an absence (no 404s, no
  SELECT, no diff) can pass by computing nothing. Each gate below states how it proves it
  can fail.
- **No gate may be run before its precondition is asserted.** Preconditions are listed, not
  assumed.
- **A gate that cannot be run is a failed gate**, not a waived one.

## Gate A: the existing suite passes on the new box, against a RECORDED baseline

**Precondition, and it is time-critical: record the baseline TODAY, on the old box, before
anything moves.** Run, and commit the output to `docs/port/BASELINE_PYTEST.txt`:

```
python -m pytest -q                      # dev mode: exact-hash goldens ARMED
EEPHUS_DEPLOY_RUN=1 python -m pytest -q  # deploy mode: goldens in shape mode
```

Record for each: the summary line (passed / failed / skipped / xfailed / errors), the
python version, `pip freeze`, and whether chromium is installed. This is irreplaceable
state and it is not on any copy list. (This specification was produced under a read-only,
no-pytest constraint, so the baseline has not been captured. It is P0.1.)

**The gate.** On the NEW host, against the MIGRATED `prospects.db` and `.cache/`:

1. chromium installed and verified, so none of the 17 playwright modules self-skips.
2. Both commands run. Both exit 0.
3. **passed / skipped / xfailed counts equal the recorded baseline.** Exit 0 alone is not
   the gate; a box that skips 17 modules also exits 0.
4. Positive control: a deliberately corrupted copy of one migrated artifact must make the
   suite fail. Demonstrate it once, then restore.

Standing trap that must come across intact: **pytest pollutes build artifacts**. It must
never run while a regen is writing `data/`, and the conftest guard that restores both clean
and dirty-at-start files is part of the port.

Sub-assertions worth naming because they are the port's specific risks:
`test_publish_manifest.py` (the withhold list, and no withheld file is a `model_registry`
`eval_artifact`), `test_published_payload_hygiene.py` (no build-machine absolute paths in
any published payload, burn-down ledger asserted both directions),
`test_board_basis_coherence.py` (the basis fingerprint), `test_betting_graded_span.py` (the
305-game fit half), `test_leaderboard_vintages.py` and `test_backfill_vintages.py` (the
strictly-before rule and the backfill provenance arms), `test_hof_point_in_time.py`,
`test_identity_residue_2026_08_19.py` plus the 9 other identity tests,
`test_fwar_label_epoch_registration.py` (26 assertions), `test_proj_ml.py`'s no-lookahead
property test.

**Run Gate A twice and say which is which**: once immediately after the state transfer
(this is a copy-integrity check, since 234 of 433 modules read from `data/`), and once after
the Phase 3 rebuild (this is the real one). The previous draft conflated them.

## Gate B: URL contract parity. Presentation is explicitly out of scope.

The owner asked for the port **and** for a "rebuilt frontend with updated CSS to prevent
information overload," in the same sentence. The previous draft's B5 ("every deep-link key
resolves to the same view") forbade the second thing to gate the first. That is how a
category gets widened at 2 a.m., and the first category widened is usually the one hiding a
real number move. So the seam is drawn where the platform already has one: pre-rendered HTML
plus client `fetch()` of static JSON.

- **B1.** Build a manifest of all **12,235** published paths from the current WEBROOT. Every
  path returns 200 with the correct content type on the new host, or is listed in an explicit
  **redirect map** with a 301 to its new location. Zero unlisted 404s. Automated crawl.
- **B2.** Every path has its `.gz` twin and nginx serves it (`Content-Encoding: gzip` on a
  request with `Accept-Encoding: gzip`).
- **B3.** The **30 withheld paths return 404.** This is an assertion, not an absence.
  Explicitly include `star_label_view.json`, `identity_collisions.json`, `scout_reports.json`,
  `grpo_scores.json`, all four `xfv_*_matrix`, all four `xfv_scored*`, and `comps.json`.
- **B4.** No path under `data/baseballamerica_imports/` or any derived BA artifact is
  reachable. **Baseball America is licensed and must never be published.** Enforced twice
  today, by `.gitignore` and by the rsync shipping `data/*.json` at depth 1 only. A new
  publish mechanism must reproduce both halves.
- **B5 (revised).** The 24 deep-link keys remain a **URL contract**: each must load without
  a console error and must not 404. What renders behind them is the rebuild's business and
  is **not** part of port equivalence.
- **B6.** The scout-chunk shard function is identical: for 200 sampled `player_key` values,
  `sum(ord(c)) % 8` maps to the same chunk file and that chunk contains the key.
- **B7 (new).** A byte budget for the boot path, asserted in the same test as the `.gz`
  twins. Measured today: `timeseries.json` 81.17 MiB raw / 9.7 MB gzip-9, against a code
  comment at `prospx/index.html:10656` that still says "~42MB raw, ~5MB on the wire."
  `debuts.json` 70.89 MiB, `inactive.json` 22.20 MiB, `prospx/index.html` 3.09 MiB, and 48
  fetches in that file pass `cache: "no-cache"`. Write a gzip ceiling down; raising it
  requires a written entry. Without a number it doubles again, as it already has.
- **Positive control**: delete one published file on the staging host and assert B1 reports
  exactly that path.

The frontend rebuild is a **separate lane with its own gate**, run after cutover, whose
acceptance is a design and accessibility review plus B1/B2/B7 re-run against the redirect
map. It does not ride inside the port.

## Gate C: served-number equivalence over `data/**`. This is the gate that matters.

Scope: **payloads only** (`data/*.json`, `data/*.js`, and the three per-player directories).
Pages, CSS and markup are Gate B's business.

### C.0 Preconditions. Gate C cannot be run until all five exist.

The previous draft said "freeze the source data on both stacks; neither stack may scrape."
There is no command behind that sentence. Measured: **75 distinct `EEPHUS_*` flags** exist
and none of them is an offline switch; there is no `EEPHUS_OFFLINE`, no `EEPHUS_CACHE_ONLY`,
no global `--no-fetch`. And the trap is that the obvious workaround inverts the gate: with
the network cut, `bullpen_export.guard_nonempty_block` and its 30 call sites take the
**refusal** path by design, keep the previous artifact, stamp it stale and file INGEST RED.
Both stacks then emit the previous artifacts, the differ reports zero differences, and the
gate passes green having proven only that two machines can both refuse.

1. **A real frozen-input mode.** `EEPHUS_CACHE_ONLY=1` makes every fetch helper raise on a
   cache miss instead of going to the network, plus a test that a full build completes under
   it. This is a Phase 0 deliverable (P0.2), not a prose instruction. Record/replay at the
   HTTP helper layer is acceptable and probably easier than touching 31 modules.
2. **A liveness precondition.** On BOTH runs, `data/ingest_health.json` must report zero REDs
   and a non-zero row count for every scheduled source. If either side refused anything, the
   comparison is **void**, not passing. (Today three sources are RED; see Gate E.)
3. **A dependency lock.** There is no lockfile, no constraints file, no hashes and no
   pyproject anywhere in the tree: `requirements.txt` is ten lines and every one is a lower
   bound (`requests>=2.31`, `scikit-learn>=1.3`, `lightgbm>=4.0`, ...), and numpy, pandas,
   scipy and statsmodels are **not declared at all** although statsmodels is
   production-imported at `value_framework.py:3260`. `nightly-build.sh:120` runs
   `pip install -q -r requirements.txt` into a venv, so a venv created on the new host in
   October resolves different versions than the box that produced REF. Freeze `pip freeze`
   from the production box and from the owner's local box, commit both as constraints files,
   pin the python3.12 patch version, and install the new host from the constraints. This also
   protects the joblib pickles, which are version-coupled and can refuse to load across a
   major sklearn or lightgbm bump.
4. **A pinned environment, recorded as a file on both sides**: the full `EEPHUS_*` set (75
   flags; `nightly-build.sh` exports `EEPHUS_MAX_WORKERS=3` and `EEPHUS_SKIP_INPROC_BUILD=1`,
   so the deploy already runs a different path than a dev shell), `EEPHUS_FULL`, `TZ`, OS and
   kernel, python version, `OPENBLAS_NUM_THREADS=1`, `PYTHONHASHSEED=0`. Also pin the branch
   at `nightly-build.sh:166`: a Gate C run on a day that is not the 1st runs the daily path,
   not the monthly, so set `EEPHUS_FULL=1` on both sides and say so.
5. **The same local calendar date on both sides.** `build_site.py:2803` is
   `rnd = random.Random(date.today().toordinal())` feeding a served sample list. Everything
   else in the tree is constant-seeded (`BOOT_SEED`, `MC_SEED`, `_RIDGE_HOLDOUT_SEED`,
   `DEF_PERMUTE_SEED`, `random.Random(71)`); this is the exception. Either run both sides on
   the same date or replace the seed with a constant as a pre-registered NAMED_FIX.

### C.1 Protocol

1. Pick and write down a pin date, with the environment files from C.0.4 attached.
2. Run the full pipeline plus `build_site.py` on the OLD stack under `EEPHUS_CACHE_ONLY=1`
   and `EEPHUS_FULL=1`. Assert the liveness precondition. Snapshot the published payloads.
   Call it `REF`.
3. Run the new stack from the migrated state, same flags. Assert liveness. Snapshot. `NEW`.
4. Diff with a **canonical JSON differ**, not `diff`: parse both, sort object keys, compare
   numbers as decimals at full precision, report every differing leaf path with both values.
5. **Positive control, mandatory**: perturb one known leaf in a copy of `REF` by one unit in
   the last serialized place and assert the differ reports exactly that leaf and nothing
   else. A differ never shown to detect a difference is not evidence.

**Pass condition: every difference falls in a named, pre-registered category, the count in
each category is stated, and there are zero uncategorised differences.**

| category | permitted because | how it is verified |
|---|---|---|
| `TIMESTAMP` | `generated_at` / `built_at` / `checked_at` | leaf key on an allow-list of 12 stamp keys |
| `BUILD_ID` | `?v=` asset hashes, `build_info.json` | path on an allow-list |
| `ORDERING` | a set serialised in a different order | sorted forms compare equal |
| `FLOAT_REPR` | same value, different formatting (1.0 vs 1) | decimal values compare equal |
| `PLATFORM_FP` | genuine floating-point platform difference | see below. **Bounded and capped.** |
| `NAMED_FIX` | a defect the port deliberately corrects | one written entry naming artifact, field, old value, new value, why. Section 10 pre-registers the only ones recommended |

**`PLATFORM_FP` is new and it exists so nobody widens `FLOAT_REPR` under pressure.** The
previous draft justified having no tolerance with "the numbers come from the same Python code
on the same inputs." With no dependency lock that premise was unfunded, and
`np.linalg.solve` in `prospect_path._fit_ridge` and `efv_model._fit_ridge` goes through
BLAS, whose result depends on the OpenBLAS build and thread count. Rules:

- A difference qualifies only if it is **strictly below the last decimal place the artifact
  serializes** for that field (most served numbers are rounded at write time, so a true
  platform difference usually vanishes before serialization; one that survives is suspicious).
- Every `PLATFORM_FP` leaf is **listed individually** in the gate record.
- **Cap: `PLATFORM_FP` may not exceed 0.1 percent of compared leaves.** Above the cap the
  gate fails and the cause is found, because at that volume it is not floating point.
- With `OPENBLAS_NUM_THREADS=1` and matched constraints, the expected count is zero.

There is still **no epsilon** and no per-field tolerance. An epsilon is how a rewrite hides
a bug.

### C.2 Surfaces reported individually, because they are the product

`timeseries.json`, `debuts.json`, `xfv.json`, `xfv_ungraded.json`, `trade_values.json`,
`mlb_projections.json`, `mlb_player_detail.json`, the 5 team leaderboards, `betting.json`
and `betting_model_eval.json`, `hof_board.json`, `management_board.json`, `arbitration.json`,
`fa_class*.json`, `pal.json`, plus a random sample of 500 files from each of the three
per-player directories (fixed seed, recorded).

### C.3 The eval sidecars: FROZEN vs RECOMPUTED, partitioned in Phase 0

The previous draft said all 215 `*_eval.json` must be byte-identical apart from `TIMESTAMP`
because "these are frozen gate results." Measured today: **12 of the 215 are modified in the
working tree right now** (advancement_pace, betting_model, college_translation,
consensus_weight, draft_consensus_weight, editorial, eta, star_odds, stuff_plus_aaa,
team_outlook, xfv_proxy, xfv_scoreboard), and they move because pipeline modules write them
(`proj_export.py:2106` writes `team_outlook_eval.json`, `source_backtest.py:4035` writes
`consensus_weight_eval.json`, `college_translation.py:633`, `efv_proxy.py:159`,
`draft_source_backtest.py:242`). So the rule as written fails on day one, twelve times, for
reasons unrelated to the port, and the first response would be an epsilon.

Measured partition, by scanning every non-test `.py` for a write context around each
filename: **38 of the 215 are written by a non-test production module; 177 have no writer
anywhere in the tree.** That is the starting point, not the answer.

**P0 deliverable: `docs/port/EVAL_PARTITION.json`,** one entry per sidecar, each marked
FROZEN or RECOMPUTED with the writing module and line for the RECOMPUTED ones.

- **FROZEN**: byte-identical apart from `TIMESTAMP`. Any movement is a port failure
  regardless of direction. A registered verdict has been silently re-run.
- **RECOMPUTED**: goes through Gate C's ordinary categories like any other payload.
- A test asserts that no file changes partition without an entry, and that no file is
  missing from the partition. That is **stricter** than the previous draft, not weaker.

## Gate D: leakage controls, verified by assertion

Each is a test, not a review. Items 2 through 5 apply only if a fact store is exposed to a
role at all, which under D2 it is not on day one.

1. `.cache/leaderboard_vintages/` has **42** records on the new host, `provenance` preserved,
   `covers_through` unchanged, and the sha256 of every file matches a manifest recorded
   before the transfer. Verified by re-running the coverage report and matching the live /
   git-backfill / unknown arm counts.
2. **Catalog-driven role check.** Enumerate every table in `core` from `pg_class` and assert
   `has_table_privilege('app_role', oid, 'SELECT')` is false for all of them. Writing this as
   "connect as the role and try one SELECT" passes against the old tables while next month's
   new table is readable.
3. Every as-of function rejects a call with no cutoff and returns nothing dated on or after
   it. Verified with a fixture row dated exactly the cutoff.
4. `REVOKE UPDATE, DELETE` on every observation table, plus
   `ALTER DEFAULT PRIVILEGES ... REVOKE`, verified by attempting `ON CONFLICT DO UPDATE` and
   asserting failure, and by creating a new table in `core` and asserting the role still
   cannot read it.
5. `eval_split`, `basis_epoch`, `basis_fingerprint`, `gate_registration`, `model_bundle`
   exist, are insert-only, and rank history cannot be read without the epoch join.
6. The 305-game fit half is still excluded and still explained:
   `n_fit + n_graded == n_gradable` and `why_not_graded` still contains "training data".
7. Every served payload carries a vintage. 322 of 430 do today; the port may raise that
   number and may not lower it.
8. `test_published_payload_hygiene` ported to whatever writes the response, both directions
   of the burn-down ledger.
9. The 90 gate documents travel with the code and their sha256 is recorded; 84 of them are
   named from Python, so a missing one is also a broken import.
10. `identity_collisions.json` still reports `c3_unresolved_active: 0` and
    `frankenstein_records: 0` on 4,680 active rows.
11. **Positive control**: insert a post-cutoff fixture row and assert an as-of query dated
    before it does not move. Then insert a pre-cutoff row and assert it does. A leakage gate
    that has never been shown to catch a leak is not evidence.

## Gate E: refusal semantics still work, demonstrated

Two refusal levels exist today and both are load-bearing:

- **Report-only**: `ingest_health.json` names a `red` array of scheduled sources that wrote
  zero rows, the nightly prints `!!! INGEST RED` and **deliberately does not fail the
  build**, so one dead source cannot stop publishing the rest of the site.
- **Blocking**: the pytest gate blocks the rsync, so a red suite leaves the live site
  untouched rather than publishing a degenerate one.

Gate E: inject an empty upstream for one exporter and assert the previous artifact is still
served, stamped stale, carrying its own vintage, with a RED filed. Then inject a failing test
and assert nothing publishes. This is the one gate that already had a negative control; keep
it and move it onto the cutover path rather than leaving it last.

**Three sources are RED right now**, `data/ingest_health.json` generated 2026-09-17T20:34Z:
`arbitration_export` (raised with `n_rows: 0` against a last-good 852 rows on 2026-09-16),
`betting_close_capture` (never captured a close snapshot on this box, making CLV
unrecoverable for every slate to date), and `vintage_capture_gap` (last OK 2026-09-07).
**They must be fixed or explicitly carried as known-RED before the port**, both so a fresh
backend is not blamed for them and so it cannot hide them. Note that Gate C's liveness
precondition (C.0.2) cannot be satisfied while they are RED, so this is on the critical path,
not a nicety.

---

# 3. STATIC VERSUS LIVE, QUANTIFIED

Direct answer to: *"the AI made a number of assumptions that we could throw away because most
of the data is static."*

**He is right by file count and wrong by bytes, and the gap is the entire product.**

Top-level shipped JSON, 400 files / 353.33 MB, by last write against 2026-09-18:

| age | files | percent of files | MB | percent of bytes |
|---|---:|---:|---:|---:|
| today or yesterday | 111 | 27.8 | 331.21 | **93.7** |
| 2 to 7 days | 10 | 2.5 | 1.24 | 0.4 |
| 8 to 30 days | 59 | 14.8 | 6.94 | 2.0 |
| 31 to 90 days | 211 | **52.8** | 13.82 | 3.9 |
| over 90 days | 9 | 2.2 | 0.11 | 0.0 |

**72 percent of the files have not changed in a week. 94 percent of the bytes changed
today.** Nine files are 242 MB, 69 percent of the shipped top-level payload, and all nine
rebuild nightly: `timeseries.json`, `debuts.json`, `inactive.json`, `draft_timeseries.json`,
`debuts_lite.json`, `xfv_ungraded.json`, `xfv.json`, `mlb_player_detail.json`,
`trade_values.json`.

**The static majority is frozen by contract, not by neglect.** The 211 files aged 31 to 90
days are 13.82 MB and are overwhelmingly the `*_eval.json` accountability sidecars (7.25 MB),
of which 177 have no writer at all. They are static because a pre-registered gate stamped
them and nothing has re-run the gate. **A backend that "refreshes stale data" on a live
cadence voids every registered result on the platform.** This is the single most important
thing the plan must not silently do.

**Where the measurement is on his side.** The per-player split directories:

| directory | files | MB | rewritten today or yesterday | aged 31 to 90 days |
|---|---:|---:|---|---|
| `pitch_plots/` | 1,789 | 1,003.62 | 240 files / 198.16 MB | **764 files / 231.03 MB** |
| `player_detail/` | 7,147 | 255.02 | 866 files / 102.78 MB | **4,484 files / 41.42 MB** |
| `debuts_full/` | 2,761 | 74.33 | 2,618 files / 73.96 MB (99.5 percent) | 6 files |

**5,248 files and 272 MB are rewritten wholesale every night having not changed in over a
month**, then rsynced on mtime. That is real disk, real deploy time and real bandwidth, and
`data/_artifact_fingerprints/` (10 files) shows the repo already carries the
`{canon_len, sha256}` primitive and simply does not apply it here. **This is his win, it is
measurable, and it touches no served number.** `debuts_full/` is the counter-case at 99.5
percent genuinely fresh, so the rule is per directory, not global.

**Conclusion.** Static-versus-live is a **write-side** finding. The correct action is change
detection on the write path. It is not an argument for changing how bytes reach the browser,
and it is not an argument for refreshing frozen artifacts.

---

# 4. THE LEAKAGE CONTROL PLAN

The owner's requirement is "no data leakage." Nineteen guards implement that today
(`portspec/I3/NOTES.md`, G1 to G19). The structural problem is one sentence:

> **Every one of the nineteen is a property of the CALLER, not of the store.**

`as_of()` is a function someone chooses to call. `season_cutoff` is a parameter someone
chooses to pass. `decision_year < yr` is a line in a loop. The board-rank epoch is a `?`
placeholder in one SQL string in one Python function. They work because there is exactly one
caller, that caller is in version control, and a test reads it. **A live-queried SQL backend
breaks all three conditions at once**: the caller becomes a request-time query string that is
not reviewed, not versioned and not pinnable.

And the database already has the leaky shape. Measured: `prospects.db` is 1.879 GB, 53
tables, **0 views, 0 triggers**. `statlines` is
`(player_key TEXT PRIMARY KEY, season, payload_json, fetched_at)`: one row per player,
overwritten on every fetch, 7,538 rows. `sabermetrics`, `zone_metrics`, `statcast_metrics`,
`pitch_arsenals`, `career_stats` and `career_war` have exactly this shape. `fetched_at` is a
write time, not a valid time, and cannot answer what a row said on 2026-05-14. **The database
enforces nothing. It is a cache with a schema.**

## 4.1 The three primitives. Adopt these or adopt nothing.

The previous draft's snippets were reviewed and three of them were wrong. Corrected here.

**P1. No base-table SELECT for the serving or training role.** Access is through
set-returning functions whose cutoff is **bound to a registration, not chosen by the caller**.

```sql
CREATE FUNCTION api.statlines_as_of(p_split_id text)
RETURNS TABLE (player_key text, season smallint, payload jsonb, basis text)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = ''                                   -- REQUIRED: see below
AS $fn$
  WITH s AS (SELECT as_of FROM reg.eval_split WHERE split_id = p_split_id)
  SELECT DISTINCT ON (o.player_key, o.season)
         o.player_key, o.season, o.payload, 'vintage'::text
    FROM core.statline_obs o, s
   WHERE o.knowledge_date < s.as_of                    -- strictly before
     AND o.season = extract(year from s.as_of)::smallint
   ORDER BY o.player_key, o.season, o.knowledge_date DESC;
$fn$;

ALTER DEFAULT PRIVILEGES IN SCHEMA core REVOKE ALL ON TABLES FROM app_role;
REVOKE ALL ON ALL TABLES IN SCHEMA core FROM app_role;
GRANT EXECUTE ON FUNCTION api.statlines_as_of(text) TO app_role;
```

Three corrections folded in, each of which the reviews caught:

- **`SET search_path = ''` on every `SECURITY DEFINER` function**, with every object inside
  schema-qualified. Without it, a definer function callable by `app_role` is the standard
  schema-shadowing escalation.
- **`ALTER DEFAULT PRIVILEGES`**, because `REVOKE ALL ON ALL TABLES` is a statement about
  the tables that exist at the instant it runs, not a policy. Next month's fact table is not
  covered by it.
- **The cutoff is `p_split_id`, not `p_as_of`.** Making the caller pass a date makes "forgot
  the cutoff" impossible and does nothing about "wrong cutoff". This query passes every
  assertion in the previous draft's Gate D and is textbook feature leakage:
  `SELECT ... FROM api.statlines_as_of(current_date) s JOIN reg.training_labels l USING
  (player_key) WHERE l.label_season = 2025` -- 2026 features against 2025 labels. Binding the
  cutoff to a registered split, and asserting `CHECK (as_of <= train_end)` on every fit row,
  closes it. Keep a `p_as_of` overload for ad-hoc analysis, granted to a human role only,
  never to the training role.

**P2. Append-only observation tables with the knowledge date in the primary key, plus
`REVOKE UPDATE, DELETE`, plus a backdating rule.**

```sql
CREATE TABLE core.statline_obs (
    player_key     text        NOT NULL,
    season         smallint    NOT NULL,
    knowledge_date date        NOT NULL,
    provenance     core.arm    NOT NULL,          -- live | git_backfill | unknown, NO DEFAULT
    attest_sha     text,                          -- commit sha, required for git_backfill
    payload        jsonb       NOT NULL,
    ingested_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (player_key, season, knowledge_date),
    CONSTRAINT knowledge_not_future
        CHECK (knowledge_date <= (ingested_at AT TIME ZONE 'UTC')::date),
    CONSTRAINT no_backdating CHECK (
        (provenance = 'live'         AND knowledge_date = (ingested_at AT TIME ZONE 'UTC')::date)
     OR (provenance = 'git_backfill' AND attest_sha IS NOT NULL)
     OR (provenance = 'unknown'      AND knowledge_date = (ingested_at AT TIME ZONE 'UTC')::date)
    )
);
REVOKE UPDATE, DELETE ON core.statline_obs FROM PUBLIC;
```

`knowledge_not_future` alone forbids only the **harmless** direction. The direction that
leaks is **backdating**: inserting a row learned today under `knowledge_date 2020-01-01`,
which makes today's information visible to every as-of query for 2020. It is
writer-controlled and nothing in the previous draft stopped it. `no_backdating` says a live
row's knowledge date is the day it arrived, and an earlier knowledge date is legal only for a
`git_backfill` row that carries the attesting commit sha, which is the property section 4.3
is actually relying on.

`REVOKE UPDATE, DELETE` is "first write wins" expressed as a grant instead of an
`if path.exists()`. It also makes `INSERT ... ON CONFLICT DO UPDATE` fail, which matters
because that is the idiom every ORM reaches for, and it is exactly how a better-informed row
silently replaces a less-informed one. Add a `BEFORE UPDATE` trigger that raises, for defence
against a superuser migration.

**P3. Registration ROWS with enforcement, not just documents.**

The previous draft's flagship example was invalid SQL: a `CHECK` constraint containing two
subqueries. PostgreSQL rejects it, because a `CHECK` may not contain a subquery or reference
another row. The one concrete demonstration that a pre-registration can be enforced by the
database did not compile. Corrected:

```sql
CREATE TABLE reg.gate_registration (
    gate_id       text PRIMARY KEY,
    doc_path      text NOT NULL,
    doc_sha256    text NOT NULL,
    look_opens    date NOT NULL,
    look_closes   date NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (gate_id, look_opens, look_closes)        -- FK target below
);
CREATE TABLE reg.gate_result (
    gate_id     text NOT NULL,
    look_opens  date NOT NULL,
    look_closes date NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    payload     jsonb NOT NULL,
    FOREIGN KEY (gate_id, look_opens, look_closes)
        REFERENCES reg.gate_registration (gate_id, look_opens, look_closes),
    CONSTRAINT look_window CHECK (recorded_at::date BETWEEN look_opens AND look_closes)
);
```

The window columns are carried onto the result row by foreign key, so the `CHECK` compares
columns of the current row only, which is legal, and the FK guarantees they are the
registered window rather than whatever the writer typed. A `BEFORE INSERT` trigger that
raises outside the window is an equally acceptable implementation; pick one, not neither.

`doc_sha256` makes editing a registration after results exist a detectable event, which is
the rule the fWAR gate currently states only in prose. **Looking early disqualifies** stays a
platform rule regardless: the database can refuse to record a result early, it cannot stop a
human from computing one.

## 4.2 New leak vectors the migration itself creates

| vector | what it does | control |
|---|---|---|
| `ALTER TABLE ADD COLUMN x` then backfill from today's computation across all history | the dark-capture leak, executed as one migration line | `column_available_from` metadata joined by the as-of function; CHECK that rows older than `available_from` have the column NULL |
| `COALESCE(col, 0)` on an as-of path | turns "this column did not exist yet" into a zero | banned in review, made checkable by the per-row `basis` string the as-of function returns |
| Materialized views on as-of paths | caches an answer under a key that omits the cutoff. This is the `_CAREER_CACHE` defect and it is ON BY DEFAULT | forbidden on as-of paths; use partition pruning. Any cache key is `(function, split_id, args)` |
| Prepared-statement plan caching, poolers, application result caches | same defect, three more places it happens for free | same rule; test by inserting a post-cutoff row and asserting a cached pre-cutoff answer does not change |
| Absence becomes silence | with no eligible row the function returns zero rows, the outer join yields NULL, the standardizer reads NULL as the league mean, and the game prices on an implicit average **with no flag anywhere** | as-of functions return `basis` per row (`vintage` / `neutral` / `absent`); the pricing input table CHECKs that `basis = 'absent'` requires a written `override_reason` |
| `SELECT ... WHERE is_active` as pipeline step one | survivorship: pool membership becomes a function of the outcome and the washouts vanish, which is `test_bust_inclusive_frame`'s defect reintroduced as step one | see 4.2.1. **Not** solved by storing first/last |

### 4.2.1 The survivorship fix has to be derived from observations, not from a first/last pair

The previous draft prescribed storing `mlb_played_first` / `mlb_played_last` and exposing
`api.active_as_of(p_as_of)`. **That fix is itself a survivorship leak**, and the review is
right. `mlb_played_last` is a live aggregate recomputed from today's knowledge and then
applied backwards across all history, which is the exact defect the table above files as a
new vector. `active_as_of('2021-06-01')` implemented as
`mlb_played_first <= 2021 AND mlb_played_last >= 2021` asks a 2021 question with a column
that knows who was still playing in 2026, and a pool built that way for a 2021-basis fit
again contains only the players the future kept. The repo already uses the column that way:
`stats.py:1075-1078` filters same-name retireds with `mlb_played_last < 2018`, a today-value.

Correct form:

```sql
CREATE FUNCTION api.active_as_of(p_split_id text) RETURNS TABLE (player_key text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $fn$
  WITH s AS (SELECT as_of FROM reg.eval_split WHERE split_id = p_split_id)
  SELECT DISTINCT a.player_key
    FROM core.appearance_obs a, s
   WHERE a.knowledge_date < s.as_of
     AND a.game_date BETWEEN s.as_of - interval '1 year' AND s.as_of;
$fn$;
```

Activity is derived from the observation table under the cutoff. If a first/last pair is kept
for convenience, version it as `first_as_of` / `last_as_of` per knowledge date and forbid the
unversioned columns to the training role entirely. Chadwick's `mlb_played_first/last` are
fine for a UI filter and are not a training input.

## 4.3 The guarantee the plan would destroy, stated precisely (and corrected)

`.cache/leaderboard_vintages/` holds 42 dated snapshots and is gitignored. Its own docstring
says there is no way to recompute what the leaderboards said on a past date. The partial
rescue, `tools/backfill_vintages.py`, reconstructs vintages from the git blob dates of the
tracked `data/*_leaderboards.json` (24 commits each on `hitter_leaderboards.json` and
`bullpen_leaderboards.json`). That backfill moved the honest betting sample from 41 gradable
games to 414.

**Correction to the previous draft, which overstated the guarantee.** It said "a git blob has
a commit date the writer cannot move backwards." That is false, and the tool itself says so
at `tools/backfill_vintages.py:147-156`:

> `max(author, committer)` and not either one alone. A rebase rewrites the committer date and
> keeps the author date; `git commit --date` does the reverse. The later of the two is the
> first moment this tree can prove the content existed, and proving a LATER existence is the
> safe direction.

So the real property is weaker and more interesting: **both timestamps are movable, the tool
takes the max because moving a vintage later prices fewer games and is therefore the
conservative error.** A database `written_at` column has no equivalent conservative reading
and no second independent witness, which is still a decisive argument for keeping the git
history. State it in that form; the strong form invites a correct rebuttal that discards a
correct conclusion.

Three consequences, all actions:
1. Copy `.cache/leaderboard_vintages/` physically, first, with a sha256 manifest recorded
   **before** the transfer (Gate D1).
2. Keep the leaderboards as tracked files in a repository with continuous history. Do not
   untrack them as part of a JSON cleanup.
3. **Do not delete the old repository.** Make it read-only and keep it indefinitely. Record
   the tip sha of every branch at migration time in `docs/port/ARCHIVE_TIPS.txt`, because a
   force push can rewrite a history that nobody is watching.

---

# 5. THE MIGRATION SEQUENCE

## 5.1 The head-on question: together or in sequence?

**In sequence. Port first on the existing Python, rewrite the backend after.** Three reasons,
each measurable:

1. **Gate C only exists in sequence.** Served-number equivalence works because the same code
   runs on both sides, so any difference is a migration bug. Port and rewrite together and
   every diff has two candidate causes, with no way to tell a migration bug from an intended
   model change. That is no gate at all on the one requirement the owner named explicitly.
2. **A rewrite is a re-registration, not a port.** The standard is that a served number never
   moves without being named and measured. Re-implementing an estimator changes every number
   it produces, by construction. Several affected gates are pre-registered with hard dates
   (handedness restarted post-season, xwOBA and availability around 09-17, schema-4 on
   10-07), and **looking early disqualifies**. Re-earning `proj_horizon_eval.json` requires
   the touch-once 2022-2024 holdout, which has already been touched once.
3. **There is a hard blocker regardless.** Four shipped bundles are Python joblib pickles
   with no portable export anywhere in the repo, confirmed by grep for `model_to_string`,
   `save_model`, `dump_model` and `onnx`. **An Odin process cannot score anything** until
   that export exists, so the rewrite cannot complete even if it starts today.

## 5.2 Phase 0: pre-port work on the old stack. Bigger than the previous draft said.

Entry condition: none. Do these now; they get harder or impossible after the move. P0.1
through P0.5 are the new ones and they are preconditions for the gates, not polish.

- **P0.1 Record the test baseline today.** Both pytest modes, summary lines, `pip freeze`,
  python version, chromium presence, committed to `docs/port/BASELINE_PYTEST.txt`. Gate A is
  unfalsifiable without it and the old box's exact state is irreplaceable once it is
  decommissioned.
- **P0.2 Build the frozen-input mode.** `EEPHUS_CACHE_ONLY=1` raises on a cache miss in every
  fetch helper, plus a test that a full build completes under it. Gate C has no mechanism
  without this. Record/replay at the HTTP layer is acceptable.
- **P0.3 Freeze the dependency set.** `pip freeze` from production and from the owner's local
  box, both committed as constraints files; pin the python3.12 patch version; add numpy,
  pandas, scipy and statsmodels to `requirements.txt` (measured import counts: numpy 244,
  pandas 41, sklearn 35, scipy 35, lightgbm 10, statsmodels 2, and statsmodels is
  production-imported at `value_framework.py:3260`). Install the new host from the
  constraints, never from the floors.
- **P0.4 Partition the eval sidecars.** `docs/port/EVAL_PARTITION.json`, 215 entries, FROZEN
  or RECOMPUTED with the writing module named, plus the test that no file moves partition
  silently. Starting measurement: 38 written by production modules, 177 with no writer, 12
  dirty right now.
- **P0.5 Make a missing point-in-time bundle loud.** `EEPHUS_ALLOW_PIT_RETRAIN=1` gates the
  training branch of `proj_ml.train_cached`; add `_corpus_sig` to the key; record the WAR
  basis in the bundle meta. Precedent and wording already exist at `nightly-build.sh:131`.
- **P0.6 Fix the bundle pin.** Update `proj_def_prior`, `docs/audit/current_state_map.md` and
  the `mlb_projections.json` accountability note from `6a691e03ff096a35` to
  `4baf67400e5af498`, **or** re-run `tools/def_feature_backtest.py` under `ewar_v2` and
  restamp the verdict (D7). Then strengthen `test_proj_ml.py:130-148` from truthiness to
  equality and assert the bundle's WAR provider equals `war_source.DEFAULT_PROVIDER`.
- **P0.7 Stamp the 6 unstamped validated eval artifacts** (`fa_gate1_eval`,
  `value_framework_fitted`, `proj_def_feature_eval`, `surplus_sensitivity`,
  `xfv_lambda_reselect_eval`, `xfv_odds_calibration_slope_eval`) with `generated_at`, the
  bundle hash and the WAR provider. **Today their only vintage evidence is file mtime. A
  fresh checkout destroys it permanently and six validated verdicts become undateable.**
- **P0.8 Fix `efv_il_severity`**, whose `eval_artifact` points at a markdown file and would
  pass any "artifact exists" check. Same pass: the five `eval_artifact` paths pointing at
  `docs/`, `tools/` and `.cache/`, which do not ship, so five accountability claims have
  unreachable receipts.
- **P0.9 Decide the 41 unvalidated SERVED rows** (D8): label them on the page or drop them
  from the first cut. They have no eval artifact, so Gate C has nothing to diff them against.
- **P0.10 Clear or explicitly carry the three open REDs.** Gate C's liveness precondition
  fails while they are RED.
- **P0.11 Export the four joblib bundles to LightGBM text format**, pin a hash of each
  export, and add a test that scores a fixed row set through both and asserts equality. This
  is the gating item for any Odin inference (D1).
- **P0.12 Sort the unsorted directory walks.** 25 `glob()` / `iterdir()` / `listdir()` sites
  in non-test modules iterate unsorted (`bayes_trade_value.py:400`,
  `leaderboard_vintages.py:1982`, `feed_cache.py:197`, `storage.py:16995` and `17007`,
  `run_monthly.py:479`, `org_tendencies.py:184`, and others). NTFS and ext4 return different
  orders, and the owner's local stack is Windows. One `sorted()` each, no number moves, and
  Gate C's `ORDERING` bucket stays small enough to read.
- **P0.13 Make `SITE_ORIGIN` an environment override** so the parallel-run host does not
  advertise production canonicals.
- **P0.14 Version `assets/site.css` on the three hand-maintained pages.**
- **P0.15 Enumerate the 27 beta-only commits** (`git log --oneline HEAD..origin/beta`) and
  classify each: box-side ops fix to re-apply, superseded, or abandon (D6).
- **P0.16 Disclose or fix the two-scale `tj_stuff_plus`** in `data/pitch_plots/` (section 9.2
  and D10). This is a live served-number defect; it must be decided before the port so it is
  not confused with one.

## 5.3 Phase 1: seed the new repository

Entry: P0.15 complete. Section 6 has the exact commands.

## 5.4 Phase 2: state transfer. Nothing else can start before this.

Entry: new remote configured, Phase 1 pushed, sha256 manifests recorded on the old box.

- **P2.1** `.cache/leaderboard_vintages/` (42 files), copied first, verified against its
  manifest and by matching the coverage report's live / git-backfill / unknown arm counts.
- **P2.2** The cache, by the **rule in 1.4.1**: everything under `.cache/` not inside a
  `SAFE_CACHES` directory. **115,412 files, 3.77 GB**, verified by sha256 manifest. Name
  these explicitly in the runbook so the manifest can be eyeballed: `proj_ml_pit_*.joblib`
  (29 / 756.7 MB), `proj_ml_frame_*.pkl` (6 / 64.9 MB), `fa_fits_*.pkl` (219 / 7.5 MB),
  `ewar_bwar_{bat,pit}.pkl` (2 / 64.4 MB), `fg_*` (271 / 94.2 MB), `spotrac_*` (89 /
  77.0 MB), `leaderboard_vintages/`, `odds/`, `betting/`, `futures/`, `pbp_corpus/`,
  `bref_register/`, `efv_backup/`, `draft_history/`.
- **P2.3** `prospects.db` migrated **as a seed, not a rebuild.** The nightly already refuses a
  cold rebuild for this reason (`nightly-build.sh:122-137`): the 2021-plus snapshot history
  is not re-scrapable, and a cold build silently produces a plausible-looking site with wrong
  FV history, consensus and surplus. That is what production served after 2026-07-11.
- **P2.4** `data/fangraphs_imports/` (33 MB drop folder) and the tracked
  `data/fangraphs_articles/*.csv` carve-out. **FanGraphs is the largest single grade source
  (24,503 of 65,067 snapshots, back to 2017-02-15) and the production box is
  Cloudflare-blocked from fetching it.** Lose the drop folder and the largest grade source
  goes dark with no error. The `.cache/fg_*` pages in P2.2 are the other half of this.
- **P2.5** `data/baseballamerica_imports/` (312 files, 9.5 MB), transferred and confirmed
  unpublishable at both enforcement points (Gate B4).
- **P2.6** Secrets. `/etc/eephus.env`, root-owned, chmod 600, **outside the checkout**,
  because the deploy does `git checkout -- .` and would destroy a secrets file inside the
  repo nightly. Measured precedent: `nightly-build.sh` once had zero references to
  `EEPHUS_ODDS_API_KEY`, so run_daily step 9e **had never once fired on the box** while
  `betting_status.json` reported `configured: true` alongside `n_snapshots_cached: 0`.
- **P2.7** Run **Gate A (copy-integrity pass)** here, before any rebuild.

## 5.5 Phase 3: run the existing stack on the new host, unchanged

Entry: Phase 2 verified, Gate A copy pass green.

Run `run_monthly.py` and `build_site.py` as they are, from the migrated state. Target: the
last full monthly took **3,672 seconds (61.2 minutes) over 62 steps**, dominated by betting
model context refit (926.8 s), approximate zone metrics (673.9 s) and the timeseries export
(295.7 s). A materially different runtime is a signal, not a nuisance.

Then run **Gate A (rebuild pass)**, **Gate C**, **Gate D** and **Gate E**. Gate C is the
point of this phase.

Carry the eight timing constraints as explicit scheduled-job requirements with their
measurements attached, so nobody moves a cron without reading the number behind it:

- **T1.** Open odds capture at `10 13 * * *` UTC, chosen to be more than three hours before
  **16:16 UTC, the earliest first pitch on record in the cache**. Measured 2026-09-05: 11 of
  22 snapshots landed after their own slate's first pitch.
- **T2.** Close capture every 15 minutes all day with **`TZ=UTC` in the crontab,
  load-bearing**. A windowed cron in an undocumented box timezone is why CLV was never
  gradeable.
- **T3.** `decide()` depends on `data/fantasy.json` carrying tonight's schedule, across two
  different schedulers.
- **T4.** Step 9d-park must run before anything prices the slate.
- **T5.** The nightly leaderboard vintage snapshot: a missed night is missed permanently.
- **T6.** The paid-credit ledger is checked **before** the request, not after (500/month,
  allocations open 100 / close 100 / props 120 / futures 30, 150 held in reserve).
- **T7.** Cron runs with almost no environment and a missing key is a silent no-op.
- **T8.** Every cron entry point exits 0 on a no-op, because one that raises becomes a retry
  loop that bills.

## 5.6 Phase 4: cut over

Entry: Gates A through E all pass.

Serve from the new host in parallel for one week, running Gate C nightly against the old
host under the same pinned environment. Then move DNS. Keep the old box running and untouched
for 30 days, and keep the old repository read-only forever.

## 5.7 Phase 5 onward: the backend program, one lane at a time

Entry: Phase 4 complete and stable, and each lane has its own pre-registration.

Ordered by value over risk:

1. **Change detection on the per-player split directories.** 5,248 files / 272 MB per night,
   using the existing `_artifact_fingerprints` primitive. Touches no served number. This is
   the webmaster's finding and it is free.
2. **The `pitch_plots` re-encoding.** Larger than lane 1 (section 9.2). Split into the free
   half and the pre-registered half.
3. **The database as store of record, with a publish step.** Move authoring into the database,
   run as-of queries in a build job, write vintage-stamped content-hashed bundles, serve the
   bundles. Adopt P1, P2, P3 from section 4 at this point. The frontend already fetches JSON
   over HTTP, so nothing changes for the user.
4. **Chadwick as the crosswalk**, with the coverage measurement gating it (D5).
5. **Go or Odin inference against exported LightGBM text models**, with the exact equivalence
   test from P0.11.
6. **Estimator replacement, one module at a time, each behind a registered equivalence gate.**
   `docs/EFV_GATE_STANDARD.md` already supplies the floors: MDE95 0.0440 hit / 0.0436 pit on
   the pooled pair-weighted basis, 0.02 equivalence margin, seed convention 20260807.
7. **Training-stack replacement.** Last, or never.

---

# 6. THE GIT PROBLEM

## 6.1 Verified state, re-measured today

| fact | measured |
|---|---|
| working branch ahead of `main` | 346 commits, 0 behind |
| `main` vs `origin/main` | level. main IS pushed to the old remote |
| working branch vs `origin/efv-conviction-2026-08-08` | **159 ahead, 0 behind. The branch is partly pushed already** |
| `git merge-base HEAD beta` | empty. **No common ancestor** |
| `beta..HEAD` / `HEAD..beta` | 1,644 / 27 |
| remotes | `origin https://github.com/aiyer9175/eephus.io.git` only. **New remote not configured** |
| `.git` | 818 MB |
| local `beta` vs `origin/beta` | `14e0e328` (2026-07-19) vs `03c1428e` (2026-08-01, a rollback commit). **The local beta is not the deployed beta** |

Two corrections to the brief: the working branch is **not** wholly unpushed (159 of 346 are
unpushed on top of a remote branch holding the rest), and the per-extension counts are
understated. Measured: **1,166 `.py`** (brief said 945), **375 `.md`** (said 257), 628
`.json`, 64 `.html`, 58 `.js`, 8 `.css`. The 2,533 total, the 818 MB and the 560 tracked data
files are correct. **Do not size the port off the per-extension breakdown**, and note the 118
extra `.md` are mostly the 90 `*GATE*.md` pre-registrations, 84 of which are named from
Python.

## 6.2 Recommendation: seed the new repository with the FULL history of the working branch

```
git remote add eephus https://git.eephus.io/eephus/eephus.git
git push eephus efv-conviction-2026-08-08:main
```

**Push the complete history. Do not start a clean repo and do not filter the blobs.** The
reason is section 4.3: `tools/backfill_vintages.py` reconstructs 10 of the 42 leaderboard
vintages from the git dates of the tracked `data/*_leaderboards.json`. A filtered history that
drops data blobs drops the evidence, and a filtered history that keeps exactly those files is
more fragile than pushing everything once. 818 MB is a one-time cost.

**Also: do not delete the old repository.** Make it read-only, keep it indefinitely, and
record every branch tip sha at migration time.

## 6.3 What to do about `beta`

`beta` has no common ancestor with the working branch. There is no merge and no rebase. **The
port is a tree replacement.** The 27 beta-only commits are box-side operator fixes
(`deploy/WEBMASTER.md` section 1 says the box tracks `beta`, delivered by a single
`Sync beta to main@<sha>` full-tree snapshot commit onto an orphan branch).

1. `git log --oneline HEAD..beta` against **`origin/beta`**, not local `beta`, which is 13
   days older and is not what is deployed.
2. Classify each of the 27 as (a) box-side ops fix to re-apply by hand, (b) superseded, or
   (c) abandon. Write the classification down; it is an owner decision, not an engineering
   one.
3. Push `beta` to the new remote as `archive/beta-2026-08-01` so the history is retrievable,
   and never merge it.

## 6.4 The old remote

Keep `origin` configured as a second remote named `archive`, push nothing more to it, leave it
fetchable. `main` is already level there, so nothing is lost.

## 6.5 The data history going forward

Push the full history now, and from the first commit on the new remote stop tracking the
artifacts that are purely derived. The `.gitignore` already documents which ones and why.

## 6.6 The trap that will bite whoever regenerates `.gitignore`

`nightly-build.sh` step 3 runs `git checkout -- .` before pulling. **Any file that is both
tracked and appended-to on production is destroyed nightly with no error anywhere.** This
already happened: a betting record row appended on production at 21:00 was reverted to the
committed `[]` at 03:10, `load_record` read the restored file as "the record is empty", and
`check_append_only` then waved the same one-row proposal through as a legal append. The
immutability check held on every write and the ledger still could not survive a night.

The resolution pattern must be reproduced for every accruing artifact: **source of truth in
`.cache/` (untracked, append-only, chain-hashed); `data/*.json` is a derived re-render written
by every build; losing the derived copy costs nothing.** Applied today to
`betting_record.json`, `betting_clv.json`, `betting_settlement.json`, `betting_shadow.json`,
`futures_ledger.json`, `betting_learning.json`.

The worst state is **untracked AND unignored**: `checkout -- .` cannot touch it, but a single
`git add -A` tracks it and re-arms the identical defect. Two files have landed there already.
**A port that regenerates `.gitignore` from scratch re-arms this whole class.** Carry the
existing `.gitignore` forward with its comments, which are the incident log.

**Note before migrating: `.cache/betting/record.jsonl` is 0 bytes** (mtime 2026-09-07) and
`data/betting_record.json` is `[]`. The public betting record's source of truth is empty.
Someone should know that before it is migrated as-is and before anything on `/betting/`
claims a record.

---

# 7. CORRECTIONS TO THE WEBMASTER PLAN

## 7.1 Where he is right, with the evidence

**R-1. A name slug is the wrong primary key and he is correct to want it replaced.** This is
the strongest structural point in his plan and the evidence is in the repo, not in theory.
`players.player_key` is a normalized name slug from `scrapers.py:516 normalize_key()`. The
cost, measured: **200 colliding slugs on a 9,788-row board**, 496 minted fork keys, a 41-entry
hand alias table, a 12-route batch repair, and **2,853 of 10,623 players (26.9 percent) with
no MLBAM id at all**, 103 of whom carry a 2026 board snapshot and are being served right now.
The served consequence has a dollar figure: Jack Natili reached the served board **twice**, at
ranks 155 and 320 with grades 45 and 42, surplus double counted at $16.7M plus $3.8M. Moving
to a stable integer spine is the highest-value structural change on the table.

**R-2. Chadwick is the right shape of artifact.** A crosswalk keyed by a stable internal id
carrying `key_mlbam`, `key_retro`, `key_bbref`, `key_bbref_minors`, `key_fangraphs`,
`key_wikidata`. That is exactly the join table this platform has been hand-building in three
Python dicts. Today it is the **last resort** resolver (`stats.py:1019-1025`), exact-match
only, behind two other paths. Promoting it to the key table and storing all ten columns
removes a class of work.

**R-3. Retrosheet incorporation is a real gain and I have no counter-argument.** The platform
has **zero** Retrosheet references today. `key_retro` is the clean route in. HoF, management
and arbitration all reason over history and `career_war` holds only 2,679 rows.

**R-4. "Most of the data is static" is true and it is his best observation.** 322 of 430
served JSON carry a vintage stamp and the nightly pipeline is the only writer. Fourteen of the
34 validated served models are stdlib-only arithmetic over committed JSON. `storage.py`
(17,309 lines) and `build_site.py` (6,584 lines) import no numeric library at all.

**R-5. The measured win that follows from R-4 is real and nobody else found it.** 5,248
per-player files / 272 MB rewritten nightly having not changed in over a month, and
`data/_artifact_fingerprints/` already carries the primitive to fix it.

**R-6. One store of record is right.** State is currently split across a 1.879 GB SQLite file,
560 tracked JSON artifacts, and a 56.84 GB `.cache/` tree holding the irreplaceable vintage
archive **on one box**. Consolidating is correct.

**R-7. Removing scikit is more achievable than it sounds.** Measured: **87 of 104 sklearn
importers live in four research trees that do not serve the site** (swing-plus 36,
playing-time-model 33, defense-plus 11, milb-decision-plus 7). Inside `prospect-tracker` only
17 import it, 9 of those `tools/*_lab.py`. That leaves 8 core modules, and one of them
(`xwoba.py`, six top-level sklearn imports) is **imported by nothing**. The imports
concentrate: isotonic 13, ensemble 9, linear_model 6. Isotonic and linear/logistic are a few
hundred lines to reimplement exactly.

**R-8. Go for serving and Odin for compute is a reasonable split**, and "Odin has no http
package yet" is honest engineering rather than hand-waving.

**R-9 (new, conceded to the webmaster review). Some of this machinery is not earning its
place, and the platform should stop defending all of it.** Section 9 is that list, with
measurements. The biggest item in it, a 528 MB literal duplication inside the single largest
served directory, was found by attacking the platform rather than the plan.

## 7.2 Where the plan breaks, with the file and the measurement

**W-1. "The site LIVE PULLS data" contradicts "most of the data is static", and it is the
single change that costs the most.** It costs three guards outright:

- **Refusal has no live equivalent.** `bullpen_export.guard_nonempty_block` (line 208) keeps
  the previous artifact when a fetch returns empty, stamps it stale carrying its own vintage,
  and files RED. A live query returns zero rows and the page renders empty. The outage this
  was built for (2026-08-05) blanked 30 team rollups and made Offense+ read a flat 100 for
  every opponent on the streamer board and every DFS matchup, and **nothing raised**, because
  "no teams" and "no data yet" are the same value to every consumer downstream. It is called
  from 30 sites across 7 exporters.
- **Frozen stamped artifacts disappear.** 322 stamped artifacts become unstamped query
  results. "What did the board say on 2026-08-14" stops being answerable the moment a base row
  updates. Two readers ten seconds apart can see different numbers with no way to say which.
- **The fit half loses its anchor.** A fit/eval split is a property of an analysis, not of a
  row, and there is no natural column for it.

Today there is zero request-time computation: pre-rendered HTML plus client `fetch()` of
static JSON behind nginx `gzip_static`, with at least 12 modules writing via `os.replace`.
**Recommendation: keep the publish step.**

**The one place the previous draft asserted a preference instead of a measurement** was
"live querying buys nothing measurable." The safety review flagged the betting slate as the
counter-example. Measured answer: the betting jobs write to `.cache/odds/`, and **nothing
publishes between nightly builds** -- the only rsync in the tree is at
`nightly-build.sh:224`. So the served slate is already up to 24 hours behind the capture, and
the capture itself is bounded by the paid tier (3 credits/day open, 3/day close, against 500
a month with 150 held in reserve), not by the serving model. A live database read would show
exactly what the last 15-minute cron wrote, which **a lightweight incremental publish shows
identically**, without giving up refusal, the vintage stamp or the fit-half anchor. So the
correct claim, and the one the spec makes, is: *live querying buys nothing that a 15-minute
incremental publish does not also buy.* If the betting page needs intraday freshness, build
the incremental publish (a few artifacts, seconds to write, same gate), not a live read.

**W-2. "Pull out all active players using SQL" is a survivorship leak at step one.** `active`
is current state. Selecting the pool by it makes membership a function of the outcome and
silently removes exactly the players a grade got most wrong. `test_bust_inclusive_frame.py`
exists because this shipped once: `_is_vintage_matched` required a debut year, so a prospect
who never reached the majors could not enter the flagship head-to-head frame, and every
published accuracy cell was measured on players who all made it. **The fix is section 4.2.1,
and it is not "store first and last"** -- that pair is itself a today-value applied backwards.
Derive activity from appearance observations under the cutoff.

Separately, **"active players" is not the served population.** `inactive.json` is 22.20 MiB,
`debuts_full/` is 2,761 graduates, `hof_board.json` is every ten-season player, and
`pipeline_vintages.json` reaches back to 2011. An active-only extract drops roughly a third of
the served payload.

**W-3. Chadwick cannot be the ACTIVE-PLAYER register, which is the one job the plan gives
it.** The live register is `stats.py:242 PlayerIndex`, built **daily** from MLB StatsAPI
`/sports/{id}/players` over sport ids (1, 11, 12, 13, 14, 16) for the current and prior
season, matched on name plus birth-year plus active flag plus position class. Its freshness is
load-bearing: `snapshots` holds `draft_signing` rows dated **2026-09-18, today**. Chadwick's
register republishes on a lag measured in weeks. If the active list comes from Chadwick the
board goes stale by exactly that lag and the draft and IFA pipelines (7,889 draft plus 3,802
international_fa acquisitions) lose their newest cohort. The failure mode is in the source,
`stats.py:1075-1078`: Chadwick returned a pitcher born in 1974 for a current draft prospect.
**The register is comprehensive backwards; this site's population is forwards.**

**W-4. `key_fangraphs` does not cover the FanGraphs ids this platform actually uses.**
Chadwick's `key_fangraphs` is the numeric MLB-level playerid. FanGraphs issues
minor-league-only prospects an id in the `sa#######` namespace and the pipeline keys on it
(`fangraphs_csv.py:1159 _disambiguate_key`, e.g. `julio_rodriguez__sa3007992` for the SFG SIRP
against PID 23697 for the Mariners CF). Measured: **96 `__sa` keys in `players`, 136 snapshots
on them, and only 26 of the 96 carry an MLBAM binding. Chadwick will resolve none of the other
70.**

**W-5. Chadwick's minor-league coverage is unmeasured exactly where this platform lives.**
`key_bbref_minors` comes from B-Ref's minor league register, which lags the season and is
sparse for complex-league, DSL and just-signed IFA players, which is this platform's whole
product (3,802 international_fa rows, 3,261 draft_players, modeled level order
AAA > AA > A > A+ > CPX > DSL). **I could not measure this: no network, register not in the
tree.** This is an assumption the port must measure, not a proven defect. Make it a gate:
join all 10,623 `players` rows against the register and report unmatched broken out by level
and by acquisition method, **with the threshold written down before the join is run** (D5).

**W-6. Chadwick does not adjudicate. It maps.** It will not tell you that `dom_keegan`'s own
2026 snapshots flip between TBR and BAL inside one cycle, or that one `players` row provably
mixes two humans because the stored birth date implies age under 16.0 at the key's earliest
snapshot. Those are the 7 critical keys. **Chadwick shrinks the collision surface; it does not
empty it**, and the seven detectors (C1 through C7) plus the three hand tables must be ported
regardless.

**W-7. "550k people back to the early 1900s" is a scale claim, not a benefit.** The board is
9,788 rows and `players` is 10,623. Loading 550k rows is fine and cheap. The difficulty is the
2,853 players with no MLBAM id and the 200 colliding slugs, and 540k retired players do not
help with either.

**W-8. The pipeline diagram has no gate in it.** Scrape -> model -> update database -> serve
is missing the fit half that is never graded, the forward-chained evaluation, the
pre-registration written before the numbers exist, and the point-in-time bundles. 260 eval
artifacts and 54 validated verdicts exist because of those. The diagram needs a **gate stage
between "run our own models" and "update database", with a refusal edge back to "keep the
previous artifact".** `proj_eval.py:219` trains a separate bundle per base year via
`proj_ml.train_cached(corpus, B-1)` precisely so historical enrichment never sees the live
model, and `fa_market.py:468-470` says "the live bundle must never serve" historical winters.
If the flow is "run models, write numbers to the DB", **the point-in-time distinction has
nowhere to live.** See section 1.4.2 for what that distinction is actually worth and where it
is already leaking on the current box.

**W-9. Removing scikit understates the job, and LightGBM is the harder half and is not
named.** Import sites: **numpy 244, pandas 41, sklearn 35, scipy 35, lightgbm 10,
statsmodels 2.** scikit is fourth, not first. Four shipped bundles are LightGBM,
`requirements.txt` pins `lightgbm>=4.0`, and there is no portable export. And the manifest is
wrong: it does not declare numpy, pandas, scipy or statsmodels at all, so a dependency list
copied from that file will be incomplete (P0.3).

**W-10. Odin has no HTTP client either, not just no server.** 31 modules make outbound calls
against 20-plus hosts, several behind Cloudflare, with rate limits, retry and backoff, and TTL
caching. **Port compute to Odin and keep ingest in Python or Go.** Do not port ingest first.

**W-11. "Throw away the AI's assumptions" is half right, and the half that is wrong is
expensive.** Genuinely disposable: sklearn in the research trees, the JSON sprawl, the 82 MB
payloads, `xwoba.py`, and the items in section 9. **Not disposable: anything that is a gate
RESULT.** Statcast features into projections was tested and rejected
(`proj_horizon_eval.json`, `challenger_blocks.dev_statcast_v2_rejected`); the dedicated mean
head was rejected twice; defence is rejected in prospect xFV and validated in MLB projections,
on purpose, for a stated reason. The 86 deprecated rows are that ledger. **Rule for the port:
before discarding an assumption, check whether it has a registry row. If it does, discarding
it is re-running a banned experiment.**

**W-12. The 433-test publish gate. RESOLVED, and it was a false choice.** Python stays the
gate runner permanently; Odin writes artifacts and Python asserts over them. 433 modules and
5,248 assertions never get reimplemented. See section 1.8.

**W-13. The branch reality is a bigger problem than the backend and the plan does not mention
it.** Section 6.

**W-14. The site builder is also a data producer.** `build_site.py` writes
`data/efv_alerts.json` (line 6574), `data/swing_delta.json` (6533),
`data/mlb_current_lines.json` (6534), read-modify-writes `data/wire_fv_first_seen.json`
(1295), and touches `timeseries.json`, `debuts.json`, `xfv.json`, `mlb_projections.json` and
`positional_fit.json`. **Splitting "Go frontend serving" from "Odin backend pipeline" along
the obvious seam silently stops producing five served artifacts.**

## 7.3 The one-sentence correction that preserves his design

Adopt Chadwick as the **crosswalk** table (`chadwick_id` to
`{key_mlbam, key_retro, key_bbref, key_bbref_minors, key_fangraphs, key_wikidata}`) with
**`key_mlbam` as the internal primary spine** and **StatsAPI as the live active register**;
keep **`player_key` as the public URL key and a legacy alias column**, not a primary key; and
migrate the 496 fork keys plus the 41 alias routes as explicit rows in an adjudication table
the backend reads **at join time**, preserving the read-time-undo property that
`consensus.py:366-372` argues for on the record:

> Fixed HERE rather than by re-keying the database on purpose. This table canonicalises at
> READ time, so the merge happens every rebuild and is undone by deleting these four lines.
> The alternative, a DB key remap, cannot be cleanly undone, and the survey found it would
> also have thrown on 23 of 30 rows, because both keys hold snapshots on the same dates under
> PK(player_key, snapshot_date).

---

# 8. THE SECOND DATASTORE NOBODY HAS MENTIONED

`supabase/migrations/0001-0005` create `profiles`, `boards`, `threads`, `comments`, `votes`,
`reports`, `polls` and `bets` with RLS. The account and forum layer is inert without config
(`assets/eephus-config.js` ships as a committed blank stub), but the schema is real and it is
user-generated content, which is the one class of data on this platform that cannot be
regenerated from a scrape.

Port requirements, none of which are in the webmaster plan:
- Decide whether the account layer moves at all (D11). If it does, the Supabase project,
  its RLS policies and its data are a **separate migration with its own backup**, not part of
  the file transfer.
- If it does not move yet, keep the stub blank and assert the pages still render inert.
- Never place a `service_role` key in a tracked file. The anon key is publishable by design;
  RLS is the control, so the RLS policies must be verified on the new project before any real
  key is installed.

---

# 9. WHAT CAN GENUINELY BE THROWN AWAY

The webmaster's premise deserves a real answer, not a defence of everything. These are
measured and they are droppable. Two of them are bigger than anything in the port itself.

## 9.1 Dead weight, no argument needed

- **`prospect-tracker/xwoba.py`**: six top-level sklearn imports, **imported by zero modules**
  (verified by grep for `import xwoba`). The two apparent hits elsewhere import
  `xwoba_projection_blend_lab`, a different file. Delete it and one sklearn surface goes away.
- **87 of 104 sklearn importers** live in four research trees that never serve the site. They
  do not need to move to the new host at all.
- **The 86 deprecated registry rows**: move to an archive artifact, off the served registry.
  They are a ledger, not a product surface. Keep the ledger; stop shipping it in the same file.
- **`data/player_news.json`**: 4 bytes, an empty object, last written 2026-06-12, fetched on
  every board load at `prospx/index.html:11015`. Retire it or fill it.
- **`SITE_MAP.md` as a checklist**: wrong in both directions (section 1.2). Keep the generator
  as a hint, never as a contract.
- **The 5 `eval_artifact` paths pointing at `docs/`, `tools/` and `.cache/`**: unreachable
  receipts. Fix or drop the claim (P0.8).

## 9.2 `data/pitch_plots/` is 57 percent of the served payload and about half of it is a
literal duplicate. This is the largest single finding in this document.

Measured today across **all 1,789 files, 957.1 MiB** (not a sample):

- **1,179 files (65.9 percent) are single-level, and their `top.points` array is
  byte-identical to their one level split.** Those files are **55.2 percent of the corpus
  bytes**, about 528 MiB of literal duplication. The cause is in the source and is already
  documented as a memory fix: `statcast_metrics.py:1104-1106` reuses the aggregate object for
  a single-level player instead of recomputing it, which removed the second allocation but
  left both copies in the serialized payload.
- The per-point encoding is the other half. Each of up to 900 rows carries `venue_name`
  "American Family Field", `pitch_name` "Curveball" and
  `tj_stuff_plus_model` "tjstuff_plus_2020_2023_lgbm" (hoisted to one view-level `stuff_model` on 2026-09-23; before that, one constant of roughly 30 KB per
  player), and full double-precision physics (`extension 5.594834799829195`,
  `ax -4.83044697864399`) for values that render as a dot in a scatter plot.
- Re-encoding one real file (columnar arrays, a string lookup table, 3-decimal rounding):
  **965,236 -> 101,160 bytes raw (9.5x), 170,838 -> 27,423 bytes gzip-9 (6.2x)**. Corpus
  extrapolation: about 1,004 MB down to under 110 MB, under 30 MB on the wire.

**Split the lane in two, because only one half is free.**

- **Free half**: for the 1,179 single-level files, stop serving `top` and have the client read
  the single split. Zero numbers change; the bytes are identical today.
- **Pre-registered half**: rounding is a served-number change even at 3 decimals. It goes
  through Gate C as **one** `NAMED_FIX` with a written per-column rounding rule. That is the
  platform's own rule applied honestly, not an exemption from it.

**And the half nobody knew about, which is a live defect and not an optimisation.** For
multi-level pitchers, `top` is **not** a view of the splits:

```
multi-level files                                                   610
  top.points is a subset of the union of the splits                 588
  top.points is NOT a subset                                         22
files where a matched pitch (same game_pk, date, pitch_type, velo)
  carries a DIFFERENT tj_stuff_plus in `top` than in its split      609 of 610
  affected points                                                58,270
  delta: min -72.0, median +0.10, max +52.7
```

The mechanism is exact and it is defensible in itself. `statcast_metrics._finalize_pitch` is
called once over all points and once per level bucket, and
`mlb_stuff_plus.score_pitch_points` computes `_primary_fastball(rows)` from whatever row set
it is given. Pooled across levels, the reference fastball differs from the per-level reference
fastball, so the same physical pitch scores differently. That is a real basis difference, not
a bug in the arithmetic.

**What makes it a defect is that neither number is labelled.** `prospx/index.html:45177-45186`
picks the level split when a level is selected and falls back to `top` otherwise, so a user
toggling from "main" to "A" sees Stuff+ move on the same pitch with nothing saying the
baseline changed. The platform's own standing rule is *a number is never shown on a scale it
was not computed on*. This has to be decided before the port (D10), not silently carried
across and not silently fixed.

## 9.3 The boot payload has doubled past its own documented budget

`prospx/index.html:10656` still says `timeseries.json` is "~42MB raw, ~5MB on the wire."
Measured: **81.17 MiB raw, 9.7 MB gzip-9**, with `debuts.json` at 70.89 MiB and 48 fetches in
that file passing `cache: "no-cache"`, so a repeat visitor re-downloads it. The previous draft
asserted only that a `.gz` twin exists. Gate B7 turns the budget into a number that has to be
argued up in writing. This is squarely the frontend rebuild's lane and it is the strongest
evidence for the owner's own "prevent information overload".

## 9.4 What is NOT droppable, restated because it will come up again

The 90 gate documents (84 named from Python), the 215 eval sidecars, the 42 vintages, the
withhold list, the refusal paths, the fit half, the identity adjudication tables, and the
`.gitignore` comments. Every one of them is either executable or is the only surviving
evidence for a published claim. The test for "is this AI ceremony or a gate result" is
mechanical: **does a registry row, a test, or a published page point at it?** If yes, it is a
result, and deleting it is re-running a banned experiment.

---

# 10. PRE-REGISTERED `NAMED_FIX` ENTRIES

Only these are authorised to move a served number during the port. Anything else is a gate
failure. Each needs its one-line entry filled in before the Gate C run, not after.

1. **`proj_def_prior` / `fa_war_paths_decay` bundle hash** (P0.6). Artifact:
   `data/model_registry.json`, `MODEL_REGISTRY.md`, `data/mlb_projections.json`. Field: the
   accountability string. Old: `6a691e03ff096a35`. New: `4baf67400e5af498` (or the re-run
   verdict under D7). Why: the pinned hash is not the bundle producing the page's numbers.
2. **The six unstamped eval artifacts gain `generated_at`** (P0.7). This adds a key; it moves
   no value. Why: file mtime is the only vintage evidence they have and a fresh checkout
   destroys it.
3. **Date-seeded sampler** (C.0.5), if the owner chooses the constant-seed option rather than
   matching calendar dates. Artifact: whichever served list `build_site.py:2803` feeds.
4. **`pitch_plots` single-level `top` removal** (9.2, free half), if it lands before cutover.
   Byte-level change only, no value changes; still written down because the payload shape
   changes.
5. **`pitch_plots` rounding rule** (9.2, pre-registered half), if the owner approves it as
   part of the port rather than as a later lane. One entry, one per-column rounding table.
6. **The two-scale `tj_stuff_plus` resolution** (9.2, D10), whichever option the owner picks.

Nothing else. In particular, no entry may be added during the Gate C run itself; the list
freezes when the pin date is chosen.

---

# 11. DEFECT RESOLUTION MAP

Both reviews, every defect, where it is resolved. Items marked **CORRECTED** are places a
review was itself partly wrong and the spec says so with the measurement.

| # | defect | resolution |
|---|---|---|
| A1 | point-in-time bundles absent from the copy list; silent retrain | 1.4.1, 1.4.2, P0.5, P2.2. **CORRECTED**: a retrain is an evidence and feature-vintage loss, not a label lookahead; `train()` does filter labels. New finding: all 29 bundles are bWAR-basis and already miss under the eWAR epoch |
| A2 | "everything else is SAFE_CACHES" is false; FanGraphs pages dropped | 1.4.1. Rule replaced with "copy `.cache` minus `SAFE_CACHES`", 115,412 files / 3.77 GB, plus the new-cache-directory test |
| A3 | Gate C has no mechanism; cutting the network makes both sides refuse | C.0.1 (`EEPHUS_CACHE_ONLY` as a P0 deliverable), C.0.2 (liveness precondition), C.1.5 (positive control). Positive controls added to Gates A, B, D too |
| A4 | Gate A weaker than billed; deploy mode relaxes goldens; 17 modules self-skip | 2.1: recorded baseline (P0.1), both modes, chromium required, count equality, run twice with the two purposes named |
| A5 | no dependency lock; "no epsilon" premise unfunded | C.0.3 (constraints from `pip freeze`, pinned patch version), C.0.4 (`OPENBLAS_NUM_THREADS=1`, `PYTHONHASHSEED=0`), new `PLATFORM_FP` category with a bound and a 0.1 percent cap |
| A6 | invalid `CHECK` with subqueries; missing `search_path`; `REVOKE` is not a policy | 4.1 P3 rewritten with a composite FK plus a legal `CHECK`; `SET search_path = ''` on every definer function; `ALTER DEFAULT PRIVILEGES`; Gate D2 made catalog-driven |
| A7 | caller-chosen as-of date; backdating unconstrained | 4.1 P1 takes `p_split_id`; 4.1 P2 adds `no_backdating` with the `git_backfill` plus `attest_sha` carve-out |
| A8 | the survivorship fix is itself a survivorship leak | 4.2.1 rewritten: activity derived from appearance observations under the cutoff; first/last demoted to a UI filter |
| B-O1 | Gates B and C forbid the frontend rebuild the owner asked for | Gate B rewritten: URL contract plus redirect map, presentation explicitly out of scope; Gate C scoped to `data/**` |
| B-O2 | copy list short by ~580x in files | same as A2 |
| B-O3 | the eval-sidecar rule fails on day one, 12 times | C.3 plus P0.4: FROZEN/RECOMPUTED partition with a test. Measured 38 / 177 |
| B-O4 | no offline mode anywhere | same as A3 |
| B-O5 | unpinned Gate C inputs: date seed, env flags, `EEPHUS_FULL`, unsorted globs | C.0.4, C.0.5, P0.12. Measured 75 `EEPHUS_*` flags, 25 unsorted walk sites |
| B-O6 | Gate A ordering backwards | 2.1, run twice, purposes named |
| B-O7 | W-12 is a false choice | 1.8 and W-12: Python stays the gate runner permanently |
| B-T1 | `pitch_plots` duplication | 9.2, re-measured across all 1,789 files, split into free and pre-registered halves. **CORRECTED**: "deleting `top` is not a number change" holds for the 1,179 single-level files and fails for the 610 multi-level ones; and the two-scale `tj_stuff_plus` (58,270 points) is a new live defect |
| B-T2 | boot payload doubled past its documented budget | Gate B7, section 9.3 |
| B-T3 | disposable items | 9.1 |
| B-C1..C5 | withdrawn objections | retained as evidence in 7.1, W-1 and 5.1 |
| both | `backfill_vintages` "commit date cannot move backwards" | 4.3 **CORRECTED**: both dates are movable; the tool takes `max()` because later is the conservative direction. Conclusion unchanged, argument repaired |
| new | `SITE_ORIGIN` baked to production | 1.7, P0.13 |
| new | Supabase/account layer is a second datastore | section 8, D11 |
| new | `eephus-config.js` is tracked, not gitignored as a code comment claims | 1.7 |

---

# 12. OWNER DECISIONS

Twelve. Each has a recommendation. These are the ones an engineer cannot make because they
trade one thing the platform values against another.

**D1. Port first, then rewrite the backend? Or both together?**
*Recommendation: in sequence.* Gate C only exists if the same code runs on both sides.
Together and every diff has two candidate causes, which means no gate at all on the one
requirement you named explicitly. Also, four shipped bundles have no portable export, so an
Odin backend cannot score anything today regardless.

**D2. Does the site live-query the database, or keep the publish step?**
*Recommendation: keep the publish step.* Database becomes the store of record; a build job
runs as-of queries and writes vintage-stamped content-hashed bundles; the site serves the
bundles. Live querying costs the refusal path, the frozen stamped artifact and the fit-half
anchor. For the one surface where freshness is a real product question, the betting slate, a
live read buys nothing that a 15-minute incremental publish does not also buy, and the true
constraint there is the paid credit tier, not the serving model. If you want live reads
anyway, the refusal semantics get rebuilt **before** they are enabled, not after.

**D3. Full git history to the new remote, or a clean start?**
*Recommendation: push the full 818 MB history of the working branch as `main`, and keep the
old repository read-only forever.* Ten of the 42 leaderboard vintages derive from dates in
that history. Record every branch tip sha at migration time. Stop tracking purely-derived
artifacts going forward, but do not rewrite what exists.

**D4. Is `player_key` retired as the public URL key?**
*Recommendation: no.* Make `key_mlbam` the internal spine and keep `player_key` as the public
URL key. Retiring it breaks 11,697 published per-player URLs plus every deep link at once,
for no product benefit. The spine change is internal and gets you everything you want.

**D5. What is the pre-registered Chadwick coverage threshold?**
*Recommendation: write the threshold down before running the join.* Join all 10,623 `players`
rows against the register, report unmatched by level and by acquisition method. Suggested bar:
Chadwick becomes crosswalk-only, with the slug ladder retained underneath for the unmatched
tail, if unmatched active rows exceed 5 percent or if any currently-served 2026 board row
becomes unresolvable. Whatever number you pick, pick it first. Looking early disqualifies
applies here too.

**D6. What happens to the 27 beta-only commits?**
*Recommendation: enumerate against `origin/beta` (not local `beta`, 13 days older and not what
is deployed), classify each as re-apply / superseded / abandon, write it down, push `beta` to
the new remote as `archive/beta-2026-08-01`, and never merge it.* `merge-base` is empty; there
is no merge path.

**D7. The stale `proj_lgbm_v1` pin: restamp, or re-run the gate?**
*Recommendation: re-run `tools/def_feature_backtest.py` under `ewar_v2`.* The cheap option is
to correct the hash string in three places, but the verdict was earned on bundle
`6a691e03ff096a35` **and** on the bWAR label, and neither is what ships now. The measured
effect was small to begin with (-0.0027 holdout pooled MAE), so this is not "the prior is
wrong", it is "its evidence no longer describes the shipped model". If you will not spend the
compute, the fallback is to restamp **and** demote the row from `validated` to `provisional`
with a disclosure, because a served accountability note on `/projections/` currently names a
bundle that is not producing that page's numbers. Either way, strengthen the test to equality.

**D8. The 41 unvalidated SERVED rows: label or drop?**
*Recommendation: label them on the page for the first cut, then decide each on its own.* They
have no eval artifact, so Gate C has nothing to diff them against and they are precisely where
a number moves without anyone noticing. Dropping 41 served rows at once is a large product
change; labelling is honest and costs nothing.

**D9. `data/player_news.json` and the five unreachable eval receipts.**
*Recommendation: retire the sidecar, fix or drop the five claims.* Low stakes, decide in
passing, but do not port them unexamined.

**D10 (NEW, and it should be decided first). The two-scale `tj_stuff_plus` in
`data/pitch_plots/`.** 609 of 610 multi-level pitchers serve the same pitch with two different
Stuff+ values, up to 72 points apart, with nothing in the payload or the UI naming the
baseline. Three options:
- **(a) Label it.** Keep both, add a `basis` field per block (`pooled` / `level`), and have
  the card say which baseline it is showing. Smallest change, fully honest, no number moves.
  **Recommended.**
- **(b) Pick one basis.** Serve level-relative Stuff+ everywhere and recompute `top` from it.
  This moves 58,270 served points and is a `NAMED_FIX` with a real verdict behind it.
- **(c) Carry it as-is and disclose.** Acceptable only with a written entry, because the
  platform's own rule forbids showing a number on a scale it was not computed on.
Do this before the port so a new backend is not blamed for a number that already differs.

**D11 (NEW). Does the Supabase account and forum layer move in this port?**
*Recommendation: no, not in the first cut.* Keep the blank stub, assert the pages render
inert, and move it as its own migration with its own backup and its own RLS verification. It
is the only user-generated data on the platform and it cannot be regenerated from a scrape.

**D12 (NEW). Who owns the frontend rebuild lane, and does it ship before or after cutover?**
*Recommendation: after.* Port on the existing frontend, cut over, then rebuild behind Gate B's
redirect map and the B7 byte budget. Shipping it inside the port re-couples the two things the
gate split was drawn to separate, and the owner's stated number one priority is the port.

---

# 13. ACCEPTANCE CRITERIA, IN ONE LIST

The port is done when all of the following are true and recorded. Anything not recorded did
not happen.

1. `docs/port/BASELINE_PYTEST.txt` exists, captured on the old box before the move, with both
   pytest modes, `pip freeze`, python version and chromium status.
2. `EEPHUS_CACHE_ONLY=1` exists, raises on a cache miss in every fetch helper, and has a test
   proving a full build completes under it.
3. Constraints files from both boxes are committed; the new host is installed from them; the
   python3.12 patch version is pinned; numpy, pandas, scipy and statsmodels are declared.
4. `docs/port/EVAL_PARTITION.json` covers all 215 sidecars, and a test fails if a file moves
   partition or goes missing.
5. `proj_ml.train_cached` refuses to retrain without `EEPHUS_ALLOW_PIT_RETRAIN=1`, and the
   cache key digests the corpus and records the WAR basis.
6. The transfer manifest verifies: `prospects.db` (1,878,773,760 bytes) and **115,412 cache
   files / 3.77 GB**, sha256-matched, including the 29 point-in-time bundles and the 271
   `fg_*` pages.
7. **Gate A** passes twice (copy pass and rebuild pass), in both pytest modes, with chromium
   installed and passed / skipped / xfailed counts equal to the recorded baseline.
8. **Gate B** passes: 12,235 paths 200 or redirected, `.gz` twins served, 30 withheld paths
   404, no BA artifact reachable, 24 deep links load, the scout shard function matches on 200
   sampled keys, and the boot gzip budget holds.
9. **Gate C** passes with its preconditions asserted (frozen inputs, zero INGEST RED on both
   sides, pinned env recorded, same calendar date or a constant seed), its positive control
   demonstrated, **zero uncategorised differences**, `PLATFORM_FP` under 0.1 percent of leaves
   and individually listed, and every `NAMED_FIX` drawn from the frozen section 10 list.
10. All 177 FROZEN eval sidecars are byte-identical apart from `TIMESTAMP`.
11. **Gate D** passes all eleven assertions, including the catalog-driven role check and the
    leakage positive control, with the 42 vintages sha256-verified and
    `c3_unresolved_active: 0` / `frankenstein_records: 0` re-earned on 4,680 active rows.
12. **Gate E** passes: an injected empty upstream keeps the previous artifact, stamps it
    stale, carries its vintage and files RED; an injected failing test publishes nothing.
13. The three open INGEST REDs are cleared, or carried with a written known-RED entry.
14. The eight timing constraints T1 to T8 are installed as cron entries with `TZ=UTC` where
    stated, and `tools/betting_close_job.py --selfcheck` reports the scheduler has reached the
    job on the new box.
15. The old repository is read-only, branch tips recorded; the old box is running and
    untouched for 30 days after DNS moves.
16. Every owner decision D1 to D12 has a written answer in the repo, not in a chat log.

---

## Appendix: the single-paragraph version for the webmaster

You are right that the data is mostly static, and the measurement backs you: 72 percent of the
served files have not changed in a week, 14 of the 34 validated served models are stdlib-only
arithmetic, and `storage.py` and `build_site.py` import no numeric library at all. You are
right that the name-slug primary key has to go, and the repo pays for it in 200 colliding
slugs and one player who reached the served board twice with $20.5M of double-counted surplus.
You are right that some of this machinery is not earning its place, and attacking it rather
than the plan produced the biggest finding in this document: 1,179 of the 1,789
`pitch_plots` files carry a `top` array byte-identical to their one level split, about 528 MiB
of pure duplication, and the same pass found 58,270 pitches served with two different Stuff+
values in the same file because the pooled and per-level fastball baselines differ and nothing
labels which is which. Your write-side win is real too: 5,248 per-player files and 272 MB
rewritten every night having not changed in a month, when the repo already ships the
fingerprint primitive to fix it. Four corrections. First, 94 percent of the served **bytes**
changed today, and the files that are frozen are frozen because a pre-registered gate froze
them, so "refresh the stale data" would void every registered result on the platform. Second,
live-querying the database costs the refusal path, the frozen vintage stamp and the
never-graded fit half, and on the one surface where freshness is a real question, the betting
slate, it buys nothing a 15-minute incremental publish does not, because the constraint there
is a 500-credit monthly tier and not the serving model. Third, Chadwick is the right crosswalk
and the wrong active register: it is the last-resort resolver today precisely because it
returned a 1974-born pitcher for a current draft prospect, it has no row for 70 of the 96
FanGraphs `sa` prospects on our board, and the StatsAPI index that resolves all 4,680 active
rows is refreshed daily. Fourth, sequence the ML rewrite after the port, because all four
shipped bundles are Python pickles with no portable export, so nothing in Odin can score
anything until that export exists. And the test suite never has to be reimplemented: Odin
writes artifacts, Python asserts over them, the rsync stays behind the same exit code.
