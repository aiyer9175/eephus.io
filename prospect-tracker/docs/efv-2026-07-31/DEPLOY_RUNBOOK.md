# Deploy runbook: what the 2026-07-31 session owes the box

Everything here is CODE that is committed and inert until an artifact is
rebuilt, or a DB repair that must be run on the box's own `prospects.db`.
The box is the single writer for served data (`deploy/publish_paths.txt`,
`data_exclude.txt`), so none of it was run locally.

Do NOT run any of this between 00:30 and 04:00 local: the nightly pipeline is
writing, and a regen fired into that window corrupts artifacts.

## 1. DB repairs (`--apply`, idempotent, run in this order)

All three default to dry-run. The corruption is in the DATABASE, not the code,
so each must run on the deploy box's own `prospects.db` as well as locally.

```
python tools/repair_sabermetrics_stint_rows.py --apply
python tools/repair_jb_chimera.py --apply
python tools/repair_intl_redating.py --apply
python run_monthly.py --daily        # rebuild after the last two
```

| script | what it fixes | note |
|---|---|---|
| `repair_sabermetrics_stint_rows.py` | traded players stored ONE STINT as their season; prospx renders that wRC+ as a headline chip. 160 of 511 stored hitters were off by >0.5 | **scope on `numTeams > 1`**, NOT on "disagrees with the bulk call" (that flags 1,025 of 1,120, most of it ordinary daily drift) |
| `repair_jb_chimera.py` | deletes the 100 exact June duplicates from the `JB 2026 Preseason` interval, leaving 26 rows with 26 distinct ranks | **74 of the original 100 March rows are UNRECOVERABLE** - the upsert destroyed rank/fv in place and JB no longer serves that list. The script says so rather than inventing them |
| `repair_intl_redating.py` | re-dates the 50 MLB Pipeline International rows 2026-07-31 -> 2026-01-15 | **MOVES SERVED NUMBERS**: consensus events key on snapshot_date. Ranks and FVs untouched |

## 2. Regenerations, in dependency order

### 2a. The eFV chain (`rebuild_only`)
Picks up, all committed this session and all currently INERT:

- **F-SIDE-FIX crosswalk guard** (`_sff_pool_tail`). Until this runs, the board
  still serves the old `xfv_grade_display`, so **kade_anderson is still the #1
  surplus prospect on the live site**. After it: his pricing grade goes
  60.1 -> 55.8 and the band top reads made > de_vries > arias.
- **`xfv_grade_healthy`** on injured rows (the healthy-eFV display).
- **Pace columns** in the matrix (`entry_level_rank`, `pace_from_entry`,
  `entry_observed`) - emitted, feeding nothing. (2026-08-04: the gate RAN and
  came back NO-SHIP, so `PACE_FROM_ENTRY` stays False and these columns stay
  permanently inert unless the arm is re-opened on new evidence.)
- **Chip relabel** for fast risers from a low start.
- **`meta.calibration`** stamp on `xfv.json`.

`rebuild_only` runs the WHOLE chain (dataset/score/history/tools/ungraded/
reliability/export), so a following `efv_export.py --all` is redundant. ~10 min.

**TWO PASSES ARE REQUIRED.** `overall_rank` lags `xfv.json` by one full run by
documented design (`storage._load_xfv_join`), and the crosswalk guard moves the
board basis. One pass leaves the board displaying new grades against a baked
rank that still encodes the old ones.

### 2b. The surplus-carrying artifacts, from a FRESH interpreter
`trade_values.json`, `mlb_projections.json`, `timeseries.json`.

**Fresh interpreter is not a formality.** On 2026-07-31 a long-running chained
export held the pre-14:42 config in memory and wrote v5 dollars into
`timeseries.json` at 21:12, six and a half hours after the v6 calibration
landed. `test_calibration_vintage.py` now xfails until all four artifacts agree;
those xfails ARE this regen debt and go green when it is done.

### 2c. FA + draft exports
Picks up the unfrozen 2027 board (the Spotrac compact-layout parser), the
per-class freshness stamps, and the lottery top-6 / GB fields.

