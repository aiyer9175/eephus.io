# PATCH SPEC (lane: scale-audit) -- put the calibration fit pool on production's FV scale

NOT APPLIED. `surplus_backtest_real.py` is shared with the refit lane, which owns the
edit; this is the drop-in so the two lanes do not collide. Back up to
`surplus_backtest_real.py.bak-scaleaudit` before applying.

## The defect

`surplus_backtest_real._load_inputs` (lines 104-124) medians the RAW per-source
snapshot FV. `tools/fit_surplus_calibration.py` calls `build_cohorts()` from that
loader, so the shipped calibration `linearmap-v5-todaypriced-2026-07-24`
(`value_framework_config.yaml` line 527, NOT `prospx_current.yaml`) was fit on the raw
scale. Production prices on the normalized consensus. Verified: the loader returns
exactly 3,368 listings and the resolved slice exactly 2,236, matching the registered
fit n.

## The change

```python
# at module import
import consensus as _cons
from grade_normalization import build_remapper

# inside _load_inputs, ONCE before the loop
remap = build_remapper(aliases=_cons.SOURCE_ALIASES)

# the SELECT must also return `position` (role drives the remap cell):
#   SELECT fv, position FROM snapshots WHERE player_key=? AND source=? AND snapshot_date=?
# then, per (player, source, year):
fv_n = remap(float(fv[0]), r["source"], row_position, int(r["y"]))
fv_at.setdefault((r["player_key"], int(r["y"])), []).append((fv_n, r["d"]))
```

Keep the median aggregator. Only the scale of the inputs changes.

## Two traps the refit lane must not step in

1. **MIN_FV = 40 is applied AFTER the median.** On the normalized scale 493 of the
   3,368 fit-window cells (14.6%) fall below 40 and leave the pool; 0 enter. If the
   gate stays at a literal 40 the refit silently loses the bottom band and the fit
   re-tilts. Either move the gate to the raw scale (gate on raw, fit on normalized)
   or drop it to ~37.9 so the pool membership is held fixed. State which.

2. **`fv_to_6yr_avg_war` is ALSO raw-fit and sits UNDERNEATH the calibration.**
   `data/value_framework_fitted.json` (`empirical_anchors`, generated 2026-06-22,
   cohort_window [2014, 2020]) was fit by `empirical_anchors._cohort`, which pools
   raw snapshot FV. Refitting the calibration on the normalized scale WITHOUT
   refitting the anchors makes the calibration absorb an anchor-axis error, which is
   exactly the mistake the 2026-07-14 lambda retraction was about. Sequence:
   FV scale -> anchors -> $/WAR level -> surplus calibration.
