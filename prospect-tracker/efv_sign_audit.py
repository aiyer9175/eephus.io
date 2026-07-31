# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DECLARED-vs-FITTED sign audit for the shipped eFV feature sets.

WHY THIS EXISTS (owner bugs, 2026-07-25). Two of the three eFV oddities the owner
found by inspection were the SAME failure: a feature ships with a DECLARED monotone
direction in `efv_model._FEATURES_HIT` / `_FEATURES_PIT`, the ridge fits the OPPOSITE
sign, and nothing anywhere notices.

  * `k_rel` (hitters) is declared -1 ("more whiffs worse"). The served ridge fits it
    POSITIVE, so an elite-contact hitter (Franklin Arias, k_rel -0.088) drew a
    "Contact (K%) vs level DOWN" chip.
  * `age` (pitchers) is declared -1 ("younger better"). The served ridge fits it
    POSITIVE, so a 20-year-old in Double-A (Ryan Sloan) is PENALIZED for his age.

The declaration only binds the LightGBM challenger (`monotone_constraints` in
`efv_model._fit_lgbm_mono`, an eval-only model). It does NOT bind the shipped ridge.
So the declaration is a CLAIM ABOUT INTENT that was never enforced or re-checked.

WHAT A CONTRADICTION IS AND IS NOT. A wrong-signed fitted weight is not automatically
a bug. On a collinear block a legitimate SUPPRESSOR has a marginal correlation in the
declared direction and a partial coefficient in the other. `k_rel` is exactly that
(marginal -0.088, partial +0.187). The audit therefore reports the marginal and the
partial side by side and classifies:

  OK               declaration and fitted sign agree (or declaration is 0 = no claim)
  SUPPRESSOR       contradiction, but the MARGINAL agrees with the declaration -> the
                   conditional effect is real; the DECLARATION is what is wrong
  WRONG_SIGN       contradiction with the marginal on the same side as the fit -> the
                   declaration was never true, not even unconditionally

and separately flags sign INSTABILITY across the forward-chained folds, which is a
different and arguably worse problem than a stably-wrong sign.

A declaration of 0 means "no directional claim" (LightGBM leaves the feature
unconstrained). That is the correct declaration for a measured suppressor: it stops
the module asserting something the fit contradicts without pretending the reverse
claim is theory.

