# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Stamp the GLOBAL mean-blend recenter into the live proj_lgbm bundle.

P-MBLEND (2026-07-24). data/proj_mean_blend.json was fitted 2026-06-13,
holdout-confirmed on 2022-2024 and recorded in MODEL_REGISTRY as shipped -
but nothing in the repo ever wrote `mean_blend` into the bundle meta, so
proj_ml.predict_path's recenter (proj_ml.py, the `gblend` block) has been
reading None and doing nothing in production the entire time. The
star_blend twin has had a stamping tool (tools/fit_star_blend.py --apply)
and a pinning test since June; the mean blend had neither, which is why the
gap survived a bundle retrain and three registry updates.

This is the missing half. It writes ONLY meta - heads untouched, train hash
unchanged - and test_mean_blend_pinned_to_artifact keeps the bundle and the
artifact from drifting apart again.

Run: python tools/apply_mean_blend.py            (dry run: show the diff)
     python tools/apply_mean_blend.py --apply
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import proj_ml  # noqa: E402

log = logging.getLogger("apply_mean_blend")
ART = ROOT / "data" / "proj_mean_blend.json"

NOTE = ("post-hoc GLOBAL lift-only mean recenter (data/proj_mean_blend.json, "
        "tools/apply_mean_blend.py); heads untouched, train hash unchanged")


def _artifact() -> dict:
    d = json.loads(ART.read_text(encoding="utf-8"))
    lam = d.get("lambda_by_horizon") or {}
    if not lam:
        raise SystemExit("proj_mean_blend.json carries no lambda_by_horizon")
    # Every positive lambda must sit on a horizon that was holdout-scored, or
    # be explicitly disclosed as unconfirmable (h5 has no mature labels).
    hold = d.get("holdout_2022_2024") or {}
    for h, v in lam.items():
        if float(v) > 0 and str(h) not in hold and "disclosed_residual" not in d:
            raise SystemExit(f"lambda h{h} > 0 with no holdout row and no disclosure")
    return {str(k): float(v) for k, v in lam.items()}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    lam = _artifact()
    p = proj_ml.MODEL_DIR / "models.joblib"
    if not p.exists():
        raise SystemExit(f"no bundle at {p}")
    import joblib
    models = joblib.load(p)
    cur = models["meta"].get("mean_blend")
    log.info("bundle mean_blend  now: %s", cur)
    log.info("artifact lambdas       : %s", lam)
    if "--apply" not in sys.argv:
        log.info("(dry run - pass --apply to stamp)")
        return
    models["meta"]["mean_blend"] = lam
    models["meta"]["mean_blend_note"] = NOTE
    joblib.dump(models, p, compress=3)
    (proj_ml.MODEL_DIR / "meta.json").write_text(
        json.dumps(models["meta"], indent=1), encoding="utf-8")
    log.info("stamped mean_blend into %s", p)


if __name__ == "__main__":
    main()
