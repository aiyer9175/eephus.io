"""Driver System V2 core pins (docs/efv-v2/DRIVER_SYSTEM_V2.md s5): DS-04 (missingness
rewrite, bug B3), DS-05 (the SCRAP list, pinned feature lists) and DS-06 (the admission
rule and its per-vintage signs in the arm ledger).

These are TRAINING paths only. The served eFV v1 lists (efv_model._FEATURES_HIT /
_FEATURES_PIT) are pinned unchanged here too, because DS-02, not this step, is where the
served grade moves.
"""
from __future__ import annotations

import ast
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_model as V1  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_vintage_frame as F  # noqa: E402

ADMISSION = ROOT / "data" / "xfv_driver_admission.json"
LEDGER = ROOT / "data" / "xfv_arm_ledger.json"


# ---------------------------------------------------------------------------
# DS-05: the lists, pinned
# ---------------------------------------------------------------------------

def test_v2_feature_lists_pinned():
    assert H.V2_SKILL_KEYS == {
        "hit": ("obp_rel", "contact", "tool_hit", "tool_speed", "is_college",
                "level_rank"),
        "pit": (),
    }
    assert H.V2_TIMING_KEYS == {"hit": ("age_rel_level", "level_rank"),
                                "pit": ("age_rel_level", "level_rank")}
    assert H.V2_PIT_SKILL_CANDIDATES == ("k_rel",)
    assert H.V2_ABSENCE_KEY == "milb_absent"
    assert set(H.V2_SCRAPPED["pit"]) == {"peak_k_rel", "k_rel", "bb_rel",
                                         "age_rel_level", "x_era_k", "tool_fb", "age",
                                         "seasons_at_level"}
    assert set(H.V2_SCRAPPED["hit"]) == {"age", "milb_missing", "n_milb_seasons",
                                         "ops_rel", "is_ifa", "k_rel", "peak_k_rel"}


def test_scrapped_drivers_never_reach_a_skill_list():
    for side in F.SIDES:
        assert not set(H.skill_keys(side)) & set(H.V2_SCRAPPED[side]), side
    assert H.skill_keys("pit") == ()                      # owner DS-Q2
    for side in F.SIDES:
        assert "age" not in H.timing_keys(side, ids_outcome_blind=True,
                                          absence_admitted=True)


def test_served_v1_lists_untouched():
    """The served grade does not move in this step (DS-02 serves V2)."""
    hit, _ = V1._feature_spec("hit")
    pit, _ = V1._feature_spec("pit")
    assert hit == ["fv", "obp_rel", "k_rel", "peak_k_rel", "age_rel_level",
                   "n_milb_seasons", "tool_hit", "tool_speed", "milb_missing", "is_ifa",
                   "is_college", "ops_rel", "age", "level_rank"]
    assert pit == ["fv", "peak_k_rel", "k_rel", "bb_rel", "age_rel_level", "x_era_k",
                   "tool_fb", "age", "seasons_at_level"]
    assert V1.NEUTRAL_MILB_IMPUTE is False


# ---------------------------------------------------------------------------
# DS-04: missingness
# ---------------------------------------------------------------------------

def _feats(block: bool, **kw):
    f = {"milb_unavailable": 0.0 if block else 1.0, "milb_missing": 0.0,
         "obp_rel": 0.0, "k_rel": 0.0, "peak_k_rel": 0.0, "level_rank": 0.0,
         "age_rel_level": 0.0, "tool_hit": 50.0, "tool_speed": 48.0,
         "is_college": 0.0, "is_ifa": 0.0, "pick_missing": 1.0}
    f.update(kw)
    return f


def _row(i, yr, block, target, fv, reached=1.0, **kw):
    return {"player_key": f"p{i}", "decision_year": yr, "fv": fv, "target": target,
            "weight": 1.0, "reached": reached, "kind": "debuted" if reached else "bust",
            "feats": _feats(block, **kw)}


