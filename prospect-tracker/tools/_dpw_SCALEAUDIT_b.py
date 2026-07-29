# SCRATCH LAB (lane: scale-audit) part (b). Read-only.
# Under the SHIPPED calibration (linearmap-v5-todaypriced-2026-07-24), how many
# dollars does the RAW-vs-NORMALIZED scale mismatch move?
#
# The calibration was fit so that cal(pred(fv_RAW)) matches realized surplus.
# Production feeds fv_NORMALIZED. The dollar error attributable purely to the
# scale mismatch is  cal(pred(fv_NORM)) - cal(pred(fv_RAW))  on the same player.
import json
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))
import os
os.chdir(_HERE)
OUT = _HERE / "tools" / "_dpw_out"

import value_framework as vf                                    # noqa: E402
from surplus_backtest_real import build_cohorts, _resolved_only  # noqa: E402

POOL = {(r["player_key"], r["year"]): r
        for r in json.loads((OUT / "scale_pool.json").read_text(encoding="utf-8"))}
RNG = np.random.default_rng(20260725)

cal = vf._config().get("calibration", {})
print(f"shipped calibration: enabled={cal.get('enabled')} version={cal.get('version')} "
      f"method={cal.get('method')}")


def price(fv, li):
    usd = vf.expected_surplus_usd(fv, li.is_pitcher, li.position,
                                  age=li.age_at_listing, eta_years=li.eta_years)
    return float(vf.apply_calibration((usd or 0.0) / 1e6, fv, li.is_pitcher))


def main():
    records, acct = build_cohorts()
    resolved = _resolved_only(records)
    print(f"cohort accounting: {acct}")
    print(f"resolved pool n={len(resolved)}  (registered v5 fit n=2,236)")

    rows = []
    for rec in resolved:
        li = rec.listing
        p = POOL.get((li.player_id, li.listing_year))
        if not p:
            continue
        d_raw = price(p["raw"], li)
        d_new = price(p["new"], li)
        d_old = price(p["old"], li)
        rows.append({"k": li.player_id, "y": li.listing_year, "pit": li.is_pitcher,
                     "fv_raw": p["raw"], "fv_new": p["new"], "fv_old": p["old"],
                     "raw": d_raw, "new": d_new, "old": d_old})
    print(f"priced n={len(rows)}")
    (OUT / "scale_dollars.json").write_text(json.dumps(rows), encoding="utf-8")

    a_raw = np.array([r["raw"] for r in rows])
    a_new = np.array([r["new"] for r in rows])
    a_old = np.array([r["old"] for r in rows])

    def summarize(a, b, lbl):
        d = b - a
        tot_a, tot_b = a.sum(), b.sum()
        print(f"\n--- {lbl} ---")
        print(f"  aggregate: fit-scale ${tot_a:,.1f}M  ->  production-scale ${tot_b:,.1f}M   "
              f"delta ${tot_b - tot_a:,.1f}M ({100*(tot_b/tot_a - 1):+.2f}%)")
        print(f"  per player: mean {d.mean():+.3f}M  median {np.median(d):+.3f}M  "
              f"sd {d.std(ddof=1):.3f}M  mean|d| {np.abs(d).mean():.3f}M")
        print(f"  pctiles p05 {np.percentile(d,5):+.2f}  p25 {np.percentile(d,25):+.2f}  "
              f"p75 {np.percentile(d,75):+.2f}  p95 {np.percentile(d,95):+.2f}  "
              f"[min {d.min():+.2f}, max {d.max():+.2f}]")
        print(f"  players moved by >$1M: {int((np.abs(d)>1).sum())} "
              f"({100*np.mean(np.abs(d)>1):.1f}%);  >$5M: {int((np.abs(d)>5).sum())} "
              f"({100*np.mean(np.abs(d)>5):.1f}%)")
        # player-clustered bootstrap of the aggregate % error
        idx_by_p = {}
        for i, r in enumerate(rows):
            idx_by_p.setdefault(r["k"], []).append(i)
        keys = list(idx_by_p)
        bs = []
        for _ in range(2000):
            pick = RNG.integers(0, len(keys), len(keys))
            ii = [i for j in pick for i in idx_by_p[keys[j]]]
            bs.append(100 * (b[ii].sum() / a[ii].sum() - 1))
        bs = np.array(bs)
        print(f"  aggregate %% error, player-clustered bootstrap 2000 reps 95%% CI "
              f"[{np.percentile(bs,2.5):+.2f}%, {np.percentile(bs,97.5):+.2f}%]")
        # where it concentrates
        print(f"  {'raw FV band':>12} {'n':>5} {'$ fit':>10} {'$ prod':>10} {'delta $M':>10} "
              f"{'%':>8} {'share of total delta':>21}")
        tot_d = d.sum()
        for lo, hi in ((40, 45), (45, 50), (50, 55), (55, 60), (60, 100)):
            m = np.array([lo <= r["fv_raw"] < hi for r in rows])
            if m.sum() < 5:
                continue
            sa, sb = a[m].sum(), b[m].sum()
            band = f"{lo}-{hi-1 if hi<100 else '80'}"
            print(f"  {band:>12} {int(m.sum()):>5} {sa:>10,.1f} {sb:>10,.1f} "
                  f"{sb-sa:>+10,.1f} {100*(sb/sa-1) if sa else float('nan'):>+7.1f}% "
                  f"{100*(sb-sa)/tot_d if tot_d else float('nan'):>20.1f}%")

    summarize(a_raw, a_new, "SHIPPED calibration applied to the NEW (post-repair) production scale")
    summarize(a_raw, a_old, "SHIPPED calibration applied to the OLD (pre-repair) production scale")

    print("\n=== per-cycle (forward-chained) aggregate %% error, NEW scale ===")
    for y in sorted({r["y"] for r in rows}):
        m = np.array([r["y"] == y for r in rows])
        print(f"  {y}: n={int(m.sum()):4d}  fit ${a_raw[m].sum():9,.1f}M  "
              f"prod ${a_new[m].sum():9,.1f}M  {100*(a_new[m].sum()/a_raw[m].sum()-1):+.2f}%")
    print("\n=== by role ===")
    for lbl, pit in (("hitters", False), ("pitchers", True)):
        m = np.array([r["pit"] == pit for r in rows])
        print(f"  {lbl}: n={int(m.sum()):4d}  fit ${a_raw[m].sum():9,.1f}M  "
              f"prod ${a_new[m].sum():9,.1f}M  {100*(a_new[m].sum()/a_raw[m].sum()-1):+.2f}%")


if __name__ == "__main__":
    main()
