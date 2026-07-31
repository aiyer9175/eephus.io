# scratch lab (lane: nested) -- POSITIVE CONTROL for the nested harness.
#
# A null is only worth reporting if the instrument can detect a real effect.
# Inject a synthetic archetype offset of known size into the residual of a
# stratum that IS in the pre-registered candidate space, then run the identical
# nested-CV procedure. If nested d_rho does not go clearly positive, the harness
# is broken and the null means nothing.
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import _comb_nested as C            # noqa: E402
import _comb_nested_run as R        # noqa: E402


def main(arm="tr", eff=(0.0, 1.0, 2.0, 3.0)):
    rows = R.get_rows(arm)
    n = len(rows)
    years = np.array([r["year"] for r in rows])
    resid = np.array([r["resid"] for r in rows], float)

    # the injected stratum: mid-infield/CF, age < 22 -- a real cell of the
    # pre-registered space, present in every fold.
    mask = np.array([(C._posgroup(r) == 1)
                     and ((r.get("milb") or {}).get("age") or 22.5) < 22.0
                     for r in rows])
    print(f"[poscheck] arm={arm} n={n} injected stratum n={int(mask.sum())} "
          f"({100*mask.mean():.1f}%)")
    print(f"           per-year n: "
          f"{[(int(y), int(mask[years==y].sum())) for y in np.unique(years)]}")

    base_t = np.array([r["target"] for r in rows], float)
    for e in eff:
        # shift the TARGET, so the residual shifts consistently and the archetype
        # offset has something real to correct. (Shifting only the residual, as a
        # first cut did, makes even a perfect find useless by construction.)
        for i, r in enumerate(rows):
            r["target"] = float(base_t[i] + (e if mask[i] else 0.0))
            r["resid"] = float(r["target"] - r["pred"])
        y = np.array([r["resid"] for r in rows], float)
        res = R.run_nested(rows, arm, {"real": y}, C.KS)
        line = []
        for k in C.KS:
            line.append(f"k={k}: d_rho={res['real'][k]['d_rho']:+.4f} "
                        f"dmse={res['real'][k]['d_mse']:+.2f} "
                        f"(best|t|={res['real'][k]['insample_best_t_mean']:.2f})")
        print(f"  inject +{e:.1f} WAR  " + "  ".join(line))
    for i, r in enumerate(rows):
        r["target"] = float(base_t[i])
        r["resid"] = float(r["target"] - r["pred"])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "tr")
