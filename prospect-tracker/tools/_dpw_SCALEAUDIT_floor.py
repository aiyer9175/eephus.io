# SCRATCH LAB (lane: scale-audit) -- NOISE FLOOR, derived not registered.
#
# The scale gap is an ESTIMATE: every per-(source, role, cycle) offset is
# mean(src) - mean(ref) over a PAIRED same-player overlap. So the gap carries
# sampling error. Two bands, both with a REFIT PER DRAW of every offset and a
# full rebuild of the normalized pool:
#   SAMPLING   resample the overlap PAIRS with replacement -> how precisely is
#              the -2.13 FV / -41% dollar gap measured?
#   NULL       per pair, randomly swap which side is "source" and which is
#              "reference" (prob 0.5). The true offset is then 0 BY
#              CONSTRUCTION while the data's magnitude and spread are
#              untouched. Refit -> the gap a genuinely-zero scale difference
#              manufactures. This is the SAMPLING floor, not a numerical-
#              perturbation floor.
import json
import os
import statistics
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))
os.chdir(_HERE)
OUT = _HERE / "tools" / "_dpw_out"

import grade_normalization as gn      # noqa: E402
import consensus as cons              # noqa: E402
import value_framework as vf          # noqa: E402
from surplus_backtest_real import build_cohorts, _resolved_only   # noqa: E402

RNG = np.random.default_rng(20260725)
REPS = 400
CAL_YEARS = (2017, 2018, 2019)
POOL = [r for r in json.loads((OUT / "scale_pool.json").read_text(encoding="utf-8"))
        if r["year"] in CAL_YEARS and r["raw"] >= 40.0]


# ---- rebuild the PRODUCTION cell table, keeping the PAIRS (not just sorted sides)
def cell_pairs():
    latest = gn._all_latest()
    sources = set()
    for players in latest.values():
        for d in players.values():
            sources.update(d.keys())
    out = {}
    for (role, yr) in list(latest.keys()):
        for src in sources:
            if src == gn.REFERENCE or src in gn._SYNTHETIC_SOURCES:
                continue
            s_sorted, r_sorted, _p = gn._paired_dists(src, role, yr)
            if not (len(s_sorted) and len(r_sorted) and gn._mappable(s_sorted, r_sorted)):
                continue
            if len(s_sorted) < gn._MIN_N:
                continue                      # production drops the thin cell
            # recover the actual pairs behind that cell (cycle pairs, else pooled)
            p = gn._pairs(src, role, yr)
            if len(p) < gn._MIN_N:
                p = []
                for (r2, y2) in list(latest.keys()):
                    if r2 == role:
                        p.extend(gn._pairs(src, r2, y2))
            out[(src, role, yr)] = np.array(p, dtype=float)
    return out


CELLS = cell_pairs()
ALIAS = dict(cons.SOURCE_ALIASES)
print(f"production cells with a measurable offset: {len(CELLS)}  "
      f"(mean overlap n {np.mean([len(v) for v in CELLS.values()]):.0f})")


def offsets_from(pairs_by_cell):
    return {k: float(v[:, 0].mean() - v[:, 1].mean()) for k, v in pairs_by_cell.items()
            if len(v)}


def normalized_medians(offs):
    """Re-derive every pool cell's normalized median under an offset table."""
    med = np.empty(len(POOL))
    for i, r in enumerate(POOL):
        vals = []
        for src, fv, _n, _o in r["per_source"]:
            role = "pitcher" if r["is_pitcher"] else "hitter"
            k = (src, role, r["year"])
            o = offs.get(k)
            if o is None:
                canon = ALIAS.get(src)
                if canon and canon != src:
                    o = offs.get((canon, role, r["year"]))
            if src == gn.REFERENCE or src in gn._SYNTHETIC_SOURCES or o is None:
                vals.append(float(fv))
            else:
                vals.append(min(80.0, max(20.0, float(fv) - o)))
        med[i] = statistics.median(vals)
    return med