def test_no_block_row_imputes_at_the_has_block_train_mean_not_raw_zero():
    rows = H.attach_v2([
        _row(0, 2018, True, 1.0, 45, obp_rel=0.04, level_rank=4.0, k_rel=-0.02,
             peak_k_rel=-0.04),
        _row(1, 2018, True, 1.0, 45, obp_rel=0.02, level_rank=2.0, k_rel=0.0,
             peak_k_rel=-0.02),
        _row(2, 2018, False, 0.0, 45),
    ])
    nb = rows[2]["v2"]
    assert nb["has_block"] is False and nb[H.V2_ABSENCE_KEY] == 1.0
    assert all(nb[k] is None for k in H.V2_MILB_KEYS)
    means = H.has_block_means(rows)
    assert means["level_rank"] == pytest.approx(3.0)
    assert means["obp_rel"] == pytest.approx(0.03)
    assert means["contact"] == pytest.approx(0.02)
    vec = H.v2_vector(nb, ("level_rank", "obp_rel", "contact"), means)
    assert vec == pytest.approx([3.0, 0.03, 0.02])
    # the milb_missing population is a no-block row too
    assert H.v2_row(_feats(True, milb_missing=1.0))["has_block"] is False


def test_unknown_acquisition_imputes_the_college_flag():
    known = H.v2_row(_feats(True, is_college=1.0, pick_missing=0.0))
    ifa = H.v2_row(_feats(True, is_ifa=1.0))
    unknown = H.v2_row(_feats(True, is_college=0.0, pick_missing=1.0))
    assert known["acq_known"] and known["is_college"] == 1.0
    assert ifa["acq_known"] and ifa["is_college"] == 0.0
    assert not unknown["acq_known"] and unknown["is_college"] is None


def test_contact_merges_the_two_strikeout_rates():
    v = H.v2_row(_feats(True, k_rel=0.04, peak_k_rel=0.02))
    assert v["contact"] == pytest.approx(-0.03)


def _synthetic(n_per_year=120, years=range(2016, 2022), seed=7):
    rng = np.random.default_rng(seed)
    out, i = [], 0
    for yr in years:
        for _ in range(n_per_year):
            block = bool(rng.random() < 0.6)
            fv = float(rng.normal(45, 5))
            th = float(rng.normal(50, 8))
            t = 0.1 * (fv - 45) + 0.05 * (th - 50) + float(rng.normal(0, 1))
            out.append(_row(i, yr, block, t, fv, reached=float(t > 0), tool_hit=th,
                            obp_rel=float(rng.normal(0, 0.03)) if block else 0.0,
                            level_rank=float(rng.integers(0, 6)) if block else 0.0,
                            k_rel=float(rng.normal(0, 0.05)) if block else 0.0,
                            peak_k_rel=float(rng.normal(0, 0.05)) if block else 0.0,
                            age_rel_level=float(rng.normal(0, 1)) if block else 0.0))
            i += 1
    return H.attach_v2(out)


def test_skill_head_trains_on_has_block_rows_only():
    rows = _synthetic()
    head = H.fit_skill_head(rows, "hit", admit=False, alpha=1.0)
    assert head is not None
    assert head["trained_on"] == "has_block"
    assert head["n_train"] == sum(1 for r in rows if r["v2"]["has_block"])
    assert H.skill_training_rows(rows) and all(r["v2"]["has_block"]
                                               for r in H.skill_training_rows(rows))
    # the no-block rows' features cannot move the slopes: rewrite them and refit
    moved = [dict(r, v2=dict(r["v2"], tool_hit=99.0)) if not r["v2"]["has_block"]
             else r for r in rows]
    head2 = H.fit_skill_head(moved, "hit", admit=False, alpha=1.0)
    assert head2["beta"] == pytest.approx(head["beta"])


