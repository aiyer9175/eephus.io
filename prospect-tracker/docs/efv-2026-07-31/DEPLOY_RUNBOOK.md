# Deploy runbook: what the 2026-07-31 session owes the box

Everything here is CODE that is committed and inert until an artifact is
rebuilt, or a DB repair that must be run on the box's own `prospects.db`.
The box is the single writer for served data (`deploy/publish_paths.txt`,
`data_exclude.txt`), so none of it was run locally.

Do NOT run any of this between 00:30 and 04:00 local: the nightly pipeline is
writing, and a regen fired into that window corrupts artifacts.

## 1. DB repairs (`--apply`, idempotent, run in this order)

| script | what it fixes | scope |
|---|---|---|
| `tools/repair_sabermetrics_stint_rows.py` | traded players stored ONE STINT as their season; prospx renders that wRC+ as a headline chip. 160 of 511 stored hitters were off by >0.5 | **scope on `numTeams > 1`**, not on "disagrees with the bulk call" (that flags 1,025 of 1,120, most of it ordinary daily drift) |
| ingestion-lane repairs (see the lane's own report) | Just Baseball chimera split, MLB Pipeline International re-dating | written this session, `--dry-run` by default |

Local runs of these are already done where noted in the lane reports; the box
has its own database and needs its own pass.

## 2. Regenerations, in dependency order

### 2a. The eFV chain (`rebuild_only`)
Picks up, all committed this session and all currently INERT:

- **F-SIDE-FIX crosswalk guard** (`_sff_pool_tail`). Until this runs, the board
  still serves the old `xfv_grade_display`, so **kade_anderson is still the #1
  surplus prospect on the live site**. After it: his pricing grade goes
  60.1 -> 55.8 and the band top reads made > de_vries > arias.
- **`xfv_grade_healthy`** on injured rows (the healthy-eFV display).
- **Pace columns** in the matrix (`entry_level_rank`, `pace_from_entry`,
  `entry_observed`) - emitted, feeding nothing until `PACE_FROM_ENTRY` is
  flipped after its gate.
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

- `PACE_FROM_ENTRY` gate run (`docs/efv-2026-07-31/PACE_FROM_ENTRY_GATE.md`) -
  needs a matrix rebuild and the four-part gate; the expected failure mode is
  pre-registered.
- The surplus re-key remains a NO-SHIP with its preconditions recorded
  (`SURPLUS_PRICING_KEY_GATE.md`); do not re-open it from the display-coherence
  argument alone.
