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

WHAT THE DECLARATION GUARD CANNOT SEE (added 2026-08-07 with the Pinazzi bug). Once a
declaration is corrected to 0 the guard above is blind to that feature forever: 0 can
never contradict. Pitcher `age_rel_level` was corrected to 0 on 2026-07-30 and eight
days later an owner reported the card it produces (a 26.8-year-old at High-A reading UP
on "Age for level"). So this module now also measures the two things that DO move
between rebuilds and decide whether a coefficient can be narrated:

  stability()                fold-sign agreement with the SERVED sign and the
                             production-only refit sign, per feature. A feature that
                             disagrees with itself across refits is one matrix rebuild
                             from flipping, whatever its declaration says.
  explainer_narration_risk() features whose served sign is opposite their MARGINAL and
                             that the per-prospect explainer would still narrate as that
                             player's reason. The three accepted remedies are a skip
                             (efv_score._EXPLAINER_SKIP*), a declared collinear group
                             (efv_factor_groups, which reports the NET direction), or a
                             DISPLAY_ACKNOWLEDGED entry citing its evidence.

REGENERATING THE LEDGER: `python efv_sign_audit.py --write` rewrites
data/xfv_sign_audit.json from the SHIPPED module (this one), not from a scratch lab, and
carries forward any block it does not itself produce with its previous vintage recorded.
It touches no other artifact and runs no pipeline export. `python efv_sign_audit.py`
alone still only prints. The file it rewrites was written by tools/_sweep_signs.py on
2026-07-25 and carried no generated_at at all, which is how it sat thirteen days behind
the code it describes, still recording pit age_rel_level as declared -1 serving -0.0076
against a shipped declaration of 0 serving +0.0560, without anything noticing.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from efv_model import _feature_spec, _prep, _FEATURES_HIT, _FEATURES_PIT, SCORED_YEARS
from efv_dataset import matrix_path
# efv_model's wrapper, so the audit reports the weights the board is SERVED from
# under ARM A2 rather than an un-imputed refit (pass-through while the arm is off).
from efv_model import _fit_ridge

LEDGER_PATH = Path(__file__).resolve().parent / "data" / "xfv_sign_audit.json"

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

# Fold-sign agreement below this fraction marks a feature SIGN_AT_RISK. Taken from the
# measurement rather than from taste: on the 2026-08-07 matrices the agreement values
# fall into two groups with an empty gap between them, 0.778 and up (19 of 23 features
# across both sides) against 0.667 and down (4), and 0.75 is that gap. A feature under
# the floor is not wrong; it is unpinned, and the next rebuild is about as likely to
# move its sign as not.
# The production-only refit is NOT redundant with this: pit peak_k_rel agrees with its
# served sign in 9 of 9 folds and still flips when the imputed-production rows leave the
# pool, which is the exact feature docs/SIGN_AUDIT_PATCHES.md follow-up 3 named.
FOLD_AGREEMENT_FLOOR = 0.75

# Suppressor-shaped features (served sign opposite the marginal) whose EXPLAINER
# narration has an accepted remedy other than a skip or a collinear group. Keyed
# (side, feature) -> evidence. Same discipline as ACKNOWLEDGED: an entry must cite where
# the remedy is written down, and explainer_narration_risk() drops it only while the
# feature is still suppressor-shaped.
DISPLAY_ACKNOWLEDGED: dict[tuple[str, str], str] = {
    ("hit", "n_milb_seasons"):
        "relabelled rather than skipped, docs/SIGN_AUDIT_PATCHES.md patch 4a: the chip "
        "reads 'Seasons to reach level', which is what the negative weight means "
        "(seasons USED to reach the level), so the DOWN direction narrates correctly.",
}


def _pool(side: str, production_only: bool = False):
    """The production pool, exactly as efv_model.fit_production_stack selects it.

    `production_only` narrows to the rows that carry a MiLB production block, which is
    the pool efv_ungraded.fit_nofv selects. That refit is a DIAGNOSTIC and never a
    served fit: it answers whether a weight survives dropping the rows whose production
    columns are imputed, which is the refit that flipped pit peak_k_rel (+0.1787 served,
    -0.1322 production-only) in the 2026-07-25 lane."""
    rows = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    is_pit = side == "pit"
    pool = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
            and not (r.get("kind") == "bust" and r.get("bust_recent"))]
    if production_only:
        pool = [r for r in pool if r.get("milb")]
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