def test_absence_flag_never_in_the_skill_design_matrix():
    rows = _synthetic()
    head = H.fit_skill_head(rows, "hit", admit=False, alpha=1.0)
    X = H.skill_design(rows, head)
    assert X.shape == (len(rows), len(head["keys"]))
    assert H.V2_ABSENCE_KEY not in head["keys"]
    bad = dict(head, keys=head["keys"] + [H.V2_ABSENCE_KEY])
    with pytest.raises(ValueError):
        H.skill_design(rows, bad)
    assert H.V2_ABSENCE_KEY not in H.skill_keys("hit")


def test_absence_flag_reaches_timing_only_on_outcome_blind_admitted_ids():
    for side in F.SIDES:
        assert H.V2_ABSENCE_KEY not in H.timing_keys(side)
        assert H.V2_ABSENCE_KEY not in H.timing_keys(side, ids_outcome_blind=True)
        assert H.V2_ABSENCE_KEY not in H.timing_keys(side, absence_admitted=True)
        assert H.V2_ABSENCE_KEY in H.timing_keys(side, ids_outcome_blind=True,
                                                 absence_admitted=True)
    head = H.fit_timing_head(_synthetic(), "hit", admit=False, alpha=1.0)
    assert head is not None and H.V2_ABSENCE_KEY not in head["keys"]


def test_consensus_is_a_free_control_not_a_driver():
    """Consensus enters as the unpenalized u_c column; the head's score is the driver
    part alone, so a driver-free row scores the same as any other at the means."""
    rows = _synthetic()
    head = H.fit_skill_head(rows, "hit", admit=False, alpha=1.0)
    assert "b_uc" in head and "fv" not in head["keys"]
    z = H.z_skill(head, rows)
    assert np.isfinite(z).all()
    assert H.z_skill(None, rows).tolist() == [0.0] * len(rows)


def test_pitcher_skill_head_is_consensus_only():
    assert H.fit_skill_head(_synthetic(), "pit") is None


def test_reserved_decision_years_raise():
    rows = _synthetic(years=range(2023, 2026))
    with pytest.raises(F.ReservedFrameError):
        H.fit_skill_head(rows, "hit")
    with pytest.raises(F.ReservedFrameError):
        H.admission_for_key(rows, "tool_hit")


@pytest.mark.skipif(not (ROOT / "data" / "xfv_hitter_matrix.json").exists(),
                    reason="training matrices absent")
def test_real_skill_head_rows_all_have_blocks():
    rows = H.attach_v2([r for r in H.training_rows("hit") if r["decision_year"] < 2024])
    head = H.fit_skill_head(rows, "hit")
    assert head is not None
    assert head["n_train"] == sum(1 for r in rows if r["v2"]["has_block"])
    assert set(head["keys"]) <= set(H.skill_keys("hit"))
    assert all(head["admission"][k]["admitted"] for k in head["keys"])


# ---------------------------------------------------------------------------
# DS-06: the admission rule
# ---------------------------------------------------------------------------

def test_rule_refuses_one_flipped_sign():
    ok = H.admission_check({2018: 1.5, 2019: 2.0, 2020: 1.1})
    assert ok["admitted"] and ok["sign"] == 1
    assert ok["per_vintage_signs"] == {"2018": 1, "2019": 1, "2020": 1}
    flip = H.admission_check({2018: 1.5, 2019: -0.2, 2020: 3.0})
    assert not flip["admitted"] and flip["reason"] == "sign flipped between training vintages"
    assert flip["per_vintage_signs"]["2019"] == -1


def test_rule_needs_mean_abs_t_and_two_vintages():
    assert not H.admission_check({2018: 0.5, 2019: 0.9})["admitted"]
    assert H.admission_check({2018: -1.2, 2019: -0.9})["admitted"]
    assert not H.admission_check({2019: 4.0})["admitted"]
    lone = H.admission_check({2017: None, 2018: 3.0, 2019: None})
    assert not lone["admitted"] and lone["vintages_without_t"] == [2017, 2019]