**Acceptance for the FA board:** `data/fa_class.json` should carry ~218 members
parsed from the compact layout, and `fa_meta.sources.class` should show today
rather than 2026-07-30. The prospx lottery panel should render "% top 6" and
"GB to top 3" with real numbers rather than dashes.

### 2c-bis. The $/WAR series, and an owner glance owed
`data/fa_dpw_series.json` was deliberately NOT committed with the FA lane.
Regenerating it moves the headline 2026 figure **$14.92M -> $17.29M per WAR**,
decomposing into **+9.0% corpus drift** (which would arrive on the next pipeline
run regardless) and **+6.4% from the shipped WAR-map changes**.

That file is the $/WAR level the whole valuation engine prices against: on the
first full-suite run it unfroze `prospx_current`'s table and turned **18
valuation-set tests red**. It is not a ride-along on a chart page.

When the pipeline regenerates it:
- expect `test_valuation_sets` to go red until `prospx_current.yaml` is
  re-frozen against the new $/WAR (and **re-capture it INSIDE
  `with vf.valuation_set("prospx_current")`** - it is the base-identity set with
  6 control years, and capturing on the clemens_2026 default silently yields a
  different grid);
- `proj_export._winter_dpw` READS this file while `fa_export` computes it in
  memory, so the projections dollars step once on that run;
- the $/WAR page fills in its breakdown cuts and its realized series at the same
  moment, which is why they were left to arrive together.

### 2c-ter. Positional ladder is INERT until its artifact regenerates
`prospect_def_value` now reads `data/positional_fit.json` and refuses an
artifact without the new `identification` block, so today `POS_ADJ_SOURCE`
reads `"frozen fallback"` and **nothing has moved**. On regeneration: def_value
mean |delta| 0.096 runs, Spearman 0.99966 over 884 rows. `def_home.json` is
unaffected (it reads only p_hold / entropy).

### 2d. Homepage / static pages (`build_site.py`)
Picks up the FV chip tier fix. **Acceptance:** in the generated
`prospect-tracker/index.html` Top Prospects module,
`roch_cholowsky` renders `('fv-pill gold','60')` and `jesus_made` renders
`('fv-pill holo','61')`.

## 3. Golden restamp (after 2a settles)

```
python -c "from tools.pipeline_artifact_diff import fingerprint_file; \
from pathlib import Path; print(fingerprint_file(Path('data/xfv.json'), None))"
```
into `_GOLDEN_XFV_SHA256` in `test_efv_export.py`. The board basis moved, so the
old golden is expected to be red until this is done.

## 4. Coordination checks after the regen (all three, in order)

1. `storage.board_basis_fingerprint()` matches the committed pin.
2. `storage.xfv_history_is_on_board_basis()` returns **True** (it suppresses the
   eFV movement signal while False - correct for exactly one run, and it stays
   suppressed for as long as the regen is delayed).
3. Top-N side mix inside its recorded band (a BAND, not an exact count: the
   exact pin fired spuriously on a nightly regen once already).

## 5. Reds that must REMAIN red

- `test_team_outlook_calibration::test_recenter_remainder_near_zero`. The owner
  chose to keep hunting a per-player fix; the bound must NOT be widened, because
  it is the only instrument that noticed the star-tail shrink.
- `test_calibration_vintage` xfails until 2b completes (see above).

## 6. Not owed to the box, but owed

- ~~`PACE_FROM_ENTRY` gate run~~ - **DONE 2026-08-04, NO-SHIP.** The
  pre-registered failure mode fired (negative hitter pace weight = the
  survivorship-censoring artifact); the arm is closed and the flag stays False.
  The gate doc's "second arm" premise (a -0.5943 `efv_ungraded` weight) does not
  reproduce and is annotated in place. See
  `docs/efv-2026-07-31/PACE_FROM_ENTRY_GATE.md` and
  `data/xfv_pace_entry_eval.json`.
- The surplus re-key remains a NO-SHIP with its preconditions recorded
  (`SURPLUS_PRICING_KEY_GATE.md`); do not re-open it from the display-coherence
  argument alone.