def served_std_weights(side: str, data=None) -> dict:
    """{feature: standardized ridge weight} for the SERVED model.

    Exists because the published `ridge_std_weights` block in data/xfv_eval*.json is
    fit by efv_model._importances on the DEBUTED-ONLY eval pool, not on the pool
    fit_production_stack serves, and the two disagree on SIGN for about 5 of 14 hitter
    features (docs/SIGN_AUDIT_PATCHES.md follow-up 1). Nothing labels which table a
    reader is looking at, so "which way does this feature push?" gets the wrong answer
    from the published one. Call this to emit the served table beside it."""
    keys, _ = _feature_spec(side)
    data = _pool(side) if data is None else data
    ridge = _fit_ridge(data, keys)
    if not ridge:
        raise RuntimeError(f"served weights: ridge unfittable for side={side}")
    return {k: round(float(w), 4) for k, w in zip(ridge["keys"], ridge["w"])}


def _fold_weights(keys, data):
    """Standardized weight per feature on every forward-chained fold (train =
    decision_year < Y over efv_model.SCORED_YEARS), plus the folds that were fittable.

    DEGENERATE-FOLD GUARD, carried over from tools/_sweep_signs.py: the oldest folds
    train only on rows from before the StatsAPI MiLB floor, where several production
    columns are exactly CONSTANT. A standardized constant column gets weight exactly 0,
    and counting that as disagreement would manufacture instability, so a fold counts
    for a feature only where that feature actually varies in the fold's training rows."""
    out = {k: [] for k in keys}
    years = []
    for Y in SCORED_YEARS:
        tr = [r for r in data if r["decision_year"] < Y]
        n_te = sum(1 for r in data if r["decision_year"] == Y)
        if n_te < 15 or len(tr) < 60:
            continue
        m = _fit_ridge(tr, keys)
        if not m:
            continue
        years.append(int(Y))
        for i, k in enumerate(keys):
            col = [r["feats"].get(k, 0.0) for r in tr]
            if max(col) == min(col):
                continue
            out[k].append(float(m["w"][i]))
    return out, years


def stability(side: str, data=None) -> dict:
    """{feature: row} answering "is this sign PINNED, or is it one refit from moving?".

    Two instruments, both refits of the same ridge on a different row set:
      fold_sign_agreement    fraction of informative forward-chained folds whose weight
                             carries the SERVED sign. Measured against the served sign
                             and not the declaration on purpose: a declaration of 0 can
                             never contradict, so the declaration guard goes blind on
                             exactly the features a suppressor correction has already
                             touched, which is how the pitcher age_rel_level chip
                             survived to reach an owner.
      production_only_w      the same fit on rows carrying a MiLB production block only.
                             A sign that needs the imputed-production rows to hold is
                             not a finding about baseball.
    SIGN_AT_RISK is a WARNING, never a verdict: nothing here is evidence to drop or
    re-declare a feature (every such move needs the full docs/EFV_GATE_STANDARD.md
    battery, and every drop measured so far has been a null well under its MDE95)."""
    keys, mono = _feature_spec(side)
    data = _pool(side) if data is None else data
    served = _fit_ridge(data, keys)
    if not served:
        raise RuntimeError(f"stability: ridge unfittable for side={side}")
    fold_w, years = _fold_weights(keys, data)
    prod = _pool(side, production_only=True)
    pridge = _fit_ridge(prod, keys)
    out = {}
    for i, k in enumerate(keys):
        w = float(served["w"][i])
        decl = mono[i]
        fw = fold_w[k]
        agree = sum(1 for v in fw if (v > 0) == (w > 0))
        frac = (agree / len(fw)) if fw else None
        pw = float(pridge["w"][i]) if pridge else None
        pflip = bool(pw is not None and abs(pw) > NOISE_W and abs(w) > NOISE_W
                     and (pw > 0) != (w > 0))
        at_risk = bool(abs(w) > NOISE_W
                       and ((frac is not None and frac < FOLD_AGREEMENT_FLOOR) or pflip))
        out[k] = {
            "declared": decl,
            "served_w": round(w, 4),
            "folds_n": len(fw),
            "folds_agreeing_with_served_sign": agree,
            "fold_sign_agreement": (round(frac, 3) if frac is not None else None),
            "fold_w_mean": (round(sum(fw) / len(fw), 4) if fw else None),
            "fold_w_min": (round(min(fw), 4) if fw else None),
            "fold_w_max": (round(max(fw), 4) if fw else None),
            "production_only_w": (round(pw, 4) if pw is not None else None),
            "production_only_sign_flip": pflip,
            "flag": "SIGN_AT_RISK" if at_risk else "PINNED",
        }
    return {"side": side, "n": len(data), "n_production_only": len(prod),
            "fold_years": years, "fold_agreement_floor": FOLD_AGREEMENT_FLOOR,
            "features": out,
            "sign_at_risk": [k for k, v in out.items() if v["flag"] == "SIGN_AT_RISK"]}


