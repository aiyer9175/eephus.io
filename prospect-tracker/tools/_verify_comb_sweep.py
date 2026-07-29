# ADVERSARIAL VERIFICATION of the combinatorial-archetype sweep lane. READ-ONLY.
# Independent re-derivation using sklearn IsotonicRegression + scipy Welch, NOT the
# lane's own _pava / welch_t.
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
from _comb_sweep import build, crossfit, ORIGINS   # model replica only


def iso_xfit(p, y, blk):
    out = np.empty(len(y))
    for b in np.unique(blk):
        m = blk == b
        ir = IsotonicRegression(increasing=True, out_of_bounds="clip")
        ir.fit(p[~m], y[~m])
        out[m] = ir.predict(p[m])
    return out


def main(side="pit"):
    D = build(side)
    pred = crossfit(D)
    inorig = np.isin(D["dy"], np.array(ORIGINS))
    mask = inorig & D["has_milb"]          # TRACK
    idx = np.flatnonzero(mask)
    y, p, dy = D["y"][idx], pred[idx], D["dy"][idx]
    print("side=%s TRACK n=%d" % (side, len(idx)))

    # ---- INDEPENDENT stratum membership, rebuilt from the raw rows, not from D["axes"]
    rows = [D["rows"][i] for i in idx]
    def age(r):
        m = r.get("milb") if isinstance(r.get("milb"), dict) else {}
        return m.get("age")
    def arl(r):
        m = r.get("milb") if isinstance(r.get("milb"), dict) else {}
        return m.get("age_rel_level")
    a = np.array([np.nan if age(r) is None else float(age(r)) for r in rows])
    b = np.array([np.nan if arl(r) is None else float(arl(r)) for r in rows])
    memb = (a < 20.0) & (b >= -2.0) & (b < -0.5)
    print("  INDEP membership U20 & YNG: n=%d  (lane says 43)" % memb.sum())
    print("  U20 alone n=%d (lane says 56)" % int((a < 20.0).sum()))

    # realized outcome on FINISHED windows only
    res = D["res"][idx]; comp = D["complete"][idx]; deb = D["deb"][idx]
    c = memb & comp
    print("  n_complete=%d mean_war=%.3f median=%.3f never_debuted=%.3f share<=0.5=%.3f"
          % (c.sum(), np.nanmean(res[c]), np.nanmedian(res[c]),
             (~deb[c]).mean(), (res[c] <= 0.5).mean()))

    # ---- INDEPENDENT residual arms
    g = iso_xfit(p, y, dy)
    R_cal = y - g
    R_flr = y - np.maximum(0.0, p)
    R_war = y - p
    for nm, r in (("R_cal", R_cal), ("R_flr", R_flr), ("R_war", R_war)):
        t, pv = stats.ttest_ind(r[memb], r[~memb], equal_var=False)
        print("  %-6s mean_in %+.4f  mean_out %+.4f  Welch t %+.3f  p %.3g"
              % (nm, r[memb].mean(), r[~memb].mean(), t, pv))

    # ---- per-year decomposition of the headline effect
    print("  PER-YEAR R_cal (in-stratum mean, n):")
    for yv in sorted(set(dy.tolist())):
        m = (dy == yv) & memb
        if m.sum():
            print("    %d n=%2d mean %+7.3f   (rest-of-year mean %+.3f)"
                  % (yv, m.sum(), R_cal[m].mean(), R_cal[(dy == yv) & ~memb].mean()))

    # ---- how much of the family is just "U20"? nested containment
    u20 = a < 20.0
    print("  overlap: U20&YNG is %d/%d of U20 (%.1f%%)"
          % (memb.sum(), u20.sum(), 100.0 * memb.sum() / max(u20.sum(), 1)))
    t, pv = stats.ttest_ind(R_cal[u20], R_cal[~u20], equal_var=False)
    print("  U20 alone R_cal Welch t %+.3f mean %+.4f" % (t, R_cal[u20].mean()))

    # ---- is the prediction itself sane on this stratum?
    print("  pred mean in-stratum %+.3f  y mean %+.3f ; pred<0 share overall %.3f"
          % (p[memb].mean(), y[memb].mean(), (p < 0).mean()))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "pit")
