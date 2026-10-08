# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EFV3_C03 pins: the model-class screen (tools/efv_v2_model_class_screen.py).

1. The guards raise on a reserved list vintage and on a 2025 year before any fit.
2. The admission function on fixture deltas returns the documented verdicts (s6),
   MC-4a's adoptable mark included; Holm on a known family.
3. The controls: the twin permutations keep every vintage's multiset; the per-fold sign
   count; the band-label hook and the vm reliability frame in efv_v2_candidates.
4. The whole reporting path on SYNTHETIC rows (never a frame): every arm on both frames,
   twin, per-fold deltas, permutation null, Holm, admission, probes, the artifact's key
   order, and the progress rows (role development, resolvable none, the registered note).
5. A second run with an artifact under data/ refuses ("spent").
6. The conftest restore list carries the screen artifact, the arm ledger and the
   progress ledger.
"""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pytest

import efv_progress as P
import efv_v2_candidates as C
import efv_v2_model as H
import efv_vintage_frame as F

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))

import efv_v2_model_class_screen as M  # noqa: E402

WEIGHTS = {"hit": {"w_skill": 0.5, "w_time": 0.2}, "pit": {"w_skill": 0.5, "w_time": 0.2}}
CONS = M.CONS


# ---------------------------------------------------------------------------
# synthetic rows (test_efv_v2_candidates' generator, with grades and an outcome)
# ---------------------------------------------------------------------------

def _feats(block=True, **kw):
    f = {"milb_unavailable": 0.0 if block else 1.0, "milb_missing": 0.0,
         "obp_rel": 0.0, "k_rel": 0.0, "peak_k_rel": 0.0, "level_rank": 0.0,
         "age_rel_level": 0.0, "tool_hit": 50.0, "tool_speed": 48.0,
         "is_college": 0.0, "is_ifa": 0.0, "pick_missing": 1.0}
    f.update(kw)
    return f


def _rows(side, years, n, seed, frame):
    rng = np.random.default_rng(seed)
    out, i = [], 0
    for yr in years:
        for _ in range(n):
            fv = float(rng.normal(45, 5))
            th = float(rng.normal(50, 8))
            kr = float(rng.normal(0, 0.05))
            drv = 0.08 * (th - 50) if side == "hit" else 20.0 * kr
            t = 0.1 * (fv - 45) + drv + float(rng.normal(0, 1))
            feats = _feats(True, tool_hit=th, tool_speed=float(rng.normal(48, 6)), k_rel=kr,
                           peak_k_rel=kr, obp_rel=float(rng.normal(0, 0.03)),
                           level_rank=float(rng.integers(0, 6)),
                           age_rel_level=float(rng.normal(0, 1)))
            extra = {"bmi": float(rng.normal(25, 2)), "pl_rev": None,
                     "on_40man": float(rng.random() < 0.2), "nov_add": float(rng.random() < 0.1)}
            g = {}
            if rng.random() < 0.9:
                g["fangraphs"] = fv + float(rng.normal(0, 3))
            if rng.random() < 0.7:
                g["mlb_pipeline"] = fv + float(rng.normal(0, 2))
            out.append({"player_key": f"{frame}{side}{i}", "decision_year": yr, "fv": fv,
                        "target": t, "reached": float(t > 0.5), "weight": 1.0,
                        "feats": feats, "extra": extra, "v2": H.v2_row(feats, extra),
                        "frame": frame, "ids_outcome_blind": frame == "lv", "grades": g})
            i += 1
    return out


def _frame_inputs(kind, years, folds, n, seed):
    out = {"kind": kind, "folds": list(folds), "by_side": {}, "reliability_rows": {},
           "per_fold": [], "w_star_dev": {"w_star": 1.5}}
    rows_all = {}
    for s_i, side in enumerate(F.SIDES):
        rows = _rows(side, years, n, seed + s_i, kind)
        rows_all[side] = rows
        out["reliability_rows"][side] = {}
        for r in rows:
            out["reliability_rows"][side].setdefault(int(r["decision_year"]), []).append(
                {"grades": r["grades"], "target": r["target"]})
        out["by_side"][side] = {}
        for V in folds:
            train = [r for r in rows if r["decision_year"] < V]
            test = [r for r in rows if r["decision_year"] == V]
            model = H.fit_v2(train, side, frame=kind, weights=WEIGHTS, absent_ok=False)
            pred = H.predict_v2(model, test)
            v2 = {p["player_key"]: float(p["order_idx"]) for p in pred}
            scored = []
            for r in test:
                grades = {CONS: r["fv"], M.V2_KEY: v2[r["player_key"]], **r["grades"]}
                scored.append({"key": r["player_key"], "side": side, "year": V,
                               "group": f"{side}|{V}", "grades": grades,
                               "outcome": {"war": r["target"], "contributor": r["target"] > 1.5}})
            out["by_side"][side][V] = {"train": train, "test": test, "scored": scored,
                                       "v2_model": model, "v2_pred": pred}
            out["per_fold"].append({"side": side, "year": V, "n_train": len(train),
                                    "n_scored": len(scored)})
    return out, rows_all


def synthetic_inputs(n=60, seed=3):
    lv, lv_rows = _frame_inputs("lv", range(2011, 2020), (2017, 2018, 2019), n, seed)
    vm, vm_rows = _frame_inputs("vm", range(2011, 2024), tuple(range(2017, 2024)), n, seed + 10)
    guards = M.screen_guards(lv["folds"], vm["folds"])
    return {"weights": WEIGHTS, "absent_ok": False, "guards": guards,
            "rule_sources": {s: {"matrix": vm_rows[s], "lv": lv_rows[s]} for s in F.SIDES},
            "frames": {"lv_dev": lv, "vm_dev": vm}}


# ---------------------------------------------------------------------------
# 1. guards
# ---------------------------------------------------------------------------

def test_guards_raise_on_a_reserved_vintage_and_a_2025_year_before_any_fit(monkeypatch):
    with pytest.raises(F.ReservedFrameError):
        M.screen_guards([2017, 2018, 2020], [2017, 2018])
    with pytest.raises(F.ReservedFrameError):
        M.screen_guards([2017, 2018, 2019], [2017, 2025])
    with pytest.raises(F.ReservedFrameError):
        M.screen_guards([2017, 2018, 2021], [2017])
    g = M.screen_guards([2017, 2018, 2019], list(range(2017, 2024)))
    assert g["lv_folds"] == [2017, 2018, 2019] and g["reserved_vm_pins"] == []
    calls = []
    monkeypatch.setattr(H, "fit_v2", lambda *a, **k: calls.append(1))
    ctx = {"weights": WEIGHTS, "absent_ok": False, "reliability": None, "band_weights": None}
    for arm in M.ARMS:
        with pytest.raises(F.ReservedFrameError):
            M.fit_fold(arm, "hit", "lv", _rows("hit", [2019, 2020], 30, 1, "lv"), [], ctx)
        with pytest.raises(F.ReservedFrameError):
            M.fit_fold(arm, "hit", "vm", _rows("hit", [2024, 2025], 30, 1, "vm"), [], ctx)
    assert calls == []


# ---------------------------------------------------------------------------
# 2. admission on fixture deltas
# ---------------------------------------------------------------------------

def _pf(delta=0.012, ci_low=0.001, sign=True, twin=0.0, auc=0.002, auc_mde=0.01, p_gt_0=0.995):
    return {"delta": delta, "ci_low": ci_low, "p_gt_0": p_gt_0, "sign": sign,
            "twin_delta": twin, "auc_delta": auc, "auc_mde95": auc_mde}


HOLM_OK = {"p": 0.005, "rank": 1, "holm_p": 0.025, "holm_alpha": 0.01, "survives_holm": True}
HOLM_NO = {"p": 0.04, "rank": 1, "holm_p": 0.2, "holm_alpha": 0.01, "survives_holm": False}


def test_admission_returns_the_documented_verdicts():
    both = {"lv_dev": _pf(), "vm_dev": _pf()}
    v = M.admission_verdict("mc2", both, HOLM_OK)
    assert v["admitted"] is True and v["adoptable"] is False
    assert all(x is True for x in v["clauses"].values()) and v["reason"].startswith("ADMITTED")
    # item 1: +0.004 on one frame fails
    v = M.admission_verdict("mc2", {"lv_dev": _pf(), "vm_dev": _pf(delta=0.004)}, HOLM_OK)
    assert v["admitted"] is False and v["clauses"]["1_within_delta_vs_v2"] is False
    assert "1_within_delta_vs_v2 failed" in v["reason"]
    # item 2: the fold signs
    v = M.admission_verdict("mc1", {"lv_dev": _pf(sign=False), "vm_dev": _pf()}, HOLM_OK)
    assert v["admitted"] is False and v["clauses"]["2_fold_signs"] is False
    # item 3: non-inferiority at exactly -0.005 fails, above it holds
    v = M.admission_verdict("mc3", {"lv_dev": _pf(ci_low=-0.005), "vm_dev": _pf()}, HOLM_OK)
    assert v["clauses"]["3_noninferiority"] is False
    v = M.admission_verdict("mc3", {"lv_dev": _pf(ci_low=-0.0049), "vm_dev": _pf()}, HOLM_OK)
    assert v["clauses"]["3_noninferiority"] is True
    # item 4: a twin at or above the arm
    v = M.admission_verdict("mc4b", {"lv_dev": _pf(twin=0.012), "vm_dev": _pf()}, HOLM_OK)
    assert v["admitted"] is False and v["clauses"]["4_twin"] is False
    # item 5: the AUC veto fires below minus its own mde95
    v = M.admission_verdict("mc2", {"lv_dev": _pf(auc=-0.011), "vm_dev": _pf()}, HOLM_OK)
    assert v["clauses"]["5_auc_veto"] is False
    v = M.admission_verdict("mc2", {"lv_dev": _pf(auc=-0.01), "vm_dev": _pf()}, HOLM_OK)
    assert v["clauses"]["5_auc_veto"] is True
    # item 6: Holm
    v = M.admission_verdict("mc2", both, HOLM_NO)
    assert v["admitted"] is False and v["clauses"]["6_holm"] is False
    v = M.admission_verdict("mc2", both, None)
    assert v["admitted"] is False and v["clauses"]["6_holm"] is None
    assert "6_holm not derivable" in v["reason"]
    # a leg that was not derived never admits
    v = M.admission_verdict("mc2", {"lv_dev": _pf(delta=None), "vm_dev": _pf()}, HOLM_OK)
    assert v["admitted"] is False and v["clauses"]["1_within_delta_vs_v2"] is None
    # MC-4a: adoptable on non-inferiority alone, no margin claim
    low = {"lv_dev": _pf(delta=0.001, ci_low=-0.002, sign=False),
           "vm_dev": _pf(delta=-0.001, ci_low=-0.003, sign=False)}
    v = M.admission_verdict("mc4a", low, HOLM_NO)
    assert v["admitted"] is False and v["adoptable"] is True
    assert v["reason"].startswith("ADOPTABLE on non-inferiority alone")
    assert M.probe_verdict(v) == "ADOPTABLE"
    v = M.admission_verdict("mc4b", low, HOLM_NO)
    assert v["adoptable"] is False and M.probe_verdict(v) == "NULL"
    v = M.admission_verdict("mc4a", {"lv_dev": _pf(delta=0.001, ci_low=-0.006, sign=False),
                                     "vm_dev": _pf(delta=0.001, ci_low=-0.002, sign=False)},
                            HOLM_NO)
    assert v["adoptable"] is False
    v = M.admission_verdict("mc4a", {"lv_dev": _pf(delta=0.001, ci_low=-0.002, sign=False,
                                                   auc=-0.02),
                                     "vm_dev": _pf(delta=0.001, ci_low=-0.002, sign=False)},
                            HOLM_NO)
    assert v["adoptable"] is False
    assert M.probe_verdict(M.admission_verdict("mc2", both, HOLM_OK)) == "ADMITTED"


def test_admission_inputs_read_the_frame_block():
    blk = {"deltas": {M.ADMISSION_LEG: {"spearman": {"delta": 0.01, "ci95": [-0.002, 0.02],
                                                       "p_gt_0": 0.93},
                                         "auc": {"delta": 0.004, "mde95": 0.009}}},
           "fold_sign_agreement": {"ok": True}, "twin": {"within": {"delta": -0.003}}}
    assert M.admission_inputs(blk) == {"delta": 0.01, "ci_low": -0.002, "p_gt_0": 0.93,
                                       "sign": True, "twin_delta": -0.003,
                                       "auc_delta": 0.004, "auc_mde95": 0.009}


def test_holm_family_of_five():
    h = M.holm_adjust({"mc1": 0.5, "mc2": 0.004, "mc3": 0.03, "mc4a": None, "mc4b": 0.2}, m=5)
    assert h["mc2"]["rank"] == 1 and h["mc2"]["holm_p"] == 0.02 and h["mc2"]["survives_holm"]
    assert h["mc3"]["rank"] == 2 and h["mc3"]["holm_p"] == 0.12 and not h["mc3"]["survives_holm"]
    assert h["mc4b"]["holm_p"] >= h["mc3"]["holm_p"]
    assert h["mc4a"]["survives_holm"] is None and h["mc4a"]["p"] is None


def test_fold_sign_agreement_bars():
    folds = {str(y): {"sign": s} for y, s in zip(range(2017, 2020), (1, 1, -1))}
    a = M.sign_agreement(folds, "lv_dev", 0.01)
    assert a["same_sign"] == 2 and a["required"] == 2 and a["ok"] is True
    assert M.sign_agreement(folds, "lv_dev", -0.01)["ok"] is False
    folds7 = {str(y): {"sign": 1 if y < 2021 else -1} for y in range(2017, 2024)}
    assert M.sign_agreement(folds7, "vm_dev", 0.01)["same_sign"] == 4
    assert M.sign_agreement(folds7, "vm_dev", 0.01)["ok"] is False
    folds7["2021"]["sign"] = 1
    assert M.sign_agreement(folds7, "vm_dev", 0.01)["ok"] is True
    assert M.sign_agreement(folds, "vm_dev", 0.01)["ok"] is False   # 3 folds are not 7


# ---------------------------------------------------------------------------
# 3. the controls and the candidates hooks
# ---------------------------------------------------------------------------

def test_twin_permutations_keep_every_vintage_multiset():
    rows = _rows("hit", range(2011, 2014), 25, 5, "lv")
    rng = np.random.default_rng(M.SEED)
    out = M.permute_drivers(rows, rng)
    assert [r["player_key"] for r in out] == [r["player_key"] for r in rows]
    assert [r["fv"] for r in out] == [r["fv"] for r in rows]
    for y in (2011, 2012, 2013):
        a = sorted(r["v2"]["tool_hit"] for r in rows if r["decision_year"] == y)
        b = sorted(r["v2"]["tool_hit"] for r in out if r["decision_year"] == y)
        assert a == b
    assert any(r["v2"] is not s["v2"] for r, s in zip(rows, out))
    bands = M.permute_bands(rows, np.random.default_rng(M.SEED))
    for y in (2011, 2012, 2013):
        a = sorted(C.band_of_row(r) for r in rows if r["decision_year"] == y)
        b = sorted(r[C.MC3_BAND_KEY] for r in bands if r["decision_year"] == y)
        assert a == b
        assert sorted(C.band_of_row(r) for r in bands if r["decision_year"] == y) == a
    rel = {"table": {"hit": {"2017": {"fangraphs": 0.8, "mlb_pipeline": 1.2}}},
           "sources": {"hit": ["fangraphs", "mlb_pipeline"]}}
    tw = M.exchange_reliability(rel, np.random.default_rng(1))
    assert sorted(tw["table"]["hit"]["2017"].values()) == [0.8, 1.2]
    assert rel["table"]["hit"]["2017"] == {"fangraphs": 0.8, "mlb_pipeline": 1.2}


def test_band_label_hook_and_the_vm_reliability_frame():
    r = {"v2": {"has_block": True, "level_rank": 5.0}}
    assert C.band_of_row(r) == "upper"
    assert C.band_of_row(dict(r, mc3_band="lower")) == "lower"
    with pytest.raises(ValueError):
        C.band_of_row(dict(r, mc3_band="middle"))
    ss = {"k": 0.5, "prior": 35.0}
    by = {2017: [{"grades": {"fangraphs": 50.0}, "target": 1.0}]}
    with pytest.raises(F.ReservedFrameError):
        C.build_source_reliability({"hit": by}, single_source=ss, target_vintages=[2020])
    t = C.build_source_reliability({"hit": by}, single_source=ss, target_vintages=[2020, 2023],
                                   frame="vm")
    assert t["frame"] == "vm" and sorted(t["table"]["hit"]) == ["2020", "2023"]
    assert t["reads"]["hit"]["2020"] == [2017]
    with pytest.raises(F.ReservedFrameError):
        C.build_source_reliability({"hit": by}, single_source=ss, target_vintages=[2025],
                                   frame="vm")
    with pytest.raises(F.ReservedFrameError):
        C.build_source_reliability({"hit": {2025: by[2017]}}, single_source=ss, frame="vm")
    with pytest.raises(ValueError):
        C.build_source_reliability({"hit": by}, single_source=ss, frame="debut")


def test_permutation_null_is_centred_and_fold_deltas_cover_every_fold():
    rng = np.random.default_rng(7)
    rows = []
    for side in F.SIDES:
        for y in (2017, 2018, 2019):
            for i in range(40):
                war = float(rng.normal())
                rows.append({"key": f"{side}{y}{i}", "side": side, "year": y,
                             "group": f"{side}|{y}", "grades": {CONS: 45.0 + rng.normal(),
                                                                M.V2_KEY: war + rng.normal(),
                                                                M.ARM_KEY: war + rng.normal()},
                             "outcome": {"war": war, "contributor": war > 1}})
    f = M.fold_deltas(rows)
    assert sorted(f) == ["2017", "2018", "2019"] and all(v["n"] == 80 for v in f.values())
    obs = M.S.paired_delta([r["key"] for r in rows], [r["group"] for r in rows],
                           [r["outcome"]["war"] for r in rows],
                           [r["outcome"]["contributor"] for r in rows],
                           [r["grades"][M.ARM_KEY] for r in rows],
                           [r["grades"][M.V2_KEY] for r in rows],
                           [r["grades"][CONS] for r in rows], statistic="within", B=60)
    p = M.permutation_null(rows, obs["delta"], n_perm=50, seed=M.SEED)
    assert p["n"] == 50 and p["status"] == "derived" and 0 < p["p"] <= 1
    assert abs(p["null_mean"]) < 0.05 and p["null_q95"] > p["null_mean"]
    assert M.permutation_null(rows, None, n_perm=5)["p"] is None


# ---------------------------------------------------------------------------
# 4. the whole reporting path on synthetic rows
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def synthetic_doc(tmp_path_factory):
    inputs = synthetic_inputs()
    M.finish_inputs(inputs, log=lambda *_a: None)
    doc = M.run(inputs, B=120, n_perm=12, exploratory=True, with_mc5=False,
                with_rank_weight=True, log=lambda *_a: None)
    out = tmp_path_factory.mktemp("screen") / "efv_v2_model_class_screen.json"
    M.write_doc(doc, out)
    return doc, out, inputs


def test_synthetic_run_carries_every_registered_block(synthetic_doc):
    doc, out, inputs = synthetic_doc
    assert doc["exploratory"] is True and doc["role"] == "development"
    assert doc["adjudicates"] is False and doc["selects"] is False
    assert doc["forking_paths_added"] == 10 and doc["n_probes"] == 10
    assert sorted(doc["arms"]) == sorted(M.ARMS)
    assert doc["holm"]["m"] == 5 and sorted(doc["holm"]["by_arm"]) == sorted(M.ARMS)
    for arm, a in doc["arms"].items():
        assert a["model_id"] == C.ARM_IDS[arm]
        assert a["admitted"] in (True, False) and a["adoptable"] in (True, False)
        assert set(a["clauses"]) == set(k for k in M.ADMISSION_RULE if k != "mc4a_adoptable")
        for fid in M.FRAMES:
            f = a["frames"][fid]
            assert f["n"] == sum(f["n_by_side"].values()) > 0
            assert set(f["deltas"]) == {n for n, *_ in M.COMPARISONS}
            for comp in f["deltas"].values():
                assert set(comp) == {"spearman", "pooled", "auc"}
                for leg in comp.values():
                    assert leg["estimator"] == "E_cond" and leg["B"] == 120
                    assert leg["reading"].startswith("development only")
            assert f["statistic"] == M.S.STAT_LABEL["within"]
            assert set(f["raters"]) >= {"efv_v2_mc", "efv_v2", "prospx_consensus"}
            assert len(f["per_fold"]) == M.SIGN_REQUIRED[fid][1]
            assert f["fold_sign_agreement"]["of"] == M.SIGN_REQUIRED[fid][1]
            assert f["permutation_null"]["n"] == 12 and f["permutation_null"]["seed"] == M.SEED
            assert f["twin"]["seed"] == M.SEED and "delta" in f["twin"]["within"]
            assert f["twin"]["below_arm"] in (True, False)
            assert f["verdict"] == a["reason"] and f["note"] == M.NOTE
            assert f["secondary"]["statistic"] == M.S.STAT_LABEL["pooled"]
            assert len(f["folds"]) == 2 * M.SIGN_REQUIRED[fid][1]
        assert a["holm"] is doc["holm"]["by_arm"][arm]
    assert set(doc["probes"]) == {f"MC-SCREEN:{fid}.{arm}_vs_v2" for arm in M.ARMS for fid in M.FRAMES}
    assert {p["verdict"] for p in doc["probes"].values()} <= {"ADMITTED", "ADOPTABLE", "NULL"}
    assert doc["admitted"] == [a for a in M.ARMS if doc["arms"][a]["admitted"]]
    assert "mc1_listwise" in doc["sensitivities"]
    rw = doc["sensitivities"]["rank_consistent_weight"]
    assert "weights" in rw.get("derivation", {}).get("hit", {}) or "error" not in rw
    for s in F.SIDES:
        for w in rw["rank_consistent_weights"][s].values():
            assert w in M.RANK_WEIGHT_GRID
    for fid in M.FRAMES:
        assert "delta" in rw["frames"][fid]
    # MC-4b on folds under the has-block floor fell back to MC-4a and says so
    assert all("fell_back" in r for r in doc["arms"]["mc4b"]["frames"]["lv_dev"]["folds"].values())
    # the band weights precede the arms in the written file; no em-dash anywhere
    text = out.read_text(encoding="utf-8")
    assert text.find('"band_weights"') < text.find('"arms"')
    assert chr(0x2014) not in text and chr(0x2013) not in text
    assert doc["band_weights"]["hit"]["weights"]["upper"]["hit"]["w_skill"] <= H.W_MAX
    assert doc["band_weights_twin"]["hit"]["twin"]


def test_synthetic_mc1_listwise_and_twins_are_not_the_arm(synthetic_doc):
    doc, _out, _inputs = synthetic_doc
    a = doc["arms"]["mc1"]["frames"]["lv_dev"]
    s = doc["sensitivities"]["mc1_listwise"]["frames"]["lv_dev"]
    assert s["within_vs_v2"]["status"] == "derived"
    assert all(r["pair_weighting"] == "listwise" for r in s["folds"].values())
    assert all(r["pair_weighting"] == "distance" for r in a["folds"].values())
    assert a["twin"]["what"].startswith("driver columns")
    assert doc["arms"]["mc2"]["frames"]["vm_dev"]["twin"]["what"].startswith("source reliability")
    assert doc["arms"]["mc3"]["frames"]["vm_dev"]["twin"]["what"].startswith("band labels")


def test_progress_rows_carry_role_development_and_resolvable_none(synthetic_doc):
    doc, _out, _inputs = synthetic_doc
    assert P.model_class_arm_docs(doc) == []            # exploratory lands nothing
    real = dict(doc, exploratory=False,
                label={"provider": "fwar", "resolved_through": 2026, "id": "fwar@test"})
    docs = P.model_class_arm_docs(real)
    assert [d["model_id"] for d in docs] == [C.ARM_IDS[a] for a in M.ARMS]
    rows = []
    for d in docs:
        rows += P.build_dev_rows(d, sources=[{"path": "data/" + P.MC_SCREEN_NAME,
                                              "generated_at": "g", "sha256": "s"}],
                                 date="2026-10-08", trigger="efv_change",
                                 now_iso="2026-10-08T00:00:00Z", frames=P.DEV_FRAMES,
                                 raters=P.MC_SCREEN_RATERS, deltas=P.MC_SCREEN_DELTAS,
                                 statistic_fields=True)
    assert len(rows) == 10
    for r in rows:
        assert r["role"] == "development" and r["resolvable"] is None
        assert r["note"] == M.NOTE and r["model_id"].startswith(P.MC_SCREEN_MODEL_PREFIX)
        assert r["frame"] in P.DEV_FRAMES and r["tilted"] is False
        assert r["model_version"]["label"] == "fwar@test"
        assert set(r["deltas"]) == {n for n, _ in P.MC_SCREEN_DELTAS}
        assert all(leg["resolvable"] is None for comp in r["deltas"].values()
                   for leg in comp.values())
        assert r["raters"]["efv"]["spearman"] is not None
        assert r["statistic"] == M.S.STAT_LABEL["within"] and "secondary" in r
        assert r["content_hash"] == P.content_hash(r)
    assert any(n == P.MC_SCREEN_NAME and f == P.DEV_FRAMES and rm is P.MC_SCREEN_RATERS
               and dm is P.MC_SCREEN_DELTAS and sub is None
               for n, f, rm, dm, sub in P.DEV_ARTIFACTS)
    assert P.model_class_arm_docs({"role": "development", "arms": []}) == []
    assert P.model_class_arm_docs(None) == []


# ---------------------------------------------------------------------------
# 5. one run: a second run refuses
# ---------------------------------------------------------------------------

def test_a_second_run_with_an_existing_artifact_refuses_as_spent(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    out = data / "efv_v2_model_class_screen.json"
    out.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(M.H, "DATA_DIR", data)
    monkeypatch.setattr(M, "OUT_PATH", out)

    def no_build(*_a, **_k):
        raise AssertionError("the frames were built after the refusal")
    monkeypatch.setattr(M, "build_inputs", no_build)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = M.main([])
    assert rc == 2 and "spent" in buf.getvalue()
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = M.main(["--out", str(out), "--B", "50"])
    assert rc == 2
    assert M._is_under_data(out) and not M._is_under_data(tmp_path / "elsewhere.json")


# ---------------------------------------------------------------------------
# 6. the restore list, the registration echo, copy
# ---------------------------------------------------------------------------

def test_conftest_restores_the_screen_artifacts():
    import conftest as CT
    for rel in ("data/efv_progress.json", "data/xfv_arm_ledger.json",
                "data/efv_v2_model_class_screen.json"):
        assert rel in CT._SIDECAR_GLOBS
    targets = {(m, a): rel for m, a, rel in CT._SIDECAR_WRITE_TARGETS}
    assert targets[("tools.efv_v2_model_class_screen", "OUT_PATH")] == (
        "data/efv_v2_model_class_screen.json")
    assert targets[("tools.efv_arm_ledger", "OUT")] == "data/xfv_arm_ledger.json"


def test_registration_constants_and_copy():
    assert M.ARMS == C.FAMILY == ("mc1", "mc2", "mc3", "mc4a", "mc4b")
    assert M.HOLM_M == 5 and M.B_DEFAULT == 2000 and M.SEED == 20260906 and M.N_PERM == 500
    assert M.MIN_DELTA == 0.005 and M.NONINFERIORITY == -0.005
    assert M.SIGN_REQUIRED == {"lv_dev": (2, 3), "vm_dev": (5, 7)}
    assert M.FORKING_PATHS_ADDED == 10 and M.NOTE == "model-class screen, spent frame, not a claim"
    import efv_arm_ledger as AL
    assert any(n == "efv_v2_model_class_screen.json" and k == "probes" for n, k, _ in AL.PROBES)
    for name in ("tools/efv_v2_model_class_screen.py", "test_efv_v2_model_class_screen.py"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert chr(0x2014) not in text and chr(0x2013) not in text
