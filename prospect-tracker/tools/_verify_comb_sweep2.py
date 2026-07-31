# ADVERSARIAL VERIFICATION part 2: year-composition / censoring confound + Bradfield.
from __future__ import annotations
import json, os, sys
from pathlib import Path
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"
import numpy as np
from scipy import stats
from sklearn.isotonic import IsotonicRegression

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
from _comb_sweep import build, crossfit, ORIGINS


def iso_xfit(p, y, blk):
    out = np.empty(len(y))
    for b in np.unique(blk):
        m = blk == b
        ir = IsotonicRegression(increasing=True, out_of_bounds="clip")
        ir.fit(p[~m], y[~m]); out[m] = ir.predict(p[m])
    return out


def pit_confound():
    D = build("pit"); pred = crossfit(D)
    mask = np.isin(D["dy"], np.array(ORIGINS)) & D["has_milb"]
    idx = np.flatnonzero(mask)
    y, p, dy = D["y"][idx], pred[idx], D["dy"][idx]
    rows = [D["rows"][i] for i in idx]
    def mv(r, k):
        m = r.get("milb") if isinstance(r.get("milb"), dict) else {}
        return m.get(k)
    a = np.array([np.nan if mv(r, "age") is None else float(mv(r, "age")) for r in rows])
    b = np.array([np.nan if mv(r, "age_rel_level") is None else float(mv(r, "age_rel_level")) for r in rows])
    memb = (a < 20.0) & (b >= -2.0) & (b < -0.5)
    R = y - iso_xfit(p, y, dy)
    cens = ~D["complete"][idx]

    print("=== PITCHER U20&YNG: YEAR COMPOSITION CONFOUND ===")
    print(" year   pop_n  strat_n  strat_share  pop_censored_share  strat_censored_share")
    for yv in sorted(set(dy.tolist())):
        m = dy == yv
        print("  %d  %4d   %3d      %.3f        %.3f               %.3f"
              % (yv, m.sum(), (m & memb).sum(), (m & memb).sum() / m.sum(),
                 cens[m].mean(), cens[m & memb].mean() if (m & memb).sum() else float("nan")))
    recent = np.isin(dy, [2022, 2023, 2024])
    print("  share of stratum in 2022-24: %.3f ; share of population: %.3f"
          % (recent[memb].mean(), recent.mean()))
    print("  censored share: stratum %.3f  population %.3f" % (cens[memb].mean(), cens.mean()))

    # WITHIN-YEAR demeaned residual removes any year-level level shift (censoring, cohort)
    Rw = R.copy()
    for yv in np.unique(dy):
        m = dy == yv
        Rw[m] = R[m] - R[m].mean()
    t0, p0 = stats.ttest_ind(R[memb], R[~memb], equal_var=False)
    t1, p1 = stats.ttest_ind(Rw[memb], Rw[~memb], equal_var=False)
    print("  POOLED   Welch t %+.3f  mean %+.4f" % (t0, R[memb].mean()))
    print("  WITHIN-YEAR demeaned  Welch t %+.3f  mean %+.4f" % (t1, Rw[memb].mean()))

    # cluster-robust: treat decision-year as the cluster (8 year means, one-sample t)
    diffs = []
    for yv in np.unique(dy):
        m = dy == yv
        if (m & memb).sum() >= 1:
            diffs.append(R[m & memb].mean() - R[m & ~memb].mean())
    diffs = np.array(diffs)
    t2, p2 = stats.ttest_1samp(diffs, 0.0)
    print("  YEAR-CLUSTERED (n=%d year means) diff %+.4f  t %+.3f  p %.3f"
          % (len(diffs), diffs.mean(), t2, p2))
    # weighted by stratum n per year
    wn = np.array([(dy == yv)[  (dy == yv) & memb ].sum() for yv in np.unique(dy) if ((dy == yv) & memb).sum() >= 1], dtype=float)
    print("  year-weighted diff %+.4f" % (np.average(diffs, weights=wn)))

    # COMPLETE-WINDOW-ONLY replication (removes censoring entirely)
    comp = D["complete"][idx]
    cy = np.isin(dy, [2016, 2017, 2018, 2019, 2020])
    m2 = cy
    if m2.sum() > 50 and (m2 & memb).sum() >= 3:
        t3, p3 = stats.ttest_ind(R[m2 & memb], R[m2 & ~memb], equal_var=False)
        print("  ORIGINS 2016-2020 ONLY: n_strat=%d  t %+.3f  mean %+.4f"
              % ((m2 & memb).sum(), t3, R[m2 & memb].mean()))


def bradfield():
    D = build("hit"); pred = crossfit(D)
    mask = np.isin(D["dy"], np.array(ORIGINS)) & D["has_milb"]
    idx = np.flatnonzero(mask)
    y, p, dy = D["y"][idx], pred[idx], D["dy"][idx]
    rows = [D["rows"][i] for i in idx]
    def mv(r, k):
        m = r.get("milb") if isinstance(r.get("milb"), dict) else {}
        return m.get(k)
    lvl = np.array([str(mv(r, "milb_level")) for r in rows])
    age = np.array([np.nan if mv(r, "age") is None else float(mv(r, "age")) for r in rows])
    ops = np.array([np.nan if mv(r, "ops_rel") is None else float(mv(r, "ops_rel")) for r in rows])
    memb = (lvl == "AAA") & (age >= 23.5) & (ops < 0)
    res = D["res"][idx]; comp = D["complete"][idx]; deb = D["deb"][idx]
    print("\n=== BRADFIELD STRATUM: AAA & age>=23.5 & ops_rel<0 ===")
    print("  n=%d (brief says 69)  censored=%d (%.1f%%)  dy2024=%d"
          % (memb.sum(), (~comp[memb]).sum(), 100 * (~comp[memb]).mean(),
             ((dy == 2024) & memb).sum()))
    print("  ALL rows: mean target_resolved %.3f median %.3f share<=0.5 %.3f never_debuted %.3f"
          % (np.nanmean(res[memb]), np.nanmedian(res[memb]),
             (res[memb] <= 0.5).mean(), (~deb[memb]).mean()))
    c = memb & comp
    print("  FINISHED windows only: n=%d mean %.3f median %.3f share<=0.5 %.3f"
          % (c.sum(), np.nanmean(res[c]), np.nanmedian(res[c]), (res[c] <= 0.5).mean()))
    base = comp
    print("  BASE (track-record, finished): n=%d share<=0.5 %.3f mean %.3f"
          % (base.sum(), (res[base] <= 0.5).mean(), np.nanmean(res[base])))
    R = y - iso_xfit(p, y, dy)
    t, pv = stats.ttest_ind(R[memb], R[~memb], equal_var=False)
    print("  R_cal mean %+.4f  Welch t %+.3f  p %.3f (lane: mean -0.042, t +0.04)"
          % (R[memb].mean(), t, pv))


if __name__ == "__main__":
    pit_confound(); bradfield()
