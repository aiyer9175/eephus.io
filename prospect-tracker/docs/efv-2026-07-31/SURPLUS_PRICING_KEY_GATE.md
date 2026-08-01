# Surplus pricing key: why the board still prices the quantile grade

Status: **REGISTERED, NOT SHIPPED.** Owner decision 2026-07-31 after measurement:
ship the crosswalk guard (A1), keep the pricing key, disclose the basis in the UI.

## The complaint that opened this

Kade Anderson served as the board's #1 prospect by surplus ($87.4M) while
displaying eFV 56.0, above jesus_made at $80.4M / eFV 60.9. Two independent
causes, and only one of them is the pricing key:

1. **The F-SIDE-FIX crosswalk endpoint was one player** (shohei_ohtani, two-way
   WAR on a pitcher row). FIXED, see `_sff_pool_tail` in efv_score.py and commit
   919c276. This alone drops Anderson's pricing grade 60.1 -> 55.8 and restores
   the band top to made > de_vries > arias.
2. **Surplus prices `xfv_grade_quantile`, the board displays `xfv_grade`.** Real
   incoherence, and the subject of this document.

## The proposal

Re-key `_reprice_surplus_on_display` (efv_score.py) and `proj_export.py`'s
`price_fv` from `xfv_grade_quantile` to `xfv_grade`, so the site prices the
grade it displays. Registered as a follow-up in POOLED_OUTCOME_REFIT.md 1.3.

## Why it does not ship: THREE measurements

### 1. The calibration is fitted on the consensus frame, and only one key is on it

`value_framework_config.yaml` calibration `isotonic-real-v6-evframe-2026-07-31`,
fit_provenance: fitted "on the NORMALIZED consensus frame production actually
serves (the frame P0, closed the same day)".

Live distributions over all 9,334 served rows:

| field | mean | sd | p10 | p50 | p90 | max |
|---|---|---|---|---|---|---|
| `consensus_fv` | 38.83 | 5.15 | 35.0 | 37.8 | 45.9 | 72.9 |
| `xfv_grade_quantile` (pricing key) | **38.92** | **5.01** | 35.0 | 38.0 | 45.6 | 60.1 |
| `xfv_grade` (displayed) | 32.51 | 12.36 | **20.0** | 37.7 | 47.5 | 66.5 |

The quantile key tracks the fitted frame almost exactly, which is not a
coincidence: it IS a per-side rank-quantile map onto the consensus FV
distribution. `xfv_grade` is a different scale (2.5x the dispersion, 6.4 points
lower on the mean). Re-keying evaluates a dollar-space isotonic map on a
raw-dollar distribution unlike the one it was fitted on. That is the same defect
class as the frame P0 closed on 2026-07-31, pointed the other way.

### 2. It would RE-CREATE the flat bottom v6 existed to remove

`outcome_implied_fv` returns exactly 20.0 for every non-positive predicted WAR.

Measured on the GRADE, which is the honest ground because price is a monotone
function of grade given (side, position, age, eta):

| | distinct grades | largest single-grade bucket |
|---|---|---|
| `xfv_grade_quantile` (today) | 176 | 3,693 rows (39.6%) at grade 35.0 |
| `xfv_grade` (proposed) | 342 | **4,365 rows (46.8%) at grade 20.0** |

The v6 EV re-fit's entire purpose was to lift 6,271 rows off a shared $0 floor.
Re-keying puts nearly half the board onto a single grade, at the extreme floor,
where it carries no ordering information at all.

**CORRECTION, and it cuts both ways.** An earlier draft of this document quoted
"158 vs 237 distinct prices, largest bucket 39.6% -> 48.7%". Those figures were
computed by pricing rows straight out of `xfv.json`, which carries **no `age`,
`eta_years` or `position`** - so every row was priced as an ageless, ETA-less
hitter. The price-level numbers were therefore measured on a degenerate frame
and are withdrawn. The grade-level table above replaces them and needs no
pricing arguments to be true.

The honest nuance the correction exposes: **`xfv_grade` is MORE granular overall**
(342 distinct grades against 176). The re-key would buy resolution in the middle
of the board and lose it at the bottom. The floor pile and the frame mismatch are
still decisive, but "the displayed grade is a blunter instrument" would be a
false way to put it.

### 3. Our own documentation forbids it

`efv-fa-execution-2026-07-30` (Phase 2, shipped): the pooled outcome curve
"CANNOT produce FV20-45 granularity (flat there; 71% of rows below the data
floor). **Never present a sub-45 grade as outcome-calibrated.**" Pricing is
exactly presenting it as outcome-calibrated, for the 71% of the board that
sits there.

## What shipped instead

- A1 crosswalk guard (commit 919c276) - fixes the actual served defect.
- **Disclosure, not concealment**: `makeSurplusCell`'s tooltip now names the
  pricing scale whenever it rounds differently from the displayed grade, and
  says why. The eFV tooltip already carried the same disclosure.
- This document, so the re-key is not re-proposed from the display-coherence
  argument alone.

## What WOULD unblock the re-key

Not a re-key on its own. In order:

1. **Fix sub-45 granularity in the grade map first.** While 46.8% of rows share
   one grade, no pricing key built on it can produce a distribution. This is a
   modelling problem (the outcome curve has no data below its floor), not a
   plumbing one.
2. **Then re-fit the calibration on the xfv_grade frame** with
   `tools/fit_surplus_calibration.py`, re-running `surplus_backtest_real` on
   that frame so the map and the served frame agree.
3. **Then gate on the EV metrics** the v6 fit is governed by (held-out bias,
   calibration slope), with per-player MAE reported as the diagnostic, and the
   flat-bottom bucket count as an explicit stop condition: if the largest
   single-price bucket grows, the re-key has failed regardless of coherence.

Until then the honest position is the one now served: the board prices the
scale the dollar model was fitted on, and says so.

## Reproduce

```
python - <<'EOF'
import json
from collections import Counter
# Grade-level, deliberately. xfv.json carries no age / eta_years / position,
# so anything that PRICES straight off this file is measuring an ageless,
# ETA-less hitter - which is how the withdrawn price figures were produced.
bp = json.load(open('data/xfv.json', encoding='utf-8'))['by_player']
for key in ('xfv_grade_quantile', 'xfv_grade'):
    gs = [round(v[key], 1) for v in bp.values() if v.get(key) is not None]
    top_grade, n = Counter(gs).most_common(1)[0]
    print(f'{key:20s} distinct={len(set(gs)):4d} '
          f'largest={n} ({100*n/len(gs):.1f}%) at grade {top_grade}')
EOF
```