# NOTE: role here comes from the PLAYER (players.is_pitcher) while production
# derives it from the snapshot position; the point estimate below is re-checked
# against the production remapper to confirm the approximation is faithful.
raw = np.array([r["raw"] for r in POOL])
new_prod = np.array([r["new"] for r in POOL])
pt = normalized_medians(offsets_from(CELLS))
print(f"point-estimate check: reconstructed mean shift {np.mean(pt - raw):+.4f} FV vs "
      f"production remapper {np.mean(new_prod - raw):+.4f} FV "
      f"(agreement {np.mean(np.abs(pt - new_prod)):.4f} FV mean abs)")

# ---- price lookup: per-player 1-D price curve on an FV grid (validated below)
records = build_cohorts()[0]
resolved = {(r.listing.player_id, r.listing.listing_year): r.listing
            for r in _resolved_only(records)}
GRID = np.arange(34.0, 72.01, 0.25)
idx = [i for i, r in enumerate(POOL) if (r["player_key"], r["year"]) in resolved]
curves = {}
for i in idx:
    li = resolved[(POOL[i]["player_key"], POOL[i]["year"])]
    curves[i] = np.array([vf.apply_calibration(
        (vf.expected_surplus_usd(f, li.is_pitcher, li.position,
                                 age=li.age_at_listing, eta_years=li.eta_years) or 0.0) / 1e6,
        f, li.is_pitcher) for f in GRID])
print(f"priced players: {len(idx)}")


def dollars(fvs):
    return np.array([np.interp(fvs[i], GRID, curves[i]) for i in idx])


d_raw = dollars(raw)
d_new = dollars(new_prod)
exact = json.loads((OUT / "scale_dollars.json").read_text(encoding="utf-8"))
ex_raw = sum(r["raw"] for r in exact)
print(f"grid-interp check: raw aggregate ${d_raw.sum():,.1f}M vs exact ${ex_raw:,.1f}M "
      f"({100*(d_raw.sum()/ex_raw-1):+.3f}%)")
pt_gap_fv = float(np.mean(new_prod - raw))
pt_gap_d = float(100 * (d_new.sum() / d_raw.sum() - 1))
print(f"\nPOINT ESTIMATES: FV gap {pt_gap_fv:+.4f}   dollar gap {pt_gap_d:+.2f}%")


def run(mode, reps=REPS):
    gaps_fv, gaps_d = [], []
    for _ in range(reps):
        drawn = {}
        for k, v in CELLS.items():
            if mode == "sampling":
                j = RNG.integers(0, len(v), len(v))
                drawn[k] = v[j]
            else:  # permutation null: true offset 0 by construction
                w = v.copy()
                flip = RNG.random(len(w)) < 0.5
                w[flip] = w[flip][:, ::-1]
                drawn[k] = w
        m = normalized_medians(offsets_from(drawn))
        gaps_fv.append(float(np.mean(m - raw)))
        dd = dollars(m)
        gaps_d.append(float(100 * (dd.sum() / d_raw.sum() - 1)))
    return np.array(gaps_fv), np.array(gaps_d)


for mode in ("sampling", "null"):
    f, d = run(mode)
    print(f"\n=== {mode.upper()} ({REPS} draws, offsets REFIT every draw, "
          f"pool + prices rebuilt every draw) ===")
    print(f"  FV gap      mean {f.mean():+.4f}  sd {f.std(ddof=1):.4f}  "
          f"95% [{np.percentile(f,2.5):+.4f}, {np.percentile(f,97.5):+.4f}]  "
          f"p95|gap| {np.percentile(np.abs(f),95):.4f}")
    print(f"  dollar gap  mean {d.mean():+.3f}%  sd {d.std(ddof=1):.3f}  "
          f"95% [{np.percentile(d,2.5):+.3f}%, {np.percentile(d,97.5):+.3f}%]  "
          f"p95|gap| {np.percentile(np.abs(d),95):.3f}%")
    if mode == "null":
        print(f"  --> DERIVED NOISE FLOOR: |FV gap| {np.percentile(np.abs(f),95):.4f} FV, "
              f"|dollar gap| {np.percentile(np.abs(d),95):.3f}%")
        print(f"  --> observed / floor: FV {abs(pt_gap_fv)/max(np.percentile(np.abs(f),95),1e-9):.1f}x, "
              f"dollars {abs(pt_gap_d)/max(np.percentile(np.abs(d),95),1e-9):.1f}x")