def explainer_narration_risk(side: str, data=None) -> dict:
    """THE GUARD THE PINAZZI BUG NEEDED. {feature: row} for every feature the
    per-prospect explainer would narrate as this player's reason while its served sign
    is the OPPOSITE of its marginal correlation with realized WAR.

    A suppressor coefficient is a legitimate thing for the ridge to hold, because the
    ridge is answering a conditional question. It is not a legitimate thing to hand a
    reader as "here is what this player's age for level did to his grade", because the
    reader has no conditioning set in their head. The three accepted remedies, all
    already used in this codebase:
      skip     efv_score._EXPLAINER_SKIP / _EXPLAINER_SKIP_SIDE (pit age 2026-07-25,
               hit age 2026-08-04, pit age_rel_level 2026-08-07)
      group    efv_factor_groups.GROUP_OF, where the member is summed with its
               collinear partner and only the NET direction is shown (hit k_rel)
      relabel  a label that means what the sign means, recorded in DISPLAY_ACKNOWLEDGED
    Anything left over is a chip that tells a reader the opposite of the truth."""
    import efv_factor_groups as fg
    import efv_score as S
    rows = audit(side, data)
    skip = S._EXPLAINER_SKIP | S._EXPLAINER_SKIP_SIDE.get(side, set())
    out = {}
    for k, v in rows.items():
        m = v["marginal"]
        w = v["fitted_w"]
        if m is None or abs(w) <= NOISE_W or (w > 0) == (m > 0):
            continue
        if k in skip or fg.group_id(k) or (side, k) in DISPLAY_ACKNOWLEDGED:
            continue
        out[k] = v
    return out


def declared_directions() -> dict:
    """Every declaration the module makes, so an undeclared shipped key is visible."""
    return {"hit": dict(_FEATURES_HIT), "pit": dict(_FEATURES_PIT)}


def undeclared_provisional() -> dict:
    """Keys shipped in the efv_ungraded provisional (no-FV) sets that carry NO
    declared direction anywhere. Those models serve a grade with no stated intent
    for the feature at all, so the audit above cannot check them.

    CORRECTED 2026-08-07: this ignored efv_ungraded._NOFV_MONO, which is where the
    provisional sets got their OWN declarations in the 2026-07-25 patch, so it kept
    reporting peak_obp_rel / iso_rel / era_rel as undeclared a fortnight after they were
    declared. audit_provisional and the guard test always read _NOFV_MONO, so only this
    reporting helper was wrong, but a sign audit that misreports its own coverage is the
    exact failure this module exists to catch."""
    import efv_ungraded as U
    decl = declared_directions()
    own = getattr(U, "_NOFV_MONO", {}) or {}
    return {"hit": [k for k in U._NOFV_HIT
                    if k not in own and k not in decl["hit"] and k not in decl["pit"]],
            "pit": [k for k in U._NOFV_PIT
                    if k not in own and k not in decl["pit"] and k not in decl["hit"]]}


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


def _matrix_vintage(side: str) -> dict:
    """Which matrix file the numbers below describe. The 2026-07-25 ledger carried no
    vintage at all, so it read as current for eleven days after the code it audits
    moved."""
    p = matrix_path(side)
    st = p.stat()
    return {"path": p.name,
            "mtime_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ")}


