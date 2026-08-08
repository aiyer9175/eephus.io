"""M4: is the correct consensus shrinkage a function of publisher COVERAGE?

Pre-registration: docs/efv-2026-08-08/SHRINK_GATE.md (written before this file).

THE INCUMBENT is a hand-set pair, `consensus.SINGLE_SOURCE_K = 0.5` and
`SINGLE_SOURCE_PRIOR = 35.0`, never fitted, firing on the k=1 regime that is
58.2% of player-years and about 63% of the live board. The measurement-model
claim is that the right shrinkage is

    lambda_k = sigma_true^2 / (sigma_true^2 + sigma_pub^2 / k)

which rises with coverage (roughly 0.705 at k=1 against 0.877 at k=3), so ONE
constant cannot be right for every k.

THE PRIMARY GATE IS THE INTERACTION, NOT delta-R^2, and the gate doc explains
why: the pooled delta-R^2 effect is about 0.007 against an MDE of about 0.054,
so pre-registering that test would be pre-registering a null. Here we ask the
question directly. Regress

    y ~ x + x*(k - kbar)

and test the interaction. A non-zero interaction IS the statement that the
slope on the observed consensus should depend on coverage.

Read-only with respect to the tree: prints a report and writes one artifact.

Usage:
    python tools/consensus_shrink_lab.py [B]
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT_PATH = DATA / "consensus_shrink_eval.json"
SEED = 20260808
SIDES = ("hit", "pit")


def _matrix(side: str) -> list[dict]:
    p = DATA / ("xfv_pitcher_matrix.json" if side == "pit" else "xfv_hitter_matrix.json")
    obj = json.loads(p.read_text(encoding="utf-8"))
    rows = obj.get("rows") if isinstance(obj, dict) else obj
    return list(rows or [])


def _year(r: dict) -> int | None:
    c = r.get("cutoff") or r.get("asof_date")
    if isinstance(c, str) and len(c) >= 4 and c[:4].isdigit():
        return int(c[:4])
    dy = r.get("debut_year")
    return int(dy) if isinstance(dy, (int, float)) else None


def load(side: str, x_field: str = "consensus_fv_raw"):
    """x = observed consensus, k = number of grading sources, y = label.

    WHICH x MATTERS, and getting it wrong inverts the question. `consensus_fv_raw`
    already has the incumbent single-source shrink applied inside
    `compute_consensus_point`, so an interaction test on it asks whether the
    RESIDUAL shrinkage still depends on coverage, i.e. whether the hand-set
    constant is detectably wrong. `consensus_fv_pre_shrinkage` is the unshrunk
    input, and the same test on it asks the raw measurement-model question:
    should the slope depend on coverage AT ALL. Both are run and reported.
    """
    x, k, y, w, yr, res = [], [], [], [], [], []
    for r in _matrix(side):
        xi = r.get(x_field)
        ki = r.get("n_sources")
        yi = r.get("target_censored")
        if xi is None or ki is None or yi is None:
            continue
        try:
            xi, ki, yi = float(xi), float(ki), float(yi)
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(xi) and math.isfinite(ki) and math.isfinite(yi)):
            continue
        if ki < 1:
            continue
        x.append(xi)
        k.append(ki)
        y.append(yi)
        w.append(float(r.get("weight") or 1.0))
        yr.append(_year(r) or -1)
        res.append(not bool(r.get("censored")))
    return (np.asarray(x), np.asarray(k), np.asarray(y),
            np.clip(np.asarray(w), 1e-3, None), np.asarray(yr), np.asarray(res))


def wls(X: np.ndarray, y: np.ndarray, w: np.ndarray):
    """Weighted least squares. Returns (beta, se) with a sandwich-free
    homoskedastic se, which is all the interaction test needs because the
    permutation control carries the real null width."""
    sw = np.sqrt(w)
    Xw, yw = X * sw[:, None], y * sw
    beta, *_ = np.linalg.lstsq(Xw, yw, rcond=None)
    resid = yw - Xw @ beta
    dof = max(len(y) - X.shape[1], 1)
    s2 = float(resid @ resid) / dof
    try:
        cov = s2 * np.linalg.inv(Xw.T @ Xw)
        se = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    except np.linalg.LinAlgError:
        se = np.full(X.shape[1], np.nan)
    return beta, se


def design(x, k):
    kc = k - k.mean()
    return np.column_stack([np.ones_like(x), x, x * kc])


def interaction(x, k, y, w):
    beta, se = wls(design(x, k), y, w)
    t = beta[2] / se[2] if se[2] and math.isfinite(se[2]) and se[2] > 0 else float("nan")
    return float(beta[2]), float(se[2]), float(t)


def permuted_k_null(x, k, y, w, B, rng):
    """CONTROL C2. Permute the coverage covariate across players, keeping every
    marginal identical. If the interaction survives this, it is not coverage."""
    out = []
    for _ in range(B):
        out.append(interaction(x, k[rng.permutation(len(k))], y, w)[0])
    return np.asarray(out)


def cluster_boot(x, k, y, w, B, rng):
    """Paired bootstrap. Matrix rows are one per player (verified 2026-08-08:
    1917/1917 hit, 2040/2040 pit), so a row draw IS a player draw."""
    n = len(y)
    out = []
    for _ in range(B):
        i = rng.integers(0, n, n)
        out.append(interaction(x[i], k[i], y[i], w[i])[0])
    return np.asarray(out)


def run(B: int = 2000) -> dict:
    rng = np.random.default_rng(SEED)
    report: dict = {
        "generated_at": None,
        "produced_by": "python tools/consensus_shrink_lab.py",
        "registration": "docs/efv-2026-08-08/SHRINK_GATE.md",
        "lane": "M4",
        "seed": SEED,
        "B": B,
        "primary": "interaction of observed consensus with publisher coverage",
        "note": ("The primary is NOT pooled delta-R^2. Per the registration that "
                 "test would be pre-registering a null: effect ~0.007 against an "
                 "MDE ~0.054."),
        "sides": {},
    }

    for side_key in [f"{s}|{f}" for s in SIDES
                     for f in ("consensus_fv_pre_shrinkage", "consensus_fv_raw")]:
        side, x_field = side_key.split("|")
        x, k, y, w, yr, res = load(side, x_field)
        if len(y) < 200:
            report["sides"][side_key] = {"error": f"insufficient rows: {len(y)}"}
            continue
        side = side_key

        b2, se2, t2 = interaction(x, k, y, w)
        null = permuted_k_null(x, k, y, w, min(B, 1000), rng)
        boot = cluster_boot(x, k, y, w, B, rng)

        lo, hi = np.percentile(boot, [2.5, 97.5])
        nlo, nhi = np.percentile(null, [2.5, 97.5])
        p_perm = float((np.abs(null) >= abs(b2)).mean())

        # resolved-only sensitivity: drops the censoring-projection noise
        rb2 = rse2 = rt2 = float("nan")
        if res.sum() >= 200:
            rb2, rse2, rt2 = interaction(x[res], k[res], y[res], w[res])

        # per-cohort-year sign stability (registration clause P5)
        per_year = {}
        for u in sorted({int(v) for v in yr if v > 0}):
            m = yr == u
            if m.sum() >= 120 and len(np.unique(k[m])) > 1:
                bb, _, tt = interaction(x[m], k[m], y[m], w[m])
                per_year[str(u)] = {"n": int(m.sum()), "beta": round(bb, 6),
                                    "t": round(tt, 3)}
        signs = [1 if v["beta"] > 0 else -1 for v in per_year.values()]
        agree = (max(signs.count(1), signs.count(-1)) / len(signs)) if signs else None

        report["sides"][side] = {
            "n": int(len(y)),
            "k_distribution": {str(int(u)): int((k == u).sum())
                               for u in sorted(np.unique(k))},
            "interaction_beta": round(b2, 6),
            "interaction_se": round(se2, 6),
            "interaction_t": round(t2, 3),
            "boot_ci95": [round(float(lo), 6), round(float(hi), 6)],
            "boot_excludes_zero": bool(lo > 0 or hi < 0),
            "permuted_k_null_ci95": [round(float(nlo), 6), round(float(nhi), 6)],
            "permutation_p": round(p_perm, 4),
            "resolved_only": {"beta": round(rb2, 6), "t": round(rt2, 3)},
            "per_year": per_year,
            "per_year_sign_agreement": agree,
        }

    return report


def main(argv: list[str]) -> int:
    B = int(argv[1]) if len(argv) > 1 else 2000
    rep = run(B)

    import datetime as _dt
    rep["generated_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")

    for side, d in rep["sides"].items():
        print("=" * 66)
        print(f"SIDE {side}")
        if "error" in d:
            print("  ", d["error"])
            continue
        print(f"  n={d['n']}  coverage k -> {d['k_distribution']}")
        print(f"  interaction beta={d['interaction_beta']:+.6f} "
              f"se={d['interaction_se']:.6f} t={d['interaction_t']:+.3f}")
        print(f"  paired bootstrap CI95 {d['boot_ci95']} "
              f"excludes_zero={d['boot_excludes_zero']}")
        print(f"  permuted-k null CI95 {d['permuted_k_null_ci95']}  "
              f"permutation p={d['permutation_p']}")
        print(f"  resolved-only beta={d['resolved_only']['beta']:+.6f} "
              f"t={d['resolved_only']['t']:+.3f}")
        print(f"  per-year sign agreement: {d['per_year_sign_agreement']} "
              f"over {len(d['per_year'])} cohorts")

    OUT_PATH.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
