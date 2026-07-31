"""MECHANISM lane: decompose Enrique Bradfield Jr's served eFV end to end and
explain the +6.1 premium against a historical stratum mean of -6.05.

Read-only. Writes nothing outside data/_prem_mech_out.json (scratch).
Run: python tools/_prem_MECH.py
"""
from __future__ import annotations

import json
import sys
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import value_framework as vf                                        # noqa: E402
import efv_model as em                                              # noqa: E402
import efv_score as es                                              # noqa: E402
from prospect_path import _predict                                  # noqa: E402

DATA = ROOT / "data"
PK = "enrique_bradfield_jr"


def _load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def main():
    out = {}
    side = "hit"
    is_pit = False
    keys, _mono = em._feature_spec(side)
    ridge, a, b, ols, _k = es._fit_production(side)
    lam = em.blend_lambda(side)
    out["stack"] = {"alpha_keys": keys, "cal_a": a, "cal_b": b,
                    "ols_a": ols["a"], "ols_b": ols["b"], "lambda": lam}

    live = _load("xfv_live_hitter_matrix.json")
    r = next(x for x in live if x["player_key"] == PK)
    feats = em._vec(r, side)

    # ---- ridge leg, per-feature contribution in WAR (pre output-calibration) ----
    contrib = {}
    for k, mu, sd, w in zip(ridge["keys"], ridge["mu"], ridge["sd"], ridge["w"]):
        z = (feats.get(k, 0.0) - mu) / (sd or 1.0)
        contrib[k] = {"raw": feats.get(k, 0.0), "mu": mu, "sd": sd, "z": z,
                      "w": w, "contrib_pred": w * z}
    raw_pred = _predict(ridge, feats)
    out["ridge"] = {"intercept_b": ridge["b"], "raw_pred": raw_pred,
                    "contrib": contrib}

    xfv_war_pre = max(-2.0, a + b * raw_pred)
    sc = es._statcast_factor(r, side)
    inj = es._injury_factor(r)
    agef = es._age_factor(r)
    rolef = es._role_factor(r, xfv_war_pre)
    adj = inj * sc * agef * rolef
    xfv_war = es._apply_war_tilt(xfv_war_pre, adj) if adj != 1.0 else xfv_war_pre

    fv_eff = r.get("fv_effective")
    cons_anchor = float(fv_eff) if fv_eff is not None else float(r["consensus_fv_raw"])
    cons_war = max(0.0, em._pred_ols(ols, cons_anchor)) if ols else xfv_war
    rank_war = (1 - lam) * cons_war + lam * xfv_war

    age = r.get("age_now")
    eta = float(r.get("eta_years"))
    gm_age = es._grade_map_age(age, eta)
    grade = vf.realized_implied_fv(xfv_war, is_pit, age=gm_age,
                                   position=r.get("position"),
                                   exposure_seasons=es.TARGET_SEASONS)
    out["bradfield"] = {
        "consensus_fv_raw": r["consensus_fv_raw"], "fv_effective": fv_eff,
        "age_now": age, "eta_years": eta, "gm_age": gm_age,
        "position": r.get("position"),
        "raw_pred": raw_pred, "xfv_war_pre_tilt": xfv_war_pre,
        "statcast_factor": sc, "inj": inj, "agef": agef, "rolef": rolef,
        "xfv_war": xfv_war, "cons_war": cons_war, "rank_war": rank_war,
        "grade_raw": grade,
    }

    # ---- board affine (W-SIDESCALE) ----
    try:
        import efv_board_scale as bs
        out["bradfield"]["board_grade"] = bs.board_value({"side": "H",
                                                          "xfv_grade_model_raw": grade,
                                                          "xfv_grade": grade})
        out["board_scale_enabled"] = bs.enabled() if hasattr(bs, "enabled") else None
    except Exception as e:
        out["board_scale_err"] = repr(e)

    # ---- AGE SENSITIVITY of the WAR->grade inversion at his own xfv_war ----
    age_curve = {}
    for aa in (20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0):
        g = vf.realized_implied_fv(xfv_war, is_pit, age=aa + 0.0 + es.TARGET_SEASONS,
                                   position=r.get("position"),
                                   exposure_seasons=es.TARGET_SEASONS)
        age_curve[f"debut_age_{aa}"] = g
    out["age_curve_at_his_war"] = age_curve
    # position sensitivity
    pos_curve = {}
    for pp in ("CF", "SS", "C", "1B", "LF", "RF", "2B", "3B"):
        pos_curve[pp] = vf.realized_implied_fv(xfv_war, is_pit, age=gm_age, position=pp,
                                               exposure_seasons=es.TARGET_SEASONS)
    out["pos_curve_at_his_war"] = pos_curve

    (DATA / "_prem_mech_out.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "ridge"}, indent=1))
    print("--- ridge contributions (WAR units, sorted) ---")
    for k, v in sorted(contrib.items(), key=lambda kv: -abs(kv[1]["contrib_pred"])):
        print(f"{k:18s} raw={v['raw']:9.3f} mu={v['mu']:8.3f} sd={v['sd']:7.3f} "
              f"z={v['z']:+7.3f} w={v['w']:+7.4f} contrib={v['contrib_pred']:+7.4f}")
    print(f"{'INTERCEPT':18s} {'':46s} contrib={ridge['b']:+7.4f}")
    print(f"raw_pred={raw_pred:.4f}  -> cal {a:.4f}+{b:.4f}*pred = {a + b * raw_pred:.4f}")


if __name__ == "__main__":
    main()