def ledger() -> dict:
    """The full audit as one artifact: declarations, served signs, stability, the served
    weight table, and the provisional sets. Everything here is measured from the SHIPPED
    module, so a rebuilt matrix changes the file and a stale file is visible."""
    out = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "python efv_sign_audit.py --write",
        "gate_standard": "docs/EFV_GATE_STANDARD.md",
        "basis": {"scored_years": list(SCORED_YEARS),
                  "fold_agreement_floor": FOLD_AGREEMENT_FLOOR,
                  "noise_w": NOISE_W,
                  "matrices": {s: _matrix_vintage(s) for s in ("hit", "pit")}},
        "flagship": {},
        "provisional": {s: {"features": audit_provisional(s)} for s in ("hit", "pit")},
        "served_ridge_std_weights": {},
        "acknowledged": {"|".join(k): v for k, v in ACKNOWLEDGED.items()},
        "display_acknowledged": {"|".join(k): v for k, v in DISPLAY_ACKNOWLEDGED.items()},
    }
    for s in ("hit", "pit"):
        data = _pool(s)
        rows = audit(s, data)
        st = stability(s, data)
        feats = {k: dict(rows[k], **{q: v for q, v in st["features"][k].items()
                                     if q not in ("declared", "served_w")})
                 for k in rows}
        out["flagship"][s] = {
            "side": s, "n": st["n"], "n_production_only": st["n_production_only"],
            "fold_years": st["fold_years"], "features": feats,
            "contradictions": [k for k, v in rows.items() if v["contradiction"]],
            "sign_at_risk": st["sign_at_risk"],
            "explainer_narration_risk": sorted(explainer_narration_risk(s, data)),
        }
        out["served_ridge_std_weights"][s] = served_std_weights(s, data)
    out["undeclared_provisional_keys"] = undeclared_provisional()
    return out


def write_ledger(path=None) -> dict:
    """Rewrite the ledger, preserving any top-level block this module does not produce.

    The drop-gate adjudications in the 2026-07-25 file cost 2,000-draw bootstraps and
    are cited by comments in efv_model, so they are carried through untouched rather
    than dropped. They are also NOT re-measured here, and a carried block on a rebuilt
    matrix is a stale number, so each one is named in `carried_forward` with the mtime of
    the file it came from. Re-run tools/_sweep_signs.py (no --quick) to refresh them."""
    p = Path(path) if path else LEDGER_PATH
    res = ledger()
    if p.exists():
        try:
            prev = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            prev = {}
        carried = [k for k in prev if k not in res]
        if carried:
            for k in carried:
                res[k] = prev[k]
            res["carried_forward"] = {
                "keys": sorted(carried),
                "from_generated_at": prev.get("generated_at"),
                "from_file_mtime_utc": datetime.fromtimestamp(
                    p.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "note": "not re-measured by this run; refresh with tools/_sweep_signs.py",
            }
    p.write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true",
                    help="rewrite the ledger artifact (default: print only)")
    ap.add_argument("--out", default=None,
                    help="write somewhere other than data/xfv_sign_audit.json")
    args = ap.parse_args()

    for s in ("hit", "pit"):
        print("=== " + s)
        st = stability(s)["features"]
        for k, v in audit(s).items():
            print("  %-16s declared=%+d fitted=%+.4f marginal=%s  %-10s "
                  "folds=%s prod_only=%s %s"
                  % (k, v["declared"], v["fitted_w"], v["marginal"], v["classification"],
                     st[k]["fold_sign_agreement"], st[k]["production_only_w"],
                     st[k]["flag"]))
    for s in ("hit", "pit"):
        print("=== provisional " + s)
        for k, v in audit_provisional(s).items():
            print("  %-16s declared=%-5s inherited=%-5s fitted=%+.4f marginal=%s  %s"
                  % (k, v["declared"], v["inherited"], v["fitted_w"], v["marginal"],
                     v["classification"]))
    print("undeclared provisional keys:", undeclared_provisional())
    for s in ("hit", "pit"):
        print("explainer narration risk (%s):" % s, sorted(explainer_narration_risk(s)))
    if args.write or args.out:
        write_ledger(args.out)
        print("wrote", args.out or LEDGER_PATH)