USE: `audit(side)` for the full table, `contradictions(side)` for the machine check.
Pinned by test_efv_sign_declarations.py, which fails on any contradiction that is not
in ACKNOWLEDGED and also fails on a STALE ACKNOWLEDGED entry that no longer
contradicts. Lab + full gate evidence: tools/_sweep_signs.py, data/xfv_sign_audit.json.
"""
from __future__ import annotations

import json

from efv_model import _feature_spec, _prep, _FEATURES_HIT, _FEATURES_PIT
from efv_dataset import matrix_path
from prospect_path import _fit_ridge

# Contradictions the owner has SEEN, measured and accepted, keyed (model, side, feature)
# where model is "flagship" or "provisional". Empty is the goal state: the fix for a
# measured suppressor is to correct the DECLARATION to 0, not to park it here. An entry
# here must cite its evidence artifact.
ACKNOWLEDGED: dict[tuple[str, str, str], str] = {}

# Provisional keys knowingly shipped with NO declared direction anywhere. Empty is the
# goal state: declare the direction (0 is a legitimate declaration) rather than list it
# here. A key reaching a served model with no stated intent is the defect this file
# exists to stop, so the allowlist is deliberately awkward.
UNDECLARED_OK: dict[str, set] = {"hit": set(), "pit": set()}

# Sign flips at or below this |weight| are numerically meaningless (the ridge is
# standardized, so this is a fraction of a WAR per SD). Below it we record the
# contradiction as NOISE rather than asserting a direction the fit cannot support.
NOISE_W = 0.02


def _pool(side: str):
    """The production pool, exactly as efv_model.fit_production_stack selects it."""
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    is_pit = side == "pit"
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    return _prep(pool, "target_censored", side)


def _wcorr(xs, ys, ws):
    sw = sum(ws)
    if sw <= 0:
        return None
    mx = sum(w * x for w, x in zip(ws, xs)) / sw
    my = sum(w * y for w, y in zip(ws, ys)) / sw
    cxy = sum(w * (x - mx) * (y - my) for w, x, y in zip(ws, xs, ys))
    vx = sum(w * (x - mx) ** 2 for w, x in zip(ws, xs))
    vy = sum(w * (y - my) ** 2 for w, y in zip(ws, ys))
    return (cxy / (vx * vy) ** 0.5) if vx > 0 and vy > 0 else None


def contradicts(declared: int, fitted: float, tol: float = 1e-9) -> bool:
    """THE RULE. A nonzero declaration contradicted by the fitted sign.

    declared == 0 is 'no directional claim' and can never contradict."""
    return bool(declared) and abs(fitted) > tol and (fitted > 0) != (declared > 0)


def audit(side: str, data=None) -> dict:
    """{feature: {declared, fitted_w, marginal, contradiction, classification}}.

    `fitted_w` is the STANDARDIZED ridge weight from the served production fit
    (efv_model.fit_production_stack fits the identical pool + the identical ridge).
    `marginal` is the sample-weighted Pearson correlation of the RAW column with
    realized WAR - no conditioning - which is what separates a suppressor from a
    declaration that was simply never true."""
    keys, mono = _feature_spec(side)
    data = _pool(side) if data is None else data
    ridge = _fit_ridge(data, keys)
    if not ridge:
        raise RuntimeError(f"sign audit: ridge unfittable for side={side}")
    ys = [r["target"] for r in data]
    ws = [max(float(r.get("weight", 1.0) or 0.0), 1e-3) for r in data]
    out = {}
    for i, k in enumerate(keys):
        w = float(ridge["w"][i])
        decl = mono[i]
        marg = _wcorr([r["feats"].get(k, 0.0) for r in data], ys, ws)
        con = contradicts(decl, w)
        if not con:
            cls = "OK"
        elif abs(w) <= NOISE_W:
            cls = "NOISE"
        elif marg is not None and decl and (marg > 0) == (decl > 0):
            cls = "SUPPRESSOR"
        else:
            cls = "WRONG_SIGN"
        out[k] = {"declared": decl, "fitted_w": round(w, 4),
                  "marginal": (round(marg, 4) if marg is not None else None),
                  "contradiction": con, "classification": cls}
    return out


def contradictions(side: str, data=None) -> dict:
    """{feature: row} for every shipped feature whose fitted sign contradicts its
    declared monotone direction. Empty dict = the declarations are honest."""
    return {k: v for k, v in audit(side, data).items() if v["contradiction"]}


def declared_directions() -> dict:
    """Every declaration the module makes, so an undeclared shipped key is visible."""
    return {"hit": dict(_FEATURES_HIT), "pit": dict(_FEATURES_PIT)}


def undeclared_provisional() -> dict:
    """Keys shipped in the efv_ungraded provisional (no-FV) sets that carry NO
    declared direction anywhere. Those models serve a grade with no stated intent
    for the feature at all, so the audit above cannot check them."""
    import efv_ungraded as U
    decl = declared_directions()
    return {"hit": [k for k in U._NOFV_HIT if k not in decl["hit"] and k not in decl["pit"]],
            "pit": [k for k in U._NOFV_PIT if k not in decl["pit"] and k not in decl["hit"]]}


def audit_provisional(side: str) -> dict:
    """Same audit for the efv_ungraded no-FV set. Those sets are BARE KEY LISTS with
    no declarations of their own, so the only stated intent for a shared key is the
    flagship one - own side first, then the other side (recorded as `inherited`).
    A key declared nowhere is `declared=None` and cannot be checked at all.

    The pool is the provisional fit's pool (production-bearing rows only, recent
    busts excluded) so the weights match efv_ungraded.fit_nofv."""
    import efv_ungraded as U
    keys = U._keys(side)
    decl = declared_directions()
    # efv_ungraded may declare its OWN directions (_NOFV_MONO); they win over the
    # inherited flagship ones because a key can legitimately mean different things
    # in a model with no FV anchor.
    own = getattr(U, "_NOFV_MONO", {}) or {}
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    is_pit = side == "pit"
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit and r.get("milb")
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    data = _prep(pool, "target_censored", side)
    ridge = _fit_ridge(data, keys)
    if not ridge:
        raise RuntimeError(f"provisional sign audit: ridge unfittable for side={side}")
    other = "pit" if side == "hit" else "hit"
    ys = [r["target"] for r in data]
    ws = [max(float(r.get("weight", 1.0) or 0.0), 1e-3) for r in data]
    out = {}
    for i, k in enumerate(keys):
        w = float(ridge["w"][i])
        d = own.get(k, decl[side].get(k))
        inherited = d is None and k in decl[other]
        if inherited:
            d = decl[other][k]
        marg = _wcorr([r["feats"].get(k, 0.0) for r in data], ys, ws)
        con = d is not None and contradicts(d, w)
        out[k] = {"declared": d, "inherited": inherited, "fitted_w": round(w, 4),
                  "marginal": (round(marg, 4) if marg is not None else None),
                  "contradiction": bool(con),
                  "classification": ("UNDECLARED" if d is None else
                                     "OK" if not con else
                                     "NOISE" if abs(w) <= NOISE_W else
                                     "SUPPRESSOR" if (marg is not None and (marg > 0) == (d > 0))
                                     else "WRONG_SIGN")}
    return out


if __name__ == "__main__":
    for s in ("hit", "pit"):
        print("=== " + s)
        for k, v in audit(s).items():
            print("  %-16s declared=%+d fitted=%+.4f marginal=%s  %s"
                  % (k, v["declared"], v["fitted_w"], v["marginal"], v["classification"]))
    for s in ("hit", "pit"):
        print("=== provisional " + s)
        for k, v in audit_provisional(s).items():
            print("  %-16s declared=%-5s inherited=%-5s fitted=%+.4f marginal=%s  %s"
                  % (k, v["declared"], v["inherited"], v["fitted_w"], v["marginal"],
                     v["classification"]))
    print("undeclared provisional keys:", undeclared_provisional())