def test_admission_on_synthetic_vintages():
    rows = _synthetic(n_per_year=200)
    good = H.admission_for_key(rows, "tool_hit", has_block_only=False)
    assert good["admitted"] and good["sign"] == 1
    # break the sign in one vintage: flip tool_hit around its mean in 2019 only
    flipped = [dict(r, v2=dict(r["v2"], tool_hit=100.0 - r["v2"]["tool_hit"]))
               if r["decision_year"] == 2019 else r for r in rows]
    bad = H.admission_for_key(flipped, "tool_hit", has_block_only=False)
    assert not bad["admitted"] and bad["per_vintage_signs"]["2019"] == -1


def test_admission_t_matches_ols():
    rng = np.random.default_rng(3)
    u = rng.random(200)
    x = rng.normal(size=200)
    y = 0.3 * u + 0.2 * x + rng.normal(0, 0.5, 200)
    t = H.admission_t(u, y, x)
    z = (x - x.mean()) / x.std()
    X = np.column_stack([np.ones(200), u, z])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    r = y - X @ b
    se = math.sqrt(r @ r / 197 * np.linalg.inv(X.T @ X)[2, 2])
    assert t == pytest.approx(b[2] / se)
    assert H.admission_t(u[:10], y[:10], x[:10]) is None       # below the row floor


def test_admission_artifact_carries_per_vintage_signs():
    if not ADMISSION.exists():
        pytest.skip("data/xfv_driver_admission.json not built")
    doc = json.loads(ADMISSION.read_text(encoding="utf-8"))
    assert doc["role"] == "development"
    assert doc["rule"]["min_mean_abs_t"] == H.ADMIT_MIN_MEAN_ABS_T
    for tag, a in doc["arms"].items():
        assert a["per_vintage_signs"], tag
        assert all(int(v) < F.R_VM_FIRST_DEBUT_YEAR for v in a["per_vintage_signs"])
        again = H.admission_check({int(v): t for v, t in a["t_by_vintage"].items()})
        assert again["admitted"] is a["admitted"], tag
        assert a["verdict"] == ("ADMITTED" if a["admitted"] else "REFUSED")
        if len(set(a["per_vintage_signs"].values())) > 1:
            assert not a["admitted"], tag
    # every V2 candidate is on the record
    want = {f"DS-06:{s}.skill.{k}" for s in F.SIDES
            for k in (H.skill_keys(s) or H.V2_PIT_SKILL_CANDIDATES)}
    want |= {f"DS-06:{s}.timing.{k}" for s in F.SIDES for k in H.timing_keys(s)}
    assert set(doc["arms"]) == want


def test_arm_ledger_carries_the_signs():
    if not (LEDGER.exists() and ADMISSION.exists()):
        pytest.skip("ledger or admission artifact not built")
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    rows = [r for r in led["arms"] if r["lane"] == "admission rule (DS-06)"]
    doc = json.loads(ADMISSION.read_text(encoding="utf-8"))
    assert len(rows) == len(doc["arms"])
    for r in rows:
        assert r["per_vintage_signs"] == doc["arms"][r["arm"]]["per_vintage_signs"]
        assert r["verdict"] in ("ADMITTED", "REFUSED")
    assert led["n_probes"] == len(led["probes"]) > 0
    assert all(p["lane"] != r["lane"] for p in led["probes"] for r in rows)


@pytest.mark.parametrize("mod", ["tools/efv_driver_admission.py",
                                 "tools/efv_identity_balance.py", "efv_identity.py"])
def test_new_modules_group_nothing_by_grade(mod):
    tree = ast.parse((ROOT / mod).read_text(encoding="utf-8"))
    banned = ("groupby", "tier", "bucket", "cell", "stratum", "strata", "by_fv",
              "fv_band", "fv_bin")
    grid = {35, 40, 45, 50, 55, 60, 65, 70, 75, 80}
    for node in ast.walk(tree):
        name = (node.id if isinstance(node, ast.Name) else
                node.attr if isinstance(node, ast.Attribute) else
                node.name if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else None)
        if name:
            assert not any(t in name.lower() for t in banned), (mod, name)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            assert node.value not in grid, (mod, node.value, node.lineno)
